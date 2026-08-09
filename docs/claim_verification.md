# Plan claim verification

## Purpose and stakes

Plan verification exists to stop a structurally persuasive plan from converging on a
false premise. Under the supported operating model, paranoia-local is a single-user local
MCP on a trusted OS. Plan/repository text and fetched pages are untrusted data, but no
hostile local process races the run. A false `NOT-BLOCKED`, authority misclassification,
or evidence bound to the wrong proposition is high impact. A recoverable blocked run is
acceptable. Expected work is tens to low hundreds of load-bearing facts and evidence should
be useful within minutes. Formal natural-language completeness proofs, multi-tenant
hardening, hostile same-user filesystem races, and recovery from deliberately corrupted
state are outside this contract.

The priorities are: accurate claim verdicts, reliable ordinary operation, useful latency,
maintainable architecture, then security hardening within the stated model.

## Architecture

Verification adds one focused module to the existing plan-review path:

1. The existing reviewer engine runs a factual audit with repository read access and its
   own built-in web search. No search endpoint or provider abstraction exists.
2. `plan_claims.py` strictly parses the audit, enforces source/entailment rules, freezes
   exact unchanged supported packets after round 1, targets later audits at the factual edit
   cone and unresolved claims, and renders packets.
3. The existing plan lineage stores `claim_state` beside class state in the same atomic JSON
   file. There is no second database, CAS, journal, or transaction protocol.
4. The existing cold structural reviewer receives a concise claim inventory and independently
   checks omissions, atomicity, source authority, citation truth, and replacement entailment.
   Its packet includes every URL, authority basis, location, exact passage, and relation; a
   model-supplied `primary` label is not accepted as the only review of authority.
5. One final computed verdict combines claim closure and class closure.

The active ceiling is 500 factual claims and 20 evidence records per claim. These are
pathology/corruption guards, not work-pagination limits: nothing beyond them is silently
dropped or called verified. Exceeding one produces visible audit debt and a blocked verdict.

## What becomes a claim

Retain only a load-bearing factual proposition whose truth could change feasibility,
ordering, a dependency, rationale, mapping, implementation premise, or acceptance result.
Scan headings, prose, lists, and tables; include necessary implied premises; split compound
assertions into atomic propositions.

Do not retain decisions, selected policies, permissions, requirements, definitions,
intentions, instructions, preferences, pure forecasts, or incidental facts. They are omitted
from active inventory immediately, not carried forever as `not-applicable` rows. If a statement
mixes a decision with a factual rationale, verify the rationale only.

## Evidence and authority

Repository facts require a `repo://path#Lx-Ly` location and an exact code passage. External
facts require a canonical absolute URL, publisher, title, precise section/table/page, exact
passage, and source class.

Primary and authoritative sources can govern a verdict: first-party documentation and
records, standards, legislation/regulators, government data, and original papers/datasets.
Secondary sources can corroborate or locate primary evidence. UGC—including Reddit, forums,
Stack Overflow, social media, wikis, and community publishing—can supply leads or conflict
signals but cannot support or refute closure. Known UGC hosts are downgraded by server code
even when model output calls them primary.

Evidence is claim-specific. A passage qualifies only if it entails the exact proposition.
A refuting passage can mark old wording refuted. It cannot authorize a replacement unless an
authoritative passage separately entails the complete replacement wording.
Unsupported optional replacement wording is removed during validation while the valid
refutation and source packet are retained. It does not invalidate unrelated claims in the
same audit response.
Authority, scope, and entailment mistakes are also localized: the questionable source
is retained as context, the affected claim is server-demoted to blocking `unverified`,
and independently valid claims in the response remain usable. Structural corruption
such as malformed JSON still fails the audit closed. A non-verbatim anchor gets the
single correction retry; if it remains invalid, that item becomes explicit blocking
debt while valid retry packets and dispositions persist for the next round.

## Multi-round behavior

Round 1 is exhaustive: it scans the whole plan, establishes the atomic inventory, and gathers
authoritative packets. Each claim receives a server-minted ID. On later rounds, an exact
unchanged claim that is already `supported` is frozen with that packet and omitted from the
claim-model prompt. External evidence remains the captured authoritative passage for the
convergence lineage. Repository evidence is frozen only while at least one qualifying quoted
passage is still present in the current worktree. Edited propositions require a new full packet
and inherit no verdict.

The later-round verifier receives a unified diff with context, every added or edited factual
assertion, and every retained `refuted` or `unverified` claim. It follows dependencies from that
edit cone when needed but does not rescan settled prose or reopen settled URLs. If the plan is
byte-identical and all active claims are supported, the factual phase makes zero model calls.
This optimization is deliberately limited to claim verification: every convergence round still
runs the existing broad, cold structural FATAL/MAJOR review over the full plan and repository.
That reviewer receives the complete active claim register and independently checks omitted
facts, atomicity, authority, entailment, and structural correctness.

A previously active claim cannot disappear merely because a later model omits it. Identity
is reused only for the exact same proposition; model-supplied prior IDs cannot bind edited
wording. Otherwise the audit must explicitly classify the predecessor `removed`, which is
accepted only after its exact old anchor has left the plan. There is no model-only
`nonfactual` escape: edit away the old factual wording. Missing or invalid dispositions keep
the prior packet active as `unverified`; this blocks rather than converting sampling variance
into clearance. On each initial audit and correction retry, the server identifies prior exact
anchors that are absent from the current plan and presents them as removal candidates. This
avoids rediscovering stale packets across rounds, but does not auto-retire them: the reviewer
must validate and return an explicit `removed` disposition. The cold structural reviewer sees
every current-round retirement.

Prior URLs and passages for unresolved or edited assertions are included as candidate evidence
in the targeted audit. Every still-present unresolved ID is mechanically required. A missing ID
rejects the audit and is named in the one bounded correction prompt before any state commit,
rather than becoming stochastic next-round churn. If both attempts fail, the rejected output's
reason, hash, and bounded excerpt become blocking debt; targeted unresolved claims remain
blocking, but frozen supported claims keep their verdicts. One malformed successor packet can
therefore never invalidate hundreds of unrelated settled claims.

## Autonomous correction contract

The paranoia reviewer is read-only; the calling coding agent is the autonomous operator.
After round 1 it consumes each `ACTIONABLE SOURCE PACKET`, validates that the cited passage
and authority justify the action, edits the plan, increments `round`, and calls again. It uses
the evidence-entailled replacement when present. Without one it removes, qualifies, or
researches the assertion rather than guessing.

Negative-existence and chronology corrections require one extra completeness check. A missing
path or a named file's first-add commit establishes only that path-level fact; it does not entail
that no equivalent executor brief, manifest, issue record, tag, or retained Git object existed.
The caller inspects alternative authoritative surfaces at the relevant revision, separates
source existence from declared process/profile, requirement conformance, and current
reusability, and applies the finding across every affected sibling case before another round.
This prevents a credible but incomplete packet from producing one newly discovered omission per
round.

There is no required human confirmation step. A calling agent must not rerun unchanged plan
text merely hoping a different sample clears it, and must not declare plan convergence from
class closure alone. It stops only when:

- the structural reviewer has no in-scope blocking finding;
- every blocking class is closed and there is no class-register debt;
- every active factual claim is supported by a frozen exact packet or current qualifying
  evidence;
- there is no claim-audit debt; and
- the computed final line is `CONVERGENCE: NOT-BLOCKED`.

This governing computed line exists only when class closure is enabled. A structural-only
one-shot review still returns claim packets and reviewer prose, but deliberately emits no
computed convergence verdict because its free-text FATAL/MAJOR findings are not parsed.

## Failure behavior

The audit JSON example contains concrete literals such as `"kind":"fact"`; alternatives
are listed outside JSON. One correction call receives the exact validation failure. If both
attempts fail, neither attempted edit-cone verdict is applied and the bounded diagnostics
remain visible; frozen supported packets remain usable. Research is persisted before
structural review so a later structural CLI failure does not force successful evidence work
to restart.
