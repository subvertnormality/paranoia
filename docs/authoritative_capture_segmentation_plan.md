# Complete-packet binding for long authoritative sources

## Decision and operating model

The plan-verification path must not discard a complete, otherwise admissible official source
merely because it exceeds the ordinary 400,000-character binding batch. It will retain the
one-source/one-decision protocol and allow a complete primary or authoritative source to occupy a
larger dedicated packet. The complete capture will also accompany the selected exact passage in
that source's cold attestation input, avoiding fragmented or decontextualized adjudication.

This change uses the repository's default local-tool stakes: one trusted operator and OS;
repository, plan, fetched HTTP content, and provider output are untrusted static data; public
HTTP(S) capture is the network boundary; no repository code execution, hostile local path race,
compromised OS/provider, or multi-tenancy. A review ordinarily has tens to low hundreds of claims
and should finish within minutes. False support, incorrect authority/entailment, and silently
dropped evidence are high-impact. Visible recoverable blocking is acceptable. Formal proof and
deliberately corrupted-state recovery are excluded.

## Failure class and architecture checkpoint

`MAX_EXTRACTED_CHARS = 100_000` rejects ordinary primary records such as regulatory filings,
standards, manuals, and long vendor references before binding. `_binding_batches` then assumes
that every source must fit the ordinary batch size. Raising only the extraction constant moves the
first boundary and still rejects the same source after capture.

An initial segmentation proposal was rejected at the architecture checkpoint because it created
new correctness protocols for cross-boundary passages, source-level aggregation, duplicate
segment manifests, unavailable captures, replacement targeting, and downstream prompt sizing.
Those mechanisms are disproportionate when current providers can be capability-tested with the
complete reported filing. Packet and latency limits are circuit breakers, not evidence-quality
targets; the smallest coherent fix is to flex the packet allocation without splitting evidence.

## Complete-packet protocol

1. Raise the complete extracted-text admission ceiling to 1,000,000 characters while retaining
   the 5,000,000-byte raw-response ceiling. `Capture.text` and `text_sha256` continue to cover the
   complete extraction.
2. Retain the ordinary compact binding batch ceiling of 400,000 characters. Pack ordinary rows as
   today, counting the exact compact JSON representation.
3. If one row exceeds the ordinary ceiling, permit it only when the candidate is normalized again
   with `capture.final_url` and is structurally governing (`primary` or `authoritative`, eligible
   public HTTP(S) final destination, and a governing relation)
   and the complete rendered binding prompt fits a 685,000-character expanded-packet ceiling.
   Flush the ordinary batch and place that row alone. A duplicate reference never crosses a batch.
4. Size the complete initial prompt and reserve the complete worst-case correction prompt, not
   only the data array. The correction reservation includes its fixed template plus the maximum
   bounded 2,000-character local validation diagnostic. Both envelopes must fit their ordinary or
   expanded packet ceiling before the initial invocation, so a response-dependent error cannot
   make an admitted correction exceed the ceiling.
   Implement this as one pure `binding_prompts(row, diagnostic)` renderer used by both execution
   and preflight. Preflight calls it with a diagnostic of exactly 2,000 maximally escaped
   characters and requires both returned strings to fit; execution may invoke only those same
   returned shapes with a shorter bounded diagnostic.
5. Bypass model binding for unavailable captures and directly materialize their existing bounded
   server-owned capture-failure decision. Model omission can therefore never replace a known
   capture failure. If a usable row is not eligible for expansion, or the complete expanded
   prompt is too large, retain
   the existing server-owned per-source binding-budget failure and continue unrelated sources.
   Fixed non-text metadata overflow takes this same source-local path. Aggregate sixth-batch,
   model-call, and deadline exhaustion remain visible global debt; nothing is partially verified.
   Concretely, partition captures before `_binding_batches`: for every `capture.usable is False`,
   set `decisions[(claim_index, evidence_index)] = None` and do not construct a row. Final
   materialization reads the untouched `Capture` and persists its effective URL, status, content
   type, fallback fact, digests, and bounded server error. No provider value can participate in
   this path.
6. Bound model-authored binding `location` at 1,000 characters and `passage` at 8,000 characters
   before either enters later prompts. A passage remains an exact, normalized match against the
   complete capture.
7. Serialize a server-owned `binding_target` in every row: `claim.replacement` for
   `supports_replacement`, otherwise `claim.proposition`. This fixes the existing replacement
   search ambiguity while leaving final relation and replacement attestation rules unchanged.
8. Before admitting an expanded source to binding, render its worst-case cold-attestation envelope
   using the complete numbered capture plus maximum 1,000-character location and 8,000-character
   passage. It must fit 685,000 characters. Then render the exact prompt before invocation. Ordinary sources retain the existing
   bounded exact-passage packet. Every expanded source additionally contributes its complete
   numbered captured text, final URL, and digests, allowing the cold reviewer to assess the passage
   in full source context. The whole prompt must fit 685,000 characters; otherwise fail visibly
   before partial attestation. The initial and correction attestation prompts use the same check.
   An expanded source that fails this preflight receives source-local binding-budget debt before
   any model call, so it cannot abort attestation for unrelated evidence.
   Implement one pure `attestation_prompts(packet, diagnostic)` renderer shared by execution and
   preflight. The synthetic preflight packet contains the exact full capture and metadata plus a
   maximally escaped 1,000-character location and 8,000-character passage; the diagnostic is
   exactly 2,000 maximally escaped characters. Define
   `expanded_preflight = all(len(prompt) <= 685_000 for prompt in
   (*binding_prompts(max_row, max_diagnostic),
   *attestation_prompts(max_packet, max_diagnostic)))`.
   Failure replaces only this source's usability/error before batching. Execution cannot compose
   another initial or correction shape: it calls these same renderers and asserts their limits
   immediately before each provider invocation.
9. A provider execution failure on a dedicated expanded binding call becomes a bounded
   server-owned failure for that source, with the call's raw/failure/stderr channels retained in
   the attempt ledger; later batches and unrelated sources continue. Validation-invalid output
   still receives the one correction and a final invalid result remains source-local for that
   dedicated row. In both paths, replace only `text` and `error` on the immutable capture; retain
   effective final URL, HTTP status/content type, fallback fact, and content/text digests through
   audit persistence. Ordinary multi-source call failures keep their existing whole-batch behavior.
10. Unavailable captures retain exactly one truthful source-level aggregate and durable capture
    provenance. No new segment or persistent source-aggregation protocol is introduced.

The 685,000-character value is a measured compatibility ceiling, not an assumed provider promise.
Before PR, the exact maximum prompt shape must succeed through fresh and resumed Codex and Claude
binding routes, and the expanded cold-attestation route must pass the same probe. A later provider
that cannot accept the request fails visibly through the existing execution path. The ceiling can
be revised independently when real provider capability changes; evidence is never truncated to
preserve it.

Arbitration research remains outside this change. Its deliberate single 400,000-character shared
binding call and deterministic per-capture demotion are unchanged.

## Acceptance

- Exact extraction boundaries admit 1,000,000 characters and reject 1,000,001.
- A real primary source longer than 100,000 extracted characters whose complete serialized row
  exceeds 400,000 characters receives one dedicated expanded binding call, not capture debt.
- Exact full prompts at and below ordinary/expanded limits are admitted; the first character over
  is source-local binding-budget failure before invocation. Admission reserves the maximum bounded
  correction diagnostic and downstream location/passage envelope.
- Tests compare every preflight-rendered initial/correction string byte-for-byte with the string
  handed to the injected provider, including JSON escape amplification, and prove no invocation
  occurs when any of the four envelopes is one character over.
- A deep passage from the reported class of long official record reaches the cold
  authority-and-entailment attester together with the complete capture and persists its digest.
- A secondary/UGC/context row cannot claim expanded capacity merely by being large.
- A redirect from an apparently official discovery URL to UGC or plan-self content is ineligible
  for expansion under the final URL.
- Duplicate captures, ordinary multi-source batches, batch ceilings, and omission provenance
  retain their existing behavior. Unavailable captures bypass the model and cannot be mislabeled
  as an omission.
- An end-to-end unavailable capture test proves no binding row or call contains that source and
  its exact effective URL/status/content type/fallback/digests/server error reach persisted debt.
- Replacement-support rows expose the replacement as `binding_target`; support/refutation rows
  expose the original proposition.
- Oversized binding output fields reject through the one bounded correction; exact boundary values
  reach an exactly size-checked attestation prompt. Expanded-source attestation includes the full
  capture; overflow is detected per source before binding and cannot abort unrelated attestation.
- Dedicated-call execution and terminal validation failures retain the effective final URL, status,
  fallback fact, and both capture digests alongside their bounded provider channels.
- Existing capture, 403 retry, attestation, arbitration, frozen-claim, and full test suites pass.
- The pre-PR production run forces one ordinary binding call followed by one dedicated expanded
  call, with decisive evidence only in the expanded call. It records extracted characters, every
  exact rendered prompt size, batch/row and model-call counts, elapsed time, complete-context cold
  attestation, and durable capture digest. Separate fresh/resumed Codex and Claude capability probes
  exercise the maximum binding and attestation packet shapes.
- Record production diff size and largest changed modules, then run tightly scoped Codex CODE
  convergence under the operating model above.
