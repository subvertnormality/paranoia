# Sessionless discovery correction

The full merge CODE cold final found that a successful discovery process with no session could return a supported-looking claim audit directly to reconciliation. This pre-existing defect violated the captured-evidence lifecycle in the accepted contract.

Both initial discovery and its one correction now pass the same required-session gate. Missing metadata becomes local validation failure, preserving native stdout, structured detail, stderr, actual return code, timing and usage. The existing claim-debt owner retains prior history and ordered discovery attempts. No additional provider call, persistence mechanism, or evidence fallback is introduced.

The public-handler regression failed before the fix because the claim state was unblocked. Eight cases now cover Codex and Claude, initial and corrected discovery, and empty versus prior claim debt. Each runs the real handler and durable settlement with deterministic provider replies, verifies combined blocking despite clean structural output, and rejects any capture/binding admission. Existing Issue 114 success coverage still traverses capture, binding and cold attestation. The focused eleven-test selection passed.

These are deterministic lifecycle checks, not a new live plan review or a claim of faster provider execution. Full regression and continued CODE convergence are required before merge.
