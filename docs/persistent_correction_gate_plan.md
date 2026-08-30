# Persistent correction gate

## Problem and scope

Tracked staged reviews already render `PERSISTENCE` after three caller-supplied round
labels and `REOPEN-WAVE` after a class reopens, but neither signal affects settlement.
A blocking class can therefore consume arbitrarily many correction rounds while finding
and debt identities rotate. Issue #66 records a 115-round plan lineage exhibiting that
failure.

This change makes those existing diagnostics load-bearing without changing review quality,
severity, class discovery, claim verification, or the census/correction/final lifecycle.
It applies to both tracked plan and branch staged reviews. One-shot reviews remain unchanged.

## Frozen operating model

- One trusted operator, trusted OS, and trusted configured Codex or Claude provider.
- Repository, plan, diff, fetched content, and provider output are untrusted data only.
- Ordinary concurrent tool calls are possible; no hostile same-user process races lineage
  paths, no repository-selected code execution, and no compromised provider or OS.
- A lineage has tens to low hundreds of classes and claims. Review results should remain
  useful within minutes; a correction loop must not run indefinitely.
- A false `NOT-BLOCKED`, wrong evidence binding, or silent loss of blocking class state is
  high impact. A visible, recoverable refusal after repeated unresolved corrections is
  acceptable.
- Excluded: multi-tenancy, hostile local races, deliberate state corruption recovery,
  formal proof, and changes to external-claim verification or arbitration.

## Durable control state

Add a closed, versioned `correction_control` object inside `review_state`. It is server-owned
and contains exactly one row per canonical active (nonsuperseded) class:

```json
{
  "version": 1,
  "classes": {
    "<class-id>": {
      "reset_round": 12,
      "reopen_count": 1,
      "last_session_ref": "provider-session"
    }
  }
}
```

The closed schema requires exactly `version` and `classes`; `version` must have Python type
`int` (booleans reject) and equal literal `1`. Every class row requires exactly
`reset_round`, `reopen_count`, and `last_session_ref`. `reset_round` is null or a non-boolean
integer from one through durable `last_round`; `reopen_count` is a non-boolean nonnegative
integer; `last_session_ref` is null or a strict-UTF-8 string of 1 through 256 Python characters
with NUL, CR/LF, C0 controls, DEL, and unpaired surrogates rejected. The bound is characters,
not encoded bytes. Keys are exact IDs of those
classes, including closed nonsuperseded classes. The authoritative
`review_census.normalize_correction_control(review_state, lineage.active())` validator runs
immediately after lineage load and before gate calculation. If the whole object is absent, it
synthesizes every required row in canonical class encounter order with null reset/session and
zero reopen count. A newly minted class receives that default before atomic settlement save; a
replacement successor instead receives the current-round reset below. Unknown fields, malformed
identities, scalar aliases, invalid bounds, orphan rows, and a present object missing any active
class row make review state unavailable. Whole-object absence is the only legacy migration;
malformed or incomplete present control never migrates.

`reset_round` is the last successful class-bound rebut or replacement round. The effective
persistence start is one label after that reset, otherwise the class's durable
`first_round`. `reopen_count` counts reopen waves since the last replacement, successful
class-bound rebut, or completed cold final that leaves the class closed. An intermediate
correction close does not reset history: if the following final reopens it, that is the
repeatable event being measured. `last_session_ref` is updated after a successful settlement
that leaves the class canonically blocking, using `TrackedClass.blocking` rather than one
literal status.

After lineage load and before provider/cache/snapshot work, every tracked caller round label
must be strictly greater than durable `review_state.last_round`. Repeated or backward labels
reject before provider work; forward jumps remain authoritative spans. Failed or rejected
rounds do not advance `last_round`, so retrying their label remains legal after restart.

## Gate semantics

Define:

- `PERSISTENCE_CORRECTION_LIMIT = 6` (twice the existing three-round advisory threshold);
- `REOPEN_CORRECTION_LIMIT = 3`.

Before a `correction` settlement mutates substantive state, compute gates from the prior
lineage and the caller's current round label. A canonically blocking class is gated when its
effective round-label span is greater than six, or when three prior reopen waves remain
undisposed. Caller labels, not an inferred presence count, remain authoritative.

Render the gated rows in the correction prompt, naming the class, span/reopen count, and
the only accepted outcomes. The settlement may proceed only if the canonical class-engine
dry run shows that each gated class is closed or superseded. A replacement is an explicit
disposition; its canonical successor receives a reset at the current label rather than
inheriting an immediately exhausted window. Reclassification that leaves the class
canonically blocking, rotating debt, changing evidence, or merely returning another unresolved outcome
does not satisfy the gate.

If a gated class remains canonically blocking, reject the complete settlement through the existing
bounded semantic validation retry. The diagnostic names the class, measured span/reopen
count, and two exits: perform a class-bound `rebut`, or return a genuine close/replacement
disposition. If the one retry also fails, preserve the existing staged validation-failure
diagnostics and leave substantive review/class state unchanged. Do not add a provider call,
persistence protocol, or partial settlement.

After a successful atomic settlement:

- remove control only for superseded classes; after a successful cold final/clear, retain
  every closed nonsuperseded class's required row but reset it to null reset/session and zero
  reopen count, so a later changed artifact can reload and reopen it;
- increment `reopen_count` once for each class in the round's deduplicated reopen wave;
- initialize a replacement successor with `reset_round` equal to this round and zero
  reopen count;
- update `last_session_ref` only for classes whose canonical `TrackedClass.blocking` is true;
- prune rows for unknown/inactive classes.

A stakes digest change forces the existing broad census but does not erase durable control
before that census settles. Provider, validation, or persistence failure retains the prior
control and prior `review_state.stakes_digest`; that durable mismatch is the recalibration-pending
representation and causes the next call/restart to repeat recalibration. A successful census
atomically resets every surviving active class to that census round with zero reopen count;
reopens caused only by stakes transition do not consume a reopen wave.

## Class-bound rebut settlement

Keep ordinary unbound `rebut` backward compatible and non-mutating. Durable settlement uses an
optional all-or-none quartet: `lineage`, `class_id`, `debt_id`, and `lineage_mode` (`plan` or
`branch`). When present, `rebut` opens the existing lineage latch before provider work, validates
that the class is active and blocking, the named debt is its exact current open debt, and the
stored `last_session_ref` exactly equals the supplied session. It then requests a closed structured
`CONCEDE` or `HOLD` disposition with resolvable evidence. `HOLD` is audit-only. `CONCEDE` closes
only the named debt and closes the class only when no sibling blocker remains; it never grants
clearance, so the normal cold final still governs. Provider failure, mismatched identity/session,
malformed state, unresolvable evidence, or save ambiguity performs no confirmed settlement. The
counter-evidence text is never parsed for identity.

Legacy exhausted classes initially have no stored session. Their first gated correction still
runs the bounded provider attempt and retry but cannot settle another canonically unresolved result. On terminal
gate rejection, persist only the exact latest successful provider session into the control row
alongside existing bounded failure diagnostics; class, debt, claim, and severity state remain
unchanged. The returned trailer then advertises that usable session. If provider execution
produced no session, do not advertise rebut and retain disposition as the only exit. This is a
one-time bootstrap, not an extra model call or clearance path.

The legacy sessionless gate bootstrap remains only a way to establish current reviewer authority;
it does not settle debt or grant clearance. Once authority exists, the exact debt-bound structured
disposition above is the sole rebut settlement path.

## Auditability

Add stable top-level `rendered_trailer` to every `critique_plan` and `critique_branch` audit
record. It is the exact string returned to the caller for every tracked success, validation
rejection, execution failure, pending, and state-unavailable outcome; one-shot calls store null.
It includes `PERSISTENCE`,
`REOPEN-WAVE`, structural failure, attempt counts, and computed convergence. Do not rebuild
it from state during logging. Rebut audit records include the optional lineage/class/debt/mode
binding, the disposition, the complete prior target debt, validated evidence, and whether debt or
class settlement was confirmed.
Tracked review audits also store closed server-owned `correction_gates` as the exact pre-call
ordered rows rendered into the correction prompt (`class_id`, `reason`, `span`, and
`reopen_count`); non-correction and ungated calls store an empty list.

## Rejection atomicity

Capture the pre-prepare substantive class snapshot immediately after lineage load and before
branch exemptions or mechanized sweeps. Terminal staged rejection restores classes, next
sequence, exemptions, legacy class debt, and substantive review/control state from that snapshot
before adding only named bounded failure diagnostics and the optional legacy gate-session
bootstrap. Independently completed and persisted plan claim evidence remains retained. A failed
rollback write is state-unavailable and leaves the latch like any ambiguous lineage save. Test a
mechanized closed class reopened during prepare followed by terminal rejection and restart; the
substantive reopen must not persist.

## Executable acceptance

Tests through production handlers and pure helpers prove:

1. persistence spans 1-6 remain advisory; label 7 rejects a plain correction that leaves
   the class canonically blocking;
2. debt/finding rotation cannot evade the class-keyed gate;
3. a same-round genuine close or replacement passes, while a still-blocking reclassification does
   not; the replacement successor starts a fresh window;
4. three completed reopen waves gate the next plain correction, with deduplication and a
   replacement/rebut/final-clear reset; intermediate close/final-reopen cycles retain history;
   a production lifecycle clears at cold final, reloads the present V1 default row, changes the
   artifact, reopens that same class, and reaches the new three-wave boundary across restarts;
5. the existing validation retry can repair a gated payload by disposing the class, while
   two invalid replies preserve substantive lineage bytes and exact diagnostics;
6. class-bound rebut accepts only the stored current session and all-or-none identity quartet,
   keeps `HOLD` audit-only, and lets validated `CONCEDE` close only the exact named debt and then
   its class only without a sibling blocker; mismatched, failed, or ambiguous cases do not settle;
7. gates and reset state survive process restart, correction cache behavior, and ordinary
   sequential branch and plan use; schema cases cover whole-object absence with zero/multiple
   active classes, complete present rows, missing/extra/orphan rows, every scalar boundary,
   newly minted rows, and malformed present V1 fail-closed behavior;
8. repeated/backward labels reject before provider work, failed-round retry remains legal,
   and a skipped forward label contributes its full span; the matrix runs through both public
   `critique_plan` and `critique_branch`, restarts from disk, and spies zero provider, cache, and
   snapshot work on preflight rejection;
9. stakes recalibration remains pending across failure/restart, and only a successful census
   atomically starts a fresh control window without claiming prior clearance; a high-age fixture
   changes stakes, fails, reloads the retained old digest/control, succeeds, reloads reset fields,
   and proves the subsequent label-7 boundary;
10. audit JSON `rendered_trailer` stores the exact trailer returned by successful, gated-rejected,
   `STATE-UNAVAILABLE`, ordinary provider execution-failure, structural-pending, persistence,
   and reopen-wave paths through production plan and branch handlers; direct equality uses the
   returned trailer suffix, and one-shot audit records store null;
11. README, both critique tools' `round` argument rows, its public `rebut` argument table and
    state/audit operator section, AGENTS.md operator guidance, and the server schema document the
    all-or-none lineage/class/debt/mode binding, structured settlement semantics, current-session validation,
    strict-greater/forward-jump/failed-retry/restart round semantics, failure outcomes, sessionless
    bootstrap, gated recovery, and exact `rendered_trailer`/`correction_gates` presence and meaning.
    One acceptance comparison checks all surfaces against behavior and rejects diagnostic-only wording;
12. one bounded signed-in Codex acceptance calls public `critique_plan` with claim verification
    disabled, a tiny four-line plan, and a source-bound prebuilt plan lineage at `last_round: 6`
    with one blocking class and complete control row. It uses Codex `gpt-5.6-sol` high effort,
    admits at most one correction plus one validation retry, and must observe canonical
    close/replacement or terminal gate rejection. Retain
    `docs/persistent_correction_gate_acceptance_2026-08-23.json` with source revision/hashes,
    plan digest, exact before/after lineage, audit, provider route, attempt ledger/call count,
    elapsed time, durable reload, and returned/audited trailer equality. Construction and replay
    share one validator and fail closed for any mismatch without prescribing provider prose.
    The prebuilt state has phase `correction`, stakes and structural snapshot digests exactly
    matching invocation, caller round 7, class `first_round: 1`, null reset, zero reopen count,
    and open blocking debt bound to that class. Audit retains the server-owned pre-call
    `correction_gates` projection naming that class, persistence reason, and span 7; the shared
    validator requires that exact nonempty projection before accepting either outcome;
13. migrated-session acceptance uses a production handler and exhausted sessionless class:
    failed acquisition advertises no rebut and changes no control, successful terminal rejection
    persists exactly its session, restart renders it, the first bound rebut records one reset with
    no extra call beyond rebut itself, and class/debt/verdict bytes remain unchanged;
14. gate, retention, session, prompt, and trailer cases cover each blocking severity combined
    with `open`, `over-broad`, `malformed`, and `unchecked`, plus closed/superseded and advisory
    controls;
    schema boundaries include version `true`, `false`, `0`, `1`, and `2`, plus session null,
    empty, 1/256/257 characters, forbidden controls, valid non-ASCII, and unpaired surrogate;
15. regression coverage includes staged protocol, census settlement, handler/server schema,
    lineage persistence, and the full suite.

No test claims hostile-race safety, unlimited lineage history, or that rebut itself proves a
class fixed.
