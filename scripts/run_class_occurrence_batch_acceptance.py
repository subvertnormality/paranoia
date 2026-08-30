#!/usr/bin/env python3
"""Run one signed-in multi-occurrence correction through critique_branch."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, review_census as rc, staged_protocol as sp
from paranoia_local.engines import Review

OUTPUT = ROOT / "docs" / "class_occurrence_batch_acceptance_2026-08-30.json"
LINEAGE = "class-occurrence-batch-acceptance-20260830"
CLASS_ID = "duplicate-mode-contract"
PRODUCTION_SOURCES = tuple(sorted(
    str(path.relative_to(ROOT))
    for path in (ROOT / "src" / "paranoia_local").glob("*.py")
))
SOURCES = PRODUCTION_SOURCES + (
    "scripts/run_class_occurrence_batch_acceptance.py",
    "tests/test_class_occurrence_batch_acceptance.py",
    "tests/test_review_census.py",
)
STAKES = (
    "One trusted operator and OS; repository, diff, and provider output are untrusted "
    "data only; no repository execution, hostile local race, compromised OS, or "
    "multitenancy; one small repository and one active class; false clearance or incomplete "
    "class evidence is high impact; recoverable blocking is acceptable."
)
BASE_FILES = {"app.conf":"MODE = safe\n", "worker.conf":"MODE = safe\n"}
HEAD_FILES = {
    name:"MODE = unsafe\n"
    for name in BASE_FILES
}
ATTEMPT_FIELDS = {
    "sequence", "role", "engine", "session_ref", "outcome", "response_sha256",
    "returncode", "requested_timeout_sec",
}
FORBIDDEN_ANSWER_KEYS = (
    "independent active sites", "aggregate both exact anchors",
    "two active configuration files", "independently violates",
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


def _fixture_repo(
    parent: Path, *, base_files: dict[str, str] = BASE_FILES,
    head_files: dict[str, str] = HEAD_FILES,
) -> Path:
    repo = parent / "repository"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME":"acceptance", "GIT_AUTHOR_EMAIL":"acceptance@example.test",
        "GIT_COMMITTER_NAME":"acceptance", "GIT_COMMITTER_EMAIL":"acceptance@example.test",
        "GIT_CONFIG_GLOBAL":"/dev/null", "GIT_CONFIG_SYSTEM":"/dev/null",
        "GIT_AUTHOR_DATE":"2026-08-30T12:00:00+00:00",
        "GIT_COMMITTER_DATE":"2026-08-30T12:00:00+00:00",
    }
    _git("init", "-q", "-b", "main", cwd=repo, env=env)
    for name, text in base_files.items():
        (repo / name).write_text(text, encoding="utf-8")
    _git("add", "-A", cwd=repo, env=env)
    _git("commit", "-q", "-m", "safe baseline", cwd=repo, env=env)
    _git("checkout", "-q", "-b", "feature", cwd=repo, env=env)
    for name, text in head_files.items():
        (repo / name).write_text(text, encoding="utf-8")
    _git("add", "-A", cwd=repo, env=env)
    _git("commit", "-q", "-m", "introduce both occurrences", cwd=repo, env=env)
    return repo


def _before_lineage_record() -> dict:
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
    return json.loads(json.dumps({
        "rounds":1, "next_seq":2, "classes":[vars(tracked)], "review_state":state,
    }))


def validate_artifact(
    artifact: dict, root: Path = ROOT, *, require_committed: bool = True,
) -> None:
    expected = {
        "acceptance_kind", "version", "date", "source_revision", "source_sha256",
        "allowed_later_source_diffs",
        "provider", "fixture", "lineage_id", "stakes", "calls",
        "attempt_ledger", "settlement", "before_lineage", "after_lineage",
        "rendered_trailer", "result_text", "result_sha256",
    }
    if set(artifact) != expected:
        raise ValueError("acceptance fields are not closed and exact")
    if artifact["acceptance_kind"] != "class-occurrence-batch-public-branch-handler-v1":
        raise ValueError("wrong acceptance kind")
    if (
        artifact["version"] != 1 or artifact["date"] != "2026-08-30"
        or artifact["lineage_id"] != LINEAGE or artifact["stakes"] != STAKES
    ):
        raise ValueError("acceptance identity metadata is not exact")
    if require_committed:
        committed = json.loads(_git("show", f"HEAD:{OUTPUT.relative_to(root)}", cwd=root))
        if committed != artifact:
            raise ValueError("acceptance differs from its committed Git envelope")
    revision = artifact["source_revision"]
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("source revision is not a full commit")
    try:
        resolved_revision = _git("rev-parse", f"{revision}^{{commit}}", cwd=root)
    except subprocess.CalledProcessError as exc:
        raise ValueError("source revision does not resolve to a commit") from exc
    if resolved_revision != revision:
        raise ValueError("source revision is not canonical")
    if require_committed:
        artifact_commit = _git(
            "log", "-1", "--format=%H", "--", str(OUTPUT.relative_to(root)), cwd=root,
        )
        if _git("rev-parse", f"{artifact_commit}^{{commit}}", cwd=root) != artifact_commit:
            raise ValueError("artifact commit identity is invalid")
        if _git("rev-parse", f"{artifact_commit}^", cwd=root) != revision:
            raise ValueError("source revision is not the artifact generation boundary")
    if set(artifact["source_sha256"]) != set(SOURCES):
        raise ValueError("source inventory is not exact")
    allowed = artifact["allowed_later_source_diffs"]
    changed: set[str] = set()
    for relative, expected_sha in artifact["source_sha256"].items():
        historical = subprocess.run(
            ["git", "show", f"{revision}:{relative}"], cwd=root, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        if _sha_bytes(historical) != expected_sha:
            raise ValueError(f"historical source mismatch for {relative}")
        if (root / relative).read_bytes() != historical:
            changed.add(relative)
            row = allowed.get(relative)
            if not isinstance(row, dict) or set(row) != {"sha256", "scope"}:
                raise ValueError(f"later-source allowance is absent for {relative}")
            diff = subprocess.run(
                ["git", "diff", "--no-ext-diff", revision, "--", relative],
                cwd=root, check=True, stdout=subprocess.PIPE,
            ).stdout
            if _sha_bytes(diff) != row["sha256"]:
                raise ValueError(f"later-source allowance mismatch for {relative}")
    if changed != set(allowed):
        raise ValueError("later-source allowance inventory is not exact")
    provider = artifact["provider"]
    if set(provider) != {
        "engine", "model", "effort", "web_search", "minimum_cli_version",
    }:
        raise ValueError("provider record is not closed and exact")
    minimum_cli_version = ".".join(str(part) for part in engines.MIN_CODEX_VERSION)
    if provider != {
        "engine":"codex", "model":"gpt-5.6-sol", "effort":"high",
        "web_search":False, "minimum_cli_version":minimum_cli_version,
    }:
        raise ValueError("acceptance did not use the required Codex route")
    calls = artifact["calls"]
    if not isinstance(calls, list) or len(calls) not in {1, 2}:
        raise ValueError("acceptance must retain one call and at most one validation retry")
    ledger = artifact["attempt_ledger"]
    if not isinstance(ledger, list) or len(ledger) != len(calls):
        raise ValueError("attempt ledger does not match provider call count")
    for index, (row, attempt) in enumerate(zip(calls, ledger), 1):
        if set(row) != {
            "route", "prompt_text", "prompt_sha256", "session_ref",
            "response_text", "response_sha256",
        } or not row["session_ref"]:
            raise ValueError("acceptance call schema or signed-in session is invalid")
        if _sha_text(row["prompt_text"]) != row["prompt_sha256"]:
            raise ValueError("provider prompt digest mismatch")
        if any(token in row["prompt_text"] for token in FORBIDDEN_ANSWER_KEYS):
            raise ValueError("provider-visible prompt contains a fixture answer key")
        if _sha_text(row["response_text"]) != row["response_sha256"]:
            raise ValueError("provider response digest mismatch")
        expected_role = "correction" if index == 1 else "correction-validation-retry"
        expected_outcome = "completed" if index == len(calls) else "validation-invalid"
        if set(attempt) != ATTEMPT_FIELDS:
            raise ValueError("attempt record is not closed and exact")
        if (
            attempt.get("sequence") != index or attempt.get("role") != expected_role
            or attempt.get("engine") != provider["engine"]
            or attempt.get("session_ref") != row["session_ref"]
            or attempt.get("response_sha256") != row["response_sha256"]
            or attempt.get("outcome") != expected_outcome
            or attempt.get("returncode") != 0
            or attempt.get("requested_timeout_sec") != (2400 if index == 1 else 600)
        ):
            raise ValueError("provider call and attempt ledger are not route-bound")
    if calls[0]["route"] != "fresh" or (len(calls) == 2 and (
        calls[1]["route"] != "resumed" or calls[0]["session_ref"] != calls[1]["session_ref"]
    )):
        raise ValueError("validation retry did not preserve one provider session")
    before = artifact["before_lineage"]
    if before != _before_lineage_record():
        raise ValueError("before-lineage envelope is not closed and exact")
    active = before["classes"]
    durable_debt = before["review_state"]["debt"]
    decoded = sp.decode_decision(
        calls[-1]["response_text"], mode=cc.BRANCH_MODE, role="correction",
        active_classes=active, durable_debt=durable_debt,
    )
    replayed_settlement = sp.materialize_decision_value(
        decoded, mode=cc.BRANCH_MODE, role="correction",
        active_classes=active, durable_debt=durable_debt,
    )
    if replayed_settlement != artifact["settlement"]:
        raise ValueError("retained provider response does not materialize to settlement")
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
    if set(assessments[0].get("evidence") or ()) != set(anchors):
        raise ValueError("class outcome and governing finding occurrences diverge")
    after = artifact["after_lineage"]
    if set(after) != {"rounds", "next_seq", "classes", "review_state"}:
        raise ValueError("after-lineage envelope is not closed and exact")
    debts = after["review_state"]["debt"]
    if not isinstance(debts, list) or len(debts) != 2 or any(
        not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in debts
    ):
        raise ValueError("durable debt envelope is not closed and exact")
    by_debt_id = {row["id"]:row for row in debts}
    if set(by_debt_id) != {"D1", "D2"}:
        raise ValueError("durable debt identities are not exact")
    historic = by_debt_id["D1"]
    fresh = by_debt_id["D2"]
    if historic["status"] != "closed" or fresh["status"] != "open":
        raise ValueError("durable debt lifecycle is wrong")
    if set(fresh["evidence"]) != set(anchors) or fresh["class_ids"] != [CLASS_ID]:
        raise ValueError("durable aggregate evidence or class binding is wrong")
    if after["review_state"]["phase"] != "correction":
        raise ValueError("violated class did not remain in correction")
    if _sha_text(artifact["result_text"]) != artifact["result_sha256"]:
        raise ValueError("result digest mismatch")
    if not isinstance(artifact["rendered_trailer"], str) or not artifact["rendered_trailer"]:
        raise ValueError("rendered trailer is absent")
    fixture = artifact["fixture"]
    if set(fixture) != {"base_id", "head_id", "base_files", "head_files", "expected_anchors"}:
        raise ValueError("fixture record is not closed and exact")
    if (
        fixture["base_files"] != BASE_FILES or fixture["head_files"] != HEAD_FILES
        or fixture["expected_anchors"] != [
            "repository/app.conf:1", "repository/worker.conf:1",
        ]
        or any(
            not isinstance(fixture[key], str) or len(fixture[key]) != 40
            for key in ("base_id", "head_id")
        )
    ):
        raise ValueError("fixture inputs or anchors are not exact")
    with tempfile.TemporaryDirectory(prefix="paranoia-occurrence-replay-") as raw:
        temp = Path(raw)
        repo = _fixture_repo(
            temp, base_files=fixture["base_files"], head_files=fixture["head_files"],
        )
        if (
            _git("rev-parse", "main^{commit}", cwd=repo) != fixture["base_id"]
            or _git("rev-parse", "feature^{commit}", cwd=repo) != fixture["head_id"]
        ):
            raise ValueError("retained fixture does not reconstruct recorded Git identities")
        for anchor in fixture["expected_anchors"]:
            path, raw_line = anchor.removeprefix("repository/").rsplit(":", 1)
            lines = (repo / path).read_text(encoding="utf-8").splitlines()
            if not raw_line.isdigit() or int(raw_line) > len(lines):
                raise ValueError("retained fixture does not resolve an occurrence anchor")
        state_root = temp / "state"
        prior_root = os.environ.get(cc.STATE_ROOT_ENV)
        os.environ[cc.STATE_ROOT_ENV] = str(state_root)
        before_classes = [cc.TrackedClass(**row) for row in before["classes"]]
        cc.save_lineage(state_root, cc.Lineage(
            artifact["lineage_id"], rounds=before["rounds"], next_seq=before["next_seq"],
            classes={row.class_id:row for row in before_classes}, mode=cc.BRANCH_MODE,
            review_state=before["review_state"],
        ))

        replay_prompts: list[str] = []
        replay_index = 0
        original_run = engines.CodexEngine.run
        original_resume = engines.CodexEngine.resume

        def replay_reply(prompt: str) -> Review:
            nonlocal replay_index
            replay_prompts.append(prompt)
            row = calls[replay_index]
            replay_index += 1
            return Review(
                text=row["response_text"], session_ref=row["session_ref"],
                raw=row["response_text"],
            )

        def replay_run(self, prompt, *args, **kwargs):
            return replay_reply(prompt)

        def replay_resume(self, session_ref, prompt, *args, **kwargs):
            if session_ref != calls[0]["session_ref"]:
                raise ValueError("validation retry did not resume the original session")
            return replay_reply(prompt)

        engines.CodexEngine.run = replay_run
        engines.CodexEngine.resume = replay_resume
        try:
            replay_result = handlers.critique_branch(
                _arguments(repo), engine=engines.CodexEngine(), log_dir=temp / "logs",
                now=lambda:"REPLAY",
            )
            durable = cc.load_lineage(
                state_root, artifact["lineage_id"], stamp="REPLAYED", mode=cc.BRANCH_MODE,
            )
        finally:
            engines.CodexEngine.run = original_run
            engines.CodexEngine.resume = original_resume
            if prior_root is None:
                os.environ.pop(cc.STATE_ROOT_ENV, None)
            else:
                os.environ[cc.STATE_ROOT_ENV] = prior_root
        if replay_prompts != [row["prompt_text"] for row in calls]:
            raise ValueError("retained inputs do not reproduce the exact provider prompts")
        if replay_result != artifact["result_text"]:
            raise ValueError("public-handler replay does not reproduce retained result")
        replayed_after = json.loads(json.dumps({
            "rounds":durable.rounds, "next_seq":durable.next_seq,
            "classes":[vars(row) for row in durable.classes.values()],
            "review_state":durable.review_state,
        }))
        if replayed_after != json.loads(json.dumps(after)):
            raise ValueError("public handler does not reproduce complete durable lineage")
        footer = (
            "\n\n---\n_paranoia-local · engine=codex · "
            f"session_ref=`{calls[-1]['session_ref']}` — to dispute a finding, call `rebut` "
            "with this session_ref and your counter-evidence._"
        )
        rerendered = (
            rc.render_review(settlement, durable.review_state) + footer + "\n\n"
            + artifact["rendered_trailer"]
        )
        if rerendered != artifact["result_text"]:
            raise ValueError("replayed durable lineage does not rerender retained result")


def _arguments(repo: Path) -> dict:
    return {
        "repo_path":str(repo), "base_ref":"main", "head_ref":"feature",
        "lineage":LINEAGE, "round":2, "model":"gpt-5.6-sol",
        "effort":"high", "web_search":False, "stakes":STAKES,
        "project_summary":"A small application with runtime configuration files.",
        "diff_intent":"Change runtime mode settings.",
        "focus":"Assess the complete diff and supplied active class using normal branch-review instructions.",
    }


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
        before_lineage = _before_lineage_record()
        state = before_lineage["review_state"]
        tracked = cc.TrackedClass(**before_lineage["classes"][0])
        cc.save_lineage(state_root, cc.Lineage(
            LINEAGE, rounds=1, next_seq=2, classes={CLASS_ID:tracked},
            mode=cc.BRANCH_MODE, review_state=state,
        ))
        engine = engines.CodexEngine()
        calls: list[dict] = []
        original_run, original_resume = engine.run, engine.resume

        def record_run(prompt, *args, response_schema=None, **kwargs):
            review = original_run(prompt, *args, response_schema=response_schema, **kwargs)
            calls.append({
                "route":"fresh", "prompt_text":prompt,
                "prompt_sha256":_sha_text(prompt), "review":review,
            })
            return review

        def record_resume(session_ref, prompt, *args, response_schema=None, **kwargs):
            review = original_resume(
                session_ref, prompt, *args, response_schema=response_schema, **kwargs,
            )
            calls.append({
                "route":"resumed", "prompt_text":prompt,
                "prompt_sha256":_sha_text(prompt), "review":review,
            })
            return review

        engine.run = record_run  # type: ignore[method-assign]
        engine.resume = record_resume  # type: ignore[method-assign]
        result = handlers.critique_branch(
            _arguments(repo), engine=engine, log_dir=log_root,
        )
        audit = json.loads(next(log_root.glob("*.json")).read_text(encoding="utf-8"))
        lineage = cc.load_lineage(state_root, LINEAGE, stamp="acceptance", mode=cc.BRANCH_MODE)
        artifact_calls = [{
            "route":row["route"], "prompt_text":row["prompt_text"],
            "prompt_sha256":row["prompt_sha256"],
            "session_ref":row["review"].session_ref,
            "response_text":row["review"].text,
            "response_sha256":_sha_text(row["review"].text),
        } for row in calls]
        if any(token in artifact_calls[0]["prompt_text"] for token in FORBIDDEN_ANSWER_KEYS):
            raise RuntimeError("provider-visible acceptance prompt contains an answer key")
        artifact = {
            "acceptance_kind":"class-occurrence-batch-public-branch-handler-v1",
            "version":1, "date":"2026-08-30", "source_revision":revision,
            "source_sha256":{
                relative:_sha_bytes((ROOT / relative).read_bytes()) for relative in SOURCES
            },
            "provider":{
                "engine":"codex", "model":"gpt-5.6-sol", "effort":"high",
                "web_search":False,
                "minimum_cli_version":".".join(
                    str(part) for part in engines.MIN_CODEX_VERSION
                ),
            },
            "fixture":{
                "base_id":_git("rev-parse", "main^{commit}", cwd=repo),
                "head_id":_git("rev-parse", "feature^{commit}", cwd=repo),
                "base_files":BASE_FILES, "head_files":HEAD_FILES,
                "expected_anchors":["repository/app.conf:1", "repository/worker.conf:1"],
            },
            "lineage_id":LINEAGE, "stakes":STAKES, "calls":artifact_calls,
            "attempt_ledger":[{
                key:row[key] for key in ATTEMPT_FIELDS
            } for row in audit["attempt_ledger"]],
            "settlement":audit["staged_settlement"],
            "before_lineage":before_lineage,
            "after_lineage":{
                "rounds":lineage.rounds, "next_seq":lineage.next_seq,
                "classes":[vars(row) for row in lineage.classes.values()],
                "review_state":lineage.review_state,
            },
            "rendered_trailer":audit["rendered_trailer"],
            "result_text":result, "result_sha256":_sha_text(result),
        }
        candidate_path = Path("/tmp/paranoia-class-occurrence-batch-candidate.json")
        candidate_path.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        validate_artifact(artifact, require_committed=False)
        OUTPUT.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"wrote {OUTPUT} from {len(calls)} signed-in provider call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
