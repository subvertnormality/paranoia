from __future__ import annotations

import json
import re
from pathlib import Path

from paranoia_local import class_closure as cc
from paranoia_local import handlers, plan_claims as pc
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
            event = {
                "op": "ADD", "temp_id": "premise", "claim": "app.py defines greet",
                "kind": "fact", "assertion_mode": "asserted",
                "plan_anchor": {"first_span": "p000001", "last_span": "p000001"},
            }
            return _review("=== RESEARCH REGISTER ===\nEVENTS-JSON: " + _json([event]))
        if "neutral evidence planner" in prompt:
            claim_id = re.search(r"\[([0-9a-f]{10})\] app.py", prompt).group(1)
            request = {"op": "READ_BLOB", "claim_id": claim_id, "path": "app.py",
                       "max_bytes": 1048576}
            return _review("=== EVIDENCE REQUESTS ===\nREQUESTS-JSON: " + _json([request]))
        if "preparing bounded repository context" in prompt:
            return _review("=== EVIDENCE REQUESTS ===\nREQUESTS-JSON: []")
        if "neutral evidence verifier" in prompt:
            claim_id = re.search(r"\[([0-9a-f]{10})\] app.py", prompt).group(1)
            evidence = re.search(r"\[(e[0-9a-f]{12})\]", prompt).group(1)
            events = [
                {"op": "CONFIRM_KIND", "claim_id": claim_id, "kind": "fact",
                 "reason": "an implementation assertion"},
            ]
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
