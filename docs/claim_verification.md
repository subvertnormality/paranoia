# Plan claim verification

Plan claim verification is an optional research-and-verify phase for `critique_plan`.
It answers a narrower question than structural review: are the registered load-bearing
premises verified, contradicted, safely deferred, or explicitly unresolved?

## Rollout modes

`claim_verification` has three modes:

| Mode | Effect |
|---|---|
| `off` | Opt out and preserve ordinary class-closure plan review; do not run or persist claim research |
| `diagnostic` | Default. Run and persist claim research, display claim closure, but let only class closure govern `CONVERGENCE` |
| `blocking` | Combine unresolved claims, claim debt, class debt, and blocking classes into `CONVERGENCE` |

Diagnostic mode ignores unresolved claim findings for convergence; it never ignores an
operationally incomplete round. Model-role failure, register debt, state failure, or an
abandoned structural/class transaction blocks in every enabled mode.

`diagnostic` is the required rollout stage. Promote a workflow to `blocking` only after its
operators have measured latency, false-block rate, extraction quality, state growth, and
recovery behavior on representative plans. `class_closure: false` remains the stateless
one-shot review and accepts only `claim_verification: off`.

## Stakes and trust model

The initial implementation is a single-user local MCP tool:

- the operator, OS, filesystem implementation, and other local processes are trusted;
- plan bytes, repository content, Git configuration, supplied artifacts, persisted records,
  and fetched pages are untrusted data;
- no hostile local process is assumed to rename or replace repository path components while
  a round is running;
- ordinary edits may occur and must cause an explicit unavailable/stale result rather than a
  false clear;
- repository configuration must not select hooks, filters, signing programs, lazy fetches,
  alternate object databases, or inherited Git behavior used by evidence collection;
- model-visible untrusted values remain escaped data and cannot become role instructions;
- false `NOT-BLOCKED`, cross-claim evidence reuse, stale evidence reuse, and silent durable
  state loss are in scope;
- defending against a compromised OS, a hostile process with concurrent filesystem write
  access, or deliberate mutation of server-owned state by another local principal is out of
  scope for this rollout.

“Malicious repository” in this document means malicious static bytes and configuration. It
does not mean an active process racing `open(2)`. Expanding that threat model requires a new
architecture decision and performance budget; it is not an incremental hardening task.

## What the gate proves

For the registered claim set, claim closure proves that no active load-bearing claim is
unchecked, unverified, contradicted, disputed, malformed, stale, or missing a required
authorization. It also verifies that every evidence dependency still resolves to a valid
record bound to that claim.

It does not prove that extraction found every premise, that a primary source is truthful,
that semantic entailment is mathematically certain, or that two models cannot share a
mistake. `NOT-BLOCKED` is a gate result, not approval of the plan.

## Round topology

A diagnostic or blocking round performs these stages:

1. Read at most 1 MiB of exact UTF-8 plan bytes and divide them into server-owned span IDs.
2. Build an ephemeral dirty-tree repository snapshot without running repository filters,
   hooks, signing commands, lazy fetches, or inherited Git configuration.
3. Ask a fresh plan-only extractor to register candidate load-bearing claims by span anchor.
4. Ask a separate clean policy role to confirm fact/decision classification and any complete
   plan-authored deferral contract.
5. Ask a toolless evidence planner for bounded repository, empirical, external, or supplied
   records. The server executes those requests.
6. Ask source-isolated verifier roles what each complete evidence record establishes.
7. Run a separate structural reviewer using the plan and bounded evidence context.
8. Validate both registers, atomically persist the lineage/evidence roots, and compute the
   claim and class trailers in Python.

The extractor cannot clear its own claim. Omission in a later round never deletes a durable
claim. Research output never edits the plan.

## Fast repository snapshot

`plan_snapshot.py` uses a server-owned temporary Git directory, index, and object directory.
It copies only bounded ref metadata, points Git at the native object directory through an
explicit server-selected alternate, and writes dirty/untracked blob objects into the
temporary object directory. One batched index update and `write-tree` create the exact
dirty-tree snapshot commit.

This avoids copying the repository's complete object database and avoids one Git process per
worktree file. The native repository is not given temporary refs and its index is not
modified. The temporary directory keeps the synthetic objects alive for the round.

The snapshot boundary retains these protections:

- inherited `GIT_*` settings are removed;
- hooks, fsmonitor, signing, replacement objects, grafts, lazy fetches, and filters are not
  used by snapshot construction;
- repository config includes and `config.worktree` are not loaded into evidence commands;
- native `objects/info/alternates` is rejected rather than followed;
- path, record, per-file, total snapshot, output, and subprocess-time limits are enforced;
- dirty regular files are read with pre/open/post identity checks, and bounded repository-wide
  pre/post manifests compare candidate paths, index entries, special paths, file identities,
  HEAD, and the bounded ref map, so ordinary edits or ref maintenance spanning construction
  fail explicitly;
- ignored files and unsupported nonregular paths are disclosed but are not evidence blobs;
  their presence makes a containing list/search scope incomplete and unable to prove absence;
- history refs are copied into the private control directory at snapshot creation, so later
  ref movement does not change their identity.

The snapshot does not defend against an active process replacing the repository root,
ancestors, native object files, or temporary directory while the round runs. If ordinary
maintenance removes a captured native object, the later evidence operation fails explicitly.

## Claim state

Claims persist in schema version 2 of the plan lineage envelope. The main fields are:

- kind: `fact | decision`;
- assertion mode: `asserted | assumption | estimate`;
- kind classification: `proposed | confirmed`;
- bearing: `blocking | advisory`;
- status: `unchecked | unverified | verified | contradicted | disputed | deferred | stale |
  malformed | not-applicable | superseded`.

New claims begin proposed, blocking, and unchecked. A separate role must confirm kind.
Facts remain blocking until verified, safely deferred, or independently authorized as
advisory. Decisions become nonblocking only as confirmed `not-applicable` decisions.

Truth, bearing, dispute, and deferral authorizations occupy separate slots. Tightening the
current authorization policy reblocks an applied transition until its required checks
complete. An advisory bearing never bypasses pending or invalid truth authorization.

Plan edits relocate claims only when their exact anchored bytes still occur uniquely.
Otherwise they become stale. A clean plan-only role may supersede a stale claim with a
replacement anchored in the current plan. Persisted active replacement edges are accepted
only from a stale source to an existing confirmed non-clear target; a clear target must
already have completed the source transition to `superseded`.

## Evidence and accuracy

Every evidence record has a server-generated ID, exact full-content hash, claim binding,
source kind, source identity, bounded passage, exact passage offsets, and completeness
metadata. Evidence for one claim cannot authorize another. For a large external or supplied
source, the server deterministically selects a claim/query-relevant window while retaining
the complete source in the content-addressed journal. If that initial window is insufficient,
a later round can issue `SELECT_PASSAGE` for any explicit at-most-4-KiB byte range of the
already rooted source; the server enforces the claim binding and aligns UTF-8 boundaries.
Refinable records are surfaced fairly—one least-refined source per least-refined blocking
claim—so bounded prompt limits rotate rather than permanently hiding later claims or sources.

A visible bounded passage may authorize only a proposition directly entailed by those
bytes. It cannot prove absence, exhaustive coverage, or an unshown source-wide property.
Incomplete tree, history, and search scopes are context-only; an exact blob range may support
a directly visible fact. Non-UTF-8 passages that require lossy display are also context-only.
A citation is metadata, not proof.

Repository cache validity depends on the snapshot commit and every recorded object/path
identity. Empirical cache validity additionally depends on the fixed adapter, runtime, and
input hashes. External evidence carries retrieval and freshness metadata. Semantic source
changes invalidate the record and stale the claim; an operational read failure blocks the
round without pretending that the source changed.

The initial empirical adapter is `PYTHON_COMPILE`: a bounded compile-only check over pinned
Python blobs. It is optional and is requested only for claims specifically about Python
source. All snapshot, tree, blob, literal-search, history, supplied-evidence, external-source,
claim-state, and convergence behavior is language-, framework-, and project-domain-neutral.
Models cannot submit arbitrary shell commands. Projects using other languages still receive
the complete generic verification flow; they simply have no language-specific empirical
adapter until one is deliberately added.

## External and supplied evidence

External discovery is optional and uses the trusted process-level
`PARANOIA_SEARCH_ENDPOINT`. The endpoint must be HTTPS and return the documented bounded
JSON search shape. Redirects, DNS results, connected peers, response media, compressed and
decompressed bytes, and a shared total deadline are validated by server code.

Search rank is not source authority. Callers provide trusted `external_source_policy` rules
with an exact lowercase host, URL path prefix, and `primary`, `authoritative`, `secondary`,
or `ugc`
classification. The longest exact-host/path match governs; subdomains do not inherit a rule.
Authority rules apply only to HTTPS's default origin (effective port 443). Path prefixes
match complete path segments; alternate ports and ambiguous percent-encoded, backslash, or
dot-segment paths remain unclassified. Unmatched pages remain `unclassified-external`. Only primary and authoritative records may
authorize an external truth or bearing transition. Secondary and unclassified records may
guide structural critique but cannot clear a load-bearing claim. The verifier still judges
whether an eligible passage actually entails the proposition; server classification does
not make irrelevant official material evidence.

Known user-generated-content hosts—including Reddit, Stack Overflow/Stack Exchange, Hacker
News, Quora, and common social/publishing platforms—are forced to `ugc`; a caller rule cannot
promote them to primary or authoritative. UGC can expose leads, conflicts, or user-experience
reports, but cannot authorize general API, standard, regulatory, historical, or product facts.
Cached external URLs are reclassified against the current caller policy on every round; a
removed or downgraded rule invalidates the record and stales every dependent active claim.

Remote content and caller-supplied artifacts are untrusted data. They receive isolated
verifier calls and cannot classify plan decisions, author evidence-free deferrals, or waive
claims. Unavailable sources produce an abstention and leave a load-bearing claim unresolved.

## Independent authorization

`independent_check` is `auto` or `require`. Required authorization uses the fixed vendor
identities `codex` and `claude`. `auto` applies it to higher-risk transitions including
external high-stakes evidence, contradiction reversal, dispute resolution, and a change
from blocking to advisory.

The exact event, evidence IDs, claim state, vendor/model identities, and checks persist.
Unavailable checks remain pending and are replayed from the stored event in a later round.
Duplicate evidence IDs, unknown vendors, mismatched event digests, or incomplete provenance
cannot clear a claim.

## Persistence and recovery

Exact evidence bytes live in the content-addressed evidence store beneath
`$PARANOIA_STATE_ROOT/evidence/`. Lineage publication and evidence roots use atomic replace,
advisory locking, and explicit recovery journals. Malformed persisted structures are
quarantined or reported as blocked; they are never defaulted to empty state.

Operational failures before an unambiguous publication boundary release the lineage latch.
Ambiguous failures at or after publication retain recovery state for the next operator or
round. The ephemeral repository snapshot itself owns no native refs, so snapshot cleanup is
limited to removing its temporary directory.

## Limits and performance

Important bounds include:

- plan: 1 MiB;
- paths: 100,000;
- path enumeration: 32 MiB;
- individual dirty file: 32 MiB;
- dirty-tree content retained for a snapshot: 256 MiB;
- evidence records and requests: bounded per operation and by one shared round budget;
- external work: bounded requests, redirects, compressed/decompressed bytes, and total time;
- persisted evidence: 100 MiB per lineage and 1 GiB globally by default.

Snapshot latency is measured separately from model latency. On the development repository,
the refactored snapshot dropped from roughly 17.2 seconds to roughly 0.23 seconds. This is a
local benchmark, not a universal guarantee; representative diagnostic rollout data governs
promotion.

## Promotion and rollback criteria

Promote `diagnostic` to `blocking` for a workflow only when:

- representative plans show useful claim extraction with an acceptable false-block rate;
- snapshot and non-model overhead meet the workflow's latency budget;
- cached rounds avoid unnecessary research calls;
- malformed, stale, interrupted, and unavailable cases recover without manual state edits;
- operators understand that the gate covers only registered claims.

Remain diagnostic or roll back to `off` when latency, model calls, false blocking, state
growth, or operational recovery outweigh the additional premise assurance. Rollback does
not delete lineage evidence; it only stops the claim gate from running or governing future
verdicts.
