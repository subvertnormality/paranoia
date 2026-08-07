from pathlib import Path

import pytest

from paranoia_local import server
from paranoia_local.engines import Review


class SpyEngine:
    default_model = "spy-model"

    def __init__(self, name: str = "codex") -> None:
        self.name = name

    def run(self, prompt, cwd, model, effort, web_search, runner=None, timeout=None):
        return Review(text=f"REVIEW via {self.name}", session_ref="s1", raw="")

    def resume(self, session_ref, prompt, cwd, model, effort, web_search, runner=None, timeout=None):
        return Review(text="REBUT via " + self.name, session_ref=session_ref, raw="")


@pytest.fixture
def spy_get_engine(monkeypatch):
    requested: list[str] = []

    def fake_get_engine(name: str) -> SpyEngine:
        requested.append(name)
        if name not in ("codex", "claude"):
            raise ValueError(f"unknown engine {name!r}")
        return SpyEngine(name)

    monkeypatch.setattr(server, "get_engine", fake_get_engine)
    return requested


class TestToolListing:
    def test_all_five_tools_present(self) -> None:
        names = {t.name for t in server.TOOLS}
        assert names == {"critique_branch", "critique_plan", "query", "rebut", "arbitrate"}

    def test_arbitrate_requires_its_four_inputs(self) -> None:
        tool = next(t for t in server.TOOLS if t.name == "arbitrate")
        assert set(tool.inputSchema["required"]) == {
            "repo_path", "decision", "options", "stakes"
        }

    def test_arbitrate_exposes_no_single_engine_override(self) -> None:
        """A single engine/model override would degrade arbitration to one vendor, or
        send one vendor's model name to the other CLI."""
        tool = next(t for t in server.TOOLS if t.name == "arbitrate")
        props = tool.inputSchema["properties"]
        assert "engine" not in props and "model" not in props
        assert set(props["models"]["properties"]) == {"codex", "claude"}

    def test_critique_branch_requires_repo_path(self) -> None:
        tool = next(t for t in server.TOOLS if t.name == "critique_branch")
        assert "repo_path" in tool.inputSchema["required"]

    def test_critique_plan_schema_caps_inline_text_and_path_length(self) -> None:
        tool = next(t for t in server.TOOLS if t.name == "critique_plan")
        props = tool.inputSchema["properties"]
        assert props["plan_text"]["maxLength"] == server.handlers.MAX_PLAN_BYTES
        assert props["plan_text"]["minLength"] == 1
        assert props["plan_path"]["maxLength"] == 4096

    def test_claim_verification_rolls_out_off_then_diagnostic_then_blocking(self) -> None:
        tool = next(t for t in server.TOOLS if t.name == "critique_plan")
        claim_mode = tool.inputSchema["properties"]["claim_verification"]
        assert claim_mode["enum"] == ["off", "diagnostic", "blocking"]
        assert claim_mode["default"] == "diagnostic"
        source_policy = tool.inputSchema["properties"]["external_source_policy"]
        assert source_policy["maxItems"] == 50
        assert source_policy["items"]["properties"]["source_class"]["enum"] == [
            "primary", "authoritative", "secondary", "ugc",
        ]

    def test_rebut_requires_session_and_rebuttal(self) -> None:
        tool = next(t for t in server.TOOLS if t.name == "rebut")
        req = tool.inputSchema["required"]
        assert "session_ref" in req and "rebuttal" in req


class TestDispatch:
    def test_routes_query(self, repo: Path, tmp_path: Path, spy_get_engine) -> None:
        out = server.dispatch(
            "query",
            {"question": "is it safe?", "repo_path": str(repo)},
            default_engine_name="codex", log_dir=tmp_path, now=lambda: "t",
        )
        assert "REVIEW via codex" in out

    def test_uses_default_engine(self, repo: Path, tmp_path: Path, spy_get_engine) -> None:
        server.dispatch(
            "query", {"question": "q", "repo_path": str(repo)},
            default_engine_name="claude", log_dir=tmp_path, now=lambda: "t",
        )
        assert spy_get_engine == ["claude"]

    def test_per_call_engine_override(self, repo: Path, tmp_path: Path, spy_get_engine) -> None:
        out = server.dispatch(
            "query", {"question": "q", "repo_path": str(repo), "engine": "claude"},
            default_engine_name="codex", log_dir=tmp_path, now=lambda: "t",
        )
        assert spy_get_engine == ["claude"]
        assert "REVIEW via claude" in out

    def test_unknown_tool_returns_error_text(self, tmp_path: Path, spy_get_engine) -> None:
        out = server.dispatch(
            "critique_everything", {}, default_engine_name="codex",
            log_dir=tmp_path, now=lambda: "t",
        )
        assert "[paranoia-local error]" in out
        assert "unknown tool" in out.lower()

    def test_handler_valueerror_becomes_error_text(self, tmp_path: Path, spy_get_engine) -> None:
        # query with no question → handler raises ValueError → dispatch returns error text
        out = server.dispatch(
            "query", {}, default_engine_name="codex", log_dir=tmp_path, now=lambda: "t",
        )
        assert "[paranoia-local error]" in out

    def test_bad_engine_name_returns_error_text(self, repo: Path, tmp_path: Path, spy_get_engine) -> None:
        out = server.dispatch(
            "query", {"question": "q", "repo_path": str(repo), "engine": "gemini"},
            default_engine_name="codex", log_dir=tmp_path, now=lambda: "t",
        )
        assert "[paranoia-local error]" in out


class TestBuildServer:
    def test_builds_named_server(self) -> None:
        srv = server.build_server(default_engine_name="codex")
        assert srv.name == "paranoia-local"
