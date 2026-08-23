#!/usr/bin/env python3
"""Project two real critique_branch audits into a bounded replayable acceptance record."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import handlers, orientation  # noqa: E402
FIXTURE_CONTRACT = (
    "# Fidelity contract\n"
    "O1: emit fidelity.json\n"
    "A1: exercise O1 through the public critique_branch entry point\n"
    "P1: persisted additions are limited to branch_contract"
)
SOURCES = (
    "src/paranoia_local/class_closure.py",
    "src/paranoia_local/handlers.py",
    "src/paranoia_local/prompts.py",
    "src/paranoia_local/runner.py",
    "src/paranoia_local/server.py",
    "src/paranoia_local/staged_protocol.py",
    "tests/test_branch_plan_fidelity.py",
    "scripts/build_branch_plan_fidelity_acceptance.py",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _attempt(row: dict) -> dict:
    return {key: row.get(key) for key in (
        "sequence", "role", "engine", "session_ref", "outcome", "returncode",
        "requested_timeout_sec", "duration_ms", "provider_duration_ms", "usage",
        "response_sha256", "response_excerpt", "raw_sha256", "raw_excerpt",
        "failure_detail_sha256", "failure_detail_excerpt", "stderr_sha256",
        "stderr_excerpt", "validation_issue", "validation_pointer",
    )}


def _plan_anchors(*values: object) -> list[str]:
    anchors: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"evidence", "assessment_evidence"} and isinstance(child, list):
                    anchors.update(
                        item for item in child
                        if isinstance(item, str) and item.startswith("plan:")
                    )
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for value in values:
        visit(value)
    return sorted(anchors)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _unique_rows(rows: object, key: str, label: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} is not a list")
    result: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str):
            raise ValueError(f"{label} contains an invalid identity")
        identity = row[key]
        if identity in result:
            raise ValueError(f"{label} contains duplicate identity {identity!r}")
        result[identity] = row
    return result


def _route(path: Path, state_path: Path, expected: str, fixture_repo: Path) -> dict:
    raw = path.read_bytes()
    audit = json.loads(raw)
    state_raw = state_path.read_bytes()
    state = json.loads(state_raw)
    settlement = audit.get("staged_settlement") or {}
    debt = (state.get("review_state") or {}).get("debt") or []
    blocking = [row for row in debt if row.get("status") == "open"]
    if expected == "conforming" and (settlement.get("findings") or blocking):
        raise ValueError("conforming audit contains findings or open debt")
    if expected == "nonconforming" and not blocking:
        raise ValueError("nonconforming audit contains no open debt")
    anchors = _plan_anchors(audit.get("staged_manifests"), settlement, state)
    packet = orientation.build_packet(
        fixture_repo, audit["base_id"], audit["head_id"],
        project_summary=None, diff_intent=None, focus=None, already_raised=[],
        class_blocks=[], max_chars=orientation.MAX_PACKET_CHARS,
    )
    contract = handlers._branch_contract_view(FIXTURE_CONTRACT)
    expected_snapshot = handlers._branch_structural_snapshot(
        base_id=audit["base_id"], head_id=audit["head_id"], packet=packet,
        contract=contract,
    )
    if expected_snapshot != audit.get("structural_snapshot"):
        raise ValueError("audit structural snapshot does not bind the fixture packet")
    return {
        "expected": expected,
        "audit_canonical_sha256": _sha(_canonical(audit)),
        "audit": audit,
        "engine": audit.get("engine"),
        "model": audit.get("model"),
        "session_ref": audit.get("session_ref"),
        "base_id": audit.get("base_id"),
        "head_id": audit.get("head_id"),
        "lineage": audit.get("lineage"),
        "round": audit.get("round"),
        "plan_digest": audit.get("plan_digest"),
        "rendered_trailer": audit.get("rendered_trailer"),
        "structural_snapshot": audit.get("structural_snapshot"),
        "packet": packet,
        "packet_sha256": _sha(packet.encode("utf-8")),
        "plan_contract_reused": audit.get("plan_contract_reused"),
        "accepted_plan_anchors": anchors,
        "attempt_ledger": [_attempt(row) for row in audit.get("attempt_ledger", [])],
        "settlement": settlement,
        "lineage_state_canonical_sha256": _sha(_canonical(state)),
        "lineage_state": state,
    }


def validate_record(record: dict, root: Path = ROOT) -> None:
    if record.get("acceptance_kind") != "branch-plan-fidelity-public-handler-v1":
        raise ValueError("wrong acceptance kind")
    fixture = record.get("fixture") or {}
    if fixture.get("contract") != FIXTURE_CONTRACT:
        raise ValueError("fixture contract is not exact")
    if fixture.get("contract_sha256") != _sha(FIXTURE_CONTRACT.encode("utf-8")):
        raise ValueError("fixture contract digest mismatch")
    if fixture.get("deterministic_governing_identities") != [
        "contract-missing-obligation", "contract-entry-point-unexercised",
        "contract-undescribed-persistence",
    ]:
        raise ValueError("deterministic governing identities are not exact")
    revision = record.get("source_revision")
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("source revision is not a commit identity")
    source_inventory = record.get("source_sha256") or {}
    if set(source_inventory) != set(SOURCES):
        raise ValueError("source inventory is incomplete or contains unknown files")
    allowed_later = record.get("allowed_later_source_diffs") or {}
    changed: set[str] = set()
    for relative, expected in source_inventory.items():
        try:
            committed = subprocess.run(
                ["git", "show", f"{revision}:{relative}"], cwd=root, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ).stdout
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"source revision does not contain {relative}") from exc
        if _sha(committed) != expected:
            raise ValueError(f"acceptance commit hash mismatch: {relative}")
        if _sha((root / relative).read_bytes()) != expected:
            changed.add(relative)
            allowance = allowed_later.get(relative)
            if not isinstance(allowance, dict):
                raise ValueError(f"acceptance source hash mismatch: {relative}")
            diff = subprocess.run(
                ["git", "diff", "--no-ext-diff", revision, "--", relative],
                cwd=root, check=True, stdout=subprocess.PIPE,
            ).stdout
            if _sha(diff) != allowance.get("sha256"):
                raise ValueError(f"allowed later source diff mismatch: {relative}")
            if "does not alter branch plan-contract binding" not in str(
                allowance.get("scope", "")
            ):
                raise ValueError(f"allowed later source scope is incomplete: {relative}")
    if set(allowed_later) != changed:
        raise ValueError("allowed later source inventory is not exact")
    route_rows = record.get("routes", [])
    routes = _unique_rows(route_rows, "expected", "acceptance routes")
    if set(routes) != {"conforming", "nonconforming"}:
        raise ValueError("acceptance routes are not exact")
    contract = handlers._branch_contract_view(FIXTURE_CONTRACT)
    for expected, route in routes.items():
        audit = route.get("audit")
        state = route.get("lineage_state")
        if not isinstance(audit, dict) or not isinstance(state, dict):
            raise ValueError("embedded audit or lineage state is absent")
        if _sha(_canonical(audit)) != route.get("audit_canonical_sha256"):
            raise ValueError("embedded audit canonical digest mismatch")
        if _sha(_canonical(state)) != route.get("lineage_state_canonical_sha256"):
            raise ValueError("embedded lineage canonical digest mismatch")
        if route.get("plan_digest") != contract.digest:
            raise ValueError("route plan digest mismatch")
        authority = state.get("branch_contract")
        if authority != {
            "version": handlers.BRANCH_CONTRACT_VERSION,
            "present": True, "digest": contract.digest, "text": FIXTURE_CONTRACT,
        }:
            raise ValueError("lineage authority digest mismatch")
        projected = {
            "engine": audit.get("engine"), "model": audit.get("model"),
            "session_ref": audit.get("session_ref"), "base_id": audit.get("base_id"),
            "head_id": audit.get("head_id"), "lineage": audit.get("lineage"),
            "round": audit.get("round"), "plan_digest": audit.get("plan_digest"),
            "rendered_trailer": audit.get("rendered_trailer"),
            "structural_snapshot": audit.get("structural_snapshot"),
            "plan_contract_reused": audit.get("plan_contract_reused"),
            "settlement": audit.get("staged_settlement"),
        }
        if any(route.get(key) != value for key, value in projected.items()):
            raise ValueError("route projection does not match its audit")
        trailer = route.get("rendered_trailer")
        digest_line = f"PLAN-DIGEST: {contract.digest}"
        if not isinstance(trailer, str) or trailer.splitlines().count(digest_line) != 1:
            raise ValueError("public trailer does not contain the exact plan digest once")
        if (
            audit.get("tool") != "critique_branch"
            or audit.get("mode") != "converge-packet"
            or audit.get("plan_text") != FIXTURE_CONTRACT
            or audit.get("plan_path") is not None
            or audit.get("plan_contract_reused") is not False
            or audit.get("returncode") != 0
            or audit.get("error") is not False
        ):
            raise ValueError("audit is not the required successful public-handler route")
        review_state = state.get("review_state") or {}
        if (
            state.get("mode") != "branch"
            or state.get("rounds") != audit.get("round")
            or review_state.get("last_round") != audit.get("round")
            or review_state.get("snapshot_digest") != route.get("structural_snapshot")
        ):
            raise ValueError("lineage identity does not match its audit")
        packet = route.get("packet")
        if not isinstance(packet, str) or _sha(packet.encode("utf-8")) != route.get(
            "packet_sha256"
        ):
            raise ValueError("embedded packet digest mismatch")
        snapshot = handlers._branch_structural_snapshot(
            base_id=route["base_id"], head_id=route["head_id"], packet=packet,
            contract=contract,
        )
        if snapshot != route.get("structural_snapshot") or snapshot != audit.get(
            "structural_snapshot"
        ):
            raise ValueError("route structural snapshot mismatch")
        if route.get("accepted_plan_anchors") != _plan_anchors(
            audit.get("staged_manifests"), audit.get("staged_settlement"), state,
        ):
            raise ValueError("accepted plan anchors do not match lifecycle artifacts")
        attempts = route.get("attempt_ledger") or []
        if not attempts or attempts != [
            _attempt(row) for row in audit.get("attempt_ledger", [])
        ]:
            raise ValueError("attempt ledger projection mismatch")
        if [row.get("sequence") for row in attempts] != [1, 2, 3, 4] or [
            row.get("role") for row in attempts
        ] != [
            "census-behaviour", "census-execution", "census-integrity", "consolidation",
        ]:
            raise ValueError("attempt ledger does not describe one complete census")
        if attempts[-1].get("session_ref") != audit.get("session_ref"):
            raise ValueError("audit session does not name its terminal attempt")
        for attempt in attempts:
            for key in (
                "returncode", "requested_timeout_sec", "duration_ms", "usage",
                "response_sha256", "response_excerpt", "raw_sha256", "raw_excerpt",
                "failure_detail_sha256", "failure_detail_excerpt", "stderr_sha256",
                "stderr_excerpt", "session_ref",
            ):
                if attempt.get(key) is None:
                    raise ValueError(f"attempt telemetry missing {key}")
            if (
                attempt.get("engine") != route.get("engine")
                or attempt.get("outcome") != "completed"
                or attempt.get("returncode") != 0
            ):
                raise ValueError("attempt telemetry is not a completed route")
        settlement = audit.get("staged_settlement") or {}
        if route.get("settlement") != settlement:
            raise ValueError("route settlement does not match its audit")
        manifests = audit.get("staged_manifests")
        manifests_by_lane = _unique_rows(manifests, "lane", "staged manifests")
        if set(manifests_by_lane) != {"behaviour", "execution", "integrity"}:
            raise ValueError("staged manifests do not contain the exact census lanes")
        manifest_sources: dict[str, dict] = {}
        for lane, manifest in manifests_by_lane.items():
            for source_id, finding in _unique_rows(
                manifest.get("findings"), "id", f"{lane} manifest findings",
            ).items():
                if not source_id.startswith(f"{lane}:") or source_id in manifest_sources:
                    raise ValueError("staged manifests contain a duplicate or misbound source")
                manifest_sources[source_id] = finding
        settlement_debt = _unique_rows(settlement.get("debt"), "id", "settlement debt")
        durable_debt = _unique_rows(review_state.get("debt"), "id", "durable debt")
        if set(settlement_debt) != set(durable_debt):
            raise ValueError("settlement debt does not match durable lineage debt")
        source_ids_by_finding: dict[str, list[str]] = {}
        source_dispositions = _unique_rows(
            settlement.get("source_dispositions"), "source_id", "source dispositions",
        )
        if set(source_dispositions) != set(manifest_sources):
            raise ValueError("source dispositions do not exactly cover manifest findings")
        findings = _unique_rows(settlement.get("findings"), "id", "settlement findings")
        for row in source_dispositions.values():
            governing = findings.get(row.get("governing_id"))
            if governing is None:
                raise ValueError("source disposition names an unknown governing finding")
            source = manifest_sources[row["source_id"]]
            if not set(source.get("evidence", [])) & set(governing.get("evidence", [])):
                raise ValueError("source disposition has no evidence-traceable governing finding")
            source_ids_by_finding.setdefault(row.get("governing_id"), []).append(
                row.get("source_id")
            )
        disposition_by_finding = _unique_rows(
            settlement.get("class_dispositions"), "finding_id", "class dispositions",
        )
        if set(disposition_by_finding) != set(findings):
            raise ValueError("class dispositions do not exactly cover governing findings")
        classes = state.get("classes", [])
        for debt_id, debt in settlement_debt.items():
            durable = durable_debt[debt_id]
            if any(durable.get(key) != value for key, value in debt.items()):
                raise ValueError("settlement debt does not match durable lineage debt")
            if durable.get("first_round") != audit.get("round") or durable.get(
                "last_round"
            ) != audit.get("round"):
                raise ValueError("durable debt round binding is inconsistent")
            if durable.get("source_ids") != source_ids_by_finding.get(
                debt.get("finding_id"), []
            ):
                raise ValueError("durable debt source binding is inconsistent")
            disposition = disposition_by_finding.get(debt.get("finding_id")) or {}
            expected_classes: list[str] = []
            if disposition.get("kind") == "new_class":
                index = disposition.get("record_index")
                if not isinstance(index, int) or index >= len(classes):
                    raise ValueError("class disposition does not bind a durable class")
                expected_classes = [classes[index].get("class_id")]
            if durable.get("class_ids") != expected_classes:
                raise ValueError("durable debt class binding is inconsistent")
        for debt in settlement.get("debt", []):
            finding = findings.get(debt.get("finding_id"))
            if finding is None or any(
                debt.get(key) != finding.get(key)
                for key in ("severity", "evidence", "source_ids")
            ):
                raise ValueError("settlement debt is not bound to its governing finding")
        phase = review_state.get("phase")
        open_debt = [
            row for row in review_state.get("debt", [])
            if row.get("status") == "open"
        ]
        if expected == "conforming" and (phase != "clear" or open_debt):
            raise ValueError("conforming lineage is not clear")
        if expected == "nonconforming" and not open_debt:
            raise ValueError("nonconforming lineage has no open debt")
        if expected == "nonconforming":
            mappings = [
                sorted(set(row.get("evidence", [])) & {"plan:2", "plan:3", "plan:4"})
                for row in open_debt
            ]
            if sorted(mappings) != [["plan:2"], ["plan:3"], ["plan:4"]]:
                raise ValueError(
                    "real nonconforming route does not preserve three distinct semantic "
                    "plan obligations"
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nonconforming-audit", type=Path, required=True)
    parser.add_argument("--nonconforming-state", type=Path, required=True)
    parser.add_argument("--conforming-audit", type=Path, required=True)
    parser.add_argument("--conforming-state", type=Path, required=True)
    parser.add_argument("--fixture-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = {
        "acceptance_kind": "branch-plan-fidelity-public-handler-v1",
        "date": "2026-08-22",
        "production_entrypoint": "critique_branch",
        "fixture": {
            "contract": FIXTURE_CONTRACT,
            "contract_sha256": _sha(FIXTURE_CONTRACT.encode("utf-8")),
            "deterministic_governing_identities": [
                "contract-missing-obligation",
                "contract-entry-point-unexercised",
                "contract-undescribed-persistence",
            ],
            "provider_prose_and_response_local_ids_are_recorded_not_prescribed": True,
        },
        "provider": {
            "engine": "codex",
            "cli_version": subprocess.run(
                ["codex", "--version"], check=True, capture_output=True, text=True,
            ).stdout.strip(),
            "model": "gpt-5.6-sol",
            "effort": "high",
        },
        "source_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip(),
        "source_sha256": {
            relative: _sha((ROOT / relative).read_bytes()) for relative in SOURCES
        },
        "allowed_later_source_diffs": {},
        "routes": [
            _route(
                args.nonconforming_audit, args.nonconforming_state,
                "nonconforming", args.fixture_repo,
            ),
            _route(
                args.conforming_audit, args.conforming_state,
                "conforming", args.fixture_repo,
            ),
        ],
        "claims": {
            "proves": [
                "A signed-in Codex census accepted plan anchors and blocked a nonconforming branch.",
                "A separate signed-in Codex census cleared a genuinely conforming branch through critique_branch.",
                "Both routes used the production staged handler with immutable plan digests and retained attempt ledgers.",
                "Both public result trailers rendered the exact immutable plan digest once.",
            ],
            "does_not_prove": [
                "Every future provider response will classify implementation fidelity correctly.",
                "The acceptance fixture covers repository sizes or concurrency beyond the frozen local-tool stakes.",
                "Old unrelated acceptance artifacts remain source-current after this branch changes shared files.",
            ],
        },
    }
    if any(
        route["plan_digest"] != record["fixture"]["contract_sha256"]
        for route in record["routes"]
    ):
        raise ValueError("a real route did not use the exact four-line fixture contract")
    validate_record(record)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
