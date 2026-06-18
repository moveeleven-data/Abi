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
    "context/21_REPO_AUDIT_OPERATOR_HANDOFF_SPEC.md",
    """
# Phase 14: Repo Audit + Operator Handoff Report Spec

## Status

Phase 14 is an audit and handoff phase.

It must not add new product capabilities.

It must not add new model workers.

It must not add new generation behavior.

It must not change the architecture.

It must not mark final gates as passed.

## Goal

Verify and document the system that now exists after Phase 13.

Abi now has an end-to-end scaffold from source material to candidate artifact, evaluation packet, final-artifact candidate packet, paper/evidence packet, and finalization-readiness report. Phase 14 should make that state explicit, auditable, and operator-ready.

## Required outputs

Phase 14 should produce tracked documentation under a directory such as:

docs/phase14_operator_handoff/

Required documents:

1. audit_report.md
2. command_matrix.md
3. phase_inventory.md
4. known_blockers.md
5. finalization_profile_summary.md
6. fixture_evidence_safety_report.md
7. live_model_guardrail_report.md
8. artifact_schema_envelope_report.md
9. fresh_clone_verification.md
10. next_validation_roadmap.md
11. operator_handoff.md

Exact filenames may differ if clearly equivalent.

## Required audit checks

The audit must address:

- all phase tags exist and point to expected commits
- README commands match actual CLI behavior
- AGENTS.md is still accurate and durable
- context docs are not obviously contradictory
- all listed CLI commands work or are clearly marked unavailable
- finalization profile behavior is correct
- fixture-only evidence cannot satisfy final_artifact gates
- candidate/final-artifact packets remain non-final
- live OpenAI paths require explicit opt-in
- tests do not require API keys
- tests do not make accidental network calls
- db/runs/outputs/.venv/cache files are not accidentally tracked
- artifact envelopes consistently expose schema_version, artifact_type, run_id, lineage_id, parent_ids, created_by, fixture_only, model_call_id, and payload where applicable
- model_call_id behavior is consistent
- generated runtime directories are gitignored or intentionally untracked
- fresh clone instructions are documented
- remaining blockers are clear

## Required CLI verification

Phase 14 should verify at minimum:

- git status
- git log --oneline --decorate -60
- git tag --list
- git ls-files
- python -m ruff check .
- python -m pytest
- abi status
- abi artifact list
- abi run list
- abi run latest
- abi final-artifact packet --client fake
- abi finalization status --profile final_artifact
- abi finalize --profile final_artifact

Additional CLI checks are allowed if useful.

## Required factual stance

The audit must state that Abi has not yet proven:

- phase-shift-level writing
- real human validation
- baseline superiority
- hostile-audit survival
- final artifact readiness
- paper-readiness

The audit must state that the current system is a working research harness and end-to-end scaffold, not a validated creative system.

## Prohibited

- no new generation behavior
- no new model worker
- no automatic OpenAI call
- no real live production run
- no human-study automation
- no dashboard
- no SKILL.md
- no finalization gate passing
- no phase-shift claim
- no broad refactor

## Acceptance criteria

Phase 14 is complete only when:

- ruff passes
- pytest passes
- working tree is clean after commit
- audit/handoff docs exist
- no out-of-scope features are added
- no final gates are falsely passed
- no fixture evidence is accepted as real validation
- finalization still refuses
- audit report clearly explains where Abi is, what remains unproven, and what Phase 15 should do
""",
)

write(
    "context/plans/PHASE_14_REPO_AUDIT_OPERATOR_HANDOFF.md",
    """
# Phase 14 Repo Audit + Operator Handoff ExecPlan

## Goal

Audit and document the current Abi repo after Phase 13.

Do not add new runtime capability.

## Scope

Add tracked handoff documentation.

Possible directory:

docs/phase14_operator_handoff/

Required reports:

1. audit_report.md
2. command_matrix.md
3. phase_inventory.md
4. known_blockers.md
5. finalization_profile_summary.md
6. fixture_evidence_safety_report.md
7. live_model_guardrail_report.md
8. artifact_schema_envelope_report.md
9. fresh_clone_verification.md
10. next_validation_roadmap.md
11. operator_handoff.md

## Suggested implementation approach

Use existing repo state and command outputs.

Run commands locally as needed.

Do not rely on stale assumptions.

When documenting command results, distinguish:

- commands actually verified in this phase
- commands known from earlier phases
- commands not rerun

## Required command checks

At minimum, run or document:

git status
git log --oneline --decorate -60
git tag --list
git ls-files
python -m ruff check .
python -m pytest
abi status
abi artifact list
abi run list
abi run latest
abi final-artifact packet --client fake
abi finalization status --profile final_artifact
abi finalize --profile final_artifact

## Tests

No new runtime tests are strictly required unless code changes are made.

If any helper code is added, tests are required.

Prefer documentation-only changes.

## Done means

Phase 14 is done when the repo has a clear operator handoff package and all existing tests still pass.
""",
)

append_once(
    "context/00_CONTEXT_INDEX.md",
    "Phase 14 reads:",
    """
## Phase 14 reads:

For Phase 14, read:

1. AGENTS.md
2. README.md
3. context/00_ARCHITECTURE_FREEZE.md
4. context/00_CONTEXT_INDEX.md
5. context/01_PROJECT_BRIEF.md
6. context/02_ENGINEERING_CONTRACT.md
7. context/05_FAIL_CLOSED_CONTROLLER_SPEC.md
8. context/06_DATA_MODEL.md
9. context/08_GATES_AND_EVALUATION.md
10. context/17_SOURCE_TO_ARTIFACT_PRODUCTION_RUN_SPEC.md
11. context/18_EVALUATION_BASELINES_SPEC.md
12. context/19_FINALIZATION_GATE_POLICY_V2_SPEC.md
13. context/20_FINAL_ARTIFACT_AND_PAPER_PACKET_SPEC.md
14. context/21_REPO_AUDIT_OPERATOR_HANDOFF_SPEC.md
15. context/plans/PHASE_14_REPO_AUDIT_OPERATOR_HANDOFF.md

Phase 14 performs repo audit and operator handoff only.
""",
)

print("Phase 14 Repo Audit + Operator Handoff context files created.")
print("Next:")
print("  git status")
print("  git add context tools/setup_context_scripts/setup_phase14_context.py")
print('  git commit -m "Add Phase 14 repo audit operator handoff frozen context"')
print("  git push")
