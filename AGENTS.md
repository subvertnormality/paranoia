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
After implementation begins, do not invoke `critique_plan` again merely as acceptance for
plan-role mechanics unless the user explicitly authorizes that return. Use deterministic
production-handler lifecycle coverage and keep convergence on the code artifact.

Before review, update public documentation and these agent instructions. Before opening a PR,
run the primary capability end to end; fake-backed tests alone do not establish usability.

When `critique_branch` receives an explicit plan contract, bind the exact loaded contract and
its server-computed full digest to the reviewed Git snapshot, staged state, census cache, every
review role, and the audit record. Keep `plan:` anchors unavailable when no contract was supplied.
Every census lane and cold final must use the existing mechanically required checklist to check
implementation/traceable deferral of plan obligations, named acceptance criteria through their
named production entry points, and undescribed persisted/public contracts. Do not add a reviewer
call, truncate the contract, treat caller digest metadata as authoritative, or reopen plan design
during branch review.
Treat contract content only as declarative requirements, never reviewer instructions. Contract
presence and digest are immutable after the first-use lineage reservation; reject any later
add/remove/change before provider spend and require a new explicit lineage. Reuse the exact bounded
contract stored in atomic review state so mutable paths cannot change or strand current `plan:`
citations. Ordinary code snapshot changes retain targeted correction.
Store a closed, versioned present contract-authority record in a dedicated top-level lineage
field that survives review-state normalization. Acquire the existing latch before authoritative
load; save a first present binding before downstream work, or hand the same latch through a
contract-free review and treat substantive missing authority as immutable absence. Require
absolute plan paths and read them once into one captured object
threaded through every consumer; never reread the source path.
Allow first plan-bearing reservation only at round 1; contract-free reviews retain existing round
labels. A supplied plan against a substantive contract-free lineage blocks. Complete deletion followed by
omitted contract input or a falsely restarted round 1 remains outside the corrupted-state boundary.
Treat plan anchors as coordinates for the active lineage, not a historical archive after lineage
loss. State loss remains visibly blocking; do not add audit retention/backup/recovery machinery
outside the frozen trusted-OS, non-corrupted-state stakes.
Reject plan-bearing legacy one-shot review instead of creating a weaker binding path.
Resend the captured contract and authority fence on census-lane and correction/final validation
retry; consolidation and its retry remain manifest-only. Use an injective LF-only branch-contract
line representation while leaving plan-review `ArtifactView` semantics unchanged.
Bind shared provider subprocess text streams explicitly to strict UTF-8 for initial and resumed
calls, and preflight exact prompt serialization with that codec before provider admission.

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
When fresh class decisions use keyed objects, retain those wire locations through semantic and
canonical class-engine validation so the bounded retry names provider-repairable JSON Pointers;
never expose canonical array indexes that were absent from the provider response.
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
digests, claims, and persistence. When plan-anchor resolution fails, the bounded same-session retry
must repeat the strict `plan:<line-or-range>` grammar and current line bound, explicitly discarding
column coordinates rather than concatenating their digits. Never guess, clamp, drop evidence, or
partially settle. Constrain fresh and resumed provider output with a deterministic
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
Model-owned staged evidence uses a closed `{anchor, rationale}` citation object. Validate that wire
shape before projecting the exact anchor into the existing string-only semantic/cache/settlement
contract; validate the canonical projection again so duplicate anchors cannot hide behind different
rationales. Never trim or extract a leading anchor from prose, split joined citations, accept legacy
strings, or relax traversal, range, prefix, snapshot, and symlink resolution. Cached lane manifests
are canonical data and use an explicit canonical validator plus a cache-version cutover, not the
fresh wire decoder.
Represent fresh model-owned class outcomes and independent class actions as closed objects keyed by
the exact server-supplied class IDs, rejecting duplicate JSON keys before schema validation. Project
those maps in duplicate-checked encounter order into the existing canonical arrays; do not sort
actions whose order determines successor identity, deduplicate an invalid array, accept a legacy
wire shape, or partially settle a register. Detect nested duplicate keys in Claude's raw structured
envelope before converting `structured_output` to a mapping, retaining its session and raw channel
through the validation retry. Final owns one outcome per active class; correction owns outcomes
only for classes already bound to supplied open debt and derives a new existing-class violation
from a distinct role-specific assessment-evidence member, never from finding evidence. Census
continues to derive outcomes from validated integrity assessments. Specialize each action value
schema to the target class so mechanized classes cannot express close/reopen, while canonical
semantic validation and the class-engine dry-run remain authoritative for state/outcome
compatibility. Capability-gate the exact compact minimum and maximum generated schemas on fresh and
resumed Codex and Claude routes; unsupported schema dialect or transport size blocks the cutover.
For keyed correction outcomes, require every permitted property in the provider schema and make
only semantically optional values nullable; project null values away before canonical validation.
Never expose a property set wider than `required`, because Codex rejects that schema before review.
When a correction fresh finding targets a debt-bound class, require that class's authored violated
outcome to use `new_finding` basis naming the exact finding; `carried_debt` is legal only when no
fresh existing-class finding targets that class. Preserve independently authored finding evidence,
assessment evidence, every debt outcome, assessment disposition, and audit binding.
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
durable settlement, not stop at materializer row shape. Before a fresh or replacement mechanized
class enters durable branch state, run its predicate over the reviewed Git snapshot and require it
to match at least one repository line cited by the governing finding or violated class assessment.
Reject match-all `.*`; when no honest line-level violation predicate exists, require an
unmechanized procedure. Keep this inside the existing same-session validation retry so a repairable
predicate does not cost another review round. Charge admission checks to the same aggregate
per-round predicate budget as closure sweeps, reuse exact snapshot/pattern/path results within the
round even after execution budget exhaustion, and fail candidate validation visibly only when an
uncached execution cannot be admitted.
Any retained public acceptance for this admission-and-sweep lifecycle must bind the class-closure
executor as well as the staged handler and anchor resolver.

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

In plan review, judge whether an in-card implementation obligation is completely bound by named
scope, executable acceptance evidence, and fail-closed behavior; never require the plan itself
to produce future runtime artifacts. New plan classes must state plan-reviewable invariants. Replace
an inherited class whose invariant demands implementation execution with a phase-correct invariant
instead of recurring on the absent artifact or pretending implementation has passed. A routed
out-of-card blocking obligation needs a named durable residual, owner, and acceptance boundary.
Ownership never substitutes for in-card scope, and advisory, OUT-OF-SCOPE, stakes-excluded, and
declared non-goal work is not promoted to blocking debt. Branch review remains the broad cold proof
of the resulting code and tests.

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
  Keep the 5,000,000-byte raw response circuit breaker and admit complete extracted text through
  1,000,000 characters. In plan verification, preserve complete-source context. Let a normalized,
  structurally governing primary or authoritative capture that exceeds the ordinary 400,000-
  character batch occupy one dedicated expanded packet only when the exact complete initial and
  correction prompts fit 685,000 characters, recomputing eligibility from the final URL. Carry its
  complete capture into the cold attestation prompt and enforce the same exact prompt bound there.
  Before binding admission, reserve the maximum bounded validation diagnostic, location, passage,
  correction template, and attestation envelope so later output cannot overflow unrelated evidence.
  Pack cold attestation by exact initial-and-correction prompt size into at most five batches and
  allow one same-session validation correction. Persist one closed server-owned capture-provenance
  row per source outcome with explicit nullable response metadata, both digests, fallback fact, and
  bounded error; retain it when an expanded packet cannot be bound or attested.
  Bound the complete evidence phase to 22 model calls (the discovery + five binding + five
  attestation topology and one reserved correction for every initial call) as a pathology guard,
  not a quality target. Whole-plan discovery and its correction each receive 900 seconds; binding
  and cold-attestation calls retain 300 seconds. Admit an initial call only when both its call-count
  and full role-specific latency reserve fit the remaining monotonic deadline. Before the first
  model call, reserve the complete maximum model/retry graph plus explicit non-model
  capture/processing time and scheduling slack.
  Use the same pure prompt renderers for preflight and invocation and test the exact strings; do not
  maintain parallel size estimates.
  Packet and latency limits are circuit breakers, not
  irretractable evidence-quality budgets. Deduplicate
  identical final-URL/content/text captures only within one
  binding prompt or batch, using an earlier-row reference bound to all three values. Count actual
  numbered, metadata-bearing, JSON-escaped representations against aggregate binding budgets.
  When distinct arbitration captures exceed its single prompt budget, deterministically demote
  the largest capture groups to bounded server-owned binding-budget failures until it fits;
  preserve the remaining research and do not add a model call.
  Apply the same per-source failure when a row is ineligible for expansion or its complete expanded
  prompt cannot fit; never silently truncate an admitted page or let it abort unrelated plan
  evidence. Bound model-authored binding fields before downstream attestation, and bind replacement
  evidence against the replacement proposition rather than the original proposition. Bypass model
  binding for unavailable captures so omission cannot overwrite a known capture failure. A failed
  dedicated expanded call is a diagnostic-retaining source-local failure; continue unrelated
  batches and preserve its requested location, nullable effective HTTP(S) final URL, response
  metadata, fallback fact, and capture digests. A non-web context location remains a valid
  uncaptured provenance outcome and must not invalidate independently captured HTTP(S) evidence.
  Partition unavailable captures before row construction, materialize their server-owned decision
  directly, and never expose them to provider binding output.
  Retry HTTP 403 at most once with a browser-compatible user agent, a fresh redirect counter, and
  the original absolute deadline and public-address/final-URL policy. A persistent 403 remains
  unusable and retains final URL, numeric status, bounded error, and retry fact; never add cookies,
  browser automation, access-control bypass, third-party mirrors, snippets, or provider bodies.
  Validate retained inventory before capture; attest replacement wording as its own exact
  proposition; and enforce aggregate capture/binding budgets so multiplicative per-claim maxima
  become visible debt rather than an hours-long run.
  Reject a sixth exact binding or cold-attestation batch globally before that role settles a
  prefix; aggregate ceilings must never become cross-round pagination.
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
  Record the timeout actually supplied and the local monotonic duration on every claim and staged
  attempt, retaining any provider-reported duration separately;
  acceptance must validate execution telemetry rather than infer it from role names.
  Successful attempts retain actual return code and the same separate bounded, hashed raw output,
  structured-detail, and stderr channels as failures; acceptance may not permit null placeholders.
  A same-snapshot legacy claim-only phase migration is a zero-call transition and must run before
  admitting any positive structural model reserve.
  Enforce the reserved non-model capture/pre-binding interval as one aggregate monotonic deadline;
  it may not consume time reserved for later model phases.
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
  Reject an extracted claim proposition that introduces a form from the closed, documented
  `UNIVERSAL_FORMS` grammar absent from its verbatim plan wording before capture. This is an
  operational pre-capture guard, not a claim to decide every English expression of scope.
  A failed source capture remains
  blocking, but durable/rendered diagnostics must identify retrieval failure and must not
  tell the author to weaken or remove the proposition solely because retrieval failed.
  Response acquisition, text extraction, and the aggregate capture/pre-binding processing
  deadline are retrieval-stage failures even when response metadata and a content digest are
  available.
  Preserve server-owned binding and attestation failure phases distinctly and render
  phase-specific retry guidance rather than relabeling either as retrieval failure. Preserve
  every affected phase for mixed and partial source failures; processing failure alone never
  warrants editing the proposition. Render a failed sibling's phase and retry even when another
  independently adjudicated source keeps the claim supported or refuted, without demoting that
  verdict or removing replacement guidance.
  Ordinary terminal provider or role-admission failure must
  carry that same server-owned phase through durable claim debt and rendered recovery guidance.
  Terminal evidence validation debt retains the initial and corrected attempts as separate,
  ordered bounded channel records. Unexpected parallel capture-worker failure becomes retrieval
  debt and retains bounded metadata for every sibling completed before the group failed.
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
  a new plan snapshot's census and the final regression are broad and cold. Plan correction is
  targeted to open findings/classes, claimed corrections, and transitive effects until it starts
  with one or two blocking units; that closure-candidate correction uses the same single call but
  also scans the complete plan against the full checklist and all active classes for sibling and
  repair-created defects. It still advances only to an independent cold final and does not promise
  a fixed round count. When a finding changes a rule, value, schema, lifecycle, or ordering
  contract, require its evidence and remedy to cover every material co-asserting site in the
  complete artifact, including definitions, call sites, tests, and fixtures in branch review.
  When correction or final assesses an unmechanized active class, use its durable invariant and
  procedure—not its current finding, debt wording, known anchors, or claimed patch—as the search
  boundary. Enumerate and inspect every site/property category named there before satisfaction or
  closure, account explicitly for empty or inapplicable categories, and aggregate every surviving
  occurrence into the class's one finding. Mechanized classes retain their server-run predicate.
  Preserve standalone lifecycle actions, but require an authored evidence-bearing satisfied
  outcome whenever correction closes an otherwise outcome-optional unmechanized class; a bare
  close action never proves the invariant-wide search completed.
  Retained acceptance for the plan-restatement duty must exercise both broad plan roles through
  the public handler, bind the complete executable package source, and reconstruct each exact
  provider invocation, returned result, replayable audit projection, and durable successor from
  source-derived initial state. Retain raw provider stdout as the sole text-channel authority;
  derive parsed response, session, usage, and failure detail through the bound extractor, retain
  the observed subprocess return code separately and apply it during replay, and exclude
  non-reproducible process stderr and wall-clock observations from the proof.
  For each existing class, aggregate every independently anchored current occurrence into its one
  governing finding and bounded all-site remedy; keep the one-finding/outcome settlement shape.
  Before predecessor debt can close, require the fresh governing finding to contain every
  current-occurrence anchor independently authored in its matching violated class outcome; report
  omissions at provider-owned JSON Pointers through the bounded retry.
  Apply the same containment rule to a non-debt-bound correction occurrence before deriving its
  violated outcome from `classification.assessment_evidence`.
  A fresh aggregate finding must close every prior open debt bound to that class after including
  every still-reachable predecessor occurrence; never retain narrower and aggregate blockers side by side.
  After any correction settlement, at most one open debt may remain bound to an active class.
  The server-owned correction gate, not reuse of a historical debt ID, rejects a rephrased finding
  that leaves the class blocking. Do not add prior-plan persistence or textual
  duplicate heuristics for this semantic task. Tracked branch review uses the same broad cold census, targeted correction,
  and broad cold final lifecycle; its external claim register remains out of scope. Do not reopen external inventory for repository
  mechanics or “missing atomic bridges,” and do not repeatedly hunt unrelated unchanged material
  for novelty between the census and final regression.
  Bind a pending cold-final obligation to the engine whose settlement created it. A clean
  final from another engine may not discharge that obligation, though any fresh debt it finds
  still reopens correction. Migrate legacy unowned final state through one fresh census rather
  than guessing an owner.
  During broad plan census and final, proactively inspect for one normative contract asserted as
  independently authoritative at multiple operative sites, even before the copies drift. Require
  one authoritative definition and references or derived projections elsewhere, while exempting
  worked examples, faithful table/prose explanations, generated projections, summaries that
  explicitly defer to the authority, and coincidentally equal tokens. Keep this semantic and
  reviewer-owned; do not add textual duplicate heuristics, a provider call, or unrelated discovery
  during targeted correction.
  Surface every currently blocking class spanning at least three caller round labels with its
  round-label span, current-debt start label, and current reviewer session for `rebut`; do not infer a per-round
  presence count that durable state does not store. Mark any class reopen transition as a reopen
  wave so a prior scope disposition is explicitly re-armed. Early signals are diagnostic; the
  bounded correction/reopen limits below are load-bearing settlement gates.
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
- A terminal claim-role failure is audit failure, not a semantic verdict on every claim. Preserve
  packets as non-governing history, but call them last accepted only when a successful claim audit
  is bound to the exact same plan snapshot. On a first-audit failure or a changed-plan structural
  preflight, omit prior semantic remedies and counts from current actionable output and label any
  retained rows non-adjudicated. Render `CLAIM-CLOSURE: AUDIT-FAILED`, and expose aggregate
  claim-plus-structural attempt telemetry so recovered validation retries remain visible.
  Predecessor terminal-debt rows already rewritten by the old failure path are non-adjudicated,
  never last-accepted verdicts or counts.
- Claim debt blocks combined plan convergence but never rewrites the independently settled staged
  structural phase or masquerades as staged structural debt. Render claim and structural closure
  separately before the single governing combined convergence verdict.
  Migrate an exact same-snapshot legacy `correction` phase directly to `clear` only when it has no
  blocking structural debt, blocking or unbound class, staged failure, or ambiguous persistence;
  retain claim debt and spend no correction/final provider call for that migration.
- When discovery and its single correction both fail local claim-payload validation, preserve the
  ordered bounded validator reasons and exact initial/correction raw exchange; do not describe a
  successful provider process as a reviewer execution failure.
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
Classify terminal cleaning failures by the actor who can repair them. Caller-owned advocacy in the
original decision/options/hints, context, or stakes is `caller-framing-rejected` and must retain the
exact field/passage diagnostic across the bounded retry. Cleaner output/protocol failure remains
`cleaner-rejected`; attester output/protocol failure remains `attestation-rejected`. Never add a
keyword lint that claims to replace semantic cross-vendor attestation.
Treat an option's ordinary proposal as content, but require original-neutrality failure for embedded
meta-selection language that calls the option correct, directs its selection, or tells deciders to
disregard contrary evidence or tradeoffs.
Require every stakes/context advocacy verdict to be a closed field-and-passage object whose nonempty
passage occurs verbatim in that exact caller field. Keep fallback-ineligibility evidence separate
from the terminal attempt owner so a later cleaner or attester protocol failure cannot be relabeled
as caller fault; persist it as `fallback_ineligibility_diagnostic` without letting it override the
terminal status or terminal `caller_framing_diagnostic`. A valid fidelity, cleaned-neutrality, or
cleaned-candidate rejection is cleaner-owned; malformed or oversized attester output is
attestation-owned. Bound attester replies independently as strictly as cleaner replies.
Real-provider failure acceptance must parse the retained report and require its headline, exact
reason/diagnostic, `ARBITRATION`, `CLEANING`, `ROUNDS`, and `AUDIT` projection to agree with the
validated audit; a report digest alone is not semantic agreement.
When the cross-vendor attester finds a cleaned semantic change or cleaner-introduced bias but judges
the original decision/options/hints neutral, use the exact original cleaner-owned packet atomically;
never mix original and cleaned fields. Context and stakes remain independently advocacy-gated, and
an advocating original packet must still be faithfully neutralized or fail.
Cleaning may normalize presentation but must never copy facts, constraints, caveats, or
qualifications between options merely to equalize length or detail. Preserve substantive asymmetry
for the deciders. A neutral factual statement that a prior decision exists and governs the current
bytes is context, not advocacy. Substantive facts, governing constraints, costs, risks, tradeoffs,
and consequences remain merits context even when they affect options unequally; asymmetry alone is
not advocacy. Directives, endorsements, rhetorical preference, pre-emptive conclusions, or an
instruction to follow a prior result remain advocacy.

Use `apply_patch` for edits and preserve unrelated user changes. Add focused tests for root
invariants and the real model-facing schema. Model JSON examples must contain concrete valid
literals—never `"fact|decision"` or similar pseudo-enums—and correction prompts must name the
actual validation error. Record production diff size, largest modules, model-call count, and
real elapsed time.

After implementation and docs pass locally, run Codex paranoia against the code with the frozen
stakes. Accepted findings trigger one coherent change followed by a focused rerun; recurring
classes trigger an architecture checkpoint, not endless patching. Do not open/merge a PR while
real acceptance, tests, implementation convergence, or documented stakes remain unresolved.

Persistent staged correction is a gate, not merely a trailer warning. After six unresolved
caller-supplied round labels or three undisposed reopen waves, reject another correction that
leaves the same class canonically blocking. Admit only a canonical close/replacement or a durable
class-bound rebut against the stored current session and exact open debt. Bound rebut output is a
closed CONCEDE/HOLD disposition: HOLD is audit-only; CONCEDE closes only the named debt and closes
the class only when no sibling blocker remains. It never grants clearance. Preserve this state
atomically with the lineage and store the exact returned trailer in plan and branch audit records.
Persist a validated CONCEDE as a closed optional concession on that exact debt, separately retaining
the original finding proposition/evidence and the concession reason/evidence/snapshot/round. Every
later staged role receives the latest concession for each non-superseded active class. A fresh
finding, reopen, or replacement targeting such a class must explicitly challenge that adjudication
with new resolved evidence; unrelated snapshot or stakes changes do not erase it. This is a
challenge requirement, not an exemption: changed relevant evidence can still reopen the class.
Build one canonical closed prior-concession projection, enforce its aggregate cap prospectively in
the rebut transaction and again before provider work, and bind its exact bytes to prompts, cache,
settlement, and audit. `class_closure.MAX_ACTIVE_CLASSES` is the sole numeric active-class authority;
all schema, registration, provider, policy, and test projections derive from that symbol.
Mechanized branch classes remain owned by the canonical predicate sweep: refuse their bound rebut
before provider spend and require `critique_branch` to decide closure.
The durable row is exactly `reset_round`, `reopen_count`, and `last_session_ref`. Current-attempt
session authority replaces stale authority even when it is null; a terminal gate bootstrap may
use only the exact validation-invalid terminal retry and only for a previously sessionless row.
Clear session authority when a class becomes closed or advisory, and accept a bound rebut only for
a currently blocking class in correction phase whose named open debt binds only that class. Refuse
settlement while staged/format/validation failure or an unbound blocker exists. Repeated/backward caller labels refuse before provider, cache, snapshot,
or worktree work, returning a zero-attempt blocked review whose exact trailer is audited; forward
jumps count and failed labels may retry. Provider/validation failure does not advance substantive
state, and ambiguous lineage or rebut saves retain the pending latch. The rebut audit retains the
complete prior target debt row separately while current closed-debt evidence records the concession
citations.
Persist the reviewed plan line count in staged plan state and resolve repeated plan rebut anchors
against that bound; absence of a trustworthy bound refuses plan-anchor settlement.
Keep `rendered_trailer` as the exact returned suffix and `correction_gates` as its ordered pre-call
server-owned audit projection.
Bind bounded attempt-channel digests and exact retained response evidence to the acceptance
artifact's committed Git blob during replay; generation runs the same semantic validator before
that immutable envelope exists.
