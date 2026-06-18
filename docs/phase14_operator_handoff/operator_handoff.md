# Operator Handoff

Last checked: 2026-06-18

## Current State

Abi is an audited research scaffold through Phase 13. Phase 14 adds this handoff documentation only. The system can initialize runs, register immutable artifacts, run deterministic demos, run fake-client packet scaffolds, record model-call metadata, inspect artifacts and runs, and evaluate fail-closed finalization profiles.

Abi is not a proven writing system yet. It has not passed real human validation, has not beaten strong baselines, has not completed hostile final audit, and is not paper-ready.

## Quick Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\abi.exe final-artifact packet --client fake
.\.venv\Scripts\abi.exe finalization status --profile final_artifact
.\.venv\Scripts\abi.exe finalize --profile final_artifact
```

The final command should refuse for the `final_artifact` profile.

## Operational Rules

- Treat `runs/`, `db/`, and `outputs/` as runtime state unless a `.gitkeep` placeholder is involved.
- Use fake-client commands for local verification without an API key.
- Run OpenAI paths only when the operator explicitly passes `--allow-live-model` and has set `OPENAI_API_KEY`.
- Do not mark final gates passed from fixture data.
- Do not claim phase-shift, paper readiness, or real validation from demo packets.

## Handoff Packet

Read these files together:

- `audit_report.md`
- `command_matrix.md`
- `phase_inventory.md`
- `known_blockers.md`
- `finalization_profile_summary.md`
- `fixture_evidence_safety_report.md`
- `live_model_guardrail_report.md`
- `artifact_schema_envelope_report.md`
- `fresh_clone_verification.md`
- `next_validation_roadmap.md`

The next operator should begin with `fresh_clone_verification.md`, then read `known_blockers.md` and `next_validation_roadmap.md` before planning Phase 15.
