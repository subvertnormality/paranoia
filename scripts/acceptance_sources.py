"""Inventory historical provider evidence at its immutable source revision.

New modules are covered by current acceptance, never retroactively attributed to
an old provider run. Existing per-file later-diff checks still bind all changes to
the historical inventory.
"""
import subprocess
from pathlib import Path


# These modules are not executed by the retained structural-only class fixtures.
# Their original blobs remain checked. Issue 146 separately qualifies current
# capture/research behavior; an old structural run cannot qualify that behavior.
HISTORICAL_CLASS_CONTEXT = frozenset({
    "src/paranoia_local/arbitration_research.py",
    "src/paranoia_local/external_sources.py",
})


def current_class_source_required(relative: str, existing_allowances: dict) -> bool:
    """Keep existing deltas exact; do not invent new allowances for unrelated roles."""
    return relative not in HISTORICAL_CLASS_CONTEXT or relative in existing_allowances


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
