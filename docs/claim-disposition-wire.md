# Prior-claim removal rows

Claim discovery and its single validation correction generate removal rows using
claim_id, disposition and reason:

    {"claim_id":"C-example","disposition":"removed","reason":"The old anchor is absent."}

The example ID must be replaced with the actual prior claim ID. Removal remains
conditional on the old external anchor being absent from the current plan.

The parser retains compatibility with prior_claim_id instead of claim_id, and
rationale instead of reason. Each pair admits exactly one name. Supplying both
names rejects even if their values agree. A rejection identifies the row and
observed names and supplies the canonical example to the existing correction.
Another invalid response retains blocking audit debt; it does not retire the claim.

Claim objects have separate prior_claim_id and rationale fields. Their shape
must not be copied into coverage.prior_dispositions rows.
