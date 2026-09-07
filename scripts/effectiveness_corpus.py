"""Oracle-owned pilot corpus. Never copy this module into reviewer workspaces."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

COMMON = (
    "Review app.py against this specification. helpers.py supplies the documented "
    "fixture context and is not a proposed change. Callers enforce the stated input "
    "domain. Do not execute repository code. Missing tests alone are not a contract "
    "defect. Identify concrete reachable violations, not optional enhancements.\n\n"
)

HELPERS = '''import json
import hashlib
import re
from pathlib import Path
from typing import Any
from copy import deepcopy
from urllib.parse import urlparse
from dataclasses import dataclass

AUDIT_MARKER = "=== CLAIM AUDIT JSON ==="
MAX_ACTIVE_CLAIMS = 100
DIAGNOSTIC_CHARS = 8000

class AuditError(ValueError):
    def __init__(self, reason, raw):
        self.reason = reason
        self.raw = raw
        super().__init__(reason)

@dataclass
class Audit:
    claims: tuple
    coverage: dict
    prior_dispositions: tuple
    prior_assessments: tuple
    issues: tuple
    digest: str
    excerpt: str

def _excerpt(text):
    return text[:2000]

def _validate_claim(item, plan_text, **kwargs):
    if not isinstance(item, dict) or set(item) != {"anchor", "proposition"}:
        raise ValueError("claim fields invalid")
    if not all(isinstance(v, str) and v.strip() for v in item.values()):
        raise ValueError("claim text invalid")
    if "whole" in item["proposition"].lower().split() and "whole" not in plan_text.lower().split():
        raise ValueError("proposition introduces whole absent from plan wording")
    return dict(item)

def _validate_dispositions(value, raw):
    if not isinstance(value, list):
        raise AuditError("prior_dispositions must be an array", raw)
    return tuple(value)

def _validate_assessments(value, raw):
    if not isinstance(value, list):
        raise AuditError("prior_assessments must be an array", raw)
    return tuple(value)

def _one_line(value, name):
    if not isinstance(value, str) or not value.strip() or "\\n" in value or "\\r" in value:
        raise ValueError(name + " must be nonempty one-line text")
    return value
'''
PREFIX = '''from helpers import (
    json, hashlib, re, Path, Any, deepcopy, urlparse, Audit, AuditError,
    AUDIT_MARKER, MAX_ACTIVE_CLAIMS, DIAGNOSTIC_CHARS, _excerpt,
    _validate_claim, _validate_dispositions, _validate_assessments, _one_line,
)

'''


def historical(root: Path, revision: str, function: str):
    commit = subprocess.check_output(
        ["git", "rev-parse", revision], cwd=root, text=True).strip()
    path = "src/paranoia_local/plan_claims.py"
    raw = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=root)
    text = raw.decode("utf-8")
    node = next(n for n in ast.parse(text).body
                if isinstance(n, ast.FunctionDef) and n.name == function)
    span = "\n".join(text.splitlines()[node.lineno - 1:node.end_lineno]) + "\n"
    return PREFIX + span, {
        "kind": "historical-extracted", "revision": commit, "path": path,
        "start": node.lineno, "end": node.end_lineno,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "span_sha256": hashlib.sha256(span.encode()).hexdigest(),
        "transformation": "Exact function lines with fixture import prefix; helpers are controlled context.",
    }


def build(root: Path):
    families = [
        ("overlap", "codex",
         "overlap(a,b) returns whether two half-open integer intervals share any point. "
         "Each interval is a pair (start,end) with start <= end. Empty intervals share no points.\n",
         "def overlap(a, b):\n    return max(a[0], b[0]) <= min(a[1], b[1])\n",
         "def overlap(a, b):\n    return max(a[0], b[0]) < min(a[1], b[1])\n"),
        ("reserve", "claude",
         "reserve(state,amount) returns True and deducts amount from state['available'] "
         "when sufficient units exist. On insufficient units it returns False and leaves "
         "state byte-for-byte equivalent. Inputs are nonnegative integers; state has only "
         "the available key. There is one caller and no concurrent access.\n",
         "def reserve(state, amount):\n    state['available'] -= amount\n    if state['available'] < 0:\n        return False\n    return True\n",
         "def reserve(state, amount):\n    if amount > state['available']:\n        return False\n    state['available'] -= amount\n    return True\n"),
    ]
    for family, provider, spec, function, revision in [
        ("diagnostic", "codex",
         "parse_audit parses one marked JSON object using the supplied helper validators. "
         "For a decodable correctly shaped object, the bounded error must report all "
         "independent suffix, claim-row and coverage errors so one correction can repair "
         "them together. A suffix always rejects, even in partial mode. Partial mode may "
         "retain valid rows with row issues when there is no fatal suffix/coverage error. "
         "Helpers implement the fixture row domain exactly as supplied; no broader external "
         "claim semantics are implied.\n", "parse_audit", "1ca55d9"),
        ("identity", "claude",
         "_validate_capture_attestations accepts a list with at most one row per evidence "
         "item. Each row has exactly the listed fields and an exact integer evidence_index "
         "within range, not another JSON scalar. Identity, URL and relation must agree with "
         "the referenced evidence item. Duplicate identities reject; the digest is lowercase "
         "64-digit hex, decision flags are booleans and reason fields are nonempty single "
         "lines. Reject invalid inputs with ValueError. No network access is required.\n",
         "_validate_capture_attestations", "ac50c47"),
    ]:
        bad, bad_source = historical(root, revision + "^", function)
        good, good_source = historical(root, revision, function)
        families.append((family, provider, spec, bad, good, bad_source, good_source))
    cases, oracle = [], {}
    for row in families:
        family, provider, spec, bad, good = row[:5]
        for defect, app in [(True, bad), (False, good)]:
            case_id = "c-" + hashlib.sha256((family + str(defect)).encode()).hexdigest()[:12]
            files = {"SPEC.md": COMMON + spec, "app.py": app, "helpers.py": HELPERS if len(row) > 5 else ""}
            cases.append({"id": case_id, "provider": provider, "files": files})
            oracle[case_id] = {
                "family": family, "defective": defect,
                "specification": files["SPEC.md"],
                "provenance": row[5 if defect else 6] if len(row) > 5 else {"kind": "seeded"},
                "witness": witness(family, files),
            }
            assert oracle[case_id]["witness"]["violates"] is defect
    return cases, oracle


def witness(family, files):
    """Execute only this trusted, locally authored/extracted corpus before freezing."""
    import types
    import sys
    helper = types.ModuleType("helpers")
    previous = sys.modules.get("helpers")
    sys.modules["helpers"] = helper
    namespace = {}
    try:
        exec(compile(files["helpers.py"], "helpers.py", "exec"), helper.__dict__)
        exec(compile(files["app.py"], "app.py", "exec"), namespace)
        if family == "overlap":
            inputs = ((1, 3), (3, 5))
            actual = namespace["overlap"](*inputs)
            return {"input": inputs, "expected": False, "actual": actual, "violates": actual is not False}
        if family == "reserve":
            state = {"available": 3}
            result = namespace["reserve"](state, 5)
            return {"input": {"available": 3, "amount": 5}, "expected": [False, {"available": 3}],
                    "actual": [result, state], "violates": result is not False or state != {"available": 3}}
        if family == "diagnostic":
            value = {"claims": [{"anchor": "a", "proposition": "whole project"}],
                     "coverage": {"prior_dispositions": [], "prior_assessments": []}}
            raw = helper.AUDIT_MARKER + "\n" + json.dumps(value) + "\nextra"
            try:
                namespace["parse_audit"](raw, "project")
                actual = "accepted"
            except helper.AuditError as exc:
                actual = exc.reason
            return {"input": raw, "plan": "project", "expected_errors": ["unexpected text after", "whole"],
                    "actual": actual, "violates": not all(t in actual for t in ["unexpected text after", "whole"])}
        evidence = [{"url": "https://example.test/a", "relation": "supports_claim"}] * 2
        row = {"evidence_index": True, "final_url": "https://example.test/a",
               "relation": "supports_claim", "text_sha256": "a" * 64,
               "publisher_authority": True, "passage_entailment": True,
               "authority_reason": "fixture authority", "entailment_reason": "fixture passage"}
        try:
            namespace["_validate_capture_attestations"]([row], evidence)
            actual = "accepted"
        except ValueError as exc:
            actual = str(exc)
        return {"input": {"value": [row], "evidence": evidence}, "expected": "reject boolean identity",
                "actual": actual, "violates": actual == "accepted"}
    finally:
        if previous is None:
            sys.modules.pop("helpers", None)
        else:
            sys.modules["helpers"] = previous
