#!/usr/bin/env python3
"""Run the bounded live provider gate for keyed staged class decisions."""

from __future__ import annotations

import hashlib
import json
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import staged_protocol as sp
from paranoia_local.engines import ClaudeEngine, CodexEngine

OUTPUT = ROOT / "docs" / "keyed_class_decision_provider_acceptance_2026-08-19.json"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def historical_issue_98_schema(
    schema: dict, *, role: str, outcome_ids: list[str],
) -> dict:
    """Project the current schema to the exact pre-#98 provider surface."""
    value = json.loads(json.dumps(schema))
    if role != "correction":
        return value
    outcomes = value["properties"]["class_outcomes"]
    outcomes["properties"] = {
        class_id:outcomes["properties"][class_id] for class_id in outcome_ids
    }
    return value


def active_class(index: int) -> dict:
    mechanized = index % 2 == 0
    return {
        "class_id":f"{index:08x}", "invariant":f"invariant {index}",
        "severity":"MAJOR", "status":cc.CLOSED, "mechanized":mechanized,
        "pattern":"BROKEN" if mechanized else None,
        "pathspec":"*.py" if mechanized else None,
        "procedure":None if mechanized else "inspect the affected path",
    }


def citation() -> dict:
    return {"anchor":"plan:1", "rationale":"the fixture establishes this judgement"}


def concessions(classes: list[dict]) -> dict:
    return {
        cls["class_id"]:{
            "debt_id":f"C-{cls['class_id']}", "finding_id":f"F-{cls['class_id']}",
            "summary":"historic conceded occurrence", "remedy":"do not repeat it",
            "finding_evidence":["plan:1"],
            "concession":{
                "version":1, "reason":"the prior demand was disproved",
                "evidence":["plan:1"], "snapshot_digest":"a" * 64, "round":1,
            },
        }
        for cls in classes
    }


def fixtures() -> list[dict]:
    minimal_classes = [active_class(0)]
    minimal = {
        "role":"correction", "governing_findings":[], "debt_outcomes":[],
        "class_outcomes":{}, "class_actions":{"00000000":None},
        "concession_challenges":{"00000000":None},
    }
    maximum_classes = [active_class(index) for index in range(sp.MAX_ACTIVE_CLASSES)]
    populated_classes = [active_class(1), active_class(3)]
    populated_debt = [{
        "id":"D1", "finding_id":"historic", "status":"open",
        "severity":"MAJOR", "summary":"historic occurrence",
        "evidence":["plan:1"], "remedy":"repair it", "source_ids":[],
        "class_ids":["00000001"], "first_round":1, "last_round":1,
    }]
    populated = {
        "role":"correction",
        "governing_findings":[{
            "id":"fresh", "severity":"MINOR", "summary":"new occurrence",
            "evidence":[citation()], "remedy":"repair the occurrence",
            "classification":{
                "kind":"existing_class", "class_id":"00000003",
                "assessment_evidence":[citation()],
            },
        }],
        "debt_outcomes":[{
            "debt_id":"D1", "status":"open", "evidence":[citation()],
            "reason":"the historic occurrence remains reachable",
        }],
        "class_outcomes":{
            "00000001":{
                "verdict":"violated", "evidence":[citation()],
                "basis":{"kind":"carried_debt", "debt_id":"D1"},
            },
        },
        "class_actions":{"00000001":None, "00000003":None},
        "concession_challenges":{},
    }
    maximum = {
        "role":"final", "governing_findings":[], "debt_outcomes":[],
        "class_outcomes":{
            cls["class_id"]:{
                "verdict":"satisfied", "evidence":[citation()],
            }
            for cls in maximum_classes
        },
        "class_actions":{cls["class_id"]:None for cls in maximum_classes},
        "concession_challenges":{
            cls["class_id"]:None for cls in maximum_classes
        },
        "coverage":[
            {
                "id":item, "status":"covered", "summary":"checked",
                "evidence":[citation()], "finding_ids":[],
            }
            for item in sp.CHECKLIST
        ],
    }
    census_classes = [active_class(1), active_class(3)]
    census = {
        "role":"census", "governing_findings":[], "debt_outcomes":[],
        "class_actions":{"00000001":None, "00000003":None},
        "concession_challenges":{},
    }
    census_kwargs = {
        "assessment_verdicts":{"00000001":"satisfied", "00000003":"satisfied"},
        "assessment_findings":{"00000001":None, "00000003":None},
        "assessment_evidence":{"00000001":["plan:1"], "00000003":["plan:1"]},
    }
    return [
        {"shape":"minimal-correction", "role":"correction",
         "classes":minimal_classes, "durable_debt":[],
         "prior_concessions":concessions(minimal_classes), "response":minimal},
        {"shape":"populated-correction", "role":"correction",
         "classes":populated_classes, "durable_debt":populated_debt,
         "response":populated},
        {"shape":"maximum-final", "role":"final",
         "classes":maximum_classes, "durable_debt":[],
         "prior_concessions":concessions(maximum_classes), "response":maximum},
        {"shape":"representative-census", "role":"census",
         "classes":census_classes, "durable_debt":[], "response":census,
         "materialize_kwargs":census_kwargs},
    ]


def validate_artifact(artifact: dict) -> None:
    """Fail closed before publishing a complete or partially refreshed artifact."""
    if artifact.get("acceptance_kind") != (
        "keyed-staged-class-decision-provider-capability"
    ) or artifact.get("version") != 1:
        raise RuntimeError("provider acceptance identity is invalid")
    if artifact.get("max_active_classes") != sp.MAX_ACTIVE_CLASSES:
        raise RuntimeError("provider acceptance active-class bound is stale")
    expected_fixtures = {row["shape"]:row for row in fixtures()}
    providers = artifact.get("providers")
    if not isinstance(providers, list) or {
        row.get("engine") for row in providers
    } != {"codex", "claude"}:
        raise RuntimeError("provider acceptance route inventory is invalid")
    counted = 0
    for provider in providers:
        probes = provider.get("probes")
        if not isinstance(probes, list) or {
            row.get("shape") for row in probes
        } != set(expected_fixtures):
            raise RuntimeError("provider acceptance probe inventory is invalid")
        for probe in probes:
            fixture = expected_fixtures[probe["shape"]]
            classes = probe.get("active_classes")
            durable_debt = probe.get("durable_debt")
            prior_concessions = probe.get("prior_concessions", {})
            role = probe.get("role")
            if (
                classes != fixture["classes"]
                or durable_debt != fixture["durable_debt"]
                or prior_concessions != fixture.get("prior_concessions", {})
                or role != fixture["role"]
            ):
                raise RuntimeError("provider acceptance probe authority is inconsistent")
            outcome_ids = sp.expected_outcome_class_ids(
                role, active_classes=classes, durable_debt=durable_debt,
            )
            schema = sp.provider_schema(sp.decision_schema(
                cc.BRANCH_MODE, role, active_classes=classes,
                outcome_class_ids=outcome_ids,
                prior_concessions=prior_concessions,
            ))
            historical_schema = historical_issue_98_schema(
                schema, role=role, outcome_ids=outcome_ids,
            )
            schema_text = sp.canonical_schema(historical_schema)
            if (
                probe.get("active_class_count") != len(classes)
                or probe.get("required_outcome_count") != len(outcome_ids)
                or probe.get("schema_bytes") != len(schema_text.encode("utf-8"))
                or probe.get("schema_sha256") != digest(schema_text)
            ):
                raise RuntimeError("provider acceptance probe metadata is inconsistent")
            calls = probe.get("calls")
            if not isinstance(calls, list) or [
                row.get("route") for row in calls
            ] != ["fresh", "resumed"] or len({
                row.get("session_ref") for row in calls
            }) != 1:
                raise RuntimeError("provider acceptance call topology is invalid")
            for call in calls:
                text = call.get("response_text")
                if not isinstance(text, str) or digest(text) != call.get("response_sha256"):
                    raise RuntimeError("provider acceptance response binding is invalid")
                decoded = sp.decode_decision(
                    text, mode=cc.BRANCH_MODE, role=role,
                    active_classes=classes, durable_debt=durable_debt,
                    prior_concessions=prior_concessions,
                )
                sp.materialize_decision_value(
                    decoded, mode=cc.BRANCH_MODE, role=role,
                    active_classes=classes, durable_debt=durable_debt,
                    prior_concessions=prior_concessions,
                    **probe.get("materialize_kwargs", {}),
                )
            counted += len(calls)
    if artifact.get("call_count") != counted:
        raise RuntimeError("provider acceptance aggregate call count is invalid")


def version(binary: str) -> str:
    return subprocess.run(
        [binary, "--version"], capture_output=True, text=True, check=True,
    ).stdout.strip()


def main() -> int:
    providers = [
        (CodexEngine(), "gpt-5.6-sol"),
        (ClaudeEngine(), "sonnet"),
    ]
    artifact = {
        "acceptance_kind":"keyed-staged-class-decision-provider-capability",
        "version":1, "date":"2026-08-19", "max_active_classes":sp.MAX_ACTIVE_CLASSES,
        "providers":[],
    }
    started = time.monotonic()
    for engine, model in providers:
        provider = {
            "engine":engine.name, "cli_version":version(engine.binary),
            "model":model, "effort":"high", "web_search":False, "probes":[],
        }
        for fixture in fixtures():
            classes = fixture["classes"]
            durable_debt = fixture["durable_debt"]
            role = fixture["role"]
            prior_concessions = fixture.get("prior_concessions", {})
            outcome_ids = sp.expected_outcome_class_ids(
                role, active_classes=classes, durable_debt=durable_debt,
            )
            schema = sp.provider_schema(sp.decision_schema(
                cc.BRANCH_MODE, role, active_classes=classes,
                outcome_class_ids=outcome_ids,
                prior_concessions=prior_concessions,
            ))
            schema_text = sp.canonical_schema(schema)
            prompt = (
                "This is a structured-output transport probe. Return a correction with "
                "no findings, debt outcomes, or class outcomes, and a null action for "
                "the sole class."
                if fixture["shape"] == "minimal-correction" else
                "This is a structured-output transport probe. Return exactly this "
                "populated correction object: " + json.dumps(
                    fixture["response"], ensure_ascii=False, separators=(",", ":"),
                )
                if fixture["shape"] == "populated-correction" else
                "This is a structured-output transport probe. Return exactly this "
                "census object: " + json.dumps(
                    fixture["response"], ensure_ascii=False, separators=(",", ":"),
                )
                if fixture["shape"] == "representative-census" else
                "This is a structured-output transport probe. Assess every class "
                "satisfied using plan:1 evidence, use null for every action slot, and "
                "mark each of these checklist IDs covered with no findings: "
                + json.dumps(list(sp.CHECKLIST), separators=(",", ":"))
            )
            calls = []
            session = None
            for route in ("fresh", "resumed"):
                call_started = time.monotonic()
                review = (
                    engine.run(
                        prompt, ROOT, model, "high", False, timeout=600,
                        response_schema=schema,
                    )
                    if route == "fresh" else engine.resume(
                        session, prompt, ROOT, model, "high", False, timeout=600,
                        response_schema=schema,
                    )
                )
                elapsed = time.monotonic() - call_started
                if review.error:
                    raise RuntimeError(
                        f"{engine.name} {fixture['shape']} {route}: "
                        f"{review.failure_detail or review.text}"
                    )
                json.loads(review.text)
                decoded = sp.decode_decision(
                    review.text, mode=cc.BRANCH_MODE, role=role,
                    active_classes=classes, durable_debt=durable_debt,
                    prior_concessions=prior_concessions,
                )
                sp.materialize_decision_value(
                    decoded, mode=cc.BRANCH_MODE, role=role,
                    active_classes=classes, durable_debt=durable_debt,
                    prior_concessions=prior_concessions,
                    **fixture.get("materialize_kwargs", {}),
                )
                session = review.session_ref
                if not session:
                    raise RuntimeError(f"{engine.name} {route}: missing session reference")
                calls.append({
                    "route":route, "session_ref":session,
                    "elapsed_seconds":round(elapsed, 3),
                    "response_sha256":digest(review.text),
                    "raw_sha256":digest(review.raw), "usage":review.usage,
                    "response_text":review.text,
                })
            provider["probes"].append({
                "shape":fixture["shape"], "role":role,
                "active_class_count":len(classes),
                "active_classes":classes,
                "required_outcome_count":len(outcome_ids),
                "durable_debt":durable_debt,
                "prior_concessions":prior_concessions,
                "materialize_kwargs":fixture.get("materialize_kwargs", {}),
                "schema_bytes":len(schema_text.encode("utf-8")),
                "schema_sha256":digest(schema_text),
                "calls":calls,
            })
        artifact["providers"].append(provider)
    artifact["call_count"] = sum(
        len(probe["calls"])
        for provider in artifact["providers"] for probe in provider["probes"]
    )
    artifact["elapsed_seconds"] = round(time.monotonic() - started, 3)
    validate_artifact(artifact)
    OUTPUT.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT} with {artifact['call_count']} successful calls")
    return 0


def repair_claude_maximum() -> int:
    """Replace only the intermittent Claude maximum pair in a successful artifact."""
    artifact = json.loads(OUTPUT.read_text(encoding="utf-8"))
    for provider in artifact["providers"]:
        for probe in provider["probes"]:
            for call in probe["calls"]:
                if "response_text" in call:
                    continue
                candidate = json.dumps(
                    call["response"], ensure_ascii=False, separators=(",", ":"),
                )
                if digest(candidate) == call["response_sha256"]:
                    call["response_text"] = candidate
                    del call["response"]
    provider = next(
        row for row in artifact["providers"] if row["engine"] == "claude"
    )
    probe = next(
        row for row in provider["probes"] if row["shape"] == "maximum-final"
    )
    fixture = next(row for row in fixtures() if row["shape"] == "maximum-final")
    classes = fixture["classes"]
    durable_debt = fixture["durable_debt"]
    prior_concessions = fixture.get("prior_concessions", {})
    role = fixture["role"]
    outcome_ids = sp.expected_outcome_class_ids(
        role, active_classes=classes, durable_debt=durable_debt,
    )
    schema = sp.provider_schema(sp.decision_schema(
        cc.BRANCH_MODE, role, active_classes=classes,
        outcome_class_ids=outcome_ids,
        prior_concessions=prior_concessions,
    ))
    prompt = (
        "This is a structured-output transport probe. Assess every class satisfied "
        "using plan:1 evidence, use null for every action slot, and mark each of "
        "these checklist IDs covered with no findings: "
        + json.dumps(list(sp.CHECKLIST), separators=(",", ":"))
    )
    engine = ClaudeEngine()
    calls = []
    session = None
    for route in ("fresh", "resumed"):
        started = time.monotonic()
        review = (
            engine.run(
                prompt, ROOT, "sonnet", "high", False, timeout=600,
                response_schema=schema,
            )
            if route == "fresh" else engine.resume(
                session, prompt, ROOT, "sonnet", "high", False, timeout=600,
                response_schema=schema,
            )
        )
        if review.error:
            raise RuntimeError(
                f"claude maximum-final {route}: {review.failure_detail or review.text}"
            )
        decoded = sp.decode_decision(
            review.text, mode=cc.BRANCH_MODE, role=role, active_classes=classes,
            durable_debt=durable_debt, prior_concessions=prior_concessions,
        )
        sp.materialize_decision_value(
            decoded, mode=cc.BRANCH_MODE, role=role, active_classes=classes,
            durable_debt=durable_debt, prior_concessions=prior_concessions,
        )
        session = review.session_ref
        if not session:
            raise RuntimeError(f"claude maximum-final {route}: missing session")
        calls.append({
            "route":route, "session_ref":session,
            "elapsed_seconds":round(time.monotonic() - started, 3),
            "response_sha256":digest(review.text), "raw_sha256":digest(review.raw),
            "usage":review.usage, "response_text":review.text,
        })
    probe["calls"] = calls
    probe.update(
        active_class_count=len(classes), active_classes=classes,
        required_outcome_count=len(outcome_ids), durable_debt=durable_debt,
        prior_concessions=prior_concessions,
        materialize_kwargs=fixture.get("materialize_kwargs", {}),
        schema_bytes=len(sp.canonical_schema(schema).encode("utf-8")),
        schema_sha256=digest(sp.canonical_schema(schema)),
    )
    if any(
        "response_text" not in call
        for item in artifact["providers"] for row in item["probes"]
        for call in row["calls"]
    ):
        raise RuntimeError("retained response could not be reconstructed exactly")
    artifact["elapsed_seconds"] = round(sum(
        call["elapsed_seconds"] for item in artifact["providers"]
        for row in item["probes"] for call in row["calls"]
    ), 3)
    validate_artifact(artifact)
    OUTPUT.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"repaired {OUTPUT} with an exact Claude maximum pair")
    return 0


def add_shape(shape: str) -> int:
    """Add one exact role shape without rerunning retained probes."""
    artifact = json.loads(OUTPUT.read_text(encoding="utf-8"))
    fixture = next(row for row in fixtures() if row["shape"] == shape)
    classes = fixture["classes"]
    durable_debt = fixture["durable_debt"]
    role = fixture["role"]
    prior_concessions = fixture.get("prior_concessions", {})
    outcome_ids = sp.expected_outcome_class_ids(
        role, active_classes=classes, durable_debt=durable_debt,
    )
    schema = sp.provider_schema(sp.decision_schema(
        cc.BRANCH_MODE, role, active_classes=classes,
        outcome_class_ids=outcome_ids,
        prior_concessions=prior_concessions,
    ))
    schema_text = sp.canonical_schema(schema)
    prompt = (
        "This is a structured-output transport probe. Return exactly this "
        f"{role} object: " + json.dumps(
            fixture["response"], ensure_ascii=False, separators=(",", ":"),
        )
    )
    for provider in artifact["providers"]:
        engine = CodexEngine() if provider["engine"] == "codex" else ClaudeEngine()
        calls = []
        session = None
        for route in ("fresh", "resumed"):
            started = time.monotonic()
            review = (
                engine.run(
                    prompt, ROOT, provider["model"], "high", False, timeout=600,
                    response_schema=schema,
                )
                if route == "fresh" else engine.resume(
                    session, prompt, ROOT, provider["model"], "high", False,
                    timeout=600, response_schema=schema,
                )
            )
            if review.error:
                raise RuntimeError(
                    f"{provider['engine']} {shape} {route}: "
                    f"{review.failure_detail or review.text}"
                )
            decoded = sp.decode_decision(
                review.text, mode=cc.BRANCH_MODE, role=role,
                active_classes=classes, durable_debt=durable_debt,
                prior_concessions=prior_concessions,
            )
            sp.materialize_decision_value(
                decoded, mode=cc.BRANCH_MODE, role=role,
                active_classes=classes, durable_debt=durable_debt,
                prior_concessions=prior_concessions,
                **fixture.get("materialize_kwargs", {}),
            )
            session = review.session_ref
            if not session:
                raise RuntimeError(f"{provider['engine']} {route}: missing session")
            calls.append({
                "route":route, "session_ref":session,
                "elapsed_seconds":round(time.monotonic() - started, 3),
                "response_sha256":digest(review.text), "raw_sha256":digest(review.raw),
                "usage":review.usage, "response_text":review.text,
            })
        probe = {
            "shape":shape, "role":role,
            "active_class_count":len(classes),
            "active_classes":classes,
            "required_outcome_count":len(outcome_ids),
            "durable_debt":durable_debt,
            "prior_concessions":prior_concessions,
            "materialize_kwargs":fixture.get("materialize_kwargs", {}),
            "schema_bytes":len(schema_text.encode("utf-8")),
            "schema_sha256":digest(schema_text), "calls":calls,
        }
        provider["probes"] = [
            row for row in provider["probes"]
            if row["shape"] != shape
        ]
        provider["probes"].insert(-1, probe)
        for row in provider["probes"]:
            row.setdefault("durable_debt", [])
            if "active_classes" not in row:
                row["active_classes"] = (
                    [active_class(0)] if row["shape"] == "minimal-correction"
                    else [active_class(index) for index in range(sp.MAX_ACTIVE_CLASSES)]
                )
    artifact["call_count"] = sum(
        len(row["calls"]) for item in artifact["providers"] for row in item["probes"]
    )
    artifact["elapsed_seconds"] = round(sum(
        call["elapsed_seconds"] for item in artifact["providers"]
        for row in item["probes"] for call in row["calls"]
    ), 3)
    validate_artifact(artifact)
    OUTPUT.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"extended {OUTPUT} with {shape} on both providers")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-claude-maximum", action="store_true")
    parser.add_argument("--add-populated-correction", action="store_true")
    parser.add_argument("--add-representative-census", action="store_true")
    args = parser.parse_args()
    if args.repair_claude_maximum:
        sys.exit(repair_claude_maximum())
    if args.add_populated_correction:
        sys.exit(add_shape("populated-correction"))
    if args.add_representative_census:
        sys.exit(add_shape("representative-census"))
    sys.exit(main())
