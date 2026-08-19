#!/usr/bin/env python3
"""Run one signed-in keyed correction through the production branch handler."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, review_census as rc


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "keyed_class_handler_acceptance_2026-08-19.json"
LINEAGE = "keyed-class-handler-acceptance-20260819"
STAKES = (
    "One trusted operator and OS; repository and provider bytes are untrusted static data; "
    "no repository execution or hostile local race; one bounded correction retry; false "
    "settlement or wrong class/evidence binding is high impact; recoverable blocking is acceptable."
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


class RecordingCodex(engines.CodexEngine):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict] = []

    def run(self, prompt, *args, response_schema=None, **kwargs):
        review = super().run(
            prompt, *args, response_schema=response_schema, **kwargs,
        )
        self.calls.append({
            "route":"fresh", "prompt":prompt, "schema":response_schema,
            "review":review,
        })
        return review

    def resume(self, session_ref, prompt, *args, response_schema=None, **kwargs):
        review = super().resume(
            session_ref, prompt, *args, response_schema=response_schema, **kwargs,
        )
        self.calls.append({
            "route":"resumed", "prompt":prompt, "schema":response_schema,
            "review":review,
        })
        return review


def main() -> int:
    state_root = Path(tempfile.mkdtemp(prefix="paranoia-keyed-handler-state-"))
    log_root = Path(tempfile.mkdtemp(prefix="paranoia-keyed-handler-log-"))
    os.environ[cc.STATE_ROOT_ENV] = str(state_root)
    before = rc.normalize_state({}, stakes=STAKES, snapshot="seed")
    before["phase"] = "correction"
    before["debt"] = [{
        "id":"D1", "finding_id":"historical-acceptance-gap", "status":"open",
        "severity":"MAJOR",
        "summary":"The keyed protocol lacks a retained production-handler lifecycle.",
        "evidence":["repository/README.md:1"],
        "remedy":"Run and retain the production keyed handler lifecycle.",
        "source_ids":[], "class_ids":["acceptance-class"],
        "first_round":0, "last_round":0,
    }]
    tracked = cc.TrackedClass(
        "acceptance-class",
        "A keyed staged protocol cutover has replayable production-handler acceptance binding "
        "the exact provider schema and response through anchor validation, canonical dry-run, "
        "atomic settlement, durable lineage, audit attempts, and rendered verdict.",
        "MAJOR", 0, cc.CLOSED, procedure="replay the complete retained handler artifact",
    )
    cc.save_lineage(state_root, cc.Lineage(
        LINEAGE, rounds=0, next_seq=1, classes={tracked.class_id:tracked},
        mode=cc.BRANCH_MODE, review_state=before,
    ))
    engine = RecordingCodex()
    args = {
        "repo_path":str(ROOT), "base_ref":"main",
        "head_ref":"codex/fix-consolidation-registers", "lineage":LINEAGE,
        "round":1, "converge":True, "class_closure":True, "isolate":True,
        "model":"gpt-5.6-sol", "effort":"high", "web_search":False,
        "stakes":STAKES,
        "project_summary":"Paranoia Local is a trusted-single-user local review MCP server.",
        "diff_intent":"Prove the keyed staged class-decision protocol through its production handler.",
        "focus":"Assess only the seeded acceptance class and preserve exact evidence bindings.",
    }
    started = time.monotonic()
    result = handlers.critique_branch(args, engine=engine, log_dir=log_root)
    elapsed = time.monotonic() - started
    if len(engine.calls) not in {1, 2}:
        raise RuntimeError(f"expected one call plus optional validation retry, got {len(engine.calls)}")
    if any(call["review"].error for call in engine.calls):
        raise RuntimeError("provider execution failed")
    audit_path = next(log_root.glob("*.json"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    lineage = cc.load_lineage(state_root, LINEAGE, stamp="ACCEPTANCE", mode=cc.BRANCH_MODE)
    head_id = subprocess.run(
        ["git", "rev-parse", "codex/fix-consolidation-registers^{commit}"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    base_id = subprocess.run(
        ["git", "rev-parse", "main^{commit}"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    calls = []
    for call in engine.calls:
        review = call["review"]
        schema_text = json.dumps(
            call["schema"], ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        calls.append({
            "route":call["route"], "session_ref":review.session_ref,
            "prompt_sha256":digest(call["prompt"]), "schema":call["schema"],
            "schema_sha256":digest(schema_text), "response_text":review.text,
            "response_sha256":digest(review.text), "raw_sha256":digest(review.raw),
            "usage":review.usage,
        })
    artifact = {
        "acceptance_kind":"keyed-staged-class-decision-handler-lifecycle",
        "version":1, "date":"2026-08-19", "provider":{
            "engine":"codex",
            "cli_version":subprocess.run(
                ["codex", "--version"], capture_output=True, text=True, check=True,
            ).stdout.strip(),
            "model":"gpt-5.6-sol", "effort":"high", "web_search":False,
        },
        "base_id":base_id, "head_id":head_id, "lineage_id":LINEAGE,
        "stakes":STAKES, "elapsed_seconds":round(elapsed, 3),
        "calls":calls, "before_state":before,
        "settlement":audit["staged_settlement"],
        "attempt_ledger":audit["attempt_ledger"],
        "after_lineage":{
            "rounds":lineage.rounds, "next_seq":lineage.next_seq,
            "classes":[vars(row) for row in lineage.classes.values()],
            "review_state":lineage.review_state,
        },
        "result_text":result, "result_sha256":digest(result),
    }
    OUTPUT.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT} from {len(calls)} production handler call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
