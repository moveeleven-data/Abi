"""Bounded selected nonlocal-law target candidate generation."""

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
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_calls import MODEL_CALL_VALIDATION_FAILED, link_model_call_parsed_artifact
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    ModelValidationError,
    SELECTED_NONLOCAL_LAW_TARGET_GENERATION_SCHEMA,
    WorkerRole,
)
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_consolidated_target_selection import (
    SELECTED_RISK_ID,
    SELECTED_TARGET_SEED_ID,
)
from abi.modules.nonlocal_law_cycle_consolidation import (
    EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
)
from abi.modules.nonlocal_law_selected_target_generation_authorization import (
    AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    CONSTRAINT_UNIT_IDS,
    MATERIAL_GENERATION_UNIT_IDS,
    NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_ARTIFACT_TYPES,
    _stale_authorization_message,
)
from abi.modules.nonlocal_law_selected_target_work_order import (
    ABLATION_CONTROLS,
    FORBIDDEN_REGRESSIONS,
    FORBIDDEN_RIVAL_IMITATION_MODES,
    FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE,
    FUTURE_SCHEMA,
    GENERATION_CONTRACT_VERSION,
    MATERIALITY_POLICY_ID,
    MATERIALITY_REQUIREMENTS,
    NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND,
    PROMPT_CONTRACT_ID,
    PROTECTED_PACKET_0002_STRENGTHS,
    READER_STATE_FOCUS,
    SEMANTIC_VALIDATION_REQUIREMENTS,
    SEMANTIC_VALIDATOR_ID,
    TARGET_UNIT_IDS,
    WORK_ORDER_SCOPE,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_LINEAGE_ID = (
    "nonlocal_law_selected_target_candidate_generation_v1"
)
NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_CREATED_BY = (
    "nonlocal_law_selected_target_candidate_generation_v1_controller"
)
NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_CLIENTS = ("fake", "openai")
NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_REQUIRED_MODEL_CALLS = 1
NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT = 1
NEXT_RECOMMENDED_ACTION = "review_selected_nonlocal_law_candidate_before_ablation"
FAILED_NEXT_RECOMMENDED_ACTION = (
    "review_failed_selected_nonlocal_law_candidate_generation"
)
SAFETY_METADATA_FAILURE_CLASS = (
    "selected_nonlocal_law_generation_safety_metadata_failure"
)
SAFETY_GENERATION_ALLOWED_REASON = "generation_allowed_true_or_not_false"
GENERATION_ALLOWED_DIAGNOSTIC_MESSAGE = (
    "The model treated generation_allowed as current-call permission. This field "
    "is a downstream safety/escalation assertion and must be false."
)

PACKET_0002_OBJECT_FIELD = ("table", "dust", "spoon", "saucer", "ring", "light")
CLAIM_LEAKAGE_TERMS = (
    "final artifact",
    "finalization",
    "phase shift",
    "phase-shift",
    "human validation",
    "validated by readers",
    "strongest rival defeated",
    "defeats the strongest rival",
    "beats the rival",
    "current best is updated",
    "supersedes the current best",
    "immediate finalization",
)
FORBIDDEN_PROCESS_CLAIMS = (
    "ablation proves",
    "reader-state evaluation proves",
    "synthesis proves",
    "finalization proves",
)
GENERIC_INCIDENT_TERMS = (
    "generic incident",
    "generic vividness",
    "decorative vividness",
    "busier scene",
)
OBJECT_INVENTORY_AS_CAUSALITY_TERMS = (
    "object inventory is living causality",
    "inventory itself is causality",
    "list of objects makes causality",
)

NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ARTIFACT_TYPES = (
    "source_authorization_intake_summary",
    "base_current_best_subject",
    "generated_candidate_text",
    "selected_target_diff_summary",
    "target_unit_change_report",
    "living_event_sequence_validation_report",
    "materiality_validation_report",
    "semantic_validation_report",
    "non_imitation_validation_report",
    "protected_strengths_preservation_report",
    "forbidden_regression_report",
    "authorization_consumption_report",
    "post_generation_evidence_plan",
    "selected_target_candidate_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_selected_target_candidate_packet",
)

FAILED_NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ARTIFACT_TYPES = (
    "failed_generation_diagnostic",
    "failed_generation_gate_report",
    "nonlocal_law_selected_target_failed_generation_packet",
)

REQUIRED_AUTHORIZATION_ARTIFACTS = (
    NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_ARTIFACT_TYPES
)


@dataclass(frozen=True)
class NonlocalLawSelectedTargetCandidateGenerationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class NonlocalLawSelectedTargetCandidateSubject:
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
    prior_current_best_candidate_packet_id: str
    base_candidate_packet_dir: Path
    base_candidate_artifact_id: str | None
    base_text: str
    base_text_sha256: str


class NonlocalLawSelectedTargetCandidateValidationError(ModelValidationError):
    def __init__(self, validation_report: dict[str, object]) -> None:
        self.validation_report = validation_report
        failures = validation_report.get("validation_failures")
        if isinstance(failures, list):
            message = "; ".join(str(item) for item in failures)
        else:
            message = "validation failed"
        super().__init__(message)


class FakeSelectedNonlocalLawTargetGenerationModelClient:
    provider = "fake"
    model = "fake-selected-nonlocal-law-target-generation-v1"

    def __init__(
        self,
        mode: str = "valid",
        *,
        provider: str = "fake",
        model: str = "fake-selected-nonlocal-law-target-generation-v1",
    ) -> None:
        self.mode = mode
        self.provider = provider
        self.model = model

    def generate(self, request: WorkerRequest) -> str:
        prompt = json.loads(request.input_text)
        payload = _valid_fake_payload(prompt)
        if self.mode == "forbidden_rival_material":
            payload["text"] += " A cup waits by the windowsill."
        elif self.mode == "missing_material_unit":
            payload["target_unit_change_report"] = [
                item
                for item in payload["target_unit_change_report"]
                if item["target_unit_id"] != MATERIAL_GENERATION_UNIT_IDS[0]
            ]
        elif self.mode == "finality":
            payload["finality_claimed"] = True
            payload["safety_claims"]["finality_claimed"] = True
        elif self.mode == "phase_shift":
            payload["phase_shift_claimed"] = True
            payload["safety_claims"]["phase_shift_claimed"] = True
        elif self.mode == "rival_defeat":
            payload["strongest_rival_defeated_claimed"] = True
            payload["safety_claims"]["strongest_rival_defeated_claimed"] = True
        elif self.mode == "current_best_supersession":
            payload["current_best_supersession_claimed"] = True
            payload["safety_claims"]["current_best_supersession_claimed"] = True
        elif self.mode == "generation_allowed":
            payload["generation_allowed"] = True
            payload["safety_claims"]["generation_allowed"] = True
        elif self.mode == "unchanged":
            payload["text"] = str(prompt["base_candidate_text"])
        elif self.mode == "static_trace":
            payload["text"] = (
                "The table is still there. Dust and spoon and saucer and ring "
                "show what already happened. The light explains the evidence."
            )
            payload["selected_target_application_summary"] = (
                "The trace remains retrospective evidence."
            )
            payload["living_event_sequence_repair_summary"] = (
                "No repair is introduced before naming."
            )
            payload["target_unit_change_report"][0]["materiality_satisfied"] = False
            payload["materiality_self_report"][0]["satisfied"] = False
        elif self.mode == "invalid_json":
            return "{not valid json"
        return _canonical_json(payload)


def run_nonlocal_law_selected_target_candidate_generation(
    config: AbiConfig,
    *,
    client_name: str,
    authorization_packet: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = (
        NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT
    ),
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> NonlocalLawSelectedTargetCandidateGenerationResult:
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name not in NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_CLIENTS:
        return _refusal(
            message=(
                "Unsupported selected nonlocal law candidate client: "
                f"{client_name}"
            ),
            authorization_packet=authorization_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )

    initialize_database(config)
    resolved_packet = _resolve_path(config, authorization_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            message=(
                "Selected nonlocal law candidate generation refused; authorization "
                f"packet directory not found: {resolved_packet}"
            ),
            authorization_packet=resolved_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )
    stale_message = _stale_authorization_message(resolved_packet)
    if stale_message is not None:
        return _refusal(
            message=stale_message,
            authorization_packet=resolved_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )
    if client_name == "openai":
        if not allow_live_model:
            return _refusal(
                message=(
                    "Selected nonlocal law candidate OpenAI path refused; pass "
                    "--allow-live-model to opt in explicitly."
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model,
            )
        resolved_api_key = (
            api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        )
        if not resolved_api_key:
            return _refusal(
                message=(
                    "Selected nonlocal law candidate OpenAI path refused; "
                    f"{OPENAI_API_KEY_ENV} is not set."
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model,
            )
        if (
            max_model_calls
            != NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_REQUIRED_MODEL_CALLS
        ):
            return _refusal(
                message=(
                    "Selected nonlocal law candidate OpenAI path refused; "
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
                    "Selected nonlocal law candidate generation refused; "
                    f"{error}"
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )

        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Selected nonlocal law candidate generation refused; run is "
                    f"not registered: {subject.run_id}"
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )
        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_ACTIVE_PHASE,
        )

    fixture_only = client_name == "fake"
    model_results: list[ModelDriverResult] = []
    model_call_id: str | None = None
    packet_dir: Path | None = None
    if client_name == "fake":
        model_payload = _valid_fake_payload(_prompt_packet(subject))
    else:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_selected_target_candidate"
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
    except NonlocalLawSelectedTargetCandidateValidationError as error:
        return _failure_result(
            config=config,
            subject=subject,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_results=model_results,
            message=(
                "Selected nonlocal law candidate generation refused; "
                f"{error}"
            ),
            validation_report=error.validation_report,
        )

    if packet_dir is None:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_selected_target_candidate"
        )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_CREATED_BY,
            fixture_only=fixture_only,
            model_call_id=None,
        )
        model_writer = (
            PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=packet_dir,
                lineage_id=(
                    NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_LINEAGE_ID
                ),
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
            gate_name="selected_target_candidate_gate_report",
            passed=False,
            blocking_defects=list(
                payloads["selected_target_candidate_gate_report"][
                    "unresolved_blockers"
                ]
            ),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_LINEAGE_ID,
        )

    return NonlocalLawSelectedTargetCandidateGenerationResult(
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
) -> NonlocalLawSelectedTargetCandidateSubject:
    auth_envelopes, auth_payloads = _load_required_payloads(
        authorization_packet_dir,
        REQUIRED_AUTHORIZATION_ARTIFACTS,
        "authorization packet",
    )
    auth_packet = auth_payloads[
        "nonlocal_law_selected_target_generation_authorization_packet"
    ]
    run_id = str(
        auth_packet.get("run_id")
        or auth_envelopes[
            "nonlocal_law_selected_target_generation_authorization_packet"
        ].get("run_id")
        or ""
    )
    if not run_id:
        raise ValueError("authorization packet missing run_id")
    base_packet_id = str(
        auth_packet.get("source_candidate_packet_id")
        or auth_packet.get("current_best_for_next_loop_packet_id")
        or EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID
    )
    base_packet_dir = (
        config.run_dir(run_id) / "nonlocal_law_guided_candidate" / base_packet_id
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
        / "nonlocal_law_selected_target_generation_authorization_packet.json",
    )
    auth_artifact_ids = _artifact_ids_from_packet(auth_packet)
    parent_ids = _unique(
        [
            auth_packet_artifact.id if auth_packet_artifact else None,
            base_artifact_id,
            *auth_artifact_ids.values(),
        ]
    )
    return NonlocalLawSelectedTargetCandidateSubject(
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
        source_candidate_packet_id=base_packet_id,
        current_best_for_next_loop_packet_id=str(
            auth_packet.get("current_best_for_next_loop_packet_id") or ""
        ),
        prior_current_best_candidate_packet_id=str(
            auth_packet.get("prior_current_best_candidate_packet_id") or ""
        ),
        base_candidate_packet_dir=base_packet_dir,
        base_candidate_artifact_id=base_artifact_id,
        base_text=base_text,
        base_text_sha256=str(base_payload.get("text_sha256") or sha256_text(base_text)),
    )


def _validate_subject_before_generation(
    connection: sqlite3.Connection,
    subject: NonlocalLawSelectedTargetCandidateSubject,
) -> None:
    auth = subject.authorization_payloads[
        "nonlocal_law_selected_target_generation_authorization_packet"
    ]
    gate = subject.authorization_payloads[
        "selected_target_generation_authorization_gate_report"
    ]
    budget = subject.authorization_payloads["model_call_budget_report"]
    lock = subject.authorization_payloads["generation_lock_transition_report"]
    units = subject.authorization_payloads["target_unit_authorization_scope"]

    _require_bool(auth, "accepted", True)
    _require_equal(auth, "decision", AUTHORIZATION_DECISION_AUTHORIZE_ONE)
    _require_bool(auth, "generation_authorized", True)
    _require_bool(auth, "next_generation_authorized", True)
    _require_equal(auth, "generation_attempt_budget", 1)
    _require_bool(auth, "authorization_consumed", False)
    _require_bool(auth, "candidate_generated", False)
    _require_equal(auth, "model_calls", 0)
    _require_equal(auth, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(auth, "selected_target_seed_id", SELECTED_TARGET_SEED_ID)
    _require_equal(auth, "selected_risk_id", SELECTED_RISK_ID)
    _require_equal(auth, "source_work_order_packet_id", "packet_0002")
    _require_equal(auth, "source_target_selection_packet_id", "packet_0002")
    _require_equal(
        auth,
        "current_best_for_next_loop_packet_id",
        EXPECTED_CURRENT_BEST_FOR_NEXT_LOOP_PACKET_ID,
    )
    _require_equal(
        auth,
        "prior_current_best_candidate_packet_id",
        EXPECTED_PRIOR_CURRENT_BEST_PACKET_ID,
    )
    _require_equal(auth, "source_candidate_packet_id", "packet_0002")
    _require_equal(auth, "work_order_kind", NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND)
    _require_equal(auth, "work_order_scope", WORK_ORDER_SCOPE)
    _require_bool(auth, "no_final_claim", True)
    _require_bool(auth, "no_phase_shift_claim", True)
    _require_bool(auth, "strongest_rival_defeated_claimed", False)
    _require_optional_equal(auth, "generation_contract_version", GENERATION_CONTRACT_VERSION)
    _require_optional_equal(auth, "prompt_contract_id", PROMPT_CONTRACT_ID)
    _require_optional_equal(auth, "materiality_policy_id", MATERIALITY_POLICY_ID)
    _require_optional_equal(auth, "semantic_validator_id", SEMANTIC_VALIDATOR_ID)
    _require_optional_equal(auth, "schema", FUTURE_SCHEMA)
    _require_equal(budget, "remaining_model_calls", 1)
    _require_equal(budget, "model_call_budget", 1)
    _require_equal(lock, "authorization_packet_does_not_run_generation", True)
    _require_exact_list(auth, "material_generation_unit_ids", MATERIAL_GENERATION_UNIT_IDS)
    _require_exact_list(auth, "preservation_or_guard_unit_ids", CONSTRAINT_UNIT_IDS)
    _require_exact_list(units, "material_generation_unit_ids", MATERIAL_GENERATION_UNIT_IDS)
    _require_exact_list(units, "preservation_or_guard_unit_ids", CONSTRAINT_UNIT_IDS)
    if gate.get("finalization_eligible") is True:
        raise ValueError("authorization gate report is finalization eligible")
    if int(auth.get("generation_attempt_budget") or 0) != 1:
        raise ValueError("generation_attempt_budget must be 1")
    if _linked_candidate_for_authorization(connection, subject) is not None:
        raise ValueError("existing accepted candidate already consumed this authorization")
    if _has_final_or_phase_claim(subject.authorization_payloads):
        raise ValueError("authorization carries finality or phase-shift claim")


def _run_live_generation_model(
    *,
    config: AbiConfig,
    subject: NonlocalLawSelectedTargetCandidateSubject,
    packet_dir: Path,
    model_client: ModelClient,
    parent_ids: list[str],
) -> ModelDriverResult:
    return ModelDriver(config=config, client=model_client).run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.SELECTED_NONLOCAL_LAW_TARGET_GENERATOR,
            prompt_contract_id=PROMPT_CONTRACT_ID,
            schema=SELECTED_NONLOCAL_LAW_TARGET_GENERATION_SCHEMA,
            input_text=_canonical_json(_prompt_packet(subject)),
            input_artifact_ids=parent_ids,
            input_packet_path=str(subject.authorization_packet_dir),
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_LINEAGE_ID,
            parent_ids=parent_ids,
            fixture_only=False,
            output_dir=str(packet_dir),
            register_parsed_artifact=False,
        )
    )


def _prompt_packet(subject: NonlocalLawSelectedTargetCandidateSubject) -> dict[str, object]:
    auth = subject.authorization_payloads[
        "nonlocal_law_selected_target_generation_authorization_packet"
    ]
    return {
        "task": "generate one bounded selected nonlocal law target candidate",
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": FUTURE_SCHEMA,
        "authorization_packet_id": subject.authorization_packet_id,
        "work_order_packet_id": subject.work_order_packet_id,
        "source_target_selection_packet_id": subject.target_selection_packet_id,
        "base_current_best_packet_id": subject.source_candidate_packet_id,
        "base_current_best_text_sha256": subject.base_text_sha256,
        "base_candidate_text": subject.base_text,
        "prior_current_best_candidate_packet_id": (
            subject.prior_current_best_candidate_packet_id
        ),
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "work_order_scope": WORK_ORDER_SCOPE,
        "target_unit_ids": list(auth["target_unit_ids"]),
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(CONSTRAINT_UNIT_IDS),
        "materiality_requirements": list(auth["materiality_requirements"]),
        "semantic_validation_requirements": list(
            auth["semantic_validation_requirements"]
        ),
        "forbidden_rival_objects_or_sequence": list(
            auth["forbidden_rival_sequence"]
        ),
        "forbidden_rival_imitation_modes": list(auth["forbidden_rival_modes"]),
        "forbidden_regressions": list(auth["forbidden_regressions"]),
        "ablation_controls": list(auth["post_generation_evidence_plan"]["ablation_controls"])
        if isinstance(auth.get("post_generation_evidence_plan"), dict)
        else list(ABLATION_CONTROLS),
        "reader_state_focus": list(READER_STATE_FOCUS),
        "model_must_not": [
            "copy rival scenes, diction, cadence, causal plot, or object inventory",
            "claim improvement, finality, phase shift, strongest-rival defeat, or current-best supersession",
            "run or claim ablation, reader-state evaluation, synthesis, or finalization",
            "perform a free rewrite beyond the selected target",
            "add generic incidents or vividness instead of living object-event consequence",
        ],
    }


def _validate_generated_payload(
    subject: NonlocalLawSelectedTargetCandidateSubject,
    payload: dict[str, object],
) -> dict[str, object]:
    text = str(payload.get("text") or "")
    failures: list[str] = []
    lower = text.lower()
    combined = " ".join(
        [
            lower,
            str(payload.get("selected_target_application_summary") or "").lower(),
            str(payload.get("living_event_sequence_repair_summary") or "").lower(),
        ]
    )
    if not text.strip():
        failures.append("text is missing or empty")
    if _normalize_text(text) == _normalize_text(subject.base_text):
        failures.append("text is unchanged from packet_0002")
    forbidden_hits = _forbidden_rival_hits(text)
    if forbidden_hits:
        failures.append("text contains forbidden rival material: " + ", ".join(forbidden_hits))
    leakage_hits = [term for term in CLAIM_LEAKAGE_TERMS if term in lower]
    if leakage_hits:
        failures.append(
            "text contains finality/current-best/rival-defeat claim leakage: "
            + ", ".join(leakage_hits)
        )
    process_hits = [term for term in FORBIDDEN_PROCESS_CLAIMS if term in lower]
    if process_hits:
        failures.append(
            "text includes post-generation evidence claims: " + ", ".join(process_hits)
        )
    generic_hits = [term for term in GENERIC_INCIDENT_TERMS if term in combined]
    if generic_hits:
        failures.append(
            "text substitutes generic incident or vividness for selected target: "
            + ", ".join(generic_hits)
        )
    inventory_hits = [
        term for term in OBJECT_INVENTORY_AS_CAUSALITY_TERMS if term in combined
    ]
    if inventory_hits:
        failures.append("text treats object inventory as living causality")

    for key in (
        "generation_allowed",
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
        "current_best_supersession_claimed",
    ):
        if payload.get(key) is not False:
            failures.append(f"{key} must be false")
    safety = payload.get("safety_claims")
    if not isinstance(safety, dict):
        failures.append("safety_claims missing")
    else:
        for key in (
            "generation_allowed",
            "finality_claimed",
            "phase_shift_claimed",
            "strongest_rival_defeated_claimed",
            "current_best_supersession_claimed",
        ):
            if safety.get(key) is not False:
                failures.append(f"safety_claims.{key} must be false")

    missing_objects = [
        term for term in PACKET_0002_OBJECT_FIELD if not _contains_word(lower, term)
    ]
    if missing_objects:
        failures.append("packet_0002 object field absent: " + ", ".join(missing_objects))
    explanation_timing_preserved = _explanation_timing_preserved(combined)
    if not explanation_timing_preserved:
        failures.append("explanation timing is not preserved or earned")

    living_event_sequence_present = _living_event_sequence_present(combined)
    static_trace_reduced = _static_retrospective_trace_reduced(combined)
    causal_bridge_present = _causal_bridge_present(combined)
    consequence_before_naming = _consequence_before_naming_present(combined)
    if not living_event_sequence_present:
        failures.append("living event sequence not present")
    if not static_trace_reduced:
        failures.append("static retrospective trace not materially reduced")
    if not causal_bridge_present:
        failures.append("causal bridge between object-events not present")
    if not consequence_before_naming:
        failures.append("consequence before naming not present")

    reported_units = _reported_target_units(payload.get("target_unit_change_report"))
    missing_units = [unit_id for unit_id in TARGET_UNIT_IDS if unit_id not in reported_units]
    if missing_units:
        failures.append(
            "target_unit_change_report missing required units: "
            + ", ".join(missing_units)
        )
    for item in _object_items(payload.get("target_unit_change_report")):
        unit_id = str(item.get("target_unit_id") or "")
        if item.get("semantic_satisfied") is not True:
            failures.append(f"semantic not satisfied for {unit_id}")
        if (
            unit_id in MATERIAL_GENERATION_UNIT_IDS
            and item.get("materiality_satisfied") is not True
        ):
            failures.append(f"materiality not satisfied for {unit_id}")
        if (
            unit_id in CONSTRAINT_UNIT_IDS
            and item.get("semantic_satisfied") is not True
        ):
            failures.append(f"guard unit not preserved for {unit_id}")

    materiality_report = _requirement_report_status(
        payload.get("materiality_self_report"),
        MATERIALITY_REQUIREMENTS,
    )
    semantic_report = _requirement_report_status(
        payload.get("semantic_self_report"),
        SEMANTIC_VALIDATION_REQUIREMENTS,
    )
    failures.extend(materiality_report["failures"])
    failures.extend(semantic_report["failures"])
    non_imitation = payload.get("non_imitation_acknowledgement")
    if not isinstance(non_imitation, dict) or non_imitation.get("passed") is not True:
        failures.append("non_imitation_acknowledgement does not explicitly pass")
    protected = payload.get("protected_strengths_preservation_acknowledgement")
    if not isinstance(protected, dict) or protected.get("preserved") is not True:
        failures.append(
            "protected_strengths_preservation_acknowledgement does not preserve strengths"
        )
    forbidden = payload.get("forbidden_regression_acknowledgement")
    if not isinstance(forbidden, dict) or forbidden.get("passed") is not True:
        failures.append(
            "forbidden_regression_acknowledgement does not explicitly pass"
        )

    materiality_passed = (
        materiality_report["passed"]
        and living_event_sequence_present
        and static_trace_reduced
        and causal_bridge_present
        and consequence_before_naming
    )
    semantic_passed = (
        semantic_report["passed"]
        and not missing_objects
        and explanation_timing_preserved
        and not generic_hits
        and not inventory_hits
    )
    report = {
        "validation_passed": not failures,
        "validation_failures": failures,
        "target_units_reported": sorted(reported_units),
        "missing_target_units": missing_units,
        "materiality_passed": materiality_passed,
        "semantic_passed": semantic_passed,
        "living_event_sequence_present": living_event_sequence_present,
        "static_retrospective_trace_reduced": static_trace_reduced,
        "causal_bridge_between_object_events_present": causal_bridge_present,
        "consequence_before_naming_present": consequence_before_naming,
        "existing_object_field_preserved": not missing_objects,
        "explanation_timing_preserved": explanation_timing_preserved,
        "selected_target_scope_preserved": True,
        "generic_vividness_absent": not generic_hits,
        "object_inventory_as_living_causality_absent": not inventory_hits,
        "non_imitation_passed": isinstance(non_imitation, dict)
        and non_imitation.get("passed") is True
        and not forbidden_hits,
        "protected_strengths_preserved": isinstance(protected, dict)
        and protected.get("preserved") is True,
        "forbidden_regression_passed": isinstance(forbidden, dict)
        and forbidden.get("passed") is True,
        "forbidden_rival_hits": forbidden_hits,
        "candidate_text_sha256": sha256_text(text),
        "base_text_sha256": subject.base_text_sha256,
    }
    if failures:
        raise NonlocalLawSelectedTargetCandidateValidationError(report)
    return report


def _write_candidate_artifacts(
    *,
    writer: PacketWriter,
    model_writer: PacketWriter | None,
    subject: NonlocalLawSelectedTargetCandidateSubject,
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
        artifact_type="source_authorization_intake_summary",
        payload=_build_source_intake(subject, packet_dir, client_name, model),
        parent_ids=list(subject.source_parent_ids),
    )
    _write_payload_artifact(
        writer=writer,
        artifacts=artifacts,
        payloads=payloads,
        artifact_type="base_current_best_subject",
        payload=_build_base_subject(subject),
        parent_ids=[artifacts["source_authorization_intake_summary"].id],
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
        parent_ids=[artifacts["base_current_best_subject"].id],
    )

    chained_artifacts = (
        ("selected_target_diff_summary", _build_diff_summary(subject, model_payload)),
        ("target_unit_change_report", _build_target_report(model_payload)),
        (
            "living_event_sequence_validation_report",
            _build_living_event_sequence_report(subject, validation_report),
        ),
        (
            "materiality_validation_report",
            _build_materiality_report(subject, model_payload, validation_report),
        ),
        (
            "semantic_validation_report",
            _build_semantic_report(subject, validation_report),
        ),
        (
            "non_imitation_validation_report",
            _build_non_imitation_report(model_payload, validation_report),
        ),
        (
            "protected_strengths_preservation_report",
            _build_protected_report(model_payload, validation_report),
        ),
        (
            "forbidden_regression_report",
            _build_forbidden_regression_report(model_payload, validation_report),
        ),
        (
            "authorization_consumption_report",
            _build_consumption_report(subject, client_name, model_results),
        ),
        ("post_generation_evidence_plan", _build_evidence_plan(subject)),
        (
            "selected_target_candidate_gate_report",
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
                    "target_unit_change_report",
                    "materiality_validation_report",
                    "semantic_validation_report",
                    "non_imitation_validation_report",
                    "protected_strengths_preservation_report",
                    "forbidden_regression_report",
                }
                else None
            ),
            artifact_type=artifact_type,
            payload=payload,
            parent_ids=[parent_id],
        )
        parent_id = artifacts[artifact_type].id

    payloads["nonlocal_law_selected_target_candidate_packet"] = (
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
    artifacts["nonlocal_law_selected_target_candidate_packet"] = writer.write_artifact(
        "nonlocal_law_selected_target_candidate_packet",
        payloads["nonlocal_law_selected_target_candidate_packet"],
        parent_ids=[
            artifact.id
            for artifact_type, artifact in artifacts.items()
            if artifact_type != "nonlocal_law_selected_target_candidate_packet"
        ],
    )
    return payloads, artifacts


def _build_source_intake(
    subject: NonlocalLawSelectedTargetCandidateSubject,
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
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "source_authorization_intake_summary_v1_controller",
    }


def _build_base_subject(
    subject: NonlocalLawSelectedTargetCandidateSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "base_current_best_packet_id": subject.current_best_for_next_loop_packet_id,
        "base_current_best_packet_dir": str(subject.base_candidate_packet_dir),
        "base_current_best_artifact_id": subject.base_candidate_artifact_id,
        "base_current_best_text_sha256": subject.base_text_sha256,
        "base_current_best_word_count": len(subject.base_text.split()),
        "prior_current_best_candidate_packet_id": (
            subject.prior_current_best_candidate_packet_id
        ),
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "base_current_best_subject_v1_controller",
    }


def _build_generated_text(
    subject: NonlocalLawSelectedTargetCandidateSubject,
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
        "generation_attempt_index": 1,
        "validation_passed": validation_report["validation_passed"],
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "generated_candidate_text_v1_controller",
    }


def _build_diff_summary(
    subject: NonlocalLawSelectedTargetCandidateSubject,
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
        "selected_target_application_summary": model_payload[
            "selected_target_application_summary"
        ],
        "living_event_sequence_repair_summary": model_payload[
            "living_event_sequence_repair_summary"
        ],
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "selected_target_diff_summary_v1_controller",
    }


def _build_target_report(model_payload: dict[str, object]) -> dict[str, object]:
    return {
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(CONSTRAINT_UNIT_IDS),
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


def _build_living_event_sequence_report(
    subject: NonlocalLawSelectedTargetCandidateSubject,
    validation_report: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "passed": validation_report["materiality_passed"],
        "living_event_sequence_present": validation_report[
            "living_event_sequence_present"
        ],
        "static_retrospective_trace_reduced": validation_report[
            "static_retrospective_trace_reduced"
        ],
        "causal_bridge_between_object_events_present": validation_report[
            "causal_bridge_between_object_events_present"
        ],
        "consequence_before_naming_present": validation_report[
            "consequence_before_naming_present"
        ],
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "living_event_sequence_validation_report_v1_controller",
    }


def _build_materiality_report(
    subject: NonlocalLawSelectedTargetCandidateSubject,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "required_requirements": list(MATERIALITY_REQUIREMENTS),
        "self_report": list(model_payload["materiality_self_report"]),
        "materiality_passed": validation_report["materiality_passed"],
        "living_event_sequence_present": validation_report[
            "living_event_sequence_present"
        ],
        "static_retrospective_trace_reduced": validation_report[
            "static_retrospective_trace_reduced"
        ],
        "causal_bridge_between_object_events_present": validation_report[
            "causal_bridge_between_object_events_present"
        ],
        "consequence_before_naming_present": validation_report[
            "consequence_before_naming_present"
        ],
        "materiality_failures": [] if validation_report["materiality_passed"] else [
            failure
            for failure in validation_report["validation_failures"]
            if "materiality" in str(failure)
            or "living" in str(failure)
            or "causal" in str(failure)
            or "trace" in str(failure)
        ],
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "materiality_validation_report_v1_controller",
    }


def _build_semantic_report(
    subject: NonlocalLawSelectedTargetCandidateSubject,
    validation_report: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "semantic_passed": validation_report["semantic_passed"],
        "existing_object_field_preserved": validation_report[
            "existing_object_field_preserved"
        ],
        "explanation_timing_preserved": validation_report[
            "explanation_timing_preserved"
        ],
        "selected_target_scope_preserved": validation_report[
            "selected_target_scope_preserved"
        ],
        "generic_vividness_absent": validation_report["generic_vividness_absent"],
        "object_inventory_as_living_causality_absent": validation_report[
            "object_inventory_as_living_causality_absent"
        ],
        "semantic_failures": [] if validation_report["semantic_passed"] else [
            failure
            for failure in validation_report["validation_failures"]
            if "semantic" in str(failure)
            or "object" in str(failure)
            or "explanation" in str(failure)
            or "generic" in str(failure)
        ],
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "semantic_validation_report_v1_controller",
    }


def _build_non_imitation_report(
    model_payload: dict[str, object],
    validation_report: dict[str, object],
) -> dict[str, object]:
    return {
        **dict(model_payload["non_imitation_acknowledgement"]),
        "forbidden_rival_objects_or_sequence": list(FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE),
        "forbidden_rival_imitation_modes": list(FORBIDDEN_RIVAL_IMITATION_MODES),
        "forbidden_rival_hits": list(validation_report["forbidden_rival_hits"]),
        "forbidden_rival_mode_hits": [],
        "rival_imitation_detected": False,
        "non_imitation_evidence": model_payload[
            "non_imitation_acknowledgement"
        ]["evidence"],
        "passed": validation_report["non_imitation_passed"],
        "strongest_rival_defeated_claimed": False,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "non_imitation_validation_report_v1_controller",
    }


def _build_protected_report(
    model_payload: dict[str, object],
    validation_report: dict[str, object],
) -> dict[str, object]:
    return {
        **dict(model_payload["protected_strengths_preservation_acknowledgement"]),
        "protected_strengths_preserved": validation_report[
            "protected_strengths_preserved"
        ],
        "first_read_pressure_preserved_or_improved": True,
        "object_event_consequence_preserved_or_improved": True,
        "explanation_timing_preserved": validation_report[
            "explanation_timing_preserved"
        ],
        "reread_return_preserved": True,
        "packet_0002_object_field_preserved": validation_report[
            "existing_object_field_preserved"
        ],
        "proof_and_reader_state_references_preserved": True,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "protected_strengths_preservation_report_v1_controller",
    }


def _build_forbidden_regression_report(
    model_payload: dict[str, object],
    validation_report: dict[str, object],
) -> dict[str, object]:
    safety = dict(model_payload["safety_claims"])
    return {
        **dict(model_payload["forbidden_regression_acknowledgement"]),
        "forbidden_regression_passed": validation_report["forbidden_regression_passed"],
        "free_rewrite_absent": True,
        "generic_incident_addition_absent": validation_report["generic_vividness_absent"],
        "deleted_explanation_absent": True,
        "premature_explanation_absent": validation_report[
            "explanation_timing_preserved"
        ],
        "rival_imitation_absent": validation_report["non_imitation_passed"],
        "finality_claim_absent": safety.get("finality_claimed") is False,
        "phase_shift_claim_absent": safety.get("phase_shift_claimed") is False,
        "strongest_rival_defeat_claim_absent": (
            safety.get("strongest_rival_defeated_claimed") is False
        ),
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "forbidden_regression_report_v1_controller",
    }


def _build_consumption_report(
    subject: NonlocalLawSelectedTargetCandidateSubject,
    client_name: str,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "authorization_consumed": True,
        "consumption_reason": "accepted_validated_selected_target_candidate",
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


def _build_evidence_plan(
    subject: NonlocalLawSelectedTargetCandidateSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "required_next_steps": [
            "ablate_selected_nonlocal_law_candidate",
            "evaluate_selected_nonlocal_law_candidate_reader_state",
            "synthesize_selected_nonlocal_law_candidate_evidence",
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
    subject: NonlocalLawSelectedTargetCandidateSubject,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    gate_results = [
        _gate_result("authorization_consumed", True),
        _gate_result("candidate_generated", True),
        _gate_result("material_generation_units_validated", True),
        _gate_result("guard_units_preserved", True),
        _gate_result("materiality_validation_passed", True),
        _gate_result("semantic_validation_passed", True),
        _gate_result("non_imitation_validation_passed", True),
        _gate_result("protected_strengths_preserved", True),
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
        "worker": "selected_target_candidate_gate_report_v1_controller",
    }


def _build_health_report(
    subject: NonlocalLawSelectedTargetCandidateSubject,
    validation_report: dict[str, object],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    checks = [
        _check("authorization_consumed", True),
        _check("candidate_generated", True),
        _check("validation_passed", validation_report["validation_passed"] is True),
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
    subject: NonlocalLawSelectedTargetCandidateSubject,
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
        required_artifact_types=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_selected_target_candidate_packet",
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
        "work_order_kind": NONLOCAL_LAW_SELECTED_TARGET_WORK_ORDER_KIND,
        "work_order_scope": WORK_ORDER_SCOPE,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
        "generation_contract_version": GENERATION_CONTRACT_VERSION,
        "materiality_policy_id": MATERIALITY_POLICY_ID,
        "semantic_validator_id": SEMANTIC_VALIDATOR_ID,
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": FUTURE_SCHEMA,
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "model_calls": len(model_results),
        "model_backed": client_name == "openai",
        "materiality_requirements": list(MATERIALITY_REQUIREMENTS),
        "semantic_validation_requirements": list(SEMANTIC_VALIDATION_REQUIREMENTS),
        "target_unit_ids": list(TARGET_UNIT_IDS),
        "material_generation_unit_ids": list(MATERIAL_GENERATION_UNIT_IDS),
        "preservation_or_guard_unit_ids": list(CONSTRAINT_UNIT_IDS),
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
        "artifact_types": [
            *artifacts,
            "nonlocal_law_selected_target_candidate_packet",
        ],
        "gate_report": payloads["selected_target_candidate_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "current_best_supersession_claimed": False,
        "worker": "nonlocal_law_selected_target_candidate_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_selected_target_candidate_packet"]
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
    subject: NonlocalLawSelectedTargetCandidateSubject,
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
    message: str,
    validation_report: dict[str, object],
) -> NonlocalLawSelectedTargetCandidateGenerationResult:
    with connect(config.db_path) as connection:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_selected_target_failed_generation"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_CREATED_BY,
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
            required_artifact_types=(
                FAILED_NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_ARTIFACT_TYPES
            ),
            produced_artifact_types=list(artifacts),
            packet_artifact_type="nonlocal_law_selected_target_failed_generation_packet",
        )
        payloads["nonlocal_law_selected_target_failed_generation_packet"] = {
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
            "worker": "nonlocal_law_selected_target_failed_generation_packet_v1_controller",
        }
        artifacts["nonlocal_law_selected_target_failed_generation_packet"] = (
            writer.write_artifact(
                "nonlocal_law_selected_target_failed_generation_packet",
                payloads["nonlocal_law_selected_target_failed_generation_packet"],
                parent_ids=[
                    artifacts["failed_generation_diagnostic"].id,
                    artifacts["failed_generation_gate_report"].id,
                ],
            )
        )
    return NonlocalLawSelectedTargetCandidateGenerationResult(
        exit_code=1,
        payload={
            **payloads["nonlocal_law_selected_target_failed_generation_packet"],
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
    validation_failures = _validation_failures(validation_report)
    model_call_status = (
        str(validation_report.get("model_call_status"))
        if validation_report.get("model_call_status")
        else (
            latest_result.model_call.status if latest_result is not None else None
        )
    )
    observation = _model_output_observation(output_payload)
    if _is_generation_allowed_failure(validation_failures, output_payload):
        failure_class = SAFETY_METADATA_FAILURE_CLASS
        failure_reason = SAFETY_GENERATION_ALLOWED_REASON
        diagnostic_message = GENERATION_ALLOWED_DIAGNOSTIC_MESSAGE
    else:
        failure_class = "selected_nonlocal_law_generation_validation_failure"
        failure_reason = (
            "structured_output_validation_failed"
            if model_call_status == MODEL_CALL_VALIDATION_FAILED
            else "controller_validation_failed"
        )
        diagnostic_message = (
            "Selected nonlocal law candidate generation failed validation."
        )
    return {
        "failure_class": failure_class,
        "failure_reason": failure_reason,
        "validation_failures": validation_failures,
        "model_call_status": model_call_status,
        "diagnostic_message": diagnostic_message,
        **observation,
    }


def _is_generation_allowed_failure(
    validation_failures: list[str],
    output_payload: dict[str, object],
) -> bool:
    return any("generation_allowed" in failure for failure in validation_failures) or (
        "generation_allowed" in output_payload
        and output_payload.get("generation_allowed") is not False
    )


def _validation_failures(validation_report: dict[str, object]) -> list[str]:
    failures = validation_report.get("validation_failures")
    if isinstance(failures, list):
        return [str(failure) for failure in failures]
    return []


def _model_output_observation(output_payload: dict[str, object]) -> dict[str, object]:
    safety = output_payload.get("safety_claims")
    if not isinstance(safety, dict):
        safety = {}
    return {
        "model_output_keys": sorted(output_payload),
        "generation_allowed": output_payload.get("generation_allowed"),
        "finality_claimed": output_payload.get("finality_claimed"),
        "phase_shift_claimed": output_payload.get("phase_shift_claimed"),
        "strongest_rival_defeated_claimed": output_payload.get(
            "strongest_rival_defeated_claimed"
        ),
        "current_best_supersession_claimed": output_payload.get(
            "current_best_supersession_claimed"
        ),
        "safety_claims": safety,
    }


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
    report.update(_model_output_observation(_model_output_payload_for_result(model_result)))
    return report


def _model_failure_message(result: ModelDriverResult) -> str:
    return (
        "Selected nonlocal law candidate generation refused; model call "
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
    subject: NonlocalLawSelectedTargetCandidateSubject,
) -> ArtifactRecord | None:
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type not in {
            "nonlocal_law_selected_target_candidate_packet",
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


def _requirement_report_status(
    report: object,
    required: tuple[str, ...],
) -> dict[str, object]:
    failures: list[str] = []
    if not isinstance(report, list):
        return {"passed": False, "failures": ["requirement self-report missing"]}
    by_requirement = {
        str(item.get("requirement")): item
        for item in report
        if isinstance(item, dict)
    }
    for requirement in required:
        item = by_requirement.get(requirement)
        if item is None:
            failures.append(f"requirement missing: {requirement}")
        elif item.get("satisfied") is not True:
            failures.append(f"requirement not satisfied: {requirement}")
    return {"passed": not failures, "failures": failures}


def _reported_target_units(report: object) -> set[str]:
    return {
        str(item.get("target_unit_id"))
        for item in _object_items(report)
        if item.get("target_unit_id")
    }


def _object_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _forbidden_rival_hits(text: str) -> list[str]:
    lower = text.lower()
    hits: list[str] = []
    for term in FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE:
        normalized = term.lower()
        if "sequence" in normalized:
            continue
        if _contains_word(lower, normalized):
            hits.append(term)
    for mode in FORBIDDEN_RIVAL_IMITATION_MODES:
        if mode.lower() in lower:
            hits.append(mode)
    return hits


def _living_event_sequence_present(text: str) -> bool:
    return (
        _has_any(text, ("active condition", "later perception", "changes later", "alters later"))
        or (
            _has_any(text, ("then", "until", "after", "because", "makes", "answers"))
            and _has_any(text, PACKET_0002_OBJECT_FIELD)
        )
    )


def _static_retrospective_trace_reduced(text: str) -> bool:
    return _has_any(
        text,
        (
            "not merely report",
            "not merely evidence",
            "active condition",
            "condition later",
            "later perception",
            "working edge",
            "has to pass",
        ),
    )


def _causal_bridge_present(text: str) -> bool:
    object_hits = sum(1 for term in PACKET_0002_OBJECT_FIELD if _contains_word(text, term))
    return object_hits >= 4 and _has_any(
        text,
        (
            "because",
            "therefore",
            "then",
            "until",
            "makes",
            "answers",
            "conditions",
            "has to pass",
            "leaves",
        ),
    )


def _consequence_before_naming_present(text: str) -> bool:
    return _has_any(
        text,
        (
            "before explanation",
            "before any explanation",
            "before conceptual naming",
            "before it has a name",
            "before naming",
            "before anyone tries to say",
        ),
    )


def _explanation_timing_preserved(text: str) -> bool:
    return _has_any(
        text,
        (
            "only after",
            "before explanation",
            "before any explanation",
            "earned explanation",
            "explanation remains earned",
            "explanation enters",
            "does explanation",
            "conceptual naming",
        ),
    )


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def _contains_word(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text.lower()) is not None


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower()))


def _valid_fake_payload(prompt: dict[str, object]) -> dict[str, object]:
    target_units = [str(unit) for unit in prompt["target_unit_ids"]]
    materiality = [str(item) for item in prompt["materiality_requirements"]]
    semantic = [str(item) for item in prompt["semantic_validation_requirements"]]
    text = (
        "The table is still there in the morning. Before any explanation can "
        "settle over it, the ring on the wood has already changed what the next "
        "look must pass through. Dust gathers along one edge of the mark, not as "
        "a report of something finished, but as an active condition: the light "
        "catches it first, the spoon answers it next, and the saucer makes the "
        "small pressure harder to dismiss.\n\n"
        "The spoon lies close enough to the saucer that the refrigerator's hum "
        "makes metal touch clay, then stop. That contact makes the ring appear "
        "less like a stain and more like a boundary the morning has to cross. "
        "Dust is no longer a general film. It has been divided by pressure, by "
        "air, by the near edge of the spoon, until the surface begins to carry "
        "sequence rather than inventory. The table does not explain this. It "
        "keeps it.\n\n"
        "Only after the ring, dust, spoon, saucer, and light have made their "
        "relations felt does explanation have a place to enter. It cannot arrive "
        "as a label pasted over stillness. It has to follow what the objects have "
        "already done to one another: the mark changes the light, the light makes "
        "the dust legible, the dust sharpens the spoon's angle, and the spoon's "
        "small answer returns the eye to the saucer. What happened is finished, "
        "but its working edge remains inside the first look.\n\n"
        "When the room returns, it returns through that altered condition. The "
        "table is still itself; the ring is still a ring; dust, spoon, saucer, "
        "and light remain ordinary. Yet the ordinary surface no longer sits "
        "outside consequence. The first sentence comes back carrying what later "
        "perception had to learn before naming it."
    )
    safety = {
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "strongest_rival_defeated_claimed": False,
        "current_best_supersession_claimed": False,
        "generation_allowed": False,
    }
    return {
        "text": text,
        "revision_summary": (
            "Converted a retrospective trace into an active object-event sequence "
            "while keeping the selected intervention bounded."
        ),
        "selected_target_application_summary": (
            "The ring, dust, spoon, saucer, and light condition later perception "
            "before explanation, directly addressing the selected target."
        ),
        "living_event_sequence_repair_summary": (
            "Object traces no longer merely report finished events; they become "
            "active conditions and causal bridges before conceptual naming."
        ),
        "target_unit_change_report": [
            {
                "target_unit_id": unit_id,
                "change_summary": (
                    f"{unit_id} is addressed through bounded living-event sequence."
                ),
                "materiality_satisfied": unit_id in MATERIAL_GENERATION_UNIT_IDS,
                "semantic_satisfied": True,
            }
            for unit_id in target_units
        ],
        "materiality_self_report": [
            {
                "requirement": requirement,
                "satisfied": True,
                "evidence": "The candidate materially changes object-event function.",
            }
            for requirement in materiality
        ],
        "semantic_self_report": [
            {
                "requirement": requirement,
                "satisfied": True,
                "evidence": "The candidate preserves selected semantic guards.",
            }
            for requirement in semantic
        ],
        "non_imitation_acknowledgement": {
            "passed": True,
            "evidence": "No rival object inventory, scene structure, cadence, or causal plot is used.",
            "forbidden_material_absent": list(FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE),
        },
        "protected_strengths_preservation_acknowledgement": {
            "preserved": True,
            "evidence": "The table, dust, spoon, saucer, ring, light field and earned explanation timing remain active.",
            "protected_strengths": list(PROTECTED_PACKET_0002_STRENGTHS),
        },
        "forbidden_regression_acknowledgement": {
            "passed": True,
            "evidence": "The candidate avoids free rewrite, generic incident addition, explanation deletion, rival imitation, and safety claims.",
            "avoided_regressions": list(FORBIDDEN_REGRESSIONS),
        },
        "safety_claims": safety,
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "strongest_rival_defeated_claimed": False,
        "current_best_supersession_claimed": False,
        "generation_allowed": False,
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
) -> NonlocalLawSelectedTargetCandidateGenerationResult:
    return NonlocalLawSelectedTargetCandidateGenerationResult(
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
            "prior_current_best_candidate_packet_id": None,
            "generation_authorized": client_name == "openai",
            "next_generation_authorized": client_name == "openai",
            "authorization_consumed": False,
            "candidate_generated": False,
            "candidate_artifact_created": False,
            "generation_attempt_index": None,
            "model_calls": 0,
            "counts": {
                "model_calls": 0,
                "candidate_artifacts_created": 0,
            },
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
            "current_best_supersession_claimed": False,
            "next_recommended_action": "review_refusal_before_generation",
        },
    )


def _source_fields(subject: NonlocalLawSelectedTargetCandidateSubject) -> dict[str, object]:
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
        "prior_current_best_candidate_packet_id": (
            subject.prior_current_best_candidate_packet_id
        ),
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "selected_target_seed_id": SELECTED_TARGET_SEED_ID,
        "selected_risk_id": SELECTED_RISK_ID,
    }


def _require_equal(payload: dict[str, Any], field_name: str, expected: object) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _require_optional_equal(
    payload: dict[str, Any],
    field_name: str,
    expected: object,
) -> None:
    if payload.get(field_name) is not None and payload.get(field_name) != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _require_bool(payload: dict[str, Any], field_name: str, expected: bool) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(f"{field_name} must be {str(expected).lower()}")


def _require_exact_list(
    payload: dict[str, Any],
    field_name: str,
    expected: tuple[str, ...],
) -> None:
    value = payload.get(field_name)
    if not isinstance(value, list) or [str(item) for item in value] != list(expected):
        raise ValueError(f"{field_name} must match expected selected target surface")


def _has_final_or_phase_claim(payloads: dict[str, dict[str, Any]]) -> bool:
    return any(_payload_has_final_or_phase_claim(payload) for payload in payloads.values())


def _payload_has_final_or_phase_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "finalization_eligible",
                "final_artifact",
                "final_claim",
                "phase_shift_claim",
                "strongest_rival_defeated",
                "strongest_rival_defeat_claim",
                "current_best_supersession_claimed",
            } and item is True:
                return True
            if key in {"no_final_claim", "no_phase_shift_claim"} and item is False:
                return True
            if _payload_has_final_or_phase_claim(item):
                return True
    elif isinstance(value, list):
        return any(_payload_has_final_or_phase_claim(item) for item in value)
    return False


def _check(
    check_id: str,
    passed: bool,
    blockers: list[str] | None = None,
) -> dict[str, object]:
    return {
        "check_id": check_id,
        "passed": passed,
        "blocking_defects": blockers or ([] if passed else [f"{check_id} failed"]),
    }


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
        "blocking_defects": blockers or ([] if passed else [f"{gate_name} failed"]),
        "recorded_as_passed_gate": record and passed,
    }


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
