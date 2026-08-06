from __future__ import annotations

import os
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


def test_path_traversal_and_symlink_reads_are_rejected_without_rejecting_snapshot(repo: Path) -> None:
    (repo / "escape").symlink_to("../outside")
    with PlanRepositorySnapshot.create(repo, run_id="round-4") as snap:
        with pytest.raises(SnapshotUnavailable, match="symlink paths"):
            snap.read_blob("escape")
        with pytest.raises(SnapshotUnavailable):
            snap.read_blob("../README.md")


def test_snapshot_hashing_does_not_execute_repository_clean_filters(
    repo: Path, tmp_path: Path
) -> None:
    marker = tmp_path / "filter-ran"
    subprocess.run(
        ["git", "config", "filter.hostile.clean", f"touch {marker} && cat"],
        cwd=repo, check=True,
    )
    (repo / ".gitattributes").write_text("*.py filter=hostile\n")
    (repo / "app.py").write_text("dirty without filter\n")
    with PlanRepositorySnapshot.create(repo, run_id="hostile-config") as snap:
        assert snap.read_blob("app.py") == b"dirty without filter\n"
    assert not marker.exists()


def test_history_reads_only_the_initial_server_pinned_ref_map(repo: Path) -> None:
    with PlanRepositorySnapshot.create(repo, run_id="round-history") as snap:
        rows = snap.history("refs/heads/main", "app.py", limit=5)
        assert rows and rows[0]["commit"]
        with pytest.raises(SnapshotUnavailable, match="initial pinned map"):
            snap.history("refs/heads/future", "app.py")


def test_external_object_alternates_are_rejected(repo: Path, tmp_path: Path) -> None:
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    common_path = Path(common) if Path(common).is_absolute() else repo / common
    info = common_path / "objects" / "info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "alternates").write_text(str(tmp_path / "external-objects") + "\n")
    with pytest.raises(SnapshotUnavailable, match="object alternates"):
        PlanRepositorySnapshot.create(repo, run_id="alternate")


def test_inherited_git_object_environment_is_cleared(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", "/definitely/not/approved")
    monkeypatch.setenv("GIT_REPLACE_REF_BASE", "refs/hostile-replacements/")
    with PlanRepositorySnapshot.create(repo, run_id="clean-object-env") as snap:
        assert snap.read_blob("app.py").startswith(b'"""App module')


def test_native_linked_worktree_common_store_is_explicitly_approved(
    repo: Path, tmp_path: Path
) -> None:
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(linked), "HEAD"],
        cwd=repo, check=True, capture_output=True,
    )
    with PlanRepositorySnapshot.create(linked, run_id="linked-worktree") as snap:
        assert snap.read_blob("app.py").startswith(b'"""App module')


def test_replacement_objects_are_disabled_and_not_exposed_as_history_refs(repo: Path) -> None:
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    replacement = subprocess.run(
        ["git", "commit-tree", tree, "-m", "FORGED REPLACEMENT"], cwd=repo, check=True,
        capture_output=True, text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    ).stdout.strip()
    subprocess.run(["git", "replace", "HEAD", replacement], cwd=repo, check=True)
    with PlanRepositorySnapshot.create(repo, run_id="replace-disabled") as snap:
        assert not any(name.startswith("refs/replace/") for name in snap.history_refs)
        subjects = [row["subject"] for row in snap.history("refs/heads/main", "app.py")]
        assert "FORGED REPLACEMENT" not in subjects
