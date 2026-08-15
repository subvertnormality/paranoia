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
    "test_historical_v1_v2_standalone_close_reopen_are_equivalent",
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
        "outcome-completeness",
        "if set(outcomes) != expected_model_classes:",
        "if False:",
        "test_class_and_debt_outcome_completeness_are_independent_controls",
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
        '{"close", "reclassify", "replace"}',
        '{"close"}',
        "test_satisfied_open_class_preserves_compatible_standalone_action",
    ),
    (
        "derived-close",
        "if action is None:\n                actions[cid] = {\"kind\": \"close\", \"class_id\": cid}",
        "if False:\n                actions[cid] = {\"kind\": \"close\", \"class_id\": cid}",
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
        'if role != "census":\n        properties["class_outcomes"]',
        'if True:\n        properties["class_outcomes"]',
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
        "census-assessment-completeness",
        "for cid, verdict in (assessment_verdicts or {}).items():",
        "for cid, verdict in list((assessment_verdicts or {}).items())[:1]:",
        "test_source_fanout_requires_distinct_cited_existing_classes",
    ),
)


def main() -> int:
    differential = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-c", "/dev/null",
            *(f"{ROOT / TEST}::{name}" for name in DIFFERENTIAL_TESTS),
        ],
        cwd=ROOT, capture_output=True, text=True, check=False,
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
    original = SOURCE.read_text(encoding="utf-8")
    failures: list[str] = []
    for name, before, after, test_name in MUTATIONS:
        if original.count(before) != 1:
            failures.append(f"{name}: source target count is {original.count(before)}, expected 1")
            continue
        with TemporaryDirectory(prefix=f"paranoia-mutant-{name}-") as directory:
            package_root = Path(directory)
            shutil.copytree(ROOT / "src" / "paranoia_local", package_root / "paranoia_local")
            target = package_root / "paranoia_local" / "staged_protocol.py"
            target.write_text(original.replace(before, after), encoding="utf-8")
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join((
                str(package_root), str(ROOT), env.get("PYTHONPATH", ""),
            ))
            completed = subprocess.run(
                [
                    sys.executable, "-m", "pytest", "-q", "-c", "/dev/null",
                    f"{ROOT / TEST}::{test_name}",
                ],
                cwd=ROOT, env=env, capture_output=True, text=True, check=False,
            )
            if completed.returncode == 0:
                failures.append(f"{name}: survived {test_name}")
            else:
                print(f"KILLED {name} by {test_name}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"All {len(MUTATIONS)} owned Protocol v2 mutants were killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
