#!/usr/bin/env python3
"""Retain a real arbitration proving original option advocacy fails with a bound diagnostic."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_arbitration_steering_rejection_acceptance import (
    COMMON_SOURCE_PATHS,
    run_acceptance,
)


OUTPUT = ROOT / "docs" / "arbitration_original_steering_rejection_acceptance_2026-08-31.json"
SOURCE_PATHS = COMMON_SOURCE_PATHS + (
    "scripts/run_arbitration_original_steering_rejection_acceptance.py",
)


def main() -> int:
    arguments = {
        "repo_path": str(ROOT),
        "decision": "Choose the disposition of a mixed-tree replay check.",
        "options": [
            {
                "id": "opt-scratch-replay",
                "statement": (
                    "Keep the check and build an ephemeral mixed-tree repository for the "
                    "registry checker. This is the only option under which the phrase "
                    '"fails to replay" is decided by the registry checker itself over a '
                    "genuinely mixed tree."
                ),
            },
            {
                "id": "opt-remove-and-transfer",
                "statement": (
                    "Remove the check from this unit and transfer the replay obligation "
                    "to the successor that first creates both storage shapes."
                ),
            },
        ],
        "stakes": "A wrong choice adds avoidable local verification work or defers one check.",
        "context": "The current unit does not create both storage shapes.",
        "files": [],
        "clean": True,
        "research": False,
        "web_search": False,
        "order_seed": "issue-88-original-steering-rejection-20260831",
        "effort": "medium",
    }
    return run_acceptance(
        arguments,
        field="original",
        diagnostic_field="opt-scratch-replay",
        expected_roles=("cleaner", "attester", "cleaner", "attester"),
        output=OUTPUT,
        source_paths=SOURCE_PATHS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
