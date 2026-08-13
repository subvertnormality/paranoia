import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_arbitration_acceptance.py"
_SPEC = importlib.util.spec_from_file_location("acceptance_validator", _SCRIPT)
assert _SPEC and _SPEC.loader
validator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validator)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    hashes = {}
    for relative in validator.PRODUCTION_SOURCES:
        source = repo / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"# {relative}\n")
        hashes[relative] = _sha(source)
    packets = json.dumps([{
        "packet_id": "src-one", "source": {"url": "https://example.test/doc"},
    }])
    digest = hashlib.sha256(packets.encode()).hexdigest()
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({
        "snapshot": "abc", "outcome": "CONVERGED", "selected": "decimal",
        "cleaning": "attested", "refs_moved": False,
        "phase_attempts": [
            {"role": "cleaner", "invoked": True},
            {"role": "attester", "invoked": True},
        ],
        "research": {
            "digest": digest,
            "packets": packets,
            "runs": [
                {"engine": "codex", "calls": 1, "attempts": [{"invoked": True}]},
                {"engine": "claude", "calls": 1, "attempts": [{"invoked": True}]},
            ],
        },
        "rounds": [{
            "codex": {"attempts": [{"invoked": True}], "decisive": "README.md:1"},
            "claude": {"attempts": [{"invoked": True}], "decisive": "SOURCE:src-one"},
        }],
    }))
    preceding_audit = tmp_path / "preceding.json"
    preceding_audit.write_text(json.dumps({
        "snapshot": "abc", "outcome": "FAILED", "reason": "provider failed",
        "cleaning": "attested-after-retry",
    }))
    artifact = tmp_path / "acceptance.json"
    artifact.write_text(json.dumps({"primary_path": {
        "audit": str(audit), "result": "CONVERGED", "selected": "decimal",
        "snapshot": "abc", "research_digest": digest, "cleaning": "attested",
        "rounds": 1, "refs_moved": False,
        "captured_packets": ["src-one"],
        "captured_urls": ["https://example.test/doc"],
        "decisive_evidence": {
            "codex": "README.md:1", "claude": "SOURCE:src-one",
        },
        "production_source_sha256": hashes,
        "model_calls": {
            "research": {"codex": 1, "claude": 1},
            "deciders": {"codex": 1, "claude": 1},
            "cleaner": 1, "attester": 1, "total": 6,
        },
        "audit_reconciliation": {
            "audit_sha256": _sha(audit),
            "research_attempts": {"codex": 1, "claude": 1},
            "framing_attempts": 2, "decider_attempts": 2,
            "total_provider_calls": 6, "packet_count": 1,
            "packet_digest_matches": True, "packet_ids_match": True,
            "production_hashes_match": True,
        },
        "preceding_failed_closed_attempt": {
            "audit": str(preceding_audit), "audit_sha256": _sha(preceding_audit),
            "result": "FAILED", "reason": "provider failed",
            "cleaning": "attested-after-retry", "snapshot": "abc",
        },
    }}))
    return artifact, repo


def test_acceptance_validator_reconciles_audit_and_sources(tmp_path: Path):
    artifact, repo = fixture(tmp_path)
    validator.validate(artifact, repo)


def test_acceptance_validator_reconciles_one_framing_retry(tmp_path: Path):
    artifact, repo = fixture(tmp_path)
    acceptance = json.loads(artifact.read_text())
    audit_path = Path(acceptance["primary_path"]["audit"])
    audit = json.loads(audit_path.read_text())
    audit["phase_attempts"] += [
        {"role": "cleaner", "invoked": True},
        {"role": "attester", "invoked": True},
    ]
    audit["cleaning"] = "attested-after-retry"
    audit_path.write_text(json.dumps(audit))
    primary = acceptance["primary_path"]
    primary["audit_reconciliation"]["audit_sha256"] = _sha(audit_path)
    primary["audit_reconciliation"]["framing_attempts"] = 4
    primary["audit_reconciliation"]["total_provider_calls"] = 8
    primary["model_calls"].update({"cleaner": 2, "attester": 2, "total": 8})
    primary["cleaning"] = "attested-after-retry"
    artifact.write_text(json.dumps(acceptance))

    validator.validate(artifact, repo)


def test_acceptance_validator_rejects_a_self_asserted_stale_total(tmp_path: Path):
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    data["primary_path"]["model_calls"]["total"] = 5
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="total calls"):
        validator.validate(artifact, repo)


@pytest.mark.parametrize(("mutation", "message"), [
    (lambda a, d: a["primary_path"]["captured_packets"].append("src-two"), "packet count"),
    (lambda a, d: a["primary_path"]["captured_packets"].__setitem__(0, "src-two"), "packet ids"),
    (lambda a, d: a["primary_path"].__setitem__("research_digest", "stale"), "packet digest"),
    (lambda a, d: a["primary_path"]["captured_urls"].clear(), "packet urls"),
    (lambda a, d: a["primary_path"]["decisive_evidence"].__setitem__("codex", "README.md:2"), "decisive evidence"),
    (lambda a, d: a["primary_path"]["model_calls"].__setitem__("cleaner", 0), "cleaner attempts"),
    (lambda a, d: a["primary_path"]["model_calls"].__setitem__("attester", 0), "attester attempts"),
    (lambda a, d: a["primary_path"]["model_calls"]["research"].__setitem__("codex", 2), "research attempts"),
    (lambda a, d: a["primary_path"]["model_calls"]["deciders"].__setitem__("codex", 2), "decider attempts"),
    (lambda a, d: d["research"]["runs"].append(d["research"]["runs"][0]), "each engine exactly once"),
    (lambda a, d: d["research"]["runs"][0].__setitem__("calls", 2), "calls disagree"),
    (lambda a, d: d["research"]["runs"][0]["attempts"][0].__setitem__("invoked", "false"), "exact boolean"),
    (lambda a, d: a["primary_path"].__setitem__("result", "FAILED"), "audit outcome"),
    (lambda a, d: a["primary_path"].__setitem__("selected", "float"), "audit selection"),
    (lambda a, d: a["primary_path"].__setitem__("snapshot", "def"), "audit snapshot"),
    (lambda a, d: a["primary_path"].__setitem__("cleaning", "skipped"), "cleaning"),
    (lambda a, d: a["primary_path"].__setitem__("rounds", 99), "round count"),
    (lambda a, d: a["primary_path"].__setitem__("refs_moved", True), "refs moved"),
    (lambda a, d: a["primary_path"]["production_source_sha256"].pop(next(iter(validator.PRODUCTION_SOURCES))), "complete source set"),
    (lambda a, d: a["primary_path"]["production_source_sha256"].__setitem__(next(iter(validator.PRODUCTION_SOURCES)), "0" * 64), "production hash mismatch"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("packet_ids_match", False), "packet_ids_match"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("packet_digest_matches", False), "packet_digest_matches"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("production_hashes_match", False), "production_hashes_match"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("framing_attempts", 1), "framing_attempts"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("decider_attempts", 1), "decider_attempts"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"]["research_attempts"].__setitem__("codex", 2), "research_attempts"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("total_provider_calls", 5), "total_provider_calls"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("packet_count", 2), "packet_count"),
])
def test_acceptance_validator_rejects_each_independent_summary(
    tmp_path: Path, mutation, message: str,
):
    artifact, repo = fixture(tmp_path)
    acceptance = json.loads(artifact.read_text())
    audit_path = Path(acceptance["primary_path"]["audit"])
    audit = json.loads(audit_path.read_text())
    mutation(acceptance, audit)
    audit_path.write_text(json.dumps(audit))
    acceptance["primary_path"]["audit_reconciliation"]["audit_sha256"] = _sha(audit_path)
    artifact.write_text(json.dumps(acceptance))

    with pytest.raises(ValueError, match=message):
        validator.validate(artifact, repo)


def test_acceptance_validator_rejects_stale_audit_hash(tmp_path: Path):
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    data["primary_path"]["audit_reconciliation"]["audit_sha256"] = "0" * 64
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="audit_sha256"):
        validator.validate(artifact, repo)


@pytest.mark.parametrize(("field", "value", "message"), [
    ("audit_sha256", "0" * 64, "preceding audit digest"),
    ("result", "CONVERGED", "preceding result"),
    ("reason", "different", "preceding reason"),
    ("cleaning", "skipped", "preceding cleaning"),
    ("snapshot", "def", "preceding snapshot"),
])
def test_acceptance_validator_rejects_stale_preceding_failure(
    tmp_path: Path, field: str, value: str, message: str,
):
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    data["primary_path"]["preceding_failed_closed_attempt"][field] = value
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match=message):
        validator.validate(artifact, repo)
