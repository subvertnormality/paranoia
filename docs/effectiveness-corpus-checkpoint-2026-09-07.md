# Corpus-design checkpoint

The calibrated campaign exposed another genuine parser-control defect at t011.
The implementing agent reproduced it before scoring: NaN, Infinity and -Infinity
in extra coverage metadata return a successful Audit in both strict and partial
modes, although the frozen specification requires malformed JSON rejection.
The independent t012 query reported the same defect plus two reproduced boundary
failures: nested metadata can leak RecursionError instead of AuditError, and
distinct strings with a lone surrogate versus a question mark receive the same
replacement-encoded original-text digest. The repeated t027 query also exposed
a plain ValueError for a 4,301-digit metadata integer, reproduced on Python
3.11.9 with its configured 4,300-digit limit. Exact code and observations are
bound to the corresponding score records and retained campaign archive.

This is an unexpected corpus problem, not a reviewer false positive. The corpus,
specification, oracle and execution records remain frozen. Comparative
qualification is withheld. Under C9 the one scheduled 32-slot campaign is
completed; C10 prohibits another patch-and-rerun campaign under this card.
Production behavior remains unchanged. No independent rating or speedup is
inferred from target detection, and incorrect consequence claims remain review
quality concerns even when the target defect and repair are correct.

The shared root cause is a mismatch between broadly stated extracted parser
contracts and finite calibration examples. More examples can find more faults,
but they do not establish that an arbitrary Python parser is a clean control.
Repeatedly patching those examples after model feedback makes the sample more
familiar without supplying independent evidence of control correctness.

The next corpus decision requires a new acceptance boundary. Options to assess
are a smaller executable input language with independently constructed expected
results; historical defects evaluated for target detection while leaving broad
false-positive precision unclaimed; or a separately curated control set whose
correctness is established before reviewer evaluation. Any narrower domain must
be chosen and frozen prospectively, never used to dismiss these observations.
The benchmark maintainer owns that decision. Andy owns independent acceptance
of new review outputs; approval of earlier model-assisted ratings does not
transfer. Issue 49 remains open.

Scheduling, context preparation and retry opportunities may be measured from
this campaign's preserved timings, but effectiveness acceptance cannot be used
as a speed-candidate gate until the corpus issue is resolved. Preserve reviewer
roles and calls. Further production work still needs credible potential for at
least 20% lower end-to-end time or cost with neither materially worse, or a
substantial maintenance simplification at high confidence.
