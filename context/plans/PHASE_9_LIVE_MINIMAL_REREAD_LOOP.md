# Phase 9 Live Minimal Reread Loop ExecPlan

## Goal

Implement the guarded live-shaped Minimal Reread loop.

This phase should convert the deterministic Minimal Reread loop into a fake-model/live-guarded packet while preserving deterministic behavior.

## Scope

Add:

- live Minimal Reread packet orchestrator
- fake-client packet path
- optional guarded OpenAI packet path
- schemas for Minimal Reread outputs if needed
- model-call record reuse
- artifact registry integration
- max model-call guard
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/live_reread.py
tests/test_live_reread_packet.py
tests/test_live_reread_cli.py

Likely updated files:

src/abi/cli.py
src/abi/model_schemas.py
src/abi/live_model.py
src/abi/model_driver.py
README.md

## CLI

Preferred command:

abi reread live-demo --client fake

Optional real live path:

abi reread live-demo --client openai --allow-live-model --max-model-calls 12

The fake path must use fake/stubbed model clients and require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Required output packet

The live minimal reread packet must produce:

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
- deterministic `abi reread demo` remains unchanged
- fake live Minimal Reread packet succeeds
- fake live packet produces required artifact types
- fake live packet registers model_call_id on parsed model artifacts
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- max-call budget is enforced
- openai client path refuses without --allow-live-model
- openai client path refuses without OPENAI_API_KEY
- invalid fake output records validation_failed and creates no parsed artifact
- client failure records client_failed and creates no parsed artifact
- counterfactual result exists
- finalization remains fail-closed

## Manual live smoke test

Manual OpenAI live reread smoke test is optional and should not be run by Codex.

It should require:

- OPENAI_API_KEY set
- --allow-live-model passed
- max model calls explicitly set

## Done means

Phase 9 is done when a minimal reread packet can be generated through fake model-shaped workers, all outputs are registered and inspectable, and the guarded OpenAI path is available but not automatic.
