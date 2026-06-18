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
    "context/23_FIRST_REAL_CANDIDATE_SET_SPEC.md",
    """
# Phase 16: First Real Candidate Set / Pilot Artifact Set Spec

## Status

Phase 16 prepares the first real pilot artifact set.

This phase must not collect human data.

This phase must not claim validation.

This phase must not mark final gates passed.

This phase must not run an automatic OpenAI call.

## Goal

Create a source-frozen candidate-set pipeline that can produce the artifacts needed for the first human-reader pilot:

- Abi candidate
- direct-prompt baseline
- raw-model baseline
- strongest-rival placeholder or imported strongest rival
- neutral labels
- blinded study bundle
- pilot readiness report

The output should make the artifact set ready for future human reading under the Phase 15 protocol.

## Privacy rule

The repo may be public.

Do not commit private source material.

Phase 16 must support source input from an untracked local directory such as:

inputs/private/phase16_source/

The command may also support deterministic fixture mode for tests.

Add or preserve gitignore protection for private input directories.

## Required CLI behavior

Add a command such as:

abi pilot artifact-set --client fake --source-dir fixtures/production_harness

and optionally:

abi pilot artifact-set --client openai --source-dir inputs/private/phase16_source --allow-live-model --max-model-calls 36

Rules:

- fake mode must require no API key
- OpenAI mode must require --allow-live-model
- OpenAI mode must require OPENAI_API_KEY
- tests must use fake mode only
- no automatic OpenAI calls
- source manifest must include source file names and hashes
- private source files must not be copied into tracked docs
- output must use unique packet directories
- finalization must remain fail-closed

## Required artifact set

The pilot artifact set must include artifacts equivalent to:

1. pilot_source_manifest
2. pilot_generation_plan
3. pilot_abi_candidate_ref
4. pilot_direct_prompt_baseline
5. pilot_raw_model_baseline
6. pilot_strongest_rival_slot
7. pilot_neutral_label_map_private
8. pilot_blinded_reader_bundle
9. pilot_artifact_set_manifest
10. pilot_readiness_report
11. pilot_packet

Exact names may differ if aligned with repo conventions.

## Candidate and baseline rules

The Abi candidate must remain:

- non_final: true
- not_human_validated: true
- not_finalization_eligible: true
- no_phase_shift_claim: true

Baselines generated in fake mode must be marked fixture/fake.

Strongest-rival placeholder must state that strongest-rival evidence is not yet satisfied unless a real rival artifact is explicitly imported under protocol rules.

Neutral labels must not reveal source class to readers.

## Budget behavior

Add or reuse max-call budgeting.

Suggested default:

--max-model-calls 36

If execution would exceed the budget, refuse with a structured error.

## Required finalization behavior

Phase 16 must preserve finalization refusal.

No final_artifact gates should pass from Phase 16 artifact-set generation.

## Prohibited

- no real human data collection
- no live OpenAI call during tests or Codex implementation
- no final artifact claim
- no phase-shift claim
- no gate passing
- no dashboard
- no SKILL.md
- no broad refactor
- no architecture rewrite

## Acceptance criteria

Phase 16 is complete when:

- ruff passes
- pytest passes
- fake pilot artifact-set command works
- OpenAI path refuses without --allow-live-model
- OpenAI path refuses without OPENAI_API_KEY
- source manifest hashes source files
- private source directory is gitignored
- pilot bundle uses neutral labels
- candidate remains non-final
- baselines are marked fixture/fake in fake mode
- strongest-rival slot does not falsely pass strongest-rival gate
- finalization remains fail-closed
""",
)

write(
    "context/plans/PHASE_16_FIRST_REAL_CANDIDATE_SET.md",
    """
# Phase 16 First Real Candidate Set ExecPlan

## Goal

Implement the first pilot artifact-set generator.

This is the bridge between protocol and actual human-reader pilot.

## Scope

Add:

- pilot artifact-set orchestrator
- fake-client path
- guarded OpenAI path
- source manifest with hashes
- private input directory protection
- neutral label map
- blinded reader bundle
- candidate/baseline artifacts
- strongest-rival slot
- pilot readiness report
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/pilot_artifact_set.py
tests/test_pilot_artifact_set.py
tests/test_pilot_artifact_set_cli.py

Likely updated files:

src/abi/cli.py
src/abi/controller/state.py
README.md
.gitignore

Optional fixtures:

fixtures/pilot_source/

## CLI

Preferred command:

abi pilot artifact-set --client fake --source-dir fixtures/production_harness

Optional guarded live path:

abi pilot artifact-set --client openai --source-dir inputs/private/phase16_source --allow-live-model --max-model-calls 36

## Tests

Tests must verify:

- all previous tests still pass
- fake artifact-set command succeeds
- source manifest records file hashes
- private input path is gitignored
- neutral labels do not reveal source class
- blinded reader bundle exists
- candidate artifact is non-final and not human validated
- fake baselines are marked fixture/fake
- strongest-rival slot remains unsatisfied unless real imported rival exists
- OpenAI path refuses without --allow-live-model
- OpenAI path refuses without OPENAI_API_KEY
- final_artifact profile remains ineligible
- finalization remains fail-closed

## Done means

Phase 16 is done when the repo can create a pilot-ready artifact set without collecting human data or making validation claims.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 16 reads:",
    """
## Phase 16 reads:

For Phase 16, read:

1. AGENTS.md
2. README.md
3. docs/phase14_operator_handoff/operator_handoff.md
4. docs/phase15_real_validation_protocol/validation_protocol.md
5. docs/phase15_real_validation_protocol/human_reader_protocol.md
6. docs/phase15_real_validation_protocol/baseline_protocol.md
7. docs/phase15_real_validation_protocol/raw_model_baseline_protocol.md
8. docs/phase15_real_validation_protocol/strongest_rival_protocol.md
9. docs/phase15_real_validation_protocol/blind_reread_task.md
10. docs/phase15_real_validation_protocol/live_run_budget_plan.md
11. docs/phase15_real_validation_protocol/evidence_to_gate_mapping.md
12. context/23_FIRST_REAL_CANDIDATE_SET_SPEC.md
13. context/plans/PHASE_16_FIRST_REAL_CANDIDATE_SET.md

Phase 16 implements the pilot artifact-set generator only.
""",
)

print("Phase 16 First Real Candidate Set context files created.")
print("Next:")
print("  git status")
print("  git add context tools/setup_context_scripts/setup_phase16_context.py")
print('  git commit -m "Add Phase 16 first real candidate set frozen context"')
print("  git push")
