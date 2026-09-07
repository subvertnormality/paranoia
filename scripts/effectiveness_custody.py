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


def terminal(directory, outcome, error=None, *, elapsed_ms=None, dispatch_ms=None):
    if dispatch_ms is None:
        dispatch_ms = sum(read(p)["elapsed_ms"] for p in directory.glob("output-*.json"))
    if elapsed_ms is None:
        elapsed_ms = sum(read(p)["elapsed_ms"] for p in directory.glob("output-*.json"))
    shared.dump(directory / "terminal.json", {
        "outcome": outcome, "error": error, "elapsed_ms": elapsed_ms,
        "dispatch_ms": dispatch_ms, "files": runtime_files(directory),
    })


def attempts(directory):
    path = directory / "attempts.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def join_invocations(rows, checks, traces, refusals):
    """One native run/role identity per call, even when reply bytes are identical."""
    admitted = [c for c in checks if not c["refused"]]
    refused = [c for c in checks if c["refused"]]
    refusal_key = lambda r: (r["engine"], r["operation"], r.get("role"))
    if Counter(map(refusal_key, refused)) != Counter(map(refusal_key, refusals)):
        raise ValueError("refused invocations do not join the admission ledger")
    identities = [(c["run_id"], c["review_role"]) for c in checks]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate native invocation identity")
    key = lambda r: (r["engine"], r["operation"], r["prompt_sha256"],
                     r.get("raw_sha256"), r.get("session_ref"))
    if Counter(map(key, rows)) != Counter(map(key, admitted)):
        raise ValueError("attempt/workspace/prompt checks do not join")
    native = [{**a, "run_id": t["run_id"]} for t in traces for a in t.get("attempts", [])]
    native_key = lambda r: (r["run_id"], r["engine"], r["operation"],
                            r["prompt_sha256"], r.get("session_ref"))
    if Counter(map(native_key, native)) != Counter(map(native_key, admitted)):
        raise ValueError("native execution trace does not join attempts")
    joined = []
    for row in rows:
        matching = [c for c in admitted if key(c) == key(row)]
        if len(matching) != 1:
            raise ValueError("observed attempt lacks unique invocation binding")
        check = matching[0]
        matching_trace = [n for n in native if native_key(n) == native_key(check)]
        if len(matching_trace) != 1:
            raise ValueError("native invocation trace is ambiguous")
        trace = matching_trace[0]
        for name in ("model", "effort", "web_search", "schema_sha256", "requested_session"):
            if trace.get(name) != check.get(name):
                raise ValueError("native invocation settings differ: " + name)
        joined.append((row, check))
    return joined


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
    outputs, audits, traces, t, joined = [], [], [], {}, []
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
        refusal_path = directory / "refusals.jsonl"
        refusals = [json.loads(line) for line in refusal_path.read_text().splitlines()] if refusal_path.exists() else []
        joined = join_invocations(rows, checks, traces, refusals)
        if any(r.get("fixture_ok") is not True for r in checks):
            errors.append("fixture changed during invocation")
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
                native_calls = [(r, c) for r, c in joined if c["run_id"] == audit["run_id"]]
                if Counter((a["role"], a["engine"]) for a in ledger) != Counter(
                        (c["review_role"], c["engine"]) for r, c in native_calls if "exception" not in r):
                    errors.append("native staged attempt multiplicity differs")
                if audit.get("error") is False:
                    role = (audit.get("staged_settlement") or {}).get("role")
                    completed_roles = {a["role"].removesuffix("-validation-retry")
                                       for a in ledger if a.get("outcome") == "completed"}
                    required_roles = ({"census-behaviour", "census-execution", "census-integrity", "consolidation"}
                                      if role == "census" else {role})
                    if not required_roles <= completed_roles:
                        errors.append("incomplete native staged role settlement")
                for attempt in ledger:
                    matching = [r for r, c in native_calls if c["review_role"] == attempt["role"]
                                and c["engine"] == attempt["engine"]]
                    if len(matching) != 1:
                        errors.append("staged attempt lacks unique native invocation")
                        continue
                    observed = matching[0]
                    if any(observed.get(k) != attempt.get(k) for k in ("raw_sha256", "session_ref", "returncode")):
                        errors.append("staged attempt native result differs")
                    for channel, field in (("stdout", "raw_sha256"), ("stderr", "stderr_sha256"),
                                           ("failure_detail", "failure_detail_sha256")):
                        if observed["process_channels"][channel]["sha256"] != attempt.get(field):
                            errors.append("staged attempt channel differs: " + channel)
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
            "attempt_roles": {r["sequence"]: c["review_role"] for r, c in joined},
            "errors": errors, "terminal": t, "execution_success": successful and not errors,
            "clear_eligible": clear and not errors, "state": state,
            "elapsed_ms": t.get("elapsed_ms", sum(o["elapsed_ms"] for o in outputs)),
            "dispatch_ms": t.get("dispatch_ms", sum(o["elapsed_ms"] for o in outputs)),
            "calls": len(rows)}
