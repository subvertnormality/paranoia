#!/usr/bin/env python3
"""Frozen, source-paired live review pilot. See docs/claim-audit-benchmark-plan.md.

Linux/WSL pilot runner (uses POSIX file locking).
Run --freeze first, --run for independent trials, qualify rebut setup in the
worksheet, then --run again. No answer key is passed to worker processes.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

MODELS = {"codex": "gpt-6-astra", "claude": "claude-fable-5-1"}
STAKES = ("One trusted operator and OS, static untrusted repository and plan data; "
          "no hostile local race or repository code execution. A tiny local function "
          "with caller-enforced integer domain, no network service or concurrency. "
          "Wrong arithmetic or false clearance matters; recoverable blocking is acceptable. "
          "Exclude authentication, multi-tenancy, OS compromise and corrupted-state recovery.")
CONTRACT = ("total(n) accepts an integer n from 0 through 1000, inclusive. "
            "Return the sum of the integers from 0 through n, inclusive. "
            "The caller enforces the input domain. Additional validation is not required.\n")
GOOD = 'def total(n):\n    """Return the inclusive sum required by CONTRACT.md."""\n    return n * (n + 1) // 2\n'
BAD = 'def total(n):\n    """Return the inclusive sum required by CONTRACT.md."""\n    return n * (n - 1) // 2\n'
QUESTION = ("Review app.py against CONTRACT.md. State whether there is a reachable "
            "contract violation, with a concrete input and file:line evidence. "
            "Read files only; do not run tests or repository code. Test-file absence "
            "alone is not a contract violation.")

def sha(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "surrogatepass")
    return hashlib.sha256(raw).hexdigest()

def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")

def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()

def admit(path, maximum=320):
    """Reserve once, before provider spend. Trusted local benchmark only."""
    import fcntl
    with Path(path).open("r+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        count = int(handle.read())
        if count >= maximum:
            raise RuntimeError("BENCHMARK_CALL_LIMIT: provider invocation refused")
        handle.seek(0)
        handle.write(str(count + 1))
        handle.truncate()
        handle.flush()
        return count + 1

def corpus():
    rows, oracle = [], {}
    modes = ["critique_branch", "critique_plan", "query", "rebut", "arbitrate"]
    for mode_index, mode in enumerate(modes):
        for variant in range(2):
            identifier = sha(f"pilot-v1-{mode_index}-{variant}")[:12]
            provider = "claude" if mode == "critique_plan" else (
                "codex" if (mode_index + variant) % 2 == 0 else "claude")
            code = GOOD if variant == 0 else BAD
            claim = ("pytest-xdist's loadscope scheduler groups test methods by their "
                     + ("test class." if variant == 0 else "containing file."))
            row = {"id": identifier, "mode": mode, "provider": provider,
                   "files": {"CONTRACT.md": CONTRACT, "app.py": code},
                   "plan_text": ("# Scheduler choice\n\n" + claim +
                                 "\n\nUse loadscope for this grouping. Confirm the stated "
                                 "grouping against the official distribution documentation "
                                 "before adopting this choice. No implementation is authorized "
                                 "by this review-only proposal.\n") if mode == "critique_plan" else None,
                   "repair": GOOD if mode == "rebut" and variant == 0 else None}
            if mode == "arbitrate":
                # Two different normative contracts counterbalance the correct option.
                if variant:
                    row["files"]["CONTRACT.md"] = (
                        "total(n) accepts an integer n from 0 through 1000 inclusive. "
                        "Return the sum of integers from 0 up to but excluding n. "
                        "The caller enforces the input domain.\n")
                row["files"]["app.py"] = "# Implementation is to be selected.\n"
            if mode == "critique_plan":
                row["files"].update({
                    "tests/test_app.py": "from app import total\n\nclass TestTotal:\n"
                        "    def test_zero(self):\n        assert total(0) == 0\n"
                        "    def test_two(self):\n        assert total(2) == 3\n",
                    "pytest.ini": "[pytest]\npythonpath = .\naddopts = -n 2 --dist=loadscope\n",
                    "requirements-dev.txt": "pytest\npytest-xdist\n",
                    "app.py": GOOD,
                })
                grouping = "test class" if variant == 0 else "containing file"
                row["files"]["CONTRACT.md"] = CONTRACT + (
                    "The test runner must group test methods by their " + grouping +
                    "; review pytest.ini against that scheduling requirement.\n")
                row["plan_text"] = (
                    "# Scheduling configuration review\n\n"
                    "## Existing repository setup\n"
                    "tests/test_app.py contains TestTotal; pytest.ini already selects "
                    "-n 2 --dist=loadscope and requirements-dev.txt declares pytest-xdist.\n\n"
                    "## External premise\n" + claim + "\n\n"
                    "## Proposed decision\nRetain the existing pytest.ini scheduler setting "
                    "to meet CONTRACT.md's grouping requirement for TestTotal methods. "
                    "This is approval of existing configuration; no runtime-code or dependency "
                    "change is proposed.\n\n"
                    "## Acceptance\nThe reviewer must compare the exact scheduler premise with "
                    "the official pytest-xdist distribution documentation at "
                    "https://pytest-xdist.readthedocs.io/en/stable/distribution.html. "
                    "A mismatch blocks configuration approval. A matching documented grouping "
                    "satisfies this review-only decision; no future implementation artifact "
                    "is required to accept it.\n")
            rows.append(row)
            oracle[identifier] = {
                "mode": mode,
                "expected": ("CONCEDE" if variant == 0 else "HOLD") if mode == "rebut"
                    else ("inclusive" if variant == 0 else "exclusive") if mode == "arbitrate"
                    else ("clear" if variant == 0 else "defect"),
                "governing_contract": row["files"]["CONTRACT.md"] if mode != "critique_plan" else claim,
                "required_evidence": (
                    "Official pytest-xdist distribution documentation: loadscope groups methods "
                    "by class, whereas loadfile groups by file. Require captured, cold-attested "
                    "claim support/refutation and a matching settled structural result."
                    if mode == "critique_plan" else
                    "Cite the current app.py arithmetic and CONTRACT.md. Inclusive sum at n=2 "
                    "is 3; exclusive sum is 1. Rebut must address this exact prior finding. "
                    "Arbitration must converge on the option satisfying its own case contract."),
                "source": "https://pytest-xdist.readthedocs.io/en/stable/distribution.html"
                    if mode == "critique_plan" else None,
            }
    return rows, oracle

def validate_manifest(value):
    if value.get("schema") != 1 or value.get("repetitions") != 2:
        raise ValueError("unsupported manifest")
    cases = value["cases"]
    ids = [c["id"] for c in cases]
    if len(ids) != 10 or len(set(ids)) != 10 or set(ids) != set(value["oracle"]):
        raise ValueError("case/oracle inventory mismatch")
    for case in cases:
        if case["mode"] not in {"critique_branch", "critique_plan", "query", "rebut", "arbitrate"}:
            raise ValueError("unknown mode")
        if case["provider"] not in MODELS or not value["oracle"][case["id"]]["required_evidence"]:
            raise ValueError("missing provider or oracle evidence")
        if value["payload_hashes"][case["id"]] != sha(json.dumps(case, sort_keys=True)):
            raise ValueError("changed case payload")
    if len(value["order"]) != len(cases) * len(value["sources"]) * value["repetitions"]:
        raise ValueError("trial inventory mismatch")
    expected = {(c, v, r) for c in ids for v in value["sources"] for r in range(2)}
    actual = {(r["case"], r["version"], r["repetition"]) for r in value["order"]}
    if actual != expected:
        raise ValueError("duplicate or missing trial")
    for source in value["sources"].values():
        if len(source["revision"]) != 40 or not source["files"]:
            raise ValueError("missing frozen source")

def freeze(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    cases, oracle = corpus()
    sources = {}
    for name, path in (("baseline", args.baseline), ("candidate", args.candidate)):
        path = path.resolve()
        if git(path, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError(f"{name} must be committed before freeze")
        sources[name] = {"path": str(path), "revision": git(path, "rev-parse", "HEAD"),
                         "files": {str(p.relative_to(path)): sha(p.read_bytes())
                                   for p in sorted((path / "src/paranoia_local").glob("*.py"))}}
    versions = {}
    for provider in MODELS:
        versions[provider] = subprocess.run([provider, "--version"], check=True,
                                            capture_output=True, text=True).stdout.strip()
    order = []
    for repetition in range(2):
        for index, case in enumerate(cases):
            pair = ["baseline", "candidate"] if (index + repetition) % 2 == 0 else ["candidate", "baseline"]
            for version in pair:
                order.append({"id": f"t{len(order)+1:03}", "case": case["id"],
                              "version": version, "repetition": repetition})
    manifest = {"schema": 1, "repetitions": 2, "sources": sources, "models": MODELS,
                "cli_versions": versions, "python": sys.version, "stakes": STAKES,
                "cases": cases, "oracle": oracle, "order": order,
                "payload_hashes": {c["id"]: sha(json.dumps(c, sort_keys=True)) for c in cases},
                "harness_sha256": sha(Path(__file__).read_bytes()),
                "counter_path": str(args.counter.resolve() if args.counter else root / "calls.txt")}
    validate_manifest(manifest)
    dump(root / "manifest.json", manifest)
    (root / "manifest.sha256").write_text(sha((root / "manifest.json").read_bytes()))
    if args.counter:
        int(args.counter.read_text())  # existing shared admission count, never reset
    else:
        (root / "calls.txt").write_text("0")
    for trial in order:
        path = root / trial["id"]
        path.mkdir()
        dump(path / "status.json", {"status": "unstarted", **trial})
    print(f"Frozen {len(order)} trials at {root}", flush=True)

def install_observer(engines, directory, counter):
    from paranoia_local import runner as provider_runner
    default_timeout = provider_runner.DEFAULT_TIMEOUT_SEC
    lock = threading.Lock()
    for operation in ("run", "resume"):
        original = getattr(engines.Engine, operation)
        signature = inspect.signature(original)
        def make(original=original, signature=signature, operation=operation):
            @wraps(original)
            def observed(*args, **kwargs):
                values = signature.bind(*args, **kwargs).arguments
                engine = values["self"]
                try:
                    sequence = admit(counter)
                except RuntimeError:
                    with lock:
                        with (directory / "refusals.jsonl").open("a") as handle:
                            handle.write(json.dumps({"operation": operation, "engine": engine.name,
                                                     "role": engine.role, "stage": CURRENT_STAGE[0]}) + "\n")
                    raise
                row = {"sequence": sequence, "operation": operation, "engine": engine.name,
                       "role": engine.role, "model": values["model"], "effort": values["effort"],
                       "prompt_sha256": sha(values["prompt"]),
                       "timeout": values.get("timeout") or default_timeout, "stage": CURRENT_STAGE[0]}
                started = time.perf_counter()
                try:
                    review = original(*args, **kwargs)
                    raw = review.raw or ""
                    (directory / f"provider-{sequence}.txt").write_text(raw, errors="backslashreplace")
                    row.update(error=review.error, returncode=review.returncode,
                               session_ref=review.session_ref, raw_sha256=sha(raw),
                               provider_duration_ms=review.provider_duration_ms)
                    usage = []
                    for line in raw.splitlines():
                        try:
                            packet = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(packet, dict):
                            retained = {k: packet[k] for k in ("usage", "modelUsage", "total_cost_usd")
                                        if k in packet}
                            if retained:
                                usage.append(retained)
                    row["provider_usage"] = usage
                    return review
                except BaseException as exc:
                    row["exception"] = type(exc).__name__ + ": " + str(exc)
                    raise
                finally:
                    row["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
                    with lock:
                        with (directory / "attempts.jsonl").open("a") as handle:
                            handle.write(json.dumps(row) + "\n")
            return observed
        setattr(engines.Engine, operation, make())

CURRENT_STAGE = ["review"]


def validate_source(source):
    """Bind each worker import to the frozen revision and complete package inventory."""
    path = Path(source["path"])
    if git(path, "rev-parse", "HEAD") != source["revision"]:
        raise ValueError("source revision changed")
    inventory = {str(p.relative_to(path)) for p in (path / "src/paranoia_local").glob("*.py")}
    if inventory != set(source["files"]):
        raise ValueError("source inventory changed")
    for name, digest in source["files"].items():
        if sha((path / name).read_bytes()) != digest:
            raise ValueError("source bytes changed")


def validate_harness(bindings):
    for name, digest in bindings.items():
        if sha(Path(name).read_bytes()) != digest:
            raise ValueError("harness changed since freeze")


class ExecutionEvidenceError(ValueError):
    def __init__(self, message, category="unscored"):
        super().__init__(message)
        self.category = category


def require_successful_review(directory, mode, result, *, session=None, provider=None):
    """Require exact native output and successful execution for plain query/rebut."""
    from types import SimpleNamespace
    from paranoia_local.engines import Review
    from paranoia_local.handlers import _footer

    matches = []
    for path in (directory / "logs").glob("*.json"):
        try:
            audit = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise ExecutionEvidenceError("execution audit unavailable") from exc
        if not isinstance(audit, dict) or audit.get("tool") != mode:
            continue
        if (type(audit.get("error")) is not bool or type(audit.get("returncode")) is not int
                or not isinstance(audit.get("text"), str)
                or not isinstance(audit.get("engine"), str)
                or (audit.get("session_ref") is not None
                    and not isinstance(audit["session_ref"], str))):
            continue
        if session is not None and audit.get("session_ref") != session:
            continue
        if provider is not None and audit["engine"] != provider:
            continue
        review = Review(text=audit["text"], session_ref=audit.get("session_ref"), raw="",
                        error=audit["error"], returncode=audit["returncode"])
        if _footer(review, SimpleNamespace(name=audit["engine"])) == result:
            matches.append(audit)
    if len(matches) != 1:
        raise ExecutionEvidenceError("missing or ambiguous exact execution audit")
    audit = matches[0]
    if audit["error"] or audit["returncode"] != 0:
        raise ExecutionEvidenceError("failed execution cannot receive semantic credit",
                                     "operational_failure")
    return audit


def worker(spec_path):
    spec = json.loads(spec_path.read_text())
    directory = spec_path.parent
    validate_source(spec["source"])
    source = Path(spec["source"]["path"])
    sys.path.insert(0, str(source / "src"))
    from paranoia_local import server, engines, class_closure as cc
    os.environ[cc.STATE_ROOT_ENV] = str(directory / "state")
    install_observer(engines, directory, Path(spec["counter"]))
    case = spec["input"]
    repo = directory / "repository"
    if not repo.exists():
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.name", "review fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        for name, text in case["files"].items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        if case["mode"] in {"critique_branch", "rebut"}:
            (repo / "app.py").write_text(GOOD if case["mode"] == "critique_branch" else BAD)
        git(repo, "add", ".")
        git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "Initial contract")
        if case["mode"] == "critique_branch":
            git(repo, "checkout", "-qb", "change")
            (repo / "app.py").write_text(case["files"]["app.py"] + "\n")
            git(repo, "add", ".")
            git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "Implementation")
    common = {"repo_path": str(repo), "engine": case["provider"],
              "model": spec["models"][case["provider"]], "effort": "high", "web_search": False}
    outputs = []
    def call(mode, arguments, stage="review"):
        CURRENT_STAGE[0] = stage
        started = time.perf_counter()
        result = server.dispatch(mode, arguments, default_engine_name=case["provider"],
                                 log_dir=directory / "logs")
        elapsed = round((time.perf_counter() - started) * 1000)
        record = {"mode": mode, "stage": stage, "elapsed_ms": elapsed, "result": result}
        outputs.append(record)
        dump(directory / f"{stage}-{len(outputs)}.json", record)
        return result
    mode = case["mode"]
    if mode == "rebut":
        setup_path = directory / "setup.json"
        if not setup_path.exists():
            result = call("query", {**common, "question": QUESTION}, "setup")
            import re
            sessions = re.findall(r"session_ref=`([^`]+)`", result)
            dump(setup_path, {"result": result, "session": sessions[-1] if sessions else None,
                              "provider": case["provider"], "snapshot": git(repo, "rev-parse", "HEAD"),
                              "elapsed_ms": outputs[-1]["elapsed_ms"]})
            try:
                require_successful_review(directory, "query", result,
                                          session=sessions[-1] if sessions else None,
                                          provider=case["provider"])
            except ExecutionEvidenceError as exc:
                dump(directory / "status.json", {"status": "setup_unusable", "error": str(exc)})
                return
            dump(directory / "status.json", {"status": "setup_pending"})
            return
        setup = json.loads(setup_path.read_text())
        qualification = json.loads((directory / "qualification.json").read_text())
        if not qualification.get("accepted") or not setup["session"]:
            dump(directory / "status.json", {"status": "setup_unusable", "scored": False})
            return
        if qualification["setup_sha256"] != sha(setup_path.read_bytes()):
            raise ValueError("qualification does not bind setup")
        try:
            require_successful_review(directory, "query", setup["result"],
                                      session=setup["session"], provider=setup["provider"])
        except ExecutionEvidenceError as exc:
            dump(directory / "status.json", {"status": "setup_unusable", "error": str(exc)})
            return
        if (git(repo, "rev-parse", "HEAD") != setup["snapshot"]
                or git(repo, "status", "--porcelain")
                or setup["provider"] != case["provider"]):
            raise ValueError("setup binding changed")
        if case["repair"]:
            (repo / "app.py").write_text(case["repair"])
            git(repo, "add", ".")
            git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "Update implementation")
        call("rebut", {**common, "session_ref": setup["session"],
                      "rebuttal": "Recheck your inclusive-sum contract finding against the current "
                      "app.py. The implementation now satisfies CONTRACT.md; concede if the "
                      "current code proves that claim, otherwise hold with exact code evidence."})
    elif mode == "query":
        call(mode, {**common, "question": QUESTION})
    elif mode == "arbitrate":
        call(mode, {"repo_path": str(repo), "decision": "Select an implementation for total(n).",
                    "options": [{"id": "inclusive", "statement": "Return n * (n + 1) // 2."},
                                {"id": "exclusive", "statement": "Return n * (n - 1) // 2."}],
                    "context": "CONTRACT.md specifies the required input domain and arithmetic result.",
                    "files": [{"path": "CONTRACT.md"}], "stakes": STAKES, "research": False,
                    "models": spec["models"], "cleaner_model": spec["models"]["claude"],
                    "effort": "high", "order_seed": case["id"]})
    else:
        base = {**common, "stakes": STAKES, "lineage": case["id"]}
        if mode == "critique_plan":
            base.update(plan_text=case["plan_text"], web_search=True)
        else:
            base.update(base_ref="main")
        for round_no in (1, 2):
            result = call(mode, {**base, "round": round_no})
            # Advance only an accepted census awaiting cold final, never failed work.
            lineages = list((directory / "state").rglob("*.json"))
            phases = []
            claim_blocked = False
            for path in lineages:
                try:
                    state = json.loads(path.read_text())
                    phases.append(state.get("review_state", {}).get("phase"))
                    claims = state.get("claim_state", {})
                    claim_blocked = claim_blocked or bool(claims.get("debt")) or any(
                        c.get("verdict") != "supported" for c in claims.get("claims", {}).values())
                except (ValueError, AttributeError):
                    pass
            if round_no != 1 or "final" not in phases or claim_blocked or "validation-debt" in result.lower():
                break
    terminal = "incomplete_call_limit" if any(
        "BENCHMARK_CALL_LIMIT" in r["result"] for r in outputs) else "completed"
    dump(directory / "status.json", {"status": terminal, "outputs": outputs,
                                    "snapshot": git(repo, "rev-parse", "HEAD")})

def run(args):
    root = args.output.resolve()
    raw = (root / "manifest.json").read_bytes()
    if sha(raw) != (root / "manifest.sha256").read_text():
        raise ValueError("manifest changed since freeze")
    manifest = json.loads(raw)
    validate_manifest(manifest)
    harness = {str(Path(__file__).resolve()): manifest["harness_sha256"]}
    validate_harness(harness)
    for provider, version in manifest["cli_versions"].items():
        actual = subprocess.run([provider, "--version"], check=True, capture_output=True,
                                text=True).stdout.strip()
        if actual != version:
            raise ValueError("provider CLI changed")
    for source in manifest["sources"].values():
        validate_source(source)
    def execute(trial):
        directory = root / trial["id"]
        status = json.loads((directory / "status.json").read_text())["status"]
        if status != "unstarted" and not (
            status == "setup_pending" and (directory / "qualification.json").exists()
        ):
            return
        if int(Path(manifest.get("counter_path", str(root / "calls.txt"))).read_text()) >= 320:
            dump(directory / "status.json", {"status": "incomplete_call_limit"})
            return
        try:
            validate_harness(harness)
            validate_source(manifest["sources"][trial["version"]])
        except (OSError, ValueError) as exc:
            dump(directory / "status.json", {"status": "incomplete_binding_changed", "error": str(exc)})
            return
        case = next(c for c in manifest["cases"] if c["id"] == trial["case"])
        dump(directory / "input.json", {"input": case, "models": manifest["models"],
                                       "source": manifest["sources"][trial["version"]],
                                       "counter": manifest.get("counter_path", str(root / "calls.txt"))})
        dump(directory / "status.json", {"status": "running"})
        with (directory / "worker.txt").open("a") as handle:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                     "--worker", str(directory / "input.json")],
                                    stdout=handle, stderr=subprocess.STDOUT)
        if result.returncode:
            dump(directory / "status.json", {"status": "incomplete_worker_failure",
                                            "returncode": result.returncode})
        print(trial["id"], json.loads((directory / "status.json").read_text())["status"], flush=True)
    # Pair order is fixed; worker scheduling is recorded by actual invocation admissions.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(execute, manifest["order"]))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--counter", type=Path, help="Reuse an existing admission counter without resetting it")
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("the pilot runner requires Linux/WSL POSIX file locking")
    os.environ.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    if args.worker:
        worker(args.worker)
    elif args.freeze:
        freeze(args)
    elif args.run:
        run(args)
    else:
        parser.error("choose --freeze or --run")
if __name__ == "__main__":
    main()
