# Project Abi

Abi v0.1 is a Self-Isomorphic Causal Reread Compiler scaffold. The repository is currently an evidence-ready research harness, not a proven writing system and not a final artifact.

The runtime centers on a fail-closed controller, immutable JSON artifacts, SQLite-backed state, guarded model-call surfaces, and finalization gates. Demos and fake-client paths are for engineering verification unless a future protocol explicitly collects real evidence.

## Project Status

- Current implemented surface: infrastructure through the first pilot artifact-set scaffold.
- Current validation status: no real human validation has run.
- Current finalization status: `final_artifact` remains ineligible and must refuse.
- Current artifact status: candidates remain non-final, not human-validated, not finalization-eligible, and no-phase-shift-claim.
- Current OpenAI status: guarded paths exist, but no live call runs unless explicitly opted in.

## Quickstart

Install locally:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run the basic checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\abi.exe status
.\.venv\Scripts\abi.exe finalization status --profile final_artifact
```

Expected finalization behavior:

```powershell
.\.venv\Scripts\abi.exe finalize --profile final_artifact
```

That command should refuse until real final-artifact evidence exists.

## Current Capabilities

Deterministic local demos:

```powershell
.\.venv\Scripts\abi.exe ear demo
.\.venv\Scripts\abi.exe reread demo
.\.venv\Scripts\abi.exe harness demo
.\.venv\Scripts\abi.exe calibration demo
```

Fake-client and scaffold packets:

```powershell
.\.venv\Scripts\abi.exe model-driver demo
.\.venv\Scripts\abi.exe ear live-demo --client fake
.\.venv\Scripts\abi.exe reread live-demo --client fake
.\.venv\Scripts\abi.exe production live-demo --client fake
.\.venv\Scripts\abi.exe evaluation demo --client fake
.\.venv\Scripts\abi.exe final-artifact packet --client fake
.\.venv\Scripts\abi.exe pilot artifact-set --client fake --source-dir fixtures/production_harness
```

Inspection commands:

```powershell
.\.venv\Scripts\abi.exe artifact list
.\.venv\Scripts\abi.exe artifact show <artifact_id>
.\.venv\Scripts\abi.exe run list
.\.venv\Scripts\abi.exe run show <run_id>
.\.venv\Scripts\abi.exe run latest
.\.venv\Scripts\abi.exe model-call list
.\.venv\Scripts\abi.exe model-call show <model_call_id>
```

Controller and gate inspection:

```powershell
.\.venv\Scripts\abi.exe controller status
.\.venv\Scripts\abi.exe controller blockers
.\.venv\Scripts\abi.exe controller demo
.\.venv\Scripts\abi.exe gate list
.\.venv\Scripts\abi.exe finalization status
.\.venv\Scripts\abi.exe finalization status --profile final_artifact
```

## Current Non-Claims

Do not claim from this repo state that:

- Abi produces phase-shift-level writing.
- Abi has passed real human validation.
- Abi has beaten strong baselines.
- Abi has passed hostile final audit.
- Abi is paper-ready.
- Any generated candidate is a final artifact.

Fixture and fake-client outputs are engineering artifacts. They cannot satisfy final-artifact gates.

## Guarded OpenAI Usage

OpenAI-backed commands refuse unless `--allow-live-model` is passed. Commands that pass that flag also require `OPENAI_API_KEY`. The default live model is code-defined and can be overridden with `ABI_OPENAI_MODEL`.

Examples that refuse without opt-in:

```powershell
.\.venv\Scripts\abi.exe model-driver live-demo --worker abi_ear_germ_analysis
.\.venv\Scripts\abi.exe model-driver live-demo --worker abi_ear_field_model
.\.venv\Scripts\abi.exe ear live-demo --client openai
.\.venv\Scripts\abi.exe reread live-demo --client openai
.\.venv\Scripts\abi.exe production live-demo --client openai
.\.venv\Scripts\abi.exe evaluation demo --client openai
.\.venv\Scripts\abi.exe final-artifact packet --client openai
.\.venv\Scripts\abi.exe pilot artifact-set --client openai --source-dir inputs/private/phase16_source
```

Opt-in examples:

```powershell
.\.venv\Scripts\abi.exe model-driver live-demo --worker abi_ear_germ_analysis --allow-live-model
.\.venv\Scripts\abi.exe model-driver live-demo --worker abi_ear_field_model --allow-live-model
.\.venv\Scripts\abi.exe ear live-demo --client openai --allow-live-model --max-model-calls 8
.\.venv\Scripts\abi.exe reread live-demo --client openai --allow-live-model --max-model-calls 12
.\.venv\Scripts\abi.exe production live-demo --client openai --allow-live-model --max-model-calls 24
.\.venv\Scripts\abi.exe evaluation demo --client openai --allow-live-model --max-model-calls 12
.\.venv\Scripts\abi.exe final-artifact packet --client openai --allow-live-model --max-model-calls 8
.\.venv\Scripts\abi.exe pilot artifact-set --client openai --source-dir inputs/private/phase16_source --allow-live-model --max-model-calls 36
```

Install optional live dependencies only for an intentional manual live smoke test:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[live]"
```

## Private Source Material Warning

The repository may be public. Do not commit private source material.

Use ignored local paths for private source files:

```text
inputs/private/
```

The pilot artifact-set command hashes source files and records filenames. It must not copy private source content into tracked docs.

## Validation Roadmap

The next real work is evidence, not new claims:

1. Freeze source material and artifact-set rules.
2. Select or import a real strongest rival under protocol rules.
3. Generate or import non-fixture baselines with stored prompts, budgets, and model-call records.
4. Run a small human-reader pilot only after task wording, exclusion rules, blindness rules, and scoring are locked.
5. Run hostile audit before any final-artifact gate is considered.
6. Keep `final_artifact` finalization fail-closed until all required evidence is reviewed.

## Where To Find Docs

- [Docs index](docs/INDEX.md)
- [Phase 14 operator handoff](docs/phase14_operator_handoff/operator_handoff.md)
- [Phase 15 validation protocol](docs/phase15_real_validation_protocol/validation_protocol.md)
- [Known blockers](docs/phase14_operator_handoff/known_blockers.md)
- [Fresh clone verification](docs/phase14_operator_handoff/fresh_clone_verification.md)
- [Frozen context specs](context/README.md)

Setup context scripts live under:

```text
tools/setup_context_scripts/
```
