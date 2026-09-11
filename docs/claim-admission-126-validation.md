# Issue 126 validation

The original reviewed candidate identity is retained in the private validation
record. Public history was redacted to remove private project identifiers;
the implementation and tests are unchanged by that documentation redaction.

The production repair changes only `src/paranoia_local/handlers.py`: 15 added
and four removed lines. It adds preparation budget and retains locally authored
admission diagnostics. Evidence topology, reviewer roles, provider caps and
closure gates are unchanged.

## Tests and review

The original seven admission/diagnostic regressions failed before the production
repair. Subsequent acceptance regressions reproduced the reviewed failure modes
before their fixes. The final focused acceptance run passed 39 tests, including
actual expanded binding with a sessionless successful provider reply followed by
source-local rejection and receipt refusal. Historical controls preserve original
provider evidence and reject missing, extra or mismatched allowance metadata.

The complete canonical tree, `python -m pytest tests/ -q`, passed **2,309 tests**,
with no skips or exclusions, in **122.89 seconds** on the candidate above.
The retained output SHA-256 is
`fb32826e0b4bda6c986653e4aa53950b5220cf8415e877bd62ce08db1b062e34`.

This run used Ubuntu 26.04 aarch64, Python 3.14.4, one pytest process in an
isolated local VM with two CPUs and 2 GiB RAM. Test temporary directories used
disk storage. The isolated checkout used `core.abbrev=7` to reproduce the exact
historical Git diff serialization bound by existing acceptance records. The
recorded historical Codex fixture used its exact original package version;
active reviewers were unchanged.

PLAN review converged at round 3. Codex CODE review converged at round 5, after
resolving findings and completing the required cold final regression: zero blocking
debt, `STRUCTURAL-PHASE: clear`, `CONVERGENCE: NOT-BLOCKED`. Its five rounds used
eight recorded model attempts. The frozen reviewed plan remains unchanged; the
full-suite-discovered three-record inventory correction is explicitly documented
in `claim-admission-126.md` and was included in CODE convergence.

## Retained failures and limitations

An unchanged-base macOS diagnostic run recorded 33 failures, 2,224 passes and
one skip. Missing historical Git objects and an exact historical CLI fixture
were recovered without changing recorded identities or outcomes. Later macOS
diagnostics retained unsupported invalid-UTF8 filename failures. Those tests
ran unchanged and passed on Linux.

The first Linux attempt exhausted its default RAM-backed temporary filesystem;
its output and fixtures were retained. A later run recorded 34 failures caused
by historical source-diff serialization differences; the observed host/guest
diff differed only in seven- versus eight-character Git object abbreviations.
Matching that isolated test setting allowed the original validators to pass.
A subsequent complete run retained the newly introduced diagnostic-order
regression (one failure, 2,308 passes), then the corrected candidate passed the
complete suite above. Failed attempts are not reported as passing evidence.

## Native acceptance

**Failed; delivery remains blocked.** The fresh source-bound Claude MCP run
executed four claim-role attempts and one structural correction in
617.5967928329483 seconds. Initial discovery required its existing validation
retry; that retry and evidence binding completed. Cold attestation then returned
exit 1 with a provider safeguard refusal tagged `reasoning_extraction`.

The actual claim status was `attestation-failed`. The harness retained the audit,
response, source-bound receipt and `failure.json`, and produced no `accepted.json`.
The structural review also retained one blocking design finding. No provider
roles, safeguards or closure gates were bypassed. This proves that the original
zero-call admission point was passed for this input; it does **not** establish
complete native acceptance or reviewed-plan clearance.

Native audit SHA-256:
`8e5a758c093c165e1df9198459227329669d9dd5c6892665c35db0139845891b`.
Native response SHA-256:
`5d342369222b7d3694fd65666deaf7b25f974cef690257f7089e2ba60f3e56c4`.

The operator subsequently authorized a blocked draft PR despite this failed native
acceptance. It remains a draft pending the separate attestation correction, actual
CODE convergence, complete tests and successful native qualification. No merge occurred.

## Size measurements

| Module | Bytes | Lines |
| --- | ---: | ---: |
| `src/paranoia_local/handlers.py` | 246014 | 5341 |
| `src/paranoia_local/arbitrate_handler.py` | 130620 | 3073 |
| `src/paranoia_local/plan_claims.py` | 85019 | 1889 |
| `scripts/run_claim_admission_acceptance.py` | 12214 | 261 |

Private native inputs, audit channels and source-bound receipts are retained
outside this public repository. This report records measured outcomes, not
retroactive acceptance of historical provider runs or universal performance.

## Attestation correction in progress

Codex PLAN review converged at round 5 on
`paranoia~126~attestation-justifications~plan`, with zero open blocking debt.
The review found that prefixes and duplicate JSON keys were previously accepted;
all nine added public-adapter cases reproduced that bug before the parser fix.
The initial focused RED run recorded 26 failures and 66 passes, including the
wording and discovery-only acceptance gaps. Implementation verification, CODE
review and current native qualification are pending; the earlier green suite and
review apply only to the previous timeout repair.

The first correction candidate passed 363 focused/historical tests in 149.15
seconds and the complete Linux tree: 2,324 passed in 129.84 seconds. Its first
Codex CODE review recorded five staged attempts, including one invalid payload
and its successful correction; structural debt was clear. It identified a minor
compatibility regression in surrounding Unicode whitespace. Two public-adapter
regressions reproduced this on both initial and correction replies. Restoring
the previous `strip()` normalization fixes that gap without relaxing duplicate
key, prefix or trailing-content rejection. Updated CODE and full-suite results
remain pending for this subsequent candidate.
