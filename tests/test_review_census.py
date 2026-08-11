import json

import pytest

from paranoia_local import (
    class_closure as cc, handlers, plan_claims as pc, prompts, review_census as rc,
)
from paranoia_local.engines import Review


HEADINGS = (
    "## What works", "## What doesn't work", "## Risks", "## Gaps", "## Improvements",
)


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
        "debt_updates": [], "class_records": [],
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
        "summary":"broken", "evidence":["a.py:1"],
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
    with pytest.raises(rc.CensusError, match="every existing debt"):
        rc.parse_settlement(wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=[],
                            known_debt=["D1"], role="correction")


def test_correction_cannot_downgrade_a_class_or_reuse_durable_debt():
    value = payload(settlement())
    value.update(
        role="correction", source_dispositions=[], assessment_dispositions=[],
        findings=[], debt=[],
        debt_updates=[{"id":"D1","status":"closed","evidence":["a.py:2"]}],
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


def test_correction_requires_a_final_before_clearance():
    state = rc.normalize_state({}, stakes="s", snapshot="p")
    first = rc.parse_settlement(settlement(), source_ids=["domain-1"], assessment_ids=[])
    state = rc.settle_state(state, first, phase="census", snapshot="p", round_no=1)
    assert state["phase"] == "correction"
    close = payload(settlement())
    close.update(role="correction", source_dispositions=[], findings=[], debt=[],
                 debt_updates=[{"id":"D1","status":"closed","evidence":["a.py:2"]}])
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
        parser=lambda text: rc.parse_settlement(
            text, source_ids=["domain-1"], assessment_ids=[],
        ),
    )
    assert parsed["debt"][0]["id"] == "D1"
    assert [row.outcome for row in attempts] == ["format-invalid", "completed"]


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
        parser=lambda text: rc.parse_settlement(
            text, source_ids=["domain-1"], assessment_ids=[],
        ),
    )
    assert parsed["findings"][0]["remedy"] == "fix it"
    assert [row.outcome for row in attempts] == ["format-invalid", "completed"]


def test_violated_class_cannot_be_replaced_at_lower_severity():
    value = payload(settlement())
    value.update(
        source_dispositions=[], findings=[], debt=[],
        assessment_dispositions=[{"assessment_id":"abc","governing_id":"C1"}],
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
    value["debt"].append({"id":"D2", "finding_id":"G2", "status":"open"})
    value["coverage"][0]["finding_ids"].append("G2")
    with pytest.raises(rc.CensusError, match="follow its cited finding"):
        rc.parse_settlement(
            wire(rc.SETTLEMENT_MARKER, value), source_ids=[], assessment_ids=["abc"],
            class_states={"abc": (cc.CLOSED, False, "BLOCKER")}, role="final",
        )


def test_violated_advisory_class_still_requires_concrete_debt():
    value = payload(settlement())
    value.update(
        source_dispositions=[{"source_id":"integrity:F1","governing_id":"G1"}],
        findings=[finding("G1", "MINOR")], debt=[],
        assessment_dispositions=[{"assessment_id":"abc","governing_id":"G1"}],
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
            value = payload(lane())
            value["coverage"][0]["evidence"] = ["missing.py:1"]
            text = wire(rc.LANE_MARKER, value)
            return Review(text=text, session_ref="session", raw=text)

        def resume(self, session_ref, prompt, *args, **kwargs):
            assert session_ref == "session"
            assert "unresolvable repository anchor" in prompt
            (tmp_path / "ok.py").write_text("ok\n")
            value = payload(lane())
            for row in value["coverage"]:
                row["evidence"] = ["ok.py:1"]
            text = wire(rc.LANE_MARKER, value)
            return Review(text=text, session_ref="session", raw=text)

    def parse(text):
        value = rc.parse_lane(text, lane="domain")
        rc.resolve_anchors(value, root=tmp_path)
        return value

    _, _, attempts = handlers._staged_call(
        role="census-domain", engine=Engine(), prompt="review", cwd=tmp_path,
        model="m", effort="high", timeout=10, parser=parse, on_progress=None,
    )
    assert [attempt.role for attempt in attempts] == [
        "census-domain", "census-domain-format-retry",
    ]
    assert [attempt.sequence for attempt in attempts] == [None, None]
    assert [attempt.outcome for attempt in attempts] == ["format-invalid", "completed"]
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
    assert_five_headings(review.text)


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
                    "debt_updates":[], "class_records":[],
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
                "debt_updates":[], "class_records":[],
            })
        elif '"role": "correction"' in prompt:
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"correction", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":[{"id":"D1","status":"closed","evidence":["plan:1"]}],
                "class_records":[],
            })
        else:
            assert '"role": "final"' in prompt
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"final", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":[], "class_records":[],
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


def test_branch_handler_runs_the_four_call_cold_census(repo_with_branch, tmp_path, monkeypatch):
    calls = []
    cc.save_lineage(
        cc.default_state_root(),
        cc.Lineage(
            "four-call-branch", mode=cc.BRANCH_MODE, next_seq=2,
            classes={
                "abc": cc.TrackedClass(
                    "abc", "needle must remain absent", "MAJOR", 1, cc.CLOSED,
                    pattern="needle", pathspec="README.md",
                ),
            },
        ),
    )

    def run(self, prompt, *args, **kwargs):
        calls.append(prompt)
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            assessments = ([{
                "class_id":"abc", "verdict":"satisfied",
                "evidence":["README.md:1"], "finding_id":None,
            }] if lane_name == "integrity" else [])
            value = payload(lane(lane_name, assessments=assessments))
            for row in value["coverage"]:
                row["evidence"] = ["README.md:1"]
            text = wire(rc.LANE_MARKER, value)
        else:
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"census", "source_dispositions":[],
                "assessment_dispositions":[{"assessment_id":"abc","governing_id":None}],
                "findings":[], "debt":[],
                "debt_updates":[], "class_records":[],
            })
        return Review(text=text, session_ref=f"b{len(calls)}", raw=text)

    monkeypatch.setattr(handlers.eng.CodexEngine, "run", run)
    result = handlers.critique_branch({
        "repo_path":str(repo_with_branch), "base_ref":"main", "head_ref":"feature",
        "lineage":"four-call-branch", "round":1, "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs", now=lambda: "B1")
    assert len(calls) == 4
    integrity_prompt = next(
        prompt for prompt in calls if "ROLE: census lane integrity" in prompt
    )
    assert '"invariant": "needle must remain absent"' in integrity_prompt
    assert '"pattern": "needle"' in integrity_prompt
    assert '"pathspec": "README.md"' in integrity_prompt
    assert "STRUCTURAL-PHASE: clear" in result
    audit = json.loads(next((tmp_path / "logs").glob("B1-critique_branch-*.json")).read_text())
    assert len(audit["staged_manifests"]) == 3


def test_failed_consolidation_audit_retains_lane_and_retry_attempts(
    repo_with_branch, tmp_path, monkeypatch,
):
    calls = []

    def run(self, prompt, *args, **kwargs):
        calls.append(("run", prompt))
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            value = payload(lane(lane_name))
            for row in value["coverage"]:
                row["evidence"] = ["README.md:1"]
            text = wire(rc.LANE_MARKER, value)
            return Review(text=text, session_ref=lane_name, raw=text)
        return Review(text="malformed", session_ref="consolidation", raw="malformed")

    def resume(self, session_ref, prompt, *args, **kwargs):
        calls.append(("resume", prompt))
        assert session_ref == "consolidation"
        return Review(text="still malformed", session_ref=session_ref, raw="still malformed")

    monkeypatch.setattr(handlers.eng.CodexEngine, "run", run)
    monkeypatch.setattr(handlers.eng.CodexEngine, "resume", resume)
    result = handlers.critique_branch({
        "repo_path":str(repo_with_branch), "base_ref":"main", "head_ref":"feature",
        "lineage":"failed-consolidation", "round":1, "stakes":"trusted local tool",
    }, engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs", now=lambda: "BF")
    assert "CONVERGENCE: BLOCKED" in result
    assert_five_headings(result)
    assert len(calls) == 5
    audit = json.loads(next((tmp_path / "logs").glob("BF-critique_branch-*.json")).read_text())
    assert len(audit["staged_manifests"]) == 3
    rows = audit["attempt_ledger"]
    invoked_lanes = [
        next(
            line.split()[-1] for line in prompt.splitlines()
            if line.startswith("ROLE: census lane")
        )
        for kind, prompt in calls[:3] if kind == "run"
    ]
    assert [row["role"] for row in rows[:3]] == [
        f"census-{lane_name}" for lane_name in invoked_lanes
    ]
    assert {row["role"] for row in rows[:3]} == {
        "census-behaviour", "census-execution", "census-integrity",
    }
    assert [row["role"] for row in rows[3:]] == [
        "consolidation", "consolidation-format-retry",
    ]
    assert [row["outcome"] for row in rows] == [
        "completed", "completed", "completed", "format-invalid", "format-invalid",
    ]
    assert [row["sequence"] for row in rows] == [1, 2, 3, 4, 5]


def test_branch_handler_runs_census_correction_and_cold_final(
    repo_with_branch, tmp_path, monkeypatch,
):
    calls = []

    def run(self, prompt, *args, **kwargs):
        calls.append(prompt)
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane_name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            findings = ([finding("F1", "MAJOR")] if lane_name == "behaviour" else [])
            value = payload(lane(lane_name, findings=findings))
            for row in value["coverage"]:
                row["evidence"] = ["README.md:1"]
            for item in value["findings"]:
                item["evidence"] = ["README.md:1"]
            text = wire(rc.LANE_MARKER, value)
        elif prompts.STAGED_CONSOLIDATION_INSTRUCTIONS.splitlines()[0] in prompt:
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"census",
                "source_dispositions":[{"source_id":"behaviour:F1","governing_id":"G1"}],
                "assessment_dispositions":[],
                "findings":[{
                    "id":"G1", "severity":"MAJOR", "summary":"repair it",
                    "evidence":["README.md:1"], "remedy":"edit it",
                }],
                "debt":[{"id":"D1", "finding_id":"G1", "status":"open"}],
                "debt_updates":[], "class_records":[],
            })
        elif '"role": "correction"' in prompt:
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"correction", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":[{"id":"D1","status":"closed","evidence":["README.md:1"]}],
                "class_records":[],
            })
        else:
            assert '"role": "final"' in prompt
            coverage = payload(lane())["coverage"]
            for row in coverage:
                row["evidence"] = ["README.md:1"]
            text = wire(rc.SETTLEMENT_MARKER, {
                "role":"final", "source_dispositions":[],
                "assessment_dispositions":[], "findings":[], "debt":[],
                "debt_updates":[], "class_records":[],
                "coverage":coverage, "class_assessments":[],
            })
        return Review(text=text, session_ref=f"branch-{len(calls)}", raw=text)

    monkeypatch.setattr(handlers.eng.CodexEngine, "run", run)
    args = {
        "repo_path":str(repo_with_branch), "base_ref":"main", "head_ref":"feature",
        "lineage":"three-phase-branch", "stakes":"trusted local tool",
    }
    first = handlers.critique_branch(
        {**args, "round":1}, engine=handlers.eng.CodexEngine(),
        log_dir=tmp_path / "logs", now=lambda:"BC1",
    )
    second = handlers.critique_branch(
        {**args, "round":2}, engine=handlers.eng.CodexEngine(),
        log_dir=tmp_path / "logs", now=lambda:"BC2",
    )
    third = handlers.critique_branch(
        {**args, "round":3}, engine=handlers.eng.CodexEngine(),
        log_dir=tmp_path / "logs", now=lambda:"BC3",
    )
    assert "STRUCTURAL-PHASE: correction" in first
    assert "STRUCTURAL-PHASE: final" in second
    assert "STRUCTURAL-PHASE: clear" in third
    assert "CONVERGENCE: NOT-BLOCKED" in third
    assert len(calls) == 6
    assert [row["role"] for row in json.loads(
        next((tmp_path / "logs").glob("BC2-critique_branch-*.json")).read_text()
    )["attempt_ledger"]] == ["correction"]
    assert [row["role"] for row in json.loads(
        next((tmp_path / "logs").glob("BC3-critique_branch-*.json")).read_text()
    )["attempt_ledger"]] == ["final"]
