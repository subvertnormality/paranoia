from contextvars import ContextVar
from threading import Barrier

from paranoia_local import census_execution as census


def test_collect_joins_all_lanes_in_order_and_carries_context():
    trace = ContextVar("census_test_trace", default="missing")
    token = trace.set("review-context")
    barrier = Barrier(3)
    completed = []

    def run(lane):
        assert trace.get() == "review-context"
        barrier.wait(timeout=5)
        completed.append(lane)
        return census.LaneResult(
            lane, {"lane": lane}, [], [],
            {"class": ["member"]} if lane == "integrity" else {},
        )

    lanes = ("behaviour", "execution", "integrity")
    try:
        result = census.collect(lanes, run)
    finally:
        trace.reset(token)
    assert set(completed) == set(lanes)
    assert [row["lane"] for row in result.manifests] == list(lanes)
    assert result.member_coverage == {"class": ["member"]}
    assert trace.get() == "missing"


def test_namespace_preserves_finding_coverage_and_assessment_bindings():
    manifest = {
        "findings": [{"id": "F1", "severity": "MAJOR", "evidence": ["repository/a:1"]}],
        "coverage": [{"finding_ids": ["F1"]}],
        "class_assessments": [{"class_id": "C1", "finding_id": "F1",
                               "verdict": "violated", "evidence": ["repository/a:1"]}],
    }
    row = census.namespace_lane("integrity", manifest, [], [], {})
    assert row.manifest["findings"][0]["id"] == "integrity:F1"
    assert row.manifest["coverage"][0]["finding_ids"] == ["integrity:F1"]
    assert row.manifest["class_assessments"][0]["finding_id"] == "integrity:F1"
    sources = census.CensusSources.capture([row.manifest])
    assert sources.source_ids == ["integrity:F1"]
    assert sources.assessment_findings == {"C1": "integrity:F1"}
    assert sources.source_evidence == {"integrity:F1": ["repository/a:1"]}
