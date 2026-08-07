"""Content-addressed evidence storage with serialized roots and sweeping."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import stat
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

DEFAULT_LINEAGE_CAP = 100 << 20
DEFAULT_GLOBAL_CAP = 1 << 30
DEFAULT_ORPHAN_TTL = 7 * 24 * 60 * 60
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_MANIFEST_BYTES = 8 << 20
MAX_MANIFEST_DIGESTS = 100_000
MAX_SNAPSHOT_REFS = 4096


class EvidenceStoreError(RuntimeError):
    pass


class EvidenceCommitAmbiguous(EvidenceStoreError):
    """State/root publication may have crossed its atomic replace boundary."""


def _name(value: str) -> str:
    rendered = _SAFE.sub("-", value).strip(".-")[:48] or "id"
    if rendered != value:
        rendered += "-" + hashlib.sha256(value.encode()).hexdigest()[:10]
    return rendered


def _identity(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\0" in value:
        raise EvidenceStoreError(f"evidence manifest {field} is invalid")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise EvidenceStoreError(f"evidence manifest {field} is invalid") from exc
    return value


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
        fd: int | None = None
        try:
            self._mkdir_durable(self.root)
            lock_existed = self.lock_path.exists()
            fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            if not lock_existed:
                self._fsync_dir(self.root)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        except OSError as exc:
            raise EvidenceStoreError(f"evidence store filesystem failure: {exc}") from exc
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                except OSError:
                    pass

    def _journal(self, run_id: str) -> Path:
        _identity(run_id, field="run_id")
        return self.journals / f"{_name(run_id)}.json"

    def _root(self, lineage_id: str) -> Path:
        _identity(lineage_id, field="lineage_id")
        return self.roots / f"{_name(lineage_id)}.json"

    def begin(self, run_id: str, *, metadata: dict[str, Any] | None = None,
              now: float | None = None) -> None:
        """Durably root run metadata before snapshot refs or evidence can exist."""
        with self.locked():
            path = self._journal(run_id)
            if path.exists():
                raise EvidenceStoreError(f"in-flight journal already exists for {run_id}")
            manifest = {
                "run_id": run_id,
                "digests": [],
                "created_at": time.time() if now is None else now,
                "metadata": metadata or {},
            }
            self._validate_journal(manifest, path=path, expected_run_id=run_id)
            self._atomic_json(path, manifest)

    def stage(self, run_id: str, data: bytes, *, now: float | None = None) -> str:
        digest = hashlib.sha256(data).hexdigest()
        with self.locked():
            self._mkdir_durable(self.blobs)
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
            journal = self._read_journal(
                journal_path,
                missing={"run_id": run_id, "digests": [], "created_at": time.time(),
                         "metadata": {}}, expected_run_id=run_id,
            )
            digests = list(journal["digests"])
            if digest not in digests:
                digests.append(digest)
            updated = {**journal, "run_id": run_id, "digests": digests}
            self._validate_journal(updated, path=journal_path, expected_run_id=run_id)
            self._atomic_json(journal_path, updated)
        return digest

    def read(self, digest: str, *, max_bytes: int | None = None) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise EvidenceStoreError("invalid evidence digest")
        if max_bytes is not None and (
            not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0
        ):
            raise EvidenceStoreError("invalid evidence read limit")
        path = self.blobs / digest
        fd: int | None = None
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) \
                    or (max_bytes is not None and before.st_size > max_bytes):
                raise EvidenceStoreError(f"evidence blob {digest} is unsafe or exceeds its limit")
            fd = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            )
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) \
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) \
                    or (max_bytes is not None and opened.st_size > max_bytes):
                raise EvidenceStoreError(f"evidence blob {digest} changed while opening")
            limit = opened.st_size if max_bytes is None else max_bytes
            chunks = bytearray()
            while len(chunks) <= limit:
                chunk = os.read(fd, min(65536, limit + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            if len(chunks) > limit:
                raise EvidenceStoreError(f"evidence blob {digest} exceeds its read limit")
            data = bytes(chunks)
        except OSError as exc:
            raise EvidenceStoreError(f"evidence blob {digest} is missing") from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if hashlib.sha256(data).hexdigest() != digest:
            raise EvidenceStoreError(f"evidence blob {digest} hash mismatch")
        return data

    def adopt(self, lineage_id: str, run_id: str, digests: Sequence[str]) -> None:
        self.commit_state(lineage_id, run_id, digests, lambda: None)

    def commit_state(self, lineage_id: str, run_id: str, digests: Sequence[str],
                     state_writer: Callable[[], None]) -> None:
        """Publish candidate roots and lineage state under one global transaction lock.

        The journal and available candidate roots remain GC roots across an ambiguous
        failure. A writer failure explicitly reported before its atomic replace is a
        normal store error, allowing callers to publish blocking debt and release their
        lineage latch. Callers retain the latch only for ambiguous publication.
        """
        with self.locked():
            journal = self._read_journal(
                self._journal(run_id), expected_run_id=run_id,
            )
            staged = set(journal["digests"])
            requested = list(dict.fromkeys(digests))
            existing = self._read_root_manifest(
                self._root(lineage_id), expected_lineage_id=lineage_id,
                missing={"lineage_id": lineage_id, "run_id": run_id, "digests": []},
            )
            previously_rooted = set(existing["digests"])
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
            root_manifest = {
                "lineage_id": lineage_id, "run_id": run_id, "digests": roots,
            }
            self._validate_root(
                root_manifest, path=candidate, expected_lineage_id=lineage_id,
                expected_run_id=run_id, candidate=True,
            )
            self._atomic_json(candidate, root_manifest)
            try:
                state_writer()
            except BaseException as exc:
                if getattr(exc, "publication_ambiguous", False):
                    raise EvidenceCommitAmbiguous(
                        "lineage state commit is ambiguous; recovery roots retained"
                    ) from exc
                try:
                    candidate.unlink(missing_ok=True)
                    self._fsync_dir(self.roots)
                except OSError:
                    # A stale candidate only retains extra evidence. The lineage state
                    # replace was never entered, so the state outcome remains known.
                    pass
                raise EvidenceStoreError(
                    "lineage state failed before atomic publication"
                ) from exc
            try:
                os.replace(candidate, self._root(lineage_id))
                self._fsync_dir(self.roots)
                self._journal(run_id).unlink(missing_ok=True)
                self._fsync_dir(self.journals)
            except BaseException as exc:
                raise EvidenceCommitAmbiguous(
                    "evidence-root commit is ambiguous; available recovery roots retained"
                ) from exc

    def abort(self, run_id: str) -> None:
        with self.locked():
            self._journal(run_id).unlink(missing_ok=True)
            self._fsync_dir(self.journals)

    def quarantine(self, lineage_id: str) -> None:
        """Keep its last strict root and record that only repair/abandon may remove it."""
        with self.locked():
            root = self._read_root_manifest(
                self._root(lineage_id), expected_lineage_id=lineage_id,
            )
            quarantine_path = self.quarantine_dir / f"{_name(lineage_id)}.json"
            quarantine = {
                "lineage_id": lineage_id, "root_digest": hashlib.sha256(
                    json.dumps(root, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            }
            self._validate_quarantine(
                quarantine, path=quarantine_path, expected_lineage_id=lineage_id,
            )
            self._atomic_json(quarantine_path, quarantine)

    def gc(self, *, now: float | None = None) -> list[str]:
        clock = time.time() if now is None else now
        with self.locked():
            marked: set[str] = set()
            # A malformed manifest aborts the sweep. Treating it as empty is the unsafe
            # quarantine bug this store exists to prevent.
            if self.roots.exists():
                for manifest in self.roots.glob("*.json"):
                    marked.update(self._read_root_manifest(manifest)["digests"])
            if self.journals.exists():
                for manifest in self.journals.glob("*.json"):
                    marked.update(self._read_journal(manifest)["digests"])
            if self.quarantine_dir.exists():
                for manifest in self.quarantine_dir.glob("*.json"):
                    self._read_quarantine(manifest)
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
        tmp: str | None = None
        try:
            EvidenceStore._mkdir_durable(path.parent)
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
            EvidenceStore._fsync_dir(path.parent)
        except OSError as exc:
            raise EvidenceStoreError(f"could not publish evidence file: {exc}") from exc
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise EvidenceStoreError(
                        f"could not clean evidence temporary file: {exc}"
                    ) from exc

    @classmethod
    def _atomic_json(cls, path: Path, value: dict[str, Any]) -> None:
        cls._atomic_bytes(path, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())

    @staticmethod
    def _read_json_manifest(
        path: Path, *, missing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fd: int | None = None
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_MANIFEST_BYTES:
                raise EvidenceStoreError(f"evidence manifest {path} is unsafe or oversized")
            fd = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
            )
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) \
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) \
                    or opened.st_size > MAX_MANIFEST_BYTES:
                raise EvidenceStoreError(f"evidence manifest {path} changed while opening")
            chunks = bytearray()
            while len(chunks) <= MAX_MANIFEST_BYTES:
                chunk = os.read(fd, min(65536, MAX_MANIFEST_BYTES + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            if len(chunks) > MAX_MANIFEST_BYTES:
                raise EvidenceStoreError(f"evidence manifest {path} exceeds its byte cap")
            raw = json.loads(bytes(chunks).decode("utf-8", errors="strict"))
        except FileNotFoundError:
            if missing is not None:
                return missing
            raise EvidenceStoreError(f"evidence manifest {path} is unavailable") from None
        except EvidenceStoreError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise EvidenceStoreError(f"evidence manifest {path} is unavailable: {exc}") from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if not isinstance(raw, dict):
            raise EvidenceStoreError(f"evidence manifest {path} is malformed")
        return raw

    @staticmethod
    def _validate_digests(raw: object, *, path: Path) -> list[str]:
        if not isinstance(raw, list) or len(raw) > MAX_MANIFEST_DIGESTS:
            raise EvidenceStoreError(f"evidence manifest {path} has invalid digests")
        if any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item)
               for item in raw) or len(set(raw)) != len(raw):
            raise EvidenceStoreError(f"evidence manifest {path} has invalid digests")
        return raw

    @staticmethod
    def _validate_metadata(raw: object, *, path: Path) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise EvidenceStoreError(f"evidence manifest {path} has invalid metadata")
        if not raw:
            return raw
        keys = set(raw)
        if keys not in ({"repo", "lineage"}, {"repo", "lineage", "snapshot_refs"}):
            raise EvidenceStoreError(f"evidence manifest {path} has invalid metadata")
        repo = raw["repo"]
        lineage = raw["lineage"]
        if not isinstance(repo, str) or not repo or len(repo) > 4096 or "\0" in repo:
            raise EvidenceStoreError(f"evidence manifest {path} has invalid repository metadata")
        try:
            repo.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise EvidenceStoreError(
                f"evidence manifest {path} has invalid repository metadata"
            ) from exc
        _identity(lineage, field="metadata.lineage")
        # schema-v1 journals carried native snapshot refs. New ephemeral snapshots own
        # no repository refs, but old recovery journals remain readable.
        refs = raw.get("snapshot_refs", [])
        if not isinstance(refs, list) or len(refs) > MAX_SNAPSHOT_REFS:
            raise EvidenceStoreError(f"evidence manifest {path} has invalid snapshot refs")
        names: set[str] = set()
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"name", "oid"}:
                raise EvidenceStoreError(f"evidence manifest {path} has invalid snapshot refs")
            name, oid = ref["name"], ref["oid"]
            if not isinstance(name, str) or not name.startswith(
                "refs/paranoia/plan-snapshots/"
            ) or len(name) > 1024 or "\0" in name or name in names:
                raise EvidenceStoreError(f"evidence manifest {path} has invalid snapshot refs")
            try:
                name.encode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise EvidenceStoreError(
                    f"evidence manifest {path} has invalid snapshot refs"
                ) from exc
            if not isinstance(oid, str) or not re.fullmatch(
                r"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid
            ):
                raise EvidenceStoreError(f"evidence manifest {path} has invalid snapshot refs")
            names.add(name)
        return raw

    @classmethod
    def _validate_journal(
        cls, raw: dict[str, Any], *, path: Path, expected_run_id: str | None = None,
    ) -> dict[str, Any]:
        if set(raw) != {"run_id", "digests", "created_at", "metadata"}:
            raise EvidenceStoreError(f"evidence journal {path} has an invalid schema")
        run_id = _identity(raw["run_id"], field="run_id")
        if expected_run_id is not None and run_id != expected_run_id:
            raise EvidenceStoreError("in-flight journal run identity mismatch")
        if path.name != f"{_name(run_id)}.json":
            raise EvidenceStoreError(f"evidence journal {path} has a filename identity mismatch")
        created_at = raw["created_at"]
        if isinstance(created_at, bool) or not isinstance(created_at, (int, float)) \
                or not math.isfinite(created_at) or created_at < 0:
            raise EvidenceStoreError(f"evidence journal {path} has an invalid timestamp")
        cls._validate_digests(raw["digests"], path=path)
        cls._validate_metadata(raw["metadata"], path=path)
        return raw

    @classmethod
    def _read_journal(
        cls, path: Path, *, missing: dict[str, Any] | None = None,
        expected_run_id: str | None = None,
    ) -> dict[str, Any]:
        raw = cls._read_json_manifest(path, missing=missing)
        return cls._validate_journal(raw, path=path, expected_run_id=expected_run_id)

    @classmethod
    def _validate_root(
        cls, raw: dict[str, Any], *, path: Path,
        expected_lineage_id: str | None = None, expected_run_id: str | None = None,
        candidate: bool | None = None,
    ) -> dict[str, Any]:
        if set(raw) != {"lineage_id", "run_id", "digests"}:
            raise EvidenceStoreError(f"evidence root {path} has an invalid schema")
        lineage_id = _identity(raw["lineage_id"], field="lineage_id")
        run_id = _identity(raw["run_id"], field="run_id")
        if expected_lineage_id is not None and lineage_id != expected_lineage_id:
            raise EvidenceStoreError("evidence root lineage identity mismatch")
        if expected_run_id is not None and run_id != expected_run_id:
            raise EvidenceStoreError("evidence root run identity mismatch")
        if candidate is None:
            is_candidate = path.name != f"{_name(lineage_id)}.json"
        else:
            is_candidate = candidate
        expected_name = (
            f"{_name(lineage_id)}.candidate-{_name(run_id)}.json"
            if is_candidate else f"{_name(lineage_id)}.json"
        )
        if path.name != expected_name:
            raise EvidenceStoreError(f"evidence root {path} has a filename identity mismatch")
        cls._validate_digests(raw["digests"], path=path)
        return raw

    @classmethod
    def _read_root_manifest(
        cls, path: Path, *, missing: dict[str, Any] | None = None,
        expected_lineage_id: str | None = None,
    ) -> dict[str, Any]:
        raw = cls._read_json_manifest(path, missing=missing)
        return cls._validate_root(
            raw, path=path, expected_lineage_id=expected_lineage_id,
        )

    @staticmethod
    def _validate_quarantine(
        raw: dict[str, Any], *, path: Path, expected_lineage_id: str | None = None,
    ) -> dict[str, Any]:
        if set(raw) != {"lineage_id", "root_digest"}:
            raise EvidenceStoreError(f"evidence quarantine {path} has an invalid schema")
        lineage_id = _identity(raw["lineage_id"], field="lineage_id")
        if expected_lineage_id is not None and lineage_id != expected_lineage_id:
            raise EvidenceStoreError("evidence quarantine lineage identity mismatch")
        if path.name != f"{_name(lineage_id)}.json" or not isinstance(
            raw["root_digest"], str
        ) or not re.fullmatch(r"[0-9a-f]{64}", raw["root_digest"]):
            raise EvidenceStoreError(f"evidence quarantine {path} is malformed")
        return raw

    @classmethod
    def _read_quarantine(cls, path: Path) -> dict[str, Any]:
        return cls._validate_quarantine(cls._read_json_manifest(path), path=path)

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        if not path.exists():
            return
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _mkdir_durable(path: Path) -> None:
        missing: list[Path] = []
        cursor = path
        while not cursor.exists():
            missing.append(cursor)
            if cursor.parent == cursor:
                break
            cursor = cursor.parent
        path.mkdir(parents=True, exist_ok=True)
        for created in reversed(missing):
            EvidenceStore._fsync_dir(created.parent)
