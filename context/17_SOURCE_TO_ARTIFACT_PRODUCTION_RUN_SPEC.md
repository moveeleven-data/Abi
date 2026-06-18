# Phase 10: Controlled Source-to-Artifact Production Run v1 Spec

## Status

Phase 10 implements the first bounded source-to-artifact production run.

This is not the final essay system.

This is not a multi-lineage tournament.

This is not a human-calibrated production claim.

## Goal

Connect existing subsystems into one controlled production pipeline:

source material
→ production harness packet
→ selected germ / target effect
→ live Abi Ear packet
→ live Minimal Reread packet
→ candidate artifact packet
→ production run report
→ gate report

The phase should prove that Abi can move from source-like material to a candidate artifact packet while preserving artifact lineage, model-call records, guard behavior, and fail-closed finalization.

## Inputs

Default input should be deterministic fixture material from:

fixtures/production_harness/

Optional explicit source directory may be supported:

inputs/

or another user-provided path, but default tests must use fixtures only.

## Required CLI behavior

Add a command such as:

abi production live-demo --client fake

and optionally:

abi production live-demo --client openai --allow-live-model --max-model-calls 24

Rules:

- fake client mode must not require API key
- openai client mode must require --allow-live-model
- openai client mode must require OPENAI_API_KEY
- deterministic harness/ear/reread demos must remain unchanged
- production run output must use unique packet directories
- accepted parsed model artifacts must include model_call_id
- all artifacts must be registered through the artifact registry
- finalization must remain fail-closed

## Required production pipeline

The production run should create or reference:

1. production_source_manifest
2. production_harness_packet_ref
3. production_selected_germ
4. production_target_effect
5. production_live_abi_ear_packet_ref
6. production_live_reread_packet_ref
7. production_candidate_artifact
8. production_candidate_report
9. production_gate_report
10. production_packet

Artifact type names may differ if aligned with existing conventions, but the packet must expose these concepts.

## Candidate artifact

The candidate artifact may be derived from the live Minimal Reread recomposed draft or equivalent packet output.

It must be clearly marked:

- candidate only
- not final
- not human-validated
- not a phase-shift claim

## Model-call behavior

The fake production run may call existing fake live Abi Ear and fake live Minimal Reread paths.

Every model-shaped output must be schema-validated before parsed artifact registration.

Accepted parsed model artifacts must include:

- schema_version
- artifact_type
- run_id
- lineage_id
- parent_ids
- created_by
- fixture_only
- model_call_id
- payload

Invalid model outputs must not create parsed artifacts.

Client failures must be recorded.

## Budget guard

Add or reuse a simple max-call guard.

Default should be conservative.

Suggested default:

--max-model-calls 24

If execution would exceed the budget, the command must refuse or stop with a structured error.

## Required gate behavior

Phase 10 gate report should evaluate only the production packet scaffold.

It must not claim final artifact success.

It must not satisfy finalization gates.

Finalization must remain fail-closed.

## Prohibited

- no final essay generation claim
- no multi-lineage tournament
- no human calibration automation
- no real human-study claims
- no automatic OpenAI calls
- no agent loops
- no finalization semantic changes
- no SKILL.md
- no broad refactor
- no dashboard

## Acceptance criteria

Phase 10 is complete only when:

- ruff passes
- pytest passes
- deterministic demos still work
- fake production live-demo works
- openai production live-demo refuses without --allow-live-model
- openai production live-demo refuses without OPENAI_API_KEY
- production packet contains source/harness/germ/ear/reread/candidate/report/gate artifacts
- candidate artifact is marked non-final
- accepted parsed model artifacts include model_call_id
- parent IDs are populated where appropriate
- max-call budget is enforced
- finalization remains fail-closed
