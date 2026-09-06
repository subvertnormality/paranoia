"""Measured boundaries for the architecture/performance delivery."""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from paranoia_local import class_closure as cc, handlers, review_census as rc
from paranoia_local import review_transitions as tr, runner, session_routing, telemetry
from paranoia_local import engines, orientation, server, staged_protocol as sp
from scripts import run_staged_protocol_mutation_checks as mutation


@pytest.mark.parametrize("run", [runner.run_capture, runner.run_streaming])
def test_timeout_includes_descendant_pipe_lifetime(tmp_path, run):
    if os.name != "posix":
        pytest.skip("POSIX process-group acceptance")
    script = (
        "import subprocess,sys; "
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "print('parent exits',flush=True)"
    )
    started = time.monotonic()
    result = run([sys.executable, "-c", script], "", tmp_path, timeout=1)
    assert result.returncode == 124
    assert time.monotonic() - started < 4
    assert result.stdout == ""


@pytest.mark.parametrize("run", [runner.run_capture, runner.run_streaming])
@pytest.mark.parametrize("channel", ["stdout", "stderr"])
def test_invalid_utf8_in_either_pipe_cannot_succeed(tmp_path, run, channel):
    script = f"import sys; print('valid reply'); sys.{channel}.buffer.write(bytes([255]))"
    result = run([sys.executable, "-c", script], "", tmp_path, timeout=5)
    assert result.returncode == 65
    assert "UnicodeDecodeError" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("run", [runner.run_capture, runner.run_streaming])
def test_multibyte_pipe_roundtrip(tmp_path, run):
    result = run(
        [sys.executable, "-c", "import sys; print(sys.stdin.read()); sys.stderr.write('日本語')"],
        "初回契約", tmp_path, timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "初回契約"
    assert result.stderr == "日本語"


@pytest.mark.parametrize("phase,owner,expected", [
    ("census", None, "census"), ("correction", None, "census"),
    ("final", "codex", "final"),
])
def test_class_only_incoming_never_invents_final_owner(phase, owner, expected):
    state = {"phase":phase, "debt":[], "final_engine":owner}
    decision = tr.incoming(tr.ReviewFacts.capture(state, ["a"]))
    assert decision.phase == expected
    assert decision.final_engine == (owner if expected == "final" else None)


def _seed(root, monkeypatch, mode, repo, *, last_round=1):
    state_root = root / "state"
    monkeypatch.setenv(cc.STATE_ROOT_ENV, str(state_root))
    anchor = "plan:1" if mode == cc.PLAN_MODE else "repository/app.py:1"
    state = rc.normalize_state(None, stakes="s", snapshot=rc.digest("prior"))
    state.update(phase="correction", last_round=last_round, plan_line_count=1, debt=[{
        "id":"D1", "finding_id":"F1", "status":"open", "severity":"MAJOR",
        "summary":"repair needed", "evidence":[anchor], "remedy":"repair",
        "source_ids":[], "class_ids":["class-a"], "first_round":1,
        "last_round":last_round,
    }])
    tracked = cc.TrackedClass(
        "class-a", "all sites remain safe", cc.MAJOR, 1, cc.OPEN,
        procedure="inspect every site", members=("primary-call-path",),
    )
    cc.save_lineage(state_root, cc.Lineage(
        "architecture", rounds=last_round, mode=mode,
        classes={tracked.class_id:tracked}, review_state=state,
    ))
    args = {"repo_path":str(repo), "lineage":"architecture",
            "round":last_round + 1, "stakes":"s"}
    if mode == cc.PLAN_MODE:
        args.update(plan_text="artifact", claim_verification=False)
    else:
        args.update(base_ref="main", head_ref="feature")
    return state_root, args, anchor


def _citation(anchor):
    return [{"anchor":anchor, "rationale":"the complete site is inspected"}]


def _satisfied(anchor):
    return {"verdict":"satisfied", "member_coverage":[
        {"member_id":"primary-call-path", "evidence":_citation(anchor)},
    ]}


def _decision(role, anchor, ids, *, replace=False, checkpoint=False):
    value = {
        "role":role, "governing_findings":[], "concession_challenges":{},
        "debt_outcomes":[], "class_actions":{cid:None for cid in ids},
        "class_outcomes":{cid:_satisfied(anchor) for cid in ids},
    }
    if role == "correction":
        value["debt_outcomes"] = [{
            "debt_id":"D1", "status":"open" if checkpoint else "closed",
            "evidence":_citation(anchor),
            **({"reason":"still violated"} if checkpoint else {}),
        }]
        if checkpoint:
            value["class_outcomes"]["class-a"] = {
                "verdict":"violated", "evidence":_citation(anchor),
                "basis":{"kind":"carried_debt", "debt_id":"D1"},
            }
        elif replace:
            value["class_actions"]["class-a"] = {"kind":"replace", "definition":{
                "invariant":"the complete replacement obligation remains safe",
                "severity":"MAJOR", "procedure":"inspect every site", "members":["primary-call-path"],
            }}
    else:
        value["coverage"] = [{
            "id":item, "status":"covered", "summary":"inspected the full artifact",
            "evidence":_citation(anchor), "finding_ids":[],
        } for item in sp.CHECKLIST]
    return json.dumps(value)


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("foreign", [False, True])
def test_public_replacement_uses_owned_class_only_final(
    tmp_path, monkeypatch, repo, repo_with_branch, mode, foreign,
):
    state_root, args, anchor = _seed(
        tmp_path, monkeypatch, mode, repo if mode == cc.PLAN_MODE else repo_with_branch,
    )
    calls = []
    def run(self, prompt, *unused, **kwargs):
        schema = kwargs["response_schema"]
        role = schema["properties"]["role"]["const"]
        ids = list(schema["properties"]["class_outcomes"]["properties"])
        calls.append((self.name, role))
        text = _decision(role, anchor, ids, replace=role == "correction")
        return engines.Review(text=text, raw=text, session_ref="review-session")
    monkeypatch.setattr(engines.CodexEngine, "run", run)
    monkeypatch.setattr(engines.ClaudeEngine, "run", run)
    handler = handlers.critique_plan if mode == cc.PLAN_MODE else handlers.critique_branch
    first = handler(args, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "CONVERGENCE: BLOCKED" in first
    state = cc.load_lineage(state_root, "architecture", stamp="read", mode=mode)
    assert state.review_state["phase"] == "final"
    assert state.review_state["final_engine"] == "codex"
    assert state.blocking()
    args["round"] += 1
    second = handler(args, engine=engines.ClaudeEngine() if foreign else engines.CodexEngine(),
                     log_dir=tmp_path / "logs")
    assert calls == [("codex", "correction"), ("claude" if foreign else "codex", "final")]
    if foreign:
        assert "CONVERGENCE: BLOCKED" in second
        state = cc.load_lineage(state_root, "architecture", stamp="read2", mode=mode)
        assert state.review_state["final_engine"] == "codex"
        args["round"] += 1
        second = handler(args, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "CONVERGENCE: NOT-BLOCKED" in second


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("disposition", ["HOLD", "CONCEDE"])
@pytest.mark.parametrize("repair_first", [False, True])
def test_public_checkpoint_to_bound_rebut(
    tmp_path, monkeypatch, repo, repo_with_branch, mode, disposition, repair_first,
):
    state_root, args, anchor = _seed(
        tmp_path, monkeypatch, mode, repo if mode == cc.PLAN_MODE else repo_with_branch,
        last_round=6,
    )
    calls = []
    text = _decision("correction", anchor, ["class-a"], checkpoint=True)
    def run(self, prompt, *unused, **kwargs):
        calls.append("run")
        result = "{}" if repair_first else text
        return engines.Review(text=result, raw=result, session_ref="checkpoint-session")
    def resume(self, session, prompt, *unused, **kwargs):
        calls.append("resume")
        if "disposition" in kwargs["response_schema"]["properties"]:
            result = json.dumps({"disposition":disposition, "reason":"specific counter-evidence",
                                 "evidence":_citation(anchor)})
        else:
            result = text
        return engines.Review(text=result, raw=result, session_ref="checkpoint-session")
    monkeypatch.setattr(engines.CodexEngine, "run", run)
    monkeypatch.setattr(engines.CodexEngine, "resume", resume)
    handler = handlers.critique_plan if mode == cc.PLAN_MODE else handlers.critique_branch
    result = handler(args, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "ARCHITECTURE-CHECKPOINT: required" in result
    assert calls == (["run", "resume"] if repair_first else ["run"])
    state = cc.load_lineage(state_root, "architecture", stamp="checkpoint", mode=mode)
    assert state.review_state["last_round"] == 6
    assert state.review_state["debt"][0]["status"] == "open"
    assert not any(state.review_state.get(k) for k in rc.REBUT_FAILURE_FIELDS)
    result = handlers.rebut({
        "repo_path":args["repo_path"], "lineage":"architecture", "lineage_mode":mode,
        "class_id":"class-a", "debt_id":"D1", "session_ref":"checkpoint-session",
        "rebuttal":"The cited site contradicts the finding.",
    }, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert disposition in result
    state = cc.load_lineage(state_root, "architecture", stamp="rebut", mode=mode)
    assert state.review_state["debt"][0]["status"] == ("closed" if disposition == "CONCEDE" else "open")


def test_source_index_preserves_coordinates_and_contract_bytes():
    text = "# same\n~~~python\n# hidden\n~~~\n## same ##\n" + ("body\n" * 2100) + "# last\n"
    contract = handlers._branch_contract_view(text)
    index = orientation.contract_heading_index(contract.lines)
    assert index.splitlines() == ["plan:1 # same", "plan:5 ## same", "plan:2106 # last"]
    rendered = handlers._branch_contract_section(contract)
    assert index in rendered and contract.rendered in rendered
    assert contract.original == text
    assert contract.digest == telemetry.digest(text)
    assert contract.line_count == 2107


def test_session_routing_ignores_failed_echoes_and_requires_explicit_unknown(tmp_path):
    good = {"tool":"query", "engine":"claude", "error":False, "returncode":0, "session_ref":"s"}
    (tmp_path / "good.json").write_text(json.dumps(good))
    (tmp_path / "echo.json").write_text(json.dumps({**good, "engine":"codex", "error":True}))
    assert session_routing.resolve("s", None, (tmp_path,)) == "claude"
    with pytest.raises(ValueError, match="belongs to"):
        session_routing.resolve("s", "codex", (tmp_path,))
    with pytest.raises(ValueError, match="unknown"):
        session_routing.resolve("unknown", None, (tmp_path,))
    assert session_routing.resolve("unknown", "codex", (tmp_path,)) == "codex"
    (tmp_path / "conflict.json").write_text(json.dumps({**good, "engine":"codex"}))
    with pytest.raises(ValueError, match="conflicting"):
        session_routing.resolve("s", "claude", (tmp_path,))


def test_common_trace_captures_parallel_attempts_without_summing_wall_time(tmp_path):
    engine = engines.CodexEngine()
    def call():
        return engine.run(
            "prompt", tmp_path, "m", "high", False,
            runner=lambda *args: (time.sleep(.12) or runner.RunResult(
                0, '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}', "",
            )),
        )
    with telemetry.recording("query", tmp_path):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [telemetry.submit(pool, call) for _ in range(2)]
            for future in futures:
                future.result()
    data = json.loads(next(tmp_path.glob("*-run-*.json")).read_text())
    assert len(data["attempts"]) == 2
    assert data["total_elapsed_ms"] < sum(row["elapsed_ms"] for row in data["attempts"])
    assert all(row["prompt_sha256"] == telemetry.digest("prompt") for row in data["attempts"])
    assert data["source_observed_at_finish"]["source_sha256"]


@pytest.mark.parametrize("tool", ["query", "rebut", "critique_plan", "critique_branch", "arbitrate"])
def test_dispatch_records_total_for_every_mode(tmp_path, monkeypatch, tool):
    table = server._MULTI_ENGINE_HANDLERS if tool == "arbitrate" else server._HANDLERS
    monkeypatch.setitem(table, tool, lambda *args, **kwargs: "result")
    args = {"engine":"codex", "session_ref":"unknown"} if tool == "rebut" else {}
    assert server.dispatch(tool, args, default_engine_name="codex", log_dir=tmp_path) == "result"
    data = json.loads(next(tmp_path.glob("*-run-*.json")).read_text())
    assert data["reviewed_tool"] == tool and data["total_elapsed_ms"] >= 0


@pytest.mark.parametrize("code,xml,expected", [
    (1, '<testsuite><testcase><failure message="AssertionError">assert False</failure></testcase></testsuite>', True),
    (1, '<testsuite><testcase><error message="setup failed"/></testcase></testsuite>', False),
    (2, '<testsuite><testcase><error message="collection failed"/></testcase></testsuite>', False),
    (5, '<testsuite/>', False),
    (1, '<testsuite><testcase><failure message="OSError">network down</failure></testcase></testsuite>', False),
])
def test_mutation_infrastructure_failures_are_not_kills(code, xml, expected):
    assert mutation.assertion_kill(code, xml) is expected


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("failure", ["missing-member", "bad-anchor", "ambiguous-save"])
def test_public_class_only_final_never_clears_invalid_evidence_or_save(
    tmp_path, monkeypatch, repo, repo_with_branch, mode, failure,
):
    state_root, args, anchor = _seed(
        tmp_path, monkeypatch, mode, repo if mode == cc.PLAN_MODE else repo_with_branch,
    )
    calls = []
    def run(self, *unused, **kwargs):
        props = kwargs["response_schema"]["properties"]
        role = props["role"]["const"]
        ids = list(props["class_outcomes"]["properties"])
        calls.append(role)
        value = json.loads(_decision(role, anchor, ids, replace=role == "correction"))
        if role == "final":
            if failure == "ambiguous-save":
                def unavailable(*args, **kwargs):
                    raise cc.StateUnavailable("unconfirmed test save")
                monkeypatch.setattr(cc, "save_lineage", unavailable)
            else:
                for outcome in value["class_outcomes"].values():
                    if failure == "missing-member":
                        outcome["member_coverage"] = []
                    else:
                        outcome["member_coverage"][0]["evidence"] = _citation("plan:999999")
        text = json.dumps(value)
        return engines.Review(text=text, raw=text, session_ref="review-session")
    monkeypatch.setattr(engines.CodexEngine, "run", run)
    monkeypatch.setattr(engines.CodexEngine, "resume", run)
    handler = handlers.critique_plan if mode == cc.PLAN_MODE else handlers.critique_branch
    handler(args, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    before = cc.load_lineage(state_root, "architecture", stamp="before", mode=mode)
    args["round"] += 1
    result = handler(args, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "CONVERGENCE: NOT-BLOCKED" not in result
    assert "STATE-UNAVAILABLE" in result if failure == "ambiguous-save" else "CONVERGENCE: BLOCKED" in result
    if failure == "ambiguous-save":
        with pytest.raises(cc.StateUnavailable, match="pending write latch"):
            cc.load_lineage(state_root, "architecture", stamp="after", mode=mode)
        return
    after = cc.load_lineage(state_root, "architecture", stamp="after", mode=mode)
    assert after.review_state["last_round"] == before.review_state["last_round"]
    assert after.blocking()


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
@pytest.mark.parametrize("session", [None, "", "new-session"])
def test_checkpoint_replaces_stale_session_without_mutating_debt(
    tmp_path, monkeypatch, repo, repo_with_branch, mode, session,
):
    root, args, anchor = _seed(
        tmp_path, monkeypatch, mode, repo if mode == cc.PLAN_MODE else repo_with_branch,
        last_round=6,
    )
    before = cc.load_lineage(root, "architecture", stamp="seed", mode=mode)
    before.review_state["correction_control"] = rc.normalize_correction_control(
        before.review_state, before.active(),
    )
    before.review_state["correction_control"]["classes"]["class-a"]["last_session_ref"] = "stale"
    cc.save_lineage(root, before)
    text = _decision("correction", anchor, ["class-a"], checkpoint=True)
    monkeypatch.setattr(engines.CodexEngine, "run", lambda *a, **k: engines.Review(
        text=text, raw=text, session_ref=session,
    ))
    handler = handlers.critique_plan if mode == cc.PLAN_MODE else handlers.critique_branch
    result = handler(args, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "ARCHITECTURE-CHECKPOINT" in result
    after = cc.load_lineage(root, "architecture", stamp="after", mode=mode)
    assert after.review_state["debt"] == before.review_state["debt"]
    assert after.rounds == before.rounds
    assert after.review_state["correction_control"]["classes"]["class-a"]["last_session_ref"] == (session or None)


@pytest.mark.parametrize("mode", [cc.PLAN_MODE, cc.BRANCH_MODE])
def test_checkpoint_ambiguous_save_never_offers_rebut(
    tmp_path, monkeypatch, repo, repo_with_branch, mode,
):
    root, args, anchor = _seed(
        tmp_path, monkeypatch, mode, repo if mode == cc.PLAN_MODE else repo_with_branch,
        last_round=6,
    )
    text = _decision("correction", anchor, ["class-a"], checkpoint=True)
    def run(*a, **k):
        def unavailable(*a, **k):
            raise cc.StateUnavailable("unconfirmed checkpoint")
        monkeypatch.setattr(cc, "save_lineage", unavailable)
        return engines.Review(text=text, raw=text, session_ref="new-session")
    monkeypatch.setattr(engines.CodexEngine, "run", run)
    handler = handlers.critique_plan if mode == cc.PLAN_MODE else handlers.critique_branch
    result = handler(args, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert "STATE-UNAVAILABLE" in result
    assert "CONVERGENCE: NOT-BLOCKED" not in result
    with pytest.raises(cc.StateUnavailable, match="pending write latch"):
        cc.load_lineage(root, "architecture", stamp="after", mode=mode)


def test_public_rebut_wrong_provider_rejects_before_handler(tmp_path, monkeypatch):
    record = {"tool":"query", "engine":"claude", "session_ref":"known",
              "error":False, "returncode":0}
    (tmp_path / "owner.json").write_text(json.dumps(record))
    monkeypatch.setattr(server, "DEFAULT_LOG_DIR", tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("provider must not run")
    monkeypatch.setitem(server._HANDLERS, "rebut", forbidden)
    result = server.dispatch("rebut", {"session_ref":"known", "engine":"codex"},
                             default_engine_name="codex", log_dir=tmp_path)
    assert "belongs to claude" in result


def test_incomplete_audit_requires_explicit_engine_and_nested_content_is_not_owner(tmp_path):
    (tmp_path / "fake.json").write_text(json.dumps({"tool":"query", "raw":{
        "session_ref":"s", "engine":"claude", "error":False, "returncode":0,
    }}))
    assert not session_routing.ownership("s", (tmp_path,)).owners
    (tmp_path / "malformed.json").write_text("{")
    assert session_routing.ownership("s", (tmp_path,)).incomplete
    with pytest.raises(ValueError):
        session_routing.resolve("s", None, (tmp_path,))
    assert session_routing.resolve("s", "codex", (tmp_path,)) == "codex"


def test_trace_binds_schema_and_actual_default_timeout_without_prompt(tmp_path):
    schema = {"type":"object", "properties":{}}
    engine = engines.CodexEngine()
    with telemetry.recording("query", tmp_path):
        engine.run("private prompt", tmp_path, "m", "high", False,
                   response_schema=schema,
                   runner=lambda *a: runner.RunResult(1, "", "failed"))
    data = json.loads(next(tmp_path.glob("*-run-*.json")).read_text())
    row = data["attempts"][0]
    assert row["requested_timeout_sec"] == runner.DEFAULT_TIMEOUT_SEC
    assert row["schema_sha256"] == telemetry.digest(json.dumps(schema, sort_keys=True, separators=(",", ":")))
    assert row["provider_outcome"] == "failed" and row["returncode"] == 1
    assert "private prompt" not in json.dumps(data)


@pytest.mark.parametrize("run", [runner.run_capture, runner.run_streaming])
def test_cancellation_cleans_up_process_group(tmp_path, monkeypatch, run):
    if os.name != "posix":
        pytest.skip("POSIX process-group acceptance")
    import threading
    original = threading.Thread.join
    interrupted = False
    def join(thread, *args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt()
        return original(thread, *args, **kwargs)
    monkeypatch.setattr(threading.Thread, "join", join)
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        run([sys.executable, "-c", "import time; time.sleep(60)"], "", tmp_path, timeout=60)
    assert time.monotonic() - started < 4
