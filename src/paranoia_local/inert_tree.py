"""Materialize a pinned Git tree without checkout, filters, or executable links."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator

from . import inert_git


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


def _git_oid(data: bytes, oid_length: int) -> str:
    algorithm = "sha1" if oid_length == 40 else "sha256" if oid_length == 64 else None
    if algorithm is None:
        raise RuntimeError(f"unsupported Git object id length: {oid_length}")
    digest = hashlib.new(algorithm)
    digest.update(f"blob {len(data)}\0".encode())
    digest.update(data)
    return digest.hexdigest()


def _safe_path(raw: bytes) -> Path:
    text = raw.decode("utf-8", errors="surrogateescape")
    pure = PurePosixPath(text)
    if not text or pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise RuntimeError(f"unsafe Git tree path: {text!r}")
    return Path(*pure.parts)


def _entries(repo: Path, snapshot: str) -> list[tuple[str, str, str, bytes]]:
    output = inert_git.run(repo, ["ls-tree", "-rz", "--full-tree", snapshot])
    entries: list[tuple[str, str, str, bytes]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        meta, sep, path = record.partition(b"\t")
        fields = meta.decode("ascii").split()
        if not sep or len(fields) != 3:
            raise RuntimeError("malformed git ls-tree record")
        mode, kind, oid = fields
        if len(oid) not in (40, 64) or any(c not in "0123456789abcdef" for c in oid):
            raise RuntimeError(f"invalid object id in ls-tree output: {oid!r}")
        _safe_path(path)
        entries.append((mode, kind, oid, path))
    return entries


def _blob(repo: Path, oid: str) -> bytes:
    kind = inert_git.text(repo, ["cat-file", "-t", oid]).strip()
    if kind != "blob":
        raise RuntimeError(f"expected blob {oid}, got {kind or 'no type'}")
    data = inert_git.run(repo, ["cat-file", "blob", oid])
    if _git_oid(data, len(oid)) != oid:
        raise RuntimeError(f"blob digest mismatch for {oid}")
    return data


def materialize(repo: Path, snapshot: str, root: Path) -> MaterializedTree:
    inert_git.require_supported_version()
    root.mkdir(parents=True, exist_ok=False)
    repository = root / "repository"
    repository.mkdir()
    manifest_rows: list[dict[str, str | int]] = []
    for mode, kind, oid, raw_path in _entries(repo, snapshot):
        relative = _safe_path(raw_path)
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "blob":
            data = _blob(repo, oid)
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
