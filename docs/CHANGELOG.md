# Abi Changelog

This changelog summarizes the work performed in this repository from the initial
"Phase 0 of Project Abi is frozen" implementation request through the current
state of the repo.

It is written as an operator-facing engineering history. It records what was
built, what was intentionally kept out of scope, and which invariants have been
preserved across the build.

Current endpoint in Git history:

- `544e967 Allow executed ablation of ablation-informed revision packets`
- Active branch during latest changelog update:
  `fix/revise-from-ablation-source-packet-adapter`
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
