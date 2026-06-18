# Phase 9: Guarded Live Minimal Reread Loop v1 Spec

## Status

Phase 9 implements a guarded live-shaped Minimal Reread loop.

This phase remains bounded to the minimal reread loop. It is not the production essay system.

## Goal

Produce a complete Minimal Reread packet from the benchmark germ and/or a live Abi Ear packet using validated model-shaped workers.

The phase must demonstrate the core Abi loop in live-shaped form:

reader-state trace
→ diagnosed failure
→ targeted intervention
→ counterfactual proof

## Inputs

Primary benchmark input:

The table is still there in the morning.

The command may run or reuse a live Abi Ear fake packet as an upstream dependency.

## Required CLI behavior

Add a command such as:

abi reread live-demo --client fake

and optionally:

abi reread live-demo --client openai --allow-live-model --max-model-calls 12

Rules:

- deterministic `abi reread demo` must remain unchanged
- fake client mode must not require API key
- openai client mode must require --allow-live-model
- openai client mode must require OPENAI_API_KEY
- live packet output must use unique packet directories
- parsed model artifacts must include model_call_id
- every model-shaped output must be schema-validated before artifact registration
- final Minimal Reread packet must register all artifacts through the artifact registry

## Required artifacts

The live minimal reread packet should produce artifact types equivalent to:

- live_reread_formal_problem
- live_reread_germ_afterimage_pair
- live_reread_consequence_graph
- live_reread_draft_version
- live_reread_first_read_trace
- live_reread_reread_trace
- live_reread_failure_diagnosis
- live_reread_intervention
- live_reread_recomposed_draft
- live_reread_counterfactual_result
- live_reread_irreducibility_report
- live_reread_gate_report
- live_reread_packet

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

Add a simple max-call guard for live reread execution.

The command should accept something like:

--max-model-calls 12

Default should be conservative.

If the loop would exceed the budget, it must refuse or stop with a structured error.

## Required loop shape

The packet must make the loop explicit:

1. first-read trace
2. reread trace
3. failure diagnosis
4. targeted intervention
5. recomposed draft
6. counterfactual result

The output does not need to be artistically excellent yet. The goal is control and traceability.

## Prohibited

- no production essay generation
- no source ingestion changes
- no human calibration automation
- no lineage tournament
- no multi-branch search
- no agent loops
- no automatic OpenAI calls
- no deterministic demo replacement
- no finalization semantics changes
- no SKILL.md

## Acceptance criteria

Phase 9 is complete only when:

- ruff passes
- pytest passes
- deterministic demos still work
- fake live Minimal Reread command works
- openai live Minimal Reread command refuses without --allow-live-model
- openai live Minimal Reread command refuses without OPENAI_API_KEY
- packet artifacts are registered with parent IDs and hashes
- accepted parsed model artifacts include model_call_id
- invalid fake outputs are rejected in tests
- counterfactual result artifact exists
- finalization remains fail-closed
