# Issue 138: caller disposition of supplemental proposals

Beta scope: caller accounting, never proof of repair, claim support or clearance.
Use one bounded optional proposal_receipt in the existing atomic lineage file.
After a validated PROPOSED/PARTIAL patch has a supplemental audit receipt, save
round, structural snapshot, patch digest, audit name and addressed target IDs under
the existing latch. Save failure makes the supplement UNAVAILABLE, preserving the
settled original review and exact trailer. No audit scan, extra store or model call.
Historical lineages without this field remain valid.

The next tracked round accepts optional prior_proposal_disposition as a closed
object with status (applied, partially-applied, departed) and departed_targets:
exact addressed target IDs mapped to nonempty one-line reasons, at most 500 chars.
Applied requires an empty map; departed all targets; partial a nonempty proper subset.
Reject malformed, unknown, misbound or one-shot input before provider work. Bind the
receipt round to durable last_round, permitting forward jumps and failed-round retry.
Omission with a pending receipt renders PROPOSAL-DISPOSITION: none-recorded.
Echo receipt-bound accounting in the exact returned/audited trailer and structured
audit field. Do not infer application from added-line overlap or pass disposition
to reviewers; substantive settlement is unchanged.

Both tool descriptions require reading and dispositioning a proposal before the
next round. The optional API preserves ordinary omitted review behavior.

Acceptance: public plan/branch lifecycles on both native adapters; reload, changed
artifact, jumps, omission, malformed zero-call input, failed-round retry, exact
target coverage, escaped trailer text, audit/save failure and unchanged clearance.
Verify actual tool schemas. Exercise native public-handler branch proposal,
dispositioned correction and cold final. Keep implementation convergence on CODE.

Frozen model: one trusted operator and OS; untrusted static repository/plan/proposal
data; ordinary edits block/retry. Exclude hostile local races, compromised OS,
corrupted-state recovery, multi-tenancy and formal proof. Tens to low hundreds of
findings, bounded rounds, results useful within minutes. Wrong evidence binding or
clearance is high impact; recoverable blocking acceptable. No new network boundary.
