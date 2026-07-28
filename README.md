# paranoia-local

A local MCP server that gets a **cold, adversarial second opinion** on your code
changes and plans — from the *other* frontier coding agent, running on its own
subscription, with **full read access to your repository**.

Install it into Claude Code and reviews are performed by Codex (GPT‑5.6). Install
it into Codex and reviews are performed by Claude Code (Fable 5). The MCP server
is just the channel between them.

One tool is a different shape: [`arbitrate`](#arbitrate--deciding-not-reviewing)
does not review, it **decides** — it runs *both* vendors against each other on a
choice you hand it and computes the verdict itself.

```
┌──────────────┐   "paranoia: critique this branch"   ┌──────────────┐
│  Claude Code │ ───────────────────────────────────► │ paranoia-local│
│  (your work) │                                       │   (MCP, local)│
└──────────────┘                                       └──────┬───────┘
                                                              │ codex exec (read-only, your repo)
                                                       ┌──────▼───────┐
                                                       │ Codex / GPT-5.6│  ← reads the whole repo,
                                                       │  cold reviewer │    decides what to open
                                                       └──────────────┘
```

## Why

Claude (or Codex) can review its own work, but it reviews with the same biases it
wrote with. A *different* model with a *fresh* context is a genuine second opinion.
This tool packages that into one MCP call.

Compared to an API-key reviewer that only sees a hand-assembled payload, a local
agent reviewer is:

- **More powerful** — it has the *entire* repository and git history and decides
  what to read. It opens call-sites, follows the blast radius, checks tests and
  configs, and reads git history — the things a diff-only reviewer can't.
- **Cheaper** — it runs on your existing ChatGPT / Claude **subscription**, not
  metered API tokens.
- **Safer** — the reviewer runs read-only (OS sandbox for Codex; a read-only tool
  allowlist for Claude) inside a throwaway git worktree, so it can't touch your
  work.

## Tools

| Tool | What it does |
|---|---|
| `critique_branch` | Adversarial review of a git branch/diff or the dirty working tree. Five-section critique (What works / doesn't / Risks / Gaps / Improvements) with `[BLOCKER]`/`[MAJOR]`/`[MINOR]`/`[OUT-OF-SCOPE]` tags. |
| `critique_plan` | Adversarial review of a plan or design doc. With `repo_path`, the reviewer reads the real code to test the plan's premises about current behaviour — a plan built on an inverted premise is the most dangerous kind. |
| `query` | A quick double-check of a single fact or point. Not a full review — lower reasoning effort, a direct answer with citations and a stated confidence level. |
| `rebut` | Dispute a specific finding. Resumes the **same** reviewer session with your counter-evidence; it concedes or holds with fresh citations. Cheaper and higher-resolution than a cold re-round. |
| `arbitrate` | Decide between 2–4 options. **Both** engines choose independently and cold over one pinned snapshot; Python computes the verdict. See below. |

Every review returns a `session_ref` in its footer — pass it to `rebut`.

## `arbitrate` — deciding, not reviewing

The other four tools get you a second opinion. `arbitrate` gets you a *decision*:
you hand it 2–4 options and it returns `CONVERGED` only when both frontier
vendors, judging independently, picked the same one for reasons they could each
cite.

```json
{
  "name": "arbitrate",
  "arguments": {
    "repo_path": "/Users/you/Work/my-project",
    "decision": "Choose the numeric type for the position-size threshold.",
    "options": [
      {"id": "opt-float",   "statement": "Store it as a float."},
      {"id": "opt-decimal", "statement": "Store it as a Decimal."}
    ],
    "stakes": "Internal CLI, single team, threshold used only in a log line.",
    "files": [{"path": "scripts/lib/registry.py", "reason": "the writer"}]
  }
}
```

What happens, and why each step is there — a decision tool is only worth the
independence behind it, so most of the machinery exists to stop the two vendors
agreeing for a reason other than the evidence:

1. **One snapshot.** The working tree is pinned to a commit and each decider gets
   its own worktree of it, so both search freely over the same pinned tree. Git
   *history* is still live — the worktrees attach to your real repo — so the server
   digests every ref and the reflog before and after the run and returns `FAILED` if
   anything moved, rather than reporting agreement it cannot describe.
2. **The framing is neutralized** by an Opus agent — advocacy stripped, options
   equalized in detail — and then **attested by the other vendor**, field by
   field, before any decider sees it. `stakes` is never rewritten.
3. **Counterbalanced presentation.** One decider sees the options in canonical
   order, the other reversed, under **opaque per-decider labels** so nothing about
   your ordering or ids leaks. Neither is told the other exists.
4. **Python computes the verdict.** No model adjudicates the adjudication.
5. **On divergence**, one reconciliation round carries only `path:line` citations
   and the bytes the server itself read — never the other model's prose — and
   only when there is genuinely novel evidence for both.

### Outcomes

| Outcome | Meaning |
|---|---|
| `CONVERGED` | Unanimous, unblocked, and each vote substantiated by a resolved citation. |
| `BLOCKED` | They agree on an option and one of them tags it `[MAJOR]`/`[FATAL]`. |
| `REFRAME_REQUIRED` | A decider surfaced a better unlisted option. Give it an id and re-run. |
| `UNRESOLVED` | Still split, or agreement nobody could substantiate, or divergence with nothing new to reconcile. |
| `FAILED` | Preflight, cleaning, parsing, or the repo's refs moved mid-run. |

The reply ends with a machine-readable trailer whose fields are always present:
`ARBITRATION`, `SELECTED`, `ADVISORY`, `AUTHORITY-POLICY`, `CLEANING`,
`SNAPSHOT`, `ORDER-SEED`, `REFS-MOVED`, `AUDIT`, `ROUNDS`.

### Shaping the input

The framing is checked against numeric bounds **before** anything is spent, and one
shape passes them naturally:

> Put every shared fact, and the **full specification of whatever only one option
> adopts**, into `context` — prefaced as "the rules under consideration, if adopted".
> Leave each option statement to say only how much of it is adopted, and what follows.

The reason is structural. "Adopt X, with this precedence and this invariant" carries
more mechanism to state than "don't", so a scope decision written the obvious way
trips the equalization bound by construction, and no amount of re-cleaning fixes it —
shortening the longer option just deletes the specification the deciders need. Hoisting
the mechanism turns both options into statements of *scope-of-adoption*, and they
equalize on their own (~800 chars each is typical).

| Bound | Limit | Why |
|---|---|---|
| option statement | 1200 chars | dense options cannot be round-tripped through the cleaner without the attester scoring a fidelity change |
| longest ÷ shortest option | 2.0 | asymmetric detail is an argument regardless of wording |
| `decision` | 2500 chars | it states what is being chosen, not the evidence for it |
| `context` | 20000 chars | the designated home for detail; not per-option, so its length cannot be a vote |

Failures name the gate, the measurement, and the remedy, and cost nothing — they are
raised before the cleaner runs.

### Things to know before you rely on it

- **Both CLIs must be installed.** Unlike the review tools, `arbitrate` drives
  `codex` *and* `claude` whichever one you installed the server into. There is no
  single-vendor mode: two rounds against one vendor is not arbitration.
- **`ADVISORY` does not block.** Each decider reports whether it thinks a human
  owner should be authorizing the decision at all. That is reported, never gated
  — a `CONVERGED` with `ADVISORY: human-owner` is still `CONVERGED`. Enforcing it
  is your policy, not the tool's.
- **A vendor that never changed its mind is not asked to cite the other's evidence.**
  In round 2 the carried-evidence requirement applies only to a vendor whose selection
  *moved* — that is what it is for, since capitulation is a change. A vendor that held
  its round-1 position needs only a citation that resolves, **provided its round-1
  decisive citation resolved too**; a holder that was never substantiated in the first
  place must ground in gained evidence like a mover.
- **It only decides things the repository can settle.** A converging vote must
  cite a line. A decision that does not turn on repo-verifiable grounds will
  never return `CONVERGED` here.
- **Cost:** 4 agent turns typically, 8 at worst, across both subscriptions.
- **Bias is reduced, not eliminated.** Order counterbalancing equalizes mean rank
  but not higher moments for 3–4 options; attestation is a model's judgement, not
  a proof; and a file-hint list that only points at evidence favouring one option
  biases both deciders identically. `docs/arbitration_plan.md` §2 names every
  residual.
- `SNAPSHOT` is provenance, not a replay handle — the snapshot commit is
  unreferenced and `git gc` reclaims it. The audit log holds both prompts, both
  replies, and the carried evidence. Pass `retain_snapshot: true` to pin it behind
  a ref; that is the only mode that writes one.

### Convergence loop

`critique_branch` and `critique_plan` take an `already_raised` array: one-line,
`file:line`-cited claims already accepted from prior rounds. The reviewer is told
not to restate them and to hunt for what they missed. Drive the loop from the
caller — spawn a fresh review each round feeding the growing `already_raised`
list — until findings converge or drop to noise. (Never paste prior reviewers'
prose; just the deduplicated claim + citation.)

**Two calibration levers keep the loop proportionate and terminating** — tune
them per round (they exist because an uncalibrated cold reviewer defaults to
maximum paranoia and manufactures marginal/hardening findings for 20+ rounds):

- **`stakes`** — the real deployment context / threat model / scale (e.g.
  `"single-user local CLI, trusted input, no multi-tenancy"`). The reviewer
  treats it as the **boundary of legitimate concern**: findings that assume
  adversaries, scale, or failure modes beyond it are dropped or tagged
  `[OUT-OF-SCOPE]`, never must-fix. Omit it and the reviewer assumes a *modest
  internal tool*, not a hostile/high-scale service. Set it **once per project in
  `.paranoia.toml`**; override per-call to tighten. This is the single highest-
  leverage lever against hardening scope-creep.
- **`round`** — the 1-based loop round. **Increment it each cold round.** At
  `round >= 3` the reviewer reports only merge-blocking in-scope findings
  (`[MAJOR]` or higher for the review mode) and says `CONVERGED` — inside the
  five-section format — when none remain, which is how you *stop* the loop
  instead of chasing diminishing findings. Start at 1; raise as the design stabilises.

Operator recipe: set `stakes` in `.paranoia.toml`, then loop `already_raised` +
`round` (1, 2, 3, …). **Stop when the computed `CONVERGENCE:` trailer says
`NOT-BLOCKED` and the round returns `CONVERGED` or only
`[OUT-OF-SCOPE]`/`[MINOR]` items** — the trailer governs, and when it says
`BLOCKED` a reviewer's own `CONVERGED` is void (see *Class closure* below). Fold
`[FATAL]`/in-scope-`[MAJOR]` findings; record `[OUT-OF-SCOPE]` ones separately
rather than growing the design to fix them.

**Two signals that the loop is going wrong, both learned the hard way:**

- *The same defect keeps reappearing in a new spelling.* You are fixing instances,
  not the class. That is what class closure exists to stop.
- *Findings stop being about your diff and start being about imaginable inputs.*
  The stakes are wrong, not the code. Tighten `stakes` and re-run that round
  rather than folding what it raised.

### Class closure (`class_closure`, **on by default** for `critique_branch`)

A convergence loop that reports one instance of a defect per round can run for ten
rounds while a single invariant stays violated — each round the operator fixes the
site that was named, and the next round finds a sibling. The protocol had nowhere to
put the *class*: findings are `file:line` shaped, `already_raised` tells the reviewer
not to look there again, and the round-3 severity floor meters the leak to one
instance per round.

With class closure on, the reviewer ends its review with a **class register**: for
each defect class, the invariant, a severity, and a **regex that matches violations
only** (or a `PROCEDURE`, when no regex can express it). The server then:

- **re-runs every registered predicate itself, every round**, against the reviewed
  snapshot — `git grep -l -z` decides, so a violation inside a binary blob still counts;
- **injects the surviving matches** into the next packet, *after* `already_raised` and
  with explicit precedence over it, exempt from the severity floor;
- **computes the verdict in Python** and appends it:

```
LINEAGE: 9f2c1a4b0e77 (rounds recorded: 8)
CLASS-REGISTER: parsed 1
CLASS-CLOSURE: 1 open, 2 closed, 3 surviving matches, 0 exempt, 1 unmechanized
CONVERGENCE: BLOCKED — 1 class(es) unclosed:
  3f2a91c4 every open state must be in the v2 open set (mechanized: 3 match(es))
```

A class closes when its predicate returns **zero matches**, and reopens the moment it
matches again. Only `BLOCKER`/`MAJOR` classes block; `MINOR` and `OUT-OF-SCOPE` ones
are tracked and advisory, so the mechanism can't trap you on a marginal finding.

**What it does not do.** It guarantees durability for a class the reviewer
*registers*. A reviewer that finds a class and doesn't register it is
indistinguishable from one that never found it, and no parser over free text closes
that gap — so nothing in the review's prose is parsed at all. `NOT-BLOCKED` therefore
says only "no blocking class is unclosed", never that the change is correct.

State lives in `~/.paranoia/lineages/<id>.json`, keyed by repo + `base_ref` + the
reviewed branch (override with `lineage`; required when reviewing a detached HEAD).
A false positive of a regex is dismissed with `exempt` — shown to every later reviewer
for challenge, and revocable with `unexempt`. Unreadable or unwritable state **blocks**
rather than starting a fresh lineage, because a storage fault must never read as an
all-clear. Pass `class_closure: false` to restore the previous behaviour exactly.

Full design, and the sixteen review rounds behind it:
[`docs/class_closure_plan.md`](docs/class_closure_plan.md).

### Convergence packet mode (`converge`, **on by default**)

Each cold round otherwise re-gathers the same orientation — re-reading the touched
files and re-running `git`, which measurements show dominates the per-round cost.
`critique_branch` therefore runs in **convergence mode by default** (pass
`converge: false`, or set it in `.paranoia.toml`, to fall back to the legacy in-place
review). In convergence mode the server **pre-gathers a
deterministic evidence packet** (the contents of every touched file in the reviewed
snapshot — binary/large files are marked rather than embedded — plus the diff) and
hands it to the reviewer with a packet-aware prompt, so it verifies rather than
re-collects. The review runs against a **materialized worktree** of the snapshot
captured at request time, so evidence is a consistent point-in-time view that later
live edits can't perturb, and `already_raised` is always preserved under the packet
budget (`max_packet_chars`, default 400k). Deterministic and per-request — no
persistent session or handle; independent of the reviewer engine. (The end-to-end
saving is the subject of the plan's acceptance benchmark; the mechanism removes the
gather step, but treat the magnitude as pending that measurement.)

## Install

### Prerequisites

- Python 3.11+
- `git` on `PATH`
- The reviewing agent's CLI installed and signed in on a subscription:
  - [Codex CLI](https://developers.openai.com/codex) (`codex`, ≥ 0.144) signed in
    with a ChatGPT plan, **or**
  - [Claude Code](https://code.claude.com) (`claude`) signed in with a Claude plan.
- **`arbitrate` needs BOTH**, whichever one you install the server into — it drives
  the two vendors against each other, so there is no single-vendor mode. The four
  review tools need only the other agent's CLI, as above.

### Install the server

```bash
git clone https://github.com/subvertnormality/paranoia-local
cd paranoia-local
pip install -e .
```

This puts a `paranoia-local` executable on your `PATH` — the command both the
Claude Code and Codex MCP entries below launch.

### Wire into Claude Code (reviews performed by Codex)

```bash
claude mcp add paranoia -- paranoia-local --engine codex
```

Add to your `~/.claude/CLAUDE.md` so it's only used on request:

```
Never call the paranoia MCP server unless I explicitly ask for adversarial review,
critique, or a second opinion.
```

### Wire into Codex (reviews performed by Claude Code)

Register the server (this writes the `[mcp_servers.paranoia]` table to
`~/.codex/config.toml`):

```bash
codex mcp add paranoia -- paranoia-local --engine claude
```

Then **you must add the timeout keys** — `codex mcp add` does not set them, and
the defaults are far too low. Edit `~/.codex/config.toml` so the entry reads:

```toml
[mcp_servers.paranoia]
command = "paranoia-local"
args = ["--engine", "claude"]
# REQUIRED: an agentic review is many turns of tool use and runs for minutes.
# Codex's default MCP tool timeout is 60s and startup is 10s, which abort every
# review. Give the tool an hour and startup 30s.
tool_timeout_sec = 3600
startup_timeout_sec = 30
```

Verify it took:

```bash
codex mcp get paranoia
#   tool_timeout_sec: 3600
#   startup_timeout_sec: 30
```

> **Timeout gotcha.** A full review is many turns of tool use and can run for
> several minutes. Claude Code's stdio MCP idle timeout (~30 min) is fine out of
> the box; **Codex defaults to a 60-second tool timeout** (`tool_timeout_sec`)
> and a 10-second startup timeout (`startup_timeout_sec`), and both must be
> raised as shown above or every review fails. 3600s is a generous per-call
> ceiling — a single review is minutes, and a multi-round convergence loop is
> separate calls, each well under the limit. Raise it further for very large
> repos at high effort.

## Usage

In Claude Code:

> "Use paranoia to critique this branch against main. Intent: add overdraft
> protection to `withdraw()`."

The agent calls:

```json
{
  "name": "critique_branch",
  "arguments": {
    "repo_path": "/Users/you/Work/my-project",
    "base_ref": "main",
    "head_ref": "HEAD",
    "diff_intent": "Add overdraft protection to withdraw()."
  }
}
```

## Per-repo defaults — `.paranoia.toml`

Drop a `.paranoia.toml` at the repo root so callers stop retyping context. Keys at
the top level or under `[paranoia]`. Precedence: **call arg > `.paranoia.toml` >
built-in default**.

```toml
project_summary = "A booking API. Python/FastAPI, Postgres. Auth via short-lived JWTs."
base_ref = "develop"
web_search = true      # allow external methodology/library cross-checks
isolate = true         # review inside a throwaway worktree
# stakes: the deployment reality the reviewer must stay proportionate to (see
# "Convergence loop"). Set once here so every review is calibrated to the project.
stakes = "Internal booking API, single team, authenticated first-party callers, ~1k req/min."
# model / effort overrides also honoured
```

## Common arguments

The four review tools accept:

- `engine` — override which engine reviews for this one call (`codex` | `claude`).
- `model` — override the reviewer model (defaults to the engine's strongest:
  `gpt-5.6-sol` / `claude-fable-5`).
- `effort` — `low` | `medium` | `high`. Reviews default to `high`; `query`
  defaults to `medium`.
- `web_search` — allow the reviewer to cross-check external methodology/library
  claims on the web (default `true`).

**`arbitrate` deliberately has no `engine` or `model`.** It runs both vendors, so a
single override could only degrade it to one of them or send one vendor's model
name to the other CLI. It takes `models: {codex?, claude?}` for per-vendor
overrides, plus `cleaner_model`, and honours `effort` and `web_search`.

## Safety model

- **Read-only.** Codex runs under its OS sandbox (`--sandbox read-only`); Claude
  runs with a read-only tool allowlist (`Read`, `Grep`, `Glob`, scoped `git`
  reads, web search) and write tools explicitly denied. The reviewer cannot edit
  your code, run your test suite, or reach the network except for opt-in web
  search.
- **Hermetic — the audited repo cannot widen the reviewer.** The Claude engine
  is spawned with `--setting-sources ""`, so it loads **no** `.claude` settings
  files. Without this, `claude -p` merges the reviewed repo's
  `.claude/settings.local.json` and your global `~/.claude/settings.json` on top
  of paranoia's allow-list — and those routinely grant `Bash(python3:*)`,
  `Bash(git commit:*)`, `Bash(python -m pytest …)` etc., silently handing the
  reviewer arbitrary code execution and write-capable git on the very repo it is
  auditing. Loading zero settings sources makes paranoia's `--allowedTools` the
  sole authority. This is a flag on the **spawned reviewer subprocess only** — it
  does not read, write, or affect any of your interactive `claude` sessions or
  settings files. (Codex is already covered here by its OS-level read-only
  sandbox, which no repo setting can loosen.)
- **Isolated.** Committed reviews run inside a throwaway `git worktree` of the
  target ref, so they never collide with your working tree and can review a
  branch that isn't checked out. (Dirty-working-tree reviews necessarily run in
  the live repo, read-only.)
- **No API keys, no telemetry, minimal state.** The server shells out to a CLI
  you're already signed into. It writes a local audit record per review to
  `~/.paranoia/logs/` (provenance + the session ref for `rebut`). In `converge`
  mode (below) it additionally creates a short-lived git worktree and a few
  **unreferenced** git objects (the reviewed snapshot) in the target repo. On a
  clean exit both are cleaned up (best-effort) and no ref is created. A hard
  crash mid-review — or a rare teardown failure —
  can leave the worktree registration (and, while it exists, the snapshot objects
  it checks out) until the next `git worktree prune`/`git gc` — run either to
  reclaim them. Your working tree and index are never touched.

  **One opt-in exception:** `arbitrate` with `retain_snapshot: true` creates
  `refs/paranoia/arbitrate/<stamp>` so its evidence survives `git gc`. It defaults
  to **off** precisely to keep the promise above, and it is the only mode in the
  whole server that writes a ref. Remove one with `git update-ref -d <ref>`.

## Rate limits

Reviews draw on your subscription's agentic-usage pool. A heavy convergence loop
is many agent turns — on smaller plans you can hit the 5-hour window. Use `query`
(lower effort) for quick checks, and reserve full multi-round `critique_branch`
loops for changes that warrant them.

`arbitrate` is the expensive one, and it is the only tool that spends from **both**
subscriptions in a single call: 4 agent turns typically, 8 at worst (a cleaning
retry plus a reconciliation round). Its cleaner and attester are short text-only
turns; the decider turns are the real cost.

## Development

```bash
pip install -e '.[dev]'
python -m pytest        # unit + integration (integration uses fake CLIs; no quota)
```

Every module is TDD'd. The engine subprocess boundary is dependency-injected, so
the whole stack is unit-tested without spending subscription quota; a separate
integration test drives the real subprocess runner against fake `codex`/`claude`
binaries on `PATH`.

## License

MIT © 2026 Andrew Hillel
