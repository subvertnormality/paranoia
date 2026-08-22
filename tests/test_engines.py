import json
import re
from pathlib import Path

import pytest

from paranoia_local import engines
from paranoia_local.runner import RunResult


CODEX_JSONL = (
    '{"type":"thread.started","thread_id":"abc-123"}\n'
    '{"type":"turn.started"}\n'
    '{"type":"item.completed","item":{"id":"i0","type":"reasoning","text":"thinking"}}\n'
    '{"type":"item.completed","item":{"id":"i1","type":"agent_message","text":"## What works\\nNothing notable."}}\n'
    '{"type":"turn.completed","usage":{"input_tokens":10}}\n'
)

CLAUDE_JSON = (
    '{"type":"result","subtype":"success","is_error":false,'
    '"result":"## What works\\nNothing notable.","session_id":"sess-xyz",'
    '"total_cost_usd":0.01}'
)

STRUCTURED_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


class TestFactory:
    def test_get_codex(self) -> None:
        assert engines.get_engine("codex").name == "codex"

    def test_get_claude(self) -> None:
        assert engines.get_engine("claude").name == "claude"

    def test_unknown_engine_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown engine"):
            engines.get_engine("gemini")

    def test_default_models(self) -> None:
        assert "gpt-5.6" in engines.get_engine("codex").default_model
        assert "fable" in engines.get_engine("claude").default_model


@pytest.mark.parametrize(
    ("engine", "version", "rendered"),
    [
        (engines.CodexEngine(), (0, 144, 6), "0.144.6"),
        (engines.CodexEngine(), (0, 145, 0), "0.145.0"),
        (engines.ClaudeEngine(), (2, 1, 197), "2.1.197"),
        (engines.ClaudeEngine(), (2, 1, 220), "2.1.220"),
        (engines.ClaudeEngine(), (3, 0, 0), "3.0.0"),
    ],
)
def test_evidence_profile_accepts_minimum_and_later_versions(
    monkeypatch, engine, version, rendered,
) -> None:
    monkeypatch.setattr(engines, "_cli_version", lambda binary: version)

    assert engines.require_evidence_profile(engine) == rendered


@pytest.mark.parametrize(
    ("engine", "version", "minimum"),
    [
        (engines.CodexEngine(), (0, 144, 5), "0.144.6"),
        (engines.ClaudeEngine(), (2, 1, 196), "2.1.197"),
    ],
)
def test_evidence_profile_rejects_only_versions_below_minimum(
    monkeypatch, engine, version, minimum,
) -> None:
    monkeypatch.setattr(engines, "_cli_version", lambda binary: version)

    with pytest.raises(RuntimeError, match=rf">= {re.escape(minimum)}"):
        engines.require_evidence_profile(engine)


def test_cli_version_is_compared_numerically(monkeypatch) -> None:
    monkeypatch.setattr(
        engines.subprocess,
        "run",
        lambda *args, **kwargs: RunResult(
            returncode=0, stdout="Claude Code 2.10.3\n", stderr="",
        ),
    )

    assert engines._cli_version("claude") == (2, 10, 3)


@pytest.mark.parametrize(
    "reported",
    [
        "claude 2.1.197-alpha.1",
        "codex-cli 0.144.6-beta",
        "codex-cli 0.145.0-alpha.1",
    ],
)
def test_cli_version_rejects_prereleases(monkeypatch, reported) -> None:
    monkeypatch.setattr(
        engines.subprocess,
        "run",
        lambda *args, **kwargs: RunResult(
            returncode=0, stdout=reported, stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="does not support prerelease"):
        engines._cli_version("provider")


def test_cli_version_accepts_build_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        engines.subprocess,
        "run",
        lambda *args, **kwargs: RunResult(
            returncode=0, stdout="claude 2.1.197+native.4", stderr="",
        ),
    )

    assert engines._cli_version("claude") == (2, 1, 197)


def test_minimum_provider_cli_acceptance_binds_later_real_versions() -> None:
    artifact = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/minimum_provider_cli_acceptance_2026-08-16.json"
        ).read_text()
    )
    assert artifact["model_call_count"] == 11
    minimums = {
        "codex": engines.MIN_CODEX_VERSION,
        "claude": engines.MIN_CLAUDE_VERSION,
    }
    assert {probe["cli"] for probe in artifact["probes"]} == set(minimums)
    for probe in artifact["probes"]:
        parse = lambda value: tuple(int(part) for part in value.split("."))
        assert parse(probe["minimum_version"]) == minimums[probe["cli"]]
        assert parse(probe["tested_version"]) > minimums[probe["cli"]]
        assert probe["returncode"] == 0
        assert probe["response"] == {"status": "compatible"}
    lifecycles = {row["cli"]: row for row in artifact["primary_lifecycles"]}
    assert set(lifecycles) == set(minimums)
    assert lifecycles["claude"]["claim_counts"] == {
        "refuted": 0, "supported": 1, "unverified": 0,
    }
    assert lifecycles["codex"]["claim_counts"] == {
        "refuted": 0, "supported": 1, "unverified": 1,
    }
    assert all(row["engine_returncode"] == 0 for row in lifecycles.values())
    assert sum(
        row["claim_model_calls"] + row["structural_model_calls"]
        for row in lifecycles.values()
    ) + artifact["structured_probe_model_calls"] == artifact["model_call_count"]


def test_codex_recovered_stream_error_does_not_discard_completed_turn() -> None:
    review = engines.CodexEngine().parse_output(
        '{"type":"thread.started","thread_id":"recovered"}\n'
        '{"type":"error","message":"transient stream failure"}\n'
        '{"type":"item.completed","item":{"type":"agent_message",'
        '"text":"settled"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":10}}\n'
    )

    assert review.error is False
    assert review.text == "settled"
    assert review.failure_detail is None


def test_codex_terminal_error_remains_a_failure() -> None:
    review = engines.CodexEngine().parse_output(
        '{"type":"thread.started","thread_id":"failed"}\n'
        '{"type":"item.completed","item":{"type":"agent_message",'
        '"text":"partial"}}\n'
        '{"type":"turn.failed","error":{"message":"terminal"}}\n'
    )

    assert review.error is True
    assert review.text == "partial"
    assert review.failure_detail == "terminal"

class TestCodexArgv:
    def test_build_argv_read_only_and_model_and_effort(self) -> None:
        e = engines.get_engine("codex")
        argv = e.build_argv(cwd=Path("/repo"), model="gpt-5.6-sol", effort="high", web_search=True)
        assert argv[:2] == ["codex", "exec"]
        assert "--json" in argv
        assert "--ignore-user-config" in argv
        joined = " ".join(argv)
        assert "-s read-only" in joined
        assert "-C /repo" in joined
        assert "-m gpt-5.6-sol" in joined
        assert 'model_reasoning_effort="high"' in joined
        assert "tools.web_search=true" in joined
        assert argv[-1] == "-"  # prompt read from stdin

    def test_web_search_off_omits_flag(self) -> None:
        e = engines.get_engine("codex")
        argv = e.build_argv(cwd=Path("/repo"), model="m", effort="high", web_search=False)
        assert "tools.web_search=true" not in " ".join(argv)

    def test_resume_argv_targets_session(self) -> None:
        e = engines.get_engine("codex")
        argv = e.build_resume_argv(session_ref="abc-123", cwd=Path("/repo"), model="m", effort="high", web_search=False)
        assert argv[:3] == ["codex", "exec", "resume"]
        assert "abc-123" in argv
        assert argv[-1] == "-"
        # `codex exec resume` rejects -s and -C; they must not appear
        assert "-s" not in argv
        assert "-C" not in argv
        assert "--ignore-user-config" in argv

    def test_evidence_roles_are_explicit_on_fresh_and_resume(self) -> None:
        discovery = engines.get_engine("codex").for_role(engines.ROLE_DISCOVERY)
        fresh = discovery.build_argv(Path("/launch"), "m", "high", True)
        assert 'web_search="live"' in fresh
        assert "workspace-write" in fresh
        for feature in engines.CODEX_EXTERNAL_FEATURES:
            assert fresh.count(feature) == 1
        repository = engines.get_engine("codex").for_role(engines.ROLE_REPOSITORY)
        resumed = repository.build_resume_argv("s", Path("/launch"), "m", "high", False)
        joined = " ".join(resumed)
        assert 'web_search="disabled"' in resumed
        assert "exclude_slash_tmp=true" in joined
        assert "exclude_tmpdir_env_var=true" in joined
        assert "writable_roots=[]" in joined
        assert 'approval_policy="never"' in resumed
        binding = engines.get_engine("codex").for_role(engines.ROLE_BINDING)
        bound_resume = binding.build_resume_argv("s", Path("/launch"), "m", "high", False)
        assert 'sandbox_mode="read-only"' in bound_resume

    def test_parse_output_extracts_final_message_and_thread(self) -> None:
        e = engines.get_engine("codex")
        review = e.parse_output(CODEX_JSONL)
        assert review.text == "## What works\nNothing notable."
        assert review.session_ref == "abc-123"

    def test_parse_tolerates_garbage_lines(self) -> None:
        e = engines.get_engine("codex")
        review = e.parse_output("not json\n" + CODEX_JSONL + "trailing noise\n")
        assert review.text == "## What works\nNothing notable."


class TestClaudeArgv:
    def test_build_argv_print_json_model_effort(self) -> None:
        e = engines.get_engine("claude")
        argv = e.build_argv(cwd=Path("/repo"), model="claude-fable-5", effort="high", web_search=True)
        assert argv[0] == "claude"
        assert "-p" in argv
        joined = " ".join(argv)
        assert "--output-format json" in joined
        assert "--model claude-fable-5" in joined
        assert "--effort high" in joined

    def test_allowlist_is_read_only(self) -> None:
        e = engines.get_engine("claude")
        argv = e.build_argv(cwd=Path("/repo"), model="m", effort="high", web_search=True)
        allowed = argv[argv.index("--allowedTools") + 1]
        assert "Read" in allowed
        assert "Bash(git diff:*)" in allowed
        assert "WebSearch" in allowed
        # write tools must be denied
        disallowed = argv[argv.index("--disallowedTools") + 1]
        assert "Write" in disallowed
        assert "Edit" in disallowed

    def test_web_search_off_drops_web_tools(self) -> None:
        e = engines.get_engine("claude")
        argv = e.build_argv(cwd=Path("/repo"), model="m", effort="high", web_search=False)
        allowed = argv[argv.index("--allowedTools") + 1]
        assert "WebSearch" not in allowed

    def test_loads_no_settings_sources(self) -> None:
        # Hermetic read-only: the reviewed repo's (or the user's) own
        # .claude settings must NOT widen the reviewer's permissions. Loading
        # zero settings sources makes paranoia's --allowedTools the sole
        # authority. Empty value = load none (verified against the real CLI).
        e = engines.get_engine("claude")
        argv = e.build_argv(cwd=Path("/repo"), model="m", effort="high", web_search=True)
        i = argv.index("--setting-sources")
        assert argv[i + 1] == ""

    def test_resume_also_loads_no_settings_sources(self) -> None:
        e = engines.get_engine("claude")
        argv = e.build_resume_argv(session_ref="s", cwd=Path("/repo"), model="m", effort="high", web_search=False)
        i = argv.index("--setting-sources")
        assert argv[i + 1] == ""

    def test_resume_argv_targets_session(self) -> None:
        e = engines.get_engine("claude")
        argv = e.build_resume_argv(session_ref="sess-xyz", cwd=Path("/repo"), model="m", effort="high", web_search=False)
        assert "--resume" in argv
        assert "sess-xyz" in argv

    def test_evidence_role_tool_sets_repeat_on_resume(self) -> None:
        expected = {
            engines.ROLE_DISCOVERY: "WebSearch",
            engines.ROLE_REPOSITORY: "Read,Grep,Glob",
            engines.ROLE_BINDING: "",
            engines.ROLE_TEXT: "",
        }
        for role, tools in expected.items():
            engine = engines.get_engine("claude").for_role(role)
            calls = (
                engine.build_argv(Path("/launch"), "m", "high", role == engines.ROLE_DISCOVERY),
                engine.build_resume_argv(
                    "s", Path("/launch"), "m", "high", role == engines.ROLE_DISCOVERY,
                ),
            )
            for argv in calls:
                assert argv[argv.index("--tools") + 1] == tools
                assert argv[argv.index("--allowedTools") + 1] == tools
                assert "--safe-mode" in argv and "--strict-mcp-config" in argv
        discovery_tools = expected[engines.ROLE_DISCOVERY]
        assert "WebFetch" not in discovery_tools
        assert "Read" not in discovery_tools

    def test_required_evidence_tool_denial_is_a_capability_failure(self) -> None:
        discovery = engines.get_engine("claude").for_role(engines.ROLE_DISCOVERY)
        payload = json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "result": "fallback claims", "session_id": "s",
            "permission_denials": [{"tool_name": "WebSearch"}],
        })

        review = discovery.parse_output(payload)

        assert review.error is True
        assert review.text == "fallback claims"
        assert review.failure_detail == "required evidence tool permission denied: WebSearch"

    def test_tool_less_role_denial_remains_expected_enforcement(self) -> None:
        binding = engines.get_engine("claude").for_role(engines.ROLE_BINDING)
        payload = json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "result": "bound without tools", "session_id": "s",
            "permission_denials": [{"tool_name": "WebSearch"}],
        })

        review = binding.parse_output(payload)

        assert review.error is False
        assert review.failure_detail is None

    def test_parse_output_extracts_result_and_session(self) -> None:
        e = engines.get_engine("claude")
        review = e.parse_output(CLAUDE_JSON)
        assert review.text == "## What works\nNothing notable."
        assert review.session_ref == "sess-xyz"

    def test_parse_non_json_falls_back_to_raw(self) -> None:
        e = engines.get_engine("claude")
        review = e.parse_output("plain text review, no json")
        assert "plain text" in review.text
        assert review.session_ref is None


class TestRunWithInjectedRunner:
    def test_run_pipes_prompt_to_stdin_and_parses(self) -> None:
        e = engines.get_engine("codex")
        captured = {}

        def fake_runner(argv, stdin_text, cwd, timeout):
            captured["argv"] = argv
            captured["stdin"] = stdin_text
            captured["cwd"] = cwd
            return RunResult(returncode=0, stdout=CODEX_JSONL, stderr="")

        review = e.run(
            prompt="REVIEW THIS", cwd=Path("/repo"), model="m", effort="high",
            web_search=False, runner=fake_runner,
        )
        assert captured["stdin"] == "REVIEW THIS"
        assert captured["cwd"] == Path("/repo")
        assert review.text == "## What works\nNothing notable."

    def test_run_measures_duration_when_provider_omits_it(self, monkeypatch) -> None:
        e = engines.get_engine("codex")
        ticks = iter((10.0, 10.125))
        monkeypatch.setattr(engines.time, "monotonic", lambda: next(ticks))

        review = e.run(
            prompt="x", cwd=Path("/repo"), model="m", effort="high",
            web_search=False,
            runner=lambda *args, **kwargs: RunResult(
                returncode=0, stdout=CODEX_JSONL, stderr="",
            ),
        )

        assert review.duration_ms == 125

    def test_run_surfaces_nonzero_exit_as_error_text(self) -> None:
        e = engines.get_engine("claude")

        def fake_runner(argv, stdin_text, cwd, timeout):
            return RunResult(returncode=1, stdout="", stderr="auth failed: not logged in")

        review = e.run(
            prompt="x", cwd=Path("/repo"), model="m", effort="high",
            web_search=False, runner=fake_runner,
        )
        assert "error" in review.text.lower()
        assert "auth failed" in review.text
        assert review.failure_detail == "auth failed: not logged in"

    def test_process_failure_detail_is_not_masked_by_partial_output(self) -> None:
        e = engines.get_engine("codex")
        partial = (
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"partial reviewer output"}}\n'
        )

        def fake_runner(argv, stdin_text, cwd, timeout):
            return RunResult(
                returncode=9, stdout=partial,
                stderr="terminal process diagnostic\n",
            )

        review = e.run(
            prompt="x", cwd=Path("/repo"), model="m", effort="high",
            web_search=False, runner=fake_runner,
        )
        assert review.error is True
        assert review.text == "partial reviewer output"
        assert review.failure_detail == "terminal process diagnostic\n"
        assert review.stderr == "terminal process diagnostic\n"

    def test_structured_failure_detail_is_not_overwritten_by_stderr(self) -> None:
        e = engines.get_engine("codex")
        payload = (
            '{"type":"turn.failed","error":{"message":"structured provider failure"}}\n'
        )

        def fake_runner(argv, stdin_text, cwd, timeout):
            return RunResult(returncode=9, stdout=payload, stderr="process stderr\n")

        review = e.run(
            prompt="x", cwd=Path("/repo"), model="m", effort="high",
            web_search=False, runner=fake_runner,
        )
        assert review.error is True
        assert review.failure_detail == "structured provider failure"
        assert review.stderr == "process stderr\n"

    def test_resume_uses_resume_argv(self) -> None:
        e = engines.get_engine("claude")
        captured = {}

        def fake_runner(argv, stdin_text, cwd, timeout):
            captured["argv"] = argv
            return RunResult(returncode=0, stdout=CLAUDE_JSON, stderr="")

        e.resume(
            session_ref="sess-xyz", prompt="rebuttal", cwd=Path("/repo"),
            model="m", effort="high", web_search=False, runner=fake_runner,
        )
        assert "--resume" in captured["argv"]

    @pytest.mark.parametrize("resumed", [False, True])
    def test_codex_structured_schema_is_readable_for_call_then_removed(self, resumed) -> None:
        engine = engines.CodexEngine()
        captured = {}

        def fake_runner(argv, stdin_text, cwd, timeout):
            schema_path = Path(argv[argv.index("--output-schema") + 1])
            captured["path"] = schema_path
            captured["schema"] = json.loads(schema_path.read_text())
            captured["mode"] = schema_path.stat().st_mode & 0o777
            return RunResult(
                returncode=0,
                stdout=(
                    '{"type":"thread.started","thread_id":"structured"}\n'
                    '{"type":"item.completed","item":{"type":"agent_message",'
                    '"text":"{\\"answer\\":\\"ok\\"}"}}\n'
                    '{"type":"turn.completed","usage":{}}\n'
                ),
                stderr="",
            )

        kwargs = dict(
            prompt="respond", cwd=Path("/repo"), model="m", effort="low",
            web_search=False, runner=fake_runner, response_schema=STRUCTURED_SCHEMA,
        )
        review = (
            engine.resume(session_ref="structured", **kwargs)
            if resumed else engine.run(**kwargs)
        )
        assert json.loads(review.text) == {"answer": "ok"}
        assert captured["schema"] == STRUCTURED_SCHEMA
        assert captured["mode"] == 0o400
        assert not captured["path"].exists()

    @pytest.mark.parametrize("resumed", [False, True])
    def test_claude_structured_schema_precedes_variadic_tool_flags(self, resumed) -> None:
        engine = engines.ClaudeEngine()
        captured = {}

        def fake_runner(argv, stdin_text, cwd, timeout):
            captured["argv"] = argv
            return RunResult(
                returncode=0,
                stdout=json.dumps({
                    "type": "result", "subtype": "success", "is_error": False,
                    "result": "prose is not authoritative",
                    "structured_output": {"answer": "ok"}, "session_id": "structured",
                }),
                stderr="",
            )

        kwargs = dict(
            prompt="respond", cwd=Path("/repo"), model="m", effort="low",
            web_search=False, runner=fake_runner, response_schema=STRUCTURED_SCHEMA,
        )
        review = (
            engine.resume(session_ref="structured", **kwargs)
            if resumed else engine.run(**kwargs)
        )
        argv = captured["argv"]
        assert argv.index("--json-schema") < argv.index("--allowedTools")
        assert json.loads(argv[argv.index("--json-schema") + 1]) == STRUCTURED_SCHEMA
        assert json.loads(review.text) == {"answer": "ok"}

    @pytest.mark.parametrize("resumed", [False, True])
    @pytest.mark.parametrize(
        "payload",
        [
            {"result": '{"answer":"prose"}'},
            {"result": "fallback", "structured_output": ["not", "an", "object"]},
        ],
    )
    def test_claude_schema_call_fails_closed_without_structured_object(
        self, resumed, payload,
    ) -> None:
        engine = engines.ClaudeEngine()

        def fake_runner(argv, stdin_text, cwd, timeout):
            return RunResult(
                returncode=0,
                stdout=json.dumps({
                    "type": "result", "subtype": "success", "is_error": False,
                    "session_id": "structured", **payload,
                }),
                stderr="",
            )

        kwargs = dict(
            prompt="respond", cwd=Path("/repo"), model="m", effort="low",
            web_search=False, runner=fake_runner, response_schema=STRUCTURED_SCHEMA,
        )
        review = (
            engine.resume(session_ref="structured", **kwargs)
            if resumed else engine.run(**kwargs)
        )
        assert review.error
        assert review.failure_detail == (
            "claude did not return the requested structured_output object"
        )

    def test_claude_preserves_nested_duplicate_keys_for_local_rejection(self) -> None:
        review = engines.ClaudeEngine().parse_output(
            '{"is_error":false,"session_id":"s","structured_output":'
            '{"class_actions":{"class-a":{"kind":"close"},'
            '"class-a":{"kind":"reopen"}}}}'
        )
        assert not review.error
        assert review.session_ref == "s"
        assert review.text.count('"class-a"') == 2

    def test_claude_rejects_duplicate_structured_output_envelope_keys(self) -> None:
        review = engines.ClaudeEngine().parse_output(
            '{"is_error":false,"structured_output":{"answer":"first"},'
            '"structured_output":{"answer":"second"}}'
        )
        assert review.error
        assert review.failure_detail == (
            "claude returned duplicate structured_output envelope keys"
        )


def test_every_claude_deny_rule_is_a_tool_the_cli_knows():
    """An unknown deny rule contaminates the engine's structured output.

    Claude Code rejects a rule naming no known tool with

        Permission deny rule "X" matches no known tool — check for typos.

    on the same stream the review is read from, so the reply no longer parses and
    EVERY review on this engine fails. `MultiEdit` was removed from Claude Code
    (absent in 2.1.197) and had to be dropped for that reason.

    This pins the names rather than the absence of one, because the failure is
    not specific to `MultiEdit`: any future rule naming a retired or misspelled
    tool breaks the engine the same way. The allowlist is what actually bounds
    the reviewer — a tool that is not allowlisted is auto-denied in `-p` mode —
    so this list is belt-and-braces and shrinking it costs nothing.
    """
    assert engines.CLAUDE_DENY_TOOLS == ["Write", "Edit", "NotebookEdit"]
    assert "MultiEdit" not in engines.CLAUDE_DENY_TOOLS
