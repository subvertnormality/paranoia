"""Tool dispatch logic, separated from MCP wiring so it is unit-testable with
an injected fake engine and clock.

Each handler: resolve inputs (call arg > `.paranoia.toml` > default), build the
task body, compose it with the adversarial instructions, run the reviewer in
the right working directory (an isolated worktree for committed reviews, the
live repo for dirty ones), write an audit record, and return the review with a
footer exposing the session reference for `rebut`.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import class_closure as cc
from . import logs, orientation, prompts
from .config import load_repo_config, resolve
from .engines import Engine, Review
from .worktree import worktree_at



Clock = Callable[[], str]


def _default_clock() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _require_repo(arguments: dict[str, Any]) -> Path:
    rp = arguments.get("repo_path")
    if not rp:
        raise ValueError("repo_path is required")
    repo = Path(rp).resolve()
    if not repo.exists():
        raise ValueError(f"repo_path does not exist: {repo}")
    if not (repo / ".git").exists():
        raise ValueError(f"not a git repo (no .git): {repo}")
    return repo


def _no_repo_cwd() -> Path:
    return Path(tempfile.gettempdir())


def _footer(review: Review, engine: Engine) -> str:
    if review.session_ref:
        note = (
            f"\n\n---\n_paranoia-local · engine={engine.name} · "
            f"session_ref=`{review.session_ref}` — to dispute a finding, call `rebut` "
            f"with this session_ref and your counter-evidence._"
        )
    else:
        note = f"\n\n---\n_paranoia-local · engine={engine.name}_"
    # Surface a failed run explicitly — a non-zero exit or an in-band engine error means
    # the text below may be an error message or a truncated/aborted review, not a verdict.
    prefix = ""
    if review.error:
        prefix = (
            f"⚠️ REVIEW FAILED (engine={engine.name}, exit={review.returncode}) — treat the "
            f"output below as an error, not a completed review.\n\n"
        )
    return prefix + (review.text or "[empty review]") + note


def _progress_kwargs(on_progress: Callable[[str], None] | None) -> dict[str, Any]:
    """Pass on_progress only when set — injected engines may predate the kwarg."""
    return {"on_progress": on_progress} if on_progress is not None else {}


def _calibration(stakes: str | None, review_round: int | None) -> str | None:
    """Render the reviewer-calibration block. STAKES bounds legitimate concern
    (findings beyond it are out of scope); ROUND sets the severity floor across a
    convergence loop (round >=3 reports MAJOR-or-higher only, withholding MINOR
    and OUT-OF-SCOPE). Both optional; absent → the reviewer assumes a modest
    internal tool and reports everything."""
    lines: list[str] = []
    if stakes:
        lines.append(f"STAKES: {stakes}")
    if review_round is not None and review_round >= 1:
        lines.append(f"ROUND: {review_round}")
    if not lines:
        return None
    return "=== REVIEW CALIBRATION ===\n" + "\n".join(lines)


def _prepend(block: str | None, body: str) -> str:
    return f"{block}\n\n{body}" if block else body


def _log(
    log_dir: Path,
    tool: str,
    engine: Engine,
    review: Review,
    now: Clock,
    extra: dict[str, Any],
) -> None:
    logs.write_log(
        log_dir,
        tool=tool,
        record={
            "engine": engine.name,
            "session_ref": review.session_ref,
            "returncode": review.returncode,
            "error": review.error,
            "text": review.text,
            **extra,
        },
        timestamp=now(),
    )


def critique_branch(
    arguments: dict[str, Any],
    *,
    engine: Engine,
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    repo = _require_repo(arguments)
    cfg = load_repo_config(repo)

    base_ref = resolve("base_ref", arguments.get("base_ref"), cfg, "main")
    head_ref = arguments.get("head_ref", "HEAD")
    include_unc = bool(arguments.get("include_uncommitted", False))
    isolate = bool(resolve("isolate", arguments.get("isolate"), cfg, True))
    project_summary = resolve("project_summary", arguments.get("project_summary"), cfg, None)
    diff_intent = arguments.get("diff_intent")
    focus = arguments.get("focus")
    already = list(arguments.get("already_raised", []))
    model = resolve("model", arguments.get("model"), cfg, engine.default_model)
    effort = resolve("effort", arguments.get("effort"), cfg, "high")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))
    # Converge (packet) mode is ON by default: pre-gather a deterministic evidence packet
    # and review it against an immutable materialized snapshot. Pass converge=false (call
    # arg or .paranoia.toml) to fall back to the legacy in-place review.
    converge = bool(resolve("converge", arguments.get("converge"), cfg, True))
    max_packet_chars = int(
        resolve("max_packet_chars", arguments.get("max_packet_chars"), cfg, orientation.MAX_PACKET_CHARS)
    )
    # Calibration: STAKES (project-level, so also honoured from .paranoia.toml) bounds
    # scope; ROUND (per-call, raised each convergence round) sets the severity floor.
    calibration = _calibration(
        resolve("stakes", arguments.get("stakes"), cfg, None), arguments.get("round")
    )
    closure_on = bool(resolve("class_closure", arguments.get("class_closure"), cfg, True))
    if (converge and closure_on and include_unc
            and arguments.get("head_ref") not in (None, "HEAD")
            and not arguments.get("lineage")):
        # resolve_target discards head_ref for a dirty review and snapshots the checkout, so
        # accepting it would key this round's classes to a branch that was never reviewed.
        # An explicit `lineage` says the caller has chosen the key deliberately, so it is
        # honoured rather than rejected — an error whose remedy it also refuses is no remedy.
        raise ValueError(
            "include_uncommitted reviews the current checkout, so head_ref="
            f"{arguments['head_ref']!r} would not be the reviewed ref. Drop head_ref, or pass "
            "an explicit `lineage` to choose the key yourself, or `class_closure: false`."
        )

    target = orientation.resolve_target(repo, base_ref, head_ref, include_unc)

    if converge:
        return _converge_branch_review(
            repo, engine, target=target, base_ref=base_ref, head_ref=head_ref,
            project_summary=project_summary, diff_intent=diff_intent, focus=focus,
            already=already, model=model, effort=effort, web_search=web_search,
            max_packet_chars=max_packet_chars, calibration=calibration,
            log_dir=log_dir, now=now, on_progress=on_progress,
            closure_on=closure_on, closure_args=arguments,
            review_round=arguments.get("round"), include_unc=include_unc,
        )

    packet = orientation.build_orientation(
        repo, target, project_summary, diff_intent, focus, already
    )
    prompt = prompts.compose(prompts.CODE_REVIEW_INSTRUCTIONS, _prepend(calibration, packet))

    if target.is_dirty or not isolate:
        review = engine.run(prompt, repo, model, effort, web_search,
                            **_progress_kwargs(on_progress))
    else:
        with worktree_at(repo, head_ref) as wt:
            review = engine.run(prompt, wt, model, effort, web_search,
                                **_progress_kwargs(on_progress))

    _log(log_dir, "critique_branch", engine, review, now,
         {"target": target.description, "model": model})
    return _footer(review, engine)


def _converge_branch_review(
    repo: Path,
    engine: Engine,
    *,
    target: orientation.Target,
    base_ref: str,
    head_ref: str | None,
    project_summary: str | None,
    diff_intent: str | None,
    focus: str | None,
    already: list[str],
    model: str,
    effort: str,
    web_search: bool,
    max_packet_chars: int,
    calibration: str | None,
    log_dir: Path,
    now: Clock,
    on_progress: Callable[[str], None] | None,
    closure_on: bool = False,
    closure_args: dict[str, Any] | None = None,
    review_round: int | None = None,
    include_unc: bool = False,
    state_root: Path | None = None,
) -> str:
    """Opt-in convergence path: pre-gather a deterministic packet so the reviewer skips
    the re-read/re-grep turns, and review it against an IMMUTABLE materialized worktree
    (which always applies here, overriding isolate=false — mixed-revision evidence off a
    live mutable tree is exactly what this prevents)."""
    if target.is_dirty:
        if orientation.has_head(repo):
            base_id = orientation.resolve_head(repo)
            parent: str | None = base_id
        else:
            # Unborn repo (files, no commit yet): base off git's empty tree, parentless wrapper.
            base_id = orientation.empty_tree(repo)
            parent = None
        head_id = orientation.wrap_commit(repo, orientation.snapshot_tree(repo, base_id), parent)
    else:
        base_id = orientation.resolve_ref(repo, base_ref)
        head_id = orientation.resolve_ref(repo, head_ref or "HEAD")

    closure = _ClassClosure(
        repo, head_id, args=closure_args or {}, round_no=review_round or 1,
        is_dirty=target.is_dirty, base_ref=base_ref, head_ref=head_ref,
        state_root=state_root or cc.default_state_root(), stamp=now(),
    ) if closure_on else None
    blocks = closure.prepare() if closure else []

    # EVERYTHING after prepare() is inside the latch's cleanup: packet building, worktree
    # entry and the engine call can all raise, and a latch stranded there would make every
    # later round STATE-UNAVAILABLE over a fault that already surfaced to the caller. A
    # failed *write* is the one case that deliberately keeps the latch (see `release`).
    try:
        packet = orientation.build_packet(
            repo, base_id, head_id,
            project_summary=project_summary, diff_intent=diff_intent, focus=focus,
            already_raised=already, class_blocks=blocks, max_chars=max_packet_chars,
        )
        instructions = prompts.CODE_REVIEW_INSTRUCTIONS_PACKET
        if closure:
            instructions += "\n\n" + prompts.CLASS_REGISTER_INSTRUCTIONS
        prompt = prompts.compose(instructions, _prepend(calibration, packet))

        with worktree_at(repo, head_id) as wt:
            review = engine.run(prompt, wt, model, effort, web_search,
                                **_progress_kwargs(on_progress))
            # Settle inside the worktree: a register retry resumes the same session and
            # must see the same materialized snapshot the review did.
            trailer = closure.settle(review, engine, wt, model, effort, web_search,
                                     on_progress) if closure else None
    except BaseException:
        if closure:
            closure.abandon()
        raise
    finally:
        if closure:
            closure.release()

    _log(log_dir, "critique_branch", engine, review, now,
         {"target": target.description, "model": model, "mode": "converge-packet",
          "usage": review.usage, "duration_ms": review.duration_ms,
          # Recorded so a future incident IS replayable: the plan's own acceptance
          # replay was impossible because these were never written down.
          "base_id": base_id, "head_id": head_id,
          "lineage": closure.lineage_id if closure else None,
          # The retry's register is what actually changed durable state, so it belongs in
          # the audit record; the original review only carries the malformed attempt.
          "retry_register": closure.retry_register if closure else None})
    body = _footer(review, engine)
    if closure and closure.retry_register:
        # Same reason, for the operator: a CLOSED or a corrected predicate that the retry
        # supplied would otherwise be invisible in everything they can see.
        body += ("\n\n---\n_The register below was supplied on retry and is what this "
                 f"round applied:_\n\n{closure.retry_register.strip()}")
    return f"{body}\n\n{trailer}" if trailer else body


def _plan_body(
    plan_text: str,
    context: str | None,
    focus: str | None,
    already: list[str],
    repo_grounded: bool,
) -> str:
    parts: list[str] = []
    if repo_grounded:
        parts.append(
            "=== REPOSITORY IS AVAILABLE ===\n"
            "You are inside the repository this plan concerns. Read the code to test "
            "every premise the plan makes about current behaviour."
        )
    if context:
        parts.append(f"=== CONTEXT ===\n{context}")
    if focus:
        parts.append(f"=== REVIEWER FOCUS ===\n{focus}")
    parts.append(f"=== PLAN ===\n{plan_text}")
    if already:
        rendered = "\n".join(f"- {c}" for c in already)
        parts.append(
            "=== Already-raised — do NOT restate; hunt for what they missed ===\n" + rendered
        )
    return "\n\n".join(parts)


def critique_plan(
    arguments: dict[str, Any],
    *,
    engine: Engine,
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    plan_text = arguments.get("plan_text")
    plan_path = arguments.get("plan_path")
    if plan_text and plan_path:
        raise ValueError("critique_plan takes plan_text OR plan_path, not both")
    if not plan_text and not plan_path:
        raise ValueError("critique_plan requires plan_text or plan_path")
    if plan_path:
        try:
            plan_text = Path(plan_path).read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, IsADirectoryError, PermissionError, OSError) as exc:
            raise ValueError(f"cannot read plan_path: {exc}") from exc

    context = arguments.get("context")
    focus = arguments.get("focus")
    already = list(arguments.get("already_raised", []))
    repo_path = arguments.get("repo_path")
    repo = _require_repo(arguments) if repo_path else None
    cwd = repo if repo else _no_repo_cwd()
    cfg = load_repo_config(repo) if repo else {}

    model = resolve("model", arguments.get("model"), cfg, engine.default_model)
    effort = resolve("effort", arguments.get("effort"), cfg, "high")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))

    calibration = _calibration(
        resolve("stakes", arguments.get("stakes"), cfg, None), arguments.get("round")
    )
    body = _plan_body(plan_text, context, focus, already, repo_grounded=bool(repo))
    prompt = prompts.compose(prompts.PLAN_REVIEW_INSTRUCTIONS, _prepend(calibration, body))
    review = engine.run(prompt, cwd, model, effort, web_search,
                        **_progress_kwargs(on_progress))

    _log(log_dir, "critique_plan", engine, review, now, {"grounded": bool(repo), "model": model})
    return _footer(review, engine)


def _query_body(
    question: str, files: list[dict], focus: str | None, repo_grounded: bool
) -> str:
    parts: list[str] = []
    if repo_grounded:
        parts.append(
            "=== REPOSITORY IS AVAILABLE ===\n"
            "Answer by reading the actual code, data, and git history in your working "
            "directory — not from assumption."
        )
    if files:
        hints = "\n".join(
            f"- {f.get('path', '?')}" + (f" ({f['reason']})" if f.get("reason") else "")
            for f in files
        )
        parts.append(f"=== FILES THE CALLER SUGGESTS LOOKING AT ===\n{hints}")
    if focus:
        parts.append(f"=== FOCUS ===\n{focus}")
    parts.append(f"=== QUESTION ===\n{question}")
    return "\n\n".join(parts)


def query(
    arguments: dict[str, Any],
    *,
    engine: Engine,
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    question = arguments.get("question")
    if not question:
        raise ValueError("query requires a question")

    repo_path = arguments.get("repo_path")
    repo = _require_repo(arguments) if repo_path else None
    cwd = repo if repo else _no_repo_cwd()
    cfg = load_repo_config(repo) if repo else {}
    files = list(arguments.get("files", []))
    focus = arguments.get("focus")

    model = resolve("model", arguments.get("model"), cfg, engine.default_model)
    # query is a quick double-check, not a full review — lower reasoning effort.
    effort = resolve("effort", arguments.get("effort"), cfg, "medium")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))

    body = _query_body(question, files, focus, repo_grounded=bool(repo))
    prompt = prompts.compose(prompts.QUERY_INSTRUCTIONS, body)
    review = engine.run(prompt, cwd, model, effort, web_search,
                        **_progress_kwargs(on_progress))

    _log(log_dir, "query", engine, review, now, {"model": model})
    return _footer(review, engine)


def rebut(
    arguments: dict[str, Any],
    *,
    engine: Engine,
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    session_ref = arguments.get("session_ref")
    rebuttal = arguments.get("rebuttal")
    if not session_ref:
        raise ValueError("rebut requires session_ref (from a prior review's footer)")
    if not rebuttal:
        raise ValueError("rebut requires rebuttal (your counter-evidence)")
    repo = _require_repo(arguments)
    cfg = load_repo_config(repo)

    model = resolve("model", arguments.get("model"), cfg, engine.default_model)
    effort = resolve("effort", arguments.get("effort"), cfg, "high")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))

    body = f"=== AUTHOR'S COUNTER-EVIDENCE ===\n{rebuttal}"
    prompt = prompts.compose(prompts.REBUT_INSTRUCTIONS, body)
    review = engine.resume(session_ref, prompt, repo, model, effort, web_search,
                           **_progress_kwargs(on_progress))

    _log(log_dir, "rebut", engine, review, now, {"session_ref": session_ref, "model": model})
    return _footer(review, engine)


class _ClassClosure:
    """Orchestration for one round of class closure: the impure half of `class_closure`.

    Split from the pure core so the protocol stays testable without a repository, and
    kept in one object so the round's two halves — the blocks handed to the reviewer,
    and the verdict computed from its register — cannot drift apart.

    Every failure path here BLOCKS and returns the review text. A paid review is never
    discarded over a formatting miss, and a storage fault is never allowed to read as
    an all-clear.
    """

    def __init__(self, repo: Path, head_id: str, *, args: dict[str, Any], round_no: int,
                 is_dirty: bool, base_ref: str, head_ref: str | None,
                 state_root: Path, stamp: str) -> None:
        self.repo, self.head_id, self.round_no = repo, head_id, round_no
        self.args, self.state_root, self.stamp = args, Path(state_root), stamp
        self.lineage_id = _lineage_id(repo, base_ref, head_ref, is_dirty, args.get("lineage"))
        self.lineage: cc.Lineage | None = None
        self.unavailable: str | None = None
        self.budget = cc.Budget()
        #: The retry text, held back until the round has actually applied AND persisted it.
        #: A failed, malformed or transition-invalid retry must never be reported as what
        #: the round applied while durable state says otherwise.
        self._retry_candidate: str | None = None
        self.retry_register: str | None = None
        self._latched = False
        self._settled = False

    def prepare(self) -> list[str]:
        """Load state, sweep what the lineage already holds, and render the reviewer blocks."""
        try:
            self.lineage = cc.load_lineage(self.state_root, self.lineage_id, stamp=self.stamp)
        except cc.StateUnavailable as exc:
            self.unavailable = str(exc)
            return []
        cc.open_latch(self.state_root, self.lineage_id)
        self._latched = True
        self._apply_exemption_args()
        cc.sweep(self.lineage, self._grep(), budget=self.budget, clock=time.monotonic)
        return [b for b in (cc.render_unclosed(self.lineage),
                            cc.render_unmechanized(self.lineage),
                            cc.render_exempt(self.lineage)) if b]

    def settle(self, review: Review, engine: Engine, repo: Path, model: str, effort: str,
               web_search: bool, on_progress: Callable[[str], None] | None) -> str:
        if self.unavailable or self.lineage is None:
            return (f"CLASS-CLOSURE: STATE-UNAVAILABLE — {self.unavailable}\n"
                    "CONVERGENCE: BLOCKED — lineage state could not be used this round.")
        lineage = self.lineage
        if review.error:
            # A CLI failure or timeout is not a review. Recording debt or applying whatever
            # text came back would let a broken run mutate durable state — and the plan
            # requires a failed engine call to leave the lineage byte-identical.
            self._settled = True
            return (f"CLASS-CLOSURE: not evaluated — the review failed "
                    f"(exit {review.returncode}); lineage state is unchanged.\n"
                    "CONVERGENCE: BLOCKED — no verdict can be computed from a failed review.")
        status, minted = "parsed 0", []
        try:
            register, status = self._register(review, engine, repo, model, effort,
                                              web_search, on_progress)
            minted = cc.apply_register(lineage, register, round_no=self.round_no)
            # Round 10: a class registered by THIS review does not exist until now, so it
            # must be evaluated before the verdict — otherwise a new MAJOR class and
            # NOT-BLOCKED could ship in the same response.
            cc.sweep(lineage, self._grep(), only=minted, budget=self.budget,
                     clock=time.monotonic)
            lineage.debt = None
        except cc.RegisterError as exc:
            lineage.debt = {"round": self.round_no, "reason": str(exc)}
            status = f"malformed: {exc}"

        lineage.rounds += 1
        try:
            cc.save_lineage(self.state_root, lineage)
        except cc.StateUnavailable as exc:
            # The latch deliberately STAYS: a write that may have half-happened must block
            # the next round rather than let it start from an empty lineage.
            return (f"CLASS-CLOSURE: STATE-UNAVAILABLE — {exc}\n"
                    "CONVERGENCE: BLOCKED — this round's classes were not persisted.")
        self._settled = True
        if lineage.debt is None:
            self.retry_register = self._retry_candidate
        return cc.render_trailer(lineage, register_status=status, minted=minted)

    def abandon(self) -> None:
        """The round died before it could settle. Nothing was written, so the latch has
        nothing to protect and must not outlive the exception that is already propagating."""
        self._settled = True

    def release(self) -> None:
        """Clear the pending latch once the round is over WITHOUT an unresolved write.

        Called from a `finally` covering everything after `prepare()`, so no failure between
        the two can strand the latch and block every later round on a fault the caller has
        already been told about. A failed *write* does not release: that is the one
        genuinely ambiguous case, and the one the latch exists for.
        """
        if self._latched and self._settled:
            cc.clear_latch(self.state_root, self.lineage_id)
            self._latched = False

    # ── internals ──

    def _grep(self) -> cc.GitGrep:
        return cc.make_grep(self.repo, self.head_id, runner=_run_git)

    def _register(self, review: Review, engine: Engine, repo: Path, model: str, effort: str,
                  web_search: bool, on_progress: Callable[[str], None] | None):
        try:
            register = cc.parse_register(review.text)
            return register, _count(register)
        except cc.RegisterError as first:
            if not review.session_ref or not hasattr(engine, "resume"):
                # Claude's supported non-JSON fallback has no session to resume, and an
                # injected engine may predate `resume` (the reason `_progress_kwargs`
                # exists). Retrying either would raise and replace the paid review with
                # an error — the one outcome this path must never produce.
                raise first
            retry = engine.resume(
                review.session_ref, prompts.REGISTER_RETRY, repo, model, effort, web_search,
                **_progress_kwargs(on_progress))
            self._retry_candidate = retry.text
            if retry.error:
                # A failed CLI still returns text, and that text can contain a parseable
                # NONE or CLOSED block. Trusting it would let a broken retry mutate durable
                # state — the same reason `settle` refuses a failed review outright.
                raise cc.RegisterError(
                    f"the register retry itself failed (exit {retry.returncode})"
                ) from first
            register = cc.parse_register(retry.text)   # a second failure raises, and blocks
            return register, f"parsed after retry: {_count(register)}"

    def _apply_exemption_args(self) -> None:
        assert self.lineage is not None
        for e in self.args.get("exempt", []) or []:
            self.lineage.exemptions.append(cc.Exemption(
                class_id=e["class_id"], path=e["path"], line=int(e["line"]),
                fingerprint=cc.fingerprint(e.get("line_text", "")),
            ))
        drop = {(e["class_id"], e["path"], int(e["line"]))
                for e in (self.args.get("unexempt", []) or [])}
        if drop:
            self.lineage.exemptions = [
                e for e in self.lineage.exemptions
                if (e.class_id, e.path, e.line) not in drop
            ]


def _lineage_id(repo: Path, base_ref: str, head_ref: str | None, is_dirty: bool,
                explicit: str | None) -> str:
    if explicit:
        return explicit
    if is_dirty or not head_ref or head_ref == "HEAD":
        # `symbolic-ref` reads the ref HEAD POINTS AT rather than resolving it to an
        # object, so it works before the first commit — `rev-parse` exits 128 there and
        # would break the supported unborn-repository first review.
        name = _git_line(["git", "symbolic-ref", "-q", "HEAD"], repo)
    else:
        name = _git_line(["git", "rev-parse", "--symbolic-full-name", head_ref], repo)
    if not name:
        raise ValueError(
            "class closure cannot derive a lineage: the reviewed ref is not a branch "
            "(a detached HEAD or a raw commit). Pass `lineage` explicitly, or "
            "`class_closure: false`."
        )
    key = "\0".join([str(repo.resolve()), base_ref, name])
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _git_line(argv: list[str], repo: Path) -> str:
    proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _run_git(argv: list[str], cwd: Path, timeout: int) -> tuple[int, bytes, bytes]:
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(str(exc)) from exc
    return proc.returncode, proc.stdout, proc.stderr


def _count(register: cc.Register) -> str:
    """`NONE` and `parsed 0` are different facts about a review, and an operator reading
    the trailer needs to tell an empty register from one whose records were all accepted."""
    total = len(register.new_classes) + len(register.transitions)
    return cc.NONE if total == 0 else f"parsed {total}"
