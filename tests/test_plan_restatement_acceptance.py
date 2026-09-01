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


def test_restatement_acceptance_rejects_artifact_owned_response_projection() -> None:
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
    channels = artifact["discovery"]["exact_attempt_channels"][0]
    channels["response_text"] = '{"lane":"domain"}'
    with pytest.raises(ValueError, match="channel envelope"):
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
    attempt = artifact["discovery"]["audit_projection"]["attempt_ledger"][0]
    channels = artifact["discovery"]["exact_attempt_channels"][0]
    channels["raw"] += (
        '\n{"type":"turn.failed","error":{"message":"forged terminal failure"}}\n'
    )
    attempt["raw_sha256"] = hashlib.sha256(
        channels["raw"].encode("utf-8"),
    ).hexdigest()
    attempt["raw_excerpt"] = channels["raw"][:4000]
    with pytest.raises(ValueError, match="derive from raw provider stdout|reconstruct"):
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


def test_restatement_acceptance_rejects_forged_provider_route() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_provider_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    artifact["provider"]["effort"] = "low"
    with pytest.raises(ValueError, match="provider route"):
        acceptance.validate_artifact(artifact, root, require_committed=False)


def test_restatement_acceptance_rejects_forged_audit_telemetry() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_audit_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    artifact["final_control"]["audit_projection"]["attempt_ledger"][0]["sequence"] = 99
    with pytest.raises(ValueError, match="audit settlement"):
        acceptance.validate_artifact(artifact, root, require_committed=False)


def test_restatement_acceptance_rejects_digest_consistent_stderr_injection() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_stderr_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    channels = artifact["final_control"]["exact_attempt_channels"][0]
    attempt = artifact["final_control"]["audit_projection"]["attempt_ledger"][0]
    channels["stderr"] = "forged provider warning"
    attempt["stderr_sha256"] = hashlib.sha256(
        channels["stderr"].encode("utf-8"),
    ).hexdigest()
    attempt["stderr_excerpt"] = channels["stderr"]
    with pytest.raises(ValueError, match="channel envelope"):
        acceptance.validate_artifact(artifact, root, require_committed=False)


def test_restatement_acceptance_rejects_nonzero_retained_returncode() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_returncode_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    artifact["final_control"]["exact_attempt_channels"][0]["returncode"] = 17
    artifact["final_control"]["audit_projection"]["attempt_ledger"][0][
        "returncode"
    ] = 17
    with pytest.raises(
        ValueError, match="reconstruct audit settlement|reconstruct returned result|engine failed",
    ):
        acceptance.validate_artifact(artifact, root, require_committed=False)


@pytest.mark.parametrize("forged_returncode", [False, 0.0])
def test_restatement_acceptance_rejects_noninteger_retained_returncode(
    forged_returncode: object,
) -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "docs/plan_restatement_acceptance_2026-09-01.json"
    spec = importlib.util.spec_from_file_location(
        "plan_restatement_acceptance_returncode_type_mutation",
        root / "scripts/run_plan_restatement_acceptance.py",
    )
    assert spec and spec.loader
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    artifact = deepcopy(json.loads(artifact_path.read_text(encoding="utf-8")))
    artifact["final_control"]["exact_attempt_channels"][0][
        "returncode"
    ] = forged_returncode
    artifact["final_control"]["audit_projection"]["attempt_ledger"][0][
        "returncode"
    ] = forged_returncode
    with pytest.raises(ValueError, match="return code must be an exact integer"):
        acceptance.validate_artifact(artifact, root, require_committed=False)
