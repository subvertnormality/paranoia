"""Public-handler acceptance for the only server-derived census decision."""
import json
from copy import deepcopy

import pytest

from paranoia_local import class_closure as cc, census_execution as census
from paranoia_local import engines, handlers, prompts, review_census as rc, staged_protocol as sp
from paranoia_local.engines import Review
from tests.test_review_census import lane, payload, wire, _unit_debt
from tests.conftest import commit_all


def install_clean_provider(monkeypatch, mode, *, repair=False, severity=None):
    calls = []
    answers = {}
    anchor = "plan:1" if mode == cc.PLAN_MODE else "repository/README.md:1"

    def run(self, prompt, *args, **kwargs):
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            name = next(
                row.split()[-1] for row in prompt.splitlines()
                if row.startswith("ROLE: census lane")
            )
            value = payload(lane(name))
            for row in value["coverage"]:
                row["evidence"] = [anchor]
            if severity and name == sp.LANES[mode][0]:
                value["findings"] = [{
                    "id": "F1", "severity": severity, "summary": "fixture observation",
                    "evidence": [anchor], "remedy": "address this fixture",
                }]
                value["coverage"][0].update(status="finding", finding_ids=["F1"])
            text = wire(value)
            answers[name] = text
            if repair and name == "execution":
                text = "{}"
        else:
            name = "consolidation"
            text = wire({
                "role": "census",
                "governing_findings": ([{
                    "id": "G1", "severity": severity, "summary": "fixture observation",
                    "evidence": [anchor], "remedy": "address this fixture",
                    "source_ids": [f"{sp.LANES[mode][0]}:F1"],
                    "classification": {"kind": "one_off", "reason": "unique fixture"},
                }] if severity else []),
                "debt_outcomes": [], "class_actions": [],
            })
        calls.append((name, prompt))
        return Review(text=text, session_ref=name, raw=text, duration_ms=1)

    def resume(self, session_ref, prompt, *args, **kwargs):
        calls.append(("retry", prompt))
        return Review(text=answers[session_ref], session_ref=session_ref,
                      raw=answers[session_ref], duration_ms=1)

    monkeypatch.setattr(engines.CodexEngine, "run", run)
    monkeypatch.setattr(engines.CodexEngine, "resume", resume)
    return calls


def invoke(mode, repo, tmp_path, *, round_no=1, stakes="s", **extra):
    arguments = {
        "repo_path": str(repo), "lineage": "empty-public", "round": round_no, "stakes": stakes,
    }
    if mode == cc.PLAN_MODE:
        arguments.update(plan_text="# Plan\n\nDo it.", claim_verification=False)
    else:
        arguments.update(base_ref="main", head_ref="feature")
    arguments.update(extra)
    function = handlers.critique_plan if mode == cc.PLAN_MODE else handlers.critique_branch
    output = function(arguments, engine=engines.CodexEngine(), log_dir=tmp_path / "logs",
                      now=lambda: f"T{round_no}")
    audit = json.loads(sorted((tmp_path / "logs").glob("*.json"))[-1].read_text())
    return output, audit


def assert_server(audit, output, count):
    assert audit["review_origin"] == "server-empty-census"
    assert "consolidation=server-empty-census" in output
    assert "session_ref=" + chr(96) not in output
    for key in ("session_ref", "returncode", "usage", "duration_ms",
                "provider_duration_ms", "raw", "stderr"):
        assert audit[key] is None
    assert len(audit["attempt_ledger"]) == count
    assert all(row["role"].startswith("census-") for row in audit["attempt_ledger"])


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("repair", [False, True])
def test_empty_public_success_is_server_owned(repo_with_branch, tmp_path, monkeypatch, mode, repair):
    calls = install_clean_provider(monkeypatch, mode, repair=repair)
    output, audit = invoke(mode, repo_with_branch, tmp_path)
    assert_server(audit, output, 4 if repair else 3)
    assert "CONVERGENCE: NOT-BLOCKED" in output
    assert len(calls) == (4 if repair else 3)
    assert len(audit["rejected_payloads"]) == (1 if repair else 0)
    state = cc.load_lineage(cc.default_state_root(), "empty-public", stamp="T", mode=mode)
    assert state.review_state["phase"] == "clear"
    assert state.review_state["debt"] == []
    assert state.classes == {}


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("failure", ["validation", "persistence"])
def test_empty_public_failure_retains_server_origin(repo_with_branch, tmp_path, monkeypatch, mode, failure):
    install_clean_provider(monkeypatch, mode, repair=True)
    if failure == "validation":
        def reject(*args, **kwargs):
            raise sp.ProtocolError("/governing_findings: injected local rejection")
        monkeypatch.setattr(sp, "materialize_decision_value", reject)
    else:
        save = cc.save_lineage

        def fail_clear(root, lineage):
            if lineage.review_state.get("phase") == "clear":
                raise cc.StateUnavailable("injected ambiguous save")
            return save(root, lineage)
        monkeypatch.setattr(cc, "save_lineage", fail_clear)
    output, audit = invoke(mode, repo_with_branch, tmp_path)
    assert_server(audit, output, 4)
    assert "CONVERGENCE: BLOCKED" in output
    assert "CONVERGENCE: NOT-BLOCKED" not in output
    assert "SERVER SETTLEMENT FAILED" in output
    assert len(audit["rejected_payloads"]) == 1
    if failure == "persistence":
        assert "CLASS-CLOSURE: STATE-UNAVAILABLE" in output
    else:
        assert "server-empty-census" in output
        assert "injected local rejection" in output


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("history", ["debt", "format_debt", "validation_debt", "staged_failure"])
@pytest.mark.parametrize("stakes", ["s", "changed stakes"])
def test_incoming_history_survives_normalization_gate(repo_with_branch, tmp_path, monkeypatch, mode, history, stakes):
    calls = install_clean_provider(monkeypatch, mode)
    state = rc.normalize_state(None, stakes="s", snapshot="old-snapshot")
    state.update(phase="clear", last_round=1)
    if history == "debt":
        state["debt"] = [_unit_debt("D1", status="closed", severity=cc.MINOR)]
    elif history == "format_debt":
        state[history] = "old format failure"
    else:
        state[history] = {"role": "consolidation", "kind": "validation", "message": "old failure"}
    cc.save_lineage(cc.default_state_root(), cc.Lineage(
        "empty-public", rounds=1, mode=mode, review_state=state,
    ))
    output, audit = invoke(mode, repo_with_branch, tmp_path, round_no=2, stakes=stakes)
    assert "CONVERGENCE: NOT-BLOCKED" in output
    assert [name for name, _ in calls].count("consolidation") == 1
    assert "review_origin" not in audit
    assert audit["session_ref"] == "consolidation"
    calls.clear()
    # The successful settlement removes prior failure metadata through the existing
    # state transition. Eligibility is incoming-state based, not a lifetime registry.
    (repo_with_branch / "README.md").write_text("# Changed snapshot\n")
    commit_all(repo_with_branch, "new snapshot after settled history")
    output, audit = invoke(mode, repo_with_branch, tmp_path, round_no=3, stakes=stakes)
    assert_server(audit, output, 3)


def test_empty_candidate_rechecks_complete_lane_identity_and_coverage():
    lineage = cc.Lineage("unit", mode=cc.PLAN_MODE)
    history = census.EmptyCensusHistory.capture(lineage)
    manifests = [payload(lane(name)) for name in sp.LANES[cc.PLAN_MODE]]
    args = dict(mode=cc.PLAN_MODE, incoming=history, lineage=lineage, state={})
    assert census.empty_decision(**args, manifests=manifests)
    assert census.empty_decision(**args, manifests=manifests[:-1]) is None
    assert census.empty_decision(**args, manifests=[manifests[0]] * 3) is None
    broken = deepcopy(manifests)
    broken[0]["coverage"].pop()
    with pytest.raises(rc.CensusError):
        census.empty_decision(**args, manifests=broken)


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("severity", cc.SEVERITIES)
def test_every_finding_severity_retains_model_consolidation(
    repo_with_branch, tmp_path, monkeypatch, mode, severity,
):
    calls = install_clean_provider(monkeypatch, mode, severity=severity)
    output, audit = invoke(mode, repo_with_branch, tmp_path)
    assert len(calls) == 4
    assert calls[-1][0] == "consolidation"
    assert "review_origin" not in audit
    assert audit["staged_settlement"]["findings"][0]["severity"] == severity
    if severity in cc.BLOCKING_SEVERITIES:
        assert "CONVERGENCE: BLOCKED" in output


@pytest.mark.parametrize("status", [cc.OPEN, cc.CLOSED, cc.SUPERSEDED])
def test_all_loaded_class_history_disqualifies(status):
    tracked = cc.TrackedClass(
        "C1", "fixture", cc.MINOR, 1, status, procedure="inspect fixture",
    )
    lineage = cc.Lineage("history", classes={"C1": tracked}, mode=cc.PLAN_MODE)
    incoming = census.EmptyCensusHistory.capture(lineage)
    assert incoming.exclusions == ("classes",)
    lineage.classes.clear()
    assert incoming.exclusions == ("classes",)


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
def test_provider_and_server_empty_settlement_have_identical_substantive_state(
    repo_with_branch, tmp_path, monkeypatch, mode,
):
    results = []
    calls = install_clean_provider(monkeypatch, mode)
    for provider in (True, False):
        directory = tmp_path / ("provider" if provider else "server")
        monkeypatch.setenv(cc.STATE_ROOT_ENV, str(directory / "state"))
        with monkeypatch.context() as context:
            if provider:
                context.setattr(census, "empty_decision", lambda **kwargs: None)
            output, audit = invoke(mode, repo_with_branch, directory)
        state = cc.load_lineage(cc.default_state_root(), "empty-public", stamp="T", mode=mode)
        results.append((audit, deepcopy(state.review_state), deepcopy(state.classes)))
        assert "CONVERGENCE: NOT-BLOCKED" in output
    assert results[0][0]["staged_settlement"] == results[1][0]["staged_settlement"]
    assert results[0][1:] == results[1][1:]
    assert sorted(prompt for role, prompt in calls[:4] if role != "consolidation") == sorted(
        prompt for _, prompt in calls[4:]
    )
