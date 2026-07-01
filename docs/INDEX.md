# Documentation Index

Start with the root [README](../README.md). It is the operator entry point for the current autonomous creative-engine path.

## Active Path

- [Core realignment context](../context/24_CORE_REALIGNMENT_REMOVE_HUMAN_PAPER_VALIDATION.md)
- [Architecture freeze](../context/00_ARCHITECTURE_FREEZE.md)
- [Project brief](../context/01_PROJECT_BRIEF.md)
- [Engineering contract](../context/02_ENGINEERING_CONTRACT.md)
- [Data model](../context/06_DATA_MODEL.md)
- [Gate and evaluation foundations](../context/08_GATES_AND_EVALUATION.md)
- [Gate policy v2 spec](../context/19_FINALIZATION_GATE_POLICY_V2_SPEC.md)

## Operator Reference

- [Abi intro presentation](abi_intro.pdf)
- [Changelog](CHANGELOG.md)
- [Phase 14 operator handoff](phase14_operator_handoff/operator_handoff.md)
- [Audit report](phase14_operator_handoff/audit_report.md)
- [Command matrix](phase14_operator_handoff/command_matrix.md)
- [Known blockers](phase14_operator_handoff/known_blockers.md)
- [Fresh clone verification](phase14_operator_handoff/fresh_clone_verification.md)
- [Finalization profile summary](phase14_operator_handoff/finalization_profile_summary.md)

## Current Commands

Use the README for exact syntax. The active command groups are:

- `abi ear`
- `abi reread`
- `abi production`
- `abi pilot artifact-set`
- `abi pilot import-rival`
- `abi autonomous reader-lab`
- `abi autonomous revise`
- `abi model-driver`
- `abi model-call`
- `abi artifact`
- `abi run`
- `abi gate`
- `abi finalization`
- `abi finalize`

The retired active commands are `abi calibration demo`, `abi evaluation demo`, `abi final-artifact packet`, and `abi pilot export-reader-kit`.

## Frozen Context

- [Context README](../context/README.md)
- [Context index](../context/00_CONTEXT_INDEX.md)
- [Phase plans](../context/plans/)

Frozen context files document earlier phase constraints and historical side quests. They are not all current runtime instructions.

## Non-Active Historical Docs

The Phase 15 validation protocol and Phase 13 paper-packet materials remain in the repository as historical documents. They are not the active development path and should not be used as instructions to run human readers, public validation, or paper-evidence collection.

## Runtime And Private Files

- Runtime output belongs in ignored `db/`, `runs/`, and `outputs/` paths.
- Private source material belongs in ignored `inputs/private/`.
- Setup context scripts are stored in `tools/setup_context_scripts/`.
