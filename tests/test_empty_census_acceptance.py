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
