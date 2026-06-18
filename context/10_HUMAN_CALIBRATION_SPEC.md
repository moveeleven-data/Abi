# Human Calibration / Paper-Grade Evaluation Spec

## Phase 5 status

Phase 5 implements the deterministic Human Calibration and Paper-Grade Evaluation scaffold.

No model calls are allowed in Phase 5.

Phase 5 does not run real human studies yet. It creates the artifact structure, protocols, fixture traces, baseline comparison scaffolds, and evaluation reports needed for later real human calibration.

## Goal

Create a deterministic evaluation scaffold that can represent:

1. human-reader protocol
2. reader trial fixture
3. first-read trace
4. reread trace
5. reader-state transition
6. blind comparison fixture
7. baseline comparison fixture
8. calibration summary
9. paper-grade evaluation report
10. calibration gate report
11. calibration packet summary

The purpose is to make the reader a first-class substrate in the repo, not just a conceptual claim.

## Core principle

Artwork = Artifact + ΔReaderState

Phase 5 must represent ΔReaderState explicitly.

The calibration scaffold should test whether the artifact caused a reader-state transformation, not merely whether the reader liked the text.

## Required artifact types

- calibration_protocol
- calibration_human_reader_trial
- calibration_first_read_trace
- calibration_reread_trace
- calibration_reader_state_transition
- calibration_blind_comparison
- calibration_baseline_comparison
- calibration_summary
- calibration_evaluation_report
- calibration_gate_report
- calibration_packet

Each artifact must be registered through the Phase 0 artifact registry.

## Required CLI behavior

Add a command similar to:

abi calibration demo

It should:

- ensure a run exists
- use deterministic fixture inputs from fixtures/human_calibration/
- create a unique packet directory under runs/<run_id>/calibration/<packet_id>/
- write all Phase 5 artifacts as JSON
- register all artifacts in SQLite
- update active_phase to phase5_human_calibration
- print a compact JSON summary with run_id, packet_id, artifact IDs, and gate result

## Determinism

Phase 5 outputs must not depend on API calls, randomness, clock time except artifact metadata, or external files not in the repo.

## Required evaluation concepts

### Human reader protocol

Defines what a human reader should report:

- first-read memory
- opening interpretation
- retained images
- predictions
- attention drops
- confusion
- overexplicitness
- post-ending opening reread
- changed interpretation
- paraphrase attempt
- details that gained force
- details that felt fake

### Reader-state transition

Represents the change from R1 to R2:

- before_state
- after_state
- changed_opening_interpretation
- newly_connected_fragments
- motif_role_changes
- paraphrase_loss
- unsupported_depth_flags

### Blind comparison

Represents a comparison between two artifacts without revealing which came from Abi.

### Baseline comparison

Represents comparison against direct prompt, best-of-N, or prior draft baselines.

Phase 5 may use deterministic fixture baselines only.

## Prohibited in Phase 5

- no OpenAI API calls
- no real model_driver behavior
- no live human study collection UI
- no external survey integration
- no dashboard
- no large orchestration framework
- no SKILL.md
- no production essay generation
- no claims of validated human success from fixture data

## Acceptance criteria

Phase 5 is complete only when:

- all previous tests pass
- abi calibration demo runs locally
- all required Phase 5 artifact types are produced
- artifacts are registered with hashes and parent IDs
- packet directories are immutable and non-overwriting
- active_phase becomes phase5_human_calibration
- a calibration gate report is produced
- controller still refuses finalization unless required finalization gates are satisfied
