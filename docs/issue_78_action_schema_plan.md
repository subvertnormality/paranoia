# Issue 78: make rejected class actions unrepresentable

## Goal

Stop fresh staged providers from selecting class actions that the canonical settlement
validator will deterministically reject, while preserving atomic settlement and every legal
semantic outcome. The reported failures are `close` paired with a violated outcome and a
severity downgrade on an active class.

## Operating boundary

Paranoia is a trusted-single-operator local tool. Repository, plan, and provider payloads are
untrusted data. Codex and Claude must support the supplied structured-output schema; capability
failure remains visibly blocking. The supported register has at most 100 active classes and one
same-session validation correction. False settlement and inconsistent class/debt state are high
impact; a recoverable rejected round is acceptable. Hostile local races, a compromised OS,
multi-tenancy, corrupted-state recovery, and partial settlement are out of scope.

## Design

1. Keep the canonical action schema and semantic validator unchanged as the durable compatibility
   and defense-in-depth boundary. Legacy/canonical arrays may still express every historically
   legal action, and illegal combinations still reject atomically.
2. Narrow only the fresh keyed provider schema, using the role's exact `outcome_class_ids` and
   each active class's status, severity, and mechanization. A class action slot is `null` or one
   independent action:
   - `close`/`reopen` only when that class has no required outcome in this role, preserving legal
     standalone correction actions;
   - `reclassify`, with an enum containing only the class's current severity and stronger
     severities;
   - `replace`, with the same non-downgrading severity enum. A mechanized class remains mechanized;
     an unmechanized branch class retains both currently legal procedural and mechanized
     replacement shapes.
3. Suppress explicit `close`/`reopen` only when the role requires an outcome for that class. In
   that case they are redundant model mirrors: satisfied open unmechanized outcomes derive close,
   and violated closed unmechanized outcomes derive reopen. Closed mechanized violation continues
   to require replacement. Classes without a required outcome retain their status-compatible
   standalone lifecycle actions. Canonical materialization and the class-engine dry-run remain
   authoritative for every path.
4. Update every model-facing consumer of the contract: census consolidation, correction, final,
   and shared class-decision instructions/rendering. Advertise exactly the values generated for
   each role: server-derived lifecycle when an outcome is required; otherwise status-compatible
   standalone close/reopen; and only non-downgrading reclassify/replace severities.
5. Send the exact same generated schema on fresh and same-session validation-correction Codex and
   Claude routes. A schema/transport mismatch remains a visible capability failure.
6. Do not retain valid subsets of invalid payloads, add a model call, add persistence state, or
   weaken the one atomic transition.

## Acceptance evidence

- Schema tests cover every role, open/closed state, mechanized/unmechanized form, outcome-required
  and outcome-free slot, and severity at the supported 100-class maximum. Outcome-required schemas
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
- Prompt/schema consistency tests cover census consolidation, correction, final, and shared
  rendering, failing closed if advertised actions differ from the generated role/class schema.
- Provider-schema capability tests cover exact compact minimum and 100-class maximum schemas on
  both fresh and resumed Codex and Claude routes, retaining route-specific evidence and visible
  fail-closed behavior for unsupported schema dialect or transport.
- Production-handler atomicity tests submit a mixed payload containing valid findings/debt plus one
  schema-invalid action. Exhausted correction leaves every substantive class, debt, phase, lineage,
  and settlement field byte-identical while retaining bounded diagnostics. An invalid-first,
  valid-retry case applies the complete corrected settlement once through durable reload.
- The full test suite passes. A CODE convergence review checks correctness and reachable bugs under
  the frozen boundary. The acceptance claim is limited to schema-conforming structured providers;
  an unsupported or ignored schema remains a visible provider/capability failure, not a clear. The
  claim is limited to the two reported families—lifecycle/outcome conflicts and severity
  downgrades; other cross-field incompatibilities remain fail-closed in semantic validation and the
  class-engine dry-run.
