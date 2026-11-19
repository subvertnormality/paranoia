"""Public claim lifecycle regressions for local failures and inventory growth."""
import hashlib
import json
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import replace
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
            keys = ()
            count = sum(role == self.role for role, _, _ in s["calls"])
            text = _audit(*s.get("discovery_claims", {}).get(count, s["claims"]))
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
            attempts = sum(role == self.role for role, _, _ in s["calls"])
            if s.get("malformed_provider_error") == (self.role, attempts):
                detail = s["provider_failure_detail"]
                raw = json.dumps({"type": "error", "message": detail})
                return Review(s["provider_failure_text"], "fixture-session", raw, error=True, returncode=73,
                              failure_detail=detail, stderr=s["provider_failure_stderr"])
            surrogate = s.get("surrogate_replies", {}).get(self.role, 0) >= attempts
            if self.role == "evidence-binding":
                text = h.PLAN_BINDING_MARKER + "\n" + json.dumps({"bindings": [
                    {"claim_index": i, "evidence_index": j, "usable": True,
                     "location": "\ud800" if surrogate else f"record {i}",
                     "passage": s["claims"][i]["evidence"][j]["quote"]}
                    for i, j in keys
                ]})
                if s.get("repeat_binding_envelope"):
                    text += "\n" + text
            else:
                if s.get("attestation_execution_failure") == attempts:
                    return Review(
                        "provider failed", "fixture-session", "actual attestation stdout",
                        error=True, returncode=73, failure_detail="actual attestation detail",
                        stderr="actual attestation stderr",
                    )
                text = "=== EVIDENCE ATTESTATION JSON ===\n" + json.dumps({"attestations": [
                    {"claim_index": i, "evidence_index": j, "publisher_authority": True,
                     "authority_reason": "\ud800" if surrogate else f"official publisher {i}",
                     "passage_entailment": True,
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
        attempt = len(s["calls"])
        session = "fixture-session"
        if self.role == "evidence-binding" and s.get("binding_sessionless") == attempt:
            session = None
        if s.get("mismatched_session") == attempt:
            session = "different-provider-session"
        raw = f"stdout {attempt}" if s.get("terminal_channels") else text
        return Review(text=text, raw=raw, session_ref=session, returncode=0,
                      failure_detail=f"detail {attempt}", stderr=f"stderr {attempt}", duration_ms=0)

    def run(self, prompt, *args, **kwargs):
        return self.answer(prompt, **kwargs)

    def resume(self, session, prompt, *args, **kwargs):
        self.shared.setdefault("resumed", []).append((self.role, session))
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
        if (bodies := shared.get("structural_bodies")) is not None:
            bodies.append(kwargs["body"])
        raise rc.CensusError("stop after durable claims; structural acceptance is separate")
    monkeypatch.setattr(h, "_staged_structural_review", stop)
    report = h.critique_plan(
        {"repo_path": str(repo), "plan_text": shared["plan"], "lineage": lineage,
         "round": round_no, "stakes": "trusted local tool; evidence binding has high impact",
         "propose_patch": False},
        engine=Provider(shared), log_dir=tmp_path / "logs",
    )
    state = cc.load_lineage(cc.default_state_root(), lineage, stamp="T", mode=cc.PLAN_MODE).claim_state
    audit_path = max((tmp_path / "logs").glob("*.json"), key=lambda p: p.stat().st_mtime_ns)
    if isinstance(state["debt"], dict) and state["debt"].get("audit_failed"):
        assert f"CLAIM-AUDIT-LOG: {rc.trailer_diagnostic(str(audit_path))}" in report.splitlines()
    audit = json.loads(audit_path.read_text())
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
    plan, claims, texts = fixture(expanded=7)
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
        assert sum(r == role for r, _, _ in shared["calls"]) == 8
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
def test_one_over_allowance_rejects_before_role_dispatch(repo, tmp_path, monkeypatch, phase):
    plan, claims, texts = fixture(count=36, expanded=8)
    capture_fixture(monkeypatch, texts)
    shared = dict(plan=plan, claims=claims)
    if phase == "attestation":
        # Supply completed bindings so only attestation packing is under test.
        def finished_binding(self, session, discovery, captures, *args):
            self.expanded_captures = {(i, 0) for i in range(8)}
            return discovery, []
        monkeypatch.setattr(h._CapturedClaimEngine, "_bind_indexed", finished_binding)
    report, state, log = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt["failure_phase"] == phase and debt["failure_kind"] == "limit"
    assert "requires 9" in debt["reason"] in report
    assert "aggregate ceiling is 8" in report
    assert debt["attempts"] == [] and debt["returncode"] is None
    assert log["claim_audit_debt"] == debt
    assert_empty_provider_channels(debt)
    assert not any(r == ("evidence-binding" if phase == "binding" else "evidence-text")
                   for r, _, _ in shared.get("calls", []))


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
        from scripts.run_authoritative_capture_acceptance import digest
        assert digest(self.attestation_raw) == digest("stdout 5\n--- attestation ---\nstdout 6")
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
    shared = dict(plan=plan, claims=claims, repair=True, terminal_channels=True)
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
    parts = [f"stdout {i}" for i in range(1, 7)]
    stdout = "\n--- phase ---\n".join(parts)
    assert debt["rejected_excerpt"] == stdout
    assert debt["raw_sha256"] == hashlib.sha256(stdout.encode()).hexdigest()
    assert [r["raw_excerpt"] for r in audit["attempt_ledger"]] == parts
    for row in audit["attempt_ledger"][::2]:
        assert row["outcome"] == "validation-invalid"
        assert row["validation_issue"] and row["validation_pointer"]
        assert row["rejected_reply_excerpt"] == "invalid initial reply"
    for channel in ("failure_detail", "stderr"):
        base = "detail" if channel == "failure_detail" else channel
        parts = [f"{base} {i}" for i in range(1, 7)]
        value = "\n--- phase ---\n".join(parts)
        assert debt[channel] == value
        assert debt[channel + "_sha256"] == hashlib.sha256(value.encode()).hexdigest()
        assert [r[channel + "_excerpt"] for r in audit["attempt_ledger"]] == parts


def assert_empty_provider_channels(debt):
    assert [debt[key] for key in ("rejected_excerpt", "failure_detail", "stderr")] == [""] * 3
    empty = hashlib.sha256(b"").hexdigest()
    assert [debt[key] for key in ("raw_sha256", "failure_detail_sha256", "stderr_sha256")] == [empty] * 3


def test_combined_binding_rejection_does_not_own_completed_batch(repo, tmp_path, monkeypatch):
    plan, claims, texts = fixture(count=1, expanded=0)
    capture_fixture(monkeypatch, texts)
    original = pc.parse_audit
    def reject_combined(*args, **kwargs):
        if kwargs.get("require_capture_provenance"):
            raise pc.AuditError("combined packet rejected", "rendered non-provider input")
        return original(*args, **kwargs)
    monkeypatch.setattr(pc, "parse_audit", reject_combined)
    shared = dict(plan=plan, claims=claims)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt["failure_phase"] == "binding" and debt["failure_kind"] == "validation"
    assert debt["reason"] in report and "combined packet rejected" in debt["reason"]
    assert debt["returncode"] is None and debt["attempts"] == []
    assert debt["failure_detail"] == "detail 1\n--- phase ---\ndetail 2"
    assert "rendered non-provider input" not in debt["rejected_excerpt"]
    assert [(r["role"], r["outcome"]) for r in audit["attempt_ledger"]] == [
        ("claim-discovery", "completed"), ("claim-binding", "completed"),
    ]
    assert audit["claim_audit_debt"] == debt


@pytest.mark.parametrize("corrected", [False, True])
def test_missing_binding_session_is_owned_validation(repo, tmp_path, monkeypatch, corrected):
    plan, claims, texts = fixture(count=1, expanded=0)
    capture_fixture(monkeypatch, texts)
    attempt = 4 if corrected else 2
    shared = dict(plan=plan, claims=claims, binding_sessionless=attempt, repair=corrected)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt["failure_phase"] == "binding" and debt["failure_kind"] == "validation"
    assert debt["returncode"] == 0 and "no resumable session" in debt["reason"] in report
    assert debt["failure_detail"] == f"detail {attempt}" and debt["stderr"] == f"stderr {attempt}"
    assert len(debt["attempts"]) == (2 if corrected else 1)
    assert debt["attempts"][-1]["validation_pointer"] == "/session_ref"
    assert audit["claim_audit_debt"] == debt


@pytest.mark.parametrize("enlarged,phase,allowance", [
    (690_000, "binding", 685_000),
    (660_000, "attestation", 685_000),
])
def test_oversized_source_recovery_names_complete_bound(repo, tmp_path, monkeypatch, enlarged, phase, allowance):
    plan, claims, texts = fixture(count=1, expanded=0)
    url = claims[0]["evidence"][0]["url"]
    texts[url] = "x" * enlarged + "\n" + claims[0]["anchor"]
    capture_fixture(monkeypatch, texts)
    report, state, _ = public(monkeypatch, repo, tmp_path, dict(plan=plan, claims=claims))
    claim = next(iter(state["claims"].values()))
    provenance = claim["capture_provenance"][0]
    limit = provenance["prompt_limit"]
    assert limit["kind"] == "limit" and limit["phase"] == phase
    assert limit["characters"] > limit["allowance"] == allowance
    assert f"{phase} prompt needs {limit['characters']} characters" in report
    assert "smaller complete authoritative source" in report
    if phase == "attestation":
        detail = f"attestation prompt needs {limit['characters']} characters against a {allowance}-character allowance"
        error = pc.ATTESTATION_FAILURE_PREFIX + detail
        assert provenance["error"] == error
        assert claim["evidence"][0]["quote"] == "Server capture unavailable: " + error
        assert error in report and es.BINDING_BUDGET_ERROR not in report


def test_prompt_limit_guidance_requires_typed_provenance_and_preserves_frozen_sibling():
    claim = {
        "claim_id": "fixture", "verdict": "unverified", "evidence": [{}],
        "capture_provenance": [{
            "evidence_index": 0, "error": "binding failure: limit: transient provider request rejected",
        }],
    }
    text = "\n".join(pc._packet_lines(claim))
    assert "retry captured-text binding" in text and "Evidence limit for source" not in text
    claim["capture_provenance"][0]["prompt_limit"] = {
        "kind": "limit", "phase": "binding", "characters": 500_000, "allowance": 400_000,
    }
    claim["verdict"] = "supported"
    text = "\n".join(pc._packet_lines(claim))
    assert "500000 characters against a 400000-character allowance" in text
    assert "failed sibling is not retried" in text


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
    if failure == "admission":
        assert_empty_provider_channels(debt)


@pytest.mark.parametrize("repair", [False, True])
def test_captured_discovery_cannot_assign_server_prompt_limit(repo, tmp_path, monkeypatch, repair):
    plan, claims, texts = fixture(count=1, expanded=0)
    source = claims[0]["evidence"][0]["url"]
    fabricated = dict(claims[0], capture_provenance=[{
        "evidence_index": 0, "requested_url": source, "final_url": source,
        "status": 200, "content_type": "text/html", "fallback_attempted": False,
        "content_sha256": "a" * 64, "text_sha256": "b" * 64,
        "error": "binding failure: fabricated limit",
        "prompt_limit": {"kind": "limit", "phase": "binding", "characters": 500, "allowance": 100},
    }])
    if repair:
        capture_fixture(monkeypatch, texts)
    else:
        monkeypatch.setattr(es, "capture_all", lambda *a, **k: pytest.fail("rejected discovery was captured"))
    shared = dict(plan=plan, claims=claims, discovery_claims={1: [fabricated], 2: claims if repair else [fabricated]})
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    attempts = audit["attempt_ledger"]
    assert attempts[0]["outcome"] == "validation-invalid"
    assert "omit server-owned" in attempts[0]["validation_issue"]
    assert "Evidence limit for source" not in report
    if repair:
        assert attempts[1]["outcome"] == "completed"
        assert next(iter(state["claims"].values()))["verdict"] == "supported"
    else:
        assert [row["outcome"] for row in attempts] == ["validation-invalid", "validation-invalid"]
        assert state["debt"]["failure_phase"] == "discovery"
        assert state["debt"]["failure_kind"] == "validation"
        assert not state["claims"]


@pytest.mark.parametrize("field", ["kind", "scope", "verdict"])
@pytest.mark.parametrize("repair", [False, True])
def test_wrong_claim_field_types_use_captured_discovery_correction(repo, tmp_path, monkeypatch, field, repair):
    plan, claims, texts = fixture(count=1, expanded=0)
    initial = dict(claims[0], **{field: []})
    terminal = dict(claims[0], **{field: {"unexpected": "value"}})
    if repair:
        capture_fixture(monkeypatch, texts)
    else:
        monkeypatch.setattr(es, "capture_all", lambda *a, **k: pytest.fail("invalid discovery was captured"))
    shared = dict(plan=plan, claims=claims, discovery_claims={1: [initial], 2: claims if repair else [terminal]})
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    initial_attempt, correction = audit["attempt_ledger"][:2]
    assert initial_attempt["outcome"] == "validation-invalid"
    assert field in initial_attempt["validation_issue"]
    assert shared["resumed"][0] == ("evidence-discovery", "fixture-session")
    if repair:
        assert correction["outcome"] == "completed"
        assert next(iter(state["claims"].values()))["verdict"] == "supported"
    else:
        assert correction["outcome"] == "validation-invalid"
        assert field in correction["validation_issue"]
        assert [role for role, _, _ in shared["calls"]] == ["evidence-discovery", "evidence-discovery"]
        debt = state["debt"]
        assert debt == audit["claim_audit_debt"]
        assert debt["failure_phase"] == "discovery" and debt["failure_kind"] == "validation"
        assert debt["attempts"] == [initial_attempt, correction]
        assert debt["reason"] in report and not state["claims"]


@pytest.mark.parametrize("phase,provider_role", [
    ("discovery", "evidence-discovery"), ("binding", "evidence-binding"), ("attestation", "evidence-text"),
])
@pytest.mark.parametrize("repair", [False, True])
def test_unpaired_surrogate_stays_in_its_producing_role(repo, tmp_path, monkeypatch, phase, provider_role, repair):
    plan, claims, texts = fixture(count=1, expanded=0)
    malformed = dict(claims[0], evidence=[dict(claims[0]["evidence"][0], title="broken \ud800 title")])
    shared = dict(plan=plan, claims=claims, surrogate_replies={provider_role: 1 if repair else 2})
    if phase == "discovery":
        shared["discovery_claims"] = {1: [malformed], 2: claims if repair else [malformed]}
    if phase == "discovery" and not repair:
        monkeypatch.setattr(es, "capture_all", lambda *a, **k: pytest.fail("invalid discovery reached capture"))
    else:
        capture_fixture(monkeypatch, texts)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    attempts = [row for row in audit["attempt_ledger"] if row["role"].startswith("claim-" + phase)]
    assert [row["outcome"] for row in attempts] == ["validation-invalid", "completed" if repair else "validation-invalid"]
    rejected = attempts[0]
    assert "strict UTF-8" in rejected["validation_issue"]
    assert "\\ud800" in rejected["raw_excerpt"]
    assert attempts[1]["session_ref"] == rejected["session_ref"] == "fixture-session"
    for _, prompt, _ in shared["calls"]:
        prompt.encode("utf-8", errors="strict")
    if repair:
        assert next(iter(state["claims"].values()))["verdict"] == "supported"
    else:
        debt = state["debt"]
        assert debt == audit["claim_audit_debt"]
        assert debt["failure_phase"] == phase and debt["failure_kind"] == "validation"
        assert debt["attempts"] == attempts
        assert "strict UTF-8" in report and not state["claims"]
        assert audit["attempt_ledger"][-1] == attempts[-1]


@pytest.mark.parametrize("frozen", [False, True])
def test_retained_surrogate_in_failed_source_is_safe_to_render(repo, tmp_path, monkeypatch, frozen):
    plan, current_claims, texts = fixture(count=1, expanded=0)
    failed = _source(url="https://www.python.org/failed", quote=current_claims[0]["anchor"])
    sources = current_claims[0]["evidence"] + [failed] if frozen else [failed]
    capture_fixture(monkeypatch, texts)
    lineage = "issue150-legacy-text"
    old_claims = [dict(current_claims[0], evidence=sources)]
    _, state, _ = public(monkeypatch, repo, tmp_path, dict(plan=plan, claims=old_claims), lineage=lineage)
    claim_id, retained = next(iter(state["claims"].items()))
    assert retained["verdict"] == ("supported" if frozen else "unverified")
    assert retained["capture_provenance"][-1]["error"]
    previous_audit, = (tmp_path / "logs").glob("*-critique_plan-*.json")
    previous_bytes = previous_audit.read_bytes()
    # The older validator stored candidate titles even when their capture never bound.
    legacy = cc.load_lineage(cc.default_state_root(), lineage, stamp="T", mode=cc.PLAN_MODE)
    legacy_title = "Retained \ud800 source"
    legacy.claim_state["claims"][claim_id]["evidence"][-1]["title"] = legacy_title
    cc.save_lineage(cc.default_state_root(), legacy)
    escaped = r"Retained \ud800 source"

    shared = dict(plan=plan, claims=current_claims, structural_bodies=[])
    if frozen:
        monkeypatch.setattr(es, "capture_all", lambda *a, **k: pytest.fail("frozen claim recaptured"))
    result, current, audit = public(monkeypatch, repo, tmp_path, shared, lineage=lineage, round_no=2)
    result.encode("utf-8", errors="strict")
    (body,) = shared["structural_bodies"]
    body.encode("utf-8", errors="strict")
    assert previous_audit.read_bytes() == previous_bytes
    assert list(current["claims"]) == [claim_id] and current["claims"][claim_id]["verdict"] == "supported"
    if frozen:
        assert not shared.get("calls")
        assert "non-governing sibling" in result and escaped in result and escaped in body
        assert current["claims"][claim_id]["evidence"][-1]["title"] == legacy_title
        assert audit["claim_model_calls"] == 0
    else:
        roles = [call[0] for call in shared["calls"]]
        assert roles == ["evidence-discovery", "evidence-binding", "evidence-text"]
        discovery = shared["calls"][0][1]
        discovery.encode("utf-8", errors="strict")
        assert escaped in discovery and claim_id in discovery
        assert audit["claim_model_calls"] == 3


@pytest.mark.parametrize("phase,role", [("binding", "evidence-binding"), ("attestation", "evidence-text")])
@pytest.mark.parametrize("correction", [False, True])
@pytest.mark.parametrize("diagnostic", ["surrogate", "marker", "blank"])
def test_expanded_provider_diagnostic_cannot_discard_supported_sibling(
    repo, tmp_path, monkeypatch, phase, role, correction, diagnostic,
):
    plan, claims, texts = fixture(count=1, expanded=1)
    anchor = claims[0]["anchor"]
    sibling = _source(url="https://www.python.org/ordinary", quote=anchor)
    claims[0]["evidence"].append(sibling)
    texts[sibling["url"]] = anchor
    capture_fixture(monkeypatch, texts)
    # Binding visits the expanded source first. Attestation visits the ordinary sibling first.
    batch_number = 1 if phase == "binding" else 2
    detail = {"surrogate": "provider \ud800 diagnostic",
              "marker": f"provider cited {pc.AUDIT_MARKER} as text", "blank": " \t "}[diagnostic]
    stderr = " \n\t " if diagnostic == "blank" else "original stderr"
    text = " \t\n " if diagnostic == "blank" else "provider failed"
    shared = dict(plan=plan, claims=claims, repair=correction,
                  malformed_provider_error=(role, batch_number * (2 if correction else 1)),
                  provider_failure_detail=detail, provider_failure_stderr=stderr, provider_failure_text=text)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    report.encode("utf-8", errors="strict")
    assert not audit["claim_audit_failed"] and not state["debt"]
    claim = next(iter(state["claims"].values()))
    assert claim["verdict"] == "supported" and pc._captured_support(claim)
    assert claim["capture_provenance"][1]["error"] is None
    expected_prefix = pc.BINDING_FAILURE_PREFIX if phase == "binding" else pc.ATTESTATION_FAILURE_PREFIX
    if diagnostic == "surrogate":
        rendered_detail = r"provider \ud800 diagnostic"
    elif diagnostic == "blank":
        rendered_detail = f"dedicated expanded {phase} {'correction' if correction else 'call'} failed"
    else:
        rendered_detail = detail
    assert claim["capture_provenance"][0]["error"] == expected_prefix + rendered_detail
    assert "Source 1 failure: " + expected_prefix + rendered_detail in report
    assert "Source 2 failure:" not in report
    if phase == "attestation":
        failed_decision = claim["capture_attestations"][0]
        assert failed_decision["authority_reason"] == failed_decision["entailment_reason"] == rendered_detail
        assert claim["evidence"][0]["quote"] == anchor
        assert f"Exact passage: {anchor}" in report
    assert f"{phase.upper()}-FAILED (non-governing sibling; claim independently supported)" in report
    failed, = [row for row in audit["attempt_ledger"] if row["outcome"] == "failed"]
    expected_role = f"claim-{phase}" + ("-validation-retry" if correction else "")
    assert failed["role"] == expected_role and failed["returncode"] == 73
    raw = json.dumps({"type": "error", "message": detail})
    for key, value in (("raw", raw), ("failure_detail", detail), ("stderr", stderr)):
        assert failed[key + "_excerpt"] == value
        assert failed[key + "_sha256"] == hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def test_expanded_attestation_report_names_failed_source_when_claim_blocks(repo, tmp_path, monkeypatch):
    plan, claims, texts = fixture(count=1, expanded=1)
    capture_fixture(monkeypatch, texts)
    detail = "attester \ud800 unavailable"
    shared = dict(plan=plan, claims=claims, malformed_provider_error=("evidence-text", 1),
                  provider_failure_detail=detail, provider_failure_stderr="", provider_failure_text="failed")
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    claim = next(iter(state["claims"].values()))
    error = pc.ATTESTATION_FAILURE_PREFIX + r"attester \ud800 unavailable"
    assert claim["verdict"] == "unverified" and not audit["claim_audit_failed"]
    assert claim["capture_provenance"][0]["error"] == error
    assert "Source 1 failure: " + error in report
    assert "ATTESTATION-FAILED (blocking; bound passage not adjudicated)" in report
    assert f"Exact passage: {claims[0]['anchor']}" in report
    report.encode("utf-8", errors="strict")


def test_terminal_provider_channel_hashes_match_ledger_for_surrogate_text(repo, tmp_path, monkeypatch):
    plan, claims, texts = fixture(count=1, expanded=0)
    capture_fixture(monkeypatch, texts)
    detail, stderr = "provider \ud800 diagnostic", "original stderr"
    shared = dict(plan=plan, claims=claims, repair=True, malformed_provider_error=("evidence-text", 2),
                  provider_failure_detail=detail, provider_failure_stderr=stderr, provider_failure_text="failed")
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt == audit["claim_audit_debt"]
    attempt = audit["attempt_ledger"][-1]
    assert attempt["role"] == "claim-attestation-validation-retry" and attempt["returncode"] == 73
    assert debt["failure_kind"] == "execution"
    values = dict(raw=json.dumps({"type": "error", "message": detail}), failure_detail=detail, stderr=stderr)
    for channel, value in values.items():
        key = channel + "_sha256"
        assert debt[key] == attempt[key] == hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()
    assert debt["failure_detail"] == detail
    assert debt["failure_detail_sha256"] != hashlib.sha256(b"provider ? diagnostic").hexdigest()
    report.encode("utf-8", errors="strict")


def test_claim_audit_marker_inside_quote_is_data_but_second_envelope_is_invalid():
    quote = f"The source contains the exact text {pc.AUDIT_MARKER} here."
    response = _audit(_claim(evidence=[_source(quote=quote)]))
    assert pc.parse_audit(response, PLAN).claims[0]["evidence"][0]["quote"] == quote
    with pytest.raises(pc.AuditError, match="unexpected text after claim audit JSON"):
        pc.parse_audit(response + "\n" + response, PLAN)


@pytest.mark.parametrize("repeat_envelope", [False, True])
def test_indexed_binding_accepts_marker_inside_complete_passage(repo, tmp_path, monkeypatch, repeat_envelope):
    plan, claims, texts = fixture(count=2, expanded=0)
    source = claims[0]["evidence"][0]
    passage = f"{claims[0]['anchor']} The source also contains {h.PLAN_BINDING_MARKER} as literal text."
    source["quote"] = passage
    texts[source["url"]] = passage
    capture_fixture(monkeypatch, texts)
    report, state, audit = public(
        monkeypatch, repo, tmp_path, dict(plan=plan, claims=claims, repeat_binding_envelope=repeat_envelope),
    )
    if repeat_envelope:
        assert "BINDING-FAILED" in report and not state["claims"]
        debt = state["debt"]
        assert debt == audit["claim_audit_debt"]
        assert debt["failure_phase"] == "binding" and debt["failure_kind"] == "validation"
        assert [row["outcome"] for row in debt["attempts"]] == ["validation-invalid", "validation-invalid"]
        assert not any(row["role"].startswith("claim-attestation") for row in audit["attempt_ledger"])
    else:
        settled = {claim["anchor"]: claim for claim in state["claims"].values()}
        assert len(settled) == 2
        assert all(claim["verdict"] == "supported" and pc._captured_support(claim) for claim in settled.values())
        assert settled[claims[0]["anchor"]]["evidence"][0]["quote"] == passage
        assert not state["debt"] and "CLAIM-CLOSURE: 2 supported" in report


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("phase,provider_role,defect", [
    ("discovery", "evidence-discovery", "duplicate"),
    ("binding", "evidence-binding", "duplicate"),
    ("attestation", "evidence-text", "duplicate"),
    ("discovery", "evidence-discovery", "depth"),
    ("binding", "evidence-binding", "depth"),
    ("attestation", "evidence-text", "depth"),
    ("discovery", "evidence-discovery", "integer"),
    ("binding", "evidence-binding", "integer"),
    ("attestation", "evidence-text", "integer"),
    ("discovery", "evidence-discovery", "coverage-depth"),
])
def test_malformed_reply_uses_producing_roles_correction(
    repo, tmp_path, monkeypatch, phase, provider_role, defect, repair,
):
    plan, claims, texts = fixture(count=1, expanded=0)
    if phase == "discovery" and not repair:
        monkeypatch.setattr(es, "capture_all", lambda *a, **k: pytest.fail("invalid discovery reached capture"))
    else:
        capture_fixture(monkeypatch, texts)
    original_answer = Provider.answer
    rejected = []

    def answer(self, prompt, **kwargs):
        review = original_answer(self, prompt, **kwargs)
        if self.role != provider_role or (repair and rejected):
            return review
        if defect == "duplicate":
            if phase == "discovery":
                # Ordinary last-key-wins JSON would erase the only discovered claim.
                text = review.text.rstrip()[:-1] + ', "claims": []}'
            else:
                # Ordinary last-key-wins JSON would accept the second identity.
                text = review.text.replace('"evidence_index": 0', '"evidence_index": 99, "evidence_index": 0')
        elif defect == "coverage-depth":
            # CPython can decode this, but the wire bound protects consumers.
            nested = "[" * 80 + "0" + "]" * 80
            text = review.text.replace('"coverage": {', f'"coverage": {{"nested": {nested}, ')
        else:
            value = "[" * 2000 + "0" + "]" * 2000 if defect == "depth" else "9" * 8000
            text = review.text.split("\n", 1)[0] + "\n" + '{"malformed": ' + value + "}"
        rejected.append(text)
        return replace(review, text=text, raw=text)

    monkeypatch.setattr(Provider, "answer", answer)
    shared = dict(plan=plan, claims=claims)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    role = f"claim-{phase}"
    attempts = [row for row in audit["attempt_ledger"] if row["role"].startswith(role)]
    assert [row["role"] for row in attempts] == [role, f"{role}-validation-retry"]
    assert [row["outcome"] for row in attempts] == [
        "validation-invalid", "completed" if repair else "validation-invalid",
    ]
    assert [row["session_ref"] for row in attempts] == ["fixture-session", "fixture-session"]
    assert shared["resumed"].count((provider_role, "fixture-session")) == 1 + (phase == "binding")
    issue = {
        "duplicate": "duplicate JSON object key",
        "depth": "JSON nesting exceeds",
        "coverage-depth": "JSON nesting exceeds",
        "integer": "integer string conversion",
    }[defect]
    assert any(issue in prompt for name, prompt, _ in shared["calls"] if name == provider_role)
    for row, text in zip(attempts, rejected):
        assert issue in row["validation_issue"]
        assert row["returncode"] == 0
        assert row["raw_sha256"] == hashlib.sha256(text.encode()).hexdigest()
        assert row["failure_detail_excerpt"] and row["stderr_excerpt"]
    if repair:
        assert not state["debt"] and "CLAIM-CLOSURE: 1 supported" in report
        assert pc._captured_support(next(iter(state["claims"].values())))
    else:
        debt = state["debt"]
        assert debt == audit["claim_audit_debt"]
        assert debt["attempts"] == attempts
        assert debt["failure_phase"] == phase and debt["failure_kind"] == "validation"
        assert issue in report and not state["claims"]
        assert audit["attempt_ledger"][-1] == attempts[-1]


@pytest.mark.parametrize("returned", [None, "another-session", "session"])
def test_ordinary_claim_retry_requires_requested_session(repo, tmp_path, returned):
    from tests.test_plan_claims import ScriptedEngine, STRUCTURAL_CLEAR

    engine = ScriptedEngine(
        "invalid initial audit",
        Review(_audit(_claim()), returned, "correction stdout",
               failure_detail="actual detail", stderr="actual stderr"),
        STRUCTURAL_CLEAR,
    )
    lineage = "issue150-ordinary-retry"
    report = h.critique_plan(
        {"repo_path": str(repo), "plan_text": PLAN, "lineage": lineage, "round": 1,
         "stakes": "trusted local tool; evidence binding has high impact", "propose_patch": False},
        engine=engine, log_dir=tmp_path / "logs",
    )
    (path,) = (tmp_path / "logs").glob("*-critique_plan-*.json")
    audit = json.loads(path.read_bytes())
    state = cc.load_lineage(cc.default_state_root(), lineage, stamp="T", mode=cc.PLAN_MODE).claim_state
    initial, retry = audit["attempt_ledger"]
    assert initial["outcome"] == "validation-invalid"
    assert retry["role"] == "claim-audit-retry" and retry["session_ref"] == returned
    assert len(engine.prompts) == 3 and "Return the COMPLETE corrected audit" in engine.prompts[1]
    if returned == "session":
        assert retry["outcome"] == "completed" and not state["debt"]
        assert "CLAIM-CLOSURE: 1 supported" in report
    else:
        assert retry["outcome"] == "validation-invalid" and retry["validation_pointer"] == "/session_ref"
        debt = state["debt"]
        assert debt == audit["claim_audit_debt"]
        assert debt["failure_kind"] == "validation" and debt["returncode"] == 0
        assert debt["attempts"] == [initial, retry]
        assert debt["rejected_excerpt"] == "correction stdout"
        assert debt["failure_detail"] == "actual detail" and debt["stderr"] == "actual stderr"
        message = "resumable session" if returned is None else "different session"
        assert message in report
        assert not state["claims"] and "CONVERGENCE: BLOCKED" in report


@pytest.mark.parametrize("role,attempt,repair", [
    ("claim-discovery-validation-retry", 2, True),
    ("claim-binding", 2, False),
    ("claim-binding-validation-retry", 4, True),
    ("claim-attestation-validation-retry", 6, True),
])
def test_captured_resume_rejects_valid_output_from_another_session(
    repo, tmp_path, monkeypatch, role, attempt, repair,
):
    plan, claims, texts = fixture(count=1, expanded=0)
    capture_fixture(monkeypatch, texts)
    shared = dict(plan=plan, claims=claims, repair=repair, mismatched_session=attempt)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    phase = role.removeprefix("claim-").removesuffix("-validation-retry")
    debt = state["debt"]
    assert debt["failure_phase"] == phase and debt["failure_kind"] == "validation"
    assert "different session from the requested continuation" in report
    assert not state["claims"]
    assert len(shared["calls"]) == len(audit["attempt_ledger"]) == attempt
    observed = audit["attempt_ledger"][-1]
    assert observed["role"] == role and observed["outcome"] == "validation-invalid"
    assert observed["validation_pointer"] == "/session_ref"
    assert observed["session_ref"] == "different-provider-session" and observed["returncode"] == 0
    assert observed["raw_sha256"] == hashlib.sha256(observed["raw_excerpt"].encode()).hexdigest()
    assert debt["attempts"][-1] == observed
    assert all(session == "fixture-session" for _, session in shared["resumed"])


def test_expanded_binding_session_mismatch_preserves_other_batch_custody(repo, tmp_path, monkeypatch):
    plan, claims, texts = fixture(count=2, expanded=1)
    capture_fixture(monkeypatch, texts)
    shared = dict(plan=plan, claims=claims, mismatched_session=2)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    results = {claim["anchor"]: claim for claim in state["claims"].values()}
    assert results[claims[0]["anchor"]]["verdict"] == "unverified"
    assert results[claims[1]["anchor"]]["verdict"] == "supported"
    error = results[claims[0]["anchor"]]["capture_provenance"][0]["error"]
    assert "different session from the requested continuation" in error
    assert "BINDING-FAILED" in report
    bindings = [row for row in audit["attempt_ledger"] if row["role"] == "claim-binding"]
    assert [row["session_ref"] for row in bindings] == ["different-provider-session", "fixture-session"]
    assert all(session == "fixture-session" for _, session in shared["resumed"])


@pytest.mark.parametrize("repair,attempt", [(False, 3), (True, 6)])
def test_final_expanded_binding_mismatch_keeps_discovery_session(repo, tmp_path, monkeypatch, repair, attempt):
    plan, claims, texts = fixture(count=2, expanded=0)
    last_url = claims[-1]["evidence"][0]["url"]
    texts[last_url] = "x" * 450_000 + "\n" + texts[last_url]
    capture_fixture(monkeypatch, texts)
    original = h._CapturedClaimEngine.run
    aggregate = []

    def record(self, *a, **k):
        review = original(self, *a, **k)
        aggregate.append((review.session_ref, self.last_session, review.error))
        return review

    monkeypatch.setattr(h._CapturedClaimEngine, "run", record)
    shared = dict(plan=plan, claims=claims, repair=repair, mismatched_session=attempt)
    _, state, audit = public(monkeypatch, repo, tmp_path, shared)
    results = {claim["anchor"]: claim for claim in state["claims"].values()}
    assert results[claims[0]["anchor"]]["verdict"] == "supported"
    assert results[claims[1]["anchor"]]["verdict"] == "unverified"
    assert aggregate == [("fixture-session", "fixture-session", False)]
    role = "claim-binding-validation-retry" if repair else "claim-binding"
    rejected = audit["attempt_ledger"][attempt - 1]
    assert rejected["role"] == role and rejected["outcome"] == "validation-invalid"
    assert rejected["session_ref"] == "different-provider-session"


@pytest.mark.parametrize("repair", [False, True])
def test_attestation_execution_kind_reaches_public_report_and_debt(repo, tmp_path, monkeypatch, repair):
    plan, claims, texts = fixture(count=1, expanded=0)
    capture_fixture(monkeypatch, texts)
    shared = dict(plan=plan, claims=claims, repair=repair, attestation_execution_failure=2 if repair else 1)
    report, state, audit = public(monkeypatch, repo, tmp_path, shared)
    debt = state["debt"]
    assert debt["failure_phase"] == "attestation" and debt["failure_kind"] == "execution"
    assert debt["returncode"] == 73
    assert "EVIDENCE failure kind: execution" in report
    assert "ATTESTATION-FAILED" in report and "exit 73" in report
    assert audit["claim_audit_debt"] == debt
    terminal_attempts = [row for row in audit["attempt_ledger"] if row["role"].startswith("claim-attestation")]
    assert debt["attempts"] == terminal_attempts
    assert [row["outcome"] for row in terminal_attempts] == (
        ["validation-invalid", "failed"] if repair else ["failed"]
    )
    assert terminal_attempts[-1]["returncode"] == 73
    for key, expected in (("raw", "stdout"), ("failure_detail", "detail"), ("stderr", "stderr")):
        value = f"actual attestation {expected}"
        assert terminal_attempts[-1][key + "_excerpt"] == value
        assert terminal_attempts[-1][key + "_sha256"] == hashlib.sha256(value.encode()).hexdigest()


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
    assert_empty_provider_channels(debt)
    assert "no provider response for this failure" in report
    assert debt["returncode"] == 124
    assert "later role admission refused" in report
    if correction:
        assert debt["attempts"][0]["outcome"] == "validation-invalid"
    assert len(audit["attempt_ledger"]) > len(debt["attempts"])


def test_native_trial_resumes_durable_label_and_preserves_failed_receipt(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from paranoia_local import server
    from scripts import run_claim_binding_150_acceptance as native

    identity = {"revision": "fixture", "sha256": {}}
    monkeypatch.setattr(native, "source_identity", lambda: identity)
    monkeypatch.setattr(native.runpy, "run_path", lambda *_: None)
    monkeypatch.setattr(native, "observe_evidence_calls", lambda *_: None)
    monkeypatch.setattr(es, "capture_all", es.capture_all)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "argv", ["qualification", "--output", str(tmp_path)])
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    source = _source(url=native.URL, quote="Python 3.11.0, released on 24 October 2022")
    claim = _claim(anchor=native.PROPOSITION, proposition=native.PROPOSITION, evidence=[source])
    claim_state = pc.reconcile(
        {}, pc.parse_audit(_audit(claim), native.PLAN),
        lineage_id=native.LINEAGE, round_no=1, plan_text=native.PLAN,
    )
    predecessor = json.dumps({"rounds": 0, "review_state": {"last_round": 0},
                              "claim_state": claim_state})
    assert pc.frozen_supported_ids(claim_state, native.PLAN)
    state_path = tmp_path / "state/lineages" / (native.LINEAGE + ".json")
    calls = []
    measured = [10.0]
    monkeypatch.setattr(native, "time", SimpleNamespace(monotonic=lambda: measured[0]))

    def dispatch(tool, request, *, log_dir, **kwargs):
        measured[0] += 3.5
        assert tool == "critique_plan"
        calls.append(dict(request))
        log_dir.mkdir()
        (log_dir / "fixture-critique_plan-audit.json").write_text("{}")
        if len(calls) == 1:
            state_path.parent.mkdir(parents=True)
            state_path.write_text(predecessor)
        else:
            assert state_path.read_text() == predecessor
            assert not pc.frozen_supported_ids(claim_state, request["plan_text"])
        return "fixture report"

    def validate(record, *args, **kwargs):
        measured[0] += 29.0
        if len(calls) == 1:
            raise ValueError("fixture receipt rejected after support persisted")
        assert record["predecessor_text"] == predecessor

    monkeypatch.setattr(server, "dispatch", dispatch)
    monkeypatch.setattr(native, "validate", validate)
    with pytest.raises(ValueError, match="fixture receipt rejected"):
        native.main()
    first = next((tmp_path / "trials").glob("round-001-*/receipt.json"))
    original = first.read_bytes()
    assert json.loads(original)["outcome"] == "failed"
    assert json.loads(original)["elapsed_seconds"] == 3.5
    native.main()
    second = next((tmp_path / "trials").glob("round-002-*/receipt.json"))
    receipt = json.loads(second.read_bytes())
    assert receipt["outcome"] == "passed"
    assert receipt["elapsed_seconds"] == 3.5
    assert [request["round"] for request in calls] == [1, 2]
    assert calls[0]["repo_path"] == calls[1]["repo_path"]
    assert calls[0]["lineage"] == calls[1]["lineage"] == native.LINEAGE
    assert calls[1]["plan_text"].splitlines()[2] == native.PROPOSITION
    assert first.read_bytes() == original
    assert receipt["predecessor_sha256"] == native.sha(predecessor.encode())
    assert receipt["prior_receipts"] == {f"{first.parent.name}/receipt.json": native.sha(original)}


@pytest.mark.parametrize("mutation", [
    None, "valid-repair", "timeout", "orphan", "native-error", "review-error",
    "different-initial-binding-session",
    "missing-raw", "missing-stderr", "missing-failure_detail", "missing-returncode",
    "missing-error", "missing-duration_ms",
])
def test_native_attempt_replay_requires_observed_engine_call_and_valid_initial_roles(mutation):
    from dataclasses import asdict
    from paranoia_local.engines import CodexEngine
    from scripts import run_claim_binding_150_acceptance as native

    record = {"audit": {"attempt_ledger": []}, "reviews": []}
    profiles = [
        ("claim-discovery", "evidence-discovery", 900, None, "discovery"),
        ("claim-binding", "evidence-binding", 300, "discovery", "discovery"),
        ("claim-attestation", "evidence-text", 300, None, "attestation"),
    ]
    if mutation == "valid-repair":
        profiles.insert(2, ("claim-binding-validation-retry", "evidence-binding",
                            300, "discovery", "discovery"))
    for index, (phase, role, timeout, resumed, session) in enumerate(profiles):
        if mutation == "orphan" and index == 1:
            phase += "-validation-retry"
        if mutation == "different-initial-binding-session" and phase == "claim-binding":
            session = "unrelated-binding-session"
        events = [
            {"type": "thread.started", "thread_id": session},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "output"}},
            {"type": "turn.completed"},
        ]
        if mutation == "native-error" and index == 1:
            events.append({"type": "turn.failed", "error": {"message": "provider error"}})
        raw = "\n".join(map(json.dumps, events))
        review = Review("output", session, raw, duration_ms=1,
                        error=mutation == "review-error" and index == 1)
        row = h._attempt(phase, CodexEngine(), review, requested_timeout_sec=timeout).json()
        row["outcome"] = "validation-invalid" if mutation == "valid-repair" and index == 1 else "completed"
        record["audit"]["attempt_ledger"].append(row)
        record["reviews"].append({
            "role": role, "timeout": 299 if mutation == "timeout" and index == 1 else timeout,
            "resumed_session": resumed, "review": asdict(review), "prompt": "request",
        })
    if mutation and mutation.startswith("missing-"):
        record["reviews"][1]["review"].pop(mutation.removeprefix("missing-"))
    if mutation in (None, "valid-repair"):
        native.validate_attempts(record, h)
    else:
        with pytest.raises(ValueError):
            native.validate_attempts(record, h)


def native_review(text, session):
    raw = "\n".join(map(json.dumps, [
        {"type": "thread.started", "thread_id": session},
        {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
        {"type": "turn.completed"},
    ]))
    return Review(text, session, raw, duration_ms=1, failure_detail="", stderr="")


def schedule_native_lanes(monkeypatch, order, starts):
    from concurrent.futures import Future

    pending = {}

    def submit(pool, run_lane, lane):
        future = Future()
        pending[lane] = (run_lane, future)
        if len(pending) == len(order):
            calls = pending.copy()
            pending.clear()
            for scheduled in order:
                run, response = calls[scheduled]
                starts.append(scheduled)
                try:
                    response.set_result(run(scheduled))
                except BaseException as error:
                    response.set_exception(error)
        return future

    monkeypatch.setattr(h.census.telemetry, "submit", submit)


@pytest.fixture
def native_replay_receipt(tmp_path, monkeypatch, request):
    from dataclasses import asdict
    from paranoia_local.engines import CodexEngine
    from scripts import run_claim_binding_150_acceptance as native

    monkeypatch.setattr(h.inert_git, "require_supported_version", lambda: (2, 50, 1))
    monkeypatch.setattr(h.eng, "require_evidence_profile", lambda _: "test")
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    variant = getattr(request, "param", None)
    directory, fixture = native.prepare_trial(tmp_path)
    record = dict(**fixture, source={"revision": "fixture"}, reviews=[], captures=[], elapsed_seconds=1)
    clock = h.time.monotonic
    scripted_seconds = [0.0]
    quote = "Python 3.11.0, released on 24 October 2022"
    source = _source(url=native.URL, quote=quote)
    discovery = _audit(_claim(anchor=native.PROPOSITION, proposition=native.PROPOSITION, evidence=[source]))
    bound = h.PLAN_BINDING_MARKER + "\n" + json.dumps({"bindings": [{
        "claim_index": 0, "evidence_index": 0, "usable": True,
        "location": "   Release history  ", "passage": quote.replace(" released", "  released"),
    }]})
    cold = "=== EVIDENCE ATTESTATION JSON ===\n" + json.dumps({"attestations": [{
        "claim_index": 0, "evidence_index": 0, "publisher_authority": True,
        "authority_reason": "  Official  history  ", "passage_entailment": True,
        "entailment_reason": "  Exact  release date  ",
    }]})

    def staged_reply(lane):
        return json.dumps({
            "lane": lane, "findings": [], "class_assessments": [],
            "coverage": [{"id": key, "status": "covered", "summary": "checked",
                          "evidence": [{"anchor": "plan:3", "rationale": "fixture scope"}],
                          "finding_ids": []} for key in h.sp.CHECKLIST],
        })

    def run(engine, prompt, *args, **kwargs):
        scripted_seconds[0] += 0.005
        if engine.role == "evidence-discovery":
            return native_review(discovery, "discovery")
        if engine.role == "evidence-text":
            return native_review("invalid initial attestation", "cold")
        assert engine.role == native.STRUCTURAL_ROLE
        lane = next((line.split()[-1] for line in prompt.splitlines()
                     if line.startswith("ROLE: census lane ")), None)
        if lane == "domain":
            return native_review("", "staged-domain")
        if lane == "execution":
            return native_review(staged_reply("domain"), "staged-execution")
        if lane:
            return native_review(staged_reply(lane), "staged-" + lane)
        return native_review(json.dumps({
            "role": "census", "governing_findings": [], "debt_outcomes": [],
            "class_actions": {}, "concession_challenges": {},
        }), "staged-consolidation")

    def resume(engine, session, *args, **kwargs):
        scripted_seconds[0] += 0.005
        if engine.role == "evidence-binding":
            return native_review(bound if "rejected" in args[0] else "invalid initial binding", session)
        if engine.role == native.STRUCTURAL_ROLE:
            lane = session.removeprefix("staged-")
            assert lane in {"domain", "execution"}
            if lane == "domain" and variant == "wrong-session":
                return native_review(staged_reply(lane), "unrelated-session")
            return native_review(staged_reply(lane), session)
        assert engine.role == "evidence-text"
        return native_review(cold, session)

    def capture(candidates, **kwargs):
        digest = native.sha(quote.encode())
        rows = [es.Capture(candidate, native.URL, 200, "text/html", digest, digest, quote)
                for candidate in candidates]
        record["captures"].extend(map(asdict, rows))
        return rows

    def tracked_call(*, interrupt=False):
        with monkeypatch.context() as scope:
            # Restore the observed methods even though the harness installs wrappers.
            scope.setattr(CodexEngine, "run", run)
            scope.setattr(CodexEngine, "resume", resume)
            scope.setattr(es, "capture_all", capture)
            scope.setattr(h, "time", SimpleNamespace(monotonic=lambda: clock() + scripted_seconds[0]))
            native.observe_evidence_calls(CodexEngine, record)
            schedule_native_lanes(scope, ("domain", "execution", "integrity"), [])
            if interrupt:
                def stop(**kwargs):
                    raise RuntimeError("stop after durable claim settlement")
                scope.setattr(h, "_staged_structural_review", stop)
            return h.critique_plan(
                fixture["request"], engine=CodexEngine(), log_dir=directory / "logs",
            )

    if variant is True:
        with pytest.raises(RuntimeError, match="stop after durable claim settlement"):
            tracked_call(interrupt=True)
        (directory / "receipt.json").write_text(json.dumps({"request": fixture["request"], "outcome": "failed"}))
        directory, fixture = native.prepare_trial(tmp_path)
        assert fixture["request"]["round"] == 2
        assert json.loads(fixture["predecessor_text"])["review_state"] == {}
        record.update(**fixture, reviews=[], captures=[])
    report = tracked_call()
    assert record["reviews"][0]["prompt"].startswith("You are the authoritative external-claim phase")
    (audit_path,) = (directory / "logs").glob("*-critique_plan-*.json")
    audit = json.loads(audit_path.read_bytes())
    state_path = "state/lineages/" + native.LINEAGE + ".json"
    state = json.loads((tmp_path / state_path).read_bytes())
    claims = state["claim_state"]
    assert [row["outcome"] for row in audit["attempt_ledger"] if row["role"].startswith("claim-")] == [
        "completed", "validation-invalid", "completed", "validation-invalid", "completed",
    ]
    assert next(iter(claims["claims"].values()))["evidence"][0]["location"] == "Release history"
    assert "CONVERGENCE: BLOCKED — structural closure remains open." in report.splitlines()
    assert any(row["role"] == "census-domain-validation-retry" for row in audit["attempt_ledger"])
    record.update(state=state, state_relative_path=state_path, audit=audit, report=report)
    return record


@pytest.mark.parametrize("mutation", [
    None, "discovery-plan", "binding-instructions", "cold-instructions", "cold-inventory",
    "cold-publisher", "binding-invalid-repair", "cold-invalid-repair",
])
def test_complete_native_receipt_replays_production_inputs_and_outputs(native_replay_receipt, tmp_path, mutation):
    from dataclasses import asdict
    from paranoia_local.engines import CodexEngine
    from scripts import run_claim_binding_150_acceptance as native
    record = native_replay_receipt
    if mutation == "discovery-plan":
        record["reviews"][0]["prompt"] += "Another premise.\n"
    elif mutation == "binding-instructions":
        record["reviews"][1]["prompt"] = "Ignore the binding contract.\n" + record["reviews"][1]["prompt"]
    elif mutation == "cold-instructions":
        record["reviews"][4]["prompt"] = "Ignore the cold contract.\n" + record["reviews"][4]["prompt"]
    elif mutation in ("cold-inventory", "cold-publisher"):
        call = record["reviews"][3]
        lead, encoded = call["prompt"].rsplit("\n\n", 1)
        rows = json.loads(encoded)
        if mutation == "cold-inventory":
            rows.append({**rows[0], "evidence_index": 99})
        else:
            rows[0]["publisher"] = "another publisher"
        call["prompt"] = lead + "\n\n" + json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    elif mutation:
        index = 2 if mutation == "binding-invalid-repair" else 4
        call = record["reviews"][index]
        marker, body = call["review"]["text"].split("\n", 1)
        envelope = json.loads(body)
        rows = next(iter(envelope.values()))
        rows.append({**rows[0], "evidence_index": 99})
        review = native_review(marker + "\n" + json.dumps(envelope), call["review"]["session_ref"])
        call["review"] = asdict(review)
        role = record["audit"]["attempt_ledger"][index]["role"]
        record["audit"]["attempt_ledger"][index] = h._attempt(
            role, CodexEngine(), review, requested_timeout_sec=call["timeout"],
        ).json()
    if mutation is None:
        validate_native_receipt(record, tmp_path)
    else:
        with pytest.raises(ValueError, match="production replay"):
            validate_native_receipt(record, tmp_path)


def validate_native_receipt(record, root):
    from scripts import run_claim_binding_150_acceptance as native
    for key in ("state", "audit"):
        record[key + "_text"] = json.dumps(record[key])
        record[key + "_sha256"] = native.sha(record[key + "_text"].encode())
    record["report_sha256"] = native.sha(record["report"].encode())
    native.validate(record, h, pc, identity=record["source"], root=root)


@pytest.mark.parametrize("native_replay_receipt", [True], indirect=True)
def test_complete_native_receipt_resumes_after_claims_saved_before_structural_settlement(native_replay_receipt, tmp_path):
    validate_native_receipt(native_replay_receipt, tmp_path)


def test_complete_native_receipt_preserves_diagnostics_under_different_lane_schedule(
    native_replay_receipt, monkeypatch, tmp_path,
):
    record = native_replay_receipt
    assert [row["role"] for row in record["audit"]["rejected_payloads"]] == ["census-domain", "census-execution"]
    starts = []
    schedule_native_lanes(monkeypatch, ("execution", "integrity", "domain"), starts)
    validate_native_receipt(record, tmp_path)
    assert starts == ["execution", "integrity", "domain"]


def test_complete_native_receipt_accepts_repaired_empty_reply(native_replay_receipt, tmp_path):
    from scripts import run_claim_binding_150_acceptance as native
    record = native_replay_receipt
    attempt = next(row for row in record["audit"]["attempt_ledger"] if row["role"] == "census-domain")
    rejected = next(row for row in record["audit"]["rejected_payloads"] if row["role"] == "census-domain")
    assert attempt["response_sha256"] is None
    assert rejected["sha256"] == native.sha(b"")
    assert rejected["excerpt"] == ""
    validate_native_receipt(record, tmp_path)


@pytest.mark.parametrize("field", ["elapsed_seconds", "claim_duration_ms"])
def test_complete_native_receipt_requires_consistent_dispatch_duration(native_replay_receipt, tmp_path, field):
    record = native_replay_receipt
    validate_native_receipt(record, tmp_path)
    if field == "elapsed_seconds":
        record[field] = 0.000001
    else:
        total = sum(row["duration_ms"] for row in record["audit"]["attempt_ledger"]
                    if row["role"].startswith("claim-"))
        record["audit"][field] = total - 1
    with pytest.raises(ValueError, match="measured native dispatch"):
        validate_native_receipt(record, tmp_path)


@pytest.mark.parametrize("native_replay_receipt", ["wrong-session"], indirect=True)
def test_complete_native_receipt_rejects_structural_repair_from_different_session(native_replay_receipt, tmp_path):
    with pytest.raises(ValueError, match="same session"):
        validate_native_receipt(native_replay_receipt, tmp_path)


@pytest.mark.parametrize("line", [
    "LINEAGE: other (rounds recorded: 1)",
    "CLAIM-CLOSURE: 0 supported, 0 refuted, 1 unverified",
    "REVIEW-ATTEMPTS: total=0 validation-retries=0 validation-invalid=0 execution-failed=0",
    "STAGED-ATTEMPTS: total=0 validation-retries=0 validation-invalid=0 execution-failed=0",
    "CONVERGENCE: NOT-BLOCKED — contradictory clearance",
])
def test_complete_native_receipt_rejects_contradictory_trailer(native_replay_receipt, tmp_path, line):
    record = native_replay_receipt
    validate_native_receipt(record, tmp_path)
    record["audit"]["rendered_trailer"] += "\n" + line
    record["report"] += "\n" + line
    with pytest.raises(ValueError, match="production replay"):
        validate_native_receipt(record, tmp_path)


@pytest.mark.parametrize("mutation", [
    "missing-settlement", "nonzero", "fake-outcome", "fake-duration", "fake-channel",
    "wrong-rejected-sequence", "wrong-requested-session", "retry-before-initial",
])
def test_complete_native_receipt_binds_tracked_structural_result(native_replay_receipt, tmp_path, mutation):
    record = native_replay_receipt
    validate_native_receipt(record, tmp_path)
    if mutation == "missing-settlement":
        del record["audit"]["staged_settlement"]
    elif mutation == "nonzero":
        call = next(row for row in record["reviews"] if row["role"] == "evidence-repository")
        call["review"]["returncode"] = 3
    elif mutation == "wrong-rejected-sequence":
        rejected = record["audit"]["rejected_payloads"]
        rejected[0]["sequence"] = rejected[1]["sequence"]
    elif mutation == "wrong-requested-session":
        retry = next(row for row in record["reviews"] if row["resumed_session"] == "staged-domain")
        retry["resumed_session"] = "unrelated-session"
    elif mutation == "retry-before-initial":
        initial, retry = [i for i, row in enumerate(record["reviews"])
                          if row["review"]["session_ref"] == "staged-domain"]
        record["reviews"][initial], record["reviews"][retry] = record["reviews"][retry], record["reviews"][initial]
    else:
        attempt = next(row for row in record["audit"]["attempt_ledger"] if row["role"] == "census-domain")
        field, value = {
            "fake-outcome": ("outcome", "completed"), "fake-duration": ("duration_ms", 999),
            "fake-channel": ("raw_sha256", "f" * 64),
        }[mutation]
        attempt[field] = value
    with pytest.raises(ValueError, match=(
        "misbound native|native execution|production replay|rejected replies|lacks an invalid attempt"
        "|precedes its initial invocation|differs from observed native stdout"
    )):
        validate_native_receipt(record, tmp_path)


@pytest.mark.parametrize("change", ["readme", "untracked", "snapshot"])
def test_native_replay_rejects_changed_fixture(tmp_path, monkeypatch, change):
    from scripts import run_claim_binding_150_acceptance as native
    monkeypatch.setattr(h.inert_git, "require_supported_version", lambda: (2, 50, 1))
    _, fixture = native.prepare_trial(tmp_path)
    repo = tmp_path / "repository"
    revision = fixture["fixture_revision"]
    tree = h.orientation.snapshot_tree(repo, revision)
    wrapper = h.orientation.wrap_commit(repo, tree, revision)
    state = {"review_state": {"snapshot_digest": rc.digest(f"{native.PLAN}\0{wrapper}")}}
    native.validate_fixture_snapshot(tmp_path, revision, native.PLAN, state, h)
    if change == "readme":
        (repo / "README.md").write_text("Changed while HEAD stayed pinned.\n")
    elif change == "untracked":
        (repo / "extra.md").write_text("Additional reviewed material.\n")
    else:
        state["review_state"]["snapshot_digest"] = "different recorded snapshot"
    with pytest.raises(ValueError, match="frozen fixture|reviewed fixture"):
        native.validate_fixture_snapshot(tmp_path, revision, native.PLAN, state, h)


def test_native_report_replay_rejects_claim_closure_only_in_body(native_replay_receipt, tmp_path):
    record = native_replay_receipt
    trailer = record["audit"]["rendered_trailer"]
    claim_line = "CLAIM-CLOSURE: 1 supported, 0 refuted, 0 unverified\n"
    assert claim_line in trailer
    record["audit"]["rendered_trailer"] = trailer.replace(claim_line, "")
    record["report"] = claim_line + record["report"].replace(claim_line, "")
    with pytest.raises(ValueError, match="production replay"):
        validate_native_receipt(record, tmp_path)
