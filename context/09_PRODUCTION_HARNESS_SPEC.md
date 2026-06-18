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
