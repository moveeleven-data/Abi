# Abi

Abi is an autonomous creative engine for building artifacts through a triply isometric
design: the machine process, the artifact's subject/form, and the reader-state
transformation are all described in the same symbolic terms. Its core pattern is
germ -> differentiation -> pressure -> crisis -> recomposition -> return: the
architecture uses that pattern to generate, read, diagnose, revise, ablate, and compare
creative work, while the target artifact embodies the same transformation and the
internal reader model tests whether the artifact caused that transformation. Abi begins
with one narrow literary-metaphysical domain so the architecture, topic, and reader
effect can be maximally aligned, then aims to generalize the same causal-creative loop
into a broader creative intelligence system.

## How It Works

Abi stores work in packet directories under `runs/<run_id>/.../packet_NNNN/`.
Each packet contains JSON artifacts with a normalized envelope:

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

The SQLite registry records artifact IDs, hashes, parent IDs, run state, gates, and
model-call records. This gives Abi a durable memory outside the model context.

Most pipelines follow the same shape:

1. Build or load a source packet.
2. Create candidate, baseline, and rival artifacts.
3. Run internal reader analysis over the candidate set.
4. Diagnose failures and choose a bounded repair target.
5. Apply a controller-owned revision.
6. Compare old, new, rival, and ablated variants.
7. Record gate reports and blocker reports without silently finalizing anything.

## What Is Implemented

The current repo includes:

- The `abi` Python package and CLI.
- SQLite-backed runs, artifacts, gates, and model-call records.
- Immutable JSON artifacts with hashes and parent lineage.
- Deterministic Abi Ear and Minimal Reread demos.
- Production-harness and pilot artifact-set packet scaffolds.
- Strongest-rival import and counterbalanced private reader-kit export.
- Autonomous internal reader-lab packets.
- Autonomous closed-loop revision packets.
- Executed counterfactual ablation packets.
- Policy-driven controller and finalization profiles.

Workers can produce artifacts, comparisons, diagnoses, and blocker reports. Finalization
is controlled separately by the controller/finalization layer.

## Repository Layout

```text
src/abi/                      runtime package
src/abi/controller/           controller decisions, gates, finalization policy
src/abi/modules/              packet-producing pipelines
tests/                        regression tests
fixtures/                     non-private fixture inputs
context/                      frozen phase specs and historical context
docs/                         operator handoff and protocol notes
tools/setup_context_scripts/  context setup utilities
```

Runtime state, generated packets, outputs, private source material, and environment
files are intentionally kept out of Git.
