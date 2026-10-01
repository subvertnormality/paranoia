"""Git-backed issue-139 admission/suitability, never executing caller filters."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from paranoia_local import engines, handlers, inert_git, patch_proposals as pp
from paranoia_local import proposal_checkout as checkout
from tests.test_patch_proposals_integration import (
    git, install_settled_census, proposal_reply, repository,
)

PAYLOAD = b"dataset\x00\xff\n" * 8192


def pointer(data=PAYLOAD):
    return (f"version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{hashlib.sha256(data).hexdigest()}\nsize {len(data)}\n").encode()


def add_lfs(repo, *, data=PAYLOAD, pinned=None, attribute=True, name="data.bin"):
    if attribute:
        (repo / ".gitattributes").write_text(f"{name} filter=lfs -text\n")
        git(repo, "add", ".gitattributes")
    pinned = pointer(data) if pinned is None else pinned
    oid = inert_git.run(repo, ["hash-object", "-w", "--stdin"], input_bytes=pinned).strip().decode()
    git(repo, "update-index", "--add", "--cacheinfo", f"100644,{oid},{name}")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "pinned LFS fixture")
    (repo / name).write_bytes(data)
    return pinned


@pytest.mark.parametrize("shape", ["expanded", "pointer"])
def test_verified_lfs_and_raw_pointer_are_clean(tmp_path, shape):
    repo = repository(tmp_path)
    pinned = add_lfs(repo)
    if shape == "pointer":
        (repo / "data.bin").write_bytes(pinned)
    assert handlers._branch_proposal_admission_issue(repo, git(repo, "rev-parse", "HEAD")) is None


def test_real_git_lfs_clean_status_matches_admission(tmp_path, monkeypatch):
    lfs = shutil.which("git-lfs") or "/home/andy/.local/bin/git-lfs"
    if not Path(lfs).exists():
        pytest.skip("native Git LFS unavailable")
    monkeypatch.setenv("PATH", str(Path(lfs).parent) + os.pathsep + os.environ["PATH"])
    repo = repository(tmp_path)
    git(repo, "lfs", "install", "--local", "--skip-smudge")
    (repo / ".gitattributes").write_text("data.bin filter=lfs diff=lfs merge=lfs -text\n")
    (repo / "data.bin").write_bytes(PAYLOAD)
    git(repo, "add", ".")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "native LFS")
    assert git(repo, "show", "HEAD:data.bin").encode() + b"\n" == pointer()
    assert git(repo, "status", "--porcelain") == ""
    assert handlers._branch_proposal_admission_issue(repo, git(repo, "rev-parse", "HEAD")) is None


@pytest.mark.parametrize("change", ["same-size", "shorter", "longer", "index", "untracked", "mode", "missing-attribute"])
def test_dirty_lfs_and_other_dirty_state_still_block(tmp_path, change):
    repo = repository(tmp_path)
    add_lfs(repo, attribute=change != "missing-attribute")
    data = repo / "data.bin"
    if change == "same-size": data.write_bytes(b"X" + PAYLOAD[1:])
    elif change == "shorter": data.write_bytes(PAYLOAD[:-1])
    elif change == "longer": data.write_bytes(PAYLOAD + b"X")
    elif change == "index":
        (repo / "app.py").write_text("staged edit\n")
        git(repo, "add", "app.py")
    elif change == "untracked": (repo / "extra").write_text("caller data\n")
    elif change == "mode":
        git(repo, "config", "core.fileMode", "true")
        data.chmod(0o755)
    assert handlers._branch_proposal_admission_issue(repo, git(repo, "rev-parse", "HEAD")) is not None


@pytest.mark.parametrize("mutation", [
    lambda p: p.replace(b"/v1", b"/v2"),
    lambda p: p.replace(b"sha256:", b"sha1:"),
    lambda p: p.replace(b"oid ", b"oid  "),
    lambda p: p.replace(b"size ", b"size 0"),
    lambda p: p.replace(b"\n", b"\r\n"),
    lambda p: p[:-1],
    lambda p: p + b"unknown value\n",
    lambda p: p.replace(b"oid ", b"ext-0-test sha256:" + b"0" * 64 + b"\noid "),
    lambda p: b"x" * checkout.LFS_POINTER_LIMIT,
])
def test_unsupported_pointer_never_grants_expanded_identity(tmp_path, mutation):
    repo = repository(tmp_path)
    add_lfs(repo, pinned=mutation(pointer()))
    assert handlers._branch_proposal_admission_issue(repo, git(repo, "rev-parse", "HEAD")) is not None


def test_lfs_hashing_uses_bounded_reads(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    data = b"binary\x00" * (checkout.READ_CHUNK_BYTES // 2)
    add_lfs(repo, data=data)
    original = Path.open
    sizes = []
    class Stream:
        def __init__(self, wrapped): self.wrapped = wrapped
        def __enter__(self): return self
        def __exit__(self, *args): self.wrapped.close()
        def read(self, size):
            sizes.append(size)
            assert 0 < size <= checkout.READ_CHUNK_BYTES
            return self.wrapped.read(size)
    def guarded(path, *args, **kwargs):
        stream = original(path, *args, **kwargs)
        return Stream(stream) if path == repo / "data.bin" else stream
    monkeypatch.setattr(Path, "open", guarded)
    assert handlers._branch_proposal_admission_issue(repo, git(repo, "rev-parse", "HEAD")) is None
    assert len(sizes) > 2


def test_initialized_submodule_lfs_is_checked_recursively(tmp_path):
    repo = repository(tmp_path)
    child = repo / "child"
    child.mkdir()
    git(child, "init", "-q")
    git(child, "config", "user.name", "fixture")
    git(child, "config", "user.email", "fixture@localhost")
    add_lfs(child)
    oid = git(child, "rev-parse", "HEAD")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{oid},child")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "child")
    head = git(repo, "rev-parse", "HEAD")
    assert handlers._branch_proposal_admission_issue(repo, head) is None
    (child / "data.bin").write_bytes(b"X" + PAYLOAD[1:])
    assert "submodule" in handlers._branch_proposal_admission_issue(repo, head)


def test_absent_sparse_lfs_is_clean(tmp_path):
    repo = repository(tmp_path)
    add_lfs(repo)
    git(repo, "update-index", "--skip-worktree", "data.bin")
    (repo / "data.bin").unlink()
    assert handlers._branch_proposal_admission_issue(repo, git(repo, "rev-parse", "HEAD")) is None


@pytest.mark.parametrize("phase", ["clean", "dirty", "changed-during-call", "admission-failure", "suitability-failure"])
def test_public_branch_lfs_phases_preserve_original_review(tmp_path, monkeypatch, phase):
    repo = repository(tmp_path)
    add_lfs(repo)
    monkeypatch.setenv("PARANOIA_STATE_ROOT", str(tmp_path / "state"))
    trailer = install_settled_census(monkeypatch)
    sentinel = tmp_path / "filter-ran"
    command = f"sh -c 'echo ran >> {sentinel}; cat'"
    staged = handlers._staged_structural_review
    def configure_after_review(*args, **kwargs):
        result = staged(*args, **kwargs)
        for name in ("clean", "process"):
            git(repo, "config", f"filter.lfs.{name}", command)
        # Scope the sentinel to the supplemental admission/return path, after
        # ordinary review preparation (as in the existing filter-free test).
        (repo / "data.bin").touch()
        if phase == "dirty": (repo / "data.bin").write_bytes(b"X" + PAYLOAD[1:])
        return result
    monkeypatch.setattr(handlers, "_staged_structural_review", configure_after_review)
    real_run = inert_git.run
    fail = phase == "admission-failure"
    def failing_run(repo_arg, args, **kwargs):
        if fail and args[0] == "check-attr": raise RuntimeError("attribute read failed")
        return real_run(repo_arg, args, **kwargs)
    monkeypatch.setattr(inert_git, "run", failing_run)
    calls = []
    def resume(self, *args, **kwargs):
        nonlocal fail
        calls.append(args)
        if phase == "changed-during-call": (repo / "data.bin").write_bytes(b"X" + PAYLOAD[1:])
        if phase == "suitability-failure": fail = True
        text = proposal_reply("branch")
        return engines.Review(text, "proposal-session", text)
    monkeypatch.setattr(engines.CodexEngine, "resume_proposal", resume)
    output = handlers.critique_branch({
        "repo_path": str(repo), "base_ref": "main", "head_ref": "feature",
        "round": 1, "lineage": "lfs-" + phase, "stakes": "local",
        "web_search": False, "propose_patch": True,
    }, engine=engines.CodexEngine(), log_dir=tmp_path / "logs")
    assert output.endswith(trailer)
    assert not sentinel.exists()
    if phase in ("dirty", "admission-failure"):
        assert not calls and "PATCH-PROPOSAL: UNAVAILABLE" in output
    else:
        assert len(calls) == 1 and "PATCH-PROPOSAL: PROPOSED" in output
        status = "CURRENT" if phase == "clean" else "STALE"
        assert "APPLICATION-SUITABILITY: " + status in output
        audit = json.loads(next((tmp_path / "logs").glob("*patch_proposal*.json")).read_text())
        assert audit["application_suitability"] == status


def test_smudged_bytes_never_become_patch_preimage(tmp_path):
    repo = repository(tmp_path)
    pinned = add_lfs(repo)
    head = git(repo, "rev-parse", "HEAD")
    entries, reader = handlers._repository_proposal_sources(repo, head, repo)
    entry = next(e for e in entries if e.path == "data.bin")
    assert reader(entry).pinned == pinned != PAYLOAD
    result = SimpleNamespace(files=(pp.ProposedFile("data.bin", "100644", pinned, b"new\n", entry.oid),))
    assert handlers._branch_proposal_suitability(repo, head, result) == "STALE"
    (repo / "data.bin").write_bytes(pinned)
    assert handlers._branch_proposal_suitability(repo, head, result) == "CURRENT"
