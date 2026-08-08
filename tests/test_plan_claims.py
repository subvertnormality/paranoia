from __future__ import annotations

import json
from pathlib import Path

import pytest

from paranoia_local import handlers, plan_claims as pc
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
    *claims: dict[str, object], dispositions: list[dict[str, str]] | None = None
) -> str:
    payload = {
        "claims": list(claims),
        "coverage": {
            "sections_scanned": 1, "omitted_nonfacts": 1,
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

    def test_reddit_is_never_upgraded_to_primary_by_model_output(self) -> None:
        reddit = _source(url="https://www.reddit.com/r/python/comments/x", kind="primary")
        with pytest.raises(pc.AuditError, match="lacks claim-entailing authoritative"):
            pc.parse_audit(_audit(_claim(evidence=[reddit])), PLAN)

    def test_refutation_alone_cannot_authorize_replacement_wording(self) -> None:
        refuting = _source(relation="refutes_claim")
        with pytest.raises(pc.AuditError, match="replacement lacks authoritative"):
            pc.parse_audit(_audit(_claim(
                verdict="refuted", evidence=[refuting],
                replacement="Python 3.11 was released on 24 October 2022.",
            )), PLAN)

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


class TestRetainedEvidence:
    def test_corrected_wording_reuses_identity_but_not_the_old_verdict(self) -> None:
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
            first, pc.parse_audit(_audit(corrected), corrected_plan),
            lineage_id="x-plan", round_no=2, plan_text=corrected_plan,
        )
        assert next(iter(second["claims"])) == claim_id
        assert pc.is_blocked(second)
        assert second["claims"][claim_id]["previous_proposition"].endswith("2022.")
        prompt = pc.audit_instructions(corrected_plan, first, "trusted local tool")
        assert claim_id in prompt and _source()["url"] in prompt

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

    def test_model_omission_cannot_clear_a_still_present_prior_claim(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        second = pc.reconcile(
            first, pc.parse_audit(_audit(), PLAN),
            lineage_id="x-plan", round_no=2, plan_text=PLAN,
        )
        assert list(second["claims"]) == [claim_id]
        assert second["claims"][claim_id]["verdict"] == "unverified"
        assert pc.is_blocked(second)

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

    def test_one_shot_structural_failure_cannot_emit_not_blocked(self, tmp_path: Path) -> None:
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
        assert "CONVERGENCE: BLOCKED" in out
        assert "CONVERGENCE: NOT-BLOCKED" not in out
