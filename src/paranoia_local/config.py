"""Per-repo defaults from an optional `.paranoia.toml` at the repo root.

Lets a project stop retyping its `project_summary`, base ref, and review
defaults on every call. Keys may sit at the top level or under a `[paranoia]`
table. A missing, malformed, unsafe, or oversized file is not an error — it just
means no defaults. Closure-enabled plan verification deliberately does not call
this loader: repository bytes cannot select that mode's policy or instructions.
"""

from __future__ import annotations

import os
import stat
import tomllib
from pathlib import Path
from typing import Any

CONFIG_FILENAME = ".paranoia.toml"
MAX_CONFIG_BYTES = 64 * 1024


def _read_regular_nofollow(path: Path) -> bytes | None:
    """Read one bounded regular-file snapshot without following or blocking."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        return None
    flags = os.O_RDONLY | nofollow
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_CONFIG_BYTES:
            return None
        chunks: list[bytes] = []
        total = 0
        while total <= MAX_CONFIG_BYTES:
            chunk = os.read(fd, min(65536, MAX_CONFIG_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > MAX_CONFIG_BYTES:
            return None
        after = os.fstat(fd)
        before_identity = (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns,
        )
        if before_identity != after_identity or total != before.st_size:
            return None
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def load_repo_config(repo: Path) -> dict[str, Any]:
    path = repo / CONFIG_FILENAME
    raw = _read_regular_nofollow(path)
    if raw is None:
        return {}
    try:
        data = tomllib.loads(raw.decode("utf-8", errors="replace"))
    except tomllib.TOMLDecodeError:
        return {}
    if isinstance(data.get("paranoia"), dict):
        return data["paranoia"]
    return data


def resolve(key: str, explicit: Any, cfg: dict[str, Any], default: Any) -> Any:
    """Precedence: explicit call arg > repo config > hardcoded default."""
    if explicit is not None:
        return explicit
    if key in cfg and cfg[key] is not None:
        return cfg[key]
    return default
