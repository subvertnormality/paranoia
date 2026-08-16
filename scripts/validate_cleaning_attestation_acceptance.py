#!/usr/bin/env python3
"""Fail unless an arbitration acceptance summary is derived from its exact audit."""

from __future__ import annotations

import hashlib
import json
import re
import runpy
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from paranoia_local import arbitrate_handler as production_arbitrate  # noqa: E402
from paranoia_local import arbitration as production_protocol  # noqa: E402
from paranoia_local import evidence as production_evidence  # noqa: E402
from paranoia_local import prompts as production_prompts  # noqa: E402

PRODUCTION_SOURCES = frozenset({
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/arbitration.py",
    "src/paranoia_local/arbitration_research.py",
    "src/paranoia_local/engines.py",
    "src/paranoia_local/evidence.py",
    "src/paranoia_local/external_sources.py",
    "src/paranoia_local/handlers.py",
    "src/paranoia_local/plan_claims.py",
    "src/paranoia_local/review_census.py",
})
ENGINES = frozenset({"codex", "claude"})
CLEANING_SOURCES = frozenset({
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/prompts.py",
    "src/paranoia_local/server.py",
})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _invoked_count(attempts: list[dict]) -> int:
    values = [attempt.get("invoked") for attempt in attempts]
    if any(type(value) is not bool for value in values):
        raise ValueError("every invoked ledger value must be an exact boolean")
    return sum(values)


def _exact_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _exact_numeric_schema(artifact: dict) -> None:
    metrics = artifact["delivery_metrics"]
    diff_keys = {"files", "lines_added", "lines_removed", "net_lines"}
    for name in ("production_diff", "all_changed_files_diff"):
        row = metrics[name]
        if set(row) != diff_keys or any(type(row[key]) is not int for key in diff_keys):
            raise ValueError(f"{name} numeric schema mismatch")
        if any(row[key] < 0 for key in ("files", "lines_added", "lines_removed")):
            raise ValueError(f"{name} numeric values are invalid")
    calls = metrics["model_calls"]
    call_groups = {"positive", "original_input"}
    call_fields = {"cleaner", "attester", "codex_decider", "claude_decider", "total"}
    if set(calls) != call_groups:
        raise ValueError("model-call group schema mismatch")
    for name in call_groups:
        if (
            set(calls[name]) != call_fields
            or any(not _exact_nonnegative_int(calls[name][key]) for key in call_fields)
        ):
            raise ValueError(f"{name} model-call numeric schema mismatch")
    for name in ("positive_long_context", "original_report_input"):
        if (
            not _exact_nonnegative_int(artifact[name]["context_chars"])
            or not _exact_nonnegative_int(artifact[name]["rounds"])
        ):
            raise ValueError(f"{name} count schema mismatch")
    for row in metrics["largest_production_modules"]:
        if set(row) != {"path", "lines"} or not _exact_nonnegative_int(row["lines"]):
            raise ValueError("largest production module numeric schema mismatch")
    for prefix in ("focused", "full"):
        if type(artifact["tests"][f"{prefix}_exit_status"]) is not int:
            raise ValueError(f"{prefix} test exit status schema mismatch")


def _validate_hashes(hashes: dict[str, str], expected: frozenset[str], repo: Path) -> None:
    if set(hashes) != expected:
        raise ValueError("production_source_sha256 does not name the complete source set")
    for relative, expected_hash in hashes.items():
        if _sha256(repo / relative) != expected_hash:
            raise ValueError(f"production hash mismatch: {relative}")


def _phase_counts(audit: dict) -> dict[str, int]:
    rows = audit["phase_attempts"]
    roles = [row["role"] for row in rows]
    if roles not in (["cleaner", "attester"],
                     ["cleaner", "attester", "cleaner", "attester"]):
        raise ValueError("phase attempts must contain one or two ordered cleaner/attester pairs")
    return {
        role: _invoked_count([row for row in rows if row["role"] == role])
        for role in ("cleaner", "attester")
    }


def _decider_counts(audit: dict) -> dict[str, int]:
    counts = {engine: 0 for engine in ENGINES}
    for round_record in audit["rounds"]:
        if set(round_record) != ENGINES:
            raise ValueError("every round must contain each decider exactly once")
        for engine, cast in round_record.items():
            counts[engine] += _invoked_count(cast["attempts"])
    return counts


def _derived_outcome_bound(audit: dict, fixture_repo: Path) -> bool:
    if len(audit["rounds"]) != 1 or set(audit.get("label_maps", {})) != ENGINES:
        return False
    snapshot = production_arbitrate._snapshot(fixture_repo)
    if audit["snapshot"] != snapshot:
        return False
    cleaned = audit["cleaned"]
    packet = production_arbitrate.Packet(
        decision=cleaned["decision"], stakes=audit["raw_input"]["stakes"],
        context=cleaned["context"], hints=cleaned["hints"],
        statements=cleaned["statements"], cleaning=audit["cleaning"],
        attestation=audit["attestation"],
    )
    votes = []
    resolver = production_evidence.LinkResolver(fixture_repo, snapshot)
    round_record = audit["rounds"][0]
    if set(round_record) != ENGINES:
        return False
    for engine in round_record:
        mapping = audit["label_maps"][engine]
        if set(mapping.values()) != set(cleaned["statements"]) or len(mapping) != len(set(mapping.values())):
            return False
        presentation = production_protocol.Presentation(
            engine=engine,
            items=tuple((label, cleaned["statements"][option_id]) for label, option_id in mapping.items()),
            label_to_id=mapping,
            id_to_label={option_id: label for label, option_id in mapping.items()},
            reversed_order=False,
        )
        cast = round_record[engine]
        if set(cast) != {
            "label", "selected", "severity", "risk", "authority", "new_option",
            "constraint", "decisive", "citations", "prompt", "reply", "attempts",
        }:
            return False
        base_body = production_arbitrate.render_decider_body(packet, presentation)
        attempts = cast.get("attempts", [])
        if not (1 <= len(attempts) <= 2) or attempts[0].get("body") != base_body:
            return False
        expected_body = base_body
        for index, attempt in enumerate(attempts):
            if (
                set(attempt) != {
                    "body", "raw", "rejection", "prompt_sha256", "prompt_excerpt",
                    "failure", "status", "admitted", "invoked",
                }
                or attempt.get("body") != expected_body
                or attempt.get("status") != "provider-completed"
                or attempt.get("admitted") is not True
                or attempt.get("invoked") is not True
                or attempt.get("failure") is not None
                or not isinstance(attempt.get("raw"), str)
                or not attempt["raw"]
            ):
                return False
            prompt = production_prompts.compose(
                production_prompts.ARBITRATE_INSTRUCTIONS, expected_body,
            )
            if (
                attempt.get("prompt_sha256") != hashlib.sha256(prompt.encode()).hexdigest()
                or attempt.get("prompt_excerpt")
                != production_arbitrate._bounded_research_text(prompt)
            ):
                return False
            if index == 0 and len(attempts) == 2:
                try:
                    production_protocol.parse_verdict(attempt.get("raw", ""), presentation)
                except production_protocol.ArbitrationError as exc:
                    if attempt.get("rejection") != str(exc):
                        return False
                    expected_body = (
                        base_body + "\n\n=== FORMAT CORRECTION ===\n"
                        + f"Your previous reply was rejected: {str(exc)[:1000]}\n"
                        + "Fix exactly that. Return one complete replacement reply. Do not "
                        "quote, preview, or discuss any trailer field name in the prose before "
                        "the final trailer block."
                    )
                else:
                    return False
            elif attempt.get("rejection") is not None:
                return False
        if cast.get("prompt") != attempts[-1].get("body") or cast.get("reply") != attempts[-1].get("raw"):
            return False
        try:
            vote = production_protocol.parse_verdict(cast.get("reply", ""), presentation)
        except production_protocol.ArbitrationError:
            return False
        if production_arbitrate._vote_record(vote) != {
            key: cast.get(key) for key in (
                "label", "selected", "severity", "risk", "authority", "new_option",
                "constraint", "decisive", "citations",
            )
        }:
            return False
        votes.append(vote)

    substantiated = production_protocol.substantiation(
        votes,
        resolve=lambda citation: (
            resolved[0] if (resolved := production_evidence.resolve_citation(
                fixture_repo, citation, snapshot=snapshot, links=resolver,
                context=production_protocol.CONTEXT_LINES,
            )) else None
        ),
    )
    outcome = production_protocol.compute_outcome(votes, substantiated=substantiated)
    return (
        audit["outcome"] == outcome.outcome
        and audit["selected"] == outcome.selected
        and audit["reason"] == outcome.reason
    )


def _validate_cleaning_acceptance(artifact: dict, repo: Path) -> None:
    expected_top = {
        "acceptance_kind", "acceptance_scope", "delivery_metrics", "positive_long_context",
        "original_report_input", "production_source_sha256",
        "timing_record", "tests",
    }
    if set(artifact) != expected_top:
        raise ValueError("cleaning acceptance top-level schema is incomplete or contains unverified fields")
    expected_scope = {
        "proves": [
            "caller context and normalized options reached both deciders in the recorded runs",
            "cleaner and attester lifecycle, prompts, replies, diagnostics, and call counts match the audits",
            "the recorded production result and selection are reproduced from the checked-in audits",
        ],
        "does_not_prove": [
            "that a resolved repository citation entails a decider constraint",
            "that the positive fixture independently substantiates the selected option",
            "that the original run exercised agreed-but-unsubstantiated fail-closed behavior",
        ],
    }
    if artifact["acceptance_scope"] != expected_scope:
        raise ValueError("cleaning acceptance claim scope mismatch")
    if set(artifact["delivery_metrics"]) != {
        "diff_base", "production_diff", "all_changed_files_diff",
        "largest_production_modules", "model_calls",
    }:
        raise ValueError("cleaning delivery metrics schema is incomplete or contains unverified fields")
    common_summary = {
        "context_chars", "result", "cleaning", "snapshot", "refs_moved",
        "audit", "audit_sha256", "options", "rounds", "research",
    }
    if set(artifact["positive_long_context"]) != common_summary | {
        "selected", "attestation", "outcome_basis",
    }:
        raise ValueError("positive cleaning summary schema is incomplete or contains unverified fields")
    if set(artifact["original_report_input"]) != common_summary | {
        "selected", "attestation", "reason", "outcome_basis",
    }:
        raise ValueError("original-input summary schema is incomplete or contains unverified fields")
    if set(artifact["timing_record"]) != {"path", "sha256", "runs", "runner_sources"}:
        raise ValueError("timing record schema is incomplete or contains unverified fields")
    if set(artifact["tests"]) != {
        "focused_log", "focused_log_sha256", "focused_result",
        "focused_exit_status", "full_log", "full_log_sha256", "full_result",
        "full_exit_status", "runner_manifest", "runner_manifest_sha256",
    }:
        raise ValueError("test record schema is incomplete or contains unverified fields")
    _exact_numeric_schema(artifact)
    _validate_hashes(artifact["production_source_sha256"], CLEANING_SOURCES, repo)
    audits: dict[str, dict] = {}
    for name in ("positive_long_context", "original_report_input"):
        summary = artifact[name]
        path = _evidence_path(repo, summary["audit"])
        if not path.is_file():
            raise ValueError(f"referenced {name} audit does not exist: {path}")
        if _sha256(path) != summary["audit_sha256"]:
            raise ValueError(f"{name} audit_sha256 does not match referenced audit")
        audits[name] = json.loads(path.read_text(encoding="utf-8"))

    positive = audits["positive_long_context"]
    original = audits["original_report_input"]
    positive_summary = artifact["positive_long_context"]
    original_summary = artifact["original_report_input"]
    positive_phases = _phase_counts(positive)
    original_phases = _phase_counts(original)
    positive_deciders = _decider_counts(positive)
    original_deciders = _decider_counts(original)
    expected_calls = artifact["delivery_metrics"]["model_calls"]
    fixture_source = _evidence_path(
        repo, "docs/cleaning_attestation_evidence/acceptance_fixture.py",
    )
    fixture_namespace = runpy.run_path(str(fixture_source))
    repository_fixture = fixture_namespace.get("repository_fixture")
    if not callable(repository_fixture):
        raise ValueError("acceptance fixture source has no repository_fixture")
    with repository_fixture() as fixture_repo:
        # This reproduces the production outcome, including its citation-resolution
        # rule. It does not elevate resolution into an independent semantic
        # entailment attestation; that exclusion is explicit in acceptance_scope.
        positive_outcome_bound = _derived_outcome_bound(positive, fixture_repo)
        original_outcome_bound = _derived_outcome_bound(original, fixture_repo)
    positive_votes = {cast["selected"] for cast in positive["rounds"][-1].values()}
    original_votes = {cast["selected"] for cast in original["rounds"][-1].values()}
    checks = {
        "positive outcome": positive["outcome"] == positive_summary["result"],
        "positive selection": positive["selected"] == positive_summary["selected"],
        "positive cleaning": positive["cleaning"] == positive_summary["cleaning"],
        "positive snapshot": positive["snapshot"] == positive_summary["snapshot"],
        "positive refs moved": positive["refs_moved"] is positive_summary["refs_moved"],
        "positive context length": len(positive["raw_input"]["context"]) == positive_summary["context_chars"],
        "positive context equality": positive["raw_input"]["context"] == positive["cleaned"]["context"],
        "positive cleaned packet": _cleaned_packet_bound(positive),
        "positive option mapping": positive["raw_input"]["options"] == positive_summary["options"],
        "positive attestation": positive["attestation"].splitlines() == positive_summary["attestation"],
        "positive diagnostics": _phase_diagnostics_bound(positive),
        "positive prompt bindings": _phase_prompts_bound(positive),
        "positive derived outcome": positive_outcome_bound,
        "positive outcome basis": (
            positive_summary["outcome_basis"] == "observed unanimous production result; citation entailment not independently attested"
            and len(positive_votes) == 1
        ),
        "positive rounds": len(positive["rounds"]) == positive_summary["rounds"],
        "positive research": (
            positive_summary["research"] == "repository-only"
            and positive["research"] == {"enabled": False, "digest": None, "packets": None, "runs": []}
        ),
        "positive phases": positive_phases == {"cleaner": expected_calls["positive"]["cleaner"], "attester": expected_calls["positive"]["attester"]},
        "positive deciders": positive_deciders == {"codex": expected_calls["positive"]["codex_decider"], "claude": expected_calls["positive"]["claude_decider"]},
        "positive total": sum(positive_phases.values()) + sum(positive_deciders.values()) == expected_calls["positive"]["total"],
        "original outcome": original["outcome"] == original_summary["result"],
        "original selection": original["selected"] == original_summary["selected"],
        "original cleaning": original["cleaning"] == original_summary["cleaning"],
        "original snapshot": original["snapshot"] == original_summary["snapshot"],
        "original refs moved": original["refs_moved"] is original_summary["refs_moved"],
        "original context length": len(original["raw_input"]["context"]) == original_summary["context_chars"],
        "original context equality": original["raw_input"]["context"] == original["cleaned"]["context"],
        "original cleaned packet": _cleaned_packet_bound(original),
        "original option mapping": original["raw_input"]["options"] == original_summary["options"],
        "original attestation": original["attestation"].splitlines() == original_summary["attestation"],
        "original rounds": len(original["rounds"]) == original_summary["rounds"],
        "original research": (
            original_summary["research"] == "repository-only"
            and original["research"] == {"enabled": False, "digest": None, "packets": None, "runs": []}
        ) if original_summary["research"] == "repository-only" else (
            original_summary["research"] == "not reached"
            and original["research"].get("status") == "not reached"
            and original["research"].get("runs") == []
        ),
        "original reason": original["reason"] == original_summary["reason"],
        "original diagnostics": _phase_diagnostics_bound(
            original, accepted=(
                original["cleaning"].startswith("attested")
                or original["cleaning"] == "original-attested"
            )
        ),
        "original prompt bindings": _phase_prompts_bound(original),
        "original derived outcome": original_outcome_bound,
        "original outcome basis": (
            original_summary["outcome_basis"] == "decider selection divergence"
            and len(original_votes) > 1
        ),
        "original phases": original_phases == {"cleaner": expected_calls["original_input"]["cleaner"], "attester": expected_calls["original_input"]["attester"]},
        "original deciders": original_deciders == {"codex": expected_calls["original_input"]["codex_decider"], "claude": expected_calls["original_input"]["claude_decider"]},
        "original total": sum(original_phases.values()) + sum(original_deciders.values()) == expected_calls["original_input"]["total"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("cleaning acceptance reconciliation failed: " + ", ".join(failed))

    timing_path = _evidence_path(repo, artifact["timing_record"]["path"])
    if _sha256(timing_path) != artifact["timing_record"]["sha256"]:
        raise ValueError("timing record digest mismatch")
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    if timing != artifact["timing_record"]["runs"] or set(timing) != {"positive", "original"}:
        raise ValueError("timing record schema mismatch")
    for name, summary in (("positive", positive_summary), ("original", original_summary)):
        row = timing[name]
        if set(row) != {
            "command", "started_utc", "finished_utc", "monotonic_elapsed_seconds",
            "exit_status", "audit", "audit_sha256",
        }:
            raise ValueError(f"{name} timing record schema mismatch")
        expected_live_command = [
            "{python}",
            f"docs/cleaning_attestation_evidence/run_{name}_acceptance.py",
        ]
        if row["command"] != expected_live_command or not row["started_utc"].endswith("Z") or not row["finished_utc"].endswith("Z"):
            raise ValueError(f"{name} timing boundary is incomplete")
        if (
            type(row["monotonic_elapsed_seconds"]) not in (int, float)
            or row["monotonic_elapsed_seconds"] <= 0
            or type(row["exit_status"]) is not int
        ):
            raise ValueError(f"{name} timing elapsed is invalid")
        if row["exit_status"] != 0 or row["audit"] != summary["audit"] or row["audit_sha256"] != summary["audit_sha256"]:
            raise ValueError(f"{name} timing record is not bound to its audit")
        try:
            started = datetime.fromisoformat(row["started_utc"].replace("Z", "+00:00"))
            finished = datetime.fromisoformat(row["finished_utc"].replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} timing boundary is not ISO-8601") from exc
        wall_seconds = (finished - started).total_seconds()
        if wall_seconds <= 0 or abs(wall_seconds - row["monotonic_elapsed_seconds"]) > 0.1:
            raise ValueError(f"{name} wall and monotonic durations disagree")

    runner_sources = artifact["timing_record"]["runner_sources"]
    expected_runner_paths = {
        "wrapper": "docs/cleaning_attestation_evidence/run_timed_acceptances.py",
        "original": "docs/cleaning_attestation_evidence/run_original_acceptance.py",
        "positive": "docs/cleaning_attestation_evidence/run_positive_acceptance.py",
        "fixture": "docs/cleaning_attestation_evidence/acceptance_fixture.py",
        "tests": "scripts/run_cleaning_acceptance_checks.py",
        "validator": "scripts/validate_cleaning_attestation_acceptance.py",
    }
    if set(runner_sources) != set(expected_runner_paths):
        raise ValueError("live runner source inventory is incomplete")
    for role, row in runner_sources.items():
        if (
            set(row) != {"path", "sha256"}
            or row["path"] != expected_runner_paths[role]
            or _sha256(_evidence_path(repo, row["path"])) != row["sha256"]
        ):
            raise ValueError("live runner source digest mismatch")

    test_manifest_path = _evidence_path(repo, artifact["tests"]["runner_manifest"])
    if _sha256(test_manifest_path) != artifact["tests"]["runner_manifest_sha256"]:
        raise ValueError("test runner manifest digest mismatch")
    test_manifest = json.loads(test_manifest_path.read_text(encoding="utf-8"))
    if set(test_manifest) != {"focused", "full"}:
        raise ValueError("test runner manifest schema mismatch")
    for prefix in ("focused", "full"):
        test_path = _evidence_path(repo, artifact["tests"][f"{prefix}_log"])
        if _sha256(test_path) != artifact["tests"][f"{prefix}_log_sha256"]:
            raise ValueError(f"{prefix} test log digest mismatch")
        result_text = artifact["tests"][f"{prefix}_result"]
        if artifact["tests"][f"{prefix}_exit_status"] != 0:
            raise ValueError(f"{prefix} test exit status is not successful")
        if (
            not re.fullmatch(r"\d+ passed in \d+\.\d+s(?: \(\d+:\d{2}:\d{2}\))?", result_text)
            or not test_path.read_text(encoding="utf-8").strip().endswith(result_text)
        ):
            raise ValueError(f"{prefix} test result is not a valid successful terminal")
        manifest_row = test_manifest[prefix]
        if set(manifest_row) != {
            "command", "started_utc", "finished_utc", "monotonic_elapsed_seconds",
            "exit_status", "log", "log_sha256", "terminal",
        }:
            raise ValueError(f"{prefix} test runner row schema mismatch")
        if (
            type(manifest_row["exit_status"]) is not int
            or type(manifest_row["monotonic_elapsed_seconds"]) not in (int, float)
        ):
            raise ValueError(f"{prefix} test runner numeric schema mismatch")
        expected_test_command = ["{python}", "-m", "pytest", "-q"]
        if prefix == "focused":
            expected_test_command += [
                "tests/test_arbitrate_handler.py", "tests/test_acceptance_validator.py",
            ]
        if (
            manifest_row["command"] != expected_test_command
            or
            manifest_row["exit_status"] != artifact["tests"][f"{prefix}_exit_status"]
            or manifest_row["log"] != artifact["tests"][f"{prefix}_log"]
            or manifest_row["log_sha256"] != artifact["tests"][f"{prefix}_log_sha256"]
            or manifest_row["terminal"] != result_text
            or not _duration_bound(manifest_row)
        ):
            raise ValueError(f"{prefix} test runner record mismatch")

    base = artifact["delivery_metrics"]["diff_base"]
    expected_base = subprocess.run(
        ["git", "merge-base", "HEAD", "main"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if base != expected_base:
        raise ValueError("delivery diff base is not the HEAD/main merge base")
    result = subprocess.run(
        ["git", "diff", "--numstat", f"{base}..HEAD"], cwd=repo,
        check=True, capture_output=True, text=True,
    )
    added = removed = files = 0
    production_added = production_removed = production_files = 0
    for line in result.stdout.splitlines():
        add, delete, _path = line.split("\t", 2)
        if not add.isdigit() or not delete.isdigit():
            raise ValueError("binary files are not accepted in cleaning delivery metrics")
        added += int(add); removed += int(delete); files += 1
        if _path in CLEANING_SOURCES:
            production_added += int(add); production_removed += int(delete)
            production_files += 1
    if artifact["delivery_metrics"]["all_changed_files_diff"] != {
        "files": files, "lines_added": added, "lines_removed": removed,
        "net_lines": added - removed,
    }:
        raise ValueError("delivery diff metrics do not match git")
    if artifact["delivery_metrics"]["production_diff"] != {
        "files": production_files, "lines_added": production_added,
        "lines_removed": production_removed,
        "net_lines": production_added - production_removed,
    }:
        raise ValueError("production diff metrics do not match git")
    claimed_modules = artifact["delivery_metrics"]["largest_production_modules"]
    if len(claimed_modules) != 6:
        raise ValueError("largest production modules must contain exactly six entries")
    derived_modules = sorted(
        (
            {"path": str(path.relative_to(repo)), "lines": len(path.read_text(encoding="utf-8").splitlines())}
            for path in (repo / "src" / "paranoia_local").glob("*.py")
        ),
        key=lambda row: (-row["lines"], row["path"]),
    )[:len(claimed_modules)]
    if claimed_modules != derived_modules:
        raise ValueError("largest production modules do not match source tree")


def _phase_diagnostics_bound(audit: dict, *, accepted: bool = True) -> bool:
    original_fields = {
        "decision": audit["raw_input"]["decision"],
        **audit["raw_input"]["options"],
    }
    cleaned_fields: dict[str, str] = {}
    expected_keys = {
        "role", "attempt", "status", "admitted", "invoked", "prompt_sha256",
        "prompt_excerpt", "reply", "reply_sha256", "rejection",
    }
    for index, row in enumerate(audit["phase_attempts"]):
        expected_role = "cleaner" if index % 2 == 0 else "attester"
        if (
            set(row) != expected_keys
            or row.get("role") != expected_role
            or row.get("attempt") != index // 2 + 1
            or row.get("status") != "provider-completed"
            or row.get("admitted") is not True
            or row.get("invoked") is not True
            or not isinstance(row.get("prompt_excerpt"), str)
            or not row["prompt_excerpt"]
            or not _is_sha256(row.get("prompt_sha256"))
            or not _is_sha256(row.get("reply_sha256"))
            or hashlib.sha256(row.get("reply", "").encode("utf-8", "surrogatepass")).hexdigest()
            != row["reply_sha256"]
        ):
            return False
        if row["role"] == "cleaner":
            if (
                not row.get("reply")
                or row.get("rejection") is not None
                or index > 0 and not audit["phase_attempts"][index - 1].get("rejection")
            ):
                return False
            cleaned_fields = _cleaner_fields(row["reply"])
            continue
        expected_pairs = {
            field: (original, cleaned_fields[field])
            for field, original in original_fields.items()
            if field in cleaned_fields
        }
        if set(expected_pairs) != set(original_fields):
            return False
        try:
            attestation = _parse_attestation_record(row.get("reply", ""), expected_pairs)
        except production_arbitrate.ArbitrationError:
            return False
        changed = set(attestation.changed)
        raw_detail = attestation.fidelity_detail
        rejection = row.get("rejection")
        neutrality = (
            "PASS" if attestation.neutrality_pass
            else f"FAIL {attestation.neutrality_note}"
        )
        if attestation.stakes_advocacy is not None or attestation.context_advocacy is not None:
            return False
        should_reject = not attestation.ok
        if (rejection is not None) is not should_reject:
            return False
        if should_reject:
            expected_rejection = (
                f"fidelity changed: {sorted(changed)!r}; detail: {raw_detail}; "
                f"neutrality: {neutrality}"
            )
            if rejection != expected_rejection:
                return False
        if index < len(audit["phase_attempts"]) - 1 and rejection is None:
            return False
    attesters = [row for row in audit["phase_attempts"] if row["role"] == "attester"]
    if not attesters or attesters[-1]["reply"] != audit["attestation"]:
        return False
    if accepted is (attesters[-1].get("rejection") is not None):
        return False
    return True


def _parse_attestation_record(
    reply: str, expected: dict[str, tuple[str, str]],
) -> production_arbitrate.Attestation:
    """Validate immutable v1 evidence without pretending it made the v2 judgement.

    Five-line records predate ORIGINAL-NEUTRALITY. Inserting a parser-only PASS lets
    the current closed parser validate their original five claims; callers of this
    helper must never use the synthetic field to authorize original fallback.
    """
    lines = reply.splitlines()
    if len(lines) == 5:
        lines.insert(3, "ORIGINAL-NEUTRALITY: PASS")
    return production_arbitrate.parse_attestation("\n".join(lines), expected)


def _cleaner_fields(reply: str) -> dict[str, str]:
    headings = ("DECISION", "OPTIONS", "CONTEXT", "HINTS")
    sections: dict[str, str] = {}
    for index, heading in enumerate(headings):
        marker = f"=== {heading} ===\n"
        if marker not in reply:
            return {}
        tail = reply.split(marker, 1)[1]
        next_marker = f"\n\n=== {headings[index + 1]} ===" if index + 1 < len(headings) else None
        sections[heading] = tail.split(next_marker, 1)[0].strip() if next_marker else tail.strip()
    fields = {"decision": sections["DECISION"]}
    current_id: str | None = None
    for line in sections["OPTIONS"].splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if match:
            option_id, statement = match.groups()
            if not statement or option_id in fields:
                return {}
            fields[option_id] = statement
            current_id = option_id
        elif line.strip():
            if current_id is None:
                return {}
            fields[current_id] += "\n" + line.strip()
    return fields


def _cleaned_packet_bound(audit: dict) -> bool:
    cleaners = [row for row in audit["phase_attempts"] if row["role"] == "cleaner"]
    if not cleaners or audit["raw_input"].get("files") != []:
        return False
    fields = _cleaner_fields(cleaners[-1].get("reply", ""))
    if not fields:
        return False
    expected = {
        "decision": fields.pop("decision"),
        "context": audit["raw_input"]["context"],
        "hints": [],
        "statements": fields,
    }
    encoded = json.dumps(
        expected, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    expected["sha256"] = hashlib.sha256(encoded.encode("utf-8", "surrogatepass")).hexdigest()
    return set(audit.get("cleaned", {})) == set(expected) and audit["cleaned"] == expected


def _phase_prompts_bound(audit: dict) -> bool:
    raw = audit["raw_input"]
    originals = raw["options"]
    hints = raw.get("files", [])
    complaint = ""
    rows = audit["phase_attempts"]
    try:
        for index in range(0, len(rows), 2):
            cleaner, attester = rows[index:index + 2]
            cleaner_body = production_arbitrate._clean_body(
                raw["decision"], raw["stakes"], raw["context"], hints,
                originals, complaint,
            )
            cleaner_prompt = production_prompts.compose(
                production_prompts.CLEANER_INSTRUCTIONS, cleaner_body,
            )
            if not _prompt_record_bound(cleaner, cleaner_prompt):
                return False
            parsed = production_arbitrate.parse_cleaned_packet(
                cleaner["reply"], list(originals),
                caller_gave_context=bool(raw["context"]),
            )
            parsed["context"] = raw["context"]
            cleaned_hints = production_arbitrate._merge_hints(hints, parsed["hints"])
            attester_body = production_arbitrate._attest_body(
                raw["decision"], raw["stakes"], raw["context"], hints,
                cleaned_hints, originals, parsed,
            )
            attester_prompt = production_prompts.compose(
                production_prompts.ATTEST_INSTRUCTIONS, attester_body,
            )
            if not _prompt_record_bound(attester, attester_prompt):
                return False
            complaint = (
                "An independent auditor rejected your previous attempt: "
                f"{attester['rejection']}\nFix exactly that."
                if attester["rejection"] else ""
            )
    except (KeyError, ValueError, production_arbitrate.ArbitrationError):
        return False
    return len(rows) > 0 and len(rows) % 2 == 0


def _prompt_record_bound(row: dict, prompt: str) -> bool:
    return (
        row["prompt_sha256"]
        == hashlib.sha256(prompt.encode("utf-8", "surrogatepass")).hexdigest()
        and row["prompt_excerpt"] == production_arbitrate._bounded_research_text(prompt)
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _duration_bound(row: dict) -> bool:
    try:
        started = datetime.fromisoformat(row["started_utc"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(row["finished_utc"].replace("Z", "+00:00"))
        elapsed = row["monotonic_elapsed_seconds"]
        return (
            isinstance(elapsed, (int, float)) and elapsed > 0
            and abs((finished - started).total_seconds() - elapsed) <= 0.1
        )
    except (KeyError, TypeError, ValueError):
        return False


def _evidence_path(repo: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("acceptance evidence path must be repository-relative")
    path = repo / value
    if not path.is_file():
        raise ValueError(f"acceptance evidence does not exist: {value}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", value], cwd=repo,
        capture_output=True, text=True,
    )
    if tracked.returncode != 0:
        raise ValueError(f"acceptance evidence is not tracked: {value}")
    return path



def validate(artifact_path: Path, repo: Path) -> None:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if artifact.get("acceptance_kind") != "cleaning-attestation-v1":
        raise ValueError("unsupported acceptance kind for cleaning-attestation validator")
    _validate_cleaning_acceptance(artifact, repo)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_cleaning_attestation_acceptance.py ARTIFACT REPO")
    try:
        validate(Path(sys.argv[1]), Path(sys.argv[2]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
