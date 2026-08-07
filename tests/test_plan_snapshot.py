from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from paranoia_local import plan_snapshot as ps
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


def test_cleanup_timeout_is_normalized_as_ambiguous_cleanup_failure(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    snap = PlanRepositorySnapshot.create(repo, run_id="cleanup-timeout")
    original = ps._delete_owned_ref

    def timeout(*_args, **_kwargs) -> None:
        raise SnapshotUnavailable("ref cleanup exceeded hard deadline")

    monkeypatch.setattr(ps, "_delete_owned_ref", timeout)
    with pytest.raises(ps.SnapshotCleanupError, match="could not delete temporary snapshot refs"):
        snap.close()
    assert not snap._closed
    monkeypatch.setattr(ps, "_delete_owned_ref", original)
    snap.close()


def test_cleanup_verification_nonzero_is_not_mistaken_for_an_absent_ref(
    repo: Path,
) -> None:
    snap = PlanRepositorySnapshot.create(repo, run_id="cleanup-verify-failure")
    ref_path = repo / ".git" / snap.wrapper_ref
    original = ref_path.read_bytes()
    ref_path.write_text("0" * 40 + "\n")
    with pytest.raises(ps.SnapshotCleanupError, match="changed owner"):
        snap.close()
    assert not snap._closed
    ref_path.write_bytes(original)
    snap.close()


def test_wait_timeout_kills_and_reaps_a_child_that_ignores_terminate() -> None:
    class DefiantProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.wait_timeouts: list[float | None] = []

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout=None):
            self.wait_timeouts.append(timeout)
            if not self.killed:
                raise subprocess.TimeoutExpired("git", timeout)
            return -9

    proc = DefiantProcess()
    with pytest.raises(SnapshotUnavailable, match="exceeded hard deadline"):
        ps._wait_and_reap(
            proc, deadline=time.monotonic() + 0.01, terminate=True,
            context="test child",
        )
    assert proc.terminated and proc.killed
    assert all(timeout is not None for timeout in proc.wait_timeouts)


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


def test_repository_config_includes_are_not_followed(repo: Path, tmp_path: Path) -> None:
    external = tmp_path / "external-git-config"
    external.write_text("[this is deliberately malformed")
    subprocess.run(
        ["git", "config", "--add", "include.path", str(external)],
        cwd=repo, check=True,
    )
    with PlanRepositorySnapshot.create(repo, run_id="ignored-config-include") as snapshot:
        assert snapshot.list_tree()


def test_config_worktree_is_not_read_even_when_repository_enables_it(
    repo: Path, tmp_path: Path,
) -> None:
    external = tmp_path / "external-worktree-config"
    external.write_text("[this is deliberately malformed")
    subprocess.run(
        ["git", "config", "extensions.worktreeConfig", "true"], cwd=repo, check=True,
    )
    (repo / ".git" / "config.worktree").symlink_to(external)
    with PlanRepositorySnapshot.create(repo, run_id="ignored-worktree-config") as snapshot:
        assert snapshot.list_tree()


def test_symlinked_repository_config_fails_before_git_runs(
    repo: Path, tmp_path: Path,
) -> None:
    config = repo / ".git" / "config"
    external = tmp_path / "external-config"
    external.write_text(config.read_text())
    config.unlink()
    config.symlink_to(external)
    with pytest.raises(SnapshotUnavailable, match="small regular file"):
        PlanRepositorySnapshot.create(repo, run_id="symlinked-config")


def test_repository_loose_ref_symlink_is_skipped_without_touching_its_target(
    repo: Path, tmp_path: Path,
) -> None:
    external = tmp_path / "external-refs"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_text("unchanged")
    target = external / "external-ref"
    target.write_text(subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout)
    (repo / ".git" / "refs" / "heads" / "external").symlink_to(target)
    with PlanRepositorySnapshot.create(repo, run_id="symlink-loose-ref") as snapshot:
        assert "git-ref:refs/heads/external" in snapshot.unavailable_paths
    assert sentinel.read_text() == "unchanged"
    assert sorted(path.name for path in external.iterdir()) == ["external-ref", "sentinel"]


def test_repository_owned_ref_ancestor_symlink_fails_closed(
    repo: Path, tmp_path: Path,
) -> None:
    external = tmp_path / "external-owned-refs"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_text("unchanged")
    (repo / ".git" / "refs" / "paranoia").symlink_to(
        external, target_is_directory=True,
    )
    with pytest.raises(SnapshotUnavailable, match="ref directory is unsafe"):
        PlanRepositorySnapshot.create(repo, run_id="symlink-owned-ancestor")
    assert sentinel.read_text() == "unchanged"
    assert [path.name for path in external.iterdir()] == ["sentinel"]


def test_cleanup_does_not_follow_a_replaced_pin_directory(
    repo: Path, tmp_path: Path,
) -> None:
    snap = PlanRepositorySnapshot.create(repo, run_id="cleanup-ref-ancestor")
    token_dir = repo / ".git" / snap.wrapper_ref.rsplit("/", 1)[0]
    saved = token_dir.with_name(token_dir.name + "-saved")
    token_dir.rename(saved)
    external = tmp_path / "external-cleanup"
    external.mkdir()
    sentinel = external / "wrapper"
    sentinel.write_text(snap.commit_id + "\n")
    token_dir.symlink_to(external, target_is_directory=True)
    with pytest.raises(ps.SnapshotCleanupError, match="ref directory is unsafe"):
        snap.close()
    assert sentinel.read_text() == snap.commit_id + "\n"
    token_dir.unlink()
    saved.rename(token_dir)
    snap.close()


def test_failed_ref_write_rolls_back_the_just_created_inode(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ps.os.write

    def fail_ref_write(fd: int, data: bytes) -> int:
        if len(data) in {41, 65} and data.endswith(b"\n"):
            raise OSError("injected ref write failure")
        return original(fd, data)

    monkeypatch.setattr(ps.os, "write", fail_ref_write)
    with pytest.raises(SnapshotUnavailable, match="could not publish temporary ref"):
        PlanRepositorySnapshot.create(repo, run_id="failed-ref-write")
    namespace = repo / ".git" / "refs" / "paranoia"
    assert not namespace.exists() or not any(
        path.is_file() or path.is_symlink() for path in namespace.rglob("*")
    )


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


@pytest.mark.parametrize("metadata_name", [".git", "commondir", "gitdir"])
def test_supplied_git_metadata_fifos_are_rejected_without_blocking(
    tmp_path: Path, metadata_name: str,
) -> None:
    fake = tmp_path / "fake-repo"
    fake.mkdir()
    if metadata_name == ".git":
        os.mkfifo(fake / ".git")
    else:
        common = tmp_path / "common"
        git_dir = common / "worktrees" / "fake"
        git_dir.mkdir(parents=True)
        (fake / ".git").write_text(f"gitdir: {git_dir}\n")
        if metadata_name == "commondir":
            os.mkfifo(git_dir / "commondir")
        else:
            (git_dir / "commondir").write_text("../..\n")
            os.mkfifo(git_dir / "gitdir")
    started = time.monotonic()
    with pytest.raises(SnapshotUnavailable, match="regular file|metadata"):
        ps._approved_common_dir(fake)
    assert time.monotonic() - started < 1.0


def test_symlinked_object_store_root_is_rejected(repo: Path, tmp_path: Path) -> None:
    objects = repo / ".git" / "objects"
    external = tmp_path / "external-objects"
    objects.rename(external)
    objects.symlink_to(external, target_is_directory=True)
    with pytest.raises(SnapshotUnavailable, match="object-store root"):
        PlanRepositorySnapshot.create(repo, run_id="symlinked-objects")


def test_irrelevant_object_store_symlink_does_not_invalidate_snapshot(
    repo: Path, tmp_path: Path,
) -> None:
    inert_target = tmp_path / "inert"
    inert_target.mkdir()
    (repo / ".git" / "objects" / "not-a-git-namespace").symlink_to(
        inert_target, target_is_directory=True,
    )
    with PlanRepositorySnapshot.create(repo, run_id="irrelevant-object-symlink") as snap:
        assert snap.read_blob("app.py").startswith(b'"""App module')


def test_nested_inert_info_symlink_does_not_invalidate_snapshot(
    repo: Path, tmp_path: Path,
) -> None:
    inert = repo / ".git" / "objects" / "info" / "paranoia-inert"
    inert.mkdir()
    (inert / "link").symlink_to(tmp_path, target_is_directory=True)
    with PlanRepositorySnapshot.create(repo, run_id="inert-info-symlink") as snap:
        assert snap.read_blob("app.py").startswith(b'"""App module')


def test_packed_object_names_remain_accepted(repo: Path) -> None:
    subprocess.run(["git", "gc", "--prune=now"], cwd=repo, check=True)
    with PlanRepositorySnapshot.create(repo, run_id="packed-objects") as snap:
        assert snap.read_blob("app.py").startswith(b'"""App module')


def test_symlink_in_resolvable_object_namespace_is_rejected(
    repo: Path, tmp_path: Path,
) -> None:
    pack = repo / ".git" / "objects" / "pack"
    if pack.exists():
        pack.rmdir()
    pack.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SnapshotUnavailable, match="object-store path"):
        PlanRepositorySnapshot.create(repo, run_id="pack-symlink")


def test_snapshot_commit_never_invokes_repository_gpg_program(
    repo: Path, tmp_path: Path,
) -> None:
    marker = tmp_path / "gpg-ran"
    program = tmp_path / "hostile-gpg"
    program.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    program.chmod(0o755)
    subprocess.run(["git", "config", "commit.gpgSign", "true"], cwd=repo, check=True)
    subprocess.run(["git", "config", "gpg.program", str(program)], cwd=repo, check=True)
    with PlanRepositorySnapshot.create(repo, run_id="unsigned-snapshot"):
        pass
    assert not marker.exists()


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


def test_untracked_special_files_are_disclosed_and_skipped(repo: Path) -> None:
    fifo = repo / "events.pipe"
    os.mkfifo(fifo)
    with PlanRepositorySnapshot.create(repo, run_id="special-file") as snap:
        assert "events.pipe" in snap.unavailable_paths
        assert snap.read_blob("app.py").startswith(b'"""App module')
        with pytest.raises(SnapshotUnavailable, match="not present"):
            snap.read_blob("events.pipe")


def test_special_file_scan_prunes_ignored_regular_directories(repo: Path) -> None:
    (repo / ".gitignore").write_text("ignored/\n")
    ignored = repo / "ignored"
    ignored.mkdir()
    for index in range(10):
        (ignored / f"{index}.txt").write_text("x")
    assert ps._find_special_paths(
        repo, ignored_paths=("ignored/",), max_entries=3
    ) == ()


def test_git_tree_output_is_bounded_while_streaming(repo: Path) -> None:
    with pytest.raises(SnapshotUnavailable, match="output exceeds byte cap"):
        ps._run_bounded(
            repo, ["ls-tree", "-r", "-z", "--name-only", "HEAD"],
            max_bytes=2, stop_after_nuls=200,
        )


def test_snapshot_path_enumerations_reject_the_first_excess_record(repo: Path) -> None:
    for args in (
        ["ls-files", "-s", "-z"],
        ["ls-files", "-z", "--cached", "--others", "--exclude-standard"],
    ):
        with pytest.raises(SnapshotUnavailable, match="record cap"):
            ps._run_bounded_records(repo, args, max_records=1)


def test_snapshot_ignored_and_ref_enumerations_are_record_bounded(repo: Path) -> None:
    (repo / ".gitignore").write_text("ignored-*.txt\n")
    (repo / "ignored-one.txt").write_text("x")
    (repo / "ignored-two.txt").write_text("x")
    with pytest.raises(SnapshotUnavailable, match="record cap"):
        ps._run_bounded_records(
            repo,
            ["ls-files", "--others", "-i", "--exclude-standard", "--directory", "-z"],
            max_records=1,
        )
    subprocess.run(["git", "branch", "second"], cwd=repo, check=True)
    with pytest.raises(SnapshotUnavailable, match="record cap"):
        ps._run_bounded_records(
            repo,
            ["for-each-ref", "--format=%(refname)%00%(objectname)%00", "refs/"],
            max_records=1, terminators_per_record=2,
        )


def test_bounded_git_output_debits_only_bytes_actually_read(repo: Path) -> None:
    debits: list[int] = []
    output = ps._run_bounded(
        repo, ["ls-tree", "-r", "-z", "--name-only", "HEAD"],
        max_bytes=1 << 20, stop_after_nuls=200, debit_bytes=debits.append,
    )
    assert sum(debits) == len(output)
    assert sum(debits) < 65536


def test_bounded_git_output_never_reads_past_shared_budget(repo: Path) -> None:
    debits: list[int] = []
    with pytest.raises(SnapshotUnavailable, match="shared byte budget"):
        ps._run_bounded(
            repo, ["ls-tree", "-r", "-z", "--name-only", "HEAD"],
            max_bytes=1 << 20, stop_after_nuls=200, debit_bytes=debits.append,
            remaining_bytes=lambda: 3 - sum(debits),
        )
    assert sum(debits) == 3


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


def test_missing_promisor_objects_never_trigger_lazy_fetch(repo: Path, tmp_path: Path) -> None:
    marker = tmp_path / "lazy-fetch-ran"
    upload_pack = tmp_path / "hostile-upload-pack"
    upload_pack.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    upload_pack.chmod(0o755)
    subprocess.run(["git", "config", "core.repositoryFormatVersion", "1"], cwd=repo, check=True)
    subprocess.run(["git", "config", "extensions.partialClone", "origin"], cwd=repo, check=True)
    subprocess.run(["git", "config", "remote.origin.promisor", "true"], cwd=repo, check=True)
    subprocess.run(["git", "config", "remote.origin.url", str(repo)], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "remote.origin.uploadpack", str(upload_pack)], cwd=repo, check=True
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    object_path = repo / ".git" / "objects" / head[:2] / head[2:]
    assert object_path.exists(), "fixture commit should be a loose object"
    object_path.unlink()
    with pytest.raises(SnapshotUnavailable):
        PlanRepositorySnapshot.create(repo, run_id="no-lazy-fetch")
    assert not marker.exists()
