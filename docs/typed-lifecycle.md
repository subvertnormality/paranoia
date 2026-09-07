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

The [complete source-hashed baseline/candidate inventory](lifecycle_complexity_inventory_2026-09-07.json.gz)
includes every module and function plus production diff sizes. It binds baseline
cc1afef87c1386379fc2da97b72b733815013ca0 and candidate
5c3ed0c9df0a02d541767ff1ab2c2aa610e4ffc4; subsequent benchmark-only edits do not
change those production bytes. The deterministic gzip SHA-256 is
365a4a6b81a4c9ede76bf56ff7c03618d5c43c8361c74ef3b6c6ee0edd0ba2ec.

The frozen matrix covers 3,024 cases (622 accepted), comparing exact projections,
canonical class application, durable state/trailers and rejected diagnostics with
the baseline. Its receipt is `lifecycle_equivalence_baseline.json`; run
`tests/test_lifecycle_decisions.py` and the existing staged protocol tests.
All seven historical V1/V2 differential groups and all 33 owned mutation probes
passed after retargeting moved controls. Full-suite and CODE acceptance remain
separate mandatory delivery gates.
