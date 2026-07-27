"""Git-facing arbitration evidence: pinning limits, symlink escapes, label
clearance, and citation reads. Each case is a way the recorded snapshot could
fail to describe what the deciders actually read."""

from pathlib import Path

import pytest

from paranoia_local import evidence, orientation
from paranoia_local.arbitration import ArbitrationError, Citation

from .conftest import commit_all, git


def snapshot(repo: Path) -> str:
    head = orientation.resolve_head(repo)
    tree = orientation.snapshot_tree(repo, head)
    return orientation.wrap_commit(repo, tree, head)


# --- ref movement -----------------------------------------------------------


def test_refs_digest_changes_when_a_branch_advances(repo: Path):
    before = evidence.refs_digest(repo)
    (repo / "new.py").write_text("x = 1\n")
    commit_all(repo, "second")
    assert evidence.refs_digest(repo) != before


def test_refs_digest_is_stable_across_a_file_edit(repo: Path):
    """A working-tree edit is not ref movement — the snapshot already pins it."""
    before = evidence.refs_digest(repo)
    (repo / "app.py").write_text("changed\n")
    assert evidence.refs_digest(repo) == before


def test_advance_and_restore_is_still_detected(repo: Path):
    """Round-10 MAJOR: comparing ref TIPS alone is defeated by a rebase that lands
    and then resets inside the run window."""
    before = evidence.refs_digest(repo)
    original = orientation.resolve_head(repo)
    (repo / "transient.py").write_text("x = 1\n")
    commit_all(repo, "transient")
    git(["reset", "-q", "--hard", original], repo)
    assert orientation.resolve_head(repo) == original  # tip restored
    assert evidence.refs_digest(repo) != before  # but the reflog remembers


# --- symlinks ---------------------------------------------------------------


def test_in_tree_symlink_is_permitted(repo: Path):
    (repo / "alias.py").symlink_to("app.py")
    commit_all(repo, "add alias")
    commit = snapshot(repo)
    assert evidence.escaping_symlinks(repo, commit) == []


def test_absolute_symlink_escapes(repo: Path):
    (repo / "bad.py").symlink_to("/etc/hostname")
    commit_all(repo, "add escaping link")
    assert evidence.escaping_symlinks(repo, snapshot(repo)) == ["bad.py"]


def test_relative_symlink_escaping_the_root_is_rejected(repo: Path):
    (repo / "out.py").symlink_to("../outside.py")
    commit_all(repo, "add escaping link")
    assert evidence.escaping_symlinks(repo, snapshot(repo)) == ["out.py"]


def test_two_hop_chain_whose_second_hop_escapes_is_caught(repo: Path):
    (repo / "one.py").symlink_to("two.py")
    (repo / "two.py").symlink_to("/etc/hostname")
    commit_all(repo, "chain")
    assert evidence.escaping_symlinks(repo, snapshot(repo)) == ["two.py"]


def test_symlink_in_a_subdirectory_resolves_relative_to_its_own_directory(repo: Path):
    (repo / "pkg").mkdir()
    (repo / "pkg" / "mod.py").write_text("y = 2\n")
    (repo / "pkg" / "link.py").symlink_to("mod.py")
    commit_all(repo, "subdir link")
    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    assert evidence.canonical_path("pkg/link.py", links) == "pkg/mod.py"


# --- label clearance --------------------------------------------------------


def test_label_planted_in_a_tracked_file_is_detected(repo: Path):
    token = "OPTION-" + "a" * 16
    (repo / "app.py").write_text(f"# {token}\n")
    commit_all(repo, "plant")
    assert evidence.scan_for_tokens(repo, snapshot(repo), [token]) == [token]


def test_label_planted_in_an_untracked_file_is_detected(repo: Path):
    """`git add -A` puts ordinary untracked files in the snapshot, so the deciders
    can read them."""
    token = "OPTION-" + "b" * 16
    (repo / "scratch.txt").write_text(token + "\n")
    assert evidence.scan_for_tokens(repo, snapshot(repo), [token]) == [token]


def test_label_in_a_pathname_is_detected(repo: Path):
    """`git grep <commit>` reads blob contents only — not filenames."""
    token = "OPTION-" + "c" * 16
    (repo / f"{token}.py").write_text("x = 1\n")
    commit_all(repo, "plant path")
    assert evidence.scan_for_tokens(repo, snapshot(repo), [token]) == [token]


def test_label_in_a_commit_message_is_detected(repo: Path):
    token = "OPTION-" + "d" * 16
    (repo / "z.py").write_text("x = 1\n")
    commit_all(repo, f"mentions {token}")
    assert evidence.scan_for_tokens(repo, snapshot(repo), [token]) == [token]


def test_clear_labels_scan_clean(repo: Path):
    assert evidence.scan_for_tokens(repo, snapshot(repo), ["OPTION-" + "e" * 16]) == []


def test_historical_blob_only_label_is_NOT_detected(repo: Path):
    """Pins the documented residual: historical blob contents are out of scan, so a
    future reader does not mistake the scan for total coverage."""
    token = "OPTION-" + "f" * 16
    (repo / "hist.py").write_text(f"# {token}\n")
    commit_all(repo, "add")
    (repo / "hist.py").write_text("# clean\n")
    commit_all(repo, "remove")
    assert evidence.scan_for_tokens(repo, snapshot(repo), [token]) == []


# --- citation reads ---------------------------------------------------------


def test_citation_reads_the_cited_lines(repo: Path):
    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    got = evidence.resolve_citation(
        repo, Citation("app.py", 4), snapshot=commit, links=links, context=1
    )
    assert got is not None
    region, body = got
    assert region.path == "app.py"
    assert (region.lo, region.hi) == (3, 5)
    assert "def greet(name):" in body


def test_alias_citation_carries_the_referent_contents_not_the_target_string(repo: Path):
    """Round-8 FATAL: `git show <commit>:<symlink>` returns the target string."""
    (repo / "alias.py").symlink_to("app.py")
    commit_all(repo, "alias")
    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    got = evidence.resolve_citation(
        repo, Citation("alias.py", 4), snapshot=commit, links=links, context=1
    )
    assert got is not None
    region, body = got
    assert region.path == "app.py"  # canonicalized
    assert "def greet(name):" in body
    assert "app.py" not in body.replace("  ", "")  # not the literal target string


def test_alias_and_target_collapse_to_one_region(repo: Path):
    (repo / "alias.py").symlink_to("app.py")
    commit_all(repo, "alias")
    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    a, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4), snapshot=commit, links=links, context=3
    )
    b, _ = evidence.resolve_citation(
        repo, Citation("alias.py", 4), snapshot=commit, links=links, context=3
    )
    assert a.key == b.key


def test_two_aliases_for_one_referent_collapse(repo: Path):
    (repo / "a1.py").symlink_to("app.py")
    (repo / "a2.py").symlink_to("app.py")
    commit_all(repo, "aliases")
    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    r1, _ = evidence.resolve_citation(repo, Citation("a1.py", 4), snapshot=commit, links=links, context=3)
    r2, _ = evidence.resolve_citation(repo, Citation("a2.py", 4), snapshot=commit, links=links, context=3)
    assert r1.key == r2.key


def test_line_past_eof_and_missing_path_drop(repo: Path):
    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    assert evidence.resolve_citation(
        repo, Citation("app.py", 9999), snapshot=commit, links=links, context=3
    ) is None
    assert evidence.resolve_citation(
        repo, Citation("nope.py", 1), snapshot=commit, links=links, context=3
    ) is None


def test_citation_to_a_directory_drops(repo: Path):
    (repo / "pkg").mkdir()
    (repo / "pkg" / "m.py").write_text("x = 1\n")
    commit_all(repo, "pkg")
    commit = snapshot(repo)
    assert evidence.resolve_citation(
        repo, Citation("pkg", 1), snapshot=commit, links={}, context=3
    ) is None


def test_commit_prefixed_citation_reads_that_revision(repo: Path):
    """Revision-aware: a bare path:line would silently resolve against the snapshot
    with bytes the decider never read."""
    old = orientation.resolve_head(repo)
    (repo / "app.py").write_text("# rewritten\n")
    commit_all(repo, "rewrite")
    commit = snapshot(repo)
    got = evidence.resolve_citation(
        repo, Citation("app.py", 4, commit=old), snapshot=commit, links={}, context=1
    )
    assert got is not None
    region, body = got
    assert region.commit == old
    assert "def greet(name):" in body
    # and the same path:line in the snapshot is a DIFFERENT region
    snap = evidence.resolve_citation(
        repo, Citation("app.py", 1), snapshot=commit, links={}, context=1
    )
    assert snap[0].key != region.key


def test_unreachable_commit_prefix_drops(repo: Path):
    commit = snapshot(repo)
    assert evidence.resolve_citation(
        repo, Citation("app.py", 1, commit="deadbee"), snapshot=commit, links={}, context=1
    ) is None


# --- hints ------------------------------------------------------------------


def test_valid_hint_normalizes(repo: Path):
    commit = snapshot(repo)
    assert evidence.validate_hints(repo, commit, [{"path": "./app.py", "reason": "the writer"}]) == [
        {"path": "app.py", "reason": "the writer"}
    ]


@pytest.mark.parametrize("bad", ["/etc/hostname", "../outside.py", "missing.py"])
def test_bad_hints_are_rejected(repo: Path, bad: str):
    commit = snapshot(repo)
    with pytest.raises(ArbitrationError):
        evidence.validate_hints(repo, commit, [{"path": bad}])


def test_ignored_untracked_hint_is_rejected(repo: Path):
    """`git add -A` omits ignored untracked files, so a hint naming one references
    something the recorded commit does not contain."""
    (repo / ".gitignore").write_text("secret.py\n")
    commit_all(repo, "ignore")
    (repo / "secret.py").write_text("x = 1\n")
    commit = snapshot(repo)
    with pytest.raises(ArbitrationError, match="not in the snapshot"):
        evidence.validate_hints(repo, commit, [{"path": "secret.py"}])


# --- merged-region carry and historical aliases (implementation review) -----


def test_read_region_carries_exactly_lo_to_hi(repo: Path):
    """A merged region spans wider than either anchor's window, so reading from the
    anchor would under-carry while substantiation used the merged bounds."""
    (repo / "wide.py").write_text("".join(f"L{i}\n" for i in range(1, 31)))
    commit_all(repo, "wide")
    commit = snapshot(repo)
    from paranoia_local.arbitration import Region

    body = evidence.read_region(repo, Region(commit, "wide.py", 7, 19, 10))
    assert "L7" in body and "L19" in body
    assert "L6" not in body and "L20" not in body
    assert body.count("\n") == 12  # 13 lines


def test_read_region_clamps_and_drops_out_of_range(repo: Path):
    from paranoia_local.arbitration import Region

    commit = snapshot(repo)
    assert evidence.read_region(repo, Region(commit, "app.py", 1, 9999, 1))
    assert evidence.read_region(repo, Region(commit, "app.py", 900, 999, 900)) is None
    assert evidence.read_region(repo, Region(commit, "missing.py", 1, 3, 1)) is None


def test_historical_alias_citation_is_canonicalized_in_its_own_commit(repo: Path):
    """A revision-prefixed citation resolves in ITS commit, so it needs that
    commit's symlink map — the snapshot's would not describe it."""
    (repo / "alias.py").symlink_to("app.py")
    commit_all(repo, "alias")
    old = orientation.resolve_head(repo)
    (repo / "alias.py").unlink()
    (repo / "alias.py").write_text("# no longer a link\n")
    commit_all(repo, "de-alias")
    commit = snapshot(repo)

    got = evidence.resolve_citation(
        repo, Citation("alias.py", 4, commit=old),
        snapshot=commit, links=evidence.symlink_map(repo, commit), context=1,
    )
    assert got is not None
    region, body = got
    assert region.path == "app.py"  # canonicalized in the OLD commit
    assert "def greet(name):" in body


def test_historical_alias_and_target_collapse_to_one_region(repo: Path):
    (repo / "alias.py").symlink_to("app.py")
    commit_all(repo, "alias")
    old = orientation.resolve_head(repo)
    commit = snapshot(repo)
    resolver = evidence.LinkResolver(repo, commit)
    a, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4, commit=old), snapshot=commit, links=resolver, context=3
    )
    b, _ = evidence.resolve_citation(
        repo, Citation("alias.py", 4, commit=old), snapshot=commit, links=resolver, context=3
    )
    assert a.key == b.key


def test_link_resolver_caches_per_commit(repo: Path):
    commit = snapshot(repo)
    resolver = evidence.LinkResolver(repo, commit, {"x": "y"})
    assert resolver.for_commit(commit) == {"x": "y"}
    assert resolver.for_commit("deadbeef") == {}  # unreachable commit degrades to empty
