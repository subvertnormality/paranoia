#!/usr/bin/env python3
"""Run one signed-in multi-occurrence correction through critique_branch."""

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

OUTPUT = ROOT / "docs" / "class_occurrence_batch_acceptance_2026-08-30.json"
LINEAGE = "class-occurrence-batch-acceptance-20260830"
CLASS_ID = "duplicate-mode-contract"
SOURCES = (
    "src/paranoia_local/class_closure.py",
    "src/paranoia_local/handlers.py",
    "src/paranoia_local/prompts.py",
    "src/paranoia_local/review_census.py",
    "src/paranoia_local/staged_protocol.py",
    "scripts/run_class_occurrence_batch_acceptance.py",
    "tests/test_class_occurrence_batch_acceptance.py",
    "tests/test_review_census.py",
)
STAKES = (
    "One trusted operator and OS; repository, diff, and provider output are untrusted "
    "data only; no repository execution, hostile local race, compromised OS, or "
    "multitenancy; two text files and one active class; false clearance or incomplete "
    "class evidence is high impact; recoverable blocking is acceptable."
)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8", "surrogatepass"))


def _git(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _fixture_repo(parent: Path) -> Path:
    repo = parent / "repository"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME":"acceptance", "GIT_AUTHOR_EMAIL":"acceptance@example.test",
        "GIT_COMMITTER_NAME":"acceptance", "GIT_COMMITTER_EMAIL":"acceptance@example.test",
        "GIT_CONFIG_GLOBAL":"/dev/null", "GIT_CONFIG_SYSTEM":"/dev/null",
    }
    _git("init", "-q", "-b", "main", cwd=repo, env=env)
    for name in ("app.conf", "worker.conf"):
        (repo / name).write_text("MODE = safe\n", encoding="utf-8")
    _git("add", "-A", cwd=repo, env=env)
    _git("commit", "-q", "-m", "safe baseline", cwd=repo, env=env)
    _git("checkout", "-q", "-b", "feature", cwd=repo, env=env)
    for name in ("app.conf", "worker.conf"):
        (repo / name).write_text(
            "MODE = unsafe  # independently violates the shared safe-mode contract\n",
            encoding="utf-8",
        )
    _git("add", "-A", cwd=repo, env=env)
    _git("commit", "-q", "-m", "introduce both occurrences", cwd=repo, env=env)
    return repo


def validate_artifact(
    artifact: dict, root: Path = ROOT, *, require_committed: bool = True,
) -> None:
    expected = {
        "acceptance_kind", "version", "date", "source_revision", "source_sha256",
        "provider", "fixture", "lineage_id", "stakes", "elapsed_seconds", "calls",
        "attempt_ledger", "settlement", "after_lineage", "result_text", "result_sha256",
    }
    if set(artifact) != expected:
        raise ValueError("acceptance fields are not closed and exact")
    if artifact["acceptance_kind"] != "class-occurrence-batch-public-branch-handler-v1":
        raise ValueError("wrong acceptance kind")
    if require_committed:
        committed = json.loads(_git("show", f"HEAD:{OUTPUT.relative_to(root)}", cwd=root))
        if committed != artifact:
            raise ValueError("acceptance differs from its committed Git envelope")
    revision = artifact["source_revision"]
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("source revision is not a full commit")
    if set(artifact["source_sha256"]) != set(SOURCES):
        raise ValueError("source inventory is not exact")
    for relative, expected_sha in artifact["source_sha256"].items():
        historical = subprocess.run(
            ["git", "show", f"{revision}:{relative}"], cwd=root, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        if _sha_bytes(historical) != expected_sha:
            raise ValueError(f"historical source mismatch for {relative}")
        if (root / relative).read_bytes() != historical:
            raise ValueError(f"current source differs from acceptance for {relative}")
    provider = artifact["provider"]
    if provider.get("engine") != "codex" or provider.get("model") != "gpt-5.6-sol":
        raise ValueError("acceptance did not use the required Codex route")
    calls = artifact["calls"]
    if not isinstance(calls, list) or len(calls) not in {1, 2}:
        raise ValueError("acceptance must retain one call and at most one validation retry")
    if any(not row.get("session_ref") for row in calls):
        raise ValueError("acceptance lacks signed-in provider sessions")
    for row in calls:
        if _sha_text(row["response_text"]) != row["response_sha256"]:
            raise ValueError("provider response digest mismatch")
    settlement = artifact["settlement"]
    findings = settlement.get("findings") or []
    if len(findings) != 1:
        raise ValueError("acceptance did not settle exactly one governing finding")
    anchors = findings[0].get("evidence")
    if set(anchors or ()) != {"repository/app.conf:1", "repository/worker.conf:1"}:
        raise ValueError("governing finding did not aggregate both occurrences")
    remedy = findings[0].get("remedy", "").lower()
    if not ("both" in remedy or "all" in remedy):
        raise ValueError("governing remedy is not explicitly all-site")
    assessments = settlement.get("class_assessments") or []
    if len(assessments) != 1 or assessments[0].get("class_id") != CLASS_ID:
        raise ValueError("class outcome is not singular and correctly bound")
    after = artifact["after_lineage"]
    debts = after["review_state"]["debt"]
    historic = next(row for row in debts if row["id"] == "D1")
    fresh = next(row for row in debts if row["id"] != "D1")
    if historic["status"] != "closed" or fresh["status"] != "open":
        raise ValueError("durable debt lifecycle is wrong")
    if set(fresh["evidence"]) != set(anchors) or fresh["class_ids"] != [CLASS_ID]:
        raise ValueError("durable aggregate evidence or class binding is wrong")
    if after["review_state"]["phase"] != "correction":
        raise ValueError("violated class did not remain in correction")
    if _sha_text(artifact["result_text"]) != artifact["result_sha256"]:
        raise ValueError("result digest mismatch")


def main() -> int:
    revision = _git("rev-parse", "HEAD^{commit}")
    dirty = _git("status", "--short", "--", *SOURCES)
    if dirty:
        raise RuntimeError("commit all acceptance-bound sources before generation")
    with tempfile.TemporaryDirectory(prefix="paranoia-occurrence-batch-") as raw:
        temp = Path(raw)
        repo = _fixture_repo(temp)
        state_root = temp / "state"
        log_root = temp / "logs"
        os.environ[cc.STATE_ROOT_ENV] = str(state_root)
        state = rc.normalize_state(None, stakes=STAKES, snapshot="seed")
        state.update(phase="correction", last_round=1, debt=[{
            "id":"D1", "finding_id":"known-app-occurrence", "status":"open",
            "severity":"MAJOR", "summary":"app.conf violates the safe-mode contract",
            "evidence":["repository/app.conf:1"],
            "remedy":"repair every occurrence of the shared contract", "source_ids":[],
            "class_ids":[CLASS_ID], "first_round":1, "last_round":1,
        }])
        tracked = cc.TrackedClass(
            CLASS_ID, "Every active configuration sets MODE = safe.", "MAJOR", 1,
            cc.OPEN, procedure="inspect every active configuration file",
        )
        cc.save_lineage(state_root, cc.Lineage(
            LINEAGE, rounds=1, next_seq=2, classes={CLASS_ID:tracked},
            mode=cc.BRANCH_MODE, review_state=state,
        ))
        engine = engines.CodexEngine()
        calls: list[dict] = []
        original_run, original_resume = engine.run, engine.resume

        def record_run(prompt, *args, response_schema=None, **kwargs):
            review = original_run(prompt, *args, response_schema=response_schema, **kwargs)
            calls.append({"route":"fresh", "prompt_sha256":_sha_text(prompt), "review":review})
            return review

        def record_resume(session_ref, prompt, *args, response_schema=None, **kwargs):
            review = original_resume(
                session_ref, prompt, *args, response_schema=response_schema, **kwargs,
            )
            calls.append({"route":"resumed", "prompt_sha256":_sha_text(prompt), "review":review})
            return review

        engine.run = record_run  # type: ignore[method-assign]
        engine.resume = record_resume  # type: ignore[method-assign]
        started = time.monotonic()
        result = handlers.critique_branch({
            "repo_path":str(repo), "base_ref":"main", "head_ref":"feature",
            "lineage":LINEAGE, "round":2, "model":"gpt-5.6-sol",
            "effort":"high", "web_search":False, "stakes":STAKES,
            "project_summary":"The fixture has two active configuration files.",
            "diff_intent":"Keep every active configuration in safe mode.",
            "focus":(
                "Assess the supplied active class against the complete diff. app.conf and "
                "worker.conf are independent active sites; if violated, aggregate both exact "
                "anchors into its one governing finding and make the remedy cover both sites."
            ),
        }, engine=engine, log_dir=log_root)
        elapsed = time.monotonic() - started
        audit = json.loads(next(log_root.glob("*.json")).read_text(encoding="utf-8"))
        lineage = cc.load_lineage(state_root, LINEAGE, stamp="acceptance", mode=cc.BRANCH_MODE)
        artifact_calls = [{
            "route":row["route"], "prompt_sha256":row["prompt_sha256"],
            "session_ref":row["review"].session_ref,
            "response_text":row["review"].text,
            "response_sha256":_sha_text(row["review"].text),
        } for row in calls]
        artifact = {
            "acceptance_kind":"class-occurrence-batch-public-branch-handler-v1",
            "version":1, "date":"2026-08-30", "source_revision":revision,
            "source_sha256":{
                relative:_sha_bytes((ROOT / relative).read_bytes()) for relative in SOURCES
            },
            "provider":{
                "engine":"codex", "model":"gpt-5.6-sol", "effort":"high",
                "web_search":False,
                "cli_version":subprocess.run(
                    ["codex", "--version"], check=True, capture_output=True, text=True,
                ).stdout.strip(),
            },
            "fixture":{
                "base_id":_git("rev-parse", "main^{commit}", cwd=repo),
                "head_id":_git("rev-parse", "feature^{commit}", cwd=repo),
                "expected_anchors":["repository/app.conf:1", "repository/worker.conf:1"],
            },
            "lineage_id":LINEAGE, "stakes":STAKES,
            "elapsed_seconds":round(elapsed, 3), "calls":artifact_calls,
            "attempt_ledger":audit["attempt_ledger"],
            "settlement":audit["staged_settlement"],
            "after_lineage":{
                "rounds":lineage.rounds,
                "classes":[vars(row) for row in lineage.classes.values()],
                "review_state":lineage.review_state,
            },
            "result_text":result, "result_sha256":_sha_text(result),
        }
        validate_artifact(artifact, require_committed=False)
        OUTPUT.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"wrote {OUTPUT} from {len(calls)} signed-in provider call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
