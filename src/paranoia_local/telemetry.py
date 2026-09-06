"""Best-effort diagnostic run traces; never authority for review settlement."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from . import inert_git


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def source_identity() -> dict[str, Any]:
    package = Path(__file__).resolve().parent
    try:
        files = {
            path.name:hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(package.glob("*.py"))
        }
        try:
            revision = inert_git.text(package, ["rev-parse", "HEAD"]).strip()
        except Exception:
            revision = None
        return {
            "revision":revision,
            "source_sha256":digest(json.dumps(files, sort_keys=True, separators=(",", ":"))),
            "files":files,
        }
    except Exception:
        return {"revision":None, "source_sha256":None, "files":{}}


# These are on-disk source observations, not proof of Python's loaded code objects.
IMPORT_SOURCE = source_identity()


@dataclass
class RunTrace:
    tool: str
    started: float = field(default_factory=time.perf_counter)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)
    result_sha256: str | None = None
    exception: str | None = None


CURRENT: ContextVar[RunTrace | None] = ContextVar("paranoia_run", default=None)


def submit(pool, function: Callable, *args, **kwargs):
    """ThreadPoolExecutor does not propagate ContextVars itself."""
    return pool.submit(copy_context().run, function, *args, **kwargs)


def observe(call: Callable, **settings):
    trace = CURRENT.get()
    if trace is None:
        return call()
    try:
        row = {
            **settings, "prompt_sha256":digest(settings.pop("prompt")),
            "schema_sha256":(
                digest(json.dumps(settings["schema"], ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                if settings.get("schema") is not None else None
            ),
        }
        row.pop("prompt", None)
        row.pop("schema", None)
        with trace.lock:
            row.update(sequence=len(trace.attempts) + 1,
                       start_offset_ms=int((time.perf_counter() - trace.started) * 1000))
            trace.attempts.append(row)
    except Exception:
        return call()
    started = time.perf_counter()
    try:
        review = call()
        row.update(
            provider_outcome="failed" if review.error else "completed",
            returncode=review.returncode, session_ref=review.session_ref,
            provider_duration_ms=review.provider_duration_ms,
        )
        return review
    except BaseException as exc:
        row.update(provider_outcome="raised", exception=type(exc).__name__)
        raise
    finally:
        row["elapsed_ms"] = int((time.perf_counter() - started) * 1000)


@contextmanager
def recording(tool: str, log_dir: Path):
    trace = RunTrace(tool)
    token = CURRENT.set(trace)
    try:
        yield trace
    except BaseException as exc:
        trace.exception = type(exc).__name__
        raise
    finally:
        elapsed = int((time.perf_counter() - trace.started) * 1000)
        CURRENT.reset(token)
        try:
            from .logs import write_log
            observed = source_identity()
            write_log(log_dir, "run", {
                "reviewed_tool":tool, "run_id":trace.run_id,
                "total_elapsed_ms":elapsed,
                "duration_semantics":"local dispatch wall time; concurrent attempts are not summed",
                "source_observed_at_import":IMPORT_SOURCE,
                "source_observed_at_finish":observed,
                "source_changed_since_import":(
                    IMPORT_SOURCE["source_sha256"] != observed["source_sha256"]
                ),
                "attempts":trace.attempts, "result_sha256":trace.result_sha256,
                "exception":trace.exception,
            }, time.strftime("%Y%m%dT%H%M%S", time.gmtime()))
        except Exception:
            pass
