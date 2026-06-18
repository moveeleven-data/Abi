# Phase 15: Real Validation Protocol + Evidence Plan Spec

## Status

Phase 15 defines the real validation protocol and evidence plan.

This phase must not run real validation.

This phase must not run a real OpenAI production pass.

This phase must not mark final gates passed.

## Goal

Define the evidence protocol required before Abi can make any claim about phase-shift writing, reader-state transformation, baseline superiority, or final-artifact readiness.

Phase 15 should convert the current audited scaffold into an evidence-ready system.

## Required outputs

Create tracked documentation under:

docs/phase15_real_validation_protocol/

Required documents:

1. validation_protocol.md
2. human_reader_protocol.md
3. blind_reread_task.md
4. reader_trace_schema.md
5. baseline_protocol.md
6. strongest_rival_protocol.md
7. raw_model_baseline_protocol.md
8. hostile_final_audit_checklist.md
9. evidence_to_gate_mapping.md
10. pilot_run_plan.md
11. live_run_budget_plan.md
12. phase15_operator_checklist.md

Exact names may differ if clearly equivalent.

## Required protocol contents

The protocol must define:

- recruitment criteria
- consent / data-use note
- blindness requirements
- first-read task
- reread task
- opening-transfiguration measurement
- paraphrase-loss measurement
- attention/confusion/overexplicitness reporting
- exclusion criteria
- comparison ordering
- baseline generation rules
- strongest-rival comparison rules
- raw-model baseline rules
- hostile-audit failure criteria
- evidence thresholds for pilot success
- what evidence can and cannot satisfy final_artifact gates

## Required finalization stance

Phase 15 must preserve finalization refusal.

It must state that no gate is passed by protocol definition alone.

It may define which future evidence would be required to satisfy:

- real_human_validation_passed
- strongest_rival_comparison_passed
- raw_model_baseline_comparison_passed
- hostile_final_audit_passed
- no_fixture_only_evidence_used_as_final_claim
- no_unresolved_blocking_defects
- final_operator_approval

## Required command verification

At minimum, rerun:

- python -m ruff check .
- python -m pytest
- abi finalization status --profile final_artifact
- abi finalize --profile final_artifact

Finalization must refuse.

## Prohibited

- no live OpenAI production run
- no real human-data collection
- no final artifact claim
- no phase-shift claim
- no gate passing
- no dashboard
- no SKILL.md
- no broad refactor
- no architecture rewrite

## Acceptance criteria

Phase 15 is complete when:

- documentation exists
- Ruff passes
- Pytest passes
- finalization still refuses
- no gates are falsely marked passed
- validation protocol makes the next live/pilot phase actionable
