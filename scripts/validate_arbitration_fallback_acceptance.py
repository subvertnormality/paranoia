#!/usr/bin/env python3
"""Validate the separately versioned original-fallback acceptance record."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from paranoia_local import arbitrate_handler as ah
from paranoia_local import arbitration as arb
from paranoia_local import evidence
from paranoia_local import engines
from paranoia_local import inert_git
from paranoia_local import prompts


SOURCES = frozenset({
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/arbitration.py",
    "src/paranoia_local/engines.py",
    "src/paranoia_local/evidence.py",
    "src/paranoia_local/prompts.py",
    "src/paranoia_local/server.py",
    "scripts/run_arbitration_fallback_acceptance.py",
    "scripts/validate_arbitration_fallback_acceptance.py",
    "tests/test_arbitrate_handler.py",
    "tests/test_arbitration_fallback_acceptance.py",
})

SCOPE = {
    "proves": [
        "a reported destructive cleaner candidate was retained as rejected audit data",
        "the current ordinary Claude cleaner completed the six-line attestation path with real deciders",
        "a signed-in Codex attester authorized the complete canonical originals",
        "both signed-in decider prompts contained the complete canonical originals and no substituted cleaned field",
        "the transient snapshot was the exact tree of the recorded durable source commit",
        "the recorded replies parse to the stored votes whose resolved decisive citations recompute the terminal result",
        "attempt-ledger provenance proves the ordinary and deterministic-fallback execution routes",
    ],
    "does_not_prove": [
        "that the current Claude cleaner will reproduce the historical destructive rewrite probabilistically",
        "that either decider's resolved citation semantically entails its constraint",
        "provider service identity beyond the recorded local CLI versions and configured model names",
    ],
}

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _evidence_path(repo: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("acceptance evidence path must be repository-relative")
    path = repo / value
    if not path.is_file():
        raise ValueError(f"acceptance evidence does not exist: {value}")
    return path


def _cleaned_digest_bound(cleaned: dict) -> bool:
    if set(cleaned) != {"decision", "context", "hints", "statements", "sha256"}:
        return False
    fields = {key: cleaned[key] for key in ("decision", "context", "hints", "statements")}
    encoded = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return cleaned["sha256"] == hashlib.sha256(
        encoded.encode("utf-8", "surrogatepass")
    ).hexdigest()


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _external_execution(engine: str, model: str) -> dict[str, str | None]:
    implementation = engines.get_engine(engine)
    return {
        "engine": engine, "model": model, "route": "external-cli",
        "binary": implementation.binary, "cli_version": None,
    }


def _execution_bound(actual: object, expected: dict[str, str | None]) -> bool:
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return False
    if any(actual.get(key) != value for key, value in expected.items() if key != "cli_version"):
        return False
    if expected["route"] != "external-cli":
        return actual.get("cli_version") is None
    value = actual.get("cli_version")
    if not isinstance(value, str) or re.fullmatch(r"\d+\.\d+\.\d+", value) is None:
        return False
    minimum = (
        engines.MIN_CODEX_VERSION if expected["engine"] == "codex"
        else engines.MIN_CLAUDE_VERSION
    )
    return tuple(int(part) for part in value.split(".")) >= minimum


def _attempt_bound(
    record: dict, *, prompt: str, reply: str, rejection: str | None,
    execution: dict[str, str | None],
) -> bool:
    return (
        record.get("status") == "provider-completed"
        and record.get("admitted") is True
        and record.get("invoked") is True
        and record.get("prompt_sha256") == _text_digest(prompt)
        and record.get("prompt_excerpt") == ah._bounded_research_text(prompt)
        and record.get("reply_sha256") == _text_digest(reply)
        and record.get("reply") == reply
        and record.get("rejection") == rejection
        and _execution_bound(record.get("execution"), execution)
    )


def _effective_packet(audit: dict) -> ah.Packet:
    raw = audit["raw_input"]
    cleaned = audit["cleaned"]
    original = audit.get("cleaning") == "original-attested"
    return ah.Packet(
        decision=raw["decision"] if original else cleaned["decision"],
        stakes=raw["stakes"], context=raw["context"] if original else cleaned["context"],
        hints=list(raw["files"] if original else cleaned["hints"]),
        statements=dict(raw["options"] if original else cleaned["statements"]),
        cleaning=audit["cleaning"], attestation=audit["attestation"],
    )


def _cleaning_and_attestation_bound(audit: dict, *, fallback: bool) -> bool:
    raw, cleaned = audit["raw_input"], audit["cleaned"]
    phase_attempts = audit.get("phase_attempts", [])
    if [row.get("role") for row in phase_attempts] != ["cleaner", "attester"]:
        return False
    cleaner, attester_record = phase_attempts
    if cleaner.get("attempt") != 1 or attester_record.get("attempt") != 1:
        return False
    cleaner_body = ah._clean_body(
        raw["decision"], raw["stakes"], raw["context"], raw["files"],
        raw["options"], "",
    )
    cleaner_prompt = prompts.compose(prompts.CLEANER_INSTRUCTIONS, cleaner_body)
    cleaner_reply = cleaner.get("reply")
    if not isinstance(cleaner_reply, str) or not _attempt_bound(
        cleaner, prompt=cleaner_prompt, reply=cleaner_reply, rejection=None,
        execution=(
            ah._execution_identity(
                engines.CLEANER_ENGINE, engines.CLEANER_MODEL,
                route="deterministic-cleaner",
            )
            if fallback else _external_execution(
                engines.CLEANER_ENGINE, engines.CLEANER_MODEL,
            )
        ),
    ):
        return False
    try:
        parsed = ah.parse_cleaned_packet(
            cleaner_reply, list(raw["options"]),
            caller_gave_context=bool(raw["context"]),
        )
    except arb.ArbitrationError:
        return False
    parsed["context"] = raw["context"]
    if set(parsed["hints"]) != {hint["path"] for hint in raw["files"]}:
        return False
    cleaned_hints = ah._merge_hints(raw["files"], parsed["hints"])
    if {
        "decision": parsed["decision"], "context": parsed["context"],
        "hints": cleaned_hints, "statements": parsed["statements"],
    } != {key: cleaned[key] for key in ("decision", "context", "hints", "statements")}:
        return False
    expected = {
        "decision": (raw["decision"], cleaned["decision"]),
        **{
            option_id: (statement, cleaned["statements"][option_id])
            for option_id, statement in raw["options"].items()
        },
    }
    if raw["files"]:
        expected["hints"] = (
            ah._render_hints(raw["files"]), ah._render_hints(cleaned["hints"]),
        )
    try:
        attestation = ah.parse_attestation(audit["attestation"], expected)
    except (KeyError, arb.ArbitrationError):
        return False
    if (
        (fallback and attestation.ok)
        or (not fallback and not attestation.ok)
        or not attestation.original_neutrality_pass
        or attestation.stakes_advocacy is not None
        or attestation.context_advocacy is not None
    ):
        return False
    expected_rejection = None if attestation.ok else (
        f"fidelity changed: {attestation.changed}; detail: {attestation.fidelity_detail}; "
        f"neutrality: {'PASS' if attestation.neutrality_pass else 'FAIL ' + attestation.neutrality_note}"
    )
    attester_body = ah._attest_body(
        raw["decision"], raw["stakes"], raw["context"], raw["files"],
        cleaned_hints, raw["options"], parsed,
    )
    attester_prompt = prompts.compose(prompts.ATTEST_INSTRUCTIONS, attester_body)
    return _attempt_bound(
        attester_record, prompt=attester_prompt, reply=audit["attestation"],
        rejection=expected_rejection,
        execution=_external_execution(engines.ATTESTER_ENGINE, engines.ATTESTER_MODEL),
    )


def _decider_transcripts(audit: dict) -> list[arb.Vote] | None:
    if len(audit.get("rounds", [])) != 1 or set(audit["rounds"][0]) != {"codex", "claude"}:
        return None
    packet = _effective_packet(audit)
    votes: list[arb.Vote] = []
    for engine, cast in audit["rounds"][0].items():
        mapping = audit.get("label_maps", {}).get(engine)
        if not isinstance(mapping, dict) or set(mapping.values()) != set(packet.statements):
            return None
        presentation = arb.Presentation(
            engine=engine,
            items=tuple((label, packet.statements[option_id]) for label, option_id in mapping.items()),
            label_to_id=dict(mapping),
            id_to_label={option_id: label for label, option_id in mapping.items()},
            reversed_order=False,
        )
        expected_body = ah.render_decider_body(packet, presentation)
        attempts = cast.get("attempts", [])
        if len(attempts) != 1 or attempts[0].get("body") != expected_body:
            return None
        reply = cast.get("reply")
        prompt = prompts.compose(prompts.ARBITRATE_INSTRUCTIONS, expected_body)
        attempt = attempts[0]
        if (
            cast.get("prompt") != expected_body
            or not isinstance(reply, str)
            or attempt.get("raw") != reply
            or attempt.get("failure") is not None
            or not _attempt_bound(
                {**attempt, "reply": attempt.get("raw"),
                 "reply_sha256": _text_digest(attempt.get("raw", ""))},
                prompt=prompt, reply=reply, rejection=None,
                execution=_external_execution(
                    engine,
                    engines.get_engine(engine).default_model,
                ),
            )
        ):
            return None
        try:
            vote = arb.parse_verdict(reply, presentation)
        except arb.ArbitrationError:
            return None
        if ah._vote_record(vote) != {
            key: cast[key] for key in (
                "label", "selected", "severity", "risk", "authority", "new_option",
                "constraint", "decisive", "citations",
            )
        }:
            return None
        votes.append(vote)
    return votes


def _snapshot_and_outcome_bound(repo: Path, artifact: dict, audit: dict, votes: list[arb.Vote]) -> bool:
    meta = artifact.get("snapshot_binding", {})
    if set(meta) != {"commit_object", "sha256", "source_commit", "tree"}:
        return False
    object_path = _evidence_path(repo, meta["commit_object"])
    content = object_path.read_bytes()
    if _sha256(object_path) != meta["sha256"]:
        return False
    object_id = hashlib.sha1(
        b"commit " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()
    lines = content.decode("utf-8").splitlines()
    if (
        object_id != audit.get("snapshot")
        or lines[:2] != [f"tree {meta['tree']}", f"parent {meta['source_commit']}"]
    ):
        return False
    source_commit = inert_git.text(
        repo, ["rev-parse", "--verify", f"{meta['source_commit']}^{{commit}}"],
    ).strip()
    source_tree = inert_git.text(repo, ["rev-parse", f"{source_commit}^{{tree}}"] ).strip()
    if source_commit != meta["source_commit"] or source_tree != meta["tree"]:
        return False
    resolver = evidence.LinkResolver(repo, source_commit)

    def resolve(citation: arb.Citation) -> arb.Region | None:
        got = evidence.resolve_citation(
            repo, citation, snapshot=source_commit, links=resolver,
            context=arb.CONTEXT_LINES,
        )
        return got[0] if got else None

    substantiated = arb.substantiation(votes, resolve=resolve)
    if substantiated != {"codex": True, "claude": True}:
        return False
    outcome = arb.compute_outcome(votes, substantiated=substantiated)
    return (
        outcome.outcome == audit.get("outcome")
        and outcome.selected == audit.get("selected")
        and outcome.reason == audit.get("reason")
    )


def _timing_bound(record: dict, audit_sha256: str) -> bool:
    if set(record) != {
        "started_utc", "finished_utc", "monotonic_elapsed_seconds", "exit_status",
        "audit_sha256",
    }:
        return False
    try:
        started = datetime.fromisoformat(record["started_utc"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(record["finished_utc"].replace("Z", "+00:00"))
        elapsed = record["monotonic_elapsed_seconds"]
    except (KeyError, TypeError, ValueError):
        return False
    return (
        type(elapsed) in (int, float) and elapsed > 0
        and abs((finished - started).total_seconds() - elapsed) <= 1.0
        and record["exit_status"] == 0
        and record["audit_sha256"] == audit_sha256
    )


def _validate_run(
    *, repo: Path, artifact: dict, audit_meta: dict, timing_meta: dict,
    fallback: bool,
) -> None:
    if set(audit_meta) != {"path", "sha256", "snapshot", "cleaning", "result"}:
        raise ValueError("acceptance audit metadata schema mismatch")
    audit_path = _evidence_path(repo, audit_meta["path"])
    if _sha256(audit_path) != audit_meta["sha256"]:
        raise ValueError("acceptance audit digest mismatch")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    expected_cleaning = "original-attested" if fallback else "attested"
    if not (
        audit_meta["cleaning"] == audit.get("cleaning") == expected_cleaning
        and audit_meta["snapshot"] == audit.get("snapshot")
        and audit_meta["result"] == audit.get("outcome") == "CONVERGED"
        and _cleaned_digest_bound(audit.get("cleaned", {}))
        and (not fallback or audit["cleaned"]["statements"] != audit["raw_input"]["options"])
        and _cleaning_and_attestation_bound(audit, fallback=fallback)
    ):
        raise ValueError("acceptance audit does not prove its exact delivery route")
    votes = _decider_transcripts(audit)
    if votes is None or not _snapshot_and_outcome_bound(repo, artifact, audit, votes):
        raise ValueError("acceptance audit does not replay to its terminal result")
    if set(timing_meta) != {"path", "sha256"}:
        raise ValueError("acceptance timing metadata schema mismatch")
    timing_path = _evidence_path(repo, timing_meta["path"])
    if _sha256(timing_path) != timing_meta["sha256"]:
        raise ValueError("acceptance timing digest mismatch")
    if not _timing_bound(json.loads(timing_path.read_text()), audit_meta["sha256"]):
        raise ValueError("acceptance timing record mismatch")


def validate(artifact_path: Path, repo: Path) -> None:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if set(artifact) != {
        "acceptance_kind", "acceptance_scope", "audits", "timings",
        "snapshot_binding", "source_commit", "source_sha256", "tests",
    }:
        raise ValueError("fallback acceptance top-level schema mismatch")
    if artifact["acceptance_kind"] != "arbitration-original-fallback-v2":
        raise ValueError("unsupported fallback acceptance kind")
    if artifact["acceptance_scope"] != SCOPE:
        raise ValueError("fallback acceptance claim scope mismatch")
    if set(artifact["source_sha256"]) != SOURCES:
        raise ValueError("fallback acceptance source set mismatch")
    source_commit = artifact.get("source_commit")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("fallback acceptance source commit is invalid")
    for relative, digest in artifact["source_sha256"].items():
        blob = inert_git.invoke(repo, ["show", f"{source_commit}:{relative}"])
        if (
            not _is_sha256(digest)
            or blob.returncode != 0
            or hashlib.sha256(blob.stdout).hexdigest() != digest
        ):
            raise ValueError(f"fallback acceptance source hash mismatch: {relative}")

    if set(artifact["audits"]) != {"ordinary", "fallback"} or set(artifact["timings"]) != {
        "ordinary", "fallback",
    }:
        raise ValueError("acceptance run set mismatch")
    _validate_run(
        repo=repo, artifact=artifact, audit_meta=artifact["audits"]["ordinary"],
        timing_meta=artifact["timings"]["ordinary"], fallback=False,
    )
    _validate_run(
        repo=repo, artifact=artifact, audit_meta=artifact["audits"]["fallback"],
        timing_meta=artifact["timings"]["fallback"], fallback=True,
    )
    if artifact["audits"]["ordinary"]["snapshot"] != artifact["audits"]["fallback"]["snapshot"]:
        raise ValueError("acceptance runs did not share one source snapshot")
    if artifact["tests"] != {"full_suite": "1111 passed", "exit_status": 0}:
        raise ValueError("fallback acceptance test record mismatch")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_arbitration_fallback_acceptance.py ARTIFACT REPO")
    validate(Path(sys.argv[1]), Path(sys.argv[2]).resolve())
    print("arbitration original-fallback acceptance: valid")


if __name__ == "__main__":
    main()
