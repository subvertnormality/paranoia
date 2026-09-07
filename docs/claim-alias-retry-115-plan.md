# Issue 115: unambiguous prior-disposition authoring and repair

## Operating model
One trusted local operator and OS run the MCP server and authenticated Codex/Claude CLIs.
Plans, repositories and provider output are untrusted static data. Reviewers inspect but do
not execute repository-selected code. Ordinary edits invalidate bindings; no hostile local
races, multi-tenancy, corrupted-state recovery or compromised OS. Tens to low hundreds of
claims, existing native concurrency/network boundaries and timeouts, useful evidence within
minutes. False clearance, wrong evidence binding and unjustified blocking have high impact;
recoverable blocking is acceptable. No new calls, transport, persistence or schema cutover.

## Scope
I1. Preserve the accepted language of plan_claims._validate_dispositions: exactly one ID
field from claim_id/prior_claim_id, exactly one reason field from reason/rationale, and
the existing disposition/value/identity checks. Equal as well as conflicting paired aliases
still reject. Preserve existing accepted canonical, alias-only and mixed single-name rows.
Do not broaden or narrow unrelated parsing, normalize collisions or change claim retirement.

I2. Author one shared canonical prior-disposition instruction and minimal valid example.
Use it in exhaustive audit_instructions, targeted_audit_instructions and retry_instructions.
Distinguish disposition-row claim_id/reason from claim-object prior_claim_id/rationale.
Generated rows use canonical names only; aliases remain parser compatibility, not additional
fields to emit. The fixed example is synthetic and instructs substitution of the actual prior ID;
it never authorizes removal of a present claim.

I3. When _validate_dispositions rejects malformed identity/reason shape, retain the exact row
index and name whichever known alias pairs were simultaneously present, without interpolating
unbounded provider values or unknown keys. Give the canonical minimal example in the bounded
existing repair diagnostic. Keep the same single same-session correction, claim-debt retention,
capture admission and structural-review behavior. I4 is the executable acceptance boundary
for this retry contract. No live-search/capture/authority weakening.

## Acceptance
I4. Parser regressions cover equal and conflicting dual aliases, either pair independently,
canonical-only, alias-only and mixed legal pairs. Generated exhaustive/targeted/correction
prompts carry the shared contract. A production-handler correction regression supplies the
reported malformed row: the one retry must receive both offending pairs, the row coordinate
and a valid minimal example. A corrected removal of an absent synthetic prior claim succeeds;
a repeated invalid row retains the prior claim and blocking audit debt. Neither path captures
a page for the absent claim; no extra retry is admitted. Include the public critique_plan
boundary with claim verification enabled and an exact ClaudeEngine, scripting only its
provider subprocess responses or run/resume methods. Preserve _CapturedClaimEngine routing;
a generic injected engine does not qualify. Verify the original resumed session, ordered
claim-discovery and claim-discovery-validation-retry outcomes, both alias-pair diagnostics,
row coordinate, zero page captures, durable retirement after repair, and durable audit debt
plus blocked combined convergence after repeated invalid output. Bypassing the adapter or
admitting a third discovery attempt fails delivery. Verify durable state, not strings alone.

I5. Before delivery run the affected tests and full suite, then one source-bound native
Claude opus public critique_plan acceptance with verification enabled, an absent synthetic
prior anchor and no current external assertion. Require truthful claim closure and retained
native prompts/channels/audit/state; record the resolved model and all attempts. Do not inject
a fake success, disable verification, use provider snippets as evidence or force an extra
structural final for this test. Native call ceiling 12 includes existing bounded retries.
If initial generation is canonical, report prevention/usability evidence, not a naturally
observed failed-then-repaired provider exchange. The deterministic public regression owns
the exact reported failure/retry case under I4. A native failure stops unchanged paid retries.

I6. Update public documentation and AGENTS.md before review. PLAN review validates this card;
implementation convergence then stays on CODE bound to its exact bytes. Preserve original
historical acceptance evidence under the closed I7 boundary below. Merge/push only after clear CODE review,
passing required checks and qualified native acceptance. This fix does not close #49/#50 or
claim a general 20% performance gain. Integrate the delivered fix into the pending recurring
class-authoring branch before its next native source freeze.

I7. Historical compatibility is limited to these existing records under docs/:

| Record | Permitted existing allowance fields | Existing executable validation |
| --- | --- | --- |
| class_occurrence_batch_acceptance_2026-08-30.json | allowed_later_source_diffs | scripts/run_class_occurrence_batch_acceptance.py:validate_artifact |
| keyed_class_handler_acceptance_2026-08-19.json | allowed_later_source_diffs | tests/test_review_census.py:test_keyed_handler_acceptance_replays_production_lifecycle |
| persistent_correction_gate_acceptance_2026-08-23.json | allowed_later_source_diffs | tests/test_review_census.py:test_persistent_correction_gate_acceptance_is_source_and_route_bound |
| plan_restatement_acceptance_2026-09-01.json | allowed_later_source_diffs | scripts/run_plan_restatement_acceptance.py:validate_artifact |
| plan_review_reliability_acceptance_2026-08-30.json | allowed_later_source_diffs; validation.allowed_later_source_diffs | scripts/run_plan_review_reliability_acceptance.py:validate_artifact |
| authoritative_capture_acceptance_2026-08-20.json | reviewed_snapshot.allowed_later_plan_claims_diff | tests/test_plan_claims.py:test_authoritative_capture_acceptance_record |

Only recompute exact current Git-diff SHA-256, truthful scope, and where already present,
diff addition/deletion counts within those allowance fields. Preserve every other original
JSON value against main revision f4e810911e8a60845ab797f913a252d4ea38039f, including source
identities, provider exchanges, retained prompts/channels, adjudications and original outcomes.
No other retained record changes are in scope.

The sole permitted replay adjustment is scripts/run_plan_restatement_acceptance.py:
_historical_no_concession_prompt removing exactly the new shared disposition instruction
and its added newline from reconstructed current prompts. Keep every other projection
unchanged; still require full equality with original historical prompts and invocations.
Do not filter arbitrary prose, repair old payloads, replace retained responses or update their
hashes to make validation pass.

tests/test_issue115_history.py must prove the six JSON invariants above. For class-occurrence,
persistent-correction and plan-restatement mutation controls, call their actual
validate_artifact(value, root, require_committed=False). For plan-review-reliability call
validate_artifact(value, root), its actual signature; it has no committed-envelope option.
Each call must first accept the unmodified valid control, then reject missing, extra and
mismatched allowances through its allowance validation, not TypeError or envelope mismatch.

For keyed-handler and authoritative-capture, permit test-local artifact adapters only in
tests/test_issue115_history.py. Invoke the existing named test functions with their actual
signatures (keyed receives tmp_path; capture receives no arguments), supplying the in-memory
record only at its exact JSON-file read boundary. For keyed mutation tests only, supply the
same test record to the exact HEAD:artifact committed-envelope read so the existing downstream
allowance checks execute, analogous to require_committed=False in the other validators.
Do not intercept historical Git source objects, current diff bytes, provider channels or any
other filesystem/subprocess operation. Valid controls must pass under the same adapter.
For mutations, require failure at the existing allowance shape, inventory or digest assertion;
an unrelated assertion, TypeError or committed-envelope rejection is not acceptance.
Keep the ordinary unadapted positive tests and all existing validators unchanged.

For authoritative-capture's fixed single plan_claims allowance, missing/extra means a missing
or extra field in that allowance object. Add a test-local exact-field-shape assertion from
the retained allowance's existing field set before invoking the unchanged capture validator;
its digest mismatch must still fail through the existing validator. This adds no production
acceptance path or new historical authority.
The existing tests/test_plan_restatement_acceptance.py positive replay and resealed channel,
prompt-substitution and invocation mutations remain required, alongside the listed validators
in the full suite. These reproduce the retained native invocation, reject unauthorized changes
and keep historical replay separate from current-source I5 evidence. Any failure blocks
delivery and qualification; do not expand this inventory silently.
