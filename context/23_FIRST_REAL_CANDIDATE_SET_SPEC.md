# Phase 16: First Real Candidate Set / Pilot Artifact Set Spec

## Status

Phase 16 prepares the first real pilot artifact set.

This phase must not collect human data.

This phase must not claim validation.

This phase must not mark final gates passed.

This phase must not run an automatic OpenAI call.

## Goal

Create a source-frozen candidate-set pipeline that can produce the artifacts needed for the first human-reader pilot:

- Abi candidate
- direct-prompt baseline
- raw-model baseline
- strongest-rival placeholder or imported strongest rival
- neutral labels
- blinded study bundle
- pilot readiness report

The output should make the artifact set ready for future human reading under the Phase 15 protocol.

## Privacy rule

The repo may be public.

Do not commit private source material.

Phase 16 must support source input from an untracked local directory such as:

inputs/private/phase16_source/

The command may also support deterministic fixture mode for tests.

Add or preserve gitignore protection for private input directories.

## Required CLI behavior

Add a command such as:

abi pilot artifact-set --client fake --source-dir fixtures/production_harness

and optionally:

abi pilot artifact-set --client openai --source-dir inputs/private/phase16_source --allow-live-model --max-model-calls 36

Rules:

- fake mode must require no API key
- OpenAI mode must require --allow-live-model
- OpenAI mode must require OPENAI_API_KEY
- tests must use fake mode only
- no automatic OpenAI calls
- source manifest must include source file names and hashes
- private source files must not be copied into tracked docs
- output must use unique packet directories
- finalization must remain fail-closed

## Required artifact set

The pilot artifact set must include artifacts equivalent to:

1. pilot_source_manifest
2. pilot_generation_plan
3. pilot_abi_candidate_ref
4. pilot_direct_prompt_baseline
5. pilot_raw_model_baseline
6. pilot_strongest_rival_slot
7. pilot_neutral_label_map_private
8. pilot_blinded_reader_bundle
9. pilot_artifact_set_manifest
10. pilot_readiness_report
11. pilot_packet

Exact names may differ if aligned with repo conventions.

## Candidate and baseline rules

The Abi candidate must remain:

- non_final: true
- not_human_validated: true
- not_finalization_eligible: true
- no_phase_shift_claim: true

Baselines generated in fake mode must be marked fixture/fake.

Strongest-rival placeholder must state that strongest-rival evidence is not yet satisfied unless a real rival artifact is explicitly imported under protocol rules.

Neutral labels must not reveal source class to readers.

## Budget behavior

Add or reuse max-call budgeting.

Suggested default:

--max-model-calls 36

If execution would exceed the budget, refuse with a structured error.

## Required finalization behavior

Phase 16 must preserve finalization refusal.

No final_artifact gates should pass from Phase 16 artifact-set generation.

## Prohibited

- no real human data collection
- no live OpenAI call during tests or Codex implementation
- no final artifact claim
- no phase-shift claim
- no gate passing
- no dashboard
- no SKILL.md
- no broad refactor
- no architecture rewrite

## Acceptance criteria

Phase 16 is complete when:

- ruff passes
- pytest passes
- fake pilot artifact-set command works
- OpenAI path refuses without --allow-live-model
- OpenAI path refuses without OPENAI_API_KEY
- source manifest hashes source files
- private source directory is gitignored
- pilot bundle uses neutral labels
- candidate remains non-final
- baselines are marked fixture/fake in fake mode
- strongest-rival slot does not falsely pass strongest-rival gate
- finalization remains fail-closed
