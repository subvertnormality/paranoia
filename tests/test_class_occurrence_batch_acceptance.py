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
    "provider", "provider_effort", "provider_web", "provider_cli", "prompt",
    "prompt_digest", "response", "response_digest", "call_route", "call_session",
    "ledger", "outcome", "role", "attempt_engine", "attempt_sequence",
    "attempt_timeout", "attempt_returncode", "retry", "fixture", "fixture_anchor",
    "fixture_base", "version", "date", "lineage_id", "stakes", "before_rounds",
    "before_next_seq", "before_class", "before_state", "settlement", "lineage",
    "after_rounds", "after_next_seq", "after_class", "after_state", "trailer",
    "result", "engine_source",
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
    elif field == "provider_effort":
        artifact["provider"]["effort"] = "medium"
    elif field == "provider_web":
        artifact["provider"]["web_search"] = True
    elif field == "provider_cli":
        artifact["provider"]["cli_version"] = "codex-cli 0.1.0"
    elif field == "prompt":
        artifact["calls"][-1]["prompt_text"] += " changed"
    elif field == "prompt_digest":
        artifact["calls"][-1]["prompt_sha256"] = "0" * 64
    elif field == "response":
        artifact["calls"][-1]["response_text"] += " "
    elif field == "response_digest":
        artifact["calls"][-1]["response_sha256"] = "0" * 64
    elif field == "call_route":
        artifact["calls"][0]["route"] = "resumed"
    elif field == "call_session":
        artifact["calls"][0]["session_ref"] = "different-session"
    elif field == "ledger":
        artifact["attempt_ledger"][-1]["session_ref"] = "different-session"
    elif field == "outcome":
        artifact["attempt_ledger"][-1]["outcome"] = "validation-invalid"
    elif field == "role":
        artifact["attempt_ledger"][-1]["role"] = "final"
    elif field == "attempt_engine":
        artifact["attempt_ledger"][-1]["engine"] = "claude"
    elif field == "attempt_sequence":
        artifact["attempt_ledger"][-1]["sequence"] = 2
    elif field == "attempt_timeout":
        artifact["attempt_ledger"][-1]["requested_timeout_sec"] = 1
    elif field == "attempt_returncode":
        artifact["attempt_ledger"][-1]["returncode"] = 1
    elif field == "retry":
        artifact["calls"].append(deepcopy(artifact["calls"][-1]))
    elif field == "fixture":
        artifact["fixture"]["head_files"]["worker.conf"] = "MODE = safe\n"
    elif field == "fixture_anchor":
        artifact["fixture"]["expected_anchors"][1] = "repository/worker.conf:2"
    elif field == "fixture_base":
        artifact["fixture"]["base_id"] = "0" * 40
    elif field == "version":
        artifact["version"] = 2
    elif field == "date":
        artifact["date"] = "2026-08-29"
    elif field == "lineage_id":
        artifact["lineage_id"] = "different-lineage"
    elif field == "stakes":
        artifact["stakes"] += " changed"
    elif field == "before_rounds":
        artifact["before_lineage"]["rounds"] = 0
    elif field == "before_next_seq":
        artifact["before_lineage"]["next_seq"] = 3
    elif field == "before_class":
        artifact["before_lineage"]["classes"][0]["invariant"] += " changed"
    elif field == "before_state":
        artifact["before_lineage"]["review_state"]["phase"] = "final"
    elif field == "settlement":
        artifact["settlement"]["findings"][0]["summary"] += " changed"
    elif field == "lineage":
        artifact["after_lineage"]["review_state"]["phase"] = "clear"
    elif field == "after_rounds":
        artifact["after_lineage"]["rounds"] = 1
    elif field == "after_next_seq":
        artifact["after_lineage"]["next_seq"] = 3
    elif field == "after_class":
        artifact["after_lineage"]["classes"][0]["status"] = "closed"
    elif field == "after_state":
        artifact["after_lineage"]["review_state"]["last_round"] = 1
    elif field == "trailer":
        artifact["rendered_trailer"] += " changed"
    elif field == "result":
        artifact["result_text"] += " changed"
    else:
        assert "src/paranoia_local/engines.py" in artifact["source_sha256"]
        artifact["source_sha256"]["src/paranoia_local/engines.py"] = "0" * 64
    with pytest.raises(ValueError):
        acceptance.validate_artifact(artifact, root, require_committed=False)
