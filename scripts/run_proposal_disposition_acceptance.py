"""Live issue-138 acceptance through the public branch handler, with retained audits.

This controlled arithmetic fixture permits only the already inspected exact remedy.
It does not apply arbitrary reviewer code. Run from a committed source checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from paranoia_local import class_closure as cc, engines, handlers
from benchmark_review_modes import source_record, validate_source

STAKES = (
    "Trusted single operator and OS; untrusted static repository bytes. No hostile "
    "local process or OS compromise. One arithmetic function, a few findings, results "
    "within minutes. Wrong clearance is high impact; recoverable blocking acceptable. "
    "No network service, concurrency or formal proof."
)
GOOD = "def divide(numerator, denominator):\n    return numerator / denominator\n"
BAD = "def divide(numerator, denominator):\n    return denominator / numerator\n"
PATCH = (
    "diff --git a/divide.py b/divide.py\n--- a/divide.py\n+++ b/divide.py\n"
    "@@ -1,2 +1,2 @@\n def divide(numerator, denominator):\n"
    "-    return denominator / numerator\n+    return numerator / denominator\n"
)


def run(output: Path, *, lfs: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=False)
    source = source_record(ROOT)
    repo = output / "repo"
    repo.mkdir()
    state_root = output / "state"
    os.environ["PARANOIA_STATE_ROOT"] = str(state_root)
    lineage_id = "issue139-live-lfs" if lfs else "issue138-live-branch"

    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Paranoia acceptance")
    git("config", "user.email", "acceptance@localhost")
    lfs_fixture = None
    if lfs:
        git("lfs", "install", "--local", "--skip-smudge")
        (repo / ".gitattributes").write_text("data.bin filter=lfs diff=lfs merge=lfs -text\n")
        payload = b"inert dataset\x00\xff\n" * 16384
        (repo / "data.bin").write_bytes(payload)
        lfs_fixture = {
            "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "git_lfs_version": git("lfs", "version"),
        }
    (repo / "divide.py").write_text(GOOD, encoding="utf-8")
    (repo / "README.md").write_text(
        "Contract: divide(numerator, denominator) returns numerator divided by "
        "denominator. Zero denominator raises ZeroDivisionError.\n", encoding="utf-8",
    )
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "baseline")
    baseline = git("rev-parse", "HEAD")
    (repo / "divide.py").write_text(BAD, encoding="utf-8")
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "inverted operands")
    record = {
        "kind": "issue139-native-lfs-proposal" if lfs else "issue138-native-proposal-disposition",
        "source": source,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "stakes": STAKES, "baseline": baseline, "rounds": [], "outcome": "incomplete",
    }
    if lfs:
        lfs_fixture["pointer"] = git("show", "HEAD:data.bin") + "\n"
        lfs_fixture["status"] = git("status", "--porcelain")
        assert lfs_fixture["status"] == ""
        assert lfs_fixture["pointer"] == (
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{lfs_fixture['sha256']}\nsize {lfs_fixture['size']}\n"
        )
        record["lfs_fixture"] = lfs_fixture
    receipt = None
    for round_no in (1, 2, 3):
        validate_source(source)
        if lfs:
            assert hashlib.sha256((repo / "data.bin").read_bytes()).hexdigest() == lfs_fixture["sha256"]
            assert git("status", "--porcelain") == ""
        logs = output / f"logs-{round_no}"
        args = dict(
            repo_path=str(repo), base_ref=baseline, head_ref="HEAD", lineage=lineage_id,
            round=round_no, stakes=STAKES, web_search=False,
            review_model_policy="strongest", propose_patch=round_no == 1,
        )
        if round_no == 2:
            args["prior_proposal_disposition"] = {
                "proposal_audit": receipt["audit"], "status": "applied", "departed_targets": {},
            }
        text = handlers.critique_branch(
            args, engine=engines.CodexEngine(), log_dir=logs,
            on_progress=lambda progress: print(progress, flush=True),
        )
        (output / f"round-{round_no}.txt").write_text(text, encoding="utf-8")
        lineage = cc.load_lineage(state_root, lineage_id, stamp="read")
        audits = {p.name: json.loads(p.read_text()) for p in sorted(logs.glob("*.json"))}
        main = [v for k, v in audits.items() if "patch_proposal" not in k]
        assert len(main) == 1 and text.endswith(main[0]["rendered_trailer"])
        record["rounds"].append({
            "round": round_no, "arguments": args, "result": text, "audits": audits,
            "durable_lineage": cc._to_json(lineage),
        })
        (output / "acceptance.json").write_text(json.dumps(record, indent=2) + "\n")
        if round_no == 1:
            assert "PATCH-PROPOSAL: PROPOSED" in text
            assert "APPLICATION-SUITABILITY: CURRENT" in text
            receipt = lineage.proposal_receipt
            patch = text.split("```diff\n", 1)[1].split("```", 1)[0]
            assert patch == PATCH  # inspect by exact allowlist before any execution
            assert hashlib.sha256(patch.encode()).hexdigest() == receipt["patch_sha256"]
            assert receipt["target_ids"] and receipt["audit"] in audits
            for options in (["--check"], []):
                subprocess.run(["git", "-C", str(repo), "apply", *options, "-"],
                               input=patch, text=True, check=True)
            assert (repo / "divide.py").read_text() == GOOD
            divide = runpy.run_path(str(repo / "divide.py"))["divide"]
            assert divide(6, 3) == 2 and divide(0, 3) == 0
            try:
                divide(3, 0)
            except ZeroDivisionError:
                pass
            else:
                raise AssertionError("zero denominator accepted")
            git("add", ".")
            git("-c", "commit.gpgsign=false", "commit", "-qm", "apply inspected diff")
        elif round_no == 2:
            assert main[0]["proposal_disposition"] == {
                "receipt": receipt, "status": "applied", "departed_targets": {},
            }
            assert "PROPOSAL-DISPOSITION: applied" in text
            assert lineage.review_state["phase"] == "final"
        else:
            assert main[0]["proposal_disposition"] is None
            assert "PROPOSAL-DISPOSITION:" not in text
            assert lineage.review_state["phase"] == "clear"
            assert "CONVERGENCE: NOT-BLOCKED" in text
    validate_source(source)
    record["outcome"] = "passed"
    (output / "acceptance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Native acceptance passed: {output / 'acceptance.json'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lfs", action="store_true", help="Native issue-139 LFS fixture")
    args = parser.parse_args()
    run(args.output.resolve(), lfs=args.lfs)
