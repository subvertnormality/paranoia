"""Git reads that arbitration needs and the review packet does not.

Kept out of `orientation.py` because these serve a different purpose: not
assembling a briefing, but *bounding* what the deciders can have seen so a
`CONVERGED` is describable by the recorded snapshot.

Four jobs:

- `refs_digest` — detect history moving under the deciders during the run.
- `symlink_map` / `escaping_symlinks` — tree membership does not bound what a
  path resolves to; a tracked symlink can point at live external bytes.
- `scan_for_tokens` — prove the derived option labels appear nowhere the deciders
  can read them.
- `read_lines` / `blob_eof` — the bounded citation reads that round 2 carries.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .arbitration import ArbitrationError, Citation, Region

# Modes are the only way to tell a symlink from a file in a tree listing;
# `ChangeEntry` in orientation.py carries no mode, which is why the escape hole
# existed in the first place.
SYMLINK_MODE = "120000"
_MAX_SYMLINK_HOPS = 8

SNAPSHOT_REF_PREFIX = "refs/paranoia/arbitrate"


def _git(args: list[str], cwd: Path, *, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if r.returncode != 0:
        if not check:
            return ""
        raise RuntimeError(
            f"git {' '.join(args)} failed: {r.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return r.stdout.decode("utf-8", errors="replace")


# --- ref movement -----------------------------------------------------------


def retain_snapshot(repo: Path, commit: str, stamp: str) -> str:
    """Pin the snapshot behind a ref so its evidence survives `git gc`.

    Opt-in only. `wrap_commit` deliberately creates no ref and the README promises
    "no ref is ever created", so durable evidence replay is a choice the operator
    makes per call rather than a promise quietly broken for everyone. Delete with
    `git update-ref -d <ref>`.
    """
    ref = f"{SNAPSHOT_REF_PREFIX}/{stamp}-{commit[:12]}"
    _git(["update-ref", ref, commit], repo)
    return ref


def refs_digest(repo: Path) -> str:
    """A digest of every ref AND the reflog.

    Ref tips alone are defeated by an advance-and-restore cycle: a rebase that
    lands and then resets a branch inside the run window leaves the tips identical
    while the deciders could have read the transient commit. The reflog records the
    movement. A repository with reflogs disabled loses that half of the detection.
    """
    refs = _git(["for-each-ref", "--format=%(refname) %(objectname)"], repo, check=False)
    reflog = _git(["reflog", "--all", "--format=%H %gd"], repo, check=False)
    return hashlib.sha256((refs + "\n--\n" + reflog).encode("utf-8", "replace")).hexdigest()


# --- tree membership and symlinks -------------------------------------------


def tree_paths(repo: Path, commit: str) -> frozenset[str]:
    out = _git(["ls-tree", "-r", "--name-only", commit], repo)
    return frozenset(line for line in out.splitlines() if line)


def symlink_map(repo: Path, commit: str) -> dict[str, str]:
    """`{path: target}` for every mode-120000 entry in the snapshot.

    Serves two callers: the escape check below, and citation canonicalization —
    `git show <commit>:<symlink>` returns the *target string*, not the referent's
    contents, so an uncanonicalized alias citation would carry a filename as
    though it were source, and would key as a different region from its referent.
    """
    out = _git(["ls-tree", "-r", commit], repo)
    links: dict[str, str] = {}
    for line in out.splitlines():
        if not line:
            continue
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 2 and parts[0] == SYMLINK_MODE:
            links[path] = _git(["show", f"{commit}:{path}"], repo).strip()
    return links


def _resolve_link(path: str, target: str) -> str | None:
    """Resolve a symlink target relative to its own directory. None if it escapes."""
    if target.startswith("/"):
        return None
    base = path.rsplit("/", 1)[0] if "/" in path else ""
    parts = [p for p in base.split("/") if p] if base else []
    for seg in target.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts) if parts else None


def escaping_symlinks(repo: Path, commit: str, links: dict[str, str] | None = None) -> list[str]:
    """Snapshot symlinks whose target is absolute or normalizes outside the root.

    Per-link validation is sufficient for chains: a link to a link is itself an
    entry, so an escaping hop is caught wherever in the chain it occurs. Rejecting
    all symlinks would be simpler but refuses repositories with benign in-tree ones.
    """
    links = symlink_map(repo, commit) if links is None else links
    return sorted(p for p, t in links.items() if _resolve_link(p, t) is None)


def canonical_path(path: str, links: dict[str, str]) -> str | None:
    """Follow the snapshot's symlink graph to the referent. None if it escapes or loops."""
    seen: set[str] = set()
    current = path
    for _ in range(_MAX_SYMLINK_HOPS):
        if current not in links:
            return current
        if current in seen:
            return None
        seen.add(current)
        nxt = _resolve_link(current, links[current])
        if nxt is None:
            return None
        current = nxt
    return None


# --- label clearance --------------------------------------------------------


def scan_for_tokens(repo: Path, commit: str, tokens: list[str]) -> list[str]:
    """Which of `tokens` appear in the snapshot's blobs, its pathnames, or a
    reachable commit message.

    `git grep <commit>` reads blob contents only — not filenames, not commit
    messages — while a decider has `Glob`, `git ls-files`, `git log`, and
    `git show`. Historical blob contents are deliberately NOT scanned: that is
    unbounded work against a 64-bit accidental-collision risk, and the residual is
    documented rather than implied away.
    """
    if not tokens:
        return []
    hits: set[str] = set()
    paths = "\n".join(sorted(tree_paths(repo, commit)))
    messages = _git(["log", "--all", "--format=%B"], repo, check=False)
    for token in tokens:
        if token in paths or token in messages:
            hits.add(token)
            continue
        r = subprocess.run(
            ["git", "grep", "-F", "-l", "-e", token, commit],
            cwd=repo, capture_output=True,
        )
        # rc 0 = found, 1 = not found, >1 = a real failure we must not read as "clear"
        if r.returncode == 0:
            hits.add(token)
        elif r.returncode > 1:
            raise RuntimeError(
                "git grep failed: " + r.stderr.decode("utf-8", errors="replace").strip()
            )
    return sorted(hits)


# --- citation reads ---------------------------------------------------------


def _blob(repo: Path, commit: str, path: str) -> str | None:
    """The file's contents, or None unless `path` is a regular blob at `commit`.

    The type check is load-bearing, not defensive: `git show <commit>:<dir>`
    succeeds and prints a *tree listing*, and on a submodule gitlink it prints
    `commit <sha>`. Either would be carried into round 2 as though it were source.
    """
    spec = f"{commit}:{path}"
    t = subprocess.run(["git", "cat-file", "-t", spec], cwd=repo, capture_output=True)
    if t.returncode != 0 or t.stdout.decode().strip() != "blob":
        return None
    r = subprocess.run(["git", "show", spec], cwd=repo, capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def resolve_citation(
    repo: Path,
    citation: Citation,
    *,
    snapshot: str,
    links: dict[str, str],
    context: int,
) -> tuple[Region, str] | None:
    """A citation → its carried region and the lines themselves, or None if it drops.

    Order matters: canonicalize through the symlink map FIRST, then bounds-check,
    then read. Doing it the other way keys aliases as distinct regions and carries
    a symlink's target string as though it were source.
    """
    commit = citation.commit or snapshot
    path = canonical_path(citation.path, links) if commit == snapshot else citation.path
    if path is None:
        return None
    text = _blob(repo, commit, path)
    if text is None:
        return None
    lines = text.splitlines()
    eof = len(lines)
    if eof == 0 or not (1 <= citation.line <= eof):
        return None
    lo = max(1, citation.line - context)
    hi = min(eof, citation.line + context)
    body = "\n".join(f"{n:>6}  {lines[n - 1]}" for n in range(lo, hi + 1))
    return Region(commit=commit, path=path, lo=lo, hi=hi, anchor=citation.line), body


def validate_hints(repo: Path, commit: str, hints: list[dict]) -> list[dict]:
    """Every hint must be a repo-relative path present in the snapshot tree.

    Closes two holes: an absolute or `../` path points both deciders at live
    mutable bytes outside the worktree, and `git add -A` omits *ignored untracked*
    files, so a hint naming one references something the recorded commit does not
    contain. Rejection beats force-capture, which would change what a snapshot is.
    """
    present = tree_paths(repo, commit)
    out: list[dict] = []
    for hint in hints:
        raw = str(hint.get("path", "")).strip()
        if not raw:
            raise ArbitrationError("a file hint has no path")
        if raw.startswith("/") or ".." in raw.split("/"):
            raise ArbitrationError(
                f"file hint {raw!r} must be a repo-relative path inside the snapshot"
            )
        norm = "/".join(seg for seg in raw.replace("\\", "/").split("/") if seg not in ("", "."))
        if norm not in present:
            raise ArbitrationError(
                f"file hint {norm!r} is not in the snapshot "
                "(ignored/untracked files are not captured)"
            )
        out.append({"path": norm, "reason": str(hint.get("reason", "")).strip()})
    return out
