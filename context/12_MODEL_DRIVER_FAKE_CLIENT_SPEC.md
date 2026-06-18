# Phase 6B: Model Driver + Structured Outputs Fake Client Spec

## Status

Phase 6B implements the sealed model-call layer using fake clients only.

No real model/API calls are allowed.

No API key may be required.

No live model workers are allowed.

No creative generation is allowed.

Do not redesign the architecture.

## Goal

Build the model-call layer that will later support live Structured Outputs while proving, with fake clients, that model-shaped outputs can be accepted, validated, rejected, wrapped, registered, inspected, and linked to model_call_id without weakening fail-closed control.

This phase is not about making Abi smart. It is about making future model intelligence unable to corrupt Abi.

## Required components

### Model driver interface

Add a narrow model-driver layer.

Suggested files:

- src/abi/model_driver.py
- src/abi/model_schemas.py or src/abi/schemas.py
- src/abi/model_calls.py if useful

Use existing repo conventions after inspection.

### Core records

Define structures equivalent to:

- WorkerRequest
- WorkerRole
- WorkerSchema
- ModelDriverResult
- ModelCallRecord
- ModelValidationError

Each model call record should include:

- model_call_id
- run_id
- worker_role
- prompt_contract_id
- input_artifact_ids or input_packet_path
- input_hash
- schema_name
- schema_version
- provider
- model
- raw_output_path
- parsed_output_artifact_id nullable
- status: success / validation_failed / client_failed
- error_message nullable
- created_at
- token/cost fields nullable for now

### Fake model client

The fake client must support:

- valid structured output
- invalid JSON or malformed structured output
- schema-valid but semantically minimal output
- simulated client failure

No network calls.

### Validation before registration

A fake model output may become a registered parsed artifact only after it passes schema validation.

Invalid fake output must be rejected and must not create a parsed output artifact.

The failed call must still be recorded as a model-call record or failure report.

### Envelope usage

Any parsed model artifact must use the normalized envelope:

- schema_version
- artifact_type
- run_id
- lineage_id nullable
- parent_ids
- created_by
- fixture_only nullable
- model_call_id
- payload

### Narrow example schema

Add one narrow example schema, such as:

AbiEarGermAnalysisModelOutput

It should use fake data only.

Do not replace deterministic Abi Ear behavior.

Do not add Abi Ear live behavior.

## Optional CLI

Add minimal commands if useful:

- abi model-call list
- abi model-call show MODEL_CALL_ID
- abi model-driver demo

The demo must use fake client only.

## Tests required

Tests must prove:

- valid fake structured output is accepted
- invalid fake output is rejected
- invalid fake output does not register a parsed artifact
- model_call_id is present on accepted parsed artifacts
- model call record stores input hash, schema name/version, worker role, provider/model placeholders, status, and paths
- no network/API key is required
- existing artifact list/show works for model-produced parsed artifacts
- existing demos still work
- finalization remains fail-closed

## Prohibited

- no real OpenAI API calls
- no API key required
- no live model workers
- no creative generation
- no Abi Ear live behavior
- no agent loops
- no finalization semantics change except preserving fail-closed behavior
- no architecture redesign
- no SKILL.md
