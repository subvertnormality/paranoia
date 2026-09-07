"""Frozen baseline equivalence plus local pure decision boundaries."""
import hashlib
import json
from pathlib import Path
from scripts.lifecycle_matrix import fingerprints
from paranoia_local.lifecycle_decisions import ClassState, derive, action_issues, concession_issues

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_lifecycle_matrix_matches_exact_baseline():
    receipt = json.loads((ROOT / "docs/lifecycle_equivalence_baseline.json").read_text())
    assert hashlib.sha256((ROOT / "scripts/lifecycle_matrix.py").read_bytes()).hexdigest() == receipt["matrix_sha256"]
    rows = fingerprints()
    assert len(rows) == receipt["cases"]
    assert sum(row["outcome"] == "accepted" for row in rows.values()) == receipt["accepted"]
    assert hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest() == receipt["fingerprints_sha256"]


def test_derived_transition_is_pure_and_carries_authored_pointer():
    state = ClassState("c", "closed", "MAJOR", False)
    outcome = {"verdict": "violated"}
    result = derive(state, outcome, None, outcome_pointer="/outcomes/c",
                    action_pointer=None, missing_action_pointer="/actions/c")
    assert result.actions == (({"kind": "reopen", "class_id": "c"}, "/outcomes/c"),)
    assert result.issues == ()
    assert outcome == {"verdict": "violated"}
    assert state.status == "closed"


def test_explicit_action_and_concession_remain_independent_checks():
    state = ClassState("c", "open", "MAJOR", True)
    action = {"kind": "replace", "definition": {"severity": "MINOR", "procedure": "inspect"}}
    issues = action_issues(state, action, None, "/actions/c")
    assert issues == (
        "/actions/c: cannot downgrade active class",
        "/actions/c/definition: mechanized class replacement requires pattern and pathspec",
    )
    assert concession_issues(None, targeted=True, expected_debt="D1", pointer="/challenges/c") == (
        "/challenges/c: newly targeting a conceded class requires an evidence-backed concession challenge",
    )
