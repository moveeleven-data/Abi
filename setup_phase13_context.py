from pathlib import Path

ROOT = Path.cwd()


def write(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip() + "\n", encoding="utf-8")


def append_once(path: str, marker: str, text: str) -> None:
    p = ROOT / path
    current = p.read_text(encoding="utf-8") if p.exists() else ""
    if marker not in current:
        p.write_text(current.rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8")


write(
    "context/20_FINAL_ARTIFACT_AND_PAPER_PACKET_SPEC.md",
    """
# Phase 13: Final Artifact + Paper Packet v1 Spec

## Status

Phase 13 creates the final-artifact candidate packet and research/paper packet scaffold.

This phase must not finalize the project.

This phase must not claim phase shift.

This phase must not claim real human validation.

## Goal

Create a structured packet that gathers the current production candidate, evaluation evidence, hidden consequence evidence, risk register, paper outline, and finalization-readiness report.

This packet should make the project externally legible without pretending the artifact is final.

## Required CLI behavior

Add a command such as:

abi final-artifact packet --client fake

and optionally:

abi final-artifact packet --client openai --allow-live-model --max-model-calls 8

Rules:

- fake client mode must not require API key
- OpenAI client mode must require --allow-live-model
- OpenAI client mode must require OPENAI_API_KEY
- no automatic OpenAI calls
- output must use unique packet directories
- all artifacts must be registered through the artifact registry
- finalization must remain fail-closed

## Required input behavior

Default input should use the latest available fake production and evaluation packets.

If no production/evaluation packet exists, the command may run fake production/evaluation dependencies or refuse with a clear structured message.

Tests should be deterministic.

## Required artifacts

The final artifact packet should produce artifact types equivalent to:

- final_artifact_source_refs
- final_artifact_candidate_text
- final_artifact_lineage_summary
- hidden_consequence_report
- reader_effect_claim_map
- final_artifact_risk_register
- hostile_final_audit_scaffold
- paper_outline
- paper_evidence_map
- finalization_readiness_report
- final_artifact_packet

Exact names may differ if aligned with repo conventions.

## Required flags

The packet must clearly mark the artifact as:

- non_final: true
- not_human_validated: true
- not_finalization_eligible: true
- no_phase_shift_claim: true
- fixture_or_scaffold_evidence_present: true where applicable

It must not mark final gates as passed.

It must not satisfy finalization profile eligibility.

## Candidate artifact

The candidate artifact may be based on the latest production candidate artifact.

It must be represented as a candidate, not a final work.

## Paper packet

The paper packet should be a scaffold, not a finished paper.

It should include:

- project thesis
- system architecture summary
- artifact/evidence map
- baseline/evaluation status
- known blockers
- claims not yet made
- next required validation steps

## Finalization readiness

The finalization readiness report should call into or mirror the final_artifact profile blockers.

It should show the run remains ineligible for finalization.

## Required tests

Tests must verify:

- all previous tests still pass
- fake final-artifact packet command succeeds
- OpenAI path refuses without --allow-live-model
- OpenAI path refuses without OPENAI_API_KEY
- all required packet artifacts are produced
- candidate artifact is marked non-final
- no phase-shift claim is made
- no real human-validation claim is made
- finalization readiness report says ineligible
- finalization remains fail-closed
- packet directory is unique per invocation
- parent IDs are populated where appropriate

## Prohibited

- no actual finalization
- no phase-shift claim
- no real human-validation claim
- no automatic OpenAI calls
- no dashboard
- no agent loops
- no SKILL.md
- no broad refactor
- no weakening finalization
""",
)

write(
    "context/plans/PHASE_13_FINAL_ARTIFACT_AND_PAPER_PACKET.md",
    """
# Phase 13 Final Artifact + Paper Packet ExecPlan

## Goal

Implement the final-artifact candidate and paper/report packet scaffold.

The purpose is to make the current state legible and auditable while preserving finalization blockers.

## Scope

Add:

- final artifact packet orchestrator
- fake-client packet path
- optional guarded OpenAI path
- final artifact candidate artifact
- hidden consequence report
- reader effect claim map
- risk register
- hostile final audit scaffold
- paper outline
- paper evidence map
- finalization readiness report
- packet summary
- CLI command
- tests

## Likely files

Likely new files:

src/abi/modules/final_artifact.py
tests/test_final_artifact_packet.py
tests/test_final_artifact_cli.py

Likely updated files:

src/abi/cli.py
src/abi/controller/state.py
README.md

Possible updates if useful:

src/abi/model_schemas.py

## CLI

Preferred command:

abi final-artifact packet --client fake

Optional guarded live path:

abi final-artifact packet --client openai --allow-live-model --max-model-calls 8

The fake path must require no API key.

The OpenAI path must refuse unless --allow-live-model is passed and OPENAI_API_KEY is set.

## Required output packet

The final artifact packet must expose:

1. source_refs
2. candidate_text
3. lineage_summary
4. hidden_consequence_report
5. reader_effect_claim_map
6. risk_register
7. hostile_final_audit_scaffold
8. paper_outline
9. paper_evidence_map
10. finalization_readiness_report
11. final_artifact_packet

## Tests

Tests must verify:

- all previous tests still pass
- fake final-artifact packet succeeds
- required artifacts exist
- candidate_text is non-final
- paper packet makes no phase-shift claim
- human validation is marked missing/not real
- finalization readiness report says ineligible
- final_artifact profile still refuses
- packet directory is unique per invocation
- parent IDs are populated where appropriate
- OpenAI path refuses without --allow-live-model
- OpenAI path refuses without OPENAI_API_KEY
- finalization remains fail-closed

## Done means

Phase 13 is done when a final-artifact candidate packet and paper/report packet exist, and the finalization policy still refuses the current run with meaningful blockers.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 13 reads:",
    """
## Phase 13 reads:

For Phase 13, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
7. context/06_DATA_MODEL.md
8. context/08_GATES_AND_EVALUATION.md
9. context/17_SOURCE_TO_ARTIFACT_PRODUCTION_RUN_SPEC.md
10. context/18_EVALUATION_BASELINES_SPEC.md
11. context/19_FINALIZATION_GATE_POLICY_V2_SPEC.md
12. context/20_FINAL_ARTIFACT_AND_PAPER_PACKET_SPEC.md
13. context/plans/PHASE_13_FINAL_ARTIFACT_AND_PAPER_PACKET.md

Phase 13 implements the final-artifact candidate and paper packet scaffold only.
""",
)

print("Phase 13 Final Artifact + Paper Packet context files created.")
print("Next:")
print("  git status")
print("  git add context setup_phase13_context.py")
print('  git commit -m "Add Phase 13 final artifact paper packet frozen context"')
print("  git push")
