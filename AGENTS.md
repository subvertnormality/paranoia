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

For staged census settlement, preserve one concrete debt record for every blocking governing
finding and every governing finding referenced by a violated class assessment, including
`MINOR` and `OUT-OF-SCOPE`. Advisory debt is tracked but excluded from phase gating and the
computed blocking-debt count; do not weaken the validator or inflate severity to reconcile a
prompt mismatch.
One atomic lane finding may violate several active classes. Preserve that observation and allow
its source disposition to fan out to one distinct governing finding per affected class; do not
force the reviewer to split or paraphrase the source finding merely to satisfy settlement shape.
Every target of a repeated source must be an existing-class finding backed by its own distinct
violated assessment citing that source; repetition must not manufacture one-off or new-class debt.
During census consolidation, do not ask the model to repeat class outcomes. Derive one outcome from
each validated integrity assessment, copying its verdict and ordered evidence exactly. For a
violation, require exactly one governing finding that includes the cited integrity source and
classifies to that class; a finding may not target a satisfied class. Correction and final retain
model-owned class outcomes because they have no prior lane judgement to project.
Derive the deterministic close transition when an open, unmechanized class is assessed satisfied;
do not discard a healthy census because the model omitted that redundant lifecycle record.
After consolidation-only failure, reuse a complete validated lane census only under exact bindings
to mode, structural snapshot, full review body/open debt, stakes, active-class state,
engine/model/effort/web settings, plan context, and cache schema. Persist it only after terminal
validation rejection, and bind the exact composed lane prompt bytes so instruction changes
invalidate reuse. Incomplete or mismatched lanes, execution failure, timeout, cancellation, or
failed retry must delete any older cache and never suppress a fresh census. Persist those
non-terminal-consolidation-validation exits as structured staged failure with exact role, kind,
and message, not validation debt. Preserve timeout, unavailable executable, provider error, and
other execution outcomes distinctly, including the validation-retry role.
Attempt telemetry must use that same `*-validation-retry` role.
Terminal validation debt must persist and render the identical structured role, kind, and message.
Every failed engine Review projected into staged or claim state must also retain return code, raw
stdout, structured failure detail, and process stderr as distinct bounded, hashed channels.
Persist terminally rejected staged model replies separately from provider envelopes as bounded
head-and-tail excerpts plus full-reply SHA-256 in both lineage failure/debt state and the top-level
audit record. Retry diagnostics must retain the bounded local validation issue and JSON Pointer;
do not restore a hand-maintained row-shape catalogue beside the executable schema.
Parallel staged failure fan-in must preserve rejected replies from every failed lane in deterministic
attempt-sequence order. Attach diagnostics to the closure before lineage persistence so a failed
state write cannot remove them from either branch or plan audit output.
Hash rejected extracted model text with a total, documented encoding for every Python string the
engine JSON parser can produce, including unpaired surrogates; do not change historical structural
or state digest encoding as a side effect of diagnostic capture.

For the staged Protocol v2 cutover, give plan reviewers a displayed line-number view derived from
the same line collection used by anchor bounds while retaining original unnumbered bytes for
digests, claims, and persistence. Constrain fresh and resumed provider output with a deterministic
provider-compatible projection of the closed, role-specific JSON Schema the server validates.
Provider-subset omissions such as Codex's unsupported `uniqueItems`, plus non-semantic draft
metadata that Claude cannot receive, remain fail-closed local constraints and may cause only the
existing same-session validation retry. Ask the model for each semantic judgement once;
derive mirror debt, disposition, binding, and lifecycle rows deterministically, then dry-run the
canonical class engine before the single atomic state transition. Preserve every current legal
semantic outcome, including carried-debt identity, independent new-class severity, and standalone
class actions. Preserve stored debt IDs; allocate new IDs canonically and compare historical fresh
V1 labels through an explicit semantic bijection. Treat fresh governing-finding labels as
response-local: after validating response-local uniqueness and bindings, deterministically rekey
collisions with durable historical finding IDs and rewrite every in-response reference. Historical
updates remain debt-ID keyed; unknown, duplicate, and misbound references still reject. Define
rejection atomicity over substantive
review/class state while retaining required failure diagnostics. Prove historical V1/V2
materialization equivalence, and do not ship a permissive alias normalizer, partial settlement,
durable dual protocol, extra model call, or new persistence mechanism. A structured-output
capability failure blocks the cutover rather than falling back to unconstrained prose.
Derive the reopen lifecycle record when an evidenced violated outcome targets a closed unmechanized
class; never infer a violation, evidence, or basis from a bare reopen action, and continue to require
an explicit replacement for a closed mechanized violation. Compose derived lifecycle with one
compatible independent model action deterministically: reclassification precedes derived lifecycle,
explicit lifecycle is not duplicated, replacement supersedes derivation, and incompatible actions
reject through the canonical dry-run. Bind every validation-invalid staged attempt and
rejected-payload record to that attempt's own bounded executable validation issue, retaining its
JSON Pointer lines even after successful retry; merge all rejected rows in attempt-sequence order.
Execution failures keep distinct full-channel digests and bounded excerpts, and provider text must
not escape those bounds through the rendered/persisted error message. Render terminal staged failure
in a failure-only body that accurately distinguishes pre-settlement failure from an unconfirmed
post-settlement persistence result, and summarize attempt/retry counts from the ledger, never with a
clean-review section.
Treat a requested Claude schema as unsatisfied unless the provider envelope contains an object in
`structured_output`; a successful process plus result prose is not structured success. Branch
class definitions must reject leading-colon Git pathspec magic, and a mechanized class replacement
must remain mechanized. Semantic validation must report independent safe-to-detect issues together
within its bounded diagnostic so the one retry can repair them. The census decision schema must
represent the complete aggregate admitted by all three lane bounds and active-class fan-out.
Resolve all independent model-owned anchors and dry-run all independent class actions into one
bounded, pointer-addressed retry diagnostic; derived mirror debt must not create unrepairable
diagnostic pointers. Reject whitespace-only semantic text and oversized raw staged replies before
JSON decoding. Cross-layer tests must carry accepted class actions through the canonical engine and
durable settlement, not stop at materializer row shape.

Preserve full class-closure semantics on every tracked staged plan and branch path. Every governing
finding must have exactly one explicit disposition: genuine one-off, new reusable class, or existing
active class. Bind each new class record to one finding, apply it through the canonical class engine,
and render `CLASS-REGISTER` plus `CLASS-CLOSURE` with canonical IDs and blocking detail alongside the
single staged structural verdict. Concrete structural debt is not a substitute for class closure.
When lineage state is unavailable or persistence is ambiguous, render both class fields but use
`CLASS-CLOSURE: STATE-UNAVAILABLE`; never present unconfirmed in-memory counts as durable state.

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
Treat operational timeouts as generous circuit breakers, not review-quality budgets. Do not
shorten a normal thorough review to control cost; use bounded model-call counts, batches, packet
sizes, and convergence phases to stop pathological work while allowing valid calls to finish.

## Claim-verification invariants

- Verification is on by default for real plan reviews. Codex live search or Claude `WebSearch`
  may discover candidate URLs, but provider summaries, snippets, and fetched bodies are never
  evidence. The server must capture public HTTP(S) pages, extract them with Trafilatura, resume
  binding with browsing disabled, and require a separate cold authority-and-entailment
  attestation. Claude `WebFetch` must not be enabled in plan verification or arbitration
  research. No placeholder endpoint, optional plugin, or caller adapter may stand in for this
  primary path.
  Claude discovery must both expose and allow only `WebSearch`; repository evidence may expose
  and allow only `Read,Grep,Glob`; binding and text evidence roles must remain tool-less. A
  permission denial of a tool required by the active evidence role is an execution failure, not
  an unverified-claim result. Treat the accepted Codex and Claude CLI versions as minimums, not
  exact pins: permit later versions and let unsupported flags/tools, missing structured output, or
  other real capability failures block visibly.
  Treat the final redirect URL as governing UGC/self-source eligibility and persist capture
  digests plus cold authority/entailment decisions before support may freeze.
  Validate retained inventory before capture; attest replacement wording as its own exact
  proposition; and enforce aggregate capture/binding budgets so multiplicative per-claim maxima
  become visible debt rather than an hours-long run.
  Treat an omitted expected indexed binding row as unusable for that exact source and demote only
  the affected claim when it has no other qualifying evidence. Preserve omission as a distinct
  conservative outcome from an explicit `usable:false` row so durable provenance remains truthful.
  For an explicit unusable row, retain a server-owned capture failure reason when capture failed;
  use model-rejection provenance only when the server capture was actually available.
  Non-integer, unknown, or duplicate identities, malformed rows, unavailable captures claimed as
  usable, and passage mismatches still reject through the bounded correction path.
  Apply the same exact-integer identity rule before constructing cold-attestation keys; no JSON
  scalar or container alias may bind authority or entailment to another claim or evidence row.
  Bound the full verified plan call below the documented MCP timeout, persist claim debt before
  structural review, and start each model phase only when its full cap fits the monotonic deadline.
  Captured binding failure debt must retain raw provider stdout, structured failure detail, and
  process stderr as distinct hashed and bounded channels, including initial and correction calls.
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
  the preserved inventory when verification is next enabled. For tracked plan structural review,
  a new plan snapshot's census and the final regression are broad and cold; intervening correction
  rounds are deliberately targeted to open findings/classes, the claimed corrections, and their
  transitive effects. Tracked branch review uses the same broad cold census, targeted correction,
  and broad cold final lifecycle; its external claim register remains out of scope. Do not reopen external inventory for repository
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

Arbitration deciders operate only on separate inert materializations of the pinned snapshot and
its bounded snapshot-derived history. Ref movement during snapshot construction fails before
spend; movement after that boundary is audit provenance (`REFS-MOVED: yes`), not grounds to discard
an otherwise valid decision. A terminal research validation failure must retain bounded raw and
extracted replies plus the exact parser errors for both the initial attempt and its single retry,
and all accepted discovery, capture, session, usage, and duration artifacts accumulated before it;
an execution failure must preserve the engine's structured failure detail. Once snapshot or
cleaning state exists, a research failure must render and persist that actual run provenance rather
than preflight defaults, including binding-input and shared packet validation, with exact baseline
and final ref digests. Successful and failed lanes use the same structured attempt and accepted-
artifact ledger; never rebuild a successful corrected lane in a way that drops its initial parser
error. Establish the run record immediately after snapshot setup and route every later ordinary
failure through it. Transition that record after every cleaner/attester attempt, label assignment,
fan-out, and carried-evidence step so later failure cannot erase completed artifacts. Do not add a
third research retry. Store round-two carried bytes before starting either second-round call, and
record the prompt for an initial decider execution failure.
After shared research normalization succeeds, every later failure must retain the exact rendered
packet bytes and computed digest in addition to the lane ledger.
Treat normalization/rendering as establishment before reserved-token validation, so rejection of
the rendered packet retains its exact bytes and digest.
Open every research attempt record before provider invocation with phase, intended session, and
prompt digest/excerpt; complete that same record from either the Review or caught exception so call
counts and retry diagnostics remain exact.
Apply the same before-invocation ledger rule to cleaner and attester calls. Mark research running
only after deadline admission, and keep established packet digest computation total on
model-controlled Unicode so the failure serializer cannot throw.
Cleaner, attester, and decider attempt rows must carry the requested engine/model and a closed
execution route. External routes retain executable and compatible CLI version; injected and
deterministic routes must not claim either. Derive acceptance call routes from those rows, not
artifact prose. Append the prepared row before any local composed-prompt bound can reject it;
retain local rejection distinctly with no admission or invocation.
Treat arbitration context as caller-owned shared specification/data: preserve its exact bytes,
ignore any cleaner rewrite or omission, and gate its advocacy independently rather than asking the
cleaner to alter it. A changed fidelity verdict is actionable only when a per-field structured entry
names every changed field, binds exact original and cleaned substrings to that field's actual pair,
classifies the semantic delta with the closed change enum, and repeats that classification in the
deterministic `<field>: <change>` reason label. Do not use a free-text heuristic as a semantic gate. Keep valid
`raw_input.options` as the same ID-to-statement mapping on every success and failure path.
When the cross-vendor attester finds a cleaned semantic change or cleaner-introduced bias but judges
the original decision/options/hints neutral, use the exact original cleaner-owned packet atomically;
never mix original and cleaned fields. Context and stakes remain independently advocacy-gated, and
an advocating original packet must still be faithfully neutralized or fail.

Use `apply_patch` for edits and preserve unrelated user changes. Add focused tests for root
invariants and the real model-facing schema. Model JSON examples must contain concrete valid
literals—never `"fact|decision"` or similar pseudo-enums—and correction prompts must name the
actual validation error. Record production diff size, largest modules, model-call count, and
real elapsed time.

After implementation and docs pass locally, run Codex paranoia against the code with the frozen
stakes. Accepted findings trigger one coherent change followed by a focused rerun; recurring
classes trigger an architecture checkpoint, not endless patching. Do not open/merge a PR while
real acceptance, tests, implementation convergence, or documented stakes remain unresolved.
