from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from paranoia_local import class_closure as cc, handlers, plan_claims as pc
from paranoia_local.engines import Review


PLAN = "# Rollout\n\nPython 3.11 was released in October 2022.\n"
REPO_PLAN = "# Config\n\nThe setting is enabled.\n"


def _source(
    *,
    url: str = "https://www.python.org/downloads/release/python-3110/",
    kind: str = "primary",
    relation: str = "supports_claim",
    quote: str = "Python 3.11.0 was released on Monday, October 24, 2022.",
) -> dict[str, str]:
    return {
        "url": url,
        "title": "Python 3.11.0",
        "publisher": "Python Software Foundation",
        "source_kind": kind,
        "authority_basis": "The Python Software Foundation publishes Python releases.",
        "location": "Release page, first paragraph",
        "quote": quote,
        "relation": relation,
    }


def _claim(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "kind": "fact",
        "scope": "external",
        "anchor": "Python 3.11 was released in October 2022.",
        "proposition": "Python 3.11 was released in October 2022.",
        "prior_claim_id": None,
        "verdict": "supported",
        "evidence": [_source()],
        "replacement": None,
        "rationale": "The official release page directly gives the date.",
    }
    value.update(changes)
    return value


def _repository_claim(*, url: str, quote: str = '"enabled": true') -> dict[str, object]:
    return {
        "kind": "fact",
        "scope": "repository",
        "anchor": "The setting is enabled.",
        "proposition": "The repository setting is enabled.",
        "prior_claim_id": None,
        "verdict": "supported",
        "evidence": [{
            "url": url,
            "title": "Settings",
            "publisher": "Repository",
            "source_kind": "repository",
            "authority_basis": "The cited repository bytes define the setting.",
            "location": "enabled field",
            "quote": quote,
            "relation": "supports_claim",
        }],
        "replacement": None,
        "rationale": "The exact field is present.",
    }


def _audit(
    *claims: dict[str, object], dispositions: list[dict[str, str]] | None = None,
    assessments: list[dict[str, str]] | None = None,
) -> str:
    payload = {
        "claims": list(claims),
        "coverage": {
            "sections_scanned": 1, "omitted_nonfacts": 1,
            "prior_assessments": assessments or [],
            "prior_dispositions": dispositions or [], "notes": "complete",
        },
    }
    return pc.AUDIT_MARKER + "\n" + json.dumps(payload)


class TestAuditValidation:
    def test_primary_exact_passage_can_support_an_atomic_fact(self) -> None:
        audit = pc.parse_audit(_audit(_claim()), PLAN)
        state = pc.reconcile(
            {}, audit, lineage_id="x-plan", round_no=1, plan_text=PLAN
        )
        assert not pc.is_blocked(state)
        assert next(iter(state["claims"].values()))["verdict"] == "supported"

    def test_verbatim_anchor_may_cross_markdown_line_wrapping(self) -> None:
        wrapped = "# Release\n\nPython 3.11 was released\nin October 2022.\n"
        claim = _claim(
            anchor="Python 3.11 was released in October 2022.",
            proposition="Python 3.11 was released in October 2022.",
        )
        assert len(pc.parse_audit(_audit(claim), wrapped).claims) == 1

    def test_reddit_is_never_upgraded_to_primary_by_model_output(self) -> None:
        reddit = _source(url="https://www.reddit.com/r/python/comments/x", kind="primary")
        claim = pc.parse_audit(_audit(_claim(evidence=[reddit])), PLAN).claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["evidence"][0]["source_kind"] == "ugc"

    def test_context_only_support_is_demoted_without_discarding_other_claims(self) -> None:
        context_only = _source(relation="context")
        audit = pc.parse_audit(_audit(
            _claim(evidence=[context_only]),
            _claim(proposition="Python 3.11 became available in October 2022."),
        ), PLAN)
        assert [claim["verdict"] for claim in audit.claims] == ["unverified", "supported"]
        assert "Server demotion" in audit.claims[0]["rationale"]

    def test_wrong_scope_source_is_context_and_claim_is_unverified(self) -> None:
        wrong_scope = _source()
        claim = pc.parse_audit(_audit(_claim(
            scope="repository", evidence=[wrong_scope],
        )), PLAN).claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["evidence"][0]["relation"] == "context"

    def test_repository_support_must_resolve_to_exact_current_bytes(
        self, tmp_path: Path,
    ) -> None:
        (tmp_path / "settings.json").write_text('{"enabled": true}\n')
        audit = pc.parse_audit(
            _audit(_repository_claim(url="repo://settings.json#L1")),
            REPO_PLAN, repo=tmp_path,
        )
        assert audit.claims[0]["verdict"] == "supported"

        with pytest.raises(pc.AuditError, match="does not resolve to bytes"):
            pc.parse_audit(
                _audit(_repository_claim(url="repo://missing.json#L1")),
                REPO_PLAN, repo=tmp_path,
            )

    def test_repository_support_resolves_historical_git_object(
        self, tmp_path: Path,
    ) -> None:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / "settings.json").write_text('{"enabled": true}\n')
        subprocess.run(["git", "add", "settings.json"], cwd=tmp_path, check=True)
        subprocess.run([
            "git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "settings",
        ], cwd=tmp_path, check=True)
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        url = f"repo://git/{revision}:settings.json"
        audit = pc.parse_audit(
            _audit(_repository_claim(url=url)), REPO_PLAN, repo=tmp_path,
        )
        assert audit.claims[0]["evidence"][0]["url"] == url + "#L1"

    def test_repository_location_is_repaired_from_the_exact_quote(
        self, tmp_path: Path,
    ) -> None:
        (tmp_path / "settings.json").write_text('first\nsecond\n{"enabled": true}\n')
        audit = pc.parse_audit(
            _audit(_repository_claim(url="repo://settings.json#L1")),
            REPO_PLAN, repo=tmp_path,
        )
        assert audit.claims[0]["evidence"][0]["url"] == "repo://settings.json#L3"

    def test_whole_file_sha256_is_verified_as_computed_byte_evidence(
        self, tmp_path: Path,
    ) -> None:
        content = b'{"enabled": true}\n'
        (tmp_path / "settings.json").write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        audit = pc.parse_audit(
            _audit(_repository_claim(url="repo://settings.json", quote=digest)),
            REPO_PLAN, repo=tmp_path,
        )
        assert audit.claims[0]["verdict"] == "supported"

    def test_repository_support_rejects_wrong_quote_and_traversal(
        self, tmp_path: Path,
    ) -> None:
        (tmp_path / "settings.json").write_text('{"enabled": false}\n')
        for url in ("repo://settings.json", "repo://../settings.json"):
            with pytest.raises(pc.AuditError, match="does not resolve to bytes"):
                pc.parse_audit(
                    _audit(_repository_claim(url=url)), REPO_PLAN, repo=tmp_path,
                )

    def test_refutation_alone_keeps_packet_but_drops_unsupported_replacement(self) -> None:
        refuting = _source(relation="refutes_claim")
        audit = pc.parse_audit(_audit(_claim(
            verdict="refuted", evidence=[refuting],
            replacement="Python 3.11 was released on 24 October 2022.",
        )), PLAN)
        assert audit.claims[0]["verdict"] == "refuted"
        assert audit.claims[0]["evidence"][0]["relation"] == "refutes_claim"
        assert audit.claims[0]["replacement"] is None

    def test_decisions_never_enter_active_inventory(self) -> None:
        with pytest.raises(pc.AuditError, match='literal \\"fact\\"'):
            pc.parse_audit(_audit(_claim(kind="decision")), PLAN)

    def test_the_incident_pseudo_enum_is_rejected_with_bounded_raw_diagnostics(self) -> None:
        raw = _audit(_claim(kind="fact|decision"))
        with pytest.raises(pc.AuditError) as caught:
            pc.parse_audit(raw, PLAN)
        assert "fact|decision" in caught.value.excerpt
        assert len(caught.value.excerpt) <= pc.DIAGNOSTIC_CHARS + 40
        assert len(caught.value.raw_sha256) == 64

    def test_final_retry_localizes_bad_anchor_and_retains_valid_packets(self) -> None:
        bad = _claim(anchor="This wording is not in the plan.")
        audit = pc.parse_audit(_audit(bad, _claim()), PLAN, allow_partial=True)
        state = pc.reconcile(
            {}, audit, lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        assert len(state["claims"]) == 1
        assert next(iter(state["claims"].values()))["verdict"] == "supported"
        assert "localized invalid claim" in state["debt"]["reason"]
        assert "This wording is not in the plan" in state["debt"]["rejected_excerpt"]
        assert pc.is_blocked(state)

    def test_disposition_rationale_wire_alias_is_normalized_to_reason(self) -> None:
        audit = pc.parse_audit(_audit(
            _claim(),
            dispositions=[{
                "claim_id": "C-old", "disposition": "removed",
                "rationale": "The old exact wording is absent.",
            }],
        ), PLAN)
        assert audit.dispositions == ({
            "claim_id": "C-old", "disposition": "removed",
            "reason": "The old exact wording is absent.",
        },)

    def test_disposition_prior_claim_id_wire_alias_is_normalized(self) -> None:
        audit = pc.parse_audit(_audit(
            _claim(),
            dispositions=[{
                "prior_claim_id": "C-old", "disposition": "removed",
                "rationale": "The old exact wording is absent.",
            }],
        ), PLAN)
        assert audit.dispositions == ({
            "claim_id": "C-old", "disposition": "removed",
            "reason": "The old exact wording is absent.",
        },)


class TestRetainedEvidence:
    def test_corrected_wording_gets_new_identity_and_re_entails_retained_evidence(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        corrected_plan = "# Rollout\n\nPython 3.11 was released on 24 October 2022.\n"
        corrected = _claim(
            anchor="Python 3.11 was released on 24 October 2022.",
            proposition="Python 3.11 was released on 24 October 2022.",
            prior_claim_id=claim_id,
            verdict="unverified",
            evidence=[_source(relation="context")],
        )
        second = pc.reconcile(
            first, pc.parse_audit(_audit(corrected, dispositions=[{
                "claim_id": claim_id, "disposition": "removed",
                "reason": "The old date wording was replaced by the corrected assertion.",
            }]), corrected_plan),
            lineage_id="x-plan", round_no=2, plan_text=corrected_plan,
        )
        replacement_id = next(iter(second["claims"]))
        assert replacement_id != claim_id
        assert pc.is_blocked(second)
        assert second["retired"][-1]["claim_id"] == claim_id
        prompt = pc.audit_instructions(corrected_plan, first, "trusted local tool")
        assert claim_id in prompt and _source()["url"] in prompt
        assert "ABSENT PRIOR ANCHOR CANDIDATES" in prompt
        assert json.dumps({"claim_id": claim_id, "anchor": _claim()["anchor"]},
                          separators=(",", ":")) in prompt

    def test_wrapped_anchor_is_not_a_removal_candidate(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        wrapped = "# Rollout\n\nPython 3.11 was released\nin October 2022.\n"
        prompt = pc.audit_instructions(wrapped, first, "trusted local tool")
        assert "ABSENT PRIOR ANCHOR CANDIDATES (JSON):\n[]" in prompt

    def test_removed_claims_are_retired_and_do_not_consume_active_inventory(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        second = pc.reconcile(
            first, pc.parse_audit(_audit(dispositions=[{
                "claim_id": claim_id, "disposition": "removed",
                "reason": "The release-date assertion is absent from the edited plan.",
            }]), "# Rollout\n\nUse Python.\n"),
            lineage_id="x-plan", round_no=2, plan_text="# Rollout\n\nUse Python.\n",
        )
        assert second["claims"] == {}
        assert len(second["retired"]) == 1
        assert not pc.is_blocked(second)
        assert "1 retired and excluded from active inventory" in pc.render_trailer(second)

    def test_model_omission_is_rejected_when_a_claim_is_not_frozen(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        with pytest.raises(pc.AuditError, match=claim_id):
            pc.reconcile(
                first, pc.parse_audit(_audit(), PLAN),
                lineage_id="x-plan", round_no=2, plan_text=PLAN,
            )

    def test_supported_exact_claim_is_frozen_out_of_targeted_inventory(
        self, tmp_path: Path,
    ) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        frozen = pc.frozen_supported_ids(first, PLAN, repo=tmp_path)
        assert frozen == {claim_id}
        prompt = pc.targeted_audit_instructions(PLAN, first, "trusted local tool", frozen)
        assert claim_id not in prompt
        assert "(no textual changes)" in prompt
        second = pc.reconcile(
            first, pc.parse_audit(_audit(), PLAN),
            lineage_id="x-plan", round_no=2, plan_text=PLAN, frozen_ids=frozen,
        )
        assert second["claims"][claim_id]["verified_round"] == 1
        assert second["claims"][claim_id]["retained_round"] == 2
        assert not pc.is_blocked(second)

    def test_failed_targeted_audit_does_not_invalidate_frozen_support(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        failed = pc.with_debt(
            first, pc.AuditError("edited successor audit failed"),
            round_no=2, plan_text=PLAN, frozen_ids={claim_id},
        )
        assert failed["claims"][claim_id]["verdict"] == "supported"
        assert failed["debt"]["reason"] == "edited successor audit failed"
        assert pc.is_blocked(failed)

    def test_targeted_audit_cannot_reemit_a_frozen_claim(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        with pytest.raises(pc.AuditError, match="frozen claims were re-emitted"):
            pc.reconcile(
                first, pc.parse_audit(_audit(_claim()), PLAN),
                lineage_id="x-plan", round_no=2, plan_text=PLAN,
                frozen_ids={claim_id},
            )

    def test_targeted_round_verifies_edited_successor_and_freezes_unchanged_claim(self) -> None:
        sqlite_old = "SQLite 3.45.0 was released on 15 January 2024."
        first_plan = PLAN + sqlite_old + "\n"
        sqlite_claim = _claim(anchor=sqlite_old, proposition=sqlite_old)
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(), sqlite_claim), first_plan),
            lineage_id="x-plan", round_no=1, plan_text=first_plan,
        )
        python_id = next(
            claim_id for claim_id, claim in first["claims"].items()
            if claim["proposition"].startswith("Python")
        )
        sqlite_id = next(claim_id for claim_id in first["claims"] if claim_id != python_id)
        sqlite_new = "SQLite 3.45.0 was released on 15 January 2025."
        second_plan = PLAN + sqlite_new + "\n"
        frozen = pc.frozen_supported_ids(first, second_plan)
        assert frozen == {python_id}
        prompt = pc.targeted_audit_instructions(
            second_plan, first, "trusted local tool", frozen,
        )
        assert python_id not in prompt
        assert sqlite_id in prompt
        assert "-SQLite 3.45.0 was released on 15 January 2024." in prompt
        assert "+SQLite 3.45.0 was released on 15 January 2025." in prompt

        successor = _claim(anchor=sqlite_new, proposition=sqlite_new)
        audit = pc.parse_audit(_audit(successor, dispositions=[{
            "claim_id": sqlite_id, "disposition": "removed",
            "reason": "The old SQLite date wording was replaced.",
        }]), second_plan)
        second = pc.reconcile(
            first, audit, lineage_id="x-plan", round_no=2,
            plan_text=second_plan, frozen_ids=frozen,
        )
        assert second["claims"][python_id]["verified_round"] == 1
        assert sqlite_id not in second["claims"]
        assert any(item["claim_id"] == sqlite_id for item in second["retired"])
        assert len(second["claims"]) == 2

    def test_compact_assessment_reentails_retained_packet_without_repeating_it(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        second = pc.reconcile(
            first, pc.parse_audit(_audit(assessments=[{
                "claim_id": claim_id,
                "verdict": "supported",
                "rationale": "The retained official passage still entails the exact claim.",
            }]), PLAN),
            lineage_id="x-plan", round_no=2, plan_text=PLAN,
        )
        assert list(second["claims"]) == [claim_id]
        assert second["claims"][claim_id]["verdict"] == "supported"
        assert second["claims"][claim_id]["verified_round"] == 2
        assert second["claims"][claim_id]["evidence"] == first["claims"][claim_id]["evidence"]
        assert not pc.is_blocked(second)

    def test_compact_support_cannot_retain_a_nonresolving_repository_packet(
        self, tmp_path: Path,
    ) -> None:
        legacy = pc.reconcile(
            {}, pc.parse_audit(_audit(_repository_claim(url="repo://wrong-id.json")), REPO_PLAN),
            lineage_id="x-plan", round_no=1, plan_text=REPO_PLAN,
        )
        claim_id = next(iter(legacy["claims"]))
        assessment = pc.parse_audit(_audit(assessments=[{
            "claim_id": claim_id,
            "verdict": "supported",
            "rationale": "The old packet still looks plausible.",
        }]), REPO_PLAN)
        second = pc.reconcile(
            legacy, assessment, lineage_id="x-plan", round_no=2,
            plan_text=REPO_PLAN, repo=tmp_path,
        )
        assert second["claims"][claim_id]["verdict"] == "unverified"
        assert "Server demotion" in second["claims"][claim_id]["rationale"]

    def test_compact_support_cannot_upgrade_a_nonqualifying_retained_packet(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(evidence=[_source(relation="context")])), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        audit = pc.parse_audit(_audit(assessments=[{
            "claim_id": claim_id,
            "verdict": "supported",
            "rationale": "The old context still looks plausible.",
        }]), PLAN)
        with pytest.raises(pc.AuditError, match="no qualifying supports_claim evidence"):
            pc.reconcile(
                first, audit, lineage_id="x-plan", round_no=2, plan_text=PLAN,
            )

    def test_unrelated_prior_id_cannot_replace_the_old_claim(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        old_id = next(iter(first["claims"]))
        expanded_plan = PLAN + "SQLite 3.45.0 was released on 15 January 2024.\n"
        unrelated = _claim(
            anchor="SQLite 3.45.0 was released on 15 January 2024.",
            proposition="SQLite 3.45.0 was released on 15 January 2024.",
            prior_claim_id=old_id,
        )
        second = pc.reconcile(
            first, pc.parse_audit(_audit(unrelated, assessments=[{
                "claim_id": old_id, "verdict": "supported",
                "rationale": "The retained passage still entails the old exact claim.",
            }]), expanded_plan),
            lineage_id="x-plan", round_no=2, plan_text=expanded_plan,
        )
        assert old_id in second["claims"]
        assert second["claims"][old_id]["verdict"] == "supported"
        assert len(second["claims"]) == 2
        assert not pc.is_blocked(second)

    def test_opposite_punctuation_propositions_never_share_identity(self) -> None:
        old_plan = "# Check\n\nThe values satisfy A != B.\n"
        old_claim = _claim(
            anchor="The values satisfy A != B.",
            proposition="The values satisfy A != B.",
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(old_claim), old_plan),
            lineage_id="x-plan", round_no=1, plan_text=old_plan,
        )
        old_id = next(iter(first["claims"]))
        both_plan = old_plan + "The values satisfy A == B.\n"
        opposite = _claim(
            anchor="The values satisfy A == B.",
            proposition="The values satisfy A == B.",
            prior_claim_id=old_id,
        )
        second = pc.reconcile(
            first, pc.parse_audit(_audit(opposite, assessments=[{
                "claim_id": old_id, "verdict": "supported",
                "rationale": "The retained passage still entails the old exact claim.",
            }]), both_plan),
            lineage_id="x-plan", round_no=2, plan_text=both_plan,
        )
        assert old_id in second["claims"]
        assert second["claims"][old_id]["verdict"] == "supported"
        assert len(second["claims"]) == 2

    def test_nonfactual_is_not_an_accepted_disposition(self) -> None:
        with pytest.raises(pc.AuditError, match="must be removed"):
            pc.parse_audit(_audit(dispositions=[{
                "claim_id": "C-old", "disposition": "nonfactual",
                "reason": "The model changed its mind.",
            }]), PLAN)

    def test_structural_context_contains_full_evidence_for_independent_audit(self) -> None:
        state = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        context = pc.review_context(state)
        source = _source()
        assert source["url"] in context
        assert source["quote"] in context
        assert source["authority_basis"] in context

    def test_action_packet_returns_exact_passage_and_location(self) -> None:
        refuted = _claim(
            verdict="refuted",
            evidence=[
                _source(relation="refutes_claim", quote="The release date was October 24, 2022."),
                _source(relation="supports_replacement", quote="The release date was October 24, 2022."),
            ],
            replacement="Python 3.11 was released on 24 October 2022.",
        )
        state = pc.reconcile(
            {}, pc.parse_audit(_audit(refuted), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        packet = pc.render_trailer(state)
        assert "Evidence-entailled replacement" in packet
        assert "Release page, first paragraph" in packet
        assert "The release date was October 24, 2022." in packet


class ScriptedEngine:
    name = "codex"
    default_model = "test-model"
    native_web = True

    def __init__(self, *outputs: object) -> None:
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def run(self, prompt, cwd, model, effort, web_search, **kwargs):
        self.prompts.append(prompt)
        output = self.outputs.pop(0)
        if isinstance(output, Review):
            return output
        return Review(text=str(output), session_ref="session", raw="")

    def resume(self, session_ref, prompt, cwd, model, effort, web_search, **kwargs):
        self.prompts.append(prompt)
        output = self.outputs.pop(0)
        if isinstance(output, Review):
            return output
        return Review(text=str(output), session_ref=session_ref, raw="")


STRUCTURAL_CLEAR = """## What works
Nothing notable.
## What doesn't work
CONVERGED — no blocking findings at this round.
## Risks
Nothing notable.
## Gaps
Nothing notable.
## Improvements
Nothing notable.

=== CLASS REGISTER ===
NONE"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


class TestHandlerFlow:
    def test_refuted_claim_blocks_and_emits_a_packet_for_autonomous_correction(
        self, tmp_path: Path
    ) -> None:
        refuted = _claim(
            verdict="refuted",
            evidence=[_source(relation="refutes_claim")],
            replacement=None,
        )
        engine = ScriptedEngine(_audit(refuted), STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "lineage": "flow-plan", "round": 1,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        assert "CLAIM-CLOSURE: 0 supported, 1 refuted" in out
        assert "ACTIONABLE SOURCE PACKETS" in out
        assert "CONVERGENCE: BLOCKED — factual claim closure" in out
        assert "BUILT-IN web search" in engine.prompts[0]
        assert "FACTUAL CLAIM REGISTER" in engine.prompts[1]

    def test_supported_claim_and_closed_classes_produce_one_governing_clearance(
        self, tmp_path: Path
    ) -> None:
        engine = ScriptedEngine(_audit(_claim()), STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "lineage": "clear-plan", "round": 3,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T3",
        )
        assert "CLAIM-CLOSURE: 1 supported, 0 refuted, 0 unverified" in out
        assert "CLASS-CONVERGENCE: NOT-BLOCKED" in out
        assert out.count("\nCONVERGENCE:") == 1
        assert "CONVERGENCE: NOT-BLOCKED" in out

    def test_unchanged_supported_round_skips_claim_model_but_keeps_structural_review(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        first_engine = ScriptedEngine(_audit(_claim()), STRUCTURAL_CLEAR)
        handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(repo),
                "lineage": "retained-flow-plan", "round": 1,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=first_engine, log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        second_engine = ScriptedEngine(STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(repo),
                "lineage": "retained-flow-plan", "round": 2,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=second_engine, log_dir=tmp_path / "logs", now=lambda: "T2",
        )
        assert len(second_engine.prompts) == 1
        assert "adversarial reviewer of plans" in second_engine.prompts[0]
        assert "factual-verification phase" not in second_engine.prompts[0]
        assert "CLAIM-CLOSURE: 1 supported, 0 refuted, 0 unverified" in out
        assert "CONVERGENCE: NOT-BLOCKED" in out

    def test_web_search_cannot_be_disabled_while_verification_is_on(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="requires.*built-in web search"):
            handlers.critique_plan(
                {
                    "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                    "lineage": "no-web-plan", "round": 1,
                    "claim_verification": True, "web_search": False,
                },
                engine=ScriptedEngine(), log_dir=tmp_path / "logs", now=lambda: "T1",
            )

    def test_one_shot_structural_review_emits_no_computed_clearance(self, tmp_path: Path) -> None:
        failure = Review(
            text="structural reviewer timed out", session_ref=None, raw="timeout",
            returncode=124, error=True,
        )
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "class_closure": False, "claim_verification": True,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=ScriptedEngine(_audit(_claim()), failure),
            log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        assert "REVIEW FAILED" in out
        assert "CONVERGENCE:" not in out
        assert "CLAIM-CLOSURE: 1 supported" in out
