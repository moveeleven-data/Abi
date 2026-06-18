# Phase 7A: First Live Abi Ear Worker Spec

## Status

Phase 7A adds the first live model worker behind explicit opt-in.

This phase must remain narrow.

## Goal

Add one live model worker for Abi Ear germ analysis using the existing Phase 6B model-driver shape, normalized artifact envelopes, model-call records, and schema validation.

The live worker must prove that a real model output can enter Abi only through the validated model-call layer.

## Worker

Implement one live worker only:

Abi Ear Germ Analysis

Input:

The table is still there in the morning.

Output schema:

AbiEarGermAnalysisModelOutput or the existing equivalent from Phase 6B.

## Required behavior

The live worker must:

- require an explicit opt-in flag such as --allow-live-model
- require OPENAI_API_KEY from the environment
- refuse clearly if the opt-in flag is missing
- refuse clearly if OPENAI_API_KEY is missing
- use the existing model-call record infrastructure
- use schema validation before artifact registration
- register parsed model artifacts only after validation
- include model_call_id in accepted parsed artifact envelopes
- preserve raw output path / failure record behavior
- preserve finalization fail-closed behavior

## Required model integration constraints

Use an OpenAI client adapter or equivalent isolated module.

Do not let OpenAI-specific code spread into Abi Ear, Reread, Harness, Calibration, Controller, or Finalization.

The live adapter must be replaceable.

Use environment variables for secrets.

Never hard-code API keys.

Make the model configurable through environment variable or CLI option.

Suggested environment variables:

- OPENAI_API_KEY
- ABI_OPENAI_MODEL

## Required CLI behavior

Add a command such as:

abi model-driver live-demo --worker abi_ear_germ_analysis --allow-live-model

or an equivalent documented command.

The command must refuse unless --allow-live-model is present.

The command must not be called by existing deterministic demos.

Existing commands must remain deterministic:

- abi ear demo
- abi reread demo
- abi harness demo
- abi calibration demo
- abi model-driver demo

## Required tests

Tests must not require an API key.

Tests must use fake/stub live adapters, not network calls.

Tests must prove:

- missing --allow-live-model refuses before any client call
- missing OPENAI_API_KEY refuses before any client call
- live adapter success creates a valid model-call record
- live adapter success creates a parsed artifact with model_call_id
- live adapter schema failure records validation_failed and no parsed artifact
- live adapter client failure records client_failed and no parsed artifact
- deterministic demos still work
- fake model-driver demo still works
- finalization remains fail-closed

## Prohibited

- no automatic live model calls
- no real model call in tests
- no full Abi Ear replacement
- no live field model worker
- no live prose generation
- no live reread loop
- no agent loops
- no human calibration automation
- no finalization semantics change except preserving fail-closed behavior
- no architecture redesign
- no SKILL.md

## Acceptance criteria

Phase 7A is complete only when:

- ruff passes
- pytest passes
- all existing demos still work
- model-driver fake demo still works
- live command refuses without --allow-live-model
- live command refuses without OPENAI_API_KEY
- stubbed live adapter tests pass
- optional manual live smoke test succeeds when OPENAI_API_KEY is set
- accepted live output is registered with model_call_id
- finalization remains fail-closed
