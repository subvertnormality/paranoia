# Frozen reviewer-patch qualification schedule

Status: **CANCELLED WITHOUT LAUNCH — OPT-IN DELIVERY SELECTED**. Revision 2 was frozen on 2026-09-20
after the user explicitly approved the complete 16-pair external campaign,
synthetic fixture/plan/finding/prompt egress to both configured providers,
fresh Codex caller sessions, and the 708 reviewer/proposal/evidence plus 88
caller-invocation hard ceilings. The user subsequently ruled out the expensive
campaign and approved the narrower explicit opt-in merge. No campaign provider
or caller call was made; this schedule remains as the unexecuted historical design.
This schedule follows
`docs/reviewer-patch-proposal-plan.md` sections 12 and 16. It authorizes no
provider call beyond that explicit authorization. The converged implementation
under test is rooted at
`2b76c3fa44b14156df49eb38d60954b9b888bafe`; CODE rounds 12 and 13
closed the round-11 debt and completed a cold final with zero open classes.
Any production-code repair
requires a new recorded schedule revision before launch.

## Fixed operating choices

- Stakes are the frozen local-tool model in the accepted plan: trusted single
  user and OS; fixture repository/plan/model text is untrusted static data; no
  repository-selected execution by the reviewer, hostile local race, compromised
  OS, multi-tenancy, or corrupt-state recovery.
- Reviewer providers are the configured native Codex and Claude routes with
  their repository-role defaults and normal effort mapping.
- Both arms use fresh Codex caller sessions with model `gpt-6-astra`, effort
  `high`, identical workspace-write tools, the same fixture specification and
  the same frozen allowed test commands. No repair subagents are permitted.
- The seed is one production public-handler call with
  `propose_patch: true`; every correction/final call sets it false.
- Tasks are serial. Native census lanes retain their production concurrency.
  Baseline-first/candidate-first order is balanced within each provider.
- Hidden behavioral oracles and scoring material remain outside reviewer and
  caller workspaces. Failed, declined, censored and harness-error slots remain
  in the result table; there are no optional reruns.

## Branch pairs

Each family runs once per reviewer provider. B1-B5 are actionable; B6 is the
predeclared decline control.

| Slot | Provider | First arm | Family | Frozen obligation and hidden check |
| --- | --- | --- | --- | --- |
| B1-CX | Codex | baseline | Local Boolean identity | Reject Boolean aliases where an exact integer is required; hidden cases cover `True`, `False`, integers and ordinary invalid scalars. |
| B1-CL | Claude | candidate | Local Boolean identity | Identical fixture/oracle to B1-CX. |
| B2-CL | Claude | baseline | Cross-file invariant | Repair both admission and replay consumers of one canonical identity rule; either single-file repair fails the hidden cross-file check. |
| B2-CX | Codex | candidate | Cross-file invariant | Identical fixture/oracle to B2-CL. |
| B3-CX | Codex | baseline | Repeated class occurrences | Repair all three independently reachable occurrences of one validation defect; a surviving sibling fails. |
| B3-CL | Claude | candidate | Repeated class occurrences | Identical fixture/oracle to B3-CX. |
| B4-CL | Claude | baseline | Regression-prone repair | Preserve the successful path and bounded diagnostic channels while correcting the failing branch; hidden regression tests cover both. |
| B4-CX | Codex | candidate | Regression-prone repair | Identical fixture/oracle to B4-CL. |
| B5-CX | Codex | baseline | Misleading suggested syntax | Satisfy the behavioral invariant; the oracle accepts a correct alternative and rejects blind use of the suggested syntax. |
| B5-CL | Claude | candidate | Misleading suggested syntax | Identical fixture/oracle to B5-CX. |
| B6-CL | Claude | baseline | Architectural decision | The fixture omits the governing product policy. A safe result must decline rather than invent authority or emit a patch. |
| B6-CX | Codex | candidate | Architectural decision | Identical fixture/oracle to B6-CL. |

## Plan pairs

P1/P2 are structural-only. P3/P4 are verified factual repairs using the
qualified Python Boolean/integer proposition from the feasibility fixture. The
starting claim is intentionally false; the repair must preserve the plan's
acceptance obligations and must not treat evidence for the old wording as
automatic attestation of replacement wording.

| Slot | Provider | Input | First arm | Family | Frozen hidden check |
| --- | --- | --- | --- | --- | --- |
| P1-CX | Codex | `plan_text` | baseline | Structural rollout/acceptance repair | Require bounded rollout, rollback trigger and executable acceptance; dropping an obligation fails. |
| P2-CL | Claude | outside-repository `plan_path` | candidate | Structural rollout/acceptance repair | Identical semantic oracle to P1-CX; file capture and stale-preimage custody are also checked. |
| P3-CL | Claude | `plan_text` | baseline | Verified factual repair | Correct Python's Boolean/integer relationship from captured primary evidence while preserving acceptance scope. |
| P4-CX | Codex | repository-contained `plan_path` | candidate | Verified factual repair | Identical semantic oracle to P3-CL plus repository-contained single-target custody. |

## Spend and stop boundary

The hard new campaign ceiling is the accepted-plan maximum: 312 branch
reviewer/proposal calls plus 396 plan reviewer/proposal/evidence calls, and no
more than 72 branch plus 16 plan caller repair invocations. These are pathology
ceilings, not targets.

The ordinary planning estimate is approximately 108 branch and 66 plan
reviewer/proposal/evidence calls (about 174 total) plus 32 caller invocations
when each actionable arm repairs in one cycle and native replies validate on
the first attempt. Evidence reuse and real failures may move the actual count;
all actual admissions are retained by role/provider. At ordinary observed
review latencies this is expected to consume many hours, potentially more than
one working day. Subscription price is unknown and no monetary estimate is
invented.

Stop before launch unless the user explicitly authorizes this 16-pair external
campaign, its synthetic fixture/plan/finding/prompt egress to both configured
providers, the fixed Codex caller sessions, and the stated 708/88 hard
ceilings. A narrower authorization is a new schedule decision, not permission
to selectively trim tasks after results are visible.
