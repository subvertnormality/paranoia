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


def test_missing_promised_blob_does_not_run_repository_transport(
    repo: Path, tmp_path: Path,
) -> None:
    commit = orientation.resolve_head(repo)
    blob = git(["rev-parse", f"{commit}:app.py"], repo).strip()
    object_path = repo / ".git" / "objects" / blob[:2] / blob[2:]
    assert object_path.exists()
    object_path.unlink()
    marker = tmp_path / "promisor-ran"
    helper = tmp_path / "promisor-helper"
    helper.write_text(f"#!/bin/sh\n: > '{marker}'\nexit 1\n")
    helper.chmod(0o755)
    git(["config", "extensions.partialClone", "origin"], repo)
    git(["config", "remote.origin.promisor", "true"], repo)
    git(["config", "remote.origin.partialclonefilter", "blob:none"], repo)
    git(["config", "protocol.ext.allow", "always"], repo)
    git(["config", "remote.origin.url", f"ext::{helper}"], repo)

    resolved = evidence.resolve_citation(
        repo, Citation("app.py", 1), snapshot=commit,
        links=evidence.LinkResolver(repo, commit), context=1,
    )

    assert resolved is None
    assert not marker.exists()


def test_packet_builder_does_not_run_repository_transport_for_missing_blob(
    repo: Path, tmp_path: Path,
) -> None:
    base = orientation.resolve_head(repo)
    (repo / "app.py").write_text("print('changed')\n")
    commit_all(repo, "change app")
    head = orientation.resolve_head(repo)
    blob = git(["rev-parse", f"{head}:app.py"], repo).strip()
    object_path = repo / ".git" / "objects" / blob[:2] / blob[2:]
    assert object_path.exists()
    object_path.unlink()
    marker = tmp_path / "promisor-ran"
    helper = tmp_path / "promisor-helper"
    helper.write_text(f"#!/bin/sh\n: > '{marker}'\nexit 1\n")
    helper.chmod(0o755)
    git(["config", "extensions.partialClone", "origin"], repo)
    git(["config", "remote.origin.promisor", "true"], repo)
    git(["config", "remote.origin.partialclonefilter", "blob:none"], repo)
    git(["config", "protocol.ext.allow", "always"], repo)
    git(["config", "remote.origin.url", f"ext::{helper}"], repo)

    packet = orientation.build_packet(repo, base, head)

    assert "FILE app.py" in packet
    assert not marker.exists()


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
    # the rewritten snapshot is only one line long, so line 4 no longer exists there
    assert evidence.resolve_citation(
        repo, Citation("app.py", 4), snapshot=commit, links={}, context=1
    ) is None


def test_unreachable_commit_prefix_drops(repo: Path):
    commit = snapshot(repo)
    assert evidence.resolve_citation(
        repo, Citation("app.py", 1, commit="deadbee"), snapshot=commit, links={}, context=1
    ) is None


# --- hints ------------------------------------------------------------------


def test_a_dot_slash_citation_drops_rather_than_keying_a_second_region(repo: Path):
    """git accepts `./f.py` as a lookup, but the string differs from `f.py` and would
    key as a separate region. Literal tree membership drops it."""
    commit = snapshot(repo)
    resolver = evidence.LinkResolver(repo, commit)
    assert evidence.resolve_citation(
        repo, Citation("./app.py", 4), snapshot=commit, links=resolver, context=1
    ) is None
    assert evidence.resolve_citation(
        repo, Citation("app.py", 4), snapshot=commit, links=resolver, context=1
    ) is not None


def test_symlink_target_is_read_verbatim(repo: Path):
    """Round-11 blocker: `.strip()` on a target resolves `alias -> ' real.py '` to a
    different tracked file than the decider read."""
    (repo / " spaced.py ").write_text("SPACED\n" * 4)
    (repo / "alias.py").symlink_to(" spaced.py ")
    commit_all(repo, "spaced target")
    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    assert links["alias.py"] == " spaced.py "


def test_a_hint_path_is_used_verbatim(repo: Path):
    commit = snapshot(repo)
    assert evidence.validate_hints(repo, commit, [{"path": "app.py", "reason": "the writer"}]) == [
        {"path": "app.py", "reason": "the writer"}
    ]


def test_a_hint_path_is_not_normalized(repo: Path):
    """Round-3 blocker, and the same class as citation paths: every rewrite can map one
    tracked file onto another. `./app.py` now errors rather than being folded."""
    commit = snapshot(repo)
    with pytest.raises(ArbitrationError, match="as spelled"):
        evidence.validate_hints(repo, commit, [{"path": "./app.py"}])


def test_a_backslash_hint_does_not_fold_onto_a_different_tracked_file(repo: Path):
    """The concrete swap: git tracks both spellings as distinct files with different
    bytes, and the attester is shown the path the SERVER resolved, so folding the
    separator would steer both deciders invisibly."""
    (repo / "policy").mkdir()
    (repo / "policy" / "choice.py").write_text("FORWARD\n")
    (repo / "policy\\choice.py").write_text("BACKSLASH\n")
    commit_all(repo, "both spellings")
    commit = snapshot(repo)
    assert evidence.validate_hints(
        repo, commit, [{"path": "policy\\choice.py"}]
    ) == [{"path": "policy\\choice.py", "reason": ""}]
    assert evidence.validate_hints(
        repo, commit, [{"path": "policy/choice.py"}]
    ) == [{"path": "policy/choice.py", "reason": ""}]


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


def test_equivalent_commit_spellings_are_one_region(repo: Path):
    """Round-2 blocker: keying on the supplied spelling made `abc1234@f:1` and
    `abc1234def@f:1` two regions, so each vendor 'gained' the other's spelling and
    round 2 carried identical bytes twice."""
    old = orientation.resolve_head(repo)
    commit = snapshot(repo)
    resolver = evidence.LinkResolver(repo, commit)
    short, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4, commit=old[:8]), snapshot=commit, links=resolver, context=1
    )
    longer, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4, commit=old[:12]), snapshot=commit, links=resolver, context=1
    )
    full, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4, commit=old), snapshot=commit, links=resolver, context=1
    )
    assert short.commit == longer.commit == full.commit == old


def test_bare_and_explicitly_prefixed_snapshot_citations_are_one_region(repo: Path):
    commit = snapshot(repo)
    resolver = evidence.LinkResolver(repo, commit)
    bare, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4), snapshot=commit, links=resolver, context=1
    )
    prefixed, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4, commit=commit[:8]), snapshot=commit, links=resolver, context=1
    )
    assert bare.commit == prefixed.commit


def test_unresolvable_revision_drops(repo: Path):
    commit = snapshot(repo)
    assert evidence.resolve_citation(
        repo, Citation("app.py", 1, commit="0123456"), snapshot=commit,
        links=evidence.LinkResolver(repo, commit), context=1,
    ) is None


def test_unchanged_file_at_wrapper_and_parent_is_one_region(repo: Path):
    """Round-3 blocker, the normal case: every run wraps HEAD, so a bare citation
    resolves to the wrapper commit while `HEAD@…` resolves to its parent. Same bytes,
    so it must be one region — otherwise both vendors 'gain' evidence and round 2
    carries identical bytes twice."""
    head = orientation.resolve_head(repo)
    commit = snapshot(repo)
    assert commit != head  # the wrapper really is a different commit
    resolver = evidence.LinkResolver(repo, commit)
    bare, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4), snapshot=commit, links=resolver, context=1
    )
    parent, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4, commit=head), snapshot=commit, links=resolver, context=1
    )
    from paranoia_local.arbitration import same_region

    assert bare.commit != parent.commit  # provenance is preserved
    assert same_region(bare, parent)  # but identity is the carried content


def test_a_changed_cited_window_at_two_commits_is_two_regions(repo: Path):
    from paranoia_local.arbitration import same_region

    head = orientation.resolve_head(repo)
    (repo / "app.py").write_text("# rewritten entirely\n" * 6)
    commit = snapshot(repo)
    resolver = evidence.LinkResolver(repo, commit)
    now, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4), snapshot=commit, links=resolver, context=1
    )
    before, _ = evidence.resolve_citation(
        repo, Citation("app.py", 4, commit=head), snapshot=commit, links=resolver, context=1
    )
    assert not same_region(now, before)


def test_a_change_outside_the_cited_window_is_still_one_region(repo: Path):
    """Round-4 blocker: keying on git's blob id split a region whose transported
    lines were identical, because the blob covers the whole file."""
    from paranoia_local.arbitration import same_region

    (repo / "long.py").write_text("".join(f"L{i}\n" for i in range(1, 41)))
    commit_all(repo, "long")
    head = orientation.resolve_head(repo)
    # edit line 40, far outside a context-3 window around line 10
    text = (repo / "long.py").read_text().splitlines()
    text[39] = "UNRELATED"
    (repo / "long.py").write_text("\n".join(text) + "\n")
    commit = snapshot(repo)
    resolver = evidence.LinkResolver(repo, commit)
    now, _ = evidence.resolve_citation(
        repo, Citation("long.py", 10), snapshot=commit, links=resolver, context=3
    )
    before, _ = evidence.resolve_citation(
        repo, Citation("long.py", 10, commit=head), snapshot=commit, links=resolver, context=3
    )
    assert now.commit != before.commit
    assert same_region(now, before)


def test_directory_symlink_with_dotdot_cannot_substitute_evidence(repo: Path):
    """Round-6 finding, end to end: `alias/../f.py` resolves to `sub/f.py` in the
    worktree but would normalize to root `f.py`. The citation is dropped instead."""
    (repo / "sub").mkdir()
    (repo / "sub" / "dir").mkdir()
    (repo / "sub" / "f.py").write_text("SUBDIR VERSION\n" * 5)
    (repo / "f.py").write_text("ROOT VERSION\n" * 5)
    (repo / "alias").symlink_to("sub/dir")
    commit_all(repo, "dir symlink")
    commit = snapshot(repo)

    # what the worktree would resolve
    assert (repo / "alias" / ".." / "f.py").resolve() == (repo / "sub" / "f.py").resolve()
    # but the citation is used verbatim, is not a literal tree entry, and drops
    assert evidence.resolve_citation(
        repo, Citation("alias/../f.py", 2), snapshot=commit,
        links=evidence.LinkResolver(repo, commit), context=1,
    ) is None
    # the root file is still citable on its own terms
    got = evidence.resolve_citation(
        repo, Citation("f.py", 2), snapshot=commit,
        links=evidence.LinkResolver(repo, commit), context=1,
    )
    assert got and "ROOT VERSION" in got[1]


def test_dotdot_inside_a_symlink_target_fails_closed(repo: Path):
    """Round-12 blocker, and the last boundary of the path-substitution class: the
    string comes from repository data rather than a model, but the same lexical
    collapsing diverges from the worktree as soon as an earlier component is itself
    a symlink."""
    (repo / "sub").mkdir()
    (repo / "sub" / "dir").mkdir()
    (repo / "sub" / "f.py").write_text("SUB VERSION\n" * 5)
    (repo / "f.py").write_text("ROOT VERSION\n" * 5)
    (repo / "linkdir").symlink_to("sub/dir")
    (repo / "alias").symlink_to("linkdir/../f.py")
    commit_all(repo, "symlink through symlink")

    # the worktree reads sub/f.py, NOT root f.py
    assert (repo / "alias").resolve() == (repo / "sub" / "f.py").resolve()

    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    # so we decline to resolve it rather than substituting root f.py
    assert evidence.canonical_path("alias", links) is None
    assert evidence.resolve_citation(
        repo, Citation("alias", 2), snapshot=commit,
        links=evidence.LinkResolver(repo, commit, links), context=1,
    ) is None
    # both real files remain citable on their own terms
    got = evidence.resolve_citation(
        repo, Citation("sub/f.py", 2), snapshot=commit,
        links=evidence.LinkResolver(repo, commit, links), context=1,
    )
    assert got and "SUB VERSION" in got[1]


def test_a_plain_relative_symlink_target_still_resolves(repo: Path):
    """Only `..` fails closed; ordinary in-tree targets are unaffected."""
    (repo / "pkg").mkdir()
    (repo / "pkg" / "mod.py").write_text("MOD\n" * 5)
    (repo / "pkg" / "link.py").symlink_to("mod.py")
    commit_all(repo, "plain link")
    commit = snapshot(repo)
    links = evidence.symlink_map(repo, commit)
    assert evidence.canonical_path("pkg/link.py", links) == "pkg/mod.py"


def test_a_dotdot_target_does_not_reject_the_whole_run(repo: Path):
    """The escape gate keeps its lexical reading: a `..` target that stays inside the
    repo is not an escape, so a repository using them is still arbitrable."""
    (repo / "shared").mkdir()
    (repo / "shared" / "x.py").write_text("X\n")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "link.py").symlink_to("../shared/x.py")
    commit_all(repo, "upward but inside")
    assert evidence.escaping_symlinks(repo, snapshot(repo)) == []


def test_a_citation_to_a_path_git_would_quote_still_resolves(repo: Path):
    """Latent break in the round-12 literal-membership closure, exposed by round 3:
    `ls-tree --name-only` QUOTES paths containing a backslash or non-ASCII byte, so the
    membership set held `"policy\\\\choice.py"` while a citation carries the raw name.
    Every legitimate reference to such a file was therefore unresolvable — the opposite
    of what the literal match is for. `-z` makes the read byte-faithful."""
    (repo / "policy").mkdir()
    (repo / "policy" / "choice.py").write_text("FORWARD\n" * 10)
    (repo / "policy\\choice.py").write_text("BACKSLASH\n" * 10)
    (repo / "café.py").write_text("UNICODE\n" * 10)
    commit_all(repo, "paths git quotes")
    commit = snapshot(repo)

    paths = evidence.tree_paths(repo, commit)
    assert "policy\\choice.py" in paths and "policy/choice.py" in paths
    assert "café.py" in paths
    assert not any(p.startswith('"') for p in paths), "no path may come back quoted"

    links = evidence.LinkResolver(repo, commit, evidence.symlink_map(repo, commit))
    for path, want in (("policy\\choice.py", "BACKSLASH"),
                       ("policy/choice.py", "FORWARD"),
                       ("café.py", "UNICODE")):
        got = evidence.resolve_citation(
            repo, Citation(path, 3), snapshot=commit, links=links, context=1
        )
        assert got, f"{path} should resolve"
        assert want in got[1], f"{path} resolved to the wrong file's bytes"


def test_a_hint_path_is_not_stripped(repo: Path):
    """Round-4 blocker: `.strip()` folded one tracked file onto another. The repo
    already tracks space-delimited filenames, so this was the same substitution class
    the rest of the module refuses."""
    (repo / " spaced.py ").write_text("PADDED\n" * 5)
    (repo / "spaced.py").write_text("BARE\n" * 5)
    commit_all(repo, "both spellings")
    commit = snapshot(repo)
    assert evidence.validate_hints(repo, commit, [{"path": " spaced.py "}]) == [
        {"path": " spaced.py ", "reason": ""}
    ]
    assert evidence.validate_hints(repo, commit, [{"path": "spaced.py"}]) == [
        {"path": "spaced.py", "reason": ""}
    ]


def test_tree_paths_do_not_collapse_on_undecodable_bytes(repo: Path):
    """Round-4: `errors='replace'` mapped every undecodable byte to U+FFFD, so two
    distinct filenames collapsed to one string and the membership set stopped
    describing the tree."""
    import os
    (repo / os.fsdecode(b"caf\xe9.py")).write_bytes(b"LATIN1\n" * 5)
    (repo / os.fsdecode(b"caf\xff.py")).write_bytes(b"OTHER\n" * 5)
    commit_all(repo, "undecodable names")
    paths = evidence.tree_paths(repo, snapshot(repo))
    assert os.fsdecode(b"caf\xe9.py") in paths
    assert os.fsdecode(b"caf\xff.py") in paths
    assert "caf�.py" not in paths, "distinct names must not collapse"


def test_an_escaping_symlink_with_an_undecodable_name_is_reportable(repo: Path):
    """`surrogateescape` means a path can hold lone surrogates, and encoding one to
    UTF-8 raises — an error message must never be the thing that crashes the run."""
    import os
    name = os.fsdecode(b"esc\xff")
    (repo / name).symlink_to("../outside.py")
    commit_all(repo, "undecodable escaping link")
    escaping = evidence.escaping_symlinks(repo, snapshot(repo))
    assert escaping
    rendered = ", ".join(evidence.printable(e) for e in escaping)
    rendered.encode("utf-8")  # must not raise
