"""The published qualification must remain attributable to exact source and observations."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_retained_batch_qualification_binds_source_artifacts_and_every_slot():
    def read(name):
        return json.loads((ROOT / "docs" / name).read_text())
    receipt = read("snapshot_batch_requalification_2026-09-06.json")
    for name, row in receipt["artifacts"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == row["sha256"]
    assert hashlib.sha256((ROOT / receipt["plan_path"]).read_bytes()).hexdigest() == receipt["plan_sha256"]
    actual = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (ROOT / "src/paranoia_local").rglob("*.py")}
    assert actual == receipt["production_source_sha256"]
    local = read("snapshot_batch_local_results_2026-09-06.json")
    live = read("snapshot_batch_live_results_2026-09-06.json")
    manifest = read("snapshot_batch_live_manifest_2026-09-06.json")
    assert local["source"] == manifest["sources"]
    assert local["source"]["candidate"]["revision"] == receipt["candidate_revision"]
    assert manifest["expected_baseline"] == receipt["baseline_revision"]
    assert manifest["large_padding"] == 3000
    assert len(local["rows"]) == 40 and all(r["status"] == "complete" for r in local["rows"])
    for fixture, result in local["fixtures"].items():
        assert result["qualified"] and result["equivalent"] and result["reduced_calls"]
        if fixture in {"1000", "3000"}:
            assert result["ratio"] <= 0.5
        elif fixture == "repository":
            assert result["ratio"] <= 1.1
    assert len(live["rows"]) == 8 and live["qualified"] and live["paired_equivalence"]
    assert live["calls"] == live["cumulative_calls"] == receipt["actual_calls"] == 32
    assert live["ledger_complete"]
    for row in live["rows"]:
        assert row["qualified"] and row["bound"] and row["workspace_ok"]
        assert not row["false_convergence"]
        path = ROOT / "docs/snapshot_batch_audits_2026-09-06" / f"trial-{row['index']}.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["audit_sha256"]
    assert all(s["correct"] == 4 and s["provider_calls"] == 16 for s in live["summary"].values())
