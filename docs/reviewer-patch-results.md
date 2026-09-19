# Reviewer-authored patch proposal qualification

This record follows `docs/reviewer-patch-proposal-plan.md`. The public default remains
false. Explicit `propose_patch: true` is reserved for qualification until every pre-flip
gate passes; no proposal is applied or tested by the production path.

| Gate | Branch evidence | Plan evidence | Status / disposition |
| --- | --- | --- | --- |
| G1 feasibility | Six frozen families across both providers; retained successes, decline, and repeated-occurrence failure | Structural routes qualified for both providers; Claude verified route qualified; Codex verified harness failure retained | PASS for implementation feasibility only |
| G2 local correctness | Focused protocol, engine, custody, audit, and public-handler tests | Same plus exact plan capture/staleness and claim gating | IN PROGRESS; default stays false |
| G3 state independence | Enabled proposal is supplemental and trailer/state assertions are covered | Same | IN PROGRESS |
| G4 native correctness | Production-entry native campaign not run | Production-entry native campaign not run | PENDING explicit campaign authorization |
| G5 usefulness | Paired E1-E9 experiment not run | L8/L9 paired experiment not run | PENDING; no benefit claim |
| G6 human quality | No named independent human inspection yet | No named independent human inspection yet | PENDING; cannot be supplied by an LLM |
| G7 delivery acceptance | Requires post-flip regression, primary E2E, docs/default agreement and CODE closure | Same, separately | BLOCKED until G1-G6 pass; no candidate flip |

## Current evidence

- Accepted PLAN digest: `c8ca80d70c699d65bf1c312d25af301e4df70fdc8fe88c94b4af56698d320a89`.
- Historical ledger: `docs/reviewer-patch-history.json` (139 exact transitions).
- Feasibility assessment: `docs/reviewer-patch-assessment.md` and adjacent native JSON records.
- Production path status: implemented under explicit true; omitted and false make zero
  proposal calls; full pre-flip verification is still in progress.
- Known negative evidence: the Codex repeated-occurrence proposal failed its one retry;
  the frozen Codex verified-plan probe lost exact attempt telemetry after a harness assertion.
- Cost: qualifying proposal calls added 8.3-26.5 seconds in the small feasibility set.
  Human time, subscription price, and comparative experiment cost remain unknown.

## Stop conditions currently active

Do not flip `PROPOSE_PATCH_DEFAULT`, publish delivered/default-on wording, or claim repair
speed/cost improvement until the frozen native paired campaign, separate branch/plan benefit
thresholds, complete interval/call custody, and named human quality inspection all pass.
