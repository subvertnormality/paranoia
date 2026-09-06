import json
from pathlib import Path

import pytest

from paranoia_local import engines, git_objects, handlers, prompts, server, staged_protocol as sp


@pytest.mark.parametrize("provider", ["codex", "claude"])
@pytest.mark.parametrize("failure", [False, True])
def test_public_verified_plan_observes_batch_workspace_and_retains_earlier_call(
    repo, tmp_path, monkeypatch, provider, failure,
):
    from tests.snapshot_fixture import populate, assert_complete
    populate(repo)
    source_repos = []
    calls, workspaces, batches = [], [], []
    real_batch = git_objects.read_batch

    def acquire(repo, requests):
        batches.append(len(requests))
        source_repos.append(repo)
        if failure:
            raise RuntimeError("fixture acquisition failure")
        return real_batch(repo, requests)

    def execute(self, argv, prompt, cwd, *args, **kwargs):
        calls.append(self.role)
        if self.role == engines.ROLE_DISCOVERY:
            text = '=== CLAIM AUDIT JSON ===\n' + json.dumps({
                "claims": [], "coverage": {"sections_scanned": 1, "omitted_nonfacts": 1,
                "prior_assessments": [], "prior_dispositions": [], "notes": "no external facts"},
            })
            # Use the production marker; this test concerns acquisition, not parser spelling.
            text = handlers.pc.AUDIT_MARKER + text[text.index("\n"):]
        else:
            assert self.role == engines.ROLE_REPOSITORY
            root = (cwd / "repository").resolve()
            assert_complete(source_repos[0], root.parent)
            workspaces.append(root)
            if prompts.STAGED_CENSUS_INSTRUCTIONS.splitlines()[0] in prompt:
                lane = next(x.split()[-1] for x in prompt.splitlines()
                            if x.startswith("ROLE: census lane"))
                text = json.dumps({
                    "lane": lane, "coverage": [
                        {"id": key, "status": "covered", "summary": "checked",
                         "evidence": [{"anchor": "repository/README.md:1",
                                       "rationale": "fixture"}], "finding_ids": []}
                        for key in sp.CHECKLIST
                    ], "findings": [], "class_assessments": [],
                })
            else:
                text = json.dumps({"role": "census", "governing_findings": [],
                    "debt_outcomes": [], "class_actions": {}, "concession_challenges": {}})
        return engines.Review(text=text, raw=text, session_ref="fixture", duration_ms=11)

    monkeypatch.setattr(git_objects, "read_batch", acquire)
    monkeypatch.setattr(engines.Engine, "_execute", execute)
    monkeypatch.setattr(engines, "require_evidence_profile", lambda e: None)
    out = server.dispatch("critique_plan", {
        "repo_path": str(repo), "plan_text": "# Internal choice\nInspect the current source.\n",
        "lineage": "batch-integration", "round": 1, "stakes": "trusted local tool",
    }, default_engine_name=provider, log_dir=tmp_path / "logs")
    assert batches
    trace = next(json.loads(p.read_text()) for p in (tmp_path / "logs").glob("*.json")
                 if json.loads(p.read_text()).get("tool") == "run")
    assert calls[0] == engines.ROLE_DISCOVERY
    assert trace["attempts"][0]["role"] == engines.ROLE_DISCOVERY
    assert trace["attempts"][0]["returncode"] == 0
    assert trace["attempts"][0]["elapsed_ms"] >= 0
    if failure:
        assert "fixture acquisition failure" in out
        assert "CONVERGENCE: NOT-BLOCKED" not in out
        assert calls == [engines.ROLE_DISCOVERY]
        assert len(trace["attempts"]) == 1
    else:
        assert "CONVERGENCE: NOT-BLOCKED" in out
        assert workspaces and all(not p.exists() for p in workspaces)
