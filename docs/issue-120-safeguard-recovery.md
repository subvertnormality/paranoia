# Issue 120: Claude safeguard refusal recovery

Issue #120 reported a benign Python verification request rejected by the fixed
Claude Opus arbitration cleaner before attestation or voting. The existing
failure semantics were correct: `ARBITRATION: FAILED`, `SELECTED: none`,
`ROUNDS: 0`, and `CLEANING: cleaner-rejected`. The missing behavior was an
actionable, supported recovery path.

The runtime now recognizes the terminal provider diagnostic
`<Claude model>'s safeguards flagged this message` only on failed Claude calls.
It adds guidance to the rendered failure but does not alter the provider's raw
text, failure detail, stderr, return code, audit record, call count, role, or
model. Successful prose, other engines, unrelated errors, and prefixed quoted
descriptions are not reclassified.

Recovery remains fail-closed:

1. Preserve the failed audit and do not treat it as a decision or convergence.
2. After the bounded retry, do not replay the unchanged request or try to bypass
   the safeguard.
3. Start a new arbitration with a faithful, neutral restatement that removes
   accidental trigger wording, or report the false positive to provider support.
4. Do not use `models.claude` as a cleaner workaround. That mapping affects
   Claude research and voting, not the separate cleaner or attester role.
   `cleaner_model` is an explicit API override, but changing it to evade a
   safeguard is unsupported.

`tests/test_provider_quota.py` covers exact recognition, negative controls,
unchanged provider-channel retention, and the public pre-vote arbitration
failure trailer and audit.
