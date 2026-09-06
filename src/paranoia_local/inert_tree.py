"""Materialize a pinned Git tree without checkout, filters, or executable links."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator

from . import inert_git, git_objects


@dataclass(frozen=True)
class MaterializedTree:
    root: Path
    repository: Path
    manifest: Path
    history: Path


@dataclass(frozen=True)
class EvidenceWorkspace:
    launch: Path
    tree: MaterializedTree

    def cwd_for(self, engine_name: str) -> Path:
        # Claude's Read/Grep/Glob tools do not traverse a directory symlink from
        # the disposable launch root. Its explicit read-only tool allowlist can
        # safely start at the inert root itself. Codex has shell reads, so it keeps
        # the launch-root symlink: /tmp exclusions then place evidence outside its
        # writable sandbox root while leaving the same bytes readable.
        return self.tree.root if engine_name == "claude" else self.launch


def _safe_path(raw: bytes) -> Path:
    text = raw.decode("utf-8", errors="surrogateescape")
    pure = PurePosixPath(text)
    if not text or pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise RuntimeError(f"unsafe Git tree path: {text!r}")
    return Path(*pure.parts)


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    kind: str
    oid: str
    raw_path: bytes
    size: int | None


def _entries(repo: Path, snapshot: str) -> list[TreeEntry]:
    output = inert_git.run(repo, ["ls-tree", "-rlz", "--full-tree", snapshot])
    entries: list[TreeEntry] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        meta, sep, path = record.partition(b"\t")
        fields = meta.decode("ascii").split()
        if not sep or len(fields) != 4:
            raise RuntimeError("malformed git ls-tree record")
        mode, kind, oid, raw_size = fields
        git_objects.validate_oid(oid)
        _safe_path(path)
        if kind == "blob":
            if not raw_size.isascii() or not raw_size.isdecimal():
                raise RuntimeError(f"invalid blob size for {oid}")
            size = int(raw_size)
        elif raw_size == "-":
            size = None
        else:
            raise RuntimeError(f"invalid non-blob size for {oid}")
        entries.append(TreeEntry(mode, kind, oid, path, size))
    return entries


def materialize(repo: Path, snapshot: str, root: Path) -> MaterializedTree:
    inert_git.require_supported_version()
    root.mkdir(parents=True, exist_ok=False)
    repository = root / "repository"
    repository.mkdir()
    manifest_rows: list[dict[str, str | int]] = []
    entries = _entries(repo, snapshot)
    blobs = git_objects.read_blobs(
        repo, (git_objects.BlobRequest(entry.oid, entry.size)
               for entry in entries if entry.kind == "blob" and entry.size is not None),
    )
    for entry in entries:
        mode, kind, oid, raw_path = entry.mode, entry.kind, entry.oid, entry.raw_path
        relative = _safe_path(raw_path)
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "blob":
            data = next(blobs)
            if mode == "120000":
                rendered = b"PARANOIA INERT SYMLINK TARGET\n" + data
                record_kind = "symlink"
            else:
                rendered = data
                record_kind = "executable" if mode == "100755" else "file"
            target.write_bytes(rendered)
            target.chmod(0o444)
            manifest_rows.append({
                "path": raw_path.decode("utf-8", errors="backslashreplace"),
                "kind": record_kind,
                "mode": mode,
                "oid": oid,
                "bytes": len(data),
            })
        elif kind == "commit" and mode == "160000":
            target.write_text(f"PARANOIA INERT GITLINK OID\n{oid}\n", encoding="ascii")
            target.chmod(0o444)
            manifest_rows.append({
                "path": raw_path.decode("utf-8", errors="backslashreplace"),
                "kind": "gitlink",
                "mode": mode,
                "oid": oid,
                "bytes": 0,
            })
        else:
            raise RuntimeError(f"unsupported tree entry {mode} {kind} at {relative}")

    manifest = root / "MANIFEST.json"
    manifest.write_text(
        json.dumps({"snapshot": snapshot, "entries": manifest_rows}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    history = root / "HISTORY.txt"
    history.write_text(
        inert_git.text(
            repo,
            [
                "log", "--no-patch", "--max-count=100",
                "--format=%H%x09%aI%x09%an%x09%s", snapshot,
            ],
        ),
        encoding="utf-8",
        errors="surrogateescape",
    )
    manifest.chmod(0o444)
    history.chmod(0o444)
    return MaterializedTree(root=root, repository=repository, manifest=manifest, history=history)


@contextmanager
def materialized(repo: Path, snapshot: str) -> Iterator[MaterializedTree]:
    parent = Path(tempfile.mkdtemp(prefix="paranoia-evidence-"))
    root = parent / "evidence"
    try:
        yield materialize(repo, snapshot, root)
    finally:
        shutil.rmtree(parent, ignore_errors=True)


@contextmanager
def evidence_workspace(repo: Path, snapshot: str) -> Iterator[EvidenceWorkspace]:
    parent = Path(tempfile.mkdtemp(prefix="paranoia-evidence-"))
    try:
        tree = materialize(repo, snapshot, parent / "evidence")
        launch = parent / "launch"
        launch.mkdir()
        (launch / "repository").symlink_to(tree.repository, target_is_directory=True)
        (launch / "EVIDENCE_MANIFEST.json").symlink_to(tree.manifest)
        (launch / "HISTORY.txt").symlink_to(tree.history)
        yield EvidenceWorkspace(launch=launch, tree=tree)
    finally:
        shutil.rmtree(parent, ignore_errors=True)
