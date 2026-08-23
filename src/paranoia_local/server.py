"""MCP stdio server. Exposes four tools that drive a local coding-agent CLI
(Codex or Claude Code) as an adversarial reviewer with full repo access.

The heavy lifting lives in `handlers`; this module is the MCP glue plus a
`dispatch` router that resolves the engine (per-call override > server default)
and turns any handler failure into readable error text instead of a protocol
error.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from . import arbitrate_handler, handlers
from .engines import get_engine
from .logs import DEFAULT_LOG_DIR

Clock = Callable[[], str]

# Shared arg fragments reused across tool schemas.
_COMMON = {
    "engine": {
        "type": "string",
        "enum": ["codex", "claude"],
        "description": "Override which local engine reviews (default: the server's configured engine).",
    },
    "model": {
        "type": "string",
        "description": "Override the reviewer model (default: the engine's strongest — gpt-5.6-sol / claude-fable-5).",
    },
    "effort": {
        "type": "string",
        "enum": ["low", "medium", "high"],
        "description": "Reasoning effort. Reviews default to high; query defaults to medium.",
    },
    "web_search": {
        "type": "boolean",
        "description": (
            "Use the selected reviewer's built-in web search (default true). For "
            "critique_plan this is required while claim verification is enabled; there "
            "is no custom search endpoint or API-key integration."
        ),
    },
}

_ALREADY_RAISED = {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Convergence loop: one-line, file:line-cited claims already accepted from prior rounds. "
        "The reviewer is told NOT to restate these and to hunt for what they missed. Never paste prior reviewers' prose."
    ),
}

# Calibration inputs — the levers an LLM operator tunes to keep a convergence loop
# proportionate and terminating (see README "Convergence loop").
_STAKES = {
    "type": "string",
    "description": (
        "The real deployment context / threat model / scale this work operates in "
        "(e.g. 'single-user local CLI, trusted input, no multi-tenancy, ~hundreds of files'). "
        "The reviewer treats it as the BOUNDARY of legitimate concern: findings that assume "
        "adversaries, scale, concurrency, or failure modes beyond it are dropped or tagged "
        "[OUT-OF-SCOPE], never must-fix — this keeps the review proportionate and stops "
        "hardening/scope-creep. Omit and the reviewer assumes a MODEST internal tool (trusted "
        "operators, no hostile input), not a hostile/high-scale service. Best set once per "
        "project in .paranoia.toml; override per-call to tighten for a specific review."
    ),
}
_ROUND = {
    "type": "integer",
    "minimum": 1,
    "description": (
        "REQUIRED unless you pass class_closure: false (the one-shot mode). "
        "Convergence-loop caller label (1-based). After a settled tracked round it must be "
        "strictly greater than the durable prior label; forward jumps count toward persistence, "
        "while a failed or rejected label may be retried. "
        "Tracked review uses it for lineage ordering while its cold census/final always cover "
        "every in-scope severity and correction targets durable debt. The legacy one-shot "
        "review retains the round-3 MAJOR-or-higher floor."
    ),
}

_STAKES_REQUIRED = {
    **_STAKES,
    "description": (
        "REQUIRED. " + _STAKES["description"] + " For arbitrate it is passed to the deciders "
        "VERBATIM (never rewritten by the cleaner) because it is the highest-leverage input to "
        "the severity tag, and severity is the one axis that blocks. Pass 'unstated' to accept a "
        "fixed default reading rather than omitting it."
    ),
}

TOOLS: list[Tool] = [
    Tool(
        name="critique_branch",
        description=(
            "Adversarially review a git branch/diff. A cold, strongest-frontier reviewer on the "
            "OTHER engine reads the repo directly (full read access, its own subscription) and returns "
            "a five-section critique with severity tags. Reviews an isolated worktree of the ref by "
            "default; can review the dirty working tree with include_uncommitted."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repo."},
                "base_ref": {"type": "string", "description": "Base ref for the diff (default main / .paranoia.toml)."},
                "head_ref": {"type": "string", "description": "Head ref (default HEAD)."},
                "include_uncommitted": {
                    "type": "boolean",
                    "description": "Review the dirty working tree vs HEAD instead of a committed range (runs in the live repo, not a worktree).",
                },
                "isolate": {
                    "type": "boolean",
                    "description": "Review inside a throwaway worktree of head_ref so it can't collide with ongoing work (default true; ignored for uncommitted).",
                },
                "converge": {
                    "type": "boolean",
                    "description": "Convergence mode (default TRUE): review an immutable evidence packet through a broad three-lane census, targeted correction debt, and one cold final regression. A clear census may converge immediately. Pass false with class_closure:false for the legacy one-shot path.",
                },
                "max_packet_chars": {
                    "type": "integer",
                    "description": "Total character budget for the converge packet (default 400000). The already_raised list is always preserved; only file evidence is trimmed.",
                },
                "plan_text": {
                    "type": "string",
                    "description": (
                        "Optional frozen implementation contract for tracked convergence. "
                        "Provide this OR absolute plan_path. The first lineage reservation "
                        "freezes exact text/digest; later rounds may omit it to reuse state."
                    ),
                },
                "plan_path": {
                    "type": "string",
                    "description": (
                        "Optional absolute path to the frozen implementation contract. "
                        "Read once; provide this OR plan_text."
                    ),
                },
                "plan_digest": {
                    "type": "string",
                    "pattern": "^(?:[0-9a-f]{16}|[0-9a-f]{64})$",
                    "description": (
                        "Optional 16-hex critique_plan digest prefix or full 64-hex "
                        "SHA-256 assertion; requires plan_text or plan_path."
                    ),
                },
                "project_summary": {"type": "string", "description": "Neutral factual description of the project (not advocacy). The reviewer tests the diff against it."},
                "diff_intent": {"type": "string", "description": "What the diff is SUPPOSED to achieve — treated as a claim to verify."},
                "focus": {"type": "string", "description": "Narrow the review to a specific concern."},
                "already_raised": _ALREADY_RAISED,
                "stakes": _STAKES,
                "round": _ROUND,
                "class_closure": {
                    "type": "boolean",
                    "description": (
                        "Enable tracked staged review (default true): concrete census findings, "
                        "reusable classes, targeted correction, and a mandatory cold final. Branch "
                        "class predicates are still swept against each reviewed snapshot. Set false "
                        "for the legacy one-shot review."
                    ),
                },
                "lineage": {
                    "type": "string",
                    "description": (
                        "Explicit class-closure lineage key. Defaults to repo + base_ref + the "
                        "reviewed branch. Required when the reviewed ref is not a branch (detached "
                        "HEAD or a raw commit), where there is no stable key to derive."
                    ),
                },
                "exempt": {
                    "type": "array",
                    "description": (
                        "Mark specific matches as false positives of a class's regex. Each is shown "
                        "to every later reviewer for challenge, and can be revoked with `unexempt`."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "class_id": {"type": "string"},
                            "path": {"type": "string"},
                            "line": {"type": "integer"},
                            "line_text": {
                                "type": "string",
                                "description": "The matched line verbatim; the exemption is void once it changes.",
                            },
                        },
                        "required": ["class_id", "path", "line", "line_text"],
                    },
                },
                "unexempt": {
                    "type": "array",
                    "description": "Revoke exemptions previously granted (a successful challenge).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "class_id": {"type": "string"},
                            "path": {"type": "string"},
                            "line": {"type": "integer"},
                        },
                        "required": ["class_id", "path", "line"],
                    },
                },
                **_COMMON,
            },
            "required": ["repo_path"],
            "oneOf": [
                {
                    "not": {
                        "anyOf": [
                            {"required": ["plan_text"]},
                            {"required": ["plan_path"]},
                            {"required": ["plan_digest"]},
                        ],
                    },
                },
                {
                    "required": ["plan_text"],
                    "not": {"required": ["plan_path"]},
                },
                {
                    "required": ["plan_path"],
                    "not": {"required": ["plan_text"]},
                },
            ],
        },
    ),
    Tool(
        name="critique_plan",
        description=(
            "Adversarially review a plan or design doc. The reviewer reads the actual "
            "code to test the plan's premises about current behaviour — a plan built on an inverted "
            "premise is the most dangerous kind. Returns the five-section critique with FATAL/MAJOR/MINOR tags."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "plan_text": {"type": "string", "description": "The plan as markdown. Provide this OR plan_path, never both."},
                "plan_path": {"type": "string", "description": "Absolute path to a markdown plan file. Provide this OR plan_text, never both."},
                "context": {"type": "string", "description": "Background the reviewer needs to judge the plan fairly."},
                "repo_path": {"type": "string", "description": "REQUIRED. The repo the plan concerns. Testing the plan's premises against the real code is the reviewer's highest-value job — a plan that asserts 'X currently does Y' when the code shows otherwise is the most dangerous kind — and an ungrounded review cannot do it."},
                "focus": {"type": "string", "description": "Narrow the review to a specific concern."},
                "already_raised": _ALREADY_RAISED,
                "stakes": _STAKES,
                "round": _ROUND,
                "class_closure": {
                    "type": "boolean",
                    "description": (
                        "Enable tracked staged plan review (default TRUE, as for "
                        "critique_branch). Requires `lineage` and `round`. Pass FALSE for a "
                        "ONE-SHOT review — a design sketch with no convergence loop behind "
                        "it — which is the single explicit escape, drops the `round` "
                        "requirement, and emits no computed CONVERGENCE verdict (claim "
                        "packets and structural prose are still returned). The reviewer registers "
                        "each class with a PROCEDURE (never a regex: over prose a predicate "
                        "would close the moment the wording changed, which is what a rewrite "
                        "that keeps the defect looks like). Every later round is shown the "
                        "class and must re-verify it, and a computed CONVERGENCE trailer "
                        "reports BLOCKED until a reviewer explicitly emits `CLOSED` — for "
                        "OPEN classes of severity FATAL or MAJOR only; MINOR and "
                        "OUT-OF-SCOPE ones are tracked, advisory, and never block. The "
                        "guarantee is non-forgetting plus explicit closure — NOT the "
                        "git-backed recurrence detection critique_branch gets. This is a "
                        "call argument only; .paranoia.toml is not consulted for it, in "
                        "either direction, so a project's branch-review setting can neither "
                        "enable nor disable the plan gate."
                    ),
                },
                "claim_verification": {
                    "type": "boolean",
                    "description": (
                        "Verify load-bearing external facts, externally issued design "
                        "principles/requirements, and promised external-system behaviors "
                        "before structural review using the selected reviewer's built-in web "
                        "search (default TRUE for bundled Codex/Claude engines). Repository "
                        "mechanics and local decisions remain in structural/code review and "
                        "tests, not claim inventory. External claims close only on primary or "
                        "authoritative exact passages; known UGC such as Reddit can be a "
                        "lead but never governing evidence. Retained source packets are "
                        "rechecked for entailment against edited wording in later rounds. "
                        "Set false only "
                        "for an explicit structural-only/legacy review."
                    ),
                },
                "lineage": {
                    "type": "string",
                    "description": (
                        "REQUIRED unless class_closure is false. A plan has no branch to key "
                        "state to, and nothing is derived from the plan's text or path — "
                        "either would mint a fresh empty lineage whenever it changed and "
                        "report NOT-BLOCKED with every tracked class silently dropped. The "
                        "key is used VERBATIM as the state filename with no namespacing, so "
                        "pass a globally unique, MODE-QUALIFIED key ('myproject-42-plan'); a "
                        "key already used by a critique_branch seam is refused, because plan "
                        "and branch classes mean different things."
                    ),
                },
                **_COMMON,
            },
            "required": ["repo_path"],
            # The handler has always enforced exactly-one-of; the schema never said so, so
            # a client could not catch it before spending a call.
            "oneOf": [{"required": ["plan_text"]}, {"required": ["plan_path"]}],
        },
    ),
    Tool(
        name="query",
        description=(
            "Quick adversarial double-check of a single fact or point — NOT a full review, no five-section "
            "scaffold, lower reasoning effort. The reviewer reads the repo (if given) and returns a direct "
            "answer with citations and a stated confidence level."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The specific question to double-check."},
                "repo_path": {"type": "string", "description": "Absolute path to the git repo to ground the answer (optional)."},
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "reason": {"type": "string"}},
                        "required": ["path"],
                    },
                    "description": "Optional files to suggest the reviewer look at first (hints, not a payload — it can read anything).",
                },
                "focus": {"type": "string", "description": "Extra framing for the question."},
                **_COMMON,
            },
            "required": ["question"],
        },
    ),
    Tool(
        name="arbitrate",
        description=(
            "Decide between 2-4 options by independent two-vendor adjudication. An Opus agent "
            "neutralizes the framing (cross-vendor attested), performs bounded two-vendor URL "
            "discovery plus server-controlled Trafilatura capture by default, then BOTH frontier engines choose "
            "cold and unaware of each other, over one pinned snapshot, each seeing a "
            "counterbalanced option order under its own opaque labels. Python computes the "
            "verdict: CONVERGED only on a unanimous, unblocked, evidence-substantiated choice. "
            "On divergence it runs one fact-only reconciliation round, and only when there is "
            "novel evidence to carry. Each malformed decider reply gets one bounded full-reply "
            "correction; execution failures are not retried. All phases remain inside the "
            "whole-call deadline. "
            "SHAPE THE INPUT LIKE THIS: put only facts and specification shared by every "
            "option in `context`. Keep each option's distinct mechanism, scope, and "
            "consequences in that option's own concise statement. Substantive detail may differ; "
            "the cleaner may normalize presentation but never transfer content. Absolute framing "
            "bounds are checked before anything is spent; fully "
            "composed cleaner/attester prompts are capped at 180,000 characters and initial or "
            "correction decider prompts at 240,000."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Absolute path to the git repo whose context is pinned. Decisive evidence may be a repository citation or a captured SOURCE packet.",
                },
                "decision": {
                    "type": "string",
                    "maxLength": 2500,
                    "description": "What is being decided, and the properties that bear on it — NOT the evidence for it, which belongs in `context` (max 2500 chars). State it neutrally; your own recommendation will be stripped, and including it only wastes a cleaning round.",
                },
                "options": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Stable id — the vocabulary of the record. Never shown to a decider."},
                            "statement": {"type": "string", "maxLength": 1200, "description": "What this option is (max 1200 chars). Include this option's distinct mechanism, scope, and consequences. Substantive detail may differ from other options; presentation is normalized without transferring content. Self-contained: never reference another option by id, since the two deciders see different orders."},
                        },
                        "required": ["id", "statement"],
                    },
                    "description": "2-4 mutually exclusive options, each with a caller-stable id. Array order is irrelevant — canonical order is derived by sorting ids.",
                },
                "stakes": {**_STAKES_REQUIRED, "maxLength": 20000},
                "context": {"type": "string", "maxLength": 20000, "description": "Background shared by every option: common facts and common specification only. Option-specific mechanisms and consequences stay in their option statements. Preserved byte-for-byte rather than cleaned; the cross-vendor attester independently rejects context that advocates for an option.",},
                "files": {
                    "type": "array",
                    "maxItems": 32,
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "reason": {
                                "type": "string",
                                "description": (
                                    "Optional prose; surrounding whitespace is removed and the "
                                    "canonical value is limited to 1200 characters by runtime validation."
                                ),
                            },
                        },
                        "required": ["path"],
                    },
                    "description": "Starting-point hints. Each must be a repo-relative path present in the snapshot. Both deciders see the same list, so a one-sided hint list biases both.",
                },
                "subject": {"type": "string", "description": "Short label for the paste-ready record block."},
                "clean": {
                    "type": "boolean",
                    "description": "Run the Opus cleaner and its cross-vendor attestation (default true). False passes your framing through verbatim and is reported as CLEANING: skipped.",
                },
                "models": {
                    "type": "object",
                    "properties": {"codex": {"type": "string"}, "claude": {"type": "string"}},
                    "description": "Per-vendor model overrides. There is no single `engine`/`model` override: arbitration needs both vendors.",
                },
                "cleaner_model": {"type": "string", "description": "Override the cleaner model (default claude-opus-5)."},
                "order_seed": {"type": "string", "description": "Replay a previous run's ORDER-SEED to reproduce its labels and option ordering."},
                "retain_snapshot": {
                    "type": "boolean",
                    "description": "Create refs/paranoia/arbitrate/<stamp> so the evidence survives git gc (default false — the only mode that writes a ref).",
                },
                "effort": _COMMON["effort"],
                "web_search": _COMMON["web_search"],
                "research": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Run shared authoritative external research before voting (default true). "
                        "Provider search discovers URLs; the server downloads and extracts pages, "
                        "then resumes the same sessions to bind exact passages. Deciders receive "
                        "the identical captured packet with live web tools disabled. Set false only "
                        "for an explicit repository-only decision. research:true requires web_search:true."
                    ),
                },
            },
            "required": ["repo_path", "decision", "options", "stakes"],
        },
    ),
    Tool(
        name="rebut",
        description=(
            "Dispute a specific finding from a prior review. Resumes the SAME reviewer session (cheaper and "
            "higher-resolution than a cold re-round) with your counter-evidence; it concedes or holds with fresh citations. "
            "The optional lineage/class/mode trio is all-or-none and resets only that class's bounded correction window "
            "after a successful current-session rebut; it never closes debt, changes severity, or grants clearance. "
            "Sessionless gate recovery uses only the exact terminal validation retry and never falls back to an earlier attempt."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Absolute path to the git repo (same one the review ran against)."},
                "session_ref": {"type": "string", "description": "The session_ref printed in the prior review's footer."},
                "rebuttal": {"type": "string", "description": "Your counter-evidence for the disputed finding."},
                "lineage": {"type": "string", "description": "Optional tracked lineage whose correction window resets; requires class_id and lineage_mode."},
                "class_id": {"type": "string", "description": "Optional active class whose durable current session must equal session_ref; requires lineage and lineage_mode."},
                "lineage_mode": {"type": "string", "enum": ["plan", "branch"], "description": "Mode of the optionally bound lineage; requires lineage and class_id."},
                **_COMMON,
            },
            "required": ["repo_path", "session_ref", "rebuttal"],
            "dependentRequired": {
                "lineage": ["class_id", "lineage_mode"],
                "class_id": ["lineage", "lineage_mode"],
                "lineage_mode": ["lineage", "class_id"],
            },
        },
    ),
]

_HANDLERS: dict[str, Callable[..., str]] = {
    "critique_branch": handlers.critique_branch,
    "critique_plan": handlers.critique_plan,
    "query": handlers.query,
    "rebut": handlers.rebut,
}

# `arbitrate` drives BOTH vendors, so it cannot come through the single-engine
# resolution below — that would either degrade it to one vendor or send one
# vendor's model name to the other CLI. It resolves its own engines instead.
_MULTI_ENGINE_HANDLERS: dict[str, Callable[..., str]] = {
    "arbitrate": arbitrate_handler.arbitrate,
}


def dispatch(
    name: str,
    arguments: dict[str, Any],
    *,
    default_engine_name: str,
    log_dir: Path = DEFAULT_LOG_DIR,
    now: Clock | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    try:
        multi = _MULTI_ENGINE_HANDLERS.get(name)
        if multi is not None:
            kwargs: dict[str, Any] = {"log_dir": log_dir}
            if now is not None:
                kwargs["now"] = now
            if on_progress is not None:
                kwargs["on_progress"] = on_progress
            return multi(arguments, **kwargs)
        handler = _HANDLERS.get(name)
        if handler is None:
            raise ValueError(f"unknown tool: {name}")
        engine_name = arguments.get("engine") or default_engine_name
        engine = get_engine(engine_name)
        kwargs = {"engine": engine, "log_dir": log_dir}
        if now is not None:
            kwargs["now"] = now
        if on_progress is not None:
            kwargs["on_progress"] = on_progress
        return handler(arguments, **kwargs)
    except Exception as exc:  # noqa: BLE001 — surface any failure as readable text
        return f"[paranoia-local error] {type(exc).__name__}: {exc}"


def build_server(
    default_engine_name: str,
    log_dir: Path = DEFAULT_LOG_DIR,
    now: Clock | None = None,
) -> Server:
    srv: Server = Server("paranoia-local")

    @srv.list_tools()
    async def _list_tools() -> list[Tool]:
        return TOOLS

    @srv.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        # A review runs for many minutes with no output; when the client sent a
        # progressToken, stream the engine's activity back as MCP progress
        # notifications so the call is visibly alive. The handler runs on a
        # worker thread, so notifications hop back to the event loop.
        on_progress = _progress_callback(srv, asyncio.get_running_loop())
        result = await asyncio.to_thread(
            dispatch, name, arguments,
            default_engine_name=default_engine_name, log_dir=log_dir, now=now,
            on_progress=on_progress,
        )
        return [TextContent(type="text", text=result)]

    return srv


# Progress notifications are rate-limited: an agentic reviewer can emit event
# bursts (one per file read), and each notification is a protocol message.
_PROGRESS_MIN_INTERVAL_SEC = 1.0


def _progress_callback(
    srv: Server, loop: asyncio.AbstractEventLoop
) -> Callable[[str], None] | None:
    """Build a thread-safe progress callback from the CURRENT request's
    progressToken, or None when the client didn't ask for progress."""
    import time

    try:
        ctx = srv.request_context
    except LookupError:
        return None
    meta = getattr(ctx, "meta", None)
    token = getattr(meta, "progressToken", None) if meta else None
    if token is None:
        return None
    session = ctx.session
    state = {"count": 0.0, "last": 0.0}

    def _cb(message: str) -> None:
        now_s = time.monotonic()
        if now_s - state["last"] < _PROGRESS_MIN_INTERVAL_SEC:
            return
        state["last"] = now_s
        state["count"] += 1.0
        # Fire-and-forget: the reviewer thread must never block on the client.
        asyncio.run_coroutine_threadsafe(
            session.send_progress_notification(
                token, state["count"], total=None, message=message
            ),
            loop,
        )

    return _cb


async def run_stdio(server_obj: Server) -> None:
    async with stdio_server() as (read, write):
        await server_obj.run(read, write, server_obj.create_initialization_options())
