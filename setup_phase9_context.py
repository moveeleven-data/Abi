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
    "context/16_LIVE_MINIMAL_REREAD_LOOP_SPEC.md",
    """
# Phase 9: Guarded Live Minimal Reread Loop v1 Spec

## Status

Phase 9 implements a guarded live-shaped Minimal Reread loop.

This phase remains bounded to the minimal reread loop. It is not the production essay system.

## Goal

Produce a complete Minimal Reread packet from the benchmark germ and/or a live Abi Ear packet using validated model-shaped workers.

The phase must demonstrate the core Abi loop in live-shaped form:

reader-state trace
→ diagnosed failure
→ targeted intervention
→ counterfactual proof

## Inputs

Primary benchmark input:

The table is still there in the morning.

The command may run or reuse a live Abi Ear fake packet as an upstream dependency.

## Required CLI behavior

Add a command such as:

abi reread live-demo --client fake

and optionally:

abi reread live-demo --client openai --allow-live-model --max-model-calls 12

Rules:

- deterministic `abi reread demo` must remain unchanged
- fake client mode must not require API key
- openai client mode must require --allow-live-model
- openai client mode must require OPENAI_API_KEY
- live packet output must use unique packet directories
- parsed model artifacts must include model_call_id
- every model-shaped output must be schema-validated before artifact registration
- final Minimal Reread packet must register all artifacts through the artifact registry

## Required artifacts

The live minimal reread packet should produce artifact types equivalent to:

- live_reread_formal_problem
- live_reread_germ_afterimage_pair
- live_reread_consequence_graph
- live_reread_draft_version
- live_reread_first_read_trace
- live_reread_reread_trace
- live_reread_failure_diagnosis
- live_reread_intervention
- live_reread_recomposed_draft
- live_reread_counterfactual_result
- live_reread_irreducibility_report
- live_reread_gate_report
- live_reread_packet

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

Add a simple max-call guard for live reread execution.

The command should accept something like:

--max-model-calls 12

Default should be conservative.

If the loop would exceed the budget, it must refuse or stop with a structured error.

## Required loop shape

The packet must make the loop explicit:

1. first-read trace
2. reread trace
3. failure diagnosis
4. targeted intervention
5. recomposed draft
6. counterfactual result

The output does not need to be artistically excellent yet. The goal is control and traceability.

## Prohibited

- no production essay generation
- no source ingestion changes
- no human calibration automation
- no lineage tournament
- no multi-branch search
- no agent loops
- no automatic OpenAI calls
- no deterministic demo replacement
- no finalization semantics changes
- no SKILL.md

## Acceptance criteria

Phase 9 is complete only when:

- ruff passes
- pytest passes
- deterministic demos still work
- fake live Minimal Reread command works
- openai live Minimal Reread command refuses without --allow-live-model
- openai live Minimal Reread command refuses without OPENAI_API_KEY
- packet artifacts are registered with parent IDs and hashes
- accepted parsed model artifacts include model_call_id
- invalid fake outputs are rejected in tests
- counterfactual result artifact exists
- finalization remains fail-closed
""",
)

write(
    "context/plans/PHASE_9_LIVE_MINIMAL_REREAD_LOOP.md",
    """
# Phase 9 Live Minimal Reread Loop ExecPlan

## Goal

Implement the guarded live-shaped Minimal Reread loop.

This phase should convert the deterministic Minimal Reread loop into a fake-model/live-guarded packet while preserving deterministic behavior.

## Scope

Add:

- live Minimal Reread packet orchestrator
- fake-client packet path
- optional guarded OpenAI packet path
- schemas for Minimal Reread outputs if needed
- model-call record reuse
- artifact registry integration
- max model-call guard
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/live_reread.py
tests/test_live_reread_packet.py
tests/test_live_reread_cli.py

Likely updated files:

src/abi/cli.py
src/abi/model_schemas.py
src/abi/live_model.py
src/abi/model_driver.py
README.md

## CLI

Preferred command:

abi reread live-demo --client fake

Optional real live path:

abi reread live-demo --client openai --allow-live-model --max-model-calls 12

The fake path must use fake/stubbed model clients and require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Required output packet

The live minimal reread packet must produce:

1. formal_problem
2. germ_afterimage_pair
3. consequence_graph
4. draft_version
5. first_read_trace
6. reread_trace
7. failure_diagnosis
8. intervention
9. recomposed_draft
10. counterfactual_result
11. irreducibility_report
12. gate_report
13. packet summary

## Tests

Tests must verify:

- all previous tests still pass
- deterministic `abi reread demo` remains unchanged
- fake live Minimal Reread packet succeeds
- fake live packet produces required artifact types
- fake live packet registers model_call_id on parsed model artifacts
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- max-call budget is enforced
- openai client path refuses without --allow-live-model
- openai client path refuses without OPENAI_API_KEY
- invalid fake output records validation_failed and creates no parsed artifact
- client failure records client_failed and creates no parsed artifact
- counterfactual result exists
- finalization remains fail-closed

## Manual live smoke test

Manual OpenAI live reread smoke test is optional and should not be run by Codex.

It should require:

- OPENAI_API_KEY set
- --allow-live-model passed
- max model calls explicitly set

## Done means

Phase 9 is done when a minimal reread packet can be generated through fake model-shaped workers, all outputs are registered and inspectable, and the guarded OpenAI path is available but not automatic.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 9 reads:",
    """
## Phase 9 reads:

For Phase 9, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/04_ABI_REREAD_CORE_SPEC.md
7. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
8. context/06_DATA_MODEL.md
9. context/08_GATES_AND_EVALUATION.md
10. context/11_MODEL_READINESS_CONSOLIDATION_SPEC.md
11. context/12_MODEL_DRIVER_FAKE_CLIENT_SPEC.md
12. context/15_LIVE_ABI_EAR_PACKET_SPEC.md
13. context/16_LIVE_MINIMAL_REREAD_LOOP_SPEC.md
14. context/plans/PHASE_9_LIVE_MINIMAL_REREAD_LOOP.md

Phase 9 implements the guarded live Minimal Reread loop only.
""",
)

print("Phase 9 Live Minimal Reread Loop context files created.")
print("Next:")
print("  git status")
print("  git add context setup_phase9_context.py")
print('  git commit -m "Add Phase 9 live Minimal Reread loop frozen context"')
print("  git push")
