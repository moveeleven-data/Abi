# Phase 4 Production Harness ExecPlan

## Goal

Implement the deterministic production harness scaffold.

Phase 4 should prove that Abi can ingest source-like material into structured production artifacts while preserving the existing fail-closed controller and artifact registry invariants.

## Scope

Add:

- deterministic production harness module
- fixture input material
- source manifest
- source cards
- claim cards
- motif cards
- image cards
- risk cards
- canon/kernel packet
- artifact genome
- candidate lineage packet
- harness gate report
- CLI command
- tests

## Likely files

src/abi/modules/production_harness.py
tests/test_production_harness.py
tests/test_production_harness_cli.py
fixtures/production_harness/source_note.md
fixtures/production_harness/theory_fragment.md

Possible updates:

src/abi/cli.py
src/abi/controller/state.py
README.md

## CLI

Add a command such as:

abi harness demo

The command should:

- initialize or reuse the active run
- read deterministic fixture material
- create a unique run subfolder:
  runs/<run_id>/harness/<packet_id>/
- write artifacts
- register artifacts
- print JSON summary

## Required output packet

The benchmark run must produce:

1. source_manifest
2. source_cards
3. claim_cards
4. motif_cards
5. image_cards
6. risk_cards
7. canon_kernel
8. artifact_genome
9. candidate_lineage
10. harness_gate_report
11. harness_packet

## Tests

Tests must verify:

- all previous tests still pass
- deterministic pipeline output
- all required artifact types are produced
- all required artifacts are registered
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- active_phase becomes phase4_production_harness
- harness gate report exists
- controller/finalization still fail closed
- no model/API code is used

## Constraints

No model calls.
No production essay generation.
No human calibration.
No dashboard.
No SKILL.md.
No large orchestration framework.

## Done means

Phase 4 is complete when:

- python -m pytest passes
- ruff passes
- abi harness demo runs
- all Production Harness artifacts are stored and registered
- existing ear/reread/controller demos still work
- finalization remains fail closed
