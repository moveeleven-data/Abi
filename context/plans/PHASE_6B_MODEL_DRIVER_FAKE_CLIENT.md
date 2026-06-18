# Phase 6B Model Driver + Structured Outputs Fake Client ExecPlan

## Goal

Implement the fake-client model-driver layer.

This phase creates the sealed socket where future live model calls will plug in.

It must use fake clients only.

## Scope

Add:

- model-driver interface
- fake model client
- schema validation helper
- model call records
- one narrow example schema
- parsed artifact registration after validation
- failure record for invalid/client-failed calls
- optional model-call inspection CLI
- tests

## Likely files

Likely new files:

src/abi/model_driver.py
src/abi/model_schemas.py
src/abi/model_calls.py
tests/test_model_driver.py
tests/test_model_schema_validation.py

Possible updates:

src/abi/cli.py
src/abi/packets.py
src/abi/artifacts.py
README.md

## Example schema

Use a narrow fake schema such as:

AbiEarGermAnalysisModelOutput

Required fields may include:

- germ_text
- word_forces
- fertility_score
- risks

Keep it small. This is not live Abi Ear.

## CLI

Preferred optional commands:

- abi model-driver demo
- abi model-call list
- abi model-call show MODEL_CALL_ID

All commands emit JSON.

If CLI is added, tests must cover it.

## Tests

Tests must verify:

- valid fake output passes validation
- invalid JSON or malformed output fails validation
- schema-valid minimal output passes structural validation
- simulated client failure records client_failed
- invalid output does not create parsed artifact
- valid output creates parsed artifact
- parsed artifact uses normalized envelope
- parsed artifact has model_call_id
- model call record includes required metadata
- no API key required
- no network calls
- artifact list/show can inspect parsed model artifact
- all existing demos still pass
- finalization remains fail-closed

## Acceptance criteria

Phase 6B is complete only when:

- ruff passes
- pytest passes
- controller demo works
- ear demo works
- reread demo works
- harness demo works
- calibration demo works
- artifact list/show works
- run list/show/latest works
- model-driver fake demo works if added
- no real OpenAI network call code is active
- no API key is required
- no live model worker is added
- finalize still refuses as expected

## Done means

Phase 6B is done when the system can accept, validate, reject, register, and inspect model-shaped fake outputs through the model-driver layer while preserving fail-closed behavior.
