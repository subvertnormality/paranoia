# Review effectiveness pilot

This measurement implements issue #49's bounded pilot alongside the
[typed lifecycle extraction](typed-lifecycle.md) for #50. The immutable
[accepted card](effectiveness-lifecycle-plan.md) governs acceptance.

## Scope and contract resolution

Preserve production reviewer roles and calls. A clean initial census already
settles clear after three lanes plus consolidation; correction requires its
normal cold final. Public-handler coverage confirms this behavior. Q3's wording
about always requiring a cold final overstated the existing lifecycle. The
implementation follows the user's explicit call-preservation instruction and
M3/B1: it never manufactures another review call. A partial census without
consolidation cannot receive clear credit. This is an implementation resolution,
not a reopened plan review.

The frozen corpus contains eight tiny fixtures: defective/corrected pairs from
two seeded families and two historical public Paranoia defects. Historical
functions are exact extracted spans with controlled helper context, not full
historical repository evaluations. Oracle records contain complete source
revisions, source/span hashes, specification and executable witness results.
Reviewers receive only one fixture, its specification, controlled helpers and
two deterministic commits. The base has no implementation; no control sibling,
fix commit message, oracle, score or other slot output is copied into that repo.

Each case has two repetitions of single query and native tracked branch review,
with balanced arm order. Four cases use each provider. Settings, versions,
source, harness, fixtures, prompt packet digests, order and the aggregate ceiling
of 192 provider calls freeze before the first call. Slots run sequentially in
fresh processes; census retains its native concurrency. No selective reruns.

## Reproduce

Use Python 3.11+, the configured Codex/Claude CLIs and a committed source checkout.
Keep the harness checkout and source unchanged until replay is complete.

    python scripts/benchmark_effectiveness.py /tmp/pilot --freeze --source /path/to/source
    python scripts/benchmark_effectiveness.py /tmp/pilot --run
    python scripts/benchmark_effectiveness.py /tmp/pilot
    python scripts/score_effectiveness.py /tmp/pilot --seal
    python scripts/score_effectiveness.py /tmp/pilot
    python scripts/score_effectiveness.py /tmp/pilot --human
    python scripts/score_effectiveness.py /tmp/pilot --ratings /path/to/ratings.json

The sole campaign gate rechecks frozen bindings, every worker specification,
fixture history/bytes, native invocation and audit, process channels, attempt
admission sequence and terminal receipt. Errors retain readable attempts and
costs but remove semantic credit. Failed provider prose, zero-call slots and
unsettled census cannot score clear. Validation retries remain native calls.

Initial provider prompts must match the native query renderer or contain the
exact frozen census diff; withheld benchmark markers reject before admission.
After adjudication, --seal creates a receipt binding score bytes to the original
immutable terminal hashes. Report replay rejects changed scores or terminals.
It never rewrites an execution terminal to attach later adjudication.

Slot wall time includes preflight/context preparation, actual dispatch and
postflight, including failed dispatches; per-dispatch wall time is retained
separately. Concurrent role durations are not added and presented as wall time.
Provider token usage is retained where available; missing usage is unknown.
Subscription dollar cost remains unknown rather than being inferred from tokens.

## Adjudication and limits

An implementer writes each slot's closed score.json, binding every output digest,
an explicit verdict quotation, complete coverage attestation and exact quotations
for every actionable assertion. Staged findings also bind native governing IDs.
Target detections bind the frozen witness; false positives quote counterevidence
from the frozen specification. Duplicated descriptions cluster as one defect.
Advisory, non-finding, unscored and fixture-problem outcomes remain distinct.
Unknowns prohibit superiority; failures remain in scheduled denominators.
Precision with no findings is null. The tiny sample supports descriptive results,
not population guarantees or an all-mode speed claim.

The human packet preserves native text except its exact server footer.
Oracle, implementer scores and experimental labels are omitted, but native
workflow/provider cues may remain: the packet explicitly discloses that limitation.
Validation reconstructs every item and private mapping from qualified custody.
Andy owns independent ratings: accept/reject/uncertain with a reason for every
digest-bound item. Acceptance needs at least 90% accept, no accepted false clear
and qualified complete implementer scoring. Pending ratings do not become an
acceptance claim; they remain a named #49 residual even if measurement code merges.

The current work does not claim a 20% speedup. #50 is justified by measured
maintenance simplification and exact behavioral equivalence. Any later speed
candidate must meet the user's separate end-to-end time/cost gate.

## Qualification status

The first frozen campaign at ec39686 was stopped before adjudication when a
contract check identified missing explicit prompt-contamination admission and
later scoring custody. Four slots completed, 28 were honestly cancelled, and
10 calls were retained. Its original custody gate passes; no effectiveness
comparison is claimed from this stopped campaign. The complete replacement
schedule must include all 32 slots, not selected outcomes, and its freeze uses
--call-limit 182 so combined admission remains below the original 192 ceiling.
The stopped campaign lives at /tmp/paranoia-effectiveness-pilot-2026-09-07;
campaign-stop.json records the reason, slots and exact spend.

Before replacement admission, the new deterministic gate has 32 passing tests,
including both fixture variants through both public handlers, contaminated base
history/prompts, ordinary edits before and after dispatch, failed providers,
missing consolidation, custody tampering, and score/human-rating bindings.
The full suite passed 2,112 tests before those last added harness checks.
CODE review and complete live measurement remain delivery gates.
