# Phase 3 Fail-Closed Controller ExecPlan

## Goal

Implement the fail-closed controller expansion.

Phase 3 should make controller decisions explicit and make finalization policy-driven, inspectable, and tested.

## Scope

Add:

- controller decision object
- gate policy object or module
- blocker report
- controller status/demo CLI
- run status helpers if needed
- tests

## Likely files

src/abi/controller/decision.py
src/abi/controller/policy.py
src/abi/controller/blockers.py
src/abi/controller/finalization.py updates
src/abi/controller/state.py updates
src/abi/cli.py updates
tests/test_controller_decisions.py
tests/test_controller_cli.py

## CLI

Add commands such as:

abi controller status
abi controller blockers
abi controller demo

The command should:

- inspect active run
- inspect gates
- return structured JSON
- refuse finalization when required gates are missing or failed

## Tests

Tests must verify:

- all previous tests still pass
- missing required gates create a refuse_finalization decision
- failed required gates create a refuse_finalization decision
- blocking defects create a refuse_finalization decision
- all required gates passing creates an eligible decision in a controlled unit test
- live/demo finalization still refuses unless required finalization gates are actually satisfied
- CLI emits valid JSON

## Constraints

No model calls.
No production generation.
No Phase 4 source harness.
No human calibration.
No SKILL.md.
No large orchestration framework.

## Done means

Phase 3 is complete when:

- python -m pytest passes
- ruff passes
- controller CLI works
- controller emits structured blocker reports
- finalization remains fail-closed
- Phase 0/1/2 demos still work
