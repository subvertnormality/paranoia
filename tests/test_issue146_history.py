import importlib
import json
from pathlib import Path

import pytest

from scripts.acceptance_sources import current_class_source_required
from .test_issue115_history import invoke_existing

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("src/paranoia_local/arbitration_research.py", "src/paranoia_local/external_sources.py")


def test_only_named_unexecuted_modules_are_historical_context():
    for name in MODULES:
        assert not current_class_source_required(name, {})
        assert current_class_source_required(name, {name: {"sha256": "x", "scope": "existing"}})
    assert current_class_source_required("src/paranoia_local/handlers.py", {})
    assert current_class_source_required("src/paranoia_local/other.py", {})


@pytest.mark.parametrize("stem", ["class_occurrence_batch", "persistent_correction_gate", "plan_restatement"])
@pytest.mark.parametrize("module", MODULES)
def test_historical_context_still_rejects_changed_original_source(stem, module):
    path = next((ROOT / "docs").glob(stem + "_acceptance_*.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["source_sha256"][module] = "0" * 64
    validator = importlib.import_module("scripts.run_" + stem + "_acceptance")
    with pytest.raises(ValueError, match="historical source"):
        validator.validate_artifact(record, ROOT, require_committed=False)


@pytest.mark.parametrize("module", MODULES)
def test_keyed_history_still_rejects_changed_original_source(module, monkeypatch, tmp_path):
    name = "keyed_class_handler_acceptance_2026-08-19.json"
    record = json.loads((ROOT / "docs" / name).read_text(encoding="utf-8"))
    record["source_sha256"][module] = "0" * 64
    with pytest.raises(AssertionError):
        invoke_existing(name, record, monkeypatch, tmp_path)
