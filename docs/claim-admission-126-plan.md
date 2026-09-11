# Issue 126: admit claim verification after repository preparation

Status: proposed; implementation and native acceptance are not complete.
Tracking: https://github.com/subvertnormality/paranoia/issues/126

## Operating model

Trusted single local operator and OS; plan, repository and fetched content are
untrusted data. No hostile local process or path race, multi-tenancy, compromised
OS or deliberately corrupted-state recovery. Ordinary edits must block/retry.
Expected work is tens to low hundreds of claims and repositories with thousands
of files. Useful results should arrive within minutes; timeout limits are generous
circuit breakers. False clearance, wrong authority and wrong evidence binding have
high impact; a truthful recoverable block is acceptable. No trading operations.

## Observed failure and bounded remedy

On the unchanged private test repository, the existing snapshot preparation took
113.15619374997914 seconds. The existing total review window gives pre-claim
preparation only the evidence scheduling slack, so the maximum evidence graph
cannot be admitted after this ordinary setup. The adapter returns exit 124 with
zero calls; its reason is then lost from the persisted claim failure channels.
Historical failures stay failed; this measurement does not prove their exact
loaded code identity or universal failure on either provider.

In `src/paranoia_local/handlers.py`, introduce
`PLAN_PREPARATION_RESERVE_SEC = 300` as the authoritative added setup allowance.
Derive `PLAN_REVIEW_TOTAL_TIMEOUT_SEC` from that allowance, the existing complete
evidence window and teardown reserve. Keep the deadline origin before snapshot
construction and the existing min(deadline minus teardown, claim start plus
evidence window) rule. Do not reset deadlines or reduce the complete graph,
role-specific caps, calls, capture reserve, structural admission or closure gates.
Setup beyond the available total budget still blocks before provider spend.

Preserve the exact locally authored admission reason in the existing structured
failure-detail channel. Include that local reason in claim debt/recovery output
without copying arbitrary provider text into an unbounded headline. Keep actual
return code, empty provider stdout, stderr and distinct bounded channel hashes.
Use the existing evidence-phase adapter mechanism; no new persistent schema,
provider calls, bypass, severity change or review profile.

Update current operational references in README.md, docs/llm-reference.md and
docs/claim_verification.md to the derived whole-review window and a client timeout
with the existing client margin. Historical accepted plans and original provider
evidence stay unchanged. Use only the existing closed compatibility-allowance
fields in the six records enumerated by `tests/test_issue115_history.py:RECORDS`:
recompute exact current-source diff hashes and truthful scope (and existing counts),
without changing original sources, prompts, provider channels, outcomes or judgments.
Run that module's immutability and actual-validator mutation controls. An allowance
records later source differences, never retroactive native acceptance of new code.
The missing historical CLI fixture is restored at its recorded temporary path with
its exact recorded package version; active review providers are unchanged.
Update AGENTS.md with this scope. Align this operator's Paranoia-only MCP timeout
with the documented recommendation and reload only this review service after
validation. Never restart trading services or reset review lineage.

## Required acceptance

First add deterministic tests in tests/test_plan_claims.py through critique_plan
for both bundled engine types. Advance a controlled monotonic clock during
snapshot construction past the old allowance but within the new allowance;
assert actual discovery admission, its unchanged requested timeout, a valid empty
external inventory and native-shaped clean structural settlement. Exercise the
exhausted budget boundary with zero discovery calls, persisted prior claim debt,
exact actionable local reason, actual exit status and distinct channel hashes.
Use a single controlled clock for deadline construction and adapter admission.
Retain the maximum full evidence graph/retry test and budget-composition test.
No production edit before the new regression is observed RED.

Run `.venv/bin/python -m pytest tests/test_plan_claims.py` after the fix and
`.venv/bin/python -m pytest tests/` before delivery. Any required failure blocks.
After code and public docs are green, run Codex CODE review on this diff under
these frozen stakes; resolve accepted findings without weakening the gates.

Native usability evidence must execute the public plan handler through a freshly
loaded Paranoia MCP server bound by the identity procedure below, with default
claim verification and the existing
Claude role/model configuration. Resume the existing private test plan lineage at its
next round, preserving all prior classes/debt. Retain actual discovery attempts,
claim status, structural status, final combined verdict, source hashes, real wall
time and model-call count. A provider/audit failure is failed acceptance, never
clearance. Native success here proves admission and execution for that input,
not universal performance. Before any PR, require native acceptance, the full
suite, implementation convergence and recorded production diff/module sizes.
No automatic merge and no reconciliation implementation before its design gate.

## Acceptance implementation identity (sole reload/acceptance procedure)

Use an acceptance-only launcher in `scripts/run_claim_admission_acceptance.py`,
covered by `tests/test_claim_admission_acceptance.py`. Reuse
`scripts/benchmark_bootstrap.py` for source-only imports and
`scripts/benchmark_review_modes.py:source_record` / `validate_source` for the
complete recursive production inventory bound to the committed repair tree.
The launcher and those harness files must also have frozen hashes, verified before
server launch and before acceptance credit. This is a validation harness, not a new
production review framework or persistence mechanism.

Launch a fresh stdio MCP subprocess with the resolved repository venv interpreter,
isolated interpreter mode and the explicit selected source root. Run the verified
bootstrap before importing any owned module, reject any preloaded `paranoia_local`
module, and prepend exactly that source directory. Validate the source record
before import. Verify every loaded package module's resolved `__file__` against its
expected inventory entry; reject other installations, bytecode files, missing or
extra production files and ordinary source edits. Repeat source and loaded-module
checks immediately before dispatch and after the handler returns, before writing
the acceptance receipt. Keep the handler and actual MCP wire path unchanged.

The client sends the frozen tool name/arguments (embed the exact plan bytes rather
than trusting a mutable plan path). The server receipt binds their digest, resolved
interpreter, selected root/revision/inventory, harness hashes, loaded module paths,
the exact returned text digest and the actual audit bytes/digest. The client checks
that receipt against its request and received response before crediting acceptance.
Retain the actual native result and audit even when acceptance checks fail; report
failure instead of supplying a success receipt. Never reframe a missing receipt as
a completed run. This dedicated fresh server is the reload for this task; unrelated
MCP connections and trading services are not stopped.

Deterministic tests must exercise the launch/import/receipt boundaries: valid source
passes, another package root refuses, ordinary source or harness edits refuse
before spend or after execution, and changed request/response/audit receipt bindings
refuse credit. Existing source validation retains the complete inventory and Git
object checks. No live reviewer is invoked by deterministic tests. Native acceptance
still requires the real default Claude discovery and structural roles on that plan.
