# Abi

Abi is an autonomous creative engine for building artifacts through a triply isometric design: the machine process, the artifact’s subject/form, and the reader-state transformation are all described in the same symbolic terms. Its core pattern is germ → differentiation → pressure → crisis → recomposition → return: the architecture uses that pattern to generate, read, diagnose, revise, ablate, and compare creative work, while the target artifact embodies the same transformation and the internal reader model tests whether the artifact caused that transformation. In plain ASCII: germ -> differentiation -> pressure -> crisis -> recomposition -> return. Abi begins with one narrow literary-metaphysical domain so the architecture, topic, and reader effect can be maximally aligned, then aims to generalize the same causal-creative loop into a broader creative intelligence system.

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

SQLite records runs, artifact IDs, hashes, parent lineage, gates, blocker reports, and model-call records. This gives Abi durable memory outside model context.

Most pipelines follow the same shape:

1. Load a source packet and controller-owned constraints.
2. Produce or import candidate, baseline, rival, or evidence artifacts.
3. Run internal reader and ablation checks.
4. Diagnose failures and select a bounded target.
5. Authorize and recompose only the bounded region.
6. Compare the candidate against prior versions, rival pressure, reader-state evidence, and ablated variants.
7. Record gates and blockers through the controller.

## Current Capabilities

The repo currently includes:

- The `abi` Python package and CLI.
- SQLite-backed run state, artifact registry, gate records, and model-call logs.
- Deterministic Abi Ear and Minimal Reread demos.
- Production-harness and pilot artifact-set scaffolds.
- Strongest-rival import and private reader-kit export.
- Internal reader-lab, reader-state evaluation, and targeted provisional reader-state evaluation packets.
- Autonomous evidence synthesis with candidate evidence graph adjudication and loop-level review.
- Bounded macro recomposition with target coverage and materiality checks.
- Executed counterfactual ablation over supported candidate packet types.
- Ablation-informed revision and synthesis-guided macro recomposition.
- Loop-integrity cleanup, supervised next-cycle authorization, and cleanup-aware target planning.
- Narrow residual target selection, target-aware residual work-order planning, one-shot residual generation, and materiality feedback for failed attempts.
- Residual target adapters for object-motion causality and tactile inevitability gaps.
- Policy-driven controller and fail-closed finalization profiles.

Model-shaped work is routed through a structured model-driver layer. Tests use fake or stub clients, and live paths require explicit operator opt-in.

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
