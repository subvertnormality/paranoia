"""Twelve frozen branch trials for empty-census acceptance; reuses the five-mode worker."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import benchmark_review_modes as pilot

MAX_CALLS = 96


def source(path):
    path = path.resolve()
    if pilot.git(path, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("freeze requires committed sources")
    return {
        "path": str(path), "revision": pilot.git(path, "rev-parse", "HEAD"),
        "files": {str(p.relative_to(path)): pilot.sha(p.read_bytes())
                  for p in sorted((path / "src/paranoia_local").glob("*.py"))},
    }


def freeze(root, baseline, candidate, counter=None):
    sources = {"baseline": source(baseline), "candidate": source(candidate)}
    counter = counter.resolve() if counter else root / "calls.txt"
    prior_admissions = int(counter.read_text()) if counter.exists() else 0
    cases = []
    for provider in pilot.MODELS:
        for defect in (False, True):
            case = {
                "id": pilot.sha(f"empty-census-v2-{provider}-{defect}")[:12],
                "provider": provider, "mode": "critique_branch",
                "files": {
                    "CONTRACT.md": pilot.CONTRACT,
                    # The reused worker appends one newline to branch app.py.
                    "app.py": (pilot.BAD if defect else pilot.GOOD.replace(
                        "n * (n + 1)", "(n * n + n)",
                    )).rstrip("\n"),
                    "test_app.py": (
                        "from app import total\n\n"
                        "def test_total():\n"
                        "    for n in range(1001):\n"
                        "        assert total(n) == sum(range(n + 1)), n\n\n"
                        "if __name__ == \"__main__\":\n"
                        "    test_total()\n"
                    ),
                    "README.md": "Run the contract regression with python test_app.py.\n",
                },
                "plan_text": None, "repair": None,
            }
            cases.append((case, defect))
    order = []
    for index, (case, defect) in enumerate(cases):
        for repetition in range(1 if defect else 2):
            versions = ("baseline", "candidate") if (index + repetition) % 2 == 0 else ("candidate", "baseline")
            for version in versions:
                order.append({
                    "id": f"t{len(order)+1:03}", "case": case["id"],
                    "version": version, "repetition": repetition,
                })
    manifest = {
        "schema": "empty-census-acceptance-v2", "sources": sources, "models": pilot.MODELS,
        "stakes": pilot.STAKES, "cases": [row for row, _ in cases],
        "oracle": {row["id"]: ("defect" if defect else "clear") for row, defect in cases},
        "order": order, "maximum_calls": MAX_CALLS,
        "counter_path": str(counter), "admissions_at_freeze": prior_admissions,
        "harness": {str(p): pilot.sha(p.read_bytes()) for p in (
            Path(__file__).resolve(), Path(pilot.__file__).resolve(),
        )},
        "cli_versions": {
            name: subprocess.check_output([name, "--version"], text=True).strip()
            for name in pilot.MODELS
        },
    }
    root.mkdir(parents=True, exist_ok=False)
    pilot.dump(root / "manifest.json", manifest)
    (root / "manifest.sha256").write_text(pilot.sha((root / "manifest.json").read_bytes()))
    if not counter.exists():
        counter.write_text("0")
    for trial in order:
        directory = root / trial["id"]
        directory.mkdir()
        pilot.dump(directory / "status.json", {"status": "unstarted"})
        case = next(row for row in manifest["cases"] if row["id"] == trial["case"])
        pilot.dump(directory / "input.json", {
            "input": case, "models": manifest["models"],
            "source": sources[trial["version"]], "counter": str(counter),
        })
    print(f"Frozen {len(order)} trials; maximum {MAX_CALLS} provider admissions", flush=True)


def load(root):
    raw = (root / "manifest.json").read_bytes()
    if pilot.sha(raw) != (root / "manifest.sha256").read_text():
        raise ValueError("manifest changed")
    return json.loads(raw)


def run(root):
    manifest = load(root)
    for name, digest in manifest["harness"].items():
        if pilot.sha(Path(name).read_bytes()) != digest:
            raise ValueError("harness changed")
    for row in manifest["sources"].values():
        if source(Path(row["path"])) != row:
            raise ValueError("source changed")
    for name, version in manifest["cli_versions"].items():
        if subprocess.check_output([name, "--version"], text=True).strip() != version:
            raise ValueError("CLI changed")
    # Sequential pairs avoid cross-trial contention; each census still has three lanes.
    for trial in manifest["order"]:
        directory = root / trial["id"]
        if json.loads((directory / "status.json").read_text())["status"] != "unstarted":
            continue
        if int(Path(manifest.get("counter_path", str(root / "calls.txt"))).read_text()) >= MAX_CALLS:
            pilot.dump(directory / "status.json", {"status": "incomplete_call_limit"})
            continue
        pilot.dump(directory / "status.json", {"status": "running"})
        with (directory / "worker.txt").open("w") as handle:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker", str(directory / "input.json")],
                stdout=handle, stderr=subprocess.STDOUT,
            )
        if result.returncode:
            pilot.dump(directory / "status.json", {
                "status": "incomplete_worker_failure", "returncode": result.returncode,
            })
        print(trial["id"], json.loads((directory / "status.json").read_text())["status"], flush=True)


def report(root):
    from paranoia_local.class_closure import BLOCKING_SEVERITIES

    manifest = load(root)
    rows = []
    for trial in manifest["order"]:
        directory = root / trial["id"]
        status = json.loads((directory / "status.json").read_text())
        audits = sorted((directory / "logs").glob("*critique_branch*.json"))
        outputs = status.get("outputs", [])
        audit = json.loads(audits[-1].read_text()) if audits else {}
        # The state filename is owned by class_closure, not the benchmark.
        candidates = list((directory / "state").rglob("*.json"))
        state = next((value for p in candidates
                      if isinstance((value := json.loads(p.read_text())), dict)
                      and "review_state" in value), {})
        attempts = audit.get("attempt_ledger", [])
        expected = manifest["oracle"][trial["case"]]
        qualified = status["status"] == "completed" and bool(outputs) and not audit.get("error", True)
        roles = [row["role"] for row in attempts]
        qualified = qualified and all(
            roles.count(f"census-{lane}") == 1 for lane in ("behaviour", "execution", "integrity")
        ) and all(row["outcome"] == "completed" or row["outcome"] == "validation-invalid" for row in attempts)
        derived = audit.get("review_origin") == "server-empty-census"
        if expected == "clear":
            qualified = qualified and state.get("review_state", {}).get("phase") == "clear"
            qualified = qualified and "CONVERGENCE: NOT-BLOCKED" in outputs[-1]["result"]
            qualified = qualified and derived == (trial["version"] == "candidate")
            qualified = qualified and (not any(role.startswith("consolidation") for role in roles) if derived
                                       else "consolidation" in roles)
        else:
            qualification_path = directory / "qualification.json"
            qualification = json.loads(qualification_path.read_text()) if qualification_path.exists() else {}
            debts = state.get("review_state", {}).get("debt", [])
            chosen = next((d for d in debts if d.get("finding_id") == qualification.get("finding_id")), {})
            qualified = qualified and not derived and "consolidation" in roles
            qualified = qualified and qualification.get("accepted") is True
            qualified = qualified and qualification.get("audit_sha256") == (
                pilot.sha(audits[-1].read_bytes()) if audits else None)
            qualified = qualified and chosen.get("status") == "open" and chosen.get("severity") in BLOCKING_SEVERITIES
            qualified = qualified and any(a.startswith("repository/app.py:") for a in chosen.get("evidence", []))
        rows.append({
            **trial, "expected": expected, "status": status["status"], "qualified": bool(qualified),
            "wall_ms": sum(row["elapsed_ms"] for row in outputs), "calls": len(attempts),
            "server_consolidation": derived,
            "audit_sha256": pilot.sha(audits[-1].read_bytes()) if audits else None,
        })
    result = {
        "manifest_sha256": pilot.sha((root / "manifest.json").read_bytes()),
        "admissions": int(Path(manifest.get("counter_path", str(root / "calls.txt"))).read_text()), "trials": rows,
        "qualified": len(rows) == 12 and all(row["qualified"] for row in rows),
    }
    pilot.dump(root / "report.json", result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--counter", type=Path, help="Reuse the campaign counter without resetting admissions")
    args = parser.parse_args()
    if os.name != "posix":
        raise SystemExit("This acceptance runner requires Linux/WSL.")
    if args.worker:
        original = pilot.admit
        pilot.admit = lambda path, maximum=MAX_CALLS: original(path, MAX_CALLS)
        pilot.worker(args.worker.resolve())
    elif args.freeze:
        freeze(args.output.resolve(), args.baseline, args.candidate, args.counter)
    elif args.run:
        run(args.output.resolve())
    elif args.report:
        report(args.output.resolve())


if __name__ == "__main__":
    main()
