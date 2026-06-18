# Evidence To Gate Mapping

Last checked: 2026-06-18

## Rule

Protocol documents pass no gates. Only future collected, reviewed, non-fixture evidence can support final-artifact gates.

| Final Artifact Gate | Future Evidence Required | Current Status |
| --- | --- | --- |
| `final_artifact_packet_exists` | A reviewed final artifact packet whose candidate is no longer marked candidate-only. | Not satisfied. Current packet is scaffold/candidate state. |
| `final_artifact_not_fixture` | Registered packet artifacts with `fixture_only: false` and evidence that inputs are real validation evidence. | Not satisfied. Current evidence includes fixture/fake paths. |
| `final_artifact_not_marked_non_final` | Candidate flags no longer include `non_final`, `not_human_validated`, or `not_finalization_eligible`, after evidence review. | Not satisfied. Current candidates intentionally carry those flags. |
| `real_human_validation_passed` | Complete blinded human traces, locked scoring, exclusions, and analysis showing preregistered success. | Not satisfied. |
| `strongest_rival_comparison_passed` | Blinded comparison against a preregistered strongest rival with locked selection and scoring. | Not satisfied. |
| `raw_model_baseline_comparison_passed` | Blinded comparison against a preregistered raw-model baseline with stored prompts and model-call records. | Not satisfied. |
| `hostile_final_audit_passed` | Independent hostile audit report with no blocking defects. | Not satisfied. |
| `no_fixture_only_evidence_used_as_final_claim` | Evidence map showing no fixture-only artifacts support final claims. | Not satisfied. |
| `no_unresolved_blocking_defects` | Defect log showing all blocking defects resolved or explicitly waived by final policy. | Not satisfied. |
| `final_operator_approval` | Explicit operator approval after reviewing all final evidence and audit reports. | Not satisfied. |

## Evidence Classes

Fixture data can support tests and protocol dry-runs only.

Fake-client outputs can support engineering verification only.

Guarded live outputs can support artifact production only if model-call records, prompts, budgets, and packet IDs are preserved.

Human validation evidence can support final gates only if it is real, consented, blinded, non-fixture, and reviewed.
