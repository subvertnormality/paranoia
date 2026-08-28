# Issue 78: make rejected class actions unrepresentable

## Goal

Prevent the two deterministic action failures reported in issue 78 before semantic
materialization: an explicit lifecycle action conflicting with a role-required outcome, and a
severity downgrade. Preserve atomic settlement and every currently legal semantic outcome.

## Operating boundary

Paranoia is a trusted-single-operator local tool. Repository, plan, and provider payloads are
untrusted data. Existing Codex and Claude structured-output routes remain in scope, including
their one same-session validation correction; a capability failure remains visibly blocking.
False settlement and inconsistent class/debt state are high
impact; a recoverable rejected round is acceptable. Hostile local races, a compromised OS,
multi-tenancy, corrupted-state recovery, and partial settlement are out of scope.

## Design

1. Keep the canonical action schema and semantic validator unchanged as the durable compatibility
   and defense-in-depth boundary. Legacy/canonical arrays may still express every historically
   legal action, and illegal combinations still reject atomically.
2. Narrow only the fresh keyed provider schema, using the role's exact `outcome_class_ids` and
   each active class's status, severity, and mechanization. Retain the existing required keyed
   action map and `null` no-action representation; do not introduce a new union, scale, or
   transport contract. A non-null action slot admits:
   - no explicit lifecycle action when that class has a role-required outcome;
   - otherwise `close` only for an open unmechanized class and `reopen` only for a closed
     unmechanized class, preserving legal standalone correction actions;
   - `reclassify`, with an enum containing only the class's current severity and stronger
     severities;
   - `replace`, with the same non-downgrading severity enum. A mechanized class remains mechanized;
     an unmechanized branch class retains both currently legal procedural and mechanized
     replacement shapes.
3. Define the authoritative-outcome matrix explicitly. Census outcomes are server-projected from
   every integrity assessment and census has no model-owned outcome map. Final requires a
   model-owned outcome for every active class. Correction requires outcomes for debt-bound active
   classes; it may additionally derive a violated outcome from a fresh existing-class finding and
   its distinct `assessment_evidence`. For the schema-known census/final/debt-bound correction
   cases, omit lifecycle choices because satisfied open unmechanized outcomes derive close and
   violated closed unmechanized outcomes derive reopen; closed mechanized violation still requires
   replacement. A correction class with no role-required outcome retains its status-compatible
   standalone lifecycle action. If a fresh correction finding later creates an outcome that
   conflicts with such an independently authored action, the unchanged canonical semantic
   validator rejects it atomically. That residual cross-field family is explicitly outside this
   targeted preclusion because it is not knowable when the schema is generated.
4. Update every repository-owned statement of the model-facing contract: census consolidation,
   correction, final, shared class-decision rendering, `AGENTS.md`, and
   `docs/staged_review_protocol_v2_acceptance.md`. Advertise exactly the values generated for each
   role: server-derived lifecycle when an outcome is required; otherwise status-compatible
   standalone close/reopen; and only non-downgrading reclassify/replace severities. Check exact
   prompt/schema value sets in both plan and branch modes.
5. Send the exact same generated schema on fresh and same-session validation-correction Codex and
   Claude routes. A schema/transport mismatch remains a visible capability failure.
6. Do not retain valid subsets of invalid payloads, add a model call, add persistence state, or
   weaken the one atomic transition.

## Acceptance evidence

- Schema tests cover every role, plan/branch mode, open/closed state,
  mechanized/unmechanized form, outcome-required and outcome-free slot, and every severity.
  Outcome-required schemas
  reject explicit close/reopen and every downgrade before semantic materialization. Outcome-free
  correction slots retain only status-compatible standalone lifecycle actions. Null,
  same-severity/upgrade reclassification, and every currently legal replacement shape remain
  admitted.
- Existing canonical semantic tests continue to reject close-with-violation, invalid reopen, and
  downgrade inputs, proving the backstop remains intact.
- Cross-layer tests pass fresh keyed actions through wire decoding, canonical projection,
  materialization, class-engine dry-run, and durable settlement. They prove satisfied open and
  violated closed unmechanized outcomes still derive close/reopen, and mechanized violation still
  requires a mechanized replacement. They also prove legal standalone correction close/reopen and
  both branch replacement shapes for an unmechanized class remain reachable.
- Prompt/schema consistency tests compare exact advertised/generated action sets for census
  consolidation, correction, final, and shared composers in plan and branch modes, including open
  and closed classes, both mechanization states, all severities, every replacement form, and
  required versus absent outcomes.
- Existing provider-route acceptance is rerun on the exact changed schema through fresh and
  same-session correction routes for Codex and Claude. Retained artifacts name the executable,
  engine/model, route and role, exact schema bytes/digest, raw and decoded response digests,
  session identity, and call count, and are replayed through the production decoder. This is a
  regression check of the repository's existing supported routes, not a new claim about a larger
  class-count boundary; rejected, missing, or ignored structured output blocks visibly.
- Production-handler atomicity tests submit a mixed payload containing valid findings/debt plus one
  schema-invalid action. Invalid-then-invalid is inspected before retry, after terminal handling,
  and after durable reload: class register, debt, phase, lineage binding, correction controls,
  claims, plan-contract authority, and settlement fields remain identical, with only the existing
  explicitly enumerated attempt/failure diagnostics changing. Invalid-then-valid applies the
  complete corrected settlement exactly once and proves it after durable reload.
- Residual semantic and dry-run tests enumerate the still-reachable families: debt/outcome and
  finding/basis binding, correction-derived outcomes conflicting with independent lifecycle,
  mechanized satisfaction/replacement, lifecycle composition, class-cap/definition errors,
  classification assessment predicates, and anchor admission. Each rejects before substantive
  settlement with a provider-addressable pointer.
- The full test suite passes. A CODE convergence review checks correctness and reachable bugs under
  the frozen boundary. The acceptance claim is limited to schema-conforming structured providers;
  an unsupported or ignored schema remains a visible provider/capability failure, not a clear. The
  claim is limited to schema-known role-required lifecycle conflicts and severity downgrades;
  correction outcomes derived from a same-response fresh finding and other cross-field
  incompatibilities remain fail-closed in semantic validation and the class-engine dry-run.
