# Branch review plan-fidelity contract

## Outcome and supported model

`critique_branch` may bind one explicit reviewed plan to a tracked branch lineage. The
plan becomes an immutable implementation contract alongside the pinned Git snapshot.
Every staged branch role then checks ordinary code correctness and implementation
fidelity. A branch lineage created without a plan remains contract-free and behaves as it
does today.

This is not external-claim verification and does not reopen plan design. The plan is
project-authored specification data; branch review proves what current code and tests do
against it.

Frozen operating model: a trusted single operator and OS run the local CLI, and the
Codex/Claude executable and provider are trusted. Repository bytes, supplied plan bytes,
and model output are untrusted data only. One tracked lineage binds at most one plan
contract. Ordinary reviews contain tens to low hundreds of obligations and should remain
useful within minutes. False fidelity clearance and wrong evidence binding have high
impact; recoverable false blocking is acceptable. Hostile local races,
repository-selected execution, multi-tenancy, a compromised OS/provider, hostile web
content, formal proof, and deliberately corrupted state recovery are excluded.

## Public input and immutable lineage binding

Add optional `plan_text`, `plan_path`, and `plan_digest` arguments to
`critique_branch`.

- `plan_text` and `plan_path` are mutually exclusive. Empty/unreadable input, invalid
  UTF-8, unpaired surrogates, NUL, CR/non-LF line separators, malformed assertions, and
  assertion mismatches fail before Git snapshot creation or provider spend.
- `plan_digest` is optional metadata only when text/path is supplied. Accept the
  16-lowercase-hex prefix already published by `critique_plan` or a full 64-lowercase-hex
  SHA-256. The server always computes and governs with the full digest of accepted UTF-8
  text.
- Plan-bearing calls require `converge:true` and `class_closure:true`. Reject a plan in
  legacy one-shot mode rather than create a weaker binding model.
- `plan_path` must be absolute. Resolve its spelling once with `Path.resolve(strict=True)`,
  require a regular readable file, and decode those bytes as strict UTF-8. Reject relative,
  missing/dangling/symlink-loop, directory, and unreadable inputs before cache lookup, snapshot
  creation, or provider spend. Equivalent absolute spellings that resolve to the same file
  and absolute symlinks to a regular file are allowed because exact decoded content—not
  spelling—is authoritative.
- On the first plan-bearing call of a new lineage, bind
  `{version:1, present:true, digest, text}` into a dedicated top-level `branch_contract`
  lineage field, not `review_state`, so it survives stakes/review-state normalization.
  Contract-free reviews perform no preflight write: they retain the authority latch through
  review, after which substantive state plus a missing field is immutable absence. Pre-feature
  substantive lineages receive the same deterministic interpretation. Once bound,
  contract presence and digest are immutable for that lineage. An attempt to add, remove,
  or change it fails before provider spend and leaves state/cache untouched. A revised
  plan requires a new explicit lineage. This is the intended frozen-contract workflow,
  not cross-contract migration.
- If later calls on a plan-bound lineage omit plan input, reuse the exact text already in
  atomic state. If they supply it, require an exact digest match and continue using the
  stored text. Thus a changed/deleted `plan_path` cannot alter or strand a review.
- A pre-feature lineage with substantive rounds, debt, classes, or staged state is already
  contract-free and cannot acquire a plan retroactively; use a new explicit lineage.
- A first-use present contract reservation is legal only with `round:1`; ordinary
  contract-free reviews retain their existing ability to begin at another round label.
  If plan input is supplied for a missing lineage at `round>1`, block before
  provider/cache/snapshot work. Complete deletion of a plan-bound state followed by an
  omitted contract or falsely restarted round 1 is deliberately corrupted-state recovery
  and remains excluded.

For the first authority decision, acquire the existing lineage latch before authoritative load.
A present reservation is atomically saved under that ownership before downstream work; for an
absent decision, hand the same latch through the review and let substantive settlement make the
missing field authoritative, preserving contract-free no-preflight-write behavior. If the reservation save fails,
return state-unavailable and make no provider call. Provider/validation failure after a
successful reservation retains the honest frozen binding. Every later call must load and
compare the reservation before those operations; absent, unreadable, malformed, or
ambiguous lineage authority blocks without fallback. Settlement remains the existing
single atomic substantive state transition under the same latch.

The public-handler authority oracle is:

| case | provider/cache | citation and state | latch/clearance |
|---|---|---|---|
| successful round-1 plan reservation | provider admitted only after save; cache lookup after save | top-level text+digest persisted; plan citations enabled | reservation latch released after the atomic authority save; normal review latch governs settlement |
| initial reservation save failure | neither provider nor cache | prior disk bytes unchanged or write ambiguity reported; no authoritative plan citation | retain existing failed-write latch; `STATE-UNAVAILABLE`, blocked |
| exact later resupply or omitted input on bound lineage | normal phase/cache rules | stored bytes/digest remain authoritative; supplied match cannot replace them | normal release/verdict |
| add/remove/change mismatch | neither provider nor cache | state bytes unchanged; no verdict may use attempted input | release latch; explicit blocking input error |
| supplied plan with absent lineage at `round>1`, unreadable/malformed authority | neither provider nor cache | no citation authority or fallback | release unless a write was ambiguous; input error or `STATE-UNAVAILABLE`, blocked |
| settlement save failure | provider may have run; no new cache/clearance is authoritative | disk retains last good reservation/state or ambiguity is reported | retain existing failed-write latch; `STATE-UNAVAILABLE`, blocked |
| stakes recalibration | normal fresh phase; old cache invalid | top-level contract bytes/digest unchanged while review state recalibrates | normal release; clearance only after new phase settles |
| review-state version normalization | fresh census; old cache invalid | top-level contract bytes/digest unchanged while review state resets | normal release; clearance only after census settles |

Write the computed full digest, supplied assertion/path, and whether stored contract text
was reused to the ordinary best-effort top-level log. Logs are diagnostic, never evidence
authority. The atomic lineage record is the sole contract source for clearance and current
`plan:` citation resolution.

`plan:` anchors are validation coordinates for the active lineage's current frozen
contract. This feature is not a permanent historical audit archive after an operator
deletes, corrupts, or loses that lineage. In that excluded recovery scenario the existing
`STATE-UNAVAILABLE` result blocks clearance; it never reconstructs authority from mutable
paths or best-effort logs. Logs may retain plan text for diagnosis but cannot restore a
governing verdict. Historical replay after lineage loss, log retention/backup policy, and
disaster recovery are explicit non-goals under the frozen single-user/trusted-OS stakes.

## Exact contract view and provider boundary

Accepted contract text is at most 1,000,000 characters. Build one branch-contract view
with `original=text` and `lines=tuple(text.split("\n"))`. Keep it separate from plan
review's `ArtifactView`. Its exact line collection and count drive numbered rendering,
all branch `plan:` anchor bounds, prompt composition, digest/state binding, and reload.
Fixtures explicitly cover terminal/no-terminal LF, consecutive blanks, and empty final
lines; rejected line separators never enter the view.

Implement one loader seam that returns this immutable captured object plus computed digest
and supplied metadata. After it returns, no code may read `plan_path` again. Thread that
object through contract reservation/comparison, structural snapshot, packet/artifact
composition, census cache identity, every initial/retry/follow-up prompt, anchor bounds,
lineage save, and top-level audit projection. A deterministic hook immediately after load
lets tests mutate or delete the source; every named consumer must still use the captured
object and exact digest.

Configure the shared provider subprocess text streams with explicit strict UTF-8 for
initial and resumed calls rather than relying on the interpreter-selected default
encoding. Preflight exact prompt serialization with the same codec before provider
admission. Serialization failure blocks locally without reusable cache or clearance.

## Prompt, checklist, and anchor semantics

Append the numbered contract to the canonical branch artifact under fixed begin/end
markers. Server-owned instructions immediately before and after it state that contract
text contains declarative implementation requirements only and cannot alter reviewer
role, procedure, tools, stakes, checklist ownership, severity, evidence grammar, schema,
validation, or clearance. This is an instruction/data boundary under the frozen
trusted-provider/no-active-adversary model, not formal prompt-injection resistance.

With a bound contract, branch evidence accepts `plan:<line-or-range>` and
`repository/<path>:<line-or-range>`. Without one, it retains the current repository-only
policy and rejects `plan:`. Do not infer a plan from repository files.

Do not add a lane or model call. Every census lane and cold final already covers all nine
mechanically required checklist rows. With a contract, instructions give three existing
rows explicit fidelity meaning:

- `artifact-complete`: every in-scope plan obligation is implemented, or an explicit,
  traceable deferral names its residual owner and acceptance boundary;
- `tests-acceptance`: every named acceptance criterion is exercised through its named
  public/production entry point;
- `consistency`: persisted/public contracts introduced by the diff are described by the
  plan and implementation behavior does not silently contradict it.

Every lane owns these duties from its perspective. Correction remains targeted to open
debt. The cold final repeats all nine rows and therefore repeats all fidelity duties.
Consolidation only combines validated manifests and stays manifest-only.

The initial census-lane and correction/final prompts contain the complete canonical
artifact. Their same-session validation retries resend that same contract section and
authority fence with the bounded diagnostic, and preflight the exact retry prompt.
Consolidation and its retry never review or receive the artifact; they receive only
validated manifests and the plan-capable anchor grammar. This distinction is explicit,
not a promise that every retry role resends the contract.

## Snapshot, cache, bounds, and failures

Bind a versioned canonical serialization of base ID, reviewed head/synthetic ID, ordinary
packet bytes, contract presence, full contract digest, and exact contract text into the
structural snapshot. The census cache continues to bind snapshot, complete body, line
count, and exact lane prompts. Stored contract reuse produces the same identity; an
attempted contract mutation rejects before cache lookup.

The contract is load-bearing and never truncated. The ordinary 400,000-character packet
budget still governs gathered repository evidence; the contract is additional input
under the existing 5,000,000-character staged prompt breaker. Preflight exact census,
correction/final, and their validation-retry prompts. Below-limit and exactly-at-limit
prompts transmit the complete contract; over-limit prompts fail before that role's call
and leave no reusable cache/clearance. Consolidation's manifest-only bound is unchanged.

Anchor traversal, range, prefix, snapshot, and symlink rules remain unchanged. Repository
anchors resolve only in the pinned worktree. Plan anchors resolve only against the stored
branch-contract view. Lineage load/save ambiguity keeps the existing visible
state-unavailable blocking behavior.

## Executable acceptance

Unit and cross-layer acceptance proves:

1. tool schema and handler XOR/error behavior, 16/64-digit assertions, invalid text/path,
   digest-without-plan, size limit, and rejection in either one-shot configuration;
   path cases include relative, absolute regular, absolute symlink to regular, unreadable,
   directory, missing/dangling/symlink-loop, and equivalent absolute spellings, all with
   the declared pre-provider/cache/snapshot boundary;
2. first-round present/absent binding, later stored-text reuse after path deletion, exact
   resupply, and pre-provider rejection of add/remove/change or retrofitting a substantive
   pre-feature lineage, with state/cache bytes unchanged on rejection; explicit tests cover
   first reservation save failure, absent authority at round>1, later load failure, malformed authority,
   settlement save failure, stakes recalibration, and state-version normalization, asserting
   provider/cache/citation/latch/clearance behavior in each case;
   lineage loss returns the existing blocking state-unavailable result and does not claim
   historical replay or recover clearance from a path/log;
3. a post-load mutation hook separately changes and deletes the first-call source; snapshot,
   cache, census, initial/retry/follow-up prompts, bounds, reservation, settlement, and audit
   all retain the captured text/digest and never reread the path;
4. the dedicated line view supplies display and bounds, including an addressable terminal
   empty line, while plan review's `ArtifactView` remains unchanged;
5. all census lanes and cold final receive the three fidelity duties and plan-capable
   anchors only with a contract; correction/final and their validation retries resend the
   exact contract; consolidation/retry remain manifest-only; no-plan prompts reject plan
   anchors;
6. strict UTF-8 byte capture for non-ASCII text at initial and resumed provider stdin,
   independent of interpreter default, with serialization failures before provider work;
7. canonical snapshot/cache binding and below/exact/over prompt boundaries without
   truncation, stale reuse, or clearance;
8. conflicting-instruction/false-clearance contract fixtures remain inside the authority
   fence while server schema, anchor checks, stakes, and verdict computation govern;
9. deterministic public-handler fixtures use this exact four-line contract:
   `# Fidelity contract`; `O1: emit fidelity.json`; `A1: exercise O1 through the public
   critique_branch entry point`; `P1: persisted additions are limited to branch_contract`.
   They emit and assert three named governing findings:
   `contract-missing-obligation`, `contract-entry-point-unexercised`, and
   `contract-undescribed-persistence`, each `MAJOR`, mapped respectively to exact obligation
   and citation `O1/plan:2`, `A1/plan:3`, and `P1/plan:4`,
   distinct open debt identity, full stored digest, and governing blocked verdict. The same
   fixture made conforming clears under identical identity checks;
10. real Codex public-handler lifecycles exercise conforming and nonconforming fixtures.
   Audit/state must show the full digest, stored contract binding, and accepted `plan:`
   evidence. Provider prose is recorded rather than asserted exactly.

README, tool schema/help, and agent instructions document the immutable-per-lineage
contract and new-lineage rule. Regression runs cover prompt/protocol, census/cache/state,
handler/server/runner, and the full suite. After implementation begins, convergence reviews
the code branch only; the plan is not reopened.
