"""Acceptance orchestration tests; scripted judgments are not live quality evidence."""
import json
import fcntl
import os
import tarfile
from pathlib import Path

import pytest
from paranoia_local import engines, handlers
from scripts import run_class_authoring_acceptance as acceptance
from tests.test_review_census import lane, payload, wire


def test_acceptance_graph_and_resealed_negative_controls(tmp_path, monkeypatch):
    archive = acceptance.ROOT / "docs/predicate-convergence-evidence.tar.gz"
    with tarfile.open(archive) as retained:
        original = json.load(retained.extractfile("input.json"))
    original["case"]["files"]["app.py"] = original["case"]["files"]["app.py"].replace(
        "isinstance(index, bool) or ", "", 1,
    )
    seed = tmp_path / "seed.json"
    acceptance.shared.dump(seed, original)
    root = tmp_path / "acceptance"

    real_output = acceptance.subprocess.check_output
    def output(args, *a, **kw):
        if len(args) == 2 and args[0] in {"codex", "claude"} and args[1] == "--version":
            return "scripted-unit-route"
        return real_output(args, *a, **kw)
    monkeypatch.setattr(acceptance.subprocess, "check_output", output)
    # Unit tests may run an uncommitted checkout. Source admission itself has
    # dedicated committed-blob regressions; all native observed source joins
    # below still execute. No artifact from this temporary run is live evidence.
    monkeypatch.setattr(acceptance.shared, "validate_source", lambda source: None)

    retry_reply = {}
    retry_schema = {}
    def execute(self, argv, prompt, cwd, runner, timeout, on_progress=None, response_schema=None):
        if prompt.startswith("Your staged JSON was rejected:"):
            assert self.name == "codex" and acceptance.AUTHORING_TASK not in prompt
            assert response_schema is retry_schema[self.name]
            assert "scripted-codex" in argv
            return engines.Review(
                text=retry_reply[self.name], raw=retry_reply[self.name],
                session_ref="scripted-codex", returncode=0, error=False,
                duration_ms=1, provider_duration_ms=1, stderr="", failure_detail="",
            )
        anchors = [f"repository/app.py:{line}" for line in acceptance.manifest(root)["gate_lines"]]
        anchor = anchors[0]
        finding = {
            "id":"identity", "severity":"MAJOR",
            "summary":"Boolean identity admitted by the integer gate.",
            "evidence":anchors, "remedy":"Reject non-integer JSON identities at both entry points.",
        }
        if "ROLE: census lane " in prompt:
            assert acceptance.AUTHORING_TASK not in prompt
            name = next(l.split()[-1] for l in prompt.splitlines()
                        if l.startswith("ROLE: census lane "))
            value = json.loads(lane(name, findings=[finding]))
            text = json.dumps(value).replace("plan:1", anchor)
        else:
            task = json.loads(prompt.split("===== TASK INPUT =====\n\n", 1)[1])
            if task["role"] == "census":
                assert prompt.startswith(acceptance.AUTHORING_TASK + "\n\n")
                value = {
                    "role":"census", "governing_findings":[{
                        **finding,
                        "source_ids":[f["id"] for m in task["manifests"] for f in m["findings"]],
                        "classification":{"kind":"new_class", "definition":{
                            "invariant":"JSON scalar identities exclude Booleans and non-integers.",
                            "severity":"MAJOR", "procedure":"Inspect all identity gates in the supported JSON scalar domain.",
                            "members":["integer-identity"],
                        }},
                    }], "debt_outcomes":[], "class_actions":{},
                }
            else:
                assert acceptance.AUTHORING_TASK not in prompt
                cls = task["active_classes"][0]
                value = {
                    "role":task["role"], "governing_findings":[],
                    "debt_outcomes":[{"debt_id":d["id"], "status":"closed", "evidence":anchors}
                                     for d in task["existing_debt"]],
                    "class_outcomes":{cls["class_id"]:{
                        "verdict":"satisfied", "member_coverage":[{
                            "member_id":"integer-identity", "evidence":anchors,
                        }],
                    }}, "class_actions":{cls["class_id"]:None},
                }
                if task["role"] == "final":
                    value["coverage"] = payload(lane())["coverage"]
                    for row in value["coverage"]:
                        row["evidence"] = [anchor]
            text = wire(value)
            if task["role"] == "census" and self.name == "codex":
                retry_reply[self.name] = text
                retry_schema[self.name] = response_schema
                text = "{}"  # Exercise the unchanged native consolidation retry.
        return engines.Review(text=text, raw=text, session_ref="scripted-" + self.name,
                              returncode=0, error=False, duration_ms=1,
                              provider_duration_ms=1, stderr="", failure_detail="")
    monkeypatch.setattr(engines.Engine, "_execute", execute)

    acceptance.freeze(root, seed)
    for variant, expected in {"defect":[True, True], "exact":[False, False],
                              "boolean":[False, False], "half":[False, True]}.items():
        calibration = acceptance.sealed(root / f"{variant}-calibration.json")
        assert [bool(entry["result"]["target_failures"]) for entry in calibration["entries"]] == expected
        assert all(len(entry["result"]["checks"]) == 100 for entry in calibration["entries"])
    def run(node):
        # Real runs use one process per node. Restore wrappers between simulated
        # workers to preserve that same observer/admission boundary.
        with monkeypatch.context() as worker:
            worker.setattr(engines.Engine, "run", engines.Engine.run)
            worker.setattr(engines.Engine, "resume", engines.Engine.resume)
            worker.setattr(acceptance.shared, "admit", acceptance.shared.admit)
            worker.setattr(acceptance.pilot, "verify_fixture", acceptance.pilot.verify_fixture)
            acceptance.run_node(root, node)
        assert acceptance.custody.read(root / node / "terminal.json")["error"] is None

    for parent in acceptance.PROVIDERS:
        run(parent)
        state = acceptance.custody.read(acceptance.state_file(root / parent))
        target = state["classes"][0]
        debt = state["review_state"]["debt"]
        acceptance.seal(root / parent / "assessment.json", {
            "state_sha256":acceptance.shared.sha(acceptance.state_file(root / parent).read_bytes()),
            "terminal_sha256":acceptance.shared.sha((root / parent / "terminal.json").read_bytes()),
            "faithful":True, "rationale":"Scripted unit class expresses exactly the fixture contract.",
            "class_id":target["class_id"], "definition":acceptance.definition(target),
            "debt_ids":[d["id"] for d in debt],
            "evidence":[f"repository/app.py:{line}" for line in acceptance.manifest(root)["gate_lines"]],
        })
        for repair in acceptance.REPAIRS:
            node = parent + "-" + repair
            acceptance.fork(root, node)
            run(node)
    qualified = acceptance.qualify_trial_graph(root, complete=True)
    assert qualified["calls"] == 17
    results = acceptance.check_replay(root)
    assert len(results) == 18
    assert all(row["rejection"] for row in results)
    assert all(row["dependent_calls"] == 0 for row in results
               if row["mutation"].startswith(("gate-", "task-")))


def test_direct_task_forwards_every_other_argument_and_restores_scope(tmp_path, monkeypatch):
    forwarded = []
    returned = object()
    def original(**kwargs):
        forwarded.append(kwargs)
        return returned
    monkeypatch.setattr(handlers, "_staged_call", original)
    arguments = {
        "role": "consolidation", "prompt": "production prompt",
        "parser": object(), "response_schema": object(), "retry_context": object(),
        "next_sequence": object(), "timeout": 900,
    }
    with acceptance.direct_authoring_scope(tmp_path, parent=True):
        assert handlers._staged_call(**arguments) is returned
        assert forwarded[-1]["prompt"] == acceptance.AUTHORING_TASK + "\n\nproduction prompt"
        assert all(forwarded[-1][key] is value for key, value in arguments.items() if key != "prompt")
        lane = {**arguments, "role": "census-behaviour"}
        assert handlers._staged_call(**lane) is returned
        assert forwarded[-1] == lane
    assert handlers._staged_call is original
    with acceptance.direct_authoring_scope(tmp_path, parent=False):
        assert handlers._staged_call(**arguments) is returned
        assert forwarded[-1] == arguments
    assert handlers._staged_call is original


def test_direct_task_rechecks_augmented_prompt_limit_before_invocation(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(handlers, "_staged_call", lambda **kwargs: calls.append(kwargs))
    with acceptance.direct_authoring_scope(tmp_path, parent=True):
        with pytest.raises(ValueError, match="prompt"):
            handlers._staged_call(role="consolidation",
                prompt="x" * handlers.rc.MAX_CONSOLIDATION_PROMPT_CHARS)
    assert not calls and not (tmp_path / "authoring-task.json").exists()


def test_serial_admission_rejects_overlapping_node_before_work(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(acceptance, "_run_node", lambda root, node: calls.append(node))
    descriptor = os.open(tmp_path, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="another campaign node is running"):
            acceptance.run_node(tmp_path, "p01")
        assert calls == []
    finally:
        os.close(descriptor)
    acceptance.run_node(tmp_path, "p01")
    assert calls == ["p01"]
