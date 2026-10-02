# Beta tiered review: native qualification record

Contract: [`beta-tiered-review-plan.md`](beta-tiered-review-plan.md) §8.
Date: 2026-09-23. Candidate source: the branch working tree applied as scratch commit
`802c6d3` on base `bdeb5d1` (WSL workspace; the delivery commit is separate).
CLIs: Codex CLI 0.156.1 (ChatGPT account), Claude Code 2.1.280.
Evidence: [`beta-tiered-review-qualification-evidence.tar.gz`](beta-tiered-review-qualification-evidence.tar.gz)
(every round record, output, attempt ledger and proposal ledger of both campaigns).

**Verdict: readiness BLOCKED.** Three of four fixtures qualified; `plan-codex` reached the
six-invocation ceiling without acceptance. Per §8 the failure is reported, not resampled, and
`0.2.0b1` is not assigned.

## Preconditions observed

- Codex CLI 0.153.3 on a ChatGPT account was not offered `gpt-6-sol`. The tiered
  correction round failed visibly as a staged execution failure with no model substitution.
  After updating to 0.156.1 the model was offered. See plan §10.2.
- CODE convergence on this candidate (lineage `beta-tiered-review-code`) reached
  `CONVERGENCE: NOT-BLOCKED` with `BETA-ACCEPTANCE: qualified` after five rounds:
  - Codex census;
  - two Codex/Sol corrections, one of which failed because of the old CLI;
  - two Claude/Fable corrections under `review_model_policy: strongest`, at the user's request;
  - a Claude/Fable cold final.

## Campaign 1: scripted author (failed, retained)

The scripted author (`qualify.py`) could apply only its one canned repair. Real reviewers
then found legitimate further defects in the fixtures that the canned repair did not
address:
- total-versus-discount rounding;
- missing tests;
- plan contract gaps.

The scripted author resubmitted unchanged artifacts until the branch runs crashed on an empty
commit and the plan runs reached the ceiling. None qualified. The campaign did show, natively:
- correct phase routing;
- census proposals on both providers;
- two declined candidates;
- a Codex blocked-final proposal resumed from that final's own session.

The campaign is a harness failure, not a product fault. It is retained unchanged in the
evidence archive.

## Campaign 2: operator as author

Each round is one public handler invocation (`qround.py`). Between rounds the operator:
- read the findings;
- applied, adapted or declined candidates;
- ran the fixture checks (`unittest` for branches; a design prototype for plan-codex);
- committed the result.

A genuine regression was injected before the pending final of `branch-claude` to exercise a
Claude blocked-final proposal.

| Fixture | Round | Structural role: model/effort | Proposal (model/effort) | Phase after | Acceptance | Seconds |
|---|---|---|---|---|---|---|
| branch-codex | 1 | census, consolidation: gpt-6-astra/medium | PROPOSED (gpt-6-astra/medium); applied + tests | correction | - | 113.7 |
| branch-codex | 2 | correction: gpt-6-sol/high | UNAVAILABLE (correction-ineligible) | final | - | 49.2 |
| branch-codex | 3 | final: gpt-6-astra/medium | NOT-NEEDED | clear | **qualified** (tiered) | 78.5 |
| branch-claude | 1 | census, consolidation: claude-fable-5-1/medium | PROPOSED (fable/medium); applied | correction | - | 106.5 |
| branch-claude | 2 | correction: claude-opus-5-5/high | UNAVAILABLE | final | - | 23.3 |
| branch-claude | 3 | final: claude-fable-5-1/medium, blocked on injected regression | PROPOSED from the final's own session (fable/medium); applied | correction | - | 68.2 |
| branch-claude | 4 | correction: claude-opus-5-5/high | UNAVAILABLE | final | - | 14.1 |
| branch-claude | 5 | final: claude-fable-5-1/medium | NOT-NEEDED | clear | **qualified** (tiered) | 38.3 |
| plan-claude | 1 | census, consolidation: claude-fable-5-1/medium | PROPOSED; applied, then adapted | correction | - | 229.0 |
| plan-claude | 2 | correction: claude-opus-5-5/high | UNAVAILABLE | correction | - | 159.1 |
| plan-claude | 3 | correction: claude-opus-5-5/high | UNAVAILABLE | final | - | 176.3 |
| plan-claude | 4 | final: claude-fable-5-1/medium | NOT-NEEDED | clear | **qualified** (tiered, verified plan, claims supported) | 101.4 |
| plan-codex | 1 | census, consolidation: gpt-6-astra/medium | PARTIAL; declined (left a blocking residual) | correction | - | 189.4 |
| plan-codex | 2 | correction: gpt-6-sol/high | UNAVAILABLE | correction | - | 159.8 |
| plan-codex | 3 | correction: gpt-6-sol/high | UNAVAILABLE | correction | - | 265.5 |
| plan-codex | 4 | correction: gpt-6-sol/high | UNAVAILABLE | correction | - | 212.9 |
| plan-codex | 5 | correction: gpt-6-sol/high | UNAVAILABLE | correction | - | 307.4 |

`plan-codex` round 6 was not run. It would have been a correction, which cannot produce
acceptance, so the fixture failed at the ceiling. Every round narrowed to finer legitimate
obligations. The author's own plan text also made an external claim, that a SQLite timeout
bounds thread lifetime, and the verifier correctly refuted it against the authoritative
documentation. These are plan-authoring convergence limits of the fixture, not observed
routing or proposal faults.

## Established natively (both campaigns)

- **Phase routing:** census and consolidation ran on the strongest model at medium effort,
  and correction on Sol/Opus 5.5 at high effort, for both providers and both modes. Every
  trailer and attempt row carries the actual model and effort.
- **Census proposals:** they resume a successful census lane session with the source model
  and effort.
- **Blocked-final proposals:** they resume that final's own session with its model and effort,
  for both providers: Codex in campaign 1, Claude in campaign 2.
- **Correction rounds:** they are proposal-ineligible and make no call. Clean results report
  `NOT-NEEDED`.
- **Candidate handling:** the author inspected, applied, adapted and declined candidates; a
  PARTIAL candidate that left a blocking residual was declined.
- **Cold-final acceptance:** strongest-model cold finals clear to `BETA-ACCEPTANCE: qualified`
  on branch and on a verified plan. A pending final is owned by the engine that created it.
- **Claim verification during routed corrections:** it keeps the call-level model. It
  supported, refuted and demoted claims with authoritative evidence, and correctly refuted an
  author overstatement.
- **Unavailable model:** it fails visibly, with no fallback.

## Not established and residuals

- No verified Codex plan reached acceptance within the ceiling.
- Clean census → final was not observed natively, because every native census found real
  defects. It is covered by deterministic public-handler tests.
- Claim-role attempt rows (`claim-discovery`, `claim-binding`, `claim-attestation`) do not
  record model/effort; only staged and proposal attempts do. Claims are not routed; recording
  them is a follow-up.
- Before the conftest guard was added, the Linux test suite launched an unknown small number
  of real `codex exec resume s1` invocations against a fake session id. The guard now
  prevents this, and a stub-CLI Linux run showed no provider invocation.
- Follow-up (agreed): `plan-codex` debt stayed unclassed, with `CLASS-CLOSURE` showing 0
  open throughout. The class-based persistence warning, correction gate and architecture
  checkpoint therefore never engaged, and broad one-off debt could churn until the
  invocation ceiling. Model consistency across tiers is unmeasured: one churning Codex
  fixture against one converging Claude fixture, with author churn as a confounder.
- Savings and quality equivalence remain hypotheses (plan §9). Observed wall time is recorded
  above; subscription usage is not an API charge.
