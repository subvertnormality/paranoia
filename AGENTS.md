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

- Verification is on by default for real plan reviews. Codex live search or Claude `WebSearch`
  may discover candidate URLs, but provider summaries, snippets, and fetched bodies are never
  evidence. The server must capture public HTTP(S) pages, extract them with Trafilatura, resume
  binding with browsing disabled, and require a separate cold authority-and-entailment
  attestation. Claude `WebFetch` must not be enabled in plan verification or arbitration
  research. No placeholder endpoint, optional plugin, or caller adapter may stand in for this
  primary path.
  Treat the final redirect URL as governing UGC/self-source eligibility and persist capture
  digests plus cold authority/entailment decisions before support may freeze.
  Validate retained inventory before capture; attest replacement wording as its own exact
  proposition; and enforce aggregate capture/binding budgets so multiplicative per-claim maxima
  become visible debt rather than an hours-long run.
  Bound the full verified plan call below the documented MCP timeout, persist claim debt before
  structural review, and start each model phase only when its full cap fits the monotonic deadline.
- The evidence register is mechanically external-only. Retain atomic, load-bearing external
  facts; design principles/requirements issued by a governing external authority; and behavior
  promised by an external API, dependency, platform, protocol, service, or runtime. Reject
  repository state, code paths, internal history, implementation conformance, and internal
  function bridges from claim inventory: the broad structural/code review and tests own them.
  Project-authored choices do not become external design principles through labeling.
- Preserve event, actor, date, modality, scope, and chronology in every packet. A dated external
  report event is not proved by the underlying condition alone; an external rule asserted for a
  past date requires a source authoritative for that date, not a later summary.
- Prefer official/primary evidence. Secondary sources corroborate or locate. Reddit, forums,
  Stack Overflow, social media, wikis, blogs, and other UGC never govern closure.
- Shared arbitration research follows the same capture boundary. Research is on by default;
  `research: false` is the explicit repository-only mode. Both deciders receive the same
  deterministic captured packet and have live web disabled. Unknown, non-governing, or
  passage-mismatched packet IDs cannot substantiate convergence.
  Reject caller IDs across the complete rendered packet before either decider runs. Working-tree
  snapshots use the checked-out commit of each initialized submodule, not a stale superproject
  gitlink.
  Route every Git evidence read through the shared inert launcher; promised missing objects must
  fail closed without lazy-fetching through a repository-configured transport.
- Only canonical HTTP(S) sources with a host may govern closure. Repository, file, and custom
  schemes are context only, and a repository plan's own blob/raw HTTP(S) URL remains self-context,
  not evidence. Active versionless predecessor state must become blocking migration debt and
  force one exhaustive audit, never normalize to an empty verified register.
- Return exact passage, canonical location, publisher/authority, relation, and a replacement
  only when qualifying evidence entails the replacement itself. Refutation alone is not a fix.
  The plan under review is context, not evidence for its own assertions; require authoritative
  external sources.
- Round 1 is the exhaustive external inventory across facts, design principles, and behaviors.
  In later rounds, an exact unchanged supported claim is frozen with its authoritative packet
  and requires no model call or web search. Bind “unchanged” to the same assertion-bearing
  Markdown block, structured heading levels, and list ancestry, not substring presence;
  quotation, code, negation, parent changes, or relocation must re-enter verification. Edited,
  new, refuted, and unverified claims receive targeted verification. Every non-freezable claim
  requires a full current server-captured and cold-attested evidence packet rather than a compact
  verdict-only assessment; edited
  wording also requires a new full packet. Removed and mechanically out-of-scope claims do not
  consume active context. This optimization applies only to external verification. For tracked
  plan reviews with claim verification explicitly disabled, retain claim packets without rendering
  or gating on them; if stakes change, persist a re-verification requirement and exhaustively audit
  the preserved inventory when verification is next enabled. For tracked structural review, a new
  snapshot's census and the final regression are broad and cold;
  intervening correction rounds are deliberately targeted to open findings/classes, the claimed
  corrections, and their transitive effects. Do not reopen external inventory for repository
  mechanics or “missing atomic bridges,” and do not repeatedly hunt unrelated unchanged material
  for novelty between the census and final regression.
- Model omission and ID reuse are not removal: exact propositions alone preserve identity;
  every other predecessor requires old wording to be absent plus an explicit `removed`
  disposition. Surface absent old anchors as removal candidates on both the initial audit and
  correction retry, but never auto-retire them. Do not provide a model-only `nonfactual`
  escape. Reject an initial response that omits any still-present unresolved retained ID and
  name missing IDs in the same-round correction prompt. If the final bounded retry still omits
  one, apply its other valid packets and carry only the omitted claim as `unverified`; never turn
  extractor sampling into another full claim review round. A failed targeted audit must preserve frozen supported verdicts while
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
