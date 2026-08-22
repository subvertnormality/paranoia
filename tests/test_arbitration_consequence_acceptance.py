import hashlib
import json
from pathlib import Path

from paranoia_local import inert_git

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs/arbitration_consequence_acceptance_2026-08-22.json"


def test_real_consequence_framing_acceptance_is_source_and_route_bound() -> None:
    artifact = json.loads(ARTIFACT.read_text())
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
    assert artifact["elapsed_seconds"] > 0

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

    production = artifact["production_diff"]
    assert (production["additions"], production["deletions"]) == (1, 1)
    assert production["largest_changed_module"]["path"] == (
        "src/paranoia_local/prompts.py"
    )
    report = artifact["report"]
    assert hashlib.sha256(report.encode("utf-8", "surrogatepass")).hexdigest() == (
        artifact["report_sha256"]
    )
