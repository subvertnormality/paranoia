import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


def test_class_occurrence_batch_acceptance_is_source_and_route_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/class_occurrence_batch_acceptance_2026-08-30.json"
    assert artifact_path.exists(), "run scripts/run_class_occurrence_batch_acceptance.py"
    spec = importlib.util.spec_from_file_location(
        "class_occurrence_batch_acceptance",
        root / "scripts/run_class_occurrence_batch_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    acceptance.validate_artifact(artifact, root)


@pytest.mark.parametrize("field", [
    "provider", "prompt", "response", "ledger", "outcome", "role", "retry",
    "fixture", "settlement", "lineage", "result", "engine_source",
])
def test_class_occurrence_batch_acceptance_rejects_mutation(field: str) -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/class_occurrence_batch_acceptance_2026-08-30.json"
    spec = importlib.util.spec_from_file_location(
        "class_occurrence_batch_acceptance_mutation",
        root / "scripts/run_class_occurrence_batch_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    if field == "provider":
        artifact["provider"]["model"] = "different-model"
    elif field == "prompt":
        artifact["calls"][-1]["prompt_text"] += " changed"
    elif field == "response":
        artifact["calls"][-1]["response_text"] += " "
    elif field == "ledger":
        artifact["attempt_ledger"][-1]["session_ref"] = "different-session"
    elif field == "outcome":
        artifact["attempt_ledger"][-1]["outcome"] = "validation-invalid"
    elif field == "role":
        artifact["attempt_ledger"][-1]["role"] = "final"
    elif field == "retry":
        artifact["calls"].append(deepcopy(artifact["calls"][-1]))
    elif field == "fixture":
        artifact["fixture"]["head_files"]["worker.conf"] = "MODE = safe\n"
    elif field == "settlement":
        artifact["settlement"]["findings"][0]["summary"] += " changed"
    elif field == "lineage":
        artifact["after_lineage"]["review_state"]["phase"] = "clear"
    elif field == "result":
        artifact["result_text"] += " changed"
    else:
        assert "src/paranoia_local/engines.py" in artifact["source_sha256"]
        artifact["source_sha256"]["src/paranoia_local/engines.py"] = "0" * 64
    with pytest.raises(ValueError):
        acceptance.validate_artifact(artifact, root, require_committed=False)
