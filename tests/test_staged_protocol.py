import json

import pytest
from jsonschema import Draft202012Validator

from paranoia_local import class_closure as cc
from paranoia_local import review_census as rc
from paranoia_local import staged_protocol as sp


def coverage(*finding_ids: str, anchor: str = "plan:1"):
    rows = [
        {
            "id": item,
            "status": "covered",
            "summary": "checked",
            "evidence": [anchor],
            "finding_ids": [],
        }
        for item in sp.CHECKLIST
    ]
    if finding_ids:
        rows[0].update(status="finding", finding_ids=list(finding_ids))
    return rows


def lane_value(lane="domain", *, findings=None, assessments=None):
    findings = findings or []
    return {
        "lane": lane,
        "coverage": coverage(*(row["id"] for row in findings)),
        "findings": findings,
        "class_assessments": assessments or [],
    }


def finding(fid="G1", severity="MAJOR", *, classification=None, source_ids=None):
    value = {
        "id": fid,
        "severity": severity,
        "summary": "reachable defect",
        "evidence": ["plan:1"],
        "remedy": "repair the reachable path",
        "classification": classification or {
            "kind": "one_off", "reason": "this fixture has one site",
        },
    }
    if source_ids is not None:
        value["source_ids"] = source_ids
    return value


def decision(role="census", **overrides):
    value = {
        "role": role,
        "governing_findings": [],
        "debt_outcomes": [],
        "class_outcomes": [],
        "class_actions": [],
    }
    if role == "final":
        value["coverage"] = coverage()
    value.update(overrides)
    return value


def active_class(
    cid="class-a", *, severity="MAJOR", status=cc.OPEN, mechanized=False,
):
    return {
        "class_id": cid,
        "invariant": "the recurring invariant",
        "severity": severity,
        "status": status,
        "mechanized": mechanized,
        "pattern": "BAD" if mechanized else None,
        "pathspec": "*.py" if mechanized else None,
        "procedure": None if mechanized else "inspect the recurring path",
    }


def durable_debt(
    debt_id="D7", *, cid="class-a", severity="MAJOR", status="open",
    finding_id="old-finding",
):
    return {
        "id": debt_id,
        "finding_id": finding_id,
        "status": status,
        "severity": severity,
        "summary": "historic occurrence",
        "evidence": ["plan:1"],
        "remedy": "repair it",
        "source_ids": [],
        "class_ids": [cid] if cid else [],
        "first_round": 1,
        "last_round": 1,
    }


def materialize(value, **kwargs):
    return sp.materialize_decision(
        json.dumps(value), mode=kwargs.pop("mode", cc.PLAN_MODE),
        role=value["role"], **kwargs,
    )


@pytest.mark.parametrize(
    ("text", "lines", "rendered"),
    [
        ("", (), ""),
        ("one", ("one",), "00001: one"),
        ("one\n", ("one",), "00001: one"),
        ("one\n\nthree", ("one", "", "three"), "00001: one\n00002: \n00003: three"),
        ("λ\r\nβ", ("λ", "β"), "00001: λ\n00002: β"),
    ],
)
def test_artifact_view_has_one_coordinate_source(text, lines, rendered):
    view = sp.ArtifactView.from_text(text)
    assert view.original == text
    assert view.lines == lines
    assert view.rendered == rendered
    assert view.line_count == len(lines)


def test_artifact_view_line_count_is_the_resolver_bound(tmp_path):
    view = sp.ArtifactView.from_text("one\n\nthree")
    rc.resolve_anchors({"evidence": ["plan:1-3"]}, root=tmp_path, plan_lines=view.line_count)
    with pytest.raises(rc.CensusError, match="unresolvable plan"):
        rc.resolve_anchors({"evidence": ["plan:1-4"]}, root=tmp_path, plan_lines=view.line_count)


def test_every_role_schema_is_closed_and_draft_valid():
    schemas = [
        *(sp.lane_schema(mode, lane) for mode, lanes in sp.LANES.items() for lane in lanes),
        *(sp.decision_schema(mode, role) for mode in sp.LANES for role in ("census", "correction", "final")),
    ]
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def test_role_schemas_reject_cross_role_payloads():
    for role in ("census", "correction", "final"):
        raw = decision(role)
        for other in ("census", "correction", "final"):
            issues = list(Draft202012Validator(sp.decision_schema("plan", other)).iter_errors(raw))
            assert bool(issues) is (role != other)


def test_provider_projection_only_removes_unsupported_uniqueness():
    full = sp.lane_schema("plan", "domain")
    projected = sp.provider_schema(full)
    assert "uniqueItems" in sp.canonical_schema(full)
    assert '"$schema"' in sp.canonical_schema(full)
    assert "uniqueItems" not in sp.canonical_schema(projected)
    assert '"$schema"' not in sp.canonical_schema(projected)
    assert projected["properties"]["coverage"]["maxItems"] == len(sp.CHECKLIST)
    assert projected["additionalProperties"] is False


def test_schema_error_names_json_pointer_and_does_not_accept_alias():
    value = decision("census", governing_findings=[
        finding(source_ids=["domain:F1"], classification={
            "disposition": "one_off", "reason": "one site",
        })
    ])
    with pytest.raises(sp.ProtocolError) as caught:
        materialize(value, source_ids=["domain:F1"])
    message = str(caught.value)
    assert "/governing_findings/0/classification" in message
    assert "disposition" in message


@pytest.mark.parametrize(
    ("anchor", "valid"),
    [
        ("plan:2", True),
        ("plan:2-4", True),
        ("repository/my-file.py:12", True),
        ("repository/path:with-colon.py:12-14", True),
        ("a.py:2", False),
        ("plan:0", False),
        ("plan:2-", False),
        ("The files are at repository/a.py:1 and repository/b.py:2.", False),
    ],
)
def test_provider_schema_constrains_each_evidence_item_to_one_anchor(anchor, valid):
    value = lane_value()
    value["coverage"][0]["evidence"] = [anchor]
    issues = list(Draft202012Validator(sp.lane_schema("plan", "domain")).iter_errors(value))
    assert (not issues) is valid


def test_lane_dynamic_completeness_and_binding():
    value = lane_value()
    value["coverage"].pop()
    with pytest.raises(sp.ProtocolError, match="/coverage"):
        sp.parse_lane(json.dumps(value), mode="plan", lane="domain")

    value = lane_value(findings=[{
        "id": "F1", "severity": "MAJOR", "summary": "broken",
        "evidence": ["plan:1"], "remedy": "fix",
    }])
    value["coverage"][0].update(status="covered", finding_ids=[])
    with pytest.raises(sp.ProtocolError, match="bound to coverage"):
        sp.parse_lane(json.dumps(value), mode="plan", lane="domain")


def test_census_materializes_one_off_and_canonical_debt_id():
    value = decision("census", governing_findings=[
        finding(source_ids=["domain:F1"]),
    ])
    parsed = materialize(
        value, source_ids=["domain:F1"], source_severities={"domain:F1": "MAJOR"},
        durable_debt=[durable_debt("D1", status="closed")],
    )
    assert parsed["source_dispositions"] == [
        {"source_id": "domain:F1", "governing_id": "G1"},
    ]
    assert parsed["debt"][0]["id"] == "D2"
    assert parsed["class_dispositions"][0]["kind"] == "one_off"


def test_source_severity_cannot_be_downgraded():
    value = decision("census", governing_findings=[
        finding(severity="MINOR", source_ids=["domain:F1"]),
    ])
    with pytest.raises(sp.ProtocolError, match="cannot downgrade"):
        materialize(
            value, source_ids=["domain:F1"],
            source_severities={"domain:F1": "MAJOR"},
        )


def test_census_existing_advisory_violation_still_mints_debt():
    cls = active_class(severity="OUT-OF-SCOPE")
    value = decision(
        "census",
        governing_findings=[finding(
            severity="OUT-OF-SCOPE", source_ids=["integrity:F1"],
            classification={"kind": "existing_class", "class_id": "class-a"},
        )],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "new_finding", "finding_id": "G1"},
        }],
    )
    parsed = materialize(
        value, source_ids=["integrity:F1"],
        source_severities={"integrity:F1": "OUT-OF-SCOPE"},
        assessment_verdicts={"class-a": "violated"},
        assessment_findings={"class-a": "integrity:F1"},
        active_classes=[cls],
    )
    assert parsed["debt"] == [{
        "id": "D1", "finding_id": "G1", "status": "open",
        "severity": "OUT-OF-SCOPE", "summary": "reachable defect",
        "evidence": ["plan:1"], "remedy": "repair the reachable path",
    }]
    state = rc.settle_state(
        rc.normalize_state({}, stakes="s", snapshot="p"), parsed,
        phase="census", snapshot="p", round_no=1,
    )
    assert state["debt"][0]["class_ids"] == ["class-a"]
    assert state["phase"] == "clear"


def test_new_class_keeps_independent_severity_and_record_binding():
    value = decision("census", governing_findings=[finding(
        severity="MAJOR", source_ids=["domain:F1"],
        classification={
            "kind": "new_class",
            "definition": {
                "invariant": "all copies preserve identity",
                "severity": "BLOCKER",
                "procedure": "inspect every copied identity",
            },
        },
    )])
    parsed = materialize(
        value, source_ids=["domain:F1"], source_severities={"domain:F1": "MAJOR"},
    )
    assert parsed["findings"][0]["severity"] == "MAJOR"
    assert parsed["class_records"] == [{
        "op": "new", "invariant": "all copies preserve identity",
        "severity": "BLOCKER", "procedure": "inspect every copied identity",
    }]
    assert parsed["debt"][0]["id"] == "D1"
    assert parsed["class_dispositions"][0]["record_index"] == 0


def test_branch_supports_pattern_and_procedure_definitions():
    for definition in (
        {
            "invariant": "no BAD token", "severity": "MAJOR",
            "pattern": "BAD", "pathspec": "*.py",
        },
        {
            "invariant": "manual invariant", "severity": "MAJOR",
            "procedure": "inspect the transition owner",
        },
    ):
        value = decision("census", governing_findings=[finding(
            source_ids=["behaviour:F1"],
            classification={"kind": "new_class", "definition": definition},
        )])
        parsed = materialize(
            value, mode="branch", source_ids=["behaviour:F1"],
            source_severities={"behaviour:F1": "MAJOR"},
        )
        rc.register_from_records(parsed["class_records"], mechanized=None)


def test_carried_debt_preserves_one_identity_without_minting():
    debts = [durable_debt("D7", finding_id="old-7"), durable_debt("D8", finding_id="old-8")]
    value = decision(
        "correction",
        debt_outcomes=[
            {"debt_id": "D7", "status": "open", "evidence": ["plan:1"], "reason": "still reachable"},
            {"debt_id": "D8", "status": "open", "evidence": ["plan:1"], "reason": "also reachable"},
        ],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "carried_debt", "debt_id": "D7"},
        }],
    )
    parsed = materialize(value, active_classes=[active_class()], durable_debt=debts)
    assert parsed["debt"] == []
    assert parsed["class_assessments"][0]["finding_id"] == "old-7"
    assert {row["id"] for row in parsed["debt_updates"]} == {"D7", "D8"}


def test_carried_debt_must_remain_open_and_bind_the_class():
    value = decision(
        "correction",
        debt_outcomes=[{"debt_id": "D7", "status": "closed", "evidence": ["plan:1"]}],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "carried_debt", "debt_id": "D7"},
        }],
    )
    with pytest.raises(sp.ProtocolError, match="must remain open"):
        materialize(
            value, active_classes=[active_class()], durable_debt=[durable_debt()],
        )


def test_open_class_bound_debt_needs_at_least_one_violated_bound_class():
    value = decision(
        "correction",
        debt_outcomes=[{
            "debt_id": "D7", "status": "open", "evidence": ["plan:1"],
            "reason": "claimed open",
        }],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "satisfied", "evidence": ["plan:1"],
        }],
    )
    with pytest.raises(sp.ProtocolError, match="needs a violated class"):
        materialize(value, active_classes=[active_class()], durable_debt=[durable_debt()])


def test_satisfied_open_unmechanized_class_derives_close():
    value = decision(
        "final", coverage=coverage(),
        class_outcomes=[{
            "class_id": "class-a", "verdict": "satisfied", "evidence": ["plan:1"],
        }],
    )
    parsed = materialize(value, active_classes=[active_class()])
    assert parsed["class_records"] == [{"op": "close", "class_id": "class-a"}]


def test_satisfied_open_mechanized_class_cannot_be_model_closed():
    value = decision(
        "final", coverage=coverage(),
        class_outcomes=[{
            "class_id": "class-a", "verdict": "satisfied", "evidence": ["plan:1"],
        }],
    )
    with pytest.raises(sp.ProtocolError, match="mechanized open class"):
        materialize(value, active_classes=[active_class(mechanized=True)])


@pytest.mark.parametrize("kind", ["reclassify", "replace"])
def test_class_action_cannot_downgrade(kind):
    action = {
        "kind": kind, "class_id": "class-a",
        **(
            {"severity": "MINOR"}
            if kind == "reclassify"
            else {"definition": {
                "invariant": "replacement", "severity": "MINOR",
                "procedure": "inspect replacement",
            }}
        ),
    }
    value = decision("correction", class_actions=[action])
    with pytest.raises(sp.ProtocolError, match="cannot downgrade"):
        materialize(value, active_classes=[active_class()])


def test_closed_violated_class_requires_reopen_or_replace():
    value = decision(
        "final", coverage=coverage("G1"),
        governing_findings=[finding(classification={
            "kind": "existing_class", "class_id": "class-a",
        })],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "new_finding", "finding_id": "G1"},
        }],
    )
    with pytest.raises(sp.ProtocolError, match="closed violated class"):
        materialize(value, active_classes=[active_class(status=cc.CLOSED)])
    value["class_actions"] = [{"kind": "reopen", "class_id": "class-a"}]
    parsed = materialize(value, active_classes=[active_class(status=cc.CLOSED)])
    assert parsed["class_records"] == [{"op": "reopen", "class_id": "class-a"}]


def test_source_fanout_requires_distinct_cited_existing_classes():
    classes = [active_class("class-a"), active_class("class-b")]
    findings = [
        finding(
            fid=f"G{index}", source_ids=["integrity:F1"],
            classification={"kind": "existing_class", "class_id": cls["class_id"]},
        )
        for index, cls in enumerate(classes, 1)
    ]
    outcomes = [
        {
            "class_id": cls["class_id"], "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "new_finding", "finding_id": f"G{index}"},
        }
        for index, cls in enumerate(classes, 1)
    ]
    parsed = materialize(
        decision("census", governing_findings=findings, class_outcomes=outcomes),
        source_ids=["integrity:F1"], source_severities={"integrity:F1": "MAJOR"},
        assessment_verdicts={cls["class_id"]: "violated" for cls in classes},
        assessment_findings={cls["class_id"]: "integrity:F1" for cls in classes},
        active_classes=classes,
    )
    assert len(parsed["debt"]) == 2


def test_final_coverage_binds_every_new_finding():
    value = decision("final", governing_findings=[finding()], coverage=coverage())
    with pytest.raises(sp.ProtocolError, match="bound to coverage"):
        materialize(value)


def test_new_finding_cannot_reuse_durable_finding_identity():
    value = decision("correction", governing_findings=[finding("old-finding")])
    with pytest.raises(sp.ProtocolError, match="reuse durable identities"):
        materialize(value, durable_debt=[durable_debt()])
