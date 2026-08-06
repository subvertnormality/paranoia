from __future__ import annotations

from pathlib import Path

import pytest

from paranoia_local.engines import ClaudeEngine, CodexEngine, ToollessUnavailable


def test_claude_toolless_profile_has_empty_allowlist_and_forces_web_off(tmp_path: Path) -> None:
    argv = ClaudeEngine().build_toolless_argv(tmp_path, "claude", "high")
    allowed = argv[argv.index("--allowedTools") + 1]
    assert allowed == ""
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
