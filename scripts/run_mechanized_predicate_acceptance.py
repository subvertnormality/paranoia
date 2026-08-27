#!/usr/bin/env python3
"""Exercise evidence-bound mechanized replacement through public critique_branch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, orientation, review_census as rc

CLASS_ID = "predicate-acceptance"
LINEAGE_ID = "mechanized-predicate-acceptance-20260827"
STAKES = (
    "One trusted operator and OS; repository and provider bytes are untrusted data; "
    "no hostile local race, compromised OS, multi-tenancy, or corrupted state. A fresh "
    "mechanized replacement must match its cited repository occurrence before durable "
    "settlement. False closure is high impact; one validation retry is acceptable."
)
DIFF_INTENT = (
    "Exercise one unsafe distinct-value selection so the supplied closed mechanized "
    "class must be replaced with a predicate matching the cited occurrence."
)
FOCUS = (
    "Assess only the supplied class. Replace its stale predicate with the POSIX ERE "
    "'next\\(iter\\(distinct\\)\\)' over pathspec selection.py so the definition matches "
    "the cited violation line."
)


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
        default=str(ROOT / "docs" / "mechanized_predicate_acceptance_2026-08-27.json"),
    )
    args = parser.parse_args()

    fixture = Path(tempfile.mkdtemp(prefix="paranoia-predicate-fixture-"))
    state_root = Path(tempfile.mkdtemp(prefix="paranoia-predicate-state-"))
    log_root = Path(tempfile.mkdtemp(prefix="paranoia-predicate-log-"))
    (fixture / "selection.py").write_text(
        "def choose(distinct):\n    return None\n", encoding="utf-8",
    )
    _run("git", "init", "-q", "-b", "main", cwd=fixture)
    _run("git", "config", "user.name", "paranoia acceptance", cwd=fixture)
    _run("git", "config", "user.email", "paranoia@localhost", cwd=fixture)
    _run("git", "add", "selection.py", cwd=fixture)
    _run("git", "-c", "commit.gpgsign=false", "commit", "-qm", "base", cwd=fixture)
    base_id = _run("git", "rev-parse", "HEAD", cwd=fixture)
    (fixture / "selection.py").write_text(
        "def choose(distinct):\n    return next(iter(distinct))\n", encoding="utf-8",
    )
    _run("git", "add", "selection.py", cwd=fixture)
    _run(
        "git", "-c", "commit.gpgsign=false", "commit", "-qm", "unsafe selection",
        cwd=fixture,
    )
    head_id = _run("git", "rev-parse", "HEAD", cwd=fixture)

    tracked = cc.TrackedClass(
        class_id=CLASS_ID,
        invariant=(
            "Selecting a member from distinct values requires an explicit cardinality "
            "refusal before selection."
        ),
        severity=cc.MAJOR,
        first_round=1,
        status=cc.CLOSED,
        pattern="UNSAFE_DISTINCT_SELECTION",
        pathspec="selection.py",
    )
    seed = cc.Lineage(
        LINEAGE_ID, rounds=1, classes={CLASS_ID: tracked}, mode=cc.BRANCH_MODE,
    )
    class_block = cc.render_unclosed(seed)
    assert class_block is None
    packet = orientation.build_packet(
        fixture, base_id, head_id, diff_intent=DIFF_INTENT, focus=FOCUS,
        class_blocks=[],
    )
    structural_snapshot = rc.digest(f"{base_id}\0{head_id}\0{packet}")
    seed.review_state = rc.normalize_state(
        None, stakes=STAKES, snapshot=structural_snapshot,
    )
    seed.review_state.update(phase="final", last_round=1, debt=[])
    cc.save_lineage(state_root, seed)
    os.environ[cc.STATE_ROOT_ENV] = str(state_root)

    engine = engines.CodexEngine()
    engine.binary = args.codex
    provider_run = engine.run
    injected = False

    def fault_injected_run(*run_args, **run_kwargs):
        nonlocal injected
        review = provider_run(*run_args, **run_kwargs)
        evidence = [{
            "anchor":"repository/selection.py:2",
            "rationale":"The changed function selects a member without a cardinality refusal.",
        }]
        value = {
            "role":"final",
            "governing_findings":[{
                "id":"F1", "severity":"MAJOR",
                "summary":"Distinct-member selection lacks a cardinality refusal.",
                "evidence":evidence,
                "remedy":"Refuse unsupported cardinality before selecting a member.",
                "classification":{"kind":"existing_class", "class_id":CLASS_ID},
            }],
            "debt_outcomes":[],
            "class_outcomes":{
                CLASS_ID:{
                    "verdict":"violated", "evidence":evidence,
                    "basis":{"kind":"new_finding", "finding_id":"F1"},
                },
            },
            "class_actions":{
                CLASS_ID:{
                    "kind":"replace", "definition":{
                        "invariant":"Distinct selection requires cardinality refusal.",
                        "severity":"MAJOR",
                        "pattern":"arbitrary member selected from a distinct-value set",
                        "pathspec":"selection.py",
                    },
                },
            },
            "coverage":[
                {
                    "id":check, "status":"finding" if check == "transformations" else "covered",
                    "summary":"The acceptance fixture was inspected for this checklist item.",
                    "evidence":evidence,
                    "finding_ids":["F1"] if check == "transformations" else [],
                }
                for check in (
                    "artifact-complete", "repository-premises", "transformations",
                    "consumers", "failure-recovery", "tests-acceptance",
                    "docs-operations", "consistency", "proportionality",
                )
            ],
        }
        injected = True
        return replace(
            review,
            text=json.dumps(value, ensure_ascii=False, sort_keys=True),
        )

    # Keep the exact production engine type so critique_branch selects Protocol v2.
    # Only the initial extracted payload is fault-injected; resume is untouched.
    engine.run = fault_injected_run  # type: ignore[method-assign]
    started = time.monotonic()
    result = handlers.critique_branch({
        "repo_path":str(fixture), "base_ref":base_id, "head_ref":head_id,
        "lineage":LINEAGE_ID, "round":2, "converge":True,
        "class_closure":True, "model":"gpt-5.6-sol", "effort":"high",
        "web_search":False, "stakes":STAKES, "diff_intent":DIFF_INTENT,
        "focus":FOCUS,
    }, engine=engine, log_dir=log_root)
    elapsed = time.monotonic() - started
    if not injected:
        raise RuntimeError("acceptance fault injection did not run")

    audits = list(log_root.glob("*.json"))
    if len(audits) != 1:
        raise RuntimeError(f"expected one audit, got {len(audits)}")
    audit = json.loads(audits[0].read_text(encoding="utf-8"))
    attempts = audit.get("attempt_ledger", [])
    outcomes = [row.get("outcome") for row in attempts]
    if (
        len(attempts) != 2 or outcomes[0] != "validation-invalid"
        or outcomes[1] != "completed"
    ):
        raise RuntimeError(
            "positive acceptance requires one successful bounded validation retry, "
            f"got {attempts!r}"
        )
    rejected = audit.get("rejected_payloads", [])
    if (
        not rejected
        or "did not match any cited violation line" not in rejected[0].get(
            "validation_issue", "",
        )
    ):
        raise RuntimeError("audit omitted the evidence-mismatch rejection")
    settlement = audit.get("staged_settlement") or {}
    replacements = [
        row for row in settlement.get("class_records", [])
        if row.get("op") == "replace" and row.get("class_id") == CLASS_ID
    ]
    durable = cc.load_lineage(
        state_root, LINEAGE_ID, stamp="ACCEPTANCE", mode=cc.BRANCH_MODE,
    )
    successor_id = durable.classes[CLASS_ID].superseded_by
    successor = durable.classes.get(successor_id or "")
    if len(replacements) != 1:
        raise RuntimeError("corrected settlement omitted the mechanized replacement")
    replacement = replacements[0]
    if (
        replacement.get("pattern") != r"next\(iter\(distinct\)\)"
        or replacement.get("pathspec") != "selection.py"
    ):
        raise RuntimeError(f"replacement predicate is not exact: {replacement!r}")
    if successor is None or successor.status != cc.OPEN or len(successor.matches) != 1:
        raise RuntimeError("matching successor did not survive durable reload")
    route_outcome = "corrected-and-settled"
    if "CONVERGENCE: BLOCKED" not in result:
        raise RuntimeError("public result did not remain visibly blocked")

    source_revision = _run("git", "rev-parse", "HEAD", cwd=ROOT)
    sources = (
        "src/paranoia_local/class_closure.py",
        "src/paranoia_local/handlers.py",
        "src/paranoia_local/review_census.py",
        "scripts/run_mechanized_predicate_acceptance.py",
    )
    artifact = {
        "acceptance_kind":"evidence-bound-mechanized-predicate-public-branch",
        "version":1, "date":"2026-08-27", "source_revision":source_revision,
        "source_sha256":{
            path:hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in sources
        },
        "provider":{
            "engine":"codex", "executable":args.codex,
            "cli_version":_run(args.codex, "--version", cwd=ROOT),
            "model":"gpt-5.6-sol", "effort":"high", "web_search":False,
        },
        "fixture":{
            "base_id":base_id, "head_id":head_id, "lineage":LINEAGE_ID,
            "round":2, "class_id":CLASS_ID, "successor_id":successor_id,
            "packet_sha256":_digest(packet), "structural_snapshot":structural_snapshot,
            "initial_payload_fault_injection":(
                "After a real Codex call established the session and raw channels, the "
                "harness substituted one deterministic schema-valid extracted payload "
                "whose sole intended invalidity was a prose mechanized pattern. The "
                "provider raw channels and session identity were retained."
            ),
        },
        "elapsed_seconds":round(elapsed, 3),
        "route_outcome":route_outcome,
        "attempt_ledger":attempts,
        "rejected_payload":rejected[0],
        "settlement":settlement,
        "durable_successor":asdict(successor) if successor is not None else None,
        "durable_original":asdict(durable.classes[CLASS_ID]),
        "result_text":result,
        "result_sha256":_digest(result),
        "claims":{
            "proves":[
                "The public critique_branch handler rejected a disclosed fault-injected prose-like mechanized replacement against its cited line.",
                "The public handler used exactly one bounded retry on the same real Codex session.",
                (
                    "The corrected predicate settled and reloaded with its live occurrence."
                    if route_outcome == "corrected-and-settled" else
                    "The provider repeated a nonmatching predicate and substantive class state remained atomic after terminal rejection."
                ),
            ],
            "does_not_prove":[
                "The real provider authored the substituted invalid initial payload or pattern.",
                "Every future provider response will choose a mechanized class or repair it correctly.",
                "A line-level POSIX ERE completely represents every semantic recurrence.",
            ],
        },
    }
    Path(args.output).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} from {len(attempts)} provider attempts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
