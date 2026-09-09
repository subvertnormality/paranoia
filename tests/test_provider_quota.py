import json
from dataclasses import replace
from pathlib import Path

import pytest

from paranoia_local import engines, handlers, arbitrate_handler as ah
from paranoia_local import class_closure as cc, review_census as rc
from paranoia_local.runner import RunResult

# Exact provider diagnostic from issue 124's retained failed Claude attempts.
MESSAGE = "You've reached your Fable limit. Switch to another model, or manage usage credits at claude.ai/settings/usage?from=cc_cli_limit_message, to continue."
RAW = json.dumps({"type": "result", "is_error": True, "result": MESSAGE, "session_id": "quota-session"})


def quota_review():
    return engines.ClaudeEngine()._finalize_review(
        engines.ClaudeEngine().parse_output(RAW), returncode=1,
        stderr="", measured_duration_ms=1,
    )


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("channel", ["json", "stderr", "plain"])
def test_claude_quota_is_diagnostic_only_across_cli_routes(resume, channel):
    calls = []
    def runner(argv, prompt, cwd, timeout):
        calls.append(argv)
        return RunResult(1, RAW if channel == "json" else MESSAGE if channel == "plain" else "",
                         MESSAGE if channel == "stderr" else "")
    engine = engines.ClaudeEngine()
    kwargs = dict(prompt="p", cwd=Path("/repo"), model=engine.default_model,
                  effort="low", web_search=False, runner=runner)
    review = engine.resume("quota-session", **kwargs) if resume else engine.run(**kwargs)
    before = replace(review)
    hint = engines.claude_quota_guidance(review, "claude")
    assert "Claude model quota exhausted (fable)" in hint
    assert "model=" in hint and "models={'claude':" in hint
    assert "does not change fixed cleaner/attester" in hint
    assert "claude-opus-5" in hint
    assert review == before and review.returncode == 1 and review.error
    assert len(calls) == 1
    assert calls[0][calls[0].index("--model") + 1] == engine.default_model


@pytest.mark.parametrize("engine,error,code,text", [
    ("claude", False, 0, MESSAGE),
    ("codex", True, 1, MESSAGE),
    ("claude", True, 124, MESSAGE),
    ("claude", True, 1, "Documentation says: " + MESSAGE),
    ("claude", True, 1, "Selected model is at capacity"),
    ("claude", True, 1, "authentication failed"),
])
def test_quota_detection_does_not_relabel_other_results(engine, error, code, text):
    review = engines.Review(text=text, raw=text, session_ref=None, error=error, returncode=code)
    assert engines.claude_quota_guidance(review, engine) is None


@pytest.mark.parametrize("retry", [False, True])
def test_staged_quota_and_validation_retry_preserve_provider_channels(tmp_path, retry):
    review = quota_review()
    class Engine:
        name = "claude"
        calls = 0
        def run(self, *args, **kwargs):
            self.calls += 1
            return engines.Review("bad", "s", "bad") if retry else review
        def resume(self, *args, **kwargs):
            self.calls += 1
            return review
    engine = Engine()
    def parse(text):
        raise rc.CensusError("invalid initial payload")
    with pytest.raises(rc.CensusError, match="Claude model quota exhausted") as caught:
        handlers._staged_call(role="correction", engine=engine, prompt="p", cwd=tmp_path,
                             model="m", effort="low", timeout=100, parser=parse)
    error = caught.value
    assert error.failure_kind == "provider"
    assert error.stage_role == ("correction-validation-retry" if retry else "correction")
    assert error.engine_failure["failure_detail_excerpt"] == MESSAGE
    assert error.engine_failure["raw_excerpt"] == RAW
    assert error.engine_failure["returncode"] == 1
    assert engine.calls == (2 if retry else 1)


@pytest.mark.parametrize("mode", ["plan", "branch"])
def test_public_reviews_persist_actionable_quota_without_clearance(repo_with_branch, tmp_path, monkeypatch, mode):
    monkeypatch.setattr(engines, "require_evidence_profile", lambda engine: None)
    monkeypatch.setattr(engines.ClaudeEngine, "run", lambda *a, **k: quota_review())
    arguments = dict(repo_path=str(repo_with_branch), round=1, lineage="quota-" + mode,
                     stakes="local test", claim_verification=False, web_search=False)
    if mode == "plan":
        arguments["plan_text"] = "# Plan\nUpdate greeting.\n"
        invoke = handlers.critique_plan
    else:
        arguments.update(base_ref="main", head_ref="feature")
        invoke = handlers.critique_branch
    result = invoke(arguments, engine=engines.ClaudeEngine(), log_dir=tmp_path / "logs")
    assert "Claude model quota exhausted" in result
    assert "CONVERGENCE: NOT-BLOCKED" not in result
    lineage = cc.load_lineage(cc.default_state_root(), "quota-" + mode, stamp="after", mode=mode)
    assert lineage.review_state["staged_failure"]["kind"] == "provider"
    audit = json.loads(next((tmp_path / "logs").glob("*.json")).read_text())
    assert "engine failed (provider)" in result
    assert audit["attempt_ledger"][0]["failure_detail_excerpt"] == MESSAGE


def test_arbitration_quota_names_override_without_rewriting_failure_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(engines, "require_evidence_profile", lambda engine: None)
    calls = []
    def run(self, *args, **kwargs):
        calls.append((args, kwargs))
        return quota_review()
    monkeypatch.setattr(engines.ClaudeEngine, "run", run)
    with pytest.raises(ah.EngineCallError, match="Claude model quota exhausted") as caught:
        ah._run_agent(engine_name="claude", model="claude-fable-5-1", instructions="i",
                      body="b", cwd=tmp_path, effort="low", web_search=False,
                      timeout=100, text_only=True)
    assert "models={'claude':" in str(caught.value)
    assert caught.value.record["failure_detail"] == MESSAGE
    assert caught.value.record["returncode"] == 1
    assert caught.value.record["raw"] == RAW
    assert len(calls) == 1
    assert "Claude model quota exhausted" in handlers._footer(quota_review(), engines.ClaudeEngine())


@pytest.mark.parametrize("phase", ["discovery", "discovery-validation-retry", "binding", "binding-validation-retry"])
def test_arbitration_research_quota_preserves_original_attempt(phase):
    attempts = [{"prompt_sha256": "a" * 64, "prompt_excerpt": "p", "intended_session_ref": "s"}]
    failure = ah._research_execution_failure(
        engine=engines.ClaudeEngine(), model="claude-fable-5-1", phase=phase,
        attempts=attempts, review=quota_review(), rejected=[],
    )
    assert "Claude model quota exhausted" in str(failure)
    assert "models={'claude':" in str(failure)
    assert failure.record["attempts"][0]["failure_detail"] == MESSAGE


def test_public_plan_claim_audit_quota_names_recovery(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(engines, "require_evidence_profile", lambda engine: None)
    monkeypatch.setattr(engines.ClaudeEngine, "run", lambda *a, **k: quota_review())
    result = handlers.critique_plan({
        "repo_path": str(repo), "plan_text": "# Plan\nPython supports strings.\n",
        "lineage": "quota-claims", "round": 1, "stakes": "local test",
    }, engine=engines.ClaudeEngine(), log_dir=tmp_path / "logs")
    assert "Claude model quota exhausted" in result
    assert "CONVERGENCE: NOT-BLOCKED" not in result
    audit = json.loads(next((tmp_path / "logs").glob("*.json")).read_text())
    assert audit["attempt_ledger"][0]["failure_detail_excerpt"] == MESSAGE
