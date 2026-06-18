# Phase 16 First Real Candidate Set ExecPlan

## Goal

Implement the first pilot artifact-set generator.

This is the bridge between protocol and actual human-reader pilot.

## Scope

Add:

- pilot artifact-set orchestrator
- fake-client path
- guarded OpenAI path
- source manifest with hashes
- private input directory protection
- neutral label map
- blinded reader bundle
- candidate/baseline artifacts
- strongest-rival slot
- pilot readiness report
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/pilot_artifact_set.py
tests/test_pilot_artifact_set.py
tests/test_pilot_artifact_set_cli.py

Likely updated files:

src/abi/cli.py
src/abi/controller/state.py
README.md
.gitignore

Optional fixtures:

fixtures/pilot_source/

## CLI

Preferred command:

abi pilot artifact-set --client fake --source-dir fixtures/production_harness

Optional guarded live path:

abi pilot artifact-set --client openai --source-dir inputs/private/phase16_source --allow-live-model --max-model-calls 36

## Tests

Tests must verify:

- all previous tests still pass
- fake artifact-set command succeeds
- source manifest records file hashes
- private input path is gitignored
- neutral labels do not reveal source class
- blinded reader bundle exists
- candidate artifact is non-final and not human validated
- fake baselines are marked fixture/fake
- strongest-rival slot remains unsatisfied unless real imported rival exists
- OpenAI path refuses without --allow-live-model
- OpenAI path refuses without OPENAI_API_KEY
- final_artifact profile remains ineligible
- finalization remains fail-closed

## Done means

Phase 16 is done when the repo can create a pilot-ready artifact set without collecting human data or making validation claims.
