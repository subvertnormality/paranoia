# paranoia-local

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
- The reviewing agent's CLI, installed and signed in on a subscription:
  [Codex CLI](https://developers.openai.com/codex) (`codex`, ≥ 0.144) **or**
  [Claude Code](https://code.claude.com) (`claude`)
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
tool_timeout_sec = 3600
startup_timeout_sec = 30
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

Each round is a **fresh, cold reviewer** — it has no memory of the last one. You
carry state forward with the arguments below.

### `round` — the severity floor

The 1-based round number. **Increment it every round.** At `round >= 3` the
reviewer reports only merge-blocking findings and withholds `[MINOR]` and
`[OUT-OF-SCOPE]`, writing `CONVERGED` when none remain. This is the lever that
makes a loop *stop* instead of grinding through diminishing findings.

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

The reviewer ends its review with a register block:

```
=== CLASS REGISTER ===
CLASS: every public writer must validate its input before the first mutation
SEVERITY: MAJOR
PATTERN: def (create|update)_[a-z_]+\(.*\):\n(?!.*validate)
PATHSPEC: src/
```

The server then, every round:

- **re-runs each registered regex itself** against the reviewed snapshot
  (`git grep`), and lists every surviving match to the next reviewer;
- **refuses to report the loop unblocked** while any `BLOCKER`/`MAJOR`/`FATAL`
  class still matches;
- **computes the verdict in Python** and appends it as the `CONVERGENCE:` trailer.

A class closes when its predicate returns zero matches and reopens the moment it
matches again. `MINOR` and `OUT-OF-SCOPE` classes are tracked but advisory — they
never block.

Where no regex can express the invariant, the reviewer registers a `PROCEDURE:`
instead. Those are **unmechanized**: nothing re-runs them, they are shown to every
later reviewer, and they close only when a reviewer explicitly writes
`CLOSED: <class-id>`.

**On `critique_plan`, every class is unmechanized** — a regex over prose closes as
soon as the wording changes, so predicates are not accepted there at all. Plan
closure gives you *non-forgetting plus explicit closure*, not automatic recurrence
detection. Its final verdict is also gated by the distinct claim-verification system
below.

**Register transitions** a reviewer can emit, besides a new class:

| Record | Effect |
|---|---|
| `CLOSED: <id>` | An unmechanized class is judged closed |
| `REOPEN: <id>` | A closed unmechanized class is violated again |
| `RECLASSIFY: <id> <severity>` | Correct a severity |
| `SUPERSEDE: <id>` + `BY:` / `WITH-PATTERN:` / `WITH-PROCEDURE:` | Replace a class |

You cannot emit these yourself — ask for them in `focus`, e.g. *"class 3f2a91c4 is
registered MAJOR but its effect is cosmetic; reclassify it if you agree."*

### Plan claim verification — closing load-bearing premises

Closure-enabled `critique_plan` first runs fresh toolless roles that extract factual
premises, request bounded server-owned repository/external evidence, and verify,
contradict, defer, or abstain. Registered claims persist independently of defect classes;
a later reviewer cannot make one disappear by omission.

Every new claim starts unchecked and blocking. A different role must confirm whether it
is a fact or decision. A blocking fact closes only with exact server evidence or a safe
plan deferral whose verification step precedes every dependency, has falsifiable evidence,
and stops on failure. Advisory bearing requires its own evidence-bearing verifier event.
Evidence IDs are bound to one exact claim; another claim cannot reuse them. Truth, dispute,
deferral, and bearing audits and evidence dependencies persist separately. Model agreement
and citations alone do not verify anything. Transitions out of disputed or contradicted
states require the independent audit, and dispute resolution states the exact audited
outcome. Register correction covers semantic transition errors as well as JSON grammar;
correcting a structural register preserves the original five-section critique.

Repository reads are pinned to one exact dirty-tree snapshot. Models see server span IDs,
bounded repository records, and no filesystem path. Plan bytes appear only as ordered,
JSON-escaped span data, including for the structural reviewer. External passages only enter a
command-incapable role; the structural reviewer receives their metadata, not remote bytes.
Unavailable sources cause abstention and remain blocking. The full trust model, register
grammar, evidence limits, caching, and recovery rules are in
[`docs/claim_verification.md`](docs/claim_verification.md).

### `lineage` — which loop this round belongs to

Closure state lives in `~/.paranoia/lineages/<lineage>.json`. Plan lineages use a
versioned envelope containing both class and claim/evidence references.

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

1. the computed trailer reads `CONVERGENCE: NOT-BLOCKED`, **and**
2. the round returns `CONVERGED`, or only `[MINOR]`/`[OUT-OF-SCOPE]` items.

When the two disagree, **the trailer governs** — and says so in its own output.

### One-shot reviews

For a review with no loop behind it — a design sketch, a quick second opinion —
pass `class_closure: false`. That is the single escape, and it also drops the
`round` and `lineage` requirements. On `critique_plan` it also disables claim
verification and is rejected if `claim_verification` is supplied explicitly.

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
| `converge` | boolean | `true` | Pre-gather a deterministic evidence packet (every touched file in full, plus the diff) and review it against an immutable materialized snapshot. Always materializes, overriding `isolate` |
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

Integrated claim verification followed by adversarial review of a plan or design
document. Exact plan bytes and one dirty-tree Git snapshot are pinned; toolless roles
extract load-bearing claims, request bounded server evidence, and verify or abstain before
a separate structural reviewer judges the design. Python combines claim closure and
defect-class closure into one verdict. See [plan claim verification](docs/claim_verification.md).

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | **required** | The repo the plan concerns |
| `plan_text` | string | **one of these two** | The plan as markdown |
| `plan_path` | string | **one of these two** | Absolute path to a markdown plan file |
| `round` | integer | **required** unless `class_closure: false` | 1-based round number |
| `lineage` | string | **required** unless `class_closure: false` | Globally unique, mode-qualified key. Nothing is derived |
| `class_closure` | boolean | `true` | Unmechanized classes only. `false` is the one-shot mode |
| `claim_verification` | `blocking` | `blocking` when closure is on | Integrated claim gate. Rejected with `class_closure: false` |
| `independent_check` | `auto` \| `require` | `auto` | Distinct-vendor evidence audit policy; unavailable required checks stay blocking, including required deferrals |
| `stakes_level` | `low` \| `high` | high for any stated stakes | Explicit authorization-risk policy for `auto`; natural-language stakes are never parsed for opt-down words |
| `supplied_evidence` | array | `[]` | Up to 20 `{claim, source, content}` caller artifacts. The server hashes them; the verifier still decides what they establish |
| `refresh_claims` | boolean | `false` | Bypass an otherwise valid zero-research cache hit for this round |
| `context` | string | — | Background the reviewer needs to judge the plan fairly |
| `focus` | string | — | Narrow the review to a specific concern |
| `stakes` | string | — | The scope boundary |
| `already_raised` | array | `[]` | Claims already accepted from prior rounds |
| `engine`, `model`, `effort`, `web_search` | — | see [Common arguments](#common-arguments) | |

`class_closure` and `lineage` are **call arguments only** here — `.paranoia.toml`
is not consulted for either. The sole legacy one-shot escape is
`class_closure: false`: it performs one ordinary review and emits no lineage state or
`CONVERGENCE`. There is no closure-enabled off/shadow mode.

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

1. **Pins one snapshot.** Each decider gets its own worktree of the same commit.
   Git refs and the reflog are digested before and after; if anything moved, the
   run returns `FAILED` rather than reporting agreement it cannot describe.
2. **Neutralizes the framing** with an Opus agent — advocacy stripped, options
   equalized in detail — then has the *other* vendor attest that field by field.
   `stakes` is passed through verbatim, never rewritten.
3. **Counterbalances presentation.** One decider sees canonical order, the other
   reversed, under opaque per-decider labels. Neither is told the other exists.
4. **Computes the verdict.** No model adjudicates the adjudication.
5. **On divergence**, runs one reconciliation round carrying only `path:line`
   citations and bytes the server itself read — never the other model's prose —
   and only when there is genuinely novel evidence.

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | **required** | Every decisive citation must be repo-verifiable |
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
| `effort`, `web_search` | — | see [Common arguments](#common-arguments) | |

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

- **It only decides what the repository can settle.** A converging vote must cite a
  line that resolves. A decision that does not turn on repo-verifiable grounds
  will never return `CONVERGED`.
- **`ADVISORY` does not block.** Each decider reports whether it judges that a
  named human owner should be authorizing the decision. That is reported, never
  gated: `CONVERGED` with `ADVISORY: human-owner` is still `CONVERGED`. Enforcing
  it is your policy.
- **`SNAPSHOT` is provenance, not a replay handle.** The snapshot commit is
  unreferenced and `git gc` reclaims it. The audit log holds both prompts, both
  replies, and the carried evidence. `retain_snapshot: true` pins it behind a ref.
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

Every review returns exactly five sections, in this order:

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

### Closure trailer

Appended below a branch review whenever class closure ran. A closure-enabled plan review
adds claim lines before the class lines and still emits exactly one convergence verdict:

```
LINEAGE: 9f2c1a4b0e77 (rounds recorded: 8)
CLAIM-REGISTER: parsed 2
CLAIMS: verified=1, unverified=1
CLAIM-CLOSURE: BLOCKED — 1 load-bearing claim(s) unresolved
CLASS-REGISTER: parsed 1
CLASS-CLOSURE: 1 open, 2 closed, 3 unmechanized
CONVERGENCE: BLOCKED — 1 claim(s), 1 class(es)
```

| Line | Meaning |
|---|---|
| `CONVERGENCE: NOT-BLOCKED` | No registered blocking claim or defect class is unclosed. Advisory state may remain |
| `CONVERGENCE: BLOCKED` | Claims, classes, or register/state debt remain; any incompatible reviewer `CONVERGED` is void |
| `CLAIM-CLOSURE: BLOCKED` | A registered load-bearing premise is unresolved, contradicted, stale, disputed, malformed, unchecked, or awaiting required independent authorization |
| `CLASS-REGISTER: NONE` \| `parsed N` \| `malformed: …` | What the reviewer's register block contained |
| `CLASS-CLOSURE-WARNING: … closed in the round it was registered` | The predicate matched nothing at birth — usually too narrow. Ask the next reviewer to `SUPERSEDE` it |
| `BLOCKED — register debt from round N` | Two attempts at a parseable register failed. The next round with a good register clears it |
| `unmechanized: awaiting reviewer CLOSED or RECLASSIFY` | A semantic class no regex can check |
| `STATE-UNAVAILABLE` | Lineage state is unreadable, unwritable, or a previous write may not have completed. The message names the absolute path; repair or delete it, then re-run |

`NOT-BLOCKED` asserts only that neither registered gate is blocking. It never proves
extraction completeness or that the plan is correct — the reviewer's findings still
govern that.

### `arbitrate` outcomes

| Outcome | Meaning |
|---|---|
| `CONVERGED` | Unanimous, unblocked, and each vote substantiated by a resolved citation |
| `BLOCKED` | They agree on an option and one of them tags it `[MAJOR]`/`[FATAL]` |
| `REFRAME_REQUIRED` | A decider surfaced a better unlisted option. Give it an id and re-run |
| `UNRESOLVED` | Still split, or agreement nobody could substantiate |
| `FAILED` | Preflight, cleaning, parsing, or the repo's refs moved mid-run |

The reply ends with a machine-readable trailer whose fields are always present:
`ARBITRATION`, `SELECTED`, `ADVISORY`, `AUTHORITY-POLICY`, `CLEANING`, `SNAPSHOT`,
`ORDER-SEED`, `REFS-MOVED`, `AUDIT`, `ROUNDS`.

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
# Optional server-owned external discovery for critique_plan claim verification.
```

Honoured keys: `base_ref`, `project_summary`, `stakes`, `isolate`, `converge`,
`class_closure`, `max_packet_chars`, `model`, `effort`, and `web_search`.
Set trusted process environment variable `PARANOIA_SEARCH_ENDPOINT` for the plan
claim-verification fetch boundary. A reviewed repository cannot select an outbound host.

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
| `~/.paranoia/lineages/` | Class-closure state, one file per lineage |

Lineage state deliberately does **not** follow `--log-dir`, so moving your logs
cannot silently reset a tracked lineage. Set `PARANOIA_STATE_ROOT` to relocate it.

---

## Safety model

- **Read-only.** Codex runs under its OS sandbox (`--sandbox read-only`); Claude
  runs with a read-only tool allowlist (`Read`, `Grep`, `Glob`, scoped `git`
  reads, web search) and write tools explicitly denied. The reviewer cannot edit
  your code, run your test suite, or reach the network except for opt-in web
  search.
- **The audited repo cannot widen the reviewer.** The Claude engine is spawned
  with `--setting-sources ""`, so it loads no `.claude` settings files — otherwise
  the reviewed repo's `.claude/settings.local.json` and your global settings would
  merge on top of the allowlist, and those routinely grant `Bash(python3:*)` and
  friends. This applies to the spawned reviewer subprocess only; it does not read,
  write, or affect your interactive `claude` sessions. Codex is covered by its
  OS-level sandbox, which no repo setting can loosen.
- **Isolated.** Committed reviews run inside a throwaway `git worktree` of the
  target ref, so they never collide with your working tree and can review a branch
  that isn't checked out. Dirty-working-tree reviews necessarily run in the live
  repo, read-only.
- **Plan evidence is server-mediated.** Closure-enabled `critique_plan` roles do not
  receive a repository worktree. Claude uses an empty tool allowlist; Codex uses a
  `bwrap` namespace with no shell or repository mounts. Native web is disabled. Claude
  roles also receive an empty tool-availability set and strict empty MCP configuration. Exact
  Codex tool and agent feature schemas are explicitly disabled under strict configuration.
  repository bytes are hashed without Git filters/hooks, and configured HTTPS sources are
  fetched only by bounded server code. All model-visible paths, sources, metadata, and
  passages are JSON escaped; remote and repository bodies never share a role call. Git
  alternates and symlinked object-store components are rejected, inherited object-database
  settings are cleared, and replacement objects/grafts and lazy fetching are disabled for
  plan evidence. Persisted evidence uses strict per-kind schemas; every retained claim
  dependency must still resolve to a valid same-claim record. Network budgets charge each
  redirect hop and every response body, including rejected responses, while DNS and all
  later phases share one enforceable total deadline. Synthetic snapshot commits always
  disable repository-configured signing programs.
- **No API keys, no telemetry.** The server shells out to a CLI you are already
  signed into.
- **Minimal footprint.** In `converge` mode the server creates a short-lived
  worktree and a few unreferenced git objects in the target repo. Both are cleaned
  up on exit and no ref is created. A hard crash can leave the worktree
  registration until the next `git worktree prune` / `git gc`. Your working tree
  and index are never touched.

  **Ref exceptions:** `arbitrate` with `retain_snapshot: true` creates
  `refs/paranoia/arbitrate/<stamp>` so its evidence survives `git gc`. It is the
  persistent opt-in ref. Closure-enabled plan verification also creates temporary
  `refs/paranoia/plan-snapshots/<run>/...` refs so concurrent `git gc` cannot reclaim
  the dirty wrapper or initial history roots mid-round; the server deletes them after
  evidence adoption or abort recovery. Remove an abandoned one only after confirming
  its lineage/in-flight journal is no longer active, with `git update-ref -d <ref>`.

### Rate limits

Reviews draw on your subscription's agentic-usage pool, and a convergence loop is
many agent turns. Use `query` for quick checks and reserve multi-round
`critique_branch` loops for changes that warrant them.

`arbitrate` routinely spends from **both** subscriptions in one call: typically 4
agent turns, 8 at worst (a cleaning retry plus a reconciliation round). A
closure-enabled `critique_plan` also uses both when `independent_check: require` or
an automatic high-stakes/dispute/bearing transition needs a distinct-vendor audit.

---

## Development

```bash
pip install -e '.[dev]'
python -m pytest        # unit + integration; integration uses fake CLIs, no quota
```

The engine subprocess boundary is dependency-injected, so the whole stack is
unit-tested without spending subscription quota. A separate integration test drives
the real subprocess runner against fake `codex`/`claude` binaries on `PATH`.

Design documents for the non-obvious subsystems live in
[`docs/`](docs/): [`class_closure_plan.md`](docs/class_closure_plan.md),
[`plan_class_closure_proposal.md`](docs/plan_class_closure_proposal.md), and
[`claim_verification.md`](docs/claim_verification.md), and
[`arbitration_plan.md`](docs/arbitration_plan.md).

## License

MIT © 2026 Andrew Hillel
