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
