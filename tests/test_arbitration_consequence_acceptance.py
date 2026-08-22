import copy
import hashlib
import json
from pathlib import Path

from paranoia_local import inert_git
import pytest
from scripts import validate_arbitration_consequence_acceptance as validator

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs/arbitration_consequence_acceptance_2026-08-22.json"
NEGATIVE = ROOT / "docs/arbitration_steering_rejection_acceptance_2026-08-22.json"
CONTEXT_NEGATIVE = ROOT / "docs/arbitration_context_steering_rejection_acceptance_2026-08-22.json"


def test_real_consequence_framing_acceptance_is_source_and_route_bound() -> None:
    artifact = json.loads(ARTIFACT.read_text())
    negative = json.loads(NEGATIVE.read_text())
    context_negative = json.loads(CONTEXT_NEGATIVE.read_text())
    validator.validate_artifacts(artifact, negative, context_negative, ROOT)
    assert artifact["acceptance_kind"] == "arbitration-consequence-not-advocacy"
    source_revision = artifact["source_revision"]
    resolved = inert_git.text(
        ROOT, ["rev-parse", "--verify", f"{source_revision}^{{commit}}"],
    ).strip()
    assert resolved == source_revision
    accepted = inert_git.invoke(
        ROOT, ["show", f"{resolved}:src/paranoia_local/prompts.py"],
    )
    assert accepted.returncode == 0
    accepted_prompt = accepted.stdout
    assert accepted_prompt == (ROOT / "src/paranoia_local/prompts.py").read_bytes()
    assert artifact["input"]["stakes"] == (
        "Review effort spent on this naming decision is effort not spent on its "
        "implementation. A wrong choice causes rework, not corrupted state."
    )
    assert artifact["input"]["research"] is False
    assert artifact["input"]["web_search"] is False
    assert artifact["model_call_count"] == 4

    audit = artifact["audit"]
    assert audit["outcome"] == "CONVERGED"
    assert audit["reason"] == "unanimous, unblocked, substantiated"
    assert audit["cleaning"] == "original-attested"
    assert "ORIGINAL-NEUTRALITY: PASS" in audit["attestation"]
    assert "STAKES-ADVOCACY: NONE" in audit["attestation"]
    assert "CONTEXT-ADVOCACY: NONE" in audit["attestation"]
    phase_routes = [
        (row["role"], row["execution"]["engine"], row["execution"]["route"])
        for row in audit["phase_attempts"]
    ]
    assert phase_routes == [
        ("cleaner", "claude", "external-cli"),
        ("attester", "codex", "external-cli"),
    ]
    assert all(row["execution"]["cli_version"] for row in audit["phase_attempts"])
    assert len(audit["rounds"]) == 1
    assert set(audit["rounds"][0]) == {"claude", "codex"}
    for engine, row in audit["rounds"][0].items():
        assert row["selected"] == "opt-paranoia"
        assert len(row["attempts"]) == 1
        route = row["attempts"][0]["execution"]
        assert (route["engine"], route["route"]) == (engine, "external-cli")
        assert route["cli_version"]

    report = artifact["report"]
    assert hashlib.sha256(report.encode("utf-8", "surrogatepass")).hexdigest() == (
        artifact["report_sha256"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "source", "snapshot", "audit-digest", "cleaner-prompt", "attester-reply",
        "decider-prompt", "vote", "outcome", "negative-rounds", "negative-reason",
        "context-rounds", "context-reason", "manifest-extra", "manifest-delete",
        "production-drift", "cleaner-model", "attester-model",
        "input-cleaner-override", "claims", "limitation", "top-level-extra",
        "top-level-delete",
    ],
)
def test_consequence_acceptance_rejects_every_binding_mutation(
    mutation: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    positive = json.loads(ARTIFACT.read_text())
    negative = json.loads(NEGATIVE.read_text())
    context_negative = json.loads(CONTEXT_NEGATIVE.read_text())
    target = positive
    sync = True
    if mutation == "source":
        key = next(iter(positive["source_sha256"]))
        positive["source_sha256"][key] = "0" * 64
        sync = False
    elif mutation == "snapshot":
        positive["snapshot_binding"]["tree"] = "0" * 40
        sync = False
    elif mutation == "audit-digest":
        positive["audit_sha256"] = "0" * 64
        sync = False
    elif mutation == "cleaner-prompt":
        positive["audit"]["phase_attempts"][0]["prompt_sha256"] = "0" * 64
    elif mutation == "attester-reply":
        target = negative
        negative["audit"]["attestation"] = negative["audit"]["attestation"].replace(
            "STAKES-ADVOCACY: PRESENT", "STAKES-ADVOCACY: NONE",
        )
    elif mutation == "decider-prompt":
        positive["audit"]["rounds"][0]["codex"]["attempts"][0]["prompt_sha256"] = "0" * 64
    elif mutation == "vote":
        positive["audit"]["rounds"][0]["codex"]["selected"] = "opt-paranoia-review"
    elif mutation == "outcome":
        positive["audit"]["outcome"] = "UNRESOLVED"
    elif mutation == "negative-rounds":
        target = negative
        negative["audit"]["rounds"] = [{"codex": {}}]
    elif mutation == "context-rounds":
        target = context_negative
        context_negative["audit"]["rounds"] = [{"codex": {}}]
    elif mutation == "context-reason":
        target = context_negative
        context_negative["audit"]["reason"] = "warning only"
    elif mutation == "manifest-extra":
        positive["source_sha256"]["README.md"] = "0" * 64
        sync = False
    elif mutation == "manifest-delete":
        del positive["source_sha256"]["src/paranoia_local/evidence.py"]
        sync = False
    elif mutation == "production-drift":
        original_read = Path.read_bytes

        def changed_read(path: Path) -> bytes:
            body = original_read(path)
            return body + b"# drift\n" if path.name == "arbitration.py" else body

        monkeypatch.setattr(Path, "read_bytes", changed_read)
        sync = False
    elif mutation == "cleaner-model":
        target = negative
        negative["audit"]["phase_attempts"][0]["execution"]["model"] = "other-cleaner"
    elif mutation == "attester-model":
        target = context_negative
        context_negative["audit"]["phase_attempts"][1]["execution"]["model"] = "other-attester"
    elif mutation == "input-cleaner-override":
        negative["input"]["cleaner_model"] = "other-cleaner"
        sync = False
    elif mutation == "claims":
        positive["claims"]["proves"][0] = "Everything is proven."
        sync = False
    elif mutation == "limitation":
        context_negative["claims"]["does_not_prove"] = []
        sync = False
    elif mutation == "top-level-extra":
        positive["observational_elapsed_seconds"] = 1.0
        sync = False
    elif mutation == "top-level-delete":
        del negative["date"]
        sync = False
    else:
        target = negative
        negative["audit"]["reason"] = "warning only"
    if sync:
        target["audit_sha256"] = validator._canonical_digest(target["audit"])
    with pytest.raises(ValueError):
        validator.validate_artifacts(positive, negative, context_negative, ROOT)
