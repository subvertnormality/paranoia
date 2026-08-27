# Plan: reduce plan-review correction/final cycles without weakening clearance

## Objective and evidence boundary

Reduce the number of tracked `critique_plan` rounds needed to reach a correct plan by making
late correction reviews search for adjacent defects before they hand the artifact to the
independent cold final. The cold final, severity rules, evidence validation, class engine, claim
verification, and convergence transition remain unchanged.

This is an evidence-led experiment, not a promise that every plan will converge faster. An
exploratory local sample of three recent long Parallax plan lineages found frequent blocking cold
finals on unchanged plan digests, commonly as successive findings in the same active class, while
provider execution errors were rare. The local audit directory is not an authoritative expected-
event inventory, so its numerical sample is motivation only: it is not shipped as a complete
cohort, efficacy result, or release acceptance claim.

The current implementation gives final the complete nine-item checklist while correction receives
an empty checklist and is told to cover exactly affected classes. A clean correction then
mechanically advances to final. This plan tests whether a bounded broad sweep in a likely-to-close
correction reduces cold-final rejection, without using the correction as clearance.

## Supported operating model

- One trusted operator and trusted OS use the local tool against one repository and plan.
- Repository, plan, fetched pages, and provider output are untrusted data, not executable authority.
- No hostile local process races state or repository paths.
- Ordinary concurrent edits must block or retry rather than reuse a stale decision.
- Plans may be long; lineages normally contain tens to low hundreds of claims/classes/rounds.
- A false `NOT-BLOCKED`, incorrect authority decision, or lost evidence/class binding is high impact.
- Recoverable extra blocking is acceptable; useful review output is expected within minutes per role.
- Multi-tenancy, compromised OS/provider, hostile same-user races, deliberately corrupted state,
  and formal proof are excluded.

## Design

### 1. Server-owned, plan-only closure-candidate classification

Add a pure helper used only when `mode == PLAN_MODE` that classifies a correction as a
`closure_candidate` when its durable state has one or two blocking units. A blocking unit is a
distinct active class whose severity is `FATAL|BLOCKER|MAJOR` and whose status is one of the
canonical unproven statuses, whether or not current debt is bound to it, plus one synthetic unit
for each open blocking debt that has no valid reference to such a class. Unit identities are
`class:<class_id>` in active-class encounter order followed by `debt:<debt_id>` in durable-debt
encounter order. Multiple debt rows bound only to the same class remain one unit; a debt bound to
several valid active blocking classes contributes those distinct class units and no synthetic
unit. A reference to any active blocking class in a canonical unproven status—including
`malformed`, `over-broad`, or `unchecked`—is a valid binding because that class is already one unit.
Unknown, closed, superseded, or advisory class targets do not make a debt bound: an otherwise
unbound open blocking debt contributes a synthetic unit. A non-object debt,
missing/non-string/duplicate debt ID, non-list `class_ids`, or non-string class reference raises
`CensusError` before provider spend. Zero units and three or more units are `targeted`.

Branch correction does not call the helper and retains its current packet, prompt, schema, and
settlement path byte-for-byte. Census and final do not call it in either mode.

In `_staged_structural_review`, invoke the helper only when `mode == PLAN_MODE` and the phase read
from normalized state is already `correction`. Invoke it immediately after constructing
`active_classes` and before the existing `debt_class_ids`, `has_blocking_debt`, legacy-migration,
unbound-class, correction-gate, or open-debt logic dereferences or iterates any debt row or
`class_ids`; retain its validated unit tuple for later scope selection. Census—including the
existing legacy in-call census-to-correction recovery—final, and every branch role do not invoke
the helper and retain their current behavior. A helper `CensusError` follows the existing staged
validation-failure settlement path, persists visible blocking failure, records an empty structural
attempt ledger, and spends zero provider calls.

The threshold is deliberately small. It targets the tail of a correction sequence while avoiding
a broad duplicate of the census before the design has stabilized; it is an experimental policy,
not a conclusion derived from the final-only audit metric. The helper is deterministic and has no
persisted state.

### 2. Enrich only the existing plan-correction call

For a closure candidate, include in the existing correction task packet:

- `review_scope: "closure_candidate"`;
- the same complete nine-item checklist supplied to final;
- all active class definitions already supplied today.

For ordinary plan corrections use `review_scope: "targeted"` and retain an empty checklist. Final
retains its current task packet. Branch correction retains the exact current JSON object: it does
not receive `review_scope` or any checklist change.

Do not persist review scope or add an audit field. Prompt-capture acceptance proves which packet
the production handler constructs; existing `staged_settlement`, `error`, and `attempt_ledger`
remain the only result channels. A frozen complete branch audit dictionary from the pre-change
production handler proves that excluded audit records remain unchanged.

### 3. Tell the reviewer exactly what the sweep means

Revise the follow-up instructions so a closure-candidate correction must, after checking the
specific repairs, scan the complete artifact against every supplied checklist item and active
class for sibling occurrences, cross-reference contradictions, and repair-created regressions.
Any defect is returned through the existing governing-finding/classification shape.

Construct this directive only inside the `mode == PLAN_MODE and role == "correction" and
review_scope == "closure_candidate"` handler branch and append it to that call's composed
instructions. Do not edit the shared base follow-up instruction in a way that changes other roles.
The exact composed plan-final and branch-final prompts must remain byte-identical to frozen
pre-change oracles.

Do not require satisfied outcomes for every active class in correction and do not introduce a new
schema role. The sweep is broader search within the existing correction judgement. The independent
final still authors every active-class outcome and every checklist coverage row.

### 4. Preserve the convergence boundary

Do not change `settle_state`: a correction with no blocking debt still advances to `final`, never
to `clear`. Do not add a provider call, reuse a correction session as final, auto-close a class,
change severity, or suppress advisory findings.

### 5. Keep measurement claims narrower than the evidence

Do not add an audit field, general audit analyzer, cohort schema, or post-change efficacy claim in
this card. Delivery claims are limited to the mechanically testable behavior: eligible plan
corrections receive one broader search packet, excluded roles do not, valid sibling findings
settle durably, and only the independent final can clear.

## Tests and acceptance

### Deterministic tests

1. Unit-test classification for zero, one, two, and three distinct blocking classes; repeated debt
   for one class; advisory debt; unbound active classes; bound and unbound debt; one debt bound to
   multiple classes; mixed valid/invalid references; and references to advisory, closed,
   superseded, or unknown classes; one and two bound classes whose canonical status is `malformed`;
   and structurally malformed rows/references. Assert exact unit identities, threshold results,
   and every fail-closed malformed-row case.
   Through the production plan handler, repeat malformed debt-row/reference cases and assert a
   `CensusError`-backed durable validation failure, empty attempt ledger, and zero provider calls;
   this proves preflight precedes every existing debt dereference.
   Add a helper-spy matrix proving invocation exactly once for an initially normalized plan
   correction and zero invocations for plan census, legacy census-to-correction recovery, plan
   final, branch census, branch correction, and branch final.
2. Through the production handler with a capture engine, prove a plan closure-candidate correction
   supplies all nine checklist items, labels its scope, and makes exactly one structural provider
   call. Assert the exact composed prompt contains every closure-candidate directive.
3. Prove a correction with three blocking classes retains targeted scope and an empty checklist.
4. Through production-handler capture engines, compare exact composed prompts and task JSON against
   frozen pre-change oracles for plan final, branch correction, and branch final. Prove their
   provider schemas and phase transitions are unchanged.
5. Settle a clean closure-candidate response through the canonical engine and prove the next phase
   is still `final`, then settle a final response to prove only final reaches `clear`.
6. Feed the capture engine a valid correction response containing a deterministic fresh sibling
   finding in another active class. Prove the production handler creates its governing finding,
   durable open debt and class binding, and remains in correction. The targeted-scope oracle must
   omit the broad-search directive. A closed exclusion matrix must assert every closure-candidate
   directive is absent from exact composed prompts for targeted plan correction, plan final,
   branch correction, and branch final; the plan closure-candidate prompt must contain each exactly
   once.
7. Run focused suites, then the complete test suite and `git diff --check`. The pre-change focused
   baseline is 302 passing tests across `test_plan_class_closure.py`, `test_staged_protocol.py`,
   `test_review_census.py`, and `test_prompts.py` with fixture commit signing disabled.

### Evidence-based acceptance

- Run one real-provider production-handler acceptance on a synthetic plan fixture containing an
  open class plus an adjacent sibling defect. Confirm the closure-candidate correction sees the
  full checklist and broad-sweep directive through the real Codex route, uses one structural
  attempt, and still
  requires a separate final. Do not treat one stochastic sample as proof of fewer rounds.
- Do not publish a post-change efficacy claim in this card. The acceptance claim is limited to
  correct exposure of the broader plan-correction search packet, behavioral
  settlement of a sibling finding, unchanged branch/final boundaries, and one real-route exercise.

## Documentation

Update `docs/how-it-works.md`, `docs/tool-reference.md`, and `AGENTS.md` to describe the
plan-only closure-candidate correction sweep, its threshold, the unchanged cold-final authority,
and the excluded branch and audit paths. State explicitly that prompt enrichment is intended to
reduce repeated cycles
but does not guarantee convergence in a fixed number of rounds.

## Explicit non-goals

- Removing, weakening, or combining away the independent cold final.
- Running correction and final in one public call.
- Reopening external-claim inventory or moving plan proof into implementation review.
- Persisting plan bodies, adding a new review role/schema/protocol, or changing class lifecycles.
- Treating validation retries or provider errors as successful review evidence.
- Projecting historical debt into reviewer prompts.
- Claiming causal improvement from historical observations or a single provider acceptance.
