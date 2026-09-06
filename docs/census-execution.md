# Census execution and maintenance

## Current behavior
Every staged census runs three independent reviewers with full prompts, schemas, evidence
checks, model and effort, followed by model consolidation. A valid cached census retains
its existing bound reuse rules. Correction and independent cold final are unchanged.

The proposed server-empty-census optimization was tested and withheld under the
[frozen plan](census-execution-plan.md). Both Claude candidate clean pairs retained
advisory findings and did not exercise the required path. See the
[complete experiment report](empty-census-benchmark-2026-09-06.md). Current production
code has no empty-census shortcut or server-consolidation provenance variant.

## Maintenance map
| Concern | Owner |
| --- | --- |
| Public inputs, snapshot/contract authority, provider policy and atomic settlement | handlers.py |
| Complete parallel census result, ordering and failure aggregation | census_execution.py |
| Fresh wire schema, canonical projection and semantic materialization | staged_protocol.py |
| Durable structural state, debt, cache contracts and verdict rendering | review_census.py |
| Class lifecycle and predicate execution | class_closure.py |
| Pure phase selection and final ownership | review_transitions.py |
| Provider subprocess protocol | engines.py and runner.py |

LaneResult and CensusResult replace positional tuple indexing. A lane callback in the
handler owns invocation and validation; collect joins all admitted lanes before returning
or raising. Do not add provider options or persistence inside the coordinator. CensusSources
projects the validated observations once for settlement.

For a lane scheduling change, start with tests/test_census_execution.py and parallel
failure tests in tests/test_review_census.py. For settlement or lifecycle changes, retain the public
census-correction-final regression in tests/test_review_census.py and the canonical
protocol tests. Larger parsers and other handlers remain separate future extraction
targets; this change does not resolve their complexity.

## Reproduce the measurements
Run scripts/measure_review_complexity.py with --revision 9336ce3 for the baseline, or
without --revision for the working tree. --output writes the complete JSON inventory.
The retained baseline is census_complexity_baseline.json. The metric counts inclusive
Python AST branch constructs and Boolean alternatives; it is a navigation aid, not formal
cyclomatic complexity or a guarantee that a particular LLM can maintain the package.

Before extraction, _staged_structural_review occupied 748 lines with proxy 154.
The delivered extraction occupies 636 lines with proxy 106; new census coordinator
functions are at most 28 lines. Remeasure if implementation changes. No performance
speedup is claimed for this extraction; its purpose is a smaller, typed maintenance boundary.
