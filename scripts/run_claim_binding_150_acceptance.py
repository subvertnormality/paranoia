"""Source-bound native claim qualification for issue 150; retain every failed trial."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.python.org/doc/versions/"
PROPOSITION = "Python 3.11.0 was released on October 24, 2022."
PLAN = (
    f"# Release premise\n\n{PROPOSITION}\n\n"
    f"Candidate official source: <{URL}>\n"
)
FIXTURE_README = "# Issue 150 native qualification fixture\n"
LINEAGE = "issue150-native"
STAKES = (
    "Trusted single local user and OS. Untrusted static content. No hostile race. "
    "One external claim. Wrong evidence binding is high impact. Recoverable blocking is acceptable."
)
RELEASE_PASSAGE = re.compile(
    r"Python 3\.11\.0[, ]+\s*(?:was )?released on "
    r"(?:24 October 2022|October 24, 2022)\b", re.IGNORECASE,
)
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


def read_predecessor(root):
    path = root / "state/lineages" / (LINEAGE + ".json")
    if not path.exists():
        return None
    return path.read_bytes().decode("utf-8")


def request_for(root, predecessor):
    round_no = 1
    if predecessor is not None:
        last_round = json.loads(predecessor)["review_state"].get("last_round", 0)
        if type(last_round) is not int or last_round < 0:
            raise ValueError("invalid durable predecessor round")
        round_no = last_round + 1
    return dict(repo_path=str(root / "repository"), plan_text=PLAN, engine="codex",
                round=round_no, lineage=LINEAGE, propose_patch=False, stakes=STAKES)


def fixture_revision(root):
    repo = root / "repository"
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo)
    if (git("ls-tree", "-r", "--name-only", "HEAD") != b"README.md\n"
            or git("show", "HEAD:README.md") != FIXTURE_README.encode()):
        raise ValueError("qualification repository differs from frozen fixture")
    return git("rev-parse", "HEAD").decode().strip()


def prepare_trial(root):
    repo = root / "repository"
    if not repo.exists():
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        (repo / "README.md").write_text(FIXTURE_README, encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Qualification Fixture", "-c", "user.email=fixture@example.com",
             "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
             "commit", "-qm", "Freeze qualification fixture"],
            cwd=repo, check=True,
        )
    revision = fixture_revision(root)
    predecessor = read_predecessor(root)
    request = request_for(root, predecessor)
    trials = root / "trials"
    trials.mkdir(exist_ok=True)
    previous = {path.relative_to(trials).as_posix(): sha(path.read_bytes())
                for path in sorted(trials.glob("round-*/receipt.json"))}
    directory = Path(tempfile.mkdtemp(prefix=f"round-{request['round']:03d}-", dir=trials))
    return directory, dict(
        request=request, fixture_revision=revision, prior_receipts=previous,
        predecessor_text=predecessor,
        predecessor_sha256=sha(predecessor.encode()) if predecessor else None,
    )


def observe_evidence_calls(engine_type, record):
    """Record the arguments and reply at the actual engine call boundary."""
    roles = {"evidence-discovery", "evidence-binding", "evidence-text"}

    def wrap(method, *, resume):
        def observed(engine, *args, **kwargs):
            if engine.role not in roles:
                return method(engine, *args, **kwargs)
            attempt = dict(
                role=engine.role, timeout=kwargs.get("timeout"),
                prompt=args[1] if resume else args[0],
                resumed_session=args[0] if resume else None,
            )
            record["reviews"].append(attempt)
            review = method(engine, *args, **kwargs)
            attempt["review"] = asdict(review)
            return review
        return observed

    engine_type.run = wrap(engine_type.run, resume=False)
    engine_type.resume = wrap(engine_type.resume, resume=True)


def validate_attempts(record, handlers):
    from paranoia_local.engines import CodexEngine, Review

    rows = [r for r in record["audit"]["attempt_ledger"] if r["role"].startswith("claim-")]
    actuals = record["reviews"]
    if len(rows) != len(actuals):
        raise ValueError("native review custody/attempt inventory mismatch")
    expected_roles = (
        ("claim-discovery", "evidence-discovery", handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC),
        ("claim-binding", "evidence-binding", handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC),
        ("claim-attestation", "evidence-text", handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC),
    )
    index = 0
    accepted = {}
    for phase, provider_role, timeout in expected_roles:
        if index >= len(rows) or rows[index]["role"] != phase:
            raise ValueError("missing initial native evidence role")
        initial_session = rows[index]["session_ref"]
        corrected = rows[index]["outcome"] == "validation-invalid"
        for retry in ([False, True] if corrected else [False]):
            if index >= len(rows):
                raise ValueError("invalid initial reply lacks successful same-session repair")
            row, actual = rows[index], actuals[index]
            role = phase + "-validation-retry" if retry else phase
            review = Review(**actual["review"])
            extracted = CodexEngine().parse_output(review.raw)
            if review.error or extracted.error:
                raise ValueError("native execution reported an error")
            if extracted.text != review.text or extracted.session_ref != review.session_ref:
                raise ValueError("returned review differs from native stdout extraction")
            prior_session = initial_session if retry else (
                accepted["claim-discovery"][0].session_ref if phase == "claim-binding" else None
            )
            if (actual["role"] != provider_role or actual["timeout"] != timeout
                    or actual["resumed_session"] != prior_session
                    or not review.session_ref or (retry and review.session_ref != initial_session)):
                raise ValueError("native role, engine timeout, or session mismatch")
            projection = handlers._attempt(
                role, CodexEngine(), review, requested_timeout_sec=actual["timeout"],
            ).json()
            for key in ("role", "session_ref", "returncode", "duration_ms", "requested_timeout_sec",
                        "raw_sha256", "raw_excerpt", "failure_detail_sha256", "failure_detail_excerpt",
                        "stderr_sha256", "stderr_excerpt"):
                if row.get(key) != projection[key] or row.get(key) is None:
                    raise ValueError(f"native attempt channel/metadata mismatch: {key}")
            expected_outcome = "validation-invalid" if corrected and not retry else "completed"
            if (row["outcome"] != expected_outcome or row["returncode"] != 0
                    or type(row["duration_ms"]) is not int or row["duration_ms"] < 0):
                raise ValueError("native execution, correction or duration failure")
            index += 1
        accepted[phase] = (review, actual["prompt"])
    if index != len(rows):
        raise ValueError("unexpected native evidence role after complete graph")
    return accepted


def indexed_row(text, marker, key, index):
    prefix, separator, body = text.partition(marker)
    if prefix.strip() or not separator:
        raise ValueError("missing native evidence envelope")
    matches = [
        row for row in json.loads(body)[key]
        if type(row["claim_index"]) is int and row["claim_index"] == 0
        and type(row["evidence_index"]) is int and row["evidence_index"] == index
    ]
    if len(matches) != 1:
        raise ValueError("native evidence response omitted or repeated the governing index")
    return matches[0]


def validate(record, handlers, pc, *, identity, root):
    if record.get("source") != identity:
        raise ValueError("qualification source differs from delivery revision or inventory")
    predecessor = record["predecessor_text"]
    if record["predecessor_sha256"] != (sha(predecessor.encode()) if predecessor else None):
        raise ValueError("changed retained predecessor")
    for key in ("audit", "state"):
        raw = record[key + "_text"].encode()
        if sha(raw) != record[key + "_sha256"] or json.loads(raw) != record[key]:
            raise ValueError(f"changed retained {key}")
    if sha(record["report"].encode()) != record["report_sha256"]:
        raise ValueError("changed retained report")
    if record["request"] != request_for(root, predecessor):
        raise ValueError("qualification input or provider mismatch")
    if record["fixture_revision"] != fixture_revision(root):
        raise ValueError("qualification repository mismatch")
    for relative, digest in record["prior_receipts"].items():
        path = Path(relative)
        if (len(path.parts) != 2 or not path.parts[0].startswith("round-")
                or path.name != "receipt.json" or sha((root / "trials" / path).read_bytes()) != digest):
            raise ValueError("retained predecessor trial bytes changed")
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
    if (claim["anchor"] != PROPOSITION or claim["proposition"] != PROPOSITION
            or claim["verdict"] != "supported" or not pc._captured_support(claim)
            or "CLAIM-CLOSURE: 1 supported, 0 refuted, 0 unverified" not in report):
        raise ValueError("expected release claim/report or captured cold support missing")
    accepted = validate_attempts(record, handlers)
    discovery = pc.parse_audit(accepted["claim-discovery"][0].text, PLAN)
    if (len(discovery.claims) != 1 or discovery.claims[0]["anchor"] != PROPOSITION
            or discovery.claims[0]["proposition"] != PROPOSITION
            or discovery.claims[0]["verdict"] != "supported"):
        raise ValueError("discovery did not adjudicate the exact release claim")
    candidates = discovery.claims[0]["evidence"]
    if len(candidates) != len(record["captures"]) or len(candidates) != len(claim["evidence"]):
        raise ValueError("discovery, captures and durable evidence have different inventories")
    binding = accepted["claim-binding"][0].text
    attestation, attestation_prompt = accepted["claim-attestation"]
    cold_packet = json.loads(attestation_prompt.rsplit("\n\n", 1)[1])
    qualifying = False
    for index, item in enumerate(claim["evidence"]):
        candidate, capture = candidates[index], record["captures"][index]
        if any(row.get("url") != URL or row.get("relation") != "supports_claim"
               for row in (candidate, capture["candidate"], item)):
            continue
        if any(candidate.get(key) != value or item.get(key) != value
               for key, value in capture["candidate"].items()):
            continue
        provenance = next((r for r in claim["capture_provenance"] if r["evidence_index"] == index), {})
        decision = next((r for r in claim["capture_attestations"] if r["evidence_index"] == index), {})
        if (not pc._captured_support({**claim, "capture_attestations": [decision]})
                or provenance.get("requested_url") != URL or provenance.get("final_url") != URL
                or capture["final_url"] != URL or capture["status"] != 200):
            continue
        if (not isinstance(capture["text"], str) or not re.fullmatch(r"[0-9a-f]{64}", capture["content_sha256"] or "")
                or any(capture[key] != provenance.get(key) or capture[key] != decision.get(key)
                       for key in ("content_sha256", "text_sha256"))
                or sha(capture["text"].encode()) != capture["text_sha256"]
                or not RELEASE_PASSAGE.search(pc.sources.normalize_text(item["quote"]))
                or not pc.sources.passage_matches(item["quote"], capture["text"])):
            continue
        bound = indexed_row(binding, handlers.PLAN_BINDING_MARKER, "bindings", index)
        cold = indexed_row(attestation.text, "=== EVIDENCE ATTESTATION JSON ===", "attestations", index)
        packets = [row for row in cold_packet if row["claim_index"] == 0 and row["evidence_index"] == index]
        if (bound["usable"] is True and bound["location"] == item["location"]
                and pc.sources.normalize_text(bound["passage"]) == item["quote"]
                and len(packets) == 1 and packets[0]["proposition"] == PROPOSITION
                and packets[0]["relation"] == "supports_claim" and packets[0]["passage"] == item["quote"]
                and all(packets[0]["capture"][key] == capture[key]
                        for key in ("final_url", "content_sha256", "text_sha256"))
                and cold["publisher_authority"] is True and cold["passage_entailment"] is True
                and all(cold[key] == decision[key] for key in ("authority_reason", "entailment_reason"))):
            qualifying = True
    if not qualifying:
        raise ValueError("official captured date passage and matching cold decision missing")
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
    from paranoia_local.engines import CodexEngine
    if args.validate_only:
        path = args.validate_only.resolve()
        record = json.loads(path.read_text())
        if record.get("outcome") != "passed":
            raise ValueError("failed trial is not acceptance")
        validate(record, handlers, pc, identity=identity, root=path.parents[2])
        print("native claim qualification replay passed")
        return
    if args.output is None:
        parser.error("provide --output or --validate-only")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["PARANOIA_STATE_ROOT"] = str(root / "state")
    directory, fixture = prepare_trial(root)
    request = fixture["request"]
    record = dict(kind="issue150-native-claim-qualification", source=identity,
                  **fixture, captures=[], reviews=[], outcome="failed")
    original_capture = es.capture_all
    def capture(*a, **k):
        captures = original_capture(*a, **k)
        record["captures"].extend(asdict(c) for c in captures)
        return captures
    es.capture_all = capture
    observe_evidence_calls(CodexEngine, record)
    started = time.monotonic()
    try:
        if read_predecessor(root) != fixture["predecessor_text"]:
            raise ValueError("durable predecessor changed before dispatch")
        record["report"] = server.dispatch("critique_plan", request,
            default_engine_name="codex", log_dir=directory / "logs", on_progress=lambda s: print(s, flush=True))
        (directory / "report.txt").write_text(record["report"])
        audits = list((directory / "logs").glob("*-critique_plan-*.json"))
        if len(audits) != 1:
            raise ValueError("native invocation did not retain exactly one audit")
        audit_bytes = audits[0].read_bytes()
        state_bytes = (root / "state/lineages" / (request["lineage"]+".json")).read_bytes()
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
        validate(record, handlers, pc, identity=identity, root=root)
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
