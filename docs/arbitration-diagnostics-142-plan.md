# Issue 142: arbitration diagnostics

## Operating model

Trusted single local user and OS; repository and fetched bytes are untrusted data.
Public HTTP(S) capture is the external boundary. No repository-selected execution,
hostile local races, compromised OS, multi-tenancy or corrupted-state recovery.
Ordinary edits must block/retry. Tens to low hundreds of claims, a few rounds,
useful evidence within minutes. False clearance and wrong evidence binding have
high impact; recoverable blocking is acceptable.

## Requirements

Preserve changed-selection grounding in gained, actually carried evidence,
already-substantiated holder behavior, decisive-only grounding, the two-round
ceiling, outcome enums, provisional selection and existing diagnostics. Explicitly
explain unanimous but unsubstantiated agreement in the report. Add no provider call.

Derive one shared research summary from completed runs and normalized packets:
discovered claims, usable/failed/binding-budget-excluded capture rows, bindings,
unbound usable capture rows, total/governing packets. Counts are per-claim rows,
not unique URLs.
Expose these counts in reports and audits, including partial binding and every
post-research failure path. Distinguish no claims, captures with no binding and
capture failures when no packets result. Preserve execution statuses, attempt
ledgers and all capture/binding artifacts. Research diagnostics never grant or
block the independently substantiated arbitration verdict.

Preserve complete admitted text and all existing capture/binding bounds. The field
report does not establish extraction truncation; windowing and changed source
policy are excluded.

The retained field audit `20261105T161405-arbitrate-6756114d` shows three binding
budget exclusions, fifteen empty extractions and two raw-response size failures,
all with HTTP 200. See arbitration-diagnostics-142-incident.json for bounded
provenance from every capture row. It does not show silent truncation.
Expose these distinct server-owned causes without changing admission policy.

## Acceptance

Public-handler regressions cover grounded/ungrounded changes and holders, empty
discovery, successful unbound captures, failed captures, binding-budget exclusions,
partial binding and post-research failures, with identical report/audit counts and unchanged call
topology. Long-source extraction/binding preparation preserves complete text or
explicitly excludes it, never silently truncates it. A mixed public-handler fixture
must assert explicit expected counters for capture failures and budget exclusions separately in both
report and audit; equality alone is insufficient.

Run deterministic tests and native public arbitration with weaker test models.
The native fixture asks which wire message conforms to RFC 8259, contrasting an
object literal with a message containing a leading comment. Use research enabled,
require completed discovery and capture/binding work, at least one usable capture,
binding and governing packet, and verify the report and audit counters. A failed
or incomplete run cannot qualify. Cleaning is disabled to avoid its pinned Astra
attester; both researchers and deciders use weaker models. Then run
Astra CODE convergence through tracked class/debt closure and cold final. Record
source, calls, elapsed time and diff size. Then open/merge the PR and update local
main and the installed package.
