# Live Run Budget Plan

Last checked: 2026-06-18

## Status

This plan defines future budget controls only. It does not run a live OpenAI pass.

## Budget Principles

Future live runs must be bounded before execution. Budgets should cover model calls, artifacts, candidate selection, baselines, and reader load.

Every live model call must preserve provider, model, worker role, schema, input hash, output path, status, and model-call ID.

## Suggested Future Call Budgets

| Path | Suggested Maximum | Notes |
| --- | --- | --- |
| Abi Ear live packet | 8 model-shaped calls | Matches existing guarded packet budget. |
| Minimal Reread live packet | 12 model-shaped calls | Matches existing guarded reread budget. |
| Production live packet | 24 model-shaped calls | Includes upstream Abi Ear and Minimal Reread packet calls. |
| Evaluation baseline live path | 12 model-shaped calls | For future non-fixture baseline generation only. |
| Final-artifact packet path | 8 model-shaped calls | For packet/report shaping only, not validation. |

## Approval Rules

Before any real live production pass:

- The operator must approve `--allow-live-model`.
- `OPENAI_API_KEY` must be set intentionally.
- The model must be documented through `ABI_OPENAI_MODEL` or the code default.
- The run must record the exact command and max-model-call budget.
- The output must remain candidate-only until validation evidence exists.

## Stop Conditions

Stop the run if a budget is exceeded, schema validation fails, client failure blocks required artifacts, packet IDs collide, or any artifact is incorrectly marked final.
