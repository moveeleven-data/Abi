# Phase 11 Evaluation, Baselines, and Human-Trace Import ExecPlan

## Goal

Implement the first evaluation packet around a production candidate artifact.

This phase should create comparison evidence scaffolding without claiming real validation.

## Scope

Add:

- evaluation orchestrator
- fake-client evaluation path
- optional guarded OpenAI evaluation path
- baseline fixture generation or import
- candidate artifact reference
- blind comparison protocol/result
- human-trace import fixture
- reader-state transition comparison
- baseline comparison report
- evaluation gate report
- evaluation packet
- max model-call budget guard
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/evaluation.py
tests/test_evaluation.py
tests/test_evaluation_cli.py

Likely updated files:

src/abi/cli.py
src/abi/controller/state.py
src/abi/model_schemas.py
README.md

Optional fixtures:

fixtures/evaluation/direct_prompt_baseline.md
fixtures/evaluation/human_trace_fixture.json

## CLI

Preferred command:

abi evaluation demo --client fake

Optional guarded live path:

abi evaluation demo --client openai --allow-live-model --max-model-calls 12

The fake path must require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Required output packet

The evaluation packet must expose:

1. evaluation_subject
2. candidate_artifact_ref
3. direct_prompt_baseline
4. best_of_n_baseline_summary
5. blind_comparison_protocol
6. blind_comparison_result
7. human_trace_import
8. reader_state_transition_comparison
9. baseline_comparison_report
10. evaluation_gate_report
11. evaluation_packet

## Tests

Tests must verify:

- all previous tests still pass
- deterministic demos remain unchanged
- fake evaluation demo succeeds
- evaluation packet produces required concepts
- candidate artifact is marked non-final
- fixture human trace is marked fixture_only and not_real_validation
- baseline artifacts are marked fixture/fake unless live path is explicitly selected
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- max-call budget is enforced
- openai client path refuses without --allow-live-model
- openai client path refuses without OPENAI_API_KEY
- finalization remains fail-closed

## Manual live smoke test

Manual OpenAI evaluation smoke test is optional and should not be run by Codex.

It should require:

- OPENAI_API_KEY set
- --allow-live-model passed
- max model calls explicitly set

## Done means

Phase 11 is done when an evaluation packet can be generated around a production candidate, baselines and human-trace fixtures are represented as artifacts, and no final validation claim is made.
