import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


root = Path(__file__).resolve().parents[2]
log_dir = Path(__file__).resolve().parent
for path in log_dir.glob("20260813T*-arbitrate-*.json"):
    path.unlink()

runs = {}
for name, script, stamp in (
    ("original", "docs/cleaning_attestation_evidence/run_original_acceptance.py", "20260813T063000"),
    ("positive", "docs/cleaning_attestation_evidence/run_positive_acceptance.py", "20260813T070000"),
):
    command = [sys.executable, script]
    started = datetime.now(timezone.utc)
    monotonic_start = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        check=False,
    )
    elapsed = time.monotonic() - monotonic_start
    finished = datetime.now(timezone.utc)
    if completed.returncode != 0:
        raise RuntimeError(f"{name}: acceptance driver exited {completed.returncode}")
    matches = list(log_dir.glob(f"{stamp}-arbitrate-*.json"))
    if len(matches) != 1:
        raise RuntimeError(f"{name}: expected one audit, got {matches}")
    audit = root / "docs" / "cleaning_attestation_evidence" / f"{name}-audit.json"
    matches[0].replace(audit)
    runs[name] = {
        "command": ["{python}", *command[1:]],
        "started_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_utc": finished.isoformat().replace("+00:00", "Z"),
        "monotonic_elapsed_seconds": round(elapsed, 3),
        "exit_status": completed.returncode,
        "audit": str(audit.relative_to(root)),
        "audit_sha256": hashlib.sha256(audit.read_bytes()).hexdigest(),
    }

(root / "docs" / "cleaning_attestation_timing_2026-08-13.json").write_text(
    json.dumps(runs, indent=2, sort_keys=True) + "\n", encoding="utf-8",
)
