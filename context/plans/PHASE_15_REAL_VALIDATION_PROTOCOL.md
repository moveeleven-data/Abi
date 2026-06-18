# Phase 15 Real Validation Protocol ExecPlan

## Goal

Create the real validation protocol and evidence plan.

This is a documentation/protocol phase, not a generation phase.

## Scope

Add tracked protocol documents under:

docs/phase15_real_validation_protocol/

Required reports:

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

## Required checks

Run:

python -m ruff check .
python -m pytest
abi finalization status --profile final_artifact
abi finalize --profile final_artifact

## Done means

The repo contains a clear, auditable protocol for the first real evidence-producing run, and finalization still refuses.
