import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tests.conftest import commit_all, git

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import benchmark_snapshot_materialization as bench


def campaign(repo, tmp_path, monkeypatch):
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "sample.py").write_text("value = 1\n")
    commit_all(repo, "source fixture")
    revision = git(["rev-parse", "HEAD"], repo).strip()
    monkeypatch.setattr(bench, "BASELINE", revision)
    harness = tmp_path / "harness.py"
    harness.write_text("# frozen\n")
    root = tmp_path / "campaign"
    root.mkdir()
    source = bench.source_record(repo)
    fixtures = {key: {"path": str(repo), "snapshot": revision}
                for key in ["repository", "100", "1000", "3000"]}
    manifest = {"schema": 1, "sources": {"baseline": source, "candidate": source},
                "fixtures": fixtures, "harness": {str(harness): bench.shared.sha(harness.read_bytes())},
                "order": bench.order(fixtures), "repetitions": bench.REPETITIONS}
    bench.shared.dump(root / "manifest.json", manifest)
    digest = bench.shared.sha((root / "manifest.json").read_bytes())
    (root / "manifest.sha256").write_text(digest)
    return root, manifest, harness, digest


@pytest.mark.parametrize("kind", ["source", "inventory", "harness", "manifest"])
@pytest.mark.parametrize("later", [False, True])
def test_first_and_later_worker_admission_rejects_ordinary_edits(
    repo, tmp_path, monkeypatch, kind, later,
):
    root, manifest, harness, digest = campaign(repo, tmp_path, monkeypatch)
    def edit():
        if kind == "source":
            (repo / "src/paranoia_local/sample.py").write_text("value = 2\n")
        elif kind == "inventory":
            (repo / "src/paranoia_local/extra.py").write_text("x = 1\n")
        elif kind == "harness":
            harness.write_text("# edited\n")
        else:
            (root / "manifest.json").write_text("{}")
    launched = []
    real_run = bench.subprocess.run
    def launch(argv, **kwargs):
        if argv[0] == "git":
            return real_run(argv, **kwargs)
        index = int(argv[argv.index("--index") + 1])
        launched.append(index)
        bench.shared.dump(root / f"trial-{index:03}.json",
                          {"trial": manifest["order"][index], "status": "complete"})
        edit()
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(bench.subprocess, "run", launch)
    if not later:
        edit()
    if kind == "manifest" and not later:
        with pytest.raises(ValueError, match="manifest"):
            bench.run(root)
        assert not launched
        return
    bench.run(root)
    assert launched == ([0] if later else [])
    rows = [json.loads((root / f"trial-{i:03}.json").read_text())
            for i in range(len(manifest["order"]))]
    assert all(row["status"] == "incomplete" for row in rows[1 if later else 0:])
    if later:
        assert rows[0]["status"] == "complete"


@pytest.mark.parametrize("kind", ["source", "inventory", "harness"])
def test_worker_rechecks_before_import(repo, tmp_path, monkeypatch, kind):
    root, manifest, harness, digest = campaign(repo, tmp_path, monkeypatch)
    if kind == "source":
        (repo / "src/paranoia_local/sample.py").write_text("changed\n")
    elif kind == "inventory":
        (repo / "src/paranoia_local/extra.py").write_text("changed\n")
    else:
        harness.write_text("changed\n")
    before = list(sys.path)
    with pytest.raises(ValueError):
        bench.worker(root, 0, digest)
    assert sys.path == before
    assert not list(root.glob("trial-*.json"))


def test_report_rejects_misbound_success(repo, tmp_path, monkeypatch):
    root, manifest, harness, digest = campaign(repo, tmp_path, monkeypatch)
    for i, trial in enumerate(manifest["order"]):
        bench.shared.dump(root / f"trial-{i:03}.json", {
            "trial": trial, "status": "complete", "source_revision": "wrong",
            "snapshot": manifest["fixtures"][trial["fixture"]]["snapshot"],
        })
    with pytest.raises(ValueError, match="binding"):
        bench.report(root)
