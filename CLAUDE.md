# Claude repository instructions

@AGENTS.md

`AGENTS.md` is the canonical repository-wide instruction set and must be followed in full.
In particular:

- Write explicit, proportionate stakes before review. "Malicious repository" is ambiguous:
  say whether only its static bytes/configuration are untrusted or whether an active local
  process may race filesystem operations.
- Treat every defect class as an architectural hypothesis to triage, not as an automatic
  patch request.
- Stop for an architecture checkpoint when a class recurs, a late round opens a new
  architectural class, or two review/fix cycles fail to reduce blocking classes.
- Do not expand public guarantees to justify a patch, skip an approved shadow rollout, or
  equate a passing test suite with acceptable architectural growth.
- Preserve accurate claim/evidence state and verdicts ahead of speed, but do not retain
  expensive hardening solely for attacker capabilities that the frozen stakes exclude.
- Do not call a placeholder endpoint, optional plugin, or caller-supplied adapter a completed
  default integration. Exercise the primary capability end to end before convergence, and
  treat a live acceptance failure as an architecture-checkpoint input.
- Keep verification enabled in the approved diagnostic rollout by default. Record live
  true/false, latency, version, and failure evidence before proposing blocking-by-default.
