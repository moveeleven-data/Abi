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
    "context/19_FINALIZATION_GATE_POLICY_V2_SPEC.md",
    """
# Phase 12: Finalization Gate Policy v2 Spec

## Status

Phase 12 upgrades finalization from Phase 0 placeholder gates to project-relevant release-readiness gates.

This phase must not finalize the project.

This phase must not claim artistic success.

This phase must not add generation.

## Goal

Make finalization refusal reflect the actual maturity of Abi.

The current system refuses because Phase 0 placeholder gates are missing.

Phase 12 should make finalization refuse for meaningful release reasons:

- no final artifact packet
- candidate artifact is non-final
- fixture-only evaluation evidence
- no real human validation
- no strongest-rival comparison
- no raw-model baseline comparison
- no hostile final audit
- no final approval gate

## Required concepts

### GateProfile

A named finalization policy.

Recommended profiles:

1. infrastructure
2. candidate_release
3. final_artifact

The default `abi finalize` should remain fail-closed.

### GateCatalog

A structured list of known gate names, their purpose, and whether they are required for each profile.

### ReleaseReadinessReport

A structured report explaining whether a run is eligible for a given profile.

Required fields:

- run_id
- profile
- eligible
- missing_gates
- failed_gates
- blocking_defects
- fixture_only_blockers
- non_final_blockers
- recommended_next_action

### Finalization behavior

`abi finalize` must still refuse by default.

The refusal should mention meaningful blockers when artifacts show the run is a candidate/evaluation scaffold rather than a final artifact.

## Required CLI behavior

Add or update commands such as:

- abi gate list
- abi finalization status
- abi finalization status --profile final_artifact
- abi finalize --profile final_artifact

Exact command names may vary if aligned with existing CLI conventions.

All commands must emit JSON.

## Required gate profiles

### infrastructure profile

Checks basic infrastructure gates.

This may be used for diagnostics only. Passing it must not imply project finalization.

### candidate_release profile

Checks whether a candidate production/evaluation packet exists and is clearly marked non-final.

This profile should be eligible for "candidate release readiness" only if all candidate gates pass.

It must not imply final artifact eligibility.

### final_artifact profile

Requires at minimum:

- final_artifact_packet_exists
- final_artifact_not_fixture
- final_artifact_not_marked_non_final
- real_human_validation_passed
- strongest_rival_comparison_passed
- raw_model_baseline_comparison_passed
- hostile_final_audit_passed
- no_fixture_only_evidence_used_as_final_claim
- no_unresolved_blocking_defects
- final_operator_approval

Phase 12 should not make these pass. It should report them as missing unless explicitly present in controlled tests.

## Required behavior

Phase 12 must:

- preserve existing finalization refusal
- preserve all existing demos
- avoid satisfying final artifact gates with fixture data
- prevent fixture-only evaluation from passing final gates
- report candidate artifacts as non-final
- add tests showing final_artifact profile refuses in current fixture state
- add controlled tests proving the policy can become eligible only when all required gates are present and passed

## Prohibited

- no final artifact generation
- no phase-shift claim
- no real human validation claim
- no automatic OpenAI calls
- no production generation changes
- no source ingestion changes
- no agent loops
- no dashboard
- no SKILL.md
- no weakening finalization

## Acceptance criteria

Phase 12 is complete only when:

- ruff passes
- pytest passes
- all existing demos still work
- abi finalize remains fail-closed
- finalization blocker report uses meaningful final_artifact blockers
- fixture-only evidence cannot satisfy final_artifact profile
- candidate artifacts marked non-final cannot satisfy final_artifact profile
- gate list/status commands work
- controlled unit tests can show eligibility only when all profile gates pass
""",
)

write(
    "context/plans/PHASE_12_FINALIZATION_GATE_POLICY_V2.md",
    """
# Phase 12 Finalization Gate Policy v2 ExecPlan

## Goal

Upgrade finalization policy from Phase 0 placeholder gates to real project release-readiness gates.

The purpose is better refusal, not completion.

## Scope

Add:

- gate profile definitions
- gate catalog
- release readiness report
- finalization status CLI
- gate list CLI
- finalization profile support
- tests

## Likely files

Likely updated:

src/abi/controller/policy.py
src/abi/controller/finalization.py
src/abi/controller/control.py
src/abi/cli.py
README.md

Possible new:

src/abi/controller/gate_catalog.py
src/abi/controller/release_readiness.py
tests/test_finalization_profiles.py
tests/test_gate_catalog_cli.py

## CLI

Add or update:

abi gate list
abi finalization status
abi finalization status --profile final_artifact
abi finalize --profile final_artifact

Existing `abi finalize` must remain fail-closed.

## Tests

Tests must verify:

- all previous tests still pass
- current fixture/evaluation state refuses final_artifact profile
- fixture-only evidence blocks final_artifact profile
- non-final candidate blocks final_artifact profile
- missing real human validation blocks final_artifact profile
- missing strongest-rival comparison blocks final_artifact profile
- missing raw-model baseline comparison blocks final_artifact profile
- missing hostile final audit blocks final_artifact profile
- gate list emits JSON
- finalization status emits JSON
- controlled all-gates-passed test can become eligible
- existing finalize remains fail-closed

## Done means

Phase 12 is done when finalization refusal is mature and project-relevant, but still refuses current runs.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 12 reads:",
    """
## Phase 12 reads:

For Phase 12, read:

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
12. context/plans/PHASE_12_FINALIZATION_GATE_POLICY_V2.md

Phase 12 upgrades finalization gate policy only.
""",
)

print("Phase 12 Finalization Gate Policy v2 context files created.")
print("Next:")
print("  git status")
print("  git add context setup_phase12_context.py")
print('  git commit -m "Add Phase 12 finalization gate policy frozen context"')
print("  git push")
