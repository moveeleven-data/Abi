# Phase 13: Final Artifact + Paper Packet v1 Spec

## Status

Phase 13 creates the final-artifact candidate packet and research/paper packet scaffold.

This phase must not finalize the project.

This phase must not claim phase shift.

This phase must not claim real human validation.

## Goal

Create a structured packet that gathers the current production candidate, evaluation evidence, hidden consequence evidence, risk register, paper outline, and finalization-readiness report.

This packet should make the project externally legible without pretending the artifact is final.

## Required CLI behavior

Add a command such as:

abi final-artifact packet --client fake

and optionally:

abi final-artifact packet --client openai --allow-live-model --max-model-calls 8

Rules:

- fake client mode must not require API key
- OpenAI client mode must require --allow-live-model
- OpenAI client mode must require OPENAI_API_KEY
- no automatic OpenAI calls
- output must use unique packet directories
- all artifacts must be registered through the artifact registry
- finalization must remain fail-closed

## Required input behavior

Default input should use the latest available fake production and evaluation packets.

If no production/evaluation packet exists, the command may run fake production/evaluation dependencies or refuse with a clear structured message.

Tests should be deterministic.

## Required artifacts

The final artifact packet should produce artifact types equivalent to:

- final_artifact_source_refs
- final_artifact_candidate_text
- final_artifact_lineage_summary
- hidden_consequence_report
- reader_effect_claim_map
- final_artifact_risk_register
- hostile_final_audit_scaffold
- paper_outline
- paper_evidence_map
- finalization_readiness_report
- final_artifact_packet

Exact names may differ if aligned with repo conventions.

## Required flags

The packet must clearly mark the artifact as:

- non_final: true
- not_human_validated: true
- not_finalization_eligible: true
- no_phase_shift_claim: true
- fixture_or_scaffold_evidence_present: true where applicable

It must not mark final gates as passed.

It must not satisfy finalization profile eligibility.

## Candidate artifact

The candidate artifact may be based on the latest production candidate artifact.

It must be represented as a candidate, not a final work.

## Paper packet

The paper packet should be a scaffold, not a finished paper.

It should include:

- project thesis
- system architecture summary
- artifact/evidence map
- baseline/evaluation status
- known blockers
- claims not yet made
- next required validation steps

## Finalization readiness

The finalization readiness report should call into or mirror the final_artifact profile blockers.

It should show the run remains ineligible for finalization.

## Required tests

Tests must verify:

- all previous tests still pass
- fake final-artifact packet command succeeds
- OpenAI path refuses without --allow-live-model
- OpenAI path refuses without OPENAI_API_KEY
- all required packet artifacts are produced
- candidate artifact is marked non-final
- no phase-shift claim is made
- no real human-validation claim is made
- finalization readiness report says ineligible
- finalization remains fail-closed
- packet directory is unique per invocation
- parent IDs are populated where appropriate

## Prohibited

- no actual finalization
- no phase-shift claim
- no real human-validation claim
- no automatic OpenAI calls
- no dashboard
- no agent loops
- no SKILL.md
- no broad refactor
- no weakening finalization
