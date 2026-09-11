#!/usr/bin/env python3
"""Run a source-bound, fresh MCP plan review; retain local evidence, not a bypass."""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import hashlib
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
HARNESS_FILES = (
    "scripts/run_claim_admission_acceptance.py",
    "scripts/benchmark_bootstrap.py",
    "scripts/benchmark_review_modes.py",
)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value) -> str:
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=True).encode())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")


def helpers(root):
    return runpy.run_path(str(root / "scripts/benchmark_review_modes.py"))


def freeze(root: Path, request: dict) -> dict:
    root = root.resolve()
    lineage, round_no = request.get("lineage"), request.get("round")
    if request.get("class_closure", True) is not True:
        raise ValueError("acceptance requires tracked class closure")
    if not isinstance(lineage, str) or not lineage or Path(lineage).name != lineage:
        raise ValueError("acceptance requires an explicit lineage")
    if type(round_no) is not int or round_no < 1:
        raise ValueError("acceptance requires a positive integer round")
    if request.get("engine") != "claude" or request.get("claim_verification", True) is not True:
        raise ValueError("acceptance requires the native Claude claim-verification route")
    if "plan_path" in request or not isinstance(request.get("plan_text"), str):
        raise ValueError("acceptance requires frozen plan_text")
    manifest = {
        "source": helpers(root)["source_record"](root),
        "harness": {name: sha((root / name).read_bytes()) for name in HARNESS_FILES},
        "interpreter": str(Path(sys.executable).absolute()),
        "resolved_interpreter": str(Path(sys.executable).resolve()),
        "tool": "critique_plan", "request": request,
        "state_root": str(Path(os.environ.get("PARANOIA_STATE_ROOT") or Path.home() / ".paranoia").resolve()),
    }
    predecessor = Path(manifest["state_root"]) / "lineages" / f"{lineage}.json"
    raw = predecessor.read_bytes() if predecessor.exists() else None
    if round_no > 1 and raw is None:
        raise ValueError("continuation predecessor lineage is missing")
    last_round = json.loads(raw).get("review_state", {}).get("last_round") if raw is not None else None
    if type(last_round) is int and round_no <= last_round:
        raise ValueError("requested round must exceed predecessor last_round")
    manifest["predecessor_sha256"] = sha(raw) if raw is not None else None
    verify_identity(manifest, modules={})
    return manifest


def verify_predecessor(manifest):
    root = Path(os.environ.get("PARANOIA_STATE_ROOT") or Path.home() / ".paranoia").resolve()
    if str(root) != manifest["state_root"]:
        raise ValueError("predecessor state root differs from frozen selection")
    path = root / "lineages" / (manifest["request"]["lineage"] + ".json")
    current = sha(path.read_bytes()) if path.exists() else None
    if current != manifest["predecessor_sha256"]:
        raise ValueError("predecessor lineage changed before dispatch")


def verify_identity(manifest: dict, *, modules=None) -> dict:
    source = manifest["source"]
    root = Path(source["path"])
    if set(manifest["harness"]) != set(HARNESS_FILES):
        raise ValueError("harness inventory changed")
    for name, expected in manifest["harness"].items():
        current = (root / name).read_bytes()
        committed = subprocess.run(
            ["git", "show", f"{source['revision']}:{name}"], cwd=root,
            check=True, capture_output=True,
        ).stdout
        if sha(current) != expected or current != committed:
            raise ValueError(f"harness binding changed: {name}")
    if str(Path(sys.executable).resolve()) != manifest["resolved_interpreter"]:
        raise ValueError("interpreter binding changed")
    helpers(root)["validate_source"](source)
    loaded = {}
    for name, module in (sys.modules if modules is None else modules).copy().items():
        if name != "paranoia_local" and not name.startswith("paranoia_local."):
            continue
        path = Path(getattr(module, "__file__", "")).resolve()
        stem = "src/" + name.replace(".", "/")
        candidates = [stem + ".py", stem + "/__init__.py"]
        if not any(relative in source["files"] and path == root / relative for relative in candidates):
            raise ValueError(f"loaded module does not match selected source: {name}")
        loaded[name] = str(path)
    return loaded


def make_receipt(manifest, response, audit_path, loaded):
    return {
        "manifest_sha256": digest(manifest), "response_sha256": sha(response.encode()),
        "audit_path": str(audit_path), "audit_sha256": sha(Path(audit_path).read_bytes()),
        "loaded_modules": loaded,
    }


def validate_receipt(manifest, receipt, response):
    loaded = receipt["loaded_modules"]
    if "paranoia_local.server" not in loaded:
        raise ValueError("receipt has no loaded server identity")
    verify_identity(manifest, modules={
        name: SimpleNamespace(__file__=path) for name, path in loaded.items()
    })
    if receipt["manifest_sha256"] != digest(manifest) or receipt["response_sha256"] != sha(response.encode()):
        raise ValueError("request or response receipt binding changed")
    audit_bytes = Path(receipt["audit_path"]).read_bytes()
    if sha(audit_bytes) != receipt["audit_sha256"]:
        raise ValueError("audit receipt binding changed")
    audit = json.loads(audit_bytes)
    if (audit.get("class_closure") is not True or audit.get("engine") != "claude"
            or audit.get("lineage") != manifest["request"]["lineage"]
            or audit.get("round") != manifest["request"]["round"]):
        raise ValueError("audit tracking differs from frozen invocation")
    trailer = audit.get("rendered_trailer") or ""
    if "STRUCTURAL-PHASE:" not in trailer or "\nCONVERGENCE:" not in trailer:
        raise ValueError("audit has no tracked structural result")
    ledger = audit["attempt_ledger"]
    for index, row in enumerate(ledger):
        if (row["role"] in {"claim-binding", "claim-binding-validation-retry"}
                and row["outcome"] == "completed" and not row.get("session_ref")):
            raise ValueError("native binding completion has no provider session")
        if row["outcome"] != "validation-invalid":
            continue
        retry = next((later for later in ledger[index + 1:]
                      if later["role"] == row["role"] + "-validation-retry"), None)
        if (row["role"].endswith("-validation-retry") or not row.get("session_ref")
                or retry is None or retry["outcome"] != "completed"
                or retry.get("session_ref") != row["session_ref"]):
            raise ValueError("native validation failure was not successfully repaired")
    if (audit["returncode"] != 0 or audit["error"] or audit["claim_audit_failed"]
            or not audit["claim_status"].startswith("parsed ") or audit["claim_model_calls"] < 1
            or not any(row["role"] in {"claim-discovery", "claim-discovery-validation-retry"}
                       and row["outcome"] == "completed"
                       for row in audit["attempt_ledger"])
            or any(row["outcome"] not in {"completed", "validation-invalid", "checkpoint"}
                   or type(row.get("returncode")) is not int or row["returncode"] != 0
                   for row in audit["attempt_ledger"])):
        raise ValueError("native claim/provider acceptance failed; retain the actual audit")


def load_source(manifest):
    verify_predecessor(manifest)
    if any(name == "paranoia_local" or name.startswith("paranoia_local.") for name in sys.modules):
        raise ValueError("production package was loaded before source verification")
    verify_identity(manifest, modules={})
    root = Path(manifest["source"]["path"])
    if Path(__file__).resolve() != root / HARNESS_FILES[0]:
        raise ValueError("launcher belongs to another source installation")
    runpy.run_path(str(root / "scripts/benchmark_bootstrap.py"))
    sys.path.insert(0, str(root / "src"))
    server = importlib.import_module("paranoia_local.server")
    return server, verify_identity(manifest)


def bound_dispatch(manifest, directory, dispatch):
    def invoke(name, arguments, **kwargs):
        if name != manifest["tool"] or arguments != manifest["request"]:
            raise ValueError("MCP request differs from frozen invocation")
        verify_identity(manifest)
        verify_predecessor(manifest)
        started = time.monotonic()
        response = dispatch(name, arguments, **kwargs)
        (directory / "native-result.txt").write_text(response)
        loaded = verify_identity(manifest)
        audits = list((directory / "logs").glob("*-critique_plan-*.json"))
        if len(audits) != 1:
            raise ValueError("native invocation must retain exactly one audit")
        receipt = make_receipt(manifest, response, audits[0], loaded)
        receipt["elapsed_seconds"] = time.monotonic() - started
        write(directory / "receipt.json", receipt)
        return response
    return invoke


def server_parameters(manifest, directory):
    from mcp import StdioServerParameters
    script = Path(manifest["source"]["path"]) / HARNESS_FILES[0]
    return StdioServerParameters(
        command=manifest["interpreter"],
        args=["-I", str(script), "--serve", str(directory / "manifest.json")],
        env={"PARANOIA_STATE_ROOT": manifest["state_root"]},
    )


async def client(manifest, directory):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    params = server_parameters(manifest, directory)
    with (directory / "server-stderr.txt").open("w") as stderr:
        async with stdio_client(params, errlog=stderr) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=8700)) as session:
                await session.initialize()
                result = await session.call_tool(manifest["tool"], manifest["request"])
    response = "\n".join(block.text for block in result.content if block.type == "text")
    (directory / "response.txt").write_text(response)
    if result.isError:
        raise ValueError("MCP invocation failed; retained response is not acceptance")
    receipt = json.loads((directory / "receipt.json").read_text())
    validate_receipt(manifest, receipt, response)
    write(directory / "accepted.json", receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", type=Path)
    parser.add_argument("--verify-only", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.serve or args.verify_only:
        path = args.serve or args.verify_only
        manifest = json.loads(path.read_text())
        server, loaded = load_source(manifest)
        if args.verify_only:
            print(json.dumps(loaded))
            return
        server.dispatch = bound_dispatch(manifest, path.parent, server.dispatch)
        asyncio.run(server.run_stdio(server.build_server(
            default_engine_name="claude", log_dir=path.parent / "logs",
        )))
        return
    if not args.request or not args.output:
        parser.error("provide --request and a new --output directory")
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        manifest = freeze(ROOT, json.loads(args.request.read_text()))
        write(args.output / "manifest.json", manifest)
        asyncio.run(client(manifest, args.output))
    except Exception as error:
        write(args.output / "failure.json", {"error": str(error), "type": type(error).__name__})
        raise


if __name__ == "__main__":
    main()
