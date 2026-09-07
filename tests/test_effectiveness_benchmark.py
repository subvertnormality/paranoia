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
    def create(arm="single", control=False):
        case = build(ROOT)[0][int(control)]
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
@pytest.mark.parametrize("control", [False, True])
def test_real_public_handlers_bind_fixture_attempts_outputs_and_clear(pilot_slot, arm, control):
    directory, spec = pilot_slot(arm, control)
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
               "basis_quote": "", "witness_sha256": custody.json_digest(oracle["witness"]),
               "additional_witness": None}
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
        item = {**fp, "classification": classification}
        if classification == "fixture_problem":
            item["additional_witness"] = {"code": "assert False, 'unexpected contract violation'", "result": "AssertionError: unexpected contract violation"}
            item["witness_sha256"] = custody.json_digest(item["additional_witness"])
        result = scoring.validate_annotation(annotation(slot, "unresolved", [item]),
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



def test_prompt_contamination_is_rejected_before_provider(pilot_slot, monkeypatch):
    directory, spec = pilot_slot()
    from paranoia_local import handlers
    original = handlers._query_body
    monkeypatch.setattr(handlers, "_query_body", lambda *a, **k: original(*a, **k) + "\noracle.json")
    monkeypatch.setattr(engines.Engine, "_execute", lambda *a, **k: pytest.fail("contaminated provider admission"))
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    assert custody.collect_slot(directory, spec)["calls"] == 0
    assert not custody.collect_slot(directory, spec)["execution_success"]


def test_ordinary_query_edit_after_call_retains_cost_without_credit(pilot_slot, monkeypatch):
    directory, spec = pilot_slot()
    original = engines.Engine._execute
    def changed(*args, **kwargs):
        review = original(*args, **kwargs)
        (directory / "repository/app.py").write_text("ordinary edit")
        return review
    monkeypatch.setattr(engines.Engine, "_execute", changed)
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    slot = custody.collect_slot(directory, spec)
    assert slot["calls"] == 1 and not slot["execution_success"]


def test_contaminated_base_rejects_even_with_consistent_head_history(tmp_path):
    import subprocess
    case = build(ROOT)[0][0]
    repo = tmp_path / "repository"
    fixture = bench.setup_repo(repo, case["files"])
    # Rebuild the two-commit chain with a control in the base, preserving all
    # internally consistent hashes/history. The explicit base check must reject.
    base = fixture["base"]
    tree = bench.shared.git(repo, "rev-parse", fixture["head"] + "^{tree}")
    env = {**__import__("os").environ, "GIT_AUTHOR_NAME": "fixture",
           "GIT_AUTHOR_EMAIL": "fixture@example.test", "GIT_COMMITTER_NAME": "fixture",
           "GIT_COMMITTER_EMAIL": "fixture@example.test"}
    bad_base = subprocess.check_output(["git", "commit-tree", tree, "-m", "Specification"],
                                      cwd=repo, env=env, text=True).strip()
    head = subprocess.check_output(["git", "commit-tree", tree, "-p", bad_base, "-m", "Implementation"],
                                  cwd=repo, env=env, text=True).strip()
    bench.shared.git(repo, "reset", "--hard", head)
    fixture.update(base=bad_base, head=head,
                   base_tree=tree, head_tree=tree,
                   history=bench.shared.git(repo, "log", "--format=%H%x09%aI%x09%an%x09%s", "HEAD"))
    with pytest.raises(ValueError, match="base contains"):
        bench.verify_fixture(repo, case, fixture)


def test_scoring_receipt_binds_original_terminals_and_later_annotations(pilot_slot, monkeypatch):
    directory, spec = pilot_slot()
    bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
    root = directory.parent
    row = spec["slot"]
    target = root / row["id"]
    directory.rename(target)
    manifest = {"order": [row], "call_limit": bench.CALL_LIMIT}
    bench.shared.dump(root / "manifest.json", manifest)
    (root / "calls.txt").write_text("1")
    (root / "completions.jsonl").write_text(json.dumps({
        "id": row["id"], "sha256": bench.shared.sha((target / "terminal.json").read_bytes())}) + "\n")
    monkeypatch.setattr(bench, "load_manifest", lambda root: manifest)
    monkeypatch.setattr(bench, "specification", lambda *args: spec)
    slot = custody.collect_slot(target, spec)
    bench.shared.dump(target / "score.json", annotation(slot))
    bench.shared.dump(root / "oracle.json", build(ROOT)[1])
    terminal_before = (target / "terminal.json").read_bytes()
    scoring.seal_scores(root)
    assert bench.qualify_campaign(root)["qualified"]
    assert (target / "terminal.json").read_bytes() == terminal_before
    value = custody.read(target / "score.json")
    value["verdict"] = "unresolved"
    bench.shared.dump(target / "score.json", value)
    q = bench.qualify_campaign(root)
    assert not q["qualified"] and q["calls"] == 1
    assert any("scoring custody" in e for e in q["errors"])



def test_complete_campaign_retains_identical_failures_refusals_and_unscored_findings(
        tmp_path, pilot_slot, monkeypatch):
    original_output = bench.subprocess.check_output
    def version_only(argv, *args, **kwargs):
        if len(argv) == 2 and argv[0] in bench.shared.MODELS and argv[1] == "--version":
            return argv[0] + " test-version"
        return original_output(argv, *args, **kwargs)
    monkeypatch.setattr(bench.subprocess, "check_output", version_only)
    root = tmp_path / "campaign"
    bench.freeze(root, ROOT, call_limit=4)
    m = bench.load_manifest(root)
    def failed(self, argv, prompt, cwd, runner, timeout, on_progress=None, response_schema=None):
        text = ("Touching intervals incorrectly overlap. Empty intervals must overlap."
                if response_schema is None else "Provider unavailable")
        return engines.Review(text=text, session_ref=None, raw="", error=True,
                              returncode=127, stderr="same unavailable executable")
    base_run, base_resume, base_admit = engines.Engine.run, engines.Engine.resume, bench.shared.admit
    for row in m["order"]:
        directory = root / row["id"]
        with monkeypatch.context() as context:
            context.setattr(engines.Engine, "run", base_run)
            context.setattr(engines.Engine, "resume", base_resume)
            context.setattr(engines.Engine, "_execute", failed)
            context.setattr(bench.shared, "admit", base_admit)
            context.setenv("PARANOIA_STATE_ROOT", str(directory / "state"))
            bench.worker(directory / "input.json", bench.shared.sha((directory / "input.json").read_bytes()))
        with (root / "completions.jsonl").open("a") as f:
            f.write(json.dumps({"id": row["id"], "sha256": bench.shared.sha(
                (directory / "terminal.json").read_bytes())}) + "\n")
    q = bench.qualify_campaign(root)
    assert q["qualified"], q["errors"]
    assert q["calls"] == 4 and len(q["slots"]) == 32
    assert all(not s["execution_success"] and not s["clear_eligible"] for s in q["slots"].values())
    assert q["slots"]["t001"]["calls"] == 1 and q["slots"]["t002"]["calls"] == 3
    assert sum(s["calls"] for s in q["slots"].values()) == 4
    usage = scoring.stage_usage(q["slots"]["t002"])
    assert set(usage) == {"census-behaviour", "census-execution", "census-integrity"}
    assert all(v["calls"] == 1 for v in usage.values())
    oracle = custody.read(root / "oracle.json")
    for row in m["order"]:
        slot = q["slots"][row["id"]]
        score = annotation(slot, "operational_failure")
        if row["id"] == "t001":
            target = {"id": 1, "output": 0, "quote": "Touching intervals incorrectly overlap.",
                      "native_id": None, "classification": "target", "cluster": "target",
                      "reason": "The retained failed response quotes the target trigger.",
                      "basis_quote": "", "witness_sha256": custody.json_digest(oracle[row["case"]]["witness"]),
                      "additional_witness": None}
            fp = {**target, "id": 2, "quote": "Empty intervals must overlap.",
                  "classification": "false_positive", "cluster": "empty",
                  "basis_quote": "Empty intervals share no points."}
            score["findings"] = [target, fp]
            for verdict in ("operational_failure", "unresolved"):
                result = scoring.validate_annotation({**score, "verdict": verdict}, slot, oracle[row["case"]], row["arm"])
                assert result["tp"] == result["fp"] == 0 and result["unscored"]
        bench.shared.dump(root / row["id"] / "score.json", score)
    scoring.seal_scores(root)
    result = scoring.report(root)
    assert result["custody_qualified"] and not result["comparative_qualified"]
    assert result["calls"] == 4
    assert result["summary"]["single"]["target_detections"] == 0
    assert result["summary"]["single"]["unsupported_finding_clusters"] == 0
    assert result["summary"]["single"]["unscored_slots"] == 1
    assert not result["observed_superiority_criteria_met"]
    packet = scoring.export_human(root)
    assert len(packet["items"]) == 32


def test_unresolved_clean_false_positive_counts_as_case_event(tmp_path, monkeypatch):
    case = {"id": "clean"}
    order = bench.schedule([case])
    slots = {}
    for row in order:
        text = "Logging is required." if row["arm"] == "single" else "No actionable defects."
        slots[row["id"]] = {"outputs": [{"result": text}], "audits": [], "errors": [],
                           "execution_success": True, "clear_eligible": True,
                           "attempts": [], "attempt_roles": {}, "elapsed_ms": 1, "dispatch_ms": 1, "calls": 0}
    q = {"qualified": True, "errors": [], "calls": 0,
         "manifest": {"order": order, "cases": [case]}, "slots": slots}
    monkeypatch.setattr(scoring, "qualify_campaign", lambda root: q)
    oracle = {"clean": {"defective": False, "specification": "Logging is optional."}}
    bench.shared.dump(tmp_path / "oracle.json", oracle)
    bench.shared.dump(tmp_path / "scoring-receipt.json", {})
    for row in order:
        slot = slots[row["id"]]
        if row["arm"] == "single":
            finding = {"id": 1, "output": 0, "quote": "Logging is required.", "native_id": None,
                       "classification": "false_positive", "cluster": "logging",
                       "reason": "The specification makes logging optional.", "basis_quote": "Logging is optional.",
                       "witness_sha256": None, "additional_witness": None}
            value = annotation(slot, "unresolved", [finding])
        else:
            value = annotation(slot)
        (tmp_path / row["id"]).mkdir()
        bench.shared.dump(tmp_path / row["id"] / "score.json", value)
    result = scoring.report(tmp_path)
    assert result["summary"]["single"]["false_positives"] == 2
    assert result["summary"]["single"]["false_positive_rate"] == 1
    assert result["summary"]["single"]["operational_or_unresolved"] == 2
