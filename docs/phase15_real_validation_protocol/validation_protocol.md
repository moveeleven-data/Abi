# Real Validation Protocol

Last checked: 2026-06-18

## Status

This protocol is an evidence plan only. It does not run validation, collect human data, run a real OpenAI production pass, generate a final artifact, pass any final gate, or make a phase-shift claim.

Abi remains a scaffold until future evidence is collected under this protocol and reviewed through the `final_artifact` gate profile.

## Validation Question

The validation question is whether an Abi-produced candidate causes a reproducible reader-state change that is stronger than baseline outputs under blind comparison.

This question must be tested without telling readers which text came from Abi, without relying on fixture traces, and without interpreting protocol completion as evidence.

## Study Arms

Future validation must compare at least:

- Abi candidate artifact.
- Strongest-rival artifact.
- Raw-model baseline artifact.
- Direct-prompt baseline artifact, if distinct from the raw-model baseline.

The final analysis must preserve each artifact's source label internally while showing only neutral labels to readers.

## Required Measurements

- First-read response.
- Reread response.
- Opening-transfiguration score.
- Paraphrase-loss score.
- Attention report.
- Confusion report.
- Overexplicitness report.
- Free-text evidence for claimed reader-state transition.

## Evidence Thresholds

Pilot success means the protocol is usable, not that Abi passes validation. A pilot may be considered usable only if:

- At least 80 percent of enrolled pilot readers produce complete usable traces.
- No blindness breach occurs.
- Readers can complete both first-read and reread tasks without moderator repair.
- Opening-transfiguration and paraphrase-loss fields are populated consistently enough for independent scoring.
- No hostile-audit blocking defect is found in task wording, ordering, evidence handling, or baseline construction.

Future full validation thresholds must be preregistered before data collection. They must include minimum sample size, exclusion rules, primary endpoint, secondary endpoints, and baseline superiority criteria.

## Finalization Stance

This protocol passes no final gates. It only defines what future evidence could be reviewed for gates such as `real_human_validation_passed`, `strongest_rival_comparison_passed`, `raw_model_baseline_comparison_passed`, `hostile_final_audit_passed`, and `final_operator_approval`.
