# Phase 8: Live Abi Ear Packet v1 Spec

## Status

Phase 8 implements a guarded live Abi Ear packet pipeline.

This phase is larger than Phase 7A/7B but remains bounded to Abi Ear only.

## Goal

Produce a complete Abi Ear packet for the benchmark germ using the model-driver/live-worker infrastructure.

Benchmark input:

The table is still there in the morning.

The live packet must prove that Abi can produce a full local literary packet through validated, recorded model-shaped outputs while preserving deterministic demos and fail-closed finalization.

## Scope

Phase 8 may add live/stubbed workers for the remaining Abi Ear packet pieces:

- variants
- move composition
- ranked move sequence / retrospective judge
- prose inventions
- refined invention
- reread trace
- ablation report
- local gate report
- packet summary

It may reuse existing guarded live workers:

- abi_ear_germ_analysis
- abi_ear_field_model

## Required CLI behavior

Add a command such as:

abi ear live-demo --client fake

and optionally:

abi ear live-demo --client openai --allow-live-model --max-model-calls 8

Rules:

- deterministic `abi ear demo` must remain unchanged
- fake client mode must not require API key
- openai client mode must require --allow-live-model
- openai client mode must require OPENAI_API_KEY
- live packet output must use unique packet directories
- parsed model artifacts must include model_call_id
- every model-shaped output must be schema-validated before artifact registration
- final Abi Ear packet must register all artifacts through the artifact registry

## Required artifact types

The live packet should produce artifact types equivalent to:

- live_abi_ear_germ_analysis
- live_abi_ear_field_model
- live_abi_ear_variants
- live_abi_ear_moves
- live_abi_ear_ranked_move_sequence
- live_abi_ear_prose_inventions
- live_abi_ear_refined_invention
- live_abi_ear_reread_trace
- live_abi_ear_ablation_report
- live_abi_ear_gate_report
- live_abi_ear_packet

Exact type names may differ if they align with existing conventions.

## Required model-call behavior

Every live/fake model worker call must create or reuse model-call records.

Accepted parsed artifacts must include:

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

Add a simple max-call guard for live packet execution.

The command should accept something like:

--max-model-calls 8

Default should be conservative.

If the packet would exceed the budget, it must refuse or stop with a structured error.

## Prohibited

- no production essay generation
- no live Minimal Reread loop
- no source ingestion changes
- no human calibration automation
- no agent loops
- no automatic OpenAI calls
- no deterministic demo replacement
- no finalization semantics changes
- no SKILL.md

## Acceptance criteria

Phase 8 is complete only when:

- ruff passes
- pytest passes
- deterministic demos still work
- fake live Abi Ear packet command works
- openai live Abi Ear packet command refuses without --allow-live-model
- openai live Abi Ear packet command refuses without OPENAI_API_KEY
- packet artifacts are registered with parent IDs and hashes
- accepted parsed model artifacts include model_call_id
- invalid fake outputs are rejected in tests
- finalization remains fail-closed
