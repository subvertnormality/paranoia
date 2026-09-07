"""Custody joins for the effectiveness pilot; no production review authority."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import benchmark_review_modes as shared


def read(path):
    return json.loads(Path(path).read_text())


def json_digest(value):
    return shared.sha(json.dumps(value, sort_keys=True, separators=(",", ":")))


def runtime_files(directory):
    paths = [directory / "input.json"]
    paths += list(directory.glob("output-*.json")) + list(directory.glob("provider-*"))
    paths += [directory / name for name in ("attempts.jsonl", "checks.json", "refusals.jsonl")
              if (directory / name).exists()]
    paths += [p for folder in ("logs", "state") for p in (directory / folder).rglob("*") if p.is_file()]
    return {p.relative_to(directory).as_posix(): shared.sha(p.read_bytes()) for p in sorted(paths)}


def terminal(directory, outcome, error=None, *, elapsed_ms=None):
    if elapsed_ms is None:
        elapsed_ms = sum(read(p)["elapsed_ms"] for p in directory.glob("output-*.json"))
    shared.dump(directory / "terminal.json", {
        "outcome": outcome, "error": error, "elapsed_ms": elapsed_ms, "files": runtime_files(directory),
    })


def attempts(directory):
    path = directory / "attempts.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def collect_slot(directory, spec):
    """Retain observations first; all qualification errors are additive."""
    rows, errors = [], []
    try:
        path = directory / "attempts.jsonl"
        for line in path.read_text().splitlines() if path.exists() else []:
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("attempt must be an object")
                rows.append(row)
            except ValueError as exc:
                errors.append("invalid attempt record: " + str(exc))
    except OSError as exc:
        errors.append("attempt records unavailable: " + str(exc))
    outputs, audits, traces, t = [], [], [], {}
    try:
        t = read(directory / "terminal.json")
        if t["files"] != runtime_files(directory):
            errors.append("runtime custody changed")
        if read(directory / "input.json") != spec:
            errors.append("worker specification changed")
        checks = read(directory / "checks.json") if (directory / "checks.json").exists() else []
        for path in sorted((directory / "logs").glob("*.json")):
            audit = read(path)
            (traces if audit.get("tool") == "run" else audits).append(audit)
        outputs = [read(p) for p in sorted(directory.glob("output-*.json"))]
        for row in rows:
            if "exception" not in row:
                shared.validate_channels(directory, row)
            if (row.get("engine") != spec["case"]["provider"]
                    or row.get("model") != spec["models"][spec["case"]["provider"]]
                    or row.get("effort") != "high"):
                errors.append("attempt execution settings differ")
        observed = Counter((r["engine"], r["prompt_sha256"], r.get("raw_sha256")) for r in rows)
        checked = Counter((r["engine"], r["prompt_sha256"], r.get("raw_sha256")) for r in checks)
        if observed != checked or any(r.get("fixture_ok") is not True for r in checks):
            errors.append("attempt/workspace/prompt checks do not join")
        trace_rows = [row for trace in traces for row in trace.get("attempts", [])]
        if Counter((r["engine"], r["prompt_sha256"], r.get("session_ref")) for r in rows) != Counter(
            (r["engine"], r["prompt_sha256"], r.get("session_ref")) for r in trace_rows
        ):
            errors.append("native execution trace does not join attempts")
        if len(traces) != len(outputs) or len(audits) > len(outputs):
            errors.append("missing or duplicated native output/audit")
        for output in outputs:
            matches = [t for t in traces if t.get("result_sha256") == shared.sha(output["result"])]
            native = [a for a in audits if a.get("run_id") == output.get("run_id")]
            native_failure = not native and output["result"].startswith("[paranoia-local error]")
            if len(matches) != 1 or (len(native) != 1 and not native_failure) or matches[0]["run_id"] != output["run_id"]:
                errors.append("output not bound to unique native invocation")
                continue
            if native_failure:
                continue
            if output["mode"] == "query":
                try:
                    shared.require_successful_review(directory, "query", output["result"])
                except shared.ExecutionEvidenceError as exc:
                    if exc.category != "operational_failure":
                        errors.append(str(exc))
            else:
                audit = native[0]
                if (audit.get("head_id") != spec["fixture"]["head"]
                        or audit.get("base_id") != spec["fixture"]["base"]):
                    errors.append("branch audit snapshot differs")
                if audit.get("rendered_trailer") and not output["result"].endswith(audit["rendered_trailer"]):
                    errors.append("returned staged trailer differs")
                ledger = audit.get("attempt_ledger", [])
                if audit.get("error") is False:
                    role = (audit.get("staged_settlement") or {}).get("role")
                    completed_roles = {a["role"].removesuffix("-validation-retry")
                                       for a in ledger if a.get("outcome") == "completed"}
                    required_roles = ({"census-behaviour", "census-execution", "census-integrity", "consolidation"}
                                      if role == "census" else {role})
                    if not required_roles <= completed_roles:
                        errors.append("incomplete native staged role settlement")
                for attempt in ledger:
                    matching = [r for r in rows if r.get("raw_sha256") == attempt.get("raw_sha256")
                                and r.get("session_ref") == attempt.get("session_ref")]
                    if "raw_sha256" in attempt and len(matching) != 1:
                        errors.append("staged attempt does not join native channel")
        successful = bool(rows) and bool(outputs) and len(audits) == len(outputs) and not any(
            r.get("error") is not False or r.get("returncode") != 0 for r in rows
        ) and all(a.get("error") is False and a.get("returncode") == 0 for a in audits)
        successful = successful and t["outcome"] == "completed"
        state = None
        if spec["arm"] == "staged":
            states = list((directory / "state" / "lineages").glob("*.json"))
            state = read(states[0]) if len(states) == 1 else None
            if successful and state is None:
                errors.append("missing unique staged lineage")
        clear = successful and (
            spec["arm"] == "single" or (
                state is not None and state.get("review_state", {}).get("phase") == "clear"
                and any(line.startswith("CONVERGENCE: NOT-BLOCKED")
                        for line in outputs[-1]["result"].splitlines())
                and not state["review_state"].get("validation_debt")
                and not state["review_state"].get("staged_failure")
            )
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
        successful, clear, state = False, False, None
    return {"attempts": rows, "outputs": outputs, "audits": audits, "traces": traces,
            "errors": errors, "terminal": t, "execution_success": successful and not errors,
            "clear_eligible": clear and not errors, "state": state,
            "elapsed_ms": t.get("elapsed_ms", sum(o["elapsed_ms"] for o in outputs)),
            "calls": len(rows)}
