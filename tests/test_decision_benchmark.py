"""Fail-closed measurement checks for the frozen arbitration comparison."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from paranoia_local import inert_tree, inert_git
from .conftest import commit_all, git

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("decision_benchmark", SCRIPTS / "benchmark_decision_evidence.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_expected_rendering_covers_bytes_modes_and_markers(repo):
    (repo / "binary.dat").write_bytes(b"\\0\\xff\\n")
    (repo / "empty").write_bytes(b"")
    (repo / "app.py").chmod(0o755)
    (repo / "alias").symlink_to("app.py")
    commit_all(repo, "binary executable and marker")
    head = git(["rev-parse", "HEAD"], repo).strip()
    git(["update-index", "--add", "--cacheinfo", f"160000,{head},module"], repo)
    git(["commit", "-qm", "gitlink"], repo)
    snapshot = git(["rev-parse", "HEAD"], repo).strip()
    expected = bench.expected_rows(repo, snapshot, inert_git)
    with inert_tree.materialized(repo, snapshot) as tree:
        actual = bench.observed_rows(tree.root)
        assert actual == expected
        # The expected rendering is independent of what the measured materializer wrote.
        (tree.repository / "app.py").chmod(0o644)
        (tree.repository / "app.py").write_text("wrong")
        assert bench.observed_rows(tree.root) != expected
        (tree.repository / "app.py").unlink()
        assert bench.observed_rows(tree.root) != expected


@pytest.mark.parametrize("mutation", ["changed", "missing_file", "missing_before", "missing_after",
                                     "missing_expected", "missing_attempt", "wrong_attempt", "cleanup"])
def test_workspace_gate_rejects_missing_or_mismatched_observation(mutation):
    row = {"provider": "codex", "root": "/fixture", "snapshot": "snap",
           "before": "exact", "after": "exact", "expected": "exact", "cleaned_up": True}
    attempts = [{"provider": "codex", "root": "/fixture", "snapshot": "snap", "before": "exact"}]
    assert bench.verify_workspace(row, attempts)
    if mutation in ("changed", "missing_file"):
        row["after"] = mutation
    elif mutation in ("missing_before", "missing_after", "missing_expected"):
        del row[mutation.removeprefix("missing_")]
    elif mutation == "missing_attempt":
        attempts.clear()
    elif mutation == "wrong_attempt":
        attempts[0]["snapshot"] = "other"
    else:
        row["cleaned_up"] = False
    assert not bench.verify_workspace(row, attempts)


def test_source_binding_rejects_package_changes(repo, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    bench.shared.git(source, "init", "-q", "-b", "main")
    bench.shared.git(source, "config", "user.name", "test")
    bench.shared.git(source, "config", "user.email", "test@example.test")
    package = source / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    bench.shared.git(source, "add", ".")
    bench.shared.git(source, "-c", "commit.gpgsign=false", "commit", "-qm", "source")
    record = bench.source_record(source)
    (package / "__init__.py").write_text("# changed")
    with pytest.raises(ValueError, match="source bytes"):
        bench.shared.validate_source(record)


def test_worker_observes_real_dispatch_attempts_and_cleanup(repo, tmp_path, monkeypatch):
    from paranoia_local import engines, arbitrate_handler as ah
    from .test_arbitrate_handler import BASE, Agent, decider_reply
    root = tmp_path / "campaign"
    directory = root / "trial-0"
    directory.mkdir(parents=True)
    (root / "counter").write_text("0")
    source = bench.source_record(SCRIPTS.parent)
    trial = {"version": "candidate", "case": {}}
    manifest = {"sources": {"candidate": source}, "models": {"codex": "m", "claude": "m"}}
    monkeypatch.setattr(bench, "load", lambda *a: (manifest, "frozen"))
    monkeypatch.setattr(bench, "preflight", lambda *a: trial)
    monkeypatch.setattr(ah, "_preflight", lambda *a: None)
    monkeypatch.setattr(engines, "require_evidence_profile", lambda *a: None)
    # Register worker-owned instrumentation mutations for fixture cleanup.
    for owner, name in [(inert_tree, "evidence_workspace"),
                        (inert_tree.EvidenceWorkspace, "cwd_for"),
                        (bench.shared, "install_observer"), (bench.shared, "admit"),
                        (engines.Engine, "run"), (engines.Engine, "resume")]:
        monkeypatch.setattr(owner, name, getattr(owner, name))
    # Earlier replay tests restore inherited methods as subclass attributes.
    # Fresh benchmark workers have no such aliases; remove only identical aliases
    # so the base Engine observer is exercised in the same shape as a fresh import.
    for cls in (engines.CodexEngine, engines.ClaudeEngine):
        for operation in ("run", "resume"):
            if operation in cls.__dict__:
                assert cls.__dict__[operation] is getattr(engines.Engine, operation)
                monkeypatch.delattr(cls, operation)
    scripted = Agent(lambda e, r: "opt-decimal")
    def execute(self, argv, prompt, cwd, *args, **kwargs):
        label = scripted._label_for(prompt, "opt-decimal")
        text = decider_reply(label)
        return engines.Review(text=text, raw=text, session_ref="fixture", returncode=0)
    monkeypatch.setattr(engines.Engine, "_execute", execute)
    def dispatch(spec_path):
        spec = json.loads(spec_path.read_text())
        bench.shared.install_observer(engines, directory, root / "counter")
        result = ah.arbitrate({**BASE, "repo_path": str(repo), "clean": False,
                               "models": spec["models"]}, log_dir=directory / "logs")
        assert "ARBITRATION: CONVERGED" in result
    monkeypatch.setattr(bench.shared, "worker", dispatch)
    bench.worker(root, 0, "frozen")
    trees = json.loads((directory / "workspaces.json").read_text())
    attempts = [json.loads(s) for s in (directory / "attempts.jsonl").read_text().splitlines()]
    assert len(trees["rows"]) == len(trees["provider_attempts"]) == len(attempts) == 2
    assert {a["role"] for a in attempts} == {"evidence-repository"}
    assert all(bench.verify_workspace(r, trees["provider_attempts"]) for r in trees["rows"])
    assert trees["source"] == source and trees["manifest_sha256"] == "frozen"
