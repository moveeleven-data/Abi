"""Generate one selected-target cycle mechanism-visibility candidate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import get_run, set_active_phase
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_calls import MODEL_CALL_VALIDATION_FAILED, link_model_call_parsed_artifact
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    ModelValidationError,
    SELECTED_TARGET_CYCLE_MECHANISM_VISIBILITY_GENERATION_SCHEMA,
    WorkerRole,
)
from abi.modules.nonlocal_law_selected_target_cycle_generation_authorization import (
    ARTIFACT_TYPES as AUTHORIZATION_ARTIFACT_TYPES,
    AUTHORIZATION_DECISION_AUTHORIZE_ONE_CYCLE,
    MATERIAL_GENERATION_UNIT_IDS,
    PRESERVATION_OR_GUARD_UNIT_IDS,
)
from abi.modules.nonlocal_law_selected_target_cycle_work_order import (
    ABLATION_CONTROLS,
    MATERIALITY_REQUIREMENTS,
    PHRASE_INVENTORY,
    PHRASE_INVENTORY_POLICY,
    READER_STATE_FOCUS,
    SELECTED_RISK_ID,
    SELECTED_TARGET_CLASS,
    SELECTED_TARGET_SEED_ID,
    SEMANTIC_REQUIREMENTS,
    TARGET_UNIT_IDS,
    WORK_ORDER_SCOPE,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


LINEAGE_ID = "nonlocal_law_selected_target_cycle_candidate_generation_v1"
CREATED_BY = "nonlocal_law_selected_target_cycle_candidate_generation_v1_controller"
ACTIVE_PHASE = "nonlocal_law_selected_target_cycle_candidate_generation_v1"
CLIENTS = ("fake", "openai")
REQUIRED_MODEL_CALLS = 1
MAX_MODEL_CALLS_DEFAULT = 1
PROMPT_CONTRACT_ID = "autonomous.selected_target_cycle_mechanism_visibility_generation.v1"
SCHEMA_NAME = "SelectedTargetCycleMechanismVisibilityGenerationOutput@1"
NEXT_RECOMMENDED_ACTION = "review_selected_target_cycle_candidate_before_ablation"
FAILED_NEXT_RECOMMENDED_ACTION = "review_failed_selected_target_cycle_generation"

ARTIFACT_TYPES = (
    "nonlocal_law_selected_target_cycle_candidate_packet",
    "source_cycle_authorization_intake_summary",
    "base_working_current_best_subject",
    "generated_candidate_text",
    "mechanism_visibility_candidate_diff_summary",
    "phrase_handling_report",
    "target_unit_change_report",
    "materiality_validation_report",
    "semantic_validation_report",
    "protected_living_event_gain_preservation_report",
    "forbidden_overcorrection_regression_report",
    "non_imitation_validation_report",
    "authorization_consumption_report",
    "post_generation_evidence_plan",
    "selected_target_cycle_candidate_gate_report",
    "project_health_scope_guard_report",
)
FAILED_ARTIFACT_TYPES = (
    "failed_generation_diagnostic",
    "failed_generation_gate_report",
    "nonlocal_law_selected_target_cycle_failed_generation_packet",
)
REQUIRED_AUTHORIZATION_ARTIFACTS = AUTHORIZATION_ARTIFACT_TYPES

FORBIDDEN_RIVAL_TERMS = (
    "cup",
    "windowsill",
    "bill",
    "shoes",
    "drag-mark",
    "scar",
    "sink",
    "payment",
    "shade",
)
CLAIM_LEAKAGE_TERMS = (
    "final artifact",
    "finalization",
    "phase shift",
    "phase-shift",
    "strongest rival defeated",
    "defeats the strongest rival",
    "beats the rival",
    "current best is updated",
    "supersedes the current best",
)
BASE_OBJECT_TERMS = ("table", "ring", "dust", "spoon", "saucer")


@dataclass(frozen=True)
class SelectedTargetCycleCandidateGenerationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class SelectedTargetCycleCandidateSubject:
    run_id: str
    authorization_packet_dir: Path
    authorization_packet_id: str
    authorization_packet_artifact_id: str | None
    authorization_payloads: dict[str, dict[str, Any]]
    authorization_artifact_ids: dict[str, str]
    source_parent_ids: tuple[str, ...]
    work_order_packet_id: str
    target_selection_packet_id: str
    source_consolidation_packet_id: str
    source_loop_review_packet_id: str
    source_synthesis_packet_id: str
    source_reader_state_packet_id: str
    source_candidate_packet_id: str
    current_best_for_next_loop_packet_id: str
    prior_working_current_best_candidate_packet_id: str
    prior_historical_current_best_candidate_packet_id: str
    base_candidate_packet_dir: Path
    base_candidate_artifact_id: str | None
    base_text: str
    base_text_sha256: str


class SelectedTargetCycleCandidateValidationError(ModelValidationError):
    def __init__(self, validation_report: dict[str, object]) -> None:
        self.validation_report = validation_report
        failures = validation_report.get("validation_failures")
        message = (
            "; ".join(str(item) for item in failures)
            if isinstance(failures, list)
            else "validation failed"
        )
        super().__init__(message)


class FakeSelectedTargetCycleMechanismVisibilityGenerationModelClient:
    provider = "fake"
    model = "fake-selected-target-cycle-mechanism-visibility-v1"

    def __init__(
        self,
        mode: str = "valid",
        *,
        provider: str = "fake",
        model: str = "fake-selected-target-cycle-mechanism-visibility-v1",
    ) -> None:
        self.mode = mode
        self.provider = provider
        self.model = model

    def generate(self, request: WorkerRequest) -> str:
        prompt = json.loads(request.input_text)
        payload = _valid_fake_payload(prompt)
        if self.mode == "missing_phrase_report":
            payload.pop("phrase_handling_report", None)
        elif self.mode == "short_phrase_report":
            payload["phrase_handling_report"] = payload["phrase_handling_report"][:-1]
        elif self.mode == "unknown_phrase":
            payload["phrase_handling_report"][0]["phrase"] = "unknown mechanism phrase"
        elif self.mode == "deletion_required":
            payload["phrase_handling_report"][0]["deletion_required"] = True
        elif self.mode == "deletion_list":
            payload["phrase_handling_report"][0][
                "pressure_point_not_deletion_target"
            ] = False
        elif self.mode == "causal_force_lost":
            payload["phrase_handling_report"][0]["causal_force_preserved"] = False
        elif self.mode == "living_sequence_weakened":
            payload["phrase_handling_report"][0][
                "living_event_sequence_weakened"
            ] = True
        elif self.mode == "generation_allowed":
            payload["generation_allowed"] = True
        elif self.mode == "finality":
            payload["finality_claimed"] = True
        elif self.mode == "phase_shift":
            payload["phase_shift_claimed"] = True
        elif self.mode == "rival_defeat":
            payload["strongest_rival_defeated_claimed"] = True
        elif self.mode == "invalid_json":
            return "{not valid json"
        return _canonical_json(payload)


def run_selected_target_cycle_candidate_generation(
    config: AbiConfig,
    *,
    client_name: str,
    authorization_packet: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> SelectedTargetCycleCandidateGenerationResult:
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name not in CLIENTS:
        return _refusal(
            message=f"Unsupported selected-target cycle candidate client: {client_name}",
            authorization_packet=authorization_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )
    initialize_database(config)
    resolved_packet = _resolve_path(config, authorization_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            message=(
                "Selected-target cycle candidate generation refused; "
                f"authorization packet directory not found: {resolved_packet}"
            ),
            authorization_packet=resolved_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )
    if client_name == "openai":
        if not allow_live_model:
            return _refusal(
                message=(
                    "Selected-target cycle candidate OpenAI path refused; pass "
                    "--allow-live-model to opt in explicitly."
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model,
            )
        resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        if not resolved_api_key:
            return _refusal(
                message=(
                    "Selected-target cycle candidate OpenAI path refused; "
                    f"{OPENAI_API_KEY_ENV} is not set."
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model,
            )
        if max_model_calls != REQUIRED_MODEL_CALLS:
            return _refusal(
                message=(
                    "Selected-target cycle candidate OpenAI path refused; "
                    "max-model-calls must be exactly 1."
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model,
            )

    with connect(config.db_path) as connection:
        try:
            subject = _load_subject(connection, config, resolved_packet)
            _validate_subject_before_generation(connection, subject)
        except (
            KeyError,
            TypeError,
            ValueError,
            FileNotFoundError,
            json.JSONDecodeError,
        ) as error:
            return _refusal(
                message=(
                    "Selected-target cycle candidate generation refused; "
                    f"{error}"
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Selected-target cycle candidate generation refused; run is "
                    f"not registered: {subject.run_id}"
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )
        set_active_phase(connection, subject.run_id, ACTIVE_PHASE)

    fixture_only = client_name == "fake"
    model_results: list[ModelDriverResult] = []
    model_call_id: str | None = None
    packet_dir: Path | None = None
    if client_name == "fake":
        model_payload = _valid_fake_payload(_prompt_packet(subject))
    else:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_cycle_candidate"
        )
        factory = client_factory or _default_openai_client_factory
        model_result = _run_live_generation_model(
            config=config,
            subject=subject,
            packet_dir=packet_dir,
            model_client=factory(configured_model),
            parent_ids=list(subject.source_parent_ids),
        )
        model_results.append(model_result)
        if not model_result.accepted or model_result.parsed_payload is None:
            return _failure_result(
                config=config,
                subject=subject,
                client_name=client_name,
                model=configured_model,
                model_results=model_results,
                message=_model_failure_message(model_result),
                validation_report=_validation_report_for_model_failure(model_result),
            )
        model_payload = model_result.parsed_payload
        model_call_id = model_result.model_call.id

    try:
        validation_report = _validate_generated_payload(subject, model_payload)
    except SelectedTargetCycleCandidateValidationError as error:
        return _failure_result(
            config=config,
            subject=subject,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_results=model_results,
            message=(
                "Selected-target cycle candidate generation refused; "
                f"{error}"
            ),
            validation_report=error.validation_report,
        )

    if packet_dir is None:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_cycle_candidate"
        )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=LINEAGE_ID,
            created_by=CREATED_BY,
            fixture_only=fixture_only,
            model_call_id=None,
        )
        model_writer = (
            PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=packet_dir,
                lineage_id=LINEAGE_ID,
                created_by=f"model_driver:openai:{configured_model}",
                fixture_only=False,
                model_call_id=model_call_id,
            )
            if model_call_id
            else None
        )
        payloads, artifacts = _write_candidate_artifacts(
            writer=writer,
            model_writer=model_writer,
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_payload=model_payload,
            validation_report=validation_report,
            model_results=model_results,
        )
        if model_results:
            linked_call = link_model_call_parsed_artifact(
                connection,
                model_call_id=model_results[-1].model_call.id,
                parsed_output_artifact_id=artifacts["generated_candidate_text"].id,
            )
            model_results[-1] = ModelDriverResult(
                model_call=linked_call,
                parsed_payload=model_results[-1].parsed_payload,
                parsed_artifact=artifacts["generated_candidate_text"],
            )
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="selected_target_cycle_candidate_gate_report",
            passed=False,
            blocking_defects=list(
                payloads["selected_target_cycle_candidate_gate_report"][
                    "unresolved_blockers"
                ]
            ),
            lineage_id=LINEAGE_ID,
        )

    return SelectedTargetCycleCandidateGenerationResult(
        exit_code=0,
        payload=_result_payload(
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
        ),
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
        model_results=tuple(model_results),
    )


def _load_subject(
    connection: sqlite3.Connection,
    config: AbiConfig,
    authorization_packet_dir: Path,
) -> SelectedTargetCycleCandidateSubject:
    auth_envelopes, auth_payloads = _load_required_payloads(
        authorization_packet_dir,
        REQUIRED_AUTHORIZATION_ARTIFACTS,
        "authorization packet",
    )
    auth_packet = auth_payloads[
        "nonlocal_law_selected_target_cycle_generation_authorization_packet"
    ]
    run_id = str(
        auth_packet.get("run_id")
        or auth_envelopes[
            "nonlocal_law_selected_target_cycle_generation_authorization_packet"
        ].get("run_id")
        or ""
    )
    if not run_id:
        raise ValueError("authorization packet missing run_id")
    base_packet_id = str(auth_packet.get("current_best_for_next_loop_packet_id") or "")
    base_packet_dir = (
        config.run_dir(run_id) / "nonlocal_law_selected_target_candidate" / base_packet_id
    )
    base_payload, base_artifact_id = _load_base_candidate_payload(
        connection,
        base_packet_dir,
    )
    base_text = str(base_payload.get("text") or "")
    if not base_text.strip():
        raise ValueError("base current-best text is empty")
    auth_packet_artifact = _artifact_for_path(
        connection,
        authorization_packet_dir
        / "nonlocal_law_selected_target_cycle_generation_authorization_packet.json",
    )
    auth_artifact_ids = _artifact_ids_from_packet(auth_packet)
    parent_ids = _unique(
        [
            auth_packet_artifact.id if auth_packet_artifact else None,
            base_artifact_id,
            *auth_artifact_ids.values(),
        ]
    )
    return SelectedTargetCycleCandidateSubject(
        run_id=run_id,
        authorization_packet_dir=authorization_packet_dir,
        authorization_packet_id=str(
            auth_packet.get("packet_id") or authorization_packet_dir.name
        ),
        authorization_packet_artifact_id=(
            auth_packet_artifact.id if auth_packet_artifact else None
        ),
        authorization_payloads=auth_payloads,
        authorization_artifact_ids=auth_artifact_ids,
        source_parent_ids=tuple(parent_ids),
        work_order_packet_id=str(auth_packet.get("source_work_order_packet_id") or ""),
        target_selection_packet_id=str(
            auth_packet.get("source_target_selection_packet_id") or ""
        ),
        source_consolidation_packet_id=str(
            auth_packet.get("source_consolidation_packet_id") or ""
        ),
        source_loop_review_packet_id=str(
            auth_packet.get("source_loop_review_packet_id") or ""
        ),
        source_synthesis_packet_id=str(
            auth_packet.get("source_synthesis_packet_id") or ""
        ),
        source_reader_state_packet_id=str(
            auth_packet.get("source_reader_state_packet_id") or ""
        ),
        source_candidate_packet_id=str(auth_packet.get("source_candidate_packet_id") or ""),
        current_best_for_next_loop_packet_id=base_packet_id,
        prior_working_current_best_candidate_packet_id=str(
            auth_packet.get("prior_working_current_best_candidate_packet_id") or ""
        ),
        prior_historical_current_best_candidate_packet_id=str(
            auth_packet.get("prior_historical_current_best_candidate_packet_id") or ""
        ),
        base_candidate_packet_dir=base_packet_dir,
        base_candidate_artifact_id=base_artifact_id,
        base_text=base_text,
        base_text_sha256=str(base_payload.get("text_sha256") or sha256_text(base_text)),
    )


def _validate_subject_before_generation(
    connection: sqlite3.Connection,
    subject: SelectedTargetCycleCandidateSubject,
) -> None:
    auth = subject.authorization_payloads[
        "nonlocal_law_selected_target_cycle_generation_authorization_packet"
    ]
    phrase_policy = subject.authorization_payloads["phrase_handling_authorization_policy"]
    budget = subject.authorization_payloads["model_call_budget_report"]
    lock = subject.authorization_payloads["generation_lock_transition_report"]
    _require_bool(auth, "accepted", True)
    _require_equal(auth, "decision", AUTHORIZATION_DECISION_AUTHORIZE_ONE_CYCLE)
    _require_bool(auth, "generation_authorized", True)
    _require_bool(auth, "next_generation_authorized", True)
    _require_equal(auth, "generation_attempt_budget", 1)
    _require_bool(auth, "authorization_consumed", False)
    _require_bool(auth, "candidate_generated", False)
    _require_equal(auth, "model_calls", 0)
    _require_equal(auth, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(auth, "selected_risk_id", SELECTED_RISK_ID)
    _require_equal(auth, "selected_target_class", SELECTED_TARGET_CLASS)
    _require_equal(auth, "work_order_scope", WORK_ORDER_SCOPE)
    _require_equal(auth, "phrase_inventory_policy", PHRASE_INVENTORY_POLICY)
    _require_bool(auth, "phrase_inventory_not_deletion_list", True)
    _require_bool(auth, "phrase_handling_report_required", True)
    _require_bool(auth, "generation_schema_requires_phrase_handling_report", True)
    _require_bool(auth, "finalization_eligible", False)
    _require_bool(auth, "no_final_claim", True)
    _require_bool(auth, "no_phase_shift_claim", True)
    _require_bool(auth, "strongest_rival_defeated_claimed", False)
    _require_equal(budget, "remaining_model_calls", 1)
    _require_equal(budget, "model_call_budget", 1)
    _require_bool(lock, "authorization_packet_does_not_run_generation", True)
    _require_bool(phrase_policy, "phrase_inventory_not_deletion_list", True)
    _require_bool(phrase_policy, "phrase_handling_report_required", True)
    _require_equal(phrase_policy, "phrase_inventory_count", len(PHRASE_INVENTORY))
    if _linked_candidate_for_authorization(connection, subject) is not None:
        raise ValueError("existing accepted candidate already consumed this authorization")
    if _has_final_or_phase_claim(subject.authorization_payloads):
        raise ValueError("authorization carries finality or phase-shift claim")


def _run_live_generation_model(
    *,
    config: AbiConfig,
    subject: SelectedTargetCycleCandidateSubject,
    packet_dir: Path,
    model_client: ModelClient,
    parent_ids: list[str],
) -> ModelDriverResult:
    return ModelDriver(config=config, client=model_client).run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.SELECTED_TARGET_CYCLE_MECHANISM_VISIBILITY_GENERATOR,
            prompt_contract_id=PROMPT_CONTRACT_ID,
            schema=SELECTED_TARGET_CYCLE_MECHANISM_VISIBILITY_GENERATION_SCHEMA,
            input_text=_canonical_json(_prompt_packet(subject)),
            input_artifact_ids=parent_ids,
            input_packet_path=str(subject.authorization_packet_dir),
            lineage_id=LINEAGE_ID,
            parent_ids=parent_ids,
            fixture_only=False,
            output_dir=str(packet_dir),
            register_parsed_artifact=False,
        )
    )


def _prompt_packet(subject: SelectedTargetCycleCandidateSubject) -> dict[str, object]:
    phrase_policy = subject.authorization_payloads["phrase_handling_authorization_policy"]
    return {
        "task": "generate one bounded selected-target cycle mechanism-visibility candidate",
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": SCHEMA_NAME,
        "authorization_packet_id": subject.authorization_packet_id,
        "work_order_packet_id": subject.work_order_packet_id,
        "source_target_selection_packet_id": subject.target_selection_packet_id,
        "base_current_best_packet_id": subject.current_best_for_next_loop_packet_id,
        "base_current_best_text_sha256": subject.base_text_sha256,
        "base_candidate_text": subject.base_text,
        "prior_working_current_best_candidate_packet_id": (
            subject.prior_working_current_best_candidate_packet_id
        ),
        "prior_historical_current_best_candidate_packet_id": (
            subject.prior_historical_current_best_candidate_packet_id
        ),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "work_order_scope": WORK_ORDER_SCOPE,
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(PRESERVATION_OR_GUARD_UNIT_IDS),
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "phrase_inventory_policy": PHRASE_INVENTORY_POLICY,
        "phrase_inventory": list(phrase_policy["phrase_inventory"]),
        "materiality_requirements": list(MATERIALITY_REQUIREMENTS),
        "semantic_requirements": list(SEMANTIC_REQUIREMENTS),
        "ablation_controls": list(ABLATION_CONTROLS),
        "reader_state_focus": list(READER_STATE_FOCUS),
        "model_must_not": [
            "delete explanation wholesale",
            "reduce object activity",
            "make the text vague",
            "add new object inventory",
            "expand into return-summary repair as the primary target",
            "expand into chemistry-register repair as the primary target",
            "treat phrase inventory as a deletion list",
            "claim finality, phase shift, or strongest-rival defeat",
        ],
    }


def _validate_generated_payload(
    subject: SelectedTargetCycleCandidateSubject,
    payload: dict[str, object],
) -> dict[str, object]:
    text = str(payload.get("text") or "")
    failures: list[str] = []
    lower = text.lower()
    if not text.strip():
        failures.append("text is missing or empty")
    if _normalize_text(text) == _normalize_text(subject.base_text):
        failures.append("text is unchanged from packet_0001")
    forbidden_hits = _forbidden_hits(lower)
    if forbidden_hits:
        failures.append("forbidden rival material present: " + ", ".join(forbidden_hits))
    leakage_hits = [term for term in CLAIM_LEAKAGE_TERMS if term in lower]
    if leakage_hits:
        failures.append("claim leakage present: " + ", ".join(leakage_hits))
    for key in (
        "generation_allowed",
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
    ):
        if payload.get(key) is not False:
            failures.append(f"{key} must be false")
    missing_objects = [term for term in BASE_OBJECT_TERMS if not _contains_word(lower, term)]
    if missing_objects:
        failures.append("base object field absent: " + ", ".join(missing_objects))

    phrase_report = _phrase_report_status(payload.get("phrase_handling_report"))
    target_report = _target_unit_report_status(payload.get("target_unit_change_report"))
    failures.extend(phrase_report["failures"])
    failures.extend(target_report["failures"])
    materiality_passed = _simple_model_report_passed(payload.get("materiality_report"))
    semantic_passed = _simple_model_report_passed(payload.get("semantic_report"))
    preservation_passed = _simple_model_report_passed(payload.get("preservation_report"))
    forbidden_passed = _simple_model_report_passed(
        payload.get("forbidden_overcorrection_report")
    )
    if not materiality_passed:
        failures.append("materiality_report did not pass")
    if not semantic_passed:
        failures.append("semantic_report did not pass")
    if not preservation_passed:
        failures.append("preservation_report did not pass")
    if not forbidden_passed:
        failures.append("forbidden_overcorrection_report did not pass")
    if _explanation_deleted_or_vague(lower):
        failures.append("text deletes explanation or becomes vague atmosphere")
    report = {
        "validation_passed": not failures,
        "validation_failures": failures,
        "phrase_handling_failures": phrase_report["failures"],
        "target_unit_failures": target_report["failures"],
        "materiality_passed": materiality_passed,
        "semantic_passed": semantic_passed,
        "living_event_gain_preserved": preservation_passed and not missing_objects,
        "forbidden_overcorrection_passed": forbidden_passed,
        "non_imitation_passed": not forbidden_hits,
        "forbidden_rival_hits": forbidden_hits,
        "candidate_text_sha256": sha256_text(text),
        "base_text_sha256": subject.base_text_sha256,
    }
    if failures:
        raise SelectedTargetCycleCandidateValidationError(report)
    return report


def _write_candidate_artifacts(
    *,
    writer: PacketWriter,
    model_writer: PacketWriter | None,
    subject: SelectedTargetCycleCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
    model_results: list[ModelDriverResult],
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="source_cycle_authorization_intake_summary",
        payload=_build_source_intake(subject, packet_dir, client_name, model),
        parent_ids=list(subject.source_parent_ids),
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="base_working_current_best_subject",
        payload=_build_base_subject(subject),
        parent_ids=[artifacts["source_cycle_authorization_intake_summary"].id],
    )
    model_call_id = model_results[-1].model_call.id if model_results else None
    payloads["generated_candidate_text"] = _build_generated_text(
        subject,
        model_payload,
        validation_report,
        model_call_id,
        client_name,
    )
    artifacts["generated_candidate_text"] = _write_artifact(
        writer=writer,
        model_writer=model_writer,
        artifact_type="generated_candidate_text",
        payload=payloads["generated_candidate_text"],
        parent_ids=[artifacts["base_working_current_best_subject"].id],
    )
    chained_artifacts = (
        (
            "mechanism_visibility_candidate_diff_summary",
            _build_diff_summary(subject, model_payload),
        ),
        ("phrase_handling_report", _build_phrase_report(model_payload)),
        ("target_unit_change_report", _build_target_report(model_payload)),
        (
            "materiality_validation_report",
            _build_simple_validation_report(
                subject,
                model_payload,
                validation_report,
                "materiality_report",
                "materiality_passed",
            ),
        ),
        (
            "semantic_validation_report",
            _build_simple_validation_report(
                subject,
                model_payload,
                validation_report,
                "semantic_report",
                "semantic_passed",
            ),
        ),
        (
            "protected_living_event_gain_preservation_report",
            _build_simple_validation_report(
                subject,
                model_payload,
                validation_report,
                "preservation_report",
                "living_event_gain_preserved",
            ),
        ),
        (
            "forbidden_overcorrection_regression_report",
            _build_simple_validation_report(
                subject,
                model_payload,
                validation_report,
                "forbidden_overcorrection_report",
                "forbidden_overcorrection_passed",
            ),
        ),
        (
            "non_imitation_validation_report",
            _build_non_imitation_report(subject, validation_report),
        ),
        (
            "authorization_consumption_report",
            _build_consumption_report(subject, client_name, model_results),
        ),
        ("post_generation_evidence_plan", _build_evidence_plan(subject)),
        (
            "selected_target_cycle_candidate_gate_report",
            _build_gate_report(subject, model_results),
        ),
        (
            "project_health_scope_guard_report",
            _build_health_report(subject, validation_report, model_results),
        ),
    )
    parent_id = artifacts["generated_candidate_text"].id
    for artifact_type, payload in chained_artifacts:
        payloads[artifact_type] = payload
        artifacts[artifact_type] = _write_artifact(
            writer=writer,
            model_writer=(
                model_writer
                if artifact_type
                in {
                    "phrase_handling_report",
                    "target_unit_change_report",
                    "materiality_validation_report",
                    "semantic_validation_report",
                    "protected_living_event_gain_preservation_report",
                    "forbidden_overcorrection_regression_report",
                }
                else None
            ),
            artifact_type=artifact_type,
            payload=payload,
            parent_ids=[parent_id],
        )
        parent_id = artifacts[artifact_type].id
    payloads["nonlocal_law_selected_target_cycle_candidate_packet"] = (
        _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=model,
            model_payload=model_payload,
            validation_report=validation_report,
            payloads=payloads,
            artifacts=artifacts,
            model_results=model_results,
        )
    )
    artifacts["nonlocal_law_selected_target_cycle_candidate_packet"] = (
        writer.write_artifact(
            "nonlocal_law_selected_target_cycle_candidate_packet",
            payloads["nonlocal_law_selected_target_cycle_candidate_packet"],
            parent_ids=[artifact.id for artifact in artifacts.values()],
        )
    )
    return payloads, artifacts


def _build_source_intake(
    subject: SelectedTargetCycleCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "model": model,
        "source_authorization_packet_dir": str(subject.authorization_packet_dir),
        "generation_authorized": True,
        "authorization_consumed": True,
        "candidate_generated": True,
        "model_calls": 1 if client_name == "openai" else 0,
        "model_backed": client_name == "openai",
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": SCHEMA_NAME,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "source_cycle_authorization_intake_summary_v1_controller",
    }


def _build_base_subject(subject: SelectedTargetCycleCandidateSubject) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "base_current_best_packet_id": subject.current_best_for_next_loop_packet_id,
        "base_current_best_packet_dir": str(subject.base_candidate_packet_dir),
        "base_current_best_artifact_id": subject.base_candidate_artifact_id,
        "base_current_best_text_sha256": subject.base_text_sha256,
        "base_current_best_word_count": len(subject.base_text.split()),
        "prior_working_current_best_candidate_packet_id": (
            subject.prior_working_current_best_candidate_packet_id
        ),
        "prior_historical_current_best_candidate_packet_id": (
            subject.prior_historical_current_best_candidate_packet_id
        ),
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "base_working_current_best_subject_v1_controller",
    }


def _build_generated_text(
    subject: SelectedTargetCycleCandidateSubject,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
    model_call_id: str | None,
    client_name: str,
) -> dict[str, object]:
    text = str(model_payload["text"])
    return {
        **_source_fields(subject),
        "text": text,
        "text_sha256": sha256_text(text),
        "base_text_sha256": subject.base_text_sha256,
        "word_count": len(text.split()),
        "model_call_id": model_call_id,
        "fixture_only": client_name == "fake",
        "model_backed": client_name == "openai",
        "candidate_generated": True,
        "candidate_artifact_created": True,
        "authorization_consumed": True,
        "validation_passed": validation_report["validation_passed"],
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "generated_candidate_text_v1_controller",
    }


def _build_diff_summary(
    subject: SelectedTargetCycleCandidateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    text = str(model_payload["text"])
    base_words = _word_set(subject.base_text)
    revised_words = _word_set(text)
    return {
        **_source_fields(subject),
        "base_text_sha256": subject.base_text_sha256,
        "candidate_text_sha256": sha256_text(text),
        "changed": _normalize_text(text) != _normalize_text(subject.base_text),
        "added_unique_words": sorted(revised_words - base_words)[:50],
        "removed_unique_words": sorted(base_words - revised_words)[:50],
        "revision_summary": model_payload["revision_summary"],
        "mechanism_visibility_repair_summary": model_payload[
            "mechanism_visibility_repair_summary"
        ],
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "mechanism_visibility_candidate_diff_summary_v1_controller",
    }


def _build_phrase_report(model_payload: dict[str, object]) -> dict[str, object]:
    report = list(model_payload["phrase_handling_report"])
    return {
        "phrase_inventory_policy": PHRASE_INVENTORY_POLICY,
        "phrase_inventory_count": len(PHRASE_INVENTORY),
        "phrase_handling_count": len(report),
        "phrase_handling_report": report,
        "all_phrase_pressure_points_reported": True,
        "phrase_inventory_not_deletion_list": True,
        "passed": True,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "phrase_handling_report_v1_controller",
    }


def _build_target_report(model_payload: dict[str, object]) -> dict[str, object]:
    return {
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(PRESERVATION_OR_GUARD_UNIT_IDS),
        "target_units_reported": list(TARGET_UNIT_IDS),
        "target_unit_count": len(TARGET_UNIT_IDS),
        "target_unit_change_report": list(model_payload["target_unit_change_report"]),
        "all_required_units_reported": True,
        "passed": True,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "target_unit_change_report_v1_controller",
    }


def _build_simple_validation_report(
    subject: SelectedTargetCycleCandidateSubject,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
    payload_key: str,
    passed_key: str,
) -> dict[str, object]:
    source = model_payload[payload_key]
    return {
        **_source_fields(subject),
        "passed": bool(validation_report[passed_key]),
        passed_key: validation_report[passed_key],
        "model_report": source,
        "validation_failures": []
        if validation_report["validation_passed"]
        else validation_report["validation_failures"],
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": f"{payload_key}_v1_controller",
    }


def _build_non_imitation_report(
    subject: SelectedTargetCycleCandidateSubject,
    validation_report: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "passed": validation_report["non_imitation_passed"],
        "non_imitation_passed": validation_report["non_imitation_passed"],
        "forbidden_rival_hits": validation_report["forbidden_rival_hits"],
        "strongest_rival_defeated_claimed": False,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "non_imitation_validation_report_v1_controller",
    }


def _build_consumption_report(
    subject: SelectedTargetCycleCandidateSubject,
    client_name: str,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "authorization_consumed": True,
        "consumption_reason": "accepted_validated_selected_target_cycle_candidate",
        "candidate_generated": True,
        "generation_attempt_index": 1,
        "generation_attempt_budget": 1,
        "remaining_generation_attempt_budget": 0,
        "client": client_name,
        "model_calls": len(model_results),
        "validation_passed_before_consumption": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "authorization_consumption_report_v1_controller",
    }


def _build_evidence_plan(subject: SelectedTargetCycleCandidateSubject) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "required_next_steps": [
            "review_selected_target_cycle_candidate_before_ablation",
            "ablate_selected_target_cycle_candidate",
            "evaluate_selected_target_cycle_candidate_reader_state",
            "synthesize_selected_target_cycle_candidate_evidence",
            "loop_review_before_any_current_best_update",
        ],
        "ablation_controls": list(ABLATION_CONTROLS),
        "reader_state_focus": list(READER_STATE_FOCUS),
        "synthesis_required_before_current_best_update": True,
        "finalization_forbidden_after_generation": True,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "post_generation_evidence_plan_v1_controller",
    }


def _build_gate_report(
    subject: SelectedTargetCycleCandidateSubject,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    gate_results = [
        _gate_result("authorization_consumed", True),
        _gate_result("candidate_generated", True),
        _gate_result("phrase_handling_validated", True),
        _gate_result("material_generation_units_validated", True),
        _gate_result("guard_units_preserved", True),
        _gate_result("materiality_validation_passed", True),
        _gate_result("semantic_validation_passed", True),
        _gate_result("non_imitation_validation_passed", True),
        _gate_result(
            "post_generation_evidence_pending",
            False,
            ["ablation, reader-state evaluation, and synthesis remain pending"],
            record=False,
        ),
        _gate_result(
            "strongest_rival_resolved",
            False,
            ["strongest rival pressure remains blocking"],
            record=False,
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["candidate generation is not finalization evidence"],
            record=False,
        ),
    ]
    return {
        **_source_fields(subject),
        "passed": False,
        "eligible": False,
        "candidate_generated": True,
        "authorization_consumed": True,
        "model_calls": len(model_results),
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "gate_results": gate_results,
        "failed_gates": [
            str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
        ],
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            "ablation has not been executed",
            "reader-state evaluation has not been run",
            "synthesis has not been run",
            "strongest rival remains blocking",
            "finalization remains refused",
        ],
        "worker": "selected_target_cycle_candidate_gate_report_v1_controller",
    }


def _build_health_report(
    subject: SelectedTargetCycleCandidateSubject,
    validation_report: dict[str, object],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    checks = [
        _check("authorization_consumed", True),
        _check("candidate_generated", True),
        _check("validation_passed", validation_report["validation_passed"] is True),
        _check("phrase_handling_validated", not validation_report["phrase_handling_failures"]),
        _check("model_call_count_expected", len(model_results) in {0, 1}),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
        _check("no_strongest_rival_defeat_claim", True),
    ]
    passed = all(bool(check["passed"]) for check in checks)
    return {
        **_source_fields(subject),
        "checks": checks,
        "passed": passed,
        "project_health_scope_guard_passed": passed,
        "source_chain_coherent": True,
        "candidate_generated": True,
        "authorization_consumed": True,
        "model_calls": len(model_results),
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: SelectedTargetCycleCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_cycle_candidate_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "model": model,
        "candidate_generated": True,
        "candidate_artifact_created": True,
        "candidate_artifact_id": artifacts["generated_candidate_text"].id,
        **_source_fields(subject),
        "selected_target_class": SELECTED_TARGET_CLASS,
        "work_order_scope": WORK_ORDER_SCOPE,
        "phrase_inventory_policy": PHRASE_INVENTORY_POLICY,
        "model_backed": client_name == "openai",
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": SCHEMA_NAME,
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "model_calls": len(model_results),
        "materiality_requirements": list(MATERIALITY_REQUIREMENTS),
        "semantic_requirements": list(SEMANTIC_REQUIREMENTS),
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(PRESERVATION_OR_GUARD_UNIT_IDS),
        "phrase_handling_report": list(model_payload["phrase_handling_report"]),
        "target_unit_change_report": list(model_payload["target_unit_change_report"]),
        "validation_report": validation_report,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "counts": {
            **counts,
            "model_calls": len(model_results),
            "candidate_artifacts_created": 1,
        },
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [*artifacts, "nonlocal_law_selected_target_cycle_candidate_packet"],
        "gate_report": payloads["selected_target_cycle_candidate_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "current_best_supersession_claimed": False,
        "worker": "nonlocal_law_selected_target_cycle_candidate_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_cycle_candidate_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
        "model_call_ids": [result.model_call.id for result in model_results],
    }


def _failure_result(
    *,
    config: AbiConfig,
    subject: SelectedTargetCycleCandidateSubject,
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
    message: str,
    validation_report: dict[str, object],
) -> SelectedTargetCycleCandidateGenerationResult:
    with connect(config.db_path) as connection:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_cycle_failed_generation"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=LINEAGE_ID,
            created_by=CREATED_BY,
            fixture_only=client_name == "fake",
            model_call_id=None,
        )
        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}
        failure_surface = _failure_surface_fields(validation_report, model_results)
        payloads["failed_generation_diagnostic"] = {
            "accepted": False,
            "message": message,
            **failure_surface,
            "client": client_name,
            "model": model,
            **_source_fields(subject),
            "validation_report": validation_report,
            "model_call_ids": [result.model_call.id for result in model_results],
            "authorization_consumed": False,
            "candidate_generated": False,
            "model_calls": len(model_results),
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "worker": "failed_generation_diagnostic_v1_controller",
        }
        artifacts["failed_generation_diagnostic"] = writer.write_artifact(
            "failed_generation_diagnostic",
            payloads["failed_generation_diagnostic"],
            parent_ids=list(subject.source_parent_ids),
        )
        payloads["failed_generation_gate_report"] = {
            **_source_fields(subject),
            "passed": False,
            "eligible": False,
            "authorization_consumed": False,
            "candidate_generated": False,
            "model_calls": len(model_results),
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "unresolved_blockers": [message],
            "worker": "failed_generation_gate_report_v1_controller",
        }
        artifacts["failed_generation_gate_report"] = writer.write_artifact(
            "failed_generation_gate_report",
            payloads["failed_generation_gate_report"],
            parent_ids=[artifacts["failed_generation_diagnostic"].id],
        )
        counts = packet_artifact_count_summary(
            required_artifact_types=FAILED_ARTIFACT_TYPES,
            produced_artifact_types=list(artifacts),
            packet_artifact_type="nonlocal_law_selected_target_cycle_failed_generation_packet",
        )
        payloads["nonlocal_law_selected_target_cycle_failed_generation_packet"] = {
            "accepted": False,
            "refused": True,
            "message": message,
            **failure_surface,
            "packet_id": packet_dir.name,
            "packet_dir": str(packet_dir),
            **_source_fields(subject),
            "authorization_consumed": False,
            "candidate_generated": False,
            "candidate_artifact_created": False,
            "model_calls": len(model_results),
            "counts": {**counts, "model_calls": len(model_results)},
            "artifact_ids": {
                artifact_type: artifact.id
                for artifact_type, artifact in artifacts.items()
            },
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
            "current_best_supersession_claimed": False,
            "next_recommended_action": FAILED_NEXT_RECOMMENDED_ACTION,
            "worker": (
                "nonlocal_law_selected_target_cycle_failed_generation_packet_v1_controller"
            ),
        }
        artifacts["nonlocal_law_selected_target_cycle_failed_generation_packet"] = (
            writer.write_artifact(
                "nonlocal_law_selected_target_cycle_failed_generation_packet",
                payloads["nonlocal_law_selected_target_cycle_failed_generation_packet"],
                parent_ids=[
                    artifacts["failed_generation_diagnostic"].id,
                    artifacts["failed_generation_gate_report"].id,
                ],
            )
        )
    return SelectedTargetCycleCandidateGenerationResult(
        exit_code=1,
        payload={
            **payloads["nonlocal_law_selected_target_cycle_failed_generation_packet"],
            "artifact_paths": {
                artifact_type: str(packet_dir / f"{artifact_type}.json")
                for artifact_type in artifacts
            },
            "validation_report": validation_report,
        },
        artifacts=tuple(artifacts.values()),
        model_results=tuple(model_results),
    )


def _failure_surface_fields(
    validation_report: dict[str, object],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    latest_result = model_results[-1] if model_results else None
    output_payload = (
        _model_output_payload_for_result(latest_result)
        if latest_result is not None
        else {}
    )
    failures = _validation_failures(validation_report)
    model_call_status = (
        str(validation_report.get("model_call_status"))
        if validation_report.get("model_call_status")
        else (latest_result.model_call.status if latest_result is not None else None)
    )
    return {
        "failure_class": "selected_target_cycle_generation_validation_failure",
        "failure_reason": (
            "structured_output_validation_failed"
            if model_call_status == MODEL_CALL_VALIDATION_FAILED
            else "controller_validation_failed"
        ),
        "validation_failures": failures,
        "model_call_status": model_call_status,
        "model_output_keys": sorted(output_payload),
        "generation_allowed": output_payload.get("generation_allowed"),
        "finality_claimed": output_payload.get("finality_claimed"),
        "phase_shift_claimed": output_payload.get("phase_shift_claimed"),
        "strongest_rival_defeated_claimed": output_payload.get(
            "strongest_rival_defeated_claimed"
        ),
        "diagnostic_message": (
            "Selected-target cycle candidate generation failed validation."
        ),
    }


def _validation_failures(validation_report: dict[str, object]) -> list[str]:
    failures = validation_report.get("validation_failures")
    if isinstance(failures, list):
        return [str(failure) for failure in failures]
    return []


def _model_output_payload_for_result(
    model_result: ModelDriverResult,
) -> dict[str, object]:
    if isinstance(model_result.parsed_payload, dict):
        return dict(model_result.parsed_payload)
    path = model_result.model_call.raw_output_path
    if not path:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _validation_report_for_model_failure(
    model_result: ModelDriverResult,
) -> dict[str, object]:
    report: dict[str, object] = {
        "validation_passed": False,
        "validation_failures": [
            model_result.model_call.error_message or model_result.model_call.status
        ],
        "model_call_status": model_result.model_call.status,
    }
    report.update(
        {
            "model_output_keys": sorted(_model_output_payload_for_result(model_result)),
            "generation_allowed": _model_output_payload_for_result(model_result).get(
                "generation_allowed"
            ),
            "finality_claimed": _model_output_payload_for_result(model_result).get(
                "finality_claimed"
            ),
            "phase_shift_claimed": _model_output_payload_for_result(model_result).get(
                "phase_shift_claimed"
            ),
            "strongest_rival_defeated_claimed": _model_output_payload_for_result(
                model_result
            ).get("strongest_rival_defeated_claimed"),
        }
    )
    return report


def _model_failure_message(result: ModelDriverResult) -> str:
    return (
        "Selected-target cycle candidate generation refused; model call "
        f"{result.model_call.status}: "
        f"{result.model_call.error_message or 'no parsed output'}"
    )


def _load_required_payloads(
    packet_dir: Path,
    artifact_types: tuple[str, ...],
    label: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    envelopes: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in artifact_types:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(f"{label} missing {path.name}")
        envelope = read_json_file(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError(f"malformed {label} artifact: {path.name}")
        envelopes[artifact_type] = envelope
        payloads[artifact_type] = envelope["payload"]
    return envelopes, payloads


def _load_base_candidate_payload(
    connection: sqlite3.Connection,
    packet_dir: Path,
) -> tuple[dict[str, Any], str | None]:
    path = packet_dir / "generated_candidate_text.json"
    if not path.exists():
        raise ValueError("base current-best generated_candidate_text cannot be loaded")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        raise ValueError("base current-best text artifact is malformed")
    artifact = _artifact_for_path(connection, path)
    return payload, artifact.id if artifact else None


def _linked_candidate_for_authorization(
    connection: sqlite3.Connection,
    subject: SelectedTargetCycleCandidateSubject,
) -> ArtifactRecord | None:
    for artifact in list_artifacts(connection, subject.run_id):
        if "nonlocal_law_selected_target_cycle_candidate" not in Path(
            artifact.path
        ).parts:
            continue
        if artifact.type not in {
            "nonlocal_law_selected_target_cycle_candidate_packet",
            "generated_candidate_text",
        }:
            continue
        payload = _artifact_payload(artifact)
        if payload.get("source_authorization_packet_id") != subject.authorization_packet_id:
            continue
        if (
            payload.get("candidate_generated") is True
            and payload.get("authorization_consumed") is True
        ):
            return artifact
    return None


def _write_payload_artifact(
    *,
    writer: PacketWriter,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> None:
    payloads[artifact_type] = payload
    artifacts[artifact_type] = writer.write_artifact(
        artifact_type,
        payload,
        parent_ids=parent_ids,
    )


def _write_artifact(
    *,
    writer: PacketWriter,
    model_writer: PacketWriter | None,
    artifact_type: str,
    payload: dict[str, object],
    parent_ids: list[str],
) -> ArtifactRecord:
    return (model_writer or writer).write_artifact(
        artifact_type,
        payload,
        parent_ids=parent_ids,
    )


def _phrase_report_status(report: object) -> dict[str, object]:
    failures: list[str] = []
    expected = _phrase_set()
    if not isinstance(report, list):
        return {"passed": False, "failures": ["phrase_handling_report missing"]}
    if len(report) != len(expected):
        failures.append(f"phrase_handling_report must contain {len(expected)} phrases")
    seen: set[str] = set()
    for item in _object_items(report):
        phrase = str(item.get("phrase") or "")
        if phrase not in expected:
            failures.append(f"unknown phrase: {phrase}")
        if phrase in seen:
            failures.append(f"duplicate phrase: {phrase}")
        seen.add(phrase)
        for field_name, expected_value in (
            ("deletion_required", False),
            ("automatic_deletion_forbidden", True),
            ("pressure_point_not_deletion_target", True),
            ("transformation_or_earned_retention_required", True),
            ("causal_force_preserved", True),
            ("living_event_sequence_weakened", False),
        ):
            if item.get(field_name) is not expected_value:
                failures.append(f"{phrase}.{field_name} must be {expected_value}")
    missing = expected - seen
    if missing:
        failures.append("missing phrases: " + ", ".join(sorted(missing)))
    return {"passed": not failures, "failures": failures}


def _target_unit_report_status(report: object) -> dict[str, object]:
    failures: list[str] = []
    expected = set(TARGET_UNIT_IDS)
    if not isinstance(report, list):
        return {"passed": False, "failures": ["target_unit_change_report missing"]}
    by_unit = {
        str(item.get("unit_id")): item
        for item in _object_items(report)
        if item.get("unit_id")
    }
    missing = expected - set(by_unit)
    extra = set(by_unit) - expected
    if missing:
        failures.append("missing target units: " + ", ".join(sorted(missing)))
    if extra:
        failures.append("unknown target units: " + ", ".join(sorted(extra)))
    for unit_id in MATERIAL_GENERATION_UNIT_IDS:
        item = by_unit.get(unit_id, {})
        if item.get("material_change_present") is not True:
            failures.append(f"{unit_id}.material_change_present must be true")
        if item.get("validation_required") is not True:
            failures.append(f"{unit_id}.validation_required must be true")
    for unit_id in PRESERVATION_OR_GUARD_UNIT_IDS:
        item = by_unit.get(unit_id, {})
        if item.get("preservation_passed") is not True:
            failures.append(f"{unit_id}.preservation_passed must be true")
        if item.get("validation_required") is not True:
            failures.append(f"{unit_id}.validation_required must be true")
    return {"passed": not failures, "failures": failures}


def _simple_model_report_passed(report: object) -> bool:
    if not isinstance(report, dict):
        return False
    evidence = report.get("evidence")
    return report.get("passed") is True and isinstance(evidence, list) and bool(evidence)


def _object_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _forbidden_hits(text: str) -> list[str]:
    return [term for term in FORBIDDEN_RIVAL_TERMS if _contains_word(text, term)]


def _explanation_deleted_or_vague(text: str) -> bool:
    vague_terms = (
        "vague atmosphere",
        "all explanation disappears",
        "no explanation remains",
        "pure mood",
        "merely atmospheric",
    )
    return any(term in text for term in vague_terms)


def _contains_word(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text.lower()) is not None


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower()))


def _phrase_set() -> set[str]:
    return {str(item["phrase"]) for item in PHRASE_INVENTORY}


def _valid_fake_payload(prompt: dict[str, object]) -> dict[str, object]:
    phrase_inventory = list(prompt.get("phrase_inventory", []))
    phrase_values = [
        str(item.get("phrase") if isinstance(item, dict) else item)
        for item in phrase_inventory
    ]
    if not phrase_values:
        phrase_values = [str(item["phrase"]) for item in PHRASE_INVENTORY]
    target_units = [str(unit) for unit in prompt["target_unit_ids"]]
    text = (
        "The table is still there in the morning. The ring is not announced as a "
        "meaning. It waits in the grain until the light reaches it, and the light "
        "has to bend around the bare edge before the eye can settle. Dust has "
        "thickened on one side and thinned on the other, so the next glance does "
        "not simply move across the table; it is slowed, redirected, and made to "
        "receive the mark as a pressure in the wood.\n\n"
        "The spoon touches the saucer once when the refrigerator starts. The sound "
        "does not explain the table, but it changes the order of attention. First "
        "the ring, then the dust, then the spoon's small answer, then the crack in "
        "the saucer: one visible thing hands the room to the next. Only after the "
        "objects have arranged that passage can the room begin to instruct. The "
        "instruction is not a label. It is the way the table has made later seeing "
        "pass through what the morning received.\n\n"
        "The room teaches slowly because nothing steps outside the ordinary field. "
        "The ring stays a ring, the dust stays dust, the spoon remains near the "
        "saucer, and still each relation leaves the next perception altered. What "
        "would have been a proof becomes an event that keeps working. Explanation "
        "arrives only where it has been earned by object pressure, and the return "
        "finds the first sentence changed by the sequence it had to cross."
    )
    return {
        "text": text,
        "revision_summary": (
            "Reduced direct mechanism naming by making object relations carry the "
            "reader's altered order of attention."
        ),
        "mechanism_visibility_repair_summary": (
            "The candidate treats mechanism phrases as pressure points rather than "
            "deletion targets, preserving causal force through ring, dust, spoon, "
            "saucer, and light."
        ),
        "phrase_handling_report": [
            {
                "phrase": phrase,
                "phrase_found_in_source": True,
                "handling_action": "transformed",
                "deletion_required": False,
                "automatic_deletion_forbidden": True,
                "pressure_point_not_deletion_target": True,
                "transformation_or_earned_retention_required": True,
                "earned_retention_allowed": True,
                "context_sensitive_decision_required": True,
                "preserve_if_still_earned_after_object_pressure": True,
                "handling_rationale": (
                    "The phrase is carried by object pressure rather than treated "
                    "as an automatic deletion target."
                ),
                "causal_force_preserved": True,
                "living_event_sequence_weakened": False,
            }
            for phrase in phrase_values
        ],
        "target_unit_change_report": [
            {
                "unit_id": unit_id,
                "change_summary": (
                    f"{unit_id} is addressed through bounded mechanism visibility repair."
                ),
                "material_change_present": unit_id in MATERIAL_GENERATION_UNIT_IDS,
                "preservation_passed": True,
                "validation_required": True,
            }
            for unit_id in target_units
        ],
        "materiality_report": {
            "passed": True,
            "summary": "Object-event sequence materially carries causal pressure.",
            "evidence": [
                "ring, dust, spoon, saucer, and light alter later perception before naming"
            ],
        },
        "semantic_report": {
            "passed": True,
            "summary": "Mechanism naming is reduced without deleting earned explanation.",
            "evidence": ["explanation arrives only after object pressure"],
        },
        "preservation_report": {
            "passed": True,
            "summary": "Living-event sequence gain remains preserved.",
            "evidence": ["ordinary object relations remain active and delicate"],
        },
        "forbidden_overcorrection_report": {
            "passed": True,
            "summary": "No wholesale deletion, vague atmosphere, or target expansion.",
            "evidence": ["the text remains bounded to mechanism visibility repair"],
        },
        "post_generation_evidence_note": {
            "passed": True,
            "summary": "Ablation, reader-state evaluation, and synthesis remain pending.",
            "evidence": ["candidate is evidence-ready but not finalization evidence"],
        },
        "generation_allowed": False,
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "strongest_rival_defeated_claimed": False,
    }


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    try:
        envelope = read_json_file(artifact.path)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        return {}
    return envelope["payload"]


def _artifact_ids_from_packet(packet_payload: dict[str, Any]) -> dict[str, str]:
    raw = packet_payload.get("artifact_ids")
    if not isinstance(raw, dict):
        return {}
    return {
        str(artifact_type): str(artifact_id)
        for artifact_type, artifact_id in raw.items()
        if isinstance(artifact_type, str)
        and isinstance(artifact_id, str)
        and artifact_id
    }


def _artifact_for_path(
    connection: sqlite3.Connection,
    path: Path,
) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (str(path),),
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _refusal(
    *,
    message: str,
    authorization_packet: Path | str,
    client_name: str,
    model: str | None,
) -> SelectedTargetCycleCandidateGenerationResult:
    return SelectedTargetCycleCandidateGenerationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "authorization_packet": str(authorization_packet),
            "client": client_name,
            "model": model,
            "source_authorization_packet_id": None,
            "source_work_order_packet_id": None,
            "source_target_selection_packet_id": None,
            "current_best_for_next_loop_packet_id": None,
            "generation_authorized": client_name == "openai",
            "next_generation_authorized": client_name == "openai",
            "authorization_consumed": False,
            "candidate_generated": False,
            "candidate_artifact_created": False,
            "generation_attempt_index": None,
            "model_calls": 0,
            "counts": {"model_calls": 0, "candidate_artifacts_created": 0},
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
            "current_best_supersession_claimed": False,
            "next_recommended_action": "review_refusal_before_generation",
        },
    )


def _source_fields(subject: SelectedTargetCycleCandidateSubject) -> dict[str, object]:
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "source_target_selection_packet_id": subject.target_selection_packet_id,
        "source_consolidation_packet_id": subject.source_consolidation_packet_id,
        "source_loop_review_packet_id": subject.source_loop_review_packet_id,
        "source_synthesis_packet_id": subject.source_synthesis_packet_id,
        "source_reader_state_packet_id": subject.source_reader_state_packet_id,
        "source_candidate_packet_id": subject.source_candidate_packet_id,
        "base_current_best_packet_id": subject.current_best_for_next_loop_packet_id,
        "current_best_for_next_loop_packet_id": (
            subject.current_best_for_next_loop_packet_id
        ),
        "prior_working_current_best_candidate_packet_id": (
            subject.prior_working_current_best_candidate_packet_id
        ),
        "prior_historical_current_best_candidate_packet_id": (
            subject.prior_historical_current_best_candidate_packet_id
        ),
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "selected_target_class": SELECTED_TARGET_CLASS,
        "work_order_scope": WORK_ORDER_SCOPE,
        "phrase_inventory_policy": PHRASE_INVENTORY_POLICY,
    }


def _require_equal(payload: dict[str, Any], field_name: str, expected: object) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _require_bool(payload: dict[str, Any], field_name: str, expected: bool) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(f"{field_name} must be {str(expected).lower()}")


def _has_final_or_phase_claim(payloads: dict[str, dict[str, Any]]) -> bool:
    return any(_payload_has_final_or_phase_claim(payload) for payload in payloads.values())


def _payload_has_final_or_phase_claim(payload: dict[str, Any]) -> bool:
    return (
        payload.get("finalization_eligible") is True
        or payload.get("no_final_claim") is False
        or payload.get("no_phase_shift_claim") is False
        or payload.get("strongest_rival_defeated_claimed") is True
    )


def _check(name: str, passed: bool, details: str | None = None) -> dict[str, object]:
    return {"check": name, "passed": bool(passed), "details": details}


def _gate_result(
    gate_name: str,
    passed: bool,
    blockers: list[str] | None = None,
    *,
    record: bool = True,
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "blocking_defects": list(blockers or []),
        "record_as_final_gate": record,
    }


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
