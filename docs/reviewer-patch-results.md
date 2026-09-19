# Reviewer-authored patch proposal qualification

This record follows `docs/reviewer-patch-proposal-plan.md`. The public default remains
false. Explicit `propose_patch: true` is reserved for qualification until every pre-flip
gate passes; no proposal is applied or tested by the production path.

| Gate | Branch evidence | Plan evidence | Status / disposition |
| --- | --- | --- | --- |
| G1 feasibility | Six frozen families across both providers; retained successes and decline; the repeated-occurrence trial remains historically failed with a documented false-rejecting harness diagnosis | Structural routes qualified for both providers; Claude verified route qualified; Codex verified harness failure retained | PASS for implementation feasibility only |
| G2 local correctness | Pure protocol/rendering plus Git-backed directory, pre-read byte admission, retry cache, clean/stale caller, inert rendering, exception containment with retained attempt evidence, rebut-role exclusion and public-handler lifecycle coverage | Exact plan capture/newline/staleness, source-processing and localized-omission exclusion, audit/trailer equality, custody, the same failure matrix, and a public verified-plan factual-repair lifecycle with real capture, binding and cold attestation | PASS pre-flip on the current branch |
| G3 state independence | Paired isolated state roots drive the production census/materializer/class engine/persistence through nonempty debt/class, an actual committed wrong repair, correct repair and cold final; true and false successors/trailers match | Paired isolated state roots drive both structural-only and verified production plan lifecycles through nonempty debt/class/claim state, wrong and scope-weakening text, correct text and cold final; true and false review/class/claim successors and trailers match | PASS pre-flip |
| G4 native correctness | Production-entry native campaign authorized but not run | Production-entry native campaign authorized but not run | PENDING campaign execution |
| G5 usefulness | Paired E1-E9 experiment not run | L8/L9 paired experiment not run | PENDING; no benefit claim |
| G6 human quality | No named independent human inspection yet | No named independent human inspection yet | PENDING; cannot be supplied by an LLM |
| G7 delivery acceptance | Requires post-flip regression, primary E2E, docs/default agreement and CODE closure | Same, separately | BLOCKED until G1-G6 pass; no candidate flip |

## Current evidence

- Accepted PLAN digest: `c8ca80d70c699d65bf1c312d25af301e4df70fdc8fe88c94b4af56698d320a89`.
- Historical ledger: `docs/reviewer-patch-history.json` (139 exact transitions).
- Feasibility assessment: `docs/reviewer-patch-assessment.md` and adjacent native JSON records.
- Frozen but unlaunched campaign schedule and spend boundary:
  `docs/reviewer-patch-campaign-schedule.md`.
- Production path status: implemented under explicit true; omitted and false make zero
  proposal calls. `PROPOSE_PATCH_DEFAULT` remains false.
- Focused pre-flip matrix:
  `PYTHONPATH=src /home/andy/tools/paranoia-local/.venv/bin/pytest -q
  tests/test_patch_proposals.py tests/test_patch_proposals_integration.py
  tests/test_architecture_performance.py tests/test_engines.py
  tests/test_census_execution.py` — 223 passed in 17.83s.
- Full regression after CODE round-2 repairs:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,441 passed in 304.45s at checkpoint `3abac3a`. The per-process Git
  override prevents the host's SSH commit-signing policy from affecting temporary
  fixture repositories; it does not change product behavior. `git diff --check`
  passed and the checkpoint worktree was clean.
- The deterministic E2 evidence validator rejects mismatched state/trailer/snapshot/session
  custody, missing audit or cleanup evidence, invalid call counts, overlapping or unowned
  intervals, and derives the frozen 7/8-second repair and 17/18-second end-to-end examples
  identically in both arm orders.
- Known negative evidence: the Codex repeated-occurrence trial failed its one retry because
  the historical substring oracle falsely rejected both complete retained repairs; it remains
  recorded as failed rather than retroactively relabeled passing.
- The frozen Codex verified-plan probe lost exact attempt telemetry after a harness assertion.
- Cost: qualifying proposal calls added 8.3-26.5 seconds in the small feasibility set.
  Human time, subscription price, and comparative experiment cost remain unknown.

## Stop conditions currently active

Do not flip `PROPOSE_PATCH_DEFAULT`, publish delivered/default-on wording, or claim repair
speed/cost improvement until the frozen native paired campaign, separate branch/plan benefit
thresholds, complete interval/call custody, and named human quality inspection all pass.
