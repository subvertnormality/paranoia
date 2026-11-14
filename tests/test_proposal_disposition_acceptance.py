"""Replay retained live evidence; historical provider exchanges remain immutable."""
import hashlib
import ast
import json
from pathlib import Path
import subprocess

import pytest

from paranoia_local import proposal_disposition as pd

ROOT = Path(__file__).resolve().parents[1]
@pytest.mark.parametrize("name,current", [
    ("proposal_disposition_acceptance_2026-10-01.json", False),
    ("proposal_disposition_acceptance_2026-10-01-integration.json", False),
    ("proposal_disposition_acceptance_2026-10-01-delivery.json", False),
    ("lfs_proposal_acceptance_2026-10-01.json", False),
    ("lfs_proposal_acceptance_2026-10-01-delivery.json", True),
])
def test_native_proposal_disposition_acceptance(name, current):
    record = json.loads((ROOT / "docs" / name).read_text(encoding="utf-8"))
    expected_kind = ("issue139-native-lfs-proposal" if name.startswith("lfs_")
                     else "issue138-native-proposal-disposition")
    assert record["kind"] == expected_kind
    assert record["outcome"] == "passed"
    revision = record["source"]["revision"]
    runner = "scripts/run_proposal_disposition_acceptance.py"
    def blob(path):
        return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)
    assert hashlib.sha256(blob(runner)).hexdigest() == record["runner_sha256"]
    for path, digest in record["source"]["files"].items():
        assert hashlib.sha256(blob(path)).hexdigest() == digest
    # Bind the critical route while preserving the trace's historical model.
    # Default/description model spelling may differ. Arbitration-only instruction
    # constants are outside this proposal route; all other prompt AST stays exact.
    # The retained run does not qualify either later change as new native evidence.
    if current:
        for path in ("handlers.py", "class_closure.py", "proposal_disposition.py", "server.py",
                     "patch_proposals.py", "engines.py", "review_census.py", "prompts.py",
                     "proposal_checkout.py"):
            relative = f"src/paranoia_local/{path}"
            source = (ROOT / relative).read_bytes()
            if path == "engines.py":
                source = source.replace(
                    b'default_model = "claude-fable-5-2"',
                    b'default_model = "claude-fable-5-1"',
                    1,
                )
            elif path == "server.py":
                source = source.replace(b"claude-fable-5-2", b"claude-fable-5-1")
            elif path == "prompts.py":
                def proposal_route_ast(raw):
                    tree = ast.parse(raw)
                    excluded = {"ARBITRATION_DISCOVERY_INSTRUCTIONS", "ARBITRATION_BINDING_INSTRUCTIONS"}
                    seen = set()
                    for node in tree.body:
                        if isinstance(node, ast.Assign) and len(node.targets) == 1:
                            target = node.targets[0]
                            if isinstance(target, ast.Name) and target.id in excluded:
                                assert isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
                                seen.add(target.id)
                                node.value = ast.Constant("arbitration-only instruction outside proposal route")
                    assert seen == excluded
                    return ast.dump(tree, include_attributes=False)
                assert proposal_route_ast(source) == proposal_route_ast(blob(relative))
                continue
            assert hashlib.sha256(source).hexdigest() == record["source"]["files"][relative]
    if name.startswith("lfs_"):
        fixture = record["lfs_fixture"]
        payload = b"inert dataset\x00\xff\n" * 16384
        assert fixture["size"] == len(payload)
        assert fixture["sha256"] == hashlib.sha256(payload).hexdigest()
        assert fixture["git_lfs_version"].startswith("git-lfs/")
        assert fixture["status"] == ""
        assert fixture["pointer"] == (
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{fixture['sha256']}\nsize {fixture['size']}\n"
        )
        assert "APPLICATION-SUITABILITY: CURRENT" in record["rounds"][0]["result"]
    rounds = record["rounds"]
    assert [r["round"] for r in rounds] == [1, 2, 3]
    receipt = rounds[0]["durable_lineage"]["proposal_receipt"]
    pd.validate_receipt(receipt)
    assert receipt["audit"] in rounds[0]["audits"]
    assert "PATCH-PROPOSAL: PROPOSED" in rounds[0]["result"]
    for round_record in rounds:
        main = [a for name, a in round_record["audits"].items() if "patch_proposal" not in name]
        assert len(main) == 1
        assert round_record["result"].endswith(main[0]["rendered_trailer"])
        assert round_record["durable_lineage"]["review_state"]["last_round"] == round_record["round"]
        assert main[0]["engine"] == "codex"
        assert main[0]["attempt_ledger"]
        assert all(a["outcome"] == "completed" for a in main[0]["attempt_ledger"])
        expected = ({"receipt": receipt, "status": "applied", "departed_targets": {}}
                    if round_record["round"] == 2 else None)
        assert main[0]["proposal_disposition"] == expected
        if expected:
            assert pd.render(expected) in round_record["result"]
        else:
            assert "PROPOSAL-DISPOSITION:" not in round_record["result"]
    assert rounds[1]["arguments"]["prior_proposal_disposition"] == {
        "proposal_audit": receipt["audit"], "status": "applied", "departed_targets": {},
    }
    assert rounds[2]["durable_lineage"]["review_state"]["phase"] == "clear"
    assert "CONVERGENCE: NOT-BLOCKED" in rounds[2]["result"]
