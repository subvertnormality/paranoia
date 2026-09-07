# Proposed fixture-only acceptance revision

Status: the user approved the label fix and broad Codex CODE convergence as the delivery
gate. The proposal below is retained as history; its proposed new PLAN review and complete
two-provider campaign are superseded by the current gate in class-authoring-quality-plan.md.

Correct only the thirteen diagnostic string constants in the generated replacement validator:
`capture_attestation` becomes `replacement_attestation`, including the plural form.
Leave the original capture validator, imports, function signatures, conditions, return values,
exceptions, fixture specification, two defect sites and two prescribed repairs unchanged.
This removes the unintended copied-label defect that independently blocked Opus.

The concrete diff and all four proposed fixtures are in
`class-authoring-fixture-label-proposal-evidence-2026-09-07.tar.gz`: 15 files,
67,292 bytes, SHA-256
`216fa36a7ecf3f2c203a280dc17f825c1e66030d82d39cb0249296d3437c9c83`.
Every file was byte-compared with its original. The AST is identical after restoring those
13 string constants. Across defect, exact, Boolean and half-repaired variants, 800 existing
entry-point calibration checks retain the same outcomes and target failures. Only replacement
error reasons and their source/observation hashes change. These are zero-call proposal checks,
not live acceptance. No retained campaign was modified.

If approved, reopen Q4d only for this fixture construction correction, preserving Q1-Q4f's
remaining requirements. Review the revised PLAN before implementation, then return to CODE.
Add a deterministic fixture regression that verifies both entry points name their own input
on rejection and proves no non-diagnostic code changed. Keep the existing positive, malformed,
half-repair, schema/retry and resealed custody controls; run the full suite before native spend.

Authorize one fresh campaign from its committed source. Retain both providers, their models
and effort, all reviewer roles/calls, serial nodes, the maximum 32 attempts, both prescribed
repair arms, unchanged authored classes/member inventories, cold finals, source/channel joins
and full-graph qualification. Preserve and count every earlier failure. No extra repair,
class intervention, terminal rerun or runtime policy change is proposed. Another nonqualification
returns to the checkpoint. Qualified native acceptance and CODE convergence still precede delivery.
