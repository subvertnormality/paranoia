#!/usr/bin/env python3
"""Closed replay validator for the positive and negative issue-59 acceptances."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from paranoia_local import arbitrate_handler as ah
from paranoia_local import arbitration as arb
from paranoia_local import engines, evidence, inert_git, prompts
from scripts import validate_arbitration_fallback_acceptance as shared


POSITIVE_SOURCES = frozenset({
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/arbitration.py",
    "src/paranoia_local/engines.py",
    "src/paranoia_local/evidence.py",
    "src/paranoia_local/inert_git.py",
    "src/paranoia_local/prompts.py",
    "scripts/run_arbitration_consequence_acceptance.py",
    "scripts/validate_arbitration_consequence_acceptance.py",
    "scripts/validate_arbitration_fallback_acceptance.py",
})
STAKES_NEGATIVE_SOURCES = frozenset({
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/arbitration.py",
    "src/paranoia_local/engines.py",
    "src/paranoia_local/inert_git.py",
    "src/paranoia_local/prompts.py",
    "scripts/run_arbitration_steering_rejection_acceptance.py",
    "scripts/validate_arbitration_consequence_acceptance.py",
    "scripts/validate_arbitration_fallback_acceptance.py",
})
CONTEXT_NEGATIVE_SOURCES = STAKES_NEGATIVE_SOURCES | {
    "scripts/run_arbitration_context_steering_rejection_acceptance.py",
}
ORIGINAL_NEGATIVE_SOURCES = STAKES_NEGATIVE_SOURCES | {
    "scripts/run_arbitration_original_steering_rejection_acceptance.py",
}
REPLAYED_PRODUCTION_SOURCES = frozenset({
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/arbitration.py",
    "src/paranoia_local/engines.py",
    "src/paranoia_local/evidence.py",
    "src/paranoia_local/inert_git.py",
    "src/paranoia_local/prompts.py",
})
POSITIVE_CLAIMS = {
    "proves": [
        "The real cleaner and cross-vendor attester admitted consequence-only stakes and governing factual context.",
        "Both real deciders received the accepted packet and the arbitration converged.",
    ],
    "does_not_prove": [
        "Genuine directives, endorsements, rhetorical preference, or pre-emptive conclusions are accepted.",
        "Every future provider version will classify every framing correctly.",
    ],
}


def _negative_claims(field: str) -> dict[str, list[str]]:
    return {
        "proves": [
            f"The real cleaner and cross-vendor attester rejected this explicit {field}-steering packet.",
            f"No decider ran after the attester's {field}-advocacy verdict.",
        ],
        "does_not_prove": [
            "Each phrase in the compound packet independently causes rejection.",
            "Every future provider version will classify every framing correctly.",
        ],
    }


COMMON_TOP_LEVEL = {
    "acceptance_kind", "audit", "audit_sha256", "claims", "date", "input",
    "model_call_count", "report", "report_sha256", "snapshot_binding",
    "source_revision", "source_sha256", "allowed_later_source_diffs", "version",
}
INPUT_FIELDS = {
    "clean", "context", "decision", "files", "options", "order_seed", "research",
    "stakes", "web_search",
}


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


def _common(
    artifact: dict, repo: Path, *, expected_sources: frozenset[str],
) -> tuple[dict, dict[str, str], str]:
    source = artifact.get("source_revision")
    if not isinstance(source, str):
        raise ValueError("acceptance source revision is absent")
    resolved = inert_git.text(
        repo, ["rev-parse", "--verify", f"{source}^{{commit}}"],
    ).strip()
    if resolved != source:
        raise ValueError("acceptance source revision is not the recorded commit")
    source_hashes = artifact.get("source_sha256")
    if not isinstance(source_hashes, dict) or set(source_hashes) != expected_sources:
        raise ValueError("acceptance source manifest is not exact for its route")
    allowed_later = artifact.get("allowed_later_source_diffs")
    if not isinstance(allowed_later, dict):
        raise ValueError("later-source allowance inventory is absent")
    changed: set[str] = set()
    for path, expected in source_hashes.items():
        historical = _source_blob(repo, source, path)
        if hashlib.sha256(historical).hexdigest() != expected:
            raise ValueError(f"acceptance source hash mismatch: {path}")
        if path in REPLAYED_PRODUCTION_SOURCES and (repo / path).read_bytes() != historical:
            changed.add(path)
            allowance = allowed_later.get(path)
            if not isinstance(allowance, dict) or set(allowance) != {"sha256", "scope"}:
                raise ValueError(f"later-source allowance is absent for {path}")
            diff = inert_git.invoke(
                repo, ["diff", "--no-ext-diff", source, "--", path],
            )
            if diff.returncode != 0 or hashlib.sha256(diff.stdout).hexdigest() != allowance["sha256"]:
                raise ValueError(f"later-source allowance mismatch for {path}")
            if not isinstance(allowance["scope"], str) or not allowance["scope"].strip():
                raise ValueError(f"later-source allowance scope is empty for {path}")
    if set(allowed_later) != changed:
        raise ValueError("later-source allowance inventory is not exact")
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
    options = arguments.get("options") if isinstance(arguments, dict) else None
    files = arguments.get("files") if isinstance(arguments, dict) else None
    options_closed = (
        isinstance(options, list)
        and len(options) == 2
        and all(
            isinstance(row, dict)
            and set(row) == {"id", "statement"}
            and all(isinstance(row[key], str) and row[key].strip() for key in row)
            for row in options
        )
        and len({row["id"] for row in options}) == len(options)
    )
    files_closed = (
        isinstance(files, list)
        and len(files) <= 1
        and all(
            isinstance(row, dict)
            and set(row) == {"path", "reason"}
            and all(isinstance(row[key], str) and row[key].strip() for key in row)
            for row in files
        )
    )
    return (
        isinstance(arguments, dict)
        and set(arguments) == INPUT_FIELDS
        and options_closed
        and files_closed
        and raw.get("decision") == arguments.get("decision")
        and raw.get("stakes") == arguments.get("stakes")
        and raw.get("context") == arguments.get("context")
        and raw.get("files") == arguments.get("files")
        and raw.get("options") == {
            row["id"]: row["statement"] for row in options
        }
        and arguments.get("clean") is True
        and arguments.get("research") is False
        and arguments.get("web_search") is False
        and arguments.get("order_seed") == audit.get("order_seed")
        and audit.get("research", {}).get("enabled") is False
    )


def _positive(artifact: dict, repo: Path) -> None:
    if set(artifact) != COMMON_TOP_LEVEL:
        raise ValueError("positive acceptance top-level schema mismatch")
    audit, instructions, source = _common(
        artifact, repo, expected_sources=POSITIVE_SOURCES,
    )
    if artifact.get("acceptance_kind") != "arbitration-consequence-not-advocacy":
        raise ValueError("positive acceptance kind mismatch")
    if type(artifact.get("version")) is not int or artifact["version"] != 1 or artifact.get("date") != "2026-08-22":
        raise ValueError("positive acceptance version metadata mismatch")
    if artifact.get("claims") != POSITIVE_CLAIMS:
        raise ValueError("positive acceptance claim scope mismatch")
    if not _raw_input_bound(artifact, audit):
        raise ValueError("positive acceptance input mismatch")
    if not (
        type(artifact.get("model_call_count")) is int
        and artifact["model_call_count"] == 4
        and audit.get("outcome") == arb.CONVERGED
        and audit.get("cleaning") == "original-attested"
        and shared._cleaned_digest_bound(audit.get("cleaned", {}))
        and shared._cleaning_and_attestation_bound(
            audit, fallback=True, instruction_set=instructions,
            deterministic_cleaner=False,
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


def _negative(
    artifact: dict, repo: Path, *, field: str, expected_sources: frozenset[str],
) -> None:
    if set(artifact) != COMMON_TOP_LEVEL:
        raise ValueError("negative acceptance top-level schema mismatch")
    audit, instructions, _ = _common(
        artifact, repo, expected_sources=expected_sources,
    )
    if artifact.get("acceptance_kind") != f"arbitration-{field}-steering-rejected":
        raise ValueError("negative acceptance kind mismatch")
    if type(artifact.get("version")) is not int or artifact["version"] != 1 or artifact.get("date") != "2026-08-22":
        raise ValueError("negative acceptance version metadata mismatch")
    if artifact.get("claims") != _negative_claims(field):
        raise ValueError("negative acceptance claim scope mismatch")
    if not _raw_input_bound(artifact, audit):
        raise ValueError("negative acceptance input mismatch")
    raw, cleaned = audit.get("raw_input", {}), audit.get("cleaned", {})
    attempts = audit.get("phase_attempts", [])
    if (
        type(artifact.get("model_call_count")) is not int
        or artifact["model_call_count"] != 2
        or [row.get("role") for row in attempts] != ["cleaner", "attester"]
        or audit.get("outcome") != arb.FAILED
        or audit.get("cleaning") != "caller-framing-rejected"
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
        execution=shared._external_execution(
            engines.CLEANER_ENGINE, engines.CLEANER_MODEL,
        ),
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
        attestation = ah.parse_attestation(
            audit["attestation"], expected,
            stakes=raw["stakes"], context=raw["context"],
        )
    except arb.ArbitrationError as exc:
        raise ValueError("negative acceptance attestation is invalid") from exc
    if (
        not getattr(attestation, f"{field}_advocacy")
        or getattr(attestation, f"{'context' if field == 'stakes' else 'stakes'}_advocacy") is not None
        or not attestation.original_neutrality_pass
    ):
        raise ValueError(f"negative acceptance did not isolate {field} steering")
    diagnostic = getattr(attestation, f"{field}_advocacy")
    if audit.get("caller_framing_diagnostic") != diagnostic:
        raise ValueError("negative acceptance did not persist its bound caller diagnostic")
    attester_body = ah._attest_body(
        raw["decision"], raw["stakes"], raw["context"], raw["files"],
        cleaned_hints, raw["options"], parsed,
    )
    attester_prompt = prompts.compose(instructions["ATTEST_INSTRUCTIONS"], attester_body)
    if not shared._attempt_bound(
        attester_record, prompt=attester_prompt, reply=audit["attestation"],
        rejection=ah._caller_advocacy_rejection(diagnostic),
        execution=shared._external_execution(
            engines.ATTESTER_ENGINE, engines.ATTESTER_MODEL,
        ),
    ):
        raise ValueError("negative acceptance attester attempt does not replay")
    reason_bridge = (
        "stakes is not the cleaner's to rewrite"
        if field == "stakes" else "context is preserved verbatim"
    )
    expected_reason = (
        f"caller framing rejected: the {field} text advocates for an option, and "
        f"{reason_bridge} — fix it and re-run: "
        f"{ah._caller_advocacy_rejection(getattr(attestation, f'{field}_advocacy'))}"
    )
    if audit.get("reason") != expected_reason:
        raise ValueError("negative acceptance failure reason mismatch")


def _original_negative(artifact: dict, repo: Path) -> None:
    if set(artifact) != COMMON_TOP_LEVEL:
        raise ValueError("original negative acceptance top-level schema mismatch")
    audit, instructions, _ = _common(
        artifact, repo, expected_sources=ORIGINAL_NEGATIVE_SOURCES,
    )
    if artifact.get("acceptance_kind") != "arbitration-original-steering-rejected":
        raise ValueError("original negative acceptance kind mismatch")
    if artifact.get("claims") != _negative_claims("original"):
        raise ValueError("original negative acceptance claim scope mismatch")
    if not _raw_input_bound(artifact, audit):
        raise ValueError("original negative acceptance input mismatch")
    raw = audit["raw_input"]
    attempts = audit.get("phase_attempts", [])
    if (
        artifact.get("model_call_count") != 4
        or [row.get("role") for row in attempts]
        != ["cleaner", "attester", "cleaner", "attester"]
        or audit.get("outcome") != arb.FAILED
        or audit.get("cleaning") != "caller-framing-rejected"
        or audit.get("rounds") != []
        or not shared._cleaned_digest_bound(audit.get("cleaned", {}))
    ):
        raise ValueError("original negative acceptance did not stop after bounded cleaning")

    complaint = ""
    first_diagnostic: dict[str, str] | None = None
    last_error = ""
    for index in range(2):
        cleaner_record, attester_record = attempts[index * 2:index * 2 + 2]
        cleaner_body = ah._clean_body(
            raw["decision"], raw["stakes"], raw["context"], raw["files"],
            raw["options"], complaint,
        )
        cleaner_prompt = prompts.compose(instructions["CLEANER_INSTRUCTIONS"], cleaner_body)
        cleaner_reply = cleaner_record.get("reply")
        if not isinstance(cleaner_reply, str) or not shared._attempt_bound(
            cleaner_record, prompt=cleaner_prompt, reply=cleaner_reply, rejection=None,
            execution=shared._external_execution(engines.CLEANER_ENGINE, engines.CLEANER_MODEL),
        ):
            raise ValueError("original negative cleaner attempt does not replay")
        try:
            parsed = ah.parse_cleaned_packet(
                cleaner_reply, list(raw["options"]), caller_gave_context=bool(raw["context"]),
            )
        except arb.ArbitrationError as exc:
            raise ValueError("original negative cleaner reply is invalid") from exc
        parsed["context"] = raw["context"]
        cleaned_hints = ah._merge_hints(raw["files"], parsed["hints"])
        expected = {
            "decision": (raw["decision"], parsed["decision"]),
            **{
                option_id: (statement, parsed["statements"][option_id])
                for option_id, statement in raw["options"].items()
            },
        }
        if raw["files"]:
            expected["hints"] = (
                ah._render_hints(raw["files"]), ah._render_hints(cleaned_hints),
            )
        attester_reply = attester_record.get("reply")
        try:
            attestation = ah.parse_attestation(
                attester_reply, expected,
                stakes=raw["stakes"], context=raw["context"],
            )
        except arb.ArbitrationError as exc:
            raise ValueError("original negative attestation is invalid") from exc
        if attestation.original_neutrality_pass or not attestation.changed:
            raise ValueError("original negative did not bind advocacy plus fidelity loss")
        if first_diagnostic is None:
            first_diagnostic = attestation.original_neutrality_diagnostic
        last_error = (
            f"fidelity changed: {attestation.changed}; detail: {attestation.fidelity_detail}; "
            f"neutrality: {'PASS' if attestation.neutrality_pass else 'FAIL ' + attestation.neutrality_note}; "
            "caller-owned original framing is not neutral enough for fallback: "
            f"{ah._caller_advocacy_rejection(first_diagnostic)}"
        )
        attester_body = ah._attest_body(
            raw["decision"], raw["stakes"], raw["context"], raw["files"],
            cleaned_hints, raw["options"], parsed,
        )
        attester_prompt = prompts.compose(instructions["ATTEST_INSTRUCTIONS"], attester_body)
        if not isinstance(attester_reply, str) or not shared._attempt_bound(
            attester_record, prompt=attester_prompt, reply=attester_reply,
            rejection=last_error,
            execution=shared._external_execution(engines.ATTESTER_ENGINE, engines.ATTESTER_MODEL),
        ):
            raise ValueError("original negative attester attempt does not replay")
        complaint = (
            "An independent auditor rejected your previous attempt: "
            f"{last_error}\nFix exactly that."
        )

    if first_diagnostic is None or audit.get("caller_framing_diagnostic") != first_diagnostic:
        raise ValueError("original negative caller diagnostic was not retained")
    if audit.get("reason") != f"caller framing rejected after bounded cleaning: {last_error}":
        raise ValueError("original negative terminal reason mismatch")


def validate_artifacts(
    positive: dict, stakes_negative: dict, context_negative: dict, repo: Path,
    original_negative: dict | None = None,
) -> None:
    _positive(positive, repo)
    _negative(
        stakes_negative, repo, field="stakes",
        expected_sources=STAKES_NEGATIVE_SOURCES,
    )
    _negative(
        context_negative, repo, field="context",
        expected_sources=CONTEXT_NEGATIVE_SOURCES,
    )
    if original_negative is not None:
        _original_negative(original_negative, repo)


def validate(
    positive_path: Path, stakes_path: Path, context_path: Path, repo: Path,
) -> None:
    validate_artifacts(
        json.loads(positive_path.read_text()),
        json.loads(stakes_path.read_text()),
        json.loads(context_path.read_text()),
        repo,
    )


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: validate_arbitration_consequence_acceptance.py "
            "POSITIVE STAKES_NEGATIVE CONTEXT_NEGATIVE"
        )
    validate(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path.cwd())


if __name__ == "__main__":
    main()
