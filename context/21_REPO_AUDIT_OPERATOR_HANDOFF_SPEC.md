# Phase 14: Repo Audit + Operator Handoff Report Spec

## Status

Phase 14 is an audit and handoff phase.

It must not add new product capabilities.

It must not add new model workers.

It must not add new generation behavior.

It must not change the architecture.

It must not mark final gates as passed.

## Goal

Verify and document the system that now exists after Phase 13.

Abi now has an end-to-end scaffold from source material to candidate artifact, evaluation packet, final-artifact candidate packet, paper/evidence packet, and finalization-readiness report. Phase 14 should make that state explicit, auditable, and operator-ready.

## Required outputs

Phase 14 should produce tracked documentation under a directory such as:

docs/phase14_operator_handoff/

Required documents:

1. audit_report.md
2. command_matrix.md
3. phase_inventory.md
4. known_blockers.md
5. finalization_profile_summary.md
6. fixture_evidence_safety_report.md
7. live_model_guardrail_report.md
8. artifact_schema_envelope_report.md
9. fresh_clone_verification.md
10. next_validation_roadmap.md
11. operator_handoff.md

Exact filenames may differ if clearly equivalent.

## Required audit checks

The audit must address:

- all phase tags exist and point to expected commits
- README commands match actual CLI behavior
- AGENTS.md is still accurate and durable
- context docs are not obviously contradictory
- all listed CLI commands work or are clearly marked unavailable
- finalization profile behavior is correct
- fixture-only evidence cannot satisfy final_artifact gates
- candidate/final-artifact packets remain non-final
- live OpenAI paths require explicit opt-in
- tests do not require API keys
- tests do not make accidental network calls
- db/runs/outputs/.venv/cache files are not accidentally tracked
- artifact envelopes consistently expose schema_version, artifact_type, run_id, lineage_id, parent_ids, created_by, fixture_only, model_call_id, and payload where applicable
- model_call_id behavior is consistent
- generated runtime directories are gitignored or intentionally untracked
- fresh clone instructions are documented
- remaining blockers are clear

## Required CLI verification

Phase 14 should verify at minimum:

- git status
- git log --oneline --decorate -60
- git tag --list
- git ls-files
- python -m ruff check .
- python -m pytest
- abi status
- abi artifact list
- abi run list
- abi run latest
- abi final-artifact packet --client fake
- abi finalization status --profile final_artifact
- abi finalize --profile final_artifact

Additional CLI checks are allowed if useful.

## Required factual stance

The audit must state that Abi has not yet proven:

- phase-shift-level writing
- real human validation
- baseline superiority
- hostile-audit survival
- final artifact readiness
- paper-readiness

The audit must state that the current system is a working research harness and end-to-end scaffold, not a validated creative system.

## Prohibited

- no new generation behavior
- no new model worker
- no automatic OpenAI call
- no real live production run
- no human-study automation
- no dashboard
- no SKILL.md
- no finalization gate passing
- no phase-shift claim
- no broad refactor

## Acceptance criteria

Phase 14 is complete only when:

- ruff passes
- pytest passes
- working tree is clean after commit
- audit/handoff docs exist
- no out-of-scope features are added
- no final gates are falsely passed
- no fixture evidence is accepted as real validation
- finalization still refuses
- audit report clearly explains where Abi is, what remains unproven, and what Phase 15 should do
