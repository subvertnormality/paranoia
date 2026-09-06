"""Inventory historical provider evidence at its immutable source revision.

New modules are covered by current acceptance, never retroactively attributed to
an old provider run. Existing per-file later-diff checks still bind all changes to
the historical inventory.
"""
import subprocess
from pathlib import Path


def historical_inventory(root: Path, revision: str, configured) -> set[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", "src/paranoia_local"],
        cwd=root, check=True, capture_output=True, text=True,
    )
    package = {name for name in result.stdout.splitlines()
               if name.startswith("src/paranoia_local/")
               and name.count("/") == 2 and name.endswith(".py")}
    if not package:
        raise ValueError("historical package inventory is empty")
    return package | {name for name in configured
                      if not name.startswith("src/paranoia_local/")}
