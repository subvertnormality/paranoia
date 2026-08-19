# Staged review Protocol v2 implementation acceptance

Status: **Protocol v2 shipped. The keyed class-decision amendment for issue #42 passed its external
provider capability gate and is undergoing its CODE-convergence gate.**

This report records the artifacts that exist for the implementation of
[`staged_review_protocol_v2_plan.md`](staged_review_protocol_v2_plan.md). It does not claim
that structured output improves reviewer judgement, that every provider version supports the
schemas, or that a subsequent code review has converged merely because this report exists.

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
| Claude | Fresh and resumed minimal objects returned `structured_output` in session `99654842-8875-4335-998f-516202b4c43d`. The exact production plan/domain lane schema and response are retained from session `dc5dd7c9-a8fe-4978-bc65-d7ec5b96679c`. Exact production census and final decision schemas materialized in sessions `805533c1-241a-4917-b3a0-de983fafe63d` and `f1cb1870-f62e-4368-8f4e-3dbd6f52e75b`; correction completed a real same-session validation retry in `f9ab6c74-ca5c-4fc0-a7b9-f61cbe18b795`. A probe retaining `$schema` returned ordinary prose and no `structured_output`, so `$schema` and Codex-unsupported `uniqueItems` are removed from the common provider projection; no other bound was removed. |

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

The Claude decision probes used pinned CLI `2.1.197`, explicit model alias `sonnet`, high effort,
and web disabled. Provider-schema SHA-256 values were `58f614ba…c01ab` (census),
`4d3b30f0…49d1c` (correction), and `52b01f64…1925` (final); retained response hashes were
`2b3b8df7…59144`, `6cf6179d…124a`, and `5ae606ea…425`. The correction attempt ledger was exactly
`correction: validation-invalid` then `correction-validation-retry: completed`. The configured
default Fable model was also attempted and explicitly refused the call because the account had no
remaining Fable usage credits; this report therefore establishes the Claude engine/CLI path with
the available explicit `sonnet` model and makes no current Fable-lifecycle claim.

The machine-readable
[`staged_review_protocol_v2_claude_acceptance.json`](staged_review_protocol_v2_claude_acceptance.json)
retains the full schema/response hashes, exact probe response objects, retry roles/outcomes,
lifecycle round/plan/audit/response hashes, attempt durations and costs, state transitions, final
state hash, and the Fable rejection. A test regenerates every exact production provider schema,
re-hashes and locally materializes every retained response, and validates the complete attempt and
state sequence. The artifact is intentionally a bounded acceptance projection, not a claim that
the external provider transcript can be replayed offline.

The retained lane probe binds provider-schema SHA-256
`d871043c9de3ddff4cf33c6839d3111354d8891c32e632e06fd52828fc4f6655` to exact response
SHA-256 `d683a2d0a1897d186c2b4076dc4c2ebfe25d5af9aab00e2bc53dfa6d83705a81`;
the executable test regenerates `lane_schema("plan", "domain")`, re-hashes the compact response,
and parses it through the production lane validator.

## Keyed class-decision amendment (issue #42)

Fresh decision replies no longer express `class_outcomes` or `class_actions` as arrays containing
repeatable `class_id` fields. They are closed objects generated from the active-class snapshot.
Final requires every active class outcome; correction requires exactly the classes already bound to
open debt; census derives outcomes from the integrity manifest. Every active class has a required
nullable action slot, where `null` means no independent action. A non-null slot admits exactly one
action. A mechanized class's value schema excludes `close` and `reopen`
and requires a mechanized replacement definition.

The decoder retains JSON object pairs until duplicate keys have been rejected, including nested
Claude `structured_output`, then projects the maps to the unchanged canonical arrays in encounter
order. Canonical semantic validation, class-engine dry-run, atomic settlement, durable state, and
the single corrective retry are unchanged. No invalid row is collapsed or partially settled.

Correction findings for a non-debt-bound existing class carry independent
`classification.assessment_evidence`; the server derives that one violated outcome with a
`new_finding` basis. A fresh finding for a debt-bound class instead requires the authored outcome to
name that exact finding; `carried_debt` cannot mask a fresh occurrence. Finding and assessment
evidence are projected and retained independently.

The maximum 100-active-class branch schemas use local `$defs`/`$ref` sharing and grouped class-ID
enums without changing the closed contract. Their compact provider projections are 15,677 bytes
for census, 22,975 for correction, and 24,197 for final, all below a 32,768-byte transport gate and
well below Linux's per-argument limit used by Claude. Exact fresh/resumed Codex and Claude results
are retained in
[`keyed_class_decision_provider_acceptance_2026-08-19.json`](keyed_class_decision_provider_acceptance_2026-08-19.json).
The bounded gate made sixteen successful calls: minimal correction, a populated correction with one
debt-bound and one newly affected active class, a representative two-class census, and maximum
100-class final, fresh and resumed, on
Codex CLI `0.144.6` with `gpt-5.6-sol` and Claude Code `2.1.197` with
`sonnet`, all at high effort with web disabled. Each retained exact response replays through the
production decoder and semantic materializer. The maximum-final schema was 24,197 bytes; the
retained call time totaled 384.068 seconds. The census probe carries its authoritative assessment
inputs into executable semantic replay, so every decision role is exercised rather than merely
schema-generated. The older hashes above describe the pre-amendment array
wire schema and remain historical evidence only.

The separate signed-in
[`keyed_class_handler_acceptance_2026-08-19.json`](keyed_class_handler_acceptance_2026-08-19.json)
drives commit `9ef782b` through the production `critique_branch` correction handler with one closed,
debt-bound active class. Codex session `01a01a28-879a-7ab2-aede-d38271faeb70` returned one exact keyed
response; schema SHA-256 is `5e044b4c…f6635` and response SHA-256 is `55bc5e4a…2e12`. Anchor
validation and canonical materialization derived `reopen`; atomic settlement persisted that class
open with its original open debt binding, and the rendered result remained correctly blocked.
The exact settlement retains `_class_record_pointers` as
`["/class_outcomes/acceptance-class"]`. Elapsed handler time was 77.854 seconds with one model call
and no validation retry. The executable
replay regenerates the exact schema, hashes and decodes the retained response, resolves anchors from
the recorded commit, replays canonical class transition, and checks durable and rendered outcomes.

The final pre-convergence production diff from `main` is 456 additions and 66
deletions across five existing modules: `staged_protocol.py` +382/-47, `engines.py` +44/-7,
`handlers.py` +16/-5, `prompts.py` +13/-6, and `review_census.py` +1/-1. The largest changed
production module is `handlers.py` at 2,982 lines; `staged_protocol.py` is 1,483 lines. The retained
provider and handler acceptance totals 17 successful model calls and 461.922 seconds of observable
wall time. This excludes failed diagnostic/capability attempts and CODE-review calls rather than
misstating them as successful release evidence.

Fresh keyed locations are also retained through canonical materialization solely for retry
diagnostics. Semantic and canonical class-engine failures therefore name the provider-repairable
key (for example `/class_actions/<class-id>`) rather than an array index that never appeared in the
provider response. This includes canonical projection collisions, invalid finding bases, fallback
class-engine candidates, and required null action slots. The private pointer map is not persisted
or included in settlement state.
The worktree-bound full suite passed **1,167 tests in 60.82 seconds**. The historical differential
passed all eight role/shape groups and the bounded mutation gate killed all **31** owned mutants,
including keyed diagnostic-pointer preservation.

### Keyed amendment acceptance boundary

The retained live evidence is deliberately compositional, not Cartesian. The provider matrix proves
fresh and resumed structured transport for census, populated correction (including independent
`assessment_evidence`), and final responses through the production decoder/materializer. The
signed-in handler artifact proves the production `critique_branch` bridge through anchor
resolution, canonical dry-run, settlement, persistence, audit, and rendering. Deterministic handler
tests then drive the same production `_staged_call` used by that bridge through schema-valid
semantic and canonical failures, the exact keyed retry prompt, rejected-attempt retention, resumed
success, and final materialization. This acceptance does **not** claim that a signed-in model was
induced to fail validation on command, or that every semantic payload shape was crossed with every
provider/route/handler combination.

That boundary is intentional. Asking a live model to emit a prescribed invalid response tests
model obedience to an instruction to fail, not a distinct CLI/schema capability, and is not a
repeatable release gate. Production class IDs are server-minted as the first eight hexadecimal
characters of SHA-256, so a primary lifecycle cannot naturally create a class key containing `/` or
`~`; doing so requires deliberately corrupted lineage state, which the frozen operating model
excludes. RFC 6901 escaping remains total defensive behavior, while reachable production pointer
bindings are covered using actual ID-shaped and named test-fixture keys. A future distinct call
adapter or supported non-hex ID source would require new live evidence; semantic reuse alone does
not.

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

### Duplicate class-outcome correction acceptance (2026-08-15)

A controlled signed-in Codex branch census reviewed implementation commit `6bdae17770f31c56e62be3f9f5fb3d687e47e309`
with active class `89308d49` seeded through the canonical class engine. The integrity lane assessed
that class `satisfied` with three repository evidence anchors. Consolidation emitted exactly one
outcome for the class with the identical verdict and ordered evidence, and durable settlement closed
the seeded class. This establishes the real provider's one-row behavior at this commit; it does not
claim that every future provider response will follow the prompt.

The bounded retained projection is
[`duplicate_class_outcome_acceptance_2026-08-15.json`](duplicate_class_outcome_acceptance_2026-08-15.json).
The full local audit SHA-256 was `54e6dfb1b75d1e15c62f285ab1c26a82fc8389b34a42f7d3a9ef298d76221169`;
the consolidation response SHA-256 was `90b95f63feb27c703a769952af8e0db8c915b89abdd47f91ac93fbaf6c1551f0`.
The run made five model attempts—three lanes, one execution-lane validation retry, and
consolidation—and used 4,837,709 input tokens (4,177,408 cached), 26,480 output tokens, and 13,107
reasoning tokens. Observable provider wall time across the command yields was approximately 202
seconds.

At the reviewed implementation commit the production diff was 50 additions and 2 deletions across
`handlers.py`, `prompts.py`, and `staged_protocol.py`. The largest production diff was 37 added lines
in `staged_protocol.py`; the largest changed production module was `handlers.py` at 2,827 lines.
The real run did not force a consolidation retry. A production-handler test now supplies a seeded
active class and valid branch anchors, sends a duplicate/overriding consolidation response, repairs
it on the actual same-session retry, and asserts the exact audited and durable class assessment.

## Real Claude primary lifecycle

The same disposable repository and contradictory/corrected plan pair then exercised the complete
path with pinned Claude CLI `2.1.197`, explicit `sonnet`, high effort, claim verification and web
disabled, and a fresh lineage:

| Invocation | Artifact result | Audit SHA-256 |
|---|---|---|
| 1, census + consolidation | One BLOCKER, one new class, one open debt; correction required | `cf29adde97ad96412ceb436f3916fbbf56e90bc18b09815ca4ff6bce480b7451` |
| 2, correction | Contradiction class and debt closed; final required | `dea31cbb6b67a2808f0e4302ea391529b9fd69194079b15a2b56b410c4508cd7` |
| 3, cold final | `CONVERGENCE: NOT-BLOCKED`; zero blocking debt, class closed | `c7d1b289f91ecf2ae2666fed3c7a90400731c3724391840ad5c0146cf5b037c3` |

The lifecycle made six model attempts: three concurrent lanes, consolidation, correction, and
final. All completed without a validation retry; the separate exact correction probe above owns
the real resume/retry evidence. Audit cost totaled `$1.19994`; observable provider time was about
256 seconds with concurrent lanes. Final durable-state SHA-256 is
`e2ba49e060bbfc2130eaa423f7b773f16f1c4ce22d9214864ef515bc97c50474`, phase `clear`.

## Automated verification

The current complete collection ran with global and system Git configuration disabled so fixture
commits did not inherit the operator's signing key: **999 passed in 62.34 seconds**. An initial
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
group. The eight-group executable matrix covers census, correction, final, one-off/new/existing
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

CODE round 6 showed that one fail-fast aggregate call could still mask a second aggregate
interaction: duplicate transitions could hide the independently detectable new-class cap. The
architecture checkpoint replaces that call with bounded canonical partitions, not pairwise subset
search: every record is checked alone, each same-class transition group is checked through the
canonical engine, all new definitions are checked together for the single global cap, and the full
set is checked only when those independent groups pass. The terminal retry fixture now combines two
same-class actions with two new definitions at 99 active classes and verifies both aggregate errors,
the semantic duplicate pointer, debt incompleteness, and anchor failures in one diagnostic.

CODE round 7 closed the last correction blocker, but the round-8 broad cold final found one omitted
V1 lifecycle shape: correction rejected outcome-independent standalone `close` and `reopen` even
though both are valid canonical operations and the accepted plan promises them. The materializer
now permits those actions when no class outcome is required, while retaining compatibility checks
whenever an outcome is present. Independently authored V1/V2 close and reopen fixtures apply both
through the canonical engine and durable settlement and compare class state, phase, and trailer.

CODE round 9 closed that compatibility class. Round 10's second broad cold final found three
release-gate defects: some semantic diagnostics used IDs rather than numeric array components;
unpaired surrogates could pass schema validation and later fail strict UTF-8 subprocess transport;
and the Claude decision/lifecycle acceptance required by the plan was missing. Semantic errors now
use model-owned numeric JSON Pointers, and a regression mechanically resolves every reported
pointer against the rejected object. Recursive validation rejects unpaired surrogates at their
exact pointer before an accepted manifest can reach a later prompt, cache, persistence, or process
boundary. The exact-schema, retry, and full Claude evidence is recorded above. The round's advisory
README mismatch now names the actual 240,000 lane, 1,000,000 decision, and separate 5,000,000 prompt
limits.

CODE round 11 retained the Unicode and Claude classes because only one high-surrogate value was
tested and the live evidence existed only outside the repository; it also found that a duplicate
integrity assessment could point a retained first-row error at the last duplicate. The pointer map
now follows `_unique`'s first-row rule and the duplicate regression pins both numeric locations.
Unicode tests cover high and low unpaired values, property names without unsafe echo, a valid astral
scalar, composed prompt encoding, cache/state persistence, review rendering, and both real capture
and streaming subprocess boundaries. The retained Claude artifact and its executable binding test
provide the independently inspectable evidence described above.

CODE round 12 closed the Unicode and pointer classes. It retained only the provider-acceptance class
because the versioned artifact bound decision schemas and the lifecycle but not the exact lane
schema previously cited in prose. The retained lane probe and executable binding immediately above
close that finite evidence gap; no implementation behavior changed in this correction.

## Size and architecture checkpoint

The pre-review checkpoint covered `handlers.py`, `review_census.py`, `prompts.py`, `engines.py`, and
`staged_protocol.py` at +198 net lines. CODE round 1 then triggered the documented architecture
checkpoint rather than another open-ended patch loop. The accepted completion pass moves those five
modules to **+525 net lines** and current sizes 2,783, 450, 501, 616, and 906 lines. The increase is
bounded cross-layer issue accumulation, provider-envelope closure, and coherent packet limits;
the larger differential and mutation evidence lives in tests/scripts rather than production.
There is still no new subsystem, and the largest existing handler was not expanded by this pass.
Across all production Python and dependency-manifest changes the current diff is **+545 net lines**;
the remaining 20 lines are the independent arbitration fence-helper relocation, existing numbering
helper change, and dependency declaration already described above.

The model-facing top-level settlement relationships fall from seven mirrored tables to four
semantic tables. There is no new persistence layer, model phase, provider call, trust boundary, or
durable V1 fallback. Cache protocol version is 2; durable lineage format remains version 1.

## Deterministic census-outcome amendment (2026-08-15)

The amendment in
[`derive_census_class_outcomes_plan.md`](derive_census_class_outcomes_plan.md) removes model-authored
`class_outcomes` from the census role only. The server now copies each validated integrity
assessment's verdict and ordered evidence and, for a violation, requires exactly one governing
finding that both contains the cited integrity source and classifies to that active class.
Correction and final schemas, materialization, branch lifecycle, evidence anchors, durable state,
and provider call count are unchanged.

The combined focused protocol/handler suite passed 140 tests, including an unchanged-input
cross-invocation case proving a satisfied assessment for an unproven mechanized class exhausts its
lane retry, persists no census cache, and causes the next invocation to execute fresh lanes. The
ordinary suite passed **1,054 tests in 191.46 seconds**. The historical differential passed all
eight V1/V2 role/shape groups, and the expanded release gate killed all **15** owned mutations:
the original nine plus census schema exclusion, lane/class-state compatibility, governing-match
cardinality, exact verdict projection, exact ordered-evidence projection, and assessment
completeness at the integrity-lane boundary.

[`derive_census_class_outcomes_acceptance_2026-08-15.json`](derive_census_class_outcomes_acceptance_2026-08-15.json)
retains the exact current provider schema, schema hash, exact response objects and hashes,
server-owned materialization inputs, and replayed class assessments/records for both supported
transports. Codex CLI 0.144.6 with `gpt-5.6-sol`/high and Claude Code 2.1.197 with Sonnet/high both
returned the same valid response with web disabled. The executable test regenerates and compares the
exact schema, validates and hashes each retained response, and replays each through the current local
decoder and materializer with the recorded inputs. Raw-envelope transport claims are made only from
the separately retained exact material below.

[`derive_census_class_outcomes_authenticated_material_2026-08-15.json`](derive_census_class_outcomes_authenticated_material_2026-08-15.json)
retains gzip-compressed exact bytes for the primary census audit and fresh raw Codex and Claude
provider envelopes. The executable acceptance test decompresses each record, recomputes its SHA-256,
reconstructs the bounded primary audit projection, parses both provider envelopes through the real
engine parsers, and proves the resulting structured objects equal the retained schema-valid
responses. The Claude check additionally reads `structured_output` directly from its exact envelope.
It also retains the exact same-vendor reviewer disposition for the circular demand that the reviewed
commit contain its own future cold-final record. That reviewer answered `CONCEDE`; the executable
test authenticates the disposition and session. This does not replace the external correction and
cold-final release gate, and the report makes no self-attesting convergence claim.

The current signed-in primary acceptance used the real tracked branch handler at snapshot
`f5950327303e9278829ca789b68577b5eb2b3be1` with active class `f7da2428`. Three Codex lanes plus
consolidation completed in an operator-measured 208.165 seconds (four model calls). The elapsed value
is an operational observation, not an authenticated timing claim. The persisted settlement assessed the
class satisfied with repository evidence, derived its canonical close, and the audit file hashes to
`d148bfd9fbf6bde6cb5a4d6cfeb7a60af640143b8e817f29f4c111baaea36d1e`. The retained bounded audit
projection binds the base/head commits, attempt roles/outcomes/response hashes, lineage/round, and
materialized assessment; its executable digest is verified in the suite. For that exact snapshot,
production Python changed by +101/-70 (net +31); `staged_protocol.py` was the largest changed
production module at +94/-63, while `handlers.py` was the largest changed production module by size
at 2,827 lines. The executable acceptance test recomputes those diff and module metrics directly from
the retained base/head Git objects.
