# Reviewer-authored patch proposal opt-in delivery

This record follows `docs/reviewer-patch-proposal-plan.md`. The public default remains
false and the user approved a narrower explicit opt-in merge after ruling out the
expensive paired campaign. Explicit `propose_patch: true` requests the qualified
supplement; no proposal is applied or tested by the production path. Default-on
performance benefit is not claimed.

| Gate | Branch evidence | Plan evidence | Status / disposition |
| --- | --- | --- | --- |
| G1 feasibility | Six frozen families across both providers; retained successes and decline; the repeated-occurrence trial remains historically failed with a documented false-rejecting harness diagnosis | Structural routes qualified for both providers; Claude verified route qualified; Codex verified harness failure retained | PASS for implementation feasibility only |
| G2 local correctness | Pure protocol/rendering plus Git-backed directory, pre-read byte admission, retry cache, clean/stale caller, inert rendering, exception containment with retained attempt and rejected-payload evidence through retry preparation, requested/returned proposal-handle rebut exclusion and public-handler lifecycle coverage | Exact plan capture/newline/staleness, source-processing and localized-omission exclusion with UNAVAILABLE rendering, audit/trailer equality, custody, the same failure matrix through retry preparation, and a public verified-plan factual-repair lifecycle with real capture, binding and cold attestation | PASS pre-flip on the current branch |
| G3 state independence | Paired isolated state roots drive the production census/materializer/class engine/persistence through nonempty debt/class, an actual committed wrong repair, correct repair and cold final; true and false successors/trailers match | Paired isolated state roots drive both structural-only and verified production plan lifecycles through nonempty debt/class/claim state, wrong and scope-weakening text, correct text and cold final; true and false review/class/claim successors and trailers match | PASS pre-flip |
| G4 native correctness | Current-source public-handler Codex E2E produced a validated, CURRENT two-file proposal in one call | Earlier feasibility covers structural and verified plan paths | Campaign not run; sufficient only for explicit opt-in |
| G5 usefulness | Paired E1-E9 experiment not run | L8/L9 paired experiment not run | WAIVED for opt-in by user; no speed/cost benefit claim |
| G6 human quality | No campaign final-diff packet exists | No campaign final-diff packet exists | NOT APPLICABLE to cancelled campaign; user approved narrower opt-in |
| G7 delivery acceptance | Default remains false; full regression, docs/default agreement, CODE closure and current native E2E complete | Default remains false; production lifecycle coverage retained | PASS for explicit opt-in only; default-on remains unqualified |

## Current evidence

- Accepted PLAN digest: `c8ca80d70c699d65bf1c312d25af301e4df70fdc8fe88c94b4af56698d320a89`.
- Historical ledger: `docs/reviewer-patch-history.json` (139 exact transitions).
- Feasibility assessment: `docs/reviewer-patch-assessment.md` and adjacent native JSON records.
- Frozen but unlaunched campaign schedule and spend boundary:
  `docs/reviewer-patch-campaign-schedule.md`.
- Production path status: implemented under explicit true; omitted and false make zero
  proposal calls. `PROPOSE_PATCH_DEFAULT` remains false by explicit delivery decision.
- Repository-only two-provider arbitration unanimously selected `merge-opt-in`.
  Both deciders identified that flipping the constant alone would turn some valid
  omitted-flag calls into eligibility errors; default-on needs separate tri-state
  eligibility work. The arbitration used one round and no web research.
- Current-source primary E2E: public `critique_branch` with explicit true produced
  one validated two-file Codex proposal in 23,819 ms, exact snapshot/structural
  bindings, `APPLICATION-SUITABILITY: CURRENT`, and an audit receipt. The reviewer
  applied nothing and ran no tests.
- Focused pre-flip matrix:
  `PYTHONPATH=src /home/andy/tools/paranoia-local/.venv/bin/pytest -q
  tests/test_patch_proposals.py tests/test_patch_proposals_integration.py
  tests/test_architecture_performance.py tests/test_engines.py
  tests/test_census_execution.py` — 225 passed in 17.10s.
- Full regression after CODE round-3 repairs:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,449 passed in 310.92s at checkpoint `01279d9`. The per-process Git
  override prevents the host's SSH commit-signing policy from affecting temporary
  fixture repositories; it does not change product behavior. `git diff --check`
  passed and the checkpoint worktree was clean.
- Full regression after CODE round-4 repairs:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,451 passed in 315.77s at checkpoint `39bb2b2`. The same per-process Git
  override was used for temporary fixture repositories; `git diff --check`
  passed before the code checkpoint and the committed checkpoint was clean.
- CODE round 5 reached structural `NOT-BLOCKED` but identified one actionable
  minor defect: adjacent individually valid replacements could cancel to the
  pinned original bytes and render a header-only patch. The repair rejects that
  group through the existing branch/plan validation retry while retaining valid
  adjacent edits.
- Full regression after that CODE round-5 repair:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,456 passed in 296.77s at checkpoint `33d477e`. The focused proposal
  matrix passed 230 tests and the clean committed issue-115/117/126 guard set
  passed 68 tests.
- CODE round 6 found one blocking cleanliness defect and one minor prospective
  path defect. Branch proposal admission and suitability now compare HEAD,
  index, untracked paths, modes, kinds, and raw bytes without invoking
  repository-selected clean/process filters. Create validation rejects
  case-folded new/new and existing-ancestor file/directory collisions.
- Full regression after the CODE round-6 repairs:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,457 passed in 288.21s at checkpoint `806266a`. The proposal matrix
  passed 231 tests and the clean committed issue-115/117/126 guard set passed
  68 tests.
- CODE round 7 closed structural debt with no findings. Its round-8 cold final
  was structurally clear but found one minor prospective-inventory edge case:
  differently cased implied directory prefixes could escape collision
  validation. The repair now rejects shallow and deep implied-directory aliases
  while preserving consistently spelled shared directories.
- Full regression after that cold-final repair:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,457 passed in 264.93s at checkpoint `f463159`. The proposal matrix passed
  231 tests and the clean committed issue-115/117/126 guard set passed 68 tests.
- CODE round 9 was structurally clear and identified four minor custody/status
  edges. The branch inventory now retains non-ASCII tracked names for portable
  path collision checks; empty uninitialized submodules remain clean while
  initialized ones are checked recursively; ignored create obstructions make
  application suitability STALE; and disabled claim verification leaves
  retained claim history inactive for supplemental status and targeting.
- Full regression after those CODE round-9 repairs:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,463 passed in 252.25s at checkpoint `8dc41cb`. The expanded proposal
  matrix passed 237 tests and the clean committed issue-115/117/126 guard set
  passed 68 tests.
- CODE round 10 was structurally clear and found one minor application-handoff
  edge: identical tracked leaf bytes could be reached through a symlinked
  checkout ancestor. Shared admission/suitability now requires real-directory
  ancestors for tracked leaves, with pre-dispatch refusal and post-response
  STALE coverage while preserving sparse-checkout and submodule handling.
- Full regression after the CODE round-10 repair:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,465 passed in 274.37s at checkpoint `8c8d707`. The proposal matrix passed
  239 tests and the clean committed issue-115/117/126 guard set passed 68 tests.
- CODE round 11 found one blocking supplemental-diagnostic retention defect and
  one minor uninitialized-submodule layout edge. Retry prompt/schema preparation
  failures now retain the completed invalid attempt, rejected payload, channels,
  session and timing without another dispatch, while preserving the settled
  review and trailer. Absent uninitialized gitlink leaves and ancestors are clean;
  existing symlink or non-directory ancestors remain rejected.
- Full regression after the CODE round-11 repairs:
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign
  GIT_CONFIG_VALUE_0=false PYTHONPATH=src
  /home/andy/tools/paranoia-local/.venv/bin/pytest -q --tb=short` —
  2,471 passed in 268.51s at checkpoint `b67897b`. The proposal matrix passed
  245 tests, all 19 historical allowance mutation guards passed, and
  `git diff --check` passed before the clean checkpoint.
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

## Default-on stop conditions retained

Do not flip `PROPOSE_PATCH_DEFAULT`, publish default-on wording, or claim repair
speed/cost improvement without a separate approved decision, corrected omitted-flag
eligibility semantics, and proportionate new acceptance evidence.
