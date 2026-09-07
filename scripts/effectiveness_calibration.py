"""Oracle-owned finite calibration checks; never supplied to review providers.

These checks execute only the explicitly authored/extracted local corpus. They
are examples and finite-domain references, not a proof of arbitrary Python.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import sys
import types


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@contextmanager
def fixture(files):
    helper = types.ModuleType("helpers")
    previous = sys.modules.get("helpers")
    sys.modules["helpers"] = helper
    namespace = {}
    try:
        exec(compile(files["helpers.py"], "helpers.py", "exec"), helper.__dict__)
        exec(compile(files["app.py"], "app.py", "exec"), namespace)
        yield namespace, helper
    finally:
        if previous is None:
            sys.modules.pop("helpers", None)
        else:
            sys.modules["helpers"] = previous


def observe(call):
    try:
        return {"kind": "return", "value": call()}
    except ValueError as exc:
        return {"kind": "error", "type": type(exc).__name__,
                "reason": str(getattr(exc, "reason", exc))}
    except Exception as exc:
        return {"kind": "unexpected", "type": type(exc).__name__, "reason": str(exc)}


class Checks:
    def __init__(self, family, defective):
        self.family, self.defective, self.rows = family, defective, []

    def add(self, name, inputs, expected, actual, failures, allowed=(), domain="admitted"):
        failures = list(failures)
        row = {"id": name, "domain": domain, "input": deepcopy(inputs),
               "expected": expected, "actual": actual, "failures": failures,
               "target_family": self.family if allowed else None}
        if actual.get("kind") == "unexpected":
            failures.append("unexpected-exception")
        if failures and (not self.defective or any(f not in allowed for f in failures)):
            raise ValueError(f"corpus calibration failed: {self.family}/{name}: {failures}")
        row["observation_sha256"] = digest(row)
        self.rows.append(row)

    def finish(self, files):
        failed = [r["id"] for r in self.rows if r["failures"]]
        if self.defective and not failed:
            raise ValueError(f"corpus calibration lost target defect: {self.family}")
        return {"schema": 1, "family": self.family, "defective": self.defective,
                "files_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()},
                "checks": self.rows, "target_failures": failed,
                "checks_sha256": digest(self.rows)}


def _overlap(ns, helper, checks):
    intervals = [(a, b) for a in range(-2, 3) for b in range(a, 3)]
    for i, a in enumerate(intervals):
        for j, b in enumerate(intervals):
            # Enumerate actual integer points rather than restating the implementation.
            expected = bool(set(range(*a)) & set(range(*b)))
            actual = observe(lambda: ns["overlap"](a, b))
            failures = []
            if actual["kind"] != "return" or type(actual.get("value")) is not bool:
                failures.append("return-shape")
            elif actual["value"] is not expected:
                failures.append("overlap-result")
            target = not expected and bool(set(range(a[0], a[1] + 1)) & set(range(b[0], b[1] + 1)))
            checks.add(f"points-{i}-{j}", [a, b], expected, actual, failures,
                       ("overlap-result",) if target else ())


def _reserve(ns, helper, checks):
    for available in range(6):
        for amount in range(8):
            state, reference = {"available": available}, available
            prior_failure = False
            for step, requested in enumerate((amount, 0, 1, available, available + 1)):
                sufficient = requested <= reference
                if sufficient:
                    reference -= requested
                before = deepcopy(state)
                actual = observe(lambda: ns["reserve"](state, requested))
                actual["state"] = deepcopy(state)
                expected = {"value": sufficient, "state": {"available": reference}}
                failures = []
                if actual["kind"] != "return" or type(actual.get("value")) is not bool:
                    failures.append("return-shape")
                elif actual["value"] is not sufficient:
                    failures.append("result-after-failed-reservation")
                if digest(state) != digest(expected["state"]):
                    failures.append("failed-reservation-state")
                allowed = []
                if prior_failure or not sufficient:
                    allowed.append("failed-reservation-state")
                if prior_failure:
                    allowed.append("result-after-failed-reservation")
                checks.add(f"sequence-{available}-{amount}-{step}",
                           {"initial": available, "amount": requested, "before": before},
                           expected, actual, failures, allowed)
                prior_failure |= not sufficient


def _parse_case(ns, helper, checks, name, value, *, partial=False, wrapper="none",
                suffix="", rows=(), issues=(), coverage_errors=(), structural=False,
                raw_override=None):
    openings = {"none": "", "plain": "```\n", "json": "```json\n",
                "opening": "```json\n", "closing": ""}
    endings = {"none": "", "plain": "\n```", "json": "\n```",
               "opening": "", "closing": "\n```"}
    raw = raw_override if raw_override is not None else (
        helper.AUDIT_MARKER + "\n" + openings[wrapper] +
        json.dumps(value, ensure_ascii=False) + endings[wrapper] + suffix)
    actual = observe(lambda: ns["parse_audit"](raw, "project", allow_partial=partial))
    if actual["kind"] == "return":
        audit = actual["value"]
        try:
            actual["value"] = {"claims": list(audit.claims), "coverage": audit.coverage,
                               "prior_dispositions": list(audit.prior_dispositions),
                               "prior_assessments": list(audit.prior_assessments),
                               "issues": list(audit.issues), "digest": audit.digest,
                               "excerpt": audit.excerpt}
        except (AttributeError, TypeError):
            actual = {"kind": "unexpected", "type": type(audit).__name__, "reason": "not an Audit"}
    fatal = bool(suffix) or wrapper in {"opening", "closing"} or bool(coverage_errors)
    error = structural or fatal or (issues and not partial)
    fragments = ([] if structural else
                 (["unexpected text after"] if suffix or wrapper in {"opening", "closing"} else []) +
                 list(issues) + list(coverage_errors))
    expected = {"kind": "error" if error else "return", "error_fragments": fragments,
                "claims": list(rows), "issues": list(issues)}
    failures, allowed = [], []
    if actual["kind"] != expected["kind"]:
        failures.append("result-kind")
    elif error:
        if actual["type"] != "AuditError":
            failures.append("exception-type")
        reason = actual["reason"]
        if len(reason) > helper.DIAGNOSTIC_CHARS:
            failures.append("diagnostic-bound")
        if any(fragment not in reason for fragment in fragments):
            failures.append("diagnostic-omission")
        # Only incomplete aggregation is an allowed target failure, never an
        # unrelated error, successful invalid return, or discarded error category.
        if len(fragments) > 1 and any(fragment in reason for fragment in fragments):
            allowed.append("diagnostic-omission")
    else:
        result = actual["value"]
        coverage = value["coverage"]
        if digest(result["claims"]) != digest(list(rows)) or digest(result["coverage"]) != digest(coverage):
            failures.append("returned-data")
        if (digest(result["prior_dispositions"]) != digest(coverage["prior_dispositions"]) or
                digest(result["prior_assessments"]) != digest(coverage["prior_assessments"])):
            failures.append("coverage-projection")
        if len(result["issues"]) != len(issues) or any(
                fragment not in message for fragment, message in zip(issues, result["issues"])):
            failures.append("partial-row-diagnostics")
        if result["digest"] != hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest():
            failures.append("input-digest")
    checks.add(name, {"text": raw, "plan_text": "project", "allow_partial": partial},
               expected, actual, failures, allowed)


def _diagnostic(ns, helper, checks):
    valid = {"anchor": "a", "proposition": "project"}
    second = {"anchor": "b", "proposition": "project"}
    coverage = {"prior_dispositions": [], "prior_assessments": []}
    row_cases = [
        ("empty", [], [], []),
        ("valid", [valid, second], [valid, second], []),
        ("fields", [{}], [], ["claim 0:"]),
        ("blank", [{"anchor": " ", "proposition": "project"}], [], ["claim 0:"]),
        ("whole", [{"anchor": "a", "proposition": "whole project"}], [], ["claim 0:"]),
        ("duplicate", [valid, valid], [valid], ["claim 1:"]),
        ("mixed", [valid, {}, second, None], [valid, second], ["claim 1:", "claim 3:"]),
    ]
    coverage_cases = [
        ("valid", coverage, []),
        ("extra", {**coverage, "context": "retained"}, []),
        ("missing-dispositions", {"prior_assessments": []}, ["prior_dispositions"]),
        ("missing-assessments", {"prior_dispositions": []}, ["prior_assessments"]),
        ("missing-both", {}, ["prior_dispositions", "prior_assessments"]),
        ("invalid-dispositions", {**coverage, "prior_dispositions": None}, ["prior_dispositions"]),
        ("invalid-assessments", {**coverage, "prior_assessments": {}}, ["prior_assessments"]),
        ("invalid-both", {"prior_dispositions": None, "prior_assessments": 1},
         ["prior_dispositions", "prior_assessments"]),
    ]
    for name, claims, rows, issues in row_cases:
        for cname, cov, errors in coverage_cases:
            for partial in (False, True):
                for suffix in ("", "\nextra"):
                    _parse_case(ns, helper, checks, f"rows-{name}-{cname}-{partial}-{bool(suffix)}",
                                {"claims": claims, "coverage": cov}, partial=partial, suffix=suffix,
                                rows=rows, issues=issues, coverage_errors=errors)
    for wrapper in ("none", "plain", "json", "opening", "closing"):
        for partial in (False, True):
            _parse_case(ns, helper, checks, f"envelope-{wrapper}-{partial}",
                        {"claims": [valid], "coverage": coverage}, partial=partial,
                        wrapper=wrapper, rows=[valid])
            _parse_case(ns, helper, checks, f"combined-envelope-{wrapper}-{partial}",
                        {"claims": [{}], "coverage": {}}, partial=partial, wrapper=wrapper,
                        issues=["claim 0:"], coverage_errors=["prior_dispositions", "prior_assessments"])
    malformed = ["", "not JSON", helper.AUDIT_MARKER + "\n{", helper.AUDIT_MARKER * 2]
    for i, raw in enumerate(malformed):
        _parse_case(ns, helper, checks, f"malformed-{i}", None, structural=True, raw_override=raw)
    for i, value in enumerate([[], {}, {"claims": [], "coverage": {}, "extra": 1},
                               {"claims": {}, "coverage": {}}, {"claims": [], "coverage": []}]):
        _parse_case(ns, helper, checks, f"shape-{i}", value, structural=True)
    limit = helper.MAX_ACTIVE_CLAIMS
    for count in (0, 1, limit, limit + 1):
        claims = [{"anchor": str(i), "proposition": "project"} for i in range(count)]
        _parse_case(ns, helper, checks, f"count-{count}", {"claims": claims, "coverage": coverage},
                    rows=claims, structural=count > limit)
    # Long source values must not displace any indexed diagnostic. The longest
    # helper error plus index/pointer fits for every admitted row and both coverage errors.
    claims = [{"anchor": str(i), "proposition": "whole " + "界" * 4096} for i in range(limit)]
    for partial in (False, True):
        for fatal in (False, True):
            _parse_case(ns, helper, checks, f"maximum-diagnostic-{partial}-{fatal}",
                        {"claims": claims, "coverage": {} if fatal else coverage},
                        partial=partial, suffix="\nextra" if fatal else "",
                        issues=[f"claim {i}:" for i in range(limit)],
                        coverage_errors=["prior_dispositions", "prior_assessments"] if fatal else [])


def _identity(ns, helper, checks):
    evidence = [{"url": "https://example.test/a", "relation": "supports"},
                {"url": "http://example.test/b", "relation": "refutes"}]
    def row(index=0):
        return {"evidence_index": index, "final_url": evidence[index]["url"],
                "relation": evidence[index]["relation"], "text_sha256": "a" * 64,
                "publisher_authority": True, "passage_entailment": False,
                "authority_reason": "authority", "entailment_reason": "passage"}
    cases = [("empty", [], False, False), ("first", [row()], False, False),
             ("last", [row(1)], False, False), ("all", [row(1), row()], False, False)]
    for index in (True, False, -1, 2, 0.0, "0", None, [], {}):
        value = row(1 if index is True else 0)
        value["evidence_index"] = index
        cases.append(("index-" + json.dumps(index), [value], True, type(index) is bool))
    cases += [("duplicate", [row(), row()], True, False),
              ("too-many", [row(), row(1), row()], True, False)]
    for value in (None, {}, "rows", 1, True):
        cases.append(("outer-" + json.dumps(value), value, True, False))
        cases.append(("row-" + json.dumps(value), [value], True, False))
    for field in row():
        value = row(); value.pop(field)
        cases.append(("missing-" + field, [value], True, False))
    cases.append(("extra", [{**row(), "extra": 1}], True, False))
    for field, values in [
        ("final_url", ["ftp://example.test/a", "/relative", "https:///missing", "http://[",
                       evidence[1]["url"], "", " ", "\n", None, 1, []]),
        ("relation", ["other", "", " ", "\n", None, 1]),
        ("text_sha256", ["A"*64, "a"*63, "a"*65, "g"*64, "", " ", None, 1]),
        ("publisher_authority", [1, 0, "true", None, [], {}]),
        ("passage_entailment", [1, 0, "false", None, [], {}]),
        ("authority_reason", ["", " ", "\t", "\u2003", "\n", "a\rb", None, 1, []]),
        ("entailment_reason", ["", " ", "\t", "\u2003", "\r", "a\nb", None, 1, []]),
    ]:
        for i, value in enumerate(values):
            cases.append((f"field-{field}-{i}", [{**row(), field: value}], True, False))
    for i, text in enumerate(("文", " a ", "a\u2028b", "a\x00b")):
        cases.append((f"unicode-{i}", [{**row(), "authority_reason": text,
                                     "entailment_reason": text}], False, False))
    for authority in (False, True):
        for entailment in (False, True):
            cases.append((f"flags-{authority}-{entailment}",
                          [{**row(), "publisher_authority": authority,
                            "passage_entailment": entailment}], False, False))
    for name, value, invalid, target in cases:
        original = deepcopy(value)
        actual = observe(lambda: ns["_validate_capture_attestations"](value, evidence))
        expected = {"kind": "error"} if invalid else {"kind": "return", "value": value}
        failures = []
        if actual["kind"] != expected["kind"]:
            failures.append("boolean-identity" if target else "result-kind")
        elif not invalid and digest(actual["value"]) != digest(expected["value"]):
            failures.append("returned-data")
        if invalid and actual["kind"] == "error" and actual["type"] != "ValueError":
            failures.append("exception-type")
        if digest(value) != digest(original):
            failures.append("input-mutation")
        checks.add(name, {"value": original, "evidence": evidence}, expected, actual, failures,
                   ("boolean-identity",) if target else ())
    ftp = [{"url": "ftp://example.test/a", "relation": "supports"}]
    value = [{**row(), "final_url": ftp[0]["url"]}]
    actual = observe(lambda: ns["_validate_capture_attestations"](value, ftp))
    checks.add("historical-ftp-domain-observation", {"value": value, "evidence": ftp},
               {"contract": "outside caller-enforced evidence domain; no acceptance promise"},
               actual, [], domain="outside")


def calibrate(family, files, defective):
    checks = Checks(family, defective)
    with fixture(files) as (ns, helper):
        {"overlap": _overlap, "reserve": _reserve,
         "diagnostic": _diagnostic, "identity": _identity}[family](ns, helper, checks)
    return checks.finish(files)
