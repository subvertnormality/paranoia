"""Closed historical metadata boundary for issue 115; never new live acceptance."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = "f4e810911e8a60845ab797f913a252d4ea38039f"
RECORDS = {
    "class_occurrence_batch_acceptance_2026-08-30.json": [("allowed_later_source_diffs",)],
    "keyed_class_handler_acceptance_2026-08-19.json": [("allowed_later_source_diffs",)],
    "persistent_correction_gate_acceptance_2026-08-23.json": [("allowed_later_source_diffs",)],
    "plan_restatement_acceptance_2026-09-01.json": [("allowed_later_source_diffs",)],
    "plan_review_reliability_acceptance_2026-08-30.json": [
        ("allowed_later_source_diffs",), ("validation", "allowed_later_source_diffs")],
    "authoritative_capture_acceptance_2026-08-20.json": [
        ("reviewed_snapshot", "allowed_later_plan_claims_diff"),
        ("reviewed_snapshot", "allowed_later_handlers_diff")],
}


def at(value, path):
    for key in path:
        value = value[key]
    return value


def historical(name):
    return json.loads(subprocess.run(
        ["git", "show", f"{BASE}:docs/{name}"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout)


@pytest.mark.parametrize("name", RECORDS)
def test_original_acceptance_is_immutable_except_existing_allowance_metadata(name):
    old = historical(name)
    current = json.loads((ROOT / "docs" / name).read_text())
    for path in RECORDS[name]:
        before, after = at(old, path), at(current, path)
        assert set(before) == set(after)
        rows = [(before, after)] if name.startswith("authoritative") else [
            (before[key], after[key]) for key in before]
        for original, updated in rows:
            assert set(original) == set(updated)
            assert set(original) <= {"sha256", "scope", "additions", "deletions"}
            for key in original:
                assert type(updated[key]) is type(original[key])
                updated[key] = original[key]
    if name.startswith("authoritative"):
        original_sentence = "The exact allowed later handlers diff changes role-specific discovery timing and combined trailer composition but not the capture, binding, cold-attestation, prompt-size, or source-admission semantics proved here."
        qualification = "This historical run used its recorded prompts. Issue 117 later changes cold-attestation authoring and exact prompt sizes, requiring separate current-source acceptance."
        assert current["scope"] == old["scope"].replace(original_sentence, qualification)
        current["scope"] = old["scope"]
    assert current == old


SCRIPT_RECORDS = [
    ("class_occurrence_batch", False),
    ("persistent_correction_gate", False),
    ("plan_restatement", False),
    ("plan_review_reliability", False),
    ("plan_review_reliability", True),
]


@pytest.mark.parametrize("stem,nested", SCRIPT_RECORDS)
def test_script_allowances_accept_control_and_reject_mutations(stem, nested):
    name = next(name for name in RECORDS if name.startswith(stem + "_acceptance"))
    value = json.loads((ROOT / "docs" / name).read_text())
    validate = importlib.import_module("scripts.run_" + stem + "_acceptance").validate_artifact
    kwargs = {} if stem == "plan_review_reliability" else {"require_committed": False}
    validate(value, ROOT, **kwargs)
    path = ("validation", "allowed_later_source_diffs") if nested else ("allowed_later_source_diffs",)
    for mutation in ("missing", "extra", "mismatch"):
        changed = deepcopy(value)
        allowed = at(changed, path)
        key = "src/paranoia_local/plan_claims.py"
        if key not in allowed:
            key = next(iter(allowed))
        if mutation == "missing":
            del allowed[key]
        elif mutation == "extra":
            allowed["not-an-accepted-source.py"] = {"sha256": "0" * 64, "scope": "invalid"}
        else:
            allowed[key]["sha256"] = "0" * 64
        with pytest.raises(ValueError, match="later-source allowance") as caught:
            validate(changed, ROOT, **kwargs)
        assert "committed" not in str(caught.value)


def invoke_existing(name, value, monkeypatch, tmp_path):
    """Replace only this artifact's read and, for keyed, its HEAD envelope."""
    target = ROOT / "docs" / name
    read_text, run = Path.read_text, subprocess.run
    payload = json.dumps(value)
    keyed = name.startswith("keyed")
    if not keyed:
        assert set(at(value, RECORDS[name][0])) == set(at(historical(name), RECORDS[name][0])), (
            "capture allowance field shape"
        )
    def read(path, *args, **kwargs):
        return payload if path == target else read_text(path, *args, **kwargs)

    def git(args, *positional, **kwargs):
        if keyed and args == ["git", "show", f"HEAD:docs/{name}"] and kwargs.get("cwd") == ROOT:
            assert kwargs.get("text") is True and kwargs.get("capture_output") is True
            return subprocess.CompletedProcess(args, 0, stdout=payload, stderr="")
        return run(args, *positional, **kwargs)

    with monkeypatch.context() as adapter:
        adapter.setattr(Path, "read_text", read)
        adapter.setattr(subprocess, "run", git)
        if keyed:
            test_review_census = load_test_module("test_review_census")
            test_review_census.test_keyed_handler_acceptance_replays_production_lifecycle(tmp_path)
        else:
            test_plan_claims = load_test_module("test_plan_claims")
            test_plan_claims.test_authoritative_capture_acceptance_record()


def load_test_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", [
    "keyed_class_handler_acceptance_2026-08-19.json",
    "authoritative_capture_acceptance_2026-08-20.json",
])
def test_existing_assertion_validators_reject_only_at_allowance_boundary(name, monkeypatch, tmp_path):
    value = json.loads((ROOT / "docs" / name).read_text())
    invoke_existing(name, value, monkeypatch, tmp_path)
    keyed = name.startswith("keyed")
    for mutation in ("missing", "extra", "mismatch"):
        changed = deepcopy(value)
        allowance = at(changed, RECORDS[name][0])
        key = "src/paranoia_local/plan_claims.py" if keyed else "sha256"
        if mutation == "missing":
            del allowance[key]
        elif mutation == "extra":
            allowance["unexpected"] = {"scope": "invalid", "sha256": "0" * 64} if keyed else 0
        elif keyed:
            allowance[key]["sha256"] = "0" * 64
        else:
            allowance["sha256"] = "0" * 64
        with pytest.raises(AssertionError) as caught:
            invoke_existing(name, changed, monkeypatch, tmp_path)
        # Prove which assertion rejected, not merely that any assertion failed.
        traceback = caught.value.__traceback__
        while traceback.tb_next:
            traceback = traceback.tb_next
        frame = traceback.tb_frame
        # The live frame has advanced after unwinding; use the traceback's exact line.
        line = Path(frame.f_code.co_filename).read_text().splitlines()[traceback.tb_lineno - 1]
        if keyed:
            assert line.strip() in {
                'assert isinstance(allowance, dict) and set(allowance) == {"scope", "sha256"}',
                'assert hashlib.sha256(diff).hexdigest() == allowance["sha256"]',
                'assert changed == set(artifact["allowed_later_source_diffs"])',
            }
        elif mutation == "mismatch":
            assert line.strip() == 'assert hashlib.sha256(claims_diff).hexdigest() == claims_allowed["sha256"]'
        else:
            assert "assert set(at(value, RECORDS[name][0]))" in line
