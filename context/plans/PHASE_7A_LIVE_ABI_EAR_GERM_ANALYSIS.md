# Phase 7A Live Abi Ear Germ Analysis ExecPlan

## Goal

Implement the first live model worker through the sealed model-driver layer.

This phase tests one live Structured Outputs path only.

## Scope

Add:

- OpenAI client adapter or live client interface
- live Abi Ear germ analysis worker command
- explicit --allow-live-model guard
- environment-variable checks
- schema validation reuse
- model-call record reuse
- tests with fake/stub live adapters
- optional manual live smoke path

## Likely files

Likely new files:

src/abi/live_model.py
src/abi/openai_adapter.py
tests/test_live_model_adapter.py
tests/test_live_worker_cli.py

Likely updated files:

src/abi/cli.py
src/abi/model_driver.py
src/abi/model_schemas.py
README.md
pyproject.toml, only if adding optional live dependency

## Dependency policy

Do not make OpenAI SDK required for deterministic tests.

Acceptable options:

1. Add an optional dependency group such as [project.optional-dependencies].live = ["openai>=..."], and import it lazily.
2. Avoid adding dependency until manual live test, but keep adapter isolated.

No test should require OPENAI_API_KEY.

## CLI

Add a command such as:

abi model-driver live-demo --worker abi_ear_germ_analysis --allow-live-model

The command must:

- refuse if --allow-live-model is absent
- refuse if OPENAI_API_KEY is absent
- use ABI_OPENAI_MODEL or a documented default model
- call only the one germ-analysis worker
- validate output before artifact registration
- print JSON summary

## Tests

Tests must verify:

- all previous tests still pass
- missing opt-in flag refuses
- missing API key refuses
- stubbed live success creates model-call record
- stubbed live success creates parsed artifact
- parsed artifact envelope has non-null model_call_id
- validation failure creates validation_failed record and no parsed artifact
- client failure creates client_failed record and no parsed artifact
- deterministic demos are unchanged
- finalization remains fail-closed

## Manual live smoke test

Manual live smoke test is optional but recommended after tests pass.

It should require:

- OPENAI_API_KEY set in environment
- --allow-live-model passed explicitly

It should produce one real parsed artifact for Abi Ear germ analysis.

## Done means

Phase 7A is done when the system has one guarded live model worker path and all normal deterministic behavior remains unchanged.
