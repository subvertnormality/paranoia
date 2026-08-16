# Arbitration original-neutrality fallback plan

## Objective

Fix the recurring cleaner-fidelity failure class without weakening arbitration neutrality. A
cleaner may still rewrite caller framing, but a semantic rewrite must not make an otherwise neutral
caller packet unsatisfiable. The cross-vendor attester will separately judge the original
cleaner-owned fields. When the original framing is neutral and the cleaned framing is unusable, the
server will send the canonical post-validation original decision, option statements, and full
validated hint entries to both deciders.

## Frozen operating model

One trusted operator runs the local CLI on a trusted OS. The caller owns the decision, options,
context, stakes, and file hints. Repository bytes, caller prose, cleaner output, attester output,
research pages, and decider output are untrusted data. The cleaner and attester are separate
provider/model roles; neither has repository or web access. Two deciders receive counterbalanced
labels over one pinned inert snapshot. A normal arbitration has two to four options, up to two
cleaner/attester attempts, two deciders per round, and must return useful failure or convergence
within minutes. There is no hostile local process racing paths and no compromised OS or provider.

False convergence, semantic option loss, caller-ID leakage, and advocacy reaching both deciders are
high impact. A visible recoverable block is acceptable, but repeated tool-side rejection of neutral,
faithful input is also a correctness failure because it makes a decision unobtainable. Multi-tenancy,
hostile same-user races, formal proof of model judgement, changing research/capture, and redesigning
decider voting are excluded.

## Class assessment

The reported failures form one class: **a transformation role owns caller semantics, while the
verification role can only reject after semantic loss**. It is observed across decision text, hint
reasons, and option statements, not one prompt example. The context/option “two-wall” trap is a
consequence: option-specific facts belong in options, but a cleaner can delete them; moving them to
caller-owned context exposes them to the independent context-advocacy gate.

A prompt-only reminder is not a class fix. It leaves the cleaner authoritative and probabilistic.
Adding a `common` input block does not solve distinguishing option facts, and weakening context
advocacy would allow shared steering. Removing fidelity rejection would be unsafe. Adding another
model call would increase cost without changing authority.

## Protocol change

1. Extend the attester contract with one closed verdict line:
   `ORIGINAL-NEUTRALITY: PASS` or
   `ORIGINAL-NEUTRALITY: FAIL {"field":"<decision|hints|known option id>","passage":"<exact non-empty original substring>"}`.
   It judges the original decision, options, and complete validated hints (paths and reasons) as one
   packet. The FAIL JSON must contain exactly `field` and `passage`; JSON escaping is standard, the
   field must be present in the attested originals, and the passage must occur in that exact field.
   Free text, extra keys, an unknown field, or a passage mismatch is invalid. Stakes and context
   remain governed exclusively by their existing independent advocacy verdicts. `NEUTRALITY`
   continues to judge the cleaned packet.
2. Parse exactly six ordered verdict lines: `FIDELITY`, `FIDELITY-DETAIL`, `NEUTRALITY`,
   `ORIGINAL-NEUTRALITY`, `STAKES-ADVOCACY`, and `CONTEXT-ADVOCACY`. The existing closed
   fidelity/detail grammar is unchanged. `NEUTRALITY` remains exactly PASS or FAIL plus a non-empty
   diagnostic; stakes/context remain exactly NONE or PRESENT plus a non-empty diagnostic. Those
   three failure diagnostics only block and never authorize fallback. Reject duplicates, missing
   values, reordered lines, trailing commentary, qualifications after PASS/NONE, or malformed forms.
   Persist the raw attestation unchanged.
3. Bound the complete original framing before the first cleaner call: retain the decision, option,
   and context limits; add maximum hint count, per-reason length, and aggregate rendered-hint length.
   The exact constants belong beside the existing framing bounds and are repeated in the tool schema.
   After parsing a cleaner candidate, require all four blocks, the exact 1:1 option-id set, non-empty
   decision/statements, and a bounded absolute candidate size before attestation. Those are structural
   prerequisites because otherwise field binding is incomplete or the attester input is unbounded.
4. Keep the existing preferred path: when cleaned fidelity, cleaned neutrality, and relative length
   bands pass and stakes/context do not advocate, use the cleaned packet.
5. For every structurally complete, bounded candidate, collect cleaned-path ineligibility reasons
   without rejecting before attestation. These include relative length-band failure and any reserved
   caller token introduced into decision, context, statements, or merged hints. Such bytes may reach
   the tool-less attester but never a decider. Add a deterministic fallback after that candidate
   receives a valid attestation:
   when the cleaned candidate fails fidelity, cleaned neutrality, or relative length bands but
   `ORIGINAL-NEUTRALITY` passes, use the canonical post-validation original decision, option
   statements, and validated hint paths/reasons. Preserve exact stakes and context as today. No cleaner-produced byte
   reaches either decider on this path. Record `CLEANING: original-attested` and retain the cleaner
   and attester attempt ledger.
6. Use this route table on every attempt: malformed, absolute-oversize, or incomplete cleaner output
   retries without fallback because it cannot be safely field-bound and attested; context or stakes
   advocacy blocks the run; a fidelity/neutrality-valid cleaned packet with no collected ineligibility
   wins; otherwise an eligible neutral original falls back; otherwise
   retry once, then fail. The first valid `ORIGINAL-NEUTRALITY: FAIL` is latched for fallback
   eligibility across the retry, so repeated attestation cannot hill-climb the unchanged original
   packet from FAIL to PASS. A malformed first attestation establishes no verdict.
7. Context or stakes advocacy remains immediately blocking even if original cleaner-owned fields are
   neutral. The fallback does not move option-specific facts into context and does not reinterpret
   factual asymmetry as shared context.
8. Historical five-line attestations and `attested`/`attested-after-retry` audit records remain valid
   historical version-1 evidence and are never reinterpreted. New live calls require the six-line
   contract. Add `original-attested` to the closed status vocabulary in packet records, renderers,
   validators, fixtures, tool documentation, and acceptance artifacts; its persisted `cleaned`
   object remains the rejected cleaner candidate for audit, while decider prompt records prove the
   canonical original packet was used.
9. Replace public advice that moves the full specification of a one-option mechanism into context.
   Context is only for facts/specification common to every option. Concise parallel option statements
   retain every option-specific mechanism, constraint, and consequence.

## Invariants

- The fallback is attester-authorized, not a heuristic based on string length or cleaner failure.
- Canonical original fields are bounded, option-ID checked, caller-token checked, and validated
  against the pinned snapshot before cleaning;
  fallback does not bypass those preflights.
- Canonical post-validation originals are used as one atomic packet; fields are never mixed between
  original and cleaned forms. Raw request whitespace trimmed by existing scalar/option validation is
  not promised.
- The same exact packet still reaches both deciders with only opaque label/order presentation
  differences.
- No new retry, provider role, durable state version, caller field, or model call is introduced.
- `clean: false` behavior is unchanged.

## Tests

- Strict parser cases for missing, duplicated, reordered, malformed, and commented
  `ORIGINAL-NEUTRALITY` lines, plus unknown targets and passages not found in the original field.
- A reproduction based on the reported shape: byte-identical shared factual paragraphs plus distinct
  factual consequences; the cleaner compresses both options, fidelity reports removal, original
  neutrality passes, and both deciders receive the exact original statements.
- Original advocacy fails, so a fidelity-changing cleaner still retries and ultimately blocks.
- A first valid original FAIL is latched; a second-attempt PASS cannot authorize fallback, while a
  second faithful cleaned candidate can still succeed.
- Cleaned faithful neutrality remains the preferred `attested` path even when originals also pass.
- Cleaner-introduced bias falls back to a neutral original packet.
- Context or stakes advocacy blocks before fallback.
- A neutral hint reason with an advocating path cannot authorize fallback; hint count/reason/aggregate
  limits reject before the first cleaner call.
- Decision and hint fidelity changes use the same all-original fallback, proving the class rather
  than only option statements.
- Audit output records `original-attested`, exact raw/cleaned inputs, attestation, attempts, and
  unchanged canonical caller option mapping on success and failure. Historical five-line acceptance
  remains valid without being parsed as the new live form.
- Relative length-band rejection remains attested and can fall back; malformed IDs, missing blocks,
  and absolute oversize remain structural retry/failure paths. A cleaner-introduced caller token is
  attested but makes the cleaned path ineligible; it can recover only to the token-clean original.
- `_HOIST_REMEDY`, README, the MCP tool schema, status comments, acceptance validators, and packet
  reconstruction tests agree on the new guidance and status.
- Existing arbitration, cleaning-attestation acceptance, and full suites pass.

## Primary acceptance

Run the real signed-in cleaner/attester path on a small pinned fixture whose two options contain a
shared factual paragraph and different factual consequences, using the reported reproduction shape
that repeatedly caused compression. Acceptance is valid only when the signed-in providers exercise
the fallback and the resulting status is exactly `original-attested`, the persisted cleaned candidate
remains visibly unusable, both persisted decider prompts contain the canonical original facts, and an
ordinary arbitration outcome is produced. The deterministic injected-agent integration test forces
the same route independently of provider variability. Record provider/model versions, call count,
elapsed time, cleaning status, and audit digest.

Then run Codex CODE convergence against the implementation under the frozen operating model. Accepted
findings receive one coherent correction and focused rerun; recurring architectural objections stop
for a checkpoint rather than growing the protocol.

## Acceptance boundary

This change proves that neutral original cleaner-owned fields remain usable when a cleaner changes
meaning or introduces bias. It does not claim that every caller framing is neutral, that factual
claims are true, or that the context advocacy model cannot err. Repository deciders and shared
research remain responsible for truth; the attester governs framing neutrality and transformation
fidelity only.
