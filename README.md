# Abi

Abi is an autonomous creative engine built around one repeating pattern:

germ -> differentiation -> pressure -> crisis -> recomposition -> return

The same pattern is used in three places at once: the machine process, the artifact's subject and form, and the reader-state transformation Abi is trying to cause. Abi begins in a narrow literary-metaphysical domain so those three layers can stay aligned while the system learns how to generate, read, diagnose, revise, ablate, compare, and preserve creative work.

## How Abi Works

Abi stores work as immutable packet directories under `runs/<run_id>/.../packet_NNNN/`. Each packet contains JSON artifacts with a normalized envelope:

```text
schema_version
artifact_type
run_id
lineage_id
parent_ids
created_by
fixture_only
model_call_id
payload
```

SQLite records runs, artifact IDs, hashes, parent lineage, gates, blocker reports, and model-call records. This gives Abi a durable memory outside the model context.

Most pipelines follow the same shape:

1. Load a source packet and controller-owned constraints.
2. Produce or import candidate, baseline, rival, or evidence artifacts.
3. Run internal reader and ablation checks.
4. Diagnose failures and select a bounded target.
5. Recompose only the authorized region.
6. Compare candidate, prior versions, rival pressure, and ablated variants.
7. Record gates and blockers without silently finalizing anything.

## Current Capabilities

The repo currently includes:

- The `abi` Python package and CLI.
- SQLite-backed run state, artifact registry, gate records, and model-call logs.
- Deterministic Abi Ear and Minimal Reread demos.
- Production-harness and pilot artifact-set scaffolds.
- Strongest-rival import and private reader-kit export.
- Internal reader-lab and reader-state evaluation packets.
- Autonomous evidence synthesis and loop-level review.
- Bounded macro recomposition with target coverage and materiality checks.
- Executed counterfactual ablation over supported candidate packet types.
- Ablation-informed revision and synthesis-guided macro recomposition.
- Supervised next-cycle authorization and authorization-aware target planning.
- Narrow residual target selection, object-motion work-order planning, one-shot residual generation, and materiality feedback for failed attempts.
- Policy-driven controller and fail-closed finalization profiles.

Model-shaped work is routed through a structured model-driver layer. Live model paths are guarded by explicit opt-in, while tests use fake or stub clients.

## Repository Layout

```text
src/abi/                      runtime package and CLI
src/abi/controller/           controller decisions, gates, and finalization policy
src/abi/modules/              packet-producing pipelines
tests/                        regression tests
fixtures/                     non-private fixture inputs
context/                      frozen phase specs and historical context
docs/                         changelog, handoff notes, and operator documents
tools/setup_context_scripts/  context setup utilities
```

Runtime databases, generated packets, outputs, private source material, caches, virtual environments, and local environment files are intentionally kept out of Git.
