"""Mechanism tests for the arbitration protocol — zero model variance.

Every case here corresponds to a way two deciders could be reported as agreeing
when they did not. The regression cases found by adversarial review are labelled
with what they caught.
"""

import pytest

from paranoia_local import arbitration as arb
from paranoia_local.arbitration import (
    ArbitrationError,
    Citation,
    Option,
    Region,
    Vote,
)

OPTS = [
    {"id": "opt-float", "statement": "Use float."},
    {"id": "opt-decimal", "statement": "Use Decimal."},
]


def options(*pairs):
    return arb.canonical_order([Option(id=i, statement=s) for i, s in pairs])


def trailer(
    selected,
    *,
    risk="NONE",
    authority="technical",
    new_option="NONE",
    constraint="Because of a thing.",
    decisive="app.py:4",
    citations="NONE",
):
    return (
        "Some reasoning.\n\n"
        f"SELECTED: {selected}\n"
        f"SELECTED-RISK: {risk}\n"
        f"AUTHORITY: {authority}\n"
        f"NEW-OPTION: {new_option}\n"
        f"CONSTRAINT: {constraint}\n"
        f"DECISIVE-CITATION: {decisive}\n"
        f"CITATIONS: {citations}\n"
    )


def vote(engine, selected, **kw):
    return Vote(
        engine=engine,
        label="OPTION-" + "0" * 16,
        selected=selected,
        severity=kw.get("severity", "NONE"),
        risk_text=kw.get("risk_text", ""),
        authority=kw.get("authority", "technical"),
        new_option=kw.get("new_option"),
        constraint=kw.get("constraint", "c"),
        decisive=kw.get("decisive", Citation("app.py", 4)),
        citations=kw.get("citations", ()),
    )


# --- options and ids --------------------------------------------------------


def test_options_must_be_an_array_not_a_blob():
    with pytest.raises(ArbitrationError, match="array"):
        arb.validate_options("opt-1: float, opt-2: Decimal")


@pytest.mark.parametrize("count", [1, 5])
def test_option_count_is_bounded(count):
    raw = [{"id": f"o{i}", "statement": "s"} for i in range(count)]
    with pytest.raises(ArbitrationError, match="number"):
        arb.validate_options(raw)


def test_duplicate_ids_rejected():
    with pytest.raises(ArbitrationError, match="duplicate"):
        arb.validate_options([{"id": "a", "statement": "x"}, {"id": "a", "statement": "y"}])


def test_reserved_and_colliding_ids_rejected():
    label = arb.LABEL_PREFIX + "a" * 16
    for bad in ("none", "NONE", "SELECTED", label):
        with pytest.raises(ArbitrationError):
            arb.validate_options([{"id": bad, "statement": "x"}, {"id": "ok", "statement": "y"}])


def test_canonical_order_is_invariant_under_caller_array_order():
    """Retyping the same options in another order must change nothing: an earlier
    design derived ids from array order, so SELECTED denoted different actions
    across replays."""
    forward = arb.validate_options(OPTS)
    backward = arb.validate_options(list(reversed(OPTS)))
    assert arb.canonical_order(forward) == arb.canonical_order(backward)


def test_caller_id_in_prose_is_rejected():
    with pytest.raises(ArbitrationError, match="reserved token"):
        arb.reject_reserved_tokens(
            {"context": "unlike opt-float, this is exact"}, ["opt-float", "opt-decimal"]
        )


def test_label_token_in_prose_is_rejected():
    """Round-3 FATAL: with a label in the prose, a reversed decider can echo the
    prose label and have both votes map to the same option."""
    label = arb.LABEL_PREFIX + "b" * 16
    with pytest.raises(ArbitrationError, match="reserved token"):
        arb.reject_reserved_tokens({"decision": f"prefer {label}"}, [label])


def test_reserved_token_check_covers_every_decider_visible_field():
    for field in ("decision", "context", "stakes", "statement", "hint"):
        with pytest.raises(ArbitrationError, match=field):
            arb.reject_reserved_tokens({field: "see opt-float"}, ["opt-float"])


# --- stakes -----------------------------------------------------------------


def test_stakes_is_required():
    for missing in (None, "", "   "):
        with pytest.raises(ArbitrationError, match="stakes is required"):
            arb.resolve_stakes(missing)


def test_unstated_stakes_renders_one_fixed_sentence():
    assert arb.resolve_stakes("unstated") == arb.STAKES_DEFAULT
    assert arb.resolve_stakes("UNSTATED") == arb.resolve_stakes("unstated")


def test_stated_stakes_passes_through_verbatim():
    assert arb.resolve_stakes("  local CLI, trusted input  ") == "local CLI, trusted input"


# --- labels -----------------------------------------------------------------


def test_labels_are_derived_jointly_and_distinct():
    sets = arb.derive_labels("seed", 2, 4)
    flat = [x for s in sets for x in s]
    assert len(set(flat)) == 8


def test_label_sets_are_disjoint_between_deciders():
    """The membership backstop: a label echoed from the other decider must not be
    valid here."""
    a, b = arb.derive_labels("seed", 2, 3)
    assert not (set(a) & set(b))


def test_same_seed_derives_same_labels_and_different_attempt_differs():
    assert arb.derive_labels("s", 2, 2, 0) == arb.derive_labels("s", 2, 2, 0)
    assert arb.derive_labels("s", 2, 2, 1) != arb.derive_labels("s", 2, 2, 0)


def test_derivation_collision_is_detected(monkeypatch):
    """Round-5 MAJOR: an intra-set duplicate would let two options share one
    accepted token; a cross-set duplicate would defeat the backstop."""

    class Fixed:
        def __init__(self, *a, **k):
            pass

        def hexdigest(self):
            return "c" * 64

    monkeypatch.setattr(arb.hashlib, "sha256", Fixed)
    with pytest.raises(ArbitrationError, match="collided"):
        arb.derive_labels("seed", 2, 2)


def test_labels_carry_no_ordinal_information():
    labels = arb.derive_labels("seed", 2, 4)[0]
    assert sorted(labels) != list(labels) or len(set(labels)) == 4  # not lexically ordered by position


# --- presentation and counterbalancing --------------------------------------


@pytest.mark.parametrize("n", [2, 3, 4])
def test_reversal_equalizes_mean_rank(n):
    """Reversal, not rotation: every option's two ranks sum to N+1, so no option is
    early for both deciders. Rotation only guarantees different ranks."""
    canon = options(*[(f"o{i}", f"s{i}") for i in range(n)])
    labels = arb.derive_labels("seed", 2, n)
    fwd = arb.presentation_for(canon, labels[0], "a", reverse=False)
    rev = arb.presentation_for(canon, labels[1], "b", reverse=True)
    for opt in canon:
        r1 = [i for i, (lab, _) in enumerate(fwd.items, 1) if fwd.label_to_id[lab] == opt.id][0]
        r2 = [i for i, (lab, _) in enumerate(rev.items, 1) if rev.label_to_id[lab] == opt.id][0]
        assert r1 + r2 == n + 1


def test_vendor_order_assignment_comes_from_the_seed_not_the_registry():
    """Registry index would hand the same vendor the caller's order every time."""
    seeds = [f"seed-{i}" for i in range(40)]
    assignments = {arb.forward_engine(s, 2) for s in seeds}
    assert assignments == {0, 1}
    assert arb.forward_engine("fixed", 2) == arb.forward_engine("fixed", 2)


def test_mapping_is_correct_when_both_deciders_pick_their_first_label():
    """The test that catches a mapping inversion silently reporting convergence:
    both say their own first label and they mean DIFFERENT options."""
    canon = options(("opt-a", "A"), ("opt-b", "B"))
    a, b = arb.build_presentations(canon, ["codex", "claude"], "seed")
    first_a = a.items[0][0]
    first_b = b.items[0][0]
    assert a.label_to_id[first_a] != b.label_to_id[first_b]


def test_build_presentations_gives_one_forward_and_one_reversed():
    canon = options(("opt-a", "A"), ("opt-b", "B"), ("opt-c", "C"))
    ps = arb.build_presentations(canon, ["codex", "claude"], "seed")
    assert sorted(p.reversed_order for p in ps) == [False, True]


# --- trailer parsing --------------------------------------------------------


def _pres(engine="codex", n=2, seed="seed"):
    canon = options(*[(f"opt-{i}", f"s{i}") for i in range(n)])
    labels = arb.derive_labels(seed, 2, n)[0]
    return arb.presentation_for(canon, labels, engine, reverse=False)


def test_parse_verdict_maps_label_to_caller_id():
    p = _pres()
    label = p.items[1][0]
    v = arb.parse_verdict(trailer(label), p)
    assert v.selected == p.label_to_id[label]
    assert v.severity == "NONE"
    assert v.decisive == Citation("app.py", 4)


def test_parse_verdict_takes_the_last_trailer_occurrence():
    p = _pres()
    first, second = p.items[0][0], p.items[1][0]
    text = trailer(first) + "\n" + trailer(second)
    assert arb.parse_verdict(text, p).selected == p.label_to_id[second]


@pytest.mark.parametrize(
    "selected",
    ["opt-0", "Use float.", arb.LABEL_PREFIX + "f" * 16, "", "OPTION-notarealone"],
)
def test_non_member_selected_fails_rather_than_guessing(selected):
    """A caller-id echo, an option named by its words, a label from the other
    decider's set, or one seen in repository evidence must all fail."""
    p = _pres()
    with pytest.raises(ArbitrationError, match="not a label issued"):
        arb.parse_verdict(trailer(selected), p)


def test_cross_decider_label_echo_fails_membership():
    canon = options(("opt-a", "A"), ("opt-b", "B"))
    a, b = arb.build_presentations(canon, ["codex", "claude"], "seed")
    with pytest.raises(ArbitrationError, match="not a label issued"):
        arb.parse_verdict(trailer(b.items[0][0]), a)


def test_missing_trailer_field_fails():
    p = _pres()
    text = trailer(p.items[0][0]).replace("DECISIVE-CITATION: app.py:4\n", "")
    with pytest.raises(ArbitrationError, match="missing trailer field"):
        arb.parse_verdict(text, p)


def test_bad_severity_and_authority_fail():
    p = _pres()
    label = p.items[0][0]
    with pytest.raises(ArbitrationError, match="SELECTED-RISK"):
        arb.parse_verdict(trailer(label, risk="probably fine"), p)
    with pytest.raises(ArbitrationError, match="AUTHORITY"):
        arb.parse_verdict(trailer(label, authority="maybe"), p)


def test_severity_and_new_option_parse():
    p = _pres()
    label = p.items[0][0]
    v = arb.parse_verdict(trailer(label, risk="[MAJOR] crashes the writer", new_option="use ints"), p)
    assert v.severity == "MAJOR"
    assert v.risk_text == "crashes the writer"
    assert v.new_option == "use ints"


# --- citations --------------------------------------------------------------


def test_citations_parse_from_the_field_only():
    """A path:line inside CONSTRAINT prose is not a citation."""
    p = _pres()
    v = arb.parse_verdict(
        trailer(p.items[0][0], constraint="see other.py:99 for context", decisive="app.py:4"), p
    )
    assert v.decisive == Citation("app.py", 4)
    assert v.citations == ()


def test_dot_slash_normalizes_identically():
    assert arb.parse_citations("./foo.py:7") == arb.parse_citations("foo.py:7")


def test_revision_aware_citations():
    """A bare path:line resolves in the snapshot; a commit prefix resolves there."""
    (bare,) = arb.parse_citations("foo.py:7")
    (pinned,) = arb.parse_citations("abc1234@foo.py:7")
    assert bare.commit is None
    assert pinned.commit == "abc1234"
    assert pinned.path == "foo.py"


def test_citation_limit_and_unparseable_are_dropped():
    cites = arb.parse_citations("a.py:1, b.py:2, c.py:3, d.py:4")
    assert len(cites) == arb.MAX_CITATIONS
    assert arb.parse_citations("nonsense, a.py:0, ../escape.py:3") == ()


def test_none_citations():
    assert arb.parse_citations("NONE") == ()
    assert arb.parse_citations("") == ()


# --- regions ----------------------------------------------------------------


def region(path, anchor, *, commit="c0", lines=None, eof=1000, context=3):
    """Region identity is the path plus the digests of the lines transported, so two
    citations of the same content are one region however they were spelled."""
    body = lines if lines is not None else [f"{path}:{i}" for i in range(1, eof + 1)]
    return arb.to_region(
        Citation(path, anchor), commit=commit, eof=min(eof, len(body)),
        lines=body, context=context,
    )


def test_region_clamps_at_file_bounds():
    r = arb.to_region(
        Citation("a.py", 2), commit="c0", eof=4, lines=["a", "b", "c", "d"], context=3
    )
    assert (r.lo, r.hi) == (1, 4)
    assert len(r.line_digests) == 4


def test_adjacent_anchors_are_the_same_region():
    """Round-3 FATAL: anchors 100 and 101 carry near-identical windows, so keying on
    the anchor let an evidence-free round 2 run."""
    assert arb.same_region(region("a.py", 100), region("a.py", 101))


def test_distant_anchors_are_different_regions():
    assert not arb.same_region(region("a.py", 100), region("a.py", 200))


def test_same_bytes_at_different_commits_are_ONE_region():
    """Round-3 blocker: every run wraps HEAD, so a bare citation and a HEAD@ citation
    of the same unchanged file are byte-identical. Keying on the commit made them two
    regions, so both vendors 'gained' evidence and round 2 ran on the same bytes."""
    a = region("a.py", 10, commit="wrapper")
    b = region("a.py", 10, commit="parent")
    assert arb.same_region(a, b)


def test_same_path_with_different_carried_content_are_different_regions():
    body = [f"a.py:{i}" for i in range(1, 21)]
    changed = list(body)
    changed[9] = "CHANGED"
    a = region("a.py", 10, commit="c1", lines=body, eof=20)
    b = region("a.py", 10, commit="c2", lines=changed, eof=20)
    assert not arb.same_region(a, b)


def test_a_change_outside_the_carried_window_is_still_ONE_region():
    """Round-4 blocker: git's blob id is the whole FILE, so an edit anywhere outside
    the cited window split a region whose transported lines were identical."""
    body = [f"a.py:{i}" for i in range(1, 41)]
    elsewhere = list(body)
    elsewhere[35] = "UNRELATED EDIT"
    a = region("a.py", 10, commit="c1", lines=body, eof=40)
    b = region("a.py", 10, commit="c2", lines=elsewhere, eof=40)
    assert arb.same_region(a, b)


def test_regions_with_no_digests_are_treated_as_the_same():
    a = arb.Region("c1", "a.py", 7, 13, 10)
    b = arb.Region("c2", "a.py", 7, 13, 10)
    assert arb.same_region(a, b)


def test_anchor_within_is_point_in_interval_not_intersection():
    """Round-10 MAJOR: carried [104,110] and a fresh anchor at 113 have overlapping
    windows, but 113 was never carried."""
    carried = Region(commit="c0", path="a.py", lo=104, hi=110, anchor=107)
    fresh = region("a.py", 113)
    assert arb.same_region(fresh, carried)  # windows overlap
    assert not arb.anchor_within(fresh, carried)  # but the anchor was not carried
    assert arb.anchor_within(region("a.py", 108), carried)


def test_merge_regions_merges_overlaps_per_path():
    merged = arb.merge_regions(
        [region("a.py", 10), region("a.py", 13), region("a.py", 100), region("b.py", 10)]
    )
    assert len(merged) == 3
    a = [r for r in merged if r.path == "a.py"]
    assert (a[0].lo, a[0].hi) == (7, 16)


# --- the round-2 gate -------------------------------------------------------


def test_gate_runs_round_two_on_disjoint_regions():
    own = {"codex": [region("a.py", 10)], "claude": [region("b.py", 20)]}
    union = arb.region_union(own)
    assert arb.round_two_permitted(union, own)


def test_gate_refuses_overlapping_regions():
    """Both cited the same evidence: round 2 would be a second cold sample."""
    own = {"codex": [region("a.py", 10)], "claude": [region("a.py", 11)]}
    union = arb.region_union(own)
    assert not arb.round_two_permitted(union, own)


def test_gate_refuses_one_sided_gain():
    own = {"codex": [region("a.py", 10)], "claude": []}
    union = arb.region_union(own)
    assert not arb.round_two_permitted(union, own)


def test_gate_refuses_when_nothing_resolved():
    own = {"codex": [], "claude": []}
    assert not arb.round_two_permitted(arb.region_union(own), own)


def test_union_is_identical_for_both_deciders_and_content_ordered():
    """Round-3 FATAL: withholding a decider's own region contradicted the
    cold-session premise and stripped its decisive evidence from its own vote."""
    own = {"codex": [region("a.py", 10)], "claude": [region("b.py", 20)]}
    union = arb.region_union(own)
    assert len(union) == 2
    assert arb.region_union({"claude": own["claude"], "codex": own["codex"]}) == union


def test_gains_excludes_own_regions():
    own = {"codex": [region("a.py", 10)], "claude": [region("b.py", 20)]}
    union = arb.region_union(own)
    gained = arb.gains_for("codex", union, own["codex"])
    assert [r.path for r in gained] == ["b.py"]


# --- substantiation ---------------------------------------------------------


def _resolver(eof=1000, missing=()):
    def resolve(c: Citation):
        if c.path in missing:
            return None
        return arb.to_region(c, commit=c.commit or "snap", eof=eof)

    return resolve


def test_round_one_requires_a_resolved_decisive_citation():
    votes = [vote("codex", "opt-a"), vote("claude", "opt-a", decisive=None)]
    got = arb.substantiation(votes, resolve=_resolver())
    assert got == {"codex": True, "claude": False}


def test_a_citation_that_does_not_resolve_does_not_substantiate():
    votes = [vote("codex", "opt-a", decisive=Citation("gone.py", 4))]
    assert arb.substantiation(votes, resolve=_resolver(missing={"gone.py"})) == {"codex": False}


def test_round_two_requires_the_decisive_anchor_inside_a_carried_novel_region():
    carried = {"codex": [Region("snap", "b.py", 17, 23, 20)]}
    good = [vote("codex", "opt-a", decisive=Citation("b.py", 20))]
    bad = [vote("codex", "opt-a", decisive=Citation("a.py", 10))]
    assert arb.substantiation(good, resolve=_resolver(), carried=carried) == {"codex": True}
    assert arb.substantiation(bad, resolve=_resolver(), carried=carried) == {"codex": False}


def test_round_two_supporting_citations_never_substantiate():
    """Round-10 FATAL: a decider could keep its own prior region as its real reason
    and merely append the other vendor's novel region."""
    carried = {"codex": [Region("snap", "b.py", 17, 23, 20)]}
    votes = [
        vote(
            "codex",
            "opt-a",
            decisive=Citation("a.py", 10),  # its own prior region
            citations=(Citation("b.py", 20),),  # novel, but only supporting
        )
    ]
    assert arb.substantiation(votes, resolve=_resolver(), carried=carried) == {"codex": False}


# --- outcomes ---------------------------------------------------------------


SUB = {"codex": True, "claude": True}


def test_converged():
    votes = [vote("codex", "opt-a"), vote("claude", "opt-a")]
    got = arb.compute_outcome(votes, substantiated=SUB)
    assert (got.outcome, got.selected) == (arb.CONVERGED, "opt-a")


def test_blocked_on_a_single_major():
    votes = [vote("codex", "opt-a"), vote("claude", "opt-a", severity="MAJOR", risk_text="boom")]
    got = arb.compute_outcome(votes, substantiated=SUB)
    assert got.outcome == arb.BLOCKED
    assert got.selected == "opt-a"


def test_unresolved_on_split():
    votes = [vote("codex", "opt-a"), vote("claude", "opt-b")]
    assert arb.compute_outcome(votes, substantiated=SUB).outcome == arb.UNRESOLVED


def test_unsubstantiated_agreement_is_unresolved():
    votes = [vote("codex", "opt-a"), vote("claude", "opt-a")]
    got = arb.compute_outcome(votes, substantiated={"codex": True, "claude": False})
    assert got.outcome == arb.UNRESOLVED
    assert "not substantiated" in got.reason


def test_reframe_required_beats_agreement():
    """Evaluated before the selection comparison: a run that would read CONVERGED
    while a decider says something better exists is not a finished decision."""
    votes = [vote("codex", "opt-a", new_option="use ints"), vote("claude", "opt-a")]
    got = arb.compute_outcome(votes, substantiated=SUB)
    assert got.outcome == arb.REFRAME_REQUIRED
    assert "use ints" in got.reason


def test_reframe_required_beats_unsubstantiated():
    votes = [vote("codex", "opt-a", new_option="x"), vote("claude", "opt-a")]
    got = arb.compute_outcome(votes, substantiated={"codex": False, "claude": False})
    assert got.outcome == arb.REFRAME_REQUIRED


def test_blocked_beats_unsubstantiated():
    votes = [vote("codex", "opt-a", severity="FATAL", risk_text="no"), vote("claude", "opt-a")]
    got = arb.compute_outcome(votes, substantiated={"codex": False, "claude": False})
    assert got.outcome == arb.BLOCKED


def test_refs_moved_and_failure_fail():
    votes = [vote("codex", "opt-a"), vote("claude", "opt-a")]
    assert arb.compute_outcome(votes, substantiated=SUB, refs_moved=True).outcome == arb.FAILED
    assert arb.compute_outcome(votes, substantiated=SUB, failure="boom").outcome == arb.FAILED
    assert arb.compute_outcome([], substantiated={}).outcome == arb.FAILED


def test_authority_never_changes_the_outcome():
    votes = [
        vote("codex", "opt-a", authority="human-owner"),
        vote("claude", "opt-a", authority="human-owner"),
    ]
    got = arb.compute_outcome(votes, substantiated=SUB)
    assert got.outcome == arb.CONVERGED
    assert arb.advisory_line(votes) == "human-owner (flagged by: both)"


def test_advisory_line_values():
    a = vote("codex", "opt-a")
    b = vote("claude", "opt-a", authority="human-owner")
    assert arb.advisory_line([a, a]) == "none"
    assert arb.advisory_line([a, b]) == "human-owner (flagged by: claude)"


# --- trailer grammar strictness (implementation review, round 1) ------------


def test_selected_must_be_the_whole_value_not_the_first_token():
    """`SELECTED: <label> (the safe one)` must fail rather than silently discarding
    the trailing text, which may be where the decider qualified its answer."""
    p = _pres()
    label = p.items[0][0]
    with pytest.raises(ArbitrationError, match="not a label issued"):
        arb.parse_verdict(trailer(f"{label} (the safe one)"), p)


def test_none_prefixed_risk_is_rejected_not_read_as_none():
    """`NONE [MAJOR] unsafe` read as NONE would turn a blocking objection into a
    CONVERGED."""
    p = _pres()
    with pytest.raises(ArbitrationError, match="SELECTED-RISK"):
        arb.parse_verdict(trailer(p.items[0][0], risk="NONE [MAJOR] unsafe"), p)


def test_severity_without_a_reason_is_rejected():
    p = _pres()
    with pytest.raises(ArbitrationError, match="SELECTED-RISK"):
        arb.parse_verdict(trailer(p.items[0][0], risk="[MAJOR]"), p)


def test_merged_region_bounds_are_wider_than_either_anchor_window():
    """The property that made under-carrying dangerous: substantiation is checked
    against the merged span, so the merged span is what must be sent."""
    merged = arb.merge_regions([region("a.py", 10), region("a.py", 16)])
    assert len(merged) == 1
    assert (merged[0].lo, merged[0].hi) == (7, 19)
    # anchor 18 is inside the merged span but outside either 7-line window
    assert arb.anchor_within(region("a.py", 18), merged[0])


def test_regions_from_different_commits_are_not_merged():
    """Round-5 blocker: merging across revisions spliced the other commit's tail
    digests onto this commit's body, so a citation into that tail passed
    substantiation against bytes that were never sent."""
    body = [f"L{i}" for i in range(1, 41)]
    tail_differs = list(body)
    tail_differs[19] = "DIFFERENT TAIL"
    a = region("f.py", 10, commit="c1", lines=body, eof=40, context=5)   # [5,15]
    b = region("f.py", 17, commit="c2", lines=tail_differs, eof=40, context=5)  # [12,22]
    merged = arb.merge_regions([a, b])
    assert len(merged) == 2
    assert {r.commit for r in merged} == {"c1", "c2"}
    for r in merged:
        assert len(r.line_digests) == r.hi - r.lo + 1


def test_regions_from_one_commit_still_merge():
    body = [f"L{i}" for i in range(1, 41)]
    a = region("f.py", 10, commit="c1", lines=body, eof=40, context=5)
    b = region("f.py", 17, commit="c1", lines=body, eof=40, context=5)
    merged = arb.merge_regions([a, b])
    assert len(merged) == 1
    assert (merged[0].lo, merged[0].hi) == (5, 22)
    assert len(merged[0].line_digests) == 18


@pytest.mark.parametrize(
    "path",
    ["../escape.py", "a/../b.py", "alias/../f.py", "pkg/sub/../../x.py"],
)
def test_citations_containing_dotdot_are_dropped(path):
    """Round-6 finding: collapsing `..` lexically disagrees with the filesystem
    whenever a directory symlink is involved — `alias/../f.py` reads `sub/f.py` in
    the worktree but normalized to root `f.py`, so the server would substantiate
    against a different file than the decider read."""
    assert arb.parse_citations(f"{path}:4") == ()


def test_dot_segments_are_still_stripped():
    (c,) = arb.parse_citations("./pkg/./mod.py:4")
    assert c.path == "pkg/mod.py"


@pytest.mark.parametrize(
    "path",
    ["/etc/policy.py", "//host/share/x.py", "policy\\choice.py", "C:\\repo\\x.py"],
)
def test_absolute_and_backslash_paths_are_dropped(path):
    """Round-7 blocker, the same class as `..`: rewriting a backslash to '/' maps
    `policy\\choice.py` — a legal, distinct POSIX file — onto `policy/choice.py`, and
    stripping a leading '/' maps `/etc/policy.py` onto tracked `etc/policy.py`. Either
    lets a decider read one file while the server validates another."""
    assert arb.parse_citations(f"{path}:4") == ()


def test_two_distinct_spellings_cannot_resolve_to_one_region():
    slashed = arb.parse_citations("policy/choice.py:4")
    backslashed = arb.parse_citations("policy\\choice.py:4")
    assert len(slashed) == 1
    assert backslashed == ()  # dropped, never folded onto the other file
