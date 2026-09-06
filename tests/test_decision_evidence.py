"""Exact-snapshot decision admission and public retry/grounding acceptance."""
import json
from pathlib import Path
import pytest
from paranoia_local import arbitration as arb
from paranoia_local.decision_evidence import DecisionEvidence
from .conftest import commit_all, git
from .test_arbitrate_handler import (
    Agent, run, trailer_field, decider_reply, _no_preflight,
)


def admission(repo):
    return DecisionEvidence(repo, git(["rev-parse", "HEAD"], repo).strip())


@pytest.mark.parametrize("value", [
    "app.py:4", "repository/app.py:4", "NONE",
])
def test_valid_declarations(repo, value):
    admission(repo).validate_declarations({"DECISIVE-CITATION": value, "CITATIONS": value})


def test_exact_snapshot_and_source_decisions(repo):
    boundary = admission(repo)
    boundary.validate_declarations({
        "DECISIVE-CITATION": f"{boundary.snapshot[:12]}@app.py:4",
        "CITATIONS": f"{boundary.snapshot}@app.py:4",
    })
    # Neither packet membership nor a negative judgement becomes forced support.
    boundary.validate_declarations({
        "DECISIVE-CITATION": "SOURCE:src-" + "a" * 16, "CITATIONS": "NONE",
    })


@pytest.mark.parametrize("value", [
    "", "garbage", "app.py:0", "app.py:999", "/tmp/evidence/repository/app.py:4",
    "./app.py:4", "../app.py:4", "missing.py:4", "app.py:4,app.py:5",
    "app.py:4 trailing", "SOURCE:wrong", "app.py:" + "9" * 5000,
])
def test_invalid_decisive_declaration_is_not_dropped(repo, value):
    with pytest.raises(arb.ArbitrationError, match="DECISIVE-CITATION"):
        admission(repo).validate_declarations({"DECISIVE-CITATION": value, "CITATIONS": "NONE"})


@pytest.mark.parametrize("value", [
    "app.py:4,garbage", "app.py:4,", "NONE,app.py:4",
    "app.py:4,app.py:4,app.py:4,app.py:4", "./app.py:4",
])
def test_invalid_supporting_declaration_is_not_dropped(repo, value):
    with pytest.raises(arb.ArbitrationError, match="CITATIONS"):
        admission(repo).validate_declarations({"DECISIVE-CITATION": "NONE", "CITATIONS": value})


def test_old_commit_and_inert_symlink_are_rejected(repo):
    old = git(["rev-parse", "HEAD"], repo).strip()
    (repo / "alias.py").symlink_to("app.py")
    commit_all(repo, "add marker")
    for value in [f"{old}@app.py:4", "alias.py:1"]:
        with pytest.raises(arb.ArbitrationError):
            admission(repo).validate_declarations({"DECISIVE-CITATION": value, "CITATIONS": "NONE"})


def test_diagnostic_retains_both_fields_and_grammar_with_oversized_token(repo):
    with pytest.raises(arb.ArbitrationError) as error:
        admission(repo).validate_declarations({
            "DECISIVE-CITATION": "x" * 20000,
            "CITATIONS": "missing.py:4",
        })
    text = str(error.value)
    assert len(text) < 1000
    assert "DECISIVE-CITATION:" in text and "CITATIONS:" in text
    assert "repository-relative path:positive-line" in text
    assert "x" * 100 not in text


def audit(report):
    return json.loads(Path(trailer_field(report, "AUDIT")).read_text())


@pytest.mark.parametrize("replacement", ["app.py:4", "NONE", "SOURCE:src-" + "a" * 16])
def test_public_repair_preserves_independent_final_grounding(repo, tmp_path, replacement):
    scripted = Agent(lambda e, r: "opt-decimal")
    attempts = []
    def provider(**kwargs):
        text = scripted(**kwargs)
        if kwargs["cwd"] is None or kwargs["engine_name"] != "codex":
            return text
        attempts.append(kwargs)
        if len(attempts) == 1:
            return text.replace("DECISIVE-CITATION: app.py:4", "DECISIVE-CITATION: " + "x" * 5000).replace(
                "CITATIONS: NONE", "CITATIONS: missing.py:4")
        assert "DECISIVE-CITATION:" in kwargs["body"] and "CITATIONS:" in kwargs["body"]
        assert "repository-relative path:positive-line" in kwargs["body"]
        text = text.replace("DECISIVE-CITATION: app.py:4", f"DECISIVE-CITATION: {replacement}")
        if replacement.startswith("SOURCE:"):
            text = text.replace("PUBLISHER-AUTHORITY: N/A", "PUBLISHER-AUTHORITY: NO - absent authority")
            text = text.replace("PASSAGE-ENTAILMENT: N/A", "PASSAGE-ENTAILMENT: YES - exact")
            text = text.replace("DECISION-RELEVANCE: N/A", "DECISION-RELEVANCE: YES - relevant")
        return text
    report = run(repo, provider, tmp_path, clean=False)
    expected = "CONVERGED" if replacement == "app.py:4" else "UNRESOLVED"
    assert trailer_field(report, "ARBITRATION") == expected
    assert len(attempts) == 2
    record = audit(report)["rounds"][0]["codex"]
    assert len(record["attempts"]) == 2
    assert record["attempts"][0]["rejection"]
    assert record["attempts"][1]["rejection"] is None
    assert all(not Path(c["cwd"]).exists() for c in scripted.calls if c["cwd"] is not None)


@pytest.mark.parametrize("first", ["format", "evidence"])
@pytest.mark.parametrize("second", ["evidence", "execution"])
def test_public_shared_allowance_and_failed_sibling_retention(repo, tmp_path, first, second):
    scripted = Agent(lambda e, r: "opt-decimal")
    attempts = 0
    def provider(**kwargs):
        nonlocal attempts
        text = scripted(**kwargs)
        if kwargs["cwd"] is None or kwargs["engine_name"] != "codex":
            return text
        attempts += 1
        if attempts == 1 and first == "format":
            return "AUTHORITY: duplicated\n" + text
        if attempts == 2 and second == "execution":
            raise RuntimeError("correction execution failed")
        return text.replace("app.py:4", "/tmp/evidence/repository/app.py:4")
    report = run(repo, provider, tmp_path, clean=False)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert attempts == 2
    failed = audit(report)["failed_round"]["deciders"]
    assert failed["claude"]["selected"] == "opt-decimal"
    assert len(failed["codex"]["attempts"]) == 2
    assert failed["codex"]["attempts"][0]["raw"]
    assert all(not Path(c["cwd"]).exists() for c in scripted.calls if c["cwd"] is not None)


@pytest.mark.parametrize("holder", [False, True])
def test_round_two_repair_does_not_waive_gained_evidence(repo, tmp_path, holder):
    for name in ["elsewhere.py", "third.py"]:
        (repo / name).write_text("x\n" * 40)
    commit_all(repo, "disjoint evidence")
    target = "claude" if holder else "codex"
    extra = {
        ("codex", 1): {"decisive": "elsewhere.py:20"},
        ("claude", 1): {"decisive": "NONE" if holder else "app.py:4", "citations": "app.py:4"},
        ("codex", 2): {"decisive": "app.py:4" if holder else "third.py:20"},
        ("claude", 2): {"decisive": "third.py:20" if holder else "app.py:4"},
    }
    scripted = Agent(lambda e, r: "opt-float" if (e == "codex" and r == 1) else "opt-decimal", extra=extra)
    attempts = 0
    def provider(**kwargs):
        nonlocal attempts
        text = scripted(**kwargs)
        if kwargs["engine_name"] == target and "CODE REGIONS RELEVANT" in kwargs["body"]:
            attempts += 1
            if attempts == 1:
                return text.replace("third.py:20", "/tmp/evidence/repository/third.py:20")
        return text
    report = run(repo, provider, tmp_path, clean=False)
    assert trailer_field(report, "ARBITRATION") == "UNRESOLVED"
    assert trailer_field(report, "ROUNDS") == "2"
    assert attempts == 2
    records = audit(report)["rounds"][1][target]["attempts"]
    assert len(records) == 2 and records[0]["rejection"] and records[1]["rejection"] is None

def test_initial_prompt_states_exact_repository_relative_grammar():
    from paranoia_local import prompts
    assert "literal repository-relative" in prompts.ARBITRATE_INSTRUCTIONS
    assert "never an absolute temporary-workspace path" in prompts.ARBITRATE_INSTRUCTIONS
    assert "These ten lines" in prompts.ARBITRATE_INSTRUCTIONS
