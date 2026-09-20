from __future__ import annotations

import copy

import pytest

from paranoia_local import patch_experiments as pe


def receipt():
    return {
        "mode": "branch",
        "public_activations": 1,
        "settled_state_sha256": "state",
        "explicit_false_state_sha256": "state",
        "rendered_trailer_sha256": "trailer",
        "explicit_false_trailer_sha256": "trailer",
        "review_audit": "review.json",
        "proposal_audit": "proposal.json",
        "reviewed_snapshot": "snapshot",
        "proposal_snapshot": "snapshot",
        "author_session_ref": "lane-session",
        "proposal_requested_session_ref": "lane-session",
        "proposal_attempt_count": 1,
        "workspace_alive_during_proposal": True,
        "workspace_cleaned_after_return": True,
    }


def interval(owner, role, start, end, source):
    return {
        "owner": owner, "role": role, "start": start, "end": end,
        "source_identity": source,
    }


def test_handoff_receipt_binds_state_trailer_snapshot_session_and_cleanup():
    pe.validate_handoff_receipt(receipt())
    mutations = {
        "public_activations": 2,
        "settled_state_sha256": "different",
        "rendered_trailer_sha256": "different",
        "proposal_audit": "review.json",
        "proposal_snapshot": "different",
        "proposal_requested_session_ref": "different",
        "proposal_attempt_count": 3,
        "workspace_alive_during_proposal": False,
        "workspace_cleaned_after_return": False,
    }
    for key, value in mutations.items():
        changed = receipt()
        changed[key] = value
        with pytest.raises(pe.ExperimentError):
            pe.validate_handoff_receipt(changed)
    changed = receipt()
    changed["extra"] = True
    with pytest.raises(pe.ExperimentError, match="closed and exact"):
        pe.validate_handoff_receipt(changed)


def test_interval_ledger_excludes_scheduler_waits_in_both_arm_orders():
    baseline_first = [
        interval("common", "seed_review", 0, 10, "review-audit"),
        interval("candidate", "proposal", 10, 13, "proposal-audit"),
        interval("baseline", "caller", 20, 24, "baseline-caller"),
        interval("baseline", "tests", 30, 33, "baseline-tests"),
        interval("candidate", "caller", 100, 103, "candidate-caller"),
        interval("candidate", "tests", 110, 112, "candidate-tests"),
    ]
    candidate_first = [
        interval("common", "seed_review", 0, 10, "review-audit"),
        interval("candidate", "proposal", 10, 13, "proposal-audit"),
        interval("candidate", "caller", 20, 23, "candidate-caller"),
        interval("candidate", "tests", 30, 32, "candidate-tests"),
        interval("baseline", "caller", 100, 104, "baseline-caller"),
        interval("baseline", "tests", 110, 113, "baseline-tests"),
    ]
    for rows in (baseline_first, candidate_first):
        result = pe.derive_pair_timing(
            rows, handler_start=-1, settlement=10, cleanup=15,
        )
        assert result.baseline_repair_duration == 7
        assert result.candidate_repair_duration == 8
        assert result.baseline_end_to_end_duration == 17
        assert result.candidate_end_to_end_duration == 18
        assert pe.paired_ratios([result]) == ((8 / 7, 18 / 17),)


@pytest.mark.parametrize(("mutation", "message"), [
    (lambda rows: rows.__setitem__(
        0, interval("common", "seed_review", 10, 9, "review-audit")
    ), "positive duration"),
    (lambda rows: rows.append(
        interval("baseline", "tests", 22, 25, "overlap")
    ), "overlap"),
    (lambda rows: rows.__setitem__(
        1, interval("baseline", "proposal", 10, 13, "proposal-audit")
    ), "candidate proposal"),
    (lambda rows: rows.__setitem__(
        2, interval("common", "caller", 20, 24, "baseline-caller")
    ), "inconsistent owner"),
    (lambda rows: rows.__setitem__(
        2, interval("baseline", "caller", 14, 15, "baseline-caller")
    ), "before seed handler cleanup"),
    (lambda rows: rows.__setitem__(
        2, {**rows[2], "source_identity": ""}
    ), "source identity"),
])
def test_interval_ledger_rejects_invalid_or_unowned_evidence(mutation, message):
    rows = [
        interval("common", "seed_review", 0, 10, "review-audit"),
        interval("candidate", "proposal", 10, 13, "proposal-audit"),
        interval("baseline", "caller", 20, 24, "baseline-caller"),
        interval("candidate", "caller", 30, 35, "candidate-caller"),
    ]
    mutation(rows)
    with pytest.raises(pe.ExperimentError, match=message):
        pe.derive_pair_timing(rows, handler_start=-1, settlement=10, cleanup=15)


def test_interval_ledger_rejects_missing_arm_and_nonfinite_values():
    rows = [
        interval("common", "seed_review", 0, 10, "review-audit"),
        interval("candidate", "proposal", 10, 13, "proposal-audit"),
        interval("candidate", "caller", 20, 25, "candidate-caller"),
    ]
    with pytest.raises(pe.ExperimentError, match="baseline"):
        pe.derive_pair_timing(rows, handler_start=-1, settlement=10, cleanup=15)
    changed = copy.deepcopy(rows)
    changed[0]["start"] = float("nan")
    with pytest.raises(pe.ExperimentError, match="finite"):
        pe.derive_pair_timing(changed, handler_start=-1, settlement=10, cleanup=15)
