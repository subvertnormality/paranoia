#!/usr/bin/env python3
"""Closed replay validator for the positive and negative issue-59 acceptances."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from paranoia_local import arbitrate_handler as ah
from paranoia_local import arbitration as arb
from paranoia_local import evidence, inert_git, prompts
from scripts import validate_arbitration_fallback_acceptance as shared


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8", "surrogatepass")
    return hashlib.sha256(encoded).hexdigest()


def _source_blob(repo: Path, commit: str, path: str) -> bytes:
    result = inert_git.invoke(repo, ["show", f"{commit}:{path}"])
    if result.returncode != 0:
        raise ValueError(f"acceptance source blob is unavailable: {path}")
    return result.stdout


def _common(artifact: dict, repo: Path) -> tuple[dict, dict[str, str], str]:
    source = artifact.get("source_revision")
    if not isinstance(source, str):
        raise ValueError("acceptance source revision is absent")
    resolved = inert_git.text(
        repo, ["rev-parse", "--verify", f"{source}^{{commit}}"],
    ).strip()
    if resolved != source:
        raise ValueError("acceptance source revision is not the recorded commit")
    source_hashes = artifact.get("source_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("acceptance source hashes are absent")
    for path, expected in source_hashes.items():
        if hashlib.sha256(_source_blob(repo, source, path)).hexdigest() != expected:
            raise ValueError(f"acceptance source hash mismatch: {path}")
    audit = artifact.get("audit")
    if not isinstance(audit, dict) or _canonical_digest(audit) != artifact.get("audit_sha256"):
        raise ValueError("acceptance audit digest mismatch")
    report = artifact.get("report")
    if not isinstance(report, str) or shared._text_digest(report) != artifact.get("report_sha256"):
        raise ValueError("acceptance report digest mismatch")

    binding = artifact.get("snapshot_binding")
    if not isinstance(binding, dict) or set(binding) != {
        "commit_object", "sha256", "source_commit", "tree",
    }:
        raise ValueError("acceptance snapshot binding is malformed")
    raw_commit = binding["commit_object"].encode("utf-8")
    object_id = hashlib.sha1(
        b"commit " + str(len(raw_commit)).encode("ascii") + b"\0" + raw_commit,
    ).hexdigest()
    lines = binding["commit_object"].splitlines()
    source_tree = inert_git.text(repo, ["rev-parse", f"{source}^{{tree}}"] ).strip()
    if (
        hashlib.sha256(raw_commit).hexdigest() != binding["sha256"]
        or object_id != audit.get("snapshot")
        or binding["source_commit"] != source
        or binding["tree"] != source_tree
        or lines[:2] != [f"tree {source_tree}", f"parent {source}"]
    ):
        raise ValueError("acceptance snapshot does not bind the clean source tree")
    instructions = shared._historical_prompt_instructions(repo, source)
    return audit, instructions, source


def _raw_input_bound(artifact: dict, audit: dict) -> bool:
    arguments, raw = artifact.get("input", {}), audit.get("raw_input", {})
    return (
        raw.get("decision") == arguments.get("decision")
        and raw.get("stakes") == arguments.get("stakes")
        and raw.get("context") == arguments.get("context")
        and raw.get("files") == arguments.get("files")
        and raw.get("options") == {
            row["id"]: row["statement"] for row in arguments.get("options", [])
        }
        and arguments.get("research") is False
        and arguments.get("web_search") is False
    )


def _positive(artifact: dict, repo: Path) -> None:
    audit, instructions, source = _common(artifact, repo)
    if artifact.get("acceptance_kind") != "arbitration-consequence-not-advocacy":
        raise ValueError("positive acceptance kind mismatch")
    if not _raw_input_bound(artifact, audit):
        raise ValueError("positive acceptance input mismatch")
    if not (
        artifact.get("model_call_count") == 4
        and audit.get("outcome") == arb.CONVERGED
        and audit.get("cleaning") == "original-attested"
        and shared._cleaned_digest_bound(audit.get("cleaned", {}))
        and shared._cleaning_and_attestation_bound(
            audit, fallback=True, instruction_set=instructions,
        )
    ):
        raise ValueError("positive acceptance cleaning route does not replay")
    votes = shared._decider_transcripts(audit, instruction_set=instructions)
    if votes is None:
        raise ValueError("positive acceptance decider transcripts do not replay")
    resolver = evidence.LinkResolver(repo, source)

    def resolve(citation: arb.Citation) -> arb.Region | None:
        got = evidence.resolve_citation(
            repo, citation, snapshot=source, links=resolver, context=arb.CONTEXT_LINES,
        )
        return got[0] if got else None

    substantiated = arb.substantiation(votes, resolve=resolve)
    outcome = arb.compute_outcome(votes, substantiated=substantiated)
    if (
        substantiated != {"codex": True, "claude": True}
        or outcome.outcome != audit.get("outcome")
        or outcome.selected != audit.get("selected")
        or outcome.reason != audit.get("reason")
    ):
        raise ValueError("positive acceptance terminal outcome does not recompute")


def _negative(artifact: dict, repo: Path) -> None:
    audit, instructions, _ = _common(artifact, repo)
    if artifact.get("acceptance_kind") != "arbitration-genuine-steering-rejected":
        raise ValueError("negative acceptance kind mismatch")
    if not _raw_input_bound(artifact, audit):
        raise ValueError("negative acceptance input mismatch")
    raw, cleaned = audit.get("raw_input", {}), audit.get("cleaned", {})
    attempts = audit.get("phase_attempts", [])
    if (
        artifact.get("model_call_count") != 2
        or [row.get("role") for row in attempts] != ["cleaner", "attester"]
        or audit.get("outcome") != arb.FAILED
        or audit.get("cleaning") != "attestation-rejected"
        or audit.get("rounds") != []
        or not shared._cleaned_digest_bound(cleaned)
    ):
        raise ValueError("negative acceptance did not stop at the attester")
    cleaner, attester_record = attempts
    cleaner_body = ah._clean_body(
        raw["decision"], raw["stakes"], raw["context"], raw["files"],
        raw["options"], "",
    )
    cleaner_prompt = prompts.compose(instructions["CLEANER_INSTRUCTIONS"], cleaner_body)
    cleaner_reply = cleaner.get("reply")
    if not isinstance(cleaner_reply, str) or not shared._attempt_bound(
        cleaner, prompt=cleaner_prompt, reply=cleaner_reply, rejection=None,
        execution=shared._external_execution("claude", cleaner["execution"]["model"]),
    ):
        raise ValueError("negative acceptance cleaner attempt does not replay")
    try:
        parsed = ah.parse_cleaned_packet(
            cleaner_reply, list(raw["options"]), caller_gave_context=bool(raw["context"]),
        )
    except arb.ArbitrationError as exc:
        raise ValueError("negative acceptance cleaner reply is invalid") from exc
    parsed["context"] = raw["context"]
    cleaned_hints = ah._merge_hints(raw["files"], parsed["hints"])
    if {
        "decision": parsed["decision"], "context": parsed["context"],
        "hints": cleaned_hints, "statements": parsed["statements"],
    } != {key: cleaned[key] for key in ("decision", "context", "hints", "statements")}:
        raise ValueError("negative acceptance cleaned packet mismatch")
    expected = {
        "decision": (raw["decision"], cleaned["decision"]),
        **{
            option_id: (statement, cleaned["statements"][option_id])
            for option_id, statement in raw["options"].items()
        },
        "hints": (ah._render_hints(raw["files"]), ah._render_hints(cleaned_hints)),
    }
    try:
        attestation = ah.parse_attestation(audit["attestation"], expected)
    except arb.ArbitrationError as exc:
        raise ValueError("negative acceptance attestation is invalid") from exc
    if (
        not attestation.stakes_advocacy
        or attestation.context_advocacy is not None
        or not attestation.original_neutrality_pass
    ):
        raise ValueError("negative acceptance did not identify stakes steering")
    attester_body = ah._attest_body(
        raw["decision"], raw["stakes"], raw["context"], raw["files"],
        cleaned_hints, raw["options"], parsed,
    )
    attester_prompt = prompts.compose(instructions["ATTEST_INSTRUCTIONS"], attester_body)
    if not shared._attempt_bound(
        attester_record, prompt=attester_prompt, reply=audit["attestation"],
        rejection=attestation.stakes_advocacy,
        execution=shared._external_execution("codex", attester_record["execution"]["model"]),
    ):
        raise ValueError("negative acceptance attester attempt does not replay")
    expected_reason = (
        "the stakes text advocates for an option, and stakes is not the cleaner's to "
        f"rewrite — fix it and re-run: {attestation.stakes_advocacy}"
    )
    if audit.get("reason") != expected_reason:
        raise ValueError("negative acceptance failure reason mismatch")


def validate_artifacts(positive: dict, negative: dict, repo: Path) -> None:
    _positive(positive, repo)
    _negative(negative, repo)


def validate(positive_path: Path, negative_path: Path, repo: Path) -> None:
    validate_artifacts(
        json.loads(positive_path.read_text()),
        json.loads(negative_path.read_text()),
        repo,
    )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_arbitration_consequence_acceptance.py POSITIVE NEGATIVE")
    validate(Path(sys.argv[1]), Path(sys.argv[2]), Path.cwd())


if __name__ == "__main__":
    main()
