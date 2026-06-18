# Phase 8 Live Abi Ear Packet ExecPlan

## Goal

Implement the guarded live Abi Ear packet pipeline.

This phase should convert the isolated live Abi Ear workers into a complete local Abi Ear packet while preserving deterministic behavior.

## Scope

Add:

- live Abi Ear packet orchestrator
- fake-client packet path
- optional guarded OpenAI packet path
- schemas for remaining Abi Ear packet outputs if needed
- model-call record reuse
- artifact registry integration
- max model-call guard
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/live_abi_ear.py
tests/test_live_abi_ear_packet.py
tests/test_live_abi_ear_cli.py

Likely updated files:

src/abi/cli.py
src/abi/model_schemas.py
src/abi/live_model.py
src/abi/model_driver.py
README.md

## CLI

Preferred command:

abi ear live-demo --client fake

Optional real live path:

abi ear live-demo --client openai --allow-live-model --max-model-calls 8

The fake path must use fake/stubbed model clients and require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Tests

Tests must verify:

- all previous tests still pass
- deterministic `abi ear demo` remains unchanged
- fake live Abi Ear packet succeeds
- fake live packet produces required artifact types
- fake live packet registers model_call_id on parsed model artifacts
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- max-call budget is enforced
- openai client path refuses without --allow-live-model
- openai client path refuses without OPENAI_API_KEY
- invalid fake output records validation_failed and creates no parsed artifact
- client failure records client_failed and creates no parsed artifact
- finalization remains fail-closed

## Manual live smoke test

Manual OpenAI live packet smoke test is optional and should not be run by Codex.

It should require:

- OPENAI_API_KEY set
- --allow-live-model passed
- max model calls explicitly set

## Done means

Phase 8 is done when a full Abi Ear packet can be generated through fake model-shaped workers, all outputs are registered and inspectable, and the guarded OpenAI path is available but not automatic.
