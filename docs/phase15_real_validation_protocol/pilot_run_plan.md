# Pilot Run Plan

Last checked: 2026-06-18

## Goal

The pilot tests whether the protocol works. It does not prove Abi, pass final gates, or justify a phase-shift claim.

## Preconditions

- Artifact set is frozen.
- Baseline prompts and strongest-rival selection rules are frozen.
- Reader task wording is frozen.
- Exclusion criteria are frozen.
- Analysis plan is frozen.
- Consent and data-use note is approved by the operator.
- No artifact labels reveal source.

## Suggested Pilot Size

Use 8 to 12 readers for the first pilot. This is enough to find task failures, blindness leaks, missing fields, and scoring ambiguity, but not enough for final validation.

## Pilot Procedure

1. Generate or select the artifact set under the frozen rules.
2. Assign neutral labels and randomized order.
3. Collect first-read traces.
4. Collect reread traces.
5. Score opening transfiguration and paraphrase loss while blind to source.
6. Apply exclusion criteria.
7. Run hostile-audit checklist on the pilot process.
8. Write a pilot report that separates protocol defects from artifact effects.

## Pilot Success Threshold

The pilot can be considered successful only if:

- At least 80 percent of enrolled readers produce usable complete traces.
- No source-label breach occurs.
- No blocking hostile-audit defect is found.
- The scoring rubric can be applied by independent scorers without major ambiguity.
- Reader confusion is about artifacts, not task instructions.

Pilot success permits planning a full validation run. It does not satisfy final gates.
