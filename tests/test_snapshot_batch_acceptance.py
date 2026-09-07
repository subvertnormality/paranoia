"""The published qualification must remain attributable to exact source and observations."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_retained_batch_qualification_binds_source_artifacts_and_every_slot():
    def read(name):
        return json.loads((ROOT / "docs" / name).read_text())
    receipt = read("snapshot_batch_corrected_qualification_2026-09-07.json")
    for name, row in receipt["artifacts"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == row["sha256"]
    assert hashlib.sha256((ROOT / receipt["plan_path"]).read_bytes()).hexdigest() == receipt["plan_sha256"]
    # Later independent changes do not turn historical runs into current acceptance.
    revision = receipt["candidate_revision"]
    names = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", revision, "src/paranoia_local"],
        cwd=ROOT, text=True,
    ).splitlines()
    actual = {name: hashlib.sha256(subprocess.check_output(
        ["git", "show", f"{revision}:{name}"], cwd=ROOT,
    )).hexdigest() for name in names if name.endswith(".py")}
    assert actual == receipt["production_source_sha256"]
    local = read("snapshot_batch_corrected_local_results_2026-09-07.json")
    live = read("snapshot_batch_corrected_live_results_2026-09-07.json")
    manifest = read("snapshot_batch_corrected_live_manifest_2026-09-07.json")
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
    assert live["calls"] == receipt["actual_calls"] == 32
    assert live["cumulative_calls"] == receipt["cumulative_calls"] == 64
    assert live["ledger_complete"]
    for row in live["rows"]:
        assert row["qualified"] and row["bound"] and row["workspace_ok"]
        assert not row["false_convergence"]
        path = ROOT / "docs/snapshot_batch_corrected_audits_2026-09-07" / f"trial-{row['index']}.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["audit_sha256"]
    assert all(s["correct"] == 4 and s["provider_calls"] == 16 for s in live["summary"].values())


    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import benchmark_review_modes as shared
    channels = 0
    for row in live["rows"]:
        directory = ROOT / "docs/snapshot_batch_corrected_channels_2026-09-07" / f"trial-{row['index']}"
        for attempt in row["attempts"]:
            shared.validate_channels(directory, attempt)
            channels += len(attempt["process_channels"])
    assert channels == receipt["process_channels"]["count"] == 96
    assert receipt["report_custody"]["source_entry_replay_byte_identical"]
    assert (ROOT / "docs/snapshot_batch_corrected_report_replay_2026-09-07.json").read_bytes() == (
        ROOT / "docs/snapshot_batch_corrected_live_results_2026-09-07.json").read_bytes()
    for path, digest in manifest["harness"].items():
        assert hashlib.sha256((ROOT / "scripts" / Path(path).name).read_bytes()).hexdigest() == digest
    old = read("snapshot_batch_requalification_2026-09-06.json")
    assert old["release_gate_passed"] is False and len(old["post_review_limitations"]) == 3
    assert not receipt["historical_campaign"]["qualifies_delivery"]
