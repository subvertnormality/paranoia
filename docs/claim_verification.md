# Plan claim verification

## Large-plan discovery timeout acceptance

The issue-58 correction gives the initial whole-plan discovery call and its one
same-session validation correction a 900-second circuit breaker while retaining the
300-second limit for later binding and cold-attestation calls. The retained
[`claim_discovery_timeout_acceptance_2026-08-22.json`](claim_discovery_timeout_acceptance_2026-08-22.json)
record exercises the public `critique_plan` handler with the exact 94,110-byte historical
plan that repeatedly failed at the former boundary. Its claim phase took 710,810 ms,
completed four model attempts without an execution timeout, persisted 14 claim outcomes,
and continued into the structural census. The artifact deliberately retains the final
`CONVERGENCE: BLOCKED`: seven claims remained unverified, and the historical plan acquired
structural debt. It proves recovery of this concrete timeout failure, not universal
provider latency or correctness of that plan.
The runner starts with empty audit and lineage directories, binds the public handler through
`PARANOIA_STATE_ROOT`, and verifies that fresh and resumed evidence roles use the exact recorded
Codex executable. Its attempt durations are local monotonic measurements; a provider duration is
retained separately when supplied.

## Purpose and stakes

Plan verification stops a structurally persuasive plan from converging on an unsupported
external premise. The supported operating model is a single-user local MCP on a trusted OS.
Incorrect claim closure, weak authority presented as authoritative, or evidence bound to the
wrong proposition is high impact; a recoverable blocked run is acceptable. Formal
natural-language completeness proofs, multi-tenant hardening, hostile same-user races, and
recovery from deliberately corrupted state are outside the contract.

The priorities are accurate verdicts, useful ordinary-run latency, autonomous correction, a
small maintainable architecture, and then security hardening within that model.

## Mechanical scope boundary

The evidence register covers load-bearing propositions about the external world. A proposition
is eligible only when its truth or authority could change feasibility, architecture, ordering,
dependencies, rationale, or acceptance, and it has exactly one of these kinds:

- `fact`: an objective external-world state, event, quantity, identity, or history;
- `design_principle`: a requirement, constraint, or recommended principle issued by the
  external standard, regulator, protocol, platform, or vendor that governs the plan;
- `behavior`: documented or observable behavior promised by an external API, dependency,
  platform, protocol, service, or runtime on which the plan relies.

All three use `scope: "external"` and require authoritative web evidence. Design principles and
behaviors are not excluded merely because they are normative or forward-looking: if the plan
claims that an external authority requires a design or an external system behaves a certain
way, that external proposition is verifiable and belongs here.

The following are mechanically ineligible: repository state, code paths, function behavior in
the project, internal history, implementation conformance, internal function-to-function
bridges, local decisions, project-authored principles, permissions, intentions, instructions,
preferences, forecasts, and incidental observations. They remain fully reviewable by the
ordinary structural/code review and tests; they simply do not enter the persistent web-evidence
lifecycle. Calling an internal preference a “design principle” does not make it external.

The parser rejects every fresh row whose scope is not `external`, so a model cannot silently
discard an eligible external premise by mislabeling it `repository`; the bounded correction and
debt path governs that error. Existing version-1 repository claims are different: normalization
mechanically moves those already-persisted rows to retired diagnostic history, where they stop
consuming active inventory, prompts, or convergence. This server-owned distinction prevents
both old repository churn and new false-empty clearance.

The replaced, versionless claim-array schema cannot be safely guessed into this register. If it
contains active predecessor rows or debt, normalization preserves their IDs and statuses in
explicit blocking migration debt, omits a reusable plan snapshot, and forces one exhaustive
external-claim audit. A successful audit then writes the current versioned schema. Empty legacy
inventory needs no migration work. This prevents an upgrade from treating unknown old rows as
an empty, verified register.

## Architecture

1. The selected reviewer CLI scans the plan and uses Codex live search or Claude `WebSearch`
   only to discover candidate public URLs. Claude `WebFetch` is not enabled. There is no search
   endpoint, API key, plugin, or provider abstraction.
2. Before any download, the server validates the complete retained-claim inventory. Its one
   bounded correction therefore repairs omissions while discovery search is still available;
   only the corrected complete inventory proceeds to capture.
3. The server downloads each candidate directly under bounded HTTP(S), redirect, response-size,
   and extracted-text limits, then extracts main text with Trafilatura. Responses remain capped at
   5,000,000 bytes; complete extracted text through 1,000,000 characters is admitted. Plan
   binding preserves complete-source context: a structurally governing primary or authoritative
   capture may use one dedicated expanded packet when its exact rendered prompt fits 685,000
   characters, with eligibility recomputed from the final URL. Its complete capture accompanies
   the selected passage into a separately size-checked cold attestation prompt. Admission reserves
   the worst-case bounded binding correction and attestation output envelopes. Repeated
   captures with the same final URL and content/text digests appear once per serialized binding
   prompt or batch and later rows reference that exact capture. If distinct arbitration captures
   exceed its single 400,000-character binding prompt, the largest capture groups are
   deterministically made unusable with a server-owned binding-budget reason until the prompt
   fits; other research continues. The same reviewer session
   is resumed with web and repository access disabled and may bind exact passages only from those
   captures. Search snippets, provider summaries, and provider-fetched page bodies never count.
   The initial attributable request carries explicit accept/language/identity-encoding headers.
   Only HTTP 403 receives one browser-compatible same-URL retry, using a fresh five-redirect
   handler but the same absolute deadline and public-address/final-URL checks. Persistent 403
   remains unusable and retains its final URL, numeric status, bounded error, and retry fact; no
   authentication, cookies, headless browser, CAPTCHA/paywall bypass, or mirror is attempted.
4. A fresh tool-free attester receives only each atomic proposition, declared publisher and
   authority basis, capture metadata, relation, location, and exact passage. A source governs
   only when the attester independently accepts publisher authority and passage entailment. A
   proposed replacement is attested against the exact replacement proposition separately from
   the refuted claim; negative replacement attestation removes only the proposed wording.
5. `plan_claims.py` parses the resulting audit, enforces scope, authority, and entailment, freezes exact
   unchanged supported packets after round 1, targets later work at the external edit cone and
   unresolved claims, and renders actionable packets.
6. Claim state and structural-class state share the existing atomic lineage JSON. There is no
   second database, CAS protocol, or journal.
7. The cold structural reviewer receives the evidence register and an inert raw-tree repository
   materialization, with live web and Git-helper execution unavailable. It is explicitly forbidden
   from demanding claim packets for repository mechanics or “missing atomic bridges.” It performs
   a broad census on a new snapshot, targeted correction reviews over durable debt and repair
   effects, and one mandatory broad cold final regression after that debt closes.
8. The computed verdict combines external-claim closure and structural-class closure.

The active inventory ceiling is 500 external claims and 20 evidence records per claim. The
composed execution budget additionally allows at most 200 source captures and five binding
batches of 400,000 characters in one audit. These are pathology/corruption guards, not
evidence-quality targets. A single authoritative source may flex from an ordinary batch to one
dedicated expanded packet. They cover ordinary large plans while preventing the multiplicative maxima
from turning into hours of model/network work. Exceeding one creates visible audit debt and
blocks; nothing beyond a ceiling is silently discarded or called verified.

Whole-plan discovery and its same-session correction each have a 900-second cap. Captured-text
binding and cold-attestation calls retain the 300-second cap; each locally invalid response allows
at most one same-session correction. Cold attestation is
packed by its exact rendered initial and correction prompts into at most five batches, rather than
assuming every accepted passage fits one call. The complete evidence phase has an 8,160-second
monotonic circuit breaker and at most 22 model calls: discovery + five binding + five attestation
calls, with one correction reserved for every initial call. Before discovery spend, admission
reserves that entire role-specific graph plus 300 seconds for capture/bounded pre-binding
processing and 60 seconds of scheduling slack. The capture pool and exact local packing share an
enforced monotonic 300-second deadline; exhausting it blocks before the first binding call. The
handler also checks both remaining calls and two full role-specific windows before each initial
invocation. The retained
acceptance record reports the measured live latency for each 627,000-character Codex and Claude
packet. These remain generous circuit breakers, not review-quality budgets; an admitted call may
use its full time and context to establish authoritative evidence.
Captured sources are downloaded with up to 16 workers under the same monotonic deadline and
per-source wall-clock bounds, then bound in deterministic indexed batches in the same corrected
discovery session. Exact 5,000,000-byte and 1,000,000-character boundaries are admitted; the first
unit above either is rejected. Numbering, metadata, JSON escaping, and the full instruction
envelope count against either the ordinary 400,000-character prompt or the dedicated
685,000-character governing-source prompt. Arbitration degrades the largest distinct capture
groups per-source when its aggregate would overflow; the plan path retains its five deterministic
batches. An aggregate sixth plan batch, an expired capture, or a failed batch
becomes visible blocking state rather than silently truncating the inventory.
For binding and cold attestation, that aggregate rejection is global: no prefix is settled or
made eligible for later freezing as a way to paginate the inventory across rounds.
If a row is ineligible for expansion or its complete expanded prompt cannot fit, only that capture
becomes unusable with the bounded server-owned binding-budget reason; it cannot abort unrelated
claim captures. Unavailable captures bypass model binding and retain their known server-owned
failure rather than becoming model-omission provenance. A failed dedicated expanded call is also
source-local and retains its attempt diagnostics; unrelated batches continue.
Every source outcome carries a closed server-owned `capture_provenance` row with its requested
location, nullable effective HTTP(S) final URL, explicit nullable status, content type, both capture
digests, fallback fact, and bounded error. A null final URL preserves non-web context as an
uncaptured outcome rather than inventing a web capture. Dedicated binding or attestation failure
preserves that immutable provenance, records a negative attestation, and continues unrelated
batches.

The complete verified plan call has an 8,280-second deadline, leaving a 120-second teardown
reserve within the documented 8,400-second MCP client timeout. After evidence state is persisted,
the cold structural review starts only when its current 4,320-second census or 3,120-second
follow-up reserve still fits. If it does not,
the round returns blocked and the next invocation reuses frozen supported claims rather than
repeating research. A malformed class register gets one 600-second retry only when that cap also
fits the same deadline.

Claim debt, including a discovery timeout, blocks the combined plan verdict without changing the
staged structural phase. The response reports claim closure and structural convergence separately,
then emits one governing combined `CONVERGENCE` line. A clear structural census therefore remains
clear rather than being mislabeled as structural correction merely because evidence tooling failed.
The upgrade path also recognizes the exact same-snapshot predecessor shape left by the old bug:
`correction` with no blocking structural debt, blocking/unbound class, or staged failure. It
persists `clear` without a correction or final provider call while retaining claim debt unchanged.

## Evidence and authority

The retained live acceptance for the long-authoritative-source path is
`docs/authoritative_capture_acceptance_2026-08-20.json`. It records the official 590,177-character
Spotify SEC filing, exact 627k live prompts, the 682,351-character worst-case production preflight,
successful Codex and Claude routes, a public two-claim `critique_plan` lifecycle with durable
reload, bounded format retries, cold verdicts, digests, elapsed time, and full-suite
result.

Every source needs a canonical absolute URL, publisher, title, precise section/table/page,
exact passage reproduced in the server capture, evidence relation, and an explanation of why
that publisher governs the exact proposition. The passage must entail the atomic proposition
while preserving actor, event, date, modality, scope, and chronology. Evidence of an underlying
condition does not prove that a named external report occurred. A provider's source label is a
proposal, not an authority verdict; known UGC is mechanically demoted and the cold attester makes
the final claim-specific authority and entailment judgements.

The final redirect URL, rather than the discovery URL, governs UGC classification,
self-citation rejection, source eligibility, packet identity, and the URL persisted in the
claim register. A redirect therefore cannot promote a forum or the plan under review into
authoritative evidence.

Only canonical `https://` or `http://` locations with a host can govern a verdict. Repository,
file, and custom-scheme locations may be retained as context but can never count as primary or
authoritative web evidence. When the plan is a repository file and its origin remote is known,
the plan's own canonical blob/raw HTTP(S) URL is also mechanically demoted to context: publishing
the assertion does not make it evidence for itself.

Primary and authoritative sources can govern a verdict: first-party documentation and records,
standards, legislation/regulators, government data, and original papers/datasets. Secondary
sources may corroborate or locate primary evidence. UGC—including Reddit, forums, Stack
Overflow, social media, wikis, and community publishing—can provide leads or conflicts but can
never support or refute closure. Known UGC hosts are downgraded in server code even if the model
labels them `primary`.

Evidence is claim-specific. A refuting passage can refute old wording, but it cannot authorize
a replacement unless authoritative evidence separately entails the complete replacement.
Unsupported replacement text is removed while the valid refutation packet is retained.
Authority or entailment mistakes are localized: the source remains context, the affected claim
becomes blocking `unverified`, and unrelated valid packets remain usable.

## Multi-round behavior

Round 1 scans the complete plan for all three eligible external kinds and gathers authoritative
packets. It splits compound external assertions into atomic propositions, but does not atomize
an internal design into repository-mechanical hops. Each claim receives a server-owned ID.

Later rounds freeze every exact unchanged `supported` claim with its captured packet. “Unchanged”
requires the anchor to remain in one unique normalized Markdown assertion block with the same
structured heading levels and list-ancestor chain, not merely to occur as a substring;
quotation, code, negation, relocation, parent-list changes, or surrounding assertion edits force
re-verification while harmless line wrapping remains stable. The
verifier receives only added or edited eligible wording, retained `refuted` or `unverified`
claims, and removal candidates. An unchanged, fully supported register causes no evidence-model
call or web search. Structural review remains independent: the initial census and mandatory final
regression are broad and cold, while intervening correction rounds target durable structural debt,
the claimed repairs, and their transitive effects.

An edited proposition inherits no verdict. Every unresolved or otherwise non-freezable claim,
including an exact retained refutation, must return as a complete current server-captured and
cold-attested evidence packet; compact assessments cannot cross the capture boundary.
The register persists the final URL, captured-text SHA-256, relation, and both cold-attestation
decisions. Supported legacy packets without this provenance re-enter research once instead of
being silently frozen after an upgrade.
A prior claim cannot disappear through model omission or ID reuse. Its old anchor must leave the
plan and receive an explicit `removed` disposition. If the bounded correction retry still omits
a required ID, valid packets are applied and only that claim remains `unverified`.

## Autonomous correction contract

The paranoia reviewer is read-only; the calling coding agent is the autonomous operator:

1. call `critique_plan` with a stable lineage, explicit proportionate stakes, and `round: 1`;
2. inspect each `ACTIONABLE SOURCE PACKET` and confirm that its authority and exact passage
   justify the action;
3. edit the plan using the evidence-entailed replacement, or remove/qualify/research the claim
   when no replacement is proven;
4. increment `round` and rerun only after making the correction;
5. stop only when the structural review has no in-scope blocker, class debt is clear, every
   active external claim is supported, claim debt is clear, and the computed line is
   `CONVERGENCE: NOT-BLOCKED`.

No human confirmation is required. Rerunning unchanged text in hope of reviewer variance is not
a correction. The exact passage and location are returned specifically so an autonomous caller
can apply a justified correction before the next round.

## Failure behavior

Discovery and audit JSON use concrete literals, never pseudo-enums. Discovery receives at most one
same-session correction. Capture is server-controlled. Binding then resumes that exact discovery
session with browsing disabled and likewise receives at most one correction; a corrected response
must pass the same capture and attestation gates as the first. If correction still fails,
diagnostics include the reason, output hash, and bounded excerpt. Frozen supported packets remain
usable and successful evidence work is persisted before structural review, so a later structural
failure does not restart research.

Retrieval, captured-text binding, and cold-attestation failures remain distinct server-owned
phases through reconciliation and rendering, including when only some source rows fail or one
claim contains failures from multiple phases. Each affected phase names its own retry. None of
these processing failures alone is evidence to remove, weaken, or otherwise edit the proposition;
wording changes require authoritative evidence that refutes or fails to entail it. Ordinary
terminal provider failures retain the binding or attestation phase in durable claim debt and
render that same phase's retry action; phase fidelity is not limited to expanded source-local
failures.

## Recorded real acceptance

The indexed binding correction is recorded in
[`claim_binding_acceptance_2026-08-14.json`](claim_binding_acceptance_2026-08-14.json).
On implementation commit `0479336`, a fresh signed-in `critique_plan` run completed discovery,
server capture, tool-less indexed binding, independent cold attestation, stable-ID reconciliation,
and durable persistence for one official Python Software Foundation claim in 39.877 seconds and
three claim-model calls. The persisted claim count is one supported, zero refuted, zero unverified,
with no claim debt. A second production-backed controlled run on commit `8e24587` used signed-in
Codex discovery and cold attestation plus real server captures, deliberately omitted expected key
`(1,0)` at the model boundary, and durably produced one supported claim plus one context-only
`unverified` claim. Explicit `usable:false` and omission also have separate durable provenance.
An explicit unusable row retains server capture-failure provenance when capture itself failed.
The artifact records the +48/-11 production diff and the three largest production modules. The
disposable plan later opened unrelated structural findings, so the artifact claims current-revision
claim-path acceptance, not whole-plan convergence.

The final acceptance run is bound to behavior commit `ac50c47`. Signed-in Codex discovered three
official Python release claims and the server captured all three pages. A controlled production
model boundary preserved one valid binding, omitted key `(1,0)`, and returned `usable:false` for
key `(2,0)` after replacing that real capture with a deterministic failed-capture record. Signed-in
cold attestation and canonical atomic persistence then produced one supported claim, one omitted
`unverified` claim, and one capture-failed `unverified` claim with distinct provenance. The run used
three model calls and 42.151 seconds; its sessions, response hashes, state hash, and exact durable
outcomes are retained in the artifact.

A second controlled failure run on the same `ac50c47` behavior commit used signed-in discovery,
real server capture, and signed-in binding for two claims, then supplied a Boolean-alias identity at
the cold-attestation boundary. Exact identity validation rejected the response before settlement.
Canonical durable state remained blocked with zero applied claims and retained debt bound to the
exact rejected-response hash, so the valid sibling row could not be misbound or partially applied.
The run used two signed-in calls plus the controlled attestation boundary and 38.555 seconds.

When discovery and its one same-session correction both fail local payload validation, the claim
debt preserves the bounded reasons in initial/correction order. Its rejected raw identity is the
initial provider envelope, the literal discovery-correction separator, and the corrected provider
envelope in that order. Provider return code zero remains distinct from a reviewer execution error.
The controlled signed-in acceptance record is
[`minimal_claim_validation_acceptance_2026-08-18.json`](minimal_claim_validation_acceptance_2026-08-18.json).
It is bound to behavior commit `af93499`, Codex CLI 0.144.6, `gpt-5.6-sol`, high effort, and web
search enabled. Two same-session discovery calls both exited zero; controlled post-extraction text
made both payloads invalid while preserving their real provider envelopes. The production handler
persisted both ordered reasons, caller-visible blocking debt, and the exact aggregate raw SHA-256 in
157.974 seconds. The behavior diff against `main` is 25 additions and five deletions across
`handlers.py` and `plan_claims.py`; the three largest Python production modules are `handlers.py`
(135,711 bytes; 2,917 lines), `arbitrate_handler.py` (127,166 bytes; 2,991 lines), and
`plan_claims.py` (62,865 bytes; 1,422 lines).

The current Codex acceptance record is
[`external_claim_acceptance_2026-08-09.json`](external_claim_acceptance_2026-08-09.json).
It covers a known false internet-only claim, an external fact, an RFC design principle, an
external-library behavior, an internal bridge that must stay out of inventory, retained-packet
reuse, and a fresh current-snapshot convergence: round 2 closed four corrected claims and
unchanged round 3 reused all four in 1 ms with no evidence-model call. The same record separately
identifies the earlier implementation commit used for the fresh 102 KB real-dossier run, which
converged in two rounds with seven external claims; it does not present that older run as evidence
for later parser changes.

The server-capture migration is separately recorded in
[`evidence_capture_acceptance_2026-08-10.json`](evidence_capture_acceptance_2026-08-10.json).
It records a fresh two-vendor external arbitration, two fresh Codex plan claims closed only after
server capture and cold attestation, and an explicit repository-only arbitration. It also records
the timeout and Claude inert-root defects those real runs exposed before the successful reruns.

The long-page follow-up is recorded in
[`large_page_capture_acceptance_2026-08-18.json`](large_page_capture_acceptance_2026-08-18.json).
A signed-in Codex run discovered the official Python decimal reference, captured all 70,378
extracted characters, bound an exact passage with browsing disabled, and obtained an independent
positive authority/entailment attestation. A separate signed-in arbitration researcher then
discovered five sources and bound all five through the bounded capture-reference envelope.
Both paths completed in 79.361 seconds
with five model calls and no validation retry.
The production diff is 241 additions and 47 deletions across `external_sources.py`,
`arbitration_research.py`, `handlers.py`, and `arbitrate_handler.py`. At acceptance time the three largest production
Python modules were `handlers.py` (138,392 bytes; 2,971 lines), `arbitrate_handler.py` (127,184
bytes; 2,991 lines), and `plan_claims.py` (62,865 bytes; 1,422 lines).
