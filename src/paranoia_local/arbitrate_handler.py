"""The `arbitrate` handler — orchestration only; every judgement is in
`arbitration.py` and every git read is in `evidence.py`.

Shape of a run:

    preflight → snapshot → validate → clean → attest → fan out (round 1)
      → verdict → §2.11 gate → maybe fan out (round 2) → verdict → report

Two things make this different from the other handlers, which are each a single
`engine.run`: it drives *both* vendors, and it never lets a model decide anything
the protocol depends on. If you are changing this file, the invariant to preserve
is that no model output reaches another model except repository bytes the server
itself read.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import arbitration as arb
from . import engines as eng
from . import evidence, logs, orientation, prompts
from .arbitration import ArbitrationError, Citation, Option, Presentation, Region, Vote
from .config import load_repo_config, resolve
from .worktree import worktree_at

Clock = Callable[[], str]

# Per-phase caps, so the worst serial path (300+300 retry, 300+300, 900, 900)
# stays under a client's 3600s tool timeout — that timeout bounds the WHOLE
# arbitration, not each subprocess.
CLEAN_TIMEOUT_SEC = 300
DECIDE_TIMEOUT_SEC = 900

SNAPSHOT_REF_PREFIX = "refs/paranoia/arbitrate"


def _default_clock() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


@dataclass(frozen=True)
class Cast:
    """One decider's turn: the vote, the exact prompt body it saw, and its raw
    reply. The prompt and reply are kept so the audit can reconstruct the decision
    after the snapshot commit is garbage-collected."""

    vote: Vote
    body: str
    raw: str


@dataclass
class Packet:
    """The cleaned, attested framing every decider sees identically."""

    decision: str
    stakes: str
    context: str
    hints: list[dict]
    statements: dict[str, str]  # caller id -> statement shown to deciders
    cleaning: str  # attested | attested-after-retry | skipped
    attestation: str


# --- preflight and snapshot -------------------------------------------------


def _preflight(engines: Sequence[eng.Engine]) -> None:
    """Both CLIs must be present. There is no degraded single-vendor mode: two
    rounds against one vendor is not arbitration."""
    needed = {e.binary for e in engines} | {
        eng.get_engine(eng.CLEANER_ENGINE).binary,
        eng.get_engine(eng.ATTESTER_ENGINE).binary,
    }
    missing = sorted(b for b in needed if shutil.which(b) is None)
    if missing:
        raise ArbitrationError(
            f"arbitrate needs both CLIs on PATH; not found: {', '.join(missing)}"
        )


def _snapshot(repo: Path) -> str:
    """Always snapshot the WORKING TREE, never a bare HEAD.

    The caller is deciding about the code as it stands, including uncommitted work;
    offering a HEAD/dirty choice would let a run return unanimous decisions about
    stale bytes.
    """
    if orientation.has_head(repo):
        head = orientation.resolve_head(repo)
        return orientation.wrap_commit(repo, orientation.snapshot_tree(repo, head), head)
    tree = orientation.snapshot_tree(repo, orientation.empty_tree(repo))
    return orientation.wrap_commit(repo, tree, None)


# --- cleaning and attestation ----------------------------------------------


_BLOCK_RE = re.compile(r"^===\s*(?P<name>[A-Z]+)\s*===\s*$")


def parse_cleaned_packet(
    text: str, ids: Sequence[str], *, caller_gave_context: bool = False
) -> dict[str, Any]:
    """Parse the cleaner's blocks and enforce fidelity mechanically.

    The id set must round-trip 1:1. A "neutralizer" that quietly drops or merges an
    option is worse than no cleaner at all, so this is checked rather than trusted.
    """
    stripped = (text or "").strip()
    if stripped.upper().startswith("INSUFFICIENT:"):
        raise ArbitrationError(f"cleaner refused: {stripped[len('INSUFFICIENT:'):].strip()}")

    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in stripped.splitlines():
        m = _BLOCK_RE.match(line.strip())
        if m:
            current = m.group("name")
            blocks[current] = []
            continue
        if current:
            blocks[current].append(line)
    for required in ("DECISION", "OPTIONS"):
        if required not in blocks:
            raise ArbitrationError(f"cleaner output has no === {required} === block")

    statements: dict[str, str] = {}
    for line in blocks["OPTIONS"]:
        if not line.strip():
            continue
        oid, sep, statement = line.partition(":")
        if not sep:
            continue
        oid, statement = oid.strip(), statement.strip()
        if oid in statements:
            raise ArbitrationError(f"cleaner emitted option {oid!r} twice")
        statements[oid] = statement

    if set(statements) != set(ids):
        raise ArbitrationError(
            "cleaner changed the option id set: "
            f"expected {sorted(ids)}, got {sorted(statements)}"
        )
    empty = [k for k, v in statements.items() if not v]
    if empty:
        raise ArbitrationError(f"cleaner emitted empty statement(s) for {empty}")

    return {
        "decision": "\n".join(blocks["DECISION"]).strip(),
        "context": _cleaned_context(blocks.get("CONTEXT", []), caller_gave_context),
        "hints": parse_cleaned_hints(blocks.get("HINTS", [])),
        "statements": statements,
    }


def _cleaned_context(lines: Sequence[str], caller_gave_context: bool) -> str:
    """`CONTEXT: None.` is how the cleaner spells "the caller gave me none" — the same
    sentinel the HINTS block uses, and treating it as content would make an absent
    field look populated.

    But it is only a sentinel when the caller supplied nothing. A caller whose context
    legitimately *is* `None.` — the observed output of the thing being adjudicated, say
    — must have it reach the deciders verbatim, so when context was supplied the block
    is passed through untouched.
    """
    text = "\n".join(lines).strip()
    if caller_gave_context:
        return text
    return "" if text.rstrip(".").strip().lower() in ("", "none", "n/a") else text


def parse_cleaned_hints(lines: Sequence[str]) -> dict[str, str]:
    """`{path: neutralized reason}` from the cleaner's HINTS block.

    Parsed rather than kept as prose because the hint *reasons* are a steering
    channel in their own right — "the approved implementation" reaching both
    deciders unchanged would be exactly the shared anchoring the cleaner exists to
    remove, while the run still reported `CLEANING: attested`.
    """
    out: dict[str, str] = {}
    for raw in lines:
        line = raw.strip().lstrip("-").strip()
        if not line or line.upper().startswith("NONE"):
            continue
        path, _, reason = line.partition(":")
        path = path.strip()
        if path:
            out[path] = reason.strip()
    return out


def check_length_bands(cleaned: Mapping[str, str], original: Mapping[str, str]) -> None:
    """What the CLEANER is answerable for, which is not the same as what the caller is.

    The caller's own inter-option ratio is bounded at preflight
    (`arb.preflight_framing`). What remains here is that the cleaner must not make the
    asymmetry *worse* than the framing it was handed — equalized input coming back
    skewed is the cleaner introducing a length vote.

    There is deliberately **no lower bound** on how far a statement may compress.
    Issue #8: an option whose text was largely consequence-narration ("Outcome under
    this option: …") was cut to 0.09x and rejected, though the meaning was intact —
    the cleaner had correctly identified restatement as compressible. A character
    ratio cannot tell dropped substance from dropped padding; the cross-vendor
    fidelity attestation can, and it checks exactly that, per option, by id. The floor
    was a cheap proxy for a check that already exists in stronger form.

    Growth keeps its ceiling: a statement that doubles has gained content from
    somewhere, and the id-set check cannot see added prose inside a preserved id.
    """
    cleaned_lengths = {k: max(1, len(v)) for k, v in cleaned.items()}
    orig_lengths = {k: max(1, len(v)) for k, v in original.items()}
    if cleaned_lengths:
        got = max(cleaned_lengths.values()) / min(cleaned_lengths.values())
        allowed = arb.OPTION_RATIO_MAX
        if orig_lengths:
            allowed = max(allowed, max(orig_lengths.values()) / min(orig_lengths.values()))
        if got > allowed:
            longest = max(cleaned_lengths, key=cleaned_lengths.get)
            shortest = min(cleaned_lengths, key=cleaned_lengths.get)
            raise ArbitrationError(
                "the cleaner left the options less equalized than the framing it was "
                f"given: {longest} is {cleaned_lengths[longest]} chars, {shortest} is "
                f"{cleaned_lengths[shortest]} (ratio {got:.2f}, allowed {allowed:.2f})"
            )
    for oid, text in cleaned.items():
        before = orig_lengths.get(oid, 1)
        ratio = max(1, len(text)) / before
        if ratio > 2.0:
            raise ArbitrationError(
                f"cleaned option {oid} is {ratio:.2f}x its original length — the "
                "cleaner may compress, but not add (max 2.0x)"
            )


@dataclass(frozen=True)
class Attestation:
    fidelity: dict[str, str]
    neutrality_pass: bool
    neutrality_note: str
    stakes_advocacy: str | None
    raw: str

    @property
    def changed(self) -> list[str]:
        return sorted(k for k, v in self.fidelity.items() if v.upper() == "CHANGED")

    @property
    def ok(self) -> bool:
        return self.neutrality_pass and not self.changed and self.stakes_advocacy is None


def parse_attestation(text: str, expected: Sequence[str]) -> Attestation:
    """Strict: every expected field exactly once, each `PRESERVED` or `CHANGED`,
    exactly one neutrality verdict, and a stakes verdict.

    A lenient parser made an *incomplete* attestation look like a passing one:
    `FIDELITY: decision PRESERVED` alone, or a value of `UNKNOWN`, would satisfy
    "nothing said CHANGED" and stamp a semantically altered packet `attested`.
    An unparseable reply is cheap — it costs the one retry — whereas a falsely
    attested packet steers both deciders silently.
    """
    fidelity: dict[str, str] = {}
    neutrality: bool | None = None
    note = ""
    stakes: str | None = None
    stakes_seen = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if not upper.startswith(("FIDELITY:", "NEUTRALITY:", "STAKES-ADVOCACY:")):
            # No commentary. `NEUTRALITY: PASS` followed by "The cleaned wording still
            # favors option A." was otherwise accepted as clean, and the biased packet
            # went to both deciders stamped `attested`.
            raise ArbitrationError(
                f"attestation contains text outside its three verdict lines: {line!r}"
            )
        if upper.startswith("FIDELITY:"):
            for part in line[len("FIDELITY:"):].split(";"):
                field, _, verdict = part.strip().rpartition(" ")
                field, verdict = field.strip(), verdict.strip().upper()
                if not field:
                    continue
                if verdict not in ("PRESERVED", "CHANGED"):
                    raise ArbitrationError(
                        f"attestation gave {field!r} the value {verdict!r}; "
                        "only PRESERVED or CHANGED are meaningful"
                    )
                if field in fidelity:
                    raise ArbitrationError(f"attestation reported {field!r} twice")
                fidelity[field] = verdict
        elif upper.startswith("NEUTRALITY:"):
            if neutrality is not None:
                raise ArbitrationError("attestation gave two NEUTRALITY verdicts")
            body = line[len("NEUTRALITY:"):].strip()
            # `PASS` must be the WHOLE value. A prefix match accepted
            # "PASS but the wording favors option A" as a clean bill of health and
            # stamped a demonstrably biased packet `attested`, sending that same
            # bias to both deciders.
            if body.upper() == "PASS":
                neutrality = True
            elif body.upper().startswith("FAIL") and body[len("FAIL"):].strip():
                neutrality = False
                note = body[len("FAIL"):].strip()
            else:
                raise ArbitrationError(
                    f"NEUTRALITY must be exactly PASS, or FAIL with a note, got {body!r}"
                )
        elif upper.startswith("STAKES-ADVOCACY:"):
            if stakes_seen:
                raise ArbitrationError("attestation gave two STAKES-ADVOCACY verdicts")
            stakes_seen = True
            body = line[len("STAKES-ADVOCACY:"):].strip()
            # Same reasoning: "NONE despite recommending A" is not NONE.
            if body.upper() == "NONE":
                stakes = None
            elif body.upper().startswith("PRESENT") and body[len("PRESENT"):].strip():
                stakes = body[len("PRESENT"):].strip()
            else:
                raise ArbitrationError(
                    "STAKES-ADVOCACY must be exactly NONE, or PRESENT with the "
                    f"advocating words, got {body!r}"
                )

    missing = [f for f in expected if f not in fidelity]
    if missing:
        raise ArbitrationError(f"attestation did not cover: {', '.join(missing)}")
    unexpected = [f for f in fidelity if f not in expected]
    if unexpected:
        raise ArbitrationError(f"attestation covered unknown field(s): {', '.join(unexpected)}")
    if neutrality is None:
        raise ArbitrationError("attestation has no NEUTRALITY verdict")
    if not stakes_seen:
        raise ArbitrationError("attestation has no STAKES-ADVOCACY verdict")
    return Attestation(fidelity, neutrality, note, stakes, (text or "").strip())


# --- rendering --------------------------------------------------------------


def render_decider_body(
    packet: Packet,
    presentation: Presentation,
    carried: Sequence[tuple[Region, str]] = (),
) -> str:
    """One decider's task body.

    Says nothing about another model, a round number, or what the outcomes are: a
    decider that knows agreement is the test plays a different game. Round-2 bodies
    differ from round-1 bodies only by the evidence block, and the two deciders'
    bodies differ only in the options block.
    """
    parts = [
        "=== DECISION ===\n" + packet.decision,
        "=== STAKES ===\n" + packet.stakes,
    ]
    if packet.context:
        parts.append("=== CONTEXT ===\n" + packet.context)
    options_block = "\n".join(f"{label}: {statement}" for label, statement in presentation.items)
    parts.append("=== OPTIONS (choose exactly one; copy its label verbatim) ===\n" + options_block)
    if packet.hints:
        hints = "\n".join(
            f"- {h['path']}" + (f" ({h['reason']})" if h.get("reason") else "")
            for h in packet.hints
        )
        parts.append(
            "=== FILES SUGGESTED AS STARTING POINTS ===\n"
            "Non-exhaustive. Establish relevance yourself and read whatever else bears on this.\n"
            + hints
        )
    if carried:
        blocks = "\n\n".join(
            f"--- {region.path} lines {region.lo}-{region.hi}"
            + (f" (at {region.commit[:12]})" if region.commit else "")
            + f" ---\n{body}"
            for region, body in carried
        )
        parts.append(
            "=== CODE REGIONS RELEVANT TO THIS DECISION ===\n"
            "These regions were read from the repository. They are unverified as to "
            "significance: verify what each implies for yourself against the code, and "
            "disregard any that does not bear on the decision.\n\n" + blocks
        )
    return "\n\n".join(parts)


def render_trailer(
    outcome: arb.Outcome,
    *,
    advisory: str,
    cleaning: str,
    snapshot: str,
    seed: str,
    refs_moved: bool,
    audit: str,
    rounds: int,
) -> str:
    """Every field a pure token and always present, so nothing is signalled by
    absence — and the advisory is never a suffix on the outcome enum, which would
    break exact-match consumers."""
    return "\n".join(
        [
            f"ARBITRATION: {outcome.outcome}",
            f"SELECTED: {outcome.selected or 'none'}",
            f"ADVISORY: {advisory}",
            "AUTHORITY-POLICY: advisory — a Parallax CLASSIFICATION:B would escalate; "
            "this tool does not",
            f"CLEANING: {cleaning}",
            f"SNAPSHOT: {snapshot}",
            f"ORDER-SEED: {seed}",
            f"REFS-MOVED: {'yes' if refs_moved else 'no'}",
            f"AUDIT: {audit}",
            f"ROUNDS: {rounds}",
        ]
    )


def render_record_block(
    outcome: arb.Outcome,
    *,
    subject: str,
    rounds: int,
    per_round: Sequence[Mapping[str, Vote]],
    advisory: str,
) -> str:
    """A paste-ready record, assembled from parsed fields only — no model prose, so
    transcribing it cannot reintroduce interpretation."""
    lines = [
        f"DECISION: {subject or '(no subject given)'}",
        f"OUTCOME: {outcome.outcome}",
        f"SELECTED: {outcome.selected or 'none'}",
        f"ADVISORY: {advisory}",
        f"ROUNDS RUN: {rounds}",
    ]
    for i, votes in enumerate(per_round, 1):
        for engine in sorted(votes):
            v = votes[engine]
            cite = v.decisive.render() if v.decisive else "none"
            lines.append(
                f"round {i} · {engine}: selected {v.selected} · risk "
                f"{v.severity} · authority {v.authority} · decisive {cite}"
            )
    if len(per_round) == 2:
        flips = [
            f"{e}: {per_round[0][e].selected} -> {per_round[1][e].selected}"
            for e in sorted(per_round[1])
            if e in per_round[0] and per_round[0][e].selected != per_round[1][e].selected
        ]
        lines.append("ROUND-2 FLIPS: " + (", ".join(flips) if flips else "none"))
    lines.append(f"REASON: {outcome.reason}")
    return "\n".join(lines)


# --- the handler ------------------------------------------------------------


def arbitrate(
    arguments: dict[str, Any],
    *,
    engine: eng.Engine | None = None,  # accepted for dispatch symmetry; unused
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
    engines: Sequence[eng.Engine] | None = None,
    run_agent: Callable[..., str] | None = None,
) -> str:
    deciders = list(engines) if engines is not None else list(eng.all_engines())
    agent = run_agent or _run_agent
    progress = on_progress or (lambda _msg: None)

    try:
        return _arbitrate(arguments, deciders, agent, log_dir, now, progress)
    except ArbitrationError as exc:
        # A failure still returns the full trailer. "Every field is always present"
        # must hold on the error path too, or a caller that parses `ARBITRATION:`
        # gets nothing and has to fall back to reading prose.
        #
        # It also still writes an audit record. The first production run rejected three
        # framings and left nothing on disk, so gate churn could only be reconstructed
        # from terminal scrollback (issue #8, fix 7). A rejection is the cheapest thing
        # this tool produces and the most useful thing to count.
        audit = logs.write_log(
            log_dir,
            tool="arbitrate",
            record={
                "outcome": arb.FAILED,
                "reason": str(exc),
                "gate": type(exc).__name__,
                "rounds": [],
                "raw_input": {
                    k: arguments.get(k)
                    for k in ("decision", "options", "context", "stakes", "files")
                },
            },
            timestamp=now(),
        )
        return "\n".join(
            [
                "# Arbitration: FAILED",
                "",
                str(exc),
                "",
                render_trailer(
                    arb.Outcome(arb.FAILED, None, str(exc)),
                    advisory="none",
                    cleaning="not reached",
                    snapshot="none",
                    seed=str(arguments.get("order_seed") or "none"),
                    refs_moved=False,
                    audit=str(audit) if audit else "none",
                    rounds=0,
                ),
            ]
        )


def _arbitrate(
    arguments: dict[str, Any],
    deciders: list[eng.Engine],
    agent: Callable[..., str],
    log_dir: Path,
    now: Clock,
    progress: Callable[[str], None],
) -> str:
    repo_path = arguments.get("repo_path")
    if not repo_path:
        raise ArbitrationError("repo_path is required: every constraint must be repo-verifiable")
    repo = Path(repo_path).resolve()
    if not (repo / ".git").exists():
        raise ArbitrationError(f"not a git repo (no .git): {repo}")
    cfg = load_repo_config(repo)

    decision = str(arguments.get("decision", "")).strip()
    if not decision:
        raise ArbitrationError("decision is required")
    options = arb.validate_options(arguments.get("options"))
    canonical = arb.canonical_order(options)
    stakes = arb.resolve_stakes(resolve("stakes", arguments.get("stakes"), cfg, None))
    context = str(arguments.get("context", "") or "").strip()
    subject = str(arguments.get("subject", "") or "").strip()
    do_clean = bool(arguments.get("clean", True))
    seed = str(arguments.get("order_seed") or uuid.uuid4().hex)
    retain = bool(arguments.get("retain_snapshot", False))
    models = dict(arguments.get("models") or {})
    cleaner_model = str(arguments.get("cleaner_model") or eng.CLEANER_MODEL)
    effort = resolve("effort", arguments.get("effort"), cfg, "medium")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))

    # Input-only defects, checked before a single agent call: three of the first four
    # production invocations died after two Opus attempts each on exactly these
    # measurements (issue #8, fix 5).
    arb.preflight_framing(
        decision=decision, context=context, options=canonical, cleaned=do_clean
    )

    _preflight(deciders)

    progress("snapshotting the working tree")
    # Digest BEFORE the snapshot, and again after it: a commit landing while the
    # snapshot is being built would otherwise become part of the baseline, so both
    # deciders could read it through `git log --all` and the run would still report
    # REFS-MOVED: no against an older SNAPSHOT.
    refs_at_start = evidence.refs_digest(repo)
    snapshot = _snapshot(repo)
    refs_before = evidence.refs_digest(repo)
    if refs_before != refs_at_start:
        raise ArbitrationError(
            "repository refs moved while the snapshot was being taken, so the "
            "snapshot cannot describe what the deciders would read"
        )
    # The post-snapshot digest IS the baseline — re-reading it would reopen the very
    # window just closed, letting a commit that landed in between become accepted
    # history. The opt-in retain ref is therefore created after the final check, at
    # the end of the run, so our own write never masks operator movement either.

    links = evidence.symlink_map(repo, snapshot)
    # A revision-prefixed citation resolves in its OWN commit, so it needs that
    # commit's symlink map, not the snapshot's.
    resolver = evidence.LinkResolver(repo, snapshot, links)
    escaping = evidence.escaping_symlinks(repo, snapshot, links)
    if escaping:
        raise ArbitrationError(
            "snapshot contains symlink(s) whose target escapes the repository, so the "
            f"deciders could read unrecorded bytes: {', '.join(escaping)}"
        )
    hints = evidence.validate_hints(repo, snapshot, list(arguments.get("files") or []))

    # Caller-side token hygiene: option ids may not appear in anything a decider
    # reads. Options are shown in DIFFERENT orders, so a statement referring to
    # another option by id is broken under permutation regardless.
    caller_ids = [o.id for o in canonical]
    visible = {
        "decision": decision,
        "context": context,
        "stakes": stakes,
        **{f"statement[{o.id}]": o.statement for o in canonical},
        **{f"hint[{h['path']}]": h.get("reason", "") for h in hints},
    }
    arb.reject_reserved_tokens(visible, caller_ids)

    originals = {o.id: o.statement for o in canonical}
    packet, cleaning_note = _clean_and_attest(
        agent=agent,
        repo=repo,
        decision=decision,
        stakes=stakes,
        context=context,
        hints=hints,
        originals=originals,
        do_clean=do_clean,
        cleaner_model=cleaner_model,
        progress=progress,
    )

    # Present the CLEANED statements, not the caller's originals — the presentation
    # is what the deciders read, so building it from `canonical` would discard the
    # de-biasing entirely while still reporting `CLEANING: attested`.
    shown = arb.canonical_order(
        Option(id=o.id, statement=packet.statements[o.id]) for o in canonical
    )

    # Labels must be absent from the framing AND from the snapshot: deciders search
    # the repository, so a fixed vocabulary cannot be kept out of a corpus they are
    # supposed to read.
    presentations, attempts = _clear_labels(
        repo=repo,
        snapshot=snapshot,
        canonical=shown,
        deciders=deciders,
        seed=seed,
        packet=packet,
    )

    engine_names = [p.engine for p in presentations]
    progress(f"round 1: {', '.join(engine_names)}")
    casts1 = _fan_out(
        agent=agent, repo=repo, snapshot=snapshot, deciders=deciders,
        presentations=presentations, packet=packet, carried={}, models=models,
        effort=effort, web_search=web_search,
    )
    round1 = [c.vote for c in casts1]

    def resolve_region(citation: Citation) -> Region | None:
        got = evidence.resolve_citation(
            repo, citation, snapshot=snapshot, links=resolver, context=arb.CONTEXT_LINES
        )
        return got[0] if got else None

    per_round: list[dict[str, Vote]] = [{v.engine: v for v in round1}]
    transcripts: list[list[Cast]] = [casts1]
    carried_regions: list[tuple[Region, str]] = []
    sub1 = arb.substantiation(round1, resolve=resolve_region)
    outcome = arb.compute_outcome(round1, substantiated=sub1)
    rounds = 1
    carried_note = "round 2 not run"

    if outcome.outcome == arb.UNRESOLVED and len({v.selected for v in round1}) > 1:
        own = {
            v.engine: [r for r in (resolve_region(c) for c in _cited(v)) if r is not None]
            for v in round1
        }
        union = arb.region_union(own)
        if arb.round_two_permitted(union, own):
            progress("round 2: reconciling on carried evidence")
            carried_bodies = _read_union(repo, union)
            # Substantiate against what was ACTUALLY carried, not the pre-transport
            # union: a region whose bytes failed to read was never sent, so it
            # cannot be the evidence a vote was reconciled by.
            sent = [region for region, _ in carried_bodies]
            carried = {v.engine: carried_bodies for v in round1}
            casts2 = _fan_out(
                agent=agent, repo=repo, snapshot=snapshot, deciders=deciders,
                presentations=presentations, packet=packet, carried=carried,
                models=models, effort=effort, web_search=web_search,
            )
            round2 = [c.vote for c in casts2]
            transcripts.append(casts2)
            per_round.append({v.engine: v for v in round2})
            gained = {e: arb.gains_for(e, sent, own[e]) for e in own}
            # Carried grounding is anti-capitulation, so it is owed only by a vendor
            # whose selection actually moved (issue #8).
            first = {v.engine: v.selected for v in round1}
            moved = {v.engine for v in round2 if first.get(v.engine) != v.selected}
            # Waiving carried grounding rests on the held position ALREADY being
            # substantiated in round 1. A vendor that reached round 2 without a
            # resolving decisive citation has no such standing, so it must ground in
            # gained evidence like a mover: otherwise a vote that was never
            # substantiated at all rides to CONVERGED on a citation that merely
            # resolves, while the other vendor moves onto its supporting region.
            moved |= {v.engine for v in round2 if not sub1.get(v.engine, False)}
            sub2 = arb.substantiation(
                round2,
                resolve=resolve_region,
                carried={e: list(g) for e, g in gained.items()},
                moved=moved,
            )
            outcome = arb.compute_outcome(round2, substantiated=sub2)
            rounds = 2
            carried_regions = carried_bodies
            carried_note = f"{len(sent)} region(s) carried to both deciders"
        else:
            carried_note = (
                "round 2 withheld: no novel snapshot-resolved evidence for both deciders, "
                "so a second round would be a fresh sample rather than a reconciliation"
            )

    refs_moved = evidence.refs_digest(repo) != refs_before
    if retain and not refs_moved:
        # The ONE mode that writes a ref, and only once the run is known clean:
        # `wrap_commit` deliberately creates none and the README promises as much,
        # so durable evidence replay is opt-in rather than a promise quietly broken.
        evidence.retain_snapshot(repo, snapshot, now())
    final_votes = list(per_round[-1].values())
    if refs_moved:
        outcome = arb.compute_outcome(
            final_votes,
            substantiated={v.engine: True for v in final_votes},
            refs_moved=True,
        )

    advisory = arb.advisory_line(final_votes)
    record = render_record_block(
        outcome, subject=subject, rounds=rounds, per_round=per_round, advisory=advisory
    )
    audit = logs.write_log(
        log_dir,
        tool="arbitrate",
        record={
            "repo": str(repo),
            "snapshot": snapshot,
            "order_seed": seed,
            "label_attempts": attempts,
            "cleaning": cleaning_note,
            "attestation": packet.attestation,
            "raw_input": {
                "decision": decision, "stakes": stakes, "context": context,
                "options": originals, "files": hints,
            },
            "cleaned": {
                "decision": packet.decision, "context": packet.context,
                "statements": packet.statements,
            },
            "label_maps": {p.engine: dict(p.label_to_id) for p in presentations},
            # The prompts, the replies, and the bytes that crossed — everything the
            # decision was actually made on. `SNAPSHOT` is provenance only (the
            # wrapper commit is unreferenced and gc reclaims it), so if this record
            # does not hold them, the run is unauditable once that happens.
            "rounds": [
                {
                    cast.vote.engine: {
                        **_vote_record(cast.vote),
                        "prompt": cast.body,
                        "reply": cast.raw,
                    }
                    for cast in casts
                }
                for casts in transcripts
            ],
            "carried_evidence": [
                {
                    "commit": region.commit, "path": region.path,
                    "lo": region.lo, "hi": region.hi, "body": body,
                }
                for region, body in carried_regions
            ],
            "outcome": outcome.outcome,
            "selected": outcome.selected,
            "reason": outcome.reason,
            "refs_moved": refs_moved,
        },
        timestamp=now(),
    )

    return _render_report(
        outcome=outcome, packet=packet, originals=originals, presentations=presentations,
        per_round=per_round, advisory=advisory, snapshot=snapshot, seed=seed,
        refs_moved=refs_moved, audit=str(audit) if audit else "FAILED could not write log",
        rounds=rounds, record=record, carried_note=carried_note,
    )


def _cited(vote: Vote) -> list[Citation]:
    """Every citation a vote offers — decisive plus supporting. Used to build the
    carried union; substantiation still looks only at the decisive one."""
    out = list(vote.citations)
    if vote.decisive:
        out.insert(0, vote.decisive)
    return out


def _vote_record(vote: Vote) -> dict[str, Any]:
    return {
        "label": vote.label,
        "selected": vote.selected,
        "severity": vote.severity,
        "risk": vote.risk_text,
        "authority": vote.authority,
        "new_option": vote.new_option,
        "constraint": vote.constraint,
        "decisive": vote.decisive.render() if vote.decisive else None,
        "citations": [c.render() for c in vote.citations],
    }


def _read_union(repo: Path, union: Sequence[Region]) -> list[tuple[Region, str]]:
    """Read each merged region as EXACTLY `lo..hi`.

    Re-deriving the window from the anchor would under-carry a merged region — two
    anchors merge to a span wider than either expansion — while substantiation is
    checked against the merged bounds. A round-2 citation inside the merged span
    but outside what was actually sent would then count as carried evidence.
    """
    out: list[tuple[Region, str]] = []
    for region in union:
        body = evidence.read_region(repo, region)
        if body:
            out.append((region, body))
    return out


def _clear_labels(
    *,
    repo: Path,
    snapshot: str,
    canonical: Sequence[Option],
    deciders: Sequence[eng.Engine],
    seed: str,
    packet: Packet,
) -> tuple[tuple[Presentation, ...], int]:
    framing = "\n".join(
        [packet.decision, packet.stakes, packet.context, *packet.statements.values()]
        + [h["path"] + " " + h.get("reason", "") for h in packet.hints]
    )
    names = [e.name for e in deciders]
    for attempt in range(arb.MAX_LABEL_ATTEMPTS):
        presentations = arb.build_presentations(canonical, names, seed, attempt)
        labels = list(arb.all_labels(presentations))
        in_framing = [t for t in labels if t in framing]
        in_repo = evidence.scan_for_tokens(repo, snapshot, labels)
        if not in_framing and not in_repo:
            return presentations, attempt
    raise ArbitrationError(
        f"could not derive option labels absent from the framing and the snapshot "
        f"after {arb.MAX_LABEL_ATTEMPTS} attempts"
    )


def _clean_and_attest(
    *,
    agent: Callable[..., str],
    repo: Path,
    decision: str,
    stakes: str,
    context: str,
    hints: list[dict],
    originals: Mapping[str, str],
    do_clean: bool,
    cleaner_model: str,
    progress: Callable[[str], None],
) -> tuple[Packet, str]:
    if not do_clean:
        return (
            Packet(
                decision=decision, stakes=stakes, context=context, hints=hints,
                statements=dict(originals), cleaning="skipped",
                attestation="(cleaning skipped by caller — framing is the caller's own, un-de-biased)",
            ),
            "skipped",
        )

    # Only fields the caller supplied are attestable. Naming `context` when none was
    # passed produced `fidelity changed: ['context']` on the first production run —
    # an error about a field the caller had no control over (issue #8, fix 4).
    attest_fields = ["decision"]
    if context:
        attest_fields.append("context")
    if hints:
        attest_fields.append("hints")
    attest_fields.extend(originals)

    complaint = ""
    last_error: str | None = None
    # One retry only, and deliberately: a longer loop would hill-climb the framing
    # against the attester until it passed, which is optimization, not attestation.
    for attempt in range(2):
        progress("cleaning the framing" if attempt == 0 else "re-cleaning after attestation")
        cleaned_raw = agent(
            engine_name=eng.CLEANER_ENGINE, model=cleaner_model,
            instructions=prompts.CLEANER_INSTRUCTIONS,
            body=_clean_body(decision, stakes, context, hints, originals, complaint),
            cwd=None, effort="medium", web_search=False,
            timeout=CLEAN_TIMEOUT_SEC, text_only=True,
        )
        try:
            parsed = parse_cleaned_packet(
                cleaned_raw, list(originals), caller_gave_context=bool(context)
            )
            if context and not parsed["context"]:
                # Dropping a supplied context is invisible downstream: rendered back to
                # the attester as "None." it matches a caller context that also reads
                # "None.", so fidelity passes while the deciders receive nothing.
                raise ArbitrationError(
                    "the cleaner dropped the supplied context block; it may neutralize "
                    "the context but not remove it"
                )
            if parsed["context"] and not context:
                # A context the caller never wrote is the cleaner adding facts, which
                # it is forbidden to do — and it cannot be attested against anything.
                raise ArbitrationError(
                    "the cleaner invented a context block; no context was supplied, "
                    "and the cleaner may not add facts to the framing"
                )
            check_length_bands(parsed["statements"], originals)
            cleaned_hints = _merge_hints(hints, parsed["hints"])
            arb.reject_reserved_tokens(
                {
                    "decision": parsed["decision"],
                    "context": parsed["context"],
                    **{f"statement[{k}]": v for k, v in parsed["statements"].items()},
                    **{f"hint[{h['path']}]": h["reason"] for h in cleaned_hints},
                },
                list(originals),
            )
        except ArbitrationError as exc:
            last_error = str(exc)
            complaint = f"Your previous attempt was rejected: {exc}\nFix exactly that."
            continue

        progress("attesting the cleaned framing (cross-vendor)")
        attested_raw = agent(
            engine_name=eng.ATTESTER_ENGINE, model=eng.ATTESTER_MODEL,
            instructions=prompts.ATTEST_INSTRUCTIONS,
            body=_attest_body(decision, stakes, context, hints, cleaned_hints, originals, parsed),
            cwd=None, effort="low", web_search=False,
            timeout=CLEAN_TIMEOUT_SEC, text_only=True,
        )
        try:
            attestation = parse_attestation(attested_raw, attest_fields)
        except ArbitrationError as exc:
            last_error = f"attestation unusable: {exc}"
            complaint = f"An independent auditor's reply was unusable: {exc}\nRe-clean and try again."
            continue
        if attestation.stakes_advocacy:
            raise ArbitrationError(
                "the stakes text advocates for an option, and stakes is not the "
                f"cleaner's to rewrite — fix it and re-run: {attestation.stakes_advocacy}"
            )
        if attestation.ok:
            return (
                Packet(
                    decision=parsed["decision"], stakes=stakes, context=parsed["context"],
                    hints=cleaned_hints, statements=parsed["statements"],
                    cleaning="attested" if attempt == 0 else "attested-after-retry",
                    attestation=attestation.raw,
                ),
                "attested" if attempt == 0 else "attested-after-retry",
            )
        last_error = (
            f"fidelity changed: {attestation.changed}; neutrality: "
            f"{'PASS' if attestation.neutrality_pass else 'FAIL ' + attestation.neutrality_note}"
        )
        complaint = f"An independent auditor rejected your previous attempt: {last_error}\nFix exactly that."

    raise ArbitrationError(f"cleaning failed attestation twice: {last_error}")


def _clean_body(
    decision: str,
    stakes: str,
    context: str,
    hints: list[dict],
    originals: Mapping[str, str],
    complaint: str,
) -> str:
    parts = []
    if complaint:
        parts.append("=== CORRECTION REQUIRED ===\n" + complaint)
    parts.append("=== DECISION (neutralize) ===\n" + decision)
    parts.append(
        "=== OPTIONS (neutralize; emit each under EXACTLY this id) ===\n"
        + "\n".join(f"{k}: {v}" for k, v in originals.items())
    )
    parts.append("=== CONTEXT (neutralize) ===\n" + (context or "None."))
    parts.append(
        "=== HINTS (neutralize the reasons, keep the paths EXACTLY) ===\n"
        + _render_hints(hints)
    )
    parts.append(
        "=== STAKES (REPRODUCE VERBATIM — do not alter one character) ===\n" + stakes
    )
    return "\n\n".join(parts)


def _merge_hints(originals: Sequence[dict], cleaned: Mapping[str, str]) -> list[dict]:
    """Keep the caller's paths (already validated against the snapshot) and take the
    cleaner's neutralized reasons for them. The cleaner may not add or drop a path;
    a reason it fails to return falls back to empty rather than to the original,
    because an un-neutralized reason is the steering channel we are removing."""
    return [{"path": h["path"], "reason": cleaned.get(h["path"], "")} for h in originals]


def _render_hints(hints: Sequence[Mapping[str, str]]) -> str:
    return "\n".join(f"- {h['path']}: {h.get('reason', '')}" for h in hints) or "None."


def _attest_body(
    decision: str,
    stakes: str,
    context: str,
    original_hints: Sequence[dict],
    cleaned_hints: Sequence[dict],
    originals: Mapping[str, str],
    parsed: Mapping[str, Any],
) -> str:
    pairs = [f"[decision]\nORIGINAL: {decision}\nCLEANED:  {parsed['decision']}"]
    # Only fields the caller supplied. Listing an empty `context` invited the attester
    # to score empty→anything as a fidelity change, and the run then failed naming a
    # field the caller had no control over (issue #8, fix 4).
    if context:
        pairs.append(f"[context]\nORIGINAL: {context}\nCLEANED:  {parsed['context']}")
    if original_hints:
        # The real originals, not a placeholder: an auditor shown "(as given)"
        # cannot compare anything, so hint reasons went unchecked.
        pairs.append(
            f"[hints]\nORIGINAL: {_render_hints(original_hints)}\n"
            f"CLEANED:  {_render_hints(cleaned_hints)}"
        )
    for oid, original in originals.items():
        pairs.append(f"[{oid}]\nORIGINAL: {original}\nCLEANED:  {parsed['statements'][oid]}")
    return (
        "=== FIELD BY FIELD ===\n" + "\n\n".join(pairs)
        + "\n\n=== STAKES (NOT cleaned — judge only whether it advocates) ===\n" + stakes
    )


def _fan_out(
    *,
    agent: Callable[..., str],
    repo: Path,
    snapshot: str,
    deciders: Sequence[eng.Engine],
    presentations: Sequence[Presentation],
    packet: Packet,
    carried: Mapping[str, Sequence[tuple[Region, str]]],
    models: Mapping[str, str],
    effort: str,
    web_search: bool,
) -> list[Cast]:
    """Both deciders in parallel, each in its OWN worktree of the same snapshot:
    shared revision, independent search."""
    by_name = {p.engine: p for p in presentations}

    def one(engine: eng.Engine) -> Cast:
        presentation = by_name[engine.name]
        body = render_decider_body(packet, presentation, tuple(carried.get(engine.name, ())))
        with worktree_at(repo, snapshot) as wt:
            text = agent(
                engine_name=engine.name,
                model=models.get(engine.name) or engine.default_model,
                instructions=prompts.ARBITRATE_INSTRUCTIONS,
                body=body, cwd=wt, effort=effort, web_search=web_search,
                timeout=DECIDE_TIMEOUT_SEC, text_only=False,
            )
        return Cast(vote=arb.parse_verdict(text, presentation), body=body, raw=text)

    with ThreadPoolExecutor(max_workers=max(1, len(deciders))) as pool:
        futures = {engine.name: pool.submit(one, engine) for engine in deciders}
    casts: list[Cast] = []
    errors: list[str] = []
    for name, future in futures.items():
        try:
            casts.append(future.result())
        except Exception as exc:  # noqa: BLE001 — name the engine that failed
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    if errors:
        raise ArbitrationError("decider failure — " + "; ".join(errors))
    return casts


def _run_agent(
    *,
    engine_name: str,
    model: str,
    instructions: str,
    body: str,
    cwd: Path | None,
    effort: str,
    web_search: bool,
    timeout: int,
    text_only: bool,
) -> str:
    import tempfile

    engine = eng.get_engine(engine_name, text_only=text_only)
    # text_only roles get a fresh EMPTY directory: for Claude the empty allowlist is
    # the boundary; for Codex, whose read-only sandbox paranoia cannot narrow, an
    # empty cwd plus instruction is a bound, not a boundary.
    scratch = tempfile.mkdtemp(prefix="paranoia-txt-") if cwd is None else None
    where = Path(cwd) if cwd is not None else Path(scratch)
    try:
        review = engine.run(
            prompts.compose(instructions, body), where, model, effort, web_search, timeout=timeout
        )
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    # Reject ANY errored run, even one that left parseable text. `_execute`
    # deliberately preserves in-band error text (see tests/test_instrumentation.py),
    # so accepting non-empty output here would let a failed process cast a vote.
    if review.error:
        raise ArbitrationError(
            f"{engine_name} failed (exit {review.returncode}): "
            f"{(review.text or '').strip()[:500]}"
        )
    return review.text


def _render_report(
    *,
    outcome: arb.Outcome,
    packet: Packet,
    originals: Mapping[str, str],
    presentations: Sequence[Presentation],
    per_round: Sequence[Mapping[str, Vote]],
    advisory: str,
    snapshot: str,
    seed: str,
    refs_moved: bool,
    audit: str,
    rounds: int,
    record: str,
    carried_note: str,
) -> str:
    out: list[str] = [f"# Arbitration: {outcome.outcome}", "", outcome.reason, ""]

    out.append("## Options (caller ids)")
    for oid, original in originals.items():
        cleaned = packet.statements.get(oid, "")
        out.append(f"- **{oid}**")
        out.append(f"  - as given:  {original}")
        if cleaned != original:
            out.append(f"  - as shown:  {cleaned}")
    out.append("")

    out.append(f"## Framing · cleaning: {packet.cleaning}")
    out.append("```")
    out.append(packet.attestation)
    out.append("```")
    out.append("")

    for i, votes in enumerate(per_round, 1):
        out.append(f"## Round {i}")
        for name in sorted(votes):
            vote = votes[name]
            mapping = next(p for p in presentations if p.engine == name).label_to_id
            out.append(f"### {name} → `{vote.selected}`")
            out.append(f"- risk: `{vote.severity}`" + (f" — {vote.risk_text}" if vote.risk_text else ""))
            out.append(f"- authority: `{vote.authority}` (advisory)")
            out.append(f"- constraint: {vote.constraint}")
            out.append(
                "- decisive citation: "
                + (f"`{vote.decisive.render()}`" if vote.decisive else "_none_")
            )
            if vote.citations:
                out.append("- supporting: " + ", ".join(f"`{c.render()}`" for c in vote.citations))
            if vote.new_option:
                out.append(f"- **proposed option**: {vote.new_option}")
            out.append("- label map: " + ", ".join(f"`{k}`→{v}" for k, v in sorted(mapping.items())))
            out.append("")

    out.append("## Reconciliation")
    out.append(carried_note)
    out.append("")
    out.append("## Record (paste verbatim)")
    out.append("```")
    out.append(record)
    out.append("```")
    out.append("")
    out.append(
        render_trailer(
            outcome, advisory=advisory, cleaning=packet.cleaning, snapshot=snapshot,
            seed=seed, refs_moved=refs_moved, audit=audit, rounds=rounds,
        )
    )
    return "\n".join(out)
