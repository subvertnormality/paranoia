#!/usr/bin/env python3
"""Run the bounded mutation gate for Protocol v2's trusted materializer.

Each mutation removes or reverses one load-bearing control.  The focused test
named beside it must fail against the mutated copy.  This is intentionally a
small deterministic release gate, not an unbounded whole-repository campaign.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "paranoia_local" / "staged_protocol.py"
TEST = "tests/test_staged_protocol.py"
DIFFERENTIAL_TESTS = (
    "test_frozen_historical_v1_census_projection_is_preserved",
    "test_frozen_historical_v1_correction_projection_is_preserved",
    "test_frozen_historical_v1_final_projection_is_preserved",
    "test_historical_v1_v2_branch_transition_shapes_are_equivalent",
    "test_historical_v1_v2_open_unbound_debt_shape_is_equivalent",
    "test_historical_v1_v2_census_fanout_shape_is_equivalent",
    "test_historical_v1_v2_remaining_legal_shape_matrix_is_equivalent",
)

MUTATIONS = (
    (
        "coverage-binding",
        "if referenced != set(findings):",
        "if False:",
        "test_lane_dynamic_completeness_and_binding",
    ),
    (
        "severity-floor",
        '_rank(finding["severity"]) < _rank(severity)',
        '_rank(finding["severity"]) >= _rank(severity)',
        "test_source_severity_cannot_be_downgraded",
    ),
    (
        "literal-pathspec",
        'value["pattern"] = r"^[^:\\r\\n][^\\r\\n]*$"',
        'value["pattern"] = r"^[^\\r\\n]+$"',
        "test_branch_schema_rejects_git_pathspec_magic_for_new_and_replacement_classes",
    ),
    (
        "debt-completeness",
        "if set(debt_outcomes) != set(open_debt):",
        "if False:",
        "test_class_and_debt_outcome_completeness_are_independent_controls",
    ),
    (
        "mechanized-replacement",
        'and "pattern" not in action["definition"]',
        "and False",
        "test_closed_mechanized_class_cannot_be_replaced_by_manual_procedure",
    ),
    (
        "standalone-action",
        'elif action["kind"] not in {"close", "replace"}:',
        'elif action["kind"] not in {"close"}:',
        "test_satisfied_open_class_preserves_compatible_standalone_action",
    ),
    (
        "derived-close",
        'if action is None or action["kind"] == "reclassify":\n                derived_actions.append((\n                    {"kind": "close", "class_id": cid}, outcome_pointer,',
        'if False:\n                derived_actions.append((\n                    {"kind": "close", "class_id": cid}, outcome_pointer,',
        "test_satisfied_open_unmechanized_class_derives_close",
    ),
    (
        "advisory-class-debt",
        'if finding["severity"] in BLOCKING\n        or (',
        'if finding["severity"] in BLOCKING\n        and (',
        "test_census_existing_advisory_violation_still_mints_debt",
    ),
    (
        "census-schema-exclusion",
        'if role != "census":\n        if canonical:',
        'if True:\n        if canonical:',
        "test_census_schema_rejects_authored_class_outcomes",
    ),
    (
        "mechanized-lane-compatibility",
        'and cls.get("mechanized") is True',
        "and False",
        "test_integrity_lane_rejects_satisfied_unproven_mechanized_class",
    ),
    (
        "census-governing-cardinality",
        "if len(matches) != 1:",
        "if False:",
        "test_census_violated_class_requires_one_matching_governing_finding",
    ),
    (
        "census-verdict-projection",
        '"class_id": cid, "verdict": verdict, "evidence": evidence,',
        '"class_id": cid, "verdict": "satisfied", "evidence": evidence,',
        "test_census_derives_exact_verdict_evidence_and_basis",
    ),
    (
        "census-evidence-projection",
        '"class_id": cid, "verdict": verdict, "evidence": evidence,',
        '"class_id": cid, "verdict": verdict, "evidence": list(reversed(evidence)),',
        "test_census_derives_exact_verdict_evidence_and_basis",
    ),
    (
        "integrity-assessment-completeness",
        "if set(assessments) != expected:",
        "if False:",
        "test_integrity_lane_requires_every_active_class_assessment",
    ),
    (
        "duplicate-class-key-detection",
        "if key in result:",
        "if False:",
        "test_duplicate_class_decision_keys_reject_before_projection",
    ),
    (
        "keyed-outcome-completeness",
        "required=outcome_ids,",
        "required=(),",
        "test_keyed_decision_schema_exposes_only_role_legal_class_decisions",
    ),
    (
        "mechanized-action-specialization",
        'if cls.get("mechanized", False)\n                        else "#/$defs/manual_class_action"',
        'if False\n                        else "#/$defs/manual_class_action"',
        "test_keyed_decision_schema_exposes_only_role_legal_class_decisions",
    ),
    (
        "decision-encounter-order",
        "for class_id, body in rows.items()",
        "for class_id, body in sorted(rows.items())",
        "test_keyed_decision_projection_preserves_encounter_order",
    ),
    (
        "keyed-action-diagnostic-pointer",
        'action_pointers = _class_row_pointers(value, "class_actions")\n    actions = _unique(',
        'action_pointers = {\n        row["class_id"]: f"/class_actions/{index}"\n        for index, row in enumerate(value["class_actions"])\n    }\n    actions = _unique(',
        "test_keyed_decision_semantic_issue_retains_late_wire_key_pointer",
    ),
    (
        "canonical-keyed-diagnostic-pointer",
        "issues = wire_issues + _remap_class_schema_issues(canonical, issues)",
        "issues = wire_issues + issues",
        "test_keyed_decision_canonical_issue_retains_wire_key_pointer",
    ),
    (
        "null-action-slot-pointer",
        '_class_slot_pointer(value, "class_actions", cid)\n                    if action is None',
        '"/class_actions"\n                    if action is None',
        "test_census_closed_violation_derives_only_unmechanized_reopen",
    ),
    (
        "fallback-action-pointer",
        'action_pointers[action["class_id"]] for action in value["class_actions"]',
        'f"/class_actions/{index}" for index, action in enumerate(value["class_actions"])',
        "test_keyed_decision_semantic_issue_retains_late_wire_key_pointer",
    ),
    (
        "derived-correction-violation",
        "if cid not in authored_classes:",
        "if False:",
        "test_correction_projects_non_debt_assessment_evidence_into_finding",
    ),
    (
        "exact-empty-active-targets",
        "if active_classes is not None:",
        "if active_classes:",
        "test_exact_empty_active_set_cannot_target_an_existing_class",
    ),
    (
        "unmechanized-to-mechanized-replacement",
        'mode, mechanized=True if cls.get("mechanized", False) else None,',
        'mode, mechanized=bool(cls.get("mechanized", False)),',
        "test_unmechanized_class_can_be_replaced_by_a_mechanized_successor",
    ),
)

CROSS_MODULE_MUTATIONS = (
    (
        SOURCE, TEST, "citation-closed-wire-shape",
        '"rationale": _string(MAX_RATIONALE_CHARS),',
        '"rationale": {},',
        "test_citation_rationale_bound_applies_to_every_evidence_shape",
    ),
    (
        SOURCE, TEST, "citation-exact-projection",
        'node[key] = [citation["anchor"] for citation in child]',
        'node[key] = [citation["rationale"] for citation in child]',
        "test_wire_citations_are_closed_and_project_exactly_to_canonical_anchors",
    ),
    (
        SOURCE, TEST, "canonical-citation-uniqueness",
        'maximum=100, minimum=1, unique=canonical,',
        'maximum=100, minimum=1, unique=False,',
        "test_duplicate_wire_citations_reach_canonical_aggregate_validation",
    ),
    (
        SOURCE, "tests/test_review_census.py", "canonical-cache-shape",
        'text, lane_schema(mode, lane, canonical=True),',
        'text, lane_schema(mode, lane),',
        "test_census_cache_requires_every_exact_binding",
    ),
    (
        ROOT / "src" / "paranoia_local" / "review_census.py",
        "tests/test_review_census.py", "citation-cache-version",
        "CENSUS_CACHE_VERSION = 4", "CENSUS_CACHE_VERSION = 3",
        "test_census_cache_requires_every_exact_binding",
    ),
    (
        ROOT / "src" / "paranoia_local" / "handlers.py",
        "tests/test_review_census.py", "member-cache-inventory-binding",
        '"active_classes_digest":rc.digest(canonical_classes),',
        '"active_classes_digest":rc.digest("[]"),',
        "test_census_cache_requires_every_exact_binding",
    ),
    (
        ROOT / "src" / "paranoia_local" / "handlers.py",
        "tests/test_review_census.py", "received-member-cache-equality",
        "or set(members) != set(expected[class_id])",
        "or False",
        "test_census_cache_requires_every_exact_binding",
    ),
    (
        ROOT / "src" / "paranoia_local" / "review_census.py",
        "tests/test_review_census.py", "assessment-anchor-walk",
        'if key in {"evidence", "assessment_evidence"} and isinstance(child, list):',
        'if key == "evidence" and isinstance(child, list):',
        "test_assessment_evidence_uses_the_shared_anchor_resolver",
    ),
)



def assertion_kill(returncode: int, report: str) -> bool:
    """Only an executed assertion failure counts; pytest infrastructure errors do not."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(report)
    except ET.ParseError:
        return False
    cases = list(root.iter("testcase"))
    failures = [failure for case in cases for failure in case.findall("failure")]
    return (
        returncode == 1 and bool(cases) and bool(failures)
        and not list(root.iter("error")) and not list(root.iter("skipped"))
        and all(
            failure.get("message", "").startswith("AssertionError")
            or "DID NOT RAISE" in failure.get("message", "")
            for failure in failures
        )
    )


def exercise(package_root: Path, source: Path, test: str, test_name: str):
    """Prove both an executed source location and the selected pytest outcome."""
    import json
    with TemporaryDirectory(prefix="paranoia-mutation-probe-") as directory:
        probe_root = Path(directory)
        report = probe_root / "result.xml"
        hit_file = probe_root / "hits.json"
        plugin = probe_root / "paranoia_mutation_probe.py"
        plugin.write_text(
            "import sys, threading, json\n"
            f"TARGET = {str(source)!r}\n"
            "hits = set()\n"
            "def trace(frame, event, arg):\n"
            "    if frame.f_code.co_filename != TARGET: return None\n"
            "    if event == 'line': hits.add(frame.f_lineno)\n"
            "    return trace\n"
            "def pytest_sessionstart(session):\n"
            "    sys.settrace(trace); threading.settrace(trace)\n"
            "def pytest_sessionfinish(session, exitstatus):\n"
            "    sys.settrace(None); threading.settrace(None)\n"
            f"    open({str(hit_file)!r}, 'w').write(json.dumps(sorted(hits)))\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join((
            str(probe_root), str(package_root), str(ROOT), env.get("PYTHONPATH", ""),
        ))
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-c", "/dev/null",
             "-p", "paranoia_mutation_probe", f"--junitxml={report}",
             f"{ROOT / test}::{test_name}"],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False,
        )
        return (
            completed,
            report.read_text() if report.exists() else "",
            set(json.loads(hit_file.read_text())) if hit_file.exists() else set(),
        )

def main() -> int:
    source_env = dict(os.environ)
    source_env["PYTHONPATH"] = os.pathsep.join((
        str(ROOT / "src"), str(ROOT), source_env.get("PYTHONPATH", ""),
    ))
    differential = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-c", "/dev/null",
            *(f"{ROOT / TEST}::{name}" for name in DIFFERENTIAL_TESTS),
        ],
        cwd=ROOT, env=source_env, capture_output=True, text=True, check=False,
    )
    if differential.returncode:
        print("Historical V1/V2 differential gate failed.", file=sys.stderr)
        print(differential.stdout, file=sys.stderr)
        print(differential.stderr, file=sys.stderr)
        return 1
    print(
        f"Historical V1/V2 differential gate passed for "
        f"{len(DIFFERENTIAL_TESTS)} role/shape groups."
    )
    mutations = [
        (SOURCE, TEST, name, before, after, test_name)
        for name, before, after, test_name in MUTATIONS
    ] + list(CROSS_MODULE_MUTATIONS)
    failures: list[str] = []
    for source, test, name, before, after, test_name in mutations:
        original = source.read_text(encoding="utf-8")
        if original.count(before) != 1:
            failures.append(f"{name}: source target count is {original.count(before)}, expected 1")
            continue
        with TemporaryDirectory(prefix=f"paranoia-mutant-{name}-") as directory:
            package_root = Path(directory)
            shutil.copytree(ROOT / "src" / "paranoia_local", package_root / "paranoia_local")
            target = package_root / "paranoia_local" / source.name
            target.write_text(original.replace(before, after), encoding="utf-8")
            baseline, baseline_xml, baseline_hits = exercise(
                ROOT / "src", source, test, test_name,
            )
            line = original[:original.index(before)].count("\n") + 1
            if baseline.returncode != 0 or not baseline_hits:
                failures.append(f"{name}: selected baseline failed or source was not exercised\n{baseline.stdout[-1500:]}")
                continue
            completed, report, hits = exercise(package_root, target, test, test_name)
            changed_lines = set(range(line, line + len(after.splitlines())))
            if not changed_lines & hits:
                failures.append(f"{name}: intended mutation was not exercised")
            elif not assertion_kill(completed.returncode, report):
                failures.append(f"{name}: survived or failed outside an expected test assertion\n{completed.stdout[-1500:]}")
            else:
                print(f"KILLED {name} by {test_name}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"All {len(mutations)} owned Protocol v2 mutants were killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
