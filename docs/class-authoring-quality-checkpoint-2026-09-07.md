# Class-authoring quality checkpoint — 2026-09-07

Status: candidate retained, not merge-qualified. No general speedup claimed.

The implementation is on `codex/review-quality-speed`. Production source was frozen at
`495d28f9baff8b7f04289342926a04b12785f077`; subsequent commits update historical replay
compatibility and user-approved metadata without replacing original provider evidence.
The accepted [plan](class-authoring-quality-plan.md) remains unchanged.

## What changed

One shared class-authoring rule separates governing requirements from suggested repair syntax.
A behavioral invariant must allow compliant alternative repairs. A text predicate must identify
violations rather than also matching compliant code; otherwise the existing unmechanized
procedure and member inventory apply. The rule reaches existing authoring roles and their
existing validation retry. Reviewer calls, roles, schemas, closure authority and timeouts remain.

The prior [predicate continuation](predicate-convergence-result.md) demonstrated one real false
blocking obligation after a correct repair. That is a bug-reduction motivation, not evidence of
a population-wide performance improvement.

## Native acceptance and limits

| Run | Attempts | Observed result | Acceptance limit |
| --- | ---: | --- | --- |
| Original Codex parent | 5 | Found the integer/Boolean defect; created one-off debt | No authored class, so neither continuation was admitted |
| Original Claude Fable parent | 3 | Provider quota failures | No reviewer judgment or settlement |
| User-authorized Opus parent | 4 | Authored a blocking requirement-grounded class with both valid repairs explicitly admitted | Qualifying parent only |
| Opus exact-type continuation | 1 | Correction closed the same class and reached final phase | Operator ran arms concurrently; harness rejected an incomplete global attempt ledger before cold final |
| Opus Boolean-exclusion continuation | 2 | Correction and separate cold final cleared, unchanged class definition | Qualified individual continuation; incomplete overall campaign |

The Opus alias resolved to `claude-opus-5` in provider-reported model usage. Its fresh census
took 402.703 seconds of native dispatch. The exact-type correction took 91.146 seconds; the
Boolean-exclusion correction plus cold final took 366.359 seconds. These are observations,
not paired model or performance comparisons. Each successful Opus attempt used the existing
native role; there were no validation retries in this fallback campaign.

The implementing agent assessed the Opus parent against the governing fixture specification,
bound its assessment to the exact terminal and class state, and qualified both copied parent-state
forks before execution. The Boolean arm subsequently passed native custody and clear-eligibility
checks. Full campaign qualification still rejects `scheduled arm missing: p01-exact`.

Running the arms concurrently was an operator error: this harness checks the complete campaign
ledger after each round and requires serial arm execution. Preserve the failed exact-type terminal;
do not count its closed correction state as cold-final acceptance, patch the frozen harness, or
selectively rerun until a favorable result appears. The original Fable/Codex run remains intact.
No branch CODE convergence or merge acceptance is claimed.

## Deterministic validation

- Final full suite: **2,156 passed, one failed** in 193.47 seconds.
- Remaining failure: `test_authoritative_capture_acceptance_record`, the exact later-handler
  delta in the twelfth historical receipt, pending separate user approval.
- All 59 affected historical replay positive and tampering tests passed after exact inverse
  projection of the new authoring paragraph. Complete retained prompt equality remains required.
- All 33 owned Protocol v2 mutants were killed.
- Production-handler fixtures cover original defect blocking, both valid repairs through cold
  final, unchanged invalid repair, and incomplete member coverage.
- The acceptance harness's scripted complete graph passes all eleven resealed negative controls.
  Scripted results do not replace the incomplete native acceptance.

The user approved metadata-only updates to eleven historical receipts. Original runs, results,
source identities and ratings were verified unchanged. These allowances record later source
deltas; they do not assert that an old provider run exercised new code.

## General speedup feasibility

The three initial census prompts were reconstructed with hashes equal to the native invocations.
They contain 19,855, 19,855 and 20,255 characters, including the same 10,453-character artifact
body. A text-only permutation retaining every character and prompt length increases their common
prefix from 8,261 to 18,714 characters. It used zero provider calls and changed no production code.

All three provider schema hashes differ. OpenAI documents that cache reuse depends on the complete
rendered prefix and that structured output format contributes instructions and schema. Thus the
text-prefix increase alone does not establish cache reuse on these CLI routes.
[Official prompt-caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching)

The parallel first-use lanes also do not establish that a reusable cache entry is available in
time. We have no measured end-to-end latency or cost benefit from the permutation. Do not ship
it or fund a broad paired campaign on this evidence. A future test needs native cache telemetry
and a credible whole-review savings bound before a frozen quality-preserving comparison.

Earlier measured non-dispatch overhead plus idealized retry removal was about 9.3% for staged
review, below the accepted 20% gate. Broad handler decomposition also lacks a demonstrated speed
mechanism. Neither warrants implementation in this checkpoint.

## Architecture checkpoint and next boundary

Keep this candidate separate from main. The current single-site fixture permits a legitimate
one-off disposition and therefore does not reliably exercise class authoring. If this work is
continued, specify a representative recurring-defect fixture in a new explicit experiment,
retain both legitimate repair forms and negative controls, and run continuation arms serially.
Do not weaken the requirement for an actually authored class or reinterpret the failed campaign.

Prioritize measured provider work and convergence over small scheduling changes. Refactoring is
warranted only when it removes a demonstrated root cause or substantially simplifies an existing
boundary with equivalent behavior. No broad rearchitecture is proposed on the available evidence.

## Retained evidence

[class-authoring-quality-evidence-2026-09-07.tar.gz](class-authoring-quality-evidence-2026-09-07.tar.gz)
contains both native campaign roots, original provider channels, state/fork bindings and the
zero-provider layout result: 372 members, 282,335 bytes.

SHA-256: `b321809563e0111120d3742b181d2ba739d425d4f225a93639292d51dda1e733`.

The frozen execution source is `/tmp/paranoia-class-authoring-source`. Campaign roots are
`/tmp/paranoia-class-authoring-live-2026-09-07` and
`/tmp/paranoia-class-authoring-opus-2026-09-07`. The completed test log is
`/tmp/paranoia-class-authoring-final-suite.txt`.

