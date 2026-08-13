# Brief: `arbitrate` — a fifth tool that decides between options

> **Current implementation note (2026-08-10).** This is the historical design record for the
> original repository-only protocol. The current tool additionally performs bounded shared
> external research by default as specified in
> [`arbitration_research_plan.md`](arbitration_research_plan.md). Codex live search and Claude
> `WebSearch` discover candidate URLs; Paranoia Local downloads and extracts the pages with
> Trafilatura; the same sessions bind exact passages with browsing disabled; and both deciders
> receive the identical deterministic packet with live web disabled. Claude `WebFetch` is never
> enabled or trusted in that path. `research: false` explicitly selects the legacy
> repository-only mode. Deciders now read inert raw-tree materializations rather than Git
> worktrees, so repository-controlled Git helpers and executable/symlink semantics are not part
> of evidence presentation. Where this historical brief says otherwise, the current research
> plan and README describe the shipped contract. The shipped handler also gives a parser-rejected
> decider reply one bounded full-reply correction while retaining its completed sibling; the
> eight-turn accounting later in this historical brief is therefore no longer normative.

Status: FINAL for implementation, revision 11. Ten codex adversarial-review rounds
folded — round 1: 1 FATAL, 9 MAJOR, 4 MINOR; round 2: 2 FATAL, 9 MAJOR, 3 MINOR;
round 3: 3 FATAL, 1 MAJOR; round 4: 1 FATAL, 2 MAJOR; round 5: 3 MAJOR; round 6:
3 MAJOR; round 7: 2 MAJOR; round 8: 2 MAJOR; round 9: 1 FATAL, 1 MAJOR; round 10:
2 FATAL, 3 MAJOR. Every finding was accepted; one was fixed in a different
direction than proposed and has survived eight further rounds (§2.11).

**Plan review stops here by operator decision, and honestly: round 10 still
returned FATALs.** They are folded above — revision-aware citations (§2.5), the
separate `DECISIVE-CITATION` field (§3.4, §3.5), `anchor_within` as
point-in-interval (§2.5), and the reflog digest (§3.1) — but the plan is not
converged in the sense the earlier rounds were driving at. The remaining review
budget goes to the implementation, where the same reviewer tests these controls
against real code rather than against prose. One round-2 fix was taken in a
different direction than proposed and has survived eight further rounds (§2.11).

`arbitrate` mechanizes a protocol that already exists and has been probed
empirically: Parallax's `docs/prompts/decision_adjudication.md` §2–§4 (the "⚑A
two-vendor adjudication"). That document's own conclusion was *"no new
decision-maker tool is needed"* — the contract alone was enough.

This brief disagrees, on two grounds. First, ergonomics: ~120 lines of prompt
scaffolding a caller must re-type, re-parse, and re-verdict by hand every time,
and hand-execution is where a governance signal gets laundered into a proceed.
Second, and more substantially, **the hand-run protocol leaves bias vectors open
that only a program can close** — presentation order, option-id ordinality,
provenance disclosure in round 2, evidence-revision drift across a multi-minute
call, and an unreconciled round 2 that resamples instead of reconciling. A human
re-typing a template cannot counterbalance order per vendor, cannot keep two id
spaces disjoint, cannot pin both vendors to one commit, and cannot prove that
round 2 carried any new evidence at all.

**The claim this brief must earn:** the two deciders differ in *judgement and
search path only*; every other difference — framing, ordering, labelling,
repository revision — is eliminated or counterbalanced; and no outcome is
reported as convergence unless it was reached on evidence. Where a control only
*reduces* a vector, this brief says so and names the residual. Two earlier
revisions claimed closure they had not earned (§2.3, §2.5).

---

## 1. What it does

The caller hands over a decision: 2–4 options **each with its own stable id**,
context, stakes, the repo, and the files that bear on it. The server:

1. **Pins the evidence.** One immutable snapshot commit of the working tree,
   materialized as a separate inert tree per decider. Both search the same pinned
   bytes and snapshot-derived bounded history. Ref movement during setup fails;
   later movement is reported without changing the pinned verdict (§3.1).
2. **Cleans** the framing with an Opus agent — strips advocacy, equalizes the
   options, normalizes format. Never touches `stakes`. Never judges the merits.
3. **Attests** the cleaned framing with the *other* vendor, field by field. One
   retry maximum, then fail. The cleaner's vendor never signs off on its own work.
4. **Fans out** to both engines in parallel, each cold, each seeing a
   counterbalanced option order under **decider-local labels drawn from a
   namespace provably disjoint from the caller's**, and neither told any other
   model exists.
5. **Verdicts deterministically** in Python after mapping local labels back to
   the caller's stable ids.
6. On divergence, runs **one** reconciliation round — but **only if it has novel,
   snapshot-resolved evidence to give each decider**; otherwise `UNRESOLVED`
   without a second sample (§2.11).

A better unlisted option ends the run `REFRAME_REQUIRED` — it never adjudicates a
model-authored option (§2.8). Hard cap of two rounds.

---

## 2. The bias model

Eleven vectors can make two deciders agree for a reason other than the truth, or
disagree for a reason other than the evidence.

### 2.1 The caller's own view leaks into the framing — closed

Option 1 gets three sentences and option 3 gets four words; the framing says "the
obvious approach"; the caller's recommendation rides along. §2 of the
adjudication doc: *"Do not include your own recommendation: it anchors both
reviewers onto one answer and correlates their errors, destroying the
independence the mechanism runs on."* Today that is enforced by the caller
remembering it. Closed by the cleaner (§3.2), validated and cross-vendor attested
field by field (§3.3). Raw framing reaches no decider.

### 2.1a Framing bounds are checked before anything is spent

Three of the first four production invocations died after two Opus cleaning attempts
each, on defects visible in the caller's own input: an inter-option length ratio, an
over-long option, an over-long decision (issue #8). The measurements were right and the
diagnostics were excellent — they were simply taken after the spend.

`preflight_framing` now runs them before the cleaner: option statements ≤ 1200 chars,
longest ÷ shortest ≤ 2.0, `decision` ≤ 2500, `context` ≤ 20000. Same measurements, same
message shapes, no agent turn. `context` is bounded far more loosely because it is the
designated home for detail and is not per-option, so its length cannot be a vote
between the options.

The inter-option ratio belongs here rather than only after cleaning because it is
**structural, not stylistic**: "adopt X, with this precedence and this invariant"
carries more mechanism to state than "don't", so any scope decision trips it by
construction and no amount of re-cleaning fixes it. The supported remedy is therefore
a framing idiom, and the error states it: hoist the shared mechanism — including the
full specification of what only one option adopts — into `context`, and leave each
option statement to say only how much of it is adopted and what follows. Both options
then describe scope-of-adoption, and equalize on their own. The field run landed at
~780 vs ~810 chars this way, having failed at 483 vs 1262.

### 2.2 Length and detail asymmetry are a vote — closed

A four-line option beside a six-word option is an argument. The caller's own ratio is
bounded at preflight (§2.1a); what this band adds is what the **cleaner** is answerable
for, which is not the same thing:

- across cleaned options: the ratio may not exceed `max(2.0, the caller's own ratio)` —
  equalized framing coming back skewed is the cleaner introducing a length vote;
- each cleaned option against its own original: `ratio ≤ 2.0`. Growth keeps a ceiling
  because a statement that doubles has gained content from somewhere, and the id-set
  check cannot see added prose inside a preserved id.

Revision 2 specified the second band as "within a ratio bound" with no number, which
two implementations could satisfy differently while passing every stated test.

**There is deliberately no lower bound.** Revisions 2-4 set one at `0.5`, and the first
production run showed it firing on the wrong signal (issue #8): an option whose text was
largely consequence-narration ("Outcome under this option: …") was compressed to 0.09x
and rejected, though its meaning was intact — the cleaner had correctly identified
restatement as compressible, while the option describing *mechanism* survived verbatim.
A character ratio cannot distinguish dropped substance from dropped padding. The
cross-vendor fidelity attestation can, and checks exactly that, per option, by id
(§3.2). The floor was a cheap proxy for a check that already exists in stronger form,
and its only observed effect was to penalise a caller for explaining an option's
outcome. Outside a surviving band → one cleaner retry with the measurement, then fail.

### 2.3 Presentation order tilts both deciders the same way — **reduced**

LLMs favour earlier-listed items. Identical order for both deciders gives *shared*
tilt, and shared tilt is the worst failure for a unanimity test: correlated error
is indistinguishable from agreement.

**Mechanism: reversal.** Decider A sees canonical order, decider B sees it
reversed, so every option's two ranks sum to `N+1`.

**What that actually buys, stated precisely.** Revision 2 called this "exact
counterbalancing"; that assumed positional bias is *linear* in rank. It is not
necessarily. Under a convex response such as `(1, .4, .2, 0)` the endpoint ranks
collect combined weight `1.0` and the middle ranks `0.6`, so options 1 and N keep
a tilt *shared by both deciders* — and a mean-rank unit test cannot see it.

- **N = 2: exact.** Two ranks, each option holds each rank exactly once, so any
  response function is balanced. Prefer binary decisions where the question
  admits one.
- **N = 3–4: reduced, not closed.** Mean rank is equalized; higher moments are
  not. Exact balance would require each vendor to evaluate a full balanced
  permutation set — `2N` decider runs, 8 for N=4. **Declined on cost**, which is
  a real operator constraint here, and recorded as the known residual.

**Which vendor sees which order comes from a recorded seed, not the content.**
Revision 2 derived it from a digest over option ids and statements, so a
punctuation change could flip the assignment — and because the tilt above is not
fully closed, a semantically identical replay could change the verdict for no
better reason. Instead a seed is drawn per run, printed on the trailer
(`ORDER-SEED:`), written to the log, and accepted as an input for exact replay.
Deterministic *given recorded inputs*, which is the property audit needs, and
uncorrelated with vendor across a series of decisions — unlike registry index,
which would hand Codex the caller's order every time (`engines.py:315` lists
codex first).

Test invariant: prompts are **byte-identical after normalizing the options and
citations blocks** — nothing but ordering may differ.

### 2.4 The two id spaces must be provably disjoint — closed

Counterbalancing is defeated if labels are ordinal and canonical: a decider shown
`opt-2 … opt-3 … opt-1` reconstructs the caller's ordering from the numbers.

Revision 2 split the spaces — caller-stable ids for the record, sequential
`opt-N` local ids per decider — and claimed *"caller ids never reach a decider"*.
**That claim was false, and it was the round-2 FATAL.** Nothing removed caller
ids from `decision`, `context`, option statements, hint reasons, or `stakes` —
and `stakes` passes through verbatim by design (§3.2). With the natural caller
ids `opt-1`/`opt-2`, a decider could read `opt-1` in prose meaning the caller's
first option while `opt-1` was its own local label for a different one, emit
`opt-1` intending the prose referent, and be mapped to the other option — a
wrong-but-plausible `CONVERGED`, exactly the failure class this tool exists to
prevent.

**Closed by five deterministic rules:**

1. **Local labels are high-entropy, seed-derived, and different for each
   decider** — `OPTION-<16 hex>` (64 bits), derived deterministically from the
   recorded `ORDER-SEED`, the decider index, and the position. Not a fixed
   vocabulary.

   Revisions 3 and 4 both tried a fixed namespace and both failed, in escalating
   ways. Revision 3 reserved `CHOICE-A…D` against *caller ids* but let the literal
   token appear in prose; revision 4 excluded it from the framing fields too — and
   round 4 showed that is still insufficient, because **deciders search the pinned
   snapshot freely and round 2 carries snapshot source lines**. Repository text can
   contain the tokens; once this feature exists, `arbitration.py` and its tests
   contain them. If evidence labels canonical X "CHOICE-A" and Y "CHOICE-B", the
   reversed decider can favour Y, emit the evidence's `CHOICE-B`, and be mapped to
   X — a valid label, an exact member of its own set, and a silent false
   `CONVERGED`. A vocabulary fixed at design time cannot be kept out of a corpus
   the reviewer is *supposed* to read.

   Seed-derived labels invert the problem: instead of hoping a chosen token is
   absent, the server **verifies** it. Three properties do the work:

   - **Distinctness is checked, not assumed.** All `2N` labels for the run are
     derived jointly and `len(set(labels)) == 2N` is asserted before anything
     else. Domain separation by decider index does not *prove* non-collision —
     revision 4 asserted disjointness without testing it, and an intra-set
     collision would let two options share one accepted token (mapping
     overwrite), while a cross-set collision would defeat the backstop below. On
     any duplicate, advance to the next bounded attempt; on exhaustion, fail.
   - **Verified absence over the scanned domain.** Before prompting, the exact
     label strings are searched for in the final framing (including hint paths),
     the pinned snapshot's **blob contents** (`git grep -F` over the snapshot
     commit) and its **pathnames** (`git ls-tree -r --name-only`), and reachable
     **commit messages** (`git log --all --format=%B`, a conservative superset of
     the bounded snapshot history exposed to deciders). On any hit, the next label
     set is derived from the seed and the scan repeats; after a bounded number of
     attempts the run fails. Deterministic given the seed, so a replay derives the
     same labels.
   - **Disjoint per-decider sets as the backstop.** Because each decider's labels
     are distinct from the other's, a label echoed from the carried evidence or
     the other decider is **not a member of the receiving decider's set**, so rule
     5 rejects it outright — a loud `FAILED` rather than a silent mapping.

   **What the scan covers.** `git grep <commit>` reads blob contents only — not
   pathnames or commit messages — so those channels are scanned separately.
   Deciders receive only the inert snapshot tree and a bounded metadata-only
   history derived from the snapshot; they cannot browse historical blobs or live
   refs. Scanning all current commit messages is therefore conservative. The
   64-bit labels remain an accidental-collision control under the supported stakes,
   not a defense against an active input author choosing a colliding token.
   Snapshot-derived metadata history remains available because this repo's own
   review prompt treats reading relevant history as a duty (`prompts.py:53`).

   Cost: less readable transcripts. The report prints both maps beside each
   transcript, and the operator reads caller-stable ids everywhere else.
2. **Caller ids matching the local label pattern are rejected**, as is the
   reserved value `none` and any id colliding with a trailer field name.
3. **No caller-id token may appear in any decider-visible field** — `decision`,
   `context`, `stakes`, an option statement, or a hint reason. Callers
   cross-reference by content ("unlike the float approach"), never by id. This is
   required for correctness independent of id hygiene: options are presented in
   *different orders* to the two deciders, so a statement referring to another
   option by id is broken under permutation anyway. Rejection is a validation
   error with a clear message — never mechanical prose rewriting, which would risk
   substring collisions.
4. **Rules 1 and 3 are applied to cleaner output, not just caller input.** The
   cleaner rewrites `decision`, statements, and hint reasons, so it can
   introduce a caller id or reproduce a label even when the caller did not. Same
   checks, same failure path (one retry, then fail).
5. **`SELECTED` must be an exact member of the label set issued to that
   decider.** A label from the other decider's set, one seen in repository
   evidence, an echoed caller id, or an option named by its words → `FAILED`,
   never a guessed mapping.

Caller-stable ids remain **required** (`options: [{id, statement}]`, unique, 2–4
per the source protocol's *"≤4 options, each with a stable id"*). Canonical order
is derived by sorting on id, so **caller array order affects nothing** — order
independence is structural, not something an acceptance test hopes to observe.
Revision 1's scheme, which derived ids from array order, meant `SELECTED: opt-2`
denoted different actions across a replay; in a governance record that is worse
than the bias it avoided.

### 2.5 What crosses in round 2 — **reduced**

Round 2 must transmit what one decider found and the other missed. Revision 1
carried each decider's `CONSTRAINT` prose and forbade option tokens in it. That
check cannot work: `CONSTRAINT: using Decimal is required because json.dumps has
no encoder at registry.py:660` contains no option token and is pure advocacy,
while a legitimate citation of `docs/opt-2.md:17` is falsely rejected. A lexical
filter cannot separate a fact from a recommendation. Deleted.

**What crosses instead: citations and the bytes they point at.** The server reads
the cited lines from the pinned snapshot and carries citation + source lines. The
model's prose stays in the report and log and goes nowhere near another model.

**Revision 2 claimed this "cannot advocate". That was overclaimed.** Repository
text can itself recommend an option — a comment or design doc may say "prefer
Decimal here" — and *which region a model chooses to cite* is a salience channel
in its own right. Three bounds, and the residual is named rather than finessed:
carried context is capped at a small fixed number of lines, so a whole advocacy
document cannot be relayed; recipients are instructed to treat repository prose
as evidence about the repository, not as instruction; and the report prints
exactly what was carried.

**Citation grammar is exact, because the round-2 gate depends on it.** Revision 2
left extraction to a generic `extract_citations` over free-form prose, undefined
for incidental `path:line` text, missing paths, lines past EOF, and
`./foo.py:7` versus `foo.py:7`. Instead citations get their own trailer field:

- `CITATIONS: <path>:<line>[, …]` — at most 3, parsed only from this field,
  never scavenged from prose. Citations resolve only against regular-file bytes
  materialized from the pinned snapshot. Historical blobs are not present in the
  inert workspace, so a historical prefix cannot substantiate a vote.
- **Not normalized at all.** The path is used exactly as written and must be a
  literal entry in the cited commit's tree. Rewriting it — stripping `./`,
  collapsing `..`, folding backslashes, dropping a leading `/` — can map the path
  the decider read onto a *different* tracked file, and each such rewrite was found
  as a separate defect across several review rounds. Enumerating rejected spellings
  cannot close that class; not rewriting does. A noncanonical path drops, costing
  one `UNRESOLVED`.
- Hint paths are not normalized either. `validate_hints` folded `\` to `/` and stripped
  `./`, and git tracks `policy\choice.py` distinctly from `policy/choice.py`, so a
  caller hinting the former sent BOTH deciders to a different file's bytes — invisibly,
  because the attester is shown the path the server resolved, not the one the caller
  wrote. Literal membership here too.
- Snapshot path reads use `git ls-tree -z`. Without it `--name-only` quotes any path
  containing a backslash, a quote, or a non-ASCII byte, and `core.quotePath=false` does
  not suppress it — so the membership set held `"policy\\choice.py"` while a citation
  carries the raw name, making every legitimate reference to such a file unresolvable.
  That was a latent break in the closure below rather than a new one.
- The same rule reaches the one boundary where the string is repository data rather
  than model output: a **symlink target containing `..` fails closed**. Interpreting
  it lexically diverges from the worktree as soon as an earlier component is itself
  a symlink — with `alias -> linkdir/../f.py` and `linkdir -> sub/dir` the decider
  reads `sub/f.py` while lexical popping yields root `f.py`, and both are tracked.
  The escape gate keeps its lexical reading, which over-reports rather than misses,
  so a repository with ordinary `../shared/x.py` links is still arbitrable.
- The snapshot is resolved to its **full commit id** before anything else.
- Must resolve in the snapshot (`git cat-file -e`) with `1 ≤ line ≤ EOF`.
  A citation that fails resolution is dropped and the drop is recorded.

**Symlink paths cannot substantiate a vote.** The inert workspace exposes a
symlink as a marker plus its target string, deliberately not as the referent bytes.
A citation naming that symlink would therefore bind different content and line
numbers from those visible at the cited path. It is rejected; the decider must cite
the tracked regular referent path it actually read. Directories, gitlinks, dangling
targets, and historical blobs are likewise non-substantiating.

**A citation anchor is not an evidence region, and §2.11 must reason about
regions.** Revision 3 detected "the same region" by comparing normalized
`(path, line)` tuples while actually *carrying* a multi-line context window —
the round-3 FATAL. `foo.py:100` and `foo.py:101` are distinct anchors whose
carried windows are all but identical, so two deciders citing effectively the
same evidence passed the novelty gate and round 2 ran with nothing new in it,
which is exactly what §2.11 exists to prevent.

Every anchor is therefore expanded to the **interval actually carried** —
`[line − k, line + k]`, clamped to file bounds, with `k` the configured context
cap. Two distinct predicates operate on those intervals, and conflating them is a
defect:

- **`same_region`** — same path, intervals that intersect *at all*, and the
  **overlapping lines identical**. Identity is the content actually transported,
  because that is what round 2 transmits. Two weaker identities were tried and both
  manufactured novelty: `(commit, path)` split a bare citation from a `HEAD@…`
  citation of the same unchanged file (every run wraps `HEAD`, so they are different
  commits), and `(path, blob)` split two revisions differing anywhere *outside* the
  cited window, since a blob is the whole file. In each case both vendors appeared
  to gain evidence and round 2 ran as a fresh sample. Regions therefore carry a
  digest per transported line; the commit is retained as provenance only, and cited
  revisions are canonicalized to full object ids so two spellings cannot split a
  region either.
  Used for the §2.11 novelty gate. Deliberately generous: an overlap counts as
  sameness even when anchors differ, so the gate errs toward `UNRESOLVED` rather
  than toward running an evidence-thin round 2.
- **`anchor_within`** — the anchor *line itself* lies inside a carried interval.
  Used for §3.5 substantiation, and it must be the strict point-in-interval test,
  not intersection. With `k = 3`, a carried novel region `[104, 110]` and a fresh
  citation anchored at line 113 expand to `[110, 116]`, which intersects — so an
  intersection test would accept line 113 as "the carried evidence" although 113
  was never carried, turning an independently discovered line into apparent
  reconciliation.

Per path, a decider's intervals are merged. Novelty and sameness are computed on
intervals, never on anchors.

### 2.6 Provenance disclosure induces deference — closed

The adjudication doc's round-2 template opens *"Two independent reviewers
surfaced DIFFERENT decisive constraints"* and concedes the cost: *"The preamble
discloses that divergence occurred… the no-attribution rule reduces deference
pressure but cannot eliminate it."* A model told another model disagreed is under
social pressure before it reads a line of code.

Closed by disclosing nothing. Round-2 deciders are cold sessions that know
nothing of round 1 unless told, so they are not told: no reviewers, no
divergence, no prior round, no round number. Citations arrive as *code regions
relevant to this decision — verify what they imply for yourself*. The
verification duty survives; the social pressure is deleted. **Stricter than the
protocol it mechanizes**, and only a program assembling the packet can do it.

**Both deciders receive the same digest-ordered union of all distinct round-1
regions.** This corrects two successive mistakes. Revision 1 rotated the citation
list by recipient index, which gave *every* recipient its own vendor's finding
first — the opposite of the intent. Revision 3 then withheld from each decider the
region its own vendor had cited, and that was the round-3 FATAL: **it contradicts
the cold-session premise this very section rests on.** A round-2 decider is a
*fresh* session with no memory of round 1, so "its own" citation is not something
it already knows — withholding it means the final vote is cast without the
decisive evidence that vendor found, it may not re-find it, and an agreement
reached that way would be reported as reconciled convergence when one side had
simply lost its own case.

The union fixes the ordering concern more cleanly than exclusion did: the
citations block is **identical for both deciders**, digest-ordered, so there is no
recipient-relative ordering to bias and nothing to attribute. It also tightens
§2.3's invariant — the two prompts now differ *only* in the options block.

Exclusion survives in exactly one place, the §2.11 gate: what is *carried* is the
union, but whether round 2 runs at all still depends on each decider gaining a
region it did not itself produce. Carrying and gating are different questions, and
revision 3 conflated them.

### 2.7 Knowing the protocol changes the answer — closed

A decider told "you are one of two models and we proceed if you agree" hedges
toward the modal answer or holds out to force escalation. Deciders are never told
that another model exists, that unanimity is the test, what the outcomes are, or
that a second round can follow — only the decision, the options, the stakes, the
file hints, and the reply format.

### 2.8 A model-authored option is a position — closed

Round-1 review, [FATAL]: revision 1 promised "facts, never positions" then
solicited `NEW-OPTION: <an unlisted option that is strictly better>`, inserted
that advocacy into both round-2 prompts, neither re-cleaned nor re-attested it,
and defined no outcome for one surfaced *in* round 2. Both deciders could
converge on one vendor's asymmetrically-worded proposal.

Closed by never adjudicating a model-authored option. `NEW-OPTION` is still
solicited — surfacing a missed option is a genuine product of arbitration and the
reason the feature was asked for — but it is **terminal, not an input**. Any
proposal, at any round, ends the run `REFRAME_REQUIRED` with the text carried
verbatim to the operator. To adjudicate it, the operator assigns it a stable id
and neutral wording and calls again; it then enters through the same cleaning,
attestation, and counterbalancing as every other option. Round 2 therefore fires
on divergence only, exactly as adjudication §3 specifies.

**Accepted residual:** any decider can end a run by emitting arbitrary
`NEW-OPTION` text, since "strictly better" is its judgement alone. Under these
stakes that is a visible, cheap false reframe — one wasted call and an explicit
outcome — not a governance failure, and the alternative (adjudicating the
proposal) is the FATAL above.

### 2.9 The cleaner is the same vendor as one decider — **reduced**

The Opus cleaner and the Fable decider are both Anthropic, and a cleaner cannot
certify its own neutrality. Cross-vendor attestation (§3.3) has the framing
verified by the vendor that did **not** produce it, on a machine-parseable
contract, before any decider sees it.

It does not close the vector, and revision 1 overclaimed that it did. The framing
stays Anthropic-authored and Codex-*accepted*; Python validates the attester's
syntax, not its judgement. A false `FAIL` is cheap and visible; a false `PASS`
preserves shared bias silently. Bounds: the attestation is printed verbatim, so a
false PASS is at least inspectable; **retries are capped at one**, specifically so
the loop cannot hill-climb framing against the attester; `clean: false` removes
the surface entirely, now visibly (§2.10).

### 2.10 Evidence-revision drift, and invisible mode changes — closed

Neither vector appeared in revision 1.

**Revision drift.** A 5–18 minute call over a live repo lets ordinary operator
edits leave the two vendors reading different revisions — divergence caused by
drift, or agreement on a state that no longer exists, with a verdict nobody can
reproduce. This repo already treats mixed-revision evidence as unacceptable and
solves it: `handlers.py:198` materializes an immutable worktree for exactly this
reason, over `orientation.snapshot_tree` / `wrap_commit` / `worktree.worktree_at`.
Closed by one snapshot commit resolved at request time, one inert materialization
per decider, and every citation read against that commit (§3.1). Independent search is
preserved in full; only the bytes are pinned.

**`clean: false` silently restored the anchoring vector.** It removes all
de-biasing by design, but revision 1's trailer had no field for it, so a raw
recommendation-bearing packet returned a `CONVERGED` indistinguishable from an
attested one. Closed by the mandatory `CLEANING:` trailer field (§3.7).

### 2.11 An unreconciled round 2 is a second sample, not a reconciliation — closed

**The round-2 FATAL, and the most dangerous defect either review found.**
Revision 2 permitted a `CONSTRAINT` with no resolvable citation to "carry
nothing", started round-2 deciders cold with no knowledge of round 1 (§2.6, and
correctly so), and still reported final agreement as `CONVERGED`. Round 2 could
therefore be evidence-free — neither constraint resolving to a citation, or both
deciders citing the same region for opposite conclusions — in which case it is two
fresh cold samples of the same prompt, and a chance agreement silently erases an
evidenced round-1 split. That is convergence laundering with no bias vector
involved at all. Round 3 then showed the gate itself was unsound as first
specified, because it compared citation anchors rather than the regions actually
carried (§2.5).

**Closed by one gate, computed on intervals (§2.5): round 2 runs only if every
decider would gain at least one resolved region that does not overlap any region
its own vendor produced in round 1. Otherwise the run returns `UNRESOLVED`
immediately, with both positions and both constraint prose handed to the
operator.** No second sample, no chance agreement.

What is *carried* is the full union, to both deciders (§2.6). What is *gated* is
per-decider gain. Worked cases:

| Round-1 citations | Gate | Outcome |
|---|---|---|
| A cites `r1`, B cites disjoint `r2` | both gain | round 2 runs |
| A and B cite overlapping regions | neither gains | `UNRESOLVED` |
| A cites `r1`, B cites nothing | A gains nothing | `UNRESOLVED` |
| neither resolves a citation | neither gains | `UNRESOLVED` |

The third row is deliberately conservative. B would genuinely gain `r1`, but A's
round-2 vote would be a fresh sample over evidence it already had — a coin flip
that could agree with B by chance and be reported as reconciliation. Requiring
*both* to gain keeps every `CONVERGED` attributable to transmitted evidence.

**Same region, opposite conclusions: `UNRESOLVED` by construction — a deliberate
departure from the round-2 review's proposed fix.** The review proposed
reintroducing bounded, attribution-free claim prose for exactly this case. That
case is genuinely unreconcilable by this mechanism: both deciders already have
the bytes, so carrying bytes transmits nothing, and the asymmetry is
*interpretive*. Carrying the claim would carry a position — the one thing
adjudication §3 forbids and §2.5 was rebuilt to prevent. Two frontier models
reading the same line and drawing opposite conclusions is an operator decision,
not something a second sample should resolve. Failing closed is both more
conservative and simpler than the proposed fix, and it needs no new prose channel.

### Residuals, collected

Named here and in the README rather than dispersed: nonlinear positional tilt for
N ≥ 3 (§2.3); repository prose and citation-region choice as advocacy channels
(§2.5); attestation is a judgement, not a proof (§2.9); Codex's text-only
capability is a bound, not a boundary (§3.2); semantic drift in cleaned framing
is bounded and attested, not proved — `stakes` is exempt from cleaning entirely
(§3.2) because a neutrally-worded but materially altered stakes would shift both
deciders' severity the same direction while passing every check; and **shared file
hints are a shared tilt** — `files` goes to both deciders identically, so a hint
list pointing only at evidence favouring one option biases both the same way.
Order counterbalancing cannot help: selection is the issue, not order. The cleaner
strips argumentative hint reasons, attestation covers the hint list, and deciders
are told hints are non-exhaustive starting points whose relevance they must
establish themselves — but a caller who omits the file that sinks their preferred
option biases the arbitration, and no tool detects an omission.

---

## 3. The protocol

### 3.1 Snapshot first — and what "pinned" does not cover

**Always** `snapshot_tree` + `wrap_commit` over the working tree, even when it is
clean — never a bare `HEAD`. Revision 2 said "`HEAD` (or the dirty tree)" and
gave the schema no way to choose, so an implementation could return unanimous
decisions about stale bytes while the operator meant current uncommitted work.
Current code makes that choice explicitly through `target.is_dirty`
(`handlers.py:202`); `arbitrate` removes the choice instead, at the cost of one
deterministic wrapper commit. Each decider receives a separately materialized,
read-only tree plus a bounded `HISTORY.txt` rendered from that commit. No live
`.git` directory is exposed, and every citation read resolves against the same
pinned objects. `repo_path` is **required**.

**Ref movement is provenance once snapshot setup completes.** The server digests
`git for-each-ref` and `git reflog --all` before the snapshot, immediately after
it, and after the last decider returns. A change during snapshot construction
fails before model spend because it makes the setup boundary ambiguous. Movement
after that boundary renders `REFS-MOVED: yes`, but it does not alter the outcome:
the later commit cannot enter either inert decider view, its metadata history, or
citation resolution. An advance-and-restore cycle remains visible when reflogs are
enabled. `retain_snapshot: true` may safely create the durable ref after the final
digest because it preserves exactly the already-decided snapshot.

**File hints must live inside the snapshot.** Every `files` entry is required to
be a normalized, repo-relative path **present in the snapshot tree**; anything
else is rejected before spending. Two concrete holes this closes: an absolute or
`../` path would point outside the evidence tree, and
`git add -A` excludes *ignored untracked* files (`orientation.py:63-76`), so a
hint naming one would silently reference something the recorded commit does not
contain. Rejection is preferred over force-capturing the ignored file, which would
change what a snapshot means.

**Escaping symlinks are rejected, because tree membership does not bound what a
path resolves to.** Revision 6 claimed membership closed the escape; it does not.
The server validates targets before materialization, then renders accepted
symlinks as inert target text rather than executable filesystem links. This keeps
the validation invariant explicit and prevents either decider from following a
tracked path into mutable bytes outside the snapshot.

Before spending, the server enumerates the snapshot's mode-`120000` entries
(`git ls-tree -r`), reads each target string, and **rejects the run if any target
is absolute or normalizes outside the snapshot root**. Per-link validation is
sufficient for chains: a link to a link is itself an entry, so an escaping hop is
caught wherever it occurs. Rejecting *all* symlinks would be simpler and was
declined — benign in-tree symlinks are common and refusing those repositories
outright is disproportionate. The cost is one `ls-tree` plus a small blob read per
symlink.

### 3.2 The cleaner

**MUST**: strip advocacy and loaded adjectives; remove the caller's own
recommendation and any attribution; equalize detail across options; normalize
tense, voice, altitude; neutralize argumentative hint reasons; reproduce caller
`context` byte-for-byte; echo each option under the caller-stable id the server
gives it.

**MUST NOT**: add, remove, merge, split, or reorder options; change any option's
meaning; add facts not in the input; express or hint at a preference; investigate
the repo; **touch `stakes` or rewrite, reflow, summarize, or omit `context`**.

`stakes` and `context` pass through **verbatim**. Stakes are server-owned read-only
input: the cleaner uses them for calibration but must not return a `STAKES` block.
The parser rejects undeclared output blocks. The cleaner's emitted context is
non-authoritative and the server restores the exact caller bytes before attestation
and voting. `stakes` is the highest-leverage input to
`SELECTED-RISK`, and severity is the one axis that gates — a model silently
reshaping it recalibrates both deciders in the same direction. Advocacy inside
`stakes` is *detected* by the attester and pushed back to the caller to fix.
Advocacy in unchanged context is detected independently and likewise pushed back
to the caller; it is never converted into a request for the cleaner to alter shared data.

**Model defaults are explicit constants, not resolved from the engine.**
`CLEANER_MODEL = "claude-opus-5"`. Revision 2 left `cleaner_model` merely
optional; following this repo's resolution pattern would then fall back to
`ClaudeEngine.default_model`, which is `claude-fable-5` (`engines.py:253`) — a
silent violation of the operator's fixed Opus-stage decision. The attester model
is likewise pinned rather than inherited. Both defaults are tested.

**Machine-checked:** the emitted caller-id set is exactly the input set, 1:1, each
non-empty; §2.2's two bands hold; **§2.4 rule 3 is re-run over the cleaner's
output** — no caller-id token and no issued label may appear in any field the
deciders will see, whether the caller put it there or the cleaner did. Any failure
→ one cleaner retry with the specific measurement, then fail.

**It may refuse** — overlapping or non-exclusive options, or a decision too
underspecified to adjudicate → `INSUFFICIENT: <reason>`, and the server stops.
Failing in one agent-run beats burning six on a malformed question.

**Capability.** Cleaner and attester need no repository access, enforced where the
engine layer can enforce it: a new `text_only` profile gives the Claude engine an
**empty** `--allowedTools` with write tools still denied, and runs either engine
in a fresh empty temp cwd. For Codex, `codex exec` is a read-capable agent under
an OS read-only sandbox and paranoia cannot strip that capability — empty cwd plus
prompt instruction is a bound, not a boundary. Revision 1 claimed "no repo access"
as though enforced for both. The exposure is wasted turns, not corrupted
judgement, because neither role is asked which option is better.

### 3.3 The attestation

Cleaned framing goes to the vendor that did **not** clean it — `text_only`,
`effort: low` — with caller-originals beside cleaned text, **field by field**.
Revision 1 attested per-option fidelity plus one global neutrality verdict, so
`decision` and hint reasons went unchecked for meaning even though the cleaner
rewrites them. Context no longer belongs to the fidelity set because it is not a
cleaner-owned field; its unchanged bytes receive a separate advocacy verdict.

```
FIDELITY: decision PRESERVED|CHANGED; hints PRESERVED|CHANGED; <caller-id> PRESERVED|CHANGED; …
FIDELITY-DETAIL: NONE | {"<field>":{"original":"<exact passage>","cleaned":"<exact passage>","change":"<added|removed|narrowed|widened|altered-qualification>","reason":"<field>: <exact change token>"}, …}
NEUTRALITY: PASS | FAIL <which option the packet favours, and the words that do it>
STAKES-ADVOCACY: NONE | PRESENT <the advocating words>
CONTEXT-ADVOCACY: NONE | PRESENT <the advocating words>
```

The attestation must contain **only** its five verdict lines, each once: a
contradicting sentence beside `NEUTRALITY: PASS` would otherwise be ignored and the
packet stamped `attested`. Verdicts are matched **exactly**: `PASS` and `NONE` must be the whole value, and
`FAIL`/`PRESENT` must carry a note. `FIDELITY-DETAIL` must be `NONE` exactly when
every field is preserved. Otherwise it is one JSON object whose keys exactly equal
the changed fields. Every value must contain non-empty `original`, `cleaned`, `change`,
and `reason` strings; `change` is a closed semantic-delta enum and `reason` must equal
`<field>: <change>`. The enum plus exact before/after passages is the mechanically
enforceable semantic explanation; no free-text heuristic gates it. Both passages are mechanically checked as exact substrings of that
field's actual pair, and identical passages cannot demonstrate a change. A prefix match accepted
`NEUTRALITY: PASS but the wording favors option A` as a clean bill of health and
stamped a biased packet `attested` — sending that same bias to both deciders.

Any well-formed `CHANGED` or `FAIL` → one cleaner retry with the attester's exact complaint;
a second failure ends the run `FAILED` with complaint and packet returned.
`STAKES-ADVOCACY: PRESENT` fails immediately to the caller — `stakes` is not the
cleaner's to fix. `CONTEXT-ADVOCACY: PRESENT` does the same for the unchanged
context. The attester is never asked which option is better; its prompt
says it is a text auditor.

### 3.4 The deciders

Both receive the attested packet — identical but for option order and local
labels (§2.3, §2.4) — plus the file hints, and each searches its own inert
materialization of the pinned snapshot: **shared revision, independent search**.

The search asymmetry is deliberate and the one real measurement supports it. The
P12 probe (adjudication §5) found round-1 divergence came *not* from disagreement
but from **each vendor having found a different real constraint** — one the repo
convention, the other `dataset_registry.py:660` calling `json.dumps` with no
`Decimal` encoder. A frozen identical evidence packet would have suppressed the
discovery that made the mechanism work. **Identity belongs in the framing and the
revision, where drift is noise; not in the search path, where asymmetry is the
product.**

Ten verbatim trailing lines. The original adjudication established that both
engines honour a trailing-format contract; the shipped grammar extends it with
three cold source judgements so a captured source cannot govern merely because a
decider named its packet id.

```
SELECTED: <one of the OPTION-xxxxxxxx labels issued to you above, verbatim>
SELECTED-RISK: NONE | [MINOR] <one line> | [MAJOR] <one line> | [FATAL] <one line>
AUTHORITY: technical | human-owner
NEW-OPTION: NONE | <one-line description of an unlisted option that is strictly better>
CONSTRAINT: <one decisive fact about the system, in prose>
PUBLISHER-AUTHORITY: YES | NO — <reason>
PASSAGE-ENTAILMENT: YES | NO — <reason>
DECISION-RELEVANCE: YES | NO — <reason>
DECISIVE-CITATION: NONE | <path>:<line> | SOURCE:<packet-id>
CITATIONS: NONE | <path>:<line>[, …]   (max 3, supporting, non-gating)
```

**`DECISIVE-CITATION` is a separate field because substantiation must bind to the
line the vote actually turned on.** With one list of up to three, a round-2 decider
could keep its own prior region as its real reason and merely *append* the other
vendor's novel region — satisfying a "some citation is novel" test while nothing
was reconciled. Only `DECISIVE-CITATION` gates (§3.5); `CITATIONS` is supporting
context, recorded and carried but never sufficient.

`NONE` parses in both fields, but it is not free: a converging vote whose
`DECISIVE-CITATION` does not resolve cannot produce `CONVERGED`.

**The trailer is the closing block of the reply**, exactly these fields, each
appearing once, and none of these field names may appear anywhere earlier in it.
Reading only the closing lines was not enough: an earlier `SELECTED-RISK: [MAJOR] …`
or a first `DECISIVE-CITATION` sat outside the slice and was silently discarded,
dropping a blocking objection or the vote's real reason. A duplicated, early, or
post-block field line therefore fails the reply — cheap and visible, against a
discarded blocker that is neither. Ordinary prose reasoning before the block is
fine; the decider prompt says not to restate the format.

Caller option ids may not be `decision`, `context`, `hints`, or `stakes`: those are
the attestation's own fidelity field names, and an option called `decision` would
emit two `[decision]` sections and let one verdict satisfy both.

**`DECISIVE-CITATION` is all-or-nothing.** Exactly `NONE`, or exactly one citation:
two comma-separated values, or one with trailing commentary, substantiate nothing.
Taking the first of several would let a round-2 decider list the carried novel
region first and its own prior reason second and have an ambiguous vote reported as
reconciled.

`SELECTED-RISK` is each model's own severity tag against **its own pick**, so
after agreement both have independently rated the winner. The blocker gate reads
those tags and nothing else, per §2's rule: *"'Blocking' means the reviewer's own
severity tag, never the agent's paraphrase of its prose."* Python compares
strings; no model adjudicates the adjudication.

`AUTHORITY` is each model's read on whether the decision is a technical judgement
evidence can settle, or one whose *effect* — irreversible or external action, a
compliance disposition, a change to a precommitted threshold or to what the
system's outputs mean — requires a named human owner, however the question was
phrased. It maps 1:1 onto Parallax's `CLASSIFICATION: A|B`.

**`AUTHORITY` is advisory and never gates.** Parsed, reported, logged; absent from
every verdict row; cannot turn a `CONVERGED` into anything else. A deliberate
departure from adjudication §2, which escalates on a single `CLASSIFICATION: B`
whatever the votes: `arbitrate` supplies the signal, the caller supplies the
policy. Non-silence comes from two always-present trailer fields (§3.7), not from
decorating the outcome enum — a suffixed `CONVERGED (ADVISORY: …)` would break
exact-match consumers, a worse failure than the one it fixes.

### 3.5 Verdict

Computed in Python after mapping every `SELECTED` back to caller-stable ids.
Unanimity across all registered engines; currently two.

| Outcome | Condition |
|---|---|
| `CONVERGED` | all deciders selected the same option, no `SELECTED-RISK` is `[MAJOR]`/`[FATAL]`, **and every converging vote is substantiated** (below) |
| `BLOCKED` | same option, but some decider tags it `[MAJOR]`/`[FATAL]` |
| `REFRAME_REQUIRED` | any decider surfaced a `NEW-OPTION`, at any round (§2.8) |
| `UNRESOLVED` | selections differ after round 2; divergence with no novel evidence to reconcile (§2.11); **or agreement that is not substantiated** |
| `FAILED` | preflight, cleaner `INSUFFICIENT`, failed attestation, unparseable trailer, non-member `SELECTED`, ambiguous snapshot setup, or an engine error |

**Substantiation: convergence must be *reached* on evidence, not merely *offered*
it.** Revision 8's headline claim — no convergence except on evidence — was false,
and this was the round-9 FATAL. `CITATIONS: NONE` is a valid trailer value and the
`CONVERGED` test read only selection and risk, so two round-1 deciders could agree
with no resolved citation at all; and in round 2 they could agree while citing
nothing, or citing only regions their own vendor had already produced, after merely
*being shown* novel bytes. §2.11's gate establishes evidence **availability** before
the round; it says nothing about **use** within it.

- **Round 1:** every converging vote's `DECISIVE-CITATION` must resolve.
- **Round 2:** every converging vote's `DECISIVE-CITATION` must resolve, and for a
  vendor **whose selection changed between rounds** its anchor must additionally
  satisfy `anchor_within` (§2.5) a region carried to it *and* novel to its own vendor
  — computed server-side, since the round-2 session is cold and does not know what its
  own vendor cited before.

**Two vendors owe carried grounding: any that moved, and any whose round-1 vote was
unsubstantiated.** The second clause is what makes the first sound — waiving the rule
for a holder rests on that holder already having been substantiated in round 1, and a
vendor that reached round 2 with no resolving decisive citation has no such standing.
Without it, a vote that was never substantiated at all could ride to `CONVERGED` on a
fresh citation that merely resolves, while the other vendor moved onto its supporting
region.

**Why a vendor that moved.** The carried-grounding rule is anti-*capitulation*:
it proves a changed mind was changed by evidence rather than by the bare fact of
disagreement. Capitulation is by definition a change, so a vendor that held its
round-1 selection has nothing to disprove, and its position was already substantiated
on its own resolved citation in round 1.

Requiring it of every vendor produced a false negative on the very first production
run (issue #8). Both vendors agreed; the vendor that flipped grounded correctly on the
region the other had produced — the mechanism working exactly as designed — and the
run still returned `UNRESOLVED`, because the vendor that had been right all along
cited the *producer code* rather than re-citing the artifact it used in round 1. Its
gains set held exactly one region: the other vendor's argument for the option it had
rejected. The rule was demanding it cite the evidence against its own conclusion, and
it penalised the deeper piece of work. This is the expensive failure mode — a correct
convergence discarded silently, recoverable only by hand-verifying citations, and
fatal to an autonomous caller, which simply halts.

Supporting `CITATIONS` never substantiate. Otherwise `UNRESOLVED`. This is faithful to the protocol being mechanized, which
already demands *"the single decisive constraint behind your selection, with a
`file:line` citation"*; a vote that cannot point at anything is not a technical
adjudication.

**Consequence, stated rather than discovered later:** a decision must turn on
pinned evidence. That may be a line in the inert repository snapshot or a governing
server-captured `SOURCE:<packet-id>`. A source reference substantiates only when its
publisher-authority, passage-entailment, and decision-relevance judgements are all
`YES`; repository-authored URLs and unknown packet ids do not qualify. The cost of
missing support is cheap, visible non-convergence.

**Evaluation order**, since several conditions can hold at once: `FAILED` →
`REFRAME_REQUIRED` → selections differ → `BLOCKED` → unsubstantiated → `CONVERGED`.
`REFRAME_REQUIRED` precedes the selection comparison because a run that would have
read `CONVERGED` but surfaced a better unlisted option is not a finished decision.
`BLOCKED` precedes the substantiation check because it carries strictly more signal
— they agree on the option and one of them says it is unsafe — and neither is a
proceed. Every non-`CONVERGED` outcome returns the full positions, constraint prose,
and objections.

### 3.6 Round 2 — divergence with novel evidence only

Gated by §2.11. When it runs, assembled **mechanically**; no model prose crosses:

- the cleaned `DECISION` / `STAKES` block, byte-identical;
- the same option set, re-counterbalanced under the same recorded seed;
- the **same** digest-ordered union of all distinct resolved round-1 regions for
  both deciders (§2.6), each as its citation plus the capped line context the
  server read from the pinned snapshot — provenance undisclosed, no round number.
  The two round-2 prompts therefore differ only in the options block.

The cleaner is invoked **once per arbitration**; round 2 costs zero extra
non-decider runs.

This is where the brief departs from the shape originally sketched, in which the
Opus agent reassembled the options in light of the new reasoning and re-cleaned.
Parallax removed exactly that step and recorded why: *"That one synthesized a
position addressing both objections, which biases toward agreement and terminates
on agreement rather than correctness."*

**Flip tracking is mechanical.** Adjudication §3 asks the operator to track
round-2 flips toward the selection inferable from a carried constraint; the report
and log carry every engine's per-round selection, so the record exists without
anyone remembering to keep it.

### 3.7 Output

Human-readable markdown — caller-stable options, both transcripts with their
label↔caller mapping tables, caller-original beside cleaned for every field, the
attestation verbatim, exactly what round 2 carried, per-round selections — then a
paste-ready record block, then a machine-readable trailer at column 0. **Every
field is a pure token and always present**, so nothing is signalled by absence:

```
ARBITRATION: CONVERGED | BLOCKED | REFRAME_REQUIRED | UNRESOLVED | FAILED
SELECTED: <caller-stable-id> | none
ADVISORY: none | human-owner (flagged by: codex) | human-owner (flagged by: claude) | human-owner (flagged by: both)
AUTHORITY-POLICY: advisory — a Parallax CLASSIFICATION:B would escalate; this tool does not
CLEANING: not reached | cleaning | cleaner-rejected | cleaned-awaiting-attestation | attestation-rejected | attested | attested-after-retry | skipped
SNAPSHOT: <commit-id> | none
REFS-MOVED: no | yes | unavailable
ORDER-SEED: <seed>
AUDIT: <path> | FAILED <reason>
ROUNDS: 0 | 1 | 2
RESEARCH: not reached | running | failed | complete <N> packets | repository-only
RESEARCH-DIGEST: <sha256> | none
```

`AUDIT` exists because `logs.write_log` swallows every failure and returns `None`
(`logs.py:23`), so revision 1 could return `CONVERGED` with no local audit record
at all. The verdict is still returned in-band on a log failure — it is valid — but
never silently unrecorded.

**What `SNAPSHOT` and `ORDER-SEED` do and do not guarantee.** Revision 3 claimed
they make a run "exactly replayable". They do not, and the reason is in this
repo's own snapshot lifecycle: `wrap_commit` creates **no ref**
(`orientation.py:95-103`), and `tests/test_snapshot.py:39-48` exists precisely to
prove the wrapper commit is unreachable — so `git gc` reclaims it and the recorded
commit id cannot later be materialized. The seed replays label assignment and
ordering; it cannot resurrect the evidence.

What *is* durable is what the log holds: the cleaned framing, both full prompts
byte-for-byte, both replies, and the round-2 regions **with the source lines the
server embedded**. Every input the decision was actually made on is therefore
reconstructible from the audit record; what is not reconstructible after `gc` is
the wider corpus each decider was free to search. `SNAPSHOT:` is provenance, not a
replay handle, and the README must say that rather than implying otherwise.

An opt-in `retain_snapshot: true` creates `refs/paranoia/arbitrate/<timestamp>`
for operators who want durable evidence replay. It defaults **off** because
creating a ref in the audited repo contradicts a documented safety property — the
README's "no ref is ever created" — and that promise should not be broken by
default for a replay nobody asked for. When on, it is the one mode that writes a
ref, and it is documented as such along with how to delete it.

The external issue comment adjudication §4 requires stays the caller's duty; the
paste-ready block plus `AUDIT:` is the most the tool can do, and the README says so.

### 3.8 Dispatch, preflight, and time budget

**Dedicated dispatch.** `arbitrate` cannot reuse `_COMMON`: `server.dispatch`
(`server.py:204`) resolves exactly one engine and injects it, so a single
`engine`/`model` override would either degrade arbitration to one vendor, be
silently ignored, or send one vendor's model name to the other CLI. `arbitrate`
omits `engine`, takes both engines explicitly, and resolves per-vendor overrides
separately (`models: {codex?, claude?}`, `cleaner_model`, `order_seed`).

**Preflight.** Both `codex` *and* `claude` on `PATH`, whichever host the server
was installed into — a prerequisite change from today, where `--engine codex` into
Claude Code needs only `codex`. Checked before anything is spent; the missing
binary is named. No degraded single-vendor mode: two rounds against one vendor is
not arbitration, and Parallax's rule is unambiguous — *"never run the driver's own
vendor twice."* Every mode, including `research: false`, also admits both deciders
against the exact supported evidence-isolation CLI profile before snapshotting or
model spend.

**Time budget.** The client's tool timeout bounds the *whole* arbitration, not
each subprocess, so `DEFAULT_TIMEOUT_SEC = 7200` per call is not a budget.
Per-attempt caps are cleaner and attester 420s, discovery 240s, binding 360s,
and deciders 1,800s. Each permitted validation retry uses the same cap. The handler
checks the remaining monotonic whole-run deadline immediately before every model
invocation and refuses an attempt whose complete cap cannot fit. `engines.Engine.run`
already accepts `timeout` and `runner.run_capture` enforces it. Progress is also
not the reassurance revision 1 assumed — notifications require a client progress
token (`server.py:269`) and the Claude engine emits one JSON blob at completion
(`tests/test_progress.py:131`), so the Opus phase is silent by construction. The
server emits its own phase-boundary progress rather than relying on engine
streaming.

---

## 4. Interpretation surfaces

A prompt template is re-typed every time, and every re-typing admits the agent's
own reading. That is what a function removes.

### 4.1 Closed

| Surface | What closes it |
|---|---|
| Framing drift between invocations | The server owns the instructions and the trailer contract. |
| Reading prose to judge agreement | Python compares mapped `SELECTED` against an exact label set. |
| Composing the round-2 packet | Mechanical: repository bytes only, no prose, no provenance (§3.6). |
| A round 2 that reconciles nothing | The per-decider interval gate (§2.11). |
| Agreement reached without using any evidence | Substantiation: every converging vote must resolve a citation, and in round 2 one novel to its own vendor — required of any vendor that changed selection, or whose round-1 vote was itself unsubstantiated (§3.5). |
| A cold round-2 decider losing its own evidence | Both receive the full region union (§2.6). |
| Local labels colliding with framing or repository text | Seed-derived labels, absence verified against framing and snapshot, disjoint per decider so any echo fails membership (§2.4). |
| The caller's view entering the framing | Cleaner + measured bands + field-by-field attestation. |
| Caller typing order affecting the outcome | Canonical order from sorted caller ids (§2.4) — structural. |
| Ids meaning different things across calls | Caller-supplied stable ids are the only ids in the record. |
| A label collision between id spaces | Disjoint namespace + three rejection rules (§2.4). |
| Unstated stakes silently changing severity | `stakes` required, verbatim, screened for advocacy. `stakes: "unstated"` injects one fixed sentence, identical every call. |
| Evidence changing under the deciders | One pinned snapshot, one inert materialization each (§3.1). |
| History drifting past the snapshot | Inert per-decider trees and snapshot-derived bounded history; `REFS-MOVED` records later movement (§3.1). |
| Hints pointing outside the snapshot | Every hint must be a repo-relative path present in the snapshot tree (§3.1). |
| Symlinks resolving outside the snapshot | Mode-`120000` targets enumerated and escaping ones rejected before spending (§3.1). |
| Stale-vs-current evidence ambiguity | Always snapshot the working tree (§3.1). |
| Model-authored options entering adjudication | `REFRAME_REQUIRED` (§2.8). |
| An invisible skipped-cleaning mode | `CLEANING:` trailer field. |
| A missing audit record | `AUDIT:` trailer field. |
| Unrecorded decision inputs | Log holds both prompts byte-for-byte, both replies, and the embedded round-2 evidence; `SNAPSHOT:`/`ORDER-SEED:` are provenance, with `retain_snapshot` for durable evidence (§3.7). |
| Transcribing the result into a record | Server-built paste-ready block from parsed fields only. |
| Ignoring the advisory by accident | `ADVISORY:` and `AUTHORITY-POLICY:` always present with explicit values. |

### 4.2 Residual — irreducible, and named in the README

**(a) Whether to call `arbitrate`, and what the decision *is*.** A tool invoked on
the wrong question, or not invoked on one that needed it, unifies nothing.
`arbitrate` narrows the blast radius of a bad framing but cannot make it right.
Same class: an omitted file hint.

**(b) What the caller does with the verdict.** `AUTHORITY` is advisory by
decision. Always-present trailer fields make ignoring it deliberate; nothing makes
it impossible.

**(c) The bias residuals** collected at the end of §2.

**Considered and declined.** Round 1 proposed making caller-supplied structured
input authoritative and demoting model cleaning to an optional preview requiring
explicit resubmission — cutting typical usage from four agent runs to two and
removing two model-conditioned steps. Declined: the operator specified an Opus
cleaning stage in the loop, and the proportionate answer to "an invisible
transformation inside a verdict-producing call" is to make it *visible* —
originals beside cleaned, attestation verbatim, `CLEANING:` on the trailer —
rather than to remove it. `clean: false` gives exactly the proposed mode to any
caller who wants it, now non-silently.

The claim this tool earns is **"identical framing, counterbalanced presentation,
disjoint labelling, pinned evidence, evidence-gated reconciliation, deterministic
verdict, verbatim record"** — not "no interpretation".

---

## 5. Cost and latency

| Step | Agent runs | Cap |
|---|---|---|
| Clean | 1 | `text_only`, 420s |
| Attest | 1 | `text_only`, `effort: low`, 420s |
| Clean + attest retry, if it fires | 2 | 420s each |
| Shared research (parallel) | 4 typical; up to 8 with validation retries | discovery, capture, same-session binding |
| Round 1 (parallel) | 2 | inert snapshot materialization, `effort: medium`, 1,800s |
| Round 2, gated (parallel) | 2 | 1,800s |
| **Typical** | **8** | cleaner, attester, four research calls, two deciders |
| **Maximum call count** | **20** | four framing, eight research, and eight decider attempts; the whole-run deadline may stop this path before all calls start |

Research and decider calls dominate cost. Wall clock is
`clean + attest + research groups + max(decider) [+ max(decider)]` — vendor lanes fan out in parallel, new
for this repo, whose handlers are all a single `engine.run`. Realistically 5–18
minutes; the 7,200-second whole-call deadline remains the hard stop. With default research,
`clean: false` removes two typical framing calls but still uses four research calls and two
round-one deciders (six typical calls, up to sixteen across all validation retries and round 2);
`REFRAME_REQUIRED` and the §2.11 gate both terminate early. The README's
rate-limit section accounts for bounded research and validation turns across two subscriptions.

---

## 6. Implementation sketch (TDD, pure core / injected edge)

Every decision the protocol makes is pure and unit-tested; only the subprocess is
injected.

- **`arbitration.py`** (new, the pure core): `validate_options` (2–4, unique
  stable ids, §2.4 rules 1–3), `canonical_order` (sort on id),
  `presentation_for` (reversal + seeded vendor assignment + seed-derived
  per-decider labels + mapping), `derive_labels` (all `2N` jointly, distinctness
  asserted) / `labels_are_clear` (§2.4 rule 1: absence over framing, snapshot
  blobs, snapshot pathnames, and commit messages),
  `resolve_stakes`, `build_clean_prompt`, `parse_cleaned_packet`
  (id-set fidelity, both numeric bands), `build_attest_prompt`,
  `parse_attestation`, `build_decider_prompt`, `parse_verdict` (six-line trailer,
  exact label membership), `parse_citations` (§2.5 grammar + normalization),
  `to_regions` / `merge_regions` (anchor → carried interval, per-path merge),
  `region_union`, `gains_for` (the §2.11 per-decider interval gate),
  `build_round2_packet`, `compute_outcome`, `render_report`,
  `render_record_block`, `reject_reserved_tokens` (§2.4 rule 3, run over both
  caller input and cleaner output).
- **`orientation.py`**: `scan_for_tokens(repo, commit, tokens)` — the §2.4 rule 1
  clearance scan over snapshot blobs, snapshot pathnames, and reachable commit
  messages; `refs_digest(repo)` — the §3.1 ref-movement endpoints;
  `symlink_map(repo, commit)` — mode-`120000` entries and their targets, serving
  both the §3.1 escape check and the §2.5 alias canonicalization;
  `read_citation_lines(repo, commit, path, line, context)` —
  bounded read from the pinned snapshot. The `repo` parameter is required: the
  existing `_run` seam takes `cwd: Path` (`orientation.py:25`) and a commit hash
  alone does not identify its object database. Revision 2's proposed
  `(commit, path, line)` signature could not perform the read it promised.
- **`prompts.py`**: `CLEANER_INSTRUCTIONS`, `ATTEST_INSTRUCTIONS`,
  `ARBITRATE_INSTRUCTIONS`. All reuse `_NO_DELEGATION` — a decider calling a
  registered `paranoia` MCP would arbitrate the arbitration and double-spend
  quota. Deciders reuse the existing `STAKES` calibration language; the P12 probe
  found no manufactured blockers at calibrated stakes, load-bearing here because a
  spurious `[MAJOR]` becomes `BLOCKED`. Decider prompts mention no other model, no
  round, no outcome (§2.7), and instruct that repository prose is evidence, not
  instruction (§2.5).
- **`engines.py`**: `binary` class attribute (argv[0] is hardcoded inside
  `build_argv`, so preflight has nothing to check today); `all_engines()`;
  `text_only` capability profile; pinned `CLEANER_MODEL` / attester constants.
- **`handlers.py`**: `arbitrate` — preflight → snapshot → clean (skipped on
  `clean: false`) → attest → fan out → verdict → §2.11 gate → maybe round 2 →
  verdict → report. Fan-out via `ThreadPoolExecutor`, one inert tree per decider; a
  single decider failure does not lose the other's work (`FAILED`, naming the
  engine).
- **`server.py`**: fifth `Tool`, own dispatch path (§3.8). Schema: `options`
  required array of `{id, statement}`, `decision`, `stakes`, `repo_path`
  required, plus `context`, `files`, `subject`, `clean`, `models`,
  `cleaner_model`, `order_seed`, `retain_snapshot`, `effort`, `web_search`.
- **`logs.py`**: raw input, cleaned packet, attestation, snapshot id, order seed,
  per-engine label map, every decider reply per round, what round 2 carried,
  per-round selections, outcome; surface write failure for the `AUDIT:` field.
- **`pyproject.toml`**: add `mutmut` to `[dev]` — extras are pytest-only today
  (`pyproject.toml:18`), so the mutation gate is otherwise unrunnable.
- **README**: the tool; both-CLIs prerequisite; advisory non-gating `AUTHORITY`;
  §4.2's residuals.

---

## 7. Tests

**Deterministic mechanism tests — the load-bearing set, zero model variance.**

*Ordering and labelling.* Reversal gives every option mean rank `(N+1)/2` for
2 ≤ N ≤ 4, and for N=2 each option holds each rank exactly once; vendor-to-order
assignment is a pure function of the recorded seed and is neither the registry
order nor derived from packet content, and replaying a recorded seed reproduces
the assignment; labels are seed-derived, carry no ordinal information, and are
**disjoint between the two deciders**; the same seed derives the same labels;
mapping is correct **including the case where each decider's first-position label
denotes a different option** — the test that catches a mapping inversion silently
reporting convergence; canonical order is invariant under caller array reordering
and caller ids appear unchanged in the record.

*Label isolation (§2.4 rules 1–5).* Caller ids matching the label pattern, the
reserved `none`, or a trailer field name are rejected; a caller-id token in
`decision`, `context`, `stakes`, any option statement, or any hint reason is
rejected — asserted field by field, on caller input **and again on cleaner
output**. Both label-collision attacks are regression tests in full:

- **Derivation collision** (round-5 MAJOR): with derivation stubbed to return a
  duplicate, `len(set(labels)) == 2N` fails, the attempt advances, and exhaustion
  fails the run — asserted for both an intra-set and a cross-set duplicate, since
  the two have different consequences (mapping overwrite vs a defeated backstop).
- **Framing collision** (round-3 FATAL): a derived label present in the framing,
  including in a hint path, is detected and the next set derived; exhausting the
  bounded attempts fails the run.
- **Snapshot collision** (round-4 FATAL): a derived label planted in a **tracked
  file's contents**, in an **untracked file** (`git add -A` puts these in the
  snapshot — `orientation.py:66-76`, `tests/test_snapshot.py:52-57`), in a
  **pathname**, and in a **commit message** is detected by the corresponding scan
  and the next set derived. The run must never prompt with a label present in any
  scanned domain.
- **Unscanned domain is asserted as such** (round-5 MAJOR): a label planted only
  in a prior revision's blob contents is *not* detected — the test pins the
  documented residual so a future reader does not mistake the scan for total.
- **Cross-decider echo**: a `SELECTED` naming a label from the *other* decider's
  set yields `FAILED`, never a mapping — the structural backstop for any leak the
  scans miss.

A `SELECTED` that echoes a caller id, names an option by its words, or gives a
well-formed but unissued label likewise yields `FAILED`.

*Round-2 transport and gate.* Packets carry citations plus snapshot-read lines
only — no model prose, selection, preference, attribution, provenance, or round
number; **both deciders receive the identical digest-ordered union of all distinct
round-1 regions**, so the two round-2 prompts differ only in the options block and
no decider is denied the region its own vendor cited; citation parsing takes the
`CITATIONS:` field only and ignores `path:line` text inside `CONSTRAINT` prose;
`./foo.py:7` and `foo.py:7` normalize identically; a path absent from the
snapshot, a line past EOF, and more than three citations are each handled as
specified and recorded; carried context is capped.

*Alias canonicalization (§2.5).* With `alias.py → real.py` in the snapshot: a
citation of `alias.py:1` carries `real.py`'s **contents**, never the target string
`git show` would return; `real.py:1` and `alias.py:1` collapse to **one** region,
so the novelty gate sees no gain and returns `UNRESOLVED` instead of running an
evidence-free round 2; two different aliases for the same referent likewise
collapse; a citation resolving to a directory, a gitlink, or a dangling target is
dropped and recorded.

*The §2.11 gate, on intervals not anchors.* Every row of the gate table is a test:
disjoint regions run round 2; overlapping regions, one-sided gain, and
no-resolved-citations each yield `UNRESOLVED` without a second decider call.
**Adjacent anchors whose carried windows overlap — `foo.py:100` and `foo.py:101`
at any context cap ≥ 1 — count as the same region and do not run round 2**; that
is the round-3 FATAL as a regression test. Interval merging is asserted per path,
including touching-but-not-overlapping windows and clamping at file bounds.

*Framing.* Cleaned options outside either numeric band retry once then fail; a
`CHANGED` on `decision`/`hints`/any option, a `FAIL` neutrality,
`STAKES-ADVOCACY: PRESENT`, and `CONTEXT-ADVOCACY: PRESENT` each take their specified
path; the attester is always the non-cleaning vendor; `stakes` and `context` reach the deciders byte-identical to the
caller's input; the cleaner model default is `claude-opus-5` and is *not*
inherited from `ClaudeEngine.default_model`.

*Substantiation (§3.5).* Round-1 agreement with `DECISIVE-CITATION: NONE` from
either decider yields `UNRESOLVED`; round-2 agreement where a MOVING vote's
decisive anchor is its own prior region — even with the other vendor's novel region
appended to supporting `CITATIONS` — yields `UNRESOLVED`, since only the decisive
field gates; a vendor that HELD a round-1 selection which was itself substantiated
needs only a decisive citation that resolves, while one that held an unsubstantiated
round-1 selection must ground in gained evidence like a mover; round-2 agreement where each decisive anchor lies within a carried
region novel to its own vendor yields `CONVERGED`; a decisive anchor that merely
*abuts* a carried interval (anchor 113 against carried `[104,110]` at `k=3`) does
**not** substantiate, because `anchor_within` is point-in-interval and not
intersection; a citation that parses but fails to resolve does not substantiate.

*Snapshot-visible citations (§2.5).* A bare `path:line` resolves in the materialized
snapshot. Historical commit prefixes and symlink paths are dropped because their
referent bytes were not exposed to the decider. The full evaluation order is asserted, including a case
where `BLOCKED` and unsubstantiated both hold and `BLOCKED` wins, and one where
`REFRAME_REQUIRED` and unsubstantiated agreement both hold.

*Verdict.* Every table row, including `BLOCKED` from a single `[MAJOR]` on an
otherwise unanimous pick; `REFRAME_REQUIRED` at round 1 *or* round 2, evaluated
before the selection comparison, including when selections agreed; `human-owner`
changes no outcome but appears on `ADVISORY:`, including on `UNRESOLVED`; selection
disagreement is represented by `ARBITRATION: UNRESOLVED`, not an advisory token;
`ARBITRATION:` is always a bare enum token; every trailer
field is always present; unparseable or missing trailer → `FAILED`; hard stop at
two rounds.

*Input discipline.* Missing or duplicate ids rejected; <2 or >4 options rejected;
free-text `options` rejected; missing `stakes` or `repo_path` rejected;
`stakes: "unstated"` renders one byte-identical sentence across calls;
`clean: false` invokes neither cleaner nor attester, passes statements verbatim,
and reports `CLEANING: skipped`; the record block contains no model-authored prose.

**Process.** Both deciders run against the same snapshot commit, and a live-repo
edit mid-run changes neither inert materialization; the snapshot is taken from the working tree
even when clean.

*Pinning limits (§3.1).* A **branch advanced mid-run** changes the digest, so the
trailer reports `REFS-MOVED: yes` while a valid decision over the inert snapshot
remains valid. An **advance-and-restore** cycle, which leaves the ref-tip digest
identical, is caught by the reflog digest when reflogs are enabled. A hint path that is
**absolute**, escapes the repo via `../`, or names an **ignored untracked file**
(absent from the snapshot because `git add -A` skips it — distinct from the
ordinary-untracked and tracked-but-ignored cases already covered at
`tests/test_snapshot.py:52-68`) is rejected before any spend. A snapshot
containing a **tracked symlink whose target is absolute or escapes the root** is
rejected before any spend — the case `docs/orientation_reuse_plan.md:77` documents
— while a snapshot containing only in-tree symlinks proceeds; a two-hop chain
whose second hop escapes is also rejected.

*Audit.* The log alone reconstructs both prompts, both replies, and the carried
evidence without needing the snapshot commit to still exist;
`retain_snapshot: true` creates the ref and the default creates none; `read_citation_lines` works from both a primary checkout and a
linked worktree (this repo is used from a linked worktree); per-phase timeouts fit
under 7,200s; a `logs.write_log` failure yields `AUDIT: FAILED …` and still returns
the verdict; preflight fails when either binary is absent and spends nothing; a
single decider failure names its engine. Integration against the existing fake
CLIs on `PATH`: both engines invoked once per round, in parallel; no evidence
materialization or worktree registration leaked (`git worktree list` clean).

Mutation pass on `presentation_for`, `canonical_order`, `derive_labels`,
`parse_verdict`, `parse_citations`, `merge_regions`, `gains_for`,
`reject_reserved_tokens`, and `compute_outcome` — they are the whole protocol.

---

## 8. Acceptance

Full suite green; §7 tests; mutation pass on the six pure functions above.

**Gates are split by what they can actually establish.** Revision 1 used one
stochastic live replay as a correctness gate and one reversed-order pair as proof
of order independence, either of which a correct mechanism can fail and a biased
one pass by chance.

1. **Mechanism (binary, deterministic).** All §7 mechanism tests green against
   recorded/fake engine transcripts. This is what establishes correctness. Order
   independence sits here and is structural: canonical order derives from sorted
   caller ids, so caller array order cannot reach any prompt.
2. **Live smoke (non-binary, recorded not gated).** Replay the P12 probe decision
   (adjudication §5) end to end against real engines. Criteria: the pipeline
   completes, both trailers parse, the record block is well-formed, the snapshot
   and seed are recorded, and the outcome plus both constraints are captured. The
   historical hand-run result (diverge, reconcile, converge on `opt-1`) is
   recorded for comparison and **is not a pass condition** — n=1 against
   stochastic engines, as adjudication §5 concedes about its own probe.
3. **Bias observation (recorded, not gated).** Over a small set of decisions,
   record per-vendor first-choice rates by presentation rank. Given §2.3's
   surviving nonlinear residual this is the only instrument that would show it;
   with n this small it is a signal to revisit, never a release gate.
