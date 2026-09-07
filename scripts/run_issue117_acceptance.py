"""One frozen native public-adapter acceptance for issue 117; no provider retry loop."""
import sys
import runpy
from pathlib import Path

# This entry is executed as source in a fresh interpreter, before owned imports.
if any(name == "paranoia_local" or name.startswith("paranoia_local.")
       or name in {"benchmark_review_modes", "benchmark_bootstrap", "scripts.benchmark_review_modes"}
       for name in sys.modules):
    raise RuntimeError("issue117 rejects preloaded owned modules")
ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts/benchmark_bootstrap.py"))

import argparse
from collections import Counter
import dataclasses
import hashlib
import json
import os
import subprocess
import shutil
import tarfile
import threading
import time
import traceback


def load_source(root):
    if any(name == "paranoia_local" or name.startswith("paranoia_local.") for name in sys.modules):
        raise RuntimeError("issue117 rejects preloaded owned modules")
    sys.path.insert(0, str(ROOT / "scripts"))
    import benchmark_review_modes as shared
    source = shared.source_record(root)
    shared.validate_source(source)
    return shared, source


def _require_evidence_phases(ledger):
    for phase in ("claim-discovery", "claim-binding", "claim-attestation"):
        attempts = [a for a in ledger if a["role"] in {phase, phase + "-validation-retry"}]
        assert attempts and attempts[0]["role"] == phase
        assert attempts[-1]["outcome"] == "completed"



PARENT_ARCHIVE_SHA256 = "471a0b5407614ba1c170ba991d8cfac02b0e0b5af9958064e2eb4ea5af615e56"


def _load_parent(parent, source):
    """Admit only the preserved eight-call campaign, never an edited/restarted parent."""
    archive = ROOT / "docs/attestation-envelope-117-native-evidence.tar.gz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == PARENT_ARCHIVE_SHA256
    with tarfile.open(archive) as retained:
        members = retained.getmembers()
        assert all(m.isfile() and not Path(m.name).is_absolute()
                   and ".." not in Path(m.name).parts for m in members)
        assert {str(f.relative_to(parent)) for f in parent.rglob("*") if f.is_file()} == {m.name for m in members}
        for member in members:
            path = parent / member.name
            assert not path.is_symlink() and path.read_bytes() == retained.extractfile(member).read()
    read = lambda name: json.loads((parent / name).read_text())
    old_source = read("source.json")
    assert old_source["production"]["files"] == source["files"], "continuation changes production"
    assert read("qualification.json")["qualified"] is False
    inputs = [read(f"attempt-{i:02d}-input.json") for i in range(1, 9)]
    audit = json.loads(next((parent / "logs").glob("*-critique_plan-*.json")).read_text())
    assert read("qualification.json")["attempts"] == len(inputs) == len(audit["attempt_ledger"]) == 8
    _require_evidence_phases(audit["attempt_ledger"])
    return {"source": old_source, "inputs": inputs, "ledger": audit["attempt_ledger"],
            "arguments": read("invocation.json")["arguments"]}


def native(out, parent=None):
    out.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (out / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")
    shared, source = load_source(ROOT)
    prior = _load_parent(parent, source) if parent is not None else None
    base_calls = len(prior["inputs"]) if prior else 0
    source_id = shared.sha(json.dumps(source, sort_keys=True).encode())
    helper_files = {}
    for name in ("scripts/run_issue117_acceptance.py", "scripts/benchmark_bootstrap.py",
                 "scripts/benchmark_review_modes.py", "docs/attestation-envelope-117-fixture-repair.md"):
        raw = (ROOT / name).read_bytes()
        committed = subprocess.check_output(["git", "show", source["revision"] + ":" + name], cwd=ROOT)
        if raw != committed:
            raise ValueError("uncommitted acceptance helper: " + name)
        helper_files[name] = shared.sha(raw)
    write("source.json", {"production": source, "source_id": source_id, "helpers": helper_files})
    if prior:
        shutil.copytree(parent / "state", out / "state")
        write("parent.json", {"archive_sha256": PARENT_ARCHIVE_SHA256,
            "source": prior["source"], "base_calls": base_calls,
            "seed_state_sha256": shared.sha((out / "state/lineages/issue117-native.json").read_bytes())})
    os.environ["PARANOIA_STATE_ROOT"] = str(out / "state")
    sys.path.insert(0, str(ROOT / "src"))
    from paranoia_local import class_closure as cc, engines, handlers, plan_claims as pc, server

    def loaded():
        shared.validate_source(source)
        observed = {}
        for name, module in tuple(sys.modules.items()):
            if name == "paranoia_local" or name.startswith("paranoia_local."):
                path = Path(module.__file__).resolve()
                relative = path.relative_to(ROOT).as_posix()
                if path.is_symlink() or relative not in source["files"]:
                    raise ValueError("unbound loaded production module")
                digest = shared.sha(path.read_bytes())
                if digest != source["files"][relative]:
                    raise ValueError("loaded production source mismatch")
                observed[name] = {"path": str(path), "sha256": digest}
        if not observed:
            raise ValueError("no loaded production modules")
        for name, digest in helper_files.items():
            if shared.sha((ROOT / name).read_bytes()) != digest:
                raise ValueError("acceptance helper changed")
        return observed

    write("loaded-before.json", loaded())
    write("runtime.json", {"requested_model": "opus", "effort": "high",
        "claude_version": subprocess.check_output(["claude", "--version"], text=True).strip(),
        "python": sys.version, "source_id": source_id, "attempt_ceiling": 12,
        "pycache_prefix": sys.pycache_prefix, "dont_write_bytecode": sys.dont_write_bytecode})
    repo = out / "repository"
    if prior:
        shutil.copytree(parent / "repository", repo)
    else:
        repo.mkdir()
        (repo / "README.md").write_text("# Release record fixture\nRecord the release date in release-notes.md.\n")
        for args in (["init", "-q"], ["add", "."], ["-c", "user.name=Codex", "-c",
                      "user.email=codex@openai.com", "commit", "-qm", "Fixture"]):
            subprocess.run(["git", *args], cwd=repo, check=True)
    plan = "# Release record\n\nPython 3.11.0 was released on October 24, 2022.\n"
    arguments = {"repo_path": str(repo), "plan_text": plan, "lineage": "issue117-native",
        "round": 1, "model": "opus", "effort": "high", "claim_verification": True,
        "web_search": True, "stakes": "Trusted single operator and OS. One tiny repository and one external release-date claim; static inputs, ordinary edits invalidate bindings, existing CLI network boundaries and native concurrency/timeouts. False evidence clearance high impact; recoverable blocking acceptable. No hostile local races, compromised OS, multi-tenancy or corrupted-state recovery."}
    if prior:
        arguments = prior["arguments"] | {"repo_path": str(repo), "round": 2,
            "plan_text": (ROOT / "docs/attestation-envelope-117-fixture-repair.md").read_text()}
    write("invocation.json", {"source_id": source_id, "arguments": arguments})
    original = engines.Engine._execute
    attempts = []
    lock = threading.Lock()
    def observe(self, argv, prompt, cwd, runner, timeout, on_progress=None, response_schema=None):
        with lock:
            if base_calls + len(attempts) >= 12:
                raise RuntimeError("issue117 native attempt ceiling exhausted")
            number = base_calls + len(attempts) + 1
            row = {"sequence": number, "source_id": source_id, "role": self.role,
                   "argv": argv, "prompt": prompt, "prompt_sha256": shared.sha(prompt.encode()),
                   "response_schema": response_schema, "cwd": str(cwd), "timeout": timeout}
            attempts.append(row)
        if self.role == engines.ROLE_TEXT:
            packet = prompt.rsplit("\n\n", 1)[1]
            if prompt.startswith("You are a cold evidence attester"):
                expected = handlers._CapturedClaimEngine._attestation_prompt(json.loads(packet))
            else:
                lead = "Your cold evidence attestation was rejected: "
                issue = prompt[len(lead):].split(". Discard the entire ", 1)[0]
                expected = handlers._CapturedClaimEngine._attestation_correction_prompt(packet, issue)
            if prompt != expected or handlers.ATTESTATION_OUTPUT_INSTRUCTIONS not in prompt:
                raise ValueError("actual native attestation prompt differs from source renderer")
        write(f"attempt-{number:02d}-input.json", row)
        print(f"native attempt {number}: {self.role}", flush=True)
        started = time.monotonic()
        try:
            result = original(self, argv, prompt, cwd, runner, timeout, on_progress, response_schema)
            write(f"attempt-{number:02d}-output.json", dataclasses.asdict(result))
            return result
        finally:
            write(f"attempt-{number:02d}-duration.json", {"elapsed_ms": round((time.monotonic()-started)*1000)})
    engines.Engine._execute = observe
    started = time.monotonic()
    try:
        rounds = (2, 3) if prior else (1,)
        for round_no in rounds:
            current = arguments | {"round": round_no}
            write(f"invocation-{round_no}.json", {"source_id": source_id, "arguments": current})
            result = server.dispatch("critique_plan", current, default_engine_name="claude", log_dir=out / "logs")
            (out / f"result-{round_no}.txt").write_text(result)
            state = cc.load_lineage(cc.default_state_root(), "issue117-native", stamp="after", mode=cc.PLAN_MODE)
            write(f"durable-{round_no}.json", cc._to_json(state))
            if not prior or state.review_state.get("phase") != "final" or pc.is_blocked(state.claim_state):
                break
        (out / "result.txt").write_text(result)
        state = cc.load_lineage(cc.default_state_root(), "issue117-native", stamp="after", mode=cc.PLAN_MODE)
        write("durable.json", cc._to_json(state))
        write("loaded-after.json", loaded())
        audit_files = list((out / "logs").glob("*-critique_plan-*.json"))
        trace_files = list((out / "logs").glob("*-run-*.json"))
        assert len(audit_files) == len(trace_files) == len(list(out.glob("result-*.txt")))
        ledger = [a for f in sorted(audit_files) for a in json.loads(f.read_text())["attempt_ledger"]]
        traces = [json.loads(f.read_text()) for f in sorted(trace_files)]
        traced = [a for trace in traces for a in trace["attempts"]]
        assert len(ledger) == len(traced) == len(attempts)
        assert Counter(a["prompt_sha256"] for a in traced) == Counter(a["prompt_sha256"] for a in attempts)
        assert all(t["source_observed_at_import"]["revision"] == source["revision"] for t in traces)
        _require_evidence_phases((prior["ledger"] if prior else []) + ledger)
        assert any(a["role"] == engines.ROLE_TEXT for a in (prior["inputs"] if prior else []) + attempts)
        if prior:
            assert _load_parent(parent, source) == prior
            assert state.review_state.get("phase") == "clear"
        assert not pc.is_blocked(state.claim_state)
        claims = list(state.claim_state["claims"].values())
        assert claims and all(c["verdict"] == "supported" for c in claims)
        for claim in claims:
            assert claim["evidence"]
            assert claim["capture_attestations"] and claim["capture_provenance"]
            assert all(e["publisher_authority"] and e["passage_entailment"]
                       for e in claim["capture_attestations"])
        verdicts = [line for line in result.splitlines() if line.startswith("CONVERGENCE:")]
        assert len(verdicts) == 1 and verdicts[0].startswith("CONVERGENCE: NOT-BLOCKED")
        write("qualification.json", {"qualified": True, "source_id": source_id,
            "attempts": base_calls + len(attempts), "new_attempts": len(attempts), "supported_claims": len(claims),
            "elapsed_ms": round((time.monotonic()-started)*1000),
            "scope": "Native current-source attestation usability; forced correction is deterministic test evidence."})
        print("QUALIFIED", flush=True)
    except BaseException as exc:
        write("qualification.json", {"qualified": False, "source_id": source_id,
            "attempts": base_calls + len(attempts), "new_attempts": len(attempts), "error": repr(exc), "traceback": traceback.format_exc(),
            "elapsed_ms": round((time.monotonic()-started)*1000)})
        raise
    finally:
        engines.Engine._execute = original


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--continue-from", type=Path)
    args = parser.parse_args()
    native(args.output.resolve(), args.continue_from.resolve() if args.continue_from else None)
