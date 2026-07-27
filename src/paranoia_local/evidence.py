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
- `resolve_citation` / `read_region` — the bounded citation reads round 2 carries.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .arbitration import ArbitrationError, Citation, Region, digest_lines

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
    """Every path in the snapshot, byte-faithfully.

    `-z` is load-bearing, not a style choice. Without it `ls-tree --name-only` QUOTES
    any path containing a backslash, a quote, or a non-ASCII byte —
    `policy\\choice.py` comes back as `"policy\\\\choice.py"` — and `core.quotePath=false`
    does not suppress it for this command. Since citation and hint paths are matched
    against this set literally and never normalized, a quoted entry would make every
    legitimate reference to such a file unresolvable, which is the failure the literal
    match exists to avoid rather than cause. It also splits on NUL, so a path
    containing a newline cannot forge two entries.
    """
    out = _git(["ls-tree", "-r", "--name-only", "-z", commit], repo)
    return frozenset(part for part in out.split("\0") if part)


def symlink_map(repo: Path, commit: str) -> dict[str, str]:
    """`{path: target}` for every mode-120000 entry in the snapshot.

    Serves two callers: the escape check below, and citation canonicalization —
    `git show <commit>:<symlink>` returns the *target string*, not the referent's
    contents, so an uncanonicalized alias citation would carry a filename as
    though it were source, and would key as a different region from its referent.
    """
    # `-z` for the same reason as `tree_paths`: a quoted key would never match the
    # verbatim path a citation carries, so an aliased file would silently stop being
    # canonicalized.
    out = _git(["ls-tree", "-r", "-z", commit], repo)
    links: dict[str, str] = {}
    for line in out.split("\0"):
        if not line:
            continue
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 2 and parts[0] == SYMLINK_MODE:
            links[path] = _symlink_target(repo, commit, path)
    return links


def _symlink_target(repo: Path, commit: str, path: str) -> str:
    """A symlink's target, VERBATIM.

    A git symlink blob is exactly the target with no trailing newline, so stripping
    it only ever removes real characters. With `alias.py -> " real.py "` and both
    `" real.py "` and `real.py` tracked, a stripped target resolves the citation to
    the wrong file — the decider reads one and substantiation checks the other.
    """
    r = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=repo, capture_output=True)
    if r.returncode != 0:
        return ""
    return r.stdout.decode("utf-8", errors="surrogateescape")


def _resolve_link(path: str, target: str) -> str | None:
    """Resolve a symlink target relative to its own directory. None if it escapes.

    Lexical, and used ONLY by the escape gate — `canonical_path` refuses targets
    containing `..` rather than trusting this. For escape detection the lexical
    reading is the conservative one: it treats a symlink component as a single
    level where the filesystem may expand it to several, so it can over-report an
    escape but not miss one.
    """
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
    """Follow the snapshot's symlink graph to the referent. None if it cannot be
    resolved EXACTLY as the decider's worktree would.

    A target containing `..` fails closed. `_resolve_link` interprets components
    lexically, which diverges from the filesystem as soon as an earlier component is
    itself a symlink: with `alias -> linkdir/../f.py` and `linkdir -> sub/dir`, the
    worktree reads `sub/f.py` while lexical popping yields root `f.py`. Both are
    tracked, so the wrong one would pass membership and be substantiated against —
    the same substitution class that removing path normalization closed, surviving
    at the one boundary where the string comes from repository data instead of a
    model.

    Reproducing filesystem semantics exactly would need component-by-component
    resolution that expands each symlink before interpreting the next `..`.
    Declining to resolve is simpler, provably right, and costs one `UNRESOLVED` on
    an uncommon shape — the same trade taken everywhere else here.
    """
    seen: set[str] = set()
    current = path
    for _ in range(_MAX_SYMLINK_HOPS):
        if current not in links:
            return current
        if current in seen:
            return None
        seen.add(current)
        target = links[current]
        if any(seg == ".." for seg in target.split("/")):
            return None
        nxt = _resolve_link(current, target)
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


class LinkResolver:
    """Per-commit lookups a citation needs, resolved once and cached: the full
    object id of whatever revision it named, and that commit's symlink map.

    Both matter for *region identity*, which is what the round-2 novelty gate and
    substantiation key on.

    - **Full oid.** A revision is spelled many ways — `8a8877f`, `8a8877f1f4a8`, or
      omitted entirely for the snapshot. Keying on the string as supplied makes two
      spellings of one commit two regions, so each vendor "gains" the other's
      spelling, round 2 carries identical bytes twice, and quoting the alternate
      spelling substantiates a vote that reconciled nothing.
    - **Symlink map.** A revision-prefixed citation resolves in ITS OWN commit, so
      it needs that commit's map; the snapshot's would not describe it.
    """

    def __init__(self, repo: Path, snapshot: str, snapshot_links: dict[str, str] | None = None):
        self._repo = repo
        self._links: dict[str, dict[str, str]] = {}
        self._paths: dict[str, frozenset[str]] = {}
        self._oids: dict[str, str | None] = {}
        self._snapshot = snapshot
        if snapshot_links is not None:
            self._links[snapshot] = snapshot_links

    def oid(self, rev: str) -> str | None:
        """`rev` as its full commit id, or None if it does not resolve."""
        if rev not in self._oids:
            r = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
                cwd=self._repo, capture_output=True,
            )
            out = r.stdout.decode("utf-8", errors="replace").strip()
            self._oids[rev] = out if r.returncode == 0 and out else None
        return self._oids[rev]

    def paths(self, commit: str) -> frozenset[str]:
        if commit not in self._paths:
            try:
                self._paths[commit] = tree_paths(self._repo, commit)
            except RuntimeError:
                self._paths[commit] = frozenset()
        return self._paths[commit]

    def for_commit(self, commit: str) -> dict[str, str]:
        if commit not in self._links:
            try:
                self._links[commit] = symlink_map(self._repo, commit)
            except RuntimeError:
                self._links[commit] = {}
        return self._links[commit]


def resolve_citation(
    repo: Path,
    citation: Citation,
    *,
    snapshot: str,
    links: dict[str, str] | LinkResolver,
    context: int,
) -> tuple[Region, str] | None:
    """A citation → its carried region and the lines themselves, or None if it drops.

    Order matters: canonicalize through the symlink map FIRST, then bounds-check,
    then read. Doing it the other way keys aliases as distinct regions and carries
    a symlink's target string as though it were source.
    """
    resolver = links if isinstance(links, LinkResolver) else LinkResolver(repo, snapshot, links)
    # Canonicalize the REVISION before anything else, so two spellings of one commit
    # — and a bare citation versus an explicitly snapshot-prefixed one — are one
    # region rather than two.
    commit = resolver.oid(citation.commit or snapshot)
    if commit is None:
        return None
    path = canonical_path(citation.path, resolver.for_commit(commit))
    # The path must be a LITERAL entry in the tree. Since nothing normalizes it
    # (see `arbitration._normalize_path`), this is what guarantees one citation
    # names one real file: git accepts `./f.py` as a lookup, but `./f.py` and
    # `f.py` are different strings and would key as different regions.
    if path is None or path not in resolver.paths(commit):
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
    region = Region(
        commit=commit, path=path, lo=lo, hi=hi, anchor=citation.line,
        # Digests of the lines actually transported, so region identity tracks what
        # round 2 sends rather than the whole file or the revision it came from.
        line_digests=digest_lines(lines[lo - 1 : hi]),
    )
    return region, read_region(repo, region) or ""


def read_region(repo: Path, region: Region) -> str | None:
    """The bytes of EXACTLY `region.lo..region.hi`.

    Reading from the anchor and re-expanding would under-carry a merged region —
    two anchors merge to a wider interval than either expansion — while
    substantiation is checked against the merged bounds, so a citation inside the
    merged span but outside what was actually sent would count as carried evidence.
    """
    text = _blob(repo, region.commit, region.path)
    if text is None:
        return None
    lines = text.splitlines()
    lo = max(1, region.lo)
    hi = min(len(lines), region.hi)
    if lo > hi:
        return None
    return "\n".join(f"{n:>6}  {lines[n - 1]}" for n in range(lo, hi + 1))


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
        # NOT normalized, for the same reason citation paths are not (see
        # `arbitration._normalize_path`): every rewrite can map one tracked file onto
        # another. `policy\\choice.py` is a legal POSIX filename that git tracks
        # distinctly from `policy/choice.py`, so folding the separator would send BOTH
        # deciders to a different file's bytes — and since the attester is shown the
        # path the server resolved, not the one the caller wrote, the swap is invisible
        # to it. Literal tree membership, and a caller using `./` or a backslash as an
        # alias gets an error naming the exact path to write instead.
        if raw not in present:
            raise ArbitrationError(
                f"file hint {raw!r} is not in the snapshot as spelled "
                "(paths are used verbatim and must match a tracked path exactly; "
                "ignored/untracked files are not captured)"
            )
        out.append({"path": raw, "reason": str(hint.get("reason", "")).strip()})
    return out
