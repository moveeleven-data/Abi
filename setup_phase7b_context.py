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
    "context/14_LIVE_FIELD_MODEL_WORKER_SPEC.md",
    """
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
""",
)

write(
    "context/plans/PHASE_7B_LIVE_ABI_EAR_FIELD_MODEL.md",
    """
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
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 7B reads:",
    """
## Phase 7B reads:

For Phase 7B, read:

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
11. context/13_FIRST_LIVE_WORKER_SPEC.md
12. context/14_LIVE_FIELD_MODEL_WORKER_SPEC.md
13. context/plans/PHASE_7B_LIVE_ABI_EAR_FIELD_MODEL.md

Phase 7B implements one guarded live Abi Ear field-model worker only.
""",
)

print("Phase 7B Live Abi Ear Field Model context files created.")
print("Next:")
print("  git status")
print("  git add context setup_phase7b_context.py")
print('  git commit -m "Add Phase 7B live Abi Ear field model frozen context"')
print("  git push")
