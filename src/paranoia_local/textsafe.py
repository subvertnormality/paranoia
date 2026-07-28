"""Display-safe rendering of `surrogateescape`-decoded text.

`git` paths and file contents are bytes, not Unicode. We decode them with
`surrogateescape` so the exact bytes round-trip back to git, which means the
resulting `str` can carry lone surrogates. Those crash UTF-8/JSON encoding — and
both reviewer runners write stdin in text mode — so nothing decoded that way may
be rendered into a packet, footer or trailer directly.
"""

from __future__ import annotations


def display(name: str) -> str:
    """A display-safe, INJECTIVE rendering of possibly `surrogateescape`-decoded text.

    Valid Unicode (e.g. `café.py`) is kept; a literal backslash is doubled first so it
    can't be confused with an escape introducer, then non-UTF-8 bytes carried as
    surrogates become `\\u….` escapes. The result therefore can't (a) collide two
    distinct inputs onto one label (a real `a\\udcff` vs a `0xff`-byte path stay
    distinct), or (b) inject lone surrogates that crash UTF-8 encoding of the packet
    or the reviewer prompt stdin.
    """
    return name.replace("\\", "\\\\").encode("utf-8", "backslashreplace").decode("utf-8")
