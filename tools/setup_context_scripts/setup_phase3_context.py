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
    "AGENTS.md",
    """
# Project Abi Agent Instructions

## Durable project rules

Abi is a Self-Isomorphic Causal Reread Compiler.

The current implementation phase is determined by the active task prompt and the relevant file under context/plans/.

Do not implement outside the requested phase.

## Core architecture

Abi runtime is:

- deterministic fail-closed controller
- immutable artifact registry / lineage graph
- SQLite-backed external state
- bounded future model workers
- gate-based finalization

The database is memory. Model context is only a workbench.

No worker may finalize. Only controller/finalization code may finalize, and it must refuse if required gates are missing, failed, or blocked.

## Permanent constraints

- Keep model workers bounded by role.
- Keep artifacts immutable.
- Store generated artifacts through the artifact registry.
- Preserve parent IDs and hashes.
- Prefer standard library for runtime code unless a dependency is justified.
- Add tests for every new controller invariant.

## Forbidden unless explicitly requested by the active phase

- no OpenAI API integration
- no real model calls
- no human calibration UI
- no dashboard
- no large orchestration framework
- no SKILL.md
- no production essay generation before the production harness phase
""",
)

write(
    "context/05_FAIL_CLOSED_CONTROLLER_SPEC.md",
    """
# Fail-Closed Controller Spec

## Phase 3 status

Phase 3 implements the fail-closed controller expansion.

No model calls are allowed in Phase 3.

Phase 3 does not add new creative intelligence. It hardens control, state, blockers, gate policy, and finalization refusal.

## Goal

Create a controller layer that can inspect a run, evaluate required gates and blockers, and return explicit controller decisions.

The controller must make false finalization structurally impossible.

## Core invariant

No worker can finalize.

Only controller/finalization code can finalize.

Finalization is refused unless every required gate exists, has passed, and has no blocking defects.

## Required concepts

### ControllerDecision

A structured decision object with fields such as:

- run_id
- decision
- active_phase
- eligible_to_finalize
- missing_gates
- failed_gates
- blocking_defects
- recommended_next_action
- message

Allowed decision values may include:

- continue_phase
- advance_phase
- blocked
- reopen
- refuse_finalization
- finalize

Phase 3 must at least implement refusal/blocker decisions.

### GatePolicy

Defines required gates for a finalization profile.

Phase 3 should preserve the existing Phase 0 placeholder gates but make them policy-driven rather than hardcoded where practical.

### BlockerReport

Structured report explaining why a run cannot finalize or advance.

Fields:

- run_id
- active_phase
- status
- blockers
- missing_gates
- failed_gates
- recommended_next_action

### Run status

Phase 3 should clarify status handling.

Valid status values may include:

- initialized
- active
- blocked
- reopened
- finalization_refused
- finalized

Do not overbuild the full future state machine.

## Required CLI behavior

Add a command family similar to:

abi controller status
abi controller blockers
abi controller demo

The exact command names may vary, but tests must document them.

The demo must show:

- current run inspected
- current active phase reported
- existing gates inspected
- missing required gates reported
- finalization refused
- structured controller decision emitted

## Required tests

Tests must prove:

- controller decision is structured
- missing gates produce refuse_finalization
- failed gates produce refuse_finalization
- blocking defects produce refuse_finalization
- all required gates passing produces eligibility only in a controlled test case
- finalization still refuses in normal live demo state
- previous Phase 0/1/2 tests still pass

## Prohibited in Phase 3

- no model calls
- no OpenAI API integration
- no Abi Ear changes except compatibility fixes
- no Minimal Reread changes except compatibility fixes
- no production essay generation
- no human calibration UI
- no large orchestration framework
- no SKILL.md
""",
)

write(
    "context/plans/PHASE_3_FAIL_CLOSED_CONTROLLER.md",
    """
# Phase 3 Fail-Closed Controller ExecPlan

## Goal

Implement the fail-closed controller expansion.

Phase 3 should make controller decisions explicit and make finalization policy-driven, inspectable, and tested.

## Scope

Add:

- controller decision object
- gate policy object or module
- blocker report
- controller status/demo CLI
- run status helpers if needed
- tests

## Likely files

src/abi/controller/decision.py
src/abi/controller/policy.py
src/abi/controller/blockers.py
src/abi/controller/finalization.py updates
src/abi/controller/state.py updates
src/abi/cli.py updates
tests/test_controller_decisions.py
tests/test_controller_cli.py

## CLI

Add commands such as:

abi controller status
abi controller blockers
abi controller demo

The command should:

- inspect active run
- inspect gates
- return structured JSON
- refuse finalization when required gates are missing or failed

## Tests

Tests must verify:

- all previous tests still pass
- missing required gates create a refuse_finalization decision
- failed required gates create a refuse_finalization decision
- blocking defects create a refuse_finalization decision
- all required gates passing creates an eligible decision in a controlled unit test
- live/demo finalization still refuses unless required finalization gates are actually satisfied
- CLI emits valid JSON

## Constraints

No model calls.
No production generation.
No Phase 4 source harness.
No human calibration.
No SKILL.md.
No large orchestration framework.

## Done means

Phase 3 is complete when:

- python -m pytest passes
- ruff passes
- controller CLI works
- controller emits structured blocker reports
- finalization remains fail-closed
- Phase 0/1/2 demos still work
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 3 reads:",
    """
## Phase 3 reads:

For Phase 3, read:

1. AGENTS.md
2. context/00_ARCHITECTURE_FREEZE.md
3. context/00_CONTEXT_INDEX.md
4. context/01_PROJECT_BRIEF.md
5. context/02_ENGINEERING_CONTRACT.md
6. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
7. context/06_DATA_MODEL.md
8. context/08_GATES_AND_EVALUATION.md
9. context/plans/PHASE_3_FAIL_CLOSED_CONTROLLER.md

Phase 3 implements the fail-closed controller expansion only.
""",
)

print("Phase 3 Fail-Closed Controller context files created.")
print("Next:")
print("  git status")
print("  git add AGENTS.md context tools/setup_context_scripts/setup_phase3_context.py")
print('  git commit -m "Add Phase 3 Fail-Closed Controller frozen context"')
print("  git push")
