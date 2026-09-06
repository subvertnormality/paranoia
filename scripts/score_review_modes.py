#!/usr/bin/env python3
"""Create the blinded-result worksheet; apply explicit implementer adjudications."""
import argparse
import json
from pathlib import Path
import statistics
import sys
from benchmark_review_modes import sha, dump, validate_manifest

CATEGORIES = {"clear", "defect", "CONCEDE", "HOLD", "inclusive", "exclusive",
              "wrong_answer", "operational_failure", "unresolved", "unscored"}

def outputs(directory):
    status = json.loads((directory / "status.json").read_text())
    return status, "\n\n".join(r["result"] for r in status.get("outputs", []))

def qualify(directory, quote, reason, accepted=True):
    path = directory / "setup.json"
    setup = json.loads(path.read_text())
    if accepted and (not setup.get("session") or not setup.get("provider")
                     or not setup.get("snapshot") or not quote or quote not in setup["result"]
                     or "app.py" not in quote or not reason.strip()):
        raise ValueError("unqualified exact finding/session/snapshot")
    dump(directory / "qualification.json", {
        "accepted": accepted, "quote": quote, "reason": reason,
        "setup_sha256": sha(path.read_bytes()), "adjudicator": "implementer",
    })

def adjudicate(directory, category, quote, reason):
    status, text = outputs(directory)
    if category not in CATEGORIES or not reason.strip():
        raise ValueError("invalid adjudication")
    if category not in {"operational_failure", "unresolved", "unscored"}:
        if status["status"] != "completed" or not quote or quote not in text:
            raise ValueError("credit requires completed output and exact quotation")
    spec = json.loads((directory / "input.json").read_text())
    mode = spec["input"]["mode"]
    allowed = {"critique_branch": {"clear", "defect"}, "critique_plan": {"clear", "defect"},
               "query": {"clear", "defect"}, "rebut": {"CONCEDE", "HOLD"},
               "arbitrate": {"inclusive", "exclusive"}}
    if category not in allowed[mode] | {"wrong_answer", "operational_failure", "unresolved", "unscored"}:
        raise ValueError("category does not belong to mode")
    if category in allowed[mode]:
        if "[paranoia-local error]" in text or "STATE-UNAVAILABLE" in text or "AUDIT-FAILED" in text:
            raise ValueError("failed review cannot receive semantic credit")
        if mode in {"critique_branch", "critique_plan"}:
            states = [json.loads(p.read_text()) for p in (directory / "state/lineages").glob("*.json")]
            if len(states) != 1:
                raise ValueError("missing unique durable lineage")
            state = states[0]
            review = state.get("review_state", {})
            if review.get("validation_debt") or review.get("failure"):
                raise ValueError("failed settlement")
            if category == "clear" and (review.get("phase") != "clear" or
                                         "CONVERGENCE: NOT-BLOCKED" not in text):
                raise ValueError("pending review is not clear")
            if category == "defect" and not (
                any(d.get("status") == "open" and d.get("severity") in {"MAJOR", "CRITICAL"}
                    for d in review.get("debt", [])) or
                any(c.get("verdict") == "refuted" for c in state.get("claim_state", {}).get("claims", {}).values())
            ):
                raise ValueError("no durable blocking finding or refutation")
        if mode == "arbitrate" and (
            "ARBITRATION: CONVERGED" not in text or f"SELECTED: {category}\n" not in text + "\n"
        ):
            raise ValueError("arbitration did not select this option")
        if mode == "rebut" and category not in text:
            raise ValueError("missing explicit disposition")
    dump(directory / "score.json", {"category": category, "quote": quote, "reason": reason,
                                   "result_sha256": sha(text), "adjudicator": "implementer"})

def report(root):
    manifest = json.loads((root / "manifest.json").read_text())
    validate_manifest(manifest)
    rows = []
    for trial in manifest["order"]:
        directory = root / trial["id"]
        status, text = outputs(directory)
        score_path = directory / "score.json"
        score = json.loads(score_path.read_text()) if score_path.exists() else {"category": "unscored"}
        if score.get("result_sha256", sha(text)) != sha(text):
            raise ValueError("adjudication bound to different result")
        attempts_path = directory / "attempts.jsonl"
        attempts = [json.loads(l) for l in attempts_path.read_text().splitlines()] if attempts_path.exists() else []
        review_ms = sum(r["elapsed_ms"] for r in status.get("outputs", []))
        setup_path = directory / "setup.json"
        setup_ms = json.loads(setup_path.read_text())["elapsed_ms"] if setup_path.exists() else 0
        retries = 0
        for log in (directory / "logs").glob("*.json"):
            audit = json.loads(log.read_text())
            if audit.get("tool") == "run":
                continue
            retries += sum("validation-retry" in a.get("role", "")
                           for a in audit.get("attempt_ledger", []))
        expected = manifest["oracle"][trial["case"]]["expected"]
        category = score["category"]
        rows.append({**trial, "mode": manifest["oracle"][trial["case"]]["mode"],
                     "status": status["status"], "expected": expected, **score,
                     "correct": category == expected,
                     "review_ms": review_ms, "setup_ms": setup_ms,
                     "total_dispatch_ms": review_ms + setup_ms,
                     "calls": len(attempts), "validation_retries": retries,
                     "provider_usage": [r["provider_usage"] for r in attempts if r.get("provider_usage")],
                     "measurement_note": "dispatch wall time; excludes queue and human qualification delay"})
    summary = {}
    for version in manifest["sources"]:
        selected = [r for r in rows if r["version"] == version]
        scored = [r for r in selected if r["category"] not in {"unscored", "unresolved", "operational_failure"}]
        summary[version] = {"trials": len(selected), "correct": sum(r["correct"] for r in selected),
                            "scorable": len(scored),
                            "operational_failures": sum(r["category"] == "operational_failure" for r in selected),
                            "unresolved_or_unscored": sum(r["category"] in {"unresolved", "unscored"} for r in selected),
                            "false_clears": sum(r["expected"] == "defect" and r["category"] == "clear" for r in selected),
                            "false_positives": sum(r["expected"] == "clear" and r["category"] == "defect" for r in selected),
                            "calls": sum(r["calls"] for r in selected)}
    pairs = []
    for case in manifest["cases"]:
        for repetition in range(2):
            pair = {r["version"]: r for r in rows if r["case"] == case["id"] and r["repetition"] == repetition}
            baseline, candidate = pair["baseline"], pair["candidate"]
            comparable = baseline["correct"] and candidate["correct"]
            pairs.append({"case": case["id"], "mode": case["mode"], "repetition": repetition,
                          "both_correct": comparable,
                          "delta_ms": candidate["total_dispatch_ms"] - baseline["total_dispatch_ms"]
                              if comparable else None,
                          "delta_calls": candidate["calls"] - baseline["calls"] if comparable else None})
    dump(root / "report.json", {"summary": summary, "trials": rows, "pairs": pairs,
                               "human_acceptance": None, "dollar_cost": None,
                               "limitations": "Synthetic ten-case pilot; two repetitions; implementer adjudication, "
                               "no independent human acceptance, no population performance guarantee."})
    print(json.dumps(summary, indent=2))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--trial")
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--reject-setup", action="store_true")
    parser.add_argument("--category", choices=sorted(CATEGORIES))
    parser.add_argument("--quote", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    if args.qualify or args.reject_setup:
        qualify(args.root / args.trial, args.quote, args.reason, not args.reject_setup)
    elif args.category:
        adjudicate(args.root / args.trial, args.category, args.quote, args.reason)
    else:
        report(args.root)
if __name__ == "__main__":
    main()
