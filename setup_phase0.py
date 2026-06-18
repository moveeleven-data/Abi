from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()


def write(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip() + "\n", encoding="utf-8")


def touch(path: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


print(f"Setting up Abi Phase 0 context in: {ROOT}")

if not (ROOT / ".git").exists():
    run(["git", "init"])

run(["git", "config", "--global", "init.defaultBranch", "main"])

dirs = [
    "context/plans",
    "inputs/drafts",
    "inputs/notes",
    "inputs/references",
    "inputs/human_reader_trials",
    "canon",
    "cards",
    "schemas",
    "prompts/abi_ear",
    "prompts/reread",
    "src/abi/controller",
    "src/abi/modules",
    "src/abi/metrics",
    "tests",
    "runs",
    "outputs",
    "db",
]

for d in dirs:
    (ROOT / d).mkdir(parents=True, exist_ok=True)

touch("runs/.gitkeep")
touch("outputs/.gitkeep")
touch("db/.gitkeep")

write(
    ".gitignore",
    """
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
dist/
build/
*.egg-info/

.env
.env.*

db/*.sqlite
db/*.sqlite-*
runs/*
outputs/*

!runs/.gitkeep
!outputs/.gitkeep
!db/.gitkeep
""",
)

write(
    ".env.example",
    """
# Phase 0 does not use model calls.
# Keep real secrets in .env, never in Git.

ABI_DB_PATH=db/abi.sqlite
ABI_RUNS_DIR=runs
ABI_OUTPUTS_DIR=outputs
""",
)

write(
    "AGENTS.md",
    """
# Project Abi Agent Instructions

## Project state

Project Abi v0.1 is frozen for Phase 0.

Abi is a Self-Isomorphic Causal Reread Compiler, but Phase 0 implements infrastructure only.

Do not implement creative generation, model calls, Abi Ear, reader simulation, or the full reread loop in Phase 0.

## Core architecture

Abi runtime is:

- deterministic fail-closed controller
- immutable artifact registry / lineage graph
- SQLite-backed external state
- bounded future model workers
- gate-based finalization

The database is memory. Model context is only a workbench.

No worker may finalize. Only controller/finalization code may finalize, and it must refuse if required gates are missing or failed.

## Phase 0 scope

Implement only:

- Python package skeleton
- pyproject.toml
- CLI with abi init, abi status, and a finalization refusal path
- SQLite initialization
- run folder creation
- deterministic ID helpers
- hash helpers
- artifact registry
- gate records
- tests proving missing gates block finalization

Use standard library where reasonable. Avoid unnecessary runtime dependencies.

## Required commands

After implementation, these should work:

- python -m pip install -e .[dev]
- pytest
- abi init
- abi status

## Forbidden in Phase 0

- no model calls
- no OpenAI API integration
- no prose generation
- no Abi Ear implementation
- no reader models
- no dashboard
- no skills / SKILL.md
- no large framework adoption
- no premature Phase 1 code

## Done means

Phase 0 is done only when:

- tests pass
- abi init creates the database and required folders
- abi status reports current state
- artifacts can be registered with hash and parent IDs
- gates can be stored and queried
- finalization refuses when required gates are missing
- blocker report explains missing gates
""",
)

write(
    "context/00_ARCHITECTURE_FREEZE.md",
    """
# Project Abi v0.1 Architecture Freeze

Abi is a Self-Isomorphic Causal Reread Compiler.

Core formulation:

A symbolic abiogenesis machine produces a symbolic abiogenesis artifact by undergoing symbolic abiogenesis, then proves that the artifact caused symbolic abiogenesis in the reader's understanding.

Core equation:

Artwork = Artifact + ΔReaderState

Phase 0 does not implement the reader loop. Phase 0 implements the infrastructure needed to support it later.

## Runtime architecture

Abi is not a free-roaming agent.

Abi is controlled by a deterministic fail-closed controller.

The controller may later call specialist model workers, but workers never own state and never finalize.

All outputs become immutable artifacts.

Artifact lineage is a DAG.

The run controller is cyclic and budgeted.

SQLite is the initial external state store.

## Core future loop

reader-state trace
→ diagnosed failure
→ targeted intervention
→ counterfactual proof

Phase 0 must preserve the finalization invariant even before the creative loop exists.

## Phase 0 invariant

The first useful demo is not prose.

The first useful demo is a fake run that refuses to finalize because required gates are missing.
""",
)

write(
    "context/00_CONTEXT_INDEX.md",
    """
# Context Index

For Phase 0, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/01_PROJECT_BRIEF.md
4. context/02_ENGINEERING_CONTRACT.md
5. context/06_DATA_MODEL.md
6. context/08_GATES_AND_EVALUATION.md
7. context/plans/PHASE_0_REPO_SKELETON.md

Do not read or implement speculative full-system documents for Phase 0 unless explicitly asked.
""",
)

write(
    "context/01_PROJECT_BRIEF.md",
    """
# Project Brief

Abi is a narrow creative compiler for self-isomorphic symbolic-abiogenesis artifacts.

The full system target is:

- machine undergoes symbolic abiogenesis
- artifact embodies symbolic abiogenesis
- reader understanding undergoes symbolic abiogenesis

The reader is a first-class substrate of the artwork.

Phase 0 does not implement creative behavior. It builds the infrastructure spine that later phases require.

Phase 0 target:

- repo skeleton
- CLI
- SQLite
- run state
- artifact registry
- gate records
- fail-closed finalization refusal
- tests
""",
)

write(
    "context/02_ENGINEERING_CONTRACT.md",
    """
# Engineering Contract

## State

SQLite is the source of truth.

The filesystem stores artifacts and run folders.

The model context is never memory.

## Artifacts

Artifacts are immutable.

Every artifact must have:

- id
- run_id
- lineage_id, nullable
- type
- path
- hash
- created_at
- parent_ids_json

## Controller

The controller owns phase, state, gates, and finalization.

No worker can finalize.

## Phase 0 dependency policy

Prefer Python standard library.

Allowed dev dependencies:

- pytest
- ruff

Avoid runtime dependencies unless justified.
""",
)

write(
    "context/06_DATA_MODEL.md",
    """
# Data Model

Phase 0 requires only the infrastructure subset.

## Tables

runs:
- id TEXT PRIMARY KEY
- created_at TEXT NOT NULL
- status TEXT NOT NULL
- active_phase TEXT NOT NULL
- best_lineage_id TEXT
- strongest_rival_lineage_id TEXT
- final_artifact_id TEXT

artifacts:
- id TEXT PRIMARY KEY
- run_id TEXT NOT NULL
- lineage_id TEXT
- type TEXT NOT NULL
- path TEXT NOT NULL
- hash TEXT NOT NULL
- created_at TEXT NOT NULL
- parent_ids_json TEXT NOT NULL

gates:
- id TEXT PRIMARY KEY
- run_id TEXT NOT NULL
- lineage_id TEXT
- gate_name TEXT NOT NULL
- passed INTEGER NOT NULL
- blocking_defects_json TEXT NOT NULL
- evaluated_at TEXT NOT NULL

Phase 0 may also add a metadata or schema_migrations table if useful.

## Future schemas not implemented in Phase 0

ReaderState
ReaderStateTransition
ReaderTransformationProof
SelfIsomorphismCheck
FormalProblem
FieldModel
Move
DraftVersion
RereadTrace
CounterfactualResult
""",
)

write(
    "context/08_GATES_AND_EVALUATION.md",
    """
# Gates and Evaluation

Phase 0 implements gate infrastructure, not literary gates.

## Finalization invariant

A run cannot finalize unless every required gate:

- exists
- has been evaluated
- passed
- has no fatal blocking defects

## Phase 0 required gates

For fake-run finalization refusal, use placeholder required gates:

- infrastructure_initialized
- artifact_registry_ready
- required_phase0_tests_passed

The controller/finalization code must refuse finalization when any required gate is missing or failed.

## Blocker report

Finalization refusal must return or print:

- run_id
- refused: true
- missing_gates
- failed_gates
- message
""",
)

write(
    "context/plans/PHASE_0_REPO_SKELETON.md",
    """
# Phase 0 Repo Skeleton ExecPlan

## Goal

Implement the infrastructure spine of Abi.

## Scope

Create:

- pyproject.toml
- README.md
- src/abi package
- CLI with abi init, abi status, and finalization refusal path
- config module
- SQLite module
- ID helper
- hashing helper
- artifact registry
- controller gate/finalization modules
- tests

## Expected tree

src/abi/
  __init__.py
  cli.py
  config.py
  db.py
  ids.py
  hashing.py
  artifacts.py
  controller/
    __init__.py
    gates.py
    finalization.py
    state.py

tests/
  test_init.py
  test_artifacts.py
  test_gates.py
  test_finalization.py

## CLI behavior

abi init:

- creates db/
- creates runs/
- creates outputs/
- initializes SQLite
- creates or reports active run

abi status:

- reports database path
- reports run count
- reports latest run if present
- reports artifact count
- reports gate count

Finalization refusal path:

- may be exposed as abi finalize or a tested function
- refuses when required gates are missing
- emits blocker report

## Constraints

No model calls.
No prose generation.
No Abi Ear.
No full controller loop.
No SKILL.md.
""",
)

write(
    "README.md",
    """
# Project Abi

Abi v0.1 is a Self-Isomorphic Causal Reread Compiler.

Phase 0 implements infrastructure only:

- CLI
- SQLite
- run folders
- artifact registry
- gates
- fail-closed finalization refusal
- tests

No creative generation or model calls exist in Phase 0.
""",
)

if not (ROOT / ".venv").exists():
    run([sys.executable, "-m", "venv", ".venv"])

venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])

print()
print("Abi Phase 0 frozen context setup complete.")
print("Next commands:")
print("  git status")
print("  git add .")
print('  git commit -m "Add Abi Phase 0 frozen context"')
