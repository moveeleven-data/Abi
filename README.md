# Project Abi

Abi v0.1 is an internal autonomous creative-engine scaffold. It is built around
deterministic packet generation, immutable artifact lineage, structured model-call
records, and fail-closed controller gates.

The current active path is internal: source material can move through candidate and
baseline packet construction, an autonomous internal reader lab, failure diagnosis,
targeted recomposition planning, counterfactual ablation planning, strongest-rival
pressure checks, and autonomous closed-loop revision.

Abi is not currently a public validation harness, a paper-ready evaluation system, or a
final writing product.

## Current Status

Implemented today:

- Python package and CLI: `abi`
- SQLite-backed run, artifact, gate, and model-call state
- Immutable JSON artifact envelopes with hashes and parent IDs
- Deterministic Abi Ear and Minimal Reread demo packets
- Deterministic production-harness and pilot artifact-set scaffolds
- Strongest-rival import into pilot packets
- Sealed model-driver layer with structured-output validation
- Guarded fake/stub and opt-in live-worker paths
- Autonomous Internal Reader Lab v1
- Autonomous Closed-Loop Revision v1
- Policy-driven finalization profiles

The active finalization profile is:

```text
autonomous_creative_candidate
```

That profile is intentionally fail-closed until its internal gates are present and
passing.

## What Abi Does

Abi records work as packets under `runs/<run_id>/.../packet_NNNN/`. Each packet contains
JSON artifacts wrapped in a normalized envelope:

```text
schema_version
artifact_type
run_id
lineage_id
parent_ids
created_by
fixture_only
model_call_id
payload
```

Artifacts are registered in SQLite with SHA-256 hashes and parent IDs. Model-shaped
outputs are validated against local schemas before any parsed artifact is registered.
Invalid model output records a failed model call and stops packet assembly.

Finalization is controlled only by controller/finalization code. Workers can produce
evidence and blocker reports, but workers cannot finalize Abi.

## Current Non-Claims

Do not claim from this repo state that:

- Abi has produced a final artifact.
- Abi has proven phase-shift-level writing.
- Abi has passed real human validation.
- Abi has beaten a strongest rival.
- Abi has cleared hostile final audit.
- Fixture or fake-client outputs are real validation evidence.

The current system is an engineering workbench for internal autonomous revision, not a
completed validation claim.

## Local Verification

Install in editable mode with developer tools:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
```

Inspect current state:

```powershell
.\.venv\Scripts\abi.exe status
.\.venv\Scripts\abi.exe finalization status --profile autonomous_creative_candidate
```

Expected behavior:

```powershell
.\.venv\Scripts\abi.exe finalize --profile autonomous_creative_candidate
```

This should refuse unless all required autonomous gates are satisfied.

## Useful Local Commands

Deterministic demos:

```powershell
.\.venv\Scripts\abi.exe ear demo
.\.venv\Scripts\abi.exe reread demo
.\.venv\Scripts\abi.exe harness demo
```

Candidate and autonomous fake paths:

```powershell
.\.venv\Scripts\abi.exe pilot artifact-set --client fake --source-dir fixtures/production_harness
.\.venv\Scripts\abi.exe autonomous reader-lab --client fake --packet-dir <pilot_packet_dir>
.\.venv\Scripts\abi.exe autonomous revise --client fake --reader-lab-packet <reader_lab_packet_dir>
```

Inspection:

```powershell
.\.venv\Scripts\abi.exe artifact list
.\.venv\Scripts\abi.exe run latest
.\.venv\Scripts\abi.exe model-call list
.\.venv\Scripts\abi.exe gate list
.\.venv\Scripts\abi.exe controller status
.\.venv\Scripts\abi.exe controller blockers
.\.venv\Scripts\abi.exe controller demo
```

Some live model paths exist, but they are guarded, opt-in only, and not required for the
local fake/demo workflows.

## Repository Map

```text
src/abi/                      runtime package
src/abi/controller/           gates, controller decisions, finalization policy
src/abi/modules/              packet-producing pipelines
tests/                        regression tests
fixtures/                     non-private fixture inputs
context/                      frozen phase specs and historical context
docs/                         operator handoff and historical protocol docs
tools/setup_context_scripts/  phase context setup scripts
```

Runtime and private files are intentionally ignored:

```text
db/*.sqlite
runs/*
outputs/*
inputs/private/
.env
```

## Documentation

Start here:

- [Docs index](docs/INDEX.md)
- [Context README](context/README.md)
- [Core realignment context](context/24_CORE_REALIGNMENT_REMOVE_HUMAN_PAPER_VALIDATION.md)
- [Architecture freeze](context/00_ARCHITECTURE_FREEZE.md)
- [Gate policy v2 spec](context/19_FINALIZATION_GATE_POLICY_V2_SPEC.md)
- [Operator handoff](docs/phase14_operator_handoff/operator_handoff.md)
- [Known blockers](docs/phase14_operator_handoff/known_blockers.md)

The `context/` files are frozen phase specs. They are useful historical records, but not
all of them are current runtime instructions.
