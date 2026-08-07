# Plan claim verification

`critique_plan` has two modes:

- closure mode (the default): a blocking research-and-verify preflight followed by
  structural critique, with one combined claim/class `CONVERGENCE` verdict;
- one-shot mode (`class_closure: false`): one ordinary structural review, no research,
  lineage state, terminal registers, or convergence trailer.

paranoia-local requires a POSIX runtime (Linux or macOS; use WSL on Windows) because its
durable lineage and evidence transactions use POSIX advisory locks and directory fsync.

There is no closure-enabled off or shadow setting. `claim_verification` may be omitted or
set to `blocking`; any explicit claim mode with `class_closure: false` is rejected.
Closure mode ignores repository `.paranoia.toml` settings completely. Model, effort,
web policy, stakes, and every other review control come only from explicit call arguments
or trusted process defaults, so repository-controlled text cannot become role instructions.

## What the gate proves

The gate proves a negative about the registered set: no active registered load-bearing
fact is unresolved, contradicted, stale, disputed, malformed, or unchecked, and no
blocking defect class is open. It does not prove that claim extraction was complete,
that a source is true, that semantic entailment is mathematically correct, or that two
models cannot share a misconception. `NOT-BLOCKED` is not an approval.

## Round topology and trust boundary

One closure round performs these stages:

1. Accept at most 1 MiB of exact plan bytes and expose ordered opaque span IDs beside
   bounded display text. Inline schema validation rejects oversized text early; filesystem
   plans must be absolute, no-follow, nonblocking regular files whose identity, size, and
   timestamps remain stable across a bounded read. Unsafe input returns the standard five
   sections and an explicit blocked preflight verdict before any latch or model call.
   Models reference span IDs; the server owns byte offsets and hashes.
2. Snapshot tracked and non-ignored untracked repository bytes by opening exact files with
   no-follow semantics, hashing through `git hash-object --stdin` (never repository
   filters), and inserting explicit object IDs/modes into a private index. Hooks,
   fsmonitor commands, filters, attributes, aliases, and pagers are disabled or bypassed.
   Synthetic commits explicitly disable signing, including repository-configured GPG
   programs.
   Before the first repository-aware Git subprocess, the server reads approved Git-dir
   metadata with bounded no-follow file operations and builds a private Git control
   directory. Git receives only server-owned config, copied HEAD/index/packed-ref/shallow
   metadata, an fd-anchored no-follow copy of loose refs, and the approved object directory.
   Temporary GC pins are published separately through fd-relative, no-follow operations;
   Git never traverses the repository-controlled loose-ref tree. Repository `config`,
   `config.worktree`, `include.path`, and `includeIf` content
   is never part of a repository-aware Git invocation; only repository/object format values
   are extracted from a bounded private copy with `git config --no-includes`.
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
3. A fresh toolless research role registers load-bearing candidates using only a temporary
   ID, enum labels, and server span IDs. `ADD` has no model-authored proposition field. The
   server derives the durable proposition from the exact anchored plan bytes, parses the
   strict JSON immediately into a non-durable draft, and mints durable-style IDs before
   later roles need to refer to them.
4. A fresh plan-only policy role receives escaped plan spans plus only server-formatted
   candidate IDs and anchors. It never receives persisted claim prose, proposed kind
   labels, repository paths/bytes/metadata, external results, or supplied artifacts. It
   derives each proposition from the anchored plan spans, alone may classify genuine plan
   decisions, and may defer a newly confirmed unverified fact when the plan itself supplies
   the complete ordered verification contract. Every deferral follows the same independent
   authorization policy as evidence-role transitions; `independent_check: require` cannot
   publish it without accepted checks from both supported vendors.
5. A toolless evidence-planning role emits bounded structured requests. The server alone
   executes `LIST_TREE`, `READ_BLOB`, `SEARCH_LITERAL`, and configured external search.
   Request parsing rejects non-UTF-8 scalars before execution; repository operands must be
   bounded relative POSIX paths without `..`, while search/ref/query operands have strict
   byte ceilings. These semantic checks remain inside the role's one correction attempt.
   Tree, literal-search, and history results disclose their exact limit and whether the
   requested scope was completely inspected. Literal-search records additionally bind the
   candidate paths and each inspected blob object/range.
6. A toolless verifier sees exact server evidence bound to the exact claim ID that
   requested it; evidence for one claim cannot authorize another. Every model-visible source, path,
   metadata object, and passage is injectively JSON escaped. Each rendered record is one
   explicitly labelled `UNTRUSTED-EVIDENCE-RECORD-JSON` object: IDs and hashes are
   server-generated identity, while repository/caller/network source, metadata, and
   passage values are untrusted data. Repository, remote, and supplied records never share a call across source classes,
   and cannot classify decisions or emit evidence-free deferral/supersession transitions.
7. A fresh toolless structural reviewer sees the plan, repository evidence, external
   metadata, active claims, and existing class procedures. It emits one atomic PLAN and
   CLASS register. Like every other role, it receives plan bytes only inside ordered,
   injectively JSON-escaped `SPAN` data records; raw plan prose is never interpolated as
   peer-level prompt control text. Because it receives repository passages, it may confirm
   only factual kinds; decision classification remains in the clean plan-only role. Its
   `ADD` events likewise contain anchors rather than repository-influenced prose, and any
   persisted legacy claim text is excluded from the later clean-role packet.
8. Python validates role permissions, applies both registers to drafts, roots exact
   evidence bytes, atomically replaces lineage state, and computes one trailer. An
   atomically exclusive per-lineage latch rejects concurrent rounds before either can
   construct a stale draft.

For Claude, toolless means bare settings, an empty allowlist, an explicit deny list, an
empty `--tools` availability set, and strict empty MCP configuration. Before snapshot or
lineage work, a bounded `claude --help` compatibility probe must successfully advertise
every CLI flag used to construct that profile; merely finding an executable on `PATH` is
not sufficient.
For Codex on Linux, the native binary runs inside a `bwrap` mount namespace containing an
empty working directory, auth, TLS/DNS files, and no shell, repository, common Git store,
or sibling worktree. Shell, unified execution, multi-agent, apps, browser/computer, code,
image, goals, and workspace-dependency feature schemas are explicitly disabled under
strict configuration. Native web is forced off for every claim-verification role. If that
boundary cannot be constructed, the round fails closed before snapshot construction or
latch acquisition and the lineage is unchanged. The currently audited Codex CLI versions
for this boundary are exactly `0.144.6` and `0.146.0-alpha.3.1`; `bwrap` is required.
Every role is fresh and nonresumable (Codex also uses `--ephemeral`), so internal session
IDs are suppressed and closure-plan output does not offer the ordinary `rebut` workflow.

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
extractor proposed. The model selects server span IDs, while the server derives the stored
proposition from those exact anchored plan bytes; repository-aware roles cannot author a
free-form claim string for a later clean role. A different role must confirm its kind.
Advisory bearing is reachable
only through the verifier's evidence-bearing `SET_BEARING`; it cannot be set on `ADD`.
Facts block until verified or safely deferred. Decisions become `not-applicable` only
after cross-role kind confirmation and block again if a plan edit or dispute makes them
stale/disputed. Evidence disputes are accepted only for cross-role-confirmed factual
claims. Omission never deletes a claim.

Plan edits relocate a claim only when its exact anchored bytes occur uniquely. Missing or
ambiguous anchors become stale. Deferred claims additionally invalidate when their plan
ordering snapshot changes; pending deferrals are invalidated before replay under the same
full-plan snapshot rule.

## Evidence

Repository records contain the pinned commit, literal path/query or requested byte range,
underlying blob/ref object identity, exact original bytes,
source and passage hashes, byte bounds, and separately decoded display text. Lossy display
text is never evidence identity.

Bounded `LIST_TREE`, `READ_BLOB`, `SEARCH_LITERAL`, and `HISTORY` records state whether the
entire requested source scope is complete. A partial blob range or other truncated result
remains visible to the verifier as context, including the exact candidates and inspected
byte ranges for a literal search, but its evidence ID is ineligible for truth, bearing,
dispute, or deferral authorization. This prevents a bounded prefix, passage, match set,
history, or partial large-blob scan from being treated as proof of absence. The verifier can
request a complete narrower source where the operation supports it or leave the claim
blocking. Validated metadata is rendered in full, never cut at a display-character limit;
its bounded per-kind arrays and the shared rendered-byte debit limit the packet without
hiding `complete`, candidate paths, or inspected ranges.

Persisted records have an exact per-kind metadata schema, including nested collection
types and empirical input hashes. Before cache evaluation, every retained truth, bearing,
dispute, deferral-authorization, or other claim dependency must resolve to one valid record
bound to that exact claim. Missing, malformed, mismatched, or wrong-claim dependencies stale
the claim and leave it blocking.
`stale`, `disputed`, and `malformed` states override any earlier advisory-bearing
authorization; invalidated evidence or plan bytes must be revalidated before the claim
can become nonblocking again.

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
Those placeholders may occur only in the path or query components: the HTTPS scheme,
hostname, port, and fragment must remain fixed under formatting, while credentials remain
forbidden. The query is percent-encoded before substitution and the formatted origin is
checked again before each request.
Top-level and hit objects use exact schemas and reject duplicate or unknown JSON keys.
Formatting, encoding, numeric-conversion, and excessive-nesting errors are normalized to
role-specific blocked failures, never raw exceptions; the same rule applies to every
model register, evidence request, cached record, and persisted manifest. Fetching
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
lineage root manifests are GC roots. Journal, candidate-root, live-root, and quarantine
manifests have distinct exact schemas, bounded no-follow reads, unique bounded digest sets,
and filename-bound run/lineage identities; foreign, duplicate, unknown, oversized, or
symlinked records fail closed before adoption or sweeping. A global file lock serializes reservation, blob
write, exact live-root replacement, and sweep. Replaced files and their containing
directory entries are fsynced before success is reported or journals/latches are cleared.
Defaults are 100 MiB per lineage, 1 GiB globally, and a seven-day orphan TTL. Expired
evidence leaves the live lineage root and becomes collectible. Hash mismatch, missing
content, malformed roots, or cap exhaustion fails closed. Lineage state publication
tracks its phase: temporary-file creation, serialization, and pre-replace fsync failures
enter the recoverable blocked transaction path and release the unambiguous ownership
latch, while entering the atomic replace or any
later root/journal durability step is ambiguous and retains its recovery roots and latch.

Callers may provide up to 20 `{claim, source, content}` records through
`supplied_evidence`. `claim` must match exactly one registered proposition. These records
are useful for bounded empirical output or inaccessible local artifacts: the server hashes
their exact bytes, but they still pass through the verifier and are never self-authorizing.
Caller-supplied passages are isolated in their own untrusted verifier call, never mixed
with repository evidence. In high-stakes mode, a truth transition that relies on supplied
content requires the same distinct-vendor authorization as fetched external evidence.
External and caller-supplied batches may confirm a proposition as factual, but may not
classify it as a decision, defer it, supersede it, or emit any other transition without
naming evidence from that exact isolated batch. Plan decisions remain the responsibility
of the trusted local/structural roles.

## Independence and authorization

`independent_check` is `auto` (default) or `require`. Required policy applies equally to a
clean-role `DEFER`: semantic validation happens first, then the exact deferral event must
receive accepted `codex` and `claude` checks or remain pending and blocking. Risk classification is explicit
through `stakes_level = low | high`; when omitted, any nonempty stakes description is
high. Natural-language stakes are never parsed for security-significant words. Auto
requires a distinct-vendor audit for high-stakes external claims, every closure transition
out of a contradicted or disputed state, truth reversal, evidence-dispute resolution, and
blocking-to-advisory changes. `RESOLVE_DISPUTE` names its exact target outcome (`verified`
or `contradicted`) in the audited event. The proposed transition, evidence IDs,
event digest, vendor/model identities, and audit results persist. Missing, duplicate,
mismatched, or tampered provenance leaves the transition pending and the claim blocking
after reload. The vendor vocabulary is server-owned and fixed to `codex` and `claude`;
unknown or duplicate vendor identities are malformed, and `complete` requires accepted
checks from exactly both supported vendors. The exact pending event is retained for
server-side replay on the next round; a different event cannot erase it. Reload also validates the authorization's exact event
schema, scalar/nested fields, digest, evidence binding, vendor-check inputs, completion
state, and applied outcome against the claim's current truth, bearing, or deferral state.

The second vendor receives the server-owned proposition, current kind/bearing/status,
plan-anchor identity and spans, complete proposed event, and exact named evidence. Truth,
dispute, deferral, and bearing authorizations persist in separate slots, so a later ordinary
truth check cannot erase the mandatory audit that made a claim advisory. Their evidence
dependencies and exact event objects also persist separately while a retained-ID union
drives freshness invalidation.

Semantic validation of an independently audited event happens before its authorization is
looked up or marked pending. Invalid dispute outcomes, deferral anchors, dependent-claim
sets, or ordering snapshots therefore enter the ordinary one-retry correction path and
cannot consume or persist independent-authorization state.

If a required secondary auditor cannot launch, including an OS permission or resource
failure, the validated exact event still persists with incomplete checks as a pending,
blocking transition. At the start of a later round the server replays that stored event
and its exact evidence bindings directly through authorization; no model is asked to
guess or reconstruct hidden event fields. Replay reuses only accepted vendor provenance
whose event digest and evidence tuple are identical; every missing vendor, including the
current primary vendor when necessary, is actually invoked. A pending deferral is bound to
the complete plan snapshot on which its ordinal span IDs were selected. Any plan edit
clears that pending event and marks the claim stale before replay can reinterpret those IDs
against different bytes.

The persisted authorization-policy tuple includes the independent-check mode, stakes
classification, and policy version. Any change invalidates the zero-research cache. A
stricter policy immediately reblocks an authorization whose persisted provenance is no
longer sufficient; it cannot inherit an earlier weak-policy `NOT-BLOCKED` result.

Every persisted plan lineage uses one exact schema-version 2 outer envelope. Existing plan
state must contain both `schema_version: 2` and the complete `claim_state` object; missing,
unknown, downgraded, or wrong-typed envelope fields quarantine the lineage rather than
defaulting to an empty claim register. The `None` claim-state default exists only for a new
lineage that has no state file yet. The surrounding class records, matches, exemptions,
debt (exactly a positive round and nonempty reason), severities, statuses, mechanisms, and
supersession graph are likewise type-, shape-, cardinality-, and reachability-checked before
use; duplicate identities or invented clear states quarantine the file. Evidence
invalidation skips terminal superseded claims, so expiry cannot resurrect an inert
predecessor or create a state the loader rejects. A replacement may later become stale,
disputed, or otherwise blocking without invalidating the terminal predecessor; the active
replacement alone governs closure. If invalidation removes evidence named by a pending
transition, that now-unexecutable transition is cleared alongside its evidence and a fresh
verifier may propose a new event bound to refreshed IDs.

## Budgets and caching

Hard per-round limits include 50 active claims, 20 evidence requests, two requests per
claim, eight external HTTP attempts (debited before each hop, including failures),
1 MiB for the plan, 1 MiB per source, 5 MiB aggregate across claim, search, supplied,
and structural phases,
4 KiB display passages,
and one correction retry per model register. Evidence is content-addressed and reusable;
the same budget begins before cache validation: retained CAS bytes are reserved before
bounded no-follow reads, repository/history/adapter revalidation is charged as attempted,
and evidence records are charged again when rendered into verifier or auditor prompts.
Serialized bounded tree listings are likewise charged before their first evidence-planner
or structural-planner call, in addition to the raw Git bytes charged during enumeration.
Ignored-untracked and unsupported-nonregular path disclosures are completeness-marked and
charged before the research call, and charged again if a correction resends them.
If a register needs correction, the exact evidence portion resent in the correction prompt
is debited a second time before the retry call; insufficient remaining budget blocks
without transmitting it.

Repository reuse recomputes every passage/identity field and is bound to exact blob,
snapshot, history-ref, operation, canonical query-parameter identities, completeness, and
recorded search scope. Literal search charges each inspected blob before reading it and
records its object ID, byte range, whole size, and range completeness. `LIST_TREE` and
`HISTORY` read one bounded look-ahead record to distinguish complete results from truncation,
debit Git output as it is read, and terminate at their record or byte cap instead of
capturing an unbounded result. Each read is also sized to the shared budget remaining, so
attempted pipe I/O cannot cross the aggregate cap before accounting rejects it.
Snapshot-discovery enumerations are likewise streamed before decoding or retention, with
a 100,000-path/32-MiB cap and a separate 4,096-total-ref discovery cap before the smaller
pinned-history limit is applied. Directory scans count entries while iterating instead of
materializing an attacker-sized directory first. Every snapshot Git process and pipe read
also has a hard deadline; a shared termination path kills and reaps the child under a
second bounded deadline and translates wait failures into recoverable snapshot errors.
Loose refs are copied through fd-anchored, no-follow traversal under explicit entry, depth,
per-file, and aggregate-byte caps. Temporary pin creation, verification, and deletion use
the same fd-relative boundary and reject every symlinked ancestor or ref file. Directly
read Git metadata must be small regular
files opened with no-follow and nonblocking flags, then checked again by file identity and
size before a bounded read; FIFOs, devices, symlinks, and replacement races are rejected.
Within `.git/objects`, symlink rejection follows only exact Git-resolvable loose-object,
pack/multi-pack-index, alternates, and commit-graph names; inert nested names even beneath
`pack` or `info` do not invalidate a snapshot.
Network evidence is audit
material and must be refreshed under the configured freshness policy before it can
authorize a later transition.
Any cached record discarded during validation disables the zero-research cache for that
round, even if no claim directly depended on that record. Persisted supersession is also
validated as a bounded graph: the replacement must exist, be confirmed, and already be
verified or safely deferred. The loader requires the target to be a confirmed fact and
accepts only the original clear states or factual post-clear invalidation states. Thus a
not-applicable decision cannot invent a clear source, while later evidence loss may stale
the factual replacement without resurrecting the terminally superseded source. Every
persisted non-abstention record must retain its rooted
content digest and exact CAS bytes.

## Output

Closure mode preserves the five review sections and appends:

```text
LINEAGE: project-42-plan (rounds recorded: 3)
CLAIM-REGISTER: parsed 2
CLAIMS: verified=1, unverified=1
CLAIM-CLOSURE: BLOCKED — 1 load-bearing claim(s) unresolved
CLAIM-DATA-JSON={"claim":"Exact anchored plan text","claim_id":"0123456789","status":"unverified"}
CLASS-REGISTER: NONE
CLASS-CLOSURE: 0 open, 2 closed, 2 unmechanized
CONVERGENCE: BLOCKED — 1 claim(s)
```

If a structural terminal register needs correction, the original five-section critique is
preserved and the corrected register is displayed separately as the register actually
applied.

Every server-rendered claim, class, warning, and debt value is an injectively escaped,
one-line `*-DATA-JSON` record. There is exactly one `CONVERGENCE` line. Both claim and class gates must be clear for
`NOT-BLOCKED`. Preflight failures such as latch contention and quarantined state return a
synthetic review with the same five ordered, nonempty sections before the blocked trailer.
Structural prose containing a model-authored line beginning `CONVERGENCE:` is rejected and
must be corrected; any reserved verdict-looking line in a generated failure body is framed
as `UNTRUSTED-REVIEW-LINE-JSON`. The completed response asserts that only the
server-computed trailer line remains.

## Migration and recovery

This is an intentional behavior and cost change for existing callers that omitted
`class_closure`: default-on plan closure now runs the integrated gate. Callers wanting the
old inexpensive review must explicitly use `class_closure: false` and accept that the
result has no persistent stop condition.

A failed model process or unavailable toolless boundary leaves lineage state byte-for-byte
unchanged and returns a blocked verdict. Nested schema-version-2 claim/evidence records are
fully validated and corrupt lineage state is quarantined before a latch is acquired. A
quarantine uses an atomic rename followed by a parent-directory fsync. Rename or fsync
failure is reported as a quarantine failure and never as a successful move; the operator
is not told that malformed live state was safely isolated when durability is ambiguous. A
present claim-state object must contain the exact complete serialized field set—missing
fields never default to an empty claim collection. Kind,
classification, and status combinations must be transition-reachable, and anchor
relocation treats overlapping occurrences as ambiguous.

Register syntax and semantic transition validation share the same single correction
attempt; a syntactically valid event with an invalid span, evidence binding, role policy,
state transition, request path/query operand, or non-UTF-8 surrogate-bearing scalar is
corrected before application.
Malformed registers record debt. A
failed snapshot-ref cleanup, ambiguous publication, or
crash retains the journal and exclusive lineage latch for operator repair; it cannot fall
through to a stale writer. Latch release first renames the owner marker to a `releasing`
recovery marker and fsyncs that transition. If unlink durability fails, the live marker is
recreated and the current response is changed to blocked, so a later round cannot silently
inherit an undurable clear. A register still malformed after its one correction attempt is
published as durable blocking debt—even over an otherwise clear cache—and only a later
valid replacement register clears it. Never repair state by deleting evidence roots first: preserve
the last valid root until the lineage is repaired or explicitly abandoned.

Every exception while verifying or deleting temporary snapshot refs—including ownership,
decoding, boundary, and filesystem failures—is normalized as
ambiguous cleanup, so the journal and latch remain available for operator recovery.
Publication takes rollback ownership immediately after the exclusive ref-file create; any
later write, file fsync, close, or parent fsync failure removes only that exact fd-anchored
inode. If its identity or rollback durability cannot be established, cleanup is ambiguous
and the pre-published journal/latch are retained.
