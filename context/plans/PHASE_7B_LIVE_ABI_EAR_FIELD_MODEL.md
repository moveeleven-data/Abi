# Phase 7B Live Abi Ear Field Model ExecPlan

## Goal

Implement the second guarded live Abi Ear worker through the sealed model-driver layer.

This phase adds field-model live-worker support only.

## Scope

Add:

- AbiEarFieldModelOutput schema
- live worker handling for abi_ear_field_model
- fake/stub tests for field-model success/failure
- CLI worker selection support if needed
- model-call record reuse
- schema validation reuse
- documentation

## Likely files

Likely updated files:

src/abi/live_model.py
src/abi/openai_adapter.py
src/abi/model_schemas.py
src/abi/model_driver.py
src/abi/cli.py
tests/test_live_model.py
README.md

Optional new tests:

tests/test_live_field_model.py

## Dependency policy

No test should require OPENAI_API_KEY.

No real live call should be run by Codex.

OpenAI SDK should remain optional.

## CLI

Support a command such as:

abi model-driver live-demo --worker abi_ear_field_model --allow-live-model

The command must:

- refuse if --allow-live-model is absent
- refuse if OPENAI_API_KEY is absent
- use ABI_OPENAI_MODEL or documented default
- call only the field-model worker when that worker is requested
- validate output before artifact registration
- print JSON summary

## Tests

Tests must verify:

- all previous tests still pass
- missing opt-in flag refuses for field model
- missing API key refuses for field model
- stubbed field-model success creates model-call record
- stubbed field-model success creates parsed artifact
- parsed artifact envelope has non-null model_call_id
- validation failure creates validation_failed record and no parsed artifact
- client failure creates client_failed record and no parsed artifact
- deterministic demos are unchanged
- germ-analysis live-demo behavior still works
- finalization remains fail-closed

## Manual live smoke test

Manual live smoke test is optional.

It should require:

- OPENAI_API_KEY set in environment
- --allow-live-model passed explicitly

It should produce one real parsed artifact for Abi Ear field model only.

## Done means

Phase 7B is done when the system has two guarded live Abi Ear worker paths:

- abi_ear_germ_analysis
- abi_ear_field_model

and all normal deterministic behavior remains unchanged.
