from __future__ import annotations

from pathlib import Path

import pytest

from paranoia_local.engines import ClaudeEngine, CodexEngine, ToollessUnavailable
from paranoia_local.runner import RunResult


def test_claude_toolless_profile_has_empty_allowlist_and_forces_web_off(tmp_path: Path) -> None:
    argv = ClaudeEngine().build_toolless_argv(tmp_path, "claude", "high")
    allowed = argv[argv.index("--allowedTools") + 1]
    assert allowed == ""
    assert argv[argv.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    denied = argv[argv.index("--disallowedTools") + 1]
    assert "WebSearch" in denied and "WebFetch" in denied
    assert "--setting-sources" in argv


def test_codex_toolless_profile_exposes_native_binary_not_shell_or_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = tmp_path / "codex-native"
    native.write_bytes(b"binary")
    auth = tmp_path / "auth.json"
    auth.write_text("{}")
    monkeypatch.setattr(CodexEngine, "_native_binary", lambda self: native)
    monkeypatch.setattr(CodexEngine, "_auth_file", lambda self: auth)
    monkeypatch.setattr(CodexEngine, "_audit_toolless_binary", lambda self: None)
    argv = CodexEngine().build_toolless_argv(tmp_path / "scratch", "gpt", "high")
    joined = " ".join(argv)
    assert argv[0].endswith("bwrap")
    assert "--ro-bind " + str(native) + " /codex" in joined
    assert " /bin " not in joined and " /usr/bin " not in joined
    assert str(tmp_path / "scratch") not in joined, "scratch is an inner tmpfs, not host bind"
    assert "tools.web_search=false" in joined
    assert "--ignore-user-config" in argv and "--ephemeral" in argv


def test_codex_toolless_profile_fails_closed_without_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = tmp_path / "codex-native"
    native.write_bytes(b"binary")
    monkeypatch.setattr(CodexEngine, "_native_binary", lambda self: native)
    monkeypatch.setattr(CodexEngine, "_auth_file", lambda self: tmp_path / "missing")
    with pytest.raises(ToollessUnavailable, match="auth"):
        CodexEngine().build_toolless_argv(tmp_path, "gpt", "high")


def test_toolless_run_never_exposes_ephemeral_codex_thread_for_rebut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = CodexEngine()
    monkeypatch.setattr(engine, "build_toolless_argv", lambda *_args: ["codex"])

    def runner(*_args):
        return RunResult(
            0,
            '{"type":"thread.started","thread_id":"ephemeral"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}',
            "",
        )

    review = engine.run_toolless("prompt", "gpt", "high", runner=runner)
    assert review.text == "done"
    assert review.session_ref is None


def test_codex_toolless_versions_are_an_exact_audited_set() -> None:
    assert CodexEngine.TOOLLESS_VERSIONS == {"0.144.6", "0.146.0-alpha.3.1"}


def test_toolless_preflight_rejects_a_missing_cli_before_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("paranoia_local.engines.shutil.which", lambda _name: None)
    with pytest.raises(ToollessUnavailable, match="not installed"):
        ClaudeEngine().preflight_toolless("claude", "high")
