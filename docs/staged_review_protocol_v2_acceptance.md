# Staged review Protocol v2 implementation acceptance

Status: **local implementation acceptance complete; CODE convergence pending**

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
unions, and the single-anchor grammar. A provider omission can therefore cause only the existing
validation correction/failure path, never settlement.

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

The environment's command wrapper terminates a single process after roughly 30 seconds, so the
full collection was run in three exhaustive groups with identical environment and Git isolation:

- 159 arbitration-handler tests passed in 22.33 seconds;
- 438 core/engine/handler tests passed in 27.0 seconds;
- 356 integration/plan/staged/server tests passed in 12.14 seconds.

Total: **953 passed**. Focused V2/engine/prompt/plan tests also passed independently, and
`git diff --check` is clean.

## Size and architecture checkpoint

The reviewed checkpoint covers `handlers.py`, `review_census.py`, `prompts.py`, `engines.py`, and
`staged_protocol.py`. Against `main` those five modules are **+198 net lines**, within the reviewed
`+200` stop threshold. Their current sizes are 2,689, 434, 501, 601, and 704 lines respectively.
Across all production Python and dependency-manifest changes the diff is +218 net lines; this also
includes relocating arbitration's independent fence helper and making the existing numbering helper
accept an already-split line collection.

The model-facing top-level settlement relationships fall from seven mirrored tables to four
semantic tables. There is no new persistence layer, model phase, provider call, trust boundary, or
durable V1 fallback. Cache protocol version is 2; durable lineage format remains version 1.
