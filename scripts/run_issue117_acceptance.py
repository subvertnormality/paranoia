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


def native(out):
    out.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (out / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")
    shared, source = load_source(ROOT)
    source_id = shared.sha(json.dumps(source, sort_keys=True).encode())
    helper_files = {}
    for name in ("scripts/run_issue117_acceptance.py", "scripts/benchmark_bootstrap.py",
                 "scripts/benchmark_review_modes.py"):
        raw = (ROOT / name).read_bytes()
        committed = subprocess.check_output(["git", "show", source["revision"] + ":" + name], cwd=ROOT)
        if raw != committed:
            raise ValueError("uncommitted acceptance helper: " + name)
        helper_files[name] = shared.sha(raw)
    write("source.json", {"production": source, "source_id": source_id, "helpers": helper_files})
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
    repo.mkdir()
    (repo / "README.md").write_text("# Release record fixture\nRecord the release date in release-notes.md.\n")
    for args in (["init", "-q"], ["add", "."], ["-c", "user.name=Codex", "-c",
                  "user.email=codex@openai.com", "commit", "-qm", "Fixture"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    plan = "# Release record\n\nPython 3.11.0 was released on October 24, 2022.\n"
    arguments = {"repo_path": str(repo), "plan_text": plan, "lineage": "issue117-native",
        "round": 1, "model": "opus", "effort": "high", "claim_verification": True,
        "web_search": True, "stakes": "Trusted single operator and OS. One tiny repository and one external release-date claim; static inputs, ordinary edits invalidate bindings, existing CLI network boundaries and native concurrency/timeouts. False evidence clearance high impact; recoverable blocking acceptable. No hostile local races, compromised OS, multi-tenancy or corrupted-state recovery."}
    write("invocation.json", {"source_id": source_id, "arguments": arguments})
    original = engines.Engine._execute
    attempts = []
    lock = threading.Lock()
    def observe(self, argv, prompt, cwd, runner, timeout, on_progress=None, response_schema=None):
        with lock:
            if len(attempts) >= 12:
                raise RuntimeError("issue117 native attempt ceiling exhausted")
            number = len(attempts) + 1
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
        result = server.dispatch("critique_plan", arguments, default_engine_name="claude", log_dir=out / "logs")
        (out / "result.txt").write_text(result)
        state = cc.load_lineage(cc.default_state_root(), "issue117-native", stamp="after", mode=cc.PLAN_MODE)
        write("durable.json", cc._to_json(state))
        write("loaded-after.json", loaded())
        audit_files = list((out / "logs").glob("*-critique_plan-*.json"))
        trace_files = list((out / "logs").glob("*-run-*.json"))
        assert len(audit_files) == len(trace_files) == 1
        audit = json.loads(audit_files[0].read_text())
        trace = json.loads(trace_files[0].read_text())
        assert len(audit["attempt_ledger"]) == len(trace["attempts"]) == len(attempts)
        assert Counter(a["prompt_sha256"] for a in trace["attempts"]) == Counter(a["prompt_sha256"] for a in attempts)
        assert trace["source_observed_at_import"]["revision"] == source["revision"]
        for phase in ("claim-discovery", "claim-binding", "claim-attestation"):
            assert any(a["role"] == phase and a["outcome"] == "completed" for a in audit["attempt_ledger"])
        assert any(a["role"] == engines.ROLE_TEXT for a in attempts)
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
            "attempts": len(attempts), "supported_claims": len(claims),
            "elapsed_ms": round((time.monotonic()-started)*1000),
            "scope": "Native current-source attestation usability; forced correction is deterministic test evidence."})
        print("QUALIFIED", flush=True)
    except BaseException as exc:
        write("qualification.json", {"qualified": False, "source_id": source_id,
            "attempts": len(attempts), "error": repr(exc), "traceback": traceback.format_exc(),
            "elapsed_ms": round((time.monotonic()-started)*1000)})
        raise
    finally:
        engines.Engine._execute = original


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    native(parser.parse_args().output.resolve())
