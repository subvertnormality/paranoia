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


@pytest.mark.parametrize("mutation", ["candidate", "attestation", "decider"])
def test_fallback_acceptance_rejects_unbound_delivery_claims(mutation: str):
    audit = copy.deepcopy(_audit())
    if mutation == "candidate":
        audit["cleaned"]["sha256"] = "0" * 64
        assert not validator._cleaned_digest_bound(audit["cleaned"])
    elif mutation == "attestation":
        audit["attestation"] = audit["attestation"].replace(
            "ORIGINAL-NEUTRALITY: PASS",
            'ORIGINAL-NEUTRALITY: FAIL {"field":"hints","passage":"duplicated-preamble"}',
        )
        assert not validator._attestation_bound(audit)
    else:
        audit["rounds"][0]["codex"]["attempts"][0]["body"] = "cleaned candidate"
        assert not validator._decider_prompts_bound(audit)
