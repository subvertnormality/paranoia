# Brief: class closure — make a defect *class* a tracked object, not an operator inference

Status: DRAFT for review, revision 2. One codex plan-review round folded — 3 FATAL,
15 MAJOR, 2 MINOR. Every finding accepted. Round 1's three FATALs were not
patchable: they killed the candidate-enumeration design outright and it has been
replaced (§2.1), which in turn deleted five of the MAJORs rather than answering
them.

## 0. The defect this fixes

A real ten-round `critique_branch` loop against Parallax
(`runbook-v2-card-execution`, base `91f920a`, ten records in `~/.paranoia/logs/`
between `20260728T142314` and `20260728T162438`) produced findings per round of
7 → 9 → 5 → 2 → 2 → 2 → 3 → 2 → 1. Rounds 7, 8 and 9 were **the same defect three
times**: the v2 "is anything open?" predicate was incomplete — round 7 found
escalations missing from it, round 8 ungated progress, round 9 unresolved starts.
Three sites, one invariant, three rounds, three instance-shaped fixes.

The operator was not being careless. **The protocol gives the class nowhere to
live.** Three mechanisms in this repository produce that outcome:

1. **The finding schema is instance-shaped.** `prompts._SECTION_BODIES` asks each
   finding for `file:line`, the failure mechanism, and the observable symptom. It
   never asks for the invariant, and never asks where else the invariant is
   violated. The reviewer *derives* the class in order to find the instance, then
   the protocol discards it. A remedy inferred from an instance-shaped finding is
   instance-shaped.
2. **The only cross-round channel does not carry classes.** `already_raised`
   (`orientation.build_orientation`, `orientation.build_packet`,
   `handlers._plan_body`) is the sole memory between rounds, and it renders as
   `=== Already-raised — do NOT restate these; hunt for what they missed ===`.
   Nothing *prohibits* a reviewer from finding a sibling violation — `prompts`
   also tells it to follow the blast radius — but the channel carries no class
   state and its instruction points away from re-checking a site already reported.
   Round 8 had no way to know it was re-reporting round 7's invariant.
3. **The severity floor meters the leak.** `prompts._CALIBRATION` tells round ≥ 3
   to withhold everything below `[MAJOR]`. A class surviving at a new site only
   surfaces when that individual site clears the floor — which is the one-per-round
   trickle observed at rounds 7–9.

There is no lineage state of any kind: `logs.write_log` writes one record per
call and nothing links round 9 to round 7.

**This is the same shape as the `arbitrate` substantiation defect fixed in #9** —
a per-instance check with the general rule left to interpretation.

## 1. What the fix must achieve, and what it must not claim

**Must achieve.** A class reported in round N is a durable object with a
*mechanically re-checkable* membership predicate. Round N+1 re-runs that
predicate itself. A surviving match is a recurrence, is exempt from the severity
floor, and **blocks the round from being reported converged** — computed in
Python, not asserted by the reviewer and not inferred by the operator.

**Must NOT claim.** The mechanism only asserts the *negative*. "No class is
unclosed" is not "the change is correct" — new findings remain the reviewer's
judgement. The trailer therefore never emits a positive convergence verdict; it
emits `BLOCKED` or `NOT-BLOCKED` and says which. Wording that reads as
"converged" would launder a mechanical check into an approval — the `arbitrate`
failure mode in a new costume.

**Must not become a termination trap.** A mechanism that can block indefinitely
on marginal findings would reproduce the failure it exists to prevent, in a form
the operator cannot escape. §2.9 bounds what may block.

## 2. Mechanism

### 2.1 The predicate matches violations only

*Round 1 [FATAL]: revision 1 defined the predicate as matching every candidate
site — violating and conforming alike — then required the reviewer to adjudicate
each match, and made the class identity the candidate regex. Two distinct
invariants over the same syntax collapsed to one class; git could recheck only
candidate presence, never whether the invariant was still violated; and the
register had no way to express which of several matches in one file a given
adjudication referred to. Revision 2 takes round 1's own remedy.*

**A mechanized class's predicate is a regex that matches only violations.
Closure is exactly: zero matches.**

This deletes the entire adjudication apparatus — no `SITES` verdicts, no
conforming whitelist, no site identity in the closure algorithm, no
line-number-versus-text matching problem, and no "broad pattern blocks forever"
trap. It buys that at a real cost, stated plainly: **more invariants will be
inexpressible and fall to `unmechanized` (§2.10), which is materially weaker.**
That trade is correct — a check that cannot be wrong about closure is worth more
than a check with wider reach and an adjudication layer that can silently
whitelist a live defect.

### 2.2 Findings declare their scope

Every finding in "What doesn't work" and "Gaps" carries `SCOPE: isolated` or
`SCOPE: class`.

`SCOPE: class` means *the reasoning that condemned this site would condemn
another site if one existed*. A genuine off-by-one is `isolated`; requiring class
machinery for it is the over-engineering `prompts.CODE_REVIEW_INSTRUCTIONS`
already calls a defect.

### 2.3 The class register

The review ends with a machine-readable block — one record per class, following
the `arbitrate` trailer idiom. Mechanized:

```
=== CLASS REGISTER ===
CLASS: <the invariant, one line, stated without reference to any site>
SEVERITY: BLOCKER|MAJOR|MINOR|OUT-OF-SCOPE
PATTERN: <POSIX-extended regex matching VIOLATIONS ONLY>
PATHSPEC: <git pathspec, or . for the whole tree>
```

Unmechanized:

```
CLASS: <the invariant, one line>
SEVERITY: BLOCKER|MAJOR|MINOR|OUT-OF-SCOPE
PROCEDURE: <what a reviewer must do to find every violation>
```

References to classes the server already carries:

```
RECURRENCE: <class-id>          # this round's finding is an instance of it
CLOSED: <class-id>              # unmechanized only; judged closed this round
SUPERSEDED-BY: <class-id> | PATTERN: <regex> PATHSPEC: <pathspec>
```

**The register is mandatory.** A review with no classes must emit
`=== CLASS REGISTER ===` followed by `NONE`.

*Round 1 [FATAL]: revision 1 made an absent register fail open, which contradicts
the durability guarantee — a reviewer could report a class in prose, omit the
block, and have it neither tracked nor blocking.* An absent or unparseable
register now yields `CONVERGENCE: BLOCKED — class register absent/malformed`.
**The review text is still returned in full** — a paid review is never discarded
over a formatting miss — but the round cannot be reported unblocked, so the
operator either re-runs or exempts explicitly. Parsing is as strict as
`arbitration.parse_*`: the block is terminal, every field required, duplicates
and out-of-block records rejected.

### 2.4 Class identity is server-assigned

*Round 1 [MAJOR]: revision 1 hashed the reviewer's regex into the id, so a
corrected predicate minted a new class and the old one blocked forever, and
unmechanized classes had no id at all yet were required to be closed by id.*

The server assigns `class_id` (8 hex chars) at first registration and it never
changes. Reviewer-authored text never determines identity, so it does not matter
that round 7 called the class "escalations" and round 9 "unresolved starts" — a
label match would never have connected them anyway.

Two guards against duplicate registration of one class: the open classes are
shown to every subsequent reviewer with their ids and invariants, with the
instruction to emit `RECURRENCE: <id>` rather than register a new class; and the
server dedupes on identical normalized `(pattern, pathspec)` at registration.

A corrected predicate is registered with `SUPERSEDED-BY`, which marks the old
class `superseded` (non-blocking) and carries its `first_round` forward. This is
the recovery transition `malformed` and `over-broad` classes need.

### 2.5 The git invocation

The predicate is *data*, never an argv:

```
git grep -I -z -n -E --no-color -e <pattern> <snapshot-commit> -- <pathspec>
```

`shell=False`, no pipes, no redirection, no reviewer-chosen binary or flags. This
removes model-authored command execution from the design rather than sanitising
it. `git` is already a hard prerequisite; `rg` is not present on the reference
machine and is not introduced. `git grep <commit>` reads the tree directly — no
checkout needed.

**Verified empirically in this repository today:**

- `-z` output is `<commit>:<path>\0<line>\0<text>\n`. Paths are NUL-terminated,
  so paths containing newlines or non-UTF-8 bytes parse unambiguously. Decode
  with `surrogateescape`, matching the `orientation`/`evidence` precedent.
  *(Round 1 [MINOR]: revision 1 omitted `-z` and would have mis-parsed such paths.)*
- Exit codes: `0` = matches, `1` = **no matches, which is success and means
  closed**, `≥2` = error. A malformed ERE exits `128` with
  `fatal: -e option, 'a[': Invalid regular expression`.
- Pathspec magic is accepted and silently changes the result set:
  `git grep -E -e x main -- ':(exclude)src'` returned matches from outside `src`.
  A pathspec beginning with `:` is therefore **rejected at parse time** and the
  class recorded `malformed`.

**Bounds and their outcomes.** Per-class 10 s timeout and a 200-match cap. Under
violation-only semantics, many matches means many violations, so the cap is an
output bound, not a verdict: the class blocks, the block text is truncated with a
count. A regex exceeding the cap is additionally recorded `over-broad` so the
reviewer is prompted to narrow it via `SUPERSEDED-BY`. Timeout, exit ≥ 2, and
invalid ERE all record the class `malformed` and **block** — a predicate that
cannot run has not proved closure. *(Round 1 [MAJOR] gap: none of these were
specified or tested.)*

### 2.6 The closure check

Each round, for **every** mechanized class the lineage holds — `open`, `closed`,
`over-broad`, or `malformed`, but not `superseded` — the server runs the
invocation above against the snapshot commit under review, subtracts recorded
exemptions (§2.8), and:

- zero matches → `closed`
- any match → `open`, and every match is a recurrence

*Round 1 [MAJOR]: revision 1 rechecked only `open` classes and treated closure as
permanent, so a later fix could reintroduce the defect while the trailer still
reported nothing unclosed.* **A closed class reopens on any new match.** The cost
of rechecking everything is one bounded git query per class per round.

### 2.7 Lineage state

`~/.paranoia/lineages/<lineage_id>.json`, holding per class: `class_id`,
`invariant`, `severity`, `pattern`/`pathspec` or `procedure`, `first_round`,
`status`, `superseded_by`, and exemptions.

*Round 1 [MAJOR]: revision 1 derived the lineage from repo + `base_ref` only, so
two sequential feature branches reviewed against `main` would inherit each
other's classes and exemptions.* `lineage_id` defaults to
`sha256(resolved_repo_path, base_ref, head_branch)[:12]`, where `head_branch`
comes from `git symbolic-ref --quiet HEAD` (verified: exits 0 with
`refs/heads/<name>`). **On a detached HEAD there is no stable branch identity, so
an explicit `lineage` argument is required and the call errors without one** —
fail-closed rather than silently minting a fresh lineage every round. Every
trailer prints `LINEAGE: <id> (rounds recorded: N)` so an unintended split is
visible.

*Round 1 [MAJOR] risk: revision 1 said only when state is written, and
`logs.write_log` sets a precedent of swallowing every write failure —
deliberately, since a completed review is the expensive artifact.* **Lineage
state must not follow that precedent**, because a silently lost write plus a
`NOT-BLOCKED` footer is exactly the false clearance this design exists to
prevent. State is read before the engine call and written after a successful one,
via temp file + `os.replace` in the same directory. A write failure, or existing
state that will not parse, yields `CLASS-CLOSURE: STATE-UNAVAILABLE` and
`CONVERGENCE: BLOCKED`. The review text is still returned.

### 2.8 Exemptions

A match that is a false positive of the regex is exempted by an `exempt` call
argument of `(class_id, path, line_text)`; the server stores a fingerprint of the
normalized line text. *Round 1 [MAJOR]: revision 1 keyed exemptions on
`class_id` + path alone, so exempting one match suppressed every present and
future match in that file.*

Exemptions are echoed in every subsequent trailer and shown to every subsequent
reviewer under `=== CLAIMED EXEMPT ===` for challenge. This is the one place
operator judgement legitimately enters, and the design makes it a recorded,
adversarially-reviewed artifact rather than a silent lapse.

### 2.9 What may block, and the severity grammar

*Round 1 [MAJOR]: revision 1 made every recurrence merge-blocking "whatever the
severity", so a class originating as `[MINOR]` or `[OUT-OF-SCOPE]` could prevent
termination indefinitely — the termination trap §1 forbids.*

**Only classes registered `SEVERITY: BLOCKER` or `MAJOR` block.** `MINOR` and
`OUT-OF-SCOPE` classes are tracked and reported as advisory; they never appear in
`CONVERGENCE: BLOCKED`. This keeps the mechanism inside the same severity
economy `_CALIBRATION` already runs on.

*Round 1 [MAJOR]: revision 1 told reviewers to emit `[RECURRENCE]` while
`prompts.CODE_REVIEW_INSTRUCTIONS` requires exactly one of
`[BLOCKER]`/`[MAJOR]`/`[MINOR]`/`[OUT-OF-SCOPE]` per finding.* Recurrence is
**not** a severity tag. It is a marker adjacent to one:
`[MAJOR] [RECURRENCE 3f2a91c4] …`. The existing grammar is untouched, and a
recurrence of a blocking class is reported at `[MAJOR]` or higher.

`_CALIBRATION` gains: *the ROUND severity floor never applies to a finding marked
`[RECURRENCE]`.*

### 2.10 Unmechanized classes

Registered with `PROCEDURE:` instead of `PATTERN:`/`PATHSPEC:`, given a server
id like any other class, carried forward as a reviewer obligation, always shown,
never floor-suppressed, and marked `unmechanized` in the trailer so the weakness
is visible. They cannot block mechanically — there is nothing to run — and they
close only when a later reviewer names the id on a `CLOSED:` line: still a
judgement, but an explicit, cold, recorded one rather than an operator's silent
assumption.

### 2.11 The computed trailer, and the `CONVERGED` collision

Appended by `handlers._footer`:

```
LINEAGE: <id> (rounds recorded: N)
CLASS-REGISTER: parsed 3 | NONE | absent | malformed: <reason>
CLASS-CLOSURE: 2 open, 1 closed this round, 4 recurrences, 1 exempt, 1 unmechanized
CONVERGENCE: BLOCKED — 2 class(es) unclosed: 3f2a91c4 <invariant>; 91b0e77d <invariant>
```

or `CONVERGENCE: NOT-BLOCKED — no unclosed class; reviewer findings still govern.`

The second wording is deliberate and non-negotiable per §1: it is not a
convergence verdict.

*Round 1 [MAJOR] risk: `_CALIBRATION` still instructs the reviewer to print
`CONVERGED` when it has no blocking findings, and `README.md` still tells the
operator to stop on that token — so one response could contain both `CONVERGED`
and `CONVERGENCE: BLOCKED`, and the exact reviewer omission this mechanism exists
to survive could still terminate the loop.* Closed on three surfaces:
`_CALIBRATION` forbids emitting `CONVERGED` when the injected unclosed-class
block is non-empty; when the computed verdict is `BLOCKED` the footer states in
one line that any reviewer `CONVERGED` in the text above is void; and the README
stop recipe is rewritten so the computed trailer is the documented stop signal.

### 2.12 Recurrence injection

`already_raised` keeps its current meaning and instruction — it is caller-authored
and stays a caller concern. A **second, server-generated** block carries the
opposite instruction:

```
=== UNCLOSED CLASSES — re-verify these; do NOT suppress ===
[class 3f2a91c4, first raised round 7, MAJOR] <invariant>
  surviving matches: <path>:<line>: <text>
```

with: *these were reported in an earlier round and are not closed. Report every
surviving match, marked `[RECURRENCE <id>]`. The ROUND severity floor does not
apply. If a new finding of yours is an instance of one of these, emit
`RECURRENCE: <id>` in the register instead of registering a new class.*

## 3. Scope

**In:** `critique_branch` in converge mode (the default).

*Round 1 [MINOR]: revision 1 justified this by claiming converge is the only path
with a stable commit; `handlers.critique_branch` in fact reviews a committed
`head_ref` in a detached worktree too.* The real reason is narrower and honest:
converge is the default path, it already resolves an explicit snapshot id, and it
is where the packet block is rendered. Extending to the legacy path is deferred,
not impossible.

**Out:** `critique_plan` (a plan has no code sites to enumerate), `query`,
`rebut`, and legacy non-converge `critique_branch`.

**Kill switch:** `class_closure` call arg / `.paranoia.toml` key, default `true`.

## 4. Residual risks, stated

1. **A reviewer can tag everything `SCOPE: isolated`** and avoid the work. The
   prompt states the criterion; nothing enforces it. Largest residual, unclosed.
2. **Violation-only regexes are hard to write**, so the `unmechanized` population
   will be larger than revision 1 implied — and unmechanized closure is a model's
   word, not a check. This is the price of §2.1 and it is not hidden.
3. **A regex can be wrong in the safe direction** — too narrow, matching none of
   the real violations, and reporting `closed` immediately. Nothing detects this;
   a class that closes in the same round it was raised is suspicious and the
   trailer flags it, but flagging is not detection.
4. **Exemptions accumulate.** They are shown for challenge every round, which is
   pressure, not a limit.
5. **Semantic invariants** (cross-file dataflow, type-level) are not expressible
   as a line regex at all.

## 5. Implementation

New pure module `class_closure.py` — register parsing, class ids, status
transitions, survivor computation, block rendering — with the git call and the
clock injected, keeping the repository's pure-core/injected-edge split.
`handlers.py` wires it; `prompts.py` carries the register grammar, the
`SCOPE`/`[RECURRENCE]` rules and the `_CALIBRATION` amendments; `orientation.py`
renders the injected blocks; `server.py` exposes `lineage`, `exempt`,
`class_closure`; `logs.py` records `base_id`/`head_id` (§6). **`README.md` is in
scope, not optional** — *round 1 [MAJOR] gap: revision 1 listed code modules
only, while the shipped README still documents caller-managed state and stopping
on reviewer-emitted `CONVERGED`, so an operator following the docs would bypass
the new authority.*

TDD, RED first. Behavioural tests that must exist:

**Register parsing** (strictness matched to `arbitration.parse_*`, since this is
a model-authored surface): two mechanized records parse; `NONE` parses as an
empty register; absent → `CLASS-REGISTER: absent` and `BLOCKED`; duplicate field
within a record rejected; missing required field rejected; a record after the
block's end rejected; a field name appearing in earlier prose does not confuse
the parser; unmechanized record with `PROCEDURE` parses; `RECURRENCE`/`CLOSED`
naming an unknown id rejected.

**Closure semantics:** zero matches → closed; any match → open with every match a
recurrence; a closed class with a new match reopens; a superseded class is not
rechecked; `first_round` survives supersession.

**Git boundary:** exit 1 is closure, not failure; exit ≥ 2 → `malformed` +
`BLOCKED`; invalid ERE → `malformed` + `BLOCKED`; timeout → `malformed` +
`BLOCKED`; > 200 matches → `over-broad`, blocks, message says to narrow; a path
containing a newline and a non-UTF-8 byte parses correctly under `-z`; a pathspec
beginning with `:` is rejected before any git call.

**Blocking policy:** `MAJOR` class blocks; `MINOR` and `OUT-OF-SCOPE` classes do
not and are reported advisory; `BLOCKED` names the ids; `NOT-BLOCKED` text does
not contain the word *converged*; when blocked, the footer voids a reviewer
`CONVERGED`.

**Lineage state:** detached HEAD without `lineage` errors; two branches off one
base get different default lineages; unparseable state → `STATE-UNAVAILABLE` +
`BLOCKED` and the review text still returned; write failure → same; state is
replaced atomically; a failed engine call leaves state byte-identical.

**Exemptions:** an exempt match is subtracted; a different match in the same file
is not; the exemption appears under `CLAIMED EXEMPT` and in the trailer.

**Kill switch:** `class_closure: false` reproduces today's behaviour exactly.

## 6. Acceptance

*Round 1 [MAJOR] gap: revision 1 proposed replaying the ten production rounds
through git. That is impossible — `handlers._log` records target text, mode,
usage and duration but neither `base_id` nor `head_id`, and dirty wrapper commits
are unreferenced and GC-eligible (`orientation.wrap_commit`). The reviewed
commits are simply not recoverable from the logs.*

Acceptance is therefore two things, neither of which pretends to be that replay:

1. **A fixture repository**, committed to `tests/`, carrying a real three-site
   invariant across three commits that mirror the observed incident: round 7's
   commit violates at site A, the round-7 fix closes A and leaves B and C, and so
   on. The mechanism must register the class at round 7 and return
   `CONVERGENCE: BLOCKED` at rounds 8 and 9 naming the same `class_id` both
   times. This is the known-positive the design must reproduce.
2. **The next real review loop in this repository**, run with the mechanism on.
   That is the only honest end-to-end test, and the fixture exists so that
   failure is caught before spending it.

Separately and independently of this feature, `handlers._log` starts recording
`base_id` and `head_id` so that a future incident *is* replayable. Round 1 found
that gap; it is cheap and it should not wait for this design.
