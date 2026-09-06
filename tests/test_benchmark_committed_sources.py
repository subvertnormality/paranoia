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


@pytest.mark.parametrize("version", ["baseline", "candidate"])
@pytest.mark.parametrize("entry", ["benchmark_review_modes", "benchmark_snapshot_materialization",
                                    "benchmark_decision_evidence"])
def test_source_only_boundary_ignores_same_tick_stale_production_bytecode(
    repo, tmp_path, version, entry,
):
    import os
    import py_compile
    import subprocess
    package = repo / "src/paranoia_local"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    source = package / "sample.py"
    source.write_text("value = 1\n")
    commit_all(repo, "committed source")
    tick = 1700000000
    source.write_text("value = 2\n")
    os.utime(source, (tick, tick))
    # Explicit destination models a preexisting adjacent timestamp cache even
    # though the parent test process already uses the benchmark cache policy.
    cache = package / "__pycache__" / f"sample.{sys.implementation.cache_tag}.pyc"
    cache.parent.mkdir()
    py_compile.compile(str(source), cfile=str(cache), doraise=True)
    source.write_text("value = 1\n")
    os.utime(source, (tick, tick))
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    script = ("import sys; sys.path.insert(0, " + repr(str(scripts)) + "); "
              + "import " + entry + " as entry; "
              + "shared = getattr(entry, 'shared', entry); "
              + "sources = {" + repr(version) + ": shared.source_record(" + repr(str(repo)) + ")}; "
              + "sys.path.insert(0, " + repr(str(repo / "src")) + "); "
              + "from paranoia_local import sample; assert sample.value == 1; "
              + "assert sys.dont_write_bytecode; "
              + "from pathlib import Path; assert not list(Path(sys.pycache_prefix).rglob('*.pyc'))")
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    # The negative control proves this was a usable stale cache, not merely a
    # cache-shaped file which ordinary Python would also ignore.
    control = ("import sys; sys.path.insert(0, " + repr(str(repo / "src")) + "); "
               + "from paranoia_local import sample; assert sample.value == 2")
    environment = dict(os.environ)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    subprocess.run([sys.executable, "-c", control], env=environment,
                   check=True, capture_output=True, text=True)


@pytest.mark.parametrize("entry", ["benchmark_snapshot_materialization",
                                    "benchmark_decision_evidence"])
def test_entry_bootstrap_ignores_stale_imported_harness_bytecode(tmp_path, entry):
    import os
    import py_compile
    import subprocess
    import shutil
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name in [entry + ".py", "benchmark_review_modes.py", "benchmark_bootstrap.py"]:
        shutil.copyfile(scripts / name, tmp_path / name)
    source = tmp_path / "benchmark_review_modes.py"
    original = source.read_bytes()
    mutated = original.replace(b"gpt-6-astra", b"bad-cache!!", 1)
    assert len(mutated) == len(original) and mutated != original
    source.write_bytes(mutated)
    tick = 1700000000
    os.utime(source, (tick, tick))
    cache = tmp_path / "__pycache__" / f"benchmark_review_modes.{sys.implementation.cache_tag}.pyc"
    cache.parent.mkdir()
    py_compile.compile(str(source), cfile=str(cache), doraise=True)
    source.write_bytes(original)
    os.utime(source, (tick, tick))
    script = ("import sys; sys.path.insert(0, " + repr(str(tmp_path)) + "); "
              + "import " + entry + " as entry; "
              + "assert entry.shared.MODELS['codex'] == 'gpt-6-astra'")
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
