import gc
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from paranoia_local import git_objects as objects, inert_tree, orientation
from tests.conftest import git, commit_all


def frame(data, length=40):
    request = objects.BlobRequest(objects.blob_oid(data, length), len(data))
    return request, f"{request.oid} blob {request.size}\n".encode() + data + b"\n"


@pytest.mark.parametrize("length", [40, 64])
def test_complete_binary_empty_duplicate_native_frames(length):
    rows = [frame(data, length) for data in [b"", b"a\0\nb\n", b"a\0\nb\n"]]
    assert objects.decode_batch(b"".join(r[1] for r in rows), [r[0] for r in rows]) == (
        b"", b"a\0\nb\n", b"a\0\nb\n")
    assert objects.decode_batch(b"", []) == ()


@pytest.mark.parametrize("damage", ["id", "size", "type", "hash", "truncated", "delimiter", "trailing", "missing"])
def test_invalid_batch_never_returns_a_valid_prefix(damage):
    first, one = frame(b"first")
    second, two = frame(b"second")
    bad = {
        "id": two.replace(second.oid.encode(), b"0" * 40),
        "size": two.replace(b"blob 6", b"blob 7"),
        "type": two.replace(b"blob", b"tree"),
        "hash": two.replace(b"second", b"SECOND"),
        "truncated": two[:-2],
        "delimiter": two[:-1] + b"!",
        "trailing": two + b"junk",
        "missing": second.oid.encode() + b" missing\n",
    }[damage]
    with pytest.raises(RuntimeError):
        objects.decode_batch(one + bad, [first, second])


@pytest.mark.parametrize("oid,size", [("a\nHEAD", 1), ("A" * 40, 1), ("a" * 39, 1),
                                    ("a" * 40, -1), ("a" * 40, True)])
def test_request_rejects_non_identity_input(oid, size):
    with pytest.raises(RuntimeError):
        objects.BlobRequest(oid, size)


def test_count_byte_boundaries_and_oversized_singleton():
    def request(size):
        return objects.BlobRequest("a" * 40, size)
    assert [len(b) for b in objects.batches([request(0)] * 129)] == [128, 1]
    limit = objects.MAX_BATCH_BYTES
    rows = [request(limit - 1), request(1), request(limit + 1), request(1)]
    assert [sum(r.size for r in b) for b in objects.batches(rows)] == [limit, limit + 1, 1]
    assert list(objects.batches([])) == []


@pytest.mark.parametrize("algorithm", ["sha1", "sha256"])
def test_real_native_batch_round_trip_and_missing_object(tmp_path, algorithm):
    repo = tmp_path / "objects"
    repo.mkdir()
    git(["init", "-q", "--object-format=" + algorithm], repo)
    data = [b"", b"\n\0binary\xff", b"same", b"same"]
    requests = []
    for body in data:
        oid = subprocess.check_output(["git", "hash-object", "-w", "--stdin"],
                                      cwd=repo, input=body).decode().strip()
        requests.append(objects.BlobRequest(oid, len(body)))
    assert list(objects.read_blobs(repo, requests)) == data
    with pytest.raises(RuntimeError):
        objects.read_batch(repo, [objects.BlobRequest("0" * len(requests[0].oid), 1)])


def test_real_wrong_object_type_fails(repo):
    oid = orientation.resolve_head(repo)
    with pytest.raises(RuntimeError):
        objects.read_batch(repo, [objects.BlobRequest(oid, 1)])


@pytest.mark.parametrize("retain", [False, True])
def test_materialize_releases_completed_batches(repo, tmp_path, monkeypatch, retain):
    for n in range(20):
        (repo / f"row-{n}.txt").write_bytes(bytes([n]) * 300)
    commit_all(repo, "multiple batches")
    monkeypatch.setattr(objects, "MAX_BATCH_OBJECTS", 4)
    alive = set()
    saved = []
    admitted = []
    original = objects.read_batch

    class Tracked(bytes):
        def __new__(cls, data):
            value = super().__new__(cls, data)
            alive.add(id(value))
            return value

        def __del__(self):
            alive.discard(id(self))

    def observe(repo, requests):
        gc.collect()
        # The consumer may still hold its immediately preceding rendered blob.
        assert len(alive) <= 1, "completed batch payloads accumulated"
        admitted.append(len(requests))
        values = tuple(Tracked(data) for data in original(repo, requests))
        if retain:
            saved.extend(values)  # Deliberate retention mutant must be detected.
        return values

    monkeypatch.setattr(objects, "read_batch", observe)
    if retain:
        with pytest.raises(AssertionError, match="completed batch"):
            inert_tree.materialize(repo, orientation.resolve_head(repo), tmp_path / "tree")
    else:
        inert_tree.materialize(repo, orientation.resolve_head(repo), tmp_path / "tree")
        assert len(admitted) >= 4
        gc.collect()
        assert not alive
