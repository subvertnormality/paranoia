"""Acceptance orchestration tests; scripted judgments are not live quality evidence."""
import json
import fcntl
import os
import tarfile
from pathlib import Path
from copy import deepcopy

import pytest
from paranoia_local import engines, handlers
from scripts import run_class_authoring_acceptance as acceptance
from tests.test_review_census import lane, payload, wire


def provider_reply(engine, text):
    session = "scripted-" + engine
    if engine == "codex":
        return "\n".join(json.dumps(event) for event in [
            {"type": "thread.started", "thread_id": session},
            {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
            {"type": "turn.completed"},
        ])
    return json.dumps({"session_id": session, "structured_output": json.loads(text)})


def parent_schema():
    from paranoia_local import staged_protocol as sp, class_closure as cc
    return sp.provider_schema(sp.decision_schema(
        cc.BRANCH_MODE, "census", active_classes=[], outcome_class_ids=(), prior_concessions={}))


@pytest.mark.parametrize("with_retry", [True, False])
def test_acceptance_graph_and_resealed_negative_controls(tmp_path, monkeypatch, with_retry):
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
                text=retry_reply[self.name], raw=provider_reply(self.name, retry_reply[self.name]),
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
            if task["role"] == "census" and self.name == "codex" and with_retry:
                retry_reply[self.name] = text
                retry_schema[self.name] = response_schema
                text = "{}"  # Exercise the unchanged native consolidation retry.
        return engines.Review(text=text, raw=provider_reply(self.name, text), session_ref="scripted-" + self.name,
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
    assert qualified["calls"] == (17 if with_retry else 16)
    results = acceptance.check_replay(root)
    assert len(results) == 25
    assert all(row.get("rejection") or row.get("not_applicable") for row in results)
    assert sum("not_applicable" in row for row in results) == (0 if with_retry else 2)
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
        "parser": object(), "response_schema": parent_schema(), "retry_context": object(),
        "next_sequence": object(), "timeout": 900,
    }
    with acceptance.direct_authoring_scope(tmp_path, parent=True):
        assert handlers._staged_call(**arguments) is returned
        assert forwarded[-1]["prompt"] == acceptance.AUTHORING_TASK + "\n\nproduction prompt"
        assert all(forwarded[-1][key] is value for key, value in arguments.items()
                   if key not in {"prompt", "response_schema"})
        assert forwarded[-1]["response_schema"] == acceptance.required_authoring_schema(arguments["response_schema"])
        lane = {**arguments, "role": "census-behaviour"}
        assert handlers._staged_call(**lane) is returned
        assert forwarded[-1] == lane
    assert handlers._staged_call is original
    continuation = tmp_path / "continuation"
    continuation.mkdir()
    with acceptance.direct_authoring_scope(continuation, parent=False):
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


@pytest.mark.parametrize("mechanized", [False, True])
def test_required_schema_is_exact_projection_and_preserves_definitions(mechanized):
    from paranoia_local import staged_protocol as sp
    original = parent_schema()
    before = deepcopy(original)
    narrowed = acceptance.required_authoring_schema(original)
    restored = deepcopy(narrowed)
    target = restored["properties"]["governing_findings"]
    target["minItems"] = original["properties"]["governing_findings"]["minItems"]
    target["items"]["properties"]["classification"]["anyOf"] = deepcopy(
        original["properties"]["governing_findings"]["items"]["properties"]["classification"]["anyOf"])
    assert restored == original == before
    definition = {"invariant": "JSON identities exclude Booleans.", "severity": "MAJOR"}
    definition.update({"pattern": "isinstance", "pathspec": "app.py"} if mechanized else
                      {"procedure": "Inspect both identity gates.", "members": ["identity"]})
    finding = {"id": "identity", "severity": "MAJOR", "summary": "Booleans are admitted.",
               "evidence": [{"anchor": "repository/app.py:1", "rationale": "The identity gate."}],
               "remedy": "Reject Boolean identities.", "source_ids": ["integrity:identity"],
               "classification": {"kind": "new_class", "definition": definition}}
    value = {"role": "census", "governing_findings": [finding], "debt_outcomes": [],
             "class_actions": {}, "concession_challenges": {}}
    for schema in [original, narrowed]:
        assert sp.decode(json.dumps(value), schema, max_chars=1_000_000) == value
    for alternative in [[], [{**finding, "classification": {"kind": "one_off", "reason": "Localized defect."}}]]:
        value["governing_findings"] = alternative
        sp.decode(json.dumps(value), original, max_chars=1_000_000)
        with pytest.raises(sp.ProtocolError):
            sp.decode(json.dumps(value), narrowed, max_chars=1_000_000)


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_required_schema_rejects_unexpected_alternatives_before_spend(tmp_path, monkeypatch, mutation):
    schema = parent_schema()
    choices = schema["properties"]["governing_findings"]["items"]["properties"]["classification"]["anyOf"]
    new = next(choice for choice in choices if choice["properties"]["kind"]["const"] == "new_class")
    if mutation == "missing":
        choices.remove(new)
    else:
        choices.append(deepcopy(new))
    calls = []
    monkeypatch.setattr(handlers, "_staged_call", lambda **kwargs: calls.append(kwargs))
    with acceptance.direct_authoring_scope(tmp_path, parent=True):
        with pytest.raises(ValueError, match="authoring schema"):
            handlers._staged_call(role="consolidation", prompt="production prompt", response_schema=schema)
    assert not calls


def test_fresh_qualification_selects_owned_source_before_installed_package(tmp_path):
    import subprocess
    shadow = tmp_path / "installed"
    package = shadow / "paranoia_local"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('raise RuntimeError("wrong installed package imported")')
    script = acceptance.ROOT / "scripts/run_class_authoring_acceptance.py"
    code = (
        "import runpy, pathlib\n"
        f"scope = runpy.run_path({str(script)!r}, run_name='acceptance_probe')\n"
        "try:\n"
        f"    scope['qualify_authoring_schemas'](pathlib.Path({str(tmp_path)!r}), 'p01', {{'attempt_roles': {{}}}})\n"
        "except ValueError as exc:\n"
        "    assert 'role inventory' in str(exc)\n"
        "from paranoia_local import engines\n"
        f"assert pathlib.Path(engines.__file__).resolve() == pathlib.Path({str(acceptance.ROOT / 'src/paranoia_local/engines.py')!r})\n"
    )
    environment = {**os.environ, "PYTHONPATH": str(shadow)}
    subprocess.run([acceptance.sys.executable, "-c", code], cwd=tmp_path,
                   env=environment, check=True, capture_output=True, text=True)


def test_recurring_fixture_labels_preserve_behavior_and_code():
    import ast
    with tarfile.open(acceptance.ROOT / "docs/predicate-convergence-evidence.tar.gz") as archive:
        original = json.load(archive.extractfile("input.json"))
    original["case"]["files"]["app.py"] = original["case"]["files"]["app.py"].replace(
        "isinstance(index, bool) or ", "", 1)
    files = acceptance.recurring_files(original["case"]["files"])
    capture, replacement = ast.parse(files["app.py"]).body[-2:]
    assert capture.name == acceptance.ENTRY_POINTS[0]
    assert replacement.name == acceptance.ENTRY_POINTS[1]
    original_capture = ast.parse(original["case"]["files"]["app.py"]).body[-1]
    assert ast.dump(capture) == ast.dump(original_capture)
    replacement.name = capture.name
    labels = 0
    for node in ast.walk(replacement):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "capture_attestation" not in node.value
            if "replacement_attestation" in node.value:
                labels += 1
                node.value = node.value.replace("replacement_attestation", "capture_attestation")
    assert labels == 13 and ast.dump(capture) == ast.dump(replacement)
    for variant in ("defect", "exact", "boolean", "half"):
        candidate = deepcopy(files)
        if variant in acceptance.REPAIRS:
            candidate["app.py"] = candidate["app.py"].replace(
                "not isinstance(index, int)", acceptance.REPAIRS[variant])
        elif variant == "half":
            candidate["app.py"] = candidate["app.py"].replace(
                "not isinstance(index, int)", acceptance.REPAIRS["exact"], 1)
        calibrated = acceptance.calibrate_recurring(
            candidate, (variant == "defect", variant in {"defect", "half"}))
        for label, entry in zip(("capture_attestation", "replacement_attestation"),
                                calibrated["entries"], strict=True):
            assert len(entry["result"]["checks"]) == 100
            errors = [c["actual"]["reason"] for c in entry["result"]["checks"]
                      if c["actual"]["kind"] == "error"]
            assert errors
            assert all(("replacement_attestation" not in reason if label == "capture_attestation"
                        else "capture_attestation" not in reason) for reason in errors)
            assert any(label in reason for reason in errors)


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
