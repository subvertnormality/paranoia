"""Public-handler regressions for canonical census input and reviewed-plan rebut."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from paranoia_local import class_closure as cc, engines, handlers, prompts, review_census as rc, staged_protocol as sp
from paranoia_local.engines import Review
from tests.test_handlers import FakeEngine
from tests.test_review_census import lane, payload, wire, _unit_debt


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("reply", ["initial", "retry", "invalid"])
def test_consolidation_canonical_evidence_contract(repo_with_branch, tmp_path, monkeypatch, mode, reply):
    repo = repo_with_branch
    lineage_id = "canonical-consolidation"
    old = _unit_debt("D90", status="closed")
    old["evidence"] = ["repository/README.md:1"]
    state = rc.normalize_state(None, stakes="trusted local tool", snapshot="prior")
    state.update(debt=[deepcopy(old)], last_round=1)
    cc.save_lineage(cc.default_state_root(), cc.Lineage(lineage_id, mode=mode, review_state=state))
    anchors = ["repository/README.md:1", "repository/app.py:1"]
    source_lanes = sp.LANES[mode][:2]
    source_ids = [f"{name}:F1" for name in source_lanes]
    consolidation_prompts = []

    def decision(valid):
        return wire({
            "role":"census", "governing_findings":[{
                "id":"G1", "severity":"BLOCKER", "summary":"Missing a required guard.",
                "evidence":anchors[:1] if valid else ["repository/extra.py:1"],
                "remedy":"Add the guard.", "source_ids":source_ids,
                "classification":{"kind":"one_off", "reason":"Single fixture guard."},
            }], "debt_outcomes":[], "class_actions":{},
        })

    def run(self, prompt, *args, **kwargs):
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            name = next(row.split()[-1] for row in prompt.splitlines() if row.startswith("ROLE: census lane"))
            findings = []
            if name in source_lanes:
                findings = [{"id":"F1", "severity":"MAJOR" if name == source_lanes[0] else "BLOCKER",
                             "summary":"Missing a required guard.", "remedy":"Add the guard.",
                             "evidence":[anchors[source_lanes.index(name)]]}]
            value = payload(lane(name, findings=findings))
            for row in value["coverage"]:
                row["evidence"] = ["repository/README.md:1"]
            text = wire(value)
        else:
            consolidation_prompts.append(prompt)
            text = decision(reply == "initial")
        return Review(text=text, raw=text, session_ref="canonical-session")

    def resume(self, session_ref, prompt, *args, **kwargs):
        assert session_ref == "canonical-session"
        consolidation_prompts.append(prompt)
        text = decision(reply == "retry")
        return Review(text=text, raw=text, session_ref=session_ref)

    monkeypatch.setattr(engines.CodexEngine, "run", run)
    monkeypatch.setattr(engines.CodexEngine, "resume", resume)
    arguments = {"repo_path":str(repo), "lineage":lineage_id, "round":2, "stakes":"trusted local tool"}
    if mode == cc.PLAN_MODE:
        arguments.update(plan_text="# Plan\nAdd the guard.", claim_verification=False)
        handler = handlers.critique_plan
    else:
        arguments.update(base_ref="main", head_ref="feature")
        handler = handlers.critique_branch
    result = handler(arguments, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert len(consolidation_prompts) == (1 if reply == "initial" else 2)
    for prompt in consolidation_prompts:
        assert "Canonical manifest evidence intentionally contains bare anchor strings" in prompt
        assert "derive each output rationale from the mapped source summary, remedy and evidence" in prompt
        assert "Missing source rationale objects are not a defect in the reviewed artifact" in prompt
    durable = cc.load_lineage(cc.default_state_root(), lineage_id, stamp="after", mode=mode)
    assert durable.review_state["debt"][0] == old
    if reply == "invalid":
        assert durable.review_state["debt"] == [old]
        assert "CONVERGENCE: BLOCKED" in result
        assert durable.review_state["validation_debt"]["role"] == "consolidation-validation-retry"
    else:
        debt = durable.review_state["debt"][1]
        assert debt["severity"] == "BLOCKER"
        assert debt["evidence"] == anchors
        assert debt["source_ids"] == source_ids
        assert debt["summary"] == "Missing a required guard."
        assert "validation_debt" not in durable.review_state


def test_historical_metadata_debt_requires_reviewer_correction(repo, tmp_path, monkeypatch):
    old = _unit_debt("D1")
    old["summary"] = "The supplied manifests lack citation-specific rationales."
    state = rc.normalize_state(None, stakes="trusted local tool", snapshot="old")
    state.update(phase="correction", last_round=1, plan_line_count=1, debt=[deepcopy(old)])
    cc.save_lineage(cc.default_state_root(), cc.Lineage("metadata-debt", mode=cc.PLAN_MODE, review_state=state))
    calls = []

    def run(self, prompt, *args, **kwargs):
        calls.append(prompt)
        text = wire({"role":"correction", "governing_findings":[],
                     "debt_outcomes":[{"debt_id":"D1", "status":"closed", "evidence":["plan:1"]}],
                     "class_outcomes":{}, "class_actions":{}})
        return Review(text=text, raw=text, session_ref="metadata-reviewer")

    monkeypatch.setattr(engines.CodexEngine, "run", run)
    before = cc.load_lineage(cc.default_state_root(), "metadata-debt", stamp="before", mode=cc.PLAN_MODE)
    assert before.review_state["debt"] == [old]
    result = handlers.critique_plan({"repo_path":str(repo), "lineage":"metadata-debt", "round":2,
                                    "stakes":"trusted local tool", "claim_verification":False,
                                    "plan_text":"The plan contains substantive requirements.",
                                    "focus":"D1 concerns canonical transport metadata, not a plan defect; assess withdrawal."},
                                   engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    after = cc.load_lineage(cc.default_state_root(), "metadata-debt", stamp="after", mode=cc.PLAN_MODE)
    assert len(calls) == 1
    assert "D1 concerns canonical transport metadata" in calls[0]
    assert after.review_state["debt"][0]["status"] == "closed"
    assert after.review_state["debt"][0]["summary"] == old["summary"]
    assert after.review_state["phase"] == "final"
    assert "CONVERGENCE: BLOCKED" in result


def _checkpoint(tmp_path, *, sibling=False):
    debt = _unit_debt("D1", class_ids=["class-a"])
    state = rc.normalize_state(None, stakes="s", snapshot=rc.digest("old-plan"))
    state.update(phase="correction", last_round=6, plan_line_count=1, debt=[debt])
    if sibling:
        state["debt"].append(_unit_debt("D2", class_ids=["class-a"]))
    tracked = cc.TrackedClass("class-a", "guard invariant", cc.MAJOR, 1, cc.OPEN,
                              procedure="inspect the guard", members=("reviewed-path",))
    lineage = cc.Lineage("shifted-plan", mode=cc.PLAN_MODE, rounds=6,
                         classes={"class-a":tracked}, review_state=state)
    closure = SimpleNamespace(lineage=lineage, state_root=cc.default_state_root(),
                              correction_gates=[{"class_id":"class-a"}], claims_enabled=False,
                              round_no=7, reopened_class_ids=(), _blocks=lambda: [])
    error = rc.CheckpointRequired("correction limit reached", snapshot=rc.digest("revised-plan"), plan_line_count=2)
    error.attempts = [rc.Attempt("correction", "fake", "checkpoint-session", "checkpoint", 1, None)]
    handlers._settle_checkpoint(closure, error=error, mode=cc.PLAN_MODE)
    return deepcopy(closure.lineage)


@pytest.mark.parametrize("disposition,sibling", [("HOLD", False), ("CONCEDE", False), ("CONCEDE", True)])
def test_checkpoint_rebut_accepts_current_reviewed_plan_evidence(repo, tmp_path, disposition, sibling):
    before = _checkpoint(tmp_path, sibling=sibling)
    assert before.review_state["plan_line_count"] == 2
    assert before.review_state["snapshot_digest"] == rc.digest("revised-plan")
    engine = FakeEngine(json.dumps({"disposition":disposition, "reason":"The revised plan drops that scope.",
                                    "evidence":[{"anchor":"plan:2", "rationale":"Reviewed deletion."}]}))
    result = handlers.rebut({"repo_path":str(repo), "session_ref":"checkpoint-session", "rebuttal":"Scope deleted.",
                             "lineage":"shifted-plan", "class_id":"class-a", "debt_id":"D1", "lineage_mode":"plan"},
                            engine=engine, log_dir=tmp_path / "logs")
    assert result.startswith(disposition + ":")
    durable = cc.load_lineage(cc.default_state_root(), "shifted-plan", stamp="after", mode=cc.PLAN_MODE)
    if disposition == "HOLD":
        assert durable.review_state == before.review_state
        assert durable.classes == before.classes
    else:
        debt = durable.review_state["debt"][0]
        assert debt["status"] == "closed"
        assert debt["evidence"] == before.review_state["debt"][0]["evidence"]
        assert debt["concession"]["evidence"] == ["plan:2"]
        assert debt["concession"]["snapshot_digest"] == rc.digest("revised-plan")
        assert durable.classes["class-a"].status == (cc.OPEN if sibling else cc.CLOSED)
        assert durable.review_state["phase"] == ("correction" if sibling else "final")
        if sibling:
            assert durable.review_state["debt"][1] == before.review_state["debt"][1]
    audit = json.loads(next((tmp_path / "logs").glob("*.json")).read_text())
    assert audit["prior_target_debt"] == before.review_state["debt"][0]
    assert audit["rebut_evidence"] == ["plan:2"]


@pytest.mark.parametrize("anchor,bound", [("plan:3", 2), ("plan:0", 2), ("plan:2:4", 2), ("plan:2", None)])
def test_checkpoint_rebut_refuses_invalid_or_unbound_coordinates(repo, tmp_path, anchor, bound):
    before = _checkpoint(tmp_path)
    if bound is None:
        before.review_state.pop("plan_line_count")
        cc.save_lineage(cc.default_state_root(), before)
    engine = FakeEngine(json.dumps({"disposition":"CONCEDE", "reason":"changed",
                                    "evidence":[{"anchor":anchor, "rationale":"claimed evidence"}]}))
    with pytest.raises(ValueError):
        handlers.rebut({"repo_path":str(repo), "session_ref":"checkpoint-session", "rebuttal":"counter",
                        "lineage":"shifted-plan", "class_id":"class-a", "debt_id":"D1", "lineage_mode":"plan"},
                       engine=engine, log_dir=tmp_path / "logs")
    durable = cc.load_lineage(cc.default_state_root(), "shifted-plan", stamp="after", mode=cc.PLAN_MODE)
    assert durable.review_state == before.review_state
    assert durable.classes == before.classes
