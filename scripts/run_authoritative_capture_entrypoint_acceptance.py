#!/usr/bin/env python3
"""Run the public critique_plan lifecycle over ordinary and expanded evidence."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from paranoia_local import engines, handlers


SEC_URL = (
    "https://www.sec.gov/Archives/edgar/data/1639920/"
    "000163992025000003/ck0001639920-20241231.htm"
)
PYTHON_URL = "https://www.python.org/downloads/release/python-3110/"
PLAN = f"""# Evidence lifecycle acceptance

The implementation uses these two externally governed acceptance inputs:

- Python 3.11.0 was released on October 24, 2022. [Official release]({PYTHON_URL})
- Spotify reported 675 million monthly active users as of December 31, 2024. [2024 annual report]({SEC_URL})

Before implementation, verify both inputs against their linked primary sources. Preserve the
complete annual-report capture while binding the exact Spotify passage. Do not infer any broader
product or investment conclusion from either input.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=("codex", "claude"))
    parser.add_argument("--state-root")
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()
    engine = engines.CodexEngine() if args.engine == "codex" else engines.ClaudeEngine()
    state_root = (
        Path(args.state_root)
        if args.state_root else Path(tempfile.mkdtemp(prefix="paranoia-entrypoint-acceptance-"))
    )
    os.environ["PARANOIA_STATE_ROOT"] = str(state_root)
    lineage = f"authoritative-capture-entrypoint-{args.engine}-plan"
    started = time.monotonic()
    result = handlers.critique_plan(
        {
            "plan_text": PLAN,
            "repo_path": str(Path.cwd()),
            "class_closure": True,
            "claim_verification": True,
            "lineage": lineage,
            "round": args.round,
            "engine": args.engine,
            "model": engine.default_model,
            "effort": "high",
            "web_search": True,
            "stakes": (
                "trusted single operator and OS; plan, repository, fetched pages, and provider "
                "output are untrusted static data; false evidence support is high impact; "
                "visible recoverable blocking is acceptable; no hostile local race or multitenancy"
            ),
            "focus": "Acceptance run: verify the two external inputs and review correctness only.",
        },
        engine=engine,
        log_dir=state_root / "logs",
        on_progress=lambda message: print(f"[progress] {message}", flush=True),
    )
    state_path = state_root / "lineages" / f"{lineage}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    claims = list(state["claim_state"]["claims"].values())
    spotify = next(
        claim for claim in claims
        if any(row["url"] == SEC_URL for row in claim.get("evidence", []))
    )
    python = next(
        claim for claim in claims
        if any(row["url"] == PYTHON_URL for row in claim.get("evidence", []))
    )
    spotify_capture = next(
        row for row in spotify["capture_provenance"]
        if row["requested_url"] == SEC_URL and row["error"] is None
    )
    spotify_evidence_index = spotify_capture["evidence_index"]
    spotify_attestation = next(
        row for row in spotify.get("capture_attestations", [])
        if row["evidence_index"] == spotify_evidence_index
    )
    output = {
        "engine": args.engine,
        "model": engine.default_model,
        "lineage_rounds": state["rounds"],
        "claim_count": len(claims),
        "claim_debt": state["claim_state"].get("debt"),
        "python_verdict": python["verdict"],
        "spotify_verdict": spotify["verdict"],
        "spotify_extracted_text_sha256": spotify_capture["text_sha256"],
        "spotify_capture_error": spotify_capture["error"],
        "spotify_evidence_index": spotify_evidence_index,
        "spotify_source_rows": len(spotify["capture_provenance"]),
        "spotify_attested": bool(
            spotify_attestation["publisher_authority"]
            and spotify_attestation["passage_entailment"]
        ),
        "durable_reload": True,
        "result_has_claim_closure": "CLAIM-CLOSURE:" in result,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "state_root": str(state_root),
    }
    if not (
        output["python_verdict"] == "supported"
        and output["spotify_verdict"] == "supported"
        and output["spotify_attested"]
        and output["spotify_capture_error"] is None
    ):
        raise SystemExit("entrypoint acceptance failed: " + json.dumps(output))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
