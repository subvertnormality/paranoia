# Census execution boundary and empty consolidation

## Objective and baseline
Quicker tool calls and trustworthy convergence without reducing substantive review duties.
Maintainability for future capable LLM coding agents means explicit local contracts, cohesive
functions and focused regression tests; no model-capability guarantee is asserted.
Baseline is commit 9336ce3. This is a new bounded follow-on to issues 50 and 49, not a
claim to close either. The earlier checkpoint's CODE convergence is still pending.

## Operating model
Trusted single local operator and OS, untrusted static repository/plan/provider/web bytes.
Ordinary edits invalidate snapshot-bound evidence; no hostile same-user race, OS compromise,
multi-tenancy or corrupted-state recovery. Three concurrent census lanes; tens to low hundreds
of obligations. Review providers run through existing CLIs; external evidence uses existing
public HTTP capture and cold attestation. Wrong clear/authority/binding is high impact;
recoverable blocking is acceptable. No repository-selected execution is added.

## Scope
A1. Reproducible AST inventory of package module lines and function branch-count proxy,
including an explicit definition of the proxy (not a formal cyclomatic-complexity claim).
Keep a baseline inventory and comparison command. Target _staged_structural_review:
at least 100 fewer lines than its 748-line baseline and at least 20% fewer inclusive
branch points, without merely moving it intact. New census execution functions at most
120 lines each. Document ownership, dependencies and where a future maintainer changes
lane scheduling, validation, settlement and phase transitions.

A2. Extract the census parallel execution and aggregation into census_execution.py.
Use named typed result records for each validated lane and the complete census.
Keep schema/anchor/class validation in their current authorities and keep canonical
settlement and atomic persistence in the handler. The coordinator accepts a lane callback;
it owns ordering, all-lane completion and failure aggregation, not provider policy.
Preserve attempt sequence, every rejected payload and its own diagnostics, successful
sibling manifests, integrity member coverage, contextvars telemetry, and exact cache reuse.
No mutable global scheduler, generic workflow framework, new persisted state or extra calls.

A3. After all three expected lanes have passed existing full validation, allow deterministic
empty consolidation ONLY for a census with no lane findings, no class assessments,
no lineage classes (including closed/superseded), no durable structural debt (including
closed/advisory), no prior concessions, no legacy register debt, and no prior staged
failure, validation debt or census cache. Missing/duplicate/incomplete lanes cannot qualify.
Eligibility uses exact expected lane identities and validated coverage, not verdict prose.
Construct the sole empty census decision with empty governing findings, debt outcomes,
class actions and concession challenges, and send it through the same executable decoder,
materializer, anchor validator, canonical class dry-run and atomic settlement as provider
output. Any local rejection is a visible structured failure, never a reason to clear.
Preserve all lane prompts, schema, evidence duties, models, effort and deadlines.
The consolidator is manifest-only and may not conduct a new review; the empty case has
no findings to classify/merge, debt to adjudicate or class action to choose.
Any finding, including advisory/out-of-scope, or historical obligation retains the existing
provider consolidation and single validation correction. Correction and cold final are unchanged.
External claim failure still blocks combined plan clearance even when structural settlement
qualifies. Branch plan-contract binding and ordinary snapshot invalidation remain unchanged.

A4. Record deterministic provenance in the existing top-level audit projection/returned
diagnostic, clearly distinguished from provider attempts. Never fabricate a provider session,
raw response, return code, duration or provider attempt for skipped consolidation.
The canonical structural verdict and class/claim closure keep existing semantics; session
is null for server-derived consolidation. All actual lane attempts remain retained and
counted. Persistence failure renders STATE-UNAVAILABLE and BLOCKED, preserving diagnostics.

## Acceptance
A5. Deterministic tests through public critique_branch and critique_plan handlers:
clean qualifying census takes three provider calls instead of four and reaches the identical
canonical substantive successor as baseline; a failed initial lane plus successful correction
may qualify only after validation and retains the rejected payload; failure/invalid coverage,
missing/duplicate lanes, every excluded history category and every severity retain the
existing fail-closed or model route. Exercise ambiguous persistence, contract binding and
claim-blocked combined output. Compare canonical successors and rendered closure fields;
exclude honest provenance/call-count/session differences explicitly.
Replay nonempty census -> repaired correction -> independent cold final, including a repair
that leaves a sibling violation, to establish unchanged call sequence and closure requirements.
Preserve exact lane prompts in controlled baseline/candidate comparison.
Test parallel failure fan-in with multiple rejected lanes and successful sibling evidence,
plus contextvars telemetry and cache reuse. Run full regression and existing mutation checks.
Historical live acceptance bindings remain historical; changed bytes must be acknowledged,
not relabeled as provider validation of this change.

A6. Before claiming delivery, run real providers through production branch entry points on
clean and defective fixtures for both existing supported providers, with fixed source revisions,
model/effort, stakes, fixture/oracle and alternating baseline/candidate order. At least two
pairs per provider for the clean case and one per provider for the defective control.
Use the benchmark's shared admission counter with a new explicit maximum of 96 provider
calls for this acceptance (PLAN/CODE design reviews are separately recorded).
Retain every attempt and failure; never rerun-away a failure. Compare complete tool wall time,
calls, retries, correct outcomes and canonical settlement. Report sample size and variance;
do not assert guaranteed live speedup. A deterministic call reduction with no observed
wall-time improvement must be reported as such. Use deterministic plan-handler acceptance
for claim gates rather than reopening plan review as an implementation acceptance loop.

A7. Review this design once as PLAN, address accepted design findings, then keep convergence
on CODE against this exact contract after implementation. Update README and AGENTS before
review. Use the same frozen stakes and architecture checkpoint rule. No PR/merge/install
or GitHub issue closure is included. Commit coherent extraction and optimization separately.
If equivalence fails or the clean case contains a genuine remaining model judgement,
retain the extraction if useful and defer the optimization rather than weaken outcomes.

## Explicit exclusions and follow-on
No faster/weaker model substitution, shortened review budget, removal of a substantive lane,
looser evidence validation, stale verdict caching, provider transport replacement, broad
parser rewrite or unrelated handler extraction. No claim of improved query/rebut/arbitration
latency. Representative multi-round human/LLM fix-effort evaluation remains issue 49 follow-on;
this bounded empty-census case removes mechanically redundant work on already-clean calls.

## PLAN review clarifications (binding)
B1. A3 concerns the authoritative incoming state for this invocation, not lifetime history.
Capture an immutable eligibility fact after authoritative load/validation in closure.prepare,
before normalization, sweeps or provisional mutations. Inspect all loaded classes, lineage
register debt and review-state debt, format_debt, validation_debt, staged_failure and census_cache.
Unknown/unvalidated input cannot qualify. Existing successful settlement may naturally remove
old failure metadata; do not reconstruct erased history or add persistence. Also check normalized
current obligations at use. Tests cover changed snapshots, stakes changes and an intervening
successful settlement through both public handlers.

B2. Use one server-empty-census discriminator in a private Review subtype and a shared conversion
at the two staged public-handler reporting boundaries. The existing top-level audit gains
review_origin=server-empty-census only on this route. Shared _footer labels server consolidation
and the actual lane engine, supplies no rebut session and does not label local failures as provider
exit failures. Shared _log records session_ref, returncode, usage, duration_ms, provider_duration_ms,
raw and process stderr as null on this route; actual provider observations live exclusively in
the unchanged attempt ledger. A failed local validator retains its structured role/kind/message
and successful lane diagnostics, with the same discriminator. Ambiguous persistence preserves it
and remains BLOCKED/STATE-UNAVAILABLE. No origin field is added to durable lineage state.
Tests independently inspect both handlers' returned text, ledger, audit, and durable successor
for clean/corrected-lane success, local rejection and persistence ambiguity. All must pass.

B3. Live acceptance is qualified only if all four clean pairs (two per provider) clear durably,
the candidate audit reports server-empty-census with exactly three initial lane calls (plus
any honestly retained repair), and baseline uses provider consolidation. Both defective pairs
must use provider consolidation and retain a durable blocking finding whose repository/app.py
evidence and concrete arithmetic defect agree with the frozen oracle. Any operational failure,
missing qualification or budget exhaustion blocks optimization delivery; preserve trials and
report the incomplete evidence. A new corrected acceptance experiment may be explicitly frozen
only for a demonstrated harness defect; it cannot erase provider outcomes. Record wall time
and uncertainty without inferring stronger quality conclusions from this small fixture corpus.

B4. Update docs/how-it-works.md and docs/llm-reference.md as well as README and AGENTS.
One current architecture document owns the eligibility rule; other current descriptions link
to it. Historical plans and run artifacts remain historical. Inventory and maintenance targets
apply to this cohesive extraction, not to a claim that all large modules have been resolved.
