"""Acceptance orchestration tests; scripted judgments are not live quality evidence."""
import json
import tarfile
from pathlib import Path

from paranoia_local import engines
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

    def execute(self, argv, prompt, cwd, runner, timeout, on_progress=None, response_schema=None):
        anchor = "repository/app.py:23"
        finding = {
            "id":"identity", "severity":"MAJOR",
            "summary":"Boolean identity admitted by the integer gate.",
            "evidence":[anchor], "remedy":"Reject non-integer JSON identities.",
        }
        if "ROLE: census lane " in prompt:
            name = next(l.split()[-1] for l in prompt.splitlines()
                        if l.startswith("ROLE: census lane "))
            value = json.loads(lane(name, findings=[finding]))
            text = json.dumps(value).replace("plan:1", anchor)
        else:
            task = json.loads(prompt.split("===== TASK INPUT =====\n\n", 1)[1])
            if task["role"] == "census":
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
                cls = task["active_classes"][0]
                value = {
                    "role":task["role"], "governing_findings":[],
                    "debt_outcomes":[{"debt_id":d["id"], "status":"closed", "evidence":[anchor]}
                                     for d in task["existing_debt"]],
                    "class_outcomes":{cls["class_id"]:{
                        "verdict":"satisfied", "member_coverage":[{
                            "member_id":"integer-identity", "evidence":[anchor],
                        }],
                    }}, "class_actions":{cls["class_id"]:None},
                }
                if task["role"] == "final":
                    value["coverage"] = payload(lane())["coverage"]
                    for row in value["coverage"]:
                        row["evidence"] = [anchor]
            text = wire(value)
        return engines.Review(text=text, raw=text, session_ref="scripted-" + self.name,
                              returncode=0, error=False, duration_ms=1,
                              provider_duration_ms=1, stderr="", failure_detail="")
    monkeypatch.setattr(engines.Engine, "_execute", execute)

    acceptance.freeze(root, seed)
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
            "debt_ids":[d["id"] for d in debt], "evidence":["repository/app.py:23"],
        })
        for repair in acceptance.REPAIRS:
            node = parent + "-" + repair
            acceptance.fork(root, node)
            run(node)
    qualified = acceptance.qualify_trial_graph(root, complete=True)
    assert qualified["calls"] == 16
    results = acceptance.check_replay(root)
    assert len(results) == 11
    assert all(row["rejection"] for row in results)

