#!/usr/bin/env python3
"""Retain a real arbitration proving consequence text is not treated as advocacy."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import arbitrate_handler as ah, inert_git

OUTPUT = ROOT / "docs" / "arbitration_consequence_acceptance_2026-08-22.json"
SOURCE_PATHS = (
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/arbitration.py",
    "src/paranoia_local/engines.py",
    "src/paranoia_local/evidence.py",
    "src/paranoia_local/inert_git.py",
    "src/paranoia_local/prompts.py",
    "scripts/run_arbitration_consequence_acceptance.py",
    "scripts/validate_arbitration_consequence_acceptance.py",
    "scripts/validate_arbitration_fallback_acceptance.py",
)


def _git(*args: str) -> str:
    result = inert_git.invoke(ROOT, list(args))
    if result.returncode != 0:
        raise RuntimeError(
            "inert git failed: " + result.stderr.decode("utf-8", errors="replace")
        )
    return result.stdout.decode("utf-8", errors="surrogateescape").strip()


def _git_bytes(*args: str) -> bytes:
    result = inert_git.invoke(ROOT, list(args))
    if result.returncode != 0:
        raise RuntimeError(
            "inert git failed: " + result.stderr.decode("utf-8", errors="replace")
        )
    return result.stdout


def _audit_path(report: str) -> Path:
    match = re.search(r"^AUDIT: (.+)$", report, re.MULTILINE)
    if match is None:
        raise RuntimeError("arbitration report omitted its audit path")
    return Path(match.group(1))


def _attempts(audit: dict) -> list[dict]:
    rows = list(audit.get("phase_attempts", []))
    for round_row in audit.get("rounds", []):
        for decider in round_row.values():
            rows.extend(decider.get("attempts", []))
    return rows


def main() -> int:
    arguments = {
        "repo_path": str(ROOT),
        "decision": "Choose the repository's displayed project name for a diagnostic banner.",
        "options": [
            {"id": "opt-paranoia", "statement": 'Use "Paranoia".'},
            {"id": "opt-paranoia-review", "statement": 'Use "Paranoia Review".'},
        ],
        "stakes": (
            "Review effort spent on this naming decision is effort not spent on its "
            "implementation. A wrong choice causes rework, not corrupted state."
        ),
        "context": (
            "The banner must reproduce the project name shown by the repository README heading."
        ),
        "files": [{
            "path": "README.md",
            "reason": "contains the project heading used by the diagnostic banner",
        }],
        "clean": True,
        "research": False,
        "web_search": False,
        "order_seed": "issue-59-consequence-acceptance-20260822",
        "effort": "medium",
    }
    log_dir = Path(tempfile.mkdtemp(prefix="paranoia-consequence-acceptance-"))
    started = time.monotonic()
    report = ah.arbitrate(arguments, log_dir=log_dir)
    elapsed = time.monotonic() - started
    audit_path = _audit_path(report)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("outcome") != "CONVERGED":
        raise RuntimeError(f"acceptance did not converge: {audit.get('reason')}")
    if audit.get("cleaning") not in {"attested", "attested-after-retry", "original-attested"}:
        raise RuntimeError(f"unexpected cleaning route: {audit.get('cleaning')}")
    if "STAKES-ADVOCACY: NONE" not in audit.get("attestation", ""):
        raise RuntimeError("attester rejected the consequence-only stakes")
    if "CONTEXT-ADVOCACY: NONE" not in audit.get("attestation", ""):
        raise RuntimeError("attester rejected the governing factual context")
    attempts = _attempts(audit)
    roles = [row.get("role") or row.get("phase") for row in attempts]
    if "cleaner" not in roles or "attester" not in roles:
        raise RuntimeError("acceptance did not exercise cleaner and attester")
    if len(audit.get("rounds", [])) < 1:
        raise RuntimeError("acceptance did not exercise both deciders")

    source_revision = _git("rev-parse", "--verify", "HEAD^{commit}")
    snapshot_object = _git_bytes("cat-file", "commit", audit["snapshot"])
    artifact = {
        "acceptance_kind": "arbitration-consequence-not-advocacy",
        "version": 1,
        "date": "2026-08-22",
        "source_revision": source_revision,
        "source_sha256": {
            path: hashlib.sha256(_git_bytes("show", f"{source_revision}:{path}")).hexdigest()
            for path in SOURCE_PATHS
        },
        "snapshot_binding": {
            "commit_object": snapshot_object.decode("utf-8"),
            "sha256": hashlib.sha256(snapshot_object).hexdigest(),
            "source_commit": source_revision,
            "tree": _git("rev-parse", f"{source_revision}^{{tree}}"),
        },
        "input": arguments,
        "model_call_count": len(attempts),
        "report_sha256": hashlib.sha256(
            report.encode("utf-8", "surrogatepass")
        ).hexdigest(),
        "report": report,
        "audit": audit,
        "audit_sha256": hashlib.sha256(json.dumps(
            audit, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8", "surrogatepass")).hexdigest(),
        "claims": {
            "proves": [
                "The real cleaner and cross-vendor attester admitted consequence-only stakes and governing factual context.",
                "Both real deciders received the accepted packet and the arbitration converged.",
            ],
            "does_not_prove": [
                "Genuine directives, endorsements, rhetorical preference, or pre-emptive conclusions are accepted.",
                "Every future provider version will classify every framing correctly.",
            ],
        },
    }
    OUTPUT.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT} from {len(attempts)} model call(s) in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
