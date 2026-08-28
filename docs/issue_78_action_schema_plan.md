# Issue 78: make rejected class actions unrepresentable

## Goal

Stop fresh staged providers from selecting class actions that the canonical settlement
validator will deterministically reject, while preserving atomic settlement and every legal
semantic outcome. The reported failures are `close` paired with a violated outcome and a
severity downgrade on an active class.

## Operating boundary

Paranoia is a trusted-single-operator local tool. Repository, plan, and provider payloads are
untrusted data. Codex and Claude must support the supplied structured-output schema; capability
failure remains visibly blocking. The supported register has at most 500 active classes and one
same-session validation correction. False settlement and inconsistent class/debt state are high
impact; a recoverable rejected round is acceptable. Hostile local races, a compromised OS,
multi-tenancy, corrupted-state recovery, and partial settlement are out of scope.

## Design

1. Keep the canonical action schema and semantic validator unchanged as the durable compatibility
   and defense-in-depth boundary. Legacy/canonical arrays may still express every historically
   legal action, and illegal combinations still reject atomically.
2. Narrow only the fresh keyed provider schema. A class action slot is `null` or one independent
   action:
   - `reclassify`, with an enum containing only the class's current severity and stronger
     severities;
   - `replace`, with the same non-downgrading severity enum and the class's current mechanization
     shape preserved.
3. Do not expose explicit `close` or `reopen` in fresh action slots. They are redundant model
   mirrors: satisfied open unmechanized outcomes already derive close, and violated closed
   unmechanized outcomes already derive reopen. Closed mechanized violation continues to require
   replacement. Canonical materialization and the class-engine dry-run remain authoritative.
4. Update correction/final instructions to describe only `null`, non-downgrading reclassification,
   and replacement as independent model actions, and to state that ordinary lifecycle transitions
   are server-derived from outcomes.
5. Do not retain valid subsets of invalid payloads, add a model call, add persistence state, or
   weaken the one atomic transition.

## Acceptance evidence

- Schema tests cover open/closed and mechanized/unmechanized active classes at every severity.
  Fresh schemas reject explicit close/reopen and every downgrade before semantic materialization,
  while admitting null, same-severity/upgrade reclassification, and compatible replacement.
- Existing canonical semantic tests continue to reject close-with-violation, invalid reopen, and
  downgrade inputs, proving the backstop remains intact.
- Cross-layer tests pass fresh keyed actions through wire decoding, canonical projection,
  materialization, class-engine dry-run, and durable settlement. They prove satisfied open and
  violated closed unmechanized outcomes still derive close/reopen, and mechanized violation still
  requires a mechanized replacement.
- Provider-schema capability tests cover the exact compact minimum and maximum generated schemas
  for Codex and Claude routes so the narrower per-class enums do not exceed or violate supported
  dialects.
- The full test suite passes. A CODE convergence review checks correctness and reachable bugs under
  the frozen boundary. The acceptance claim is limited to schema-conforming structured providers;
  an unsupported or ignored schema remains a visible provider/capability failure, not a clear.
