# Native web verification acceptance

This document records why claim verification uses the reviewing CLIs' built-in search,
what must be exercised before release, and what the current live evidence establishes. It
is an acceptance record, not a claim that internet research is universally correct.

## Fixed integrations

Paranoia Local has two built-in discovery paths:

| Reviewer | Discovery API | Authentication | Allowed capability |
|---|---|---|---|
| Codex | `codex --search exec` | The operator's existing Codex CLI sign-in | Native live search only |
| Claude | Claude Code `WebSearch` | The operator's existing Claude Code sign-in | `WebSearch` only |

These are product defaults, not plugins or caller-supplied providers. There is no
`PARANOIA_SEARCH_ENDPOINT`, extra search API key, or optional endpoint contract. The search
role receives one neutral query and can return only HTTPS URL/title candidates. It cannot
read the repository, run shell commands, fetch candidate pages directly, classify source
authority, or verify a claim.

The server treats candidates as leads. It independently validates DNS, redirects, connected
peers, HTTPS, response media, byte limits, and deadlines; fetches and hashes the page; selects
a bounded passage; classifies publisher provenance in a fresh isolated role; and gives truth
authority only to relevant `primary` or `authoritative` records. A primary counter-source
does not lose that class merely because it is a different artifact from one falsely named
in the claim; the verifier separately decides what its visible passage establishes. Known UGC hosts are forced
to `ugc` and cannot be promoted by the discovery or provenance model. Secondary, UGC, and
unclassified pages may expose leads or conflicts but cannot clear a general factual claim.

## Release check

For each supported reviewer whose account is available:

1. Run the empty-tool capability preflight and one empty-tool call.
2. Run the search-only capability preflight and search for a canonical primary source.
3. Run `critique_plan` with no endpoint, API key, source policy, or supplied evidence. Leave
   `web_search` at its default `true` and `claim_verification` at its default `diagnostic`.
4. Use a plan containing one externally verifiable true fact and one plausible hidden
   falsehood. State that repository and caller artifacts do not establish either fact.
5. Confirm that the true claim is verified from a relevant primary/authoritative passage,
   the false claim is contradicted, and no UGC/secondary record authorizes either outcome.
6. Record CLI/model versions, elapsed time, sources, provenance classes, verdicts, and any
   account or network limitation. Confirm the round stays within the shared 480-second hard
   deadline.

The representative RFC fixture is:

```text
Prepare a standards research memo that determines the truth of exactly these two factual premises:

1. RFC 9110 was published in June 2022.
2. RFC 6585 defines HTTP status code 511 as Permanent Redirect.

Research both premises now using authoritative public internet sources. Repository files and
caller-supplied artifacts do not establish them. Record a premise as contradicted when the
authoritative source conflicts with it; do not assume or defer either premise.
```

The second premise is deliberately false but is not labelled as false in the submitted plan.
Do not add dependency or later-verification wording to this fixture: that tests deferral
contracts instead of immediate internet research.

## Current live evidence

The following checks were run on 2026-08-07 from Linux under WSL, before adversarial code
convergence:

| Path | Version/model | Result |
|---|---|---|
| Codex empty-tool | Codex CLI 0.144.6 | Completed with the isolated no-tool profile |
| Codex search-only | Codex CLI 0.144.6 | Returned the canonical RFC Editor candidate using native live search |
| Claude search-only | Claude Code 2.1.197, Sonnet | Returned canonical RFC candidates with only `WebSearch` enabled |
| Claude full RFC fixture | Claude Code 2.1.197, Sonnet | Completed accurately in about 262 seconds: true claim verified, hidden falsehood contradicted |
| Claude configured default model | Claude Code 2.1.197, Fable | Account reported exhausted usage credits before a result; this is an external account limitation, not recorded as a successful model check |
| Codex full RFC fixture | Codex CLI 0.144.6, `gpt-5.6-sol` | Completed accurately in about 234 seconds, inside the 480-second deadline |

Both full fixtures used no search endpoint, API key, source override, or supplied evidence.
The Codex run used the sharper attribution claim “RFC 9110 defines 511 as Permanent Redirect”
and correctly contradicted it by identifying 308 as Permanent Redirect and RFC 6585 as the
definition of 511. The maintained fixture now names RFC 6585 directly so one primary artifact
can visibly contradict the proposition without also asking the acceptance test to prove an
absence from another named document. The Claude run verified the June 2022 fact and
contradicted the maintained hidden falsehood from bounded primary passages.

The truth-bearing records were fetched from the RFC Editor:

- `https://www.rfc-editor.org/rfc/rfc9110.html` — `primary`, isolated provenance assessment;
- `https://www.rfc-editor.org/rfc/rfc6585.html`, IETF Datatracker, or the HTTP Working Group
  rendering — `primary`, isolated provenance assessment.

No UGC or secondary source authorized a transition. The result was
`CLAIM-CLOSURE: DIAGNOSTIC-BLOCKED` because the contradicted premise correctly remained
load-bearing, while the default rollout semantics left class convergence non-blocking.

Sanitized, checked-in exports make the underlying results independently auditable:

- [`native_web_codex_2026-08-07.json`](acceptance/native_web_codex_2026-08-07.json)
- [`native_web_claude_2026-08-07.json`](acceptance/native_web_claude_2026-08-07.json)

Each export contains the exact claim status and transition, evidence/content hashes, URL,
source class and provenance method, passage offsets and hash, full displayed passage, and
terminal closure lines. The Claude structural role registered a class claiming that quoted
passages were absent because that role intentionally receives external metadata rather than
remote bodies; the export shows the passages that were retained and sent to the verifier.
The acceptance criterion concerns the persisted verified/contradicted claim outcomes, not a
clear structural convergence verdict for this deliberately false plan.

## Interpretation and promotion

This evidence proves that both supported reviewer integrations can discover, retrieve,
classify, and accurately adjudicate a representative internet-only true/false pair out of
the box using available signed-in models. It does not yet establish representative
false-block rates, broad project coverage, or successful full-pipeline completion on both
configured default models; the configured Claude Fable model was unavailable because of the
account's usage-credit state.

Accordingly, verification is **on by default in `diagnostic` mode**. Promotion to
blocking-by-default requires a broader recorded matrix of projects, source types, true and
false claims, cached rounds, both reviewer defaults, latency, and ordinary account/network
failures. Individual workflows may select `blocking` now when they accept that rollout risk.
