# Brief: class closure for `critique_plan` — what transfers, what must not

Status: **IMPLEMENTED at revision 4. Plan-review loop stopped at round 3 by the
operator — not converged.** Round 3 returned two FATALs, so this document never
reached a clean round; §9 records what an approver still has to satisfy themselves
about, and the implementation review is where the rest was caught. Where the code
and this brief differ, the code is the authority. Written in response
to an
observed plan seam that ran nine rounds over 2h15m with no mechanical stopping
condition. Every claim below was checked against the code and against
`~/.paranoia/logs/`, not against docstrings.

*Revision 2 folds codex plan-review round 1 (1 FATAL, 8 MAJOR, 1 MINOR; every
finding accepted). The FATAL: revision 1 proposed rejecting `PATTERN` in plan mode
while leaving `CLASS_REGISTER_INSTRUCTIONS` — which presents `PATTERN` as the
normal record — as the only register prompt, so a compliant reviewer would have
been refused on every class it registered (§2.3). Two decisions reversed
outright: cross-mode lineage merging, which revision 1 called "coherent" and
declined to prevent, is undefined behaviour and is now forbidden (§2.7); and the
§4 prompt repair, as revision 1 stated it, would have forbidden convergence
forever, because the block it named deliberately lists closed classes (§4). One
claim withdrawn: `CLASS-REGISTER: parsed N` counts transitions as well as new
classes (`handlers.py:660-664`), so it cannot measure churn (§5).*

*Revision 3 folds codex round 2 (2 FATAL, 5 MAJOR, 2 MINOR; every finding
accepted). **Both FATALs were introduced by revision 2's own fixes**, which is the
failure `docs/class_closure_plan.md` was written about, reproduced here: the plan
register prompt added in §2.3 told the reviewer no class may leave the loop
unblocked, contradicting the advisory-severity rule three sections later and
manufacturing a fresh false refusal; and the `plan_path`-derived lineage in §1.4
reintroduced, one level up, the exact fresh-lineage false clearance revision 1 had
just refused for `plan_text`. Derived plan identity is now deleted rather than
repaired — an explicit `lineage` is required for both input forms. A second claim
withdrawn: §5's "age of an open class" is not computed, because `first_round` and
`rounds` are in different units.*

*Revision 4 folds codex round 3 (2 FATAL, 1 MAJOR). **For the second consecutive
round, both FATALs were defects introduced by the previous round's fixes** — the
pattern `docs/class_closure_plan.md` was written about, reproduced on a document
arguing for it. Revision 3's §4 rendering split welded together two independent
properties (exemption-from-suppression and the `CONVERGED` prohibition) and so let
a closed blocking class recur into a `NOT-BLOCKED` trailer; and revision 3's
rollout prescribed the consumer's existing branch-lineage key for plan seams, which
would have made every normal card false-refuse at its frozen seam. Revision 3 also
left a stale sentence in §2.7 asserting a derived plan key that §1.4 had just
deleted.*

**The short answer.** The unmechanized half of `class_closure` transfers to
`critique_plan` essentially intact, and I verified it runs with no repository and
no `git` call at all. The mechanized half must **not** transfer, and the argument
against it is not "a regex over prose false-positives" — it is worse than that: a
predicate over plan prose **closes on a rewording**, and a rewording is precisely
the failure mode this mechanism exists to catch. Evidence in §1.1.

What the result buys is **non-forgetting plus explicit closure**, not recurrence
*detection*. §5 accounts for exactly which computations fire and which do not, and
proposes the wording that keeps the README from over-claiming.

---

## 0. What was observed

### 0.1 The seam

Nine `critique_plan` calls against one card plan, `~/.paranoia/logs/`,
2026-08-03 19:59:25 → 22:14:33 (2h15m). No `critique_branch` call ran in that
window — the last one was `20260803T172732`.

| # | time | engine | chars | FATAL | MAJOR | MINOR |
|---|---|---|---|---|---|---|
| 1 | 19:59:25 | codex | 10602 | 2 | 10 | 3 |
| 2 | 20:20:47 | claude | 12336 | 1 | 3 | 4 |
| 3 | 20:39:45 | claude | 7314 | 0 | 3 | 0 |
| 4 | 20:53:28 | claude | 3708 | 0 | 0 | 0 |
| 5 | 21:03:07 | codex | 10548 | 2 | 12 | 6 |
| 6 | 21:16:54 | codex | 9800 | 2 | 16 | 0 |
| 7 | 21:41:29 | codex | 6038 | 0 | 10 | 0 |
| 8 | 22:06:51 | codex | 3664 | 0 | 6 | 0 |
| 9 | 22:14:33 | codex | 5233 | 0 | 8 | 0 |

Round 4 emitted a genuine `CONVERGED — no blocking findings at this round.`
(verified in context; the token also appears in round 8, but there it is the
reviewer quoting an arbitration outcome, not a declaration). **Ten minutes after
that `CONVERGED`, round 5 returned 2 FATAL and 12 MAJOR.** The reviewer's own word
was the only stop signal available, and it was worth nothing.

### 0.2 One invariant, four spellings, four rounds

The recurrence the brief predicted is present in the logs, and it is not
marginal — it is the seam's most-cited defect:

| round | tag | claim |
|---|---|---|
| 1 (19:59) | FATAL | "SU5–SU8 put native mutation campaigns before the frozen card-seam review, violating process v2" |
| 5 (21:03) | MAJOR | "Section 3 calls one native pilot per sub-unit 'exploratory/diagnostic' and argues that it is not a governed campaign. Process v2 does not recognize that distinction" |
| 6 (21:16) | FATAL | "Phase 0 **still** runs four native campaigns before SU0, contradicting two hard card instructions" |
| 7 (21:41) | MAJOR | "Section 4 says the only seam campaigns are 'one per module (four lanes),' omitting the newly authored production script" |

One invariant — *every mutation campaign in a v2 card sits at the frozen card seam
and covers every owned definition* — violated in four different plan sections
across four rounds, each instance cited against the same authorities
(`COMPLEX_DELIVERY_RUNBOOK.md:1277`, `:1282-1285`, `:1367-1375`;
`AGENTS.md:34-44`, `:139-142`). Round 6's reviewer wrote "**still**": it knew it
was repeating itself. Nothing mechanical knew.

This is the reference incident for this brief in the same way the ten-round
Parallax loop is the reference incident for `docs/class_closure_plan.md` §0 — with
one difference that matters for §1.1: **the invariant is stable and repo-anchored,
while the prose expressing its violation changed completely every round.**

### 0.3 The asymmetry, verified in code

- `handlers.critique_plan` (`handlers.py:324-365`) builds a body, composes
  `PLAN_REVIEW_INSTRUCTIONS`, runs the engine, logs, and returns
  `_footer(review, engine)`. There is no `_ClassClosure`, no lineage, no trailer.
  `_ClassClosure` is constructed in exactly one place, `handlers.py:241`, inside
  `_converge_branch_review`.
- `server.py:196-209` — the `critique_plan` schema carries `plan_text`,
  `plan_path`, `context`, `repo_path`, `focus`, `already_raised`, `stakes`,
  `round` and the four `_COMMON` keys. No `class_closure`, `lineage`, `exempt`,
  `unexempt`, or `converge`.
- `docs/class_closure_plan.md:734` scopes `critique_plan` **out**, with the reason
  "a plan has no code sites to enumerate". §1.1 below agrees with the exclusion and
  disagrees with the reason.
- Across all 788 log records, a `lineage` field appears in **143 `critique_branch`
  records and 0 `critique_plan` records**. (This is stronger evidence than
  searching the review text for trailers: `_log` runs before the trailer is
  appended at `handlers.py:294`, so the trailer never reaches the log at all.)
- `handlers.py:364` logs `{"grounded", "model"}` for a plan review. Neither
  `round`, nor `already_raised`, nor any identifier of the plan is recorded. **A
  plan seam is not reconstructible from the logs at all** — see §2.6.

Consequence, already documented on the consumer side:
`COMPLEX_DELIVERY_RUNBOOK.md:894` — *"on `critique_branch`, a `CONVERGENCE:
NOT-BLOCKED` trailer **and** convergence … ; on `critique_plan`, the triage half
alone, since it has no trailer."* The operator has already written down that the
stop condition is half-strength here.

---

## 1. The four decisions

### 1.1 Should a plan class carry a predicate? **No. Unmechanized only.**

Three independent arguments. The first two are decisive on their own.

**(a) A violation-only predicate over plan prose closes on a rewording.** §2.1 of
the existing brief defines closure as zero matches. Apply that to §0.2: a regex
written at round 1 to match "SU5–SU8 … before the frozen card-seam review" returns
zero matches at round 5, where the same defect is spelled "exploratory/diagnostic
pilot per sub-unit". The class would have **closed at round 5 with the defect
live**, and the round-6 FATAL would have arrived as a fresh finding against a
closed class. On a branch, editing the source until the predicate stops matching
*is* the fix; in a plan, editing the prose until the predicate stops matching *is
the failure mode*. The polarity that makes the mechanism sound on source makes it
actively harmful on prose.

**(b) A conformance predicate is gameable by construction, and was already killed
once.** The obvious repair — match the *required* text, close on ≥1 match — is
round 1's FATAL in `docs/class_closure_plan.md:129-148`, which killed
candidate-matching because git could recheck presence but never whether the
invariant was still violated. It is worse here than there: the plan's author is an
LLM that can satisfy any prose predicate by writing the sentence it asks for,
without changing a single ordering decision in the plan.

**(c) A predicate over the *repository* has inverted polarity for the commonest
plan defect.** Plan findings are premises the code contradicts —
`PLAN_REVIEW_INSTRUCTIONS` (`prompts.py:89`) calls that "the most dangerous kind of
plan" and the reviewer's top job. Round 6 of the incident is exactly this: *"Section
2 depends on an 'existing' `run_checker_over_tree` primitive that does not exist."*
The violation is the **absence** of a symbol. Zero matches is closure, so absence
is inexpressible as a violations-only regex. The subset of plan defects a repo
regex *could* express is the subset where the plan's own text is irrelevant — at
which point it is a branch review, not a plan review.

**What the unmechanized path actually costs, verified.** I ran the pure core with
a `GitGrep` callable that raises `AssertionError` on invocation, driving one
lineage through: parse a `PROCEDURE` register → `apply_register` → `sweep` →
`sweep(only=minted)` → render both blocks → trailer → `CLOSED` → trailer →
`REOPEN` → trailer. The grep never fired.
`class_closure.py:600` skips any class that is `not cls.mechanized`, and
`make_grep` (`class_closure.py:657`) only builds a closure — it runs no subprocess
at construction. Observed output:

```
CLASS-CLOSURE: 1 open, 0 closed, 0 surviving matches, 0 exempt, 1 unmechanized
CONVERGENCE: BLOCKED — 1 class(es) unclosed:
  4cbc119b every mutation campaign must sit at the card seam and cover every owned definition (unmechanized: awaiting reviewer CLOSED or RECLASSIFY)
  Any `CONVERGED` in the review text above is VOID: …
```
then after `CLOSED:` → `NOT-BLOCKED`, then after `REOPEN:` → `BLOCKED` again.

**So the unmechanized half is already repo-free, git-free and complete.** It does
not need porting; it needs *reaching*.

**Therefore a plan register must reject `PATTERN`/`PATHSPEC` outright** rather than
accept it and grep. Accepting it in plan mode with no `repo_path` would run
`git grep` against `self.repo = None`; accepting it *with* a `repo_path` would ship
argument (a)'s false closure.

### 1.2 Should `already_raised` be accumulated server-side? **No. Log it first.**

Two arguments against, and one thing to do instead.

**(a) The version worth having requires the parser revision 10 deleted.** The
valuable form of this is *the server derives the raised list from the review it
already has*. That is parsing findings out of prose. `docs/class_closure_plan.md`
§2.2 records eight review rounds spent attempting it, and round 9 establishing it
is not merely broken but impossible in principle. Re-opening it for plans, where
the prose is *less* structured than a code review's, is the least defensible
change available.

**(b) The version that needs no parser adds a termination hazard.** Unioning the
caller's per-round entries into durable state does not need prose parsing — but
`already_raised` renders as *"do NOT restate"* (`handlers.py:319`). A caller-owned
list has an implicit revocation: stop passing it. A server-owned one suppresses a
conceded-wrong finding, or a fix that later regressed, **permanently** — and
recovering that needs a new un-raise argument, i.e. mechanism added to fix
mechanism added. The class register already provides the durable channel *with* a
revocation (`REOPEN`), for the object that actually matters.

**(c) I cannot measure the failure it would fix, and neither can anyone else.**
`handlers.py:364` does not record `already_raised`. Across 212 plan records there
is no evidence a caller ever dropped an entry, because the evidence was never
written down.

**Do instead:** record `already_raised` (count and contents), `round`, and the
plan identity in `_log` for `critique_plan` — and `already_raised`/`round` for
`critique_branch`. This is the same move `docs/class_closure_plan.md` §6 made for
`base_id`/`head_id` after round 1 found the incident unreplayable: cheap, no
behaviour change, and it makes the *next* version of this decision evidential
rather than argued. Revisit server-side accumulation when there is a measurement.

### 1.3 Should the trailer refuse "converged" while a class is open? **Yes — and the code to do it already exists, unchanged.**

`render_trailer` (`class_closure.py:821-877`) never emits the word "converged" in
the affirmative. It emits `CONVERGENCE: BLOCKED` or `CONVERGENCE: NOT-BLOCKED`,
and when BLOCKED it appends, verbatim:

> Any `CONVERGED` in the review text above is VOID: it is the reviewer's judgement
> about new findings, not a statement about these classes.

That is precisely the §0.1 defect — a round-4 `CONVERGED` followed by 2 FATAL ten
minutes later — and it needs no new code, only to be reached from
`critique_plan`. `handlers.py:365` returns `_footer(review, engine)` where the
branch path returns `f"{body}\n\n{trailer}"` (`handlers.py:294`).

**On the "do not build a gate that can false-refuse" constraint.** The trailer
blocks only on a class *the reviewer itself registered* at blocking severity and
that *no later reviewer has closed*. Its false-refusal mode is a reviewer
over-severing its own finding, and it inherits three recorded escapes: a later cold
reviewer's `RECLASSIFY` down to MINOR (`class_closure.py:519-521`), `SUPERSEDE`,
and `CLOSED` itself — plus `class_closure: false`. That is the same exposure the
branch path has shipped since 2026-07-28. It is not a new class of gate.

The measured cost of the register grammar, over the 143 branch rounds that ran it:
**one retry in 143 (0.7%)**. Reviewers produce a parseable register essentially
always.

### 1.4 What is a plan class's identity when the plan is being edited between rounds? **The iteration handle. Never the text.**

The premise "branch classes key off source; plan text moves under you" does not
survive contact with the code. `_lineage_id` (`handlers.py:626-644`) hashes
`(resolved repo path, base_ref, head symbolic name)` — a **branch name**. The
branch's content moves under you every round too; that is what a convergence loop
*is*. The lineage key is the handle on the iteration, deliberately not its content.

So the question is only: what is the plan's handle? **Answer: an explicit
`lineage`, always. Nothing is derived.**

*Round 2 [FATAL]: revision 2 derived a key from `plan_path` and called it "stable
across edits, which is correct". A path is not an identity. Rename or move the
plan — a scratchpad file tidied between sessions — and the derived key changes, so
`load_lineage` finds no state file and returns `Lineage(lineage_id)` empty
(`class_closure.py:335-336`); the trailer then reports `NOT-BLOCKED`
(`class_closure.py:874-876`) with the old class neither injected nor closed. That
is the identical false clearance revision 1 refused to allow for `plan_text`,
reintroduced one level up because a path felt stable enough. It is not, and
"stable enough" is not the standard §2.7 of the shipped brief sets.*

- **Explicit `lineage`** → used verbatim, exactly as branches do
  (`handlers.py:627-628`). Required whenever plan closure is on, for **both**
  input forms.
- **`plan_text` or `plan_path` without `lineage`** → the call fails closed, with
  the branch path's own remedy sentence: pass `lineage`, or `class_closure: false`.

This deletes the derived-identity code rather than writing it, which is the
correct direction for this repository — and it costs a file-backed plan one extra
argument that the dominant consumer has to pass anyway.

**The cost it moves rather than removes**, and which the rollout must carry: an
explicit key is used verbatim as the state filename (`class_closure.py:317-319`),
with no namespacing. Two seams sharing a key inherit each other's open blockers —
a false refusal of an unrelated valid plan. This is not new and is already
documented on the consumer side for branches
(`COMPLEX_DELIVERY_RUNBOOK.md:457-462`: *"a bare card id is unsafe … Use a globally
unique key (`parallax-<issue>-<card>`), pinned once and reused across both
stages"*).

**But the rollout must NOT reuse that convention verbatim, and revision 3 said it
should.** *Round 3 [FATAL], part 2: one Parallax card runs `critique_plan` at its
plan seam (`COMPLEX_DELIVERY_RUNBOOK.md:1267-1269`) and `critique_branch` at its
frozen card seam, where the head "is frequently not a branch" and an explicit
lineage is pinned for the whole seam (`:1345-1357`). Both would therefore have
been told to use `parallax-<issue>-<card>` — the same filename — and §2.7's mode
check would refuse the branch review with `STATE-UNAVAILABLE`. Every normal card
would false-refuse at its most expensive seam, and the operator's only escape
would be inventing an undocumented second key.*

Keys are therefore **mode-qualified**: `parallax-<issue>-<card>-plan` and
`parallax-<issue>-<card>-branch`. The mode check (§2.7) then catches a *mistake*
rather than firing on the prescribed convention, which is what a fail-closed check
is for. This is a documentation obligation and an acceptance fixture, not a
mechanism.

**This is also why plan closure must default OFF (§2.2)**, and the reason is now
stronger than revision 1's: with no derivable key at all, defaulting on would
hard-error *every* existing plan call, not merely the `plan_text` ones. The
dominant consumer passes `plan_text` regardless — in the incident session's
scratchpad the only markdown written between 19:00 and 22:10 was the findings note
at 21:59, and Parallax's rules keep plans in GitHub issues rather than files
(`CLAUDE.md`, *Work tracking*: "Do NOT create `work/*.md` planning files").

---

## 2. What I propose to build

### 2.1 Reach the existing unmechanized machinery from `critique_plan`

Add to the `critique_plan` schema: `class_closure` (bool), `lineage` (string).
Nothing else.

**Plan mode runs no sweep and binds no grep.** `_ClassClosure.prepare()` and
`.settle()` both call `cc.sweep(...)` with a repo- and head-bound grep
(`handlers.py:497`, `:523`, `:562-563`). In plan mode there is neither, and by
§2.7 a plan lineage can hold no mechanized class, so there is nothing to sweep:
the plan coordinator omits both calls rather than passing a grep that would never
legitimately fire. Whether that is a flag on `_ClassClosure` or a sibling
coordinator is an implementation shape; that plan mode never reaches `make_grep`
is a contract, and §7 tests it.

Everything else is reached unchanged: `load_lineage`/`save_lineage`, the pending
latch and quarantine, `parse_register`/`apply_register`, the one-shot register
retry, `render_trailer`, and the failed-review rule that leaves the lineage
byte-identical (`handlers.py:509-515`).

### 2.2 Default **off**, and a call argument only — `.paranoia.toml` is not consulted

Justified narrowly: the branch default was earned by a derivable key, and plans
have none at all (§1.4). `class_closure: true` without a `lineage` is an error,
never a silent skip — a mode that degrades quietly is how a gate stops existing.

*Round 2 [MAJOR] risk: revision 2 left the interaction with repo configuration
undefined, and both readings are wrong. `resolve()` is explicit arg → repo config →
default (`config.py:32-38`), and `critique_plan` already loads that config
(`handlers.py:350`). Route plan closure through `resolve()` and an existing
`class_closure = true` in a project's `.paranoia.toml` — set for branches — turns
plan closure on and hard-errors every plan call that has no `lineage`. Bypass the
config instead and one key silently means different things in two tools.*

**Decision: `class_closure` and `lineage` are call arguments only for
`critique_plan`; `.paranoia.toml` is not read for either.** The branch key keeps
exactly its current meaning and is untouched. No new key is introduced either: a
project-level plan-closure setting cannot work without a per-seam `lineage`, which
is inherently per-call, so a `.paranoia.toml` entry could never be sufficient on
its own. The operator rule that turns this on lives in the consumer's runbook
(§7), where the lineage-naming convention lives too.

### 2.3 A plan-specific register prompt — the parser rejection is the backstop, not the mechanism

*Round 1 [FATAL]: revision 1 proposed rejecting `PATTERN`/`PATHSPEC` in plan mode
and said nothing about the prompt. The only register prompt that exists,
`CLASS_REGISTER_INSTRUCTIONS` (`prompts.py:248-294`), tells the reviewer the server
"re-runs your predicate every future round", presents `PATTERN`+`PATHSPEC` as the
normal record with `PROCEDURE` as the exception, and gives `BLOCKER` as the top
severity. A reviewer obeying its own prompt would therefore have been refused on
**every** class it registered — one wasted retry turn each, and, where
`review.session_ref` is absent or the engine has no `resume`, an immediate
`raise first` into durable register debt (`handlers.py:579-587`). A gate that
refuses the output it asked for is the second failure mode in the stakes,
manufactured by the fix rather than found in the code.*

**Plan mode gets its own terminal-block prompt**, `PLAN_CLASS_REGISTER_INSTRUCTIONS`:

- records are `CLASS` + `SEVERITY` + `PROCEDURE` only — `PATTERN`, `PATHSPEC` and
  `WITH-PATTERN` are not offered;
- severity vocabulary is `FATAL|MAJOR|MINOR|OUT-OF-SCOPE`, matching
  `PLAN_REVIEW_INSTRUCTIONS` (`prompts.py:108`);
- transitions are `CLOSED`, `REOPEN`, `RECLASSIFY`, `SUPERSEDE … BY`, and
  `SUPERSEDE … WITH-PROCEDURE`;
- and it states the closure rule **accurately**: nothing re-runs, and a class
  closes only when a later cold reviewer names its id on a `CLOSED:` line. The
  branch prompt's "the server re-runs your predicate" sentence would be a lie
  here, and a prompt that lies about the mechanism is how a reviewer learns to
  distrust the block.
- **Only open `FATAL`/`MAJOR` classes hold the loop.** *Round 2 [FATAL]: revision
  2 had this prompt say "the loop cannot be reported unblocked until one does" —
  full stop, of every class, having just offered all four severities. That
  contradicts the code, which blocks only on `BLOCKING_SEVERITIES`
  (`class_closure.py:113-115`) and deliberately emits `NOT-BLOCKED` with advisory
  classes open (`class_closure.py:874-876`), and it contradicts §2.5 of this
  document three sections later. A reviewer looking at an open `MINOR` entry would
  be told simultaneously to declare late-round `CONVERGED` and that the loop
  cannot be unblocked — so a valid plan stays stuck while the computed trailer
  says it is clear. The false-refusal failure mode, written into the prompt by the
  fix for the previous false-refusal failure mode.* The sentence must name the two
  blocking severities explicitly, and §7 tests it with an open `MINOR` at round
  ≥3 that must yield prose `CONVERGED` **and** trailer `NOT-BLOCKED` together.

The parser still rejects a mechanized record in plan mode, with `PROCEDURE` named
as the remedy — but as a **backstop for a reviewer that ignored its prompt**, not
as the routine path. Do not silently downgrade a mechanized record to
unmechanized: that would register a class under an invariant statement its author
wrote for a regex.

Cost: one prompt constant and its focused tests.

### 2.4 Accept `FATAL` as a severity — verified defect in the naive port

`SEVERITIES = (BLOCKER, MAJOR, MINOR, OUT_OF_SCOPE)` (`class_closure.py:31`), and
`_severity` rejects anything else. But the plan reviewer's documented vocabulary is
`[FATAL]`/`[MAJOR]`/`[MINOR]`/`[OUT-OF-SCOPE]` (`prompts.py:108`), and the
`round` schema says so too (`server.py:78`). Probed directly:

```
FATAL          -> REJECTED: unknown severity 'FATAL'
BLOCKER        -> accepted
```

A naive port therefore **false-refuses the reviewer's own top severity**: one
wasted retry turn, then durable register debt, then `CONVERGENCE: BLOCKED` with no
class registered at all — a gate refusing a correct review, which is the exact
failure the constraints forbid.

Proposed: add `FATAL` to `SEVERITIES` and to `BLOCKING_SEVERITIES` as a union,
rather than per-mode vocabularies. A plan reviewer writing `BLOCKER` and a branch
reviewer writing `FATAL` are both merely off-rubric; both mean "blocks"; per-mode
strictness would buy a retry round and no safety. This is a change to shared state
semantics and wants its own focused tests either way.

### 2.5 The round-≥3 severity floor — already shared; nothing to add, one thing to fix

Asked directly, so recorded here: **`critique_plan` already has the branch path's
"withhold below MAJOR after round 3" clause, because it is the same code.**
`_calibration()` is called identically by both handlers (`handlers.py:151-153`,
`handlers.py:356-358`), and `_CALIBRATION` is embedded in both
`CODE_REVIEW_INSTRUCTIONS` (`prompts.py:69`) and `PLAN_REVIEW_INSTRUCTIONS`
(`prompts.py:99`). The clause self-adjusts vocabulary — *"[MAJOR] or higher **for
this review mode**"* — so it reads `[BLOCKER]/[MAJOR]` on a branch and
`[FATAL]/[MAJOR]` on a plan. This proposal adds nothing there.

Two related things it *does* settle:

- **Class severity gating is inherited unchanged.** `BLOCKING_SEVERITIES`
  (`class_closure.py:35`), plus `FATAL` per §2.4. A plan class registered `MINOR`
  or `OUT-OF-SCOPE` is tracked and advisory and can never block — §2.9's anti-trap
  rule applies verbatim, and it is what keeps a nine-round plan seam from being
  held open by a marginal finding.
- **The floor *exemption* is the gap, and it is the sharp end of §4.**
  `_CALIBRATION` (`prompts.py:36`) exempts from the floor only "a recurrence of a
  class listed in an `=== UNCLOSED CLASSES ===` block", and that block carries
  mechanized classes only (`class_closure.py:758`). With every plan class
  unmechanized by §1.1 the block is permanently empty, so (i) a reviewer that
  judges a *new instance* of an open MAJOR class to be individually MINOR withholds
  it at round ≥3, leaving the class open with no visibility into where it recurred;
  and (ii) the same sentence is the one forbidding `CONVERGED`, so the reviewer is
  *permitted* to declare convergence with open FATAL classes. The trailer voids it
  (§1.3), but that costs a round — which is precisely the round-4-`CONVERGED`-then-
  2-FATAL shape of §0.1. Fixing §4 is therefore not a tidy-up; it is what makes the
  floor behave on plans the way it already behaves on branches.

### 2.6 Log what a plan seam did

*Round 1 [MAJOR]: revision 1 listed only `already_raised`, `round` and the plan
identity, and would have produced an audit record that could not answer "what
changed in durable state?". The branch path already records `lineage` and
`retry_register`, the latter precisely because "the retry's register is what
actually changed durable state" (`handlers.py:278-287`); without it, a plan round
whose register was accepted on retry logs the **rejected** original and not the
applied replacement. `plan_path` alone is also not an identity: the file is edited
between rounds, so the record names a path whose bytes are already gone.*

Into `_log` for `critique_plan`: `already_raised`, `round`, `class_closure`, the
resolved `lineage`, the register status, `retry_register`, and a **content digest
of the plan for both input forms** — `plan_text` and `plan_path` alike. The digest
is audit only and is never a lineage key (§1.4). For `critique_branch`:
`already_raised` and `round`, which it does not record today either.

Independent of everything else here, and worth landing first — it is the
measurement §1.2 says the *next* version of that decision needs.

---

## 3. What I propose NOT to build

- **Any predicate over plan text or over the repo for a plan class** — §1.1.
- **`exempt` / `unexempt` for plans.** An exemption's identity is
  `(class_id, path, line, text-fingerprint)` of a *grep match*
  (`class_closure.py:118-133`). With no predicate there is no match, so the
  argument would be uncallable — and `render_exempt` would render nothing.
- **Server-side `already_raised` accumulation** — §1.2.
- **A `converge` packet for plans.** The plan is already supplied in full; there
  is nothing to pre-gather.
- **Any parsing of the five prose sections.** `docs/class_closure_plan.md` §2.2 is
  settled law and this proposal does not reopen it.
- **A separate plan-mode state store.** Reuse `~/.paranoia/lineages/` with its
  latch, quarantine and fail-closed semantics unchanged — but **not** a shared
  lineage; see §2.7, which reverses revision 1 on this point.

### 2.7 Cross-mode lineage merging is forbidden, not merely documented

*Round 1 [MAJOR]: revision 1 called a merged plan/branch lineage "coherent" and
declined to prevent it. It is not coherent — it is undefined. A `TrackedClass`
persists no mode or origin (`class_closure.py:372-381`), and `prepare()` sweeps
**every** non-superseded mechanized class it loads (`class_closure.py:596-612`)
through a grep bound to a repo and a head id (`handlers.py:562-563`). A plan round
that opened a branch lineage would have to either run `git grep` with no reviewed
snapshot, block on whatever that returned, or skip the sweep and carry a branch
class's stale status forward — and the third is a false clearance. "Defer the
coordinator choice to implementation review" does not dispose of a state-semantic
contradiction.*

A lineage records the mode that created it. Opening it in the other mode is
`STATE-UNAVAILABLE`-shaped: refused, with the remedy named — use a mode-qualified
key (§1.4). *Round 3 [FATAL], part 1: revision 3 still said here that "the derived
plan key is additionally namespaced with a literal `plan` component", which §1.4
had just deleted. Every plan key is now explicit and caller-chosen, so the
recorded mode is the **only** thing standing between a plan seam and a branch
seam that share a key — which makes the naming rule below load-bearing rather than
belt-and-braces.*

**No migration is needed and none is proposed.** No plan lineage exists yet, so a
loaded lineage with no recorded mode is a branch lineage by construction.

I considered the cheaper rule — no new persisted field, and refuse in plan mode
only if the loaded lineage holds any mechanized class — and rejected it: it is
asymmetric. It catches plan-opens-branch and misses branch-opens-plan, which is
the direction that quietly imports someone else's blocking classes into an
unrelated implementation review. What this gives up is automatic plan-class
carryover into the branch review of the same work. That was speculative; if it
turns out to be wanted, it is a later, explicit feature with its own review.

---

## 4. A defect this exposes in the shipped branch path

Unmechanized classes are second-class in the *prompt*, not just in the trailer.
Verified by probe (§1.1) and by reading:

- `render_unclosed` (`class_closure.py:758`) filters `if c.mechanized` — an
  unmechanized class **never** appears in `=== UNCLOSED CLASSES ===`.
- `_UNCLOSED_INSTRUCTION` (`class_closure.py:748-754`) is the only place carrying
  (i) "do NOT suppress", (ii) "the ROUND severity floor does not apply", and
  (iii) "where this block and the already-raised block conflict, THIS block
  governs."
- `_CALIBRATION` (`prompts.py:36`) names only `=== UNCLOSED CLASSES ===` when it
  forbids writing `CONVERGED`.
- `render_unmechanized` (`class_closure.py:778-793`) carries none of the three.

**So today, on a branch, a reviewer at round ≥3 facing an open unmechanized MAJOR
class is permitted by the prompt to write `CONVERGED`** — and is simultaneously
told by `already_raised` not to restate it, with no stated precedence. The trailer
catches it (`BLOCKED`, plus the VOID line), so this costs a round rather than
producing a false clearance. On the plan path, where **every** class is
unmechanized by §1.1, that gap would be the entire user experience.

**The fix must be status-sensitive, and revision 1's was not.** *Round 1 [MAJOR]
risk: "extend the rule to `=== UNMECHANIZED CLASSES ===`" would forbid convergence
permanently. `render_unmechanized` lists closed classes deliberately
(`class_closure.py:778-793`) — §2.12 of the shipped brief added that so a later
reviewer has the id it needs to emit `REOPEN` — and `_CALIBRATION` (`prompts.py:36`)
conditions on its named block being **non-empty**. Once every blocker is closed the
block is still non-empty, so `CONVERGED` would be forbidden forever. Revision 1
wrote the false-refusal failure mode into its own repair.*

*Round 3 [FATAL]: revision 3's repair then split the wrong thing. It gave
do-not-suppress, floor exemption and `already_raised` precedence to open blocking
classes only, and put closed entries in a history block that "never gates
anything". Those are two independent properties and revision 3 welded them
together. The shipped design says unmechanized classes are "always shown, **never
floor-suppressed**" (`docs/class_closure_plan.md:621-626`) — closed ones
explicitly included, because a closed class is exactly what `REOPEN` exists for.
Under revision 3's block boundary, a rewritten recurrence of a class closed at
round 3 arrives at round 5 with no floor exemption and no precedence over "do NOT
restate"; if it is therefore not reported, no `REOPEN` is emitted, the class stays
`closed`, and `render_trailer` emits `NOT-BLOCKED` (`class_closure.py:827-875`)
over a live blocking defect. That is failure mode 1 in the stakes, produced by the
fix for failure mode 2.*

**Decompose it correctly. Two properties, two different boundaries:**

- **Suppression-exemption — applies to EVERY unmechanized class, open or closed,
  blocking or advisory.** All of them are shown; none is floor-suppressed; all of
  them take precedence over `already_raised`. This is `docs/class_closure_plan.md`
  §2.10 restated, not a new rule. Closed blocking entries additionally carry an
  explicit instruction: *re-run the procedure; if it is violated again, emit
  `REOPEN: <id>` whatever the round floor says and whatever `already_raised`
  says.* Today's `render_unmechanized` text asks for re-verification but grants no
  exemption, which is the same gap one layer down.
- **The `CONVERGED` prohibition — applies ONLY to currently open blocking
  classes.** That is the narrow condition `_CALIBRATION` must name, and it is what
  keeps the prohibition from becoming permanent once the history block is
  non-empty.

Fix it once, for both modes. That is this repository's own "close the class, not
the instance" applied to itself. Cost: one rendering distinction, two
`_CALIBRATION` sentences instead of one, and their tests — including the
round-≥3 closed-class-recurrence regression at §7.

---

## 5. Does it actually fire? The honest accounting

Per round, computed in Python, reading no prose:

| # | fires | what it computes |
|---|---|---|
| 1 | always | a class registered at round N is rendered into round N+1's input, with its invariant, procedure, id, severity and `first raised round N` |
| 2 | always | `CONVERGENCE: BLOCKED` while any FATAL/MAJOR class lacks an explicit `CLOSED` |
| 3 | always | the reviewer's own `CONVERGED` is declared VOID, in the same response, when 2 holds |
| 4 | always | the round the class was first registered, printed and carried forward — `first raised round 1` — beside `rounds recorded: N` |

*Round 2 [MINOR]: revision 2 called row 4 "the age of an open class", which the
two numbers do not give you. `first_round` is whatever `round` the caller passed
when the class was registered (`class_closure.py:483-491`), while `rounds` counts
closure-enabled settlements (`handlers.py:530`). Turn closure on at review round 5
and the trailer reads "first raised round 5" against "rounds recorded: 1" — two
different units. Their difference is an age only when closure was on from round 1
and `round` was incremented every call, which is the operator's discipline, not a
computation. Row 4 now claims only what is computed: the class carries its
origin-round forward and both numbers are printed, so a split lineage or a
forgotten increment is visible.*

*Round 1 [MAJOR]: revision 1 had a fifth row claiming `CLASS-REGISTER: parsed N`
measures new classes per round and therefore churn. It does not. `_count`
(`handlers.py:660-664`) sums `new_classes` **and** `transitions`, so a round that
closed five classes and a round that minted five are the same number. The claim is
withdrawn rather than repaired: splitting the trailer into new-class and
transition counts is a real improvement, but it is a change to a shipped format
that branch operators read, and it is not load-bearing for anything else here —
so it belongs in its own change, not smuggled in as a plan feature.*

**What does not fire, and must never be claimed:**

- **Nothing detects that a new finding is a recurrence of an open class.** The
  reviewer decides that, prompted by block (1). If it instead registers a second
  class for the same invariant, you get two classes to close — a known residual
  (`docs/class_closure_plan.md` §4.7), unchanged.
- **Nothing forces registration.** §4.1's ceiling applies identically: a reviewer
  that finds a class and does not register it is indistinguishable from one that
  never found it.

**The guarantee is therefore: non-forgetting plus explicit closure — not
detection.** That is a real, mechanical computation, and it is exactly the
guarantee the branch path already ships for unmechanized classes; it is *not* the
git-backed recheck, and the README wording must not let a reader think it is.

**Would it have changed §0.2?** Only if round 1 had registered the class. If it
had: rounds 5, 6 and 7 would each have opened with that class in front of them,
open since round 1, with its procedure; round 4's `CONVERGED` would have carried a
`BLOCKED` trailer and the VOID line; and the operator would have read "one class,
open five rounds" instead of four fresh blockers — which is the difference between
rewriting sections and fixing the invariant.

**Would it have made the seam shorter? Probably not, and possibly one round
longer** — a class needs an explicit `CLOSED` round to retire. What it changes is
the operator's read of the loop, and the impossibility of a silent exit. Anyone
selling this as a round-count reduction is selling the wrong thing.

---

## 6. Residual risks

1. **The §4.1 ceiling, unchanged and now dominant.** On branches a registered
   predicate keeps working even if later reviewers ignore the class. Here
   *everything* downstream of registration is still mechanical, but everything is
   also unmechanized — so a class's continued life depends on reviewers reading the
   injected block. Larger residual here than there. Stated, not solved.
2. **`CLOSED` is a model's word.** Same as the branch path's unmechanized classes;
   more consequential because it is the only closure route.
3. **Cross-vendor closure asymmetry.** In a two-stage seam the second vendor can
   `CLOSED` a class the first vendor registered and it may not fully understand.
   Recorded and visible; not limited.
4. **Blocking-class accumulation over a long seam.** Nine rounds × several classes
   approaches the `MAX_ACTIVE_CLASSES = 100` cap (`class_closure.py:44`). Cap
   behaviour is a `RegisterError` refusing *registration*, i.e. it fails toward
   losing new classes on a busy seam. Untested at plan cadence.
5. **`FATAL` in the shared severity set** (§2.4) changes a constant that branch
   classes also read. Needs its own focused tests; a persisted class with an
   unknown severity must not become unloadable.
6. **An explicit `lineage` is used verbatim as the state filename** and nothing
   namespaces it (`class_closure.py:317-319`, `handlers.py:627-628`). Requiring one
   for every closure-enabled plan (§1.4) moves the whole identity burden onto the
   caller's naming discipline: two seams sharing a key inherit each other's open
   blockers and false-refuse a valid plan. Held by a documentation convention
   (`COMPLEX_DELIVERY_RUNBOOK.md:457-462`, extended to mode-qualified keys by §1.4),
   not a mechanism. The §2.7 mode check catches only the plan/branch confusion, not
   two plan seams colliding. The visible signal is `rounds recorded: N` exceeding
   the seam's own round count; nothing enforces it. Round 3 found that a naming
   convention stated one section away from the rule it has to satisfy is how this
   goes wrong.

---

## 7. Implementation and acceptance

**Order.** *Round 2 [MAJOR]: revision 2 said logging lands "first and
independently", while §2.6 requires that same first increment to log the resolved
lineage, register status and `retry_register` — values only the closure
coordinator produces (`handlers.py:516-541`). The first step would have had to log
null placeholders or implement part of §2.1 out of order.* Split it:

1. **§2.6a — existing inputs only**: `already_raised`, `round`, the plan content
   digest, and the `class_closure` argument as received. Depends on nothing, lands
   first, and is the §1.2 measurement.
2. **§4** — the unmechanized prompt gap and its status-sensitive rendering split. A
   branch-path fix with its own value and no plan dependency.
3. **§2.1–§2.4, §2.7** — the plan coordinator itself.
4. **§2.6b — closure-derived audit fields**: resolved `lineage`, register status,
   `retry_register`. Requires step 3 and lands after it.
5. **The rollout documents** — README and the consumer-side edits below.

**Acceptance**, in the shape of `docs/class_closure_plan.md` §6:

1. **A fixture seam** reproducing §0.2 as a known-positive: a class registered at
   round 1, three subsequent rounds each supplying a rewritten plan in which the
   invariant is still violated in different words, and the trailer naming the same
   `class_id` as `BLOCKED` at every one of them — including the round whose review
   text says `CONVERGED`. *Round 2 [MINOR]: revision 2 claimed this fixture "would
   fail if anyone ever attached a predicate to a plan class". It would not — `sweep`
   skips a `PROCEDURE` class whether or not a grep is passed
   (`class_closure.py:596-601`), so the fixture would pass over a coordinator that
   wrongly built one.* What it proves is persistence across rewording, which is
   §1.1(a)'s claim. The separate never-reaches-`make_grep` contract (§2.1) needs its
   own test: a coordinator injected with a grep that raises on call, driven through
   a full plan round.

2. **The injection assertion, which fixture 1 does not give you.** *Round 1
   [MAJOR] gap: a trailer-only fixture passes against an implementation that never
   puts the class in front of the next reviewer — and `_plan_body`
   (`handlers.py:297-321`) has no class-block parameter today, so "never injects
   it" is the default, not a stretch. The branch suite asserts this separately
   (`tests/test_class_closure_integration.py:133-144`).* Assert on the composed
   prompt: the open class's id, invariant and procedure appear, and the open block
   is rendered **after** `already_raised` — the §2.12 precedence rule. Without it
   `CLOSED`/`REOPEN` are unreachable and the whole mechanism is a trailer that
   blocks forever.

3. **A negative fixture**: `class_closure: true` with no `lineage` errors for
   **both** input forms, and mints no lineage — asserted against the state
   directory, not only the message.

4. **The contracts this proposal changes, each with its own focused test.** *Round
   1 [MAJOR] gap: revision 1 specified two fixtures for nine changed contracts.*
   Plan-mode rejection of `PATTERN` and of `WITH-PATTERN`; the retry path when it
   succeeds; the no-`session_ref` path, which must produce debt and a `BLOCKED`
   trailer rather than an exception; `FATAL` registering, blocking, and being
   `RECLASSIFY`-ed down to `MINOR` into `NOT-BLOCKED`; an open `MINOR` class at
   round ≥3 permitting prose `CONVERGED` **and** trailer `NOT-BLOCKED` together
   (§2.3's second FATAL); `CLOSED` then `REOPEN`; `class_closure` default-off
   writing no state at all; `.paranoia.toml` carrying `class_closure = true` having
   **no** effect on `critique_plan` (§2.2); a failed review leaving the lineage
   byte-identical (the branch rule at `handlers.py:509-515`); both directions of the
   §2.7 cross-mode refusal; and the never-reaches-`make_grep` contract from item 1.

5. **The logging deliverable, with exact assertions.** *Round 2 [MAJOR] gap: the
   matrix omitted every field §2.6 promises, so wrong or absent audit fields would
   have passed acceptance while defeating §1.2's whole purpose.* Assert the written
   JSON record for a plan round: `already_raised`, `round`, plan digest,
   `class_closure`, and — after step 4 of the order above — resolved `lineage`,
   register status and `retry_register`, including the case where the register was
   accepted only on retry and the record must carry the **applied** block, not the
   rejected one.

6. **The two regressions round 3 found, which nothing above would have caught.**
   *Round 3 [MAJOR] gap: item 4's "`CLOSED` then `REOPEN`" and "both directions of
   cross-mode refusal" test scripted transitions and rejection mechanics — neither
   exercises the path where the defect actually appears.*
   - **Closed-class recurrence at round ≥3**, asserted on the *composed prompt*:
     a blocking class closed at round 3, then a round-5 call whose prompt must
     still carry that class, its procedure, and the explicit
     re-verify-and-`REOPEN`-regardless-of-the-floor instruction (§4). The
     regression this guards is a `NOT-BLOCKED` trailer over a live defect.
   - **The plan→branch card lifecycle using the prescribed keys**: a plan seam on
     `…-plan` followed by a branch seam on `…-branch` both succeed, and the same
     key used for both is refused. This is what turns §1.4's naming rule from prose
     into something that fails when it is broken.

7. **The next real plan seam in Parallax**, run with it on. The only honest
   end-to-end test; the fixtures exist so failure is caught before spending it.
   **OUTSTANDING at the time of the implementation commit** — every other item above
   is landed and green, this one is an operator action that has not happened, and the
   implementation review raised it as a gap rather than letting it pass silently.

**Existing suite is green at this baseline:** 490 passed, 22.7s, at `f0e670c`.

### The documentation is part of the rollout, not a follow-up

**This repository's README.** *Round 2 [MAJOR] gap: revision 2 said only that the
README "must not" overclaim.* `README.md:212` titles the feature "**on by
default** for `critique_branch`", `:225` describes a regex "the server then re-runs
every round", and `:251` says "**You do nothing to turn this on.**" All three are
false for plans, in the two directions that matter: a reader would either not know
plan closure exists, or believe a plan class gets git-backed recurrence detection —
the §5 over-claim this proposal exists to prevent. The README section and the
`critique_plan` schema descriptions in `server.py` are deliverables of this change,
not documentation debt after it.

**The consumer's operator rules.** *Round 1 [MAJOR] gap: because closure defaults
off (§2.2), nothing makes a later seam turn it on — and
`COMPLEX_DELIVERY_RUNBOOK.md:889-896` still tells the operator that on
`critique_plan` the stop condition is "the triage half alone, since it has no
trailer".* Shipping without changing that sentence ships a mechanism the documented
procedure tells its only user to ignore. The runbook and `CLAUDE.md` must be
updated in the same rollout to prescribe `class_closure: true`; one explicit
`lineage` held across both vendor stages, named by the **mode-qualified** extension
of the globally-unique convention the runbook already mandates
(`parallax-<issue>-<card>-plan`, against the frozen seam's
`parallax-<issue>-<card>-branch` — `COMPLEX_DELIVERY_RUNBOOK.md:457-462`, §1.4);
and the two-part stop condition — prose convergence **and** `CONVERGENCE:
NOT-BLOCKED`. That is a Parallax-side edit; this proposal's owner raises it, and
does not merge it.

---

## 8. What this does not fix

The §0.1 seam did not run nine rounds because findings were forgotten. It ran nine
rounds because the plan was **rewritten between rounds**, and each rewrite created
real new surface — rounds 5 and 6 returned 14 and 18 in-scope findings against a
document that had already survived four rounds. A class register makes a silent
exit impossible; it does **not** measure that churn (§5 withdraws the claim that
it did), it does not make a plan converge, and no server-side mechanism in this
repository can. That part is upstream of `paranoia-local`.

---

## 9. Review debt — this document was not converged

The plan-review loop was stopped by the operator after round 3, which returned two
FATALs. Rounds 1, 2 and 3 each found real defects, and rounds 2 and 3 each found
that the *previous round's fix* had introduced a new one. A fourth round was not
run, so the fixes folded as revision 4 have **not been reviewed by anyone**.

What that means concretely for an approver:

- The §4 decomposition (suppression-exemption for all unmechanized classes; the
  `CONVERGED` prohibition for open blocking ones only) is a fresh design decision
  with zero adversarial rounds against it. It is the highest-risk unreviewed change
  here, because it is where round 3 found a false clearance.
- The mode-qualified lineage convention (§1.4) is likewise unreviewed, and it is
  the only thing preventing a plan seam and a branch seam from colliding.
- The empirical base (§0) and the four decisions (§1) survived three rounds and
  are the settled part.

The implementation review is not a substitute: it reviews the code against this
document, not this document against the world.
