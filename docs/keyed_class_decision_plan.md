# Keyed staged class-decision plan

## Status and incident

Issue #42 records two current failure shapes in tracked plan and branch reviews: repeated
`class_actions` for one class, including operations impossible for a mechanized class, and
`class_outcomes` for active classes outside a correction role's targeted set. Local semantic and
canonical class validation correctly rejects both atomically. The single same-session retry is
already given the complete pointer-addressed error, but a model can reproduce the same invalid
array because the provider schema still permits the invalid cardinality.

This is one protocol-shape class, not two validator bugs: arrays ask the provider to implement a
partial function from class ID to decision while allowing duplicate, unknown, and irrelevant keys.
The fix makes that partial function explicit at the fresh model boundary. It does not reconcile an
invalid array, silently drop rows, partially settle a review, weaken canonical validation, return
unsettled findings as a review, or add a model call.

## Frozen operating model

- Deployment and operators: one trusted user runs the local MCP/CLI on a trusted OS.
- Trusted actors: the operator, local state owner, and server code. Provider output and repository
  or plan content are untrusted static data; repository-selected code is not executed.
- Active adversary capabilities: misleading static content and malformed or internally
  inconsistent provider JSON. There is no hostile same-user process racing files or refs.
- Concurrency: three census lanes may run concurrently; consolidation or one follow-up runs after
  them. Each staged role retains one same-session validation retry.
- Network boundary: the configured external Codex provider. Live web behavior is outside this
  structural change.
- Scale and latency: tens to low hundreds of findings/classes, four ordinary staged calls plus at
  most one retry per invalid role, with useful evidence expected within minutes.
- Failure tradeoff: false `NOT-BLOCKED`, an invented transition, wrong class binding, or partial
  settlement is high impact. A visible recoverable block is acceptable; repeatedly paying for a
  wire-invalid deterministic register is not.
- Exclusions: multi-tenancy, compromised OS/provider, hostile local races, deliberately corrupted
  durable state, formal proof, new persistence, additional retries, provider-specific fallback,
  permissive normalization, and unrelated claim/arbitration protocols.

## Design

### 1. Replace class-ID arrays at the fresh wire boundary

The model-facing decision schema replaces these two arrays with closed objects:

- `class_outcomes`: property names are the exact class IDs the role must judge; each value is the
  current outcome body without its redundant `class_id` member.
- `class_actions`: property names are active class IDs; each optional value is one independent
  action body without its redundant `class_id` member.

The server generates these properties from the validated active-class snapshot and sets
`additionalProperties: false`. Final requires every active-class outcome key. Correction requires
every class already bound to supplied open debt and no other outcome key. Census continues to omit
model-owned outcomes because integrity assessments are authoritative.

Action value schemas are generated per class. They preserve every currently legal independent
semantic choice but exclude operations that class can never take: mechanized classes cannot emit
`close` or `reopen`, and replacement of a mechanized class requires its violation-only pattern and
literal pathspec. State-dependent and outcome-dependent compatibility remains a local semantic
check because the outcome is in the same response.

JSON object keys are parsed with duplicate-key detection before schema validation. A repeated
class key therefore rejects rather than becoming last-value-wins. Unknown IDs, extra correction
outcomes, legacy arrays, and a value-level `class_id` reject through the existing single bounded
retry.

After wire validation, project the maps in sorted class-ID order to the existing canonical arrays,
restoring `class_id` on each row. Canonical schemas, settlement rows, class-engine records, durable
state, cache data, and audit semantics remain unchanged. There is one fresh wire protocol, not a
durable dual format or permissive alias layer.

### 2. Derive correction findings' violated outcomes

A correction may discover a new occurrence for an active class not already bound to supplied open
debt. Today the response repeats that judgment as both an `existing_class` governing finding and a
`violated` class outcome. Remove the second expression.

For correction only, every validated governing finding classified to an existing active class
deterministically creates that class's violated outcome from the finding's canonical evidence and
`new_finding` basis. Exactly one finding per existing class remains mandatory. If the class is also
in the required debt-bound outcome map, its authored outcome must be violated and bind consistently;
the server does not overwrite a contradictory satisfaction judgment. Final retains model-owned
outcomes for every class because absence of a finding is itself part of the cold judgment. Census
continues to derive outcomes from validated integrity assessments.

This preserves new unrelated findings in a targeted correction without opening the outcome map to
every active class. The finding is the one semantic judgment; the outcome is its deterministic
binding mirror.

### 3. Preserve lifecycle and atomicity

The projected independent action map enters the existing semantic validator. Satisfied open
unmechanized classes derive `close`; violated closed unmechanized classes derive `reopen`;
mechanized closure remains Git-owned; and a violated closed mechanized class still requires an
explicit predicate replacement. Reclassification composes before a derived lifecycle transition,
replacement supersedes derivation, incompatible actions reject, and the canonical class engine
dry-runs the complete register before the one atomic state transition.

Do not collapse repeated transitions, retain an action from a malformed response, or settle only
healthy classes. A wire-invalid response still rejects as a whole with its exact diagnostic and
rejected reply retained. The improvement is that the provider schema no longer offers the invalid
relational shape that caused the incident.

### 4. Role prompts, provider projection, and diagnostics

Update consolidation and follow-up instructions to describe keyed decisions explicitly: one key
per required outcome class, at most one independent action value per active class, and no
`close`/`reopen` for mechanized classes. Render the exact required correction outcome IDs and the
active action-key/action-kind table beside the role schema. The JSON Schema remains authoritative;
the prose is concise repair guidance.

Provider projection may continue removing only unsupported `uniqueItems` and draft metadata. The
keyed shape relies on closed object properties already supported by both providers, not on an
unsupported uniqueness keyword. Local duplicate-key, schema, semantic, anchor, and canonical
class-engine failures continue into the same bounded pointer-addressed retry and audit ledger.

## Verification

- Schema tests prove final requires every exact active-class key; correction requires the exact
  debt-bound keys; census has no model-owned outcome map; and unknown keys, legacy arrays, embedded
  `class_id`, and impossible mechanized lifecycle values reject.
- Raw-JSON tests prove duplicate object keys reject before ordinary parsing for both outcome and
  action maps, with a pointer-addressed retry diagnostic.
- Projection tests prove maps become sorted canonical arrays and historical legal V2 materializes
  identically through an explicit semantic bijection.
- Correction tests prove a new existing-class finding derives one violated outcome; debt-bound
  satisfaction remains authored; overlap requires consistency; duplicate/multiple findings for one
  class reject; and no finding or action can manufacture satisfaction.
- Cross-layer plan and branch tests carry keyed decisions through anchor validation, canonical
  class dry-run, atomic settlement, durable lineage state, rejected-payload diagnostics, and audit.
- Regression fixtures reproduce issue #42's repeated transition, mechanized `CLOSED`/`REOPEN`, and
  extra correction outcome shapes as provider-schema failures rather than late combined-register
  failures.
- Extend the bounded Protocol v2 mutation gate for duplicate-key detection, exact correction keys,
  action-kind specialization, projection order, and derived correction violation.
- Run focused staged protocol/review census tests, the complete suite, the mutation gate, and one
  real signed-in staged CODE lifecycle through the production handler before PR.

## Acceptance

- The fresh provider schema cannot express two actions for one class, an unknown class target, an
  extra correction outcome, or `close`/`reopen` for a mechanized class.
- Correction asks each new existing-class violation judgment once and derives its binding outcome.
- Every historical legal semantic result remains representable and materializes to the same
  canonical settlement and class-engine transition.
- Invalid JSON/schema/semantic output still rejects atomically; no row is deduplicated, repaired,
  ignored, or partially settled server-side.
- The existing retry, diagnostics, response caps, evidence rules, persistence, and convergence
  gating remain unchanged.
