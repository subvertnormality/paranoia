# Exhaustive-census prototype evidence

This record freezes the evidence used to choose the staged-census architecture. It is not a shipping
acceptance result. Shipping still requires the blinded, implemented A/B convergence replays in
`docs/exhaustive_review_census_plan.md`.

## Plan fixture

- Historical lineage: `parallax~3~A3-HOLD-TERMINATOR~plan` (16 review rounds).
- Repository commit: `1376093e6d8febd0fd35d580b4390ddd45118675`.
- Artifact: `dataset/certification/A3-HOLD-TERMINATOR_contract.md`.
- Artifact SHA-256: `5cce5bf952455959cf69dfbae74120c03386746eca2888316a2a58592606300d`.
- Raw prototype record SHA-256:
  `a11a8cb3c3eb960e016f28713d4fe1670076810f941efe3e2d4ad668141a2291`.
- Engine: Codex, high reasoning; no historical findings or class oracle was supplied.
- Method: three independent whole-artifact lanes (`domain`, `execution`, `integrity`) ran in
  parallel with the fixed nine-item checklist in the plan. A fourth call consolidated every lane
  finding by source ID without conducting another review.
- Sessions: `019fecae-11f3-7c03-ab0c-ce5480a1c520` (domain),
  `019fecae-1466-7f33-8da8-a6a1ac890529` (execution),
  `019fecae-11ca-7500-b46a-21f426601514` (integrity), and
  `019fecb7-5e18-7900-b038-c6f4e3edbc38` (consolidation).
- Calls and time: four valid calls; 691,728 ms monotonic elapsed, of which consolidation used
  81,907 ms. Lane output contained 5, 7, and 7 findings respectively. The complete four-call JSON
  record was 46,708 bytes.

The consolidation mapped all 19 source findings exactly once into these eight governing findings:

| ID | Severity | Governing finding | Historical root class recovered |
| --- | --- | --- | --- |
| C1 | FATAL | The plan targets a retired producer and specifies an artifact the canonical consumer does not accept. | Wrong executable producer/consumer |
| C2 | MAJOR | The numerical minimum and predicted movement image are not established by the measurements. | Unsupported numerical and movement-image conclusions |
| C3 | MAJOR | CIK and lifetime-symbol identity bridge distinct issuer/security epochs and mishandle unknown identity. | Null-CIK/reused-identity error |
| C4 | MAJOR | Required A1, ADR digest, and class-economics inputs are absent or unbound. | Missing reproducible inputs/digests |
| C5 | MAJOR | The proposed artifact lacks a complete, authenticated, deterministic producer/consumer contract. | Incomplete artifact contract |
| C6 | MAJOR | Acceptance omits material identity, predicate, provenance, and poison-boundary behavior. | Acceptance/test gaps |
| C7 | MAJOR | The declared card base conflicts with the pinned Git history. | Card-base mismatch |
| C8 | MAJOR | The escalation and recovery sequence is prose, not an executable fail-closed protocol. | Non-executable escalation path |

The historical first-round claim verifier separately registered eight external claims, refuting
three and leaving five unverified. Structural census is therefore additive to, not a replacement
for, the existing authoritative external-evidence path.

## Interpretation

This blind first-pass result recovered every applicable historical FATAL/MAJOR root class used as
the oracle. It supports the small design choice: exact retention of reported findings, fixed
responsibility ownership, durable debt, targeted correction, and one cold final regression. It
does not show how many rounds the implemented loop needs or prove branch-mode coverage. Those are
mandatory pre-PR gates and will receive their own frozen acceptance records.

## Branch fixture

- Historical lineage: `parallax~3~SPINE-COVERAGE-EXTENSION`, which reached sequential round 11.
  Its 17 audit logs include replayed round numbers and must not be reported as 17 sequential rounds.
- Base: `9f8961521fc2da53bf6184b7c56746ba709035a9`.
- Head: `4787a36aed9fd99987eb7682cdba21af5fa18a16`.
- Raw prototype record SHA-256:
  `a6768c95dc3033779aa22a1bd51a35e880975d52ba78b071fd30163b841fe57d`.
- Engine: Codex, high reasoning; no historical findings or class oracle was supplied.
- Method: three independent whole-diff lanes (`behaviour`, `execution`, `integrity`) plus one
  source-ID-complete consolidation call, using the same fixed checklist as the plan prototype.
- Sessions: `019fecc1-e644-78e3-904d-d2a341efda50` (behaviour),
  `019fecc1-e664-7dd3-a7b8-4d1d3bb220dd` (execution),
  `019fecc1-e60d-7fd2-bce3-9cb954bdce22` (integrity), and
  `019fecca-78fa-72e0-9222-e7b06c1ed4ad` (consolidation).
- Calls and time: four valid calls; 603,685 ms monotonic elapsed, of which consolidation used
  41,462 ms. Lanes returned 3, 4, and 2 findings; all nine were mapped exactly once into six
  governing findings.

The governing result comprised five MAJORs and one MINOR. It recovered the historical
missing-adjudication/default-classification defect and the known-red/governance-test branch-gate
coverage defects. It also identified whole-module rather than identity-bounded ledger repair,
caller-controlled/circular `source_commit` provenance, incomplete nested-test selection, and drift
between reviewed backlog population and application. This is a useful first-pass branch signal,
but it is not the shipping A/B: the acceptance replay must follow the lineage's ordered snapshots,
evaluate findings against the frozen per-snapshot historical oracle, and measure complete
convergence rather than only one final-head census.

## Existing-state sizing observation

On 2026-08-10, the design pass parsed all 106 JSON lineage files in the operator's existing
`~/.paranoia/lineages` store and ran each through the current mode-appropriate context renderers:
`render_unclosed`, `render_unmechanized`, and `render_exempt`. This includes headings, class state,
detail, every retained match, exemptions, and displayed escaping—not only the semantic fields. The
largest exact rendered context was 20,973 characters
(`parallax~3~APPEND-ASSURANCE-SUCCESSOR~plan`, 36 active class records); the largest individual
procedure was 651 characters. This observation supports a 64,000-character
active-class-context boundary for the stated real-world scale. It does not justify silent
truncation: any state outside that supported boundary must report `STATE-OVERSIZED` and remain
blocked.
