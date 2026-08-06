"""Pinned, server-only repository reads for plan claim verification."""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

from . import orientation

MAX_PINNED_REFS = 1024
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_OPTIONAL_LOCKS": "0",
}


class SnapshotUnavailable(RuntimeError):
    pass


def _run(repo: Path, args: list[str], *, input_bytes: bytes | None = None,
         check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args], cwd=repo, input=input_bytes, capture_output=True,
        env={**os.environ, **_GIT_ENV},
    )
    if check and result.returncode:
        raise SnapshotUnavailable(
            f"git {' '.join(args[:2])} failed: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result


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
    _owned_refs: list[tuple[str, str]] = field(default_factory=list, repr=False)
    _closed: bool = field(default=False, repr=False)

    @classmethod
    def create(
        cls, repo: Path, *, run_id: str,
        before_pin: Callable[[list[tuple[str, str]]], None] | None = None,
    ) -> "PlanRepositorySnapshot":
        repo = Path(repo).resolve()
        has_head = orientation.has_head(repo)
        head = orientation.resolve_head(repo) if has_head else orientation.empty_tree(repo)
        ignored_raw = _run(
            repo, ["ls-files", "--others", "-i", "--exclude-standard", "-z"]
        ).stdout
        ignored = tuple(
            item.decode("utf-8", errors="surrogateescape")
            for item in ignored_raw.split(b"\0") if item
        )
        tree = orientation.snapshot_tree(repo, head)
        commit = orientation.wrap_commit(
            repo, tree, head if has_head else None, "paranoia-plan-snapshot"
        )
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
            if name.startswith("refs/paranoia/plan-snapshots/"):
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
        snapshot = cls(repo, head, tree, commit, wrapper_ref, history, ignored, owned)
        try:
            snapshot._reject_escaping_symlinks()
        except BaseException:
            snapshot.close()
            raise
        return snapshot

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
        # Supply the old OID so a foreign replacement is never deleted as if we owned it.
        commands = [f"delete {name} {oid}" for name, oid in self._owned_refs]
        if commands:
            _run(self.repo, ["update-ref", "--stdin"],
                 input_bytes=("\n".join(commands) + "\n").encode(), check=False)
        self._closed = True

    def _verify_wrapper(self) -> None:
        result = _run(self.repo, ["rev-parse", "--verify", self.wrapper_ref + "^{commit}"],
                      check=False)
        actual = result.stdout.decode().strip() if result.returncode == 0 else ""
        if actual != self.commit_id:
            raise SnapshotUnavailable("pinned snapshot object/ref is missing or changed")

    def _entry(self, path: str) -> tuple[str, str, str]:
        self._verify_wrapper()
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

    def read_blob(self, path: str, *, max_bytes: int = 1 << 20) -> bytes:
        mode, kind, oid = self._entry(path)
        if mode == "120000":
            raise SnapshotUnavailable("symlink paths are not repository evidence blobs")
        if mode == "160000" or kind == "commit":
            raise SnapshotUnavailable("gitlinks are unavailable without a supplied artifact")
        if kind != "blob":
            raise SnapshotUnavailable("repository evidence path is not a blob")
        data = _run(self.repo, ["cat-file", "blob", oid]).stdout
        if len(data) > max_bytes:
            raise SnapshotUnavailable(f"repository blob exceeds {max_bytes} bytes")
        return data

    def list_tree(self, prefix: str = "", *, limit: int = 200) -> list[str]:
        self._verify_wrapper()
        if limit < 1 or limit > 200:
            raise SnapshotUnavailable("tree result limit must be 1..200")
        args = ["ls-tree", "-r", "-z", "--name-only", self.commit_id]
        if prefix:
            pure = PurePosixPath(prefix)
            if pure.is_absolute() or ".." in pure.parts:
                raise SnapshotUnavailable("tree prefix escapes snapshot")
            args += ["--", ":(literal)" + prefix]
        rows = _run(self.repo, args).stdout.split(b"\0")
        return [r.decode("utf-8", errors="surrogateescape") for r in rows if r][:limit]

    def search_literal(self, pattern: str, *, paths: list[str] | None = None,
                       limit: int = 50) -> list[dict[str, object]]:
        if not pattern or len(pattern.encode()) > 256 or not (1 <= limit <= 50):
            raise SnapshotUnavailable("literal search exceeds bounds")
        results: list[dict[str, object]] = []
        candidates = paths or self.list_tree(limit=200)
        for path in candidates[:200]:
            try:
                data = self.read_blob(path, max_bytes=1 << 20)
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

    def history(self, ref: str, path: str, *, limit: int = 20) -> list[dict[str, str]]:
        """Read only commits reachable from the initial pinned ref map."""
        self._verify_wrapper()
        if not (1 <= limit <= 50):
            raise SnapshotUnavailable("history result limit must be 1..50")
        if ref == "SNAPSHOT":
            oid = self.commit_id
        else:
            oid = self.history_refs.get(ref, "")
            if not oid:
                raise SnapshotUnavailable("history ref was not in the initial pinned map")
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts:
            raise SnapshotUnavailable("history path escapes snapshot")
        exists = _run(self.repo, ["cat-file", "-e", oid + "^{commit}"], check=False)
        if exists.returncode:
            raise SnapshotUnavailable("pinned history object is missing")
        output = _run(
            self.repo,
            ["log", f"-{limit}", "--format=%H%x00%ct%x00%s%x00", oid, "--",
             ":(literal)" + path],
        ).stdout
        tokens = output.decode("utf-8", errors="replace").split("\0")
        rows: list[dict[str, str]] = []
        for index in range(0, len(tokens) - 2, 3):
            commit, timestamp, subject = tokens[index:index + 3]
            if commit:
                rows.append({"commit": commit.strip(), "timestamp": timestamp,
                             "subject": subject.strip()[:500]})
        return rows

    def _reject_escaping_symlinks(self) -> None:
        out = _run(self.repo, ["ls-tree", "-r", "-z", self.commit_id]).stdout
        for row in [item for item in out.split(b"\0") if item]:
            meta, _, raw_path = row.partition(b"\t")
            mode, kind, oid = meta.decode("ascii").split()
            if mode != "120000" or kind != "blob":
                continue
            path = raw_path.decode("utf-8", errors="surrogateescape")
            target = _run(self.repo, ["cat-file", "blob", oid]).stdout.decode(
                "utf-8", errors="surrogateescape"
            )
            if target.startswith("/"):
                raise SnapshotUnavailable(f"escaping symlink in snapshot: {path}")
            combined = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
            if combined == ".." or combined.startswith("../"):
                raise SnapshotUnavailable(f"escaping symlink in snapshot: {path}")
