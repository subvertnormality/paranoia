"""Engine abstraction — each engine drives a local coding-agent CLI in a
headless, read-only mode over the user's subscription.

For ordinary code/query work the CLI *is* the reviewer: it has full read access
to the repo at `cwd` and decides what to open. Claim-verification roles instead
use ``run_toolless``: an enforceable empty-tool/filesystem profile whose only
inputs are server packets. This module builds both profiles, feeds stdin, and
parses the final message. Ordinary profiles retain resumable session references;
fresh toolless profiles deliberately suppress them.

`build_argv` / `build_resume_argv` / `parse_output` are pure and unit-tested.
The impure subprocess call is injected via `runner` (see runner.py).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .runner import RunResult, run_capture, run_streaming

Runner = Callable[[list[str], str, Path, int], RunResult]

# Longest progress message forwarded to the client (spinner-line sized).
_PROGRESS_MSG_MAX = 100


class ToollessUnavailable(RuntimeError):
    """The selected engine cannot enforce a command- and repository-free role."""


@dataclass(frozen=True)
class Review:
    """The reviewer's final message plus a token to resume the same session, and enough
    process/usage metadata to detect real failures and reproduce a cost decision."""

    text: str
    session_ref: str | None
    raw: str
    returncode: int = 0
    error: bool = False
    usage: dict | None = None
    duration_ms: int | None = None


class Engine(ABC):
    name: str
    default_model: str
    # argv[0] — needed on its own so a preflight can check the CLI is installed
    # without building a whole command line.
    binary: str

    # Capability profile for roles that must not investigate a repository (the
    # arbitration cleaner and attester). Enforced where the engine layer can
    # enforce it; see the subclass notes.
    text_only: bool = False

    @abstractmethod
    def build_argv(self, cwd: Path, model: str, effort: str, web_search: bool) -> list[str]:
        ...

    @abstractmethod
    def build_resume_argv(
        self, session_ref: str, cwd: Path, model: str, effort: str, web_search: bool
    ) -> list[str]:
        ...

    @abstractmethod
    def parse_output(self, stdout: str) -> Review:
        ...

    def progress_from_line(self, line: str) -> str | None:
        """Translate one raw stdout line into a short human progress message, or
        ``None`` for lines that carry no user-facing signal. Engines whose CLI
        emits a single final blob (no streaming) simply inherit this ``None``."""
        return None

    def run(
        self,
        prompt: str,
        cwd: Path,
        model: str,
        effort: str,
        web_search: bool,
        runner: Runner | None = None,
        timeout: int | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> Review:
        argv = self.build_argv(cwd, model, effort, web_search)
        return self._execute(argv, prompt, cwd, runner, timeout, on_progress)

    def build_toolless_argv(self, cwd: Path, model: str, effort: str) -> list[str]:
        raise ToollessUnavailable(f"{self.name} has no enforceable toolless profile")

    def build_discovery_argv(self, cwd: Path, model: str, effort: str) -> list[str]:
        raise ToollessUnavailable(f"{self.name} has no enforceable web-discovery profile")

    def preflight_toolless(self, model: str, effort: str) -> None:
        """Validate the empty-capability boundary before caller state is acquired."""
        if not shutil.which(self.binary):
            raise ToollessUnavailable(f"{self.binary} CLI is not installed")
        try:
            self.build_toolless_argv(Path(tempfile.gettempdir()), model, effort)
        except ToollessUnavailable:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise ToollessUnavailable(
                f"{self.name} toolless capability preflight failed: {exc}"
            ) from exc

    def preflight_discovery(self, model: str, effort: str) -> None:
        """Validate the search-only capability boundary before a review starts."""
        if not shutil.which(self.binary):
            raise ToollessUnavailable(f"{self.binary} CLI is not installed")
        try:
            self.build_discovery_argv(Path(tempfile.gettempdir()), model, effort)
        except ToollessUnavailable:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise ToollessUnavailable(
                f"{self.name} web-discovery capability preflight failed: {exc}"
            ) from exc

    def run_toolless(
        self,
        prompt: str,
        model: str,
        effort: str,
        runner: Runner | None = None,
        timeout: int | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> Review:
        """Run in a fresh empty directory with native web forcibly disabled.

        Subclasses must make ``build_toolless_argv`` an actual capability boundary;
        prompt instructions or the ordinary read-only repository sandbox do not qualify.
        """
        with tempfile.TemporaryDirectory(prefix=f"paranoia-{self.name}-tool-less-") as raw:
            cwd = Path(raw)
            argv = self.build_toolless_argv(cwd, model, effort)
            review = self._execute(argv, prompt, cwd, runner, timeout, on_progress)
            # These roles are intentionally fresh and, for Codex, explicitly ephemeral.
            # Never expose a token that ordinary `rebut` cannot safely resume.
            return replace(review, session_ref=None)

    def run_discovery(
        self,
        prompt: str,
        model: str,
        effort: str,
        runner: Runner | None = None,
        timeout: int | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> Review:
        """Run a fresh role with native search as its only external capability."""
        with tempfile.TemporaryDirectory(prefix=f"paranoia-{self.name}-web-only-") as raw:
            cwd = Path(raw)
            argv = self.build_discovery_argv(cwd, model, effort)
            review = self._execute(argv, prompt, cwd, runner, timeout, on_progress)
            return replace(review, session_ref=None)

    def resume(
        self,
        session_ref: str,
        prompt: str,
        cwd: Path,
        model: str,
        effort: str,
        web_search: bool,
        runner: Runner | None = None,
        timeout: int | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> Review:
        argv = self.build_resume_argv(session_ref, cwd, model, effort, web_search)
        return self._execute(argv, prompt, cwd, runner, timeout, on_progress)

    def _execute(
        self,
        argv: list[str],
        prompt: str,
        cwd: Path,
        runner: Runner | None,
        timeout: int | None,
        on_progress: Callable[[str], None] | None = None,
    ) -> Review:
        from .runner import DEFAULT_TIMEOUT_SEC

        if on_progress is not None:
            def _on_line(line: str) -> None:
                msg = self.progress_from_line(line)
                if msg:
                    on_progress(msg)

            streaming = runner or run_streaming
            result = streaming(
                argv, prompt, cwd, timeout or DEFAULT_TIMEOUT_SEC, on_line=_on_line
            )
        else:
            result = (runner or run_capture)(argv, prompt, cwd, timeout or DEFAULT_TIMEOUT_SEC)
        review = self.parse_output(result.stdout)
        # A review is failed if the process exited non-zero OR the engine reported an
        # in-band error (e.g. Claude's is_error) — the latter can occur with rc 0 and
        # non-empty stdout, which the old "rc != 0 AND empty stdout" gate silently
        # swallowed, defeating any downstream fallback.
        failed = result.returncode != 0 or review.error
        if failed and not (review.text or "").strip():
            return Review(
                text=(
                    f"[paranoia-local error] {self.name} exited {result.returncode}: "
                    f"{result.stderr.strip()[:2000]}"
                ),
                session_ref=review.session_ref,
                raw=result.stderr or result.stdout,
                returncode=result.returncode,
                error=True,
            )
        return replace(review, returncode=result.returncode, error=failed)


class CodexEngine(Engine):
    name = "codex"
    default_model = "gpt-5.6-sol"
    binary = "codex"

    TOOLLESS_VERSIONS = frozenset({"0.144.6", "0.146.0-alpha.3.1"})
    ISOLATED_DISABLED_FEATURES = (
        "shell_tool", "unified_exec", "multi_agent", "multi_agent_v2",
        "apps", "browser_use", "computer_use", "code_mode", "code_mode_host",
        "image_generation", "goals", "workspace_dependencies", "auth_elicitation",
        "in_app_browser", "plugins", "plugin_sharing", "remote_plugin",
        "skill_mcp_dependency_install", "tool_call_mcp_elicitation", "tool_suggest",
    )

    @staticmethod
    def _is_elf(path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                return handle.read(4) == b"\x7fELF"
        except OSError:
            return False

    def _native_binary(self) -> Path:
        launcher = shutil.which(self.binary)
        if not launcher:
            raise ToollessUnavailable("codex CLI is not installed")
        path = Path(launcher).resolve()
        if self._is_elf(path):
            return path
        local = Path(launcher).resolve().parents[3] if len(Path(launcher).resolve().parents) >= 4 else None
        candidates = []
        # npm layout: ~/.local/bin/codex -> ../lib/node_modules/@openai/codex/bin/codex.js
        prefix = Path(launcher).parent.parent
        candidates.append(
            prefix / "lib/node_modules/@openai/codex/node_modules/@openai/"
            "codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"
        )
        if local:
            candidates.append(local / "vendor/x86_64-unknown-linux-musl/bin/codex")
        for candidate in candidates:
            if candidate.is_file() and self._is_elf(candidate):
                return candidate
        raise ToollessUnavailable("could not locate the native Codex binary for isolation")

    def _auth_file(self) -> Path:
        root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        return root / "auth.json"

    @staticmethod
    def _audit_toolless_binary(native: Path) -> None:
        result = subprocess.run(
            [str(native), "--version"], capture_output=True, text=True, timeout=10,
        )
        version = result.stdout.strip().removeprefix("codex-cli ")
        if result.returncode or version not in CodexEngine.TOOLLESS_VERSIONS:
            raise ToollessUnavailable(
                f"Codex {version or 'unknown'} has no audited empty-tool profile"
            )
        features = subprocess.run(
            [str(native), "features", "list"], capture_output=True, text=True, timeout=10,
        )
        advertised = {
            line.split()[0] for line in features.stdout.splitlines() if line.split()
        }
        missing = sorted(set(CodexEngine.ISOLATED_DISABLED_FEATURES) - advertised)
        if features.returncode or missing:
            detail = ", ".join(missing) if missing else f"exit {features.returncode}"
            raise ToollessUnavailable(
                f"Codex isolated profile has unsupported feature controls ({detail})"
            )

    def _build_isolated_argv(
        self, cwd: Path, model: str, effort: str, *, discovery: bool,
    ) -> list[str]:
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise ToollessUnavailable("bwrap is required for isolated Codex roles")
        native, auth = self._native_binary(), self._auth_file()
        if not auth.is_file():
            raise ToollessUnavailable("Codex auth file is unavailable for isolated role")
        type(self)._audit_toolless_binary(native)
        argv = [
            bwrap, "--die-with-parent", "--new-session", "--unshare-all", "--share-net",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--dir", "/work", "--chdir", "/work",
            "--dir", "/etc",
            "--dir", "/home", "--dir", "/home/codex", "--dir", "/home/codex/.codex",
            "--ro-bind", str(auth), "/home/codex/.codex/auth.json",
            "--ro-bind", str(native), "/codex",
            "--setenv", "HOME", "/home/codex",
            "--setenv", "CODEX_HOME", "/home/codex/.codex",
            "--setenv", "PATH", "/no-tools",
        ]
        for directory in ("/etc/ssl", "/etc/ssl/certs"):
            if Path(directory).is_dir():
                argv += ["--dir", directory]
        for source in ("/etc/ssl/certs", "/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf"):
            if Path(source).exists():
                argv += ["--ro-bind", source, source]
        codex_command = ["/codex"]
        if discovery:
            # The root --search flag selects live (not cached) native web search.
            codex_command.append("--search")
        codex_command += [
            "exec", "--json", "--ephemeral", "--ignore-user-config",
            "--strict-config",
            "--skip-git-repo-check", "-s", "danger-full-access", "-C", "/work",
            "-m", model, "-c", f'model_reasoning_effort="{effort}"',
            "-c", f"tools.web_search={'true' if discovery else 'false'}",
        ]
        for feature in self.ISOLATED_DISABLED_FEATURES:
            codex_command += ["--disable", feature]
        codex_command.append("-")
        argv += ["--", *codex_command]
        return argv

    def build_toolless_argv(self, cwd: Path, model: str, effort: str) -> list[str]:
        return self._build_isolated_argv(cwd, model, effort, discovery=False)

    def build_discovery_argv(self, cwd: Path, model: str, effort: str) -> list[str]:
        return self._build_isolated_argv(cwd, model, effort, discovery=True)

    def build_argv(self, cwd: Path, model: str, effort: str, web_search: bool) -> list[str]:
        argv = [
            "codex", "exec",
            "--json",
            "--skip-git-repo-check",
            "-s", "read-only",
            "-C", str(cwd),
            "-m", model,
            "-c", f'model_reasoning_effort="{effort}"',
        ]
        if web_search:
            argv += ["-c", "tools.web_search=true"]
        argv.append("-")  # read prompt from stdin
        return argv

    def build_resume_argv(
        self, session_ref: str, cwd: Path, model: str, effort: str, web_search: bool
    ) -> list[str]:
        # `codex exec resume` does NOT accept -s/-C: a resumed session inherits
        # its original sandbox (read-only) and cwd. We pass -C nowhere and rely
        # on the process cwd (set by the runner). --skip-git-repo-check keeps it
        # working even if the original cwd (an isolated worktree) is gone.
        argv = [
            "codex", "exec", "resume", session_ref,
            "--json",
            "--skip-git-repo-check",
            "-m", model,
            "-c", f'model_reasoning_effort="{effort}"',
        ]
        if web_search:
            argv += ["-c", "tools.web_search=true"]
        argv.append("-")
        return argv

    def progress_from_line(self, line: str) -> str | None:
        line = line.strip()
        if not line:
            return None
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None
        if event.get("type") == "thread.started":
            return "reviewer session started"
        item = event.get("item")
        if not isinstance(item, dict):
            return None
        kind = item.get("type")
        if event.get("type") == "item.started" and kind == "command_execution":
            command = str(item.get("command", ""))
            return f"running: {command}"[:_PROGRESS_MSG_MAX]
        if event.get("type") == "item.started" and kind == "mcp_tool_call":
            return f"tool call: {item.get('server')}.{item.get('tool')}"[:_PROGRESS_MSG_MAX]
        if event.get("type") == "item.completed" and kind == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                return " ".join(text.split())[:_PROGRESS_MSG_MAX]
        return None

    def parse_output(self, stdout: str) -> Review:
        thread_id: str | None = None
        last_message: str | None = None
        usage: dict | None = None
        error = False
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            etype = event.get("type")
            if etype == "thread.started":
                thread_id = event.get("thread_id") or thread_id
            if etype == "error":
                error = True
            if etype == "turn.completed":
                u = event.get("usage")
                if isinstance(u, dict):
                    usage = u
            item = event.get("item")
            if isinstance(item, dict):
                if item.get("type") == "agent_message":
                    text = item.get("text")
                    if isinstance(text, str):
                        last_message = text
                elif item.get("type") == "error":
                    error = True
        return Review(
            text=last_message or "", session_ref=thread_id, raw=stdout, error=error, usage=usage
        )


# Read-only tool allowlist for the Claude engine. In `-p` mode a tool that
# needs permission and isn't allowlisted is auto-denied (no human to prompt),
# so this is the reviewer's whole capability surface.
CLAUDE_RO_TOOLS = [
    "Read", "Grep", "Glob", "LS", "NotebookRead", "TodoWrite",
    "Bash(git log:*)", "Bash(git diff:*)", "Bash(git show:*)",
    "Bash(git status:*)", "Bash(git blame:*)", "Bash(git ls-files:*)",
    "Bash(git rev-parse:*)", "Bash(git cat-file:*)", "Bash(git shortlog:*)",
]
CLAUDE_WEB_TOOLS = ["WebSearch", "WebFetch"]
CLAUDE_DENY_TOOLS = ["Write", "Edit", "MultiEdit", "NotebookEdit"]


class ClaudeEngine(Engine):
    name = "claude"
    default_model = "claude-fable-5"
    binary = "claude"

    TOOLLESS_REQUIRED_FLAGS = frozenset({
        "--output-format", "--model", "--effort", "--permission-mode",
        "--setting-sources", "--allowedTools", "--tools", "--strict-mcp-config",
        "--mcp-config", "--disallowedTools",
    })
    DISCOVERY_REQUIRED_FLAGS = TOOLLESS_REQUIRED_FLAGS | {"--max-turns"}

    def _preflight_flags(
        self, required: frozenset[str], profile: str,
    ) -> None:
        executable = shutil.which(self.binary)
        if not executable:
            raise ToollessUnavailable("claude CLI is not installed")
        try:
            result = subprocess.run(
                [executable, "--help"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ToollessUnavailable(
                f"Claude toolless capability preflight failed: {exc}"
            ) from exc
        advertised = result.stdout + "\n" + result.stderr
        missing = sorted(flag for flag in required if flag not in advertised)
        if result.returncode or missing:
            detail = ", ".join(missing) if missing else f"exit {result.returncode}"
            raise ToollessUnavailable(
                f"installed Claude CLI has no compatible {profile} profile ({detail})"
            )

    def preflight_toolless(self, model: str, effort: str) -> None:
        """Prove the installed CLI advertises every flag in the empty-tool profile."""
        self._preflight_flags(self.TOOLLESS_REQUIRED_FLAGS, "empty-tool")
        self.build_toolless_argv(Path(tempfile.gettempdir()), model, effort)

    def preflight_discovery(self, model: str, effort: str) -> None:
        self._preflight_flags(self.DISCOVERY_REQUIRED_FLAGS, "search-only")
        self.build_discovery_argv(Path(tempfile.gettempdir()), model, effort)

    def build_toolless_argv(self, cwd: Path, model: str, effort: str) -> list[str]:
        denied = list(dict.fromkeys([*CLAUDE_RO_TOOLS, *CLAUDE_WEB_TOOLS, *CLAUDE_DENY_TOOLS]))
        return [
            "claude", "-p", "--output-format", "json", "--model", model,
            "--effort", effort, "--permission-mode", "default",
            "--setting-sources", "", "--allowedTools", "",
            "--tools", "", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}',
            "--disallowedTools", ",".join(denied),
        ]

    def build_discovery_argv(self, cwd: Path, model: str, effort: str) -> list[str]:
        denied = list(dict.fromkeys([
            *CLAUDE_RO_TOOLS, "WebFetch", *CLAUDE_DENY_TOOLS,
        ]))
        return [
            "claude", "-p", "--output-format", "json", "--model", model,
            "--effort", effort, "--permission-mode", "default",
            "--setting-sources", "", "--allowedTools", "WebSearch",
            "--tools", "WebSearch", "--max-turns", "4", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}',
            "--disallowedTools", ",".join(denied),
        ]

    def _allowed(self, web_search: bool) -> str:
        # text_only: an EMPTY allowlist. In `-p` mode a tool that needs permission
        # and isn't allowlisted is auto-denied, so this is a real capability
        # boundary for the cleaner/attester roles, not just an instruction.
        if self.text_only:
            return ""
        tools = list(CLAUDE_RO_TOOLS)
        if web_search:
            tools += CLAUDE_WEB_TOOLS
        return ",".join(tools)

    def build_argv(self, cwd: Path, model: str, effort: str, web_search: bool) -> list[str]:
        return [
            "claude", "-p",
            "--output-format", "json",
            "--model", model,
            "--effort", effort,
            "--permission-mode", "default",
            # Hermetic read-only: load NO settings files, so the reviewed repo's
            # (or the user's global) .claude allow-lists cannot widen the
            # reviewer beyond paranoia's --allowedTools. This is a flag on the
            # spawned subprocess only — it does not affect any other `claude`.
            "--setting-sources", "",
            "--allowedTools", self._allowed(web_search),
            "--disallowedTools", ",".join(CLAUDE_DENY_TOOLS),
        ]

    def build_resume_argv(
        self, session_ref: str, cwd: Path, model: str, effort: str, web_search: bool
    ) -> list[str]:
        return [
            "claude", "-p",
            "--resume", session_ref,
            "--output-format", "json",
            "--model", model,
            "--effort", effort,
            "--permission-mode", "default",
            "--setting-sources", "",
            "--allowedTools", self._allowed(web_search),
            "--disallowedTools", ",".join(CLAUDE_DENY_TOOLS),
        ]

    def parse_output(self, stdout: str) -> Review:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return Review(text=stdout.strip(), session_ref=None, raw=stdout)
        if not isinstance(data, dict):
            return Review(text=stdout.strip(), session_ref=None, raw=stdout)
        usage: dict | None = None
        tokens, cost = data.get("usage"), data.get("total_cost_usd")
        if tokens is not None or cost is not None:
            usage = {"tokens": tokens, "cost_usd": cost}
        return Review(
            text=str(data.get("result", "")),
            session_ref=data.get("session_id"),
            raw=stdout,
            error=bool(data.get("is_error", False)),
            usage=usage,
            duration_ms=data.get("duration_ms"),
        )


_ENGINES: dict[str, type[Engine]] = {
    "codex": CodexEngine,
    "claude": ClaudeEngine,
}

# Arbitration roles pin their models explicitly rather than inheriting
# `default_model`: the cleaner must be Opus, and resolving it through the engine
# default would silently give it Fable instead.
CLEANER_ENGINE = "claude"
CLEANER_MODEL = "claude-opus-5"
ATTESTER_ENGINE = "codex"
ATTESTER_MODEL = "gpt-5.6-sol"


def get_engine(name: str, *, text_only: bool = False) -> Engine:
    try:
        engine = _ENGINES[name]()
    except KeyError:
        raise ValueError(
            f"unknown engine {name!r}; choose one of {sorted(_ENGINES)}"
        ) from None
    if text_only:
        engine.text_only = True
    return engine


def all_engines() -> tuple[Engine, ...]:
    """Every registered engine, in registry order.

    Arbitration fans out to all of them and requires unanimity. Note that vendor
    *ordering* here must never decide which decider sees which option order — that
    comes from the recorded seed (see `arbitration.forward_engine`).
    """
    return tuple(cls() for cls in _ENGINES.values())
