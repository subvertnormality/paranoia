# Brief: class closure — make a defect *class* a tracked object, not an operator inference

Status: DRAFT for review, revision 16. Fifteen codex plan-review rounds folded —
round 1: 3 FATAL, 15 MAJOR, 2 MINOR; round 2: 1 FATAL, 8 MAJOR, 2 MINOR; round 3:
1 FATAL, 3 MAJOR; round 4: 2 FATAL, 1 MAJOR; round 5: 2 FATAL, 1 MAJOR; round 6:
1 FATAL, 5 MAJOR; round 7: 1 FATAL, 3 MAJOR; round 8: 2 FATAL, 1 MAJOR; round 9:
4 FATAL, 2 MAJOR; round 10: 1 FATAL; rounds 11–15: one MAJOR each and nothing in
any other section. Every finding accepted.

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
Round 6 found the recurrence grammar broken a **third** time and it was deleted
outright. Rounds 7 and 8 then escalated the same underlying attempt — make the
review's prose provably account for every class — through a `FINDING:` header and
a four-section record grammar. Round 9 showed that grammar was not merely broken
but **impossible**: a record ran from its header to the next header, so a
headerless continuation is by definition *inside* the preceding record, and the
test demanding it be malformed could never be written.

**Revision 10 therefore abandons the goal rather than the eleventh attempt at
it** (§2.2). A reviewer that finds a class and does not register it cannot be
distinguished from one that never found it; no parser over free text closes that.
§1 now scopes the guarantee to a *registered* class and §4.1 states the ceiling
plainly, which is what the previous nine revisions were spending FATALs to avoid
admitting.

**Eleven of the fourteen FATALs in this review were introduced by fixes to
earlier findings**, and two distinct mechanisms — the recurrence grammar and the
prose bijection — each accounted for three, the same defect in three spellings.
That is the failure this brief exists to mechanize against, observed on the brief
itself, under the very review protocol the brief argues is inadequate to catch it.
The design is the argument; the review history is the evidence.

**Every fix that finally held removed mechanism rather than adding it**: the
adjudication layer (§2.1), dedup (§2.4), the recurrence grammar (§2.2), and now
the prose bijection entirely (§2.2). Each had been introduced to satisfy an
earlier finding.

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

**Must achieve.** A class **registered** in round N is a durable object with a
*mechanically re-checkable* membership predicate. Round N+1 re-runs that
predicate itself. A surviving match is a recurrence, is exempt from the severity
floor, and **blocks the round from being reported converged** — computed in
Python, not asserted by the reviewer and not inferred by the operator.

*Registered* is load-bearing and was added at revision 10. Eight rounds were
spent trying to guarantee that a class the reviewer *described in prose* could
not escape registration, and round 9 established the goal is unreachable in
principle: a reviewer that finds a class and does not register it is
indistinguishable from one that never found it (§2.2). The mechanism owns
everything downstream of registration and claims nothing upstream of it.

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

### 2.2 The register is the only class channel

Revisions 2 through 9 each tried to make the review's *prose* provably account
for every class it found: `SCOPE:` tags, a `CLASS-REF`/`REF` bijection, a second
bijection for recurrences, a per-finding `FINDING:` header, and finally a record
grammar over four sections. Every one of those broke something, and round 9
showed the last one was not merely broken but **impossible**: a record was
defined as running from its header to the next header, so a headerless
continuation is *by definition* inside the preceding record, and the test
demanding it be malformed could never be implemented.

**Revision 10 abandons the attempt, because the goal was unreachable in
principle.** A reviewer that finds a class and fails to register it is
indistinguishable, from outside, from a reviewer that never found the class. No
grammar over free text can separate those two, and every round spent trying
produced a more elaborate parser and a new FATAL. Round 2's "durability" finding
was asking for something no parser can deliver.

So: **the register is the sole class channel.** Nothing in the five prose
sections is parsed. There are no `SCOPE:` tags, no `FINDING:` headers, no record
grammar, no bijection, and the existing prose format of
`prompts.CODE_REVIEW_INSTRUCTIONS` is untouched — which also resolves round 9's
finding that the record grammar made a clean late-round `CONVERGED` response
unparseable, and round 9's finding that a class carried two severity
declarations with only one validated. The register's `SEVERITY` is now the only
severity a class has.

What this costs is stated honestly in §1 and §4: the mechanism guarantees
durability for a class **the reviewer registers**, and registration is a reviewer
judgement exactly as finding the defect is. That was always the true ceiling —
residual §4.1 has conceded since revision 1 that a reviewer can decline to
declare a class at all. The bijection was pretending otherwise, at the cost of
seven FATALs.

What the mechanism still does, mechanically and without operator interpretation,
is everything after registration: recheck, recurrence detection, blocking,
reopening, and the computed verdict. That is where the observed defect actually
lived — rounds 7, 8 and 9 of the reference incident each *did* report the class
in prose; nothing carried it forward.

**Recurrences carry nothing.** *Round 3 [FATAL], round 5 [FATAL] and round 6
[MAJOR] were the same wound three times: a hand-authored recurrence grammar that
had to stay consistent with the prose rules, the register rules and the tests,
and did not.* **For a mechanized class, a recurrence is whatever the server's
`git grep` found**, and nothing the reviewer writes is parsed to confirm it. The
reviewer is still *shown* the surviving matches and still asked to report them
(§2.12) — that text is for the operator to read, not for the parser to validate.
`[RECURRENCE <id>]` remains a presentational marker so the floor exemption in
§2.9 is expressible.

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

Unmechanized records replace `PATTERN`/`PATHSPEC` with
`PROCEDURE: <what a reviewer must do to find every violation>`. Transitions
against classes the server already carries, **one field per line** — *round 9
[MAJOR]: the previous single-line `SUPERSEDE … WITH-PATTERN: <regex> PATHSPEC:
<pathspec> [CLASS: <invariant>]` had no unique parse, because `PATHSPEC:` and
`CLASS:` are legal content inside a regex, a pathspec and an invariant alike, so
a legitimate correction containing one of those tokens would register the wrong
predicate or stay malformed*:

```
CLOSED: <class-id>                  # unmechanized only; judged closed this round
REOPEN: <class-id>                  # unmechanized only; found violated again
RECLASSIFY: <class-id> <severity>   # a later cold reviewer corrects the severity

SUPERSEDE: <old-id>
BY: <existing-id>

SUPERSEDE: <old-id>
WITH-PATTERN: <regex>
PATHSPEC: <pathspec>
CLASS: <invariant>                  # optional

SUPERSEDE: <old-id>
WITH-PROCEDURE: <procedure>
CLASS: <invariant>                  # optional
```

*Round 13 [MAJOR]: supersession could only mint another **mechanized** class, so
the one transition §2.1 predicts would be needed most was missing. §2.1 concedes
that under violation-only semantics "more invariants are inexpressible and fall
to `unmechanized`" — but a `MAJOR` class first registered with a malformed or
over-broad regex, and then found to be inexpressible, had no way to become a
`PROCEDURE`. At the 100-active-class boundary ordinary registration is refused
and only the net-zero pattern replacement was guaranteed available, so such a
class stayed permanently `BLOCKED` short of an inaccurate downgrade or the kill
switch — again contradicting §1's named-escape guarantee.* `WITH-PROCEDURE` is
the same atomic net-zero transition into an unmechanized replacement.

*Round 6 [MAJOR]: a closed unmechanized class had no way back — `CLOSED` was
listed but nothing reopened it, so a later reviewer finding it violated again
could say so only in prose while the state stayed closed and the trailer said
`NOT-BLOCKED`.* `REOPEN` closes that, and is unmechanized-only because a
mechanized class reopens automatically on any match (§2.6).

`WITH-PATTERN` and `WITH-PROCEDURE` each mint a **new** server-assigned id
inheriting the old class's `severity` and `first_round`; the optional `CLASS:`
line restates the invariant, and the old text carries over when it is omitted.
Both are net zero against the cap (§2.5).

`BY` **requires a target that is distinct from the source, already registered in
this lineage, and not itself superseded.** *Round 6 [FATAL]: requiring only that
the target "exist" let `SUPERSEDE: A BY: A` — or supersession by an
already-superseded class — parse, mark the source non-blocking and
never-rechecked, and leave no active blocker at all.* The distinctness and
liveness conditions also make cycles unreachable: `A BY B` marks A superseded, so
a later `B BY A` fails the liveness check. The target keeps its own `severity`
and inherits the **earlier** of the two `first_round` values.

In both forms the old class becomes `superseded`: non-blocking, never rechecked
(§2.6). This is the recovery transition `malformed` and `over-broad` classes need.

**Parsing is as strict as `arbitration.parse_*`:** the block is terminal, every
field required, duplicates and out-of-block records rejected, and an unknown
class id on any transition is malformed. A review with no new classes and no
transitions emits `=== CLASS REGISTER ===` followed by `NONE`.

**One retry, then durable debt.** An absent or malformed register triggers **one
targeted re-ask on the same reviewer session** via `engines.Engine.resume` (the
mechanism `rebut` already uses), requesting only the register block, not a
re-review — the `arbitrate` cleaner idiom, one retry then fail, cheap because it
does not re-run the review.

*Round 4 [MAJOR]: the retry is not always available. `Review.session_ref` is
`str | None`, `Engine.resume` requires a `str`, and the Claude engine's supported
non-JSON fallback returns `Review(text=…, session_ref=None)` — a contract
`tests/test_engines.py` already pins.* **When `session_ref` is `None` the retry
is skipped**, the original review is returned unchanged, and the block is emitted
directly. **The review text is always returned in full**; a paid review is never
discarded over a formatting miss.

*Round 9 [FATAL]: a twice-malformed register had no durable disposition. The
per-response `BLOCKED` footer recorded nothing, so if that outcome cleared the
pending latch the next round could initialize clean and the finding would be
suppressed through the ordinary `already_raised` workflow; and if the latch
stayed instead, it degraded into `STATE-UNAVAILABLE`, whose filesystem-only
escape cannot repair a missing model register. The implementation had to choose
between false clearance and an unrelated trap.* Neither is necessary: a failed
register is written into lineage state as **register debt** — `{round, reason}` —
which is a normal successful state write, so the latch clears cleanly. Debt
blocks (`CONVERGENCE: BLOCKED — register debt from round N`) and is discharged by
the next round whose register parses. It needs no new escape: the next clean
review clears it, and that is a review the operator was going to run anyway.

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
git grep -l -z    -E --no-color -e <pattern> <snapshot-commit> -- <pathspec>   # verdict
git grep -I -z -n -E --no-color -e <pattern> <snapshot-commit> -- <pathspec>   # display
```

**Two passes, and only the first decides.** *Round 15 [MAJOR]: a single `-I` pass
cannot be the closure authority, because `-I` suppresses matches in files git
classifies as binary — and this repository treats those as a supported case,
`orientation.file_evidence` detecting any NUL-bearing blob and `tests/test_packet.py`
pinning a late-NUL file. A registered predicate whose violation lives in such a
blob returns exit 1, is recorded `closed`, and can emit `NOT-BLOCKED` in its own
registration round while the violation survives.*

Simply dropping `-I` does not work either. **Verified on a fresh repository:** with
`-I` the binary match yields exit 1 and no output; without `-I` git emits the
untyped English line `Binary file HEAD:blob.dat matches\n` — no NUL separators, not
the `-z` record shape, and localizable. A parser fed that would mis-read it.

So the **verdict** comes from `-l -z`, which lists matching paths NUL-separated and
uniformly for text and binary alike (verified: `HEAD:blob.dat\0`), and the
**display** list comes from the `-I -z -n` pass. A path present in the verdict pass
but absent from the display pass is rendered `<path>: binary match (line not
shown)`. The blocking decision therefore never depends on the richer, more fragile
output — which is the same separation §2.2 reached for prose.

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

  *Round 14 [MAJOR]: parsing safely is not enough — revision 14 then injected
  `<path>:<line>: <text>` into the packet verbatim. `orientation.ChangeEntry`'s
  docstring already warns that `surrogateescape`-decoded paths must "never render
  them into the packet directly", which is why `orientation._display` exists and
  is documented as INJECTIVE; and both runner paths write stdin in text mode
  (`runner.py` `text=True`), where the streaming writer catches only
  `BrokenPipeError`/`OSError`. A `UnicodeEncodeError` is a `ValueError`, so a lone
  surrogate would either abort the review outright or leave the child waiting on
  an unwritten stdin until the timeout — over a filename.* **Every path *and every
  matched line* is rendered through the injective display helper before it reaches
  the packet, the footer or the trailer**; `_display` is promoted out of
  `orientation` into a shared helper for that. Injectivity matters as much as
  safety: two distinct paths must not collapse onto one label in a block the
  operator reads as an exhaustive match list.
- Exit codes on the verdict pass: `0` = matches, `1` = **no matches, which is
  success and means closed**, `≥2` = error. A malformed ERE exits `128` with
  `fatal: -e option, 'a[': Invalid regular expression`.
- Pathspec magic is accepted and silently changes the result set:
  `git grep -E -e x main -- ':(exclude)src'` returned matches from outside `src`.
  A pathspec beginning with `:` is **rejected at parse time** and the class
  recorded `malformed`.

**Bounds.** Per-class 10 s timeout, 200-match output cap, and — *round 2 [MINOR]
risk: revision 2 bounded each class but not the round, so a lineage of 36
timed-out classes would delay every round by six minutes before the reviewer even
starts* — a **60 s aggregate budget** across all classes. Classes not reached are
recorded `unchecked`. Registration is refused beyond 100 **non-superseded**
classes, with a message.

*Round 11 [MAJOR]: counting every tracked class made the cap remove the recovery
path at exactly the boundary it establishes — with 100 classes held, correcting a
unique malformed or over-broad `MAJOR` predicate needs a 101st object and would
be refused, leaving permanent `BLOCKED` unless the reviewer dishonestly
downgraded the severity or the operator reached for the kill switch. That
contradicts §1's named-escape guarantee.* Superseded classes are inert — never
rechecked, never blocking — so they do not consume the budget the cap exists to
protect, and `SUPERSEDE … WITH-PATTERN` applies atomically as one active class
retired and one added: net zero, and therefore always available at the boundary.

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

**The sweep runs twice: before the review, and again over whatever the register
just minted.**

*Round 10 [FATAL]: the sweep was specified only over classes the lineage already
holds, and it runs before the engine call — but a class registered by **this**
round's review does not exist until its register is parsed afterwards. So a brand
new `MAJOR` class, or a `WITH-PATTERN` replacement whose predecessor was
simultaneously marked non-blocking and never-rechecked, could be registered while
the same round emitted `NOT-BLOCKED` — stopping the operator before the promised
next-round check ever happened. Supersession made it worse than a one-round
delay: the old blocker was retired in the same breath.*

After a valid register is parsed, every **newly minted** mechanized predicate is
evaluated against the same snapshot before the trailer is computed. A new class
is `unchecked` until that pass runs it, and `unchecked` already blocks according
to severity (§2.5, §2.9) — so the fail-safe direction holds even when the pass
cannot run. The post-register pass draws on the same 60 s round budget; if the
budget is exhausted the class stays `unchecked` and blocks per severity. A new
unmechanized class starts `open` and blocks per severity with no pass needed.

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
where `head_symbolic_name` comes from the **reviewed** ref by one of two commands:

- **A named `head_ref`** → `git rev-parse --symbolic-full-name <head_ref>`.
  **Verified: for a commit sha this exits 0 and prints nothing** — so the test is
  empty output, not exit status. Empty means the reviewed ref is not a branch, an
  explicit `lineage` argument is required, and the call errors without one.
  Fail-closed beats silently minting a fresh lineage every round.
- **The checkout itself** — a dirty target, or `head_ref` defaulted to `HEAD` →
  `git symbolic-ref -q HEAD`.

*Round 12 [MAJOR]: using `rev-parse --symbolic-full-name` for the checkout breaks
the unborn-repository workflow this repo deliberately supports.
`handlers._converge_branch_review` branches on `orientation.has_head(repo)` and
falls back to `orientation.empty_tree`, and `tests/test_converge.py`'s
`test_converge_on_unborn_repo` exercises exactly that path with
`include_uncommitted: True` and no explicit lineage. With class closure on by
default, that first-review workflow would have errored before the reviewer ran.
Verified on a fresh `git init`: `rev-parse --symbolic-full-name HEAD` exits 128
with `fatal: ambiguous argument 'HEAD'`, while `symbolic-ref -q HEAD` returns
`refs/heads/master` and exit 0.* `symbolic-ref` reads the ref HEAD *points at*
rather than resolving it to an object, which is why it works before the first
commit — and an unborn branch is a perfectly good lineage key.

Every trailer prints `LINEAGE: <id> (rounds recorded: N)` so an unintended split
is visible.

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

*Round 8 [FATAL]: the quarantine latch below covers a **parse** failure but not a
**write** failure. If the very first registration fails to write — or an existing
state fails to persist a new class — no `corrupt-*` sibling exists, so the next
invocation reads nothing, initializes empty state, and reports `NOT-BLOCKED`. The
false clearance this section forbids, reached by the one path the latch did not
watch.* **A pending latch is therefore written before the engine call and cleared
only after the round finishes with either a successful atomic state write or an
explicit no-write outcome.** A latch present at read time is itself
`STATE-UNAVAILABLE` + `BLOCKED`. It costs one small write per review and it makes
the two failure modes symmetric: neither a corrupt read nor a failed write can
silently become an empty lineage.

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
the documented stop signal, an open
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

or `CONVERGENCE: NOT-BLOCKED — no blocking class is unclosed; advisory classes
may remain open. Reviewer findings still govern.`

*Round 7 [MAJOR]: revision 7 mandated "no unclosed class", which is a false
factual assertion whenever a `MINOR` or `OUT-OF-SCOPE` class is open — and those
are tracked-but-advisory by §2.9, so the documented stop signal would routinely
contradict the state in the same trailer.* The wording now says only what is
true.

That wording is otherwise deliberate and non-negotiable per §1: it is not a
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

A **second** reserved block lists every unmechanized class the lineage holds,
**including closed ones**, with id and status:

```
=== UNMECHANIZED CLASSES — no predicate; you are the check ===
[3f2a91c4, MAJOR, open, first raised round 7] <invariant>
  procedure: <procedure>
[91b0e77d, MAJOR, closed at round 9] <invariant>
  procedure: <procedure>
```

*Round 7 [MAJOR] gap: §2.10 promised unmechanized classes are "always shown", but
the only specified injection was `=== UNCLOSED CLASSES ===`, whose entries are by
definition not closed. A closed unmechanized class was therefore invisible to
every later reviewer, so the `REOPEN` added at round 6 was unreachable in
practice — the defect could recur while the state stayed closed and the trailer
said `NOT-BLOCKED`.* Closed entries are listed precisely so a later cold reviewer
has the id it needs to emit `REOPEN`. Both blocks are reserved from the packet
budget rather than trimmed.

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

1. **A reviewer can simply not register a class it found**, or register nothing
   at all. The prompt states the criterion; nothing enforces it, and round 9
   established that nothing *can* — this is the ceiling of the whole design, not
   an implementation gap (§2.2). Largest residual, unclosed, and now stated in §1
   rather than papered over by a parser.
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

New pure module `class_closure.py` — register parsing, class ids, status
transitions, survivor computation, debt, block rendering — with the
git call and the clock injected, keeping the repository's pure-core/injected-edge
split. `handlers.py` wires it and owns the one register retry via
`engines.Engine.resume`; `prompts.py` carries the register grammar, the
the register grammar and the `_CALIBRATION` amendments;
`orientation.py` renders the injected blocks after `already_raised`; `server.py`
exposes `lineage`, `exempt`, `unexempt`, `class_closure`; `logs.py` records
`base_id`/`head_id` (§6). **`README.md` is in scope, not optional** — *round 1
[MAJOR] gap: the shipped README documents caller-managed state and stopping on
reviewer-emitted `CONVERGED`, so an operator following the docs would bypass the
new authority.*

TDD, RED first. Behavioural tests that must exist:

**Register parsing** (strictness matched to `arbitration.parse_*`, since this is
the one model-authored surface that is parsed at all): two mechanized records
parse; `NONE` parses as empty; absent → one retry, then register debt + block;
duplicate field within a record rejected; missing required field rejected; a
record after the block's end rejected; a field name appearing in earlier prose
does not confuse the parser; unmechanized record with `PROCEDURE` parses;
`CLOSED`/`REOPEN`/`RECLASSIFY`/`SUPERSEDE` naming an unknown id rejected; the
retry path is taken exactly once and a successful retry parses; **a `Review` with
`session_ref=None` skips the retry, returns its text unchanged, and blocks per
policy** (round 4); **two records sharing a pattern and pathspec get two distinct
ids and two independent state objects** (round 4's dedup FATAL).

**Nothing outside the register is parsed** (round 9's FATAL — the record grammar
was impossible, since a headerless continuation is by definition inside the
preceding record): a review whose prose describes a class but whose register says
`NONE` **parses cleanly and records nothing**, and the test asserts exactly that,
because the opposite is unachievable and §1 now says so; **a clean late-round
response whose "What doesn't work" body is `CONVERGED — no blocking findings at
this round` parses** (round 9 — the record grammar made the existing calibration
output unparseable); a prose `[MAJOR]` tag disagreeing with the register's
`SEVERITY` is **not** a parse error, because the register's severity is the only
one a class has (round 9's two-severity FATAL).

**Multi-line supersession** (round 9's MAJOR): `SUPERSEDE`/`BY` and
`SUPERSEDE`/`WITH-PATTERN`/`PATHSPEC`/`CLASS` each parse with one field per line;
**a regex, pathspec or invariant whose text contains the literal `PATHSPEC:` or
`CLASS:` still parses to the correct fields**, which the single-line form could
not do.

**Register debt** (round 9's FATAL): a twice-malformed register writes
`{round, reason}` into lineage state, which is a **successful** state write that
clears the pending latch; the debt blocks; the next round with a parsing register
discharges it; a round whose register is malformed again keeps exactly one debt
record rather than accumulating.

**Recurrences are not parsed** (rounds 3, 5 and 6 — the mechanism's own hot path,
broken three times by a hand-authored grammar): a review that reports surviving
matches only in prose, with a register of `NONE`, **is well-formed and still
blocks** on the git result; a review that omits the recurrence prose entirely
**also still blocks**, because the verdict never depended on the reviewer's text;
`[RECURRENCE <id>]` appearing anywhere changes no parse outcome.

**Cap boundary** (round 11): at exactly 100 non-superseded classes a new
registration is refused, **but `SUPERSEDE … WITH-PATTERN` and
`SUPERSEDE … WITH-PROCEDURE` both still succeed** because each is net zero;
superseded classes do not count toward the cap.

**Mechanized → unmechanized recovery** (round 13): a `MAJOR` class whose regex is
`malformed` or `over-broad` and whose invariant turns out to be inexpressible can
be replaced by `SUPERSEDE`/`WITH-PROCEDURE`; the replacement is unmechanized,
starts `open`, blocks per severity, and closes only on a later `CLOSED:` — and
this works at the cap boundary too.

**New-class evaluation** (round 10's FATAL): a review registering a new `MAJOR`
class whose predicate still matches **cannot** emit `NOT-BLOCKED` in that same
round; `SUPERSEDE … WITH-PATTERN` cannot emit `NOT-BLOCKED` before the
replacement predicate has been run and found closed; a new class the budget could
not reach is `unchecked` and blocks per severity; a new `MINOR` class does not
block whatever the pass finds.

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

**Git boundary:** exit 1 **on the verdict pass** is closure, not failure; **a
violation inside a binary-classified blob keeps the class open** and renders as
`binary match (line not shown)` (round 15's MAJOR) — asserted with a late-NUL
file like the one `tests/test_packet.py` already pins; a verdict-pass path absent
from the display pass never silently disappears from the block; exit ≥ 2, invalid ERE, and
timeout each → `malformed`; > 200 matches → `over-broad` with a truncated,
counted block; aggregate budget exhaustion → `unchecked`; a path containing a
newline and a non-UTF-8 byte parses correctly under `-z`, **and the fully rendered
packet, footer and trailer containing that match all encode as UTF-8** — asserted
on the rendered output, not merely on the parsed grep result — **with two paths
differing only in a non-UTF-8 byte rendering to distinct labels** (round 14); a pathspec beginning
with `:` is rejected before any git call; registration beyond 100 non-superseded classes is
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

**Lineage:** **an unborn repository reviewed dirty with no explicit `lineage`
succeeds and keys on `symbolic-ref -q HEAD`** — `test_converge_on_unborn_repo`
must still pass with class closure at its default (round 12); a reviewed
`head_ref` that is a branch but not checked out yields
its own lineage, and two such branches off one base differ; a `head_ref` that is
a sha (empty `--symbolic-full-name` output, exit 0) without `lineage` errors;
**a dirty target uses the checkout's `HEAD` and rejects a supplied `head_ref`**
(round 3); unparseable state → `STATE-UNAVAILABLE` + `BLOCKED`, review text still
returned, **and the corrupt file is quarantined to a named path rather than
overwritten or silently replaced by a fresh lineage**; **re-running after a
quarantine does NOT start a fresh lineage — it blocks again until the quarantine
sibling is gone** (round 4's latch FATAL); write failure → same outcome, message
names directory and errno; **a failed write leaves the pending latch in place, so
the next invocation blocks instead of initializing empty state** (round 8's
FATAL); **a pending latch found at read time blocks even with no state file and
no quarantine sibling**; the latch is cleared after a successful write and after
an explicit no-write outcome; state replaced atomically; a failed engine call
leaves state byte-identical.

**Exemptions:** an exempt match is subtracted; **a second, textually identical
line in the same file is not** (round 2's collision); an exemption whose line
text changed is void and the match resurfaces; `unexempt` restores a match; both
appear under `CLAIMED EXEMPT` and in the trailer.

**Packet:** the unclosed-classes block is rendered after `already_raised` and
survives budget trimming; **a closed unmechanized class still appears, with its
id and `closed` status, in the unmechanized block of a later round's packet**
(round 7 — without this, `REOPEN` is unreachable), and both reserved blocks
survive trimming.

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
