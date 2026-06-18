# Gates and Evaluation

Phase 0 implements gate infrastructure, not literary gates.

## Finalization invariant

A run cannot finalize unless every required gate:

- exists
- has been evaluated
- passed
- has no fatal blocking defects

## Phase 0 required gates

For fake-run finalization refusal, use placeholder required gates:

- infrastructure_initialized
- artifact_registry_ready
- required_phase0_tests_passed

The controller/finalization code must refuse finalization when any required gate is missing or failed.

## Blocker report

Finalization refusal must return or print:

- run_id
- refused: true
- missing_gates
- failed_gates
- message
