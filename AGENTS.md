# Repository agent instructions

These rules govern planning, implementation, and adversarial convergence work in this
repository. They supplement the user request; they do not broaden it.

## Treat stakes as a specification

Before starting a review loop, write one stable stakes statement. It must be concrete
enough to decide whether a proposed failure is in scope. Cover every relevant dimension:

- deployment and operators: local CLI/MCP, service, CI, single user, or multi-tenant;
- trusted actors: operator, OS, other local processes, repository owner, callers;
- untrusted inputs: plan text, repository bytes, Git configuration, supplied artifacts,
  fetched content, persisted state;
- active adversaries: state explicitly whether an attacker can execute code or mutate the
  repository, its parent directories, process environment, network, or state directory
  while a review is running;
- concurrency and mutation: distinguish ordinary edits from adversarial race attempts;
- network boundary: configured endpoints, redirects, DNS, proxies, and credential access;
- scale and budgets: approximate files, bytes, claims, users, rounds, and acceptable latency;
- consequences: what a false `NOT-BLOCKED`, false block, data disclosure, state loss, or
  availability failure actually costs;
- exclusions: name plausible but unsupported threat capabilities that are not being built
  for.

Do not use vague stakes such as "malicious repository", "production", "high stakes", or
"security-sensitive" without defining attacker capabilities. In particular, distinguish:

1. static malicious repository content or configuration;
2. repository-selected code execution;
3. an active local process racing filesystem operations;
4. a compromised OS or filesystem;
5. malicious network content or an active network attacker;
6. corrupted state caused by a crash versus state deliberately tampered with by an attacker.

A proportionate local-tool statement looks like this:

> Single-user local MCP operated by a trusted user on a trusted OS. Plan bytes, repository
> content and Git configuration, supplied artifacts, and fetched pages are untrusted data.
> No hostile local process can mutate the repository or its ancestors during a round;
> ordinary user edits may occur and must produce an explicit retry/block, not a false clear.
> Native search uses only the selected signed-in reviewer CLI; the server retrieves candidate
> pages over public HTTPS without sending page-bound credentials. Expected scale is about
> 1,000 files, tens of claims, eight search/fetch attempts, and an eight-minute hard round
> limit. A false `NOT-BLOCKED` is high impact; a recoverable blocked round is acceptable.

If hostile concurrent mutation is intended, say so separately and name the writable paths:

> Another untrusted local process may rename or replace the repository and its parent-path
> components during snapshot construction; namespace TOCTOU attacks are in scope.

Freeze the stakes for a convergence lineage. Do not silently strengthen them in response to
a finding. A material stakes change requires an explicit user/design decision, updated
acceptance criteria, and retriage of every open class.

Documentation must describe the approved threat model. Do not turn an incidental hardening
patch into a new public security guarantee. Conversely, do not dismiss a finding as out of
scope when the public documentation already promises the affected behaviour; first decide
whether to keep the guarantee or narrow the documentation.

## Classes are architectural hypotheses, not a patch queue

An open or reopened class proposes an invariant. It is not automatic authorization to edit
code. Before implementing any class-driven change, triage the class against the frozen
stakes and record:

- the concrete failure scenario and required actor capabilities;
- evidence that the scenario is reachable in the current implementation;
- whether the invariant is required by the user request, public contract, or accepted design;
- the root architectural responsibility and every related open class;
- one disposition: `ACCEPT`, `NARROW/SUPERSEDE`, `ADVISORY/OUT-OF-SCOPE`, or `REJECT`;
- the smallest coherent remedy and its expected code, latency, compatibility, and test cost.

Review all open and reopened classes as a set. Look for a shared design error before fixing
individual manifestations. Use the class register's supported closure, narrowing, or
supersession mechanism when a class is too broad; do not write code merely to make the
register green.

The following events require an architecture checkpoint before further production edits:

- a class recurs after its proposed fix;
- a round at or above the severity floor opens a new architectural class;
- two consecutive review/fix cycles do not reduce the in-scope blocking-class set;
- a fix introduces a new subsystem, trust boundary, persistence protocol, or public guarantee;
- the implementation materially exceeds the approved plan's component or performance budget.

At the checkpoint, stop the patch loop. Re-read the original request, restate the intended
operating model, group findings by root cause, and choose among refactoring, narrowing the
contract, staged rollout, or a documented no-go. Obtain user direction when that choice
materially changes scope or guarantees.

## Control architectural growth

Use this priority order when performance, simplicity, and hardening compete:

1. accurate domain behaviour and verdicts;
2. reliable operation and recoverable ordinary failures;
3. bounded runtime, resource use, and maintainable architecture;
4. security against the actors and inputs explicitly included in the stakes;
5. hardening against excluded actors or hypothetical environments.

Never improve speed by allowing a false `NOT-BLOCKED`, dropping a load-bearing claim,
reusing invalid evidence, weakening source/claim binding, or accepting malformed durable
state. Conversely, do not retain expensive isolation, copying, durability, or race-defense
machinery solely for an actor the frozen stakes exclude. Prefer a simpler mechanism when it
preserves the same in-scope functional invariant.

Before the first implementation and after every architecture checkpoint, record a compact
change budget using `git diff --stat` plus relevant runtime measurements. Track:

- production lines and files changed;
- new modules and durable schemas;
- largest orchestration/state-machine components;
- duplicated infrastructure or policy;
- snapshot/review latency, model calls, network calls, and persisted-state growth;
- rollout mode and rollback path.

Passing tests does not by itself justify added architecture. Refactor or reduce scope when
one orchestration function owns several phases, one module combines schema validation,
state transitions, I/O and rendering, or a security adapter duplicates a general repository
abstraction. Prefer stable seams with explicit inputs and outcomes over more conditional
branches in a central handler.

Do not make a safety gate default-blocking before the approved rollout reaches that stage.
When the plan calls for shadow or diagnostic operation, preserve that stage and collect its
completion evidence before changing defaults.

## Review and delivery discipline

- Use tests to reproduce accepted in-scope failures before changing production code.
- Prove the primary user capability end to end before starting adversarial convergence. A
  placeholder URL, hypothetical service, optional plugin, caller-supplied adapter, or unit
  test around a fake is not an implementation of a required default path. For an external
  integration, name the concrete generally available API or built-in mechanism, its auth
  source, its failure behavior, and execute a live smoke test when credentials permit.
- Record the supported environment, CLI versions, exact capability profile, representative
  true/false outcome, elapsed time, and any account/network limitation for a default external
  integration. Keep diagnostic as the default until that evidence is broad enough to justify
  promotion; a fake-backed unit test or one convenient success is not rollout evidence.
- Treat acceptance failures as architectural evidence. A clean prose/code review cannot
  compensate for a primary path that has never successfully run in its supported operating
  environment.
- Test class invariants and root causes, not only the latest example.
- After a class fix, run one focused verification round to test that architectural decision;
  do not automatically begin another unbounded patch cycle.
- Report performance and complexity regressions alongside correctness results.
- Do not open or merge a PR while an architecture checkpoint is unresolved, the documented
  threat model differs from the reviewed stakes, or the rollout stage is being skipped.
- A clean review means no in-scope blocking class remains under the frozen stakes. It does
  not mean hardening against every imaginable actor or failure mode.
