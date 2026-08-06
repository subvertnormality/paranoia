from __future__ import annotations

import gzip
from datetime import datetime, timezone
from pathlib import Path

import pytest

from paranoia_local.external_evidence import (
    FetchLimits,
    NetworkEvidenceError,
    SafeHttpClient,
    TransportResponse,
)
from paranoia_local import claim_verification as cv, plan_claims as pc
from paranoia_local.evidence_store import EvidenceStore
from paranoia_local.plan_snapshot import PlanRepositorySnapshot


class FakeTransport:
    def __init__(self, *responses: TransportResponse) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def request(self, url, address, limits, deadline):
        self.calls.append((url, address))
        return self.responses.pop(0)


def test_dns_private_and_mixed_private_answers_are_rejected() -> None:
    transport = FakeTransport()
    client = SafeHttpClient(resolver=lambda host: ["93.184.216.34", "127.0.0.1"],
                            transport=transport)
    with pytest.raises(NetworkEvidenceError, match="non-public"):
        client.fetch("https://example.com/")
    assert not transport.calls


def test_connected_peer_must_equal_the_server_selected_public_address() -> None:
    response = TransportResponse(200, {"content-type": "text/plain"}, [b"ok"], "10.0.0.1")
    client = SafeHttpClient(resolver=lambda host: ["93.184.216.34"],
                            transport=FakeTransport(response))
    with pytest.raises(NetworkEvidenceError, match="connected peer"):
        client.fetch("https://example.com/")


def test_redirect_is_resolved_and_revalidated_per_hop() -> None:
    transport = FakeTransport(
        TransportResponse(302, {"location": "https://other.example/x"}, [], "93.184.216.34"),
        TransportResponse(200, {"content-type": "text/plain"}, [b"done"], "1.1.1.1"),
    )
    answers = {"example.com": ["93.184.216.34"], "other.example": ["1.1.1.1"]}
    client = SafeHttpClient(resolver=lambda host: answers[host], transport=transport)
    out = client.fetch("https://example.com/")
    assert out.final_url == "https://other.example/x" and out.body == b"done"
    assert transport.calls == [
        ("https://example.com/", "93.184.216.34"),
        ("https://other.example/x", "1.1.1.1"),
    ]


def test_compressed_and_decompressed_size_caps_are_both_enforced() -> None:
    body = gzip.compress(b"x" * 100)
    response = TransportResponse(
        200, {"content-type": "text/plain", "content-encoding": "gzip"}, [body],
        "93.184.216.34",
    )
    client = SafeHttpClient(resolver=lambda host: ["93.184.216.34"],
                            transport=FakeTransport(response))
    with pytest.raises(NetworkEvidenceError, match="decompressed"):
        client.fetch("https://example.com/", FetchLimits(max_decompressed_bytes=32))


@pytest.mark.parametrize("url", ["http://user:pass@example.com/", "file:///etc/passwd"])
def test_credentials_and_non_https_urls_are_rejected(url: str) -> None:
    client = SafeHttpClient(resolver=lambda host: [], transport=FakeTransport())
    with pytest.raises(NetworkEvidenceError):
        client.fetch(url)


def test_non_text_media_is_rejected() -> None:
    response = TransportResponse(200, {"content-type": "application/octet-stream"},
                                 [b"raw"], "93.184.216.34")
    client = SafeHttpClient(resolver=lambda host: ["93.184.216.34"],
                            transport=FakeTransport(response))
    with pytest.raises(NetworkEvidenceError, match="media type"):
        client.fetch("https://example.com/")


def test_expired_external_cache_is_removed_before_it_can_authorize_a_round(
    repo: Path, tmp_path: Path
) -> None:
    store = EvidenceStore(tmp_path / "evidence")
    body = b"old source"
    digest = store.stage("run", body)
    store.adopt("lineage", "run", [digest])
    record = cv.EvidenceRecord(
        evidence_id="eold", claim_id="claim", kind="external",
        source="https://example.com/", blob_digest=digest, source_sha256=digest,
        source_size=len(body), passage_start=0, passage_end=len(body),
        passage_sha256=digest, display_passage="old source",
        metadata={"retrieved_at": "2026-01-01T00:00:00+00:00"},
    )
    with PlanRepositorySnapshot.create(repo, run_id="ttl") as snapshot:
        valid = cv.validate_cached_records(
            [record], snapshot=snapshot, store=store,
            state=pc.ClaimState("lineage"),
            now=datetime(2026, 1, 9, tzinfo=timezone.utc),
        )
    assert valid == []
