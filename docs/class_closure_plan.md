# Brief: class closure — make a defect *class* a tracked object, not an operator inference

Status: DRAFT for review, revision 7. Six codex plan-review rounds folded —
round 1: 3 FATAL, 15 MAJOR, 2 MINOR; round 2: 1 FATAL, 8 MAJOR, 2 MINOR; round 3:
1 FATAL, 3 MAJOR; round 4: 2 FATAL, 1 MAJOR; round 5: 2 FATAL, 1 MAJOR; round 6:
1 FATAL, 5 MAJOR. Every finding accepted.

The chain is worth reading as evidence for the brief's own thesis. Round 1's
FATALs killed the candidate-enumeration design (§2.1). Round 2's FATAL found the
replacement had no link between a prose finding and a register record (§2.3).
Round 3's FATAL found that link, as specified, made every recurrence response
malformed — one round's fix breaking the next round's path. Round 4 found that
the dedup rule added for round 2 had **re-committed round 1's exact FATAL in a
different spelling** (§2.4), and that the quarantine added for round 3 had
*created* the fresh-lineage hole it was written to close (§2.7). Round 5 found
the recurrence grammar contradictory again (§2.2) and a stale dedup test left
standing in §5 that would have re-implemented the very collapse round 4 removed.
Round 6 found the recurrence grammar broken a **third** time, and revision 7
deletes it outright rather than repairing it once more (§2.2).

**Seven of the ten FATALs in this review were introduced by fixes to earlier
findings, and the recurrence grammar alone accounted for three of them — the same
defect in three spellings, exactly the pattern §0 describes.** That is the
failure this brief exists to mechanize against, observed on the brief itself,
under the very review protocol the brief argues is inadequate to catch it. The
design is the argument; the review history is the evidence.

The three fixes that finally held all **removed** mechanism rather than adding
it: dedup deleted (§2.4), the recurrence grammar deleted (§2.2), the adjudication
layer deleted (§2.1). Each had been introduced to satisfy an earlier finding.

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
   surfaces when that individual site clears the floor — the one-per-round trickle
   observed at rounds 7–9.

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
on a marginal or mistaken finding would reproduce the failure it exists to
prevent, in a form the operator cannot escape. §2.9 bounds what may block, and
every blocking state has a named escape that is not the kill switch.

*Round 3 [MAJOR]: revision 3 asserted that flatly, but `STATE-UNAVAILABLE` had no
escape at all.* The claim is now narrowed to what is true: every blocking state
has a named escape, and for `STATE-UNAVAILABLE` alone that escape is an operator
filesystem action — repairing or removing a named file — rather than an in-tool
transition. It is deliberately not automatic: silently starting a fresh lineage
on unreadable state would discard every tracked class and report `NOT-BLOCKED`,
which is precisely the false clearance this design exists to prevent (§2.7).

## 2. Mechanism

### 2.1 The predicate matches violations only

*Round 1 [FATAL]: revision 1 defined the predicate as matching every candidate
site — violating and conforming alike — then required the reviewer to adjudicate
each match, and made the class identity the candidate regex. Two distinct
invariants over the same syntax collapsed to one class; git could recheck only
candidate presence, never whether the invariant was still violated; and the
register had no way to express which of several matches in one file a given
adjudication referred to. Revision 2 took round 1's own remedy.*

**A mechanized class's predicate is a regex that matches only violations.
Closure is exactly: zero matches.**

This deletes the entire adjudication apparatus — no `SITES` verdicts, no
conforming whitelist, no site identity in the closure algorithm, no
line-number-versus-text matching problem, and no "broad pattern blocks forever"
trap. The cost is real and stated: **more invariants are inexpressible and fall
to `unmechanized` (§2.10), which is materially weaker.** That trade is correct —
a check that cannot be wrong about closure is worth more than a check with wider
reach and an adjudication layer that can silently whitelist a live defect.

### 2.2 Findings declare their scope and carry a reference

Every finding in "What doesn't work" and "Gaps" carries `SCOPE: isolated` or
`SCOPE: class`. `SCOPE: class` means *the reasoning that condemned this site
would condemn another site if one existed*. A genuine off-by-one is `isolated`;
requiring class machinery for it is the over-engineering
`prompts.CODE_REVIEW_INSTRUCTIONS` already calls a defect.

A finding reporting a **new class** — an invariant the lineage does not yet hold
— additionally opens with one machine-readable line:

```
CLASS-FINDING: ref=<short token unique in this review> severity=<BLOCKER|MAJOR|MINOR|OUT-OF-SCOPE>
```

*Round 6 [MAJOR]: revision 6 asked the parser to associate a `CLASS-REF` with
"its finding's severity tag", but `prompts._SECTION_BODIES` defines prose
content, not machine-delimited finding records — there is no boundary to
attribute a tag to, and the `arbitration` precedent only works because it slices
a fixed terminal field count. Multiple findings, or a severity tag quoted inside
one, made ownership ambiguous, and the register-only retry could not repair
prose.* The header carries both fields itself, so no prose-boundary inference is
needed anywhere.

**Recurrences carry nothing.** *Round 3 [FATAL], round 5 [FATAL] and round 6
[MAJOR] were all the same wound: a hand-authored recurrence grammar that had to
stay consistent with the prose rules, the register rules and the tests, and did
not — three times, in three different spellings.* Revision 7 deletes it, taking
round 6's own remedy: **for a mechanized class, a recurrence is whatever the
server's `git grep` found**, and nothing the reviewer writes is parsed to confirm
it. The server already ran the predicate; asking a model to restate the matches
and then machine-auditing the restatement was ceremony that repeatedly broke the
one path the mechanism exists to serve. The reviewer is still *shown* the
surviving matches and still asked to report them (§2.12) — that text is for the
operator to read, not for the parser to validate.

### 2.3 The class register, and its binding to the prose

The review ends with a machine-readable block — one record per class, following
the `arbitrate` trailer idiom. Mechanized:

```
=== CLASS REGISTER ===
REF: <the CLASS-REF token from the finding>
CLASS: <the invariant, one line, stated without reference to any site>
SEVERITY: BLOCKER|MAJOR|MINOR|OUT-OF-SCOPE
PATTERN: <POSIX-extended regex matching VIOLATIONS ONLY>
PATHSPEC: <git pathspec, or . for the whole tree>
```

Unmechanized records replace `PATTERN`/`PATHSPEC` with
`PROCEDURE: <what a reviewer must do to find every violation>`. Transitions
against classes the server already carries:

```
CLOSED: <class-id>                  # unmechanized only; judged closed this round
REOPEN: <class-id>                  # unmechanized only; found violated again
RECLASSIFY: <class-id> <severity>   # a later cold reviewer corrects the severity
SUPERSEDE: <old-id> BY: <existing-id>
SUPERSEDE: <old-id> WITH-PATTERN: <regex> PATHSPEC: <pathspec> [CLASS: <invariant>]
```

*Round 6 [MAJOR]: a closed unmechanized class had no way back. `CLOSED` was
listed but nothing reopened it, so once a reviewer judged such a class closed, a
later reviewer finding it violated again could report that only in prose while
the state stayed closed and the trailer said `NOT-BLOCKED`.* `REOPEN` closes
that. It is unmechanized-only because a mechanized class reopens automatically on
any match (§2.6).

*Round 5 [MAJOR]: the earlier `SUPERSEDED-BY: <class-id> | PATTERN: … PATHSPEC: …`
form could not name both sides — one id left the server unable to tell the
superseded class from its replacement, and the pattern form named no class at
all.* Both forms now name the source explicitly.

`WITH-PATTERN` mints a **new** server-assigned id inheriting the old class's
`severity` and `first_round`. *Round 6 [MAJOR]: revision 6 said the replacement
could restate its invariant but gave the form no field to do it in, forcing an
implementation to either reject an undocumented field or carry stale invariant
text that disagrees with the corrected predicate.* The optional `CLASS:` field is
that form; omitted, the old invariant text carries over.

`BY` **requires a target that is distinct from the source, already registered in
this lineage, and not itself superseded.** *Round 6 [FATAL]: revision 6 required
only that the target "exist", so `SUPERSEDE: A BY: A` — or supersession by an
already-superseded class — parsed, marked the source non-blocking and
never-rechecked, and left no active blocker at all. A model-authored transition
could therefore manufacture a false `NOT-BLOCKED`.* The distinctness and
liveness conditions also make cycles unreachable: `A BY B` marks A superseded, so
a later `B BY A` fails on the liveness check. The target keeps its own
`severity`; it inherits the **earlier** of the two `first_round` values.

In both forms the old class is marked `superseded`: non-blocking, and never
rechecked again (§2.6). This is the recovery transition `malformed` and
`over-broad` classes need.

**The register is mandatory and must be a bijection with the prose.**

*Round 2 [FATAL]: revision 2 required `SCOPE: class` in prose and separately
accepted `NONE` as an empty register, with nothing connecting them. A review
containing `[MAJOR] … SCOPE: class` followed by `=== CLASS REGISTER === NONE`
parsed, persisted nothing, and could return `NOT-BLOCKED` — the exact durability
failure revision 2 claimed to close.*

*Round 3 [FATAL]: revision 3's single bijection then made every **recurrence**
response malformed, because a recurrence has no new `REF` and no severity of its
own yet the rule demanded both. Revisions 4 and 5 answered that with a second,
recurrence-specific bijection — which broke again at round 5 and again at round
6.*

**There is now exactly one bijection, over new classes only.** The set of
`CLASS-FINDING` header `ref=` values in the prose equals the set of `REF` values
on new-class records, and each record's `SEVERITY` equals its header's
`severity=`. Both sides of that comparison are single machine-readable tokens, so
there is nothing left to infer.

Recurrences are not in the register at all (§2.2) — the server computes them from
git. `CLOSED`, `REOPEN`, `RECLASSIFY` and `SUPERSEDE` are state transitions, not
findings, and bind to nothing in the prose. A prose header with no record, a
record with no header, a duplicate ref, an unknown class id, or a severity
disagreement is a malformed register. A review with no new classes and no
transitions emits `=== CLASS REGISTER ===` followed by `NONE`.

Parsing is as strict as `arbitration.parse_*`: the block is terminal, every field
required, duplicates and out-of-block records rejected.

**One retry, then block.** *Round 2 [MAJOR]: revision 2 said a malformed register
blocks and "the operator either re-runs or exempts explicitly", but the exemption
grammar needs a `class_id` that a missing register does not have — so the only
real escape was the global kill switch.* An absent or malformed register triggers
**one targeted re-ask on the same reviewer session** via `engines.Engine.resume`
(the mechanism `rebut` already uses), requesting only the register block, not a
re-review. This is the `arbitrate` cleaner idiom — one retry, then fail — and it
is cheap because it does not re-run the review. If the retry also fails,
`CONVERGENCE: BLOCKED — class register absent/malformed` and the block text
quotes the exact expected grammar. **The review text is always returned in full**;
a paid review is never discarded over a formatting miss.

*Round 4 [MAJOR] gap: the retry is not always available. `Review.session_ref` is
`str | None`, `Engine.resume` requires a `str`, and the Claude engine's supported
non-JSON fallback returns `Review(text=…, session_ref=None)` — a contract
`tests/test_engines.py` already pins. An unconditional retry on that path would
raise and `dispatch` would replace the paid review with an error, which is the
one outcome this section promises cannot happen.* **When `session_ref` is
`None` the retry is skipped**, the original review is returned unchanged, and the
malformed-register block is emitted directly.

### 2.4 Class identity is server-assigned

*Round 1 [MAJOR]: revision 1 hashed the reviewer's regex into the id, so a
corrected predicate minted a new class and the old one blocked forever, and
unmechanized classes had no id at all yet were required to close by id.*

The server assigns `class_id` (8 hex chars) at first registration and it never
changes. Reviewer-authored text never determines identity, so it does not matter
that round 7 called the class "escalations" and round 9 "unresolved starts" — a
label match would never have connected them anyway.

**Every new-class record gets its own id. There is no deduplication.**

*Round 2 [MAJOR] asked for a dedup conflict rule and revision 3 gave one — max
severity, both invariant texts retained. Round 4 [FATAL] then showed that dedup
is the round-1 FATAL wearing a new hat: `(pattern, pathspec)` is not an identity,
so two genuinely distinct invariants expressible by one regex collapse into a
single state object with one `severity`, one `status` and one `superseded_by`.
`RECLASSIFY` or `SUPERSEDED-BY` against that shared id would then silently mutate
an unrelated live class — retaining both invariant strings buys nothing, because
identity and transitions are what collapsed, not the prose.*

**This is worth naming rather than quietly patching: the design re-committed
round 1's exact error, three revisions later, in a different spelling. That is
the failure mode the whole brief exists to catch, occurring inside the brief.**
It survived two intervening review rounds and was caught only because round 4
compared the fold against §2.1's own recorded FATAL.

The remedy removes a mechanism rather than adding one: no dedup, no conflict
rule, no shared state. Duplicate registration is guarded by the prompt alone —
open classes are shown to every subsequent reviewer with ids and invariants, with
the instruction to report an instance of one as a recurrence of that id rather
than registering a new class (§2.12) — and the
100-class cap (§2.5) bounds the cost of the residual duplicates that guard
misses. A duplicate class is redundant work; a collapsed class is a silent
clearance. The asymmetry decides it.

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

**Verified empirically in this repository:**

- `-z` output is `<commit>:<path>\0<line>\0<text>\n`. Paths are NUL-terminated,
  so paths containing newlines or non-UTF-8 bytes parse unambiguously. Decode
  with `surrogateescape`, matching the `orientation`/`evidence` precedent.
  *(Round 1 [MINOR]: revision 1 omitted `-z`.)*
- Exit codes: `0` = matches, `1` = **no matches, which is success and means
  closed**, `≥2` = error. A malformed ERE exits `128` with
  `fatal: -e option, 'a[': Invalid regular expression`.
- Pathspec magic is accepted and silently changes the result set:
  `git grep -E -e x main -- ':(exclude)src'` returned matches from outside `src`.
  A pathspec beginning with `:` is **rejected at parse time** and the class
  recorded `malformed`.

**Bounds.** Per-class 10 s timeout, 200-match output cap, and — *round 2 [MINOR]
risk: revision 2 bounded each class but not the round, so a lineage of 36
timed-out classes would delay every round by six minutes before the reviewer even
starts* — a **60 s aggregate budget** across all classes. Classes not reached are
recorded `unchecked`. Registration is refused beyond 100 tracked classes, with a
message.

Under violation-only semantics many matches means many violations, so the cap is
an output bound, not a verdict: the block text is truncated with a count. A regex
exceeding it is recorded `over-broad` so the reviewer narrows it via
`SUPERSEDE`.

**Execution failure inherits the class's blocking policy.** *Round 2 [MAJOR]:
revision 2 said every timeout, invalid ERE or git error "blocks", contradicting
its own promise that `MINOR` and `OUT-OF-SCOPE` classes never block, and
recreating the termination trap for a marginal class.* A `malformed`,
`over-broad` or `unchecked` class blocks **only if its severity is `BLOCKER` or
`MAJOR`** (§2.9). A predicate that cannot run has not proved closure — but for an
advisory class, not proving closure is not grounds to stop the loop.

### 2.6 The closure check

Each round, for **every** mechanized class the lineage holds — `open`, `closed`,
`over-broad`, `malformed`, `unchecked`, but not `superseded` — the server runs
the invocation above against the snapshot commit under review, subtracts recorded
exemptions (§2.8), and:

- zero matches → `closed`
- any match → `open`, and every match is a recurrence

*Round 1 [MAJOR]: revision 1 rechecked only `open` classes and treated closure as
permanent, so a later fix could reintroduce the defect while the trailer still
reported nothing unclosed.* **A closed class reopens on any new match.**

### 2.7 Lineage state

`~/.paranoia/lineages/<lineage_id>.json`, holding per class: `class_id`,
`invariant`(s), `severity`, `pattern`/`pathspec` or `procedure`, `first_round`,
`status`, `superseded_by`, and exemptions.

*Round 1 [MAJOR]: revision 1 derived the lineage from repo + `base_ref` only, so
two sequential feature branches reviewed against `main` inherited each other's
classes. Round 2 [MAJOR]: revision 2's fix used the **checked-out** branch, but
`handlers.critique_branch` accepts an independent `head_ref` and `worktree_at`
exists precisely to review a branch that is not checked out — so reviewing
`feature-a` and `feature-b` from a repo sitting on `main` still collided, and a
detached checkout wrongly rejected a perfectly stable `head_ref`.*

`lineage_id` = `sha256(resolved_repo_path, base_ref, head_symbolic_name)[:12]`,
where `head_symbolic_name` is `git rev-parse --symbolic-full-name <head_ref>` on
the **reviewed** ref. **Verified: for a commit sha this exits 0 and prints
nothing** — so the test is empty output, not exit status. Empty means the
reviewed ref is not a branch, and an explicit `lineage` argument is then
required, the call erroring without one. Fail-closed beats silently minting a
fresh lineage every round. Every trailer prints
`LINEAGE: <id> (rounds recorded: N)` so an unintended split is visible.

*Round 3 [MAJOR]: for dirty reviews that rule keys state to a branch the server
is not reviewing. Verified: `orientation.resolve_target` returns `head_ref=None`
and `is_dirty=True` whenever `include_uncommitted` is set, and
`handlers._converge_branch_review` then snapshots the **checkout's** `HEAD` — but
the caller's raw `head_ref` is still in scope. With
`include_uncommitted=true, head_ref="feature"` the server would review the current
checkout and write its classes into `feature`'s lineage.* **For a dirty target
the lineage derives from the checkout's own symbolic `HEAD`, and an
independently supplied `head_ref` is rejected with an error** — the server is not
reviewing that ref, so accepting it can only contaminate a lineage.

*Round 1 [MAJOR] risk: `logs.write_log` deliberately swallows every write failure,
since a completed review is the expensive artifact.* **Lineage state must not
follow that precedent** — a silently lost write plus a `NOT-BLOCKED` footer is
exactly the false clearance this design exists to prevent. State is read before
the engine call and written after a successful one, via temp file + `os.replace`
in the same directory. A write failure, or existing state that will not parse,
yields `CLASS-CLOSURE: STATE-UNAVAILABLE` and `CONVERGENCE: BLOCKED`. The review
text is still returned.

**The escape from `STATE-UNAVAILABLE` is an operator filesystem action, named in
the block text** (§1). Unparseable state is moved aside to
`<lineage_id>.corrupt-<timestamp>.json`, and the message gives the absolute path
of both files; a write failure names the directory and the errno.

*Round 4 [FATAL]: quarantining alone **creates** the fresh-lineage path this
section forbids. Once the canonical file is moved, the next invocation finds it
absent, initializes an empty lineage, and reports `NOT-BLOCKED` — so merely
re-running after a `STATE-UNAVAILABLE` discards every tracked class without the
operator ever performing the named repair.* **A lineage therefore refuses to
initialize fresh while any `<lineage_id>.corrupt-*.json` sibling exists**: it
keeps returning `STATE-UNAVAILABLE` + `BLOCKED` until the operator repairs the
canonical file or deletes the quarantined one. Quarantine is a latch, not a
sweep.

**Recovery is deliberately not automatic:** auto-starting a fresh lineage would
discard every tracked class and then report `NOT-BLOCKED`, turning a storage
fault into a false all-clear.

### 2.8 Exemptions

*Round 1 [MAJOR]: revision 1 keyed exemptions on `class_id` + path, so exempting
one match suppressed every present and future match in that file. Round 2
[MAJOR]: revision 2's line-text fingerprint still collided — two identical
normalized lines in one file share a fingerprint, so exempting a false positive
also suppressed a real violation on the duplicate line and could falsely close
the class.*

An exemption is `(class_id, path, line_number, line_text_fingerprint)`, all four
matched exactly. A match at that path and line whose text has changed is **not**
exempt — the exemption is void and the match resurfaces. Line drift therefore
costs re-exemption churn, which is the correct direction: it fails toward
blocking, never toward silent clearance.

*Round 2 [MAJOR] gap: exemptions were shown "for challenge" but there was no way
to act on a successful challenge.* An `unexempt` argument
`(class_id, path, line_number)` revokes one. Both actions are echoed in every
subsequent trailer and shown to every subsequent reviewer under
`=== CLAIMED EXEMPT ===`. This is the one place operator judgement legitimately
enters, and the design makes it a recorded, adversarially-reviewed, reversible
artifact rather than a silent lapse.

### 2.9 What may block, and the severity grammar

*Round 1 [MAJOR]: revision 1 made every recurrence merge-blocking "whatever the
severity", so a class originating as `[MINOR]` or `[OUT-OF-SCOPE]` could prevent
termination indefinitely — the trap §1 forbids.*

**Only classes whose current severity is `BLOCKER` or `MAJOR` block.** `MINOR`
and `OUT-OF-SCOPE` classes are tracked and reported as advisory. This holds for
every blocking state, including `malformed`, `over-broad`, `unchecked` and
`STATE-UNAVAILABLE`-adjacent conditions.

*Round 2 [MAJOR]: a severity registered once was permanent, so a class mistakenly
registered `MAJOR` blocked while its regex matched even if every later cold
reviewer judged it `MINOR` — with no escape but the kill switch.* The
`RECLASSIFY: <class-id> <severity>` transition (§2.3) lets a later **cold
reviewer** correct it. The escape is therefore a recorded adversarial judgement,
not an operator's silent override, and it is symmetric — a class can be raised as
well as lowered.

*Round 1 [MAJOR]: revision 1 told reviewers to emit `[RECURRENCE]` while
`prompts.CODE_REVIEW_INSTRUCTIONS` requires exactly one of
`[BLOCKER]`/`[MAJOR]`/`[MINOR]`/`[OUT-OF-SCOPE]` per finding.* Recurrence is
**not** a severity tag. It is a marker adjacent to one:
`[MAJOR] [RECURRENCE 3f2a91c4] …`. The existing grammar is untouched.

Since revision 7 the marker is **presentational only** — it makes the review
readable and keeps the floor exemption expressible, but nothing parses or
validates it, so it can no longer contradict the register (§2.2). The blocking
decision comes from git, not from whether the reviewer remembered to type it.

`_CALIBRATION` gains: *the ROUND severity floor never applies to a finding marked
`[RECURRENCE]`.*

### 2.10 Unmechanized classes

Registered with `PROCEDURE:` instead of `PATTERN:`/`PATHSPEC:`, given a server id
like any other class, carried forward as a reviewer obligation, always shown,
never floor-suppressed, and marked `unmechanized` in the trailer so the weakness
is visible. They close only when a later reviewer names the id on a `CLOSED:`
line, and reopen on a `REOPEN:` line: still a judgement, but an explicit, cold,
recorded one rather than an operator's silent assumption.

*Round 3 [MAJOR]: revision 3 said they "cannot block mechanically", which
conflated **nothing to run** with **not blocking**. Since `NOT-BLOCKED` is
defined as "no unclosed class" and is the documented stop signal, an open
unmechanized `MAJOR` would have let the trailer report `NOT-BLOCKED` with a known
major class outstanding — and §4.6 deliberately routes every semantic invariant
down this path, so that is the common case, not an edge one.* **An unmechanized
class of severity `BLOCKER` or `MAJOR` blocks until `CLOSED` or `RECLASSIFY`.**
What it lacks is a mechanical *check*, not the ability to block; the trailer
names it as awaiting a reviewer judgement rather than a git result.

### 2.11 The computed trailer, and the `CONVERGED` collision

Appended by `handlers._footer`:

```
LINEAGE: <id> (rounds recorded: N)
CLASS-REGISTER: parsed 3 | NONE | absent | malformed: <reason>
CLASS-CLOSURE: 2 open, 1 closed this round, 4 recurrences, 1 exempt, 1 unmechanized
CONVERGENCE: BLOCKED — 2 class(es) unclosed:
  3f2a91c4 <invariant> (mechanized: 4 matches)
  91b0e77d <invariant> (unmechanized: awaiting reviewer CLOSED or RECLASSIFY)
```

or `CONVERGENCE: NOT-BLOCKED — no unclosed class; reviewer findings still govern.`

The second wording is deliberate and non-negotiable per §1: it is not a
convergence verdict.

*Round 1 [MAJOR] risk: `_CALIBRATION` still instructs the reviewer to print
`CONVERGED` when it has no blocking findings, and `README.md` still tells the
operator to stop on that token — so one response could contain both `CONVERGED`
and `CONVERGENCE: BLOCKED`, and the exact reviewer omission this mechanism exists
to survive could still terminate the loop.* Closed on three surfaces:
`_CALIBRATION` forbids `CONVERGED` when the injected unclosed-class block is
non-empty; when the computed verdict is `BLOCKED` the footer states in one line
that any reviewer `CONVERGED` above is void; and the README stop recipe is
rewritten so the computed trailer is the documented stop signal.

### 2.12 Recurrence injection, and block precedence

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
apply. If a finding of yours is an instance of one of these, report it as a
recurrence of that id — do NOT register it as a new class. **Where this block and
the already-raised block conflict, this block governs.***

Nothing in that instruction is parsed. The classes are already open and already
blocking on the git result; the instruction exists so the review the operator
reads addresses them, not so the parser can check that it did.

*Round 2 [MINOR] risk: `orientation.build_packet` appends `already_raised` last
(`sections.append(reserved)` after the evidence and the truncation marker), so a
recurrence block placed before it would leave the suppressive instruction nearest
the end and a reviewer could obey the closer one.* **Verified against the code;
the unclosed-classes block is therefore rendered after `already_raised`**, and
carries the precedence sentence above. Like `already_raised`, it is reserved from
the packet budget rather than trimmed.

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
It is the escape of last resort, not the escape of first resort — §2.3, §2.8 and
§2.9 each provide a bounded, recorded escape from their own blocking state.

## 4. Residual risks, stated

1. **A reviewer can tag everything `SCOPE: isolated`** and avoid the work. The
   prompt states the criterion; nothing enforces it. Largest residual, unclosed.
2. **Violation-only regexes are hard to write**, so the `unmechanized` population
   will be larger than revision 1 implied — and unmechanized closure is a model's
   word, not a check. The price of §2.1, not hidden.
3. **A regex can be wrong in the safe direction** — too narrow, matching none of
   the real violations, reporting `closed` immediately. A class that closes in
   the round it was raised is flagged in the trailer, but flagging is not
   detection.
4. **`RECLASSIFY` is a downgrade path a reviewer could misuse** to clear a real
   blocker. It is recorded and shown, which is pressure, not a limit.
5. **Exemptions accumulate**, subject to the same pressure.
6. **Semantic invariants** (cross-file dataflow, type-level) are not expressible
   as a line regex at all.
7. **Duplicate classes are now possible**, since §2.4 removed dedup. Two
   reviewers can register the same invariant under different ids, and both must
   then be closed. Bounded by the prompt guard and the 100-class cap; accepted
   deliberately, because a duplicate is redundant work while a collapsed class is
   a silent clearance.

## 5. Implementation

New pure module `class_closure.py` — register parsing, prose/register bijection,
class ids, status transitions, survivor computation, block rendering — with the
git call and the clock injected, keeping the repository's pure-core/injected-edge
split. `handlers.py` wires it and owns the one register retry via
`engines.Engine.resume`; `prompts.py` carries the register grammar, the
`SCOPE`/`CLASS-FINDING` rules and the `_CALIBRATION` amendments;
`orientation.py` renders the injected blocks after `already_raised`; `server.py`
exposes `lineage`, `exempt`, `unexempt`, `class_closure`; `logs.py` records
`base_id`/`head_id` (§6). **`README.md` is in scope, not optional** — *round 1
[MAJOR] gap: the shipped README documents caller-managed state and stopping on
reviewer-emitted `CONVERGED`, so an operator following the docs would bypass the
new authority.*

TDD, RED first. Behavioural tests that must exist:

**Register parsing and binding** (strictness matched to `arbitration.parse_*`,
since this is a model-authored surface): two mechanized records parse; `NONE`
parses as empty; absent → one retry, then `absent` + policy-dependent block;
**a `CLASS-FINDING` header in prose with a `NONE` register is malformed** (round
2's FATAL); header ref with no record, record with no header, duplicate ref, and
**severity disagreement between header `severity=` and record `SEVERITY`** are
each malformed; duplicate field within a record rejected; missing required field
rejected; a record after the block's end rejected; a field name in earlier prose
does not confuse the parser; unmechanized record with `PROCEDURE` parses;
`CLOSED`/`REOPEN`/`RECLASSIFY`/`SUPERSEDE` naming an unknown id rejected; the
retry path is taken exactly once and a successful retry parses; **a `Review` with
`session_ref=None` skips the retry, returns its text unchanged, and blocks per
policy** (round 4); **two new-class records sharing a pattern and pathspec get
two distinct ids and two independent state objects** (round 4's dedup FATAL).

**Recurrences are not parsed** (rounds 3, 5 and 6 — the mechanism's own hot path,
broken three times by a hand-authored grammar that revision 7 deletes): a review
that reports surviving matches only in prose, with a register of `NONE`, **is
well-formed and still blocks** on the git result; a review that omits the
recurrence prose entirely **also still blocks**, because the verdict never
depended on the reviewer's text; `[RECURRENCE <id>]` appearing anywhere in the
prose changes no parse outcome; a review mixing a new class and recurrence prose
satisfies the single bijection over the new class alone.

**Closure semantics:** zero matches → closed; any match → open with every match a
recurrence; a closed class with a new match reopens; a superseded class is not
rechecked; `first_round` and `severity` survive supersession; **two classes
sharing a pattern and pathspec are fully independent — `RECLASSIFY` or
`SUPERSEDE` against one leaves the other's severity, status and matches
untouched** (round 5: revision 5 removed dedup in §2.4 but left the old
"dedupe to the maximum" test standing, so the two requirements could not both
pass and implementing the stale one would have recreated the collapsed-identity
FATAL).

**Supersession:** `SUPERSEDE: <old> BY: <existing>` requires a target that
exists, **is not the source itself, and is not already superseded** — each of
those three is rejected, and the self-target and superseded-target cases are
round 6's FATAL, since either would leave no active blocker; a cyclic
`A BY B` then `B BY A` is rejected on the second by the liveness rule; the target
keeps its own severity even when lower than the source's, and inherits the
earlier `first_round`. `SUPERSEDE: <old> WITH-PATTERN: …` mints a new id
inheriting `severity` and `first_round`, takes the optional `CLASS:` field as the
new invariant, and carries the old text over when it is omitted. In every form
the old class becomes `superseded`, stops blocking, and is excluded from the
recheck sweep.

**Unmechanized lifecycle:** `CLOSED` on an open unmechanized `MAJOR` unblocks;
**`REOPEN` on it blocks again** (round 6's `CLOSED → REOPEN → open` gap);
`REOPEN` against a mechanized class is rejected, since those reopen from git.

**Git boundary:** exit 1 is closure, not failure; exit ≥ 2, invalid ERE, and
timeout each → `malformed`; > 200 matches → `over-broad` with a truncated,
counted block; aggregate budget exhaustion → `unchecked`; a path containing a
newline and a non-UTF-8 byte parses correctly under `-z`; a pathspec beginning
with `:` is rejected before any git call; registration beyond 100 classes is
refused.

**Blocking policy:** `MAJOR` class blocks; `MINOR` and `OUT-OF-SCOPE` do not and
are reported advisory; **`malformed`/`over-broad`/`unchecked` on a `MINOR` class
does not block** (round 2's severity-policy contradiction); **an open
unmechanized `MAJOR` blocks, and `NOT-BLOCKED` is never emitted while one is
open** (round 3); `CLOSED` on it unblocks, as does `RECLASSIFY` to `MINOR`;
`RECLASSIFY` to `MAJOR` re-blocks; `BLOCKED` names the ids and distinguishes
mechanized match counts from unmechanized awaiting-judgement; `NOT-BLOCKED` text
does not contain the word *converged*; when blocked, the footer voids a reviewer
`CONVERGED`.

**Lineage:** a reviewed `head_ref` that is a branch but not checked out yields
its own lineage, and two such branches off one base differ; a `head_ref` that is
a sha (empty `--symbolic-full-name` output, exit 0) without `lineage` errors;
**a dirty target uses the checkout's `HEAD` and rejects a supplied `head_ref`**
(round 3); unparseable state → `STATE-UNAVAILABLE` + `BLOCKED`, review text still
returned, **and the corrupt file is quarantined to a named path rather than
overwritten or silently replaced by a fresh lineage**; **re-running after a
quarantine does NOT start a fresh lineage — it blocks again until the quarantine
sibling is gone** (round 4's latch FATAL); write failure → same outcome, message
names directory and errno; state replaced atomically; a failed engine call leaves
state byte-identical.

**Exemptions:** an exempt match is subtracted; **a second, textually identical
line in the same file is not** (round 2's collision); an exemption whose line
text changed is void and the match resurfaces; `unexempt` restores a match; both
appear under `CLAIMED EXEMPT` and in the trailer.

**Packet:** the unclosed-classes block is rendered after `already_raised` and
survives budget trimming.

**Kill switch:** `class_closure: false` reproduces today's behaviour exactly.

## 6. Acceptance

*Round 1 [MAJOR] gap: revision 1 proposed replaying the ten production rounds
through git. That is impossible — `handlers._log` records target text, mode,
usage and duration but neither `base_id` nor `head_id`, and dirty wrapper commits
are unreferenced and GC-eligible (`orientation.wrap_commit`). The reviewed
commits are not recoverable from the logs.*

Acceptance is therefore two things, neither pretending to be that replay:

1. **A fixture repository**, committed to `tests/`, carrying a real three-site
   invariant across three commits mirroring the observed incident: the round-7
   commit violates at site A, the round-7 fix closes A and leaves B and C, and so
   on. The mechanism must register the class at round 7 and return
   `CONVERGENCE: BLOCKED` at rounds 8 and 9 naming the same `class_id` both
   times. This is the known-positive the design must reproduce.
2. **The next real review loop in this repository**, run with the mechanism on.
   The only honest end-to-end test; the fixture exists so failure is caught
   before spending it.

Separately and independently, `handlers._log` starts recording `base_id` and
`head_id` so a future incident *is* replayable. Round 1 found that gap; it is
cheap and should not wait for this design.
