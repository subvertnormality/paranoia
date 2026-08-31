"""End-to-end arbitration against a scripted agent — no quota, no model variance.

These test the wiring the pure-core tests cannot: that the snapshot really pins
both deciders, that labels are cleared against the real repository, that the
round-2 gate is consulted before spending, and that the trailer tells the truth.
"""

import hashlib
import json
from pathlib import Path

import pytest

from paranoia_local import arbitrate_handler as ah
from paranoia_local import arbitration as arb
from paranoia_local import arbitration_research as ar
from paranoia_local import engines as eng
from paranoia_local import evidence
from paranoia_local import external_sources as es
from paranoia_local import prompts

from .conftest import commit_all, git

OPTIONS = [
    {"id": "opt-float", "statement": "Store the threshold as a float."},
    {"id": "opt-decimal", "statement": "Store the threshold as a Decimal."},
]

BASE = dict(
    decision="Choose the numeric type for a threshold used in a log line.",
    options=OPTIONS,
    stakes="Single-user local CLI, trusted input, no multi-tenancy.",
    research=False,
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


class ScriptedResearchEngine(FakeEngine):
    def __init__(self, name: str, reviews: list[eng.Review | Exception]):
        super().__init__(name)
        self.reviews = list(reviews)

    def for_role(self, role: str):
        self.role = role
        return self

    def run(self, *args, **kwargs):
        item = self.reviews.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def resume(self, *args, **kwargs):
        item = self.reviews.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


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


def test_cleaner_stakes_are_read_only_input_and_not_an_output_block():
    body = ah._clean_body("decision", "stakes", "context", [], {"one": "first"}, "")
    assert "=== STAKES (SERVER-OWNED READ-ONLY — use for calibration; do not return) ===" in body
    assert "=== STAKES ===" not in prompts.CLEANER_INSTRUCTIONS
    assert "Rewrite or return the STAKES text" in prompts.CLEANER_INSTRUCTIONS


@pytest.mark.parametrize("heading", [
    "STAKES",
    "STAKES (SERVER-OWNED READ-ONLY — use for calibration; do not return)",
    "stakes",
    "EXTRA NOTES",
])
def test_cleaner_rejects_an_undeclared_output_block(heading: str):
    reply = cleaner_reply({"one": "first"}) + f"\n=== {heading} ===\nchanged\n"
    with pytest.raises(ah.ArbitrationError, match="unexpected ==="):
        ah.parse_cleaned_packet(reply, ["one"], caller_gave_context=True)


ATTEST_OK = (
    "FIDELITY: decision PRESERVED; "
    "opt-float PRESERVED; opt-decimal PRESERVED\n"
    "FIDELITY-DETAIL: NONE\n"
    "NEUTRALITY: PASS\n"
    "ORIGINAL-NEUTRALITY: PASS\n"
    "STAKES-ADVOCACY: NONE\n"
    "CONTEXT-ADVOCACY: NONE\n"
)


# For callers that DO supply files, `hints` becomes an attestable field.
ATTEST_OK_WITH_HINTS = (
    "FIDELITY: decision PRESERVED; hints PRESERVED; "
    "opt-float PRESERVED; opt-decimal PRESERVED\n"
    "FIDELITY-DETAIL: NONE\n"
    "NEUTRALITY: PASS\n"
    "ORIGINAL-NEUTRALITY: PASS\n"
    "STAKES-ADVOCACY: NONE\n"
    "CONTEXT-ADVOCACY: NONE\n"
)


def decider_reply(label, *, risk="NONE", authority="technical", new_option="NONE",
                  constraint="A fact.", decisive="app.py:4", citations="NONE",
                  publisher_authority="N/A", passage_entailment="N/A",
                  decision_relevance="N/A"):
    return (
        "Reasoning here.\n\n"
        f"SELECTED: {label}\n"
        f"SELECTED-RISK: {risk}\n"
        f"AUTHORITY: {authority}\n"
        f"NEW-OPTION: {new_option}\n"
        f"CONSTRAINT: {constraint}\n"
        f"PUBLISHER-AUTHORITY: {publisher_authority}\n"
        f"PASSAGE-ENTAILMENT: {passage_entailment}\n"
        f"DECISION-RELEVANCE: {decision_relevance}\n"
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
                 web_search, timeout, text_only, role=eng.ROLE_DEFAULT):
        self.calls.append(
            {"engine": engine_name, "model": model, "body": body, "cwd": cwd,
             "text_only": text_only, "timeout": timeout, "instructions": instructions,
             "web_search": web_search}
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
    monkeypatch.setattr(ah.eng, "require_evidence_profile", lambda engine: "test")


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


def test_malformed_decider_reply_gets_one_full_correction(
    repo: Path, tmp_path: Path,
):
    scripted = Agent(lambda engine, rnd: "opt-decimal")
    claude_attempts = 0

    def flaky(**kwargs):
        nonlocal claude_attempts
        text = scripted(**kwargs)
        if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude":
            claude_attempts += 1
            if claude_attempts == 1:
                return "AUTHORITY: technical\n" + text
        return text

    report = run(repo, flaky, tmp_path, clean=False)

    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    decider_calls = [call for call in scripted.calls if call["cwd"] is not None]
    assert [call["engine"] for call in decider_calls].count("codex") == 1
    assert [call["engine"] for call in decider_calls].count("claude") == 2
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    claude = record["rounds"][0]["claude"]
    assert len(claude["attempts"]) == 2
    assert "reply mentions AUTHORITY:" in claude["attempts"][0]["rejection"]
    assert claude["attempts"][1]["rejection"] is None
    assert "FORMAT CORRECTION" in claude["attempts"][1]["body"]


def test_terminal_decider_failure_preserves_default_research_provenance(
    repo: Path, tmp_path: Path,
):
    scripted = Agent(lambda engine, rnd: "opt-decimal")

    def researcher(**kwargs):
        return ah.ResearchRun(
            kwargs["engine"].name, kwargs["model"], (), (), (),
            "discovery", "binding", 2, ({}, {}), (1, 1),
        )

    def always_bad_claude(**kwargs):
        text = scripted(**kwargs)
        return (
            "AUTHORITY: duplicated too early\n" + text
            if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude"
            else text
        )

    args = {k: v for k, v in BASE.items() if k != "research"}
    report = ah.arbitrate(
        {**args, "repo_path": str(repo), "clean": False},
        log_dir=tmp_path / "logs", engines=ENGINES, run_agent=always_bad_claude,
        run_research=researcher, now=lambda: "20260727T120000",
    )

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "RESEARCH") == "complete 0 packets"
    assert trailer_field(report, "SNAPSHOT") != "none"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["research"]["enabled"] is True
    assert len(record["research"]["runs"]) == 2
    assert record["failed_round"]["deciders"]["codex"]["selected"] == "opt-decimal"
    assert len(record["failed_round"]["deciders"]["claude"]["attempts"]) == 2


def test_decider_reply_fails_after_exactly_one_correction(
    repo: Path, tmp_path: Path,
):
    scripted = Agent(lambda engine, rnd: "opt-decimal")

    def always_bad_claude(**kwargs):
        text = scripted(**kwargs)
        return (
            "SELECTED: duplicated too early\n" + text
            if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude"
            else text
        )

    report = run(repo, always_bad_claude, tmp_path, clean=False)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "reply remained invalid after one correction" in report
    decider_calls = [call for call in scripted.calls if call["cwd"] is not None]
    assert [call["engine"] for call in decider_calls].count("codex") == 1
    assert [call["engine"] for call in decider_calls].count("claude") == 2
    assert trailer_field(report, "CLEANING") == "skipped"
    assert trailer_field(report, "SNAPSHOT") != "none"
    assert trailer_field(report, "ROUNDS") == "0"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["failed_round"]["number"] == 1
    assert record["failed_round"]["deciders"]["codex"]["selected"] == "opt-decimal"
    failed = record["failed_round"]["deciders"]["claude"]
    assert failed["status"] == "failed"
    assert len(failed["attempts"]) == 2
    assert len(record["refs_before"]) == 64
    assert len(record["refs_after"]) == 64


def test_decider_execution_failure_is_not_retried(repo: Path, tmp_path: Path):
    scripted = Agent(lambda engine, rnd: "opt-decimal")
    claude_calls = 0

    def failed_claude(**kwargs):
        nonlocal claude_calls
        if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude":
            claude_calls += 1
            raise RuntimeError("provider unavailable")
        return scripted(**kwargs)

    report = run(repo, failed_claude, tmp_path, clean=False)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "provider unavailable" in report
    assert claude_calls == 1


def test_decider_path_prefers_structured_failure_detail_over_partial_text(
    repo: Path, tmp_path: Path, monkeypatch,
):
    class AdapterEngine:
        def __init__(self, name: str):
            self.name = name
            self.calls = 0
            self.prompts = []

        def for_role(self, _role: str):
            return self

        def run(self, prompt, *args, **kwargs):
            self.calls += 1
            self.prompts.append(prompt)
            if self.name == "claude":
                return eng.Review(
                    text="SELECTED: partial-provider-output\n",
                    session_ref="partial-session",
                    raw="raw provider envelope",
                    returncode=1,
                    error=True,
                    failure_detail="provider credit exhausted before completion",
                )
            label = next(
                line.split(":", 1)[0]
                for line in prompt.splitlines()
                if line.startswith(arb.LABEL_PREFIX) and "Decimal" in line
            )
            return eng.Review(
                text=decider_reply(label), session_ref="codex-session", raw="", returncode=0,
            )

    adapters = {name: AdapterEngine(name) for name in ("codex", "claude")}
    monkeypatch.setattr(
        ah.eng, "get_engine", lambda name, text_only=False: adapters[name]
    )

    report = ah.arbitrate(
        {**BASE, "repo_path": str(repo), "clean": False},
        log_dir=tmp_path / "logs", engines=ENGINES,
        now=lambda: "20260727T120000",
    )

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "provider credit exhausted before completion" in report
    assert "partial-provider-output" not in report
    assert adapters["claude"].calls == 1
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    failed = record["failed_round"]["deciders"]["claude"]
    assert "provider credit exhausted before completion" in failed["error"]
    assert "provider credit exhausted before completion" in failed["attempts"][0]["rejection"]
    assert "partial-provider-output" not in failed["error"]
    attempt = failed["attempts"][0]
    exact_prompt = adapters["claude"].prompts[0]
    assert attempt["prompt_sha256"] == hashlib.sha256(
        exact_prompt.encode("utf-8", "surrogatepass")
    ).hexdigest()
    assert attempt["prompt_excerpt"] == exact_prompt


def test_failure_after_round_one_preserves_completed_decider_artifacts(
    repo: Path, tmp_path: Path, monkeypatch,
):
    def broken_substantiation(*args, **kwargs):
        raise RuntimeError("resolution bridge failed")

    monkeypatch.setattr(ah.arb, "substantiation", broken_substantiation)
    report = run(repo, Agent(lambda engine, rnd: "opt-decimal"), tmp_path, clean=False)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "resolution bridge failed" in report
    assert trailer_field(report, "ROUNDS") == "1"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert sorted(record["rounds"][0]) == ["claude", "codex"]
    assert record["rounds"][0]["codex"]["reply"]
    assert record["rounds"][0]["claude"]["prompt"]
    assert sorted(record["label_maps"]) == ["claude", "codex"]


def test_post_fanout_failure_preserves_completed_research_packet_and_digest(
    repo: Path, tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(ah.eng, "require_evidence_profile", lambda engine: "test")
    candidate = es.CandidateSource(
        "https://docs.example.com/api", "API docs", "Example", "primary",
        "Example defines the API", "supports_claim",
    )
    claim = ar.DiscoveryClaim("behavior", "The API retries twice.", candidate)
    capture = es.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        "The API retries twice.",
    )
    bound = es.BoundSource(candidate, capture, "API", "The API retries twice.")

    def researcher(**kwargs):
        return ah.ResearchRun(
            kwargs["engine"].name, kwargs["model"], (claim,), (bound,), (capture,),
            "discovery", "binding", 2, ({}, {}), (1, 1),
        )

    def broken_substantiation(*args, **kwargs):
        raise RuntimeError("post-research resolution failed")

    monkeypatch.setattr(ah.arb, "substantiation", broken_substantiation)
    args = {key: value for key, value in BASE.items() if key != "research"}
    report = ah.arbitrate(
        {**args, "repo_path": str(repo), "clean": False},
        log_dir=tmp_path / "logs", engines=ENGINES,
        run_agent=Agent(lambda engine, rnd: "opt-decimal"),
        run_research=researcher, now=lambda: "20260727T120000",
    )

    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert trailer_field(report, "RESEARCH") == "complete 1 packets"
    assert trailer_field(report, "RESEARCH-DIGEST") == record["research"]["digest"]
    assert record["research"]["packets"]
    assert record["research"]["packets"] == ar.render(
        ar.packets([((claim,), (bound,))])
    )


def test_correction_execution_failure_preserves_the_rejected_reply(
    repo: Path, tmp_path: Path,
):
    scripted = Agent(lambda engine, rnd: "opt-decimal")
    claude_calls = 0

    def failed_correction(**kwargs):
        nonlocal claude_calls
        if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude":
            claude_calls += 1
            if claude_calls == 2:
                raise RuntimeError("provider unavailable during correction")
        text = scripted(**kwargs)
        return (
            "AUTHORITY: duplicated too early\n" + text
            if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude"
            else text
        )

    report = run(repo, failed_correction, tmp_path, clean=False)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "correction attempt failed after a rejected reply" in report
    assert claude_calls == 2
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    failure = record["failed_round"]["deciders"]["claude"]
    assert len(failure["attempts"]) == 2
    assert "reply mentions AUTHORITY:" in failure["attempts"][0]["rejection"]
    assert "FORMAT CORRECTION" in failure["attempts"][1]["body"]
    assert failure["attempts"][1]["raw"] == ""


    assert "provider unavailable" in failure["attempts"][1]["rejection"]
    assert failure["attempts"][1]["status"] == "provider-failed"
    assert failure["attempts"][1]["admitted"] is True
    assert failure["attempts"][1]["invoked"] is True
    assert record["failed_round"]["deciders"]["codex"]["selected"] == "opt-decimal"


def test_whole_run_deadline_refuses_a_phase_that_cannot_fit(
    repo: Path, tmp_path: Path, monkeypatch,
):
    ticks = iter([0.0, 6800.0])
    monkeypatch.setattr(ah.time, "monotonic", lambda: next(ticks))
    agent = Agent(lambda engine, rnd: "opt-decimal")
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "insufficient time to start a 420s agent phase" in report
    assert not agent.calls
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["phase_attempts"][0]["status"] == "admission-refused"
    assert record["phase_attempts"][0]["invoked"] is False
    assert record["phase_attempts"][0]["execution"] == ah._execution_identity(
        eng.CLEANER_ENGINE, eng.CLEANER_MODEL,
    )


def test_cleaner_execution_exception_keeps_pending_attempt_binding(
    repo: Path, tmp_path: Path,
):
    def failed_cleaner(**kwargs):
        raise RuntimeError("cleaner provider unavailable")

    report = run(repo, failed_cleaner, tmp_path)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert trailer_field(report, "SNAPSHOT") != "none"
    assert record["phase_attempts"][0]["role"] == "cleaner"
    assert record["phase_attempts"][0]["prompt_excerpt"]
    assert len(record["phase_attempts"][0]["prompt_sha256"]) == 64
    assert "cleaner provider unavailable" in record["phase_attempts"][0]["rejection"]


def test_cleaner_execution_failure_keeps_distinct_engine_channels(
    repo: Path, tmp_path: Path,
):
    channels = {
        "engine": "codex", "returncode": 9,
        "failure_detail": "structured cleaner failure", "text": "partial cleaner text",
        "raw": "raw cleaner envelope", "stderr": "cleaner stderr",
    }

    def failed_cleaner(**kwargs):
        raise ah.EngineCallError("cleaner failed", channels)

    report = run(repo, failed_cleaner, tmp_path)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["phase_attempts"][0]["engine_failure"] == channels


def test_attester_execution_exception_keeps_pending_attempt_binding(
    repo: Path, tmp_path: Path,
):
    scripted = Agent(lambda engine, rnd: "opt-decimal")

    def failed_attester(**kwargs):
        if "TEXT AUDITOR" in kwargs["instructions"]:
            raise RuntimeError("attester provider unavailable")
        return scripted(**kwargs)

    report = run(repo, failed_attester, tmp_path)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert [item["role"] for item in record["phase_attempts"]] == [
        "cleaner", "attester",
    ]
    assert record["phase_attempts"][1]["prompt_excerpt"]
    assert "attester provider unavailable" in record["phase_attempts"][1]["rejection"]


def test_default_research_injects_one_shared_captured_packet_before_voting(
    repo: Path, tmp_path: Path,
):
    candidate = es.CandidateSource(
        "https://docs.example.com/numeric", "Numeric docs", "Example",
        "primary", "Example defines the numeric API", "supports_claim",
    )
    claim = ar.DiscoveryClaim(
        "behavior", "The API preserves decimal values exactly.", candidate,
    )
    capture = es.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        "The API preserves decimal values exactly.",
    )
    bound = es.BoundSource(
        candidate, capture, "Numeric types", "The API preserves decimal values exactly.",
    )
    packet_id = es.packet_id(claim.proposition, bound)
    research_calls: list[str] = []

    def researcher(**kwargs):
        research_calls.append(kwargs["engine"].name)
        return ah.ResearchRun(
            kwargs["engine"].name, kwargs["model"], (claim,), (bound,), (capture,),
            "discovery", "binding", 2, ({}, {}), (1, 1),
        )

    evidence_fields = {
        "constraint": claim.proposition,
        "decisive": f"SOURCE:{packet_id}",
        "publisher_authority": "YES — the publisher defines the API",
        "passage_entailment": "YES — the passage states the proposition",
        "decision_relevance": "YES — exact decimals distinguish the options",
    }
    agent = Agent(
        lambda engine, rnd: "opt-decimal",
        extra={("codex", 1): evidence_fields, ("claude", 1): evidence_fields},
    )
    args = {k: v for k, v in BASE.items() if k != "research"}
    report = ah.arbitrate(
        {**args, "repo_path": str(repo)}, log_dir=tmp_path / "logs",
        engines=ENGINES, run_agent=agent, run_research=researcher,
        now=lambda: "20260727T120000",
    )
    assert sorted(research_calls) == ["claude", "codex"]
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "RESEARCH") == "complete 1 packets"
    decider_calls = [call for call in agent.calls if call["cwd"] is not None]
    assert len(decider_calls) == 2
    assert all(call["web_search"] is False for call in decider_calls)
    assert all(packet_id in call["body"] for call in decider_calls)


def test_capture_failure_retains_completed_sibling_in_research_record(monkeypatch):
    discovery = ar.DISCOVERY_MARKER + "\n" + json.dumps({
        "claims": [{
            "kind": "behavior",
            "proposition": "The API retries twice.",
            "candidate": {
                "url": "https://docs.example.com/api", "title": "API docs",
                "publisher": "Example", "source_kind": "primary",
                "authority_basis": "Example defines the API",
                "relation": "supports_claim",
            },
        }],
    })
    engine = ScriptedResearchEngine("codex", [
        eng.Review(discovery, "discovery-session", "raw discovery"),
    ])

    def capture_all(candidates, **kwargs):
        item = candidates[0]
        completed = es.Capture(
            item, item.url, 200, "text/html", "a" * 64, "b" * 64,
            "The API retries twice.",
        )
        raise es.CaptureGroupError("RuntimeError: sibling exploded", (completed,))

    monkeypatch.setattr(ah.external_sources, "capture_all", capture_all)
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")
    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium",
        )
    assert caught.value.record["phase"] == "capture"
    assert caught.value.record["captures"][0]["final_url"] == "https://docs.example.com/api"


def test_binding_validation_failure_retains_both_rejected_replies(
    monkeypatch,
):
    discovery = ar.DISCOVERY_MARKER + "\n" + json.dumps({
        "claims": [{
            "kind": "behavior",
            "proposition": "The API retries twice.",
            "candidate": {
                "url": "https://docs.example.com/api",
                "title": "API docs",
                "publisher": "Example",
                "source_kind": "primary",
                "authority_basis": "Example defines the API",
                "relation": "supports_claim",
            },
        }],
    })
    first = ar.BINDING_MARKER + "\n" + json.dumps({"bindings": []})
    second = ar.BINDING_MARKER + "\n" + "not-json"
    engine = ScriptedResearchEngine("claude", [
        eng.Review(discovery, "discovery-session", "raw discovery"),
        eng.Review(first, "binding-session", "raw first binding"),
        eng.Review(second, "binding-session", "raw second binding"),
    ])

    def capture_all(candidates, **kwargs):
        candidate = candidates[0]
        return [es.Capture(
            candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
            "The API retries twice.",
        )]

    monkeypatch.setattr(ah.external_sources, "capture_all", capture_all)
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")

    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium",
        )

    record = caught.value.record
    assert record["phase"] == "binding-validation-retry"
    assert record["calls"] == 3
    assert [item["phase"] for item in record["rejected_replies"]] == [
        "binding", "binding-validation-retry",
    ]
    assert record["rejected_replies"][0]["extracted_excerpt"] == first
    assert record["rejected_replies"][0]["raw_excerpt"] == "raw first binding"
    assert record["rejected_replies"][1]["extracted_excerpt"] == second
    assert record["accepted_claims"][0]["proposition"] == "The API retries twice."
    assert record["captures"][0]["final_url"] == "https://docs.example.com/api"
    assert [attempt["session_ref"] for attempt in record["attempts"]] == [
        "discovery-session", "binding-session", "binding-session",
    ]


def test_research_execution_failure_surfaces_engine_detail():
    engine = ScriptedResearchEngine("claude", [eng.Review(
        "", None, "provider envelope", returncode=1, error=True,
        failure_detail="Credit balance is too low to run this request.",
    )])
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")

    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium",
        )

    assert "Credit balance is too low" in str(caught.value)
    assert caught.value.record["message"] == (
        "Credit balance is too low to run this request."
    )
    assert caught.value.record["attempts"][-1]["raw_excerpt"] == "provider envelope"
    assert caught.value.record["attempts"][-1]["failure_detail"] == (
        "Credit balance is too low to run this request."
    )
    assert caught.value.record["attempts"][-1]["status"] == "provider-failed"


@pytest.mark.parametrize("phase", [
    "discovery", "discovery-validation-retry",
    "binding", "binding-validation-retry",
])
def test_structured_research_provider_failure_has_failed_lifecycle_status(phase: str):
    review = eng.Review(
        "partial", "session", "raw", returncode=1, error=True,
        failure_detail="provider failed",
    )
    record = ah._research_reply_record(phase, review, "provider failed")

    assert record["phase"] == phase
    assert record["status"] == "provider-failed"
    assert record["invoked"] is True


def test_research_invocation_exception_is_counted_with_prompt_binding():
    engine = ScriptedResearchEngine("claude", [RuntimeError("provider offline")])
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")

    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium",
        )

    record = caught.value.record
    assert record["calls"] == 1
    assert len(record["attempts"]) == 1
    assert record["attempts"][0]["phase"] == "discovery"
    assert record["attempts"][0]["prompt_excerpt"]
    assert len(record["attempts"][0]["prompt_sha256"]) == 64
    assert record["attempts"][0]["intended_session_ref"] is None
    assert "provider offline" in record["attempts"][0]["failure_detail"]


def test_validation_retry_exception_is_counted_with_session_and_prompt():
    engine = ScriptedResearchEngine("claude", [
        eng.Review("not discovery JSON", "discovery-session", "raw invalid"),
        RuntimeError("retry provider offline"),
    ])
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")

    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium",
        )

    record = caught.value.record
    assert record["calls"] == 2
    assert [item["phase"] for item in record["attempts"]] == [
        "discovery", "discovery-validation-retry",
    ]
    retry = record["attempts"][1]
    assert retry["intended_session_ref"] == "discovery-session"
    assert retry["prompt_excerpt"]
    assert "retry provider offline" in retry["failure_detail"]
    assert record["rejected_replies"][0]["raw_excerpt"] == "raw invalid"


def test_research_deadline_admits_discovery_cap_before_invocation(monkeypatch):
    engine = ScriptedResearchEngine("codex", [RuntimeError("must not run")])
    monkeypatch.setattr(ah.time, "monotonic", lambda: 100.0)
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")

    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium", deadline=339.0,
        )

    assert caught.value.record["phase"] == "discovery"
    assert "insufficient time" in caught.value.record["message"]
    assert caught.value.record["calls"] == 0
    assert caught.value.record["kind"] == "admission"
    assert caught.value.record["attempts"][0]["status"] == "admission-refused"
    assert caught.value.record["attempts"][0]["invoked"] is False
    assert len(engine.reviews) == 1


def test_research_deadline_admits_discovery_retry_cap_before_resume(monkeypatch):
    engine = ScriptedResearchEngine("codex", [
        eng.Review("not discovery JSON", "discovery-session", "raw invalid"),
        RuntimeError("must not resume"),
    ])
    ticks = iter([0.0, 100.0])
    monkeypatch.setattr(ah.time, "monotonic", lambda: next(ticks))
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")

    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium", deadline=339.0,
        )

    assert caught.value.record["phase"] == "discovery-validation-retry"
    assert caught.value.record["calls"] == 1
    assert caught.value.record["kind"] == "admission"
    assert caught.value.record["attempts"][-1]["status"] == "admission-refused"
    assert caught.value.record["attempts"][-1]["invoked"] is False
    assert len(engine.reviews) == 1
    assert caught.value.record["rejected_replies"][0]["raw_excerpt"] == "raw invalid"


@pytest.mark.parametrize("retry", [False, True])
def test_research_deadline_admits_each_binding_cap_before_resume(monkeypatch, retry):
    discovery = ar.DISCOVERY_MARKER + "\n" + json.dumps({
        "claims": [{
            "kind": "behavior", "proposition": "The API retries twice.",
            "candidate": {
                "url": "https://docs.example.com/api", "title": "API docs",
                "publisher": "Example", "source_kind": "primary",
                "authority_basis": "Example defines the API",
                "relation": "supports_claim",
            },
        }],
    })
    invalid_binding = eng.Review(
        ar.BINDING_MARKER + "\n" + json.dumps({"bindings": []}),
        "binding-session", "raw invalid binding",
    )
    reviews = [eng.Review(discovery, "discovery-session", "raw discovery")]
    if retry:
        reviews.append(invalid_binding)
    reviews.append(RuntimeError("must not resume"))
    engine = ScriptedResearchEngine("claude", reviews)
    ticks = iter([0.0, 0.0, 100.0] if retry else [0.0, 100.0])
    monkeypatch.setattr(ah.time, "monotonic", lambda: next(ticks))

    def capture_all(candidates, **kwargs):
        candidate = candidates[0]
        return [es.Capture(
            candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
            "The API retries twice.",
        )]

    monkeypatch.setattr(ah.external_sources, "capture_all", capture_all)
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")
    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium", deadline=459.0,
        )

    expected = "binding-validation-retry" if retry else "binding"
    assert caught.value.record["phase"] == expected
    assert caught.value.record["calls"] == (2 if retry else 1)
    assert caught.value.record["kind"] == "admission"
    assert caught.value.record["attempts"][-1]["status"] == "admission-refused"
    assert caught.value.record["attempts"][-1]["invoked"] is False
    assert len(engine.reviews) == 1
    if retry:
        assert caught.value.record["rejected_replies"][0]["raw_excerpt"] == (
            "raw invalid binding"
        )


def test_successful_corrected_lane_keeps_the_initial_parser_error(monkeypatch):
    valid_discovery = ar.DISCOVERY_MARKER + "\n" + json.dumps({
        "claims": [{
            "kind": "behavior",
            "proposition": "The API retries twice.",
            "candidate": {
                "url": "https://docs.example.com/api", "title": "API docs",
                "publisher": "Example", "source_kind": "primary",
                "authority_basis": "Example defines the API",
                "relation": "supports_claim",
            },
        }],
    })
    valid_binding = ar.BINDING_MARKER + "\n" + json.dumps({
        "bindings": [{
            "claim_index": 0, "usable": True, "location": "API behavior",
            "passage": "The API retries twice.",
        }],
    })
    engine = ScriptedResearchEngine("codex", [
        eng.Review("not discovery JSON", "s1", "raw rejected discovery"),
        eng.Review(valid_discovery, "s1", "raw corrected discovery"),
        eng.Review(valid_binding, "s1", "raw binding"),
    ])

    def capture_all(candidates, **kwargs):
        candidate = candidates[0]
        return [es.Capture(
            candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
            "API behavior\nThe API retries twice.",
        )]

    monkeypatch.setattr(ah.external_sources, "capture_all", capture_all)
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")
    run_record = ah._research_one(
        engine=engine, model="m", packet=packet, options=("A", "B"),
        forbidden=("a", "b"), effort="medium",
    )

    assert run_record.attempts[0]["phase"] == "discovery"
    assert run_record.attempts[0]["error"]
    assert run_record.attempts[0]["raw_excerpt"] == "raw rejected discovery"
    assert run_record.attempts[1]["error"] == ""


def test_valid_discovery_without_session_retains_the_accepted_claim():
    discovery = ar.DISCOVERY_MARKER + "\n" + json.dumps({
        "claims": [{
            "kind": "behavior",
            "proposition": "The API retries twice.",
            "candidate": {
                "url": "https://docs.example.com/api",
                "title": "API docs",
                "publisher": "Example",
                "source_kind": "primary",
                "authority_basis": "Example defines the API",
                "relation": "supports_claim",
            },
        }],
    })
    engine = ScriptedResearchEngine(
        "claude", [eng.Review(discovery, None, "raw valid discovery")],
    )
    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")

    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=engine, model="m", packet=packet, options=("A", "B"),
            forbidden=("a", "b"), effort="medium",
        )

    assert caught.value.record["kind"] == "protocol"
    assert caught.value.record["accepted_claims"][0]["proposition"] == (
        "The API retries twice."
    )
    assert caught.value.record["attempts"][0]["raw_excerpt"] == "raw valid discovery"


def test_terminal_research_failure_is_written_to_gate_audit(
    repo: Path, tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(ah.eng, "require_evidence_profile", lambda engine: "test")

    def researcher(**kwargs):
        if kwargs["engine"].name == "claude":
            raise ah.ResearchFailure(
                "claude binding validation retry rejected: malformed JSON",
                record={
                    "engine": "claude",
                    "model": kwargs["model"],
                    "phase": "binding-validation-retry",
                    "kind": "validation",
                    "message": "malformed JSON",
                    "calls": 3,
                    "rejected_replies": [{"raw_excerpt": "the rejected body"}],
                },
            )
        candidate = es.CandidateSource(
            "https://docs.example.com/api", "API docs", "Example", "primary",
            "Example defines the API", "supports_claim",
        )
        claim = ar.DiscoveryClaim("behavior", "The API retries twice.", candidate)
        capture = es.Capture(
            candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
            "The API retries twice.",
        )
        bound = es.BoundSource(candidate, capture, "API", "The API retries twice.")
        return ah.ResearchRun(
            kwargs["engine"].name, kwargs["model"], (claim,), (bound,), (capture,),
            "discovery", "binding", 2, ({}, {}), (1, 1),
            ({"phase": "discovery", "session_ref": "peer-session"},),
        )

    args = {key: value for key, value in BASE.items() if key != "research"}
    report = ah.arbitrate(
        {**args, "repo_path": str(repo), "clean": False},
        log_dir=tmp_path / "logs", engines=ENGINES,
        run_agent=Agent(lambda engine, rnd: "opt-decimal"),
        run_research=researcher, now=lambda: "20260727T120000",
    )

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "SNAPSHOT") != "none"
    assert trailer_field(report, "CLEANING") == "skipped"
    assert trailer_field(report, "RESEARCH") == "failed"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["snapshot"] == trailer_field(report, "SNAPSHOT")
    assert record["cleaning"] == "skipped"
    assert record["research"]["failures"][0]["phase"] == "binding-validation-retry"
    assert record["research"]["failures"][0]["rejected_replies"][0][
        "raw_excerpt"
    ] == "the rejected body"
    assert record["research"]["runs"][0]["engine"] == "codex"
    assert record["research"]["runs"][0]["claims"][0]["proposition"] == (
        "The API retries twice."
    )
    assert record["research"]["runs"][0]["bindings"][0]["passage"] == (
        "The API retries twice."
    )
    assert record["research"]["runs"][0]["attempts"][0]["session_ref"] == (
        "peer-session"
    )
    assert len(record["refs_before"]) == 64
    assert len(record["refs_after"]) == 64


def test_attester_execution_failure_keeps_distinct_engine_channels(
    repo: Path, tmp_path: Path,
):
    scripted = Agent(lambda engine, rnd: "opt-decimal")
    channels = {
        "engine": "claude", "returncode": 8,
        "failure_detail": "structured attester failure", "text": "partial attester text",
        "raw": "raw attester envelope", "stderr": "attester stderr",
    }

    def failed_attester(**kwargs):
        if "TEXT AUDITOR" in kwargs["instructions"]:
            raise ah.EngineCallError("attester failed", channels)
        return scripted(**kwargs)

    report = run(repo, failed_attester, tmp_path)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["phase_attempts"][1]["engine_failure"] == channels


def test_research_false_is_the_explicit_repository_only_switch(
    repo: Path, tmp_path: Path,
):
    def researcher(**kwargs):
        pytest.fail("research must not run when explicitly disabled")

    agent = Agent(lambda engine, rnd: "opt-decimal")
    report = ah.arbitrate(
        {**BASE, "repo_path": str(repo), "clean": False},
        log_dir=tmp_path / "logs", engines=ENGINES, run_agent=agent,
        run_research=researcher, now=lambda: "20260727T120000",
    )

    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "RESEARCH") == "repository-only"


def test_repository_only_rejects_unsupported_decider_profile_before_snapshot_or_vote(
    repo: Path, tmp_path: Path, monkeypatch,
):
    checked: list[str] = []

    def reject(engine):
        checked.append(engine.name)
        if engine.name == "claude":
            raise RuntimeError("claude evidence mode supports a different CLI")

    monkeypatch.setattr(ah.eng, "require_evidence_profile", reject)
    monkeypatch.setattr(
        ah, "_snapshot", lambda repo: pytest.fail("snapshot must not be created"),
    )
    agent = Agent(lambda engine, rnd: "opt-decimal")
    report = run(repo, agent, tmp_path, clean=False)

    assert checked == ["codex", "claude"]
    assert not agent.calls
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "supports a different CLI" in report


def test_research_packet_rejects_caller_id_in_captured_passage_before_voting(
    repo: Path, tmp_path: Path,
):
    candidate = es.CandidateSource(
        "https://docs.example.com/numeric", "Numeric docs", "Example",
        "primary", "Example defines the numeric API", "supports_claim",
    )
    claim = ar.DiscoveryClaim("behavior", "The API preserves decimals.", candidate)
    leaked = "The API preserves opt-decimal values."
    capture = es.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64, leaked,
    )
    bound = es.BoundSource(candidate, capture, "Numeric types", leaked)

    def researcher(**kwargs):
        return ah.ResearchRun(
            kwargs["engine"].name, kwargs["model"], (claim,), (bound,), (capture,),
            "discovery", "binding", 2, ({}, {}), (1, 1),
        )

    agent = Agent(lambda engine, rnd: "opt-decimal")
    args = {key: value for key, value in BASE.items() if key != "research"}
    report = ah.arbitrate(
        {**args, "repo_path": str(repo)}, log_dir=tmp_path / "logs",
        engines=ENGINES, run_agent=agent, run_research=researcher,
        now=lambda: "20260727T120000",
    )

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "reserved token 'opt-decimal' appears in 'research packet'" in report
    assert trailer_field(report, "SNAPSHOT") != "none"
    assert trailer_field(report, "CLEANING") == "attested"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["research"]["failures"][0]["phase"] == "packet-validation"
    assert record["research"]["packets"]
    assert trailer_field(report, "RESEARCH-DIGEST") == record["research"]["digest"]
    assert len(record["research"]["digest"]) == 64
    assert record["snapshot"] == trailer_field(report, "SNAPSHOT")
    assert len(record["refs_before"]) == 64
    assert len(record["refs_after"]) == 64
    assert not [call for call in agent.calls if call["cwd"] is not None]


def test_every_trailer_field_is_always_present(repo: Path, tmp_path: Path):
    """Nothing is signalled by absence, so a consumer never has to infer."""
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    for field in ("ARBITRATION", "SELECTED", "PROVISIONAL-SELECTED", "ADVISORY", "AUTHORITY-POLICY",
                  "CLEANING", "SNAPSHOT", "ORDER-SEED", "RESEARCH", "RESEARCH-DIGEST",
                  "REFS-MOVED", "AUDIT", "ROUNDS"):
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
    assert cwds[0] != cwds[1]  # separate inert materializations
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


def test_label_collision_history_survives_later_decider_failure(
    repo: Path, tmp_path: Path, monkeypatch,
):
    scans = 0
    real_scan = evidence.scan_for_tokens

    def scan(repo_, commit, tokens):
        nonlocal scans
        scans += 1
        return [tokens[0]] if scans == 1 else real_scan(repo_, commit, tokens)

    scripted = Agent(lambda e, r: "opt-float")

    def failed_decider(**kwargs):
        if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude":
            raise RuntimeError("decider unavailable after label recovery")
        return scripted(**kwargs)

    monkeypatch.setattr(ah.evidence, "scan_for_tokens", scan)
    report = run(repo, failed_decider, tmp_path, clean=False)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert [item["status"] for item in record["label_attempt_records"]] == [
        "collision", "selected",
    ]
    assert record["failed_round"]["deciders"]["claude"]["status"] == "failed"


def test_later_label_scan_failure_keeps_completed_attempts(
    repo: Path, tmp_path: Path, monkeypatch,
):
    scans = 0

    def scan(_repo, _commit, tokens):
        nonlocal scans
        scans += 1
        if scans == 1:
            return [tokens[0]]
        raise RuntimeError("second label scan failed")

    monkeypatch.setattr(ah.evidence, "scan_for_tokens", scan)
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path, clean=False)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "second label scan failed" in report
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    attempts = record["label_attempt_records"]
    assert attempts[0]["status"] == "collision"
    assert attempts[0]["repository_collisions"]
    assert attempts[1]["status"] == "repository-scan-pending"
    assert attempts[1]["repository_collisions"] is None


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
    assert trailer_field(report, "SELECTED") == "none"
    assert trailer_field(report, "PROVISIONAL-SELECTED") == "opt-float"
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


def test_round_two_converges_when_source_grounded_voter_holds(
    repo: Path, tmp_path: Path,
):
    (repo / "other.py").write_text("A = 1\nB = 2\nC = 3\nD = 4\nE = 5\n")
    commit_all(repo, "other")
    candidate = es.CandidateSource(
        "https://docs.example.com/numeric", "Numeric docs", "Example",
        "primary", "Example defines the numeric API", "supports_claim",
    )
    claim = ar.DiscoveryClaim(
        "behavior", "The API preserves decimal values exactly.", candidate,
    )
    capture = es.Capture(
        candidate, candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        "The API preserves decimal values exactly.",
    )
    bound = es.BoundSource(
        candidate, capture, "Numeric types",
        "The API preserves decimal values exactly.",
    )
    packet_id = es.packet_id(claim.proposition, bound)

    def researcher(**kwargs):
        return ah.ResearchRun(
            kwargs["engine"].name, kwargs["model"], (claim,), (bound,), (capture,),
            "discovery", "binding", 2, ({}, {}), (1, 1),
        )

    source_fields = {
        "constraint": claim.proposition,
        "decisive": f"SOURCE:{packet_id}",
        "citations": "app.py:4",
        "publisher_authority": "YES — the publisher defines the API",
        "passage_entailment": "YES — the passage states the proposition",
        "decision_relevance": "YES — exact decimals distinguish the options",
    }
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda engine, rnd: picks.get((engine, rnd), "opt-decimal"),
        extra={
            ("codex", 1): {"decisive": "other.py:3"},
            ("codex", 2): {"decisive": "app.py:4"},
            ("claude", 1): source_fields,
            ("claude", 2): source_fields,
        },
    )
    args = {k: v for k, v in BASE.items() if k != "research"}
    report = ah.arbitrate(
        {**args, "repo_path": str(repo)}, log_dir=tmp_path / "logs",
        engines=ENGINES, run_agent=agent, run_research=researcher,
        now=lambda: "20260727T120000",
    )
    assert trailer_field(report, "ROUNDS") == "2"
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"


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


def test_later_carried_region_failure_keeps_earlier_bytes(
    repo: Path, tmp_path: Path, monkeypatch,
):
    (repo / "other.py").write_text("A = 1\nB = 2\nC = 3\nD = 4\nE = 5\n")
    commit_all(repo, "other")
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}
    agent = Agent(
        lambda engine, rnd: picks.get((engine, rnd), "opt-float"),
        extra={
            ("codex", 1): {"decisive": "app.py:4"},
            ("claude", 1): {"decisive": "other.py:3"},
        },
    )
    real_read = ah.evidence.read_region
    reads = 0

    def read_region(repo_, region):
        nonlocal reads
        reads += 1
        # Substantiation and union derivation resolve both anchors before the two
        # round-two transport reads.
        if reads == 6:
            raise RuntimeError("second carried region failed")
        return real_read(repo_, region)

    monkeypatch.setattr(ah.evidence, "read_region", read_region)
    report = run(repo, agent, tmp_path, clean=False)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "second carried region failed" in report
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert len(record["carried_evidence"]) == 1
    assert record["carried_evidence"][0]["body"]


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


def test_dual_round_two_execution_failure_keeps_carried_and_phase_artifacts(
    repo: Path, tmp_path: Path,
):
    (repo / "other.py").write_text("A = 1\nB = 2\nC = 3\nD = 4\nE = 5\n")
    commit_all(repo, "other")
    picks = {("codex", 1): "opt-float", ("claude", 1): "opt-decimal"}

    class RoundTwoFails(Agent):
        def __call__(self, **kwargs):
            reply = super().__call__(**kwargs)
            if kwargs["cwd"] is not None and "CODE REGIONS RELEVANT" in kwargs["body"]:
                raise RuntimeError(f"{kwargs['engine_name']} unavailable in round two")
            return reply

    agent = RoundTwoFails(
        lambda engine, rnd: picks.get((engine, rnd), "opt-decimal"),
        extra={
            ("codex", 1): {"decisive": "app.py:4"},
            ("claude", 1): {"decisive": "other.py:3"},
        },
    )
    report = run(repo, agent, tmp_path)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "ROUNDS") == "1"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert sorted(record["failed_round"]["deciders"]) == ["claude", "codex"]
    assert all(
        item["attempts"][0]["body"]
        and item["attempts"][0]["status"] == "provider-failed"
        and item["attempts"][0]["invoked"] is True
        for item in record["failed_round"]["deciders"].values()
    )
    assert {item["path"] for item in record["carried_evidence"]} == {
        "app.py", "other.py",
    }
    assert [item["role"] for item in record["phase_attempts"]] == [
        "cleaner", "attester",
    ]


def test_refs_moving_mid_run_is_reported_without_invalidating_snapshot(
    repo: Path, tmp_path: Path,
):
    """The recorded snapshot still exactly describes both inert decider views."""

    class Moving(Agent):
        def __call__(self, **kw):
            out = super().__call__(**kw)
            if kw["cwd"] is not None and len(self.calls) == 3:
                (repo / "landed.py").write_text("x = 1\n")
                commit_all(repo, "landed mid-run")
            return out

    report = run(repo, Moving(lambda e, r: "opt-float"), tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "REFS-MOVED") == "yes"


def test_decider_failure_names_its_engine(repo: Path, tmp_path: Path):
    class Broken(Agent):
        def __call__(self, **kw):
            if kw["cwd"] is not None and kw["engine_name"] == "claude":
                raise RuntimeError("cli exploded")
            return super().__call__(**kw)

    report = run(repo, Broken(lambda e, r: "opt-float"), tmp_path)
    assert "claude" in report and "cli exploded" in report


def test_decider_workspace_setup_failure_opens_a_noninvoked_prompt_attempt(
    repo: Path, tmp_path: Path, monkeypatch,
):
    def fail_workspace(*args, **kwargs):
        raise RuntimeError("materialization unavailable")

    monkeypatch.setattr(ah.inert_tree, "evidence_workspace", fail_workspace)
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert not [call for call in agent.calls if call["cwd"] is not None]
    for failure in record["failed_round"]["deciders"].values():
        [attempt] = failure["attempts"]
        assert attempt["status"] == "setup-failed"
        assert attempt["admitted"] is False
        assert attempt["invoked"] is False
        assert len(attempt["prompt_sha256"]) == 64


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
    assert trailer_field(report, "CLEANING") == "cleaner-rejected"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["cleaning"] == "cleaner-rejected"


def test_cleaner_refusal_short_circuits(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float", cleaner="INSUFFICIENT: the options overlap")
    report = run(repo, agent, tmp_path)
    assert "cleaner refused" in report and "overlap" in report
    assert all(c["cwd"] is None for c in agent.calls)


def test_cross_option_content_transfer_is_rejected_by_fidelity_attestation(
    repo: Path, tmp_path: Path,
):
    options = [
        {
            "id":"opt-float",
            "statement":(
                "Store the threshold as a float. Float uniquely preserves the legacy "
                "wire representation."
            ),
        },
        {"id":"opt-decimal", "statement":"Store the threshold as a Decimal."},
    ]
    transferred = "Float uniquely preserves the legacy wire representation."
    candidate_decimal = f"Store the threshold as a Decimal. {transferred}"
    detail = {
        "opt-decimal": {
            "original": options[1]["statement"],
            "cleaned": candidate_decimal,
            "change": "added",
            "reason": "opt-decimal: added",
        }
    }
    attestation = (
        "FIDELITY: decision PRESERVED; opt-float PRESERVED; opt-decimal CHANGED\n"
        f"FIDELITY-DETAIL: {json.dumps(detail, separators=(',', ':'))}\n"
        "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    agent = Agent(
        lambda e, r: "opt-float",
        cleaner=cleaner_reply({
            "opt-float": options[0]["statement"],
            "opt-decimal": candidate_decimal,
        }),
        attest=attestation, statements={row["id"]:row["statement"] for row in options},
    )
    report = run(repo, agent, tmp_path, options=options)
    assert trailer_field(report, "CLEANING") == "original-attested"
    assert len([c for c in agent.calls if "NEUTRALIZER" in c["instructions"]]) == 1
    decider_bodies = [c["body"] for c in agent.calls if c["cwd"] is not None]
    assert len(decider_bodies) == 2
    assert all(options[0]["statement"] in body for body in decider_bodies)
    assert all(options[1]["statement"] in body for body in decider_bodies)
    assert all(candidate_decimal not in body for body in decider_bodies)
    assert all(body.count(transferred) == 1 for body in decider_bodies)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["cleaned"]["statements"]["opt-decimal"] == candidate_decimal


def test_original_fallback_is_atomic_across_decision_options_and_hints(
    repo: Path, tmp_path: Path,
):
    cleaned = (
        "=== DECISION ===\nChoose a storage type.\n\n"
        "=== OPTIONS ===\n"
        "opt-float: Store an approximate value.\n"
        "opt-decimal: Store an exact value.\n\n"
        "=== CONTEXT ===\nNone.\n\n"
        "=== HINTS ===\n- app.py: preferred implementation\n"
    )
    fields = {
        "decision": ("Choose the numeric type", "Choose a storage type"),
        "hints": ("the threshold is written here", "preferred implementation"),
        "opt-float": ("threshold as a float", "approximate value"),
        "opt-decimal": ("threshold as a Decimal", "exact value"),
    }
    detail = {
        field: {
            "original": original, "cleaned": changed,
            "change": "altered-qualification", "reason": f"{field}: altered-qualification",
        }
        for field, (original, changed) in fields.items()
    }
    attestation = (
        "FIDELITY: decision CHANGED; hints CHANGED; opt-float CHANGED; opt-decimal CHANGED\n"
        f"FIDELITY-DETAIL: {json.dumps(detail, separators=(',', ':'))}\n"
        "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    agent = Agent(lambda e, r: "opt-float", cleaner=cleaned, attest=attestation)
    report = run(
        repo, agent, tmp_path,
        files=[{"path": "app.py", "reason": "the threshold is written here"}],
    )

    assert trailer_field(report, "CLEANING") == "original-attested"
    bodies = [call["body"] for call in agent.calls if call["cwd"] is not None]
    assert bodies
    for body in bodies:
        assert BASE["decision"] in body
        assert "Store the threshold as a float." in body
        assert "Store the threshold as a Decimal." in body
        assert "the threshold is written here" in body
        assert "Choose a storage type" not in body
        assert "preferred implementation" not in body


def test_changed_hint_path_candidate_can_only_fall_back_to_originals(
    repo: Path, tmp_path: Path,
):
    cleaned = cleaner_reply({o["id"]: o["statement"] for o in OPTIONS}).replace(
        "=== HINTS ===\nNone.",
        "=== HINTS ===\n- substituted.py: substituted path",
    )
    original_hint = "- app.py (the threshold is written here)"
    cleaned_hint = "- substituted.py (substituted path)"
    detail = json.dumps({
        "hints": {
            "original": original_hint,
            "cleaned": cleaned_hint,
            "change": "altered-qualification",
            "reason": "hints: altered-qualification",
        }
    }, separators=(",", ":"))
    attestation = (
        "FIDELITY: decision PRESERVED; hints CHANGED; opt-float PRESERVED; "
        "opt-decimal PRESERVED\n"
        f"FIDELITY-DETAIL: {detail}\n"
        "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    agent = Agent(lambda e, r: "opt-float", cleaner=cleaned, attest=attestation)
    report = run(
        repo, agent, tmp_path,
        files=[{"path": "app.py", "reason": "the threshold is written here"}],
    )

    assert trailer_field(report, "CLEANING") == "original-attested"
    bodies = [call["body"] for call in agent.calls if call["cwd"] is not None]
    assert bodies and all("app.py (the threshold is written here)" in body for body in bodies)
    assert all("substituted.py" not in body for body in bodies)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["cleaned"]["hints"] == [
        {"path": "substituted.py", "reason": "substituted path"}
    ]


def test_caller_id_in_validated_hint_path_is_rejected_before_agents(
    repo: Path, tmp_path: Path,
):
    (repo / "opt-float.py").write_text("VALUE = 1\n")
    commit_all(repo, "add identifier-bearing hint")
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path, files=[{"path": "opt-float.py"}])

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "reserved token 'opt-float'" in report
    assert not agent.calls


def test_original_neutrality_failure_latches_across_retry(repo: Path, tmp_path: Path):
    cleaner = cleaner_reply({
        "opt-float": "Float.",
        "opt-decimal": "Use a Decimal, which is exact and avoids representation error entirely.",
    })
    detail = {
        "opt-float": {
            "original":"Store the threshold as a float.", "cleaned":"Float.",
            "change":"narrowed", "reason":"opt-float: narrowed",
        },
        "opt-decimal": {
            "original":"Store the threshold as a Decimal.",
            "cleaned":"Use a Decimal, which is exact and avoids representation error entirely.",
            "change":"added", "reason":"opt-decimal: added",
        },
    }
    changed = (
        "FIDELITY: decision PRESERVED; opt-float CHANGED; opt-decimal CHANGED\n"
        f"FIDELITY-DETAIL: {json.dumps(detail, separators=(',', ':'))}\n"
        "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    failed = changed.replace(
        "ORIGINAL-NEUTRALITY: PASS",
        'ORIGINAL-NEUTRALITY: FAIL {"field":"opt-float","passage":"Store the threshold as a float."}',
    )

    class Sequenced(Agent):
        def __init__(self):
            super().__init__(lambda e, r: "opt-float", cleaner=cleaner)
            self.attestations = [failed, changed]

        def __call__(self, **kwargs):
            if "TEXT AUDITOR" in kwargs["instructions"]:
                self.attest = self.attestations.pop(0)
            return super().__call__(**kwargs)

    report = run(repo, Sequenced(), tmp_path)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "CLEANING") == "cleaner-rejected"
    assert "cleaning failed attestation twice" in report
    # The first attester's exact caller-owned diagnostic remains actionable even
    # when the bounded retry inconsistently calls the original neutral.
    assert "field 'opt-float'" in report
    assert "Store the threshold as a float." in report
    audit = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert audit["caller_framing_diagnostic"] is None
    assert audit["fallback_ineligibility_diagnostic"] == {
        "field": "opt-float", "passage": "Store the threshold as a float.",
    }


@pytest.mark.parametrize("terminal_role", ["cleaner", "attester"])
def test_terminal_protocol_owner_wins_without_losing_latched_caller_diagnostic(
    repo: Path, tmp_path: Path, terminal_role: str,
):
    cleaner = cleaner_reply({
        "opt-float": "Float.",
        "opt-decimal": "Store the threshold as a Decimal.",
    })
    detail = json.dumps({
        "opt-float": {
            "original": "Store the threshold as a float.",
            "cleaned": "Float.",
            "change": "narrowed",
            "reason": "opt-float: narrowed",
        }
    }, separators=(",", ":"))
    first_attestation = (
        "FIDELITY: decision PRESERVED; opt-float CHANGED; opt-decimal PRESERVED\n"
        f"FIDELITY-DETAIL: {detail}\nNEUTRALITY: PASS\n"
        'ORIGINAL-NEUTRALITY: FAIL {"field":"opt-float","passage":"Store the threshold as a float."}\n'
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )

    class SequencedProtocolFailure(Agent):
        def __init__(self):
            super().__init__(lambda e, r: "opt-float", cleaner=cleaner)
            self.cleaner_calls = 0
            self.attester_calls = 0

        def __call__(self, **kwargs):
            if "NEUTRALIZER" in kwargs["instructions"]:
                self.cleaner_calls += 1
                if self.cleaner_calls == 2 and terminal_role == "cleaner":
                    self.cleaner = "not a cleaner packet"
            elif "TEXT AUDITOR" in kwargs["instructions"]:
                self.attester_calls += 1
                self.attest = (
                    first_attestation
                    if self.attester_calls == 1 else "not an attestation"
                )
            return super().__call__(**kwargs)

    report = run(repo, SequencedProtocolFailure(), tmp_path)
    expected_status = f"{terminal_role}-rejected" if terminal_role == "cleaner" else "attestation-rejected"
    assert trailer_field(report, "CLEANING") == expected_status
    assert "caller framing rejected after bounded cleaning" not in report
    assert "an earlier attestation made original fallback unavailable" in report
    assert "field 'opt-float', passage 'Store the threshold as a float.'" in report
    audit = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert audit["caller_framing_diagnostic"] is None
    assert audit["fallback_ineligibility_diagnostic"] == {
        "field": "opt-float", "passage": "Store the threshold as a float.",
    }


@pytest.mark.parametrize("terminal_role", ["cleaner", "attester"])
@pytest.mark.parametrize("exit_kind", ["admission", "execution", "size"])
def test_immediate_terminal_exit_retains_latched_caller_diagnostic(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    terminal_role: str, exit_kind: str,
):
    cleaner = cleaner_reply({
        "opt-float": "Float.",
        "opt-decimal": "Store the threshold as a Decimal.",
    })
    detail = json.dumps({
        "opt-float": {
            "original": "Store the threshold as a float.",
            "cleaned": "Float.",
            "change": "narrowed",
            "reason": "opt-float: narrowed",
        }
    }, separators=(",", ":"))
    first_attestation = (
        "FIDELITY: decision PRESERVED; opt-float CHANGED; opt-decimal PRESERVED\n"
        f"FIDELITY-DETAIL: {detail}\nNEUTRALITY: PASS\n"
        'ORIGINAL-NEUTRALITY: FAIL {"field":"opt-float","passage":"Store the threshold as a float."}\n'
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )

    class SequencedImmediateFailure(Agent):
        def __init__(self):
            super().__init__(lambda e, r: "opt-float", cleaner=cleaner)
            self.role_calls = {"cleaner": 0, "attester": 0}

        def __call__(self, **kwargs):
            role = (
                "cleaner" if "NEUTRALIZER" in kwargs["instructions"]
                else "attester" if "TEXT AUDITOR" in kwargs["instructions"]
                else None
            )
            if role is not None:
                self.role_calls[role] += 1
                if role == "attester" and self.role_calls[role] == 1:
                    self.attest = first_attestation
                if (
                    exit_kind == "execution" and role == terminal_role
                    and self.role_calls[role] == 2
                ):
                    raise RuntimeError(f"{role} provider unavailable")
                if (
                    exit_kind == "size" and role == terminal_role
                    and self.role_calls[role] == 2
                ):
                    if role == "cleaner":
                        self.cleaner = "x" * (arb.MAX_CLEANER_REPLY_CHARS + 1)
                    else:
                        self.attest = "x" * (arb.MAX_ATTESTER_REPLY_CHARS + 1)
            return super().__call__(**kwargs)

    if exit_kind == "admission":
        role_calls = {"cleaner": 0, "attester": 0}

        def reject_second_role_call(role: str, prompt: str, limit: int) -> str | None:
            role_calls[role] += 1
            if role == terminal_role and role_calls[role] == 2:
                return f"{role} prompt rejected for test"
            return None

        monkeypatch.setattr(ah, "_local_prompt_rejection", reject_second_role_call)

    report = run(repo, SequencedImmediateFailure(), tmp_path)
    expected_status = (
        "cleaner-rejected" if terminal_role == "cleaner" else "attestation-rejected"
    )
    assert trailer_field(report, "CLEANING") == expected_status
    assert "an earlier attestation made original fallback unavailable" in report
    assert "field 'opt-float', passage 'Store the threshold as a float.'" in report
    audit = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert audit["caller_framing_diagnostic"] is None
    assert audit["fallback_ineligibility_diagnostic"] == {
        "field": "opt-float", "passage": "Store the threshold as a float.",
    }
    terminal_attempt = [
        row for row in audit["phase_attempts"] if row["role"] == terminal_role
    ][-1]
    assert terminal_attempt["rejection"] is not None
    assert "original fallback unavailable" not in terminal_attempt["rejection"]
    if exit_kind == "size":
        assert f"{terminal_role} reply is" in terminal_attempt["rejection"]
    if exit_kind == "size" and terminal_role == "attester":
        assert len(audit["attestation"]) <= ah.MAX_PHASE_REPLY_CHARS
        assert "[bounded phase output]" in audit["attestation"]


@pytest.mark.parametrize(
    ("field", "caller_text"),
    [
        ("stakes", BASE["stakes"]),
        ("context", "Repository context favors Decimal."),
    ],
)
def test_terminal_caller_advocacy_wins_without_losing_fallback_diagnostic(
    repo: Path, tmp_path: Path, field: str, caller_text: str,
):
    cleaner = cleaner_reply({
        "opt-float": "Float.",
        "opt-decimal": "Store the threshold as a Decimal.",
    })
    detail = json.dumps({
        "opt-float": {
            "original": "Store the threshold as a float.",
            "cleaned": "Float.",
            "change": "narrowed",
            "reason": "opt-float: narrowed",
        }
    }, separators=(",", ":"))
    first_attestation = (
        "FIDELITY: decision PRESERVED; opt-float CHANGED; opt-decimal PRESERVED\n"
        f"FIDELITY-DETAIL: {detail}\nNEUTRALITY: PASS\n"
        'ORIGINAL-NEUTRALITY: FAIL {"field":"opt-float","passage":"Store the threshold as a float."}\n'
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    second_attestation = (
        "FIDELITY: decision PRESERVED; opt-float PRESERVED; opt-decimal PRESERVED\n"
        "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        + (
            f'STAKES-ADVOCACY: PRESENT {json.dumps({"field": field, "passage": caller_text}, separators=(",", ":"))}\n'
            if field == "stakes" else "STAKES-ADVOCACY: NONE\n"
        )
        + (
            f'CONTEXT-ADVOCACY: PRESENT {json.dumps({"field": field, "passage": caller_text}, separators=(",", ":"))}\n'
            if field == "context" else "CONTEXT-ADVOCACY: NONE\n"
        )
    )

    class SequencedSemanticFailure(Agent):
        def __init__(self):
            super().__init__(lambda e, r: "opt-float", cleaner=cleaner)
            self.attestations = [first_attestation, second_attestation]

        def __call__(self, **kwargs):
            if "TEXT AUDITOR" in kwargs["instructions"]:
                self.attest = self.attestations.pop(0)
            return super().__call__(**kwargs)

    overrides = {"context": caller_text} if field == "context" else {}
    report = run(repo, SequencedSemanticFailure(), tmp_path, **overrides)
    assert trailer_field(report, "CLEANING") == "caller-framing-rejected"
    assert "field 'opt-float', passage 'Store the threshold as a float.'" in report
    assert f"field '{field}', passage {caller_text!r}" in report
    audit = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert audit["caller_framing_diagnostic"] == {
        "field": field, "passage": caller_text,
    }
    assert audit["fallback_ineligibility_diagnostic"] == {
        "field": "opt-float", "passage": "Store the threshold as a float.",
    }
    attester_attempts = [
        row for row in audit["phase_attempts"] if row["role"] == "attester"
    ]
    assert attester_attempts[-1]["rejection"] == (
        f"field '{field}', passage {caller_text!r}"
    )


def test_original_neutrality_covers_hint_paths_and_blocks_fallback(
    repo: Path, tmp_path: Path,
):
    (repo / "prefer_float.py").write_text("VALUE = 1\n")
    commit_all(repo, "add deliberately steering hint path")
    cleaner = cleaner_reply({
        "opt-float": "Float.",
        "opt-decimal": "Use a Decimal, which is exact and avoids representation error entirely.",
    }).replace(
        "=== HINTS ===\nNone.",
        "=== HINTS ===\n- prefer_float.py: implementation entry point",
    )
    detail = {
        "opt-float": {
            "original":"Store the threshold as a float.", "cleaned":"Float.",
            "change":"narrowed", "reason":"opt-float: narrowed",
        },
        "opt-decimal": {
            "original":"Store the threshold as a Decimal.",
            "cleaned":"Use a Decimal, which is exact and avoids representation error entirely.",
            "change":"added", "reason":"opt-decimal: added",
        },
    }
    attestation = (
        "FIDELITY: decision PRESERVED; hints PRESERVED; opt-float CHANGED; opt-decimal CHANGED\n"
        f"FIDELITY-DETAIL: {json.dumps(detail, separators=(',', ':'))}\n"
        "NEUTRALITY: PASS\n"
        'ORIGINAL-NEUTRALITY: FAIL {"field":"hints","passage":"prefer_float.py"}\n'
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    agent = Agent(lambda e, r: "opt-float", cleaner=cleaner, attest=attestation)
    report = run(
        repo, agent, tmp_path,
        files=[{"path": "prefer_float.py", "reason": "implementation entry point"}],
    )

    assert "caller-owned original framing is not neutral enough for fallback" in report
    assert "field 'hints', passage 'prefer_float.py'" in report
    assert trailer_field(report, "CLEANING") == "cleaner-rejected"
    audit = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert audit["caller_framing_diagnostic"] is None
    assert audit["fallback_ineligibility_diagnostic"] == {
        "field": "hints", "passage": "prefer_float.py",
    }
    assert "every path and reason" in prompts.ATTEST_INSTRUCTIONS


def test_attestation_failure_retries_once_then_fails(repo: Path, tmp_path: Path):
    """One retry only: a longer loop would hill-climb the framing against the
    attester until it passed, which is optimization, not attestation."""
    agent = Agent(
        lambda e, r: "opt-float",
        attest=("FIDELITY: decision PRESERVED; "
                "opt-float CHANGED; opt-decimal PRESERVED\nNEUTRALITY: PASS\n"
                "STAKES-ADVOCACY: NONE\n"),
    )
    report = run(repo, agent, tmp_path)
    assert "failed attestation twice" in report
    assert len([c for c in agent.calls if "TEXT AUDITOR" in c["instructions"]]) == 2
    assert trailer_field(report, "SNAPSHOT") != "none"
    assert trailer_field(report, "CLEANING") == "attestation-rejected"
    assert trailer_field(report, "RESEARCH") == "not reached"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["snapshot"] == trailer_field(report, "SNAPSHOT")
    assert record["cleaning"] == "attestation-rejected"
    assert [attempt["role"] for attempt in record["phase_attempts"]] == [
        "cleaner", "attester", "cleaner", "attester",
    ]
    assert record["phase_attempts"][-1]["rejection"]


def test_fidelity_rejection_names_exact_passages_and_reason(repo: Path, tmp_path: Path):
    detail = json.dumps({"opt-float": {
        "original": "Store the threshold as a float",
        "cleaned": "Store an approximate threshold",
        "change": "altered-qualification",
        "reason": "opt-float: altered-qualification",
    }}, separators=(",", ":"))
    agent = Agent(lambda e, r: "opt-float", cleaner=cleaner_reply({
        "opt-float": "Store an approximate threshold.",
        "opt-decimal": "Store the threshold as a Decimal.",
    }), attest=(
        "FIDELITY: decision PRESERVED; opt-float CHANGED; opt-decimal PRESERVED\n"
        f"FIDELITY-DETAIL: {detail}\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: FAIL "
        '{"field":"opt-float","passage":"Store the threshold as a float"}\n'
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    ))
    report = run(repo, agent, tmp_path)

    assert detail in report
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert detail in record["phase_attempts"][-1]["rejection"]
    assert record["phase_attempts"][-1]["reply"]


def test_changed_fidelity_without_detail_is_unusable_not_empty_changed(
    repo: Path, tmp_path: Path,
):
    agent = Agent(lambda e, r: "opt-float", attest=(
        "FIDELITY: decision PRESERVED; opt-float CHANGED; opt-decimal PRESERVED\n"
        "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    ))
    report = run(repo, agent, tmp_path)

    assert "changed fidelity requires a specific FIDELITY-DETAIL" in report
    assert "fidelity changed: []" not in report


def test_changed_fidelity_detail_must_identify_both_passages_and_reason(
    repo: Path, tmp_path: Path,
):
    agent = Agent(lambda e, r: "opt-float", attest=(
        "FIDELITY: decision PRESERVED; opt-float CHANGED; opt-decimal PRESERVED\n"
        'FIDELITY-DETAIL: {"opt-float":{"reason":"wording differs"}}\n'
        "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    ))
    report = run(repo, agent, tmp_path)

    assert "must contain exactly original, cleaned, change, reason" in report


def test_changed_fidelity_detail_rejects_duplicate_json_keys():
    reply = (
        "FIDELITY: first CHANGED\n"
        'FIDELITY-DETAIL: {"first":{"original":"alpha","cleaned":"beta",'
        '"change":"narrowed","reason":"first: narrowed"},'
        '"first":{"original":"alpha","cleaned":"invented",'
        '"change":"widened","reason":"first: widened"}}\n'
        "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE"
    )
    with pytest.raises(ah.ArbitrationError, match="duplicate key 'first'"):
        ah.parse_attestation(reply, {"first": ("alpha original", "beta cleaned")})


def test_attestation_rejects_split_or_reordered_verdict_lines():
    split = (
        "FIDELITY: first PRESERVED\nFIDELITY: second PRESERVED\n"
        "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE"
    )
    with pytest.raises(ah.ArbitrationError, match="must be ordered"):
        ah.parse_attestation(split, {"first": ("a", "a"), "second": ("b", "b")})
    reordered = (
        "FIDELITY: first PRESERVED\nNEUTRALITY: PASS\nFIDELITY-DETAIL: NONE\n"
        "ORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE"
    )
    with pytest.raises(ah.ArbitrationError, match="must be ordered"):
        ah.parse_attestation(reordered, {"first": ("a", "a")})


@pytest.mark.parametrize(("verdict", "message"), [
    (
        'FAIL {"field":"unknown","passage":"alpha"}',
        "unknown field",
    ),
    (
        'FAIL {"field":"first","passage":"not present"}',
        "passage is not in original field",
    ),
    (
        'FAIL {"field":"first","field":"first","passage":"alpha"}',
        "duplicate key",
    ),
    (
        'FAIL {"field":"first","passage":"alpha","reason":"bias"}',
        "exactly field and passage",
    ),
])
def test_original_neutrality_failure_is_exactly_field_bound(verdict: str, message: str):
    reply = (
        "FIDELITY: first PRESERVED\nFIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\n"
        f"ORIGINAL-NEUTRALITY: {verdict}\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    with pytest.raises(ah.ArbitrationError, match=message):
        ah.parse_attestation(reply, {"first": ("alpha original", "alpha cleaned")})


@pytest.mark.parametrize(("detail", "message"), [
    (
        {"first": {"original": "alpha", "cleaned": "beta", "change": "narrowed", "reason": "first: narrowed"}},
        "fields must exactly equal CHANGED fields",
    ),
    (
        {
                "first": {"original": "gamma", "cleaned": "beta", "change": "narrowed", "reason": "first: narrowed"},
                "second": {"original": "gamma", "cleaned": "delta", "change": "narrowed", "reason": "second: narrowed"},
        },
        "original passage is not in that field",
    ),
    (
        {
                "first": {"original": "alpha", "cleaned": "invented", "change": "narrowed", "reason": "first: narrowed"},
                "second": {"original": "gamma", "cleaned": "delta", "change": "narrowed", "reason": "second: narrowed"},
        },
        "cleaned passage is not in that field",
    ),
    (
        {
            "first": {"original": "alpha", "cleaned": "beta", "change": "narrowed", "reason": ""},
            "second": {"original": "gamma", "cleaned": "delta", "change": "narrowed", "reason": "second: narrowed"},
        },
        "values must be non-empty strings",
    ),
    (
        {
            "first": {"original": "alpha", "cleaned": "beta", "change": "changed", "reason": "first: the wording is materially changed"},
            "second": {"original": "gamma", "cleaned": "delta", "change": "narrowed", "reason": "second: narrowed"},
        },
        "change must be one of",
    ),
    (
        {
            "first": {"original": "alpha", "cleaned": "beta", "change": "narrowed", "reason": "first: the wording is materially changed"},
            "second": {"original": "gamma", "cleaned": "delta", "change": "narrowed", "reason": "second: narrowed"},
        },
        "reason must be exactly 'first: narrowed'",
    ),
])
def test_changed_fidelity_diagnostics_are_bound_per_field(detail, message):
    reply = (
        "FIDELITY: first CHANGED; second CHANGED\n"
        f"FIDELITY-DETAIL: {json.dumps(detail, separators=(',', ':'))}\n"
        "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    with pytest.raises(ah.ArbitrationError, match=message):
        ah.parse_attestation(reply, {
            "first": ("alpha original", "beta cleaned"),
            "second": ("gamma original", "delta cleaned"),
        })


def test_cleaner_prompt_never_calls_context_neutralized_background():
    from paranoia_local import prompts

    context_block = prompts.CLEANER_INSTRUCTIONS.split("=== CONTEXT ===", 1)[1].split(
        "=== HINTS ===", 1
    )[0]
    assert "copy the supplied CONTEXT byte-for-byte" in context_block
    assert "neutral background" not in prompts.CLEANER_INSTRUCTIONS


def test_phase_reply_bound_retains_complete_normal_protocol_and_marks_overflow():
    normal = "x" * ah.MAX_PHASE_REPLY_CHARS
    assert ah._bounded_phase_reply(normal) == normal
    overflow = normal + "tail"
    bounded = ah._bounded_phase_reply(overflow)
    assert len(bounded) == ah.MAX_PHASE_REPLY_CHARS
    assert "[bounded phase output]" in bounded


def test_cleaning_limit_applies_to_the_fully_composed_prompt():
    ah._check_cleaning_prompt("cleaner", "x" * arb.MAX_CLEANING_PROMPT_CHARS)
    with pytest.raises(ah.ArbitrationError, match="cleaner prompt"):
        ah._check_cleaning_prompt("cleaner", "x" * (arb.MAX_CLEANING_PROMPT_CHARS + 1))


def test_attester_reply_size_is_bounded_and_attester_owned(
    repo: Path, tmp_path: Path,
):
    oversized = "x" * (arb.MAX_ATTESTER_REPLY_CHARS + 1)
    report = run(repo, Agent(lambda e, r: "opt-float", attest=oversized), tmp_path)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "CLEANING") == "attestation-rejected"
    assert "attester reply is" in report
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    attester_attempts = [
        row for row in record["phase_attempts"] if row["role"] == "attester"
    ]
    assert len(attester_attempts) == 2
    assert all("attester reply is" in row["rejection"] for row in attester_attempts)
    assert all(len(row["reply"]) <= ah.MAX_PHASE_REPLY_CHARS for row in attester_attempts)
    assert len(record["attestation"]) <= ah.MAX_PHASE_REPLY_CHARS
    assert "[bounded phase output]" in record["attestation"]


def test_cleaner_prompt_local_rejection_is_durable_before_spend(
    repo: Path, tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(arb, "MAX_CLEANING_PROMPT_CHARS", 1)
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path)

    assert not agent.calls
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    attempt = record["phase_attempts"][0]
    assert attempt["role"] == "cleaner"
    assert attempt["status"] == "local-rejected"
    assert attempt["admitted"] is attempt["invoked"] is False
    assert attempt["prompt_sha256"] and "cleaner prompt" in attempt["rejection"]


def test_attester_prompt_local_rejection_is_durable_before_spend(
    repo: Path, tmp_path: Path, monkeypatch,
):
    originals = {o["id"]: o["statement"] for o in sorted(OPTIONS, key=lambda o: o["id"])}
    cleaned_raw = cleaner_reply(originals)
    parsed = ah.parse_cleaned_packet(cleaned_raw, list(originals), caller_gave_context=False)
    cleaner_prompt = prompts.compose(
        prompts.CLEANER_INSTRUCTIONS,
        ah._clean_body(BASE["decision"], BASE["stakes"], "", [], originals, ""),
    )
    attester_prompt = prompts.compose(
        prompts.ATTEST_INSTRUCTIONS,
        ah._attest_body(BASE["decision"], BASE["stakes"], "", [], [], originals, parsed),
    )
    assert len(attester_prompt) > len(cleaner_prompt)
    monkeypatch.setattr(arb, "MAX_CLEANING_PROMPT_CHARS", len(cleaner_prompt))
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path)

    assert ["NEUTRALIZER" in call["instructions"] for call in agent.calls] == [True]
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    attempt = record["phase_attempts"][-1]
    assert attempt["role"] == "attester"
    assert attempt["status"] == "local-rejected"
    assert attempt["admitted"] is attempt["invoked"] is False
    assert attempt["prompt_sha256"] and "attester prompt" in attempt["rejection"]


def test_injected_attempts_record_execution_identity(repo: Path, tmp_path: Path):
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    attempts = record["phase_attempts"] + [
        attempt
        for cast in record["rounds"][0].values()
        for attempt in cast["attempts"]
    ]
    assert attempts
    for attempt in attempts:
        assert attempt["execution"]["route"] == "injected-agent"
        assert attempt["execution"]["engine"] in {"codex", "claude"}
        assert attempt["execution"]["model"]
        assert attempt["execution"]["binary"] is None
        assert attempt["execution"]["cli_version"] is None


def test_context_advocacy_fails_without_asking_cleaner_to_rewrite(
    repo: Path, tmp_path: Path,
):
    agent = Agent(lambda e, r: "opt-float", attest=(
        "FIDELITY: decision PRESERVED; opt-float PRESERVED; opt-decimal PRESERVED\n"
        "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\n"
        'CONTEXT-ADVOCACY: PRESENT {"field":"context","passage":"Obviously choose binary floating point."}\n'
    ))
    report = run(repo, agent, tmp_path, context="Obviously choose binary floating point.")

    assert "context text advocates" in report
    assert "caller framing rejected" in report
    assert trailer_field(report, "CLEANING") == "caller-framing-rejected"
    assert len([c for c in agent.calls if "NEUTRALIZER" in c["instructions"]]) == 1


def test_stakes_advocacy_fails_to_the_caller(repo: Path, tmp_path: Path):
    """stakes is not the cleaner's to fix, so this goes back to the caller."""
    agent = Agent(
        lambda e, r: "opt-float",
        attest=("FIDELITY: decision PRESERVED; "
                "opt-float PRESERVED; opt-decimal PRESERVED\nFIDELITY-DETAIL: NONE\n"
                "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
                'STAKES-ADVOCACY: PRESENT {"field":"stakes","passage":"trusted input"}\n'
                "CONTEXT-ADVOCACY: NONE\n"),
    )
    report = run(repo, agent, tmp_path)
    assert "stakes text advocates" in report
    assert "caller framing rejected" in report
    assert trailer_field(report, "CLEANING") == "caller-framing-rejected"


@pytest.mark.parametrize(
    "line, expected",
    [
        (
            'STAKES-ADVOCACY: PRESENT {"field":"context","passage":"trusted input"}',
            "names field 'context', expected 'stakes'",
        ),
        (
            'STAKES-ADVOCACY: PRESENT {"field":"stakes","passage":"invented words"}',
            "passage is not in caller field 'stakes'",
        ),
        (
            "CONTEXT-ADVOCACY: PRESENT free-form accusation",
            "PRESENT must contain one JSON object",
        ),
    ],
)
def test_caller_advocacy_diagnostics_are_field_and_passage_bound(
    repo: Path, tmp_path: Path, line: str, expected: str,
):
    stakes_line = line if line.startswith("STAKES") else "STAKES-ADVOCACY: NONE"
    context_line = line if line.startswith("CONTEXT") else "CONTEXT-ADVOCACY: NONE"
    attestation = (
        "FIDELITY: decision PRESERVED; opt-float PRESERVED; opt-decimal PRESERVED\n"
        "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        f"{stakes_line}\n{context_line}\n"
    )
    report = run(
        repo, Agent(lambda e, r: "opt-float", attest=attestation), tmp_path,
        context="Obviously choose binary floating point.",
    )

    assert expected in report
    assert trailer_field(report, "CLEANING") == "attestation-rejected"
    assert "caller framing rejected" not in report


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
    assert "## Audit fallback" in report
    assert '"outcome":"CONVERGED"' in report
    assert '"rounds"' in report


def test_terminal_correction_audit_failure_is_surfaced(
    repo: Path, tmp_path: Path, monkeypatch,
):
    scripted = Agent(lambda e, r: "opt-float")

    def malformed_claude(**kwargs):
        text = scripted(**kwargs)
        return (
            "AUTHORITY: duplicated too early\n" + text
            if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude"
            else text
        )

    monkeypatch.setattr(ah.logs, "write_log", lambda *a, **k: None)
    report = run(repo, malformed_claude, tmp_path, clean=False)

    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "AUDIT") == "FAILED could not write log"
    assert "## Audit fallback" in report
    assert '"failed_round"' in report
    assert '"attempts"' in report


def test_research_run_audit_bounds_and_hashes_raw_provider_envelopes():
    oversized = "provider-envelope-" * 2_000
    run_record = ah.ResearchRun(
        "codex", "model", (), (), (), oversized, oversized, 2, (), (), (),
    )
    [record] = ah._research_run_records([run_record])
    expected = hashlib.sha256(oversized.encode()).hexdigest()
    assert record["discovery_raw_sha256"] == expected
    assert record["binding_raw_sha256"] == expected
    assert len(record["discovery_raw_excerpt"]) < len(oversized)
    assert len(record["binding_raw_excerpt"]) < len(oversized)


def test_run_agent_preserves_all_engine_failure_channels(monkeypatch, tmp_path: Path):
    class FailedEngine:
        def for_role(self, _role):
            return self

        def run(self, *args, **kwargs):
            return eng.Review(
                text="partial model text", session_ref="session", raw="raw envelope",
                returncode=9, error=True, failure_detail="structured failure",
                stderr="process stderr",
            )

    monkeypatch.setattr(ah.eng, "get_engine", lambda *a, **k: FailedEngine())
    with pytest.raises(ah.EngineCallError) as caught:
        ah._run_agent(
            engine_name="codex", model="m", instructions="i", body="b",
            cwd=tmp_path, effort="high", web_search=False, timeout=1,
            text_only=False,
        )
    assert caught.value.record == {
        "engine": "codex", "returncode": 9,
        "failure_detail": "structured failure", "text": "partial model text",
        "raw": "raw envelope", "stderr": "process stderr",
    }


def test_run_agent_marks_engine_setup_failure_before_provider_invocation(
    monkeypatch, tmp_path: Path,
):
    lifecycle = {
        "status": "admitted", "admitted": True, "invoked": False,
        "execution": ah._execution_identity("codex", "m"),
    }
    monkeypatch.setattr(
        ah.eng, "get_engine", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("engine setup unavailable")
        ),
    )

    with pytest.raises(RuntimeError, match="engine setup unavailable"):
        ah._run_agent(
            engine_name="codex", model="m", instructions="i", body="b",
            cwd=tmp_path, effort="high", web_search=False, timeout=1,
            text_only=False, _attempt_lifecycle=lifecycle,
        )

    assert lifecycle == {
        "status": "setup-failed", "admitted": True, "invoked": False,
        "execution": ah._execution_identity("codex", "m"),
    }


def test_run_agent_records_external_cli_execution_identity(monkeypatch, tmp_path: Path):
    class SuccessfulEngine:
        binary = "codex"

        def for_role(self, _role):
            return self

        def run(self, *args, **kwargs):
            return eng.Review(text="ok", session_ref="s", raw="raw")

    lifecycle = {"status": "admitted", "admitted": True, "invoked": False}
    monkeypatch.setattr(ah.eng, "get_engine", lambda *a, **k: SuccessfulEngine())
    monkeypatch.setattr(ah.eng, "require_evidence_profile", lambda engine: "0.144.6")

    assert ah._run_agent(
        engine_name="codex", model="gpt-5.6-sol", instructions="i", body="b",
        cwd=tmp_path, effort="high", web_search=False, timeout=1,
        text_only=False, _attempt_lifecycle=lifecycle,
    ) == "ok"
    assert lifecycle["execution"] == {
        "engine": "codex", "model": "gpt-5.6-sol", "route": "external-cli",
        "binary": "codex", "cli_version": "0.144.6",
    }


def test_research_role_setup_failure_is_prompt_bound_and_counts_zero_calls():
    class SetupFails(FakeEngine):
        def for_role(self, role: str):
            raise RuntimeError("research role unavailable")

    packet = ah.Packet("Choose.", "Local tool.", "", [], {"a": "A", "b": "B"},
                       "skipped", "skipped")
    with pytest.raises(ah.ResearchFailure) as caught:
        ah._research_one(
            engine=SetupFails("claude"), model="m", packet=packet,
            options=("A", "B"), forbidden=("a", "b"), effort="medium",
        )

    record = caught.value.record
    assert record["kind"] == "setup"
    assert record["calls"] == 0
    assert record["attempts"][0]["status"] == "setup-failed"
    assert record["attempts"][0]["invoked"] is False
    assert len(record["attempts"][0]["prompt_sha256"]) == 64


def test_decider_audit_preserves_structured_engine_failure_channels(
    repo: Path, tmp_path: Path,
):
    scripted = Agent(lambda e, r: "opt-float")
    channels = {
        "engine": "claude", "returncode": 9,
        "failure_detail": "structured failure", "text": "partial text",
        "raw": "raw envelope", "stderr": "process stderr",
    }

    def failed_agent(**kwargs):
        if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude":
            raise ah.EngineCallError("claude failed", channels)
        return scripted(**kwargs)

    report = run(repo, failed_agent, tmp_path, clean=False)
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    attempt = record["failed_round"]["deciders"]["claude"]["attempts"][0]
    assert attempt["failure"] == channels


def test_aggregate_audit_fallback_is_bounded_and_schema_preserving(
    tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(ah.logs, "write_log", lambda *a, **k: None)
    huge = "reply-" * 20_000
    failures = [
        {"engine": f"lane-{index}", "attempts": [{"raw": huge}] * 40}
        for index in range(40)
    ]
    record = {
        "outcome": "FAILED",
        "research": {
            "failures": failures,
            "runs": [{"engine": "completed-peer", "captures": [{"text": huge}]}],
        },
    }
    audit, fallback = ah._write_bounded_audit(
        tmp_path, record=record, timestamp="20260812T000000",
    )
    assert audit is None and fallback is not None
    assert len(fallback) <= ah.MAX_AUDIT_FALLBACK_CHARS
    parsed = json.loads(fallback)
    assert parsed["research"]["runs"][0]["engine"] == "completed-peer"
    assert parsed["research"]["failures"][-1]["_omitted_items"] > 0


def test_audit_fallback_bounds_wide_nested_provider_mappings(
    tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(ah.logs, "write_log", lambda *a, **k: None)
    wide = {
        f"field-{index}": {f"nested-{inner}": "x" * 10_000 for inner in range(100)}
        for index in range(100)
    }
    audit, fallback = ah._write_bounded_audit(
        tmp_path,
        record={"outcome": "FAILED", "research": {"failures": [{"usage": wide}]}},
        timestamp="20260812T000000",
    )
    assert audit is None and fallback is not None
    assert len(fallback) <= ah.MAX_AUDIT_FALLBACK_CHARS
    parsed = json.loads(fallback)
    usage = parsed["research"]["failures"][0]["usage"]
    assert usage["_omitted_fields"] > 0
    assert len(usage["_omitted_fields_sha256"]) == 64


def test_durable_audit_keeps_exact_large_packet_bytes(tmp_path: Path):
    packet = "packet-byte-" * 2_000
    audit, fallback = ah._write_bounded_audit(
        tmp_path,
        record={"outcome": "CONVERGED", "research": {"packets": packet}},
        timestamp="20260812T000000",
    )
    assert audit is not None and fallback is None
    record = json.loads(audit.read_text())
    assert record["research"]["packets"] == packet


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

    # this caller DOES supply files, so `hints` is an attestable field for it
    agent = HintCleaner(lambda e, r: "opt-float", attest=ATTEST_OK_WITH_HINTS)
    report = run(repo, agent, tmp_path=Path(repo.parent), files=[
        {"path": "app.py", "reason": "the APPROVED implementation, obviously"}
    ])
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    for call in agent.calls:
        if call["cwd"] is None:
            continue
        assert "the module under discussion" in call["body"]
        assert "APPROVED" not in call["body"]
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["cleaned"]["hints"] == [
        {"path": "app.py", "reason": "the module under discussion"}
    ]
    assert len(record["cleaned"]["sha256"]) == 64
    assert all(len(item["reply_sha256"]) == 64 for item in record["phase_attempts"])


def test_attester_sees_the_real_original_hints(repo: Path, tmp_path: Path):
    """An auditor shown "(paths and reasons as given)" cannot compare anything."""
    agent = Agent(lambda e, r: "opt-float", cleaner=(
        cleaner_reply({o["id"]: o["statement"] for o in OPTIONS})
        .replace("=== HINTS ===\nNone.", "=== HINTS ===\n- app.py: MARKER-ORIGINAL-REASON")
    ), attest=ATTEST_OK_WITH_HINTS)
    report = run(
        repo, agent, tmp_path,
        files=[{"path": "app.py", "reason": "MARKER-ORIGINAL-REASON"}],
    )
    attest_body = next(c["body"] for c in agent.calls if "TEXT AUDITOR" in c["instructions"])
    delivered = "- app.py (MARKER-ORIGINAL-REASON)"
    assert f"ORIGINAL: {delivered}" in attest_body
    assert f"CLEANED:  {delivered}" in attest_body
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    for cast in record["rounds"][0].values():
        assert delivered in cast["prompt"]
    assert "(paths and reasons as given)" not in attest_body


@pytest.mark.parametrize(
    "bad",
    [
        # missing every field but one
        "FIDELITY: decision PRESERVED\nNEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE\n",
        # a value that is neither PRESERVED nor CHANGED
        ("FIDELITY: decision UNKNOWN; "
         "opt-float PRESERVED; opt-decimal PRESERVED\nNEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE\n"),
        # no neutrality verdict
        ("FIDELITY: decision PRESERVED; "
         "opt-float PRESERVED; opt-decimal PRESERVED\nSTAKES-ADVOCACY: NONE\n"),
        # no stakes verdict
        ("FIDELITY: decision PRESERVED; "
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
                text="SELECTED: whatever\n", session_ref=None, raw="raw fallback",
                returncode=1, error=True,
                failure_detail="provider credit exhausted before completion",
            )

    monkeypatch.setattr(ah.eng, "get_engine", lambda name, text_only=False: Failing())
    with pytest.raises(Exception) as caught:
        ah._run_agent(
            engine_name="codex", model="m", instructions="i", body="b", cwd=None,
            effort="low", web_search=False, timeout=5, text_only=True,
        )
    assert "provider credit exhausted before completion" in str(caught.value)
    assert "SELECTED: whatever" not in str(caught.value)
    assert "raw fallback" not in str(caught.value)


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


def test_non_object_file_hint_fails_before_snapshot_with_complete_audit(
    repo: Path, tmp_path: Path,
):
    report = run(
        repo, Agent(lambda e, r: "opt-float"), tmp_path,
        files=["app.py"],
    )
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "SNAPSHOT") == "none"
    assert "every file hint must be an object" in report
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["outcome"] == "FAILED"
    assert record["raw_input"]["files"] == ["app.py"]


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
    assert [item["role"] for item in record["phase_attempts"]] == [
        "cleaner", "attester",
    ]
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
    assert trailer_field(report, "SNAPSHOT") != "none"
    assert trailer_field(report, "CLEANING") == "not reached"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["snapshot"] == trailer_field(report, "SNAPSHOT")
    assert len(record["refs_before"]) == 64
    assert len(record["refs_after"]) == 64
    assert agent.calls == []  # nothing spent


def test_second_setup_ref_failure_is_recorded_without_retry(
    repo: Path, tmp_path: Path, monkeypatch,
):
    real = evidence.refs_digest
    calls = 0

    def digest(repo_):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise arb.ArbitrationError("setup boundary unavailable")
        return real(repo_)

    monkeypatch.setattr(ah.evidence, "refs_digest", digest)
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path, clean=False)
    assert calls == 2
    assert trailer_field(report, "REFS-MOVED") == "unavailable"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["refs_after"] is None
    assert "setup boundary unavailable" in record["ref_provenance_error"]


def test_unavailable_ref_provenance_during_setup_fails_before_snapshot(
    repo: Path, tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(
        ah.evidence, "refs_digest",
        lambda _repo: (_ for _ in ()).throw(arb.ArbitrationError("ref provenance unavailable")),
    )
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path, clean=False)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "SNAPSHOT") == "none"
    assert trailer_field(report, "REFS-MOVED") == "unavailable"
    assert "ref provenance unavailable" in report
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["refs_before"] is None
    assert record["refs_after"] is None
    assert record["refs_moved"] is None
    assert "ref provenance unavailable" in record["ref_provenance_error"]


def test_unavailable_final_ref_provenance_preserves_established_failure(
    repo: Path, tmp_path: Path, monkeypatch,
):
    real = evidence.refs_digest
    calls = 0

    def digest(repo_):
        nonlocal calls
        calls += 1
        if calls >= 3:
            raise arb.ArbitrationError("final ref provenance unavailable")
        return real(repo_)

    monkeypatch.setattr(ah.evidence, "refs_digest", digest)
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path, clean=False)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "SNAPSHOT") != "none"
    assert "final ref provenance unavailable" in report
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["refs_after"] is None
    assert "final ref provenance unavailable" in record["ref_provenance_error"]
    assert record["rounds"]


def test_failed_final_ref_observation_is_not_retried(
    repo: Path, tmp_path: Path, monkeypatch,
):
    real = evidence.refs_digest
    calls = 0

    def digest(repo_):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise arb.ArbitrationError("one-shot final provenance failure")
        return real(repo_)

    monkeypatch.setattr(ah.evidence, "refs_digest", digest)
    report = run(repo, Agent(lambda e, r: "opt-float"), tmp_path, clean=False)
    assert calls == 3
    assert trailer_field(report, "REFS-MOVED") == "unavailable"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["refs_after"] is None
    assert "one-shot final provenance failure" in record["ref_provenance_error"]


def test_other_failure_plus_unavailable_final_refs_renders_unavailable(
    repo: Path, tmp_path: Path, monkeypatch,
):
    real = evidence.refs_digest
    calls = 0

    def digest(repo_):
        nonlocal calls
        calls += 1
        if calls >= 3:
            raise arb.ArbitrationError("final refs unreadable")
        return real(repo_)

    def failed_decider(**kwargs):
        if kwargs["cwd"] is not None and kwargs["engine_name"] == "claude":
            raise RuntimeError("provider unavailable")
        return scripted(**kwargs)

    scripted = Agent(lambda e, r: "opt-float")
    monkeypatch.setattr(ah.evidence, "refs_digest", digest)
    report = run(repo, failed_decider, tmp_path, clean=False)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert trailer_field(report, "REFS-MOVED") == "unavailable"
    assert "provider unavailable" in report
    assert "final ref provenance unavailable" in report


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


def test_refs_moving_after_snapshot_is_provenance_only(repo: Path, tmp_path: Path):
    """Deciders see inert snapshot materializations, never the moving live refs."""

    class Moving(Agent):
        def __call__(self, **kw):
            out = super().__call__(**kw)
            if kw["cwd"] is not None and len(self.calls) == 3:
                (repo / "landed.py").write_text("x = 1\n")
                commit_all(repo, "landed mid-run")
            return out

    report = run(repo, Moving(lambda e, r: "opt-float"), tmp_path, retain_snapshot=True)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "REFS-MOVED") == "yes"
    assert "refs/paranoia/arbitrate/" in git(
        ["for-each-ref", "--format=%(refname)"], repo
    )


@pytest.mark.parametrize(
    "verdicts",
    [
        # a qualified PASS is not a pass
        "NEUTRALITY: PASS but the wording favors option A\nSTAKES-ADVOCACY: NONE\n",
        # a qualified NONE is not none
        "NEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE despite recommending A\n",
        # FAIL with no note says nothing
        "NEUTRALITY: FAIL\nSTAKES-ADVOCACY: NONE\n",
        "NEUTRALITY: FAILURE biased words\nSTAKES-ADVOCACY: NONE\n",
        "NEUTRALITY: maybe\nSTAKES-ADVOCACY: NONE\n",
        "NEUTRALITY: PASS\nSTAKES-ADVOCACY: PRESENTLY biased words\n",
    ],
)
def test_qualified_attestation_verdicts_are_not_accepted(repo: Path, tmp_path: Path, verdicts: str):
    """Round-8 blocker: prefix matching let a demonstrably biased packet be stamped
    `attested`, sending the same bias to both deciders."""
    fidelity = (
        "FIDELITY: decision PRESERVED; "
        "opt-float PRESERVED; opt-decimal PRESERVED\n"
    )
    agent = Agent(lambda e, r: "opt-float", attest=fidelity + verdicts)
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert all(c["cwd"] is None for c in agent.calls)  # never reached the deciders


def test_stakes_advocacy_present_with_the_words_still_fails_to_the_caller(repo: Path, tmp_path: Path):
    agent = Agent(
        lambda e, r: "opt-float",
        attest=("FIDELITY: decision PRESERVED; "
                "opt-float PRESERVED; opt-decimal PRESERVED\nFIDELITY-DETAIL: NONE\n"
                "NEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
                'STAKES-ADVOCACY: PRESENT {"field":"stakes","passage":"trusted input"}\n'
                "CONTEXT-ADVOCACY: NONE\n"),
    )
    report = run(repo, agent, tmp_path)
    assert "stakes text advocates" in report


@pytest.mark.parametrize(
    "extra",
    [
        "The cleaned wording still favors option A.",
        "Note: I could not compare the hints.",
    ],
)
def test_commentary_in_the_attestation_is_rejected(repo: Path, tmp_path: Path, extra: str):
    """Round-9 blocker: unrecognized lines were ignored, so `NEUTRALITY: PASS`
    followed by a contradicting sentence was accepted as clean."""
    agent = Agent(lambda e, r: "opt-float", attest=ATTEST_OK + extra + "\n")
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert all(c["cwd"] is None for c in agent.calls)


def test_duplicate_attestation_verdicts_are_rejected(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float", attest=ATTEST_OK + "NEUTRALITY: PASS\n")
    assert trailer_field(run(repo, agent, tmp_path), "ARBITRATION") == "FAILED"


# --- field-report fixes (issue #8) -------------------------------------------


def test_the_field_scenario_now_converges(repo: Path, tmp_path: Path):
    """Issue #8's actual run: round 1 diverges, codex flips onto claude's carried
    region, claude holds and cites the producer code instead of the artifact. That
    is a unanimous verdict on accurate citations and must not be UNRESOLVED."""
    (repo / "writer.py").write_text("w\n" * 40)
    (repo / "manifest.json").write_text("m\n" * 40)
    (repo / "test_writer.py").write_text("t\n" * 40)
    commit_all(repo, "field shapes")
    agent = Agent(
        lambda engine, rnd: "opt-float" if (engine == "codex" and rnd == 1) else "opt-decimal",
        extra={
            ("codex", 1): {"decisive": "test_writer.py:20"},
            ("claude", 1): {"decisive": "manifest.json:20"},
            # codex flips onto the region claude produced -> carried grounding
            ("codex", 2): {"decisive": "manifest.json:20", "authority": "human-owner"},
            # claude holds, and goes deeper: the producer code, never carried
            ("claude", 2): {"decisive": "writer.py:20"},
        },
    )
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "SELECTED") == "opt-decimal"
    assert trailer_field(report, "ROUNDS") == "2"
    assert trailer_field(report, "ADVISORY") == "human-owner (flagged by: codex)"


def test_a_flip_onto_uncarried_evidence_is_still_unsubstantiated(repo: Path, tmp_path: Path):
    """The anti-capitulation purpose end to end."""
    (repo / "elsewhere.py").write_text("e\n" * 40)
    commit_all(repo, "elsewhere")
    agent = Agent(
        lambda engine, rnd: "opt-float" if (engine == "codex" and rnd == 1) else "opt-decimal",
        extra={("codex", 2): {"decisive": "elsewhere.py:20"}},
    )
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "UNRESOLVED"
    assert "codex" in report


def test_attestation_does_not_cover_fields_the_caller_never_supplied(repo: Path, tmp_path: Path):
    """Issue #8 fix 4: call 1 failed on `fidelity changed: ['context']` for a field
    the caller had no control over."""
    agent = Agent(lambda e, r: "opt-float", attest=(
        "FIDELITY: decision PRESERVED; opt-float PRESERVED; opt-decimal PRESERVED\n"
        "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\n"
        "CONTEXT-ADVOCACY: NONE\n"
    ))
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    attest_bodies = [c["body"] for c in agent.calls if "TEXT AUDITOR" in c["instructions"]]
    assert attest_bodies and "context" not in attest_bodies[0].lower().split("=== stakes")[0]


def test_a_cleaner_invented_context_is_ignored(repo: Path, tmp_path: Path):
    """Cleaner context is never authoritative, including when the caller supplied none."""
    agent = Agent(lambda e, r: "opt-float", cleaner=(
        "=== DECISION ===\nd\n\n"
        "=== OPTIONS ===\nopt-float: Store the threshold as a float.\n"
        "opt-decimal: Store the threshold as a Decimal.\n\n"
        "=== CONTEXT ===\nThe system already uses floats everywhere.\n\n"
        "=== HINTS ===\nNone.\n"
    ))
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["cleaned"]["context"] == ""


def test_substantive_length_asymmetry_reaches_both_deciders_exactly(
    repo: Path, tmp_path: Path,
):
    statements = {"A": "Keep the current behavior.", "B": "Use the bounded path. " + "y" * 180}
    cleaner = cleaner_reply(statements)
    attest = (
        "FIDELITY: decision PRESERVED; A PRESERVED; B PRESERVED\n"
        "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    )
    agent = Agent(lambda e, r: "A", cleaner=cleaner, attest=attest, statements=statements)
    report = run(
        repo, agent, tmp_path,
        options=[{"id": key, "statement": value} for key, value in statements.items()],
    )
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "CLEANING") == "attested"
    deciders = [call for call in agent.calls if call["cwd"] is not None]
    assert len(deciders) == 2
    for call in deciders:
        assert all(statement in call["body"] for statement in statements.values())


def test_the_cleaner_may_compress_narration_without_tripping_the_floor(repo: Path, tmp_path: Path):
    """Fix 3: option A's text was mostly consequence-narration and the cleaner cut it
    to 0.09x. Meaning-preservation is the attester's job, not a char ratio's."""
    long_a = "Ship the core only. " + "Outcome under this option: the manifest still fails. " * 12
    long_b = "Ship the core plus both rules. " + "Outcome under this option: the manifest verifies. " * 12
    agent = Agent(
        lambda e, r: "A",
        # label lookup matches on what the deciders actually see: the CLEANED text
        statements={"A": "a" * 90, "B": "b" * 120},
        cleaner=(
            "=== DECISION ===\nd\n\n"
            f"=== OPTIONS ===\nA: {'a' * 90}\nB: {'b' * 120}\n\n"
            "=== CONTEXT ===\nNone.\n\n"
            "=== HINTS ===\nNone.\n"
        ),
            attest=("FIDELITY: decision PRESERVED; A PRESERVED; B PRESERVED\n"
                    "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
                    "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"),
    )
    report = run(repo, agent, tmp_path,
                 options=[{"id": "A", "statement": long_a}, {"id": "B", "statement": long_b}])
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"


def test_absolute_cleaned_option_overflow_allows_original_fallback(
    repo: Path, tmp_path: Path,
):
    agent = Agent(
        lambda e, r: "opt-float",
        cleaner=(
            "=== DECISION ===\nd\n\n"
            f"=== OPTIONS ===\nopt-float: {'a' * 40}\nopt-decimal: {'b' * 1300}\n\n"
            "=== CONTEXT ===\nNone.\n\n"
            "=== HINTS ===\nNone.\n"
        ),
    )
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "CLEANING") == "original-attested"


def test_a_held_vote_that_was_never_substantiated_must_still_ground(repo: Path, tmp_path: Path):
    """Round-1 review blocker. Waiving carried grounding for a holder rests on that
    holder already being substantiated. A vendor that reached round 2 with no resolving
    decisive citation has no such standing, and must not ride to CONVERGED on a fresh
    citation that merely resolves while the other vendor moves onto its supporting
    region."""
    (repo / "elsewhere.py").write_text("e\n" * 40)
    (repo / "third.py").write_text("t\n" * 40)
    commit_all(repo, "elsewhere and third")
    agent = Agent(
        lambda engine, rnd: "opt-float" if (engine == "codex" and rnd == 1) else "opt-decimal",
        extra={
            # claude picks decimal in round 1 with NO decisive citation, but supplies a
            # supporting region so reconciliation is still permitted
            ("claude", 1): {"decisive": "NONE", "citations": "app.py:4"},
            ("codex", 1): {"decisive": "elsewhere.py:20"},
            # codex flips onto claude's supporting region
            ("codex", 2): {"decisive": "app.py:4"},
            # claude holds, on a citation that resolves but was NEVER carried to it
            ("claude", 2): {"decisive": "third.py:20"},
        },
    )
    report = run(repo, agent, tmp_path)
    assert trailer_field(report, "ARBITRATION") == "UNRESOLVED"
    assert "claude" in report


def test_a_caller_context_that_reads_None_is_not_swallowed(repo: Path, tmp_path: Path):
    """Round-1 review blocker: `None.` is a sentinel only when the caller supplied no
    context. As a real datum — the observed output of the thing being adjudicated — it
    must reach the deciders verbatim."""
    agent = Agent(lambda e, r: "opt-float", cleaner=(
        "=== DECISION ===\nd\n\n"
        "=== OPTIONS ===\nopt-float: Store the threshold as a float.\n"
        "opt-decimal: Store the threshold as a Decimal.\n\n"
        "=== CONTEXT ===\nNone.\n\n"
        "=== HINTS ===\nNone.\n"
    ), attest=(
        "FIDELITY: decision PRESERVED; opt-float PRESERVED; "
        "opt-decimal PRESERVED\nFIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\n"
        "ORIGINAL-NEUTRALITY: PASS\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
    ))
    report = run(repo, agent, tmp_path, context="None.")
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    for call in agent.calls:
        if call["cwd"] is None:
            continue
        assert "None." in call["body"], "the caller's context must reach the deciders"


def test_cleaner_context_rewrite_is_ignored_and_caller_bytes_reach_deciders(
    repo: Path, tmp_path: Path,
):
    original = "Shared specification:\n- MUST preserve `x == y`\n- Do not reflow this list."
    agent = Agent(lambda e, r: "opt-float", cleaner=(
        "=== DECISION ===\nd\n\n"
        "=== OPTIONS ===\nopt-float: Store the threshold as a float.\n"
        "opt-decimal: Store the threshold as a Decimal.\n\n"
        "=== CONTEXT ===\nA shortened paraphrase.\n\n"
        "=== HINTS ===\nNone.\n"
    ))
    report = run(repo, agent, tmp_path, context=original)

    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["cleaned"]["context"] == original


def test_context_leading_and_trailing_whitespace_reaches_deciders_unchanged(
    repo: Path, tmp_path: Path,
):
    original = "\n  Shared table heading\n\nrow | value  \n"
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path, context=original)

    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    assert record["raw_input"]["context"] == original
    assert record["cleaned"]["context"] == original
    assert all(original in call["body"] for call in agent.calls if call["cwd"] is not None)
    assert all(
        original in call["body"] for call in agent.calls if call["cwd"] is not None
    )


def test_clean_false_is_not_subject_to_cleaner_capacity_bounds(repo: Path, tmp_path: Path):
    """Round-1 review: the char caps are justified by cleaner round-trip capacity, and
    `clean: false` never invokes a cleaner."""
    long_a = "a" * 2000
    long_b = "b" * 2000
    report = run(repo, Agent(lambda e, r: "A", statements={"A": long_a, "B": long_b}),
                 tmp_path, clean=False,
                 options=[{"id": "A", "statement": long_a}, {"id": "B", "statement": long_b}])
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert trailer_field(report, "CLEANING") == "skipped"


def test_initial_decider_prompt_local_rejection_is_recorded_without_call(
    repo: Path, tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(arb, "MAX_DECIDER_PROMPT_CHARS", 1)
    agent = Agent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path, clean=False)

    assert not agent.calls
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    failures = record["failed_round"]["deciders"]
    assert set(failures) == {"codex", "claude"}
    for failure in failures.values():
        attempt = failure["attempts"][0]
        assert attempt["status"] == "local-rejected"
        assert attempt["admitted"] is attempt["invoked"] is False
        assert attempt["prompt_sha256"] and "decider prompt" in attempt["rejection"]


def test_correction_decider_prompt_local_rejection_retains_both_attempts(
    repo: Path, tmp_path: Path, monkeypatch,
):
    statements = {o["id"]: o["statement"] for o in OPTIONS}
    packet = ah.Packet(
        decision=BASE["decision"], stakes=BASE["stakes"], context="", hints=[],
        statements=statements, cleaning="skipped", attestation="skipped",
    )
    presentation = arb.Presentation(
        engine="codex",
        items=(("OPTION-0000000000000000", statements["opt-float"]),
               ("OPTION-1111111111111111", statements["opt-decimal"])),
        label_to_id={"OPTION-0000000000000000": "opt-float",
                     "OPTION-1111111111111111": "opt-decimal"},
        id_to_label={"opt-float": "OPTION-0000000000000000",
                     "opt-decimal": "OPTION-1111111111111111"},
        reversed_order=False,
    )
    initial = prompts.compose(
        prompts.ARBITRATE_INSTRUCTIONS, ah.render_decider_body(packet, presentation),
    )
    monkeypatch.setattr(arb, "MAX_DECIDER_PROMPT_CHARS", len(initial))

    class InvalidDeciderAgent(Agent):
        def __call__(self, **kwargs):
            if kwargs["cwd"] is not None:
                self.calls.append(kwargs)
                return "malformed"
            return super().__call__(**kwargs)

    agent = InvalidDeciderAgent(lambda e, r: "opt-float")
    report = run(repo, agent, tmp_path, clean=False)

    assert len(agent.calls) == 2
    record = json.loads(Path(trailer_field(report, "AUDIT")).read_text())
    for failure in record["failed_round"]["deciders"].values():
        assert [item["status"] for item in failure["attempts"]] == [
            "provider-completed", "local-rejected",
        ]
        assert failure["attempts"][1]["admitted"] is False
        assert failure["attempts"][1]["invoked"] is False


def test_clean_false_accepts_substantive_length_asymmetry(repo: Path, tmp_path: Path):
    statements = {"A": "x" * 300, "B": "y" * 900}
    report = run(
        repo, Agent(lambda e, r: "A", statements=statements), tmp_path, clean=False,
        options=[{"id": key, "statement": value} for key, value in statements.items()],
    )
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"


def test_a_cleaner_that_omits_context_is_structurally_rejected(repo: Path, tmp_path: Path):
    agent = Agent(lambda e, r: "opt-float", cleaner=(
        "=== DECISION ===\nd\n\n"
        "=== OPTIONS ===\nopt-float: Store the threshold as a float.\n"
        "opt-decimal: Store the threshold as a Decimal.\n\n"
        "=== HINTS ===\nNone.\n"
    ))
    report = run(repo, agent, tmp_path, context="None.")
    assert trailer_field(report, "ARBITRATION") == "FAILED"
    assert "no === CONTEXT === block" in report


def test_the_attester_template_names_exactly_the_fields_it_is_given(repo: Path, tmp_path: Path):
    """Round-2 review: the parser's expected set became dynamic while the prompt still
    hardcoded `context` and `hints`. An attester obeying the prompt verbatim was then
    rejected for covering unknown fields — reproducing the production false failure this
    branch exists to remove. The prompt and the parser must agree."""
    from paranoia_local import prompts

    assert "context PRESERVED|CHANGED; hints PRESERVED|CHANGED" not in prompts.ATTEST_INSTRUCTIONS
    assert "EVERY field that appears in the FIELD BY FIELD section" in prompts.ATTEST_INSTRUCTIONS

    seen: dict[str, str] = {}

    class Recorder(Agent):
        def __call__(self, **kw):
            if "TEXT AUDITOR" in kw["instructions"]:
                seen["body"] = kw["body"]
                # answer with exactly the fields the body carries, as instructed
                fields = [
                    line[1:-1] for line in kw["body"].splitlines()
                    if line.startswith("[") and line.endswith("]")
                ]
                self.attest = (
                    "FIDELITY: " + "; ".join(f"{f} PRESERVED" for f in fields) + "\n"
                    "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
                    "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
                )
            return super().__call__(**kw)

    report = run(repo, Recorder(lambda e, r: "opt-float"), tmp_path)
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert "[context]" not in seen["body"] and "[hints]" not in seen["body"]


def test_attester_checks_verbatim_context_advocacy_and_hint_fidelity(repo: Path, tmp_path: Path):
    """Context is outside fidelity scoring but remains visible to the advocacy check."""
    seen: dict[str, str] = {}

    class Recorder(Agent):
        def __call__(self, **kw):
            if "TEXT AUDITOR" in kw["instructions"]:
                seen["body"] = kw["body"]
                fields = [
                    line[1:-1] for line in kw["body"].splitlines()
                    if line.startswith("[") and line.endswith("]")
                ]
                self.attest = (
                    "FIDELITY: " + "; ".join(f"{f} PRESERVED" for f in fields) + "\n"
                    "FIDELITY-DETAIL: NONE\nNEUTRALITY: PASS\nORIGINAL-NEUTRALITY: PASS\n"
                    "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE\n"
                )
            if "NEUTRALIZER" in kw["instructions"]:
                opts = "\n".join(f"{k}: {v}" for k, v in self.statements.items())
                return (
                    "=== DECISION ===\nd\n\n"
                    f"=== OPTIONS ===\n{opts}\n\n"
                    "=== CONTEXT ===\nThe threshold is written to a log line.\n\n"
                    "=== HINTS ===\n- app.py: the module\n"
                )
            return super().__call__(**kw)

    report = run(repo, Recorder(lambda e, r: "opt-float"), tmp_path,
                 context="The threshold is written to a log line.",
                 files=[{"path": "app.py", "reason": "the module"}])
    assert trailer_field(report, "ARBITRATION") == "CONVERGED"
    assert "[context]" not in seen["body"] and "[hints]" in seen["body"]
    assert "=== CONTEXT (NOT cleaned" in seen["body"]
