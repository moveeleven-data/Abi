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
