"""Class closure: make a defect *class* a tracked object rather than an operator inference.

The pure core. Everything that touches git, the clock or the filesystem is injected,
so the protocol itself is testable without a repository.

Design contract: `docs/class_closure_plan.md`. The two rules that matter most, both
arrived at by deleting mechanism rather than adding it:

1. A mechanized class's predicate matches VIOLATIONS ONLY, so closure is exactly
   "zero matches" and no adjudication layer can whitelist a live defect (§2.1).
2. Nothing in the review's prose is parsed. The register is the sole class channel,
   and a class the reviewer declines to register is simply not tracked — that is
   unachievable to police and §1 scopes the guarantee accordingly (§2.2).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .textsafe import display

# ── severities and statuses ───────────────────────────────────────────────────

BLOCKER, MAJOR, MINOR, OUT_OF_SCOPE = "BLOCKER", "MAJOR", "MINOR", "OUT-OF-SCOPE"
SEVERITIES = (BLOCKER, MAJOR, MINOR, OUT_OF_SCOPE)
#: Only these two ever block. MINOR/OUT-OF-SCOPE classes are tracked and advisory —
#: a mechanism that can block forever on a marginal finding reproduces the very
#: failure it exists to prevent (plan §2.9).
BLOCKING_SEVERITIES = frozenset({BLOCKER, MAJOR})

OPEN, CLOSED, OVER_BROAD, MALFORMED, UNCHECKED, SUPERSEDED = (
    "open", "closed", "over-broad", "malformed", "unchecked", "superseded",
)
#: Every status except `closed` and `superseded` means "closure not proven".
UNPROVEN_STATUSES = frozenset({OPEN, OVER_BROAD, MALFORMED, UNCHECKED})

MAX_MATCHES = 200          # output bound; over it the class is `over-broad`
MAX_ACTIVE_CLASSES = 100   # counted over NON-SUPERSEDED classes only (plan §2.5)
PER_CLASS_TIMEOUT = 10     # seconds
ROUND_BUDGET = 60          # seconds, aggregate across all classes in a round

REGISTER_MARKER = "=== CLASS REGISTER ==="
NONE = "NONE"


class RegisterError(ValueError):
    """The register block is absent or does not parse."""


# ── records parsed out of the register ────────────────────────────────────────


@dataclass(frozen=True)
class NewClass:
    invariant: str
    severity: str
    pattern: str | None = None
    pathspec: str | None = None
    procedure: str | None = None

    @property
    def mechanized(self) -> bool:
        return self.pattern is not None


@dataclass(frozen=True)
class Transition:
    """`CLOSED`/`REOPEN`/`RECLASSIFY`/`SUPERSEDE` — a state change, not a finding."""

    kind: str
    class_id: str
    severity: str | None = None
    target: str | None = None
    pattern: str | None = None
    pathspec: str | None = None
    procedure: str | None = None
    invariant: str | None = None


@dataclass(frozen=True)
class Register:
    new_classes: tuple[NewClass, ...] = ()
    transitions: tuple[Transition, ...] = ()


# ── the tracked class ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrackedClass:
    class_id: str
    invariant: str
    severity: str
    first_round: int
    status: str
    pattern: str | None = None
    pathspec: str | None = None
    procedure: str | None = None
    superseded_by: str | None = None
    detail: str | None = None                 # why malformed / over-broad
    matches: tuple[dict[str, Any], ...] = ()  # last sweep's surviving matches

    @property
    def mechanized(self) -> bool:
        return self.pattern is not None

    @property
    def blocking(self) -> bool:
        return self.severity in BLOCKING_SEVERITIES and self.status in UNPROVEN_STATUSES


@dataclass(frozen=True)
class Exemption:
    class_id: str
    path: str
    line: int
    fingerprint: str


def fingerprint(text: str) -> str:
    """Exact-bytes hash of a matched line. An exemption is void the moment the line's text
    changes at all, which fails toward blocking rather than toward clearance.

    Deliberately NOT whitespace-normalized: in indentation-sensitive code a line that keeps
    its tokens but changes its indentation has moved scope, and a stale exemption would let
    the class close over a live violation."""
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()[:16]


# ── register parsing ──────────────────────────────────────────────────────────

_NEW_MECHANIZED = {"CLASS", "SEVERITY", "PATTERN", "PATHSPEC"}
_NEW_UNMECHANIZED = {"CLASS", "SEVERITY", "PROCEDURE"}
_KNOWN_KEYS = _NEW_MECHANIZED | _NEW_UNMECHANIZED | {
    "CLOSED", "REOPEN", "RECLASSIFY", "SUPERSEDE", "BY", "WITH-PATTERN", "WITH-PROCEDURE",
}


def parse_register(text: str) -> Register:
    """Parse the terminal `=== CLASS REGISTER ===` block.

    Strict in the manner of `arbitration.parse_*`, because this is the one
    model-authored surface that is parsed at all: the block is terminal, records are
    blank-line separated, every field is required for its record kind, and duplicate
    or unknown keys are rejected. Nothing outside the block is examined.
    """
    idx = text.rfind(REGISTER_MARKER)
    if idx < 0:
        raise RegisterError("no === CLASS REGISTER === block")
    if text.count(REGISTER_MARKER) > 1:
        raise RegisterError("more than one === CLASS REGISTER === block")

    body = text[idx + len(REGISTER_MARKER):].strip()
    if body == NONE:
        return Register()
    if not body:
        raise RegisterError("register block is empty (use NONE)")

    new_classes: list[NewClass] = []
    transitions: list[Transition] = []
    for block in [b for b in body.split("\n\n") if b.strip()]:
        fields = _parse_block(block)
        keys = set(fields)
        if "CLOSED" in keys or "REOPEN" in keys or "RECLASSIFY" in keys:
            transitions.append(_simple_transition(fields, keys))
        elif "SUPERSEDE" in keys:
            transitions.append(_supersede(fields, keys))
        elif "CLASS" in keys:
            new_classes.append(_new_class(fields, keys))
        else:
            raise RegisterError(f"unrecognised record: {sorted(keys)}")
    return Register(tuple(new_classes), tuple(transitions))


def _parse_block(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in block.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise RegisterError(f"register line is not KEY: value — {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        if key not in _KNOWN_KEYS:
            raise RegisterError(f"unknown register key {key!r}")
        if key in fields:
            raise RegisterError(f"duplicate register key {key!r}")
        fields[key] = value.strip()
    if not fields:
        raise RegisterError("empty register record")
    return fields


def _require(fields: dict[str, str], key: str) -> str:
    value = fields.get(key, "")
    if not value:
        raise RegisterError(f"register record is missing {key}")
    return value


def _severity(raw: str) -> str:
    if raw not in SEVERITIES:
        raise RegisterError(f"unknown severity {raw!r}")
    return raw


def _new_class(fields: dict[str, str], keys: set[str]) -> NewClass:
    invariant, severity = _require(fields, "CLASS"), _severity(_require(fields, "SEVERITY"))
    if keys == _NEW_MECHANIZED:
        pathspec = _require(fields, "PATHSPEC")
        _reject_pathspec_magic(pathspec)
        return NewClass(invariant, severity, pattern=_require(fields, "PATTERN"), pathspec=pathspec)
    if keys == _NEW_UNMECHANIZED:
        return NewClass(invariant, severity, procedure=_require(fields, "PROCEDURE"))
    raise RegisterError(
        "a new class needs CLASS+SEVERITY plus either PATTERN+PATHSPEC or PROCEDURE, "
        f"got {sorted(keys)}"
    )


def _simple_transition(fields: dict[str, str], keys: set[str]) -> Transition:
    for kind in ("CLOSED", "REOPEN"):
        if kind in keys:
            if keys != {kind}:
                raise RegisterError(f"{kind} takes no other fields, got {sorted(keys)}")
            return Transition(kind, _require(fields, kind))
    if keys != {"RECLASSIFY"}:
        raise RegisterError(f"RECLASSIFY takes no other fields, got {sorted(keys)}")
    parts = _require(fields, "RECLASSIFY").split()
    if len(parts) != 2:
        raise RegisterError("RECLASSIFY takes '<class-id> <severity>'")
    return Transition("RECLASSIFY", parts[0], severity=_severity(parts[1]))


def _supersede(fields: dict[str, str], keys: set[str]) -> Transition:
    old = _require(fields, "SUPERSEDE")
    if keys == {"SUPERSEDE", "BY"}:
        return Transition("SUPERSEDE", old, target=_require(fields, "BY"))
    if keys <= {"SUPERSEDE", "WITH-PATTERN", "PATHSPEC", "CLASS"} and "WITH-PATTERN" in keys:
        pathspec = _require(fields, "PATHSPEC")
        _reject_pathspec_magic(pathspec)
        return Transition(
            "SUPERSEDE", old, pattern=_require(fields, "WITH-PATTERN"),
            pathspec=pathspec, invariant=fields.get("CLASS") or None,
        )
    if keys <= {"SUPERSEDE", "WITH-PROCEDURE", "CLASS"} and "WITH-PROCEDURE" in keys:
        return Transition(
            "SUPERSEDE", old, procedure=_require(fields, "WITH-PROCEDURE"),
            invariant=fields.get("CLASS") or None,
        )
    raise RegisterError(
        "SUPERSEDE takes BY, or WITH-PATTERN+PATHSPEC, or WITH-PROCEDURE — "
        f"got {sorted(keys)}"
    )


def _reject_pathspec_magic(pathspec: str) -> None:
    """A leading `:` is git pathspec magic. Verified: `-- ':(exclude)src'` is accepted
    and silently changes the result set, so a model-authored pathspec must not carry it."""
    if pathspec.startswith(":"):
        raise RegisterError(
            f"pathspec magic is not allowed (leading ':') — {pathspec!r}"
        )


# ── lineage state ─────────────────────────────────────────────────────────────


@dataclass
class Lineage:
    lineage_id: str
    rounds: int = 0
    next_seq: int = 1
    classes: dict[str, TrackedClass] = field(default_factory=dict)
    exemptions: list[Exemption] = field(default_factory=list)
    debt: dict[str, Any] | None = None

    def active(self) -> list[TrackedClass]:
        return [c for c in self.classes.values() if c.status != SUPERSEDED]

    def blocking(self) -> list[TrackedClass]:
        return [c for c in self.active() if c.blocking]


class StateUnavailable(RuntimeError):
    """Lineage state could not be read or written. Blocks; never silently starts fresh —
    a storage fault must not become a false all-clear (plan §2.7)."""


#: Where lineage state lives. Deliberately NOT derived from `log_dir`: `--log-dir` is
#: documented as the audit-log directory, so a caller who moves their logs would silently
#: get an empty state root and could be told NOT-BLOCKED with classes still open.
DEFAULT_STATE_ROOT = Path.home() / ".paranoia"
STATE_ROOT_ENV = "PARANOIA_STATE_ROOT"


def default_state_root() -> Path:
    """The env override exists so the test suite can isolate itself without every caller
    threading a path — nothing may write lineages into the operator's real home."""
    override = os.environ.get(STATE_ROOT_ENV)
    return Path(override) if override else DEFAULT_STATE_ROOT


def lineage_dir(root: Path) -> Path:
    return Path(root) / "lineages"


def _paths(root: Path, lineage_id: str) -> tuple[Path, Path]:
    d = lineage_dir(root)
    return d / f"{lineage_id}.json", d / f"{lineage_id}.pending"


def load_lineage(root: Path, lineage_id: str, *, stamp: str) -> Lineage:
    state_path, pending = _paths(root, lineage_id)
    quarantined = sorted(lineage_dir(root).glob(f"{lineage_id}.corrupt-*.json"))
    if quarantined:
        raise StateUnavailable(
            f"lineage {lineage_id} has quarantined state — repair or delete "
            f"{quarantined[-1]} before this lineage can be used again"
        )
    if pending.exists():
        raise StateUnavailable(
            f"a previous round left a pending write latch at {pending}; its state write "
            "may not have completed. Inspect and remove it to continue."
        )
    if not state_path.exists():
        return Lineage(lineage_id)
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        return _from_json(lineage_id, raw)
    except Exception as exc:  # noqa: BLE001 — any unreadable state blocks, none is repaired silently
        dest = lineage_dir(root) / f"{lineage_id}.corrupt-{stamp}.json"
        try:
            state_path.replace(dest)
        except OSError:
            dest = state_path
        raise StateUnavailable(
            f"lineage state at {state_path} did not parse ({exc}); quarantined to {dest}. "
            "Repair or delete it and re-run."
        ) from exc


def _from_json(lineage_id: str, raw: dict[str, Any]) -> Lineage:
    return Lineage(
        lineage_id=lineage_id,
        rounds=int(raw.get("rounds", 0)),
        next_seq=int(raw.get("next_seq", 1)),
        classes={
            c["class_id"]: TrackedClass(
                class_id=c["class_id"], invariant=c["invariant"], severity=c["severity"],
                first_round=int(c["first_round"]), status=c["status"],
                pattern=c.get("pattern"), pathspec=c.get("pathspec"),
                procedure=c.get("procedure"), superseded_by=c.get("superseded_by"),
                detail=c.get("detail"), matches=tuple(c.get("matches", ())),
            )
            for c in raw.get("classes", [])
        },
        exemptions=[Exemption(**e) for e in raw.get("exemptions", [])],
        debt=raw.get("debt"),
    )


def _to_json(lineage: Lineage) -> dict[str, Any]:
    return {
        "rounds": lineage.rounds,
        "next_seq": lineage.next_seq,
        "classes": [
            {k: v for k, v in vars(c).items() if v not in (None, ())} | {"matches": list(c.matches)}
            for c in lineage.classes.values()
        ],
        "exemptions": [vars(e) for e in lineage.exemptions],
        "debt": lineage.debt,
    }


def open_latch(root: Path, lineage_id: str) -> None:
    """Written before the engine call, cleared only once the round has finished writing.
    Without it a *failed* write leaves no marker and the next round starts empty."""
    _, pending = _paths(root, lineage_id)
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text("pending\n", encoding="utf-8")


def clear_latch(root: Path, lineage_id: str) -> None:
    _, pending = _paths(root, lineage_id)
    pending.unlink(missing_ok=True)


def save_lineage(root: Path, lineage: Lineage) -> None:
    state_path, _ = _paths(root, lineage.lineage_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=str(state_path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(_to_json(lineage), fh, indent=2, default=str)
        os.replace(tmp, state_path)
    except OSError as exc:
        raise StateUnavailable(
            f"could not write lineage state under {state_path.parent}: {exc}"
        ) from exc


# ── applying a register ───────────────────────────────────────────────────────


def mint_id(lineage_id: str, seq: int, invariant: str) -> str:
    """Server-assigned and stable for life. Never derived from the predicate: two
    distinct invariants expressible by one regex must stay two independent classes."""
    return hashlib.sha256(f"{lineage_id}\0{seq}\0{invariant}".encode()).hexdigest()[:8]


def apply_register(lineage: Lineage, register: Register, *, round_no: int) -> list[str]:
    """Fold a parsed register into the lineage ATOMICALLY, returning the ids of newly minted
    classes for the caller to evaluate before computing a verdict (plan §2.6).

    A register is all-or-nothing. Applied record-by-record to the live lineage, a valid
    `CLOSED: A` followed by an invalid record would leave A closed even though the register
    was rejected — and once the debt was discharged the trailer could report `NOT-BLOCKED`
    on the strength of a transition from a register that never parsed.
    """
    draft = _copy(lineage)
    minted: list[str] = []
    seen_sources: set[str] = set()
    for t in register.transitions:
        if t.class_id in seen_sources:
            # Two state changes against one class in a register have no defined order, and
            # two SUPERSEDE ... WITH-* records would mint two live replacements for one
            # retired class — quietly breaking the net-zero guarantee at the cap.
            raise RegisterError(
                f"more than one transition against class {t.class_id} in a single register"
            )
        seen_sources.add(t.class_id)
        _apply_transition(draft, t, round_no=round_no, minted=minted)
    for nc in register.new_classes:
        if len(draft.active()) >= MAX_ACTIVE_CLASSES:
            raise RegisterError(
                f"registration refused: {MAX_ACTIVE_CLASSES} non-superseded classes already "
                "tracked. Close or supersede one first."
            )
        minted.append(_add(draft, nc.invariant, nc.severity, round_no,
                           nc.pattern, nc.pathspec, nc.procedure))
    if len(draft.active()) > MAX_ACTIVE_CLASSES:
        raise RegisterError(
            f"register would leave {len(draft.active())} non-superseded classes, over the "
            f"{MAX_ACTIVE_CLASSES} cap"
        )
    lineage.classes = draft.classes
    lineage.next_seq = draft.next_seq
    lineage.exemptions = draft.exemptions
    return minted


def _copy(lineage: Lineage) -> Lineage:
    return Lineage(
        lineage_id=lineage.lineage_id, rounds=lineage.rounds, next_seq=lineage.next_seq,
        classes=dict(lineage.classes), exemptions=list(lineage.exemptions), debt=lineage.debt,
    )


def _add(lineage: Lineage, invariant: str, severity: str, round_no: int,
         pattern: str | None, pathspec: str | None, procedure: str | None) -> str:
    cid = mint_id(lineage.lineage_id, lineage.next_seq, invariant)
    lineage.next_seq += 1
    lineage.classes[cid] = TrackedClass(
        class_id=cid, invariant=invariant, severity=severity, first_round=round_no,
        # A mechanized class is UNCHECKED until its predicate has actually run, so a
        # class registered this round cannot ride out the round as silently closed.
        status=UNCHECKED if pattern else OPEN,
        pattern=pattern, pathspec=pathspec, procedure=procedure,
    )
    return cid


def _apply_transition(lineage: Lineage, t: Transition, *, round_no: int, minted: list[str]) -> None:
    cls = lineage.classes.get(t.class_id)
    if cls is None:
        raise RegisterError(f"{t.kind} names unknown class id {t.class_id!r}")
    if cls.status == SUPERSEDED:
        # A superseded class is inert and uncounted against the cap. Letting CLOSED/REOPEN
        # move it back to an active status would resurrect it, and superseding it again
        # would mint a second replacement for one retirement.
        raise RegisterError(
            f"{t.kind} names class {t.class_id}, which is already superseded by "
            f"{cls.superseded_by}"
        )

    if t.kind in ("CLOSED", "REOPEN"):
        if cls.mechanized:
            raise RegisterError(
                f"{t.kind} is for unmechanized classes only; {t.class_id} has a predicate "
                "and closes or reopens from git"
            )
        lineage.classes[t.class_id] = replace(cls, status=CLOSED if t.kind == "CLOSED" else OPEN)
        return

    if t.kind == "RECLASSIFY":
        lineage.classes[t.class_id] = replace(cls, severity=t.severity or cls.severity)
        return

    # SUPERSEDE — the source must not survive as a blocker, so the replacement has to be real.
    if t.target is not None:
        if t.target == t.class_id:
            raise RegisterError("SUPERSEDE ... BY cannot name the class it supersedes")
        target = lineage.classes.get(t.target)
        if target is None:
            raise RegisterError(f"SUPERSEDE ... BY names unknown class id {t.target!r}")
        if target.status == SUPERSEDED:
            raise RegisterError(f"SUPERSEDE ... BY names an already-superseded class {t.target!r}")
        lineage.classes[t.target] = replace(
            target, first_round=min(target.first_round, cls.first_round)
        )
        new_id = t.target
    else:
        new_id = _add(
            lineage, t.invariant or cls.invariant, cls.severity, cls.first_round,
            t.pattern, t.pathspec, t.procedure,
        )
        minted.append(new_id)
    lineage.classes[t.class_id] = replace(cls, status=SUPERSEDED, superseded_by=new_id)


# ── the closure sweep ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GrepResult:
    """One class's two-pass git result. `paths` is the VERDICT (from `git grep -l -z`,
    uniform across text and binary); `matches` is display only (from `-I -z -n`), so a
    binary-only violation still blocks even though no line can be shown."""

    paths: tuple[str, ...] = ()
    matches: tuple[dict[str, Any], ...] = ()
    error: str | None = None


GitGrep = Callable[[str, str], GrepResult]


@dataclass
class Budget:
    """The round's closure budget, measured in GREP time only.

    Deliberately not a wall-clock deadline: one round's two sweeps straddle the reviewer
    call, which routinely runs for minutes, so an absolute deadline opened before the
    review would always be spent by the time the post-register sweep ran — and every
    newly registered class would be `unchecked` instead of evaluated, defeating both
    same-round evaluation and the same-round false-closure warning.

    A class is only started while budget remains, and each class can then run its two
    passes, so the real ceiling is `total + 2 * PER_CLASS_TIMEOUT`.
    """

    total: float = ROUND_BUDGET
    spent: float = 0.0

    def exhausted(self) -> bool:
        return self.spent >= self.total

    def charge(self, seconds: float) -> None:
        self.spent += max(0.0, seconds)


def sweep(lineage: Lineage, grep: GitGrep, *, only: Iterable[str] | None = None,
          budget: Budget | None = None, clock: Callable[[], float] | None = None) -> None:
    """Re-run every non-superseded mechanized predicate and update its status in place.

    `closed` classes are swept too: a later fix can reintroduce a defect, and a class
    that never reopens would let the trailer report nothing unclosed while it lives.

    Pass the SAME `Budget` to both of a round's sweeps so they share it rather than each
    getting a fresh one.
    """
    ids = list(only) if only is not None else list(lineage.classes)
    now = clock or (lambda: 0.0)
    for cid in ids:
        cls = lineage.classes.get(cid)
        if cls is None or cls.status == SUPERSEDED or not cls.mechanized:
            continue
        if budget is not None and budget.exhausted():
            lineage.classes[cid] = replace(
                cls, status=UNCHECKED, matches=(),
                detail="round closure budget exhausted before this class ran",
            )
            continue
        started = now()
        result = grep(cls.pattern or "", cls.pathspec or ".")
        if budget is not None:
            budget.charge(now() - started)
        lineage.classes[cid] = _evaluate(cls, result, lineage.exemptions)


def _evaluate(cls: TrackedClass, result: GrepResult, exemptions: Sequence[Exemption]) -> TrackedClass:
    if result.error:
        # A predicate that cannot run has not proved closure — but for an advisory class
        # that is no reason to stop the loop, so blocking still follows severity.
        return replace(cls, status=MALFORMED, detail=result.error, matches=())
    # `-l` returns FILES, so counting it alone lets one file with thousands of violating
    # lines pass as an ordinary open class and then be silently truncated in the block.
    total = max(len(result.paths), len(result.matches))
    if total > MAX_MATCHES:
        unit = "matching lines" if len(result.matches) >= len(result.paths) else "matching files"
        return replace(
            cls, status=OVER_BROAD, matches=(),
            detail=f"{total} {unit} exceeds the {MAX_MATCHES} cap — narrow the predicate "
                   "with SUPERSEDE ... WITH-PATTERN",
        )

    exempt = {(e.path, e.line, e.fingerprint) for e in exemptions if e.class_id == cls.class_id}
    shown = [
        m for m in result.matches
        if (m["path"], m["line"], fingerprint(m["text"])) not in exempt
    ]
    # A path the verdict pass found but the display pass could not read is a binary match:
    # it must still block, and must still be visible, with no line to quote.
    #
    # It can NEVER be exempted. An exemption's identity is (path, line, text-fingerprint),
    # and none of those can be established for a match no pass could read — so falling back
    # to path-only matching here would silently turn one exact exemption into a path-wide
    # one the moment a file went binary or the display pass timed out, and close the class
    # over a live violation.
    displayed_paths = {m["path"] for m in result.matches}
    binary = [
        {"path": p, "line": 0, "text": "", "binary": True}
        for p in result.paths if p not in displayed_paths
    ]
    survivors = tuple(shown + binary)
    if not survivors:
        return replace(cls, status=CLOSED, matches=(), detail=None)
    return replace(cls, status=OPEN, matches=survivors, detail=None)


# ── the git edge ──────────────────────────────────────────────────────────────

def make_grep(repo: Path, commit: str, *,
              runner: Callable[[list[str], Path, int], tuple[int, bytes, bytes]]) -> GitGrep:
    """Bind a two-pass `git grep` to one snapshot.

    The predicate is DATA, never an argv: `shell=False`, no pipes, no reviewer-chosen
    binary or flags, pattern and pathspec passed as operands. `git grep <commit>` reads
    the tree directly, so no checkout is needed.
    """

    def grep(pattern: str, pathspec: str) -> GrepResult:
        base = ["git", "grep", "-z", "-E", "--no-color", "-e", pattern, commit, "--", pathspec or "."]
        try:
            # Verdict pass: -l lists matching paths, uniformly for text AND binary blobs.
            # -I would silently drop a binary violation and report the class closed.
            code, out, err = runner(["git", "grep", "-l"] + base[2:], repo, PER_CLASS_TIMEOUT)
        except TimeoutError:
            return GrepResult(error=f"predicate timed out after {PER_CLASS_TIMEOUT}s")
        if code == 1:
            return GrepResult()               # no matches: closure, not failure
        if code >= 2:
            return GrepResult(error=_git_error(err))
        paths = tuple(p for p in _decode(out).split("\0") if p)

        # Display pass. Its failure is not a verdict failure — the verdict already stands.
        matches: tuple[dict[str, Any], ...] = ()
        try:
            code2, out2, _ = runner(["git", "grep", "-I", "-n"] + base[2:], repo, PER_CLASS_TIMEOUT)
            if code2 == 0:
                matches = _parse_matches(_decode(out2))
        except TimeoutError:
            pass
        return GrepResult(paths=_strip_commit(paths, commit), matches=matches)

    return grep


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


def _git_error(err: bytes) -> str:
    first = _decode(err).strip().splitlines()
    return first[0] if first else "git grep failed"


def _strip_commit(paths: Sequence[str], commit: str) -> tuple[str, ...]:
    prefix = f"{commit}:"
    return tuple(p[len(prefix):] if p.startswith(prefix) else p for p in paths)


def _parse_matches(out: str) -> tuple[dict[str, Any], ...]:
    """`-z -n` emits `<commit>:<path>\0<line>\0<text>\n`.

    Scanned NUL-first, never split on newlines first: git prints pathnames verbatim and
    terminates them with NUL precisely so a path MAY contain a newline. Splitting on `\n`
    would tear such a record in two and mint a wrong path — and therefore a wrong exemption
    identity. The matched text itself is a single line, so its terminating `\n` is the only
    newline that ends a record.
    """
    found: list[dict[str, Any]] = []
    pos = 0
    while pos < len(out):
        nul1 = out.find("\0", pos)
        if nul1 < 0:
            break
        nul2 = out.find("\0", nul1 + 1)
        if nul2 < 0:
            break
        path, raw_line = out[pos:nul1], out[nul1 + 1:nul2]
        end = out.find("\n", nul2 + 1)
        end = len(out) if end < 0 else end
        text = out[nul2 + 1:end]
        pos = end + 1
        path = path.split(":", 1)[1] if ":" in path else path
        try:
            found.append({"path": path, "line": int(raw_line), "text": text})
        except ValueError:
            continue
    return tuple(found)


# ── rendering (every path and line goes through the injective display helper) ──

UNCLOSED_HEADER = "=== UNCLOSED CLASSES — re-verify these; do NOT suppress ==="
UNMECHANIZED_HEADER = "=== UNMECHANIZED CLASSES — no predicate; you are the check ==="
EXEMPT_HEADER = "=== CLAIMED EXEMPT — challenge any that is not genuinely a false positive ==="

_UNCLOSED_INSTRUCTION = (
    "These were reported in an earlier round and are NOT closed. Report every surviving "
    "match, marked [RECURRENCE <id>]. The ROUND severity floor does not apply to them. If a "
    "finding of yours is an instance of one of these, report it as a recurrence of that id — "
    "do NOT register it as a new class. Where this block and the already-raised block "
    "conflict, THIS block governs."
)


def render_unclosed(lineage: Lineage) -> str | None:
    rows = [c for c in lineage.active() if c.mechanized and c.status in UNPROVEN_STATUSES]
    if not rows:
        return None
    out = [UNCLOSED_HEADER, _UNCLOSED_INSTRUCTION, ""]
    for c in sorted(rows, key=lambda c: (c.first_round, c.class_id)):
        out.append(f"[class {c.class_id}, first raised round {c.first_round}, {c.severity}] "
                   f"{display(c.invariant)}")
        if c.detail:
            out.append(f"  status {c.status}: {display(c.detail)}")
        for m in c.matches[:MAX_MATCHES]:
            if m.get("binary"):
                out.append(f"  {display(m['path'])}: binary match (line not shown)")
            else:
                out.append(f"  {display(m['path'])}:{m['line']}: {display(m['text'])}")
        if len(c.matches) > MAX_MATCHES:
            # Never truncate silently: an operator reads this block as the match list.
            out.append(f"  … {len(c.matches) - MAX_MATCHES} further match(es) not shown")
    return "\n".join(out)


def render_unmechanized(lineage: Lineage) -> str | None:
    """Closed entries are listed too — without their ids a later cold reviewer has no way
    to emit REOPEN, and the class could recur while the state stayed closed."""
    rows = [c for c in lineage.active() if not c.mechanized]
    if not rows:
        return None
    out = [UNMECHANIZED_HEADER,
           "No predicate can check these. Re-verify each by its procedure. Emit "
           "`CLOSED: <id>` when one is genuinely closed, or `REOPEN: <id>` when a closed "
           "one is violated again.", ""]
    for c in sorted(rows, key=lambda c: (c.first_round, c.class_id)):
        state = f"closed" if c.status == CLOSED else c.status
        out.append(f"[{c.class_id}, {c.severity}, {state}, first raised round {c.first_round}] "
                   f"{display(c.invariant)}")
        out.append(f"  procedure: {display(c.procedure or '')}")
    return "\n".join(out)


def render_exempt(lineage: Lineage) -> str | None:
    if not lineage.exemptions:
        return None
    out = [EXEMPT_HEADER]
    for e in lineage.exemptions:
        out.append(f"- class {e.class_id}: {display(e.path)}:{e.line}")
    return "\n".join(out)


def render_trailer(lineage: Lineage, *, register_status: str,
                   minted: Sequence[str] = (), reopened: Sequence[str] = ()) -> str:
    """The computed verdict. It only ever asserts the NEGATIVE: `NOT-BLOCKED` says no
    blocking class is unclosed, never that the change is correct and never the word
    `converged` — a mechanical check laundered into an approval is the failure mode
    this whole design is built against."""
    active = lineage.active()
    blocking = lineage.blocking()
    counts = (
        f"{sum(1 for c in active if c.status in UNPROVEN_STATUSES)} open, "
        f"{sum(1 for c in active if c.status == CLOSED)} closed, "
        f"{sum(len(c.matches) for c in active)} surviving matches, "
        f"{len(lineage.exemptions)} exempt, "
        f"{sum(1 for c in active if not c.mechanized)} unmechanized"
    )
    lines = [
        f"LINEAGE: {lineage.lineage_id} (rounds recorded: {lineage.rounds})",
        f"CLASS-REGISTER: {register_status}",
        f"CLASS-CLOSURE: {counts}",
    ]
    # A predicate can be wrong in the SAFE direction — too narrow, matching none of the
    # violations it was written for, and closing in the very round it was registered. The
    # mechanism cannot detect that, so it says so rather than presenting an ordinary close.
    born_closed = [
        lineage.classes[c] for c in minted
        if c in lineage.classes and lineage.classes[c].status == CLOSED
        and lineage.classes[c].mechanized
    ]
    if born_closed:
        lines.append(
            "CLASS-CLOSURE-WARNING: " + "; ".join(
                f"{c.class_id} closed in the round it was registered — verify its predicate "
                f"actually matches the violation it describes ({display(c.invariant)})"
                for c in born_closed
            )
        )
    if lineage.debt:
        lines.append(
            f"CONVERGENCE: BLOCKED — register debt from round {lineage.debt.get('round')}: "
            f"{lineage.debt.get('reason')}"
        )
    elif blocking:
        lines.append(f"CONVERGENCE: BLOCKED — {len(blocking)} class(es) unclosed:")
        for c in sorted(blocking, key=lambda c: (c.first_round, c.class_id)):
            how = (f"mechanized: {len(c.matches)} match(es)" if c.mechanized
                   else "unmechanized: awaiting reviewer CLOSED or RECLASSIFY")
            if c.status in (MALFORMED, OVER_BROAD, UNCHECKED):
                how = f"{c.status}: {display(c.detail or 'closure not proven')}"
            lines.append(f"  {c.class_id} {display(c.invariant)} ({how})")
        lines.append(
            "  Any `CONVERGED` in the review text above is VOID: it is the reviewer's "
            "judgement about new findings, not a statement about these classes."
        )
    else:
        lines.append("CONVERGENCE: NOT-BLOCKED — no blocking class is unclosed; advisory "
                     "classes may remain open. Reviewer findings still govern.")
    return "\n".join(lines)
