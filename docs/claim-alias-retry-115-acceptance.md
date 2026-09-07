# Issue 115 acceptance

The prior-disposition authoring fix preserves the parser's accepted language while
making canonical fields and collision repair explicit. Production diff against
f4e810911e8a60845ab797f913a252d4ea38039f: 22 additions and one deletion, all in
src/paranoia_local/plan_claims.py. That module has 1,889 lines; the largest package
modules remain handlers.py (5,297) and arbitrate_handler.py (3,069), unchanged.

## Deterministic evidence

Source checkpoint e9732ea passed 2,177 tests in 196.17 seconds, including all 13
issue-115 cases and the historical metadata invariants and mutation controls.
The real ClaudeEngine/public critique_plan adapter tests inject only provider
responses: a dual-alias rejection repairs on the existing resumed session; a
repeated invalid reply retains the prior claim and ordered blocking audit debt.
No third discovery or source capture is admitted. All four legal single-name
combinations still parse; equal and conflicting collisions still reject.

Only the six historical records listed in the accepted plan received allowance
metadata updates. Original source identities, prompts, channels and outcomes are
unchanged. The historical restatement prompt projection removes only the exact
new shared instruction plus newline, retaining its other existing projections.

## Native evidence

[Retained native evidence](claim-alias-retry-115-native-evidence.tar.gz) contains
95 files, 89,538 compressed bytes. SHA-256:
e3ccc14f3877d6a9e486c24ed778f1445f115053c9045aa5ac3afaedd080c8bc.
Every archive member was compared byte-for-byte with its original run file.

The source-bound public critique_plan run used the complete committed production
inventory at e9732ea, Claude CLI 2.1.258, requested model opus and high effort,
verification enabled and its required native search capability available.
The main provider model resolved to claude-opus-5; native provider telemetry also
reports a small claude-haiku-4-5-20251001 auxiliary charge. Provider-reported total
cost is USD 0.934686, not a claim about the subscription's incremental bill.

The isolated fixture contained one absent synthetic unverified prior claim and
no current external assertion. The initial discovery emitted only claim_id,
disposition and reason. The original claim retired durably; no capture occurred.
The native three census lanes and consolidation completed normally. Overall
convergence was NOT-BLOCKED: five calls, zero retries, 79,316 ms end to end.
The acceptance ceiling was twelve attempts; no extra structural final was forced.

This proves native prevention/usability for the fixture, not a naturally observed
failed-then-repaired model exchange or a general performance improvement. The
deterministic public adapter regression owns the exact reported collision/retry.
The first setup attempt was rejected before provider spend because the driver
set web_search false with verification true. Its original zero-call result is
retained separately; the corrected setup has a new directory and driver.

Prompts, schemas, process channels, local durations, provider usage, audit, durable
state, fixture and drivers are retained. This work does not close issues 49 or 50.
Codex-only CODE convergence is the remaining delivery gate.
