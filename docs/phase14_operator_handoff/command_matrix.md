# Command Matrix

Last realigned: 2026-06-19

## Required Verification Commands

| Command | Expected |
| --- | --- |
| `git status` | Repository status is visible before and after work. |
| `git log --oneline --decorate -60` | Recent implementation and safety tags are visible. |
| `git tag --list` | Phase and safety tags are visible. |
| `git ls-files` | Tracked file set excludes generated runtime/private files. |
| `.\.venv\Scripts\python.exe -m ruff check .` | Static checks pass. |
| `.\.venv\Scripts\python.exe -m pytest` | Tests pass without API keys. |
| `.\.venv\Scripts\abi.exe status` | Shows current run status. |
| `.\.venv\Scripts\abi.exe artifact list` | Lists registered artifacts. |
| `.\.venv\Scripts\abi.exe run list` | Lists known runs. |
| `.\.venv\Scripts\abi.exe run latest` | Shows the latest run. |
| `.\.venv\Scripts\abi.exe gate list` | Shows profiles including `autonomous_creative_candidate`. |
| `.\.venv\Scripts\abi.exe finalization status --profile autonomous_creative_candidate` | Reports missing internal gates. |
| `.\.venv\Scripts\abi.exe finalize --profile autonomous_creative_candidate` | Refuses finalization. |

## Active CLI Surface

| Area | Commands |
| --- | --- |
| State | `abi init`, `abi status`, `abi finalize` |
| Deterministic demos | `abi ear demo`, `abi reread demo`, `abi harness demo` |
| Controller | `abi controller status`, `abi controller blockers`, `abi controller demo` |
| Artifact inspection | `abi artifact list`, `abi artifact show <artifact_id>` |
| Run inspection | `abi run list`, `abi run show <run_id>`, `abi run latest` |
| Model driver | `abi model-driver demo`, `abi model-driver live-demo --worker <worker>` |
| Model-call inspection | `abi model-call list`, `abi model-call show <model_call_id>` |
| Candidate packets | `abi ear live-demo --client fake`, `abi reread live-demo --client fake`, `abi production live-demo --client fake`, `abi pilot artifact-set --client fake --source-dir <dir>` |
| Rival preservation | `abi pilot import-rival --packet-dir <packet_dir> --rival-file <rival_file>` |
| Internal reader lab | `abi autonomous reader-lab --client fake --packet-dir <packet_dir>` |
| Gates and profiles | `abi gate list`, `abi finalization status`, `abi finalization status --profile autonomous_creative_candidate`, `abi finalize --profile autonomous_creative_candidate` |

## Retired Active Commands

These commands are no longer part of the active runtime path:

- `abi calibration demo`
- `abi evaluation demo`
- `abi final-artifact packet`
- `abi pilot export-reader-kit`

## Guarded OpenAI Paths

OpenAI-backed commands are unavailable unless the operator passes `--allow-live-model` and provides `OPENAI_API_KEY`. Routine tests and fake-client demos require no API key and must not make network calls.
