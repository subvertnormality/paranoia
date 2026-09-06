# Native snapshot batching experiment, 6 September 2026

Status: **withheld**, not merged or pushed. Baseline 33394cb4b465e414a315d152b079599880771de1; candidate 7360f404d621d8fc9c375dccc752522238fd532f, retained in codex/review-pipeline.

All 40 local trials completed with exact workspace fingerprints. Median setup plus cleanup fell from 0.992s to 0.169s for the 188-file repository, 4.572s to 0.465s for 1,000 files, and 14.354s to 0.834s for 3,000 files. These are local workspace preparation gains, not end-to-end provider review speedups. The candidate passed 1,954 tests and all 33 owned Protocol v2 mutation checks.

The four frozen public arbitration dispatches consumed 16 provider calls. Baseline inclusive converged in 55.694s; candidate inclusive remained unresolved in 59.386s; candidate exclusive remained unresolved in 83.619s; baseline exclusive remained unresolved in 64.072s. All three unresolved results declared absolute temporary-workspace citations and correctly failed final evidence substantiation. The defect also occurred on unchanged main.

All paired raw workspace fingerprints and permissions matched, and all independent provider workspaces were cleaned up. The original live report's paired_equivalence field is false because that aggregate is also gated by every semantic result qualifying. It does not indicate differing workspace bytes; inspect the retained per-provider fingerprint rows. The original report is preserved unchanged.

The original contract requires successful live acceptance, so the batch optimization remains withheld despite local gains. No gate is relaxed and no failed case is omitted. The next independent architecture card validates citation declarations before the existing bounded correction opportunity expires. It starts from main, without batching. Issue #49's broader blinded study and issue #50's wider architecture work remain open.

## Retained records

The companion JSON files preserve both original reports, including all 40 local and four live rows, source identities, manifest digests and live audit hashes. Full campaign manifests, raw provider records and frozen harnesses remain in the local campaign directories identified in those reports. They are not claimed to be portable public replay artifacts.
