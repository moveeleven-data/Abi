# Fresh Clone Verification

Last checked: 2026-06-18

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
.\.venv\Scripts\abi.exe final-artifact packet --client fake
.\.venv\Scripts\abi.exe finalization status --profile final_artifact
.\.venv\Scripts\abi.exe finalize --profile final_artifact
```

`finalize --profile final_artifact` should fail closed. That failure is expected and is part of the verification.

## Optional Guarded Checks

Do not run a real OpenAI call unless the operator explicitly intends to. OpenAI paths require both `--allow-live-model` and `OPENAI_API_KEY`.

Examples:

```powershell
.\.venv\Scripts\abi.exe ear live-demo --client openai
.\.venv\Scripts\abi.exe final-artifact packet --client openai
```

Without `--allow-live-model`, these should refuse before any live call.
