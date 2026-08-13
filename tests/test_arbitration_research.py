import json
import re

import pytest

from paranoia_local import arbitration_research as ar
from paranoia_local import external_sources as es
from paranoia_local import prompts


def discovery(proposition="The API retries twice.", url="https://docs.example.com/api"):
    return ar.DISCOVERY_MARKER + "\n" + json.dumps({"claims": [{
        "kind": "behavior",
        "proposition": proposition,
        "candidate": {
            "url": url,
            "title": "API docs",
            "publisher": "Example",
            "source_kind": "primary",
            "authority_basis": "Example defines the API",
            "relation": "supports_claim",
        },
    }]})


def captured(claim):
    return es.Capture(
        claim.candidate, claim.candidate.url, 200, "text/html", "a" * 64, "b" * 64,
        "API behavior\nThe API retries twice.\nEnd",
    )


def test_discovery_rejects_duplicate_normalized_propositions():
    value = json.loads(discovery().split("\n", 1)[1])
    value["claims"].append(dict(value["claims"][0]))
    with pytest.raises(ar.ResearchError, match="duplicate"):
        ar.parse_discovery(ar.DISCOVERY_MARKER + "\n" + json.dumps(value))


def test_discovery_rejects_caller_id_leakage():
    with pytest.raises(ar.ResearchError, match="reserved"):
        ar.parse_discovery(discovery("opt-a is faster"), forbidden=["opt-a"])


def test_binding_requires_exact_captured_passage():
    claims = ar.parse_discovery(discovery())
    captures = [captured(claims[0])]
    bad = ar.BINDING_MARKER + "\n" + json.dumps({"bindings": [{
        "claim_index": 0, "usable": True, "location": "API behavior",
        "passage": "The API retries three times.",
    }]})
    with pytest.raises(ar.ResearchError, match="not in captured"):
        ar.parse_binding(bad, claims, captures)


def test_packet_union_is_deterministic_and_governing():
    claims = ar.parse_discovery(discovery())
    captures = [captured(claims[0])]
    reply = ar.BINDING_MARKER + "\n" + json.dumps({"bindings": [{
        "claim_index": 0, "usable": True, "location": "API behavior",
        "passage": "The API retries twice.",
    }]})
    bound = ar.parse_binding(reply, claims, captures)
    packets = ar.packets([(claims, bound), (claims, bound)])
    assert len(packets) == 1
    assert packets[0].governing
    assert ar.digest(packets) == ar.digest(tuple(reversed(packets)))


def test_packet_digest_is_total_on_model_controlled_surrogates():
    claims = ar.parse_discovery(discovery())
    capture = captured(claims[0])
    bound = es.BoundSource(
        claims[0].candidate, capture, "section-\udcff",
        "The API retries twice.",
    )
    packets = ar.packets([(claims, (bound,))])
    assert "\udcff" in ar.render(packets)
    assert len(ar.digest(packets)) == 64


def test_discovery_prompt_contains_no_pipe_delimited_pseudo_enum():
    assert not re.search(
        r'"(?:kind|source_kind|relation)":"[^"]*\|[^"]*"',
        prompts.ARBITRATION_DISCOVERY_INSTRUCTIONS,
    )


def test_a_markdown_fenced_binding_parses_like_a_bare_one():
    """The research phase takes the same fence as the settlement parser did.

    Measured 2026-08-13: an arbitration this delivery needed returned
    `ResearchError: invalid JSON after === EVIDENCE BINDING JSON ===` twice on
    `claude-opus-5`, at different offsets, with `ROUNDS: 0` — the deciders never
    voted. The engine had wrapped the object in a fence, exactly as it does for
    settlements, and `raw_decode` stops at the first backtick.
    """
    claims = ar.parse_discovery(discovery())
    captures = [captured(claims[0])]
    body = json.dumps({"bindings": [{
        "claim_index": 0, "usable": True, "location": "API behavior",
        "passage": "The API retries twice.",
    }]})
    bare = f"{ar.BINDING_MARKER}\n{body}"
    for opening in ("```json", "```"):
        fenced = f"{ar.BINDING_MARKER}\n{opening}\n{body}\n```"
        assert (ar.parse_binding(fenced, claims, captures)
                == ar.parse_binding(bare, claims, captures))


def test_a_fenced_discovery_payload_parses_too():
    """Discovery shares the extractor, so it gains the same tolerance."""
    bare = discovery()
    marker, body = bare.split("\n", 1)
    assert (ar.parse_discovery(f"{marker}\n```json\n{body}\n```")
            == ar.parse_discovery(bare))


def test_binding_accepts_only_a_missing_outer_object_close():
    claims = ar.parse_discovery(discovery())
    captures = [captured(claims[0])]
    body = json.dumps({"bindings": [{
        "claim_index": 0, "usable": True, "location": "API behavior",
        "passage": "The API retries twice.",
    }]})
    complete = ar.parse_binding(f"{ar.BINDING_MARKER}\n{body}", claims, captures)

    assert ar.parse_binding(
        f"{ar.BINDING_MARKER}\n{body[:-1]}", claims, captures,
    ) == complete


@pytest.mark.parametrize(
    "broken",
    [
        '{"bindings":[{"claim_index":0 "usable":false}]}',
        '{"bindings":[{"claim_index":0,"usable":false]',
        '{"bindings":[{"claim_index":0,"usable":"unterminated}]}',
    ],
)
def test_binding_does_not_guess_at_internal_or_multi_character_json_repairs(broken):
    claims = ar.parse_discovery(discovery())
    captures = [captured(claims[0])]
    with pytest.raises(ar.ResearchError, match="invalid JSON"):
        ar.parse_binding(f"{ar.BINDING_MARKER}\n{broken}", claims, captures)
