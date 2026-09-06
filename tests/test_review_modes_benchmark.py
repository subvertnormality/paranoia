from pathlib import Path
import json
import multiprocessing
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_review_modes as bench
import score_review_modes as scoring


def _reserve(counter, queue):
    try:
        queue.put(bench.admit(counter))
    except RuntimeError:
        queue.put("refused")


def test_shared_final_admission_slot(tmp_path):
    counter = tmp_path / "counter"
    counter.write_text("319")
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    workers = [context.Process(target=_reserve, args=(counter, queue)) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
        assert worker.exitcode == 0
    assert {queue.get(timeout=1), queue.get(timeout=1)} == {320, "refused"}
    assert counter.read_text() == "320"


def test_denied_observed_invocation_never_reaches_provider(tmp_path):
    calls = []
    class Engine:
        name = "codex"
        role = "default"
        def run(self, prompt, cwd, model, effort):
            calls.append("run")
        def resume(self, session_ref, prompt, cwd, model, effort):
            calls.append("resume")
    counter = tmp_path / "counter"
    counter.write_text("320")
    bench.install_observer(SimpleNamespace(Engine=Engine), tmp_path, counter)
    with pytest.raises(RuntimeError, match="CALL_LIMIT"):
        Engine().run("p", tmp_path, "m", "high")
    with pytest.raises(RuntimeError, match="CALL_LIMIT"):
        Engine().resume("s", "p", tmp_path, "m", "high")
    assert calls == []
    assert len((tmp_path / "refusals.jsonl").read_text().splitlines()) == 2


def _manifest():
    cases, oracle = bench.corpus()
    return {"schema": 1, "repetitions": 2, "cases": cases, "oracle": oracle,
            "sources": {v: {"revision": "a" * 40, "files": {"x": "b"}} for v in ("baseline", "candidate")},
            "payload_hashes": {c["id"]: bench.sha(json.dumps(c, sort_keys=True)) for c in cases},
            "order": [{"case": c["id"], "version": v, "repetition": r}
                      for c in cases for v in ("baseline", "candidate") for r in range(2)]}


def test_manifest_rejects_tampering_and_missing_trial_before_spend():
    manifest = _manifest()
    bench.validate_manifest(manifest)
    manifest["cases"][0]["files"]["app.py"] += "# changed"
    with pytest.raises(ValueError, match="payload"):
        bench.validate_manifest(manifest)
    manifest = _manifest()
    manifest["order"][-1] = manifest["order"][0]
    with pytest.raises(ValueError, match="trial"):
        bench.validate_manifest(manifest)


@pytest.mark.parametrize("missing", ["session", "provider", "snapshot", "result"])
def test_rebut_setup_requires_bound_authentic_finding(tmp_path, missing):
    setup = {"session": "s", "provider": "codex", "snapshot": "a" * 40,
             "result": "app.py:3 returns 1 for n=2 instead of 3"}
    setup[missing] = None if missing != "result" else ""
    bench.dump(tmp_path / "setup.json", setup)
    with pytest.raises(ValueError, match="unqualified"):
        scoring.qualify(tmp_path, "app.py:3 returns 1 for n=2 instead of 3", "matches oracle")


def test_rebut_qualification_is_exact_output_bound(tmp_path):
    setup = {"session": "s", "provider": "codex", "snapshot": "a" * 40,
             "result": "app.py:3 returns 1 for n=2 instead of 3"}
    bench.dump(tmp_path / "setup.json", setup)
    scoring.qualify(tmp_path, setup["result"], "matches oracle")
    record = json.loads((tmp_path / "qualification.json").read_text())
    assert record["setup_sha256"] == bench.sha((tmp_path / "setup.json").read_bytes())
    assert record["accepted"]
    scoring.qualify(tmp_path, "", "no usable setup", False)
    assert not json.loads((tmp_path / "qualification.json").read_text())["accepted"]


@pytest.mark.parametrize("mode,category,text", [
    ("query", "defect", "app.py:3 is wrong at n=2"),
    ("rebut", "HOLD", "HOLD: app.py:3 is wrong at n=2"),
    ("arbitrate", "inclusive", "ARBITRATION: CONVERGED\nSELECTED: inclusive\n"),
    ("critique_branch", "clear", "CONVERGENCE: NOT-BLOCKED"),
    ("critique_plan", "clear", "CONVERGENCE: NOT-BLOCKED"),
])
def test_mode_scoring_requires_completed_bound_output(tmp_path, mode, category, text):
    bench.dump(tmp_path / "input.json", {"input": {"mode": mode}})
    bench.dump(tmp_path / "status.json", {"status": "completed", "outputs": [{"result": text}]})
    state = tmp_path / "state/lineages"
    state.mkdir(parents=True)
    bench.dump(state / "case.json", {"review_state": {"phase": "clear"}})
    scoring.adjudicate(tmp_path, category, text, "matches the frozen oracle")
    bench.dump(tmp_path / "status.json", {"status": "running", "outputs": [{"result": text}]})
    with pytest.raises(ValueError, match="completed"):
        scoring.adjudicate(tmp_path, category, text, "cannot credit interrupted work")


def test_census_is_not_scored_as_clear(tmp_path):
    bench.dump(tmp_path / "input.json", {"input": {"mode": "critique_branch"}})
    bench.dump(tmp_path / "status.json", {"status": "completed", "outputs": [{"result": "pending final"}]})
    state = tmp_path / "state/lineages"
    state.mkdir(parents=True)
    bench.dump(state / "case.json", {"review_state": {"phase": "final"}})
    with pytest.raises(ValueError, match="pending"):
        scoring.adjudicate(tmp_path, "clear", "pending final", "not completed")


@pytest.mark.parametrize("repaired", [True, False])
def test_worker_carries_authentic_setup_through_prescribed_rebut(tmp_path, monkeypatch, repaired):
    from paranoia_local import server, class_closure as cc
    root = Path(__file__).resolve().parents[1]
    case = next(c for c in bench.corpus()[0] if c["mode"] == "rebut" and bool(c["repair"]) == repaired)
    bench.dump(tmp_path / "input.json", {"input": case, "source": {"path": str(root)},
                                       "models": bench.MODELS, "counter": str(tmp_path / "counter")})
    monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "original"))
    monkeypatch.setattr(bench, "install_observer", lambda *a: None)
    calls = []
    def dispatch(mode, arguments, **kwargs):
        code = (Path(arguments["repo_path"]) / "app.py").read_text()
        calls.append((mode, arguments, code))
        if mode == "query":
            assert code == bench.BAD
            return "app.py:3 returns 1 for n=2 instead of 3.\nsession_ref=`session`"
        assert mode == "rebut" and arguments["session_ref"] == "session"
        return ("CONCEDE" if repaired else "HOLD") + ": app.py:3"
    monkeypatch.setattr(server, "dispatch", dispatch)
    bench.worker(tmp_path / "input.json")
    assert json.loads((tmp_path / "status.json").read_text())["status"] == "setup_pending"
    scoring.qualify(tmp_path, "app.py:3 returns 1 for n=2 instead of 3.", "matches arithmetic oracle")
    bench.worker(tmp_path / "input.json")
    assert [c[0] for c in calls] == ["query", "rebut"]
    assert calls[-1][2] == (bench.GOOD if repaired else bench.BAD)
    assert json.loads((tmp_path / "status.json").read_text())["status"] == "completed"


def test_rejected_setup_never_launches_rebut(tmp_path, monkeypatch):
    from paranoia_local import server, class_closure as cc
    root = Path(__file__).resolve().parents[1]
    case = next(c for c in bench.corpus()[0] if c["mode"] == "rebut")
    bench.dump(tmp_path / "input.json", {"input": case, "source": {"path": str(root)},
                                       "models": bench.MODELS, "counter": str(tmp_path / "counter")})
    monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "original"))
    monkeypatch.setattr(bench, "install_observer", lambda *a: None)
    calls = []
    def dispatch(mode, arguments, **kwargs):
        calls.append(mode)
        return "No relevant finding. session_ref=`session`"
    monkeypatch.setattr(server, "dispatch", dispatch)
    bench.worker(tmp_path / "input.json")
    scoring.qualify(tmp_path, "", "intended finding was absent", False)
    bench.worker(tmp_path / "input.json")
    assert calls == ["query"]
    assert json.loads((tmp_path / "status.json").read_text())["status"] == "setup_unusable"


@pytest.mark.parametrize("revision", ["9bd9b89", "HEAD"])
def test_observer_works_with_each_real_source_revision(tmp_path, revision):
    import io
    import subprocess
    import tarfile
    root = Path(__file__).resolve().parents[1]
    archive = subprocess.run(["git", "archive", revision, "src/paranoia_local"],
                             cwd=root, check=True, capture_output=True).stdout
    source = tmp_path / "source"
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(source, filter="data")
    counter = tmp_path / "counter"
    counter.write_text("0")
    script = """
import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
from paranoia_local import engines, runner
import benchmark_review_modes as bench
directory=Path(sys.argv[3])
engine=engines.get_engine('codex')
engine.build_argv=lambda *a: []
engine.build_resume_argv=lambda *a: []
engine._execute=lambda *a: engines.Review(text='ok',session_ref='s',raw='{}')
bench.install_observer(engines,directory,directory/'counter')
assert not engine.run('p',directory,'m','high',False).error
assert not engine.resume('s','p',directory,'m','high',False).error
rows=[json.loads(l) for l in (directory/'attempts.jsonl').read_text().splitlines()]
assert len(rows)==2
assert all(r['timeout']==runner.DEFAULT_TIMEOUT_SEC for r in rows)
"""
    subprocess.run([sys.executable, "-c", script, str(root / "scripts"),
                    str(source / "src"), str(tmp_path)], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("variant", [0, 1])
def test_plan_fixture_has_actual_scheduler_target(tmp_path, monkeypatch, variant):
    from paranoia_local import server, class_closure as cc
    root = Path(__file__).resolve().parents[1]
    case = [c for c in bench.corpus()[0] if c["mode"] == "critique_plan"][variant]
    bench.dump(tmp_path / "input.json", {"input": case, "source": {"path": str(root)},
                                       "models": bench.MODELS, "counter": str(tmp_path / "counter")})
    monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "original"))
    monkeypatch.setattr(bench, "install_observer", lambda *a: None)
    def dispatch(mode, arguments, **kwargs):
        repo = Path(arguments["repo_path"])
        assert mode == "critique_plan" and arguments["web_search"]
        assert "TestTotal" in (repo / "tests/test_app.py").read_text()
        assert "--dist=loadscope" in (repo / "pytest.ini").read_text()
        assert "pytest-xdist" in (repo / "requirements-dev.txt").read_text()
        return "fixture checked"
    monkeypatch.setattr(server, "dispatch", dispatch)
    bench.worker(tmp_path / "input.json")
