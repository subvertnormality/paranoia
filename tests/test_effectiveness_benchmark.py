"""Public-handler pilot qualification and failure-preserving negative cases."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark_effectiveness as bench
import effectiveness_custody as custody
import score_effectiveness as scoring
from effectiveness_corpus import build
from paranoia_local import engines, orientation
from tests.test_staged_protocol import decision, lane_value, wire_value


@pytest.fixture
def pilot_slot(tmp_path, monkeypatch):
    # Historical in-process replay restores inherited methods as subclass attributes.
    # A real worker starts fresh; remove only identical inherited-method shadows so
    # this fixture exercises the same dispatch lookup without masking any override.
    for cls in (engines.CodexEngine, engines.ClaudeEngine):
        for name in ("run", "resume"):
            if cls.__dict__.get(name) is getattr(engines.Engine, name):
                monkeypatch.delattr(cls, name)
    def create(arm="single"):
        case = build(ROOT)[0][0]
        directory = tmp_path / arm
        fixture = bench.setup_repo(directory / "repository", case["files"])
        fixture["packet_sha256"] = bench.shared.sha(orientation.build_packet(
            directory / "repository", fixture["base"], fixture["head"]))
        counter = directory / "calls.txt"
        counter.write_text("0")
        spec = {"slot": {"id": "t001", "case": case["id"], "arm": arm, "repetition": 0},
                "arm": arm, "case": case, "fixture": fixture,
                "source": bench.shared.source_record(ROOT), "harness": {},
                "models": bench.shared.MODELS, "versions": {},
                "stakes": bench.STAKES, "question": bench.QUESTION,
                "counter": str(counter), "maximum": bench.CALL_LIMIT}
        bench.shared.dump(directory / "input.json", spec)
        return directory, spec
    for owner, name in [(engines.Engine, "run"), (engines.Engine, "resume"),
                        (bench.shared, "admit")]:
        monkeypatch.setattr(owner, name, getattr(owner, name))
    def execute(self, argv, prompt, cwd, runner, timeout, on_progress=None, response_schema=None):
        if response_schema is None:
            text = "There are no actionable contract defects."
        else:
            props = response_schema["properties"]
            if "lane" in props:
                lane = props["lane"].get("const") or props["lane"]["enum"][0]
                value = lane_value(lane)
            else:
                role = props["role"].get("const") or props["role"]["enum"][0]
                value = decision(role)
            text = json.dumps(wire_value(value)).replace("plan:1", "repository/app.py:1")
        return engines.Review(text=text, session_ref=str(uuid.uuid4()), raw=text,
                              error=False, returncode=0, stderr="retained diagnostic")
    monkeypatch.setattr(engines.Engine, "_execute", execute)
    return create


@pytest.mark.parametrize("arm", ["single", "staged"])
def test_real_public_handlers_bind_fixture_attempts_outputs_and_clear(pilot_slot, arm):
    directory, spec = pilot_slot(arm)
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    slot = custody.collect_slot(directory, spec)
    assert not slot["errors"], (slot["errors"], custody.read(directory / "terminal.json"))
    assert slot["execution_success"]
    assert slot["clear_eligible"]
    assert slot["calls"] == (1 if arm == "single" else 4)
    assert all(row["process_channels"]["stderr"]["bytes"] > 0 for row in slot["attempts"])


@pytest.mark.parametrize("mutation", ["channel", "output", "audit", "attempt", "fixture"])
def test_custody_negative_keeps_attempt_cost(pilot_slot, mutation):
    directory, spec = pilot_slot()
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    assert custody.collect_slot(directory, spec)["execution_success"]
    if mutation == "channel":
        next(directory.glob("provider-*-stderr.bin")).write_text("changed")
    elif mutation == "output":
        (directory / "output-1.json").unlink()
    elif mutation == "audit":
        next((directory / "logs").glob("*query*.json")).unlink()
    elif mutation == "attempt":
        p = directory / "attempts.jsonl"
        p.write_text(p.read_text() * 2)
    else:
        (directory / "repository/app.py").write_text("changed")
        with pytest.raises(ValueError, match="fixture"):
            bench.verify_fixture(directory / "repository", spec["case"], spec["fixture"])
        return
    slot = custody.collect_slot(directory, spec)
    assert slot["errors"] and not slot["execution_success"]
    assert slot["calls"] >= 1


def test_all_corpus_witnesses_and_control_free_history(tmp_path):
    cases, oracle = build(ROOT)
    assert len(cases) == 8
    for case in cases:
        repo = tmp_path / case["id"]
        fixture = bench.setup_repo(repo, case["files"])
        bench.verify_fixture(repo, case, fixture)
        assert oracle[case["id"]]["witness"]["violates"] == oracle[case["id"]]["defective"]
        assert bench.shared.git(repo, "show", fixture["base"] + ":app.py") == ""
    rows = bench.schedule(cases)
    assert len(rows) == 32 and len({r["id"] for r in rows}) == 32


def test_failed_or_census_only_clear_is_not_creditable():
    for execution, eligible in [(False, False), (True, False)]:
        slot = {"outputs": [{"result": "no defects"}], "audits": [],
                "execution_success": execution, "clear_eligible": eligible}
        annotation = {"schema": 1, "output_digests": [bench.shared.sha("no defects")],
                      "coverage_attested": True, "verdict": "clear", "verdict_quote": "no defects", "findings": [],
                      "adjudicator": "implementer"}
        with pytest.raises(ValueError):
            scoring.validate_annotation(annotation, slot, {"defective": False}, "single")


@pytest.mark.parametrize("body", [
    "No defects.", "⚠️ REVIEW FAILED (engine=codex, exit=1)",
    "Recovered validation failure from claude.", "STRUCTURAL FAILURE: provider codex unavailable",
])
def test_human_export_preserves_native_cues_and_failure_meaning(body):
    from paranoia_local.handlers import _footer
    from types import SimpleNamespace
    review = engines.Review(text=body, session_ref="s", raw="", error=False, returncode=0)
    result = _footer(review, SimpleNamespace(name="codex"))
    assert scoring.strip_native_footer(result, {"engine": "codex", "session_ref": "s"}) == body
    assert "may reveal" in scoring.DISCLOSURE


def annotation(slot, verdict="clear", findings=None):
    return {"schema": 1, "output_digests": [bench.shared.sha(o["result"]) for o in slot["outputs"]],
            "coverage_attested": True, "verdict": verdict,
            "verdict_quote": slot["outputs"][0]["result"] if slot["outputs"] else "",
            "findings": findings or [], "adjudicator": "implementer"}


@pytest.mark.parametrize("failure", ["provider", "zero_calls", "no_consolidation", "bad_json"])
def test_failure_never_receives_clear_credit(pilot_slot, monkeypatch, failure):
    directory, spec = pilot_slot("staged" if failure == "no_consolidation" else "single")
    if failure == "provider":
        monkeypatch.setattr(engines.Engine, "_execute", lambda *a, **k:
            engines.Review(text="There are no defects.", session_ref="failed",
                           raw="provider envelope", error=True, returncode=1, stderr="failure"))
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    if failure == "zero_calls":
        (directory / "attempts.jsonl").write_text("")
    elif failure == "bad_json":
        with (directory / "attempts.jsonl").open("a") as f:
            f.write("{broken\n")
    elif failure == "no_consolidation":
        for path in (directory / "logs").glob("*.json"):
            audit = custody.read(path)
            if "attempt_ledger" in audit:
                audit["attempt_ledger"] = [
                    r for r in audit["attempt_ledger"] if r["role"] != "consolidation"]
                bench.shared.dump(path, audit)
    if failure != "provider":
        custody.terminal(directory, "completed")
    slot = custody.collect_slot(directory, spec)
    assert not slot["clear_eligible"]
    assert not slot["execution_success"]
    if failure != "zero_calls":
        assert slot["calls"] >= 1


def test_preflight_failure_has_zero_calls_and_retained_diagnostic(pilot_slot):
    directory, spec = pilot_slot()
    (directory / "repository/app.py").write_text("ordinary edit")
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    slot = custody.collect_slot(directory, spec)
    assert not slot["execution_success"] and slot["calls"] == 0
    assert "fixture working tree changed" in slot["terminal"]["error"]


def test_symmetric_scoring_clusters_counterevidence_and_unknowns():
    slot = {"outputs": [{"result": "bad boundary. repeated boundary. unsupported concern."}],
            "audits": [], "execution_success": True, "clear_eligible": True}
    oracle = {"defective": True, "witness": {"input": 1}, "specification": "Endpoints are half-open."}
    finding = {"id": 1, "output": 0, "quote": "bad boundary", "native_id": None,
               "classification": "target", "cluster": "target", "reason": "Witness reproduces it.",
               "basis_quote": "", "witness_sha256": custody.json_digest(oracle["witness"])}
    duplicate = {**finding, "id": 2, "quote": "repeated boundary"}
    scored = scoring.validate_annotation(annotation(slot, "defect", [finding, duplicate]), slot, oracle, "single")
    assert scored["tp"] == 1 and scored["fp"] == 0
    fp = {**finding, "id": 3, "quote": "unsupported concern", "classification": "false_positive",
          "cluster": "optional-extra", "basis_quote": "Endpoints are half-open."}
    assert scoring.validate_annotation(annotation(slot, "defect", [fp]), slot, oracle, "single")["fp"] == 1
    with pytest.raises(ValueError, match="frozen specification"):
        scoring.validate_annotation(annotation(slot, "defect", [{**fp, "basis_quote": "invented"}]), slot, oracle, "single")
    with pytest.raises(ValueError, match="coverage"):
        scoring.validate_annotation({**annotation(slot), "coverage_attested": False}, slot, oracle, "single")
    with pytest.raises(ValueError, match="quotation"):
        scoring.validate_annotation({**annotation(slot), "verdict_quote": "invented"}, slot, oracle, "single")
    for classification in ("advisory", "non_finding", "unscored", "fixture_problem"):
        result = scoring.validate_annotation(annotation(slot, "unresolved", [{**fp, "classification": classification}]),
                                             slot, oracle, "single")
        assert result["tp"] == result["fp"] == 0
        assert result["unscored"] == (classification in {"unscored", "fixture_problem"})
    assert scoring.ratio(0, 0) is None


def test_human_ratings_recompute_projection_and_require_complete_bound_rows(tmp_path, monkeypatch):
    q = {"qualified": True, "manifest": {"order": [{"id": "t001", "case": "case"}],
         "cases": [{"id": "case", "files": {"app.py": "pass"}}]},
         "slots": {"t001": {"outputs": [], "audits": [], "terminal": {"error": "provider unavailable"}}}}
    monkeypatch.setattr(scoring, "qualify_campaign", lambda root: q)
    monkeypatch.setattr(scoring, "report", lambda root: {
        "comparative_qualified": True, "trials": [{"id": "t001", "defective": False, "verdict": "operational_failure"}]})
    packet = scoring.export_human(tmp_path)
    assert "provider unavailable" in packet["items"][0]["reviews"][0]
    ratings = custody.read(tmp_path / "human-ratings-template.json")
    assert scoring.validate_ratings(tmp_path, ratings)["status"] == "pending"
    ratings["ratings"][0].update(rating="accept", reason="Accurately reports failure")
    assert scoring.validate_ratings(tmp_path, ratings)["status"] == "accepted"
    for changed in ([], ratings["ratings"] * 2):
        with pytest.raises(ValueError, match="missing or duplicate"):
            scoring.validate_ratings(tmp_path, {**ratings, "ratings": changed})
    with pytest.raises(ValueError, match="stale"):
        scoring.validate_ratings(tmp_path, {**ratings, "packet_sha256": "changed"})
    packet["items"][0]["reviews"] = ["No defects"]
    bench.shared.dump(tmp_path / "human-packet.json", packet)
    ratings["packet_sha256"] = bench.shared.sha((tmp_path / "human-packet.json").read_bytes())
    with pytest.raises(ValueError, match="projection"):
        scoring.validate_ratings(tmp_path, ratings)



def test_campaign_gate_keeps_cost_when_frozen_binding_breaks(pilot_slot, monkeypatch):
    directory, spec = pilot_slot()
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    target = directory.parent / "t001"
    directory.rename(target)
    monkeypatch.setattr(bench, "load_manifest", lambda root: (_ for _ in ()).throw(ValueError("changed source")))
    result = bench.qualify_campaign(directory.parent)
    assert not result["qualified"] and result["calls"] == 1
    assert not result["slots"]["t001"]["execution_success"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "sequence", "terminal"])
def test_campaign_gate_joins_complete_schedule_and_global_admission(pilot_slot, monkeypatch, mutation):
    directory, spec = pilot_slot()
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    root = directory.parent
    row = spec["slot"]
    # One real executed public-handler slot isolates campaign fan-in from freeze.
    manifest = {"order": [row], "call_limit": bench.CALL_LIMIT}
    target = root / row["id"]
    directory.rename(target)
    (root / "calls.txt").write_text("1")
    completion = {"id": row["id"], "sha256": bench.shared.sha((target / "terminal.json").read_bytes())}
    (root / "completions.jsonl").write_text(json.dumps(completion) + "\n")
    monkeypatch.setattr(bench, "load_manifest", lambda root: manifest)
    monkeypatch.setattr(bench, "specification", lambda *args: spec)
    assert bench.qualify_campaign(root)["qualified"]
    if mutation == "missing":
        (root / "completions.jsonl").unlink()
    elif mutation == "duplicate":
        (root / "completions.jsonl").write_text((json.dumps(completion) + "\n") * 2)
    elif mutation == "sequence":
        (root / "calls.txt").write_text("2")
    else:
        value = custody.read(target / "terminal.json")
        value["elapsed_ms"] += 1
        bench.shared.dump(target / "terminal.json", value)
    result = bench.qualify_campaign(root)
    assert not result["qualified"] and result["calls"] >= 1
    assert not result["slots"][row["id"]]["clear_eligible"]


def test_exhausted_admission_never_invokes_provider(pilot_slot, monkeypatch):
    directory, spec = pilot_slot()
    Path(spec["counter"]).write_text(str(spec["maximum"]))
    def forbidden(*args, **kwargs):
        pytest.fail("provider invoked after exhausted admission")
    monkeypatch.setattr(engines.Engine, "_execute", forbidden)
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    slot = custody.collect_slot(directory, spec)
    assert not slot["execution_success"] and slot["calls"] == 0
    assert (directory / "refusals.jsonl").exists()
