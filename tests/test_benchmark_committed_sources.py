"""Benchmark admission must reject preexisting dirty source before any spend."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from tests.conftest import commit_all, git

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_review_modes as shared
import benchmark_snapshot_materialization as local
import benchmark_decision_evidence as live


@pytest.mark.parametrize("launcher", ["local", "live", "modes"])
@pytest.mark.parametrize("version", ["baseline", "candidate"])
@pytest.mark.parametrize("mutation", ["modified", "missing", "extra", "nested", "staged"])
def test_freeze_rejects_preexisting_dirty_modules_without_launch(
    repo, tmp_path, monkeypatch, launcher, version, mutation,
):
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "sample.py").write_text("value = 1\n")
    commit_all(repo, "source")
    other = tmp_path / "other"
    git(["clone", "-q", str(repo), str(other)], tmp_path)
    sources = {"baseline": repo, "candidate": other}
    target = sources[version] / "src/paranoia_local"
    if mutation in {"modified", "staged"}:
        (target / "sample.py").write_text("value = 2\n")
    elif mutation == "missing":
        (target / "sample.py").unlink()
    elif mutation == "extra":
        (target / "extra.py").write_text("extra = True\n")
    else:
        (target / "nested").mkdir()
        (target / "nested/extra.py").write_text("extra = True\n")
    if mutation == "staged":
        git(["add", "."], sources[version])
    revision = git(["rev-parse", "HEAD"], repo).strip()
    monkeypatch.setattr(local, "BASELINE", revision)
    monkeypatch.setattr(live, "BASELINE", revision)
    real_run = shared.subprocess.run
    def no_launch(argv, **kwargs):
        assert argv[0] == "git", "source rejection must precede providers and timed workers"
        return real_run(argv, **kwargs)
    monkeypatch.setattr(shared.subprocess, "run", no_launch)
    output = tmp_path / "campaign"
    with pytest.raises(ValueError):
        if launcher == "modes":
            shared.freeze(SimpleNamespace(output=output, **sources, counter=None))
        else:
            {"local": local, "live": live}[launcher].freeze(output, **sources)
    assert not (output / "manifest.json").exists()
    assert not list(output.glob("trial-*"))


def test_source_record_cannot_freeze_extra_module_as_authoritative(repo):
    package = repo / "src/paranoia_local/nested"
    package.mkdir(parents=True)
    (package / "sample.py").write_text("value = 1\n")
    commit_all(repo, "nested committed source")
    record = shared.source_record(repo)
    assert "src/paranoia_local/nested/sample.py" in record["files"]
    extra = package / "extra.py"
    extra.write_text("extra = True\n")
    record["files"]["src/paranoia_local/nested/extra.py"] = shared.sha(extra.read_bytes())
    with pytest.raises(ValueError, match="committed"):
        shared.validate_source(record)


def test_live_freeze_binds_explicit_baseline_large_workloads_and_pair_order(
    repo, tmp_path, monkeypatch,
):
    import json
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "sample.py").write_text("value = 1\n")
    commit_all(repo, "source")
    revision = git(["rev-parse", "HEAD"], repo).strip()
    def version_only(argv, **kwargs):
        assert argv in (["codex", "--version"], ["claude", "--version"])
        return "test-cli"
    monkeypatch.setattr(live.subprocess, "check_output", version_only)
    root = tmp_path / "large"
    live.freeze(root, repo, repo, expected_baseline=revision, large_padding=3000)
    manifest, _ = live.load(root)
    assert manifest["expected_baseline"] == revision
    assert [r["version"] for r in manifest["trials"]] == [
        "baseline", "candidate", "candidate", "baseline",
        "candidate", "baseline", "baseline", "candidate"]
    for index, row in enumerate(manifest["trials"]):
        fixture = root / f"trial-{index}/repository"
        files = {p.relative_to(fixture).as_posix(): p.read_text()
                 for p in (fixture / "_benchmark_padding").glob("*.txt")}
        assert files == live.padding_files(row["padding_files"])
        assert len(set(files.values())) == row["padding_files"]
        for name, body in row["case"]["files"].items():
            assert (fixture / name).read_text() == body
    original = (root / "manifest.json").read_bytes()
    for mutation in ("baseline", "padding", "schedule", "snapshot", "oracle"):
        changed = json.loads(original)
        if mutation == "baseline":
            changed["expected_baseline"] = "0" * 40
        elif mutation == "padding":
            changed["trials"][2]["padding_files"] = 0
        elif mutation == "schedule":
            changed["trials"][0]["version"] = "candidate"
        elif mutation == "snapshot":
            changed["trials"][0]["snapshot"] = "0" * 40
        else:
            changed["oracle"][next(iter(changed["oracle"]))] = "wrong"
        shared.dump(root / "manifest.json", changed)
        (root / "manifest.sha256").write_text(shared.sha((root / "manifest.json").read_bytes()))
        with pytest.raises(ValueError):
            live.load(root)
    assert (root / "counter").read_text() == "0"
    assert not list(root.glob("trial-*/attempts.jsonl"))
