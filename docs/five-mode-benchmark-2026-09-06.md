## Next comparison: complete convergence

The next optimization target is total elapsed time and work to a correct, durable clear
across matched review-fix-review sequences. Individual invocation latency is secondary.
Record review calls, correction retries, fix effort, recurring findings, rounds, failures,
unsupported blockers, and false clears. A slower initial review may be preferable when
it reliably prevents later rounds. This invocation pilot does not establish that benefit.

# Five-mode live pilot — 6 September 2026

Issue 114 is repaired on this branch, with a natural live Claude reproduction and successful
single correction. This pilot does **not** demonstrate a general speedup or stronger reviews.
Both versions completed the expected decision in 19 of 20 trials. Across the 18 pairs where
both completed successfully, candidate dispatch time totaled 1201.3 seconds
versus 1153.8 seconds for baseline (+4.1%).
Two repetitions of ten small cases cannot establish a population performance difference.

## Protocol and sources

The [frozen plan](claim-audit-benchmark-plan.md) defines the operating model and acceptance.
The [retained manifest and results](five_mode_benchmark_2026-09-06.json) bind the exact
corpus, oracle, source files, provider versions, models, order, costs and adjudications.
Baseline was `9bd9b893ef7d21903aa704eb31176206eb9abe74`; measured candidate was
`9f25e79f76455bf801f7f1c722657d35865b4b9c`. The production package bytes remain those
measured bytes; later changes concern benchmark guards, scoring, tests and documentation.

Ten cases cover critique_branch, critique_plan, query, rebut and arbitrate; each ran twice
against each revision. One provider is fixed per case, with both providers represented.
Plan verification used Claude with real discovery, server capture and cold attestation.
Arbitration used both vendors, cleaner/attester enabled, and explicit repository-only
research mode. Rebut used authentic qualified query sessions, prescribed repair or no
repair, and the same session/provider on resume. This does not cover tracked-class rebut,
web-research arbitration, large corpora, or every provider/case combination.

Reviewers received isolated fixture repositories and opaque case IDs, without the answer
key or version label. The implementer adjudicated results with the frozen oracle and
exact output/audit bindings. Adjudication was not independently blinded human evaluation.

## Timing and calls

Means below use only pairs where both revisions completed the expected decision.
Rebut includes query setup plus rebut dispatch, with both components retained separately.
Queue time and human qualification delay are excluded. Provider-call stage durations can
overlap and are not summed as total review wall time.

| Mode | Successful pairs | Baseline mean s | Candidate mean s | Difference |
|---|---:|---:|---:|---:|
| critique_branch | 4 | 77.7 | 80.1 | +3.1% |
| critique_plan | 3 | 148.7 | 157.5 | +6.0% |
| query | 4 | 17.1 | 18.7 | +9.3% |
| rebut | 4 | 31.3 | 33.8 | +8.0% |
| arbitrate | 3 | 67.9 | 66.1 | -2.6% |

The 18 comparable pairs used 64 baseline and 65 candidate model calls. Across every trial,
baseline used 74 calls and candidate 77. The difference includes two evidence calls that
the failed baseline claim audit never reached, and one extra candidate staged validation
retry. Provider-reported token/cache usage is retained; subscription dollar charges and
independent human acceptance are not measured.

The deterministic production-handler replay still shows class-only final scheduling
reducing 5 calls to 2, and checkpoint handling reducing 2 to 1, for plan and branch paths.
Those paths are not exercised by the simple live census cases here. They are call-topology
evidence, not a live latency or quality guarantee.

## Outcomes and limitations

- Both versions detected the seeded arithmetic and scheduler defects. There were no
  case-level false clears or incorrect blocking decisions on completed clean controls.
- Baseline t026 failed claim verification with the exact issue 114 pattern: suffix rejection
  hid unsupported each/whole wording; its correction retained those quantifiers.
- Candidate t006 encountered those simultaneous errors, received both in the first
  diagnostic, repaired them in one correction, and completed capture and cold attestation.
  The [live acceptance record](issue_114_live_acceptance_2026-09-06.json) retains exact
  hashes and role outcomes. No extra product model call or weaker scope check was added.
- Candidate t040 remained unresolved despite both deciders choosing the correct option:
  Codex used an absolute temporary evidence path that did not resolve. The unresolved
  outcome is retained as non-success, not credited or retried.
- Candidate t032 correctly detected the arithmetic defect but incorrectly said n=1 was
  valid. Candidate t024 added a blocking test recommendation outside the seeded arithmetic
  oracle. Both observations remain in the adjudication records; decision credit must not
  be mistaken for complete explanation accuracy or a proven quality improvement.

The original pilot was invalidated by an observer compatibility bug and an inadequate
plan fixture. Its records, including interrupted and unstarted slots, remain at
`/tmp/paranoia-five-mode-pilot-20260906`. The corrected pilot used a new frozen manifest and
the same shared counter: 220 provider admissions across both pilots, below the 320 ceiling.
The valid pilot has forty completed trial records, including its one audit failure and one
unresolved arbitration. Original failures were not relabeled as product performance data.

Full original provider outputs and capture-bearing audit records remain locally under
`/tmp/paranoia-five-mode-pilot-v2-20260906`. The public artifact retains hashes, outcomes,
usage and adjudication metadata without duplicating complete captured source passages.

## Issue 49 remains open

This completes a rerunnable pilot, not the complete evaluation requested by
[issue 49](https://github.com/subvertnormality/paranoia/issues/49).
Closing that issue still needs an agreed representative corpus including consented real
defects, independent human acceptance ratings, agreed success thresholds, and enough
repeated trials to assess effectiveness and marginal cost with useful uncertainty bounds.
The observed 4.1% timing difference and 19/20 decision counts do not justify a general
performance claim.

## Checkpoint status

The #114 fix and benchmark are committed as a correctness and measurement checkpoint.
CODE convergence review is pending, deferred at the user's request while work pivots to
measured general speed improvements. This checkpoint is not a release acceptance or a
claim that the architecture work has improved end-to-end latency.
