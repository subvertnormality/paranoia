# Claim audit correction and five-mode benchmark plan

## Frozen operating model
One trusted local operator and OS run the installed provider CLIs. Repository, plan,
provider, and fetched page bytes are untrusted data. No repository-selected code execution
by reviewers, hostile same-user race, compromised OS, multi-tenancy, or corrupted-state
recovery is in scope. Ordinary edits invalidate bindings. Reviews cover tens to low
hundreds of claims with evidence useful within minutes; role timeouts remain generous.
Benchmark workers are isolated processes, at most two concurrent cases (up to six census
lanes). Public HTTP(S) capture retains existing address and authority restrictions.
False clearance and wrong evidence binding have high impact; recoverable blocking is
acceptable. Benchmark fixtures are synthetic public data, never the private reported plan.

## Problem and scope
Issue 114's retained Claude sessions contain a valid audit object followed by a Sources
footer. The same object strengthens an anchor with "whole". Fail-fast suffix rejection
hides the independent semantic error from the single correction; that correction removes
the footer and retains the scope error. Envelope decoding worked. Fix diagnostic
completeness rather than weakening syntax or the closed universal-form guard.

## Implementation obligations
A1. In plan_claims.parse_audit, after safe object decoding and shape admission, accumulate
independent suffix, claim-row, and coverage validation failures into one bounded diagnostic.
Retain claim indexes and coverage locations. Malformed JSON and unsafe container shapes
still reject immediately. No rejected full audit settles or reaches capture. Preserve the
existing explicitly requested partial-audit behavior for row errors; suffix and coverage
errors remain fatal even there. No new model call, persistence mechanism, or permissive
normalizer.
A2. retry_instructions repeats the existing universal-scope instruction, asks repair of
every reported issue, and prohibits a Sources footer. Deterministic production-engine
lifecycle tests reproduce simultaneous footer and scope failures, repair both in the
existing one retry, and retain both attempts and fail-closed behavior when unrepaired.
A3. Implement a rerunnable live benchmark script and frozen corpus/oracle with ten cases:
two each for critique_branch, critique_plan, query, rebut, and arbitrate. Each pair has one
valid and one defective outcome (rebut instead uses repaired versus unrepaired code).
Plan cases use an official pytest-xdist loadscope behavior, one accurately stated and one
incorrectly stated. Branch/query/rebut use small executable arithmetic contracts and
boundary defects. Arbitration compares alternatives against an explicit local contract.
Run baseline 9bd9b893ef7d21903aa704eb31176206eb9abe74 and candidate in isolated fresh state,
two repetitions each: forty scored trials. Clean branch and plan trials continue through the cold final;
stop at validated blocking debt or an operational failure, with at most two rounds.
Report actual public invocations separately. Rebut includes authentic query
setup, measured separately and in total. Fix one provider per case, balanced across the
corpus; both plan cases use Claude to cover 114. Arbitration uses both providers. This is
not a per-case cross-provider comparison. Counterbalance version order and record it before
execution. Keep ordinary role timeouts and at most two workers. No cost-driven timeout
shortening or automatic repeats of failed trials.
A4. Freeze source revisions, file hashes, CLI/model/effort settings, fixture hashes, case
order, and scoring oracle before provider spend. Active reviewers receive opaque fixture
IDs and payloads only, with no oracle, seeded-defect label, issue number, or benchmark source
path in prompts. Oracle separation is procedural blinding under the trusted-local model.
Record complete local results, actual elapsed time, calls/retries, available provider usage,
and failures. Never invent dollar cost for subscription usage. A 320 provider-call admission
ceiling stops the pilot visibly as incomplete instead of silently skipping work.
A5. Report case-level correctness, defect misses/false clears, false positives, operational
failures, paired elapsed time and model-call differences, and available usage. Record a
finding-level adjudication worksheet against the frozen oracle; disclose implementer
adjudication and do not claim independent human acceptance or population precision/recall.
Publish reproducible aggregate results and synthetic fixtures, with limitations: ten cases,
two repeats, provider/network variability, no guarantee of improvement in the wild.
A6. Run targeted regression tests, full suite, existing mutation checks, and real Claude
verified-plan acceptance through server.dispatch as part of this explicitly authorized
functional benchmark. Capture and cold attestation remain enabled. Such critique_plan
calls test the product; implementation convergence remains CODE against this contract.
A7. Update public documentation and AGENTS before review. Run CODE convergence on this
branch with this immutable plan contract after implementation and live benchmarking.
Repair in-scope findings without scope escalation. Preserve historical acceptance records
as historical and update exact permitted later-source-diff bindings where necessary.

## Acceptance
The simultaneous defect regression exposes both errors on the initial attempt, succeeds
when both are repaired in one correction, and blocks an unrepaired quantifier before
capture. A real Claude verified-plan trial either settles with captured and cold-attested
evidence or retains truthful phase-specific failure; do not call 114 empirically resolved
on a failed reproduction. The A3 trial count or an explicitly incomplete ledger are
reported without suppressing failures. Claims of improvement are limited to measured
paired outcomes and deterministic call reductions. All current invariants, required tests,
and final CODE convergence must pass before delivery is described as complete.

## Binding clarifications after PLAN review
The operating model owns concurrency and threat assumptions; A1-A7 own implementation
obligations. Trial totals are derived from A3, not an independent execution rule.

B1. scripts/benchmark_review_modes.py owns a versioned manifest with separate inputs and
oracle rows. Before spend it validates exact case IDs, modes, provider, source revisions,
payload hashes, expected proposition/contract, acceptable answer/disposition, and evidence
needed for credit. scripts/score_review_modes.py produces a worksheet; each reviewed
finding is adjudicated against that oracle with an exact output quotation and explanation.
Branch/plan credit requires a canonical settled finding or clear final with matching
durable state; a pending census is not clear. Query requires an explicit correct answer
with code evidence. Rebut requires explicit CONCEDE/HOLD and matching current code evidence.
Arbitration requires the server's converged winning option to match the oracle; divergence,
no winner, unsupported reasoning, missing state, malformed output, and execution failures
remain separate non-success outcomes. Do not infer semantic credit from keywords alone.
Use implementer adjudication, report case accuracy conditional on scorable completion plus
unconditional task success, and label finding-level estimates as corpus-only.

B2. Count one admission for each Engine.run or Engine.resume invocation, including role
clones, setup, both vendors, validation retries, evidence, and arbitration. A benchmark-only
shared integer under a local OS file lock reserves before calling the original method,
across both worker processes. Never refund admitted calls. At 320 refuse before provider
execution and retain the refusal and affected/incomplete slots. Already admitted calls
finish under original timeouts. Parent initializes the counter once and never resumes an
old run as fresh. Tests race two workers for the final slot and prove only one invocation
launches, refusal does not invoke a provider, and unstarted/interrupted trials remain
explicitly incomplete. No product admission or state protocol is added.

B3. Rebut setup queries the defective snapshot and records its exact output, session,
provider, and snapshot. The adjudication gate must confirm the intended arithmetic defect
and cited app.py location before resume; absent/incorrect/failed/unbindable setup leaves
the dependent trial incomplete and unscored, retains setup costs, and never fabricates a
finding or retries setup. Apply only the manifest's repair for the repaired case; bind the
new snapshot and retain both. Test valid repaired/unrepaired handoffs and each invalid
setup outcome. The benchmark can pause for implementer qualification before rebut spend.

B4. Required parse_audit tests combine suffix text, multiple invalid and duplicate rows,
and both independent coverage failures. Assert indexed/located bounded diagnostics and
malformed JSON/container rejection. Row-only partial parsing retains valid packets with
blocking diagnostic debt; any suffix or coverage failure rejects even in partial mode.
Production _CapturedClaimEngine coverage must show a correctly repaired packet reaching
capture, binding, and cold attestation once, while an unrepaired correction cannot capture
or clear prior debt. Deterministic benchmark checks cover manifest rejection, per-mode
outcome categories, admission boundaries, handoff gates, and incomplete result slots.
