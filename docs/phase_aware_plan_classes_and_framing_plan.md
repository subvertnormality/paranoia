# Phase-aware plan classes and fidelity-safe arbitration framing

## Goal

Fix two review-contract defects without weakening either later implementation review or
arbitration fidelity:

1. A plan review must not remain blocked solely because a class asks the plan to produce runtime
   or implementation artifacts. It must instead judge whether the plan binds the obligation to a
   named scope, executable acceptance, and fail-closed behavior that later code review can verify.
2. Arbitration cleaning must remove advocacy without copying facts, constraints, caveats, or
   qualifications between options merely to equalize their lengths. A neutral statement of a
   binding prior decision is context, not advocacy.

## Stakes and exclusions

The supported environment is a trusted single operator and OS. Repository, plan, ballot, and web
content are untrusted data. There is no hostile local race or compromised OS. Reviews cover tens to
low hundreds of claims/classes and should return useful evidence within minutes. False clearance,
wrong phase gating, evidence misbinding, and altered ballot meaning are high impact; visible,
recoverable blocking is acceptable. Multi-tenancy, hostile same-user races, formal proof, and
deliberately corrupted-state recovery are excluded.

## Current failures

### Plan phase

The staged plan prompts tell the integrity lane to assess every active class, but never define what
`satisfied` means when the reviewed artifact is a plan. An unmechanized class can therefore demand
captured evidence, input mutation, or rematerialization and remain `violated` forever even after the
plan has specified that work correctly. The durable lifecycle already supports `replace`, `close`,
and broad cold branch review; the missing piece is phase calibration, not a new state transition.

### Arbitration framing

The cleaner is simultaneously required to equalize option detail and forbidden to add or remove
facts, caveats, or qualifications. The attester correctly rejects a copied qualification as a
semantic change. When the original packet contains advocacy, the existing atomic-original fallback
correctly remains unavailable, leaving no valid route. The attester also lacks an explicit
distinction between a neutral record of a binding prior decision and language urging a decider to
follow it.

## Design

### 1. Make plan-class satisfaction explicitly phase-relative

Add one shared plan-phase instruction block to every model role that owns plan findings or class
judgements: staged census lanes, consolidation, correction, final, and the legacy plan reviewer.

For plan mode:

- Judge the completeness and executability of the plan contract, not whether future implementation
  artifacts already exist.
- An in-card plan obligation is satisfied only when the plan names its implementation scope,
  specifies the exact evidence or observable acceptance procedure, and states the blocking failure
  behavior. Ownership is additional metadata, not a substitute for scope.
- A promise such as “test this” without those bindings remains violated.
- An otherwise blocking, in-scope obligation deferred outside the current card remains blocking
  unless it is routed to a named durable residual whose ownership and acceptance boundary are
  stated. This rule does not promote advisory, `OUT-OF-SCOPE`, stakes-excluded, or declared non-goal
  work into blocking debt.
- Never register a new plan class whose invariant can be satisfied only by executing future code.
  Register the plan-reviewable invariant: the required implementation obligation is completely and
  correctly bound.
- If an existing plan class itself demands produced artifacts, use the existing replacement
  lifecycle to restate it as a plan-reviewable invariant. Do not repeatedly report absence of the
  future artifact as a new occurrence, and do not claim the implementation has passed.

No persistence schema or class status changes. A satisfied plan class means the plan contract is
adequate at this phase. The later branch lifecycle remains a broad cold review of actual code and
tests, so this does not turn a plan promise into implementation proof.

### 2. Remove semantic equalization from cleaner and attester contracts

Remove semantic inter-option ratio enforcement from caller preflight, cleaned-candidate validation,
the public tool schema, and their error/remedy text. Retain absolute per-field and complete-prompt
capacity limits. Replace the cleaner's `EQUALIZE` mandate with a fidelity-bounded presentation rule:

- normalize tense, voice, labels, and rhetorical padding only when meaning is preserved;
- never transfer content between options or add/drop facts, constraints, caveats, or
  qualifications to make lengths match;
- preserve substantive asymmetry for the deciders to evaluate.

Align the attester: unequal substantive detail alone is not advocacy. It may still reject loaded
wording, recommendations, emphasis, or selective rhetorical padding. Fidelity remains strict and
continues to reject additions, removals, narrowing, widening, and qualification changes.

### 3. Distinguish binding context from advocacy

Tell the attester that a neutral factual statement that a prior decision exists and governs the
current bytes is shared context. It becomes advocacy only when it praises the prior result, asserts
it was correct, or tells the deciders to repeat/follow it. Context remains byte-preserved and
independently gated.

## Tests

- Assert every staged plan role receives the same phase-relative class rule through the production
  handler, while branch roles do not. Existing class-engine tests continue to prove replacement,
  closure, severity gating, durable phase/debt state, and bounded call count. Prompt-contract tests
  prove the reviewer is instructed to apply those mechanics to artifact-demanding, completely
  bound, vague, advisory, stakes-excluded, and declared non-goal obligations. These deterministic
  tests establish the executable contract and settlement behavior; they do not claim that a fake
  provider response proves the quality of a future semantic judgement or implementation.
- Assert the legacy plan prompt and plan class-register instructions forbid implementation-proof
  invariants and explain replacement of an existing malformed class.
- Add both deterministic and production-handler cases using neutral substantive option asymmetry
  greater than the legacy 2.0 ratio. Assert caller preflight and cleaned-candidate validation admit
  it, both deciders are invoked, and each recorded decider body contains the exact accepted option
  statements. Retain and separately test absolute capacity limits. Update the public schema,
  README, governing design, messages, and tests that currently encode the ratio.
- Assert cleaner prompts prohibit cross-option content transfer and no longer demand equal length.
- Assert attester prompts say substantive length/detail asymmetry alone is not advocacy and
  distinguish a binding prior-decision premise from endorsement.
- Preserve existing fidelity parser, atomic-original fallback, context byte-fidelity, and
  cross-vendor route tests.

## End-to-end acceptance

Use the public `critique_plan` handler with `repo_path` set to this checkout, `plan_path` set to this
file, lineage `phase-gating-real-code-acceptance`, the frozen stakes above, Codex
`gpt-5.6-sol`/`high`, claim verification and web search disabled, and an isolated state root. Seed
that plan lineage at round 1 with one open `MAJOR` class whose invariant requires a runtime
attestation produced by future code and one open debt record bound to it. The tracked acceptance is:

1. Round 2 must replace that predecessor with a plan-reviewable invariant requiring exact
   implementation scope, executable acceptance evidence, and fail-closed behavior. The same open
   debt ID must bind to the successor; replacement alone is not clearance.
2. A targeted correction round must independently assess the successor against this plan. It may
   close only when the cited plan text actually contains all three bindings. The durable class and
   debt must both close and the structural phase must advance to `final`.
3. The immediately following broad cold-final round must finish with `STRUCTURAL-PHASE: clear`, no
   blocking structural debt, and `CONVERGENCE: NOT-BLOCKED`.

Persist each production audit and record the provider route, exact prompt/reply digests, attempt
role, model-call count, duration, class action, debt outcome, durable phase, and final convergence
signal. Provider execution failure, validation retry exhaustion, state/settlement failure, a still
violated successor, a missing cold final, or any different terminal signal blocks delivery.

After implementation, also run the signed-in arbitration acceptance generator's ordinary route.
It supplies options with greater than 2.0 substantive length asymmetry, explicit removable advocacy
in the decision, and neutral context recording a binding prior decision. It must use `attested` or
`attested-after-retry`, never `original-attested`; reach both deciders without content transfer;
compare the accepted attested packet's exact option statements and context bytes against both
recorded decider prompt bodies; and record actual model-call count and elapsed time. Pair it with the
negative production-handler test proving that cross-option content transfer is rejected by fidelity
attestation and that both deciders receive only the atomic originals.

## Non-goals

- No new class status, cross-lineage migration, persistence field, model call, or provider schema.
- No automatic claim that implementation acceptance passed.
- No relaxation of fidelity validation or atomic packet selection.
- No acceptance of recommendations or rhetorical steering disguised as prior-decision context.
