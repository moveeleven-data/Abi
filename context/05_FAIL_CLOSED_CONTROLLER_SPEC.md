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
