from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from paranoia_local import class_closure as cc
from paranoia_local import claim_verification as cv, handlers, plan_claims as pc
from paranoia_local.engines import Review


class ClaimEngine:
    name = "fake"
    default_model = "fake-model"

    def __init__(self, *, verify: bool = True) -> None:
        self.verify = verify
        self.tool_less_prompts: list[str] = []
        self.ordinary_prompts: list[str] = []

    def run_toolless(self, prompt: str, model: str, effort: str, **kwargs) -> Review:
        self.tool_less_prompts.append(prompt)
        if "neutral claim extractor" in prompt:
            if '"claim":"app.py defines greet"' in prompt:
                return _review("=== RESEARCH REGISTER ===\nEVENTS-JSON: []")
            event = {
                "op": "ADD", "temp_id": "premise", "claim": "app.py defines greet",
                "kind": "fact", "assertion_mode": "asserted",
                "plan_anchor": {"first_span": "p000001", "last_span": "p000001"},
            }
            return _review("=== RESEARCH REGISTER ===\nEVENTS-JSON: " + _json([event]))
        if "neutral evidence planner" in prompt:
            claim_id = re.search(r'"claim_id":"([0-9a-f]{10})"', prompt).group(1)
            request = {"op": "READ_BLOB", "claim_id": claim_id, "path": "app.py", "offset": 0,
                       "max_bytes": 1048576}
            return _review("=== EVIDENCE REQUESTS ===\nREQUESTS-JSON: " + _json([request]))
        if "preparing bounded repository context" in prompt:
            return _review("=== EVIDENCE REQUESTS ===\nREQUESTS-JSON: []")
        if "neutral evidence verifier" in prompt:
            claim_id = re.search(r'"claim_id":"([0-9a-f]{10})"', prompt).group(1)
            evidence = re.search(r'"evidence_id":"(e[0-9a-f]{12})"', prompt).group(1)
            events = []
            if '"kind_classification":"proposed"' in prompt:
                events.append(
                    {"op": "CONFIRM_KIND", "claim_id": claim_id, "kind": "fact",
                     "reason": "an implementation assertion"}
                )
            if self.verify:
                events.append({"op": "VERIFY", "claim_id": claim_id,
                               "evidence_ids": [evidence], "reason": "exact pinned blob"})
            return _review("=== VERIFICATION REGISTER ===\nEVENTS-JSON: " + _json(events))
        assert "adversarial reviewer of plans" in prompt
        return _review(
            "## What works\n\nGrounded.\n\n## What doesn't work\n\nNothing notable.\n\n"
            "## Risks\n\nNothing notable.\n\n## Gaps\n\nNothing notable.\n\n"
            "## Improvements\n\nNothing notable.\n\n=== PLAN REGISTER ===\n"
            "EVENTS-JSON: []\n=== CLASS REGISTER ===\nNONE"
        )

    def run(self, prompt, cwd, model, effort, web_search, **kwargs) -> Review:
        self.ordinary_prompts.append(prompt)
        return _review(
            "## What works\n\nFine.\n\n## What doesn't work\n\nNothing.\n\n"
            "## Risks\n\nNone.\n\n## Gaps\n\nNone.\n\n## Improvements\n\nNone."
        )


def _review(text: str) -> Review:
    return Review(text=text, session_ref="s", raw=text)


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def test_verified_claim_and_empty_class_register_produce_one_not_blocked_verdict(
    repo: Path, tmp_path: Path
) -> None:
    engine = ClaimEngine()
    out = handlers.critique_plan(
        {"repo_path": str(repo), "plan_text": "Use the existing greet function.\n",
         "lineage": "verified-plan", "round": 1},
        engine=engine, log_dir=tmp_path / "logs", now=lambda: "T1",
    )
    assert out.count("CONVERGENCE:") == 1
    assert "CLAIM-CLOSURE: NOT-BLOCKED" in out
    assert "CLASS-CLOSURE: 0 open" in out
    assert "CONVERGENCE: NOT-BLOCKED" in out
    lineage = cc.load_lineage(cc.default_state_root(), "verified-plan", stamp="T",
                              mode=cc.PLAN_MODE)
    state = pc.state_from_json("verified-plan", lineage.claim_state)
    assert next(iter(state.claims.values())).status == pc.VERIFIED
    raw_state = json.loads(
        (cc.lineage_dir(cc.default_state_root()) / "verified-plan.json").read_text()
    )
    assert raw_state["schema_version"] == 2 and "claim_state" in raw_state


def test_unverified_registered_fact_blocks_even_when_classes_are_empty(
    repo: Path, tmp_path: Path
) -> None:
    out = handlers.critique_plan(
        {"repo_path": str(repo), "plan_text": "Use greet.\n",
         "lineage": "unverified-plan", "round": 1},
        engine=ClaimEngine(verify=False), log_dir=tmp_path / "logs", now=lambda: "T1",
    )
    assert "CLAIM-CLOSURE: BLOCKED" in out
    assert "CONVERGENCE: BLOCKED" in out


def test_class_closure_false_is_the_only_one_call_no_state_escape(
    repo: Path, tmp_path: Path
) -> None:
    engine = ClaimEngine()
    out = handlers.critique_plan(
        {"repo_path": str(repo), "plan_text": "Sketch.\n", "class_closure": False},
        engine=engine, log_dir=tmp_path / "logs", now=lambda: "T1",
    )
    assert len(engine.ordinary_prompts) == 1 and not engine.tool_less_prompts
    assert "CONVERGENCE:" not in out


def test_unchanged_valid_cache_round_spends_zero_research_or_fetch_calls(
    repo: Path, tmp_path: Path
) -> None:
    args = {"repo_path": str(repo), "plan_text": "Use the existing greet function.\n",
            "lineage": "cache-plan", "round": 1}
    handlers.critique_plan(
        args, engine=ClaimEngine(), log_dir=tmp_path / "logs", now=lambda: "T1",
    )
    second = ClaimEngine()
    args["round"] = 2
    out = handlers.critique_plan(
        args, engine=second, log_dir=tmp_path / "logs", now=lambda: "T2",
    )
    assert len(second.tool_less_prompts) == 1
    assert "adversarial reviewer of plans" in second.tool_less_prompts[0]
    assert "CLAIM-REGISTER: cache-hit (zero research calls, zero fetches)" in out


def test_tightening_independent_policy_invalidates_cache_and_reauthorizes(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = {
        "repo_path": str(repo),
        "plan_text": "Use the existing greet function.\n",
        "lineage": "policy-plan",
        "round": 1,
    }
    handlers.critique_plan(
        args, engine=ClaimEngine(), log_dir=tmp_path / "logs", now=lambda: "T1",
    )

    def checks(event, **_kwargs):
        digest = pc.event_digest(event)
        ids = tuple(event.data.get("evidence_ids", []))
        return [
            pc.VendorCheck("fake", "fake-model", digest, ids, True, "T2"),
            pc.VendorCheck("other", "other-model", digest, ids, True, "T2"),
        ]

    monkeypatch.setattr(handlers, "_independent_checks", checks)
    second = ClaimEngine()
    args.update({"round": 2, "independent_check": "require"})
    out = handlers.critique_plan(
        args, engine=second, log_dir=tmp_path / "logs", now=lambda: "T2",
    )
    assert len(second.tool_less_prompts) > 1
    assert "cache-hit" not in out
    assert "CONVERGENCE: NOT-BLOCKED" in out
    lineage = cc.load_lineage(
        cc.default_state_root(), "policy-plan", stamp="T3", mode=cc.PLAN_MODE
    )
    claim = next(iter(pc.state_from_json("policy-plan", lineage.claim_state).claims.values()))
    assert claim.truth_authorization["status"] == "complete"


def test_stakes_risk_is_explicit_and_never_inferred_from_negated_words() -> None:
    assert handlers._is_high_stakes("not low risk; production financial system") is True
    assert handlers._is_high_stakes("not low risk; production financial system", "low") is False
    assert handlers._is_high_stakes(None, "high") is True


def test_structural_add_receives_real_span_vocabulary_and_remains_blocking(
    repo: Path, tmp_path: Path
) -> None:
    class StructuralAddEngine(ClaimEngine):
        def run_toolless(self, prompt: str, model: str, effort: str, **kwargs) -> Review:
            if "adversarial reviewer of plans" not in prompt:
                return super().run_toolless(prompt, model, effort, **kwargs)
            self.tool_less_prompts.append(prompt)
            assert '"span_id":"p000001"' in prompt
            event = {
                "op": "ADD", "temp_id": "structural-1", "claim": "Deployment exists",
                "kind": "fact", "assertion_mode": "assumption",
                "plan_anchor": {"first_span": "p000001", "last_span": "p000001"},
            }
            return _review(
                "## What works\n\nGrounded.\n\n## What doesn't work\n\nNothing notable.\n\n"
                "## Risks\n\nNothing notable.\n\n## Gaps\n\nNothing notable.\n\n"
                "## Improvements\n\nNothing notable.\n\n=== PLAN REGISTER ===\n"
                "EVENTS-JSON: " + _json([event]) + "\n=== CLASS REGISTER ===\nNONE"
            )

    out = handlers.critique_plan(
        {
            "repo_path": str(repo), "plan_text": "Deploy it.\n",
            "lineage": "structural-add-plan", "round": 1,
        },
        engine=StructuralAddEngine(verify=False),
        log_dir=tmp_path / "logs", now=lambda: "T1",
    )
    assert "Deployment exists" in out and "CONVERGENCE: BLOCKED" in out


def test_malformed_nested_claim_state_is_quarantined_without_stranding_latch(
    repo: Path, tmp_path: Path
) -> None:
    directory = cc.lineage_dir(cc.default_state_root())
    directory.mkdir(parents=True)
    state_path = directory / "malformed-plan.json"
    state_path.write_text(json.dumps({
        "mode": cc.PLAN_MODE,
        "rounds": 1,
        "next_seq": 1,
        "classes": [],
        "exemptions": [],
        "debt": None,
        "schema_version": 2,
        "claim_state": {"next_seq": 1, "claims": [], "evidence_records": ["bad"]},
    }))
    out = handlers.critique_plan(
        {
            "repo_path": str(repo), "plan_text": "Plan.\n",
            "lineage": "malformed-plan", "round": 2,
        },
        engine=ClaimEngine(), log_dir=tmp_path / "logs", now=lambda: "T2",
    )
    assert "STATE-UNAVAILABLE" in out and "CONVERGENCE: BLOCKED" in out
    assert not (directory / "malformed-plan.pending").exists()
    assert list(directory.glob("malformed-plan.corrupt-*.json"))


def test_independent_auditor_receives_exact_proposition_and_claim_state(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    spans = pc.segment_plan(b"Use it.\n")
    state = pc.ClaimState("auditor")
    add = {
        "op": "ADD", "temp_id": "one", "claim": "The exact proposition",
        "kind": "fact", "assertion_mode": "asserted",
        "plan_anchor": {"first_span": "p000001", "last_span": "p000001"},
    }
    events = pc.parse_role_register(
        "=== RESEARCH REGISTER ===\nEVENTS-JSON: " + _json([add]), pc.RESEARCH_ROLE
    )
    claim_id = pc.apply_events(
        state, events, role=pc.RESEARCH_ROLE, spans=spans
    )["one"]
    event = pc.Event("VERIFY", {
        "op": "VERIFY", "claim_id": claim_id,
        "evidence_ids": ["e1"], "reason": "supported",
    })
    digest = "a" * 64
    record = cv.EvidenceRecord(
        "e1", claim_id, "external", "https://example.com/", digest, digest, 1,
        0, 1, digest, "x", {},
    )

    class Auditor:
        name = "other"
        default_model = "other-model"

        def __init__(self) -> None:
            self.prompt = ""

        def run_toolless(self, prompt, model, effort, **kwargs):
            self.prompt = prompt
            return _review("CHECK: ACCEPT")

    auditor = Auditor()
    monkeypatch.setattr(handlers.eng, "get_engine", lambda _name: auditor)
    checks = handlers._independent_checks(
        event, required=True, primary_engine=ClaimEngine(), primary_model="fake-model",
        evidence_records=[record], claim_state=state, effort="high",
        plan_context=pc.render_spans(spans), on_progress=None,
    )
    assert len(checks) == 2
    assert '"proposition":"The exact proposition"' in auditor.prompt
    assert f'"claim_id":"{claim_id}"' in auditor.prompt
    assert '"status":"unchecked"' in auditor.prompt


@pytest.mark.parametrize("stage", ["research", "evidence", "verifier", "structural"])
def test_twice_malformed_register_creates_durable_debt_and_disables_cache(
    repo: Path, tmp_path: Path, stage: str
) -> None:
    lineage_id = f"malformed-{stage}-register-plan"
    args = {
        "repo_path": str(repo), "plan_text": "Use the existing greet function.\n",
        "lineage": lineage_id, "round": 1,
    }
    handlers.critique_plan(
        args, engine=ClaimEngine(), log_dir=tmp_path / "logs", now=lambda: "T1",
    )

    class MalformedEngine(ClaimEngine):
        def run_toolless(self, prompt: str, model: str, effort: str, **kwargs) -> Review:
            self.tool_less_prompts.append(prompt)
            selected = (
                (stage == "research" and "neutral claim extractor" in prompt)
                or (stage == "evidence" and "neutral evidence planner" in prompt)
                or (stage == "verifier" and "neutral evidence verifier" in prompt)
                or (stage == "structural" and "adversarial reviewer of plans" in prompt)
            )
            if selected:
                return _review("not a register")
            return super().run_toolless(prompt, model, effort, **kwargs)

    args.update({"round": 2, "refresh_claims": True})
    out = handlers.critique_plan(
        args, engine=MalformedEngine(), log_dir=tmp_path / "logs", now=lambda: "T2",
    )
    assert "Claim register failed closed" in out and "CONVERGENCE: BLOCKED" in out
    lineage = cc.load_lineage(
        cc.default_state_root(), lineage_id, stamp="T3", mode=cc.PLAN_MODE
    )
    state = pc.state_from_json(lineage_id, lineage.claim_state)
    assert state.debt and lineage.debt
    assert not (cc.lineage_dir(cc.default_state_root()) / f"{lineage_id}.pending").exists()
    args.update({"round": 3, "refresh_claims": False})
    repaired = handlers.critique_plan(
        args, engine=ClaimEngine(), log_dir=tmp_path / "logs", now=lambda: "T3",
    )
    assert "cache-hit" not in repaired and "CONVERGENCE: NOT-BLOCKED" in repaired
