import json
from dataclasses import replace
from pathlib import Path

import pytest

from paranoia_local import class_closure as cc, handlers, review_census as rc
from paranoia_local.engines import Review
from tests.conftest import git


class FakeEngine:
    name = "fake"
    default_model = "fake-model"

    def __init__(self, text: str = "REVIEW BODY", session_ref: str = "sess-1") -> None:
        self.calls: list[dict] = []
        self._text = text
        self._session = session_ref

    def run(self, prompt, cwd, model, effort, web_search, runner=None, timeout=None):
        self.calls.append(
            {"kind": "run", "prompt": prompt, "cwd": cwd, "model": model,
             "effort": effort, "web_search": web_search}
        )
        return Review(text=self._text, session_ref=self._session, raw="")

    def resume(
        self, session_ref, prompt, cwd, model, effort, web_search, runner=None,
        timeout=None, response_schema=None,
    ):
        self.calls.append(
            {"kind": "resume", "session_ref": session_ref, "prompt": prompt,
             "cwd": cwd, "response_schema": response_schema}
        )
        text = self._text if response_schema is not None else "REBUTTAL VERDICT"
        return Review(text=text, session_ref=session_ref, raw=text)


def fixed_clock() -> str:
    return "20260714T120000"


class TestCritiqueBranch:
    def test_runs_reviewer_in_isolated_worktree(self, repo_with_branch: Path, tmp_path: Path) -> None:
        eng = FakeEngine()
        out = handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature",
             "diff_intent": "friendlier greeting", "round": 1},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert "REVIEW BODY" in out
        call = eng.calls[0]
        # reviewer ran in a worktree, NOT the author's checkout
        assert call["cwd"] != repo_with_branch
        assert "paranoia-wt-" in str(call["cwd"])
        # orientation reached the reviewer
        assert "friendlier greeting" in call["prompt"]
        assert "What doesn't work" in call["prompt"]  # the instructions are composed in

    def test_footer_exposes_session_for_rebut(self, repo_with_branch: Path, tmp_path: Path) -> None:
        out = handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature", "round": 1},
            engine=FakeEngine(session_ref="abc-999"), log_dir=tmp_path, now=fixed_clock,
        )
        assert "abc-999" in out

    def test_dirty_tree_runs_in_repo_not_worktree(self, repo: Path, tmp_path: Path) -> None:
        # Legacy (non-converge) path: a dirty review runs in place. converge=False pins it,
        # since converge (materialized snapshot) is now the default.
        (repo / "app.py").write_text("# uncommitted edit\n")
        eng = FakeEngine()
        handlers.critique_branch(
            {"repo_path": str(repo), "include_uncommitted": True, "converge": False, "class_closure": False, "round": 1},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert eng.calls[0]["cwd"] == repo

    def test_isolate_false_runs_in_repo(self, repo_with_branch: Path, tmp_path: Path) -> None:
        # Legacy path: isolate=false reviews in place. converge=False required now that
        # converge is the default (and converge always materializes, overriding isolate).
        eng = FakeEngine()
        handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature",
             "isolate": False, "class_closure": False, "converge": False, "class_closure": False, "round": 1},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert eng.calls[0]["cwd"] == repo_with_branch

    def test_already_raised_passed_through(self, repo_with_branch: Path, tmp_path: Path) -> None:
        eng = FakeEngine()
        handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature",
             "already_raised": ["app.py:5 — greeting not escaped"], "round": 1},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert "greeting not escaped" in eng.calls[0]["prompt"]

    def test_stakes_and_round_reach_reviewer(self, repo_with_branch: Path, tmp_path: Path) -> None:
        eng = FakeEngine()
        handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature",
             "stakes": "single-user CLI ZZZMARK", "round": 3},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        p = eng.calls[0]["prompt"]
        assert "single-user CLI ZZZMARK" in p
        assert "ROUND: 3" in p

    def test_stakes_resolved_from_repo_config(self, repo_with_branch: Path, tmp_path: Path) -> None:
        (repo_with_branch / ".paranoia.toml").write_text('stakes = "CFGSTAKES"\n')
        eng = FakeEngine()
        handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature", "round": 1},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert "CFGSTAKES" in eng.calls[0]["prompt"]

    def test_round_below_one_is_refused_in_both_modes(
        self, repo_with_branch: Path, tmp_path: Path
    ) -> None:
        # dogfood finding: the schema is 1-based and a non-positive round emits no ROUND
        # line. It used to be silently ignored; silently ignoring a round the caller took
        # the trouble to pass is how a loop believes it has a floor it never had. A
        # SUPPLIED round is now checked in both modes — only OMITTING it is the one-shot
        # mode's privilege.
        for extra in ({}, {"class_closure": False}):
            with pytest.raises(ValueError, match="integer >= 1"):
                handlers.critique_branch(
                    {"repo_path": str(repo_with_branch), "base_ref": "main",
                     "head_ref": "feature", "round": 0, **extra},
                    engine=FakeEngine(), log_dir=tmp_path, now=fixed_clock,
                )

    def test_no_calibration_block_in_body_when_absent(self, repo_with_branch: Path, tmp_path: Path) -> None:
        # The instructions always DESCRIBE the calibration block; assert it isn't
        # INJECTED into the task-input body when neither stakes nor round is given.
        # `round` is required once class closure is tracking a loop, so the only shape
        # with neither is the explicit one-shot mode.
        eng = FakeEngine()
        handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature",
             "class_closure": False},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        body = eng.calls[0]["prompt"].split("===== TASK INPUT =====", 1)[1]
        assert "REVIEW CALIBRATION" not in body

    def test_writes_audit_log(self, repo_with_branch: Path, tmp_path: Path) -> None:
        handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature", "round": 1},
            engine=FakeEngine(), log_dir=tmp_path, now=fixed_clock,
        )
        logs = list(tmp_path.glob("*.json"))
        assert len(logs) == 1
        assert "critique_branch" in logs[0].name

    def test_repo_config_supplies_base_ref(self, repo_with_branch: Path, tmp_path: Path) -> None:
        # config sets base_ref so the caller can omit it
        (repo_with_branch / ".paranoia.toml").write_text('base_ref = "main"\n')
        git(["add", "-A"], repo_with_branch)
        eng = FakeEngine()
        handlers.critique_branch(
            {"repo_path": str(repo_with_branch), "head_ref": "feature", "round": 1},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        # a diff was computed against main (feature's change is visible)
        assert "hello {name}!" in eng.calls[0]["prompt"]

    def test_missing_repo_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not a git repo|does not exist"):
            handlers.critique_branch(
                {"repo_path": "/no/such/repo"}, engine=FakeEngine(),
                log_dir=tmp_path, now=fixed_clock,
            )


class TestCritiquePlan:
    def test_rejects_both_text_and_path(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not both"):
            handlers.critique_plan(
                {"plan_text": "x", "plan_path": "/tmp/y.md", "repo_path": str(tmp_path)},
                engine=FakeEngine(), log_dir=tmp_path, now=fixed_clock,
            )

    def test_rejects_neither(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="plan_text or plan_path"):
            handlers.critique_plan(
                {"repo_path": str(tmp_path)}, engine=FakeEngine(), log_dir=tmp_path,
                now=fixed_clock,
            )

    def test_plan_text_reaches_reviewer(self, repo: Path, tmp_path: Path) -> None:
        eng = FakeEngine()
        handlers.critique_plan(
            {"plan_text": "Step 1: rewrite the auth layer.", "repo_path": str(repo),
             "class_closure": False},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert "rewrite the auth layer" in eng.calls[0]["prompt"]

    def test_plan_path_is_read(self, repo: Path, tmp_path: Path) -> None:
        plan = tmp_path / "plan.md"
        plan.write_text("# Plan\nDo the risky thing.\n")
        eng = FakeEngine()
        handlers.critique_plan(
            {"plan_path": str(plan), "repo_path": str(repo), "class_closure": False},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert "risky thing" in eng.calls[0]["prompt"]

    def test_stakes_and_round_reach_plan_reviewer(self, repo: Path, tmp_path: Path) -> None:
        eng = FakeEngine()
        handlers.critique_plan(
            {"plan_text": "do a thing", "stakes": "PLANSTAKESMARK", "round": 5,
             "repo_path": str(repo), "class_closure": False},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        p = eng.calls[0]["prompt"]
        assert "PLANSTAKESMARK" in p
        assert "ROUND: 5" in p

    def test_repo_grounding_runs_in_repo(self, repo: Path, tmp_path: Path) -> None:
        eng = FakeEngine()
        handlers.critique_plan(
            {"plan_text": "change greet()", "repo_path": str(repo), "class_closure": False},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert eng.calls[0]["cwd"] == repo
        assert "REPOSITORY IS AVAILABLE" in eng.calls[0]["prompt"]


class TestQuery:
    def test_direct_question_lower_effort(self, repo: Path, tmp_path: Path) -> None:
        eng = FakeEngine()
        handlers.query(
            {"question": "Is greet() injection-safe?", "repo_path": str(repo)},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        call = eng.calls[0]
        assert "injection-safe" in call["prompt"]
        assert call["effort"] == "medium"  # query uses lower effort than reviews
        assert call["cwd"] == repo

    def test_question_required(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="question"):
            handlers.query({}, engine=FakeEngine(), log_dir=tmp_path, now=fixed_clock)


class TestRebut:
    def test_resumes_session(self, repo: Path, tmp_path: Path) -> None:
        eng = FakeEngine()
        out = handlers.rebut(
            {"repo_path": str(repo), "session_ref": "sess-1",
             "rebuttal": "That line is unreachable because X.", "round": 1},
            engine=eng, log_dir=tmp_path, now=fixed_clock,
        )
        assert "REBUTTAL VERDICT" in out
        call = eng.calls[0]
        assert call["kind"] == "resume"
        assert call["session_ref"] == "sess-1"
        assert "unreachable because X" in call["prompt"]

    def test_requires_session_and_rebuttal(self, repo: Path, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            handlers.rebut(
                {"repo_path": str(repo), "rebuttal": "x", "round": 1},
                engine=FakeEngine(), log_dir=tmp_path, now=fixed_clock,
            )

    def test_bound_rebut_concede_settles_exact_debt_and_closes_class(
        self, repo: Path, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "state"))
        state = rc.normalize_state(None, stakes="s", snapshot="p")
        debt = {
            "id":"D1", "finding_id":"F1", "status":"open", "severity":cc.MAJOR,
            "summary":"wrong finding", "evidence":["plan:1"], "remedy":"withdraw",
            "source_ids":[], "class_ids":["class-a"], "first_round":1,
            "last_round":7, "reason":"still present",
        }
        state.update(phase="correction", last_round=7, debt=[debt])
        tracked = cc.TrackedClass(
            "class-a", "invariant", cc.MAJOR, 1, cc.OPEN, procedure="inspect",
        )
        state["correction_control"] = {
            "version":1, "classes":{"class-a":{
                "reset_round":None, "reopen_count":3,
                "last_session_ref":"sess-1",
            }},
        }
        cc.save_lineage(cc.default_state_root(), cc.Lineage(
            "bound-rebut", mode=cc.PLAN_MODE,
            classes={tracked.class_id:tracked}, review_state=state,
        ))
        eng = FakeEngine(json.dumps({
            "disposition":"CONCEDE", "reason":"The finding used the wrong path.",
            "evidence":["repository/app.py:1"],
        }))
        result = handlers.rebut({
            "repo_path":str(repo), "session_ref":"sess-1",
            "rebuttal":"The scope disposition is explicit.",
            "lineage":"bound-rebut", "class_id":"class-a", "debt_id":"D1",
            "lineage_mode":"plan",
        }, engine=eng, log_dir=tmp_path / "logs", now=fixed_clock)
        reloaded = cc.load_lineage(
            cc.default_state_root(), "bound-rebut", stamp="T", mode=cc.PLAN_MODE,
        )
        assert result.startswith("CONCEDE: The finding used the wrong path.")
        assert reloaded.review_state["phase"] == "final"
        assert reloaded.review_state["last_round"] == 7
        assert reloaded.review_state["debt"][0]["status"] == "closed"
        assert reloaded.review_state["debt"][0]["evidence"] == ["repository/app.py:1"]
        assert "reason" not in reloaded.review_state["debt"][0]
        assert reloaded.classes["class-a"].status == cc.CLOSED
        assert reloaded.review_state["correction_control"]["classes"]["class-a"] == {
            "reset_round":None, "reopen_count":0, "last_session_ref":None,
        }

        with pytest.raises(ValueError, match="not currently blocking"):
            handlers.rebut({
                "repo_path":str(repo), "session_ref":"stale",
                "rebuttal":"again", "lineage":"bound-rebut",
                "class_id":"class-a", "debt_id":"D1", "lineage_mode":"plan",
            }, engine=eng, log_dir=tmp_path / "logs", now=fixed_clock)
        assert len(eng.calls) == 1
        audits = [json.loads(path.read_text()) for path in (tmp_path / "logs").glob("*.json")]
        rejected = [row for row in audits if row.get("error")]
        assert len(rejected) == 1
        assert rejected[0]["lineage_binding"] == {
            "lineage":"bound-rebut", "class_id":"class-a", "debt_id":"D1",
            "lineage_mode":"plan",
        }
        successful = [row for row in audits if not row.get("error")][0]
        assert successful["disposition"] == "CONCEDE"
        assert successful["prior_target_debt"] == debt
        assert successful["rebut_evidence"] == ["repository/app.py:1"]
        assert successful["debt_settled"] is True
        assert successful["class_closed"] is True

    def test_bound_rebut_identity_is_all_or_none(self, repo: Path, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="requires lineage, class_id, debt_id, and lineage_mode"):
            handlers.rebut({
                "repo_path":str(repo), "session_ref":"sess-1", "rebuttal":"x",
                "lineage":"only-lineage",
            }, engine=FakeEngine(), log_dir=tmp_path, now=fixed_clock)

    def test_bound_rebut_hold_is_audit_only(
        self, repo: Path, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "state"))
        debt = {
            "id":"D1", "finding_id":"F1", "status":"open", "severity":cc.MAJOR,
            "summary":"finding", "evidence":["plan:1"], "remedy":"repair",
            "source_ids":[], "class_ids":["class-a"], "first_round":1,
            "last_round":7, "reason":"still present",
        }
        state = rc.normalize_state(None, stakes="s", snapshot="p")
        state.update(phase="correction", last_round=7, debt=[debt])
        state["correction_control"] = {"version":1, "classes":{"class-a":{
            "reset_round":None, "reopen_count":3, "last_session_ref":"sess-1",
        }}}
        lineage = cc.Lineage(
            "hold-rebut", mode=cc.PLAN_MODE,
            classes={"class-a":cc.TrackedClass(
                "class-a", "invariant", cc.MAJOR, 1, cc.OPEN, procedure="inspect",
            )}, review_state=state,
        )
        cc.save_lineage(cc.default_state_root(), lineage)
        before = json.loads(json.dumps((tmp_path / "state" / "lineages" / "hold-rebut.json").read_text()))
        eng = FakeEngine(json.dumps({
            "disposition":"HOLD", "reason":"The counter-evidence misses the path.",
            "evidence":["repository/app.py:1"],
        }))
        result = handlers.rebut({
            "repo_path":str(repo), "session_ref":"sess-1", "rebuttal":"counter",
            "lineage":"hold-rebut", "class_id":"class-a", "debt_id":"D1",
            "lineage_mode":"plan",
        }, engine=eng, log_dir=tmp_path / "logs", now=fixed_clock)
        after = json.loads(json.dumps((tmp_path / "state" / "lineages" / "hold-rebut.json").read_text()))
        assert result.startswith("HOLD: The counter-evidence misses the path.")
        assert after == before
        audit = json.loads(next((tmp_path / "logs").glob("*.json")).read_text())
        assert audit["disposition"] == "HOLD"
        assert audit["debt_settled"] is False
        assert audit["class_closed"] is False

    def test_bound_rebut_ambiguous_save_is_audited_and_retains_latch(
        self, repo: Path, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.setenv(cc.STATE_ROOT_ENV, str(tmp_path / "state"))
        state = rc.normalize_state(None, stakes="s", snapshot="p")
        state.update(phase="correction", last_round=7, debt=[{
            "id":"D1", "finding_id":"F1", "status":"open", "severity":cc.MAJOR,
            "summary":"wrong finding", "evidence":["plan:1"], "remedy":"withdraw",
            "source_ids":[], "class_ids":["class-a"], "first_round":1,
            "last_round":7, "reason":"still present",
        }])
        tracked = cc.TrackedClass(
            "class-a", "invariant", cc.MAJOR, 1, cc.OPEN, procedure="inspect",
        )
        state["correction_control"] = {"version":1, "classes":{"class-a":{
            "reset_round":None, "reopen_count":3, "last_session_ref":"sess-1",
        }}}
        cc.save_lineage(cc.default_state_root(), cc.Lineage(
            "ambiguous-rebut", mode=cc.PLAN_MODE,
            classes={"class-a":tracked}, review_state=state,
        ))
        monkeypatch.setattr(
            cc, "save_lineage",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                cc.StateUnavailable("ambiguous rebut write")
            ),
        )
        with pytest.raises(cc.StateUnavailable, match="ambiguous rebut write"):
            handlers.rebut({
                "repo_path":str(repo), "session_ref":"sess-1", "rebuttal":"scope",
                "lineage":"ambiguous-rebut", "class_id":"class-a", "debt_id":"D1",
                "lineage_mode":"plan",
            }, engine=FakeEngine(json.dumps({
                "disposition":"CONCEDE", "reason":"wrong", "evidence":["app.py:1"],
            })), log_dir=tmp_path / "logs", now=fixed_clock)
        pending = cc.lineage_dir(cc.default_state_root()) / "ambiguous-rebut.pending"
        assert pending.exists()
        audit = json.loads(next((tmp_path / "logs").glob("*.json")).read_text())
        assert audit["error"] is True
        assert audit["debt_settled"] is False
        cc.clear_latch(cc.default_state_root(), "ambiguous-rebut")
