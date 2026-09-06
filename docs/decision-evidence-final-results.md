# Final-source decision evidence results, 6 September 2026

The full eight-dispatch campaign on candidate cbdd3a1 passed its frozen live gate. Candidate correctness was 4/4 versus baseline 4/4. Candidate unresolved/failure count was 0 versus baseline 0. Provider calls were 16 and 16, respectively. False convergence was absent: True. All source, exact expected workspace, paired workspace, per-attempt and cleanup bindings passed: True.

| Contract / pair | Baseline | Candidate |
| --- | ---: | ---: |
| Inclusive / 1 | 65.131s, CONVERGED | 58.250s, CONVERGED |
| Inclusive / 2 | 52.419s, CONVERGED | 63.963s, CONVERGED |
| Exclusive / 1 | 71.736s, CONVERGED | 83.220s, CONVERGED |
| Exclusive / 2 | 66.252s, CONVERGED | 52.725s, CONVERGED |
| Total | 255.538s | 258.158s |

The candidate total was 1.03% higher in this final-source pilot. These are eight integration dispatches on two synthetic contracts, not a population performance or effectiveness study. Elapsed time includes symmetric workspace observation overhead. Do not infer guaranteed or all-mode speed improvements from these results.

Both earlier full campaigns remain unchanged: [initial source](decision-evidence-results.md), [first corrected source](decision-evidence-corrected-results.md). Their candidate runs were all correct, with baseline correctness 3/4 and 2/4; elapsed reductions were 19.75% and 5.23%. Different source revisions and provider variance prevent treating those figures as a controlled population estimate. All 96 benchmark provider calls are accounted for within the same 128-call ceiling. The additional f47760c manifest was superseded before any calls after CODE review identified the gitlink case; it spent zero.

The first report-only process lacked the signed-in CLI directory in PATH and conservatively marked all trials unqualified. The reporter overwrote its default output during revalidation; the original intermediate report was not preserved. Its observed diagnostic is retained, and a separate failure report is explicitly labelled as a reproduction from the unchanged observations under the original PATH. Restoring the same execution environment allowed the exact frozen harness to revalidate all eight unchanged trials, with no provider reruns, source or fixture changes, or gate relaxation. The qualified report and diagnostic reproduction bind identical attempts, outputs, timings, workspace observations and audit digests; successful qualification additionally derives global attempt-sequence bindings. A regression check proves raw-observation identity and checks those derived bindings.

The final source passed all 1,985 tests. The 33 owned protocol mutants and seven historical equivalence groups remain bound to unchanged owned dependencies. CODE rounds 1–4 found and closed four defect classes; the cold final remains pending before delivery. The machine-readable receipt retains every round, all three complete live reports/manifests, and 24 byte-exact native audits. Earlier failed findings and campaigns have not been erased or relabelled.

The runtime adds a typed decision-evidence admission boundary and an explicit initial citation grammar. Repairable declarations share the existing single format/evidence correction; required Git read failures terminate with provider replies retained. Successful tree metadata distinguishes missing submodule targets from unavailable required blobs. No new provider role, retry allowance, evidence normalization, submodule fetch or weakened final grounding was introduced.

Native batching remains withheld under its separate failed gate. Issue #49's blinded effectiveness study and issue #50's wider architecture work remain open.
