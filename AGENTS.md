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
