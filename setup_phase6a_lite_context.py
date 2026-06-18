from pathlib import Path

ROOT = Path.cwd()


def write(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip() + "\n", encoding="utf-8")


def append_once(path: str, marker: str, text: str) -> None:
    p = ROOT / path
    current = p.read_text(encoding="utf-8") if p.exists() else ""
    if marker not in current:
        p.write_text(current.rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8")


write(
    "context/11_MODEL_READINESS_CONSOLIDATION_SPEC.md",
    """
# Phase 6A-lite: Model-Readiness Consolidation Spec

## Status

Phase 6A-lite is a narrow consolidation phase before live model calls.

Do not implement model/API calls.

Do not implement model_driver.py.

Do not add creative generation.

Do not redesign the architecture.

Do not perform a broad cleanup/refactor.

## Goal

Prepare Abi's deterministic packet modules to safely accept future model-produced artifacts by consolidating packet writing, artifact registration, artifact envelopes, and inspection commands.

This phase should make the existing scaffold more model-ready without changing its behavior.

## Scope

Implement only:

1. Shared packet-writing helper for deterministic packet modules.
2. Shared artifact registration helper if needed.
3. Normalized packet/artifact envelope.
4. Artifact inspection CLI.
5. Run inspection CLI.
6. Tests proving no regression.

## Required normalized envelope

Packet/artifact JSON written by deterministic packet modules should use this shape where practical:

- schema_version
- artifact_type
- run_id
- lineage_id
- parent_ids
- created_by
- fixture_only
- model_call_id
- payload

Rules:

- lineage_id may be null.
- fixture_only may be null or true/false depending on artifact type.
- model_call_id must be null in Phase 6A-lite.
- payload contains the module-specific artifact content.
- Existing behavior must not regress.

## Required CLI

Add artifact inspection commands:

- abi artifact list
- abi artifact show <artifact_id>

Add run inspection commands:

- abi run list
- abi run show <run_id>
- abi run latest

Commands must emit JSON.

## Helper requirements

A shared packet helper should handle:

- creating unique packet directories
- writing JSON artifacts
- registering artifacts
- preserving parent IDs
- returning artifact IDs and paths
- applying the normalized envelope

The packet helper must be used by at least:

- Abi Ear
- one other deterministic packet module

Using it by all deterministic packet modules is allowed if low-risk, but do not over-refactor.

## Acceptance criteria

Phase 6A-lite is complete only when:

- ruff passes
- pytest passes
- all existing demos still work
- artifact list/show works
- run list/show/latest works
- packet helper is used by at least Abi Ear and one other deterministic packet module
- schema_version appears consistently in registered packet artifacts
- model_call_id is present and null in normalized envelopes
- no behavior regression
- abi finalize still refuses when required gates are missing

## Prohibited

- no model_driver.py
- no OpenAI API integration
- no real model calls
- no fake-client model driver yet
- no creative generation
- no human survey UI
- no dashboard
- no dev reset unless specifically needed
- no broad architecture rewrite
- no SKILL.md
""",
)

write(
    "context/plans/PHASE_6A_LITE_MODEL_READINESS.md",
    """
# Phase 6A-lite Model-Readiness Consolidation ExecPlan

## Goal

Make the deterministic Abi runtime ready for future model-produced artifacts.

This is a surgical consolidation phase, not a broad cleanup phase.

## Scope

Add:

- shared packet-writing helper
- normalized artifact envelope helper
- artifact list/show CLI
- run list/show/latest CLI
- tests

Refactor only enough deterministic packet code to prove the helper works.

## Likely files

Likely new files:

src/abi/packets.py
tests/test_packets.py
tests/test_artifact_cli.py
tests/test_run_cli.py

Likely updated files:

src/abi/cli.py
src/abi/modules/abi_ear.py
one or more of:
  src/abi/modules/reread.py
  src/abi/modules/production_harness.py
  src/abi/modules/human_calibration.py
README.md

## CLI requirements

Add:

abi artifact list
abi artifact show <artifact_id>
abi run list
abi run show <run_id>
abi run latest

All commands emit JSON.

## Packet helper requirements

The helper should support:

- unique packet directory creation
- artifact JSON writing
- artifact registry integration
- artifact path return
- parent ID preservation
- normalized envelope

Required envelope fields:

- schema_version
- artifact_type
- run_id
- lineage_id
- parent_ids
- created_by
- fixture_only
- model_call_id
- payload

## Tests

Tests must verify:

- all previous tests still pass
- packet helper writes a normalized envelope
- packet helper registers artifacts
- packet helper creates unique packet directories
- Abi Ear uses the packet helper
- at least one other deterministic packet module uses the packet helper
- schema_version appears in registered packet artifacts
- model_call_id is null in deterministic artifacts
- artifact list returns registered artifacts
- artifact show returns one artifact by ID
- run list returns runs
- run show returns one run by ID
- run latest returns the latest run
- all demos still work
- finalize remains fail-closed

## Constraints

Do not implement model calls.
Do not implement model_driver.py.
Do not implement fake model clients yet.
Do not add creative generation.
Do not add dev reset.
Do not do broad refactoring.

## Done means

Phase 6A-lite is complete when:

- python -m ruff check . passes
- python -m pytest passes
- abi artifact list works
- abi artifact show <artifact_id> works
- abi run list works
- abi run show <run_id> works
- abi run latest works
- existing controller/ear/reread/harness/calibration demos still work
- abi finalize remains fail-closed
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 6A-lite reads:",
    """
## Phase 6A-lite reads:

For Phase 6A-lite, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
7. context/06_DATA_MODEL.md
8. context/08_GATES_AND_EVALUATION.md
9. context/11_MODEL_READINESS_CONSOLIDATION_SPEC.md
10. context/plans/PHASE_6A_LITE_MODEL_READINESS.md

Phase 6A-lite implements narrow model-readiness consolidation only.
""",
)

print("Phase 6A-lite Model-Readiness context files created.")
print("Next:")
print("  git status")
print("  git add context setup_phase6a_lite_context.py")
print('  git commit -m "Add Phase 6A-lite Model-Readiness frozen context"')
print("  git push")
