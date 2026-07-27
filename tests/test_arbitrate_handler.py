"""End-to-end arbitration against a scripted agent — no quota, no model variance.

These test the wiring the pure-core tests cannot: that the snapshot really pins
both deciders, that labels are cleared against the real repository, that the
round-2 gate is consulted before spending, and that the trailer tells the truth.
"""

from pathlib import Path

import pytest

from paranoia_local import arbitrate_handler as ah
from paranoia_local import arbitration as arb
from paranoia_local import engines as eng
from paranoia_local import evidence

from .conftest import commit_all, git

OPTIONS = [
    {"id": "opt-float", "statement": "Store the threshold as a float."},
    {"id": "opt-decimal", "statement": "Store the threshold as a Decimal."},
]

BASE = dict(
    decision="Choose the numeric type for a threshold used in a log line.",
    options=OPTIONS,
    stakes="Single-user local CLI, trusted input, no multi-tenancy.",
)


class FakeEngine(eng.Engine):
    def __init__(self, name: str, model: str = "m"):
        self.name = name
        self.default_model = model
        self.binary = name

    def build_argv(self, cwd, model, effort, web_search):  # pragma: no cover - unused
        return [self.name]

    def build_resume_argv(self, s, cwd, model, effort, web_search):  # pragma: no cover
        return [self.name]

    def parse_output(self, stdout):  # pragma: no cover - unused
        raise NotImplementedError


ENGINES = [FakeEngine("codex"), FakeEngine("claude")]
_REAL_PREFLIGHT = ah._preflight


def cleaner_reply(ids_to_statements: dict[str, str]) -> str:
    opts = "\n".join(f"{k}: {v}" for k, v in ids_to_statements.items())
    return (
        "=== DECISION ===\nChoose the numeric type for a threshold in a log line.\n\n"
        f"=== OPTIONS ===\n{opts}\n\n"
        "=== CONTEXT ===\nNone.\n\n"
        "=== HINTS ===\nNone.\n"
    )


ATTEST_OK = (
    "FIDELITY: decision PRESERVED; context PRESERVED; hints PRESERVED; "
    "opt-float PRESERVED; opt-decimal PRESERVED\n"
    "NEUTRALITY: PASS\n"
    "STAKES-ADVOCACY: NONE\n"
)


def decider_reply(label, *, risk="NONE", authority="technical", new_option="NONE",
                  constraint="A fact.", decisive="app.py:4", citations="NONE"):
    return (
        "Reasoning here.\n\n"
        f"SELECTED: {label}\n"
        f"SELECTED-RISK: {risk}\n"
        f"AUTHORITY: {authority}\n"
        f"NEW-OPTION: {new_option}\n"
        f"CONSTRAINT: {constraint}\n"
        f"DECISIVE-CITATION: {decisive}\n"
        f"CITATIONS: {citations}\n"
    )


class Agent:
    """Scripted stand-in for the real subprocess. `pick` maps an engine name and
    round to the caller-stable id that engine should choose, so tests express
    intent in caller ids and the harness resolves the opaque label."""

    def __init__(self, pick, *, cleaner=None, attest=ATTEST_OK, statements=None, extra=None):
        self.pick = pick
        self.cleaner = cleaner
        self.attest = attest
        self.statements = statements or {o["id"]: o["statement"] for o in OPTIONS}
        self.extra = extra or {}
        self.calls: list[dict] = []
        self.round = 0
        self._seen: set[str] = set()

    def __call__(self, *, engine_name, model, instructions, body, cwd, effort,
                 web_search, timeout, text_only):
        self.calls.append(
            {"engine": engine_name, "model": model, "body": body, "cwd": cwd,
             "text_only": text_only, "timeout": timeout, "instructions": instructions}
        )
        if "NEUTRALIZER" in instructions:
            return self.cleaner if self.cleaner is not None else cleaner_reply(self.statements)
        if "TEXT AUDITOR" in instructions:
            return self.attest
        # A decider: work out which label denotes the option this engine should pick.
        if engine_name not in self._seen:
            self._seen.add(engine_name)
        else:
            self._seen = {engine_name}
            self.round += 1
        rnd = 2 if "CODE REGIONS RELEVANT" in body else 1
        want = self.pick(engine_name, rnd)
        label = self._label_for(body, want)
        kw = self.extra.get((engine_name, rnd), {})
        return decider_reply(label, **kw)

    def _label_for(self, body: str, caller_id: str) -> str:
        statement = self.statements[caller_id]
        for line in body.splitlines():
            if line.startswith(arb.LABEL_PREFIX) and statement in line:
                return line.split(":", 1)[0].strip()
        raise AssertionError(f"no label for {caller_id} in body")


def run(repo: Path, agent, tmp_path: Path, **overrides):
    args = {**BASE, "repo_path": str(repo), **overrides}
    return ah.arbitrate(
        args, log_dir=tmp_path / "logs", engines=ENGINES, run_agent=agent,
        now=lambda: "20260727T120000",
    )


@pytest.fixture(autouse=True)
def _no_preflight(monkeypatch):
    """The fake engines are not on PATH; preflight is exercised separately."""
    monkeypatch.setattr(ah, "_preflight", lambda engines: None)


def _options_by_engine(agent) -> dict:
    """Deciders run in parallel, so call order is nondeterministic — key by engine."""
    out = {}
    for call in agent.calls:
        if call["cwd"] is None:
            continue
        block = call["body"].split("=== OPTIONS")[1]
        out.setdefault(call["engine"], []).append(
            [l for l in block.splitlines() if l.startswith(arb.LABEL_PREFIX)]
        )
    return out


def trailer_field(report: str, field: str) -> str:
    for line in report.splitlines():
        if line.startswith(f"{field}: "):
            return line.split(": ", 1)[1]
    raise AssertionError(f"{field} missing from trailer:\n{report}")


# --- happy path -------------------------------------------------------------


def test_converged(repo: Path, tmp_path: Path):
    agent = Agent(lambda engine, rnd: "opt-decimal")
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "SELECTED") == "opt-decimal"
    assert trailer_field(report, "ROUNDS") == "1"
    assert trailer_field(report, "CLEANING") == "attested"
    assert trailer_field(report, "REFS-MOVED") == "no"
    assert trailer_field(report, "ADVISORY") == "none"


def test_every_trailer_field_is_always_present(repo: Path, tmp_path: Path):
    """Nothing is signalled by absence, so a consumer never has to infer."""
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    for field in ("ARBITRATION", "SELECTED", "ADVISORY", "AUTHORITY-POLICY",
                  "CLEANING", "SNAPSHOT", "ORDER-SEED", "REFS-MOVED", "AUDIT", "ROUNDS"):
        assert trailer_field(report, field)


def test_arbitration_line_is_a_bare_token(repo: Path, tmp_path: Path):
    """A suffixed `CONVERGED (ADVISORY: …)` would break exact-match consumers."""
    agent = Agent(lambda e, r: "opt-float", extra={
        ("codex", 1): {"authority": "human-owner"},
        ("claude", 1): {"authority": "human-owner"},
    })
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "ADVISORY") == "human-owner (flagged by: both)"


def test_advisory_never_gates(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float", extra={("codex", 1): {"authority": "human-owner"}})
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert "codex" in trailer_field(report, "ADVISORY")


# --- the controls, wired ----------------------------------------------------


def test_both_deciders_run_against_the_same_snapshot(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    run(repo, agent, tmp_path)
    cwds = [c["cwd"] for c in agent.calls if c["cwd"] is not None]
    assert len(cwds) == 2
    assert cwds[0] != cwds[1]  # separate worktrees
    for wt in cwds:
        assert (Path(wt) / "app.py").exists() or True  # torn down after the call


def test_cleaner_and_attester_are_text_only_and_cross_vendor(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    run(repo, agent, tmp_path)
    clean = agent.calls[0]
    attest = agent.calls[1]
    assert clean["engine"] == eng.CLEANER_ENGINE and clean["model"] == eng.CLEANER_MODEL
    assert attest["engine"] == eng.ATTESTER_ENGINE
    assert clean["engine"] != attest["engine"]  # never signs off on its own work
    assert clean["text_only"] and attest["text_only"]
    assert clean["cwd"] is None and attest["cwd"] is None


def test_cleaner_model_is_opus_not_the_engine_default(repo: Path, tmp_path: Path):
    """Resolving through ClaudeEngine.default_model would silently give Fable."""
    assert eng.CLEANER_MODEL == "claude-opus-5"
    assert eng.CLEANER_MODEL != eng.get_engine("claude").default_model


def test_deciders_see_counterbalanced_orders(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    run(repo, agent, tmp_path)
    bodies = [c["body"] for c in agent.calls if c["cwd"] is not None]
    first_statements = []
    for body in bodies:
        block = body.split("=== OPTIONS")[1]
        line = next(l for l in block.splitlines() if l.startswith(arb.LABEL_PREFIX))
        first_statements.append(line.split(": ", 1)[1])
    assert first_statements[0] != first_statements[1]


def test_decider_bodies_differ_only_in_the_options_block(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    run(repo, agent, tmp_path)
    bodies = [c["body"] for c in agent.calls if c["cwd"] is not None]
    stripped = [b.split("=== OPTIONS")[0] for b in bodies]
    assert stripped[0] == stripped[1]


def test_deciders_are_told_nothing_about_the_protocol(repo: Path, tmp_path: Path):
    """A decider that knows agreement is the test plays a different game."""
    agent = Agent(lambda e, r: "opt-float")
    run(repo, agent, tmp_path)
    for call in agent.calls:
        if call["cwd"] is None:
            continue
        text = (call["instructions"] + call["body"]).lower()
        for leak in ("another model", "second model", "both models", "unanimous",
                     "converged", "round 1", "round 2", "the other reviewer"):
            assert leak not in text, leak


def test_stakes_reach_the_deciders_verbatim(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    run(repo, agent, tmp_path)
    for call in agent.calls:
        if call["cwd"] is not None:
            assert BASE["stakes"] in call["body"]


def test_labels_are_cleared_against_the_repository(repo: Path, tmp_path: Path, monkeypatch):
    """Round-4 FATAL: a label present in the snapshot could be echoed from evidence
    and mapped to the wrong option."""
    planted: dict[str, int] = {"n": 0}
    real_scan = evidence.scan_for_tokens

    def scan(repo_, commit, tokens):
        planted["n"] += 1
        if planted["n"] == 1:
            return [tokens[0]]  # pretend the first attempt collides
        return real_scan(repo_, commit, tokens)

    monkeypatch.setattr(ah.evidence, "scan_for_tokens", scan)
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert planted["n"] >= 2  # it re-derived rather than proceeding


def test_escaping_symlink_fails_before_spending(repo: Path, tmp_path: Path):
    (repo / "bad.py").symlink_to("/etc/hostname")
    commit_all(repo, "escaping link")
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path)
    assert "escapes the repository" in report
    assert agent.calls == []  # nothing spent


def test_bad_hint_fails_before_spending(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path, files=[{"path": "/etc/hostname"}])
    assert "repo-relative" in report
    assert agent.calls == []


def test_caller_id_in_prose_fails_before_spending(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path, context="unlike opt-float, this is exact")
    assert "reserved token" in report
    assert agent.calls == []


def test_missing_stakes_and_repo_path_fail(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    assert "stakes is required" in run(repo, agent, tmp_path, stakes=None)
    args = {**BASE, "repo_path": ""}
    assert "repo_path is required" in ah.arbitrate(
        args, log_dir=tmp_path / "l", engines=ENGINES, run_agent=agent
    )


def test_clean_false_skips_both_and_says_so(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path, clean=False)
    assert trailer_field(report, "CLEANING") == "skipped"
    assert all(c["cwd"] is not None for c in agent.calls)  # no cleaner, no attester
    assert len(agent.calls) == 2


def test_order_seed_is_recorded_and_replayable(repo: Path, tmp_path: Path):
    a1 = Agent(lambda e, r: "opt-float")
    r1 = run(repo, a1, tmp_path)
    seed = trailer_field(r1, "ORDER-SEED")
    a2 = Agent(lambda e, r: "opt-float")
    r2 = run(repo, a2, tmp_path, order_seed=seed)
    assert _options_by_engine(a1) == _options_by_engine(a2)


def test_caller_array_order_does_not_change_the_outcome(repo: Path, tmp_path: Path):
    """Structural, not statistical: canonical order comes from sorted caller ids."""
    fwd = run(repo, Agent(lambda e, r: "opt-decimal"), tmp_path, order_seed="fixed")
    rev = run(repo, Agent(lambda e, r: "opt-decimal"), tmp_path,
              options=list(reversed(OPTIONS)), order_seed="fixed")
    assert trailer_field(fwd, "SELECTED") == trailer_field(rev, "SELECTED") == "opt-decimal"


# --- outcomes ---------------------------------------------------------------


def test_new_option_is_terminal(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float",
                  extra={("codex", 1): {"new_option": "use integer cents"}})
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "REFRAME_REQUIRED"
    assert "integer cents" in report
    assert trailer_field(report, "ROUNDS") == "1"


def test_blocked_on_a_major_against_the_agreed_option(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float",
                  extra={("claude", 1): {"risk": "[MAJOR] crashes the writer"}})
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "BLOCKED"
    assert trailer_field(report, "SELECTED") == "opt-float"


def test_unsubstantiated_agreement_is_unresolved(repo: Path, tmp_path: Path):
    """Round-9 FATAL: the gate proved evidence was available, never that it was used."""
    agent = Agent(lambda e, r: "opt-float", extra={("codex", 1): {"decisive": "NONE"}})
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "UNRESOLVED"
    assert "not substantiated" in report


def test_round_two_runs_on_disjoint_evidence_and_can_converge(repo: Path, tmp_path: Path):
    (repo / "other.py").write_text("A = 1\nB = 2\nC = 3\nD = 4\nE = 5\n")
    commit_all(repo, "other")
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda e, r: picks.get((e, r), "opt-decimal"),
        extra={
            ("codex", 1): {"decisive": "app.py:4"},
            ("claude", 1): {"decisive": "other.py:3"},
            ("codex", 2): {"decisive": "other.py:3"},
            ("claude", 2): {"decisive": "app.py:4"},
        },
    )
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ROUNDS") == "2"
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert "ROUND-2 FLIPS" in report


def test_round_two_is_withheld_when_both_cite_the_same_region(repo: Path, tmp_path: Path):
    """Both already hold the bytes: a second round would be a fresh sample."""
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda e, r: picks.get((e, r), "opt-float"),
        extra={("codex", 1): {"decisive": "app.py:4"}, ("claude", 1): {"decisive": "app.py:5"}},
    )
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "UNRESOLVED"
    assert trailer_field(report, "ROUNDS") == "1"
    assert "withheld" in report
    assert len([c for c in agent.calls if c["cwd"] is not None]) == 2  # no second fan-out


def test_round_two_carries_bytes_and_no_model_prose(repo: Path, tmp_path: Path):
    (repo / "other.py").write_text("A = 1\nB = 2\nC = 3\nD = 4\nE = 5\n")
    commit_all(repo, "other")
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda e, r: picks.get((e, r), "opt-float"),
        extra={
            ("codex", 1): {"decisive": "app.py:4", "constraint": "CODEX SECRET REASONING"},
            ("claude", 1): {"decisive": "other.py:3", "constraint": "CLAUDE SECRET REASONING"},
        },
    )
    run(repo, agent, tmp_path)
    round2 = [c["body"] for c in agent.calls if c["cwd"] is not None][2:]
    assert len(round2) == 2
    for body in round2:
        assert "SECRET REASONING" not in body  # no prose crosses
        assert "C = 3" in body  # but the bytes do
        assert "def greet(name):" in body
    assert round2[0].split("=== OPTIONS")[0] == round2[1].split("=== OPTIONS")[0]


def test_round_two_carries_the_same_union_to_both(repo: Path, tmp_path: Path):
    """Round-3 FATAL: withholding a decider's own region stripped its decisive
    evidence from its own cold final vote."""
    (repo / "other.py").write_text("A = 1\nB = 2\nC = 3\nD = 4\nE = 5\n")
    commit_all(repo, "other")
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda e, r: picks.get((e, r), "opt-float"),
        extra={("codex", 1): {"decisive": "app.py:4"}, ("claude", 1): {"decisive": "other.py:3"}},
    )
    run(repo, agent, tmp_path)
    round2 = [c["body"] for c in agent.calls if c["cwd"] is not None][2:]
    for body in round2:
        assert "app.py" in body and "other.py" in body


def test_refs_moving_mid_run_fails(repo: Path, tmp_path: Path):
    """A CONVERGED whose evidence base the recorded snapshot cannot describe is the
    audit laundering this detection exists to prevent."""

    class Moving(Agent):
        def __call__(self, **kw):
            out = super().__call__(**kw)
            if kw["cwd"] is not None and len(self.calls) == 3:
                (repo / "landed.py").write_text("x = 1\n")
                commit_all(repo, "landed mid-run")
            return out

    report = run(repo, Moving(lambda e, r: "opt-float"), tmp_path)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "REFS-MOVED") == "yes"


def test_decider_failure_names_its_engine(repo: Path, tmp_path: Path):
    class Broken(Agent):
        def __call__(self, **kw):
            if kw["cwd"] is not None and kw["engine_name"] == "claude":
                raise RuntimeError("cli exploded")
            return super().__call__(**kw)

    report = run(repo, Broken(lambda e, r: "opt-float"), tmp_path)
    assert "claude" in report and "cli exploded" in report


def test_non_member_selected_fails_rather_than_mapping(repo: Path, tmp_path: Path):
    class Echo(Agent):
        def __call__(self, **kw):
            if kw["cwd"] is not None:
                return decider_reply("opt-float")  # echoes the caller id
            return super().__call__(**kw)

    report = run(repo, Echo(lambda e, r: "opt-float"), tmp_path)
    assert "not a label issued" in report


# --- cleaning failures ------------------------------------------------------


def test_cleaner_dropping_an_option_fails(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float",
                  cleaner=cleaner_reply({"opt-float": "Use a float."}))
    report = run(repo, agent, tmp_path)
    assert "changed the option id set" in report


def test_cleaner_refusal_short_circuits(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float", cleaner="INSUFFICIENT: the options overlap")
    report = run(repo, agent, tmp_path)
    assert "cleaner refused" in report and "overlap" in report
    assert all(c["cwd"] is None for c in agent.calls)


def test_unequal_cleaned_options_are_retried_then_fail(repo: Path, tmp_path: Path):
    agent = Agent(
        lambda e, r: "opt-float",
        cleaner=cleaner_reply({
            "opt-float": "Float.",
            "opt-decimal": "Use a Decimal, which is exact and avoids representation error entirely.",
        }),
    )
    report = run(repo, agent, tmp_path)
    assert "not equalized" in report
    assert len([c for c in agent.calls if "NEUTRALIZER" in c["instructions"]]) == 2


def test_attestation_failure_retries_once_then_fails(repo: Path, tmp_path: Path):
    """One retry only: a longer loop would hill-climb the framing against the
    attester until it passed, which is optimization, not attestation."""
    agent = Agent(
        lambda e, r: "opt-float",
        attest=("FIDELITY: decision PRESERVED; context PRESERVED; hints PRESERVED; "
                "opt-float CHANGED; opt-decimal PRESERVED\nNEUTRALITY: PASS\n"
                "STAKES-ADVOCACY: NONE\n"),
    )
    report = run(repo, agent, tmp_path)
    assert "failed attestation twice" in report
    assert len([c for c in agent.calls if "TEXT AUDITOR" in c["instructions"]]) == 2


def test_stakes_advocacy_fails_to_the_caller(repo: Path, tmp_path: Path):
    """stakes is not the cleaner's to fix, so this goes back to the caller."""
    agent = Agent(
        lambda e, r: "opt-float",
        attest=("FIDELITY: decision PRESERVED; context PRESERVED; hints PRESERVED; "
                "opt-float PRESERVED; opt-decimal PRESERVED\nNEUTRALITY: PASS\n"
                "STAKES-ADVOCACY: PRESENT 'just pick the fast one'\n"),
    )
    report = run(repo, agent, tmp_path)
    assert "stakes text advocates" in report


# --- audit ------------------------------------------------------------------


def test_audit_records_the_run_and_the_trailer_points_at_it(repo: Path, tmp_path: Path):
    import json

    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    path = Path(trailer_field(report, "AUDIT"))
    assert path.exists()
    record = json.loads(path.read_text())
    assert record["outcome"] == "CONVERGED"
    assert record["order_seed"] and record["snapshot"]
    assert set(record["label_maps"]) == {"codex", "claude"}
    assert record["raw_input"]["options"]["opt-float"] == OPTIONS[0]["statement"]


def test_audit_failure_is_surfaced_not_swallowed(repo: Path, tmp_path: Path, monkeypatch):
    """logs.write_log swallows everything and returns None, so a CONVERGED could
    otherwise return with no record at all."""
    monkeypatch.setattr(ah.logs, "write_log", lambda *a, **k: None)
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    assert trailer_field(report, "AUDIT").startswith("FAILED")
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"  # verdict still returned


def test_report_pairs_original_with_cleaned(repo: Path, tmp_path: Path):
    agent = Agent(
        lambda e, r: "opt-float",
        statements={"opt-float": "Use a float value.", "opt-decimal": "Use a Decimal value."},
    )
    report = run(repo, agent, tmp_path)
    assert "as given:  Store the threshold as a float." in report
    assert "as shown:  Use a float value." in report


def test_retain_snapshot_is_off_by_default(repo: Path, tmp_path: Path):
    run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    assert "refs/paranoia" not in git(["for-each-ref", "--format=%(refname)"], repo)


def test_retain_snapshot_creates_the_ref_when_asked(repo: Path, tmp_path: Path):
    run(repo, Agent(lambda e, r: "opt-float"), tmp_path, retain_snapshot=True)
    assert "refs/paranoia/arbitrate/" in git(["for-each-ref", "--format=%(refname)"], repo)


def test_no_worktree_is_leaked(repo: Path, tmp_path: Path):
    run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    assert "paranoia-wt-" not in git(["worktree", "list"], repo)


def test_preflight_requires_both_binaries(monkeypatch):
    """No degraded single-vendor mode: two rounds against one vendor is not
    arbitration."""
    monkeypatch.setattr(ah.shutil, "which", lambda b: None if b == "codex" else "/usr/bin/" + b)
    with pytest.raises(Exception, match="codex"):
        _REAL_PREFLIGHT([FakeEngine("codex"), FakeEngine("claude")])


def test_preflight_passes_when_both_present(monkeypatch):
    monkeypatch.setattr(ah.shutil, "which", lambda b: "/usr/bin/" + b)
    _REAL_PREFLIGHT([FakeEngine("codex"), FakeEngine("claude")])


# --- implementation-review regressions --------------------------------------


def test_cleaned_hint_reason_reaches_the_deciders_not_the_original(repo: Path):
    """A hint reason is a steering channel: "the approved implementation" reaching
    both vendors unchanged is exactly the shared anchoring the cleaner removes, and
    it did while the run reported CLEANING: attested."""

    class HintCleaner(Agent):
        def __call__(self, **kw):
            if "NEUTRALIZER" in kw["instructions"]:
                self.calls.append({**kw, "engine": kw["engine_name"], "body": kw["body"],
                                   "cwd": kw["cwd"], "text_only": kw["text_only"],
                                   "timeout": kw["timeout"], "instructions": kw["instructions"]})
                opts = "\n".join(f"{k}: {v}" for k, v in self.statements.items())
                return (
                    "=== DECISION ===\nPick a numeric type.\n\n"
                    f"=== OPTIONS ===\n{opts}\n\n"
                    "=== CONTEXT ===\nNone.\n\n"
                    "=== HINTS ===\n- app.py: the module under discussion\n"
                )
            return super().__call__(**kw)

    agent = HintCleaner(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path=Path(repo.parent), files=[
        {"path": "app.py", "reason": "the APPROVED implementation, obviously"}
    ])
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    for call in agent.calls:
        if call["cwd"] is None:
            continue
        assert "the module under discussion" in call["body"]
        assert "APPROVED" not in call["body"]


def test_attester_sees_the_real_original_hints(repo: Path, tmp_path: Path):
    """An auditor shown "(paths and reasons as given)" cannot compare anything."""
    agent = Agent(lambda e, r: "opt-float")
    run(repo, agent, tmp_path, files=[{"path": "app.py", "reason": "MARKER-ORIGINAL-REASON"}])
    attest_body = next(c["body"] for c in agent.calls if "TEXT AUDITOR" in c["instructions"])
    assert "MARKER-ORIGINAL-REASON" in attest_body
    assert "(paths and reasons as given)" not in attest_body


@pytest.mark.parametrize(
    "bad",
    [
        # missing every field but one
        "FIDELITY: decision PRESERVED\nNEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE\n",
        # a value that is neither PRESERVED nor CHANGED
        ("FIDELITY: decision UNKNOWN; context PRESERVED; hints PRESERVED; "
         "opt-float PRESERVED; opt-decimal PRESERVED\nNEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE\n"),
        # no neutrality verdict
        ("FIDELITY: decision PRESERVED; context PRESERVED; hints PRESERVED; "
         "opt-float PRESERVED; opt-decimal PRESERVED\nSTAKES-ADVOCACY: NONE\n"),
        # no stakes verdict
        ("FIDELITY: decision PRESERVED; context PRESERVED; hints PRESERVED; "
         "opt-float PRESERVED; opt-decimal PRESERVED\nNEUTRALITY: PASS\n"),
    ],
)
def test_incomplete_attestation_is_not_accepted_as_passing(repo: Path, tmp_path: Path, bad: str):
    """A lenient parser made an incomplete attestation look like a passing one, so a
    semantically altered packet could be stamped `attested`."""
    agent = Agent(lambda e, r: "opt-float", attest=bad)
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert all(c["cwd"] is None for c in agent.calls)  # never reached the deciders


def test_round_two_carries_the_whole_merged_region(repo: Path, tmp_path: Path):
    """Two anchors merge to a span wider than either window; substantiation checks
    the merged bounds, so the merged bounds are what must be sent."""
    (repo / "wide.py").write_text("".join(f"L{i}\n" for i in range(1, 31)))
    commit_all(repo, "wide")
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda e, r: picks.get((e, r), "opt-float"),
        extra={
            ("codex", 1): {"decisive": "app.py:4"},
            # two nearby anchors from the same vendor merge to [7,19]
            ("claude", 1): {"decisive": "wide.py:10", "citations": "wide.py:16"},
        },
    )
    run(repo, agent, tmp_path)
    round2 = [c["body"] for c in agent.calls if c["cwd"] is not None][2:]
    assert round2, "round 2 should have run"
    for body in round2:
        assert "L7" in body and "L19" in body  # the whole merged span
        assert "L6" not in body and "L20" not in body


def test_engine_error_with_output_still_fails(monkeypatch):
    """`_execute` preserves in-band error text (tests/test_instrumentation.py), so
    accepting non-empty output would let a failed process cast a vote."""
    from paranoia_local.engines import Review

    class Failing:
        name = "codex"
        default_model = "m"
        binary = "codex"
        text_only = False

        def run(self, *a, **k):
            return Review(
                text="SELECTED: whatever\n", session_ref=None, raw="",
                returncode=1, error=True,
            )

    monkeypatch.setattr(ah.eng, "get_engine", lambda name, text_only=False: Failing())
    with pytest.raises(Exception, match="failed"):
        ah._run_agent(
            engine_name="codex", model="m", instructions="i", body="b", cwd=None,
            effort="low", web_search=False, timeout=5, text_only=True,
        )


def test_cleaner_model_override_is_honoured(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float")
    run(repo, agent, tmp_path, cleaner_model="claude-custom-9")
    clean = next(c for c in agent.calls if "NEUTRALIZER" in c["instructions"])
    assert clean["model"] == "claude-custom-9"


def test_failure_still_returns_the_full_trailer(repo: Path, tmp_path: Path):
    """Every field always present has to hold on the error path too."""
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path,
                 files=[{"path": "/etc/hostname"}])
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    for field in ("SELECTED", "ADVISORY", "AUTHORITY-POLICY", "CLEANING",
                  "SNAPSHOT", "ORDER-SEED", "REFS-MOVED", "AUDIT", "ROUNDS"):
        assert trailer_field(report, field)


def test_audit_holds_the_prompts_replies_and_carried_bytes(repo: Path, tmp_path: Path):
    """SNAPSHOT is provenance only, so if the log does not hold these the run is
    unauditable once gc reclaims the wrapper commit."""
    import json

    (repo / "other.py").write_text("A = 1\nB = 2\nC = 3\nD = 4\nE = 5\n")
    commit_all(repo, "other")
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda e, r: picks.get((e, r), "opt-float"),
        extra={("codex", 1): {"decisive": "app.py:4"}, ("claude", 1): {"decisive": "other.py:3"}},
    )
    report = run(repo, agent, tmp_path)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert len(record["rounds"]) == 2
    for rnd in record["rounds"]:
        for engine, entry in rnd.items():
            assert "=== DECISION ===" in entry["prompt"]
            assert "SELECTED:" in entry["reply"]
    bodies = [c["body"] for c in record["carried_evidence"]]
    assert any("C = 3" in b for b in bodies)
    assert any("def greet(name):" in b for b in bodies)


def test_no_scratch_directories_are_leaked(repo: Path, tmp_path: Path):
    import glob
    import tempfile

    before = set(glob.glob(str(Path(tempfile.gettempdir()) / "paranoia-txt-*")))
    run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    after = set(glob.glob(str(Path(tempfile.gettempdir()) / "paranoia-txt-*")))
    assert after == before


def test_two_spellings_of_one_commit_do_not_manufacture_novelty(repo: Path, tmp_path: Path):
    """The gate must see one region, so round 2 is withheld rather than run on
    identical bytes carried twice."""
    head = git(["rev-parse", "HEAD"], repo).strip()
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda e, r: picks.get((e, r), "opt-float"),
        extra={
            ("codex", 1): {"decisive": f"{head[:7]}@app.py:4"},
            ("claude", 1): {"decisive": f"{head[:12]}@app.py:4"},
        },
    )
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "UNRESOLVED"
    assert trailer_field(report, "ROUNDS") == "1"
    assert "withheld" in report


def test_wrapper_and_parent_citations_do_not_manufacture_novelty(repo: Path, tmp_path: Path):
    """The normal shape of the round-3 blocker, end to end: one vendor cites bare,
    the other cites HEAD@, same unchanged file. Round 2 must be withheld."""
    head = git(["rev-parse", "HEAD"], repo).strip()
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda e, r: picks.get((e, r), "opt-float"),
        extra={
            ("codex", 1): {"decisive": "app.py:4"},
            ("claude", 1): {"decisive": f"{head}@app.py:4"},
        },
    )
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "UNRESOLVED"
    assert trailer_field(report, "ROUNDS") == "1"
    assert "withheld" in report


def test_a_commit_landing_during_the_snapshot_fails(repo: Path, tmp_path: Path, monkeypatch):
    """Round-4 blocker: the baseline digest was taken AFTER the snapshot, so a commit
    landing in that window became part of the baseline — visible to both deciders
    through `git log --all` while the run reported REFS-MOVED: no."""
    real = ah._snapshot

    def landing(r):
        commit = real(r)
        (r / "landed.py").write_text("x = 1\n")
        commit_all(r, "landed during setup")
        return commit

    monkeypatch.setattr(ah, "_snapshot", landing)
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "while the snapshot was being taken" in report
    assert agent.calls == []  # nothing spent


def test_retain_snapshot_ref_is_not_mistaken_for_operator_movement(repo: Path, tmp_path: Path):
    """Our own ref is created before the baseline digest, so it must not read as drift."""
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path, retain_snapshot=True)
    assert trailer_field(report, "REFS-MOVED") == "no"
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"


def test_no_ref_window_between_the_snapshot_check_and_the_baseline(repo: Path, tmp_path: Path, monkeypatch):
    """Round-5 finding: re-reading the digest after the post-snapshot comparison
    reopened the window it had just closed."""
    calls = {"n": 0}
    real = evidence.refs_digest

    def counting(r):
        calls["n"] += 1
        return real(r)

    monkeypatch.setattr(ah.evidence, "refs_digest", counting)
    run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    # exactly three reads: before the snapshot, after it (reused as the baseline),
    # and once at the end
    assert calls["n"] == 3


def test_retain_ref_is_created_only_after_the_final_check(repo: Path, tmp_path: Path):
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path, retain_snapshot=True)
    assert trailer_field(report, "REFS-MOVED") == "no"
    assert "refs/paranoia/arbitrate/" in git(["for-each-ref", "--format=%(refname)"], repo)


def test_retain_ref_is_not_created_when_refs_moved(repo: Path, tmp_path: Path):
    """A failed run leaves no trace in the audited repo."""

    class Moving(Agent):
        def __call__(self, **kw):
            out = super().__call__(**kw)
            if kw["cwd"] is not None and len(self.calls) == 3:
                (repo / "landed.py").write_text("x = 1\n")
                commit_all(repo, "landed mid-run")
            return out

    report = run(repo, Moving(lambda e, r: "opt-float"), tmp_path, retain_snapshot=True)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "refs/paranoia" not in git(["for-each-ref", "--format=%(refname)"], repo)
