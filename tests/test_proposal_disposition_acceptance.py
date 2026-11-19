"""Replay retained live evidence; historical provider exchanges remain immutable."""
import hashlib
import ast
import json
from pathlib import Path
import subprocess

import pytest

from paranoia_local import proposal_disposition as pd

ROOT = Path(__file__).resolve().parents[1]


# The issue 139 receipt exercised branch proposals. These top-level nodes belong
# exclusively to plan claim verification and its verified-plan timing envelope.
_PLAN_CLAIM_NODES = {
    "critique_plan", "_verify_plan_claims", "_CapturedClaimEngine", "_EvidencePhaseReview",
    "_plan_evidence_batch_limit", "_plan_capture_reserve",
    "PLAN_SOURCES_PER_CAPTURE_RESERVE", "MIN_PLAN_EVIDENCE_BATCHES",
    "PLAN_CLAIMS_PER_EVIDENCE_BATCH", "PLAN_EVIDENCE_VALIDATION_CORRECTIONS",
    "MAX_PLAN_CAPTURE_SOURCES", "MAX_PLAN_BINDING_BATCHES", "MAX_PLAN_ATTESTATION_BATCHES",
    "MAX_PLAN_EVIDENCE_MODEL_CALLS", "PLAN_EVIDENCE_MAX_NON_MODEL_RESERVE_SEC",
    "PLAN_EVIDENCE_REQUIRED_WORK_SEC", "PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC",
    "PLAN_REVIEW_CLIENT_MARGIN_SEC", "PLAN_REVIEW_CLIENT_TIMEOUT_SEC",
}


def _branch_proposal_handler_ast(raw):
    tree = ast.parse(raw)
    kept = []
    for node in tree.body:
        name = None
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                name = target.id
        if name not in _PLAN_CLAIM_NODES:
            kept.append(node)
    tree.body = kept
    return ast.dump(tree, include_attributes=False)


def _historical_codex_no_web_source(source):
    text = source.decode("utf-8")
    classes = [node for node in ast.parse(text).body
               if isinstance(node, ast.ClassDef) and node.name == "CodexEngine"]
    assert len(classes) == 1
    names = {"build_argv", "build_resume_argv"}
    methods = [node for node in classes[0].body
               if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(methods) == 2 and {node.name for node in methods} == names
    segments = {node.name: ast.get_source_segment(text, node) for node in methods}
    disabled = '        else:\n            argv += ["-c", \'web_search="disabled"\']\n'
    for name, segment in segments.items():
        suffix = '        argv.append("-")'
        if name == "build_argv":
            suffix += '  # read prompt from stdin'
        current = ('        if web_search:\n'
                   '            argv += ["-c", "tools.web_search=true"]\n'
                   + disabled + suffix)
        assert segment.count(current) == 1, name
        assert text.count(segment) == 1, name
        historical = segment.replace(current, current.replace(disabled, "", 1), 1)
        text = text.replace(segment, historical, 1)
    return text.encode("utf-8")


@pytest.mark.parametrize("name", ["build_argv", "build_resume_argv"])
def test_no_web_history_projection_rejects_relocated_branch(name):
    source = (ROOT / "src/paranoia_local/engines.py").read_text()
    cls = next(node for node in ast.parse(source).body
               if isinstance(node, ast.ClassDef) and node.name == "CodexEngine")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    segment = ast.get_source_segment(source, method)
    disabled = '        else:\n            argv += ["-c", \'web_search="disabled"\']\n'
    assert segment.count(disabled) == 1
    moved = segment.replace(disabled, "", 1).replace('        argv = [', disabled + '        argv = [', 1)
    with pytest.raises(AssertionError):
        _historical_codex_no_web_source(source.replace(segment, moved, 1).encode("utf-8"))

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
    # Default/description model spelling and exact no-web flag additions may differ.
    # Reversals bind each original command builder. Arbitration-only instruction
    # constants are outside this proposal route; all other prompt AST stays exact.
    # The retained run does not qualify these later changes as new native evidence.
    if current:
        for path in ("handlers.py", "class_closure.py", "proposal_disposition.py", "server.py",
                     "patch_proposals.py", "engines.py", "review_census.py", "prompts.py",
                     "proposal_checkout.py"):
            relative = f"src/paranoia_local/{path}"
            source = (ROOT / relative).read_bytes()
            if path == "handlers.py":
                assert _branch_proposal_handler_ast(source) == _branch_proposal_handler_ast(blob(relative))
                continue
            if path == "engines.py":
                source = source.replace(
                    b'default_model = "claude-fable-5-2"',
                    b'default_model = "claude-fable-5-1"',
                    1,
                )
                source = source.replace(
                    b'default_model = "gpt-6.2-astra"',
                    b'default_model = "gpt-6-astra"',
                    1,
                ).replace(b'ATTESTER_MODEL = "gpt-6.2-astra"', b'ATTESTER_MODEL = "gpt-6-astra"', 1)
                source = source.replace(b'correction_model = "gpt-6.2-sol"', b'correction_model = "gpt-6.1-sol"', 1)
                source = _historical_codex_no_web_source(source)
            elif path == "server.py":
                source = source.replace(b"claude-fable-5-2", b"claude-fable-5-1")
                source = source.replace(b"gpt-6.2-astra", b"gpt-6-astra")
                source = source.replace(b"gpt-6.2-sol", b"gpt-6.1-sol")
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
