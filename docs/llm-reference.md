# Paranoia Local: LLM operating reference

Purpose: provide enough precise context for an agent to install, select, and call
Paranoia Local without inferring behavior from introductory prose. Runtime MCP
schemas are authoritative.

## Identity

- Package and executable: `paranoia-local`
- Protocol: local MCP over stdio
- Requirements: Python 3.11+, Git 2.36+
- Engines: `codex`, `claude`
- Minimum evidence-profile CLIs: Codex 0.144.6; Claude Code 2.1.197
- Default models: `gpt-5.6-sol`; `claude-fable-5`
- Arbitration cleaner: `claude-opus-5`
- Tools: `critique_branch`, `critique_plan`, `query`, `rebut`, `arbitrate`

## Host/reviewer invariant

- Claude Code host: `paranoia-local --engine codex`.
- Codex host: `paranoia-local --engine claude`.
- `--engine` names the reviewer, not the host.
- `arbitrate` invokes both vendors. It accepts `models:{codex?,claude?}`, not
  `engine` or singular `model`.

## Installation

```bash
git clone https://github.com/subvertnormality/paranoia-local
cd paranoia-local
pip install -e .
claude mcp add paranoia -- paranoia-local --engine codex
# OR
codex mcp add paranoia -- paranoia-local --engine claude
```

Codex host configuration:

```toml
[mcp_servers.paranoia]
command = "paranoia-local"
args = ["--engine", "claude"]
tool_timeout_sec = 8400
startup_timeout_sec = 60
```

## Tool selection

1. Full code/diff/working-tree review: `critique_branch`.
2. Plan review against code and external premises: `critique_plan`.
3. One factual or analytical question: `query`.
4. Dispute a prior finding using its session: `rebut`.
5. Independent choice between 2–4 explicit options: `arbitrate`.

Do not use `query` when durable convergence is required. Do not use `arbitrate`
as a full code review.

## Shared semantics

- `repo_path`: absolute path.
- `stakes`: concrete deployment, actors, trust, adversary capabilities,
  concurrency, network, scale, latency, false-clear/false-block consequences,
  and exclusions. Avoid vague labels.
- `round`: integer >= 1. After a settled tracked call, use a greater label. A
  failed/rejected call may retry the same label.
- `already_raised`: accepted one-line claims with `file:line`; never previous
  reviewer prose.
- `focus`: optional narrowing; does not replace intent or stakes.
- `engine`: `codex` or `claude` single-reviewer override.
- `model`: provider-specific override.
- `effort`: `low|medium|high`; review default high, `query` default medium.
- `web_search`: default true. Required by enabled plan claim verification.

## `critique_branch`

Required: `repo_path`; also `round` unless `class_closure:false`.

Defaults: `base_ref=main`, `head_ref=HEAD`, `include_uncommitted=false`,
`isolate=true`, `converge=true`, `max_packet_chars=400000`,
`class_closure=true`; lineage is derived when the reviewed head is a branch.

```json
{
  "repo_path": "/absolute/repo",
  "base_ref": "main",
  "round": 1,
  "project_summary": "Neutral system description.",
  "diff_intent": "Exact intended behavior.",
  "stakes": "Concrete operating model and exclusions."
}
```

Dirty review: add `"include_uncommitted":true`. It reads the live repository
because uncommitted bytes cannot be isolated. Reviewer access remains read-only.

One-shot branch review:

```json
{"repo_path":"/absolute/repo","class_closure":false,"converge":false}
```

Never set only one of those false values.

Optional contract arguments: exactly zero or one of `plan_text`, `plan_path`;
optional `plan_digest` requires a plan. `plan_path` must be absolute. Plan-backed
review requires tracked convergence and round 1 for first reservation. The first
accepted contract is immutable for the lineage; any add/remove/change requires a
new lineage. Later calls may omit the plan and reuse stored authority.

Exemption shapes:

```json
{
  "exempt": [{"class_id":"id","path":"src/a.py","line":12,"line_text":"exact text"}],
  "unexempt": [{"class_id":"id","path":"src/a.py","line":12}]
}
```

## `critique_plan`

Required: `repo_path` and exactly one of `plan_text`, `plan_path`. Tracked mode
also requires `lineage` and `round`.

Defaults: `class_closure=true`, `claim_verification=true`, `web_search=true`.

```json
{
  "repo_path": "/absolute/repo",
  "plan_path": "/absolute/repo/docs/plan.md",
  "lineage": "project-issue-42-plan",
  "round": 1,
  "context": "Neutral background.",
  "stakes": "Concrete operating model and exclusions."
}
```

Rules:

- Use a globally unique, mode-qualified lineage; never reuse a branch lineage.
- `.paranoia.toml` does not supply plan `lineage` or `class_closure`.
- `claim_verification:true` with `web_search:false` is invalid.
- `claim_verification:false` is structural-only and preserves dormant claim state.
- One-shot plan: `class_closure:false`; computed convergence is omitted.
- After editing the plan, increment `round` and keep lineage/stakes stable unless
  the real operating model changed.

Eligible external claims are only load-bearing external facts, externally issued
governing requirements/principles, and promised external-system behavior.
Repository facts and local design choices belong to structural review.
The server rejects a claim proposition that introduces an explicit universal
quantifier absent from its verbatim plan wording. A source-capture failure remains
blocking, but is reported as retrieval failure rather than evidence that the plan's
assertion should be weakened or removed. Captured-text binding and cold-attestation
failures retain their own labels and retry instructions. Mixed or partial source failures
render every affected server phase; processing failure alone never justifies editing the
assertion.

## `query`

Required: `question`. Optional: `repo_path`, `files:[{path,reason?}]`, `focus`, and
shared overrides.

```json
{
  "question": "Can this retry path duplicate a payment?",
  "repo_path": "/absolute/repo",
  "files": [{"path":"src/retry.py","reason":"retry owner"}]
}
```

Expected: direct answer, citations, confidence; no tracked lineage. File entries
are hints and do not prevent the reviewer from reading elsewhere.

## `rebut`

Required: `repo_path`, `session_ref`, `rebuttal`.

```json
{
  "repo_path": "/absolute/repo",
  "session_ref": "prior-session-reference",
  "rebuttal": "Counter-evidence with exact citations."
}
```

Expected: `CONCEDE` or `HOLD` with fresh citations.

Optional class-gate reset requires all three: `lineage`, `class_id`,
`lineage_mode` (`branch|plan`). The session must be current for the active
blocking class. Success resets a correction window only; it does not close or
reclassify debt.

## `arbitrate`

Required: `repo_path`, `decision`, `options`, `stakes`.

```json
{
  "repo_path": "/absolute/repo",
  "decision": "Neutral decision statement.",
  "options": [
    {"id":"a","statement":"Self-contained mechanism, scope, and consequences."},
    {"id":"b","statement":"Self-contained mechanism, scope, and consequences."}
  ],
  "stakes": "Concrete operating model and consequences.",
  "context": "Only facts and specification shared by every option.",
  "files": [{"path":"src/relevant.py","reason":"shared evidence"}]
}
```

Bounds: decision 2500 chars; 2–4 options; each statement 1200; context 20000;
stakes 20000; 32 files; each stripped reason 1200.

Defaults: `clean=true`, `cleaner_model=claude-opus-5`,
`retain_snapshot=false`, `research=true`, `web_search=true`, `effort=high`.

Optional: `subject`, `models`, `cleaner_model`, `order_seed`, `retain_snapshot`,
`research`, `effort`, `web_search`.

Rules:

- `context` contains only common facts/specification.
- Each statement contains that option's distinct mechanism, scope,
  qualifications, tradeoffs, and consequences.
- Statements are self-contained and do not refer to sibling IDs.
- `research:true` requires `web_search:true`.
- There is no `engine` or singular `model`.
- `retain_snapshot:true` creates a Git ref. Remove it with
  `git update-ref -d refs/paranoia/arbitrate/<stamp>`.

Results: `CONVERGED`, `BLOCKED`, `REFRAME_REQUIRED`, `UNRESOLVED`, `FAILED`.
Unsubstantiated unanimous agreement is `UNRESOLVED`, has `SELECTED: none`, and
reports the agreed option only as `PROVISIONAL-SELECTED`.
`ADVISORY: human-owner` is non-gating.

## Tracked state machine

```text
new -> census
census clear -> clear
census blocked -> correction
correction blocked -> correction
correction debt closed -> final
final clear -> clear
final blocked -> correction
```

After a tracked result:

1. Read `STRUCTURAL-PHASE`, `STRUCTURAL-DEBT`, `CLASS-CLOSURE`, optional
   `CLAIM-CLOSURE`, and `CONVERGENCE`.
2. Fix validated in-scope debt and transitive effects.
3. Increment `round` only after changing the artifact.
4. Reuse lineage and stakes.
5. Stop only at `CONVERGENCE: NOT-BLOCKED`.

Do not rerun unchanged text hoping model variance removes durable debt. Do not
treat `NOT-BLOCKED` as proof.

## Output parsing

Completed reviews have five sections in order: `What works`, `What doesn't work`,
`Risks`, `Gaps`, `Improvements`.

Code severities: `BLOCKER`, `MAJOR`, `MINOR`, `OUT-OF-SCOPE`. Plan severities:
`FATAL`, `MAJOR`, `MINOR`, `OUT-OF-SCOPE`.

Tracked fields can include `CLASS-REGISTER`, `CLASS-CLOSURE`,
`STRUCTURAL-PHASE`, `STRUCTURAL-DEBT`, `PERSISTENCE`, `REOPEN-WAVE`,
`CORRECTION-GATE`, `STAGED-ATTEMPTS`, `CLAIM-REGISTER`, `CLAIM-CLOSURE`,
`STRUCTURAL-CONVERGENCE`, `CONVERGENCE`, `STRUCTURAL-ERROR`, and
`STRUCTURAL-PENDING`.

Failure rule: `# STAGED REVIEW FAILED` has no durable clean structural verdict.
Never infer success from absent findings. `STATE-UNAVAILABLE` is blocking.

Arbitration always reports `ARBITRATION`, `SELECTED`, `PROVISIONAL-SELECTED`, `ADVISORY`,
`AUTHORITY-POLICY`, `CLEANING`, `SNAPSHOT`, `ORDER-SEED`, `REFS-MOVED`, `AUDIT`,
`ROUNDS`, `RESEARCH`, `RESEARCH-DIGEST`.

## Configuration and state

`.paranoia.toml` can use top-level keys or `[paranoia]`. Precedence: call > repo
config > built-in. Supported keys: `base_ref`, `project_summary`, `stakes`,
`isolate`, `converge`, `class_closure`, `max_packet_chars`, `model`, `effort`,
`web_search`.

- audits: `~/.paranoia/logs/` or `--log-dir`;
- lineages: `~/.paranoia/lineages/` or `PARANOIA_STATE_ROOT`.

`--log-dir` never moves lineage state. Do not edit/delete active lineage files
unless the user explicitly abandons the lineage. Audit logs are not state backup.

## Safety, cost, and recovery

- Reviewer tools cannot edit repository files or run repository tests.
- Committed review may create temporary worktrees and unreferenced Git objects.
- Dirty review reads the live working tree.
- Verified-plan and arbitration evidence trees are inert.
- Local signed-in subscriptions are used; no API key or Paranoia telemetry.
- `retain_snapshot:true` is the only ordinary mode that creates a durable Git ref.
- `query` is cheapest; census uses three lanes plus consolidation; plan
  verification adds evidence calls; `arbitrate` uses both subscriptions.

Recovery:

- Codex MCP timeout: set `tool_timeout_sec=8400`.
- Missing/old CLI: check version, update, and sign in.
- Failed/rejected tracked call: address the diagnostic and retry the same round.
- Settled blocked call: edit, increment round, retry the same lineage.
- Persistence gate: close/replace the class or use the named class-bound rebut.
- `STATE-UNAVAILABLE`: repair or intentionally abandon the diagnosed state path;
  never synthesize convergence from logs.
- Claim evidence failure: follow the phase-specific packet. Retry retrieval,
  captured-text binding, or cold attestation when that server phase failed; do not
  weaken or remove an assertion solely because evidence processing failed. Change
  wording only when authoritative evidence actually refutes or fails to entail it.

## Sources of truth

1. MCP schemas: `src/paranoia_local/server.py`.
2. CLI flags: `src/paranoia_local/cli.py`.
3. Provider versions/models: `src/paranoia_local/engines.py`.
4. Configuration: `src/paranoia_local/config.py`.
5. Human tool reference: `docs/tool-reference.md`.
6. Lifecycle and safety: `docs/how-it-works.md`.
7. Protocol detail: `docs/claim_verification.md`, `docs/arbitration_plan.md`.
