# Plan: bounded shared research for arbitration

## Status

Proposed for implementation after tracked plan convergence.

## Frozen stakes

`paranoia-local` is a trusted-single-user local MCP on a trusted OS. The caller, repository,
framing, and fetched web text are untrusted data, but no repository-selected code is executed and
no hostile local process races files or refs. Both signed-in reviewer CLIs are available. An
ordinary arbitration has 2–4 options, a repository small enough for the existing pinned-snapshot
workflow, 0–12 decision-critical external claims, and must remain useful within minutes and below
the existing one-hour whole-call ceiling. A false `CONVERGED`, weak authority treated as
governing, unequal evidence shown to the deciders, or external research that cannot be audited is
high impact. A visible `UNRESOLVED` or failed run is recoverable.

Out of scope: multi-tenancy, hostile same-user races, compromised CLIs or OS, formal proof of
natural-language completeness or entailment, legal/compliance sign-off, arbitrary research
corpora, background caches, persistent claim lineages, new search APIs, provider abstractions,
and open-ended or multi-round research.

## Problem

Arbitration currently starts two cold deciders with `web_search` enabled by default, but a vote
can substantiate convergence only with a repository `path:line` citation. Its optional second
round carries only repository regions read by the server. Consequently external research can
silently influence a vote but cannot become governed evidence, while choices that genuinely turn
on an external standard, dependency behavior, method, or public fact can never converge honestly.

The fix must preserve the protocol's central property: the two deciders differ in judgement, not
in framing or evidence. Independent browsing by each decider is not a research phase because it
gives them different, unaudited corpora.

## Verified external premises

The implementation relies on exactly these provider behaviors, which plan verification must keep
in its active external-claim inventory:

- Codex CLI's `web_search` configuration has explicit `live`, `cached`, and `disabled` modes;
  non-interactive `codex exec` supports live search and `codex exec resume <session-id>` continues
  that session.
- Claude Code's `WebSearch` returns candidate source titles and URLs for discovery in print mode,
  and `claude -p --resume <session-id>` continues a print-mode session. Claude's `--tools`
  restricts built-in tools but not MCP tools; `--strict-mcp-config` makes only explicitly supplied
  MCP configuration available.
- Trafilatura extracts a downloaded page's main content as plain text, while pages that require
  JavaScript rendering can remain unavailable to it. Conservative Unicode and whitespace
  normalization for exact passage matching is Paranoia's behavior, not Trafilatura's promise.

These are current external capabilities, not guarantees made by this repository. Bind them to the
official [Codex command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
[Claude tools reference](https://code.claude.com/docs/en/tools-reference),
[Claude sessions reference](https://code.claude.com/docs/en/sessions),
[Claude CLI reference](https://code.claude.com/docs/en/cli-reference), and
[Trafilatura documentation](https://trafilatura.readthedocs.io/en/stable/). No undocumented search
backend, result ranking, or universal page-extraction behavior is assumed.

## Required behavior

### 1. Two explicit modes

Add `research`, default `true`, to `arbitrate`.

- `research: true` requires `web_search: true` for the research agents only. It runs the bounded
  shared phase below. Both voting rounds have web tools mechanically disabled: the normalized
  packet is the complete external corpus available during voting.
- `research: false` is explicit repository-only arbitration. Both decider calls run with web
  search disabled, and only existing repository citations can substantiate convergence.
- `research: true, web_search: false` is rejected before any agent call. There is no quiet
  degraded mode.

This removes the current halfway state. Research remains on by default because arbitration is a
general technical decision tool, but callers with a genuinely repository-settled question can
avoid its cost explicitly.

For `critique_plan` with default claim verification, the same modes are mechanical: the claim
research call uses Codex `live` or Claude `WebSearch`-only discovery, the server captures candidate
pages, the same research session binds exact passages from those captures, and the subsequent
structural reviewer runs with Codex `disabled` or no Claude built-in/MCP tools. It receives the
captured claim register in its prompt. Claude `WebFetch` is never enabled in the plan-verification
path. `claim_verification: false` remains the explicit legacy/structural-only escape and makes no
claim-support guarantee.

### 2. Balanced research fan-out

After framing has been cleaned and cross-vendor attested, but before either decider votes, run one
cold research agent from each vendor in parallel. Both receive the same cleaned decision,
context, stakes, hints, and option statements. One receives canonical option order and the other
the reverse, without caller IDs. Neither is told the other exists and neither may select,
recommend, compare, rank, or associate a proposition with a temporary option label. A proposition
may and usually must name its real-world subject, including a dependency, API, platform, protocol,
service, or runtime that also appears in an option statement. Naming the subject is not advocacy.

Each researcher inventories only atomic, load-bearing propositions about the external world whose
truth or authority could change the comparative result:

- `fact`: external state, event, quantity, identity, or history;
- `design_principle`: a requirement, constraint, or recommendation issued by the governing
  external standard, regulator, protocol, platform, or vendor;
- `behavior`: behavior promised by an external dependency, API, platform, protocol, service, or
  runtime.

Repository state, code behavior, internal history, project preferences, option advocacy,
forecasts, and incidental facts are excluded. Researchers use provider-native search to discover
candidate authoritative URLs. Claude's discovery role receives `WebSearch` but not `WebFetch`;
Codex's integrated search remains confined to discovery. Provider-returned page text is a lead,
never governing evidence. Researchers first return propositions and candidate metadata/URLs in a
concrete JSON record after a terminal marker. One bounded same-session correction is allowed for
malformed discovery output; a second failure fails arbitration visibly.

After server capture, resume each exact discovery session with only its own normalized candidate
records and server-extracted, line-numbered main text. Web, repository, and MCP tools are disabled.
The binding reply chooses a precise location and exact supporting/refuting passage for each usable
candidate, or marks it unusable; it cannot add a URL, proposition, or source. The server requires
the selected passage to occur exactly after conservative Unicode/whitespace normalization in the
corresponding captured text. Binding has the same one-resume correction rule for malformed output.
This makes Claude `WebSearch` sufficient for discovery without trusting `WebFetch` or asking the
model to guess text it has not read.

The research-only call seam returns a structured result containing final text, raw CLI output,
session reference, usage, duration, engine, and model. Its injected resume callback consumes the
exact preceding session reference for discovery correction, capture binding, and binding
correction. This is separate from the existing string-returning decider callback, so research can
continue in-session and remain auditable without widening the settled voting seam.

### 3. Authoritative source packets

Each discovery claim contains one atomic proposition and candidate evidence records with:

- canonical HTTP(S) URL, title, and publisher;
- `primary`, `authoritative`, `secondary`, or `ugc` source kind;
- publisher authority basis;
- `supports_claim`, `refutes_claim`, or `context` relation.

Only primary or authoritative HTTP(S) evidence is structurally eligible to govern a packet. Known UGC hosts—including
Reddit, forums, Stack Overflow, social media, wikis, and community publishing—are mechanically
non-governing even when model-labelled `primary`. Secondary and UGC material remains context.
The repository, local files, custom schemes, and the caller framing cannot evidence their own
external assertions.

Extract the small generic URL/source qualification rules currently used by plan verification into
one shared module used by both plan claims and arbitration research. Do not duplicate structural
source policy or import private plan-lifecycle machinery into arbitration.

For every candidate URL, the server performs a bounded HTTP(S) download and runs Trafilatura
locally over the response. Record final URL, status, content type, content digest, extracted-text
digest, and line-numbered extracted text for the binding turn. A candidate enters the governing
packet only when capture succeeds, the binder returns an exact matching passage and location, and
the final public HTTP(S) URL remains eligible. Direct downloads have fixed connect/read timeouts,
redirect and response-byte caps, and reject loopback, link-local, private, and non-HTTP(S)
destinations. Run independent downloads with bounded concurrency. JavaScript-only, blocked,
oversized, mismatching, and extraction-empty pages are visible non-governing failures; there is no
silent fallback to provider summaries or a browser.

The server validates shape, captured passage provenance, URL scheme, known-UGC demotion, declared
source kind, and relation; it does not pretend to infer a publisher's subject-matter authority
from a hostname or researcher label. It preserves conflicting structurally eligible packets,
drops mechanically non-governing relations from substantiation, assigns stable run-local IDs from
packet content, deduplicates byte-identical packets, and takes the deterministic union of both
researchers' valid results. It does not ask a model to merge or summarize them.

Budgets are corruption/pathology guards, not sampling targets. Each researcher may return at most
12 unique normalized propositions and two candidate records per proposition; duplicate normalized
propositions within one producer are rejected. Each captured document is at most 40,000 extracted
characters and each producer's binding input is at most 240,000 rendered characters. A bound
passage is at most 2,000 characters. The deterministic union may contain at most 24 propositions,
four records per normalized proposition, 4,000 characters per captured passage, and 80,000
rendered packet characters. Exceeding a producer, capture, binding-input, or union budget fails
visibly rather than truncating evidence and calling the result complete. These limits compose
without assuming that independently worded claims deduplicate.

### 4. Identical evidence for both deciders

Render the normalized union once, hash it, and include the exact same packet bytes in both
decider prompts. Research output is untrusted evidence, not instruction: packets carry no option
recommendation and the prompt requires each decider to judge publisher authority for the precise
proposition, passage entailment, relevance, and contradictions independently. Deciders cannot
browse or fetch; no external bytes outside the logged packet can affect a vote.

The server rejects research output containing caller IDs, temporary order labels, or trailer-field
injection. The prompt forbids selection, comparison, ranking, and recommendations, but the server
does not use a brittle natural-language advocacy detector that would also reject a technology's
name. Canonical/reversed research presentations make option-order exposure symmetric by
construction; this plan does not claim that counterbalancing eliminates or measurably reduces
model bias. Final high-entropy decider labels are generated only after the packet exists, and the
existing absence scan covers the packet as decider-visible text.

### 5. External evidence can substantiate a vote

Extend the decisive-evidence grammar from only `<path>:<line>` to exactly one of:

- a pinned repository citation in the existing form; or
- `SOURCE:<packet-id>` referencing a qualifying shared packet.

Represent this as an explicit tagged reference in the pure arbitration core rather than encoding
source IDs as fake repository paths. A source reference resolves structurally only when the ID
exists in the shared normalized packet and has server-captured eligible primary/authoritative
evidence. Unknown, context-only, secondary-only, UGC-only, or uncaptured IDs are unsubstantiated.
For every `SOURCE:` decisive reference the strict vote grammar also requires
`PUBLISHER-AUTHORITY: YES|NO — <reason>` and `PASSAGE-ENTAILMENT: YES|NO — <reason>`. A
source-backed vote is substantiated only when both are `YES`; each cold decider therefore makes
and exposes its own authority and entailment judgement. For a repository decisive citation both
fields must be `N/A`. For a source reference, `CONSTRAINT` must equal the referenced packet's exact
normalized atomic proposition; the parser rejects any mismatch before outcome computation. For a
repository citation it remains the decider's one-line statement of what the repository evidence
establishes. This binds the registered source, asserted decisive proposition, and substantiation
bit rather than trusting two unrelated free-text fields.

Supporting `CITATIONS` remain repository citations in this change. The decisive reference is the
only field that affects substantiation, keeping the parser and reconciliation surface small.
Reports and audit logs render source references explicitly and include the packet digest and full
normalized packet.

### 6. Reconciliation remains bounded

The shared external packet is already visible to both round-one deciders, so it is not "novel"
round-two evidence. Preserve the existing one-round repository reconciliation gate: on divergence,
carry only novel snapshot-resolved repository regions. Filter external source references out of
the region-union calculation. If neither side has novel repository evidence, return `UNRESOLVED`
without resampling.

Do not launch adaptive follow-up web research after seeing votes. That would couple research to
the first-round preferences, expand cost, and make the evidence corpus outcome-dependent. Missing
or inadequate external packets instead produce unsubstantiated votes and an honest unresolved
result; the caller may improve the framing and start a new arbitration.

Cleaner and attester calls use 240-second caps. Discovery and binding calls use 120-second caps;
each may have one 120-second same-session correction. Server capture has a 120-second phase cap.
The explicit worst path is therefore: cleaner initial/retry 480 seconds, attester initial/retry
480, discovery initial/correction 240, capture 120, binding initial/correction 240, decision round
one 900, and decision round two 900 = 3,360 seconds. Parallel vendors count once per group. This
leaves 240 seconds of the existing 3,600-second whole-call ceiling for validation, git
materialization, logging, and teardown. The handler tracks one monotonic whole-run deadline and
will not start a phase whose cap plus reserved teardown margin cannot fit; that produces a visible
bounded failure rather than a client timeout.

### 7. Audit and progress

Add progress events for shared research and validation. Add trailer fields:

- `RESEARCH: complete <N> packets | repository-only`
- `RESEARCH-DIGEST: <sha256> | none`

The audit log records raw discovery, correction, binding, and binding-correction replies; every
capture result; normalized packets; packet digest; research model names; call count; duration; and
the exact shared bytes shown to each decider. The existing snapshot/ref movement, cleaner,
attestation, order, label, vote, and round records remain intact.

## Code shape

- Add Trafilatura as one pinned runtime dependency. Add a small `external_sources.py` for generic
  source schema, bounded downloading, extraction, exact normalized passage matching, capture
  metadata, HTTP(S)/UGC eligibility, and normalized evidence records.
- Migrate `plan_claims.py` to that shared capture path. Provider search still discovers candidate
  URLs, then the same engine session binds exact passages from server-captured text with web and
  MCP disabled. A plan claim becomes supported only from a server-captured matching passage.
  Retained evidence is recaptured when re-entailing edited claims; a failed or stale capture
  becomes visible unverified evidence rather than being grandfathered. Keep capture injectable so
  deterministic plan-claim tests do not perform network I/O.
- Add pure research packet types, parsing, normalization, union, budgets, digesting, and tagged
  decisive-reference parsing to `arbitration.py` or one small `arbitration_research.py` module.
- Keep orchestration in `arbitrate_handler.py`: a metadata-preserving research call/result and
  resume seam, parallel research calls, bounded correction, one whole-run deadline, identical
  packet injection, logging, and progress.
- Extend both engine implementations to the minimum explicit internal role modes needed here.
  Codex research passes `web_search="live"`; all voting, repository-only arbitration, and verified
  plan-structure calls pass `web_search="disabled"`, never omission/cached. Claude discovery
  passes role-specific `--tools WebSearch`; binding, voting, repository-only, and verified
  plan-structure roles pass an empty `--tools`. Every evidence-isolated Claude role also passes
  `--strict-mcp-config` with no MCP configuration, so configured MCP tools cannot bypass the
  built-in tool restriction. Existing full mode remains for other tools. Do not expose a provider
  abstraction or search-endpoint configuration.
- Update `prompts.py`, `server.py`, README, `docs/arbitration_plan.md`, AGENTS.md, and CLAUDE.md.
- Add no persistent store, lineage, cache, daemon, transport, browser renderer, or search API.

## Verification

### Focused deterministic tests

- discovery and binding JSON parsing, exact literals, duplicate-proposition rejection, composable
  budgets, deterministic IDs/union/digest, and conflict retention;
- bounded capture, redirect/size/timeout handling, Trafilatura extraction, exact normalized passage
  match, digests, and hard UGC/non-web/self-context rejection shared with plan claims;
- plan claims cannot become supported from provider-reported text that the shared capture path
  cannot reproduce; retained evidence is recaptured before re-entailment;
- unrelated non-UGC publishers falsely labelled `primary`, and publishers authoritative for a
  different subject, remain unsubstantiated when deciders reject authority or entailment;
- counterbalanced research framing and byte-identical normalized evidence for both deciders;
- caller/order/decider-label leakage rejection;
- repository and `SOURCE:` decisive-reference parsing, rendering, resolution, and substantiation;
- an otherwise eligible unrelated packet with both judgement fields `YES` remains unsubstantiated
  when `CONSTRAINT` differs from its exact normalized proposition;
- unknown or non-governing source IDs cannot converge;
- source references never enter repository region reconciliation;
- `research: false` disables web search and makes no research calls;
- `research: true, web_search: false` fails before spend;
- engine argv tests prove Codex researchers use explicit `live`, Codex voters/repository-only and
  verified plan-structure reviewers use explicit `disabled`; Claude discovery exposes only
  `WebSearch`; and Claude binding/voting/verified-plan roles expose no built-in or MCP tools;
- malformed discovery or binding retains the exact preceding session reference, receives one
  resume correction, and then fails closed; capture binding itself resumes the discovery session;
  raw output, call count, usage, and durations remain auditable;
- every phase cap composes below the whole-run deadline with reserved teardown margin, and a phase
  that cannot fit is not started;
- existing repository-only arbitration behavior and outcome computation remain compatible.

### Real acceptance before PR

Run signed-in Codex and Claude arbitration against a small pinned fixture where the comparative
choice depends on one authoritative external behavior or design principle not stated in repository
lines. Record CLI/model versions, exact packet IDs and URLs, research/decider call counts, elapsed
time, packet digest, both decisive source references, and computed convergence. Include one UGC
lead, one unrelated non-UGC publisher mislabelled primary, one passage mismatch, and prove none can
substantiate. Separately run a real plan claim whose discovered URL is captured and whose exact
passage is bound in-session from the shared Trafilatura output. Also run explicit `research: false` on a
repository-settled fixture and prove both deciders receive web search disabled and converge from
repository evidence.

Run the complete local test suite, then Codex paranoia convergence over the implementation branch
under the frozen stakes above. Open and merge a PR only after real acceptance, tests, documentation,
and computed code-review convergence are all clear.

## Acceptance criteria

1. External research cannot influence a reported convergence without appearing in the shared,
   logged, server-captured packet, being referenced by a converging vote, and receiving explicit
   positive authority and entailment judgements from every source-relying decider.
2. Both deciders receive byte-identical external packets and remain cold and independently judged.
3. Repository-only mode performs no research and no web-enabled decider call.
4. Weak, UGC, non-web, self-referential, uncaptured, passage-mismatched, malformed, over-budget, or
   unknown evidence cannot substantiate a vote or close a plan claim.
5. Research is one bounded pre-vote phase; arbitration remains capped at one existing repository
   reconciliation round and has no persistent evidence lifecycle.
6. Existing snapshot, ref-movement, cleaner/attester, counterbalancing, label, risk, authority,
   new-option, and deterministic-outcome guarantees remain intact.
