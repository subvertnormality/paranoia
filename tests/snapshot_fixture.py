"""Independent complete inert snapshot assertions shared by public-handler tests."""
import json
import os

from paranoia_local import inert_git
from tests.conftest import commit_all, git


def populate(repo):
    for name, body in {"binary.dat": b"\0\xff\n", "empty.txt": b"",
                       os.fsdecode(b"odd-\xff\nname.txt"): b"original\n"}.items():
        (repo / name).write_bytes(body)
    (repo / "run.sh").write_text("#!/bin/sh\nexit 0\n")
    (repo / "run.sh").chmod(0o755)
    (repo / "link").symlink_to("run.sh")
    commit_all(repo, "full snapshot fixture")
    head = git(["rev-parse", "HEAD"], repo).strip()
    git(["update-index", "--add", "--cacheinfo", f"160000,{head},submodule"], repo)
    git(["-c", "commit.gpgsign=false", "commit", "-qm", "inert gitlink"], repo)


def assert_complete(repo, root):
    manifest_path = root / "MANIFEST.json"
    history_path = root / "HISTORY.txt"
    manifest = json.loads(manifest_path.read_text())
    snapshot = manifest["snapshot"]
    rows = inert_git.run(repo, ["ls-tree", "-rz", "--full-tree", snapshot]).split(b"\0")
    expected, paths = [], set()
    for row in rows:
        if not row:
            continue
        metadata, raw_path = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        path = os.fsdecode(raw_path)
        paths.add(path)
        if kind == "commit":
            data = b""
            rendered = f"PARANOIA INERT GITLINK OID\n{oid}\n".encode("ascii")
            label = "gitlink"
        else:
            data = inert_git.run(repo, ["cat-file", "blob", oid])
            rendered = b"PARANOIA INERT SYMLINK TARGET\n" + data if mode == "120000" else data
            label = "symlink" if mode == "120000" else "executable" if mode == "100755" else "file"
        target = root / "repository" / path
        assert target.read_bytes() == rendered
        assert target.stat().st_mode & 0o777 == 0o444
        assert not target.is_symlink()
        expected.append({"path": raw_path.decode("utf-8", "backslashreplace"),
                         "mode": mode, "kind": label, "oid": oid, "bytes": len(data)})
    assert manifest == {"snapshot": snapshot, "entries": expected}
    assert {p.relative_to(root / "repository").as_posix()
            for p in (root / "repository").rglob("*") if p.is_file()} == paths
    history = inert_git.text(repo, ["log", "--no-patch", "--max-count=100",
                                    "--format=%H%x09%aI%x09%an%x09%s", snapshot])
    assert history_path.read_bytes() == history.encode("utf-8", "surrogateescape")
    assert manifest_path.stat().st_mode & 0o777 == history_path.stat().st_mode & 0o777 == 0o444
