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
        discovery = engines.get_engine("claude").for_role(engines.ROLE_DISCOVERY)
        fresh = discovery.build_argv(Path("/launch"), "m", "high", True)
        assert fresh[fresh.index("--tools") + 1] == "WebSearch"
        assert "--safe-mode" in fresh and "--strict-mcp-config" in fresh
        binding = engines.get_engine("claude").for_role(engines.ROLE_BINDING)
        resumed = binding.build_resume_argv("s", Path("/launch"), "m", "high", False)
        assert resumed[resumed.index("--tools") + 1] == ""
        repository = engines.get_engine("claude").for_role(engines.ROLE_REPOSITORY)
        argv = repository.build_argv(Path("/launch"), "m", "high", False)
        assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"

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
