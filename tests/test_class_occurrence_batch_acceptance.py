import importlib.util
import json
from pathlib import Path


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
