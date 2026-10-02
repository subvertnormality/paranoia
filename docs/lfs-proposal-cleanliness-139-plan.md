# Issue 139: filter-free Git LFS proposal cleanliness

The beta's raw-byte cleanliness check rejects a clean smudged Git LFS checkout:
Git stores a small pointer while the caller has its verified object bytes. Fix this
without running repository-selected clean/process filters or changing review authority.

Frozen deployment: the existing single-user local MCP server; operator, OS, Git and
provider executables trusted. Repository bytes and proposals are untrusted static data.
Existing three census lanes may run concurrently; ordinary caller edits must block or
invalidate suitability. No hostile local race, compromised OS, corrupted-state recovery,
multi-tenancy or formal proof. No added network boundary, LFS fetch or model call.
Expect tens to low hundreds of findings, bounded rounds and feedback within minutes.
Wrong preimage binding/clearance is high impact; recoverable proposal refusal acceptable.

Keep HEAD/index equality, untracked checks, filesystem kinds, executable modes,
real-directory ancestors, sparse checkout and recursive submodule semantics unchanged.
Regular files first retain exact Git blob identity; stream checkout bytes in bounded
chunks instead of loading whole LFS objects into memory. A differing regular file is
clean only if its pinned Git blob is a canonical extension-free v1 LFS pointer under
1024 bytes, its cached Git filter attribute is exactly lfs, and the complete caller
bytes match BOTH the pointer's decimal size and lowercase SHA-256. Read attributes
through inert Git plumbing, never git status/diff or a filter. Raw pointer checkouts
remain clean by exact blob identity. Other pointer versions, extensions and malformed
pointers remain unsupported and fail closed; do not infer arbitrary filter equivalence.

Apply the same helper before proposal dispatch and after response, including recursive
submodules. Before dispatch, read/attribute/object failures retain supplemental
UNAVAILABLE with zero proposal calls and the original review trailer. After response,
verification failures or changes report STALE while retaining the candidate and trailer.
Do not make smudged content a patch source: proposed edits still bind exact committed
blob bytes, and suitability still checks every edited file against its exact preimage.
An unrelated LFS object must no longer prevent a proposal for an ordinary source file.

Acceptance through tests/test_lfs_proposal_cleanliness.py: real Git LFS clean status
and stored pointer versus expanded object; raw pointer; altered same-size bytes,
wrong size, malformed/unsupported pointers, missing filter attribute, staged changes,
untracked files, modes, sparse files and initialized submodule LFS; sentinel clean and
process commands must never execute. Public critique_branch must return an unrelated
PROPOSED/CURRENT patch for clean LFS, spend zero proposal calls for dirty LFS, and return
STALE when LFS changes during continuation while preserving the original trailer.
Exercise both operational-failure phases through critique_branch, asserting zero
proposal calls for admission failures and retained candidate plus STALE after response;
both must preserve the original trailer. Exercise edited-LFS exact-preimage suitability.
Run focused proposal regressions and native PLAN then CODE convergence on beta;
once implementation starts, do not reopen PLAN. Run a native public-handler proposal
in a real LFS fixture, retain actual output/audit, and record results honestly.

Update README's planned-status notice and docs/how-it-works.md on delivery with
the supported LFS exception and unchanged exact-preimage requirement, referencing
this contract without duplicating parser rules.
This is a bounded correctness fix; no claim of beta cost savings or unchanged quality.
The existing full beta both-provider qualification gate remains unfulfilled.
