# Empty-census experiment and delivery decision, 2026-09-06

## Decision
Retain the typed census execution extraction. Withhold the empty-census optimization under
the frozen plan's A6/B3 acceptance gate and A7 fallback. Both experiments completed, but
neither exercised the required candidate path for both Claude clean repetitions. All
twenty-four calls returned the expected clear/blocked arithmetic decision; that is weaker
than qualifying the proposed optimization. No eligibility rule was relaxed.

The current product source is byte-identical to extraction commit 37fcc92. Model
consolidation remains in every census. Experimental source is preserved at 8b9bd97 and
eaaf17d; the latter changes the harness only. These experimental timings are not a
performance claim for the delivered extraction.

## Corrected experiment
Production critique_branch ran with baseline 9336ce3 and candidate eaaf17d, Codex
gpt-6-astra and Claude claude-fable-5-1, high effort, browsing disabled, fresh isolated
lineages, alternating pair order and sequential trials. Each census still used three
parallel lanes. The manifest froze source/harness hashes, CLI versions, inputs, oracle,
stakes and order before spend.

The fixture has caller-enforced integer domain 0..1000 and an inclusive-sum contract.
The clean diff uses an equivalent arithmetic expression. Both variants include an
exhaustive executable regression; it passes clean code and fails the defective formula.
The defective formula excludes the upper endpoint. The implementer inspected exact
app.py evidence and durable blocking findings against the frozen oracle.

| Provider / case | Pair | Baseline seconds | Candidate seconds | Calls B/C | Path qualified |
| --- | ---: | ---: | ---: | --- | --- |
| codex / clear | 1 | 79.515 | 53.266 | 4/3 | yes |
| codex / clear | 2 | 66.437 | 53.392 | 4/3 | yes |
| codex / defect | 1 | 84.278 | 88.577 | 4/4 | yes |
| claude / clear | 1 | 56.163 | 79.623 | 4/4 | no |
| claude / clear | 2 | 61.827 | 78.631 | 4/4 | no |
| claude / defect | 1 | 74.974 | 84.105 | 4/5 | yes |

The two qualifying Codex clean pairs removed one provider call each. Their combined
wall time fell 26.9%, with individual baseline times spanning 66.437–79.515 seconds
and candidate times 53.266–53.392 seconds. These two observations do not establish
statistical confidence or a general speedup.

Both Claude candidates raised MINOR findings about an unexplained equivalent rewrite.
They correctly retained model consolidation and failed the empty-path qualification.
One Claude defective candidate needed the existing execution-lane validation retry;
the rejected payload and successful correction remain retained. Every defective control
retained the expected durable blocking arithmetic finding.

Across all six corrected pairs, candidate total wall time was 3.4% longer.
Including the unqualified trials prevents the selective Codex gain from becoming a
misleading overall claim. There were 47 admissions in this experiment and 46 in the
first, totaling 93 under the original shared ceiling of 96.

## Preserved first experiment
The first twelve trials used a blank-line-only clean diff because the reused worker
appended a newline to already terminated code; the fixture also lacked executable tests.
Claude correctly produced advisory findings, so neither candidate exercised the shortcut.
The corrected experiment was separately frozen for that demonstrated fixture problem;
it did not erase the first results or reset the budget. The beginning of the first
experiment also overlapped the local mutation runner, limiting its timing interpretation.
The corrected experiment ran after those local checks completed. No third experiment
was run to seek favorable findings.

## Equivalence and validation
In the corrected experiment, both qualifying Codex clean pairs have byte-equivalent
canonical settlement data and identical durable state after excluding only each fresh
fixture's snapshot digest. The first Claude clean pair has different advisory settlement
content; it is explicitly not an equivalence success. The record compares every pair
without dropping these differences.

Before withdrawal, the experimental product passed 1,917 regression tests and all 33
existing Protocol v2 mutation checks. Its focused public-handler tests covered plan
claim blocking, snapshot and contract authority, historical exclusions, all severities,
repaired lanes, provenance, local rejection, persistence ambiguity and provider/server
canonical comparison. Those tests and implementation remain available in the experimental
commit; they are not silently represented as tests of a delivered shortcut.

The delivered extraction passed 1,877 full-suite tests, all 33 existing mutation checks,
and CODE review against the exact plan with zero blocking findings. Two MINOR findings
(a stale README sentence and unbound mutable worker input files) were fixed afterward.
Nine focused harness tests pass, and all 24 original input specifications were checked
against their manifests with no mismatch. Product package bytes are unchanged; the minor
fixes have targeted deterministic validation but no fresh provider review. The
[validation record](census_extraction_validation_2026-09-06.json) binds exact source,
review snapshot, plan, logs, findings and these limits.
The extraction keeps validation, settlement and persistence in
their existing authorities. The main coordinator shrinks from 748 to 636 lines, and
the inclusive AST branch proxy from 154 to 106 (31.2% lower). Its new coordinator
functions are at most 28 lines. This is one bounded issue-50 step, not a complete parser
or handler redesign, nor a guarantee about future LLM performance.

## Plan disposition and remaining work
A1/A2 retain the inventory, typed result boundary, deterministic ordering, all-lane
completion and diagnostics. A3/A4 and the shortcut-specific portions of A5 are deferred
under A7 because B3 failed. A6 is executed and reported as unqualified, not waived.
The plan text is unchanged. Future optimization work needs a new explicit acceptance
contract that measures realistic eligibility and review–fix–review convergence rather
than repeatedly tuning this fixture. Issues 49 and 50 remain open.

The [machine-readable record](empty_census_benchmark_2026-09-06.json) contains both frozen
manifests, all trial summaries, exact canonical settlement and durable state, ordered
attempt summaries, qualifications and audit/state hashes. Raw provider channels remain
under the two local roots named in that record. The complete original report hashes and
first-experiment correction record are retained. The test corpus is small and adjudicated
by the implementer; it does not replace the independent broader evaluation required by
issue 49.

To reproduce the historical experiment, check out eaaf17d for the harness and experimental
candidate, and 9336ce3 for baseline. Freeze a new output directory with
scripts/run_empty_census_acceptance.py; run and report that frozen directory. Do not use
the current extraction as though it still contains the experimental path. Reproduction
spends provider calls and is separate from this completed campaign.
