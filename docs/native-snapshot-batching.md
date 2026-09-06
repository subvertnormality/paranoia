# Native snapshot object reader

## Ownership

git_objects.py owns typed blob requests, bounded grouping, and exact native
cat-file framing and object-digest validation. inert_git.py remains the process
policy owner. inert_tree.py owns inventory, inert rendering, manifests, history,
and cleanup. There is no cache, background process, or new durable state.

A batch targets at most 128 objects and 8 MiB of expected payload. An oversized
object is read completely in its own batch. The native frame and decoded active
batch can coexist; completed batches are released before the next acquisition.
Symlinks, executables, and gitlinks retain their existing inert representations.

Provider prompts, schemas, roles, call topology, class closure, and evidence
requirements are unchanged. Verified-plan repository evidence and arbitration
materialization can benefit; branch checkout, ordinary query, and rebut use
different paths. This is not a claim of general model or convergence acceleration.

## Qualification

The immutable [requalification contract](snapshot-batching-requalification-plan.md)
owns baseline, workload, quality, and release gates. Historical withheld results
remain unchanged and cannot qualify this implementation.

benchmark_review_modes.py owns a shared committed-source guard: the complete
recursive Python module inventory and actual Git blob identities must equal the
named committed tree before freeze, import, and replay. Capturing hashes of dirty
files under an unchanged HEAD is rejected. Entry scripts execute the shared
benchmark_bootstrap.py from source before importing owned harness or production
modules. Standard Python cache controls use a fresh empty cache prefix with writes
disabled, so timestamp-valid stale bytecode cannot override validated source.
The bootstrap is included in frozen harness bindings; its temporary directory is
removed at exit and no existing cache is modified.

benchmark_snapshot_materialization.py freezes five alternating pairs for the
current baseline repository and 100/1,000/3,000-file fixtures. Setup plus cleanup
is timed separately from independent rendering fingerprints. Run timed trials
without concurrent tests or provider work.

benchmark_decision_evidence.py retains the existing review worker, actual-call
ledger, native audit checks, and bijective provider-workspace observations.
For this card use --expected-baseline from the contract and --large-padding 3000.
Its eight dispatches pair both arithmetic contracts on small and large snapshots.
Every baseline and candidate dispatch must qualify. Per-pair wall times and call
counts are reported separately; provider durations are not summed into wall time.
The historical default baseline remains available to callers; fresh manifests use
schema 3. Historical campaigns retain their original frozen harness.

For either benchmark: freeze with --freeze OUTPUT --baseline BASELINE_WORKTREE
--candidate CANDIDATE_WORKTREE, run with --run OUTPUT, and report with
--report OUTPUT. Live reporting must use the same CLI PATH and Git environment
as freeze and execution. Archive each complete report and its default output bytes
immediately, including failures, before any later report invocation. Native audit
copies must preserve exact bytes and hashes. The shared observer retains stdout,
stderr (including successful-call stderr), and structured failure detail separately
with explicit empty files, byte lengths, and SHA-256 values. The text encoding is
UTF-8 with surrogatepass, defined for every Python string; it does not change
historical source/state digest encodings. Qualification validates these files for
every attempt and retains cost accounting when a channel is missing or changed.

Regression coverage includes SHA-1/SHA-256, malformed frames, batch lifetime with
a deliberate retention mutant, unusual paths, pinned ordinary edits, inert modes,
missing promised objects, public-handler workspace use, sibling-call accounting,
dirty-source rejection, and frozen workload binding.

The [initial retained results](snapshot-batching-requalification-results.md) reported passing numeric and live decision gates, but CODE review found incomplete successful-stderr custody and a stale-bytecode admission gap. They remain historical observations and do not qualify delivery. Corrected requalification and CODE convergence are required.
