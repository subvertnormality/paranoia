from __future__ import annotations

import json

import pytest

from paranoia_local import plan_claims as pc


def _research(events: list[dict]) -> str:
    return (
        "notes\n\n=== RESEARCH REGISTER ===\nEVENTS-JSON: "
        + json.dumps(events, separators=(",", ":"), sort_keys=True)
    )


def _add(**overrides) -> dict:
    event = {
        "op": "ADD",
        "temp_id": "new-1",
        "claim": "The repository already has a durable cache.",
        "kind": "fact",
        "assertion_mode": "asserted",
        "plan_anchor": {"first_span": "p000001", "last_span": "p000001"},
    }
    event.update(overrides)
    return event


def test_plan_spans_preserve_distinct_raw_identity_for_lossy_display_collisions() -> None:
    spans = pc.segment_plan(b"one:\xff\ntwo:\xfe\n", max_span_bytes=32)
    assert [span.display for span in spans] == ["one:\ufffd\n", "two:\ufffd\n"]
    assert spans[0].span_id != spans[1].span_id
    assert spans[0].sha256 != spans[1].sha256


def test_model_anchor_is_resolved_to_server_owned_raw_bounds_and_hash() -> None:
    raw = "alpha\n\u03b2eta\n".encode()
    spans = pc.segment_plan(raw, max_span_bytes=32)
    resolved = pc.resolve_anchor(
        {"first_span": spans[0].span_id, "last_span": spans[1].span_id}, spans
    )
    assert raw[resolved.start : resolved.end] == raw
    assert resolved.sha256 == pc.sha256(raw)


@pytest.mark.parametrize(
    "anchor",
    [
        {"first_span": "missing", "last_span": "p000001"},
        {"first_span": "p000002", "last_span": "p000001"},
    ],
)
def test_unknown_or_reversed_model_spans_fail_closed(anchor: dict) -> None:
    with pytest.raises(pc.ClaimRegisterError):
        pc.resolve_anchor(anchor, pc.segment_plan(b"one\ntwo\n"))


def test_research_register_rejects_duplicate_and_unknown_json_fields() -> None:
    duplicate = (
        '=== RESEARCH REGISTER ===\nEVENTS-JSON: '
        '[{"op":"ADD","op":"ADD","temp_id":"x","claim":"c","kind":"fact",'
        '"assertion_mode":"asserted","plan_anchor":{"first_span":"p000001",'
        '"last_span":"p000001"}}]'
    )
    with pytest.raises(pc.ClaimRegisterError, match="duplicate JSON key"):
        pc.parse_role_register(duplicate, pc.RESEARCH_ROLE)

    event = _add(extra="not allowed")
    with pytest.raises(pc.ClaimRegisterError, match="unknown fields"):
        pc.parse_role_register(_research([event]), pc.RESEARCH_ROLE)


def test_every_add_is_server_minted_pending_and_blocking() -> None:
    state = pc.ClaimState(lineage_id="plan")
    spans = pc.segment_plan(b"Do it.\n")
    events = pc.parse_role_register(_research([_add()]), pc.RESEARCH_ROLE)
    minted = pc.apply_events(state, events, role=pc.RESEARCH_ROLE, spans=spans)
    claim = state.claims[minted["new-1"]]
    assert claim.bearing == pc.BLOCKING
    assert claim.kind_classification == pc.PROPOSED
    assert claim.status == pc.UNCHECKED
    assert pc.blocking_claims(state) == [claim]


def test_kind_confirmation_must_come_from_an_independent_role() -> None:
    state, claim_id, spans = _state_with_claim()
    event = pc.Event("CONFIRM_KIND", {"op": "CONFIRM_KIND", "claim_id": claim_id,
                                      "kind": "decision", "reason": "user choice"})
    with pytest.raises(pc.ClaimTransitionError, match="may not emit"):
        pc.apply_events(state, [event], role=pc.RESEARCH_ROLE, spans=spans)
    pc.apply_events(state, [event], role=pc.STRUCTURAL_ROLE, spans=spans)
    assert state.claims[claim_id].status == pc.NOT_APPLICABLE
    assert not pc.blocking_claims(state)


def test_advisory_bearing_requires_evidence_and_completed_independent_check() -> None:
    state, claim_id, spans = _state_with_claim()
    pc.apply_events(
        state,
        [pc.Event("CONFIRM_KIND", {"op": "CONFIRM_KIND", "claim_id": claim_id,
                                   "kind": "fact", "reason": "premise"})],
        role=pc.STRUCTURAL_ROLE,
        spans=spans,
    )
    event = pc.Event("SET_BEARING", {"op": "SET_BEARING", "claim_id": claim_id,
                                     "bearing": "advisory", "evidence_ids": ["e1"],
                                     "reason": "no dependent step"})
    pc.apply_events(
        state, [event], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={"e1"}, independent_required=True,
    )
    assert state.claims[claim_id].bearing == pc.BLOCKING
    assert state.claims[claim_id].pending_transition == event.data
    assert pc.blocking_claims(state)
    digest = pc.event_digest(event)
    checks = [
        pc.VendorCheck("openai", "gpt", digest, ("e1",), True, "t1"),
        pc.VendorCheck("anthropic", "claude", digest, ("e1",), True, "t2"),
    ]
    pc.apply_events(
        state, [event], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={"e1"}, independent_required=True, vendor_checks=checks,
    )
    assert state.claims[claim_id].bearing == pc.ADVISORY
    assert not pc.blocking_claims(state)


def test_verified_claim_reblocks_if_persisted_check_provenance_is_tampered() -> None:
    state, claim_id, spans = _state_with_confirmed_fact()
    event = pc.Event("VERIFY", {"op": "VERIFY", "claim_id": claim_id,
                                "evidence_ids": ["e1"], "reason": "exact source"})
    digest = pc.event_digest(event)
    checks = [
        pc.VendorCheck("openai", "gpt", digest, ("e1",), True, "t1"),
        pc.VendorCheck("anthropic", "claude", digest, ("e1",), True, "t2"),
    ]
    pc.apply_events(state, [event], role=pc.VERIFIER_ROLE, spans=spans,
                    evidence_ids={"e1"}, independent_required=True, vendor_checks=checks)
    assert not pc.blocking_claims(state)
    state.claims[claim_id].independent_check["checks"][1]["event_digest"] = "tampered"
    assert pc.blocking_claims(state)


def _state_with_claim() -> tuple[pc.ClaimState, str, list[pc.PlanSpan]]:
    state = pc.ClaimState(lineage_id="plan")
    spans = pc.segment_plan(b"Do it.\n")
    minted = pc.apply_events(
        state, pc.parse_role_register(_research([_add()]), pc.RESEARCH_ROLE),
        role=pc.RESEARCH_ROLE, spans=spans,
    )
    return state, minted["new-1"], spans


def _state_with_confirmed_fact() -> tuple[pc.ClaimState, str, list[pc.PlanSpan]]:
    state, claim_id, spans = _state_with_claim()
    pc.apply_events(
        state,
        [pc.Event("CONFIRM_KIND", {"op": "CONFIRM_KIND", "claim_id": claim_id,
                                   "kind": "fact", "reason": "premise"})],
        role=pc.STRUCTURAL_ROLE,
        spans=spans,
    )
    return state, claim_id, spans
