# Phase 2 Minimal Abi Reread ExecPlan

## Goal

Implement the smallest deterministic reread compiler loop.

Phase 2 should prove the architecture can represent:

reader-state trace
→ diagnosed failure
→ targeted intervention
→ counterfactual proof

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
