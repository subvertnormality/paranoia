from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from paranoia_local import plan_snapshot as ps
from paranoia_local.plan_snapshot import PlanRepositorySnapshot, SnapshotUnavailable


def test_snapshot_pins_dirty_and_nonignored_untracked_bytes(repo: Path) -> None:
    (repo / "app.py").write_bytes(b"dirty\xff\n")
    (repo / "new.txt").write_bytes(b"new\n")
    with PlanRepositorySnapshot.create(repo, run_id="dirty") as snapshot:
        original_commit = snapshot.commit_id
        assert snapshot.read_blob("app.py") == b"dirty\xff\n"
        assert snapshot.read_blob("new.txt") == b"new\n"
        (repo / "app.py").write_text("later edit\n")
        (repo / "new.txt").unlink()
        assert snapshot.commit_id == original_commit
        assert snapshot.read_blob("app.py") == b"dirty\xff\n"
        assert snapshot.read_blob("new.txt") == b"new\n"


def test_snapshot_is_ephemeral_and_does_not_publish_repository_refs(repo: Path) -> None:
    before = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)%00%(objectname)"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    snapshot = PlanRepositorySnapshot.create(repo, run_id="ephemeral")
    assert snapshot.wrapper_ref.startswith("ephemeral:")
    snapshot.close()
    after = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)%00%(objectname)"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    assert after == before


def test_closed_snapshot_fails_explicitly(repo: Path) -> None:
    snapshot = PlanRepositorySnapshot.create(repo, run_id="closed")
    snapshot.close()
    with pytest.raises(SnapshotUnavailable, match="closed"):
        snapshot.read_blob("app.py")


def test_ignored_and_special_paths_are_disclosed_but_not_readable(repo: Path) -> None:
    (repo / ".gitignore").write_text("secret.txt\n")
    (repo / "secret.txt").write_text("token")
    os.mkfifo(repo / "events.pipe")
    with PlanRepositorySnapshot.create(repo, run_id="unavailable") as snapshot:
        assert "secret.txt" in snapshot.ignored_paths
        assert "events.pipe" in snapshot.unavailable_paths
        _paths, complete = snapshot.list_tree_scoped(limit=200)
        assert complete is False
        matches, scope = snapshot.search_literal_scoped("token", paths=None, limit=10)
        assert matches == [] and scope["complete"] is False
        with pytest.raises(SnapshotUnavailable, match="not present"):
            snapshot.read_blob("secret.txt")
        with pytest.raises(SnapshotUnavailable, match="not present"):
            snapshot.read_blob("events.pipe")


def test_path_traversal_symlinks_and_gitlinks_are_not_blob_evidence(
    repo: Path, tmp_path: Path,
) -> None:
    (repo / "escape").symlink_to("../outside")
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(linked), "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    with PlanRepositorySnapshot.create(repo, run_id="types") as snapshot:
        with pytest.raises(SnapshotUnavailable, match="symlink"):
            snapshot.read_blob("escape")
        with pytest.raises(SnapshotUnavailable, match="escapes"):
            snapshot.read_blob("../outside")


def test_gitlink_makes_containing_negative_scope_incomplete(repo: Path) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    (repo / "vendor" / "module").mkdir(parents=True)
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"160000,{head},vendor/module"],
        cwd=repo, check=True,
    )
    with PlanRepositorySnapshot.create(repo, run_id="gitlink-scope") as snapshot:
        paths, complete = snapshot.list_tree_scoped("vendor/module", limit=20)
        assert paths == ["vendor/module"]
        assert "vendor/module" in snapshot.unavailable_paths
        assert complete is False
        descendants, descendants_complete = snapshot.list_tree_scoped(
            "vendor/module/docs", limit=20,
        )
        assert descendants == [] and descendants_complete is False
        matches, scope = snapshot.search_literal_scoped(
            "counterexample", paths=None, limit=10,
        )
        assert matches == [] and scope["complete"] is False


def test_snapshot_hashing_does_not_execute_repository_filters_or_signing(
    repo: Path, tmp_path: Path,
) -> None:
    marker = tmp_path / "command-ran"
    command = tmp_path / "hostile-command"
    command.write_text(f"#!/bin/sh\ntouch {marker}\ncat\n")
    command.chmod(0o755)
    subprocess.run(
        ["git", "config", "filter.hostile.clean", str(command)], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "commit.gpgSign", "true"], cwd=repo, check=True)
    subprocess.run(["git", "config", "gpg.program", str(command)], cwd=repo, check=True)
    (repo / ".gitattributes").write_text("*.py filter=hostile\n")
    (repo / "app.py").write_text("unfiltered bytes\n")
    with PlanRepositorySnapshot.create(repo, run_id="no-exec") as snapshot:
        assert snapshot.read_blob("app.py") == b"unfiltered bytes\n"
    assert not marker.exists()


def test_repository_config_includes_and_worktree_config_are_not_loaded(
    repo: Path, tmp_path: Path,
) -> None:
    malformed = tmp_path / "malformed-config"
    malformed.write_text("[deliberately malformed")
    subprocess.run(
        ["git", "config", "extensions.worktreeConfig", "true"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "--add", "include.path", str(malformed)],
        cwd=repo,
        check=True,
    )
    (repo / ".git" / "config.worktree").symlink_to(malformed)
    with PlanRepositorySnapshot.create(repo, run_id="config") as snapshot:
        assert "app.py" in snapshot.list_tree()


def test_object_alternates_are_rejected_instead_of_reading_external_objects(
    repo: Path, tmp_path: Path,
) -> None:
    info = repo / ".git" / "objects" / "info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "alternates").write_text(str(tmp_path / "external-objects") + "\n")
    with pytest.raises(SnapshotUnavailable, match="alternates are unsupported"):
        PlanRepositorySnapshot.create(repo, run_id="alternate")


def test_inherited_git_environment_and_replacement_refs_do_not_change_evidence(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    replacement = subprocess.run(
        ["git", "commit-tree", tree, "-m", "FORGED REPLACEMENT"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    ).stdout.strip()
    subprocess.run(["git", "replace", "HEAD", replacement], cwd=repo, check=True)
    monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", "/not/approved")
    monkeypatch.setenv("GIT_REPLACE_REF_BASE", "refs/replace/")
    with PlanRepositorySnapshot.create(repo, run_id="environment") as snapshot:
        assert not any(name.startswith("refs/replace/") for name in snapshot.history_refs)
        subjects = [
            row["subject"] for row in snapshot.history("refs/heads/main", "app.py")
        ]
        assert "FORGED REPLACEMENT" not in subjects


def test_history_uses_the_initial_ref_map(repo: Path) -> None:
    with PlanRepositorySnapshot.create(repo, run_id="history") as snapshot:
        initial = snapshot.history_oid("refs/heads/main")
        subprocess.run(["git", "branch", "future", "HEAD"], cwd=repo, check=True)
        assert snapshot.history_oid("refs/heads/main") == initial
        with pytest.raises(SnapshotUnavailable, match="initial snapshot map"):
            snapshot.history_oid("refs/heads/future")


def test_native_linked_worktree_is_supported(repo: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked-worktree"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(linked), "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    with PlanRepositorySnapshot.create(linked, run_id="linked") as snapshot:
        assert snapshot.read_blob("app.py").startswith(b'"""App module')


def test_tree_blob_search_and_history_scopes_are_accurate(repo: Path) -> None:
    (repo / "app.py").write_text("alpha\nbeta alpha\n")
    with PlanRepositorySnapshot.create(repo, run_id="queries") as snapshot:
        paths, tree_complete = snapshot.list_tree_scoped(limit=200)
        assert tree_complete and "app.py" in paths
        oid, size = snapshot.blob_identity("app.py")
        assert len(oid) in {40, 64} and size == len(b"alpha\nbeta alpha\n")
        assert snapshot.read_blob("app.py", offset=6, max_bytes=4) == b"beta"
        matches, scope = snapshot.search_literal_scoped(
            "alpha", paths=["app.py"], limit=10
        )
        assert [row["line"] for row in matches] == [1, 2]
        assert scope["complete"] is True
        history, history_complete = snapshot.history_scoped(
            "refs/heads/main", "app.py", limit=5
        )
        assert history_complete and history


def test_snapshot_file_and_total_byte_caps_fail_toward_unavailable(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (repo / "large.bin").write_bytes(b"x" * 32)
    monkeypatch.setattr(ps, "MAX_FILE_BYTES", 16)
    with PlanRepositorySnapshot.create(repo, run_id="bounded") as snapshot:
        assert "large.bin" in snapshot.unavailable_paths
        paths, complete = snapshot.list_tree_scoped(limit=200)
        assert "large.bin" not in paths and complete is False
        matches, scope = snapshot.search_literal_scoped("absent", paths=None, limit=10)
        assert matches == [] and scope["complete"] is False
        with pytest.raises(SnapshotUnavailable, match="not present"):
            snapshot.read_blob("large.bin")


def test_skip_worktree_file_is_preserved_from_the_index(
    repo: Path,
) -> None:
    hidden = repo / "sparse-only.txt"
    hidden.write_text("indexed sparse content\n")
    subprocess.run(["git", "add", "sparse-only.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add sparse file"], cwd=repo, check=True)
    subprocess.run(
        ["git", "update-index", "--skip-worktree", "sparse-only.txt"],
        cwd=repo, check=True,
    )
    hidden.unlink()

    with PlanRepositorySnapshot.create(repo, run_id="skip-worktree") as snapshot:
        paths, complete = snapshot.list_tree_scoped(limit=200)
        assert complete is True and "sparse-only.txt" in paths
        assert snapshot.read_blob("sparse-only.txt") == b"indexed sparse content\n"


@pytest.mark.parametrize(
    "mutation", ["create", "delete", "rename", "edit", "index"],
)
def test_repository_wide_manifest_rejects_mutation_during_snapshot(
    repo: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    original = ps._read_regular
    fired = False

    def mutate_after_read(path: Path, *, remaining: int):
        nonlocal fired
        result = original(path, remaining=remaining)
        if fired:
            return result
        fired = True
        target = repo / "app.py"
        if mutation == "create":
            (repo / "created-during-snapshot.txt").write_text("late\n")
        elif mutation == "delete":
            target.unlink()
        elif mutation == "rename":
            target.rename(repo / "renamed-during-snapshot.py")
        elif mutation == "edit":
            target.write_text("changed during snapshot\n")
        else:
            subprocess.run(
                ["git", "update-index", "--chmod=+x", "app.py"],
                cwd=repo, check=True,
            )
        return result

    monkeypatch.setattr(ps, "_read_regular", mutate_after_read)
    with pytest.raises(SnapshotUnavailable, match="changed during snapshot"):
        PlanRepositorySnapshot.create(repo, run_id=f"manifest-{mutation}")


def test_ref_manifest_rejects_multi_ref_update_during_capture(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ps._copy_ref_tree
    fired = False

    def update_after_copy(source: Path, destination: Path) -> None:
        nonlocal fired
        original(source, destination)
        if fired:
            return
        fired = True
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "update-ref", "--stdin"], cwd=repo, check=True,
            input=(
                f"create refs/heads/captured-topic {head}\n"
                f"create refs/tags/captured-tag {head}\n"
            ), text=True,
        )

    monkeypatch.setattr(ps, "_copy_ref_tree", update_after_copy)
    with pytest.raises(SnapshotUnavailable, match="refs changed"):
        PlanRepositorySnapshot.create(repo, run_id="ref-transaction")


def test_bounded_git_output_enforces_local_and_shared_budgets(repo: Path) -> None:
    with pytest.raises(SnapshotUnavailable, match="byte cap"):
        ps._run_bounded(
            repo,
            ["ls-tree", "-r", "-z", "--name-only", "HEAD"],
            max_bytes=2,
            stop_after_nuls=200,
        )
    debits: list[int] = []
    with pytest.raises(SnapshotUnavailable, match="shared byte budget"):
        ps._run_bounded(
            repo,
            ["ls-tree", "-r", "-z", "--name-only", "HEAD"],
            max_bytes=1 << 20,
            stop_after_nuls=200,
            debit_bytes=debits.append,
            remaining_bytes=lambda: 3 - sum(debits),
        )
    assert sum(debits) == 3


def test_record_enumeration_rejects_first_excess_record(repo: Path) -> None:
    with pytest.raises(SnapshotUnavailable, match="record cap"):
        ps._run_bounded_records(
            repo,
            ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            max_records=1,
        )


def test_wait_timeout_kills_and_reaps_child() -> None:
    class DefiantProcess:
        terminated = False
        killed = False

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("git", timeout)
            return -9

    process = DefiantProcess()
    with pytest.raises(SnapshotUnavailable, match="exceeded hard deadline"):
        ps._wait_and_reap(
            process,
            deadline=time.monotonic() + 0.01,
            terminate=True,
            context="test child",
        )
    assert process.terminated and process.killed
