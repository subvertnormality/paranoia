# Beta: phase-based review models and default repair proposals

> **Status (2026-10-02):** historical design record. The behavior specified here is the
> default on main, promoted by PR #140; the `tiered-review-beta-1` release name and
> `BETA-ACCEPTANCE` field remain as stable wire names. Current usage is documented in the
> [README](../README.md#tracked-reviews), [How Paranoia works](how-it-works.md#the-tracked-lifecycle)
> and the [tool reference](tool-reference.md). Later fixes: main's #131–133 changes were
> merged in (#137); caller proposal disposition (#138,
> [plan](proposal-disposition-138-plan.md)); Git LFS proposal cleanliness (#139,
> [plan](lfs-proposal-cleanliness-139-plan.md)). On a ChatGPT account Codex CLI 0.159.3
> accepted `gpt-6.1-sol` on 2026-10-02 (0.156.1 rejected it, as recorded below). The text
> below is unchanged.

2026-09-29 model-pin amendment: targeted Codex correction uses `gpt-6.1-sol`
at the existing high effort. Astra census/final routing is unchanged. The retained
2026-09-23 qualification records describe the previous Sol pin and remain historical.
Validation: 107 beta-routing and engine tests passed. A minimal live call on
2026-09-29 with Codex CLI 0.156.1 and the local ChatGPT account rejected
`gpt-6.1-sol` as unsupported; native Sol 6.1 usability is not established.
Tiered correction remains fail-closed until the CLI/account offers that model.

Status: implemented on this branch with deterministic public-handler tests
(`tests/test_beta_tiered_review.py`); see §10 for the bounded implementation decisions that
close gaps found while grounding this contract in code. CODE convergence reached
`NOT-BLOCKED` with a qualified cold final. Native qualification
([`beta-tiered-review-qualification.md`](beta-tiered-review-qualification.md)) qualified
three of four fixtures; `plan-codex` failed at the six-invocation ceiling, so readiness is
BLOCKED and the version stays `0.1.0`. §7 step 1 (PLAN review of this contract) was not
run before implementation.
User decision: default-on beta, 2026-09-23.
Branch: `codex/beta-tiered-review`.
Baseline: `bdeb5d16a2614bf2e488493a75088fabc67b754f` on main.
No native review, release, installation, publication or merge has occurred.

## 1. Product decisions

Ship an explicitly labelled beta on this branch. Supported tracked branch and plan
reviews use the selected provider's strongest model for census and independent cold
acceptance, and Sol / Opus 5.5 for targeted structural corrections. Automatically
request repairs after eligible blocked census and cold-final reviews. The author
inspects candidates, implements or adapts them, and runs appropriate checks.
Paranoia never applies a proposal or treats one as proof of repair.

| Phase | Codex | Claude | Automatic proposal |
| --- | --- | --- | --- |
| Census lanes and consolidation | gpt-6-astra | claude-fable-5-1 | After eligible blocked settlement |
| Structural correction | gpt-6.1-sol | claude-opus-5-5 | No additional proposal call |
| Independent cold final | gpt-6-astra | claude-fable-5-1 | After eligible blocked settlement |
| Proposal and validation retry | Source review's actual model | Source review's actual model | One attempt plus existing single validation retry |

Defaults are release-pinned, not automatically resolved to "latest". Preserve current
family effort defaults: Astra/Fable medium, Sol/Opus high, unless overridden. Validate
actual CLI capabilities; never silently substitute models. Only the selected provider
runs; this does not introduce dual-provider review per round.

Default on means no activation flags for eligible proposals and phase routing.
It does not mean patch application, proposals on clean results, or proposal calls
on every correction. Explicit opt-outs remain. A blocked cold final can propose
repairs only after its verdict is settled; the next path is correction followed by
a fresh strongest-model cold final. A clean review has no repair to propose.

## 2. Frozen operating model

Existing single-user local MCP server and reviewer CLIs; trusted operator, OS, Git
and server. Repository files, plans, fetched content and provider replies are
untrusted static data. No hostile same-user races, compromised OS, multi-tenancy,
or deliberately corrupted state recovery. Ordinary edits invalidate suitability or
require a new reviewed snapshot. Keep existing census concurrency and lineage latch;
proposals run serially after settlement while the pinned workspace is available.

Expected scale: tens to low hundreds of claims/findings across tens to thousands
of files; evidence useful within minutes per stage. Keep generous existing call
timeouts. Repeated 20-plus-round repair loops require architectural triage rather
than normalization. False clearance and wrong authority/evidence binding have high
impact; recoverable blocking and unavailable proposals are acceptable.

No added network permissions or repository-selected code execution by reviewers
or proposal authors. Author-side checks remain ordinary implementation work.
Preserve capture/binding/cold-attestation rules and budgets.

Non-goals: automatic patch application, extra review lanes, cross-provider session
transfer, weaker schemas or closure rules, new persistence infrastructure, shortened
timeouts, a large paired campaign, stable rollout, or a claim of unchanged quality
or proven savings. Query, rebut and arbitration defaults are outside phase routing.

## 3. Routing and configuration

Add one shared phase-policy resolver for public `critique_branch` and
`critique_plan`. Resolve the model after authoritative phase selection under the
existing latch. Round labels, caller prose or omitted submitted debt cannot select
the cheaper phase. All census lanes and consolidation use the strongest tier.
Validation retries retain their originating role, model, effort and session.

Add `review_model_policy: "tiered" | "strongest"`, defaulting to `"tiered"` in
this beta. Strongest uses the provider's strongest default for all structural phases.
Precedence is explicit argument, repository config, release default. An existing
explicit `model`, including repository configuration, continues to pin structural
review models and visibly overrides the policy. Label such runs as custom overrides:
a medium-pinned final cannot advertise strongest-model beta qualification. Resolve
effort against the actual selected model; explicit effort continues to win.

Keep claim-role model selection separate. Discovery, binding and cold attestation
retain existing strongest/default or explicit model behavior; routing a structural
correction must not downgrade external claim adjudication. Proposals use their
source review's actual model and effort.

Omitted `propose_patch` means automatic eligibility selection; false makes zero
proposal calls; true remains an explicit request. Preserve existing explicit-true
unsupported-mode preflight rejection. Omission must not turn valid dirty, one-shot,
or closure-disabled reviews into eligibility errors: run the ordinary review and
show an inert UNAVAILABLE reason. Do not coerce omission to true before preserving
request origin. MCP schemas must not insert a boolean default that destroys this
distinction. Correction-phase requests are phase-ineligible with no proposal call.

No blocking target means NOT-NEEDED; unsupported/unrepairable or unavailable work
means UNAVAILABLE. Retain current claim-verification-specific distinctions.
Nontracked paths retain their ordinary scope and cannot advertise beta convergence.

Model/policy changes never reset history, erase failed rounds or debt IDs, or change
the provider owning a pending final. Extend existing versioned state and audit only
as needed; retain existing atomic storage. Bind actual models and policy to attempts,
cache admission and final obligations. Incompatible model/prompt/policy cache entries
cannot suppress fresh review.

## 4. Independent cold acceptance

Every beta tracked acceptance requires a successful strongest-model cold final on
the exact current snapshot after census/correction obligations are satisfied.
This deliberately changes clean-census shortcuts: a clean census needs neither
proposal nor correction, but still advances to final. Include this added cost in
evaluation; it is a product gate, not an extra benchmark-only call.

Audit all clear transitions in `review_transitions.py`, `review_census.py` and
handlers: class-only and claim-only routes, plan closure-candidate correction, rebut
effects, state migration and same-snapshot reuse. No medium correction or legacy
clear record can grant beta qualification. Exact unchanged already-beta-qualified
snapshots may retain valid reuse. Existing failed lineages retain failures and debt.
Legacy clear remains historical and requires a beta final before new qualification;
never restart a lineage to gain clearance.

Final uses a fresh session, never a correction or proposal continuation. Supply the
complete current artifact, exact captured plan contract when present, full required
checklist and relevant class/debt context. Resolved labels do not prove an invariant.
Do not present proposal text as the acceptance specification or restrict coverage
to edited lines.

Supply closed-during-this-lineage class invariants and closure evidence as historical
context alongside active classes. Recheck those invariants against current bytes.
Keep historical context distinct from required active-class outcome keys. Violations
use existing evidenced reopen/replacement semantics; do not reactivate every class,
invent IDs, or alter mechanized/unmechanized policy just to provide context.
Acceptance must test a false correction closure detected after a class became closed.

Retain invariant-wide correction checks, stable members, transitive effects, plan
closure-candidate coverage and predicate sweeps. Structural final success cannot
clear failed/unresolved claims. Missing or ambiguous state, failed calls and
unconfirmed persistence remain blocking. A pending final binds owning provider and
required model/policy; strongest unavailability never causes a cheaper fallback.

## 5. Proposal extension and default-on repair

Keep existing census author selection. Add a successful final-review author handle
and select it only for that final's durably settled current targets. Never propose
against a new final snapshot by resuming an old census session. Missing author or
unsupported continuation produces UNAVAILABLE, not a new cold proposal investigation.

Use the existing proposal role/transport and bounded single validation retry.
Preserve review/proposal provenance, including same-handle returns. Proposal-only
sessions never become rebut authority; independent completed critique/query authority
remains intact. Validate final-source continuation on both native providers.

Retain exact captured bytes and pinned preimages, inert Git reads, raw checkout
cleanliness before/after dispatch, portable paths, complete collision inventory,
aggregate retry-surviving source allowance, stale/ignored destination checks and
no-op rejection. Keep current exclusions for architecture/authority gaps and
unadjudicated factual rewrites. Declining a repair is valid.

Settle first, propose second. Every supplemental preparation/provider/validation/
logging/render failure returns the original review and exact trailer with bounded
UNAVAILABLE diagnostics. Retain every completed attempt and rejected reply, including
retry-preparation failures. Proposals cannot change class, structural or claim state.
Keep requested/returned session telemetry exclusions when a receipt is missing.
Reserve supplemental time without reducing full primary review reserves; insufficient
headroom skips proposals, never load-bearing evidence.

## 6. Checkpoints and observability

Preserve existing correction/reopen limits and architectural checkpoints. Recurring
classes, late architectural findings, two ineffective fix cycles or exceeded scope
require triage, not endless cheaper rounds. Use strongest review when an explicitly
resolved checkpoint calls for architectural reassessment; do not silently add calls
or expand scope.

Expose beta version, actual phase/model/effort, requested policy and override source,
proposal status, pending final requirement and existing convergence/class/claim
trailers. Record actual per-attempt models for retries and proposals. Missing usage
remains unknown; API-equivalent estimates are not subscription charges. No new
telemetry service or rewritten historical evidence.

## 7. Implementation sequence

1. PLAN-review this contract under the frozen stakes before implementation. Update
   its existing lineage through repairs; avoid open-ended convergence.
2. Add the small shared resolver and public configuration/schema changes in
   `server.py`, `config.py`, `engines.py` and `handlers.py`.
3. Update `review_transitions.py`, `review_census.py`, state normalization and
   staged prompts for independent beta finals and closed-class context.
4. Extend `_select_proposal_author`, `_staged_structural_review`,
   `_run_patch_proposal` and public preflight; reuse `patch_proposals.py`,
   `census_execution.py` and session routing. No broad handlers refactor.
5. Add public-handler lifecycle/failure tests and run the full regression suite.
6. Update README, tool reference, config examples, llms.txt and AGENTS.md to actual
   beta behavior. Preserve historical proposal contracts/results unchanged.
7. Run bounded native qualification and broad strongest-model CODE convergence
   with this exact plan bound to the code branch. After coding starts, review CODE.
8. Produce a beta readiness record and prerelease version after gates pass. Keep
   the result on this branch; publish/install/merge/promotion are separate actions.

## 8. Acceptance and bounded spend

Deterministic tests drive public handlers through canonical engine settlement and
state reload, not just resolver outputs:

- Both modes/providers: blocked census/proposal, authored repair, medium correction,
  strongest final; clean census/final; blocked final/proposal/correction/fresh final;
  wrong repair remains blocked.
- Omission/false/true across supported and unsupported modes, no blockers, missing
  authors and checkpoints. Compare exact original review/trailer and durable state
  with proposal generation enabled versus disabled.
- Authoritative routing, explicit model/effort/policy overrides, cache invalidation,
  same-model retries and unavailable strongest capability.
- False correction closure, closed-class violation and out-of-edit-cone regression;
  no legacy, claim-only, rebut or persistence-failure shortcut to beta qualification.
- Unchanged claim capture/admission/attestation on structural corrections; proposal
  wording cannot replace evidence or weaken original obligations.
- Final-source sessions and rebut authority, decline, stale/no-op patches and all
  existing supplemental failure-containment requirements.
- Runtime schemas, docs, package metadata and beta notices agree.

Freeze four small native end-to-end fixtures on the exact candidate source: one
branch and one verified plan per provider. Each exercises an actual initial proposal,
author inspection/checks, medium correction and strongest cold final. Across these
fixtures exercise blocked-final proposals for both providers and a misleading or
declined candidate. Keep hidden correctness expectations outside reviewer workspaces
and reuse existing custody helpers; deterministic tests cover the exhaustive matrix.

Allow at most six public review invocations per fixture with existing bounded
validation retries. At the ceiling, report failure and block readiness; do not
resample until success. Preserve every attempt if repaired source is requalified.
Record source identity, snapshots, actual role/model/effort, retries, proposals,
wrong closures, cold reopenings, elapsed time, available usage and artifact checks.
Native CLI/schema failures block the advertised route; never substitute prose or
fake-backed success. Qualification establishes routing and usability, not statistical
quality equivalence.

Run focused tests, the full suite and strongest-model CODE convergence. Retain failed
histories and apply architecture checkpoints. This beta uses current native usability
and code convergence instead of the previously declined large paired campaign.
That is a new beta delivery gate, not retroactive qualification of default-on behavior
by historical opt-in results.

## 9. Release and evaluation

First qualified prerelease version: `0.2.0b1`, visibly experimental in startup/tool
output and docs, default-on without activation flags. Stable main keeps existing
behavior until a separate promotion. Planning commits say planned, not implemented.

Operational opt-out: strongest policy plus explicit proposal false, retaining state.
Before returning to an older binary, establish state compatibility; unknown newer
state fails visibly. Never delete lineage state to make rollback work.

Measure total work to independently accepted code, including proposals, author checks,
retries, cold reopenings and the added final after a clean census. Savings and unchanged
quality remain hypotheses. Report observations and unknowns, not campaign-proven
benefits. Stable promotion requires a separate decision informed by beta defects,
native usability, observed cost and human assessment of resulting code.

## 10. Bounded implementation decisions (grounding review, 2026-09-23)

These decisions close gaps found by reading the baseline code. They narrow §3–§6; they do
not add scope.

1. **Two model resolutions.** Handlers keep resolving the call-level `model`/`effort` exactly
   as before; that value continues to drive claim discovery, binding and attestation,
   one-shot review, and rebut/query. Structural staged roles resolve a separate model
   inside `_staged_structural_review` *after* `transitions.incoming` has chosen the
   authoritative phase. An explicit `model` (argument or `.paranoia.toml`) pins every
   structural phase and marks the run `custom-override`; effort follows decision 7.
2. **Pinned model IDs.** Codex correction: `gpt-6.1-sol`; Claude correction:
   `claude-opus-5-5`. Census and final use each engine's existing `default_model`.
   The arbitration cleaner (`claude-opus-5`) is out of scope and unchanged. There is no
   pre-flight model probe; the model is passed verbatim with `--model`, and a CLI
   rejection is an ordinary staged execution failure that blocks visibly. No substitute
   model is ever tried. Observed 2026-09-23: Codex CLI 0.153.3 on a ChatGPT account is
   not offered `gpt-6-sol` ("model is not supported when using Codex with a ChatGPT
   account") and the correction round failed visibly as designed; 0.156.1 (and the
   0.155 desktop build) is offered it. Tiered Codex routing therefore needs a current
   Codex CLI/account offering the current pin; the observations above qualify only
   the previous `gpt-6-sol` pin, not Sol 6.1. Otherwise update the CLI or use
   `review_model_policy: "strongest"`.
3. **Cached census reuse.** When validated lanes are reused after a consolidation
   rejection, no fresh author session exists; the automatic proposal reports
   `UNAVAILABLE` with that reason. The author handle is not persisted in the cache.
4. **Rebut.** Rebut keeps its own model resolution (outside phase routing). It resumes the
   stored correction session with the call-level model, as today.
5. **Beta acceptance marker.** A new closed `acceptance` record in versioned review state
   is written only when a cold final settles to `clear`. It binds release, engine, model,
   effort, policy, override flag and snapshot. `NOT-BLOCKED` renders only for `clear`
   with a marker bound to the current snapshot; `clear` without one (legacy clear, the
   claim-only migration) renders `FINAL-REGRESSION: required`. Any later review of a
   same-snapshot `clear` state, accepted or not, runs one fresh cold final owned by the
   current engine; this beta implements no zero-call reuse of an accepted snapshot (§4
   permits but does not require it). Leaving `clear` drops the marker. A clean census now
   transitions to a final owned by the census engine.
6. **Closed-class history.** Closed (non-superseded) classes are already "active" and
   already require a final outcome. The final additionally receives a separate,
   bounded `closed_class_history` context carrying the closed debt that discharged each
   such class; it is not an outcome key.
7. **Per model-family effort (user direction, 2026-09-23).** `effort_by_model` maps the
   `MODEL_FAMILY_EFFORT` families (`astra`, `sol`, `fable`, `opus`) to an effort for routed
   structural phases, as an argument or a `.paranoia.toml` table merged per family
   (argument wins). Precedence for a phase's model: family entry, then global `effort`,
   then release family default. `custom_override` means the cold final departs from the
   release model or release effort; correction-only effort settings stay qualified.
8. **Historical acceptance provenance.** Retained acceptance records bind later source
   changes through exact `allowed_later_source_diffs` hashes. For files this beta changes,
   only the `sha256`/`scope` (and, where present, `additions`/`deletions`) of *existing*
   entries are refreshed, each scope gaining one explicit "Beta tiered review allowance"
   note; no entry is added or removed and no recorded provider evidence changes. The
   capture record's existing `allowed_later_review_census_diff` joins the issue 117 set of
   metadata-mutable entries in `tests/test_issue115_history.py` and `tests/test_issue117.py`.
   The startup notice lives in `server.run_stdio` so `cli.py` stays byte-identical. The
   class-occurrence replay keeps its pre-beta protocol (`propose_patch: false`) and strips
   only the new `REVIEW-ROUTING` line before exact comparison; the effectiveness custody
   helper ignores supplemental `*_patch_proposal` audits, which historical runs lack.
