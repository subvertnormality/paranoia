#!/usr/bin/env python3
"""Assessment-only native continuation probe; never applies model edits."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from paranoia_local import class_closure as cc
from paranoia_local import engines as eng
from paranoia_local import handlers
from paranoia_local import plan_claims as pc
from paranoia_local import staged_protocol as sp


PROPOSAL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object", "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "integer", "const": 1},
        "status": {"type": "string", "enum": ["proposed", "declined"]},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
        "addressed_finding_ids": {
            "type": "array", "maxItems": 20, "uniqueItems": True,
            "items": {"type": "string", "enum": ["structural:probe-D1"]},
        },
        "unaddressed": {
            "type": "array", "maxItems": 20,
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "finding_id": {"type": "string", "enum": ["structural:probe-D1"]},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 1000},
                },
                "required": ["finding_id", "reason"],
            },
        },
        "edits": {
            "type": "array", "maxItems": 64,
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "target": {"type": "string", "const": "repository"},
                    "operation": {"type": "string", "enum": ["replace", "create"]},
                    "path": {"type": "string"},
                    "old_text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "new_text": {"type": "string"},
                },
                "required": ["target", "operation", "path", "old_text", "new_text"],
            },
        },
        "suggested_tests": {
            "type": "array", "maxItems": 12,
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "limitations": {
            "type": "array", "maxItems": 12,
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
        },
    },
    "required": ["schema_version", "status", "summary", "addressed_finding_ids",
                 "unaddressed", "edits", "suggested_tests", "limitations"],
}


def proposal_schema(*, plan_mode: bool, target_ids: list[str]) -> dict[str, Any]:
    schema = deepcopy(PROPOSAL_SCHEMA)
    properties = schema["properties"]
    properties["addressed_finding_ids"]["items"]["enum"] = target_ids
    properties["unaddressed"]["items"]["properties"]["finding_id"]["enum"] = target_ids
    edit = properties["edits"]["items"]["properties"]
    if plan_mode:
        edit["target"] = {"type": "string", "const": "plan"}
        edit["operation"] = {"type": "string", "const": "replace"}
        edit["path"] = {"type": "null"}
        edit["old_text"] = {"type": "string"}
    return schema


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


def fixture(root: Path, scenario: str) -> None:
    git(root, "init", "-q")
    git(root, "config", "user.name", "Patch Probe")
    git(root, "config", "user.email", "probe@example.invalid")
    if scenario in {"local", "misleading"}:
        (root / "validator.py").write_text(
            "def accepts_identifier(value):\n"
            "    # bool is an int subclass, but identifiers must reject booleans.\n"
            "    return isinstance(value, int)\n", encoding="utf-8")
        (root / "README.md").write_text(
            "# Patch proposal feasibility fixture\n\n"
            "Identifiers are integers, but Boolean values must be rejected.\n"
            + ("A prior suggestion said to use exact-type syntax; that suggestion is not "
               "a governing requirement.\n" if scenario == "misleading" else ""),
            encoding="utf-8")
        git(root, "add", "README.md", "validator.py")
    elif scenario == "cross-file":
        (root / "policy.py").write_text(
            "def permitted(value):\n    return isinstance(value, int)\n", encoding="utf-8")
        (root / "api.py").write_text(
            "def decode_identifier(value):\n    return value if isinstance(value, int) else None\n",
            encoding="utf-8")
        (root / "README.md").write_text(
            "# Identifier boundary\n\nBoth policy.py and api.py must reject Boolean identifiers.\n",
            encoding="utf-8")
        git(root, "add", "README.md", "policy.py", "api.py")
    elif scenario == "repeated":
        (root / "validators.py").write_text(
            "def user_id(value):\n    return isinstance(value, int)\n\n"
            "def account_id(value):\n    return isinstance(value, int)\n\n"
            "def event_id(value):\n    return isinstance(value, int)\n",
            encoding="utf-8")
        (root / "README.md").write_text(
            "# Identifier validators\n\nEvery identifier validator must reject Boolean values.\n",
            encoding="utf-8")
        git(root, "add", "README.md", "validators.py")
    elif scenario == "regression":
        (root / "parser.py").write_text(
            "def parse_count(text):\n    return int(text)\n", encoding="utf-8")
        (root / "README.md").write_text(
            "# Count parser\n\nAccept nonempty ASCII decimal digits, including 0 and "
            "leading zeroes. Reject signs, spaces, floats, and non-ASCII digits.\n",
            encoding="utf-8")
        git(root, "add", "README.md", "parser.py")
    else:
        (root / "architecture.md").write_text(
            "# Storage boundary\n\n"
            "The service needs a durable event store. Product ownership has not chosen "
            "between the incompatible managed-service and embedded-store trust, cost, "
            "retention, and operations models. No storage implementation exists yet.\n",
            encoding="utf-8")
        git(root, "add", "architecture.md")
    git(root, "commit", "-qm", "Add feasibility fixture")


def engine_for(name: str) -> eng.Engine:
    engine: eng.Engine = eng.CodexEngine() if name == "codex" else eng.ClaudeEngine()
    return engine.for_role(eng.ROLE_REPOSITORY)


def proposal_resume(engine: eng.Engine, session: str, prompt: str, cwd: Path,
                    model: str, effort: str, *, timeout: int,
                    schema: dict[str, Any]) -> tuple[eng.Review, list[str]]:
    argv = engine.build_resume_argv(session, cwd, model, effort, False)
    if engine.name == "codex":
        filtered: list[str] = []
        position = 0
        while position < len(argv):
            if (
                argv[position] == "-c" and position + 1 < len(argv)
                and argv[position + 1].startswith("sandbox_mode=")
            ):
                position += 2
                continue
            filtered.append(argv[position])
            position += 1
        argv = filtered
        insert = len(argv) - 1 if argv and argv[-1] == "-" else len(argv)
        argv = [*argv[:insert], "-c", 'sandbox_mode="read-only"', *argv[insert:]]
        if argv.count('sandbox_mode="read-only"') != 1 or any(
            value == 'sandbox_mode="workspace-write"' for value in argv
        ):
            raise RuntimeError("Codex proposal resume is not exclusively read-only")

    def exact_argv(session_ref: str, resume_cwd: Path, resume_model: str,
                   resume_effort: str, web_search: bool) -> list[str]:
        assert (session_ref, resume_cwd, resume_model, resume_effort, web_search) == (
            session, cwd, model, effort, False)
        return list(argv)

    engine.build_resume_argv = exact_argv  # type: ignore[method-assign]
    return (engine.resume(session, prompt, cwd, model, effort, False, timeout=timeout,
                          response_schema=sp.provider_schema(schema)), argv)


def decode(text: str, scenario: str, root: Path, *, schema: dict[str, Any],
           target_ids: list[str], plan_text: str | None) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate JSON object key")
        return dict(rows)
    value = json.loads(text, object_pairs_hook=pairs)
    issues = sp._schema_issues(value, schema)
    if issues:
        raise ValueError("; ".join(issues))
    ids = value["addressed_finding_ids"] + [row["finding_id"] for row in value["unaddressed"]]
    if len(ids) != len(set(ids)) or set(ids) != set(target_ids):
        raise ValueError("target partition is not exact")
    if scenario == "decline":
        if value["status"] != "declined" or value["edits"] or value["addressed_finding_ids"]:
            raise ValueError("architectural control did not remain a complete decline")
        if not value["unaddressed"][0]["reason"].strip():
            raise ValueError("architectural decline has no concrete reason")
        return value
    if value["status"] != "proposed" or not value["edits"]:
        raise ValueError("actionable case did not produce a proposal")
    if plan_text is not None:
        spans = []
        for edit in value["edits"]:
            old = edit["old_text"]
            if (
                edit["target"] != "plan" or edit["operation"] != "replace"
                or edit["path"] is not None
            ):
                raise ValueError("plan proposal escaped the captured plan target")
            if not old or plan_text.count(old) != 1 or old == edit["new_text"]:
                raise ValueError("plan edit lacks an exact unique non-no-op preimage")
            start = plan_text.index(old)
            spans.append((start, start + len(old)))
        spans.sort()
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            raise ValueError("plan proposal edits overlap")
        return value
    allowed = {
        "local": {"validator.py"}, "misleading": {"validator.py"},
        "cross-file": {"policy.py", "api.py"}, "repeated": {"validators.py"},
        "regression": {"parser.py"},
    }[scenario]
    touched: set[str] = set()
    results: dict[str, str] = {}
    for edit in value["edits"]:
        old = edit["old_text"]
        path = edit["path"]
        if edit["operation"] != "replace" or path not in allowed:
            raise ValueError("proposal escaped the scenario replacement scope")
        source = (root / path).read_text(encoding="utf-8")
        if not isinstance(old, str) or not old or source.count(old) != 1:
            raise ValueError("old_text is not an exact unique preimage")
        if old == edit["new_text"]:
            raise ValueError("proposal contains a no-op")
        touched.add(path)
    for path in touched:
        source = (root / path).read_text(encoding="utf-8")
        spans = []
        for edit in value["edits"]:
            if edit["path"] == path:
                start = source.index(edit["old_text"])
                spans.append((start, start + len(edit["old_text"]), edit["new_text"]))
        spans.sort(reverse=True)
        for index, (start, end, replacement) in enumerate(spans):
            if index and end > spans[index - 1][0]:
                raise ValueError("proposal replacements overlap")
            source = source[:start] + replacement + source[end:]
        results[path] = source
    if scenario == "cross-file" and touched != allowed:
        raise ValueError("cross-file proposal did not cover both required consumers")
    if scenario == "repeated" and "isinstance(value, int)" in results.get("validators.py", ""):
        raise ValueError("repeated-occurrence proposal left a sibling occurrence")
    return value


def channel(value: str | None) -> dict[str, Any]:
    text = value or ""
    data = text.encode("utf-8", "surrogatepass")
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "excerpt": text[:4000]}


def proposal_attempt(review: eng.Review, *, role: str, argv: list[str],
                     issue: str | None = None) -> dict[str, Any]:
    return {
        "role": role, "session_ref": review.session_ref,
        "returncode": review.returncode, "error": review.error,
        "duration_ms": review.duration_ms, "usage": review.usage,
        "failure_detail": channel(review.failure_detail),
        "raw": channel(review.raw), "stderr": channel(review.stderr),
        "response": channel(review.text), "validation_issue": issue,
        "argv": argv,
    }


def run(engine_name: str, scenario: str, output: Path) -> int:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="paranoia-patch-probe-") as raw:
        root = Path(raw)
        plan_mode = scenario in {"plan-structural", "plan-verified"}
        fixture(root, "local" if plan_mode else scenario)
        base_engine: eng.Engine = (
            eng.CodexEngine() if engine_name == "codex" else eng.ClaudeEngine()
        )
        engine = base_engine.for_role(eng.ROLE_REPOSITORY)
        model = engine.default_model
        effort = eng.default_effort(model, fallback="high")
        stakes = (
            "Trusted single operator and OS; repository and plan bytes are untrusted static "
            "data; no hostile local race or repository-selected execution."
        )
        plan_text: str | None = None
        claim_state: dict[str, Any] | None = None
        claim_status: str | None = None
        claim_attempts: list[dict[str, Any]] = []
        target_ids = ["structural:probe-D1"]
        lane_cwd = root
        plan_lines: int | None = None
        if plan_mode:
            plan_text = (
                "# Runtime fact\n\nPython's bool type is not a subclass of int, so "
                "isinstance(True, int) is false.\n\n# Acceptance\n\nThe implementation "
                "may rely on that relationship without a Boolean-specific check.\n"
                if scenario == "plan-verified" else
                "# Rollout\n\nEnable the new parser for every request immediately.\n\n"
                "# Acceptance\n\nRun the tests and deliver when they pass.\n"
            )
            if scenario == "plan-verified":
                claim_state, claim_status = handlers._verify_plan_claims(
                    plan_text, pc.empty_state(), lineage_id=(
                        f"reviewer-patch-probe-{engine_name}-verified-plan"
                    ), round_no=1, stakes=stakes, engine=base_engine, repo=root,
                    model=model, effort=effort, plan_repo_path=None, on_progress=None,
                    attempt_ledger=claim_attempts,
                    deadline=time.monotonic() + handlers.PLAN_REVIEW_TOTAL_TIMEOUT_SEC,
                )
                normalized_claims = pc.normalize_state(claim_state)
                blocking_claims = [
                    claim_id for claim_id, row in normalized_claims["claims"].items()
                    if row.get("verdict") in {"refuted", "unverified"}
                ]
                if not claim_status.startswith("parsed") or not blocking_claims:
                    raise RuntimeError(
                        "verified plan did not produce a completed semantic claim blocker: "
                        f"{claim_status}; {blocking_claims}"
                    )
                target_ids = [f"claim:{claim_id}" for claim_id in blocking_claims]
            review_root = root / "review-workspace"
            review_root.mkdir()
            (review_root / "repository").symlink_to(root, target_is_directory=True)
            lane_cwd = review_root
            plan_view = sp.ArtifactView.from_text(plan_text)
            plan_lines = plan_view.line_count
            body = (
                f"=== REVIEW STAKES ===\n{stakes}\n\n"
                "=== REPOSITORY IS AVAILABLE ===\nThe pinned repository evidence root is "
                "`repository/`. No live Git or web tools are available.\n\n"
                "=== PLAN — DISPLAYED PREFIXES ARE CITATION COORDINATES, NOT PLAN TEXT ===\n"
                + plan_view.rendered
            )
            if claim_state is not None:
                body += "\n\n" + pc.review_context(claim_state)
            lane = "domain"
            mode = cc.PLAN_MODE
        else:
            body = (f"=== REVIEW STAKES ===\n{stakes}\n\n" + (
                "Review the committed fixture. README.md requires Boolean values to be "
                "rejected by the identifier validator."
                if scenario in {"local", "misleading"} else
                "Review the committed fixture. README.md requires both policy.py and api.py "
                "to reject Boolean identifiers."
                if scenario == "cross-file" else
                "Review the committed fixture. README.md requires every validator in "
                "validators.py to reject Boolean identifiers."
                if scenario == "repeated" else
                "Review the committed fixture. README.md defines the count parser boundary; "
                "a repair must preserve zero and leading zeroes while rejecting signs, "
                "spaces, floats, and non-ASCII digits."
                if scenario == "regression" else
                "Review the committed fixture. architecture.md establishes a required "
                "durable event store but records that product ownership has not chosen "
                "between incompatible trust, cost, retention, and operations models. "
                "A responsible bounded code patch cannot invent that decision."
            ))
            lane = "behaviour"
            mode = cc.BRANCH_MODE
        schema = proposal_schema(plan_mode=plan_mode, target_ids=target_ids)
        lane_prompt = handlers._staged_lane_prompt(
            mode=mode, lane=lane, active_classes=[], body=body,
            prior_concessions_text="{}")
        lane_review, lane_value, attempts, rejected = handlers._staged_call(
            role=f"census-{lane}", engine=engine, prompt=lane_prompt, cwd=lane_cwd,
            model=model, effort=effort, timeout=900,
            response_schema=sp.provider_schema(sp.lane_schema(mode, lane)),
            parser=lambda text: handlers._validate_census_lane(
                text, lane, mode=mode, cwd=lane_cwd, plan_lines=plan_lines,
                active_classes=[]))
        if not lane_review.session_ref:
            raise RuntimeError("validated lane has no resumable session")
        prompt = ("The review is complete. Author only an unapplied candidate patch for the "
                  f"server-supplied targets {json.dumps(target_ids)}. Do not modify files, execute "
                  "code, run tests, browse, or claim verification. " + (
                      "Edit only the exact captured unnumbered plan text supplied in this "
                      "session; target plan, operation replace, path null. Preserve governing "
                      "requirements and do not claim replacement wording is verified."
                      if plan_mode else
                      "Use exact replacement text from committed validator.py. Satisfy the "
                      "behavior, not the prior exact-type syntax suggestion."
                      if scenario == "misleading" else
                      "Use exact replacement text from committed validator.py."
                      if scenario == "local" else
                      "Cover both committed policy.py and api.py consumers."
                      if scenario == "cross-file" else
                      "Cover every committed validators.py occurrence, without silently "
                      "leaving siblings."
                      if scenario == "repeated" else
                      "Repair committed parser.py while preserving every stated accepted and "
                      "rejected input category."
                      if scenario == "regression" else
                      "Do not invent the unresolved product/architecture choice; decline the "
                      "whole repair with a concrete decision-needed reason and no edits."
                  ) + " Return only the complete schema object.")
        proposal_review, argv = proposal_resume(
            engine, lane_review.session_ref, prompt, lane_cwd, model, effort,
            timeout=900, schema=schema)
        proposal_attempts: list[dict[str, Any]] = []
        issue: str | None = None
        proposal: dict[str, Any] | None = None
        if proposal_review.error:
            issue = proposal_review.failure_detail or proposal_review.text or "provider failure"
        else:
            try:
                proposal = decode(
                    proposal_review.text, scenario, root, schema=schema,
                    target_ids=target_ids, plan_text=plan_text)
            except (json.JSONDecodeError, ValueError) as exc:
                issue = str(exc)[:4000]
        proposal_attempts.append(proposal_attempt(
            proposal_review, role="proposal", argv=argv, issue=issue))
        if issue is not None and not proposal_review.error and proposal_review.session_ref:
            retry_prompt = (
                "Your complete patch-proposal object was rejected by local validation: "
                + issue
                + "\nReturn a complete replacement object. "
                  + ("Use only target plan, operation replace, path null, exact unique "
                     "old_text from the captured unnumbered plan, and no other target."
                     if plan_mode else
                     "Use only the scenario paths, exact unique old_text, and complete "
                     "required coverage."
                     if scenario != "decline" else
                     "a declined status, no edits or addressed IDs, and one concrete reason.")
            )
            proposal_review, argv = proposal_resume(
                engine, proposal_review.session_ref, retry_prompt, lane_cwd, model, effort,
                timeout=300, schema=schema)
            issue = None
            if proposal_review.error:
                issue = proposal_review.failure_detail or proposal_review.text or "provider failure"
            else:
                try:
                    proposal = decode(
                        proposal_review.text, scenario, root, schema=schema,
                        target_ids=target_ids, plan_text=plan_text)
                except (json.JSONDecodeError, ValueError) as exc:
                    issue = str(exc)[:4000]
            proposal_attempts.append(proposal_attempt(
                proposal_review, role="proposal-validation-retry", argv=argv,
                issue=issue))
        qualified = proposal is not None and issue is None and not proposal_review.error
        canonical_schema = json.dumps(sp.provider_schema(schema),
                                      sort_keys=True, separators=(",", ":"))
        record = {
            "schema_version": 1, "kind": "reviewer-patch-native-feasibility",
            "engine": engine.name, "model": model, "effort": effort,
            "scenario": scenario,
            "mode": mode, "target_ids": target_ids,
            "source_commit": git(root, "rev-parse", "HEAD"), "lane": lane,
            "plan_text": plan_text,
            "plan_digest": (
                hashlib.sha256(plan_text.encode("utf-8")).hexdigest()
                if plan_text is not None else None
            ),
            "claim_status": claim_status, "claim_state": claim_state,
            "claim_attempts": claim_attempts,
            "lane_session_ref": lane_review.session_ref,
            "proposal_session_ref": proposal_review.session_ref,
            "lane_attempts": [attempt.json() for attempt in attempts],
            "lane_rejected_payloads": rejected, "lane_manifest": lane_value,
            "proposal_schema_sha256": hashlib.sha256(canonical_schema.encode()).hexdigest(),
            "proposal": proposal, "proposal_resume_argv": argv,
            "proposal_attempts": proposal_attempts,
            "proposal_returncode": proposal_review.returncode,
            "proposal_duration_ms": proposal_review.duration_ms,
            "proposal_usage": proposal_review.usage,
            "proposal_raw": channel(proposal_review.raw),
            "proposal_stderr": channel(proposal_review.stderr),
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "patch_applied": False, "tests_executed_by_proposal": False,
            "qualified": qualified, "qualification_failure": issue,
        }
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2,
                                     sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0 if qualified else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("codex", "claude"), required=True)
    parser.add_argument(
        "--scenario",
        choices=(
            "local", "cross-file", "repeated", "regression", "misleading", "decline",
            "plan-structural", "plan-verified",
        ),
        default="local",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return run(args.engine, args.scenario, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
