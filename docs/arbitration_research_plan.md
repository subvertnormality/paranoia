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

The fix must preserve the protocol's central property: the two deciders differ in judgement and
search path, not in framing or evidence. Independent unrecorded browsing by each decider is not a
research phase because it gives them different, unaudited corpora.

## Required behavior

### 1. Two explicit modes

Add `research`, default `true`, to `arbitrate`.

- `research: true` requires `web_search: true`. It runs the bounded shared phase below and lets
  deciders browse only to reopen and challenge the shared sources. New external material found by
  a decider cannot substantiate a vote unless it is already a registered packet.
- `research: false` is explicit repository-only arbitration. Both decider calls run with web
  search disabled, and only existing repository citations can substantiate convergence.
- `research: true, web_search: false` is rejected before any agent call. There is no quiet
  degraded mode.

This removes the current halfway state. Research remains on by default because arbitration is a
general technical decision tool, but callers with a genuinely repository-settled question can
avoid its cost explicitly.

### 2. Balanced research fan-out

After framing has been cleaned and cross-vendor attested, but before either decider votes, run one
cold research agent from each vendor in parallel. Both receive the same cleaned decision,
context, stakes, hints, and option statements. One receives canonical option order and the other
the reverse, without caller IDs. Neither is told the other exists and neither may select,
recommend, rank, or name an option.

Each researcher inventories only atomic, load-bearing propositions about the external world whose
truth or authority could change the comparative result:

- `fact`: external state, event, quantity, identity, or history;
- `design_principle`: a requirement, constraint, or recommendation issued by the governing
  external standard, regulator, protocol, platform, or vendor;
- `behavior`: behavior promised by an external dependency, API, platform, protocol, service, or
  runtime.

Repository state, code behavior, internal history, project preferences, option advocacy,
forecasts, and incidental facts are excluded. The researchers use their built-in web search and
return only a concrete JSON record after a terminal marker. One bounded same-session correction
is allowed for malformed output; a second failure fails arbitration visibly.

### 3. Authoritative source packets

Each research claim contains one atomic proposition and evidence records with:

- canonical HTTP(S) URL, title, publisher, precise location, and exact passage;
- `primary`, `authoritative`, `secondary`, or `ugc` source kind;
- publisher authority basis;
- `supports_claim`, `refutes_claim`, or `context` relation.

Only primary or authoritative HTTP(S) evidence may govern a packet. Known UGC hosts—including
Reddit, forums, Stack Overflow, social media, wikis, and community publishing—are mechanically
non-governing even when model-labelled `primary`. Secondary and UGC material remains context.
The repository, local files, custom schemes, and the caller framing cannot evidence their own
external assertions.

Extract the small generic URL/source qualification rules currently used by plan verification into
one shared module used by both plan claims and arbitration research. Do not duplicate authority
policy or import private plan-lifecycle machinery into arbitration.

The server validates shape and authority, preserves conflicting authoritative packets, drops
non-governing relations from substantiation, assigns stable run-local IDs from packet content,
deduplicates byte-identical packets, and takes the deterministic union of both researchers'
valid results. It does not ask a model to merge or summarize them.

Budgets are corruption/pathology guards, not sampling targets: at most 24 claims total, four
evidence records per claim, 4,000 characters per quote, and 80,000 rendered packet characters.
Exceeding a budget fails visibly rather than truncating evidence and calling the result complete.

### 4. Identical evidence for both deciders

Render the normalized union once, hash it, and include the exact same packet bytes in both
decider prompts. Research output is untrusted evidence, not instruction: packets carry no option
recommendation and the prompt requires each decider to reopen authoritative URLs as needed,
check authority and entailment independently, and disregard irrelevant or contradicted packets.

The server rejects research output containing caller IDs, its temporary order labels, trailer
field injection, or option recommendations. Final high-entropy decider labels are generated only
after the packet exists, and the existing absence scan covers the packet as decider-visible text.

### 5. External evidence can substantiate a vote

Extend the decisive-evidence grammar from only `<path>:<line>` to exactly one of:

- a pinned repository citation in the existing form; or
- `SOURCE:<packet-id>` referencing a qualifying shared packet.

Represent this as an explicit tagged reference in the pure arbitration core rather than encoding
source IDs as fake repository paths. A source reference resolves only when the ID exists in the
shared normalized packet and has qualifying primary/authoritative evidence. Unknown, context-only,
secondary-only, or UGC-only IDs are unsubstantiated. The vote's `CONSTRAINT` remains the decider's
one-line statement of what the evidence establishes; semantic relevance is independently judged
by both cold deciders, not asserted by the research model.

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

### 7. Audit and progress

Add progress events for shared research and validation. Add trailer fields:

- `RESEARCH: complete <N> packets | repository-only`
- `RESEARCH-DIGEST: <sha256> | none`

The audit log records both raw research replies, correction replies if any, normalized packets,
packet digest, research model names, call count, duration, and the exact shared bytes shown to
each decider. The existing snapshot/ref movement, cleaner, attestation, order, label, vote, and
round records remain intact.

## Code shape

- Add a small `external_sources.py` for generic source schema, HTTP(S)/UGC qualification, and
  normalized evidence records; migrate `plan_claims.py` to it without changing plan behavior.
- Add pure research packet types, parsing, normalization, union, budgets, digesting, and tagged
  decisive-reference parsing to `arbitration.py` or one small `arbitration_research.py` module.
- Keep orchestration in `arbitrate_handler.py`: parallel research calls, bounded correction,
  identical packet injection, logging, and progress.
- Update `prompts.py`, `server.py`, README, `docs/arbitration_plan.md`, AGENTS.md, and CLAUDE.md.
- Add no persistent store, lineage, cache, daemon, transport, or third-party dependency.

## Verification

### Focused deterministic tests

- research JSON parsing, exact literals, budgets, deterministic IDs/union/digest, and conflict
  retention;
- primary/authoritative HTTP(S) qualification and hard UGC/non-web/self-context rejection shared
  with plan claims;
- counterbalanced research framing and byte-identical normalized evidence for both deciders;
- caller/order/decider-label leakage rejection;
- repository and `SOURCE:` decisive-reference parsing, rendering, resolution, and substantiation;
- unknown or non-governing source IDs cannot converge;
- source references never enter repository region reconciliation;
- `research: false` disables web search and makes no research calls;
- `research: true, web_search: false` fails before spend;
- malformed research receives one correction and then fails closed;
- existing repository-only arbitration behavior and outcome computation remain compatible.

### Real acceptance before PR

Run signed-in Codex and Claude arbitration against a small pinned fixture where the comparative
choice depends on one authoritative external behavior or design principle not stated in repository
lines. Record CLI/model versions, exact packet IDs and URLs, research/decider call counts, elapsed
time, packet digest, both decisive source references, and computed convergence. Include one UGC
lead and prove it cannot substantiate. Also run explicit `research: false` on a repository-settled
fixture and prove both deciders receive web search disabled and converge from repository evidence.

Run the complete local test suite, then Codex paranoia convergence over the implementation branch
under the frozen stakes above. Open and merge a PR only after real acceptance, tests, documentation,
and computed code-review convergence are all clear.

## Acceptance criteria

1. External research cannot influence a reported convergence without appearing in the shared,
   logged, authoritative packet and being referenced by a converging vote.
2. Both deciders receive byte-identical external packets and remain cold and independently judged.
3. Repository-only mode performs no research and no web-enabled decider call.
4. Weak, UGC, non-web, self-referential, malformed, over-budget, or unknown evidence cannot
   substantiate a vote.
5. Research is one bounded pre-vote phase; arbitration remains capped at one existing repository
   reconciliation round and has no persistent evidence lifecycle.
6. Existing snapshot, ref-movement, cleaner/attester, counterbalancing, label, risk, authority,
   new-option, and deterministic-outcome guarantees remain intact.
