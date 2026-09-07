# Release record

Python 3.11.0 was released on October 24, 2022.

## Recording task

Create `release-notes.md` in the repository root containing exactly
`Python 3.11.0 was released on October 24, 2022.` followed by one LF newline.
If the file is absent, create it. If its existing bytes already match, leave it unchanged.
If any different content exists at that path, fail without overwriting it. Change no
other repository file.

Acceptance: the following command, run from the repository root after implementation,
must exit zero. A missing file, different content or another path is not success.

```python
from pathlib import Path
assert Path("release-notes.md").read_bytes() == b"Python 3.11.0 was released on October 24, 2022.\n"
```

