#!/usr/bin/env python3
"""Frozen local materialization benchmark; snapshot-batching-requalification-plan.md owns gates."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

import runpy
BOOTSTRAP_PATH = Path(__file__).with_name("benchmark_bootstrap.py")
runpy.run_path(str(BOOTSTRAP_PATH))

import benchmark_review_modes as shared

BASELINE = "684898c5a8f35f57917ea77662a9aad9b8b05f19"
REPETITIONS = 5


def fingerprint(tree):
    rows = []
    for path in sorted(tree.root.rglob("*")):
        if path.is_file():
            rows.append([os.fsencode(path.relative_to(tree.root)).hex(),
                         shared.sha(path.read_bytes()), path.stat().st_mode & 0o777,
                         path.is_symlink()])
    return shared.sha(json.dumps(rows, separators=(",", ":")))


def source_record(path):
    return shared.source_record(path)


def order(fixtures):
    return [{"fixture": fixture, "version": version, "repetition": repeat}
            for fixture in fixtures for repeat in range(REPETITIONS)
            for version in (["baseline", "candidate"] if repeat % 2 == 0
                            else ["candidate", "baseline"])]


def freeze(root, baseline, candidate):
    root.mkdir(parents=True, exist_ok=False)
    sources = {"baseline": source_record(baseline), "candidate": source_record(candidate)}
    if sources["baseline"]["revision"] != BASELINE:
        raise ValueError("wrong baseline")
    fixtures = {"repository": {"path": str(Path(baseline).resolve()), "snapshot": BASELINE}}
    for count in (100, 1000, 3000):
        repo = root / f"files-{count}"
        repo.mkdir()
        shared.git(repo, "init", "-q", "-b", "main")
        shared.git(repo, "config", "user.name", "snapshot benchmark")
        shared.git(repo, "config", "user.email", "fixture@example.test")
        for number in range(count):
            (repo / f"source-{number:05}.txt").write_text(
                f"Fixture file {number}; bounded distinct source bytes.\n" * 4)
        shared.git(repo, "add", ".")
        shared.git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "Frozen fixture")
        fixtures[str(count)] = {"path": str(repo), "snapshot": shared.git(repo, "rev-parse", "HEAD")}
    harness = {str(Path(p).resolve()): shared.sha(Path(p).read_bytes())
               for p in (__file__, shared.__file__, BOOTSTRAP_PATH)}
    manifest = {"schema": 1, "sources": sources, "fixtures": fixtures,
                "harness": harness, "order": order(fixtures), "repetitions": REPETITIONS}
    shared.dump(root / "manifest.json", manifest)
    (root / "manifest.sha256").write_text(shared.sha((root / "manifest.json").read_bytes()))
    return manifest


def load_manifest(root, digest=None):
    raw = (root / "manifest.json").read_bytes()
    expected = digest or (root / "manifest.sha256").read_text().strip()
    if shared.sha(raw) != expected:
        raise ValueError("manifest changed")
    value = json.loads(raw)
    if set(value) != {"schema", "sources", "fixtures", "harness", "order", "repetitions"}:
        raise ValueError("unexpected manifest fields")
    if value["schema"] != 1 or value["repetitions"] != REPETITIONS:
        raise ValueError("unsupported campaign")
    if set(value["sources"]) != {"baseline", "candidate"}:
        raise ValueError("source inventory changed")
    if list(value["fixtures"]) != ["repository", "100", "1000", "3000"]:
        raise ValueError("fixture inventory changed")
    if value["sources"]["baseline"]["revision"] != BASELINE:
        raise ValueError("baseline changed")
    if value["order"] != order(value["fixtures"]):
        raise ValueError("trial order changed")
    return value, expected


def preflight(manifest, trial):
    shared.validate_harness(manifest["harness"])
    shared.validate_source(manifest["sources"][trial["version"]])
    fixture = manifest["fixtures"][trial["fixture"]]
    if shared.git(Path(fixture["path"]), "rev-parse", "HEAD") != fixture["snapshot"]:
        raise ValueError("fixture snapshot changed")


def worker(root, index, digest):
    manifest, _ = load_manifest(root, digest)
    trial = manifest["order"][index]
    preflight(manifest, trial)
    source = manifest["sources"][trial["version"]]
    sys.path.insert(0, str(Path(source["path"]) / "src"))
    from paranoia_local import inert_tree, inert_git
    if Path(inert_tree.__file__).resolve() != Path(source["path"]) / "src/paranoia_local/inert_tree.py":
        raise ValueError("unexpected imported source")
    calls = Counter()
    original = inert_git.invoke

    def observe(repo, args, **kwargs):
        calls[args[0]] += 1
        return original(repo, args, **kwargs)

    inert_git.invoke = observe
    fixture = manifest["fixtures"][trial["fixture"]]
    result = {"trial": trial, "source_revision": source["revision"],
              "snapshot": fixture["snapshot"], "status": "failed"}
    manager = inert_tree.materialized(Path(fixture["path"]), fixture["snapshot"])
    start = time.perf_counter()
    try:
        tree = manager.__enter__()
        setup = time.perf_counter() - start
        try:
            evidence = fingerprint(tree)
        finally:
            cleanup_start = time.perf_counter()
            manager.__exit__(None, None, None)
            cleanup = time.perf_counter() - cleanup_start
        if tree.root.exists():
            raise RuntimeError("workspace cleanup incomplete")
        preflight(manifest, trial)
        result.update(status="complete", setup_seconds=setup, cleanup_seconds=cleanup,
                      seconds=setup + cleanup, fingerprint=evidence, calls=dict(calls))
    except Exception as exc:
        result.update(error=f"{type(exc).__name__}: {exc}", calls=dict(calls),
                      failed_elapsed_seconds=time.perf_counter() - start)
    shared.dump(root / f"trial-{index:03}.json", result)
    return result


def run(root):
    manifest, digest = load_manifest(root)
    if any(root.glob("trial-*.json")):
        raise ValueError("campaign already has observations; freeze a new campaign")
    blocked = None
    for index, trial in enumerate(manifest["order"]):
        try:
            if blocked:
                raise ValueError(blocked)
            load_manifest(root, digest)
            preflight(manifest, trial)
        except Exception as exc:
            blocked = str(exc)
            shared.dump(root / f"trial-{index:03}.json",
                        {"trial": trial, "status": "incomplete", "error": blocked})
            continue
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(root),
             "--index", str(index), "--digest", digest],
            capture_output=True, text=True,
        )
        if completed.returncode:
            shared.dump(root / f"trial-{index:03}.json", {
                "trial": trial, "status": "failed", "returncode": completed.returncode,
                "error": completed.stderr[-4000:],
            })
        print(f"completed trial {index + 1}/{len(manifest['order'])}", flush=True)


def report(root):
    manifest, digest = load_manifest(root)
    rows = [json.loads((root / f"trial-{i:03}.json").read_text())
            for i in range(len(manifest["order"]))]
    for trial, row in zip(manifest["order"], rows, strict=True):
        if row.get("trial") != trial:
            raise ValueError("trial output binding changed")
        if row.get("status") == "complete":
            source = manifest["sources"][trial["version"]]
            fixture = manifest["fixtures"][trial["fixture"]]
            if row.get("source_revision") != source["revision"] or row.get("snapshot") != fixture["snapshot"]:
                raise ValueError("trial source/snapshot binding changed")
            preflight(manifest, trial)
    complete = all(r.get("status") == "complete" for r in rows)
    summaries = {}
    for fixture in manifest["fixtures"]:
        selected = [r for r in rows if r["trial"]["fixture"] == fixture]
        groups = {version: [r for r in selected if r["trial"]["version"] == version]
                  for version in manifest["sources"]}
        if not all(r.get("status") == "complete" for r in selected):
            summaries[fixture] = {"qualified": False}
            continue
        equivalent = len({r["fingerprint"] for r in selected}) == 1
        medians = {version: statistics.median(r["seconds"] for r in group)
                   for version, group in groups.items()}
        ratio = medians["candidate"] / medians["baseline"]
        reduced_calls = all(
            c["calls"].get("cat-file", 0) < b["calls"].get("cat-file", 0)
            for c, b in zip(groups["candidate"], groups["baseline"], strict=True))
        numeric_gate = ratio <= (0.5 if fixture in {"1000", "3000"} else
                                 1.1 if fixture == "repository" else float("inf"))
        summaries[fixture] = {"qualified": equivalent and reduced_calls and numeric_gate,
                             "equivalent": equivalent, "median_seconds": medians,
                             "ratio": ratio, "reduced_calls": reduced_calls}
    result = {"manifest_sha256": digest, "source": manifest["sources"],
              "rows": rows, "fixtures": summaries,
              "local_gate_passed": complete and all(x["qualified"] for x in summaries.values()),
              "limits": "Local setup/cleanup only; excludes fingerprinting and provider execution. B4 additionally requires unit/integration tests, live arbitration and CODE convergence."}
    shared.dump(root / "report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", type=Path)
    group.add_argument("--run", type=Path)
    group.add_argument("--report", type=Path)
    group.add_argument("--worker", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--index", type=int)
    parser.add_argument("--digest")
    args = parser.parse_args()
    if args.freeze:
        freeze(args.freeze.resolve(), args.baseline, args.candidate)
    elif args.run:
        run(args.run.resolve())
    elif args.report:
        print(json.dumps(report(args.report.resolve())["fixtures"], indent=2))
    else:
        worker(args.worker.resolve(), args.index, args.digest)


if __name__ == "__main__":
    main()
