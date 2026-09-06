# Review architecture and performance

Status: reviewed PLAN, amended after round 1; implementation contract.

## Frozen operating model

One trusted local operator and OS run the MCP server and signed-in reviewer CLIs.
Repository, plan, fetched pages and provider bytes are untrusted data; reviewers
do not execute repository-selected code. No hostile same-user race, multitenancy
or compromised OS. Ordinary edits invalidate affected snapshots and block/retry.
Network access uses existing provider routes and server-governed public HTTP(S)
capture. Hundreds of files, tens to low hundreds of claims, three concurrent census
lanes and sequential settlement; useful evidence within minutes. False clearance,
authority errors and wrong evidence binding have high impact; recoverable blocking
is acceptable. Formal proof and universal performance guarantees are excluded.

## Implementation obligations

1. Extract typed pure phase-selection and successor-state decisions from the
   staged handler. Preserve the canonical class engine, JSON protocol, lineage
   storage and atomic save; keep IO outside the decisions.
2. Instrument public dispatch and engine boundaries with total local elapsed time,
   implementation/source identity, prompt/schema hashes, execution settings and
   provider-versus-local duration. Preserve existing audit fields and direct-handler
   behavior. Observability failure cannot discard a review; never sum concurrent
   attempt durations and call that wall time.
3. Bound runner timeout teardown, including ordinary child processes retaining
   pipes. Preserve strict UTF-8, failure taxonomy and existing role timeouts.
4. Use existing audit provenance to route a known rebut session to its provider;
   reject explicit conflicting engines before spend. Never guess an unknown or
   ambiguous session from UUID shape. No new session database.
5. For a valid outstanding class-only closure obligation after correction, use the
   existing cold final role, which assesses every active class and the whole artifact,
   instead of three census lanes plus consolidation. Preserve census for first use,
   migration, changed-clear snapshots, stakes changes and incomplete census state.
   Preserve final engine ownership and never infer successful debt/class closure.
6. Separate persistence checkpoint reporting from JSON-format validation. Preserve
   durable correction limits and bound-rebut exits. A valid correction leaving a
   gated class blocking cannot settle but must not consume a formatting retry solely
   to demand architectural disposition. Preserve evidence and substantive atomicity.
   Malformed output retains the existing bounded retry. No fabricated history counters.
7. Add deterministic navigation for large captured contracts: an exact line-numbered
   Markdown heading index alongside the complete unchanged contract and authority
   fence. Do not truncate the contract or share model conclusions between cold lanes.
   Clarify actual read-only capabilities and unavailable test execution. Document a
   neutral arbitration ballot template and require minimal faithful cleaner edits,
   retaining independent fidelity/advocacy attestation.

## Named acceptance

- A1: pure transition differential cases preserve unchanged state decisions, debt
  IDs, concessions, migrations and final ownership. Only intentional differences
  are class-only final scheduling and persistence-checkpoint retry avoidance.
- A2: production critique_plan and critique_branch deterministic lifecycle fixtures
  prove complete class/member coverage, invalid evidence blocking, ambiguous saves
  visibly unavailable, and one cold final for class-only closure. Never invoke a
  real critique_plan after implementation starts; deterministic handler tests own it.
- A3: real subprocess tests cover capture/streaming success, UTF-8, missing binary,
  timeout and descendants retaining pipes; timeout returns within the requested cap
  plus documented teardown tolerance without shortening role budgets.
- A4: public dispatch tests cover all modes, honest total elapsed time, exact source,
  prompt/schema bindings, failures, known wrong-provider rebut and unknown/ambiguous
  provenance. Metadata does not become an alternate authority for lineage state.
- A5: reproducible offline comparison reports avoided calls on the two changed state
  shapes and preserved substantive outcomes. Separate deterministic replay from live
  quality evidence; include source identity and timing semantics.
- A6: run the full regression suite and mutation checks, preserving old provider
  artifacts as historical. Run a real public branch review on a small fixture and
  record calls, durations and actual output. Never reinterpret old output as current
  live acceptance; update only permitted source bindings with validators.
- A7: run Codex CODE convergence on the resulting branch under the frozen stakes.
  Recurring architectural classes trigger a checkpoint. No PR with unresolved
  required acceptance, test, convergence or operating-model obligations.

## Performance claims and rollout

This delivery can establish avoided model calls on specified states and bounded
timeout teardown, not improved precision/recall on every repository. GitHub #49
remains the durable owner of blinded multi-repository quality benchmarking and
repeated paired provider trials before lane-count/model/final-scope changes. This
branch supplies measurable cases and instrumentation for that acceptance boundary.
Trusted CI import and dependency navigation beyond the heading index remain #52,
requiring exact snapshot/provenance validation; neither is needed for this branch's
bounded claims. Keep all three census lanes, cold-final coverage and external-claim
verification. Do not add a workflow framework, event journal, new cache, trust
boundary or duplicate class engine. Measure production diff size and largest
functions; reassess before any wire-protocol or lineage-schema expansion.

## Resolved PLAN-review decisions

The 2026-09-06 round-1 review found six design gaps. The following decisions
resolve them; implementation acceptance remains CODE review, not another plan seam.

### Checkpoint and recovery

Use an internal typed checkpoint result only after wire, semantic, member, anchor,
predicate admission and canonical dry-run validation succeed. It is not a provider
wire variant. Invalid output still gets the existing one retry; if that repair is
valid but gated, the checkpoint consumes no further call. Mark the actual attempt
`checkpoint`, retain its bounded response/channel hashes in the existing audit,
and render an architecture checkpoint plus an explicit statement that none of its
class/debt operations applied. Keep prior rejected-attempt diagnostics in order.
Keep class/debt/round/correction counters unchanged. Update only existing current
session authority for gated classes from this successfully validated attempt,
including replacing stale sessions. Invalid/absent provider sessions never become
authority. Save that existing state atomically before offering bound rebut; an
ambiguous save is STATE-UNAVAILABLE. Do not create format/validation failure debt
for a semantic checkpoint. Preserve pre-existing unresolved failure state rather
than erase it to enable rebut. Bound rebut still requires a sole exact open target
debt, a currently blocking class, correction phase and matching durable session.
No checkpoint grants clearance. Next actions are evidence-bearing HOLD/CONCEDE,
a coherent artifact repair, or operator architecture/scope disposition; scope
changes require a new appropriately bound contract. A1/A2 additionally cover
existing, missing, stale and invalid session authority; checkpoint after validation
repair; HOLD/CONCEDE; and ambiguous save through both public handlers.

### Rebut routing

Resolve ownership only from server-written top-level successful review envelopes
and explicit attempt_ledger entries with completed or validation-invalid outcomes,
successful return codes and validated nonempty session references. Never search
arbitrary nested provider/caller content. Same-provider observations deduplicate;
different-provider observations conflict. A known owner selects the engine only
when none was explicitly supplied; an explicit conflict blocks before provider
spend. Unknown ownership may proceed only with an explicit engine. Conflicting
ownership always blocks. Malformed/unreadable candidate records make automatic
routing unavailable rather than proving absence; explicit routing remains the
operator's choice unless a known conflict exists. Existing lineage authority still
governs settlement. A4 covers each case, failed/pre-provider caller echoes, duplicate
records and both documented log locations without a new session store.

### Class-only phase eligibility

Only a newly validated correction settlement with no blocking finding debt but
surviving blocking classes earns a class-only final. The current correction engine
owns that final. A validated final with remaining classes retains its existing
owner. Store ordinary `phase=final` and `final_engine`; no new state schema.
An already owned final with class-only blockers stays final on load. Ownerless
historical census/correction, first use, legacy register failure, stakes migration,
changed-clear snapshots and incomplete census never qualify by inference. Keep
their conservative census route. Blocking finding debt always returns correction.
Both public verified-plan deadline admission and staged selection consume the same
pure phase decision. A1/A2/A5 cover exclusions, owner save/reload, foreign-engine
clean finals remaining blocked, follow-up reserve and invalid member/evidence cases.

### Navigation and prompt consumers

Derive the branch contract index from _BranchContract's captured LF-only lines and
render it inside the same declarative authority fence. Index ATX headings outside
backtick/tilde fenced blocks, preserve encounter order and duplicate headings, and
omit empty indexes. Do not alter ArtifactView plan-review semantics. Initial
census/correction/final and their existing retries receive the identical index via
the shared contract renderer; consolidation remains manifest-only. Existing exact
composed prompt caps still block oversized input without contract truncation.
Tests cover LF/trailing-newline coordinates, duplicate headings, fenced examples,
original digest/bytes, every consumer, and unchanged anchor resolution. Capability
guidance must not broaden allowed tools. Cleaner guidance prioritizes minimal edits
and substantive asymmetry over equalization, while existing independent attestation
and caller-advocacy rejection remain required. Add focused prompt and arbitration
regressions and a concrete neutral ballot in public documentation.

### Runner and measurement evidence

Repair background reader/feeder error propagation too: valid provider stdout with
invalid UTF-8 stderr must not parse as success. A3 covers invalid stdout/stderr,
multibyte input/output, cancellation and descendants in both runner modes. Bound
teardown applies to ordinary subprocess descendants within the launched process
group; daemon escape and hostile OS processes remain excluded.
A6 names scripts/run_staged_protocol_mutation_checks.py. Before each selected
mutant, its selected tests must pass unmodified. An intended assertion failure in
a test call can count as a kill; collection/setup/infrastructure/missing-test errors
cannot. Add deterministic classifier tests and a real selected-mutant run. Record
the exact baseline/candidate source digests and distinguish diagnostic source-tree
fingerprints from authoritative review snapshot/contract bindings.
