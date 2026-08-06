from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from paranoia_local.plan_snapshot import PlanRepositorySnapshot, SnapshotUnavailable


def test_snapshot_reads_dirty_and_nonignored_untracked_bytes_from_pinned_commit(repo: Path) -> None:
    (repo / "app.py").write_bytes(b"dirty\xff\n")
    (repo / "new.txt").write_bytes(b"new\n")
    with PlanRepositorySnapshot.create(repo, run_id="round-1") as snap:
        assert snap.read_blob("app.py") == b"dirty\xff\n"
        assert snap.read_blob("new.txt") == b"new\n"
        assert snap.wrapper_ref.startswith("refs/paranoia/plan-snapshots/")
        assert subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", snap.wrapper_ref], cwd=repo
        ).returncode == 0
    assert subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", snap.wrapper_ref], cwd=repo
    ).returncode != 0


def test_ignored_files_are_disclosed_but_not_readable(repo: Path) -> None:
    (repo / ".gitignore").write_text("secret.txt\n")
    (repo / "secret.txt").write_text("token")
    with PlanRepositorySnapshot.create(repo, run_id="round-2") as snap:
        assert "secret.txt" in snap.ignored_paths
        with pytest.raises(SnapshotUnavailable, match="not present"):
            snap.read_blob("secret.txt")


def test_deleting_the_server_ref_fails_closed_instead_of_resolving_live_repo(repo: Path) -> None:
    with PlanRepositorySnapshot.create(repo, run_id="round-3") as snap:
        subprocess.run(["git", "update-ref", "-d", snap.wrapper_ref], cwd=repo, check=True)
        with pytest.raises(SnapshotUnavailable, match="pinned snapshot object"):
            snap.read_blob("app.py")


def test_path_traversal_and_escaping_symlinks_are_rejected(repo: Path) -> None:
    (repo / "escape").symlink_to("../outside")
    with pytest.raises(SnapshotUnavailable, match="escaping symlink"):
        PlanRepositorySnapshot.create(repo, run_id="round-4")
    (repo / "escape").unlink()
    with PlanRepositorySnapshot.create(repo, run_id="round-4b") as snap:
        with pytest.raises(SnapshotUnavailable):
            snap.read_blob("../README.md")


def test_history_reads_only_the_initial_server_pinned_ref_map(repo: Path) -> None:
    with PlanRepositorySnapshot.create(repo, run_id="round-history") as snap:
        rows = snap.history("refs/heads/main", "app.py", limit=5)
        assert rows and rows[0]["commit"]
        with pytest.raises(SnapshotUnavailable, match="initial pinned map"):
            snap.history("refs/heads/future", "app.py")
