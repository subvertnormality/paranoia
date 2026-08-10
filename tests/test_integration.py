"""End-to-end plumbing test: the REAL subprocess runner against fake `codex`
and `claude` binaries on PATH. Proves stdin piping, cwd/-C wiring, and output
parsing connect all the way through server.dispatch — without spending any
real subscription quota.
"""

import os
import stat
from pathlib import Path

import pytest

from paranoia_local import engines, server

FAKE_CODEX = """#!/bin/bash
prompt="$(cat)"
{ echo "ARGS: $@"; echo "PWD: $(pwd)"; echo "PROMPT<<"; echo "$prompt"; } > "$PARANOIA_FAKE_OUT"
printf '%s\\n' '{"type":"thread.started","thread_id":"fake-thread-1"}'
printf '%s\\n' '{"type":"item.completed","item":{"type":"agent_message","text":"FAKE CODEX REVIEW"}}'
printf '%s\\n' '{"type":"turn.completed","usage":{}}'
"""

FAKE_CLAUDE = """#!/bin/bash
prompt="$(cat)"
{ echo "ARGS: $@"; echo "PWD: $(pwd)"; echo "PROMPT<<"; echo "$prompt"; } > "$PARANOIA_FAKE_OUT"
printf '%s\\n' '{"type":"result","subtype":"success","is_error":false,"result":"FAKE CLAUDE REVIEW","session_id":"fake-sess-1"}'
"""


@pytest.fixture
def fake_bins(tmp_path: Path, monkeypatch):
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    out = tmp_path / "fake_out.txt"
    for name, body in (("codex", FAKE_CODEX), ("claude", FAKE_CLAUDE)):
        p = bindir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("PARANOIA_FAKE_OUT", str(out))
    return out


class TestRealRunnerAgainstFakeCLIs:
    def test_codex_engine_pipes_prompt_sets_cwd_and_parses(self, repo, fake_bins):
        review = engines.get_engine("codex").run(
            prompt="HELLO-REVIEW-MARKER", cwd=repo, model="gpt-5.6-sol",
            effort="high", web_search=True,
        )
        assert review.text == "FAKE CODEX REVIEW"
        assert review.session_ref == "fake-thread-1"
        debug = fake_bins.read_text()
        assert "HELLO-REVIEW-MARKER" in debug            # stdin reached the CLI
        assert f"PWD: {repo}" in debug                    # cwd was set
        assert "-s read-only" in debug                    # read-only sandbox
        assert 'model_reasoning_effort="high"' in debug

    def test_claude_engine_parses_json_result(self, repo, fake_bins):
        review = engines.get_engine("claude").run(
            prompt="MARK-2", cwd=repo, model="claude-fable-5", effort="high", web_search=True,
        )
        assert review.text == "FAKE CLAUDE REVIEW"
        assert review.session_ref == "fake-sess-1"
        debug = fake_bins.read_text()
        assert "--output-format json" in debug
        assert "MARK-2" in debug


class TestDispatchEndToEnd:
    def test_query_full_stack(self, repo, tmp_path, fake_bins):
        out = server.dispatch(
            "query",
            {"question": "is greet() injection-safe?", "repo_path": str(repo)},
            default_engine_name="codex", log_dir=tmp_path / "logs", now=lambda: "t1",
        )
        assert "FAKE CODEX REVIEW" in out
        assert "fake-thread-1" in out  # session footer for rebut
        assert "injection-safe" in fake_bins.read_text()

    def test_critique_branch_runs_in_worktree(self, repo_with_branch, tmp_path, fake_bins):
        out = server.dispatch(
            "critique_branch",
            {"repo_path": str(repo_with_branch), "base_ref": "main", "head_ref": "feature", "round": 1},
            default_engine_name="codex", log_dir=tmp_path / "logs", now=lambda: "t1",
        )
        assert "FAKE CODEX REVIEW" in out
        # the reviewer ran inside an isolated worktree, not the author's checkout
        debug = fake_bins.read_text()
        assert "paranoia-wt-" in debug
        assert f"PWD: {repo_with_branch}\n" not in debug

    def test_rebut_resumes_via_dispatch(self, repo, tmp_path, fake_bins):
        out = server.dispatch(
            "rebut",
            {"repo_path": str(repo), "session_ref": "fake-thread-1",
             "rebuttal": "that branch is unreachable", "round": 1},
            default_engine_name="codex", log_dir=tmp_path / "logs", now=lambda: "t1",
        )
        assert "FAKE CODEX REVIEW" in out
        debug = fake_bins.read_text()
        assert "ARGS: exec resume fake-thread-1" in debug
        assert "unreachable" in debug


# Fake CLIs that speak the arbitration protocol: the cleaner and attester are
# recognised by their instruction text, and a decider echoes back the FIRST label
# it was shown. Both deciders picking their own first label means they pick
# DIFFERENT options (the orders are counterbalanced), which is the divergence path.
_ARB_SCRIPT = r"""
prompt="$(cat)"
{ echo "ARGS: $@"; echo "PWD: $(pwd)"; echo "PROMPT<<"; echo "$prompt"; } >> "$PARANOIA_FAKE_OUT"
if printf '%s' "$prompt" | grep -q 'You are a NEUTRALIZER'; then
  body=$(printf '=== DECISION ===\nPick one.\n\n=== OPTIONS ===\nopt-a: Alpha approach.\nopt-b: Bravo approach.\n\n=== CONTEXT ===\nNone.\n\n=== HINTS ===\nNone.\n')
elif printf '%s' "$prompt" | grep -q 'You are a TEXT AUDITOR'; then
  body=$(printf 'FIDELITY: decision PRESERVED; opt-a PRESERVED; opt-b PRESERVED\nNEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE')
else
  label=$(printf '%s' "$prompt" | grep -o 'OPTION-[0-9a-f]\{16\}' | head -1)
  body=$(printf 'Reasoning.\n\nSELECTED: %s\nSELECTED-RISK: NONE\nAUTHORITY: technical\nNEW-OPTION: NONE\nCONSTRAINT: A fact.\nDECISIVE-CITATION: app.py:4\nCITATIONS: NONE' "$label")
fi
"""

FAKE_CODEX_ARB = "#!/bin/bash\n" + _ARB_SCRIPT + """
python3 -c "
import json,sys
print(json.dumps({'type':'thread.started','thread_id':'t'}))
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':sys.argv[1]}}))
print(json.dumps({'type':'turn.completed','usage':{}}))
" "$body"
"""

FAKE_CLAUDE_ARB = "#!/bin/bash\n" + _ARB_SCRIPT + """
python3 -c "
import json,sys
print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':sys.argv[1],'session_id':'s'}))
" "$body"
"""


@pytest.fixture
def fake_arb_bins(tmp_path: Path, monkeypatch):
    bindir = tmp_path / "arbbin"
    bindir.mkdir()
    out = tmp_path / "arb_out.txt"
    out.write_text("")
    for name, body in (("codex", FAKE_CODEX_ARB), ("claude", FAKE_CLAUDE_ARB)):
        p = bindir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("PARANOIA_FAKE_OUT", str(out))
    return out


class TestArbitrateEndToEnd:
    """`arbitrate` through the production boundary: two real subprocesses in
    parallel, per-decider worktrees, and the trailer the caller parses."""

    def _args(self, repo: Path) -> dict:
        return {
            "repo_path": str(repo),
            "decision": "Pick an approach.",
            "options": [
                {"id": "opt-a", "statement": "Alpha approach."},
                {"id": "opt-b", "statement": "Bravo approach."},
            ],
            "stakes": "Local CLI, trusted input.",
            # These tests exercise subprocess, sandbox, and worktree plumbing.
            # The research protocol has focused integration coverage of its own.
            "research": False,
        }

    def test_drives_both_vendors_in_their_own_worktrees(self, repo, tmp_path, fake_arb_bins):
        out = server.dispatch(
            "arbitrate", self._args(repo),
            default_engine_name="codex", log_dir=tmp_path / "logs", now=lambda: "t1",
        )
        debug = fake_arb_bins.read_text()
        # Cleaner (Claude, text-only), attester (Codex, text-only), then two
        # deciders in separate inert evidence workspaces.
        assert "You are a NEUTRALIZER" in debug
        assert "You are a TEXT AUDITOR" in debug
        assert debug.count("/launch") >= 2
        # both engines were actually invoked as deciders
        assert "-s read-only" in debug          # codex
        assert "--output-format json" in debug  # claude
        assert "ARBITRATION: " in out

    def test_deciders_run_read_only_and_cleaner_runs_text_only(self, repo, tmp_path, fake_arb_bins):
        server.dispatch(
            "arbitrate", self._args(repo),
            default_engine_name="codex", log_dir=tmp_path / "logs", now=lambda: "t1",
        )
        debug = fake_arb_bins.read_text()
        assert "--allowedTools ," not in debug  # the text-only claude call has an empty list
        assert "--disallowedTools" in debug

    def test_no_worktree_is_left_registered(self, repo, tmp_path, fake_arb_bins):
        import subprocess

        server.dispatch(
            "arbitrate", self._args(repo),
            default_engine_name="codex", log_dir=tmp_path / "logs", now=lambda: "t1",
        )
        listing = subprocess.run(
            ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True
        ).stdout
        assert "paranoia-wt-" not in listing

    def test_a_missing_binary_fails_preflight_without_spending(self, repo, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", "/nonexistent")
        out = server.dispatch(
            "arbitrate", self._args(repo),
            default_engine_name="codex", log_dir=tmp_path / "logs", now=lambda: "t1",
        )
        assert "ARBITRATION: FAILED" in out
        assert "needs both CLIs" in out
