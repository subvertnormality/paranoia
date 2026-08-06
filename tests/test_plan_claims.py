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


def test_deep_register_json_is_a_recoverable_register_error() -> None:
    payload = "[" * 2000 + "0" + "]" * 2000
    text = "=== RESEARCH REGISTER ===\nEVENTS-JSON: " + payload
    with pytest.raises(pc.ClaimRegisterError, match="EVENTS-JSON is invalid"):
        pc.parse_role_register(text, pc.RESEARCH_ROLE)


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
        evidence_ids={"e1": claim_id}, independent_required=True,
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
        evidence_ids={"e1": claim_id}, independent_required=True, vendor_checks=checks,
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
                    evidence_ids={"e1": claim_id}, independent_required=True,
                    vendor_checks=checks)
    assert not pc.blocking_claims(state)
    state.claims[claim_id].truth_authorization["checks"][1]["event_digest"] = "tampered"
    assert pc.blocking_claims(state)


@pytest.mark.parametrize("op", ["VERIFY", "CONTRADICT", "SET_BEARING", "DISPUTE", "RESOLVE_DISPUTE"])
def test_evidence_from_another_claim_cannot_authorize_any_transition(op: str) -> None:
    state, first_id, spans = _state_with_confirmed_fact()
    minted = pc.apply_events(
        state,
        pc.parse_role_register(_research([_add(temp_id="second", claim="Second premise")]),
                               pc.RESEARCH_ROLE),
        role=pc.RESEARCH_ROLE, spans=spans,
    )
    second_id = minted["second"]
    pc.apply_events(
        state,
        [pc.Event("CONFIRM_KIND", {
            "op": "CONFIRM_KIND", "claim_id": second_id,
            "kind": "fact", "reason": "premise",
        })],
        role=pc.STRUCTURAL_ROLE, spans=spans,
    )
    data = {
        "op": op, "claim_id": second_id, "evidence_ids": ["for-first"],
        "reason": "wrong claim evidence",
    }
    if op == "SET_BEARING":
        data["bearing"] = "advisory"
    role = pc.STRUCTURAL_ROLE if op == "DISPUTE" else pc.VERIFIER_ROLE
    with pytest.raises(pc.ClaimTransitionError, match="exact claim"):
        pc.apply_events(
            state, [pc.Event(op, data)], role=role, spans=spans,
            evidence_ids={"for-first": first_id},
        )


def test_nonrequired_truth_check_does_not_erase_audited_advisory_authorization() -> None:
    state, claim_id, spans = _state_with_confirmed_fact()
    bearing = pc.Event("SET_BEARING", {
        "op": "SET_BEARING", "claim_id": claim_id, "bearing": "advisory",
        "evidence_ids": ["e1"], "reason": "not load bearing",
    })
    digest = pc.event_digest(bearing)
    checks = [
        pc.VendorCheck("one", "m1", digest, ("e1",), True, "t"),
        pc.VendorCheck("two", "m2", digest, ("e1",), True, "t"),
    ]
    pc.apply_events(
        state, [bearing], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={"e1": claim_id}, independent_required=True, vendor_checks=checks,
    )
    verify = pc.Event("VERIFY", {
        "op": "VERIFY", "claim_id": claim_id, "evidence_ids": ["e1"],
        "reason": "locally true",
    })
    pc.apply_events(
        state, [verify], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={"e1": claim_id}, independent_required=False,
    )
    claim = state.claims[claim_id]
    assert claim.bearing_authorization["status"] == "complete"
    assert claim.truth_authorization["status"] == "not-required"
    assert not pc.claim_blocks(claim)


@pytest.mark.parametrize("secondary_accepts", [True, False, None])
def test_required_defer_applies_only_after_two_vendor_acceptances(
    secondary_accepts: bool | None,
) -> None:
    spans = pc.segment_plan(b"Verify first.\nUse result.\n")
    state = pc.ClaimState("defer")
    add = _add(plan_anchor={"first_span": "p000001", "last_span": "p000001"})
    claim_id = pc.apply_events(
        state, pc.parse_role_register(_research([add]), pc.RESEARCH_ROLE),
        role=pc.RESEARCH_ROLE, spans=spans,
    )["new-1"]
    pc.apply_events(
        state,
        [pc.Event("CONFIRM_KIND", {
            "op": "CONFIRM_KIND", "claim_id": claim_id,
            "kind": "fact", "reason": "premise",
        })],
        role=pc.STRUCTURAL_ROLE, spans=spans,
    )
    event = pc.Event("DEFER", {
        "op": "DEFER", "claim_id": claim_id,
        "verification_anchor": {"first_span": "p000001", "last_span": "p000001"},
        "dependent_anchors": [
            {"first_span": "p000002", "last_span": "p000002"}
        ],
        "completion_evidence": "exit status zero",
        "failure_condition": "nonzero status",
        "stop_action": "stop rollout",
    })
    digest = pc.event_digest(event)
    checks = [pc.VendorCheck("one", "m1", digest, (), True, "t")]
    if secondary_accepts is not None:
        checks.append(pc.VendorCheck("two", "m2", digest, (), secondary_accepts, "t"))
    pc.apply_events(
        state, [event], role=pc.VERIFIER_ROLE, spans=spans,
        independent_required=True, vendor_checks=checks,
    )
    claim = state.claims[claim_id]
    if secondary_accepts is True:
        assert claim.status == pc.DEFERRED and not pc.claim_blocks(claim)
    else:
        assert claim.status == pc.UNVERIFIED and pc.claim_blocks(claim)
        assert claim.deferral_authorization["status"] == "pending"


def test_truth_and_bearing_keep_distinct_evidence_dependencies() -> None:
    state, claim_id, spans = _state_with_confirmed_fact()
    verify = pc.Event("VERIFY", {
        "op": "VERIFY", "claim_id": claim_id,
        "evidence_ids": ["truth"], "reason": "truth source",
    })
    pc.apply_events(
        state, [verify], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={"truth": claim_id},
    )
    bearing = pc.Event("SET_BEARING", {
        "op": "SET_BEARING", "claim_id": claim_id, "bearing": "advisory",
        "evidence_ids": ["bearing"], "reason": "no dependent step",
    })
    digest = pc.event_digest(bearing)
    checks = [
        pc.VendorCheck("one", "m1", digest, ("bearing",), True, "t"),
        pc.VendorCheck("two", "m2", digest, ("bearing",), True, "t"),
    ]
    pc.apply_events(
        state, [bearing], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={"bearing": claim_id}, independent_required=True,
        vendor_checks=checks,
    )
    claim = state.claims[claim_id]
    assert claim.truth_evidence_ids == ["truth"]
    assert claim.bearing_evidence_ids == ["bearing"]
    assert claim.evidence_ids == ["truth", "bearing"]


def test_invalid_required_truth_transition_cannot_leave_a_decision_nonblocking() -> None:
    state, claim_id, spans = _state_with_claim()
    pc.apply_events(
        state,
        [pc.Event("CONFIRM_KIND", {
            "op": "CONFIRM_KIND", "claim_id": claim_id,
            "kind": "decision", "reason": "chosen design",
        })],
        role=pc.STRUCTURAL_ROLE, spans=spans,
    )
    event = pc.Event("VERIFY", {
        "op": "VERIFY", "claim_id": claim_id,
        "evidence_ids": ["e1"], "reason": "invalid truth transition",
    })
    digest = pc.event_digest(event)
    with pytest.raises(pc.ClaimTransitionError, match="confirmed factual"):
        pc.apply_events(
            state, [event], role=pc.VERIFIER_ROLE, spans=spans,
            evidence_ids={"e1": claim_id}, independent_required=True,
            vendor_checks=[pc.VendorCheck("one", "m", digest, ("e1",), True, "t")],
        )
    claim = state.claims[claim_id]
    claim.pending_transition = event.data
    assert pc.claim_blocks(claim), "persisted pending state must block even for decisions"


def test_distinct_transition_cannot_erase_pending_independent_authorization() -> None:
    state, claim_id, spans = _state_with_confirmed_fact()
    pending = pc.Event("SET_BEARING", {
        "op": "SET_BEARING", "claim_id": claim_id, "bearing": "advisory",
        "evidence_ids": ["e1"], "reason": "pending audit",
    })
    pc.apply_events(
        state, [pending], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={"e1": claim_id}, independent_required=True,
        vendor_checks=[],
    )
    verify = pc.Event("VERIFY", {
        "op": "VERIFY", "claim_id": claim_id,
        "evidence_ids": ["e2"], "reason": "different transition",
    })
    with pytest.raises(pc.ClaimTransitionError, match="different independently"):
        pc.apply_events(
            state, [verify], role=pc.VERIFIER_ROLE, spans=spans,
            evidence_ids={"e2": claim_id},
        )
    assert state.claims[claim_id].pending_transition == pending.data


def test_null_model_anchor_is_a_correctable_register_error() -> None:
    state = pc.ClaimState("null-anchor")
    spans = pc.segment_plan(b"Plan.\n")
    event = pc.Event("ADD", {
        "op": "ADD", "temp_id": "bad", "claim": "Premise", "kind": "fact",
        "assertion_mode": "asserted", "plan_anchor": None,
    })
    with pytest.raises(pc.ClaimRegisterError, match="must be an object"):
        pc.apply_events(state, [event], role=pc.RESEARCH_ROLE, spans=spans)


def test_dispute_resolution_names_and_applies_the_audited_outcome() -> None:
    state, claim_id, spans = _state_with_confirmed_fact()
    pc.apply_events(
        state,
        [pc.Event("DISPUTE", {
            "op": "DISPUTE", "claim_id": claim_id,
            "evidence_ids": ["e1"], "reason": "conflict",
        })],
        role=pc.STRUCTURAL_ROLE, spans=spans, evidence_ids={"e1": claim_id},
    )
    event = pc.Event("RESOLVE_DISPUTE", {
        "op": "RESOLVE_DISPUTE", "claim_id": claim_id,
        "outcome": "verified", "evidence_ids": ["e2"], "reason": "resolved",
    })
    digest = pc.event_digest(event)
    checks = [
        pc.VendorCheck("one", "m1", digest, ("e2",), True, "t"),
        pc.VendorCheck("two", "m2", digest, ("e2",), True, "t"),
    ]
    pc.apply_events(
        state, [event], role=pc.VERIFIER_ROLE, spans=spans,
        evidence_ids={"e2": claim_id}, independent_required=True,
        vendor_checks=checks,
    )
    claim = state.claims[claim_id]
    assert claim.status == pc.VERIFIED and not pc.claim_blocks(claim)
    assert claim.dispute_authorization["event_digest"] == digest


@pytest.mark.parametrize("raw", [[], "", 0, False])
def test_falsey_non_object_persisted_claim_state_is_rejected(raw: object) -> None:
    with pytest.raises(pc.ClaimRegisterError, match="must be an object"):
        pc.state_from_json("corrupt", raw)  # type: ignore[arg-type]


def test_inconsistent_persisted_supersession_is_rejected() -> None:
    state, claim_id, _spans = _state_with_confirmed_fact()
    claim = state.claims[claim_id]
    claim.status = pc.SUPERSEDED
    claim.pending_replacement_id = "missing"
    claim.superseded_by = "missing"
    with pytest.raises(pc.ClaimRegisterError, match="supersession graph"):
        pc.state_from_json("plan", pc.state_to_json(state))


def test_stale_confirmed_decision_remains_blocking_after_reload() -> None:
    state, claim_id, spans = _state_with_claim()
    pc.apply_events(
        state, [pc.Event("CONFIRM_KIND", {
            "op": "CONFIRM_KIND", "claim_id": claim_id,
            "kind": "decision", "reason": "choice",
        })], role=pc.STRUCTURAL_ROLE, spans=spans,
    )
    state.claims[claim_id].status = pc.STALE
    loaded = pc.state_from_json("plan", pc.state_to_json(state))
    assert pc.claim_blocks(loaded.claims[claim_id])


def test_overlapping_anchor_occurrences_are_ambiguous() -> None:
    spans = pc.segment_plan(b"aaaa")
    state = pc.ClaimState("overlap")
    claim_id = pc.apply_events(
        state, pc.parse_role_register(_research([_add()]), pc.RESEARCH_ROLE),
        role=pc.RESEARCH_ROLE, spans=spans,
    )["new-1"]
    pc.reconcile_plan(state, b"aaaaa", pc.segment_plan(b"aaaaa"))
    assert state.claims[claim_id].status == pc.STALE


def test_pending_transition_is_rendered_for_fresh_verifier_recovery() -> None:
    state, claim_id, _spans = _state_with_confirmed_fact()
    state.claims[claim_id].pending_transition = {
        "op": "VERIFY", "claim_id": claim_id,
        "evidence_ids": ["e1"], "reason": "retry me",
    }
    rendered = pc.render_claim_summary(
        pc.state_from_json("plan", pc.state_to_json(state))
    )
    assert '"pending_transition":{"claim_id"' in rendered
    assert '"reason":"retry me"' in rendered


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
