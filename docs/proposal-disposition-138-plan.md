# Issue 138: caller disposition of supplemental proposals

Beta scope: caller accounting, never proof of repair, claim support or clearance.
The stored-receipt, eligibility/transition and accounting sections below are the
respective authoritative contracts; summaries and documentation defer to them.
The executing agent SHOULD use the proposed diff as its repair starting point,
inspect and validate it, and give a concrete reason for each target where it departs.
Use one bounded optional proposal_receipt in the existing atomic lineage file.
After a validated PROPOSED/PARTIAL patch has a supplemental audit receipt, save
round, structural snapshot, patch digest, audit name and addressed target IDs under
the existing latch. Save failure makes the supplement UNAVAILABLE, preserving the
settled original review and exact trailer. No audit scan, extra store or model call.
Historical lineages without this field remain valid.

The next tracked round accepts optional prior_proposal_disposition as a closed
object with proposal_audit (the exact PROPOSAL-AUDIT-JSON basename), status
(applied, partially-applied, departed) and departed_targets:
exact addressed target IDs mapped to nonempty one-line reasons, at most 500 chars.
Applied requires an empty map; departed all targets; partial a nonempty proper subset.
Reject malformed, unknown, misbound or one-shot input before provider work. Bind the
receipt round to durable last_round, permitting forward jumps and failed-round retry.
Omission with a pending receipt renders PROPOSAL-DISPOSITION: none-recorded.
Echo receipt-bound accounting in the exact returned/audited trailer and structured
audit field. Do not infer application from added-line overlap or pass disposition
to reviewers; substantive settlement is unchanged.

Both tool descriptions require reading and dispositioning a proposal before the
next round, using the diff unless a specific departure is justified. The optional
API preserves ordinary omitted review behavior; omission remains visibly unaccounted.

Authoritative stored receipt (closed version 1 object): version, round (caller
label), structural_snapshot, patch_sha256, audit (supplemental receipt basename),
and target_ids (ordered unique addressed IDs, bounded by MAX_TARGETS). Preserve it
through lineage load/copy/save independently of normalized review state. Absence
means no historical receipt; malformed retained receipt blocks existing state load.

Eligibility and transitions:
- A receipt is pending exactly when its round equals durable review_state.last_round.
  A supplied disposition without a pending receipt is rejected before provider work.
  Its proposal_audit must exactly equal receipt.audit. A replaced receipt or another
  lineage's receipt rejects even for applied with an empty map or identical targets.
- Snapshot changes and forward caller-round jumps keep that pending receipt usable.
- Failure/rejection does not advance last_round: retain the receipt for the same
  failed-label retry. The attempt's audit still records its caller declaration.
- Successful next settlement advances last_round, making the old receipt historical
  and ineligible without deleting it. Omission counts as none-recorded, not acceptance.
- A new successfully audited and persisted PROPOSED/PARTIAL replaces that one receipt.
  DECLINED/UNAVAILABLE/NOT-NEEDED, no proposal, and correction-ineligible outcomes
  retain the historical receipt and create no pending obligation.
- A second (receipt) save failure leaves substantive settlement untouched, reports
  supplemental UNAVAILABLE, retains its completed proposal audit and the pending
  latch, and blocks subsequent admission until that unconfirmed write is inspected.
  The original returned/audited review trailer remains exact. Never retry provider
  generation or treat the unconfirmed receipt as delivered.

Authoritative accounting wire object: receipt (the exact closed stored receipt),
status (the supplied enum or server-owned none-recorded), and departed_targets
(the validated reason map, empty for omission). Audit field: proposal_disposition.
Returned line: PROPOSAL-DISPOSITION: followed by status, a space and JSON of the
same object using ensure_ascii=True and sorted keys. Append this line to the review
trailer before either handler writes its review audit. No pending receipt and no
argument means no object and no line. Reject caller null, extra fields, multiline
or blank reasons, oversized maps and unknown targets. Accounting rendering is pure
over validated bounded data; audit failure keeps the review's existing best-effort
semantics, never falsely claims an audit receipt and never changes clearance.

Document the exact input/output in both public parameter tables, README, the LLM
reference, lifecycle documentation and both rendered CALLER instructions. All state
these are caller declarations, the API is optional, omission is visible only with
a pending receipt, and independent review alone decides repair and clearance.

Acceptance: public plan/branch lifecycles on both native adapters; reload, changed
artifact, jumps, omission, malformed zero-call input, failed-round retry, exact
target coverage, escaped trailer text, audit/save failure and unchanged clearance.
Verify actual tool schemas. Exercise native public-handler branch proposal,
dispositioned correction and cold final. Keep implementation convergence on CODE.

Executable acceptance in tests/test_proposal_disposition.py, parametrized over
critique_branch and critique_plan (both CodexEngine and ClaudeEngine adapters):
- test_disposition_lifecycle: issue a proposal, reload, change the artifact, submit
  each valid status or omit, then reload for a third round. Assert exact stored
  receipt, last_round, accounting object, returned/audited suffix and no stale use.
- test_invalid_disposition_admission: invalid shape, coverage, reasons, no receipt
  and one-shot input must reject with zero provider calls and no receipt consumption.
- test_failed_round_retry: execution/validation/substantive-save failure retains
  the receipt; ordinary failed-label retry reuses it only when the latch permits.
- test_receipt_save_failure: inject the second save failure before and after its
  atomic replacement. Assert original returned/audited trailer and substantive
  state, exact receipt visibility, supplemental UNAVAILABLE, retained latch, and
  subsequent admission refusing with zero provider calls. No automatic repair.
- test_disposition_render_failure: validate and render the bounded accounting
  object before provider admission. An injected construction/rendering exception
  propagates as a visible local error, leaves the receipt/last_round unchanged,
  releases an unambiguous admission latch and makes zero provider calls.
- test_disposition_audit_failure: main audit failure preserves the finalized
  returned suffix and ordinary confirmed settlement, claims no successful receipt,
  and suppresses new proposal generation. Supplemental audit failure creates no
  receipt and leaves the exact main audit/trailer unchanged.
- test_disposition_escaping_and_schema: quotes, backslashes and Unicode round-trip
  from the one-line suffix to the exact audit object; controls cannot forge lines;
  actual MCP schemas accept every legal object and reject illegal objects.
Any missing or failing assertion blocks delivery. Native acceptance must exercise
critique_branch itself, reload the issued receipt, pass its exact target IDs on
correction, then reach a cold final; retain each actual audit and returned output.

Frozen model: one trusted operator and OS; untrusted static repository/plan/proposal
data; ordinary edits block/retry. Exclude hostile local races, compromised OS,
corrupted-state recovery, multi-tenancy and formal proof. Tens to low hundreds of
findings, bounded rounds, results useful within minutes. Wrong evidence binding or
clearance is high impact; recoverable blocking acceptable. No new network boundary.
