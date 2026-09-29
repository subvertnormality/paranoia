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
)


@pytest.mark.parametrize("prefix", RECORDS)
def test_issue133_refresh_preserves_original_native_evidence(prefix):
    paths = list((ROOT / "docs").glob(prefix + "_acceptance_*.json"))
    assert len(paths) == 1
    path = paths[0]
    original = json.loads(subprocess.run(["git", "show", f"{BASE}:{path.relative_to(ROOT)}"],
                                        cwd=ROOT, check=True, capture_output=True, text=True).stdout)
    current = deepcopy(json.loads(path.read_text()))
    before = original["allowed_later_source_diffs"]
    after = current["allowed_later_source_diffs"]
    assert set(after) == set(before)
    for relative in before:
        assert set(after[relative]) == set(before[relative]) == {"sha256", "scope"}
        assert all(isinstance(value, str) and value for value in after[relative].values())
        after[relative] = before[relative]
    assert current == original
