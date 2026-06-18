# Phase 13 Final Artifact + Paper Packet ExecPlan

## Goal

Implement the final-artifact candidate and paper/report packet scaffold.

The purpose is to make the current state legible and auditable while preserving finalization blockers.

## Scope

Add:

- final artifact packet orchestrator
- fake-client packet path
- optional guarded OpenAI path
- final artifact candidate artifact
- hidden consequence report
- reader effect claim map
- risk register
- hostile final audit scaffold
- paper outline
- paper evidence map
- finalization readiness report
- packet summary
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/final_artifact.py
tests/test_final_artifact_packet.py
tests/test_final_artifact_cli.py

Likely updated files:

src/abi/cli.py
src/abi/controller/state.py
README.md

Possible updates if useful:

src/abi/model_schemas.py

## CLI

Preferred command:

abi final-artifact packet --client fake

Optional guarded live path:

abi final-artifact packet --client openai --allow-live-model --max-model-calls 8

The fake path must require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Required output packet

The final artifact packet must expose:

1. source_refs
2. candidate_text
3. lineage_summary
4. hidden_consequence_report
5. reader_effect_claim_map
6. risk_register
7. hostile_final_audit_scaffold
8. paper_outline
9. paper_evidence_map
10. finalization_readiness_report
11. final_artifact_packet

## Tests

Tests must verify:

- all previous tests still pass
- fake final-artifact packet succeeds
- required artifacts exist
- candidate_text is non-final
- paper packet makes no phase-shift claim
- human validation is marked missing/not real
- finalization readiness report says ineligible
- final_artifact profile still refuses
- packet directory is unique per invocation
- parent IDs are populated where appropriate
- OpenAI path refuses without --allow-live-model
- OpenAI path refuses without OPENAI_API_KEY
- finalization remains fail-closed

## Done means

Phase 13 is done when a final-artifact candidate packet and paper/report packet exist, and the finalization policy still refuses the current run with meaningful blockers.
