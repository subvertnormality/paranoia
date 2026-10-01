# Issue 139: verified LFS checkout acceptance

The old installed beta `a549b24` rejected a real Git LFS fixture with clean Git
status and a 65,536-byte object matching its committed pointer's size/SHA-256.
The bounded fix is in [the accepted contract](lfs-proposal-cleanliness-139-plan.md).
It recognizes canonical extension-free v1 pointers without filter execution, while
retaining exact committed patch preimages and all existing tree/mode checks.
Unsupported versions/extensions and arbitrary filter equivalence remain excluded.

Native PLAN rounds 1–2 retained two minor documentation/failure-phase findings and
then reached strongest-model cold-final `NOT-BLOCKED`. Actual measured wall times
were 148.23 and 81.16 seconds; five provider attempts, no validation retry.
Claim verification was explicitly disabled for this local implementation design.

The [native LFS record](lfs_proposal_acceptance_2026-10-01.json) binds source
`060a70a` and the exact runner/package inventory. Git LFS 3.8.0 created a clean
expanded object and committed pointer alongside the disclosed arithmetic fixture.
The public `critique_branch` handler returned PROPOSED/CURRENT; the caller inspected
the exact allowlisted diff, checked/applied it, ran the arithmetic checks and sent
the exact proposal receipt with applied disposition. Correction and cold final
reached `NOT-BLOCKED`, with unchanged LFS object bytes checked before every round.
All actual returned text, audits, receipt and durable lineage are retained. Seven
native attempts (four census/consolidation, one proposal, correction, final) completed
without validation retries. These use the strongest Codex route; they do not qualify
the beta's outstanding complete both-provider gate or establish cost/quality savings.
The runner did not retain a whole-lifecycle monotonic timer, so that elapsed time is
unknown; do not sum concurrent attempt durations as total wall time.

The initial focused run passed 235 tests; three additional read/object and SHA-256
Git checks plus current native replay passed in the subsequent 35-test run. New
coverage verifies clean expanded/raw pointers, real LFS status, dirty content/size,
staged/untracked/mode changes, unsupported pointers/attributes, bounded reads,
sparse files, initialized submodules, filter sentinels, zero proposal spend on dirty
or failed admission, post-response STALE, and exact edited-file preimages.

CODE round 1 reviewed the committed implementation against the exact accepted plan
digest `f4998a3c3377566ce91412be57f3963ff2d33b6c6c8371d08b1b10d07d4c848b`.
It correctly blocked on the absent retained native record/current-source replay at
that snapshot. Five attempts included one repaired out-of-range evidence citation;
wall time was 580.74 seconds. Its failed snapshot remains failed evidence. The new
record/replay and this documentation address that debt; delivery still requires
correction and a strongest-model cold final on the resulting CODE snapshot.

The broad pre-metadata-refresh suite recorded 2,655 passes and 34 failures, mostly
existing historical allowances made stale by the new handler/docs bytes. Only
existing allowance hash/scope metadata in nine historical records was refreshed;
no inventory entry, provider exchange, acceptance result or historical count changed.
The authoritative-capture test now derives today's line count from its hash-bound
Git diff instead of treating immutable historical counts as today's measurement.
The focused history/LFS/replay run then had 63 passes and the same five pre-existing
plan-restatement replay failures; those remain failed historical evidence.

Implementation at `060a70a`: 9 files, 379 additions/12 deletions. Production changes
are the 61-line `proposal_checkout.py` plus a 19-line handler diff; the inherited
handler remains the largest module at 6,725 lines. Remaining changes bind acceptance,
public documentation, regression tests and historical metadata; no new persistence,
provider call, LFS fetch, filter execution or review-authority path is introduced.
