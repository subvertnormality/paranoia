# Snapshot batching requalification results

Qualification candidate: 687e7bd0b420f784dc1757bfe5458e8148cc4d01. Baseline: 684898c5a8f35f57917ea77662a9aad9b8b05f19.
The [immutable contract](snapshot-batching-requalification-plan.md) owns the release gate. CODE convergence is a separate mandatory merge gate; this report does not authorize delivery by itself.

## Measured setup and cleanup

All 40 slots completed with identical evidence renderings. Five alternating pairs per fixture used isolated imports of the frozen committed sources. Fingerprinting ran outside the setup/cleanup timer.

| Fixture | Baseline median | Candidate median | Reduction | cat-file calls, baseline → candidate |
| --- | ---: | ---: | ---: | --- |
| repository | 1.198s | 0.178s | 85.1% | [464] → [3] |
| 100 | 0.495s | 0.039s | 92.2% | [200] → [1] |
| 1000 | 4.716s | 0.315s | 93.3% | [2000] → [8] |
| 3000 | 12.313s | 0.868s | 92.9% | [6000] → [24] |

## Live integration

Both versions produced four correct, evidence-bound convergences, with 16 actual provider calls each. No slot failed or remained unresolved. All workspace equivalence, per-attempt binding, cleanup, and call-ledger checks passed.

| Contract | Padding files | Baseline dispatch | Candidate dispatch |
| --- | ---: | ---: | ---: |
| Inclusive | 0 | 56.858s | 53.427s |
| Inclusive | 3000 | 78.655s | 83.811s |
| Exclusive | 0 | 55.622s | 54.592s |
| Exclusive | 3000 | 90.417s | 87.608s |

Total observed dispatch time was 281.552s baseline and 279.438s candidate, a 0.75% reduction. This is approximately flat and does not demonstrate a general end-to-end speedup. Provider variability, unrelated workstation activity, and symmetric workspace-observer overhead limit interpretation. Concurrent provider durations are retained separately in the native records and are not summed into dispatch wall time.

## Validation and maintenance

The complete suite passed 2,058 tests; all 33 Protocol v2 mutants were killed and seven historical differential groups passed. Source admission now binds the complete recursive Python inventory and actual bytes to the named Git commit before freeze and subsequent use. Initial modified, missing, additional, nested, and staged source changes block before timed or provider work.

The runtime adds a 103-line object reader; inert_tree remains the rendering and cleanup owner. Module counts, exact source hashes, full trial distributions, first report attempts, and eight byte-exact native audits are bound by the [acceptance record](snapshot_batch_requalification_2026-09-06.json). Reviewer roles, call topology, and evidence semantics remain unchanged.

This improves verified-plan and arbitration materialization. Branch checkout, ordinary query, and rebut do not use this path. It does not establish fewer convergence rounds, better defect detection, future-model performance, or completion of issues #49/#50.

## Further opportunity screen

The user set a 20% end-to-end time or cost investigation threshold with neither materially worse, while also allowing substantial maintenance simplification at high confidence. Existing census lanes and arbitration deciders already run concurrently. Cold attestation batches are sequential, but none of the eight attestation-bearing audits in a screen of 80 recent retained plan audits used multiple batches. Those mixed-version observations are not a representative benchmark and do not justify implementing a broader scheduler. No new general speedup is claimed from that screen.
