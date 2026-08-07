from __future__ import annotations

import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from paranoia_local.external_evidence import (
    FetchLimits,
    NativeSearchProvider,
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

    def request(self, url, address, limits, deadline, on_bytes=None):
        self.calls.append((url, address))
        response = self.responses.pop(0)
        chunks = list(response.chunks)
        if on_bytes is not None:
            for chunk in chunks:
                on_bytes(len(chunk))
        return TransportResponse(
            response.status, response.headers, chunks, response.peer_ip
        )


def test_deep_search_json_is_a_recoverable_network_error() -> None:
    body = "[" * 2000 + "0" + "]" * 2000
    client = SafeHttpClient(resolver=lambda _host: [], transport=FakeTransport())
    provider = NativeSearchProvider(
        lambda _prompt, _timeout: "=== SEARCH CANDIDATES ===\nCANDIDATES-JSON: " + body,
        client,
    )
    with pytest.raises(NetworkEvidenceError, match="malformed JSON"):
        provider.search("test")


def test_native_search_uses_bounded_strict_candidate_output_without_an_endpoint() -> None:
    prompts: list[str] = []

    timeouts: list[int] = []

    def discover(prompt: str, timeout: int) -> str:
        prompts.append(prompt)
        timeouts.append(timeout)
        return (
            '=== SEARCH CANDIDATES ===\nCANDIDATES-JSON: '
            '[{"url":"https://docs.example.com/reference","title":"Official reference"}]'
        )

    client = SafeHttpClient(resolver=lambda host: [], transport=FakeTransport())
    provider = NativeSearchProvider(discover, client)
    attempts: list[int] = []
    charged: list[int] = []
    hits = provider.search(
        "neutral api version query", limit=2,
        on_attempt=lambda: attempts.append(1), on_bytes=charged.append,
    )

    assert [(hit.url, hit.title) for hit in hits] == [
        ("https://docs.example.com/reference", "Official reference")
    ]
    assert attempts == [1]
    assert sum(charged) == provider.last_response_size
    assert timeouts == [30]
    assert "primary or authoritative" in prompts[0]
    assert "supporting and contradicting" in prompts[0]
    assert "original artifact that actually defines the disputed item" in prompts[0]
    assert "include its own compact canonical record" in prompts[0]
    assert "distinct primary sources" in prompts[0]
    assert "compact canonical HTML or plain-text" in prompts[0]
    assert "Search results are leads, not evidence" in prompts[0]


def test_native_search_rejects_model_authority_labels_and_non_https_candidates() -> None:
    client = SafeHttpClient(resolver=lambda host: [], transport=FakeTransport())
    outputs = iter([
        '=== SEARCH CANDIDATES ===\nCANDIDATES-JSON: '
        '[{"url":"https://docs.example.com/","title":"Docs","source_class":"primary"}]',
        '=== SEARCH CANDIDATES ===\nCANDIDATES-JSON: '
        '[{"url":"http://docs.example.com/","title":"Docs"}]',
    ])
    provider = NativeSearchProvider(lambda _prompt, _timeout: next(outputs), client)

    with pytest.raises(NetworkEvidenceError, match="malformed"):
        provider.search("query")
    with pytest.raises(NetworkEvidenceError, match="HTTPS"):
        provider.search("query")


def test_native_search_does_not_round_up_a_subsecond_deadline() -> None:
    calls: list[int] = []
    client = SafeHttpClient(resolver=lambda host: [], transport=FakeTransport())
    provider = NativeSearchProvider(
        lambda _prompt, timeout: calls.append(timeout) or "", client,
    )

    with pytest.raises(NetworkEvidenceError, match="less than one second"):
        provider.search("query", limits=FetchLimits(total_timeout=0.5))
    assert calls == []


def test_dns_private_and_mixed_private_answers_are_rejected() -> None:
    transport = FakeTransport()
    client = SafeHttpClient(resolver=lambda host: ["93.184.216.34", "127.0.0.1"],
                            transport=transport)
    with pytest.raises(NetworkEvidenceError, match="non-public"):
        client.fetch("https://example.com/")
    assert not transport.calls


def test_dual_stack_dns_prefers_public_ipv4_for_common_ipv4_only_hosts() -> None:
    response = TransportResponse(
        200, {"content-type": "text/plain"}, [b"ok"], "104.18.20.81",
    )
    transport = FakeTransport(response)
    client = SafeHttpClient(
        resolver=lambda _host: ["2606:4700::6812:1451", "104.18.20.81"],
        transport=transport,
    )

    assert client.fetch("https://example.com/").body == b"ok"
    assert transport.calls == [("https://example.com/", "104.18.20.81")]


def test_dns_resolution_obeys_the_shared_total_deadline() -> None:
    def slow(_host: str) -> list[str]:
        time.sleep(0.05)
        return ["93.184.216.34"]

    client = SafeHttpClient(resolver=slow, transport=FakeTransport())
    started = time.monotonic()
    with pytest.raises(NetworkEvidenceError, match="DNS resolution exceeded"):
        client.fetch("https://example.com/", FetchLimits(total_timeout=0.01))
    assert time.monotonic() - started < 0.04


def test_transport_headers_and_body_share_the_total_deadline() -> None:
    class SlowTransport:
        def request(self, url, address, limits, deadline, on_bytes=None):
            time.sleep(0.3)
            return TransportResponse(200, {"content-type": "text/plain"}, [b"late"], address)

    client = SafeHttpClient(
        resolver=lambda _host: ["93.184.216.34"], transport=SlowTransport()
    )
    with pytest.raises(NetworkEvidenceError, match="request exceeded"):
        client.fetch("https://example.com/", FetchLimits(total_timeout=0.2))


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


def test_every_redirect_hop_and_body_is_accounted_before_following() -> None:
    transport = FakeTransport(
        TransportResponse(
            302, {"location": "https://example.com/final"}, [b"redirect-body"],
            "93.184.216.34",
        ),
        TransportResponse(200, {"content-type": "text/plain"}, [b"final"], "93.184.216.34"),
    )
    client = SafeHttpClient(
        resolver=lambda host: ["93.184.216.34"], transport=transport
    )
    attempts: list[int] = []
    charged: list[int] = []
    result = client.fetch(
        "https://example.com/start",
        on_attempt=lambda: attempts.append(1), on_bytes=charged.append,
    )
    assert result.body == b"final"
    assert len(attempts) == 2
    assert sum(charged) == len(b"redirect-body") + len(b"final")


def test_rejected_response_body_is_still_accounted() -> None:
    transport = FakeTransport(
        TransportResponse(
            500, {"content-type": "text/plain"}, [b"failed-body"], "93.184.216.34"
        )
    )
    client = SafeHttpClient(
        resolver=lambda host: ["93.184.216.34"], transport=transport
    )
    charged: list[int] = []
    with pytest.raises(NetworkEvidenceError, match="HTTP 500"):
        client.fetch("https://example.com/fail", on_bytes=charged.append)
    assert sum(charged) == len(b"failed-body")


def test_redirect_hops_consume_the_shared_fetch_attempt_budget() -> None:
    responses = [
        TransportResponse(
            302, {"location": "https://example.com/next"}, [], "93.184.216.34"
        )
        for _ in range(cv.MAX_FETCHES + 1)
    ]
    transport = FakeTransport(*responses)
    client = SafeHttpClient(
        resolver=lambda host: ["93.184.216.34"], transport=transport
    )
    budget = cv.EvidenceBudget()
    with pytest.raises(cv.EvidenceRequestError, match="fetch-attempt"):
        client.fetch(
            "https://example.com/start", FetchLimits(max_redirects=20),
            on_attempt=budget.debit_fetch, on_bytes=budget.debit_bytes,
        )
    assert len(transport.calls) == cv.MAX_FETCHES


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


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@example.com/", "file:///etc/passwd",
        "https://example.com/a\nFORGED", "https://example.com/é",
    ],
)
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


def test_expired_truth_source_stales_claim_after_separate_bearing_evidence(
    repo: Path, tmp_path: Path
) -> None:
    store = EvidenceStore(tmp_path / "separate-evidence")
    store.begin("separate-run")
    spans = pc.segment_plan(b"Premise.\n")
    state = pc.ClaimState("lineage")
    add = {
        "op": "ADD", "temp_id": "one",
        "kind": "fact", "assertion_mode": "asserted",
        "plan_anchor": {"first_span": "p000001", "last_span": "p000001"},
    }
    claim_id = pc.apply_events(
        state,
        pc.parse_role_register(
            "=== RESEARCH REGISTER ===\nEVENTS-JSON: " + json.dumps([add]),
            pc.RESEARCH_ROLE,
        ),
        role=pc.RESEARCH_ROLE, spans=spans,
    )["one"]
    pc.apply_events(
        state,
        [pc.Event("CONFIRM_KIND", {
            "op": "CONFIRM_KIND", "claim_id": claim_id,
            "kind": "fact", "reason": "premise",
        })],
        role=pc.STRUCTURAL_ROLE, spans=spans,
    )
    truth = cv._record(
        store, "separate-run", claim_id, "external", "https://truth.example/",
        b"truth", {
            "requested_url": "https://truth.example/",
            "final_url": "https://truth.example/",
            "retrieved_at": "2026-01-01T00:00:00+00:00",
            "http_status": 200, "media_type": "text/plain", "redirects": [],
            "publisher_domain": "truth.example",
            "source_class": "unclassified-external",
            "independence_groups": ["domain:truth.example"], "conflicts": [],
        },
    )
    bearing = cv._record(
        store, "separate-run", claim_id, "external", "https://bearing.example/",
        b"bearing", {
            "requested_url": "https://bearing.example/",
            "final_url": "https://bearing.example/",
            "retrieved_at": "2026-01-09T00:00:00+00:00",
            "http_status": 200, "media_type": "text/plain", "redirects": [],
            "publisher_domain": "bearing.example",
            "source_class": "unclassified-external",
            "independence_groups": ["domain:bearing.example"], "conflicts": [],
        },
    )
    pc.apply_events(
        state,
        [pc.Event("VERIFY", {
            "op": "VERIFY", "claim_id": claim_id,
            "evidence_ids": [truth.evidence_id], "reason": "source",
        })],
        role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={truth.evidence_id: claim_id},
    )
    bearing_event = pc.Event("SET_BEARING", {
        "op": "SET_BEARING", "claim_id": claim_id, "bearing": "advisory",
        "evidence_ids": [bearing.evidence_id], "reason": "not load bearing",
    })
    digest = pc.event_digest(bearing_event)
    pc.apply_events(
        state, [bearing_event], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={bearing.evidence_id: claim_id}, independent_required=True,
        vendor_checks=[
            pc.VendorCheck("one", "m1", digest, (bearing.evidence_id,), True, "t"),
            pc.VendorCheck("two", "m2", digest, (bearing.evidence_id,), True, "t"),
        ],
    )
    store.adopt(
        "lineage", "separate-run", [truth.blob_digest, bearing.blob_digest]
    )
    with PlanRepositorySnapshot.create(repo, run_id="separate-cache") as snapshot:
        valid = cv.validate_cached_records(
            [truth, bearing], snapshot=snapshot, store=store, state=state,
            now=datetime(2026, 1, 9, 1, tzinfo=timezone.utc),
        )
    assert [record.evidence_id for record in valid] == [bearing.evidence_id]
    assert state.claims[claim_id].status == pc.STALE
    assert pc.claim_blocks(state.claims[claim_id])
