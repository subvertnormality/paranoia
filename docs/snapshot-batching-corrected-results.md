# Corrected snapshot batching qualification

Candidate: 0860cadb9f8a4367608aeadff425b011c4e9cb31. Baseline: 684898c5a8f35f57917ea77662a9aad9b8b05f19.
The [immutable contract](snapshot-batching-requalification-plan.md) owns the fixed release gates. CODE cold-final clearance is a separate mandatory merge gate.

## Results

All 40 local slots completed with identical complete evidence renderings and reduced native object-read process counts. Five alternating pairs were retained per fixture; no timed slot was selectively rerun.

| Fixture | Baseline median setup + cleanup | Candidate median | Reduction | cat-file calls, baseline → candidate |
| --- | ---: | ---: | ---: | --- |
| repository | 1.447s | 0.208s | 85.6% | [464] → [3] |
| 100 | 0.437s | 0.034s | 92.1% | [200] → [1] |
| 1000 | 4.384s | 0.352s | 92.0% | [2000] → [8] |
| 3000 | 12.520s | 0.877s | 93.0% | [6000] → [24] |

The corrected local comparison ran on a shared 24-CPU workstation after repeated quiet-window checks found ongoing unrelated tests. This task ran no tests or provider reviews during measurement. Endpoint observations recorded one unrelated test process at both ends, with reported CPU usage 7.9% and 5.0%; these are endpoint observations, not continuous isolation evidence. Full load observations and all distributions are retained. The numeric gates, source, fixtures, ordering, and repetition count were unchanged.

Both versions returned four correct, evidence-bound live convergences with 16 provider calls each. Every workspace, cleanup, channel, and call-ledger check passed.

| Contract | Padding files | Baseline dispatch | Candidate dispatch |
| --- | ---: | ---: | ---: |
| Inclusive | 0 | 54.826s | 57.071s |
| Inclusive | 3000 | 107.418s | 83.792s |
| Exclusive | 0 | 60.693s | 65.714s |
| Exclusive | 3000 | 101.732s | 88.283s |

Total observed dispatch time was 324.669s baseline and 294.860s candidate, a 9.18% reduction. Large cases improved and small cases regressed. These eight observations, including symmetric workspace-observer overhead and provider variability, do not establish a general speedup in ordinary use. Concurrent provider durations are retained separately and are not summed into wall time.

## CODE corrections and provenance

The initial campaign is [retained with its limitations](snapshot-batching-requalification-results.md). CODE round 1 found incomplete public-handler snapshot coverage, missing successful-stderr custody, and an ordinary stale-bytecode admission path. No evidence shows that stale bytecode affected the original campaign; its omitted stderr remains unknown. It does not qualify delivery.

Both public-handler callbacks now check complete binary and unusual-path bytes, inert symlink/executable/gitlink representations, manifests, permissions, and history. Earlier-call, sibling-failure, and cleanup assertions remain active.

Entry scripts execute a shared source bootstrap before importing owned modules. Standard Python controls use a fresh empty bytecode-cache prefix and disable writes. Tests demonstrate a same-size edit/import/restore within one timestamp tick: normal Python consumes the stale cache, while the benchmark consumes committed source. Local/live workers and shared harness consumers use this boundary; the bootstrap is frozen with the harness.

The shared observer retains stdout, stderr, and structured failure detail as separate exact encoded files, including explicit empty channels. All 96 corrected channel files and eight native audits are archived and hashed. Qualification checks every channel; missing or changed data keeps costs but cannot earn credit. Nonempty successful-stderr and failed-review fixtures cover the formerly missing path.

The corrected suite passed 2,083 tests. The intermediate run with five invalid synthetic test inputs is retained, and all fixtures were corrected without weakening validation. All 33 previously run Protocol v2 mutants were killed; every production source byte is identical to that mutation-tested candidate. A source-entry report replay reproduced the first corrected live report byte-for-byte with zero provider calls. The card spent 64 aggregate benchmark calls, including the initial campaign, under its 128-call cap.

The [qualification record](snapshot_batch_corrected_qualification_2026-09-07.json) binds complete reports, manifests, source inventory, channels, native audits, test outputs, and earlier limitations. The [native reader ownership](native-snapshot-batching.md) remains small: a 103-line object reader beside the 172-line inert renderer. No provider roles, nominal call topology, or production evidence semantics changed.

## Further work boundary

The user retained the setup gate and set a 20% end-to-end time or cost investigation threshold for substantial subsequent changes, without materially worsening the other measure. Substantial maintenance simplification can also justify work at high confidence. Existing census and arbitration reviewers already run concurrently. A limited mixed-version plan-log screen found no multi-batch attestation workload, so no broader scheduler was implemented on that evidence.

The completed CODE census showed substantial repeated context consumption during repository inspection. That is a lead for measuring context preparation and navigation, not evidence of a 20% cost saving or permission to remove reviewer coverage. This card does not close issues #49 or #50, establish a blinded quality result, or guarantee performance of future models.
