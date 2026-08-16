# Paranoia

Get a cold, adversarial review of your code, your plans, and your decisions from
the *other* frontier coding agent — running locally, on its own subscription, with
full read access to your repository.

Install it into Claude Code and reviews are performed by Codex. Install it into
Codex and reviews are performed by Claude Code. paranoia-local is the MCP server
between them: it builds the prompt, runs the other agent read-only, and returns a
structured critique.

```
┌──────────────┐   "paranoia: critique this branch"   ┌───────────────┐
│  Claude Code │ ───────────────────────────────────► │ paranoia-local│
│  (your work) │                                      │  (MCP, local) │
└──────────────┘                                      └───────┬───────┘
                                                              │ codex exec (read-only)
                                                      ┌───────▼────────┐
                                                      │  Codex / GPT-5 │ ← reads the repo,
                                                      │  cold reviewer │   decides what to open
                                                      └────────────────┘
```

**Contents** · [Quickstart](#quickstart) · [The five tools](#the-five-tools) ·
[How reviews work: the convergence loop](#how-reviews-work-the-convergence-loop) ·
[Tool reference](#tool-reference) · [Output reference](#output-reference) ·
[Configuration](#configuration) · [Safety model](#safety-model) ·
[Development](#development)

---

## Quickstart

**1. Prerequisites**

- Python 3.11+ and `git` on `PATH`
- The reviewing agent's stable CLI, installed and signed in on a subscription:
  [Codex CLI](https://developers.openai.com/codex) (`codex`, ≥ 0.144.6) **or**
  [Claude Code](https://code.claude.com) (`claude`, ≥ 2.1.197)
- `arbitrate` needs **both** CLIs; the four review tools need only the other one

**2. Install**

```bash
git clone https://github.com/subvertnormality/paranoia-local
cd paranoia-local
pip install -e .
```

**3. Wire it into your agent.** `--engine` names the agent that *performs* reviews,
which is the opposite one from the caller.

<details open>
<summary><strong>Into Claude Code</strong> (reviews performed by Codex)</summary>

```bash
claude mcp add paranoia -- paranoia-local --engine codex
```
</details>

<details>
<summary><strong>Into Codex</strong> (reviews performed by Claude Code) — needs two extra keys</summary>

```bash
codex mcp add paranoia -- paranoia-local --engine claude
```

Then edit `~/.codex/config.toml`. Codex defaults to a 60-second tool timeout and a
10-second startup timeout; a review runs for minutes, so both must be raised or
every call fails:

```toml
[mcp_servers.paranoia]
command = "paranoia-local"
args = ["--engine", "claude"]
tool_timeout_sec = 7200
startup_timeout_sec = 60
```

Verify with `codex mcp get paranoia`.
</details>

**4. Ask for a review.**

> "Use paranoia to critique this branch against main. Intent: add overdraft
> protection to `withdraw()`."

Your agent calls:

```json
{
  "name": "critique_branch",
  "arguments": {
    "repo_path": "/Users/you/Work/my-project",
    "base_ref": "main",
    "round": 1,
    "diff_intent": "Add overdraft protection to withdraw()."
  }
}
```

You get back a five-section critique with severity-tagged findings, and a computed
`CONVERGENCE:` trailer telling you whether the loop may stop.

---

## The five tools

| Tool | Use it to | Needs |
|---|---|---|
| [`critique_branch`](#critique_branch) | Review a git branch, a diff, or the dirty working tree | `repo_path` |
| [`critique_plan`](#critique_plan) | Review a plan or design doc against the code it claims things about | `repo_path` + `plan_text` \| `plan_path` |
| [`query`](#query) | Ask one question and get a cited answer — not a full review | `question` |
| [`rebut`](#rebut) | Dispute a finding from a review you just got | `session_ref` from that review |
| [`arbitrate`](#arbitrate) | Decide between 2–4 options using **both** vendors independently | `repo_path`, `decision`, `options`, `stakes` |

Every review returns a `session_ref` in its footer. Pass it to `rebut` to reopen
that exact reviewer session.

---

## How reviews work: the convergence loop

A single review is rarely the end of it. You review, you fix, you review again.
paranoia-local models that as a **convergence loop**, and gives you four controls
over it plus one computed signal that tells you when to stop.

### The loop

```
round 1 ──► review ──► fix ──► round 2 ──► review ──► fix ──► round 3 ──► CONVERGED
             │                              │                              +
             └── already_raised ────────────┴── already_raised ────► CONVERGENCE: NOT-BLOCKED
```

Tracked plan reviews use a staged lifecycle. A new or materially changed plan starts with three
independent cold lanes and one consolidation call. Their complete finding census becomes durable
debt. Later correction rounds target that debt and correction effects; once it closes, one fresh
whole-artifact final regression is mandatory. A clear initial census may converge immediately.
This preserves broad first-pass/final coverage without paying for novelty hunting over unchanged
material on every correction round. Tracked branch reviews use the same lifecycle: a broad, cold
three-lane census, targeted correction rounds over durable debt and changed code, and a mandatory
broad, cold final regression before clearance. Every staged branch role retains the established
code-review investigation, packet-use, proportionality, and warranted-web-search profile; only its
structured output contract changes. The staged roles use closed, role-specific provider schemas,
then the server validates the complete bounded schema and semantic graph independently. The
server derives each census class outcome exactly once from the validated integrity-lane assessment;
the consolidator supplies only the governing classification/source relationship needed for a
violation. Cross-lane findings cannot append an outcome or override an integrity-lane satisfaction
judgement. Correction and final class outcomes remain model-owned. The pinned Codex
schema subset lacks `uniqueItems`, and Claude must not receive the draft-identifying
`$schema` metadata. Those two non-semantic keywords are removed only from the provider projection;
uniqueness remains mandatory in local validation, so duplicates can trigger the existing
same-session correction but can never settle. There is no prose/marker fallback. One-shot reviews
retain the single broad review.
For Claude, schema success additionally requires an object in the provider envelope's
`structured_output`; a zero exit status with only result prose is a provider failure. Branch class
schemas reject leading-colon Git pathspec magic, and replacements of mechanized classes must retain
a pattern plus literal pathspec. The local semantic pass returns bounded, deterministically ordered
independent graph, model-owned anchor, and canonical-class issues with model-repairable JSON
pointers so the single validation retry can repair more than the first defect. Whitespace-only
semantic text, lane replies above 240,000 characters, and decision replies above 1,000,000
characters fail before settlement or JSON decoding. The separate composed-prompt circuit breaker
remains 5,000,000 characters.
If all three census lanes validate but consolidation is rejected, their manifests are persisted
with the lineage and the next invocation reruns consolidation only. Reuse requires an exact match
on mode, structural snapshot, complete review body and open debt, frozen stakes, active-class state,
engine/model/effort/web capability settings, plan line context, and cache schema. It is recorded only
after terminal validation rejection; the binding also digests the exact composed lane prompt bytes,
including current instructions and provider schema. Execution failure, timeout, cancellation, or failed retry is
not reusable. Any binding change or incomplete lane set forces a fresh census.

Durable lineage state carries concrete findings, reusable classes, frozen stakes, phase, and plan
claim evidence forward; the reviewer never relies on chat memory. `STRUCTURAL-PHASE` and
`STRUCTURAL-DEBT` in the trailer show where the autonomous loop is. There is no fixed round ceiling:
provider, parsing, deadline, or oversized-state failures block visibly rather than clearing.

### `round` — lineage ordering

The 1-based round number. **Increment it every round.** In tracked staged plan and branch review,
census and final remain complete at every in-scope severity while correction is limited to durable
debt and repair effects; convergence comes from that phase boundary. One-shot and injected-engine
legacy paths retain their single broad review and round-3 severity floor.

`round` is required on `critique_branch` and `critique_plan` unless you pass
`class_closure: false`.

### `stakes` — the scope boundary

The real deployment context, threat model, and scale the work operates in:

```json
"stakes": "Internal booking API, single team, authenticated first-party callers, ~1k req/min."
```

The reviewer treats it as the **boundary of legitimate concern**. Findings that
assume adversaries, scale, or failure modes beyond it are dropped or tagged
`[OUT-OF-SCOPE]`, never must-fix. Omit it and the reviewer assumes a modest
internal tool; a review with no stakes ends with a `STAKES: unstated` line. Pass
`stakes: "unstated"` to accept that reading deliberately and silence the line.

Set it once per project in [`.paranoia.toml`](#paranoiatoml); override per call to
tighten it for a specific surface.

### `already_raised` — what not to repeat

One-line, `file:line`-cited claims you have already accepted from earlier rounds.
The reviewer is told not to restate them and to hunt for what they missed. Pass
the claim and its citation, never the previous reviewer's prose.

```json
"already_raised": [
  "withdraw() ignores pending holds — accounts.py:88",
  "the overdraft test asserts the fee, not the balance — test_accounts.py:210"
]
```

### `class_closure` — tracking defect *classes* across rounds

**On by default.** A finding is usually an instance of a class: one violated
invariant, several sites. Class closure makes the class itself a tracked object
that survives the round.

Tracked staged plan and branch reviews return provider-constrained semantic JSON. The model emits
each source mapping, classification, debt outcome, and independent class action once. Correction and
final also emit their class outcomes; census outcomes are derived from the validated integrity
manifest. The server validates the graph, allocates new debt IDs, derives the internal mirror rows, and applies
class operations through the same durable class engine used by the legacy terminal register.
Decision-level finding IDs are response-local references: if a cold response reuses a historical
finding ID it was not shown, the server deterministically rekeys that fresh finding and all of its
coverage/class references before materialization, retaining the rename in the audit settlement.
Durable history updates remain keyed only by supplied debt IDs. Duplicate response-local IDs and
unknown or misbound references still reject the decision. Every
governing finding must explicitly declare whether it is a genuine one-off, a new reusable class,
or an occurrence of an active class. Every embedded new-class definition is bound to exactly one
finding; omission or an unbound definition rejects the settlement instead of silently treating its
finding as classless. Every lane finding must be named by at least one checklist
row; a `finding` row names its finding IDs and non-finding rows cannot hide one. The integrity lane
receives each active class's invariant and its procedure or mechanized predicate, not only an ID.
If one atomic lane finding violates several active classes, census consolidation may map that source
finding to one distinct governing finding per class. The source observation is not artificially
split: every target of a repeated source must be an existing-class finding backed by its own
violated assessment citing that source. One-off or new-class targets, duplicate source-to-governing
pairs, and omitted sources still reject the settlement.
An open, unmechanized active class assessed `satisfied` closes deterministically; the model does not
need to repeat that derived action. Mechanized classes retain
their separate mechanical closure rule. Rejections after parsing are recorded as
`validation-invalid`, which covers both envelope/schema and semantic lifecycle failures.
Only terminal consolidation validation populates `validation_debt`; lane/follow-up validation and
execution, retry, timeout, cancellation, deadline, and consolidation-preflight failures persist as
structured `staged_failure` records with their exact role, kind, and message. They invalidate any
older census cache and cannot authorize reuse. Engine outcomes retain `timeout`, `unavailable`,
`provider`, or `execution` rather than being flattened into an exit-code label; a failed validation
retry and its attempt-ledger event use the same `*-validation-retry` role.
Terminal validation debt retains that same structured role, kind, and message in lineage state and
the convergence trailer. Terminal staged validation rejection also persists each rejected extracted
model reply as a bounded head-and-tail excerpt plus its full SHA-256 in lineage state and the audit
log's top-level `rejected_payloads`; provider-envelope excerpts in `attempt_ledger` remain separate.
Validation retry guidance includes the bounded server validation issue with a JSON Pointer, while
the provider schema remains the structural source of truth. The server does not normalize aliases,
fences, markers, partial objects, unresolved anchors, or missing semantic decisions.
Concurrent lane failure fan-in retains replies from every failed lane in attempt-sequence order,
and diagnostics are attached to the closure before lineage persistence so a save failure cannot
erase them from the still-available branch or plan audit log.
Rejected extracted-reply digests use UTF-8 `surrogatepass`, making diagnostic capture total for
unpaired surrogates that a provider's JSON string can legally decode; structural state digests keep
their existing encoding contract.
For tracked plans, the reviewer sees immutable `NNNNN: ` display prefixes derived from the same
`splitlines()` collection that supplies anchor bounds. Those prefixes are presentation metadata;
the unnumbered original remains the sole input to plan/claim digests and persistence.
Repository evidence anchors must resolve to ordinary files inside the exact inert snapshot. The
Codex's server-created `repository/` alias is resolved only to that server-owned snapshot root;
repository symlinks remain invalid. Disabling plan claim verification makes retained claim state
dormant for that run: it is neither rendered nor gating, and is preserved for a later enabled run.
If stakes change while claims are disabled, the packets remain intact and the lineage records that
the next enabled claim phase must exhaustively reverify them under the new stakes.
The terminal register below remains the compatible contract for one-shot and injected-engine reviews:

```
=== CLASS REGISTER ===
CLASS: every public writer must validate its input before the first mutation
SEVERITY: MAJOR
PATTERN: def (create|update)_[a-z_]+\(.*\):\n(?!.*validate)
PATHSPEC: src/
```

The server then, on every applicable snapshot:

- **re-runs each registered regex itself** against the reviewed snapshot
  (`git grep`), and lists every surviving match to the next reviewer;
- **refuses to report the loop unblocked** while any `BLOCKER`/`MAJOR`/`FATAL`
  class still matches;
- **computes the verdict in Python** and appends it as the `CONVERGENCE:` trailer.

A class closes when its predicate returns zero matches and reopens the moment it
matches again. `MINOR` and `OUT-OF-SCOPE` classes are tracked but advisory — they
never block.

Staged census settlements preserve that distinction: exactly one concrete debt
record is required for every blocking governing finding and for every governing
finding cited by a violated class assessment, including advisory assessments.
Advisory debt remains durable review context but is excluded from phase gating and
the computed blocking-debt count.

Where no regex can express the invariant, the reviewer registers a `PROCEDURE:`
instead. Those are **unmechanized**: nothing re-runs them, they are shown to every
later reviewer, and they close only when a reviewer explicitly writes
`CLOSED: <class-id>`.

**On `critique_plan`, every class is unmechanized** — a regex over prose closes as
soon as the wording changes, so predicates are not accepted there at all. Plan
closure gives you *non-forgetting plus explicit closure*, not automatic recurrence
detection.

**Class transitions** a reviewer can emit, besides a new class:

| Record | Effect |
|---|---|
| `CLOSED: <id>` | An unmechanized class is judged closed |
| `REOPEN: <id>` | A closed unmechanized class is violated again |
| `RECLASSIFY: <id> <severity>` | Correct a severity |
| `SUPERSEDE: <id>` + `BY:` / `WITH-PATTERN:` / `WITH-PROCEDURE:` | Replace a class on the legacy text path |
| staged `replace` | Atomically retire a predecessor and create its corrected open successor |

You cannot emit these yourself — ask for them in `focus`, e.g. *"class 3f2a91c4 is
registered MAJOR but its effect is cosmetic; reclassify it if you agree."*

### Plan claim verification — evidence before critique

`critique_plan` verifies external premises **by default**, before structural review. It uses
the selected signed-in reviewer CLI's built-in search **only to discover candidate URLs**.
Paranoia Local then downloads those public HTTP(S) pages itself, extracts main text with
Trafilatura, and resumes the same reviewer session with web access disabled to bind exact
passages. A separate cold, tool-free attester must accept both publisher authority and passage
entailment before a packet can close a claim. Claude `WebFetch` is never enabled or trusted in
this path. There is no `PARANOIA_SEARCH_ENDPOINT`, API key, plugin, or caller-supplied search
adapter.
Redirect destinations govern URL eligibility, UGC/self-source classification, packet identity,
and the persisted source URL; a benign discovery URL cannot launder an ineligible destination.
Persisted claim provenance includes the captured-text digest and cold authority/entailment
decisions, so legacy unattested support is researched once before freezing.

The register is mechanically limited to load-bearing external propositions in three kinds:

- `fact` — objective external-world state, event, quantity, identity, or history;
- `design_principle` — a requirement, constraint, or recommended principle issued by the
  external standard, regulator, protocol, platform, or vendor governing the plan;
- `behavior` — behavior promised by an external API, dependency, platform, protocol, service,
  or runtime on which the plan relies.

All use `scope: "external"`. Repository state, code paths, internal history, implementation
conformance, and internal function bridges are excluded from this register and remain the job
of ordinary structural/code review and tests. Local decisions and project-authored preferences
do not become external claims just because they are called “design principles.” Legacy
repository claims are mechanically retired and stop consuming active inventory or prompts.
Fresh model output mislabeled `repository` is rejected into bounded correction/debt rather than
silently discarded, because it could actually be an eligible external premise.

External claims close only when an exact passage reproduced from Paranoia's server-captured
page is accepted by the cold attester as both authoritative and entailing the exact proposition.
Provider summaries, search snippets, and provider-fetched page text are not evidence.
First-party documentation, standards,
statutes/regulators, government data, original papers/datasets, and the relevant
entity's records are preferred. Secondary material can corroborate or locate a
source. Reddit, Stack Overflow, forums, social media, wikis, blogs, and other UGC
can expose leads or conflicts, but the server prevents known UGC hosts from being
treated as governing evidence even if the model labels them `primary`.
Only canonical HTTP(S) web locations with a host can govern a verdict; repository,
file, and custom-scheme locations remain context only. A repository plan's own canonical
blob/raw HTTP(S) URL is also context, never evidence for its own assertions.

Every contradicted or unresolved external claim returns an **actionable source packet**:

- the verbatim plan wording and atomic proposition;
- the canonical web URL and precise section/table/page;
- publisher and authority class;
- the exact supporting/refuting passage;
- an evidence-entailed replacement when one is actually proven.

Evidence that refutes old wording does **not** prove replacement wording. When no
authoritative passage entails a replacement, the packet explicitly says to remove,
weaken, or research the assertion instead of inventing a correction.
If a reviewer nevertheless proposes unsupported replacement text, the server drops
that optional text and retains the valid verdict and evidence packet; the cold attester
judges the exact replacement separately from the refuted proposition. It does not
discard the rest of the claim batch.
Likewise, evidence that does not entail the model's `supported`/`refuted` verdict is retained
only as context and that individual claim is forced to blocking `unverified`. One bad packet
does not invalidate the rest of the audit.
Other valid claims in the same response are still registered.
If an indexed captured-text binding response omits an expected source key, the server materializes
that omission as a distinct conservative outcome: its source becomes context and any claim left
without qualifying evidence is forced to blocking `unverified`, with provenance that the binding
row was omitted. A returned `usable:false` row instead records that the model explicitly marked the
captured source unusable when a capture exists; if the server capture itself failed, the durable
context records that server-owned failure reason instead. Valid rows in the same batch survive.
Non-integer, unknown, or duplicate keys, malformed rows, unavailable captures claimed as usable,
and passages absent from the capture still reject the batch and receive the bounded same-session
correction.
Cold-attestation rows apply the same exact-integer identity rule before key construction; Boolean,
float, string, null, array, and object aliases cannot bind authority or entailment to another claim.
If the bounded correction retry still contains an unbindable anchor, that item is
recorded as explicit blocking audit debt while the retry's valid claims and valid
removal dispositions are persisted. The next round therefore repairs one item
instead of researching the whole inventory again.
Likewise, a missing retained ID is detected before capture, rejects the initial discovery, and is
named on the same search-capable correction retry. Only the corrected complete inventory is
downloaded and bound. If the
final retry still omits it, valid corrected packets are applied and only that retained claim
is carried forward as blocking `unverified`; one omission does not invalidate the edit cone.

#### Fully autonomous correction loop

The spawned paranoia reviewer is deliberately read-only. “Autonomous” means the
calling coding agent performs the edit/rerun loop without waiting for a human:

1. call `critique_plan` with a stable `lineage`, explicit `stakes`, and `round: 1`;
2. validate each blocking packet, then edit `plan_path` (or the source that produced
   `plan_text`) using only a proven replacement or a justified removal/qualification;
3. increment `round` and call again **after the edit**;
4. after exhaustive round 1, the server freezes every exact unchanged supported claim with
   its authoritative packet. The claim verifier receives only edited/new eligible external
   wording plus retained refuted or unverified claims.
   Freeze identity includes the assertion-bearing Markdown block, structured heading levels,
   and list-parent chain, so quoting, negating, moving into code, changing list ownership, or
   relocating old words cannot preserve stale support;
   Unverified, refuted, or otherwise non-freezable claims require complete current evidence
   packets on the next targeted round; compact verdict-only assessments cannot cross the
   server-capture boundary. Settled claims
   cause no model call or web search. Edited claims inherit no verdict;
5. repeat until the single computed trailer
   says `CONVERGENCE: NOT-BLOCKED`.

Claim targeting changes only the external-evidence phase. Structural review runs a complete cold
three-lane census for a new lineage/cleared snapshot, targeted correction against its durable debt,
then one complete cold final regression. The full plan, repository, active claim register, and
class lineage remain available throughout.
The structural reviewer can still find architectural and repository blockers, but it is told
not to manufacture evidence-register claims for repository mechanics or missing atomic bridges.

Do not rerun unchanged text expecting reviewer variance to fix a claim. Do not ask a
human to translate evidence the packet already makes actionable. A human may inspect
or override the process, but is not required for ordinary convergence.

A later audit cannot clear a prior claim by omitting it or attaching its ID to edited text.
Exact propositions alone retain identity. Otherwise the old external anchor must actually
leave the plan and receive an explicit `removed` disposition; there is no model-only
`nonfactual` escape. To make that closure efficient, the server lists every prior anchor
that is absent from the current plan as a removal candidate in both the initial audit and
its correction retry. The reviewer must still confirm an explicit `removed` disposition;
absence is never an automatic retirement. The old packet remains active as `unverified`
until then. The cold structural reviewer receives the complete evidence for every
supported claim and every current-round disposition, so model-supplied authority and
entailment labels are independently checked before the combined gate can clear.
One plan audit may contain up to 500 claims and 20 evidence rows per claim as schema-corruption
guards, but its composed execution budget is deliberately narrower: at most 200 source captures
and five 400,000-character binding batches. Exceeding an aggregate budget becomes visible
blocking debt; the server never starts a multiplicative hours-long tail or truncates it into
false closure.
The complete evidence phase also has a 6,000-second monotonic deadline and nine model calls
maximum. That fits discovery, five maximum-size binding batches, cold attestation, and one
correction in both discovery and binding. The full verified plan call is bounded to 7,080 seconds.
Evidence state is persisted first. A staged census starts only when its full 4,320-second
lane/consolidation/retry reserve still fits; correction and final use a 3,120-second reserve. If the
reserve no longer fits, the result is visibly pending and the next round reuses frozen supported
claims instead of repeating research. Individual structural calls use 1,800/1,200/2,400 and
600-second role limits. A legacy class-register correction has its own 600-second cap under the
same deadline.
The disposition parser consumes the claim ID, `removed` token, and reason while ignoring
harmless extra model metadata; required fields, unambiguous aliases, and transition validity
remain strict. Both governing coverage arrays remain required even when empty, and malformed
required values receive the normal bounded correction attempt rather than escaping the audit
failure path.

On upgrade, active rows from the replaced versionless claim-array schema become explicit
blocking migration debt and force one exhaustive external audit; they are never interpreted as
an empty verified register. Empty legacy inventory migrates without work. This is separate from
version-1 repository rows, which are known mechanically out of scope and retire from inventory.

When unresolved old wording is still present, it is not rediscovered from scratch. The server
supplies its exact ID, anchor, proposition, and retained packet as a mandatory targeted
checklist. A missing unresolved ID makes the response invalid and triggers the one bounded
correction request before state is committed. Exact unchanged supported IDs are server-frozen
outside that prompt. A malformed targeted audit records blocking debt but does not invalidate
those settled packets, so one edited assertion cannot turn hundreds of supported claims back
into research work.

### `lineage` — which loop this round belongs to

Class state lives in `~/.paranoia/lineages/<lineage>.json`.

- `critique_branch` derives the key from repo + `base_ref` + reviewed branch. Pass
  `lineage` explicitly when the reviewed ref is **not** a branch (a detached HEAD
  or a raw commit), where there is no stable key to derive.
- `critique_plan` **always requires** an explicit `lineage` — a plan has no branch,
  and nothing is derived from its text or path.

The key is used verbatim as the state filename with no namespacing, so make it
globally unique and mode-qualified: `myproject-42-plan` for a plan seam,
`myproject-42-branch` for the branch seam of the same work. A key already used by
the other tool is refused rather than merged.

### When to stop

The stop condition is **two-part**:

1. the computed trailer reads `CONVERGENCE: NOT-BLOCKED` (all active external claims
   supported and no blocking class open), **and**
2. the round returns `CONVERGED`, or only `[MINOR]`/`[OUT-OF-SCOPE]` items.

When the two disagree, **the trailer governs** — and says so in its own output.

### One-shot reviews

For a review with no loop behind it — a design sketch, a quick second opinion —
pass `class_closure: false`. That is the single escape, and it also drops the
`round` and `lineage` requirements.

For plan reviews, one-shot mode still performs default external-claim verification and returns
source packets, but emits **no computed `CONVERGENCE:` line**. Without a parsed class
register the server cannot incorporate the structural review's free-text FATAL/MAJOR
findings into a mechanical clearance. Use the default tracked mode for convergence.

```json
{ "repo_path": "/path/to/repo", "plan_text": "…", "class_closure": false }
```

### Handling a false positive

When a registered regex matches a line that does not actually violate the
invariant, exempt that exact line:

```json
"exempt": [{
  "class_id": "3f2a91c4",
  "path": "src/app.py",
  "line": 17,
  "line_text": "    legacy_open(state)"
}]
```

`line_text` must be byte-exact including indentation. The exemption is keyed on it
and goes void the moment that line changes, so the match resurfaces. Every
exemption is shown to every later reviewer, with the invariant attached, so it can
be challenged; `unexempt` takes the same `class_id`/`path`/`line` and revokes one.

A match inside a binary blob cannot be exempted — narrow the class's `PATHSPEC`
instead.

---

## Tool reference

Arguments marked **required** are enforced; everything else has the default shown.

### `critique_branch`

Adversarial review of a git branch, a committed range, or the dirty working tree.
Returns a [five-section critique](#review-output) plus a
[`CONVERGENCE:` trailer](#class-closure-trailer).

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | **required** | Absolute path to the git repo |
| `base_ref` | string | `main` | Base ref for the diff |
| `head_ref` | string | `HEAD` | Head ref to review |
| `round` | integer | **required** unless `class_closure: false` | 1-based round number; must be an integer ≥ 1 |
| `include_uncommitted` | boolean | `false` | Review the dirty working tree vs HEAD instead of a committed range. Runs in the live repo, not a worktree |
| `isolate` | boolean | `true` | Review inside a throwaway worktree of `head_ref`. Ignored for uncommitted reviews |
| `converge` | boolean | `true` | Pre-gather a bounded deterministic diff/file packet and materialize an immutable snapshot for tracked broad review. Always materializes, overriding `isolate` |
| `max_packet_chars` | integer | `400000` | Character budget for that packet. `already_raised` is always preserved; only file evidence is trimmed |
| `class_closure` | boolean | `true` | Track defect classes across rounds. `false` is the one-shot mode |
| `lineage` | string | derived | Explicit class-closure key. Required when the reviewed ref is not a branch |
| `exempt` / `unexempt` | array | — | Mark or revoke false positives of a class's regex — see [above](#handling-a-false-positive) |
| `stakes` | string | — | The scope boundary |
| `already_raised` | array | `[]` | Claims already accepted from prior rounds |
| `project_summary` | string | — | Neutral factual description of the project. The reviewer tests the diff against it |
| `diff_intent` | string | — | What the diff is *supposed* to achieve. Treated as a claim to verify, never a fact to accept |
| `focus` | string | — | Narrow the review to a specific concern |
| `engine`, `model`, `effort`, `web_search` | — | see [Common arguments](#common-arguments) | |

`converge: false` falls back to a legacy in-place review that has no class closure,
so it must be paired with `class_closure: false`.

### `critique_plan`

Adversarial review of a plan or design document. The reviewer reads the real code
to test every premise the plan makes about current behaviour. Returns the same
five sections, tagged `[FATAL]`/`[MAJOR]`/`[MINOR]`/`[OUT-OF-SCOPE]`.

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | **required** | The repo the plan concerns |
| `plan_text` | string | **one of these two** | The plan as markdown |
| `plan_path` | string | **one of these two** | Absolute path to a markdown plan file |
| `round` | integer | **required** unless `class_closure: false` | 1-based round number |
| `lineage` | string | **required** unless `class_closure: false` | Globally unique, mode-qualified key. Nothing is derived |
| `class_closure` | boolean | `true` | Unmechanized classes only. `false` is the one-shot mode |
| `claim_verification` | boolean | `true` | Verify load-bearing external facts, externally issued design principles, and promised external behaviors with authoritative built-in web evidence before structural review. Set `false` only for an explicit legacy structural-only review |
| `context` | string | — | Background the reviewer needs to judge the plan fairly |
| `focus` | string | — | Narrow the review to a specific concern |
| `stakes` | string | — | The scope boundary |
| `already_raised` | array | `[]` | Claims already accepted from prior rounds |
| `engine`, `model`, `effort`, `web_search` | — | see [Common arguments](#common-arguments) | `web_search: false` is rejected while claim verification is enabled |

`class_closure` and `lineage` are **call arguments only** here — `.paranoia.toml`
is not consulted for either.

### `query`

One question, one answer. Not a full review: no five-section scaffold, lower
reasoning effort by default. The reviewer reads the repo (when given one) and
returns a direct answer, citations, and a stated confidence level.

| Argument | Type | Default | Description |
|---|---|---|---|
| `question` | string | **required** | The specific question to double-check |
| `repo_path` | string | — | Repo to ground the answer in |
| `files` | array | `[]` | `{path, reason?}` hints to look at first — hints, not a payload; it can read anything |
| `focus` | string | — | Extra framing for the question |
| `engine`, `model`, `effort`, `web_search` | — | `effort` defaults to `medium` | |

### `rebut`

Dispute one finding from a review. Resumes **that same reviewer session** with your
counter-evidence, so it is cheaper and higher-resolution than a fresh round. The
reviewer replies `CONCEDE` or `HOLD` with fresh citations.

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | **required** | Same repo the review ran against |
| `session_ref` | string | **required** | From the prior review's footer |
| `rebuttal` | string | **required** | Your counter-evidence |
| `engine`, `model`, `effort`, `web_search` | — | see [Common arguments](#common-arguments) | |

### `arbitrate`

Decides between 2–4 options. Both frontier vendors judge independently and cold
over one pinned snapshot, and Python computes the verdict.

```json
{
  "repo_path": "/Users/you/Work/my-project",
  "decision": "Choose the numeric type for the position-size threshold.",
  "options": [
    {"id": "opt-float",   "statement": "Store it as a float."},
    {"id": "opt-decimal", "statement": "Store it as a Decimal."}
  ],
  "stakes": "Internal CLI, single team, threshold used only in a log line.",
  "files": [{"path": "scripts/lib/registry.py", "reason": "the writer"}]
}
```

What it does, in order:

1. **Pins one snapshot.** Each decider gets its own inert materialization of the same raw Git
   tree and bounded metadata history. Git filters, hooks, textconv, executable bits, symlinks,
   gitlinks, and lazy-fetch helpers are never executed as part of evidence presentation.
   Initialized submodules contribute their currently checked-out commit; uninitialized
   submodules retain the pinned superproject gitlink.
   Every Git evidence read—including citation resolution, label scans, refs, trees, symlinks,
   and blobs—uses the shared inert launcher with lazy fetching disabled, so a missing promised
   object cannot execute a repository-configured transport.
   Git refs and the reflog are digested before and after. Movement while the snapshot
   is being built fails before model spend; later movement is reported as
   `REFS-MOVED: yes` provenance and cannot change the inert views the deciders saw.
2. **Neutralizes the framing** with an Opus agent — advocacy stripped, options
   equalized in detail — then has the *other* vendor attest that field by field.
   `stakes` and caller `context` are passed through verbatim, never rewritten.
   Stakes are server-owned read-only cleaner input and are not part of the cleaner's
   output schema; undeclared cleaner output blocks are rejected.
   The attester separately rejects advocacy in either caller-owned field.
3. **Researches shared external premises by default.** Codex live search and Claude
   `WebSearch` independently discover candidate URLs in parallel. The server downloads and
   extracts them with Trafilatura; the same sessions bind exact passages with browsing disabled.
   Claude `WebFetch` is not enabled. Python deterministically unions the results, hard-demotes
   known UGC hosts, rejects caller IDs anywhere in the complete rendered packet, and sends
   byte-identical packets to both deciders.
4. **Counterbalances presentation.** One decider sees canonical order, the other
   reversed, under opaque per-decider labels. Neither is told the other exists.
5. **Computes the verdict.** No model adjudicates the adjudication. A decisive external
   reference must name a captured packet and explicitly pass publisher-authority,
   passage-entailment, and decision-relevance checks.
6. **On divergence**, runs one reconciliation round carrying only `path:line`
   citations and bytes the server itself read — never the other model's prose —
   and only when there is genuinely novel evidence.

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | **required** | Repository context to pin; decisive evidence may be a repository citation or captured source packet |
| `decision` | string | **required** | What is being decided (max 2500 chars) — not the evidence for it |
| `options` | array | **required** | 2–4 mutually exclusive `{id, statement}`. Array order is irrelevant; canonical order is derived by sorting ids |
| `stakes` | string | **required** | Pass `"unstated"` to accept a fixed default reading |
| `context` | string | — | Shared facts and the full specification of whatever only one option adopts (max 20000 chars) |
| `files` | array | `[]` | `{path, reason?}` starting points. Both deciders see the same list |
| `subject` | string | — | Short label for the paste-ready record block |
| `clean` | boolean | `true` | Run the cleaner and its cross-vendor attestation |
| `models` | object | — | `{codex?, claude?}` per-vendor overrides |
| `cleaner_model` | string | `claude-opus-5` | Override the cleaner model |
| `order_seed` | string | — | Replay a previous run's `ORDER-SEED` to reproduce its labels and ordering |
| `retain_snapshot` | boolean | `false` | Create `refs/paranoia/arbitrate/<stamp>` so evidence survives `git gc` |
| `research` | boolean | `true` | Run bounded shared external research. Set `false` only for an explicit repository-only decision; both deciders then run with web disabled |
| `effort`, `web_search` | — | see [Common arguments](#common-arguments) | |

`research: true` requires `web_search: true`; the incompatible combination is rejected before
any model call. `web_search` authorizes only the isolated discovery roles. Binding and every
decider call run with web disabled, and other evidence roles retain their narrower tool surface.
Claude evidence roles use matching
availability and permission allowlists on fresh and resumed calls; denial of a tool required by
the active role is a visible provider-capability failure, never an empty-search success. Binding
and text roles use explicit empty allowlists. Only server-captured packets can affect substantiation.
Evidence roles require Codex CLI 0.144.6 or later and Claude Code 2.1.197 or later. Newer versions
are accepted; compatibility is then checked by the real call, so unsupported flags or tools,
permission denial, missing structured output, and malformed provider envelopes remain visible
blocking failures.
Signed-in structured probes and complete verified-plan lifecycles on later Claude and Codex
releases are recorded in
[`docs/minimum_provider_cli_acceptance_2026-08-16.json`](docs/minimum_provider_cli_acceptance_2026-08-16.json).
The signed-in end-to-end record, including exact versions, packet digest, source references,
plan-claim closure, repository-only closure, and defects found by the first real runs, is
[`docs/evidence_capture_acceptance_2026-08-10.json`](docs/evidence_capture_acceptance_2026-08-10.json).

**`arbitrate` has no `engine` or `model`** — it drives both vendors, so a single
override could only degrade it to one of them or send one vendor's model name to
the other CLI.

**Input bounds**, checked before anything is spent:

| Bound | Limit |
|---|---|
| option statement | 1200 chars |
| longest ÷ shortest option | 2.0 |
| `decision` | 2500 chars |
| `context` | 20000 chars |

The shape that passes these naturally: put every shared fact, and the full
specification of whatever only one option adopts, into `context` — prefaced as
"the rules under consideration, if adopted". Leave each option statement to say
only how much of it is adopted and what follows. ~800 chars each is typical.

**Behaviour worth knowing before you rely on it:**

- **It decides only from pinned evidence.** A converging vote must cite either a repository
  line that resolves or a governing server-captured `SOURCE:<packet-id>`. Provider summaries,
  unknown packet IDs, and live decider browsing cannot substantiate convergence. Repository
  citations resolve only against regular-file bytes exposed in the inert snapshot; historical
  blobs and symlink-path referents are rejected because the reviewer did not receive those bytes.
- **`ADVISORY` does not block.** Each decider reports whether it judges that a
  named human owner should be authorizing the decision. That is reported, never
  gated: `CONVERGED` with `ADVISORY: human-owner` is still `CONVERGED`. Enforcing
  it is your policy.
- **`SNAPSHOT` is provenance, not a replay handle.** The snapshot commit is
  unreferenced and `git gc` reclaims it. The audit log holds both prompts, both
  replies, and the carried evidence. `retain_snapshot: true` pins it behind a ref.
- **`REFS-MOVED` is provenance after snapshot setup.** Deciders receive no live Git
  directory: each sees a separate inert tree and bounded history rendered from
  `SNAPSHOT`. A later branch advance therefore does not invalidate their votes. If
  the initial or final ref/reflog observation fails, the run reports
  `REFS-MOVED: unavailable` and records null digests plus the structured error; it
  never aliases unavailable provenance to `no`.
- **Research failures keep the state already established.** Their trailer and audit
  retain the real snapshot, order seed, cleaning/attestation result, final ref digest,
  completed peer research, bounded attempt replies, accepted discovery/capture
  artifacts, bindings, sessions, usage, durations, and the engine or parser diagnostic.
  Raw provider envelopes are stored as SHA-256 plus bounded excerpts. Structured
  provider failure detail and process stderr remain distinct. Shared packet-union
  and reserved-token failures use the same stateful path. If the durable audit sink
  fails, the response includes a bounded, hashed fallback record containing the
  accumulated attempts and accepted artifacts before the machine trailer.
- **Captured claim-binding debt preserves all engine diagnostic channels.** Initial
  and correction binding failures hash and bound provider stdout, structured failure
  detail, and process stderr separately, so timeout and unavailable-executable debt
  remains actionable even when the provider emitted no stdout.
- **Every ordinary failure after snapshot setup uses that stateful path.** Cleaner,
  attester, budget, label, evidence-resolution, and decision-setup failures therefore
  cannot fall back to `SNAPSHOT: none` or erase cleaner/attester attempts, completed
  research, label maps, decider prompts/replies/votes, or carried evidence.
  Round-two carried bytes are recorded before either second-round call starts, and
  even an initial execution failure retains the exact prompt as an attempt.
  Failed staged attempts and their durable failure record retain return code, raw provider
  stdout, structured failure detail, and process stderr as distinct bounded, hashed channels.
  Once shared research completes, later failures retain the normalized packet bytes
  and real `RESEARCH-DIGEST` as well as the per-lane ledger.
  The packet becomes established immediately after normalization/rendering, so a
  subsequent reserved-token rejection audits the exact rejected bytes and digest.
- **Research attempts start before provider invocation.** The ledger binds phase,
  intended session, and bounded prompt/digest before `run` or `resume`; a thrown
  provider exception therefore counts as the attempted call and retains its binding.
  Immediately before every discovery/binding invocation or validation resume, the
  handler admits that attempt's full cap against the remaining monotonic whole-run
  deadline; a refused call retains the already-established lane attempts. Research
  JSON accepts markdown fencing and one measured terminal truncation only: a complete
  outer object missing its final `}`. Internal or multi-character JSON damage remains
  invalid and receives the one same-session correction before failing closed.
- **Attempt state distinguishes preparation from spend.** Cleaner, attester,
  research, and decider records expose whether a prompt was prepared, admitted,
  invoked, completed, refused by the deadline, or blocked during inert-workspace
  setup. Call counts include only attempts that crossed the provider boundary.
- **Cleaned packet audits are complete.** Success and late-failure records retain
  cleaned decision, context, hints, and statements plus one digest of that exact
  normalized packet. Cleaner and attester reply copies retain complete normal
  protocol outputs up to a 32,000-character circuit breaker and always carry full-reply
  digests. The cleaner's context copy is non-authoritative: the server always
  restores the caller's exact context, including leading and trailing whitespace,
  before attestation and voting. A changed fidelity verdict must name each field,
  quote the original and cleaned passages, classify the semantic change with the
  closed enum, and use the exact `<field>: <change>` reason label. The enum and bound
  passages are the enforceable explanation; free-form semantic heuristics are not used. Valid option arrays are
  audited as the same ID-to-statement mapping on success and every failure path.
  Signed-in reproductions are recorded in
  [`docs/cleaning_attestation_acceptance_2026-08-13.json`](docs/cleaning_attestation_acceptance_2026-08-13.json).
  They prove that exact caller context and normalized options reached both deciders and
  that the recorded cleaning lifecycle and production results are reproducible. The
  positive run records a unanimous production result but does not independently attest
  that its resolved repository citation entails either constraint. The original run
  records ordinary decider selection divergence; it does not claim to exercise the
  agreed-but-unsubstantiated fail-closed path.
- **Cleaner and attester attempts use the same before-call discipline.** Provider
  exceptions retain prompt bindings. Research becomes `running` only after deadline
  admission, and packet digesting remains total on model-controlled Unicode.
- **On divergence, only a decider that *moved* must ground in the carried
  evidence.** One that held its round-1 position needs only a citation that
  resolves — provided its round-1 decisive citation resolved too. A holder that
  was never substantiated must ground in gained evidence like a mover.
- **Bias is reduced, not eliminated.** Order counterbalancing equalizes mean rank
  but not higher moments for 3–4 options; attestation is a model's judgement, not
  a proof; and a `files` list pointing only at evidence favouring one option biases
  both deciders identically. `docs/arbitration_plan.md` §2 enumerates the residuals.

### Common arguments

Accepted by the four review tools:

| Argument | Values | Default |
|---|---|---|
| `engine` | `codex` \| `claude` | the server's configured engine |
| `model` | any model name | the engine's strongest: `gpt-5.6-sol` / `claude-fable-5` |
| `effort` | `low` \| `medium` \| `high` | `high` (`query`: `medium`) |
| `web_search` | boolean | `true` |

---

## Output reference

### Review output

Every review returns exactly five headings, in this order. One-shot reviews populate their natural
categories; tracked staged plan and branch reviews put governing findings in `What doesn't work`,
bounded remedies in `Improvements`, and write `Nothing notable.` in categories the settlement does
not represent.

| Section | Contains |
|---|---|
| `## What works` | Specific correct decisions, cited. "Nothing notable." when there are none |
| `## What doesn't work` | Actual defects: quoted lines, failure mechanism, observable symptom. Worst first |
| `## Risks` | Failure modes the author didn't consider that the code is exposed to |
| `## Gaps` | What the change should do to reach its stated intent but doesn't |
| `## Improvements` | Concrete changes that alter the outcome under the stated stakes |

Every item in the last four sections carries exactly one severity tag:

| Code review | Plan review | Meaning |
|---|---|---|
| `[BLOCKER]` | `[FATAL]` | Ships a bug / kills the plan as written |
| `[MAJOR]` | `[MAJOR]` | Fix before merge / before execution |
| `[MINOR]` | `[MINOR]` | Fix opportunistically |
| `[OUT-OF-SCOPE]` | `[OUT-OF-SCOPE]` | Real, but beyond the stated stakes — file separately |

A finding that recurs from a tracked class is marked `[RECURRENCE <class-id>]`
next to its severity tag.

The footer carries the `session_ref` for [`rebut`](#rebut).

### Tracked convergence trailer

Appended below a staged tracked plan or branch review:

```
CLASS-REGISTER: staged census parsed — NEW 19ef00ab
CLASS-CLOSURE: 1 open, 0 closed
  19ef00ab repeated state transitions preserve their owner (unmechanized: awaiting reviewer CLOSED or RECLASSIFY)
STRUCTURAL-PHASE: correction
STRUCTURAL-DEBT: 2 blocking open
CONVERGENCE: BLOCKED — staged structural debt remains open.
```

| Line | Meaning |
|---|---|
| `CLASS-REGISTER` | The class operations applied by this staged settlement, including canonical IDs minted by the existing class engine |
| `CLASS-CLOSURE` | Open/closed reusable-class counts plus blocking class detail |
| `STRUCTURAL-PHASE: census\|correction\|final\|clear` | The next broad/targeted gate; `final` requires one fresh cold regression |
| `STRUCTURAL-DEBT: N blocking open` | Concrete governing findings still requiring correction |
| `CONVERGENCE: NOT-BLOCKED` | Structural debt/classes and, for plans, external claims are clear |
| `CONVERGENCE: BLOCKED` | The named phase, debt, class, claim, format, or state condition still blocks |
| `STRUCTURAL-ERROR` / `STRUCTURAL-PENDING` | A bounded format/deadline path did not produce a settled review |
| `STATE-UNAVAILABLE` | Lineage state is unreadable, unwritable, or a previous write may not have completed. The message names the absolute path; repair or delete it, then re-run |

`STRUCTURAL-DEBT` counts concrete governing findings only. An unbound live reusable class remains a
first-class blocker in `CLASS-CLOSURE`; it is not duplicated into synthetic finding prose or given
invented evidence anchors. The class trailer lists bounded path/line/text match detail and renders a
binary recurrence as `path: binary match (line not shown)`. In that case the governing line says
class closure remains open.

One-shot, injected-engine, and successfully persisted staged tracked trailers all retain
`CLASS-REGISTER`, `CLASS-CLOSURE`, match, and unmechanized-class detail. If lineage state cannot be
loaded or a write may not have persisted, the staged trailer instead emits `CLASS-REGISTER` plus
`CLASS-CLOSURE: STATE-UNAVAILABLE`; reporting in-memory counts as durable in that case would be
misleading. Staged plan and branch reviews additionally
bind concrete debt to the corresponding canonical class IDs and use one final structural verdict;
the class trailer does not emit a competing convergence line.

`NOT-BLOCKED` asserts only that the computed structural-debt, class, and (for verified plans)
external-claim gates are clear. It is a review result, not a proof that the change is correct.

For verified plan reviews the claim gate and class gate are combined into one
governing verdict:

```
CLAIM-REGISTER: 18 active external claims; 7 retired and excluded from active inventory
CLAIM-CLOSURE: 17 supported, 1 refuted, 0 unverified
ACTIONABLE SOURCE PACKETS:
- CLAIM C-4e2d… — REFUTED
  Plan wording: …
  Atomic proposition: …
  Evidence-entailed replacement: …
  Source 1: [primary/refutes_claim] …
    Location: https://… (Section 4, table 2)
    Exact passage: …
CLASS-CONVERGENCE: NOT-BLOCKED — …
CONVERGENCE: BLOCKED — external claim closure remains open.
```

`CLAIM-AUDIT-DEBT` includes the validator reason, SHA-256, and a bounded rejected
output excerpt. Malformed model JSON, a failed audit/retry, unsupported authority,
or missing entailment blocks; it never becomes an empty successful register.

### `arbitrate` outcomes

| Outcome | Meaning |
|---|---|
| `CONVERGED` | Unanimous, unblocked, and each vote substantiated by a resolved citation |
| `BLOCKED` | They agree on an option and one of them tags it `[MAJOR]`/`[FATAL]` |
| `REFRAME_REQUIRED` | A decider surfaced a better unlisted option. Give it an id and re-run |
| `UNRESOLVED` | Still split, or agreement nobody could substantiate |
| `FAILED` | Preflight, execution, cleaning, parsing, capture, or protocol failure |

The reply ends with a machine-readable trailer whose fields are always present:
`ARBITRATION`, `SELECTED`, `ADVISORY`, `AUTHORITY-POLICY`, `CLEANING`, `SNAPSHOT`,
`ORDER-SEED`, `REFS-MOVED`, `AUDIT`, `ROUNDS`, `RESEARCH`, and `RESEARCH-DIGEST`.

---

## Configuration

### `.paranoia.toml`

Drop one at the repo root so callers stop retyping context. Keys go at the top
level or under `[paranoia]`. Precedence: **call argument > `.paranoia.toml` >
built-in default**.

```toml
project_summary = "A booking API. Python/FastAPI, Postgres. Auth via short-lived JWTs."
base_ref = "develop"
stakes = "Internal booking API, single team, authenticated first-party callers, ~1k req/min."
web_search = true
isolate = true
```

Honoured keys: `base_ref`, `project_summary`, `stakes`, `isolate`, `converge`,
`class_closure`, `max_packet_chars`, `model`, `effort`, `web_search`.

`critique_plan`'s `class_closure` and `lineage` are **not** read from here.

### Command line

```
paranoia-local --engine {codex|claude} [--log-dir DIR]
```

| Flag | Default | Description |
|---|---|---|
| `--engine` | **required** | Which local engine performs reviews — the *other* agent from the caller |
| `--log-dir` | `~/.paranoia/logs` | Audit-log directory |

### State on disk

| Path | Contents |
|---|---|
| `~/.paranoia/logs/` | One JSON audit record per call: engine, model, round, `already_raised`, session ref, timings, and the review text |
| `~/.paranoia/lineages/` | Atomic class + external-claim state, one file per lineage. Retired and mechanically out-of-scope claims are excluded from active prompt inventory |

Lineage state deliberately does **not** follow `--log-dir`, so moving your logs
cannot silently reset a tracked lineage. Set `PARANOIA_STATE_ROOT` to relocate it.

---

## Safety model

- **Role-bounded reviewer.** Ordinary reviews remain read-only. Evidence discovery receives
  only provider search; binding and cold attestation receive no web or repository tools; verified
  plan structure and arbitration voting receive only read access to an inert evidence tree and
  no web. The reviewer cannot edit your code or run your test suite. The separate calling coding
  agent owns autonomous corrections.
- **Reviewer capability is hermetic.** Codex is spawned with `--ignore-user-config`:
  authentication remains available, while registered MCP servers and user-configured tools
  do not. This prevents a reviewer from recursively calling paranoia-local even when repo
  instructions request it; model, reasoning effort, sandbox, and built-in web search are
  supplied explicitly. Claude is spawned
  with `--setting-sources ""`, so it loads no `.claude` settings files — otherwise
  the reviewed repo's `.claude/settings.local.json` and your global settings would
  merge on top of the allowlist, and those routinely grant `Bash(python3:*)` and
  friends. This applies to the spawned reviewer subprocess only; it does not read,
  write, or affect your interactive `claude` sessions. Codex also remains covered by its
  OS-level sandbox, which no repo setting can loosen.
- **Isolated.** Committed reviews run inside a throwaway `git worktree` of the
  target ref, so they never collide with your working tree and can review a branch
  that isn't checked out. Dirty-working-tree reviews necessarily run in the live
  repo, read-only. Verified plan structure and arbitration instead use disposable inert
  materializations, because those paths must not expose repository-selected Git helpers,
  executable bits, symlink traversal, or live Git commands.
- **No API keys, no telemetry.** The server shells out to a CLI you are already
  signed into.
- **Minimal footprint.** In `converge` mode the server creates a short-lived
  worktree and a few unreferenced git objects in the target repo. Both are cleaned
  up on exit and no ref is created. A hard crash can leave the worktree
  registration until the next `git worktree prune` / `git gc`. Your working tree
  and index are never touched. Verified plan and arbitration evidence modes create disposable
  directories plus unreferenced snapshot objects, but no worktree registration.

  **One opt-in exception:** `arbitrate` with `retain_snapshot: true` creates
  `refs/paranoia/arbitrate/<stamp>` so its evidence survives `git gc`. It is the
  only mode in the server that writes a ref. Remove one with
  `git update-ref -d <ref>`.

### Rate limits

Reviews draw on your subscription's agentic-usage pool. A tracked plan cold census is three concurrent
reviewer calls plus consolidation; correction and final are one call each, with at most one bounded
same-session validation correction per call. It covers schema and semantic settlement rejection and
is recorded as `*-validation-retry`. Use `query` for quick checks.

Audit `attempt_ledger` rows enumerate every provider run/resume exactly once. A synchronized
sequence is assigned immediately before each concurrent census run/resume boundary, and the stage
ledger is serialized by that sequence. Duration and session fields remain per-call telemetry.

For `critique_plan`, round 1 pays for the exhaustive external-claim inventory. Later rounds send
only the external edit cone and unresolved claims to the claim verifier; an unchanged plan
whose active claims are all supported makes zero claim-model calls. Structural correction then
targets durable debt instead of paying for another broad novelty search; the cold final remains the
regression gate.

`arbitrate` is the expensive one and the only tool that spends from **both**
subscriptions in a single call. Research is on unless `research: false` explicitly
selects repository-only mode. Both modes validate each decider's exact supported
evidence-isolation CLI profile before snapshot creation or model spend. A
parser-rejected decider reply receives one
complete correction attempt while the sibling result and completed cleaning/research
work are retained. If correction still fails, the audit records both rejected replies,
the completed sibling, and the actual phase provenance; execution failures are not
retried. Every attempt remains subject to the phase cap and 7,200-second whole-call deadline.

---

## Development

Validate a checked-in arbitration acceptance record against its exact durable audit
and current production sources before treating it as release evidence:

```bash
python scripts/validate_arbitration_acceptance.py \
  docs/arbitration_reliability_acceptance_2026-08-12.json .
```

The command fails on stale provider-call counts, packet identities/count/digest,
audit digest, outcome/selection/snapshot, or production hashes.

```bash
pip install -e '.[dev]'
python -m pytest        # unit + integration; integration uses fake CLIs, no quota
python scripts/run_staged_protocol_mutation_checks.py  # bounded Protocol v2 release gate
```

The engine subprocess boundary is dependency-injected, so the whole stack is
unit-tested without spending subscription quota. A separate integration test drives
the real subprocess runner against fake `codex`/`claude` binaries on `PATH`.

Design documents for the two non-obvious subsystems live in
[`docs/`](docs/): [`class_closure_plan.md`](docs/class_closure_plan.md),
[`plan_class_closure_proposal.md`](docs/plan_class_closure_proposal.md), and
[`claim_verification.md`](docs/claim_verification.md), and
[`arbitration_plan.md`](docs/arbitration_plan.md). The proposed simplification of the
staged model contract is specified in
[`staged_review_protocol_v2_plan.md`](docs/staged_review_protocol_v2_plan.md), with
implementation evidence in
[`staged_review_protocol_v2_acceptance.md`](docs/staged_review_protocol_v2_acceptance.md). Its
census-outcome amendment is specified in
[`derive_census_class_outcomes_plan.md`](docs/derive_census_class_outcomes_plan.md).
The latest real Codex verification evidence is recorded in
[`docs/external_claim_acceptance_2026-08-09.json`](docs/external_claim_acceptance_2026-08-09.json).

## License

MIT © 2026 Andrew Hillel
