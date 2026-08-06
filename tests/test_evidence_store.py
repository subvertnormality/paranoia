from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from paranoia_local import class_closure as cc
from paranoia_local.evidence_store import (
    EvidenceCommitAmbiguous,
    EvidenceStore,
    EvidenceStoreError,
)


def test_staged_bytes_are_exact_and_rooted_until_commit_or_abort(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path, orphan_ttl_seconds=0)
    digest = store.stage("run-1", b"\xffexact\r\n")
    assert store.read(digest) == b"\xffexact\r\n"
    store.gc(now=100)
    assert store.read(digest) == b"\xffexact\r\n", "in-flight journal is a GC root"
    store.adopt("lineage", "run-1", [digest])
    assert not (tmp_path / "journals" / "run-1.json").exists()
    store.gc(now=100)
    assert store.read(digest) == b"\xffexact\r\n", "lineage manifest is a GC root"


def test_unadopted_aborted_blob_is_swept_only_after_ttl(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path, orphan_ttl_seconds=10)
    digest = store.stage("run-2", b"orphan", now=10)
    store.abort("run-2")
    store.gc(now=19)
    assert store.read(digest) == b"orphan"
    store.gc(now=21)
    with pytest.raises(EvidenceStoreError, match="missing"):
        store.read(digest)


def test_quarantined_lineage_keeps_last_valid_root_manifest(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path, orphan_ttl_seconds=0)
    digest = store.stage("run-3", b"repairable")
    store.adopt("lineage", "run-3", [digest])
    store.quarantine("lineage")
    store.gc(now=100)
    assert store.read(digest) == b"repairable"


def test_capacity_reservation_is_enforced_under_the_global_lock(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path, global_cap=8, lineage_cap=8)
    store.stage("one", b"123456")
    with pytest.raises(EvidenceStoreError, match="global evidence cap"):
        store.stage("two", b"abcdef")


def test_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    digest = store.stage("run", b"trusted")
    (tmp_path / "sha256" / digest).write_bytes(b"tampered")
    with pytest.raises(EvidenceStoreError, match="hash mismatch"):
        store.read(digest)


def test_prepublication_state_failure_is_recoverable_and_removes_candidate(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path, orphan_ttl_seconds=0)
    store.begin("run-safe-failure")
    digest = store.stage("run-safe-failure", b"still-rooted")

    def fail() -> None:
        raise cc.StateUnavailable("temporary-file fsync failed")

    with pytest.raises(EvidenceStoreError, match="before atomic publication"):
        store.commit_state("lineage", "run-safe-failure", [digest], fail)
    assert (tmp_path / "journals" / "run-safe-failure.json").exists()
    assert not list((tmp_path / "roots").glob("lineage.candidate-*.json"))
    store.gc(now=100)
    assert store.read(digest) == b"still-rooted"


def test_ambiguous_state_commit_keeps_journal_and_candidate_as_gc_roots(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path, orphan_ttl_seconds=0)
    store.begin("run-ambiguous")
    digest = store.stage("run-ambiguous", b"still-rooted")

    def fail() -> None:
        raise cc.StatePublicationAmbiguous("replace outcome unknown")

    with pytest.raises(EvidenceCommitAmbiguous):
        store.commit_state("lineage", "run-ambiguous", [digest], fail)
    assert (tmp_path / "journals" / "run-ambiguous.json").exists()
    assert list((tmp_path / "roots").glob("lineage.candidate-*.json"))
    store.gc(now=100)
    assert store.read(digest) == b"still-rooted"


def test_deep_manifest_json_is_normalized_to_store_error(tmp_path: Path) -> None:
    path = tmp_path / "deep.json"
    path.write_text("[" * 2000 + "0" + "]" * 2000)
    with pytest.raises(EvidenceStoreError, match="manifest"):
        EvidenceStore._read_manifest(path)


def test_new_root_replaces_dropped_evidence_instead_of_growing_forever(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path, orphan_ttl_seconds=0)
    old = store.stage("old-run", b"expired")
    store.adopt("lineage", "old-run", [old])
    new = store.stage("new-run", b"current")
    store.commit_state("lineage", "new-run", [new], lambda: None)
    manifest = json.loads((tmp_path / "roots" / "lineage.json").read_text())
    assert manifest["digests"] == [new]
    store.gc(now=10**12)
    with pytest.raises(EvidenceStoreError, match="missing"):
        store.read(old)
    assert store.read(new) == b"current"


def test_first_evidence_root_creation_fsyncs_its_parent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence_root = tmp_path / "new" / "evidence"
    calls: list[Path] = []
    original = EvidenceStore._fsync_dir

    def record(path: Path) -> None:
        calls.append(Path(path))
        original(Path(path))

    monkeypatch.setattr(EvidenceStore, "_fsync_dir", staticmethod(record))
    store = EvidenceStore(evidence_root)
    store.begin("first")
    assert tmp_path in calls
    assert evidence_root.parent in calls
    assert evidence_root in calls
    before_stage = len(calls)
    store.stage("first", b"blob")
    assert evidence_root in calls[before_stage:], "sha256 directory entry must be fsynced"
