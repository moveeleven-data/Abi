# Finalization Profile Summary

Last realigned: 2026-06-19

## Profiles

| Profile | Purpose |
| --- | --- |
| `infrastructure` | Phase 0 infrastructure readiness. |
| `candidate_release` | Historical candidate scaffold readiness. |
| `autonomous_creative_candidate` | Active internal autonomous creative-candidate readiness. |
| `final_artifact` | Legacy external/public validation policy; retained but not active. |

## Active Profile

`autonomous_creative_candidate` requires internal autonomous gates only. It does not require human validation, human traces, paper evidence, public validation, or paper approval.

Run:

```powershell
.\.venv\Scripts\abi.exe finalization status --profile autonomous_creative_candidate
.\.venv\Scripts\abi.exe finalize --profile autonomous_creative_candidate
```

The profile should refuse until all internal gates are passed.

## Required Autonomous Gates

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

## Operator Rule

Do not manually mark autonomous gates passed unless the corresponding internal artifacts or operator approvals exist. Controlled unit tests may construct eligible profiles, but demo, fixture, and fake-client state must remain ineligible.
