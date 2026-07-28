# Brief: class closure — make a defect *class* a tracked object, not an operator inference

Status: DRAFT for review, revision 1.

## 0. The defect this fixes

A real ten-round `critique_branch` loop against Parallax
(`runbook-v2-card-execution`, base `91f920a`, ten records in `~/.paranoia/logs/`
between `20260728T142314` and `20260728T162438`) produced findings per round of
7 → 9 → 5 → 2 → 2 → 2 → 3 → 2 → 1. Rounds 7, 8 and 9 were **the same defect three
times**: the v2 "is anything open?" predicate was incomplete — round 7 found
escalations missing from it, round 8 ungated progress, round 9 unresolved starts.
Three sites, one invariant, three rounds, three instance-shaped fixes.

The operator was not being careless. **The protocol never gave the class anywhere
to live.** Three mechanisms in this repository actively produce that outcome:

1. **The finding schema is instance-shaped.** `prompts._SECTION_BODIES` asks each
   finding for `file:line`, the failure mechanism, and the observable symptom. It
   never asks for the invariant, and never asks where else the invariant is
   violated. The reviewer *derives* the class in order to find the instance, then
   the protocol discards it. A remedy inferred from an instance-shaped finding is
   instance-shaped.
2. **The only cross-round channel is pointed the wrong way.** `already_raised`
   (`orientation.build_orientation`, `orientation.build_packet`,
   `handlers._plan_body`) is the sole memory between rounds, and it renders as
   `=== Already-raised — do NOT restate these; hunt for what they missed ===`.
   The one channel that could catch a recurrence instructs the reviewer to stop
   looking there. Round 8 was not permitted to notice it was re-reporting round 7.
3. **The severity floor meters the leak.** `prompts._CALIBRATION` tells round ≥ 3
   to withhold everything below `[MAJOR]`. So a class surviving at a new site only
   surfaces when that individual site clears the floor — which is precisely the
   one-per-round trickle observed at rounds 7–9.

There is no lineage state of any kind: `logs.write_log` writes one record per
call and nothing links round 9 to round 7.

**This is the same shape as the `arbitrate` substantiation defect fixed in #9** —
a per-instance check with the general rule left to interpretation. Different
tool, identical failure mode.

## 1. What the fix must achieve, and what it must not claim

**Must achieve.** A class reported in round N is a durable object with a
*mechanically re-checkable* membership predicate. Round N+1 re-runs that
predicate itself. A surviving unadjudicated site is a `[RECURRENCE]`, is exempt
from the severity floor, and **blocks the round from being reported converged** —
computed in Python, not asserted by the reviewer and not inferred by the operator.

**Must NOT claim.** The mechanism can only assert the *negative*. "No class is
unclosed" is not "the change is correct" — new findings are still the reviewer's
judgement. The trailer must therefore never emit a positive convergence verdict;
it emits `BLOCKED` or `NOT-BLOCKED`, and says which. Any wording that reads as
"converged" would launder a mechanical check into an approval, which is the
`arbitrate` failure mode in a new costume.

## 2. Mechanism

### 2.1 Findings declare their scope, and a class declares its predicate

Add to the finding rules for "What doesn't work" and "Gaps": every finding
carries `SCOPE: isolated` or `SCOPE: class`.

`SCOPE: class` means *the reasoning that condemned this site would condemn
another site if one existed* — a violated invariant, not a one-off. A genuine
off-by-one is `isolated`, and requiring class machinery for it would be exactly
the over-engineering `prompts.CODE_REVIEW_INSTRUCTIONS` already calls a defect.

A `SCOPE: class` finding must additionally emit, contiguously:

- `INVARIANT:` — one line, stated **without reference to the reported site**.
- `ENUMERATION-PATTERN:` — a POSIX-extended regex that matches every *candidate*
  site (violating and conforming alike).
- `ENUMERATION-PATHSPEC:` — a git pathspec bounding the search, or `.` for the
  whole tree.
- `SITES:` — the reviewer's adjudication of what that pattern finds at this
  snapshot: one `<path>: VIOLATING|CONFORMING — <reason>` per match.

Or, when no regex can express membership:

- `ENUMERATION: unmechanized — <the procedure a reviewer must follow>`

The reviewer is the right author: it has just derived the class in order to
report the instance. The cost is one paragraph at the moment it is cheapest.

**A pattern, not a command.** The predicate is *data*, never an argv. The server
runs one fixed invocation with the pattern and pathspec substituted as operands:

```
git grep -I -n -E --no-color -e <pattern> <snapshot-commit> -- <pathspec>
```

`shell=False`, no pipes, no redirection, no reviewer-chosen binary or flags. This
removes model-authored command execution from the design entirely rather than
trying to sanitise it. `git` is already a hard prerequisite; `rg` is not present
on the reference machine and is not introduced.

**Pathspec magic must be rejected.** Verified empirically in this repository
today: `git grep -E -e x main -- ':(exclude)src'` is accepted and silently
changes the result set. A pathspec beginning with `:` is rejected at parse time,
and the class is recorded `malformed` rather than run.

**Bounds.** Per-class 10 s timeout and a 200-match cap. A class over the cap is
recorded `over-broad`, blocks, and the block text tells the reviewer to narrow
the pattern — an unbounded predicate is not a usable membership test.

### 2.2 The class register makes it parseable

Scraping classes out of five sections of prose is unreliable. The review must end
with a machine-readable block, one record per class finding, following the
`arbitrate` trailer idiom:

```
=== CLASS REGISTER ===
CLASS: <invariant, one line>
PATTERN: <regex>
PATHSPEC: <pathspec>
SITES: <path>: VIOLATING — <reason>; <path>: CONFORMING — <reason>
CLOSED: <class-id>            # only for a prior unmechanized class judged closed
```

**Absent register → fail-open, but visibly.** If a review omits the block, the
round records no classes and the trailer says `CLASS-REGISTER: absent`. Erroring
would discard a paid review over a formatting miss; silence would hide the gap.
The operator sees it.

### 2.3 Class identity is the predicate, not the label

`class_id = sha256(normalized_pattern + "\0" + normalized_pathspec)[:12]`.

This is the load-bearing decision. Round 7 called the class "escalations" and
round 9 "unresolved starts" — no label match would ever connect them, and asking
a model to reuse a prior label is asking it to be consistent across cold
sessions. A predicate hashes the same however it is described.

Residual: a reviewer restating the same class with a slightly different regex
mints a second overlapping class. That fails toward *more* tracking, not less,
and is accepted.

### 2.4 Lineage state

`~/.paranoia/lineages/<lineage_id>.json`, holding per class: `class_id`,
`invariant`, `pattern`, `pathspec`, `first_round`, `status`
(`open|closed|unmechanized|over-broad|malformed`), the adjudicated site set, and
exemptions.

`lineage_id` defaults to `sha256(resolved_repo_path + "\0" + base_ref)[:12]`, and
is overridable by a `lineage` call argument. Every round's trailer prints
`LINEAGE: <id> (rounds recorded: N)` so that a silent split — the operator
changed `base_ref` mid-loop and started a fresh lineage without noticing — is
visible on the next round rather than never.

State is read before the engine call and written only after a successful one, so
a failed review does not corrupt the lineage.

### 2.5 The closure check

Each round N > 1, before invoking the engine, for every `open` class:

1. Run the fixed `git grep` above against the snapshot commit the round is
   reviewing (converge mode already resolves it; no checkout is needed —
   `git grep <commit>` reads the tree directly).
2. Compute survivors:
   - every recorded `VIOLATING` site still present, **and**
   - every match **not present in the recorded site set at all** — unadjudicated,
     therefore not known to conform.
3. Subtract recorded exemptions.

A class is `closed` when survivors is empty. **A broad pattern therefore does not
block forever**: sites the reviewer adjudicated `CONFORMING` are not survivors.
Closure means *every site the predicate finds has been adjudicated and none is
violating* — which is the actual definition of a closed class.

**Site matching is by `(path, normalized matched line text)`, never by line
number**, because line numbers shift under the very edits being reviewed. A site
whose text changed no longer matches its record, becomes unadjudicated, and
therefore becomes a survivor. That fails toward blocking, which is the correct
direction.

### 2.6 Recurrence injection

`already_raised` keeps its current meaning and its current suppress instruction —
it is caller-authored and stays a caller concern. A **second, server-generated**
block is added to the packet, carrying the opposite instruction:

```
=== UNCLOSED CLASSES — re-verify these; do NOT suppress ===
[class <id>, first raised round <K>] <invariant>
  surviving sites: <path> — <matched line>
```

with: *these were reported in an earlier round and are not closed. Each surviving
site is a `[RECURRENCE]`. Report every one. The ROUND severity floor does not
apply to a recurrence.*

Claimed exemptions are shown too, under `=== CLAIMED EXEMPT ===`, so the cold
reviewer can challenge an illegitimate one. Nothing self-attested escapes review.

### 2.7 The computed trailer

Appended by `handlers._footer`, after the review text:

```
LINEAGE: <id> (rounds recorded: N)
CLASS-REGISTER: parsed 3 | absent
CLASS-CLOSURE: 2 open, 1 closed this round, 4 recurrences, 1 exempt
CONVERGENCE: BLOCKED — 2 class(es) unclosed: <id> <invariant>; <id> <invariant>
```

or `CONVERGENCE: NOT-BLOCKED — no unclosed class; reviewer findings still govern.`

The second wording is deliberate and non-negotiable per §1: it is not a
convergence verdict.

### 2.8 Exemptions

A surviving site that is genuinely fine is exempted by an `exempt` call argument
(`class_id`, `path`, `reason`), recorded in lineage state, echoed in every
subsequent trailer, and shown to every subsequent reviewer for challenge. This is
the single place operator judgement legitimately enters, and the design makes it
a recorded, adversarially-reviewed artifact instead of a silent lapse.

### 2.9 Severity-floor amendment

`prompts._CALIBRATION` gains: *the ROUND severity floor never applies to a
`[RECURRENCE]`. A class raised in an earlier round and still open is
merge-blocking by construction, whatever the severity of the individual site.*

### 2.10 Unmechanized classes

Carried forward as a reviewer obligation ("re-verify by the stated procedure and
report survivors"), always shown, never floor-suppressed, and marked
`unmechanized` in the trailer so their weakness is visible rather than silent.
They cannot block mechanically — there is nothing to run. They close only when a
later reviewer names the `class_id` on a `CLOSED:` line: still a judgement, but
an explicit, cold, recorded one rather than an operator's silent assumption.

## 3. Scope

**In:** `critique_branch` in converge mode (default), which is the only path with
a resolved snapshot commit to run the predicate against.

**Out:** `critique_plan` (a plan has no code sites to enumerate; its premises are
checked against the repo, which is a different mechanism), `query`, `rebut`, and
legacy non-converge `critique_branch` (dirty/in-place reviews have no stable
commit; converge mode already synthesises one for dirty trees, so the gap is
narrow and users on the default path are covered).

**Kill switch:** `class_closure` call arg / `.paranoia.toml` key, default `true`.

## 4. Residual risks, stated

1. **A reviewer can tag everything `SCOPE: isolated`** and avoid the work
   entirely. The prompt states the criterion, but nothing enforces it. This is
   the largest residual and the mechanism does not close it.
2. **`unmechanized` classes are materially weaker** — no mechanical check, and
   closure is a model's word. They are marked, not solved.
3. **A wrong `CONFORMING` adjudication permanently whitelists a real violation**
   at that site. Mitigated only by the site record being shown to later reviewers,
   not by anything mechanical.
4. **Regex is a coarse membership test.** Classes that are genuinely semantic
   (cross-file dataflow, type-level invariants) degrade to `unmechanized`.
5. **A pattern matching > 200 sites blocks as `over-broad`** and needs reviewer
   iteration; a class whose true membership really is that large is not
   expressible under this design.

## 5. Implementation

New pure module `class_closure.py` (parse register, compute survivors, site
normalization, class ids, render blocks) with the git call injected, keeping the
repository's existing pure-core/injected-edge split. `handlers.py` wires it;
`prompts.py` carries the schema and floor amendment; `orientation.py` renders the
new block; `server.py` exposes `lineage`, `exempt`, `class_closure`.

TDD, RED first. The behavioural tests that must exist:

- a register with two classes parses to two records; an absent register yields
  none and sets `CLASS-REGISTER: absent`
- the same invariant described in two different words under the same pattern
  collapses to one `class_id`; the same words under different patterns do not
- a recorded `VIOLATING` site still present survives; a recorded `CONFORMING`
  site does not; a match absent from the record survives
- a site whose line moved but whose text is unchanged is matched; a site whose
  text changed becomes a survivor
- survivors non-empty ⇒ `CONVERGENCE: BLOCKED` and the ids are named
- survivors empty ⇒ `NOT-BLOCKED`, and the text does **not** contain the word
  converged
- an exempt site is subtracted, appears under `CLAIMED EXEMPT`, and is echoed in
  the trailer
- a pathspec beginning with `:` is rejected and the class recorded `malformed`
- \> 200 matches ⇒ `over-broad`, blocks, and the message says to narrow
- a failed engine call leaves lineage state byte-identical
- `class_closure: false` restores today's behaviour exactly

## 6. Acceptance

Replay the ten recorded rounds of the `runbook-v2-card-execution` lineage
(`~/.paranoia/logs/`, `20260728T142314`–`20260728T162438`) through the register
parser and closure checker. Rounds 7, 8 and 9 are the known-positive: the
mechanism is only worth shipping if a class registered at round 7 has a surviving
unadjudicated site at rounds 8 and 9 and blocks both.

Those ten reviews predate the register, so their text carries no `CLASS REGISTER`
block; the replay therefore tests the checker against a register hand-derived
from round 7's finding text, and that derivation is stated in the test rather
than hidden in it. This is a weaker acceptance than a live loop, and the live
loop is the real test.
