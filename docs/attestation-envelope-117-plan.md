# Issue 117: one unambiguous attestation envelope

The public plan evidence attester can return competing envelopes or stray note fields
after its single correction. Preserve fail-closed parsing and strengthen authoring.

1. Share one exact attestation output contract between the initial cold prompt and its
   existing same-session correction. Require exactly one marker and one complete object,
   only the permitted envelope and row fields, exactly one row per supplied index pair,
   integer identities, Boolean verdicts and nonempty bounded reasons. Put explanations
   inside the two reason fields; prohibit prose, notes, alternate envelopes and suffixes.
   The correction replaces the entire rejected reply. Preserve independent authority and
   entailment judgments and tools-disabled attestation. Preserve existing ordinary packet
   fields and complete captured text for expanded packets; do not broaden ordinary context.
2. Keep the parser, source eligibility, durable evidence semantics, call counts, timeouts
   and retry limits unchanged. The same pure renderers must drive preflight and invocation.
3. Through server.dispatch(critique_plan) and the real Claude engine adapter, supply
   provider-shaped outputs only at the subprocess boundary. Exercise invalid initial then
   valid correction and invalid initial then invalid correction. Include extra fields,
   duplicate envelopes and conflicting rows; assert the original session is resumed once,
   both attempts are retained and only valid authority/entailment can support a claim.
   Retained failure stays attestation-phase blocking debt; no third call or last-object recovery.
4. Update public docs and AGENTS before CODE review. Run relevant tests and full regression
   checks. The issue-117 compatibility exception permits only existing later-source delta
   hashes, line counts and truthful descriptions in the twelve historical acceptance records
   already maintained by this branch. Include authoritative_capture_acceptance_2026-08-20.json
   reviewed_snapshot.allowed_later_handlers_diff, its scope assertion in test_plan_claims.py,
   and the matching closed metadata projection in test_issue115_history.py. Describe the new
   attestation wording as later compatibility, never historical execution; original source
   identities, prompts, measurements, channels, ratings and outcomes remain immutable.
   Retain controls for missing/extra/mismatched allowances and reject changes outside these
   metadata fields; any failure blocks delivery.
   Run a bounded native public verified-plan capability check, retaining original artifacts
   and recording any failed attempt honestly. CODE convergence uses Codex and this exact
   contract; no return to PLAN after implementation merely as acceptance.
5. Merge/push only after tests, native capability and CODE acceptance; fast-forward local
   main and integrate the fix into codex/review-quality-speed without losing its pending
   approved member-ID ownership changes. No general speedup claim follows from this fix.

Acceptance details:
- In tests/test_issue117.py, assert both actual subprocess-bound prompts contain the same
  authoritative contract, all six permitted row fields, the sole attestations envelope key,
  the configured reason limit, independent judgments, whole-reply replacement guidance on
  correction and exact packet preservation. Removing either contract must fail the test.
  Exercise _attestation_prompts_fit and _expanded_source_fits using the actual renderers,
  maximum reserved diagnostics and exact boundary/one-character overflow checks against
  ordinary and expanded limits. Test command: python -m pytest -q tests/test_issue117.py
  tests/test_plan_claims.py tests/test_issue115_history.py. Full gate: python -m pytest -q.
- Native fixture: one fresh nonfrozen external claim about Python 3.11's release date in a
  tiny isolated repository; Claude opus/high, verification and discovery enabled. At least
  one eligible source must be server captured, bound, cold-attested and supported after
  durable reload. Maximum twelve provider attempts, unchanged per-call timeouts, one run;
  forced invalid/corrected exchanges belong only to deterministic tests. No natural retry
  is required. Retain source hashes, requested/resolved configuration, actual prompts and
  separate process channels, audit ledger, bound decisions and reloaded provenance. Verify
  actual attestation prompt identity and at least one completed attestation. Skipped or
  failed capability, exhausted attempts, missing/mismatched evidence or any failed
  qualification blocks delivery. Historical and new native acceptance stay distinct.

Closed historical exception inventory (docs/):
arbitration_consequence_acceptance_2026-08-22.json;
arbitration_context_steering_rejection_acceptance_2026-08-22.json;
arbitration_steering_rejection_acceptance_2026-08-22.json;
branch_plan_fidelity_acceptance_2026-08-22.json;
class_occurrence_batch_acceptance_2026-08-30.json;
class_persistence_acceptance_2026-08-22.json;
keyed_class_handler_acceptance_2026-08-19.json;
mechanized_predicate_acceptance_2026-08-27.json;
persistent_correction_gate_acceptance_2026-08-23.json;
plan_restatement_acceptance_2026-09-01.json;
plan_review_reliability_acceptance_2026-08-30.json.
For these eleven records, only existing allowed_later_source_diffs entries' sha256 and
scope fields may change; no entry may be added or removed. Reliability also permits the
same fields in validation.allowed_later_source_diffs. The twelfth record is
authoritative_capture_acceptance_2026-08-20.json: only reviewed_snapshot.
allowed_later_handlers_diff's sha256, additions, deletions and scope, plus its top-level
scope string may change. Replace that top-level scope's sentence claiming later handlers
do not alter cold-attestation/prompt-size semantics with a truthful statement that this
historical run used its recorded prompts; issue 117 later changes attestation authoring
and exact prompt sizes, requiring separate current-source acceptance. Preserve every other
sentence and field. Give the handler allowance the same qualification and replace only
its obsolete scope assertion in test_authoritative_capture_acceptance_record. Extend the
closed immutable-history test only for those capture fields, checking exact permitted
scope replacement. A comparison against main 7b48159 must restore just this inventory
and obtain complete original JSON equality; missing/extra/mismatched allowance mutations
and an original-outcome mutation must still reject. No original run is relabeled current.

Loaded-source native gate: use benchmark_review_modes.source_record and validate_source
over the complete committed src/paranoia_local Python inventory before and after the run.
Record each loaded paranoia_local module's resolved __file__, require it to be the matching
regular file inside that same frozen worktree, and hash its bytes against the recorded
committed inventory before and after dispatch. Record the same source revision and full
inventory with the invocation, all retained prompts/channels and audit qualification.
Cross-check actual attestation prompts against the captured runtime renderer output and
their native attempt ledger prompt digests. Wrong imported checkout, changed or uncommitted
source, missing module identity, mismatched prompt or missing run binding blocks delivery.

Architecture checkpoint: the late source-binding class concerns acceptance execution, not
the attestation parser. Reuse the existing source-only boundary; do not add another loader,
cache protocol or runtime subsystem. scripts/run_issue117_acceptance.py starts in a fresh
interpreter and rejects preloaded paranoia_local modules or owned benchmark harness modules
before imports or provider admission. Execute scripts/benchmark_bootstrap.py with runpy.run_path
before any owned harness/production import. Then import benchmark_review_modes, validate the
committed inventory, and only then import production modules and obtain the reference renderer.
Bind the entry script, bootstrap and benchmark helper bytes to the same committed checkpoint.
Retain the existing file/prompt/ledger checks. tests/test_benchmark_committed_sources.py's
test_source_only_boundary_ignores_same_tick_stale_production_bytecode and
test_entry_bootstrap_ignores_stale_imported_harness_bytecode establish the reused boundary;
add test_issue117.py subprocess controls through this actual entry script proving usable
adjacent stale production bytecode is ignored and a preloaded owned module is rejected before
native admission. Either control or provenance failure blocks qualification and delivery.
