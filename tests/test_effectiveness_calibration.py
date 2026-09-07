"""Finite corpus references, regression mutations, and freeze admission."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark_effectiveness as bench
import effectiveness_corpus as corpus
from effectiveness_calibration import calibrate, digest, fixture
from tests.test_effectiveness_benchmark import pilot_slot


@pytest.fixture(scope="module")
def built():
    return corpus.build(ROOT)


def case_for(built, family, defective):
    cases, oracle = built
    case = next(c for c in cases if oracle[c["id"]]["family"] == family
                and oracle[c["id"]]["defective"] is defective)
    return case, oracle[case["id"]]


def test_all_cases_have_reproducible_calibration_and_controls_pass(built):
    cases, oracle = built
    assert sum(len(o["calibration"]["checks"]) for o in oracle.values()) == 1648
    for case in cases:
        entry = oracle[case["id"]]
        calibrated = entry["calibration"]
        assert calibrated == calibrate(entry["family"], case["files"], entry["defective"])
        assert bool(calibrated["target_failures"]) is entry["defective"]
        assert entry["witness"]["violates"] is entry["defective"]
        assert len({r["id"] for r in calibrated["checks"]}) == len(calibrated["checks"])
        assert calibrated["checks_sha256"] == digest(calibrated["checks"])


@pytest.mark.parametrize("family", ["overlap", "reserve", "diagnostic", "identity"])
def test_target_repaired_or_reintroduced_cannot_be_mislabeled(built, family):
    bad, _ = case_for(built, family, True)
    good, _ = case_for(built, family, False)
    with pytest.raises(ValueError, match="lost target defect"):
        calibrate(family, good["files"], True)
    with pytest.raises(ValueError, match="calibration failed"):
        calibrate(family, bad["files"], False)


@pytest.mark.parametrize("mutation", ["closing", "opening", "excerpt", "aggregation"])
def test_parser_control_rejects_prior_fixture_problems(built, mutation):
    case, _ = case_for(built, "diagnostic", False)
    files = deepcopy(case["files"])
    if mutation == "closing":
        files["app.py"] = files["app.py"].replace(
            'if remainder == "```" and fenced:', 'if remainder == "```":')
    elif mutation == "opening":
        files["app.py"] = files["app.py"].replace(
            '    elif fenced and not remainder:\n        remainder = "missing closing fence"\n', "")
    elif mutation == "excerpt":
        files["app.py"] = files["app.py"].replace(
            'f"{reason} [/claims/{index}]"',
            'f"{reason}; item={_excerpt(json.dumps(item, ensure_ascii=False))}"')
    else:
        files = case_for(built, "diagnostic", True)[0]["files"]
    with pytest.raises(ValueError, match="calibration failed"):
        calibrate("diagnostic", files, False)


@pytest.mark.parametrize("mutation", ["blank", "bool", "return-alias"])
def test_identity_control_rejects_text_type_and_projection_regressions(built, mutation):
    case, _ = case_for(built, "identity", False)
    files = deepcopy(case["files"])
    if mutation == "blank":
        files["helpers.py"] = files["helpers.py"].replace(" or not value.strip()", "")
    elif mutation == "bool":
        files["app.py"] = files["app.py"].replace("type(index) is not int", "not isinstance(index, int)")
    else:
        files["app.py"] = files["app.py"].replace('"evidence_index": index,', '"evidence_index": float(index),')
    with pytest.raises(ValueError, match="calibration failed"):
        calibrate("identity", files, False)


def test_malformed_scalar_result_does_not_alias_boolean_reference(built):
    case, _ = case_for(built, "overlap", False)
    files = deepcopy(case["files"])
    files["app.py"] = "def overlap(a, b):\n    return int(bool(set(range(*a)) & set(range(*b))))\n"
    with pytest.raises(ValueError, match="return-shape"):
        calibrate("overlap", files, False)


def test_diagnostic_bound_carries_every_admitted_index_and_both_coverage_fields(built):
    case, oracle = case_for(built, "diagnostic", False)
    with fixture(case["files"]) as (_, helper):
        limit, bound = helper.MAX_ACTIVE_CLAIMS, helper.DIAGNOSTIC_CHARS
    rows = oracle["calibration"]["checks"]
    for partial in (False, True):
        actual = next(r["actual"] for r in rows if r["id"] == f"maximum-diagnostic-{partial}-True")
        assert len(actual["reason"]) <= bound
        assert all(f"claim {i}:" in actual["reason"] for i in range(limit))
        assert "prior_dispositions" in actual["reason"] and "prior_assessments" in actual["reason"]
    assert next(r for r in rows if r["id"] == f"count-{limit + 1}")["actual"]["kind"] == "error"


def test_explicit_historical_patch_and_identity_domain_provenance(built):
    for defective, revision in [(True, "1ca55d9^"), (False, "1ca55d9")]:
        case, oracle = case_for(built, "diagnostic", defective)
        original, provenance = corpus.historical(ROOT, revision, "parse_audit")
        patched, record = corpus.calibrated_diagnostic(original, provenance)
        assert patched == case["files"]["app.py"]
        assert record == oracle["provenance"]
        assert record["historical_app_sha256"] == hashlib.sha256(original.encode()).hexdigest()
        assert record["calibration_patch_sha256"] == hashlib.sha256(record["calibration_patch"].encode()).hexdigest()
        assert "fenced" in record["calibration_patch"]
    case, oracle = case_for(built, "identity", False)
    historical, _ = corpus.historical(ROOT, "ac50c47", "_validate_capture_attestations")
    assert case["files"]["app.py"] == historical
    spec = case["files"]["SPEC.md"]
    assert "str.strip()" in spec and "Non-HTTP(S) evidence" in spec
    outside = next(r for r in oracle["calibration"]["checks"] if r["domain"] == "outside")
    assert outside["id"] == "historical-ftp-domain-observation"
    assert outside["input"]["evidence"][0]["url"].startswith("ftp:")
    assert "no acceptance promise" in outside["expected"]["contract"]


def test_broken_control_blocks_build_and_freeze_before_provider_admission(tmp_path, monkeypatch):
    original = corpus.calibrated_diagnostic
    def broken(app, provenance):
        app, provenance = original(app, provenance)
        return app.replace('if remainder == "```" and fenced:', 'if remainder == "```":'), provenance
    monkeypatch.setattr(corpus, "calibrated_diagnostic", broken)
    with pytest.raises(ValueError, match="calibration failed"):
        bench.freeze(tmp_path / "pilot", ROOT)
    assert not (tmp_path / "pilot/calls.txt").exists()
    assert not (tmp_path / "pilot/manifest.json").exists()
    assert not list((tmp_path / "pilot").glob("t*/attempts.jsonl"))


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    original = bench.subprocess.check_output
    def output(argv, *args, **kwargs):
        if len(argv) == 2 and argv[0] in {"codex", "claude"} and argv[1] == "--version":
            return "test-cli-version\n"
        return original(argv, *args, **kwargs)
    monkeypatch.setattr(bench.subprocess, "check_output", output)
    root = tmp_path / "frozen"
    bench.freeze(root, ROOT)
    return root


@pytest.mark.parametrize("change", ["missing-calibration", "changed-calibration", "changed-contract"])
def test_calibration_and_card_bindings_fail_before_launch(frozen, change):
    manifest = json.loads((frozen / "manifest.json").read_text())
    key = str(ROOT / "scripts/effectiveness_calibration.py")
    if change == "missing-calibration":
        manifest["harness"].pop(key)
    elif change == "changed-calibration":
        manifest["harness"][key] = "0" * 64
    else:
        manifest["plan_sha256"] = "0" * 64
    bench.shared.dump(frozen / "manifest.json", manifest)
    (frozen / "manifest.sha256").write_text(bench.shared.sha((frozen / "manifest.json").read_bytes()))
    with pytest.raises(ValueError):
        bench.run(frozen)
    assert (frozen / "calls.txt").read_text() == "0"
    assert not list(frozen.glob("t*/attempts.jsonl"))


def test_changed_control_is_refused_by_public_worker_before_calls(pilot_slot):
    directory, spec = pilot_slot(control=True)
    (directory / "repository/app.py").write_text("def overlap(a, b): return True\n")
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    collected = bench.custody.collect_slot(directory, spec)
    assert collected["calls"] == 0 and not collected["execution_success"]
    assert "fixture" in collected["terminal"]["error"]
