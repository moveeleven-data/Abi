# Fresh Clone Verification

Last realigned: 2026-06-19

## Setup

From a fresh checkout on Windows PowerShell:

```powershell
git clone <repo-url> abi
cd abi
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

No API key is required for tests or fake-client demos.

## Required Verification

```powershell
git status
git log --oneline --decorate -60
git tag --list
git ls-files
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\abi.exe status
.\.venv\Scripts\abi.exe artifact list
.\.venv\Scripts\abi.exe run list
.\.venv\Scripts\abi.exe run latest
.\.venv\Scripts\abi.exe gate list
.\.venv\Scripts\abi.exe finalization status --profile autonomous_creative_candidate
.\.venv\Scripts\abi.exe finalize --profile autonomous_creative_candidate
```

`finalize --profile autonomous_creative_candidate` should fail closed until the internal autonomous gates exist and pass. That refusal is expected.

## Optional Guarded Checks

Do not run a real OpenAI call unless the operator explicitly intends to. OpenAI paths require both `--allow-live-model` and `OPENAI_API_KEY`.

Examples that should refuse without opt-in:

```powershell
.\.venv\Scripts\abi.exe ear live-demo --client openai
.\.venv\Scripts\abi.exe reread live-demo --client openai
.\.venv\Scripts\abi.exe production live-demo --client openai
.\.venv\Scripts\abi.exe pilot artifact-set --client openai --source-dir inputs/private/phase16_source
```
