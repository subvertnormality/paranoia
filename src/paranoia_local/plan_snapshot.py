"""Pinned, server-only repository reads for plan claim verification."""

from __future__ import annotations

import hashlib
import os
import re
import select
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

MAX_PINNED_REFS = 1024
MAX_DISCOVERED_REFS = 4096
MAX_REF_TREE_ENTRIES = 8192
MAX_SNAPSHOT_PATHS = 100_000
MAX_DISCOVERY_BYTES = 32 << 20
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_PAGER": "cat",
    "PAGER": "cat",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_GRAFT_FILE": os.devnull,
}
_GIT_CONFIG = [
    "-c", "core.fsmonitor=false",
    "-c", "core.untrackedCache=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.attributesFile=/dev/null",
    "-c", "core.alternateRefsCommand=false",
    "-c", "commit.gpgSign=false",
    "--no-pager",
]
_SNAPSHOT_IDENTITY = {
    "GIT_AUTHOR_NAME": "paranoia",
    "GIT_AUTHOR_EMAIL": "paranoia@localhost",
    "GIT_COMMITTER_NAME": "paranoia",
    "GIT_COMMITTER_EMAIL": "paranoia@localhost",
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00 +0000",
    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00 +0000",
}
GIT_TIMEOUT_SECONDS = 30.0
PROCESS_REAP_SECONDS = 2.0


class SnapshotUnavailable(RuntimeError):
    pass


class SnapshotCleanupError(SnapshotUnavailable):
    """Temporary refs may remain; the journal/latch must be retained for repair."""


def _run(repo: Path, args: list[str], *, input_bytes: bytes | None = None,
         check: bool = True, git_env: dict[str, str] | None = None,
         extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    ambient = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        result = subprocess.run(
            ["git", *_GIT_CONFIG, *args], cwd=repo, input=input_bytes,
            capture_output=True, timeout=GIT_TIMEOUT_SECONDS,
            env={**ambient, **_GIT_ENV, **(git_env or {}), **(extra_env or {})},
        )
    except subprocess.TimeoutExpired as exc:
        raise SnapshotUnavailable(f"git {' '.join(args[:2])} exceeded hard deadline") from exc
    if check and result.returncode:
        raise SnapshotUnavailable(
            f"git {' '.join(args[:2])} failed: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result


def _run_bounded(
    repo: Path, args: list[str], *, max_bytes: int, stop_after_nuls: int,
    git_env: dict[str, str] | None = None,
    debit_bytes: Callable[[int], None] | None = None,
    remaining_bytes: Callable[[], int] | None = None,
) -> bytes:
    """Read bounded Git output and terminate once complete records reach the limit."""
    ambient = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    proc = subprocess.Popen(
        ["git", *_GIT_CONFIG, *args], cwd=repo, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env={**ambient, **_GIT_ENV, **(git_env or {})},
    )
    output = bytearray()
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    try:
        assert proc.stdout is not None
        while output.count(b"\0") < stop_after_nuls:
            remaining = max_bytes - len(output)
            if remaining <= 0:
                raise SnapshotUnavailable("bounded Git output exceeds byte cap")
            budget_remaining = remaining_bytes() if remaining_bytes is not None else remaining + 1
            if budget_remaining <= 0:
                raise SnapshotUnavailable("bounded Git output exceeds shared byte budget")
            read_size = min(65536, remaining + 1, budget_remaining)
            chunk = _read_deadline(proc.stdout, read_size, deadline)
            if not chunk:
                break
            if debit_bytes is not None:
                debit_bytes(len(chunk))
            output.extend(chunk)
            if len(output) > max_bytes:
                raise SnapshotUnavailable("bounded Git output exceeds byte cap")
        stopped_early = output.count(b"\0") >= stop_after_nuls
        returncode = _wait_and_reap(
            proc, deadline=deadline, terminate=stopped_early,
            context="bounded Git command",
        )
        if returncode not in {0, -15}:
            raise SnapshotUnavailable("bounded Git command failed")
        return bytes(output)
    finally:
        _kill_and_reap(proc, context="bounded Git command")


def _run_bounded_records(
    repo: Path, args: list[str], *, max_records: int,
    terminators_per_record: int = 1, max_bytes: int = MAX_DISCOVERY_BYTES,
    git_env: dict[str, str] | None = None,
) -> bytes:
    """Stream a NUL-framed enumeration and reject the first excess record."""
    if max_records < 1 or terminators_per_record < 1:
        raise SnapshotUnavailable("Git enumeration bounds must be positive")
    output = _run_bounded(
        repo, args, max_bytes=max_bytes,
        stop_after_nuls=(max_records + 1) * terminators_per_record,
        git_env=git_env,
    )
    terminators = output.count(b"\0")
    if terminators > max_records * terminators_per_record:
        raise SnapshotUnavailable("Git enumeration exceeds record cap")
    if terminators % terminators_per_record:
        raise SnapshotUnavailable("Git enumeration returned a malformed record")
    return output


def _read_deadline(pipe: object, size: int, deadline: float) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not select.select([pipe], [], [], remaining)[0]:
        raise SnapshotUnavailable("Git streaming read exceeded hard deadline")
    return os.read(pipe.fileno(), size)  # type: ignore[attr-defined]


def _kill_and_reap(proc: subprocess.Popen[bytes], *, context: str) -> None:
    """Bound cleanup even when a child ignores termination or wait is interrupted."""
    if proc.poll() is not None:
        return
    kill_error: OSError | None = None
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    except OSError as exc:
        kill_error = exc
    try:
        proc.wait(timeout=PROCESS_REAP_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise SnapshotUnavailable(f"{context} could not be reaped after kill") from exc
    except OSError as exc:
        raise SnapshotUnavailable(f"{context} could not be reaped: {exc}") from exc
    if kill_error is not None:
        raise SnapshotUnavailable(
            f"{context} could not be killed: {kill_error}"
        ) from kill_error


def _wait_and_reap(
    proc: subprocess.Popen[bytes], *, deadline: float, terminate: bool, context: str,
) -> int:
    """Wait only to the command deadline, then kill and reap under a second hard cap."""
    if terminate and proc.poll() is None:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        except OSError as exc:
            _kill_and_reap(proc, context=context)
            raise SnapshotUnavailable(f"{context} could not be terminated: {exc}") from exc
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _kill_and_reap(proc, context=context)
        raise SnapshotUnavailable(f"{context} exceeded hard deadline")
    try:
        return proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        _kill_and_reap(proc, context=context)
        raise SnapshotUnavailable(f"{context} exceeded hard deadline") from exc
    except OSError as exc:
        _kill_and_reap(proc, context=context)
        raise SnapshotUnavailable(f"{context} wait failed: {exc}") from exc


def _read_small_regular(
    path: Path, *, max_bytes: int = 4096, missing_ok: bool = False,
) -> bytes:
    """Read supplied metadata without following links or ever blocking on a FIFO.

    ``lstat`` bounds the candidate before open; ``O_NOFOLLOW|O_NONBLOCK`` and the
    post-open identity check close replacement races with symlinks and special files.
    """
    try:
        before = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return b""
        raise SnapshotUnavailable(f"repository metadata is missing: {path}") from None
    except OSError as exc:
        raise SnapshotUnavailable(f"repository metadata is unavailable at {path}: {exc}") from exc
    if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        raise SnapshotUnavailable(f"repository metadata must be a small regular file: {path}")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    fd: int | None = None
    try:
        fd = os.open(path, flags)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) \
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) \
                or opened.st_size > max_bytes:
            raise SnapshotUnavailable(f"repository metadata changed while opening: {path}")
        chunks = bytearray()
        while len(chunks) <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        if len(chunks) > max_bytes:
            raise SnapshotUnavailable(f"repository metadata exceeds byte cap: {path}")
        return bytes(chunks)
    except SnapshotUnavailable:
        raise
    except OSError as exc:
        raise SnapshotUnavailable(f"repository metadata is unavailable at {path}: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _open_directory(path: Path) -> int:
    """Open an existing real directory and reject replacement with a link."""
    try:
        before = path.lstat()
        if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
            raise SnapshotUnavailable(f"repository directory is unsafe: {path}")
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        opened = os.fstat(fd)
        if not stat.S_ISDIR(opened.st_mode) \
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            os.close(fd)
            raise SnapshotUnavailable(f"repository directory changed while opening: {path}")
        return fd
    except SnapshotUnavailable:
        raise
    except OSError as exc:
        raise SnapshotUnavailable(f"repository directory is unavailable at {path}: {exc}") from exc


def _open_child_directory(parent_fd: int, name: str, *, create: bool) -> int:
    """Open one fd-relative component without following a supplied link."""
    if not name or name in {".", ".."} or "/" in name or "\0" in name:
        raise SnapshotUnavailable("repository ref directory name is malformed")
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise SnapshotUnavailable(
                f"could not create private ref directory {name!r}: {exc}"
            ) from exc
    except OSError as exc:
        raise SnapshotUnavailable(f"could not inspect ref directory {name!r}: {exc}") from exc
    if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise SnapshotUnavailable(f"repository ref directory is unsafe: {name!r}")
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(fd)
        if not stat.S_ISDIR(opened.st_mode) \
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            os.close(fd)
            raise SnapshotUnavailable(f"repository ref directory changed: {name!r}")
        return fd
    except SnapshotUnavailable:
        raise
    except OSError as exc:
        raise SnapshotUnavailable(f"could not open ref directory {name!r}: {exc}") from exc


def _open_refs_root(common: Path, *, create: bool) -> int:
    common_fd = _open_directory(common)
    try:
        return _open_child_directory(common_fd, "refs", create=create)
    finally:
        os.close(common_fd)


def _read_small_regular_at(
    parent_fd: int, name: str, *, max_bytes: int = 4096,
) -> bytes:
    if not name or name in {".", ".."} or "/" in name or "\0" in name:
        raise SnapshotUnavailable("repository ref filename is malformed")
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise SnapshotUnavailable(f"repository ref is unsafe or oversized: {name!r}")
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) \
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) \
                    or opened.st_size > max_bytes:
                raise SnapshotUnavailable(f"repository ref changed while opening: {name!r}")
            data = bytearray()
            while len(data) <= max_bytes:
                chunk = os.read(fd, min(4096, max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > max_bytes:
                raise SnapshotUnavailable(f"repository ref exceeds byte cap: {name!r}")
            return bytes(data)
        finally:
            os.close(fd)
    except FileNotFoundError:
        raise
    except SnapshotUnavailable:
        raise
    except OSError as exc:
        raise SnapshotUnavailable(f"repository ref is unavailable at {name!r}: {exc}") from exc


def _copy_loose_refs(common: Path, destination: Path) -> None:
    """Materialize supplied loose refs without following any tree component."""
    destination.mkdir(mode=0o700)
    root_fd = _open_refs_root(common, create=False)
    entries = 0
    copied_bytes = 0

    def copy_directory(source_fd: int, target: Path, depth: int) -> None:
        nonlocal entries, copied_bytes
        if depth > 64:
            raise SnapshotUnavailable("repository ref tree exceeds depth cap")
        try:
            names = sorted(os.listdir(source_fd), key=os.fsencode)
        except OSError as exc:
            raise SnapshotUnavailable(f"could not enumerate repository refs: {exc}") from exc
        for name in names:
            entries += 1
            if entries > MAX_REF_TREE_ENTRIES:
                raise SnapshotUnavailable("repository ref tree exceeds entry cap")
            try:
                info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
            except OSError as exc:
                raise SnapshotUnavailable(f"could not inspect repository ref {name!r}: {exc}") from exc
            if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                child_fd = _open_child_directory(source_fd, name, create=False)
                child_target = target / name
                child_target.mkdir(mode=0o700)
                try:
                    copy_directory(child_fd, child_target, depth + 1)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise SnapshotUnavailable(f"repository ref path is unsafe: {name!r}")
            data = _read_small_regular_at(source_fd, name)
            copied_bytes += len(data)
            if copied_bytes > MAX_DISCOVERY_BYTES:
                raise SnapshotUnavailable("repository loose refs exceed byte cap")
            (target / name).write_bytes(data)

    try:
        copy_directory(root_fd, destination, 0)
    finally:
        os.close(root_fd)


def _ref_parts(name: str) -> tuple[str, ...]:
    parts = tuple(name.split("/"))
    if len(parts) < 2 or parts[0] != "refs" or any(
        not part or part in {".", ".."} or "\0" in part for part in parts
    ):
        raise SnapshotUnavailable("temporary ref name is malformed")
    return parts[1:]


def _write_owned_ref(common: Path, name: str, oid: str) -> None:
    parts = _ref_parts(name)
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid):
        raise SnapshotUnavailable("temporary ref object identity is malformed")
    fd = _open_refs_root(common, create=True)
    try:
        for component in parts[:-1]:
            child = _open_child_directory(fd, component, create=True)
            os.close(fd)
            fd = child
        flags = (
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        )
        ref_fd: int | None = None
        created = False
        created_identity: tuple[int, int] | None = None
        try:
            ref_fd = os.open(parts[-1], flags, 0o600, dir_fd=fd)
            created = True
            opened = os.fstat(ref_fd)
            created_identity = (opened.st_dev, opened.st_ino)
            payload = (oid + "\n").encode("ascii")
            written = 0
            while written < len(payload):
                count = os.write(ref_fd, payload[written:])
                if count <= 0:
                    raise OSError("temporary ref write made no progress")
                written += count
            os.fsync(ref_fd)
            closing_fd = ref_fd
            ref_fd = None
            os.close(closing_fd)
            os.fsync(fd)
        except FileExistsError as exc:
            raise SnapshotUnavailable(f"temporary ref already exists: {name}") from exc
        except BaseException as exc:
            if created and created_identity is None:
                raise SnapshotCleanupError(
                    f"temporary ref {name} was created but its identity could not be verified"
                ) from exc
            if created_identity is not None:
                try:
                    _rollback_created_ref(fd, parts[-1], created_identity)
                except SnapshotCleanupError as cleanup:
                    raise SnapshotCleanupError(
                        f"temporary ref {name} failed during publication and rollback: {cleanup}"
                    ) from exc
            if isinstance(exc, SnapshotUnavailable):
                raise
            if isinstance(exc, OSError):
                raise SnapshotUnavailable(
                    f"could not publish temporary ref {name}: {exc}"
                ) from exc
            raise
        finally:
            if ref_fd is not None:
                try:
                    os.close(ref_fd)
                except OSError as exc:
                    if created_identity is not None:
                        try:
                            _rollback_created_ref(fd, parts[-1], created_identity)
                        except SnapshotCleanupError as cleanup:
                            raise SnapshotCleanupError(
                                f"temporary ref {name} close and rollback failed: {cleanup}"
                            ) from exc
                    raise SnapshotUnavailable(
                        f"could not close temporary ref {name}: {exc}"
                    ) from exc
    finally:
        os.close(fd)


def _rollback_created_ref(
    parent_fd: int, filename: str, identity: tuple[int, int],
) -> None:
    """Remove only the exact inode created by this publication attempt."""
    try:
        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) \
                or (current.st_dev, current.st_ino) != identity:
            raise SnapshotCleanupError("new temporary ref changed identity before rollback")
        os.unlink(filename, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileNotFoundError:
        return
    except SnapshotCleanupError:
        raise
    except OSError as exc:
        raise SnapshotCleanupError(f"could not roll back newly created ref: {exc}") from exc


def _read_owned_ref(common: Path, name: str) -> str | None:
    parts = _ref_parts(name)
    fd = _open_refs_root(common, create=False)
    try:
        for component in parts[:-1]:
            try:
                child = _open_child_directory(fd, component, create=False)
            except FileNotFoundError:
                return None
            os.close(fd)
            fd = child
        try:
            data = _read_small_regular_at(fd, parts[-1])
        except FileNotFoundError:
            return None
        try:
            return data.decode("ascii", errors="strict").strip()
        except UnicodeError as exc:
            raise SnapshotUnavailable(f"temporary ref {name} is malformed") from exc
    finally:
        os.close(fd)


def _delete_owned_ref(common: Path, name: str, oid: str) -> None:
    parts = _ref_parts(name)
    fd = _open_refs_root(common, create=False)
    try:
        for component in parts[:-1]:
            try:
                child = _open_child_directory(fd, component, create=False)
            except FileNotFoundError:
                return
            os.close(fd)
            fd = child
        try:
            current = _read_small_regular_at(fd, parts[-1]).decode(
                "ascii", errors="strict"
            ).strip()
        except FileNotFoundError:
            return
        except UnicodeError as exc:
            raise SnapshotCleanupError(f"temporary ref {name} is malformed") from exc
        if current != oid:
            raise SnapshotCleanupError(f"temporary ref {name} changed owner")
        try:
            os.unlink(parts[-1], dir_fd=fd)
            os.fsync(fd)
        except OSError as exc:
            raise SnapshotCleanupError(f"could not delete temporary ref {name}: {exc}") from exc
    finally:
        os.close(fd)


def _publish_owned_refs(common: Path, refs: list[tuple[str, str]]) -> None:
    created: list[tuple[str, str]] = []
    try:
        for name, oid in refs:
            _write_owned_ref(common, name, oid)
            created.append((name, oid))
    except Exception as exc:
        failures: list[str] = []
        for name, oid in reversed(created):
            try:
                _delete_owned_ref(common, name, oid)
            except SnapshotUnavailable as cleanup:
                failures.append(str(cleanup))
        if failures:
            raise SnapshotCleanupError(
                "temporary-ref publication failed and rollback was incomplete: "
                + "; ".join(failures)
            ) from exc
        raise


def _ref_token(run_id: str) -> str:
    safe = _SAFE.sub("-", run_id).strip(".-")[:48] or "run"
    digest = hashlib.sha256(run_id.encode()).hexdigest()[:12]
    return f"{safe}-{digest}"


@dataclass(frozen=True)
class _GitControl:
    directory: Path
    environment: dict[str, str]


def _controlled_config_value(
    directory: Path, source: Path, key: str,
) -> str:
    ambient = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    try:
        result = subprocess.run(
            ["git", "config", "--file", str(source), "--no-includes", "--get", key],
            cwd=directory, capture_output=True, timeout=GIT_TIMEOUT_SECONDS,
            env={**ambient, **_GIT_ENV},
        )
    except subprocess.TimeoutExpired as exc:
        raise SnapshotUnavailable("controlled Git config parsing exceeded hard deadline") from exc
    if result.returncode not in {0, 1}:
        raise SnapshotUnavailable(
            "repository format config is malformed: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result.stdout.decode("utf-8", errors="strict").strip() if result.returncode == 0 else ""


def _create_git_control(repo: Path) -> _GitControl:
    """Create a Git directory whose config is entirely server-owned.

    Object and loose-ref storage remain in the approved native common directory, but
    repository config, config.worktree, includes, HEAD, index, packed refs, and shallow
    metadata are copied or replaced before any repository-aware Git command executes.
    """
    git_dir, common = _approved_repository_dirs(repo)
    directory = Path(tempfile.mkdtemp(prefix="paranoia-plan-git-control-"))
    try:
        source_config = directory / "source.config"
        source_config.write_bytes(
            _read_small_regular(common / "config", max_bytes=1 << 20, missing_ok=True)
        )
        version = _controlled_config_value(
            directory, source_config, "core.repositoryformatversion"
        ) or "0"
        object_format = _controlled_config_value(
            directory, source_config, "extensions.objectformat"
        ) or "sha1"
        ref_storage = _controlled_config_value(
            directory, source_config, "extensions.refstorage"
        ) or "files"
        if version not in {"0", "1"} or object_format not in {"sha1", "sha256"} \
                or ref_storage != "files":
            raise SnapshotUnavailable("repository format is unsupported by the safe Git profile")
        config_lines = [
            "[core]", f"\trepositoryFormatVersion = {version}", "\tbare = false",
            "\tlogAllRefUpdates = false",
        ]
        if object_format != "sha1":
            config_lines += ["[extensions]", f"\tobjectFormat = {object_format}"]
        (directory / "config").write_text("\n".join(config_lines) + "\n", encoding="ascii")
        source_config.unlink()

        head = _read_small_regular(git_dir / "HEAD", max_bytes=4096)
        (directory / "HEAD").write_bytes(head)
        for name, source, cap in (
            ("index", git_dir / "index", 64 << 20),
            ("packed-refs", common / "packed-refs", MAX_DISCOVERY_BYTES),
            ("shallow", common / "shallow", MAX_DISCOVERY_BYTES),
        ):
            data = _read_small_regular(source, max_bytes=cap, missing_ok=True)
            if data:
                (directory / name).write_bytes(data)
        _copy_loose_refs(common, directory / "refs")
        environment = {
            "GIT_DIR": str(directory),
            "GIT_WORK_TREE": str(repo),
            "GIT_OBJECT_DIRECTORY": str(common / "objects"),
        }
        return _GitControl(directory, environment)
    except Exception:
        import shutil
        shutil.rmtree(directory, ignore_errors=True)
        raise


@dataclass
class PlanRepositorySnapshot:
    repo: Path
    head_id: str
    tree_id: str
    commit_id: str
    wrapper_ref: str
    history_refs: dict[str, str]
    ignored_paths: tuple[str, ...]
    unavailable_paths: tuple[str, ...]
    _git_env: dict[str, str] = field(default_factory=dict, repr=False)
    _control_dir: Path | None = field(default=None, repr=False)
    _common_dir: Path | None = field(default=None, repr=False)
    _owned_refs: list[tuple[str, str]] = field(default_factory=list, repr=False)
    _closed: bool = field(default=False, repr=False)

    @classmethod
    def create(
        cls, repo: Path, *, run_id: str,
        before_pin: Callable[[list[tuple[str, str]]], None] | None = None,
    ) -> "PlanRepositorySnapshot":
        repo = Path(repo).resolve()
        _validate_object_boundary(repo)
        control = _create_git_control(repo)
        try:
            git_env = control.environment
            head_result = _run(
                repo, ["rev-parse", "--verify", "--quiet", "HEAD"],
                check=False, git_env=git_env,
            )
            has_head = head_result.returncode == 0
            head = (
                head_result.stdout.decode("ascii").strip()
                if has_head
                else _run(
                    repo, ["hash-object", "-t", "tree", "--stdin"], input_bytes=b"",
                    git_env=git_env,
                ).stdout.decode("ascii").strip()
            )
            ignored_raw = _run_bounded_records(
                repo,
                ["ls-files", "--others", "-i", "--exclude-standard", "--directory", "-z"],
                max_records=MAX_SNAPSHOT_PATHS, git_env=git_env,
            )
            ignored = tuple(
                item.decode("utf-8", errors="surrogateescape")
                for item in ignored_raw.split(b"\0") if item
            )
            tree, unavailable = _snapshot_tree_without_filters(repo, git_env=git_env)
            unavailable = tuple(dict.fromkeys([
                *unavailable, *_find_special_paths(repo, ignored_paths=ignored)
            ]))
            commit_args = ["commit-tree", "--no-gpg-sign", tree]
            if has_head:
                commit_args += ["-p", head]
            commit_args += ["-m", "paranoia-plan-snapshot"]
            commit = _run(
                repo, commit_args, git_env=git_env, extra_env=_SNAPSHOT_IDENTITY,
            ).stdout.decode("ascii").strip()
            token = _ref_token(run_id)
            wrapper_ref = f"refs/paranoia/plan-snapshots/{token}/wrapper"
            raw_refs = _run_bounded_records(
                repo,
                ["for-each-ref", "--format=%(refname)%00%(objectname)%00", "refs/"],
                max_records=MAX_DISCOVERED_REFS, terminators_per_record=2,
                git_env=git_env,
            )
            history: dict[str, str] = {}
            for line in raw_refs.splitlines():
                name_raw, separator, oid_raw = line.partition(b"\0")
                if not separator or not oid_raw.endswith(b"\0"):
                    raise SnapshotUnavailable("Git ref enumeration returned a malformed record")
                name = name_raw.decode("utf-8", errors="surrogateescape")
                oid = oid_raw[:-1].decode("ascii", errors="strict")
                if name.startswith(("refs/paranoia/plan-snapshots/", "refs/replace/")):
                    continue
                history[name] = oid
            if len(history) + 1 > MAX_PINNED_REFS:
                raise SnapshotUnavailable(
                    f"repository has {len(history)} refs; plan snapshot cap is {MAX_PINNED_REFS - 1}"
                )
            owned: list[tuple[str, str]] = [(wrapper_ref, commit)]
            for index, (name, oid) in enumerate(sorted(history.items()), 1):
                suffix = hashlib.sha256(
                    name.encode("utf-8", errors="surrogateescape")
                ).hexdigest()[:16]
                owned.append(
                    (f"refs/paranoia/plan-snapshots/{token}/history-{index:04d}-{suffix}", oid)
                )
            if before_pin is not None:
                before_pin(owned)
            _publish_owned_refs(common=Path(git_env["GIT_OBJECT_DIRECTORY"]).parent, refs=owned)
            try:
                cls._create_refs(repo, owned, git_env=git_env)
            except Exception as exc:
                failures: list[str] = []
                common = Path(git_env["GIT_OBJECT_DIRECTORY"]).parent
                for name, oid in reversed(owned):
                    try:
                        _delete_owned_ref(common, name, oid)
                    except SnapshotUnavailable as cleanup:
                        failures.append(str(cleanup))
                if failures:
                    raise SnapshotCleanupError(
                        "private ref publication failed and real pin cleanup was incomplete: "
                        + "; ".join(failures)
                    ) from exc
                raise
            return cls(
                repo, head, tree, commit, wrapper_ref, history, ignored,
                unavailable, git_env, control.directory,
                Path(git_env["GIT_OBJECT_DIRECTORY"]).parent, owned,
            )
        except Exception:
            import shutil
            shutil.rmtree(control.directory, ignore_errors=True)
            raise

    @staticmethod
    def _create_refs(
        repo: Path, refs: list[tuple[str, str]], *, git_env: dict[str, str],
    ) -> None:
        commands = ["start"] + [f"create {name} {oid}" for name, oid in refs] + ["prepare", "commit"]
        _run(
            repo, ["update-ref", "--stdin"],
            input_bytes=("\n".join(commands) + "\n").encode(), git_env=git_env,
        )

    def __enter__(self) -> "PlanRepositorySnapshot":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        try:
            failures: list[str] = []
            if self._common_dir is None:
                failures.append("approved common Git directory is unavailable")
            for name, oid in self._owned_refs:
                if self._common_dir is None:
                    continue
                try:
                    _delete_owned_ref(self._common_dir, name, oid)
                except SnapshotUnavailable as exc:
                    failures.append(str(exc))
            if failures:
                raise SnapshotCleanupError(
                    "could not delete temporary snapshot refs: " + "; ".join(failures)
                )
        except SnapshotCleanupError:
            raise
        except Exception as exc:
            raise SnapshotCleanupError(
                f"temporary snapshot-ref cleanup failed ambiguously: {exc}"
            ) from exc
        if self._control_dir is not None:
            import shutil
            try:
                shutil.rmtree(self._control_dir)
            except OSError as exc:
                raise SnapshotCleanupError(
                    f"could not remove server-owned Git control directory: {exc}"
                ) from exc
        self._closed = True

    def _verify_wrapper(self) -> None:
        _validate_object_boundary(self.repo)
        _git_dir, current_common = _approved_repository_dirs(self.repo)
        if self._common_dir is None or current_common != self._common_dir:
            raise SnapshotUnavailable("repository Git metadata boundary changed")
        if self._common_dir is None \
                or _read_owned_ref(self._common_dir, self.wrapper_ref) != self.commit_id:
            raise SnapshotUnavailable("pinned snapshot object/ref is missing or changed")
        result = _run(
            self.repo, ["rev-parse", "--verify", self.wrapper_ref + "^{commit}"],
            check=False, git_env=self._git_env,
        )
        actual = result.stdout.decode().strip() if result.returncode == 0 else ""
        if actual != self.commit_id:
            raise SnapshotUnavailable("pinned snapshot object/ref is missing or changed")

    def _entry(self, path: str) -> tuple[str, str, str]:
        self._verify_wrapper()
        if not isinstance(path, str):
            raise SnapshotUnavailable("repository evidence path must be a string")
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts or "\0" in path:
            raise SnapshotUnavailable("repository evidence path escapes the snapshot")
        literal = ":(literal)" + path
        out = _run_bounded_records(
            self.repo, ["ls-tree", "-z", self.commit_id, "--", literal],
            max_records=1, max_bytes=16384, git_env=self._git_env,
        )
        rows = [row for row in out.split(b"\0") if row]
        if len(rows) != 1:
            raise SnapshotUnavailable(f"path {path!r} is not present uniquely in the snapshot")
        meta, _, actual_path = rows[0].partition(b"\t")
        parts = meta.decode("ascii").split()
        if len(parts) != 3 or actual_path.decode("utf-8", errors="surrogateescape") != path:
            raise SnapshotUnavailable("literal tree membership check failed")
        return parts[0], parts[1], parts[2]

    def blob_identity(self, path: str) -> tuple[str, int]:
        mode, kind, oid = self._entry(path)
        if mode == "120000":
            raise SnapshotUnavailable("symlink paths are not repository evidence blobs")
        if mode == "160000" or kind == "commit":
            raise SnapshotUnavailable("gitlinks are unavailable without a supplied artifact")
        if kind != "blob":
            raise SnapshotUnavailable("repository evidence path is not a blob")
        size_raw = _run(
            self.repo, ["cat-file", "-s", oid], git_env=self._git_env,
        ).stdout.decode("ascii").strip()
        try:
            size = int(size_raw)
        except ValueError as exc:
            raise SnapshotUnavailable("repository blob size is malformed") from exc
        return oid, size

    def read_blob(self, path: str, *, offset: int = 0, max_bytes: int = 1 << 20) -> bytes:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise SnapshotUnavailable("repository blob offset must be a nonnegative integer")
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            raise SnapshotUnavailable("repository blob byte limit must be positive")
        oid, size = self.blob_identity(path)
        if offset > size:
            raise SnapshotUnavailable("repository blob offset exceeds source size")
        wanted = min(max_bytes, size - offset)
        ambient = {
            key: value for key, value in os.environ.items() if not key.startswith("GIT_")
        }
        proc = subprocess.Popen(
            ["git", *_GIT_CONFIG, "cat-file", "blob", oid], cwd=self.repo,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**ambient, **_GIT_ENV, **self._git_env},
        )
        assert proc.stdout is not None
        result = bytearray()
        skipped = 0
        deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
        try:
            while skipped < offset:
                chunk = _read_deadline(
                    proc.stdout, min(65536, offset - skipped), deadline
                )
                if not chunk:
                    raise SnapshotUnavailable("repository blob ended before requested offset")
                skipped += len(chunk)
            while len(result) < wanted:
                chunk = _read_deadline(
                    proc.stdout, min(65536, wanted - len(result)), deadline
                )
                if not chunk:
                    break
                result.extend(chunk)
            if offset + wanted == size:
                returncode = _wait_and_reap(
                    proc, deadline=deadline, terminate=False,
                    context="git cat-file",
                )
                if returncode:
                    stderr = proc.stderr.read() if proc.stderr else b""
                    raise SnapshotUnavailable(
                        "git cat-file failed: "
                        + stderr.decode("utf-8", errors="replace").strip()
                    )
            else:
                returncode = _wait_and_reap(
                    proc, deadline=deadline, terminate=True,
                    context="git cat-file",
                )
                if returncode not in {0, -15}:
                    raise SnapshotUnavailable("git cat-file failed during bounded read")
        finally:
            _kill_and_reap(proc, context="git cat-file")
        return bytes(result)

    def list_tree(
        self, prefix: str = "", *, limit: int = 200,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> list[str]:
        rows, _complete = self.list_tree_scoped(
            prefix, limit=limit, debit_bytes=debit_bytes,
            remaining_bytes=remaining_bytes,
        )
        return rows

    def list_tree_scoped(
        self, prefix: str = "", *, limit: int = 200,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> tuple[list[str], bool]:
        self._verify_wrapper()
        if limit < 1 or limit > 200:
            raise SnapshotUnavailable("tree result limit must be 1..200")
        args = ["ls-tree", "-r", "-z", "--name-only", self.commit_id]
        if not isinstance(prefix, str):
            raise SnapshotUnavailable("tree prefix must be a string")
        if prefix:
            pure = PurePosixPath(prefix)
            if pure.is_absolute() or ".." in pure.parts:
                raise SnapshotUnavailable("tree prefix escapes snapshot")
            args += ["--", ":(literal)" + prefix]
        rows = _run_bounded(
            self.repo, args, max_bytes=1 << 20, stop_after_nuls=limit + 1,
            git_env=self._git_env,
            debit_bytes=debit_bytes, remaining_bytes=remaining_bytes,
        ).split(b"\0")
        decoded = [r.decode("utf-8", errors="surrogateescape") for r in rows if r]
        return decoded[:limit], len(decoded) <= limit

    def search_literal(self, pattern: str, *, paths: list[str] | None = None,
                       limit: int = 50,
                       debit_bytes: Callable[[int], None] | None = None,
                       remaining_bytes: Callable[[], int] | None = None,
                       ) -> list[dict[str, object]]:
        matches, _scope = self.search_literal_scoped(
            pattern, paths=paths, limit=limit, debit_bytes=debit_bytes,
            remaining_bytes=remaining_bytes,
        )
        return matches

    def search_literal_scoped(
        self, pattern: str, *, paths: list[str] | None = None,
        limit: int = 50,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        if not isinstance(pattern, str) or not pattern or len(pattern.encode()) > 256 \
                or not (1 <= limit <= 50):
            raise SnapshotUnavailable("literal search exceeds bounds")
        results: list[dict[str, object]] = []
        if paths:
            candidates, candidates_complete = list(paths), True
        else:
            candidates, candidates_complete = self.list_tree_scoped(
                limit=200, debit_bytes=debit_bytes, remaining_bytes=remaining_bytes,
            )
        if any(not isinstance(path, str) for path in candidates):
            raise SnapshotUnavailable("literal search paths must be strings")
        inspected_ranges: list[dict[str, object]] = []
        all_blobs_complete = True
        processed = 0
        for path in candidates[:200]:
            try:
                oid, source_size = self.blob_identity(path)
                inspected = min(source_size, 1 << 20)
                if debit_bytes is not None:
                    debit_bytes(inspected)
                data = self.read_blob(path, max_bytes=max(1, inspected))
            except SnapshotUnavailable:
                all_blobs_complete = False
                continue
            processed += 1
            whole_blob = inspected == source_size
            all_blobs_complete = all_blobs_complete and whole_blob
            inspected_ranges.append({
                "path": path, "blob_oid": oid, "start": 0, "end": len(data),
                "whole_size": source_size, "complete": whole_blob,
            })
            start = 0
            needle = pattern.encode("utf-8")
            while len(results) <= limit:
                offset = data.find(needle, start)
                if offset < 0:
                    break
                line = data.count(b"\n", 0, offset) + 1
                results.append({"path": path, "byte": offset, "line": line})
                start = offset + max(1, len(needle))
            if len(results) > limit:
                break
        complete = (
            candidates_complete
            and processed == len(candidates[:200])
            and len(candidates) <= 200
            and all_blobs_complete
            and len(results) <= limit
        )
        scope: dict[str, object] = {
            "limit": limit,
            "complete": complete,
            "candidates_complete": candidates_complete and len(candidates) <= 200,
            "candidate_paths": list(candidates[:200]),
            "inspected_ranges": inspected_ranges,
        }
        return results[:limit], scope

    def history(
        self, ref: str, path: str, *, limit: int = 20,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> list[dict[str, str]]:
        rows, _complete = self.history_scoped(
            ref, path, limit=limit, debit_bytes=debit_bytes,
            remaining_bytes=remaining_bytes,
        )
        return rows

    def history_scoped(
        self, ref: str, path: str, *, limit: int = 20,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> tuple[list[dict[str, str]], bool]:
        """Read only commits reachable from the initial pinned ref map."""
        self._verify_wrapper()
        if not (1 <= limit <= 50):
            raise SnapshotUnavailable("history result limit must be 1..50")
        oid = self.history_oid(ref)
        if not isinstance(ref, str) or not isinstance(path, str):
            raise SnapshotUnavailable("history ref and path must be strings")
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts:
            raise SnapshotUnavailable("history path escapes snapshot")
        exists = _run(
            self.repo, ["cat-file", "-e", oid + "^{commit}"], check=False,
            git_env=self._git_env,
        )
        if exists.returncode:
            raise SnapshotUnavailable("pinned history object is missing")
        output = _run_bounded(
            self.repo,
            ["log", f"-{limit + 1}", "--format=%H%x00%ct%x00%s%x00", oid, "--",
             ":(literal)" + path],
            max_bytes=1 << 20, stop_after_nuls=(limit + 1) * 3,
            git_env=self._git_env,
            debit_bytes=debit_bytes, remaining_bytes=remaining_bytes,
        )
        tokens = output.decode("utf-8", errors="replace").split("\0")
        rows: list[dict[str, str]] = []
        for index in range(0, len(tokens) - 2, 3):
            commit, timestamp, subject = tokens[index:index + 3]
            if commit:
                rows.append({"commit": commit.strip(), "timestamp": timestamp,
                             "subject": subject.strip()[:500]})
        return rows[:limit], len(rows) <= limit

    def history_oid(self, ref: str) -> str:
        if ref == "SNAPSHOT":
            return self.commit_id
        oid = self.history_refs.get(ref, "")
        if not oid:
            raise SnapshotUnavailable("history ref was not in the initial pinned map")
        return oid



def _snapshot_tree_without_filters(
    repo: Path, *, git_env: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    """Hash working-tree bytes without ``git add`` or repository-selected commands.

    Git supplies only the candidate path set and object database. File bytes are opened
    with ``O_NOFOLLOW``, hashed through stdin (which bypasses clean filters), and inserted
    into a private index with explicit modes/object IDs. Repository hooks, fsmonitor,
    attributes, filters, pagers, and aliases therefore cannot select an executable step.
    """
    cached = _run_bounded_records(
        repo, ["ls-files", "-s", "-z"], max_records=MAX_SNAPSHOT_PATHS,
        git_env=git_env,
    )
    index_entries: dict[str, tuple[str, str]] = {}
    for row in [item for item in cached.split(b"\0") if item]:
        meta, sep, raw_path = row.partition(b"\t")
        fields = meta.decode("ascii", errors="strict").split()
        if not sep or len(fields) != 3:
            raise SnapshotUnavailable("git index entry was malformed")
        mode, oid, stage = fields
        if stage == "0":
            index_entries[raw_path.decode("utf-8", errors="surrogateescape")] = (mode, oid)

    candidates = _run_bounded_records(
        repo, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        max_records=MAX_SNAPSHOT_PATHS, git_env=git_env,
    )
    rows: list[tuple[str, str, str]] = []
    unavailable: list[str] = []
    for raw_path in [item for item in candidates.split(b"\0") if item]:
        path = raw_path.decode("utf-8", errors="surrogateescape")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise SnapshotUnavailable("snapshot candidate path escapes repository")
        target = repo.joinpath(*pure.parts)
        cursor = repo
        for part in pure.parts[:-1]:
            cursor = cursor / part
            if cursor.is_symlink():
                raise SnapshotUnavailable(f"snapshot path traverses a symlink: {path!r}")
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue  # tracked deletion
        indexed = index_entries.get(path)
        if indexed and indexed[0] == "160000":
            rows.append(("160000", indexed[1], path))
            continue
        if stat.S_ISLNK(info.st_mode):
            body = os.readlink(target).encode("utf-8", errors="surrogateescape")
            oid = _run(
                repo, ["hash-object", "-w", "--stdin"], input_bytes=body,
                git_env=git_env,
            ).stdout.decode().strip()
            rows.append(("120000", oid, path))
            continue
        if not stat.S_ISREG(info.st_mode):
            unavailable.append(path)
            continue
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags)
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise SnapshotUnavailable(f"snapshot path changed while opening: {path!r}")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                ambient = {
                    key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")
                }
                try:
                    proc = subprocess.run(
                        ["git", *_GIT_CONFIG, "hash-object", "-w", "--stdin"],
                        cwd=repo, stdin=handle, capture_output=True,
                        timeout=GIT_TIMEOUT_SECONDS,
                        env={**ambient, **_GIT_ENV, **git_env},
                    )
                except subprocess.TimeoutExpired as exc:
                    raise SnapshotUnavailable("git hash-object exceeded hard deadline") from exc
            if proc.returncode:
                raise SnapshotUnavailable(
                    "git hash-object failed: "
                    + proc.stderr.decode("utf-8", errors="replace").strip()
                )
            oid = proc.stdout.decode("ascii").strip()
        finally:
            os.close(fd)
        rows.append(("100755" if opened.st_mode & 0o111 else "100644", oid, path))

    index_dir = Path(tempfile.mkdtemp(prefix="paranoia-plan-index-"))
    try:
        env_index = str(index_dir / "index")
        private_env = {"GIT_INDEX_FILE": env_index}
        _run(
            repo, ["read-tree", "--empty"], git_env=git_env,
            extra_env=private_env,
        )
        payload = b"".join(
            f"{mode} {oid}\t".encode("ascii")
            + path.encode("utf-8", errors="surrogateescape") + b"\0"
            for mode, oid, path in sorted(
                rows, key=lambda item: item[2].encode("utf-8", "surrogateescape")
            )
        )
        _run(
            repo, ["update-index", "-z", "--index-info"],
            input_bytes=payload, git_env=git_env, extra_env=private_env,
        )
        tree = _run(
            repo, ["write-tree"], git_env=git_env, extra_env=private_env,
        ).stdout.decode("ascii").strip()
        return tree, tuple(unavailable)
    finally:
        import shutil
        shutil.rmtree(index_dir, ignore_errors=True)


def _validate_object_boundary(repo: Path) -> None:
    _git_dir, common = _approved_repository_dirs(repo)
    objects = common / "objects"
    _validate_object_store_paths(objects)
    for name in ("alternates", "http-alternates"):
        path = objects / "info" / name
        if _read_small_regular(path, missing_ok=True).strip():
            raise SnapshotUnavailable(
                f"repository object alternates are outside the approved snapshot boundary: {path}"
            )


def _approved_common_dir(repo: Path) -> Path:
    return _approved_repository_dirs(repo)[1]


def _approved_repository_dirs(repo: Path) -> tuple[Path, Path]:
    dotgit = repo / ".git"
    try:
        dotgit_info = dotgit.lstat()
    except OSError as exc:
        raise SnapshotUnavailable(f"repository gitfile is unavailable: {exc}") from exc
    if stat.S_ISLNK(dotgit_info.st_mode):
        raise SnapshotUnavailable("repository .git may not be a symlink")
    if stat.S_ISDIR(dotgit_info.st_mode):
        resolved = dotgit.resolve()
        return resolved, resolved
    try:
        marker = _read_small_regular(dotgit).decode("utf-8", errors="strict").strip()
    except UnicodeError as exc:
        raise SnapshotUnavailable(f"repository gitfile is unavailable: {exc}") from exc
    if not marker.startswith("gitdir: "):
        raise SnapshotUnavailable("repository gitfile is malformed")
    git_dir = Path(marker[8:])
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve()
    else:
        git_dir = git_dir.resolve()
    try:
        common_marker = _read_small_regular(git_dir / "commondir").decode(
            "utf-8", errors="strict"
        ).strip()
        backlink = _read_small_regular(git_dir / "gitdir").decode(
            "utf-8", errors="strict"
        ).strip()
    except (SnapshotUnavailable, UnicodeError) as exc:
        raise SnapshotUnavailable(f"linked-worktree metadata is unavailable: {exc}") from exc
    common = (git_dir / common_marker).resolve()
    backlink_path = Path(backlink)
    if not backlink_path.is_absolute():
        backlink_path = (git_dir / backlink_path).resolve()
    else:
        backlink_path = backlink_path.resolve()
    if git_dir.parent.name != "worktrees" or git_dir.parent.parent != common \
            or backlink_path != dotgit.resolve():
        raise SnapshotUnavailable("gitfile is not a self-consistent native linked worktree")
    return git_dir, common


def _validate_object_store_paths(objects: Path, *, max_entries: int = 200_000) -> None:
    if objects.is_symlink() or not objects.is_dir():
        raise SnapshotUnavailable("repository object-store root must be a real directory")
    seen = 0

    def scan(directory: Path, relevant: Callable[[str], bool]) -> list[Path]:
        nonlocal seen
        directories: list[Path] = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    seen += 1
                    if seen > max_entries:
                        raise SnapshotUnavailable(
                            "repository object-store metadata scan exceeds safety cap"
                        )
                    if not relevant(entry.name):
                        continue
                    if entry.is_symlink():
                        raise SnapshotUnavailable(
                            f"repository object-store path may not be a symlink: {entry.path}"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(Path(entry.path))
        except SnapshotUnavailable:
            raise
        except OSError as exc:
            raise SnapshotUnavailable(
                f"could not inspect repository object store: {exc}"
            ) from exc
        return directories

    # Git resolves only loose-object fanout and explicit pack/info names. Arbitrary
    # nested directories in those namespaces are inert and cannot redirect lookup.
    roots = scan(
        objects,
        lambda name: name in {"pack", "info"}
        or bool(re.fullmatch(r"[0-9a-fA-F]{2}", name)),
    )
    loose_name = re.compile(r"(?:[0-9a-fA-F]{38}|[0-9a-fA-F]{62})$")
    object_hex = r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})"
    pack_name = re.compile(
        rf"(?:pack-{object_hex}\.(?:pack|idx|rev|bitmap|promisor|mtimes)"
        rf"|multi-pack-index(?:-{object_hex}\.bitmap)?|multi-pack-index\.d)$"
    )
    info_name = re.compile(r"(?:alternates|http-alternates|packs|commit-graph|commit-graphs)$")
    for directory in roots:
        if re.fullmatch(r"[0-9a-fA-F]{2}", directory.name):
            scan(directory, lambda name: bool(loose_name.fullmatch(name)))
        elif directory.name == "pack":
            nested = scan(directory, lambda name: bool(pack_name.fullmatch(name)))
            for child in nested:
                if child.name == "multi-pack-index.d":
                    scan(
                        child,
                        lambda name: name == "multi-pack-index-chain"
                        or bool(re.fullmatch(
                            rf"multi-pack-index-{object_hex}\.midx", name
                        )),
                    )
        elif directory.name == "info":
            nested = scan(directory, lambda name: bool(info_name.fullmatch(name)))
            for child in nested:
                if child.name == "commit-graphs":
                    scan(
                        child,
                        lambda name: name == "commit-graph-chain"
                        or bool(re.fullmatch(rf"graph-{object_hex}\.graph", name)),
                    )


def _find_special_paths(
    repo: Path, *, ignored_paths: tuple[str, ...] = (), max_entries: int = 50_000
) -> tuple[str, ...]:
    """Disclose nonregular entries Git omits from ``ls-files --others``."""
    special: list[str] = []
    pending = [repo]
    seen = 0
    ignored = {path.rstrip("/") for path in ignored_paths}
    while pending:
        directory = pending.pop()
        try:
            entries = os.scandir(directory)
        except OSError as exc:
            raise SnapshotUnavailable(f"could not inspect repository entry types: {exc}") from exc
        with entries:
            for entry in entries:
                if directory == repo and entry.name == ".git":
                    continue
                relative = Path(entry.path).relative_to(repo).as_posix()
                if relative in ignored:
                    continue
                seen += 1
                if seen > max_entries:
                    raise SnapshotUnavailable("repository entry scan exceeds safety cap")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                    continue
                mode = entry.stat(follow_symlinks=False).st_mode
                if not stat.S_ISREG(mode) and not stat.S_ISLNK(mode):
                    special.append(relative)
    return tuple(sorted(special))
