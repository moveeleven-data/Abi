# Phase 6A-lite: Model-Readiness Consolidation Spec

## Status

Phase 6A-lite is a narrow consolidation phase before live model calls.

Do not implement model/API calls.

Do not implement model_driver.py.

Do not add creative generation.

Do not redesign the architecture.

Do not perform a broad cleanup/refactor.

## Goal

Prepare Abi's deterministic packet modules to safely accept future model-produced artifacts by consolidating packet writing, artifact registration, artifact envelopes, and inspection commands.

This phase should make the existing scaffold more model-ready without changing its behavior.

## Scope

Implement only:

1. Shared packet-writing helper for deterministic packet modules.
2. Shared artifact registration helper if needed.
3. Normalized packet/artifact envelope.
4. Artifact inspection CLI.
5. Run inspection CLI.
6. Tests proving no regression.

## Required normalized envelope

Packet/artifact JSON written by deterministic packet modules should use this shape where practical:

- schema_version
- artifact_type
- run_id
- lineage_id
- parent_ids
- created_by
- fixture_only
- model_call_id
- payload

Rules:

- lineage_id may be null.
- fixture_only may be null or true/false depending on artifact type.
- model_call_id must be null in Phase 6A-lite.
- payload contains the module-specific artifact content.
- Existing behavior must not regress.

## Required CLI

Add artifact inspection commands:

- abi artifact list
- abi artifact show <artifact_id>

Add run inspection commands:

- abi run list
- abi run show <run_id>
- abi run latest

Commands must emit JSON.

## Helper requirements

A shared packet helper should handle:

- creating unique packet directories
- writing JSON artifacts
- registering artifacts
- preserving parent IDs
- returning artifact IDs and paths
- applying the normalized envelope

The packet helper must be used by at least:

- Abi Ear
- one other deterministic packet module

Using it by all deterministic packet modules is allowed if low-risk, but do not over-refactor.

## Acceptance criteria

Phase 6A-lite is complete only when:

- ruff passes
- pytest passes
- all existing demos still work
- artifact list/show works
- run list/show/latest works
- packet helper is used by at least Abi Ear and one other deterministic packet module
- schema_version appears consistently in registered packet artifacts
- model_call_id is present and null in normalized envelopes
- no behavior regression
- abi finalize still refuses when required gates are missing

## Prohibited

- no model_driver.py
- no OpenAI API integration
- no real model calls
- no fake-client model driver yet
- no creative generation
- no human survey UI
- no dashboard
- no dev reset unless specifically needed
- no broad architecture rewrite
- no SKILL.md
