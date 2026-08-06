"""Class closure for `critique_plan`: unmechanized classes beside pinned evidence.

Two claims that are easy to conflate and are NOT the same: the class-closure
COORDINATOR still never constructs a grep (`TestPlanModeNeverGreps`), while the integrated
`critique_plan` HANDLER snapshots Git and resolves bounded server evidence. This module's
helper therefore always supplies a repository.

Design contract: `docs/plan_class_closure_proposal.md`. Each block names the plan-review
round whose finding it pins, so a later change that re-opens one fails with the history
attached. The two that matter most are round 3's, because both were false clearances
introduced by an earlier round's fix:

- a class CLOSED at round 3 and violated again at round 5 must still be shown, exempt
  from the round floor and from `already_raised`, or nothing ever emits `REOPEN` and the
  trailer clears a live defect (`TestClosedBlockingClassCanStillRecur`);
- a plan seam and a branch seam that share a lineage key must be refused rather than
  merged (`TestCrossModeLineages`).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from paranoia_local import class_closure as cc
from paranoia_local import handlers, prompts


def test_lineage_latch_has_exactly_one_concurrent_owner(tmp_path: Path) -> None:
    root = tmp_path / "state"

    def acquire(_index: int) -> bool:
        try:
            cc.open_latch(root, "same-lineage")
            return True
        except cc.StateUnavailable:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(acquire, range(8)))
    assert outcomes.count(True) == 1


class FakeEngine:
    """Returns a scripted review per call; records prompts and resume() invocations."""

    name = "fake"
    default_model = "fake-model"

    def __init__(self, *reviews: str, session_ref: str | None = "sess") -> None:
        self.reviews = list(reviews)
        self.session_ref = session_ref
        self.calls: list[str] = []
        self.resumed: list[str] = []

    def _next(self) -> str:
        return self.reviews.pop(0) if self.reviews else "no more scripted reviews"

    def run(self, prompt: str, cwd: Path, model: str, effort: str, web: bool, **kw):
        self.calls.append(prompt)
        return _review(self._next(), self.session_ref)

    def run_toolless(self, prompt: str, model: str, effort: str, **kw):
        if "neutral claim extractor" in prompt:
            return _review("=== RESEARCH REGISTER ===\nEVENTS-JSON: []", self.session_ref)
        if "neutral evidence planner" in prompt:
            return _review("=== EVIDENCE REQUESTS ===\nREQUESTS-JSON: []", self.session_ref)
        if "preparing bounded repository context" in prompt:
            return _review("=== EVIDENCE REQUESTS ===\nREQUESTS-JSON: []", self.session_ref)
        if "neutral evidence verifier" in prompt:
            return _review("=== VERIFICATION REGISTER ===\nEVENTS-JSON: []", self.session_ref)
        self.calls.append(prompt)
        if "CORRECTION REQUIRED" in prompt:
            self.resumed.append(prompt)
        text = self._next()
        if text.startswith("=== CLASS REGISTER ==="):
            text = "=== PLAN REGISTER ===\nEVENTS-JSON: []\n" + text
        return _review(text, self.session_ref)

    def resume(self, ref: str, prompt: str, cwd: Path, model: str, effort: str,
               web: bool, **kw):
        self.resumed.append(prompt)
        return _review(self._next(), self.session_ref)


class _R:
    def __init__(self, text: str, session_ref: str | None) -> None:
        self.text, self.session_ref = text, session_ref
        self.returncode, self.error = 0, False
        self.usage, self.duration_ms = None, None


def _review(text: str, session_ref: str | None) -> _R:
    return _R(text, session_ref)


def review_with(register: str, body: str = "## What doesn't work\n\nSomething.") -> str:
    if "## What works" not in body:
        body = "## What works\n\nNothing notable.\n\n" + body
    if "## Risks" not in body:
        body += "\n\n## Risks\n\nNothing notable."
    if "## Gaps" not in body:
        body += "\n\n## Gaps\n\nNothing notable."
    if "## Improvements" not in body:
        body += "\n\n## Improvements\n\nNothing notable."
    return (
        f"{body}\n\n=== PLAN REGISTER ===\nEVENTS-JSON: []\n"
        f"=== CLASS REGISTER ===\n{register}"
    )


PROCEDURE_CLASS = (
    "CLASS: every mutation campaign sits at the frozen card seam\n"
    "SEVERITY: FATAL\n"
    "PROCEDURE: read every step that starts a campaign; confirm none precedes the freeze"
)


def run_round(engine: FakeEngine, tmp_path: Path, *, lineage: str = "proj-1-plan",
              round_no: int = 1, plan: str = "# Plan\n\nDo the thing.",
              already: list[str] | None = None, closure: bool = True,
              repo: Path | None = None) -> str:
    args = {"plan_text": plan, "round": round_no, "class_closure": closure,
            "repo_path": str(repo or _bare_repo(tmp_path))}
    if lineage:
        args["lineage"] = lineage
    if already:
        args["already_raised"] = already
    return handlers.critique_plan(args, engine=engine, log_dir=tmp_path / "logs",
                                  now=lambda: f"T{round_no:04d}")


# ── the core loop ─────────────────────────────────────────────────────────────


class TestPlanClassLifecycle:
    def test_a_registered_class_blocks_until_a_reviewer_closes_it(self, tmp_path: Path) -> None:
        first = run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        assert "CONVERGENCE: BLOCKED" in first
        assert "every mutation campaign sits at the frozen card seam" in first

        cid = _only_class_id(tmp_path)
        second = run_round(FakeEngine(review_with(f"CLOSED: {cid}")), tmp_path, round_no=2)
        assert "CONVERGENCE: NOT-BLOCKED" in second

    def test_the_next_round_is_shown_the_class_its_procedure_and_its_id(
        self, tmp_path: Path
    ) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        engine = FakeEngine(review_with("NONE"))
        run_round(engine, tmp_path, round_no=2)

        prompt = engine.calls[0]
        cid = _only_class_id(tmp_path)
        assert cc.UNMECHANIZED_HEADER in prompt
        assert cid in prompt
        assert "every mutation campaign sits at the frozen card seam" in prompt
        assert "confirm none precedes the freeze" in prompt

    def test_the_class_block_is_rendered_after_already_raised(self, tmp_path: Path) -> None:
        """It carries explicit precedence over `already_raised`, and a reviewer reading in
        order obeys the closer instruction — so being nearest the end is load-bearing."""
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        engine = FakeEngine(review_with("NONE"))
        run_round(engine, tmp_path, round_no=2, already=["a prior claim, file.py:1"])

        prompt = engine.calls[0]
        assert prompt.index("Already-raised") < prompt.index(cc.UNMECHANIZED_HEADER)

    def test_a_reopened_class_blocks_again(self, tmp_path: Path) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        cid = _only_class_id(tmp_path)
        run_round(FakeEngine(review_with(f"CLOSED: {cid}")), tmp_path, round_no=2)
        third = run_round(FakeEngine(review_with(f"REOPEN: {cid}")), tmp_path, round_no=3)
        assert "CONVERGENCE: BLOCKED" in third
        assert cid in third


class TestClosedBlockingClassCanStillRecur:
    """Round 3 [FATAL]: revision 3 gave the floor exemption and `already_raised`
    precedence to OPEN classes only, so a class closed at round 3 and violated again at
    round 5 could be floor-suppressed, never REOPENed, and cleared by the trailer."""

    def test_a_closed_class_is_still_shown_with_an_explicit_reopen_instruction(
        self, tmp_path: Path
    ) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        cid = _only_class_id(tmp_path)
        run_round(FakeEngine(review_with(f"CLOSED: {cid}")), tmp_path, round_no=2)

        engine = FakeEngine(review_with("NONE"))
        run_round(engine, tmp_path, round_no=5, already=["a prior claim, file.py:1"])
        prompt = engine.calls[0]

        assert cid in prompt and "closed" in prompt
        assert "including the closed ones" in prompt
        assert "REOPEN" in prompt

    def test_the_floor_exemption_and_precedence_cover_closed_entries_too(
        self, tmp_path: Path
    ) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        cid = _only_class_id(tmp_path)
        run_round(FakeEngine(review_with(f"CLOSED: {cid}")), tmp_path, round_no=2)

        engine = FakeEngine(review_with("NONE"))
        run_round(engine, tmp_path, round_no=5)
        block = engine.calls[0].split(cc.UNMECHANIZED_HEADER)[1]

        assert "ROUND severity floor does not apply to any entry here" in block
        assert "THIS block governs" in block
        assert "whatever its individual severity" in block

    def test_the_calibration_separates_the_floor_exemption_from_the_converged_ban(
        self,
    ) -> None:
        """Merging them is what forbade convergence forever in revision 2, and what
        cleared a live defect in revision 3. They must stay two sentences."""
        text = prompts.PLAN_REVIEW_INSTRUCTIONS
        assert "The ROUND severity floor NEVER applies to a class listed in an " \
               "`=== UNCLOSED CLASSES ===` or `=== UNMECHANIZED CLASSES ===` block" in text
        assert "Do NOT write `CONVERGED` while any entry marked `BLOCKING` is still open" in text
        assert "Entries marked `advisory`, and closed entries, do NOT prevent convergence" in text


class TestAdvisoryClassesNeverBlock:
    """Round 2 [FATAL]: the plan register prompt said no class may leave the loop
    unblocked, which contradicts BLOCKING_SEVERITIES and traps a valid plan."""

    def test_an_open_minor_class_permits_prose_converged_and_a_clear_trailer(
        self, tmp_path: Path
    ) -> None:
        """Both halves together: the reviewer declares convergence at round >=3 AND the
        trailer agrees. A mechanism that blocked here could never be escaped."""
        minor = ("CLASS: wording is inconsistent\nSEVERITY: MINOR\n"
                 "PROCEDURE: reread the section headings")
        run_round(FakeEngine(review_with(minor)), tmp_path, round_no=1)
        converged = ("## What doesn't work\n\nCONVERGED — no blocking findings at this "
                     "round.\n\n## Risks\n\nNothing notable.")
        out = run_round(FakeEngine(review_with("NONE", converged)), tmp_path, round_no=3)
        assert "CONVERGED — no blocking findings" in out
        assert "CONVERGENCE: NOT-BLOCKED" in out
        assert "is VOID" not in out

    def test_an_open_minor_class_is_still_shown_and_marked_advisory(
        self, tmp_path: Path
    ) -> None:
        minor = ("CLASS: wording is inconsistent\nSEVERITY: MINOR\n"
                 "PROCEDURE: reread the section headings")
        run_round(FakeEngine(review_with(minor)), tmp_path, round_no=1)
        engine = FakeEngine(review_with("NONE"))
        run_round(engine, tmp_path, round_no=2)
        assert "advisory" in engine.calls[0].split(cc.UNMECHANIZED_HEADER)[1]

    def test_the_prompt_names_only_fatal_and_major_as_blocking(self) -> None:
        text = prompts.PLAN_CLASS_REGISTER_INSTRUCTIONS
        assert "Only **open** classes of severity FATAL or MAJOR hold the loop." in text
        assert "MINOR and OUT-OF-SCOPE\nclasses are tracked and advisory and never block" in text

    def test_a_blocking_class_can_be_reclassified_down_into_not_blocked(
        self, tmp_path: Path
    ) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        cid = _only_class_id(tmp_path)
        out = run_round(FakeEngine(review_with(f"RECLASSIFY: {cid} MINOR")), tmp_path,
                        round_no=2)
        assert "CONVERGENCE: NOT-BLOCKED" in out


# ── the register grammar in plan mode ─────────────────────────────────────────


class TestPlanRegisterRejectsPredicates:
    """A regex over plan prose closes on a rewording, which is a false closure. The
    parser refusal is the BACKSTOP; `PLAN_CLASS_REGISTER_INSTRUCTIONS` is what stops a
    compliant reviewer ever sending one (round 1 [FATAL])."""

    @pytest.mark.parametrize("record", [
        "CLASS: x\nSEVERITY: MAJOR\nPATTERN: foo\nPATHSPEC: .",
        "SUPERSEDE: abc\nWITH-PATTERN: foo\nPATHSPEC: .",
    ])
    def test_a_mechanized_record_is_refused_naming_procedure_as_the_remedy(
        self, record: str
    ) -> None:
        with pytest.raises(cc.RegisterError, match="Use PROCEDURE instead"):
            cc.parse_register(f"=== CLASS REGISTER ===\n{record}", allow_mechanized=False)

    def test_the_same_record_is_accepted_for_a_branch_review(self) -> None:
        register = cc.parse_register(
            "=== CLASS REGISTER ===\nCLASS: x\nSEVERITY: MAJOR\nPATTERN: foo\nPATHSPEC: ."
        )
        assert register.new_classes[0].pattern == "foo"

    def test_the_plan_prompt_offers_no_pattern_field(self) -> None:
        text = prompts.PLAN_CLASS_REGISTER_INSTRUCTIONS
        assert "PATTERN:" not in text.replace("PATTERN and PATHSPEC are NOT accepted", "")
        assert "PROCEDURE: <what a reviewer must do" in text
        assert "SEVERITY: FATAL|MAJOR|MINOR|OUT-OF-SCOPE" in text

    def test_a_mechanized_register_costs_one_retry_not_a_lost_review(
        self, tmp_path: Path
    ) -> None:
        engine = FakeEngine(
            review_with("CLASS: x\nSEVERITY: MAJOR\nPATTERN: foo\nPATHSPEC: ."),
            "=== CLASS REGISTER ===\n" + PROCEDURE_CLASS,
        )
        out = run_round(engine, tmp_path, round_no=1)
        assert len(engine.resumed) == 1
        assert "Use PROCEDURE instead" in engine.resumed[0]
        assert "parsed after retry" in out

    def test_without_a_session_to_resume_it_becomes_debt_not_an_exception(
        self, tmp_path: Path
    ) -> None:
        engine = FakeEngine(
            review_with("CLASS: x\nSEVERITY: MAJOR\nPATTERN: foo\nPATHSPEC: ."),
            session_ref=None,
        )
        out = run_round(engine, tmp_path, round_no=1)
        assert "CONVERGENCE: BLOCKED" in out and "register debt" in out


class TestFatalSeverity:
    """Round 1 [MAJOR]: `SEVERITIES` had no FATAL, but it is the plan reviewer's own top
    tag — so a naive port refused the reviewer's documented vocabulary."""

    def test_fatal_registers_and_blocks(self, tmp_path: Path) -> None:
        out = run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        assert "CONVERGENCE: BLOCKED" in out

    def test_fatal_is_a_blocking_severity(self) -> None:
        assert cc.FATAL in cc.SEVERITIES and cc.FATAL in cc.BLOCKING_SEVERITIES

    def test_a_branch_reviewer_writing_blocker_still_works(self) -> None:
        assert cc.BLOCKER in cc.BLOCKING_SEVERITIES


# ── identity ──────────────────────────────────────────────────────────────────


class TestLineageIsRequiredAndNeverDerived:
    """Round 2 [FATAL]: a `plan_path`-derived key changes when the file moves, so the next
    round loads nothing, reports NOT-BLOCKED, and drops every tracked class."""

    @pytest.mark.parametrize("form", ["plan_text", "plan_path"])
    def test_closure_without_a_lineage_is_refused(self, form: str, tmp_path: Path) -> None:
        """Both input forms, because a path is no more an identity than the text is."""
        if form == "plan_text":
            args = {"plan_text": "# Plan"}
        else:
            plan = tmp_path / "plan.md"
            plan.write_text("# Plan")
            args = {"plan_path": str(plan)}
        with pytest.raises(ValueError, match="needs an explicit `lineage`"):
            handlers.critique_plan(
                {**args, "class_closure": True, "round": 1,
                 "repo_path": str(_bare_repo(tmp_path))},
                engine=FakeEngine(), log_dir=tmp_path / "logs")

    def test_the_refusal_mints_no_lineage(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            handlers.critique_plan(
                {"plan_text": "# Plan", "class_closure": True, "round": 1,
                 "repo_path": str(_bare_repo(tmp_path))},
                engine=FakeEngine(), log_dir=tmp_path / "logs")
        assert not list(cc.lineage_dir(cc.default_state_root()).glob("*.json"))

    def test_the_error_names_both_remedies(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError) as exc:
            handlers.critique_plan(
                {"plan_text": "# Plan", "class_closure": True, "round": 1,
                 "repo_path": str(_bare_repo(tmp_path))},
                engine=FakeEngine(), log_dir=tmp_path / "logs")
        assert "mode-qualified" in str(exc.value) and "class_closure: false" in str(exc.value)

    def test_the_same_lineage_survives_a_completely_rewritten_plan(
        self, tmp_path: Path
    ) -> None:
        """§1.1(a): the whole point. A predicate would have closed here; the class must
        not, because a rewrite that keeps the defect is exactly the failure mode."""
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1,
                  plan="# Plan\n\nSU5 runs a campaign before the seam.")
        cid = _only_class_id(tmp_path)
        converged = ("## What doesn't work\n\nCONVERGED — no blocking findings at this "
                     "round.\n\n## Risks\n\nNothing notable.")
        for round_no, plan, body in (
            (2, "# Plan\n\nPhase 0 runs four native campaigns.", None),
            (3, "# Plan\n\nSection 3 calls them exploratory pilots.", None),
            (4, "# Plan\n\nSection 4 omits the new script from the seam campaigns.",
             converged),
        ):
            review = review_with("NONE", body) if body else review_with("NONE")
            out = run_round(FakeEngine(review), tmp_path, round_no=round_no, plan=plan)
            assert "CONVERGENCE: BLOCKED" in out and cid in out
        # The round that DECLARED convergence is the one that matters: a reviewer's own
        # word must not end the loop while its predecessor's class is open.
        assert "CONVERGED" in out
        assert "Any `CONVERGED` in the review text above is VOID" in out


class TestCrossModeLineages:
    """Round 3 [FATAL]: the rollout prescribed the consumer's existing branch key for
    plan seams, so every normal card would have collided at its frozen seam."""

    def test_a_branch_lineage_cannot_be_opened_as_a_plan(self, tmp_path: Path) -> None:
        root = cc.default_state_root()
        cc.save_lineage(root, cc.Lineage("shared-key", mode=cc.BRANCH_MODE))
        out = run_round(FakeEngine(review_with("NONE")), tmp_path, lineage="shared-key")
        assert "STATE-UNAVAILABLE" in out and "CONVERGENCE: BLOCKED" in out
        assert "shared-key-plan" in out

    def test_a_plan_lineage_cannot_be_opened_as_a_branch(self, tmp_path: Path) -> None:
        root = cc.default_state_root()
        cc.save_lineage(root, cc.Lineage("shared-key", mode=cc.PLAN_MODE))
        with pytest.raises(cc.StateUnavailable, match="created by a plan review"):
            cc.load_lineage(root, "shared-key", stamp="T", mode=cc.BRANCH_MODE)

    def test_the_real_card_lifecycle_plan_then_branch_on_qualified_keys(
        self, git_repo: Path, tmp_path: Path
    ) -> None:
        """Driven through both handlers, not by hand-saving state: this is the shape a
        Parallax card actually runs, and the one revision 3 would have collided."""
        plan_out = run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path,
                             lineage="card-7-plan")
        branch_out = handlers.critique_branch(
            {"repo_path": str(git_repo), "base_ref": "main", "round": 1,
             "lineage": "card-7-branch"},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs",
            now=lambda: "T0001")

        assert "CONVERGENCE: BLOCKED" in plan_out
        assert "STATE-UNAVAILABLE" not in plan_out
        assert "STATE-UNAVAILABLE" not in branch_out
        assert "CONVERGENCE: NOT-BLOCKED" in branch_out
        root = cc.default_state_root()
        assert cc.load_lineage(root, "card-7-plan", stamp="T", mode=cc.PLAN_MODE).classes
        assert cc.load_lineage(root, "card-7-branch", stamp="T").mode == cc.BRANCH_MODE

    def test_the_same_key_for_both_seams_is_refused(
        self, git_repo: Path, tmp_path: Path
    ) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, lineage="card-7")
        branch_out = handlers.critique_branch(
            {"repo_path": str(git_repo), "base_ref": "main", "round": 1,
             "lineage": "card-7"},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs",
            now=lambda: "T0002")
        assert "STATE-UNAVAILABLE" in branch_out and "CONVERGENCE: BLOCKED" in branch_out
        assert "card-7-branch" in branch_out

    def test_pre_existing_state_without_a_mode_reads_as_branch(self, tmp_path: Path) -> None:
        """No migration: every lineage written before plan mode existed is a branch one."""
        d = cc.lineage_dir(cc.default_state_root())
        d.mkdir(parents=True, exist_ok=True)
        (d / "legacy.json").write_text(json.dumps({"rounds": 3, "next_seq": 1, "classes": []}))
        assert cc.load_lineage(cc.default_state_root(), "legacy", stamp="T").mode == "branch"


# ── plan class predicates never grep ─────────────────────────────────────────


class TestPlanModeNeverGreps:
    def test_a_full_plan_round_never_constructs_a_grep(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§2.1 contract. The rewritten-plan fixture cannot prove this — `sweep` skips a
        PROCEDURE class whether or not a grep was built."""
        def explode(*a, **k):
            raise AssertionError("plan mode built a git grep")

        monkeypatch.setattr(cc, "make_grep", explode)
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        run_round(FakeEngine(review_with("NONE")), tmp_path, round_no=2)

    def test_plan_classes_remain_unmechanized_after_git_backed_evidence(
        self, tmp_path: Path
    ) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path)
        lineage = cc.load_lineage(
            cc.default_state_root(), "proj-1-plan", stamp="T", mode=cc.PLAN_MODE
        )
        assert all(not item.mechanized for item in lineage.classes.values())


class TestBranchPathUnchanged:
    """The refactor split `_ClassClosure` into a base plus two subclasses. These pin the
    branch behaviours the split could have silently altered."""

    def test_a_mechanized_advisory_class_is_marked_advisory_not_blocking(
        self, git_repo: Path, tmp_path: Path
    ) -> None:
        """`render_unclosed` has no severity filter, so without the marker the prompt
        would forbid CONVERGED while the trailer said NOT-BLOCKED — a false refusal."""
        minor = ("CLASS: stray debug print\nSEVERITY: MINOR\n"
                 "PATTERN: DEBUGME\nPATHSPEC: .")
        first = handlers.critique_branch(
            {"repo_path": str(git_repo), "base_ref": "main", "round": 1,
             "lineage": "adv-branch"},
            engine=FakeEngine(review_with(minor)), log_dir=tmp_path / "logs",
            now=lambda: "T1")
        assert "CONVERGENCE: NOT-BLOCKED" in first

        engine = FakeEngine(review_with("NONE"))
        handlers.critique_branch(
            {"repo_path": str(git_repo), "base_ref": "main", "round": 3,
             "lineage": "adv-branch"},
            engine=engine, log_dir=tmp_path / "logs", now=lambda: "T2")
        block = engine.calls[0].split(cc.UNCLOSED_HEADER)[1]
        assert "MINOR — advisory" in block
        assert "BLOCKING" not in block.split("\n\n")[0]

    @pytest.mark.parametrize("converge", [True, False])
    def test_branch_audit_records_carry_the_round_and_the_suppression_list(
        self, git_repo: Path, tmp_path: Path, converge: bool
    ) -> None:
        """Both branch paths: the legacy in-place review logs from a different call site.
        The legacy path is reachable only in the one-shot mode, since closure never ran
        there — so `class_closure` tracks `converge` here."""
        handlers.critique_branch(
            {"repo_path": str(git_repo), "base_ref": "main", "round": 6,
             "lineage": "audit-branch", "already_raised": ["a prior claim, x.py:1"],
             "converge": converge, "class_closure": converge},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs",
            now=lambda: "T3")
        files = sorted((tmp_path / "logs").glob("*critique_branch*.json"))
        record = json.loads(files[-1].read_text())
        assert record["round"] == 6
        assert record["already_raised"] == ["a prior claim, x.py:1"]


# ── the off switch, and the audit record ──────────────────────────────────────


class TestDefaultOnAndTheOneShotEscape:
    """Closure is ON by default; `class_closure: false` is the ONE explicit one-shot mode,
    and it is also what drops the `round` requirement — one rule, not two."""

    def test_closure_is_on_without_being_asked_for(self, tmp_path: Path) -> None:
        out = handlers.critique_plan(
            {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)),
             "round": 1, "lineage": "default-on-plan"},
            engine=FakeEngine(review_with(PROCEDURE_CLASS)), log_dir=tmp_path / "logs")
        assert "CONVERGENCE: BLOCKED" in out

    def test_the_default_refuses_a_call_with_no_lineage_and_names_the_one_shot_escape(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="class_closure: false"):
            handlers.critique_plan(
                {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)), "round": 1},
                engine=FakeEngine(), log_dir=tmp_path / "logs")

    def test_the_one_shot_mode_needs_neither_lineage_nor_round(self, tmp_path: Path) -> None:
        engine = FakeEngine(review_with(PROCEDURE_CLASS))
        out = handlers.critique_plan(
            {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)),
             "class_closure": False},
            engine=engine, log_dir=tmp_path / "logs")
        assert "CONVERGENCE:" not in out
        assert cc.UNMECHANIZED_HEADER not in engine.calls[0]

    def test_the_one_shot_mode_writes_no_state_at_all(self, tmp_path: Path) -> None:
        handlers.critique_plan(
            {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)),
             "class_closure": False},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs")
        assert not cc.lineage_dir(cc.default_state_root()).exists() or \
            not list(cc.lineage_dir(cc.default_state_root()).iterdir())

    def test_paranoia_toml_cannot_turn_plan_closure_off(self, tmp_path: Path) -> None:
        """The branch key must not reach across tools in EITHER direction: a project that
        set `class_closure = false` for its branch reviews must not silently disable the
        plan gate."""
        repo = _bare_repo(tmp_path)
        (repo / ".paranoia.toml").write_text("class_closure = false\n")
        out = handlers.critique_plan(
            {"plan_text": "# Plan", "repo_path": str(repo), "round": 1,
             "lineage": "toml-plan"},
            engine=FakeEngine(review_with(PROCEDURE_CLASS)), log_dir=tmp_path / "logs")
        assert "CONVERGENCE: BLOCKED" in out


class TestPlanAuditRecord:
    def test_the_record_carries_what_a_seam_needs_to_be_reconstructed(
        self, tmp_path: Path
    ) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=4,
                  already=["a prior claim, file.py:1"], plan="# Plan\n\nbody")
        record = _log_record(tmp_path)
        assert record["round"] == 4
        assert record["already_raised"] == ["a prior claim, file.py:1"]
        assert record["class_closure"] is True
        assert record["lineage"] == "proj-1-plan"
        assert record["register_status"] == "parsed 1"
        assert record["plan_digest"] == cc.hashlib.sha256(
            b"# Plan\n\nbody").hexdigest()[:16]

    def test_the_digest_is_recorded_for_a_file_backed_plan_too(self, tmp_path: Path) -> None:
        plan = tmp_path / "plan.md"
        plan.write_text("# Plan\n\nfrom a file")
        handlers.critique_plan(
            {"plan_path": str(plan), "class_closure": True, "lineage": "p-plan",
             "round": 1, "repo_path": str(_bare_repo(tmp_path))},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs")
        record = _log_record(tmp_path)
        assert record["plan_path"] == str(plan)
        assert record["plan_digest"] == cc.hashlib.sha256(
            b"# Plan\n\nfrom a file").hexdigest()[:16]

    def test_a_retried_register_records_the_applied_block_not_the_rejected_one(
        self, tmp_path: Path
    ) -> None:
        engine = FakeEngine(
            review_with("CLASS: x\nSEVERITY: MAJOR\nPATTERN: foo\nPATHSPEC: ."),
            "=== CLASS REGISTER ===\n" + PROCEDURE_CLASS,
        )
        run_round(engine, tmp_path, round_no=1)
        record = _log_record(tmp_path)
        assert "PROCEDURE:" in record["retry_register"]
        assert "PATTERN:" not in record["retry_register"]

    def test_a_one_shot_plan_review_still_logs(self, tmp_path: Path) -> None:
        handlers.critique_plan(
            {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)),
             "class_closure": False},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs")
        record = _log_record(tmp_path)
        assert record["class_closure"] is False and record["lineage"] is None


class TestFailedReviewLeavesStateAlone:
    def test_a_failed_engine_call_does_not_mutate_the_lineage(self, tmp_path: Path) -> None:
        run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path, round_no=1)
        path = cc.lineage_dir(cc.default_state_root()) / "proj-1-plan.json"
        before = path.read_bytes()

        engine = FakeEngine(review_with(f"CLOSED: {_only_class_id(tmp_path)}"))
        original_run = engine.run_toolless

        def failing(*a, **k):
            r = original_run(*a, **k)
            r.error, r.returncode = True, 1
            return r

        engine.run_toolless = failing  # type: ignore[method-assign]
        out = run_round(engine, tmp_path, round_no=2)

        assert "CONVERGENCE: BLOCKED" in out
        assert "lineage state is unchanged" in out
        # Bytes, not parsed values: the design says byte-identical, and a dict compare
        # would pass a round that rewrote the file with equal contents.
        assert path.read_bytes() == before


# ── helpers ───────────────────────────────────────────────────────────────────


def _bare_repo(tmp_path: Path) -> Path:
    """`critique_plan` now requires a repo to ground against; these tests do not care
    which, so one empty repo per tmp_path serves every call."""
    import subprocess

    r = tmp_path / "plan-repo"
    if not r.exists():
        r.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=r, check=True, capture_output=True)
    return r


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A real repo with a `feature` branch, for the branch half of the lifecycle."""
    import subprocess

    r = tmp_path / "repo"
    r.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=r, check=True, capture_output=True)
    (r / "seed.py").write_text("seed = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=r, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=r, check=True,
                   capture_output=True)
    # Carries a line a test predicate can actually match, so a registered class stays
    # open rather than being born closed and vanishing from the unclosed block.
    (r / "app.py").write_text("value = 2\nprint('DEBUGME')\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "work"], cwd=r, check=True, capture_output=True)
    return r


def _only_class_id(tmp_path: Path) -> str:
    files = list(cc.lineage_dir(cc.default_state_root()).glob("*.json"))
    assert len(files) == 1, f"expected one lineage, got {files}"
    classes = json.loads(files[0].read_text())["classes"]
    assert len(classes) == 1, f"expected one class, got {classes}"
    return classes[0]["class_id"]


def _log_record(tmp_path: Path) -> dict:
    files = sorted((tmp_path / "logs").glob("*critique_plan*.json"))
    return json.loads(files[-1].read_text())


# ── the mandatory contract ────────────────────────────────────────────────────


class TestRoundIsRequiredWhileAClosureLoopRuns:
    """`round` is the only thing that makes a loop terminate: `_CALIBRATION`'s severity
    floor starts at round 3, so a loop driven without it reports at round-1 severity
    forever. Required whenever closure is tracking a loop, and deliberately not in the
    one-shot mode, which has no next round to floor."""

    def test_a_plan_closure_call_without_round_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="needs `round`"):
            handlers.critique_plan(
                {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)),
                 "lineage": "no-round-plan"},
                engine=FakeEngine(), log_dir=tmp_path / "logs")

    def test_a_branch_call_without_round_is_refused(
        self, git_repo: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="needs `round`"):
            handlers.critique_branch(
                {"repo_path": str(git_repo), "base_ref": "main"},
                engine=FakeEngine(), log_dir=tmp_path / "logs")

    def test_the_refusal_names_the_one_shot_escape(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError) as exc:
            handlers.critique_plan(
                {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)),
                 "lineage": "no-round-plan"},
                engine=FakeEngine(), log_dir=tmp_path / "logs")
        assert "class_closure: false" in str(exc.value)

    @pytest.mark.parametrize("tool", ["plan", "branch"])
    def test_the_one_shot_mode_needs_no_round_on_either_tool(
        self, tool: str, git_repo: Path, tmp_path: Path
    ) -> None:
        if tool == "plan":
            out = handlers.critique_plan(
                {"plan_text": "# Plan", "repo_path": str(git_repo),
                 "class_closure": False},
                engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs")
        else:
            out = handlers.critique_branch(
                {"repo_path": str(git_repo), "base_ref": "main", "class_closure": False},
                engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs")
        assert "CONVERGENCE:" not in out


class TestPlanReviewsMustBeGrounded:
    def test_a_plan_review_without_a_repo_is_refused(self, tmp_path: Path) -> None:
        """225 of 225 logged plan reviews passed one, so this refuses nothing real — and
        an ungrounded review cannot do the job the prompt calls its most valuable."""
        with pytest.raises(ValueError, match="repo_path is required"):
            handlers.critique_plan(
                {"plan_text": "# Plan", "class_closure": False},
                engine=FakeEngine(), log_dir=tmp_path / "logs")

    def test_the_schema_says_so_too(self) -> None:
        from paranoia_local import server

        schema = [t for t in server.TOOLS if t.name == "critique_plan"][0].inputSchema
        assert schema["required"] == ["repo_path"]

    def test_the_schema_encodes_plan_text_xor_plan_path(self) -> None:
        """The handler has always enforced it; a client could not see it before spending."""
        from paranoia_local import server

        schema = [t for t in server.TOOLS if t.name == "critique_plan"][0].inputSchema
        assert schema["oneOf"] == [{"required": ["plan_text"]}, {"required": ["plan_path"]}]


class TestUnstatedStakesAreSurfacedNotBlocked:
    """Absent stakes is the largest cause of review scope-creep, but its fallback is the
    SAFE reading — so this shows, and never refuses."""

    def test_a_review_with_no_stakes_anywhere_says_so(self, tmp_path: Path) -> None:
        out = run_round(FakeEngine(review_with(PROCEDURE_CLASS)), tmp_path)
        assert handlers.STAKES_NOTICE in out

    def test_stated_stakes_silence_the_notice(self, tmp_path: Path) -> None:
        out = handlers.critique_plan(
            {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)),
             "class_closure": False, "stakes": "a real deployment boundary"},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs")
        assert handlers.STAKES_NOTICE not in out

    def test_the_literal_unstated_is_an_explicit_acceptance_not_an_omission(
        self, tmp_path: Path
    ) -> None:
        """`arbitrate`'s trick: saying `unstated` calibrates the reviewer to one fixed
        reading AND records that the caller chose it, so it must not be nagged."""
        engine = FakeEngine(review_with("NONE"))
        out = handlers.critique_plan(
            {"plan_text": "# Plan", "repo_path": str(_bare_repo(tmp_path)),
             "class_closure": False, "stakes": "unstated"},
            engine=engine, log_dir=tmp_path / "logs")
        assert handlers.STAKES_NOTICE not in out
        assert "modest single-team internal tool" in engine.calls[0]

    def test_the_notice_never_blocks_the_review(self, tmp_path: Path) -> None:
        out = run_round(FakeEngine(review_with("NONE")), tmp_path)
        assert "CONVERGENCE: NOT-BLOCKED" in out
        assert handlers.STAKES_NOTICE in out


class TestThereIsExactlyOneEscape:
    """The gap round 1 named: nothing proved that an ACCEPTED branch call with closure
    enabled actually emits a trailer. `converge: false` was a second, silent escape —
    closure never runs on the legacy path, so the call demanded a round, looked gated,
    and returned a review whose own `CONVERGED` nothing could contradict."""

    @pytest.mark.parametrize("extra", [
        {},
        {"converge": True},
        {"include_uncommitted": True},
        {"isolate": False},
        {"already_raised": ["a prior claim, x.py:1"]},
    ])
    def test_every_accepted_closure_enabled_branch_call_emits_a_trailer(
        self, extra: dict, git_repo: Path, tmp_path: Path
    ) -> None:
        out = handlers.critique_branch(
            {"repo_path": str(git_repo), "base_ref": "main", "round": 1,
             "lineage": f"one-escape-{len(extra)}-branch", **extra},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs",
            now=lambda: "T9")
        assert "CONVERGENCE:" in out

    def test_converge_false_with_closure_on_is_refused_naming_both_remedies(
        self, git_repo: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError) as exc:
            handlers.critique_branch(
                {"repo_path": str(git_repo), "base_ref": "main", "round": 1,
                 "converge": False},
                engine=FakeEngine(), log_dir=tmp_path / "logs")
        assert "converge: false" in str(exc.value)
        assert "class_closure: false" in str(exc.value)

    def test_a_config_sourced_converge_false_is_refused_with_a_remedy_that_works(
        self, git_repo: Path, tmp_path: Path
    ) -> None:
        """`converge` resolves from .paranoia.toml too, so "drop `converge: false`" is no
        remedy at all when the caller never passed it. The gap that let that ship was
        testing only the call-argument shape."""
        (git_repo / ".paranoia.toml").write_text("converge = false\n")
        with pytest.raises(ValueError) as exc:
            handlers.critique_branch(
                {"repo_path": str(git_repo), "base_ref": "main", "round": 1},
                engine=FakeEngine(), log_dir=tmp_path / "logs")
        assert "converge: true" in str(exc.value)
        assert ".paranoia.toml" in str(exc.value)

    def test_the_config_sourced_remedy_actually_resolves_the_refusal(
        self, git_repo: Path, tmp_path: Path
    ) -> None:
        (git_repo / ".paranoia.toml").write_text("converge = false\n")
        out = handlers.critique_branch(
            {"repo_path": str(git_repo), "base_ref": "main", "round": 1,
             "converge": True, "lineage": "cfg-remedy-branch"},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs",
            now=lambda: "T8")
        assert "CONVERGENCE:" in out

    def test_the_legacy_path_is_still_reachable_through_the_one_shot_mode(
        self, git_repo: Path, tmp_path: Path
    ) -> None:
        out = handlers.critique_branch(
            {"repo_path": str(git_repo), "base_ref": "main", "converge": False,
             "class_closure": False},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs")
        assert "CONVERGENCE:" not in out

    @pytest.mark.parametrize("bad", [0, -1, "3", 1.0, True, None])
    def test_a_round_that_renders_no_floor_is_refused_not_silently_accepted(
        self, bad: object, git_repo: Path, tmp_path: Path
    ) -> None:
        """`_calibration` renders ROUND only for an int >= 1, so 0 and "3" produce exactly
        what omitting it produces — no floor — while only None ever looked like a mistake."""
        args = {"repo_path": str(git_repo), "base_ref": "main", "lineage": "bad-round-branch"}
        if bad is not None:
            args["round"] = bad
        with pytest.raises(ValueError, match="integer >= 1"):
            handlers.critique_branch(args, engine=FakeEngine(), log_dir=tmp_path / "logs")
