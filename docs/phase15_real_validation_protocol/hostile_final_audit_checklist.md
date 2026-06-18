# Hostile Final Audit Checklist

Last checked: 2026-06-18

## Purpose

The hostile final audit looks for reasons the evidence should not be trusted. It is not a style review and not a friendly readiness check.

## Blocking Failure Criteria

A future hostile final audit must fail if any of the following occur:

- Any final evidence is fixture-only or marked `not_real_validation`.
- A reader or scorer was unblinded before completing the relevant task.
- Exclusion criteria were changed after viewing outcomes.
- Baselines were selected, edited, or discarded after viewing reader results.
- Abi outputs had access to baseline outputs in a way not preregistered.
- Source material, prompt, or artifact text changed during the study without a recorded version boundary.
- Reader traces are missing consent, anonymization, artifact label, or completion data.
- The primary endpoint was changed after results were known.
- Statistical or qualitative analysis omits adverse confusion, overexplicitness, or paraphrase-loss evidence.
- Candidate artifacts remain marked non-final, not human-validated, or not finalization-eligible.
- There is no operator-readable evidence map from artifacts to gates.
- Any final claim overstates what the evidence supports.

## Required Audit Outputs

The future audit should produce:

- Auditor ID or role.
- Audit date.
- Evidence packet IDs reviewed.
- Blocking defects.
- Nonblocking concerns.
- Gate recommendations.
- Explicit recommendation to refuse or proceed.

## Current Status

No hostile final audit has passed. The current Phase 13 hostile-audit artifact is a scaffold only.
