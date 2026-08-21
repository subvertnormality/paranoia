#!/usr/bin/env python3
"""Live acceptance for complete-packet binding of a long official SEC filing."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from paranoia_local import engines, external_sources, handlers, plan_claims as pc


URL = (
    "https://www.sec.gov/Archives/edgar/data/1639920/"
    "000163992025000003/ck0001639920-20241231.htm"
)
PROPOSITION = "Spotify had 675 million monthly active users as of December 31, 2024."


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=("codex", "claude"))
    args = parser.parse_args()
    engine = engines.CodexEngine() if args.engine == "codex" else engines.ClaudeEngine()
    model = engine.default_model
    cli_version = ".".join(str(part) for part in engines._cli_version(engine.binary))
    started = time.monotonic()
    candidate = external_sources.CandidateSource(
        URL, "Spotify Technology S.A. 2024 Annual Report", "Spotify Technology S.A.",
        "primary", "Spotify's SEC-filed annual report", "supports_claim",
    )
    capture = external_sources.capture(candidate, deadline=time.monotonic() + 120)
    if not capture.usable:
        raise SystemExit(f"capture failed: {capture.error}")
    plan = f"# Acceptance\n\n{PROPOSITION}\n"
    claim = {
        "kind": "fact", "scope": "external", "anchor": PROPOSITION,
        "proposition": PROPOSITION, "prior_claim_id": None, "verdict": "supported",
        "evidence": [{
            "url": URL, "title": candidate.title, "publisher": candidate.publisher,
            "source_kind": candidate.source_kind,
            "authority_basis": candidate.authority_basis,
            "location": "annual report", "quote": (
                "MAUs were 675 million as of December 31, 2024."
            ),
            "relation": candidate.relation,
        }],
        "replacement": None, "rationale": "Official issuer filing states the metric.",
    }
    discovery = pc.parse_audit(
        pc.AUDIT_MARKER + "\n" + json.dumps({
            "claims": [claim],
            "coverage": {
                "sections_scanned": 1, "omitted_nonfacts": 0,
                "prior_assessments": [], "prior_dispositions": [], "notes": "complete",
            },
        }),
        plan,
    )
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=plan, repo=Path.cwd(), plan_repo_path=None,
        deadline=time.monotonic() + handlers.PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC,
    )
    try:
        adapter.captures = {(0, 0): capture}
        adapter.binding_engine = engine.for_role(engines.ROLE_BINDING)
        bootstrap = adapter.binding_engine.run(
            "Reply with exactly READY.", adapter.launch, model, "high", False, timeout=600,
        )
        if bootstrap.error or not bootstrap.session_ref:
            raise SystemExit(f"binding bootstrap failed: {bootstrap.failure_detail}")
        batches = adapter._binding_batches(discovery, adapter.captures)
        binding_prompt_chars = [
            len(adapter._binding_prompt(json.dumps(batch, ensure_ascii=False, separators=(",", ":"))))
            for batch in batches
        ]
        binding_prompt_sha256 = [
            digest(adapter._binding_prompt(
                json.dumps(batch, ensure_ascii=False, separators=(",", ":")),
            ))
            for batch in batches
        ]
        bound, binding_reviews = adapter._bind_indexed(
            bootstrap.session_ref, discovery, adapter.captures, model, "high", {},
        )
        initial_binding_issue = None
        if len(binding_reviews) > 1:
            try:
                adapter._parse_indexed_binding(
                    binding_reviews[0].text, batches[0], adapter.captures,
                )
            except pc.AuditError as error:
                initial_binding_issue = str(error)
        rendered_binding = json.dumps(
            batches[0], ensure_ascii=False, separators=(",", ":"),
        )
        correction_prompt_sha256 = (
            digest(adapter._binding_prompt(
                rendered_binding,
                pc.bounded_diagnostic(initial_binding_issue)[
                    :handlers.MAX_BINDING_DIAGNOSTIC_CHARS
                ],
            ))
            if initial_binding_issue else None
        )
        item = bound.claims[0]["evidence"][0]
        attestation_item = {
            "claim_index": 0, "evidence_index": 0, "proposition": PROPOSITION,
            "publisher": item["publisher"], "authority_basis": item["authority_basis"],
            "relation": item["relation"], "location": item["location"],
            "passage": item["quote"],
            "capture": {
                "final_url": capture.final_url, "status": capture.status,
                "content_type": capture.content_type,
                "content_sha256": capture.content_sha256,
                "text_sha256": capture.text_sha256,
                "complete_line_numbered_text": external_sources.numbered_text(capture.text or ""),
            },
        }
        attestation_prompt_chars = len(adapter._attestation_prompt([attestation_item]))
        worst_attestation_item = dict(attestation_item)
        worst_attestation_item["location"] = "\x01" * handlers.MAX_BINDING_LOCATION_CHARS
        worst_attestation_item["passage"] = "\x01" * handlers.MAX_BINDING_PASSAGE_CHARS
        worst_rendered = json.dumps(
            [worst_attestation_item], ensure_ascii=False, separators=(",", ":"),
        )
        preflight = {
            "binding_initial_characters": binding_prompt_chars[0],
            "binding_correction_characters": len(adapter._binding_prompt(
                rendered_binding, "x" * handlers.MAX_BINDING_DIAGNOSTIC_CHARS,
            )),
            "attestation_initial_worst_case_characters": len(
                adapter._attestation_prompt([worst_attestation_item])
            ),
            "attestation_correction_worst_case_characters": len(
                adapter._attestation_correction_prompt(
                    worst_rendered, "x" * handlers.MAX_BINDING_DIAGNOSTIC_CHARS,
                )
            ),
            "configured_ceiling": handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS,
        }
        attested = adapter._attest(bound, model, "high")
        if isinstance(attested, engines.Review):
            raise SystemExit(f"attestation failed: {attested.text}")
        evidence = attested.claims[0]["capture_attestations"][0]
        if (
            attested.claims[0]["verdict"] != "supported"
            or evidence["publisher_authority"] is not True
            or evidence["passage_entailment"] is not True
            or evidence.get("capture_error")
        ):
            raise SystemExit(
                "live acceptance did not establish authoritative support: "
                + json.dumps(evidence, ensure_ascii=False)
            )
        print(json.dumps({
            "engine": args.engine, "model": model, "cli_version": cli_version, "url": URL,
            "extracted_characters": len(capture.text or ""),
            "content_sha256": capture.content_sha256, "text_sha256": capture.text_sha256,
            "expanded": (0, 0) in adapter.expanded_captures,
            "binding_prompt_characters": binding_prompt_chars,
            "binding_prompt_sha256": binding_prompt_sha256,
            "binding_correction_prompt_sha256": correction_prompt_sha256,
            "attestation_prompt_characters": attestation_prompt_chars,
            "attestation_prompt_sha256": digest(
                adapter._attestation_prompt([attestation_item])
            ),
            "bootstrap_reply_sha256": digest(bootstrap.text),
            "binding_reply_sha256": [digest(review.text) for review in binding_reviews],
            "binding_raw_sha256": [digest(review.raw) for review in binding_reviews],
            "attestation_raw_sha256": digest(adapter.attestation_raw),
            "binding_calls": len(binding_reviews), "total_adapter_model_calls": adapter.model_calls,
            "binding_validation_retries": max(0, len(binding_reviews) - len(batches)),
            "initial_binding_issue": initial_binding_issue,
            "verdict": attested.claims[0]["verdict"],
            "publisher_authority": evidence["publisher_authority"],
            "passage_entailment": evidence["passage_entailment"],
            "production_preflight_measurement": preflight,
            "passage": item["quote"], "elapsed_seconds": round(time.monotonic() - started, 3),
        }, ensure_ascii=False, indent=2))
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
