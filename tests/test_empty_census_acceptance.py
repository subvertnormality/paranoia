import json
import sys

import pytest

from scripts import run_empty_census_acceptance as acceptance
from tests.conftest import commit_all


def test_freeze_has_exact_balanced_inventory_and_incomplete_report_blocks(
    repo, tmp_path, monkeypatch,
):
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    commit_all(repo, "minimal frozen source")
    monkeypatch.setattr(acceptance.subprocess, "check_output", lambda *args, **kwargs: "fixture CLI\n")
    root = tmp_path / "acceptance"
    acceptance.freeze(root, repo, repo)
    manifest = acceptance.load(root)
    assert len(manifest["order"]) == 12
    assert manifest["maximum_calls"] == 96
    for provider in acceptance.pilot.MODELS:
        for expected, count in (("clear", 4), ("defect", 2)):
            ids = {c["id"] for c in manifest["cases"]
                   if c["provider"] == provider and manifest["oracle"][c["id"]] == expected}
            rows = [r for r in manifest["order"] if r["case"] in ids]
            assert len(rows) == count
            assert sum(r["version"] == "baseline" for r in rows) == count // 2
    # Exercise the actual worker's fixture construction with provider calls replaced
    # only in this harness test; live acceptance never uses this replacement.
    from paranoia_local import server
    monkeypatch.setattr(server, "dispatch", lambda *args, **kwargs: "CONVERGENCE: NOT-BLOCKED")
    monkeypatch.setattr(acceptance.pilot, "install_observer", lambda *args: None)
    saved_path = list(sys.path)
    try:
        for case in manifest["cases"]:
            trial = next(row for row in manifest["order"] if row["case"] == case["id"])
            directory = root / trial["id"]
            acceptance.pilot.worker(directory / "input.json")
            fixture = directory / "repository"
            code = (fixture / "app.py").read_text()
            assert code.endswith("\n") and not code.endswith("\n\n")
            assert acceptance.pilot.git(fixture, "diff", "--check", "main", "HEAD") == ""
            assert acceptance.pilot.git(fixture, "diff", "main", "HEAD", "--", "app.py")
            result = acceptance.subprocess.run(
                [sys.executable, "test_app.py"], cwd=fixture, capture_output=True,
            )
            assert result.returncode == (1 if manifest["oracle"][case["id"]] == "defect" else 0)
    finally:
        sys.path[:] = saved_path
    # A corrected experiment shares admissions rather than obtaining a fresh budget.
    (root / "calls.txt").write_text("46")
    corrected = tmp_path / "corrected"
    acceptance.freeze(corrected, repo, repo, root / "calls.txt")
    assert (root / "calls.txt").read_text() == "46"
    assert acceptance.load(corrected)["admissions_at_freeze"] == 46
    assert acceptance.load(corrected)["counter_path"] == str(root / "calls.txt")
    acceptance.report(root)
    assert json.loads((root / "report.json").read_text())["qualified"] is False
    (root / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="manifest changed"):
        acceptance.load(root)


def test_worker_admission_refuses_the_97th_call_without_reset(tmp_path, monkeypatch):
    counter = tmp_path / "calls.txt"
    counter.write_text("0")

    def worker(spec):
        for expected in range(1, 97):
            assert acceptance.pilot.admit(counter) == expected
        with pytest.raises(RuntimeError, match="BENCHMARK_CALL_LIMIT"):
            acceptance.pilot.admit(counter)
    monkeypatch.setattr(acceptance.pilot, "worker", worker)
    monkeypatch.setattr(sys, "argv", ["acceptance", "--worker", str(tmp_path / "input.json")])
    original = acceptance.pilot.admit
    try:
        acceptance.main()
    finally:
        acceptance.pilot.admit = original
    assert counter.read_text() == "96"
