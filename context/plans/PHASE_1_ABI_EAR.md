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
