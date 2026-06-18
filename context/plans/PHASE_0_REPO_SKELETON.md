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
