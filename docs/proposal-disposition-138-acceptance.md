# Issue 138 beta acceptance

The executing agent SHOULD use the proposed diff after inspection and validation.
Departures require a concrete reason per addressed target. The optional caller API
records this choice; it does not clear review debt or establish repair correctness.

The live Codex branch-handler acceptance passed on committed source
`dc2ace1` (CLI 0.159.3), with strongest-model review under the frozen trusted-local
arithmetic-fixture stakes. The [retained record](proposal_disposition_acceptance_2026-10-01.json)
contains the complete production-module source manifest, runner hash, actual main
and supplemental audits, returned outputs, arguments and reloaded durable lineage
for all three rounds. It exercised proposal generation, exact receipt reload,
inspection by an exact patch allowlist, applying that diff, asymmetric operand and
zero-denominator checks, receipt-bound `applied` on correction, and an independent
cold final reaching `NOT-BLOCKED`. Historical receipt accounting was absent in final.
This is a Codex native usability acceptance, not a Claude native campaign or a
performance/cost comparison. Scripted lifecycle tests cover both native adapters.

Reproduce from a committed checkout with the Codex executable and dependencies
available using [the runner](../scripts/run_proposal_disposition_acceptance.py):
`python scripts/run_proposal_disposition_acceptance.py --output /absolute/new/directory`.
It requires a new output directory, keeps partial failures, permits only the exact
inspected arithmetic patch, and verifies its source binding before every round.
[The replay test](../tests/test_proposal_disposition_acceptance.py) checks historical
source hashes and requires current critical production files to match those bytes.

Deterministic validation: the full suite on `dc2ace1` recorded 2584 passing tests
and 32 failures. The pre-change beta control (`b0e0635`) recorded 2487 passing tests
and the same 32 failing test identities; these are existing historical acceptance
bindings, not a passing full-suite gate. The feature initially added two handler
allowance failures; only existing hash/count/scope metadata in the authoritative
capture record was refreshed, keeping original provider evidence fixed. The issue
tests plus native replay then recorded 98 passing tests. No historical run is
reinterpreted as passing evidence for current behavior.

PLAN review reached `NOT-BLOCKED` before implementation. Delivery also requires
broad CODE correction and cold-final convergence on the implementation branch;
the native fixture alone is not that broad code gate.
