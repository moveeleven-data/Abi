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
    "context/10_HUMAN_CALIBRATION_SPEC.md",
    """
# Human Calibration / Paper-Grade Evaluation Spec

## Phase 5 status

Phase 5 implements the deterministic Human Calibration and Paper-Grade Evaluation scaffold.

No model calls are allowed in Phase 5.

Phase 5 does not run real human studies yet. It creates the artifact structure, protocols, fixture traces, baseline comparison scaffolds, and evaluation reports needed for later real human calibration.

## Goal

Create a deterministic evaluation scaffold that can represent:

1. human-reader protocol
2. reader trial fixture
3. first-read trace
4. reread trace
5. reader-state transition
6. blind comparison fixture
7. baseline comparison fixture
8. calibration summary
9. paper-grade evaluation report
10. calibration gate report
11. calibration packet summary

The purpose is to make the reader a first-class substrate in the repo, not just a conceptual claim.

## Core principle

Artwork = Artifact + ΔReaderState

Phase 5 must represent ΔReaderState explicitly.

The calibration scaffold should test whether the artifact caused a reader-state transformation, not merely whether the reader liked the text.

## Required artifact types

- calibration_protocol
- calibration_human_reader_trial
- calibration_first_read_trace
- calibration_reread_trace
- calibration_reader_state_transition
- calibration_blind_comparison
- calibration_baseline_comparison
- calibration_summary
- calibration_evaluation_report
- calibration_gate_report
- calibration_packet

Each artifact must be registered through the Phase 0 artifact registry.

## Required CLI behavior

Add a command similar to:

abi calibration demo

It should:

- ensure a run exists
- use deterministic fixture inputs from fixtures/human_calibration/
- create a unique packet directory under runs/<run_id>/calibration/<packet_id>/
- write all Phase 5 artifacts as JSON
- register all artifacts in SQLite
- update active_phase to phase5_human_calibration
- print a compact JSON summary with run_id, packet_id, artifact IDs, and gate result

## Determinism

Phase 5 outputs must not depend on API calls, randomness, clock time except artifact metadata, or external files not in the repo.

## Required evaluation concepts

### Human reader protocol

Defines what a human reader should report:

- first-read memory
- opening interpretation
- retained images
- predictions
- attention drops
- confusion
- overexplicitness
- post-ending opening reread
- changed interpretation
- paraphrase attempt
- details that gained force
- details that felt fake

### Reader-state transition

Represents the change from R1 to R2:

- before_state
- after_state
- changed_opening_interpretation
- newly_connected_fragments
- motif_role_changes
- paraphrase_loss
- unsupported_depth_flags

### Blind comparison

Represents a comparison between two artifacts without revealing which came from Abi.

### Baseline comparison

Represents comparison against direct prompt, best-of-N, or prior draft baselines.

Phase 5 may use deterministic fixture baselines only.

## Prohibited in Phase 5

- no OpenAI API calls
- no real model_driver behavior
- no live human study collection UI
- no external survey integration
- no dashboard
- no large orchestration framework
- no SKILL.md
- no production essay generation
- no claims of validated human success from fixture data

## Acceptance criteria

Phase 5 is complete only when:

- all previous tests pass
- abi calibration demo runs locally
- all required Phase 5 artifact types are produced
- artifacts are registered with hashes and parent IDs
- packet directories are immutable and non-overwriting
- active_phase becomes phase5_human_calibration
- a calibration gate report is produced
- controller still refuses finalization unless required finalization gates are satisfied
""",
)

write(
    "context/plans/PHASE_5_HUMAN_CALIBRATION.md",
    """
# Phase 5 Human Calibration ExecPlan

## Goal

Implement the deterministic Human Calibration / Paper-Grade Evaluation scaffold.

Phase 5 should prove that Abi can represent reader-state transformation, blind comparison, and baseline comparison as first-class artifacts.

## Scope

Add:

- deterministic calibration module
- fixture human reader protocol
- fixture human reader trace
- fixture baseline artifact
- reader-state transition artifact
- blind comparison artifact
- baseline comparison artifact
- calibration summary
- paper-grade evaluation report
- calibration gate report
- CLI command
- tests

## Likely files

src/abi/modules/human_calibration.py
tests/test_human_calibration.py
tests/test_human_calibration_cli.py
fixtures/human_calibration/protocol.md
fixtures/human_calibration/human_reader_trial.json
fixtures/human_calibration/baseline_direct_prompt.md

Possible updates:

src/abi/cli.py
src/abi/controller/state.py
README.md

## CLI

Add a command such as:

abi calibration demo

The command should:

- initialize or reuse the active run
- read deterministic fixture material
- create a unique run subfolder:
  runs/<run_id>/calibration/<packet_id>/
- write artifacts
- register artifacts
- print JSON summary

## Required output packet

The benchmark run must produce:

1. calibration_protocol
2. calibration_human_reader_trial
3. calibration_first_read_trace
4. calibration_reread_trace
5. calibration_reader_state_transition
6. calibration_blind_comparison
7. calibration_baseline_comparison
8. calibration_summary
9. calibration_evaluation_report
10. calibration_gate_report
11. calibration_packet

## Tests

Tests must verify:

- all previous tests still pass
- deterministic pipeline output
- all required artifact types are produced
- all required artifacts are registered
- parent IDs are populated where appropriate
- packet directory is unique per invocation
- active_phase becomes phase5_human_calibration
- calibration gate report exists
- controller/finalization still fail closed
- no model/API code is used
- fixture data is clearly marked as fixture data and not real validation

## Constraints

No model calls.
No live human survey UI.
No production essay generation.
No dashboard.
No SKILL.md.
No large orchestration framework.

## Done means

Phase 5 is complete when:

- python -m pytest passes
- ruff passes
- abi calibration demo runs
- all calibration artifacts are stored and registered
- existing controller/ear/reread/harness demos still work
- finalization remains fail closed
""",
)

write(
    "fixtures/human_calibration/protocol.md",
    """
# Human Calibration Protocol Fixture

This is a fixture protocol, not a completed real human study.

Reader should report:

1. First-read memory.
2. Opening interpretation before knowing the ending.
3. Retained images.
4. Predictions.
5. Attention drops.
6. Confusion points.
7. Overexplicit points.
8. Post-ending reread of the opening.
9. Changed interpretation of the opening.
10. Details that gained force.
11. Details that felt fake or unsupported.
12. Paraphrase attempt.
13. Blind preference among candidate artifacts.
""",
)

write(
    "fixtures/human_calibration/human_reader_trial.json",
    """
{
  "fixture": true,
  "reader_id": "fixture_reader_001",
  "protocol": "human_calibration_protocol_v1",
  "artifact_label": "candidate_A",
  "first_read": {
    "literal_memory": ["table", "morning", "dust", "return"],
    "opening_interpretation": "A plain domestic fact with unease.",
    "retained_images": ["table", "dust under the table"],
    "predictions": ["the table may become evidence of something that happened overnight"],
    "attention_drops": [],
    "confusion_points": [],
    "overexplicit_points": []
  },
  "reread": {
    "changed_opening_interpretation": "The opening now reads less as a report and more as a germ of persistence after attempted erasure.",
    "changed_words": ["still", "morning"],
    "details_that_gained_force": ["dust", "underside", "return"],
    "details_that_felt_fake": [],
    "paraphrase_loss": "The summary preserves the idea of return but loses the pressure of the object remaining."
  },
  "blind_preference": {
    "preferred_label": "candidate_A",
    "confidence": 0.72,
    "reason": "The opening changed more after the ending than in the baseline."
  }
}
""",
)

write(
    "fixtures/human_calibration/baseline_direct_prompt.md",
    """
# Baseline Direct Prompt Fixture

This is a deterministic fixture baseline, not a real model output.

The table remains in the morning, and this shows that things endure despite absence. The speaker learns that return is possible because the object stayed in place. The table becomes a symbol of memory and continuity.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 5 reads:",
    """
## Phase 5 reads:

For Phase 5, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
7. context/06_DATA_MODEL.md
8. context/08_GATES_AND_EVALUATION.md
9. context/10_HUMAN_CALIBRATION_SPEC.md
10. context/plans/PHASE_5_HUMAN_CALIBRATION.md

Phase 5 implements the deterministic Human Calibration / Paper-Grade Evaluation scaffold only.
""",
)

print("Phase 5 Human Calibration context files created.")
print("Next:")
print("  git status")
print("  git add context fixtures setup_phase5_context.py")
print('  git commit -m "Add Phase 5 Human Calibration frozen context"')
print("  git push")
