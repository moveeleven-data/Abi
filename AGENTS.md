# Project Abi Agent Instructions

## Durable project rules

Abi is a Self-Isomorphic Causal Reread Compiler.

The current implementation phase is determined by the active task prompt and the relevant file under context/plans/.

Do not implement outside the requested phase.

## Core architecture

Abi runtime is:

- deterministic fail-closed controller
- immutable artifact registry / lineage graph
- SQLite-backed external state
- bounded future model workers
- gate-based finalization

The database is memory. Model context is only a workbench.

No worker may finalize. Only controller/finalization code may finalize, and it must refuse if required gates are missing, failed, or blocked.

## Permanent constraints

- Keep model workers bounded by role.
- Keep artifacts immutable.
- Store generated artifacts through the artifact registry.
- Preserve parent IDs and hashes.
- Prefer standard library for runtime code unless a dependency is justified.
- Add tests for every new controller invariant.

## Forbidden unless explicitly requested by the active phase

- no OpenAI API integration
- no real model calls
- no human calibration UI
- no dashboard
- no large orchestration framework
- no SKILL.md
- no production essay generation before the production harness phase
