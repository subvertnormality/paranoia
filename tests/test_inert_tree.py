import os
import subprocess
from pathlib import Path

from paranoia_local import inert_tree, orientation
from tests.conftest import commit_all, git


def test_materializer_renders_symlinks_and_executables_inert(repo: Path, tmp_path: Path):
    script = repo / "run.sh"
    script.write_text("#!/bin/sh\ntouch SHOULD_NOT_RUN\n")
    script.chmod(0o755)
    os.symlink("run.sh", repo / "link")
    commit_all(repo, "special entries")
    snapshot = orientation.resolve_head(repo)
    tree = inert_tree.materialize(repo, snapshot, tmp_path / "evidence")
    assert not os.access(tree.repository / "run.sh", os.X_OK)
    assert (tree.repository / "link").is_file()
    assert not (tree.repository / "link").is_symlink()
    assert "INERT SYMLINK" in (tree.repository / "link").read_text()
    assert not (repo / "SHOULD_NOT_RUN").exists()


def test_snapshot_disables_repository_fsmonitor_hook(repo: Path, tmp_path: Path):
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "monitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
    hook.chmod(0o755)
    git(["config", "core.fsmonitor", str(hook)], repo)
    (repo / "app.py").write_text("changed = True\n")
    orientation.snapshot_tree(repo, orientation.resolve_head(repo))
    assert not marker.exists()


def test_provider_cwds_keep_claude_on_the_real_inert_root(repo: Path):
    snapshot = orientation.resolve_head(repo)
    with inert_tree.evidence_workspace(repo, snapshot) as workspace:
        assert workspace.cwd_for("claude") == workspace.tree.root
        assert (workspace.cwd_for("claude") / "repository" / "app.py").is_file()
        assert workspace.cwd_for("codex") == workspace.launch
        assert (workspace.cwd_for("codex") / "repository").is_symlink()


def test_materialize_preserves_snapshot_bytes_manifest_history_and_modes(repo, tmp_path):
    import hashlib
    import json
    from paranoia_local import inert_git
    odd = os.fsdecode(b"odd-\xff\nname.txt")
    bodies = {"binary.dat": b"\0\xff\n", "empty.txt": b"", odd: b"original\n"}
    for name, body in bodies.items():
        (repo / name).write_bytes(body)
    (repo / "run.sh").write_text("#!/bin/sh\nexit 0\n")
    (repo / "run.sh").chmod(0o755)
    os.symlink("run.sh", repo / "link")
    (repo / ".gitattributes").write_text("*.txt filter=hostile\n*.dat diff=hostile\n")
    commit_all(repo, "byte fixtures")
    link_oid = orientation.resolve_head(repo)
    git(["update-index", "--add", "--cacheinfo", f"160000,{link_oid},submodule"], repo)
    git(["-c", "commit.gpgsign=false", "commit", "-qm", "gitlink"], repo)
    snapshot = orientation.resolve_head(repo)
    marker = tmp_path / "helper-executed"
    helper = tmp_path / "helper.sh"
    helper.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    helper.chmod(0o755)
    git(["config", "filter.hostile.smudge", str(helper)], repo)
    git(["config", "diff.hostile.textconv", str(helper)], repo)
    git(["config", "core.fsmonitor", str(helper)], repo)
    (repo / odd).write_bytes(b"ordinary later edit\n")
    with inert_tree.evidence_workspace(repo, snapshot) as workspace:
        tree = workspace.tree
        manifest = json.loads(tree.manifest.read_text())
        assert manifest["snapshot"] == snapshot
        expected = []
        rows = inert_git.run(repo, ["ls-tree", "-rz", "--full-tree", snapshot]).split(b"\0")
        for row in rows:
            if not row:
                continue
            metadata, path = row.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            target = tree.repository / os.fsdecode(path)
            if kind == "commit":
                data = b""
                rendered = f"PARANOIA INERT GITLINK OID\n{oid}\n".encode()
                label = "gitlink"
            else:
                data = inert_git.run(repo, ["cat-file", "blob", oid])
                rendered = b"PARANOIA INERT SYMLINK TARGET\n" + data if mode == "120000" else data
                label = "symlink" if mode == "120000" else "executable" if mode == "100755" else "file"
            assert target.read_bytes() == rendered
            assert target.stat().st_mode & 0o777 == 0o444
            assert not target.is_symlink()
            expected.append({"path": path.decode("utf-8", "backslashreplace"),
                             "mode": mode, "kind": label, "oid": oid, "bytes": len(data)})
        assert manifest["entries"] == expected
        history = inert_git.text(repo, ["log", "--no-patch", "--max-count=100",
                                       "--format=%H%x09%aI%x09%an%x09%s", snapshot])
        assert tree.history.read_bytes() == history.encode("utf-8", "surrogateescape")
        root = tree.root
    assert not root.exists()
    assert not marker.exists()


def test_missing_promised_object_fails_without_fetch_or_filter(repo, tmp_path):
    import pytest
    (repo / "missing.txt").write_text("unique missing object\n")
    commit_all(repo, "promised fixture")
    snapshot = orientation.resolve_head(repo)
    oid = git(["rev-parse", f"{snapshot}:missing.txt"], repo).strip()
    marker = tmp_path / "fetch-executed"
    helper = tmp_path / "fetch.sh"
    helper.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    helper.chmod(0o755)
    git(["config", "remote.origin.url", "ext::" + str(helper)], repo)
    git(["config", "protocol.ext.allow", "always"], repo)
    git(["config", "remote.origin.promisor", "true"], repo)
    git(["config", "extensions.partialClone", "origin"], repo)
    # Deliberately omit one fixture object to exercise the existing fail-closed policy.
    target = repo / ".git" / "objects" / oid[:2] / oid[2:]
    assert target.resolve().is_relative_to(repo.resolve())
    target.unlink()
    with pytest.raises(RuntimeError):
        with inert_tree.evidence_workspace(repo, snapshot):
            pytest.fail("missing object admitted a workspace")
    assert not marker.exists()
