import json
from copy import deepcopy

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


def lineage_with_active(cls):
    tracked = cc.TrackedClass(
        class_id=cls["class_id"], invariant=cls["invariant"],
        severity=cls["severity"], first_round=1, status=cls["status"],
        pattern=cls["pattern"], pathspec=cls["pathspec"], procedure=cls["procedure"],
    )
    return cc.Lineage(
        lineage_id="protocol-v2-fixture", mode=cc.BRANCH_MODE,
        classes={tracked.class_id: tracked}, next_seq=2,
    )


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
    assert "(?=" not in sp.canonical_schema(projected)


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
    "mutate",
    [
        lambda value: value["coverage"][0].update(summary="   "),
        lambda value: value["findings"][0].update(summary="\t"),
        lambda value: value["findings"][0].update(remedy="   "),
    ],
)
def test_semantic_strings_require_non_whitespace(mutate):
    value = lane_value(findings=[{
        "id": "F1", "severity": "MAJOR", "summary": "broken",
        "evidence": ["plan:1"], "remedy": "fix",
    }])
    mutate(value)
    with pytest.raises(sp.ProtocolError, match="does not match"):
        sp.parse_lane(json.dumps(value), mode="plan", lane="domain")


def test_role_specific_response_caps_fail_before_json_decode():
    lane_text = "{" + ("x" * sp.MAX_LANE_RESPONSE_CHARS)
    with pytest.raises(sp.ProtocolError, match="response is"):
        sp.parse_lane(lane_text, mode="plan", lane="domain")
    decision_text = "{" + ("x" * sp.MAX_DECISION_RESPONSE_CHARS)
    with pytest.raises(sp.ProtocolError, match="response is"):
        sp.materialize_decision(decision_text, mode="plan", role="census")


@pytest.mark.parametrize("field", ["one_off", "procedure", "open_reason"])
def test_decision_semantic_strings_require_non_whitespace(field):
    if field == "one_off":
        value = decision("census", governing_findings=[finding(
            source_ids=["domain:F1"],
            classification={"kind": "one_off", "reason": "   "},
        )])
    elif field == "procedure":
        value = decision("census", governing_findings=[finding(
            source_ids=["domain:F1"],
            classification={
                "kind": "new_class", "definition": {
                    "invariant": "reusable", "severity": "MAJOR", "procedure": "\t",
                },
            },
        )])
    else:
        value = decision("correction", debt_outcomes=[{
            "debt_id": "D7", "status": "open", "evidence": ["plan:1"],
            "reason": "   ",
        }])
    with pytest.raises(sp.ProtocolError, match="not valid under any"):
        materialize(
            value,
            source_ids=["domain:F1"] if field != "open_reason" else [],
            source_severities={"domain:F1": "MAJOR"},
            durable_debt=[durable_debt(cid=None)] if field == "open_reason" else [],
        )


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


def test_branch_schema_rejects_git_pathspec_magic_for_new_and_replacement_classes():
    bad_definition = {
        "invariant": "no generated files", "severity": "MAJOR",
        "pattern": "BAD", "pathspec": ":(exclude)generated/**",
    }
    census = decision("census", governing_findings=[finding(
        source_ids=["behaviour:F1"],
        classification={"kind": "new_class", "definition": bad_definition},
    )])
    correction = decision("correction", class_actions=[{
        "kind": "replace", "class_id": "class-a", "definition": bad_definition,
    }])
    for value in (census, correction):
        schema = sp.provider_schema(sp.decision_schema("branch", value["role"]))
        assert list(Draft202012Validator(schema).iter_errors(value))
        with pytest.raises(sp.ProtocolError, match="not valid under any"):
            materialize(
                value, mode="branch", source_ids=["behaviour:F1"],
                source_severities={"behaviour:F1": "MAJOR"},
                active_classes=[active_class(mechanized=True)],
            )


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


@pytest.mark.parametrize(
    "action",
    [
        {"kind": "reclassify", "class_id": "class-a", "severity": "BLOCKER"},
        {
            "kind": "replace", "class_id": "class-a",
            "definition": {
                "invariant": "replacement invariant", "severity": "BLOCKER",
                "procedure": "inspect the replacement invariant",
            },
        },
    ],
)
def test_satisfied_open_class_preserves_compatible_standalone_action(action):
    value = decision(
        "correction",
        debt_outcomes=[{
            "debt_id": "D7", "status": "closed", "evidence": ["plan:1"],
        }],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "satisfied", "evidence": ["plan:1"],
        }],
        class_actions=[action],
    )
    parsed = materialize(
        value, active_classes=[active_class()], durable_debt=[durable_debt()],
    )
    assert parsed["class_records"][0]["op"] == action["kind"]
    assert parsed["debt_updates"][0]["status"] == "closed"
    lineage = lineage_with_active(active_class())
    register = rc.register_from_records(parsed["class_records"], mechanized=None)
    minted = cc.apply_register(lineage, register, round_no=2)
    state = rc.settle_state(
        {"phase": "correction", "debt": [durable_debt()]}, parsed,
        phase="correction", snapshot="s", round_no=2,
    )
    assert state["debt"][0]["status"] == "closed"
    if action["kind"] == "reclassify":
        assert lineage.classes["class-a"].severity == "BLOCKER"
        assert minted == []
    else:
        assert lineage.classes["class-a"].status == cc.SUPERSEDED
        assert len(minted) == 1
        assert lineage.classes[minted[0]].procedure == "inspect the replacement invariant"


@pytest.mark.parametrize(("status", "kind", "expected"), [
    (cc.OPEN, "close", cc.CLOSED),
    (cc.CLOSED, "reopen", cc.OPEN),
])
def test_correction_preserves_outcome_independent_standalone_lifecycle(
    status, kind, expected,
):
    active = active_class(status=status)
    parsed = materialize(
        decision("correction", class_actions=[{
            "kind":kind, "class_id":"class-a",
        }]),
        active_classes=[active],
    )
    assert parsed["class_assessments"] == []
    assert parsed["class_records"] == [{"op":kind, "class_id":"class-a"}]
    lineage = lineage_with_active(active)
    cc.apply_register(
        lineage, rc.register_from_records(parsed["class_records"], mechanized=None),
        round_no=2,
    )
    assert lineage.classes["class-a"].status == expected


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


def test_closed_mechanized_class_cannot_be_replaced_by_manual_procedure():
    value = decision(
        "final", coverage=coverage("G1"),
        governing_findings=[finding(classification={
            "kind": "existing_class", "class_id": "class-a",
        })],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "new_finding", "finding_id": "G1"},
        }],
        class_actions=[{
            "kind": "replace", "class_id": "class-a",
            "definition": {
                "invariant": "manual replacement", "severity": "MAJOR",
                "procedure": "inspect manually",
            },
        }],
    )
    with pytest.raises(sp.ProtocolError, match="requires pattern and pathspec"):
        materialize(
            value, mode="branch",
            active_classes=[active_class(status=cc.CLOSED, mechanized=True)],
        )


def test_closed_mechanized_replacement_runs_through_canonical_class_engine():
    cls = active_class(status=cc.CLOSED, mechanized=True)
    value = decision(
        "final", coverage=coverage("G1"),
        governing_findings=[finding(classification={
            "kind": "existing_class", "class_id": "class-a",
        })],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "new_finding", "finding_id": "G1"},
        }],
        class_actions=[{
            "kind": "replace", "class_id": "class-a",
            "definition": {
                "invariant": "corrected predicate", "severity": "MAJOR",
                "pattern": "STILL_BAD", "pathspec": "src/*.py",
            },
        }],
    )
    parsed = materialize(value, mode="branch", active_classes=[cls])
    register = rc.register_from_records(parsed["class_records"], mechanized=None)
    lineage = lineage_with_active(cls)
    minted = cc.apply_register(lineage, register, round_no=2)
    assert lineage.classes["class-a"].status == cc.SUPERSEDED
    assert len(minted) == 1
    successor = lineage.classes[minted[0]]
    assert successor.mechanized
    assert (successor.pattern, successor.pathspec) == ("STILL_BAD", "src/*.py")


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


def test_census_schema_represents_full_three_lane_aggregate_and_fanout():
    findings = [
        finding(
            fid=f"G{index}", source_ids=[f"behaviour:F{index}"],
            classification={"kind": "one_off", "reason": "one source"},
        )
        for index in range(sp.MAX_CENSUS_SOURCES)
    ]
    findings.extend(
        finding(
            fid=f"C{index}", source_ids=["behaviour:F0"],
            classification={"kind": "existing_class", "class_id": f"class-{index}"},
        )
        for index in range(sp.MAX_ACTIVE_CLASSES)
    )
    value = decision("census", governing_findings=findings)
    assert not list(
        Draft202012Validator(sp.decision_schema("branch", "census")).iter_errors(value)
    )
    value["governing_findings"].append(finding(
        fid="overflow", source_ids=["behaviour:F0"],
    ))
    assert list(
        Draft202012Validator(sp.decision_schema("branch", "census")).iter_errors(value)
    )

    source_ids = [f"{sp.LANES[cc.BRANCH_MODE][index % 3]}:F{index}" for index in range(150)]
    aggregate = decision("census", governing_findings=[
        finding(
            fid=f"A{index}", source_ids=[source],
            classification={"kind": "one_off", "reason": "one aggregate source"},
        )
        for index, source in enumerate(source_ids)
    ])
    parsed = materialize(
        aggregate, mode="branch", source_ids=source_ids,
        source_severities={source: "MAJOR" for source in source_ids},
    )
    assert len(parsed["findings"]) == 150


def test_semantic_validation_reports_all_independent_issues():
    value = decision(
        "census",
        governing_findings=[
            finding(
                fid="G1", severity="MINOR", source_ids=["domain:F1"],
                classification={"kind": "existing_class", "class_id": "missing"},
            ),
            finding(
                fid="G1", source_ids=["unknown:F2"],
                classification={"kind": "one_off", "reason": "one site"},
            ),
        ],
    )
    with pytest.raises(sp.ProtocolError) as caught:
        materialize(
            value, source_ids=["domain:F1"],
            source_severities={"domain:F1": "MAJOR"},
        )
    message = str(caught.value)
    assert "duplicate value 'G1'" in message
    assert "cannot downgrade domain:F1" in message
    assert "unknown active class 'missing'" in message
    assert "unknown source 'unknown:F2'" in message


def test_class_and_debt_outcome_completeness_are_independent_controls():
    with pytest.raises(sp.ProtocolError, match="class_outcomes: expected exactly"):
        materialize(
            decision("final", coverage=coverage()),
            active_classes=[active_class()],
        )
    with pytest.raises(sp.ProtocolError, match="debt_outcomes: must update every"):
        materialize(decision("correction"), durable_debt=[durable_debt(cid=None)])


def v1_projection(parsed):
    """Normalize only V1's model-chosen fresh debt label for frozen comparisons."""
    projected = {
        key: parsed[key]
        for key in (
            "role", "source_dispositions", "assessment_dispositions", "findings",
            "debt", "debt_updates", "class_dispositions", "class_records",
            "class_assessments",
        )
    }
    projected["debt"] = [
        {key: value for key, value in row.items() if key != "id"}
        for row in projected["debt"]
    ]
    if "coverage" in parsed:
        projected["coverage"] = parsed["coverage"]
    return projected


def historical_v1_reference(
    value, *, role, source_ids=(), assessment_verdicts=None,
    assessment_findings=None, active=(), prior_debt=(), mode=cc.PLAN_MODE,
):
    """Executable reference for the settlement contract at commit 83fc1e6.

    This deliberately consumes the redundant V1 tables, validates their
    historical cross-table relationships, and emits the private finding/class
    binding used by durable settlement.  It is test-only and independent of
    Protocol v2's semantic materializer.
    """
    obj = deepcopy(value)
    expected_keys = {
        "role", "source_dispositions", "assessment_dispositions", "findings",
        "debt", "debt_updates", "class_dispositions", "class_records",
        "class_assessments",
    } | ({"coverage"} if role == "final" else set())
    assert set(obj) == expected_keys
    assert obj["role"] == role
    findings = {row["id"]: row for row in obj["findings"]}
    assert len(findings) == len(obj["findings"])

    source_rows = obj["source_dispositions"]
    assert {row["source_id"] for row in source_rows} == set(source_ids)
    assert all(row["governing_id"] in findings for row in source_rows)
    expected_verdicts = assessment_verdicts or {}
    assessment_rows = obj["assessment_dispositions"]
    assert {row["assessment_id"] for row in assessment_rows} == set(expected_verdicts)
    assert all(
        row["governing_id"] is None or row["governing_id"] in findings
        for row in assessment_rows
    )

    dispositions = {row["finding_id"]: row for row in obj["class_dispositions"]}
    assert set(dispositions) == set(findings)
    refs = {}
    referenced_records = set()
    for finding_id, row in dispositions.items():
        if row["kind"] == "one_off":
            refs[finding_id] = None
        elif row["kind"] == "existing_class":
            assert row["class_id"] in {item["class_id"] for item in active}
            refs[finding_id] = row["class_id"]
        else:
            index = row["record_index"]
            assert obj["class_records"][index]["op"] == "new"
            assert index not in referenced_records
            referenced_records.add(index)
            refs[finding_id] = f"record:{index}"
    assert referenced_records == {
        index for index, row in enumerate(obj["class_records"])
        if row["op"] == "new"
    }

    debt_by_finding = {}
    for row in obj["debt"]:
        assert row["finding_id"] in findings and row["status"] in {"open", "closed"}
        debt_by_finding.setdefault(row["finding_id"], []).append(row)
    violated_targets = {
        row["governing_id"] for row in assessment_rows
        if expected_verdicts.get(row["assessment_id"]) == "violated"
    }
    for finding_id, finding_row in findings.items():
        if finding_row["severity"] in sp.BLOCKING or finding_id in violated_targets:
            assert len([
                row for row in debt_by_finding.get(finding_id, [])
                if row["status"] == "open"
            ]) == 1

    known = {row["id"] for row in prior_debt if row["status"] == "open"}
    assert {row["id"] for row in obj["debt_updates"]} == known
    assessments = {row["class_id"]: row for row in obj["class_assessments"]}
    assert set(assessments) == set(expected_verdicts)
    disposition_targets = {
        row["assessment_id"]: row["governing_id"] for row in assessment_rows
    }
    for class_id, verdict in expected_verdicts.items():
        row = assessments[class_id]
        assert row["verdict"] == verdict
        assert row["finding_id"] == disposition_targets[class_id]
        if assessment_findings is not None and verdict == "violated":
            cited = assessment_findings[class_id]
            governed = {
                item["governing_id"] for item in source_rows
                if item["source_id"] == cited
            }
            if role == "census":
                assert row["finding_id"] in governed
        if row["finding_id"] is not None:
            assert refs[row["finding_id"]] == class_id

    register = rc.register_from_records(
        obj["class_records"], mechanized=None if mode == cc.BRANCH_MODE else False,
    )
    lineage = cc.Lineage(
        "v1-reference", mode=mode,
        classes={
            item["class_id"]: lineage_with_active(item).classes[item["class_id"]]
            for item in active
        },
        next_seq=len(active) + 1,
    )
    cc.apply_register(lineage, register, round_no=2)
    obj["_finding_class_refs"] = refs
    return obj


def durable_projection(
    settlement, *, active=None, prior_debt=(), phase="census", mode=cc.PLAN_MODE,
):
    active = active or []
    lineage = cc.Lineage(
        lineage_id="v1-v2-durable", mode=mode,
        classes={
            row["class_id"]: lineage_with_active(row).classes[row["class_id"]]
            for row in active
        },
        next_seq=len(active) + 1,
    )
    register = rc.register_from_records(
        settlement["class_records"],
        mechanized=None if mode == cc.BRANCH_MODE else False,
    )
    minted = cc.apply_register(lineage, register, round_no=2)
    minted_by_record = rc.minted_record_ids(settlement["class_records"], minted)
    state = rc.normalize_state({}, stakes="s", snapshot="before")
    state["phase"] = phase
    state["debt"] = deepcopy(list(prior_debt))
    state = rc.settle_state(
        state, settlement, phase=phase, snapshot="after", round_no=2,
    )
    for debt in state["debt"]:
        debt.setdefault("class_ids", []).extend(
            minted_by_record[index] for index in debt.pop("class_record_indexes", [])
        )
        debt["class_ids"] = list(dict.fromkeys(debt["class_ids"]))
        if debt["id"] not in {row["id"] for row in prior_debt}:
            debt["id"] = f"fresh:{debt['finding_id']}"
    state["debt"].sort(key=lambda row: row["finding_id"])
    classes = sorted(
        (vars(row) for row in lineage.classes.values()), key=lambda row: row["class_id"],
    )
    return state, classes, rc.trailer(state)


def test_frozen_historical_v1_census_projection_is_preserved():
    """Projection captured from the pre-V2 settlement contract at 83fc1e6."""
    classes = [active_class(severity="MINOR")]
    values = [
        finding("G1", "MAJOR", source_ids=["domain:F1"]),
        finding(
            "G2", "MINOR", source_ids=["integrity:F2"],
            classification={"kind": "existing_class", "class_id": "class-a"},
        ),
        finding(
            "G3", "MAJOR", source_ids=["execution:F3"],
            classification={
                "kind": "new_class",
                "definition": {
                    "invariant": "identity survives copies", "severity": "BLOCKER",
                    "procedure": "inspect every copy boundary",
                },
            },
        ),
    ]
    raw = decision(
        "census", governing_findings=values,
        class_outcomes=[{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "new_finding", "finding_id": "G2"},
        }],
    )
    parsed = materialize(
        raw,
        source_ids=["domain:F1", "integrity:F2", "execution:F3"],
        source_severities={
            "domain:F1": "MAJOR", "integrity:F2": "MINOR",
            "execution:F3": "MAJOR",
        },
        assessment_verdicts={"class-a": "violated"},
        assessment_findings={"class-a": "integrity:F2"},
        active_classes=classes,
    )
    expected_debt = [
        {
            "finding_id": row["id"], "status": "open", "severity": row["severity"],
            "summary": row["summary"], "evidence": row["evidence"],
            "remedy": row["remedy"],
        }
        for row in values
    ]
    expected = {
        "role": "census",
        "source_dispositions": [
            {"source_id": "domain:F1", "governing_id": "G1"},
            {"source_id": "integrity:F2", "governing_id": "G2"},
            {"source_id": "execution:F3", "governing_id": "G3"},
        ],
        "assessment_dispositions": [
            {"assessment_id": "class-a", "governing_id": "G2"},
        ],
        "findings": [
            {key: row[key] for key in ("id", "severity", "summary", "evidence", "remedy")}
            for row in values
        ],
        "debt": expected_debt,
        "debt_updates": [],
        "class_dispositions": [
            {"finding_id": "G1", "kind": "one_off", "reason": "this fixture has one site"},
            {"finding_id": "G2", "kind": "existing_class", "class_id": "class-a"},
            {"finding_id": "G3", "kind": "new_class", "record_index": 0},
        ],
        "class_records": [{
            "op": "new", "invariant": "identity survives copies", "severity": "BLOCKER",
            "procedure": "inspect every copy boundary",
        }],
        "class_assessments": [{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "finding_id": "G2",
        }],
    }
    assert v1_projection(parsed) == expected
    legacy = deepcopy(expected)
    for index, row in enumerate(legacy["debt"], 1):
        row["id"] = f"legacy-local-{index}"
    legacy = historical_v1_reference(
        legacy, role="census",
        source_ids=["domain:F1", "integrity:F2", "execution:F3"],
        assessment_verdicts={"class-a": "violated"},
        assessment_findings={"class-a": "integrity:F2"}, active=classes,
    )
    assert durable_projection(parsed, active=classes) == durable_projection(
        legacy, active=classes,
    )


def test_frozen_historical_v1_correction_projection_is_preserved():
    debts = [durable_debt("D7"), durable_debt("D8", cid=None, finding_id="old-8")]
    new = finding(
        "G4", "MAJOR",
        classification={"kind": "existing_class", "class_id": "class-a"},
    )
    raw = decision(
        "correction", governing_findings=[new],
        debt_outcomes=[
            {"debt_id": "D7", "status": "closed", "evidence": ["plan:1"]},
            {"debt_id": "D8", "status": "closed", "evidence": ["plan:1"]},
        ],
        class_outcomes=[{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "basis": {"kind": "new_finding", "finding_id": "G4"},
        }],
        class_actions=[{
            "kind": "reclassify", "class_id": "class-a", "severity": "BLOCKER",
        }],
    )
    parsed = materialize(raw, active_classes=[active_class()], durable_debt=debts)
    expected = {
        "role": "correction", "source_dispositions": [],
        "assessment_dispositions": [
            {"assessment_id": "class-a", "governing_id": "G4"},
        ],
        "findings": [{
            key: new[key] for key in ("id", "severity", "summary", "evidence", "remedy")
        }],
        "debt": [{
            "finding_id": "G4", "status": "open", "severity": "MAJOR",
            "summary": "reachable defect", "evidence": ["plan:1"],
            "remedy": "repair the reachable path",
        }],
        "debt_updates": [
            {"id": "D7", "status": "closed", "evidence": ["plan:1"]},
            {"id": "D8", "status": "closed", "evidence": ["plan:1"]},
        ],
        "class_dispositions": [
            {"finding_id": "G4", "kind": "existing_class", "class_id": "class-a"},
        ],
        "class_records": [
            {"op": "reclassify", "class_id": "class-a", "severity": "BLOCKER"},
        ],
        "class_assessments": [{
            "class_id": "class-a", "verdict": "violated", "evidence": ["plan:1"],
            "finding_id": "G4",
        }],
    }
    assert v1_projection(parsed) == expected
    legacy = deepcopy(expected)
    legacy["debt"][0]["id"] = "legacy-local-new"
    legacy = historical_v1_reference(
        legacy, role="correction",
        assessment_verdicts={"class-a": "violated"},
        active=[active_class()], prior_debt=debts,
    )
    assert durable_projection(
        parsed, active=[active_class()], prior_debt=debts, phase="correction",
    ) == durable_projection(
        legacy, active=[active_class()], prior_debt=debts, phase="correction",
    )


def test_frozen_historical_v1_final_projection_is_preserved():
    raw = decision(
        "final", coverage=coverage(),
        class_outcomes=[{
            "class_id": "class-a", "verdict": "satisfied", "evidence": ["plan:1"],
        }],
    )
    parsed = materialize(raw, active_classes=[active_class()])
    expected = {
        "role": "final", "source_dispositions": [], "assessment_dispositions": [
            {"assessment_id": "class-a", "governing_id": None},
        ],
        "findings": [], "debt": [], "debt_updates": [], "class_dispositions": [],
        "class_records": [{"op": "close", "class_id": "class-a"}],
        "class_assessments": [{
            "class_id": "class-a", "verdict": "satisfied", "evidence": ["plan:1"],
            "finding_id": None,
        }],
        "coverage": coverage(),
    }
    assert v1_projection(parsed) == expected
    legacy = deepcopy(expected)
    legacy = historical_v1_reference(
        legacy, role="final",
        assessment_verdicts={"class-a": "satisfied"},
        active=[active_class()],
    )
    assert durable_projection(
        parsed, active=[active_class()], phase="final",
    ) == durable_projection(
        legacy, active=[active_class()], phase="final",
    )


@pytest.mark.parametrize(("mechanized", "action"), [
    (False, {"kind":"reopen", "class_id":"class-a"}),
    (True, {
        "kind":"replace", "class_id":"class-a", "definition":{
            "invariant":"replacement invariant", "severity":"MAJOR",
            "pattern":"BROKEN", "pathspec":"*.py",
        },
    }),
])
def test_historical_v1_v2_branch_transition_shapes_are_equivalent(
    mechanized, action,
):
    active = active_class(status=cc.CLOSED, mechanized=mechanized)
    current = finding(
        "G5", "MAJOR",
        classification={"kind":"existing_class", "class_id":"class-a"},
    )
    raw = decision(
        "correction", governing_findings=[current],
        class_outcomes=[{
            "class_id":"class-a", "verdict":"violated", "evidence":["plan:1"],
            "basis":{"kind":"new_finding", "finding_id":"G5"},
        }],
        class_actions=[action],
    )
    parsed = materialize(
        raw, mode=cc.BRANCH_MODE, active_classes=[active],
    )
    legacy = {
        "role":"correction", "source_dispositions":[],
        "assessment_dispositions":[{
            "assessment_id":"class-a", "governing_id":"G5",
        }],
        "findings":[{
            "id":"G5", "severity":"MAJOR", "summary":"reachable defect",
            "evidence":["plan:1"], "remedy":"repair the reachable path",
        }],
        "debt":[{
            "id":"legacy-G5", "finding_id":"G5", "status":"open",
            "severity":"MAJOR", "summary":"reachable defect",
            "evidence":["plan:1"], "remedy":"repair the reachable path",
        }],
        "debt_updates":[],
        "class_dispositions":[{
            "finding_id":"G5", "kind":"existing_class", "class_id":"class-a",
        }],
        "class_records":[
            (
                {"op":"reopen", "class_id":"class-a"}
                if not mechanized else {
                    "op":"replace", "class_id":"class-a",
                    "invariant":"replacement invariant", "severity":"MAJOR",
                    "pattern":"BROKEN", "pathspec":"*.py",
                }
            ),
        ],
        "class_assessments":[{
            "class_id":"class-a", "verdict":"violated",
            "evidence":["plan:1"], "finding_id":"G5",
        }],
    }
    legacy = historical_v1_reference(
        legacy, role="correction",
        assessment_verdicts={"class-a":"violated"}, active=[active],
        mode=cc.BRANCH_MODE,
    )
    assert durable_projection(
        parsed, active=[active], phase="correction", mode=cc.BRANCH_MODE,
    ) == durable_projection(
        legacy, active=[active], phase="correction", mode=cc.BRANCH_MODE,
    )


def test_historical_v1_v2_open_unbound_debt_shape_is_equivalent():
    debts = [durable_debt("D9", cid=None)]
    parsed = materialize(
        decision("correction", debt_outcomes=[{
            "debt_id":"D9", "status":"open", "evidence":["plan:1"],
            "reason":"the one-off occurrence remains reachable",
        }]),
        durable_debt=debts,
    )
    legacy = {
        "role":"correction", "source_dispositions":[],
        "assessment_dispositions":[], "findings":[], "debt":[],
        "debt_updates":[{
            "id":"D9", "status":"open", "evidence":["plan:1"],
            "reason":"the one-off occurrence remains reachable",
        }],
        "class_dispositions":[], "class_records":[], "class_assessments":[],
    }
    legacy = historical_v1_reference(
        legacy, role="correction", prior_debt=debts,
    )
    assert durable_projection(
        parsed, prior_debt=debts, phase="correction",
    ) == durable_projection(
        legacy, prior_debt=debts, phase="correction",
    )


def test_historical_v1_v2_census_fanout_shape_is_equivalent():
    classes = [active_class("class-a"), active_class("class-b")]
    values = [
        finding(
            "G1", "MINOR", source_ids=["integrity:F1"],
            classification={"kind":"existing_class", "class_id":"class-a"},
        ),
        finding(
            "G2", "MAJOR", source_ids=["integrity:F1"],
            classification={"kind":"existing_class", "class_id":"class-b"},
        ),
    ]
    outcomes = [
        {
            "class_id":row["classification"]["class_id"],
            "verdict":"violated", "evidence":["plan:1"],
            "basis":{"kind":"new_finding", "finding_id":row["id"]},
        }
        for row in values
    ]
    parsed = materialize(
        decision("census", governing_findings=values, class_outcomes=outcomes),
        source_ids=["integrity:F1"],
        source_severities={"integrity:F1":"MINOR"},
        assessment_verdicts={item["class_id"]:"violated" for item in outcomes},
        assessment_findings={item["class_id"]:"integrity:F1" for item in outcomes},
        active_classes=classes,
    )
    legacy = {
        "role":"census",
        "source_dispositions":[
            {"source_id":"integrity:F1", "governing_id":"G1"},
            {"source_id":"integrity:F1", "governing_id":"G2"},
        ],
        "assessment_dispositions":[
            {"assessment_id":"class-a", "governing_id":"G1"},
            {"assessment_id":"class-b", "governing_id":"G2"},
        ],
        "findings":[
            {
                "id":"G1", "severity":"MINOR", "summary":"reachable defect",
                "evidence":["plan:1"], "remedy":"repair the reachable path",
            },
            {
                "id":"G2", "severity":"MAJOR", "summary":"reachable defect",
                "evidence":["plan:1"], "remedy":"repair the reachable path",
            },
        ],
        "debt":[
            {
                "id":"legacy-G1", "finding_id":"G1", "status":"open",
                "severity":"MINOR", "summary":"reachable defect",
                "evidence":["plan:1"], "remedy":"repair the reachable path",
            },
            {
                "id":"legacy-G2", "finding_id":"G2", "status":"open",
                "severity":"MAJOR", "summary":"reachable defect",
                "evidence":["plan:1"], "remedy":"repair the reachable path",
            },
        ],
        "debt_updates":[],
        "class_dispositions":[
            {"finding_id":"G1", "kind":"existing_class", "class_id":"class-a"},
            {"finding_id":"G2", "kind":"existing_class", "class_id":"class-b"},
        ],
        "class_records":[],
        "class_assessments":[
            {
                "class_id":"class-a", "verdict":"violated",
                "evidence":["plan:1"], "finding_id":"G1",
            },
            {
                "class_id":"class-b", "verdict":"violated",
                "evidence":["plan:1"], "finding_id":"G2",
            },
        ],
    }
    legacy = historical_v1_reference(
        legacy, role="census", source_ids=["integrity:F1"],
        assessment_verdicts={item["class_id"]:"violated" for item in outcomes},
        assessment_findings={item["class_id"]:"integrity:F1" for item in outcomes},
        active=classes,
    )
    assert durable_projection(
        parsed, active=classes,
    ) == durable_projection(
        legacy, active=classes,
    )


def test_historical_v1_v2_remaining_legal_shape_matrix_is_equivalent():
    """Cover tagged outcomes and branch definitions absent from frozen fixtures."""
    classes = [active_class("class-a"), active_class("class-b")]
    debts = [
        durable_debt("D10", cid="class-a", finding_id="old-a"),
        durable_debt("D11", cid="class-b", finding_id="old-b"),
    ]
    procedure = finding(
        "G-procedure", "OUT-OF-SCOPE",
        classification={
            "kind":"new_class", "definition":{
                "invariant":"manual branch invariant", "severity":"MINOR",
                "procedure":"inspect the branch path",
            },
        },
    )
    pattern = finding(
        "G-pattern", "FATAL",
        classification={
            "kind":"new_class", "definition":{
                "invariant":"mechanized branch invariant", "severity":"BLOCKER",
                "pattern":"BROKEN", "pathspec":"*.py",
            },
        },
    )
    raw = decision(
        "correction", governing_findings=[procedure, pattern],
        debt_outcomes=[
            {
                "debt_id":"D10", "status":"open", "evidence":["plan:1"],
                "reason":"the class remains violated",
            },
            {"debt_id":"D11", "status":"closed", "evidence":["plan:1"]},
        ],
        class_outcomes=[
            {
                "class_id":"class-a", "verdict":"violated",
                "evidence":["plan:1"],
                "basis":{"kind":"carried_debt", "debt_id":"D10"},
            },
            {
                "class_id":"class-b", "verdict":"satisfied",
                "evidence":["plan:1"],
            },
        ],
        class_actions=[
            {"kind":"reclassify", "class_id":"class-a", "severity":"BLOCKER"},
            {
                "kind":"replace", "class_id":"class-b", "definition":{
                    "invariant":"manual replacement invariant", "severity":"BLOCKER",
                    "procedure":"inspect the replacement path",
                },
            },
        ],
    )
    parsed = materialize(
        raw, mode=cc.BRANCH_MODE, active_classes=classes, durable_debt=debts,
    )
    legacy = {
        "role":"correction", "source_dispositions":[],
        # V1 could update carried debt and apply standalone class operations
        # without restating those relationships as correction assessments.
        "assessment_dispositions":[],
        "findings":[
            {
                "id":"G-procedure", "severity":"OUT-OF-SCOPE",
                "summary":"reachable defect", "evidence":["plan:1"],
                "remedy":"repair the reachable path",
            },
            {
                "id":"G-pattern", "severity":"FATAL",
                "summary":"reachable defect", "evidence":["plan:1"],
                "remedy":"repair the reachable path",
            },
        ],
        "debt":[{
            "id":"legacy-pattern", "finding_id":"G-pattern", "status":"open",
            "severity":"FATAL", "summary":"reachable defect",
            "evidence":["plan:1"], "remedy":"repair the reachable path",
        }],
        "debt_updates":[
            {
                "id":"D10", "status":"open", "evidence":["plan:1"],
                "reason":"the class remains violated",
            },
            {"id":"D11", "status":"closed", "evidence":["plan:1"]},
        ],
        "class_dispositions":[
            {"finding_id":"G-procedure", "kind":"new_class", "record_index":0},
            {"finding_id":"G-pattern", "kind":"new_class", "record_index":1},
        ],
        "class_records":[
            {
                "op":"new", "invariant":"manual branch invariant",
                "severity":"MINOR", "procedure":"inspect the branch path",
            },
            {
                "op":"new", "invariant":"mechanized branch invariant",
                "severity":"BLOCKER", "pattern":"BROKEN", "pathspec":"*.py",
            },
            {"op":"reclassify", "class_id":"class-a", "severity":"BLOCKER"},
            {
                "op":"replace", "class_id":"class-b",
                "invariant":"manual replacement invariant", "severity":"BLOCKER",
                "procedure":"inspect the replacement path",
            },
        ],
        "class_assessments":[],
    }
    legacy = historical_v1_reference(
        legacy, role="correction", active=classes, prior_debt=debts,
        mode=cc.BRANCH_MODE,
    )
    assert durable_projection(
        parsed, active=classes, prior_debt=debts, phase="correction",
        mode=cc.BRANCH_MODE,
    ) == durable_projection(
        legacy, active=classes, prior_debt=debts, phase="correction",
        mode=cc.BRANCH_MODE,
    )


@pytest.mark.parametrize(("status", "kind", "expected"), [
    (cc.OPEN, "close", cc.CLOSED),
    (cc.CLOSED, "reopen", cc.OPEN),
])
def test_historical_v1_v2_standalone_close_reopen_are_equivalent(
    status, kind, expected,
):
    active = active_class(status=status)
    parsed = materialize(
        decision("correction", class_actions=[{
            "kind":kind, "class_id":"class-a",
        }]),
        active_classes=[active],
    )
    legacy = {
        "role":"correction", "source_dispositions":[],
        "assessment_dispositions":[], "findings":[], "debt":[],
        "debt_updates":[], "class_dispositions":[],
        "class_records":[{"op":kind, "class_id":"class-a"}],
        "class_assessments":[],
    }
    legacy = historical_v1_reference(
        legacy, role="correction", active=[active],
    )
    v2_durable = durable_projection(
        parsed, active=[active], phase="correction",
    )
    v1_durable = durable_projection(
        legacy, active=[active], phase="correction",
    )
    assert v2_durable == v1_durable
    assert next(
        row for row in v2_durable[1] if row["class_id"] == "class-a"
    )["status"] == expected
    assert "STRUCTURAL-PHASE: final" in v2_durable[2]
