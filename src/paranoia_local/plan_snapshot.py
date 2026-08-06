"""Pinned, server-only repository reads for plan claim verification."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

MAX_PINNED_REFS = 1024
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


class SnapshotUnavailable(RuntimeError):
    pass


class SnapshotCleanupError(SnapshotUnavailable):
    """Temporary refs may remain; the journal/latch must be retained for repair."""


def _run(repo: Path, args: list[str], *, input_bytes: bytes | None = None,
         check: bool = True,
         extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    ambient = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    result = subprocess.run(
        ["git", *_GIT_CONFIG, *args], cwd=repo, input=input_bytes, capture_output=True,
        env={**ambient, **_GIT_ENV, **(extra_env or {})},
    )
    if check and result.returncode:
        raise SnapshotUnavailable(
            f"git {' '.join(args[:2])} failed: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result


def _run_bounded(
    repo: Path, args: list[str], *, max_bytes: int, stop_after_nuls: int,
    debit_bytes: Callable[[int], None] | None = None,
) -> bytes:
    """Read bounded Git output and terminate once complete records reach the limit."""
    ambient = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    proc = subprocess.Popen(
        ["git", *_GIT_CONFIG, *args], cwd=repo, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env={**ambient, **_GIT_ENV},
    )
    output = bytearray()
    try:
        assert proc.stdout is not None
        while output.count(b"\0") < stop_after_nuls:
            remaining = max_bytes - len(output)
            if remaining <= 0:
                raise SnapshotUnavailable("bounded Git output exceeds byte cap")
            chunk = proc.stdout.read(min(65536, remaining + 1))
            if not chunk:
                break
            if debit_bytes is not None:
                debit_bytes(len(chunk))
            output.extend(chunk)
            if len(output) > max_bytes:
                raise SnapshotUnavailable("bounded Git output exceeds byte cap")
        if output.count(b"\0") >= stop_after_nuls:
            proc.terminate()
        returncode = proc.wait(timeout=10)
        if returncode not in {0, -15}:
            raise SnapshotUnavailable("bounded Git command failed")
        return bytes(output)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def _ref_token(run_id: str) -> str:
    safe = _SAFE.sub("-", run_id).strip(".-")[:48] or "run"
    digest = hashlib.sha256(run_id.encode()).hexdigest()[:12]
    return f"{safe}-{digest}"


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
    _owned_refs: list[tuple[str, str]] = field(default_factory=list, repr=False)
    _closed: bool = field(default=False, repr=False)

    @classmethod
    def create(
        cls, repo: Path, *, run_id: str,
        before_pin: Callable[[list[tuple[str, str]]], None] | None = None,
    ) -> "PlanRepositorySnapshot":
        repo = Path(repo).resolve()
        _validate_object_boundary(repo)
        head_result = _run(repo, ["rev-parse", "--verify", "--quiet", "HEAD"], check=False)
        has_head = head_result.returncode == 0
        head = (
            head_result.stdout.decode("ascii").strip()
            if has_head
            else _run(
                repo, ["hash-object", "-t", "tree", "--stdin"], input_bytes=b""
            ).stdout.decode("ascii").strip()
        )
        ignored_raw = _run(
            repo, ["ls-files", "--others", "-i", "--exclude-standard", "--directory", "-z"]
        ).stdout
        ignored = tuple(
            item.decode("utf-8", errors="surrogateescape")
            for item in ignored_raw.split(b"\0") if item
        )
        tree, unavailable = _snapshot_tree_without_filters(repo)
        unavailable = tuple(dict.fromkeys([
            *unavailable, *_find_special_paths(repo, ignored_paths=ignored)
        ]))
        commit_args = ["commit-tree", "--no-gpg-sign", tree]
        if has_head:
            commit_args += ["-p", head]
        commit_args += ["-m", "paranoia-plan-snapshot"]
        commit = _run(
            repo, commit_args, extra_env=_SNAPSHOT_IDENTITY
        ).stdout.decode("ascii").strip()
        token = _ref_token(run_id)
        wrapper_ref = f"refs/paranoia/plan-snapshots/{token}/wrapper"
        raw_refs = _run(
            repo, ["for-each-ref", "--format=%(refname)%00%(objectname)", "refs/"]
        ).stdout.decode("utf-8", errors="surrogateescape")
        history: dict[str, str] = {}
        for line in raw_refs.splitlines():
            if "\0" not in line:
                continue
            name, oid = line.split("\0", 1)
            if name.startswith(("refs/paranoia/plan-snapshots/", "refs/replace/")):
                continue
            history[name] = oid.strip()
        if len(history) + 1 > MAX_PINNED_REFS:
            raise SnapshotUnavailable(
                f"repository has {len(history)} refs; plan snapshot cap is {MAX_PINNED_REFS - 1}"
            )
        owned: list[tuple[str, str]] = [(wrapper_ref, commit)]
        for index, (name, oid) in enumerate(sorted(history.items()), 1):
            suffix = hashlib.sha256(name.encode("utf-8", errors="surrogateescape")).hexdigest()[:16]
            owned.append((f"refs/paranoia/plan-snapshots/{token}/history-{index:04d}-{suffix}", oid))
        if before_pin is not None:
            before_pin(owned)
        cls._create_refs(repo, owned)
        return cls(
            repo, head, tree, commit, wrapper_ref, history, ignored,
            unavailable, owned,
        )

    @staticmethod
    def _create_refs(repo: Path, refs: list[tuple[str, str]]) -> None:
        commands = ["start"] + [f"create {name} {oid}" for name, oid in refs] + ["prepare", "commit"]
        _run(repo, ["update-ref", "--stdin"], input_bytes=("\n".join(commands) + "\n").encode())

    def __enter__(self) -> "PlanRepositorySnapshot":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        failures: list[str] = []
        for name, oid in self._owned_refs:
            current = _run(self.repo, ["rev-parse", "--verify", name], check=False)
            if current.returncode:
                continue
            if current.stdout.decode("ascii").strip() != oid:
                failures.append(f"{name} changed owner")
                continue
            result = _run(self.repo, ["update-ref", "-d", name, oid], check=False)
            if result.returncode:
                failures.append(
                    f"{name}: " + result.stderr.decode("utf-8", errors="replace").strip()
                )
        if failures:
            raise SnapshotCleanupError(
                "could not delete temporary snapshot refs: " + "; ".join(failures)
            )
        self._closed = True

    def _verify_wrapper(self) -> None:
        _validate_object_boundary(self.repo)
        result = _run(self.repo, ["rev-parse", "--verify", self.wrapper_ref + "^{commit}"],
                      check=False)
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
        out = _run(
            self.repo, ["ls-tree", "-z", self.commit_id, "--", literal]
        ).stdout
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
        size_raw = _run(self.repo, ["cat-file", "-s", oid]).stdout.decode("ascii").strip()
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
            env={**ambient, **_GIT_ENV},
        )
        assert proc.stdout is not None
        result = bytearray()
        skipped = 0
        try:
            while skipped < offset:
                chunk = proc.stdout.read(min(65536, offset - skipped))
                if not chunk:
                    raise SnapshotUnavailable("repository blob ended before requested offset")
                skipped += len(chunk)
            while len(result) < wanted:
                chunk = proc.stdout.read(min(65536, wanted - len(result)))
                if not chunk:
                    break
                result.extend(chunk)
            if offset + wanted == size:
                returncode = proc.wait(timeout=10)
                if returncode:
                    stderr = proc.stderr.read() if proc.stderr else b""
                    raise SnapshotUnavailable(
                        "git cat-file failed: "
                        + stderr.decode("utf-8", errors="replace").strip()
                    )
            else:
                proc.terminate()
                proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        return bytes(result)

    def list_tree(
        self, prefix: str = "", *, limit: int = 200,
        debit_bytes: Callable[[int], None] | None = None,
    ) -> list[str]:
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
            self.repo, args, max_bytes=1 << 20, stop_after_nuls=limit,
            debit_bytes=debit_bytes,
        ).split(b"\0")
        return [r.decode("utf-8", errors="surrogateescape") for r in rows if r][:limit]

    def search_literal(self, pattern: str, *, paths: list[str] | None = None,
                       limit: int = 50,
                       debit_bytes: Callable[[int], None] | None = None
                       ) -> list[dict[str, object]]:
        if not isinstance(pattern, str) or not pattern or len(pattern.encode()) > 256 \
                or not (1 <= limit <= 50):
            raise SnapshotUnavailable("literal search exceeds bounds")
        results: list[dict[str, object]] = []
        candidates = paths or self.list_tree(limit=200, debit_bytes=debit_bytes)
        if any(not isinstance(path, str) for path in candidates):
            raise SnapshotUnavailable("literal search paths must be strings")
        for path in candidates[:200]:
            try:
                _oid, source_size = self.blob_identity(path)
                inspected = min(source_size, 1 << 20)
                if debit_bytes is not None:
                    debit_bytes(inspected)
                data = self.read_blob(path, max_bytes=max(1, inspected))
            except SnapshotUnavailable:
                continue
            start = 0
            needle = pattern.encode("utf-8")
            while len(results) < limit:
                offset = data.find(needle, start)
                if offset < 0:
                    break
                line = data.count(b"\n", 0, offset) + 1
                results.append({"path": path, "byte": offset, "line": line})
                start = offset + max(1, len(needle))
            if len(results) >= limit:
                break
        return results

    def history(
        self, ref: str, path: str, *, limit: int = 20,
        debit_bytes: Callable[[int], None] | None = None,
    ) -> list[dict[str, str]]:
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
        exists = _run(self.repo, ["cat-file", "-e", oid + "^{commit}"], check=False)
        if exists.returncode:
            raise SnapshotUnavailable("pinned history object is missing")
        output = _run_bounded(
            self.repo,
            ["log", f"-{limit}", "--format=%H%x00%ct%x00%s%x00", oid, "--",
             ":(literal)" + path],
            max_bytes=1 << 20, stop_after_nuls=limit * 3,
            debit_bytes=debit_bytes,
        )
        tokens = output.decode("utf-8", errors="replace").split("\0")
        rows: list[dict[str, str]] = []
        for index in range(0, len(tokens) - 2, 3):
            commit, timestamp, subject = tokens[index:index + 3]
            if commit:
                rows.append({"commit": commit.strip(), "timestamp": timestamp,
                             "subject": subject.strip()[:500]})
        return rows

    def history_oid(self, ref: str) -> str:
        if ref == "SNAPSHOT":
            return self.commit_id
        oid = self.history_refs.get(ref, "")
        if not oid:
            raise SnapshotUnavailable("history ref was not in the initial pinned map")
        return oid



def _snapshot_tree_without_filters(repo: Path) -> tuple[str, tuple[str, ...]]:
    """Hash working-tree bytes without ``git add`` or repository-selected commands.

    Git supplies only the candidate path set and object database. File bytes are opened
    with ``O_NOFOLLOW``, hashed through stdin (which bypasses clean filters), and inserted
    into a private index with explicit modes/object IDs. Repository hooks, fsmonitor,
    attributes, filters, pagers, and aliases therefore cannot select an executable step.
    """
    cached = _run(repo, ["ls-files", "-s", "-z"]).stdout
    index_entries: dict[str, tuple[str, str]] = {}
    for row in [item for item in cached.split(b"\0") if item]:
        meta, sep, raw_path = row.partition(b"\t")
        fields = meta.decode("ascii", errors="strict").split()
        if not sep or len(fields) != 3:
            raise SnapshotUnavailable("git index entry was malformed")
        mode, oid, stage = fields
        if stage == "0":
            index_entries[raw_path.decode("utf-8", errors="surrogateescape")] = (mode, oid)

    candidates = _run(
        repo, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    ).stdout
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
            oid = _run(repo, ["hash-object", "-w", "--stdin"], input_bytes=body).stdout.decode().strip()
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
                proc = subprocess.run(
                    ["git", *_GIT_CONFIG, "hash-object", "-w", "--stdin"],
                    cwd=repo, stdin=handle, capture_output=True,
                    env={**ambient, **_GIT_ENV},
                )
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
        _run(repo, ["read-tree", "--empty"], extra_env=private_env)
        payload = b"".join(
            f"{mode} {oid}\t".encode("ascii")
            + path.encode("utf-8", errors="surrogateescape") + b"\0"
            for mode, oid, path in sorted(
                rows, key=lambda item: item[2].encode("utf-8", "surrogateescape")
            )
        )
        _run(
            repo, ["update-index", "-z", "--index-info"],
            input_bytes=payload, extra_env=private_env,
        )
        tree = _run(repo, ["write-tree"], extra_env=private_env).stdout.decode("ascii").strip()
        return tree, tuple(unavailable)
    finally:
        import shutil
        shutil.rmtree(index_dir, ignore_errors=True)


def _validate_object_boundary(repo: Path) -> None:
    approved = _approved_common_dir(repo)
    common_raw = _run(repo, ["rev-parse", "--git-common-dir"]).stdout.decode(
        "utf-8", errors="surrogateescape"
    ).strip()
    common = Path(common_raw)
    if not common.is_absolute():
        common = (repo / common).resolve()
    else:
        common = common.resolve()
    if common != approved:
        raise SnapshotUnavailable("Git common directory is outside the approved repository boundary")
    objects = common / "objects"
    _validate_object_store_paths(objects)
    for name in ("alternates", "http-alternates"):
        path = objects / "info" / name
        try:
            if path.is_symlink() or (path.exists() and path.read_bytes().strip()):
                raise SnapshotUnavailable(
                    f"repository object alternates are outside the approved snapshot boundary: {path}"
                )
        except OSError as exc:
            raise SnapshotUnavailable(f"could not validate object alternates at {path}: {exc}") from exc


def _approved_common_dir(repo: Path) -> Path:
    dotgit = repo / ".git"
    if dotgit.is_symlink():
        raise SnapshotUnavailable("repository .git may not be a symlink")
    if dotgit.is_dir():
        return dotgit.resolve()
    try:
        marker = dotgit.read_text(encoding="utf-8", errors="strict").strip()
    except (OSError, UnicodeError) as exc:
        raise SnapshotUnavailable(f"repository gitfile is unavailable: {exc}") from exc
    if len(marker) > 4096 or not marker.startswith("gitdir: "):
        raise SnapshotUnavailable("repository gitfile is malformed")
    git_dir = Path(marker[8:])
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve()
    else:
        git_dir = git_dir.resolve()
    try:
        common_marker = (git_dir / "commondir").read_text(encoding="utf-8").strip()
        backlink = (git_dir / "gitdir").read_text(encoding="utf-8").strip()
    except OSError as exc:
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
    return common


def _validate_object_store_paths(objects: Path, *, max_entries: int = 200_000) -> None:
    if objects.is_symlink() or not objects.is_dir():
        raise SnapshotUnavailable("repository object-store root must be a real directory")
    pending = [objects]
    seen = 0
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise SnapshotUnavailable(f"could not inspect repository object store: {exc}") from exc
        for entry in entries:
            seen += 1
            if seen > max_entries:
                raise SnapshotUnavailable("repository object-store metadata scan exceeds safety cap")
            if entry.is_symlink():
                raise SnapshotUnavailable(
                    f"repository object-store path may not be a symlink: {entry.path}"
                )
            if entry.is_dir(follow_symlinks=False):
                pending.append(Path(entry.path))


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
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise SnapshotUnavailable(f"could not inspect repository entry types: {exc}") from exc
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
                special.append(
                    relative
                )
    return tuple(sorted(special))
