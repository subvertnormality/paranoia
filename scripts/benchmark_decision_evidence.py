#!/usr/bin/env python3
"""Frozen eight-dispatch comparison for decision-evidence admission."""
import argparse
from contextlib import contextmanager
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


def freeze(root, baseline, candidate):
    root.mkdir(parents=True, exist_ok=False)
    sources = {"baseline": source_record(baseline), "candidate": source_record(candidate)}
    if sources["baseline"]["revision"] != BASELINE:
        raise ValueError("wrong baseline")
    cases, oracle = shared.corpus()
    cases = [case for case in cases if case["mode"] == "arbitrate"]
    versions = {name: subprocess.check_output([name, "--version"], text=True).strip()
                for name in ["codex", "claude"]}
    trials = []
    for n, case in enumerate(cases):
        fixture = root / f"fixture-{n}"
        fixture.mkdir()
        shared.git(fixture, "init", "-q", "-b", "main")
        shared.git(fixture, "config", "user.name", "snapshot acceptance")
        shared.git(fixture, "config", "user.email", "fixture@example.test")
        for name, body in case["files"].items():
            (fixture / name).write_text(body)
        shared.git(fixture, "add", ".")
        shared.git(fixture, "-c", "commit.gpgsign=false", "commit", "-qm", "Frozen contract")
        snapshot = shared.git(fixture, "rev-parse", "HEAD")
        for repetition in range(2):
            versions_in_pair = (["baseline", "candidate"] if (n + repetition) % 2 == 0
                                else ["candidate", "baseline"])
            for version in versions_in_pair:
                directory = root / f"trial-{len(trials)}"
                directory.mkdir()
                shared.git(root, "clone", "-q", "--no-hardlinks", str(fixture), str(directory / "repository"))
                trials.append({"version": version, "case": case, "snapshot": snapshot,
                               "repetition": repetition})
    harness = {str(Path(p).resolve()): shared.sha(Path(p).read_bytes())
               for p in [__file__, shared.__file__]}
    manifest = {"schema": 1, "sources": sources, "models": shared.MODELS,
                "versions": versions, "trials": trials, "harness": harness,
                "oracle": {case["id"]: oracle[case["id"]]["expected"] for case in cases},
                "call_limit": CALL_LIMIT}
    shared.dump(root / "manifest.json", manifest)
    (root / "manifest.sha256").write_text(shared.sha((root / "manifest.json").read_bytes()))
    (root / "counter").write_text("0")


def load(root, digest=None):
    raw = (root / "manifest.json").read_bytes()
    expected = digest or (root / "manifest.sha256").read_text().strip()
    if shared.sha(raw) != expected:
        raise ValueError("manifest changed")
    manifest = json.loads(raw)
    if manifest["schema"] != 1 or manifest["call_limit"] != CALL_LIMIT or len(manifest["trials"]) != 8:
        raise ValueError("invalid live campaign")
    return manifest, expected


def preflight(root, manifest, index):
    row = manifest["trials"][index]
    shared.validate_harness(manifest["harness"])
    shared.validate_source(manifest["sources"][row["version"]])
    repo = root / f"trial-{index}" / "repository"
    if shared.git(repo, "rev-parse", "HEAD") != row["snapshot"] or shared.git(repo, "status", "--porcelain"):
        raise ValueError("fixture changed")
    for name, version in manifest["versions"].items():
        if subprocess.check_output([name, "--version"], text=True).strip() != version:
            raise ValueError("provider version changed")
    return row


def source_record(path):
    path = Path(path).resolve()
    row = {"path": str(path), "revision": shared.git(path, "rev-parse", "HEAD"),
           "files": {str(p.relative_to(path)): shared.sha(p.read_bytes())
                     for p in sorted((path / "src/paranoia_local").glob("*.py"))}}
    shared.validate_source(row)
    return row


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
    rows = []
    all_attempts = []
    for index, trial in enumerate(manifest["trials"]):
        directory = root / f"trial-{index}"
        row = {"index": index, "case": trial["case"]["id"], "version": trial["version"],
               "repetition": trial["repetition"], "qualified": False, "bound": False}
        try:
            preflight(root, manifest, index)
            attempts_path = directory / "attempts.jsonl"
            attempts = [json.loads(line) for line in attempts_path.read_text().splitlines()]
            all_attempts.extend(attempts)
            row["attempts"] = attempts
            for name in ["incomplete.json", "failed.json"]:
                if (directory / name).exists():
                    raise ValueError((directory / name).read_text())
            audits = [(p, json.loads(p.read_text())) for p in (directory / "logs").glob("*.json")]
            p, audit = next((p, a) for p, a in audits if a.get("tool") == "arbitrate")
            output = json.loads((directory / "review-1.json").read_text())
            trees = json.loads((directory / "workspaces.json").read_text())
            seen = trees["rows"]
            if (trees["source"] != manifest["sources"][trial["version"]]
                    or trees["trial"] != index or trees["manifest_sha256"] != digest):
                raise ValueError("observation source binding mismatch")
            expected = manifest["oracle"][trial["case"]["id"]]
            correct = audit["outcome"] == "CONVERGED" and audit["selected"] == expected
            rendered = (f"ARBITRATION: CONVERGED" in output["result"]
                        and f"SELECTED: {expected}" in output["result"])
            workspace_ok = (set(r.get("provider") for r in seen) == {"codex", "claude"}
                            and len({r["root"] for r in seen}) == len(seen)
                            and all(verify_workspace(r, trees["provider_attempts"]) for r in seen)
                            and all(r["snapshot"] == audit["snapshot"] for r in seen))
            decider_attempts = [a for a in attempts if a["role"] == "evidence-repository"]
            observed = trees["provider_attempts"]
            # Join ordinal observations to actual admitted attempt sequence per provider.
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
                               and not a.get("exception") for a in attempts)
            row.update(bound=True, qualified=correct and rendered and workspace_ok and execution_ok,
                       outcome=audit["outcome"], selected=audit["selected"],
                       false_convergence=audit["outcome"] == "CONVERGED" and not correct,
                       elapsed_ms=output["elapsed_ms"], workspaces=trees,
                       workspace_ok=workspace_ok, audit=str(p),
                       audit_sha256=shared.sha(p.read_bytes()),
                       report_sha256=shared.sha(output["result"]))
        except Exception as exc:
            row["failure"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    paired = all(
        len(group := [r for r in rows if r["case"] == case and r["repetition"] == repetition]) == 2
        and all(r.get("workspace_ok") for r in group)
        and len({w["before"] for r in group for w in r["workspaces"]["rows"]}) == 1
        for case in manifest["oracle"] for repetition in range(2))
    calls = int((root / "counter").read_text())
    sequences = [a["sequence"] for a in all_attempts]
    ledger_ok = sorted(sequences) == list(range(1, calls + 1)) and calls <= CALL_LIMIT
    counts = {v: {"correct": sum(r["qualified"] for r in rows if r["version"] == v),
                  "unresolved_or_failed": sum(not r["qualified"] for r in rows if r["version"] == v),
                  "provider_calls": sum(len(r.get("attempts", [])) for r in rows if r["version"] == v),
                  "total_elapsed_ms": sum(r.get("elapsed_ms", 0) for r in rows if r["version"] == v)}
              for v in manifest["sources"]}
    qualified = (paired and ledger_ok and all(r["bound"] for r in rows)
                 and not any(r.get("false_convergence") for r in rows)
                 and counts["candidate"]["correct"] == 4
                 and counts["candidate"]["unresolved_or_failed"] <= counts["baseline"]["unresolved_or_failed"])
    result = {"manifest_sha256": digest, "rows": rows, "paired_equivalence": paired,
              "calls": calls, "ledger_complete": ledger_ok, "summary": counts, "qualified": qualified,
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
    args = parser.parse_args()
    if args.freeze:
        freeze(args.freeze.resolve(), args.baseline, args.candidate)
    elif args.run:
        run(args.run.resolve())
    elif args.report:
        print(json.dumps(report(args.report.resolve()), indent=2))
    else:
        worker(args.worker.resolve(), args.index, args.digest)


if __name__ == "__main__":
    main()
