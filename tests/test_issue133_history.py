"""Later source metadata never rewrites the original native provider evidence."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = "bdeb5d16a2614bf2e488493a75088fabc67b754f"
RECORDS = (
    "arbitration_consequence", "arbitration_context_steering_rejection", "arbitration_steering_rejection",
    "branch_plan_fidelity", "class_occurrence_batch", "class_persistence", "keyed_class_handler",
    "mechanized_predicate", "persistent_correction_gate", "plan_restatement", "plan_review_reliability",
    "authoritative_capture",
)


def _restore_allowances(before, after):
    for key, value in before.items():
        if key == "allowed_later_source_diffs":
            assert set(after[key]) == set(value)
            for relative, row in value.items():
                assert set(after[key][relative]) == set(row) == {"sha256", "scope"}
                assert all(isinstance(item, str) and item for item in after[key][relative].values())
            after[key] = value
        elif key in {"allowed_later_handlers_diff", "allowed_later_review_census_diff", "allowed_later_plan_claims_diff"}:
            assert set(after[key]) == set(value)
            assert {"sha256", "scope"} <= set(value) <= {"sha256", "scope", "additions", "deletions"}
            assert all(type(after[key][field]) is type(item) for field, item in value.items())
            assert after[key]["sha256"] and after[key]["scope"]
            after[key] = value
        elif isinstance(value, dict):
            _restore_allowances(value, after[key])


@pytest.mark.parametrize("prefix", RECORDS)
def test_issue133_refresh_preserves_original_native_evidence(prefix):
    paths = list((ROOT / "docs").glob(prefix + "_acceptance_*.json"))
    assert len(paths) == 1
    path = paths[0]
    original = json.loads(subprocess.run(["git", "show", f"{BASE}:{path.relative_to(ROOT)}"],
                                        cwd=ROOT, check=True, capture_output=True, text=True).stdout)
    current = deepcopy(json.loads(path.read_text()))
    _restore_allowances(original, current)
    assert current == original
