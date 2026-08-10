"""Checked Git plumbing for evidence capture.

The reviewed repository may configure helpers.  Evidence paths therefore use one
small launcher which disables lazy object fetching and fsmonitor execution before
Git reads an index or object.  This is intentionally not a general Git wrapper.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Sequence


MIN_GIT_VERSION = (2, 36, 0)
_VERSION_RE = re.compile(r"git version (\d+)\.(\d+)(?:\.(\d+))?")


def environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    if extra:
        env.update(extra)
    return env


def argv(args: Sequence[str]) -> list[str]:
    return ["git", "-c", "core.fsmonitor=false", *args]


def run(
    repo: Path,
    args: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    extra_env: dict[str, str] | None = None,
) -> bytes:
    result = subprocess.run(
        argv(args),
        cwd=repo,
        env=environment(extra_env),
        input=input_bytes,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{' '.join(argv(args))} failed: {detail}")
    return result.stdout


def text(
    repo: Path,
    args: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    extra_env: dict[str, str] | None = None,
) -> str:
    return run(repo, args, input_bytes=input_bytes, extra_env=extra_env).decode(
        "utf-8", errors="surrogateescape"
    )


def installed_version(binary: str = "git") -> tuple[int, int, int]:
    result = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, env=environment()
    )
    if result.returncode != 0:
        raise RuntimeError(f"cannot run {binary} --version: {result.stderr.strip()}")
    match = _VERSION_RE.search(result.stdout)
    if not match:
        raise RuntimeError(f"cannot parse Git version from {result.stdout.strip()!r}")
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def require_supported_version(binary: str = "git") -> tuple[int, int, int]:
    version = installed_version(binary)
    if version < MIN_GIT_VERSION:
        needed = ".".join(str(part) for part in MIN_GIT_VERSION[:2])
        got = ".".join(str(part) for part in version)
        raise RuntimeError(
            f"evidence mode requires Git {needed} or newer (found {got}); upgrade Git"
        )
    return version
