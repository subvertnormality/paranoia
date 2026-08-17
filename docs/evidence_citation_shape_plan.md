# Evidence citation shape design

## Status and scope

Implemented on the issue #38 branch. This document records the converged design and its bounded
acceptance claims.

Issue #38 is current under Protocol v2: model responses still append rationale prose or join
multiple citations inside an `evidence` string, and both the initial response and its bounded retry
can fail exact anchor resolution. The fix covers every model-owned staged evidence array in census
lanes, consolidation, correction, and final. It does not relax anchor grammar, accept a leading
substring, partially settle an invalid response, follow repository symlinks, or add a model call.

## Frozen operating model

- One trusted local operator and OS run the CLI; repository, plan, and provider text are untrusted
  data, with no repository-selected execution or hostile same-user path race implied.
- Three census lanes may run concurrently; each staged role retains one same-session validation
  retry and the existing external provider network boundary.
- Reviews contain tens to low hundreds of findings/classes/citations and should remain useful within
  minutes. False clearance, wrong evidence binding, and silently discarded citations are high
  impact; a visible recoverable block is acceptable.
- Excluded: multi-tenancy, compromised OS/provider, deliberate state corruption, formal proof,
  extra retries, new persistence, symlink evidence, unrelated claim/arbitration protocols, and
  permissive extraction of anchors from prose.

## Design

### 1. Give model-owned citations an explicit rationale field

Replace every model-facing staged evidence item with one closed object:

```json
{"anchor":"repository/path.py:12-18","rationale":"The guarded write occurs after validation."}
```

Both fields are required and bounded. `anchor` retains the exact current 512-character
plan/repository pattern; `rationale` is non-empty, single-line explanatory text capped at 500
characters. Multiple citations require multiple array
items. The prompts explicitly forbid prose in `anchor` and joined citations. The local role schema
and provider projection use this same wire shape; legacy strings, extra keys, empty rationale, and
prose-contaminated anchors reject with their exact JSON Pointer.

The wire evidence array deliberately omits `uniqueItems`: two identical citation objects must
survive structural decoding so duplicate-anchor failure can be aggregated with later safe checks.
Uniqueness is load-bearing only for the projected canonical anchor array.

### 2. Canonicalize only after closed wire validation

After a complete response passes the wire schema, project each citation object to its exact
`anchor` string. Evaluate that projection against a separate closed canonical role schema. This
second pass preserves anchor uniqueness after rationale is removed and prevents two objects with
the same anchor but different prose from bypassing duplicate checks.

Wire-schema failure still rejects before projection because there is no safe complete object to
inspect. After wire success, canonical-schema issues do not reject early: the handler accumulates
them with all independently safe semantic-graph, anchor-resolution, and canonical class-engine
issues into the existing bounded pointer-addressed diagnostic before the one retry. Projection
returns the canonical object plus issues rather than throwing on the first duplicate. Standalone
decoder helpers raise the same bounded canonical issues when no outer aggregation context exists.

All existing semantic graph checks, `resolve_anchors`, class/debt materialization, and durable
settlement continue to receive string arrays. Rationale is non-authoritative generation context;
the provider response digest/excerpt remains in the attempt audit, while durable evidence stores
only resolved canonical anchors. Do not infer, trim, split, reorder, or repair an anchor.

### 3. Separate wire replies from canonical cached manifests

Fresh provider replies use the wire decoder. Validated lane manifests are canonical string-only
objects and remain the consolidation/cache representation. Add an explicit canonical-manifest
validator for cache revalidation instead of feeding stored canonical data back through the wire
decoder. Bump the census-cache schema version so pre-cutover cache entries cannot be reused.

Consolidation receives canonical source manifests but emits citation objects for every model-owned
evidence field in its own response. Census outcomes derived from integrity assessments continue to
copy canonical ordered anchor strings exactly.

### 4. Preserve historical acceptance without production compatibility

Inventory the dated Protocol v2 acceptance artifacts before cutover. Where an artifact retains an
exact provider response, copy the complete exercised pre-cutover provider schema into a test-only
legacy fixture and replay those exact bytes against it. Where an artifact retains only hashes or a
bounded audit projection, preserve and recompute that authenticated material under an explicit
immutable hash-only historical contract; do not claim or fabricate response replay. Historical
bytes, hashes, sessions, costs, and lifecycle records remain unchanged. The production decoder
rejects legacy strings; do not add an alias or compatibility branch.

Record a new dated live-provider acceptance artifact containing the citation-object provider schema
and hash, exact successful response and hash, canonical projected manifest/settlement, provider
identity/settings, attempt count, elapsed time, and production diff/module sizes. The artifact must
prove a rationale-bearing citation crosses the real structured-output boundary and materializes to
the exact string anchor.

### 5. Keep bounds and release gates executable

The 500-character rationale bound and existing response caps remain cumulative circuit breakers.
Add a budget test with 200 rationale-bearing citations showing the encoded packet fits the
240,000-character lane cap; the 1,000,000-character decision cap remains looser. Oversized replies
still reject before JSON decode.

Extend `scripts/run_staged_protocol_mutation_checks.py` with owned mutants for closed citation
objects, exact (not trimmed/split) anchor projection, post-projection duplicate rejection,
canonical cache validation, and cache-version invalidation. Each mutant names a focused test and
the mandatory mutation command runs before merge.

## Verification

- Schema tests cover every role and every evidence-bearing row with concrete citation objects.
- Cross-role tests prove trailing prose, joined anchors, legacy strings, extra fields, and empty
  rationale fail wire validation, while exact single/range anchors pass. Projected duplicate-anchor
  issues are recorded without short-circuiting later safe semantic, resolver, or class checks.
- Materialization tests prove successful wire replies produce the historical durable string-only
  settlement shape and preserve ordered anchor identity.
- Cache tests prove canonical manifests revalidate, pre-cutover cache is invalidated, and provider
  wire objects are not persisted as cached manifests.
- One composite retry test combines both identical citation objects and same-anchor/different-
  rationale objects with a semantic graph defect, bad anchor, and invalid class action, and proves
  all independently detectable pointers appear together before settlement rejects.
- Prompt tests prove every staged role tells the model where rationale belongs and forbids joining.
- Existing out-of-range, traversal, prefix, symlink, and plan-line checks remain unchanged.
- Historical acceptance tests replay stored old response values when they exist, bind their hashes
  to the explicit canonical/legacy schema mode, and keep hash/projection-only records explicitly
  hash-only. Production rejects all legacy strings. The dated
  `evidence_citation_shape_acceptance_2026-08-17.json` provider-probe artifact binds one live Codex
  call's exact prompt, schema, raw reply, canonical projection, and successful production anchor
  resolution. It does not claim the production handler/settlement/persistence seam, future provider
  compliance, or semantic entailment; a separate handler acceptance record is required before merge.
- Every evidence-bearing wire shape accepts a 500-character rationale and rejects 501 characters.
  Valid lane and decision packets with 200 maximum-length rationales remain below their respective
  240,000- and 1,000,000-character raw-response caps.
- The bounded Protocol v2 mutation gate kills every new projection/cache/schema mutant.
- README is changed from planned status to the shipped wire-object/canonical-string/cache-version
  behavior while dated historical documents remain labeled historical.
- Run focused protocol/census/handler tests, the full suite, and one real staged CODE capability
  plus `scripts/run_staged_protocol_mutation_checks.py` before merge.

## Acceptance

- Reviewers have one explicit place to explain each citation without contaminating its anchor.
- No prose suffix or joined-citation string can be accepted by normalization or prefix parsing.
- Every accepted durable evidence item is the exact anchor that passed both schemas and resolver.
- Existing settlement semantics, provider-call count, retry count, and evidence security boundary
  are unchanged.
