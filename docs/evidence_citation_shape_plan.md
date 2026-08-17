# Evidence citation shape plan

## Status and scope

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

Both fields are required and bounded. `anchor` retains the exact current plan/repository pattern;
`rationale` is non-empty, single-line explanatory text. Multiple citations require multiple array
items. The prompts explicitly forbid prose in `anchor` and joined citations. The local role schema
and provider projection use this same wire shape; legacy strings, extra keys, empty rationale, and
prose-contaminated anchors reject with their exact JSON Pointer.

### 2. Canonicalize only after closed wire validation

After a complete response passes the wire schema, project each citation object to its exact
`anchor` string. Validate that projection against a separate closed canonical role schema before
semantic validation. This second pass preserves anchor uniqueness after rationale is removed and
prevents two objects with the same anchor but different prose from bypassing duplicate checks.

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

## Verification

- Schema tests cover every role and every evidence-bearing row with concrete citation objects.
- Cross-role tests prove trailing prose, joined anchors, legacy strings, extra fields, empty
  rationale, and duplicate anchors reject before resolution, while exact single/range anchors pass.
- Materialization tests prove successful wire replies produce the historical durable string-only
  settlement shape and preserve ordered anchor identity.
- Cache tests prove canonical manifests revalidate, pre-cutover cache is invalidated, and provider
  wire objects are not persisted as cached manifests.
- Prompt tests prove every staged role tells the model where rationale belongs and forbids joining.
- Existing out-of-range, traversal, prefix, symlink, and plan-line checks remain unchanged.
- Run focused protocol/census/handler tests, the full suite, and one real staged CODE capability
  before merge.

## Acceptance

- Reviewers have one explicit place to explain each citation without contaminating its anchor.
- No prose suffix or joined-citation string can be accepted by normalization or prefix parsing.
- Every accepted durable evidence item is the exact anchor that passed both schemas and resolver.
- Existing settlement semantics, provider-call count, retry count, and evidence security boundary
  are unchanged.
