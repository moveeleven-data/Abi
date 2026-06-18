# Artifact Schema Envelope Report

Last checked: 2026-06-18

## Normalized Envelope

The shared packet helper in `src/abi/packets.py` writes JSON artifacts with the normalized envelope:

- `schema_version`
- `artifact_type`
- `run_id`
- `lineage_id`
- `parent_ids`
- `created_by`
- `fixture_only`
- `model_call_id`
- `payload`

Artifacts are then registered through the Phase 0 registry, which records path, content hash, lineage ID, and parent IDs.

## Parentage

Packet modules populate parent IDs for downstream artifacts. Packet summaries depend on earlier packet artifacts, and model-shaped outputs can depend on input artifact IDs. This preserves a local lineage graph in SQLite.

## Model Call IDs

Accepted parsed model artifacts produced through the model driver include a non-null `model_call_id`. Deterministic scaffold artifacts may have `model_call_id: null`, which is expected. Validation failures and client failures produce model-call records but do not register parsed artifacts.

## Immutability

Packet helpers create numbered packet directories such as `packet_0001`, `packet_0002`, and so on. Repeated invocations create new packet directories instead of overwriting previously registered artifact paths.

## Audit Conclusion

The envelope format is consistent enough for operator inspection and downstream audit. Future phases should preserve this envelope rather than adding ad hoc packet formats.
