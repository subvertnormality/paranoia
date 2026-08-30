# How Paranoia Local works

This guide explains the behavior behind the public tools. Start with the
[README](../README.md) for installation or the [tool reference](tool-reference.md)
for exact inputs.

## Cross-agent review

Paranoia Local is a local MCP server. The calling coding agent sends a review
request; Paranoia starts the other vendor's signed-in CLI as a read-only reviewer
and returns the result through MCP.

The reviewer is intentionally cold. It receives the artifact, repository
evidence, request context, and durable state required for its role. It does not
inherit the calling conversation's rationale or its normal user tool configuration.

## Stakes define the boundary

`stakes` should describe the deployment, operators, trusted actors, untrusted
inputs, active adversary capabilities, concurrency, network boundary, scale,
useful latency, consequences of false clear versus false block, and exclusions.

The reviewer drops or labels concerns that require conditions outside this
boundary. If `stakes` is omitted, Paranoia assumes a modest internal tool with
trusted operators and no hostile local process. Pass `stakes: "unstated"` when
that default is deliberate.

## The tracked lifecycle

Tracked review is the default for `critique_branch` and `critique_plan`.

1. **Census:** three independent cold lanes inspect the complete artifact. A
   separate call consolidates their validated findings into durable debt.
2. **Correction:** later rounds target open debt, claimed fixes, and their
   transitive effects.
3. **Final:** after debt closes, one fresh whole-artifact regression must pass.

For plan review only, a correction that starts with one or two blocking units is
a closure candidate. Its existing single reviewer call also receives the full
nine-item checklist and must search the complete plan for sibling occurrences,
cross-reference contradictions, and repair-created regressions before closing
debt. A blocking unit is an active blocking class, plus an unbound blocking debt
that has no such class. This broader search is intended to reduce repeated
correction/final cycles; it does not guarantee a fixed round count and cannot
clear the lineage. The independent cold final remains mandatory. Branch
correction is unchanged and remains targeted.

A clear census can converge immediately. Otherwise, increase `round` after each
successfully settled edit. Failed or rejected rounds may reuse their label.
Repeated or backward labels after settlement block without provider spend.

## Findings, classes, and closure

A finding is one observed defect. A class is its reusable violated invariant.
Every governing finding is classified as a one-off, the first instance of a new
class, or an instance of an active class.

Blocking findings and classes gate convergence. `MINOR` and `OUT-OF-SCOPE`
entries remain durable but advisory.

### Branch classes

Mechanized branch classes have a pattern and literal path scope. Paranoia reruns
the predicate against later snapshots; zero matches closes it and a new match
reopens it. Invariants that cannot be represented safely carry a review procedure
and require an explicit reviewer decision.

Before a new or replacement predicate is stored, it must match a repository line
cited for that violation. Admission and closure sweeps share one bounded grep-time
budget and reuse exact results for the immutable reviewed snapshot; an exhausted
budget blocks an uncached candidate instead of admitting an unchecked class, while
an already computed exact result remains usable without more execution.
Retained public acceptance for this lifecycle is source-bound to both admission
validation and the class-closure executor that performs the durable successor sweep.

An exact match can be marked as a false positive with `exempt`. The exemption
binds class, path, line, and exact line text and expires when the text changes.
`unexempt` revokes it. Later reviewers see and may challenge exemptions.

### Plan classes

Plan classes are procedural because a regex over prose could disappear while the
design defect remains. Later reviewers receive the invariant and procedure, and
blocking plan classes require explicit evidenced closure.

Plan review judges whether an in-scope future obligation is bound to named scope,
executable acceptance evidence, and fail-closed behavior. It does not require
runtime artifacts that can exist only after implementation. Code review owns the
implemented result.

### Persistence and rebuttal

When a blocking class persists across enough round-label span or repeatedly
reopens, Paranoia stops accepting another ordinary correction. The class must
close, be replaced with a more accurate invariant, or receive a class-bound
`rebut` using the reported current session and exact debt ID. `HOLD` is
audit-only. A validated `CONCEDE` withdraws only that debt and closes the class
only when no sibling blocker remains. It does not grant clearance; the normal
cold-final lifecycle still decides convergence. Its citations use the staged
anchor grammar and must resolve against the repository or retained plan line bound
before settlement.

## Plan contracts in branch review

`critique_branch` can receive `plan_text` or an absolute `plan_path` as an
implementation contract. On the first plan-bearing round, Paranoia reads it once,
computes its full SHA-256, stores a versioned authority record, and binds that
captured contract to the Git snapshot, every staged role, class state, and audit.

Reviewers check plan obligations for implementation or traceable deferral, named
acceptance criteria through their named production entry points, and new public
or persisted contracts for correspondence with the plan. The contract remains
declarative data and cannot instruct the reviewer.

Later rounds reuse the exact stored text. Adding, removing, or changing the
contract requires a new lineage. One-shot review rejects plan contracts because
it cannot provide the same binding.

## External claim verification

`critique_plan` verifies eligible external premises by default before structural
review.

### Eligible claims

The register contains only atomic, load-bearing propositions in three categories:

- `fact`: external state, event, quantity, identity, or history;
- `design_principle`: a requirement or recommendation from the governing
  external standard, regulator, protocol, platform, or vendor; and
- `behavior`: behavior promised by an external dependency, API, platform,
  protocol, service, or runtime.

Repository state, implementation conformance, internal history, and
project-authored choices stay in structural review and tests.

### Evidence boundary

Verification has four stages:

1. The reviewer uses built-in search only to inventory claims and discover URLs.
2. Paranoia downloads public HTTP(S) pages and extracts main text with Trafilatura.
3. The same session, now without browsing, binds exact captured passages to claims.
4. A separate cold, tool-free attester judges authority and entailment.

Provider summaries, snippets, and provider-fetched bodies are never evidence.
Claude `WebFetch` is not used. Known UGC can provide leads but cannot govern
closure. A repository's own web URL remains self-context, not evidence for its
plan. Redirect destinations determine source eligibility and identity.

HTTP 403 receives at most one browser-compatible same-URL retry. Paranoia does
not add cookies, browser automation, mirrors, or access-control bypasses.

### Outcomes and later rounds

A claim is `supported` only when authoritative captured text entails its exact
wording; otherwise it is `refuted` or `unverified`. Both latter states block
combined plan convergence without rewriting independently settled structural
state.

Actionable packets include plan wording, atomic proposition, canonical URL,
location, publisher/authority, exact passage, and a replacement only when the
replacement is itself entailed. Refutation does not prove substitute wording.

Round 1 performs exhaustive inventory. Exact unchanged supported claims keep
their packets without new search. Edited, new, refuted, and unverified claims
re-enter full verification. Claim identity includes the assertion-bearing block,
heading ancestry, and list ancestry.

The path is bounded to 200 candidate sources, five binding batches, five cold
attestation batches, and 22 possible model calls including reserved corrections.
These are pathology circuit breakers. Oversized or unavailable sources fail for
the affected claim rather than being silently truncated.

See [`claim_verification.md`](claim_verification.md) for protocol-level detail.

## Arbitration

`arbitrate` pins one Git snapshot and gives both deciders separate inert views of
the same regular-file bytes and bounded history. It does not run repository Git
filters, hooks, text conversion, configured transports, executables, or symlink
traversal. Ref movement during setup fails before model spend; later movement is
reported but cannot alter the pinned evidence.

With `clean: true`, Claude Opus removes advocacy and presentation asymmetry, and
Codex attests that substantive meaning was preserved. Caller `context` and
`stakes` remain byte-for-byte authoritative and are checked separately. Deciders
see opposite option order under opaque labels and are unaware of each other.

Research is on by default. Both vendors discover URLs; Paranoia downloads,
extracts, deduplicates, and binds the sources, then sends identical captured
evidence to both deciders with live web disabled. A decisive vote must cite a
repository line in the snapshot or a captured source that passes authority,
entailment, and decision-relevance checks.

Python compares the votes. One fact-only reconciliation can run on divergence
when new evidence exists; it carries server-read bytes and citations, never the
sibling model's prose. Results are `CONVERGED`, `BLOCKED`, `REFRAME_REQUIRED`,
`UNRESOLVED`, or `FAILED`.

The whole call has a 7,200-second circuit breaker. Cleaning/attestation calls use
420-second phase limits, decision calls 1,800 seconds, and the research group
1,440 seconds. See [`arbitration_plan.md`](arbitration_plan.md) for residual risks.

## Safety model

- Reviewer subprocesses are read-only; the calling coding agent owns edits and tests.
- Codex starts without user-configured MCP servers or tools. Claude starts
  without user/repository settings that could expand its allowlist.
- Committed branch reviews normally use a temporary worktree. Dirty review reads
  the live tree. Verified plans and arbitration use inert materializations.
- A hard crash can leave temporary worktree registration or unreferenced Git
  objects until `git worktree prune` or `git gc`; the working tree and index are
  not changed.
- Paranoia uses already authenticated local CLIs. It needs no API key and adds no
  Paranoia telemetry.
- Public HTTP(S) capture occurs only for enabled claim verification and
  arbitration research.

## Audit logs and durable state

Every call writes a JSON audit record under `~/.paranoia/logs/` by default. It
includes inputs, engine/model identity, round, sessions, timings, attempt ledgers,
bounded provider channels, review text, and the returned trailer.

Tracked state lives under `~/.paranoia/lineages/` and atomically stores findings,
classes, phase, claim packets, contract authority, and persistence controls. Set
`PARANOIA_STATE_ROOT` to relocate it. `--log-dir` never moves lineage state.

If state is unreadable, unwritable, or ambiguous, Paranoia reports
`STATE-UNAVAILABLE` and does not present unconfirmed in-memory counts as durable.
Audit logs are diagnostic, not a recovery protocol.

## Usage and failure behavior

- A tracked census normally uses three concurrent calls plus consolidation.
- Correction and final use one main call; each staged role can receive one
  bounded same-session validation correction.
- A late plan correction may broaden the search within that same main call; it
  does not add a role or another provider call.
- Verified plan round 1 adds discovery, binding, and cold attestation.
- `query` is the lower-cost focused operation.
- `arbitrate` is the only tool that spends from both subscriptions in one call.

Malformed output, unsupported structured output, provider errors, timeouts,
missing executables, capture failures, and ambiguous persistence block visibly.
None becomes an empty successful review. Validation-invalid responses receive at
most one role-specific correction; execution failures remain distinct.

The primary staged-failure headline preserves that taxonomy: provider and local
engine outcomes render as `engine failed (<kind>)`, schema or semantic rejection
as `staged rejected (validation)`, and reserve exhaustion as
`staged blocked (deadline)`. These labels also appear in `CLASS-REGISTER`, so a
transient provider failure cannot be mistaken for repeated structural rejection.

Persistent correction control stores `reset_round`, `reopen_count`, and
`last_session_ref`. A load-bearing `CORRECTION-GATE` is projected from
`correction_gates` into the exact `rendered_trailer`; only an exact
validation-invalid terminal retry may recover a previously sessionless gate.

A failed staged structural review begins `# STAGED REVIEW FAILED` and states
whether failure occurred before settlement or after unconfirmed persistence. It
never renders a clean-review scaffold.
