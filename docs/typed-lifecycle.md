# Typed lifecycle decisions

The class lifecycle extraction follows [the accepted contract](effectiveness-lifecycle-plan.md).
It preserves the canonical class engine and wire protocol. Measurements and exact
transition equivalence determine delivery; line count alone is not acceptance.

`lifecycle_decisions.py` owns pure concession checks, explicit action checks and
derived lifecycle decisions. `ClassState` captures the existing class facts;
`LifecycleDecision` returns derived actions with their authored pointers and
ordered diagnostics. The materializer retains wire/reference/debt binding,
encounter order and projection. The canonical class engine still applies every
accepted transition after validation; no reviewer prompt, role or call changed.

Against baseline `cc1afef`, the materializer fell from 585 to 454 lines and from
171 to 116 in the documented inclusive AST branch proxy. Production grew from
20,680 to 20,785 lines. Extracted transition functions are at most 45 lines.
Run `scripts/measure_review_complexity.py --revision <commit>` to reproduce source
inventories and hashes. These are maintenance measurements, not a speed claim.

The frozen matrix covers 3,024 cases (622 accepted), comparing exact projections,
canonical class application, durable state/trailers and rejected diagnostics with
the baseline. Its receipt is `lifecycle_equivalence_baseline.json`; run
`tests/test_lifecycle_decisions.py` and the existing staged protocol tests.
All seven historical V1/V2 differential groups and all 33 owned mutation probes
passed after retargeting moved controls. Full-suite and CODE acceptance remain
separate mandatory delivery gates.
