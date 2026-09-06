"""Admit declared arbitration evidence before the existing correction budget expires.

This boundary checks declarations, not whether a vote is substantiated. The core
still owns SOURCE judgements and final/carried grounding. No citation is rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from . import arbitration as arb, evidence


@dataclass
class DecisionEvidence:
    """One decider's exact-snapshot resolver, reused across its bounded attempts."""

    repo: Path
    snapshot: str
    links: evidence.LinkResolver = field(init=False)

    def __post_init__(self) -> None:
        self.links = evidence.LinkResolver(self.repo, self.snapshot)

    def parse_reply(self, text: str, presentation: arb.Presentation) -> arb.Vote:
        return arb.parse_verdict(
            text, presentation, evidence_validator=self.validate_declarations,
        )

    def validate_declarations(self, values: Mapping[str, str]) -> None:
        # Keep one bounded diagnostic per field, so an oversized first declaration
        # cannot hide the other field from the single replacement opportunity.
        issues: list[str] = []
        for name in ("DECISIVE-CITATION", "CITATIONS"):
            raw = values[name].strip()
            if raw.upper() == "NONE":
                continue
            decisive = name == "DECISIVE-CITATION"
            limit = 1 if decisive else arb.MAX_CITATIONS
            tokens = [raw] if decisive else raw.split(",", limit)
            reasons: set[str] = set()
            if not raw or len(tokens) > limit:
                reasons.add(f"requires NONE or at most {limit} reference(s)")
            for token in tokens[:limit]:
                try:
                    if decisive:
                        reference = arb.parse_decisive_reference(token)
                    else:
                        parsed = arb.parse_citations(token, limit=1)
                        reference = parsed[0] if len(parsed) == 1 else None
                except ValueError:
                    reference = None
                if reference is None:
                    reasons.add("malformed declaration")
                elif isinstance(reference, arb.Citation):
                    if evidence.resolve_citation(
                        self.repo, reference, snapshot=self.snapshot,
                        links=self.links, context=arb.CONTEXT_LINES,
                    ) is None:
                        reasons.add("does not resolve to a literal file/line in the reviewed snapshot")
                # A well-formed SOURCE reference is a declaration only. Its packet
                # membership and authored judgements remain final substantiation's job.
            if reasons:
                issues.append(f"{name}: {'; '.join(sorted(reasons))}.")
        if issues:
            raise arb.ArbitrationError(
                "Invalid declared evidence. "
                + " ".join(issues)
                + " Use literal repository-relative path:positive-line (optionally "
                "snapshot-commit@path:positive-line); do not use absolute workspace "
                "paths or repair paths by normalization. DECISIVE-CITATION may instead "
                "be SOURCE:src-<16 lowercase hex digits>. Use NONE for absent evidence."
            )
