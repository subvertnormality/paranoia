"""Fail-closed measurement checks for the frozen arbitration comparison."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from paranoia_local import inert_tree, inert_git
from .conftest import commit_all, git

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("decision_benchmark", SCRIPTS / "benchmark_decision_evidence.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_expected_rendering_covers_bytes_modes_and_markers(repo):
    (repo / "binary.dat").write_bytes(b"\\0\\xff\\n")
    (repo / "empty").write_bytes(b"")
    (repo / "app.py").chmod(0o755)
    (repo / "alias").symlink_to("app.py")
    commit_all(repo, "binary executable and marker")
    head = git(["rev-parse", "HEAD"], repo).strip()
    git(["update-index", "--add", "--cacheinfo", f"160000,{head},module"], repo)
    git(["commit", "-qm", "gitlink"], repo)
    snapshot = git(["rev-parse", "HEAD"], repo).strip()
    expected = bench.expected_rows(repo, snapshot, inert_git)
    with inert_tree.materialized(repo, snapshot) as tree:
        actual = bench.observed_rows(tree.root)
        assert actual == expected
        # The expected rendering is independent of what the measured materializer wrote.
        (tree.repository / "app.py").chmod(0o644)
        (tree.repository / "app.py").write_text("wrong")
        assert bench.observed_rows(tree.root) != expected
        (tree.repository / "app.py").unlink()
        assert bench.observed_rows(tree.root) != expected


@pytest.mark.parametrize("mutation", ["changed", "missing_file", "missing_before", "missing_after",
                                     "missing_expected", "missing_attempt", "wrong_attempt", "cleanup"])
def test_workspace_gate_rejects_missing_or_mismatched_observation(mutation):
    row = {"provider": "codex", "root": "/fixture", "snapshot": "snap",
           "before": "exact", "after": "exact", "expected": "exact", "cleaned_up": True}
    attempts = [{"provider": "codex", "root": "/fixture", "snapshot": "snap", "before": "exact"}]
    assert bench.verify_workspace(row, attempts)
    if mutation in ("changed", "missing_file"):
        row["after"] = mutation
    elif mutation in ("missing_before", "missing_after", "missing_expected"):
        del row[mutation.removeprefix("missing_")]
    elif mutation == "missing_attempt":
        attempts.clear()
    elif mutation == "wrong_attempt":
        attempts[0]["snapshot"] = "other"
    else:
        row["cleaned_up"] = False
    assert not bench.verify_workspace(row, attempts)


def test_source_binding_rejects_package_changes(repo, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    bench.shared.git(source, "init", "-q", "-b", "main")
    bench.shared.git(source, "config", "user.name", "test")
    bench.shared.git(source, "config", "user.email", "test@example.test")
    package = source / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    bench.shared.git(source, "add", ".")
    bench.shared.git(source, "-c", "commit.gpgsign=false", "commit", "-qm", "source")
    record = bench.source_record(source)
    (package / "__init__.py").write_text("# changed")
    with pytest.raises(ValueError, match="source bytes"):
        bench.shared.validate_source(record)


def test_worker_observes_real_dispatch_attempts_and_cleanup(repo, tmp_path, monkeypatch):
    from paranoia_local import engines, arbitrate_handler as ah
    from .test_arbitrate_handler import BASE, Agent, decider_reply
    root = tmp_path / "campaign"
    directory = root / "trial-0"
    directory.mkdir(parents=True)
    (root / "counter").write_text("0")
    source = bench.source_record(SCRIPTS.parent)
    trial = {"version": "candidate", "case": {}}
    manifest = {"sources": {"candidate": source}, "models": {"codex": "m", "claude": "m"}}
    monkeypatch.setattr(bench, "load", lambda *a: (manifest, "frozen"))
    monkeypatch.setattr(bench, "preflight", lambda *a: trial)
    monkeypatch.setattr(ah, "_preflight", lambda *a: None)
    monkeypatch.setattr(engines, "require_evidence_profile", lambda *a: None)
    # Register worker-owned instrumentation mutations for fixture cleanup.
    for owner, name in [(inert_tree, "evidence_workspace"),
                        (inert_tree.EvidenceWorkspace, "cwd_for"),
                        (bench.shared, "install_observer"), (bench.shared, "admit"),
                        (engines.Engine, "run"), (engines.Engine, "resume")]:
        monkeypatch.setattr(owner, name, getattr(owner, name))
    # Earlier replay tests restore inherited methods as subclass attributes.
    # Fresh benchmark workers have no such aliases; remove only identical aliases
    # so the base Engine observer is exercised in the same shape as a fresh import.
    for cls in (engines.CodexEngine, engines.ClaudeEngine):
        for operation in ("run", "resume"):
            if operation in cls.__dict__:
                assert cls.__dict__[operation] is getattr(engines.Engine, operation)
                monkeypatch.delattr(cls, operation)
    scripted = Agent(lambda e, r: "opt-decimal")
    def execute(self, argv, prompt, cwd, *args, **kwargs):
        label = scripted._label_for(prompt, "opt-decimal")
        text = decider_reply(label)
        return engines.Review(text=text, raw=text, session_ref="fixture", returncode=0)
    monkeypatch.setattr(engines.Engine, "_execute", execute)
    def dispatch(spec_path):
        spec = json.loads(spec_path.read_text())
        bench.shared.install_observer(engines, directory, root / "counter")
        result = ah.arbitrate({**BASE, "repo_path": str(repo), "clean": False,
                               "models": spec["models"]}, log_dir=directory / "logs")
        assert "ARBITRATION: CONVERGED" in result
    monkeypatch.setattr(bench.shared, "worker", dispatch)
    bench.worker(root, 0, "frozen")
    trees = json.loads((directory / "workspaces.json").read_text())
    attempts = [json.loads(s) for s in (directory / "attempts.jsonl").read_text().splitlines()]
    assert len(trees["rows"]) == len(trees["provider_attempts"]) == len(attempts) == 2
    assert {a["role"] for a in attempts} == {"evidence-repository"}
    assert all(bench.verify_workspace(r, trees["provider_attempts"]) for r in trees["rows"])
    assert trees["source"] == source and trees["manifest_sha256"] == "frozen"


def test_retained_live_records_bind_exact_native_audit_bytes():
    receipt = json.loads((SCRIPTS.parent / "docs/decision_evidence_validation_2026-09-06.json").read_text())
    for live in (receipt["live"], receipt["corrected_live"], receipt["final_live"]):
        for kind in ("manifest", "report"):
            path = SCRIPTS.parent / live[kind + "_path"]
            assert bench.shared.sha(path.read_bytes()) == live[kind + "_sha256"]
        report = json.loads((SCRIPTS.parent / live["report_path"]).read_text())
        for binding, row in zip(live["audits"], report["rows"], strict=True):
            raw = (SCRIPTS.parent / binding["path"]).read_bytes()
            assert bench.shared.sha(raw) == binding["sha256"] == row["audit_sha256"]
            audit = json.loads(raw)
            assert (audit["outcome"], audit["selected"]) == (row["outcome"], row["selected"])

    replay = receipt["final_live"]["reporting_replay"]
    raw = (SCRIPTS.parent / replay["reproduced_report_path"]).read_bytes()
    assert bench.shared.sha(raw) == replay["reproduced_report_sha256"]
    assert replay["original_intermediate_report_preserved"] is False
    failed = json.loads(raw)
    accepted = json.loads((SCRIPTS.parent / receipt["final_live"]["report_path"]).read_text())
    assert failed["qualified"] is False
    assert all("No such file or directory: 'codex'" in row["failure"] for row in failed["rows"])
    for before, after in zip(failed["rows"], accepted["rows"], strict=True):
        for key in ("index", "attempts", "output", "elapsed_ms", "audit_sha256"):
            assert before[key] == after[key]
        # Successful qualification adds the derived global sequence binding.
        # Every originally captured workspace field must remain unchanged.
        workspace = json.loads(json.dumps(after["workspaces"]))
        for observation in workspace["provider_attempts"]:
            sequence = observation.pop("attempt_sequence")
            attempt = next(a for a in after["attempts"] if a["sequence"] == sequence)
            assert attempt["role"] == "evidence-repository"
            assert attempt["engine"] == observation["provider"]
        assert before["workspaces"] == workspace


def recorded_campaign(tmp_path, monkeypatch, *, two_rounds=False):
    root = tmp_path / "report-campaign"
    root.mkdir()
    trials = [{"case": {"id": case}, "version": v, "repetition": r, "padding_files": 0}
              for case in ("first", "second") for r in range(2)
              for v in ("baseline", "candidate")]
    manifest = {"trials": trials, "expected_baseline": "fixture", "large_padding": 0,
                "sources": {"baseline": {}, "candidate": {}},
                "oracle": {"first": "right", "second": "right"}, "starting_calls": 0, "prior_campaign": None}
    sequence = 0
    for index, trial in enumerate(trials):
        directory = root / f"trial-{index}"
        (directory / "logs").mkdir(parents=True)
        workspaces, observations, attempts = [], [], []
        for round_ in range(2 if two_rounds else 1):
            for provider in ("codex", "claude"):
                sequence += 1
                name = f"/observed/{index}/{round_}/{provider}"
                workspaces.append({"root": name, "provider": provider, "snapshot": "snapshot",
                                   "before": "exact", "after": "exact", "expected": "exact", "cleaned_up": True})
                observations.append({"root": name, "provider": provider, "snapshot": "snapshot",
                                     "before": "exact", "provider_attempt": round_ + 1})
                attempts.append({"sequence": sequence, "engine": provider, "role": "evidence-repository",
                                 "returncode": 0, "elapsed_ms": 20})
        bench.shared.dump(directory / "workspaces.json", {
            "rows": workspaces, "provider_attempts": observations,
            "source": {}, "trial": index, "manifest_sha256": "frozen"})
        bench.shared.dump(directory / "review-1.json", {
            "elapsed_ms": 100, "result": "ARBITRATION: CONVERGED\nSELECTED: right"})
        bench.shared.dump(directory / "logs/audit.json", {
            "tool": "arbitrate", "outcome": "CONVERGED", "selected": "right", "snapshot": "snapshot"})
        (directory / "attempts.jsonl").write_text("".join(json.dumps(a) + "\n" for a in attempts))
    (root / "counter").write_text(str(sequence))
    monkeypatch.setattr(bench, "load", lambda *a: (manifest, "frozen"))
    monkeypatch.setattr(bench, "preflight", lambda *a: None)
    return root


@pytest.mark.parametrize("failure", ["source_drift", "worker_marker", "missing_workspace", "missing_result"])
def test_report_retains_observations_when_qualification_fails(tmp_path, monkeypatch, failure):
    root = recorded_campaign(tmp_path, monkeypatch)
    directory = root / "trial-0"
    if failure == "source_drift":
        def invalid(*args):
            raise ValueError("source revision changed")
        monkeypatch.setattr(bench, "preflight", invalid)
    elif failure == "worker_marker":
        bench.shared.dump(directory / "failed.json", {"error": "worker failed after dispatch"})
    elif failure == "missing_workspace":
        (directory / "workspaces.json").unlink()
    else:
        (directory / "review-1.json").unlink()
    result = bench.report(root)
    row = result["rows"][0]
    assert not result["qualified"] and not row["qualified"]
    assert len(row["attempts"]) == 2
    assert result["calls"] == 16 and result["ledger_complete"]
    assert result["summary"]["baseline"]["provider_calls"] == 8
    assert row["outcome"] == "CONVERGED"  # retained observation, explicitly unqualified
    if failure == "missing_result":
        assert row["elapsed_ms"] is None
        assert result["summary"]["baseline"]["total_elapsed_ms"] is None
        assert result["summary"]["baseline"]["known_elapsed_ms"] == 300
    else:
        assert row["elapsed_ms"] == 100
        assert result["summary"]["baseline"]["total_elapsed_ms"] == 400


def test_report_rejects_missing_second_round_workspace_in_both_directions(tmp_path, monkeypatch):
    root = recorded_campaign(tmp_path, monkeypatch, two_rounds=True)
    before = bench.report(root)
    assert before["qualified"] and all(row["qualified"] for row in before["rows"])
    path = root / "trial-1/workspaces.json"
    trees = json.loads(path.read_text())
    trees["rows"].pop()
    bench.shared.dump(path, trees)
    result = bench.report(root)
    assert not result["qualified"]
    assert not result["rows"][1]["workspace_ok"]
    assert len(result["rows"][1]["attempts"]) == 4
    assert len(result["rows"][1]["workspaces"]["provider_attempts"]) == 4


def test_report_budget_continues_prior_calls(tmp_path, monkeypatch):
    root = recorded_campaign(tmp_path, monkeypatch)
    manifest, digest = bench.load(root)
    manifest["starting_calls"] = 32
    manifest["prior_campaign"] = {"calls": 32}
    for path in root.glob("trial-*/attempts.jsonl"):
        attempts = [json.loads(line) for line in path.read_text().splitlines()]
        for row in attempts:
            row["sequence"] += 32
        path.write_text("".join(json.dumps(a) + "\n" for a in attempts))
    (root / "counter").write_text("48")
    result = bench.report(root)
    assert result["calls"] == 16 and result["cumulative_calls"] == 48 and result["ledger_complete"]
