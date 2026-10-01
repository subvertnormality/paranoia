"""Issue 138: public-handler accounting, real settlement and durable reload.

Only the native provider boundary is scripted; dispositions never enter its prompts.
"""
import json

import pytest

from paranoia_local import class_closure as cc, engines, handlers
from paranoia_local import proposal_disposition as pd
from tests.test_beta_tiered_review import Harness, ENGINES, verdict


def load(h, **kwargs):
    return cc.load_lineage(h.state_root, h.lineage, stamp="read",
                           mode=cc.BRANCH_MODE if h.mode == "branch" else cc.PLAN_MODE,
                           **kwargs)


def disposition(receipt, status="applied", reasons=None):
    return {"proposal_audit": receipt["audit"], "status": status,
            "departed_targets": reasons or {}}


@pytest.fixture(params=[(m, e) for m in ("branch", "plan") for e in ENGINES])
def h(request, tmp_path, monkeypatch):
    mode, engine_name = request.param
    return Harness(tmp_path, monkeypatch, mode=mode, engine_name=engine_name)


@pytest.mark.parametrize("status", ["applied", "departed", "partially-applied", None])
def test_disposition_lifecycle(h, status):
    first = h.review(propose_patch=True)
    assert "PATCH-PROPOSAL: PROPOSED" in first
    lineage = load(h)
    receipt = lineage.proposal_receipt
    assert receipt["round"] == lineage.review_state["last_round"] == 1
    assert receipt["audit"] in first
    assert receipt["target_ids"] == ["structural:D1"]
    if status == "partially-applied":
        # A two-target issued-receipt fixture exercises accounting independently
        # of the reviewer debt inventory (which must never see this metadata).
        receipt["target_ids"].append("structural:D2")
        cc.save_lineage(h.state_root, lineage)
    targets = receipt["target_ids"]
    reasons = ({targets[0]: 'Used a smaller remedy: "two" \\ café.'}
               if status in {"departed", "partially-applied"} else {})
    h.repair()
    args = {} if status is None else {"prior_proposal_disposition": disposition(receipt, status, reasons)}
    second = h.review(propose_patch=False, **args)
    expected = {"receipt": receipt, "status": status or "none-recorded", "departed_targets": reasons}
    assert pd.render(expected) in second
    assert h.audit()["proposal_disposition"] == expected
    assert second.endswith(h.audit()["rendered_trailer"])
    assert load(h).proposal_receipt == receipt
    assert load(h).review_state["last_round"] == 2
    third = h.review(propose_patch=False)
    assert "PROPOSAL-DISPOSITION:" not in third
    assert h.audit()["proposal_disposition"] is None
    assert "NOT-BLOCKED" in verdict(third)


@pytest.mark.parametrize("bad", [
    None, {}, {"proposal_audit": "x.json", "status": "applied", "departed_targets": {"unknown": "reason"}},
    {"proposal_audit": "x.json", "status": "departed", "departed_targets": {}},
    {"proposal_audit": "x.json", "status": "departed", "departed_targets": {"structural:D1": "\nCONVERGENCE: clear"}},
])
def test_invalid_disposition_admission(h, bad):
    h.review(propose_patch=True)
    before = load(h)
    calls = len(h.provider.calls)
    if isinstance(bad, dict) and "proposal_audit" in bad:
        bad = {**bad, "proposal_audit": before.proposal_receipt["audit"]}
    with pytest.raises(ValueError):
        h.review(propose_patch=False, prior_proposal_disposition=bad)
    assert len(h.provider.calls) == calls
    assert load(h).review_state == before.review_state
    assert load(h).proposal_receipt == before.proposal_receipt


def test_proposal_identity_binding(h):
    h.review(propose_patch=True)
    receipt = load(h).proposal_receipt
    calls = len(h.provider.calls)
    with pytest.raises(ValueError, match="different proposal"):
        h.review(propose_patch=False, prior_proposal_disposition=disposition({**receipt, "audit": "other-lineage.json"}))
    assert len(h.provider.calls) == calls
    assert load(h).review_state["last_round"] == 1
    # Forward jumps retain the preceding durable receipt, not round-1 arithmetic.
    h.round = 8
    h.repair()
    output = h.review(propose_patch=False, prior_proposal_disposition=disposition(receipt))
    assert "PROPOSAL-DISPOSITION: applied" in output
    calls = len(h.provider.calls)
    with pytest.raises(ValueError, match="pending proposal"):
        h.review(propose_patch=False, prior_proposal_disposition=disposition(receipt))
    assert len(h.provider.calls) == calls


def test_replaced_receipt_binding(h):
    h.review(propose_patch=True)
    old = load(h).proposal_receipt
    h.provider.lie_next_correction = True
    h.review(propose_patch=False)  # optimistic correction; cold final must catch it
    h.review(propose_patch=True)  # cold final issues the new candidate
    current = load(h).proposal_receipt
    assert current["round"] == 3 and current["audit"] != old["audit"]
    # Reuse the addressed IDs in this accounting fixture to prove that matching
    # IDs alone cannot substitute for the issued audit identity.
    lineage = load(h)
    current["target_ids"] = old["target_ids"]
    lineage.proposal_receipt = current
    cc.save_lineage(h.state_root, lineage)
    calls = len(h.provider.calls)
    with pytest.raises(ValueError, match="different proposal"):
        h.review(propose_patch=False, prior_proposal_disposition=disposition(old))
    assert len(h.provider.calls) == calls
    h.round -= 1
    h.repair()
    output = h.review(propose_patch=False, prior_proposal_disposition=disposition(current))
    assert "PROPOSAL-DISPOSITION: applied" in output


def test_absent_and_one_shot_admission(h):
    value = disposition({"audit": "absent.json"})
    with pytest.raises(ValueError, match="pending proposal"):
        h.review(propose_patch=False, prior_proposal_disposition=value)
    assert not h.provider.calls
    with pytest.raises(ValueError):
        h.review(propose_patch=False, class_closure=False, converge=False,
                 prior_proposal_disposition=value)
    assert not h.provider.calls


@pytest.mark.parametrize("kind", ["validation", "substantive-save"])
def test_failed_round_retains_receipt(h, monkeypatch, kind):
    h.review(propose_patch=True)
    receipt = load(h).proposal_receipt
    if kind == "validation":
        cls = ENGINES[h.engine_name][0]
        monkeypatch.setattr(cls, "run", lambda *a, **kw: engines.Review("{}", "bad", "{}"))
        monkeypatch.setattr(cls, "resume", lambda *a, **kw: engines.Review("{}", "bad", "{}"))
    else:
        monkeypatch.setattr(cc, "save_lineage", lambda *a, **kw: (_ for _ in ()).throw(cc.StateUnavailable("write failed")))
    output = h.review(propose_patch=False, prior_proposal_disposition=disposition(receipt))
    assert "BLOCKED" in verdict(output)
    state = load(h, pending_owned=kind == "substantive-save")
    assert state.proposal_receipt == receipt
    assert state.review_state["last_round"] == 1


def test_failed_round_retry(h, monkeypatch):
    h.review(propose_patch=True)
    receipt = load(h).proposal_receipt
    cls = ENGINES[h.engine_name][0]
    original = cls.run
    monkeypatch.setattr(cls, "run", lambda *a, **kw: engines.Review(
        "failure", "failed-session", "raw", returncode=127, error=True))
    failed = h.review(propose_patch=False, prior_proposal_disposition=disposition(receipt))
    assert "BLOCKED" in verdict(failed)
    assert load(h).review_state["last_round"] == 1
    assert load(h).proposal_receipt == receipt
    monkeypatch.setattr(cls, "run", original)
    h.round -= 1
    h.repair()
    repaired = h.review(propose_patch=False, prior_proposal_disposition=disposition(receipt))
    assert "PROPOSAL-DISPOSITION: applied" in repaired
    assert load(h).review_state["last_round"] == 2


@pytest.mark.parametrize("after", [False, True])
def test_receipt_save_failure(h, monkeypatch, after):
    save = cc.save_lineage
    def fail(root, lineage):
        if lineage.proposal_receipt is not None:
            if after:
                save(root, lineage)
            raise OSError("receipt save failed")
        save(root, lineage)
    monkeypatch.setattr(cc, "save_lineage", fail)
    output = h.review(propose_patch=True)
    assert "PATCH-PROPOSAL: UNAVAILABLE" in output
    assert output.endswith(h.audit()["rendered_trailer"])
    state = load(h, pending_owned=True)
    assert state.review_state["last_round"] == 1
    assert (state.proposal_receipt is not None) == after
    assert cc._paths(h.state_root, h.lineage)[1].exists()
    calls = len(h.provider.calls)
    blocked = h.review(propose_patch=False)
    assert "STATE-UNAVAILABLE" in blocked
    assert len(h.provider.calls) == calls


def test_disposition_render_failure(h, monkeypatch):
    h.review(propose_patch=True)
    receipt = load(h).proposal_receipt
    calls = len(h.provider.calls)
    monkeypatch.setattr(pd, "render", lambda value: (_ for _ in ()).throw(RuntimeError("render failed")))
    with pytest.raises(RuntimeError, match="render failed"):
        h.review(propose_patch=False, prior_proposal_disposition=disposition(receipt))
    assert len(h.provider.calls) == calls
    assert load(h).proposal_receipt == receipt
    assert load(h).review_state["last_round"] == 1


@pytest.mark.parametrize("supplemental", [False, True])
def test_disposition_audit_failure(h, monkeypatch, supplemental):
    log = handlers._log
    def fail(log_dir, tool, *a, **kw):
        if ("patch_proposal" in tool) == supplemental:
            return None
        return log(log_dir, tool, *a, **kw)
    monkeypatch.setattr(handlers, "_log", fail)
    output = h.review(propose_patch=True)
    assert "PATCH-PROPOSAL: UNAVAILABLE" in output
    assert load(h).proposal_receipt is None
    assert load(h).review_state["last_round"] == 1
    assert len(h.provider.proposals) == int(supplemental)
    if supplemental:
        assert output.endswith(h.audit()["rendered_trailer"])


def test_disposition_escaping_and_schema():
    from jsonschema import Draft202012Validator
    from paranoia_local.server import TOOLS
    receipt = {"version": 1, "round": 1, "audit": "proposal.json", "structural_snapshot": "a" * 64,
               "patch_sha256": "b" * 64, "target_ids": ["structural:D1"]}
    reasons = {"structural:D1": '"quotes" \\ Unicode café'}
    value = pd.accounting(receipt, 1, {"prior_proposal_disposition": disposition(receipt, "departed", reasons)})
    for tool in TOOLS:
        if tool.name in {"critique_branch", "critique_plan"}:
            schema = tool.inputSchema["properties"]["prior_proposal_disposition"]
            assert schema == pd.INPUT_SCHEMA
            Draft202012Validator(schema).validate(disposition(receipt, "departed", reasons))
            assert not Draft202012Validator(schema).is_valid({"status": "applied"})
    line = pd.render(value)
    assert len(line.splitlines()) == 1
    assert json.loads(line.split(" ", 2)[2]) == value
    for reason in [" ", "line\nbreak", "tab\there", "x" * 501, "x\u2028y"]:
        with pytest.raises(ValueError):
            pd.validate_input(disposition(receipt, "departed", {"structural:D1": reason}))
    with pytest.raises(ValueError, match="pending"):
        pd.accounting(None, 1, {"prior_proposal_disposition": disposition(receipt)})
