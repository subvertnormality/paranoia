"""Content-addressed evidence storage with serialized roots and sweeping."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

DEFAULT_LINEAGE_CAP = 100 << 20
DEFAULT_GLOBAL_CAP = 1 << 30
DEFAULT_ORPHAN_TTL = 7 * 24 * 60 * 60
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class EvidenceStoreError(RuntimeError):
    pass


class EvidenceCommitAmbiguous(EvidenceStoreError):
    """State/root publication may have crossed its atomic replace boundary."""


def _name(value: str) -> str:
    rendered = _SAFE.sub("-", value).strip(".-")[:48] or "id"
    if rendered != value:
        rendered += "-" + hashlib.sha256(value.encode()).hexdigest()[:10]
    return rendered


class EvidenceStore:
    def __init__(self, root: Path, *, lineage_cap: int = DEFAULT_LINEAGE_CAP,
                 global_cap: int = DEFAULT_GLOBAL_CAP,
                 orphan_ttl_seconds: int = DEFAULT_ORPHAN_TTL) -> None:
        self.root = Path(root)
        self.blobs = self.root / "sha256"
        self.journals = self.root / "journals"
        self.roots = self.root / "roots"
        self.quarantine_dir = self.root / "quarantine"
        self.lock_path = self.root / "store.lock"
        self.lineage_cap = lineage_cap
        self.global_cap = global_cap
        self.orphan_ttl_seconds = orphan_ttl_seconds

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _journal(self, run_id: str) -> Path:
        return self.journals / f"{_name(run_id)}.json"

    def _root(self, lineage_id: str) -> Path:
        return self.roots / f"{_name(lineage_id)}.json"

    def begin(self, run_id: str, *, metadata: dict[str, Any] | None = None,
              now: float | None = None) -> None:
        """Durably root run metadata before snapshot refs or evidence can exist."""
        with self.locked():
            path = self._journal(run_id)
            if path.exists():
                raise EvidenceStoreError(f"in-flight journal already exists for {run_id}")
            self._atomic_json(path, {
                "run_id": run_id,
                "digests": [],
                "created_at": time.time() if now is None else now,
                "metadata": metadata or {},
            })

    def stage(self, run_id: str, data: bytes, *, now: float | None = None) -> str:
        digest = hashlib.sha256(data).hexdigest()
        with self.locked():
            self.blobs.mkdir(parents=True, exist_ok=True)
            target = self.blobs / digest
            if not target.exists():
                used = sum(path.stat().st_size for path in self.blobs.iterdir() if path.is_file())
                if used + len(data) > self.global_cap:
                    raise EvidenceStoreError("global evidence cap would be exceeded")
                self._atomic_bytes(target, data)
                if now is not None:
                    os.utime(target, (now, now))
            elif self.read(digest) != data:
                raise EvidenceStoreError("content-addressed evidence hash collision")
            journal_path = self._journal(run_id)
            journal = self._read_manifest(
                journal_path,
                missing={"run_id": run_id, "digests": [], "created_at": time.time(),
                         "metadata": {}},
            )
            if journal.get("run_id") != run_id:
                raise EvidenceStoreError("in-flight journal run identity mismatch")
            digests = list(dict.fromkeys([*journal.get("digests", []), digest]))
            self._atomic_json(journal_path, {**journal, "run_id": run_id, "digests": digests})
        return digest

    def read(self, digest: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise EvidenceStoreError("invalid evidence digest")
        path = self.blobs / digest
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise EvidenceStoreError(f"evidence blob {digest} is missing") from exc
        if hashlib.sha256(data).hexdigest() != digest:
            raise EvidenceStoreError(f"evidence blob {digest} hash mismatch")
        return data

    def adopt(self, lineage_id: str, run_id: str, digests: Sequence[str]) -> None:
        self.commit_state(lineage_id, run_id, digests, lambda: None)

    def commit_state(self, lineage_id: str, run_id: str, digests: Sequence[str],
                     state_writer: Callable[[], None]) -> None:
        """Publish candidate roots and lineage state under one global transaction lock.

        The journal and candidate both remain GC roots across any ambiguous failure.
        Callers must retain their lineage latch when this method raises.
        """
        with self.locked():
            journal = self._read_manifest(self._journal(run_id))
            staged = set(journal.get("digests", []))
            requested = list(dict.fromkeys(digests))
            existing = self._read_manifest(
                self._root(lineage_id), missing={"lineage_id": lineage_id, "digests": []}
            )
            previously_rooted = set(existing.get("digests", []))
            if any(digest not in staged and digest not in previously_rooted for digest in requested):
                raise EvidenceStoreError(
                    "cannot adopt evidence outside the journal or prior lineage root"
                )
            # The caller supplies the exact live reference set. Dropped/expired evidence
            # must stop charging the lineage cap and become collectible after its TTL.
            roots = requested
            size = sum(len(self.read(digest)) for digest in roots)
            if size > self.lineage_cap:
                raise EvidenceStoreError("lineage evidence cap would be exceeded")
            candidate = self.roots / f"{_name(lineage_id)}.candidate-{_name(run_id)}.json"
            self._atomic_json(candidate, {
                "lineage_id": lineage_id, "digests": roots,
            })
            try:
                state_writer()
                os.replace(candidate, self._root(lineage_id))
                self._fsync_dir(self.roots)
                self._journal(run_id).unlink(missing_ok=True)
                self._fsync_dir(self.journals)
            except BaseException as exc:
                raise EvidenceCommitAmbiguous(
                    "evidence/state commit is ambiguous; journal and candidate roots retained"
                ) from exc

    def abort(self, run_id: str) -> None:
        with self.locked():
            self._journal(run_id).unlink(missing_ok=True)
            self._fsync_dir(self.journals)

    def quarantine(self, lineage_id: str) -> None:
        """Keep its last strict root and record that only repair/abandon may remove it."""
        with self.locked():
            root = self._read_manifest(self._root(lineage_id))
            self._atomic_json(self.quarantine_dir / f"{_name(lineage_id)}.json", {
                "lineage_id": lineage_id, "root_digest": hashlib.sha256(
                    json.dumps(root, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            })

    def gc(self, *, now: float | None = None) -> list[str]:
        clock = time.time() if now is None else now
        with self.locked():
            marked: set[str] = set()
            # A malformed manifest aborts the sweep. Treating it as empty is the unsafe
            # quarantine bug this store exists to prevent.
            for directory in (self.roots, self.journals):
                if directory.exists():
                    for manifest in directory.glob("*.json"):
                        marked.update(self._read_manifest(manifest).get("digests", []))
            removed: list[str] = []
            if not self.blobs.exists():
                return removed
            for path in self.blobs.iterdir():
                if not path.is_file() or path.name in marked:
                    continue
                if clock - path.stat().st_mtime < self.orphan_ttl_seconds:
                    continue
                path.unlink()
                removed.append(path.name)
            if removed:
                self._fsync_dir(self.blobs)
            return removed

    @staticmethod
    def _atomic_bytes(path: Path, data: bytes) -> None:
        parent_existed = path.parent.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not parent_existed:
            EvidenceStore._fsync_dir(path.parent.parent)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
            EvidenceStore._fsync_dir(path.parent)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    @classmethod
    def _atomic_json(cls, path: Path, value: dict[str, Any]) -> None:
        cls._atomic_bytes(path, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())

    @staticmethod
    def _read_manifest(path: Path, *, missing: dict[str, Any] | None = None) -> dict[str, Any]:
        if not path.exists() and missing is not None:
            return missing
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvidenceStoreError(f"evidence manifest {path} is unavailable: {exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("digests"), list):
            raise EvidenceStoreError(f"evidence manifest {path} is malformed")
        if any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item)
               for item in raw["digests"]):
            raise EvidenceStoreError(f"evidence manifest {path} has invalid digests")
        return raw

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        if not path.exists():
            return
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
