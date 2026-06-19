# Operator Handoff

Last realigned: 2026-06-19

## Current State

Abi is now oriented as an autonomous creative-engine scaffold. The active path is internal reader-state work, failure diagnosis, targeted recomposition, counterfactual ablation, rival preservation, and fail-closed autonomous finalization.

Abi has a deterministic fake Autonomous Internal Reader Lab v1 scaffold. It has not beaten a strongest rival, cleared fixture-only blockers, passed hostile internal audit, or made any final or phase-shift claim.

## Quick Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\abi.exe gate list
.\.venv\Scripts\abi.exe finalization status --profile autonomous_creative_candidate
.\.venv\Scripts\abi.exe finalize --profile autonomous_creative_candidate
```

The final command should refuse until internal autonomous gates are satisfied.

## Operational Rules

- Treat `runs/`, `db/`, and `outputs/` as runtime state unless a `.gitkeep` placeholder is involved.
- Keep private source material under ignored `inputs/private/`.
- Use fake-client commands for local verification without an API key.
- Run OpenAI paths only when the operator explicitly passes `--allow-live-model` and has set `OPENAI_API_KEY`.
- Do not run human-reader dry runs as the next step.
- Do not use browser ChatGPT sessions as ad hoc readers.
- Do not mark final gates passed from fixture data.

## Handoff Packet

Read these files together:

- `../../README.md`
- `../../context/24_CORE_REALIGNMENT_REMOVE_HUMAN_PAPER_VALIDATION.md`
- `command_matrix.md`
- `known_blockers.md`
- `finalization_profile_summary.md`
- `fresh_clone_verification.md`

The next operator should begin with the README, then plan bounded targeted recomposition and ablation execution on a new branch after this work is committed and main is clean.
