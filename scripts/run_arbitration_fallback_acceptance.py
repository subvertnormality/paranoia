#!/usr/bin/env python3
"""Generate the signed-in ordinary and deterministic fallback acceptance records."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paranoia_local import arbitrate_handler as ah
from paranoia_local import inert_git, prompts


COMMON = (
    "The reason string on each event records that the definition entered the canonical "
    "inventory through this card's builder-identity declarations and that this card changed "
    "none of its bytes. "
)
REPORTED_CANDIDATE = (
    "=== DECISION ===\n"
    "Choose the owning-card value for the 480 declarations entering the canonical inventory.\n\n"
    "=== OPTIONS ===\n"
    "opt-causing-card: The 480 declarations record the card that caused their inventory entry.\n"
    "opt-holding-owner: The 480 declarations record the delivery-level holding owner.\n\n"
    "=== CONTEXT ===\nNone.\n\n"
    "=== HINTS ===\n"
    "- docs/arbitrate_original_neutrality_fallback_plan.md: records the reported "
    "duplicated-preamble fidelity failure shape\n"
)


def _arguments(repo: Path, seed: str, *, asymmetry: bool = False) -> dict[str, Any]:
    if asymmetry:
        decision = (
            "Choose how the cleaner should handle substantively asymmetric option "
            "statements; the clean answer is self-evident."
        )
        options = [
            {
                "id": "opt-equalize",
                "statement": "Rewrite both options to comparable length and detail.",
            },
            {
                "id": "opt-preserve",
                "statement": (
                    "Preserve every option's own facts, constraints, caveats, qualifications, "
                    "scope, and consequences even when the resulting statements differ "
                    "substantially in length. Normalize only presentation features such as "
                    "tense, voice, labels, and rhetorical padding when meaning is unchanged; "
                    "never copy content between options merely to make their detail or length "
                    "match."
                ),
            },
        ]
        context = (
            "A prior delivery decision governs audit-record retention. This decision concerns "
            "only how cleaner-owned option presentation handles substantive asymmetry."
        )
        files = []
    else:
        decision = (
            "Choose the owning-card value for the 480 declarations entering the "
            "canonical inventory."
        )
        options = [
            {
                "id": "opt-causing-card",
                "statement": COMMON + (
                    "The 480 declarations record the card that caused their inventory entry. "
                    "The card's own 62 authored definitions record the same value, so one owner "
                    "value appears across the 542 definitions this change brings into or adds "
                    "to the governed surface."
                ),
            },
            {
                "id": "opt-holding-owner",
                "statement": COMMON + (
                    "The 480 declarations record the delivery-level holding owner. The card's "
                    "own 62 authored definitions retain the card that caused their entry, so two "
                    "owner values appear across the 542 definitions this change brings into or "
                    "adds to the governed surface."
                ),
            },
        ]
        context = ""
        files = [{
            "path":"docs/arbitrate_original_neutrality_fallback_plan.md",
            "reason":"records the reported duplicated-preamble fidelity failure shape",
        }]
    return {
        "repo_path": str(repo),
        "decision": decision,
        "options": options,
        "stakes": (
            "A trusted single operator on a trusted OS runs a local CLI over two to four "
            "options. Repository and provider text are data inputs. Two independent deciders "
            "receive one pinned snapshot, and a failed arbitration can be rerun by the operator. "
            "Multi-tenancy, hostile local path races, and a compromised provider or OS are "
            "outside the supported environment."
        ),
        "context": context,
        "files": files,
        "clean": True,
        "research": False,
        "web_search": False,
        "order_seed": seed,
        "effort": "medium",
    }


def _fallback_agent(**kwargs: Any) -> str:
    lifecycle = kwargs.pop("_attempt_lifecycle", None)
    if kwargs["instructions"] == prompts.CLEANER_INSTRUCTIONS:
        if lifecycle is not None:
            lifecycle["execution"] = ah._execution_identity(
                kwargs["engine_name"], kwargs["model"], route="deterministic-cleaner",
            )
        return REPORTED_CANDIDATE
    return ah._run_agent(**kwargs, _attempt_lifecycle=lifecycle)


_fallback_agent._paranoia_accepts_lifecycle = True  # type: ignore[attr-defined]


def _audit_path(report: str) -> Path:
    match = re.search(r"^AUDIT: (.+)$", report, re.MULTILINE)
    if match is None:
        raise RuntimeError("arbitration report did not contain an AUDIT path")
    return Path(match.group(1))


def _require_route(audit: dict[str, Any], *, fallback: bool) -> None:
    expected_cleaning = "original-attested" if fallback else "attested"
    if audit.get("outcome") != "CONVERGED" or audit.get("cleaning") != expected_cleaning:
        raise RuntimeError(
            "acceptance run did not reach its required route: "
            f"expected CONVERGED/{expected_cleaning}, got "
            f"{audit.get('outcome')}/{audit.get('cleaning')}"
        )


def _run(repo: Path, log_dir: Path, *, fallback: bool) -> tuple[Path, dict[str, Any]]:
    started_utc = datetime.now(timezone.utc)
    started = time.monotonic()
    report = ah.arbitrate(
        _arguments(
            repo,
            "original-neutrality-fallback-v2-20260821"
            if fallback else "ordinary-open-asymmetry-20260821",
            asymmetry=not fallback,
        ),
        log_dir=log_dir,
        run_agent=_fallback_agent if fallback else None,
    )
    elapsed = time.monotonic() - started
    audit_path = _audit_path(report)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    _require_route(audit, fallback=fallback)
    timing = {
        "started_utc": started_utc.isoformat().replace("+00:00", "Z"),
        "finished_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "monotonic_elapsed_seconds": round(elapsed, 6),
        "exit_status": 0,
        "audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
    }
    print(report)
    return audit_path, timing


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_arbitration_fallback_acceptance.py REPO")
    repo = Path(sys.argv[1]).resolve()
    output = repo / "docs" / "arbitration_fallback_evidence"
    output.mkdir(parents=True, exist_ok=True)
    log_dir = Path("/tmp/paranoia-arbitrate-fallback-acceptance-logs")
    ordinary_audit, ordinary_timing = _run(repo, log_dir, fallback=False)
    fallback_audit, fallback_timing = _run(repo, log_dir, fallback=True)
    ordinary = json.loads(ordinary_audit.read_text(encoding="utf-8"))
    fallback = json.loads(fallback_audit.read_text(encoding="utf-8"))
    if ordinary["snapshot"] != fallback["snapshot"]:
        raise RuntimeError("ordinary and fallback runs did not use the same source snapshot")
    snapshot_object = inert_git.run(repo, ["cat-file", "commit", ordinary["snapshot"]])
    (output / "ordinary-audit.json").write_bytes(ordinary_audit.read_bytes())
    (output / "ordinary-timing.json").write_text(
        json.dumps(ordinary_timing, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (output / "original-attested-audit.json").write_bytes(fallback_audit.read_bytes())
    (output / "timing.json").write_text(
        json.dumps(fallback_timing, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (output / "snapshot-commit.txt").write_bytes(snapshot_object)


if __name__ == "__main__":
    main()
