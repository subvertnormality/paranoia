#!/usr/bin/env python3
"""Frozen eight-dispatch comparison for decision-evidence admission."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
import inspect
import os
import json
from pathlib import Path
import subprocess
import sys
from threading import Lock

import benchmark_review_modes as shared

CALL_LIMIT = 128
BASELINE = '33394cb4b465e414a315d152b079599880771de1'


def padding_files(count):
    """Outcome-independent distinct inert files for the frozen large workload."""
    if type(count) is not int or count not in (0, 3000):
        raise ValueError("padding must be zero or exactly 3000 files")
    return {f"_benchmark_padding/{n:05}.txt":
            f"Distinct inert workload file {n:05}.\n" for n in range(count)}


def freeze(root, baseline, candidate, prior_report=None, *,
           expected_baseline=None, large_padding=0):
    expected_baseline = BASELINE if expected_baseline is None else expected_baseline
    padding = padding_files(large_padding)
    root.mkdir(parents=True, exist_ok=False)
    prior = None
    starting_calls = 0
    if prior_report is not None:
        prior_report = Path(prior_report).resolve()
        raw = prior_report.read_bytes()
        previous = json.loads(raw)
        starting_calls = previous.get("cumulative_calls", previous["calls"])
        if (type(starting_calls) is not int or not 0 <= starting_calls <= CALL_LIMIT
                or previous.get("ledger_complete") is not True):
            raise ValueError("prior campaign has no complete bounded call ledger")
        prior = {"path": str(prior_report), "sha256": shared.sha(raw), "calls": starting_calls}
    sources = {"baseline": source_record(baseline), "candidate": source_record(candidate)}
    if sources["baseline"]["revision"] != expected_baseline:
        raise ValueError("wrong baseline")
    cases, oracle = shared.corpus()
    cases = [case for case in cases if case["mode"] == "arbitrate"]
    versions = {name: subprocess.check_output([name, "--version"], text=True).strip()
                for name in ["codex", "claude"]}
    trials = []
    for n, case in enumerate(cases):
        for repetition in range(2):
            fixture = root / f"fixture-{n}-{repetition}"
            fixture.mkdir()
            shared.git(fixture, "init", "-q", "-b", "main")
            shared.git(fixture, "config", "user.name", "snapshot acceptance")
            shared.git(fixture, "config", "user.email", "fixture@example.test")
            files = {**case["files"], **(padding if repetition else {})}
            for name, body in files.items():
                target = fixture / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body)
            shared.git(fixture, "add", ".")
            shared.git(fixture, "-c", "commit.gpgsign=false", "commit", "-qm", "Frozen contract")
            snapshot = shared.git(fixture, "rev-parse", "HEAD")
            versions_in_pair = (["baseline", "candidate"] if (n + repetition) % 2 == 0
                                else ["candidate", "baseline"])
            for version in versions_in_pair:
                directory = root / f"trial-{len(trials)}"
                directory.mkdir()
                shared.git(root, "clone", "-q", "--no-hardlinks", str(fixture), str(directory / "repository"))
                trials.append({"version": version, "case": case, "snapshot": snapshot,
                               "repetition": repetition,
                               "padding_files": large_padding if repetition else 0})
    harness = {str(Path(p).resolve()): shared.sha(Path(p).read_bytes())
               for p in [__file__, shared.__file__]}
    manifest = {"schema": 3, "sources": sources, "models": shared.MODELS,
                "expected_baseline": expected_baseline, "large_padding": large_padding,
                "starting_calls": starting_calls, "prior_campaign": prior,
                "versions": versions, "trials": trials, "harness": harness,
                "oracle": {case["id"]: oracle[case["id"]]["expected"] for case in cases},
                "call_limit": CALL_LIMIT}
    shared.dump(root / "manifest.json", manifest)
    (root / "manifest.sha256").write_text(shared.sha((root / "manifest.json").read_bytes()))
    (root / "counter").write_text(str(starting_calls))


def load(root, digest=None):
    raw = (root / "manifest.json").read_bytes()
    expected = digest or (root / "manifest.sha256").read_text().strip()
    if shared.sha(raw) != expected:
        raise ValueError("manifest changed")
    manifest = json.loads(raw)
    if manifest["schema"] != 3 or manifest["call_limit"] != CALL_LIMIT or len(manifest["trials"]) != 8:
        raise ValueError("invalid live campaign")
    expected_baseline = manifest.get("expected_baseline")
    if (not isinstance(expected_baseline, str) or len(expected_baseline) not in (40, 64)
            or any(c not in "0123456789abcdef" for c in expected_baseline)
            or manifest["sources"]["baseline"]["revision"] != expected_baseline):
        raise ValueError("wrong frozen baseline")
    padding_files(manifest.get("large_padding"))
    cases, oracle = shared.corpus()
    cases = [case for case in cases if case["mode"] == "arbitrate"]
    expected_trials = []
    for n, case in enumerate(cases):
        for repetition in range(2):
            pair = (["baseline", "candidate"] if (n + repetition) % 2 == 0
                    else ["candidate", "baseline"])
            for version in pair:
                expected_trials.append((case, repetition, version,
                                        manifest["large_padding"] if repetition else 0))
    for row, (case, repetition, version, padding) in zip(manifest["trials"], expected_trials):
        if (row["case"] != case or type(row["repetition"]) is not int
                or row["repetition"] != repetition or row["version"] != version
                or type(row.get("padding_files")) is not int or row["padding_files"] != padding):
            raise ValueError("frozen workload or schedule mismatch")
    for i in range(0, len(manifest["trials"]), 2):
        if manifest["trials"][i]["snapshot"] != manifest["trials"][i + 1]["snapshot"]:
            raise ValueError("paired workload snapshots differ")
    if manifest["oracle"] != {c["id"]: oracle[c["id"]]["expected"] for c in cases}:
        raise ValueError("frozen oracle mismatch")
    start = manifest.get("starting_calls")
    prior = manifest.get("prior_campaign")
    if type(start) is not int or not 0 <= start <= CALL_LIMIT:
        raise ValueError("invalid prior call budget")
    if (prior is None and start != 0) or (prior is not None and prior.get("calls") != start):
        raise ValueError("prior campaign budget mismatch")
    return manifest, expected


def preflight(root, manifest, index):
    row = manifest["trials"][index]
    shared.validate_harness(manifest["harness"])
    if manifest.get("prior_campaign") is not None:
        prior = manifest["prior_campaign"]
        if shared.sha(Path(prior["path"]).read_bytes()) != prior["sha256"]:
            raise ValueError("prior campaign record changed")
    shared.validate_source(manifest["sources"][row["version"]])
    repo = root / f"trial-{index}" / "repository"
    if shared.git(repo, "rev-parse", "HEAD") != row["snapshot"] or shared.git(repo, "status", "--porcelain"):
        raise ValueError("fixture changed")
    for name, version in manifest["versions"].items():
        if subprocess.check_output([name, "--version"], text=True).strip() != version:
            raise ValueError("provider version changed")
    return row


def source_record(path):
    return shared.source_record(path)


def rows_digest(rows):
    return shared.sha(json.dumps(rows, sort_keys=True, separators=(",", ":")))


def observed_rows(root):
    rows = {}
    for p in sorted(root.rglob("*")):
        name = os.fsencode(p.relative_to(root)).hex()
        if p.is_symlink():
            rows[name] = ["symlink", os.readlink(p)]
        elif p.is_dir():
            rows[name] = ["directory"]
        elif p.is_file():
            rows[name] = ["file", shared.sha(p.read_bytes()), p.stat().st_mode & 0o777]
        else:
            rows[name] = ["unsupported"]
    return rows


def expected_rows(repo, snapshot, inert_git):
    """Independent test-side rendering from Git objects, never the candidate materializer."""
    files, entries = {}, []
    listing = inert_git.run(repo, ["ls-tree", "-rz", "--full-tree", snapshot])
    for row in listing.split(b"\0"):
        if not row:
            continue
        meta, path = row.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        if kind == "blob":
            raw = inert_git.run(repo, ["cat-file", "blob", oid])
            body = b"PARANOIA INERT SYMLINK TARGET\n" + raw if mode == "120000" else raw
            record_kind = "symlink" if mode == "120000" else "executable" if mode == "100755" else "file"
            size = len(raw)
        elif kind == "commit" and mode == "160000":
            body = f"PARANOIA INERT GITLINK OID\n{oid}\n".encode()
            record_kind, size = "gitlink", 0
        else:
            raise ValueError("unsupported expected entry")
        files[b"repository/" + path] = body
        entries.append({"path": path.decode("utf-8", errors="backslashreplace"),
                        "mode": mode, "kind": record_kind, "oid": oid, "bytes": size})
    files[b"MANIFEST.json"] = (json.dumps({"snapshot": snapshot, "entries": entries},
                                         indent=2, sort_keys=True) + "\n").encode()
    files[b"HISTORY.txt"] = inert_git.run(repo, [
        "log", "--no-patch", "--max-count=100", "--format=%H%x09%aI%x09%an%x09%s", snapshot])
    rows = {b"repository".hex(): ["directory"]}
    for path, body in files.items():
        rows[path.hex()] = ["file", shared.sha(body), 0o444]
        parts = path.split(b"/")
        for end in range(1, len(parts)):
            rows[b"/".join(parts[:end]).hex()] = ["directory"]
    return rows


def verify_workspace(row, attempts):
    """Absence and mismatch are failed observations, never evidence of equivalence."""
    required = {"before", "after", "expected", "provider", "root", "snapshot", "cleaned_up"}
    if not required <= row.keys() or not row["cleaned_up"]:
        return False
    related = [a for a in attempts if a["root"] == row["root"]]
    return (bool(related) and row["before"] == row["after"] == row["expected"]
            and all(a.get("before") == row["expected"] and a["provider"] == row["provider"]
                    and a["snapshot"] == row["snapshot"] for a in related))



def verify_workspaces(rows, attempts, snapshot):
    """Each actual attempt root has exactly one complete, matching workspace row."""
    if not rows or not attempts:
        return False
    roots = [row.get("root") for row in rows]
    return (None not in roots and len(set(roots)) == len(roots)
            and set(roots) == {a.get("root") for a in attempts}
            and {r.get("provider") for r in rows} == {"codex", "claude"}
            and all(r.get("snapshot") == snapshot and verify_workspace(r, attempts) for r in rows))


@dataclass(frozen=True)
class TrialRecords:
    attempts: tuple[dict, ...]
    output: dict | None
    workspaces: dict | None
    audit_path: Path | None
    audit: dict | None
    audit_sha256: str | None
    markers: dict
    errors: tuple[str, ...]


def collect_trial(directory):
    """Collect independent stored observations before any qualification can fail."""
    errors, attempts, digests = [], [], {}
    def read(path):
        try:
            raw = path.read_bytes()
            value = json.loads(raw)
            digests[path] = shared.sha(raw)
            if not isinstance(value, dict):
                raise ValueError("expected an object")
            return value
        except Exception as exc:
            errors.append(f"{path.name}: {type(exc).__name__}: {str(exc)[:300]}")
            return None
    try:
        lines = (directory / "attempts.jsonl").read_text().splitlines()
        for number, line in enumerate(lines, 1):
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("expected an attempt object")
                attempts.append(value)
            except Exception as exc:
                errors.append(f"attempts.jsonl line {number}: {type(exc).__name__}")
    except Exception as exc:
        errors.append(f"attempts.jsonl: {type(exc).__name__}: {str(exc)[:300]}")
    output = read(directory / "review-1.json")
    workspaces = read(directory / "workspaces.json")
    audits = []
    for path in sorted((directory / "logs").glob("*.json")):
        value = read(path)
        if value is not None and value.get("tool") == "arbitrate":
            audits.append((path, value))
    if len(audits) != 1:
        errors.append("expected exactly one arbitration audit")
    audit_path, audit = audits[0] if len(audits) == 1 else (None, None)
    markers = {name: read(directory / name) for name in ("incomplete.json", "failed.json")
               if (directory / name).exists()}
    return TrialRecords(tuple(attempts), output, workspaces, audit_path, audit,
                        digests.get(audit_path), markers, tuple(errors))


def worker(root, index, digest):
    manifest, _ = load(root, digest)
    trial = preflight(root, manifest, index)
    source = manifest["sources"][trial["version"]]
    sys.path.insert(0, str(Path(source["path"]) / "src"))
    from paranoia_local import inert_tree, inert_git
    directory = root / f"trial-{index}"
    if Path(inert_tree.__file__).resolve() != Path(source["path"]) / "src/paranoia_local/inert_tree.py":
        raise ValueError("wrong import")
    lock, workspaces, provider_observations, by_cwd = Lock(), [], [], {}
    original_cwd = inert_tree.EvidenceWorkspace.cwd_for
    original_workspace = inert_tree.evidence_workspace
    original_install = shared.install_observer
    original_admit = shared.admit

    @contextmanager
    def workspace(repo, snapshot):
        with original_workspace(repo, snapshot) as view:
            row = {"root": str(view.tree.root), "snapshot": snapshot,
                   "before": rows_digest(observed_rows(view.tree.root)),
                   "expected": rows_digest(expected_rows(repo, snapshot, inert_git))}
            with lock:
                workspaces.append(row)
            try:
                yield view
            finally:
                row["after"] = rows_digest(observed_rows(view.tree.root))

    def cwd_for(view, engine_name):
        cwd = original_cwd(view, engine_name)
        with lock:
            row = next(r for r in workspaces if r["root"] == str(view.tree.root))
            row["provider"] = engine_name
            by_cwd[str(cwd)] = row
        return cwd

    def install(engines, directory, counter):
        original_install(engines, directory, counter)
        for operation in ("run", "resume"):
            original = getattr(engines.Engine, operation)
            signature = inspect.signature(original)
            def make(original=original, signature=signature):
                @wraps(original)
                def observed(*args, **kwargs):
                    values = signature.bind(*args, **kwargs).arguments
                    cwd = str(values.get("cwd"))
                    with lock:
                        row = by_cwd.get(cwd)
                        if row is not None:
                            provider_observations.append({
                                "provider": values["self"].name, "root": row["root"],
                                "snapshot": row["snapshot"],
                                "before": rows_digest(observed_rows(Path(row["root"]))),
                                "provider_attempt": 1 + sum(a["provider"] == values["self"].name
                                                           for a in provider_observations),
                            })
                    return original(*args, **kwargs)
                return observed
            setattr(engines.Engine, operation, make())

    inert_tree.EvidenceWorkspace.cwd_for = cwd_for
    inert_tree.evidence_workspace = workspace
    shared.install_observer = install
    shared.admit = lambda path, maximum=CALL_LIMIT: original_admit(path, maximum=CALL_LIMIT)
    path = directory / "input.json"
    shared.dump(path, {"source": source, "models": manifest["models"],
                       "input": trial["case"], "counter": str(root / "counter")})
    try:
        shared.worker(path)
        preflight(root, manifest, index)
    finally:
        for row in workspaces:
            row["cleaned_up"] = not Path(row["root"]).exists()
        shared.dump(directory / "workspaces.json",
                    {"rows": workspaces, "provider_attempts": provider_observations,
                     "source": source, "trial": index, "manifest_sha256": digest})


def run(root):
    manifest, digest = load(root)
    if any(root.glob("trial-*/workspaces.json")):
        raise ValueError("observations already exist; do not rerun selectively")
    blocked = None
    for index in range(8):
        try:
            if blocked:
                raise ValueError(blocked)
            load(root, digest)
            preflight(root, manifest, index)
        except Exception as exc:
            blocked = str(exc)
            shared.dump(root / f"trial-{index}" / "incomplete.json", {"error": blocked})
            continue
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", str(root),
                                 "--index", str(index), "--digest", digest],
                                capture_output=True, text=True)
        if result.returncode:
            shared.dump(root / f"trial-{index}" / "failed.json",
                        {"returncode": result.returncode, "stderr": result.stderr[-4000:]})
        print(f"completed live dispatch {index + 1}/8", flush=True)


def report(root):
    manifest, digest = load(root)
    rows, all_attempts = [], []
    for index, trial in enumerate(manifest["trials"]):
        records = collect_trial(root / f"trial-{index}")
        all_attempts.extend(records.attempts)
        output, trees, audit = records.output, records.workspaces, records.audit
        elapsed = output.get("elapsed_ms") if output is not None else None
        if type(elapsed) is not int or elapsed < 0:
            elapsed = None
        row = {"index": index, "case": trial["case"]["id"], "version": trial["version"],
               "repetition": trial["repetition"], "padding_files": trial["padding_files"],
               "qualified": False, "bound": False,
               "attempts": list(records.attempts), "elapsed_ms": elapsed,
               "output": output, "workspaces": trees, "worker_markers": records.markers,
               "collection_errors": list(records.errors),
               "outcome": audit.get("outcome") if audit else None,
               "selected": audit.get("selected") if audit else None,
               "audit": str(records.audit_path) if records.audit_path else None,
               "audit_sha256": records.audit_sha256}
        try:
            preflight(root, manifest, index)
            if records.errors or records.markers:
                raise ValueError("; ".join(records.errors) or "worker recorded failure/incompletion")
            if output is None or trees is None or audit is None or elapsed is None:
                raise ValueError("missing complete observation")
            if (trees["source"] != manifest["sources"][trial["version"]]
                    or trees["trial"] != index or trees["manifest_sha256"] != digest):
                raise ValueError("observation source binding mismatch")
            expected = manifest["oracle"][trial["case"]["id"]]
            correct = audit["outcome"] == "CONVERGED" and audit["selected"] == expected
            rendered = (f"ARBITRATION: CONVERGED" in output["result"]
                        and f"SELECTED: {expected}" in output["result"])
            workspace_ok = verify_workspaces(trees["rows"], trees["provider_attempts"], audit["snapshot"])
            decider_attempts = [a for a in records.attempts if a["role"] == "evidence-repository"]
            observed = trees["provider_attempts"]
            for engine in ("codex", "claude"):
                actual = sorted((a for a in decider_attempts if a["engine"] == engine),
                                key=lambda a: a["sequence"])
                observations = sorted((a for a in observed if a["provider"] == engine),
                                      key=lambda a: a["provider_attempt"])
                if len(actual) != len(observations) or not actual:
                    raise ValueError("missing provider-attempt workspace observation")
                for number, (a, o) in enumerate(zip(actual, observations), 1):
                    if o["provider_attempt"] != number:
                        raise ValueError("provider-attempt observation order mismatch")
                    o["attempt_sequence"] = a["sequence"]
            execution_ok = all(a.get("returncode") == 0 and not a.get("error")
                               and not a.get("exception") for a in records.attempts)
            row.update(bound=True, qualified=correct and rendered and workspace_ok and execution_ok,
                       false_convergence=audit["outcome"] == "CONVERGED" and not correct,
                       workspace_ok=workspace_ok, report_sha256=shared.sha(output["result"]))
        except Exception as exc:
            row["failure"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    paired = all(
        len(group := [r for r in rows if r["case"] == case and r["repetition"] == repetition]) == 2
        and all(r.get("workspace_ok") for r in group)
        and len({w["before"] for r in group for w in r["workspaces"]["rows"]}) == 1
        for case in manifest["oracle"] for repetition in range(2))
    start = manifest["starting_calls"]
    try:
        cumulative_calls = int((root / "counter").read_text())
        if not start <= cumulative_calls <= CALL_LIMIT:
            raise ValueError("counter outside frozen budget")
        calls = cumulative_calls - start
        sequences = [a.get("sequence") for a in all_attempts]
        ledger_ok = (all(type(s) is int for s in sequences)
                     and sorted(sequences) == list(range(start + 1, cumulative_calls + 1)))
    except Exception:
        cumulative_calls, calls, ledger_ok = None, None, False
    counts = {}
    for version in manifest["sources"]:
        selected = [r for r in rows if r["version"] == version]
        complete_timing = all(r["elapsed_ms"] is not None for r in selected)
        known_time = sum(r["elapsed_ms"] for r in selected if r["elapsed_ms"] is not None)
        counts[version] = {"correct": sum(r["qualified"] for r in selected),
                          "unresolved_or_failed": sum(not r["qualified"] for r in selected),
                          "provider_calls": sum(len(r["attempts"]) for r in selected),
                          "total_elapsed_ms": known_time if complete_timing else None,
                          "known_elapsed_ms": known_time, "timing_complete": complete_timing}
    qualified = (paired and ledger_ok and all(r["bound"] for r in rows)
                 and not any(r.get("false_convergence") for r in rows)
                 and counts["candidate"]["correct"] == 4
                 and counts["baseline"]["correct"] == 4)
    pairs = []
    for case in manifest["oracle"]:
        for repetition in range(2):
            pair = [r for r in rows if r["case"] == case and r["repetition"] == repetition]
            pairs.append({"case": case, "repetition": repetition,
                          "padding_files": pair[0]["padding_files"],
                          "versions": {r["version"]: {
                              "elapsed_ms": r["elapsed_ms"], "provider_calls": len(r["attempts"]),
                              "qualified": r["qualified"]} for r in pair}})
    result = {"pairs": pairs, "expected_baseline": manifest["expected_baseline"],
              "large_padding": manifest["large_padding"],
              "manifest_sha256": digest, "rows": rows, "paired_equivalence": paired,
              "calls": calls, "cumulative_calls": cumulative_calls,
              "prior_campaign": manifest["prior_campaign"],
              "ledger_complete": ledger_ok, "summary": counts, "qualified": qualified,
              "limits": "Eight live integration dispatches, not a population speed or quality study. "
                        "Elapsed dispatch times include symmetric workspace observation overhead."}
    shared.dump(root / "report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ["freeze", "run", "report", "worker"]:
        modes.add_argument("--" + mode, type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--index", type=int)
    parser.add_argument("--digest")
    parser.add_argument("--prior-report", type=Path)
    parser.add_argument("--expected-baseline")
    parser.add_argument("--large-padding", type=int, default=0, choices=[0, 3000])
    args = parser.parse_args()
    if args.freeze:
        freeze(args.freeze.resolve(), args.baseline, args.candidate, args.prior_report,
               expected_baseline=args.expected_baseline, large_padding=args.large_padding)
    elif args.run:
        run(args.run.resolve())
    elif args.report:
        print(json.dumps(report(args.report.resolve()), indent=2))
    else:
        worker(args.worker.resolve(), args.index, args.digest)


if __name__ == "__main__":
    main()
