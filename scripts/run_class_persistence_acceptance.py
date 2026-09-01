#!/usr/bin/env python3
"""Exercise class persistence and reopen diagnostics through critique_branch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, orientation, review_census as rc

CLASS_ID = "60c1a55e"
LINEAGE_ID = "class-persistence-acceptance-20260822"
STAKES = (
    "One trusted operator and OS; repository bytes are untrusted static data; no "
    "repository execution, hostile local race, or web access; one tiny committed diff "
    "and one closed review class; false clear or omitted lifecycle diagnostics can waste "
    "repeated review rounds; recoverable blocking is acceptable."
)
DIFF_INTENT = (
    "Exercise one recurrence: the new migration policy deliberately omits the rollback "
    "command and executable rollback test required by the supplied closed class."
)
FOCUS = "Assess the supplied active class exactly; do not invent unrelated work."


def _run(*args: str, cwd: Path) -> str:
    return subprocess.run(
        list(args), cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--codex", default=os.environ.get("PARANOIA_ACCEPTANCE_CODEX", "codex"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "docs" / "class_persistence_acceptance_2026-08-22.json"),
    )
    args = parser.parse_args()

    fixture = Path(tempfile.mkdtemp(prefix="paranoia-persistence-fixture-"))
    state_root = Path(tempfile.mkdtemp(prefix="paranoia-persistence-state-"))
    log_root = Path(tempfile.mkdtemp(prefix="paranoia-persistence-log-"))
    (fixture / "migration.md").write_text(
        "# Migration policy\n\nNo destructive migration is currently proposed.\n",
        encoding="utf-8",
    )
    _run("git", "init", "-q", cwd=fixture)
    _run("git", "config", "user.name", "paranoia acceptance", cwd=fixture)
    _run("git", "config", "user.email", "paranoia@localhost", cwd=fixture)
    _run("git", "add", "migration.md", cwd=fixture)
    _run("git", "-c", "commit.gpgsign=false", "commit", "-qm", "base", cwd=fixture)
    base_id = _run("git", "rev-parse", "HEAD", cwd=fixture)
    (fixture / "migration.md").write_text(
        "# Destructive migration\n\nDelete every stored account before deployment. "
        "The rollback command and rollback test are deliberately omitted.\n",
        encoding="utf-8",
    )
    _run("git", "add", "migration.md", cwd=fixture)
    _run("git", "-c", "commit.gpgsign=false", "commit", "-qm", "unsafe change", cwd=fixture)
    head_id = _run("git", "rev-parse", "HEAD", cwd=fixture)

    tracked = cc.TrackedClass(
        class_id=CLASS_ID,
        invariant=(
            "A destructive stored-data deletion change names an exact rollback command "
            "and an executable rollback test before deployment."
        ),
        severity=cc.MAJOR,
        first_round=1,
        status=cc.CLOSED,
        procedure="Inspect the changed policy for both the rollback command and rollback test.",
    )
    seed = cc.Lineage(
        LINEAGE_ID, rounds=2, classes={CLASS_ID: tracked}, mode=cc.BRANCH_MODE,
    )
    class_block = cc.render_unmechanized(seed)
    assert class_block is not None
    packet = orientation.build_packet(
        fixture, base_id, head_id, diff_intent=DIFF_INTENT, focus=FOCUS,
        class_blocks=[class_block],
    )
    structural_snapshot = rc.digest(f"{base_id}\0{head_id}\0{packet}")
    seed.review_state = rc.normalize_state(
        None, stakes=STAKES, snapshot=structural_snapshot,
    )
    seed.review_state.update(phase="final", final_engine="codex", last_round=2, debt=[])
    cc.save_lineage(state_root, seed)
    os.environ[cc.STATE_ROOT_ENV] = str(state_root)

    engine = engines.CodexEngine()
    engine.binary = args.codex
    started = time.monotonic()
    result = handlers.critique_branch({
        "repo_path": str(fixture), "base_ref": base_id, "head_ref": head_id,
        "lineage": LINEAGE_ID, "round": 3, "converge": True,
        "class_closure": True, "model": "gpt-5.6-sol", "effort": "high",
        "web_search": False, "stakes": STAKES, "diff_intent": DIFF_INTENT,
        "focus": FOCUS,
    }, engine=engine, log_dir=log_root)
    elapsed = time.monotonic() - started

    expected_fragments = (
        f"PERSISTENCE: {CLASS_ID} currently open; round-label span 3",
        "REOPEN-WAVE: 1 previously closed class(es) reopened this round",
        "rebut with session_ref=", "CONVERGENCE: BLOCKED",
    )
    missing = [value for value in expected_fragments if value not in result]
    if missing:
        raise RuntimeError(f"acceptance result omitted {missing!r}")
    audits = list(log_root.glob("*.json"))
    if len(audits) != 1:
        raise RuntimeError(f"expected one audit record, got {len(audits)}")
    audit = json.loads(audits[0].read_text(encoding="utf-8"))
    durable = cc.load_lineage(
        state_root, LINEAGE_ID, stamp="ACCEPTANCE", mode=cc.BRANCH_MODE,
    )
    if durable.classes[CLASS_ID].status != cc.OPEN:
        raise RuntimeError("reopened class was not durably persisted")
    settlement = audit.get("staged_settlement")
    if not isinstance(settlement, dict) or {
        "op": "reopen", "class_id": CLASS_ID,
    } not in settlement.get("class_records", []):
        raise RuntimeError("accepted settlement omitted the derived reopen record")
    attempts = audit.get("attempt_ledger", [])
    if (
        not 1 <= len(attempts) <= 2
        or attempts[-1].get("outcome") != "completed"
        or any(row.get("outcome") != "validation-invalid" for row in attempts[:-1])
    ):
        raise RuntimeError("acceptance did not complete through the provider route")

    source_revision = _run("git", "rev-parse", "HEAD", cwd=ROOT)
    artifact = {
        "acceptance_kind": "code-branch-class-persistence-reopen-lifecycle",
        "version": 2, "date": "2026-08-22", "source_revision": source_revision,
        "provider": {
            "engine": "codex", "executable": args.codex,
            "cli_version": _run(args.codex, "--version", cwd=ROOT),
            "model": "gpt-5.6-sol", "effort": "high", "web_search": False,
        },
        "fixture": {
            "base_id": base_id, "head_id": head_id,
            "packet_sha256": _digest(packet), "structural_snapshot": structural_snapshot,
            "lineage": LINEAGE_ID, "round": 3, "class_id": CLASS_ID,
            "final_engine": "codex",
            "class_first_round": 1, "class_before": cc.CLOSED,
            "class_after": durable.classes[CLASS_ID].status,
        },
        "elapsed_seconds": round(elapsed, 3), "attempt_ledger": attempts,
        "settlement": settlement, "result_text": result,
        "result_sha256": _digest(result),
        "claims": {
            "proves": [
                "The public critique_branch handler reopened the seeded closed class.",
                "The same response rendered persistence, reopen-wave, resumable-session, and blocked diagnostics.",
                "The reopened class survived a durable lineage reload.",
            ],
            "does_not_prove": [
                "Every future provider response will classify every recurrence correctly.",
                "Round-label span is a count of stored per-round class observations.",
            ],
        },
    }
    Path(args.output).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} from {len(attempts)} provider call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
