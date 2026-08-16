"""Engine abstraction — each engine drives a local coding-agent CLI in a
headless, read-only mode over the user's subscription.

The CLI *is* the reviewer: it has full read access to the repo at `cwd` and
decides what to open. This module only builds the argv, feeds the prompt on
stdin, and parses the final message + a session reference (for `rebut`).

`build_argv` / `build_resume_argv` / `parse_output` are pure and unit-tested.
The impure subprocess call is injected via `runner` (see runner.py).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from .runner import RunResult, run_capture, run_streaming

Runner = Callable[[list[str], str, Path, int], RunResult]

# Longest progress message forwarded to the client (spinner-line sized).
_PROGRESS_MSG_MAX = 100

ROLE_DEFAULT = "default"
ROLE_DISCOVERY = "evidence-discovery"
ROLE_BINDING = "evidence-binding"
ROLE_REPOSITORY = "evidence-repository"
ROLE_TEXT = "evidence-text"
EVIDENCE_ROLES = frozenset({ROLE_DISCOVERY, ROLE_BINDING, ROLE_REPOSITORY, ROLE_TEXT})

MIN_CODEX_VERSION = (0, 144, 6)
MIN_CLAUDE_VERSION = (2, 1, 197)

CODEX_EXTERNAL_FEATURES = (
    "apps", "browser_use", "browser_use_external", "browser_use_full_cdp_access",
    "computer_use", "in_app_browser", "plugins", "remote_plugin", "plugin_sharing",
    "enable_mcp_apps", "image_generation", "multi_agent", "workspace_dependencies",
    "auth_elicitation", "tool_call_mcp_elicitation", "skill_mcp_dependency_install",
    "hooks", "tool_suggest",
)


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
    failure_detail: str | None = None
    stderr: str | None = None


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
    #: Both bundled reviewers expose first-party web tools through their own CLI.  The
    #: plan-claim phase keys off this capability so test/dummy engines are not silently
    #: asked to perform a second protocol they do not implement.
    native_web: bool = True
    role: str = ROLE_DEFAULT

    def for_role(self, role: str) -> Engine:
        if role not in EVIDENCE_ROLES and role != ROLE_DEFAULT:
            raise ValueError(f"unknown evidence role: {role}")
        clone = type(self)()
        clone.text_only = self.text_only
        clone.role = role
        return clone

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
        response_schema: dict[str, Any] | None = None,
    ) -> Review:
        argv = self.build_argv(cwd, model, effort, web_search)
        return self._execute(
            argv, prompt, cwd, runner, timeout, on_progress, response_schema,
        )

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
        response_schema: dict[str, Any] | None = None,
    ) -> Review:
        argv = self.build_resume_argv(session_ref, cwd, model, effort, web_search)
        return self._execute(
            argv, prompt, cwd, runner, timeout, on_progress, response_schema,
        )

    def _execute(
        self,
        argv: list[str],
        prompt: str,
        cwd: Path,
        runner: Runner | None,
        timeout: int | None,
        on_progress: Callable[[str], None] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> Review:
        from .runner import DEFAULT_TIMEOUT_SEC

        final_argv, cleanup = self._structured_argv(argv, response_schema)
        if on_progress is not None:
            def _on_line(line: str) -> None:
                msg = self.progress_from_line(line)
                if msg:
                    on_progress(msg)

            streaming = runner or run_streaming
            try:
                result = streaming(
                    final_argv, prompt, cwd, timeout or DEFAULT_TIMEOUT_SEC, on_line=_on_line
                )
            finally:
                cleanup()
        else:
            try:
                result = (runner or run_capture)(
                    final_argv, prompt, cwd, timeout or DEFAULT_TIMEOUT_SEC
                )
            finally:
                cleanup()
        review = self.parse_output(result.stdout)
        if response_schema is not None and self.name == "claude" and not review.error:
            try:
                envelope = json.loads(result.stdout)
            except json.JSONDecodeError:
                envelope = None
            if not isinstance(envelope, dict) or not isinstance(
                envelope.get("structured_output"), dict
            ):
                review = replace(
                    review,
                    error=True,
                    failure_detail=(
                        "claude did not return the requested structured_output object"
                    ),
                )
        # A review is failed if the process exited non-zero OR the engine reported an
        # in-band error (e.g. Claude's is_error) — the latter can occur with rc 0 and
        # non-empty stdout, which the old "rc != 0 AND empty stdout" gate silently
        # swallowed, defeating any downstream fallback.
        failed = result.returncode != 0 or review.error
        stderr = result.stderr if result.stderr else None
        failure_detail = (
            (
                review.failure_detail or (result.stderr if result.stderr.strip() else None)
                or f"{self.name} exited with return code {result.returncode}"
            ) if result.returncode != 0
            else review.failure_detail
        )
        if failed and not (review.text or "").strip():
            detail = failure_detail or review.raw or "engine failure"
            return Review(
                text=(
                    f"[paranoia-local error] {self.name} exited {result.returncode}: "
                    f"{detail.strip()[:2000]}"
                ),
                session_ref=review.session_ref,
                raw=result.stdout,
                returncode=result.returncode,
                error=True,
                failure_detail=detail,
                stderr=stderr,
            )
        return replace(
            review, returncode=result.returncode, error=failed,
            failure_detail=failure_detail, stderr=stderr,
        )

    def _structured_argv(
        self, argv: list[str], schema: dict[str, Any] | None,
    ) -> tuple[list[str], Callable[[], None]]:
        """Add provider-native structured output without changing capability flags."""
        if schema is None:
            return argv, lambda: None
        rendered = json.dumps(
            schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        if self.name == "claude":
            # Claude's --tools/--allowedTools are variadic.  A later --json-schema
            # is consumed as another tool value; insert before the first variadic
            # flag, exactly as the pinned-CLI live probe requires.
            indexes = [
                argv.index(flag) for flag in ("--tools", "--allowedTools") if flag in argv
            ]
            index = min(indexes) if indexes else len(argv)
            return [*argv[:index], "--json-schema", rendered, *argv[index:]], lambda: None
        descriptor, path = tempfile.mkstemp(prefix="paranoia-schema-", suffix=".json")
        try:
            os.write(descriptor, rendered.encode("utf-8"))
        finally:
            os.close(descriptor)
        os.chmod(path, 0o400)
        index = len(argv) - 1 if argv and argv[-1] == "-" else len(argv)
        final = [*argv[:index], "--output-schema", path, *argv[index:]]

        def cleanup() -> None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

        return final, cleanup


class CodexEngine(Engine):
    name = "codex"
    default_model = "gpt-5.6-sol"
    binary = "codex"

    def _evidence_flags(self, *, resumed: bool = False) -> list[str]:
        live = self.role == ROLE_DISCOVERY
        flags = [
            "-c", 'approval_policy="never"',
            "-c", f'web_search="{"live" if live else "disabled"}"',
            "-c", "sandbox_workspace_write.network_access=false",
            "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            "-c", "sandbox_workspace_write.writable_roots=[]",
        ]
        if resumed:
            resumed_sandbox = (
                "workspace-write"
                if self.role in {ROLE_DISCOVERY, ROLE_REPOSITORY}
                else "read-only"
            )
            flags += ["-c", f'sandbox_mode="{resumed_sandbox}"']
        for feature in CODEX_EXTERNAL_FEATURES:
            flags += ["--disable", feature]
        return flags

    def build_argv(self, cwd: Path, model: str, effort: str, web_search: bool) -> list[str]:
        if self.role in EVIDENCE_ROLES:
            sandbox = "workspace-write" if self.role in {ROLE_DISCOVERY, ROLE_REPOSITORY} else "read-only"
            return [
                "codex", "exec", "--json", "--ignore-user-config",
                "--skip-git-repo-check", "-s", sandbox, "-C", str(cwd), "-m", model,
                "-c", f'model_reasoning_effort="{effort}"',
                *self._evidence_flags(), "-",
            ]
        argv = [
            "codex", "exec",
            "--json",
            # Auth still comes from CODEX_HOME, but user config (especially registered
            # MCP servers) must not widen a spawned reviewer into recursive delegation.
            # Required model/effort/web capabilities are supplied explicitly below.
            "--ignore-user-config",
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
        if self.role in EVIDENCE_ROLES:
            return [
                "codex", "exec", "resume", session_ref, "--json",
                "--ignore-user-config", "--skip-git-repo-check", "-m", model,
                "-c", f'model_reasoning_effort="{effort}"',
                *self._evidence_flags(resumed=True), "-",
            ]
        # `codex exec resume` does NOT accept -s/-C: a resumed session inherits
        # its original sandbox (read-only) and cwd. We pass -C nowhere and rely
        # on the process cwd (set by the runner). --skip-git-repo-check keeps it
        # working even if the original cwd (an isolated worktree) is gone.
        argv = [
            "codex", "exec", "resume", session_ref,
            "--json",
            "--ignore-user-config",
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
        failure_detail: str | None = None
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
            if etype in {"error", "turn.failed"}:
                error = True
                detail = event.get("error")
                if isinstance(detail, dict):
                    detail = detail.get("message")
                if not isinstance(detail, str):
                    detail = event.get("message")
                if isinstance(detail, str):
                    failure_detail = detail
            if etype == "turn.completed":
                u = event.get("usage")
                if isinstance(u, dict):
                    usage = u
                # Codex can emit a transient top-level error while retrying a
                # model stream and still finish the turn successfully.  The
                # terminal event, not an earlier recovered event, governs the
                # process result.
                error = False
                failure_detail = None
            item = event.get("item")
            if isinstance(item, dict):
                if item.get("type") == "agent_message":
                    text = item.get("text")
                    if isinstance(text, str):
                        last_message = text
                elif item.get("type") == "error":
                    error = True
                    detail = item.get("message") or item.get("text")
                    if isinstance(detail, str):
                        failure_detail = detail
        return Review(
            text=last_message or "", session_ref=thread_id, raw=stdout, error=error,
            usage=usage, failure_detail=failure_detail,
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
# Redundant belt-and-braces over the allowlist above, which is what actually
# bounds the reviewer. Every NAME here must exist in the installed Claude Code,
# because the CLI rejects an unknown deny rule with
#   Permission deny rule "X" matches no known tool — check for typos.
# and that line contaminates the engine's structured output, so every review on
# this engine fails to parse. `MultiEdit` was removed from Claude Code (absent
# in 2.1.197) and was dropped here for that reason; it denied nothing either
# way, since a tool that is not allowlisted is auto-denied in `-p` mode.
CLAUDE_DENY_TOOLS = ["Write", "Edit", "NotebookEdit"]


class ClaudeEngine(Engine):
    name = "claude"
    default_model = "claude-fable-5"
    binary = "claude"

    def _evidence_tools(self) -> str:
        if self.role == ROLE_DISCOVERY:
            return "WebSearch"
        if self.role == ROLE_REPOSITORY:
            return "Read,Grep,Glob"
        return ""

    def _evidence_argv(self, model: str, effort: str) -> list[str]:
        tools = self._evidence_tools()
        return [
            "--output-format", "json", "--model", model, "--effort", effort,
            "--safe-mode", "--setting-sources", "", "--strict-mcp-config",
            # `--tools` narrows availability; it does not grant permission in
            # headless `-p` mode. Keep both boundaries identical so discovery can
            # actually use WebSearch while binding/text remain genuinely tool-less.
            "--tools", tools, "--allowedTools", tools,
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
        if self.role in EVIDENCE_ROLES:
            return ["claude", "-p", *self._evidence_argv(model, effort)]
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
        if self.role in EVIDENCE_ROLES:
            return [
                "claude", "-p", "--resume", session_ref,
                *self._evidence_argv(model, effort),
            ]
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
        structured = data.get("structured_output")
        text = (
            json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
            if isinstance(structured, dict) else str(data.get("result", ""))
        )
        is_error = bool(data.get("is_error", False))
        denied = {
            item.get("tool_name")
            for item in data.get("permission_denials", [])
            if isinstance(item, dict) and isinstance(item.get("tool_name"), str)
        } if isinstance(data.get("permission_denials", []), list) else set()
        required = set(filter(None, self._evidence_tools().split(",")))
        denied_required = sorted(required & denied)
        permission_failure = (
            "required evidence tool permission denied: " + ", ".join(denied_required)
            if self.role in EVIDENCE_ROLES and denied_required else None
        )
        return Review(
            text=text,
            session_ref=data.get("session_id"),
            raw=stdout,
            error=is_error or permission_failure is not None,
            usage=usage,
            duration_ms=data.get("duration_ms"),
            failure_detail=text if is_error else permission_failure,
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


def _cli_version(binary: str) -> tuple[int, int, int]:
    result = subprocess.run([binary, "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cannot run {binary} --version: {result.stderr.strip()}")
    match = re.search(
        r"(?<![\d.])(\d+)\.(\d+)\.(\d+)([-+][0-9A-Za-z.-]+)?",
        result.stdout,
    )
    if not match:
        raise RuntimeError(f"cannot parse {binary} version from {result.stdout.strip()!r}")
    qualifier = match.group(4) or ""
    if qualifier.startswith("-"):
        raise RuntimeError(
            f"{binary} evidence mode does not support prerelease CLI versions; "
            f"found {match.group(0)}"
        )
    return tuple(int(part) for part in match.groups()[:3])


def require_evidence_profile(engine: Engine) -> str:
    minimum = {
        "codex": MIN_CODEX_VERSION,
        "claude": MIN_CLAUDE_VERSION,
    }.get(engine.name)
    if minimum is None:
        raise RuntimeError(f"no evidence profile for engine {engine.name!r}")
    actual = _cli_version(engine.binary)
    if actual < minimum:
        minimum_text = ".".join(str(part) for part in minimum)
        actual_text = ".".join(str(part) for part in actual)
        raise RuntimeError(
            f"{engine.name} evidence mode requires CLI >= {minimum_text}; "
            f"found {actual_text}. Install a supported version."
        )
    return ".".join(str(part) for part in actual)
