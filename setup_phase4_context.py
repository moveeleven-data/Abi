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
    "context/09_PRODUCTION_HARNESS_SPEC.md",
    """
# Production Harness Spec

## Phase 4 status

Phase 4 implements the deterministic Production Harness scaffold.

No model calls are allowed in Phase 4.

Phase 4 does not produce the final symbolic abiogenesis essay. It creates the source/canon/card/lineage infrastructure needed for later production runs.

## Goal

Create a deterministic harness that can ingest small fixture source material, distill it into structured cards, build a canon/kernel packet, create an artifact genome, create a candidate lineage packet, and emit a production report.

The purpose is to connect the existing Abi Ear and Minimal Reread spine to production-ready inputs and lineage structure without adding live model workers yet.

## Required pipeline

Given deterministic fixture material, the harness must produce:

1. source manifest
2. source cards
3. claim cards
4. motif cards
5. image cards
6. risk cards
7. canon/kernel packet
8. artifact genome
9. candidate lineage packet
10. harness gate report
11. production harness packet summary

## Required artifact types

- harness_source_manifest
- harness_source_cards
- harness_claim_cards
- harness_motif_cards
- harness_image_cards
- harness_risk_cards
- harness_canon_kernel
- harness_artifact_genome
- harness_candidate_lineage
- harness_gate_report
- harness_packet

Each artifact must be registered through the Phase 0 artifact registry.

## Required CLI behavior

Add a command similar to:

abi harness demo

It should:

- ensure a run exists
- use deterministic fixture inputs from fixtures/production_harness/
- create a unique packet directory under runs/<run_id>/harness/<packet_id>/
- write all Phase 4 artifacts as JSON
- register all artifacts in SQLite
- update active_phase to phase4_production_harness
- print a compact JSON summary with run_id, packet_id, artifact IDs, and gate result

## Determinism

Phase 4 outputs must not depend on API calls, randomness, clock time except artifact metadata, or external files not in the repo.

## Prohibited in Phase 4

- no OpenAI API calls
- no real model_driver behavior
- no live generation
- no full essay generation
- no human calibration UI
- no dashboard
- no large orchestration framework
- no SKILL.md

## Acceptance criteria

Phase 4 is complete only when:

- all previous tests pass
- abi harness demo runs locally
- all required Phase 4 artifact types are produced
- artifacts are registered with hashes and parent IDs
- packet directories are immutable and non-overwriting
- active_phase becomes phase4_production_harness
- a harness gate report is produced
- controller still refuses finalization unless required finalization gates are satisfied
""",
)

write(
    "context/plans/PHASE_4_PRODUCTION_HARNESS.md",
    """
# Phase 4 Production Harness ExecPlan

## Goal

Implement the deterministic production harness scaffold.

Phase 4 should prove that Abi can ingest source-like material into structured production artifacts while preserving the existing fail-closed controller and artifact registry invariants.

## Scope

Add:

- deterministic production harness module
- fixture input material
- source manifest
- source cards
- claim cards
- motif cards
- image cards
- risk cards
- canon/kernel packet
- artifact genome
- candidate lineage packet
- harness gate report
- CLI command
- tests

## Likely files

src/abi/modules/production_harness.py
tests/test_production_harness.py
tests/test_production_harness_cli.py
fixtures/production_harness/source_note.md
fixtures/production_harness/theory_fragment.md

Possible updates:

src/abi/cli.py
src/abi/controller/state.py
README.md

## CLI

Add a command such as:

abi harness demo

The command should:

- initialize or reuse the active run
- read deterministic fixture material
- create a unique run subfolder:
  runs/<run_id>/harness/<packet_id>/
- write artifacts
- register artifacts
- print JSON summary

## Required output packet

The benchmark run must produce:

1. source_manifest
2. source_cards
3. claim_cards
4. motif_cards
5. image_cards
6. risk_cards
7. canon_kernel
8. artifact_genome
9. candidate_lineage
10. harness_gate_report
11. harness_packet

## Tests

Tests must verify:

- all previous tests still pass
- deterministic pipeline output
- all required artifact types are produced
- all required artifacts are registered
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- active_phase becomes phase4_production_harness
- harness gate report exists
- controller/finalization still fail closed
- no model/API code is used

## Constraints

No model calls.
No production essay generation.
No human calibration.
No dashboard.
No SKILL.md.
No large orchestration framework.

## Done means

Phase 4 is complete when:

- python -m pytest passes
- ruff passes
- abi harness demo runs
- all Production Harness artifacts are stored and registered
- existing ear/reread/controller demos still work
- finalization remains fail closed
""",
)

write(
    "fixtures/production_harness/source_note.md",
    """
The artifact should begin from a concrete ordinary object and make the ending change the beginning.

The reader should not be told the theory first. The reader should encounter fragments, pressure, contradiction, and return.

The work should avoid generic mystical language, decorative symbolism, and thesis-summary closure.
""",
)

write(
    "fixtures/production_harness/theory_fragment.md",
    """
Symbolic abiogenesis means a symbolic system emerges from a germ.

For Abi, the machine process, artifact process, and reader process should share one pattern:

germ -> differentiation -> separation -> pressure -> crisis -> joining -> reread transformation.

The reader is not merely an evaluator. The reader is the final substrate in which the artwork instantiates itself.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 4 reads:",
    """
## Phase 4 reads:

For Phase 4, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
7. context/06_DATA_MODEL.md
8. context/08_GATES_AND_EVALUATION.md
9. context/09_PRODUCTION_HARNESS_SPEC.md
10. context/plans/PHASE_4_PRODUCTION_HARNESS.md

Phase 4 implements the deterministic Production Harness scaffold only.
""",
)

print("Phase 4 Production Harness context files created.")
print("Next:")
print("  git status")
print("  git add context fixtures setup_phase4_context.py")
print('  git commit -m "Add Phase 4 Production Harness frozen context"')
print("  git push")
