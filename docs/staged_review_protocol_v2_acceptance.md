# Staged review Protocol v2 implementation acceptance

Status: **CODE round-5 held finding repaired; correction and cold-final convergence pending**

This report records the artifacts that exist for the implementation of
[`staged_review_protocol_v2_plan.md`](staged_review_protocol_v2_plan.md). It does not claim
that structured output improves reviewer judgement, that every provider version supports the
schemas, or that the subsequent code review has converged.

## Frozen operating model

One trusted operator runs the local tool on a trusted OS. Plans, repository snapshots, and model
output are untrusted static data; the inert review workspace does not execute repository-selected
code. A cold census has three concurrent lanes and one consolidation, with correction and final as
single calls. False clearance, lost identity, severity downgrade, and wrong evidence binding are
high impact; visible recoverable blocking is acceptable. Hostile local races, multitenancy,
compromised OS/provider behavior, formal proof, and corrupted-state recovery are excluded.

## Provider capability evidence

The pinned command profiles retained their existing tool/network restrictions. Both providers
received the same deterministic provider projection; the server retained and applied the complete
Draft 2020-12 schema independently.

| Provider | Evidence actually observed |
|---|---|
| Codex | Fresh and resumed minimal objects returned structured JSON. Exact production lane and census-decision schemas returned structured objects in sessions `019ffc6b-c700-7de1-8307-63b5a9f36cac` and `019ffc71-9f7b-7c31-8813-cfab1a85f805`. A full schema containing `uniqueItems` failed explicitly with `invalid_json_schema`, proving it was not silently ignored. |
| Claude | Fresh and resumed minimal objects returned `structured_output` in session `99654842-8875-4335-998f-516202b4c43d`. The exact production lane schema returned `structured_output` in session `93f031db-2577-4959-bce1-66d85f33f90f`. A probe retaining `$schema` returned ordinary prose and no `structured_output`, so `$schema` and Codex-unsupported `uniqueItems` are removed from the common provider projection; no other bound was removed. |

The local schema still enforces uniqueness, exact key closure, length/count bounds, enums, tagged
unions, and the single-anchor grammar. The engine now also treats a Claude response as failed when
a schema was requested but the provider envelope lacks an object-valued `structured_output`; result
prose cannot enter local settlement validation. Fresh and resumed negative tests cover absent and
non-object structured output.

The real lifecycle's largest retained response was 3,265 characters for a lane and 3,140 for a
decision. The executable pre-decode limits are now role-specific: 240,000 characters per lane and
1,000,000 per decision. Three maximum lane replies, a separately bounded 200,000-character static
context, and 50,000 characters of instruction/envelope reserve fit the 1,000,000-character
consolidation circuit breaker. These are failure-cost bounds with substantial measured headroom,
not review-quality budgets.

## Real Codex primary lifecycle

The disposable repository contained one pure Python function, its README contract, and one test.
Round 1 intentionally contradicted all three. Claim verification and web search were disabled so
this exercised only the primary staged structural path. Model `gpt-5.6-sol`, effort `medium`.

| Invocation | Artifact result | Audit SHA-256 |
|---|---|---|
| 1, census + consolidation | One BLOCKER, one new class, one open debt; correction required | `a20c01e47dbafc815390cf760f9f799bad7fc4558a2cb0fcf72e0e7f70b15dd8` |
| 2, correction | Contradiction class closed; reviewer incorrectly read from workspace root and opened one-off missing-repository debt | `ebe1123a653259ddbc5e358a1c3599cf29221f2b2bad82243969f26ce9922b55` |
| 3, correction | Files were read through `repository/`, but a sentence containing several citations was rejected atomically on both attempts | `24d99f7746d90c0a183d16607495f23fd40c307209f0b994ed91ae9dcb49b604` |
| 4, correction | After provider-constraining one evidence item to one anchor, the one-off debt closed; final required | `83d1bff523d6df714a3760b72caaf3343bdd68cad1bf3be5ae78bcaa5a1ef9a4` |
| 5, cold final | Reopened the existing class for an omitted function-docstring update | `483aba8700c501c540882dc24d48cbd01c2b321f1d1dd747ad3e3e88f8cb255b` |
| 6, correction | Accepted the docstring correction, closed the class/debt; final required | `f87029156c015b19d002d08042df64ff2d40e489a9edaaa798c11c80422416ec` |
| 7, cold final | `CONVERGENCE: NOT-BLOCKED`; zero blocking debt, class closed | `e65257e45c6095db2f19042c8343b67149d8f4cb8587723fd00b3bd8633e7637` |

The seven invocations made 13 model attempts: four initial census/consolidation attempts, six
ordinary correction/final attempts, and three same-session validation attempts. Audit usage totals
were 511,127 input tokens (317,696 cached), 18,313 output tokens, and 7,418 reasoning tokens. The
observable provider wall time was approximately 274 seconds; elapsed operator time including the
two coherent fixes and reruns was 453 seconds. No new model phase or retry was added by V2.

The final durable state is phase `clear`, three historical debts all `closed`, and class `b930c221`
`closed`. The rejected delimiter round did not increment durable rounds or apply either attempted
payload.

## Automated verification

The current complete collection ran with global and system Git configuration disabled so fixture
commits did not inherit the operator's signing key: **988 passed in 62.52 seconds**. An initial
unisolated invocation reached 931 passes and then failed only when 56 Git fixtures attempted signed
commits without an available askpass helper; it is not counted as a product result. The bounded
historical differential plus nine-mutation gate also passed, focused V2/staged-census tests passed
independently, and `git diff --check` is clean.

After the first CODE census, focused gates cover the accepted findings:

- a test-only executable reference for the V1 settlement relationships at `83fc1e6` consumes the
  redundant V1 tables independently of the V2 materializer. The bounded differential gate compares
  census, correction, final, branch reopen, mechanized replacement, open unbound debt, and census
  fan-out through durable phase, debt, class state, trailer, and the documented fresh-ID bijection;
- the existing legal-shape suite covers one-off/new/existing classes, plan procedure and branch
  procedure/pattern definitions, advisory class debt, fan-out, carried debt, action kinds, severity,
  and closure/reopen behavior. This is an enumerated compatibility corpus, not proof about every
  historical model payload;
- `scripts/run_staged_protocol_mutation_checks.py` owns nine enumerated mutations: coverage binding,
  occurrence severity floor, literal pathspec, class/debt completeness, mechanized replacement,
  standalone actions, derived close, and advisory violated-class debt. All nine are killed by named
  focused tests. This is a bounded gate over those controls, not a claim that every possible mutant
  or every historical model payload was exercised.

## CODE review checkpoint

Codex CODE round 1 (CLI 0.144.6, `gpt-5.6-sol`, high effort, web disabled) reviewed committed
snapshot `edc5c8a` against `main` under the frozen stakes. It opened seven blocking classes:
provider-envelope fallback; Git pathspec magic; mechanized-to-manual replacement; compatible
standalone class actions; first-error-only semantic diagnostics; census aggregate capacity; and
missing executable historical/mutation gates. The implementation treats all seven as accepted.

One coherent contract-completion pass now fails Claude schema calls closed, rejects pathspec magic,
preserves mechanization on replacement, permits compatible reclassify/replace actions beside a
satisfied outcome, accumulates independent semantic issues, admits the calculated 300-source plus
100-active-class census bound, and adds the narrowly described differential/mutation evidence.
No provider call, retry, phase, persistence format, trust boundary, or subsystem was added.

CODE round 2 closed the provider-envelope class and retained six blocking classes because the
first correction's tests stopped at schema/materializer boundaries and anchor/class diagnostics
still returned one error at a time. The second checkpoint pass adds a tracked-branch fresh/retry
rejection test for pathspec magic; sends valid mechanized replacement and standalone action/debt
closure through the canonical class engine and durable settlement; compares frozen V1 and V2
projections through durable phase, debt, class state, trailer, and explicit fresh-ID normalization;
materializes 150 sources drawn from all three lane namespaces; and accumulates independent anchor
and canonical-action faults with model-owned pointers. Derived mirror debt is omitted from anchor
diagnostics so retry pointers remain repairable. Five-million-character lane/decision pre-decode
caps and non-whitespace semantic strings close the two advisory observations without adding a call.

The first attempt to run CODE round 3 never reached review: Codex rejected the initial
non-whitespace schema expression because its provider dialect does not support regex lookaround.
The failure was recorded as execution failure, did not increment lineage rounds, and settled no
debt or class. The expression was replaced with the equivalent lookaround-free
`^[^\\r\\n]*\\S[^\\r\\n]*$`; the provider projection is regression-tested to contain no
lookaround before the same round is retried.

The resumed CODE round 3 closed pathspec, mechanized replacement, standalone action, and
non-whitespace classes. It retained three blocking assurance classes and the response-size
advisory: the historical comparisons did not execute a V1 validator; semantic, anchor, and class
validation still stopped between layers; and the 150-source fixture bypassed real consolidation.
The bounded correction now executes the V1 relationship reference before all nine owned mutants,
combines independently detectable semantic/anchor/canonical errors into one stable-pointer retry,
and sends 150 independent sources through all three real lane parsers and consolidation. The
measured response limits and visible persisted oversize-failure tests address the advisory without
adding a phase or retry.

CODE round 4 closed the aggregate-capacity class and response-limit advisory. It retained the
historical gate because three later fixtures copied their V1 side from the V2 materialization, and
retained cross-layer diagnostics because the semantic-failure fallback extracted explicit actions
but not embedded new-class definitions. The V1 fixtures are now independently authored for every
group. The seven-group executable matrix covers census, correction, final, one-off/new/existing
classification, plan and branch procedure definitions, branch patterns, open/closed debt outcomes,
satisfied and both violated-outcome bases, all action kinds, advisory debt, fan-out, and replacement
mechanization. The fallback now extracts both embedded definitions and explicit actions; a terminal
retry test combines graph debt-completeness, two bad anchors, an unknown action, and a new-class
attempt against the canonical 100-class cap in one bounded pointer diagnostic.

CODE round 5 closed the historical-equivalence class. It retained one exact cross-layer case:
canonical aggregate validation was skipped when any individual record was invalid, so at 99 active
classes two individually valid new definitions plus one independently invalid action omitted the
combined cap failure. Canonical validation now always runs the individually valid subset as a set;
the same terminal retry regression proves the invalid action and aggregate cap failure are both
reported without applying either.

## Size and architecture checkpoint

The pre-review checkpoint covered `handlers.py`, `review_census.py`, `prompts.py`, `engines.py`, and
`staged_protocol.py` at +198 net lines. CODE round 1 then triggered the documented architecture
checkpoint rather than another open-ended patch loop. The accepted completion pass moves those five
modules to **+459 net lines** and current sizes 2,760, 450, 501, 616, and 863 lines. The increase is
bounded cross-layer issue accumulation, provider-envelope closure, and coherent packet limits;
the larger differential and mutation evidence lives in tests/scripts rather than production.
There is still no new subsystem, and the largest existing handler was not expanded by this pass.
Across all production Python and dependency-manifest changes the current diff is **+479 net lines**;
the remaining 20 lines are the independent arbitration fence-helper relocation, existing numbering
helper change, and dependency declaration already described above.

The model-facing top-level settlement relationships fall from seven mirrored tables to four
semantic tables. There is no new persistence layer, model phase, provider call, trust boundary, or
durable V1 fallback. Cache protocol version is 2; durable lineage format remains version 1.
