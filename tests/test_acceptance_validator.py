import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import subprocess

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_cleaning_attestation_acceptance.py"
_SPEC = importlib.util.spec_from_file_location("acceptance_validator", _SCRIPT)
assert _SPEC and _SPEC.loader
validator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validator)
_LEGACY_SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_arbitration_acceptance.py"
_LEGACY_SPEC = importlib.util.spec_from_file_location("legacy_acceptance_validator", _LEGACY_SCRIPT)
assert _LEGACY_SPEC and _LEGACY_SPEC.loader
legacy_validator = importlib.util.module_from_spec(_LEGACY_SPEC)
_LEGACY_SPEC.loader.exec_module(legacy_validator)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bind_phase_prompts(audit: dict) -> None:
    raw = audit["raw_input"]
    complaint = ""
    for index in range(0, len(audit["phase_attempts"]), 2):
        cleaner, attester = audit["phase_attempts"][index:index + 2]
        cleaner_body = validator.production_arbitrate._clean_body(
            raw["decision"], raw["stakes"], raw["context"], raw["files"],
            raw["options"], complaint,
        )
        cleaner_prompt = validator.production_prompts.compose(
            validator.production_prompts.CLEANER_INSTRUCTIONS, cleaner_body,
        )
        cleaner["prompt_sha256"] = hashlib.sha256(cleaner_prompt.encode()).hexdigest()
        cleaner["prompt_excerpt"] = validator.production_arbitrate._bounded_research_text(cleaner_prompt)
        parsed = validator.production_arbitrate.parse_cleaned_packet(
            cleaner["reply"], list(raw["options"]),
            caller_gave_context=bool(raw["context"]),
        )
        parsed["context"] = raw["context"]
        hints = validator.production_arbitrate._merge_hints(raw["files"], parsed["hints"])
        attester_body = validator._v1_attest_body(
            raw["decision"], raw["stakes"], raw["context"], raw["files"],
            hints, raw["options"], parsed,
        )
        attester_prompt = validator.production_prompts.compose(
            validator.V1_ATTEST_INSTRUCTIONS, attester_body,
        )
        attester["prompt_sha256"] = hashlib.sha256(attester_prompt.encode()).hexdigest()
        attester["prompt_excerpt"] = validator.production_arbitrate._bounded_research_text(attester_prompt)
        complaint = (
            "An independent auditor rejected your previous attempt: "
            f"{attester['rejection']}\nFix exactly that."
            if attester["rejection"] else ""
        )


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "base"],
        cwd=repo, check=True,
    )
    hashes = {}
    for relative in validator.PRODUCTION_SOURCES:
        source = repo / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"# {relative}\n")
        hashes[relative] = _sha(source)
    subprocess.run(["git", "add", "src"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "sources"],
        cwd=repo, check=True,
    )
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    packets = json.dumps([{
        "packet_id": "src-one", "source": {"url": "https://example.test/doc"},
    }])
    digest = hashlib.sha256(packets.encode()).hexdigest()
    evidence = repo / "evidence"
    evidence.mkdir()
    audit = evidence / "audit.json"
    audit.write_text(json.dumps({
        "snapshot": "abc", "outcome": "CONVERGED", "selected": "decimal",
        "cleaning": "attested", "refs_moved": False,
        "phase_attempts": [
            {"role": "cleaner", "invoked": True},
            {"role": "attester", "invoked": True},
        ],
        "research": {
            "digest": digest,
            "packets": packets,
            "runs": [
                {"engine": "codex", "calls": 1, "attempts": [{"invoked": True}]},
                {"engine": "claude", "calls": 1, "attempts": [{"invoked": True}]},
            ],
        },
        "rounds": [{
            "codex": {"attempts": [{"invoked": True}], "decisive": "README.md:1"},
            "claude": {"attempts": [{"invoked": True}], "decisive": "SOURCE:src-one"},
        }],
    }))
    preceding_audit = evidence / "preceding.json"
    preceding_audit.write_text(json.dumps({
        "snapshot": "abc", "outcome": "FAILED", "reason": "provider failed",
        "cleaning": "attested-after-retry",
    }))
    artifact = tmp_path / "acceptance.json"
    artifact.write_text(json.dumps({
      "delivery_metrics": {
        "production_diff": {"files": 9, "lines_added": 9, "lines_removed": 0, "net_lines": 9},
        "largest_production_modules": sorted(
            ({"path": path, "lines": 1} for path in hashes), key=lambda row: row["path"],
        )[:6],
      },
      "primary_path": {
        "audit": "evidence/audit.json", "result": "CONVERGED", "selected": "decimal",
        "snapshot": "abc", "source_commit": source_commit,
        "research_digest": digest, "cleaning": "attested",
        "rounds": 1, "refs_moved": False,
        "captured_packets": ["src-one"],
        "captured_urls": ["https://example.test/doc"],
        "decisive_evidence": {
            "codex": "README.md:1", "claude": "SOURCE:src-one",
        },
        "production_source_sha256": hashes,
        "model_calls": {
            "research": {"codex": 1, "claude": 1},
            "deciders": {"codex": 1, "claude": 1},
            "cleaner": 1, "attester": 1, "total": 6,
        },
        "audit_reconciliation": {
            "audit_sha256": _sha(audit),
            "research_attempts": {"codex": 1, "claude": 1},
            "framing_attempts": 2, "decider_attempts": 2,
            "total_provider_calls": 6, "packet_count": 1,
            "packet_digest_matches": True, "packet_ids_match": True,
            "production_hashes_match": True,
        },
        "preceding_failed_closed_attempt": {
            "audit": "evidence/preceding.json", "audit_sha256": _sha(preceding_audit),
            "result": "FAILED", "reason": "provider failed",
            "cleaning": "attested-after-retry", "snapshot": "abc",
        },
    }}))
    subprocess.run(["git", "add", "evidence"], cwd=repo, check=True)
    return artifact, repo


def test_legacy_validator_has_no_raw_git_subprocess_boundary() -> None:
    assert not hasattr(legacy_validator, "subprocess")


def test_legacy_validator_rejects_a_missing_source_object_before_blob_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    data["primary_path"]["source_commit"] = "0" * 40
    artifact.write_text(json.dumps(data))
    calls: list[list[str]] = []
    invoke = legacy_validator.inert_git.invoke

    def recording_invoke(path: Path, args: list[str]):
        calls.append(list(args))
        return invoke(path, args)

    monkeypatch.setattr(legacy_validator.inert_git, "invoke", recording_invoke)
    with pytest.raises(ValueError, match="inert Git read failed"):
        legacy_validator.validate(artifact, repo)
    assert ["rev-parse", "--verify", f"{'0' * 40}^{{commit}}"] in calls
    assert not any(args and args[0] == "show" for args in calls)


def cleaning_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "cleaning-repo"
    repo.mkdir()
    evidence = repo / "evidence"
    evidence.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repo, check=True)
    for relative in validator.CLEANING_SOURCES:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("base\n")
    for index in range(3):
        (repo / "src" / "paranoia_local" / f"extra_{index}.py").write_text(
            "# fixture module\n"
        )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "base"],
        cwd=repo,
        check=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["git", "switch", "-qc", "feature"], cwd=repo, check=True)
    changed = repo / next(iter(validator.CLEANING_SOURCES))
    changed.write_text("base\nchanged\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "change"],
        cwd=repo,
        check=True,
    )
    hashes = {relative: _sha(repo / relative) for relative in validator.CLEANING_SOURCES}
    fixture_relative = "docs/cleaning_attestation_evidence/acceptance_fixture.py"
    fixture_path = repo / fixture_relative
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        (Path(__file__).parents[1] / fixture_relative).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    fixture_namespace = runpy.run_path(str(fixture_path))
    with fixture_namespace["repository_fixture"]() as fixture_repo:
        fixture_snapshot = validator.production_arbitrate._snapshot(fixture_repo)

    context = "shared\ncontext\n"
    options = {"one": "first", "two": "second"}
    detail = '{"one":{"original":"first","cleaned":"changed first","change":"narrowed","reason":"one: narrowed"}}'
    def phases(count: int) -> list[dict]:
        rows = []
        for attempt in range(1, count + 1):
            for role in ("cleaner", "attester"):
                reply = (
                    f"FIDELITY: decision PRESERVED; one CHANGED; two PRESERVED\nFIDELITY-DETAIL: {detail}\nNEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE"
                    if role == "attester" else (
                        "=== DECISION ===\ndecision\n\n=== OPTIONS ===\n"
                        "one: changed first\ntwo: second\n\n=== CONTEXT ===\n"
                        "shared context\n\n=== HINTS ===\nNone."
                    )
                )
                prompt_excerpt = f"attempt {attempt} {role} prompt"
                rows.append({
                    "role": role, "attempt": attempt, "status": "provider-completed",
                    "admitted": True, "invoked": True,
                    "prompt_sha256": hashlib.sha256(prompt_excerpt.encode()).hexdigest(),
                    "prompt_excerpt": prompt_excerpt, "reply": reply,
                    "reply_sha256": hashlib.sha256(reply.encode()).hexdigest(),
                    "rejection": (
                        f"fidelity changed: ['one']; detail: {detail}; neutrality: PASS"
                        if role == "attester" else None
                    ),
                })
        return rows
    positive_phases = phases(1)
    positive_phases[-1]["reply"] = (
        "FIDELITY: decision PRESERVED; one PRESERVED; two PRESERVED\nFIDELITY-DETAIL: NONE\n"
        "NEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE"
    )
    positive_phases[-1]["reply_sha256"] = hashlib.sha256(
        positive_phases[-1]["reply"].encode()
    ).hexdigest()
    positive_phases[-1]["rejection"] = None
    def cleaned_record() -> dict:
        fields = {
            "decision": "decision", "context": context, "hints": [],
            "statements": {"one": "changed first", "two": "second"},
        }
        encoded = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {**fields, "sha256": hashlib.sha256(encoded.encode()).hexdigest()}

    label_maps = {
        "codex": {"OPTION-1111111111111111": "one", "OPTION-2222222222222222": "two"},
        "claude": {"OPTION-3333333333333333": "two", "OPTION-4444444444444444": "one"},
    }
    def round_record(
        cleaning: str, attestation: str, selections: dict[str, str] | None = None,
    ) -> dict:
        cleaned = cleaned_record()
        packet = validator.production_arbitrate.Packet(
            decision=cleaned["decision"], stakes="stakes", context=cleaned["context"],
            hints=[], statements=cleaned["statements"], cleaning=cleaning,
            attestation=attestation,
        )
        result = {}
        for engine, mapping in label_maps.items():
            presentation = validator.production_protocol.Presentation(
                engine=engine,
                items=tuple((label, cleaned["statements"][option_id]) for label, option_id in mapping.items()),
                label_to_id=mapping,
                id_to_label={option_id: label for label, option_id in mapping.items()},
                reversed_order=False,
            )
            selected = (selections or {}).get(engine, "one")
            selected_label = next(label for label, option_id in mapping.items() if option_id == selected)
            reply = (
                "The tracked fixture states the governing acceptance fact.\n\n"
                f"SELECTED: {selected_label}\nSELECTED-RISK: NONE\nAUTHORITY: technical\n"
                "NEW-OPTION: NONE\nCONSTRAINT: fixture evidence\n"
                "PUBLISHER-AUTHORITY: N/A\nPASSAGE-ENTAILMENT: N/A\nDECISION-RELEVANCE: N/A\n"
                "DECISIVE-CITATION: README.md:3\nCITATIONS: NONE"
            )
            vote = validator.production_protocol.parse_verdict(reply, presentation)
            body = validator.production_arbitrate.render_decider_body(packet, presentation)
            prompt = validator.production_prompts.compose(
                validator.production_prompts.ARBITRATE_INSTRUCTIONS, body,
            )
            result[engine] = {
                **validator.production_arbitrate._vote_record(vote),
                "prompt": body, "reply": reply, "attempts": [{
                    "body": body, "raw": reply, "rejection": None,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "prompt_excerpt": validator.production_arbitrate._bounded_research_text(prompt),
                    "failure": None, "status": "provider-completed",
                    "admitted": True, "invoked": True,
                }],
            }
        return result

    positive = evidence / "positive.json"
    positive.write_text(json.dumps({
        "outcome": "CONVERGED", "selected": "one", "cleaning": "attested",
        "snapshot": fixture_snapshot, "refs_moved": False,
        "raw_input": {"decision": "decision", "stakes": "stakes", "context": context, "options": options, "files": []},
        "cleaned": cleaned_record(),
        "attestation": positive_phases[-1]["reply"],
        "research": {"enabled": False, "digest": None, "packets": None, "runs": []},
        "phase_attempts": positive_phases,
        "label_maps": label_maps,
        "reason": "unanimous, unblocked, substantiated",
        "rounds": [round_record("attested", positive_phases[-1]["reply"])],
    }))
    positive_data = json.loads(positive.read_text())
    _bind_phase_prompts(positive_data)
    positive.write_text(json.dumps(positive_data))
    original = evidence / "original.json"
    original_phases = phases(2)
    original_phases[-1]["reply"] = (
        "FIDELITY: decision PRESERVED; one PRESERVED; two PRESERVED\nFIDELITY-DETAIL: NONE\n"
        "NEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE"
    )
    original_phases[-1]["reply_sha256"] = hashlib.sha256(
        original_phases[-1]["reply"].encode()
    ).hexdigest()
    original_phases[-1]["rejection"] = None
    original.write_text(json.dumps({
        "outcome": "UNRESOLVED", "selected": None, "cleaning": "attested-after-retry",
        "snapshot": fixture_snapshot, "refs_moved": False,
        "reason": "codex selected one; claude selected two",
        "raw_input": {"decision": "decision", "stakes": "stakes", "context": context, "options": options, "files": []},
        "cleaned": cleaned_record(), "phase_attempts": original_phases,
        "attestation": original_phases[-1]["reply"],
        "label_maps": label_maps,
        "rounds": [round_record(
            "attested-after-retry", original_phases[-1]["reply"],
            {"codex": "one", "claude": "two"},
        )],
        "research": {"enabled": False, "digest": None, "packets": None, "runs": []},
    }))
    original_data = json.loads(original.read_text())
    _bind_phase_prompts(original_data)
    original.write_text(json.dumps(original_data))
    timing = evidence / "timing.json"
    timing.write_text(json.dumps({
        "positive": {
            "command": ["{python}", "docs/cleaning_attestation_evidence/run_positive_acceptance.py"], "started_utc": "2026-01-01T00:00:00Z",
            "finished_utc": "2026-01-01T00:00:12Z", "monotonic_elapsed_seconds": 12.0,
            "exit_status": 0, "audit": "evidence/positive.json", "audit_sha256": _sha(positive),
        },
        "original": {
            "command": ["{python}", "docs/cleaning_attestation_evidence/run_original_acceptance.py"], "started_utc": "2026-01-01T00:01:00Z",
            "finished_utc": "2026-01-01T00:01:08Z", "monotonic_elapsed_seconds": 8.0,
            "exit_status": 0, "audit": "evidence/original.json", "audit_sha256": _sha(original),
        },
    }))
    focused_log = evidence / "focused-tests.log"
    focused_log.write_text("200 passed in 20.00s\n")
    full_log = evidence / "full-tests.log"
    full_log.write_text("900 passed in 50.00s\n")
    test_manifest = evidence / "test-runner.json"
    test_manifest.write_text(json.dumps({
        "focused": {
            "command": ["{python}", "-m", "pytest", "-q", "tests/test_arbitrate_handler.py", "tests/test_acceptance_validator.py"],
            "started_utc": "2026-01-01T00:02:00Z", "finished_utc": "2026-01-01T00:02:20Z",
            "monotonic_elapsed_seconds": 20.0, "exit_status": 0,
            "log": "evidence/focused-tests.log", "log_sha256": _sha(focused_log),
            "terminal": "200 passed in 20.00s",
        },
        "full": {
            "command": ["{python}", "-m", "pytest", "-q"],
            "started_utc": "2026-01-01T00:03:00Z", "finished_utc": "2026-01-01T00:03:50Z",
            "monotonic_elapsed_seconds": 50.0, "exit_status": 0,
            "log": "evidence/full-tests.log", "log_sha256": _sha(full_log),
            "terminal": "900 passed in 50.00s",
        },
    }))
    runner_paths = {
        "wrapper": "docs/cleaning_attestation_evidence/run_timed_acceptances.py",
        "original": "docs/cleaning_attestation_evidence/run_original_acceptance.py",
        "positive": "docs/cleaning_attestation_evidence/run_positive_acceptance.py",
        "fixture": "docs/cleaning_attestation_evidence/acceptance_fixture.py",
        "tests": "scripts/run_cleaning_acceptance_checks.py",
        "validator": "scripts/validate_cleaning_attestation_acceptance.py",
    }
    runner_sources = {}
    for name, relative in runner_paths.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if name != "fixture":
            path.write_text(f"# {name} runner fixture\n")
        runner_sources[name] = {"path": relative, "sha256": _sha(path)}
    subprocess.run(["git", "add", "evidence", "docs", "scripts"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--amend", "--no-edit", "-q"],
        cwd=repo, check=True,
    )
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    diff_rows = subprocess.run(
        ["git", "diff", "--numstat", f"{base}..HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    diff_added = sum(int(row.split("\t", 2)[0]) for row in diff_rows)
    diff_removed = sum(int(row.split("\t", 2)[1]) for row in diff_rows)
    modules = sorted(
        ({"path": str(path.relative_to(repo)), "lines": len(path.read_text().splitlines())}
         for path in (repo / "src" / "paranoia_local").glob("*.py")),
        key=lambda row: (-row["lines"], row["path"]),
    )
    artifact = tmp_path / "cleaning-acceptance.json"
    artifact.write_text(json.dumps({
        "acceptance_kind": "cleaning-attestation-v1",
        "source_commit": source_commit,
        "acceptance_scope": {
            "proves": [
                "caller context and normalized options reached both deciders in the recorded runs",
                "cleaner and attester lifecycle, prompts, replies, diagnostics, and call counts match the audits",
                "the recorded production result and selection are reproduced from the checked-in audits",
            ],
            "does_not_prove": [
                "that a resolved repository citation entails a decider constraint",
                "that the positive fixture independently substantiates the selected option",
                "that the original run exercised agreed-but-unsubstantiated fail-closed behavior",
            ],
        },
        "production_source_sha256": hashes,
        "delivery_metrics": {
            "diff_base": base,
            "production_diff": {"files": 1, "lines_added": 1, "lines_removed": 0, "net_lines": 1},
            "all_changed_files_diff": {"files": len(diff_rows), "lines_added": diff_added, "lines_removed": diff_removed, "net_lines": diff_added - diff_removed},
            "largest_production_modules": modules,
            "model_calls": {
                "positive": {"cleaner": 1, "attester": 1, "codex_decider": 1, "claude_decider": 1, "total": 4},
                "original_input": {"cleaner": 2, "attester": 2, "codex_decider": 1, "claude_decider": 1, "total": 6},
            },
        },
        "positive_long_context": {
            "audit": "evidence/positive.json", "audit_sha256": _sha(positive), "result": "CONVERGED",
            "selected": "one", "cleaning": "attested", "snapshot": fixture_snapshot,
            "outcome_basis": "observed unanimous production result; citation entailment not independently attested",
            "refs_moved": False, "context_chars": len(context),
            "options": options, "rounds": 1, "research": "repository-only",
            "attestation": positive_phases[-1]["reply"].splitlines(),
        },
        "original_report_input": {
            "audit": "evidence/original.json", "audit_sha256": _sha(original), "result": "UNRESOLVED",
            "selected": None, "cleaning": "attested-after-retry", "snapshot": fixture_snapshot,
            "outcome_basis": "decider selection divergence",
            "refs_moved": False, "context_chars": len(context),
            "options": options, "rounds": 1, "research": "repository-only",
            "attestation": original_phases[-1]["reply"].splitlines(),
            "reason": "codex selected one; claude selected two",
        },
        "timing_record": {"path": "evidence/timing.json", "sha256": _sha(timing), "runs": json.loads(timing.read_text()), "runner_sources": runner_sources},
        "tests": {
            "focused_log": "evidence/focused-tests.log", "focused_log_sha256": _sha(focused_log),
            "focused_result": "200 passed in 20.00s", "focused_exit_status": 0,
            "full_log": "evidence/full-tests.log", "full_log_sha256": _sha(full_log),
            "full_result": "900 passed in 50.00s", "full_exit_status": 0,
            "runner_manifest": "evidence/test-runner.json", "runner_manifest_sha256": _sha(test_manifest),
        },
    }))
    return artifact, repo


def test_cleaning_acceptance_reconciles_both_audits_metrics_timing_and_tests(tmp_path: Path):
    artifact, repo = cleaning_fixture(tmp_path)
    validator.validate(artifact, repo)


def test_cleaning_acceptance_rejects_context_not_preserved(tmp_path: Path):
    artifact, repo = cleaning_fixture(tmp_path)
    data = json.loads(artifact.read_text())
    audit_path = repo / data["positive_long_context"]["audit"]
    audit = json.loads(audit_path.read_text())
    audit["cleaned"]["context"] = "rewritten"
    audit_path.write_text(json.dumps(audit))
    data["positive_long_context"]["audit_sha256"] = _sha(audit_path)
    artifact.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="positive context equality"):
        validator.validate(artifact, repo)


def test_cleaning_acceptance_rejects_cleaned_packet_digest_drift(tmp_path: Path):
    artifact, repo = cleaning_fixture(tmp_path)
    data = json.loads(artifact.read_text())
    audit_path = repo / data["positive_long_context"]["audit"]
    audit = json.loads(audit_path.read_text())
    audit["cleaned"]["sha256"] = "0" * 64
    audit_path.write_text(json.dumps(audit))
    data["positive_long_context"]["audit_sha256"] = _sha(audit_path)
    artifact.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="positive cleaned packet"):
        validator.validate(artifact, repo)


def test_cleaning_acceptance_rejects_omitted_attester_field(tmp_path: Path):
    artifact, repo = cleaning_fixture(tmp_path)
    data = json.loads(artifact.read_text())
    audit_path = repo / data["positive_long_context"]["audit"]
    audit = json.loads(audit_path.read_text())
    reply = audit["attestation"].replace("; two PRESERVED", "")
    audit["attestation"] = reply
    audit["phase_attempts"][-1]["reply"] = reply
    audit["phase_attempts"][-1]["reply_sha256"] = hashlib.sha256(reply.encode()).hexdigest()
    audit_path.write_text(json.dumps(audit))
    data["positive_long_context"]["attestation"] = reply.splitlines()
    data["positive_long_context"]["audit_sha256"] = _sha(audit_path)
    artifact.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="positive diagnostics"):
        validator.validate(artifact, repo)


def test_phase_diagnostics_bind_neutrality_only_rejection(tmp_path: Path):
    artifact, repo = cleaning_fixture(tmp_path)
    data = json.loads(artifact.read_text())
    audit = json.loads((repo / data["original_report_input"]["audit"]).read_text())
    reply = (
        "FIDELITY: decision PRESERVED; one PRESERVED; two PRESERVED\n"
        "FIDELITY-DETAIL: NONE\nNEUTRALITY: FAIL one through biased words\n"
        "STAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE"
    )
    audit["attestation"] = reply
    audit["phase_attempts"][-1]["reply"] = reply
    audit["phase_attempts"][-1]["reply_sha256"] = hashlib.sha256(reply.encode()).hexdigest()
    audit["phase_attempts"][-1]["rejection"] = "generic"
    assert not validator._phase_diagnostics_bound(audit, accepted=False)
    audit["phase_attempts"][-1]["rejection"] = (
        "fidelity changed: []; detail: NONE; neutrality: FAIL one through biased words"
    )
    assert validator._phase_diagnostics_bound(audit, accepted=False)


@pytest.mark.parametrize(
    "line",
    [
        "NEUTRALITY: FAILURE biased words",
        "STAKES-ADVOCACY: PRESENTLY biased words",
        "CONTEXT-ADVOCACY: PRESENTATION biased words",
    ],
)
def test_v1_attestation_requires_complete_verdict_tokens(line: str):
    rows = [
        "FIDELITY: decision PRESERVED",
        "FIDELITY-DETAIL: NONE",
        "NEUTRALITY: PASS",
        "STAKES-ADVOCACY: NONE",
        "CONTEXT-ADVOCACY: NONE",
    ]
    prefix = line.split(":", 1)[0] + ":"
    index = next(i for i, row in enumerate(rows) if row.startswith(prefix))
    rows[index] = line
    with pytest.raises(validator.production_arbitrate.ArbitrationError):
        validator._parse_attestation_record(
            "\n".join(rows), {"decision": ("original", "cleaned")},
        )


def test_phase_diagnostics_reject_identical_passages(tmp_path: Path):
    artifact, repo = cleaning_fixture(tmp_path)
    data = json.loads(artifact.read_text())
    audit = json.loads((repo / data["original_report_input"]["audit"]).read_text())
    row = audit["phase_attempts"][1]
    detail = '{"one":{"original":"first","cleaned":"first","change":"narrowed","reason":"one: narrowed"}}'
    row["reply"] = (
        f"FIDELITY: decision PRESERVED; one CHANGED; two PRESERVED\nFIDELITY-DETAIL: {detail}\n"
        "NEUTRALITY: PASS\nSTAKES-ADVOCACY: NONE\nCONTEXT-ADVOCACY: NONE"
    )
    row["reply_sha256"] = hashlib.sha256(row["reply"].encode()).hexdigest()
    row["rejection"] = f"fidelity changed: ['one']; detail: {detail}; neutrality: PASS"
    assert not validator._phase_diagnostics_bound(audit)


def test_cleaning_acceptance_rejects_inconsistent_timing_boundaries(tmp_path: Path):
    artifact, repo = cleaning_fixture(tmp_path)
    data = json.loads(artifact.read_text())
    timing_path = repo / data["timing_record"]["path"]
    timing = json.loads(timing_path.read_text())
    timing["positive"]["monotonic_elapsed_seconds"] = 3.0
    timing_path.write_text(json.dumps(timing))
    data["timing_record"].update({"sha256": _sha(timing_path), "runs": timing})
    artifact.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="wall and monotonic durations disagree"):
        validator.validate(artifact, repo)


@pytest.mark.parametrize(("mutation", "message"), [
    ("scope", "acceptance claim scope"),
    ("outcome_basis", "positive outcome basis"),
    ("options", "positive option mapping"),
    ("rounds", "positive rounds"),
    ("research", "positive research"),
    ("reason", "original reason"),
    ("attestation", "positive attestation"),
    ("calls", "positive total"),
    ("timing", "timing record"),
    ("tests", "full test result"),
    ("production_diff", "production diff metrics"),
    ("modules", "largest production modules"),
    ("source", "production hash mismatch"),
    ("diagnostic", "original diagnostics"),
    ("phase_schema", "positive diagnostics"),
    ("reply_digest", "positive diagnostics"),
    ("prompt_binding", "positive prompt bindings"),
    ("v2_prompt_v1_reply", "positive prompt bindings"),
    ("attestation_order", "positive diagnostics"),
    ("derived_outcome", "positive derived outcome"),
    ("decider_lifecycle", "positive derived outcome"),
    ("cleaner_rejection", "positive diagnostics"),
    ("unjustified_retry", "original diagnostics"),
    ("boolean_count", "positive model-call numeric schema"),
    ("extra_count_key", "positive model-call numeric schema"),
    ("test_exit", "full test exit status"),
    ("timing_command", "positive timing boundary"),
    ("test_command", "focused test runner record mismatch"),
    ("diff_base", "delivery diff base"),
    ("runner_role", "live runner source digest mismatch"),
])
def test_cleaning_acceptance_rejects_each_claim_family(
    tmp_path: Path, mutation: str, message: str,
):
    artifact, repo = cleaning_fixture(tmp_path)
    data = json.loads(artifact.read_text())
    if mutation == "scope":
        data["acceptance_scope"]["does_not_prove"].pop()
    elif mutation == "outcome_basis":
        data["positive_long_context"]["outcome_basis"] = "independently substantiated"
    elif mutation == "options":
        data["positive_long_context"]["options"]["one"] = "different"
    elif mutation == "rounds":
        data["positive_long_context"]["rounds"] = 2
    elif mutation == "research":
        data["positive_long_context"]["research"] = "not reached"
    elif mutation == "reason":
        data["original_report_input"]["reason"] = "different"
    elif mutation == "attestation":
        data["positive_long_context"]["attestation"].pop()
    elif mutation == "calls":
        data["delivery_metrics"]["model_calls"]["positive"]["total"] = 3
    elif mutation == "timing":
        data["timing_record"]["runs"]["positive"]["monotonic_elapsed_seconds"] = 99
    elif mutation == "tests":
        data["tests"]["full_result"] = "901 passed"
    elif mutation == "production_diff":
        data["delivery_metrics"]["production_diff"]["lines_added"] = 2
    elif mutation == "modules":
        data["delivery_metrics"]["largest_production_modules"][0]["lines"] += 1
    elif mutation == "source":
        key = next(iter(data["production_source_sha256"]))
        data["production_source_sha256"][key] = "0" * 64
    elif mutation == "diagnostic":
        audit_path = repo / data["original_report_input"]["audit"]
        audit = json.loads(audit_path.read_text())
        next(row for row in audit["phase_attempts"] if row["role"] == "attester")["rejection"] = "generic"
        audit_path.write_text(json.dumps(audit))
        data["original_report_input"]["audit_sha256"] = _sha(audit_path)
    elif mutation in {
        "phase_schema", "reply_digest", "prompt_binding", "v2_prompt_v1_reply",
        "attestation_order",
    }:
        audit_path = repo / data["positive_long_context"]["audit"]
        audit = json.loads(audit_path.read_text())
        if mutation == "phase_schema":
            audit["phase_attempts"][0].pop("status")
        elif mutation == "reply_digest":
            audit["phase_attempts"][0]["reply_sha256"] = "0" * 64
        elif mutation == "prompt_binding":
            audit["phase_attempts"][0]["prompt_excerpt"] = "invented prompt"
            audit["phase_attempts"][0]["prompt_sha256"] = hashlib.sha256(
                b"invented prompt"
            ).hexdigest()
        elif mutation == "v2_prompt_v1_reply":
            raw = audit["raw_input"]
            cleaner = audit["phase_attempts"][0]
            attester = audit["phase_attempts"][1]
            parsed = validator.production_arbitrate.parse_cleaned_packet(
                cleaner["reply"], list(raw["options"]),
                caller_gave_context=bool(raw["context"]),
            )
            parsed["context"] = raw["context"]
            hints = validator.production_arbitrate._merge_hints(raw["files"], parsed["hints"])
            body = validator.production_arbitrate._attest_body(
                raw["decision"], raw["stakes"], raw["context"], raw["files"],
                hints, raw["options"], parsed,
            )
            prompt = validator.production_prompts.compose(
                validator.production_prompts.ATTEST_INSTRUCTIONS, body,
            )
            attester["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
            attester["prompt_excerpt"] = validator.production_arbitrate._bounded_research_text(
                prompt
            )
        else:
            attester = audit["phase_attempts"][-1]
            lines = attester["reply"].splitlines()
            lines[0], lines[1] = lines[1], lines[0]
            attester["reply"] = "\n".join(lines)
            attester["reply_sha256"] = hashlib.sha256(
                attester["reply"].encode()
            ).hexdigest()
            audit["attestation"] = attester["reply"]
            data["positive_long_context"]["attestation"] = lines
        audit_path.write_text(json.dumps(audit))
        data["positive_long_context"]["audit_sha256"] = _sha(audit_path)
    elif mutation == "derived_outcome":
        audit_path = repo / data["positive_long_context"]["audit"]
        audit = json.loads(audit_path.read_text())
        audit["outcome"] = "UNRESOLVED"
        audit["selected"] = None
        audit["reason"] = "invented disagreement"
        audit_path.write_text(json.dumps(audit))
        data["positive_long_context"].update({
            "audit_sha256": _sha(audit_path), "result": "UNRESOLVED", "selected": None,
        })
    elif mutation == "decider_lifecycle":
        audit_path = repo / data["positive_long_context"]["audit"]
        audit = json.loads(audit_path.read_text())
        audit["rounds"][0]["codex"]["attempts"][0].update({
            "admitted": False, "invoked": False,
        })
        audit_path.write_text(json.dumps(audit))
        data["positive_long_context"]["audit_sha256"] = _sha(audit_path)
        data["delivery_metrics"]["model_calls"]["positive"].update({
            "codex_decider": 0, "total": 3,
        })
    elif mutation == "cleaner_rejection":
        audit_path = repo / data["positive_long_context"]["audit"]
        audit = json.loads(audit_path.read_text())
        audit["phase_attempts"][0]["rejection"] = "fabricated cleaner rejection"
        audit_path.write_text(json.dumps(audit))
        data["positive_long_context"]["audit_sha256"] = _sha(audit_path)
    elif mutation == "unjustified_retry":
        audit_path = repo / data["original_report_input"]["audit"]
        audit = json.loads(audit_path.read_text())
        audit["phase_attempts"][1]["rejection"] = None
        audit_path.write_text(json.dumps(audit))
        data["original_report_input"]["audit_sha256"] = _sha(audit_path)
    elif mutation == "boolean_count":
        data["delivery_metrics"]["model_calls"]["positive"]["cleaner"] = True
    elif mutation == "extra_count_key":
        data["delivery_metrics"]["model_calls"]["positive"]["invented"] = 0
    elif mutation == "test_exit":
        data["tests"]["full_exit_status"] = 1
    elif mutation == "timing_command":
        timing_path = repo / data["timing_record"]["path"]
        timing = json.loads(timing_path.read_text())
        timing["positive"]["command"] = ["true"]
        timing_path.write_text(json.dumps(timing))
        data["timing_record"]["sha256"] = _sha(timing_path)
        data["timing_record"]["runs"] = timing
    elif mutation == "test_command":
        manifest_path = repo / data["tests"]["runner_manifest"]
        manifest = json.loads(manifest_path.read_text())
        manifest["focused"]["command"] = ["true"]
        manifest_path.write_text(json.dumps(manifest))
        data["tests"]["runner_manifest_sha256"] = _sha(manifest_path)
    elif mutation == "diff_base":
        data["delivery_metrics"]["diff_base"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        data["delivery_metrics"]["production_diff"] = {
            "files": 0, "lines_added": 0, "lines_removed": 0, "net_lines": 0,
        }
        data["delivery_metrics"]["all_changed_files_diff"] = dict(
            data["delivery_metrics"]["production_diff"]
        )
    elif mutation == "runner_role":
        source = repo / "README.md"
        source.write_text("tracked runner impostor\n")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "commit", "--amend", "--no-edit", "-q"],
            cwd=repo, check=True,
        )
        data["timing_record"]["runner_sources"]["wrapper"] = {
            "path": "README.md", "sha256": _sha(source),
        }
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match=message):
        validator.validate(artifact, repo)


def test_acceptance_validator_reconciles_audit_and_sources(tmp_path: Path):
    artifact, repo = fixture(tmp_path)
    legacy_validator.validate(artifact, repo)


def test_acceptance_validator_reconciles_one_framing_retry(tmp_path: Path):
    artifact, repo = fixture(tmp_path)
    acceptance = json.loads(artifact.read_text())
    audit_path = repo / acceptance["primary_path"]["audit"]
    audit = json.loads(audit_path.read_text())
    audit["phase_attempts"] += [
        {"role": "cleaner", "invoked": True},
        {"role": "attester", "invoked": True},
    ]
    audit["cleaning"] = "attested-after-retry"
    audit_path.write_text(json.dumps(audit))
    primary = acceptance["primary_path"]
    primary["audit_reconciliation"]["audit_sha256"] = _sha(audit_path)
    primary["audit_reconciliation"]["framing_attempts"] = 4
    primary["audit_reconciliation"]["total_provider_calls"] = 8
    primary["model_calls"].update({"cleaner": 2, "attester": 2, "total": 8})
    primary["cleaning"] = "attested-after-retry"
    artifact.write_text(json.dumps(acceptance))

    legacy_validator.validate(artifact, repo)


def test_acceptance_validator_rejects_a_self_asserted_stale_total(tmp_path: Path):
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    data["primary_path"]["model_calls"]["total"] = 5
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="total calls"):
        legacy_validator.validate(artifact, repo)


@pytest.mark.parametrize(("mutation", "message"), [
    (lambda a, d: a.__setitem__("invented", {}), "top-level schema"),
    (lambda a, d: a["delivery_metrics"].__setitem__("invented", {}), "delivery metrics schema"),
    (lambda a, d: a["delivery_metrics"]["production_diff"].__setitem__("lines_added", 10), "production diff metrics"),
    (lambda a, d: a["delivery_metrics"]["largest_production_modules"][0].__setitem__("lines", 2), "largest production modules"),
    (lambda a, d: a["primary_path"].__setitem__("invented", None), "primary-path schema"),
    (lambda a, d: a["primary_path"]["model_calls"].__setitem__("invented", 0), "model-call schema"),
    (lambda a, d: a["primary_path"].__setitem__("rounds", True), "round count schema"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("invented", 0), "reconciliation schema"),
    (lambda a, d: a["primary_path"]["preceding_failed_closed_attempt"].__setitem__("invented", None), "preceding-attempt schema"),
    (lambda a, d: a["primary_path"]["captured_packets"].append("src-two"), "packet count"),
    (lambda a, d: a["primary_path"]["captured_packets"].__setitem__(0, "src-two"), "packet ids"),
    (lambda a, d: a["primary_path"].__setitem__("research_digest", "stale"), "packet digest"),
    (lambda a, d: a["primary_path"]["captured_urls"].clear(), "packet urls"),
    (lambda a, d: a["primary_path"]["decisive_evidence"].__setitem__("codex", "README.md:2"), "decisive evidence"),
    (lambda a, d: a["primary_path"]["model_calls"].__setitem__("cleaner", 0), "cleaner attempts"),
    (lambda a, d: a["primary_path"]["model_calls"].__setitem__("attester", 0), "attester attempts"),
    (lambda a, d: a["primary_path"]["model_calls"]["research"].__setitem__("codex", 2), "research attempts"),
    (lambda a, d: a["primary_path"]["model_calls"]["deciders"].__setitem__("codex", 2), "decider attempts"),
    (lambda a, d: d["research"]["runs"].append(d["research"]["runs"][0]), "each engine exactly once"),
    (lambda a, d: d["research"]["runs"][0].__setitem__("calls", 2), "calls disagree"),
    (lambda a, d: d["research"]["runs"][0]["attempts"][0].__setitem__("invoked", "false"), "exact boolean"),
    (lambda a, d: a["primary_path"].__setitem__("result", "FAILED"), "audit outcome"),
    (lambda a, d: a["primary_path"].__setitem__("selected", "float"), "audit selection"),
    (lambda a, d: a["primary_path"].__setitem__("snapshot", "def"), "audit snapshot"),
    (lambda a, d: a["primary_path"].__setitem__("cleaning", "skipped"), "cleaning"),
    (lambda a, d: a["primary_path"].__setitem__("rounds", 99), "round count"),
    (lambda a, d: a["primary_path"].__setitem__("refs_moved", True), "refs moved"),
    (lambda a, d: a["primary_path"]["production_source_sha256"].pop(next(iter(validator.PRODUCTION_SOURCES))), "complete source set"),
    (lambda a, d: a["primary_path"]["production_source_sha256"].__setitem__(next(iter(validator.PRODUCTION_SOURCES)), "0" * 64), "production hash mismatch"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("packet_ids_match", False), "packet_ids_match"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("packet_digest_matches", False), "packet_digest_matches"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("production_hashes_match", False), "production_hashes_match"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("framing_attempts", 1), "framing_attempts"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("decider_attempts", 1), "decider_attempts"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"]["research_attempts"].__setitem__("codex", 2), "research_attempts"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("total_provider_calls", 5), "total_provider_calls"),
    (lambda a, d: a["primary_path"]["audit_reconciliation"].__setitem__("packet_count", 2), "packet_count"),
])
def test_acceptance_validator_rejects_each_independent_summary(
    tmp_path: Path, mutation, message: str,
):
    artifact, repo = fixture(tmp_path)
    acceptance = json.loads(artifact.read_text())
    audit_path = repo / acceptance["primary_path"]["audit"]
    audit = json.loads(audit_path.read_text())
    mutation(acceptance, audit)
    audit_path.write_text(json.dumps(audit))
    acceptance["primary_path"]["audit_reconciliation"]["audit_sha256"] = _sha(audit_path)
    artifact.write_text(json.dumps(acceptance))

    with pytest.raises(ValueError, match=message):
        legacy_validator.validate(artifact, repo)


def test_acceptance_validator_rejects_stale_audit_hash(tmp_path: Path):
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    data["primary_path"]["audit_reconciliation"]["audit_sha256"] = "0" * 64
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="audit_sha256"):
        legacy_validator.validate(artifact, repo)


@pytest.mark.parametrize(("field", "value", "message"), [
    ("audit_sha256", "0" * 64, "preceding audit digest"),
    ("result", "CONVERGED", "preceding result"),
    ("reason", "different", "preceding reason"),
    ("cleaning", "skipped", "preceding cleaning"),
    ("snapshot", "def", "preceding snapshot"),
])
def test_acceptance_validator_rejects_stale_preceding_failure(
    tmp_path: Path, field: str, value: str, message: str,
):
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    data["primary_path"]["preceding_failed_closed_attempt"][field] = value
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match=message):
        legacy_validator.validate(artifact, repo)


@pytest.mark.parametrize(("field", "value"), [
    ("result", []),
    ("selected", 7),
    ("snapshot", False),
    ("cleaning", {}),
    ("refs_moved", 0),
])
def test_acceptance_validator_rejects_coordinated_primary_wrong_types(
    tmp_path: Path, field: str, value: object,
):
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    audit_path = repo / data["primary_path"]["audit"]
    audit = json.loads(audit_path.read_text())
    audit_key = {"result": "outcome", "selected": "selected"}.get(field, field)
    data["primary_path"][field] = value
    audit[audit_key] = value
    audit_path.write_text(json.dumps(audit))
    data["primary_path"]["audit_reconciliation"]["audit_sha256"] = _sha(audit_path)
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="value schema|refs-moved schema"):
        legacy_validator.validate(artifact, repo)


@pytest.mark.parametrize("path", ["/tmp/audit.json", "../audit.json", "untracked.json"])
def test_acceptance_validator_rejects_non_repository_evidence(
    tmp_path: Path, path: str,
):
    artifact, repo = fixture(tmp_path)
    data = json.loads(artifact.read_text())
    data["primary_path"]["audit"] = path
    artifact.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="repository-relative|escapes repository|not tracked"):
        legacy_validator.validate(artifact, repo)
