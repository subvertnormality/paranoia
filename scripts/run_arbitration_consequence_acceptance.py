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


def _git(*args: str) -> str:
    result = inert_git.invoke(ROOT, list(args))
    if result.returncode != 0:
        raise RuntimeError(
            "inert git failed: " + result.stderr.decode("utf-8", errors="replace")
        )
    return result.stdout.decode("utf-8", errors="surrogateescape").strip()


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

    diff_numstat = _git("diff", "--numstat", "main...HEAD").splitlines()
    changed = []
    for row in diff_numstat:
        additions, deletions, path = row.split("\t", 2)
        changed.append({
            "path": path,
            "additions": None if additions == "-" else int(additions),
            "deletions": None if deletions == "-" else int(deletions),
        })
    production = [row for row in changed if row["path"].startswith("src/")]
    largest_production = max(
        production,
        key=lambda row: (row["additions"] or 0) + (row["deletions"] or 0),
    )
    artifact = {
        "acceptance_kind": "arbitration-consequence-not-advocacy",
        "version": 1,
        "date": "2026-08-22",
        "source_revision": _git("rev-parse", "--verify", "HEAD^{commit}"),
        "input": arguments,
        "elapsed_seconds": round(elapsed, 3),
        "model_call_count": len(attempts),
        "branch_diff": {
            "base": _git("rev-parse", "main"),
            "changed_files": changed,
            "additions": sum(row["additions"] or 0 for row in changed),
            "deletions": sum(row["deletions"] or 0 for row in changed),
        },
        "production_diff": {
            "changed_modules": production,
            "additions": sum(row["additions"] or 0 for row in production),
            "deletions": sum(row["deletions"] or 0 for row in production),
            "largest_changed_module": largest_production,
        },
        "report_sha256": hashlib.sha256(
            report.encode("utf-8", "surrogatepass")
        ).hexdigest(),
        "report": report,
        "audit": audit,
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
