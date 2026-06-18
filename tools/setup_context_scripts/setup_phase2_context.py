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
    "context/04_ABI_REREAD_CORE_SPEC.md",
    """
# Minimal Abi Reread Core Spec

## Phase 2 status

Phase 2 implements a minimal deterministic Abi Reread loop.

No model calls are allowed in Phase 2.

Phase 2 is not the full essay machine. It is the smallest end-to-end reread compiler loop built on Phase 0 infrastructure and Phase 1 Abi Ear.

## Goal

Given the Abi Ear benchmark packet, Phase 2 must produce a minimal reread loop:

1. formal problem
2. germ/afterimage pair
3. consequence graph
4. draft version
5. blind first-read trace
6. reread trace
7. failure diagnosis
8. targeted intervention
9. recomposed draft
10. counterfactual result
11. irreducibility report
12. gate report
13. reread packet summary

All outputs must be deterministic.

## Core loop

reader-state trace
â†’ diagnosed failure
â†’ targeted intervention
â†’ counterfactual proof

This loop must exist structurally even with deterministic stub content.

## Required artifact types

- reread_formal_problem
- reread_germ_afterimage_pair
- reread_consequence_graph
- reread_draft_version
- reread_first_read_trace
- reread_reread_trace
- reread_failure_diagnosis
- reread_intervention
- reread_recomposed_draft
- reread_counterfactual_result
- reread_irreducibility_report
- reread_gate_report
- reread_packet

Each artifact must be registered through the Phase 0 artifact registry.

## Required CLI behavior

Add a command similar to:

abi reread demo

It should:

- ensure a run exists
- run or reuse the deterministic Abi Ear benchmark packet
- create a unique packet directory under runs/<run_id>/reread/<packet_id>/
- write all Phase 2 artifacts as JSON
- register all artifacts in SQLite
- update active_phase to phase2_minimal_reread
- print a compact JSON summary with run_id, packet_id, artifact IDs, and gate result

## Determinism

Phase 2 outputs must not depend on API calls, randomness, clock time except artifact metadata, or external files not in the repo.

## Prohibited in Phase 2

- no OpenAI API calls
- no real model_driver behavior
- no production essay generation
- no human calibration UI
- no large orchestration framework
- no SKILL.md
- no full Phase 3 fail-closed controller expansion
- no Phase 4 production harness

## Acceptance criteria

Phase 2 is complete only when:

- all existing tests pass
- abi reread demo runs locally
- all required Phase 2 artifact types are produced
- artifacts are registered with hashes and parent IDs
- packet directories are immutable and non-overwriting
- active_phase becomes phase2_minimal_reread
- a gate report is produced
- finalization still refuses unless required finalization gates are satisfied
""",
)

write(
    "context/plans/PHASE_2_MINIMAL_REREAD.md",
    """
# Phase 2 Minimal Abi Reread ExecPlan

## Goal

Implement the smallest deterministic reread compiler loop.

Phase 2 should prove the architecture can represent:

reader-state trace
â†’ diagnosed failure
â†’ targeted intervention
â†’ counterfactual proof

without model calls.

## Scope

Add:

- deterministic reread module
- minimal formal problem artifact
- germ/afterimage artifact
- consequence graph artifact
- draft artifact
- first-read trace
- reread trace
- failure diagnosis
- intervention
- recomposed draft
- counterfactual result
- irreducibility report
- gate report
- CLI command
- tests

## Expected implementation files

Likely files:

src/abi/modules/reread.py
tests/test_reread.py
tests/test_reread_cli.py

Possible updates:

src/abi/cli.py
src/abi/controller/state.py
README.md

## CLI

Add a command such as:

abi reread demo

The command should:

- initialize or reuse the active run
- ensure Abi Ear deterministic artifacts are available or create a dependency packet
- create a unique run subfolder:
  runs/<run_id>/reread/<packet_id>/
- write artifacts
- register artifacts
- print JSON summary

## Required output packet

The benchmark run must produce:

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
- deterministic pipeline output
- all required artifact types are produced
- all required artifacts are registered
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- active_phase becomes phase2_minimal_reread
- gate report exists
- counterfactual result exists
- finalization refusal still works
- no model/API code is called

## Constraints

No model calls.
No production generation.
No human calibration UI.
No Phase 3 controller expansion.
No SKILL.md.

## Done means

Phase 2 context is satisfied when:

- python -m pytest passes
- abi reread demo runs
- all Minimal Reread artifacts are stored and registered
- finalization still refuses unless required gates are satisfied
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 2 reads:",
    """
## Phase 2 reads:

For Phase 2, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/03_ABI_EAR_V1_SPEC.md
7. context/04_ABI_REREAD_CORE_SPEC.md
8. context/06_DATA_MODEL.md
9. context/07_PROMPT_CONTRACTS.md
10. context/08_GATES_AND_EVALUATION.md
11. context/plans/PHASE_2_MINIMAL_REREAD.md

Phase 2 implements Minimal Abi Reread with deterministic/stub workers only.
""",
)

print("Phase 2 Minimal Abi Reread context files created.")
print("Next:")
print("  git status")
print("  git add context tools/setup_context_scripts/setup_phase2_context.py")
print('  git commit -m "Add Phase 2 Minimal Reread frozen context"')
print("  git push")
