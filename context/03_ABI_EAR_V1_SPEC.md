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
