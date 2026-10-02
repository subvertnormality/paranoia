# Paranoia Local tool reference

This page documents the public MCP interface. The runtime schemas in
[`src/paranoia_local/server.py`](../src/paranoia_local/server.py) are authoritative
if this page and an installed version differ.

## Shared review arguments

Claude model quota exhaustion is a failed provider attempt, not a structural
finding. Recognized model-limit diagnostics name an explicit recovery route;
Paranoia never automatically substitutes a model or retries the exhausted one.
Wait for quota recovery, or choose another available Claude model using the model
argument on review/query/rebut calls. For arbitrate's Claude research/decider, use the models
mapping with its claude key; this does not change fixed cleaner/attester models.
For Fable exhaustion, claude-opus-5 is a possible alternative, not a promise of
availability. Model choice remains explicit and audited; no review is cleared by
quota failure or by changing the model.

A recognized Claude safeguard refusal is also a failed provider attempt, never
a finding, decision, or convergence result. Paranoia retains the original
provider channels and names the recovery path without weakening the safeguard:
after the bounded retry, stop replaying the unchanged request; preserve the
audit; then either start a new run with a faithful, neutral restatement that
removes accidental trigger wording or escalate the false positive to provider
support. In `arbitrate`, a `models.claude` override affects Claude research and
decider calls only; it does not select the separate cleaner or attester role.
Changing `cleaner_model` to evade a safeguard is unsupported.

`critique_branch`, `critique_plan`, `query`, and `rebut` accept these overrides:

| Argument | Values | Default |
|---|---|---|
| `engine` | `codex` or `claude` | Server configuration |
| `model` | Provider model name | `gpt-6-astra` or `claude-fable-5-1` |
| `effort` | `low`, `medium`, or `high` | By model: Fable/Astra `medium`, Opus/Sol `high`; otherwise `high` (`query` `medium`) |
| `web_search` | Boolean | `true` |
| `review_model_policy` (`critique_branch`, `critique_plan`) | `tiered` or `strongest` | `tiered` |
| `effort_by_model` (`critique_branch`, `critique_plan`) | Object mapping `astra`, `sol`, `fable`, `opus` to `low`/`medium`/`high` | Release family defaults |

Structural model routing applies only to tracked staged `critique_branch` and
`critique_plan` roles and is resolved after the authoritative durable phase:

| Phase | Codex | Claude | Effort |
|---|---|---|---|
| Census lanes and consolidation | `gpt-6-astra` | `claude-fable-5-1` | medium |
| Correction (`tiered`) | `gpt-6.1-sol` | `claude-opus-5-5` | high |
| Correction (`strongest`) | `gpt-6-astra` | `claude-fable-5-1` | medium |
| Cold final | `gpt-6-astra` | `claude-fable-5-1` | medium |
| Proposal and its validation retry | source review's model | source review's model | source review's effort |

Effort for a routed phase resolves as: that model family's `effort_by_model` entry, then
the global `effort`, then the release family default (Astra/Fable medium, Sol/Opus high).
`effort_by_model` merges per family: an argument key beats the same `.paranoia.toml`
`[effort_by_model]` key, and other configured keys still apply. Unknown families or
values are rejected before any provider call. An explicit `model` pins every structural
phase and is reported as `custom-override`; an effort setting is `custom-override` only
when it changes the cold final's release effort, so `{"sol": "high"}` stays qualified. Claim discovery/binding/attestation,
one-shot review, `query` and `rebut` keep the call-level `model`/`effort`. Model IDs are
release-pinned and passed verbatim; an unsupported model is a visible staged execution
failure, never a silent substitution. On a ChatGPT account, Codex CLI 0.156.1 rejected
`gpt-6.1-sol` (2026-09-29) and 0.159.3 accepted it (2026-10-02); tiered Codex review
needs 0.159.3 or later, or `review_model_policy: "strongest"`.

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
| `propose_patch` | boolean | omitted = automatic | Omitted: request a supplemental unapplied candidate after a blocked census or blocked cold final; `false`: zero proposal calls; `true`: explicit request |
| `prior_proposal_disposition` | object | omitted | Caller accounting for the pending proposal; see [proposal disposition](#proposal-disposition) |

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
- Omitted `propose_patch` proposes only after a blocked census (census lane
  author) or blocked cold final (that final's session). Clean results are
  `NOT-NEEDED`; correction rounds, cached-census reuse, dirty, one-shot and
  closure-disabled reviews render an inert `UNAVAILABLE` reason with no call.
- `propose_patch: true` requires committed tracked review (`converge: true`,
  `class_closure: true`, `include_uncommitted: false`) and a clean caller
  checkout. It never changes the review verdict, durable state, or returned
  convergence trailer. The candidate is validated against pinned blobs but is
  not applied and no tests are run. Stale caller ref/preimages are reported.
- Executing agents inspect every candidate and run their own checks. Pass `false`
  for architectural/authority gaps or an already complete repair.

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
| `propose_patch` | boolean | omitted = automatic | Omitted: request a supplemental unapplied plan-text candidate after a blocked census or blocked cold final; `false`: zero proposal calls; `true`: explicit request |
| `prior_proposal_disposition` | object | omitted | Caller accounting for the pending proposal; see [proposal disposition](#proposal-disposition) |

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
- `propose_patch: true` requires tracked closure. The candidate binds the exact
  captured plan bytes and uses `plan-artifact.md` only as a virtual diff label;
  apply it deliberately to the original buffer or named path. Capture, binding,
  or attestation failures remain evidence-work debt and never authorize a
  factual rewrite.

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

Rebut routing uses explicit server-written successful session observations in
the configured and default audit directories. A known session selects its owner
unless an explicitly supplied engine conflicts. Unknown ownership requires
`engine`; conflicting owners always block before spend. An incomplete audit
scan disables automatic routing, while an explicit engine may proceed unless a
known conflict exists. Routing does not replace durable bound-rebut authority.


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
write; plan anchors may name any strictly parsed in-bounds coordinate in the latest
reviewed plan, including coordinates absent from the original finding. The stored
checkpoint snapshot and line bound govern; a newer unreviewed plan is not rebut
authority. Mechanized
branch classes are refused before provider spend because
their canonical predicate sweep, not a model concession, owns closure.
A conceded debt retains the original finding and a separate durable concession.
For one-off debt with an empty class_ids list, no class_id can provide that binding.
Use unbound rebut with session_ref and rebuttal, omitting all four binding arguments.
Carry the counter-evidence and any concession into the next critique correction's
focus. This route is audit-only: the debt remains open until validated correction
settles it. Zero open classes does not clear blocking one-off debt.
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
| `effort` | `low`, `medium`, or `high` | Per decider model: Fable/Astra `medium`, Opus/Sol `high`, otherwise `medium` | Both deciders' effort |
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
`REASON` names each unsubstantiated engine, its decisive citation, and the failed
substantiation condition. A resolving citation outside gained carried evidence is
distinct from an unresolved repository citation: movers must ground their decisive
reason in the carried evidence, while already-substantiated holders need only a
resolving citation. Supporting citations do not discharge that requirement.

`ADVISORY: human-owner` is informational. `SNAPSHOT` is provenance, not a durable
replay handle, unless `retain_snapshot: true` was used. That option is the only
ordinary Paranoia mode that writes a Git ref.

## Review output

Consolidation consumes canonical lane manifests whose evidence is bare citation
strings. It derives required output citation rationales from validated source
summaries, remedies and evidence, on both initial and validation-retry calls.
Missing rationale objects in that canonical input are not reviewed-artifact defects.

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
Before that transition, the correction materializer copies every current-occurrence anchor
independently authored in the matching violated class outcome into the aggregate finding, in
authored order, and records the extension in the staged audit. Non-debt-bound correction findings
receive the same projection from authored `classification.assessment_evidence` before the server
derives a violated class outcome. Projected anchors remain subject to normal resolution and bounds
validation.
The canonical correction validator also rejects any resulting state with multiple open debts bound
to one active class.

| Trailer field | Meaning |
|---|---|
| `REVIEW-ROUTING` | Routing release (`beta=tiered-review-beta-1`, a stable wire name), policy and its source, and this round's actual phase, tier, model, effort and model source; `custom-override=yes` when a model/effort override pinned it |
| `CLASS-REGISTER` | Class operations applied in this settlement, plus any earlier validation-rejected payload count, discarded-operation warning, and bounded first diagnostic |
| `CLASS-CLOSURE` | Durable open/closed class status |
| `STRUCTURAL-PHASE` | `census`, `correction`, `final`, or `clear` |
| `STRUCTURAL-DEBT` | Blocking governing findings |
| `PERSISTENCE` | A class has remained blocking long enough to need special handling |
| `REOPEN-WAVE` | Previously closed classes reopened |
| `STAGED-ATTEMPTS` | Provider and validation attempt counts |
| `REVIEW-ATTEMPTS` | All claim and structural attempts, including recovered validation retries |
| `CLAIM-REGISTER` | Active and retired external claims, or retained non-adjudicated history after audit failure |
| `CLAIM-CLOSURE` | Supported/refuted/unverified claims, or `AUDIT-FAILED` when no current adjudication completed |
| `FINAL-REGRESSION` | A cold final is required (owning engine named), including after a clean census or for `clear` state without a current acceptance record |
| `BETA-ACCEPTANCE` | On clear: `qualified` or `custom-override (not beta-qualified)`, with the final's engine, model, effort and policy |
| `CONVERGENCE` | Governing tracked result |
| `STATE-UNAVAILABLE` | Lineage state could not be trusted or persisted |

`CONVERGENCE: NOT-BLOCKED` is not a correctness proof.

## Configuration reference

`.paranoia.toml` accepts top-level keys or a `[paranoia]` table. Resolution order
is call argument, repository config, then built-in default.

Supported keys: `base_ref`, `project_summary`, `stakes`, `isolate`, `converge`,
`class_closure`, `max_packet_chars`, `model`, `effort`, `review_model_policy`,
`effort_by_model` (a table), and `web_search`.

```text
paranoia-local --engine {codex|claude} [--log-dir DIR]
```

| Location | Purpose |
|---|---|
| `~/.paranoia/logs/` | One JSON audit record per call |
| `~/.paranoia/lineages/` | Atomic tracked finding, class, phase, and claim state |
| `PARANOIA_STATE_ROOT` | Optional lineage-state root override |

Changing `--log-dir` does not move or reset lineage state.


### Neutral ballot example

Use comparable factual options and a shared decision criterion. Example request arguments (replace the repository path):

```json
{
  "repo_path": "/absolute/path/to/repository",
  "stakes": "One trusted local operator and OS; repository bytes are data, no repository execution or hostile local race. Configuration should become visible within one minute. Recoverable blocking is acceptable; exclude multitenancy and compromised OS.",
  "decision": "Choose the cache lifetime for configuration reads.",
  "options": [
    {"id": "A", "statement": "Reload configuration on every request."},
    {"id": "B", "statement": "Reload configuration once per minute."}
  ],
  "context": "One process; configuration changes at most hourly. Assess freshness, failure recovery and request latency."
}
```

State any measured costs with evidence. Avoid labels such as “safe solution” or “reckless workaround”.
Cleaning makes the smallest faithful edits, preserves substantive asymmetry and
leaves neutral wording unchanged; independent fidelity and advocacy checks remain.

## Proposal disposition

The executing agent SHOULD use the proposed diff as the repair starting point after
inspection and validation. If it departs from the diff, give a concrete reason for
each addressed target handled differently. Both tracked tools accept this optional
closed object on the next round in the same lineage:

```json
{
  "prior_proposal_disposition": {
    "proposal_audit": "<exact PROPOSAL-AUDIT-JSON basename>",
    "status": "applied",
    "departed_targets": {}
  }
}
```

Use the addressed target IDs from the proposal. `applied` requires an empty map;
`departed` requires a reason for every addressed target; `partially-applied` requires
a nonempty proper subset. Reasons are nonblank single lines, at most 500 characters,
without controls. Unknown keys/targets, mismatched proposal basenames, absent or
historical receipts and one-shot input reject before provider spend. `proposal_audit`
is the basename, not a path. Omission with a pending receipt reports `none-recorded`.

The `PROPOSAL-DISPOSITION:` trailer contains the status and escaped canonical JSON
with the exact receipt and reason map also stored as `proposal_disposition` in the
main audit. A receipt identifies the issuing round, full structural snapshot and
patch digests, audit basename and ordered addressed IDs. A successful next round
consumes its pending status, including a forward round jump; failed rounds retain
it for retry. Only a validated proposed/partial candidate with a successful
supplemental audit and receipt save creates a new receipt. Other statuses do not.
No pending receipt means no accounting line and a null audit field. Disposition is
the caller's declaration: it never changes reviewer prompts, debt or clearance.
