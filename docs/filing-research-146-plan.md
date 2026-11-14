# Issue 146: captured filing evidence

## Operating model

One trusted local operator and OS. Repository and public HTTP(S) response bytes
are untrusted data; providers may discover URLs and suggest a quoted locator but
their text never supplies evidence. No repository-selected code execution,
hostile local races, compromised OS, multi-tenancy, OCR, access-control bypass,
or deliberately corrupted state recovery. At most four capture workers per
researcher, twelve claims per researcher, two arbitration rounds, and the existing
model-call topology. Useful evidence should arrive within minutes. False clear,
authority errors and wrong evidence binding have high impact; recoverable blocking
is acceptable. Ordinary edits require another tracked review.

## Requirements

1. Shared `external_sources.capture` accepts text-bearing PDF responses using
   pypdf, retaining the original response digest and the complete extracted-text
   digest. All PDF and HTML extraction, including SGML processing and every
   fallback, runs in an interruptible subprocess under the capture's original
   remaining deadline (maximum 60 seconds). The worker enforces a 512 MiB address
   space limit on POSIX and process committed-memory limit through a Windows Job
   Object on Windows, before importing extractors. Failure to establish containment
   is a source-local retrieval failure; other platforms fail closed. Bound PDF
   decoded content streams to 20,000,000 bytes per page, at most 500 pages, and
   incrementally enforce the selected profile's output character limit. Disable
   library logging; bound the worker protocol output and parent collection to the
   maximum serialized output permitted by that character limit. Kill and reap the
   worker on deadline or protocol overflow; workers never spawn children. At most
   four capture workers per caller means at most four extraction children per caller
   (eight across concurrent arbitration researchers), not another nested pool.
   Empty, malformed, encrypted, over-limit
   and timed-out PDFs are explicit source-local retrieval failures. No OCR or
   document scripts. Plan capture keeps its 5,000,000-byte and 1,000,000-character
   limits and complete-source binding/attestation behavior.
2. For either text/html or text/plain responses beginning with DOCUMENT, support
   exactly one balanced DOCUMENT containing exactly one balanced TEXT payload.
   Reject multiple documents or TEXT blocks, missing/reversed delimiters, non-HTML
   payloads, or non-whitespace outside the sole envelope. Do not select the first
   document from a multipart submission. Extract the complete sole HTML payload;
   retain its byte offsets and captured FILENAME (if present) as extraction metadata
   alongside the full-response digest and extracted-text digest. The SGML metadata
   preamble is not evidence. Ordinary HTML and plain text retain their normal dispatch.
   When precision extraction is empty,
   retry Trafilatura recall and then its HTML-to-text extraction, excluding scripts
   and comments. Do not silently truncate or synthesize text. Preserve response
   provenance and all final-URL, public-address, redirect and deadline checks.
3. Arbitration alone may capture complete responses through 25,000,000 bytes and
   5,000,000 extracted characters, under the same capture deadline. Larger responses
   fail explicitly. This supersedes the old shared cap only for arbitration;
   plan verification and its admission reserves remain unchanged.
4. Arbitration discovery may supply an optional `quote` locator (nonempty, at most
   1,200 characters) alongside kind/proposition/candidate. Existing discovery replies
   remain valid. A locator has no evidentiary authority. For an oversized binding
   input, a quote occurring verbatim in complete captured text may select one
   contiguous window containing the quote and up to 8,000 characters on either
   side. Ambiguous repeated quotes use the first occurrence deterministically.
   Missing/mismatched locators never substitute provider text: preserve existing
   whole-source admission or explicit budget exclusion. Never concatenate remote
   spans or shorten a source without explicit window metadata.
5. Retain complete captures and their original digests in research runs/audits.
   Render window start/end offsets (zero-based, end-exclusive), full text length,
   window digest and exact window text to the binder. Deduplication must include
   the selected window as well as final URL and content/text digests. Accept a bound
   passage only if it matches the text actually supplied for that claim. Both
   deciders receive the same bound passages and independently assess publisher
   authority, entailment and relevance. Window selection never grants support.
6. Add a bounded reason to explicit unusable binding rows; accept legacy unusable
   rows with a server-owned 'no reason supplied' diagnostic. Derive a per-claim
   diagnostic from actual completed rows: capture failure, binding-budget exclusion,
   binding not completed, model rejection (with reason), or successful binding.
   Reports and audits share this derivation, including failure paths. Diagnostics
   never change research authority or the independent arbitration verdict. Preserve
   all existing attempt/retry ledgers and the two-round ceiling; add no model call.

## Acceptance and delivery

Focused deterministic tests exercise worker memory/output/deadline enforcement,
termination/reaping and completed-sibling preservation, real PDF extraction and error handling,
SGML/table-heavy HTML, unchanged plan capture limits, larger arbitration capture,
exact scoped binding, locator mismatch, per-window deduplication, budget exclusion,
and report/audit diagnostics through the public arbitration handler. Plan-handler
coverage proves captured PDF text continues through ordinary binding and cold
attestation without weakening authority. Run the appropriate existing suites.
The deterministic acceptance matrix must include the same valid single-envelope
bytes served as both text/html and text/plain and assert the exact payload-derived
text, byte offsets, FILENAME, absence of preamble text, full-response digest and
extracted-text digest. Conflicting multiple DOCUMENT blocks, multiple TEXT blocks,
missing and reversed delimiters must each produce a source-local failure retaining
available response provenance. These tests are required before CODE acceptance.

Before the PR, run real public HTTP(S) captures of
`https://www.sec.gov/files/form10-k.pdf` and
`https://www.sec.gov/Archives/edgar/data/85535/000104746912008035/a2210566z10-k.htm`.
Both must succeed, retaining HTTP status, final URL and nonempty response/text
digests. The PDF must contain the cover instruction about the number of shares
outstanding for each class of common stock as of the latest practicable date;
the filing must contain its registrant name, Royal Gold, and exclude its SGML
preamble. Bind the exact cover instruction to the proposition 'Form 10-K asks for
the number of shares outstanding for each class of common stock as of the latest
practicable date.' Run a native Codex discovery and
binding research lane against captured filing evidence, requiring at least one
governing packet from a PDF or SGML filing with no added provider calls. Do not run
Claude: the user requires Codex only, so full dual-vendor arbitration is covered
deterministically through its public handler. Failure does not qualify acceptance.
Then converge Codex CODE review, open/merge the PR and update local main. Preserve
failed attempts and report source revision, elapsed time, calls and diff size.
Update the public tool, claim-verification and how-it-works references; historical
research-design sections must defer to this contract for these changed policies.

Issue 141 separately owns configurable SEC request identity and its redirect-safe
header routing. JSON API support is not required in this card.

The round-1 claim audit failed to capture PDFs using the existing unsupported
extractor. Preserve that failure as historical debt. This bootstrap plan's later
rounds use explicit claim_verification=false for structural design review; native
capture and binding acceptance after implementation must independently qualify the
required source text. No failed claim is relabelled supported or used as evidence.
