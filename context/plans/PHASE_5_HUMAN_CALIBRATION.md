# Phase 5 Human Calibration ExecPlan

## Goal

Implement the deterministic Human Calibration / Paper-Grade Evaluation scaffold.

Phase 5 should prove that Abi can represent reader-state transformation, blind comparison, and baseline comparison as first-class artifacts.

## Scope

Add:

- deterministic calibration module
- fixture human reader protocol
- fixture human reader trace
- fixture baseline artifact
- reader-state transition artifact
- blind comparison artifact
- baseline comparison artifact
- calibration summary
- paper-grade evaluation report
- calibration gate report
- CLI command
- tests

## Likely files

src/abi/modules/human_calibration.py
tests/test_human_calibration.py
tests/test_human_calibration_cli.py
fixtures/human_calibration/protocol.md
fixtures/human_calibration/human_reader_trial.json
fixtures/human_calibration/baseline_direct_prompt.md

Possible updates:

src/abi/cli.py
src/abi/controller/state.py
README.md

## CLI

Add a command such as:

abi calibration demo

The command should:

- initialize or reuse the active run
- read deterministic fixture material
- create a unique run subfolder:
  runs/<run_id>/calibration/<packet_id>/
- write artifacts
- register artifacts
- print JSON summary

## Required output packet

The benchmark run must produce:

1. calibration_protocol
2. calibration_human_reader_trial
3. calibration_first_read_trace
4. calibration_reread_trace
5. calibration_reader_state_transition
6. calibration_blind_comparison
7. calibration_baseline_comparison
8. calibration_summary
9. calibration_evaluation_report
10. calibration_gate_report
11. calibration_packet

## Tests

Tests must verify:

- all previous tests still pass
- deterministic pipeline output
- all required artifact types are produced
- all required artifacts are registered
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- active_phase becomes phase5_human_calibration
- calibration gate report exists
- controller/finalization still fail closed
- no model/API code is used
- fixture data is clearly marked as fixture data and not real validation

## Constraints

No model calls.
No live human survey UI.
No production essay generation.
No dashboard.
No SKILL.md.
No large orchestration framework.

## Done means

Phase 5 is complete when:

- python -m pytest passes
- ruff passes
- abi calibration demo runs
- all calibration artifacts are stored and registered
- existing controller/ear/reread/harness demos still work
- finalization remains fail closed
