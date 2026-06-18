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
