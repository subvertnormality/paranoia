import json
import os
import subprocess

import pytest

from paranoia_local import (
    class_closure as cc, handlers, plan_claims as pc, prompts, review_census as rc,
)
from paranoia_local.engines import Review


HEADINGS = (
    "## What works", "## What doesn't work", "## Risks", "## Gaps", "## Improvements",
)


def test_staged_timeouts_are_generous_and_reserves_cover_full_retry_paths():
    assert handlers.STAGED_CENSUS_LANE_TIMEOUT_SEC == 1800
    assert handlers.STAGED_CONSOLIDATION_TIMEOUT_SEC == 1200
    assert handlers.STAGED_FOLLOWUP_TIMEOUT_SEC == 2400
    assert handlers.STAGED_FORMAT_RETRY_TIMEOUT_SEC == 600
    assert handlers.STAGED_CENSUS_RESERVE_SEC >= (
        handlers.STAGED_CENSUS_LANE_TIMEOUT_SEC
        + handlers.STAGED_CONSOLIDATION_TIMEOUT_SEC
        + handlers.STAGED_FORMAT_RETRY_TIMEOUT_SEC
    )
    assert handlers.STAGED_FOLLOWUP_RESERVE_SEC >= (
        handlers.STAGED_FOLLOWUP_TIMEOUT_SEC
        + handlers.STAGED_FORMAT_RETRY_TIMEOUT_SEC
    )


def test_census_cache_requires_every_exact_binding():
    lanes = rc.LANES[cc.PLAN_MODE]
    manifests = [payload(lane(name)) for name in lanes]
    binding = handlers._census_cache_binding(
        mode=cc.PLAN_MODE, snapshot="snapshot", stakes="stakes", body="body",
        active_classes=[], existing_debt=[], engine_name="codex", model="model",
        effort="high", web_search=False, plan_lines=3,
    )
    state = {"census_cache":{**binding, "manifests":manifests}}

    def validate(text, lane_name):
        return rc.parse_lane(text, lane=lane_name)

    assert handlers._cached_census_manifests(
        state, binding=binding, lanes=lanes, validate=validate,
    ) == manifests
    for key in binding:
        changed = dict(binding)
        changed[key] = f"different-{binding[key]}"
        assert handlers._cached_census_manifests(
            state, binding=changed, lanes=lanes, validate=validate,
        ) is None
    incomplete = {"census_cache":{**binding, "manifests":manifests[:-1]}}
    assert handlers._cached_census_manifests(
        incomplete, binding=binding, lanes=lanes, validate=validate,
    ) is None


def test_only_terminal_validation_rejection_can_cache_completed_lanes():
    def error(*outcomes):
        value = rc.CensusError("rejected")
        value.stage_role = "consolidation"  # type: ignore[attr-defined]
        value.failure_kind = "validation"  # type: ignore[attr-defined]
        value.attempts = [  # type: ignore[attr-defined]
            rc.Attempt("consolidation", "codex", "s", outcome, None, None)
            for outcome in outcomes
        ]
        return value

    assert handlers._cacheable_consolidation_error(error("validation-invalid"))
    assert handlers._cacheable_consolidation_error(error(
        "validation-invalid", "validation-invalid",
    ))
    assert not handlers._cacheable_consolidation_error(error("failed"))
    assert not handlers._cacheable_consolidation_error(error(
        "validation-invalid", "failed",
    ))
    lane_error = error("validation-invalid")
    lane_error.stage_role = "census-domain"  # type: ignore[attr-defined]
    assert not handlers._cacheable_consolidation_error(lane_error)
    assert not handlers._cacheable_consolidation_error(rc.CensusError("oversized"))


def assert_five_headings(text):
    assert [line for line in text.splitlines() if line.startswith("## ")] == list(HEADINGS)


def lane(lane="domain", findings=None, assessments=None):
    findings = findings or []
    coverage = [
        {"id": key, "status": "covered", "summary": "checked",
         "evidence": ["plan:1"], "finding_ids": []} for key in rc.CHECKLIST
    ]
    if findings:
        coverage[0].update(
            status="finding", finding_ids=[item["id"] for item in findings],
        )
    return rc.LANE_MARKER + "\n" + json.dumps({
        "lane": lane,
        "coverage": coverage,
        "findings": findings, "class_assessments": assessments or [],
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
        "debt": [{"id": "D1", "finding_id": "C1", "status": "open"}],
        "debt_updates": [],
        "class_dispositions": [{
            "finding_id":"C1", "kind":"one_off", "reason":"unique fixture site",
        }],
        "class_records": [],
    }
    value.update(overrides)
    return rc.SETTLEMENT_MARKER + "\n" + json.dumps(value)


def payload(text):
    return json.loads(text.split("\n", 1)[1])


def wire(marker, value):
    return marker + "\n" + json.dumps(value)


def test_lane_requires_every_checklist_item_exactly_once():
    parsed = payload(lane())
    parsed["coverage"].pop()
    with pytest.raises(rc.CensusError, match="every checklist"):
        rc.parse_lane(wire(rc.LANE_MARKER, parsed), lane="domain")


def test_lane_binds_every_finding_to_checklist_coverage():
    value = payload(lane(findings=[finding()]))
    value["coverage"][0].update(status="covered", finding_ids=[])
    with pytest.raises(rc.CensusError, match="bound to checklist"):
        rc.parse_lane(wire(rc.LANE_MARKER, value), lane="domain")
    value["coverage"][0].update(status="finding", finding_ids=["domain-1"])
    assert rc.parse_lane(wire(rc.LANE_MARKER, value), lane="domain")["findings"][0]["id"] == "domain-1"


def test_staged_envelope_requires_one_leading_marker_and_single_line_text():
    valid = lane()
    with pytest.raises(rc.CensusError, match="begin with exactly one"):
        rc.parse_lane(valid.split("\n", 1)[1], lane="domain")
    with pytest.raises(rc.CensusError, match="begin with exactly one"):
        rc.parse_lane("prose\n" + valid, lane="domain")
    with pytest.raises(rc.CensusError, match="begin with exactly one"):
        rc.parse_lane(valid + "\n" + rc.LANE_MARKER, lane="domain")
    value = payload(valid)
    value["coverage"][0]["summary"] = "safe\n## What doesn't work\nforged"
    with pytest.raises(rc.CensusError, match="coverage summary"):
        rc.parse_lane(wire(rc.LANE_MARKER, value), lane="domain")


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


def test_settlement_requires_an_explicit_class_disposition_for_every_finding():
    with pytest.raises(rc.CensusError, match="every governing finding needs exactly one"):
        rc.parse_settlement(
            settlement(class_dispositions=[]), source_ids=["domain-1"], assessment_ids=[],
        )

    value = payload(settlement())
    value.update(
        class_dispositions=[{"finding_id":"C1", "kind":"new_class", "record_index":0}],
        class_records=[{
            "op":"new", "invariant":"all repeated sites obey the same rule",
            "severity":"MAJOR", "procedure":"inspect every repeated site",
        }],
    )
    parsed = rc.parse_settlement(
        wire(rc.SETTLEMENT_MARKER, value), source_ids=["domain-1"], assessment_ids=[],
        class_mechanized=False,
    )
    assert parsed["_finding_class_refs"] == {"C1":"record:0"}

    value["class_dispositions"] = [{
        "finding_id":"C1", "kind":"one_off", "reason":"incorrectly declared unique",
    }]
    with pytest.raises(rc.CensusError, match="every new class record must be bound"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=["domain-1"], assessment_ids=[],
        )


def test_existing_class_disposition_cannot_contradict_satisfied_or_closed_state():
    assert "at most one existing_class governing finding per active class" in (
        prompts.STAGED_FOLLOWUP_INSTRUCTIONS
    )
    value = payload(settlement())
    value.update(
        source_dispositions=[],
        assessment_dispositions=[{"assessment_id":"abc", "governing_id":None}],
        class_dispositions=[{
            "finding_id":"C1", "kind":"existing_class", "class_id":"abc",
        }],
    )
    with pytest.raises(rc.CensusError, match="satisfied class assessment"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
            assessment_verdicts={"abc":"satisfied"},
            class_states={"abc":(cc.CLOSED, False, "MAJOR")},
        )


def test_open_unmechanized_satisfied_class_gets_deterministic_close():
    assert "currently open and unmechanized must also have" in (
        prompts.STAGED_CONSOLIDATION_INSTRUCTIONS
    )
    value = payload(settlement())
    value.update(
        source_dispositions=[], findings=[], debt=[], class_dispositions=[],
        assessment_dispositions=[{"assessment_id":"abc", "governing_id":None}],
        class_records=[],
    )
    parsed = rc.parse_settlement(
        wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
        assessment_verdicts={"abc":"satisfied"},
        class_states={"abc":(cc.OPEN, False, "MAJOR")},
    )
    assert parsed["class_records"] == [{"op":"close", "class_id":"abc"}]
    register = rc.register_from_records(parsed["class_records"], mechanized=False)
    assert register.transitions[0].kind == "CLOSED"

    with pytest.raises(rc.CensusError, match="mechanized open class cannot be model-closed"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
            assessment_verdicts={"abc":"satisfied"},
            class_states={"abc":(cc.OPEN, True, "MAJOR")},
        )


def test_correction_existing_class_binding_requires_a_matching_violated_assessment():
    value = payload(settlement())
    value.update(
        role="correction", source_dispositions=[],
        assessment_dispositions=[{"assessment_id":"abc", "governing_id":"C1"}],
        class_dispositions=[{
            "finding_id":"C1", "kind":"existing_class", "class_id":"abc",
        }],
        class_assessments=[{
            "class_id":"abc", "verdict":"violated", "evidence":["a.py:1"],
            "finding_id":"C1",
        }],
    )
    parsed = rc.parse_settlement(
        wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
        class_states={"abc":(cc.OPEN, False, "MAJOR")}, role="correction",
    )
    assert parsed["_finding_class_refs"] == {"C1":"abc"}
    with pytest.raises(rc.CensusError, match="closed violated class must reopen or replace"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
            class_states={"abc":(cc.CLOSED, False, "MAJOR")}, role="correction",
        )
    value["class_records"] = [{"op":"reopen", "class_id":"abc"}]
    assert rc.parse_settlement(
        wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
        class_states={"abc":(cc.CLOSED, False, "MAJOR")}, role="correction",
    )["_finding_class_refs"] == {"C1":"abc"}
    value["class_records"] = []

    value["class_assessments"] = []
    value["assessment_dispositions"] = []
    with pytest.raises(rc.CensusError, match="matching violated assessment"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
            class_states={"abc":(cc.OPEN, False, "MAJOR")}, role="correction",
        )

    value = payload(settlement())
    value.update(
        role="correction", source_dispositions=[],
        findings=[finding("C1"), finding("C2")],
        debt=[
            {"id":"D1", "finding_id":"C1", "status":"open"},
            {"id":"D2", "finding_id":"C2", "status":"open"},
        ],
        class_dispositions=[
            {"finding_id":"C1", "kind":"existing_class", "class_id":"abc"},
            {"finding_id":"C2", "kind":"existing_class", "class_id":"abc"},
        ],
        class_assessments=[{
            "class_id":"abc", "verdict":"violated", "evidence":["a.py:1"],
            "finding_id":"C1",
        }],
        assessment_dispositions=[{"assessment_id":"abc", "governing_id":"C1"}],
    )
    with pytest.raises(rc.CensusError, match="consolidate same-class occurrences"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
            class_states={"abc":(cc.OPEN, False, "MAJOR")}, role="correction",
        )


def test_census_rejects_an_extra_existing_class_finding_without_an_assessment():
    value = payload(settlement())
    value.update(
        source_dispositions=[
            {"source_id":"integrity:F1", "governing_id":"C1"},
            {"source_id":"domain:F2", "governing_id":"C2"},
        ],
        findings=[finding("C1"), finding("C2")],
        debt=[
            {"id":"D1", "finding_id":"C1", "status":"open"},
            {"id":"D2", "finding_id":"C2", "status":"open"},
        ],
        assessment_dispositions=[{"assessment_id":"abc", "governing_id":"C1"}],
        class_dispositions=[
            {"finding_id":"C1", "kind":"existing_class", "class_id":"abc"},
            {"finding_id":"C2", "kind":"existing_class", "class_id":"abc"},
        ],
    )
    with pytest.raises(rc.CensusError, match="consolidate same-class occurrences"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value),
            source_ids=["integrity:F1", "domain:F2"], assessment_ids=["abc"],
            assessment_verdicts={"abc":"violated"},
            assessment_findings={"abc":"integrity:F1"},
            class_states={"abc":(cc.OPEN, False, "MAJOR")}, role="census",
        )


def test_census_source_finding_can_fan_out_only_to_violated_classes():
    source = "integrity:F1"
    classes = ["class-a", "class-b"]
    value = payload(settlement())
    value.update(
        source_dispositions=[
            {"source_id":source, "governing_id":"G1"},
            {"source_id":source, "governing_id":"G2"},
        ],
        assessment_dispositions=[
            {"assessment_id":classes[0], "governing_id":"G1"},
            {"assessment_id":classes[1], "governing_id":"G2"},
        ],
        findings=[finding("G1"), finding("G2")],
        debt=[
            {"id":"D1", "finding_id":"G1", "status":"open"},
            {"id":"D2", "finding_id":"G2", "status":"open"},
        ],
        class_dispositions=[
            {"finding_id":"G1", "kind":"existing_class", "class_id":classes[0]},
            {"finding_id":"G2", "kind":"existing_class", "class_id":classes[1]},
        ],
    )
    parsed = rc.parse_settlement(
        wire(rc.SETTLEMENT_MARKER, value), source_ids=[source],
        source_severities={source:"MAJOR"}, assessment_ids=classes,
        assessment_verdicts={cid:"violated" for cid in classes},
        assessment_findings={cid:source for cid in classes},
        class_states={cid:(cc.OPEN, False, "MAJOR") for cid in classes},
        class_mechanized=None, role="census",
    )
    assert parsed["_finding_class_refs"] == {"G1":classes[0], "G2":classes[1]}
    state = rc.settle_state(
        rc.normalize_state({}, stakes="s", snapshot="p"), parsed,
        phase="census", snapshot="p", round_no=1,
    )
    assert [row["source_ids"] for row in state["debt"]] == [[source], [source]]

    value["source_dispositions"].append(
        {"source_id":source, "governing_id":"G2"},
    )
    with pytest.raises(rc.CensusError, match="duplicate source_id disposition"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[source],
            assessment_ids=classes,
        )

    value["source_dispositions"].pop()
    value["class_dispositions"][1] = {
        "finding_id":"G2", "kind":"one_off", "reason":"unique site",
    }
    value["assessment_dispositions"][1]["governing_id"] = None
    verdicts = {classes[0]:"violated", classes[1]:"satisfied"}
    cited_findings = {classes[0]:source, classes[1]:None}
    with pytest.raises(
        rc.CensusError,
        match="source fan-out requires distinct violated existing-class findings",
    ):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[source],
            source_severities={source:"MAJOR"}, assessment_ids=classes,
            assessment_verdicts=verdicts,
            assessment_findings=cited_findings,
            class_states={cid:(cc.OPEN, False, "MAJOR") for cid in classes},
            class_mechanized=None, role="census",
        )


def test_settlement_accepts_only_the_observed_decorative_marker_variant():
    short = rc.SETTLEMENT_MARKER.removesuffix(" ===")
    text = settlement().replace(rc.SETTLEMENT_MARKER, short, 1)
    assert rc.parse_settlement(
        text, source_ids=["domain-1"], assessment_ids=[],
    )["role"] == "census"
    with pytest.raises(rc.CensusError, match="begin with exactly one"):
        rc.parse_settlement(
            "prose\n" + text, source_ids=["domain-1"], assessment_ids=[],
        )


def test_lane_accepts_only_the_observed_decorative_marker_variant():
    short = rc.LANE_MARKER.removesuffix(" ===")
    text = lane().replace(rc.LANE_MARKER, short, 1)
    assert rc.parse_lane(text, lane="domain")["lane"] == "domain"
    with pytest.raises(rc.CensusError, match="begin with exactly one"):
        rc.parse_lane("prose\n" + text, lane="domain")


def test_settlement_cannot_downgrade_source_and_derives_debt_fields():
    value = payload(settlement())
    value["findings"][0]["severity"] = "MINOR"
    value["debt"] = []
    with pytest.raises(rc.CensusError, match="downgrade"):
        rc.parse_settlement(wire(rc.SETTLEMENT_MARKER, value), source_ids=["domain-1"],
                            source_severities={"domain-1": "MAJOR"}, assessment_ids=[])
    parsed = rc.parse_settlement(
        settlement(), source_ids=["domain-1"], assessment_ids=[],
    )
    assert parsed["debt"][0] == {
        "id":"D1", "finding_id":"C1", "status":"open", "severity":"MAJOR",
        "summary":"broken", "evidence":["a.py:1"], "remedy":"fix it",
    }

    fatal = payload(settlement())
    fatal["findings"][0]["severity"] = "BLOCKER"
    with pytest.raises(rc.CensusError, match="downgrade"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, fatal), source_ids=["domain-1"],
            source_severities={"domain-1": "FATAL"}, assessment_ids=[],
        )


def test_correction_cannot_clear_without_updating_every_existing_debt():
    value = payload(settlement())
    value.update(role="correction", source_dispositions=[], findings=[], debt=[], debt_updates=[])
    value.update(class_dispositions=[], class_assessments=[])
    with pytest.raises(rc.CensusError, match="every existing debt"):
        rc.parse_settlement(wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
                            known_debt=["D1"], role="correction")


def test_open_debt_update_requires_and_renders_an_actionable_reason():
    value = payload(settlement())
    value.update(
        role="correction", source_dispositions=[], assessment_dispositions=[],
        findings=[], debt=[],
        debt_updates=[{"id":"D1", "status":"open", "evidence":["a.py:2"]}],
        class_dispositions=[], class_assessments=[],
    )
    with pytest.raises(rc.CensusError, match="debt update fields"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
            known_debt=["D1"], role="correction",
        )
    value["debt_updates"][0]["reason"] = "the stale-head path still bypasses validation"
    parsed = rc.parse_settlement(
        wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
        known_debt=["D1"], role="correction",
    )
    state = {
        "phase":"correction", "debt":[{
            "id":"D1", "finding_id":"G1", "status":"open", "severity":"MAJOR",
            "summary":"validate the selected head", "evidence":["a.py:1"],
            "remedy":"reject a stale head", "source_ids":[],
        }],
    }
    updated = rc.settle_state(
        state, parsed, phase="correction", snapshot="p", round_no=2,
    )
    rendered = rc.render_review(parsed, updated)
    what_doesnt_work = rendered.split("## What doesn't work\n\n", 1)[1].split("\n\n## Risks", 1)[0]
    assert what_doesnt_work != "Nothing notable."
    assert "stale-head path still bypasses validation" in rendered
    assert "validate the selected head" in rendered

    advisory = finding("A1", "MINOR")
    advisory["summary"] = "current advisory finding"
    rendered = rc.render_review(
        {"findings":[advisory]},
        {"debt":updated["debt"]},
    )
    assert "current advisory finding" in rendered
    assert "validate the selected head" in rendered
    rendered = rc.render_review({"findings":[]}, {"debt":[
        {"id":"D1", "finding_id":"F1", "status":"open", "severity":"MAJOR",
         "summary":"first durable debt", "evidence":[], "remedy":"fix first"},
        {"id":"D2", "finding_id":"F1", "status":"open", "severity":"MAJOR",
         "summary":"second durable debt", "evidence":[], "remedy":"fix second"},
    ]})
    assert "first durable debt" in rendered
    assert "second durable debt" in rendered


def test_correction_cannot_downgrade_a_class_or_reuse_durable_debt():
    value = payload(settlement())
    value.update(
        role="correction", source_dispositions=[], assessment_dispositions=[],
        findings=[], debt=[],
        debt_updates=[{"id":"D1","status":"closed","evidence":["a.py:2"]}],
        class_dispositions=[], class_assessments=[],
        class_records=[{"op":"reclassify","class_id":"abc","severity":"MINOR"}],
    )
    with pytest.raises(rc.CensusError, match="cannot downgrade"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
            class_states={"abc": (cc.OPEN, False, "MAJOR")},
            class_mechanized=False, known_debt=["D1"], role="correction",
        )

    first = rc.parse_settlement(settlement(), source_ids=["domain-1"], assessment_ids=[])
    state = rc.settle_state(
        rc.normalize_state({}, stakes="s", snapshot="p"), first,
        phase="census", snapshot="p", round_no=1,
    )
    duplicate = rc.parse_settlement(
        settlement(), source_ids=["domain-1"], assessment_ids=[],
    )
    duplicate.update(source_dispositions=[], findings=[finding("C2")])
    duplicate["debt"][0].update(finding_id="C2")
    with pytest.raises(rc.CensusError, match="reuses durable id"):
        rc.settle_state(state, duplicate, phase="correction", snapshot="p2", round_no=2)
    assert state["debt"][0]["source_ids"] == ["domain-1"]


def test_every_staged_role_rejects_a_satisfied_class_downgrade():
    value = payload(settlement())
    value.update(
        source_dispositions=[], findings=[], debt=[],
        assessment_dispositions=[{"assessment_id":"abc", "governing_id":None}],
        class_dispositions=[],
        class_records=[{"op":"reclassify", "class_id":"abc", "severity":"MINOR"}],
    )
    with pytest.raises(rc.CensusError, match="cannot downgrade"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
            assessment_verdicts={"abc":"satisfied"},
            assessment_findings={"abc":None},
            class_states={"abc": (cc.CLOSED, False, "MAJOR")}, role="census",
        )


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


def test_branch_records_allow_procedure_classes_and_reject_mechanized_reopen():
    created = rc.register_from_records([{
        "op":"new", "invariant":"new semantic invariant", "severity":"MAJOR",
        "procedure":"inspect every generated record",
    }], mechanized=None)
    assert created.new_classes[0].procedure == "inspect every generated record"
    assert created.new_classes[0].pattern is None

    register = rc.register_from_records([{
        "op":"replace", "class_id":"old", "invariant":"semantic invariant",
        "severity":"MAJOR", "procedure":"inspect every transition",
    }], mechanized=None)
    lineage = cc.Lineage("branch", classes={
        "old": cc.TrackedClass(
            "old", "legacy semantic invariant", "MAJOR", 1, cc.CLOSED,
            procedure="inspect one transition",
        ),
    }, next_seq=2, mode=cc.BRANCH_MODE)
    minted = cc.apply_register(lineage, register, round_no=2)
    assert lineage.classes[minted[0]].procedure == "inspect every transition"

    to_procedure = rc.register_from_records([{
        "op":"replace", "class_id":"regex", "invariant":"semantic successor",
        "severity":"MAJOR", "procedure":"inspect semantics",
    }], mechanized=None)
    conversion = cc.Lineage("conversion", classes={
        "regex":cc.TrackedClass(
            "regex", "regex predecessor", "MAJOR", 1, cc.CLOSED,
            pattern="BAD", pathspec="*.py",
        ),
    }, next_seq=2, mode=cc.BRANCH_MODE)
    successor = cc.apply_register(conversion, to_procedure, round_no=2)[0]
    assert conversion.classes[successor].procedure == "inspect semantics"

    to_pattern = rc.register_from_records([{
        "op":"replace", "class_id":"semantic", "invariant":"regex successor",
        "severity":"MAJOR", "pattern":"BAD", "pathspec":"*.py",
    }], mechanized=None)
    conversion = cc.Lineage("conversion-2", classes={
        "semantic":cc.TrackedClass(
            "semantic", "semantic predecessor", "MAJOR", 1, cc.CLOSED,
            procedure="inspect semantics",
        ),
    }, next_seq=2, mode=cc.BRANCH_MODE)
    successor = cc.apply_register(conversion, to_pattern, round_no=2)[0]
    assert conversion.classes[successor].pattern == "BAD"

    value = payload(settlement())
    value.update(
        source_dispositions=[],
        assessment_dispositions=[{"assessment_id":"abc", "governing_id":"C1"}],
        class_dispositions=[{"finding_id":"C1", "kind":"existing_class", "class_id":"abc"}],
        class_records=[{"op":"reopen", "class_id":"abc"}],
    )
    with pytest.raises(rc.CensusError, match="mechanized class must replace"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
            assessment_verdicts={"abc":"violated"},
            class_states={"abc": (cc.CLOSED, True, "MAJOR")},
        )


def test_correction_requires_a_final_before_clearance():
    state = rc.normalize_state({}, stakes="s", snapshot="p")
    first = rc.parse_settlement(settlement(), source_ids=["domain-1"], assessment_ids=[])
    state = rc.settle_state(state, first, phase="census", snapshot="p", round_no=1)
    assert state["phase"] == "correction"
    close = payload(settlement())
    close.update(role="correction", source_dispositions=[], findings=[], debt=[],
                 debt_updates=[{"id":"D1","status":"closed","evidence":["a.py:2"]}],
                 class_dispositions=[], class_assessments=[])
    state = rc.settle_state(
        state, rc.parse_settlement(wire(rc.SETTLEMENT_MARKER, close), source_ids=[], assessment_ids=[],
                                   known_debt=["D1"], role="correction"),
        phase="correction", snapshot="p2", round_no=2,
    )
    assert state["phase"] == "final"
    assert "FINAL-REGRESSION: required" in rc.trailer(state)


def test_final_requires_complete_checklist_and_class_verdict():
    value = payload(settlement())
    value.update(role="final", source_dispositions=[], findings=[], debt=[], debt_updates=[],
                 assessment_dispositions=[{"assessment_id":"abc","governing_id":None}],
                 class_dispositions=[],
                 class_assessments=[], coverage=[])
    with pytest.raises(rc.CensusError, match="every checklist"):
        rc.parse_settlement(wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"], role="final")


def test_evidence_anchors_resolve_against_snapshot(tmp_path):
    (tmp_path / "a.py").write_text("one\ntwo\n")
    rc.resolve_anchors({"evidence":["a.py:2"]}, root=tmp_path)
    rc.resolve_anchors(
        {"evidence":["repository/a.py:2"]}, root=tmp_path,
        trusted_roots={"repository":tmp_path},
    )
    with pytest.raises(rc.CensusError, match="requires repository/ prefix"):
        rc.resolve_anchors(
            {"evidence":["a.py:2"]}, root=tmp_path,
            trusted_roots={"repository":tmp_path},
        )
    with pytest.raises(rc.CensusError, match="out-of-range"):
        rc.resolve_anchors({"evidence":["a.py:3"]}, root=tmp_path)
    with pytest.raises(rc.CensusError, match="unresolvable plan"):
        rc.resolve_anchors({"evidence":["plan:3"]}, root=tmp_path, plan_lines=2)
    with pytest.raises(rc.CensusError, match="unresolvable repository"):
        rc.resolve_anchors({"evidence":["../outside.py:1"]}, root=tmp_path)
    outside = tmp_path.parent / "outside-anchor.py"
    outside.write_text("outside\n")
    (tmp_path / "linked.py").symlink_to(outside)
    with pytest.raises(rc.CensusError, match="unresolvable repository"):
        rc.resolve_anchors({"evidence":["linked.py:1"]}, root=tmp_path)
    materialized = tmp_path.parent / "materialized-repository"
    materialized.mkdir()
    (materialized / "README.md").write_text("snapshot\n")
    (tmp_path / "repository").symlink_to(materialized, target_is_directory=True)
    rc.resolve_anchors(
        {"evidence":["repository/README.md:1"]}, root=tmp_path,
        trusted_roots={"repository":materialized},
    )


def test_no_session_validation_failure_is_not_mislabeled_as_format(tmp_path):
    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            text = wire(rc.SETTLEMENT_MARKER, {"role":"census"})
            return Review(text=text, session_ref=None, raw=text)

    with pytest.raises(rc.CensusError, match="validation invalid") as caught:
        handlers._staged_call(
            role="consolidation", engine=Engine(), prompt="p", cwd=tmp_path,
            model="m", effort="high", timeout=10, on_progress=None,
            retry_guidance=prompts.STAGED_SETTLEMENT_RETRY_GUIDANCE,
            parser=lambda text: rc.parse_settlement(
                text, source_ids=[], assessment_ids=[],
            ),
        )
    assert "format invalid" not in str(caught.value)
    assert caught.value.stage_role == "consolidation"
    assert caught.value.failure_kind == "validation"
    assert [row.outcome for row in caught.value.attempts] == ["validation-invalid"]


def test_empty_debt_id_gets_one_same_session_format_retry(tmp_path):
    invalid = payload(settlement())
    invalid["debt"][0]["id"] = ""

    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            text = wire(rc.SETTLEMENT_MARKER, invalid)
            return Review(text=text, session_ref="s", raw=text)

        def resume(self, session_ref, prompt, *args, **kwargs):
            assert "debt id must be" in prompt
            return Review(text=settlement(), session_ref=session_ref, raw=settlement())

    _, parsed, attempts = handlers._staged_call(
        role="consolidation", engine=Engine(), prompt="p", cwd=tmp_path,
        model="m", effort="high", timeout=10, on_progress=None,
        retry_guidance=prompts.STAGED_SETTLEMENT_RETRY_GUIDANCE,
        parser=lambda text: rc.parse_settlement(
            text, source_ids=["domain-1"], assessment_ids=[],
        ),
    )
    assert parsed["debt"][0]["id"] == "D1"
    assert [row.outcome for row in attempts] == ["validation-invalid", "completed"]


def test_staged_retry_repeats_exact_shapes_after_multirow_schema_drift(tmp_path):
    invalid = payload(settlement())
    invalid["findings"][0].pop("remedy")
    invalid["findings"][0]["class_id"] = "wrong"
    invalid["class_records"] = [{
        "class_id":"wrong", "status":"open", "finding_ids":["C1"],
        "debt_ids":["D1"],
    }]

    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            text = wire(rc.SETTLEMENT_MARKER, invalid)
            return Review(text=text, session_ref="s", raw=text)

        def resume(self, session_ref, prompt, *args, **kwargs):
            assert "missing ['remedy']" in prompt
            assert "Finding rows have exactly id,severity,summary,evidence,remedy" in prompt
            assert "They never contain status,finding_ids,debt_ids" in prompt
            return Review(text=settlement(), session_ref=session_ref, raw=settlement())

    _, parsed, attempts = handlers._staged_call(
        role="consolidation", engine=Engine(), prompt="p", cwd=tmp_path,
        model="m", effort="high", timeout=10, on_progress=None,
        retry_guidance=prompts.STAGED_SETTLEMENT_RETRY_GUIDANCE,
        parser=lambda text: rc.parse_settlement(
            text, source_ids=["domain-1"], assessment_ids=[],
        ),
    )
    assert parsed["findings"][0]["remedy"] == "fix it"
    assert [row.outcome for row in attempts] == ["validation-invalid", "completed"]


def test_malformed_referenced_new_class_row_stays_in_bounded_format_retry(tmp_path):
    invalid = payload(settlement())
    invalid.update(
        class_dispositions=[{"finding_id":"C1", "kind":"new_class", "record_index":0}],
        class_records=["not an object"],
    )

    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            text = wire(rc.SETTLEMENT_MARKER, invalid)
            return Review(text=text, session_ref="s", raw=text)

        def resume(self, session_ref, prompt, *args, **kwargs):
            assert "new-class disposition must uniquely reference" in prompt
            return Review(text=settlement(), session_ref=session_ref, raw=settlement())

    _, parsed, attempts = handlers._staged_call(
        role="consolidation", engine=Engine(), prompt="p", cwd=tmp_path,
        model="m", effort="high", timeout=10, on_progress=None,
        retry_guidance=prompts.STAGED_SETTLEMENT_RETRY_GUIDANCE,
        parser=lambda text: rc.parse_settlement(
            text, source_ids=["domain-1"], assessment_ids=[],
        ),
    )
    assert parsed["class_dispositions"][0]["kind"] == "one_off"
    assert [row.outcome for row in attempts] == ["validation-invalid", "completed"]


def test_staged_retry_names_advisory_class_debt_invariant(tmp_path):
    invalid = payload(settlement())
    invalid.update(
        source_dispositions=[{"source_id":"integrity:F1","governing_id":"G1"}],
        findings=[finding("G1", "OUT-OF-SCOPE")], debt=[],
        assessment_dispositions=[{"assessment_id":"abc","governing_id":"G1"}],
        class_dispositions=[{"finding_id":"G1", "kind":"existing_class", "class_id":"abc"}],
    )
    repaired = dict(invalid)
    repaired["debt"] = [{"id":"D1","finding_id":"G1","status":"open"}]

    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            text = wire(rc.SETTLEMENT_MARKER, invalid)
            return Review(text=text, session_ref="s", raw=text)

        def resume(self, session_ref, prompt, *args, **kwargs):
            assert "every violated class needs exactly one open debt record" in prompt
            assert "including MINOR and OUT-OF-SCOPE" in prompt
            text = wire(rc.SETTLEMENT_MARKER, repaired)
            return Review(text=text, session_ref=session_ref, raw=text)

    _, parsed, attempts = handlers._staged_call(
        role="consolidation", engine=Engine(), prompt="p", cwd=tmp_path,
        model="m", effort="high", timeout=10, on_progress=None,
        retry_guidance=prompts.STAGED_SETTLEMENT_RETRY_GUIDANCE,
        parser=lambda text: rc.parse_settlement(
            text, source_ids=["integrity:F1"], assessment_ids=["abc"],
            assessment_verdicts={"abc":"violated"},
            assessment_findings={"abc":"integrity:F1"},
        ),
    )
    assert parsed["debt"][0]["severity"] == "OUT-OF-SCOPE"
    assert [row.outcome for row in attempts] == ["validation-invalid", "completed"]


def test_violated_class_cannot_be_replaced_at_lower_severity():
    value = payload(settlement())
    value.update(
        source_dispositions=[], findings=[], debt=[],
        assessment_dispositions=[{"assessment_id":"abc","governing_id":"C1"}],
        class_dispositions=[{"finding_id":"C1", "kind":"existing_class", "class_id":"abc"}],
        class_records=[{
            "op":"replace", "class_id":"abc", "invariant":"narrower invariant",
            "severity":"MINOR", "procedure":"inspect it",
        }],
    )
    value["findings"] = [finding("C1", "MAJOR")]
    value["debt"] = [{"id":"D1", "finding_id":"C1", "status":"open"}]
    with pytest.raises(rc.CensusError, match="downgrade"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
            assessment_verdicts={"abc":"violated"},
            class_states={"abc": (cc.CLOSED, False, "MAJOR")},
        )


def test_violated_class_mapping_follows_cited_finding_and_reopens_atomically():
    value = payload(settlement())
    value.update(
        role="final", source_dispositions=[],
        assessment_dispositions=[{"assessment_id":"abc","governing_id":"G1"}],
        findings=[finding("G1", "BLOCKER")],
        debt=[{"id":"D1", "finding_id":"G1", "status":"open"}],
        class_dispositions=[{"finding_id":"G1", "kind":"existing_class", "class_id":"abc"}],
        debt_updates=[], class_records=[{"op":"reopen", "class_id":"abc"}],
        coverage=payload(lane(findings=[finding("G1", "BLOCKER")]))["coverage"],
        class_assessments=[{
            "class_id":"abc", "verdict":"violated", "evidence":["a.py:1"],
            "finding_id":"G1",
        }],
    )
    parsed = rc.parse_settlement(
        wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
        class_states={"abc": (cc.CLOSED, False, "BLOCKER")}, role="final",
    )
    assert parsed["class_records"] == [{"op":"reopen", "class_id":"abc"}]
    value["assessment_dispositions"][0]["governing_id"] = "G2"
    value["findings"].append(finding("G2", "BLOCKER"))
    value["class_dispositions"].append({
        "finding_id":"G2", "kind":"one_off", "reason":"unique second fixture",
    })
    value["debt"].append({"id":"D2", "finding_id":"G2", "status":"open"})
    value["coverage"][0]["finding_ids"].append("G2")
    with pytest.raises(rc.CensusError, match="matching violated assessment"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
            class_states={"abc": (cc.CLOSED, False, "BLOCKER")}, role="final",
        )


def test_violated_advisory_class_still_requires_concrete_debt():
    assert "every governing finding referenced by a\nviolated class assessment" in (
        prompts.STAGED_CONSOLIDATION_INSTRUCTIONS
    )
    value = payload(settlement())
    value.update(
        source_dispositions=[{"source_id":"integrity:F1","governing_id":"G1"}],
        findings=[finding("G1", "MINOR")], debt=[],
        assessment_dispositions=[{"assessment_id":"abc","governing_id":"G1"}],
        class_dispositions=[{"finding_id":"G1", "kind":"existing_class", "class_id":"abc"}],
        class_records=[{"op":"reopen", "class_id":"abc"}],
    )
    with pytest.raises(rc.CensusError, match="violated class needs exactly one open debt"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=["integrity:F1"],
            assessment_ids=["abc"], assessment_verdicts={"abc":"violated"},
            assessment_findings={"abc":"integrity:F1"},
            class_states={"abc": (cc.CLOSED, False, "MINOR")}, role="census",
        )
    value["debt"] = [{"id":"D1", "finding_id":"G1", "status":"open"}]
    assert rc.parse_settlement(
        wire(rc.SETTLEMENT_MARKER, value), source_ids=["integrity:F1"],
        assessment_ids=["abc"], assessment_verdicts={"abc":"violated"},
        assessment_findings={"abc":"integrity:F1"},
        class_states={"abc": (cc.CLOSED, False, "MINOR")}, role="census",
    )["debt"][0]["severity"] == "MINOR"


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


def test_anchor_rejection_gets_one_same_session_retry_with_diagnostics(tmp_path):
    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            value = payload(lane(findings=[finding("F1")]))
            value["coverage"][0]["evidence"] = ["missing.py:1"]
            value["findings"][0]["evidence"] = ["missing.py:1"]
            text = wire(rc.LANE_MARKER, value)
            return Review(text=text, session_ref="session", raw=text)

        def resume(self, session_ref, prompt, *args, **kwargs):
            assert session_ref == "session"
            assert "unresolvable repository anchor" in prompt
            assert "Lane manifests never contain settlement debt" in prompt
            assert "open debt" not in prompt
            (tmp_path / "ok.py").write_text("ok\n")
            value = payload(lane(findings=[finding("F1")]))
            for row in value["coverage"]:
                row["evidence"] = ["ok.py:1"]
            value["findings"][0]["evidence"] = ["ok.py:1"]
            text = wire(rc.LANE_MARKER, value)
            return Review(text=text, session_ref="session", raw=text)

    def parse(text):
        value = rc.parse_lane(text, lane="domain")
        rc.resolve_anchors(value, root=tmp_path)
        return value

    _, _, attempts = handlers._staged_call(
        role="census-domain", engine=Engine(), prompt="review", cwd=tmp_path,
        model="m", effort="high", timeout=10, parser=parse, on_progress=None,
        retry_guidance=prompts.STAGED_LANE_RETRY_GUIDANCE,
    )
    assert [attempt.role for attempt in attempts] == [
        "census-domain", "census-domain-format-retry",
    ]
    assert [attempt.sequence for attempt in attempts] == [None, None]
    assert [attempt.outcome for attempt in attempts] == ["validation-invalid", "completed"]
    assert all(attempt.response_sha256 and attempt.response_excerpt for attempt in attempts)


def test_new_debt_labels_are_rekeyed_when_durable_history_owns_them():
    debt = [
        {"id":"D1", "finding_id":"G1", "status":"open"},
        {"id":"local", "finding_id":"G2", "status":"open"},
        {"id":"D3", "finding_id":"G3", "status":"open"},
    ]
    handlers._allocate_fresh_debt_ids(debt, {"D1", "D2", "local"})
    assert [item["id"] for item in debt] == ["D4", "D5", "D3"]


def test_structural_pending_settles_zero_attempt_round_and_releases_latch(tmp_path):
    closure = handlers._PlanClassClosure(
        "pending-plan", round_no=1, state_root=tmp_path, stamp="T",
    )
    closure.prepare()
    review, trailer, attempts = handlers._structural_pending_review(
        closure, mode=cc.PLAN_MODE, claim_state=pc.empty_state(),
        reason="not enough bounded time",
    )
    closure.release()
    assert review.error and attempts == []
    assert_five_headings(review.text)
    assert "CLASS-REGISTER: structural pending" in trailer
    assert "CLASS-CLOSURE: 0 open, 0 closed" in trailer
    assert "STRUCTURAL-PENDING" in trailer and "CONVERGENCE: BLOCKED" in trailer
    assert not (cc.lineage_dir(tmp_path) / "pending-plan.pending").exists()


def test_state_unavailable_result_has_five_headings(tmp_path):
    closure = handlers._PlanClassClosure(
        "unavailable-plan", round_no=1, state_root=tmp_path, stamp="T",
    )
    closure.unavailable = "cannot read state"
    review, trailer, attempts = handlers._state_unavailable_review(
        closure, mode=cc.PLAN_MODE, claim_state=pc.empty_state(),
    )
    assert review.error and attempts == [] and "STATE-UNAVAILABLE" in trailer
    assert "CLASS-REGISTER: staged state unavailable" in trailer
    assert_five_headings(review.text)


def test_staged_generic_failure_clears_old_cache_and_uses_matching_debt(tmp_path):
    closure = handlers._PlanClassClosure(
        "format-failure", round_no=1, state_root=tmp_path, stamp="T",
    )
    closure.prepare()
    closure.lineage.review_state = rc.normalize_state({}, stakes="s", snapshot="p")
    closure.lineage.review_state["census_cache"] = {"stale":True}
    error = handlers._staged_error(
        "provider exited", role="correction", kind="execution",
    )
    review, trailer, attempts = handlers._settle_staged_failure(
        closure, stakes="s", snapshot="p", error=error,
        mode=cc.PLAN_MODE,
    )
    closure.release()
    assert review.error and attempts == []
    assert "CLASS-REGISTER: staged rejected: provider exited" in trailer
    assert "CLASS-CLOSURE: 0 open, 0 closed" in trailer
    assert "STRUCTURAL-ERROR: provider exited" in trailer
    assert "STRUCTURAL-FAILURE: role=correction kind=execution" in trailer
    assert "CONVERGENCE: BLOCKED — staged execution failure did not settle." in trailer
    assert "census_cache" not in closure.lineage.review_state
    assert closure.lineage.review_state["staged_failure"] == {
        "role":"correction", "kind":"execution", "message":"provider exited",
    }
    assert "validation_debt" not in closure.lineage.review_state


def test_consolidation_preflight_validation_without_cache_is_structured_failure(tmp_path):
    closure = handlers._PlanClassClosure(
        "validation-failure", round_no=1, state_root=tmp_path, stamp="T",
    )
    closure.prepare()
    error = rc.CensusError("lane schema rejected")
    error.stage_role = "consolidation"  # type: ignore[attr-defined]
    error.failure_kind = "validation"  # type: ignore[attr-defined]
    review, trailer, attempts = handlers._settle_staged_failure(
        closure, stakes="s", snapshot="p", error=error, mode=cc.PLAN_MODE,
    )
    closure.release()
    assert review.error and attempts == []
    assert "validation_debt" not in closure.lineage.review_state
    assert closure.lineage.review_state["staged_failure"] == {
        "role":"consolidation", "kind":"validation", "message":"lane schema rejected",
    }
    assert "STRUCTURAL-FAILURE: role=consolidation kind=validation" in trailer
    assert "CONVERGENCE: BLOCKED — staged validation failure did not settle." in trailer


def test_lane_validation_failure_remains_generic_staged_failure(tmp_path):
    closure = handlers._PlanClassClosure(
        "lane-validation-failure", round_no=1, state_root=tmp_path, stamp="T",
    )
    closure.prepare()
    error = handlers._staged_error(
        "lane prompt exceeds ceiling", role="census-domain", kind="validation",
    )
    _, trailer, _ = handlers._settle_staged_failure(
        closure, stakes="s", snapshot="p", error=error, mode=cc.PLAN_MODE,
    )
    closure.release()
    assert closure.lineage.review_state["staged_failure"] == {
        "role":"census-domain", "kind":"validation",
        "message":"lane prompt exceeds ceiling",
    }
    assert "validation_debt" not in closure.lineage.review_state
    assert "STRUCTURAL-FAILURE: role=census-domain kind=validation" in trailer
    assert "CONVERGENCE: BLOCKED — staged validation failure did not settle." in trailer


def test_consolidation_prompt_ceiling_is_noncacheable_structured_validation(
    tmp_path, monkeypatch,
):
    closure = handlers._PlanClassClosure(
        "consolidation-preflight", round_no=1, state_root=tmp_path, stamp="T",
    )
    closure.prepare()

    class Engine:
        name = "fake"

        def run(self, prompt, *args, **kwargs):
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            text = lane(lane_name)
            return Review(text=text, session_ref="s", raw=text)

    monkeypatch.setattr(rc, "MAX_CONSOLIDATION_PROMPT_CHARS", 1)
    with pytest.raises(rc.CensusError, match="consolidation prompt") as caught:
        handlers._staged_structural_review(
            engine=Engine(), cwd=tmp_path, model="m", effort="high",
            mode=cc.PLAN_MODE, body="artifact", closure=closure, stakes="s",
            snapshot="p", round_no=1, on_progress=None, plan_lines=1,
        )
    assert caught.value.stage_role == "consolidation"
    assert caught.value.failure_kind == "validation"
    assert not handlers._cacheable_consolidation_error(caught.value)
    _, trailer, _ = handlers._settle_staged_failure(
        closure, stakes="s", snapshot="p", error=caught.value, mode=cc.PLAN_MODE,
    )
    closure.release()
    assert "STRUCTURAL-FAILURE: role=consolidation kind=validation" in trailer
    assert "validation_debt" not in closure.lineage.review_state
    assert "census_cache" not in closure.lineage.review_state


def test_staged_settlement_save_failure_retains_latch_and_five_heading_result(
    tmp_path, monkeypatch,
):
    state = rc.normalize_state({}, stakes="s", snapshot="p")
    state.update(phase="correction", debt=[{
        "id":"D1", "finding_id":"G1", "status":"open", "severity":"MAJOR",
        "summary":"fix", "evidence":["plan:1"], "source_ids":[],
        "first_round":1, "last_round":1,
    }])
    cc.save_lineage(
        tmp_path,
        cc.Lineage("save-fail", rounds=1, mode=cc.PLAN_MODE, review_state=state),
    )
    closure = handlers._PlanClassClosure(
        "save-fail", round_no=2, state_root=tmp_path, stamp="T",
    )
    closure.prepare()

    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"correction", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                    "debt_updates":[{"id":"D1","status":"closed","evidence":["plan:1"]}],
                    "class_dispositions":[], "class_assessments":[],
                "class_records":[],
            })
            return Review(text=text, session_ref="s", raw=text)

    monkeypatch.setattr(
        cc, "save_lineage",
        lambda *args, **kwargs: (_ for _ in ()).throw(cc.StateUnavailable("ambiguous write")),
    )
    review, trailer, attempts = handlers._staged_structural_review(
        engine=Engine(), cwd=tmp_path, model="m", effort="high", mode=cc.PLAN_MODE,
        body="artifact", closure=closure, stakes="s", snapshot="p", round_no=2,
        on_progress=None, plan_lines=1,
    )
    closure.release()
    assert review.error and [row["role"] for row in attempts] == ["correction"]
    assert_five_headings(review.text)
    assert "CLASS-REGISTER:" in trailer
    assert "STATE-UNAVAILABLE" in trailer
    assert (cc.lineage_dir(tmp_path) / "save-fail.pending").exists()
    cc.clear_latch(tmp_path, "save-fail")


def test_staged_format_debt_save_failure_also_retains_latch(tmp_path, monkeypatch):
    cc.save_lineage(tmp_path, cc.Lineage("format-save-fail", mode=cc.PLAN_MODE))
    closure = handlers._PlanClassClosure(
        "format-save-fail", round_no=1, state_root=tmp_path, stamp="T",
    )
    closure.prepare()
    monkeypatch.setattr(
        cc, "save_lineage",
        lambda *args, **kwargs: (_ for _ in ()).throw(cc.StateUnavailable("ambiguous write")),
    )
    review, trailer, attempts = handlers._settle_staged_failure(
        closure, stakes="s", snapshot="p", error=rc.CensusError("bad format"),
        mode=cc.PLAN_MODE,
    )
    closure.release()
    assert review.error and attempts == []
    assert_five_headings(review.text)
    assert "CLASS-REGISTER: staged rejected; failure state persistence unavailable" in trailer
    assert "STATE-UNAVAILABLE" in trailer
    assert (cc.lineage_dir(tmp_path) / "format-save-fail.pending").exists()
    cc.clear_latch(tmp_path, "format-save-fail")


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
            text = rc.SETTLEMENT_MARKER + "\n" + json.dumps({
                "role":"census", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":[], "class_dispositions":[], "class_records":[],
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
    (repo / "app.py").write_text("changed = True\n")
    out = handlers.critique_plan({
        "plan_text":"# Plan\n\nDo it.", "repo_path":str(repo), "lineage":"structural-only",
        "round":2, "claim_verification":False, "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs")
    assert len(calls) == 8
    assert "STRUCTURAL-PHASE: clear" in out


def test_disabled_claims_do_not_gate_or_render_stale_claim_debt(tmp_path):
    claim_state = pc.with_debt(
        pc.empty_state(), pc.AuditError("stale external debt"), round_no=1,
        plan_text="# Plan\n",
    )
    cc.save_lineage(
        tmp_path,
        cc.Lineage(
            "dormant-claims", mode=cc.PLAN_MODE, claim_state=claim_state,
            review_state=rc.normalize_state({}, stakes="s", snapshot="p"),
        ),
    )
    closure = handlers._PlanClassClosure(
        "dormant-claims", round_no=1, state_root=tmp_path, stamp="T",
    )
    closure.prepare()
    closure.claims_enabled = False

    class Engine:
        name = "fake"

        def run(self, prompt, *args, **kwargs):
            if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
                lane_name = next(
                    row.split()[-1] for row in prompt.splitlines()
                    if row.startswith("ROLE: census lane")
                )
                text = lane(lane_name)
            else:
                text = wire(rc.SETTLEMENT_MARKER, {
                    "role":"census", "source_dispositions":[],
                    "assessment_dispositions":[], "findings":[], "debt":[],
                    "debt_updates":[], "class_dispositions":[], "class_records":[],
                })
            return Review(text=text, session_ref="s", raw=text)

    _, trailer, _ = handlers._staged_structural_review(
        engine=Engine(), cwd=tmp_path, model="m", effort="high", mode=cc.PLAN_MODE,
        body="artifact", closure=closure, stakes="s", snapshot="p", round_no=1,
        on_progress=None, plan_lines=1,
    )
    closure.release()
    assert "STRUCTURAL-PHASE: clear" in trailer
    assert "CLAIM-" not in trailer


def test_unknown_legacy_calibration_preserves_disabled_claims_and_reverifies_on_enable(
    repo, tmp_path, monkeypatch,
):
    claim_state = pc.empty_state()
    claim_state["claims"] = {"C1": {"scope":"external"}}
    lineage = cc.Lineage(
        "legacy-calibration", rounds=2, mode=cc.PLAN_MODE,
        claim_state=claim_state, review_state={},
        classes={
            "old": cc.TrackedClass(
                "old", "inspect the invariant", "MAJOR", 1, cc.CLOSED,
                procedure="inspect it",
            ),
        },
    )
    cc.save_lineage(cc.default_state_root(), lineage)
    observed = {}

    def staged(**kwargs):
        closure = kwargs["closure"]
        observed["claims"] = dict(closure.lineage.claim_state["claims"])
        observed["status"] = closure.lineage.classes["old"].status
        observed["reverify"] = closure.lineage.claim_reverify_required
        closure.lineage.review_state = rc.normalize_state(
            closure.lineage.review_state, stakes=kwargs["stakes"],
            snapshot=kwargs["snapshot"],
        )
        cc.save_lineage(closure.state_root, closure.lineage)
        closure._settled = True
        review = Review(text="ok", session_ref="s", raw="ok")
        return review, "CONVERGENCE: BLOCKED — test", []

    monkeypatch.setattr(handlers, "_staged_structural_review", staged)
    handlers.critique_plan({
        "plan_text":"# Plan\n\nDo it.", "repo_path":str(repo),
        "lineage":"legacy-calibration", "round":3,
        "claim_verification":False, "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs")
    assert observed == {
        "claims": {"C1": {"scope":"external"}},
        "status": cc.OPEN, "reverify": True,
    }
    preserved = cc.load_lineage(
        cc.default_state_root(), "legacy-calibration", stamp="later", mode=cc.PLAN_MODE,
    )
    assert preserved.claim_state == claim_state
    assert preserved.claim_reverify_required is True

    verify = {}

    def verify_claims(plan_text, prior_state, **kwargs):
        verify["prior"] = prior_state
        verify["force"] = kwargs["force_exhaustive"]
        return prior_state, "parsed 1 full current packet"

    monkeypatch.setattr(handlers, "_verify_plan_claims", verify_claims)
    monkeypatch.setattr(handlers.inert_git, "require_supported_version", lambda: None)
    monkeypatch.setattr(handlers.eng, "require_evidence_profile", lambda engine: None)
    handlers.critique_plan({
        "plan_text":"# Plan\n\nDo it.", "repo_path":str(repo),
        "lineage":"legacy-calibration", "round":4,
        "claim_verification":True, "web_search":True,
        "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs")
    assert verify == {"prior": claim_state, "force": True}
    refreshed = cc.load_lineage(
        cc.default_state_root(), "legacy-calibration", stamp="later", mode=cc.PLAN_MODE,
    )
    assert refreshed.claim_state == claim_state
    assert refreshed.claim_reverify_required is False


def test_plan_handler_runs_census_correction_and_cold_final(repo, tmp_path, monkeypatch):
    calls = []

    def run(self, prompt, *args, **kwargs):
        calls.append(prompt)
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            findings = ([{
                "id":"F1", "severity":"MAJOR", "summary":"repair the plan",
                "evidence":["plan:1"], "remedy":"edit the plan",
            }] if lane_name == "domain" else [])
            text = lane(lane_name, findings=findings)
        elif prompts.STAGED_CONSOLIDATION_INSTRUCTIONS.splitlines()[0] in prompt:
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"census",
                "source_dispositions":[{"source_id":"domain:F1","governing_id":"G1"}],
                "assessment_dispositions":[],
                "findings":[{
                    "id":"G1", "severity":"MAJOR", "summary":"repair the plan",
                    "evidence":["plan:1"], "remedy":"edit the plan",
                }],
                "debt":[{"id":"D1", "finding_id":"G1", "status":"open"}],
                "debt_updates":[],
                "class_dispositions":[{
                    "finding_id":"G1", "kind":"one_off", "reason":"unique plan edit",
                }],
                "class_records":[],
            })
        elif '"role": "correction"' in prompt:
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"correction", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                    "debt_updates":[{"id":"D1","status":"closed","evidence":["plan:1"]}],
                    "class_dispositions":[], "class_assessments":[],
                "class_records":[],
            })
        else:
            assert '"role": "final"' in prompt
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"final", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":[], "class_dispositions":[], "class_records":[],
                "coverage": payload(lane())["coverage"], "class_assessments":[],
            })
        return Review(text=text, session_ref=f"s{len(calls)}", raw=text)

    monkeypatch.setattr(handlers.eng.CodexEngine, "run", run)
    args = {
        "plan_text":"# Plan\n\nDo it.", "repo_path":str(repo),
        "lineage":"three-phase-plan", "claim_verification":False,
        "stakes":"trusted local tool",
    }
    first = handlers.critique_plan(
        {**args, "round":1}, engine=handlers.eng.CodexEngine(),
        log_dir=tmp_path / "logs", now=lambda: "T1",
    )
    second = handlers.critique_plan(
        {**args, "round":2}, engine=handlers.eng.CodexEngine(),
        log_dir=tmp_path / "logs", now=lambda: "T2",
    )
    third = handlers.critique_plan(
        {**args, "round":3}, engine=handlers.eng.CodexEngine(),
        log_dir=tmp_path / "logs", now=lambda: "T3",
    )

    assert "STRUCTURAL-PHASE: correction" in first
    assert "CLASS-REGISTER: staged census parsed" in first
    assert "CLASS-CLOSURE: 0 open, 0 closed" in first
    assert "STRUCTURAL-PHASE: final" in second
    assert "STRUCTURAL-PHASE: clear" in third
    assert "CONVERGENCE: NOT-BLOCKED" in third
    assert len(calls) == 6
    assert '"existing_debt": []' in calls[5]
    assert all(key in calls[5] for key in rc.CHECKLIST)
    assert '"finding_ids"' in calls[5] and '"class_assessments"' in calls[5]
    assert third.count("## What works") == 1
    audit = json.loads(next((tmp_path / "logs").glob("T1-critique_plan-*.json")).read_text())
    assert len(audit["staged_manifests"]) == 3
    assert audit["staged_settlement"]["source_dispositions"] == [
        {"source_id":"domain:F1", "governing_id":"G1"},
    ]
    domain = next(row for row in audit["staged_manifests"] if row["lane"] == "domain")
    assert domain["coverage"][0]["finding_ids"] == ["domain:F1"]
    rows = audit["attempt_ledger"]
    assert {row["role"] for row in rows[:3]} == {
        "census-domain", "census-execution", "census-integrity",
    }
    assert rows[3]["role"] == "consolidation"
    assert [row["sequence"] for row in rows] == [1, 2, 3, 4]
    lineage = cc.load_lineage(
        cc.default_state_root(), "three-phase-plan", stamp="T4", mode=cc.PLAN_MODE,
    )
    assert lineage.review_state["debt"][0]["source_ids"] == ["domain:F1"]
    second_audit = json.loads(next((tmp_path / "logs").glob("T2-critique_plan-*.json")).read_text())
    third_audit = json.loads(next((tmp_path / "logs").glob("T3-critique_plan-*.json")).read_text())
    assert [row["role"] for row in second_audit["attempt_ledger"]] == ["correction"]
    assert [row["role"] for row in third_audit["attempt_ledger"]] == ["final"]


def test_branch_reuses_complete_census_after_settlement_rejection(
    repo_with_branch, tmp_path, monkeypatch,
):
    calls: list[str] = []
    accept_settlement = False

    def invalid_settlement():
        return wire(rc.SETTLEMENT_MARKER, {"role":"census"})

    def valid_settlement():
        return wire(rc.SETTLEMENT_MARKER, {
            "role":"census", "source_dispositions":[],
            "assessment_dispositions":[], "findings":[], "debt":[],
            "debt_updates":[], "class_dispositions":[], "class_records":[],
        })

    def run(self, prompt, *args, **kwargs):
        nonlocal accept_settlement
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            calls.append(f"lane:{lane_name}")
            value = payload(lane(lane_name))
            for row in value["coverage"]:
                row["evidence"] = ["repository/README.md:1"]
            text = wire(rc.LANE_MARKER, value)
        else:
            calls.append("consolidation")
            text = valid_settlement() if accept_settlement else invalid_settlement()
        return Review(text=text, session_ref="cache-session", raw=text)

    def resume(self, *args, **kwargs):
        calls.append("consolidation-retry")
        text = invalid_settlement()
        return Review(text=text, session_ref="cache-session", raw=text)

    monkeypatch.setattr(handlers.eng.CodexEngine, "run", run)
    monkeypatch.setattr(handlers.eng.CodexEngine, "resume", resume)
    args = {
        "repo_path":str(repo_with_branch), "base_ref":"main", "head_ref":"feature",
        "lineage":"cached-census-branch", "stakes":"trusted local tool",
    }
    first = handlers.critique_branch(
        {**args, "round":1}, engine=handlers.eng.CodexEngine(),
        log_dir=tmp_path / "logs", now=lambda: "C1",
    )
    assert "STRUCTURAL-ERROR" in first
    assert "CONVERGENCE: BLOCKED — staged validation debt remains open." in first
    lineage = cc.load_lineage(
        cc.default_state_root(), "cached-census-branch", stamp="C2",
        mode=cc.BRANCH_MODE,
    )
    assert len(lineage.review_state["census_cache"]["manifests"]) == 3
    assert "validation_debt" in lineage.review_state
    assert "staged_failure" not in lineage.review_state
    assert calls.count("consolidation") == 1
    assert sum(call.startswith("lane:") for call in calls) == 3

    accept_settlement = True
    second = handlers.critique_branch(
        {**args, "round":2}, engine=handlers.eng.CodexEngine(),
        log_dir=tmp_path / "logs", now=lambda: "C2",
    )
    assert "CONVERGENCE: NOT-BLOCKED" in second
    assert calls.count("consolidation") == 2
    assert sum(call.startswith("lane:") for call in calls) == 3
    lineage = cc.load_lineage(
        cc.default_state_root(), "cached-census-branch", stamp="C3",
        mode=cc.BRANCH_MODE,
    )
    assert "census_cache" not in lineage.review_state
    audit = json.loads(next((tmp_path / "logs").glob("C2-critique_branch-*.json")).read_text())
    assert [row["role"] for row in audit["attempt_ledger"]] == ["consolidation"]


def test_branch_codex_runs_the_staged_census_path(
    repo_with_branch, tmp_path, monkeypatch,
):
    calls = []
    web_flags = []

    def run(self, prompt, *args, **kwargs):
        calls.append(prompt)
        web_flags.append(args[3])
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            value = payload(lane(lane_name))
            for row in value["coverage"]:
                row["evidence"] = ["repository/README.md:1"]
            text = wire(rc.LANE_MARKER, value)
        else:
            debt_updates = []
            if '"id": "legacy-register"' in prompt:
                debt_updates = [{
                    "id":"legacy-register", "status":"closed",
                    "evidence":["repository/README.md:1"],
                }]
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"census", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":debt_updates, "class_dispositions":[], "class_records":[],
            })
        return Review(text=text, session_ref="branch-session", raw=text)

    monkeypatch.setattr(handlers.eng.CodexEngine, "run", run)
    result = handlers.critique_branch({
        "repo_path": str(repo_with_branch),
        "base_ref": "main",
        "head_ref": "feature",
        "lineage": "staged-branch",
        "round": 1,
        "stakes": "trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs", now=lambda: "B1")

    assert len(calls) == 4
    assert web_flags == [True] * 4
    assert sum(prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in call for call in calls) == 3
    assert all("Follow the blast radius" in call for call in calls[:3])
    assert "STRUCTURAL-PHASE: clear" in result
    audit = json.loads(next((tmp_path / "logs").glob("B1-critique_branch-*.json")).read_text())
    assert len(audit["staged_manifests"]) == 3
    lineage = cc.load_lineage(
        cc.default_state_root(), "staged-branch", stamp="B2", mode=cc.BRANCH_MODE,
    )
    assert len(lineage.review_state["snapshot_digest"]) == 64
    assert lineage.review_state["snapshot_digest"] != audit["head_id"]
    assert audit["base_id"] not in lineage.review_state["snapshot_digest"]

    lineage.debt = {"round":0, "reason":"legacy register was malformed"}
    cc.save_lineage(cc.default_state_root(), lineage)
    calls.clear(); web_flags.clear()
    result = handlers.critique_branch({
        "repo_path":str(repo_with_branch), "base_ref":"main", "head_ref":"feature",
        "lineage":"staged-branch", "round":2, "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs", now=lambda: "B2")
    assert len(calls) == 4
    assert "CONVERGENCE: NOT-BLOCKED" in result
    migrated = cc.load_lineage(
        cc.default_state_root(), "staged-branch", stamp="B3", mode=cc.BRANCH_MODE,
    )
    assert migrated.debt is None
    assert not [d for d in migrated.review_state["debt"] if d["status"] == "open"]

    subprocess.run(
        ["git", "checkout", "-q", "-b", "moved-base", "main"],
        cwd=repo_with_branch, check=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL":"/dev/null", "GIT_CONFIG_SYSTEM":"/dev/null"},
    )
    (repo_with_branch / "base-only.txt").write_text("changed base endpoint\n")
    subprocess.run(["git", "add", "base-only.txt"], cwd=repo_with_branch, check=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", "commit", "-qm", "move base"],
        cwd=repo_with_branch, check=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL":"/dev/null", "GIT_CONFIG_SYSTEM":"/dev/null"},
    )
    calls.clear(); web_flags.clear()
    result = handlers.critique_branch({
        "repo_path":str(repo_with_branch), "base_ref":"moved-base", "head_ref":"feature",
        "lineage":"staged-branch", "round":3, "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs", now=lambda: "B3")
    assert len(calls) == 4
    assert "CONVERGENCE: NOT-BLOCKED" in result


def test_branch_settlement_persists_a_new_procedure_class(
    repo_with_branch, tmp_path, monkeypatch,
):
    def run(self, prompt, *args, **kwargs):
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            value = payload(lane(lane_name))
            for row in value["coverage"]:
                row["evidence"] = ["repository/README.md:1"]
        else:
            value = {
                "role":"census", "source_dispositions":[],
                "assessment_dispositions":[],
                "findings":[{
                    "id":"G1", "severity":"MAJOR",
                    "summary":"transition ownership is inconsistent",
                    "evidence":["repository/README.md:1"],
                    "remedy":"make transition ownership consistent",
                }],
                "debt":[{"id":"D1", "finding_id":"G1", "status":"open"}],
                "debt_updates":[],
                "class_dispositions":[{
                    "finding_id":"G1", "kind":"new_class", "record_index":0,
                }],
                "class_records":[{
                    "op":"new", "invariant":"semantic transition ownership",
                    "severity":"MAJOR", "procedure":"inspect every transition owner",
                }],
            }
        text = wire(
            rc.LANE_MARKER if "lane" in value else rc.SETTLEMENT_MARKER, value,
        )
        return Review(text=text, session_ref="branch-session", raw=text)

    monkeypatch.setattr(handlers.eng.CodexEngine, "run", run)
    result = handlers.critique_branch({
        "repo_path":str(repo_with_branch), "base_ref":"main", "head_ref":"feature",
        "lineage":"procedure-branch", "round":1, "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs", now=lambda: "P1")
    assert "CONVERGENCE: BLOCKED" in result
    assert "CLASS-REGISTER: staged census parsed" in result
    assert "CLASS-CLOSURE: 1 open, 0 closed" in result
    lineage = cc.load_lineage(
        cc.default_state_root(), "procedure-branch", stamp="P2", mode=cc.BRANCH_MODE,
    )
    classes = lineage.active()
    assert len(classes) == 1
    assert classes[0].procedure == "inspect every transition owner"
    assert not classes[0].mechanized
    assert lineage.review_state["debt"][0]["class_ids"] == [classes[0].class_id]


def test_staged_replace_transfers_debt_to_successor_and_stays_in_correction(tmp_path):
    (tmp_path / "a.py").write_text("broken\n")
    state = rc.normalize_state({}, stakes="s", snapshot="p")
    state["phase"] = "final"
    state["debt"] = [{
        "id":"historic", "finding_id":"historic", "status":"closed",
        "severity":"MAJOR", "summary":"past occurrence", "evidence":["repository/a.py:1"],
        "remedy":"already fixed", "source_ids":[], "class_ids":["abc"],
        "first_round":1, "last_round":1,
    }]
    lineage = cc.Lineage("replace-binding", classes={
        "abc":cc.TrackedClass(
            "abc", "old invariant", "MAJOR", 1, cc.CLOSED,
            procedure="inspect old behavior",
        ),
    }, next_seq=2, mode=cc.BRANCH_MODE, review_state=state)

    class Closure:
        state_root = tmp_path
        unavailable = None
        claims_enabled = False
        staged_settlement = None
        register_status = None
        _settled = False

        def __init__(self):
            self.lineage = lineage

        def _blocks(self):
            return []

        def _sweep(self, only=None):
            return None

    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            findings = [finding("G1", "MAJOR")]
            coverage = payload(lane(findings=findings))["coverage"]
            findings[0]["evidence"] = ["repository/a.py:1"]
            for row in coverage:
                row["evidence"] = ["repository/a.py:1"]
            value = {
                "role":"final", "source_dispositions":[],
                "assessment_dispositions":[{"assessment_id":"abc", "governing_id":"G1"}],
                "findings":findings,
                "debt":[{"id":"D1", "finding_id":"G1", "status":"open"}],
                "debt_updates":[],
                "class_dispositions":[{
                    "finding_id":"G1", "kind":"existing_class", "class_id":"abc",
                }],
                "class_records":[{
                    "op":"replace", "class_id":"abc", "invariant":"new invariant",
                    "severity":"MAJOR", "procedure":"inspect new behavior",
                }],
                "coverage":coverage,
                "class_assessments":[{
                    "class_id":"abc", "verdict":"violated",
                    "evidence":["repository/a.py:1"],
                    "finding_id":"G1",
                }],
            }
            text = wire(rc.SETTLEMENT_MARKER, value)
            return Review(text=text, session_ref="s", raw=text)

    closure = Closure()
    _, trailer, _ = handlers._staged_structural_review(
        engine=Engine(), cwd=tmp_path, model="m", effort="high", mode=cc.BRANCH_MODE,
        body="artifact", closure=closure, stakes="s", snapshot="p", round_no=2,
        on_progress=None,
    )
    successor = lineage.classes["abc"].superseded_by
    assert successor
    current = next(d for d in lineage.review_state["debt"] if d["id"] == "D1")
    assert current["class_ids"] == [successor]
    historic = next(d for d in lineage.review_state["debt"] if d["id"] == "historic")
    assert historic["class_ids"] == ["abc"]
    assert lineage.review_state["phase"] == "correction"
    assert "STRUCTURAL-PHASE: correction" in trailer


def test_unbound_mechanized_class_uses_match_dict_evidence_without_crashing(tmp_path):
    (tmp_path / "a.py").write_text("BAD\n")
    state = rc.normalize_state({}, stakes="s", snapshot="p")
    state["phase"] = "correction"
    state["debt"] = [{
        "id":"D0", "finding_id":"G0", "status":"open", "severity":"MAJOR",
        "summary":"repair another defect", "evidence":["repository/a.py:1"],
        "remedy":"repair it", "source_ids":[], "class_ids":[],
        "first_round":1, "last_round":1,
    }]
    tracked = cc.TrackedClass(
        "abc", "no BAD tokens", "MAJOR", 1, cc.OPEN,
        pattern="BAD", pathspec="*.py",
        matches=(
            {"path":"a.py", "line":1, "text":"BAD"},
            {"path":"blob.bin", "line":0, "text":"", "binary":True},
        ),
    )
    lineage = cc.Lineage(
        "unbound-match", classes={"abc":tracked}, next_seq=2,
        mode=cc.BRANCH_MODE, review_state=state,
    )

    class Closure:
        state_root = tmp_path
        unavailable = None
        claims_enabled = False
        staged_settlement = None
        register_status = None
        _settled = False

        def __init__(self):
            self.lineage = lineage

        def _blocks(self):
            return []

        def _sweep(self, only=None):
            return None

    class Engine:
        name = "fake"

        def run(self, *args, **kwargs):
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"correction", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":[{
                    "id":"D0", "status":"closed", "evidence":["repository/a.py:1"],
                }],
                "class_dispositions":[], "class_records":[],
                "class_assessments":[],
            })
            return Review(text=text, session_ref="s", raw=text)

    closure = Closure()
    review, trailer, _ = handlers._staged_structural_review(
        engine=Engine(), cwd=tmp_path, model="m", effort="high", mode=cc.BRANCH_MODE,
        body="artifact", closure=closure, stakes="s", snapshot="p", round_no=2,
        on_progress=None,
    )
    assert not review.error
    assert lineage.review_state["unbound_class_ids"] == ["abc"]
    assert "abc no BAD tokens" in trailer
    assert "2 match(es)" in trailer
    assert "a.py:1: BAD" in trailer
    assert "blob.bin: binary match (line not shown)" in trailer
    assert "blob.bin:0" not in trailer
    assert "STRUCTURAL-DEBT: 0 blocking open" in trailer
    assert "class closure remains open" in trailer
    assert "CONVERGENCE: BLOCKED" in trailer
