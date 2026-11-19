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
from threading import Lock
import time
from unittest.mock import patch

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
STRUCTURAL_ROLE = "evidence-repository"


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


def request_for(root, predecessor, *, attempted_round=0):
    last_round = 0
    supported = False
    if predecessor is not None:
        state = json.loads(predecessor)
        last_round = state["review_state"].get("last_round", 0)
        if type(last_round) is not int or last_round < 0:
            raise ValueError("invalid durable predecessor round")
        supported = any(row.get("verdict") == "supported"
                        for row in state.get("claim_state", {}).get("claims", {}).values())
    round_no = max(last_round, attempted_round) + 1
    # Moving the same assertion under a new heading reopens it through the
    # ordinary edit-cone rules. A rejected fixture receipt cannot qualify from
    # frozen support and does not need to rewrite its durable predecessor.
    plan = PLAN
    if supported:
        plan = plan.replace("# Release premise\n", f"# Release premise (qualification round {round_no})\n", 1)
    return dict(repo_path=str(root / "repository"), plan_text=plan, engine="codex",
                round=round_no, lineage=LINEAGE, propose_patch=False, stakes=STAKES)


def fixture_revision(root):
    repo = root / "repository"
    readme = repo / "README.md"

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo)

    if (git("ls-tree", "-r", "--name-only", "HEAD") != b"README.md\n"
            or git("show", "HEAD:README.md") != FIXTURE_README.encode()
            or {path.name for path in repo.iterdir()} != {".git", "README.md"}
            or not readme.is_file() or readme.is_symlink()
            or readme.read_bytes() != FIXTURE_README.encode()):
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
    trials = root / "trials"
    trials.mkdir(exist_ok=True)
    previous = {path.relative_to(trials).as_posix(): sha(path.read_bytes())
                for path in sorted(trials.glob("round-*/receipt.json"))}
    request = request_for(root, predecessor, attempted_round=previous_round(root, previous))
    directory = Path(tempfile.mkdtemp(prefix=f"round-{request['round']:03d}-", dir=trials))
    return directory, dict(
        request=request, fixture_revision=revision, prior_receipts=previous,
        predecessor_text=predecessor,
        predecessor_sha256=sha(predecessor.encode()) if predecessor else None,
    )


def previous_round(root, receipts):
    latest = 0
    for relative, digest in receipts.items():
        path = Path(relative)
        if (len(path.parts) != 2 or not path.parts[0].startswith("round-")
                or path.name != "receipt.json"):
            raise ValueError("invalid predecessor trial path")
        raw = (root / "trials" / path).read_bytes()
        if sha(raw) != digest:
            raise ValueError("retained predecessor trial bytes changed")
        request = json.loads(raw)["request"]
        label = request["round"]
        if (type(label) is not int or label < 1 or request["lineage"] != LINEAGE
                or not path.parts[0].startswith(f"round-{label:03d}-")):
            raise ValueError("invalid predecessor trial round or lineage")
        latest = max(latest, label)
    return latest


def evidence_call(engine, args, kwargs, *, resume):
    prompt, _, model, effort, web_search = args[1:] if resume else args
    return dict(role=engine.role, prompt=prompt, model=model, effort=effort,
                web_search=web_search, timeout=kwargs.get("timeout"),
                resumed_session=args[0] if resume else None,
                response_schema=kwargs.get("response_schema"))


def observe_evidence_calls(engine_type, record):
    """Record the arguments and reply at the actual engine call boundary."""
    roles = {"evidence-discovery", "evidence-binding", "evidence-text", STRUCTURAL_ROLE}

    def wrap(method, *, resume):
        def observed(engine, *args, **kwargs):
            if engine.role not in roles:
                return method(engine, *args, **kwargs)
            attempt = evidence_call(engine, args, kwargs, resume=resume)
            record["reviews"].append(attempt)
            review = method(engine, *args, **kwargs)
            attempt["review"] = asdict(review)
            return review
        return observed

    engine_type.run = wrap(engine_type.run, resume=False)
    engine_type.resume = wrap(engine_type.resume, resume=True)


def read_native_review(actual):
    from paranoia_local.engines import CodexEngine, Review

    required = {"text", "session_ref", "returncode", "error", "duration_ms",
                "raw", "failure_detail", "stderr"}
    if not required <= actual["review"].keys():
        raise ValueError("missing observed Review execution or channel field")
    review = Review(**actual["review"])
    extracted = CodexEngine().parse_output(review.raw)
    if (review.error or extracted.error or type(review.returncode) is not int or review.returncode != 0
            or type(review.duration_ms) is not int or review.duration_ms < 0):
        raise ValueError("native execution or duration failure")
    if (not review.session_ref or extracted.text != review.text
            or extracted.session_ref != review.session_ref):
        raise ValueError("returned review differs from native stdout extraction")
    return review


def validate_attempts(record, handlers):
    from paranoia_local.engines import CodexEngine

    rows = [r for r in record["audit"]["attempt_ledger"] if r["role"].startswith("claim-")]
    actuals = [call for call in record["reviews"] if call["role"] != STRUCTURAL_ROLE]
    if len(rows) != len(actuals):
        raise ValueError("native review custody/attempt inventory mismatch")
    expected_roles = (
        ("claim-discovery", "evidence-discovery", handlers.PLAN_EVIDENCE_DISCOVERY_TIMEOUT_SEC),
        ("claim-binding", "evidence-binding", handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC),
        ("claim-attestation", "evidence-text", handlers.PLAN_EVIDENCE_PHASE_TIMEOUT_SEC),
    )
    index = 0
    discovery_session = None
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
            if not {"role", "timeout", "resumed_session", "review", "prompt"} <= actual.keys():
                raise ValueError("missing observed engine invocation field")
            review = read_native_review(actual)
            prior_session = initial_session if retry else (
                discovery_session if phase == "claim-binding" else None
            )
            if (actual["role"] != provider_role or actual["timeout"] != timeout
                    or actual["resumed_session"] != prior_session
                    or (prior_session is not None and review.session_ref != prior_session)):
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
            if row["outcome"] != expected_outcome:
                raise ValueError("native evidence correction did not complete")
            index += 1
        if phase == "claim-discovery":
            discovery_session = review.session_ref
    if index != len(rows):
        raise ValueError("unexpected native evidence role after complete graph")


def structural_sequences(audit, observations, rc):
    rows = [row for row in audit["attempt_ledger"] if not row["role"].startswith("claim-")]
    structural = {row["role"]: row for row in rows}
    sequences = {role: row["sequence"] for role, row in structural.items()}
    if (not rows or len(structural) != len(rows) or any(type(seq) is not int for seq in sequences.values())
            or sorted(sequences.values()) != list(range(1, len(rows) + 1))):
        raise ValueError("invalid tracked structural attempt sequence")
    native = {
        sha(review.raw.encode("utf-8", "surrogatepass")): (position, call, review)
        for position, (call, review) in enumerate(observations)
    }
    if len(native) != len(observations) or len(native) != len(rows):
        raise ValueError("structural attempt inventory differs from observed native calls")
    bound = {}
    for role, row in structural.items():
        observed = native.pop(row["raw_sha256"], None)
        if observed is None or observed[2].session_ref != row["session_ref"]:
            raise ValueError("structural attempt differs from observed native stdout")
        bound[role] = observed
    for role, row in structural.items():
        position, call, _ = bound[role]
        if role.endswith("-validation-retry"):
            initial_role = role.removesuffix("-validation-retry")
            initial = structural.get(initial_role)
            if (not initial or initial["sequence"] >= row["sequence"]
                    or initial["outcome"] != "validation-invalid" or row["outcome"] != "completed"
                    or initial["session_ref"] != row["session_ref"]
                    or call["resumed_session"] != initial["session_ref"]):
                raise ValueError("structural correction lacks an invalid attempt in the same session")
            if position <= bound[initial_role][0]:
                raise ValueError("observed structural correction precedes its initial invocation")
        elif call["resumed_session"] is not None or (
            row["outcome"] != "completed" and (
                row["outcome"] != "validation-invalid" or role + "-validation-retry" not in structural
            )
        ):
            raise ValueError("native structural attempt did not complete or receive a repair")
    if "consolidation" in sequences and any(
        seq >= sequences["consolidation"] or bound[role][0] >= bound["consolidation"][0]
        for role, seq in sequences.items() if role.startswith("census-")
    ):
        raise ValueError("structural consolidation precedes lane completion")
    expected_rejections = [
        rc.rejected_payload(
            row["role"], bound[row["role"]][2].text,
            sequence=row["sequence"], validation_issue=row["validation_issue"],
        )
        for row in sorted(rows, key=lambda row: row["sequence"]) if row["outcome"] == "validation-invalid"
    ]
    if (audit.get("rejected_payloads") or []) != expected_rejections:
        raise ValueError("structural rejected replies differ from their invalid attempts")
    return sequences


def audit_projection(audit):
    return {key: value for key, value in audit.items() if key not in {"timestamp", "run_id", "claim_duration_ms"}}


def validate_timing(record):
    elapsed = record["elapsed_seconds"]
    audit = record["audit"]
    claim_ms = audit["claim_duration_ms"]
    durations = [row["duration_ms"] for row in audit["attempt_ledger"] if row["role"].startswith("claim-")]
    serial_ms = sum(durations)
    # Each serial attempt and the encompassing phase are recorded in whole milliseconds.
    if (type(elapsed) not in (int, float) or not 0 < elapsed < float("inf")
            or type(claim_ms) is not int or claim_ms < 0
            or serial_ms > claim_ms + len(durations)
            or serial_ms > elapsed * 1000
            or claim_ms > elapsed * 1000 + 1):
        raise ValueError("measured native dispatch, claim phase and serial attempts disagree")


def replay_review(record, handlers, pc):
    """Reconstruct tracked critique_plan from observed responses in a private state root."""
    from paranoia_local.engines import CodexEngine

    request = record["request"]
    run_staged = handlers._staged_call
    def call_key(call):
        return call["role"], call["resumed_session"], call["prompt"]

    pending = {}
    structural_observations = []
    for call in record["reviews"]:
        key = call_key(call)
        if key in pending:
            raise ValueError("duplicate observed native invocation")
        review = read_native_review(call)
        pending[key] = (call, review)
        if call["role"] == STRUCTURAL_ROLE:
            structural_observations.append((call, review))
        elif structural_observations:
            raise ValueError("observed claim invocation follows structural review")
    sequences = structural_sequences(record["audit"], structural_observations, handlers.rc)
    calls_lock = Lock()
    captures = [
        pc.sources.Capture(**{**row, "candidate": pc.sources.CandidateSource(**row["candidate"])})
        for row in record["captures"]
    ]
    pending_captures = [captures]

    def respond(*, resume):
        def respond_to_call(engine, *args, **kwargs):
            observed = evidence_call(engine, args, kwargs, resume=resume)
            with calls_lock:
                expected, review = pending.pop(call_key(observed), ({}, None))
            if {k: v for k, v in expected.items() if k != "review"} != observed:
                raise ValueError(f"observed native {engine.role} invocation differs from production replay")
            if resume and engine.role == STRUCTURAL_ROLE and review.session_ref != observed["resumed_session"]:
                raise ValueError("native structural correction returned a different session")
            return review
        return respond_to_call

    def capture(candidates, **kwargs):
        if not pending_captures or candidates != [row.candidate for row in captures]:
            raise ValueError("native capture inventory differs from production replay")
        return pending_captures.pop()

    def staged_call(*, role, next_sequence, **kwargs):
        # Give the production validators their recorded sequence labels. The
        # physical order in which the replay threads start need not match.
        labels = iter((role, role + "-validation-retry"))

        def recorded_sequence():
            sequence = sequences.get(next(labels, None))
            if sequence is None:
                raise ValueError("unexpected structural attempt during production replay")
            return sequence

        return run_staged(role=role, next_sequence=recorded_sequence, **kwargs)

    with tempfile.TemporaryDirectory(prefix="paranoia-150-replay-") as scratch:
        scratch = Path(scratch)
        state_root = scratch / "state"
        state_file = scratch / record["state_relative_path"]
        if record["predecessor_text"] is not None:
            state_file.parent.mkdir(parents=True)
            state_file.write_bytes(record["predecessor_text"].encode())
        with (patch.dict(os.environ, {"PARANOIA_STATE_ROOT": str(state_root)}),
              patch.object(CodexEngine, "run", respond(resume=False)),
              patch.object(CodexEngine, "resume", respond(resume=True)),
              patch.object(pc.sources, "capture_all", capture),
              patch.object(handlers, "_staged_call", staged_call)):
            report = handlers.critique_plan(request, engine=CodexEngine(), log_dir=scratch / "logs")
        audits = list((scratch / "logs").glob("*-critique_plan-*.json"))
        if (pending_captures or pending or len(audits) != 1 or not state_file.is_file()
                or report != record["report"] or json.loads(state_file.read_bytes()) != record["state"]
                or audit_projection(json.loads(audits[0].read_bytes())) != audit_projection(record["audit"])):
            raise ValueError("native report, attempts or durable state differ from production replay")


def validate_fixture_snapshot(root, revision, plan, state, handlers):
    repo = root / "repository"
    if revision != fixture_revision(root):
        raise ValueError("qualification repository mismatch")
    tree = handlers.orientation.snapshot_tree(repo, revision)
    committed = subprocess.check_output(["git", "rev-parse", f"{revision}^{{tree}}"], cwd=repo).decode().strip()
    snapshot = handlers.orientation.wrap_commit(repo, tree, revision)
    if tree != committed or state["review_state"]["snapshot_digest"] != handlers.rc.digest(f"{plan}\0{snapshot}"):
        raise ValueError("durable structural snapshot differs from reviewed fixture")


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
    attempted_round = previous_round(root, record["prior_receipts"])
    if record["request"] != request_for(root, predecessor, attempted_round=attempted_round):
        raise ValueError("qualification input or provider mismatch")
    plan = record["request"]["plan_text"]
    audit, state, report = record["audit"], record["state"], record["report"]
    validate_fixture_snapshot(root, record["fixture_revision"], plan, state, handlers)
    if (audit["error"] or audit["returncode"] != 0 or audit["claim_audit_failed"]
            or audit["tool"] != "critique_plan" or audit["engine"] != record["request"]["engine"]
            or audit["grounded"] is not True or audit["plan_digest"] != sha(plan.encode())[:16]
            or not audit.get("class_closure") or not isinstance(audit.get("staged_settlement"), dict)
            or audit["lineage"] != record["request"]["lineage"]
            or audit["round"] != record["request"]["round"]
            or state["review_state"]["last_round"] != record["request"]["round"]
            or state["claim_state"]["plan_snapshot"] != plan
            or record["state_relative_path"] != "state/lineages/" + record["request"]["lineage"] + ".json"):
        raise ValueError("failed or misbound native invocation")
    claims = state["claim_state"]
    if pc.is_blocked(claims) or len(claims["claims"]) != 1:
        raise ValueError("expected exactly one supported, debt-free external claim")
    claim = next(iter(claims["claims"].values()))
    if (claim["anchor"] != PROPOSITION or claim["proposition"] != PROPOSITION
            or claim["verdict"] != "supported" or not pc._captured_support(claim)):
        raise ValueError("expected release claim or captured cold support missing")
    validate_attempts(record, handlers)
    validate_timing(record)
    replay_review(record, handlers, pc)
    qualifying = False
    for index, (item, capture) in enumerate(zip(claim["evidence"], record["captures"], strict=True)):
        if item["url"] != URL or item["relation"] != "supports_claim":
            continue
        provenance = next((r for r in claim["capture_provenance"] if r["evidence_index"] == index), {})
        decision = next((r for r in claim["capture_attestations"] if r["evidence_index"] == index), {})
        if (not pc._captured_support({**claim, "capture_attestations": [decision]})
                or provenance.get("requested_url") != URL or provenance.get("final_url") != URL
                or capture["final_url"] != URL or capture["status"] != 200):
            continue
        if (not isinstance(capture["text"], str) or not re.fullmatch(r"[0-9a-f]{64}", capture["content_sha256"] or "")
                or capture["error"] is not None
                or any(capture[key] != provenance.get(key) or capture[key] != decision.get(key)
                       for key in ("content_sha256", "text_sha256", "status", "content_type", "fallback_attempted"))
                or sha(capture["text"].encode()) != capture["text_sha256"]
                or not RELEASE_PASSAGE.search(pc.sources.normalize_text(item["quote"]))
                or not pc.sources.passage_matches(item["quote"], capture["text"])):
            continue
        qualifying = True
    if not qualifying:
        raise ValueError("official captured date passage and matching cold decision missing")


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
                  **fixture, captures=[], reviews=[], outcome="failed", elapsed_seconds=None)
    original_capture = es.capture_all
    def capture(*a, **k):
        captures = original_capture(*a, **k)
        record["captures"].extend(asdict(c) for c in captures)
        return captures
    es.capture_all = capture
    observe_evidence_calls(CodexEngine, record)
    try:
        if read_predecessor(root) != fixture["predecessor_text"]:
            raise ValueError("durable predecessor changed before dispatch")
        started = time.monotonic()
        try:
            record["report"] = server.dispatch("critique_plan", request,
                default_engine_name="codex", log_dir=directory / "logs", on_progress=lambda s: print(s, flush=True))
        finally:
            record["elapsed_seconds"] = time.monotonic() - started
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
                      report_sha256=sha(record["report"].encode()))
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
        (directory / "receipt.json").write_text(json.dumps(record, indent=2, ensure_ascii=True)+"\n")
        print(json.dumps({k: record[k] for k in ["outcome","elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
