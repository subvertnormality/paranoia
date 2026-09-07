#!/usr/bin/env python3
"""Frozen reviewer-blinded effectiveness pilot (Linux/WSL)."""
from __future__ import annotations

import argparse
from collections import Counter
from functools import wraps
import inspect
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time

BOOTSTRAP = Path(__file__).with_name("benchmark_bootstrap.py")
runpy.run_path(str(BOOTSTRAP))
import benchmark_review_modes as shared
import effectiveness_custody as custody

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("single", "staged")
REPETITIONS = 2
CALL_LIMIT = 192
STAKES = (
    "One trusted operator and OS, static untrusted fixture code/specification and provider data. "
    "Caller-enforced input domains, one local caller, no concurrency inside fixture functions. "
    "Reviewers read but do not execute repository-selected code. Ordinary edits invalidate "
    "the review. Existing provider CLI boundary; no web research. Tens to hundreds of lines, "
    "evidence useful within minutes. False clear and wrong binding have high impact; recoverable "
    "blocking acceptable. Exclude hostile local races, OS compromise, corrupted-state recovery, "
    "multi-tenancy, external source verification and optional enhancements."
)
QUESTION = (
    "Review app.py against SPEC.md and the supplied helpers.py context. Identify every concrete "
    "reachable contract violation with severity, file:line, trigger and consequence. Distinguish "
    "optional advice from required repairs. If none, explicitly say there are no actionable "
    "contract defects. Read only; do not execute repository code or tests."
)
HARNESS_NAMES = (
    "benchmark_effectiveness.py", "effectiveness_custody.py", "effectiveness_corpus.py",
    "score_effectiveness.py", "benchmark_review_modes.py",
    "benchmark_bootstrap.py",
)


def schedule(cases):
    rows = []
    for repetition in range(REPETITIONS):
        for index, case in enumerate(cases):
            arms = ARMS if (index + repetition) % 2 == 0 else tuple(reversed(ARMS))
            for arm in arms:
                rows.append({"id": f"t{len(rows)+1:03}", "case": case["id"],
                             "arm": arm, "repetition": repetition})
    return rows


def setup_repo(repo, files):
    repo.mkdir(parents=True)
    shared.git(repo, "init", "-q", "-b", "main")
    shared.git(repo, "config", "user.name", "fixture")
    shared.git(repo, "config", "user.email", "fixture@example.test")
    env = dict(os.environ, GIT_AUTHOR_DATE="2020-01-01T00:00:00+00:00",
               GIT_COMMITTER_DATE="2020-01-01T00:00:00+00:00")
    def commit(message):
        shared.git(repo, "add", ".")
        subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", message],
                       cwd=repo, env=env, check=True, capture_output=True)
        return shared.git(repo, "rev-parse", "HEAD")
    (repo / "SPEC.md").write_text(files["SPEC.md"])
    (repo / "app.py").write_text("")
    base = commit("Specification")
    for name, text in files.items():
        (repo / name).write_text(text)
    head = commit("Implementation")
    return {"base": base, "head": head,
            "history": shared.git(repo, "log", "--format=%H%x09%aI%x09%an%x09%s", "HEAD")}


def verify_fixture(repo, case, fixture):
    if shared.git(repo, "rev-parse", "HEAD") != fixture["head"]:
        raise ValueError("fixture HEAD changed")
    if shared.git(repo, "status", "--porcelain"):
        raise ValueError("fixture working tree changed")
    if shared.git(repo, "log", "--format=%H%x09%aI%x09%an%x09%s", "HEAD") != fixture["history"]:
        raise ValueError("fixture history changed")
    if shared.git(repo, "rev-list", "--count", "HEAD") != "2":
        raise ValueError("unexpected reachable fixture history")
    if shared.git(repo, "show", fixture["base"] + ":app.py") != "":
        raise ValueError("fixture base contains an implementation")
    for name, text in case["files"].items():
        if (repo / name).read_bytes() != text.encode():
            raise ValueError("fixture file changed: " + name)


def load_manifest(root):
    raw = (root / "manifest.json").read_bytes()
    if shared.sha(raw) != (root / "manifest.sha256").read_text().strip():
        raise ValueError("manifest changed")
    m = json.loads(raw)
    required = {"schema", "source", "harness", "models", "versions", "stakes", "question",
                "cases", "order", "fixtures", "oracle_sha256", "call_limit", "plan_sha256"}
    if set(m) != required or m["schema"] != 1:
        raise ValueError("closed manifest required")
    if (m["order"] != schedule(m["cases"]) or type(m["call_limit"]) is not int
            or not 0 < m["call_limit"] <= CALL_LIMIT):
        raise ValueError("schedule/admission changed")
    if len(m["cases"]) != 8 or Counter(c["provider"] for c in m["cases"]) != {"codex": 4, "claude": 4}:
        raise ValueError("invalid provider/case cardinality")
    if len({c["id"] for c in m["cases"]}) != len(m["cases"]):
        raise ValueError("duplicate case")
    if shared.sha((root / "oracle.json").read_bytes()) != m["oracle_sha256"]:
        raise ValueError("oracle changed")
    shared.validate_source(m["source"])
    shared.validate_harness(m["harness"])
    if shared.sha((ROOT / "docs/effectiveness-lifecycle-plan.md").read_bytes()) != m["plan_sha256"]:
        raise ValueError("contract changed")
    return m


def specification(root, manifest, row):
    case = next(c for c in manifest["cases"] if c["id"] == row["case"])
    return {"slot": row, "arm": row["arm"], "case": case,
            "fixture": manifest["fixtures"][row["id"]], "source": manifest["source"],
            "models": manifest["models"], "versions": manifest["versions"],
            "stakes": manifest["stakes"], "question": manifest["question"],
            "harness": manifest["harness"], "counter": str(root / "calls.txt"),
            "maximum": manifest["call_limit"]}


def freeze(root, source, call_limit=CALL_LIMIT):
    from effectiveness_corpus import build
    selected = shared.source_record(source)
    sys.path.insert(0, str(Path(selected["path"]) / "src"))
    from paranoia_local import orientation
    root.mkdir(parents=True, exist_ok=False)
    cases, oracle = build(ROOT)
    shared.dump(root / "oracle.json", oracle)
    manifest = {
        "schema": 1, "source": selected,
        "harness": {str(ROOT / "scripts" / n): shared.sha((ROOT / "scripts" / n).read_bytes())
                    for n in HARNESS_NAMES},
        "models": shared.MODELS, "versions": {
            name: subprocess.check_output([name, "--version"], text=True).strip()
            for name in shared.MODELS},
        "stakes": STAKES, "question": QUESTION, "cases": cases, "order": schedule(cases),
        "fixtures": {}, "oracle_sha256": shared.sha((root / "oracle.json").read_bytes()),
        "call_limit": call_limit,
        "plan_sha256": shared.sha((ROOT / "docs/effectiveness-lifecycle-plan.md").read_bytes()),
    }
    for row in manifest["order"]:
        case = next(c for c in cases if c["id"] == row["case"])
        directory = root / row["id"]
        fixture = setup_repo(directory / "repository", case["files"])
        packet = orientation.build_packet(directory / "repository", fixture["base"], fixture["head"])
        fixture["packet_sha256"] = shared.sha(packet)
        manifest["fixtures"][row["id"]] = fixture
        shared.dump(directory / "input.json", specification(root, manifest, row))
    (root / "calls.txt").write_text("0")
    shared.dump(root / "manifest.json", manifest)
    (root / "manifest.sha256").write_text(shared.sha((root / "manifest.json").read_bytes()))
    load_manifest(root)
    print(f"Frozen {len(manifest['order'])} slots; no provider calls")


def install_checks(engines, spec, repo, directory):
    from paranoia_local import orientation
    checks, lock = [], threading.Lock()
    for operation in ("run", "resume"):
        original = getattr(engines.Engine, operation)
        signature = inspect.signature(original)
        def wrap(original=original, signature=signature, operation=operation):
            @wraps(original)
            def checked(*args, **kwargs):
                v = signature.bind(*args, **kwargs).arguments
                verify_fixture(repo, spec["case"], spec["fixture"])
                cwd = Path(v["cwd"])
                packet = orientation.build_packet(repo, spec["fixture"]["base"], spec["fixture"]["head"])
                if shared.sha(packet) != spec["fixture"]["packet_sha256"]:
                    raise ValueError("fixture packet changed")
                inspect_prompt(v["prompt"], spec, repo, operation, v.get("response_schema"))
                if spec["arm"] == "single":
                    if cwd.resolve() != repo.resolve():
                        raise ValueError("query cwd differs")
                else:
                    verify_fixture(cwd, spec["case"], spec["fixture"])
                    common = Path(shared.git(cwd, "rev-parse", "--git-common-dir"))
                    if not common.is_absolute():
                        common = cwd / common
                    if common.resolve() != (repo / ".git").resolve():
                        raise ValueError("staged worktree belongs to a different fixture")
                row = {"engine": v["self"].name, "prompt_sha256": shared.sha(v["prompt"]),
                       "fixture_ok": True, "packet_sha256": shared.sha(packet),
                       "cwd": str(cwd), "raw_sha256": None}
                try:
                    review = original(*args, **kwargs)
                    row["raw_sha256"] = shared.sha(review.raw or "")
                    return review
                finally:
                    try:
                        verify_fixture(repo, spec["case"], spec["fixture"])
                    except Exception:
                        row["fixture_ok"] = False
                        raise
                    finally:
                        with lock:
                            checks.append(row)
                            shared.dump(directory / "checks.json", checks)
            return checked
        setattr(engines.Engine, operation, wrap())
    shared.dump(directory / "checks.json", checks)


def inspect_prompt(prompt, spec, repo, operation, schema):
    """Check native initial context and withheld metadata before provider admission."""
    if any(marker in prompt for marker in (
            "oracle.json", "human-private-map.json", "score.json",
            "historical-extracted", "oracle_sha256", "witness_sha256")):
        raise ValueError("benchmark metadata contaminated provider prompt")
    if spec["arm"] == "single":
        from paranoia_local import handlers, prompts
        expected = prompts.compose(prompts.QUERY_INSTRUCTIONS, handlers._query_body(
            spec["question"], [], None, repo_grounded=True))
        if prompt != expected:
            raise ValueError("query prompt differs from frozen native input")
    elif operation == "run" and schema and "lane" in schema.get("properties", {}):
        diff = shared.git(repo, "diff", "--no-ext-diff", spec["fixture"]["base"],
                          spec["fixture"]["head"], "--")
        if diff not in prompt:
            raise ValueError("census prompt lacks exact frozen fixture diff")


def worker(path, expected_digest):
    if shared.sha(path.read_bytes()) != expected_digest:
        raise ValueError("worker input differs from frozen launch")
    spec = custody.read(path)
    directory, repo = path.parent, path.parent / "repository"
    started_slot = time.perf_counter()
    dispatch_ms = 0
    outcome, failure = "failed", None
    try:
        shared.validate_harness(spec["harness"])
        shared.validate_source(spec["source"])
        verify_fixture(repo, spec["case"], spec["fixture"])
        for engine, version in spec["versions"].items():
            if subprocess.check_output([engine, "--version"], text=True).strip() != version:
                raise ValueError("provider version changed")
        sys.path.insert(0, str(Path(spec["source"]["path"]) / "src"))
        from paranoia_local import server, engines, class_closure as cc
        os.environ[cc.STATE_ROOT_ENV] = str(directory / "state")
        original_admit = shared.admit
        shared.admit = lambda counter: original_admit(counter, maximum=spec["maximum"])
        shared.install_observer(engines, directory, Path(spec["counter"]))
        install_checks(engines, spec, repo, directory)
        provider = spec["case"]["provider"]
        common = {"repo_path": str(repo), "engine": provider, "model": spec["models"][provider],
                  "effort": "high", "web_search": False}
        for round_no in range(1, 3 if spec["arm"] == "staged" else 2):
            mode = "critique_branch" if spec["arm"] == "staged" else "query"
            args = {**common, "question": spec["question"]} if mode == "query" else {
                **common, "base_ref": spec["fixture"]["base"], "head_ref": spec["fixture"]["head"],
                "lineage": "pilot-" + spec["slot"]["id"], "round": round_no, "stakes": spec["stakes"],
            }
            started = time.perf_counter()
            try:
                result = server.dispatch(mode, args, default_engine_name=provider, log_dir=directory / "logs")
            finally:
                elapsed = round((time.perf_counter() - started) * 1000)
                dispatch_ms += elapsed
            traces = [custody.read(p) for p in (directory / "logs").glob("*.json")]
            traces = [t for t in traces if t.get("tool") == "run"
                      and t.get("result_sha256") == shared.sha(result)]
            if len(traces) != 1:
                raise ValueError("missing unique dispatch trace")
            shared.dump(directory / f"output-{round_no}.json", {
                "mode": mode, "round": round_no, "result": result, "elapsed_ms": elapsed,
                "run_id": traces[0]["run_id"],
            })
            if mode == "query":
                break
            state = custody.read(next((directory / "state" / "lineages").glob("*.json")))
            review = state.get("review_state", {})
            if review.get("phase") != "final":
                break
        shared.validate_source(spec["source"])
        verify_fixture(repo, spec["case"], spec["fixture"])
        outcome = "completed"
    except Exception as exc:
        failure = type(exc).__name__ + ": " + str(exc)
    custody.terminal(directory, outcome, failure,
                     elapsed_ms=round((time.perf_counter() - started_slot) * 1000),
                     dispatch_ms=dispatch_ms)


def run(root):
    manifest = load_manifest(root)
    for row in manifest["order"]:
        directory = root / row["id"]
        if (directory / "terminal.json").exists():
            continue
        load_manifest(root)
        spec = specification(root, manifest, row)
        if custody.read(directory / "input.json") != spec:
            raise ValueError("selected input changed before launch")
        verify_fixture(directory / "repository", spec["case"], spec["fixture"])
        print("Running", row["id"], flush=True)
        p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker",
                            str(directory / "input.json"), "--digest",
                            shared.sha((directory / "input.json").read_bytes())],
                           capture_output=True, text=True)
        shared.dump(root / (row["id"] + "-worker.json"), {
            "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
        })
        if not (directory / "terminal.json").exists():
            custody.terminal(directory, "failed", "worker exited without terminal record")
        with (root / "completions.jsonl").open("a") as f:
            f.write(json.dumps({"id": row["id"], "sha256": shared.sha(
                (directory / "terminal.json").read_bytes())}) + "\n")
        print(row["id"], custody.read(directory / "terminal.json")["outcome"], flush=True)


def qualify_campaign(root):
    """The sole runner/scorer/replay gate: retain costs even on qualification failure."""
    errors, slots, sequences = [], {}, []
    try:
        manifest = load_manifest(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # A failed freeze/source/harness binding cannot earn semantic credit.
        # Keep independently readable attempt ledgers for cost accounting.
        observed = []
        for directory in sorted(root.glob("t[0-9][0-9][0-9]")):
            try:
                spec = custody.read(directory / "input.json")
                slot = custody.collect_slot(directory, spec)
                slot["execution_success"] = slot["clear_eligible"] = False
                slots[directory.name] = slot
                observed.extend(slot["attempts"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return {"qualified": False, "errors": ["campaign binding: " + str(exc)],
                "calls": len(observed), "manifest": None, "slots": slots}
    completed = []
    try:
        for line in (root / "completions.jsonl").read_text().splitlines():
            try:
                completed.append(json.loads(line))
            except ValueError:
                errors.append("invalid completion record")
    except OSError:
        errors.append("completion ledger unavailable")
    if Counter(r["id"] for r in completed) != Counter(r["id"] for r in manifest["order"]):
        errors.append("missing or duplicate completion slots")
    for row in manifest["order"]:
        directory = root / row["id"]
        spec = specification(root, manifest, row)
        collected = custody.collect_slot(directory, spec)
        sequences.extend(a.get("sequence") for a in collected["attempts"])
        try:
            verify_fixture(directory / "repository", spec["case"], spec["fixture"])
            receipt = [r for r in completed if r["id"] == row["id"]]
            if len(receipt) != 1 or receipt[0]["sha256"] != shared.sha((directory / "terminal.json").read_bytes()):
                raise ValueError("terminal receipt changed")
        except (OSError, ValueError) as exc:
            collected["errors"].append(str(exc))
            collected["execution_success"] = collected["clear_eligible"] = False
        errors.extend(row["id"] + ": " + e for e in collected["errors"])
        slots[row["id"]] = collected
    try:
        count = int((root / "calls.txt").read_text())
    except (OSError, ValueError):
        count = len(sequences)
        errors.append("admission counter unavailable")
    if (any(type(s) is not int for s in sequences)
            or Counter(sequences) != Counter(range(1, count + 1)) or count > manifest["call_limit"]):
        errors.append("admission ledger incomplete, duplicate, or over budget")
    if errors:
        for slot in slots.values():
            slot["execution_success"] = slot["clear_eligible"] = False
    receipt_path = root / "scoring-receipt.json"
    if receipt_path.exists():
        try:
            if custody.read(receipt_path) != scoring_binding(root, manifest):
                raise ValueError("scoring receipt changed")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append("scoring custody: " + str(exc))
            for slot in slots.values():
                slot["execution_success"] = slot["clear_eligible"] = False
    return {"qualified": not errors, "errors": errors, "calls": count,
            "manifest": manifest, "slots": slots}


def scoring_binding(root, manifest):
    """Bind later adjudication to immutable execution terminals without rewriting them."""
    return {"schema": 1, "manifest_sha256": shared.sha((root / "manifest.json").read_bytes()),
            "slots": {r["id"]: {
                "terminal_sha256": shared.sha((root / r["id"] / "terminal.json").read_bytes()),
                "score_sha256": shared.sha((root / r["id"] / "score.json").read_bytes()),
            } for r in manifest["order"]}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path, nargs="?")
    p.add_argument("--source", type=Path)
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--worker", type=Path)
    p.add_argument("--digest")
    p.add_argument("--call-limit", type=int, default=CALL_LIMIT)
    args = p.parse_args()
    if args.worker:
        worker(args.worker, args.digest)
    elif args.freeze:
        freeze(args.root.resolve(), args.source.resolve(), args.call_limit)
    elif args.run:
        run(args.root.resolve())
    else:
        q = qualify_campaign(args.root.resolve())
        print(json.dumps({"qualified": q["qualified"], "errors": q["errors"], "calls": q["calls"]}))


if __name__ == "__main__":
    main()
