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
2. `plan_claims.py` strictly parses the audit, enforces source/entailment rules, reconciles
   current claims with retained evidence, and renders packets.
3. The existing plan lineage stores `claim_state` beside class state in the same atomic JSON
   file. There is no second database, CAS, journal, or transaction protocol.
4. The existing cold structural reviewer receives a concise claim inventory and independently
   checks omissions, atomicity, source authority, citation truth, and replacement entailment.
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

## Multi-round behavior

Each current claim has a server-minted ID. On a later edited plan, an exact proposition match
or a validated `prior_claim_id` preserves identity. Removed claims move to bounded diagnostic
history and leave active inventory. Every current verdict is newly parsed and validated;
previous verdicts are never copied.

Prior URLs and passages are included as candidate evidence in the next audit. The reviewer
re-opens/searches them as needed and re-entails them against the current proposition. This
makes unchanged rounds faster without treating stale evidence as truth. If the audit fails,
old packets remain available but every old active verdict is demoted to `unverified` and the
rejected output's reason, hash, and bounded excerpt become blocking debt.

## Autonomous correction contract

The paranoia reviewer is read-only; the calling coding agent is the autonomous operator.
After round 1 it consumes each `ACTIONABLE SOURCE PACKET`, validates that the cited passage
and authority justify the action, edits the plan, increments `round`, and calls again. It uses
the evidence-entailled replacement when present. Without one it removes, qualifies, or
researches the assertion rather than guessing.

There is no required human confirmation step. A calling agent must not rerun unchanged plan
text merely hoping a different sample clears it, and must not declare plan convergence from
class closure alone. It stops only when:

- the structural reviewer has no in-scope blocking finding;
- every blocking class is closed and there is no class-register debt;
- every active factual claim is supported by current qualifying evidence;
- there is no claim-audit debt; and
- the computed final line is `CONVERGENCE: NOT-BLOCKED`.

## Failure behavior

The audit JSON example contains concrete literals such as `"kind":"fact"`; alternatives
are listed outside JSON. One correction call receives the exact validation failure. If both
attempts fail, neither is applied and the bounded diagnostics remain visible. Research is
persisted before structural review so a later structural CLI failure does not force successful
evidence work to restart.

