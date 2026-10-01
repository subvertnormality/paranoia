# Review recovery and arbitration diagnostics (#131–133)

Implement this bounded repair on main with behavioral regressions before production edits.
The delivery sequence is defined in the final paragraph. Separate explicit lineages, increment rounds;
require computed CONVERGENCE: NOT-BLOCKED and preserve historical failed lineages.

## Frozen stakes

Local CLI/MCP tool; one trusted operator and OS, sequential lineage rounds. Plan,
repository, fetched bytes and model responses are untrusted data. No hostile local
race, compromised OS, multi-tenancy or deliberately corrupted state recovery.
Tens to low hundreds of findings; useful answers within minutes. False clearance
and wrong evidence authority have high impact; recoverable false blocks acceptable.
Existing providers, retry, claim, canonical class and cold-final gates remain.
No Parallax datasets, registries, certificates or trading behavior changes.

## Verified evidence

- #131 audit 20260928T113240-critique_plan-68ac411d contains a validated
  consolidation finding about missing source rationales after one rejected reply.
  Lane citation objects are projected to canonical strings before consolidation.
  This is a semantic failure, not a terminal parser rejection.
- #132 handlers.rebut restricts plan anchors to the target debt even though the
  checkpoint stores the current reviewed snapshot and plan_line_count.
- #133 audit 20260929T084712-arbitrate-66935784: Claude changed its selection;
  decisive AGENTS.md:151 is outside carried AGENTS.md:176-182. Anti-capitulation
  legitimately refuses agreement. Diagnose this without broadening eligibility.

## Changes and acceptance

1. Consolidation prompts explain manifests intentionally contain bare anchors.
   Derive citation rationales from validated source summaries/remedies and evidence,
   without re-reviewing or inventing findings about transport-contract metadata.
   Cover initial and existing same-session retry, plan and branch roles. Keep mapped
   source validation, severity, complete union projection and canonical manifests.
   Terminal invalid replies remain failed and mint no substantive debt. Historical
   settled D1 is never deleted or auto-closed: a normal correction reviewer may
   withdraw it with counter-evidence, as for any wrongly raised one-off finding.
   Required regression matrix: test_consolidation_canonical_evidence_contract runs
   public critique_plan and critique_branch with validated bare-anchor manifests,
   initial success, single validation-retry success, and terminal invalid replies.
   Inspect actual production-composed initial and retry prompts for the input/output
   distinction and rationale derivation. Successful settlement must retain the exact
   mapped-source evidence union and highest severity; invalid replies must preserve
   existing substantive debt and add no new substantive debt. A separate correction
   fixture must withdraw historical one-off metadata debt only through reviewer output.
   These deterministic regressions are mandatory delivery gates, not evidence that
   every possible native consolidator will interpret the prompt correctly.
2. Bound plan rebut accepts any strictly parsed in-bounds plan anchor against the
   latest stored reviewed plan_line_count, rather than only original debt anchors.
   Use the checkpoint's current snapshot digest for concessions; do not read newer
   unreviewed plan paths. Keep exact lineage/class/debt/session bindings, failure
   refusals, HOLD audit-only behavior, sibling blockers, atomic settlement and cold
   final. Missing/out-of-range bounds refuse; branch contracts remain unchanged.
3. Arbitration keeps per-engine boolean substantiation and adds reason diagnostics
   from the same decisive-evidence evaluation: missing decisive citation; unresolved
   repository citation; source-packet eligibility/attestations/constraint mismatch;
   moved source reference; resolved region outside gained carried evidence. Include
   decisive citation and failure category in final REASON and existing outcome audit.
   Operational resolver errors propagate. Preserve verdict precedence, supporting
   citation exclusion, mover/holder rules and the two-round limit.

Tests cover public handlers where state/reports change: durable reload; checkpoint
with shifted coordinates; invalid bounds; HOLD/CONCEDE and sibling debt; unanimous
round-two agreement rejected for carried grounding versus missing repository evidence.
Focused tests during development, complete Paranoia suite before PR. Update public
tool documentation and agent instructions before CODE review. Native Codex PLAN/CODE
reviews exercise the primary capability end to end; retain native attempts/failures
without claiming fake-backed tests establish native usability for every changed path.
After tests and CODE convergence publish one PR fixing all three issues, wait on
required checks, merge, reinstall configured local Paranoia from merged main and
verify import source and console entry point. Preserve unrelated untracked files.
