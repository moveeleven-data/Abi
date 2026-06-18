# Phase 15 Operator Checklist

Last checked: 2026-06-18

## Phase 15 Completion

- Confirm the protocol documents exist under `docs/phase15_real_validation_protocol/`.
- Confirm no runtime code was changed for Phase 15.
- Confirm no real validation was run.
- Confirm no human data was collected.
- Confirm no real OpenAI production pass was run.
- Confirm no final gates were marked passed.
- Confirm no `SKILL.md` was created.

## Required Checks

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\abi.exe finalization status --profile final_artifact
.\.venv\Scripts\abi.exe finalize --profile final_artifact
```

The finalization commands must show that the `final_artifact` profile remains ineligible and finalization refuses.

## Before A Future Pilot

- Freeze artifact set.
- Freeze baseline generation rules.
- Freeze strongest-rival selection.
- Freeze reader task wording.
- Freeze exclusion criteria.
- Freeze analysis plan.
- Prepare consent and data-use note.
- Prepare neutral labels and randomized ordering.
- Prepare hostile-audit checklist.

## Before Any Future Final Claim

- Verify real human validation passed under the locked protocol.
- Verify strongest-rival comparison passed.
- Verify raw-model baseline comparison passed.
- Verify hostile final audit passed.
- Verify no fixture-only evidence is used as a final claim.
- Verify no blocking defects remain.
- Obtain final operator approval.

Until then, Abi remains non-final and not paper-ready.
