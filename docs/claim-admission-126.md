# Claim-audit admission repair (#126)

A large repository snapshot can exhaust the former pre-discovery allowance and
produce a local exit 124 without invoking Claude or Codex. The handler now gives
preparation its own reserve, while retaining the full evidence graph and its
per-role timeouts. The monotonic deadline still begins before snapshotting, and
exhausted admission remains blocking. Local admission reasons survive in claim
debt and the separate bounded, hashed failure-detail channel.

The current timeout composition is defined in `src/paranoia_local/handlers.py`.
Use the MCP client timeout in README.md. Changing client configuration does not
reload a running service's Python modules.

## Native acceptance

`scripts/run_claim_admission_acceptance.py` starts a dedicated fresh stdio MCP
server and binds it to the committed source tree, interpreter, complete Python
inventory and acceptance harness. It leaves unrelated MCP connections running.
The request must embed exact `plan_text`, select `engine: claude`, retain claim
verification and supply the intended repository/lineage/round/stakes. Resume the
existing lineage; do not reset it to hide prior debt.

The launcher requires tracked class closure and a positive round. It freezes the
selected state root and prior lineage bytes, explicitly forwards that root to
the MCP child, and checks the predecessor before dispatch. The receipt requires
the same lineage and round with an actual structural result. A successful native
discovery validation retry is accepted with its initial rejected attempt retained;
any failed or nonzero attempt prevents acceptance.
Validation rejection is creditable only when its existing same-session correction
completes successfully; terminally invalid retries and sessionless rejections
refuse acceptance. Continuation follows production's `review_state.last_round`
ordering, allowing forward label jumps and retry of an unsettled failed label.
The separate settlement count is never treated as the caller's round label.

The repeated receipt finding prompted an architecture checkpoint: the receipt
remains an acceptance gate over the native ordered attempt ledger, not a new
claim adjudicator. It checks execution and completed correction; production
retains ownership of claim verdicts, structural debt and the combined review gate.
The binding role additionally requires a provider session even when the process
returned successfully: production rejects that sessionless reply locally while
retaining its original completed-attempt channels. The regression exercises the
actual expanded binding adapter through source-local rejection and receipt refusal.

From a committed repair checkout, run:

```sh
.venv/bin/python scripts/run_claim_admission_acceptance.py \
  --request /absolute/path/request.json --output /absolute/path/new-evidence-directory
```

The output directory must be new. It retains the request/source manifest, actual
MCP response, provider audit, stderr and source-bound receipt. `accepted.json`
requires matching identities and a completed native claim audit. A structural
finding may still block the reviewed plan: inspect its actual combined verdict.
Identity or provider failure leaves evidence and `failure.json`, never an accepted
receipt. The checks repeat after execution so ordinary source edits cannot be
credited as acceptance of the recorded tree.

These local artifacts can contain the reviewed repository's private content.
Keep them outside a public PR; report source and artifact hashes, measured
outcomes and limitations. Historical acceptance allowance metadata records later
source differences only, not retroactive provider acceptance of this repair.

The complete suite exposed an omission from the reviewed plan's six-record
compatibility inventory. Three additional existing records bind the changed
handler: `branch_plan_fidelity_acceptance_2026-08-22.json`,
`class_persistence_acceptance_2026-08-22.json`, and
`mechanized_predicate_acceptance_2026-08-27.json`. This implementation correction
updates only each existing handler allowance's `sha256` and `scope` fields.
`tests/test_issue126_history.py` pins every other value to the pre-repair tree,
except that a later source delta may refresh the `sha256` and `scope` of any
existing allowance entry (no entry may be added or removed), and exercises the original validators against missing, extra and mismatched
allowances. The original reviewed plan remains unchanged; CODE review must
assess this explicit inventory correction together with the implementation.

The design review converged at round 3 on lineage
`paranoia~126~claim-admission~plan`. CODE and native acceptance outcomes must be
recorded separately before delivery; this design result does not establish them.

The actual CODE, full-suite and native-acceptance outcomes are recorded in
`claim-admission-126-validation.md`, including the retained earlier failure and
the successful qualification of the corrected attestation contract.

## Attestation correction

The shared contract asks for concise evidence-based justifications for the two
independent judgments and explicitly excludes private internal deliberation.
The parser rejects non-whitespace prefixes and duplicate object keys, in addition
to its existing single-envelope, schema, coverage and size checks. Both initial
and correction replies use that parser and the existing single retry.
Surrounding whitespace retains the previous Unicode-aware normalization.

Current-wording qualification requires an initial native attestation attempt in
the current source-bound audit and successful completion, including a legitimate
same-session repair. Discovery-only or frozen historical evidence cannot qualify
this change. The real adapter invokes attestation only for a nonempty packet;
its strict parser remains the sole owner of reply validation. Historical evidence
and the previous provider refusal remain historical; they do not prove this
wording or parser. See `attestation-justifications-126-plan.md` for the contract.
