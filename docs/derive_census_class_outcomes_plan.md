# Derive census class outcomes from the integrity manifest

Status: revision 2 after broad PLAN census.

## Decision

Remove `class_outcomes` from the **census consolidation** model schema and derive every census class
assessment from the already validated integrity-lane manifest. Keep model-authored `class_outcomes`
unchanged for correction and final, where there is no earlier lane judgement to project.

This removes four copy/reconciliation failures from census output: duplicate class rows, copied
verdict mismatch, copied evidence mismatch (including order), and a copied basis that names the
wrong governing finding. It does not weaken the semantic binding between an integrity violation and
the consolidator's classification of the governing finding.

## Frozen operating model

One trusted operator runs the local CLI/MCP service on a trusted OS. Pinned Codex/Claude providers
and the canonical class engine are trusted. Repository bytes, lane manifests, and model JSON are
untrusted static data; inert review does not execute repository-selected code. There is no hostile
local race. Three census lanes may run concurrently, followed by one consolidation and at most one
same-session validation retry. Supported scale is 300 lane findings and 100 active classes, with
results useful within minutes. False clearance, wrong finding-to-class binding, or altered integrity
evidence are high impact; a visible recoverable rejection is acceptable. Excluded are partial
settlement, multi-tenancy, compromised provider/OS behavior, hostile same-user races,
deliberately corrupted-state recovery, formal proof, and correction/final semantic redesign.

## Ownership boundary

The integrity lane owns each active class's semantic judgement exactly once:

- `class_id`;
- `verdict` (`satisfied` or `violated`);
- ordered evidence anchors; and
- for a violation, the cited integrity-lane finding ID.

Consolidation owns a different judgement: how each lane source becomes a governing finding and
whether that finding is one-off, a new reusable class, or an occurrence of an existing class. It
must not restate the integrity verdict or evidence.

For a satisfied integrity assessment, the server derives a satisfied class outcome with the exact
manifest evidence and no basis. A governing finding that nevertheless classifies to that satisfied
class remains a semantic contradiction and receives a pointer-addressed retry issue against that
model-owned classification.

For a violated integrity assessment, the server uses the cited qualified lane source to find
governing findings whose `source_ids` contain it and whose classification names that same existing
class. Exactly one must exist. The server derives the violated outcome with exact manifest evidence
and `new_finding` basis naming that governing finding. Zero or multiple matches reject with one
bounded actionable issue; the server cannot safely choose whether a mismatched finding should be
one-off, new-class, or a different existing class.

## Schema cutover

`decision_schema(mode, "census")` omits `class_outcomes` entirely from its closed properties and
required keys. Correction and final schemas retain the current field unchanged. Provider and local
schemas therefore agree, and an attempted census `class_outcomes` field is rejected as an additional
property before semantic materialization.

There is no permissive alias, ignored legacy field, durable dual protocol, or extra model call. The
consolidation prompt stops asking for class outcomes and instead states that the server derives them.
The response-size bound may remain unchanged; reducing it is not part of this correction.

## Materialization order

1. Decode the role-specific closed schema.
2. Validate/rekey response-local governing finding IDs as today. Rekeying no longer has census
   outcome references to rewrite; correction/final rewriting remains unchanged.
3. Map and severity-check every census source.
4. Validate every governing finding classification and build `finding_id -> class_id`.
5. Derive one outcome per integrity assessment using the rules above.
6. Feed the derived outcomes through the existing debt, assessment, class-action, canonical-engine,
   anchor, and atomic-settlement path.

### Diagnostic provenance

No census diagnostic may point at the removed `/class_outcomes` field. Before consolidation, lane
validation receives the bounded active-class metadata rather than IDs alone and rejects a satisfied
assessment for an unproven mechanized class at that lane's
`/class_assessments/<index>/verdict`; the existing same-session lane retry can repair it. This is the
only outcome/class-state combination that no consolidation action can make legal: an unproven
mechanized class is owned by its server sweep, not model closure.

During consolidation, zero or multiple cited-source/class matches point to `/governing_findings` and
name the exact source and class. An authored incompatible lifecycle operation points to its exact
`/class_actions/<index>`. A closed violated class with no required reopen/replace points to the
existing `/class_actions` array and names the required operation. Open class-bound debt that lacks a
violated derived assessment continues to point to its authored `/debt_outcomes/<index>` row.
Server-derived close records use `/class_actions` as canonical-engine provenance; the model may
override the redundant derivation only with an independently legal action already admitted by the
current contract.

Tests mechanically resolve the JSON Pointer prefix of every independently detectable census issue
against the response for the phase that receives that retry. Lane issues resolve against the lane
response; consolidation issues resolve against the consolidation response.

The materialized durable V1-shaped settlement remains unchanged: it still contains one explicit
`class_assessments` row and assessment disposition for every active census class. Debt IDs, class
IDs, source fan-out, advisory debt, close derivation, and trailers do not change.

## Historical and cache behavior

Existing durable lineage state contains debt, phase, and resulting class state, not raw census
decisions or materialized assessment rows, so no migration is required. Exact materialized
`class_assessments` remain in the audit's `staged_settlement`.

Integrity lane prompts already carried bounded class-state metadata, so compatible pre-cutover
manifests may remain reusable under the existing exact cache binding. Every cached manifest is
revalidated by the current lane parser before reuse; an old satisfied assessment for an unproven
mechanized class is therefore rejected and fresh lanes run. A seeded pre-cutover-cache test proves
that semantic revalidation, rather than a claimed prompt-byte change, rejects that manifest. A fresh
impossible assessment is rejected in the lane's own same-session retry before it can become
cacheable. If both integrity-lane attempts return it, the terminal lane failure persists no census
cache. A cross-invocation handler test repeats the request byte-for-byte and proves that all lanes
execute again rather than replaying the rejected integrity manifest.
After all lanes validate, every remaining derived-outcome failure is repairable solely by
governing-finding classification/source mapping or `class_actions`, so a terminal consolidation
validation rejection may retain the existing exact-bound lane cache. Tests cover both cache
invalidation across the prompt cutover and same-input recovery from a consolidation-only rejection
without rerunning valid lanes.

The retained Protocol-v2 provider acceptance predates this schema cutover. Preserve it as historical
evidence rather than rewriting its claimed bytes. Its executable test must validate the old census
probe against a frozen **test-only** old census schema representation, while correction/final probes
continue to bind current schemas. Add a new real-provider acceptance artifact for the new census
schema. No historical compatibility parser enters production.

The linked `staged_review_protocol_v2_plan.md` is a historical shipped design: mark its census
example and class-outcome bullet superseded by this amendment and link here. Update README's protocol
description and design-document index to state that census outcomes are derived while correction and
final remain model-owned.

## Implementation surface

- `staged_protocol.py`: make the decision schema role-specific; make collision rewriting tolerate
  census absence; derive census outcomes after source/classification validation; retain existing
  correction/final validation.
- `handlers.py`: continue passing server-owned integrity verdict/finding/evidence maps; these become
  derivation inputs rather than copy-comparison inputs.
- `prompts.py`: remove the census class-outcome copy instruction and document server derivation plus
  the one semantic classification obligation.
- Tests, README, AGENTS, and bounded acceptance artifacts: update the public contract and prove the
  cutover without changing correction/final documentation.
- `scripts/run_staged_protocol_mutation_checks.py`: add owned mutants for census-schema exclusion
  of authored `class_outcomes`, integrity-lane rejection of satisfied assessments for unproven
  mechanized classes, cited-source/class cardinality, exact manifest-verdict projection, exact
  manifest-evidence projection, and derived assessment completeness. These six mutants exhaust the
  new trusted schema/lane/derivation controls; retain the existing differential corpus and require
  this independent gate alongside the ordinary suite before PR.

No change is required to `review_census.settle_state`, class persistence, provider engines, retry
count, timeout, cache storage, evidence anchors, claim verification, arbitration, or branch/plan
lifecycle scheduling.

## Tests and acceptance

Focused schema tests prove census rejects an authored `class_outcomes` key while correction/final
still require and accept it. Materializer tests cover:

1. satisfied derivation with exact ordered integrity evidence;
2. exact satisfied and violated verdict projection plus the single cited-source/class match;
3. zero matching governing findings;
4. multiple matching governing findings;
5. a governing finding targeting a satisfied class;
6. source fan-out to several distinct violated classes;
7. response-local finding-ID rekey for correction/final and absence of a census rewrite dependency;
8. advisory violated-class debt and server-derived close behavior; and
9. historical V1 materialization equivalence for census, correction, and final.

Cross-layer tests drive the tracked handler with a seeded active class and validated manifests,
assert the consolidation response schema has no class outcomes, and verify exact audited/durable
assessment projection. A consolidation response with the removed field must enter the existing
same-session schema retry; a corrected response without it must settle. Another test reuses cached
lanes created before consolidation rejection and proves the new derivation settles without rerunning
lanes. A seeded compatible-binding cache test presents a pre-cutover satisfied/unproven-mechanized
manifest and proves current semantic revalidation refuses it. A separate unchanged-input recovery
test makes both integrity attempts return a satisfied
assessment for an unproven mechanized class, asserts the terminal lane failure wrote no census cache,
then invokes the handler again and proves fresh lane calls occur before a valid settlement.

Run the historical differential plus expanded mutation release gate independently of pytest.
Before PR, exercise the exact new provider census schema through both supported transports: pinned
Codex structured output and Claude's object-valued `structured_output`. For each, retain the exact
provider schema, the exact returned response object, both hashes, and the server-owned assessment
inputs used for local materialization. An executable acceptance test must regenerate the current
role schema, recompute both hashes, schema-validate the retained response, and decode/materialize
that exact object with those recorded inputs for **each** provider artifact. A process exit plus
prose is not Claude structured-output acceptance: its envelope must contain the retained object in
`structured_output`. Run a signed-in Codex primary census with active classes; use both a satisfied and
a violated class only if the controlled fixture can establish them without inventing product
defects, otherwise limit the live lifecycle claim to what it observes and let deterministic tests
own the other case. Retain audit hashes, model-call count, real elapsed time, production diff size,
and largest changed modules. Then run same-vendor Codex CODE convergence under the same frozen stakes.

## Non-goals

- no partial settlement of genuinely inconsistent classifications;
- no server inference of one-off versus new/existing class;
- no set/sort normalization of evidence, because the server copies validated manifest order;
- no change to correction or final class judgements;
- no extra provider call, retry, state file, or persistence version; and
- no claim that deterministic projection prevents unrelated model semantic errors.
