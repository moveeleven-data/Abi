from pathlib import Path

ROOT = Path.cwd()


def write(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip() + "\n", encoding="utf-8")


def append_once(path: str, marker: str, text: str) -> None:
    p = ROOT / path
    current = p.read_text(encoding="utf-8") if p.exists() else ""
    if marker not in current:
        p.write_text(current.rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8")


write(
    "context/15_LIVE_ABI_EAR_PACKET_SPEC.md",
    """
# Phase 8: Live Abi Ear Packet v1 Spec

## Status

Phase 8 implements a guarded live Abi Ear packet pipeline.

This phase is larger than Phase 7A/7B but remains bounded to Abi Ear only.

## Goal

Produce a complete Abi Ear packet for the benchmark germ using the model-driver/live-worker infrastructure.

Benchmark input:

The table is still there in the morning.

The live packet must prove that Abi can produce a full local literary packet through validated, recorded model-shaped outputs while preserving deterministic demos and fail-closed finalization.

## Scope

Phase 8 may add live/stubbed workers for the remaining Abi Ear packet pieces:

- variants
- move composition
- ranked move sequence / retrospective judge
- prose inventions
- refined invention
- reread trace
- ablation report
- local gate report
- packet summary

It may reuse existing guarded live workers:

- abi_ear_germ_analysis
- abi_ear_field_model

## Required CLI behavior

Add a command such as:

abi ear live-demo --client fake

and optionally:

abi ear live-demo --client openai --allow-live-model --max-model-calls 8

Rules:

- deterministic `abi ear demo` must remain unchanged
- fake client mode must not require API key
- openai client mode must require --allow-live-model
- openai client mode must require OPENAI_API_KEY
- live packet output must use unique packet directories
- parsed model artifacts must include model_call_id
- every model-shaped output must be schema-validated before artifact registration
- final Abi Ear packet must register all artifacts through the artifact registry

## Required artifact types

The live packet should produce artifact types equivalent to:

- live_abi_ear_germ_analysis
- live_abi_ear_field_model
- live_abi_ear_variants
- live_abi_ear_moves
- live_abi_ear_ranked_move_sequence
- live_abi_ear_prose_inventions
- live_abi_ear_refined_invention
- live_abi_ear_reread_trace
- live_abi_ear_ablation_report
- live_abi_ear_gate_report
- live_abi_ear_packet

Exact type names may differ if they align with existing conventions.

## Required model-call behavior

Every live/fake model worker call must create or reuse model-call records.

Accepted parsed artifacts must include:

- schema_version
- artifact_type
- run_id
- lineage_id
- parent_ids
- created_by
- fixture_only
- model_call_id
- payload

Invalid model outputs must not create parsed artifacts.

Client failures must be recorded.

## Budget guard

Add a simple max-call guard for live packet execution.

The command should accept something like:

--max-model-calls 8

Default should be conservative.

If the packet would exceed the budget, it must refuse or stop with a structured error.

## Prohibited

- no production essay generation
- no live Minimal Reread loop
- no source ingestion changes
- no human calibration automation
- no agent loops
- no automatic OpenAI calls
- no deterministic demo replacement
- no finalization semantics changes
- no SKILL.md

## Acceptance criteria

Phase 8 is complete only when:

- ruff passes
- pytest passes
- deterministic demos still work
- fake live Abi Ear packet command works
- openai live Abi Ear packet command refuses without --allow-live-model
- openai live Abi Ear packet command refuses without OPENAI_API_KEY
- packet artifacts are registered with parent IDs and hashes
- accepted parsed model artifacts include model_call_id
- invalid fake outputs are rejected in tests
- finalization remains fail-closed
""",
)

write(
    "context/plans/PHASE_8_LIVE_ABI_EAR_PACKET.md",
    """
# Phase 8 Live Abi Ear Packet ExecPlan

## Goal

Implement the guarded live Abi Ear packet pipeline.

This phase should convert the isolated live Abi Ear workers into a complete local Abi Ear packet while preserving deterministic behavior.

## Scope

Add:

- live Abi Ear packet orchestrator
- fake-client packet path
- optional guarded OpenAI packet path
- schemas for remaining Abi Ear packet outputs if needed
- model-call record reuse
- artifact registry integration
- max model-call guard
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/live_abi_ear.py
tests/test_live_abi_ear_packet.py
tests/test_live_abi_ear_cli.py

Likely updated files:

src/abi/cli.py
src/abi/model_schemas.py
src/abi/live_model.py
src/abi/model_driver.py
README.md

## CLI

Preferred command:

abi ear live-demo --client fake

Optional real live path:

abi ear live-demo --client openai --allow-live-model --max-model-calls 8

The fake path must use fake/stubbed model clients and require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Tests

Tests must verify:

- all previous tests still pass
- deterministic `abi ear demo` remains unchanged
- fake live Abi Ear packet succeeds
- fake live packet produces required artifact types
- fake live packet registers model_call_id on parsed model artifacts
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- max-call budget is enforced
- openai client path refuses without --allow-live-model
- openai client path refuses without OPENAI_API_KEY
- invalid fake output records validation_failed and creates no parsed artifact
- client failure records client_failed and creates no parsed artifact
- finalization remains fail-closed

## Manual live smoke test

Manual OpenAI live packet smoke test is optional and should not be run by Codex.

It should require:

- OPENAI_API_KEY set
- --allow-live-model passed
- max model calls explicitly set

## Done means

Phase 8 is done when a full Abi Ear packet can be generated through fake model-shaped workers, all outputs are registered and inspectable, and the guarded OpenAI path is available but not automatic.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 8 reads:",
    """
## Phase 8 reads:

For Phase 8, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/03_ABI_EAR_V1_SPEC.md
7. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
8. context/06_DATA_MODEL.md
9. context/08_GATES_AND_EVALUATION.md
10. context/11_MODEL_READINESS_CONSOLIDATION_SPEC.md
11. context/12_MODEL_DRIVER_FAKE_CLIENT_SPEC.md
12. context/13_FIRST_LIVE_WORKER_SPEC.md
13. context/14_LIVE_FIELD_MODEL_WORKER_SPEC.md
14. context/15_LIVE_ABI_EAR_PACKET_SPEC.md
15. context/plans/PHASE_8_LIVE_ABI_EAR_PACKET.md

Phase 8 implements the guarded live Abi Ear packet pipeline only.
""",
)

print("Phase 8 Live Abi Ear Packet context files created.")
print("Next:")
print("  git status")
print("  git add context tools/setup_context_scripts/setup_phase8_context.py")
print('  git commit -m "Add Phase 8 live Abi Ear packet frozen context"')
print("  git push")
