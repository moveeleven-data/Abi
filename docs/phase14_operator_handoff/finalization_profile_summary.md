# Finalization Profile Summary

Last checked: 2026-06-18

## Profiles

| Profile | Required Gates | Purpose |
| --- | --- | --- |
| `infrastructure` | `infrastructure_initialized`, `artifact_registry_ready`, `required_phase0_tests_passed` | Phase 0 infrastructure readiness. |
| `candidate_release` | `source_to_artifact_production_run_v1`, `evaluation_baselines_v1` | Candidate scaffold readiness for controlled release review. |
| `final_artifact` | `final_artifact_packet_exists`, `final_artifact_not_fixture`, `final_artifact_not_marked_non_final`, `real_human_validation_passed`, `strongest_rival_comparison_passed`, `raw_model_baseline_comparison_passed`, `hostile_final_audit_passed`, `no_fixture_only_evidence_used_as_final_claim`, `no_unresolved_blocking_defects`, `final_operator_approval` | True final artifact release readiness. |

## Current Behavior

`abi finalization status --profile final_artifact` reports the current run as ineligible. The blocker report includes missing gates and content blockers for fixture-only evidence and non-final candidate artifacts.

`abi finalize --profile final_artifact` refuses finalization. This is correct behavior.

Existing `abi finalize` remains fail-closed under its default policy. No worker path can finalize the project.

## Operator Rule

Do not manually mark final-artifact gates passed unless the corresponding external evidence exists and has been reviewed. Controlled unit tests may construct eligible profiles, but demo, fixture, and fake-client state must remain ineligible.
