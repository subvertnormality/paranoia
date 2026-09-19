#!/usr/bin/env python3
"""Materialize the frozen reviewer-patch historical transition ledger."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


AUDIT_ROOT = Path("/home/andy/.paranoia/logs")
GIT_ROOTS = (Path("/home/andy/tools/paranoia-local"), Path("/home/andy/parallax"))
BRANCH_LINEAGES = (
    "parallax~3~CENSUS-EVIDENCE-MATERIALIZATION",
    "ae52f6186204",
    "paranoia-issue124-claude-quota-code",
    "parallax~3~maintenance-long-tests-20260909-01a0764c",
    "parallax~3~maintenance-throughput-20260906-01a0764c",
    "parallax~3~CENSUS-EVIDENCE-ACQUISITION",
)
PLAN_LINEAGES = {
    "parallax~3~CENSUS-EVIDENCE-MATERIALIZATION~plan": (
        Path("/home/andy/parallax"),
        "dataset/certification/CENSUS-EVIDENCE-MATERIALIZATION_plan_contract.md",
    ),
}


def run_bytes(cwd: Path, *args: str) -> bytes:
    return subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout


def run_text(cwd: Path, *args: str) -> str:
    return run_bytes(cwd, *args).decode("utf-8", "surrogateescape")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audits() -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    selected = set(BRANCH_LINEAGES) | set(PLAN_LINEAGES)
    result = {lineage: [] for lineage in selected}
    for path in sorted(AUDIT_ROOT.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        lineage = value.get("lineage")
        if lineage in result:
            result[lineage].append((path, value))
    return result


def commit_root(*commits: str) -> Path:
    for root in GIT_ROOTS:
        if all(subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0 for commit in commits):
            return root
    raise RuntimeError(f"no retained Git object store contains commits {commits!r}")


def plan_blobs(root: Path, repo_path: str) -> dict[str, dict[str, Any]]:
    commits = run_text(
        root, "git", "log", "--all", "--reflog", "--format=%H", "--", repo_path,
    ).splitlines()
    result: dict[str, dict[str, Any]] = {}
    for commit in commits:
        try:
            data = run_bytes(root, "git", "show", f"{commit}:{repo_path}")
            blob = run_text(root, "git", "rev-parse", f"{commit}:{repo_path}").strip()
        except subprocess.CalledProcessError:
            continue
        digest = sha256(data)
        result.setdefault(digest[:16], {
            "blob_id": blob, "sha256": digest, "bytes": len(data), "data": data,
        })
    return result


def open_debt(audit: dict[str, Any]) -> list[dict[str, Any]]:
    settlement = audit.get("staged_settlement")
    if not isinstance(settlement, dict):
        return []
    rows = settlement.get("debt")
    if not isinstance(rows, list):
        return []
    return [
        {key: row.get(key) for key in ("id", "finding_id", "severity", "summary")}
        for row in rows if isinstance(row, dict) and row.get("status") == "open"
    ]


def verdict(audit: dict[str, Any]) -> dict[str, Any]:
    trailer = audit.get("rendered_trailer") or ""
    lines = trailer.splitlines()
    return {
        "convergence": next((line for line in lines if line.startswith("CONVERGENCE:")), None),
        "structural_phase": next((line for line in lines if line.startswith("STRUCTURAL-PHASE:")), None),
        "returncode": audit.get("returncode"), "error": audit.get("error"),
    }


def telemetry(audit: dict[str, Any]) -> dict[str, Any]:
    attempts = audit.get("attempt_ledger")
    if not isinstance(attempts, list):
        attempts = []
    return {
        "known_model_calls": len(attempts),
        "duration_ms": audit.get("duration_ms"),
        "usage": audit.get("usage"),
        "attempts": [{
            key: row.get(key) for key in (
                "sequence", "role", "engine", "outcome", "duration_ms", "usage",
                "requested_timeout_sec", "validation_issue",
            )
        } for row in attempts if isinstance(row, dict)],
    }


def cause(predecessor: dict[str, Any], successor: dict[str, Any]) -> list[str]:
    attempts = successor.get("attempt_ledger") or []
    categories: list[str] = []
    if any(isinstance(row, dict) and row.get("validation_issue") for row in attempts):
        categories.append("validation/protocol failure")
    if any(isinstance(row, dict) and row.get("outcome") not in {None, "completed"}
           for row in attempts):
        categories.append("execution failure")
    trailer = predecessor.get("rendered_trailer") or ""
    if "cold final regression is required" in trailer.lower():
        categories.append("required final")
    return categories or ["unknown"]


def base_row(lineage: str, before: tuple[Path, dict[str, Any]],
             after: tuple[Path, dict[str, Any]]) -> dict[str, Any]:
    before_path, predecessor = before
    after_path, successor = after
    return {
        "lineage": lineage,
        "predecessor_audit": before_path.name,
        "predecessor_round": predecessor.get("round"),
        "predecessor_debt": open_debt(predecessor),
        "successor_audit": after_path.name,
        "successor_round": successor.get("round"),
        "successor_result": verdict(successor),
        "known_cost": telemetry(successor),
        "cause_categories": cause(predecessor, successor),
    }


def changed_pairs(rows: list[tuple[Path, dict[str, Any]]], key: str):
    prior = rows[0] if rows else None
    for current in rows[1:]:
        if current[1].get(key) != prior[1].get(key):
            yield prior, current
        prior = current


def branch_rows(lineage: str, rows: list[tuple[Path, dict[str, Any]]]):
    result = []
    for before, after in changed_pairs(rows, "head_id"):
        old = before[1].get("head_id")
        new = after[1].get("head_id")
        if not isinstance(old, str) or not isinstance(new, str):
            raise RuntimeError(f"missing branch identity in {lineage}")
        root = commit_root(old, new)
        patch = run_bytes(root, "git", "diff", "--binary", "--no-ext-diff", old, new)
        row = base_row(lineage, before, after)
        row.update({
            "mode": "branch", "git_root": str(root),
            "predecessor_head": old, "successor_head": new,
            "repair_diff": {
                "command": ["git", "diff", "--binary", "--no-ext-diff", old, new],
                "sha256": sha256(patch), "bytes": len(patch),
                "name_status": run_text(root, "git", "diff", "--name-status", old, new).splitlines(),
                "numstat": run_text(root, "git", "diff", "--numstat", old, new).splitlines(),
            },
        })
        result.append(row)
    return result


def plan_rows(lineage: str, rows: list[tuple[Path, dict[str, Any]]],
              root: Path, repo_path: str):
    blobs = plan_blobs(root, repo_path)
    result = []
    for before, after in changed_pairs(rows, "plan_digest"):
        old_digest = before[1].get("plan_digest")
        new_digest = after[1].get("plan_digest")
        if old_digest not in blobs or new_digest not in blobs:
            raise RuntimeError(
                f"missing retained plan blob for {lineage}: {old_digest} -> {new_digest}"
            )
        old, new = blobs[old_digest], blobs[new_digest]
        patch = b"".join(difflib.diff_bytes(
            difflib.unified_diff, old["data"].splitlines(keepends=True),
            new["data"].splitlines(keepends=True),
            fromfile=f"a/{repo_path}".encode(), tofile=f"b/{repo_path}".encode(),
        ))
        row = base_row(lineage, before, after)
        row.update({
            "mode": "plan", "git_root": str(root), "repository_path": repo_path,
            "predecessor_plan_digest": old_digest,
            "successor_plan_digest": new_digest,
            "repair_diff": {
                "predecessor_blob": old["blob_id"], "successor_blob": new["blob_id"],
                "predecessor_sha256": old["sha256"], "successor_sha256": new["sha256"],
                "sha256": sha256(patch), "bytes": len(patch),
            },
        })
        result.append(row)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    found = audits()
    transitions = []
    inventory = []
    for lineage in BRANCH_LINEAGES:
        rows = branch_rows(lineage, found[lineage])
        inventory.append({"lineage": lineage, "mode": "branch",
                          "audits": len(found[lineage]), "transitions": len(rows)})
        transitions.extend(rows)
    for lineage, (root, repo_path) in PLAN_LINEAGES.items():
        rows = plan_rows(lineage, found[lineage], root, repo_path)
        inventory.append({"lineage": lineage, "mode": "plan",
                          "audits": len(found[lineage]), "transitions": len(rows)})
        transitions.extend(rows)
    report = {
        "schema_version": 1, "kind": "reviewer-patch-historical-transition-ledger",
        "selection": inventory, "transition_count": len(transitions),
        "limitations": [
            "Unknown cause means the retained audits and Git diff do not prove a more specific cause.",
            "Known cost excludes unrecorded caller work, human inspection, and subscription price.",
            "Diff bytes are reproducible from the recorded Git objects and command; the ledger stores their full digest, not a duplicate patch body.",
        ],
        "transitions": transitions,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
