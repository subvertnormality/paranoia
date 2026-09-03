# Paranoia

Get a cold, adversarial review of your code, plans, and technical decisions from
the other frontier coding agent.

Paranoia Local is an MCP server that connects Claude Code and Codex CLI. Install
it in one agent and it runs the other as a read-only reviewer, using that
reviewer's existing subscription and full repository context.

```text
Claude Code ──MCP──> Paranoia Local ──read-only──> Codex
Codex       ──MCP──> Paranoia Local ──read-only──> Claude Code
```

Use it to:

- review a branch, diff, or dirty working tree;
- challenge a plan against the code it describes;
- track findings and defect classes until they are closed;
- verify load-bearing plan claims against captured authoritative sources;
- ask a focused repository question;
- rebut a finding in the same reviewer session; or
- arbitrate a decision with both vendors independently.

[Get started](#quickstart) · [Choose a tool](#choose-a-tool) ·
[Understand tracked reviews](#tracked-reviews) · [Configure](#configuration) ·
[Full tool reference](docs/tool-reference.md) · [LLM and agent entry point](llms.txt)

## Quickstart

### 1. Install the prerequisites

You need:

- Python 3.11 or later;
- Git 2.36 or later on `PATH`; and
- the reviewing agent's stable CLI, installed and signed in:
  [Codex CLI](https://developers.openai.com/codex) 0.144.6 or later, or
  [Claude Code](https://code.claude.com) 2.1.251 or later.

Most tools need only the reviewer CLI. `arbitrate` uses both vendors and needs
both CLIs.

### 2. Install Paranoia Local

```bash
git clone https://github.com/subvertnormality/paranoia-local
cd paranoia-local
pip install -e .
```

### 3. Add it to your coding agent

`--engine` names the agent that performs the review, so it is the opposite of
the agent you are configuring.

#### Claude Code: reviews performed by Codex

```bash
claude mcp add paranoia -- paranoia-local --engine codex
```

#### Codex: reviews performed by Claude Code

```bash
codex mcp add paranoia -- paranoia-local --engine claude
```

Codex defaults to short MCP timeouts, while a thorough review can take several
minutes. Add these values to `~/.codex/config.toml`:

```toml
[mcp_servers.paranoia]
command = "paranoia-local"
args = ["--engine", "claude"]
tool_timeout_sec = 8400
startup_timeout_sec = 60
```

Verify the registration with `codex mcp get paranoia`.

### 4. Request your first review

Ask your coding agent naturally:

> Use Paranoia to critique this branch against `main`. The change is intended
> to add overdraft protection to `withdraw()`. This is an internal API with
> authenticated first-party callers and no hostile local processes. Use round 1.

The corresponding MCP call is:

```json
{
  "name": "critique_branch",
  "arguments": {
    "repo_path": "/absolute/path/to/project",
    "base_ref": "main",
    "round": 1,
    "diff_intent": "Add overdraft protection to withdraw().",
    "stakes": "Internal API; authenticated first-party callers; no hostile local processes."
  }
}
```

Paranoia returns cited findings, severity tags, a reusable `session_ref`, and a
computed `CONVERGENCE` result. Fix the blocking findings, increment `round`, and
run the review again until the result is `CONVERGENCE: NOT-BLOCKED`.

## Choose a tool

| Tool | Use it when |
|---|---|
| [`critique_branch`](docs/tool-reference.md#critique_branch) | You want a full review of committed or uncommitted code |
| [`critique_plan`](docs/tool-reference.md#critique_plan) | You want a plan checked against the repository and its external premises |
| [`query`](docs/tool-reference.md#query) | You need one cited answer, not a full review |
| [`rebut`](docs/tool-reference.md#rebut) | You have evidence that a previous finding is wrong |
| [`arbitrate`](docs/tool-reference.md#arbitrate) | You need Codex and Claude to decide independently between 2–4 options |

The [complete tool reference](docs/tool-reference.md) documents every argument,
default, constraint, result, and failure mode.

## Common workflows

### Review a branch or working tree

`critique_branch` reviews `base_ref..head_ref` in an isolated temporary worktree
by default. To review local edits instead, pass `include_uncommitted: true`; that
mode necessarily reads the live working tree, but the reviewer remains read-only.

Useful inputs are:

- `diff_intent`: what the change is supposed to accomplish;
- `project_summary`: neutral project context;
- `stakes`: the actual deployment, trust, scale, and failure consequences;
- `focus`: an optional narrow concern; and
- `already_raised`: short, accepted, `file:line`-cited claims from earlier rounds.

You can bind an approved implementation plan to the branch review with
`plan_text` or an absolute `plan_path`. The first plan-bearing round freezes that
contract for the lineage; later rounds verify the implementation against the same
text. Changing the contract requires a new lineage.

### Review a plan

Tracked plan reviews require an explicit, stable lineage because plans do not
have a branch name that can identify their history.

```json
{
  "name": "critique_plan",
  "arguments": {
    "repo_path": "/absolute/path/to/project",
    "plan_path": "/absolute/path/to/project/docs/overdraft-plan.md",
    "lineage": "payments-42-plan",
    "round": 1,
    "stakes": "Internal API; one service team; about 1,000 requests/minute."
  }
}
```

The reviewer reads the repository to test the plan's claims about current
behavior. By default, it also verifies load-bearing external facts, requirements,
and dependency behavior. Search discovers candidate URLs; Paranoia downloads the
pages, extracts the text, binds exact passages, and uses a separate cold check for
authority and entailment. Search summaries, snippets, and user-generated content
cannot close a claim.

Set `claim_verification: false` only when you deliberately want a structural-only
review. See [external claim verification](docs/how-it-works.md#external-claim-verification)
for the evidence model and limits.

### Ask a focused question

Use `query` for a fast second opinion:

```json
{
  "name": "query",
  "arguments": {
    "question": "Can this retry loop duplicate a payment?",
    "repo_path": "/absolute/path/to/project",
    "files": [{"path": "src/payments/retry.py", "reason": "retry owner"}]
  }
}
```

It returns a direct, cited answer with a confidence level and does not create a
tracked review.

### Challenge a finding

Every review returns a `session_ref`. Pass it to `rebut` with concrete
counter-evidence:

```json
{
  "name": "rebut",
  "arguments": {
    "repo_path": "/absolute/path/to/project",
    "session_ref": "<session_ref from the review>",
    "rebuttal": "The call is guarded by the transaction opened at db.py:74."
  }
}
```

The same reviewer session responds `CONCEDE` or `HOLD` with fresh citations.
The unbound form is non-mutating. For a persistently gated class, optional
`lineage`, `class_id`, `debt_id`, and `lineage_mode` arguments bind the result
to one current durable target. `HOLD` is audit-only. A validated `CONCEDE`
closes that debt and closes its class only when no sibling blocker remains; it
never grants clearance, and the next critique still performs the normal final.
The closed debt retains a durable concession record. Later staged reviewers see
that exact prior adjudication and must provide a keyed challenge with new resolved
evidence before the same class can be violated, reopened, or replaced. The record
survives unrelated snapshot and stakes changes, but it is not an exemption from a
genuine changed occurrence.
Bound citations use the staged anchor grammar and must resolve before settlement;
tracked plan reviews retain their line count so repeated `plan:` anchors remain bounded.
When a staged plan citation fails resolution, the bounded same-session retry repeats the legal
`plan:<line-or-range>` grammar and the current plan bound. It explicitly tells the reviewer to
discard any column component rather than concatenate line and column digits; validation never
guesses, clamps, drops evidence, or partially settles an unresolved citation.
Mechanized branch classes remain predicate-owned and must be closed by a normal
`critique_branch` sweep rather than a bound rebut.

### Arbitrate a decision

`arbitrate` runs both vendors independently over one pinned repository snapshot:

```json
{
  "name": "arbitrate",
  "arguments": {
    "repo_path": "/absolute/path/to/project",
    "decision": "Choose the numeric type for the position-size threshold.",
    "options": [
      {"id": "float", "statement": "Store the threshold as a float."},
      {"id": "decimal", "statement": "Store the threshold as a Decimal."}
    ],
    "stakes": "Internal CLI; the threshold is used only in a log line.",
    "files": [{"path": "scripts/lib/registry.py", "reason": "current writer"}]
  }
}
```

Put facts shared by every option in `context`. Put each option's distinct
mechanism, scope, tradeoffs, and consequences in its own `statement`. Research is
enabled by default; Paranoia gives both deciders the same server-captured evidence
with live browsing disabled. Python computes the outcome rather than asking a
third model to choose between the votes.

`arbitrate` is the only tool that consumes both subscriptions in one call. Read
its [full reference](docs/tool-reference.md#arbitrate) before relying on the
outcome or using `retain_snapshot`.

## Tracked reviews

Tracking is on by default for branch and plan reviews. A tracked review has three
phases:

1. **Census:** three cold review lanes inspect the complete artifact and one call
   consolidates their findings.
2. **Correction:** later rounds target durable debt and the effects of your fixes.
3. **Final:** after debt closes, one fresh whole-artifact regression is required.

The engine that closes correction debt owns the resulting final-regression gate.
A different engine may still report new debt, but its clean result cannot discharge
that pending gate; the trailer names the required engine. Older unowned final state
re-enters census once rather than guessing an owner.

The retained 2026-08-23 persistent-correction acceptance predates final ownership
and is historical evidence only; it does not certify the current final-selection or
clearance route. Current owner behavior is exercised through both public handlers.

A clear census can finish immediately. Otherwise, increase `round` only after
you have changed the reviewed artifact. Failed or rejected rounds can reuse the
same label; a successfully settled round requires the next label to increase.

Paranoia tracks both concrete findings and reusable defect classes. Blocking
classes remain open across rounds even if a reviewer forgets to mention them.
Mechanized branch classes are rechecked against each snapshot. Plan classes are
procedural and require explicit reviewer closure. `MINOR` and `OUT-OF-SCOPE`
classes remain visible but do not block convergence.

The key trailer fields are:

| Field | Meaning |
|---|---|
| `CLASS-CLOSURE` | Open and closed reusable classes |
| `STRUCTURAL-PHASE` | The next tracked phase: `census`, `correction`, `final`, or `clear` |
| `STRUCTURAL-DEBT` | Remaining blocking findings |
| `CLAIM-CLOSURE` | External-plan-claim status, when verification is enabled |
| `REVIEW-ATTEMPTS` | Claim and structural attempts, including recovered validation retries |
| `CONVERGENCE` | The single governing `BLOCKED` or `NOT-BLOCKED` result |

`NOT-BLOCKED` means the tracked gates are clear under the stated stakes. It is a
review result, not proof that the artifact is correct.

A terminal claim-role failure renders `CLAIM-CLOSURE: AUDIT-FAILED`; claim counts are called
last accepted only when a successful audit is bound to the exact same plan snapshot. Otherwise,
including a first-audit failure or changed-plan structural preflight, preserved rows are omitted
from current actionable packets and labeled non-adjudicated history rather than rewritten as
`unverified` verdicts. Predecessor rows already rewritten by the old failure path receive the
same conservative treatment. A missing correction-control row for an active class is initialized without
discarding the other classes' counters; stale rows for inactive classes still fail closed.

Correction batches independent occurrences of one reusable class into one governing finding with
all distinct evidence anchors and an all-site remedy. Both plan and branch reviewers trace
co-asserting sites, so definitions, call sites, tests, fixtures, and contract sections are repaired
together. Each settlement retains one finding and outcome per class; historical debt IDs may close
and a fresh occurrence may receive a new ID, while the server-owned correction gate still rejects
rephrasing that leaves the class blocking.
For an unmechanized class, correction and final use the durable class invariant and procedure as
the search boundary rather than limiting review to the current debt or its known anchors. Every
site or property category named there must be inspected and accounted for before the class can be
reported satisfied; any surviving occurrences are returned together. Mechanized classes continue
to use their server-run violation predicates.
Every unmechanized class stores a closed list of stable member IDs. A satisfied census assessment,
correction outcome, or final outcome must provide exactly one separately evidenced row for every
server-supplied member ID; the server checks exact set equality before deriving and deduplicating
the existing flat durable evidence list. Different members may share an anchor. Legacy classes
without an inventory remain loadable, but every staged phase—including same-snapshot clear and
claim-only migration—re-enters broad census until an inventoried replacement is settled. The
retained text register also requires `MEMBERS` for new and replacement unmechanized classes.
An otherwise standalone correction `close` must carry an authored `satisfied` class outcome and
evidence; the server rejects a bare close through the existing bounded validation retry.
A fresh aggregate finding closes the class's narrower prior open debt after incorporating every
still-reachable predecessor occurrence, preventing duplicate blockers for one class.
The correction materializer cross-checks the fresh finding against its matching violated class
outcome and rejects it if any independently authored current-occurrence anchor is missing from the
aggregate finding; the retry identifies the provider-owned evidence pointer.
The same check runs before a non-debt-bound correction finding can derive its violated outcome from
`classification.assessment_evidence`.
Correction settlement rejects any prospective state with more than one open debt for an active class.

Broad plan census and final roles also inspect proactively for one normative contract stated as
authoritative in multiple operative locations, even before the copies visibly disagree. They ask
for one authoritative definition with references or derived projections elsewhere. This is a
semantic review duty, not a repeated-token lint: examples, faithful table explanations, generated
projections, and summaries that explicitly defer to the governing definition remain valid.
Targeted correction does not reopen unrelated plan material for this audit.
The retained real-provider acceptance in
`docs/plan_restatement_acceptance_2026-09-01.json` binds the four-call broad census,
the complete operative restatement cluster, the deferred-example exemption, durable settlement,
and a separate targeted-correction scope control to exact prompts and source bytes. It then
continues that lineage through a real cold final, where the previously out-of-scope duplicate
contract is discovered and persisted. The validator replays every retained raw provider envelope
through the production extractor and public `critique_plan` handler from source-derived initial
lineages, and requires the returned result, replayable audit projection, and complete durable
successor to match. The source inventory covers the complete executable `paranoia_local` package;
raw stdout is the sole text-channel authority. Parsed response, session, usage, and failure detail
are derived from it; the observed subprocess return code is retained separately and drives replay.
Process stderr and local wall-clock duration are deliberately not claimed because neither can be
independently reproduced from stdout.

For lifecycle details, persistence controls, false-positive exemptions, and
failure recovery, read [How Paranoia works](docs/how-it-works.md).

### One-shot reviews

For an exploratory branch review with no durable convergence state, pass both:

```json
{"class_closure": false, "converge": false}
```

For a one-shot plan review, pass `class_closure: false`; `converge` is not a plan
argument. One-shot plan reviews still return structural prose and claim packets,
but no computed convergence verdict. Plan-backed branch contracts are not
available in one-shot mode.

## Configuration

Add `.paranoia.toml` to a repository to avoid repeating branch-review defaults.
Keys can be top-level or under `[paranoia]`. Precedence is call argument, then
repository configuration, then built-in default.

```toml
project_summary = "A Python booking API backed by Postgres."
base_ref = "develop"
stakes = "Internal service; authenticated callers; one team; about 1,000 requests/minute."
web_search = true
isolate = true
```

Supported keys are `base_ref`, `project_summary`, `stakes`, `isolate`,
`converge`, `class_closure`, `max_packet_chars`, `model`, `effort`, and
`web_search`.

For `critique_plan`, `lineage` and `class_closure` are call-only arguments and
are never read from `.paranoia.toml`.

The executable accepts:

```text
paranoia-local --engine {codex|claude} [--log-dir DIR]
```

Audit records default to `~/.paranoia/logs/`. Durable review state defaults to
`~/.paranoia/lineages/` and deliberately does not follow `--log-dir`. Set
`PARANOIA_STATE_ROOT` to relocate lineage state.

## Safety and cost

- Reviewers are read-only. The calling coding agent owns all edits and test runs.
- Committed branch reviews use temporary worktrees; dirty reviews read the live
  working tree without writing to it.
- Verified plans and arbitration use inert repository materializations that do
  not execute repository hooks, filters, helpers, symlinks, or executables.
- Reviewer subprocesses ignore user tool configuration and receive only the
  capabilities required for their role.
- Paranoia uses the CLI subscriptions you are already signed into. It needs no
  API keys and sends no Paranoia telemetry.
- Tracked census reviews use multiple model calls. `query` is the lower-cost
  choice for a single question; `arbitrate` is the most expensive tool.
- `arbitrate` normally creates no durable Git ref. Opting into
  `retain_snapshot: true` creates `refs/paranoia/arbitrate/<stamp>` until you
  delete it with `git update-ref -d <ref>`.

Read the complete [safety, evidence, state, and rate-limit model](docs/how-it-works.md).

## Troubleshooting

**The MCP call times out in Codex.** Set `tool_timeout_sec = 8400` in the MCP
configuration shown in the quickstart.

**The reviewer executable is unavailable or too old.** Run `codex --version` or
`claude --version`, update the CLI, and confirm it is signed in in the same
environment that launches the MCP server.

**A tracked plan call rejects `lineage`.** Use a globally unique, mode-qualified
key such as `myproject-42-plan`. Do not reuse a branch lineage for a plan.

**A continuing review reports `STATE-UNAVAILABLE`.** Follow the absolute state
path in the diagnostic. Repair or deliberately remove that lineage before
starting again; audit logs are not backup authority for convergence state.

**You only need a quick opinion.** Use `query`, or deliberately select the
one-shot settings described above.

## Documentation

- [Complete MCP tool reference](docs/tool-reference.md)
- [Review lifecycle, evidence, safety, state, and limits](docs/how-it-works.md)
- [Dense LLM/agent operating reference](docs/llm-reference.md)
- [Standard LLM documentation index](llms.txt)
- [Claim-verification design and acceptance notes](docs/claim_verification.md)
- [Arbitration design](docs/arbitration_plan.md)
- [Developer and acceptance documentation](docs/)

## Development

```bash
pip install -e '.[dev]'
python -m pytest
python scripts/run_staged_protocol_mutation_checks.py
```

Tests use dependency-injected fake CLIs and do not consume subscription quota.
The [`docs/`](docs/) directory contains design records and signed-in acceptance
artifacts for provider-sensitive paths.

## Help and maintenance

Paranoia Local is maintained by Andrew Hillel. Open a GitHub issue with a minimal
reproduction, the tool name, bounded error text, and relevant CLI versions. Do
not publish secrets or a complete private audit log.

## License

MIT © 2026 Andrew Hillel
