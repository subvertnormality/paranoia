# Repository agent instructions

These instructions govern work in paranoia-local. User instructions take precedence but do
not silently expand scope.

## Freeze proportionate stakes

Before any convergence loop, state one concrete, stable operating model: deployment,
operators, trusted actors, untrusted inputs, active adversary capabilities, concurrency,
network boundary, expected files/claims/rounds/latency, consequences of false clear versus
false block, and explicit exclusions. Avoid vague labels such as “production”, “malicious
repository”, or “high stakes”. Distinguish untrusted static bytes from repository-selected
code execution, a hostile local process racing paths, a compromised OS, and hostile web
content. A material stakes change requires user direction and retriage; never strengthen
stakes merely to keep a review loop generating work.

Default local-tool calibration unless the task says otherwise: trusted single user and OS;
plan/repository/fetched content untrusted as data; no hostile local race; ordinary edits must
block/retry; tens to low hundreds of claims; evidence useful within minutes; false
`NOT-BLOCKED`, authority errors, and wrong evidence binding high impact; recoverable blocking
acceptable. Formal proof, multi-tenancy, hostile same-user races, and deliberately corrupted
state recovery are not implied.

## Review the right artifact

Do a plan review to validate the design, then implement it. Once implementation begins,
paranoia convergence reviews the **code branch/diff**, not the old plan, unless the user
explicitly asks to reopen plan design. Never spend repeated rounds polishing a plan while
reporting implementation progress. Label every run in commentary as PLAN or CODE.

Before review, update public documentation and these agent instructions. Before opening a PR,
run the primary capability end to end; fake-backed tests alone do not establish usability.

## Classes are architectural hypotheses

An open class is not a patch instruction. Triage all open/reopened classes together: concrete
reachable failure, required actor capabilities, user/public invariant, shared root cause,
proportionate disposition, and smallest coherent remedy. Stop patching and hold an architecture
checkpoint when a class recurs, a late round opens an architectural class, two fix cycles do
not reduce blockers, a fix adds a subsystem/trust boundary/persistence protocol, or the change
budget is materially exceeded. Choose refactor, narrower contract, staged rollout, or no-go.

At a checkpoint, do not “fix every class” line by line. Re-read the request, group patterns,
measure current diff/runtime, and simplify. A clean review means no in-scope blocking class
under frozen stakes—not defense against every imaginable environment.

## Optimize for a workable product

Priority order:

1. accurate domain behavior and verdicts;
2. reliable ordinary operation and recoverable failures;
3. useful latency and bounded resources;
4. maintainable, small architecture;
5. security against actors explicitly in scope;
6. excluded hardening.

Never improve speed by dropping a load-bearing claim, accepting weak authority, reusing a stale
verdict, weakening evidence-to-claim entailment, or falsely clearing debt. Do not add CAS,
journals, custom transports, all-pair protocols, or hostile-race defenses when existing atomic
state and reviewer-native capabilities meet the supported model.

## Claim-verification invariants

- Verification is on by default for real plan reviews and uses the selected reviewer CLI's
  built-in web search. No placeholder endpoint, optional plugin, or caller adapter may stand
  in for the primary path.
- Retain only atomic, load-bearing factual propositions. Decisions, policies, requirements,
  intentions, definitions, preferences, forecasts, and incidental facts leave active inventory
  once classified.
- Prefer official/primary evidence. Secondary sources corroborate or locate. Reddit, forums,
  Stack Overflow, social media, wikis, blogs, and other UGC never govern closure.
- Return exact passage, canonical location, publisher/authority, relation, and a replacement
  only when qualifying evidence entails the replacement itself. Refutation alone is not a fix.
- Treat negative-existence and chronology inferences as their own claims. The absence or late
  first-add of one named file proves only that fact about that path; it does not prove that no
  equivalent plan, brief, manifest, issue record, tag, or historical Git object existed. Before
  applying such a correction, inspect the relevant revision for alternative authoritative
  surfaces, then separately assess source existence, declared process/profile, requirement
  conformance, and current reusability. If one omitted source class affects sibling cases, audit
  the whole sibling set once before the next round instead of discovering one case per round.
- Round 1 is the exhaustive factual inventory. In later rounds, an exact unchanged supported
  claim is frozen with its authoritative packet and requires no model call or web search;
  repository packets additionally require a resolving current-file or historical Git-object
  location whose exact quoted bytes still exist. Edited, new,
  refuted, and unverified claims receive targeted verification and edited wording requires a
  new full packet. Removed/non-factual claims do not consume active context. This optimization
  applies only to factual verification: the structural FATAL/MAJOR review remains broad and
  cold on every convergence round.
- Model omission and ID reuse are not removal: exact propositions alone preserve identity;
  every other predecessor requires old wording to be absent plus an explicit `removed`
  disposition. Surface absent old anchors as removal candidates on both the initial audit and
  correction retry, but never auto-retire them. Do not provide a model-only `nonfactual`
  escape. Reject a response that omits any still-present unresolved retained ID and name
  missing IDs in the same-round correction prompt; never turn extractor sampling into another
  full claim review round. A failed targeted audit must preserve frozen supported verdicts while
  recording debt for the affected edit cone. The cold structural reviewer must see the complete
  active register plus current retirements
  before its success contributes to tracked-mode clearance; one-shot plan reviews emit no
  computed convergence verdict.
- Malformed model output and required-role failure produce visible blocking debt with bounded
  diagnostics; they never become an empty register or false clear.
- The reviewer remains read-only. The calling coding agent autonomously validates packets,
  edits the plan before round 2, increments the round, and reruns. No human is required for
  ordinary convergence, and unchanged-input reviewer churn is not correction.
- Material plan convergence requires both claim closure and class closure plus the governing
  computed `CONVERGENCE: NOT-BLOCKED` line.

## Delivery discipline

Use `apply_patch` for edits and preserve unrelated user changes. Add focused tests for root
invariants and the real model-facing schema. Model JSON examples must contain concrete valid
literals—never `"fact|decision"` or similar pseudo-enums—and correction prompts must name the
actual validation error. Record production diff size, largest modules, model-call count, and
real elapsed time.

After implementation and docs pass locally, run Codex paranoia against the code with the frozen
stakes. Accepted findings trigger one coherent change followed by a focused rerun; recurring
classes trigger an architecture checkpoint, not endless patching. Do not open/merge a PR while
real acceptance, tests, implementation convergence, or documented stakes remain unresolved.
