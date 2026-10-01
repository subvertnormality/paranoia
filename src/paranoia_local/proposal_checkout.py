"""Filter-free regular-file identity for supplemental proposal cleanliness.

Only canonical, extension-free v1 LFS pointers gain a content equivalence path.
This does not turn smudged bytes into proposal sources or application preimages.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from . import git_objects, inert_git

READ_CHUNK_BYTES = 1024 * 1024
LFS_POINTER_LIMIT = 1024  # Git LFS spec: pointer bytes must be strictly below this.
_LFS_POINTER = re.compile(
    rb"version https://git-lfs.github.com/spec/v1\n"
    rb"oid sha256:([0-9a-f]{64})\n"
    rb"size (0|[1-9][0-9]*)\n"
)


def regular_file_matches(
    repo: Path, path: Path, raw_path: bytes, oid: str, blob_size: int,
    checkout_size: int,
) -> bool:
    """Verify exact Git bytes, or exact content named by an indexed LFS pointer.

    HEAD/index and filesystem/mode checks belong to the caller. Object, attribute
    and read failures propagate to its existing phase-specific failure handling.
    Neither the Git operations here nor hashing execute configured filters.
    """
    git_objects.validate_oid(oid)
    digest = hashlib.new({40: "sha1", 64: "sha256"}[len(oid)])
    digest.update(f"blob {checkout_size}\0".encode("ascii"))
    content_digest = hashlib.sha256()
    observed_size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(READ_CHUNK_BYTES):
            observed_size += len(chunk)
            digest.update(chunk)
            content_digest.update(chunk)
    if observed_size != checkout_size:
        return False
    if digest.hexdigest() == oid:
        return True
    if not 0 < blob_size < LFS_POINTER_LIMIT:
        return False
    pointer, = git_objects.read_batch(repo, [git_objects.BlobRequest(oid, blob_size)])
    match = _LFS_POINTER.fullmatch(pointer)
    if match is None or int(match[2]) != observed_size:
        return False
    if content_digest.hexdigest().encode("ascii") != match[1]:
        return False
    # --cached reads the index, already checked against HEAD. NUL stdin/output
    # handles every tracked path literally, including newlines and non-ASCII.
    attributes = inert_git.run(
        repo, ["check-attr", "-z", "--cached", "--stdin", "filter"],
        input_bytes=raw_path + b"\0",
    )
    return attributes == raw_path + b"\0filter\0lfs\0"
