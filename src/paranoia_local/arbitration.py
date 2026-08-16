"""The arbitration protocol — every decision it makes, as pure functions.

`arbitrate` asks two frontier models, independently and cold, to choose between
the caller's options, then computes the verdict in Python. The design rationale
for each rule below (and the ten adversarial-review rounds that produced them)
lives in `docs/arbitration_plan.md`; this module is the mechanism.

The load-bearing invariants, because getting any of them wrong reports agreement
that was not reached:

- **Two id spaces.** The caller's stable ids are the record's vocabulary and never
  reach a decider; each decider sees its own high-entropy labels, disjoint from
  the other's, so an echoed label from anywhere fails membership rather than
  mapping to the wrong option (§2.4).
- **Counterbalanced order.** One decider sees canonical order, the other reversed,
  so no option is early for both (§2.3).
- **Regions, not anchors.** A citation is the interval actually carried; sameness
  is interval intersection, substantiation is strict point-in-interval (§2.5).
- **Substantiation.** Agreement counts only when each converging vote's decisive
  citation resolves, and in round 2 additionally lands inside a region novel to its
  own vendor — for any vendor that CHANGED selection, or whose round-1 vote was
  itself unsubstantiated (§3.5).

Everything here is deterministic and free of I/O: the git reads it needs are
injected by the caller.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Callable, Collection, Iterable, Mapping, Sequence

from .external_sources import normalize_text

# --- shape limits -----------------------------------------------------------

MIN_OPTIONS = 2
# The protocol this mechanizes caps options at four ("<=4 options, each with a
# stable id"); more than that is a sign the decision needs splitting.
MAX_OPTIONS = 4
MAX_CITATIONS = 3
# Lines of context carried either side of a citation anchor. Small on purpose: a
# larger window would let a whole advocacy document ride along as "evidence".
CONTEXT_LINES = 3
# Attempts to find a label set absent from the framing and the snapshot.
MAX_LABEL_ATTEMPTS = 8

LABEL_PREFIX = "OPTION-"
LABEL_HEX = 16
_LABEL_RE = re.compile(rf"^{LABEL_PREFIX}[0-9a-f]{{{LABEL_HEX}}}$")

# A caller id may not collide with these: `none` is a reserved trailer value, and
# `decision`/`context`/`hints` are the attestation's own fidelity field names — an
# option called `decision` would emit two `[decision]` sections and let one verdict
# satisfy both, so a semantic change to either could be stamped `attested`.
OPTION_KEYS = frozenset({"id", "statement"})
RESERVED_IDS = frozenset({"none", "decision", "context", "hints", "stakes"})
TRAILER_FIELDS = (
    "SELECTED",
    "SELECTED-RISK",
    "AUTHORITY",
    "NEW-OPTION",
    "CONSTRAINT",
    "PUBLISHER-AUTHORITY",
    "PASSAGE-ENTAILMENT",
    "DECISION-RELEVANCE",
    "DECISIVE-CITATION",
    "CITATIONS",
)

SEVERITIES = ("NONE", "MINOR", "MAJOR", "FATAL")
BLOCKING_SEVERITIES = frozenset({"MAJOR", "FATAL"})
AUTHORITIES = ("technical", "human-owner")

STAKES_UNSTATED = "unstated"
# One fixed sentence, byte-identical on every call, so an omitted stakes statement
# produces a uniform reading rather than an accidental one.
STAKES_DEFAULT = (
    "The operator did not state stakes. Assume a modest single-team internal "
    "tool: trusted operators, no hostile input, ordinary scale."
)


class ArbitrationError(ValueError):
    """Caller input or a model reply that cannot be used. Always fails the run."""


# --- options ----------------------------------------------------------------


@dataclass(frozen=True)
class Option:
    id: str
    statement: str


def validate_options(raw: object) -> tuple[Option, ...]:
    """Caller options → validated tuple, or raise.

    Requires an array of `{id, statement}`: a single free-text blob would make id
    assignment (and therefore presentation order) the server's guess at the
    caller's intent instead of the caller's own stable vocabulary.
    """
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ArbitrationError(
            "options must be an array of {id, statement} objects, not a string"
        )
    if not (MIN_OPTIONS <= len(raw) <= MAX_OPTIONS):
        raise ArbitrationError(
            f"options must number {MIN_OPTIONS}..{MAX_OPTIONS}, got {len(raw)}"
        )
    out: list[Option] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise ArbitrationError("each option must be an object with id and statement")
        # Silently ignoring an unknown key hides a typo in the one field whose
        # spelling the whole protocol keys on: `{"id": .., "statment": ..}` would
        # arbitrate an empty option rather than telling the caller.
        unknown = sorted(k for k in entry if k not in OPTION_KEYS)
        if unknown:
            raise ArbitrationError(
                f"option object has unknown key(s): {', '.join(unknown)} "
                f"(expected only {', '.join(sorted(OPTION_KEYS))})"
            )
        oid = str(entry.get("id", "")).strip()
        statement = str(entry.get("statement", "")).strip()
        if not oid:
            raise ArbitrationError("every option needs a stable id")
        if not statement:
            raise ArbitrationError(f"option {oid!r} has an empty statement")
        if oid.lower() in RESERVED_IDS:
            raise ArbitrationError(f"option id {oid!r} is reserved")
        if oid in TRAILER_FIELDS:
            raise ArbitrationError(f"option id {oid!r} collides with a trailer field")
        if _LABEL_RE.match(oid):
            raise ArbitrationError(f"option id {oid!r} collides with the label namespace")
        if oid in seen:
            raise ArbitrationError(f"duplicate option id {oid!r}")
        seen.add(oid)
        out.append(Option(id=oid, statement=statement))
    return tuple(out)


# Framing bounds, enforced at preflight so an input-only defect never costs a
# cleaner call. The numbers come from the first production run (issue #8): dense
# ~1,800-char options and a ~4,500-char decision could not be round-tripped through
# the cleaner without the cross-vendor attester scoring a fidelity change, while the
# hoisted shape it converged on — shared mechanism in `context`, each option stating
# only scope-of-adoption — landed at ~800 chars and passed first time.
MAX_OPTION_CHARS = 1200
MAX_DECISION_CHARS = 2500
# `context` carries shared detail, and it is not per-option, so its length cannot
# be a vote between the options. It gets a far looser bound.
MAX_CONTEXT_CHARS = 20000
MAX_STAKES_CHARS = 20000
MAX_HINTS = 32
MAX_HINT_REASON_CHARS = 1200
MAX_HINTS_CHARS = 20000
# Includes the fixed instructions, caller framing, any bounded correction, and the
# cleaner candidate. This is an admission bound, not a model quality budget.
MAX_CLEANING_PROMPT_CHARS = 180000
# Initial and one bounded correction decider prompt, including the fixed instruction
# block and every rendered packet field. This is an admission bound, not a quality budget.
MAX_DECIDER_PROMPT_CHARS = 240000
MAX_CLEANER_REPLY_CHARS = 50000
OPTION_RATIO_MAX = 2.0

_HOIST_REMEDY = (
    "Put only facts and specification shared by every option in `context`. Keep "
    "each option's distinct mechanism, scope, and consequences in that option's "
    "own concise statement, using parallel structure and comparable detail."
)


def preflight_framing(
    *, decision: str, context: str, options: Sequence[Option], cleaned: bool = True,
    stakes: str = "", hints: Sequence[Mapping[str, object]] = (),
) -> None:
    """Reject framing defects visible in the caller's own input, before spending a
    cleaner call on them.

    Three of the first four production invocations died after two Opus attempts each
    on exactly these arithmetic checks (issue #8). Same measurements, same message
    shapes — just moved ahead of the spend.

    The inter-option ratio is checked HERE rather than only after cleaning because
    it is structural: "adopt X, with this precedence and this invariant" carries more
    mechanism to state than "don't", so any scope decision trips it by construction
    and no amount of re-cleaning fixes it. Telling the caller up front, with the
    remedy, is the only useful response.
    """
    # The ratio is a BIAS bound — asymmetric detail is an argument regardless of
    # wording — so it holds whether or not a cleaner runs. The character caps are
    # CLEANER-CAPACITY bounds, justified by what can be round-tripped through the
    # cleaner without the attester scoring a fidelity change, so `clean: false` (which
    # sends the caller's statements verbatim and never invokes a cleaner) is not
    # subject to them.
    lengths = {o.id: max(1, len(o.statement)) for o in options}
    if lengths:
        longest = max(lengths, key=lengths.__getitem__)
        shortest = min(lengths, key=lengths.__getitem__)
        if lengths[longest] / lengths[shortest] > OPTION_RATIO_MAX:
            raise ArbitrationError(
                "options are not equalized: "
                f"{longest} is {lengths[longest]} chars, {shortest} is "
                f"{lengths[shortest]} (ratio must be <= {OPTION_RATIO_MAX}). "
                + _HOIST_REMEDY
            )
    if not cleaned:
        return
    for oid, n in lengths.items():
        if n > MAX_OPTION_CHARS:
            raise ArbitrationError(
                f"option statement {oid} is {n} chars (max {MAX_OPTION_CHARS}). "
                + _HOIST_REMEDY
            )
    if len(decision) > MAX_DECISION_CHARS:
        raise ArbitrationError(
            f"decision is {len(decision)} chars (max {MAX_DECISION_CHARS}). "
            "Move the supporting facts into `context`; the decision field states "
            "what is being chosen, not the evidence for it."
        )
    if len(context) > MAX_CONTEXT_CHARS:
        raise ArbitrationError(
            f"context is {len(context)} chars (max {MAX_CONTEXT_CHARS})"
        )
    if len(stakes) > MAX_STAKES_CHARS:
        raise ArbitrationError(
            f"stakes is {len(stakes)} chars (max {MAX_STAKES_CHARS})"
        )
    if len(hints) > MAX_HINTS:
        raise ArbitrationError(f"file hints number {len(hints)} (max {MAX_HINTS})")
    rendered_hints: list[str] = []
    for index, hint in enumerate(hints):
        path = str(hint.get("path", "")).strip()
        reason = str(hint.get("reason", "")).strip()
        if len(reason) > MAX_HINT_REASON_CHARS:
            raise ArbitrationError(
                f"file hint {index} reason is {len(reason)} chars "
                f"(max {MAX_HINT_REASON_CHARS})"
            )
        rendered_hints.append(f"- {path}" + (f" ({reason})" if reason else ""))
    hint_chars = len("\n".join(rendered_hints) or "None.")
    if hint_chars > MAX_HINTS_CHARS:
        raise ArbitrationError(
            f"file hints render to {hint_chars} chars (max {MAX_HINTS_CHARS})"
        )


def canonical_order(options: Iterable[Option]) -> tuple[Option, ...]:
    """Canonical order is sorted by caller id, never the caller's array order — so
    retyping the same options in a different order cannot change anything."""
    return tuple(sorted(options, key=lambda o: o.id))


def reject_reserved_tokens(fields: Mapping[str, str], tokens: Iterable[str]) -> None:
    """Raise if any token appears in any decider-visible field.

    Applied to the caller's input AND to the cleaner's output: the cleaner rewrites
    four of these fields, so it can introduce a token the caller never wrote. A
    caller id in the prose is rejected too — options are shown in different orders
    to the two deciders, so a statement referring to another option by id is
    broken under permutation regardless.
    """
    for token in tokens:
        if not token:
            continue
        for name, value in fields.items():
            if value and token in value:
                raise ArbitrationError(
                    f"reserved token {token!r} appears in {name!r}; "
                    "cross-reference options by content, not by id or label"
                )


def resolve_stakes(stakes: object) -> str:
    """`stakes` is required — it is the highest-leverage input to the severity tag,
    and severity is the one axis that gates. Declining it is explicit."""
    if stakes is None or not str(stakes).strip():
        raise ArbitrationError(
            "stakes is required; pass stakes='unstated' to accept the default reading"
        )
    text = str(stakes).strip()
    return STAKES_DEFAULT if text.lower() == STAKES_UNSTATED else text


# --- labels and presentation ------------------------------------------------


def derive_labels(seed: str, n_engines: int, n_options: int, attempt: int = 0) -> tuple[tuple[str, ...], ...]:
    """All `n_engines * n_options` labels, derived jointly and asserted distinct.

    Jointly, because domain separation by engine index does not *prove*
    non-collision: an intra-set duplicate would let two options share one accepted
    token, and a cross-set duplicate would defeat the membership backstop that
    catches echoes. The caller advances `attempt` and retries.
    """
    sets: list[tuple[str, ...]] = []
    for engine_index in range(n_engines):
        labels = []
        for position in range(n_options):
            material = f"{seed}|{attempt}|{engine_index}|{position}".encode()
            labels.append(LABEL_PREFIX + hashlib.sha256(material).hexdigest()[:LABEL_HEX])
        sets.append(tuple(labels))
    flat = [label for s in sets for label in s]
    if len(set(flat)) != n_engines * n_options:
        raise ArbitrationError("label derivation collided")
    return tuple(sets)


def forward_engine(seed: str, n_engines: int) -> int:
    """Which engine index sees canonical (unreversed) order.

    Derived from the recorded seed rather than the engine registry: registry index
    would hand the same vendor the caller's order on every decision, permanently
    correlating one vendor with primacy.
    """
    digest = hashlib.sha256(f"order|{seed}".encode()).hexdigest()
    return int(digest, 16) % n_engines


@dataclass(frozen=True)
class Presentation:
    """One decider's view: options in its own order under its own labels."""

    engine: str
    items: tuple[tuple[str, str], ...]  # (label, statement) in presentation order
    label_to_id: Mapping[str, str]
    id_to_label: Mapping[str, str]
    reversed_order: bool

    @property
    def labels(self) -> frozenset[str]:
        return frozenset(self.label_to_id)


def presentation_for(
    canonical: Sequence[Option],
    labels: Sequence[str],
    engine: str,
    *,
    reverse: bool,
) -> Presentation:
    """Build a decider's presentation.

    Reversal, not rotation: reversal makes every option's two ranks sum to N+1, so
    every option has the same mean rank. Rotation merely guarantees different
    ranks, which leaves later options late for both deciders.
    """
    order = list(reversed(canonical)) if reverse else list(canonical)
    items = tuple((labels[i], opt.statement) for i, opt in enumerate(order))
    label_to_id = {labels[i]: opt.id for i, opt in enumerate(order)}
    return Presentation(
        engine=engine,
        items=items,
        label_to_id=label_to_id,
        id_to_label={v: k for k, v in label_to_id.items()},
        reversed_order=reverse,
    )


def build_presentations(
    canonical: Sequence[Option], engines: Sequence[str], seed: str, attempt: int = 0
) -> tuple[Presentation, ...]:
    label_sets = derive_labels(seed, len(engines), len(canonical), attempt)
    fwd = forward_engine(seed, len(engines))
    return tuple(
        presentation_for(canonical, label_sets[i], engine, reverse=(i != fwd))
        for i, engine in enumerate(engines)
    )


def all_labels(presentations: Iterable[Presentation]) -> tuple[str, ...]:
    return tuple(label for p in presentations for label in sorted(p.label_to_id))


# --- citations and regions --------------------------------------------------


@dataclass(frozen=True)
class Citation:
    """`[<commit>@]<path>:<line>`. `commit` None means the pinned snapshot.

    Revision-aware because deciders are told to read git history: a bare
    `path:line` taken from an older revision would otherwise be silently resolved
    against the snapshot, substantiating a vote with bytes the decider never read.
    """

    path: str
    line: int
    commit: str | None = None

    def render(self) -> str:
        base = f"{self.path}:{self.line}"
        return f"{self.commit}@{base}" if self.commit else base


@dataclass(frozen=True)
class SourceReference:
    packet_id: str

    def render(self) -> str:
        return f"SOURCE:{self.packet_id}"


_CITATION_RE = re.compile(
    r"^(?:(?P<commit>[0-9a-fA-F]{7,40})@)?(?P<path>[^\s:][^\s]*?):(?P<line>\d+)$"
)


def _normalize_path(path: str) -> str:
    """No normalization at all — the path is used exactly as written.

    This function used to rewrite: strip `./`, collapse `..`, fold backslashes to
    `/`, drop a leading `/`. Every one of those rewrites was a defect of the same
    kind, found one spelling at a time across several review rounds, because a
    rewrite can map the path the decider read onto a *different* tracked file, and
    then the server carries and substantiates against bytes nobody cited:

    - `alias/../f.py` is `sub/f.py` through a directory symlink, but `f.py` lexically;
    - `policy\\choice.py` is a legal POSIX filename distinct from `policy/choice.py`;
    - `/etc/policy.py` would fold onto tracked `etc/policy.py`.

    Enumerating rejections cannot close that class — there is always another
    spelling. Not rewriting does: the path must be a literal entry in the cited
    commit's tree (enforced downstream by the object-type check in
    `evidence._blob`), so a citation either names exactly one real tracked file or it
    drops. A model that writes `./f.py` gets a dropped citation, which costs one
    `UNRESOLVED` — the cheap, self-announcing outcome.
    """
    if path.startswith("repository/"):
        path = path[len("repository/"):]
    if not path.strip():
        raise ArbitrationError(f"citation path is empty: {path!r}")
    return path


def parse_citations(field: str, *, limit: int = MAX_CITATIONS) -> tuple[Citation, ...]:
    """Parse the `CITATIONS`/`DECISIVE-CITATION` field ONLY.

    Never scavenged from prose: a `path:line` mentioned inside a `CONSTRAINT`
    sentence is not a citation, and treating it as one was how an earlier design
    let advocacy masquerade as evidence.
    """
    text = (field or "").strip()
    if not text or text.upper() == "NONE":
        return ()
    out: list[Citation] = []
    for chunk in text.split(","):
        token = chunk.strip()
        if not token:
            continue
        m = _CITATION_RE.match(token)
        if not m:
            continue  # unparseable citations are dropped, and the drop is recorded
        line = int(m.group("line"))
        if line < 1:
            continue
        try:
            path = _normalize_path(m.group("path"))
        except ArbitrationError:
            continue
        commit = m.group("commit")
        out.append(Citation(path=path, line=line, commit=commit.lower() if commit else None))
        if len(out) == limit:
            break
    return tuple(out)


def parse_decisive_citation(field: str) -> tuple[Citation, ...]:
    """Exactly `NONE`, or exactly ONE citation. Anything else substantiates nothing.

    Reusing the list parser with `limit=1` silently took the first entry, so
    `DECISIVE-CITATION: novel.py:20, own.py:10` parsed as `novel.py:20` alone. In
    round 2 a decider could put the carried novel region first and its own prior
    reason second, satisfy `anchor_within`, and have an ambiguous vote reported as
    reconciled. This field is the one thing substantiation rests on, so it is
    all-or-nothing.
    """
    text = (field or "").strip()
    if not text or text.upper() == "NONE":
        return ()
    if "," in text or len(text.split()) != 1:
        return ()
    return parse_citations(text, limit=1)


def parse_decisive_reference(field: str) -> Citation | SourceReference | None:
    text = (field or "").strip()
    if text.upper() == "NONE" or not text:
        return None
    if text.startswith("SOURCE:"):
        packet_id = text[len("SOURCE:"):]
        if re.fullmatch(r"src-[0-9a-f]{16}", packet_id):
            return SourceReference(packet_id)
        return None
    citations = parse_decisive_citation(text)
    return citations[0] if citations else None


@dataclass(frozen=True)
class Region:
    """The interval a citation actually carries, plus a digest per carried line.

    Identity is the canonical **path** and the **content of the lines transported**,
    compared over whatever span two regions share. `commit` is provenance only.

    Two weaker identities were tried and both manufactured false novelty:

    - `(commit, path)` — every run wraps `HEAD`, so a bare citation (resolving to
      the wrapper) and a `HEAD@…` citation of the same unchanged file keyed apart
      although they are byte-identical.
    - `(path, blob)` — git's blob id is the whole *file*, so two revisions that
      differ anywhere outside the cited window keyed apart although the carried
      lines are identical.

    In both cases both vendors appear to gain evidence, round 2 runs as a fresh
    sample over the same bytes, and each vendor can substantiate by citing the
    other's revision. Comparing the transported lines themselves is the only
    identity that tracks what round 2 actually transmits.

    Paths are canonicalized through the cited commit's symlink map before
    construction, so two aliases for one file are also one region.
    """

    commit: str
    path: str
    lo: int
    hi: int
    anchor: int
    # sha256 per line, index 0 == line `lo`. Bounded: regions are context-capped.
    line_digests: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Grouping key only — content equality is decided by `line_digests`."""
        return self.path

    def digest_at(self, line: int) -> str | None:
        idx = line - self.lo
        if 0 <= idx < len(self.line_digests):
            return self.line_digests[idx]
        return None


def digest_lines(lines: Iterable[str | bytes]) -> tuple[str, ...]:
    return tuple(
        hashlib.sha256(line if isinstance(line, bytes) else line.encode("utf-8", "replace"))
        .hexdigest()[:16]
        for line in lines
    )


def to_region(
    citation: Citation,
    *,
    commit: str,
    eof: int,
    lines: Sequence[str] = (),
    context: int = CONTEXT_LINES,
) -> Region:
    """`lines` is the full file's lines; the region keeps digests for `lo..hi` only."""
    lo = max(1, citation.line - context)
    hi = min(eof, citation.line + context)
    return Region(
        commit=commit,
        path=citation.path,
        lo=lo,
        hi=hi,
        anchor=citation.line,
        line_digests=digest_lines(lines[lo - 1 : hi]) if lines else (),
    )


def _overlap(a: Region, b: Region) -> tuple[int, int] | None:
    lo, hi = max(a.lo, b.lo), min(a.hi, b.hi)
    return (lo, hi) if lo <= hi else None


def same_region(a: Region, b: Region) -> bool:
    """Sameness for the novelty gate: same path, overlapping intervals, and the
    overlapping lines identical.

    Deliberately generous on the interval — two anchors a line apart carry
    near-identical windows, so treating them as distinct would let an evidence-free
    round 2 run. And decided on the transported lines, not the revision or the whole
    file, so neither a snapshot wrapper nor an unrelated edit elsewhere in the file
    can split one piece of evidence into two (see `Region`).
    """
    if a.path != b.path:
        return False
    span = _overlap(a, b)
    if span is None:
        return False
    if not a.line_digests or not b.line_digests:
        return True  # no content available to distinguish them; treat as the same
    return all(a.digest_at(n) == b.digest_at(n) for n in range(span[0], span[1] + 1))


def anchor_within(anchor_region: Region, carried: Region) -> bool:
    """Substantiation: the anchor LINE must sit inside the carried interval, and be
    the same line that was carried.

    Strictly point-in-interval, not intersection. At context 3 a carried region
    [104,110] and a fresh anchor at 113 expand to overlapping windows, but line 113
    was never carried — accepting it would count independent discovery as
    reconciliation. The digest check additionally rules out citing the same line
    number at a revision whose content differs.
    """
    if anchor_region.path != carried.path:
        return False
    if not (carried.lo <= anchor_region.anchor <= carried.hi):
        return False
    mine = anchor_region.digest_at(anchor_region.anchor)
    theirs = carried.digest_at(anchor_region.anchor)
    if mine is None or theirs is None:
        return True
    return mine == theirs


def merge_regions(regions: Iterable[Region]) -> tuple[Region, ...]:
    """Merge overlapping same-content intervals per path.

    Two regions of one path merge only when they overlap AND agree on the shared
    lines — otherwise they are different content at the same coordinates and must
    stay distinct. The merged interval keeps the first anchor; anchors matter only
    on unmerged citation regions.
    """
    by_key: dict[tuple[str, str], list[Region]] = {}
    for r in regions:
        # Grouped by (commit, path), so a merged region always describes ONE
        # revision. Merging across revisions spliced the other commit's tail
        # digests onto this commit's body: `read_region` reads the whole merged
        # interval from `current.commit`, so a round-2 citation into the other
        # revision's tail would pass `anchor_within` against bytes never sent.
        # Cross-revision duplicates still count as the same evidence for the
        # novelty gate (`same_region` is content-based); they are simply carried
        # separately.
        by_key.setdefault((r.commit, r.path), []).append(r)
    out: list[Region] = []
    for key in sorted(by_key):
        current: Region | None = None
        for r in sorted(by_key[key], key=lambda x: (x.lo, x.hi)):
            if current is None:
                current = r
            elif r.lo <= current.hi and same_region(current, r):
                current = _extend(current, r)
            else:
                out.append(current)
                current = r
        if current is not None:
            out.append(current)
    return tuple(out)


def _extend(current: Region, other: Region) -> Region:
    """Widen `current` to cover `other`, keeping per-line digests aligned to `lo`.

    Only ever called for two regions of the SAME commit and path (see
    `merge_regions`), so the appended digests describe the same bytes the widened
    interval will be read from.
    """
    if other.hi <= current.hi:
        return current
    digests = list(current.line_digests)
    if digests and other.line_digests:
        # append only the lines beyond current.hi, keeping index 0 == current.lo
        digests.extend(other.line_digests[current.hi - other.lo + 1 :])
    elif not current.line_digests:
        digests = []
    return replace(current, hi=other.hi, line_digests=tuple(digests))


def region_union(per_engine: Mapping[str, Sequence[Region]]) -> tuple[Region, ...]:
    """The digest-ordered union carried to BOTH deciders in round 2.

    Both get the same set: a round-2 session is cold, so withholding "its own"
    region would strip a vendor's decisive evidence from its own final vote. The
    order is content-derived so it is not one engine's findings first.
    """
    merged = merge_regions([r for regions in per_engine.values() for r in regions])
    return tuple(
        sorted(
            merged,
            key=lambda r: hashlib.sha256(
                f"{r.path}|{r.lo}|{r.hi}|{''.join(r.line_digests)}".encode()
            ).hexdigest(),
        )
    )


def gains_for(engine: str, union: Sequence[Region], own: Sequence[Region]) -> tuple[Region, ...]:
    """Regions in the union that do not overlap anything this vendor produced."""
    return tuple(r for r in union if not any(same_region(r, o) for o in own))


def round_two_permitted(
    union: Sequence[Region], own_by_engine: Mapping[str, Sequence[Region]]
) -> bool:
    """Round 2 runs only if EVERY decider gains a region.

    One-sided gain is refused deliberately: the decider that gains nothing would be
    resampling the same evidence, and a coin-flip agreement would then be reported
    as reconciliation.
    """
    if not union:
        return False
    return all(gains_for(e, union, own) for e, own in own_by_engine.items())


# --- decider replies --------------------------------------------------------


@dataclass(frozen=True)
class Vote:
    engine: str
    label: str
    selected: str  # caller-stable id, already de-permuted
    severity: str
    risk_text: str
    authority: str
    new_option: str | None
    constraint: str
    decisive: Citation | SourceReference | None
    citations: tuple[Citation, ...]
    publisher_authority: bool | None
    passage_entailment: bool | None
    decision_relevance: bool | None
    evidence_reasons: Mapping[str, str]


def _judgement(raw: str, field: str) -> tuple[bool | None, str]:
    text = raw.strip()
    if text.upper() == "N/A":
        return None, ""
    match = re.fullmatch(r"(YES|NO)\s+[—-]\s+(\S.*)", text, re.IGNORECASE)
    if not match:
        raise ArbitrationError(f"{field} must be N/A or YES/NO — <reason>")
    return match.group(1).upper() == "YES", match.group(2).strip()


def _trailer_values(text: str) -> dict[str, str]:
    """The trailer is the FINAL block of exactly the expected fields, each once.

    Scanning the whole reply and keeping the last occurrence of each field was
    lenient in a way that defeated `parse_decisive_citation`: a reply could emit
    `DECISIVE-CITATION: own.py:10` and then `DECISIVE-CITATION: novel.py:20`, and the
    all-or-nothing rule would never see the pair. Reading only the closing block
    still lets a model quote the format earlier while explaining itself — that text
    is not the last lines — while making a duplicate a parse failure.
    """
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    block, before = lines[-len(TRAILER_FIELDS):], lines[: -len(TRAILER_FIELDS)]
    found: dict[str, str] = {}
    for line in block:
        for field in TRAILER_FIELDS:
            prefix = f"{field}:"
            if line.upper().startswith(prefix):
                if field in found:
                    raise ArbitrationError(f"reply repeats the {field} trailer field")
                found[field] = line[len(prefix):].strip()
                break
    # A field line BEFORE the block is rejected too. Reading only the last lines was
    # not enough: an earlier `SELECTED-RISK: [MAJOR] …` or a first
    # `DECISIVE-CITATION` sits outside the slice and would be silently discarded,
    # dropping a blocking objection or the vote's real reason. The cost is that a
    # reply quoting the field names outside the block fails — cheap and visible,
    # against a discarded blocker that is neither.
    for line in before:
        upper = line.upper()
        for field in TRAILER_FIELDS:
            # Anywhere in the line, not just at its start: an inline qualification
            # like "The option has SELECTED-RISK: [MAJOR] breaks the writer" slips a
            # column-zero check while the closing `SELECTED-RISK: NONE` is accepted,
            # discarding the blocker.
            if f"{field}:" in upper:
                raise ArbitrationError(
                    f"reply mentions {field}: before its final trailer block; "
                    "these fields may appear only in the closing block"
                )
    return found


def parse_verdict(text: str, presentation: Presentation) -> Vote:
    """Parse one decider's reply, or raise.

    `SELECTED` must be an exact member of the labels issued to THIS decider. A
    label from the other decider's set, one seen in repository evidence, an echoed
    caller id, or an option named by its words all fail here rather than being
    guessed into a mapping.
    """
    values = _trailer_values(text)
    missing = [f for f in TRAILER_FIELDS if f not in values]
    if missing:
        raise ArbitrationError(f"reply is missing trailer field(s): {', '.join(missing)}")

    # Full-string match, not the first token: `SELECTED: <label> (the safe one)`
    # must fail rather than quietly discarding the trailing commentary, which could
    # be where the decider actually qualified its answer.
    label = values["SELECTED"].strip()
    if label not in presentation.label_to_id:
        raise ArbitrationError(
            f"SELECTED {label!r} is not a label issued to {presentation.engine}"
        )

    risk = values["SELECTED-RISK"]
    severity, risk_text = _parse_severity(risk)

    authority = values["AUTHORITY"].strip().lower()
    if authority not in AUTHORITIES:
        raise ArbitrationError(f"AUTHORITY must be one of {AUTHORITIES}, got {authority!r}")

    new_option_raw = values["NEW-OPTION"].strip()
    new_option = None if new_option_raw.upper() == "NONE" or not new_option_raw else new_option_raw

    decisive = parse_decisive_reference(values["DECISIVE-CITATION"])
    authority_ok, authority_reason = _judgement(
        values["PUBLISHER-AUTHORITY"], "PUBLISHER-AUTHORITY"
    )
    entailment_ok, entailment_reason = _judgement(
        values["PASSAGE-ENTAILMENT"], "PASSAGE-ENTAILMENT"
    )
    relevance_ok, relevance_reason = _judgement(
        values["DECISION-RELEVANCE"], "DECISION-RELEVANCE"
    )
    if isinstance(decisive, SourceReference):
        if None in (authority_ok, entailment_ok, relevance_ok):
            raise ArbitrationError("SOURCE decisive evidence requires three YES/NO judgements")
    elif any(value is not None for value in (authority_ok, entailment_ok, relevance_ok)):
        raise ArbitrationError("repository decisive evidence requires three N/A judgements")
    return Vote(
        engine=presentation.engine,
        label=label,
        selected=presentation.label_to_id[label],
        severity=severity,
        risk_text=risk_text,
        authority=authority,
        new_option=new_option,
        constraint=values["CONSTRAINT"].strip(),
        decisive=decisive,
        citations=parse_citations(values["CITATIONS"]),
        publisher_authority=authority_ok,
        passage_entailment=entailment_ok,
        decision_relevance=relevance_ok,
        evidence_reasons={
            "publisher_authority": authority_reason,
            "passage_entailment": entailment_reason,
            "decision_relevance": relevance_reason,
        },
    )


def _parse_severity(raw: str) -> tuple[str, str]:
    """`NONE` exactly, or `[SEV] <reason>`.

    `NONE` must be the WHOLE value: a prefix match would read
    `SELECTED-RISK: NONE [MAJOR] unsafe` as no risk at all and let a blocking
    objection become a `CONVERGED`.
    """
    text = (raw or "").strip()
    if text.upper() == "NONE":
        return "NONE", ""
    m = re.fullmatch(r"\[(MINOR|MAJOR|FATAL)\]\s*(\S.*)", text, re.IGNORECASE | re.DOTALL)
    if not m:
        raise ArbitrationError(
            f"SELECTED-RISK must be exactly NONE, or [MINOR]/[MAJOR]/[FATAL] "
            f"followed by a reason, got {text!r}"
        )
    return m.group(1).upper(), m.group(2).strip()


# --- verdict ----------------------------------------------------------------

CONVERGED = "CONVERGED"
BLOCKED = "BLOCKED"
REFRAME_REQUIRED = "REFRAME_REQUIRED"
UNRESOLVED = "UNRESOLVED"
FAILED = "FAILED"


@dataclass(frozen=True)
class Outcome:
    outcome: str
    selected: str | None
    reason: str


def compute_outcome(
    votes: Sequence[Vote],
    *,
    substantiated: Mapping[str, bool],
    failure: str | None = None,
) -> Outcome:
    """The whole verdict, in evaluation order.

    FAILED → REFRAME_REQUIRED → selections differ → BLOCKED → unsubstantiated →
    CONVERGED. `REFRAME_REQUIRED` precedes the selection comparison because a run
    that would read CONVERGED while a decider says something better exists is not
    a finished decision. BLOCKED precedes substantiation because it carries more
    signal and neither is a proceed. AUTHORITY appears nowhere: it is advisory.
    """
    if failure:
        return Outcome(FAILED, None, failure)
    if not votes:
        return Outcome(FAILED, None, "no decider replies")

    proposals = [v for v in votes if v.new_option]
    if proposals:
        return Outcome(
            REFRAME_REQUIRED,
            None,
            "; ".join(f"{v.engine}: {v.new_option}" for v in proposals),
        )

    selections = {v.selected for v in votes}
    if len(selections) != 1:
        return Outcome(
            UNRESOLVED,
            None,
            "; ".join(f"{v.engine} selected {v.selected}" for v in votes),
        )
    selected = selections.pop()

    blocking = [v for v in votes if v.severity in BLOCKING_SEVERITIES]
    if blocking:
        return Outcome(
            BLOCKED,
            selected,
            "; ".join(f"{v.engine} [{v.severity}] {v.risk_text}" for v in blocking),
        )

    unsubstantiated = [v.engine for v in votes if not substantiated.get(v.engine, False)]
    if unsubstantiated:
        return Outcome(
            UNRESOLVED,
            selected,
            "agreement not substantiated by resolved evidence: "
            + ", ".join(sorted(unsubstantiated)),
        )
    return Outcome(CONVERGED, selected, "unanimous, unblocked, substantiated")


def substantiation(
    votes: Sequence[Vote],
    *,
    resolve: Callable[[Citation], Region | None],
    carried: Mapping[str, Sequence[Region]] | None = None,
    moved: Collection[str] | None = None,
    source_packets: Mapping[str, tuple[str, bool]] | None = None,
) -> dict[str, bool]:
    """Per-engine substantiation.

    Round 1 (`carried` None): the decisive citation must resolve.

    Round 2: the carried-grounding rule is **anti-capitulation** — it proves a vendor
    that changed its mind was moved by evidence rather than by the mere fact of
    disagreement. So it applies only to vendors in `moved`. A vendor that held its
    round-1 selection has no capitulation to disprove and its position was already
    substantiated on its own resolved citation, so it needs only a citation that
    resolves.

    Applying it to every vendor produced a false negative on the first production run
    (issue #8): both vendors agreed, the flipping vendor grounded correctly on carried
    bytes, and the run still returned UNRESOLVED because the vendor that had been
    right all along cited the producer code instead of the artifact. The only region
    it could have grounded in was the other vendor's argument for the option it had
    rejected — so the rule demanded it cite the evidence against its own conclusion.

    `moved=None` means "treat every vendor as moved", the conservative reading.
    Supporting `CITATIONS` never substantiate: otherwise a decider could keep its own
    prior region as its real reason and merely append the novel one.
    """
    out: dict[str, bool] = {}
    for vote in votes:
        if vote.decisive is None:
            out[vote.engine] = False
            continue
        if isinstance(vote.decisive, SourceReference):
            packet = (source_packets or {}).get(vote.decisive.packet_id)
            out[vote.engine] = bool(
                (carried is None or (moved is not None and vote.engine not in moved))
                and packet
                and packet[1]
                and normalize_text(vote.constraint) == normalize_text(packet[0])
                and vote.publisher_authority is True
                and vote.passage_entailment is True
                and vote.decision_relevance is True
            )
            continue
        region = resolve(vote.decisive)
        if region is None:
            out[vote.engine] = False
            continue
        if carried is None:
            out[vote.engine] = True
            continue
        if moved is not None and vote.engine not in moved:
            out[vote.engine] = True
            continue
        out[vote.engine] = any(
            anchor_within(region, c) for c in carried.get(vote.engine, ())
        )
    return out


# --- advisory ---------------------------------------------------------------


def advisory_line(votes: Sequence[Vote]) -> str:
    """`AUTHORITY` never gates, so it must be impossible to miss: an always-present
    field with an explicit value, rather than a suffix on the outcome enum (which
    would break exact-match consumers)."""
    flagged = sorted(v.engine for v in votes if v.authority == "human-owner")
    if not flagged:
        return "none"
    if len(flagged) == len(votes):
        return "human-owner (flagged by: both)" if len(votes) == 2 else "human-owner (flagged by: all)"
    return f"human-owner (flagged by: {', '.join(flagged)})"
