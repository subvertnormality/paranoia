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
