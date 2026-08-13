import json
from pathlib import Path

from paranoia_local import arbitrate_handler
from acceptance_fixture import repository_fixture


evidence_dir = Path(__file__).resolve().parent
source = evidence_dir / "positive-audit.json"
arguments = dict(json.loads(source.read_text(encoding="utf-8"))["raw_input"])
arguments["options"] = [
    {"id": option_id, "statement": statement}
    for option_id, statement in arguments["options"].items()
]


def progress(message: str) -> None:
    print(f"PROGRESS: {message}", flush=True)


with repository_fixture() as repo:
    arguments.update({
        "repo_path": str(repo),
        "clean": True,
        "research": False,
        "order_seed": "cleaning-attestation-positive-2026-08-13",
        "models": {"claude": "claude-opus-5"},
    })
    result = arbitrate_handler.arbitrate(
        arguments,
        log_dir=evidence_dir,
        now=lambda: "20260813T070000",
        on_progress=progress,
    )
print(f"CONTEXT-CHARS: {len(arguments['context'])}")
print(result)
if "\nARBITRATION: FAILED\n" in result:
    raise SystemExit(1)
