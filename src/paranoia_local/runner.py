"""Bounded subprocess execution shared by capture and progress-streaming routes."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_TIMEOUT_SEC = 7200
TEARDOWN_TIMEOUT_SEC = 2


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def _stop(proc: subprocess.Popen) -> None:
    """Kill the launched process group, including ordinary pipe-holding children."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            # Windows does not offer POSIX process-group termination. Bound the
            # native tree-kill command as well as the subsequent pipe teardown.
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, timeout=TEARDOWN_TIMEOUT_SEC,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass


def run_capture(
    argv: list[str], stdin_text: str, cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> RunResult:
    return run_streaming(argv, stdin_text, cwd, timeout)


def run_streaming(
    argv: list[str], stdin_text: str, cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    on_line: Callable[[str], None] | None = None,
) -> RunResult:
    """Read all three pipes concurrently under one deadline.

    Timeout remains rc 124 with empty stdout; unavailable executable remains 127.
    A failed pipe worker is rc 65, never successful provider output. Progress
    callback exceptions are advisory. Cancellation kills the process tree and
    re-raises. Teardown waits at most two seconds (four on Windows including
    taskkill); daemonized/escaped descendants are outside the supported model.
    """
    stdin_text.encode("utf-8", errors="strict")
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=str(cwd), text=True,
            encoding="utf-8", errors="strict", start_new_session=os.name == "posix",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except FileNotFoundError as exc:
        return RunResult(127, "", f"executable not found: {exc}")
    deadline = time.monotonic() + timeout
    stdout: list[str] = []
    stderr: list[str] = []
    failures: list[BaseException] = []

    def feed() -> None:
        try:
            with proc.stdin:
                proc.stdin.write(stdin_text)
        except (BrokenPipeError, OSError):
            pass  # An early provider exit owns this result.
        except BaseException as exc:
            failures.append(exc)

    def read(pipe, chunks: list[str], callback=None) -> None:
        try:
            with pipe:
                for line in pipe:
                    chunks.append(line)
                    if callback is not None:
                        try:
                            callback(line)
                        except Exception:
                            pass
        except BaseException as exc:
            failures.append(exc)

    workers = [
        threading.Thread(target=feed, daemon=True),
        threading.Thread(target=read, args=(proc.stdout, stdout, on_line), daemon=True),
        threading.Thread(target=read, args=(proc.stderr, stderr), daemon=True),
    ]
    for worker in workers:
        worker.start()
    timed_out = False
    try:
        for worker in workers:
            worker.join(timeout=max(0, deadline - time.monotonic()))
            if worker.is_alive():
                raise subprocess.TimeoutExpired(argv, timeout)
        returncode = proc.wait(timeout=max(0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        timed_out = True
        _stop(proc)
    except BaseException:
        _stop(proc)
        raise
    finally:
        teardown = time.monotonic() + TEARDOWN_TIMEOUT_SEC
        for worker in workers:
            worker.join(timeout=max(0, teardown - time.monotonic()))
        try:
            proc.wait(timeout=max(0, teardown - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    if timed_out:
        return RunResult(124, "", f"timed out after {timeout}s")
    if failures:
        exc = failures[0]
        return RunResult(65, "", f"provider pipe failed ({type(exc).__name__}): {str(exc)[:1000]}")
    return RunResult(returncode, "".join(stdout), "".join(stderr))
