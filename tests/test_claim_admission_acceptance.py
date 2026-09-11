"""Acceptance identity must reject a different installation or changed evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import run_claim_admission_acceptance as acceptance
from tests.conftest import commit_all


@pytest.fixture
def frozen(repo):
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "server.py").write_text("# deterministic identity fixture\n")
    for name in acceptance.HARNESS_FILES:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((acceptance.ROOT / name).read_bytes())
    commit_all(repo, "acceptance fixture")
    return acceptance.freeze(repo, {"engine": "claude", "plan_text": "# Fixture",
                                    "class_closure": True, "lineage": "fixture-plan", "round": 1})


def test_fresh_isolated_interpreter_checks_selected_source(frozen, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(frozen))
    script = Path(frozen["source"]["path"]) / acceptance.HARNESS_FILES[0]
    result = subprocess.run(
        [sys.executable, "-I", str(script), "--verify-only", str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout)
    assert loaded["paranoia_local.server"] == str(script.parents[1] / "src/paranoia_local/server.py")


def test_other_loaded_installation_refuses(frozen, tmp_path):
    wrong = {"paranoia_local.server": SimpleNamespace(__file__=str(tmp_path / "server.py"))}
    with pytest.raises(ValueError, match="loaded module"):
        acceptance.verify_identity(frozen, modules=wrong)


@pytest.mark.parametrize("relative", ["src/paranoia_local/server.py", "scripts/benchmark_bootstrap.py"])
def test_edits_refuse_before_or_after_dispatch(frozen, relative):
    acceptance.verify_identity(frozen, modules={})
    path = Path(frozen["source"]["path"]) / relative
    path.write_text(path.read_text() + "# ordinary edit\n")
    with pytest.raises(ValueError, match="changed|binding"):
        acceptance.verify_identity(frozen, modules={})


@pytest.fixture
def receipt(frozen, tmp_path):
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({
        "returncode": 0, "error": False, "claim_audit_failed": False,
        "engine": "claude", "class_closure": True, "lineage": "fixture-plan", "round": 1,
        "rendered_trailer": "STRUCTURAL-PHASE: clear\nCONVERGENCE: NOT-BLOCKED",
        "claim_status": "parsed 1 new + 0 targeted retained + 0 frozen",
        "claim_model_calls": 2, "attempt_ledger": [
            {"role": "claim-discovery", "outcome": "completed", "returncode": 0},
            {"role": "claim-attestation", "outcome": "completed", "returncode": 0,
             "session_ref": "attester"}],
    }))
    loaded = {"paranoia_local.server": str(Path(frozen["source"]["path"]) / "src/paranoia_local/server.py")}
    return acceptance.make_receipt(frozen, "review result", audit, loaded)


def test_matching_receipt_requires_native_claim_success(frozen, receipt):
    acceptance.validate_receipt(frozen, receipt, "review result")


@pytest.mark.parametrize("channel", ["request", "response", "audit", "receipt", "provider_failure", "loaded", "missing_loaded"])
def test_changed_evidence_never_credits_acceptance(frozen, receipt, channel):
    manifest = copy.deepcopy(frozen)
    response = "review result"
    if channel == "request":
        manifest["request"]["plan_text"] += " changed"
    elif channel == "response":
        response += " changed"
    elif channel == "audit":
        Path(receipt["audit_path"]).write_text("{}")
    elif channel == "receipt":
        receipt["manifest_sha256"] = "0" * 64
    elif channel == "loaded":
        receipt["loaded_modules"]["paranoia_local.server"] = "/tmp/another-server.py"
    elif channel == "missing_loaded":
        receipt["loaded_modules"] = {}
    else:
        path = Path(receipt["audit_path"])
        value = json.loads(path.read_text())
        value["claim_audit_failed"] = True
        path.write_text(json.dumps(value))
        receipt["audit_sha256"] = acceptance.sha(path.read_bytes())
    with pytest.raises(ValueError):
        acceptance.validate_receipt(manifest, receipt, response)


def test_changed_wire_request_refuses_before_provider(frozen, tmp_path):
    invoke = acceptance.bound_dispatch(frozen, tmp_path, lambda *a, **k: pytest.fail("provider admitted"))
    with pytest.raises(ValueError, match="frozen invocation"):
        invoke("critique_plan", {"plan_text": "another request"})


def test_post_dispatch_edit_preserves_result_without_credit(frozen, tmp_path, monkeypatch):
    verify = acceptance.verify_identity
    monkeypatch.setattr(acceptance, "verify_identity", lambda manifest: verify(manifest, modules={}))
    def dispatch(*args, **kwargs):
        source = Path(frozen["source"]["path"]) / "src/paranoia_local/server.py"
        source.write_text("# changed during review\n")
        return "actual native result"
    invoke = acceptance.bound_dispatch(frozen, tmp_path, dispatch)
    with pytest.raises(ValueError, match="source bytes changed"):
        invoke("critique_plan", frozen["request"])
    assert (tmp_path / "native-result.txt").read_text() == "actual native result"
    assert not (tmp_path / "receipt.json").exists()


@pytest.mark.parametrize("change", [{"class_closure": False}, {"lineage": ""}, {"round": True}, {"round": 0}])
def test_one_shot_or_invalid_tracking_refuses_before_launch(frozen, change):
    with pytest.raises(ValueError, match="tracked|lineage|round"):
        acceptance.freeze(Path(frozen["source"]["path"]), frozen["request"] | change)


def rewrite_audit(receipt, change):
    path = Path(receipt["audit_path"])
    audit = json.loads(path.read_text())
    change(audit)
    path.write_text(json.dumps(audit))
    receipt["audit_sha256"] = acceptance.sha(path.read_bytes())


def test_production_source_local_failure_refuses_credit(frozen, receipt):
    from paranoia_local import engines, handlers
    failure = handlers._attempt("claim-attestation", engines.ClaudeEngine(), engines.Review(
        text="expanded attester failed", session_ref=None, raw="native failure",
        returncode=124, error=True,
    )).json()
    rewrite_audit(receipt, lambda audit: audit["attempt_ledger"].append(failure))
    with pytest.raises(ValueError, match="acceptance failed"):
        acceptance.validate_receipt(frozen, receipt, "review result")


def test_successful_discovery_correction_is_accepted(frozen, receipt):
    from paranoia_local import engines, handlers
    initial = handlers._attempt("claim-discovery", engines.ClaudeEngine(), engines.Review(
        text="malformed audit", session_ref="session", raw="initial", returncode=0,
    )).json() | {"outcome": "validation-invalid"}
    retry = handlers._attempt("claim-discovery-validation-retry", engines.ClaudeEngine(), engines.Review(
        text="valid audit", session_ref="session", raw="corrected", returncode=0,
    )).json()
    rewrite_audit(receipt, lambda audit: audit.update(
        attempt_ledger=[initial, retry, *audit["attempt_ledger"][1:]], claim_model_calls=3))
    acceptance.validate_receipt(frozen, receipt, "review result")


@pytest.mark.parametrize("change", [{"lineage": "another-plan"}, {"round": 2}, {"class_closure": False}, {"rendered_trailer": ""}])
def test_audit_tracking_must_match_invocation(frozen, receipt, change):
    rewrite_audit(receipt, lambda audit: audit.update(change))
    with pytest.raises(ValueError, match="tracking|structural"):
        acceptance.validate_receipt(frozen, receipt, "review result")


def test_continuation_preserves_selected_child_state_root(frozen, tmp_path, monkeypatch):
    state = tmp_path / "selected-state"
    (state / "lineages").mkdir(parents=True)
    prior = state / "lineages/fixture-plan.json"
    prior.write_text(json.dumps({"rounds": 1, "claim_state": {"debt": {"reason": "retained"}}}))
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(state))
    manifest = acceptance.freeze(Path(frozen["source"]["path"]), frozen["request"] | {"round": 2})
    assert manifest["state_root"] == str(state)
    assert manifest["predecessor_sha256"] == acceptance.sha(prior.read_bytes())
    params = acceptance.server_parameters(manifest, tmp_path)
    from mcp.client.stdio import get_default_environment
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    args = ["--verify-only" if value == "--serve" else value for value in params.args]
    child_env = get_default_environment() | params.env
    result = subprocess.run([params.command, *args], env=child_env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["paranoia_local.server"].startswith(manifest["source"]["path"])
    acceptance.verify_predecessor(manifest)
    prior.write_text("{}")
    result = subprocess.run([params.command, *args], env=child_env,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "predecessor lineage changed" in result.stderr
    with pytest.raises(ValueError, match="predecessor"):
        acceptance.verify_predecessor(manifest)


def test_continuation_requires_prior_lineage(frozen):
    with pytest.raises(ValueError, match="predecessor"):
        acceptance.freeze(Path(frozen["source"]["path"]), frozen["request"] | {"round": 2})


@pytest.mark.parametrize("role", ["claim-binding", "claim-attestation"])
@pytest.mark.parametrize("terminal", ["invalid-retry", "sessionless", "unrelated-success"])
def test_unrepaired_native_validation_failure_refuses(frozen, receipt, role, terminal):
    from paranoia_local import engines, handlers
    def attempt(name, session, outcome):
        return handlers._attempt(name, engines.ClaudeEngine(), engines.Review(
            text="native reply", session_ref=session, raw="native reply", returncode=0,
        )).json() | {"outcome": outcome}
    rows = [attempt(role, None if terminal == "sessionless" else "initial", "validation-invalid")]
    if terminal != "sessionless":
        rows.append(attempt(role + "-validation-retry", "initial" if terminal == "invalid-retry" else "other",
                            "validation-invalid" if terminal == "invalid-retry" else "completed"))
    rewrite_audit(receipt, lambda audit: audit["attempt_ledger"].extend(rows))
    with pytest.raises(ValueError, match="validation"):
        acceptance.validate_receipt(frozen, receipt, "review result")


@pytest.mark.parametrize("role", ["claim-binding", "claim-attestation"])
def test_native_validation_repair_preserves_acceptance(frozen, receipt, role):
    from paranoia_local import engines, handlers
    rows = [handlers._attempt(name, engines.ClaudeEngine(), engines.Review(
        text="native reply", session_ref="same-session", raw="native reply", returncode=0,
    )).json() | {"outcome": outcome} for name, outcome in
        [(role, "validation-invalid"), (role + "-validation-retry", "completed")]]
    rewrite_audit(receipt, lambda audit: audit["attempt_ledger"].extend(rows))
    acceptance.validate_receipt(frozen, receipt, "review result")


@pytest.mark.parametrize("requested,accepted", [(4, True), (5, True), (3, False), (2, False)])
def test_continuation_uses_last_settled_label_not_settlement_count(frozen, tmp_path, monkeypatch, requested, accepted):
    state = tmp_path / "label-state"
    (state / "lineages").mkdir(parents=True)
    prior = {"rounds": 2, "review_state": {"last_round": 3},
             "debt": {"round": 4, "reason": "failed attempt; may retry"}}
    (state / "lineages/fixture-plan.json").write_text(json.dumps(prior))
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(state))
    request = frozen["request"] | {"round": requested}
    if accepted:
        manifest = acceptance.freeze(Path(frozen["source"]["path"]), request)
        acceptance.verify_predecessor(manifest)
    else:
        with pytest.raises(ValueError, match="last_round"):
            acceptance.freeze(Path(frozen["source"]["path"]), request)


def test_native_expanded_sessionless_binding_cannot_credit_receipt(frozen, receipt, tmp_path):
    from paranoia_local import external_sources, handlers, plan_claims as pc
    from tests.test_issue115_history import load_test_module
    fixture = load_test_module("test_plan_claims")
    discovery = pc.parse_audit(fixture._audit(fixture._claim()), fixture.PLAN)
    item = discovery.claims[0]["evidence"][0]
    candidate = external_sources.CandidateSource(
        item["url"], item["title"], item["publisher"], item["source_kind"],
        item["authority_basis"], item["relation"],
    )
    captures = {(0, 0): external_sources.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        "x" * 590_000 + "\n" + item["quote"],
    )}
    reply = handlers.Review(text="sessionless native reply", session_ref=None,
                            raw="original provider envelope", returncode=0)
    engine = fixture._RoleScript({"evidence-binding": [reply]})
    ledger = []
    adapter = handlers._CapturedClaimEngine(
        engine, plan_text=fixture.PLAN, repo=fixture._repo(tmp_path),
        plan_repo_path=None, attempt_ledger=ledger,
    )
    adapter.captures = captures
    adapter.binding_engine = engine.for_role("evidence-binding")
    try:
        bound, reviews = adapter._bind_indexed("session", discovery, captures, "m", "high", {})
        assert reviews == [reply]
        assert ledger[0]["outcome"] == "completed"
        assert ledger[0]["raw_sha256"] == acceptance.sha(reply.raw.encode())
        persisted = adapter._attest(bound, "m", "high")
        assert persisted.claims[0]["verdict"] == "unverified"
        assert "binding" in persisted.claims[0]["capture_provenance"][0]["error"]
        rewrite_audit(receipt, lambda audit: audit["attempt_ledger"].extend(ledger))
        with pytest.raises(ValueError, match="binding.*session"):
            acceptance.validate_receipt(frozen, receipt, "review result")
    finally:
        adapter.close()


@pytest.mark.parametrize("replacement", [[], [{"role": "claim-attestation-validation-retry",
    "outcome": "completed", "returncode": 0, "session_ref": "historical"}]])
def test_current_wording_requires_initial_attestation(frozen, receipt, replacement):
    rewrite_audit(receipt, lambda audit: audit.update(
        attempt_ledger=[audit["attempt_ledger"][0], *replacement]))
    with pytest.raises(ValueError, match="attestation"):
        acceptance.validate_receipt(frozen, receipt, "review result")


@pytest.mark.parametrize("kind", ["valid", "repaired", "terminal-invalid", "empty"])
def test_actual_attester_qualification(frozen, receipt, tmp_path, kind):
    from paranoia_local import handlers, plan_claims as pc
    from tests.test_issue115_history import load_test_module
    fixture = load_test_module("test_plan_claims")
    ledger = []
    if kind == "empty":
        engine = fixture._RoleScript({})
        adapter = handlers._CapturedClaimEngine(
            engine, plan_text=fixture.PLAN, repo=fixture._repo(tmp_path),
            plan_repo_path=None, attempt_ledger=ledger)
        try:
            result = adapter._attest(pc.parse_audit(fixture._audit(), fixture.PLAN), "m", "high")
            assert isinstance(result, pc.Audit)
            assert not engine.calls and not ledger
        finally:
            adapter.close()
    else:
        rows = fixture._valid_attestation_rows()
        correction = None
        if kind != "valid":
            correction = copy.deepcopy(rows) if kind == "repaired" else None
            rows[0]["note"] = "invalid"
        result = fixture._run_indexed_attestation_rows(
            tmp_path, rows, correction_rows=correction, attempt_ledger=ledger)
        assert bool(isinstance(result, pc.Audit)) == (kind != "terminal-invalid")
        assert ledger[0]["role"] == "claim-attestation"
    rewrite_audit(receipt, lambda audit: audit.update(
        attempt_ledger=[audit["attempt_ledger"][0], *ledger]))
    if kind in {"valid", "repaired"}:
        acceptance.validate_receipt(frozen, receipt, "review result")
    else:
        with pytest.raises(ValueError, match="attestation|validation"):
            acceptance.validate_receipt(frozen, receipt, "review result")
