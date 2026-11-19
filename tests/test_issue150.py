"""Public claim lifecycle regressions for local failures and inventory growth."""
import hashlib
import json
from pathlib import Path
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from paranoia_local import class_closure as cc, external_sources as es, handlers as h
from paranoia_local import plan_claims as pc, review_census as rc
from paranoia_local.engines import Review
from tests.test_plan_claims import _audit, _claim, _source, PLAN


def fixture(count=36, expanded=6, per_claim=1):
    anchors = [f"External behavior {i} is guaranteed." for i in range(count)]
    claims = []
    texts = {}
    for i, anchor in enumerate(anchors):
        evidence = [_source(url=f"https://www.python.org/source-{i}", quote=anchor)]
        texts[evidence[0]["url"]] = ("x" * 450_000 + "\n" if i < expanded else "") + anchor
        for j in range(1, per_claim):
            evidence.append(_source(url=f"repo://context-{i}-{j}", relation="context"))
        claims.append(_claim(anchor=anchor, proposition=anchor, evidence=evidence))
    return "# External premises\n\n" + "\n\n".join(anchors), claims, texts


class Provider:
    name = "codex"
    default_model = "test"
    native_web = True

    def __init__(self, shared, role="default"):
        self.shared, self.role = shared, role

    def for_role(self, role):
        return Provider(self.shared, role)

    def answer(self, prompt, **kwargs):
        s = self.shared
        s.setdefault("calls", []).append((self.role, prompt, kwargs.get("timeout")))
        if "clock" in s:
            s["clock"][0] += kwargs["timeout"]
        if self.role == "evidence-discovery":
            text = _audit(*s["claims"])
            keys = ()
            count = sum(role == self.role for role, _, _ in s["calls"])
            failure = s.get("discovery_failure")
            if count == 2 and failure:
                if failure == "execution":
                    return Review(text="provider failed", raw="actual correction stdout",
                        session_ref="fixture-session", returncode=73, error=True,
                        failure_detail="actual correction detail", stderr="actual correction stderr")
                if failure == "session":
                    return Review(text=text, raw="sessionless correction stdout", session_ref=None,
                                  failure_detail="", stderr="")
                if failure == "invalid":
                    return Review(text="invalid correction", raw="invalid correction stdout",
                                  session_ref="fixture-session", failure_detail="", stderr="")
        else:
            rows = json.loads(prompt.rsplit("\n\n", 1)[1])
            keys = tuple((r["claim_index"], r["evidence_index"]) for r in rows)
            if self.role == "evidence-binding":
                text = h.PLAN_BINDING_MARKER + "\n" + json.dumps({"bindings": [
                    {"claim_index": i, "evidence_index": j, "usable": True,
                     "location": f"record {i}", "passage": s["claims"][i]["evidence"][j]["quote"]}
                    for i, j in keys
                ]})
            else:
                text = "=== EVIDENCE ATTESTATION JSON ===\n" + json.dumps({"attestations": [
                    {"claim_index": i, "evidence_index": j, "publisher_authority": True,
                     "authority_reason": f"official publisher {i}", "passage_entailment": True,
                     "entailment_reason": f"exact record {i}"}
                    for i, j in keys
                ]})
        identity = self.role, keys
        seen = s.setdefault("seen", set())
        if s.get("repair") and identity not in seen:
            seen.add(identity)
            text = "invalid initial reply"
        if s.get("wrong") and self.role == "evidence-binding":
            text = text.replace('"claim_index": 0', '"claim_index": 999') if s["wrong"] == "index" else text.replace(
                s["claims"][keys[0][0]]["evidence"][0]["quote"], "invented passage")
        return Review(text=text, raw=text, session_ref="fixture-session", returncode=0,
                      failure_detail="", stderr="", duration_ms=0)

    def run(self, prompt, *args, **kwargs):
        return self.answer(prompt, **kwargs)

    def resume(self, session, prompt, *args, **kwargs):
        return self.answer(prompt, **kwargs)


def capture_fixture(monkeypatch, texts, *, clock=None):
    def capture(candidates, **kwargs):
        if clock is not None:
            reserve = h._plan_capture_reserve(len(candidates))
            assert kwargs["deadline"] == clock[0] + reserve
            clock[0] += reserve
        return [es.Capture(
            c, c.url if c.url in texts else None, 200 if c.url in texts else None,
            "text/html" if c.url in texts else None,
            hashlib.sha256(texts[c.url].encode()).hexdigest() if c.url in texts else None,
            hashlib.sha256(texts[c.url].encode()).hexdigest() if c.url in texts else None,
            texts.get(c.url), error=None if c.url in texts else "non-web context",
        ) for c in candidates]
    monkeypatch.setattr(es, "capture_all", capture)


def public(monkeypatch, repo, tmp_path, shared, *, lineage="issue150", round_no=1):
    monkeypatch.setattr(h.eng, "CodexEngine", Provider)
    monkeypatch.setattr(h.eng, "require_evidence_profile", lambda engine: "test")
    monkeypatch.setattr(h.inert_git, "require_supported_version", lambda: (2, 50, 1))
    def stop(**kwargs):
        raise rc.CensusError("stop after durable claims; structural acceptance is separate")
    monkeypatch.setattr(h, "_staged_structural_review", stop)
    report = h.critique_plan(
        {"repo_path": str(repo), "plan_text": shared["plan"], "lineage": lineage,
         "round": round_no, "stakes": "trusted local tool; evidence binding has high impact",
         "propose_patch": False},
        engine=Provider(shared), log_dir=tmp_path / "logs",
    )
    assert "CLAIM-AUDIT-LOG:" in report
    state = cc.load_lineage(cc.default_state_root(), lineage, stamp="T", mode=cc.PLAN_MODE).claim_state
    audit = json.loads(max((tmp_path / "logs").glob("*.json"), key=lambda p: p.stat().st_mtime_ns).read_text())
    return report, state, audit


@pytest.mark.parametrize("count,expected", [(0,5),(25,5),(26,6),(30,6),(31,7),(36,8),(45,9),(46,10),(500,10)])
def test_batch_allowance_boundaries(count, expected):
    assert h._plan_evidence_batch_limit(count) == expected


@pytest.mark.parametrize("count,expected", [(0,300),(100,300),(101,303),(199,597),(200,600)])
def test_capture_reserve_boundaries(count, expected):
    assert h._plan_capture_reserve(count) == expected


def test_budget_equations_and_published_client_timeout():
    assert h.PLAN_EVIDENCE_REQUIRED_WORK_SEC == 14_400
    assert h.PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC == 14_460
    assert h.PLAN_REVIEW_TOTAL_TIMEOUT_SEC == 14_880
    assert h.PLAN_REVIEW_CLIENT_TIMEOUT_SEC == 15_000
    assert h.MAX_PLAN_EVIDENCE_MODEL_CALLS == 42
    root = Path(__file__).resolve().parents[1]
    for name in ["README.md", "docs/llm-reference.md"]:
        assert "8700" not in (root / name).read_text()
        assert "15000" in (root / name).read_text()


@pytest.mark.asyncio
async def test_acceptance_client_uses_actual_derived_timeout(tmp_path, monkeypatch):
    from scripts import run_claim_admission_acceptance as a
    import mcp
    import mcp.client.stdio
    seen = []
    @asynccontextmanager
    async def streams(*args, **kwargs):
        yield None, None
    class Session:
        def __init__(self, *args, **kwargs):
            seen.append(kwargs["read_timeout_seconds"].total_seconds())
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def initialize(self):
            pass
        async def call_tool(self, *args):
            return SimpleNamespace(content=[], isError=False)
    monkeypatch.setattr(a, "load_source", lambda manifest: None)
    monkeypatch.setattr(a, "server_parameters", lambda *args: None)
    monkeypatch.setattr(a, "validate_receipt", lambda *args: None)
    monkeypatch.setattr(mcp, "ClientSession", Session)
    monkeypatch.setattr(mcp.client.stdio, "stdio_client", streams)
    (tmp_path / "receipt.json").write_text("{}")
    await a.client({"tool":"critique_plan","request":{}}, tmp_path)
    assert seen == [15000] == [h.PLAN_REVIEW_CLIENT_TIMEOUT_SEC]


@pytest.mark.parametrize("wrong", [None,"passage","index"])
def test_public_growth_recovers_old_failed_lineage(repo, tmp_path, monkeypatch, wrong):
    plan, claims, texts = fixture()
    prior = pc.reconcile({}, pc.parse_audit(_audit(*claims), plan),
                         lineage_id="issue150", round_no=16, plan_text=plan)
    original_ids = list(prior["claims"])
    for claim, claim_id in zip(claims, original_ids):
        claim["prior_claim_id"] = claim_id
    prior = pc.with_debt(prior, pc.AuditError("old five-batch ceiling", failure_phase="binding"),
                         round_no=17, plan_text=plan)
    historical = tmp_path / "old-audit.json"
    historical.write_text(json.dumps(prior))
    original_bytes = historical.read_bytes()
    cc.save_lineage(cc.default_state_root(), cc.Lineage(
        "issue150", mode=cc.PLAN_MODE, rounds=17, claim_state=prior))
    capture_fixture(monkeypatch, texts)
    shared = dict(plan=plan, claims=claims, wrong=wrong)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared, round_no=18)
    assert historical.read_bytes() == original_bytes
    assert list(state["claims"]) == original_ids
    if wrong:
        assert pc.is_blocked(state)
        if state["debt"]:
            assert state["debt"]["failure_phase"] == "binding"
        else:
            assert next(iter(state["claims"].values()))["verdict"] == "unverified"
        assert "CONVERGENCE: BLOCKED" in report
        return
    assert not pc.is_blocked(state)
    assert "CLAIM-CLOSURE: 36 supported, 0 refuted, 0 unverified" in report
    for role in ["evidence-binding", "evidence-text"]:
        assert sum(r == role for r, _, _ in shared["calls"]) == 7
    for index, row in enumerate(state["claims"].values()):
        assert row["anchor"] == claims[index]["anchor"]
        assert row["evidence"][0]["quote"] == claims[index]["evidence"][0]["quote"]
        assert row["capture_provenance"][0]["text_sha256"] == hashlib.sha256(
            texts[row["evidence"][0]["url"]].encode()).hexdigest()
        assert pc._captured_support(row)
    assert audit["claim_audit_failed"] is False


def test_maximum_graph_has_200_sources_and_all_42_attempts(repo, monkeypatch):
    plan, claims, texts = fixture(count=50, expanded=9, per_claim=4)
    clock = [0.0]
    shared = dict(plan=plan, claims=claims, repair=True, clock=clock)
    capture_fixture(monkeypatch, texts, clock=clock)
    ledger = []
    adapter = h._CapturedClaimEngine(Provider(shared), plan_text=plan, repo=repo,
        plan_repo_path=None, deadline=14_460, clock=lambda: clock[0], attempt_ledger=ledger)
    try:
        result = adapter.run("audit", repo, "test", "high", True)
        assert not result.error, result.text
        assert len(ledger) == adapter.model_calls == 42
        assert clock[0] == 14_400
        assert [r["role"] for r in ledger[:2]] == ["claim-discovery", "claim-discovery-validation-retry"]
        assert sum(r["role"] == "claim-binding" for r in ledger) == 10
        assert sum(r["role"] == "claim-attestation" for r in ledger) == 10
        parsed = pc.parse_audit(result.text, plan, require_capture_provenance=True)
        assert len(parsed.claims) == 50
        assert all(pc._captured_support(c) for c in parsed.claims)
    finally:
        adapter.close()


@pytest.mark.parametrize("phase", ["binding", "attestation"])
def test_one_over_allowance_rejects_before_role_dispatch(repo, monkeypatch, phase):
    plan, claims, texts = fixture(count=36, expanded=9)
    capture_fixture(monkeypatch, texts)
    shared = dict(plan=plan, claims=claims)
    adapter = h._CapturedClaimEngine(Provider(shared), plan_text=plan, repo=repo, plan_repo_path=None)
    if phase == "attestation":
        # Supply completed bindings to exercise real attestation packing independently.
        audit = pc.parse_audit(_audit(*claims), plan)
        adapter.captures = adapter._capture(audit)
        adapter.expanded_captures = {(i,0) for i in range(9)}
        result = adapter._attest(audit, "test", "high")
    else:
        result = adapter.run("audit", repo, "test", "high", True)
    try:
        assert result.error and result.failure_kind == "limit"
        assert "aggregate ceiling is 8" in result.evidence_reason
        assert result.phase_attempts == ()
        assert not any(r == ("evidence-binding" if phase == "binding" else "evidence-text")
                       for r, _, _ in shared.get("calls", []))
    finally:
        adapter.close()


@pytest.mark.parametrize("packing", [False,True])
def test_public_local_deadline_is_retrieval(repo, tmp_path, monkeypatch, packing):
    plan, claims, texts = fixture(count=1, expanded=0)
    capture_fixture(monkeypatch, texts)
    clock = [0.0]
    init = h._CapturedClaimEngine.__init__
    def initialize(self, *args, **kwargs):
        init(self, *args, **kwargs, clock=lambda: clock[0])
    monkeypatch.setattr(h._CapturedClaimEngine, "__init__", initialize)
    target = "_binding_batches" if packing else "_capture"
    original = getattr(h._CapturedClaimEngine, target)
    def expired(self, *args):
        if packing:
            result = original(self, *args)
            clock[0] = self.non_model_deadline + 1
            return result
        clock[0] = self.non_model_deadline + 1
        return original(self, *args)
    monkeypatch.setattr(h._CapturedClaimEngine, target, expired)
    shared = dict(plan=plan, claims=claims)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt["failure_phase"] == "capture" and debt["failure_kind"] == "deadline"
    assert "300-second reserve" in debt["reason"] in report
    assert debt["attempts"] == []
    assert [r for r,_,_ in shared["calls"]] == ["evidence-discovery"]
    assert audit["claim_audit_debt"] == debt


@pytest.mark.parametrize("coverage", [False,True])
@pytest.mark.parametrize("exhausted", [False,True])
def test_issue150_public_final_validation_is_terminal(repo, tmp_path, monkeypatch, coverage, exhausted):
    plan, claims, texts = fixture(count=1, expanded=0)
    capture_fixture(monkeypatch, texts)
    original = h._CapturedClaimEngine._attest
    def completed(self, *args):
        result = original(self, *args)
        if exhausted:
            self.model_calls = h.MAX_PLAN_EVIDENCE_MODEL_CALLS
        if coverage:
            original_coverage = pc.validate_prior_coverage
            def reject(*a, **k):
                raise pc.AuditError("retained coverage rejected locally")
            monkeypatch.setattr(pc, "validate_prior_coverage", reject)
            return result
        return pc.Audit((), {}, (), ())  # syntactically invalid final rendered coverage
    monkeypatch.setattr(h._CapturedClaimEngine, "_attest", completed)
    shared = dict(plan=plan, claims=claims, repair=True)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt["failure_phase"] == "binding" and debt["failure_kind"] == "validation"
    assert debt["returncode"] is None and debt["attempts"] == []
    assert debt["reason"] in report and "final captured audit invalid" in report
    assert [r for r,_,_ in shared["calls"]] == [
        "evidence-discovery", "evidence-discovery", "evidence-binding", "evidence-binding",
        "evidence-text", "evidence-text"]
    assert len(audit["attempt_ledger"]) == 6
    assert audit["claim_audit_debt"] == debt


def test_issue150_recovery_guidance():
    for kind in [None,"limit","deadline","admission","execution","validation"]:
        state = pc.with_debt({}, pc.AuditError("requires 9; aggregate ceiling is 8",
            failure_phase="binding", failure_kind=kind), round_no=18, plan_text=PLAN)
        text = pc.render_trailer(state)
        assert "requires 9; aggregate ceiling is 8" in text
        assert "critique_plan on the same lineage at a higher round" in text
        if kind == "limit":
            assert "identical request cannot repair a fixed limit" in text
    assert "failed sibling is not retried" in pc.evidence_recovery(None, frozen=True)


@pytest.mark.parametrize("remaining", [14_400,14_399])
def test_complete_graph_admission_after_nonzero_setup(repo, remaining):
    adapter = h._CapturedClaimEngine(Provider({}), plan_text=PLAN, repo=repo,
        plan_repo_path=None, deadline=100+remaining, clock=lambda: 100)
    try:
        if remaining == 14_400:
            adapter._admit_complete_graph()
        else:
            with pytest.raises(pc.AuditError, match="complete maximum model-call graph"):
                adapter._admit_complete_graph()
        assert adapter.model_calls == 0
    finally:
        adapter.close()


@pytest.mark.parametrize("failure", ["admission","execution","invalid","session"])
def test_issue150_discovery_correction_failure(repo, tmp_path, monkeypatch, failure):
    plan, claims, _ = fixture(count=1, expanded=0)
    monkeypatch.setattr(es, "capture_all", lambda *a, **k: pytest.fail("no capture after discovery failure"))
    if failure == "admission":
        original = h._CapturedClaimEngine._next_model_timeout
        def refusal(self, **kwargs):
            if self.model_calls:
                raise pc.AuditError("correction admission refused", failure_kind="admission")
            return original(self, **kwargs)
        monkeypatch.setattr(h._CapturedClaimEngine, "_next_model_timeout", refusal)
    shared = dict(plan=plan, claims=claims, repair=True, discovery_failure=failure)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt["failure_phase"] == "discovery"
    assert "initial" in debt["reason"] and debt["reason"] in report
    assert debt["returncode"] == (124 if failure == "admission" else 73 if failure == "execution" else 0)
    assert debt["failure_kind"] == (failure if failure in {"admission","execution"} else "validation")
    assert len(shared["calls"]) == len(debt["attempts"]) == (1 if failure == "admission" else 2)
    assert all(r == "evidence-discovery" for r,_,_ in shared["calls"])
    assert debt["attempts"][0]["outcome"] == "validation-invalid"
    assert debt["attempts"][0]["validation_issue"]
    for row in debt["attempts"]:
        for key in ["raw", "failure_detail", "stderr"]:
            assert isinstance(row[key + "_sha256"], str)
            assert isinstance(row[key + "_excerpt"], str)
    assert audit["attempt_ledger"] == debt["attempts"]


@pytest.mark.parametrize("phase", ["binding","attestation"])
@pytest.mark.parametrize("correction", [False,True])
def test_later_batch_admission_never_borrows_previous_response(repo, tmp_path, monkeypatch, phase, correction):
    plan, claims, texts = fixture()
    capture_fixture(monkeypatch, texts)
    original_bind, original_attest = h._CapturedClaimEngine._bind_indexed, h._CapturedClaimEngine._attest
    def bind(self, *a, **k):
        self.test_phase = "binding"
        return original_bind(self, *a, **k)
    def attest(self, *a, **k):
        self.test_phase = "attestation"
        return original_attest(self, *a, **k)
    monkeypatch.setattr(h._CapturedClaimEngine, "_bind_indexed", bind)
    monkeypatch.setattr(h._CapturedClaimEngine, "_attest", attest)
    original_timeout = h._CapturedClaimEngine._next_model_timeout
    shared = dict(plan=plan, claims=claims, repair=correction)
    def timeout(self, **kwargs):
        role = "evidence-binding" if phase == "binding" else "evidence-text"
        count = sum(r == role for r,_,_ in shared.get("calls", []))
        if getattr(self, "test_phase", None) == phase and count == 1:
            raise pc.AuditError("later role admission refused", failure_kind="admission")
        return original_timeout(self, **kwargs)
    monkeypatch.setattr(h._CapturedClaimEngine, "_next_model_timeout", timeout)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt["failure_phase"] == phase and debt["failure_kind"] == "admission"
    assert len(debt["attempts"]) == (1 if correction else 0)
    assert debt["rejected_excerpt"] == ""  # no response to the refused call
    assert debt["returncode"] == 124
    assert "later role admission refused" in report
    if correction:
        assert debt["attempts"][0]["outcome"] == "validation-invalid"
    assert len(audit["attempt_ledger"]) > len(debt["attempts"])
