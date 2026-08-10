# Plan: bounded shared research for arbitration

## Status

Proposed for implementation after tracked plan convergence.

## Frozen stakes

`paranoia-local` is a trusted-single-user local MCP on a trusted OS. The caller, repository,
framing, and fetched web text are untrusted data, but no repository-selected code is executed and
no hostile local process races files or refs. Both signed-in reviewer CLIs are available. An
ordinary arbitration has 2–4 options, Git 2.36 or newer, a repository small enough for the existing
pinned-snapshot workflow, 0–12 decision-critical external claims, and must remain useful within minutes and below
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

The first implementation supports the installed, acceptance-tested CLI profiles Codex 0.144.6 and
Claude Code 2.1.197, and Git 2.36 or newer. A different provider version or older Git fails
evidence-mode preflight with an upgrade instruction;
adding a profile requires rerunning the inventory and real acceptance fixtures. The implementation
relies on exactly these provider behaviors, which plan verification must keep in its active
external-claim inventory:

- Codex CLI's `web_search` configuration has explicit `live`, `cached`, and `disabled` modes;
  `disabled` removes the search tool, non-interactive `codex exec` supports live search, and
  `codex exec resume <session-id>` continues that session. `--ignore-user-config` excludes the
  user config but trusted-project `.codex/config.toml` is loaded separately and may register MCP
  servers. Project configuration is discovered from the project root through the current working
  directory. Fresh and resumed `codex exec` accept explicit `--disable <feature>` overrides.
- Claude Code's `WebSearch` returns candidate source titles and URLs for discovery in print mode,
  and `claude -p --resume <session-id>` continues a print-mode session. Claude's `--tools`
  with an empty value removes all built-ins when no MCP tools remain; `--strict-mcp-config` with no
  supplied config establishes that condition. `--setting-sources ""` loads no user, project, or
  local settings sources. `--safe-mode` disables documented customizations including skills,
  plugins, hooks, MCP servers, custom commands, and agents while preserving built-in tools and
  permissions.
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

### Inert evidence premises

Git `ls-tree -r` recursively lists a named tree object. Its `--full-tree` option does not limit the
listing to the current working directory and implies `--full-name`, so emitted paths are relative
to the tree root. Its `-z` option does not quote filenames and terminates each output record with
NUL. Git `cat-file -t <object>` reports
the named object's actual type. After the server has required that type to be `blob`,
`git cat-file blob <object>` prints its raw, uncompressed contents; the separate type check avoids
the typed form's documented trivial dereferencing behavior. These are the raw enumeration/read
semantics used by the inert materializer. `GIT_NO_LAZY_FETCH=1` prevents commands from lazily
fetching missing objects. These assertions bind to the official
[`git-ls-tree`](https://git-scm.com/docs/git-ls-tree),
[`git-cat-file`](https://git-scm.com/docs/git-cat-file), [`git`](https://git-scm.com/docs/git), and
[`git-config`](https://git-scm.com/docs/git-config) references.

Git 2.36 and newer understands boolean `core.fsmonitor` values; the official compatibility note
states that Git 2.35.1 and earlier instead treat `true` and `false` as hook pathnames. Evidence mode
therefore preflights Git 2.36 or newer before any snapshot command. Git `update-index --index-info`
removes a path when its input record has mode zero. Command-scope
configuration supplied with `git -c` overrides worktree, local, global, and system values for that
command. Within the supported Git range, `core.fsmonitor=false` disables the fsmonitor extension
and hook. On `git log`,
`--no-patch` suppresses diff output and `--format=...` formats the selected commit metadata. These
are the only repository-configured
execution controls and metadata-history semantics on which the inert launcher relies; they bind to
the official [`git-update-index`](https://git-scm.com/docs/git-update-index),
[`git-config`](https://git-scm.com/docs/git-config), and
[`git-log`](https://git-scm.com/docs/git-log) references.

Codex `workspace-write` permits reads outside its writable roots but confines writes to the
current working directory and configured writable roots; `/tmp` and the directory named by
`TMPDIR` remain writable unless their two documented exclusions are enabled. This documented
sandbox behavior is why the wrapper can inspect an out-of-root evidence target while both temp
exclusions prevent that target from becoming implicitly writable. This assertion binds to the
official [Codex security and approvals documentation](https://developers.openai.com/codex/security/).
Absence of every external tool in the complete pinned-version deny profile is an empirical
supported-profile condition, not a broader documented Codex guarantee: preflight and signed-in
fresh/resume acceptance must establish it before evidence mode is usable.

## Required behavior

### 1. Two explicit modes

Add `research`, default `true`, to `arbitrate`.

- `research: true` requires `web_search: true` for the research agents only. It runs the bounded
  shared phase below. Both voting rounds have web tools mechanically disabled: the normalized
  packet is the complete registered web-derived corpus available during voting. Repository bytes
  and the model's pre-existing knowledge remain inputs under the trusted-local stakes; no
  repository or user configuration may add a live external tool.
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

Every evidence-isolated Codex role starts from a trusted empty temporary launch root, never from
the reviewed repository. When repository access is required, the pinned inert evidence tree is
exposed beneath `repository/`; the prompt defines that directory as the citation root and the
server strips exactly that prefix before resolving citations against the pinned snapshot. The
project's `.codex/config.toml`, plugins, rules, and instructions remain readable as ordinary files
under `repository/` but are not in Codex's startup ancestry and therefore cannot configure the
session. The wrapper itself contains no project configuration. Research/binding sessions retain
their launch root until the final resume completes, then remove it. This is an orchestration
boundary, not a new container or provider abstraction.

First replace the shared working-tree snapshot writer used before arbitration. `snapshot_tree`
must not call `git add`, checkout, or any other operation that applies attributes. Seed a private
index with `git read-tree <pinned-head>`, enumerate tracked and non-ignored untracked paths with
`git ls-files -z --cached --others --exclude-standard`, compare that inventory with the filesystem
to remove deleted paths, and hash each regular file's raw stdin bytes (or a symlink's raw target
bytes) with `git hash-object -w --stdin --no-filters`. Feed the resulting mode/OID/path records to
the private index with NUL-delimited `git update-index --index-info`, then `write-tree`. All of
those commands use the same empty system/global configuration and no optional locks; every
subprocess return code and expected OID/byte length is checked. Repository ignore rules may decide
which untracked paths belong in the snapshot, but repository attributes, hooks, clean/process
filters, external diff, textconv, and checkout machinery are never evaluated. Preserve the current
working-tree semantics, including tracked-but-ignored files, deletions, executable modes, symlinks,
and gitlinks. For each initialized tracked submodule, record its currently checked-out commit;
an uninitialized submodule retains the pinned superproject gitlink. Do not narrow arbitration to
committed-only input.

Put every Git invocation in snapshotting, inert materialization, and metadata-only history behind
one shared inert-plumbing launcher. It sets `GIT_CONFIG_NOSYSTEM=1`, an empty global configuration,
`GIT_NO_LAZY_FETCH=1`, and `GIT_OPTIONAL_LOCKS=0`, and passes command-line overrides including
`core.fsmonitor=false`. The empty system/global layers are deterministic hygiene under the trusted
operator stakes, not part of the no-helper proof. Local repository configuration remains readable
only where Git needs object-store/promisor metadata, but neither an fsmonitor hook nor a configured
promisor transport may execute: missing objects fail the checked plumbing call. None of the chosen
plumbing commands invokes ordinary Git hooks, diff, or textconv, so the plan does not add redundant
settings for those unrelated surfaces. No evidence path calls Git outside this launcher.

Do not create the later evidence tree with `git worktree`, checkout, archive filters, or any
model-run Git command. Add an inert server materializer that reads the pinned commit with plumbing only:
`git ls-tree -rz --full-tree` enumerates entries. For each enumerated blob, `git cat-file -t <oid>`
must return exactly `blob` before `git cat-file blob <oid>` reads its raw contents. Every invocation
uses the shared launcher, including `GIT_NO_LAZY_FETCH=1`, so Git does not lazily fetch a missing
promised object through a repository promisor remote. The materializer fails closed on a nonzero
plumbing result, an absent object, an unexpected object type, or a blob whose length or digest does
not match its enumerated object. It writes ordinary files itself; executable bits are
recorded in a manifest but not made executable, symlinks are rendered as inert target-text records,
and gitlinks are rendered as submodule-OID records. No checkout/filter/process driver runs.

Evidence-isolated model roles receive no Git commands. Claude's repository allowlist is reduced to
`Read`, `Grep`, and `Glob`. Codex runs a network-restricted `workspace-write` sandbox rooted at its
disposable empty launch directory with `sandbox_workspace_write.exclude_slash_tmp=true`,
`exclude_tmpdir_env_var=true`, `network_access=false`, and `writable_roots=[]` on fresh and resumed
commands. The inert repository tree is a sibling outside the writable root and is exposed by a
read-only symlink. It can run `rg`, `sed`, and similar inspections
unattended but cannot modify the evidence tree. When history is useful, the server
renders a bounded metadata-only `git log --no-patch --format=...` record under the same empty-config
environment; it never renders patches through diff/textconv. Arbitration citation resolution still
uses the original pinned blobs, while the inert manifest makes exceptional symlink/gitlink entries
explicit. The same inert tree grounds verified plan structure. This replaces, rather than wraps,
the config-bearing worktree path for evidence-isolated roles.

Every Codex evidence role also applies one explicit profile tested against the supported version on both
fresh and resumed commands. It disables `apps`, `browser_use`, `browser_use_external`,
`browser_use_full_cdp_access`, `computer_use`, `in_app_browser`, `plugins`, `remote_plugin`,
`plugin_sharing`, `enable_mcp_apps`, `image_generation`, `multi_agent`, `workspace_dependencies`,
`auth_elicitation`, `tool_call_mcp_elicitation`, `skill_mcp_dependency_install`, `hooks`, and
`tool_suggest`. Discovery alone sets `web_search="live"`; binding, voting, repository-only, and
verified plan-structure roles set `web_search="disabled"`. Preflight requires the exact supported
CLI profile and confirms every named flag exists; it does not claim `codex features list` is a
complete tool inventory. The allow surface is the shell inside a disposable `workspace-write`
launch root, under the CLI's network-restricted sandbox, not an open-ended feature default. Fresh
and resumed calls set `approval_policy="never"`; the supported-profile acceptance must demonstrate
unattended `rg`/`sed` reads, failure to mutate the out-of-root evidence tree, and no network access.

Every Claude evidence role adds `--safe-mode`, `--setting-sources ""`, `--strict-mcp-config` with no
supplied MCP config, and its exact `--tools` set. Discovery exposes only `WebSearch`;
binding exposes no built-in tools; repository-reading voting and plan-structure roles expose only
`Read`, `Grep`, and `Glob`. Resume repeats the same role flags instead
of assuming the original session's inventory remains narrowed.

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
12 unique normalized propositions and one candidate record per proposition; duplicate normalized
propositions within one producer are rejected. Bound fields are: proposition 1,200 characters,
URL 2,048, title 400, publisher 200, authority basis 600, location 400, and exact passage 1,200.
Each captured document is at most 40,000 extracted characters and each producer's binding input is
at most 400,000 rendered characters. The deterministic two-producer union may contain at most 24
propositions, two records per normalized proposition, and 200,000 rendered packet characters.
The maximum accepted field payload plus fixed rendering overhead is below that union limit.
Exceeding a producer, field, capture, binding-input, or union budget fails visibly rather than
truncating evidence and calling the result complete. These limits compose without assuming that
independently worded claims deduplicate.

### 4. Identical evidence for both deciders

Render the normalized union once, hash it, and include the exact same packet bytes in both
decider prompts. Research output is untrusted evidence, not instruction: packets carry no option
recommendation and the prompt requires each decider to judge publisher authority for the precise
proposition, passage entailment, relevance, and contradictions independently. Deciders cannot
use provider search, browser, app/connector, computer-use, plugin, MCP, or shell-network paths;
no live external bytes outside the logged packet can enter a vote. Repository bytes and model
pretraining remain the explicitly stated non-web inputs.

The server rejects caller IDs across the complete rendered research packet—including final URLs,
metadata, locations, and captured passages—before labels are generated or either decider runs.
It also rejects temporary order labels or trailer-field injection. The prompt forbids selection,
comparison, ranking, and recommendations, but the server
does not use a brittle natural-language advocacy detector that would also reject a technology's
name. Canonical/reversed research presentations make option-order exposure symmetric by
construction; this plan does not claim that counterbalancing eliminates or measurably reduces
model bias. Final high-entropy decider labels are generated only after the packet exists, and the
existing absence scan covers the packet as decider-visible text.

The protocol does not claim to prove what internal model knowledge causally produced a vote.
Pretraining is a declared input. Its proportionate semantic control is two cold deciders who see
the same registered live corpus and independently expose relevance reasons; adding a third LLM
would move, not mechanize, that judgement. A wrong unanimous relevance assessment remains residual
model error, as it does for repository-citation relevance, rather than evidence of an unlogged live
source path.

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
source vote also requires `DECISION-RELEVANCE: YES|NO — <reason>`. It is substantiated only when all
three judgements are `YES`; each cold decider therefore exposes authority, entailment, and why the
registered proposition materially supports its selected option under the frozen stakes. For a
repository decisive citation all three fields must be `N/A`. For a source reference, `CONSTRAINT`
must equal the referenced packet's exact
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

Cleaner and attester calls use 210-second caps. Discovery calls use 120-second caps and binding
calls use 180-second caps; each may have one same-session correction at the same cap. Server
capture has a 120-second phase cap. The explicit worst path is therefore: cleaner initial/retry
420 seconds, attester initial/retry 420, discovery initial/correction 240, capture 120, binding
initial/correction 360, decision round one 900, and decision round two 900 = 3,360 seconds.
Parallel vendors count once per group. This
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
  MCP disabled. Before state transition, start one cold evidence attester with all external and
  repository tools disabled. It receives only the atomic claim, publisher/authority metadata,
  capture metadata, and exact passage, and returns strict independent
  `PUBLISHER-AUTHORITY` and `PASSAGE-ENTAILMENT` verdicts with reasons. A plan claim becomes
  supported only from a server-captured matching passage with both cold verdicts `YES`; researcher
  labels and the absence of a UGC hostname are never sufficient.
  Retained evidence is recaptured when re-entailing edited claims; a failed or stale capture
  becomes visible unverified evidence rather than being grandfathered. Keep capture injectable so
  deterministic plan-claim tests do not perform network I/O.
  While touching retained-evidence binding, remove line-layout marker text from assertion-body
  matching: heading and list ancestry still identify the assertion, but a Markdown reflow that
  leaves an exact anchor and proposition unchanged must retain its frozen packet instead of
  forcing unrelated web research.
- Add pure research packet types, parsing, normalization, union, budgets, digesting, and tagged
  decisive-reference parsing to `arbitration.py` or one small `arbitration_research.py` module.
- Add a small inert snapshot materializer beside `worktree.py`; use raw tree/blob plumbing, inert
  symlink/gitlink records, and bounded metadata-only history. Evidence-isolated arbitration and
  verified-plan roles use it instead of `worktree_at` and receive no model-visible Git commands.
- Add one small shared context manager for sanitized Codex launch roots and retained resume roots;
  use it from `handlers.py` for verified plan reviews and from `arbitrate_handler.py`. Keep the
  metadata-preserving research call/result and resume seam, repository-prefix citation mapping,
  parallel research calls, bounded correction, whole-run deadline, identical packet injection,
  logging, and progress in the relevant handler.
- Extend both engine implementations to the minimum explicit internal role modes needed here.
  The supported-version preflight selects a fixed profile rather than inferring completeness from
  feature flags. Codex discovery passes `web_search="live"`; all binding, voting, repository-only arbitration,
  and verified plan-structure calls pass `web_search="disabled"`, never omission/cached, and set
  `approval_policy="never"`. Fresh and
  resumed Codex roles repeat the complete external-feature deny profile, keep
  `--ignore-user-config`, and start outside the project. Claude evidence roles repeat `--safe-mode`,
  `--setting-sources ""`, `--strict-mcp-config`, and role-specific `--tools`; discovery gets
  only `WebSearch`, binding gets none, and repository roles get exactly `Read`, `Grep`, and `Glob`
  without Bash or web. Codex repository-reading roles use `workspace-write` only for the disposable
  wrapper; the separately materialized evidence target is outside writable roots. Existing full
  mode remains for unrelated tools. Do not expose a provider
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
  cannot reproduce; retained evidence is recaptured before re-entailment; unrelated or
  wrong-subject publishers labelled `primary` remain unverified unless the cold plan-evidence
  attester independently accepts publisher authority and passage entailment;
- unrelated non-UGC publishers falsely labelled `primary`, and publishers authoritative for a
  different subject, remain unsubstantiated when deciders reject authority or entailment;
- counterbalanced research framing and byte-identical normalized evidence for both deciders;
- caller/order/decider-label leakage rejection;
- repository and `SOURCE:` decisive-reference parsing, rendering, resolution, and substantiation;
- an otherwise eligible unrelated packet with all three judgement fields `YES` remains unsubstantiated
  when `CONSTRAINT` differs from its exact normalized proposition;
- an eligible packet with an exactly copied proposition and positive authority/entailment remains
  unsubstantiated when `DECISION-RELEVANCE` is `NO`; require the real acceptance deciders to explain
  the causal comparison rather than merely restate the packet;
- unknown or non-governing source IDs cannot converge;
- source references never enter repository region reconciliation;
- `research: false` disables web search and makes no research calls;
- `research: true, web_search: false` fails before spend;
- engine argv tests prove Codex researchers use explicit `live`, Codex voters/repository-only and
  verified plan-structure reviewers use explicit `disabled`; every named external Codex feature is
  disabled on fresh and resume; Claude discovery exposes only `WebSearch`; Claude binding exposes
  nothing; and Claude voting/verified-plan roles expose only the read-only repository allowlist;
- sanitized-root tests place sentinel MCP/plugin configuration under `repository/.codex`, prove it
  is readable as evidence but absent from fresh and resumed Codex tool inventories, and prove
  `repository/` citations normalize to the pinned repository path before resolution;
- inert-materialization fixtures define smudge/process filters, textconv, external diff, hooks,
  executable files, symlinks, and gitlinks; marker helpers never run during materialization or
  reviewer reads, while raw expected bytes/manifests remain visible; the fixture starts before the
  shared dirty-tree snapshot and proves the markers also remain absent during snapshot creation.
  A partial-clone fixture with a missing promised blob and executable `ext::` promisor remote
  produces no helper marker under `GIT_NO_LAZY_FETCH=1`, and the materializer fails closed on the
  missing/non-blob/length-or-digest-mismatch result without promising one Git-specific presentation;
- supported-version acceptance captures the expected fresh/resumed Codex tool inventory and proves
  browser, app/connector, computer-use, plugin, MCP, image-generation, workspace-dependency, and
  delegation tools are absent; an unsupported CLI version fails preflight before either provider
  call without claiming that feature flags enumerate all future tools;
- evidence-mode preflight accepts Git 2.36 and the installed Git 2.50.1, rejects a simulated 2.35.1
  before snapshotting, and the supported minimum-version fixture proves `core.fsmonitor=false`
  does not execute a configured `false` hook pathname;
- the supported Codex profile runs `rg` and `sed` against the inert tree unattended from its
  disposable `workspace-write` root with `approval_policy="never"`, while evidence-tree mutation
  and network/escalation attempts fail without prompting; captured sandbox policy proves both temp
  exclusions and an empty additional-writable-root list were applied on fresh and resume, and
  pre/post digests prove immutability;
- malformed discovery or binding retains the exact preceding session reference, receives one
  resume correction, and then fails closed; capture binding itself resumes the discovery session;
  raw output, call count, usage, and durations remain auditable;
- every phase cap composes below the whole-run deadline with reserved teardown margin, and a phase
  that cannot fit is not started;
- existing repository-only arbitration behavior and outcome computation remain compatible.
- a dedicated inert-launcher fixture configures an executable `core.fsmonitor` and an executable
  `ext::` promisor remote before snapshotting, then proves neither marker runs during snapshot,
  materialization, metadata-history rendering, or reviewer reads.
- assertion-binding tests prove wrapping or unwrapping a list item's unchanged sentence retains
  its frozen packet, while negation, relocation to another list item, or proposition edits stale it.

### Real acceptance before PR

Run signed-in Codex and Claude arbitration against a small pinned fixture where the comparative
choice depends on one authoritative external behavior or design principle not stated in repository
lines. Record CLI/model versions, exact packet IDs and URLs, research/decider call counts, elapsed
time, packet digest, both decisive source references, and computed convergence. Include one UGC
lead, one unrelated non-UGC publisher mislabelled primary, one passage mismatch, and prove none can
substantiate. Separately run a real plan claim whose discovered URL is captured and whose exact
passage is bound in-session from the shared Trafilatura output. Also run explicit `research: false`
on a repository-settled fixture and prove both deciders receive web search disabled and converge from
repository evidence. In the real Codex fixtures, put a harmless sentinel MCP under project
`.codex/config.toml`; prove it is neither started nor listed in fresh voting/plan-structure roles
or the resumed binding role. Include inert Git-helper markers and prove none executes. Also have those roles attempt the browser, app/connector,
computer-use, plugin, and native-search paths and prove the CLI exposes none. Record the exact
Codex/Claude versions and effective fresh/resumed tool inventories with the acceptance artifact.

Run the complete local test suite, then Codex paranoia convergence over the implementation branch
under the frozen stakes above. Open and merge a PR only after real acceptance, tests, documentation,
and computed code-review convergence are all clear.

## Acceptance criteria

1. External research cannot influence a reported convergence without appearing in the shared,
   logged, server-captured packet, being referenced by a converging vote, and receiving explicit
   positive authority, entailment, and decision-relevance judgements from every source-relying
   decider.
2. Both deciders receive byte-identical external packets and remain cold and independently judged.
3. Repository-only mode performs no research and no web-enabled decider call.
4. Weak, UGC, non-web, self-referential, uncaptured, passage-mismatched, malformed, over-budget, or
   unknown evidence cannot substantiate a vote or close a plan claim.
5. Research is one bounded pre-vote phase; arbitration remains capped at one existing repository
   reconciliation round and has no persistent evidence lifecycle.
6. Existing snapshot, ref-movement, cleaner/attester, counterbalancing, label, risk, authority,
   new-option, and deterministic-outcome guarantees remain intact.
7. Evidence materialization and model-visible reads execute no repository-selected Git helper;
   supported CLI profiles expose no live external tool outside the discovery phase.
