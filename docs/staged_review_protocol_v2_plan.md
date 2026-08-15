# Staged review Protocol v2: one executable contract, fewer model bookkeeping seams

Status: **PLAN-REVIEWED — revision 2, Codex `CONVERGENCE: NOT-BLOCKED` at round 5**

Revision 2 accepts all five governing findings from the tightly staked Codex round-1
census: carried debt now has an explicit class-outcome basis; independently legal class
severity and lifecycle actions remain semantic model decisions; fresh V2 debt uses a
canonical allocator with an explicit V1 comparison bijection; failure atomicity is defined
over substantive state rather than required diagnostics; and `debt_outcome` is a closed
tagged union. The round-3 cold final narrowed `carried_debt` to exactly one durable debt
identity; other historical debts for the same class are updated only through their own
debt outcomes.

Review history under the frozen §0 stakes: round 1 broad census consolidated three BLOCKER
and two MAJOR findings; revision 2 accepted all five. Round 2 targeted correction closed all
five. Round 3 broad cold final found one recurrence in carried-debt cardinality. Round 4
targeted correction closed it. Round 5 unchanged broad cold final returned no findings,
zero open classes, zero structural debt, and computed `CONVERGENCE: NOT-BLOCKED`.

This plan replaces the duplicated model-facing staged-review protocol with one
executable structured-output contract and a deterministic materializer. It does not
weaken evidence resolution, class closure, severity, debt gating, or the atomic state
transition. The model continues to discover defects and make semantic judgements; the
server stops asking it to repeat the same relationship in several bookkeeping tables.

## 0. Frozen operating model

The product is a local MCP/CLI review tool operated by one trusted user on a trusted OS.
The installed, version-pinned Codex and Claude CLIs and paranoia-local's canonical class
state engine are trusted components. Repository snapshots, plans, fetched text, and all
model output are untrusted data. The staged structural path exposes an inert read-only
repository snapshot; repository-selected code is not executed. There is no hostile local
process racing paths.

An ordinary cold review runs three independent census lanes concurrently and one
consolidation call. Correction and final each use one call. Plans contain tens to low
hundreds of claims/classes and evidence must be useful within minutes. Provider network
access is limited to the explicit model call; this internal protocol review does not need
web search, plugins, MCP delegation, or external claim research.

A false `NOT-BLOCKED`, a lost governing finding, a severity downgrade, a wrong evidence
binding, or a class/debt transition applied to the wrong object is high impact. A visible,
recoverable false block is acceptable. Excluded are multitenancy, a compromised OS or
provider, hostile same-user races, formal proof, deliberately corrupted-state recovery,
arbitration redesign, and external-claim redesign. A material change to these stakes
requires operator direction and retriage; review churn must not strengthen them.

## 1. Observed failure and architectural cause

Against `83fc1e6`, seven of forty `critique_plan` calls on 2026-08-13 were rejected after
the expensive review work:

- three responses used `"disposition":"existing_class"` where the validator required
  `"kind":"existing_class"`; the validation retry repeated the same shape;
- two responses cited valid repository line ranges before the resolver accepted ranges;
- one response cited `plan:§0` and one cited `plan:958-969` against a 968-line plan because
  the prompt required exact plan coordinates but displayed the plan without line numbers.

These are not seven independent review failures. They expose two instances of one cause:
the server owns a precise contract that the model is shown only through hand-maintained
prose and examples.

The settlement contract is currently repeated in:

1. `STAGED_CONSOLIDATION_INSTRUCTIONS`;
2. `STAGED_FOLLOWUP_INSTRUCTIONS`;
3. `STAGED_SETTLEMENT_RETRY_GUIDANCE`;
4. `review_census.parse_settlement`'s procedural exact-key checks;
5. the settlement/state materialization rules in `review_census` and `handlers`;
6. tests that construct another spelling of the same rows.

The presentation contract is similarly split: `_plan_body` emits unnumbered bytes,
`PLAN_EVIDENCE_ANCHORS` requires `plan:<line>`, and `resolve_anchors` enforces a coordinate
space that the reviewer cannot see.

The cost of continuing locally is already visible. Since the earlier staged retry work at
`2bebab7`, `handlers.py`, `review_census.py`, `prompts.py`, and `engines.py` have grown by
1,116 inserted and 181 deleted lines; they now total 4,731 lines. This plan is an
architecture checkpoint, not another alias or retry patch.

## 2. Required outcome and preserved quality

Protocol v2 must provide one source of truth for what the model sees, what both providers
are constrained to emit, what the server accepts structurally, and what retry diagnostics
name. It must reduce the model response to semantic decisions and derive redundant state
mechanically.

The following properties remain non-negotiable:

1. Every census source finding is mapped at least once. Fan-out remains legal only when
   one atomic source is evidence for distinct violated existing classes, with one distinct
   governing finding per class.
2. Every required active class is assessed exactly once for that role. A violated class
   maps to exactly one governing finding classified to that same class; a satisfied class
   maps to none.
3. Every governing finding has a severity, summary, remedy, resolvable evidence, and one
   explicit classification: genuine one-off, new reusable class, or existing class.
   Independently legal class severity and lifecycle decisions remain explicit semantic
   actions even when no new finding owns them.
4. Governing severity never downgrades a source finding. Class reclassification or
   replacement never downgrades the active class.
5. Every supplied open debt item receives exactly one explicit outcome. Every blocking
   governing finding and every governing finding attached to a violated class creates one
   open debt record. Advisory debt remains durable but does not enter the computed blocking
   count.
6. The canonical class engine remains the sole authority for registering and applying
   new, close, reopen, reclassify, and replace operations.
7. Evidence anchors must resolve exactly against the pinned artifact or repository. No
   clipping, nearest-line repair, section-anchor fallback, or silent anchor deletion is
   introduced.
8. Substantive review/class state changes only after the complete structural and semantic
   graph validates. Partial settlement cannot clear a round. Required attempt, failure,
   rejected-output, and exact-cache diagnostics may still persist on rejection.
9. Census, targeted correction, and broad cold final retain their current lifecycle and
   bounded model-call counts. Convergence remains computed by the server.
10. External claim verification and arbitration are unchanged.

Structured output reduces protocol failure; it does not establish finding quality. Finding
quality continues to come from the same complete artifact, repository access, independent
lanes, frozen stakes, evidence requirements, correction scope, and broad final regression.

## 3. Design

### 3.1 One artifact view owns plan coordinates

Add an immutable `ArtifactView` constructed once from `plan_text`:

- `lines` is exactly `plan_text.splitlines()`, preserving the current coordinate contract;
- `rendered` is `external_sources.numbered_text(plan_text)`;
- `line_count` is `len(lines)`;
- the original unnumbered bytes continue to govern plan digests, structural snapshot
  identity, claim identity, and persistence bindings.

The staged prompt renders:

```text
=== PLAN — DISPLAYED PREFIXES ARE CITATION COORDINATES, NOT PLAN TEXT ===
00001: first plan line
00002: second plan line
```

`PLAN_EVIDENCE_ANCHORS` says explicitly that the displayed number is the number in
`plan:<line>` or `plan:<start>-<end>`. `resolve_anchors` receives
`ArtifactView.line_count`; no second split or count is permitted. Repository files retain
their current tool-provided line coordinates.

The plan digest and external-claim extractor must never see the prefixed view. Tests cover
empty text, one line, final line, internal and trailing blank lines, Unicode, CRLF input,
and ranges. For every case, the displayed coordinate set and the resolver's valid
`plan:` coordinate set must be equal.

### 3.2 One executable structural contract

Add `src/paranoia_local/staged_protocol.py`. It owns JSON Schema 2020-12 components and
role-specific schema factories for:

- each census lane;
- census consolidation;
- targeted correction;
- broad final review;
- plan versus branch class definitions.

Schemas use `additionalProperties:false`, concrete enum literals, bounded strings and
arrays, and tagged unions with disjoint required fields. Add `jsonschema>=4.23,<5` as an
explicit runtime dependency so the server independently enforces the same schema; provider
enforcement is not trusted.

Extend `Engine.run` and `Engine.resume` with an optional `response_schema`. Codex receives a
secure temporary schema file through `--output-schema`; Claude receives the identical
canonical JSON through `--json-schema`. The temporary file is outside the reviewed
repository, read only for the call, and always removed. Tool, sandbox, web, model, effort,
timeout, and session-resume profiles do not change.

The pinned CLIs advertise structured output on both paths: Codex 0.144.6 exposes
`--output-schema` on `exec` and `exec resume`; Claude 2.1.197 exposes `--json-schema` with
`--resume`. Before the protocol refactor proceeds, a live capability spike must prove for
both providers that:

1. fresh and resumed calls return an object conforming to the supplied schema;
2. the engine extracts the structured object without prose, fences, or markers;
3. an impossible/nonconforming response is an explicit engine or validation failure;
4. structured output does not widen tools or network access.

If any of those fail, implementation stops for a new design decision. There is no fallback
to unconstrained prose plus permissive normalization.

Prompts retain semantic instructions but delete copied row-shape catalogues. Any compact
example is generated from a test fixture that validates against the actual schema. Retry
guidance is generated from bounded validation issues, not maintained as another schema.

### 3.3 The model emits semantic decisions once

The lane report keeps its current semantic content: role/lane, nine checklist coverage
rows, lane findings, and integrity class assessments. Its structure becomes schema-bound.

Consolidation and follow-up responses use these concepts:

```json
{
  "role": "census",
  "governing_findings": [
    {
      "id": "G1",
      "severity": "MAJOR",
      "summary": "concrete defect",
      "evidence": ["plan:42-48"],
      "remedy": "bounded repair",
      "source_ids": ["integrity:integrity-1"],
      "classification": {
        "kind": "existing_class",
        "class_id": "abc123"
      }
    }
  ],
  "debt_outcomes": [
    {
      "debt_id": "D7",
      "status": "open",
      "evidence": ["plan:42-48"],
      "reason": "the cited branch remains reachable"
    }
  ],
  "class_outcomes": [
    {
      "class_id": "abc123",
      "verdict": "violated",
      "evidence": ["plan:42-48"],
      "basis": {"kind": "new_finding", "finding_id": "G1"}
    }
  ],
  "class_actions": []
}
```

Role schemas add only what the role owns:

- census findings require one or more `source_ids`; census class outcomes must exactly
  preserve the validated integrity verdicts and explicitly bind each violation during
  consolidation;
- correction and final findings omit `source_ids`, because each is already a governing
  finding rather than a merge target;
- correction returns one `class_outcome` for each affected class: the union of class IDs
  carried by supplied open debt and classes named by a new existing-class finding;
- final returns one `class_outcome` for every active class and all nine coverage rows;
- every role returns one `debt_outcome` for every supplied open debt item; and
- every role may return `class_actions` for independently legal lifecycle/severity changes.

A `class_outcome` is a closed verdict union. `satisfied` contains `class_id`, verdict, and
evidence and has no basis. `violated` additionally has exactly one explicit `basis`:

- `new_finding` names one governing finding whose classification names that same existing
  class; in census, that finding's `source_ids` must include the lane finding cited by the
  integrity assessment; or
- `carried_debt` names exactly one supplied durable `debt_id`. That debt must already bind
  the class, receive an `open` debt outcome in this response, and retain its existing
  governing-finding identity. No fresh finding or debt is minted. If historical state has
  additional open debts bound to the same class, each still receives its required
  `debt_outcome`, but none becomes a second basis for this one class verdict.

This binding permits a correction to say that an existing-class violation remains without
manufacturing a second occurrence. A satisfied outcome requires every supplied open debt
bound only to that class to close or to remain justified by another explicitly violated
class. Census outcomes must match the integrity manifest's class ID, verdict, and cited
source relationship; correction and final own their class judgements directly.

`debt_outcome` is also a closed tagged union:

- closed: exactly `debt_id`, `status:"closed"`, and current resolvable evidence;
- open: those fields plus a bounded concrete `reason` stating the reachable unresolved
  condition.

Every supplied open debt ID occurs exactly once. The materializer projects these objects to
the current `debt_updates` shape and preserves the durable debt's finding ID, severity,
summary, remedy, source IDs, class IDs, and first-round identity. Unknown, duplicate, or
misbound debt IDs reject the whole decision.

`classification` is a schema-discriminated union:

- `one_off` includes the reason it cannot recur;
- `new_class` embeds the complete new definition and its explicit class severity;
- `existing_class` names the active class and contains no lifecycle operation.

`class_actions` preserves legal class decisions that are independent of a new finding. It
is a closed union corresponding to the canonical engine's `close`, `reopen`, `reclassify`,
and `replace` semantics. Reclassify supplies an explicit non-downgrading severity. Replace
supplies the full successor definition and explicit non-downgrading severity. Plan
definitions use a procedure. Branch definitions use exactly one of a procedure or pattern
plus pathspec.

The server may derive only the already-established redundant transition: an open,
unmechanized class assessed satisfied closes when no class action names it. A violated
closed unmechanized class requires `reopen` or `replace`; a violated closed mechanized class
requires `replace` with a corrected violation-only predicate. Other valid standalone
reclassify or replace actions remain expressible even when no new governing finding owns
them. More than one explicit/derived action against one class rejects.

The model no longer emits:

- fresh debt records or model-chosen fresh debt IDs;
- `source_dispositions` separate from each finding's `source_ids`;
- `assessment_dispositions` separate from class outcomes;
- standalone `class_dispositions` separate from finding classification;
- low-level `class_records`; semantic `class_actions` remain where the operation is not the
  one safe derived close;
- positional `record_index` links;
- duplicated severity, summary, evidence, and remedy fields on debt.

These removed rows are same-response mirrors, not independent checks. Explicit class
severity, carried-debt identity, and independently legal lifecycle actions are not mirrors
and therefore remain model decisions.

### 3.4 Structural validation, semantic validation, then materialization

Replace the mixed `parse_settlement` path with three pure phases:

1. **Decode and structural validation.** Extract one provider-structured object and validate
   it against the exact role schema. Collect all structural issues up to bounded count and
   length, sorted by JSON Pointer.
2. **Semantic graph validation.** Check dynamic source/debt/class completeness, unique IDs,
   source fan-out, severity floors, class state, anchor resolution, coverage binding, and
   replacement rules. Collect independent issues where continuing is safe; do not cascade
   from a missing prerequisite.
3. **Deterministic materialization.** Produce the current internal settlement shape,
   preserve every supplied durable debt ID, allocate canonical IDs for genuinely new debt,
   derive source/class bindings and permitted lifecycle operations, enrich durable debt from
   governing findings, and dry-run the canonical class engine against a copied lineage.

Governing-finding IDs are response-local labels, not authority over durable history. After the
response graph has established that those labels are unique and internally bound, materialization
rekeys any label that collides with a retained historical finding ID to the lowest unused `F<n>`
and rewrites its coverage and `new_finding` basis references. The rename is retained in the audit
settlement. Historical updates still name durable `debt_id` values, so rekeying cannot overwrite or
impersonate an earlier finding. Unknown, duplicate, and misbound response references still reject.

V2 owns one fresh-ID allocator: visit newly debt-bearing governing findings in their
validated response order and assign the lowest unused `D<n>` against every retained open or
closed durable ID. One finding receives exactly one new debt. Existing V1 debt IDs are never
renamed, and all later `debt_outcome` bindings use the stored ID. Model-local V1 labels were
not semantic identity—they were already re-keyed on collision—so the differential harness
compares fresh V1/V2 debt through an explicit bijection keyed by the governing finding's
validated source/class association and stable occurrence order. After applying that
bijection, all debt content and every later update binding must be identical. The plan does
not claim literal equality for arbitrary model-chosen fresh V1 labels.

Only the materialized internal settlement reaches `settle_state`, `apply_register`, review
rendering, logs, or persistence. The durable `review_state` and class-lineage formats remain
unchanged. This avoids a state migration and provides a direct old-versus-new equivalence
surface.

The first invalid attempt receives every bounded actionable issue, for example:

```text
/governing_findings/0/classification/kind: required property missing
/governing_findings/0/classification/disposition: additional property forbidden
```

There remains exactly one same-session validation retry. A second invalid result persists
the exact role, kind, message, attempts, and bounded rejected objects as structural failure.
The server never silently renames `disposition` to `kind`, clips an anchor, invents a debt
row, or infers a missing semantic classification.

### 3.5 Atomicity and bounded failure cost

Atomic settlement remains: a malformed or semantically incomplete response applies none of
its findings or transitions and cannot clear. Acceptance compares the structural attempt's
substantive projection after ordinary stakes/snapshot normalization: review phase, snapshot,
debt content, class map, class sequence, and settled round history. That projection must not
change on rejection. Required attempt telemetry, structured failure/validation debt,
rejected-output diagnostics, and an exactly bound complete-census cache may change and must
persist according to the existing failure contract. Claim evidence deliberately persisted
before structural review is outside this projection. Accepting "everything except the bad
finding" would make the missing finding the easiest route to false clearance and is rejected.

The existing complete-census cache remains the only reuse boundary. A complete validated
set of lanes may be reused after terminal consolidation validation rejection only under the
current exact bindings to mode, snapshot, full prompt bytes, stakes, active classes, debt,
engine/model/effort/web profile, plan coordinates, and cache schema. Incomplete lanes,
mismatches, provider errors, timeout, cancellation, or failed lane retry do not suppress a
fresh census. Protocol v2 bumps the census cache version so V1 prompt/schema artifacts cannot
be reused.

No per-lane persistence, journal, CAS, extra model call, or second retry is added. The cost
control is a smaller constrained response, exact diagnostics, visible coordinates, and safe
reuse of an already complete census—not weaker acceptance.

## 4. Quality risks and controls

### 4.1 A materializer defect could become systemic

The deterministic materializer becomes trusted code. Its primary acceptance gate is
differential equivalence: a corpus of historical valid census, correction, and final
settlements is parsed by the V1 implementation and independently represented as V2 semantic
decisions. Existing durable IDs must remain literal. Fresh model-local V1 debt IDs are compared
through the canonical semantic bijection defined in §3.4; after relabelling, both paths must
produce identical durable debt content, subsequent debt-update bindings, source IDs, class IDs,
class operations, blocking counts, phase transitions, and convergence. Differences require an
explicit reviewed contract change, never fixture normalization.

Mutation tests remove or invert each completeness, severity, evidence, and class-state check.
Every mutant must either be killed or receive a concrete equivalent disposition.

### 4.2 The new payload could lose legal expressiveness

Before V1 deletion, mapping tests cover every currently legal shape: one-off, new plan class,
new branch pattern class, new branch procedural class, existing-class reuse, non-downgrading
new-class severity distinct from occurrence severity, standalone reclassification and
replacement, unmechanized reopen/close, advisory violated-class debt, carried-debt class
violation without a fresh finding, source fan-out, debt stay-open with reason, debt close,
census, correction, and final. V2 is not accepted if any valid V1 semantic outcome lacks one
unambiguous V2 representation.

The carried-debt suite includes a sequential history with two open debts bound to the same
class. One violated class outcome must select exactly one representative durable debt/finding
identity; both debt IDs must still receive independent outcomes, and materialization must not
mint a third finding or debt or collapse either historical record.

### 4.3 Structured output could constrain reasoning rather than shape

Schemas constrain keys, types, enums, uniqueness, and size bounds only. They do not constrain
the model's defect theory, summary wording, remedy, number of findings within existing caps,
evidence choice, severity choice, or classification choice. Prompt and context budgets are not
shortened. The cold census and final remain broad; correction remains targeted.

Live provider acceptance compares a representative unconstrained baseline with structured
output for artifact coverage, finding/evidence content, duration, and token use. This is not a
requirement for identical findings, but any material truncation or loss of evidence is a stop
condition.

### 4.4 Provider schema handling could differ between fresh and resume

Fresh/resume argv tests assert the identical schema digest and unchanged capability flags for
both vendors. Live smoke tests exercise a deliberately invalid first turn followed by a valid
same-session correction. Failure to enforce the schema or extract the corrected object blocks
the cutover.

### 4.5 Displayed line prefixes could contaminate reviewed content

The numbered view is labelled as presentation metadata and is used only for structural review.
Original bytes remain the sole input to hashing, claim identity, external inventory, and stored
plan snapshots. Tests inject text that itself begins with numbers, colons, headings, code fences,
and `plan:` tokens and prove that display prefixes remain distinguishable and anchors still bind
to the original line.

### 4.6 Role differences could disappear into a permissive union

There is no universal permissive settlement schema. Shared components are composed into four
closed role schemas with role `const` values and forbidden irrelevant fields. Tests submit every
role payload to every other role schema and require rejection.

### 4.7 Cutover or cache migration could strand active lineages

The durable state shape is unchanged. V2 materializes the current internal form before state
settlement. Only transient protocol/cache versions change. Old incomplete caches are invalidated;
existing debt and class state are retained. There is one atomic active protocol—no long-lived
V1 fallback whose behavior can diverge.

### 4.8 The refactor could become another subsystem

The change adds no model phase, retry, persistence layer, transport, trust boundary, or external
service. `staged_protocol.py` replaces structural code and prose elsewhere rather than layering
beside it. Before implementation record production diff size and module sizes. Stop at an
architecture checkpoint if:

- production code across `handlers.py`, `review_census.py`, `prompts.py`, `engines.py`, and
  `staged_protocol.py` grows by more than 200 net lines rather than shrinking;
- model-facing top-level relationship tables are not reduced;
- any current legal semantic outcome cannot be represented;
- a second persistence mechanism or additional provider call appears necessary;
- two correction cycles do not reduce blocking findings;
- the live structured-output probes show a material evidence-quality regression.

At that checkpoint choose a narrower contract or no-go; do not patch around the limit.

## 5. Implementation sequence

Use one branch and one atomic protocol cutover, with reviewable commits. Do not ship a durable
dual protocol.

1. **Capability spike.** Prove fresh and resumed structured output on the pinned Codex and
   Claude versions, including invalid-first-turn correction and unchanged tool profiles. Record
   calls, duration, usage, and exact schema digest. Do not change production behavior yet.
2. **Artifact view.** Add `ArtifactView`, numbered staged plan rendering, shared line count, and
   boundary/property tests. This directly repairs the current plan-anchor defect while retaining
   strict resolver behavior.
3. **Executable schemas.** Add the explicit JSON Schema dependency, shared components, closed
   role schemas, local validation, engine schema transport, extraction, and fresh/resume tests.
4. **Semantic decisions and materializer.** Implement graph validation and deterministic
   projection into the current internal settlement, including carried-debt bases, explicit
   class actions, and the canonical fresh-debt allocator/bijection. Add historical differential
   and full legal shape coverage before connecting persistence.
5. **Atomic cutover.** Switch census, consolidation, correction, final, and validation retry
   together. Bump the transient cache/protocol version. Delete markers, fence normalization,
   duplicate row-shape prompt/retry prose, and legacy model settlement parsing.
6. **Documentation and end-to-end acceptance.** Update README and repository instructions before
   review. Run focused tests, full tests, the primary plan lifecycle end to end on a disposable
   lineage with a real provider, and record model calls, elapsed time, diff size, and largest
   modules.
7. **Review.** Run a tightly staked PLAN review before implementation. After implementation run
   tightly staked CODE convergence against the branch/diff. Accept findings through one coherent
   correction; a recurring or architectural class returns to the checkpoint instead of growing
   the mechanism.

## 6. Acceptance matrix

The implementation is complete only when all rows pass:

| Surface | Required evidence |
|---|---|
| Coordinate identity | For representative plan bytes, first/middle/final displayed numbers equal the resolver's valid coordinates; overrun and malformed anchors still reject. |
| Provider enforcement | Fresh and resume on Codex and Claude enforce the same schema digest and return a structured object without prose/fence parsing. |
| Role closure | A payload valid for one role is rejected by every incompatible role schema. |
| Dynamic completeness | Missing, duplicate, unknown, or misbound sources, debts, carried-debt bases, classes, findings, coverage IDs, or anchors block before materialization. |
| Debt outcomes | Closed outcomes have identity/status/evidence only; open outcomes additionally require a bounded concrete reason; every supplied ID occurs exactly once and retains its governing identity. |
| Severity | Source and class downgrades block; a new class retains its explicit independent severity; advisory violated-class debt persists but does not gate. |
| Class lifecycle | New plus standalone close, reopen, reclassify, and replace decisions dry-run through the canonical class engine and match current legal semantics. |
| Fan-out | One source may reach several governing findings only for distinct matching violated existing classes. |
| Atomicity | Every injected structural, semantic, anchor, or class-engine error leaves the defined substantive projection unchanged while required failure/rejected-output/cache diagnostics persist. |
| Differential equivalence | Historical valid V1 artifacts and equivalent V2 decisions preserve existing IDs and, after the documented fresh-ID bijection, produce identical debt content/update bindings, operations, phases, trailers, and convergence. |
| Historical failures | Line ranges resolve; the plan reviewer sees exact coordinates; `disposition`/`kind` drift is provider- and server-rejected with a JSON Pointer before state settlement. |
| Primary lifecycle | Real-provider census → correction → final reaches the expected computed verdict without fake-backed adapters standing in for the capability. |
| Cost and size | No additional model calls; full review remains within existing timeouts; production code stays within the change budget and preferably shrinks. |

## 7. Explicit non-goals

This plan does not add section anchors, accept unresolved evidence, normalize model aliases,
apply partial findings, increase retries, shorten review quality budgets, cache incomplete lane
sets, change durable lineage format, alter external claims, redesign arbitration, add hostile-race
defences, or claim that structured output improves the reviewer's substantive judgement. It makes
the existing quality contract visible, executable, smaller, and harder to contradict.
