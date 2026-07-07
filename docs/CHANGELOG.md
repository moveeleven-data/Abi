# Abi Changelog

This changelog summarizes the work performed in this repository from the initial
"Phase 0 of Project Abi is frozen" implementation request through the current
state of the repo.

It is written as an operator-facing engineering history. It records what was
built, what was intentionally kept out of scope, and which invariants have been
preserved across the build.

Current documented endpoint in Git history:

- `aee502e Allow live reader-state evaluation after fake evaluation`
- Active branch during latest changelog update:
  `feature/nonlocal-law-candidate-evidence-synthesis`
- Active working-tree addition during latest changelog update:
  nonlocal law candidate evidence synthesis
- The active runtime direction is the autonomous creative-engine path.

## Standing Invariants

Across the whole sequence, the following invariants were repeatedly preserved:

- Finalization remains fail-closed.
- Workers may produce artifacts, reports, diagnoses, and proposals, but they do
  not finalize.
- Controller/finalization code owns eligibility decisions.
- Runtime state lives outside model context in SQLite and packet artifacts.
- JSON artifacts are registered through the artifact registry with hashes and
  parent lineage.
- Generated runtime outputs belong under ignored runtime directories such as
  `runs/`, `db/`, and `outputs/`.
- Private source material belongs under ignored `inputs/private/`.
- Live OpenAI paths are guarded by explicit opt-in and environment checks.
- Tests use fake or stub clients and do not require API keys.
- Fixture and fake outputs are not treated as real validation evidence.
- Candidate artifacts remain non-final unless a controller policy explicitly
  allows otherwise.
- No `SKILL.md` has been created.

## Phase 0: Repository Skeleton And Infrastructure

Commit/tag:

- `c3a3996 Implement Phase 0 infrastructure`
- `phase-0-complete`

Implemented:

- Python package skeleton under `src/abi/`.
- `pyproject.toml` with allowed dev dependencies.
- CLI bootstrap with `abi init`, `abi status`, and fail-closed `abi finalize`.
- SQLite initialization.
- Run folder creation.
- Deterministic ID helpers.
- Hash helpers.
- Immutable artifact registry.
- Gate records.
- Tests proving missing required gates block finalization.

Explicitly not implemented:

- Model calls.
- OpenAI integration.
- Abi Ear.
- Prose generation.
- Reader simulation.
- Full reread controller loop.

## Phase 1: Deterministic Abi Ear v1

Commit/tag:

- `2d6bf71 Implement Phase 1 Abi Ear deterministic pipeline`
- `phase-1-complete`

Implemented:

- Deterministic local Abi Ear demo pipeline.
- Required benchmark input:
  `"The table is still there in the morning."`
- CLI surface:
  `abi ear demo`
- JSON artifacts for:
  - word-level germ analysis
  - ten variants
  - field model
  - twenty moves
  - ranked move sequence
  - three prose inventions
  - one refined invention
  - reread trace
  - word/move ablation report
  - gate report
  - packet summary
- Artifact registration with parent IDs and hashes.
- Tests for deterministic output and required artifact counts.

Follow-up QA:

- Abi Ear packet output was changed to use unique packet directories so repeated
  `abi ear demo` runs do not overwrite prior artifacts.
- Active phase reporting was corrected from Phase 0 to a clear Phase 1 value.
- Finalization refusal behavior was preserved.

## Phase 2: Deterministic Minimal Reread

Commit/tag:

- `1c67318 Implement Phase 2 Minimal Reread deterministic pipeline`
- `phase-2-complete`

Implemented:

- Deterministic local Minimal Reread demo pipeline.
- CLI surface:
  `abi reread demo`
- Unique packet directory structure:
  `runs/<run_id>/reread/<packet_id>/`
- JSON artifacts for:
  - formal problem
  - germ/afterimage pair
  - consequence graph
  - draft version
  - blind first-read trace
  - reread trace
  - failure diagnosis
  - targeted intervention
  - recomposed draft
  - counterfactual result
  - irreducibility report
  - gate report
  - packet summary
- Active phase tracking for `phase2_minimal_reread`.
- Tests for determinism, required artifact types, parent IDs, unique packet
  directories, gate report existence, and fail-closed finalization.

## Phase 3: Fail-Closed Controller Expansion

Commit/tag:

- `4a4a181 Implement Phase 3 Fail-Closed Controller`
- `phase-3-complete`

Implemented:

- `ControllerDecision` structured decision object.
- Policy-driven gate evaluation.
- `BlockerReport` structured object.
- Controller functions that inspect active runs and produce explicit decisions.
- Hardened finalization path using policy-driven gate checks.
- Run status helpers.
- CLI surfaces such as:
  - `abi controller status`
  - `abi controller blockers`
  - `abi controller demo`
- Tests for missing gates, failed gates, blocking defects, controlled eligible
  decisions, live demo refusal, and preserved prior behavior.

## Phase 4: Deterministic Production Harness Scaffold

Commit/tag:

- `95bfbae Implement Phase 4 Production Harness deterministic scaffold`
- `phase-4-complete`

Implemented:

- Deterministic production harness scaffold.
- Fixture source inputs under `fixtures/production_harness/`.
- CLI surface:
  `abi harness demo`
- Unique packet directory:
  `runs/<run_id>/harness/<packet_id>/`
- JSON artifacts for:
  - source manifest
  - source cards
  - claim cards
  - motif cards
  - image cards
  - risk cards
  - canon/kernel packet
  - artifact genome
  - candidate lineage packet
  - harness gate report
  - harness packet summary
- Parent lineage and artifact registry integration.
- Tests for deterministic output, required artifacts, parent IDs, unique
  packets, active phase, harness gate report, and fail-closed finalization.

## Phase 5: Deterministic Human Calibration Scaffold

Commit/tag:

- `e375eba Implement Phase 5 Human Calibration deterministic scaffold`
- `phase-5-complete`

Implemented:

- Deterministic local calibration scaffold from fixture inputs under
  `fixtures/human_calibration/`.
- CLI surface:
  `abi calibration demo`
- Unique packet directory:
  `runs/<run_id>/calibration/<packet_id>/`
- JSON artifacts for:
  - calibration protocol
  - human reader trial
  - first-read trace
  - reread trace
  - reader-state transition
  - blind comparison
  - baseline comparison
  - calibration summary
  - paper-grade evaluation report
  - calibration gate report
  - calibration packet summary
- Fixture-only marking to avoid real-validation claims.
- Tests proving fixture data is not real validation and finalization remains
  fail-closed.

## Phase 6A-Lite: Model-Readiness Consolidation

Commit/tag:

- `f182213 Implement Phase 6A-lite Model-Readiness Consolidation`
- `phase-6a-lite-complete`

Implemented:

- Shared packet-writing helper.
- Normalized artifact envelope:
  - `schema_version`
  - `artifact_type`
  - `run_id`
  - `lineage_id`
  - `parent_ids`
  - `created_by`
  - `fixture_only`
  - `model_call_id`
  - `payload`
- Artifact list/show CLI.
- Run list/show/latest CLI.
- Packet helper adoption by Abi Ear and at least one other module.
- Preservation of deterministic demo behavior and fail-closed finalization.

Explicitly avoided:

- Model driver.
- OpenAI API calls.
- Fake model client.
- Creative generation changes.
- Broad refactor.
- Dev reset.

## Phase 6B: Fake Model Driver And Structured Outputs

Commit/tag:

- `02b6f29 Implement Phase 6B fake model driver`
- `phase-6b-fake-model-driver-complete`

Implemented:

- Sealed model-driver interface.
- Structured request/response records:
  - `WorkerRequest`
  - `WorkerRole`
  - `WorkerSchema`
  - `ModelDriverResult`
  - `ModelCallRecord`
  - validation error handling
- Fake model client modes:
  - valid structured output
  - invalid JSON
  - malformed structured output
  - schema-valid minimal output
  - simulated client failure
- Schema validation before artifact registration.
- Failure records for `validation_failed` and `client_failed`.
- Normalized envelopes for accepted parsed artifacts.
- Narrow example schema for Abi Ear germ analysis.
- CLI surfaces:
  - `abi model-driver demo`
  - `abi model-call list`
  - `abi model-call show MODEL_CALL_ID`
- Tests proving accepted artifacts receive `model_call_id`, invalid output does
  not register parsed artifacts, and no network/API key is required.

## Phase 7A: Guarded Live Abi Ear Germ Analysis

Commit/tag:

- `c723151 Implement Phase 7A live Abi Ear germ analysis guard`
- `phase-7a-live-abi-ear-germ-analysis-complete`

Implemented:

- Isolated live model adapter.
- Guarded live worker path for Abi Ear germ analysis.
- Explicit opt-in guard:
  `--allow-live-model`
- Environment guard:
  `OPENAI_API_KEY`
- Model configuration via `ABI_OPENAI_MODEL` or documented default.
- Schema validation before artifact registration.
- Model-call records for success, validation failure, and client failure.
- Parsed artifact envelopes with non-null `model_call_id` on success.
- Tests with fake/stub live adapters only.

Preserved:

- Deterministic Abi Ear demo.
- Existing model-driver demo.
- Fail-closed finalization.

## Phase 7B: Guarded Live Abi Ear Field Model

Commit/tag:

- `c398281 Implement Phase 7B live Abi Ear field model guard`
- `phase-7b-live-abi-ear-field-model-complete`

Implemented:

- Abi Ear field-model output schema.
- Guarded live field-model worker using existing model-driver/live-adapter
  conventions.
- CLI support for:
  `abi model-driver live-demo --worker abi_ear_field_model`
- Tests proving opt-in refusal, missing-key refusal, stubbed success,
  validation failure, client failure, and preserved germ-analysis behavior.

## Phase 8: Guarded Live Abi Ear Packet

Commit/tag:

- `e0611ce Implement Phase 8 live Abi Ear packet`
- `phase-8-live-abi-ear-packet-complete`

Implemented:

- Live Abi Ear packet orchestrator.
- Fake-client packet path:
  `abi ear live-demo --client fake`
- Guarded OpenAI packet path:
  `abi ear live-demo --client openai --allow-live-model --max-model-calls 8`
- Packet output covering:
  - germ analysis
  - field model
  - variants
  - moves
  - ranked move sequence
  - prose inventions
  - refined invention
  - reread trace
  - ablation report
  - gate report
  - packet summary
- Schema validation for model-shaped output.
- Model-call budget guard.
- Failure behavior for invalid fake outputs and client failures.

## Phase 9: Guarded Live Minimal Reread Loop

Commit/tag:

- `9483c60 Implement Phase 9 live Minimal Reread loop`
- `phase-9-live-minimal-reread-loop-complete`

Implemented:

- Live Minimal Reread packet orchestrator.
- Fake-client path:
  `abi reread live-demo --client fake`
- Guarded OpenAI path:
  `abi reread live-demo --client openai --allow-live-model --max-model-calls 12`
- Packet output covering:
  - formal problem
  - germ/afterimage pair
  - consequence graph
  - draft version
  - first-read trace
  - reread trace
  - failure diagnosis
  - targeted intervention
  - recomposed draft
  - counterfactual result
  - irreducibility report
  - gate report
  - packet summary
- Schema validation, model-call IDs, budget guard, and fail-closed behavior.

## Phase 10: Source-To-Artifact Production Run v1

Commit/tag:

- `d84f9d8 Implement Phase 10 source-to-artifact production run`
- `phase-10-source-to-artifact-production-run-complete`

Implemented:

- Controlled production run orchestrator.
- Fake production path:
  `abi production live-demo --client fake`
- Guarded OpenAI path:
  `abi production live-demo --client openai --allow-live-model --max-model-calls 24`
- Production packet exposing:
  - source manifest
  - harness packet reference
  - selected germ
  - target effect
  - live Abi Ear packet reference
  - live Minimal Reread packet reference
  - candidate artifact
  - candidate report
  - production gate report
  - production packet summary
- Candidate artifact remained non-final, not human-validated, and not
  finalization-eligible.

## Phase 11: Evaluation, Baselines, And Human-Trace Import v1

Commit/tag:

- `8094f6e Implement Phase 11 evaluation baselines`
- `phase-11-evaluation-baselines-complete`

Implemented:

- Evaluation orchestrator.
- Fake evaluation path:
  `abi evaluation demo --client fake`
- Guarded OpenAI path:
  `abi evaluation demo --client openai --allow-live-model --max-model-calls 12`
- Evaluation packet exposing:
  - evaluation subject
  - candidate artifact reference
  - direct prompt baseline
  - best-of-N baseline summary
  - blind comparison protocol
  - blind comparison result
  - human-trace import
  - reader-state transition comparison
  - baseline comparison report
  - evaluation gate report
  - evaluation packet summary
- Human-trace fixture marked `fixture_only` and `not_real_validation`.
- Baselines marked fixture/fake unless generated by guarded live path.
- Finalization remained fail-closed.

## Phase 12: Finalization Gate Policy v2

Commit/tag:

- `ee201c3 Implement Phase 12 finalization gate policy v2`
- `phase-12-finalization-gate-policy-v2-complete`

Implemented:

- Gate profiles:
  - `infrastructure`
  - `candidate_release`
  - `final_artifact`
- Gate catalog with required gates per profile.
- Release readiness reporting.
- CLI surfaces:
  - `abi gate list`
  - `abi finalization status`
  - `abi finalization status --profile final_artifact`
  - `abi finalize --profile final_artifact`
- Tests proving controlled eligibility can be produced in unit tests while demo
  state still refuses.

Important behavior:

- `abi finalize` remains fail-closed.
- `final_artifact` refuses fixture/candidate state because required evidence and
  approvals are absent.

## Phase 13: Final Artifact And Paper Packet v1

Commit/tag:

- `867e8fc Implement Phase 13 final artifact paper packet`
- `phase-13-final-artifact-paper-packet-complete`

Implemented:

- Final artifact packet orchestrator.
- Fake-client command:
  `abi final-artifact packet --client fake`
- Guarded OpenAI command:
  `abi final-artifact packet --client openai --allow-live-model --max-model-calls 8`
- Packet exposing:
  - source refs
  - candidate text
  - lineage summary
  - hidden consequence report
  - reader effect claim map
  - risk register
  - hostile final audit scaffold
  - paper outline
  - paper evidence map
  - finalization readiness report
  - final artifact packet summary
- Candidate artifact explicitly marked:
  - non-final
  - not human-validated
  - not finalization-eligible
  - no phase-shift claim
- Finalization readiness report says current run is ineligible.

## Operator Tree And Verification Summaries

During the build, operator-facing local summary files were also requested on the
Desktop:

- A full working-directory tree summary.
- A command-output confirmation summary covering Git status, logs, tags, ruff,
  pytest, final-artifact packet creation, finalization status, and finalize
  refusal.

These Desktop files were operator scratch artifacts, not tracked repo runtime
features.

## Phase 14: Repo Audit And Operator Handoff

Commit/tag:

- `2c6a9d9 Add Phase 14 operator handoff audit docs`
- `phase-14-repo-audit-operator-handoff-complete`

Implemented documentation under:

- `docs/phase14_operator_handoff/`

Produced:

- `audit_report.md`
- `command_matrix.md`
- `phase_inventory.md`
- `known_blockers.md`
- `finalization_profile_summary.md`
- `fixture_evidence_safety_report.md`
- `live_model_guardrail_report.md`
- `artifact_schema_envelope_report.md`
- `fresh_clone_verification.md`
- `next_validation_roadmap.md`
- `operator_handoff.md`

Audited:

- Phase tags.
- README command accuracy.
- AGENTS/context consistency.
- CLI behavior.
- Finalization profile behavior.
- Fixture-only evidence safety.
- Live OpenAI guardrails.
- Tests avoiding API keys/network calls.
- Git tracking hygiene for runtime/private/cache paths.
- Artifact envelopes.
- Model-call ID behavior.
- Final-artifact packet non-final status.
- Fresh-clone verification instructions.

The audit clearly recorded that the repo did not yet prove final writing quality,
real human validation, strong baseline victory, hostile final audit success, or
paper readiness.

## Phase 15: Real Validation Protocol And Evidence Plan

Commit/tag:

- `d970299 Add Phase 15 real validation protocol docs`
- `phase-15-real-validation-protocol-complete`

Implemented documentation under:

- `docs/phase15_real_validation_protocol/`

Produced:

- `validation_protocol.md`
- `human_reader_protocol.md`
- `blind_reread_task.md`
- `reader_trace_schema.md`
- `baseline_protocol.md`
- `strongest_rival_protocol.md`
- `raw_model_baseline_protocol.md`
- `hostile_final_audit_checklist.md`
- `evidence_to_gate_mapping.md`
- `pilot_run_plan.md`
- `live_run_budget_plan.md`
- `phase15_operator_checklist.md`

Defined:

- Recruitment criteria.
- Consent/data-use note.
- Blindness rules.
- First-read and reread tasks.
- Opening-transfiguration measurement.
- Paraphrase-loss measurement.
- Attention/confusion/overexplicitness reporting.
- Exclusion criteria.
- Comparison ordering.
- Baseline generation rules.
- Strongest-rival comparison rules.
- Raw-model baseline rules.
- Hostile-audit failure criteria.
- Pilot success thresholds.
- Evidence-to-gate mapping.

No real validation was run.

## Phase 16: First Real Candidate Set / Pilot Artifact Set

Commit/tag:

- `8dcb4c2 Implement Phase 16 first real candidate set`
- `phase-16-first-real-candidate-set-complete`

Implemented:

- Pilot artifact-set orchestrator.
- Fake-client command:
  `abi pilot artifact-set --client fake --source-dir fixtures/production_harness`
- Guarded OpenAI command:
  `abi pilot artifact-set --client openai --source-dir inputs/private/phase16_source --allow-live-model --max-model-calls 36`
- Source manifest with filenames and hashes.
- `.gitignore` protection for private inputs.
- Packet exposing:
  - source manifest
  - generation plan
  - Abi candidate reference
  - direct prompt baseline
  - raw model baseline
  - strongest rival slot
  - neutral label map private
  - blinded reader bundle
  - artifact set manifest
  - pilot readiness report
  - pilot packet summary
- Candidate remained non-final, not human-validated, not finalization-eligible,
  and no-phase-shift-claim.
- Fake baselines marked fixture/fake.
- Strongest-rival slot did not falsely satisfy strongest-rival gates.

## Repo Hygiene And README Realignment

Commit:

- `3cda4c2 Clean up repo layout and polish operator README`

Implemented:

- Moved root `setup_phase*.py` scripts into:
  `tools/setup_context_scripts/`
- Added or updated docs navigation.
- Added `context/README.md` explaining frozen context files.
- Confirmed `.gitignore` protects:
  - `.venv/`
  - `.pytest_cache/`
  - `.ruff_cache/`
  - `db/*.sqlite`
  - `runs/*`
  - `outputs/*`
  - `inputs/private/`
  - `.env`
- Reworked the root README into a simpler operator entry point.

Later README cleanup:

- Public-facing README was shortened and simplified.
- The title was changed to `Abi`.
- Externally awkward "non-claims", commit-hygiene, OpenAI details, local
  verification, and documentation-heavy sections were removed.
- The README now describes Abi as an autonomous creative engine built around the
  repeating pattern:
  `germ -> differentiation -> pressure -> crisis -> recomposition -> return`.

## Pilot OpenAI Bugfixes And Reader-Facing Safeguards

Commits:

- `d65d7cb Fix pilot OpenAI artifact-set model calls`
- `85d219e Fix pilot baseline type metadata`
- `b846f26 Fix pilot reader-facing artifact generation`

Implemented/fixed:

- OpenAI pilot artifact-set path now creates actual model-call records for:
  - `pilot_abi_candidate_ref`
  - `pilot_direct_prompt_baseline`
  - `pilot_raw_model_baseline`
- `counts.model_calls` now reflects actual model calls.
- OpenAI-produced artifacts carry:
  - provider `openai`
  - configured model
  - status `success` when accepted
  - non-null `model_call_id`
  - `fixture_only: false`
- Fake mode remains zero-model-call fixture behavior.
- Direct baseline type is controller-assigned as `direct_prompt`.
- Raw-model baseline type is controller-assigned as `raw_model`.
- The model generates baseline content rather than authoritative role metadata.
- OpenAI pilot workers receive actual source contents only during explicit
  `--allow-live-model` runs.
- Source privacy was preserved:
  - private source contents may be sent only during explicit live runs
  - private contents remain under ignored runtime/private paths
  - private contents are not copied into tracked docs
- Added reader-facing text validator rejecting:
  - too-short live prose
  - JSON text
  - scaffold leakage
  - finalization/validation/gate/non-final metadata terms
  - source-class labels in reader-facing text
- Packet fails closed if candidate or baseline prose is not suitable for readers.

## Strongest-Rival Import And Reader-Kit Tooling

Commits:

- `4755f95 Import strongest rival into pilot artifact set`
- `5bdaccc Export counterbalanced pilot reader kit`

Implemented:

- CLI command to import a strongest-rival text into an existing pilot artifact
  set:
  `abi pilot import-rival --packet-dir ... --rival-file ...`
- Imported rival artifact type such as `pilot_strongest_rival_import`.
- Derived packet directory creation instead of mutating the source packet.
- New private neutral label map with Text A/B/C/D.
- New blinded reader bundle with Text A/B/C/D.
- Source classes hidden from reader-facing bundle.
- Strongest-rival slot marked imported/filled without marking the
  strongest-rival comparison gate passed.
- Fix for stale artifact IDs in derived pilot manifests.
- CLI command to export counterbalanced reader kits:
  `abi pilot export-reader-kit --packet-dir ... --out-dir ... --reader-count 12`
- Reader-specific bundle files:
  - `reader_001_bundle.md`
  - through configured reader count
- Counterbalanced/rotated presentation order.
- Private order schedule containing reader ID, presentation order, and source
  classes.
- Response form template from Phase 15 protocol.
- Operator README for what to send readers and what to keep private.

Current status:

- These reader-kit and human-collection directions later became non-active after
  core autonomous realignment.

## Core Autonomous Realignment

Commit/tag:

- `037ee85 Realign Abi around autonomous creative core`
- `pre-core-autonomous-realignment` marks the point before this shift.

Implemented:

- Repositioned active runtime direction around autonomous internal creative
  evaluation rather than human/paper/public validation.
- Added context:
  `context/24_CORE_REALIGNMENT_REMOVE_HUMAN_PAPER_VALIDATION.md`
- Active path became:
  - source material
  - Abi Ear
  - Minimal Reread
  - candidate/baseline/rival set
  - internal reader-state workers
  - failure diagnosis
  - targeted recomposition
  - counterfactual ablation
  - rival preservation
  - fail-closed autonomous finalization
- Active finalization profile became:
  `autonomous_creative_candidate`
- Human reader dry runs, reader-kit export workflows, human calibration runtime
  direction, paper-grade validation language, and public-validation finalization
  were removed from the active path.
- Legacy external validation artifacts and docs remain historical/non-active.

## Autonomous Internal Reader Lab v1

Commit:

- `573786c Implement autonomous internal reader lab v1`

Implemented:

- Autonomous internal reader-lab packet scaffold.
- Fake internal reader mode.
- Internal reader-state artifacts, including stream/reread/forensic/hostile/rival
  comparison/failure/gate-style outputs.
- Internal evidence outputs for autonomous candidate evaluation.
- Preservation of fail-closed finalization.

## Autonomous Closed-Loop Revision v1

Commit:

- `7c10e7c Implement autonomous closed-loop revision v1`

Implemented:

- Autonomous closed-loop revision pipeline.
- Revision subject loading from internal reader-lab packets.
- Failure diagnosis selection.
- Causal handle selection.
- Revision work order.
- Patch proposal.
- Controller-applied revised candidate text.
- Revision diff report.
- Old/new/rival comparison.
- Local-law case notes.
- Autonomous closed-loop gate report and packet.

## Guarded Live Internal Reader Workers

Commit:

- `c3dc1d4 Add guarded live internal reader workers`

Implemented:

- Guarded live internal reader-lab workers using structured outputs and model
  driver records.
- Live/stub paths for internal reader worker schemas.
- Opt-in and API-key guards.
- Validation-failure and client-failure recording.
- Preservation of fake reader-lab mode.

Follow-up bugfixes:

- `9a31af1 Fix internal reader structured output schemas`
  - Made internal reader-lab schemas compatible with OpenAI Structured Outputs.
  - Ensured nested object schemas use `additionalProperties: false`.
- `a333ab3 Align internal reader failure taxonomy`
  - Centralized or synchronized internal failure taxonomy.
  - Allowed or normalized `thesis_replacing_artifact`.
  - Kept arbitrary unknown failure types rejected.
- `0c36665 Make autonomous gate report controller-owned`
  - Moved autonomous candidate gate authority back to controller logic.
- `29bfdcc Tighten live internal reader evidence targeting`
  - Hardened evidence targeting for live internal reader outputs.

## Guarded Live Autonomous Revision Workers

Commit:

- `3b853b5 Add guarded live autonomous revision workers`

Implemented:

- Guarded live workers for autonomous closed-loop revision.
- Model-driver-backed structured outputs.
- OpenAI path behind explicit opt-in and API-key guard.
- Stubbed live tests only.
- Preservation of fake revision mode.

Integrity follow-up commits:

- `3aa0867 Tighten autonomous revision evidence integrity`
- `a9dc392 Constrain autonomous revision comparison provenance`
- `65d0028 Tighten autonomous revision ablation alignment`
- `888f207 Enforce autonomous revision target-region contract`
- `825305a Apply autonomous revision patches through controller`
- `96af17e Define autonomous revision patch target contract`
- `58dd452 Make autonomous revision patch targets controller-owned`
- `baec73c Apply autonomous revision patches by controller-owned spans`
- `0733dc3 Add controller-owned autonomous revision work order`
- `85f7b84 Use offset-backed autonomous revision work orders`
- `072c565 Make autonomous revision evidence rows controller-owned`

These passes hardened:

- Controller-owned patch targets.
- Controller-owned patch spans.
- Offset-backed work orders.
- Bounded patch application.
- Evidence row authority.
- Provenance constraints.
- Ablation alignment.
- Rejection of invented IDs or model-authored control-plane fields.
- Preservation of fail-closed autonomous finalization.

## Executed Counterfactual Ablation v1

Commit:

- `fd3ab72 Implement executed counterfactual ablation`

Implemented:

- Executed counterfactual ablation pipeline.
- CLI surface through autonomous ablation command group.
- Executed ablation packet artifacts including:
  - subject manifest
  - work order
  - actual ablation variant set
  - execution report
  - internal reader comparison
  - old/new/rival comparison
  - comparison consistency report
  - causal effect report
  - gate report
  - packet summary
- Guarded live/stub support for internal comparison where applicable.
- Distinctions between:
  - countable executed variants
  - planned-only probes
  - no-op controls
  - operation-mismatch controls
- Fail-closed gate reporting.

## Ablation-Informed Revision Cycle v1

Commit:

- `cda2f46 Implement ablation-informed revision cycle`

Implemented:

- Deterministic/fake ablation-informed revision cycle.
- CLI surface:
  `abi autonomous revise-from-ablation --client fake --executed-ablation-packet <packet_dir>`
- Consumption of executed ablation packets.
- Cycle 2 packet artifacts:
  - `ablation_informed_revision_subject_manifest`
  - `ablation_evidence_summary`
  - `cycle2_base_candidate_selection`
  - `selected_next_failure_or_handle`
  - `ablation_informed_revision_work_order`
  - `cycle2_patch_proposal`
  - `cycle2_revised_candidate_text`
  - `cycle2_revision_diff_report`
  - `cycle2_preliminary_old_new_rival_comparison`
  - `cycle2_gate_report`
  - `cycle2_packet`
- Behavior:
  - treats the prior repair as not proven
  - can treat packet_0030 as noncausal/cosmetic evidence rather than proof
  - selects a controller-composed base from evidence-supported changes
  - preserves embodiment insight
  - targets record/law/proof/answer compression
  - preserves strongest-rival pressure
  - remains non-final and fail-closed

## Guarded Live Ablation-Informed Revision v1

Commit:

- `3311390 Add guarded live ablation-informed revision`

Implemented:

- Guarded model-driver-backed OpenAI path for:
  `abi autonomous revise-from-ablation --client openai --executed-ablation-packet <packet_dir> --allow-live-model --max-model-calls 8`
- OpenAI mode now:
  - refuses without `--allow-live-model`
  - refuses without `OPENAI_API_KEY`
  - checks max-model-call budget
  - uses the model driver
  - uses structured outputs
  - validates schemas before artifact registration
  - records `model_call_id` on model-produced artifacts
  - fails closed on malformed output
- Added structured-output schemas:
  - `AblationInformedBaseSelectionOutput`
  - `AblationInformedHandleSelectionOutput`
  - `AblationInformedPatchProposalOutput`
- Controller owns:
  - source packet references
  - executed ablation packet references
  - base candidate options
  - base candidate IDs
  - base candidate text assembly
  - patch target inventory
  - patch spans
  - before text
  - revised text assembly
  - diff report
  - gate report
  - finalization status
- Model may provide only constrained:
  - base option choice from controller list
  - next handle interpretation
  - patch replacement text
  - rationale
  - local-law explanation
  - uncertainty
- Model must not own:
  - finalization fields
  - gate pass/fail
  - before text
  - authoritative full revised text
  - target IDs
  - span IDs
  - evidence counts
  - phase-shift claim
  - rival-defeated status as gate truth
- Tests added for:
  - fake path preservation
  - OpenAI guard refusal without opt-in
  - OpenAI refusal without API key
  - stubbed OpenAI success
  - `model_call_id` on model-produced artifacts
  - controller-owned base options
  - invented base ID fail-closed behavior
  - bounded patch proposals
  - controller-assembled revised candidate and diff
  - preliminary comparison marked not proof
  - fail-closed cycle2 gate report
  - malformed output producing `validation_failed` with no parsed artifact

Verification after implementation:

- `ruff check .` passed.
- `pytest` passed with 192 tests.
- Fake CLI path produced an ablation-informed packet.
- Guarded OpenAI command without `--allow-live-model` refused before model calls.
- `autonomous_creative_candidate` finalization remained refused.

## Ablation-Informed Integrity And Source-Packet Adapter Work

Commits:

- `c2e2e2a Enforce ablation-informed patch ledger integrity`
- `544e967 Allow executed ablation of ablation-informed revision packets`

Implemented:

- Hardened ablation-informed revision packet integrity around patch ledgers,
  diff consistency, and controller-owned text spans.
- Added executed-ablation support for revision source packets whose
  `revision_packet_kind` is `ablation_informed_revision`.
- Preserved support for older executed-ablation packets sourced from
  `autonomous_revision`.
- Added source packet metadata so executed-ablation packets can record whether
  their source was an original autonomous revision packet or a later
  ablation-informed revision packet.
- Prevented adapter code from assuming every executed-ablation source packet
  contains legacy autonomous closed-loop files.
- Preserved fail-closed behavior when required source files or integrity gates
  are missing.

Verification:

- `ruff check .` passed.
- `pytest` passed after the executed-ablation source-packet adapter work.
- Executed ablation of ablation-informed revision packets produced valid
  executed-ablation packets without weakening finalization.

## Revise-From-Ablation Source-Packet Adapter

Current branch work:

- `fix/revise-from-ablation-source-packet-adapter`

Implemented:

- `abi autonomous revise-from-ablation` now consumes executed-ablation packets
  sourced from either:
  - `autonomous_revision`
  - `ablation_informed_revision`
- Added source-kind detection and normalization for cycle2 ablation-informed
  source packets.
- Added required-file and integrity checks for ablation-informed source packets:
  - `cycle2_packet.json`
  - `cycle2_revised_candidate_text.json`
  - `cycle2_revision_diff_report.json`
  - `cycle2_applied_patch_ledger.json`
  - `cycle2_gate_report.json`
- Required the ablation-informed source packet to preserve:
  - text/diff consistency
  - applied-patch ledger consistency
  - non-final status
  - no phase-shift claim
  - no finalization eligibility
- Normalized source packet evidence into the ablation-informed revision subject
  manifest without treating newer cycle2 packets as legacy packet_0030 packets.
- Preserved compatibility aliases where older packet consumers still expect
  packet_0030-style fields.
- Updated packet outputs to record:
  - `source_revision_packet_kind`
  - `source_revision_packet_id`
  - `source_revision_packet_dir`
  - source artifact IDs
  - source revision diff
  - source patch ledger
- Updated the evidence summary and base-selection outputs so they refer to the
  actual source revision packet and its executed-ablation verdicts.
- Kept strongest-rival pressure, bounded revision behavior, and controller
  ownership intact.

Verification:

- `ruff check .` passed.
- `pytest` passed with 211 tests.
- Fake revise-from-ablation from old source packet succeeded:
  `abi autonomous revise-from-ablation --client fake --executed-ablation-packet runs\run_8fa54199f23f3d8e\executed_ablation\packet_0004`
- Fake revise-from-ablation from ablation-informed source packet succeeded:
  `abi autonomous revise-from-ablation --client fake --executed-ablation-packet runs\run_8fa54199f23f3d8e\executed_ablation\packet_0008`
- Guarded OpenAI path without `--allow-live-model` refused before model calls:
  `abi autonomous revise-from-ablation --client openai --executed-ablation-packet runs\run_8fa54199f23f3d8e\executed_ablation\packet_0008`
- `autonomous_creative_candidate` finalization remained refused.

## Updates Since Last Changelog Refresh

Current endpoint:

- `5dcf829 Fix object-motion generation materiality feedback`

The work since the previous changelog refresh moved Abi from a recursive
ablation-informed revision path into a broader autonomous evidence loop with
macro recomposition, reader-state evaluation, supervised authorization, narrow
residual targeting, and one-shot object-motion generation.

### Ablation Evidence And Pivot Policy

Commits:

- `15f90f6 Add ablation evidence dominance policy`
- `820a304 Add residual blocker pivot policy`
- `a3acabd Lock pivot base selection to preserve useful repair`

Implemented:

- Evidence dominance rules for ablation-informed revision.
- Residual-blocker pivot logic so the system can pivot from a weak or noncausal
  prior repair without treating it as proven.
- Controller-owned base selection for pivot repairs.
- Preservation of useful embodied gains while keeping strongest-rival pressure
  active.
- Tests proving gate failure remains correct and finalization remains
  fail-closed.

### Autonomous Evidence Synthesis v1

Commit:

- `d07031e Add autonomous evidence synthesis`

Implemented:

- Evidence synthesis packets that aggregate reader-lab, revision,
  executed-ablation, rival, and blocker evidence.
- Candidate/proof summaries and evidence-weighted current-best selection.
- Explicit distinction between useful evidence, weak evidence, predicted-only
  claims, and unresolved blockers.
- Non-final synthesis gate reports.

### Bounded Macro Recomposition

Commits:

- `e07acbc Implement bounded macro recomposition`
- `709c926 Add guarded live bounded macro recomposition`
- `122a12b Enforce macro recomposition target coverage`
- `57e0621 Add generic executed ablation subject adapter`

Implemented:

- Bounded macro recomposition packets from synthesis-selected candidates.
- Fake and guarded OpenAI paths using structured outputs.
- Controller-owned final assembly and diff reports.
- Macro target coverage checks.
- Generic executed-ablation subject adapter so executed ablation can read
  multiple supported revision packet kinds.
- Guarded live path refusing without explicit opt-in or required environment.

### Evidence Synthesis Timeline And Reader-State Evaluation

Commits:

- `fae44bf Update evidence synthesis for macro proof timeline`
- `556cf17 Add internal reader state evaluation`
- `92d0cbf Add reader-state evidence adjudication`
- `b73f2cc Support synthesis-guided macro recomposition briefs`

Implemented:

- Evidence synthesis subject timeline v2.
- Internal reader-state evaluation packets over synthesis-selected macro
  candidates.
- Reader-state evidence adjudication inside synthesis.
- Synthesis-guided macro recomposition briefs that preserve the selected macro
  candidate and route next work through reader-state evidence rather than
  blind generation.

### Target-Addressed Macro Recomposition Hardening

Commits:

- `fb468aa Add target-addressed live macro recomposition`
- `338b304 Fix OpenAI structured output schema parity`
- `190adb2 Add target-addressed macro corrective retry`
- `ba5715d Add span-level macro active target validation`
- `6a9b30e Fix finality claim validator semantics`
- `4aa697c Fix macro retry failure-set consistency`
- `92910db Fix macro target assignment consistency`
- `f7e3cc9 Tighten macro2 materiality feedback contract`
- `ebe12c0 Normalize model active-target claims`

Implemented:

- Target-addressed live macro recomposition with guarded OpenAI support.
- OpenAI structured-output schema parity fixes.
- Bounded corrective retry behavior for target-addressed macro recomposition.
- Span-level active-target granularity and validation.
- Field-aware, negation-aware finality/phase-shift claim validation.
- Retry failure-set consistency checks.
- Macro target-assignment consistency checks.
- Macro-2 materiality feedback contract.
- Controller-owned active-target normalization so model claims cannot redefine
  active targets.

### Macro-2 And Object-Event Evidence Synthesis

Commits:

- `bb919a7 Add macro2 proof supersession to evidence synthesis`
- `96c6328 Consume macro2 reader-state evidence in synthesis`
- `b712c22 Add evidence-grounded next target strategy`
- `d3e0ba9 Add bounded object-event pressure recomposition`
- `305fdba Add object-event proof-aware synthesis`
- `afa3b52 Consume object-event reader-state evidence in synthesis`

Implemented:

- Candidate/proof supersession logic for macro-2 evidence.
- Reader-state-aware synthesis for macro-2 packets.
- Evidence-grounded next-target strategy planning.
- Bounded object-event pressure recomposition.
- Object-event proof-aware synthesis.
- Object-event reader-state-aware synthesis.

### Loop Integrity And Supervised Authorization

Commits:

- `7b35686 Add evidence loop-level review`
- `c6334f9 Clean up evidence loop integrity before generation`
- `d9cfdef Add supervised next-cycle authorization`
- `2938935 Make next-target strategy authorization-aware`

Implemented:

- Loop-level evidence review packets.
- Loop-integrity cleanup before further generation.
- Supervised next-cycle authorization packets.
- Authorization-aware next-target strategy planning.
- Guardrails that prevent generation from proceeding when proof, reader-state,
  or operator authorization prerequisites are not satisfied.

### Narrow Residual Targeting And Object-Motion Generation

Commits:

- `1dc1306 Add narrow residual target selection`
- `b90dec0 Add object-motion causality work-order planning`
- `ba9f485 Add residual generation authorization`
- `0622c6d Add bounded object-motion causality generation`
- `5dcf829 Fix object-motion generation materiality feedback`

Implemented:

- Operator-selected narrow residual target packets.
- Object-motion causality work-order packets identifying selected region,
  target units, protected effects, and future generation contract.
- Supervised residual generation authorization with one-attempt budget and
  explicit operator review.
- One-shot bounded residual candidate generation for object-motion causality.
- Artifact-driven object/action/consequence term validation based on the
  work-order target-unit map rather than permanent hardcoded production terms.
- Explicit model prompt and work-order materiality feedback:
  - selected-region materiality required
  - replacement must be genuinely re-authored
  - protected effects do not require preserving sentence architecture
  - lexical substitutions are insufficient
  - target-unit mappings are necessary but insufficient
  - required changed unique word count is `10`
  - required changed ratio is `0.12`
  - overlapping units must be reconciled in one integrated replacement
- Materiality failure reporting with:
  - before word count
  - replacement word count
  - changed unique word count
  - changed unique word ratio
  - required thresholds
  - exact-copy flag
  - near-copy / under-materiality classification
  - failed materiality reason
  - target unit IDs
- Failed-attempt hygiene:
  - failed packets do not assert actual `authorization_consumed: true`
  - failed packets do not assert actual `candidate_generated: true`
  - planned intent is recorded separately
  - refused outputs retain `authorization_consumed: false`,
    `candidate_generated: false`, and `candidate_artifact_id: null`
- Duplicate prevention now distinguishes accepted/generated candidates from
  validation-failed attempts.

Verification at the object-motion materiality endpoint:

- `ruff check .` passed.
- `pytest` passed with 370 tests.
- Guarded residual OpenAI generation without `--allow-live-model` refused before
  model calls with `model_calls: 0`.
- `gate list` succeeded.
- `finalization status --profile autonomous_creative_candidate` remained
  ineligible.
- `finalize --profile autonomous_creative_candidate` refused.

## Updates Since The Previous Changelog Endpoint

These entries cover the commits after `5dcf829 Fix object-motion generation
materiality feedback`.

### README Cleanup

Commit:

- `676cb0e update readme`

Implemented:

- Simplified the top-level README around Abi's current autonomous
  creative-engine shape.
- Removed outdated public-facing validation/paper positioning language.
- Kept the README focused on Abi's architecture, current capabilities, and
  repository layout.

### Targeted Provisional Reader-State Evaluation

Commit:

- `0e498f8 Add targeted provisional reader-state evaluation`

Implemented:

- Targeted internal reader-state evaluation support for provisional residual
  candidates.
- Autonomous evidence synthesis ingestion for those provisional reader-state
  packets.
- Tests covering targeted provisional evaluation and its synthesis
  integration.

### Candidate Evidence Graph Adjudication

Commit:

- `defcdea Adjudicate residual candidate evidence graph in synthesis`

Implemented:

- Candidate evidence graph adjudication inside autonomous evidence synthesis.
- Explicit comparison of candidate evidence states rather than treating newer
  residual packets as automatically superior.
- Regression tests for evidence graph behavior and candidate selection
  outcomes.

### Loop-Integrity Cleanup Checkpoint

Commit:

- `54dd057 Add loop integrity cleanup checkpoint`

Implemented:

- `loop_integrity_cleanup` packet production.
- CLI support for creating loop-integrity cleanup checkpoints before further
  generation.
- Controller state support for the cleanup checkpoint phase.
- Tests proving cleanup packets preserve fail-closed loop behavior.

### Cleanup-Aware Supervised Strategy Handoff

Commit:

- `12cb7e0 Add cleanup-aware supervised strategy handoff`

Implemented:

- Cleanup-aware supervised next-cycle authorization.
- Cleanup-aware next-target strategy planning.
- Residual target selection updates that account for cleanup packet state.
- Guardrails preventing follow-on generation from proceeding without the
  expected cleanup and authorization evidence.

### Target-Aware Residual Generation Handoff

Commit:

- `8ab798a Add target-aware residual generation handoff`

Implemented:

- Shared residual target adapter registry in `residual_targets.py`.
- Target-aware support for:
  - object-motion causality specificity
  - tactile inevitability gaps
- Generic residual intervention generator schema and OpenAI adapter prompt path.
- Target-aware residual work-order planning with:
  - target adapter IDs
  - target adapter versions
  - work-order contract versions
  - semantic preflight checks
  - target-unit validation
  - supersession metadata for stale work orders
- Target-aware residual generation authorization with a recorded
  `residual_generation_contract`.
- Target-aware residual candidate generation dispatch.
- Tactile validation that rejects decorative, generic, abstract, or
  object-motion-relabel outputs when the selected target is tactile
  inevitability.
- Internal reader-state loader compatibility for supported residual target
  packet types.

Verification at this endpoint:

- `ruff check .` passed.
- `pytest` passed with 391 tests.
- Planning from
  `runs\run_8fa54199f23f3d8e\residual_target_selection\packet_0003` produced
  `residual_work_order\packet_0005`.
- The corrected tactile work order superseded stale `packet_0004` without
  making model calls.
- `gate list` succeeded.
- `finalization status --profile autonomous_creative_candidate` remained
  ineligible.
- `finalize --profile autonomous_creative_candidate` refused.

## Updates Since Target-Aware Residual Generation Handoff

These entries cover the work after
`8ab798a Add target-aware residual generation handoff`.

### Target-Aware Residual Materiality Contracts

Commit:

- `05a1e96 Add target-aware residual materiality contracts`

Implemented:

- Added target-aware materiality contract support for residual-generated
  candidates.
- Made residual-generation validation distinguish target-specific materiality
  requirements from generic prose polish.
- Preserved fail-closed behavior for candidates that do not satisfy the selected
  target contract.

### Target-Aware Executed Ablation Controls

Commit:

- `7570baa Add target-aware executed ablation controls`

Implemented:

- Added executed-ablation controls for residual-generated bounded candidates.
- Kept ablation evidence tied to the selected residual target and candidate
  packet type.
- Preserved controller ownership of proof and finalization semantics.

### Target-Aware Ablation Comparator Consistency

Commits:

- `b92f161 Add target-aware ablation comparator consistency`
- `cd9e029 Fix target-aware ablation role consistency negation`

Implemented:

- Added comparator consistency checks for target-aware ablation packets.
- Hardened role-consistency handling so negated or diagnostic statements do not
  become false positives.
- Kept rejected or diagnostic ablation outputs from being promoted as proof.

### Target-Aware Residual Proof Adjudication

Commit:

- `e486d7c Adjudicate target-aware residual proof in synthesis`

Implemented:

- Updated autonomous evidence synthesis to adjudicate target-aware residual
  proof.
- Required candidate/proof alignment before residual candidates can supersede
  earlier candidates.
- Preserved fail-closed finalization when proof is generic, role-inconsistent,
  fixture-only, or otherwise non-authoritative.

### Target-Aware Cleanup And Supervised Authorization

Commits:

- `9327fa9 Accept target-aware residual cycle cleanup`
- `d7c7770 Authorize strategy from target-aware cleanup`

Implemented:

- Extended loop-integrity cleanup to accept the target-aware residual evidence
  cycle.
- Added supervised authorization for strategy-only continuation from that
  cleanup state.
- Kept next-generation authorization separate from next-strategy authorization.

### Hostile Scaffold Residual Target Support

Commit:

- `a0b2e9f Add hostile scaffold residual target planning`

Implemented:

- Added `hostile_scaffold_visibility` as a residual target.
- Added planning support for hostile-scaffold work orders while keeping
  candidate generation separately authorized.
- Preserved the strongest-rival and no-final-claim blockers.

### Hostile Scaffold Work-Order Alignment

Commit:

- `974d8e4 Align hostile scaffold work-order units with selected region`

Implemented:

- Aligned hostile-scaffold target units with the selected intervention region.
- Added checks that prevent region/unit mismatch from silently producing an
  invalid work order.

### Hostile Scaffold Generation Contract Readiness

Commit:

- `ba3d0da Add hostile scaffold generation contract readiness`

Implemented:

- Added generation-contract readiness for hostile-scaffold residual generation.
- Kept hostile-scaffold generation bounded by selected units, protected effects,
  and materiality constraints.

### Hostile Scaffold Materiality And Leakage Feedback

Commits:

- `b85c317 Strengthen hostile scaffold generation materiality feedback`
- `d1d9101 Strengthen hostile scaffold ordinary-table feedback`
- `7162716 Improve hostile scaffold semantic leakage feedback`

Implemented:

- Strengthened feedback for hostile-scaffold generation failures.
- Added ordinary-table unit feedback so near-synonym sentence polish does not
  pass as material hostile-scaffold reduction.
- Added semantic leakage feedback so scaffold language and explanatory residue
  remain visible to the validator.
- Preserved retry hygiene: failed packets remain diagnostics, not candidates,
  and do not consume authorization.

### Failed Hostile Scaffold Generation Adjudication

Commit:

- `2c9253b Adjudicate failed hostile scaffold generation path`

Implemented:

- Autonomous evidence synthesis now recognizes repeated failed hostile-scaffold
  generation attempts.
- Failed hostile packets are recorded as diagnostic evidence, not accepted
  candidates.
- The hostile path is marked
  `paused_or_exhausted_pending_strategy_review` after repeated failures.
- The residual generation authorization remains unconsumed unless a candidate
  is actually accepted.

### Failed Hostile Awareness In Next-Target Strategy

Current branch update:

- `fix/next-target-strategy-failed-hostile-awareness`

Implemented:

- Next-target strategy now consumes failed-target adjudication from the source
  synthesis/loop-review/cleanup/authorization chain.
- `hostile_scaffold_visibility` is written into
  `failed_target_status_map` with:
  - failed packets `packet_0064`, `packet_0065`, `packet_0066`, `packet_0067`
  - `failed_attempt_count: 4`
  - `target_status: paused_or_exhausted_pending_strategy_review`
  - `next_allowed_status: strategy_review_only`
  - `generation_retry_recommended: false`
- `hostile_scaffold_visibility` remains visible for auditability but is no
  longer listed as available for operator selection.
- Stale strategy packets that still show hostile scaffold as available now
  refuse selection when their linked synthesis has failed-hostile adjudication.

Verification at this endpoint:

- `ruff check .` passed.
- `pytest` passed with 432 tests.
- Planning from
  `runs\run_8fa54199f23f3d8e\supervised_cycle_authorization\packet_0005`
  produced
  `runs\run_8fa54199f23f3d8e\next_target_strategy\packet_0010`.
- `packet_0010` preserved current best `bounded_macro_recomposition/packet_0063`,
  proof `executed_ablation/packet_0034`, and reader-state
  `internal_reader_state_evaluation/packet_0013`.
- `packet_0010` generated no candidate and made zero model calls.
- Stale `next_target_strategy/packet_0009` refused hostile-scaffold selection
  with zero model calls.
- `finalization status --profile autonomous_creative_candidate` remained
  ineligible.
- `finalize --profile autonomous_creative_candidate` refused.

## Updates Since The Failed-Hostile Strategy Endpoint

This section records the work added after the previous changelog endpoint,
which ended at failed-hostile awareness in next-target strategy planning.

### README And Presentation Entry Point

Commits:

- `c6d76fb Highlight Abi intro presentation`
- `49ce921 Make README a visual entry point`

Implemented:

- Added the Abi intro PDF under `docs/abi_intro.pdf`.
- Simplified the top-level README into a centered, presentation-first entry
  point.
- Removed older public-facing operational clutter from the README so the root
  page functions as a clean visual doorway rather than an internal operator
  manual.

### Ending-Return Residual Target Support

Commits:

- `e4f57b7 Add ending return residual target planning`
- `d647b4c Add ending return generation handoff readiness`
- `1d8e9c2 Tighten ending return reset semantics diagnostics`
- `3351141 Tighten ending return global relation diagnostics`
- `da13f80 Adjudicate failed ending return generation path`

Implemented:

- Added `ending_explains_return_risk` as a residual target focused on the
  final-return/opening-transformation region.
- Added work-order planning for ending-return risk while keeping generation
  separately authorized and fail-closed.
- Added generation handoff readiness with target-specific materiality,
  semantic validator metadata, ablation controls, reader-state focus, and
  overlap-cluster reporting.
- Tightened reset-semantics diagnostics so clearing, erasure, restart, or
  repeat-without-carry language is rejected when it turns return into reset.
- Tightened global-relation diagnostics so return must be enacted through
  object pressure rather than explained as a thesis.
- Added failed-generation adjudication for ending-return attempts so failed
  packets remain diagnostic evidence and do not become accepted candidates or
  consume unrelated authorizations.

Preserved:

- No live model call was required by tests.
- No candidate was accepted without later ablation/reader-state evidence.
- No finality, phase-shift, or strongest-rival defeat claim was introduced.

### Architecture/Evidence Risk Checkpoint And Strategy Routing

Commits:

- `27d2965 Add architecture evidence risk checkpoint`
- `716f71d Make next-target strategy checkpoint-aware`
- `faf44fc Add checkpoint strategy direction review`

Implemented:

- Added an architecture/evidence-risk checkpoint before further creative
  strategy.
- Made next-target strategy checkpoint-aware so stale pre-checkpoint strategy
  packets cannot continue the loop without the checkpoint.
- Added checkpoint strategy direction review as an operator-reviewed direction
  step before selecting sensitive residual targets.
- Preserved current best `bounded_macro_recomposition/packet_0063`, proof
  `executed_ablation/packet_0034`, and reader-state
  `internal_reader_state_evaluation/packet_0013` as the governing evidence
  references for the new proof/no-answer direction.

### Generic Target Artifact Aliases And Adapter Audit

Commits:

- `c6798a5 Add generic target artifact aliases`
- `a917399 Add target adapter contract audit`

Implemented:

- Added generic target artifact aliases so consumers can prefer
  `target_unit_map` and `target_diagnostic` while legacy artifact names remain
  compatible.
- Added target-adapter contract audit coverage for residual target adapters,
  including generation readiness, alias policy status, selected target scope,
  and current-run usage classification.
- Preserved legacy packet compatibility while steering new code toward
  generic target artifacts.

### Proof-No-Answer Residual Target Planning

Commit:

- `afeeb77 Add proof no-answer residue target planning`

Implemented:

- Added `proof_no_answer_residue` as a residual target.
- Added direction-review-gated selection for proof/no-answer work.
- Added proof/no-answer work-order planning against the
  `proof_no_outside_answer_region`.
- Added five target units:
  - `no_outside_answer_embodied_in_room`
  - `sky_silence_without_thesis`
  - `line_bears_weight_without_abstraction`
  - `proof_stays_in_object_carry`
  - `answer_absence_registered_by_objects`
- Preserved the rule that proof/no-answer work must not retry hostile scaffold,
  ending-return, object-motion, or tactile paths by inertia.
- Kept generation out of the planning command.

### Proof-No-Answer Generation Handoff

Commit:

- `85c7584 Add proof no-answer generation handoff`

Implemented:

- Promoted `proof_no_answer_residue` from planning-only metadata to
  generation-ready handoff metadata.
- Added:
  - `generation_contract_version: 1`
  - `materiality_policy_id:
    proof_no_answer_residue_generation_materiality_v1`
  - `semantic_validator_id: proof_no_answer_residue_semantic_validator_v1`
  - prompt contract
    `autonomous.residual_intervention_generation.v1.proof_no_answer_residue`
  - schema `ResidualInterventionGenerationOutput@1`
- Added proof/no-answer materiality and semantic checks covering:
  - embodied room/object carry
  - no outside answer intrusion
  - sky/silence not becoming thesis or doctrine
  - proof held in line/object/mark/carry rather than abstraction
  - answer absence registered through objects/room
  - object/tactile field preservation
  - failed-path retry prevention
  - no rival imitation, finality claim, phase-shift claim, or strongest-rival
    defeat claim
- Added overlap-cluster reporting for the shared source sentence used by
  `proof_stays_in_object_carry` and
  `answer_absence_registered_by_objects`.
- Added proof/no-answer authorization support so only corrected,
  generation-ready work orders can authorize one bounded generation attempt.

Real packet result:

- Re-running proof-no-answer work-order planning from
  `runs\run_8fa54199f23f3d8e\residual_target_selection\packet_0010`
  produced `residual_work_order\packet_0015`.
- `packet_0015` superseded the older placeholder `packet_0014`.
- Authorization from `packet_0015` produced
  `residual_generation_authorization\packet_0006`.
- Guarded OpenAI generation without `--allow-live-model` refused before model
  calls.

### Proof-No-Answer Evidence Handoff Metadata Finalization

Commit:

- `d7f7e0f Finalize proof no-answer evidence handoff metadata`

Implemented:

- Added missing operator/downstream aliases for proof-no-answer evidence
  handoff metadata:
  - `ablation_controls`
  - `target_specific_ablation_controls`
  - `reader_state_focus`
  - `reader_state_evaluation_focus`
  - `target_specific_reader_state_focus`
- Hardened proof-no-answer work-order supersession so a work order missing
  those aliases is considered stale before live generation.
- Hardened proof-no-answer generation authorization so stale work orders with
  missing evidence handoff metadata refuse instead of authorizing a live
  attempt.
- Ensured corrected work orders, authorization packet summaries, target-unit
  integration policies, and residual generation contracts carry non-null
  ablation controls and reader-state focus.

Real packet result:

- Re-running proof-no-answer work-order planning from
  `runs\run_8fa54199f23f3d8e\residual_target_selection\packet_0010`
  produced `residual_work_order\packet_0016`.
- `packet_0016` superseded `packet_0015` with
  `supersession_reason:
  proof_no_answer_generation_handoff_metadata_missing`.
- Authorization from `packet_0016` produced
  `residual_generation_authorization\packet_0007`.
- `packet_0007` remains unconsumed, generated no candidate, and recorded
  `counts.model_calls: 0`.
- Guarded OpenAI generation from `packet_0007` without `--allow-live-model`
  refused before model calls.

### Proof-No-Answer Generation Feedback And Failed-Generation Memory

Commits:

- `052f7a5 Tighten proof no-answer generation feedback diagnostics`
- `9c219ba Adjudicate failed proof no-answer generation path`
- `e1cec85 Finalize checkpoint proof failed-target memory`

Implemented:

- Tightened proof/no-answer generation feedback and diagnostics after a failed
  live attempt so the next model-facing contract more explicitly rejects:
  - abstract answer language
  - external proof or doctrine
  - explanation that arrives before object pressure
  - weak object carry
  - failed-path retry patterns
- Added failed-generation adjudication for proof/no-answer residue attempts so
  failed packets are recorded as diagnostic evidence, not silently ignored or
  treated as accepted candidates.
- Ensured failed proof/no-answer generation does not consume authorization as a
  successful candidate path.
- Threaded failed proof/no-answer target memory into the architecture checkpoint
  and checkpoint-aware planning layers.
- Preserved fail-closed behavior: failed generation evidence can steer future
  strategy, but it does not authorize finalization or mark the candidate
  improved.

### Post-Local Residual Strategy Synthesis

Commit:

- `7fbe0b7 Add post-local residual strategy synthesis`

Implemented:

- Added an autonomous synthesis stage that reviews local residual-target history
  after hostile scaffold, ending-return, object-motion, tactile, and
  proof/no-answer work.
- Consolidated failed local evidence into a strategy packet for the next
  nonlocal direction.
- Preserved boundedness by making the synthesis choose a strategy direction
  rather than creating a target, work order, or generation packet directly.
- Added tests proving finalization remains blocked and no candidate/generation
  path is opened by synthesis alone.

### Strongest-Rival Forensic Diagnosis

Commits:

- `a68f460 Add strongest rival forensic diagnosis`
- `7563839 Normalize strongest rival diagnosis surface contract`

Implemented:

- Added a strongest-rival forensic diagnosis packet path that consumes the
  post-local strategy packet and analyzes why the imported strongest rival
  remains structurally pressuring.
- Added required diagnostic hypotheses and evidence surfaces for rival pressure
  without claiming the rival has been beaten.
- Normalized the public packet surface so downstream consumers receive stable
  fields for packet kind, source packet IDs, diagnosis kind, recommended
  strategy class, and blocker status.
- Kept the diagnosis non-generative: no candidate text, residual target,
  work order, ablation path, or finalization gate is created.

### Local-Law Discovery From Rival Forensics

Commits:

- `da3a6ea Add local law discovery from rival forensics`
- `fd2faba Normalize local law discovery surface contract`

Implemented:

- Added local-law discovery from strongest-rival forensic diagnosis.
- Discovered and recorded the current law:
  `first_read_pressure_precedes_explanation_law`.
- Added local-law artifacts that describe the law, its evidence basis, limits,
  and downstream strategy implications.
- Normalized the local-law packet surface so downstream commands can reliably
  consume:
  - `law_id`
  - source diagnosis packet references
  - current best/proof/reader-state packet IDs
  - direct-rival availability flags
  - recommended next strategy class
- Preserved non-generative boundaries and fail-closed finalization.

### Direct Rival Subject Materialization

Commit:

- `acd1b61 Add direct rival subject materialization`

Implemented:

- Added a direct-rival subject materialization command that consumes the
  local-law discovery packet and resolves the strongest-rival text into an
  explicit materialized subject for comparison.
- Registered the materialized rival subject, provenance/hash report,
  limitations report, non-imitation report, readiness report, scope guard, gate
  report, and packet summary.
- Recorded the direct rival text hash:
  `f3f7adef01c4bd24257c3dabfabec9024031c2d82c7f2061f6fc5de36430b06c`
  in the live run.
- Added surface-alias handling so canonical materialized-subject artifacts are
  consumed even when display aliases are absent.
- Preserved non-imitation constraints and kept generation unauthorized.

### Model-Backed Local-Law Rival Diagnostic Scaffold

Commit:

- `69ee216 Add local law rival diagnostic scaffold`

Implemented:

- Added the fake/deterministic scaffold for:
  `abi autonomous diagnose-local-law-with-rival`.
- The command consumes direct-rival subject materialization and compares
  packet `0063` with the materialized direct rival under
  `first_read_pressure_precedes_explanation_law`.
- Added artifacts for:
  - source direct-rival materialization intake
  - current-best subject comparison
  - direct-rival subject comparison
  - law application comparison matrix
  - first-read pressure diagnostic report
  - rival advantage under law report
  - packet `0063` law gap report
  - non-imitation constraint report
  - next strategy readiness report
  - project health scope guard report
  - local-law rival diagnostic gate report
  - packet summary
- Fake mode records `model_calls: 0`, `model_backed: false`, and
  `diagnostic_is_provisional: true`.
- The scaffold remained diagnostic-only: no candidate, no generation
  authorization, no target selection, no work order, no ablation, no
  reader-state evaluation, and no finalization claim.

### Live Model-Backed Local-Law Rival Diagnostic

Commit:

- `0cb8f24 Add live local law rival diagnostic path`

Implemented:

- Added the guarded live OpenAI path for
  `abi autonomous diagnose-local-law-with-rival`.
- Added structured-output schema:
  `ModelBackedLocalLawRivalDiagnosticOutput@1`.
- Added worker role:
  `model_backed_local_law_rival_diagnostic`.
- Added prompt contract:
  `autonomous.local_law_rival_diagnostic.v1`.
- Registered the schema with the OpenAI response-format adapter and strict
  structured-output validation.
- Live mode requires:
  - `--allow-live-model`
  - `OPENAI_API_KEY`
  - `--max-model-calls 1`
  - configured model from `ABI_OPENAI_MODEL` or the documented default
- Stubbed OpenAI tests prove that a valid live response creates exactly one
  model-call record and produces an accepted diagnostic packet with:
  - `client: openai`
  - `model_backed: true`
  - `live_model_diagnostic: true`
  - `model_calls: 1`
  - non-empty `model_call_ids`
- Local validation rejects:
  - wrong `law_id`
  - `generation_allowed: true`
  - `finality_claimed: true`
  - `phase_shift_claimed: true`
  - missing non-imitation acknowledgment
  - candidate/rewrite/target/work-order fields
  - immediate generation recommendations
- Fake mode remains unchanged and still produces `model_calls: 0`.
- OpenAI mode without `--allow-live-model` refuses before any model call.
- The live diagnostic remains non-generative and does not authorize any next
  generation step.

Real packet result:

- Fake verification produced:
  `runs\run_8fa54199f23f3d8e\model_backed_local_law_diagnostic\packet_0003`
- The packet was accepted with:
  - `client: fake`
  - `model_backed: false`
  - `model_calls: 0`
  - `candidate_generated: false`
  - `generation_authorized: false`

Latest verification at this endpoint:

- `ruff check .` passed.
- `pytest` passed with 494 tests.
- Focused model-backed local-law diagnostic tests passed.
- `gate list` succeeded.
- `finalization status --profile autonomous_creative_candidate` remained
  ineligible.
- `finalize --profile autonomous_creative_candidate` refused.
- Guarded OpenAI local-law rival diagnostic without `--allow-live-model`
  refused with `model_calls: 0`.

## Updates Since Live Local-Law Rival Diagnostic

This section records the nonlocal law-guided generation chain built after the
last changelog endpoint. It is the first path in which Abi learned a local law
from strongest-rival pressure, turned that law into strategy and work-order
state, explicitly authorized one generation attempt, and then accepted a live
model-produced candidate under controller validation.

### Live Local-Law Rival Diagnostic Surface Normalization

Commit:

- `d574acb Normalize live local law rival diagnostic reports`

Implemented/fixed:

- Hardened the live model-backed local-law rival diagnostic output surface.
- Normalized report richness for the live diagnostic packet so downstream
  strategy code could rely on the diagnostic fields.
- Preserved the live diagnostic as diagnostic-only:
  - no candidate generation
  - no generation authorization
  - no ablation
  - no reader-state evaluation
  - no finalization claim
- Kept fake/stub/live-guard behavior intact.

### Nonlocal Law-Guided Strategy

Commit:

- `c3695d5 Add nonlocal law-guided strategy`

Implemented:

- Strategy packet construction from the model-backed local-law rival diagnostic.
- Strategy class:
  `consequence_first_nonlocal_recomposition_strategy`
- Law:
  `first_read_pressure_precedes_explanation_law`
- Current-best reference remained:
  `bounded_macro_recomposition/packet_0063`
- Proof reference remained:
  `executed_ablation/packet_0034`
- Reader-state reference remained:
  `internal_reader_state_evaluation/packet_0013`
- Strategy remained planning-only and did not generate a candidate.
- Tests preserved finalization refusal.

### Nonlocal Law-Guided Work-Order Planning

Commits:

- `5cc8eec Add nonlocal law-guided work-order planning`
- `553d83c Fix nonlocal law work-order generation readiness surface`

Implemented/fixed:

- Work-order packet creation for the nonlocal law-guided strategy.
- Target scope:
  `nonlocal_artifact_pressure_distribution`
- Work-order kind:
  `nonlocal_law_guided_work_order`
- Prompt contract:
  `autonomous.nonlocal_law_guided_generation.v1`
- Future schema:
  `NonlocalLawGuidedGenerationOutput@1`
- Materiality policy:
  `nonlocal_law_guided_generation_materiality_v1`
- Semantic validator:
  `nonlocal_law_guided_semantic_validator_v1`
- Target units:
  - `object_event_consequence_before_explanation`
  - `delay_or_embed_explanatory_naming`
  - `packet_0063_objects_undergo_consequence`
  - `middle_sequence_pressure_accumulation`
  - `reread_return_prepared_by_first_read_pressure`
  - `non_imitation_constraint_preservation`
- Added generation-readiness metadata needed for authorization review.
- Superseded incomplete work-order surfaces when generation-readiness metadata
  was missing.
- Kept the work order bounded and non-generative.

### Nonlocal Law-Guided Generation Authorization

Commit:

- `76e1fea Add nonlocal law-guided generation authorization`

Implemented:

- CLI:
  `abi autonomous authorize-nonlocal-law-generation`
- Operator-reviewed authorization record for one bounded nonlocal
  law-guided generation attempt.
- Authorization decision:
  `authorize_one_bounded_nonlocal_law_guided_generation`
- Runtime authorization packet:
  `runs\run_8fa54199f23f3d8e\nonlocal_law_guided_generation_authorization\packet_0001`
- Authorization packet state before live candidate generation:
  - `accepted: true`
  - `generation_authorized: true`
  - `next_generation_authorized: true`
  - `generation_attempt_budget: 1`
  - `authorization_consumed: false`
  - `candidate_generated: false`
  - `model_calls: 0`
- Authorization did not itself create candidate evidence.
- Failed attempts do not consume authorization.
- Accepted candidate generation consumes authorization only after controller
  validation succeeds.

### Nonlocal Law-Guided Candidate Generation

Commits:

- `c4647e3 Add nonlocal law-guided candidate generation`
- `d53213d Tighten nonlocal law generation safety metadata`

Implemented:

- CLI:
  `abi autonomous generate-nonlocal-law-candidate`
- Client modes:
  - `--client fake`
  - `--client openai`
- Guarded OpenAI path requiring:
  - `--allow-live-model`
  - `OPENAI_API_KEY`
  - `--max-model-calls 1`
- Structured-output schema:
  `NonlocalLawGuidedGenerationOutput@1`
- Worker role:
  `nonlocal_law_guided_generator`
- Prompt contract:
  `autonomous.nonlocal_law_guided_generation.v1`
- Accepted candidate packet directory:
  `runs/<run_id>/nonlocal_law_guided_candidate/<packet_id>/`
- Failed validation packet directory:
  `runs/<run_id>/nonlocal_law_guided_candidate_failed_generation/<packet_id>/`
- Accepted packets create and register 15 artifacts:
  - `nonlocal_law_guided_candidate_packet`
  - `source_authorization_intake_summary`
  - `base_candidate_subject`
  - `generated_candidate_text`
  - `candidate_diff_summary`
  - `target_unit_change_report`
  - `materiality_validation_report`
  - `semantic_validation_report`
  - `non_imitation_validation_report`
  - `protected_strengths_preservation_report`
  - `forbidden_regression_report`
  - `post_generation_evidence_plan`
  - `authorization_consumption_report`
  - `nonlocal_law_candidate_gate_report`
  - `project_health_scope_guard_report`
- Controller validation rejects:
  - missing or unchanged `revised_text`
  - forbidden rival material
  - finality, phase-shift, improvement, or strongest-rival-defeat claims
  - law-as-thesis output
  - generic domestic grime as law substitute
  - missing target units
  - failed materiality or semantic self-reports
  - failed non-imitation report
  - unpreserved protected strengths
  - explanation abolished rather than delayed or earned
  - missing packet `0063` object field
  - local patching instead of nonlocal pressure redistribution
  - claims that ablation, reader-state evaluation, synthesis, or finalization
    already happened
- The prompt and schema now clarify that:
  - `generation_allowed` is a downstream safety/escalation field
  - it is not the answer to whether the current call was authorized
  - `generation_allowed` must be `false`
  - `finality_claimed` must be `false`
  - `phase_shift_claimed` must be `false`
  - `strongest_rival_defeated_claimed` must be `false`
- The JSON schema constrains those safety/finality fields to enum `[false]`.
- Failed-generation diagnostics now expose top-level:
  - `failure_class`
  - `failure_reason`
  - `validation_failures`
  - `model_call_status`
  - `diagnostic_message`
  - `model_output_keys`
  - safety/finality fields when recoverable from raw output
- Specific `generation_allowed: true` failures are classified as:
  - `failure_class: nonlocal_law_generation_safety_metadata_failure`
  - `failure_reason: generation_allowed_true_or_not_false`
- Failed packets do not create accepted candidate evidence.
- Failed packets do not consume authorization.
- Guarded OpenAI refusal without `--allow-live-model` still refuses before any
  model call with:
  - `model_calls: 0`
  - `authorization_consumed: false`
  - `candidate_generated: false`

Runtime milestone:

- A guarded live OpenAI command was run by the operator with
  `--allow-live-model --max-model-calls 1`.
- It produced the first accepted live nonlocal law-guided candidate:
  `runs\run_8fa54199f23f3d8e\nonlocal_law_guided_candidate\packet_0002`
- The runtime packet reports:
  - `accepted: true`
  - `candidate_generated: true`
  - `candidate_artifact_created: true`
  - `authorization_consumed: true`
  - `model_calls: 1`
  - `base_candidate_packet_id: packet_0063`
  - `current_best_candidate_packet_id: packet_0063`
  - `proof_packet_id: packet_0034`
  - `reader_state_packet_id: packet_0013`
  - `next_recommended_action: review_nonlocal_law_candidate_before_ablation`
- The accepted packet created all 15 required artifacts.
- Its validation report was clean:
  - `validation_passed: true`
  - `materiality_passed: true`
  - `semantic_passed: true`
  - `non_imitation_passed: true`
  - `protected_strengths_preserved: true`
  - `forbidden_regression_passed: true`
  - `forbidden_rival_hits: []`
  - `missing_target_units: []`
- This completed the first live chain:
  rival pressure -> local law -> direct rival materialization -> live
  model-backed diagnosis -> nonlocal strategy -> bounded work order ->
  explicit authorization -> live law-guided candidate.

Milestone meaning:

- This is the first accepted live candidate produced after Abi learned a law
  from strongest-rival pressure.
- The accepted candidate is reviewable candidate evidence, not a final artifact.
- It does not prove the new candidate is better than `packet_0063`.
- It does not prove the strongest rival has been beaten.
- It does not prove finalization or phase shift.
- The current best remains `packet_0063` until later evidence supports a
  supersession.
- The correct next stage is review, then executed ablation, reader-state
  evaluation, and synthesis before any current-best or finalization decision.

Latest verification at this endpoint:

- `ruff check .` passed.
- `pytest` passed with 564 tests.
- Guarded OpenAI nonlocal-law candidate generation without
  `--allow-live-model` refused with `model_calls: 0`.
- `gate list` succeeded.
- `finalization status --profile autonomous_creative_candidate` remained
  ineligible.
- `finalize --profile autonomous_creative_candidate` refused.

## Updates Since Nonlocal Law-Guided Candidate Generation

This section records the work after the first accepted live nonlocal
law-guided candidate. The work extends that candidate from accepted generation
evidence into ablation, model-backed reader-state evidence, and deterministic
evidence synthesis. It reaches the first true loop-closure threshold: Abi used
strongest-rival pressure to discover a law, generated under that law, evaluated
what the generation caused, preserved active risks, refused finality, and
synthesized the evidence without turning the result into an automatic current
best or final artifact.

### Nonlocal Law Candidate Ablation

Commit:

- `03f0178 Add nonlocal law candidate ablation`

Implemented:

- CLI:
  `abi autonomous ablate-nonlocal-law-candidate`
- Deterministic ablation packet for the accepted nonlocal law-guided candidate.
- Runtime ablation packet:
  `runs\run_8fa54199f23f3d8e\nonlocal_law_candidate_ablation\packet_0001`
- Source candidate:
  `runs\run_8fa54199f23f3d8e\nonlocal_law_guided_candidate\packet_0002`
- Base/current best remained:
  `bounded_macro_recomposition/packet_0063`
- Proof reference remained:
  `executed_ablation/packet_0034`
- Prior reader-state reference remained:
  `internal_reader_state_evaluation/packet_0013`
- The ablation packet records:
  - `accepted: true`
  - `ablation_executed: true`
  - `source_candidate_packet_id: packet_0002`
  - `candidate_text_extracted_from: generated_candidate_text.payload.text`
  - `candidate_text_sha256:
    a760e5fee3cd3069232702d49d27b1518bdc52ca5116abd601684719fd00ca0f`
  - `candidate_word_count: 1080`
  - `ablation_control_count: 7`
  - `law_bearing_choice_count: 9`
  - `candidate_review_risk_count: 4`
  - `ready_for_reader_state_evaluation: true`
  - `reader_state_evaluation_authorized: false`
  - `synthesis_authorized: false`
  - `candidate_generated: false`
  - `model_calls: 0`
- Ablation controls created for:
  - full nonlocal law-guided intervention
  - revert to packet `0063`
  - remove consequence-first sequence
  - restore early explanation timing
  - rival imitation control
  - generic vividness control
  - strongest-rival comparison
- Law-bearing choices were mapped across the opening sequence, object-event
  pressure, delayed explanation, later return, and no-reset/no-outside-answer
  pressure.
- Active risks preserved for later evidence:
  - explanation may still arrive too explicitly after initial pressure
  - event sequence may remain too static or retrospective
  - `"Chemistry gives thought a place to search"` may be a register-risk span
  - conclusion may still summarize law instead of fully enacting return
- The ablation path does not generate text, authorize generation, run
  reader-state evaluation, run synthesis, update current best, or finalize.

### Nonlocal Law Candidate Reader-State Evaluation

Commits:

- `648f5a9 Add nonlocal law candidate reader-state evaluation`
- `aee502e Allow live reader-state evaluation after fake evaluation`

Implemented:

- CLI:
  `abi autonomous evaluate-nonlocal-law-candidate-reader-state`
- Fake mode:
  `--client fake`
- Guarded OpenAI mode:
  `--client openai --allow-live-model --max-model-calls 1`
- Structured-output schema:
  `NonlocalLawCandidateReaderStateEvaluationOutput@1`
- Worker role:
  `nonlocal_law_candidate_reader_state_evaluator`
- Prompt contract:
  `autonomous.nonlocal_law_candidate_reader_state_evaluation.v1`
- Accepted packet directory:
  `runs/<run_id>/nonlocal_law_candidate_reader_state_evaluation/<packet_id>/`
- Failed validation packet directory:
  `runs/<run_id>/nonlocal_law_candidate_reader_state_failed_evaluation/<packet_id>/`
- Accepted packets create and register 16 artifacts:
  - `nonlocal_law_candidate_reader_state_evaluation_packet`
  - `source_ablation_intake_summary`
  - `candidate_reader_state_subject`
  - `base_candidate_reader_state_subject`
  - `ablation_control_reader_state_matrix`
  - `first_pass_pressure_before_explanation_report`
  - `object_event_consequence_reader_state_report`
  - `explanation_earned_not_abolished_report`
  - `reread_return_preparation_report`
  - `non_imitation_reader_signal_report`
  - `candidate_review_risk_probe_report`
  - `candidate_vs_packet_0063_reader_state_comparison`
  - `strongest_rival_pressure_status_report`
  - `synthesis_readiness_report`
  - `nonlocal_law_reader_state_gate_report`
  - `project_health_scope_guard_report`
- Evaluation dimensions:
  - first-read pressure before explanation
  - object-event consequence before naming
  - explanation earned rather than abolished
  - reread return preparation
  - non-imitation reader signal
  - active risk probes
  - strongest-rival pressure
- The loader tolerates the known base-subject hash gap only when the source
  chain is coherent and the base/current-best packet resolves to `packet_0063`.
  It records:
  - `base_subject_hash_missing: true`
  - `base_subject_resolved_from_packet_id: packet_0063`
  - `consumed_base_candidate_packet_successfully: true`
- Fake reader-state evaluations are now explicitly provisional:
  - `model_backed: false`
  - `reader_state_evaluation_mode: deterministic_fake_verification`
  - `provisional_reader_state_evaluation: true`
  - `usable_for_command_verification: true`
  - `usable_for_synthesis: false`
  - `ready_for_live_reader_state_evaluation: true`
  - `ready_for_synthesis: false`
- Live/model-backed evaluations are synthesis-grade but still non-final:
  - `model_backed: true`
  - `reader_state_evaluation_mode: model_backed_live`
  - `provisional_reader_state_evaluation: false`
  - `usable_for_synthesis: true`
  - `ready_for_synthesis: true`
  - `synthesis_authorized: false`
- Live-after-fake handling:
  - an accepted fake/provisional evaluation no longer blocks the guarded OpenAI
    path
  - the model-backed packet records which fake packet it supersedes
  - duplicate model-backed evaluations for the same ablation packet refuse
  - fake evaluation after any accepted evaluation refuses
- Guarded OpenAI without `--allow-live-model` still refuses before any model
  call with `model_calls: 0`.
- Validation failure creates failed diagnostic packets and no accepted
  reader-state evidence.

Runtime milestone:

- Fake verification produced:
  `runs\run_8fa54199f23f3d8e\nonlocal_law_candidate_reader_state_evaluation\packet_0001`
- The live model-backed reader-state evaluation superseded that fake packet and
  produced:
  `runs\run_8fa54199f23f3d8e\nonlocal_law_candidate_reader_state_evaluation\packet_0002`
- The live packet reports:
  - `accepted: true`
  - `client: openai`
  - `model_backed: true`
  - `reader_state_evaluation_mode: model_backed_live`
  - `provisional_reader_state_evaluation: false`
  - `usable_for_synthesis: true`
  - `model_calls: 1`
  - `source_ablation_packet_id: packet_0001`
  - `source_candidate_packet_id: packet_0002`
  - `base_candidate_packet_id: packet_0063`
  - `current_best_candidate_packet_id: packet_0063`
  - `proof_packet_id: packet_0034`
  - `prior_reader_state_packet_id: packet_0013`
  - `law_id: first_read_pressure_precedes_explanation_law`
  - `superseded_reader_state_evaluation_packet_id: packet_0001`
  - `supersession_reason:
    model_backed_reader_state_evaluation_supersedes_fake_evaluation`
- The live reader-state result was supportive but mixed:
  - `first_read_pressure_result: improved`
  - `object_event_consequence_result: improved`
  - `explanation_timing_result: improved`
  - `reread_return_result: improved`
  - `non_imitation_result: passed`
  - `strongest_rival_pressure_result: narrowed_but_blocking`
  - `overall_reader_state_result: mixed_requires_synthesis`
- The live packet did not claim:
  - candidate superiority
  - current-best supersession
  - strongest-rival defeat
  - finality
  - phase shift

### Nonlocal Law Candidate Evidence Synthesis

Active working-tree implementation at this changelog update:

- `src/abi/modules/nonlocal_law_candidate_evidence_synthesis.py`
- `src/abi/cli.py`
- `src/abi/controller/state.py`
- `tests/test_autonomous_revision.py`

Implemented:

- CLI:
  `abi autonomous synthesize-nonlocal-law-candidate-evidence`
- Deterministic synthesis command consuming only a model-backed, synthesis-usable
  nonlocal law candidate reader-state packet.
- Source packet:
  `runs\run_8fa54199f23f3d8e\nonlocal_law_candidate_reader_state_evaluation\packet_0002`
- Runtime synthesis packet:
  `runs\run_8fa54199f23f3d8e\nonlocal_law_candidate_evidence_synthesis\packet_0001`
- Accepted synthesis packets create and register 12 artifacts:
  - `nonlocal_law_candidate_evidence_synthesis_packet`
  - `source_reader_state_intake_summary`
  - `evidence_chain_integrity_report`
  - `candidate_law_effect_synthesis`
  - `packet_0063_comparison_synthesis`
  - `ablation_reader_state_alignment_report`
  - `active_risk_synthesis_report`
  - `strongest_rival_pressure_synthesis`
  - `current_best_decision_recommendation`
  - `future_repair_or_supersession_options`
  - `synthesis_gate_report`
  - `project_health_scope_guard_report`
- Intake validation refuses:
  - missing `--operator-reviewed`
  - fake/provisional reader-state packets
  - non-model-backed reader-state packets
  - reader-state packets not usable for synthesis
  - packets where reader-state evaluation did not execute
  - packets not ready for synthesis
  - packets with `synthesis_authorized: true`
  - packets with `current_best_updated: true`
  - wrong source candidate/current best/proof/prior reader-state/law IDs
  - missing required reader-state result fields
  - finality, phase-shift, current-best supersession, candidate superiority,
    or strongest-rival-defeat claim leakage
- The accepted synthesis packet reports:
  - `accepted: true`
  - `synthesis_executed: true`
  - `source_reader_state_packet_id: packet_0002`
  - `source_ablation_packet_id: packet_0001`
  - `source_candidate_packet_id: packet_0002`
  - `base_candidate_packet_id: packet_0063`
  - `prior_current_best_candidate_packet_id: packet_0063`
  - `proof_packet_id: packet_0034`
  - `prior_reader_state_packet_id: packet_0013`
  - `law_id: first_read_pressure_precedes_explanation_law`
  - `candidate_text_sha256:
    a760e5fee3cd3069232702d49d27b1518bdc52ca5116abd601684719fd00ca0f`
  - `candidate_law_effect: supported_but_incomplete`
  - `reader_state_support: supportive_mixed`
  - `strongest_rival_status: narrowed_but_blocking`
  - `current_best_decision: do_not_finalize`
  - `current_best_update_recommendation:
    recommend_promote_to_new_current_best_pending_loop_review`
  - `candidate_generated: false`
  - `generation_authorized: false`
  - `ablation_executed: false`
  - `reader_state_evaluation_executed: false`
  - `model_calls: 0`
  - `current_best_updated: false`
  - `finalization_eligible: false`
  - `no_final_claim: true`
  - `no_phase_shift_claim: true`
  - `strongest_rival_defeated_claimed: false`
- The synthesis records supportive evidence:
  - first-read pressure improved
  - object-event consequence improved
  - explanation timing improved
  - reread return improved
  - non-imitation passed
  - the reader-state evidence is model-backed
  - the ablation packet identified coherent law-bearing choices
- The synthesis preserves blocking evidence:
  - strongest-rival pressure is narrowed but still blocking
  - overall reader-state result remains mixed and requires synthesis/loop review
  - active risks remain
  - no external or human validation is claimed
  - current best is not updated
  - finalization remains refused
- The synthesis gate report passes:
  - operator reviewed
  - source reader-state accepted
  - source reader-state model-backed
  - source reader-state usable for synthesis
  - candidate evidence chain coherent
  - reader-state results present
  - no candidate generated
  - no generation authorized
  - no model calls
  - no current-best update
  - no final claim
  - no phase-shift claim
- The synthesis gate report blocks:
  - `current_best_updated`
  - `strongest_rival_pressure_resolved`
  - `finalization_eligible`

Latest verification after this work:

- `ruff check .` passed.
- `pytest` passed with 617 tests.
- The real deterministic synthesis command accepted and created
  `nonlocal_law_candidate_evidence_synthesis/packet_0001`.
- `gate list` succeeded.
- `finalization status --profile autonomous_creative_candidate` remained
  ineligible.
- `finalize --profile autonomous_creative_candidate` refused.

### Strategic Summary At Loop-Closure Threshold

Abi has now completed its first full law-guided creative repair cycle through
evidence synthesis:

1. strongest-rival pressure
2. local law discovery
3. direct rival materialization
4. live model-backed law/rival diagnostic
5. nonlocal strategy
6. corrected work order
7. explicit generation authorization
8. accepted live candidate
9. ablation packet
10. live model-backed reader-state evaluation
11. deterministic evidence synthesis

The important result is not that the artifact is final or that the candidate is
proven better in an absolute sense. The important result is architectural: Abi
used evidence to discover a local law, generated under that law, evaluated the
reader-state consequences of that generation, preserved residual risks, kept
strongest-rival pressure active, refused finality, and synthesized the evidence
without collapsing into free generation or premature celebration.

The current tactical state is:

- current best remains `bounded_macro_recomposition/packet_0063`
- new candidate is `nonlocal_law_guided_candidate/packet_0002`
- candidate status is accepted, validated, model-backed, and synthesis-supported
  but incomplete
- ablation is complete as a structured packet
- live model-backed reader-state evaluation is complete
- evidence synthesis is complete
- current-best update has not happened
- finalization remains refused
- next required step is loop review / current-best decision

The current strategic state is:

- the evidence supports `packet_0002` as a possible new current best
- the evidence does not support finalization
- strongest-rival pressure remains active and blocking
- active risks should guide the next loop if `packet_0002` is promoted
- Abi has reached a real loop-closure threshold, but not a final-artifact
  threshold

## Current Runtime Surface

The current repo includes these active areas:

- `abi init`
- `abi status`
- `abi artifact list/show`
- `abi run list/show/latest`
- `abi gate list`
- `abi finalization status`
- `abi finalize`
- deterministic `abi ear demo`
- deterministic `abi reread demo`
- production harness demo
- pilot artifact-set generation
- strongest-rival import
- internal reader-lab
- autonomous closed-loop revision
- executed ablation
- ablation-informed revision
- autonomous evidence synthesis
- loop-level evidence review
- bounded macro recomposition
- internal reader-state evaluation
- object-event pressure recomposition
- supervised next-cycle authorization
- authorization-aware next-target planning
- narrow residual target selection
- target-aware residual work-order planning
- supervised residual generation authorization
- one-shot target-aware residual candidate generation
- residual target adapters for object-motion causality and tactile
  inevitability gaps
- hostile scaffold residual-target planning, validation feedback, and failed
  generation adjudication
- ending-return residual-target planning, generation handoff, validation
  feedback, and failed generation adjudication
- architecture/evidence-risk checkpointing and checkpoint-aware strategy
  routing
- generic target artifact aliases and target-adapter contract audit
- checkpoint direction review for sensitive residual target selection
- proof-no-answer residual-target planning, generation handoff, authorization,
  and evidence handoff metadata validation
- proof-no-answer generation feedback, failed-generation adjudication, and
  checkpoint failed-target memory
- post-local residual strategy synthesis
- strongest-rival forensic diagnosis
- local-law discovery from rival forensics
- direct rival subject materialization
- model-backed local-law rival diagnostic in fake and guarded live modes
- nonlocal law-guided strategy planning
- nonlocal law-guided work-order planning
- nonlocal law-guided generation authorization
- nonlocal law-guided candidate generation in fake and guarded live modes
- nonlocal law candidate ablation
- nonlocal law candidate reader-state evaluation in fake and guarded live modes
- nonlocal law candidate evidence synthesis
- target-aware executed ablation controls and comparator consistency checks
- model-driver demos and model-call inspection
- guarded live paths behind explicit opt-in

The codebase is organized around:

- `src/abi/controller/` for decisions, gates, policies, and finalization.
- `src/abi/modules/` for packet-producing pipelines.
- `src/abi/model_driver.py`, `model_schemas.py`, `model_calls.py`, and
  `openai_adapter.py` for sealed structured model-call infrastructure.
- `src/abi/packets.py` and `src/abi/artifacts.py` for artifact envelopes and
  registry integration.
- `tests/` for regression coverage.
- `context/` for frozen phase specs and historical context.
- `docs/` for operator-facing handoff and protocol documents.

## Current Finalization Position

The active internal profile is:

- `autonomous_creative_candidate`

It remains fail-closed. Current blockers include unresolved internal blockers
and missing internal operator approval.

The legacy external profile is:

- `final_artifact`

It remains in the repo as a stricter external/public validation profile, but it
is not the active development path after core autonomous realignment.

## What Has Not Been Done

Across the session, these boundaries remained intact:

- No unguarded automatic OpenAI calls.
- No test requiring an API key.
- No final artifact generation claim.
- No final gates falsely marked passed.
- No phase-shift claim.
- No real human validation collection.
- No restoration of human/paper/public validation as the active path.
- No dashboard.
- No agent-loop framework.
- No `SKILL.md`.
