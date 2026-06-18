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
    "context/13_FIRST_LIVE_WORKER_SPEC.md",
    """
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
""",
)

write(
    "context/plans/PHASE_7A_LIVE_ABI_EAR_GERM_ANALYSIS.md",
    """
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
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 7A reads:",
    """
## Phase 7A reads:

For Phase 7A, read:

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
12. context/plans/PHASE_7A_LIVE_ABI_EAR_GERM_ANALYSIS.md

Phase 7A implements one guarded live Abi Ear germ-analysis worker only.
""",
)

print("Phase 7A First Live Worker context files created.")
print("Next:")
print("  git status")
print("  git add context setup_phase7a_context.py")
print('  git commit -m "Add Phase 7A live Abi Ear germ analysis frozen context"')
print("  git push")
