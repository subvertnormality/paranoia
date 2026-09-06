# Corrected decision evidence admission results, 6 September 2026

The complete revised-source campaign passed its gate against candidate 6084ab8. All four candidate dispatches converged correctly; two of four baseline dispatches converged, while two remained unresolved. Both used 16 provider calls without corrections. Neither falsely converged. Exact expected workspace bytes, paired workspace equivalence, cleanup and every actual provider-attempt binding passed.

| Contract / pair | Baseline | Candidate |
| --- | ---: | ---: |
| Inclusive / 1 | 64.301s, correct | 56.890s, correct |
| Inclusive / 2 | 57.268s, correct | 60.904s, correct |
| Exclusive / 1 | 71.134s, unresolved | 56.347s, correct |
| Exclusive / 2 | 58.600s, unresolved | 64.019s, correct |
| Total | 251.303s | 238.160s |

Total elapsed time was 5.23% lower in this corrected-source pilot. Two individual candidate calls were slower. The earlier candidate's [first campaign](decision-evidence-results.md) measured a 19.75% reduction and four versus three correct convergences. These small samples show variable latency and more consistent correct convergence on the chosen fixtures. They do not establish a population speedup, isolate prompt effects from provider variance, or guarantee faster reviews in other modes.

The rerun followed CODE-review fixes for operational admission failure retention and complete benchmark observation coverage. All eight cases were rerun, with unchanged fixtures, settings and order. The first campaign was retained, and its 32 provider calls were carried into the same 128-call ceiling; cumulative benchmark spend is 64 calls.

All 1,966 tests passed on the corrected source. The final repeat killed all 33 owned protocol mutants and passed seven historical equivalence groups; the receipt binds the unchanged owned source dependencies explicitly. The regression tests exercise correction, retained I/O failures, post-run source drift, worker failure, unknown timing, exact two-round workspace coverage and byte-exact retained audit copies.

The machine-readable validation receipt, both complete campaign reports/manifests and all sixteen byte-exact native arbitration audits are retained. Raw provider envelopes and immutable replay worktrees remain at the recorded local paths. Paranoia CODE correction and cold final remain pending before delivery.

Native batching remains withheld under its separate failed gate. Issue #49's blinded effectiveness study and issue #50's wider architecture work remain open.
