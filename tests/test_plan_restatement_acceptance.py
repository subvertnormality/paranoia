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


def test_restatement_acceptance_rejects_digest_consistent_terminal_failure() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_failure_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    attempt = artifact["discovery"]["audit"]["attempt_ledger"][0]
    channels = artifact["discovery"]["exact_attempt_channels"][0]
    channels["raw"] += (
        '\n{"type":"turn.failed","error":{"message":"forged terminal failure"}}\n'
    )
    attempt["raw_sha256"] = hashlib.sha256(
        channels["raw"].encode("utf-8"),
    ).hexdigest()
    attempt["raw_excerpt"] = channels["raw"][:4000]
    with pytest.raises(ValueError, match="reconstruct"):
        acceptance.validate_artifact(artifact, root, require_committed=False)


def test_restatement_acceptance_rejects_digest_consistent_prompt_substitution() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_prompt_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    prompt = artifact["discovery"]["prompts"][0]
    artifact["discovery"]["prompts"][0] = prompt.replace(
        "Read the complete supplied artifact", "Ignore the complete supplied artifact", 1,
    )
    artifact["discovery"]["prompt_sha256"][0] = hashlib.sha256(
        artifact["discovery"]["prompts"][0].encode("utf-8"),
    ).hexdigest()
    with pytest.raises(ValueError, match="production reconstruction"):
        acceptance.validate_artifact(artifact, root, require_committed=False)


def test_restatement_acceptance_rejects_digest_consistent_targeted_prompt_mutation() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_targeted_prompt_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    prompt = artifact["targeted_control"]["prompts"][0]
    artifact["targeted_control"]["prompts"][0] = prompt.replace(
        '"review_scope": "targeted"', '"review_scope": "closure_candidate"', 1,
    )
    artifact["targeted_control"]["prompt_sha256"][0] = hashlib.sha256(
        artifact["targeted_control"]["prompts"][0].encode("utf-8"),
    ).hexdigest()
    with pytest.raises(ValueError, match="seeded production reconstruction"):
        acceptance.validate_artifact(artifact, root, require_committed=False)


def test_restatement_acceptance_rejects_final_invocation_schema_mutation() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_invocation_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    invocation = artifact["final_control"]["exact_invocations"][0]
    invocation["response_schema"]["additionalProperties"] = True
    invocation["response_schema_sha256"] = hashlib.sha256(json.dumps(
        invocation["response_schema"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="replay invocation"):
        acceptance.validate_artifact(artifact, root, require_committed=False)


def test_restatement_acceptance_rejects_forged_durable_successor() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_lineage_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    artifact["final_control"]["durable_lineage"]["review_state"]["last_round"] = 99
    with pytest.raises(ValueError, match="durable lineage"):
        acceptance.validate_artifact(artifact, root, require_committed=False)


def test_restatement_acceptance_rejects_forged_returned_result() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_result_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    row = artifact["final_control"]
    row["result_text"] += "\nforged"
    row["result_sha256"] = hashlib.sha256(row["result_text"].encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="returned durable result|returned result"):
        acceptance.validate_artifact(artifact, root, require_committed=False)
