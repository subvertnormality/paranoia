import copy
import json
from pathlib import Path

import pytest

from scripts import validate_arbitration_fallback_acceptance as validator


ROOT = Path(__file__).parents[1]
ARTIFACT = ROOT / "docs" / "arbitration_fallback_acceptance_2026-08-16.json"


def _audit() -> dict:
    artifact = json.loads(ARTIFACT.read_text())
    return json.loads((ROOT / artifact["audit"]["path"]).read_text())


def test_checked_in_original_fallback_acceptance_is_valid():
    validator.validate(ARTIFACT, ROOT)


@pytest.mark.parametrize(
    "mutation", ["candidate", "attestation", "decider", "vote", "snapshot", "outcome"],
)
def test_fallback_acceptance_rejects_unbound_delivery_claims(mutation: str):
    audit = copy.deepcopy(_audit())
    artifact = json.loads(ARTIFACT.read_text())
    if mutation == "candidate":
        audit["cleaned"]["sha256"] = "0" * 64
        assert not validator._cleaned_digest_bound(audit["cleaned"])
    elif mutation == "attestation":
        audit["attestation"] = audit["attestation"].replace(
            "ORIGINAL-NEUTRALITY: PASS",
            'ORIGINAL-NEUTRALITY: FAIL {"field":"hints","passage":"duplicated-preamble"}',
        )
        assert not validator._cleaning_and_attestation_bound(audit)
    elif mutation == "decider":
        audit["rounds"][0]["codex"]["attempts"][0]["body"] = "cleaned candidate"
        assert validator._decider_transcripts(audit) is None
    elif mutation == "vote":
        audit["rounds"][0]["codex"]["selected"] = "opt-causing-card"
        assert validator._decider_transcripts(audit) is None
    elif mutation == "snapshot":
        artifact["snapshot_binding"]["tree"] = "0" * 40
        votes = validator._decider_transcripts(audit)
        assert votes is not None
        assert not validator._snapshot_and_outcome_bound(ROOT, artifact, audit, votes)
    else:
        audit["outcome"] = "BLOCKED"
        votes = validator._decider_transcripts(audit)
        assert votes is not None
        assert not validator._snapshot_and_outcome_bound(ROOT, artifact, audit, votes)
