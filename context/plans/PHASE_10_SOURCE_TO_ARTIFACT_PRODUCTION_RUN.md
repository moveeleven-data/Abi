# Phase 10 Source-to-Artifact Production Run ExecPlan

## Goal

Implement the first bounded source-to-artifact production run.

This phase connects the existing production harness, live Abi Ear packet, and live Minimal Reread loop into a single candidate-artifact packet.

## Scope

Add:

- production run orchestrator
- fake-client production run path
- optional guarded OpenAI production run path
- candidate artifact packet
- production run report
- production gate report
- max model-call budget guard
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/production_run.py
tests/test_production_run.py
tests/test_production_run_cli.py

Likely updated files:

src/abi/cli.py
src/abi/controller/state.py
README.md

Possible updates if needed:

src/abi/modules/live_abi_ear.py
src/abi/modules/live_reread.py

## CLI

Preferred command:

abi production live-demo --client fake

Optional real live path:

abi production live-demo --client openai --allow-live-model --max-model-calls 24

The fake path must use fake/stubbed model clients and require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Required output packet

The production run packet must expose:

1. source_manifest
2. harness_packet_ref
3. selected_germ
4. target_effect
5. live_abi_ear_packet_ref
6. live_reread_packet_ref
7. candidate_artifact
8. candidate_report
9. production_gate_report
10. production_packet

The candidate artifact must be marked:

- non_final: true
- fixture_only or source_fixture where appropriate
- not_human_validated: true
- not_finalization_eligible: true

## Tests

Tests must verify:

- all previous tests still pass
- deterministic demos remain unchanged
- fake production live-demo succeeds
- fake production packet produces required concepts
- production packet references harness, live Abi Ear, and live Reread packets
- candidate artifact exists and is marked non-final
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- max-call budget is enforced
- openai client path refuses without --allow-live-model
- openai client path refuses without OPENAI_API_KEY
- finalization remains fail-closed

## Manual live smoke test

Manual OpenAI production smoke test is optional and should not be run by Codex.

It should require:

- OPENAI_API_KEY set
- --allow-live-model passed
- max model calls explicitly set

## Done means

Phase 10 is done when a source-to-candidate production packet can be generated through fake model-shaped workers, all outputs are registered and inspectable, and the guarded OpenAI path is available but not automatic.
