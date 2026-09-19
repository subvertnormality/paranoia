from __future__ import annotations

import json
from pathlib import Path

import pytest

from paranoia_local import git_objects, inert_git
from paranoia_local import patch_proposals as pp


def target(key: str = "structural:D1") -> pp.ProposalTarget:
    return pp.ProposalTarget(key, "repair the validator", "MAJOR", ("repository/app.py:1",))


def entry(path: str, data: bytes, *, mode: str = "100644",
          kind: str = "file") -> pp.ProposalEntry:
    return pp.ProposalEntry(path, kind, mode, git_objects.blob_oid(data, 40))


def branch_context(data: bytes = b"value = 1\n", *, entries=None,
                   targets=None) -> tuple[pp.ProposalContext, pp.SourceReader]:
    rows = tuple(entries or (entry("app.py", data),))
    contents = {row.path: pp.SourceContent(data) for row in rows if row.kind in {"file", "executable"}}
    context = pp.ProposalContext(
        "branch", tuple(targets or (target(),)), "local stakes", "head", "snapshot", None,
        None, rows,
    )
    return context, lambda row: contents[row.path]


def plan_context(data: bytes = b"Always retry.\n", *, targets=None) -> pp.ProposalContext:
    return pp.ProposalContext(
        "plan", tuple(targets or (target(),)), "local stakes", "plan-snapshot", "structural",
        None, None, (), data, "digest", "plan_text", None,
    )


def response(*, edits, status="proposed", addressed=None, unaddressed=None,
             summary="candidate repair") -> str:
    return json.dumps({
        "schema_version": 1,
        "status": status,
        "summary": summary,
        "addressed_finding_ids": ["structural:D1"] if addressed is None else addressed,
        "unaddressed": [] if unaddressed is None else unaddressed,
        "edits": edits,
        "suggested_tests": ["Run focused tests."],
        "limitations": ["Tests were not executed."],
    })


def replace(path="app.py", old="value = 1\n", new="value = 2\n", *, target="repository"):
    return {"target": target, "operation": "replace", "path": path,
            "old_text": old, "new_text": new}


def test_schema_is_closed_and_provider_projection_preserves_required_fields():
    context, unused = branch_context()
    schema = pp.proposal_schema(context)
    projected = pp.provider_schema(context)
    assert schema["additionalProperties"] is False
    assert "uniqueItems" in schema["properties"]["addressed_finding_ids"]
    assert "uniqueItems" not in projected["properties"]["addressed_finding_ids"]
    assert set(projected["required"]) == set(projected["properties"])
    assert set(projected["properties"]["edits"]["items"]["required"]) == {
        "target", "operation", "path", "old_text", "new_text",
    }


@pytest.mark.parametrize("bad", [
    '{"schema_version":1,"schema_version":1}',
    '{"schema_version":1,"status":"declined","summary":"x",'
    '"addressed_finding_ids":[],"unaddressed":[{"finding_id":"structural:D1",'
    '"reason":"first","reason":"second"}],"edits":[],"suggested_tests":[],'
    '"limitations":[]}',
    '{"schema_version":true,"status":"declined","summary":"x",'
    '"addressed_finding_ids":[],"unaddressed":[],"edits":[],'
    '"suggested_tests":[],"limitations":[]}',
    '[]',
    '{} trailing',
])
def test_wire_rejects_duplicate_wrong_type_competing_and_trailing_json(bad):
    context, reader = branch_context()
    with pytest.raises(pp.ProposalError):
        pp.parse_and_render(context, bad, reader)


def test_partition_partial_and_decline_are_exact():
    targets = (target(), target("structural:D2"))
    context, reader = branch_context(targets=targets)
    partial = response(
        edits=[replace()], addressed=["structural:D1"],
        unaddressed=[{"finding_id": "structural:D2", "reason": "needs product input"}],
    )
    assert pp.parse_and_render(context, partial, reader).status == "partial"
    declined = response(
        edits=[], status="declined", addressed=[],
        unaddressed=[
            {"finding_id": "structural:D1", "reason": "unsupported"},
            {"finding_id": "structural:D2", "reason": "unsupported"},
        ],
    )
    result = pp.parse_and_render(context, declined, reader)
    assert result.status == "declined" and result.patch == b""
    with pytest.raises(pp.ProposalError, match="exactly partition"):
        pp.parse_and_render(context, response(edits=[replace()]), reader)


@pytest.mark.parametrize(("field", "value"), [
    ("summary", "   "),
    ("suggested_tests", ["\t"]),
    ("limitations", ["\n"]),
])
def test_semantic_text_must_be_nonblank(field, value):
    context, reader = branch_context()
    payload = json.loads(response(edits=[replace()]))
    payload[field] = value
    with pytest.raises(pp.ProposalError, match="semantic text must be nonblank"):
        pp.parse_and_render(context, json.dumps(payload), reader)


def test_raw_and_edit_strings_must_be_strict_utf8():
    context, reader = branch_context()
    with pytest.raises(pp.ProposalError, match="strict UTF-8"):
        pp.parse_and_render(context, "\ud800", reader)
    payload = json.loads(response(edits=[replace()]))
    payload["edits"][0]["new_text"] = "\ud800"
    with pytest.raises(pp.ProposalError, match="strict UTF-8"):
        pp.parse_and_render(context, json.dumps(payload, ensure_ascii=False), reader)


def test_replacements_use_original_spans_and_render_no_final_newline():
    data = b"first\nmiddle\nlast"
    context, reader = branch_context(data)
    raw = response(edits=[
        replace(old="first\n", new="FIRST\n"),
        replace(old="last", new="LAST"),
    ])
    result = pp.parse_and_render(context, raw, reader)
    assert result.files[0].proposed == b"FIRST\nmiddle\nLAST"
    assert b"\\ No newline at end of file\n" in result.patch
    assert result.patch_sha256 == __import__("hashlib").sha256(result.patch).hexdigest()


def test_adjacent_replacements_and_empty_replacement_are_valid():
    context, reader = branch_context(b"abc\n")
    result = pp.parse_and_render(context, response(edits=[
        replace(old="a", new="A"),
        replace(old="b", new=""),
        replace(old="c", new="C"),
    ]), reader)
    assert result.files[0].proposed == b"AC\n"


@pytest.mark.parametrize(("old", "new", "message"), [
    ("", "x", "nonempty"),
    ("value = 1\n", "value = 1\n", "no-op"),
    ("absent", "x", "occurs 0 times"),
])
def test_invalid_replacements_are_visible(old, new, message):
    context, reader = branch_context()
    with pytest.raises(pp.ProposalError, match=message):
        pp.parse_and_render(context, response(edits=[replace(old=old, new=new)]), reader)


def test_repeated_and_overlapping_old_text_reject():
    context, reader = branch_context(b"x x\n")
    with pytest.raises(pp.ProposalError, match="occurs 2 times"):
        pp.parse_and_render(context, response(edits=[replace(old="x", new="y")]), reader)
    context, reader = branch_context(b"abcdef\n")
    with pytest.raises(pp.ProposalError, match="overlaps"):
        pp.parse_and_render(context, response(edits=[
            replace(old="abc", new="x"), replace(old="bcde", new="y"),
        ]), reader)


@pytest.mark.parametrize("path", [
    "/abs.py", "../escape.py", "a\\b.py", "C:/drive.py", ".git/config",
    "src/:magic.py", "CON", "a//b.py", "odd name.py",
])
def test_path_grammar_rejects_unsafe_or_ambiguous_names(path):
    context, reader = branch_context()
    with pytest.raises(pp.ProposalError, match="path"):
        pp.parse_and_render(context, response(edits=[replace(path=path)]), reader)


def test_source_kinds_encoding_crlf_binary_and_identity_reject():
    for data, match in ((b"x\r\n", "CRLF"), (b"x\0y", "binary"), (b"\xff", "UTF-8")):
        context, reader = branch_context(data)
        with pytest.raises(pp.ProposalError, match=match):
            pp.parse_and_render(context, response(edits=[replace(old=data.decode("latin1"), new="x")]), reader)
    link = pp.ProposalEntry("app.py", "symlink", "120000", "0" * 40)
    context, reader = branch_context(entries=(link,))
    with pytest.raises(pp.ProposalError, match="unsupported kind"):
        pp.parse_and_render(context, response(edits=[replace()]), reader)


def test_blob_identity_aggregate_source_and_executable_mode_are_enforced(monkeypatch):
    data = b"value = 1\n"
    wrong = pp.ProposalEntry("app.py", "file", "100644", "0" * 40)
    context, reader = branch_context(data, entries=(wrong,))
    with pytest.raises(pp.ProposalError, match="blob identity mismatch"):
        pp.parse_and_render(context, response(edits=[replace()]), reader)

    executable = entry("app.py", data, mode="100755", kind="executable")
    context, reader = branch_context(data, entries=(executable,))
    result = pp.parse_and_render(context, response(edits=[replace()]), reader)
    assert result.files[0].mode == "100755"

    monkeypatch.setattr(pp, "MAX_SOURCE_BYTES", len(data) - 1)
    with pytest.raises(pp.ProposalError, match="source exceeds invocation byte limit"):
        pp.parse_and_render(context, response(edits=[replace()]), reader)


def test_checkout_divergence_is_named_without_rebasing():
    pinned = b"value = 1\n"
    context, unused = branch_context(pinned)
    reader = lambda row: pp.SourceContent(pinned, b"value = 1\r\n")
    raw = response(edits=[replace(old="value = 1\r\n", new="value = 2\r\n")])
    with pytest.raises(pp.ProposalError, match="checkout-view-diverged-from-pinned-blob"):
        pp.parse_and_render(context, raw, reader)


def test_create_requires_absence_safe_parent_and_nonempty_text():
    parent = pp.ProposalEntry("src", "directory", "040000")
    context, reader = branch_context(entries=(parent,))
    create = {"target": "repository", "operation": "create", "path": "src/new.py",
              "old_text": None, "new_text": "created = True\n"}
    result = pp.parse_and_render(context, response(edits=[create]), reader)
    assert result.files[0].mode == "100644"
    assert b"new file mode 100644" in result.patch
    existing, reader = branch_context()
    create["path"] = "app.py"
    with pytest.raises(pp.ProposalError, match="already exists"):
        pp.parse_and_render(existing, response(edits=[create]), reader)


def test_create_parent_path_and_case_collisions_reject():
    data = b"target\n"
    file_parent = entry("src", data)
    context, reader = branch_context(data, entries=(file_parent,))
    create = {"target": "repository", "operation": "create", "path": "src/new.py",
              "old_text": None, "new_text": "created = True\n"}
    with pytest.raises(pp.ProposalError, match="ancestor 'src' is not a directory"):
        pp.parse_and_render(context, response(edits=[create]), reader)
    symlink_parent = pp.ProposalEntry("src", "symlink", "120000", "0" * 40)
    context, reader = branch_context(data, entries=(symlink_parent,))
    with pytest.raises(pp.ProposalError, match="ancestor 'src' is not a directory"):
        pp.parse_and_render(context, response(edits=[create]), reader)

    upper = entry("Name.py", data)
    lower = entry("name.py", data)
    context, reader = branch_context(data, entries=(upper, lower))
    with pytest.raises(pp.ProposalError, match="ambiguous existing paths"):
        pp.parse_and_render(
            context,
            response(edits=[replace(path="name.py", old="target\n", new="changed\n")]),
            reader,
        )


def test_create_empty_and_gitlink_replace_reject():
    directory = pp.ProposalEntry("src", "directory", "040000")
    context, reader = branch_context(entries=(directory,))
    create = {"target": "repository", "operation": "create", "path": "src/new.py",
              "old_text": None, "new_text": ""}
    with pytest.raises(pp.ProposalError, match="created file must be nonempty"):
        pp.parse_and_render(context, response(edits=[create]), reader)
    gitlink = pp.ProposalEntry("app.py", "gitlink", "160000", "0" * 40)
    context, reader = branch_context(entries=(gitlink,))
    with pytest.raises(pp.ProposalError, match="unsupported kind gitlink"):
        pp.parse_and_render(context, response(edits=[replace()]), reader)


@pytest.mark.parametrize("field", ["mode", "rename_from", "delete"])
def test_model_cannot_request_mode_rename_or_delete(field):
    context, reader = branch_context()
    edit = replace()
    edit[field] = "unsupported"
    with pytest.raises(pp.ProposalError, match="Additional properties"):
        pp.parse_and_render(context, response(edits=[edit]), reader)


def test_raw_edit_and_rendered_patch_limits_fail_closed(monkeypatch):
    context, reader = branch_context()
    monkeypatch.setattr(pp, "MAX_RAW_BYTES", 32)
    with pytest.raises(pp.ProposalError, match="raw response exceeds"):
        pp.parse_and_render(context, response(edits=[replace()]), reader)

    monkeypatch.setattr(pp, "MAX_RAW_BYTES", 262_144)
    monkeypatch.setattr(pp, "MAX_EDIT_BYTES", 3)
    with pytest.raises(pp.ProposalError, match="replacement text exceeds"):
        pp.parse_and_render(context, response(edits=[replace()]), reader)

    monkeypatch.setattr(pp, "MAX_EDIT_BYTES", 131_072)
    monkeypatch.setattr(pp, "MAX_PATCH_BYTES", 20)
    with pytest.raises(pp.ProposalError, match="rendered patch exceeds"):
        pp.parse_and_render(context, response(edits=[replace()]), reader)


def test_plan_uses_exact_unnumbered_capture_and_virtual_label():
    context = plan_context(b"1. Always retry.\n")
    edit = replace(path=None, old="Always retry.", new="Retry documented failures.", target="plan")
    result = pp.parse_and_render(context, response(edits=[edit]))
    assert result.files[0].proposed == b"1. Retry documented failures.\n"
    assert b"plan-artifact.md" in result.patch
    assert b"1. Retry" in result.patch


def test_test_only_git_apply_reproduces_expected_bytes_and_modes(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    inert_git.run(repo, ["init", "-q"])
    inert_git.run(repo, ["config", "user.name", "fixture"])
    inert_git.run(repo, ["config", "user.email", "fixture@example.test"])
    (repo / "app.py").write_bytes(b"value = 1\n")
    inert_git.run(repo, ["add", "app.py"])
    inert_git.run(repo, ["-c", "commit.gpgsign=false", "commit", "-qm", "base"])
    context, reader = branch_context()
    create = {"target": "repository", "operation": "create", "path": "new.py",
              "old_text": None, "new_text": "created = True"}
    result = pp.parse_and_render(context, response(edits=[replace(), create]), reader)
    applied = inert_git.invoke(repo, ["apply", "--index", "-"], input_bytes=result.patch)
    assert applied.returncode == 0, applied.stderr
    assert (repo / "app.py").read_bytes() == b"value = 2\n"
    assert (repo / "new.py").read_bytes() == b"created = True"
    assert inert_git.text(repo, ["ls-files", "-s", "new.py"]).startswith("100644 ")


def test_prompt_contains_binding_targets_contract_and_exact_plan():
    context = pp.ProposalContext(
        "plan", (target(),), "stakes", "reviewed", "structural", "contract-digest",
        "requirement text", (), b"actual plan\n", "plan-digest", "plan_path", "/input/plan.md",
    )
    prompt = pp.render_prompt(context)
    assert "structural:D1" in prompt
    assert "contract-digest" in prompt
    assert "requirement text" in prompt
    assert "=== EXACT UNNUMBERED PLAN TEXT ===\nactual plan\n" in prompt
