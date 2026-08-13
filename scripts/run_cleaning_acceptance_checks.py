#!/usr/bin/env python3
"""Run the cleaning-attestation release tests and persist their exact terminals."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "cleaning_attestation_evidence"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    runs = {}
    specs = {
        "focused": [
            sys.executable, "-m", "pytest", "-q",
            "tests/test_arbitrate_handler.py", "tests/test_acceptance_validator.py",
        ],
        "full": [sys.executable, "-m", "pytest", "-q"],
    }
    for name, command in specs.items():
        started = _utc()
        monotonic_start = time.monotonic()
        environment = {
            **os.environ,
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "commit.gpgsign",
            "GIT_CONFIG_VALUE_0": "false",
        }
        completed = subprocess.run(
            command, cwd=ROOT, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        finished = _utc()
        log = EVIDENCE / f"{name}-tests.log"
        log.write_text(completed.stdout, encoding="utf-8")
        runs[name] = {
            "command": ["{python}", *command[1:]],
            "started_utc": started,
            "finished_utc": finished,
            "monotonic_elapsed_seconds": round(time.monotonic() - monotonic_start, 3),
            "exit_status": completed.returncode,
            "log": str(log.relative_to(ROOT)),
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            "terminal": completed.stdout.strip().splitlines()[-1],
        }
        if completed.returncode:
            break
    manifest = EVIDENCE / "test-runner-manifest.json"
    manifest.write_text(
        json.dumps(runs, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return next((row["exit_status"] for row in runs.values() if row["exit_status"]), 0)


if __name__ == "__main__":
    raise SystemExit(main())
