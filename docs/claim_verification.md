# Plan claim verification

`critique_plan` has two modes:

- closure mode (the default): a blocking research-and-verify preflight followed by
  structural critique, with one combined claim/class `CONVERGENCE` verdict;
- one-shot mode (`class_closure: false`): one ordinary structural review, no research,
  lineage state, terminal registers, or convergence trailer.

There is no closure-enabled off or shadow setting. `claim_verification` may be omitted or
set to `blocking`; any explicit claim mode with `class_closure: false` is rejected.

## What the gate proves

The gate proves a negative about the registered set: no active registered load-bearing
fact is unresolved, contradicted, stale, disputed, malformed, or unchecked, and no
blocking defect class is open. It does not prove that claim extraction was complete,
that a source is true, that semantic entailment is mathematically correct, or that two
models cannot share a misconception. `NOT-BLOCKED` is not an approval.

## Round topology and trust boundary

One closure round performs these stages:

1. Read the exact plan bytes and expose ordered opaque span IDs beside bounded display
   text. Models reference span IDs; the server owns byte offsets and hashes.
2. Snapshot tracked and non-ignored untracked repository bytes by opening exact files with
   no-follow semantics, hashing through `git hash-object --stdin` (never repository
   filters), and inserting explicit object IDs/modes into a private index. Hooks,
   fsmonitor commands, filters, attributes, aliases, and pagers are disabled or bypassed.
   Synthetic commits explicitly disable signing, including repository-configured GPG
   programs.
   Inherited Git environment is cleared, native linked-worktree object storage is the only
   approved object database, alternates and symlinked object-store components are rejected,
   and grafts/replacement objects are disabled for snapshot and history operations. Lazy
   fetching is disabled, so a partial
   clone with missing objects fails closed instead of invoking a configured promisor remote.
   Ignored untracked paths and unsupported FIFOs/sockets/devices are JSON-escaped,
   disclosed, and unavailable. Ignored regular directories are pruned from the bounded
   special-entry walk, so a large ignored build tree cannot exhaust that scan. A temporary
   `refs/paranoia/plan-snapshots/...` namespace pins the wrapper and initial history roots
   against concurrent pruning.
3. A fresh toolless research role registers load-bearing claims. The server parses its
   strict JSON immediately into a non-durable draft and mints durable-style IDs before
   later roles need to refer to them.
4. A toolless evidence-planning role emits bounded structured requests. The server alone
   executes `LIST_TREE`, `READ_BLOB`, `SEARCH_LITERAL`, and configured external search.
5. A toolless verifier sees exact server evidence bound to the exact claim ID that
   requested it; evidence for one claim cannot authorize another. Every model-visible source, path,
   metadata object, and passage is injectively JSON escaped. Remote passages are framed
   as untrusted JSON data and never share a call with repository bytes.
6. A fresh toolless structural reviewer sees the plan, repository evidence, external
   metadata, active claims, and existing class procedures. It emits one atomic PLAN and
   CLASS register. Like every other role, it receives plan bytes only inside ordered,
   injectively JSON-escaped `SPAN` data records; raw plan prose is never interpolated as
   peer-level prompt control text.
7. Python validates role permissions, applies both registers to drafts, roots exact
   evidence bytes, atomically replaces lineage state, and computes one trailer. An
   atomically exclusive per-lineage latch rejects concurrent rounds before either can
   construct a stale draft.

For Claude, toolless means bare settings, an empty allowlist, an explicit deny list, an
empty `--tools` availability set, and strict empty MCP configuration.
For Codex on Linux, the native binary runs inside a `bwrap` mount namespace containing an
empty working directory, auth, TLS/DNS files, and no shell, repository, common Git store,
or sibling worktree. Shell, unified execution, multi-agent, apps, browser/computer, code,
image, goals, and workspace-dependency feature schemas are explicitly disabled under
strict configuration. Native web is forced off for every claim-verification role. If that
boundary cannot be constructed, the round fails closed and the lineage is unchanged.

## Claim state

Claims persist in schema-version 2 of the existing plan lineage envelope. Branch lineage
JSON and branch output remain on their existing representation.

The important orthogonal fields are:

- kind: `fact | decision`;
- assertion mode: `asserted | assumption | estimate`;
- kind classification: `proposed | confirmed`;
- bearing: `blocking | advisory`;
- status: `unchecked | unverified | verified | contradicted | disputed | deferred |
  stale | malformed | not-applicable | superseded`.

Every new claim starts `proposed`, `blocking`, and `unchecked`, regardless of what the
extractor proposed. A different role must confirm its kind. Advisory bearing is reachable
only through the verifier's evidence-bearing `SET_BEARING`; it cannot be set on `ADD`.
Facts block until verified or safely deferred. Decisions become `not-applicable` only
after cross-role kind confirmation and block again if a plan edit or dispute makes them
stale/disputed. Evidence disputes are accepted only for cross-role-confirmed factual
claims. Omission never deletes a claim.

Plan edits relocate a claim only when its exact anchored bytes occur uniquely. Missing or
ambiguous anchors become stale. Deferred claims additionally invalidate when their plan
ordering snapshot changes.

## Evidence

Repository records contain the pinned commit, literal path/query or requested byte range,
underlying blob/ref object identity, exact original bytes,
source and passage hashes, byte bounds, and separately decoded display text. Lossy display
text is never evidence identity.

Persisted records have an exact per-kind metadata schema, including nested collection
types and empirical input hashes. Before cache evaluation, every retained truth, bearing,
dispute, deferral-authorization, or other claim dependency must resolve to one valid record
bound to that exact claim. Missing, malformed, mismatched, or wrong-claim dependencies stale
the claim and leave it blocking.

The initial empirical adapter set is deliberately narrow: `PYTHON_COMPILE` compiles up to
20 pinned Python blobs without executing them and records the fixed recipe, interpreter
version, input hashes, structured results, exit status, and falsifying result. It is
invalidated by any runtime or input change. Arbitrary model-authored commands and shell
strings are never accepted.

`READ_BLOB` accepts a nonnegative byte offset and bounded length. An evidence planner can
use a literal-search byte position to retrieve relevant code after the first display
passage without widening the 1 MiB source cap or 5 MiB round cap. Fixed adapters charge
every input byte they inspect, not only their small structured result.

External work requires a trusted process-level HTTPS JSON search endpoint. Repository
configuration cannot select a network destination:

```bash
export PARANOIA_SEARCH_ENDPOINT='https://search.internal.example/query?q={query}&limit={limit}'
```

The endpoint must return `{"hits":[{"url":"https://…","title":"…"}]}`. Fetching
preflights the template and permits only `{query}` plus optional `{limit}` placeholders.
Top-level and hit objects use exact schemas and reject duplicate or unknown JSON keys.
Formatting errors are blocked network-evidence failures, never raw exceptions. Fetching
rejects credentials, non-HTTPS URLs, any DNS answer that is non-public, a connected peer
different from the selected address, unsupported media/encodings, excessive redirects,
non-ASCII/non-percent-encoded URL data, hard total deadlines, and streaming compressed or
decompressed byte caps. Every redirect hop consumes a fetch attempt, and every response
body is charged before redirect, status, media-type, or decoding acceptance; decompressed
output is additionally capped by the aggregate bytes still available before inflation and
charged as it is produced. DNS resolution, connect, TLS, headers, redirects, and body reads
and decompression all share the same enforceable total deadline. With no endpoint, external research
explicitly abstains and an otherwise unresolved external premise blocks.

Exact bodies live under `$PARANOIA_STATE_ROOT/evidence/sha256/`. In-flight journals and
lineage root manifests are GC roots. A global file lock serializes reservation, blob
write, exact live-root replacement, and sweep. Replaced files and their containing
directory entries are fsynced before success is reported or journals/latches are cleared.
Defaults are 100 MiB per lineage, 1 GiB globally, and a seven-day orphan TTL. Expired
evidence leaves the live lineage root and becomes collectible. Hash mismatch, missing
content, malformed roots, or cap exhaustion fails closed. Pre-publication filesystem
failures enter the blocked transaction path; only ambiguous publication retains its
recovery journal and latch.

Callers may provide up to 20 `{claim, source, content}` records through
`supplied_evidence`. `claim` must match exactly one registered proposition. These records
are useful for bounded empirical output or inaccessible local artifacts: the server hashes
their exact bytes, but they still pass through the verifier and are never self-authorizing.

## Independence and authorization

`independent_check` is `auto` (default) or `require`. Risk classification is explicit
through `stakes_level = low | high`; when omitted, any nonempty stakes description is
high. Natural-language stakes are never parsed for security-significant words. Auto
requires a distinct-vendor audit for high-stakes external claims, every closure transition
out of a contradicted or disputed state, truth reversal, evidence-dispute resolution, and
blocking-to-advisory changes. `RESOLVE_DISPUTE` names its exact target outcome (`verified`
or `contradicted`) in the audited event. The proposed transition, evidence IDs,
event digest, vendor/model identities, and audit results persist. Missing, duplicate,
mismatched, or tampered provenance leaves the transition pending and the claim blocking
after reload. The exact pending event is rendered to the next verifier for recovery; a
different event cannot erase it.

The second vendor receives the server-owned proposition, current kind/bearing/status,
plan-anchor identity and spans, complete proposed event, and exact named evidence. Truth,
dispute, deferral, and bearing authorizations persist in separate slots, so a later ordinary
truth check cannot erase the mandatory audit that made a claim advisory. Their evidence
dependencies and exact event objects also persist separately while a retained-ID union
drives freshness invalidation.

The persisted authorization-policy tuple includes the independent-check mode, stakes
classification, and policy version. Any change invalidates the zero-research cache. A
stricter policy immediately reblocks an authorization whose persisted provenance is no
longer sufficient; it cannot inherit an earlier weak-policy `NOT-BLOCKED` result.

## Budgets and caching

Hard per-round limits include 50 active claims, 20 evidence requests, two requests per
claim, eight external HTTP attempts (debited before each hop, including failures),
1 MiB per source, 5 MiB aggregate across claim, search, supplied, and structural phases,
4 KiB display passages,
and one correction retry per model register. Evidence is content-addressed and reusable;
repository reuse recomputes every passage/identity field and is bound to exact blob,
snapshot, history-ref, operation, and canonical query-parameter identities. Literal search
charges each inspected blob before reading it. `LIST_TREE` and `HISTORY` stream bounded
Git output, debit it as it is read, and terminate at their record or byte cap instead of
capturing an unbounded result. Every snapshot Git process and pipe read also has a hard
deadline and is killed/reaped on expiry; directly read Git metadata must be small regular
files rather than FIFOs or devices. Network evidence is audit
material and must be refreshed under the configured freshness policy before it can
authorize a later transition.
Any cached record discarded during validation disables the zero-research cache for that
round, even if no claim directly depended on that record. Persisted supersession is also
validated as a bounded graph: the replacement must exist, be confirmed, and already be
verified or safely deferred. Every persisted non-abstention record must retain its rooted
content digest and exact CAS bytes.

## Output

Closure mode preserves the five review sections and appends:

```text
LINEAGE: project-42-plan (rounds recorded: 3)
CLAIM-REGISTER: parsed 2
CLAIMS: verified=1, unverified=1
CLAIM-CLOSURE: BLOCKED — 1 load-bearing claim(s) unresolved
CLASS-REGISTER: NONE
CLASS-CLOSURE: 0 open, 2 closed, 2 unmechanized
CONVERGENCE: BLOCKED — 1 claim(s)
```

If a structural terminal register needs correction, the original five-section critique is
preserved and the corrected register is displayed separately as the register actually
applied.

There is exactly one `CONVERGENCE` line. Both claim and class gates must be clear for
`NOT-BLOCKED`.

## Migration and recovery

This is an intentional behavior and cost change for existing callers that omitted
`class_closure`: default-on plan closure now runs the integrated gate. Callers wanting the
old inexpensive review must explicitly use `class_closure: false` and accept that the
result has no persistent stop condition.

A failed model process or unavailable toolless boundary leaves lineage state byte-for-byte
unchanged and returns a blocked verdict. Nested schema-version-2 claim/evidence records are
fully validated and corrupt lineage state is quarantined before a latch is acquired. Kind,
classification, and status combinations must be transition-reachable, and anchor
relocation treats overlapping occurrences as ambiguous.
Register syntax and semantic transition validation share the same single correction
attempt; a syntactically valid event with an invalid span, evidence binding, role policy,
or state transition is corrected before application. Malformed registers record debt. A
failed snapshot-ref cleanup, ambiguous publication, or
crash retains the journal and exclusive lineage latch for operator repair; it cannot fall
through to a stale writer. A register still malformed after its one correction attempt is
published as durable blocking debt—even over an otherwise clear cache—and only a later
valid replacement register clears it. Never repair state by deleting evidence roots first: preserve
the last valid root until the lineage is repaired or explicitly abandoned.
