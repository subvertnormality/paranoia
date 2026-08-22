from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from email.message import Message
from pathlib import Path

import pytest

from paranoia_local import (
    class_closure as cc,
    external_sources,
    handlers,
    plan_claims as pc,
    prompts,
    review_census as rc,
)
from paranoia_local.engines import Review


PLAN = "# Rollout\n\nPython 3.11 was released in October 2022.\n"


def test_large_page_capture_acceptance_record() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact = json.loads(
        (root / "docs/large_page_capture_acceptance_2026-08-18.json").read_text()
    )
    assert artifact["acceptance_kind"] == "large-page-plan-claim-capture"
    assert artifact["runtime"]["model_calls"] == [
        "plan-evidence-discovery", "plan-evidence-binding", "plan-evidence-text",
        "arbitration-discovery", "arbitration-binding",
    ]
    assert artifact["runtime"]["validation_retries"] == 0
    assert artifact["direct_capture"]["extracted_characters"] == 70_378
    assert artifact["direct_capture"]["former_limit"] < 70_378
    assert artifact["direct_capture"]["current_limit"] >= 70_378
    assert artifact["verified_plan"]["verdict"] == "supported"
    assert artifact["verified_plan"]["blocked"] is False
    assert len(artifact["verified_plan"]["evidence"]) == 1
    assert all(
        row["publisher_authority"] and row["passage_entailment"]
        for row in artifact["verified_plan"]["evidence"]
    )
    assert artifact["arbitration_research"] == {
        "model_calls": ["arbitration-discovery", "arbitration-binding"],
        "claim_count": 5,
        "capture_count": 5,
        "bound_count": 5,
        "binding_budget_demotions": 0,
        "validation_retries": 0,
    }
    source_commit = artifact["source_commit"]
    for relative, expected in artifact["source_sha256"].items():
        content = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"], cwd=root,
            capture_output=True, check=True,
        ).stdout
        assert hashlib.sha256(content).hexdigest() == expected


def test_claim_discovery_timeout_public_acceptance_record() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact = json.loads(
        (root / "docs/claim_discovery_timeout_acceptance_2026-08-22.json").read_text()
    )
    audit = artifact["production_audit"]
    lineage = artifact["durable_lineage"]

    assert artifact["schema_version"] == 1
    expected_input = artifact["input"] | {
        "repository_revision": "c17c58e40dec7e660ec39f6d2a95e9f1d5ac1e7a",
        "path": "dataset/certification/A1-PIT-SYMBOL-RESOLUTION_plan_contract.md",
        "sha256": "706953595c48d12a0e421266b77bdf9c18cd1db2fd93b3ac7a1724b472a0b1f0",
        "bytes": 94_110,
        "lines": 1_606,
    }
    assert artifact["input"] == expected_input
    assert hashlib.sha256(
        artifact["input"]["text"].encode("utf-8", "surrogateescape")
    ).hexdigest() == artifact["input"]["sha256"]
    assert artifact["source"]["revision"] == "798092a1b0d346d22e81db2ac0287ae1cc31c469"
    assert artifact["source"]["clean_before_and_after"] is True
    assert artifact["source"]["diff"]["file_count"] == 10
    assert artifact["source"]["diff"]["additions"] == 3_328
    assert artifact["source"]["diff"]["deletions"] == 57
    assert artifact["source"]["module_lines"]["src/paranoia_local/handlers.py"] == 3_519
    for relative, expected_sha256 in artifact["source"]["hashes"].items():
        content = subprocess.run(
            ["git", "show", f'{artifact["source"]["revision"]}:{relative}'],
            cwd=root, check=True, stdout=subprocess.PIPE,
        ).stdout
        assert hashlib.sha256(content).hexdigest() == expected_sha256

    invocation = artifact["invocation"]
    assert invocation["public_handler"] == "paranoia_local.handlers.critique_plan"
    assert invocation["execution_route"] == "external-cli"
    assert invocation["cli_version_output"] == "codex-cli 0.149.0"
    assert invocation["model"] == "gpt-5.6-sol"
    assert invocation["source_revision_before"] == artifact["source"]["revision"]
    assert invocation["source_revision_after"] == artifact["source"]["revision"]
    assert invocation["source_status_before"] == invocation["source_status_after"] == ""
    assert invocation["elapsed_ms"] > invocation["claim_role_timeouts_seconds"]["claim-discovery"] * 1000
    assert invocation["result_text"] == artifact["observed"]["result_text"]
    assert invocation["claim_role_timeouts_seconds"] == {
        "claim-discovery": 600,
        "claim-discovery-validation-retry": 600,
        "claim-binding": 300,
        "claim-binding-validation-retry": 300,
        "claim-attestation": 300,
    }

    observed = artifact["observed"]
    assert observed["claim_duration_ms"] == audit["claim_duration_ms"] > 300_000
    assert observed["claim_model_calls"] == audit["claim_model_calls"] == 5
    assert observed["claim_status"].startswith("parsed ")
    assert observed["claim_counts"] == {"refuted": 1, "supported": 8, "unverified": 9}
    assert observed["ordered_attempt_roles"] == [
        "claim-discovery",
        "claim-discovery-validation-retry",
        "claim-binding",
        "claim-binding-validation-retry",
        "claim-attestation",
        "census-domain",
        "census-execution",
        "census-integrity",
        "consolidation",
    ]
    for row in audit["attempt_ledger"]:
        assert row["outcome"] in {"completed", "validation-invalid"}
        assert row["returncode"] in {None, 0}
        for channel in ("response", "raw", "failure_detail", "stderr"):
            assert f"{channel}_sha256" in row
            assert f"{channel}_excerpt" in row
            digest = row[f"{channel}_sha256"]
            assert digest is None or len(digest) == 64
    assert lineage["rounds"] == 1
    assert lineage["claim_state"]["rounds"] == 1
    assert len(lineage["claim_state"]["claims"]) == 18
    assert lineage["review_state"]["phase"] == "correction"
    assert observed["result_text"].endswith(
        "STAGED-ATTEMPTS: total=4 validation-retries=0 validation-invalid=0 execution-failed=0\n"
        "CONVERGENCE: BLOCKED — external claim closure remains open."
    )
    assert hashlib.sha256(
        observed["result_text"].encode("utf-8", "surrogateescape")
    ).hexdigest() == observed["result_sha256"]


def test_authoritative_capture_acceptance_record() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact = json.loads(
        (root / "docs/authoritative_capture_acceptance_2026-08-20.json").read_text()
    )
    assert "No exact-maximum provider transport guarantee" in artifact[
        "acceptance_claims"
    ]["does_not_claim"]
    assert artifact["source"]["extracted_characters"] > artifact["source"]["former_limit"]
    assert artifact["source"]["extracted_characters"] == 590_177
    assert {row["engine"] for row in artifact["routes"]} == {"codex", "claude"}
    for row in artifact["routes"]:
        assert handlers.MAX_PLAN_BINDING_BATCH_CHARS < row["binding_prompt_characters"]
        assert row["binding_prompt_characters"] <= handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS
        assert row["attestation_prompt_characters"] <= handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS
        assert row["fresh_binding_bootstrap"] and row["resumed_binding"]
        assert row["fresh_full_context_attestation"]
        assert len(row["binding_prompt_sha256"]) == 64
        assert len(row["binding_correction_prompt_sha256"]) == 64
        assert len(row["attestation_prompt_sha256"]) == 64
        assert len(row["bootstrap_reply_sha256"]) == 64
        assert len(row["binding_reply_sha256"]) == row["binding_calls"]
        assert all(len(value) == 64 for value in row["binding_reply_sha256"])
        assert all(len(value) == 64 for value in row["binding_raw_sha256"])
        assert len(row["attestation_raw_sha256"]) == 64
        assert row["publisher_authority"] and row["passage_entailment"]
        assert row["verdict"] == "supported"
    production = artifact["production_entrypoint"]
    assert production["public_handler"] == "critique_plan"
    assert production["ordinary_and_expanded_claims"] == 2
    assert production["supported_claims_after_reload"] == 2
    assert production["claim_debt"] is None
    assert production["spotify_capture_error"] is None
    assert production["spotify_publisher_authority"]
    assert production["spotify_passage_entailment"]
    assert production["durable_reload"]
    measured = artifact["production_preflight_measurement"]
    assert measured["attestation_correction_worst_case_characters"] <= (
        handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS
    )
    assert measured["configured_ceiling"] == handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS
    snapshot = artifact["reviewed_snapshot"]
    assert len(snapshot["base_commit"]) == 40
    source_commit = snapshot["source_commit"]
    for relative, expected in snapshot["production_source_sha256"].items():
        recorded = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"], cwd=root,
            check=True, stdout=subprocess.PIPE,
        ).stdout
        assert hashlib.sha256(recorded).hexdigest() == expected
        if relative not in {
            "src/paranoia_local/handlers.py", "src/paranoia_local/review_census.py",
        }:
            assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
    allowed = snapshot["allowed_later_handlers_diff"]
    handler_diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", source_commit, "--", "src/paranoia_local/handlers.py"],
        cwd=root, check=True, stdout=subprocess.PIPE,
    ).stdout
    assert hashlib.sha256(handler_diff).hexdigest() == allowed["sha256"]
    assert "does not alter capture, binding, cold-attestation" in allowed["scope"]
    census_allowed = snapshot["allowed_later_review_census_diff"]
    census_diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", source_commit, "--",
         "src/paranoia_local/review_census.py"],
        cwd=root, check=True, stdout=subprocess.PIPE,
    ).stdout
    assert hashlib.sha256(census_diff).hexdigest() == census_allowed["sha256"]
    assert census_allowed["scope"] == "Adds requested timeout to attempt telemetry only."
    production_diff = artifact["implementation_diff"]
    assert production_diff["largest_changed_module"] == "src/paranoia_local/handlers.py"
    assert production_diff["largest_changed_module_lines_after"] == 3415
    current_lines = sum(1 for _ in (root / "src/paranoia_local/handlers.py").open())
    assert current_lines == 3415 + allowed["additions"] - allowed["deletions"]


def test_minimal_claim_validation_acceptance_record() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact = json.loads(
        (root / "docs/minimal_claim_validation_acceptance_2026-08-18.json").read_text()
    )
    assert artifact["acceptance_kind"] == "minimal-claim-validation-diagnostics-v1"
    assert artifact["model_call_count"] == 2
    calls = artifact["provider_calls"]
    assert [call["role"] for call in calls] == [
        "evidence-discovery", "evidence-discovery",
    ]
    assert all(call["returncode"] == 0 and not call["error"] for call in calls)
    assert calls[0]["session_ref"] == calls[1]["session_ref"]
    debt = artifact["debt"]
    assert "initial: unexpected text after claim audit JSON" in debt["reason"]
    assert "correction: unexpected text after claim audit JSON" in debt["reason"]
    assert "reviewer failed" not in debt["reason"]
    assert debt["raw_sha256"] == artifact["expected_rejected_exchange_sha256"]
    assert artifact["caller_claim_audit_debt"] is True
    assert artifact["caller_convergence_blocked"] is True
    assert "CONVERGENCE: BLOCKED" in artifact["result_excerpt"]
    source = subprocess.run(
        ["git", "show", f'{artifact["source_commit"]}:src/paranoia_local/handlers.py'],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout
    assert "class _ValidationReview" in source


def _source(
    *,
    url: str = "https://www.python.org/downloads/release/python-3110/",
    kind: str = "primary",
    relation: str = "supports_claim",
    quote: str = "Python 3.11.0 was released on Monday, October 24, 2022.",
) -> dict[str, str]:
    return {
        "url": url,
        "title": "Python 3.11.0",
        "publisher": "Python Software Foundation",
        "source_kind": kind,
        "authority_basis": "The Python Software Foundation publishes Python releases.",
        "location": "Release page, first paragraph",
        "quote": quote,
        "relation": relation,
    }


def _claim(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "kind": "fact",
        "scope": "external",
        "anchor": "Python 3.11 was released in October 2022.",
        "proposition": "Python 3.11 was released in October 2022.",
        "prior_claim_id": None,
        "verdict": "supported",
        "evidence": [_source()],
        "replacement": None,
        "rationale": "The official release page directly gives the date.",
    }
    value.update(changes)
    return value


def _audit(
    *claims: dict[str, object], dispositions: list[dict[str, str]] | None = None,
    assessments: list[dict[str, str]] | None = None,
) -> str:
    payload = {
        "claims": list(claims),
        "coverage": {
            "sections_scanned": 1, "omitted_nonfacts": 1,
            "prior_assessments": assessments or [],
            "prior_dispositions": dispositions or [], "notes": "complete",
        },
    }
    return pc.AUDIT_MARKER + "\n" + json.dumps(payload)


class TestAuditValidation:
    def test_primary_exact_passage_can_support_an_atomic_fact(self) -> None:
        audit = pc.parse_audit(_audit(_claim()), PLAN)
        state = pc.reconcile(
            {}, audit, lineage_id="x-plan", round_no=1, plan_text=PLAN
        )
        assert not pc.is_blocked(state)
        assert next(iter(state["claims"].values()))["verdict"] == "supported"

    def test_verbatim_anchor_may_cross_markdown_line_wrapping(self) -> None:
        wrapped = "# Release\n\nPython 3.11 was released\nin October 2022.\n"
        claim = _claim(
            anchor="Python 3.11 was released in October 2022.",
            proposition="Python 3.11 was released in October 2022.",
        )
        assert len(pc.parse_audit(_audit(claim), wrapped).claims) == 1

    def test_reddit_is_never_upgraded_to_primary_by_model_output(self) -> None:
        reddit = _source(url="https://www.reddit.com/r/python/comments/x", kind="primary")
        claim = pc.parse_audit(_audit(_claim(evidence=[reddit])), PLAN).claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["evidence"][0]["source_kind"] == "ugc"

    @pytest.mark.parametrize("url", [
        "repo://docs/plan.md", "file:///tmp/evidence.txt", "custom://authority/item",
    ])
    def test_non_web_locations_cannot_govern_external_verdicts(self, url: str) -> None:
        source = _source(url=url, kind="primary")
        claim = pc.parse_audit(_audit(_claim(evidence=[source])), PLAN).claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["evidence"][0]["relation"] == "context"

    @pytest.mark.parametrize("url", [
        "https://github.com/example/project/blob/main/docs/plan.md",
        "https://raw.githubusercontent.com/example/project/main/docs/plan.md",
    ])
    def test_plan_repository_web_url_cannot_govern_its_own_claim(
        self, repo: Path, url: str,
    ) -> None:
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:example/project.git"],
            cwd=repo, check=True,
        )
        source = _source(url=url, kind="primary")
        claim = pc.parse_audit(
            _audit(_claim(evidence=[source])), PLAN,
            repo=repo, plan_repo_path="docs/plan.md",
        ).claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["evidence"][0]["relation"] == "context"

    def test_other_same_repository_web_page_is_not_mistaken_for_the_plan(
        self, repo: Path,
    ) -> None:
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/example/project.git"],
            cwd=repo, check=True,
        )
        source = _source(
            url="https://github.com/example/project/blob/main/docs/source.md",
            kind="primary",
        )
        claim = pc.parse_audit(
            _audit(_claim(evidence=[source])), PLAN,
            repo=repo, plan_repo_path="docs/plan.md",
        ).claims[0]
        assert claim["verdict"] == "supported"

    def test_changed_origin_is_used_for_self_source_classification(
        self, repo: Path,
    ) -> None:
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/example/project.git"],
            cwd=repo, check=True,
        )
        source = _source(
            url="https://github.com/example/project/blob/main/docs/plan.md",
            kind="primary",
        )
        first = pc.parse_audit(
            _audit(_claim(evidence=[source])), PLAN,
            repo=repo, plan_repo_path="docs/plan.md",
        ).claims[0]
        subprocess.run(
            ["git", "remote", "set-url", "origin", "https://github.com/example/other.git"],
            cwd=repo, check=True,
        )
        second = pc.parse_audit(
            _audit(_claim(evidence=[source])), PLAN,
            repo=repo, plan_repo_path="docs/plan.md",
        ).claims[0]
        assert first["verdict"] == "unverified"
        assert second["verdict"] == "supported"

    def test_persisted_plan_self_evidence_cannot_freeze_after_upgrade(
        self, repo: Path,
    ) -> None:
        self_source = _source(
            url="https://github.com/example/project/blob/main/docs/plan.md",
            kind="primary",
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(evidence=[self_source])), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:example/project.git"],
            cwd=repo, check=True,
        )
        assert not pc.frozen_supported_ids(
            first, PLAN, repo=repo, plan_repo_path="docs/plan.md",
        )

    def test_persisted_plan_self_evidence_cannot_govern_compact_assessment(
        self, repo: Path,
    ) -> None:
        self_source = _source(
            url="https://github.com/example/project/blob/main/docs/plan.md",
            kind="primary", relation="refutes_claim",
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(
                verdict="refuted", evidence=[self_source],
            )), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:example/project.git"],
            cwd=repo, check=True,
        )
        with pytest.raises(pc.AuditError, match="compact assessments cannot cross"):
            pc.parse_audit(_audit(assessments=[{
                "claim_id": claim_id, "verdict": "refuted",
                "rationale": "The old packet still contradicts the claim.",
            }]), PLAN)

    def test_context_only_support_is_demoted_without_discarding_other_claims(self) -> None:
        context_only = _source(relation="context")
        audit = pc.parse_audit(_audit(
            _claim(evidence=[context_only]),
            _claim(proposition="Python 3.11 became available in October 2022."),
        ), PLAN)
        assert [claim["verdict"] for claim in audit.claims] == ["unverified", "supported"]
        assert "Server demotion" in audit.claims[0]["rationale"]

    def test_fresh_repository_scope_enters_correction_instead_of_disappearing(self) -> None:
        with pytest.raises(pc.AuditError, match="repository/internal assertions"):
            pc.parse_audit(_audit(_claim(scope="repository")), PLAN)

    def test_unknown_scope_typo_is_not_silently_discarded(self) -> None:
        with pytest.raises(pc.AuditError, match='scope must be the literal \\"external\\"'):
            pc.parse_audit(_audit(_claim(scope="externl")), PLAN)

    @pytest.mark.parametrize("kind", ["fact", "design_principle", "behavior"])
    def test_all_external_claim_kinds_are_eligible(self, kind: str) -> None:
        claim = pc.parse_audit(_audit(_claim(kind=kind)), PLAN).claims[0]
        assert claim["kind"] == kind
        assert claim["scope"] == "external"

    def test_refutation_alone_keeps_packet_but_drops_unsupported_replacement(self) -> None:
        refuting = _source(relation="refutes_claim")
        audit = pc.parse_audit(_audit(_claim(
            verdict="refuted", evidence=[refuting],
            replacement="Python 3.11 was released on 24 October 2022.",
        )), PLAN)
        assert audit.claims[0]["verdict"] == "refuted"
        assert audit.claims[0]["evidence"][0]["relation"] == "refutes_claim"
        assert audit.claims[0]["replacement"] is None

    def test_decisions_never_enter_active_inventory(self) -> None:
        with pytest.raises(pc.AuditError, match="kind must be one of"):
            pc.parse_audit(_audit(_claim(kind="decision")), PLAN)

    def test_the_incident_pseudo_enum_is_rejected_with_bounded_raw_diagnostics(self) -> None:
        raw = _audit(_claim(kind="fact|decision"))
        with pytest.raises(pc.AuditError) as caught:
            pc.parse_audit(raw, PLAN)
        assert "fact|decision" in caught.value.excerpt
        assert len(caught.value.excerpt) <= pc.DIAGNOSTIC_CHARS + 40
        assert len(caught.value.raw_sha256) == 64

    def test_final_retry_localizes_bad_anchor_and_retains_valid_packets(self) -> None:
        bad = _claim(anchor="This wording is not in the plan.")
        audit = pc.parse_audit(_audit(bad, _claim()), PLAN, allow_partial=True)
        state = pc.reconcile(
            {}, audit, lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        assert len(state["claims"]) == 1
        assert next(iter(state["claims"].values()))["verdict"] == "supported"
        assert "localized invalid claim" in state["debt"]["reason"]
        assert "This wording is not in the plan" in state["debt"]["rejected_excerpt"]
        assert pc.is_blocked(state)

    def test_disposition_rationale_wire_alias_is_normalized_to_reason(self) -> None:
        audit = pc.parse_audit(_audit(
            _claim(),
            dispositions=[{
                "claim_id": "C-old", "disposition": "removed",
                "rationale": "The old exact wording is absent.",
            }],
        ), PLAN)
        assert audit.dispositions == ({
            "claim_id": "C-old", "disposition": "removed",
            "reason": "The old exact wording is absent.",
        },)

    def test_disposition_prior_claim_id_wire_alias_is_normalized(self) -> None:
        audit = pc.parse_audit(_audit(
            _claim(),
            dispositions=[{
                "prior_claim_id": "C-old", "disposition": "removed",
                "rationale": "The old exact wording is absent.",
            }],
        ), PLAN)
        assert audit.dispositions == ({
            "claim_id": "C-old", "disposition": "removed",
            "reason": "The old exact wording is absent.",
        },)

    def test_disposition_ignores_harmless_model_metadata(self) -> None:
        audit = pc.parse_audit(_audit(
            _claim(),
            dispositions=[{
                "claim_id": "C-old", "disposition": "removed",
                "reason": "The old exact wording is absent.",
                "anchor": "Old wording from the prior plan.",
            }],
        ), PLAN)
        assert audit.dispositions == ({
            "claim_id": "C-old", "disposition": "removed",
            "reason": "The old exact wording is absent.",
        },)

    @pytest.mark.parametrize("extra", [
        {"prior_claim_id": "C-other"},
        {"rationale": "A second reason."},
    ])
    def test_disposition_still_rejects_ambiguous_wire_aliases(
        self, extra: dict[str, str],
    ) -> None:
        item = {
            "claim_id": "C-old", "disposition": "removed",
            "reason": "The old exact wording is absent.",
            **extra,
        }
        with pytest.raises(pc.AuditError, match="must contain one claim ID"):
            pc.parse_audit(_audit(_claim(), dispositions=[item]), PLAN)

    @pytest.mark.parametrize("field", ["prior_dispositions", "prior_assessments"])
    def test_governing_coverage_arrays_are_required(self, field: str) -> None:
        payload = json.loads(_audit(_claim()).split("\n", 1)[1])
        del payload["coverage"][field]
        raw = pc.AUDIT_MARKER + "\n" + json.dumps(payload)
        with pytest.raises(pc.AuditError, match=rf"coverage\.{field} is required"):
            pc.parse_audit(raw, PLAN)

    def test_null_disposition_reason_is_a_recoverable_audit_error(self) -> None:
        payload = json.loads(_audit(_claim()).split("\n", 1)[1])
        payload["coverage"]["prior_dispositions"] = [{
            "claim_id": "C-old",
            "disposition": "removed",
            "reason": None,
        }]
        raw = pc.AUDIT_MARKER + "\n" + json.dumps(payload)
        with pytest.raises(pc.AuditError, match="must be a non-empty string"):
            pc.parse_audit(raw, PLAN)


class TestRetainedEvidence:
    def test_corrected_wording_gets_new_identity_and_re_entails_retained_evidence(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        corrected_plan = "# Rollout\n\nPython 3.11 was released on 24 October 2022.\n"
        corrected = _claim(
            anchor="Python 3.11 was released on 24 October 2022.",
            proposition="Python 3.11 was released on 24 October 2022.",
            prior_claim_id=claim_id,
            verdict="unverified",
            evidence=[_source(relation="context")],
        )
        second = pc.reconcile(
            first, pc.parse_audit(_audit(corrected, dispositions=[{
                "claim_id": claim_id, "disposition": "removed",
                "reason": "The old date wording was replaced by the corrected assertion.",
            }]), corrected_plan),
            lineage_id="x-plan", round_no=2, plan_text=corrected_plan,
        )
        replacement_id = next(iter(second["claims"]))
        assert replacement_id != claim_id
        assert pc.is_blocked(second)
        assert second["retired"][-1]["claim_id"] == claim_id
        prompt = pc.audit_instructions(corrected_plan, first, "trusted local tool")
        assert claim_id in prompt and _source()["url"] in prompt
        assert "ABSENT PRIOR ANCHOR CANDIDATES" in prompt
        assert json.dumps({"claim_id": claim_id, "anchor": _claim()["anchor"]},
                          separators=(",", ":")) in prompt

    def test_wrapped_anchor_is_not_a_removal_candidate(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        wrapped = "# Rollout\n\nPython 3.11 was released\nin October 2022.\n"
        prompt = pc.audit_instructions(wrapped, first, "trusted local tool")
        assert "ABSENT PRIOR ANCHOR CANDIDATES (JSON):\n[]" in prompt

    def test_removed_claims_are_retired_and_do_not_consume_active_inventory(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        second = pc.reconcile(
            first, pc.parse_audit(_audit(dispositions=[{
                "claim_id": claim_id, "disposition": "removed",
                "reason": "The release-date assertion is absent from the edited plan.",
            }]), "# Rollout\n\nUse Python.\n"),
            lineage_id="x-plan", round_no=2, plan_text="# Rollout\n\nUse Python.\n",
        )
        assert second["claims"] == {}
        assert len(second["retired"]) == 1
        assert not pc.is_blocked(second)
        assert "1 retired and excluded from active inventory" in pc.render_trailer(second)

    def test_model_omission_is_rejected_when_a_claim_is_not_frozen(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        with pytest.raises(pc.AuditError, match=claim_id):
            pc.reconcile(
                first, pc.parse_audit(_audit(), PLAN),
                lineage_id="x-plan", round_no=2, plan_text=PLAN,
            )

    def test_final_retry_localizes_a_missing_retained_claim(self) -> None:
        sqlite = "SQLite 3.45.0 was released on 15 January 2024."
        plan = PLAN + sqlite + "\n"
        refuting = [_source(relation="refutes_claim")]
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(
                _claim(verdict="refuted", evidence=refuting),
                _claim(
                    anchor=sqlite, proposition=sqlite, verdict="refuted",
                    evidence=refuting,
                ),
            ), plan),
            lineage_id="x-plan", round_no=1, plan_text=plan,
        )
        python_id = next(
            claim_id for claim_id, claim in first["claims"].items()
            if claim["proposition"].startswith("Python")
        )
        sqlite_id = next(claim_id for claim_id in first["claims"] if claim_id != python_id)
        retry = pc.parse_audit(_audit(_claim(
            verdict="refuted", evidence=refuting, prior_claim_id=python_id,
        )), plan)

        second = pc.reconcile(
            first, retry, lineage_id="x-plan", round_no=2, plan_text=plan,
            allow_missing=True,
        )

        assert second["claims"][python_id]["verdict"] == "refuted"
        assert second["claims"][sqlite_id]["verdict"] == "unverified"
        assert "omitted this prior claim" in second["claims"][sqlite_id]["rationale"]
        assert second["debt"] is None

    def test_supported_exact_claim_is_frozen_out_of_targeted_inventory(
        self, tmp_path: Path,
    ) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        frozen = pc.frozen_supported_ids(first, PLAN, repo=tmp_path)
        assert frozen == {claim_id}
        prompt = pc.targeted_audit_instructions(PLAN, first, "trusted local tool", frozen)
        assert claim_id not in prompt
        assert "(no textual changes)" in prompt
        second = pc.reconcile(
            first, pc.parse_audit(_audit(), PLAN),
            lineage_id="x-plan", round_no=2, plan_text=PLAN, frozen_ids=frozen,
        )
        assert second["claims"][claim_id]["verified_round"] == 1
        assert second["claims"][claim_id]["retained_round"] == 2
        assert not pc.is_blocked(second)

    @pytest.mark.parametrize("changed", [
        '# Rollout\n\nThe statement "Python 3.11 was released in October 2022." is rejected.\n',
        '# Rollout\n\nPython 3.11 was not released in October 2022.\n',
        '# Quotation\n\n> Python 3.11 was released in October 2022.\n',
        '# Example\n\n```text\nPython 3.11 was released in October 2022.\n```\n',
        '# Historical notes\n\nPython 3.11 was released in October 2022.\n',
    ])
    def test_changed_assertion_context_is_not_frozen(self, changed: str) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        assert not pc.frozen_supported_ids(first, changed)

    def test_adjacent_retraction_in_the_same_block_forces_reverification(self) -> None:
        original = (
            PLAN.rstrip() + " The official release date governs this rollout.\n"
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), original),
            lineage_id="x-plan", round_no=1, plan_text=original,
        )
        retracted = (
            PLAN.rstrip() + " This statement is false and must not be relied on.\n"
        )
        assert not pc.frozen_supported_ids(first, retracted)

    def test_setext_heading_relocation_forces_reverification(self) -> None:
        original = (
            "Rollout\n=======\n\nPython 3.11 was released in October 2022.\n"
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), original),
            lineage_id="x-plan", round_no=1, plan_text=original,
        )
        relocated = (
            "Historical notes\n================\n\n"
            "Python 3.11 was released in October 2022.\n"
        )
        assert not pc.frozen_supported_ids(first, relocated)

    def test_indented_code_occurrence_cannot_freeze_asserted_prose(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        code_only = (
            "# Rollout\n\n    Python 3.11 was released in October 2022.\n"
        )
        assert not pc.frozen_supported_ids(first, code_only)

    @pytest.mark.parametrize("relocated", [
        '# A\n\n## B\n\nPython 3.11 was released in October 2022.\n',
        '# A / B\n\nPython 3.11 was released in October 2022.\n',
    ])
    def test_heading_structure_collisions_force_reverification(self, relocated: str) -> None:
        original = (
            '# A\n\n### B\n\nPython 3.11 was released in October 2022.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), original),
            lineage_id="x-plan", round_no=1, plan_text=original,
        )
        assert not pc.frozen_supported_ids(first, relocated)

    def test_list_parent_cannot_be_lost_from_assertion_identity(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        rejected_list = (
            '# Rollout\n\n- The following claim is rejected:\n'
            '  Python 3.11 was released in October 2022.\n'
        )
        assert not pc.frozen_supported_ids(first, rejected_list)

    def test_nested_assertion_cannot_move_between_list_parents(self) -> None:
        original = (
            '# Rollout\n\n- Accepted premises:\n'
            '  - Python 3.11 was released in October 2022.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), original),
            lineage_id="x-plan", round_no=1, plan_text=original,
        )
        rejected = (
            '# Rollout\n\n- Rejected premises:\n'
            '  - Python 3.11 was released in October 2022.\n'
        )
        assert not pc.frozen_supported_ids(first, rejected)

    def test_unchanged_list_assertion_can_reuse_its_packet(self) -> None:
        listed = (
            '# Rollout\n\n- Python 3.11 was released in October 2022.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), listed),
            lineage_id="x-plan", round_no=1, plan_text=listed,
        )
        assert pc.frozen_supported_ids(first, listed) == set(first["claims"])

    def test_reflowed_list_assertion_can_reuse_its_packet(self) -> None:
        listed = (
            '# Rollout\n\n- Python 3.11 was released in\n'
            '  October 2022. A second sentence stays in the item.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), listed),
            lineage_id="x-plan", round_no=1, plan_text=listed,
        )
        reflowed = (
            '# Rollout\n\n- Python 3.11 was released in October 2022.\n'
            '  A second sentence stays in the item.\n'
        )
        assert pc.frozen_supported_ids(first, reflowed) == set(first["claims"])

    def test_duplicate_assertion_and_quotation_cannot_freeze_ambiguously(self) -> None:
        mixed = (
            PLAN + '\n## Quotation\n\n'
            '> Python 3.11 was released in October 2022.\n'
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), mixed),
            lineage_id="x-plan", round_no=1, plan_text=mixed,
        )
        quotation_only = (
            '# Rollout\n\nThe assertion was removed.\n\n## Quotation\n\n'
            '> Python 3.11 was released in October 2022.\n'
        )
        assert not pc.frozen_supported_ids(first, quotation_only)

    def test_nonfreezable_claim_rejects_compact_support(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        quoted = (
            '# Rollout\n\nThe statement "Python 3.11 was released in October 2022." '
            'is rejected.\n'
        )
        with pytest.raises(pc.AuditError, match="compact assessments cannot cross"):
            pc.parse_audit(_audit(assessments=[{
                "claim_id": claim_id, "verdict": "supported",
                "rationale": "The old packet is unchanged.",
            }]), quoted)

    def test_markdown_wrapping_keeps_the_same_assertion_binding(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        wrapped = "# Rollout\n\nPython 3.11 was released\nin October 2022.\n"
        assert pc.frozen_supported_ids(first, wrapped) == set(first["claims"])

    def test_failed_targeted_audit_does_not_invalidate_frozen_support(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        failed = pc.with_debt(
            first, pc.AuditError("edited successor audit failed"),
            round_no=2, plan_text=PLAN, frozen_ids={claim_id},
        )
        assert failed["claims"][claim_id]["verdict"] == "supported"
        assert failed["debt"]["reason"] == "edited successor audit failed"
        assert pc.is_blocked(failed)

    def test_targeted_audit_cannot_reemit_a_frozen_claim(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        with pytest.raises(pc.AuditError, match="frozen claims were re-emitted"):
            pc.reconcile(
                first, pc.parse_audit(_audit(_claim()), PLAN),
                lineage_id="x-plan", round_no=2, plan_text=PLAN,
                frozen_ids={claim_id},
            )

    def test_targeted_round_verifies_edited_successor_and_freezes_unchanged_claim(self) -> None:
        sqlite_old = "SQLite 3.45.0 was released on 15 January 2024."
        first_plan = PLAN + "\n" + sqlite_old + "\n"
        sqlite_claim = _claim(anchor=sqlite_old, proposition=sqlite_old)
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(), sqlite_claim), first_plan),
            lineage_id="x-plan", round_no=1, plan_text=first_plan,
        )
        python_id = next(
            claim_id for claim_id, claim in first["claims"].items()
            if claim["proposition"].startswith("Python")
        )
        sqlite_id = next(claim_id for claim_id in first["claims"] if claim_id != python_id)
        sqlite_new = "SQLite 3.45.0 was released on 15 January 2025."
        second_plan = PLAN + "\n" + sqlite_new + "\n"
        frozen = pc.frozen_supported_ids(first, second_plan)
        assert frozen == {python_id}
        prompt = pc.targeted_audit_instructions(
            second_plan, first, "trusted local tool", frozen,
        )
        assert python_id not in prompt
        assert sqlite_id in prompt
        assert "-SQLite 3.45.0 was released on 15 January 2024." in prompt
        assert "+SQLite 3.45.0 was released on 15 January 2025." in prompt

        successor = _claim(anchor=sqlite_new, proposition=sqlite_new)
        audit = pc.parse_audit(_audit(successor, dispositions=[{
            "claim_id": sqlite_id, "disposition": "removed",
            "reason": "The old SQLite date wording was replaced.",
        }]), second_plan)
        second = pc.reconcile(
            first, audit, lineage_id="x-plan", round_no=2,
            plan_text=second_plan, frozen_ids=frozen,
        )
        assert second["claims"][python_id]["verified_round"] == 1
        assert sqlite_id not in second["claims"]
        assert any(item["claim_id"] == sqlite_id for item in second["retired"])
        assert len(second["claims"]) == 2

    def test_compact_assessment_cannot_bypass_current_capture_for_refutation(self) -> None:
        refuting = [_source(relation="refutes_claim")]
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(
                verdict="refuted", evidence=refuting,
            )), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        with pytest.raises(pc.AuditError, match="compact assessments cannot cross"):
            pc.parse_audit(_audit(assessments=[{
                "claim_id": claim_id,
                "verdict": "refuted",
                "rationale": "The retained official passage still contradicts the exact claim.",
            }]), PLAN)

    def test_legacy_repository_claims_are_mechanically_retired(self) -> None:
        legacy = pc.empty_state()
        legacy["claims"] = {
            "C-repo": {
                "kind": "fact", "scope": "repository",
                "anchor": "The setting is enabled.",
                "proposition": "The repository setting is enabled.",
                "verdict": "supported", "evidence": [],
            },
            "C-external": {
                **_claim(), "claim_id": "C-external",
            },
        }

        normalized = pc.normalize_state(legacy)

        assert set(normalized["claims"]) == {"C-external"}
        assert normalized["retired"][-1]["claim_id"] == "C-repo"
        assert normalized["retired"][-1]["disposition"] == "out_of_scope"

    def test_parent_schema_with_unresolved_claims_migrates_to_blocking_debt(self) -> None:
        legacy = {
            "next_seq": 4,
            "claims": [{
                "claim_id": "a" * 32,
                "claim": "An external premise remains unresolved.",
                "status": "UNVERIFIED",
            }],
            "debt": None,
            "evidence_records": [],
            "plan_sha256": "b" * 64,
            "authorization_policy": None,
        }
        normalized = pc.normalize_state(legacy)
        assert pc.is_blocked(normalized)
        assert normalized["claims"] == {}
        assert "1 active predecessor" in normalized["debt"]["reason"]
        assert "a" * 32 in normalized["debt"]["reason"]
        assert not pc.has_prior_snapshot(normalized)

    def test_targeted_prompt_requires_full_packet_for_unverified_claim(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(verdict="unverified", evidence=[])), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))

        prompt = pc.targeted_audit_instructions(PLAN, first, "trusted local tool", set())

        assert "RETAINED CLAIMS REQUIRING FULL EVIDENCE PACKETS" in prompt
        assert claim_id in prompt
        assert '"prior_assessments":[]' in prompt
        assert "Mechanically OMIT repository state" in prompt

    def test_prompts_include_external_principles_and_behaviors_but_exclude_repo_claims(
        self,
    ) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )

        exhaustive = pc.audit_instructions(PLAN, {}, "trusted local tool")
        targeted = pc.targeted_audit_instructions(PLAN, first, "trusted local tool", set())
        retry = pc.retry_instructions(
            pc.AuditError("bad packet"), PLAN, first,
        )

        for prompt in (exhaustive, targeted, retry):
            assert "design_principle" in prompt
            assert "behavior" in prompt
            assert "repository" in prompt.lower()
            assert "structural" in prompt and "review" in prompt
        assert "Every claim has scope `external`" in exhaustive
        assert '"scope":"external"' in targeted
        assert 'Allowed scope: "external"' in targeted

    def test_prompts_preserve_report_event_and_chronology(self) -> None:
        exhaustive = pc.audit_instructions(PLAN, {}, "trusted local tool")
        targeted = pc.targeted_audit_instructions(PLAN, {}, "trusted local tool", set())

        for prompt in (exhaustive, targeted):
            assert "audit/report" in prompt
            assert "underlying" in prompt
            assert "chronology" in prompt

    def test_compact_support_cannot_upgrade_a_nonqualifying_retained_packet(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim(evidence=[_source(relation="context")])), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        claim_id = next(iter(first["claims"]))
        with pytest.raises(pc.AuditError, match="compact assessments cannot cross"):
            pc.parse_audit(_audit(assessments=[{
                "claim_id": claim_id,
                "verdict": "supported",
                "rationale": "The old context still looks plausible.",
            }]), PLAN)

    def test_unrelated_prior_id_cannot_replace_the_old_claim(self) -> None:
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        old_id = next(iter(first["claims"]))
        expanded_plan = PLAN + "SQLite 3.45.0 was released on 15 January 2024.\n"
        unrelated = _claim(
            anchor="SQLite 3.45.0 was released on 15 January 2024.",
            proposition="SQLite 3.45.0 was released on 15 January 2024.",
            prior_claim_id=old_id,
        )
        second = pc.reconcile(
            first, pc.parse_audit(_audit(unrelated), expanded_plan),
            lineage_id="x-plan", round_no=2, plan_text=expanded_plan,
            frozen_ids={old_id},
        )
        assert old_id in second["claims"]
        assert second["claims"][old_id]["verdict"] == "supported"
        assert len(second["claims"]) == 2
        assert not pc.is_blocked(second)

    def test_opposite_punctuation_propositions_never_share_identity(self) -> None:
        old_plan = "# Check\n\nThe values satisfy A != B.\n"
        old_claim = _claim(
            anchor="The values satisfy A != B.",
            proposition="The values satisfy A != B.",
        )
        first = pc.reconcile(
            {}, pc.parse_audit(_audit(old_claim), old_plan),
            lineage_id="x-plan", round_no=1, plan_text=old_plan,
        )
        old_id = next(iter(first["claims"]))
        both_plan = old_plan + "The values satisfy A == B.\n"
        opposite = _claim(
            anchor="The values satisfy A == B.",
            proposition="The values satisfy A == B.",
            prior_claim_id=old_id,
        )
        second = pc.reconcile(
            first, pc.parse_audit(_audit(opposite), both_plan),
            lineage_id="x-plan", round_no=2, plan_text=both_plan,
            frozen_ids={old_id},
        )
        assert old_id in second["claims"]
        assert second["claims"][old_id]["verdict"] == "supported"
        assert len(second["claims"]) == 2

    def test_nonfactual_is_not_an_accepted_disposition(self) -> None:
        with pytest.raises(pc.AuditError, match="must be removed"):
            pc.parse_audit(_audit(dispositions=[{
                "claim_id": "C-old", "disposition": "nonfactual",
                "reason": "The model changed its mind.",
            }]), PLAN)

    def test_structural_context_contains_full_evidence_for_independent_audit(self) -> None:
        state = pc.reconcile(
            {}, pc.parse_audit(_audit(_claim()), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        context = pc.review_context(state)
        source = _source()
        assert source["url"] in context
        assert source["quote"] in context
        assert source["authority_basis"] in context
        assert "function-to-function bridges" in context
        assert "Do not demand claim packets for repository state" in context
        assert "omitted load-bearing factual assertion" not in context

    def test_action_packet_returns_exact_passage_and_location(self) -> None:
        refuted = _claim(
            verdict="refuted",
            evidence=[
                _source(relation="refutes_claim", quote="The release date was October 24, 2022."),
                _source(relation="supports_replacement", quote="The release date was October 24, 2022."),
            ],
            replacement="Python 3.11 was released on 24 October 2022.",
        )
        state = pc.reconcile(
            {}, pc.parse_audit(_audit(refuted), PLAN),
            lineage_id="x-plan", round_no=1, plan_text=PLAN,
        )
        packet = pc.render_trailer(state)
        assert "Evidence-entailed replacement" in packet
        assert "Release page, first paragraph" in packet
        assert "The release date was October 24, 2022." in packet


class ScriptedEngine:
    name = "codex"
    default_model = "test-model"
    native_web = True

    def __init__(self, *outputs: object) -> None:
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def run(self, prompt, cwd, model, effort, web_search, **kwargs):
        self.prompts.append(prompt)
        output = self.outputs.pop(0)
        if isinstance(output, Review):
            return output
        return Review(text=str(output), session_ref="session", raw="")

    def resume(self, session_ref, prompt, cwd, model, effort, web_search, **kwargs):
        self.prompts.append(prompt)
        output = self.outputs.pop(0)
        if isinstance(output, Review):
            return output
        return Review(text=str(output), session_ref=session_ref, raw="")


STRUCTURAL_CLEAR = """## What works
Nothing notable.
## What doesn't work
CONVERGED — no blocking findings at this round.
## Risks
Nothing notable.
## Gaps
Nothing notable.
## Improvements
Nothing notable.

=== CLASS REGISTER ===
NONE"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


class TestHandlerFlow:
    def test_exhausted_discovery_validation_preserves_both_reasons_and_raw(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        initial = _audit(_claim()) + "\nunexpected source list"
        correction = _audit(_claim(
            anchor="This corrected anchor is absent.",
            proposition="This corrected anchor is absent.",
        ))
        engine = _RoleScript({"evidence-discovery": [initial, correction]})
        monkeypatch.setattr(handlers.eng, "CodexEngine", _RoleScript)

        state, status = handlers._verify_plan_claims(
            PLAN, pc.empty_state(), lineage_id="validation-diagnostic", round_no=1,
            stakes="trusted local tool", engine=engine, repo=_repo(tmp_path),
            model="m", effort="high", plan_repo_path=None, on_progress=None,
        )

        debt = state["debt"]
        expected_raw = (
            "evidence-discovery\n--- discovery correction ---\nevidence-discovery"
        )
        assert status == "validation-invalid"
        assert "initial: unexpected text after claim audit JSON" in debt["reason"]
        assert "correction: claim 0: anchor is not a verbatim substring" in debt["reason"]
        assert "reviewer failed" not in debt["reason"]
        assert debt["returncode"] == 0
        assert debt["raw_sha256"] == hashlib.sha256(expected_raw.encode()).hexdigest()
        assert debt["rejected_excerpt"] == expected_raw

    def test_returncode_zero_provider_error_keeps_execution_wording(
        self, tmp_path: Path,
    ) -> None:
        failure = Review(
            "provider rejected request", "session", "provider envelope",
            returncode=0, error=True, failure_detail="in-band provider error",
        )

        state, status = handlers._verify_plan_claims(
            PLAN, pc.empty_state(), lineage_id="provider-error", round_no=1,
            stakes="trusted local tool", engine=ScriptedEngine(failure),
            repo=_repo(tmp_path), model="m", effort="high", plan_repo_path=None,
            on_progress=None,
        )

        assert status == "failed"
        assert state["debt"]["reason"] == "claim-audit reviewer failed (exit 0)"
        assert state["debt"]["failure_detail"] == "in-band provider error"

    @pytest.mark.parametrize(("returncode", "diagnostic"), [
        (124, "timed out after 3600s"),
        (127, "executable not found: codex"),
    ])
    def test_outer_claim_retry_persists_all_failure_channels(
        self, tmp_path: Path, returncode: int, diagnostic: str,
    ) -> None:
        failed = Review(
            text="partial", session_ref="session", raw="retry stdout",
            returncode=returncode, error=True,
            failure_detail="structured provider failure", stderr=diagnostic,
        )
        state, status = handlers._verify_plan_claims(
            PLAN, pc.empty_state(), lineage_id="outer-retry", round_no=1,
            stakes="trusted local tool",
            engine=ScriptedEngine("not a claim audit", failed),
            repo=_repo(tmp_path), model="m", effort="high", plan_repo_path=None,
            on_progress=None,
        )

        assert status == "retry-failed"
        debt = state["debt"]
        assert debt["returncode"] == returncode
        assert debt["rejected_excerpt"] == "retry stdout"
        assert debt["failure_detail"] == "structured provider failure"
        assert debt["stderr"] == diagnostic
        assert len({debt["raw_sha256"], debt["failure_detail_sha256"],
                    debt["stderr_sha256"]}) == 3

    def test_invalid_disposition_scalar_gets_one_correction_and_recovers(
        self, tmp_path: Path,
    ) -> None:
        invalid = _audit(_claim(), dispositions=[{
            "claim_id": "C-old", "disposition": "removed", "reason": None,
        }])
        engine = ScriptedEngine(invalid, _audit(_claim()), STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "lineage": "scalar-retry-plan", "round": 1,
                "stakes": "trusted local tool; convergence correctness matters",
            },
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        assert len(engine.prompts) == 3
        assert "disposition.reason must be a non-empty string" in engine.prompts[1]
        assert "CONVERGENCE: NOT-BLOCKED" in out

    def test_missing_governing_array_twice_becomes_blocking_debt(
        self, tmp_path: Path,
    ) -> None:
        payload = json.loads(_audit(_claim()).split("\n", 1)[1])
        del payload["coverage"]["prior_dispositions"]
        invalid = pc.AUDIT_MARKER + "\n" + json.dumps(payload)
        engine = ScriptedEngine(invalid, invalid, STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "lineage": "missing-array-plan", "round": 1,
                "stakes": "trusted local tool; convergence correctness matters",
            },
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        assert len(engine.prompts) == 3
        assert "coverage.prior_dispositions is required" in engine.prompts[1]
        assert "CLAIM-AUDIT-DEBT: round 1: initial audit invalid" in out
        assert "CONVERGENCE: BLOCKED" in out

    def test_refuted_claim_blocks_and_emits_a_packet_for_autonomous_correction(
        self, tmp_path: Path
    ) -> None:
        refuted = _claim(
            verdict="refuted",
            evidence=[_source(relation="refutes_claim")],
            replacement=None,
        )
        engine = ScriptedEngine(_audit(refuted), STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "lineage": "flow-plan", "round": 1,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        assert "CLAIM-CLOSURE: 0 supported, 1 refuted" in out
        assert "ACTIONABLE SOURCE PACKETS" in out
        assert "CONVERGENCE: BLOCKED — external claim closure" in out
        assert "BUILT-IN web search" in engine.prompts[0]
        assert "AUTHORITATIVE EXTERNAL CLAIM REGISTER" in engine.prompts[1]
        assert "Never demand claim packets" in engine.prompts[1]
        assert "missing atomic bridge" in engine.prompts[1]

    def test_supported_claim_and_closed_classes_produce_one_governing_clearance(
        self, tmp_path: Path
    ) -> None:
        engine = ScriptedEngine(_audit(_claim()), STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "lineage": "clear-plan", "round": 3,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T3",
        )
        assert "CLAIM-CLOSURE: 1 supported, 0 refuted, 0 unverified" in out
        assert "CLASS-CONVERGENCE: NOT-BLOCKED" in out
        assert out.count("\nCONVERGENCE:") == 1
        assert "CONVERGENCE: NOT-BLOCKED" in out

    def test_unchanged_supported_round_skips_claim_model_but_keeps_structural_review(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        first_engine = ScriptedEngine(_audit(_claim()), STRUCTURAL_CLEAR)
        handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(repo),
                "lineage": "retained-flow-plan", "round": 1,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=first_engine, log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        second_engine = ScriptedEngine(STRUCTURAL_CLEAR)
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(repo),
                "lineage": "retained-flow-plan", "round": 2,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=second_engine, log_dir=tmp_path / "logs", now=lambda: "T2",
        )
        assert len(second_engine.prompts) == 1
        assert "adversarial reviewer of plans" in second_engine.prompts[0]
        assert "factual-verification phase" not in second_engine.prompts[0]
        assert "CLAIM-CLOSURE: 1 supported, 0 refuted, 0 unverified" in out
        assert "CONVERGENCE: NOT-BLOCKED" in out

    def test_web_search_cannot_be_disabled_while_verification_is_on(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="requires.*built-in web search"):
            handlers.critique_plan(
                {
                    "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                    "lineage": "no-web-plan", "round": 1,
                    "claim_verification": True, "web_search": False,
                },
                engine=ScriptedEngine(), log_dir=tmp_path / "logs", now=lambda: "T1",
            )

    def test_one_shot_structural_review_emits_no_computed_clearance(self, tmp_path: Path) -> None:
        failure = Review(
            text="structural reviewer timed out", session_ref=None, raw="timeout",
            returncode=124, error=True,
        )
        out = handlers.critique_plan(
            {
                "plan_text": PLAN, "repo_path": str(_repo(tmp_path)),
                "class_closure": False, "claim_verification": True,
                "stakes": "single-user local tool; factual correctness is high impact",
            },
            engine=ScriptedEngine(_audit(_claim()), failure),
            log_dir=tmp_path / "logs", now=lambda: "T1",
        )
        assert "REVIEW FAILED" in out
        assert "CONVERGENCE:" not in out
        assert "CLAIM-CLOSURE: 1 supported" in out


class _RoleScript:
    name = "codex"
    default_model = "test"

    def __init__(
        self, outputs: dict[str, list[str | Review]],
        calls: list[tuple[str, str]] | None = None,
        advance: Callable[[], None] | None = None,
    ) -> None:
        self.outputs = outputs
        self.role = "default"
        self.calls = calls if calls is not None else []
        self.advance = advance

    def for_role(self, role: str):
        child = _RoleScript(self.outputs, self.calls, self.advance)
        child.role = role
        return child

    def _next(self) -> Review:
        value = self.outputs[self.role].pop(0)
        if self.advance is not None:
            self.advance()
        if isinstance(value, Review):
            return value
        return Review(
            text=value, session_ref="session", raw=self.role,
        )

    def run(self, *args, **kwargs):
        self.calls.append((self.role, args[0]))
        return self._next()

    def resume(self, *args, **kwargs):
        self.calls.append((self.role, args[1]))
        return self._next()


def test_captured_claim_retry_cannot_bypass_capture_validation(
    tmp_path: Path, monkeypatch,
) -> None:
    source = _source()
    candidate = external_sources.CandidateSource(
        source["url"], source["title"], source["publisher"], source["source_kind"],
        source["authority_basis"], source["relation"],
    )
    capture = external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        source["quote"],
    )
    monkeypatch.setattr(
        handlers.external_sources, "capture_all", lambda candidates, **kwargs: [capture],
    )
    valid = _audit(_claim())
    changed = _audit(_claim(evidence=[_source(url="https://example.com/changed")]))
    binding = (
        handlers.PLAN_BINDING_MARKER
        + '\n{"bindings":[{"claim_index":0,"evidence_index":0,"usable":true,'
        '"location":"Release page, first paragraph",'
        '"passage":"Python 3.11.0 was released on Monday, October 24, 2022."}]}'
    )
    attestation = (
        '=== EVIDENCE ATTESTATION JSON ===\n'
        '{"attestations":[{"claim_index":0,"evidence_index":0,'
        '"publisher_authority":true,"authority_reason":"official release owner",'
        '"passage_entailment":true,"entailment_reason":"states the release date"}]}'
    )
    engine = _RoleScript({
        "evidence-discovery": [valid],
        "evidence-binding": [binding, changed],
        "evidence-text": [attestation],
    })
    ledger: list[dict] = []
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
        attempt_ledger=ledger,
    )
    try:
        first = adapter.run("audit", tmp_path, "m", "high", True)
        assert not first.error
        retry = adapter.resume("session", "correct", tmp_path, "m", "high", True)
        assert retry.error
        assert "binding changed immutable source metadata" in retry.text
        assert [row["role"] for row in ledger] == [
            "claim-discovery", "claim-binding", "claim-attestation",
            "claim-binding-outer-retry",
        ]
    finally:
        adapter.close()


def test_non_web_context_provenance_preserves_authoritative_http_sibling(
    tmp_path: Path, monkeypatch,
) -> None:
    context = _source(url="repo://docs/plan.md", kind="primary")
    authoritative = _source()
    discovery = _audit(_claim(evidence=[context, authoritative]))

    def capture_all(candidates, **kwargs):
        rows = []
        for candidate in candidates:
            if candidate.url.startswith("repo://"):
                rows.append(external_sources.Capture(
                    candidate, None, None, None, None, None, None,
                    error="only public HTTP(S) sources can be captured",
                ))
            else:
                rows.append(external_sources.Capture(
                    candidate, candidate.url, 200, "text/html",
                    "a" * 64, "b" * 64, authoritative["quote"],
                ))
        return rows

    monkeypatch.setattr(handlers.external_sources, "capture_all", capture_all)
    binding = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
        "bindings": [{
            "claim_index": 0, "evidence_index": 1, "usable": True,
            "location": authoritative["location"],
            "passage": authoritative["quote"],
        }],
    })
    attestation = "=== EVIDENCE ATTESTATION JSON ===\n" + json.dumps({
        "attestations": [{
            "claim_index": 0, "evidence_index": 1,
            "publisher_authority": True,
            "authority_reason": "The publisher owns the release record.",
            "passage_entailment": True,
            "entailment_reason": "The passage states the release date.",
        }],
    })
    engine = _RoleScript({
        "evidence-discovery": [discovery],
        "evidence-binding": [binding],
        "evidence-text": [attestation],
    })
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        result = adapter.run("audit", tmp_path, "m", "high", True)
        assert not result.error
        audit = pc.parse_audit(
            result.text, PLAN, require_capture_provenance=True,
        )
        claim = audit.claims[0]
        assert claim["verdict"] == "supported"
        assert claim["evidence"][0]["relation"] == "context"
        assert claim["capture_provenance"][0] == {
            "evidence_index": 0,
            "requested_url": "repo://docs/plan.md",
            "final_url": None,
            "status": None,
            "content_type": None,
            "fallback_attempted": False,
            "content_sha256": None,
            "text_sha256": None,
            "error": "only public HTTP(S) sources can be captured",
        }
        assert claim["capture_provenance"][1]["requested_url"] == authoritative["url"]
        assert claim["capture_provenance"][1]["final_url"] == authoritative["url"]
        state = pc.reconcile(
            {}, audit, lineage_id="mixed-context", round_no=1, plan_text=PLAN,
        )
        reloaded = json.loads(json.dumps(state))
        record = next(iter(reloaded["claims"].values()))
        assert record["verdict"] == "supported"
        assert record["capture_provenance"] == claim["capture_provenance"]
    finally:
        adapter.close()


def test_default_redirect_rejection_reaches_durable_capture_provenance(
    tmp_path: Path, monkeypatch,
) -> None:
    source = _source(url="https://official.example/redirect")
    rejected = "http://127.0.0.1/private"
    redirect_headers = Message()
    redirect_headers["Content-Type"] = "text/plain; charset=utf-8"

    def validate(url):
        if url == source["url"]:
            return
        raise external_sources.SourceError(
            "source host resolves to non-public address 127.0.0.1"
        )

    class Opener:
        def __init__(self, handler):
            self.handler = handler

        def open(self, request, timeout):
            return self.handler.redirect_request(
                request, None, 302, "Found", redirect_headers, rejected,
            )

    monkeypatch.setattr(external_sources, "_validate_public_url", validate)
    monkeypatch.setattr(
        external_sources.urllib.request,
        "build_opener",
        lambda handler: Opener(handler),
    )
    engine = _RoleScript({
        "evidence-discovery": [_audit(_claim(evidence=[source]))],
    })
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        result = adapter.run("audit", tmp_path, "m", "high", True)
        assert not result.error
        audit = pc.parse_audit(
            result.text, PLAN, require_capture_provenance=True,
        )
        claim = audit.claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["capture_provenance"] == [{
            "evidence_index": 0,
            "requested_url": source["url"],
            "final_url": rejected,
            "status": 302,
            "content_type": "text/plain",
            "fallback_attempted": False,
            "content_sha256": None,
            "text_sha256": None,
            "error": (
                "rejected final URL: source host resolves to non-public address "
                "127.0.0.1"
            ),
        }]
        state = pc.reconcile(
            {}, audit, lineage_id="redirect-rejected", round_no=1, plan_text=PLAN,
        )
        record = next(iter(json.loads(json.dumps(state))["claims"].values()))
        assert record["capture_provenance"] == claim["capture_provenance"]
    finally:
        adapter.close()


def test_only_server_attested_supported_packets_freeze() -> None:
    unattested = pc.reconcile(
        {}, pc.parse_audit(_audit(_claim()), PLAN),
        lineage_id="capture-plan", round_no=1, plan_text=PLAN,
    )
    assert not pc.frozen_supported_ids(
        unattested, PLAN, require_capture_attestation=True,
    )
    attestation = {
        "evidence_index": 0,
        "final_url": _source()["url"],
        "text_sha256": "a" * 64,
        "relation": "supports_claim",
        "publisher_authority": True,
        "authority_reason": "The publisher owns the release record.",
        "passage_entailment": True,
        "entailment_reason": "The passage states the release date.",
    }
    provenance = {
        "evidence_index": 0,
        "requested_url": _source()["url"],
        "final_url": _source()["url"],
        "status": 200,
        "content_type": "text/html",
        "fallback_attempted": False,
        "content_sha256": "b" * 64,
        "text_sha256": "a" * 64,
        "error": None,
    }
    legacy = pc.reconcile(
        {}, pc.parse_audit(_audit(_claim(capture_attestations=[attestation])), PLAN),
        lineage_id="capture-plan", round_no=1, plan_text=PLAN,
    )
    legacy["plan_snapshot"] = PLAN
    assert not pc.frozen_supported_ids(
        legacy, PLAN, require_capture_attestation=True,
    )
    attested = pc.reconcile(
        {}, pc.parse_audit(_audit(_claim(
            capture_attestations=[attestation], capture_provenance=[provenance],
        )), PLAN),
        lineage_id="capture-plan", round_no=1, plan_text=PLAN,
    )
    assert len(pc.frozen_supported_ids(
        attested, PLAN, require_capture_attestation=True,
    )) == 1


def test_capture_attestation_boolean_index_cannot_parse_or_freeze() -> None:
    evidence = [
        _source(url="https://docs.python.org/3/whatsnew/3.11.html"),
        _source(),
    ]
    attestation = {
        "evidence_index": 1,
        "final_url": evidence[1]["url"],
        "text_sha256": "a" * 64,
        "relation": "supports_claim",
        "publisher_authority": True,
        "authority_reason": "The publisher owns the release record.",
        "passage_entailment": True,
        "entailment_reason": "The passage states the release date.",
    }
    audit = pc.parse_audit(_audit(_claim(
        evidence=evidence, capture_attestations=[attestation],
    )), PLAN)
    state = pc.reconcile(
        {}, audit, lineage_id="capture-index", round_no=1, plan_text=PLAN,
    )
    record = next(iter(state["claims"].values()))
    record["capture_attestations"][0]["evidence_index"] = True
    assert not pc.frozen_supported_ids(
        state, PLAN, require_capture_attestation=True,
    )

    forged = dict(attestation, evidence_index=True)
    with pytest.raises(pc.AuditError, match="evidence_index is invalid or duplicated"):
        pc.parse_audit(_audit(_claim(
            evidence=evidence, capture_attestations=[forged],
        )), PLAN)


def test_negative_attestation_removes_exact_replacement_but_keeps_refutation(
    tmp_path: Path,
) -> None:
    replacement = "Python 3.11.0 was released on October 24, 2022."
    evidence = [
        _source(relation="refutes_claim"),
        _source(
            url="https://docs.python.org/3.11/whatsnew/3.11.html",
            relation="supports_replacement",
        ),
    ]
    audit = pc.parse_audit(_audit(_claim(
        verdict="refuted", evidence=evidence, replacement=replacement,
    )), PLAN)
    attestation = (
        '=== EVIDENCE ATTESTATION JSON ===\n'
        '{"attestations":['
        '{"claim_index":0,"evidence_index":0,"publisher_authority":true,'
        '"authority_reason":"official release owner","passage_entailment":true,'
        '"entailment_reason":"refutes the old wording"},'
        '{"claim_index":0,"evidence_index":1,"publisher_authority":true,'
        '"authority_reason":"official release owner","passage_entailment":false,'
        '"entailment_reason":"does not entail the proposed replacement"}]}'
    )
    engine = _RoleScript({"evidence-text": [attestation]})
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    for evidence_index, item in enumerate(audit.claims[0]["evidence"]):
        candidate = external_sources.CandidateSource(
            item["url"], item["title"], item["publisher"], item["source_kind"],
            item["authority_basis"], item["relation"],
        )
        adapter.captures[(0, evidence_index)] = external_sources.Capture(
            candidate, candidate.url, 200, "text/html", "a" * 64,
            chr(ord("b") + evidence_index) * 64, item["quote"],
        )
    try:
        result = adapter._attest(audit, "m", "high")
        assert isinstance(result, pc.Audit)
        assert result.claims[0]["verdict"] == "refuted"
        assert result.claims[0]["replacement"] is None
        attester_prompt = next(
            prompt for role, prompt in engine.calls if role == "evidence-text"
        )
        assert f'"proposition":"{replacement}"' in attester_prompt
    finally:
        adapter.close()


def _run_indexed_attestation_rows(
    tmp_path: Path, rows: list[dict[str, object]],
    correction_rows: list[dict[str, object]] | None = None,
    attempt_ledger: list[dict] | None = None,
) -> pc.Audit | Review:
    second_anchor = "Python documentation also records the release date."
    plan = PLAN + "\n" + second_anchor + "\n"
    evidence = [
        _source(),
        _source(url="https://docs.python.org/3/whatsnew/3.11.html"),
    ]
    audit = pc.parse_audit(_audit(
        _claim(evidence=evidence),
        _claim(anchor=second_anchor, proposition=second_anchor, evidence=evidence),
    ), plan)
    response = (
        "=== EVIDENCE ATTESTATION JSON ===\n"
        + json.dumps({"attestations": rows})
    )
    correction = (
        "=== EVIDENCE ATTESTATION JSON ===\n"
        + json.dumps({"attestations": correction_rows})
        if correction_rows is not None else response
    )
    engine = _RoleScript({"evidence-text": [response, correction]})
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
        attempt_ledger=attempt_ledger,
    )
    for claim_index, claim in enumerate(audit.claims):
        for evidence_index, item in enumerate(claim["evidence"]):
            candidate = external_sources.CandidateSource(
                item["url"], item["title"], item["publisher"], item["source_kind"],
                item["authority_basis"], item["relation"],
            )
            adapter.captures[(claim_index, evidence_index)] = (
                external_sources.Capture(
                    candidate, candidate.url, 200, "text/html", "a" * 64,
                    f"{claim_index * 2 + evidence_index + 1:064x}", item["quote"],
                )
            )
    try:
        return adapter._attest(audit, "m", "high")
    finally:
        adapter.close()


def _valid_attestation_rows() -> list[dict[str, object]]:
    return [{
        "claim_index": claim_index,
        "evidence_index": evidence_index,
        "publisher_authority": True,
        "authority_reason": "official owner",
        "passage_entailment": True,
        "entailment_reason": "direct statement",
    } for claim_index in range(2) for evidence_index in range(2)]


@pytest.mark.parametrize("field", ["claim_index", "evidence_index"])
@pytest.mark.parametrize("invalid_index", [True, 1.0, "1", None, [], {}])
def test_attestation_index_types_fail_before_identity_binding(
    tmp_path: Path, field: str, invalid_index: object,
) -> None:
    rows = _valid_attestation_rows()
    rows[-1][field] = invalid_index
    result = _run_indexed_attestation_rows(tmp_path, rows)
    assert isinstance(result, Review)
    assert result.error
    assert result.session_ref == "session"
    assert "attestation row indices must be integers" in result.text


@pytest.mark.parametrize(("case", "message"), [
    ("unknown", "unknown or duplicate attestation row"),
    ("duplicate", "unknown or duplicate attestation row"),
    ("omitted", "attestation inventory differs"),
])
def test_attestation_identity_inventory_fails_recoverably(
    tmp_path: Path, case: str, message: str,
) -> None:
    rows = _valid_attestation_rows()
    if case == "unknown":
        rows[-1]["claim_index"] = 9
    elif case == "duplicate":
        rows[-1] = dict(rows[0])
    else:
        rows.pop()
    result = _run_indexed_attestation_rows(tmp_path, rows)
    assert isinstance(result, Review)
    assert result.error
    assert result.session_ref == "session"
    assert message in result.text


def test_attestation_reason_bound_uses_one_successful_correction(tmp_path: Path) -> None:
    rows = _valid_attestation_rows()
    rows[0]["authority_reason"] = "x" * (handlers.MAX_ATTESTATION_REASON_CHARS + 1)
    ledger: list[dict] = []
    result = _run_indexed_attestation_rows(
        tmp_path, rows, correction_rows=_valid_attestation_rows(),
        attempt_ledger=ledger,
    )
    assert isinstance(result, pc.Audit)
    assert all(claim["verdict"] == "supported" for claim in result.claims)
    assert [row["role"] for row in ledger] == [
        "claim-attestation", "claim-attestation-validation-retry",
    ]
    assert ledger[0]["outcome"] == "validation-invalid"
    assert ledger[0]["validation_pointer"] == "/attestations"
    assert ledger[0]["rejected_reply_sha256"]
    assert ledger[1]["outcome"] == "completed"


def test_retained_inventory_is_corrected_before_capture(
    tmp_path: Path, monkeypatch,
) -> None:
    second_anchor = "SQLite 3.45.0 was released on January 15, 2024."
    plan = PLAN + "\n" + second_anchor + "\n"
    first_claim = _claim(verdict="unverified", evidence=[])
    second_claim = _claim(
        anchor=second_anchor, proposition=second_anchor, verdict="unverified", evidence=[],
    )
    prior = pc.reconcile(
        {}, pc.parse_audit(_audit(first_claim, second_claim), plan),
        lineage_id="inventory", round_no=1, plan_text=plan,
    )
    complete_first = _claim()
    complete_second = _claim(anchor=second_anchor, proposition=second_anchor)
    discovery_omission = _audit(complete_first)
    discovery_corrected = _audit(complete_first, complete_second)
    binding = (
        handlers.PLAN_BINDING_MARKER
        + '\n{"bindings":['
        '{"claim_index":0,"evidence_index":0,"usable":true,'
        '"location":"release record","passage":"'
        + complete_first["evidence"][0]["quote"]
        + '"},{"claim_index":1,"evidence_index":0,"usable":true,'
        '"location":"release record","passage":"'
        + complete_second["evidence"][0]["quote"]
        + '"}]}'
    )
    attestation = (
        '=== EVIDENCE ATTESTATION JSON ===\n{"attestations":['
        '{"claim_index":0,"evidence_index":0,"publisher_authority":true,'
        '"authority_reason":"official owner","passage_entailment":true,'
        '"entailment_reason":"direct statement"},'
        '{"claim_index":1,"evidence_index":0,"publisher_authority":true,'
        '"authority_reason":"official owner","passage_entailment":true,'
        '"entailment_reason":"direct statement"}]}'
    )
    engine = _RoleScript({
        "evidence-discovery": [discovery_omission, discovery_corrected],
        "evidence-binding": [binding],
        "evidence-text": [attestation],
    })
    capture_sizes: list[int] = []

    def capture_all(candidates, **kwargs):
        rows = list(candidates)
        capture_sizes.append(len(rows))
        return [
            external_sources.Capture(
                candidate, candidate.url, 200, "text/html", "a" * 64,
                f"{index + 1:064x}", complete_first["evidence"][0]["quote"],
            )
            for index, candidate in enumerate(rows)
        ]

    monkeypatch.setattr(handlers.external_sources, "capture_all", capture_all)
    ledger: list[dict] = []
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
        prior_state=prior, frozen_ids=frozenset(), attempt_ledger=ledger,
    )
    try:
        result = adapter.run("audit", tmp_path, "m", "high", True)
        assert not result.error
        assert capture_sizes == [2]
        assert [role for role, _ in engine.calls].count("evidence-discovery") == 2
        assert [row["role"] for row in ledger] == [
            "claim-discovery", "claim-discovery-validation-retry", "claim-binding",
            "claim-attestation",
        ]
    finally:
        adapter.close()


def test_final_retained_omission_preserves_valid_captured_packets(
    tmp_path: Path, monkeypatch,
) -> None:
    second_anchor = "SQLite 3.45.0 was released on January 15, 2024."
    plan = PLAN + "\n" + second_anchor + "\n"
    first_claim = _claim(verdict="unverified", evidence=[])
    second_claim = _claim(
        anchor=second_anchor, proposition=second_anchor, verdict="unverified", evidence=[],
    )
    prior = pc.reconcile(
        {}, pc.parse_audit(_audit(first_claim, second_claim), plan),
        lineage_id="partial-inventory", round_no=1, plan_text=plan,
    )
    complete_first = _claim()
    discovery_omission = _audit(complete_first)
    binding = (
        handlers.PLAN_BINDING_MARKER
        + '\n{"bindings":[{"claim_index":0,"evidence_index":0,"usable":true,'
        '"location":"release record","passage":"'
        + complete_first["evidence"][0]["quote"]
        + '"}]}'
    )
    attestation = (
        '=== EVIDENCE ATTESTATION JSON ===\n{"attestations":['
        '{"claim_index":0,"evidence_index":0,"publisher_authority":true,'
        '"authority_reason":"official owner","passage_entailment":true,'
        '"entailment_reason":"direct statement"}]}'
    )
    engine = _RoleScript({
        "evidence-discovery": [discovery_omission, discovery_omission],
        "evidence-binding": [binding],
        "evidence-text": [attestation],
    })
    capture_sizes: list[int] = []

    def capture_all(candidates, **kwargs):
        rows = list(candidates)
        capture_sizes.append(len(rows))
        return [
            external_sources.Capture(
                candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
                complete_first["evidence"][0]["quote"],
            )
            for candidate in rows
        ]

    monkeypatch.setattr(handlers.external_sources, "capture_all", capture_all)
    monkeypatch.setattr(handlers.eng, "CodexEngine", _RoleScript)
    state, status = handlers._verify_plan_claims(
        plan, prior, lineage_id="partial-inventory", round_no=2,
        stakes="trusted local plan; factual correctness matters", engine=engine,
        repo=_repo(tmp_path), model="m", effort="high", plan_repo_path=None,
        on_progress=None, deadline=float("inf"),
    )

    assert capture_sizes == [1]
    assert "localized retained omission" in status
    verdicts = sorted(record["verdict"] for record in state["claims"].values())
    assert verdicts == ["supported", "unverified"]


def test_plan_binding_batches_large_ordinary_inventory(tmp_path: Path) -> None:
    lines = [f"External behavior {index} is guaranteed." for index in range(11)]
    plan = "# Plan\n\n" + "\n".join(lines)
    claims = [
        _claim(anchor=line, proposition=line) for line in lines
    ]
    audit = pc.parse_audit(_audit(*claims), plan)
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        captures = {}
        for claim_index, claim in enumerate(audit.claims):
            item = claim["evidence"][0]
            candidate = external_sources.CandidateSource(
                item["url"], item["title"], item["publisher"], item["source_kind"],
                item["authority_basis"], item["relation"],
            )
            captures[(claim_index, 0)] = external_sources.Capture(
                candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
                "x" * 100_000,
            )
        batches = adapter._binding_batches(audit, captures)
        assert len(batches) == 1
        assert sum(map(len, batches)) == 11
        assert batches[0][0]["capture"]["capture_ref"] is None
        assert batches[0][1]["capture"]["capture_ref"] == {
            "claim_index": 0, "evidence_index": 0,
        }
        assert batches[0][1]["capture"]["line_numbered_text"] == ""
    finally:
        adapter.close()


def test_plan_binding_capture_references_never_cross_batch_boundary(tmp_path: Path) -> None:
    lines = [f"External behavior {index} is guaranteed." for index in range(6)]
    plan = "# Plan\n\n" + "\n".join(lines)
    audit = pc.parse_audit(_audit(*[
        _claim(anchor=line, proposition=line) for line in lines
    ]), plan)
    identities = [0, 1, 2, 3, 0, 0]
    captures = {}
    for claim_index, (claim, identity) in enumerate(zip(audit.claims, identities)):
        item = claim["evidence"][0]
        candidate = external_sources.CandidateSource(
            item["url"], item["title"], item["publisher"], item["source_kind"],
            item["authority_basis"], item["relation"],
        )
        captures[(claim_index, 0)] = external_sources.Capture(
            candidate, f"{candidate.url}?page={identity}", 200, "text/html",
            f"{identity:064x}", f"{identity + 10:064x}",
            "x" * 100_000,
        )
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        batches = adapter._binding_batches(audit, captures)
    finally:
        adapter.close()
    assert len(batches) == 2
    assert [row["claim_index"] for row in batches[1]] == [3, 4, 5]
    assert batches[1][1]["capture"]["capture_ref"] is None
    assert batches[1][1]["capture"]["line_numbered_text"]
    assert batches[1][2]["capture"]["capture_ref"] == {
        "claim_index": 4, "evidence_index": 0,
    }
    assert batches[1][2]["capture"]["line_numbered_text"] == ""


def test_long_primary_capture_uses_one_complete_expanded_packet(tmp_path: Path) -> None:
    audit = pc.parse_audit(_audit(_claim()), PLAN)
    item = audit.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    text = "x" * 590_000 + "\n" + item["quote"]
    captures = {(0, 0): external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64, text,
    )}
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        batches = adapter._binding_batches(audit, captures)
        rendered = json.dumps(batches[0], ensure_ascii=False, separators=(",", ":"))
        assert len(batches) == 1 and len(batches[0]) == 1
        assert (0, 0) in adapter.expanded_captures
        assert len(adapter._binding_prompt(rendered)) > handlers.MAX_PLAN_BINDING_BATCH_CHARS
        assert len(adapter._binding_prompt(rendered)) <= handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS
        assert batches[0][0]["binding_target"] == audit.claims[0]["proposition"]
        assert captures[(0, 0)].usable
    finally:
        adapter.close()


def test_long_capture_expansion_uses_effective_final_url_policy(tmp_path: Path) -> None:
    audit = pc.parse_audit(_audit(_claim()), PLAN)
    item = audit.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    captures = {(0, 0): external_sources.Capture(
        candidate, "https://www.reddit.com/r/python/comments/x", 200, "text/html",
        "a" * 64, "b" * 64, "x" * 590_000,
    )}
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        assert adapter._binding_batches(audit, captures) == []
        assert not captures[(0, 0)].usable
        assert captures[(0, 0)].final_url == "https://www.reddit.com/r/python/comments/x"
        assert captures[(0, 0)].content_sha256 == "a" * 64
        assert captures[(0, 0)].text_sha256 == "b" * 64
    finally:
        adapter.close()


@pytest.mark.parametrize("host_form", [
    "https://github.com/acme/review-repo/blob/main/docs/plan.md",
    "https://raw.githubusercontent.com/acme/review-repo/main/docs/plan.md",
])
def test_long_capture_redirect_to_reviewed_plan_cannot_expand(
    tmp_path: Path, host_form: str,
) -> None:
    repo = tmp_path / "review-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/review-repo.git"],
        cwd=repo, check=True,
    )
    audit = pc.parse_audit(_audit(_claim()), PLAN)
    item = audit.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    captures = {(0, 0): external_sources.Capture(
        candidate, host_form, 200, "text/html", "a" * 64, "b" * 64,
        "x" * 590_000,
    )}
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=repo,
        plan_repo_path="docs/plan.md",
    )
    try:
        assert adapter._binding_batches(audit, captures) == []
        assert (0, 0) not in adapter.expanded_captures
        assert captures[(0, 0)].error == external_sources.BINDING_BUDGET_ERROR
    finally:
        adapter.close()


def test_plan_binding_demotes_one_escape_amplified_capture_per_source(tmp_path: Path) -> None:
    audit = pc.parse_audit(_audit(_claim()), PLAN)
    item = audit.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    captures = {(0, 0): external_sources.Capture(
        candidate, candidate.url, 200, "text/plain", "a" * 64, "b" * 64,
        "\n" * 100_000,
    )}
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        batches = adapter._binding_batches(audit, captures)
    finally:
        adapter.close()
    assert batches == []
    assert not captures[(0, 0)].usable
    assert captures[(0, 0)].error == external_sources.BINDING_BUDGET_ERROR


def test_escape_amplified_capture_is_demoted_before_flushing_current_batch(
    tmp_path: Path,
) -> None:
    lines = [f"External behavior {index} is guaranteed." for index in range(4)]
    plan = "# Plan\n\n" + "\n".join(lines)
    audit = pc.parse_audit(_audit(*[
        _claim(anchor=line, proposition=line) for line in lines
    ]), plan)
    captures = {}
    for claim_index, claim in enumerate(audit.claims):
        item = claim["evidence"][0]
        candidate = external_sources.CandidateSource(
            item["url"], item["title"], item["publisher"], item["source_kind"],
            item["authority_basis"], item["relation"],
        )
        captures[(claim_index, 0)] = external_sources.Capture(
            candidate, f"{candidate.url}?page={claim_index}", 200, "text/plain",
            f"{claim_index:064x}", f"{claim_index + 10:064x}",
            ("x" * 100_000)
            if claim_index < 3 else ("\n" * 100_000),
        )
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        batches = adapter._binding_batches(audit, captures)
    finally:
        adapter.close()
    assert len(batches) == 1
    assert len(batches[0]) == 3
    assert captures[(3, 0)].error == external_sources.BINDING_BUDGET_ERROR


def test_repeated_ineligible_oversized_rows_cannot_manufacture_batches(
    tmp_path: Path,
) -> None:
    lines = [f"External behavior {index} is guaranteed." for index in range(12)]
    plan = "# Plan\n\n" + "\n".join(lines)
    claims = [
        _claim(
            anchor=line, proposition=line,
            evidence=[_source(kind="secondary" if index % 2 else "primary")],
        )
        for index, line in enumerate(lines)
    ]
    audit = pc.parse_audit(_audit(*claims), plan)
    captures = {}
    for claim_index, claim in enumerate(audit.claims):
        item = claim["evidence"][0]
        candidate = external_sources.CandidateSource(
            item["url"], item["title"], item["publisher"], item["source_kind"],
            item["authority_basis"], item["relation"],
        )
        captures[(claim_index, 0)] = external_sources.Capture(
            candidate, f"{candidate.url}?page={claim_index}", 200, "text/plain",
            f"{claim_index + 1:064x}", f"{claim_index + 101:064x}",
            "\n" * 100_000 if claim_index % 2 else item["quote"],
        )
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        batches = adapter._binding_batches(audit, captures)
    finally:
        adapter.close()
    assert len(batches) == 1
    assert [row["claim_index"] for row in batches[0]] == [0, 2, 4, 6, 8, 10]
    assert all(
        captures[(index, 0)].error == external_sources.BINDING_BUDGET_ERROR
        for index in range(1, 12, 2)
    )


def test_plan_capture_aggregate_ceiling_blocks_before_network(
    tmp_path: Path, monkeypatch,
) -> None:
    lines = [
        f"External behavior {index} is guaranteed."
        for index in range(handlers.MAX_PLAN_CAPTURE_SOURCES + 1)
    ]
    plan = "# Plan\n\n" + "\n".join(lines)
    audit = pc.parse_audit(_audit(*[
        _claim(anchor=line, proposition=line) for line in lines
    ]), plan)
    monkeypatch.setattr(
        handlers.external_sources, "capture_all",
        lambda candidates, **kwargs: pytest.fail("capture must not start past the ceiling"),
    )
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        with pytest.raises(pc.AuditError, match="aggregate capture ceiling"):
            adapter._capture(audit)
    finally:
        adapter.close()


def test_non_model_reserve_bounds_200_source_capture_before_binding(
    tmp_path: Path, monkeypatch,
) -> None:
    count = handlers.MAX_PLAN_CAPTURE_SOURCES
    lines = [f"External behavior {index} is guaranteed." for index in range(count)]
    plan = "# Plan\n\n" + "\n".join(lines)
    discovery = _audit(*[
        _claim(anchor=line, proposition=line) for line in lines
    ])
    now = [0.0]
    engine = _RoleScript(
        {"evidence-discovery": [discovery]},
        advance=lambda: now.__setitem__(
            0, now[0] + handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC,
        ),
    )

    def capture_all(candidates, **kwargs):
        assert len(candidates) == count
        assert kwargs["deadline"] == (
            handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC
            + handlers.PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC
        )
        now[0] += handlers.PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC + 1
        return [
            external_sources.Capture(
                candidate, candidate.url, 200, "text/html",
                f"{index + 1:064x}", f"{index + 201:064x}", _source()["quote"],
            )
            for index, candidate in enumerate(candidates)
        ]

    monkeypatch.setattr(handlers.external_sources, "capture_all", capture_all)
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
        deadline=float(handlers.PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC),
        clock=lambda: now[0],
    )
    try:
        result = adapter.run("audit", tmp_path, "m", "high", True)
        assert result.error
        assert "exceeded its aggregate 300-second reserve" in result.text
        assert [role for role, _ in engine.calls] == ["evidence-discovery"]
        assert adapter.model_calls == 1
    finally:
        adapter.close()


def test_plan_binding_aggregate_batch_ceiling_raises_before_model_calls(
    tmp_path: Path,
) -> None:
    count = handlers.MAX_PLAN_BINDING_BATCHES * 10 + 1
    lines = [f"External behavior {index} is guaranteed." for index in range(count)]
    plan = "# Plan\n\n" + "\n".join(lines)
    audit = pc.parse_audit(_audit(*[
        _claim(anchor=line, proposition=line) for line in lines
    ]), plan)
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
    )
    captures = {}
    for claim_index, claim in enumerate(audit.claims):
        item = claim["evidence"][0]
        candidate = external_sources.CandidateSource(
            item["url"], item["title"], item["publisher"], item["source_kind"],
            item["authority_basis"], item["relation"],
        )
        captures[(claim_index, 0)] = external_sources.Capture(
            candidate, f"{candidate.url}?claim={claim_index}", 200, "text/html",
            f"{claim_index:064x}", "b" * 64,
            "x" * 100_000,
        )
    try:
        with pytest.raises(pc.AuditError, match="aggregate ceiling"):
            adapter._binding_batches(audit, captures)
    finally:
        adapter.close()


def test_sixth_attestation_batch_fails_globally_before_settling_a_prefix(
    tmp_path: Path, monkeypatch,
) -> None:
    count = handlers.MAX_PLAN_CAPTURE_SOURCES
    passage = '"' * handlers.MAX_BINDING_PASSAGE_CHARS
    lines = [f"External behavior {index} is guaranteed." for index in range(count)]
    plan = "# Plan\n\n" + "\n".join(lines)
    source = _source(quote=passage)
    discovery = _audit(*[
        _claim(
            anchor=line, proposition=line,
            evidence=[dict(source)],
        )
        for line in lines
    ])
    binding = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
        "bindings": [{
            "claim_index": index, "evidence_index": 0, "usable": True,
            "location": source["location"], "passage": passage,
        } for index in range(count)],
    })

    def capture_all(candidates, **kwargs):
        return [
            external_sources.Capture(
                candidate, source["url"], 200, "text/html",
                "a" * 64, "b" * 64, passage,
            )
            for candidate in candidates
        ]

    monkeypatch.setattr(handlers.external_sources, "capture_all", capture_all)
    engine = _RoleScript({
        "evidence-discovery": [discovery],
        "evidence-binding": [binding],
    })
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        result = adapter.run("audit", tmp_path, "m", "high", True)
        assert result.error
        assert "evidence attestation requires" in result.text
        assert f"aggregate ceiling is {handlers.MAX_PLAN_ATTESTATION_BATCHES}" in result.text
        assert [role for role, _ in engine.calls] == [
            "evidence-discovery", "evidence-binding",
        ]
        assert "=== CLAIM AUDIT JSON ===" not in result.text
        assert adapter.attestation_raw == ""
    finally:
        adapter.close()


def test_plan_evidence_model_call_budget_refuses_another_phase(tmp_path: Path) -> None:
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
        deadline=float("inf"),
    )
    adapter.model_calls = handlers.MAX_PLAN_EVIDENCE_MODEL_CALLS
    try:
        with pytest.raises(pc.AuditError, match="model-call ceiling"):
            adapter._next_model_timeout()
    finally:
        adapter.close()


def test_plan_evidence_budget_composes_at_maximum_batch_count() -> None:
    normal_path = (
        1 + handlers.MAX_PLAN_BINDING_BATCHES
        + handlers.MAX_PLAN_ATTESTATION_BATCHES
    )
    assert handlers.MAX_PLAN_EVIDENCE_MODEL_CALLS == normal_path * 2
    assert handlers.PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC == (
        handlers.MAX_PLAN_EVIDENCE_MODEL_CALLS
        * handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC
        + 2 * (
            handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC
            - handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC
        )
        + handlers.PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC
        + handlers.PLAN_EVIDENCE_SCHEDULING_SLACK_SEC
    )
    assert handlers.PLAN_REVIEW_TOTAL_TIMEOUT_SEC == (
        handlers.PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC
        + handlers.PLAN_TEARDOWN_RESERVE_SEC
    )


def test_large_plan_discovery_uses_the_dedicated_timeout(
    tmp_path: Path, monkeypatch,
) -> None:
    # Match the 2,328-line / 140,509-character plan from the issue-58 failure series,
    # then exceed it substantially. Discovery sees the whole plan; later source
    # capture and binding are deliberately irrelevant to this regression boundary.
    line = "An external platform behavior remains subject to authoritative verification.\n"
    plan = ("# Large plan\n\n" + line * 4_000)[:280_000]
    seen: list[int | None] = []
    ledger: list[dict] = []

    class TimeoutEngine(_RoleScript):
        def for_role(self, role: str):
            child = TimeoutEngine(self.outputs, self.calls)
            child.role = role
            return child

        def run(self, *args, **kwargs):
            seen.append(kwargs.get("timeout"))
            return Review(
                text="discovery timed out", session_ref=None, raw="",
                returncode=124, error=True,
            )

    monkeypatch.setattr(
        handlers.external_sources, "capture_all",
        lambda *args, **kwargs: pytest.fail("capture follows successful discovery"),
    )
    adapter = handlers._CapturedClaimEngine(
        TimeoutEngine({}), plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
        deadline=float(handlers.PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC),
        clock=lambda: 0.0, attempt_ledger=ledger,
    )
    try:
        result = adapter.run(plan, tmp_path, "m", "high", True)
        assert result.error and result.returncode == 124
        assert len(plan) > 2 * 140_509 - 2_000
        assert seen == [handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC]
        assert seen != [handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC]
        assert ledger[0]["requested_timeout_sec"] == (
            handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC
        )
    finally:
        adapter.close()


def test_plan_evidence_budget_admits_every_initial_and_validation_retry(
    tmp_path: Path,
) -> None:
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
        deadline=float("inf"),
    )
    phases = (
        1 + handlers.MAX_PLAN_BINDING_BATCHES
        + handlers.MAX_PLAN_ATTESTATION_BATCHES
    )
    try:
        for _ in range(phases):
            assert adapter._next_model_timeout(reserve_calls=2) == (
                handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC
            )
            assert adapter._next_model_timeout() == handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC
        with pytest.raises(pc.AuditError, match="model-call ceiling"):
            adapter._next_model_timeout()
    finally:
        adapter.close()


def test_maximum_evidence_topology_executes_every_validation_retry(
    tmp_path: Path, monkeypatch,
) -> None:
    claims: list[dict[str, object]] = []
    anchors: list[str] = []
    passages: list[str] = []
    for index in range(handlers.MAX_PLAN_BINDING_BATCHES):
        anchor = f"Vendor {index} published release {index} on January {index + 1}, 2024."
        passage = f"Release {index} was published on January {index + 1}, 2024."
        anchors.append(anchor)
        passages.append(passage)
        claims.append(_claim(
            anchor=anchor,
            proposition=anchor,
            evidence=[_source(
                url=f"https://official.example/source-{index}", quote=passage,
            )],
        ))
    plan = "# Maximum topology\n\n" + "\n".join(anchors) + "\n"
    discovery = _audit(*claims)
    binding_outputs: list[str | Review] = []
    attestation_outputs: list[str | Review] = []
    for index, passage in enumerate(passages):
        binding_outputs.extend([
            "invalid binding",
            handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
                "bindings": [{
                    "claim_index": index, "evidence_index": 0, "usable": True,
                    "location": "release record", "passage": passage,
                }],
            }),
        ])
        attestation_outputs.extend([
            "invalid attestation",
            "=== EVIDENCE ATTESTATION JSON ===\n" + json.dumps({
                "attestations": [{
                    "claim_index": index, "evidence_index": 0,
                    "publisher_authority": True,
                    "authority_reason": "official publisher",
                    "passage_entailment": True,
                    "entailment_reason": "direct release record",
                }],
            }),
        ])
    now = [0.0]
    phase_calls = [0]

    def advance() -> None:
        timeout = (
            handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC
            if phase_calls[0] < 2 else handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC
        )
        phase_calls[0] += 1
        now[0] += timeout

    engine = _RoleScript({
        "evidence-discovery": ["invalid discovery", discovery],
        "evidence-binding": binding_outputs,
        "evidence-text": attestation_outputs,
    }, advance=advance)

    def capture_all(candidates, **kwargs):
        now[0] += handlers.PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC
        return [
            external_sources.Capture(
                candidate, candidate.url, 200, "text/html",
                f"{index + 1:064x}", f"{index + 101:064x}",
                "x" * 450_000 + "\n" + passages[index],
            )
            for index, candidate in enumerate(candidates)
        ]

    monkeypatch.setattr(handlers.external_sources, "capture_all", capture_all)
    ledger: list[dict] = []
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
        deadline=float(handlers.PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC),
        attempt_ledger=ledger, clock=lambda: now[0],
    )
    try:
        result = adapter.run("audit", tmp_path, "m", "high", True)
        assert not result.error
        assert adapter.model_calls == handlers.MAX_PLAN_EVIDENCE_MODEL_CALLS
        assert now[0] == (
            handlers.PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC
            - handlers.PLAN_EVIDENCE_SCHEDULING_SLACK_SEC
        )
        assert len(ledger) == handlers.MAX_PLAN_EVIDENCE_MODEL_CALLS
        assert [row["outcome"] for row in ledger[::2]] == [
            "validation-invalid"
        ] * 11
        assert [row["outcome"] for row in ledger[1::2]] == ["completed"] * 11
        assert all(row.get("validation_pointer") for row in ledger[::2])
        audited = pc.parse_audit(
            result.text, plan, require_capture_provenance=True,
        )
        assert len(audited.claims) == 5
        assert all(claim["verdict"] == "supported" for claim in audited.claims)
    finally:
        adapter.close()


def test_evidence_deadline_debt_is_persisted_before_structural_review(
    repo: Path, tmp_path: Path, monkeypatch,
) -> None:
    lineage_id = "deadline-debt-plan"
    observed: dict[str, float | None] = {}

    def deadline_debt(plan_text, prior_state, **kwargs):
        observed["deadline"] = kwargs["deadline"]
        return pc.with_debt(
            prior_state, pc.AuditError("evidence deadline exhausted"),
            round_no=kwargs["round_no"], plan_text=plan_text,
        ), "failed"

    def structural_review(self, *args, **kwargs):
        observed["structural_timeout"] = kwargs.get("timeout")
        prompt = args[0]
        if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
            lane = next(x.split()[-1] for x in prompt.splitlines() if x.startswith("ROLE: census lane"))
            coverage = [
                {"id": key, "status": "covered", "summary": "checked",
                 "evidence": [{
                     "anchor": "repository/README.md:1",
                     "rationale": "fixture coverage",
                 }], "finding_ids": []}
                for key in handlers.sp.CHECKLIST
            ]
            text = json.dumps({
                "lane": lane, "coverage": coverage, "findings": [],
                "class_assessments": [],
            })
        else:
            text = json.dumps({
                "role": "census", "governing_findings": [],
                "debt_outcomes": [], "class_actions": {},
            })
        return Review(text=text, session_ref="structural", raw=text)

    monkeypatch.setattr(handlers, "_verify_plan_claims", deadline_debt)
    monkeypatch.setattr(handlers.inert_git, "require_supported_version", lambda: (2, 50, 1))
    monkeypatch.setattr(handlers.eng, "require_evidence_profile", lambda engine: None)
    monkeypatch.setattr(
        handlers.eng.CodexEngine, "run", structural_review,
    )
    monkeypatch.setattr(
        handlers.eng.CodexEngine, "resume", structural_review,
    )
    result = handlers.critique_plan(
        {
            "plan_text": PLAN, "repo_path": str(repo), "lineage": lineage_id,
            "round": 1, "stakes": "trusted local plan; correctness is high impact",
        },
        engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs", now=lambda: "T1",
    )
    lineage = cc.load_lineage(
        cc.default_state_root(), lineage_id, stamp="T2", mode=cc.PLAN_MODE,
    )

    assert observed["deadline"] is not None
    assert observed["structural_timeout"] in {1800, 1200}
    assert lineage.claim_state["debt"]["reason"] == "evidence deadline exhausted"
    assert "CLAIM-AUDIT-DEBT" in result
    assert lineage.review_state["phase"] == "clear"
    assert "STRUCTURAL-PHASE: clear" in result
    assert "STRUCTURAL-CONVERGENCE: NOT-BLOCKED" in result
    assert "CONVERGENCE: BLOCKED — external claim closure remains open." in result
    assert "staged structural debt remains open" not in result


def test_same_snapshot_claim_only_correction_migrates_without_structural_call(
    repo: Path, tmp_path: Path, monkeypatch,
) -> None:
    lineage_id = "legacy-claim-only-phase"
    stakes = "trusted local plan; correctness is high impact"
    parent = handlers.orientation.resolve_head(repo)
    snapshot = handlers.orientation.wrap_commit(
        repo, handlers.orientation.snapshot_tree(repo, parent), parent,
    )
    structural_snapshot = rc.digest(f"{PLAN}\0{snapshot}")
    claim_state = pc.with_debt(
        pc.empty_state(), pc.AuditError("claim discovery timed out"),
        round_no=4, plan_text=PLAN,
    )
    lineage = cc.Lineage(
        lineage_id, mode=cc.PLAN_MODE, rounds=4, claim_state=claim_state,
        review_state={
            "version": 1,
            "stakes_digest": rc.digest(stakes),
            "stakes": stakes,
            "phase": "correction",
            "snapshot_digest": structural_snapshot,
            "debt": [],
            "last_round": 4,
        },
    )
    cc.save_lineage(cc.default_state_root(), lineage)

    monkeypatch.setattr(
        handlers, "_verify_plan_claims",
        lambda plan_text, prior_state, **kwargs: (prior_state, "failed"),
    )
    monkeypatch.setattr(handlers.inert_git, "require_supported_version", lambda: (2, 50, 1))
    monkeypatch.setattr(handlers.eng, "require_evidence_profile", lambda engine: None)
    monkeypatch.setattr(handlers.orientation, "snapshot_tree", lambda *args, **kwargs: "tree")
    monkeypatch.setattr(handlers.orientation, "wrap_commit", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(
        handlers.eng.CodexEngine, "run",
        lambda *args, **kwargs: pytest.fail("migration must not call a structural reviewer"),
    )

    result = handlers.critique_plan(
        {
            "plan_text": PLAN, "repo_path": str(repo), "lineage": lineage_id,
            "round": 5, "stakes": stakes,
        },
        engine=handlers.eng.CodexEngine(), log_dir=tmp_path / "logs", now=lambda: "T5",
    )
    migrated = cc.load_lineage(
        cc.default_state_root(), lineage_id, stamp="T6", mode=cc.PLAN_MODE,
    )

    assert migrated.review_state["phase"] == "clear"
    assert migrated.rounds == 5
    assert migrated.claim_state["debt"]["reason"] == "claim discovery timed out"
    assert "STRUCTURAL STATE MIGRATED" in result
    assert "STRUCTURAL-PHASE: clear" in result
    assert "STRUCTURAL-CONVERGENCE: NOT-BLOCKED" in result
    assert "CONVERGENCE: BLOCKED — external claim closure remains open." in result
    assert "STAGED-ATTEMPTS: total=0" in result


def test_indexed_plan_binding_defaults_omission_but_rejects_unknown_key(
    tmp_path: Path,
) -> None:
    claim = _claim(evidence=[_source(), _source(url="https://docs.python.org/3/whatsnew/3.11.html")])
    audit = pc.parse_audit(_audit(claim), PLAN)
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        captures = {}
        for evidence_index, item in enumerate(audit.claims[0]["evidence"]):
            candidate = external_sources.CandidateSource(
                item["url"], item["title"], item["publisher"], item["source_kind"],
                item["authority_basis"], item["relation"],
            )
            captures[(0, evidence_index)] = external_sources.Capture(
                candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
                item["quote"],
            )
        batch = adapter._binding_batches(audit, captures)[0]
        passage = audit.claims[0]["evidence"][0]["quote"]
        omitted = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
            "bindings": [{
                "claim_index": 0, "evidence_index": 0, "usable": True,
                "location": "release record", "passage": passage,
            }],
        })
        assert adapter._parse_indexed_binding(omitted, batch, captures) == {
            (0, 0): ("release record", passage),
            (0, 1): handlers._OMITTED_BINDING,
        }

        unknown = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
            "bindings": [{
                "claim_index": 9, "evidence_index": 0, "usable": False,
                "location": None, "passage": None,
            }],
        })
        with pytest.raises(pc.AuditError, match="identity is invalid or duplicated"):
            adapter._parse_indexed_binding(unknown, batch, captures)
    finally:
        adapter.close()


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("location", handlers.MAX_BINDING_LOCATION_CHARS),
        ("passage", handlers.MAX_BINDING_PASSAGE_CHARS),
    ],
)
def test_binding_output_text_limits_are_exact(
    tmp_path: Path, field: str, limit: int,
) -> None:
    audit = pc.parse_audit(_audit(_claim()), PLAN)
    item = audit.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    text = "z" * (handlers.MAX_BINDING_PASSAGE_CHARS + 1)
    captures = {(0, 0): external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64, text,
    )}
    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        batch = adapter._binding_batches(audit, captures)[0]
        row = {
            "claim_index": 0, "evidence_index": 0, "usable": True,
            "location": "l", "passage": "z",
        }
        row[field] = "z" * limit
        accepted = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({"bindings": [row]})
        assert adapter._parse_indexed_binding(accepted, batch, captures)[(0, 0)]
        row[field] += "z"
        rejected = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({"bindings": [row]})
        with pytest.raises(pc.AuditError, match=f"{field} exceeds"):
            adapter._parse_indexed_binding(rejected, batch, captures)
    finally:
        adapter.close()


@pytest.mark.parametrize("field", ["claim_index", "evidence_index"])
@pytest.mark.parametrize("invalid_index", [True, 0.0, "0", None, [], {}])
def test_invalid_binding_index_type_uses_bounded_correction(
    tmp_path: Path, field: str, invalid_index: object,
) -> None:
    discovery = pc.parse_audit(_audit(_claim()), PLAN)
    item = discovery.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    captures = {(0, 0): external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        item["quote"],
    )}
    invalid_row = {
        "claim_index": 0, "evidence_index": 0, "usable": False,
        "location": None, "passage": None,
    }
    invalid_row[field] = invalid_index
    invalid = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
        "bindings": [invalid_row],
    })
    corrected = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
        "bindings": [{
            "claim_index": 0, "evidence_index": 0, "usable": False,
            "location": None, "passage": None,
        }],
    })
    engine = _RoleScript({"evidence-binding": [invalid, corrected]})
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    adapter.binding_engine = engine.for_role("evidence-binding")
    try:
        audit, reviews = adapter._bind_indexed(
            "session", discovery, captures, "m", "high", {},
        )
        assert len(reviews) == 2
        assert [role for role, _ in engine.calls] == [
            "evidence-binding", "evidence-binding",
        ]
        assert audit.claims[0]["verdict"] == "unverified"
    finally:
        adapter.close()


def test_binding_omission_survives_capture_attestation_and_reconciliation(
    tmp_path: Path, monkeypatch,
) -> None:
    second_anchor = "Python documentation also records the release date."
    plan = PLAN + "\n" + second_anchor + "\n"
    discovery_payload = _audit(
        _claim(),
        _claim(
            anchor=second_anchor,
            proposition=second_anchor,
            evidence=[_source(url="https://docs.python.org/3/whatsnew/3.11.html")],
        ),
    )
    discovery = pc.parse_audit(discovery_payload, plan)
    passage = discovery.claims[0]["evidence"][0]["quote"]
    binding = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
        "bindings": [{
            "claim_index": 0, "evidence_index": 0, "usable": True,
            "location": "release record", "passage": passage,
        }],
    })
    attestation = (
        '=== EVIDENCE ATTESTATION JSON ===\n'
        '{"attestations":[{"claim_index":0,"evidence_index":0,'
        '"publisher_authority":true,"authority_reason":"official release owner",'
        '"passage_entailment":true,"entailment_reason":"states the release date"}]}'
    )
    engine = _RoleScript({
        "evidence-discovery": [discovery_payload],
        "evidence-binding": [binding],
        "evidence-text": [attestation],
    })

    def capture_all(candidates, **kwargs):
        return [
            external_sources.Capture(
                candidate, candidate.url, 200, "text/html", "a" * 64,
                f"{index + 1:064x}", passage,
            )
            for index, candidate in enumerate(candidates)
        ]

    monkeypatch.setattr(handlers.external_sources, "capture_all", capture_all)
    ledger: list[dict] = []
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
        attempt_ledger=ledger,
    )
    try:
        review = adapter.run("audit", tmp_path, "m", "high", True)
        assert not review.error
        audit = pc.parse_audit(review.text, plan)
        state = pc.reconcile(
            {}, audit, lineage_id="omitted-binding", round_no=1, plan_text=plan,
        )
        assert [role for role, _ in engine.calls] == [
            "evidence-discovery", "evidence-binding", "evidence-text",
        ]
        assert [row["role"] for row in ledger] == [
            "claim-discovery", "claim-binding", "claim-attestation",
        ]
        records = {row["anchor"]: row for row in state["claims"].values()}
        assert records[PLAN.splitlines()[-1]]["verdict"] == "supported"
        assert records[second_anchor]["verdict"] == "unverified"
        omitted = records[second_anchor]["evidence"][0]
        assert omitted["relation"] == "context"
        assert omitted["location"] == "No binding row returned for captured source"
        assert omitted["quote"] == "The model omitted this captured-source binding."
        assert pc.is_blocked(state)
    finally:
        adapter.close()


def test_mixed_ordinary_and_expanded_sources_reach_full_context_attestation(
    tmp_path: Path, monkeypatch,
) -> None:
    second_anchor = "SQLite 3.45.0 was released on January 15, 2024."
    plan = PLAN + "\n" + second_anchor + "\n"
    second_passage = "SQLite version 3.45.0 was released on 2024-01-15."
    second_source = _source(
        url="https://sqlite.org/releaselog/3_45_0.html", quote=second_passage,
    )
    discovery_text = _audit(
        _claim(),
        _claim(
            anchor=second_anchor, proposition=second_anchor,
            evidence=[second_source],
        ),
    )
    first_passage = _source()["quote"]
    binding_rows = [
        handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({"bindings": [{
            "claim_index": 0, "evidence_index": 0, "usable": True,
            "location": "release record", "passage": first_passage,
        }]}),
        handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({"bindings": [{
            "claim_index": 1, "evidence_index": 0, "usable": True,
            "location": "release record", "passage": second_passage,
        }]}),
    ]

    def attestation(claim_index: int) -> str:
        return "=== EVIDENCE ATTESTATION JSON ===\n" + json.dumps({
            "attestations": [{
                "claim_index": claim_index, "evidence_index": 0,
                "publisher_authority": True, "authority_reason": "official publisher",
                "passage_entailment": True, "entailment_reason": "direct release record",
            }],
        })

    engine = _RoleScript({
        "evidence-discovery": [discovery_text],
        "evidence-binding": binding_rows,
        "evidence-text": [attestation(0), attestation(1)],
    })

    def capture_all(candidates, **kwargs):
        rows = list(candidates)
        return [
            external_sources.Capture(
                rows[0], rows[0].url, 200, "text/html", "a" * 64, "b" * 64,
                first_passage,
            ),
            external_sources.Capture(
                rows[1], rows[1].url, 200, "text/html", "c" * 64, "d" * 64,
                "x" * 450_000 + "\n" + second_passage,
            ),
        ]

    monkeypatch.setattr(handlers.external_sources, "capture_all", capture_all)
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
    )
    try:
        review = adapter.run("audit", tmp_path, "m", "high", True)
        assert not review.error
        assert [role for role, _ in engine.calls] == [
            "evidence-discovery", "evidence-binding", "evidence-binding",
            "evidence-text", "evidence-text",
        ]
        binding_prompts = [prompt for role, prompt in engine.calls if role == "evidence-binding"]
        assert len(binding_prompts[0]) <= handlers.MAX_PLAN_BINDING_BATCH_CHARS
        assert handlers.MAX_PLAN_BINDING_BATCH_CHARS < len(binding_prompts[1])
        attestation_prompts = [prompt for role, prompt in engine.calls if role == "evidence-text"]
        assert "complete_line_numbered_text" not in attestation_prompts[0]
        assert "complete_line_numbered_text" in attestation_prompts[1]
        assert second_passage in attestation_prompts[1]
        assert len(attestation_prompts[1]) <= handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS
        audited = pc.parse_audit(review.text, plan)
        assert [claim["verdict"] for claim in audited.claims] == ["supported", "supported"]
        assert audited.claims[1]["capture_attestations"][0]["text_sha256"] == "d" * 64
    finally:
        adapter.close()


def test_expanded_binding_rejection_is_source_local_with_durable_provenance(
    tmp_path: Path,
) -> None:
    discovery = pc.parse_audit(_audit(_claim()), PLAN)
    item = discovery.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    captures = {(0, 0): external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        "x" * 590_000 + "\n" + item["quote"],
    )}
    engine = _RoleScript({"evidence-binding": ["invalid", "still invalid"]})
    ledger: list[dict] = []
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
        attempt_ledger=ledger,
    )
    adapter.captures = captures
    adapter.binding_engine = engine.for_role("evidence-binding")
    try:
        bound, reviews = adapter._bind_indexed(
            "session", discovery, captures, "m", "high", {},
        )
        assert len(reviews) == 2
        assert [row["outcome"] for row in ledger] == [
            "validation-invalid", "validation-invalid",
        ]
        assert all(row.get("validation_issue") for row in ledger)
        assert all(row["validation_pointer"] == "/bindings" for row in ledger)
        assert all(row["raw_sha256"] and row["failure_detail_sha256"] for row in ledger)
        assert all(row["stderr_sha256"] and row["rejected_reply_sha256"] for row in ledger)
        assert [row["rejected_reply_excerpt"] for row in ledger] == [
            "invalid", "still invalid",
        ]
        attested = adapter._attest(bound, "m", "high")
        assert isinstance(attested, pc.Audit)
        persisted = pc.parse_audit(handlers._render_audit(attested), PLAN)
        claim = persisted.claims[0]
        assert claim["verdict"] == "unverified"
        assert claim["evidence"][0]["relation"] == "context"
        provenance = claim["capture_attestations"][0]
        assert provenance["content_sha256"] == "a" * 64
        assert provenance["text_sha256"] == "b" * 64
        assert provenance["status"] == 200
        assert "expected exactly one" in provenance["capture_error"]
        assert provenance["publisher_authority"] is False
        assert provenance["passage_entailment"] is False
        capture_row = claim["capture_provenance"][0]
        assert capture_row == {
            "evidence_index": 0,
            "requested_url": item["url"],
            "final_url": item["url"],
            "status": 200,
            "content_type": "text/html",
            "fallback_attempted": False,
            "content_sha256": "a" * 64,
            "text_sha256": "b" * 64,
            "error": "expected exactly one === PLAN EVIDENCE BINDING JSON === marker",
        }
    finally:
        adapter.close()


def test_expanded_attestation_failure_is_source_local_and_preserves_sibling(
    tmp_path: Path,
) -> None:
    second_anchor = "SQLite 3.45.0 was released on January 15, 2024."
    plan = PLAN + "\n" + second_anchor + "\n"
    second_source = _source(
        url="https://sqlite.org/releaselog/3_45_0.html",
        quote="SQLite version 3.45.0 was released on 2024-01-15.",
    )

    def provenance(url: str, content: str, text: str) -> list[dict[str, object]]:
        return [{
            "evidence_index": 0, "requested_url": url, "final_url": url, "status": 200,
            "content_type": "text/html", "fallback_attempted": False,
            "content_sha256": content, "text_sha256": text, "error": None,
        }]

    audit = pc.parse_audit(_audit(
        _claim(capture_provenance=provenance(_source()["url"], "a" * 64, "b" * 64)),
        _claim(
            anchor=second_anchor, proposition=second_anchor, evidence=[second_source],
            capture_provenance=provenance(second_source["url"], "c" * 64, "d" * 64),
        ),
    ), plan)
    ordinary = "=== EVIDENCE ATTESTATION JSON ===\n" + json.dumps({
        "attestations": [{
            "claim_index": 0, "evidence_index": 0,
            "publisher_authority": True, "authority_reason": "official publisher",
            "passage_entailment": True, "entailment_reason": "direct release record",
        }],
    })
    failed = Review(
        text="provider failed", session_ref=None, raw="raw provider channel", error=True,
        returncode=1, failure_detail="expanded attester failed", stderr="stderr channel",
    )
    engine = _RoleScript({"evidence-text": [ordinary, failed]})
    ledger: list[dict] = []
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=_repo(tmp_path), plan_repo_path=None,
        attempt_ledger=ledger,
    )
    first_candidate = external_sources.CandidateSource(
        **{key: _source()[key] for key in (
            "url", "title", "publisher", "source_kind", "authority_basis", "relation",
        )}
    )
    second_candidate = external_sources.CandidateSource(
        **{key: second_source[key] for key in (
            "url", "title", "publisher", "source_kind", "authority_basis", "relation",
        )}
    )
    adapter.captures = {
        (0, 0): external_sources.Capture(
            first_candidate, first_candidate.url, 200, "text/html", "a" * 64,
            "b" * 64, _source()["quote"],
        ),
        (1, 0): external_sources.Capture(
            second_candidate, second_candidate.url, 200, "text/html", "c" * 64,
            "d" * 64, "x" * 450_000 + "\n" + second_source["quote"],
        ),
    }
    adapter.expanded_captures.add((1, 0))
    try:
        result = adapter._attest(audit, "m", "high")
        assert isinstance(result, pc.Audit)
        assert [claim["verdict"] for claim in result.claims] == [
            "supported", "unverified",
        ]
        assert "expanded attester failed" in result.claims[1][
            "capture_attestations"
        ][0]["capture_error"]
        assert result.claims[1]["capture_provenance"][0]["error"] == (
            "expanded attester failed"
        )
        assert ledger[-1]["outcome"] == "failed"
        assert ledger[-1]["raw_sha256"] and ledger[-1]["stderr_sha256"]
    finally:
        adapter.close()


def test_explicit_unusable_binding_has_distinct_durable_provenance(
    tmp_path: Path,
) -> None:
    discovery = pc.parse_audit(_audit(_claim()), PLAN)
    item = discovery.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    captures = {(0, 0): external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        item["quote"],
    )}
    binding = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
        "bindings": [{
            "claim_index": 0, "evidence_index": 0, "usable": False,
            "location": None, "passage": None,
        }],
    })
    engine = _RoleScript({"evidence-binding": [binding]})
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    adapter.binding_engine = engine.for_role("evidence-binding")
    try:
        audit, reviews = adapter._bind_indexed(
            "session", discovery, captures, "m", "high", {},
        )
        assert len(reviews) == 1
        state = pc.reconcile(
            {}, audit, lineage_id="explicit-unusable", round_no=1, plan_text=PLAN,
        )
        record = next(iter(state["claims"].values()))
        assert record["verdict"] == "unverified"
        assert record["evidence"][0]["relation"] == "context"
        assert record["evidence"][0]["location"] == (
            "Captured source explicitly marked unusable"
        )
        assert record["evidence"][0]["quote"] == (
            "No usable captured-text passage was returned."
        )
        assert pc.is_blocked(state)
    finally:
        adapter.close()


def test_explicit_unusable_binding_preserves_capture_failure_provenance(
    tmp_path: Path,
) -> None:
    discovery = pc.parse_audit(_audit(_claim()), PLAN)
    item = discovery.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    captures = {(0, 0): external_sources.Capture(
        candidate, "http://127.0.0.1/private", 200, "text/plain", None, None, None,
        error="rejected final URL: non-public final address",
    )}
    binding = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
        "bindings": [{
            "claim_index": 0, "evidence_index": 0, "usable": False,
            "location": None, "passage": None,
        }],
    })
    engine = _RoleScript({"evidence-binding": [binding]})
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    adapter.binding_engine = engine.for_role("evidence-binding")
    try:
        audit, reviews = adapter._bind_indexed(
            "session", discovery, captures, "m", "high", {},
        )
        assert reviews == []
        state = pc.reconcile(
            {}, audit, lineage_id="capture-failed", round_no=1, plan_text=PLAN,
        )
        record = next(iter(state["claims"].values()))
        assert record["verdict"] == "unverified"
        assert record["evidence"][0]["relation"] == "context"
        assert record["evidence"][0]["location"] == "Server capture unavailable"
        assert record["evidence"][0]["quote"] == (
            "Server capture unavailable: rejected final URL: non-public final address"
        )
        assert record["capture_provenance"] == [{
            "evidence_index": 0,
            "requested_url": item["url"],
            "final_url": "http://127.0.0.1/private",
            "status": 200,
            "content_type": "text/plain",
            "fallback_attempted": False,
            "content_sha256": None,
            "text_sha256": None,
            "error": "rejected final URL: non-public final address",
        }]
        assert pc.is_blocked(state)
    finally:
        adapter.close()


def test_recorded_claim_binding_acceptance_is_narrow_and_complete() -> None:
    artifact = json.loads(
        (Path(__file__).parents[1] / "docs" / "claim_binding_acceptance_2026-08-14.json")
        .read_text(encoding="utf-8")
    )
    assert artifact["implementation_commit"] == (
        "0479336c647b026f023c8ee0a1a514f1148c229a"
    )
    assert artifact["provider"] == {
        "engine": "codex",
        "cli_version": "0.144.6",
        "model": "gpt-5.6-sol",
        "effort": "high",
        "web_discovery": True,
        "binding_web_access": False,
        "attestation_web_access": False,
    }
    assert artifact["claim_phase"]["counts"] == {
        "supported": 1, "refuted": 0, "unverified": 0,
    }
    assert artifact["claim_phase"]["debt"] is None
    assert artifact["claim_phase"]["claim"]["verdict"] == "supported"
    assert len(artifact["claim_phase"]["claim"]["evidence"][
        "captured_text_sha256"
    ]) == 64
    assert [row["role"] for row in artifact["attempts"]] == [
        "claim-discovery", "claim-binding", "claim-attestation",
    ]
    assert all(row["outcome"] == "completed" for row in artifact["attempts"])
    assert artifact["attempts"][0]["session_ref"] == artifact["attempts"][1][
        "session_ref"
    ]
    assert artifact["durable_artifacts"]["tool_returncode"] == 0
    assert artifact["durable_artifacts"]["tool_error"] is False
    controlled = artifact["controlled_omission"]
    assert controlled["implementation_commit"] == (
        "8e24587536ebf624bed93b3095bcaa967198ebae"
    )
    assert controlled["omitted_keys"] == [[1, 0]]
    assert [row["kind"] for row in controlled["attempts"]] == [
        "signed-in-provider", "controlled-omission", "signed-in-provider",
    ]
    assert controlled["durable_state"]["supported_claim"]["verdict"] == "supported"
    assert controlled["durable_state"]["omitted_claim"] == {
        "claim_id": "C-01c0486e7a",
        "verdict": "unverified",
        "relation": "context",
        "location": "No binding row returned for captured source",
        "quote": "The model omitted this captured-source binding.",
        "capture_attestations": [],
    }
    assert controlled["durable_state"]["blocked"] is True
    assert artifact["measurements"]["production_diff"] == {
        "files": [
            "src/paranoia_local/handlers.py",
            "src/paranoia_local/plan_claims.py",
        ],
        "added_lines": 48,
        "deleted_lines": 11,
        "net_lines": 37,
    }
    final = artifact["final_revision_acceptance"]
    assert final["implementation_commit"] == (
        "ac50c479dd536ba6d3e3e2253e9af321ba62fbdb"
    )
    assert final["model_calls"] == 3
    assert final["omitted_keys"] == [[1, 0]]
    assert final["capture_failed_keys"] == [[2, 0]]
    assert [row["kind"] for row in final["attempts"]] == [
        "signed-in-provider", "controlled-partial-binding", "signed-in-provider",
    ]
    assert [row["verdict"] for row in final["durable_state"]["claims"]] == [
        "supported", "unverified", "unverified",
    ]
    assert final["durable_state"]["claims"][1]["location"] == (
        "No binding row returned for captured source"
    )
    assert final["durable_state"]["claims"][2]["location"] == (
        "Server capture unavailable"
    )
    assert final["durable_state"]["blocked"] is True
    invalid = artifact["invalid_attestation_acceptance"]
    assert invalid["implementation_commit"] == (
        "ac50c479dd536ba6d3e3e2253e9af321ba62fbdb"
    )
    assert invalid["expected_parser_error"] == (
        "attestation row indices must be integers"
    )
    assert [row["kind"] for row in invalid["attempts"]] == [
        "signed-in-provider", "signed-in-provider", "controlled-boolean-identity",
    ]
    assert invalid["durable_state"]["blocked"] is True
    assert invalid["durable_state"]["claim_count"] == 0
    assert invalid["durable_state"]["debt"]["raw_sha256"] == invalid[
        "controlled_attestation_response_sha256"
    ]
    assert invalid["durable_state"]["debt"]["rejected_identity"] == {
        "claim_index": True, "evidence_index": 0,
    }


@pytest.mark.parametrize(("correction", "returncode", "diagnostic"), [
    (False, 124, "timed out after 420s"),
    (True, 127, "executable not found: codex"),
])
def test_binding_engine_failure_preserves_structured_diagnostics(
    tmp_path: Path, correction: bool, returncode: int, diagnostic: str,
) -> None:
    audit = pc.parse_audit(_audit(_claim()), PLAN)
    item = audit.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    capture = external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        item["quote"],
    )
    failed = Review(
        text="", session_ref="session" if correction else None, raw="",
        returncode=returncode, error=True, failure_detail=diagnostic,
        stderr=diagnostic,
    )
    replies = ([Review("invalid", "session", "provider stdout"), failed]
               if correction else [failed])

    class BindingEngine:
        def resume(self, *args, **kwargs):
            return replies.pop(0)

    adapter = handlers._CapturedClaimEngine(
        _RoleScript({}), plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    adapter.binding_engine = BindingEngine()
    try:
        with pytest.raises(pc.AuditError) as caught:
            adapter._bind_indexed(
                "session", audit, {(0, 0): capture}, "m", "high", {"timeout": 300},
            )
        debt = caught.value.debt(1)
        assert debt["returncode"] == returncode
        assert debt["rejected_excerpt"] == ""
        assert debt["failure_detail"] == diagnostic
        assert debt["stderr"] == diagnostic
        assert debt["failure_detail_sha256"] != debt["raw_sha256"]
        assert debt["stderr_sha256"] != debt["raw_sha256"]
    finally:
        adapter.close()


@pytest.mark.parametrize(("correction", "returncode", "diagnostic"), [
    (False, 124, "timed out after 420s"),
    (True, 127, "executable not found: codex"),
])
def test_outer_claim_verification_persists_binding_failure_channels(
    tmp_path: Path, monkeypatch, correction: bool, returncode: int, diagnostic: str,
) -> None:
    source = _source()
    candidate = external_sources.CandidateSource(
        source["url"], source["title"], source["publisher"], source["source_kind"],
        source["authority_basis"], source["relation"],
    )
    capture = external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        source["quote"],
    )
    monkeypatch.setattr(
        handlers.external_sources, "capture_all", lambda candidates, **kwargs: [capture],
    )
    failed = Review(
        text="", session_ref="binding-session" if correction else None, raw="",
        returncode=returncode, error=True, failure_detail=diagnostic, stderr=diagnostic,
    )
    binding = ([Review("invalid", "binding-session", "invalid binding"), failed]
               if correction else [failed])

    class FailureEngine:
        name = "codex"
        default_model = "test"
        native_web = True

        def __init__(self, role="default"):
            self.role = role

        def for_role(self, role):
            return FailureEngine(role)

        def run(self, *args, **kwargs):
            assert self.role == "evidence-discovery"
            text = _audit(_claim())
            return Review(text, "discovery-session", text)

        def resume(self, *args, **kwargs):
            assert self.role == "evidence-binding"
            return binding.pop(0)

    monkeypatch.setattr(handlers.eng, "CodexEngine", FailureEngine)
    state, status = handlers._verify_plan_claims(
        PLAN, pc.empty_state(), lineage_id="binding-failure", round_no=1,
        stakes="trusted local tool", engine=FailureEngine(), repo=_repo(tmp_path),
        model="m", effort="high", plan_repo_path=None, on_progress=None,
    )

    assert status == "failed"
    debt = state["debt"]
    assert debt["returncode"] == returncode
    assert debt["rejected_excerpt"] == ""
    assert debt["failure_detail"] == diagnostic
    assert debt["stderr"] == diagnostic
    assert debt["failure_detail_sha256"] != debt["raw_sha256"]
    assert debt["stderr_sha256"] != debt["raw_sha256"]


def test_plan_binding_demotes_a_redirect_to_ugc(tmp_path: Path) -> None:
    audit = pc.parse_audit(_audit(_claim()), PLAN)
    item = audit.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    capture = external_sources.Capture(
        candidate, "https://www.reddit.com/r/python/comments/example", 200,
        "text/html", "a" * 64, "b" * 64, item["quote"],
    )
    binding = (
        handlers.PLAN_BINDING_MARKER
        + '\n{"bindings":[{"claim_index":0,"evidence_index":0,"usable":true,'
        '"location":"post","passage":"'
        + item["quote"]
        + '"}]}'
    )
    engine = _RoleScript({"evidence-binding": [binding]})
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    adapter.binding_engine = engine.for_role("evidence-binding")
    adapter.captures = {(0, 0): capture}
    try:
        bound, _ = adapter._bind_indexed(
            "session", audit, adapter.captures, "m", "high", {"timeout": 300},
        )
        assert bound.claims[0]["verdict"] == "unverified"
        assert bound.claims[0]["evidence"][0]["source_kind"] == "ugc"
    finally:
        adapter.close()


def test_persistent_403_provenance_survives_claim_state_reload(tmp_path: Path) -> None:
    audit = pc.parse_audit(_audit(_claim()), PLAN)
    item = audit.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    capture = external_sources.Capture(
        candidate, "https://www.python.org/forbidden", 403, "text/html",
        None, None, None,
        "HTTP Error 403: Forbidden; browser-compatible retry attempted", True,
    )
    binding = (
        handlers.PLAN_BINDING_MARKER
        + '\n{"bindings":[{"claim_index":0,"evidence_index":0,"usable":false,'
        '"location":null,"passage":null}]}'
    )
    engine = _RoleScript({"evidence-binding": [binding]})
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=PLAN, repo=_repo(tmp_path), plan_repo_path=None,
    )
    adapter.binding_engine = engine.for_role("evidence-binding")
    try:
        bound, _ = adapter._bind_indexed(
            "session", audit, {(0, 0): capture}, "m", "high", {"timeout": 300},
        )
    finally:
        adapter.close()
    state = pc.reconcile(
        {}, bound, lineage_id="persistent-403", round_no=1, plan_text=PLAN,
    )
    reloaded = pc.normalize_state(json.loads(json.dumps(state)))
    evidence = next(iter(reloaded["claims"].values()))["evidence"][0]
    assert evidence["url"] == "https://www.python.org/forbidden"
    assert evidence["location"] == "Server capture unavailable"
    assert "HTTP Error 403" in evidence["quote"]
    assert "browser-compatible retry attempted" in evidence["quote"]
