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
    "context/17_SOURCE_TO_ARTIFACT_PRODUCTION_RUN_SPEC.md",
    """
# Phase 10: Controlled Source-to-Artifact Production Run v1 Spec

## Status

Phase 10 implements the first bounded source-to-artifact production run.

This is not the final essay system.

This is not a multi-lineage tournament.

This is not a human-calibrated production claim.

## Goal

Connect existing subsystems into one controlled production pipeline:

source material
→ production harness packet
→ selected germ / target effect
→ live Abi Ear packet
→ live Minimal Reread packet
→ candidate artifact packet
→ production run report
→ gate report

The phase should prove that Abi can move from source-like material to a candidate artifact packet while preserving artifact lineage, model-call records, guard behavior, and fail-closed finalization.

## Inputs

Default input should be deterministic fixture material from:

fixtures/production_harness/

Optional explicit source directory may be supported:

inputs/

or another user-provided path, but default tests must use fixtures only.

## Required CLI behavior

Add a command such as:

abi production live-demo --client fake

and optionally:

abi production live-demo --client openai --allow-live-model --max-model-calls 24

Rules:

- fake client mode must not require API key
- openai client mode must require --allow-live-model
- openai client mode must require OPENAI_API_KEY
- deterministic harness/ear/reread demos must remain unchanged
- production run output must use unique packet directories
- accepted parsed model artifacts must include model_call_id
- all artifacts must be registered through the artifact registry
- finalization must remain fail-closed

## Required production pipeline

The production run should create or reference:

1. production_source_manifest
2. production_harness_packet_ref
3. production_selected_germ
4. production_target_effect
5. production_live_abi_ear_packet_ref
6. production_live_reread_packet_ref
7. production_candidate_artifact
8. production_candidate_report
9. production_gate_report
10. production_packet

Artifact type names may differ if aligned with existing conventions, but the packet must expose these concepts.

## Candidate artifact

The candidate artifact may be derived from the live Minimal Reread recomposed draft or equivalent packet output.

It must be clearly marked:

- candidate only
- not final
- not human-validated
- not a phase-shift claim

## Model-call behavior

The fake production run may call existing fake live Abi Ear and fake live Minimal Reread paths.

Every model-shaped output must be schema-validated before parsed artifact registration.

Accepted parsed model artifacts must include:

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

Add or reuse a simple max-call guard.

Default should be conservative.

Suggested default:

--max-model-calls 24

If execution would exceed the budget, the command must refuse or stop with a structured error.

## Required gate behavior

Phase 10 gate report should evaluate only the production packet scaffold.

It must not claim final artifact success.

It must not satisfy finalization gates.

Finalization must remain fail-closed.

## Prohibited

- no final essay generation claim
- no multi-lineage tournament
- no human calibration automation
- no real human-study claims
- no automatic OpenAI calls
- no agent loops
- no finalization semantic changes
- no SKILL.md
- no broad refactor
- no dashboard

## Acceptance criteria

Phase 10 is complete only when:

- ruff passes
- pytest passes
- deterministic demos still work
- fake production live-demo works
- openai production live-demo refuses without --allow-live-model
- openai production live-demo refuses without OPENAI_API_KEY
- production packet contains source/harness/germ/ear/reread/candidate/report/gate artifacts
- candidate artifact is marked non-final
- accepted parsed model artifacts include model_call_id
- parent IDs are populated where appropriate
- max-call budget is enforced
- finalization remains fail-closed
""",
)

write(
    "context/plans/PHASE_10_SOURCE_TO_ARTIFACT_PRODUCTION_RUN.md",
    """
# Phase 10 Source-to-Artifact Production Run ExecPlan

## Goal

Implement the first bounded source-to-artifact production run.

This phase connects the existing production harness, live Abi Ear packet, and live Minimal Reread loop into a single candidate-artifact packet.

## Scope

Add:

- production run orchestrator
- fake-client production run path
- optional guarded OpenAI production run path
- candidate artifact packet
- production run report
- production gate report
- max model-call budget guard
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/production_run.py
tests/test_production_run.py
tests/test_production_run_cli.py

Likely updated files:

src/abi/cli.py
src/abi/controller/state.py
README.md

Possible updates if needed:

src/abi/modules/live_abi_ear.py
src/abi/modules/live_reread.py

## CLI

Preferred command:

abi production live-demo --client fake

Optional real live path:

abi production live-demo --client openai --allow-live-model --max-model-calls 24

The fake path must use fake/stubbed model clients and require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Required output packet

The production run packet must expose:

1. source_manifest
2. harness_packet_ref
3. selected_germ
4. target_effect
5. live_abi_ear_packet_ref
6. live_reread_packet_ref
7. candidate_artifact
8. candidate_report
9. production_gate_report
10. production_packet

The candidate artifact must be marked:

- non_final: true
- fixture_only or source_fixture where appropriate
- not_human_validated: true
- not_finalization_eligible: true

## Tests

Tests must verify:

- all previous tests still pass
- deterministic demos remain unchanged
- fake production live-demo succeeds
- fake production packet produces required concepts
- production packet references harness, live Abi Ear, and live Reread packets
- candidate artifact exists and is marked non-final
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- max-call budget is enforced
- openai client path refuses without --allow-live-model
- openai client path refuses without OPENAI_API_KEY
- finalization remains fail-closed

## Manual live smoke test

Manual OpenAI production smoke test is optional and should not be run by Codex.

It should require:

- OPENAI_API_KEY set
- --allow-live-model passed
- max model calls explicitly set

## Done means

Phase 10 is done when a source-to-candidate production packet can be generated through fake model-shaped workers, all outputs are registered and inspectable, and the guarded OpenAI path is available but not automatic.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 10 reads:",
    """
## Phase 10 reads:

For Phase 10, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
7. context/06_DATA_MODEL.md
8. context/08_GATES_AND_EVALUATION.md
9. context/09_PRODUCTION_HARNESS_SPEC.md
10. context/11_MODEL_READINESS_CONSOLIDATION_SPEC.md
11. context/12_MODEL_DRIVER_FAKE_CLIENT_SPEC.md
12. context/15_LIVE_ABI_EAR_PACKET_SPEC.md
13. context/16_LIVE_MINIMAL_REREAD_LOOP_SPEC.md
14. context/17_SOURCE_TO_ARTIFACT_PRODUCTION_RUN_SPEC.md
15. context/plans/PHASE_10_SOURCE_TO_ARTIFACT_PRODUCTION_RUN.md

Phase 10 implements the controlled source-to-artifact production run only.
""",
)

print("Phase 10 Source-to-Artifact Production Run context files created.")
print("Next:")
print("  git status")
print("  git add context setup_phase10_context.py")
print('  git commit -m "Add Phase 10 source-to-artifact production run frozen context"')
print("  git push")
