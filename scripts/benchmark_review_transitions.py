#!/usr/bin/env python3
"""Compare public-handler model-call topology against another source checkout.

This is deterministic protocol replay, not a provider-quality or wall-time benchmark.
Each process imports exactly one source tree; fixture replies are identical across
versions. Run: python scripts/benchmark_review_transitions.py --baseline /path/to/base
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def trial(source: Path):
    sys.path.insert(0, str(source / "src"))
    from paranoia_local import class_closure as cc, handlers, review_census as rc
    from paranoia_local import engines, staged_protocol as sp

    outcomes = {}
    for mode in (cc.PLAN_MODE, cc.BRANCH_MODE):
        for scenario in ("class-only", "checkpoint"):
            with tempfile.TemporaryDirectory(prefix="paranoia-benchmark-") as directory:
                parent = Path(directory)
                repo = parent / "repository"
                repo.mkdir()
                env = {**os.environ, "GIT_CONFIG_GLOBAL":"/dev/null", "GIT_CONFIG_SYSTEM":"/dev/null"}
                def git(*args):
                    return subprocess.run(["git", *args], cwd=repo, env=env, check=True,
                                          capture_output=True, text=True).stdout.strip()
                git("init", "-q", "-b", "main")
                git("config", "user.name", "fixture")
                git("config", "user.email", "fixture@example.test")
                (repo / "app.py").write_text("safe = True\n")
                git("add", "."); git("-c", "commit.gpgsign=false", "commit", "-qm", "baseline")
                git("checkout", "-qb", "feature")
                (repo / "app.py").write_text("safe = True  # inspected\n")
                git("add", "."); git("-c", "commit.gpgsign=false", "commit", "-qm", "change")
                os.environ[cc.STATE_ROOT_ENV] = str(parent / "state")
                anchor = "plan:1" if mode == cc.PLAN_MODE else "repository/app.py:1"
                citation = [{"anchor":anchor, "rationale":"the complete obligation is inspected"}]
                coverage = [{"id":item, "status":"covered", "summary":"whole artifact inspected",
                             "evidence":citation, "finding_ids":[]} for item in sp.CHECKLIST]
                member = [{"member_id":"primary-call-path", "evidence":citation}]
                last = 6 if scenario == "checkpoint" else 1
                state = rc.normalize_state(None, stakes="s", snapshot=rc.digest("prior"))
                state.update(phase="correction", last_round=last, plan_line_count=1, debt=[{
                    "id":"D1", "finding_id":"F1", "status":"open", "severity":"MAJOR",
                    "summary":"repair required", "evidence":[anchor], "remedy":"repair",
                    "source_ids":[], "class_ids":["class-a"], "first_round":1, "last_round":last,
                }])
                tracked = cc.TrackedClass(
                    "class-a", "all call paths satisfy the obligation", cc.MAJOR, 1,
                    cc.OPEN, procedure="inspect all call paths", members=("primary-call-path",),
                )
                cc.save_lineage(parent / "state", cc.Lineage(
                    "benchmark", rounds=last, mode=mode, classes={"class-a":tracked},
                    review_state=state,
                ))
                calls = []
                def response(self, prompt, *unused, **kwargs):
                    schema = kwargs["response_schema"]
                    properties = schema["properties"]
                    if "lane" in properties:
                        lane = properties["lane"]["const"]
                        active = json.loads(next(l[len("ACTIVE CLASSES: "):]
                                            for l in prompt.splitlines() if l.startswith("ACTIVE CLASSES: ")))
                        value = {
                            "lane":lane, "coverage":coverage, "findings":[],
                            "class_assessments":[{"class_id":c["class_id"], "verdict":"satisfied",
                                                  "member_coverage":member, "finding_id":None} for c in active],
                        }
                        role = "census-" + lane
                    else:
                        role = properties["role"]["const"]
                        value = {"role":role, "governing_findings":[], "debt_outcomes":[],
                                 "class_actions":{}, "concession_challenges":{}}
                        value["class_actions"] = {
                            cid:None for cid in properties["class_actions"]["properties"]
                        }
                        if role != "census":
                            ids = list(properties["class_outcomes"]["properties"])
                            value["class_outcomes"] = {cid:{"verdict":"satisfied", "member_coverage":member}
                                                       for cid in ids}
                            value["class_actions"] = {cid:None for cid in ids}
                        if role == "final":
                            value["coverage"] = coverage
                        if role == "correction":
                            value["debt_outcomes"] = [{
                                "debt_id":"D1", "status":"open" if scenario == "checkpoint" else "closed",
                                "evidence":citation,
                                **({"reason":"still violated"} if scenario == "checkpoint" else {}),
                            }]
                            if scenario == "checkpoint":
                                value["class_outcomes"]["class-a"] = {
                                    "verdict":"violated", "evidence":citation,
                                    "basis":{"kind":"carried_debt", "debt_id":"D1"},
                                }
                            else:
                                value["class_actions"]["class-a"] = {"kind":"replace", "definition":{
                                    "invariant":"replacement call-path obligation",
                                    "severity":"MAJOR", "procedure":"inspect all call paths",
                                    "members":["primary-call-path"],
                                }}
                    calls.append(role)
                    text = json.dumps(value)
                    return engines.Review(text=text, raw=text, session_ref="benchmark-session")
                engines.CodexEngine.run = response
                engines.CodexEngine.resume = lambda self, session, prompt, *a, **kw: response(self, prompt, *a, **kw)
                args = {"repo_path":str(repo), "lineage":"benchmark", "round":last + 1, "stakes":"s"}
                if mode == cc.PLAN_MODE:
                    args.update(plan_text="artifact", claim_verification=False)
                else:
                    args.update(base_ref="main", head_ref="feature")
                handler = handlers.critique_plan if mode == cc.PLAN_MODE else handlers.critique_branch
                started = time.perf_counter()
                result = handler(args, engine=engines.CodexEngine(), log_dir=parent / "logs")
                if scenario == "class-only":
                    args["round"] += 1
                    result = handler(args, engine=engines.CodexEngine(), log_dir=parent / "logs")
                durable = cc.load_lineage(parent / "state", "benchmark", stamp="inspect", mode=mode)
                outcomes[mode + "/" + scenario] = {
                    "calls":calls, "call_count":len(calls),
                    "local_fixture_elapsed_ms":int((time.perf_counter() - started) * 1000),
                    "substantive":{
                        "classes":{cid:c.status for cid,c in durable.classes.items()},
                        "debt":[(d["id"],d["status"]) for d in durable.review_state["debt"]],
                        "last_round":durable.review_state["last_round"],
                    },
                    "blocked":"CONVERGENCE: NOT-BLOCKED" not in result,
                }
    files = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted((source / "src/paranoia_local").glob("*.py"))}
    return {"source_sha256":hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
            "provider_mode":"deterministic", "cases":outcomes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--trial", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.trial:
        print(json.dumps(trial(args.trial.resolve())))
        return 0
    if not args.baseline:
        parser.error("--baseline is required")
    def run(source):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--trial", str(source)],
            check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout)
    baseline, candidate = run(args.baseline.resolve()), run(ROOT)
    comparisons = {}
    for key, before in baseline["cases"].items():
        after = candidate["cases"][key]
        assert before["substantive"] == after["substantive"], key
        assert before["blocked"] == after["blocked"], key
        saved = before["call_count"] - after["call_count"]
        assert saved == (3 if key.endswith("class-only") else 1), (key,before,after)
        comparisons[key] = {"avoided_calls":saved, "substantive_outcome_equal":True}
    report = {
        "kind":"deterministic-public-handler-topology-comparison",
        "limitation":"No live quality or general latency claim. Fixture elapsed time excludes provider inference.",
        "baseline":baseline, "candidate":candidate, "comparisons":comparisons,
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
