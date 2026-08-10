import json

import pytest

from paranoia_local import class_closure as cc, handlers, prompts, review_census as rc
from paranoia_local.engines import Review


def lane(lane="domain", findings=None, assessments=None):
    return json.dumps({
        "lane": lane,
        "coverage": [
            {"id": key, "status": "covered", "summary": "checked",
             "evidence": ["plan:1"]} for key in rc.CHECKLIST
        ],
        "findings": findings or [], "class_assessments": assessments or [],
    })


def finding(fid="domain-1", severity="MAJOR"):
    return {"id": fid, "severity": severity, "summary": "broken",
            "evidence": ["a.py:1"], "remedy": "fix it"}


def settlement(**overrides):
    value = {
        "role": "census",
        "source_dispositions": [{"source_id": "domain-1", "governing_id": "C1"}],
        "assessment_dispositions": [],
        "findings": [finding("C1")],
        "debt": [{"id": "D1", "finding_id": "C1", "severity": "MAJOR",
                  "summary": "broken", "evidence": ["a.py:1"], "status": "open"}],
        "debt_updates": [], "class_records": [],
    }
    value.update(overrides)
    return json.dumps(value)


def test_lane_requires_every_checklist_item_exactly_once():
    parsed = json.loads(lane())
    parsed["coverage"].pop()
    with pytest.raises(rc.CensusError, match="every checklist"):
        rc.parse_lane(json.dumps(parsed), lane="domain")


def test_integrity_requires_every_class_and_violated_names_a_finding():
    text = lane("integrity", [finding("integrity-1")], [{
        "class_id": "abc", "verdict": "violated", "evidence": ["a.py:1"],
        "finding_id": "integrity-1",
    }])
    assert rc.parse_lane(text, lane="integrity", class_ids=["abc"])["lane"] == "integrity"
    with pytest.raises(rc.CensusError, match="every active class"):
        rc.parse_lane(lane("integrity"), lane="integrity", class_ids=["abc"])


def test_settlement_rejects_dropped_sources_and_blockers_without_debt():
    with pytest.raises(rc.CensusError, match="every source_id"):
        rc.parse_settlement(settlement(source_dispositions=[]), source_ids=["domain-1"],
                            assessment_ids=[])
    with pytest.raises(rc.CensusError, match="open debt"):
        rc.parse_settlement(settlement(debt=[]), source_ids=["domain-1"], assessment_ids=[])


def test_settlement_cannot_downgrade_source_or_debt_severity():
    value = json.loads(settlement())
    value["findings"][0]["severity"] = "MINOR"
    value["debt"] = []
    with pytest.raises(rc.CensusError, match="downgrade"):
        rc.parse_settlement(json.dumps(value), source_ids=["domain-1"],
                            source_severities={"domain-1": "MAJOR"}, assessment_ids=[])
    value = json.loads(settlement())
    value["debt"][0]["severity"] = "MINOR"
    with pytest.raises(rc.CensusError, match="debt severity"):
        rc.parse_settlement(json.dumps(value), source_ids=["domain-1"], assessment_ids=[])


def test_correction_cannot_clear_without_updating_every_existing_debt():
    value = json.loads(settlement())
    value.update(role="correction", source_dispositions=[], findings=[], debt=[], debt_updates=[])
    with pytest.raises(rc.CensusError, match="every existing debt"):
        rc.parse_settlement(json.dumps(value), source_ids=[], assessment_ids=[],
                            known_debt=["D1"], role="correction")


def test_replace_carries_corrected_severity_in_one_transition():
    register = rc.register_from_records([{
        "op": "replace", "class_id": "old", "invariant": "better invariant",
        "severity": "MINOR", "procedure": "check all sites",
    }], mechanized=False)
    lineage = cc.Lineage("x", classes={
        "old": cc.TrackedClass("old", "old invariant", "MAJOR", 1, cc.CLOSED,
                               procedure="old check")
    }, next_seq=2, mode=cc.PLAN_MODE)
    minted = cc.apply_register(lineage, register, round_no=3)
    assert lineage.classes["old"].status == cc.SUPERSEDED
    assert lineage.classes[minted[0]].severity == "MINOR"
    assert lineage.classes[minted[0]].status == cc.OPEN


def test_correction_requires_a_final_before_clearance():
    state = rc.normalize_state({}, stakes="s", snapshot="p")
    first = rc.parse_settlement(settlement(), source_ids=["domain-1"], assessment_ids=[])
    state = rc.settle_state(state, first, phase="census", snapshot="p", round_no=1)
    assert state["phase"] == "correction"
    close = json.loads(settlement())
    close.update(role="correction", source_dispositions=[], findings=[], debt=[],
                 debt_updates=[{"id":"D1","status":"closed","evidence":["a.py:2"]}])
    state = rc.settle_state(
        state, rc.parse_settlement(json.dumps(close), source_ids=[], assessment_ids=[],
                                   known_debt=["D1"], role="correction"),
        phase="correction", snapshot="p2", round_no=2,
    )
    assert state["phase"] == "final"
    assert "FINAL-REGRESSION: required" in rc.trailer(state)


def test_final_requires_complete_checklist_and_class_verdict():
    value = json.loads(settlement())
    value.update(role="final", source_dispositions=[], findings=[], debt=[], debt_updates=[],
                 assessment_dispositions=[{"assessment_id":"abc","governing_id":None}],
                 class_assessments=[], coverage=[])
    with pytest.raises(rc.CensusError, match="every checklist"):
        rc.parse_settlement(json.dumps(value), source_ids=[], assessment_ids=["abc"], role="final")


def test_evidence_anchors_resolve_against_snapshot(tmp_path):
    (tmp_path / "a.py").write_text("one\ntwo\n")
    rc.resolve_anchors({"evidence":["a.py:2"]}, root=tmp_path)
    with pytest.raises(rc.CensusError, match="out-of-range"):
        rc.resolve_anchors({"evidence":["a.py:3"]}, root=tmp_path)
    with pytest.raises(rc.CensusError, match="unresolvable plan"):
        rc.resolve_anchors({"evidence":["plan:3"]}, root=tmp_path, plan_lines=2)
    with pytest.raises(rc.CensusError, match="unresolvable repository"):
        rc.resolve_anchors({"evidence":["../outside.py:1"]}, root=tmp_path)


def test_violated_class_cannot_be_replaced_at_lower_severity():
    value = json.loads(settlement())
    value.update(
        source_dispositions=[], findings=[], debt=[],
        assessment_dispositions=[{"assessment_id":"abc","governing_id":"C1"}],
        class_records=[{
            "op":"replace", "class_id":"abc", "invariant":"narrower invariant",
            "severity":"MINOR", "procedure":"inspect it",
        }],
    )
    value["findings"] = [finding("C1", "MAJOR")]
    value["debt"] = [{
        "id":"D1", "finding_id":"C1", "severity":"MAJOR", "summary":"broken",
        "evidence":["a.py:1"], "status":"open",
    }]
    with pytest.raises(rc.CensusError, match="cannot be downgraded"):
        rc.parse_settlement(
            json.dumps(value), source_ids=[], assessment_ids=["abc"],
            assessment_verdicts={"abc":"violated"},
            class_states={"abc": (cc.CLOSED, False, "MAJOR")},
        )


def test_class_records_require_the_exact_mode_specific_shape():
    with pytest.raises(rc.CensusError, match="new class record"):
        rc.register_from_records([{
            "op":"new", "invariant":"x", "severity":"MAJOR", "procedure":"inspect",
            "extra":"ignored",
        }], mechanized=False)
    with pytest.raises(rc.CensusError, match="pattern"):
        rc.register_from_records([{
            "op":"new", "invariant":"x", "severity":"MAJOR",
            "pattern":"", "pathspec":".",
        }], mechanized=True)


def test_structural_only_tracked_plan_still_uses_staged_census(repo, tmp_path, monkeypatch):
    calls = []

    def run(self, prompt, *args, **kwargs):
        calls.append(prompt)
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            text = lane(lane_name)
        else:
            text = json.dumps({
                "role":"census", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":[], "class_records":[],
            })
        return Review(text=text, session_ref="s", raw=text)

    monkeypatch.setattr(handlers.eng.CodexEngine, "run", run)
    out = handlers.critique_plan({
        "plan_text":"# Plan\n\nDo it.", "repo_path":str(repo), "lineage":"structural-only",
        "round":1, "claim_verification":False, "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs")
    assert len(calls) == 4
    assert "## What works" in out
    assert "STRUCTURAL-PHASE: clear" in out
