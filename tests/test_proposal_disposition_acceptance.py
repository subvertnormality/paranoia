"""Replay retained live evidence; historical provider exchanges remain immutable."""
import hashlib
import json
from pathlib import Path
import subprocess

from paranoia_local import proposal_disposition as pd

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs/proposal_disposition_acceptance_2026-10-01.json"


def test_native_proposal_disposition_acceptance():
    record = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert record["kind"] == "issue138-native-proposal-disposition"
    assert record["outcome"] == "passed"
    revision = record["source"]["revision"]
    runner = "scripts/run_proposal_disposition_acceptance.py"
    def blob(path):
        return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)
    assert hashlib.sha256(blob(runner)).hexdigest() == record["runner_sha256"]
    for path, digest in record["source"]["files"].items():
        assert hashlib.sha256(blob(path)).hexdigest() == digest
    # This retained acceptance applies to the current critical production route,
    # not a blanket claim that historical evidence exercises later changed bytes.
    for path in ("handlers.py", "class_closure.py", "proposal_disposition.py", "server.py",
                 "patch_proposals.py", "engines.py", "review_census.py"):
        relative = f"src/paranoia_local/{path}"
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == record["source"]["files"][relative]
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
