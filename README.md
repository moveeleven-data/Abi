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

## Phase 2 Minimal Reread Demo

Phase 2 adds a deterministic local minimal reread loop. Run it with:

```powershell
.\.venv\Scripts\abi.exe reread demo
```

The command ensures a deterministic Abi Ear packet exists, writes JSON artifacts
under `runs/<run_id>/reread/<packet_id>/`, registers every artifact in SQLite,
and leaves finalization fail-closed unless the required Phase 0 finalization
gates are satisfied.

## Phase 3 Controller Commands

Phase 3 adds a policy-driven fail-closed controller surface:

```powershell
.\.venv\Scripts\abi.exe controller status
.\.venv\Scripts\abi.exe controller blockers
.\.venv\Scripts\abi.exe controller demo
```

The controller commands inspect the active run, evaluate the required
finalization gates through policy, and emit structured decisions or blocker
reports. Finalization remains controller-owned and fail-closed.

## Phase 4 Production Harness Demo

Phase 4 adds a deterministic local production harness scaffold. Run it with:

```powershell
.\.venv\Scripts\abi.exe harness demo
```

The command reads fixture material from `fixtures/production_harness/`, writes
JSON artifacts under `runs/<run_id>/harness/<packet_id>/`, registers every
artifact in SQLite, and keeps finalization policy-driven and fail-closed.
