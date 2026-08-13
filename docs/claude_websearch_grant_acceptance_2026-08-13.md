# Claude evidence-role permission acceptance — 2026-08-13

Frozen operating model: one trusted local operator and trusted OS; repository,
plan, fetched pages, and model output are untrusted data; Claude discovery may
use only native `WebSearch`, repository evidence only `Read,Grep,Glob`, and
binding/text roles no tools. Hostile local races, compromised OS, multitenancy,
and custom transport hardening are excluded. Silent search denial or false
verification is high impact; an explicit recoverable block is acceptable.

Environment: Claude Code 2.1.197, `claude-haiku-4-5-20251001`.

- Discovery used matching `--tools WebSearch --allowedTools WebSearch` under
  `--safe-mode --setting-sources "" --strict-mcp-config`. It completed one real
  WebSearch (`modelUsage.webSearchRequests: 1`) with no permission denials in
  16.019 seconds, costing $0.0376802.
- The tool-less profile used matching empty availability and permission lists.
  An explicit WebSearch request executed zero searches; the unavailable tool
  could only appear as model text. It completed in 2.157 seconds, costing
  $0.004629.
- Provider calls: 2. Combined provider duration: 18.176 seconds. Combined cost:
  $0.0423092.
- Tests: 34 focused engine/instrumentation tests passed; the full suite passed
  950 tests in 92.62 seconds.
- Production diff: one file, `src/paranoia_local/engines.py`, +18/-3. It is the
  only touched production module and contains 544 lines after the change.

The discovery result proves the required permission grant works on the pinned
CLI. The tool-less result proves the empty role surface remains unavailable; it
does not rely on a permission-denial event because an unavailable tool is never
offered to Claude Code.
