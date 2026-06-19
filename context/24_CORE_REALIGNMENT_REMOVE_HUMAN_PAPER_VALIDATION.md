# Core Realignment: Remove Human/Paper Validation From Active Path

This document records a repo cleanup and core realignment. It is not a numbered implementation phase.

## Active Direction

Abi is being developed as an autonomous creative engine. The active runtime path is:

1. source material
2. Abi Ear
3. Minimal Reread
4. candidate/baseline/rival set
5. internal reader-state workers
6. failure diagnosis
7. targeted recomposition
8. counterfactual ablation
9. rival preservation
10. fail-closed autonomous finalization

The next development milestone is **Autonomous Internal Reader Lab v1**.

## Removed From Active Path

The following are no longer active runtime or operator directions:

- human reader dry runs
- reader-kit export workflows for external people
- human calibration as a runtime direction
- paper-grade validation language
- public-validation finalization requirements
- docs that present human readers or paper evidence as the next step
- ad hoc browser ChatGPT sessions as stand-in readers

Human or public validation may be intentionally reintroduced later, but it is out of scope for the current core engine path.

## Active Finalization Profile

The active internal profile is `autonomous_creative_candidate`.

It must remain fail-closed. It must not require real human validation, human traces, human reader data, paper evidence, public validation, paper-grade validation, or final paper approval.

The active profile requires internal gates:

- `autonomous_candidate_packet_exists`
- `internal_stream_reader_trace_exists`
- `internal_reread_trace_exists`
- `forensic_grounding_report_exists`
- `hostile_reader_report_exists`
- `failure_diagnosis_exists`
- `targeted_recomposition_plan_exists`
- `counterfactual_ablation_plan_or_result_exists`
- `rival_preservation_present`
- `internal_rival_comparison_exists`
- `no_fixture_only_core_evidence`
- `no_unresolved_internal_blockers`
- `internal_operator_approval`

## Legacy External Validation

The legacy `final_artifact` profile may remain in the codebase as an external/public validation policy. It is not the active path and must not drive current development. Do not weaken it or treat fixture evidence as satisfying it.

## Claims Not Made

This repo state makes no final claim and no phase-shift claim. It has not completed Autonomous Internal Reader Lab v1, has not beaten a strongest rival, and has not passed hostile internal audit.
