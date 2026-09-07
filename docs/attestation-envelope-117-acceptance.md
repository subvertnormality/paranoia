# Issue 117 acceptance

Native public verified-plan acceptance is complete. The final call returned one combined
NOT-BLOCKED verdict; durable state has one supported claim, zero blocking structural debt,
and the fixture class closed. Two server-captured primary sources received independent
positive authority and entailment judgments. A third source was successfully captured
and bound as context, then intentionally excluded from governing attestation.

The final native source is 85f54b6388da2991972d4b3473503027c8c0d6a9, with the same complete
production inventory as the original f743559 checkpoint. The final segment made four
calls without retries: discovery, binding, cold attestation, cold structural final.
The complete campaign spent eighteen calls including the original fixture failure and
both undersized-budget continuations. Standing approval authorized completion; no
runtime timeout, reviewer role, retry or evidence policy changed.

The immutable complete-run archive is attestation-envelope-117-complete-evidence.tar.gz
(64,253 bytes), SHA-256
`3132b2d705956ac23f91f39ba8b5e78642d9e5bf82db6dcbaa0253635e373f70`.
It includes the original failed qualification: the harness incorrectly required positive
attestation for even a context-only source after the public result was already
clear. At 164aff9, the corrected acceptance check revalidated that exact archive with
zero additional provider calls. The separate native-qualification JSON records the
native source and qualification source. Neither original records nor historical
acceptances were relabeled as newly executed.

The retained archive chain also includes native, continuation and final-budget evidence.
The final-budget archive SHA-256 is
`0832e48413041fc0921bf6138bd4ddfa0fb859fd4b029c24a41c5fc4ed8448ee`.
Existing checkpoint reports describe their historical failures. New controls reject
edited parents, changed production inventories, excess cumulative calls, missing
governing authority, missing entailment, context-only evidence and an unverified verdict.

At 164aff9, 38 issue-specific tests passed. The preceding complete regression run passed
2,214 tests in 203.94 seconds; the final delivery run and Codex CODE convergence are
recorded separately. This repair improves authoring reliability; it does not guarantee
that every future model reply is valid and makes no general latency claim.

Delivery gate: all 2,215 tests passed in 256.99 seconds. Codex CODE round 1 returned
NOT-BLOCKED with zero blocking classes, four calls and no retries; session
01a07d4e-1a8b-70f3-bcdd-9c4b65efbb39, bound plan digest
4ff0c260d1875c20a43ebf40a03c1da614358ed59a33c8b25e4b36fe8542afe8.

Factual erratum from that CODE review: the frozen execution narrative at plan lines
139-145 and the initial certificate scope mislabeled the third context-only source as
a capture failure. Its retained provenance has HTTP 200, capture digests and no error;
it was successfully bound as context, then intentionally excluded from governing
attestation. The server's generic negative attestation placeholder was not evidence of
a capture failure. This run therefore proves supported closure with context exclusion,
not recovery from a failed capture. The report, scope generator and published certificate
now state that accurately. Original archives, native verdicts, qualification identities
and the frozen plan contract remain unchanged. No new provider run was needed.
