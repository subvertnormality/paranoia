import importlib.util
import json
from pathlib import Path


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
