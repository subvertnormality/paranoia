"""Fast, pinned repository evidence for local plan verification.

The repository and its configuration are untrusted data, but the local operator, OS,
and other local processes are trusted.  Snapshot construction therefore prevents Git
configuration from selecting executable behaviour and detects ordinary concurrent edits;
it does not attempt to defend the filesystem namespace from a hostile racing process.
"""

from __future__ import annotations

import hashlib
import os
import re
import select
import shutil
import stat
import subprocess
import tempfile
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

MAX_PINNED_REFS = 1024
MAX_DISCOVERED_REFS = 4096
MAX_SNAPSHOT_PATHS = 100_000
MAX_DISCOVERY_BYTES = 32 << 20
MAX_SNAPSHOT_BYTES = 256 << 20
MAX_FILE_BYTES = 32 << 20
GIT_TIMEOUT_SECONDS = 30.0
PROCESS_REAP_SECONDS = 2.0

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
    "GIT_TERMINAL_PROMPT": "0",
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


class SnapshotUnavailable(RuntimeError):
    pass


class SnapshotContentUnavailable(SnapshotUnavailable):
    """A requested path/ref is absent or has an unsupported repository type."""


class SnapshotCleanupError(SnapshotUnavailable):
    """The ephemeral snapshot could not be removed cleanly."""


def _ambient() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _run(
    repo: Path,
    args: list[str],
    *,
    input_bytes: bytes | None = None,
    check: bool = True,
    git_env: dict[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = {**_ambient(), **_GIT_ENV, **(git_env or {}), **(extra_env or {})}
    try:
        result = subprocess.run(
            ["git", *_GIT_CONFIG, *args],
            cwd=repo,
            input=input_bytes,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnapshotUnavailable(f"git {' '.join(args[:2])} unavailable: {exc}") from exc
    if check and result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotUnavailable(f"git {' '.join(args[:2])} failed: {detail}")
    return result


def _read_deadline(pipe: object, size: int, deadline: float) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not select.select([pipe], [], [], remaining)[0]:
        raise SnapshotUnavailable("Git streaming read exceeded hard deadline")
    return os.read(pipe.fileno(), size)  # type: ignore[attr-defined]


def _kill_and_reap(proc: subprocess.Popen[bytes], *, context: str) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise SnapshotUnavailable(f"{context} could not be killed: {exc}") from exc
    try:
        proc.wait(timeout=PROCESS_REAP_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnapshotUnavailable(f"{context} could not be reaped: {exc}") from exc


def _wait_and_reap(
    proc: subprocess.Popen[bytes], *, deadline: float, terminate: bool, context: str,
) -> int:
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
    except (OSError, subprocess.TimeoutExpired) as exc:
        _kill_and_reap(proc, context=context)
        raise SnapshotUnavailable(f"{context} exceeded hard deadline: {exc}") from exc


def _run_bounded(
    repo: Path,
    args: list[str],
    *,
    max_bytes: int,
    stop_after_nuls: int,
    git_env: dict[str, str] | None = None,
    debit_bytes: Callable[[int], None] | None = None,
    remaining_bytes: Callable[[], int] | None = None,
) -> bytes:
    proc = subprocess.Popen(
        ["git", *_GIT_CONFIG, *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={**_ambient(), **_GIT_ENV, **(git_env or {})},
    )
    output = bytearray()
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    try:
        assert proc.stdout is not None
        while output.count(b"\0") < stop_after_nuls:
            local_remaining = max_bytes - len(output)
            shared_remaining = (
                remaining_bytes() if remaining_bytes is not None else local_remaining + 1
            )
            if local_remaining <= 0:
                raise SnapshotUnavailable("bounded Git output exceeds byte cap")
            if shared_remaining <= 0:
                raise SnapshotUnavailable("bounded Git output exceeds shared byte budget")
            chunk = _read_deadline(
                proc.stdout, min(65536, local_remaining + 1, shared_remaining), deadline
            )
            if not chunk:
                break
            if debit_bytes is not None:
                debit_bytes(len(chunk))
            output.extend(chunk)
            if len(output) > max_bytes:
                raise SnapshotUnavailable("bounded Git output exceeds byte cap")
        stopped_early = output.count(b"\0") >= stop_after_nuls
        returncode = _wait_and_reap(
            proc,
            deadline=deadline,
            terminate=stopped_early,
            context="bounded Git command",
        )
        if returncode not in {0, -15}:
            raise SnapshotUnavailable("bounded Git command failed")
        return bytes(output)
    finally:
        _kill_and_reap(proc, context="bounded Git command")


def _run_bounded_records(
    repo: Path,
    args: list[str],
    *,
    max_records: int,
    terminators_per_record: int = 1,
    max_bytes: int = MAX_DISCOVERY_BYTES,
    git_env: dict[str, str] | None = None,
) -> bytes:
    if max_records < 1 or terminators_per_record < 1:
        raise SnapshotUnavailable("Git enumeration bounds must be positive")
    output = _run_bounded(
        repo,
        args,
        max_bytes=max_bytes,
        stop_after_nuls=(max_records + 1) * terminators_per_record,
        git_env=git_env,
    )
    terminators = output.count(b"\0")
    if terminators > max_records * terminators_per_record:
        raise SnapshotUnavailable("Git enumeration exceeds record cap")
    if terminators % terminators_per_record:
        raise SnapshotUnavailable("Git enumeration returned a malformed record")
    return output


def _repository_dirs(repo: Path) -> tuple[Path, Path]:
    marker = repo / ".git"
    if marker.is_dir() and not marker.is_symlink():
        return marker, marker
    try:
        text = marker.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise SnapshotUnavailable(f"repository .git is unavailable: {exc}") from exc
    if not text.startswith("gitdir: ") or "\n" in text.strip("\n"):
        raise SnapshotUnavailable("repository gitfile is malformed")
    target = Path(text[8:].strip())
    git_dir = (repo / target).resolve() if not target.is_absolute() else target.resolve()
    if not git_dir.is_dir():
        raise SnapshotUnavailable("linked-worktree Git directory is unavailable")
    common = git_dir
    common_file = git_dir / "commondir"
    if common_file.exists():
        try:
            common_text = common_file.read_text(encoding="utf-8", errors="strict").strip()
        except (OSError, UnicodeError) as exc:
            raise SnapshotUnavailable(f"linked-worktree commondir is unavailable: {exc}") from exc
        common_path = Path(common_text)
        common = (
            (git_dir / common_path).resolve()
            if not common_path.is_absolute()
            else common_path.resolve()
        )
    if not common.is_dir():
        raise SnapshotUnavailable("linked-worktree common Git directory is unavailable")
    return git_dir, common


@dataclass(frozen=True)
class _GitControl:
    directory: Path
    git_dir: Path
    common: Path
    environment: dict[str, str]
    discovery_environment: dict[str, str]
    object_format: str


def _read_metadata(path: Path, *, max_bytes: int) -> bytes:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise SnapshotUnavailable(f"repository metadata is unsafe or oversized: {path}")
        return path.read_bytes()
    except SnapshotUnavailable:
        raise
    except OSError as exc:
        raise SnapshotUnavailable(f"repository metadata is unavailable: {path}: {exc}") from exc


def _copy_ref_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    entries = 0
    retained = 0
    for root, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()]
        relative = Path(root).relative_to(source)
        target_root = destination / relative
        target_root.mkdir(parents=True, exist_ok=True)
        for name in files:
            entries += 1
            if entries > MAX_DISCOVERED_REFS:
                raise SnapshotUnavailable("repository loose refs exceed record cap")
            candidate = Path(root) / name
            if candidate.is_symlink():
                continue
            body = _read_metadata(candidate, max_bytes=1024)
            retained += len(body)
            if retained > MAX_DISCOVERY_BYTES:
                raise SnapshotUnavailable("repository loose refs exceed byte cap")
            (target_root / name).write_bytes(body)


def _create_git_control(repo: Path) -> _GitControl:
    git_dir, common = _repository_dirs(repo)
    native_objects = common / "objects"
    if not native_objects.is_dir():
        raise SnapshotUnavailable("repository object database is unavailable")
    alternates = native_objects / "info" / "alternates"
    if alternates.exists():
        raise SnapshotUnavailable(
            "repository object alternates are unsupported by the local snapshot boundary"
        )

    directory = Path(tempfile.mkdtemp(prefix="paranoia-plan-snapshot-"))
    try:
        private_git = directory / "git"
        private_objects = directory / "objects"
        (private_git / "refs").mkdir(parents=True)
        (private_objects / "info").mkdir(parents=True)
        (private_git / "HEAD").write_bytes(_read_metadata(git_dir / "HEAD", max_bytes=4096))
        _copy_ref_tree(common / "refs", private_git / "refs")
        for name in ("packed-refs", "shallow"):
            source = common / name
            if source.exists():
                (private_git / name).write_bytes(
                    _read_metadata(source, max_bytes=MAX_DISCOVERY_BYTES)
                )

        config = common / "config"
        object_format = "sha1"
        if config.exists():
            result = subprocess.run(
                [
                    "git", "config", "--file", str(config), "--no-includes", "--get",
                    "extensions.objectFormat",
                ],
                cwd=directory,
                capture_output=True,
                timeout=GIT_TIMEOUT_SECONDS,
                env={**_ambient(), **_GIT_ENV},
            )
            if result.returncode == 0:
                object_format = result.stdout.decode("ascii", errors="strict").strip()
            elif result.returncode not in {1}:
                raise SnapshotUnavailable("repository object format metadata is malformed")
        if object_format not in {"sha1", "sha256"}:
            raise SnapshotUnavailable("repository object format is unsupported")
        (private_git / "config").write_text(
            "[core]\n\trepositoryformatversion = "
            + ("1" if object_format == "sha256" else "0")
            + "\n\tbare = false\n"
            + ("[extensions]\n\tobjectFormat = sha256\n" if object_format == "sha256" else ""),
            encoding="ascii",
        )

        environment = {
            "GIT_DIR": str(private_git),
            "GIT_WORK_TREE": str(repo),
            "GIT_OBJECT_DIRECTORY": str(private_objects),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(native_objects),
            "GIT_INDEX_FILE": str(directory / "snapshot.index"),
        }
        discovery_environment = {
            **environment,
            "GIT_INDEX_FILE": str(git_dir / "index"),
        }
        return _GitControl(
            directory,
            git_dir,
            common,
            environment,
            discovery_environment,
            object_format,
        )
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def _store_object(control: _GitControl, kind: str, body: bytes) -> str:
    payload = f"{kind} {len(body)}\0".encode("ascii") + body
    digest = hashlib.new(control.object_format, payload).hexdigest()
    target = Path(control.environment["GIT_OBJECT_DIRECTORY"]) / digest[:2] / digest[2:]
    if target.exists():
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{os.getpid()}.tmp"
    temporary.write_bytes(zlib.compress(payload))
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return digest


def _decode_path(raw: bytes) -> str:
    path = raw.decode("utf-8", errors="surrogateescape")
    pure = PurePosixPath(path)
    if not path or pure.is_absolute() or ".." in pure.parts or "\0" in path:
        raise SnapshotUnavailable("snapshot candidate path escapes repository")
    return path


def _index_entries(repo: Path, control: _GitControl) -> dict[str, tuple[str, str]]:
    raw = _run_bounded_records(
        repo,
        ["ls-files", "--stage", "-z"],
        max_records=MAX_SNAPSHOT_PATHS,
        git_env=control.discovery_environment,
    )
    entries: dict[str, tuple[str, str]] = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        metadata, tab, path_raw = row.partition(b"\t")
        parts = metadata.decode("ascii", errors="strict").split()
        if not tab or len(parts) != 3 or parts[2] != "0":
            raise SnapshotUnavailable("unmerged or malformed index entry is unsupported")
        path = _decode_path(path_raw)
        if path in entries:
            raise SnapshotUnavailable("duplicate index path is unsupported")
        entries[path] = (parts[0], parts[1])
    return entries


def _candidate_paths(repo: Path, control: _GitControl) -> tuple[str, ...]:
    raw = _run_bounded_records(
        repo,
        ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        max_records=MAX_SNAPSHOT_PATHS,
        git_env=control.discovery_environment,
    )
    return tuple(dict.fromkeys(_decode_path(row) for row in raw.split(b"\0") if row))


def _ignored_paths(repo: Path, control: _GitControl) -> tuple[str, ...]:
    raw = _run_bounded_records(
        repo,
        ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        max_records=MAX_SNAPSHOT_PATHS,
        git_env=control.discovery_environment,
    )
    return tuple(_decode_path(row) for row in raw.split(b"\0") if row)


def _special_paths(repo: Path, *, ignored: set[str]) -> tuple[str, ...]:
    """Disclose bounded nonregular entries that Git omits from untracked output."""
    found: list[str] = []
    entries = 0
    for root, dirs, files in os.walk(repo, followlinks=False):
        relative_root = Path(root).relative_to(repo)
        if relative_root == Path("."):
            dirs[:] = [name for name in dirs if name != ".git"]
        names = [*dirs, *files]
        for name in names:
            entries += 1
            if entries > MAX_SNAPSHOT_PATHS:
                raise SnapshotUnavailable("repository entry scan exceeds record cap")
            full = Path(root) / name
            relative = full.relative_to(repo).as_posix()
            if relative in ignored:
                continue
            try:
                mode = full.lstat().st_mode
            except OSError as exc:
                raise SnapshotUnavailable(
                    f"repository entry scan failed at {relative!r}: {exc}"
                ) from exc
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
                found.append(relative)
    return tuple(found)


def _read_regular(path: Path, *, remaining: int) -> tuple[bytes, os.stat_result]:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise SnapshotContentUnavailable("snapshot path is not a regular file")
    limit = min(MAX_FILE_BYTES, remaining)
    if before.st_size > limit:
        raise SnapshotContentUnavailable("snapshot file exceeds the bounded byte budget")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise SnapshotUnavailable("snapshot path changed type while opening")
        chunks = bytearray()
        while len(chunks) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )
    if len(chunks) > limit or identity(before) != identity(opened) or identity(opened) != identity(after):
        raise SnapshotUnavailable("snapshot path changed while reading")
    return bytes(chunks), opened


def _snapshot_tree(
    repo: Path, control: _GitControl,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    index = _index_entries(repo, control)
    candidates = _candidate_paths(repo, control)
    ignored = _ignored_paths(repo, control)
    rows: list[tuple[str, str, str]] = []
    unavailable: list[str] = list(_special_paths(repo, ignored=set(ignored)))
    retained_bytes = 0

    for path in candidates:
        full_path = repo / Path(path)
        indexed = index.get(path)
        try:
            info = full_path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SnapshotUnavailable(f"snapshot path is unavailable: {path!r}: {exc}") from exc

        if indexed and indexed[0] == "160000":
            rows.append(("160000", indexed[1], path))
            continue
        if stat.S_ISLNK(info.st_mode):
            try:
                body = os.readlink(full_path).encode("utf-8", errors="surrogateescape")
            except OSError as exc:
                raise SnapshotUnavailable(f"snapshot symlink is unavailable: {path!r}: {exc}") from exc
            rows.append(("120000", _store_object(control, "blob", body), path))
            retained_bytes += len(body)
            continue
        if not stat.S_ISREG(info.st_mode):
            unavailable.append(path)
            continue
        try:
            body, opened = _read_regular(
                full_path, remaining=MAX_SNAPSHOT_BYTES - retained_bytes
            )
        except SnapshotContentUnavailable:
            unavailable.append(path)
            continue
        retained_bytes += len(body)
        mode = "100755" if opened.st_mode & 0o111 else "100644"
        rows.append((mode, _store_object(control, "blob", body), path))

    _run(repo, ["read-tree", "--empty"], git_env=control.environment)
    payload = b"".join(
        f"{mode} {oid} 0\t".encode("ascii")
        + path.encode("utf-8", errors="surrogateescape")
        + b"\0"
        for mode, oid, path in sorted(rows, key=lambda row: row[2].encode(
            "utf-8", errors="surrogateescape"
        ))
    )
    if payload:
        _run(
            repo,
            ["update-index", "-z", "--index-info"],
            input_bytes=payload,
            git_env=control.environment,
        )
    tree = _run(repo, ["write-tree"], git_env=control.environment).stdout.decode("ascii").strip()
    return tree, tuple(unavailable), ignored


def _ref_token(run_id: str) -> str:
    safe = _SAFE.sub("-", run_id).strip("-")[:48] or "round"
    return f"{safe}-{hashlib.sha256(run_id.encode()).hexdigest()[:16]}"


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
    _closed: bool = field(default=False, repr=False)

    @classmethod
    def create(
        cls,
        repo: Path,
        *,
        run_id: str,
        before_pin: Callable[[list[tuple[str, str]]], None] | None = None,
    ) -> "PlanRepositorySnapshot":
        repo = Path(repo).resolve()
        if not repo.is_dir():
            raise SnapshotUnavailable("repository root is unavailable")
        control = _create_git_control(repo)
        try:
            head_result = _run(
                repo,
                ["rev-parse", "--verify", "--quiet", "HEAD"],
                check=False,
                git_env=control.environment,
            )
            has_head = head_result.returncode == 0
            head = head_result.stdout.decode("ascii").strip() if has_head else ""
            tree, unavailable, ignored = _snapshot_tree(repo, control)
            commit_args = ["commit-tree", "--no-gpg-sign", tree]
            if has_head:
                commit_args += ["-p", head]
            commit_args += ["-m", "paranoia-plan-snapshot"]
            commit = _run(
                repo,
                commit_args,
                git_env=control.environment,
                extra_env=_SNAPSHOT_IDENTITY,
            ).stdout.decode("ascii").strip()

            raw_refs = _run_bounded_records(
                repo,
                ["for-each-ref", "--format=%(refname)%00%(objectname)%00", "refs/"],
                max_records=MAX_DISCOVERED_REFS,
                terminators_per_record=2,
                git_env=control.environment,
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
            if len(history) > MAX_PINNED_REFS:
                raise SnapshotUnavailable(
                    f"repository has {len(history)} refs; history cap is {MAX_PINNED_REFS}"
                )
            if before_pin is not None:
                before_pin([])
            token = _ref_token(run_id)
            return cls(
                repo,
                head,
                tree,
                commit,
                f"ephemeral:{token}",
                history,
                ignored,
                unavailable,
                control.environment,
                control.directory,
            )
        except Exception:
            shutil.rmtree(control.directory, ignore_errors=True)
            raise

    def __enter__(self) -> "PlanRepositorySnapshot":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        if self._control_dir is not None:
            try:
                shutil.rmtree(self._control_dir)
            except OSError as exc:
                raise SnapshotCleanupError(
                    f"could not remove ephemeral repository snapshot: {exc}"
                ) from exc
        self._closed = True

    def _verify_wrapper(self) -> None:
        if self._closed:
            raise SnapshotUnavailable("repository snapshot is closed")
        result = _run(
            self.repo,
            ["cat-file", "-e", self.commit_id + "^{commit}"],
            check=False,
            git_env=self._git_env,
        )
        if result.returncode:
            raise SnapshotUnavailable("ephemeral snapshot object is unavailable")

    def _entry(self, path: str) -> tuple[str, str, str]:
        self._verify_wrapper()
        if not isinstance(path, str):
            raise SnapshotUnavailable("repository evidence path must be a string")
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts or "\0" in path:
            raise SnapshotUnavailable("repository evidence path escapes the snapshot")
        out = _run_bounded_records(
            self.repo,
            ["ls-tree", "-z", self.commit_id, "--", ":(literal)" + path],
            max_records=1,
            max_bytes=16384,
            git_env=self._git_env,
        )
        rows = [row for row in out.split(b"\0") if row]
        if len(rows) != 1:
            raise SnapshotContentUnavailable(f"path {path!r} is not present in the snapshot")
        metadata, _, actual_path = rows[0].partition(b"\t")
        parts = metadata.decode("ascii").split()
        if len(parts) != 3 or actual_path.decode(
            "utf-8", errors="surrogateescape"
        ) != path:
            raise SnapshotUnavailable("literal tree membership check failed")
        return parts[0], parts[1], parts[2]

    def blob_identity(self, path: str) -> tuple[str, int]:
        mode, kind, oid = self._entry(path)
        if mode == "120000":
            raise SnapshotContentUnavailable("symlink paths are not repository evidence blobs")
        if mode == "160000" or kind == "commit":
            raise SnapshotContentUnavailable("gitlinks require supplied evidence")
        if kind != "blob":
            raise SnapshotContentUnavailable("repository evidence path is not a blob")
        raw = _run(self.repo, ["cat-file", "-s", oid], git_env=self._git_env).stdout
        try:
            return oid, int(raw.decode("ascii").strip())
        except ValueError as exc:
            raise SnapshotUnavailable("repository blob size is malformed") from exc

    def read_blob(self, path: str, *, offset: int = 0, max_bytes: int = 1 << 20) -> bytes:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise SnapshotUnavailable("repository blob offset must be a nonnegative integer")
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            raise SnapshotUnavailable("repository blob byte limit must be positive")
        oid, size = self.blob_identity(path)
        if offset > size:
            raise SnapshotUnavailable("repository blob offset exceeds source size")
        wanted = min(max_bytes, size - offset)
        proc = subprocess.Popen(
            ["git", *_GIT_CONFIG, "cat-file", "blob", oid],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**_ambient(), **_GIT_ENV, **self._git_env},
        )
        result = bytearray()
        skipped = 0
        deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
        try:
            assert proc.stdout is not None
            while skipped < offset:
                chunk = _read_deadline(proc.stdout, min(65536, offset - skipped), deadline)
                if not chunk:
                    raise SnapshotUnavailable("repository blob ended before requested offset")
                skipped += len(chunk)
            while len(result) < wanted:
                chunk = _read_deadline(proc.stdout, min(65536, wanted - len(result)), deadline)
                if not chunk:
                    break
                result.extend(chunk)
            complete = offset + wanted == size
            returncode = _wait_and_reap(
                proc,
                deadline=deadline,
                terminate=not complete,
                context="git cat-file",
            )
            if returncode not in {0, -15}:
                raise SnapshotUnavailable("git cat-file failed during bounded read")
        finally:
            _kill_and_reap(proc, context="git cat-file")
        return bytes(result)

    def list_tree(
        self,
        prefix: str = "",
        *,
        limit: int = 200,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> list[str]:
        rows, _ = self.list_tree_scoped(
            prefix,
            limit=limit,
            debit_bytes=debit_bytes,
            remaining_bytes=remaining_bytes,
        )
        return rows

    def list_tree_scoped(
        self,
        prefix: str = "",
        *,
        limit: int = 200,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> tuple[list[str], bool]:
        self._verify_wrapper()
        if not (1 <= limit <= 200):
            raise SnapshotUnavailable("tree result limit must be 1..200")
        if not isinstance(prefix, str):
            raise SnapshotUnavailable("tree prefix must be a string")
        args = ["ls-tree", "-r", "-z", "--name-only", self.commit_id]
        if prefix:
            pure = PurePosixPath(prefix)
            if pure.is_absolute() or ".." in pure.parts:
                raise SnapshotUnavailable("tree prefix escapes snapshot")
            args += ["--", ":(literal)" + prefix]
        raw = _run_bounded(
            self.repo,
            args,
            max_bytes=1 << 20,
            stop_after_nuls=limit + 1,
            git_env=self._git_env,
            debit_bytes=debit_bytes,
            remaining_bytes=remaining_bytes,
        )
        decoded = [
            row.decode("utf-8", errors="surrogateescape")
            for row in raw.split(b"\0")
            if row
        ]
        return decoded[:limit], len(decoded) <= limit

    def search_literal(
        self,
        pattern: str,
        *,
        paths: list[str] | None = None,
        limit: int = 50,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> list[dict[str, object]]:
        rows, _ = self.search_literal_scoped(
            pattern,
            paths=paths,
            limit=limit,
            debit_bytes=debit_bytes,
            remaining_bytes=remaining_bytes,
        )
        return rows

    def search_literal_scoped(
        self,
        pattern: str,
        *,
        paths: list[str] | None = None,
        limit: int = 50,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        if not isinstance(pattern, str) or not pattern or len(pattern.encode()) > 256:
            raise SnapshotUnavailable("literal search exceeds bounds")
        if not (1 <= limit <= 50):
            raise SnapshotUnavailable("literal search exceeds bounds")
        if paths is None:
            candidates, candidates_complete = self.list_tree_scoped(
                limit=200,
                debit_bytes=debit_bytes,
                remaining_bytes=remaining_bytes,
            )
        else:
            if any(not isinstance(path, str) for path in paths):
                raise SnapshotUnavailable("literal search paths must be strings")
            candidates, candidates_complete = list(paths), True
        results: list[dict[str, object]] = []
        inspected_ranges: list[dict[str, object]] = []
        all_complete = True
        processed = 0
        needle = pattern.encode("utf-8")
        for path in candidates[:200]:
            try:
                oid, source_size = self.blob_identity(path)
                inspected = min(source_size, 1 << 20)
                if debit_bytes is not None:
                    debit_bytes(inspected)
                data = self.read_blob(path, max_bytes=max(1, inspected))
            except SnapshotContentUnavailable:
                all_complete = False
                continue
            processed += 1
            whole = inspected == source_size
            all_complete = all_complete and whole
            inspected_ranges.append({
                "path": path,
                "blob_oid": oid,
                "start": 0,
                "end": len(data),
                "whole_size": source_size,
                "complete": whole,
            })
            start = 0
            while len(results) <= limit:
                offset = data.find(needle, start)
                if offset < 0:
                    break
                results.append({
                    "path": path,
                    "byte": offset,
                    "line": data.count(b"\n", 0, offset) + 1,
                })
                start = offset + max(1, len(needle))
            if len(results) > limit:
                break
        complete = (
            candidates_complete
            and len(candidates) <= 200
            and processed == len(candidates[:200])
            and all_complete
            and len(results) <= limit
        )
        return results[:limit], {
            "limit": limit,
            "complete": complete,
            "candidates_complete": candidates_complete and len(candidates) <= 200,
            "candidate_paths": candidates[:200],
            "inspected_ranges": inspected_ranges,
        }

    def history(
        self,
        ref: str,
        path: str,
        *,
        limit: int = 20,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> list[dict[str, str]]:
        rows, _ = self.history_scoped(
            ref,
            path,
            limit=limit,
            debit_bytes=debit_bytes,
            remaining_bytes=remaining_bytes,
        )
        return rows

    def history_scoped(
        self,
        ref: str,
        path: str,
        *,
        limit: int = 20,
        debit_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> tuple[list[dict[str, str]], bool]:
        self._verify_wrapper()
        if not (1 <= limit <= 50):
            raise SnapshotUnavailable("history result limit must be 1..50")
        if not isinstance(ref, str) or not isinstance(path, str):
            raise SnapshotUnavailable("history ref and path must be strings")
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts:
            raise SnapshotUnavailable("history path escapes snapshot")
        oid = self.history_oid(ref)
        if _run(
            self.repo,
            ["cat-file", "-e", oid + "^{commit}"],
            check=False,
            git_env=self._git_env,
        ).returncode:
            raise SnapshotUnavailable("pinned history object is unavailable")
        raw = _run_bounded(
            self.repo,
            [
                "log",
                f"-{limit + 1}",
                "--format=%H%x00%ct%x00%s%x00",
                oid,
                "--",
                ":(literal)" + path,
            ],
            max_bytes=1 << 20,
            stop_after_nuls=(limit + 1) * 3,
            git_env=self._git_env,
            debit_bytes=debit_bytes,
            remaining_bytes=remaining_bytes,
        )
        tokens = raw.decode("utf-8", errors="replace").split("\0")
        rows = [
            {
                "commit": tokens[index].strip(),
                "timestamp": tokens[index + 1],
                "subject": tokens[index + 2].strip()[:500],
            }
            for index in range(0, len(tokens) - 2, 3)
            if tokens[index]
        ]
        return rows[:limit], len(rows) <= limit

    def history_oid(self, ref: str) -> str:
        if ref == "SNAPSHOT":
            return self.commit_id
        oid = self.history_refs.get(ref, "")
        if not oid:
            raise SnapshotContentUnavailable("history ref was not in the initial snapshot map")
        return oid
