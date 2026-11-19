# Issue 150: bounded claim-binding growth and local failure diagnostics

Stage transition: PLAN rounds 1–3 are retained as blocked design-review evidence.
Their remaining obligations are incorporated below and must be discharged by
deterministic acceptance and broad CODE convergence. Implementation begins after
this design review; this document does not claim PLAN convergence. All repeated
numerical examples and delivery checklists defer to the executable policy authority
and named qualification gate below rather than establishing independent rules.

## Scope and operating model

One trusted local operator and OS run this local review tool. Plans, repository bytes,
and public HTTP(S) content are untrusted data. No repository-selected execution,
hostile local race, multi-tenancy, compromised OS, or corrupted-state recovery is in
scope. Typical plans have tens to low hundreds of claims; useful evidence should
arrive within minutes. False clear, wrong authority, and wrong evidence binding have
high impact; recoverable blocking is acceptable. Preserve the existing parallel
capture pool, model roles, per-call timeouts, and one validation correction per call.

## Design

The old five-batch limit is a hard aggregate guard, not a claim-quality rule.
Existing unchanged supported packets already freeze across rounds; do not weaken
that qualification, cache unresolved claims, or settle batch prefixes across rounds.

1. Preserve a bounded server-owned failure reason on evidence-phase reviews and
   project it into durable claim debt and the returned evidence status. Preserve
   actual raw provider output, failure detail, stderr, phase, return code, and ordered
   attempts separately. Local pre-call failures must not invent provider attempts or
   identify an empty response hash as the explanation. Cover capture, binding, and
   attestation, including local batch and deadline rejection.
2. Derive a binding and attestation batch allowance from the current discovered
   claim count: five through 25 claims, then one additional batch per five claims,
   rounded up, with a maximum of ten. Thus 36 claims admit eight batches. Both
   phases use the same allowance. Keep exact complete prompt bounds, expanded-source
   admission, capture digests, indexed passage checking, authority, and cold
   attestation unchanged. Exhausting the allowance rejects the entire role before
   any of its model calls, never settling a prefix.
3. Scale capture/pre-binding time from 300 seconds through 100 candidate sources
   to 600 seconds for 200 sources, rounding up proportionally. Retain the 200-source
   hard cap and source-local limits. Start that clock after discovery. Reserve the
   complete maximum graph before discovery: 42 calls (discovery plus ten binding
   plus ten attestation, each with one correction), both 900-second discovery
   windows, all 300-second later-call windows, the maximum 600-second local reserve,
   and 60 seconds scheduling slack. Derive overall and documented client timeouts
   coherently; these are circuit breakers, not expected latency or quality targets.
4. Explain actionable recovery: unchanged-input replay cannot repair a fixed
   ceiling; inspect the exact count/limit, keep assertions and authoritative source
   requirements intact, and split independently reviewable plans with explicit
   cross-plan obligations or reduce redundant candidate sources. A genuinely
   transient capture/provider failure may retry its phase. Preserve failed historical
   reviews and resume their existing lineages after this repair.

## Acceptance and delivery

The following details close the initial PLAN census findings and govern the numbered
design above. They are implementation obligations, not claims of completed execution.

All numerical rules in this document are worked projections of the single executable
authority in `handlers.py`: `MIN_PLAN_EVIDENCE_BATCHES`,
`PLAN_CLAIMS_PER_EVIDENCE_BATCH`, `MAX_PLAN_BINDING_BATCHES`,
`MAX_PLAN_ATTESTATION_BATCHES` (derived from the binding maximum),
`PLAN_EVIDENCE_VALIDATION_CORRECTIONS`, the discovery and later-role timeout constants,
`PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC`, `PLAN_SOURCES_PER_CAPTURE_RESERVE`,
`MAX_PLAN_CAPTURE_SOURCES`, scheduling slack, preparation/teardown reserves and
`PLAN_REVIEW_CLIENT_MARGIN_SEC`. `_plan_evidence_batch_limit(count)` and
`_plan_capture_reserve(count)` own the two scaling functions. Graph, maximum local
reserve, evidence deadline, whole-call deadline and `PLAN_REVIEW_CLIENT_TIMEOUT_SEC`
are derived expressions. Active guides and recovery instructions defer to these
definitions; tests assert independent worked boundaries to catch drift. The runtime
client imports the derived timeout only after its existing source admission checks.

Named production entry point and acceptance obligations:

- `test_issue150_public_final_validation_is_terminal` exercises
  `handlers.critique_plan` after a completed captured graph, separately injecting
  outer parse and retained-coverage rejection with spare and exhausted capacity,
  including a successful in-role validation correction. The terminal phase is
  `binding` (final captured-audit materialization/coverage), kind `validation`.
  Preserve the exact local validator reason and earlier in-role validation context
  in the ledger. No outer correction or repeated attestation may dispatch; actual
  raw stdout, detail and stderr remain separately hashed. A local final decision
  has no provider exit code of its own; completed provider exit codes stay on their
  actual attempt rows. Compare report, audit and reloaded debt. Ordinary injected
  non-captured audit retries remain covered by the existing lifecycle tests.
- `test_issue150_discovery_correction_failure` exercises public `critique_plan`
  for invalid initial discovery followed either by local correction admission
  refusal or dispatched correction execution failure. Extend the closed phase
  vocabulary with `discovery`. Preserve initial validation context and exactly the
  started discovery attempts and channels. A local refusal has kind `admission`
  and a server-owned exit 124; execution failure keeps the provider's code and kind
  `execution`. Report, audit and reloaded debt must agree, with no capture or later
  role calls. Existing successful discovery correction and retained-omission
  behavior remain unchanged.
- `test_issue150_recovery_guidance` covers terminal and per-packet guidance through
  `plan_claims.render_trailer` and `_render_claim`. Update both claim_verification
  and how-it-works guides. Higher-round `critique_plan` re-discovers/re-captures and
  re-adjudicates unresolved, refuted or changed packets. Independently supported,
  unchanged packets can freeze, including a supported packet with a failed sibling;
  explicitly say that frozen sibling is not retried unless the assertion re-enters
  verification. Do not promise phase-only retries or evidence-refresh calls.
  Preserve supported/refuted decisions and assertion wording. Limit failures name
  actual counts and allowance and require bounded input change; legacy debt has
  conservative public-entry-point guidance. The public failed-lineage fixture must
  both recover with full adjudication and remain blocked on repeat rejection.
- `scripts/run_claim_binding_150_acceptance.py` is the executable native qualification
  route. Its frozen fixture is: `# Release premise\n\nPython 3.11.0 was released on
  October 24, 2022.\n`, followed by a blank line and a candidate-source link to
  `https://www.python.org/downloads/release/python-3110/`, with a captured release-date
  passage. Run tracked `critique_plan` with Codex and a dedicated stable lineage,
  POSIX synthetic fixture repository containing one committed README, preserving all
  original rounds and failed trials. A passing receipt binds the
  complete loaded production source inventory/hashes and committed delivery revision,
  exact request/input, lineage and rounds, report/audit/reloaded-state bytes and hashes,
  ordered attempts and elapsed wall time. Check the exact expected claim and its
  matching indexed URL, final URL, content/text digests, passage and true cold
  publisher-authority and entailment judgments. Require completed zero-return-code
  discovery (or its valid same-session repair), binding and attestation attempts,
  nonempty matching supported state and report, no claim audit debt, and source
  identity unchanged at finish. Missing, mismatched or failed evidence withholds
  delivery. Native structural convergence for this fixture is not implementation
  acceptance; the CODE lineage remains the independent merge gate. Its receipt
  validator also requires actual requested role timeouts, measured local durations,
  return codes and separate bounded/hashed stdout, detail and stderr channels for
  every attempt. A validation-invalid initial reply needs a successful same-session
  correction of that role; any failed attempt, missing channel, timeout or duration
  mismatch rejects qualification. All delivery clauses refer to this same gate.
- Final local materialization rejection retains the completed graph's ledger and
  exact validation diagnostic as referenced by the returned audit path. Debt has
  phase `binding`, kind `validation`, null terminal return code, actual aggregate
  returned raw/detail/stderr channels and explicit empty failed-batch attempts.
  It names no failing provider batch. The preceding successful repair and initial
  validation context remain in the complete audit ledger. Public tests compare
  report reason/phase/kind/audit reference with audit and reloaded debt channels.
- Discovery correction tests also cover completed invalid correction content and
  missing correction session metadata, retaining both validation contexts, phase
  `discovery`, and exactly the actual attempts. Preserve successful correction and
  the narrowly permitted retained-omission exception; no downstream calls on failure.
- One failure-kind-driven recovery helper governs terminal and actual per-packet
  output, both guides, llm-reference and AGENTS. Public report tests cover overflow
  counts, transient replay recovery, frozen siblings and legacy fallback. Every
  admission/rejection/expiry diagnostic uses the authoritative policy calculation.
  The positive client margin is 120 seconds, defined only by its named constant.

- Define the batch allowance once (five baseline, five claims per batch, ten maximum),
  and derive both role maxima, call count, maximum local reserve, evidence window,
  whole-call window and executable client timeout from those independent policy inputs.
  The evidence window includes scheduling slack; pre-discovery required work excludes
  that slack. Worked values are 14,460 evidence seconds, 14,400 required work seconds,
  14,880 whole-call seconds, and 15,000 client seconds. Test nonzero preparation,
  equality and just below admission equality; only the last refuses discovery.
- Captured discovery, indexed binding and attestation already own their bounded
  corrections. If the completed captured audit fails outer parsing or retained
  coverage, return terminal phase-aware validation debt; never invoke the old outer
  binding retry and repeat attestation. The ordinary non-captured engine retry remains.
  Preserve its exact validation reason and actual completed channels and ledger.
- The scaled local interval belongs to retrieval until packing completes. Expiry
  detected during capture or real binding packing has the same capture phase and
  effective interval. Role-call admission refusal is distinct. Test both fake-clock
  expiry sites with zero binding attempts.
- Persist a closed server-owned failure kind (limit, deadline/admission, validation,
  or execution) alongside the phase and bounded reason. Preserve legacy debt without
  that field. The complete audit ledger retains all actual calls; terminal debt includes
  only the failing batch's started attempts, including an invalid initial reply if
  admission refuses its correction. A local refusal of B after successful A has no
  invented B response or provider exit code. Test binding and attestation in both
  situations, including separate channel hashes and the local failure identity.
- Recovery names the actual public entry point: rerun `critique_plan` on the same
  lineage with a higher round after addressing the reported problem. Capture and
  research may run again; there is no standalone phase retry API. Limit recovery
  states actual count and allowance and requires a bounded input change, rather
  than another identical request. Preserve assertions and authority. Test legacy
  guidance and both kinds. Seed a failed old-limit lineage, resume it under the
  new allowance with matching fresh evidence and retained claim IDs, preserve prior
  audit bytes, and clear debt only after full adjudication. Rejection stays blocking.
- In the 36-claim public-handler growth fixture, cross five batches in binding AND
  attestation with production packing, distinguishable passages and capture digests.
  Verify every persisted identity, passage and cold decision; wrong-passage and
  wrong-index controls must not clear. For each role test its inclusive allowance
  and one-batch-over refusal before any role call. The maximum fake-clock topology
  must earn ten batches with at least 46 claims and 200 source rows, use exactly ten
  batches in each role and every correction, and verify order, elapsed time and outcomes.
- The native qualification uses a separate frozen input with eligible external
  claims and known official passages. It must complete nonempty discovery, real
  server capture, indexed binding and cold authority/entailment on the changed
  implementation through tracked `critique_plan`. Retain exact source identities,
  input, lineage, rounds, report, audit, attempt order and elapsed time, and verify
  matching supported state. The deterministic growth fixture qualifies the larger
  packet topology; native qualification checks the unchanged provider/capture boundary
  with a small meaningful input. A second campaign of many megabytes of live evidence
  is excluded: this card changes local budgets and diagnostics, not provider schemas,
  prompts, evidence admission or capture transport. Failed native trials remain failures.
- Update `scripts/run_claim_admission_acceptance.py`'s actual ClientSession argument
  as well as current README, llm-reference, how-it-works, claim-verification and
  AGENTS projections. Test executable and published timeout agreement. Historical
  runtime and receipt values remain fixed.

- Deterministic tests through `handlers.critique_plan` and its captured adapter prove
  local binding/capture/attestation reasons survive reports and audit/state, no
  unstarted provider attempt is recorded, and prior claim history remains blocking.
- Exercise the real indexed binding and cold-attestation production methods with
  a 36-claim inventory requiring six to eight distinct complete-source batches;
  require complete evidence and durable supported outcomes, plus exact rejection
  above each derived batch allowance before any calls in that role.
- Test allowance boundaries, maximum-call admission, source-count-scaled deadlines,
  exact prompt limits, validation correction, and frozen-packet reuse regressions.
- Update public documentation and AGENTS before CODE review. Run relevant tests
  and the full suite, refreshing only existing permitted historical allowance
  metadata where necessary; retain original provider evidence.
- Run the primary public claim-verification capability with real Codex discovery,
  server capture, binding and cold attestation before opening the PR. Retain actual
  source identity, attempts, outcome and elapsed time, including failed trials.
- After PLAN design review, implement and converge on CODE with real Codex paranoia;
  no further plan review. Record production diff size, largest modules, model-call
  count and elapsed time. Open, review, merge the PR and update issue 150 only after
  acceptance gates pass. Do not claim to reproduce Alex's unavailable local logs.
