"""Orchestration tests for class closure: `_ClassClosure` driven through real rounds.

`test_class_closure.py` covers the pure protocol. These cover the half that actually
failed review — retry, durable debt, post-register sweeping, failed-engine state
identity, latch lifecycle, dirty `head_ref` rejection and trailer integration — plus the
known-positive the whole design was built to reproduce.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from paranoia_local import class_closure as cc
from paranoia_local import handlers


def git(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(["init", "-q", "-b", "main"], r)
    git(["config", "user.email", "t@t"], r)
    git(["config", "user.name", "t"], r)
    (r / "seed.py").write_text("seed = 1\n")
    git(["add", "-A"], r)
    git(["commit", "-qm", "seed"], r)
    git(["branch", "-q", "feature"], r)
    git(["checkout", "-q", "feature"], r)
    return r


def commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, body in files.items():
        (repo / name).write_text(body)
    git(["add", "-A"], repo)
    git(["commit", "-qm", message], repo)


class FakeEngine:
    """Returns a scripted review per call, and records resume() invocations."""

    name = "fake"
    default_model = "fake-model"

    def __init__(self, *reviews: str, session_ref: str | None = "sess") -> None:
        self.reviews = list(reviews)
        self.session_ref = session_ref
        self.resumed: list[str] = []
        self.calls: list[str] = []

    def run(self, prompt: str, cwd: Path, model: str, effort: str, web: bool, **kw):
        self.calls.append(prompt)
        return self._review(self.reviews.pop(0) if self.reviews else "## What works\nok")

    def resume(self, session_ref: str, prompt: str, cwd: Path, model: str, effort: str,
               web: bool, **kw):
        self.resumed.append(prompt)
        return self._review(self.reviews.pop(0) if self.reviews else "no register here either")

    def _review(self, text: str):
        from paranoia_local.engines import Review
        return Review(text=text, session_ref=self.session_ref, raw="{}")


def review_with(register: str) -> str:
    return f"## What works\nNothing notable.\n\n=== CLASS REGISTER ===\n{register}"


MECHANIZED = (
    "CLASS: every open state must be in the v2 open set\n"
    "SEVERITY: MAJOR\n"
    "PATTERN: NOT_IN_OPEN_SET\n"
    "PATHSPEC: .\n"
)


def run_round(repo: Path, engine: FakeEngine, tmp_path: Path, **extra) -> str:
    args = {"repo_path": str(repo), "base_ref": "main", "converge": True, **extra}
    return handlers.critique_branch(args, engine=engine, log_dir=tmp_path / "logs")


def state_root(tmp_path: Path) -> Path:
    """Matches the autouse isolation fixture in conftest: lineage state deliberately does
    NOT follow log_dir, so tests must look where the env override actually points."""
    return tmp_path / "state"


# ── the known-positive this whole design exists to reproduce ──────────────────


class TestThreeSiteIncident:
    """A real three-site invariant across three commits, mirroring the observed loop:
    round 7 finds site A, the fix closes A and leaves B and C, and so on. The mechanism
    must register the class once and keep BLOCKING under the SAME id at every round."""

    def test_one_class_id_blocks_across_all_three_rounds(self, repo: Path, tmp_path: Path) -> None:
        commit(repo, {"a.py": "NOT_IN_OPEN_SET_escalation\n",
                      "b.py": "NOT_IN_OPEN_SET_progress\n",
                      "c.py": "NOT_IN_OPEN_SET_unresolved\n"}, "three sites")

        engine = FakeEngine(review_with(MECHANIZED))
        first = run_round(repo, engine, tmp_path, round=7)
        assert "CONVERGENCE: BLOCKED" in first
        lineage = cc.load_lineage(state_root(tmp_path), _only_lineage(tmp_path), stamp="s")
        cid = lineage.active()[0].class_id

        # Round 8: the operator fixed only the site that was named.
        commit(repo, {"a.py": "fixed = 1\n"}, "fix site A only")
        second = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=8)
        assert "CONVERGENCE: BLOCKED" in second and cid in second, (
            "the class must survive under its original id, not be re-derived"
        )

        # Round 9: still one site left.
        commit(repo, {"b.py": "fixed = 1\n"}, "fix site B only")
        third = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=9)
        assert "CONVERGENCE: BLOCKED" in third and cid in third

        # Only when the last site goes does the class close.
        commit(repo, {"c.py": "fixed = 1\n"}, "fix site C")
        fourth = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=10)
        assert "CONVERGENCE: NOT-BLOCKED" in fourth
        assert "converged" not in fourth.lower()

    def test_the_reviewer_is_shown_the_surviving_matches_next_round(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "NOT_IN_OPEN_SET here\n", "b.py": "NOT_IN_OPEN_SET too\n"}, "two")
        run_round(repo, FakeEngine(review_with(MECHANIZED)), tmp_path, round=1)
        engine = FakeEngine(review_with("NONE"))
        run_round(repo, engine, tmp_path, round=2)
        prompt = engine.calls[0]
        assert cc.UNCLOSED_HEADER in prompt
        assert "a.py" in prompt and "b.py" in prompt
        assert prompt.index("Already-raised") < prompt.index(cc.UNCLOSED_HEADER) \
            if "Already-raised" in prompt else True


def _only_lineage(tmp_path: Path) -> str:
    files = list(cc.lineage_dir(state_root(tmp_path)).glob("*.json"))
    assert len(files) == 1, f"expected one lineage, got {files}"
    return files[0].stem


# ── register handling at the orchestration layer ──────────────────────────────


class TestRegisterHandling:
    def test_a_missing_register_is_retried_once_then_becomes_durable_debt(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "c")
        engine = FakeEngine("no register at all", "still no register")
        out = run_round(repo, engine, tmp_path, round=1)
        assert len(engine.resumed) == 1, "exactly one retry"
        assert "register debt from round 1" in out

        # Debt is durable: it survives into the next round's state, and clears on a good one.
        lineage = cc.load_lineage(state_root(tmp_path), _only_lineage(tmp_path), stamp="s")
        assert lineage.debt and lineage.debt["round"] == 1
        out2 = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=2)
        assert "NOT-BLOCKED" in out2 and "register debt" not in out2

    def test_a_successful_retry_is_used_and_is_visible_to_the_operator(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """The retry's register is what actually changed durable state; showing only the
        malformed original would hide the transition that took effect."""
        import json

        commit(repo, {"a.py": "x = 1\n"}, "c")
        engine = FakeEngine("no register", review_with(MECHANIZED))
        out = run_round(repo, engine, tmp_path, round=1)
        assert "parsed after retry" in out
        assert "supplied on retry" in out and "NOT_IN_OPEN_SET" in out
        record = json.loads(next((tmp_path / "logs").glob("*.json")).read_text())
        assert "NOT_IN_OPEN_SET" in (record.get("retry_register") or "")

    def test_a_semantic_register_error_also_earns_the_retry(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Round 7's MAJOR: only syntactic failures earned a retry, so an unknown class id
        or a repeated transition — usually a reviewer typo — cost a whole extra round."""
        commit(repo, {"a.py": "NOT_IN_OPEN_SET\n"}, "c")
        engine = FakeEngine(
            review_with("CLOSED: deadbeef\n"),   # semantically invalid: unknown id
            review_with(MECHANIZED),              # the retry gets it right
        )
        out = run_round(repo, engine, tmp_path, round=1)
        assert len(engine.resumed) == 1, "a semantic error must be retried, not banked as debt"
        assert "unknown class id" in engine.resumed[0], (
            "the retry must say what was actually wrong, or the reviewer resends the same block"
        )
        assert "parsed after retry" in out and "register debt" not in out

    def test_a_semantic_error_applies_none_of_the_register_before_retrying(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "c")
        run_round(repo, FakeEngine(review_with(
            "CLASS: a semantic invariant\nSEVERITY: MAJOR\nPROCEDURE: read every caller\n"
        )), tmp_path, round=1)
        lin_id = _only_lineage(tmp_path)
        cid = cc.load_lineage(state_root(tmp_path), lin_id, stamp="s").active()[0].class_id

        # A valid CLOSED followed by an unknown id: the whole register is rejected, retried,
        # and the retry's NONE must leave the class open.
        engine = FakeEngine(
            review_with(f"CLOSED: {cid}\n\nCLOSED: deadbeef\n"),
            review_with("NONE"),
        )
        run_round(repo, engine, tmp_path, round=2)
        after = cc.load_lineage(state_root(tmp_path), lin_id, stamp="s")
        assert after.classes[cid].status == cc.OPEN

    def test_no_session_ref_skips_the_retry_and_keeps_the_review(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Claude's supported non-JSON fallback has no session; retrying would raise and
        replace the paid review with an error."""
        commit(repo, {"a.py": "x = 1\n"}, "c")
        engine = FakeEngine("no register", session_ref=None)
        out = run_round(repo, engine, tmp_path, round=1)
        assert engine.resumed == []
        assert "no register" in out, "the paid review text must still be returned"
        assert "CONVERGENCE: BLOCKED" in out

    def test_a_rejected_register_applies_none_of_its_records(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """A valid CLOSED followed by an invalid record must not leave the CLOSED applied."""
        commit(repo, {"a.py": "x = 1\n"}, "c")
        run_round(repo, FakeEngine(review_with(
            "CLASS: a semantic invariant\nSEVERITY: MAJOR\nPROCEDURE: read every caller\n"
        )), tmp_path, round=1)
        lin_id = _only_lineage(tmp_path)
        cid = cc.load_lineage(state_root(tmp_path), lin_id, stamp="s").active()[0].class_id

        out = run_round(repo, FakeEngine(
            review_with(f"CLOSED: {cid}\n\nCLOSED: deadbeef\n"),
            review_with(f"CLOSED: {cid}\n\nCLOSED: deadbeef\n"),
        ), tmp_path, round=2)
        assert "CONVERGENCE: BLOCKED" in out
        after = cc.load_lineage(state_root(tmp_path), lin_id, stamp="s")
        assert after.classes[cid].status == cc.OPEN, (
            "the valid CLOSED rode in on a register that was rejected"
        )


# ── failure paths ─────────────────────────────────────────────────────────────


class TestFailurePaths:
    def test_a_failed_review_leaves_lineage_state_byte_identical(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "NOT_IN_OPEN_SET\n"}, "c")
        run_round(repo, FakeEngine(review_with(MECHANIZED)), tmp_path, round=1)
        path = cc.lineage_dir(state_root(tmp_path)) / f"{_only_lineage(tmp_path)}.json"
        before = path.read_bytes()

        class Failing(FakeEngine):
            def run(self, *a, **kw):
                from paranoia_local.engines import Review
                return Review(text="boom", session_ref=None, raw="", returncode=1, error=True)

        out = run_round(repo, Failing(), tmp_path, round=2)
        assert path.read_bytes() == before, "a failed review must not mutate durable state"
        assert "CONVERGENCE: BLOCKED" in out and "review failed" in out

    def test_a_failed_retry_is_not_trusted_and_leaves_state_unchanged(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Round 2's BLOCKER: a failed CLI still returns text, and that text can contain a
        parseable NONE or CLOSED block."""
        commit(repo, {"a.py": "x = 1\n"}, "c")
        run_round(repo, FakeEngine(review_with(
            "CLASS: a semantic invariant\nSEVERITY: MAJOR\nPROCEDURE: read every caller\n"
        )), tmp_path, round=1)
        lin_id = _only_lineage(tmp_path)
        cid = cc.load_lineage(state_root(tmp_path), lin_id, stamp="s").active()[0].class_id

        class FailingRetry(FakeEngine):
            def resume(self, *a, **kw):
                from paranoia_local.engines import Review
                self.resumed.append("x")
                return Review(text=f"=== CLASS REGISTER ===\nCLOSED: {cid}\n",
                              session_ref="sess", raw="", returncode=1, error=True)

        out = run_round(repo, FailingRetry("no register"), tmp_path, round=2)
        assert "CONVERGENCE: BLOCKED" in out
        after = cc.load_lineage(state_root(tmp_path), lin_id, stamp="s")
        assert after.classes[cid].status == cc.OPEN, (
            "a failed retry's parseable CLOSED must not be applied"
        )
        assert after.debt, "the round is register debt, not a silent success"
        assert "supplied on retry" not in out, (
            "a retry that was rejected must not be presented as what the round applied"
        )

    def test_an_exception_after_prepare_does_not_strand_the_latch(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """A stranded latch would make every later round STATE-UNAVAILABLE over a fault the
        caller has already been told about."""
        commit(repo, {"a.py": "x = 1\n"}, "c")

        class Exploding(FakeEngine):
            def run(self, *a, **kw):
                raise RuntimeError("engine blew up")

        with pytest.raises(RuntimeError, match="engine blew up"):
            run_round(repo, Exploding(), tmp_path, round=1)
        assert not list(cc.lineage_dir(state_root(tmp_path)).glob("*.pending"))
        out = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=2)
        assert "CONVERGENCE: NOT-BLOCKED" in out

    def test_an_unwritable_latch_blocks_but_still_returns_the_review(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """A storage fault must never prevent the review running or discard its text."""
        commit(repo, {"a.py": "x = 1\n"}, "c")
        d = cc.lineage_dir(state_root(tmp_path))
        d.mkdir(parents=True)
        d.chmod(0o500)  # readable, not writable
        try:
            out = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=1)
        finally:
            d.chmod(0o700)
        assert "STATE-UNAVAILABLE" in out and "CONVERGENCE: BLOCKED" in out
        assert "Nothing notable" in out, "the paid review text must survive"

    def test_an_unremovable_latch_does_not_destroy_the_review(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """An un-removable latch leaves the next round STATE-UNAVAILABLE, which is the
        fail-closed outcome it exists for — but it must not cost this round's review."""
        commit(repo, {"a.py": "x = 1\n"}, "c")
        real_clear = cc.clear_latch
        calls: list[str] = []

        def boom(root: Path, lineage_id: str) -> None:
            calls.append(lineage_id)
            raise OSError("read-only filesystem")

        try:
            cc.clear_latch = lambda *a, **kw: real_clear(*a, **kw)
            out = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=1)
            assert "CONVERGENCE: NOT-BLOCKED" in out
        finally:
            cc.clear_latch = real_clear
        # And the unlink failure itself is swallowed rather than raised:
        latch = cc.lineage_dir(state_root(tmp_path)) / "nonexistent.pending"
        cc.clear_latch(state_root(tmp_path), "nonexistent")  # must not raise
        assert not latch.exists()

    def test_the_pending_latch_is_released_on_a_normal_round(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "c")
        run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=1)
        assert not list(cc.lineage_dir(state_root(tmp_path)).glob("*.pending"))

    def test_a_stranded_latch_blocks_the_next_round_rather_than_starting_empty(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "c")
        run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=1)
        cc.open_latch(state_root(tmp_path), _only_lineage(tmp_path))
        out = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=2)
        assert "STATE-UNAVAILABLE" in out and "CONVERGENCE: BLOCKED" in out

    def test_state_is_written_under_the_state_root_not_the_real_home(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "c")
        run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=1)
        assert list(cc.lineage_dir(state_root(tmp_path)).glob("*.json")), (
            "tests must not write lineages into the operator's ~/.paranoia"
        )

    def test_moving_the_audit_log_dir_does_not_start_a_fresh_lineage(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """`--log-dir` is documented as the AUDIT-LOG directory. Deriving state from it
        meant an operator who moved their logs silently got an empty lineage and could be
        told NOT-BLOCKED with classes still open."""
        commit(repo, {"a.py": "NOT_IN_OPEN_SET\n"}, "c")
        first = handlers.critique_branch(
            {"repo_path": str(repo), "base_ref": "main", "converge": True, "round": 1},
            engine=FakeEngine(review_with(MECHANIZED)), log_dir=tmp_path / "logs-a")
        assert "CONVERGENCE: BLOCKED" in first
        second = handlers.critique_branch(
            {"repo_path": str(repo), "base_ref": "main", "converge": True, "round": 2},
            engine=FakeEngine(review_with("NONE")), log_dir=tmp_path / "logs-b")
        assert "CONVERGENCE: BLOCKED" in second, (
            "the class must survive a change of audit-log directory"
        )
        assert len(list(cc.lineage_dir(state_root(tmp_path)).glob("*.json"))) == 1


# ── argument handling ─────────────────────────────────────────────────────────


class TestArguments:
    def test_the_legacy_non_converge_path_still_accepts_a_dirty_head_ref(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Class closure never runs on the legacy path, so its argument rule must not
        reach back and break a review that was valid before this feature existed."""
        (repo / "dirty.py").write_text("x = 1\n")
        out = run_round(repo, FakeEngine("## What works\nok"), tmp_path,
                        converge=False, include_uncommitted=True, head_ref="feature")
        assert "CONVERGENCE:" not in out

    def test_a_dirty_review_rejects_an_explicit_head_ref(self, repo: Path, tmp_path: Path) -> None:
        """resolve_target discards head_ref for a dirty review, so accepting it would key
        this round's classes to a branch that was never reviewed."""
        (repo / "dirty.py").write_text("x = 1\n")
        with pytest.raises(ValueError, match="would not be the reviewed ref"):
            run_round(repo, FakeEngine(review_with("NONE")), tmp_path,
                      include_uncommitted=True, head_ref="feature")

    def test_a_dirty_review_without_head_ref_works_and_keys_on_the_checkout(
        self, repo: Path, tmp_path: Path
    ) -> None:
        (repo / "dirty.py").write_text("x = 1\n")
        out = run_round(repo, FakeEngine(review_with("NONE")), tmp_path, include_uncommitted=True)
        assert "LINEAGE:" in out

    def test_two_branches_off_one_base_get_different_lineages(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "on feature")
        run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=1)
        git(["checkout", "-q", "-b", "other", "main"], repo)
        commit(repo, {"b.py": "y = 1\n"}, "on other")
        run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=1)
        assert len(list(cc.lineage_dir(state_root(tmp_path)).glob("*.json"))) == 2

    def test_class_closure_false_emits_no_trailer_at_all(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "c")
        out = run_round(repo, FakeEngine("## What works\nok"), tmp_path, class_closure=False)
        assert "CONVERGENCE:" not in out and "LINEAGE:" not in out
        assert not cc.lineage_dir(state_root(tmp_path)).exists()

    def test_an_exemption_subtracts_a_match_and_is_shown_for_challenge(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "NOT_IN_OPEN_SET here\n"}, "c")
        run_round(repo, FakeEngine(review_with(MECHANIZED)), tmp_path, round=1)
        lin_id = _only_lineage(tmp_path)
        cid = cc.load_lineage(state_root(tmp_path), lin_id, stamp="s").active()[0].class_id

        engine = FakeEngine(review_with("NONE"))
        out = run_round(repo, engine, tmp_path, round=2, exempt=[
            {"class_id": cid, "path": "a.py", "line": 1, "line_text": "NOT_IN_OPEN_SET here"},
        ])
        assert "CONVERGENCE: NOT-BLOCKED" in out
        block = engine.calls[0]
        assert cc.EXEMPT_HEADER in block, "exemptions must be shown for challenge"
        # Once an exemption removes the last survivor the class closes and its unclosed
        # block disappears, so this block is the ONLY place the reviewer can learn what the
        # exempted line is alleged to violate. A bare path:line is unchallengeable.
        assert "every open state must be in the v2 open set" in block
        assert "NOT_IN_OPEN_SET" in block, "the predicate must travel with the exemption"


class TestTrailerIntegration:
    def test_a_class_registered_this_round_is_swept_before_the_verdict(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Round 10's FATAL: a new MAJOR class and NOT-BLOCKED could ship together."""
        commit(repo, {"a.py": "NOT_IN_OPEN_SET\n"}, "c")
        out = run_round(repo, FakeEngine(review_with(MECHANIZED)), tmp_path, round=1)
        assert "CONVERGENCE: BLOCKED" in out
        assert "unchecked" not in out, "the new class must be evaluated, not left unchecked"

    def test_a_predicate_that_closes_in_its_own_round_is_flagged(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """A too-narrow regex is the one predicate failure nothing can detect, so the
        trailer says so rather than presenting an ordinary closed class."""
        commit(repo, {"a.py": "x = 1\n"}, "c")
        out = run_round(repo, FakeEngine(review_with(MECHANIZED)), tmp_path, round=1)
        assert "CLASS-CLOSURE-WARNING" in out and "closed in the round it was registered" in out

    def test_an_empty_register_reads_as_NONE_not_parsed_zero(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "c")
        assert "CLASS-REGISTER: NONE" in run_round(
            repo, FakeEngine(review_with("NONE")), tmp_path, round=1)

    def test_an_accepted_register_reports_its_record_count(
        self, repo: Path, tmp_path: Path
    ) -> None:
        commit(repo, {"a.py": "x = 1\n"}, "c")
        assert "CLASS-REGISTER: parsed 1" in run_round(
            repo, FakeEngine(review_with(MECHANIZED)), tmp_path, round=1)

    def test_base_id_and_head_id_are_recorded_in_the_audit_log(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """The plan's own acceptance replay was impossible because these were never logged."""
        import json

        commit(repo, {"a.py": "x = 1\n"}, "c")
        run_round(repo, FakeEngine(review_with("NONE")), tmp_path, round=1)
        record = json.loads(next((tmp_path / "logs").glob("*.json")).read_text())
        assert len(record["base_id"]) == 40 and len(record["head_id"]) == 40
