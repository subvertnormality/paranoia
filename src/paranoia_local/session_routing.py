"""Conservative provider routing from explicit server-written audit fields."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ENGINES = frozenset({"codex", "claude"})
MAX_AUDIT_BYTES = 20_000_000


@dataclass(frozen=True)
class SessionOwnership:
    owners: frozenset[str]
    incomplete: bool = False


def ownership(session_ref: str, directories: tuple[Path, ...]) -> SessionOwnership:
    owners: set[str] = set()
    incomplete = False
    for directory in dict.fromkeys(directories):
        try:
            paths = list(directory.glob("*.json"))
        except OSError:
            incomplete = True
            continue
        for path in paths:
            try:
                if path.stat().st_size > MAX_AUDIT_BYTES:
                    incomplete = True
                    continue
                record = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(record, dict):
                    incomplete = True
                    continue
            except (OSError, ValueError):
                incomplete = True
                continue
            rows = []
            if record.get("tool") in {"critique_branch", "critique_plan", "query", "rebut"}:
                if record.get("error") is False and type(record.get("returncode")) is int and record["returncode"] == 0:
                    rows.append(record)
                ledger = record.get("attempt_ledger", [])
                if isinstance(ledger, list):
                    rows.extend(row for row in ledger if isinstance(row, dict)
                                and row.get("outcome") in {"completed", "validation-invalid", "checkpoint"}
                                and type(row.get("returncode")) is int and row["returncode"] == 0)
            elif record.get("tool") == "run":
                attempts = record.get("attempts", [])
                if isinstance(attempts, list):
                    rows.extend(row for row in attempts if isinstance(row, dict)
                                and row.get("provider_outcome") == "completed"
                                and type(row.get("returncode")) is int and row["returncode"] == 0)
            for row in rows:
                if row.get("session_ref") == session_ref and row.get("engine") in ENGINES:
                    owners.add(row["engine"])
    return SessionOwnership(frozenset(owners), incomplete)


def resolve(session_ref: str, explicit: str | None, directories: tuple[Path, ...]) -> str:
    if not isinstance(session_ref, str) or not session_ref.strip():
        raise ValueError("rebut requires a nonempty session_ref")
    if explicit is not None and explicit not in ENGINES:
        raise ValueError("rebut engine must be codex or claude")
    found = ownership(session_ref, directories)
    if len(found.owners) > 1:
        raise ValueError("rebut session has conflicting provider provenance; resolve the audit conflict")
    if found.owners:
        owner = next(iter(found.owners))
        if explicit is not None and explicit != owner:
            raise ValueError(f"rebut session belongs to {owner}, not the explicitly requested {explicit}")
        if found.incomplete and explicit is None:
            raise ValueError("rebut audit scan is incomplete; supply the known engine explicitly")
        return owner
    if explicit is not None:
        return explicit
    raise ValueError("rebut session provider is unknown; supply engine explicitly or restore its audit record")
