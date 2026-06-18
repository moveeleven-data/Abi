# Phase 12 Finalization Gate Policy v2 ExecPlan

## Goal

Upgrade finalization policy from Phase 0 placeholder gates to real project release-readiness gates.

The purpose is better refusal, not completion.

## Scope

Add:

- gate profile definitions
- gate catalog
- release readiness report
- finalization status CLI
- gate list CLI
- finalization profile support
- tests

## Likely files

Likely updated:

src/abi/controller/policy.py
src/abi/controller/finalization.py
src/abi/controller/control.py
src/abi/cli.py
README.md

Possible new:

src/abi/controller/gate_catalog.py
src/abi/controller/release_readiness.py
tests/test_finalization_profiles.py
tests/test_gate_catalog_cli.py

## CLI

Add or update:

abi gate list
abi finalization status
abi finalization status --profile final_artifact
abi finalize --profile final_artifact

Existing `abi finalize` must remain fail-closed.

## Tests

Tests must verify:

- all previous tests still pass
- current fixture/evaluation state refuses final_artifact profile
- fixture-only evidence blocks final_artifact profile
- non-final candidate blocks final_artifact profile
- missing real human validation blocks final_artifact profile
- missing strongest-rival comparison blocks final_artifact profile
- missing raw-model baseline comparison blocks final_artifact profile
- missing hostile final audit blocks final_artifact profile
- gate list emits JSON
- finalization status emits JSON
- controlled all-gates-passed test can become eligible
- existing finalize remains fail-closed

## Done means

Phase 12 is done when finalization refusal is mature and project-relevant, but still refuses current runs.
