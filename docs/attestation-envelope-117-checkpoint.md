# Issue 117 implementation checkpoint

Status: not merge-qualified. Native fixture continuation approval is pending.

The production change shares one complete cold-attestation output contract between the
initial prompt and its single same-session correction. It prohibits extra fields,
competing envelopes and appended repairs, and distinguishes independent authority and
entailment judgments. Parser, capture, binding, role/call topology, timeouts, retry count
and canonical settlement are unchanged. Production diff: handlers.py, 19 additions and
9 deletions. Ordinary and expanded preflight still uses the exact invocation renderers.

Codex PLAN convergence cleared at round 6, session
01a07cf2-ebfa-70c3-ad9e-76a7864e3662. The late source-loading class was closed by reusing
the existing benchmark source-only bootstrap and adding actual-entry contamination controls.

At committed implementation f743559, all 2,207 tests passed in 228.29 seconds.
The public Claude adapter tests inject process-shaped JSON only at subprocess execution,
with a deterministic server-capture fixture. They exercise extra envelope/row keys,
competing envelopes, conflicting rows, valid correction, repeated rejection, and a valid
negative entailment judgment. Both actual prompts, exact size boundaries, same-session
resume, attempt diagnostics and durable claim outcomes are checked. These are scripted
regressions, not native provider judgments.

The native campaign used f743559, Claude opus/high (resolved claude-opus-5, with auxiliary
Haiku usage), real discovery, server capture, binding and cold attestation. Discovery's
initial response had trailing text; its built-in correction succeeded. Both captured
sources were cold-attested in one 10,349 ms call without an attestation retry. One external
claim reloaded durably as supported. Eight attempts consumed 235,056 ms through the
qualification failure. Provider-reported cost was USD 1.838517; this is not a subscription
billing claim.

The campaign did not qualify for delivery. The initial qualifier incorrectly required an
initial discovery success rather than accepting its successful validation retry. That
check is now corrected, with a regression using the retained real ledger and terminal
failure mutations. Separately, the fixture plan omitted an implementation target despite
the repository asking it to record the release date. Structural review correctly retained
one blocking class/debt. The combined result remains BLOCKED. The structural-clear gate
has not been removed, and no provider call has been repeated.

The current focused suite passes 31 tests, including the recorded-retry regression.
Approval was requested to repair the fixture and complete correction/cold final within
the original twelve-call ceiling. CODE convergence and main/active-branch delivery remain
outstanding. No general speedup, native structural clearance or issue closure is claimed.

[Original native evidence](attestation-envelope-117-native-evidence.tar.gz):
63 files, 96,277 bytes, SHA-256
471a0b5407614ba1c170ba991d8cfac02b0e0b5af9958064e2eb4ea5af615e56.
All archive members were compared byte-for-byte with the original campaign files. The
archive preserves the failed qualification, all native channels/prompts, loaded-source
observations, audit, state and blocked result without alteration.

