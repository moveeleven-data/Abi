from pathlib import Path

ROOT = Path.cwd()


def write(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip() + "\n", encoding="utf-8")


def append_once(path: str, marker: str, text: str) -> None:
    p = ROOT / path
    current = p.read_text(encoding="utf-8") if p.exists() else ""
    if marker not in current:
        p.write_text(current.rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8")


write(
    "context/12_MODEL_DRIVER_FAKE_CLIENT_SPEC.md",
    """
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
""",
)

write(
    "context/plans/PHASE_6B_MODEL_DRIVER_FAKE_CLIENT.md",
    """
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
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 6B reads:",
    """
## Phase 6B reads:

For Phase 6B, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
7. context/06_DATA_MODEL.md
8. context/08_GATES_AND_EVALUATION.md
9. context/11_MODEL_READINESS_CONSOLIDATION_SPEC.md
10. context/12_MODEL_DRIVER_FAKE_CLIENT_SPEC.md
11. context/plans/PHASE_6B_MODEL_DRIVER_FAKE_CLIENT.md

Phase 6B implements Model Driver + Structured Outputs with fake client tests only.
""",
)

print("Phase 6B Model Driver fake-client context files created.")
print("Next:")
print("  git status")
print("  git add context tools/setup_context_scripts/setup_phase6b_context.py")
print('  git commit -m "Add Phase 6B fake model driver frozen context"')
print("  git push")
