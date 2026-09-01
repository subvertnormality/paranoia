from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def test_plan_restatement_acceptance_is_source_and_route_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    assert artifact_path.exists(), "run scripts/run_plan_restatement_acceptance.py"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    acceptance.validate_artifact(
        json.loads(artifact_path.read_text(encoding="utf-8")), root,
    )


def test_restatement_acceptance_rejects_digest_consistent_response_substitution() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    replacement = '{"lane":"domain"}'
    attempt = artifact["discovery"]["audit"]["attempt_ledger"][0]
    channels = artifact["discovery"]["exact_attempt_channels"][0]
    digest = hashlib.sha256(replacement.encode("utf-8")).hexdigest()
    channels["response_text"] = replacement
    attempt["response_sha256"] = digest
    attempt["response_excerpt"] = replacement
    artifact["discovery"]["provider_response_sha256"][0] = digest
    with pytest.raises(ValueError, match="reconstruct"):
        acceptance.validate_artifact(artifact, root, require_committed=False)
