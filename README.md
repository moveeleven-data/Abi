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

## Phase 1 Abi Ear Demo

Phase 1 adds a deterministic local Abi Ear benchmark pipeline. It uses the fixed
input:

```text
The table is still there in the morning.
```

Run it with:

```powershell
.\.venv\Scripts\abi.exe ear demo
```

The command writes JSON artifacts under `runs/<run_id>/abi_ear/<packet_id>/`
and registers each artifact in SQLite through the Phase 0 artifact registry. It
does not make model calls or API calls.
