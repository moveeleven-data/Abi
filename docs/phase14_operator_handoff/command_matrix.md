# Command Matrix

Last checked: 2026-06-18

## Required Phase 14 Commands

| Command | Expected | Observed |
| --- | --- | --- |
| `git status` | Repository status is visible before audit work. | Clean before Phase 14 docs were added. |
| `git log --oneline --decorate -60` | Recent phase commits and tags are visible. | Phase 0 through Phase 13 implementation tags appear in the recent history. |
| `git tag --list` | Completion tags exist. | Tags through `phase-13-final-artifact-paper-packet-complete` exist. |
| `git ls-files` | Tracked file set excludes generated runtime files. | Only placeholders under `db/`, `outputs/`, and `runs/` are tracked. |
| `.\.venv\Scripts\python.exe -m ruff check .` | Static checks pass. | Passed. |
| `.\.venv\Scripts\python.exe -m pytest` | Full test suite passes without API keys. | Passed, 126 tests. |
| `.\.venv\Scripts\abi.exe status` | Shows active run status. | Succeeded. |
| `.\.venv\Scripts\abi.exe artifact list` | Lists artifacts from the active run. | Succeeded. |
| `.\.venv\Scripts\abi.exe run list` | Lists known runs. | Succeeded. |
| `.\.venv\Scripts\abi.exe run latest` | Shows latest run. | Succeeded. |
| `.\.venv\Scripts\abi.exe final-artifact packet --client fake` | Creates a fake/fixture, non-final packet. | Succeeded; packet artifacts were written under ignored `runs/`. |
| `.\.venv\Scripts\abi.exe finalization status --profile final_artifact` | Reports ineligible. | Succeeded and listed missing final-artifact gates plus fixture/non-final blockers. |
| `.\.venv\Scripts\abi.exe finalize --profile final_artifact` | Refuses finalization. | Refused as expected. |

## Preserved CLI Surface

| Area | Commands |
| --- | --- |
| Phase 0 state | `abi init`, `abi status`, `abi finalize` |
| Deterministic demos | `abi ear demo`, `abi reread demo`, `abi harness demo`, `abi calibration demo` |
| Controller | `abi controller status`, `abi controller blockers`, `abi controller demo` |
| Artifact inspection | `abi artifact list`, `abi artifact show <artifact_id>` |
| Run inspection | `abi run list`, `abi run show <run_id>`, `abi run latest` |
| Model-driver fake path | `abi model-driver demo`, `abi model-call list`, `abi model-call show <model_call_id>` |
| Guarded worker demos | `abi model-driver live-demo --worker abi_ear_germ_analysis`, `abi model-driver live-demo --worker abi_ear_field_model` |
| Live packet scaffolds | `abi ear live-demo --client fake`, `abi reread live-demo --client fake`, `abi production live-demo --client fake`, `abi evaluation demo --client fake`, `abi final-artifact packet --client fake` |
| Guarded OpenAI packet paths | `abi ear live-demo --client openai --allow-live-model --max-model-calls 8`, `abi reread live-demo --client openai --allow-live-model --max-model-calls 12`, `abi production live-demo --client openai --allow-live-model --max-model-calls 24`, `abi evaluation demo --client openai --allow-live-model --max-model-calls 12`, `abi final-artifact packet --client openai --allow-live-model --max-model-calls 8` |
| Gates and profiles | `abi gate list`, `abi finalization status`, `abi finalization status --profile final_artifact`, `abi finalize --profile final_artifact` |

## Unavailable Without Explicit Guard

OpenAI-backed commands are intentionally unavailable unless the operator passes `--allow-live-model` and provides `OPENAI_API_KEY`. This audit did not run any real live OpenAI call.
