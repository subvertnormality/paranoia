from pathlib import Path
import json
import multiprocessing
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_review_modes as bench
import score_review_modes as scoring



def _source_record(root):
    return {"path": str(root), "revision": bench.git(root, "rev-parse", "HEAD"),
            "files": {str(p.relative_to(root)): bench.sha(p.read_bytes())
                      for p in sorted((root / "src/paranoia_local").glob("*.py"))}}


def _native_result(directory, mode, text, *, session="session", provider="codex",
                   error=False, returncode=0):
    from paranoia_local.engines import Review
    from paranoia_local.handlers import _footer
    review = Review(text=text, session_ref=session, raw="", error=error, returncode=returncode)
    (directory / "logs").mkdir(exist_ok=True)
    bench.dump(directory / "logs" / (mode + ".json"), {
        "tool": mode, "engine": provider, "text": text, "session_ref": session,
        "error": error, "returncode": returncode,
    })
    return _footer(review, SimpleNamespace(name=provider))


def _reserve(counter, queue):
    try:
        queue.put(bench.admit(counter))
    except RuntimeError:
        queue.put("refused")


@pytest.mark.skipif(os.name != "posix", reason="Linux/WSL pilot uses POSIX file locking")
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


@pytest.mark.skipif(os.name != "posix", reason="Linux/WSL pilot uses POSIX file locking")
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
             "result": _native_result(tmp_path, "query", "app.py:3 returns 1 for n=2 instead of 3",
                                      session="s")}
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
    if mode in {"query", "rebut"}:
        text = _native_result(tmp_path, mode, text)
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
    bench.dump(tmp_path / "input.json", {"input": case, "source": _source_record(root),
                                       "models": bench.MODELS, "counter": str(tmp_path / "counter")})
    monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "original"))
    monkeypatch.setattr(bench, "install_observer", lambda *a: None)
    calls = []
    def dispatch(mode, arguments, **kwargs):
        code = (Path(arguments["repo_path"]) / "app.py").read_text()
        calls.append((mode, arguments, code))
        if mode == "query":
            assert code == bench.BAD
            return _native_result(tmp_path, mode, "app.py:3 returns 1 for n=2 instead of 3.",
                                  provider=case["provider"])
        assert mode == "rebut" and arguments["session_ref"] == "session"
        return _native_result(tmp_path, mode, ("CONCEDE" if repaired else "HOLD") + ": app.py:3",
                              provider=case["provider"])
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
    bench.dump(tmp_path / "input.json", {"input": case, "source": _source_record(root),
                                       "models": bench.MODELS, "counter": str(tmp_path / "counter")})
    monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "original"))
    monkeypatch.setattr(bench, "install_observer", lambda *a: None)
    calls = []
    def dispatch(mode, arguments, **kwargs):
        calls.append(mode)
        return _native_result(tmp_path, mode, "No relevant finding.", provider=case["provider"])
    monkeypatch.setattr(server, "dispatch", dispatch)
    bench.worker(tmp_path / "input.json")
    scoring.qualify(tmp_path, "", "intended finding was absent", False)
    bench.worker(tmp_path / "input.json")
    assert calls == ["query"]
    assert json.loads((tmp_path / "status.json").read_text())["status"] == "setup_unusable"


@pytest.mark.parametrize("revision", ["9bd9b89", "HEAD"])
@pytest.mark.skipif(os.name != "posix", reason="Linux/WSL pilot uses POSIX file locking")
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
    bench.dump(tmp_path / "input.json", {"input": case, "source": _source_record(root),
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


@pytest.mark.parametrize("severity", ["FATAL", "BLOCKER", "MAJOR"])
def test_scorer_uses_canonical_blocking_severities(tmp_path, severity):
    bench.dump(tmp_path / "input.json", {"input": {"mode": "critique_branch"}})
    bench.dump(tmp_path / "status.json", {"status": "completed", "outputs": [{"result": "app.py:3 is wrong"}]})
    directory = tmp_path / "state/lineages"
    directory.mkdir(parents=True)
    bench.dump(directory / "case.json", {"review_state": {
        "phase": "correction", "debt": [{"status": "open", "severity": severity}]}})
    scoring.adjudicate(tmp_path, "defect", "app.py:3 is wrong", "matches oracle")


def test_structural_clear_is_not_full_plan_clear(tmp_path):
    bench.dump(tmp_path / "input.json", {"input": {"mode": "critique_plan"}})
    text = "STRUCTURAL-CONVERGENCE: NOT-BLOCKED\nCONVERGENCE: BLOCKED"
    bench.dump(tmp_path / "status.json", {"status": "completed", "outputs": [{"result": text}]})
    directory = tmp_path / "state/lineages"
    directory.mkdir(parents=True)
    bench.dump(directory / "case.json", {"review_state": {"phase": "clear"},
                                       "claim_state": {"claims": {"c": {"verdict": "refuted"}}}})
    with pytest.raises(ValueError, match="pending"):
        scoring.adjudicate(tmp_path, "clear", text, "must not credit structural-only result")


def test_finding_adjudication_binds_exact_audit(tmp_path):
    directory = tmp_path / "logs"
    directory.mkdir()
    audit = {"staged_settlement": {"findings": [
        {"id": "f", "severity": "MAJOR", "summary": "wrong formula", "evidence": ["app.py:3"]}]}}
    path = directory / "audit.json"
    bench.dump(path, audit)
    key = scoring.findings(tmp_path)[0]["key"]
    scoring.annotate_finding(tmp_path, key, "true_defect", "matches seeded formula failure")
    assert scoring.findings(tmp_path)[0]["classification"] == "true_defect"
    audit["changed"] = True
    bench.dump(path, audit)
    with pytest.raises(ValueError, match="bind"):
        scoring.findings(tmp_path)


def test_report_retains_unstarted_and_interrupted_slots(tmp_path):
    manifest = _manifest()
    for index, trial in enumerate(manifest["order"]):
        trial["id"] = f"t{index:03}"
        directory = tmp_path / trial["id"]
        directory.mkdir()
        bench.dump(directory / "status.json",
                   {"status": "incomplete_interrupted" if index == 0 else "unstarted"})
    bench.dump(tmp_path / "manifest.json", manifest)
    (tmp_path / "manifest.sha256").write_text(bench.sha((tmp_path / "manifest.json").read_bytes()))
    scoring.report(tmp_path)
    report = json.loads((tmp_path / "report.json").read_text())
    assert len(report["trials"]) == 40
    assert report["trials"][0]["status"] == "incomplete_interrupted"
    assert all(row["category"] == "unscored" for row in report["trials"])


def test_rebut_worker_rejects_ordinary_uncommitted_edit(tmp_path, monkeypatch):
    from paranoia_local import server, class_closure as cc
    root = Path(__file__).resolve().parents[1]
    case = next(c for c in bench.corpus()[0] if c["mode"] == "rebut")
    bench.dump(tmp_path / "input.json", {"input": case, "source": _source_record(root),
                                       "models": bench.MODELS, "counter": str(tmp_path / "counter")})
    monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "original"))
    monkeypatch.setattr(bench, "install_observer", lambda *a: None)
    calls = []
    def dispatch(mode, arguments, **kwargs):
        calls.append(mode)
        return _native_result(tmp_path, mode, "app.py:3 returns 0 instead of 1 at n=1.",
                              provider=case["provider"])
    monkeypatch.setattr(server, "dispatch", dispatch)
    bench.worker(tmp_path / "input.json")
    scoring.qualify(tmp_path, "app.py:3 returns 0 instead of 1 at n=1.", "matches the intended defect")
    (tmp_path / "repository/app.py").write_text("ordinary edit\n")
    with pytest.raises(ValueError, match="binding changed"):
        bench.worker(tmp_path / "input.json")
    assert calls == ["query"]


def test_new_source_module_invalidates_frozen_inventory(tmp_path, monkeypatch):
    manifest = _manifest()
    source = tmp_path / "source"
    package = source / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "a.py").write_text("a=1\n")
    for row in manifest["sources"].values():
        row.update(path=str(source), files={"src/paranoia_local/a.py": bench.sha("a=1\n")})
    manifest.update(cli_versions={}, harness_sha256=bench.sha(Path(bench.__file__).read_bytes()))
    bench.dump(tmp_path / "manifest.json", manifest)
    (tmp_path / "manifest.sha256").write_text(bench.sha((tmp_path / "manifest.json").read_bytes()))
    (package / "b.py").write_text("b=2\n")
    monkeypatch.setattr(bench, "git", lambda *a: "a" * 40)
    with pytest.raises(ValueError, match="inventory"):
        bench.run(SimpleNamespace(output=tmp_path))


@pytest.mark.parametrize("mode,category", [("query", "defect"), ("rebut", "HOLD")])
@pytest.mark.parametrize("error,returncode", [(True, 7), (True, 0), (False, 7)])
def test_failed_execution_with_creditable_text_cannot_be_scored(
    tmp_path, mode, category, error, returncode,
):
    text = _native_result(tmp_path, mode, "HOLD: app.py:3 is wrong at n=2",
                          error=error, returncode=returncode)
    bench.dump(tmp_path / "input.json", {"input": {"mode": mode}})
    bench.dump(tmp_path / "status.json", {"status": "completed", "outputs": [{"result": text}]})
    for proposed in [category, "wrong_answer"]:
        with pytest.raises(bench.ExecutionEvidenceError, match="failed execution"):
            scoring.adjudicate(tmp_path, proposed, text, "retained text matches the oracle")
    assert not (tmp_path / "score.json").exists()


@pytest.mark.parametrize("error,returncode", [(True, 7), (True, 0)])
def test_failed_setup_cannot_qualify_or_resume_even_with_legacy_approval(
    tmp_path, monkeypatch, error, returncode,
):
    from paranoia_local import server, class_closure as cc
    root = Path(__file__).resolve().parents[1]
    case = next(c for c in bench.corpus()[0] if c["mode"] == "rebut")
    bench.dump(tmp_path / "input.json", {"input": case, "source": _source_record(root),
                                       "models": bench.MODELS, "counter": str(tmp_path / "counter")})
    monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "original"))
    monkeypatch.setattr(bench, "install_observer", lambda *a: None)
    calls = []

    def dispatch(mode, arguments, **kwargs):
        calls.append(mode)
        assert mode == "query"
        return _native_result(tmp_path, mode, "app.py:3 returns 0 instead of 1 at n=1.",
                              provider=case["provider"], error=error, returncode=returncode)

    monkeypatch.setattr(server, "dispatch", dispatch)
    bench.worker(tmp_path / "input.json")
    assert json.loads((tmp_path / "status.json").read_text())["status"] == "setup_unusable"
    setup = json.loads((tmp_path / "setup.json").read_text())
    assert setup["elapsed_ms"] >= 0
    with pytest.raises(bench.ExecutionEvidenceError, match="failed execution"):
        scoring.qualify(tmp_path, "app.py:3 returns 0 instead of 1 at n=1.", "matches defect")
    bench.dump(tmp_path / "qualification.json", {
        "accepted": True, "setup_sha256": bench.sha((tmp_path / "setup.json").read_bytes()),
    })
    bench.worker(tmp_path / "input.json")
    assert calls == ["query"]
    assert json.loads((tmp_path / "status.json").read_text())["status"] == "setup_unusable"


@pytest.mark.parametrize("changed", ["output", "session", "provider", "missing", "ambiguous"])
def test_execution_evidence_requires_exact_output_and_authority(tmp_path, changed):
    text = _native_result(tmp_path, "query", "app.py:3 is wrong", session="s")
    kwargs = {"session": "s", "provider": "codex"}
    if changed == "output":
        text += " altered"
    elif changed == "session":
        kwargs["session"] = "other"
    elif changed == "provider":
        kwargs["provider"] = "claude"
    elif changed == "missing":
        (tmp_path / "logs/query.json").unlink()
    else:
        (tmp_path / "logs/duplicate.json").write_bytes((tmp_path / "logs/query.json").read_bytes())
    with pytest.raises(bench.ExecutionEvidenceError, match="exact execution audit"):
        bench.require_successful_review(tmp_path, "query", text, **kwargs)


def test_report_revalidates_failed_stored_credit_and_retains_costs(tmp_path):
    manifest = _manifest()
    chosen = None
    for index, trial in enumerate(manifest["order"]):
        trial["id"] = f"t{index:03}"
        directory = tmp_path / trial["id"]
        directory.mkdir()
        bench.dump(directory / "status.json", {"status": "unstarted"})
        if chosen is None and manifest["oracle"][trial["case"]]["mode"] == "query":
            chosen = (trial, directory)
    trial, directory = chosen
    text = _native_result(directory, "query", "app.py:3 is wrong at n=2", error=True, returncode=0)
    bench.dump(directory / "status.json", {"status": "completed",
                                          "outputs": [{"result": text, "elapsed_ms": 125}]})
    bench.dump(directory / "score.json", {"category": manifest["oracle"][trial["case"]]["expected"],
                                        "quote": text, "reason": "old text-only credit",
                                        "result_sha256": bench.sha(text)})
    (directory / "attempts.jsonl").write_text(json.dumps({"role": "default", "elapsed_ms": 111}) + "\n")
    bench.dump(tmp_path / "manifest.json", manifest)
    (tmp_path / "manifest.sha256").write_text(bench.sha((tmp_path / "manifest.json").read_bytes()))
    scoring.report(tmp_path)
    report = json.loads((tmp_path / "report.json").read_text())
    row = next(r for r in report["trials"] if r["id"] == trial["id"])
    assert row["category"] == "operational_failure" and not row["correct"]
    assert row["submitted_category"] == manifest["oracle"][trial["case"]]["expected"]
    assert row["calls"] == 1 and row["total_dispatch_ms"] == 125
    assert report["summary"][trial["version"]]["operational_failures"] == 1
    assert json.loads((directory / "score.json").read_text())["category"] == row["submitted_category"]


@pytest.mark.parametrize("changed", ["revision", "inventory", "bytes"])
def test_worker_rejects_source_drift_before_import(repo, tmp_path, changed):
    from tests.conftest import commit_all
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    commit_all(repo, "source fixture")
    frozen = _source_record(repo)
    if changed == "revision":
        (repo / "note.txt").write_text("new commit")
        commit_all(repo, "source moved")
    elif changed == "inventory":
        (package / "new.py").write_text("added = True")
    else:
        (package / "__init__.py").write_text("edited = True")
    bench.dump(tmp_path / "input.json", {"source": frozen})
    before = list(sys.path)
    with pytest.raises(ValueError, match="source "):
        bench.worker(tmp_path / "input.json")
    assert sys.path == before
    assert not (tmp_path / "repository").exists()


@pytest.mark.parametrize("adapter", ["five-mode", "empty-census"])
@pytest.mark.parametrize("changed", ["source", "harness"])
def test_campaign_refuses_later_launch_after_binding_drift(
    repo, tmp_path, monkeypatch, adapter, changed,
):
    from tests.conftest import commit_all
    if adapter == "empty-census":
        from scripts import run_empty_census_acceptance as launcher
        common = launcher.pilot
    else:
        launcher = common = bench
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    module = package / "__init__.py"
    module.write_text("")
    commit_all(repo, "campaign source")
    driver = tmp_path / "driver.py"
    driver.write_text("# frozen launcher")
    monkeypatch.setattr(launcher, "__file__", str(driver))
    root = tmp_path / "campaign"
    monkeypatch.setattr(common.subprocess, "check_output", lambda *a, **k: "fixture CLI\n")
    real_run = common.subprocess.run
    launches = []

    def launch(command, **kwargs):
        if command[0] != sys.executable:
            return real_run(command, **kwargs)
        directory = Path(command[-1]).parent
        launches.append(directory.name)
        common.dump(directory / "status.json", {"status": "completed"})
        (module if changed == "source" else driver).write_text("# edited during earlier trial")
        return SimpleNamespace(returncode=0)

    if adapter == "empty-census":
        launcher.freeze(root, repo, repo)
    else:
        root.mkdir()
        manifest = _manifest()
        manifest.update(sources={v: _source_record(repo) for v in ("baseline", "candidate")},
                        models=bench.MODELS, cli_versions={}, harness_sha256=bench.sha(driver.read_bytes()),
                        counter_path=str(root / "calls.txt"))
        for index, trial in enumerate(manifest["order"]):
            trial["id"] = f"t{index+1:03}"
            (root / trial["id"]).mkdir()
            common.dump(root / trial["id"] / "status.json", {"status": "unstarted"})
        common.dump(root / "manifest.json", manifest)
        (root / "manifest.sha256").write_text(common.sha((root / "manifest.json").read_bytes()))
        (root / "calls.txt").write_text("0")

        class OrderedPool:
            def __init__(self, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def map(self, function, rows):
                return map(function, rows)
        monkeypatch.setattr(common, "ThreadPoolExecutor", OrderedPool)
    monkeypatch.setattr(common.subprocess, "run", launch)
    if adapter == "empty-census":
        launcher.run(root)
    else:
        launcher.run(SimpleNamespace(output=root))
    assert launches == ["t001"]
    states = [json.loads(p.read_text()) for p in sorted(root.glob("t*/status.json"))]
    assert states[0]["status"] == "completed"
    assert all(s["status"] == "incomplete_binding_changed" for s in states[1:])
    assert (root / "calls.txt").read_text() == "0"
