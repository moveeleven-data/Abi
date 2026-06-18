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
    "context/03_ABI_EAR_V1_SPEC.md",
    """
# Abi Ear v1 Spec

## Phase 1 status

Phase 1 implements Abi Ear v1 with deterministic/stub workers first.

No model calls are allowed in Phase 1.

Abi Ear is the local literary perception layer. It tests whether a concrete germ can generate a field, moves, candidate inventions, reread transformation, and ablation-sensitive proof.

## Benchmark input

The required benchmark input is:

The table is still there in the morning.

## Phase 1 goal

Given the benchmark input, Abi Ear must produce a complete local artifact packet:

1. word-level germ analysis
2. ten variants
3. field model
4. twenty moves
5. ranked move sequence
6. three prose inventions
7. one refined invention
8. reread trace
9. word/move ablation report
10. gate report

All outputs must be deterministic in Phase 1.

## Required artifact types

- abi_ear_germ_analysis
- abi_ear_variants
- abi_ear_field_model
- abi_ear_moves
- abi_ear_ranked_move_sequence
- abi_ear_prose_inventions
- abi_ear_refined_invention
- abi_ear_reread_trace
- abi_ear_ablation_report
- abi_ear_gate_report
- abi_ear_packet

Each artifact must be registered through the Phase 0 artifact registry.

## Required CLI behavior

Phase 1 should add a CLI path similar to:

abi ear demo

It should:

- ensure a run exists
- run the deterministic Abi Ear benchmark
- write JSON artifacts under the current run folder
- register artifacts in SQLite
- print a compact JSON summary with run_id, artifact IDs, and gate result

If Codex chooses a slightly different command, tests must document it.

## Determinism

Phase 1 outputs must not depend on API calls, randomness, clock time except artifact metadata, or external files not in the repo.

## Prohibited in Phase 1

- no OpenAI API calls
- no real model_driver behavior
- no reader-agent framework
- no production harness
- no full essay generation
- no human calibration UI
- no large orchestration framework
- no SKILL.md

## Acceptance criteria

Phase 1 is complete only when:

- tests pass
- Abi Ear benchmark command runs locally
- all required artifact types are produced
- artifacts are registered with hashes and parent IDs
- a gate report is produced
- the gate report evaluates the local benchmark, not final project success
- finalization still refuses unless required Phase 0 gates are satisfied
""",
)

write(
    "context/07_PROMPT_CONTRACTS.md",
    """
# Prompt and Worker Contracts

Phase 1 uses deterministic worker functions, not model prompts.

The contracts still matter because future model workers must preserve the same input/output boundaries.

## Abi Ear worker contracts

### Germ Analyzer

Input:

- germ text

Output:

- word_forces
- future_opened
- risks
- fertility_score

### Variant Generator

Input:

- germ text
- germ analysis

Output:

- ten variants
- short rationale for each
- predicted field shift

### Field Model Builder

Input:

- selected germ
- germ analysis

Output:

- objects
- local laws
- latent oppositions
- negative space
- scale ceiling
- forbidden imports
- possible returns

### Move Composer

Input:

- germ
- field model

Output:

- twenty moves
- parent material
- operation name
- new material
- predicted field delta
- pressure delta
- derivation distance
- return payoff
- risk

### Retrospective Inevitability Judge

Input:

- moves
- field model

Output:

- ranked move sequence
- score for surprise-before / necessity-after
- risks

### Development Composer

Input:

- germ
- field model
- ranked move sequence

Output:

- three short prose inventions
- one refined invention

### Reread Tracer

Input:

- refined invention
- germ
- field model

Output:

- first-read opening interpretation
- second-read opening interpretation
- changed opening words
- supporting lines or passages
- reread gain estimate
- unsupported claims

### Ablation Reporter

Input:

- refined invention
- germ
- selected moves
- reread trace

Output:

- tested removals/replacements
- predicted effect loss
- verdict per ablation

### Gate Evaluator

Input:

- full Abi Ear packet

Output:

- passed
- blocking defects
- gate scores
- summary verdict

## Role separation

Even with deterministic stubs, keep functions separated by role.

Do not create one monolithic function that fabricates the whole packet without preserving intermediate artifacts.
""",
)

write(
    "context/plans/PHASE_1_ABI_EAR.md",
    """
# Phase 1 Abi Ear ExecPlan

## Goal

Implement Abi Ear v1 as a deterministic local pipeline using the benchmark sentence:

The table is still there in the morning.

## Scope

Add:

- Abi Ear module
- deterministic worker functions
- simple schemas or validation helpers
- JSON artifact writing
- artifact registry integration
- CLI command for the benchmark
- tests

## Expected implementation files

Likely files:

src/abi/modules/abi_ear.py
src/abi/modules/__init__.py
src/abi/controller/gates.py updates if needed
tests/test_abi_ear.py
tests/test_abi_ear_cli.py

Optional files:

src/abi/schemas.py
src/abi/jsonio.py
fixtures/abi_ear/table_still_morning.txt

## Required output packet

The benchmark run must produce:

1. germ_analysis
2. variants
3. field_model
4. moves
5. ranked_move_sequence
6. prose_inventions
7. refined_invention
8. reread_trace
9. ablation_report
10. gate_report
11. packet summary

## CLI

Add a command such as:

abi ear demo

The command should:

- initialize or reuse the active run
- create a run subfolder if needed
- write artifacts under runs/<run_id>/abi_ear/
- register all artifacts in SQLite
- print JSON summary

## Testing

Tests must verify:

- deterministic pipeline output
- exactly ten variants
- exactly twenty moves
- at least three prose inventions
- one refined invention
- all required artifact types registered
- parent IDs are populated where appropriate
- gate report exists
- no model/API code is called
- existing Phase 0 tests still pass

## Constraints

No model calls.
No prose-generation API.
No reader simulation framework.
No production harness.
No Phase 2 reread loop.
No SKILL.md.

## Done means

Phase 1 context is satisfied when:

- python -m pytest passes
- abi ear demo runs
- all Abi Ear artifacts are stored and registered
- the final gate report exists
- Phase 0 finalization refusal still works
""",
)

write(
    "fixtures/abi_ear/table_still_morning.txt",
    """
The table is still there in the morning.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 1 reads:",
    """
## Phase 1 reads:

For Phase 1, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/03_ABI_EAR_V1_SPEC.md
7. context/06_DATA_MODEL.md
8. context/07_PROMPT_CONTRACTS.md
9. context/08_GATES_AND_EVALUATION.md
10. context/plans/PHASE_1_ABI_EAR.md

Phase 1 implements Abi Ear v1 with deterministic/stub workers only.
""",
)

print("Phase 1 Abi Ear context files created.")
print("Next:")
print("  git status")
print("  git add context fixtures setup_phase1_context.py")
print('  git commit -m "Add Phase 1 Abi Ear frozen context"')
print("  git push")
