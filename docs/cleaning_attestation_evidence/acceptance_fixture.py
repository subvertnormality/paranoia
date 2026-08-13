"""Create the inert, self-contained Git repository used by live acceptance runs."""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator


@contextmanager
def repository_fixture() -> Iterator[Path]:
    with TemporaryDirectory(prefix="paranoia-cleaning-acceptance-") as directory:
        repo = Path(directory)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Acceptance Fixture"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "acceptance-fixture@example.invalid"],
            cwd=repo,
            check=True,
        )
        (repo / "README.md").write_text(
            "# Cleaning-attestation acceptance fixture\n\n"
            "This inert repository gives arbitration a stable local Git snapshot. "
            "The complete decision, options, context, stakes, and hints are loaded "
            "from the checked-in audit's raw_input.\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        environment = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-08-13T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-08-13T00:00:00Z",
        }
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "Acceptance fixture"],
            cwd=repo,
            check=True,
            env=environment,
        )
        yield repo
