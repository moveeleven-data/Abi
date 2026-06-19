# Project Abi

Abi v0.1 is an autonomous creative-engine scaffold. The active path is internal: source material moves through Abi Ear, Minimal Reread, candidate/baseline/rival set construction, internal reader-state workers, failure diagnosis, targeted recomposition, counterfactual ablation, rival preservation, and fail-closed autonomous finalization.

Abi is not a public-validation harness right now. Human readers, browser ChatGPT reader sessions, paper-grade validation, and external study tooling are outside the core engine path.

## Project Status

- Current implemented surface: deterministic infrastructure, artifact/run registries, guarded model-call records, Abi Ear, Minimal Reread, production/candidate scaffolds, pilot candidate/baseline/rival artifact sets, strongest-rival import, Autonomous Internal Reader Lab v1 fake packets, and Autonomous Closed-Loop Revision v1 fake packets.
- Active finalization profile: `autonomous_creative_candidate`.
- Current finalization status: fail-closed until internal autonomous gates are explicitly satisfied.
- Legacy external profile: `final_artifact` remains present as historical/external validation policy, but it is not the active development path.
- Current OpenAI status: guarded paths exist; no live call runs unless explicitly opted in.

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
.\.venv\Scripts\abi.exe finalization status --profile autonomous_creative_candidate
```

Expected finalization behavior:

```powershell
.\.venv\Scripts\abi.exe finalize --profile autonomous_creative_candidate
```

That command should refuse until the internal autonomous gates are present and passing.

## Current Capabilities

Deterministic local demos:

```powershell
.\.venv\Scripts\abi.exe ear demo
.\.venv\Scripts\abi.exe reread demo
.\.venv\Scripts\abi.exe harness demo
```

Fake-client and candidate packet paths:

```powershell
.\.venv\Scripts\abi.exe model-driver demo
.\.venv\Scripts\abi.exe ear live-demo --client fake
.\.venv\Scripts\abi.exe reread live-demo --client fake
.\.venv\Scripts\abi.exe production live-demo --client fake
.\.venv\Scripts\abi.exe pilot artifact-set --client fake --source-dir fixtures/production_harness
.\.venv\Scripts\abi.exe autonomous reader-lab --client fake --packet-dir <packet_dir>
.\.venv\Scripts\abi.exe autonomous revise --client fake --reader-lab-packet <reader_lab_packet_dir>
```

Strongest-rival preservation:

```powershell
.\.venv\Scripts\abi.exe pilot import-rival --packet-dir <packet_dir> --rival-file <rival_file>
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
.\.venv\Scripts\abi.exe finalization status --profile autonomous_creative_candidate
```

## Current Non-Claims

Do not claim from this repo state that:

- Abi produces phase-shift-level writing.
- Abi has proven autonomous creative success from the internal reader lab or revision loop.
- Abi has beaten a strongest rival.
- Abi has passed hostile internal audit.
- Any generated candidate is final.
- External human or public validation is part of the active runtime.

Fixture and fake-client outputs are engineering artifacts. They do not satisfy autonomous finalization gates by themselves.

## Guarded OpenAI Usage

OpenAI-backed commands refuse unless `--allow-live-model` is passed. Commands that pass that flag also require `OPENAI_API_KEY`. The default live model is code-defined and can be overridden with `ABI_OPENAI_MODEL`.

Examples that refuse without opt-in:

```powershell
.\.venv\Scripts\abi.exe model-driver live-demo --worker abi_ear_germ_analysis
.\.venv\Scripts\abi.exe model-driver live-demo --worker abi_ear_field_model
.\.venv\Scripts\abi.exe ear live-demo --client openai
.\.venv\Scripts\abi.exe reread live-demo --client openai
.\.venv\Scripts\abi.exe production live-demo --client openai
.\.venv\Scripts\abi.exe pilot artifact-set --client openai --source-dir inputs/private/phase16_source
.\.venv\Scripts\abi.exe autonomous reader-lab --client openai --packet-dir <packet_dir>
.\.venv\Scripts\abi.exe autonomous revise --client openai --reader-lab-packet <reader_lab_packet_dir>
```

Opt-in examples:

```powershell
.\.venv\Scripts\abi.exe model-driver live-demo --worker abi_ear_germ_analysis --allow-live-model
.\.venv\Scripts\abi.exe model-driver live-demo --worker abi_ear_field_model --allow-live-model
.\.venv\Scripts\abi.exe ear live-demo --client openai --allow-live-model --max-model-calls 8
.\.venv\Scripts\abi.exe reread live-demo --client openai --allow-live-model --max-model-calls 12
.\.venv\Scripts\abi.exe production live-demo --client openai --allow-live-model --max-model-calls 24
.\.venv\Scripts\abi.exe pilot artifact-set --client openai --source-dir inputs/private/phase16_source --allow-live-model --max-model-calls 36
.\.venv\Scripts\abi.exe autonomous reader-lab --client openai --packet-dir <packet_dir> --allow-live-model --max-model-calls 12
.\.venv\Scripts\abi.exe autonomous revise --client openai --reader-lab-packet <reader_lab_packet_dir> --allow-live-model --max-model-calls 12
```

Do not run live OpenAI commands casually. Install optional live dependencies only for an intentional manual live smoke test:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[live]"
```

## Private Source Material Warning

The repository may be public. Do not commit private source material.

Use ignored local paths for private source files:

```text
inputs/private/
```

The pilot artifact-set command hashes source files and records filenames. Private source contents may be sent to OpenAI only during explicit `--allow-live-model` runs and must stay out of tracked docs.

## Autonomous Roadmap

The current development milestone is **Autonomous Closed-Loop Revision v1**.

Do not use browser ChatGPT sessions as ad hoc readers. Do not use external humans as core Abi evaluators.

Near-term work should focus on:

1. Repeat closed-loop revision as a second autonomous cycle.
2. Expand internal reader-state and recomposition workers beyond deterministic fake mode.
3. Preserve strongest-rival pressure through every internal comparison.
4. Keep fail-closed `autonomous_creative_candidate` readiness.

## Where To Find Docs

- [Docs index](docs/INDEX.md)
- [Core realignment context](context/24_CORE_REALIGNMENT_REMOVE_HUMAN_PAPER_VALIDATION.md)
- [Architecture freeze](context/00_ARCHITECTURE_FREEZE.md)
- [Gate policy v2 spec](context/19_FINALIZATION_GATE_POLICY_V2_SPEC.md)
- [Phase 14 operator handoff](docs/phase14_operator_handoff/operator_handoff.md)
- [Known blockers](docs/phase14_operator_handoff/known_blockers.md)
- [Frozen context specs](context/README.md)

Setup context scripts live under:

```text
tools/setup_context_scripts/
```
