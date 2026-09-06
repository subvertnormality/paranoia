# Census execution and maintenance

## Conditional consolidation
Every staged census runs the same three independent reviewers with their full prompts,
schemas, evidence checks, model and effort. A valid cached census retains its existing
bound reuse rules.

Only a complete, validated census containing no findings of any severity and no class
assessments can use server-empty-census consolidation. The authoritative incoming state,
captured after load validation and before normalization or sweeps, must contain no
classes (including closed or superseded), legacy register debt, structural debt (including
closed/advisory), format debt, validation debt, staged failure or census cache. The
normalized current state must still satisfy these exclusions. Missing or duplicate lanes
cannot qualify. This is an incoming-state rule, not a new lifetime history register.

The server constructs the empty decision and sends it through the ordinary decoder,
materializer, anchor validation, class-engine dry-run and atomic settlement. It replaces
only a manifest-only call with no remaining finding, debt or class decision. All nonempty
cases retain model consolidation and its existing single correction. Correction and
independent cold final are unchanged. External claim debt still blocks combined plan
clearance. A failed save never establishes clearance.

The returned footer identifies server-empty-census and the actual lane engine, without
offering a consolidation session for rebut. The top-level audit records
review_origin=server-empty-census and null provider-only process/session/usage/duration
fields. Its attempt ledger retains every actual lane/retry observation; the server
transition is not counted as a provider call. Local rejection and ambiguous persistence
keep the same provenance and fail closed.

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
projects the validated observations once for settlement. EmptyCensusHistory contains only
immutable exclusion facts; it is not durable state or a second source of authority.

For a lane scheduling change, start with tests/test_census_execution.py and parallel
failure tests in tests/test_review_census.py. For eligibility or reporting, start with
tests/test_empty_census.py. For settlement or lifecycle changes, retain the public
census-correction-final regression in tests/test_review_census.py and the canonical
protocol tests. Larger parsers and other handlers remain separate future extraction
targets; this change does not resolve their complexity.

## Reproduce the measurements
Run scripts/measure_review_complexity.py with --revision 9336ce3 for the baseline, or
without --revision for the working tree. --output writes the complete JSON inventory.
The retained baseline is census_complexity_baseline.json. The metric counts inclusive
Python AST branch constructs and Boolean alternatives; it is a navigation aid, not formal
cyclomatic complexity or a guarantee that a particular LLM can maintain the package.

Before the change, _staged_structural_review occupied 748 lines with proxy 154.
The current extraction and empty path occupy 631 lines with proxy 108; final acceptance
must remeasure this rather than copy these numbers if the implementation changes.
The performance claim is conditional: one fewer provider call on a qualifying census.
Actual elapsed time, outcomes and qualified sample counts require live acceptance.
