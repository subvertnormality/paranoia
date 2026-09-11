"""Preserve original provider evidence while binding later handler differences."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from tests.test_issue115_history import load_test_module

ROOT = Path(__file__).resolve().parents[1]
BASE = "6bd761b"
HANDLER = "src/paranoia_local/handlers.py"
RECORDS = {
    "branch_plan_fidelity_acceptance_2026-08-22.json": None,
    "class_persistence_acceptance_2026-08-22.json": "test_real_code_branch_class_persistence_acceptance_is_source_bound",
    "mechanized_predicate_acceptance_2026-08-27.json": "test_mechanized_predicate_acceptance_is_source_and_route_bound",
}


@pytest.mark.parametrize("name", RECORDS)
def test_only_existing_handler_allowance_metadata_changes(name):
    original = json.loads(subprocess.run(
        ["git", "show", f"{BASE}:docs/{name}"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout)
    current = json.loads((ROOT / "docs" / name).read_text())
    before = original["allowed_later_source_diffs"][HANDLER]
    after = current["allowed_later_source_diffs"][HANDLER]
    assert set(before) == set(after) == {"sha256", "scope"}
    for key in before:
        assert isinstance(after[key], str)
        after[key] = before[key]
    assert current == original


@pytest.mark.parametrize("name", RECORDS)
def test_real_validators_accept_control_and_reject_changed_allowance(name, monkeypatch):
    path = ROOT / "docs" / name
    original = json.loads(path.read_text())
    validator = RECORDS[name]
    def validate(value):
        if validator is None:
            from scripts.build_branch_plan_fidelity_acceptance import validate_record
            validate_record(value, ROOT)
        else:
            read = Path.read_text
            with monkeypatch.context() as patch:
                patch.setattr(Path, "read_text", lambda target, *a, **kw:
                              json.dumps(value) if target == path else read(target, *a, **kw))
                getattr(load_test_module("test_review_census"), validator)()
    validate(original)
    for mutation in ("missing", "extra", "mismatch"):
        value = deepcopy(original)
        allowed = value["allowed_later_source_diffs"]
        if mutation == "missing":
            del allowed[HANDLER]
        elif mutation == "extra":
            allowed["unexpected.py"] = {"sha256": "0" * 64, "scope": "invalid"}
        else:
            allowed[HANDLER]["sha256"] = "0" * 64
        with pytest.raises((ValueError, AssertionError)):
            validate(value)
