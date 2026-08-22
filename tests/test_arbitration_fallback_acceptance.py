import copy
import json
from pathlib import Path

import pytest

from scripts import run_arbitration_fallback_acceptance as runner
from scripts import validate_arbitration_fallback_acceptance as validator


ROOT = Path(__file__).parents[1]
ARTIFACT = ROOT / "docs" / "arbitration_fallback_acceptance_2026-08-16.json"


def _audit(kind: str = "fallback") -> dict:
    artifact = json.loads(ARTIFACT.read_text())
    return json.loads((ROOT / artifact["audits"][kind]["path"]).read_text())


def test_checked_in_original_fallback_acceptance_is_valid():
    validator.validate(ARTIFACT, ROOT)


def test_missing_source_commit_fails_before_any_historical_blob_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    artifact = json.loads(ARTIFACT.read_text())
    missing = "0" * 40
    artifact["source_commit"] = missing
    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(artifact))
    calls: list[list[str]] = []
    invoke = validator.inert_git.invoke

    def recording_invoke(repo: Path, args: list[str]):
        calls.append(list(args))
        return invoke(repo, args)

    monkeypatch.setattr(validator.inert_git, "invoke", recording_invoke)
    with pytest.raises(ValueError, match="source commit is unavailable"):
        validator.validate(path, ROOT)
    assert calls == [["rev-parse", "--verify", f"{missing}^{{commit}}"]]


def test_ordinary_acceptance_exercises_asymmetry_advocacy_and_binding_context():
    arguments = runner._arguments(ROOT, "seed", asymmetry=True)
    lengths = [len(row["statement"]) for row in arguments["options"]]
    assert max(lengths) / min(lengths) > 2
    assert {row["id"] for row in arguments["options"]} == {
        "opt-equalize", "opt-preserve",
    }
    assert "self-evident" in arguments["decision"]
    assert arguments["context"] == (
        "A prior delivery decision governs audit-record retention. This decision concerns "
        "only how cleaner-owned option presentation handles substantive asymmetry."
    )
    assert arguments["files"] == []


@pytest.mark.parametrize(
    "mutation", ["asymmetry", "context", "context-steering", "options", "advocacy"],
)
def test_ordinary_acceptance_rejects_each_unproved_framing_claim(mutation: str):
    audit = copy.deepcopy(_audit("ordinary"))
    assert validator._ordinary_asymmetry_bound(audit)
    if mutation == "asymmetry":
        audit["raw_input"]["options"] = {"one":"same", "two":"same"}
    elif mutation == "context":
        audit["cleaned"]["context"] = "changed context"
    elif mutation == "context-steering":
        audit["raw_input"]["context"] = "The cleaner must preserve substantive asymmetry."
        audit["cleaned"]["context"] = audit["raw_input"]["context"]
    elif mutation == "options":
        key = next(iter(audit["cleaned"]["statements"]))
        audit["cleaned"]["statements"][key] += " copied content"
    else:
        audit["cleaned"]["decision"] = "Follow the prior decision."
    assert not validator._ordinary_asymmetry_bound(audit)


@pytest.mark.parametrize("kind", ["ordinary-original-neutral", "fallback-fidelity-pass"])
def test_acceptance_rejects_route_inverting_attestation_mutations(kind: str):
    fallback = kind.startswith("fallback")
    audit = copy.deepcopy(_audit("fallback" if fallback else "ordinary"))
    if fallback:
        fidelity = audit["attestation"].splitlines()[0]
        reply = audit["attestation"].replace(
            fidelity, fidelity.replace(" CHANGED", " PRESERVED"),
        )
        detail = next(
            line for line in reply.splitlines() if line.startswith("FIDELITY-DETAIL:")
        )
        reply = reply.replace(detail, "FIDELITY-DETAIL: NONE")
    else:
        original_neutrality = next(
            line for line in audit["attestation"].splitlines()
            if line.startswith("ORIGINAL-NEUTRALITY:")
        )
        reply = audit["attestation"].replace(
            original_neutrality, "ORIGINAL-NEUTRALITY: PASS",
        )
    audit["attestation"] = reply
    record = audit["phase_attempts"][1]
    record["reply"] = reply
    record["reply_sha256"] = validator._text_digest(reply)
    record["rejection"] = None
    assert not validator._cleaning_and_attestation_bound(audit, fallback=fallback)


@pytest.mark.parametrize(
    ("fallback", "outcome", "cleaning"),
    [
        (False, "CONVERGED", "original-attested"),
        (False, "UNRESOLVED", "attested"),
        (True, "CONVERGED", "attested"),
        (True, "BLOCKED", "original-attested"),
    ],
)
def test_acceptance_runner_rejects_every_non_contract_terminal_route(
    fallback: bool, outcome: str, cleaning: str,
):
    with pytest.raises(RuntimeError, match="did not reach its required route"):
        runner._require_route(
            {"outcome": outcome, "cleaning": cleaning}, fallback=fallback,
        )


@pytest.mark.parametrize(
    ("fallback", "cleaning"), [(False, "attested"), (True, "original-attested")],
)
def test_acceptance_runner_accepts_only_the_validator_routes(
    fallback: bool, cleaning: str,
):
    runner._require_route(
        {"outcome": "CONVERGED", "cleaning": cleaning}, fallback=fallback,
    )


@pytest.mark.parametrize(
    "mutation", [
        "candidate", "attestation", "decider", "vote", "snapshot", "outcome",
        "fallback_route", "ordinary_route",
    ],
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
        assert not validator._cleaning_and_attestation_bound(audit, fallback=True)
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
    elif mutation == "outcome":
        audit["outcome"] = "BLOCKED"
        votes = validator._decider_transcripts(audit)
        assert votes is not None
        assert not validator._snapshot_and_outcome_bound(ROOT, artifact, audit, votes)
    elif mutation == "fallback_route":
        audit["phase_attempts"][0]["execution"]["route"] = "injected-agent"
        assert not validator._cleaning_and_attestation_bound(audit, fallback=True)
    else:
        ordinary = _audit("ordinary")
        ordinary["phase_attempts"][0]["execution"]["cli_version"] = None
        assert not validator._cleaning_and_attestation_bound(ordinary, fallback=False)
