"""Pure reviewer-authored patch proposal protocol and rendering.

This module does not dispatch providers, mutate repositories, or execute patches.
Callers supply pinned source bytes through a bounded reader.
"""
from __future__ import annotations

from dataclasses import dataclass
import difflib
import hashlib
import json
import re
from typing import Any, Callable, Literal, Sequence

from . import git_objects
from . import staged_protocol as sp


SCHEMA_VERSION = 1
MAX_TARGETS = 20
MAX_PATHS = 12
MAX_EDITS = 64
MAX_EDIT_BYTES = 131_072
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_RAW_BYTES = 262_144
MAX_PATCH_BYTES = 262_144
MAX_SUMMARY_CHARS = 2_000
MAX_REASON_CHARS = 1_000
MAX_NOTE_ITEMS = 12
MAX_NOTE_CHARS = 500
PLAN_LABEL = "plan-artifact.md"

_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")
_TARGET_ID = re.compile(r"^(?:structural:[A-Za-z0-9._-]+|claim:C-[0-9a-f]{10})$")
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


class ProposalError(ValueError):
    """Bounded, provider-repairable proposal rejection."""

    def __init__(self, issues: Sequence[str]):
        ordered = list(dict.fromkeys(issues))
        super().__init__("\n".join(ordered[:20])[:8_000])
        self.issues = tuple(ordered[:20])


class SourceReadError(ValueError):
    """A bounded source-admission failure that the proposal author can repair."""


@dataclass(frozen=True)
class ProposalTarget:
    key: str
    summary: str
    severity: str
    evidence: tuple[str, ...]
    remedy: str = ""
    class_context: tuple[str, ...] = ()
    claim_context: str = ""

    def __post_init__(self) -> None:
        if not _TARGET_ID.fullmatch(self.key):
            raise ValueError(f"invalid canonical proposal target: {self.key!r}")


@dataclass(frozen=True)
class ProposalEntry:
    path: str
    kind: Literal["file", "executable", "symlink", "gitlink", "directory"]
    mode: str
    oid: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class SourceContent:
    pinned: bytes
    checkout: bytes | None = None


SourceReader = Callable[[ProposalEntry], SourceContent]


@dataclass(frozen=True)
class ProposalContext:
    mode: Literal["branch", "plan"]
    targets: tuple[ProposalTarget, ...]
    stakes: str
    reviewed_snapshot: str
    structural_snapshot: str
    contract_digest: str | None
    contract_text: str | None
    entries: tuple[ProposalEntry, ...] = ()
    plan_bytes: bytes | None = None
    plan_digest: str | None = None
    plan_source_kind: Literal["plan_text", "plan_path"] | None = None
    plan_source_path: str | None = None

    def __post_init__(self) -> None:
        keys = [target.key for target in self.targets]
        if not keys or len(keys) > MAX_TARGETS or len(keys) != len(set(keys)):
            raise ValueError("proposal targets must be one to twenty unique canonical keys")
        if self.mode == "plan" and self.plan_bytes is None:
            raise ValueError("plan proposal context requires captured plan bytes")
        if self.mode == "branch" and self.plan_bytes is not None:
            raise ValueError("branch proposal context cannot own plan bytes")


@dataclass(frozen=True)
class ProposedFile:
    path: str
    mode: str
    original: bytes | None
    proposed: bytes
    original_oid: str | None


@dataclass(frozen=True)
class ProposalResult:
    status: Literal["proposed", "partial", "declined"]
    summary: str
    addressed_ids: tuple[str, ...]
    unaddressed: tuple[tuple[str, str], ...]
    suggested_tests: tuple[str, ...]
    limitations: tuple[str, ...]
    files: tuple[ProposedFile, ...]
    patch: bytes
    patch_sha256: str
    raw_value: dict[str, Any]


def proposal_schema(context: ProposalContext) -> dict[str, Any]:
    target_ids = [target.key for target in context.targets]
    edit_properties: dict[str, Any] = {
        "target": {"type": "string", "enum": ["repository", "plan"]},
        "operation": {"type": "string", "enum": ["replace", "create"]},
        "path": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "old_text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "new_text": {"type": "string"},
    }
    if context.mode == "plan":
        edit_properties.update({
            "target": {"type": "string", "const": "plan"},
            "operation": {"type": "string", "const": "replace"},
            "path": {"type": "null"},
            "old_text": {"type": "string"},
        })
    else:
        edit_properties["target"] = {"type": "string", "const": "repository"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
            "status": {"type": "string", "enum": ["proposed", "declined"]},
            "summary": {"type": "string", "minLength": 1, "maxLength": MAX_SUMMARY_CHARS},
            "addressed_finding_ids": {
                "type": "array", "maxItems": MAX_TARGETS, "uniqueItems": True,
                "items": {"type": "string", "enum": target_ids},
            },
            "unaddressed": {
                "type": "array", "maxItems": MAX_TARGETS,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "finding_id": {"type": "string", "enum": target_ids},
                        "reason": {"type": "string", "minLength": 1,
                                   "maxLength": MAX_REASON_CHARS},
                    },
                    "required": ["finding_id", "reason"],
                },
            },
            "edits": {
                "type": "array", "maxItems": MAX_EDITS,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": edit_properties,
                    "required": ["target", "operation", "path", "old_text", "new_text"],
                },
            },
            "suggested_tests": {
                "type": "array", "maxItems": MAX_NOTE_ITEMS,
                "items": {"type": "string", "minLength": 1, "maxLength": MAX_NOTE_CHARS},
            },
            "limitations": {
                "type": "array", "maxItems": MAX_NOTE_ITEMS,
                "items": {"type": "string", "minLength": 1, "maxLength": MAX_NOTE_CHARS},
            },
        },
        "required": ["schema_version", "status", "summary", "addressed_finding_ids",
                     "unaddressed", "edits", "suggested_tests", "limitations"],
    }


def provider_schema(context: ProposalContext) -> dict[str, Any]:
    return sp.provider_schema(proposal_schema(context))


def render_prompt(context: ProposalContext) -> str:
    targets = [{
        "id": target.key, "severity": target.severity, "summary": target.summary,
        "evidence": list(target.evidence), "remedy": target.remedy,
        "class_context": list(target.class_context), "claim_context": target.claim_context,
    } for target in context.targets]
    binding = {
        "mode": context.mode, "reviewed_snapshot": context.reviewed_snapshot,
        "structural_snapshot": context.structural_snapshot,
        "contract_digest": context.contract_digest,
        "plan_digest": context.plan_digest,
        "plan_source_kind": context.plan_source_kind,
    }
    plan = ""
    if context.mode == "plan":
        assert context.plan_bytes is not None
        plan = "\n\n=== EXACT UNNUMBERED PLAN TEXT ===\n" + context.plan_bytes.decode("utf-8")
    contract = context.contract_text or ""
    return (
        "The review is complete. Author only an unapplied candidate patch. Do not modify files, "
        "execute code, run tests, install packages, or browse. Satisfy governing requirements "
        "rather than treating suggested syntax as mandatory. Cover related affected sites and "
        "avoid unrelated cleanup. Decline unsupported or uncertain work; tests are suggestions "
        "only and must not be claimed as executed. Read current pinned source before choosing "
        "exact old_text. Return one complete object matching the supplied schema.\n\n"
        f"=== FROZEN STAKES ===\n{context.stakes}\n\n"
        f"=== SERVER BINDING ===\n{json.dumps(binding, sort_keys=True)}\n\n"
        f"=== CURRENT TARGETS ===\n{json.dumps(targets, ensure_ascii=False, sort_keys=True)}\n\n"
        f"=== DECLARATIVE CONTRACT ===\n{contract}"
        f"{plan}\n\n=== LOCAL RESPONSE CONTRACT ===\n"
        + json.dumps(proposal_schema(context), ensure_ascii=False, sort_keys=True)
    )


def _utf8(value: str, pointer: str, issues: list[str]) -> bytes:
    try:
        return value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        issues.append(f"{pointer}: string is not strict UTF-8")
        return b""


def _semantic(value: str, pointer: str, issues: list[str]) -> None:
    _utf8(value, pointer, issues)
    if not value.strip():
        issues.append(f"{pointer}: semantic text must be nonblank")


def _valid_path(path: str) -> str | None:
    if not path or path.startswith(('/', '\\')) or '\\' in path or re.match(r"^[A-Za-z]:", path):
        return "path must be relative and use forward slashes"
    parts = path.split("/")
    for part in parts:
        lowered = part.casefold()
        stem = lowered.split(".", 1)[0]
        if (not part or part in {".", ".."} or part.startswith(":")
                or not _PATH_COMPONENT.fullmatch(part)):
            return "path has an unsupported component"
        if lowered == ".git" or stem in _WINDOWS_RESERVED or part.endswith((".", " ")):
            return "path has a reserved or ambiguous component"
    return None


def _lines(data: bytes) -> list[bytes]:
    return data.splitlines(keepends=True)


def _diff_lines(original: bytes, proposed: bytes, old_label: bytes,
                new_label: bytes) -> bytes:
    rows = list(difflib.diff_bytes(
        difflib.unified_diff, _lines(original), _lines(proposed),
        fromfile=old_label, tofile=new_label, n=3, lineterm=b"\n",
    ))
    rendered = bytearray()
    for row in rows:
        if row.endswith(b"\n"):
            rendered.extend(row)
        else:
            rendered.extend(row + b"\n\\ No newline at end of file\n")
    return bytes(rendered)


def render_patch(files: Sequence[ProposedFile], *, plan: bool = False) -> bytes:
    output = bytearray()
    for item in sorted(files, key=lambda row: row.path):
        path = PLAN_LABEL if plan else item.path
        encoded = path.encode("ascii" if not plan else "utf-8")
        output.extend(b"diff --git a/" + encoded + b" b/" + encoded + b"\n")
        if item.original is None:
            output.extend(b"new file mode 100644\n")
            old_label = b"/dev/null"
            original = b""
        else:
            old_label = b"a/" + encoded
            original = item.original
        output.extend(_diff_lines(original, item.proposed, old_label, b"b/" + encoded))
    if len(output) > MAX_PATCH_BYTES:
        raise ProposalError([f"/: rendered patch exceeds {MAX_PATCH_BYTES} bytes"])
    return bytes(output)


def _source_text(content: SourceContent, entry: ProposalEntry, pointer: str,
                 issues: list[str]) -> str | None:
    data = content.pinned
    if len(data) > MAX_SOURCE_BYTES:
        issues.append(f"{pointer}: source exceeds invocation byte limit")
        return None
    if b"\0" in data:
        issues.append(f"{pointer}: binary source is unsupported")
    if b"\r" in data:
        issues.append(f"{pointer}: CRLF source is unsupported")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError:
        issues.append(f"{pointer}: source is not strict UTF-8")
        return None
    if entry.oid is not None:
        try:
            if git_objects.blob_oid(data, len(entry.oid)) != entry.oid:
                issues.append(f"{pointer}: pinned blob identity mismatch")
        except RuntimeError as exc:
            issues.append(f"{pointer}: {exc}")
    return text


def parse_and_render(context: ProposalContext, raw: str,
                     source_reader: SourceReader | None = None) -> ProposalResult:
    raw_issues: list[str] = []
    raw_bytes = _utf8(raw, "/", raw_issues)
    if raw_issues:
        raise ProposalError(raw_issues)
    if len(raw_bytes) > MAX_RAW_BYTES:
        raise ProposalError([f"/: raw response exceeds {MAX_RAW_BYTES} bytes"])
    try:
        value = sp.decode(raw, proposal_schema(context), max_chars=MAX_RAW_BYTES)
    except sp.ProtocolError as exc:
        raise ProposalError(str(exc).splitlines()) from exc

    issues: list[str] = []
    _semantic(value["summary"], "/summary", issues)
    for name in ("suggested_tests", "limitations"):
        for index, item in enumerate(value[name]):
            _semantic(item, f"/{name}/{index}", issues)
    addressed = value["addressed_finding_ids"]
    unaddressed = value["unaddressed"]
    for index, row in enumerate(unaddressed):
        _semantic(row["reason"], f"/unaddressed/{index}/reason", issues)
    partition = addressed + [row["finding_id"] for row in unaddressed]
    expected = [target.key for target in context.targets]
    if len(partition) != len(set(partition)) or set(partition) != set(expected):
        issues.append("/addressed_finding_ids: addressed and unaddressed IDs must exactly partition targets")
    if value["status"] == "declined":
        if addressed or value["edits"] or len(unaddressed) != len(expected):
            issues.append("/status: declined requires no edits/addressed IDs and a reason for every target")
    elif not addressed or not value["edits"]:
        issues.append("/status: proposed requires nonempty addressed IDs and edits")

    edits = value["edits"]
    edit_bytes = 0
    paths: list[str] = []
    unsafe_edits: set[int] = set()
    for index, edit in enumerate(edits):
        for field in ("old_text", "new_text"):
            text = edit[field]
            if isinstance(text, str):
                before = len(issues)
                edit_bytes += len(_utf8(text, f"/edits/{index}/{field}", issues))
                if len(issues) != before:
                    unsafe_edits.add(index)
        if context.mode == "branch" and isinstance(edit["path"], str):
            paths.append(edit["path"])
    if edit_bytes > MAX_EDIT_BYTES:
        issues.append(f"/edits: replacement text exceeds {MAX_EDIT_BYTES} bytes")
    if len(set(paths)) > MAX_PATHS:
        issues.append(f"/edits: proposal exceeds {MAX_PATHS} unique paths")

    files: list[ProposedFile] = []
    if value["status"] == "proposed":
        if context.mode == "plan":
            assert context.plan_bytes is not None
            entry = ProposalEntry(PLAN_LABEL, "file", "100644")
            source_reader = source_reader or (lambda unused: SourceContent(context.plan_bytes))
            files = _apply_edits(
                context, edits, (entry,), source_reader, issues,
                plan=True, unsafe_edits=unsafe_edits,
            )
        else:
            if source_reader is None:
                issues.append("/: repository proposal requires a pinned source reader")
            else:
                files = _apply_edits(
                    context, edits, context.entries, source_reader, issues,
                    plan=False, unsafe_edits=unsafe_edits,
                )
    if issues:
        raise ProposalError(issues)
    patch = render_patch(files, plan=context.mode == "plan") if files else b""
    status: Literal["proposed", "partial", "declined"]
    status = "declined" if value["status"] == "declined" else (
        "partial" if unaddressed else "proposed"
    )
    return ProposalResult(
        status, value["summary"], tuple(addressed),
        tuple((row["finding_id"], row["reason"]) for row in unaddressed),
        tuple(value["suggested_tests"]), tuple(value["limitations"]), tuple(files), patch,
        hashlib.sha256(patch).hexdigest(), value,
    )


def _apply_edits(context: ProposalContext, edits: Sequence[dict[str, Any]],
                 entries: Sequence[ProposalEntry], source_reader: SourceReader,
                 issues: list[str], *, plan: bool,
                 unsafe_edits: set[int] | None = None) -> list[ProposedFile]:
    unsafe_edits = unsafe_edits or set()
    by_path = {entry.path: entry for entry in entries}
    casefold_paths: dict[str, list[str]] = {}
    for entry in entries:
        casefold_paths.setdefault(entry.path.casefold(), []).append(entry.path)
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, edit in enumerate(edits):
        if index in unsafe_edits:
            continue
        pointer = f"/edits/{index}"
        path = PLAN_LABEL if plan else edit["path"]
        if not isinstance(path, str):
            issues.append(f"{pointer}/path: repository edit requires a string path")
            continue
        if not plan:
            path_issue = _valid_path(path)
            if path_issue:
                issues.append(f"{pointer}/path: {path_issue}")
            collisions = sorted(set(casefold_paths.get(path.casefold(), ())))
            if len(collisions) > 1:
                issues.append(
                    f"{pointer}/path: case-collides with ambiguous existing paths "
                    + repr(collisions)
                )
            elif collisions and collisions[0] != path:
                issues.append(f"{pointer}/path: case-collides with {collisions[0]!r}")
        grouped.setdefault(path, []).append((index, edit))

    total_source = 0
    result: list[ProposedFile] = []
    for path, rows in grouped.items():
        operations = {edit["operation"] for _, edit in rows}
        if len(operations) != 1:
            issues.append(f"/edits: path {path!r} mixes create and replace")
            continue
        operation = next(iter(operations))
        entry = by_path.get(path)
        if operation == "create":
            if plan:
                issues.append("/edits: plan creation is unsupported")
                continue
            if entry is not None:
                issues.append(f"/edits: create target {path!r} already exists")
                continue
            if len(rows) != 1 or rows[0][1]["old_text"] is not None:
                issues.append(f"/edits: create for {path!r} requires one null old_text")
                continue
            ancestor = ""
            for component in path.split("/")[:-1]:
                ancestor = f"{ancestor}/{component}".lstrip("/")
                parent = by_path.get(ancestor)
                if parent is not None and parent.kind != "directory":
                    issues.append(f"/edits: create ancestor {ancestor!r} is not a directory")
            if any(other != path and (other.startswith(path + "/") or path.startswith(other + "/"))
                   for other in grouped):
                issues.append(f"/edits: create target {path!r} conflicts with another edit path")
            data = _utf8(
                rows[0][1]["new_text"],
                f"/edits/{rows[0][0]}/new_text",
                issues,
            )
            if not data:
                issues.append(f"/edits/{rows[0][0]}/new_text: created file must be nonempty")
            if b"\r" in data or b"\0" in data:
                issues.append(f"/edits/{rows[0][0]}/new_text: source must be LF-only text")
            result.append(ProposedFile(path, "100644", None, data, None))
            continue

        if entry is None:
            issues.append(f"/edits: replace target {path!r} is absent")
            continue
        if entry.kind not in {"file", "executable"}:
            issues.append(f"/edits: replace target {path!r} is unsupported kind {entry.kind}")
            continue
        try:
            content = source_reader(entry)
        except SourceReadError as exc:
            issues.append(f"/edits/{rows[0][0]}/path: {exc}")
            continue
        total_source += len(content.pinned)
        text = _source_text(content, entry, f"/edits/{rows[0][0]}/path", issues)
        if text is None:
            continue
        spans: list[tuple[int, int, str, int]] = []
        for index, edit in rows:
            old = edit["old_text"]
            new = edit["new_text"]
            if not isinstance(old, str) or not old:
                issues.append(f"/edits/{index}/old_text: replace requires nonempty text")
                continue
            if old == new:
                issues.append(f"/edits/{index}: no-op replacement")
            occurrences: list[int] = []
            position = text.find(old)
            while position >= 0:
                occurrences.append(position)
                position = text.find(old, position + 1)
            if len(occurrences) != 1:
                detail = "checkout-view-diverged-from-pinned-blob" if (
                    not occurrences and content.checkout is not None
                    and _utf8(old, f"/edits/{index}/old_text", issues) in content.checkout
                ) else f"old_text occurs {len(occurrences)} times in pinned blob"
                issues.append(f"/edits/{index}/old_text: {detail}")
                continue
            start = occurrences[0]
            spans.append((start, start + len(old), new, index))
        spans.sort()
        for left, right in zip(spans, spans[1:]):
            if left[1] > right[0]:
                issues.append(f"/edits/{right[3]}: replacement overlaps another original span")
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            continue
        proposed = text
        for start, end, new, unused in reversed(spans):
            proposed = proposed[:start] + new + proposed[end:]
        encoded = _utf8(proposed, f"/edits/{rows[0][0]}/new_text", issues)
        if encoded == content.pinned:
            issues.append(
                f"/edits/{rows[0][0]}: replacement group leaves source unchanged"
            )
        if b"\r" in encoded or b"\0" in encoded:
            issues.append(f"/edits: result for {path!r} must be LF-only text")
        result.append(ProposedFile(path, entry.mode, content.pinned, encoded, entry.oid))
    if total_source > MAX_SOURCE_BYTES:
        issues.append(f"/edits: admitted source exceeds {MAX_SOURCE_BYTES} bytes")
    return result
