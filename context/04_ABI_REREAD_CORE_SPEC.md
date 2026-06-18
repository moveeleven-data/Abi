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
→ diagnosed failure
→ targeted intervention
→ counterfactual proof

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
