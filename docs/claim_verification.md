# Plan claim verification

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
   and extracted-text limits, then extracts main text with Trafilatura. The same reviewer session
   is resumed with web and repository access disabled and may bind exact passages only from those
   captures. Search snippets, provider summaries, and provider-fetched page bodies never count.
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
   from demanding claim packets for repository mechanics or “missing atomic bridges.” It still
   performs the complete ordinary FATAL/MAJOR review over the plan and repository every round.
8. The computed verdict combines external-claim closure and structural-class closure.

The active inventory ceiling is 500 external claims and 20 evidence records per claim. The
composed execution budget additionally allows at most 200 source captures and five binding
batches of 400,000 characters in one audit. These are pathology/corruption guards, not
pagination limits. They cover ordinary large plans while preventing the multiplicative maxima
from turning into hours of model/network work. Exceeding one creates visible audit debt and
blocks; nothing beyond a ceiling is silently discarded or called verified.

Each discovery, captured-text binding, and cold-attestation model call has a 300-second cap;
discovery and each binding batch allow at most one correction. The complete evidence phase has
a 3,000-second monotonic deadline and at most nine model calls, including enough capacity for
one discovery correction and one binding correction at the five-batch maximum. These
limits let a large real plan complete useful research without making either a call sequence or
an individual model call unbounded.
Captured sources are downloaded with up to 16 workers under the same monotonic deadline and
per-source wall-clock bounds, then bound in deterministic indexed batches in the same corrected
discovery session. One oversized source, a sixth batch, an expired capture, or a failed batch
becomes visible blocking state rather than silently truncating the inventory.

The complete verified plan call has a 3,540-second deadline, leaving a 60-second teardown
reserve within the documented 3,600-second MCP client timeout. After evidence state is persisted,
the cold structural review starts only when its full 1,200-second cap still fits. If it does not,
the round returns blocked and the next invocation reuses frozen supported claims rather than
repeating research. A malformed class register gets one 300-second retry only when that cap also
fits the same deadline.

## Evidence and authority

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
call or web search. This optimization applies only to claim verification: the full cold
structural review still runs each round.

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

## Recorded real acceptance

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
