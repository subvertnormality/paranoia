#!/usr/bin/env python3
"""Oracle-bound implementer adjudication and disclosed human-rating handoff."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import statistics
import runpy

runpy.run_path(str(Path(__file__).with_name("benchmark_bootstrap.py")))
import benchmark_review_modes as shared
from benchmark_effectiveness import qualify_campaign, scoring_binding
from effectiveness_custody import read, json_digest

DISCLOSURE = (
    "Expected answers, implementer scores and experimental labels are withheld. "
    "Native review wording, diagnostics and formatting are preserved and may reveal "
    "the workflow or provider. This is not guaranteed arm/provider-blinded adjudication."
)


def governing_findings(slot):
    rows = {}
    for audit in slot["audits"]:
        for row in (audit.get("staged_settlement") or {}).get("findings", []):
            key = row["id"]
            if key in rows and rows[key] != row:
                raise ValueError("governing finding identity changed across rounds")
            rows[key] = row
    return rows


def validate_annotation(annotation, slot, oracle, arm):
    expected = {"schema", "output_digests", "coverage_attested", "verdict", "verdict_quote", "findings", "adjudicator"}
    if set(annotation) != expected or annotation["schema"] != 1 or annotation["adjudicator"] != "implementer":
        raise ValueError("closed implementer annotation required")
    if annotation["output_digests"] != [shared.sha(o["result"]) for o in slot["outputs"]]:
        raise ValueError("annotation binds different output")
    if annotation["coverage_attested"] is not True:
        raise ValueError("complete actionable-assertion coverage is not attested")
    if annotation["verdict"] not in {"clear", "defect", "unresolved", "operational_failure"}:
        raise ValueError("unknown verdict")
    if annotation["verdict"] in {"clear", "defect"} and not slot["execution_success"]:
        raise ValueError("unsuccessful execution cannot receive semantic credit")
    if annotation["verdict"] == "clear" and not slot["clear_eligible"]:
        raise ValueError("census-only or failed review cannot receive clear credit")
    quote = annotation["verdict_quote"]
    if not isinstance(quote, str) or (annotation["verdict"] in {"clear", "defect"} and
            (not quote.strip() or not any(quote in o["result"] for o in slot["outputs"]))):
        raise ValueError("semantic verdict requires an exact output quotation")
    native = governing_findings(slot) if arm == "staged" else {}
    covered, seen_ids, clusters = set(), set(), {}
    for finding in annotation["findings"]:
        required = {"id", "output", "quote", "native_id", "classification", "cluster",
                    "reason", "basis_quote", "witness_sha256", "additional_witness"}
        if set(finding) != required or type(finding["id"]) is not int or finding["id"] in seen_ids:
            raise ValueError("invalid or duplicate finding annotation")
        seen_ids.add(finding["id"])
        index = finding["output"]
        if type(index) is not int or not 0 <= index < len(slot["outputs"]):
            raise ValueError("finding output index invalid")
        if not finding["quote"] or finding["quote"] not in slot["outputs"][index]["result"]:
            raise ValueError("finding quotation not bound")
        if not isinstance(finding["reason"], str) or not finding["reason"].strip():
            raise ValueError("finding rationale required")
        kind = finding["classification"]
        if kind not in {"target", "false_positive", "advisory", "non_finding", "unscored", "fixture_problem"}:
            raise ValueError("unknown finding classification")
        if arm == "staged":
            if finding["native_id"] not in native:
                raise ValueError("annotation does not name native governing finding")
            covered.add(finding["native_id"])
            if kind in {"target", "false_positive"} and native[finding["native_id"]]["severity"] not in {"MAJOR", "BLOCKER", "FATAL"}:
                raise ValueError("advisory native finding is not a blocking detection")
        elif finding["native_id"] is not None:
            raise ValueError("query prose has no governing ID")
        if kind == "target":
            if not oracle["defective"] or finding["witness_sha256"] != json_digest(oracle["witness"]):
                raise ValueError("target does not bind defective oracle witness")
            if finding["cluster"] != "target":
                raise ValueError("one target defect has one cluster")
        elif kind == "false_positive":
            if not finding["basis_quote"] or not finding["cluster"]:
                raise ValueError("disproved assertion requires quoted counterevidence and cluster")
            if finding["basis_quote"] not in oracle["specification"]:
                raise ValueError("counterevidence is not an exact frozen specification quotation")
        if kind == "fixture_problem":
            witness = finding["additional_witness"]
            if (not isinstance(witness, dict) or set(witness) != {"code", "result"}
                    or any(not isinstance(v, str) or not v.strip() for v in witness.values())
                    or finding["witness_sha256"] != json_digest(witness)):
                raise ValueError("unexpected valid defect requires a recorded executable witness")
        elif finding["additional_witness"] is not None:
            raise ValueError("additional witness belongs to a fixture problem")
        if kind in {"target", "false_positive", "unscored", "fixture_problem"}:
            cluster = finding["cluster"]
            if not isinstance(cluster, str) or not cluster:
                raise ValueError("finding cluster required")
            if cluster in clusters and clusters[cluster] != kind:
                raise ValueError("duplicate cluster has conflicting adjudications")
            clusters[cluster] = kind
    if covered != set(native):
        raise ValueError("native governing finding annotations incomplete")
    if annotation["verdict"] == "clear" and any(v in {"target", "false_positive"} for v in clusters.values()):
        raise ValueError("clear conflicts with blocking assertion")
    unresolved = any(v in {"unscored", "fixture_problem"} for v in clusters.values())
    return {"tp": int("target" in clusters), "fp": sum(v == "false_positive" for v in clusters.values()),
            "unscored": unresolved, "verdict": annotation["verdict"], "clusters": clusters}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def stage_usage(slot):
    roles = {}
    for audit in slot["audits"]:
        for row in audit.get("attempt_ledger", []):
            roles[(row.get("session_ref"), row.get("raw_sha256"))] = row.get("role")
    result = {}
    for row in slot["attempts"]:
        role = roles.get((row.get("session_ref"), row.get("raw_sha256")), row.get("role") or "unmapped")
        group = result.setdefault(role, {"calls": 0, "provider_call_ms": 0, "usage": []})
        group["calls"] += 1
        group["provider_call_ms"] += row["elapsed_ms"]
        group["usage"].extend(row.get("provider_usage", []))
    return result


def report(root):
    q = qualify_campaign(root)
    if q["manifest"] is None:
        result = {"custody_qualified": False, "comparative_qualified": False,
                  "custody_errors": q["errors"], "calls": q["calls"], "summary": {},
                  "observed_superiority_criteria_met": False, "human_acceptance": "pending"}
        shared.dump(root / "report.json", result)
        return result
    manifest, oracle = q["manifest"], read(root / "oracle.json")
    rows, annotation_errors = [], []
    for trial in manifest["order"]:
        slot = q["slots"][trial["id"]]
        score = {"tp": 0, "fp": 0, "unscored": True, "verdict": "unscored"}
        try:
            annotation = read(root / trial["id"] / "score.json")
            score = validate_annotation(annotation, slot, oracle[trial["case"]], trial["arm"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            annotation_errors.append(trial["id"] + ": " + str(exc))
        rows.append({**trial, **score, "defective": oracle[trial["case"]]["defective"],
                     "execution_success": slot["execution_success"], "custody_errors": slot["errors"],
                     "elapsed_ms": slot["elapsed_ms"], "calls": slot["calls"],
                     "dispatch_ms": slot["dispatch_ms"],
                     "stage_usage": stage_usage(slot),
                     "retries": sum("validation-retry" in a.get("role", "") for audit in slot["audits"]
                                    for a in audit.get("attempt_ledger", []))})
    summary = {}
    for arm in ("single", "staged"):
        group = [r for r in rows if r["arm"] == arm]
        tp, fp = sum(r["tp"] for r in group), sum(r["fp"] for r in group)
        defects = sum(r["defective"] for r in group)
        false_clears = sum(r["defective"] and r["verdict"] == "clear" for r in group)
        false_positives = sum(not r["defective"] and r["verdict"] == "defect" for r in group)
        summary[arm] = {
            "scheduled": len(group), "defective": defects, "target_detections": tp,
            "finding_precision": ratio(tp, tp + fp), "target_recall": ratio(tp, defects),
            "false_clears": false_clears, "false_clear_rate": ratio(false_clears, defects),
            "false_positives": false_positives, "false_positive_rate": ratio(false_positives, len(group)-defects),
            "unsupported_finding_clusters": fp,
            "unscored_slots": sum(r["unscored"] for r in group),
            "operational_or_unresolved": sum(r["verdict"] in {"operational_failure", "unresolved", "unscored"} for r in group),
            "calls": sum(r["calls"] for r in group), "total_slot_ms": sum(r["elapsed_ms"] for r in group),
            "total_dispatch_ms": sum(r["dispatch_ms"] for r in group),
            "min_ms": min(r["elapsed_ms"] for r in group), "median_ms": statistics.median(r["elapsed_ms"] for r in group),
            "max_ms": max(r["elapsed_ms"] for r in group),
        }
    pairs = []
    for case in manifest["cases"]:
        for repetition in range(2):
            selected = {r["arm"]: r for r in rows if r["case"] == case["id"] and r["repetition"] == repetition}
            a, b = selected["single"], selected["staged"]
            comparable = all(r["execution_success"] and not r["unscored"] for r in (a, b))
            pairs.append({"case": case["id"], "repetition": repetition, "comparable": comparable,
                          "delta_ms": b["elapsed_ms"] - a["elapsed_ms"] if comparable else None,
                          "delta_dispatch_ms": b["dispatch_ms"] - a["dispatch_ms"] if comparable else None,
                          "delta_calls": b["calls"] - a["calls"],
                          "delta_detections": b["tp"] - a["tp"]})
    sealed = (root / "scoring-receipt.json").exists()
    comparative = q["qualified"] and sealed and not annotation_errors and not any(r["unscored"] for r in rows)
    a, b = summary["single"], summary["staged"]
    superiority = comparative and b["false_clears"] == 0 and all(
        a[k] is not None and b[k] is not None and b[k] >= a[k] for k in ("finding_precision", "target_recall")
    ) and b["target_detections"] > a["target_detections"]
    result = {"custody_qualified": q["qualified"], "custody_errors": q["errors"],
              "comparative_qualified": comparative, "annotation_errors": annotation_errors,
              "observed_superiority_criteria_met": superiority, "calls": q["calls"],
              "summary": summary, "trials": rows, "pairs": pairs,
              "human_acceptance": "pending", "scoring_sealed": sealed, "subscription_dollar_cost": None,
              "limitations": [
                  "Eight scoped fixtures, including extracted public defects; not a population or all-mode evaluation.",
                  "Implementer adjudication is not independent human acceptance.",
                  "Two repetitions provide descriptive ranges, not useful population non-inferiority bounds.",
                  "Provider-call stage durations overlap; dispatch wall time is measured separately.",
                  "Undefined zero-denominator metrics are null; failures remain in scheduled denominators.",
                  "No inference about token usage translating to subscription dollar charges.",
              ]}
    shared.dump(root / "report.json", result)
    return result


def seal_scores(root):
    q = qualify_campaign(root)
    if not q["qualified"]:
        raise ValueError("custody must qualify before adjudication is sealed")
    oracle = read(root / "oracle.json")
    for row in q["manifest"]["order"]:
        validate_annotation(read(root / row["id"] / "score.json"),
                            q["slots"][row["id"]], oracle[row["case"]], row["arm"])
    path = root / "scoring-receipt.json"
    if path.exists():
        raise ValueError("scoring is already sealed")
    shared.dump(path, scoring_binding(root, q["manifest"]))


def strip_native_footer(text, audit):
    engine, session = audit["engine"], audit.get("session_ref")
    footer = (f"\n\n---\n_paranoia-local · engine={engine} · session_ref=\u0060{session}\u0060 — "
              "to dispute a finding, call \u0060rebut\u0060 with this session_ref and your counter-evidence._") if session else (
                  f"\n\n---\n_paranoia-local · engine={engine}_")
    if text.count(footer) != 1:
        raise ValueError("missing or ambiguous exact native footer")
    return text.replace(footer, "", 1)


def human_projection(q):
    """Pure exact-text projection; validation regenerates it from qualified custody."""
    if not q["qualified"]:
        raise ValueError("custody must qualify before human export")
    order = list(q["manifest"]["order"])
    random.Random(json_digest(q["manifest"])).shuffle(order)
    items, mapping = [], {}
    for index, row in enumerate(order, 1):
        slot = q["slots"][row["id"]]
        reviews = []
        for output in slot["outputs"]:
            native = [a for a in slot["audits"] if a.get("run_id") == output["run_id"]]
            if not native and output["result"].startswith("[paranoia-local error]"):
                reviews.append(output["result"])
            elif len(native) != 1:
                raise ValueError("human item lacks unique native source")
            else:
                reviews.append(strip_native_footer(output["result"], native[0]))
        if not reviews:
            reviews.append("Review did not produce an output. " + (slot["terminal"].get("error") or "No diagnostic was recorded."))
        case = next(c for c in q["manifest"]["cases"] if c["id"] == row["case"])
        body = {"files": case["files"], "reviews": reviews}
        item = {"id": f"item-{index:02}", "content_sha256": json_digest(body), **body}
        items.append(item)
        mapping[item["id"]] = {"slot": row["id"], "output_digests": [shared.sha(o["result"]) for o in slot["outputs"]]}
    packet = {"schema": 1, "disclosure": DISCLOSURE,
              "task": "For every item rate accuracy and actionability: accept, reject, or uncertain; give a reason and identify any incorrect assertion.",
              "items": items}
    return packet, mapping


def export_human(root):
    packet, mapping = human_projection(qualify_campaign(root))
    shared.dump(root / "human-packet.json", packet)
    shared.dump(root / "human-private-map.json", mapping)
    shared.dump(root / "human-ratings-template.json", {
        "packet_sha256": shared.sha((root / "human-packet.json").read_bytes()),
        "ratings": [{"id": item["id"], "rating": None, "reason": ""} for item in packet["items"]],
    })
    return packet


def validate_ratings(root, ratings):
    packet = read(root / "human-packet.json")
    expected_packet, expected_mapping = human_projection(qualify_campaign(root))
    if packet != expected_packet or read(root / "human-private-map.json") != expected_mapping:
        raise ValueError("human projection differs from qualified custody")
    if set(ratings) != {"packet_sha256", "ratings"} or not isinstance(ratings["ratings"], list):
        raise ValueError("closed ratings record required")
    if packet.get("disclosure") != DISCLOSURE:
        raise ValueError("missing human packet disclosure")
    if ratings.get("packet_sha256") != shared.sha((root / "human-packet.json").read_bytes()):
        raise ValueError("ratings bind stale packet")
    expected = {item["id"] for item in packet["items"]}
    rows = ratings.get("ratings", [])
    if any(not isinstance(r, dict) or set(r) != {"id", "rating", "reason"}
           or not isinstance(r["reason"], str) for r in rows):
        raise ValueError("closed human rating required")
    if Counter(r["id"] for r in rows) != Counter(expected):
        raise ValueError("missing or duplicate human ratings")
    if any(r.get("rating") not in {"accept", "reject", "uncertain"} or not r.get("reason", "").strip() for r in rows):
        return {"status": "pending", "reason": "Every item requires a rating and reason."}
    counts = Counter(r["rating"] for r in rows)
    result = report(root)
    mapping = read(root / "human-private-map.json")
    scored = {r["id"]: r for r in result["trials"]}
    false_clear_accepted = any(
        r["rating"] == "accept" and scored[mapping[r["id"]]["slot"]]["defective"]
        and scored[mapping[r["id"]]["slot"]]["verdict"] == "clear" for r in rows
    )
    accepted = counts["accept"] / len(rows) >= .9 and not false_clear_accepted and result["comparative_qualified"]
    return {"status": "accepted" if accepted else "rejected", "counts": dict(counts),
            "acceptance_rate": counts["accept"] / len(rows), "accepted_false_clear": false_clear_accepted,
            "packet_sha256": ratings["packet_sha256"], "ratings_sha256": json_digest(ratings)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--human", action="store_true")
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    if args.seal:
        seal_scores(args.root)
    elif args.human:
        export_human(args.root)
    elif args.ratings:
        result = validate_ratings(args.root, read(args.ratings))
        shared.dump(args.root / "human-acceptance.json", result)
        print(json.dumps(result))
    else:
        result = report(args.root)
        print(json.dumps({k: result[k] for k in ("custody_qualified", "comparative_qualified", "summary")}))


if __name__ == "__main__":
    main()
