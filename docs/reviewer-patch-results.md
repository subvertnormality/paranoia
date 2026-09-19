# Reviewer-authored patch proposal qualification

This record follows `docs/reviewer-patch-proposal-plan.md`. The public default remains
false. Explicit `propose_patch: true` is reserved for qualification until every pre-flip
gate passes; no proposal is applied or tested by the production path.

| Gate | Branch evidence | Plan evidence | Status / disposition |
| --- | --- | --- | --- |
| G1 feasibility | Six frozen families across both providers; retained successes, decline, and repeated-occurrence failure | Structural routes qualified for both providers; Claude verified route qualified; Codex verified harness failure retained | PASS for implementation feasibility only |
| G2 local correctness | Pure protocol/rendering, native argv, continuation, custody, audit-failure and public-handler lifecycle matrix | Exact plan capture/staleness, current/reused claim gating, plan-path custody and the same failure matrix | PASS pre-flip at revision `8543823967a4a1e09eea2977d8fa42da5ed13910` |
| G3 state independence | Explicit true and false produce identical durable review/class state and existing trailer; proposal audit remains supplemental | Explicit true and false produce identical durable review/class/claim state and existing trailer | PASS pre-flip |
| G4 native correctness | Production-entry native campaign not run | Production-entry native campaign not run | PENDING explicit campaign authorization |
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
  `/home/andy/tools/paranoia-local/.venv/bin/pytest -q tests/test_patch_proposals.py
  tests/test_patch_proposals_integration.py tests/test_patch_experiments.py
  tests/test_engines.py tests/test_census_execution.py` — 135 passed in 6.93s.
- Full regression:
  `/home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,417 passed in 265.65s at the recorded revision before the final additional
  plan-mode G3 fixture; production code was unchanged by that fixture.
- The deterministic E2 evidence validator rejects mismatched state/trailer/snapshot/session
  custody, missing audit or cleanup evidence, invalid call counts, overlapping or unowned
  intervals, and derives the frozen 7/8-second repair and 17/18-second end-to-end examples
  identically in both arm orders.
- Known negative evidence: the Codex repeated-occurrence proposal failed its one retry;
  the frozen Codex verified-plan probe lost exact attempt telemetry after a harness assertion.
- Cost: qualifying proposal calls added 8.3-26.5 seconds in the small feasibility set.
  Human time, subscription price, and comparative experiment cost remain unknown.

## Stop conditions currently active

Do not flip `PROPOSE_PATCH_DEFAULT`, publish delivered/default-on wording, or claim repair
speed/cost improvement until the frozen native paired campaign, separate branch/plan benefit
thresholds, complete interval/call custody, and named human quality inspection all pass.
