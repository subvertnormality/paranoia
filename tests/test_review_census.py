import json

import pytest

from paranoia_local import class_closure as cc, review_census as rc


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
