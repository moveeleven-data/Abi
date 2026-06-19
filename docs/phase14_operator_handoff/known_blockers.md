# Known Blockers

Last realigned: 2026-06-19

## Autonomous Creative Candidate Blockers

The active `autonomous_creative_candidate` profile remains fail-closed until internal gates are present and passing:

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

## Evidence Blockers

Abi has deterministic fake internal reader-state artifacts, failure diagnosis, recomposition planning, ablation planning, hostile internal reader reporting, and internal rival comparison. It has not executed targeted recomposition, executed ablation, cleared fixture-only evidence, or resolved internal blockers.

Fixture and fake-client outputs remain engineering artifacts. They do not satisfy `no_fixture_only_core_evidence`.

## Non-Active Blockers

The legacy `final_artifact` profile still exists as an external/public validation policy and remains fail-closed. It is not the active path and should not be used to drive current development.

Abi is not proven to produce phase-shift-level writing. No document in this handoff should be read as making that claim.
