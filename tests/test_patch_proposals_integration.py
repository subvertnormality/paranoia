from __future__ import annotations

import json
from pathlib import Path
import time

from paranoia_local import census_execution as census
from paranoia_local import engines
from paranoia_local import git_objects
from paranoia_local import handlers
from paranoia_local import inert_git
from paranoia_local import patch_proposals as pp
from paranoia_local import plan_claims as pc
from paranoia_local import review_census as rc
from paranoia_local import staged_protocol as sp


def context_and_reader():
    data = b"value = 1\n"
    entry = pp.ProposalEntry("app.py", "file", "100644", git_objects.blob_oid(data, 40))
    context = pp.ProposalContext(
        "branch",
        (pp.ProposalTarget("structural:D1", "repair", "MAJOR", ("repository/app.py:1",)),),
        "stakes", "head", "snapshot", None, None, (entry,),
    )
    return context, lambda unused: pp.SourceContent(data)


def valid_response():
    return json.dumps({
        "schema_version": 1, "status": "proposed", "summary": "repair",
        "addressed_finding_ids": ["structural:D1"], "unaddressed": [],
        "edits": [{"target": "repository", "operation": "replace", "path": "app.py",
                   "old_text": "value = 1\n", "new_text": "value = 2\n"}],
        "suggested_tests": ["Run tests."], "limitations": ["Tests not run."],
    })


def author():
    return census.AuthorHandle("behaviour", "lane-session", "codex")


def test_proposal_continuation_success_uses_one_resume(monkeypatch):
    calls = []
    def resume(self, session, prompt, cwd, model, effort, **kwargs):
        calls.append((session, prompt, kwargs))
        return engines.Review(valid_response(), "proposal-session", valid_response())
    monkeypatch.setattr(engines.CodexEngine, "resume_proposal", resume)
    context, reader = context_and_reader()
    result = handlers._run_patch_proposal(
        context=context, source_reader=reader, author=author(),
        engine=engines.CodexEngine(), cwd=Path("/repo"), model="m", effort="high",
        deadline=time.monotonic() + 2_000, on_progress=None,
    )
    assert result.result is not None
    assert result.result.patch
    assert len(result.attempts) == 1
    assert calls[0][0] == "lane-session"
    assert calls[0][2]["timeout"] == handlers.PROPOSAL_INITIAL_TIMEOUT_SEC


def test_invalid_reply_retries_same_returned_session_and_retains_rejection(monkeypatch):
    replies = [
        engines.Review("{}", "repair-session", "raw-invalid"),
        engines.Review(valid_response(), "final-session", "raw-valid"),
    ]
    sessions = []
    def resume(self, session, prompt, cwd, model, effort, **kwargs):
        sessions.append(session)
        return replies.pop(0)
    monkeypatch.setattr(engines.CodexEngine, "resume_proposal", resume)
    context, reader = context_and_reader()
    result = handlers._run_patch_proposal(
        context=context, source_reader=reader, author=author(),
        engine=engines.CodexEngine(), cwd=Path("/repo"), model="m", effort="high",
        deadline=time.monotonic() + 2_000, on_progress=None,
    )
    assert result.result is not None
    assert sessions == ["lane-session", "repair-session"]
    assert [row["role"] for row in result.attempts] == [
        "patch-proposal", "patch-proposal-validation-retry",
    ]
    assert result.attempts[0]["outcome"] == "validation-invalid"
    assert len(result.rejected_payloads) == 1


def test_execution_failure_has_no_retry_or_fresh_fallback(monkeypatch):
    calls = []
    def resume(self, session, prompt, cwd, model, effort, **kwargs):
        calls.append(session)
        return engines.Review("failure", "failed-session", "raw", returncode=1,
                              error=True, failure_detail="quota")
    monkeypatch.setattr(engines.CodexEngine, "resume_proposal", resume)
    context, reader = context_and_reader()
    result = handlers._run_patch_proposal(
        context=context, source_reader=reader, author=author(),
        engine=engines.CodexEngine(), cwd=Path("/repo"), model="m", effort="high",
        deadline=time.monotonic() + 2_000, on_progress=None,
    )
    assert result.result is None and result.reason == "quota"
    assert calls == ["lane-session"]
    assert len(result.attempts) == 1


def test_missing_or_insufficient_deadline_spends_no_provider_call(monkeypatch):
    monkeypatch.setattr(
        engines.CodexEngine, "resume_proposal",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called")),
    )
    context, reader = context_and_reader()
    for deadline in (None, time.monotonic() + 100):
        result = handlers._run_patch_proposal(
            context=context, source_reader=reader, author=author(),
            engine=engines.CodexEngine(), cwd=Path("/repo"), model="m", effort="high",
            deadline=deadline, on_progress=None,
        )
        assert result.result is None and not result.attempts


def git(repo: Path, *args: str) -> str:
    return inert_git.text(repo, list(args)).strip()


def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "fixture")
    git(repo, "config", "user.email", "fixture@example.test")
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    git(repo, "add", "app.py")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "feature")
    (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "feature")
    return repo


def install_settled_census(monkeypatch):
    trailer = (
        "CLASS-REGISTER: staged census parsed — NONE\n"
        "CLASS-CLOSURE: 0 open, 0 closed, 0 surviving matches, 0 exempt, 0 unmechanized\n"
        "STRUCTURAL-PHASE: correction\n"
        "STRUCTURAL-DEBT: 1 blocking open\n"
        "CONVERGENCE: BLOCKED — staged structural debt remains open."
    )
    def staged(*, mode, closure, snapshot, stakes, **kwargs):
        assert closure.lineage is not None
        lane = sp.LANES[mode][0]
        state = rc.normalize_state(closure.lineage.review_state, stakes=stakes, snapshot=snapshot)
        state.update(phase="correction", last_round=closure.round_no, debt=[{
            "id": "D1", "finding_id": "G1", "status": "open", "severity": "MAJOR",
            "summary": "value must be two", "evidence": [
                "repository/app.py:1" if mode == "branch" else "plan:1"
            ], "remedy": "replace one with two", "source_ids": [f"{lane}:F1"],
            "class_ids": [], "first_round": closure.round_no,
            "last_round": closure.round_no,
        }])
        closure.lineage.review_state = state
        closure._settled = True
        closure.register_status = "staged census parsed — NONE"
        handle = census.AuthorHandle(lane, "lane-session", "codex")
        lane_result = census.LaneResult(lane, {"lane": lane}, [], [], {}, handle)
        closure.proposal_census = census.CensusResult([], [], [], {}, (lane_result,))
        closure.proposal_debt_lanes = {"D1": (lane,)}
        closure.staged_manifests = []
        closure.staged_settlement = {"source_dispositions": []}
        return engines.Review("settled body", "review-session", "raw"), trailer, []
    monkeypatch.setattr(handlers, "_staged_structural_review", staged)
    return trailer


def proposal_reply(mode: str) -> str:
    edit = (
        {"target": "repository", "operation": "replace", "path": "app.py",
         "old_text": "value = 1\n", "new_text": "value = 2\n"}
        if mode == "branch" else
        {"target": "plan", "operation": "replace", "path": None,
         "old_text": "value is one", "new_text": "value is two"}
    )
    return json.dumps({
        "schema_version": 1, "status": "proposed", "summary": "repair",
        "addressed_finding_ids": ["structural:D1"], "unaddressed": [],
        "edits": [edit], "suggested_tests": ["Run tests."],
        "limitations": ["Tests not run."],
    })


def test_public_branch_handoff_proposes_before_cleanup_and_preserves_trailer(
    tmp_path, monkeypatch,
):
    repo = repository(tmp_path)
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    trailer = install_settled_census(monkeypatch)
    calls = []
    def resume(self, session, prompt, cwd, model, effort, **kwargs):
        calls.append((session, cwd, cwd.exists()))
        text = proposal_reply("branch")
        return engines.Review(text, "proposal-session", text)
    monkeypatch.setattr(engines.CodexEngine, "resume_proposal", resume)
    output = handlers.critique_branch({
        "repo_path": str(repo), "base_ref": "main", "head_ref": "feature",
        "round": 1, "lineage": "patch-branch", "stakes": "local",
        "web_search": False, "propose_patch": True,
    }, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "PATCH-PROPOSAL: PROPOSED" in output
    assert "value = 2" in output
    assert output.endswith(trailer)
    assert calls == [("lane-session", calls[0][1], True)]
    records = sorted((tmp_path / "logs").glob("*.json"))
    assert len(records) == 2
    proposal_record = json.loads(next(
        path for path in records if "patch_proposal" in path.name
    ).read_text())
    assert proposal_record["patch_applied"] is False
    assert proposal_record["tests_executed"] is False


def test_public_plan_handoff_uses_captured_plan_and_preserves_trailer(
    tmp_path, monkeypatch,
):
    repo = repository(tmp_path)
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    trailer = install_settled_census(monkeypatch)
    calls = []
    def resume(self, session, prompt, cwd, model, effort, **kwargs):
        calls.append((session, cwd.exists()))
        text = proposal_reply("plan")
        return engines.Review(text, "proposal-session", text)
    monkeypatch.setattr(engines.CodexEngine, "resume_proposal", resume)
    output = handlers.critique_plan({
        "repo_path": str(repo), "plan_text": "The value is one.\n",
        "round": 1, "lineage": "patch-plan", "stakes": "local",
        "claim_verification": False, "web_search": False, "propose_patch": True,
    }, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "PATCH-PROPOSAL: PROPOSED" in output
    assert "plan-artifact.md" in output
    assert "The value is two." in output
    assert output.endswith(trailer)
    assert calls == [("lane-session", True)]


def test_plan_path_change_after_capture_reports_stale_without_rebasing(
    tmp_path, monkeypatch,
):
    repo = repository(tmp_path)
    plan = tmp_path / "outside-plan.md"
    plan.write_text("The value is one.\n", encoding="utf-8")
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    trailer = install_settled_census(monkeypatch)
    def resume(self, session, prompt, cwd, model, effort, **kwargs):
        plan.write_text("A concurrently changed plan.\n", encoding="utf-8")
        text = proposal_reply("plan")
        return engines.Review(text, "proposal-session", text)
    monkeypatch.setattr(engines.CodexEngine, "resume_proposal", resume)
    output = handlers.critique_plan({
        "repo_path": str(repo), "plan_path": str(plan),
        "round": 1, "lineage": "stale-plan", "stakes": "local",
        "claim_verification": False, "web_search": False, "propose_patch": True,
    }, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "-The value is one." in output
    assert "+The value is two." in output
    assert "APPLICATION-SUITABILITY: STALE" in output
    assert "concurrently changed" not in output
    assert output.endswith(trailer)


def test_public_omitted_and_false_make_zero_proposal_calls(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    install_settled_census(monkeypatch)
    monkeypatch.setattr(
        engines.CodexEngine, "resume_proposal",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("proposal called")),
    )
    for index, proposal_value in enumerate((None, False), start=1):
        args = {
            "repo_path": str(repo), "base_ref": "main", "head_ref": "feature",
            "round": 1, "lineage": f"disabled-{index}", "stakes": "local",
            "web_search": False,
        }
        if proposal_value is not None:
            args["propose_patch"] = proposal_value
        output = handlers.critique_branch(
            args, engine=engines.CodexEngine(), log_dir=tmp_path / f"logs-{index}",
        )
        assert "PATCH-PROPOSAL" not in output


def test_missing_settled_review_audit_receipt_prevents_proposal_spend(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    install_settled_census(monkeypatch)
    monkeypatch.setattr(handlers.logs, "write_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        engines.CodexEngine, "resume_proposal",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("proposal called")),
    )
    output = handlers.critique_branch({
        "repo_path": str(repo), "base_ref": "main", "head_ref": "feature",
        "round": 1, "lineage": "missing-audit", "stakes": "local",
        "web_search": False, "propose_patch": True,
    }, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "PATCH-PROPOSAL: UNAVAILABLE" in output
    assert "settled review audit receipt unavailable" in output


def test_failed_current_claim_audit_prevents_plan_proposal_spend(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    install_settled_census(monkeypatch)
    monkeypatch.setattr(handlers.inert_git, "require_supported_version", lambda: (2, 36, 0))
    monkeypatch.setattr(handlers.eng, "require_evidence_profile", lambda engine: None)
    failed_state = pc.empty_state()
    failed_state["debt"] = {
        "audit_failed": True, "reason": "claim discovery failed", "claim_rows": "none",
    }
    monkeypatch.setattr(
        handlers, "_verify_plan_claims",
        lambda *args, **kwargs: (failed_state, "claim-discovery-failed"),
    )
    monkeypatch.setattr(
        engines.CodexEngine, "resume_proposal",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("proposal called")),
    )
    output = handlers.critique_plan({
        "repo_path": str(repo), "plan_text": "The value is one.\n",
        "round": 1, "lineage": "failed-claim-plan", "stakes": "local",
        "claim_verification": True, "web_search": True, "propose_patch": True,
    }, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "PATCH-PROPOSAL: UNAVAILABLE" in output
    assert "current claim audit did not complete successfully" in output


def test_explicit_true_unsupported_modes_refuse_before_provider(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    monkeypatch.setattr(
        engines.CodexEngine, "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called")),
    )
    with __import__("pytest").raises(ValueError, match="include_uncommitted:false"):
        handlers.critique_branch({
            "repo_path": str(repo), "include_uncommitted": True,
            "round": 1, "lineage": "unsupported", "propose_patch": True,
        }, engine=engines.CodexEngine())
    with __import__("pytest").raises(ValueError, match="class_closure:true"):
        handlers.critique_plan({
            "repo_path": str(repo), "plan_text": "plan", "class_closure": False,
            "propose_patch": True,
        }, engine=engines.CodexEngine())
