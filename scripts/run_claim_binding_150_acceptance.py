"""Source-bound native claim qualification for issue 150; retain every failed trial."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.python.org/downloads/release/python-3110/"
PLAN = (
    "# Release premise\n\nPython 3.11.0 was released on October 24, 2022.\n\n"
    f"Candidate official source: <{URL}>\n"
)
FIXTURE_README = "# Issue 150 native qualification fixture\n"
HARNESS = ("scripts/run_claim_binding_150_acceptance.py", "scripts/benchmark_bootstrap.py")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_identity():
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    names = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", "src/paranoia_local"],
        cwd=ROOT, text=True).splitlines()
    names = {n for n in names if n.endswith(".py")}
    actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / "src/paranoia_local").rglob("*.py")}
    if names != actual:
        raise ValueError("production inventory differs from committed source")
    hashes = {}
    for name in sorted(names | set(HARNESS)):
        data = (ROOT / name).read_bytes()
        if data != subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=ROOT):
            raise ValueError(f"uncommitted qualification source: {name}")
        hashes[name] = sha(data)
    return {"revision": revision, "sha256": hashes}


def validate(record, handlers, pc):
    for key in ("audit", "state"):
        raw = record[key + "_text"].encode()
        if sha(raw) != record[key + "_sha256"] or json.loads(raw) != record[key]:
            raise ValueError(f"changed retained {key}")
    if sha(record["report"].encode()) != record["report_sha256"]:
        raise ValueError("changed retained report")
    if record["request"]["plan_text"] != PLAN or record["request"]["engine"] != "codex":
        raise ValueError("qualification input or provider mismatch")
    if record["fixture_readme_sha256"] != sha(FIXTURE_README.encode()):
        raise ValueError("qualification repository mismatch")
    audit, state, report = record["audit"], record["state"], record["report"]
    if (audit["error"] or audit["returncode"] != 0 or audit["claim_audit_failed"]
            or audit["lineage"] != record["request"]["lineage"]
            or audit["round"] != record["request"]["round"]
            or state["review_state"]["last_round"] != record["request"]["round"]
            or state["claim_state"]["plan_snapshot"] != PLAN
            or record["state_relative_path"] != "state/lineages/" + record["request"]["lineage"] + ".json"):
        raise ValueError("failed or misbound native invocation")
    claims = state["claim_state"]
    if pc.is_blocked(claims) or len(claims["claims"]) != 1:
        raise ValueError("expected exactly one supported, debt-free external claim")
    claim = next(iter(claims["claims"].values()))
    if (claim["anchor"] != PLAN.splitlines()[2] or not pc._captured_support(claim)
            or "CLAIM-CLOSURE: 1 supported, 0 refuted, 0 unverified" not in report):
        raise ValueError("expected release claim/report or captured cold support missing")
    qualifying = []
    for index, item in enumerate(claim["evidence"]):
        provenance = next((r for r in claim["capture_provenance"] if r["evidence_index"] == index), {})
        decision = next((r for r in claim["capture_attestations"] if r["evidence_index"] == index), {})
        capture = next((r for r in record["captures"] if r["final_url"] == URL
                        and r["text_sha256"] == provenance.get("text_sha256")), None)
        if item["url"] != URL or capture is None:
            continue
        if (capture["status"] == 200 and capture["content_sha256"] == provenance["content_sha256"]
                and sha(capture["text"].encode()) == provenance["text_sha256"]
                and pc.sources.passage_matches(item["quote"], capture["text"])
                and "2022" in item["quote"] and "24" in item["quote"]
                and ("Oct" in item["quote"] or "October" in item["quote"])
                and decision.get("publisher_authority") is True
                and decision.get("passage_entailment") is True):
            qualifying.append(index)
    if not qualifying:
        raise ValueError("official captured date passage and matching cold decision missing")
    rows = [r for r in audit["attempt_ledger"] if r["role"].startswith("claim-")]
    if len(rows) != len(record["reviews"]):
        raise ValueError("native review custody/attempt inventory mismatch")
    expected = ["claim-discovery", "claim-binding", "claim-attestation"]
    completed = []
    from paranoia_local.engines import CodexEngine, Review
    for index, (row, actual) in enumerate(zip(rows, record["reviews"], strict=True)):
        role = actual["role"]
        timeout = (handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC if role.startswith("claim-discovery")
                   else handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC)
        review = Review(**actual["review"])
        extracted = CodexEngine().parse_output(review.raw)
        if extracted.text != review.text or extracted.session_ref != review.session_ref:
            raise ValueError("returned review differs from native stdout extraction")
        projection = handlers._attempt(role, CodexEngine(), review,
                                      requested_timeout_sec=actual["timeout"]).json()
        for key in ["role", "session_ref", "returncode", "duration_ms", "requested_timeout_sec",
                    "raw_sha256", "raw_excerpt", "failure_detail_sha256", "failure_detail_excerpt",
                    "stderr_sha256", "stderr_excerpt"]:
            if row.get(key) != projection[key] or row.get(key) is None:
                raise ValueError(f"native attempt channel/metadata mismatch: {key}")
        if (row["returncode"] != 0 or actual["timeout"] != timeout
                or type(row["duration_ms"]) is not int or row["duration_ms"] < 0):
            raise ValueError("native execution/timeout/duration failure")
        if row["outcome"] == "validation-invalid":
            if (index+1 >= len(rows) or rows[index+1]["role"] != role+"-validation-retry"
                    or rows[index+1]["outcome"] != "completed"
                    or rows[index+1]["session_ref"] != row["session_ref"]):
                raise ValueError("invalid initial reply lacks successful same-session repair")
        elif row["outcome"] != "completed":
            raise ValueError("native role did not complete")
        if row["outcome"] == "completed":
            completed.append(role.removesuffix("-validation-retry"))
    if completed != expected:
        raise ValueError("nonempty complete captured claim graph required")
    if record["elapsed_seconds"] <= 0:
        raise ValueError("missing measured wall time")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", type=Path)
    args = parser.parse_args()
    identity = source_identity()  # before owned modules or production imports
    runpy.run_path(str(ROOT / "scripts/benchmark_bootstrap.py"))
    sys.path.insert(0, str(ROOT / "src"))
    from paranoia_local import handlers, plan_claims as pc, server, external_sources as es
    if args.validate_only:
        record = json.loads(args.validate_only.read_text())
        if record.get("outcome") != "passed":
            raise ValueError("failed trial is not acceptance")
        if identity["sha256"] != record["source"]["sha256"]:
            raise ValueError("qualification source differs from delivery source")
        validate(record, handlers, pc)
        print("native claim qualification replay passed")
        return
    if args.output is None:
        parser.error("provide --output or --validate-only")
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    os.environ["PARANOIA_STATE_ROOT"] = str(directory / "state")
    # The reviewed content is a synthetic repository. The implementation under
    # qualification still loads from the committed, verified production checkout.
    fixture_repo = directory / "repository"
    fixture_repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=fixture_repo, check=True)
    (fixture_repo / "README.md").write_text(FIXTURE_README, encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=fixture_repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Qualification Fixture", "-c", "user.email=fixture@example.com",
         "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
         "commit", "-qm", "Freeze qualification fixture"],
        cwd=fixture_repo, check=True,
    )
    request = dict(repo_path=str(fixture_repo), plan_text=PLAN, engine="codex", round=1,
                   lineage="issue150-native-"+str(time.time_ns()), propose_patch=False,
                   stakes="Trusted single local user and OS; untrusted static content; no hostile race. "
                          "One external claim. Wrong evidence binding is high impact; recoverable blocking is acceptable.")
    record = dict(kind="issue150-native-claim-qualification", source=identity, request=request,
                  fixture_readme_sha256=sha((fixture_repo / "README.md").read_bytes()),
                  captures=[], reviews=[], outcome="failed")
    original_capture, original_record = es.capture_all, handlers._CapturedClaimEngine._record
    def capture(*a, **k):
        captures = original_capture(*a, **k)
        record["captures"].extend(asdict(c) for c in captures)
        return captures
    def observe(self, role, engine, review, *, requested_timeout_sec):
        record["reviews"].append(dict(role=role, timeout=requested_timeout_sec, review=asdict(review)))
        original_record(self, role, engine, review, requested_timeout_sec=requested_timeout_sec)
    es.capture_all, handlers._CapturedClaimEngine._record = capture, observe
    started = time.monotonic()
    try:
        record["report"] = server.dispatch("critique_plan", request,
            default_engine_name="codex", log_dir=directory / "logs", on_progress=lambda s: print(s, flush=True))
        (directory / "report.txt").write_text(record["report"])
        audits = list((directory / "logs").glob("*-critique_plan-*.json"))
        if len(audits) != 1:
            raise ValueError("native invocation did not retain exactly one audit")
        audit_bytes = audits[0].read_bytes()
        state_bytes = (directory / "state/lineages" / (request["lineage"]+".json")).read_bytes()
        record.update(audit=json.loads(audit_bytes), state=json.loads(state_bytes),
                      audit_text=audit_bytes.decode(), state_text=state_bytes.decode(),
                      state_relative_path="state/lineages/"+request["lineage"]+".json",
                      audit_sha256=sha(audit_bytes), state_sha256=sha(state_bytes),
                      report_sha256=sha(record["report"].encode()), elapsed_seconds=time.monotonic()-started)
        if source_identity() != identity:
            raise ValueError("source changed during qualification")
        for name, module in tuple(sys.modules.items()):
            if name == "paranoia_local" or name.startswith("paranoia_local."):
                if not Path(module.__file__).resolve().is_relative_to(ROOT / "src/paranoia_local"):
                    raise ValueError("loaded production module belongs to another installation")
        validate(record, handlers, pc)
        record["outcome"] = "passed"
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic()-started
        (directory / "receipt.json").write_text(json.dumps(record, indent=2, ensure_ascii=True)+"\n")
        print(json.dumps({k: record[k] for k in ["outcome","elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
