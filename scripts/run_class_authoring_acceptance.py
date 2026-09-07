#!/usr/bin/env python3
"""Bounded class-authoring acceptance; see docs/class-authoring-quality-plan.md."""
from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts/benchmark_bootstrap.py"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark_review_modes as shared
import benchmark_effectiveness as pilot
import effectiveness_custody as custody
from effectiveness_calibration import calibrate

PROVIDERS = {"p01": "codex", "p02": "claude"}
MODELS = {"codex": "gpt-6-astra", "claude": "opus"}
AUTHORING_TASK = (
    "For this class-authoring acceptance task, author a reusable class for the shared blocking "
    "contract violation identified by the validated census manifests. Use the existing response schema."
)
ENTRY_POINTS = ("_validate_capture_attestations", "_validate_replacement_attestations")
REPAIRS = {
    "exact": "type(index) is not int",
    "boolean": "isinstance(index, bool) or not isinstance(index, int)",
}
CLASS_FIELDS = ("class_id", "invariant", "severity", "pattern", "pathspec", "procedure", "members")
STAGES = ("census", "correction", "final")


def require(value, message):
    if not value:
        raise ValueError(message)


def seal(path, value):
    shared.dump(path, value)
    path.with_suffix(path.suffix + ".sha256").write_text(shared.sha(path.read_bytes()))


def sealed(path):
    require(shared.sha(path.read_bytes()) == path.with_suffix(path.suffix + ".sha256").read_text(),
            "sealed record changed: " + path.name)
    return custody.read(path)


def definition(row):
    return {key: row.get(key) for key in CLASS_FIELDS}


def state_file(directory):
    files = list((directory / "state/lineages").glob("*.json"))
    require(len(files) == 1, "unique lineage required")
    return files[0]


def verify_fixture(repo, case, fixture):
    require(shared.git(repo, "rev-parse", "HEAD") == fixture["head"], "fixture HEAD changed")
    require(not shared.git(repo, "status", "--porcelain"), "fixture working tree changed")
    require(shared.git(repo, "log", "--format=%H%x09%aI%x09%an%x09%s", "HEAD") == fixture["history"],
            "fixture history changed")
    for ref, files in ((fixture["base"], fixture["base_files"]), (fixture["head"], case["files"])):
        require(shared.git(repo, "ls-tree", "-r", "--name-only", ref).splitlines() == sorted(files),
                "fixture file inventory changed")
        for name, content in files.items():
            require(subprocess.check_output(["git", "show", ref + ":" + name], cwd=repo) == content.encode(),
                    "fixture committed bytes changed")
    for ref in ("base", "head"):
        require(shared.git(repo, "rev-parse", fixture[ref] + "^{tree}") == fixture[ref + "_tree"],
                "fixture tree changed")
    for name, content in case["files"].items():
        require((repo / name).read_bytes() == content.encode(), "fixture bytes changed")


def manifest(root):
    value = sealed(root / "manifest.json")
    require(value["schema"] == 4 and value["models"] == MODELS, "campaign version/model differs")
    require(value["providers"] == PROVIDERS and value["repairs"] == REPAIRS, "schedule changed")
    require(value["gate_lines"] == gate_lines(value["files"]["defect"]), "gate coordinates differ")
    require(value["maximum"] == 32, "call ceiling changed")
    require(value["authoring_task"] == AUTHORING_TASK, "authoring task changed")
    shared.validate_source(value["source"])
    shared.validate_harness(value["harness"])
    require(shared.sha((ROOT / "docs/class-authoring-quality-plan.md").read_bytes()) == value["plan_sha256"],
            "accepted plan changed")
    for name, digest in value["calibration_sha256"].items():
        require(shared.sha((root / (name + "-calibration.json")).read_bytes()) == digest, "calibration changed")
    return value


def expected_request(m, node, spec, round_no):
    return {
        "repo_path":str(Path(m["execution_root"]) / node / "repository"),
        "engine":spec["case"]["provider"], "model":spec["models"][spec["case"]["provider"]],
        "effort":"high", "web_search":False, "base_ref":spec["fixture"]["base"],
        "head_ref":spec["fixture"]["head"], "lineage":"pilot-" + node.split("-")[0],
        "round":round_no, "stakes":spec["stakes"],
    }


def qualify_node(root, node, m):
    directory = root / node
    binding = sealed(directory / "binding.json")
    spec = sealed(directory / "input.json")
    require(binding["input_sha256"] == shared.sha((directory / "input.json").read_bytes()),
            "node input binding differs")
    provider = PROVIDERS[node.split("-")[0]]
    require(spec["case"]["provider"] == provider, "cross-provider node")
    require(spec["source"] == m["source"] and spec["harness"] == m["harness"]
            and spec["models"] == m["models"] and spec["versions"] == m["versions"]
            and spec["stakes"] == m["stakes"]
            and spec["authoring_task"] == m["authoring_task"], "node execution authority differs")
    verify_fixture(directory / "repository", spec["case"], spec["fixture"])
    require(spec["case"]["files"] == m["files"][node.split("-")[1] if "-" in node else "defect"],
            "wrong repair bytes")
    q = custody.collect_slot(directory, spec)
    require(not q["errors"], "native custody: " + repr(q["errors"]))
    expected_source = {k.removeprefix("src/paranoia_local/"):v for k, v in m["source"]["files"].items()}
    for trace in q["traces"]:
        require(trace["source_changed_since_import"] is False, "native source changed")
        for field in ("source_observed_at_import", "source_observed_at_finish"):
            require(trace[field]["files"] == expected_source
                    and trace[field]["revision"] == m["source"]["revision"], "native source differs")
    events = sealed(directory / "events.json")
    require(len(events) == len(q["outputs"]), "event/output cardinality differs")
    first_round = 2 if "-" in node else 1
    require([e["round"] for e in events] == list(range(first_round, first_round + len(events))),
            "round sequence differs")
    require(len(events) <= (2 if "-" in node else 1), "extra review invocation")
    previous = binding["seed_sha256"]
    for event, output in zip(events, q["outputs"]):
        round_no = event["round"]
        request = custody.read(directory / f"request-{round_no}.json")
        require(request == expected_request(m, node, spec, round_no), "request differs")
        require(shared.sha(json.dumps(request, sort_keys=True)) == event["request_sha256"],
                "request digest differs")
        before = (directory / f"state-before-{round_no}.bin").read_bytes()
        after = (directory / f"state-after-{round_no}.json").read_bytes()
        require(shared.sha(before) == previous == event["before_sha256"], "predecessor differs")
        require(shared.sha(after) == event["after_sha256"], "successor differs")
        require(output["run_id"] == event["run_id"] and output["round"] == round_no,
                "swapped result")
        audits = [a for a in q["audits"] if a["run_id"] == event["run_id"]]
        require(len(audits) == 1, "missing native audit")
        audit, state = audits[0], json.loads(after)
        require(audit["lineage"] == request["lineage"] and audit["round"] == round_no,
                "audit lineage/round differs")
        if audit.get("error") is False:
            require(state["review_state"]["snapshot_digest"] == audit["structural_snapshot"]
                    and state["review_state"]["last_round"] == round_no,
                    "state is not the native successor")
        previous = event["after_sha256"]
    require(events and shared.sha(state_file(directory).read_bytes()) == previous, "terminal state differs")
    require(len({r["sequence"] for r in q["attempts"]}) == len(q["attempts"]),
            "duplicate attempt")
    qualify_authoring_prompts(directory, node, q)
    return q, binding


def qualify_parent(root, node, m):
    q, binding = qualify_node(root, node, m)
    require(q["execution_success"], "parent execution failed")
    assessment = sealed(root / node / "assessment.json")
    state = custody.read(state_file(root / node))
    require(binding["seed_sha256"] == shared.sha(b""), "parent is not fresh")
    require(assessment["state_sha256"] == shared.sha(state_file(root / node).read_bytes()),
            "parent assessment state differs")
    require(assessment["terminal_sha256"] == shared.sha((root / node / "terminal.json").read_bytes()),
            "parent assessment run differs")
    require(assessment["faithful"] is True and assessment["rationale"].strip()
            and assessment["evidence"], "target authoring was not qualified")
    classes = [c for c in state["classes"] if c["class_id"] == assessment["class_id"]]
    require(len(classes) == 1, "target class missing (one-off cannot qualify)")
    target = classes[0]
    require(target["status"] == "open" and target["severity"] in {"BLOCKER", "MAJOR"},
            "target class is not blocking")
    require(definition(target) == assessment["definition"], "target definition differs")
    debt = [d for d in state["review_state"]["debt"]
            if d["status"] == "open" and target["class_id"] in d["class_ids"]]
    require(debt and {d["id"] for d in debt} == set(assessment["debt_ids"]), "target debt misbound")
    for gate in m["gate_lines"]:
        require(any(covers_gate(e, gate) for e in assessment["evidence"]),
                f"parent assessment omits gate {gate}")
        require(any(covers_gate(e, gate) for d in debt for e in d["evidence"]),
                f"parent debt omits gate {gate}")
    require(set(assessment["evidence"]) <= {e for d in debt for e in d["evidence"]},
            "assessment evidence is not target evidence")
    return q, assessment


def qualify_trial_graph(root, *, complete=False):
    """One authority for custody/lineage joins; semantic assessment is explicit."""
    m = manifest(root)
    rows = {}
    for parent in PROVIDERS:
        if (root / parent / "terminal.json").exists():
            rows[parent], _ = qualify_node(root, parent, m)
        for repair in REPAIRS:
            node = parent + "-" + repair
            if not (root / node / "terminal.json").exists():
                require(not complete, "scheduled arm missing: " + node)
                continue
            _, target = qualify_parent(root, parent, m)
            q, binding = qualify_node(root, node, m)
            parent_state = state_file(root / parent).read_bytes()
            require(binding["parent"] == parent
                    and binding["seed_sha256"] == shared.sha(parent_state), "fork seed differs")
            require((root / node / "seed-state.bin").read_bytes() == parent_state, "substituted fork seed")
            require(binding["parent_head"] == sealed(root / parent / "input.json")["fixture"]["head"],
                    "fork repository parent differs")
            require(shared.git(root / node / "repository", "rev-parse", "HEAD^") == binding["parent_head"],
                    "repair is not the prescribed child of parent")
            states = [custody.read(p) for p in sorted((root / node).glob("state-after-*.json"))]
            for state in states:
                targets = [c for c in state["classes"] if c["class_id"] == target["class_id"]]
                require(len(targets) == 1 and definition(targets[0]) == target["definition"],
                        "target class changed")
            if complete:
                require(q["clear_eligible"] and len(q["outputs"]) == 2, "arm did not clear through final")
                require(targets[0]["status"] == "closed", "target class did not close")
                require([a["staged_settlement"]["role"] for a in sorted(q["audits"], key=lambda a:a["round"])] == ["correction", "final"],
                        "required roles did not settle")
            rows[node] = q
    observed = [r["sequence"] for q in rows.values() for r in q["attempts"]]
    count = int((root / "calls.txt").read_text())
    require(sorted(observed) == list(range(1, count + 1)) and count <= 32, "global attempt ledger differs")
    return {"nodes":rows, "calls":count, "complete":complete}


def gate_lines(files):
    lines = [i for i, line in enumerate(files["app.py"].splitlines(), 1)
             if "not isinstance(index, int) or not 0 <= index < len(evidence)" in line]
    require(len(lines) == 2, "recurring fixture must retain exactly two defective gates")
    return lines


def covers_gate(anchor, line):
    match = re.fullmatch(r"repository/app\.py:(\d+)(?:-(\d+))?", anchor)
    return bool(match and int(match[1]) <= line <= int(match[2] or match[1]))


def recurring_files(files):
    files = deepcopy(files)
    entry, replacement = ENTRY_POINTS
    marker = f"def {entry}("
    require(files["app.py"].count(marker) == 1 and replacement not in files["app.py"],
            "original fixture entry point changed")
    body = files["app.py"][files["app.py"].index(marker):]
    files["app.py"] += "\n" + body.replace(marker, f"def {replacement}(", 1)
    phrase = f"{entry} accepts"
    require(files["SPEC.md"].count(phrase) == 1, "original fixture specification changed")
    files["SPEC.md"] = files["SPEC.md"].replace(
        phrase, f"Each of {entry} and {replacement} independently accepts", 1,
    )
    gate_lines(files)
    return files


def calibrate_recurring(files, defective_paths):
    entries = []
    for entry, defective in zip(ENTRY_POINTS, defective_paths, strict=True):
        projected = deepcopy(files)
        if entry == ENTRY_POINTS[1]:
            projected["app.py"] = projected["app.py"].replace(
                f"def {ENTRY_POINTS[0]}(", "def _unused_capture_attestations(", 1,
            ).replace(f"def {entry}(", f"def {ENTRY_POINTS[0]}(", 1)
        result = calibrate("identity", projected, defective)
        require(len(result["checks"]) == 100, "entry-point calibration incomplete")
        entries.append({"entry_point":entry, "projection_app":projected["app.py"], "result":result})
    return {"fixture_files_sha256":{k:shared.sha(v) for k,v in files.items()}, "entries":entries}


def freeze(root, seed):
    original = custody.read(seed)
    source = shared.source_record(ROOT)
    files = {"defect":recurring_files(original["case"]["files"])}
    gate = "not isinstance(index, int)"
    require(files["defect"]["app.py"].count(gate) == 2, "fixture changed")
    for name, repair in REPAIRS.items():
        files[name] = {**files["defect"], "app.py":files["defect"]["app.py"].replace(gate, repair)}
    root.mkdir(parents=True, exist_ok=False)
    files["half"] = {**files["defect"], "app.py":files["defect"]["app.py"].replace(
        gate, REPAIRS["exact"], 1,
    )}
    checks = {name:calibrate_recurring(body, (name == "defect", name in {"defect", "half"}))
              for name, body in files.items()}
    for name, result in checks.items():
        seal(root / (name + "-calibration.json"), result)
    m = {
        "schema":4, "authoring_task":AUTHORING_TASK, "execution_root":str(root), "providers":PROVIDERS, "repairs":REPAIRS,
        "source":source, "models":MODELS, "stakes":original["stakes"], "files":files,
        "gate_lines":gate_lines(files["defect"]),
        "versions":{e:subprocess.check_output([e, "--version"], text=True).strip() for e in PROVIDERS.values()},
        "harness":{str(ROOT / "scripts" / n):shared.sha((ROOT / "scripts" / n).read_bytes())
                   for n in (*pilot.HARNESS_NAMES, Path(__file__).name)},
        "maximum":32, "calibration_sha256":{name:shared.sha((root / (name + "-calibration.json")).read_bytes())
                                         for name in files},
        "plan_sha256":shared.sha((ROOT / "docs/class-authoring-quality-plan.md").read_bytes()),
    }
    seal(root / "manifest.json", m)
    (root / "calls.txt").write_text("0")
    for node, provider in PROVIDERS.items():
        directory = root / node
        fixture = pilot.setup_repo(directory / "repository", files["defect"])
        write_node(root, node, m, original, fixture, b"", None)
    print("Frozen two providers and four continuation arms; no provider calls.")


def write_node(root, node, m, original, fixture, seed, parent):
    from paranoia_local import orientation
    directory = root / node
    spec = deepcopy(original)
    provider = PROVIDERS[node.split("-")[0]]
    spec.update(source=m["source"], models=m["models"], versions=m["versions"], harness=m["harness"],
                counter=str(root / "calls.txt"), maximum=32, fixture=fixture,
                authoring_task=m["authoring_task"])
    spec["slot"] = {"id":node.split("-")[0], "arm":"staged", "case":"identity", "repetition":1}
    spec["case"]["provider"] = provider
    spec["case"]["files"] = m["files"][node.split("-")[1] if parent else "defect"]
    spec["fixture"]["packet_sha256"] = shared.sha(orientation.build_packet(
        directory / "repository", fixture["base"], fixture["head"]))
    seal(directory / "input.json", spec)
    (directory / "seed-state.bin").write_bytes(seed)
    seal(directory / "binding.json", {
        "parent":parent, "parent_head":sealed(root / parent / "input.json")["fixture"]["head"] if parent else None,
        "seed_sha256":shared.sha(seed), "input_sha256":shared.sha((directory / "input.json").read_bytes()),
    })


def fork(root, node):
    m = manifest(root); parent, repair = node.split("-")
    require(repair in REPAIRS, "unknown arm")
    qualify_parent(root, parent, m)
    source = root / parent
    directory = root / node
    require(not directory.exists(), "arm already exists; no rerun")
    shutil.copytree(source / "repository", directory / "repository")
    shutil.copytree(source / "state", directory / "state")
    seed = state_file(source).read_bytes()
    require(state_file(directory).read_bytes() == seed, "copied state differs")
    original = sealed(source / "input.json")
    verify_fixture(directory / "repository", original["case"], original["fixture"])
    (directory / "repository/app.py").write_text(m["files"][repair]["app.py"])
    shared.git(directory / "repository", "add", "app.py")
    shared.git(directory / "repository", "-c", "commit.gpgsign=false", "commit", "-qm", "Prescribed repair")
    fixture = deepcopy(original["fixture"])
    fixture.update(head=shared.git(directory / "repository", "rev-parse", "HEAD"),
                   head_tree=shared.git(directory / "repository", "rev-parse", "HEAD^{tree}"),
                   history=shared.git(directory / "repository", "log", "--format=%H%x09%aI%x09%an%x09%s", "HEAD"))
    write_node(root, node, m, original, fixture, seed, parent)


def required_authoring_schema(original):
    """Narrow only the two approved locations, preserving production policy."""
    try:
        findings = original["properties"]["governing_findings"]
        choices = findings["items"]["properties"]["classification"]["anyOf"]
        require(findings["type"] == "array" and findings["minItems"] == 0,
                "authoring schema unexpected finding bound")
        require(isinstance(choices, list) and len(choices) == 2
                and sorted(c["properties"]["kind"]["const"] for c in choices)
                == ["new_class", "one_off"], "authoring schema unexpected classification alternatives")
    except (KeyError, TypeError) as exc:
        raise ValueError("authoring schema unexpected source shape") from exc
    narrowed = deepcopy(original)
    target = narrowed["properties"]["governing_findings"]
    target["minItems"] = 1
    target["items"]["properties"]["classification"]["anyOf"] = [
        deepcopy(c) for c in choices if c["properties"]["kind"]["const"] == "new_class"
    ]
    return narrowed


def qualify_authoring_schemas(directory, node, q):
    from paranoia_local import engines, staged_protocol as sp
    roles = {role.removesuffix("-validation-retry") for role in q["attempt_roles"].values()}
    records = {p.stem: p for p in (directory / "schema-contracts").glob("*.json")}
    require(set(records) == roles and bool(records), "authoring schema role inventory differs")
    expected = {}
    for role, path in records.items():
        record = sealed(path)
        require(set(record) == {"role", "original", "expected"} and record["role"] == role,
                "authoring schema record shape differs")
        desired = (required_authoring_schema(record["original"])
                   if "-" not in node and role == "consolidation" else record["original"])
        require(record["expected"] == desired, "authoring schema restriction differs")
        expected[role] = shared.sha(sp.canonical_schema(desired))
    files = {p.stem: p for p in (directory / "schemas").glob("*.json")}
    checks = custody.read(directory / "checks.json")
    joined = custody.join_invocations(q["attempts"], checks, q["traces"], [])
    require(set(files) == {check["schema_sha256"] for _, check in joined} and bool(files),
            "authoring schema invocation inventory differs")
    for digest, path in files.items():
        raw = path.read_text(encoding="utf-8")
        require(shared.sha(raw) == digest and sp.canonical_schema(json.loads(raw)) == raw,
                "authoring schema canonical bytes differ")
    for row, check in joined:
        role = q["attempt_roles"][row["sequence"]].removesuffix("-validation-retry")
        require(check["schema_sha256"] == expected[role],
                "authoring schema native role differs")
    if "-" in node:
        return
    # The completed attempt is selected by the native ledger, not by process success:
    # a rejected initial reply is ordinary retry evidence and must remain retained.
    accepted = [(row, check) for row, check in joined
                if check["review_role"].removesuffix("-validation-retry") == "consolidation"
                and any(a["run_id"] == check["run_id"] and any(
                    attempt["role"] == check["review_role"] and attempt["outcome"] == "completed"
                    for attempt in a.get("attempt_ledger", [])) for a in q["audits"])]
    require(len(accepted) == 1, "authoring schema requires one accepted consolidation")
    row, check = accepted[0]
    raw = (directory / row["process_channels"]["stdout"]["file"]).read_text(encoding="utf-8")
    review = engines.get_engine(row["engine"]).parse_output(raw)
    require(not review.error and review.session_ref == row["session_ref"],
            "authoring schema accepted native response differs")
    try:
        sp.decode(review.text, json.loads(files[check["schema_sha256"]].read_text()),
                  max_chars=sp.MAX_DECISION_RESPONSE_CHARS)
    except sp.ProtocolError as exc:
        raise ValueError("authoring schema accepted response violates restriction: " + str(exc)) from exc


@contextmanager
def direct_authoring_scope(directory, *, parent):
    """A disclosed acceptance task; no shipped policy or provider result changes."""
    from paranoia_local import engines, handlers

    original_call = handlers._staged_call
    original_execute = engines.Engine._execute
    prompt_dir = directory / "prompts"
    prompt_dir.mkdir(exist_ok=True)
    schema_dir = directory / "schemas"
    schema_dir.mkdir(exist_ok=True)
    contracts = directory / "schema-contracts"
    contracts.mkdir(exist_ok=True)

    def staged_call(**kwargs):
        def forward(arguments):
            role = arguments["role"]
            original = kwargs["response_schema"]
            expected = (required_authoring_schema(original)
                        if parent and role == "consolidation" else original)
            path = contracts / (role + ".json")
            require(not path.exists(), "authoring schema repeated role")
            seal(path, {"role": role, "original": original, "expected": expected})
            return original_call(**{**arguments, "response_schema": expected})

        if not parent or kwargs["role"] != "consolidation":
            return forward(kwargs)
        original = kwargs["prompt"]
        require(AUTHORING_TASK not in original, "authoring task already present")
        augmented = AUTHORING_TASK + "\n\n" + original
        issue = handlers._staged_prompt_issue(
            augmented, "direct-authoring consolidation prompt",
            maximum=handlers.rc.MAX_CONSOLIDATION_PROMPT_CHARS,
        )
        require(issue is None, issue or "authoring task prompt admission failed")
        record = directory / "authoring-task.json"
        require(not record.exists(), "authoring task may augment only one initial consolidation")
        seal(record, {
            "task": AUTHORING_TASK, "original_prompt": original,
            "original_sha256": shared.sha(original), "prompt": augmented,
            "prompt_sha256": shared.sha(augmented),
        })
        return forward({**kwargs, "prompt": augmented})

    def execute(self, argv, prompt, cwd, runner, timeout, on_progress=None, response_schema=None):
        # These bytes are the actual native invocation, joined to its trace hash.
        (prompt_dir / (shared.sha(prompt) + ".txt")).write_text(prompt, encoding="utf-8")
        from paranoia_local import staged_protocol as sp
        require(isinstance(response_schema, dict) and bool(response_schema), "authoring schema missing")
        raw = sp.canonical_schema(response_schema)
        (schema_dir / (shared.sha(raw) + ".json")).write_text(raw, encoding="utf-8")
        return original_execute(self, argv, prompt, cwd, runner, timeout, on_progress, response_schema)

    handlers._staged_call = staged_call
    engines.Engine._execute = execute
    try:
        yield
    finally:
        handlers._staged_call = original_call
        engines.Engine._execute = original_execute


def qualify_authoring_prompts(directory, node, q):
    qualify_authoring_schemas(directory, node, q)
    files = {p.stem: p for p in (directory / "prompts").glob("*.txt")}
    require(set(files) == {r["prompt_sha256"] for r in q["attempts"]},
            "authoring task invocation prompt inventory differs")
    texts = {}
    for digest, path in files.items():
        text = path.read_text(encoding="utf-8")
        require(shared.sha(text) == digest, "authoring task invocation prompt hash differs")
        texts[digest] = text
    initial = []
    for row in q["attempts"]:
        role = q["attempt_roles"][row["sequence"]]
        text = texts[row["prompt_sha256"]]
        if "-" not in node and role == "consolidation":
            initial.append(row)
        else:
            require(AUTHORING_TASK not in text, "authoring task escaped initial parent consolidation")
    record_path = directory / "authoring-task.json"
    if "-" in node:
        require(not initial and not record_path.exists(), "authoring task present in continuation")
        return
    require(len(initial) == 1, "authoring task requires one initial consolidation")
    record = sealed(record_path)
    require(set(record) == {"task", "original_prompt", "original_sha256", "prompt", "prompt_sha256"},
            "authoring task record shape differs")
    require(record["task"] == AUTHORING_TASK and AUTHORING_TASK not in record["original_prompt"],
            "authoring task definition differs")
    require(record["prompt"] == AUTHORING_TASK + "\n\n" + record["original_prompt"]
            and record["original_sha256"] == shared.sha(record["original_prompt"])
            and record["prompt_sha256"] == shared.sha(record["prompt"]),
            "authoring task exact augmentation differs")
    require(initial[0]["operation"] == "run"
            and initial[0]["prompt_sha256"] == record["prompt_sha256"],
            "authoring task native invocation differs")


def mutate_invocation_prompt(directory, digest, text):
    """Reseal only a disposable negative-control invocation, including native joins."""
    replacement = shared.sha(text)
    old = directory / "prompts" / (digest + ".txt")
    (old.parent / (replacement + ".txt")).write_text(text, encoding="utf-8")
    old.unlink()
    path = directory / "attempts.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        if row["prompt_sha256"] == digest:
            row["prompt_sha256"] = replacement
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    checks = custody.read(directory / "checks.json")
    for row in checks:
        if row["prompt_sha256"] == digest:
            row["prompt_sha256"] = replacement
    shared.dump(directory / "checks.json", checks)
    for path in (directory / "logs").glob("*-run-*.json"):
        trace = custody.read(path)
        for row in trace["attempts"]:
            if row["prompt_sha256"] == digest:
                row["prompt_sha256"] = replacement
        shared.dump(path, trace)


def mutate_invocation_schema(directory, check, schema):
    """Reseal a disposable native schema while preserving its invocation identity."""
    from paranoia_local import staged_protocol as sp
    raw = sp.canonical_schema(schema)
    digest = shared.sha(raw)
    (directory / "schemas" / (digest + ".json")).write_text(raw, encoding="utf-8")
    checks = custody.read(directory / "checks.json")
    for row in checks:
        if (row["run_id"], row["review_role"]) == (check["run_id"], check["review_role"]):
            row["schema_sha256"] = digest
    shared.dump(directory / "checks.json", checks)
    for path in (directory / "logs").glob("*-run-*.json"):
        trace = custody.read(path)
        if trace["run_id"] == check["run_id"]:
            for row in trace["attempts"]:
                if row["prompt_sha256"] == check["prompt_sha256"]:
                    row["schema_sha256"] = digest
            shared.dump(path, trace)
    used = {row["schema_sha256"] for row in checks}
    for path in (directory / "schemas").glob("*.json"):
        if path.stem not in used:
            path.unlink()


def mutate_accepted_response(directory, q):
    """Keep native channel joins intact while violating only the test schema."""
    from paranoia_local import engines, staged_protocol as sp
    accepted = [attempt for audit in q["audits"] for attempt in audit["attempt_ledger"]
                if attempt["role"].removesuffix("-validation-retry") == "consolidation"
                and attempt["outcome"] == "completed"]
    require(len(accepted) == 1, "response control requires one accepted consolidation")
    attempt = accepted[0]
    row = next(row for row in q["attempts"]
               if q["attempt_roles"][row["sequence"]] == attempt["role"])
    path = directory / row["process_channels"]["stdout"]["file"]
    raw = path.read_text(encoding="utf-8")
    reply = engines.get_engine(row["engine"]).parse_output(raw)
    value = json.loads(reply.text)
    finding = value["governing_findings"][0]
    require(len(finding["source_ids"]) > 1, "response control needs distinct lane sources")
    extra = deepcopy(finding)
    extra["id"] = "control-one-off"
    extra["source_ids"] = [finding["source_ids"].pop()]
    extra["classification"] = {"kind": "one_off", "reason": "Independent localized defect."}
    value["governing_findings"].append(extra)
    text = json.dumps(value)
    original = sealed(directory / "schema-contracts/consolidation.json")["original"]
    sp.decode(text, original, max_chars=sp.MAX_DECISION_RESPONSE_CHARS)
    if row["engine"] == "codex":
        events = [json.loads(line) for line in raw.splitlines()]
        messages = [event["item"] for event in events
                    if isinstance(event.get("item"), dict)
                    and event["item"].get("type") == "agent_message"]
        messages[-1]["text"] = text
        raw = "\n".join(json.dumps(event) for event in events)
    else:
        envelope = json.loads(raw)
        envelope["structured_output"] = value
        raw = json.dumps(envelope)
    path.write_text(raw, encoding="utf-8")
    digest = shared.sha(path.read_bytes())
    rows = custody.attempts(directory)
    for target in rows:
        if target["sequence"] == row["sequence"]:
            target["raw_sha256"] = digest
            target["process_channels"]["stdout"].update(sha256=digest, bytes=len(path.read_bytes()))
    (directory / "attempts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    checks = custody.read(directory / "checks.json")
    for check in checks:
        if check["raw_sha256"] == row["raw_sha256"] and check["session_ref"] == row["session_ref"]:
            check["raw_sha256"] = digest
    shared.dump(directory / "checks.json", checks)
    for audit_path in (directory / "logs").glob("*-critique_branch-*.json"):
        audit = custody.read(audit_path)
        for target in audit.get("attempt_ledger", []):
            if target["role"] == attempt["role"]:
                target["raw_sha256"] = digest
        shared.dump(audit_path, audit)


def run_node(root, node):
    # The observer's counter has its own short lock. Hold the existing campaign
    # directory open for this separate, transient whole-node serial admission.
    descriptor = os.open(root, os.O_RDONLY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another campaign node is running; wait for terminal qualification") from exc
        _run_node(root, node)
    finally:
        os.close(descriptor)


def _run_node(root, node):
    m = manifest(root)
    directory = root / node
    require(not (directory / "terminal.json").exists(), "terminal node cannot rerun")
    if "-" in node:
        qualify_parent(root, node.split("-")[0], m)
    spec, binding = sealed(directory / "input.json"), sealed(directory / "binding.json")
    require(spec["authoring_task"] == m["authoring_task"], "authoring task input changed")
    require((directory / "seed-state.bin").read_bytes() == (
        state_file(directory).read_bytes() if "-" in node else b""), "initial seed differs")
    require(shared.sha((directory / "seed-state.bin").read_bytes()) == binding["seed_sha256"], "seed binding differs")
    if "-" in node:
        parent = node.split("-")[0]
        require(binding["parent"] == parent and state_file(root / parent).read_bytes() == state_file(directory).read_bytes(),
                "fork is not exact parent state")
        require(shared.git(directory / "repository", "rev-parse", "HEAD^") == binding["parent_head"]
                == sealed(root / parent / "input.json")["fixture"]["head"], "wrong parent snapshot")
    for name, version in m["versions"].items():
        require(subprocess.check_output([name, "--version"], text=True).strip() == version, "CLI changed")
    for name, digest in m["calibration_sha256"].items():
        require(shared.sha((root / (name + "-calibration.json")).read_bytes()) == digest, "calibration changed")
    from paranoia_local import server, engines
    os.environ["PARANOIA_STATE_ROOT"] = str(directory / "state")
    original_admit = shared.admit
    def admit(counter):
        try:
            return original_admit(counter, maximum=32)
        except RuntimeError as exc:
            raise pilot.AdmissionRefused(str(exc)) from exc
    shared.admit = admit
    shared.install_observer(engines, directory, root / "calls.txt")
    pilot.verify_fixture = verify_fixture
    pilot.install_checks(engines, spec, directory / "repository", directory)
    events, failure, dispatch_ms = [], None, 0
    started = time.perf_counter()
    try:
        for round_no in ((2, 3) if "-" in node else (1,)):
            manifest(root)
            verify_fixture(directory / "repository", spec["case"], spec["fixture"])
            request = expected_request(m, node, spec, round_no)
            shared.dump(directory / f"request-{round_no}.json", request)
            before = state_file(directory).read_bytes() if round_no > 1 else b""
            (directory / f"state-before-{round_no}.bin").write_bytes(before)
            shared.CURRENT_STAGE[0] = STAGES[round_no - 1]
            call_started = time.perf_counter()
            try:
                with direct_authoring_scope(directory, parent="-" not in node):
                    result = server.dispatch("critique_branch", request,
                        default_engine_name=spec["case"]["provider"], log_dir=directory / "logs",
                        on_progress=lambda s:print(s, flush=True))
            finally:
                elapsed = round((time.perf_counter() - call_started) * 1000)
                dispatch_ms += elapsed
            traces = [custody.read(p) for p in (directory / "logs").glob("*-run-*.json")]
            traces = [t for t in traces if t["result_sha256"] == shared.sha(result)]
            require(len(traces) == 1, "dispatch trace ambiguous")
            run_id = traces[0]["run_id"]
            shared.dump(directory / f"output-{round_no}.json", {
                "mode":"critique_branch", "round":round_no, "result":result,
                "elapsed_ms":elapsed, "run_id":run_id,
            })
            after = state_file(directory).read_bytes()
            (directory / f"state-after-{round_no}.json").write_bytes(after)
            events.append({"round":round_no, "run_id":run_id, "before_sha256":shared.sha(before),
                           "after_sha256":shared.sha(after),
                           "request_sha256":shared.sha(json.dumps(request, sort_keys=True))})
            seal(directory / "events.json", events)
            custody.terminal(directory, "completed",
                elapsed_ms=round((time.perf_counter() - started) * 1000), dispatch_ms=dispatch_ms)
            q, _ = qualify_node(root, node, m)
            require(q["execution_success"], "native execution failed")
            if "-" in node:
                qualify_trial_graph(root)
            print(result, flush=True)
            if json.loads(after)["review_state"]["phase"] != "final":
                break
    except Exception as exc:
        failure = type(exc).__name__ + ": " + str(exc)
    custody.terminal(directory, "failed" if failure else "completed", failure,
        elapsed_ms=round((time.perf_counter() - started) * 1000), dispatch_ms=dispatch_ms)
    print(json.dumps({"node":node, "failure":failure, "dispatch_ms":dispatch_ms}), flush=True)



def check_replay(root):
    """Mutate disposable copies of real records, never original provider evidence."""
    import tempfile

    qualify_trial_graph(root, complete=True)
    cases = (
        "one-off", "parent", "fork-seed", "swapped-state", "swapped-result",
        "head", "snapshot", "channel", "cross-provider", "missing-audit", "duplicate-attempt",
        "gate-assessment-0", "gate-assessment-1", "gate-debt-0", "gate-debt-1",
        "task-missing", "task-modified", "task-in-lane",
        "schema-missing", "schema-restriction", "schema-lane", "schema-continuation",
        "schema-retry", "response-initial", "response-retry",
    )
    results = []
    for case in cases:
        response_node = None
        if case in {"schema-retry", "response-initial", "response-retry"}:
            retry = case != "response-initial"
            for parent in PROVIDERS:
                q, _ = qualify_node(root, parent, manifest(root))
                accepted_roles = {a["role"] for audit in q["audits"] for a in audit["attempt_ledger"]
                                  if a["outcome"] == "completed"}
                wanted = "consolidation-validation-retry" if retry else "consolidation"
                if wanted in accepted_roles:
                    response_node = parent
                    break
            if response_node is None:
                results.append({"mutation": case, "not_applicable": "No accepted " + wanted
                                + " attempt in this retained graph; deterministic graph tests own this control.",
                                "dependent_calls": 0})
                continue
        with tempfile.TemporaryDirectory(prefix="class-authoring-negative-") as tmp:
            copy = Path(tmp) / "records"
            shutil.copytree(root, copy)
            node = "p01" if case == "one-off" or case.startswith(("gate-", "task-")) else "p01-exact"
            if case.startswith(("schema-", "response-")):
                node = ("p01-exact" if case == "schema-continuation" else
                        "p02" if case == "response-initial" else "p01")
            if response_node is not None:
                node = response_node
            directory = copy / node
            parent_control = "-" not in node
            if case.startswith("response-"):
                q, _ = qualify_node(copy, node, manifest(copy))
                mutate_accepted_response(directory, q)
            elif case.startswith("schema-"):
                q, _ = qualify_node(copy, node, manifest(copy))
                role = ("census-behaviour" if case == "schema-lane" else
                        "correction" if case == "schema-continuation" else
                        "consolidation-validation-retry" if case == "schema-retry" else "consolidation")
                checks = custody.read(directory / "checks.json")
                check = next(row for row in checks if row["review_role"] == role)
                record_path = directory / "schema-contracts" / (role.removesuffix("-validation-retry") + ".json")
                record = sealed(record_path)
                if case == "schema-missing":
                    record_path.unlink()
                else:
                    schema = deepcopy(record["original"] if case == "schema-retry" else
                                      sealed(copy / "p01/schema-contracts/consolidation.json")["expected"])
                    if case == "schema-restriction":
                        schema["properties"]["governing_findings"]["minItems"] = 0
                        record["expected"] = schema
                        seal(record_path, record)
                    mutate_invocation_schema(directory, check, schema)
            elif case.startswith("task-"):
                q, _ = qualify_node(copy, "p01", manifest(copy))
                role = "census-behaviour" if case == "task-in-lane" else "consolidation"
                row = next(r for r in q["attempts"] if q["attempt_roles"][r["sequence"]] == role)
                text = (directory / "prompts" / (row["prompt_sha256"] + ".txt")).read_text()
                if case == "task-missing":
                    text = text.removeprefix(AUTHORING_TASK + "\n\n")
                elif case == "task-modified":
                    text = text.replace(AUTHORING_TASK, "Changed authoring task", 1)
                else:
                    text = AUTHORING_TASK + "\n\n" + text
                mutate_invocation_prompt(directory, row["prompt_sha256"], text)
            elif case.startswith("gate-"):
                gate = manifest(copy)["gate_lines"][int(case[-1])]
                if case.startswith("gate-assessment"):
                    assessment = sealed(directory / "assessment.json")
                    assessment["evidence"] = [e for e in assessment["evidence"] if not covers_gate(e, gate)]
                    seal(directory / "assessment.json", assessment)
                else:
                    state = custody.read(state_file(directory))
                    for debt in state["review_state"]["debt"]:
                        debt["evidence"] = [e for e in debt["evidence"] if not covers_gate(e, gate)]
                    shared.dump(state_file(directory), state)
                    (directory / "state-after-1.json").write_bytes(state_file(directory).read_bytes())
            elif case == "one-off":
                state = custody.read(state_file(directory))
                state["classes"] = []
                for debt in state["review_state"]["debt"]:
                    debt["class_ids"] = []
                shared.dump(state_file(directory), state)
                (directory / "state-after-1.json").write_bytes(state_file(directory).read_bytes())
            elif case == "parent":
                value = sealed(directory / "binding.json")
                value["parent"] = "p02"
                seal(directory / "binding.json", value)
            elif case == "fork-seed":
                (directory / "seed-state.bin").write_bytes(state_file(copy / "p02").read_bytes())
            elif case == "swapped-state":
                raw = state_file(copy / "p01-boolean").read_bytes()
                state_file(directory).write_bytes(raw)
                (directory / "state-after-3.json").write_bytes(raw)
            elif case == "swapped-result":
                shutil.copy2(copy / "p01-boolean/output-3.json", directory / "output-3.json")
            elif case == "head":
                spec = sealed(directory / "input.json")
                spec["fixture"]["head"] = sealed(copy / "p01-boolean/input.json")["fixture"]["head"]
                seal(directory / "input.json", spec)
                binding = sealed(directory / "binding.json")
                binding["input_sha256"] = shared.sha((directory / "input.json").read_bytes())
                seal(directory / "binding.json", binding)
            elif case == "snapshot":
                with (directory / "repository/app.py").open("a") as handle:
                    handle.write("\nchanged_snapshot = True\n")
            elif case in {"channel", "cross-provider"}:
                path = next(directory.glob("provider-*.txt"))
                path.write_bytes(
                    next((copy / "p02").glob("provider-*.txt")).read_bytes()
                    if case == "cross-provider" else path.read_bytes() + b"altered"
                )
            elif case == "missing-audit":
                next((directory / "logs").glob("*-critique_branch-*.json")).unlink()
            else:
                path = directory / "attempts.jsonl"
                with path.open("a") as handle:
                    handle.write(path.read_text().splitlines()[0] + "\n")
            if case in {"one-off", "swapped-state"} or case.startswith("gate-debt"):
                events = sealed(directory / "events.json")
                events[-1]["after_sha256"] = shared.sha(state_file(directory).read_bytes())
                seal(directory / "events.json", events)
            # Reseal the mutated copy so relational/native joins must reject it.
            terminal = custody.read(directory / "terminal.json")
            custody.terminal(directory, terminal["outcome"], terminal["error"],
                             elapsed_ms=terminal["elapsed_ms"], dispatch_ms=terminal["dispatch_ms"])
            if parent_control:
                assessment = sealed(directory / "assessment.json")
                assessment["state_sha256"] = shared.sha(state_file(directory).read_bytes())
                assessment["terminal_sha256"] = shared.sha((directory / "terminal.json").read_bytes())
                seal(directory / "assessment.json", assessment)
            try:
                qualify_trial_graph(copy, complete=True)
            except ValueError as exc:
                results.append({"mutation":case, "rejection":str(exc)})
            else:
                raise ValueError("negative control was accepted: " + case)
            if case.startswith(("gate-", "task-", "schema-", "response-")):
                expected = ("authoring schema" if case.startswith(("schema-", "response-")) else
                            "authoring task" if case.startswith("task-") else
                            "parent assessment omits gate" if "assessment" in case else "parent debt omits gate")
                require(expected in results[-1]["rejection"], "gate control rejected at the wrong boundary")
                if not parent_control:
                    continue
                before = (copy / "calls.txt").read_bytes()
                try:
                    fork(copy, node + "-exact")
                except ValueError as exc:
                    require(expected in str(exc), "fork did not reject incomplete parent coverage")
                else:
                    raise ValueError("fork admitted incomplete parent coverage")
                require((copy / "calls.txt").read_bytes() == before, "negative control spent provider calls")
                results[-1]["dependent_calls"] = 0
    qualify_trial_graph(root, complete=True)
    seal(root / "replay-checks.json", {"positive_replay":True, "negative_controls":results})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--freeze", type=Path, metavar="SEED_INPUT")
    parser.add_argument("--fork")
    parser.add_argument("--run")
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--check-replay", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.check_replay:
        print(json.dumps(check_replay(root), indent=2))
    elif args.freeze:
        freeze(root, args.freeze)
    elif args.fork:
        fork(root, args.fork)
    elif args.run:
        run_node(root, args.run)
    else:
        q = qualify_trial_graph(root, complete=args.qualify)
        print(json.dumps({"calls":q["calls"], "nodes":list(q["nodes"]), "complete":q["complete"]}))


if __name__ == "__main__":
    main()
