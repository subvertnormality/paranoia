# Arbitration original-neutrality fallback plan

## Objective

Fix the recurring cleaner-fidelity failure class without weakening arbitration neutrality. A
cleaner may still rewrite caller framing, but a semantic rewrite must not make an otherwise neutral
caller packet unsatisfiable. The cross-vendor attester will separately judge the original
cleaner-owned fields. When the original framing is neutral and the cleaned framing is unusable, the
server will send the exact original decision, option statements, and hint reasons to both deciders.

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
   `ORIGINAL-NEUTRALITY: PASS` or `ORIGINAL-NEUTRALITY: FAIL <specific option and words>`.
   It judges only the original decision, options, and hint reasons as one packet. Stakes and context
   remain governed exclusively by their existing independent advocacy verdicts. `NEUTRALITY`
   continues to judge the cleaned packet.
2. Parse the new line strictly and require exactly six ordered verdict lines. Reject duplicates,
   missing values, commentary, or malformed PASS/FAIL forms. Persist the raw attestation unchanged.
3. Keep the existing preferred path: when cleaned fidelity and neutrality pass and stakes/context do
   not advocate, use the cleaned packet.
4. Add a deterministic fallback after a valid attestation: when cleaned fidelity or neutrality
   fails but `ORIGINAL-NEUTRALITY` passes, use the exact caller decision, option statements, and
   validated hint paths/reasons. Preserve exact stakes and context as today. No cleaner-produced byte
   reaches either decider on this path. Record `CLEANING: original-attested` and retain the cleaner
   and attester attempt ledger.
5. When original neutrality fails, retain the existing one correction attempt. A cleaned packet must
   then pass both fidelity and cleaned neutrality. If neither path is valid after the bounded retry,
   fail visibly as today.
6. Context or stakes advocacy remains immediately blocking even if original cleaner-owned fields are
   neutral. The fallback does not move option-specific facts into context and does not reinterpret
   factual asymmetry as shared context.

## Invariants

- The fallback is attester-authorized, not a heuristic based on string length or cleaner failure.
- Original fields were already bounded, option-ID checked, and caller-token checked before cleaning;
  fallback does not bypass those preflights.
- Exact originals are used as one atomic packet; fields are never mixed between original and cleaned
  forms.
- The same exact packet still reaches both deciders with only opaque label/order presentation
  differences.
- No new retry, provider role, persistence format, caller field, or model call is introduced.
- `clean: false` behavior is unchanged.

## Tests

- Strict parser cases for missing, duplicated, reordered, malformed, and commented
  `ORIGINAL-NEUTRALITY` lines.
- A reproduction based on the reported shape: byte-identical shared factual paragraphs plus distinct
  factual consequences; the cleaner compresses both options, fidelity reports removal, original
  neutrality passes, and both deciders receive the exact original statements.
- Original advocacy fails, so a fidelity-changing cleaner still retries and ultimately blocks.
- Cleaned faithful neutrality remains the preferred `attested` path even when originals also pass.
- Cleaner-introduced bias falls back to a neutral original packet.
- Context or stakes advocacy blocks before fallback.
- Decision and hint fidelity changes use the same all-original fallback, proving the class rather
  than only option statements.
- Audit output records `original-attested`, exact raw/cleaned inputs, attestation, attempts, and
  unchanged caller option mapping on success and failure.
- Existing arbitration, cleaning-attestation acceptance, and full suites pass.

## Primary acceptance

Run the real signed-in cleaner/attester path on a small pinned fixture whose two options contain a
shared factual paragraph and different factual consequences. The cleaner must either preserve
fidelity normally or trigger the attester-authorized all-original fallback; both deciders must then
receive the exact option facts and produce an ordinary arbitration outcome. Record provider/model
versions, call count, elapsed time, cleaning status, and audit digest.

Then run Codex CODE convergence against the implementation under the frozen operating model. Accepted
findings receive one coherent correction and focused rerun; recurring architectural objections stop
for a checkpoint rather than growing the protocol.

## Acceptance boundary

This change proves that neutral original cleaner-owned fields remain usable when a cleaner changes
meaning or introduces bias. It does not claim that every caller framing is neutral, that factual
claims are true, or that the context advocacy model cannot err. Repository deciders and shared
research remain responsible for truth; the attester governs framing neutrality and transformation
fidelity only.
