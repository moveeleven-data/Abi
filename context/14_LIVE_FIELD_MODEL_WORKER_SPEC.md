# Phase 7B: Guarded Live Abi Ear Field Model Worker Spec

## Status

Phase 7B adds the second guarded live Abi Ear worker.

This phase must remain narrow.

## Goal

Add one live model worker for Abi Ear field-model building using the existing model-driver layer, normalized artifact envelopes, model-call records, and schema validation.

The worker should prove that a real or stubbed model can produce a field model artifact from a germ and/or germ-analysis packet, and that the result enters Abi only through validation and model-call recording.

## Worker

Implement one live worker only:

Abi Ear Field Model Builder

Input:

- benchmark germ: The table is still there in the morning.
- existing or supplied germ-analysis artifact/payload if available

Output schema:

AbiEarFieldModelOutput or equivalent.

Required payload concepts:

- germ_text
- objects
- local_laws
- latent_oppositions
- negative_space
- scale_ceiling
- forbidden_imports
- possible_returns
- risks

Keep schema compact. This is not full Abi Ear live generation.

## Required behavior

The live field-model worker must:

- require explicit opt-in flag such as --allow-live-model
- require OPENAI_API_KEY from the environment for real live call
- refuse clearly if opt-in flag is missing
- refuse clearly if OPENAI_API_KEY is missing
- use existing model-call record infrastructure
- use schema validation before artifact registration
- register parsed model artifacts only after validation
- include model_call_id in accepted parsed artifact envelopes
- preserve raw output path / failure record behavior
- preserve finalization fail-closed behavior
- not replace deterministic Abi Ear demo

## CLI behavior

Add a command such as:

abi model-driver live-demo --worker abi_ear_field_model --allow-live-model

or support worker selection through the existing live-demo command.

The command must refuse unless --allow-live-model is present.

Existing commands must remain deterministic:

- abi ear demo
- abi reread demo
- abi harness demo
- abi calibration demo
- abi model-driver demo

## Tests

Tests must not require an API key.

Tests must use fake/stub live adapters, not network calls.

Tests must prove:

- missing --allow-live-model refuses before client call
- missing OPENAI_API_KEY refuses before client call
- stubbed field-model success creates model-call record
- stubbed field-model success creates parsed artifact with model_call_id
- field-model schema failure records validation_failed and no parsed artifact
- field-model client failure records client_failed and no parsed artifact
- deterministic demos still work
- Phase 7A germ-analysis live-demo behavior still works
- finalization remains fail-closed

## Prohibited

- no automatic live model calls
- no real model call in tests
- no deterministic Abi Ear replacement
- no live move composer
- no live prose generation
- no live reread loop
- no agent loops
- no human calibration automation
- no finalization semantics change except preserving fail-closed behavior
- no architecture redesign
- no SKILL.md

## Acceptance criteria

Phase 7B is complete only when:

- ruff passes
- pytest passes
- all existing demos still work
- fake model-driver demo still works
- live germ-analysis command still refuses without opt-in
- live field-model command refuses without opt-in
- live field-model command refuses without OPENAI_API_KEY
- stubbed field-model tests pass
- accepted field-model output is registered with model_call_id
- finalization remains fail-closed
