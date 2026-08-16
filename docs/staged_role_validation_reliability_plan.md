# Staged-role validation reliability plan

## Status and scope

The incident report measured logs through commit `f4fe2cd`. Its aggregate failure rate is
historical evidence, not a current acceptance baseline. Protocol v2 already gives provider and
local validation one closed role schema, supplies the complete pointer-addressed validation
diagnostic to the same-session retry, derives census outcomes and debt, and constrains evidence
anchors to exact `plan|repository:path:line[-end]` strings.

This change addresses the remaining class: the server still asks for a redundant lifecycle mirror,
does not bind each rejected attempt to its own local validation diagnostic, and renders terminal
failure in a success-shaped body. It does not relax anchors, accept malformed JSON, silently dedupe
model decisions, infer an evidenced violation from an action alone, add a retry, or change class
severity/gating semantics.

## Frozen operating model

- Deployment and operators: a local CLI/MCP tool used by one trusted operator on a trusted OS.
- Trusted actors: the operator and local state owner; provider identities configured by the tool.
- Untrusted inputs: repository/plan bytes and provider-produced structured text, treated as data.
- Active adversary capabilities: misleading static repository/web content and malformed or
  internally inconsistent provider output; no repository-selected code execution is implied.
- Concurrency: the existing parallel census lanes and one same-session validation retry per role;
  no hostile same-user process racing paths or state.
- Network boundary: external model providers are reached through the existing engines; live web
  behavior is unchanged and irrelevant to staged structural validation.
- Scale and latency: three census lanes, one consolidation or one follow-up role, tens to low
  hundreds of findings/classes, and useful evidence within minutes.
- Failure tradeoff: false `NOT-BLOCKED`, invented class transitions, and wrong evidence binding are
  high impact; a visible recoverable block is acceptable; avoid spending a second call without an
  actionable diagnostic.
- Exclusions: multi-tenancy, compromised OS/provider, hostile local races, deliberately corrupted
  durable state, formal proof, new persistence, extra retries, and unrelated arbitration/claim work.

## Design

### 1. Derive the remaining lifecycle mirror

For a model-owned `violated` class outcome on a closed, unmechanized class, materialization derives
the canonical `reopen` record when no independent action is supplied. The violated outcome remains
mandatory and retains its evidence plus `new_finding` or `carried_debt` basis; a bare `reopen`
action never manufactures a violation. A supplied `replace` remains legal, and mechanized closed
classes still require an explicit replacement because the new predicate/pathspec is a semantic
choice the server cannot derive. Standalone class actions remain legal under their existing rules.

This makes close and reopen symmetric lifecycle projections of evidenced outcomes without changing
the canonical class engine or durable settlement format.

### 2. Bind every rejected attempt to its own diagnostic

Add one bounded `validation_issue` string to staged attempt records. When local schema, semantic,
anchor, or class-engine validation rejects a provider response, set it on that exact attempt before
retry or failure propagation. Preserve the executable validator's JSON Pointer lines verbatim
within the existing diagnostic bound.

Add the same `validation_issue` to each corresponding `rejected_payloads` entry, beside the exact
role, sequence, reply excerpt, and full-reply digest. The retry record receives the retry's own
issue, not the first issue. Execution failures continue to use their distinct return-code/raw/
detail/stderr channels and do not acquire a fabricated validation issue.

The retry prompt continues to use the exact first validation issue. No hand-maintained row-shape
catalogue or second retry is introduced.

### 3. Make terminal failure unmistakable and report call shape

Render staged failure with an explicit failure-only body headed `STAGED REVIEW FAILED`, stating that
no structural verdict was produced, followed by the bounded diagnostic. Do not emit `What works —
Nothing notable` or any other success-review section.

Add a deterministic trailer line summarizing staged attempt count and validation-retry count on
both success and failure paths. The audit ledger remains authoritative; the trailer is an operator
summary derived from it.

## Verification

- Protocol tests prove an evidenced closed unmechanized violation derives exactly one reopen;
  explicit replacement wins; mechanized violation still rejects without replacement; and a bare
  reopen never creates an outcome.
- Cross-layer settlement tests carry the derived reopen through the canonical class engine and
  durable lineage state.
- Retry tests assert first and retry validation issues (including JSON Pointers) on both attempt
  ledger and rejected payloads, including parallel lane fan-in ordering and terminal persistence.
- Execution-failure tests prove validation diagnostics remain absent while existing engine channels
  remain exact.
- Rendering tests prove failure bodies cannot be mistaken for completed reviews and attempt counts
  match the ledger on success and failure.
- Run focused staged-protocol/review-census/handler tests, then the full suite and one primary staged
  capability end to end before the PR.

## Acceptance

- Every semantic judgement is requested once: violation evidence/basis is model-owned; the
  unmechanized reopen lifecycle row is server-derived.
- Every validation-invalid attempt is self-diagnosing in the audit and rejected-payload ledger.
- The one retry receives the same bounded executable diagnostic later persisted for its source
  attempt.
- Terminal staged failure is visibly failure-shaped and never contains a clean-review claim.
- No anchor relaxation, silent normalization, extra model call, persistence protocol, or weakening
  of class/evidence gating is introduced.
