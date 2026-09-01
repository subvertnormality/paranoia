#!/usr/bin/env python3
"""Run one signed-in keyed correction through the production branch handler."""

from __future__ import annotations

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
from paranoia_local import engines, handlers, review_census as rc

OUTPUT = ROOT / "docs" / "keyed_class_handler_acceptance_2026-08-19.json"
SOURCE_PATHS = tuple(sorted(
    str(path.relative_to(ROOT))
    for path in (ROOT / "src" / "paranoia_local").glob("*.py")
)) + ("scripts/run_keyed_handler_acceptance.py", "tests/test_review_census.py")
LINEAGE = "keyed-class-handler-acceptance-20260819"
STAKES = (
    "One trusted operator and OS; repository and provider bytes are untrusted static data; "
    "no repository execution or hostile local race; one bounded correction retry; false "
    "settlement or wrong class/evidence binding is high impact; recoverable blocking is acceptable."
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    head_id = subprocess.run(
        ["git", "rev-parse", "HEAD^{commit}"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    base_id = subprocess.run(
        ["git", "rev-parse", "main^{commit}"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    state_root = Path(tempfile.mkdtemp(prefix="paranoia-keyed-handler-state-"))
    log_root = Path(tempfile.mkdtemp(prefix="paranoia-keyed-handler-log-"))
    os.environ[cc.STATE_ROOT_ENV] = str(state_root)
    before = rc.normalize_state({}, stakes=STAKES, snapshot="a" * 64)
    before["phase"] = "correction"
    before["last_round"] = 1
    before["debt"] = [{
        "id":"D0", "finding_id":"conceded-acceptance-gap", "status":"closed",
        "severity":"MAJOR", "summary":"A prior acceptance demand was withdrawn.",
        "evidence":["repository/docs/keyed_class_handler_acceptance_2026-08-19.json:1"],
        "remedy":"Do not repeat the withdrawn demand without new evidence.",
        "source_ids":[], "class_ids":["acceptance-class"],
        "first_round":1, "last_round":1,
        "concession":{
            "version":1, "reason":"The old pointer claim did not match the durable record.",
            "evidence":["repository/docs/keyed_class_handler_acceptance_2026-08-19.json:1"],
            "snapshot_digest":"a" * 64, "round":1,
        },
    }, {
        "id":"D1", "finding_id":"historical-acceptance-gap", "status":"open",
        "severity":"MAJOR",
        "summary":"The retained handler lifecycle predates the current keyed diagnostic contract.",
        "evidence":["repository/docs/keyed_class_handler_acceptance_2026-08-19.json:947-949"],
        "remedy":"Run and retain the current production handler with exact keyed pointers.",
        "source_ids":[], "class_ids":["acceptance-class"],
        "first_round":1, "last_round":1,
    }]
    tracked = cc.TrackedClass(
        "acceptance-class",
        "The retained keyed handler acceptance is bound to current head " + head_id +
        " and records _class_record_pointers as exactly "
        "['/class_outcomes/acceptance-class'] without excluding that field from replay.",
        "MAJOR", 1, cc.CLOSED, procedure="replay the complete retained handler artifact",
    )
    cc.save_lineage(state_root, cc.Lineage(
        LINEAGE, rounds=1, next_seq=1, classes={tracked.class_id:tracked},
        mode=cc.BRANCH_MODE, review_state=before,
    ))
    engine = engines.CodexEngine()
    recorded_calls: list[dict] = []
    original_run = engine.run
    original_resume = engine.resume

    def record_run(prompt, *args, response_schema=None, **kwargs):
        review = original_run(
            prompt, *args, response_schema=response_schema, **kwargs,
        )
        recorded_calls.append({
            "route":"fresh", "prompt":prompt, "schema":response_schema,
            "review":review,
        })
        return review

    def record_resume(session_ref, prompt, *args, response_schema=None, **kwargs):
        review = original_resume(
            session_ref, prompt, *args, response_schema=response_schema, **kwargs,
        )
        recorded_calls.append({
            "route":"resumed", "prompt":prompt, "schema":response_schema,
            "review":review,
        })
        return review

    engine.run = record_run  # type: ignore[method-assign]
    engine.resume = record_resume  # type: ignore[method-assign]
    args = {
        "repo_path":str(ROOT), "base_ref":"main",
        "head_ref":"HEAD", "lineage":LINEAGE,
        "round":2, "converge":True, "class_closure":True, "isolate":True,
        "model":"gpt-5.6-sol", "effort":"high", "web_search":False,
        "stakes":STAKES,
        "project_summary":"Paranoia Local is a trusted-single-user local review MCP server.",
        "diff_intent":"Prove the keyed staged class-decision protocol through its production handler.",
        "focus":(
            "Assess only the seeded acceptance class. A prior demand was durably conceded, "
            "but the current retained artifact now supplies distinct new evidence. Emit one "
            "fresh existing-class finding, close D1 as superseded by that aggregate finding, "
            "author the violated new_finding outcome, and explicitly challenge D0 with the "
            "new repository evidence."
        ),
    }
    started = time.monotonic()
    result = handlers.critique_branch(args, engine=engine, log_dir=log_root)
    elapsed = time.monotonic() - started
    if len(recorded_calls) not in {1, 2}:
        raise RuntimeError(
            f"expected one call plus optional validation retry, got {len(recorded_calls)}"
        )
    if any(call["review"].error for call in recorded_calls):
        raise RuntimeError("provider execution failed")
    audit_path = next(log_root.glob("*.json"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    lineage = cc.load_lineage(state_root, LINEAGE, stamp="ACCEPTANCE", mode=cc.BRANCH_MODE)
    settlement = audit.get("staged_settlement")
    if not isinstance(settlement, dict):
        raise RuntimeError("production staged settlement is absent")
    assessments = settlement.get("class_assessments", [])
    if (
        len(assessments) != 1
        or assessments[0].get("class_id") != "acceptance-class"
        or assessments[0].get("verdict") != "violated"
        or not assessments[0].get("evidence")
        or assessments[0].get("finding_id") in {None, "historical-acceptance-gap"}
    ):
        raise RuntimeError("unexpected staged class assessment")
    if settlement["class_records"] != [{
        "op":"reopen", "class_id":"acceptance-class",
    }]:
        raise RuntimeError("expected the violated closed class to derive reopen")
    current_class = lineage.classes["acceptance-class"]
    if current_class.status != cc.OPEN:
        raise RuntimeError("derived reopen did not persist")
    current_debt = next(row for row in lineage.review_state["debt"] if row["id"] == "D1")
    if current_debt["status"] != "closed" or current_debt["class_ids"] != ["acceptance-class"]:
        raise RuntimeError("durable debt binding changed unexpectedly")
    successor = [
        row for row in lineage.review_state["debt"]
        if row["id"] not in {"D0", "D1"} and row.get("status") == "open"
        and row.get("class_ids") == ["acceptance-class"]
    ]
    if len(successor) != 1:
        raise RuntimeError("fresh aggregate debt did not replace D1 exactly")
    if not settlement.get("concession_challenges") or (
        settlement["concession_challenges"][0].get("challenge") or {}
    ).get("debt_id") != "D0":
        raise RuntimeError("durable concession challenge is absent")
    if "STRUCTURAL-PHASE: correction" not in result or "CONVERGENCE: BLOCKED" not in result:
        raise RuntimeError("rendered staged trailer is not the expected blocked correction")
    artifact_calls = []
    for call in recorded_calls:
        review = call["review"]
        schema_text = json.dumps(
            call["schema"], ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        artifact_calls.append({
            "route":call["route"], "session_ref":review.session_ref,
            "prompt_sha256":digest(call["prompt"]), "schema":call["schema"],
            "schema_sha256":digest(schema_text), "response_text":review.text,
            "response_sha256":digest(review.text), "raw_sha256":digest(review.raw),
            "usage":review.usage,
        })
    artifact = {
        "acceptance_kind":"keyed-staged-class-decision-handler-lifecycle",
        "acceptance_scope":{
            "proves":(
                "At source_revision, the signed-in public critique_branch correction "
                "confronted a durable concession with new exact repository evidence, "
                "reopened the class, superseded the sibling debt, persisted successor "
                "debt, and retained its audit-bound provider response."
            ),
            "does_not_prove":(
                "A clean review result, a census-cache lifecycle, or that arbitrary "
                "future source/provider versions reproduce this historical exchange."
            ),
        },
        "version":1, "date":"2026-08-19", "provider":{
            "engine":"codex",
            "cli_version":subprocess.run(
                ["codex", "--version"], capture_output=True, text=True, check=True,
            ).stdout.strip(),
            "model":"gpt-5.6-sol", "effort":"high", "web_search":False,
        },
        "source_revision":head_id,
        "source_tree":subprocess.run(
            ["git", "rev-parse", f"{head_id}^{{tree}}"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip(),
        "source_sha256":{
            relative:bytes_digest((ROOT / relative).read_bytes())
            for relative in SOURCE_PATHS
        },
        "allowed_later_source_diffs":{},
        "reviewed_diff":{
            "base":base_id, "head":head_id,
            "sha256":bytes_digest(subprocess.run(
                ["git", "diff", "--binary", base_id, head_id], cwd=ROOT,
                capture_output=True, check=True,
            ).stdout),
            "numstat":subprocess.run(
                ["git", "diff", "--numstat", base_id, head_id], cwd=ROOT,
                capture_output=True, text=True, check=True,
            ).stdout.splitlines(),
        },
        "census_cache":None,
        "base_id":base_id, "head_id":head_id, "lineage_id":LINEAGE,
        "stakes":STAKES, "elapsed_seconds":round(elapsed, 3),
        "calls":artifact_calls, "before_state":before,
        "settlement":settlement,
        "attempt_ledger":audit["attempt_ledger"],
        "after_lineage":{
            "rounds":lineage.rounds, "next_seq":lineage.next_seq,
            "classes":[vars(row) for row in lineage.classes.values()],
            "review_state":lineage.review_state,
        },
        "result_text":result, "result_sha256":digest(result),
    }
    if (
        audit["attempt_ledger"][-1]["response_sha256"]
        != artifact_calls[-1]["response_sha256"]
    ):
        raise RuntimeError("audit attempt is not bound to the accepted response")
    OUTPUT.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT} from {len(artifact_calls)} production handler call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
