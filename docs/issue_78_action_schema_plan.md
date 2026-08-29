# Issue 78: make staged action validation repairable

## Goal

Stop the issue-78 sequence in which the same correction gate first rejects a payload, then the
single validation retry chooses a different illegal action and discards the round. Preserve the
atomic settlement boundary: findings, debt, outcomes, and actions settle together or not at all.

## Operating boundary

Paranoia is a trusted-single-operator local tool. Repository, plan, and provider payloads are
untrusted data. Codex and Claude correction/final roles and one same-session validation correction
are in scope. False settlement and inconsistent class/debt state are
high impact; a recoverable blocked result is acceptable. Hostile local races, compromised OS,
multi-tenancy, corrupted-state recovery, partial settlement, extra reviewer calls, schema changes,
and new persistence mechanisms are excluded.

## Evidence and disposition

The issue's two terminal rounds shared one shape. Their initial correction payloads failed the
persistent correction gate. The generic retry then failed on `close requires satisfied outcome`
in round 20 and `cannot downgrade active class` in round 22. The retry prompt currently supplies
only the bounded error plus “fix every violation”; its `retry_context` carries only an optional
branch plan contract. The next round's staged task carries debt, classes, gates, and artifact, but
not the preceding terminal validation issue.

Do not implement the issue's suggested per-action partial settlement. An action is not independent
of its class outcome, finding basis, debt result, correction gate, or successor identity. Keeping
the surrounding rows after any one of those relations fails validation would weaken the existing
single canonical dry-run and atomic transition.

## Design

1. Keep the provider schema, canonical semantic validator, class-engine dry-run, correction-gate
   semantics, one retry, and atomic state transition unchanged.
2. Extend the existing server-owned class-decision instructions; do not structurally constrain or
   remove any action. For each active class, render current status, severity, mechanization, the
   complete state-compatible lifecycle choices, every legal same-or-stronger reclassification
   severity, and both legal unmechanized replacement forms. State the canonical cross-field rules:
   census outcomes are derived from integrity assessments; final outcomes are authored for every
   active class; correction outcomes are authored for debt-bound classes, while a fresh finding may
   author the debt-bound outcome through exact `new_finding` basis or derive a distinct
   non-debt-bound violated outcome through `assessment_evidence`; `close` requires a satisfied
   outcome when one exists; `reopen` requires a violated outcome when one exists; and replacement
   preserves mechanization and may not downgrade. Outcome-free standalone close/reopen remain legal.
   A correction-gate section names only gated classes and explains that they must become
   nonblocking: a violated gated class needs a valid replacement, while a satisfied open
   unmechanized class is closed by the existing derivation; retaining a blocking severity cannot
   satisfy the gate.
3. Put those exact instructions in the original census consolidation, correction, and final prompt
   in plan and branch modes. The existing same-session retry retains that original provider context
   and adds the bounded executable validator issue; keep its branch-plan-contract resend unchanged.
   Do not duplicate a second repair catalogue or parse provider prose.
4. Leave terminal failure persistence unchanged. Its bounded role/message, rejected-payload
   diagnostics, and trailer remain visible, but no new cross-round repair context or failure
   discriminator is added.
5. Update the applicable `CLAUDE.md` summary and staged Protocol v2 acceptance documentation to
   describe the repair guidance, one-retry bound, and unchanged atomicity. `AGENTS.md` already
   governs the same-session retry, canonical semantic validation, legal action surface, and atomic
   settlement, so record an explicit no-change disposition rather than perturbing source-bound
   historical acceptance.

The documentation edits are closed: leave `AGENTS.md` under “For the staged Protocol v2 cutover”
unchanged for the reason above; amend `CLAUDE.md` under its staged Protocol v2 summary and
`docs/staged_review_protocol_v2_acceptance.md` under “Keyed class decisions”. Each must state the
four outcome-authority paths above, outcome-free standalone lifecycle legality, non-downgrading
severity, both procedural and mechanized replacements for an unmechanized branch class,
mechanization-preserving replacement for a mechanized class, the unchanged 100-active-class
boundary and schema identifiers, the single retry and provider-failure behavior, unchanged durable
terminal diagnostics, and all-or-nothing settlement. A named test reads those three sections
and asserts the shared normative sentences/identifiers are present; publication blocks if it fails.

## Acceptance evidence

- Replay the two issue-78 payload shapes using production parsing: a correction-gate rejection
  followed by (a) close with a violated outcome and (b) a severity downgrade. Assert that the retry
  prompt contains the exact class-specific legal alternatives and expressly says that neither
  attempted action satisfies the gate.
- Run invalid-then-valid production-handler cases for plan and branch correction. The valid retry
  uses replacement for a violated gated class and settles findings, debt, outcome, action, and
  successor exactly once through durable reload. Include mechanized and unmechanized replacement
  shapes and every blocking severity floor.
- Run invalid-then-invalid cases. Before retry, after terminal handling, and after durable reload,
  class register, debt, phase, lineage binding, correction controls, claims, plan-contract
  authority, and settlement fields remain unchanged except for the existing enumerated diagnostic
  ledger/failure fields.
- Exercise the same `_staged_call` retry consumer through the actual top-level `critique_plan` and
  `critique_branch` production handlers for census consolidation, correction, and final. Use one
  durable plan lineage and one durable branch lineage across save/reload boundaries. For each role
  and mode, cover invalid-then-valid and invalid-then-invalid. In every exhausted case, compare the
  pre-round substantive state with durable reload allowing only the existing enumerated attempt,
  rejected-payload, and failure diagnostics. A later valid settlement atomically clears the
  existing terminal failure.
- Exact initial-prompt tests cover census consolidation, correction, and final; plan and branch modes;
  open/closed and mechanized/unmechanized classes; required and absent outcomes; all severities;
  correction gates; and branch-contract ordering. At the existing 100-active-class maximum, render
  the most verbose legal metadata, all gates, and a branch contract; prove the exact initial and
  retry prompts remain below their production bounds and
  pass strict UTF-8 preflight. Overflow remains visibly fail-closed before a provider call.
- Existing canonical semantic and dry-run tests continue to reject lifecycle/outcome conflicts,
  downgrades, invalid replacement, finding/basis/debt mismatches, and incompatible action
  composition before substantive settlement.
- Positive transition coverage enumerates outcome-free standalone close/reopen, derived close for
  open unmechanized satisfaction, derived reopen for closed unmechanized violation, required
  mechanized replacement, same-severity and stronger reclassification, both legal unmechanized
  branch replacement definitions, and mechanization-preserving replacement. Negative coverage
  enumerates close/reopen against incompatible authored, census-derived, debt-bound correction,
  debt-bound fresh-finding, and non-debt-bound fresh-finding outcomes, plus downgrade and
  mechanization loss. All run through guidance rendering, canonical semantic validation, dry-run,
  and atomic settlement or rejection as applicable.
- Run the focused suites and full suite. Then perform one bounded CODE convergence lineage under
  the frozen stakes. No live provider capability acceptance is required because provider schemas,
  routes, call counts, and transport are unchanged; the CODE review itself exercises the external
  Codex route.
