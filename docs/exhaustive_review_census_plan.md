# Staged census for tracked plan review

Status: the plan and branch lifecycles are activated. The plan replay proved a material efficiency
win; branch replay proved stronger controlled coverage but not a comparable efficiency win.

## 1. Outcome and proportionate stakes

Tracked `critique_plan` reviews should front-load independent structural
coverage, correct one consolidated finding set, and converge through targeted closure plus one cold
full regression. They should stop using every correction round as another novelty-maximising review
of unchanged material.

The same architecture serves tracked `critique_branch` without the external-claim phase. It uses a
broad cold census, targeted correction, and a mandatory broad cold final regression.

Operating model: one trusted operator and OS; first-party repositories; plan/repository bytes and
model replies are untrusted data. There is no hostile same-user race, compromised OS or provider,
multi-tenancy, public service, adversarial process environment, or deliberate quota exhaustion.
Real inputs include plans around 300 KB, existing branch packets up to 400 KB, and tens of findings.
False structural clearance is high impact. Visible blocking, one bounded format correction, or one
additional cold regression is recoverable. Material correctness and evidence quality come first;
useful wall time, subscription cost, and a small maintainable architecture follow. Exclude generic
workflow engines, security hardening, project-specific rules, automatic source edits, formal proof,
and numerical round ceilings that convert incomplete review into clearance.

The server freezes the normalised stakes text and digest in lineage state. A changed or absent
calibration invalidates frozen claim support, reopens active unmechanised classes for re-triage, and
starts a new claim inventory and structural census. It does not mix clearance made under unknown or
different stakes.

## 2. Evidence before implementation

The earlier design attempted to prove semantic completeness with one status per paragraph, hunk,
search term, and discovered consumer. That created a second analysis protocol, Git-search
calibration, large manifests, and maximum-shape problems. It was disproportionate: a parser can
prove that a model filled fields, but cannot prove that the model understood every premise. The
mechanical guarantee should instead be exact retention of every blocking finding the reviewers
actually report, complete ownership of a fixed stakes-bounded responsibility checklist, durable
debt, and a mandatory final cold review.

A blinded disposable prototype tested that smaller architecture against the exact first input of a
representative 16-round historical plan lineage:

- lineage: `parallax~3~A3-HOLD-TERMINATOR~plan`;
- repository commit: `1376093e6d8febd0fd35d580b4390ddd45118675`;
- plan SHA-256: `5cce5bf952455959cf69dfbae74120c03386746eca2888316a2a58592606300d`;
- three independent Codex lanes plus one consolidation call;
- elapsed time: 691,728 ms; valid model calls: four;
- lane findings: 5 domain, 7 execution, and 7 integrity; consolidation produced eight blocking root
  findings.

Without seeing the historical findings, the prototype recovered the material numerical
movement-image error, null-CIK/reused-identity error, missing digest/input closure, wrong executable
consumer, incomplete artifact contract, acceptance gaps, card-base mismatch, and non-executable
escalation path. The existing first-round external-claim verifier separately registered eight
external claims for this frozen input, with three refuted and five unverified, covering the
historical evidence-authority failure. The frozen method, sessions, governing results, and
raw-output digest are recorded in `docs/exhaustive_census_prototype_evidence.md`; no acceptance
premise depends on the temporary raw file.

This is sufficient to proceed with the small architecture, not sufficient to ship it. Before PR
creation, repeat the comparison through the implemented path and add a representative 10–19-round
changing-branch fixture as described in section 7.

## 3. Lifecycle

The staged lifecycle applies only when tracked class closure is enabled. One-shot and explicit
`converge:false` behaviour keep their current single-call contracts.

### 3.1 Census

A new lineage or materially new clear snapshot runs three independent lanes concurrently against
the same immutable plan/repository snapshot, frozen stakes, and captured external-claim packets.
Each receives the complete artifact and existing repository tools. Plan lanes are `domain`,
`execution`, and `integrity`; branch lanes are `behaviour`, `execution`, and `integrity`.

Each lane owns the same fixed checklist from its perspective:

1. complete artifact and stated requirements;
2. repository/current-behaviour premises;
3. inputs, transformations, outputs and calculations;
4. consumers, callers and blast radius;
5. failure and recovery paths;
6. tests and acceptance;
7. documentation and operator workflow;
8. cross-section/component consistency;
9. simplicity, proportionality and scope.

The `integrity` lane also receives every active class, including closed unmechanised and closed
mechanised classes, with its invariant, severity, state, and procedure or pattern/pathspec. It must
assess each as `satisfied|violated` with a resolved anchor. Each `violated` assessment must
name a source finding. Settlement maps every assessment ID exactly once: `violated` requires open
concrete debt through the same governing finding as that cited lane finding and, when the class was
closed, either `REOPEN` for an unmechanised class or one atomic `REPLACE` that retires
the predecessor and creates an open successor with the corrected invariant, severity and procedure.
`REPLACE` is the staged representation of existing supersession semantics; it never emits a second
transition against the predecessor. Its successor may use either supported mechanism independently
of the predecessor, and any governing debt binding moves atomically to the live successor before
phase calculation. A satisfied open unmechanised class requires `CLOSED`; a
mechanised class remains governed by its snapshot predicate. No transition is needed for an already
closed satisfied class. Omission, contradiction, or two operations against one class
rejects the whole settlement. This makes recurrence mechanically blocking before a blocker-free
census can use immediate clearance without repeating the class context in all three lane prompts.

The lane returns one strict JSON manifest: its lane, every checklist ID exactly once with
`covered|finding|not_applicable`, a bounded summary, one or more resolved evidence anchors, and the
IDs of findings governing that row. A `finding` row must name findings, other statuses must not,
and every lane finding must be named by at least one checklist row. The manifest also carries every
required integrity class assessment and every finding with lane-scoped ID, severity, summary,
resolved evidence anchors, and remedy. Stakes and snapshot identity are server-owned inputs; the
manifest is governing and extra prose is rejected.
The server rejects missing/duplicate checklist IDs, dangling or unbound findings, invalid severity,
and unresolvable plan/repository/diff anchors. Repository anchors may not traverse repository
symlinks; Codex's server-owned `repository/` launch alias is resolved to the inert tree before
validation. Anchors must name ordinary files in that tree. It does not claim to validate semantic entailment or enumerate every
paragraph and hunk. One same-session correction names the exact schema error; a second malformed
reply visibly blocks the attempt.

One consolidation call receives the parsed findings, checklist digests/summaries, integrity class
assessments, frozen stakes, and current class IDs/invariants. Claim packets and repeated lane prose
are omitted: their structural conclusions are already present in validated findings. Consolidation
groups shared root causes without conducting another broad review. Its one staged JSON envelope
contains every source-finding disposition, integrity-assessment disposition, governing finding,
concrete-debt record, explicit finding-to-class disposition, and class registration/transition in
structured form. Every governing finding is classified exactly once as a genuine one-off, a new
reusable class, or an occurrence of an active class. Every `new` class record is referenced by
exactly one new-class disposition; a violated active-class assessment binds its governing finding
to that same class. Multiple occurrences of one active class consolidate into one governing root
finding and one violated assessment in census, correction, and final. Missing or duplicate
dispositions, extra existing-class findings, and unbound new records reject the complete
settlement. Every source finding of every severity is mapped at least once and every integrity
assessment exactly once. A single atomic source finding may fan out to distinct governing findings
when it is an occurrence of multiple active classes; each source-to-governing pair remains unique,
and every target of that repeated source is an existing-class governing finding with its own
matching violated assessment citing the same source. Repetition cannot manufacture one-off or new
class debt from a single observation.
The governing severity
cannot be lower than any merged source; every blocking governing finding and every governing
finding referenced by a violated class assessment maps to exactly one open concrete-debt record,
including advisory findings whose debt does not gate convergence. The server parses the complete envelope into the existing
`Register`/lineage types, validates all fields, then applies finding and class state atomically. A
missing source or assessment ID, dangling merge, missing blocking debt, unsupported class
transition, or prose-only blocker rejects the whole envelope. The staged JSON is an adapter into
the existing class engine rather than a second closure implementation. The legacy terminal text
class block remains only on unstaged one-shot paths, but staged output still renders the canonical
`CLASS-REGISTER` and `CLASS-CLOSURE` trailer (including minted IDs and blocking class detail) beside
the single governing structural convergence verdict.
If lineage loading or persistence is ambiguous, both fields remain present but class closure is
`STATE-UNAVAILABLE`; in-memory counts are not represented as confirmed durable state.
For a satisfied open, unmechanized class, the server derives the deterministic `close` transition
when consolidation omits it; the prompt still asks for the explicit record. The model supplies the
assessment judgement, while the server owns its fixed lifecycle consequence.

A valid census costs four model calls over two serial wall-clock phases. The bounded worst case is
eight calls when all four replies need their one format correction. All limits use Python Unicode
characters. The existing `MAX_PACKET_CHARS = 400_000` branch evidence-packet contract remains
unchanged. Plan review passes the complete active claim register and current retirements; it does
not truncate evidence that may change authority or entailment. Each exact staged lane prompt has a
5,000,000-character ceiling, and an oversized prompt persists a visible non-cacheable structured
failure rather than running partially or clearing. Each lane envelope is
capped at 48,000 characters, with 2,000-character summaries/remedies and 512-character anchors.
New class invariant/procedure fields are capped at 1,000/2,000 characters and total rendered active
class context at 64,000 characters. Active-class or lane-prompt overflow is a non-cacheable
structured staged failure of kind `validation`; only terminal consolidation rejection populates
`validation_debt`. Before a lane call, render its exact prompt and reject over 5,000,000
characters; do not truncate a valid evidence packet. Consolidation has no
artifact packet and retains a 400,000-character exact-prompt ceiling; three maximum lane envelopes
leave more than 250,000 characters for its instructions, stakes, and class context. The plan
prototype's complete raw four-call JSON record was 46,708 bytes.

The real lineage census at design time found a largest exact rendered class context of 20,973
characters and a largest procedure of 651 characters, so every existing operator lineage fits. The
measurement used the current plan/branch context renderers and included headings, state, detail,
matches, exemptions and escaping. Persisted state
already beyond the new 64,000-character support boundary returns explicit `STATE-OVERSIZED` with
its path and measured size and cannot clear. Building an autonomous semantic compactor for a
hypothetical legacy shape would add a new review protocol and is excluded under the stated
non-adversarial, observed-scale stakes.

### 3.2 Correction

A later round beginning with blocking debt runs one targeted reviewer. It receives every open
concrete finding, every active open class including advisory classes, surviving mechanised matches,
the claimed corrections, and their transitive effects. Closed unmechanised classes are omitted. The
prompt permits new or reopened findings only when introduced or exposed by the correction; it does
not ask for unrelated novelty in unchanged material.

Its terminal staged JSON envelope accounts for every open concrete finding as `closed|open`, with
resolved evidence for closure, may add a correction-introduced finding, and carries structured new
class records/transitions. The server converts those class records to the existing reusable
invariant model only after the whole envelope validates. Every newly introduced governing finding
uses the same mandatory finding-to-class disposition contract as census. Missing debt, a missing
class disposition, an unbound new class, or an unregistered prose
blocker rejects the reply and gets one bounded same-session format correction. Correction does not
reassess every active class. Consolidation merges multiple occurrences of one reusable class into
at most one `existing_class` governing root finding per active class per settlement. Correction
returns exactly one partial `violated` assessment for each active class with such a finding, using
the same consolidated finding binding; it returns no assessment for other classes. Duplicate
governing rows for one class are rejected rather than adding a second class identity. An
already-open class needs no transition; binding new debt to a closed unmechanised class additionally
requires `REOPEN`, and a closed mechanised class requires `REPLACE`.

When correction closes all blocking finding, class, and claim debt, computed output remains blocked
with `FINAL-REGRESSION: required`. The same round cannot declare final convergence.

### 3.3 Final regression

The next round is one fresh, cold, whole-artifact review using the normal broad reviewer contract,
the fixed checklist, complete current snapshot, frozen stakes, actionable claim packets, and every
active class. Its strict staged envelope uses `role: final`, evidence-bearing checklist results,
findings, concrete-debt transitions, exact-one `class_assessments`, and structured class
records/transitions. The same `satisfied|violated`, debt, `REOPEN`, and `REPLACE` settlement rules
used by census apply through one shared validator. If it finds no new/reopened blocker and claim
closure is clear, the server emits `CONVERGENCE: NOT-BLOCKED`. A blocker returns the lineage to
correction and requires another final regression after repair.

A census with no blocker may converge immediately: three independent broad lanes already supplied
the cold review. There is no arbitrary maximum round. Repeated root classes remain visible and
trigger the existing architecture-checkpoint guidance rather than automatic patching.

## 4. Minimal durable state

Extend the existing atomically replaced lineage JSON; do not add a state store. Versioned
`review_state` contains:

- frozen stakes text/digest;
- `census|correction|final|clear` phase;
- last census/final artifact digest; for branches this covers the complete packet, including both
  resolved endpoints and material packet-defining inputs, rather than the head commit alone;
- concrete review debt: ID, severity, summary, evidence, source/class IDs, status and round metadata.

Concrete debt carries exact census findings until correction. The existing class register continues
to carry reusable invariants; claim state continues to carry external evidence. Clearance requires
no blocking debt in any of the three.
An unbound live class remains first-class class debt and is rendered by `CLASS-CLOSURE`; it is not
converted into a synthetic concrete finding. `STRUCTURAL-DEBT` therefore continues to count only
real governing findings, while the class trailer preserves bounded path-level recurrence evidence
using the canonical binary-safe display and the single verdict explicitly names open class closure.

Transitions settle with class results in one atomic lineage write: census with blockers →
correction; census clear → clear; correction with blockers → correction; correction clear → final;
final with blockers → correction; final clear → clear. `clear` plus a changed artifact starts a new
census. Artifact changes during correction remain correction because edits are expected there.

A legacy lineage without `review_state` has unknown calibration and starts a new inventory+census.
Any durable legacy register failure is included verbatim in that cold re-audit and is cleared only
by its successfully settled census. A reopened blocking class without bound staged debt likewise
forces the broad integrity census instead of entering an empty targeted correction.
Plan claim verification still runs before structural review. Valid claim-evidence progress may
persist when structural work later fails or lacks deadline; structural phase does not advance until
a valid structural settlement. Audit logs record phase, stakes/snapshot digests, validated
manifests/dispositions, and one attempt-ledger row for every actual `run`/`resume`: role,
engine/session, outcome, duration, and usage. Aggregate provider calls are the ledger length, never
inferred from a status string. Concurrent structural calls receive a synchronized monotonic
sequence immediately before each provider run/resume boundary and are serialized by that sequence.

## 5. Small code shape

- Add one pure `review_census.py` module for lane/checklist definitions, manifest/disposition parsing,
  anchor validation and consolidation rendering. It contains no provider, Git-search or persistence
  subsystem.
- Extend the existing `Transition` with one `REPLACE` kind carrying successor invariant, severity
  and procedure/predicate. `apply_register` retires the predecessor and creates one open successor
  atomically; this is not encoded as `REOPEN` plus another transition.
- Add census, correction and final instruction blocks in `prompts.py`; retain the existing review
  sections, claim packets and class-register semantics.
- Branch staged roles retain the resolved code-review web-search capability; plan structural roles
  remain web-disabled because their external claims use the separate captured-evidence pipeline.
- Add one shared handler runner for three parallel calls plus consolidation and for the targeted
  correction/final calls.
- Thread the same small attempt-ledger collector through plan discovery, capture binding,
  attestation, every retry, and structural calls; expose its rows in the existing audit JSON.
- Extend current closure preparation/settlement with stakes, phase and concrete finding debt.
- Preserve plan claim verification exactly: authoritative server-captured web evidence remains
  default-on, frozen unchanged supported claims avoid repeat web/model calls, and structural lanes
  receive the complete active claim register and current-round retirements with live web disabled,
  preserving the canonical cold-review invariant. The exact composed prompt is checked before each
  call; existing oversized state returns explicit staged debt and cannot clear.
- Keep `AGENTS.md` and `CLAUDE.md` amendments already made: census/final are broad and cold;
  correction is targeted to open debt and correction effects.
- Update README and tool schemas with default phases, costs, autonomous correction workflow,
  frozen-stakes reset, final-regression gate, and the explicit limit that checklist completion is
  strong review evidence rather than formal semantic proof.

## 6. Deadlines and failure

Plan review keeps a monotonic 7,080-second whole-review deadline and reserves the
complete structural phase before starting it. In both modes, each census lane has a 1,800-second
timeout, consolidation 1,200 seconds, correction/final 2,400 seconds, and a format correction at
most 600 seconds. The three census lanes run concurrently.

Plan evidence gathering can consume most of a request. If the full census reserve no longer fits,
persist valid claim progress, leave phase and structural round unchanged, and return explicit
resumable structural-pending output. The autonomous caller repeats the same round; retained evidence
makes it cheaper. When all three lanes validated and only consolidation failed, the lineage retains
those manifests and a retry runs consolidation only if mode, structural snapshot, full review body,
open debt, stakes, active-class state, engine/model/effort/web settings, plan line context, and cache
schema all match exactly. The digest includes the exact composed prompt bytes for every lane, so an
instruction-contract change invalidates reuse. Persistence requires terminal validation rejection; incomplete lanes,
failed validation retry, execution failure, timeout, cancellation, or any binding change force a
fresh immutable census. Parser and semantic settlement failures are logged as
`validation-invalid`, not misclassified as format-only failures. Only terminal consolidation
validation populates `validation_debt`. Lane/follow-up validation and every execution-class failure
first delete any older cache and persist as structured `staged_failure` with exact role, kind, and
message; consolidation preflight validation does the same. Engine outcomes preserve timeout,
unavailable executable, in-band provider error, and other execution failure distinctly, including
the same `*-validation-retry` role in failure state and attempt telemetry. They cannot authorize reuse.
Terminal validation debt also persists and renders that structured role, kind, and message.

The supported local runtime is a trusted execution boundary, not an externally researched factual
premise. Preflight uses the exact rendered request bytes and the tool's existing conservative local
caps; a provider refusal, truncation, timeout, malformed response, or exhausted deadline visibly
blocks and cannot settle review state. Pinning provider versions, researching advertised context
windows, or treating the monotonic clock as an internet claim would not establish what happened in
the current invocation and is outside the frozen stakes.

## 7. Tests and acceptance

Pure tests cover manifests, every schema rejection, consolidation retention/merge/severity,
resolved anchors on every checklist row and finding, all-source/all-assessment disposition, phase
transitions/migration, stakes reset, concrete debt and deadline arithmetic. They also prove that a
closed active class recurring in an otherwise clean census is assessed by the integrity lane,
registered as durable debt, and blocks clearance.

Scripted handler tests cover the four-call valid census, structural-only tracked plan entry,
one bounded format correction, correction → required final, complete final coverage/class
assessment, exact severity/debt retention, resolved anchors, atomic `REPLACE`, attempt logging, and
the unchanged injected-engine/one-shot contracts. Real acceptance below supplies the provider and
maximum-real-input coverage that fake-backed tests cannot establish.

Plan activation gates:

1. full local suite;
2. simulated plan census → correction → final, including failures and audit fields;
3. real Codex plan review convergence under section 1 stakes;
4. real Codex implementation review convergence under the established branch-review path;
5. blinded replay of the recoverable 16-round plan fixture above through the implemented path,
   with frozen historical-class oracle, provider-call count and monotonic elapsed time;
6. each new plan census must recover every applicable historical FATAL/MAJOR root class without an
   unresolved new FATAL/MAJOR false positive. Targeted correction must close repaired roots and
   retain any material defect still present in the historical bytes; old convergence is comparison
   evidence, not authority to force a new false clearance. The implementation's own convergence
   run must use the staged correction/final lifecycle, and measured wall time/call cost must be
   reported rather than waived;
7. acceptance records with fixture/digest/oracle/result metadata committed under `docs/`. The
   completed final review's invocation metadata remains in its immutable audit log and PR/handoff
   report: committing a statement that the current commit passed a later review would change the
   reviewed snapshot and make that statement self-referentially stale;
8. only then open a PR, pass CI, merge, and update the primary `main` worktree.

Branch activation rests on stronger controlled coverage rather than an all-metrics efficiency
claim. The first comparison improved quality but used 14 calls versus 10 and more tokens; a later
representative replay likewise found additional material defects without proving a comparable cost
win. Branch staging therefore must not be described as guaranteed to use fewer calls or tokens.
