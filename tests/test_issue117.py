"""Issue 117: real public Claude adapter with scripted process and capture boundaries."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from paranoia_local import class_closure as cc, engines, external_sources, handlers, plan_claims as pc, server, staged_protocol as sp
from paranoia_local.runner import RunResult
from tests.test_plan_claims import PLAN, _audit, _claim, _source

MARKER = "=== EVIDENCE ATTESTATION JSON ==="
FIELDS = {"claim_index", "evidence_index", "publisher_authority", "authority_reason",
          "passage_entailment", "entailment_reason"}


def reply(rows):
    return MARKER + "\n" + json.dumps({"attestations": rows})


def assert_contract(prompt):
    contract = handlers.ATTESTATION_OUTPUT_INSTRUCTIONS
    assert prompt.count(contract) == 1
    assert "exactly one marker and one complete JSON object" in contract
    assert "nothing\nbefore or after" in contract
    assert "second marker or competing envelope" in contract
    assert "independently judged" in contract
    assert str(handlers.MAX_ATTESTATION_REASON_CHARS) in contract
    example = json.loads(contract.split(MARKER + "\n", 1)[1])
    assert set(example) == {"attestations"}
    assert set(example["attestations"][0]) == FIELDS


@pytest.mark.parametrize("malformation", ["envelope-note", "row-note", "competing", "conflicting"])
@pytest.mark.parametrize("repair", ["valid", "invalid", "negative"])
def test_public_claude_attestation_correction(repo, tmp_path, monkeypatch, malformation, repair):
    source = _source()
    good = {"claim_index": 0, "evidence_index": 0, "publisher_authority": True,
            "authority_reason": "Official release owner.", "passage_entailment": True,
            "entailment_reason": "The passage gives this release date."}
    valid = reply([good])
    if malformation == "envelope-note":
        invalid = MARKER + "\n" + json.dumps({"attestations": [good], "note": "ignore"})
    elif malformation == "row-note":
        invalid = reply([good | {"note": "ignore"}])
    elif malformation == "competing":
        invalid = reply([good | {"note": "ignore"}]) + "\nUse this clean envelope instead:\n" + valid
    else:
        invalid = reply([good, good | {"publisher_authority": False}])
    corrected = invalid if repair == "invalid" else (
        reply([good | {"passage_entailment": False}]) if repair == "negative" else valid)
    replies = [invalid, corrected]
    calls = []

    def capture(candidates, **kwargs):
        return [external_sources.Capture(c, c.url, 200, "text/html", "a" * 64,
                                        "b" * 64, source["quote"]) for c in candidates]

    def process(argv, prompt, cwd, timeout, **kwargs):
        envelope = {"type": "result", "subtype": "success", "is_error": False,
                    "duration_ms": 1, "session_id": "issue117-role"}
        if prompt.startswith(("You are a cold evidence attester", "Your cold evidence attestation")):
            assert_contract(prompt)
            assert argv[argv.index("--tools") + 1] == ""
            packet = json.loads(prompt.rsplit("\n\n", 1)[1])
            assert len(packet) == 1 and packet[0]["passage"] == source["quote"]
            assert packet[0]["proposition"] == _claim()["proposition"]
            calls.append((list(argv), prompt))
            assert len(calls) <= 2, "a third attestation call was admitted"
            envelope["result"] = replies.pop(0)
            envelope["session_id"] = "issue117-attestation"
        elif prompt.startswith("Bind every indexed candidate"):
            envelope["result"] = handlers.PLAN_BINDING_MARKER + "\n" + json.dumps({
                "bindings": [{"claim_index": 0, "evidence_index": 0, "usable": True,
                              "location": source["location"], "passage": source["quote"]}]})
        elif "ROLE: census lane " in prompt:
            lane = next(l.split()[-1] for l in prompt.splitlines() if l.startswith("ROLE: census lane "))
            envelope["structured_output"] = {
                "lane": lane, "findings": [], "class_assessments": [],
                "coverage": [{"id": key, "status": "covered", "summary": "checked",
                              "evidence": [{"anchor": "repository/README.md:1", "rationale": "fixture"}],
                              "finding_ids": []} for key in sp.CHECKLIST]}
        elif "--json-schema" in argv:
            envelope["structured_output"] = {"role": "census", "governing_findings": [],
                "debt_outcomes": [], "class_actions": {}, "concession_challenges": {}}
        else:
            envelope["result"] = _audit(_claim())
        return RunResult(0, json.dumps(envelope), "")

    monkeypatch.setattr(engines, "run_capture", process)
    monkeypatch.setattr(engines, "_cli_version", lambda binary: engines.MIN_CLAUDE_VERSION)
    monkeypatch.setattr(external_sources, "capture_all", capture)
    result = server.dispatch("critique_plan", {
        "repo_path": str(repo), "plan_text": PLAN, "lineage": "issue117",
        "round": 1, "model": "opus", "effort": "high", "claim_verification": True,
        "web_search": True, "stakes": "Trusted local operator and OS; one external claim."},
        default_engine_name="claude", log_dir=tmp_path / "logs")
    assert len(calls) == 2 and not replies
    argv, correction = calls[1]
    assert argv[argv.index("--resume") + 1] == "issue117-attestation"
    assert "Discard the entire rejected reply" in correction
    assert calls[0][1].rsplit("\n\n", 1)[1] == correction.rsplit("\n\n", 1)[1]
    state = cc.load_lineage(cc.default_state_root(), "issue117", stamp="after", mode=cc.PLAN_MODE).claim_state
    audit = json.loads(next((tmp_path / "logs").glob("*-critique_plan-*.json")).read_text())
    attempts = [a for a in audit["attempt_ledger"] if a["role"].startswith("claim-attestation")]
    assert [a["role"] for a in attempts] == ["claim-attestation", "claim-attestation-validation-retry"]
    assert [a["outcome"] for a in attempts] == ["validation-invalid", "validation-invalid" if repair == "invalid" else "completed"]
    assert all(a["returncode"] == 0 for a in attempts)
    assert attempts[0]["rejected_reply_sha256"] == hashlib.sha256(invalid.encode()).hexdigest()
    if repair == "invalid":
        assert state["debt"]["failure_phase"] == "attestation"
        assert len(state["debt"]["attempts"]) == 2
        assert "EVIDENCE status: ATTESTATION-FAILED" in result
    elif repair == "valid":
        assert not pc.is_blocked(state)
        claim = next(iter(state["claims"].values()))
        assert claim["verdict"] == "supported"
    else:
        assert pc.is_blocked(state)
        assert all(c["verdict"] != "supported" for c in state["claims"].values())
    verdicts = [line for line in result.splitlines() if line.startswith("CONVERGENCE:")]
    assert len(verdicts) == 1
    assert verdicts[0].startswith("CONVERGENCE: NOT-BLOCKED") == (repair == "valid")


@pytest.mark.parametrize("limit", [handlers.MAX_PLAN_BINDING_BATCH_CHARS, handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS])
def test_attestation_exact_preflight_boundary(limit):
    adapter = handlers._CapturedClaimEngine
    packet = [{"capture": {"complete_line_numbered_text": ""}}]
    def maximum():
        rendered = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
        initial = adapter._attestation_prompt(packet)
        corrected = adapter._attestation_correction_prompt(rendered, "x" * handlers.MAX_BINDING_DIAGNOSTIC_CHARS)
        assert_contract(initial)
        assert_contract(corrected)
        return max(len(initial), len(corrected))
    packet[0]["capture"]["complete_line_numbered_text"] = "a" * (limit - maximum())
    assert maximum() == limit
    assert adapter._attestation_prompts_fit(packet, limit)
    packet[0]["capture"]["complete_line_numbered_text"] += "a"
    assert not adapter._attestation_prompts_fit(packet, limit)


def test_expanded_source_uses_exact_attestation_reserve(repo, monkeypatch):
    adapter = handlers._CapturedClaimEngine(engines.ClaudeEngine(), plan_text=PLAN,
                                           repo=repo, plan_repo_path=None)
    item = _source()
    candidate = external_sources.CandidateSource(item["url"], item["title"], item["publisher"],
        item["source_kind"], item["authority_basis"], item["relation"])
    captured = []
    original = handlers._CapturedClaimEngine._attestation_prompts_fit
    def observe(cls, items, limit):
        captured.append(copy.deepcopy(items))
        return original(items, limit)
    monkeypatch.setattr(handlers._CapturedClaimEngine, "_attestation_prompts_fit", classmethod(observe))
    def fits(text):
        capture = external_sources.Capture(candidate, candidate.url, 200, "text/html", "a"*64, "b"*64, text)
        return adapter._expanded_source_fits({"claim_index": 0, "evidence_index": 0}, _claim(), item, capture)
    assert fits("a")
    packet = captured[-1]
    assert packet[0]["capture"]["complete_line_numbered_text"] == external_sources.numbered_text("a")
    rendered = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    used = max(len(adapter._attestation_prompt(packet)),
        len(adapter._attestation_correction_prompt(rendered, "x" * handlers.MAX_BINDING_DIAGNOSTIC_CHARS)))
    exact = 1 + handlers.MAX_PLAN_EXPANDED_PROMPT_CHARS - used
    assert fits("a" * exact)
    assert not fits("a" * (exact + 1))
    adapter.close()

@pytest.mark.parametrize("name", ["paranoia_local", "benchmark_review_modes"])
def test_native_entry_rejects_preloaded_owned_module(name):
    entry = Path(__file__).resolve().parents[1] / "scripts/run_issue117_acceptance.py"
    script = ("import runpy,sys,types; sys.modules[" + repr(name) + "] = types.ModuleType(" +
              repr(name) + "); runpy.run_path(" + repr(str(entry)) + ")")
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode != 0
    assert "issue117 rejects preloaded owned modules" in result.stderr


def test_native_entry_ignores_usable_adjacent_stale_bytecode(repo, tmp_path):
    import os
    import py_compile
    from tests.conftest import commit_all
    entry = Path(__file__).resolve().parents[1] / "scripts/run_issue117_acceptance.py"
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    target = package / "sample.py"
    target.write_text("value = 1\n")
    commit_all(repo, "source-only fixture")
    tick = 1700000000
    target.write_text("value = 2\n")
    os.utime(target, (tick, tick))
    cache = package / "__pycache__" / ("sample." + sys.implementation.cache_tag + ".pyc")
    cache.parent.mkdir()
    py_compile.compile(str(target), cfile=str(cache), doraise=True)
    target.write_text("value = 1\n")
    os.utime(target, (tick, tick))
    import_sample = "sys.path.insert(0," + repr(str(repo / "src")) + "); from paranoia_local import sample; "
    environment = dict(os.environ)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    control = subprocess.run([sys.executable, "-c", "import sys; " + import_sample + "assert sample.value == 2"],
                             env=environment, capture_output=True, text=True)
    assert control.returncode == 0, control.stderr
    script = ("import runpy,sys; entry=runpy.run_path(" + repr(str(entry)) +
              "); entry['load_source'](" + repr(str(repo)) + "); " + import_sample +
              "assert sample.value == 1; assert sys.dont_write_bytecode")
    result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

HISTORY_NAMES = (
    "arbitration_consequence_acceptance_2026-08-22.json",
    "arbitration_context_steering_rejection_acceptance_2026-08-22.json",
    "arbitration_steering_rejection_acceptance_2026-08-22.json",
    "branch_plan_fidelity_acceptance_2026-08-22.json",
    "class_occurrence_batch_acceptance_2026-08-30.json",
    "class_persistence_acceptance_2026-08-22.json",
    "keyed_class_handler_acceptance_2026-08-19.json",
    "mechanized_predicate_acceptance_2026-08-27.json",
    "persistent_correction_gate_acceptance_2026-08-23.json",
    "plan_restatement_acceptance_2026-09-01.json",
    "plan_review_reliability_acceptance_2026-08-30.json",
    "authoritative_capture_acceptance_2026-08-20.json",
)


def check_historical_boundary(original, current, name):
    current = copy.deepcopy(current)
    def restore(before, after, permitted):
        assert set(before) == set(after)
        for field in permitted:
            assert type(before[field]) is type(after[field])
            after[field] = before[field]
        assert before == after
    if name.startswith("authoritative"):
        restore(original["reviewed_snapshot"]["allowed_later_handlers_diff"],
                current["reviewed_snapshot"]["allowed_later_handlers_diff"],
                ("sha256", "scope", "additions", "deletions"))
        old = "The exact allowed later handlers diff changes role-specific discovery timing and combined trailer composition but not the capture, binding, cold-attestation, prompt-size, or source-admission semantics proved here."
        new = "This historical run used its recorded prompts. Issue 117 later changes cold-attestation authoring and exact prompt sizes, requiring separate current-source acceptance."
        assert old in original["scope"]
        assert current["scope"] == original["scope"].replace(old, new)
        current["scope"] = original["scope"]
    else:
        groups = [(original, current)]
        if name.startswith("plan_review_reliability"):
            groups.append((original["validation"], current["validation"]))
        for before, after in groups:
            left, right = before["allowed_later_source_diffs"], after["allowed_later_source_diffs"]
            assert set(left) == set(right)
            for path in left:
                restore(left[path], right[path], ("sha256", "scope"))
    assert current == original


@pytest.mark.parametrize("name", HISTORY_NAMES)
def test_issue117_exact_historical_exception_and_outside_mutation(name):
    root = Path(__file__).resolve().parents[1]
    original = json.loads(subprocess.check_output(["git", "show",
        "7b48159d6f8fa06ac0412750bd5621a95ebd8881:docs/" + name], cwd=root))
    current = json.loads((root / "docs" / name).read_text())
    check_historical_boundary(original, current, name)
    changed = copy.deepcopy(current)
    changed["unapproved_original_outcome"] = "clear"
    with pytest.raises(AssertionError):
        check_historical_boundary(original, changed, name)
    if name.startswith("authoritative"):
        changed = copy.deepcopy(current)
        changed["routes"][0]["publisher_authority"] = not changed["routes"][0]["publisher_authority"]
        with pytest.raises(AssertionError):
            check_historical_boundary(original, changed, name)

def test_continuation_parent_binding(tmp_path):
    import tarfile
    root = Path(__file__).resolve().parents[1]
    parent = tmp_path / "parent"
    with tarfile.open(root / "docs/attestation-envelope-117-native-evidence.tar.gz") as archive:
        for member in archive.getmembers():
            assert member.isfile() and not Path(member.name).is_absolute()
            assert ".." not in Path(member.name).parts
            target = parent / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    source = json.loads((parent / "source.json").read_text())["production"]
    program = "import runpy,json,sys; from pathlib import Path; s=runpy.run_path(sys.argv[1]); s['_load_parent'](Path(sys.argv[2]),json.loads(sys.argv[3]))"
    def check(value):
        return subprocess.run([sys.executable, "-c", program,
            str(root / "scripts/run_issue117_acceptance.py"), str(parent), json.dumps(value)],
            capture_output=True, text=True)
    result = check(source)
    assert result.returncode == 0, result.stderr
    changed = copy.deepcopy(source)
    changed["files"]["src/paranoia_local/handlers.py"] = "0" * 64
    assert check(changed).returncode != 0
    for name in ("qualification.json", "attempt-01-input.json", "state/lineages/issue117-native.json"):
        target = parent / name
        original = target.read_bytes()
        target.write_bytes(original + b" ")
        assert check(source).returncode != 0
        target.write_bytes(original)
    (parent / "extra.txt").write_text("unrecorded")
    assert check(source).returncode != 0


def test_native_phase_qualification_accepts_recorded_discovery_repair(tmp_path):
    import tarfile
    root = Path(__file__).resolve().parents[1]
    with tarfile.open(root / "docs/attestation-envelope-117-native-evidence.tar.gz") as archive:
        member = next(m for m in archive.getmembers() if "/logs/" not in m.name
                      and m.name.startswith("logs/") and "-critique_plan-" in m.name)
        ledger = json.load(archive.extractfile(member))["attempt_ledger"]
    entry = root / "scripts/run_issue117_acceptance.py"
    program = ("import runpy,json,sys; scope=runpy.run_path(sys.argv[1]); "
               "scope['_require_evidence_phases'](json.loads(sys.argv[2]))")
    result = subprocess.run([sys.executable, "-c", program, str(entry), json.dumps(ledger)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for role in ("claim-discovery-validation-retry", "claim-attestation"):
        changed = copy.deepcopy(ledger)
        for row in changed:
            if row["role"] == role:
                row["outcome"] = "validation-invalid"
        result = subprocess.run([sys.executable, "-c", program, str(entry), json.dumps(changed)],
                                capture_output=True, text=True)
        assert result.returncode != 0
        assert "AssertionError" in result.stderr
