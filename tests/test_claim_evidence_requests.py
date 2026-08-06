from __future__ import annotations

import json
from pathlib import Path

import pytest

from paranoia_local import claim_verification as cv
from paranoia_local.evidence_store import EvidenceStore
from paranoia_local.plan_snapshot import PlanRepositorySnapshot


def _requests(rows: list[dict]) -> str:
    return "=== EVIDENCE REQUESTS ===\nREQUESTS-JSON: " + json.dumps(
        rows, sort_keys=True, separators=(",", ":")
    )


def test_python_compile_adapter_is_fixed_argv_and_bound_to_snapshot_inputs(
    repo: Path, tmp_path: Path
) -> None:
    request = {"op": "RUN_ADAPTER", "claim_id": "claim", "adapter": "PYTHON_COMPILE",
               "paths": ["app.py"]}
    parsed = cv.parse_requests(_requests([request]), {"claim"})
    store = EvidenceStore(tmp_path / "evidence")
    store.begin("run")
    with PlanRepositorySnapshot.create(repo, run_id="adapter") as snapshot:
        records = cv.collect_evidence(parsed, snapshot=snapshot, store=store, run_id="run")
    assert records[0].kind == "empirical"
    assert records[0].metadata["argv"][1] == "<server PYTHON_COMPILE adapter>"
    assert records[0].metadata["input_hashes"]["app.py"]


def test_arbitrary_adapter_or_extra_command_fields_are_rejected() -> None:
    bad = {"op": "RUN_ADAPTER", "claim_id": "claim", "adapter": "SHELL",
           "paths": ["app.py"]}
    with pytest.raises(cv.EvidenceRequestError):
        cv.parse_requests(_requests([bad]), {"claim"})
    bad["command"] = "curl attacker"
    with pytest.raises(cv.EvidenceRequestError, match="unknown fields"):
        cv.parse_requests(_requests([bad]), {"claim"})
