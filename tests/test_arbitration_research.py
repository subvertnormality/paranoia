import json

import pytest

from paranoia_local import arbitration_research as ar
from paranoia_local import external_sources as es


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
