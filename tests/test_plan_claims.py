from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from paranoia_local import (
    class_closure as cc,
    external_sources,
    handlers,
    plan_claims as pc,
)
from paranoia_local.engines import Review


PLAN = "# Rollout\n\nPython 3.11 was released in October 2022.\n"


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

    @pytest.mark.parametrize("url", [
        "repo://docs/plan.md", "file:///tmp/evidence.txt", "custom://authority/item",
    ])
    def test_non_web_locations_cannot_govern_external_verdicts(self, url: str) -> None:
        source = _source(url=url, kind="primary")
        claim = pc.parse_audit(_audit(_claim(evidence=[source])), PLAN).claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["evidence"][0]["relation"] == "context"

    @pytest.mark.parametrize("url", [
        "https://github.com/example/project/blob/main/docs/plan.md",
        "https://raw.githubusercontent.com/example/project/main/docs/plan.md",
    ])
    def test_plan_repository_web_url_cannot_govern_its_own_claim(
        self, repo: Path, url: str,
    ) -> None:
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:example/project.git"],
            cwd=repo, check=True,
        )
        source = _source(url=url, kind="primary")
        claim = pc.parse_audit(
            _audit(_claim(evidence=[source])), PLAN,
            repo=repo, plan_repo_path="docs/plan.md",
        ).claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["evidence"][0]["relation"] == "context"

    def test_other_same_repository_web_page_is_not_mistaken_for_the_plan(
        self, repo: Path,
    ) -> None:
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/example/project.git"],
            cwd=repo, check=True,
        )
        source = _source(
            url="https://github.com/example/project/blob/main/docs/source.md",
            kind="primary",
        )
        claim = pc.parse_audit(
            _audit(_claim(evidence=[source])), PLAN,
            repo=repo, plan_repo_path="docs/plan.md",
        ).claims[0]
        assert claim["verdict"] == "supported"

    def test_persisted_plan_self_evidence_cannot_freeze_after_upgrade(
        self, repo: Path,
    ) -> None:
        self_source = _source(
            url="https://github.com/example/project/blob/main/docs/plan.md",
            kind="primary",
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(evidence=[self_source])), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:example/project.git"],
            cwd=repo, check=True,
        )
        assert not pc.frozen_supported_ids(
            first, PLAN, repo=repo, plan_repo_path="docs/plan.md",
        )

    def test_persisted_plan_self_evidence_cannot_govern_compact_assessment(
        self, repo: Path,
    ) -> None:
        self_source = _source(
            url="https://github.com/example/project/blob/main/docs/plan.md",
            kind="primary", relation="refutes_claim",
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(
                verdict="refuted", evidence=[self_source],
            )), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:example/project.git"],
            cwd=repo, check=True,
        )
        assessment = pc.parse_audit(_audit(assessments=[{
            "claim_id": claim_id, "verdict": "refuted",
            "rationale": "The old packet still contradicts the claim.",
        }]), PLAN)
        with pytest.raises(pc.AuditError, match="no qualifying refutes_claim evidence"):
            pc.reconcile(
                first, assessment, lineage_id="x-plan", round_no=2,
                plan_text=PLAN, repo=repo, plan_repo_path="docs/plan.md",
            )

    def test_context_only_support_is_demoted_without_discarding_other_claims(self) -> None:
        context_only = _source(relation="context")
        audit = pc.parse_audit(_audit(
            _claim(evidence=[context_only]),
            _claim(proposition="Python 3.11 became available in October 2022."),
        ), PLAN)
        assert [claim["verdict"] for claim in audit.claims] == ["unverified", "supported"]
        assert "Server demotion" in audit.claims[0]["rationale"]

    def test_fresh_repository_scope_enters_correction_instead_of_disappearing(self) -> None:
        with pytest.raises(pc.AuditError, match="repository/internal assertions"):
            pc.parse_audit(_audit(_claim(scope="repository")), PLAN)

    def test_unknown_scope_typo_is_not_silently_discarded(self) -> None:
        with pytest.raises(pc.AuditError, match='scope must be the literal \\"external\\"'):
            pc.parse_audit(_audit(_claim(scope="externl")), PLAN)

    @pytest.mark.parametrize("kind", ["fact", "design_principle", "behavior"])
    def test_all_external_claim_kinds_are_eligible(self, kind: str) -> None:
        claim = pc.parse_audit(_audit(_claim(kind=kind)), PLAN).claims[0]
        assert claim["kind"] == kind
        assert claim["scope"] == "external"

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
        with pytest.raises(pc.AuditError, match="kind must be one of"):
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

    def test_disposition_ignores_harmless_model_metadata(self) -> None:
        audit = pc.parse_audit(_audit(
            _claim(),
            dispositions=[{
                "claim_id": "C-old", "disposition": "removed",
                "reason": "The old exact wording is absent.",
                "anchor": "Old wording from the prior plan.",
            }],
        ), PLAN)
        assert audit.dispositions == ({
            "claim_id": "C-old", "disposition": "removed",
            "reason": "The old exact wording is absent.",
        },)

    @pytest.mark.parametrize("extra", [
        {"prior_claim_id": "C-other"},
        {"rationale": "A second reason."},
    ])
    def test_disposition_still_rejects_ambiguous_wire_aliases(
        self, extra: dict[str, str],
    ) -> None:
        item = {
            "claim_id": "C-old", "disposition": "removed",
            "reason": "The old exact wording is absent.",
            **extra,
        }
        with pytest.raises(pc.AuditError, match="must contain one claim ID"):
            pc.parse_audit(_audit(_claim(), dispositions=[item]), PLAN)

    @pytest.mark.parametrize("field", ["prior_dispositions", "prior_assessments"])
    def test_governing_coverage_arrays_are_required(self, field: str) -> None:
        payload = json.loads(_audit(_claim()).split("\n", 1)[1])
        del payload["coverage"][field]
        raw = pc.AUDIT_MARKER + "\n" + json.dumps(payload)
        with pytest.raises(pc.AuditError, match=rf"coverage\.{field} is required"):
            pc.parse_audit(raw, PLAN)

    @pytest.mark.parametrize("section, field", [
        ("prior_dispositions", "reason"),
        ("prior_assessments", "rationale"),
    ])
    def test_null_governing_scalar_is_a_recoverable_audit_error(
        self, section: str, field: str,
    ) -> None:
        payload = json.loads(_audit(_claim()).split("\n", 1)[1])
        payload["coverage"][section] = [{
            "claim_id": "C-old",
            **({"disposition": "removed"} if section == "prior_dispositions"
               else {"verdict": "supported"}),
            field: None,
        }]
        raw = pc.AUDIT_MARKER + "\n" + json.dumps(payload)
        with pytest.raises(pc.AuditError, match="must be a non-empty string"):
            pc.parse_audit(raw, PLAN)


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

    def test_final_retry_localizes_a_missing_retained_claim(self) -> None:
        sqlite = "SQLite 3.45.0 was released on 15 January 2024."
        plan = PLAN + sqlite + "\n"
        refuting = [_source(relation="refutes_claim")]
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(
                _claim(verdict="refuted", evidence=refuting),
                _claim(
                    anchor=sqlite, proposition=sqlite, verdict="refuted",
                    evidence=refuting,
                ),
            ), plan),
            lineage_id="x-plan", round_no=1, plan_text=plan,
        )
        python_id = next(
            claim_id for claim_id, claim in first["claims"].items()
            if claim["proposition"].startswith("Python")
        )
        sqlite_id = next(claim_id for claim_id in first["claims"] if claim_id != python_id)
        retry = pc.parse_audit(_audit(assessments=[{
            "claim_id": python_id,
            "verdict": "refuted",
            "rationale": "The retained official passage still contradicts the claim.",
        }]), plan)

        second = pc.reconcile(
            first, retry, lineage_id="x-plan", round_no=2, plan_text=plan,
            allow_missing=True,
        )

        assert second["claims"][python_id]["verdict"] == "refuted"
        assert second["claims"][sqlite_id]["verdict"] == "unverified"
        assert "omitted this prior claim" in second["claims"][sqlite_id]["rationale"]
        assert second["debt"] is None

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

    @pytest.mark.parametrize("changed", [
        '# Rollout\n\nThe statement "Python 3.11 was released in October 2022." is rejected.\n',
        '# Rollout\n\nPython 3.11 was not released in October 2022.\n',
        '# Quotation\n\n> Python 3.11 was released in October 2022.\n',
        '# Example\n\n```text\nPython 3.11 was released in October 2022.\n```\n',
        '# Historical notes\n\nPython 3.11 was released in October 2022.\n',
    ])
    def test_changed_assertion_context_is_not_frozen(self, changed: str) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        assert not pc.frozen_supported_ids(first, changed)

    def test_adjacent_retraction_in_the_same_block_forces_reverification(self) -> None:
        original = (
            PLAN.rstrip() + " The official release date governs this rollout.\n"
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), original),
            lineage_id="x-plan", round_no=1, plan_text=original,
        )
        retracted = (
            PLAN.rstrip() + " This statement is false and must not be relied on.\n"
        )
        assert not pc.frozen_supported_ids(first, retracted)

    def test_setext_heading_relocation_forces_reverification(self) -> None:
        original = (
            "Rollout\n=======\n\nPython 3.11 was released in October 2022.\n"
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), original),
            lineage_id="x-plan", round_no=1, plan_text=original,
        )
        relocated = (
            "Historical notes\n================\n\n"
            "Python 3.11 was released in October 2022.\n"
        )
        assert not pc.frozen_supported_ids(first, relocated)

    def test_indented_code_occurrence_cannot_freeze_asserted_prose(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        code_only = (
            "# Rollout\n\n    Python 3.11 was released in October 2022.\n"
        )
        assert not pc.frozen_supported_ids(first, code_only)

    @pytest.mark.parametrize("relocated", [
        '# A\n\n## B\n\nPython 3.11 was released in October 2022.\n',
        '# A / B\n\nPython 3.11 was released in October 2022.\n',
    ])
    def test_heading_structure_collisions_force_reverification(self, relocated: str) -> None:
        original = (
            '# A\n\n### B\n\nPython 3.11 was released in October 2022.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), original),
            lineage_id="x-plan", round_no=1, plan_text=original,
        )
        assert not pc.frozen_supported_ids(first, relocated)

    def test_list_parent_cannot_be_lost_from_assertion_identity(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        rejected_list = (
            '# Rollout\n\n- The following claim is rejected:\n'
            '  Python 3.11 was released in October 2022.\n'
        )
        assert not pc.frozen_supported_ids(first, rejected_list)

    def test_nested_assertion_cannot_move_between_list_parents(self) -> None:
        original = (
            '# Rollout\n\n- Accepted premises:\n'
            '  - Python 3.11 was released in October 2022.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), original),
            lineage_id="x-plan", round_no=1, plan_text=original,
        )
        rejected = (
            '# Rollout\n\n- Rejected premises:\n'
            '  - Python 3.11 was released in October 2022.\n'
        )
        assert not pc.frozen_supported_ids(first, rejected)

    def test_unchanged_list_assertion_can_reuse_its_packet(self) -> None:
        listed = (
            '# Rollout\n\n- Python 3.11 was released in October 2022.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), listed),
            lineage_id="x-plan", round_no=1, plan_text=listed,
        )
        assert pc.frozen_supported_ids(first, listed) == set(first["claims"])

    def test_reflowed_list_assertion_can_reuse_its_packet(self) -> None:
        listed = (
            '# Rollout\n\n- Python 3.11 was released in\n'
            '  October 2022. A second sentence stays in the item.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), listed),
            lineage_id="x-plan", round_no=1, plan_text=listed,
        )
        reflowed = (
            '# Rollout\n\n- Python 3.11 was released in October 2022.\n'
            '  A second sentence stays in the item.\n'
        )
        assert pc.frozen_supported_ids(first, reflowed) == set(first["claims"])

    def test_duplicate_assertion_and_quotation_cannot_freeze_ambiguously(self) -> None:
        mixed = (
            PLAN + '\n## Quotation\n\n'
            '> Python 3.11 was released in October 2022.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), mixed),
            lineage_id="x-plan", round_no=1, plan_text=mixed,
        )
        quotation_only = (
            '# Rollout\n\nThe assertion was removed.\n\n## Quotation\n\n'
            '> Python 3.11 was released in October 2022.\n'
        )
        assert not pc.frozen_supported_ids(first, quotation_only)

    def test_nonfreezable_claim_rejects_compact_support(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        quoted = (
            '# Rollout\n\nThe statement "Python 3.11 was released in October 2022." '
            'is rejected.\n'
        )
        audit = pc.parse_audit(_audit(assessments=[{
            "claim_id": claim_id, "verdict": "supported",
            "rationale": "The old packet is unchanged.",
        }]), quoted)
        with pytest.raises(pc.AuditError, match="require full current evidence packets"):
            pc.reconcile(
                first, audit, lineage_id="x-plan", round_no=2, plan_text=quoted,
            )

    def test_markdown_wrapping_keeps_the_same_assertion_binding(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        wrapped = "# Rollout\n\nPython 3.11 was released\nin October 2022.\n"
        assert pc.frozen_supported_ids(first, wrapped) == set(first["claims"])

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
        first_plan = PLAN + "\n" + sqlite_old + "\n"
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
        second_plan = PLAN + "\n" + sqlite_new + "\n"
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

    def test_compact_assessment_rechecks_retained_refutation_without_repeating_it(self) -> None:
        refuting = [_source(relation="refutes_claim")]
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(
                verdict="refuted", evidence=refuting,
            )), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        second = pc.reconcile(
            first, pc.parse_audit(_audit(assessments=[{
                "claim_id": claim_id,
                "verdict": "refuted",
                "rationale": "The retained official passage still contradicts the exact claim.",
            }]), PLAN),
            lineage_id="x-plan", round_no=2, plan_text=PLAN,
        )
        assert list(second["claims"]) == [claim_id]
        assert second["claims"][claim_id]["verdict"] == "refuted"
        assert second["claims"][claim_id]["verified_round"] == 2
        assert second["claims"][claim_id]["evidence"] == first["claims"][claim_id]["evidence"]
        assert pc.is_blocked(second)

    def test_legacy_repository_claims_are_mechanically_retired(self) -> None:
        legacy = pc.empty_state()
        legacy["claims"] = {
            "C-repo": {
                "kind": "fact", "scope": "repository",
                "anchor": "The setting is enabled.",
                "proposition": "The repository setting is enabled.",
                "verdict": "supported", "evidence": [],
            },
            "C-external": {
                **_claim(), "claim_id": "C-external",
            },
        }

        normalized = pc.normalize_state(legacy)

        assert set(normalized["claims"]) == {"C-external"}
        assert normalized["retired"][-1]["claim_id"] == "C-repo"
        assert normalized["retired"][-1]["disposition"] == "out_of_scope"

    def test_parent_schema_with_unresolved_claims_migrates_to_blocking_debt(self) -> None:
        legacy = {
            "next_seq": 4,
            "claims": [{
                "claim_id": "a" * 32,
                "claim": "An external premise remains unresolved.",
                "status": "UNVERIFIED",
            }],
            "debt": None,
            "evidence_records": [],
            "plan_sha256": "b" * 64,
            "authorization_policy": None,
        }
        normalized = pc.normalize_state(legacy)
        assert pc.is_blocked(normalized)
        assert normalized["claims"] == {}
        assert "1 active predecessor" in normalized["debt"]["reason"]
        assert "a" * 32 in normalized["debt"]["reason"]
        assert not pc.has_prior_snapshot(normalized)

    def test_targeted_prompt_requires_full_packet_for_unverified_claim(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(verdict="unverified", evidence=[])), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))

        prompt = pc.targeted_audit_instructions(PLAN, first, "trusted local tool", set())

        assert "RETAINED CLAIMS REQUIRING FULL EVIDENCE PACKETS" in prompt
        assert claim_id in prompt.split(
            "RETAINED REFUTED CLAIMS ELIGIBLE FOR COMPACT ASSESSMENT", 1
        )[0]
        assert '"prior_assessments":[]' in prompt
        assert "Mechanically OMIT repository state" in prompt

    def test_prompts_include_external_principles_and_behaviors_but_exclude_repo_claims(
        self,
    ) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )

        exhaustive = pc.audit_instructions(PLAN, {}, "trusted local tool")
        targeted = pc.targeted_audit_instructions(PLAN, first, "trusted local tool", set())
        retry = pc.retry_instructions(
            pc.AuditError("bad packet"), PLAN, first,
        )

        for prompt in (exhaustive, targeted, retry):
            assert "design_principle" in prompt
            assert "behavior" in prompt
            assert "repository" in prompt.lower()
            assert "structural" in prompt and "review" in prompt
        assert "Every claim has scope `external`" in exhaustive
        assert '"scope":"external"' in targeted
        assert 'Allowed scope: "external"' in targeted

    def test_prompts_preserve_report_event_and_chronology(self) -> None:
        exhaustive = pc.audit_instructions(PLAN, {}, "trusted local tool")
        targeted = pc.targeted_audit_instructions(PLAN, {}, "trusted local tool", set())

        for prompt in (exhaustive, targeted):
            assert "audit/report" in prompt
            assert "underlying" in prompt
            assert "chronology" in prompt

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
        with pytest.raises(pc.AuditError, match="require full current evidence packets"):
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
            first, pc.parse_audit(_audit(unrelated), expanded_plan),
            lineage_id="x-plan", round_no=2, plan_text=expanded_plan,
            frozen_ids={old_id},
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
            first, pc.parse_audit(_audit(opposite), both_plan),
            lineage_id="x-plan", round_no=2, plan_text=both_plan,
            frozen_ids={old_id},
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
        assert "function-to-function bridges" in context
        assert "Do not demand claim packets for repository state" in context
        assert "omitted load-bearing factual assertion" not in context

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
        assert "Evidence-entailed replacement" in packet
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
    def test_invalid_disposition_scalar_gets_one_correction_and_recovers(
        self, tmp_path: Path,
    ) -> None:
        invalid = _audit(_claim(), dispositions=[{
            "claim_id": "C-old", "disposition": "removed", "reason": None,
        }])
        engine = ScriptedEngine(invalid, _audit(_claim()), STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "lineage": "scalar-retry-plan", "round": 1,
                "stakes": "trusted local tool; convergence correctness matters",
            },
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        assert len(engine.prompts) == 3
        assert "disposition.reason must be a non-empty string" in engine.prompts[1]
        assert "CONVERGENCE: NOT-BLOCKED" in out

    def test_missing_governing_array_twice_becomes_blocking_debt(
        self, tmp_path: Path,
    ) -> None:
        payload = json.loads(_audit(_claim()).split("\n", 1)[1])
        del payload["coverage"]["prior_dispositions"]
        invalid = pc.AUDIT_MARKER + "\n" + json.dumps(payload)
        engine = ScriptedEngine(invalid, invalid, STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "lineage": "missing-array-plan", "round": 1,
                "stakes": "trusted local tool; convergence correctness matters",
            },
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        assert len(engine.prompts) == 3
        assert "coverage.prior_dispositions is required" in engine.prompts[1]
        assert "CLAIM-AUDIT-DEBT: round 1: initial audit invalid" in out
        assert "CONVERGENCE: BLOCKED" in out

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
        assert "CONVERGENCE: BLOCKED — external claim closure" in out
        assert "BUILT-IN web search" in engine.prompts[0]
        assert "AUTHORITATIVE EXTERNAL CLAIM REGISTER" in engine.prompts[1]
        assert "Never demand claim packets" in engine.prompts[1]
        assert "missing atomic bridge" in engine.prompts[1]

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


class _RoleScript:
    name = "codex"
    default_model = "test"

    def __init__(self, outputs: dict[str, list[str]]) -> None:
        self.outputs = outputs
        self.role = "default"

    def for_role(self, role: str):
        child = _RoleScript(self.outputs)
        child.role = role
        return child

    def _next(self) -> Review:
        return Review(
            text=self.outputs[self.role].pop(0), session_ref="session", raw=self.role,
        )

    def run(self, *args, **kwargs):
        return self._next()

    def resume(self, *args, **kwargs):
        return self._next()


def test_captured_claim_retry_cannot_bypass_capture_validation(
    tmp_path: Path, monkeypatch,
) -> None:
    source = _source()
    candidate = external_sources.CandidateSource(
        source["url"], source["title"], source["publisher"], source["source_kind"],
        source["authority_basis"], source["relation"],
    )
    capture = external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "body", "text",
        source["quote"],
    )
    monkeypatch.setattr(
        handlers.external_sources, "capture_all", lambda candidates: [capture],
    )
    valid = _audit(_claim())
    changed = _audit(_claim(evidence=[_source(url="https://example.com/changed")]))
    attestation = (
        '=== EVIDENCE ATTESTATION JSON ===\n'
        '{"attestations":[{"claim_index":0,"evidence_index":0,'
        '"publisher_authority":true,"authority_reason":"official release owner",'
        '"passage_entailment":true,"entailment_reason":"states the release date"}]}'
    )
    engine = _RoleScript({
        "evidence-discovery": [valid],
        "evidence-binding": [valid, changed],
        "evidence-text": [attestation],
    })
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        first = adapter.run("audit", tmp_path, "m", "high", True)
        assert not first.error
        retry = adapter.resume("session", "correct", tmp_path, "m", "high", True)
        assert retry.error
        assert "binding added or changed" in retry.text
    finally:
        adapter.close()
