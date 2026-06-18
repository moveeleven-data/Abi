# Phase 6A-lite Model-Readiness Consolidation ExecPlan

## Goal

Make the deterministic Abi runtime ready for future model-produced artifacts.

This is a surgical consolidation phase, not a broad cleanup phase.

## Scope

Add:

- shared packet-writing helper
- normalized artifact envelope helper
- artifact list/show CLI
- run list/show/latest CLI
- tests

Refactor only enough deterministic packet code to prove the helper works.

## Likely files

Likely new files:

src/abi/packets.py
tests/test_packets.py
tests/test_artifact_cli.py
tests/test_run_cli.py

Likely updated files:

src/abi/cli.py
src/abi/modules/abi_ear.py
one or more of:
  src/abi/modules/reread.py
  src/abi/modules/production_harness.py
  src/abi/modules/human_calibration.py
README.md

## CLI requirements

Add:

abi artifact list
abi artifact show <artifact_id>
abi run list
abi run show <run_id>
abi run latest

All commands emit JSON.

## Packet helper requirements

The helper should support:

- unique packet directory creation
- artifact JSON writing
- artifact registry integration
- artifact path return
- parent ID preservation
- normalized envelope

Required envelope fields:

- schema_version
- artifact_type
- run_id
- lineage_id
- parent_ids
- created_by
- fixture_only
- model_call_id
- payload

## Tests

Tests must verify:

- all previous tests still pass
- packet helper writes a normalized envelope
- packet helper registers artifacts
- packet helper creates unique packet directories
- Abi Ear uses the packet helper
- at least one other deterministic packet module uses the packet helper
- schema_version appears in registered packet artifacts
- model_call_id is null in deterministic artifacts
- artifact list returns registered artifacts
- artifact show returns one artifact by ID
- run list returns runs
- run show returns one run by ID
- run latest returns the latest run
- all demos still work
- finalize remains fail-closed

## Constraints

Do not implement model calls.
Do not implement model_driver.py.
Do not implement fake model clients yet.
Do not add creative generation.
Do not add dev reset.
Do not do broad refactoring.

## Done means

Phase 6A-lite is complete when:

- python -m ruff check . passes
- python -m pytest passes
- abi artifact list works
- abi artifact show <artifact_id> works
- abi run list works
- abi run show <run_id> works
- abi run latest works
- existing controller/ear/reread/harness/calibration demos still work
- abi finalize remains fail-closed
