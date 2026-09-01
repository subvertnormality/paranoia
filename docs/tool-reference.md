# Paranoia Local tool reference

This page documents the public MCP interface. The runtime schemas in
[`src/paranoia_local/server.py`](../src/paranoia_local/server.py) are authoritative
if this page and an installed version differ.

## Shared review arguments

`critique_branch`, `critique_plan`, `query`, and `rebut` accept these overrides:

| Argument | Values | Default |
|---|---|---|
| `engine` | `codex` or `claude` | Server configuration |
| `model` | Provider model name | `gpt-5.6-sol` or `claude-fable-5` |
| `effort` | `low`, `medium`, or `high` | `high`; `query` uses `medium` |
| `web_search` | Boolean | `true` |

`engine` names the reviewer. `arbitrate` has no single `engine` or `model`
argument because it always uses both vendors.

## `critique_branch`

Reviews a committed Git range or the dirty working tree. The tracked path is the
default and returns cited findings plus a computed convergence trailer.

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | Required | Absolute Git repository path |
| `base_ref` | string | `main` or config | Diff base |
| `head_ref` | string | `HEAD` | Diff head |
| `round` | integer ≥ 1 | Required unless `class_closure: false` | Increase after every settled tracked round |
| `include_uncommitted` | boolean | `false` | Review working-tree changes against `HEAD` in the live repository |
| `isolate` | boolean | `true` | Use a temporary worktree for committed review; ignored for dirty review |
| `converge` | boolean | `true` | Use the immutable-packet tracked review path |
| `max_packet_chars` | integer | `400000` | Tracked packet budget; file evidence may be trimmed, but `already_raised` is retained |
| `plan_text` | string | — | Optional frozen implementation contract; mutually exclusive with `plan_path` |
| `plan_path` | string | — | Absolute path to the optional contract; mutually exclusive with `plan_text` |
| `plan_digest` | string | — | Optional 16-hex frozen digest or full 64-hex SHA-256 assertion; requires a plan |
| `project_summary` | string | — | Neutral project description |
| `diff_intent` | string | — | Intended result, treated as a claim to verify |
| `focus` | string | — | Optional review focus |
| `stakes` | string | Modest internal-tool assumptions | Deployment, trust boundary, scale, and consequences |
| `already_raised` | string array | `[]` | Accepted one-line `file:line` findings from earlier rounds |
| `class_closure` | boolean | `true` | Track findings/classes and compute convergence |
| `lineage` | string | Derived | Explicit key; required for a detached head or raw commit |
| `exempt` | object array | `[]` | Exempt exact `{class_id,path,line,line_text}` predicate matches |
| `unexempt` | object array | `[]` | Revoke exact `{class_id,path,line}` exemptions |

Rules:

- Pair `converge: false` with `class_closure: false` for a one-shot branch review.
- A dirty review cannot use a temporary worktree.
- A plan-bearing branch review requires tracked convergence and `round: 1` for
  the first contract reservation.
- `plan_path` is resolved and read once. Its captured text and server-computed
  digest are frozen for the lineage.
- Later rounds may omit the plan input. Adding, removing, or changing the
  contract requires a new lineage.
- A contract is declarative requirements data, not reviewer instructions.
- Lost or ambiguous substantive lineage state blocks with `STATE-UNAVAILABLE`.

Example:

```json
{
  "repo_path": "/repo",
  "base_ref": "main",
  "round": 1,
  "diff_intent": "Reject withdrawals that exceed available funds.",
  "stakes": "Internal API; authenticated callers; one region; 1,000 requests/minute."
}
```

## `critique_plan`

Reviews a plan against the repository it describes. External claim verification
runs before structural review by default.

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | Required | Absolute relevant repository path |
| `plan_text` | string | Exactly one plan input required | Plan Markdown |
| `plan_path` | string | Exactly one plan input required | Absolute path to plan Markdown |
| `round` | integer ≥ 1 | Required unless `class_closure: false` | Caller round label |
| `lineage` | string | Required unless `class_closure: false` | Globally unique, mode-qualified durable key |
| `class_closure` | boolean | `true` | Track procedural plan classes and compute convergence |
| `claim_verification` | boolean | `true` | Verify eligible external premises before structural review |
| `context` | string | — | Background needed to judge the plan |
| `focus` | string | — | Optional review focus |
| `stakes` | string | Modest internal-tool assumptions | Scope and consequence boundary |
| `already_raised` | string array | `[]` | Accepted cited findings from earlier rounds |

Rules:

- Provide exactly one of `plan_text` and `plan_path`.
- Use a unique, mode-qualified lineage such as `project-issue-42-plan`. A plan
  lineage cannot be shared with branch review.
- `lineage` and `class_closure` are call-only values; `.paranoia.toml` does not
  supply them for plan reviews.
- `claim_verification: true` requires `web_search: true` on bundled engines.
- The external claim register excludes repository facts, code paths, internal
  conformance, and local design choices.
- One-shot plan review uses `class_closure: false`. It returns review prose and
  claim packets but no computed convergence verdict.

```json
{
  "repo_path": "/repo",
  "plan_path": "/repo/docs/change-plan.md",
  "lineage": "project-issue-42-plan",
  "round": 1,
  "stakes": "Single-team service; trusted operators; authenticated public requests."
}
```

## `query`

Asks one focused question without creating a tracked review.

| Argument | Type | Default | Description |
|---|---|---|---|
| `question` | string | Required | Specific question |
| `repo_path` | string | — | Optional repository grounding |
| `files` | object array | `[]` | `{path, reason?}` starting hints; the reviewer may read elsewhere |
| `focus` | string | — | Additional framing |

The response is a direct answer with citations and a stated confidence level.

## `rebut`

Resumes the reviewer session that produced a disputed finding.

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | Required | Same repository used for the review |
| `session_ref` | string | Required | Session reference from the review footer |
| `rebuttal` | string | Required | Concrete counter-evidence |
| `lineage` | string | — | Optional gated lineage; requires all other binding values |
| `class_id` | string | — | Optional active blocking class |
| `debt_id` | string | — | Optional exact open debt bound only to `class_id` |
| `lineage_mode` | `plan` or `branch` | — | Optional lineage mode |

The unbound form returns prose `CONCEDE` or `HOLD` with fresh citations and does
not mutate lineage state. The four class-binding arguments are all-or-none. A
bound response is closed structured output: `HOLD` is audit-only; `CONCEDE`
closes only the named debt and closes the class only when no sibling blocker
remains. It never grants convergence. The session must be the durable current
session for the active blocking class, and ambiguous or invalid state refuses
settlement. Bound citations use the staged anchor grammar and resolve before any
write; plan anchors also require the retained reviewed-plan line bound. Mechanized
branch classes are refused before provider spend because
their canonical predicate sweep, not a model concession, owns closure.
A conceded debt retains the original finding and a separate durable concession.
Later staged decisions must submit a keyed, evidence-backed challenge before they
can target that class again; an unrelated snapshot or stakes change does not erase
the concession.

## `arbitrate`

Asks Codex and Claude to decide independently between two to four options over
the same pinned evidence. Python computes the outcome.

| Argument | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | Required | Repository whose snapshot supplies context |
| `decision` | string, max 2,500 chars | Required | Neutral question and relevant properties |
| `options` | 2–4 objects | Required | Unique `{id, statement}` options; statement max 1,200 chars |
| `stakes` | string, max 20,000 chars | Required | Scope and consequence boundary; use `unstated` deliberately if needed |
| `context` | string, max 20,000 chars | — | Facts and specification shared by every option |
| `files` | object array, max 32 | `[]` | Snapshot-relative `{path, reason?}` hints; reason max 1,200 chars |
| `subject` | string | — | Short label for the record |
| `clean` | boolean | `true` | Neutralize framing with Claude Opus and cross-vendor attestation |
| `models` | object | Provider defaults | Optional `{codex, claude}` model overrides |
| `cleaner_model` | string | `claude-opus-5` | Cleaner override |
| `order_seed` | string | Generated | Reproduce labels and ordering from an earlier run |
| `retain_snapshot` | boolean | `false` | Create `refs/paranoia/arbitrate/<stamp>` to survive Git GC |
| `research` | boolean | `true` | Discover and server-capture shared authoritative web evidence |
| `effort` | `low`, `medium`, or `high` | `high` | Both deciders' effort |
| `web_search` | boolean | `true` | Discovery authorization; required by `research: true` |

Input design is load-bearing:

- Put only shared facts and specification in `context`.
- Put each option's unique mechanism, scope, qualifications, consequences, and
  tradeoffs in its own self-contained statement.
- Do not refer to another option by ID inside a statement. Deciders see different
  opaque labels and counterbalanced orders.
- Keep file hints balanced; both deciders receive the same list.
- Caller `context` and `stakes` remain byte-for-byte authoritative and are
  checked for advocacy.

Processing sequence:

1. Pin a Git snapshot and materialize inert evidence for each decider.
2. Clean and cross-attest framing unless `clean: false`.
3. With `research: true`, let both vendors discover URLs, then capture and bind
   the sources server-side.
4. Give both deciders identical evidence with live web disabled and
   counterbalanced presentation.
5. Resolve citations and compute the result in Python.
6. On divergence, run one fact-only reconciliation only when new evidence exists.

| Outcome | Meaning |
|---|---|
| `CONVERGED` | Unanimous, unblocked, and substantiated by resolved evidence |
| `BLOCKED` | Same option, but at least one decider marks it major/fatal |
| `REFRAME_REQUIRED` | A decider found a better unlisted option; add it and rerun |
| `UNRESOLVED` | Split decision or unsubstantiated agreement |
| `FAILED` | Preflight, execution, cleaning, capture, parsing, or protocol failure |

The trailer always includes `ARBITRATION`, `SELECTED`, `PROVISIONAL-SELECTED`, `ADVISORY`,
`AUTHORITY-POLICY`, `CLEANING`, `SNAPSHOT`, `ORDER-SEED`, `REFS-MOVED`, `AUDIT`,
`ROUNDS`, `RESEARCH`, and `RESEARCH-DIGEST`.

`CLEANING: caller-framing-rejected` means the terminal verdict found advocacy in
unchanged caller-owned context or stakes; a closed `{field, passage}` diagnostic
is validated against the exact caller text and the failure names what the caller
must restate. Original-neutrality evidence from cleaner-owned decision, option,
or hint fields only disables fallback and is retained separately. A terminal
fidelity, cleaned-neutrality, or candidate-shape rejection is `cleaner-rejected`;
malformed or oversized attester output is `attestation-rejected`.
Paranoia may discard a meaning-changing cleaner candidate and safely use an
independently attested neutral original, but never sends the changed candidate to
the deciders.

When the final votes are unanimous but not substantiated, the result remains
`UNRESOLVED`: `SELECTED` is `none`, while `PROVISIONAL-SELECTED` reports the
common option as non-binding diagnostic information.

`ADVISORY: human-owner` is informational. `SNAPSHOT` is provenance, not a durable
replay handle, unless `retain_snapshot: true` was used. That option is the only
ordinary Paranoia mode that writes a Git ref.

## Review output

A completed review uses these headings in order: `What works`, `What doesn't
work`, `Risks`, `Gaps`, and `Improvements`.

Code findings use `[BLOCKER]`, `[MAJOR]`, `[MINOR]`, or `[OUT-OF-SCOPE]`. Plan
findings use `[FATAL]`, `[MAJOR]`, `[MINOR]`, or `[OUT-OF-SCOPE]`. Tracked
recurrences include `[RECURRENCE <class-id>]`.

A terminal staged failure begins `# STAGED REVIEW FAILED`, contains a bounded
diagnostic, and never implies that missing findings mean success.

Tracked plan correction uses a broader closure-candidate search when the round
starts with one or two active blocking-class/unbound-debt units. The task packet
includes the complete checklist, but settlement remains correction: clearing its
debt advances to the independent `final` phase, never directly to `clear`.
Tracked branch correction and all final prompts retain their existing scope.
This is a convergence-efficiency heuristic, not a fixed-round guarantee.

In both plan and branch correction, independently anchored occurrences of one active class are
reported together as one governing finding whose evidence and remedy cover every site. The server
still permits only one finding and outcome per class in a settlement. A fresh occurrence may mint
a fresh debt ID; correction gates prevent rewording the same site from satisfying a blocking class.
For each unmechanized class being assessed, the durable invariant and procedure define the search
scope. The reviewer must enumerate and inspect every site/property category they name, explicitly
account for empty or inapplicable categories, and cannot close the class merely because all anchors
from its current debt were repaired. Mechanized classes remain bounded by the server-run predicate.
An outcome-optional unmechanized class may still use a standalone correction `close`, but only with
an authored `satisfied` outcome and evidence; a bare close is validation-invalid.
A fresh aggregate finding must close the class's prior open debt after incorporating every
still-reachable predecessor occurrence, so one class does not accumulate duplicate blockers.
Before that transition, the correction materializer requires the finding to contain every
current-occurrence anchor independently authored in its matching violated class outcome and reports
an omission at the governing finding's evidence pointer through the bounded validation retry.
Non-debt-bound correction findings pass the same check against their authored
`classification.assessment_evidence` before the server derives a violated class outcome.
The canonical correction validator also rejects any resulting state with multiple open debts bound
to one active class.

| Trailer field | Meaning |
|---|---|
| `CLASS-REGISTER` | Class operations applied in this settlement |
| `CLASS-CLOSURE` | Durable open/closed class status |
| `STRUCTURAL-PHASE` | `census`, `correction`, `final`, or `clear` |
| `STRUCTURAL-DEBT` | Blocking governing findings |
| `PERSISTENCE` | A class has remained blocking long enough to need special handling |
| `REOPEN-WAVE` | Previously closed classes reopened |
| `STAGED-ATTEMPTS` | Provider and validation attempt counts |
| `REVIEW-ATTEMPTS` | All claim and structural attempts, including recovered validation retries |
| `CLAIM-REGISTER` | Active and retired external claims, or retained non-adjudicated history after audit failure |
| `CLAIM-CLOSURE` | Supported/refuted/unverified claims, or `AUDIT-FAILED` when no current adjudication completed |
| `CONVERGENCE` | Governing tracked result |
| `STATE-UNAVAILABLE` | Lineage state could not be trusted or persisted |

`CONVERGENCE: NOT-BLOCKED` is not a correctness proof.

## Configuration reference

`.paranoia.toml` accepts top-level keys or a `[paranoia]` table. Resolution order
is call argument, repository config, then built-in default.

Supported keys: `base_ref`, `project_summary`, `stakes`, `isolate`, `converge`,
`class_closure`, `max_packet_chars`, `model`, `effort`, and `web_search`.

```text
paranoia-local --engine {codex|claude} [--log-dir DIR]
```

| Location | Purpose |
|---|---|
| `~/.paranoia/logs/` | One JSON audit record per call |
| `~/.paranoia/lineages/` | Atomic tracked finding, class, phase, and claim state |
| `PARANOIA_STATE_ROOT` | Optional lineage-state root override |

Changing `--log-dir` does not move or reset lineage state.
