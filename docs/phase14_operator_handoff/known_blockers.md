# Known Blockers

Last checked: 2026-06-18

## Final Artifact Blockers

The current run is blocked from the `final_artifact` profile by the following required gates:

- `final_artifact_packet_exists`
- `final_artifact_not_fixture`
- `final_artifact_not_marked_non_final`
- `real_human_validation_passed`
- `strongest_rival_comparison_passed`
- `raw_model_baseline_comparison_passed`
- `hostile_final_audit_passed`
- `no_fixture_only_evidence_used_as_final_claim`
- `no_unresolved_blocking_defects`
- `final_operator_approval`

The current final-artifact scaffold intentionally creates candidate artifacts that are non-final, not human-validated, not finalization-eligible, and marked with no phase-shift claim.

## Evidence Blockers

Abi has not passed real human validation. Human traces and calibration inputs currently available in the repository are fixtures and must not be treated as validation evidence.

Abi has not beaten strong baselines. The evaluation baseline scaffold distinguishes fixture/fake baseline outputs from future guarded live outputs, but no production-quality strongest-rival or raw-model baseline result has been accepted as final evidence.

Abi has not completed hostile final audit. The hostile final audit scaffold exists as a packet component, but no hostile final audit gate is passed.

## Release Blockers

Abi is not paper-ready. It lacks a final artifact, real validation, strongest-rival evidence, raw-model baseline evidence, hostile audit clearance, and final operator approval.

Abi is not proven to produce phase-shift-level writing. No document in this handoff should be read as making that claim.
