# Reviewer-authored patch proposals: assessment and implementation plan

Status: proposed implementation contract; PLAN rounds 1-4 completed BLOCKED and this revision
addresses round 4's retained experiment-timing finding; not yet accepted or implemented.
Baseline inspected: main at 2e23bd2ed17f9d10c2b07b0e7386738d1afbd254.
User decision: the reviewer proposes and returns a patch; Paranoia does not apply it.
This document authorizes no implementation, live campaign, PR, merge, or installation by itself.
An executor asked to implement this plan should follow the gates below in order.

## 1. Objective and decisions already made

Reuse the investigation context of the reviewer to produce an actionable repair, reducing
caller reconstruction and faulty translations of findings into edits. Measure the entire
repair-to-accepted-result workflow, not just the number of review rounds.

The delivered feature proposes a patch by default after an eligible successfully settled tracked
branch or plan review. Branch proposals edit repository text; plan proposals edit the reviewed
plan text. Neither is applied by Paranoia.
Review first, settle the existing verdict, then propose. Never let a promised or syntactically
valid repair close debt. The caller decides whether and how to apply the patch. Normal tracked
correction and cold-final gates subsequently review the actual changed snapshot.

The initial implementation uses one resumed investigating session per proposal, with at most
one same-session output-validation retry. It adds no substantive review lane, changes no
existing review prompt/schema, and does not add a patch-writing requirement to every finding.
During qualification the candidate is explicitly enabled in the experiment only. After the delivery
gates pass, patch generation defaults to true, with an explicit opt-out. It is not a condition
for completing a review.

Non-goals: autonomous application, commits, test execution by the proposal agent, automatic
installation, multi-agent patch merging, a repair queue, patch generation
from legacy one-shot reviews, automatic retry until a patch works, changing class policy,
provider/model substitution, and removing correction or cold-final calls.

## 2. Frozen operating model

Deployment: existing single-user local MCP server and the supported local reviewer CLIs.
Operator, OS, Git executable and server implementation are trusted. Repository contents,
plans, model responses and model-proposed edits are untrusted static data. There is no hostile
same-user process racing filesystem paths, compromised OS, multi-tenancy, or deliberately
corrupted review state recovery.

The server may read pinned Git objects and perform bounded text transformations in memory.
Neither the server's proposal path nor the reviewer executes repository-selected programs,
build tools, hooks, tests, package installers or patch-authored commands. The caller's later
decision to execute project tests belongs to its ordinary implementation workflow.

Keep existing three-lane census concurrency. Proposal calls are serial, after successful
settlement, while the reviewed isolated workspace still exists. One proposal author owns the
whole returned patch. No network capability is added: proposal continuation explicitly requests
web_search=false and retains existing read-only provider restrictions.

Expected ordinary workload: tens to low hundreds of findings across the review; proposal
admission uses the single authoritative limits in P3. Reviews and repairs may take minutes.
Provider timeout is a generous circuit breaker,
not an instruction to reason less. False clearance and wrong snapshot binding are high impact;
a missing or declined patch is recoverable and must not erase useful review output.

Ordinary source edits invalidate application suitability. The initial branch feature supports only
tracked converged committed branch reviews with a clean relevant working tree. Tracked convergence
already materializes its immutable worktree and ignores the caller's isolate value, so isolate=false
is supported and is not an admission condition. An explicitly true proposal request with
include_uncommitted=true, converge=false, or class_closure=false refuses
before provider spend. When the argument is omitted in an unsupported mode, run the existing
review and show proposal UNAVAILABLE with the exact unsupported-mode reason. An explicit false
omits proposal work. Existing review modes must not break simply because the default changes.
Dirty-tree branch proposals are a named follow-on, not something the executor should approximate.
Tracked plan proposals support both plan_text and plan_path, including a plan outside the
repository, using the exact captured plan text and repository evidence snapshot. The model cannot
choose a filesystem destination. Plan review with verification disabled remains structural-only;
with verification enabled, all existing external-evidence gates remain in force.

## 3. Evidence and hypothesis

Read these before coding:

- README.md: tracked census, correction, final, class/debt ownership and convergence.
- docs/review-effectiveness.md: existing pilot measures review modes, not repair ownership.
- docs/predicate-convergence-result.md: a correct repair remained blocked by an overconstrained
  syntax-based class. Reviewer authorship alone does not solve a bad requirement.
- docs/class-authoring-quality-plan.md: governing requirements must remain separate from
  suggested repair syntax.
- AGENTS.md in full: immutable lineages, review contracts, retained failure evidence and gates.

Hypothesis H1: reusing an investigating session reduces marginal repair work enough to offset
the extra proposal call and reduces caller-induced incomplete or incorrect repairs.
Alternative H2: patch authoring shifts work without net savings.
Alternative H3: the reviewer implements its own mistaken prescription, reducing superficial
round count while worsening correctness, scope or maintainability.

Do not claim H1 from anecdotes or a clean patch alone. A provider context resume is not free:
record actual usage where available and leave unavailable usage/cost unknown. The existing
pilot's timings do not establish a reviewer-patch benefit.

## 4. Assessment gate before production implementation

Deliver docs/reviewer-patch-assessment.md before delivering the default-on public feature.

A1. Inventory up to six consecutive recent completed branch lineages and six plan lineages
for which both review and
repair history are actually available. Freeze the selection rule and selected IDs before
classification. If fewer are available, use all available and report the shortfall. Do not
fabricate caller transcripts, missing timings, or reasons for a change from Git history alone.

A2. For each repair transition record: preceding snapshot/debt, actual repair diff, successor
review result, known time/calls/usage, and an evidence-backed cause category:
caller misunderstood finding; missed sibling occurrence; introduced regression; original
suggestion incorrect/incomplete; reviewer overconstraint/false positive; newly discovered
independent defect; validation/protocol failure; execution failure; required final; unknown.
Categories may coexist. Distinguish model-output validation retry from a code repair round.

A3. Identify representative concrete findings for a bounded feasibility probe. Freeze six cases:
a local fix, a cross-file invariant, repeated occurrences of one class, a regression-prone
repair, a misleading/overconstrained recommendation, and a case requiring an explicit decline.
Cover both providers in the branch probe, then add one structural-plan and one verified-plan
case per provider. This gives ten feasibility cases: six branch and four plan.
Keep hidden correctness expectations out of reviewer
workspaces. Existing seeded fixtures may be adapted with declared provenance.

A4. Probe continuation without production schema changes. Use only an actual internal successful
fresh-census lane session, read-only, to emit exact replacement text; correction/final sessions
remain rebut authority and are excluded. Do not apply the proposal.
Check that the session can still read the pinned workspace, the correct provider resumes,
both fresh and resumed structured-output routes support the proposed schema, and the original
review's session/audit remains intact. This is new proposal-role work, not a review acceptance.

A5. Feasibility passes only if both providers can produce at least one usable snapshot-bound
proposal, the decline case stays a decline, and neither provider requires write permission or
repository execution. Retain all failed attempts and costs. A failed route blocks a claim of
two-provider delivery; do not silently fall back to a new cold session or a different model.
If continuation of a schema-constrained review session cannot adopt the proposal schema,
record the blocker and request a revised design rather than changing the feature secretly.

The assessment should explain which observed costs could be avoided and which remain. No
statistical generalization is warranted from this small convenience sample.

## 5. Current implementation map and seams

Verify names against the executor's checkout; this is a map, not authority to copy old code.
- src/paranoia_local/server.py: critique_branch and critique_plan input schemas and dispatch.
- src/paranoia_local/handlers.py: critique_branch, critique_plan, _converge_branch_review,
  _staged_structural_review, _staged_call, _branch_structural_snapshot, _log.
- src/paranoia_local/census_execution.py: LaneResult, CensusResult, namespace_lane, collect.
  Current lane results do not explicitly retain a separate successful-session handle.
- src/paranoia_local/engines.py: Engine.run/resume and provider restrictions/schema transport.
  Ordinary Codex resume currently supplies no sandbox flag, while repository-role evidence resume
  explicitly selects workspace-write. The proposal helper must override both with literal
  `-c sandbox_mode="read-only"`; inheritance is not an accepted premise.
- src/paranoia_local/review_census.py and staged_protocol.py: existing attempt diagnostics,
  canonical decisions, materialization and current snapshot/debt semantics.
- src/paranoia_local/inert_git.py, git_objects.py, inert_tree.py: inert snapshot reads and
  materialization. Never introduce raw unsafe Git reads alongside these helpers.
- src/paranoia_local/logs.py and session_routing.py: existing logs and session provenance.
  `write_log` already returns `Path | None`, but `_log` discards it; proposal orchestration must
  expose that result to implement P10's audit gate.
- tests/test_handlers.py, test_engines.py, test_census_execution.py,
  test_branch_plan_fidelity.py, test_class_closure_integration.py: regression integration.
- scripts/benchmark_review_modes.py:validate_source and existing benchmark bootstrap/custody
  helpers: reuse for experiments instead of building a second generic harness.

Add one cohesive proposal module, proposed name patch_proposals.py, for immutable inputs,
schema, prompt, parsing, text-edit validation and rendering. Keep orchestration in a small
handler helper. Add a separate module only if the resulting responsibilities genuinely warrant
it. Do not refactor the entire large handlers module as part of this card.

## 6. Public interface and invocation lifecycle

Add the same propose_patch: boolean argument to critique_branch and critique_plan. One server-side
`PROPOSE_PATCH_DEFAULT` constant is false throughout assessment, implementation and qualification.
An explicit true is the public production-handler activation path used by the frozen harness; an
explicit false opts out. Only Step 8 may perform a reversible candidate flip after pre-flip gates
G1-G6 pass. G7 is deliberately post-flip and alone authorizes delivery.
No new MCP tool or automatic caller-side application exists in v1.

When true:
1. Preflight supported mode and existing repo/model settings before review provider admission.
2. Run the exact existing review topology and settle existing review/class state atomically.
3. If settlement fails, is ambiguous, reaches a checkpoint, or has execution/validation failure,
   do not propose. Preserve the original result and report proposal unavailable with its reason.
4. A settled review with open blocking structural findings is eligible. Plan review also admits
   actionable semantic claim debt from a successfully completed current claim audit, using the
   completed structural investigator as author. Operational/validation claim failures are not
   semantic repair targets. No actionable blockers means NOT-NEEDED, zero proposal calls.
   Advisory-only work does not trigger a proposal.
5. Capture the settled canonical finding/debt rows, exact contract/stakes and pinned source
   identity into an immutable ProposalContext. This context is not new authority for settlement.
   For plans capture original unnumbered plan bytes, plan digest and current qualified claim
   context as specified in section 16; never edit the line-numbered display.
6. Select a successful fresh-census lane session as described in section 7. Keep its workspace
   alive until proposal completes. Resume once; retry only a repairable invalid output once.
7. Validate returned edits against original pinned blobs without writing them. Render one patch.
8. Attach proposal output/audit as supplemental data. Return the already computed review result
   and unchanged convergence trailer. Do not feed proposal prose back into that verdict.

No proposal attempt changes durable round labels, open debt, class inventory, final-engine
ownership, review cache, correction gates, concessions, or rebut authority. Proposal failure
must not be represented as a failed structural review or manufacture validation debt.

Use a proposal-specific attempt list. Aggregate reporting may show total actual calls, but
existing structural attempt semantics and counts must remain separately inspectable.
Record successful and failed proposal attempts with actual timeouts, monotonic durations,
session owner, return code and existing bounded/hashed channel conventions.

A client timeout/cancellation must leave the already settled review/audit recoverable under the
existing mechanism; do not add a new persistence protocol to guarantee response delivery.
Proposal initial/retry caps are 900 and 300 seconds, with 30 seconds local-processing reserve.
One authoritative deadline applies per eligible path and is captured monotonically at handler
entry. Branch converge and structural-only plan mode use a new server-owned
`PROPOSAL_WHOLE_CALL_SECONDS = 8400` admission deadline, leaving 300 seconds beneath the documented
8700-second client timeout. Verified plan mode reuses its existing 8580-second `plan_deadline`;
it does not add 1230 seconds to that deadline. At settlement the server admits an initial proposal
only when the full 1230-second reserve remains before the applicable deadline. A full-budget
verified plan review therefore cannot admit a proposal, while one that settles early may. A path
with no establishable deadline reports PATCH-PROPOSAL UNAVAILABLE. These are proposal-admission
deadlines, not shorter review-quality budgets: the existing review proceeds unchanged when there
is insufficient proposal headroom. Never consume time reserved for required review or claim work,
silently extend the documented client timeout, or shorten normal review budgets to make room.

## 7. Selecting the author without losing review independence

Retain a transient successful session handle per lane, including the successful validation-retry
session when the initial reply was invalid. Do not use a rejected initial reply as the author.
Attach these to typed in-memory census results; do not persist a new session registry or put
provider handles inside canonical lane manifests. Existing attempt telemetry stays intact.

For a fresh census, use the validated consolidation source-disposition mapping, including
canonical ID rekeying, to map current governing blockers to originating lanes. Select the lane
covering the largest number of eligible blocking governing findings; break ties using the
existing canonical lane order. Pass all selected current blockers to the one author, even those
originating in sibling lanes, with their canonical evidence and scope. Do not send sibling
private reasoning or raw transcripts. Explain in telemetry which findings originated elsewhere.

Only an internal successful fresh-census lane session may author a v1 proposal. Correction and
final sessions remain eligible rebut authority and therefore never author proposals; a review
whose actionable current debt first appears or is remapped after correction/final reports proposal
UNAVAILABLE. A clean correction awaiting final is not a patch opportunity. Lane sessions selected
for proposals are not exposed or registered as review/rebut authority, and proposal continuations
are never selected as future review or rebut sessions.

A cached census may not have a live originating session and matching extant workspace. If its
author cannot be established, proposal is UNAVAILABLE. Do not choose the manifest-only
consolidator, silently launch a fresh agent, rerun census, or reconstruct a purported session
from prose. An actual resume execution failure ends proposal work; no execution retry.

The P3 target-finding limit governs admission. If there are more, return UNAVAILABLE with the count;
do not silently cover a prefix or issue multiple calls. The author may decline the whole repair
or explicitly cover a subset. A partial proposal must label every omitted blocker and must not
be rendered as the complete repair.

The review final text/session, successful lane handle, proposal session and proposal retry session
are distinct audit fields even if the provider returns identical handle strings. Preserve the
existing review session reference and its routing observations. Do not register a proposal-only
session or its originating internal lane session as new review/rebut authority.

## 8. Model-owned response and server-owned patch

Prefer exact text edits to model-authored unified-diff hunk headers. The reviewer authors every
replacement byte; Python computes hunk coordinates and patch formatting. This reduces mechanical
diff errors without delegating the substantive repair back to the caller.

Use a closed, versioned response object. The exact proposed wire contract is:

    {
      "schema_version": 1,
      "status": "proposed",
      "summary": "Reject Boolean identities at this entry point.",
      "addressed_finding_ids": ["structural:D1"],
      "unaddressed": [],
      "edits": [
        {
          "target": "repository",
          "operation": "replace",
          "path": "src/example.py",
          "old_text": "    if isinstance(index, int):\n",
          "new_text": "    if type(index) is int:\n"
        }
      ],
      "suggested_tests": ["Run the identity-validation test module."],
      "limitations": ["Tests were not executed."]
    }

The example illustrates wire shape only; it is not an instruction to prefer exact-type syntax.
The key structural:D1 must be replaced by an actual supplied target key (section 16, L4).
Do not invent IDs.

P1. Every listed top-level and edit field is required; additionalProperties=false at every
object level. status is proposed or declined. operation is replace or create.
target is repository or plan. path is a string for repository and null for plan.
Branch mode permits only repository; plan mode permits only plan with operation replace.
old_text is a string for replace and null for create. new_text is always a string.
Each unaddressed item is a closed object with required finding_id and reason.
Keep operation-dependent semantics in local validation if provider schema support requires it.
Use the existing deterministic provider-compatible schema projection, not a second schema dialect.
Retain stricter unsupported constraints locally. Reject duplicate JSON keys at every depth.

P2. addressed_finding_ids and unaddressed IDs form an exact, disjoint, duplicate-free partition
of supplied canonical finding IDs. proposed requires nonempty edits and addressed IDs.
declined requires no edits and no addressed IDs; all targets have nonempty reasons.
A declining reviewer may identify disagreement or need for architecture/product direction.
This is advisory explanation; it does not rebut, close or reclassify any finding.

P3. Limits: 12 unique paths, 64 edits, at most 20 target findings, 131072 UTF-8 bytes across
old_text plus new_text, maximum raw response 262144 UTF-8 bytes before JSON decoding, and maximum
rendered patch 262144 UTF-8 bytes.
summary <= 2000 characters; each reason <= 1000; suggested_tests <= 12 strings each <= 500;
limitations <= 12 strings each <= 500. All semantic strings must be nonblank; old/new source
text is exact and is not stripped. Source replacement may intentionally be empty (deletion
within a file). Empty old_text is forbidden for replace. The server-owned patch format is strict
UTF-8, so local validation rejects unpaired surrogates without depending on an external standards
claim. Preserve rejected diagnostics using the existing
total diagnostic hashing convention rather than crashing on a surrogate.

P4. For repository replace, the pinned Git blob is authoritative even when checkout attributes,
EOL conversion or filters make the reviewer's workspace view differ. Read that exact existing
regular-file blob from the captured snapshot; require
strict UTF-8, no NUL, and LF-only line endings in v1. old_text must occur exactly once in that
original blob. Resolve every edit against original bytes, then reject overlapping spans.
Apply accepted transformations only to in-memory strings, in descending offset order.
Do not let edit two search the result of edit one. Reject no-op replacements.
Multiple edits to one path are legal if they are nonoverlapping. When old_text fails to match and
the checkout view differs from the pinned blob, report `checkout-view-diverged-from-pinned-blob`
in the bounded validation diagnostic; never search or rebase against transformed checkout bytes.

P5. For repository create, require the path to be absent from the entire original tree, all existing
ancestors to be real directories, and no edit to conflict with an ancestor or descendant.
old_text must be null and new_text nonempty strict UTF-8/LF text. File mode is server-owned
regular 100644. No executable creation. A path cannot have both create and replace operations.
No whole-file deletion, rename, binary edit, symlink, submodule, executable-bit change or
other metadata operation in v1. Existing regular executable files may have text changes only,
with their mode preserved. Reject unsupported files visibly; never decode with replacement.

P6. For repository targets use a deliberately small documented path grammar: ASCII components consisting of letters,
digits, dot, underscore and hyphen, separated by forward slashes. Reject absolute/drive/UNC
paths, empty/dot/dot-dot components, backslashes, leading-colon components, controls,
case-insensitive .git path components, and platform-ambiguous/reserved names. Reuse existing
path policy where stricter; do not weaken it. Check canonical tree entry kinds and ancestor
symlinks, including broken links. Unsupported unusual filenames yield a reasoned decline or
validation rejection. The leading-colon exclusion is a conservative server-owned grammar choice,
not an external claim about Git behavior. No path rewriting or quoting-based guessing.

P7. Read each required source blob once through existing inert Git APIs and memoize it within
the invocation. Bound original source bytes admitted for proposal validation to 2 MiB total.
Over-limit input makes proposal unavailable; it does not invalidate the settled review.
Use full reviewed tree identity, existing structural snapshot identity, contract digest and
server-computed original per-file blob identity/SHA-256. Do not treat model-authored hashes,
paths, IDs, test claims or base revisions as authority.

P8. Render one canonical Git-compatible unified diff from validated in-memory original/result
pairs, paths sorted lexicographically, with three context lines and correct missing-final-newline
markers. Include correct new-file metadata. Use strict UTF-8 and LF output. Do not call git apply
or write proposed file contents in production, even to a temporary tree. Enforce P3's rendered
patch cap. Exceeding it yields unavailable/rejected proposal, never truncation.

P9. Syntactic applicability is not semantic correctness. Status must be PROPOSED, not FIXED,
TESTED, VERIFIED, or ACCEPTED. suggested_tests are inert text, never executable instructions to
the server. Provider claims to have run tests are not proof; the prompt explicitly forbids that
claim and the public output states tests were not run by this proposal path.

P10. Audit ordering is explicit. Persist the settled review record first and require `_log` to
return its `Path | None`; only a confirmed path permits proposal work. After proposal validation,
write one linked supplemental proposal record through the same existing audit-log mechanism,
containing the exact full rendered patch and digest separately from bounded native-channel excerpts.
Return PROPOSED/PARTIAL only when that second write returns a path. If either write returns None,
return the original review with proposal UNAVAILABLE and no purported durable patch receipt.
Cancellation after the settled-review write but before the supplemental write can lose the proposal,
not the durable review; this is the accepted loss window. No arbitrary output path, database,
journal, retrying audit protocol or durable lineage extension is added. Preserve available
diagnostics through existing failure reporting.

## 9. Prompt and retry contract

Write one pure proposal prompt renderer and use its exact output for preflight and invocation.
State: review is complete; author only a candidate patch; do not modify files or execute code;
satisfy governing requirements, not mandatory suggested syntax; cover related affected sites;
avoid unrelated cleanup; decline unsupported/uncertain work; tests are suggestions only.

Supply canonical current findings and class invariants/member inventories, evidence anchors,
original reviewed base/head/tree and structural snapshot, frozen stakes, exact captured plan
contract if present, and output schema instructions. Contract content remains declarative
requirements, never instructions authorizing extra capabilities. Do not reread mutable plan_path.
Do not send only a digest where substantive contract text is needed. Follow existing context
size bounds; if the complete required context does not fit, decline admission without truncation.

A retained session can contain superseded source context. Explicitly identify the exact current
snapshot and require reading current pinned source before proposing edits; exact old_text and
server validation provide a mechanical check, not a guarantee of sound reasoning.

A locally invalid schema, ID partition, path, source span or rendered patch permits one existing-
style same-session correction. Give a bounded diagnostic with JSON Pointers to independently
detectable issues, repeat full response contract and exact source binding, and require a full
replacement response. Never combine edits from the rejected reply and retry. Never select a
later envelope, repair hunk text heuristically, or silently drop invalid edits.

Do not call _staged_call unmodified: it starts a new session and has structural-role-specific
failure semantics. Build a small proposal-specific continuation helper using existing Engine.resume,
schema projection, channel capture, clocks and bounded diagnostics. Do not add a generic workflow
framework or broaden staged settlement exceptions for this auxiliary role.

Both initial continuation and its optional correction use read-only permissions and web disabled.
For every Codex role, including a repository-role lane, the resume argv must contain literal
`-c sandbox_mode="read-only"`; workspace-write or reliance on inherited policy makes the proposal
UNAVAILABLE before spend. Claude resume must use the existing empty setting sources, read-only
`Read,Grep,Glob` allowlist, deny write/execute/web tools, and omit web flags. A4 records these
observed native capabilities; no provider behavior is accepted merely from documentation.
Execution error, timeout, unavailable binary, cancellation, quota failure, unsupported structured
output, missing session and failed retry each remain distinct outcomes. No silent fallback.

## 10. Returned output and caller handoff

Keep the original review body and its exact structural/class/convergence trailer intact.
Place a clearly delimited supplemental proposal section before the existing final trailer;
never let model summary text forge trailer fields. Use structured serialization/escaping for
metadata and untrusted prose. Render patch contents in a fence longer than any backtick run
within them so source bytes cannot terminate the presentation fence.

Server-authored fields:
- PATCH-PROPOSAL: PROPOSED, PARTIAL, DECLINED, NOT-NEEDED, UNAVAILABLE, or DISABLED.
- Bound reviewed commit/tree, structural snapshot, contract digest, and patch SHA-256.
- Target IDs; author-covered and explicitly unaddressed IDs.
- Validation statement: original source spans matched; patch not applied; tests not executed.
- Actual proposal call/retry counts and local duration, separate from review attempts.
- For proposed/partial: complete patch; for other statuses: exact bounded reason.
- Caller instruction: inspect changes, confirm current source matches the bound preimage,
  apply deliberately, run appropriate tests, and submit the changed artifact in the same lineage
  with the next lawful round label. A stale proposal needs a new review/proposal.

Do not automatically treat the caller's acceptance of a patch as acceptance of its correctness.
Do not add proposed code to already_raised or otherwise suppress subsequent findings. A later
review receives actual source changes through its existing snapshot path and may receive a short
factual change/test report from the caller, not the proposal author's assurance of success.

Integration should preserve current callers when propose_patch is omitted: while
`PROPOSE_PATCH_DEFAULT` is false the option does nothing, and after a qualified Step 8 flip
eligibility gating
must skip unsupported modes with a clear reason, never make formerly valid review requests fail.
An explicitly true unsupported request may refuse early as described in section 2.
Document cost: eligible reviews normally add one model call, at most two, even when declined.

## 11. Deterministic validation and regression matrix

Add focused tests in tests/test_patch_proposals.py and public-handler integration tests in
tests/test_patch_proposals_integration.py. Reuse production schemas/renderers/validators; avoid
a parallel fixture implementation that simply repeats the intended behavior.

T1. Wire: valid replace/create/partial/declined; missing and extra fields; duplicate nested keys;
wrong types including Boolean version; unknown and duplicate IDs; invalid partition; whitespace
semantic text; malformed JSON; competing objects; trailing content; raw size and UTF-8 failures.
Test the actual initial and resumed provider schema projections for both providers. Treat closed
required properties and an object-valued structured envelope as this feature's local wire contract;
A4 must capability-gate both native routes, so the plan does not depend on an unverified statement
about either provider's external schema dialect.

T2. Exact edits: first/last line, absent/present final newline, adjacent nonoverlapping edits,
overlaps, repeated old text, missing old text, empty old text, empty replacement, no-op,
multiple replacements per file, create collision and create-parent conflicts. Rendered patch
must reproduce byte-exact expected files. CRLF, binary, surrogate, symlink, gitlink, unusual path,
rename/delete/mode requests and each P3 boundary limit must visibly reject. Include a
`.gitattributes` `eol=crlf` fixture whose transformed checkout old_text differs from the pinned LF
blob and require the named P4 diagnostic rather than silent rebasing.

T3. Paths/snapshot: traversal, .git, leading colon, Windows drive/UNC/reserved components,
case collisions where relevant, symlink ancestors, stale blob, changed reviewed tree,
contract add/remove/change, and ordinary checkout edits while a proposal is pending.
A proposal remains tied to the original pinned snapshot; never silently rebase it onto later
bytes. Verify current workspace edits are preserved and reported as stale for application.

T4. Independent patch-applicability test: in TEST CODE ONLY, create a disposable fixture Git
repository, apply the returned patch using the inert Git execution policy, then compare exact
result bytes, inventory and modes with expected output. Include missing-final-newline and new
file cases. This tests rendering; production must never apply a proposal even to a scratch tree.
Tests must not execute arbitrary model-supplied commands.

T5. Provider behavior: resume the correct successful fresh-census lane session; use its proposal
retry session when appropriate; assert literal Codex `sandbox_mode="read-only"` and absence of
workspace-write/web flags for default and repository roles; assert Claude's empty setting sources,
read-only allowlist and write/execute/web deny list; empty or conflicted provenance; cancelled/failed resume;
one invalid output repaired; invalid retry; missing structured output; known quota failure.
Assert at most two proposal dispatches and no execution retry or fresh-session fallback.

T6. Session selection: multiple findings mapping to one lane, tied lane coverage, source fan-out
across existing classes, canonical finding-ID collisions/rekeying, successful lane retry,
cached census with no usable session, correction/final session refusal, no blockers and the P3
target-finding overflow.
Test mapping through the real consolidation materializer, not a hand-waved ID mapping.

T7. Public critique_branch and critique_plan lifecycle: with `PROPOSE_PATCH_DEFAULT=false`, same
fake-backed native review responses with explicit false/true produce identical substantive durable state and identical existing verdict,
class and convergence trailer. Eligible blocked review adds only proposal calls.
No change to clear-census topology; no proposal after settlement failure, checkpoint,
unconfirmed save or nonblocking-only review. Unsupported omitted mode preserves existing review;
unsupported explicit true refuses before any provider call. Derive every parameterized unsupported
case from Section 2, the sole mode-inventory authority. Retain isolate=false as a supported
regression case referencing that rule rather than restating the inventory here.
Add a production-handler experiment-handoff fixture for both review modes: explicit true must
settle the shared seed, retain the selected successful lane and pinned workspace through proposal
completion, then clean up. Assert unchanged canonical settlement/trailer bytes, exact lane-session/
snapshot custody in both audit records, proposal timing before cleanup, one public activation and
the E6/L8 call counts. Missing handle, mismatched custody or premature cleanup makes the scheduled
pair unqualified with retained evidence; it must not reconstruct provenance or launch a census.
Add deterministic interval-ledger replay with a 10-second seed, 3-second proposal, 7-second baseline
and 5-second candidate arm plus different scheduler waits in both arm orders. It must derive repair
durations 7 and 8 seconds and end-to-end durations 17 and 18 seconds regardless of order. Missing,
overlapping, negative or ownership-inconsistent intervals must make the pair unqualified.

T8. Independence: generate a syntactically valid but intentionally wrong patch. It must not
close any debt or advance phase. Let a test caller apply it and call the real public handler;
the defect remains blocking. Apply a correct patch in a different fixture continuation; ordinary
correction and cold-final ownership/closure rules remain required. A proposal session is not used
to certify its own repair, and its prose cannot manufacture a convergence trailer.

T9. Failure/audit: each failed attempt retains bounded raw/detail/stderr channels and hashes,
local diagnostics and pointer, actual return code, role and timing. Recovered first reply remains
rejected evidence. Exercise P10's settled-review-first ordering and both observable `None` returns.
Audit-write error, output truncation risk, prompt cap and insufficient deadline
leave original review visible and do not mutate substantive state. Full patch receipt matches
returned bytes exactly. A patch digest mismatch fails replay.

T10. Default transition integration: before Step 8, omitted and explicit false make zero proposal
calls while explicit true on an eligible fresh blocked branch or plan census proposes once. After
pre-flip gates G1-G6 pass, Step 8 may flip only `PROPOSE_PATCH_DEFAULT`, rerun this matrix, and
require omitted to match explicit true; omitted on unsupported modes then reports unavailable and
explicit false stays off. This post-flip run is evidence for G7, not a prerequisite for the flip.
Clean review skips in both states. Existing substantive review topology for both modes is unchanged;
query/rebut/arbitrate behavior is unchanged. Add the plan-specific matrix in section 16.

Run focused tests first, then affected existing handler, engine, census, class-closure, snapshot,
audit and server-schema tests, then the full suite once coherent. Record exact commands and outcomes.
Do not mark fake-backed tests as native acceptance.

## 12. Paired end-to-end experiment and decision rule

This measures the user's hypothesis rather than merely qualifying a new response format.
Freeze sources, harness, fixtures, oracles, model settings, schedules and budgets before execution.
Use existing benchmark source admission and source-only bootstrap; preserve complete attempt
channels and failed slots. Oracle and scoring material remain outside reviewer/caller workspaces.

E1. Freeze 12 branch task/provider pairs: the six branch families from A3 for each reviewer provider.
Five per provider are actionable tasks, including a behaviorally valid alternative to suggested
syntax. The sixth requires a decline because the bounded patch cannot responsibly settle the
required architectural decision. Both arms receive identical specification, starting snapshot,
stakes and validated initial review findings.

E2. Each pair begins with one production public-handler invocation using explicit
propose_patch=true while the omitted default remains false. Inside that same invocation the
ordinary native seed settles first; the handler captures its unchanged review body/canonical state,
keeps the selected successful lane session and pinned workspace alive, and invokes the real
candidate proposal boundary before cleanup exactly as Section 6 requires. No transient provider
handle crosses a call boundary and the harness never resumes an already-cleaned workspace.

After the handler returns, clone the captured settled review/class state into two isolated
continuations using existing qualified fixture custody patterns. Preserve the original lineage
history inside each clone; never reset failed evidence for clearance. The baseline receives only
the unchanged review body/findings. The candidate receives that identical review projection plus
the supplemental proposal produced in the seed invocation. Do not reuse a candidate repair
conversation across tasks or expose the proposal to the baseline.

Retain and replay-check the settled-state digest, source/plan snapshot, selected lane owner/session,
proposal attempt sequence, review and proposal audit links, settlement/proposal timestamps, cleanup
event and exact returned patch/decline bytes. Canonical state and the original trailer must match
the explicit-false control byte-for-byte.

One monotonic owner-tagged interval ledger is authoritative for elapsed time. Record one common
`seed_review` interval ending at settlement; one contiguous candidate-owned `proposal` interval
from proposal admission through validation/retry, local rendering and supplemental audit completion;
and each arm's own active caller, test, correction/final review and local-processing intervals.
Because arms run serially, scheduler waiting before an arm starts or while the other arm runs is
unowned and excluded from both. Baseline repair-to-acceptance time is the sum of its active intervals.
Candidate repair-to-acceptance time is its proposal interval plus its active post-proposal intervals.
Common seed duration is charged once in aggregate cost reporting and added identically to each arm's
repair duration only for that arm's separate end-to-end metric. Absolute wall-clock distance from
settlement to arm completion is never used for a paired ratio.

Every interval records owner, role, monotonic start/end and source attempt/audit identity. Reject
negative, overlapping or multiply owned intervals and any proposal interval that is not inside the
seed handler invocation before cleanup. Missing or inconsistent interval evidence leaves the pair
unqualified; never infer a duration from arm execution order. This is one seed plus one candidate
proposal opportunity, so E6 call accounting is unchanged.

If seed review fails to find the frozen target, or if exact session/snapshot custody cannot keep
the proposal boundary inside that invocation before cleanup, record the scheduled pair as
unqualified with all evidence; do not reconstruct a session, add a census or quietly replace it
with an easier case. Seed costs are common, reported once and also included
consistently in per-arm end-to-end presentations. This is an explicitly shared seed experiment,
not 24 independent initial reviews.

E3. Baseline: a fresh caller agent receives the original findings and performs the repair.
Candidate: an otherwise equivalent fresh caller receives the same findings plus the proposal.
Both callers use the same fixed model, effort, tooling, tests and repair instructions. Choose
the actual intended caller model at freeze; do not label it weaker without naming the version.
The caller may reject or amend the patch, and all inspection/amendment cost counts.
Do not force blind application to make the candidate appear cheaper.

E4. Callers may apply code and run controlled fixture tests in the experiment; this permission is
for the caller/harness, not the proposal role. Freeze allowed test commands. Each arm has at most
three repair/correction cycles plus one native cold final. If final discovers a blocker, retain
the failure and stop that trial; no hidden fourth repair. Every native review uses the same
original stakes/contract and legitimate forward labels. New findings may be repaired within
the bound, never erased or called out of scope solely to finish.

E5. Alternate baseline-first/candidate-first across the fixed pair schedule. Tasks run serially;
native census retains native lane concurrency. Use fresh caller sessions per arm. Record that
provider caches/subscription conditions can still confound a small sample. No optional reruns
after observing outcomes; a harness-bug requalification needs an explicitly newly frozen schedule
and retains original failures.

E6. Budgets: feasibility campaign ceiling 188 calls: ten maximum-eight-attempt structural seeds,
ten maximum-two-attempt proposals, and four verified-plan evidence graphs capped at 22 each.
The four plan probe cases may all enable verification for this conservative ceiling; actual
structural-only cases make no evidence calls. Branch paired campaign
ceiling 312 reviewer/proposal calls: 12 seeds x maximum 8 attempts = 96; two arms x 12 pairs x
three correction calls x maximum 2 attempts = 144; two arms x 12 finals x maximum 2 = 48;
candidate x 12 pairs x one fresh-census proposal x maximum 2 attempts = 24. Correction/final
invocations always use propose_patch=false because section 7 excludes those sessions from v1
authorship. These are maxima, not required spend.
Failed/declined/no-op slots still remain in the schedule. Count actual admissions globally.

Caller executions have a separate ceiling of 72 repair invocations (12 pairs x 2 arms x 3 cycles),
with a generous 1800-second operational cap per invocation and no hidden repair subagents.
Record their actual internal turns/tool activity/usage where available. Do not conflate caller
invocations with individual provider inference calls if the CLI does not expose those counts.
Reserve enough time for all admitted roles; no budget exhaustion becomes a successful outcome.
PLAN/CODE convergence review spend is recorded separately from the experimental workload.

E7. Primary measures per scheduled arm:
- Attributable repair-to-acceptance duration derived only from E2's interval ledger: candidate-only
  proposal time where applicable plus that arm's caller inspection/editing, tests, all correction/
  retry/final calls and local processing, excluding inter-arm scheduling waits.
- Total end-to-end duration derived by adding the identical common seed-review duration to each
  arm's attributable repair duration, reported separately.
- Usage by role/provider (input, cached input, output where available); absent usage stays unknown.
- Provider-reported monetary estimates separately labeled; never inferred subscription billing.
- Actual review/proposal attempts, caller invocations, correction rounds, rejected patches,
  amended patch proportion, operational failures and final outcome.
- Hidden-oracle correctness, regressions, scope expansion and independently judged maintainability.

Never count a failed trial as a zero-cost repair or exclude it from success-rate denominators.
For a nonconverged arm report observed time and censored/not-accepted status, not a made-up
time-to-success. Analyze the ten actionable pairs separately from the two predefined decline
controls. Keep the combined scheduled outcome table visible.

E8. Correctness gates: all ten actionable candidate arms must reach native tracked acceptance
and pass independently frozen behavioral tests; no accepted false clear or new out-of-scope
regression is permitted. Both decline controls must decline honestly without an unsafe patch.
The valid-alternative case must accept behaviorally correct repairs rather than force suggested
syntax. Blinded human inspection of final diffs checks scope and maintainability; require no
unresolved major quality objections, with Andy or a named independent human as owner.
Human absence is pending evidence, not an LLM substitute or automatic pass.

Baseline failures do not excuse candidate failures. If a baseline fails, report it and do not
compute a successful paired-time reduction for that pair. An experiment with incomplete
paired-success coverage cannot qualify the percentage speed claim below.

E9. Benefit gate for default-on delivery: across all ten actionable pairs with successful,
comparable outcomes and complete valid E2 interval ledgers, require median paired attributable
repair-to-acceptance time ratio <= 0.80.
Also require median paired end-to-end ratio including common initial review <= 1.00, and neither
reviewer provider's median repair-to-acceptance ratio > 1.00. Report every ratio, median, range,
sample size and failures; this is a small engineering decision sample, not statistical proof
of universal superiority. Report sums of the same derived attributable and end-to-end durations so
tails are not concealed; do not substitute continuous wall time across serial arm scheduling.

Cost is a co-reported outcome. Claim monetary or token savings only with complete comparable
measurements; do not substitute an invented price table. If speed passes but cost rises, show
the exact tradeoff and obtain user direction before default-on delivery. If comparable usage is
missing, say that cost benefit remains unknown and seek an explicit rollout decision rather than
asserting the user's cheaper hypothesis was established.

E10. Apply the additional plan-mode qualification in section 16. If quality, feasibility or benefit gates fail, retain the assessment/harness and failed
evidence, leave production review defaults/behavior unchanged, and report no-go or a narrower
follow-on for user decision. Do not quietly ship an opt-in feature as if that satisfies this
default-on plan. Do not remove gates, weaken reviewers or trim tasks to manufacture savings.

## 13. Ordered implementation checklist

An executor should produce one checkpoint summary after each step: changed files, invariant
preserved, exact verification run, unresolved issue, and next step. No unrequested delegation.

Step 0 — prepare.
Read current AGENTS and this plan; fetch main; record HEAD, status and environment. Preserve
unrelated files. Use a codex/ branch when implementation is authorized. Record source/module
size and existing primary workflow. Confirm accepted scope with this document, not old examples.

Step 1 — assess.
Perform A1-A5. Write the assessment with evidence and unknowns. Stop production implementation
on a demonstrated feasibility blocker. Do not turn exploratory probe outputs into live acceptance.

Step 2 — review design.
Update current public documentation and AGENTS with a contract-status note linking this plan,
stating that the feature is under qualification and `PROPOSE_PATCH_DEFAULT` remains false. Do not
publish section 14's delivered default-on wording yet.
Freeze the section 2 stakes. Run one PLAN review of this design, address legitimate in-scope
findings and retain its lineage/history. Do not implement while unresolved blocking design
obligations remain. Once implementation starts, convergence is CODE only against the exact
accepted plan; do not return to critique_plan as an implementation acceptance shortcut.

Step 3 — pure protocol.
Implement immutable ProposalContext/ProposalResult, closed schema, exact prompt renderer,
parser, validation, in-memory transformations and canonical diff rendering in patch_proposals.py.
Complete T1-T4 before wiring a provider. No file mutation in these APIs.

Step 4 — preserve author handles.
Add minimal transient fields to census result types and thread accepted handles and validated
source-to-governing mapping to the proposal boundary. Keep manifests, cache schema and durable
lineage unchanged. Complete T6; verify parallel failure aggregation is still deterministic.

Step 5 — continuation.
Implement the small resume/retry helper with explicit role, timeout and telemetry. Complete T5
and channel-capture parts of T9. Exercise native schema feasibility for both routes; never widen
provider tools to make the experiment succeed.

Step 6 — orchestration.
Wire proposal only after confirmed native settlement and before snapshot-workspace cleanup.
Use explicit propose_patch=true through the public handlers during qualification while the omitted
default remains false. Preserve original review output, rebut session, audit and trailer. Complete
the pre-flip T7-T10 matrix, including full lifecycle fixtures and opt-out.

Step 7 — native qualification and experiment.
Run the frozen E1-E10 schedule using real production entry points. Preserve all artifacts and
failure costs. Caller applies only in its isolated controlled fixture workspace. Replay custody,
patch bytes, snapshot identity, outcome, telemetry and metrics from retained evidence.

Step 8 — reversible candidate default flip.
Only after G1-G6 all pass, switch the public omitted option to default-on for eligible calls,
retain explicit false, publish Section 14's candidate post-flip wording and actual supported-mode/
size limitations, and rerun T10 with the flipped constant. This is not delivery. If post-flip T10
or the documentation/default check fails, immediately restore the constant to false and restore
the pre-flip qualification wording; retain the failed evidence and do not proceed to Step 9.
Human-dependent gates must be resolved, not treated as an automatic pass.

Step 9 — post-flip validation and CODE convergence.
Run the post-flip full regression and primary real end-to-end path, verify public documentation
matches the true constant, and record production diff size, largest modules, actual model calls
and elapsed time. Then CODE-review the branch against the accepted contract with frozen stakes.
These checks constitute G7. Triage all classes together; recurring architectural debt or two
ineffective fix cycles triggers a checkpoint, not an unlimited patch loop.
For convergence on this feature's own implementation, pass propose_patch=false unless the user
explicitly authorizes an additional experimental use; avoid self-hosting as hidden acceptance.
If any G7 check fails, restore the constant to false and the pre-flip qualification wording before
repair. Preserve the failed post-flip evidence and rerun every pre-flip gate whose evidence the
repair invalidates before another candidate flip. Only a passing G7 marks the feature delivered.

Step 10 — handoff.
After G7 passes, deliver code, concise operator docs, assessment, experiment report, replay
commands, full gate status and known limits. A failed or rolled-back candidate flip is handed off
as blocked, never as delivery. No automatic merge, installation, issue closure or release is included.

## 14. Documentation, acceptance matrix and stop rules

Documentation has three ordered states. Before Step 8, README.md, docs/tool-reference.md,
docs/how-it-works.md, docs/llm-reference.md and AGENTS say only that this linked feature is under
qualification, omitted means disabled, and explicit true is reserved for the qualification harness.
After G1-G6 pass and the Step 8 candidate flip makes `PROPOSE_PATCH_DEFAULT` true, replace that
status note with wording that accurately says post-flip delivery validation is pending and:
eligible blocked branch and plan reviews return an unapplied candidate patch by default;
propose_patch=false opts out; clean reviews add no proposal call; unsupported modes report
unavailable when omitted; explicit incompatible requests refuse; proposal adds at most two calls;
nothing is applied or tested; original review verdict remains authoritative; caller performs
ordinary review/application/testing and continuation. Add a gate that compares the public wording
to the actual constant. Once G7 passes, remove only the pending-validation qualifier. If Step 8 or
G7 fails, restore the false-default qualification wording. Do not rewrite historical results as
acceptance of this feature.

Create docs/reviewer-patch-results.md with a gate table:

| Gate | Phase | Required evidence | Failure disposition |
| --- | --- | --- | --- |
| G1 feasibility | pre-flip | A1-A5, both native provider routes | Stop; report limitation |
| G2 local correctness | pre-flip | T1-T9 plus pre-flip T10 and affected/full regression | Fix implementation |
| G3 state independence | pre-flip | Exact enabled/disabled state/trailer comparison | Block candidate flip |
| G4 native correctness | pre-flip | All actionable/decline controls and retained custody | Block candidate flip |
| G5 usefulness | pre-flip | E9 ratios, complete accounting and quality inspection | No candidate flip |
| G6 human quality | pre-flip | Named independent human inspection | Pending until supplied |
| G7 delivery acceptance | post-flip | Post-flip T10, docs/default agreement, full regression, primary end-to-end path and CODE closure under the exact accepted plan/stakes | Roll back default/docs; block delivery |

Required final report: baseline/source/harness identities; original scheduled denominators;
every failure; known versus unknown cost; exact patch/source/audit bindings; proposal acceptance
and amendment rates; semantic correctness; timing distribution; call counts; final review
outcomes; public default; supported and unsupported cases; independent human status.

Stop and ask for a scoped design decision if the implementation needs reviewer write permissions,
execution of repository code, new durable lineage authority, automatic application, concurrent
patch authors, a different provider, relaxed class closure, or recovery from deliberately corrupted
state. Do not add those capabilities by inference.

Named follow-ons, not blockers for the stated branch-and-plan scope: dirty-tree branch proposal binding,
unusual filename/encoding support, rename/delete/binary patches, proposals after cached census
without resumable provenance, broader representative workload and economic measurement. Each
requires an explicit later contract. None permits misleading claims of universal coverage.

## 15. Executor completion record template

Copy this into the handoff and fill every field with evidence or PENDING/UNKNOWN:

- Reviewed baseline and implemented commit:
- PLAN lineage and accepted contract digest:
- Frozen operating model changes, if any:
- Production files changed; diff size; largest affected module:
- Deterministic test commands/results:
- Native provider versions/models/effort:
- Feasibility schedule, outcomes and retained failures:
- Paired schedule, successful/censored/failed denominators:
- Repair-to-acceptance and end-to-end ratios:
- Known usage/cost by role; unknown fields:
- Human scope/maintainability judgment and owner:
- CODE lineage, rounds, final state and exact acceptance artifact:
- Default-on delivery qualified: YES / NO / PENDING, with reason:
- Proposal never applied by production path: evidence:
- Caller-facing limitations and follow-ons:
- Total development/PLAN/CODE spend, separately from experiment:

## 16. Plan-review requirements and additional qualification

This section is part of the same implementation scope, not a later feature. The public default
is proposals on for both review types once each passes qualification. Branch success cannot
stand in for plan acceptance, and plan review must not generate repository code changes.

L1. Source ownership.
For plan_text, bind the exact supplied string, strict UTF-8 encoding and its server digest.
For plan_path, capture file bytes once at input admission and thread that object through review,
digesting and proposal. Preserve existing review decoding behavior for compatibility, but offer
a patch only when source bytes are losslessly strict UTF-8 and satisfy the LF-only text policy.
An unsupported encoding may still be reviewed under existing semantics; its patch is unavailable.
Do not reread the file to author the patch. Ordinary later edits make application stale.
Use original unnumbered text, never ArtifactView display prefixes. Preserve any actual numerals
already in the user's text. Bind the repository evidence snapshot used by that exact review.

The model-owned plan edit is exactly:

    {
      "target": "plan",
      "operation": "replace",
      "path": null,
      "old_text": "The client always retries failed requests.\n",
      "new_text": "The client retries only the documented retryable failures.\n"
    }

This is an illustrative shape, not an externally verified proposition. The actual replacement
must be supported by the current review's facts and governing requirements.

L2. Render plan changes as a unified diff using server-owned virtual label plan-artifact.md
on both sides. Return source_kind=plan_text or plan_path, exact source digest and nullable
original server-captured input path in the surrounding metadata. Explain that this is a patch
to the supplied plan artifact, not a request to create plan-artifact.md in the repository.
For inline text the caller applies the diff to the exact original text buffer; for a file the
caller chooses its known original destination and verifies the preimage. The model cannot supply
an absolute destination, rewrite another file, or mix plan and repository targets.
If the plan lives in the repository, it is still one plan target rather than a duplicate
repository edit. Creating, deleting or renaming the plan document is unsupported.

L3. Apply P3's exact-match/nonoverlap/edit/byte limits to the captured plan text. Count it
as one file. Validate and transform only in memory. Preserve no-final-newline correctly.
A valid patch is a proposed revision of the plan, not an accepted implementation contract.
The next critique_plan invocation must receive the actual revised full text/path in the same
lineage with normal forward round labels. Existing plan-change and claim-reverification logic
decides what must be rechecked. Never copy old support to changed propositions by string similarity.

L4. Target inventory.
Use a server-built mode-tagged target key to prevent structural debt IDs and claim IDs colliding:
`structural:<exact durable debt ID>` and `claim:<exact retained claim_id string as persisted>`,
currently `claim:C-<10 lowercase hex>`. One documented encoder accepts only those exact canonical
strings and never coerces Boolean, integer, float or container aliases. Serialize one injective
mapping to the exact current rows. Branch mode uses the same structural namespace for consistency.
These are presentation keys only; do not rename persisted debt/claims or let models invent IDs.
The section 8 example uses the illustrative structural:D1 key; actual prompts/tests use supplied keys.
The response partitions these server-supplied keys exactly.

Include semantic claim blockers only from a successfully completed claim audit bound to the
exact current plan. Preserve qualification failures, unusable sources and distinctions between
unsupported, contradicted, omitted and unavailable evidence. Execution/validation/admission
failure is not an invitation to rewrite facts until the error disappears. When required claim
audit failed, report proposal UNAVAILABLE rather than misrepresent historical claim state.

L5. Author selection and deadline.
Use only the successful fresh-census lane rule in section 7; correction/final roles are rebut
authority and are never proposal authors. For claim-only semantic blockers with an otherwise
clear completed structural review, select the successful integrity census lane. Provide the
qualified current claim context and targeted proposition/source decisions explicitly.
Do not resume discovery, binding or cold-attestation roles to author the plan patch: their tool
and evidence contracts serve a different purpose. No successful structural investigator/session
or insufficient remaining headroom under section 6's applicable authoritative deadline means
unavailable. A legacy claim-only zero-call migration retains its
zero-call semantics and has no proposal author unless an independently valid structural session
for this exact invocation exists; do not add a review call to manufacture one.

L6. Evidence constraints.
Plan patch generation does not perform new research, capture, binding or authority attestation.
It may propose changes based on admitted current evidence and structural findings, with exactly
the same event/actor/date/modality/scope distinctions required by normal review.
When a replacement proposition has existing qualified captured evidence, carry that evidence
as context; do not certify the new wording merely because the source was qualified for old wording.

The author may correct wording, distinguish an explicit design choice from an external fact,
make a supported qualification, or decline if new research is needed. It must not silently remove
a load-bearing requirement, weaken acceptance criteria, replace a factual promise with a vague
aspiration, or move an in-scope blocker into a non-goal to obtain clearance. Any legitimate
scope/product decision requiring the user remains unaddressed with a concrete reason.
Tests must include this temptation, not just an easy spelling correction.

L7. Plan tests (add to T1-T10).
- Both input forms, repository-contained and outside-repository file path.
- Exact single capture: mutate path after admission; output stays bound to original text,
  and application suitability reports stale rather than rereading/rebasing it.
- Displayed line coordinates are absent from patch unless literally in original input.
- File encoding/CRLF unsupported patch with normal review behavior retained.
- Structural-only review, verified review with structurally blocking debt, and claim-only
  semantic blockers after a successful current audit.
- Failed/incomplete claim audit, unbound historical claims, missing structural session,
  correction/final-only authority, zero-call migration, full-budget verified review and
  insufficient headroom under each of section 6's three paths: zero proposal calls.
- Qualified source for old wording cannot automatically qualify replacement wording.
- Wrong proposed factual repair remains unverified/blocked after caller applies and re-reviews.
- Correct plan patch proceeds through the actual public handler's normal claims, structural,
  class-member and cold-final requirements. Preserve all source evidence and failed attempts.
- Both proposal schema routes for the repository-role engine used by critique_plan, not merely
  the ordinary branch engine. Assert the exact Codex/Claude read-only argv requirements in section
  9 and no browsing or tool permission widening on resume.
- No changes to the branch lineage's frozen plan contract: a proposal from a separate plan
  lineage cannot mutate an already bound branch contract.

L8. Native plan experiment.
In addition to the twelve branch pairs, freeze four plan pairs: one structural-only and one
verified-plan task per reviewer provider. Use both plan_text and plan_path across the schedule.
Each task has a supported correct repair, hidden checks for preserved requirements and exact
source meaning, and a tempting but invalid shortcut such as dropping an acceptance obligation.
The verified cases require factual wording repair grounded in captured primary evidence;
structural cases require an actual design/acceptance repair, not cosmetic editing.

Use E2's exact in-handler seed-to-candidate handoff, baseline projection, custody assertions,
owner-tagged interval ledger, fail-closed disposition and accounting for every plan pair. The
plan_path/plan_text capture and
repository evidence workspace must remain alive through the proposal boundary and may be cleaned
only afterward; neither is reconstructed from the returned review. Then use the same baseline
versus candidate caller procedure, fresh sessions and balanced order.
Plan caller changes only the supplied plan artifact; repository is evidence, not an implementation
target. Cap each arm at two repair/correction cycles plus one normal cold final. Review the
changing plan here because the experimental task is plan repair. This does not reopen the
implementation plan for this feature after implementation begins.

Plan experimental maximum: 396 reviewer/proposal/evidence calls. Structural seeds: 4 x 8 = 32;
followups: 4 pairs x 2 arms x (2 corrections + 1 final) x 2 = 48; proposals:
4 candidate arms x one fresh-census proposal x maximum 2 attempts = 8; evidence upper reserve: 2 verified tasks x
(1 shared seed + 2 arms x 3 followups) x 22 = 308. Actual evidence reuse may reduce calls.
Every followup uses propose_patch=false because correction/final sessions cannot author in v1.
The structural-only tasks never run claim evidence. No model calls are required just to consume
the ceiling. All admission failures stay in the report and block qualification.
Use existing complete-role deadline and capture/model reserve rules unchanged.

There are at most 16 plan caller repair invocations in addition to the branch ceiling of 72.
Across feasibility and both experiments the conservative provider-call ceiling is 896
(188 + 312 + 396), excluding explicitly recorded design/CODE review spend and caller internal
inference. This upper bound is substantial: publish the concrete frozen schedule and estimated
ordinary spend before launching; it is a pathology ceiling, not a target or presumed authorization
to use every call. An executor may propose a smaller separately justified schedule before freeze,
but may not selectively reduce it after seeing results.

L9. Plan delivery gate.
All four plan candidate arms must reach proper native acceptance with independent requirement
and factual-correctness checks and no weakening of scope. Apply E9's exact paired-success,
ledger-derived repair-to-acceptance, total end-to-end and per-provider thresholds separately to
plan mode. A missing or inconsistent E2 ledger blocks that plan pair and the complete-coverage gate.
Report mode-specific results; do not pool a branch gain over a plan regression.
Reuse E8/E9's quality, unknown-cost and human-review rules. A four-pair sample is only a limited
engineering qualification, so label it accordingly.

If only one mode qualifies, report the other explicitly as blocked/pending and ask for a scoped
delivery decision; do not silently ship a branch-only implementation as completing this request.
The final G1-G7 table must have separate branch and plan evidence columns.

L10. Scope reminder for implementation reviews.
This feature supports PLAN and CODE patch proposals, but its own implementation convergence
still reviews CODE against the approved contract after Step 2. Production-handler lifecycle
tests and the frozen plan fixtures establish plan-mode functionality. Do not repeatedly review
or rewrite this contract as a substitute for testing the implementation.
