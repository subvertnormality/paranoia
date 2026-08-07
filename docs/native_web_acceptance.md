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
authority only to relevant `primary` or `authoritative` records. Known UGC hosts are forced
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
2. RFC 9110 defines HTTP status code 511 as Permanent Redirect.

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
| Claude configured default model | Claude Code 2.1.197, Fable | Account reported exhausted usage credits before a result; this is an external account limitation, not recorded as a successful model check |
| Codex full RFC fixture | Codex CLI 0.144.6, `gpt-5.6-sol` | Completed accurately in about 234 seconds, inside the 480-second deadline |

The full Codex fixture used no search endpoint, API key, source override, or supplied evidence.
It produced four claims: two plan decisions classified `not-applicable`, the June 2022 fact
`verified`, and the hidden 511/Permanent Redirect claim `contradicted`. The structural review
also reported that RFC 9110 defines Permanent Redirect as 308 and RFC 6585 defines 511 as
Network Authentication Required.

The truth-bearing records were fetched from the RFC Editor:

- `https://www.rfc-editor.org/rfc/rfc9110.html` — `primary`, isolated provenance assessment;
- `https://www.rfc-editor.org/rfc/rfc6585.html` — `primary`, isolated provenance assessment.

No UGC or secondary source authorized a transition. The result was
`CLAIM-CLOSURE: DIAGNOSTIC-BLOCKED` because the contradicted premise correctly remained
load-bearing, while the default rollout semantics left class convergence non-blocking.

## Interpretation and promotion

This evidence proves that the supported Codex path can discover, retrieve, classify, and
accurately adjudicate a representative internet-only true/false pair out of the box. It also
proves that the Claude search-only capability profile works with an available supported
model. It does not yet establish representative false-block rates, broad project coverage,
or successful full-pipeline completion on both configured default models.

Accordingly, verification is **on by default in `diagnostic` mode**. Promotion to
blocking-by-default requires a broader recorded matrix of projects, source types, true and
false claims, cached rounds, both reviewer defaults, latency, and ordinary account/network
failures. Individual workflows may select `blocking` now when they accept that rollout risk.
