"""Bounded nonlocal law-guided candidate generation."""

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
    AUTONOMOUS_NONLOCAL_LAW_GUIDED_CANDIDATE_GENERATION_ACTIVE_PHASE,
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
    NONLOCAL_LAW_GUIDED_GENERATION_SCHEMA,
    WorkerRole,
)
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_guided_generation_authorization import (
    AUTHORIZATION_DECISION_AUTHORIZE_ONE,
)
from abi.modules.nonlocal_law_guided_strategy import SELECTED_NONLOCAL_STRATEGY_CLASS
from abi.modules.nonlocal_law_guided_work_order import (
    ABLATION_CONTROLS,
    FORBIDDEN_RIVAL_IMITATION_MODES,
    FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE,
    FUTURE_SCHEMA_NAME,
    GENERATION_CONTRACT_VERSION,
    MATERIALITY_POLICY_ID,
    MATERIALITY_REQUIREMENTS,
    NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND,
    NONLOCAL_LAW_TARGET_SCOPE,
    NONLOCAL_TARGET_UNIT_IDS,
    PROMPT_CONTRACT_ID,
    READER_STATE_FOCUS,
    SEMANTIC_VALIDATION_REQUIREMENTS,
    SEMANTIC_VALIDATOR_ID,
)
from abi.modules.post_local_residual_strategy_synthesis import (
    EXPECTED_CURRENT_BEST_PACKET_ID,
    EXPECTED_PROOF_PACKET_ID,
    EXPECTED_READER_STATE_PACKET_ID,
)
from abi.packets import (
    PacketWriter,
    create_packet_dir,
    packet_artifact_count_summary,
    read_json_file,
)


NONLOCAL_LAW_CANDIDATE_GENERATION_LINEAGE_ID = (
    "nonlocal_law_guided_candidate_generation_v1"
)
NONLOCAL_LAW_CANDIDATE_GENERATION_CREATED_BY = (
    "nonlocal_law_guided_candidate_generation_v1_controller"
)
NONLOCAL_LAW_CANDIDATE_GENERATION_CLIENTS = ("fake", "openai")
NONLOCAL_LAW_CANDIDATE_GENERATION_REQUIRED_MODEL_CALLS = 1
NONLOCAL_LAW_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT = 1
NEXT_RECOMMENDED_ACTION = "review_nonlocal_law_candidate_before_ablation"
FAILED_NEXT_RECOMMENDED_ACTION = "review_failed_nonlocal_law_candidate_generation"
SAFETY_METADATA_FAILURE_CLASS = "nonlocal_law_generation_safety_metadata_failure"
SAFETY_GENERATION_ALLOWED_REASON = "generation_allowed_true_or_not_false"
GENERATION_ALLOWED_DIAGNOSTIC_MESSAGE = (
    "The model treated generation_allowed as current-call permission. This field "
    "is a downstream safety/escalation assertion and must be false."
)

NONLOCAL_LAW_CANDIDATE_ARTIFACT_TYPES = (
    "source_authorization_intake_summary",
    "base_candidate_subject",
    "generated_candidate_text",
    "candidate_diff_summary",
    "target_unit_change_report",
    "materiality_validation_report",
    "semantic_validation_report",
    "non_imitation_validation_report",
    "protected_strengths_preservation_report",
    "forbidden_regression_report",
    "post_generation_evidence_plan",
    "authorization_consumption_report",
    "nonlocal_law_candidate_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_guided_candidate_packet",
)

FAILED_NONLOCAL_LAW_CANDIDATE_ARTIFACT_TYPES = (
    "failed_generation_diagnostic",
    "failed_generation_gate_report",
    "nonlocal_law_failed_generation_packet",
)

REQUIRED_AUTHORIZATION_ARTIFACTS = (
    "nonlocal_law_guided_generation_authorization_packet",
    "source_work_order_intake_summary",
    "generation_contract_intake_summary",
    "authorization_decision_record",
    "target_unit_authorization_scope",
    "protected_strengths_and_forbidden_imitation_review",
    "materiality_semantic_validation_readiness_report",
    "post_generation_evidence_plan",
    "model_call_budget_report",
    "generation_lock_transition_report",
    "nonlocal_law_generation_authorization_gate_report",
    "project_health_scope_guard_report",
)

REQUIRED_WORK_ORDER_ARTIFACTS = (
    "nonlocal_law_guided_work_order_packet",
    "selected_nonlocal_intervention_scope",
    "law_guided_pressure_recomposition_map",
    "protected_current_best_strengths",
    "forbidden_rival_imitation_inventory",
    "nonlocal_target_unit_map",
    "future_generation_contract",
    "materiality_and_semantic_validation_plan",
    "ablation_and_reader_eval_plan",
)

PACKET_0063_OBJECT_FIELD = ("table", "dust", "spoon", "saucer", "ring")
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
    "improvement is proven",
    "this improves",
)
FORBIDDEN_PROCESS_CLAIMS = (
    "ablation proves",
    "reader-state evaluation proves",
    "synthesis proves",
    "finalization proves",
)
LAW_THESIS_TERMS = (
    "the law is",
    "first_read_pressure_precedes_explanation_law",
    "this proves that",
    "the thesis is",
)


@dataclass(frozen=True)
class NonlocalLawCandidateGenerationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class NonlocalLawCandidateSubject:
    run_id: str
    authorization_packet_dir: Path
    authorization_packet_id: str
    authorization_packet_artifact_id: str | None
    authorization_payloads: dict[str, dict[str, Any]]
    authorization_artifact_ids: dict[str, str]
    work_order_packet_dir: Path
    work_order_packet_id: str
    work_order_packet_artifact_id: str | None
    work_order_payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    base_candidate_packet_id: str
    base_candidate_packet_dir: Path
    base_candidate_artifact_id: str | None
    base_text: str
    base_text_sha256: str
    authorization_optional_budget_aliases_missing: bool


class NonlocalLawCandidateValidationError(ModelValidationError):
    def __init__(self, validation_report: dict[str, object]) -> None:
        self.validation_report = validation_report
        failures = validation_report.get("validation_failures")
        message = "; ".join(str(item) for item in failures) if isinstance(failures, list) else "validation failed"
        super().__init__(message)


class FakeNonlocalLawGuidedGenerationModelClient:
    provider = "fake"
    model = "fake-nonlocal-law-guided-generation-v1"

    def __init__(
        self,
        mode: str = "valid",
        *,
        provider: str = "fake",
        model: str = "fake-nonlocal-law-guided-generation-v1",
    ) -> None:
        self.mode = mode
        self.provider = provider
        self.model = model

    def generate(self, request: WorkerRequest) -> str:
        prompt = json.loads(request.input_text)
        payload = _valid_fake_payload(prompt)
        if self.mode == "forbidden_rival_material":
            payload["revised_text"] += " A cup waits by the windowsill."
        elif self.mode == "missing_target_unit":
            payload["target_unit_change_report"] = payload["target_unit_change_report"][:-1]
        elif self.mode == "finality":
            payload["finality_claimed"] = True
        elif self.mode == "phase_shift":
            payload["phase_shift_claimed"] = True
        elif self.mode == "rival_defeat":
            payload["strongest_rival_defeated_claimed"] = True
        elif self.mode == "generation_allowed":
            payload["generation_allowed"] = True
        elif self.mode == "abolish_explanation":
            payload["revised_text"] = payload["revised_text"].replace(
                "Only after",
                "Without explanation,",
            )
        elif self.mode == "missing_object_field":
            payload["revised_text"] = "A room holds pressure in silence."
        elif self.mode == "thesis_statement":
            payload["revised_text"] += " The law is that pressure precedes explanation."
        elif self.mode == "unchanged":
            payload["revised_text"] = str(prompt["base_candidate_text"])
        elif self.mode == "invalid_json":
            return "{not valid json"
        return _canonical_json(payload)


def run_nonlocal_law_candidate_generation(
    config: AbiConfig,
    *,
    client_name: str,
    authorization_packet: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = NONLOCAL_LAW_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> NonlocalLawCandidateGenerationResult:
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name not in NONLOCAL_LAW_CANDIDATE_GENERATION_CLIENTS:
        return _refusal(
            message=f"Unsupported nonlocal law-guided candidate client: {client_name}",
            authorization_packet=authorization_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )
    if client_name == "openai":
        if not allow_live_model:
            return _refusal(
                message=(
                    "Nonlocal law-guided candidate OpenAI path refused; pass "
                    "--allow-live-model to opt in explicitly."
                ),
                authorization_packet=authorization_packet,
                client_name=client_name,
                model=configured_model,
            )
        resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        if not resolved_api_key:
            return _refusal(
                message=(
                    "Nonlocal law-guided candidate OpenAI path refused; "
                    f"{OPENAI_API_KEY_ENV} is not set."
                ),
                authorization_packet=authorization_packet,
                client_name=client_name,
                model=configured_model,
            )
        if max_model_calls < NONLOCAL_LAW_CANDIDATE_GENERATION_REQUIRED_MODEL_CALLS:
            return _refusal(
                message=(
                    "Nonlocal law-guided candidate OpenAI path refused; "
                    f"max-model-calls {max_model_calls} is below required budget 1."
                ),
                authorization_packet=authorization_packet,
                client_name=client_name,
                model=configured_model,
            )

    initialize_database(config)
    resolved_packet = _resolve_path(config, authorization_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            message=(
                "Nonlocal law-guided candidate generation refused; authorization "
                f"packet directory not found: {resolved_packet}"
            ),
            authorization_packet=resolved_packet,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
        )

    with connect(config.db_path) as connection:
        try:
            subject = _load_subject(connection, config, resolved_packet)
            _validate_subject_before_generation(connection, subject)
        except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
            return _refusal(
                message=f"Nonlocal law-guided candidate generation refused; {error}",
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )

        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Nonlocal law-guided candidate generation refused; run is "
                    f"not registered: {subject.run_id}"
                ),
                authorization_packet=resolved_packet,
                client_name=client_name,
                model=configured_model if client_name == "openai" else None,
            )
        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_NONLOCAL_LAW_GUIDED_CANDIDATE_GENERATION_ACTIVE_PHASE,
        )

    fixture_only = client_name == "fake"
    model_results: list[ModelDriverResult] = []
    model_call_id: str | None = None
    if client_name == "fake":
        model_payload = _valid_fake_payload(_prompt_packet(subject))
    else:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_guided_candidate"
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
    except NonlocalLawCandidateValidationError as error:
        return _failure_result(
            config=config,
            subject=subject,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_results=model_results,
            message=f"Nonlocal law-guided candidate generation refused; {error}",
            validation_report=error.validation_report,
        )

    packet_dir = (
        packet_dir
        if client_name == "openai"
        else create_packet_dir(
            config.run_dir(subject.run_id) / "nonlocal_law_guided_candidate"
        )
    )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CANDIDATE_GENERATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CANDIDATE_GENERATION_CREATED_BY,
            fixture_only=fixture_only,
            model_call_id=None,
        )
        model_writer = (
            PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=packet_dir,
                lineage_id=NONLOCAL_LAW_CANDIDATE_GENERATION_LINEAGE_ID,
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
            gate_name="nonlocal_law_candidate_gate_report",
            passed=False,
            blocking_defects=list(
                payloads["nonlocal_law_candidate_gate_report"]["unresolved_blockers"]
            ),
            lineage_id=NONLOCAL_LAW_CANDIDATE_GENERATION_LINEAGE_ID,
        )

    return NonlocalLawCandidateGenerationResult(
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
) -> NonlocalLawCandidateSubject:
    auth_envelopes, auth_payloads = _load_required_payloads(
        authorization_packet_dir,
        REQUIRED_AUTHORIZATION_ARTIFACTS,
        "authorization packet",
    )
    auth_packet = auth_payloads["nonlocal_law_guided_generation_authorization_packet"]
    run_id = str(auth_packet.get("run_id") or auth_envelopes[
        "nonlocal_law_guided_generation_authorization_packet"
    ].get("run_id") or "")
    if not run_id:
        raise ValueError("authorization packet missing run_id")
    work_order_dir = _resolve_path(
        config,
        Path(str(auth_packet.get("source_work_order_packet_dir") or "")),
    )
    if not work_order_dir.exists() or not work_order_dir.is_dir():
        raise ValueError("source work-order packet cannot be resolved")
    _work_envelopes, work_payloads = _load_required_payloads(
        work_order_dir,
        REQUIRED_WORK_ORDER_ARTIFACTS,
        "work-order packet",
    )
    base_packet_id = str(
        auth_packet.get("base_candidate_packet_id")
        or auth_packet.get("current_best_candidate_packet_id")
        or EXPECTED_CURRENT_BEST_PACKET_ID
    )
    base_packet_dir = (
        config.run_dir(run_id) / "bounded_macro_recomposition" / base_packet_id
    )
    base_payload, base_artifact_id = _load_base_candidate_payload(
        connection,
        base_packet_dir,
    )
    base_text = str(base_payload.get("text") or "")
    if not base_text.strip():
        raise ValueError("base candidate text is empty")
    auth_packet_artifact = _artifact_for_path(
        connection,
        authorization_packet_dir
        / "nonlocal_law_guided_generation_authorization_packet.json",
    )
    work_packet_artifact = _artifact_for_path(
        connection,
        work_order_dir / "nonlocal_law_guided_work_order_packet.json",
    )
    auth_artifact_ids = _artifact_ids_from_packet(auth_packet)
    work_artifact_ids = _artifact_ids_from_packet(
        work_payloads["nonlocal_law_guided_work_order_packet"]
    )
    parent_ids = _unique(
        [
            auth_packet_artifact.id if auth_packet_artifact else None,
            work_packet_artifact.id if work_packet_artifact else None,
            base_artifact_id,
            *auth_artifact_ids.values(),
            *work_artifact_ids.values(),
        ]
    )
    return NonlocalLawCandidateSubject(
        run_id=run_id,
        authorization_packet_dir=authorization_packet_dir,
        authorization_packet_id=str(auth_packet.get("packet_id") or authorization_packet_dir.name),
        authorization_packet_artifact_id=auth_packet_artifact.id
        if auth_packet_artifact
        else None,
        authorization_payloads=auth_payloads,
        authorization_artifact_ids=auth_artifact_ids,
        work_order_packet_dir=work_order_dir,
        work_order_packet_id=str(
            auth_packet.get("source_work_order_packet_id") or work_order_dir.name
        ),
        work_order_packet_artifact_id=work_packet_artifact.id
        if work_packet_artifact
        else None,
        work_order_payloads=work_payloads,
        source_parent_ids=tuple(parent_ids),
        base_candidate_packet_id=base_packet_id,
        base_candidate_packet_dir=base_packet_dir,
        base_candidate_artifact_id=base_artifact_id,
        base_text=base_text,
        base_text_sha256=str(base_payload.get("text_sha256") or sha256_text(base_text)),
        authorization_optional_budget_aliases_missing=(
            _authorization_optional_budget_aliases_missing(auth_payloads)
        ),
    )


def _validate_subject_before_generation(
    connection: sqlite3.Connection,
    subject: NonlocalLawCandidateSubject,
) -> None:
    auth = subject.authorization_payloads[
        "nonlocal_law_guided_generation_authorization_packet"
    ]
    gate = subject.authorization_payloads["nonlocal_law_generation_authorization_gate_report"]
    contract = subject.work_order_payloads["future_generation_contract"]
    _require_bool(auth, "accepted", True)
    _require_equal(auth, "decision", AUTHORIZATION_DECISION_AUTHORIZE_ONE)
    _require_bool(auth, "generation_authorized", True)
    _require_bool(auth, "next_generation_authorized", True)
    _require_equal(auth, "generation_attempt_budget", 1)
    _require_bool(auth, "authorization_consumed", False)
    _require_bool(auth, "candidate_generated", False)
    _require_equal(auth, "current_best_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID)
    _require_equal(auth, "proof_packet_id", EXPECTED_PROOF_PACKET_ID)
    _require_equal(auth, "reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID)
    _require_equal(auth, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(auth, "selected_strategy_class", SELECTED_NONLOCAL_STRATEGY_CLASS)
    _require_equal(auth, "work_order_kind", NONLOCAL_LAW_GUIDED_WORK_ORDER_KIND)
    _require_equal(auth, "target_scope", NONLOCAL_LAW_TARGET_SCOPE)
    _require_equal(
        _with_contract_fallback(auth, contract),
        "generation_contract_version",
        GENERATION_CONTRACT_VERSION,
    )
    _require_equal(
        _with_contract_fallback(auth, contract),
        "prompt_contract_id",
        PROMPT_CONTRACT_ID,
    )
    _require_equal(
        _with_contract_fallback(auth, contract),
        "materiality_policy_id",
        MATERIALITY_POLICY_ID,
    )
    _require_equal(
        _with_contract_fallback(auth, contract),
        "semantic_validator_id",
        SEMANTIC_VALIDATOR_ID,
    )
    _require_equal(_with_contract_fallback(auth, contract), "schema", FUTURE_SCHEMA_NAME)
    _require_bool(auth, "no_final_claim", True)
    _require_bool(auth, "no_phase_shift_claim", True)
    if gate.get("finalization_eligible") is True:
        raise ValueError("authorization gate report is finalization eligible")
    if not set(NONLOCAL_TARGET_UNIT_IDS) <= set(_string_list(auth.get("target_unit_ids"))):
        raise ValueError("authorization missing required target units")
    if not set(MATERIALITY_REQUIREMENTS) <= set(_string_list(auth.get("materiality_requirements"))):
        raise ValueError("authorization missing materiality requirements")
    if not set(SEMANTIC_VALIDATION_REQUIREMENTS) <= set(
        _string_list(auth.get("semantic_validation_requirements"))
    ):
        raise ValueError("authorization missing semantic validation requirements")
    if _linked_candidate_for_authorization(connection, subject) is not None:
        raise ValueError("existing accepted candidate already consumed this authorization")
    if _has_final_or_phase_claim(subject.authorization_payloads) or _has_final_or_phase_claim(
        subject.work_order_payloads
    ):
        raise ValueError("authorization or work order carries finality or phase-shift claim")


def _run_live_generation_model(
    *,
    config: AbiConfig,
    subject: NonlocalLawCandidateSubject,
    packet_dir: Path,
    model_client: ModelClient,
    parent_ids: list[str],
) -> ModelDriverResult:
    return ModelDriver(config=config, client=model_client).run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.NONLOCAL_LAW_GUIDED_GENERATOR,
            prompt_contract_id=PROMPT_CONTRACT_ID,
            schema=NONLOCAL_LAW_GUIDED_GENERATION_SCHEMA,
            input_text=_canonical_json(_prompt_packet(subject)),
            input_artifact_ids=parent_ids,
            input_packet_path=str(subject.authorization_packet_dir),
            lineage_id=NONLOCAL_LAW_CANDIDATE_GENERATION_LINEAGE_ID,
            parent_ids=parent_ids,
            fixture_only=False,
            output_dir=str(packet_dir),
            register_parsed_artifact=False,
        )
    )


def _prompt_packet(subject: NonlocalLawCandidateSubject) -> dict[str, object]:
    auth = subject.authorization_payloads[
        "nonlocal_law_guided_generation_authorization_packet"
    ]
    work_order = subject.work_order_payloads["nonlocal_law_guided_work_order_packet"]
    return {
        "task": "generate one bounded nonlocal law-guided candidate",
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": FUTURE_SCHEMA_NAME,
        "authorization_packet_id": subject.authorization_packet_id,
        "work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "base_candidate_text": subject.base_text,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "target_scope": NONLOCAL_LAW_TARGET_SCOPE,
        "target_unit_ids": list(auth["target_unit_ids"]),
        "materiality_requirements": list(auth["materiality_requirements"]),
        "semantic_validation_requirements": list(auth["semantic_validation_requirements"]),
        "forbidden_rival_objects_or_sequence": list(
            auth["forbidden_rival_objects_or_sequence"]
        ),
        "forbidden_rival_imitation_modes": list(
            auth["forbidden_rival_imitation_modes"]
        ),
        "forbidden_regressions": list(auth["forbidden_regressions"]),
        "ablation_controls": list(auth["ablation_controls"]),
        "reader_state_focus": list(auth["reader_state_focus"]),
        "work_order_summary": {
            "recomposition_principle": work_order["recomposition_principle"],
            "explanation_policy": work_order["explanation_policy"],
            "affected_regions": list(work_order["affected_regions"]),
            "protected_regions": list(work_order["protected_regions"]),
        },
        "model_must_not": [
            "copy rival scenes, diction, cadence, causal plot, or object inventory",
            "claim improvement, finality, phase shift, or strongest-rival defeat",
            "run or claim ablation, reader-state evaluation, synthesis, or finalization",
            "turn the law into an explicit thesis statement",
        ],
    }


def _validate_generated_payload(
    subject: NonlocalLawCandidateSubject,
    payload: dict[str, object],
) -> dict[str, object]:
    text = str(payload.get("revised_text") or "")
    failures: list[str] = []
    lower = text.lower()
    if _normalize_text(text) == _normalize_text(subject.base_text):
        failures.append("revised_text is unchanged from packet_0063")
    forbidden_hits = _forbidden_rival_hits(text)
    if forbidden_hits:
        failures.append("revised_text contains forbidden rival material: " + ", ".join(forbidden_hits))
    leakage_hits = [term for term in CLAIM_LEAKAGE_TERMS if term in lower]
    if leakage_hits:
        failures.append("revised_text contains finality/improvement/rival-defeat claim leakage: " + ", ".join(leakage_hits))
    process_hits = [term for term in FORBIDDEN_PROCESS_CLAIMS if term in lower]
    if process_hits:
        failures.append("revised_text includes post-generation evidence claims: " + ", ".join(process_hits))
    law_hits = [term for term in LAW_THESIS_TERMS if term in lower]
    if law_hits:
        failures.append("revised_text turns the law into a thesis statement")
    if "domestic grime" in lower or "generic grime" in lower:
        failures.append("revised_text substitutes generic domestic grime for law")
    if any(value is True for value in (
        payload.get("generation_allowed"),
        payload.get("finality_claimed"),
        payload.get("phase_shift_claimed"),
        payload.get("strongest_rival_defeated_claimed"),
    )):
        failures.append("model output claimed generation/finality/phase/rival defeat")
    if _explanation_abolished_or_unearned(text):
        failures.append("explanation is abolished rather than delayed or earned")
    missing_objects = [
        term for term in PACKET_0063_OBJECT_FIELD if not _contains_word(lower, term)
    ]
    if missing_objects:
        failures.append("packet_0063 object field absent: " + ", ".join(missing_objects))
    if "return" not in lower and "returns" not in lower:
        failures.append("reread return is not prepared in revised_text")

    target_report = list(payload.get("target_unit_change_report", []))
    reported_units = {
        str(item.get("target_unit_id"))
        for item in target_report
        if isinstance(item, dict)
    }
    missing_units = [unit_id for unit_id in NONLOCAL_TARGET_UNIT_IDS if unit_id not in reported_units]
    if missing_units:
        failures.append("target_unit_change_report missing required units: " + ", ".join(missing_units))
    for item in target_report:
        if not isinstance(item, dict):
            continue
        if item.get("materiality_satisfied") is not True:
            failures.append(f"materiality not satisfied for {item.get('target_unit_id')}")
        if item.get("semantic_satisfied") is not True:
            failures.append(f"semantic not satisfied for {item.get('target_unit_id')}")

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
    non_imitation = payload.get("non_imitation_report")
    if not isinstance(non_imitation, dict) or non_imitation.get("passed") is not True:
        failures.append("non_imitation_report does not explicitly pass")
    protected = payload.get("protected_strengths_report")
    if not isinstance(protected, dict) or protected.get("preserved") is not True:
        failures.append("protected strengths are not explicitly preserved")
    forbidden = payload.get("forbidden_regression_report")
    if not isinstance(forbidden, dict) or forbidden.get("passed") is not True:
        failures.append("forbidden_regression_report does not explicitly pass")
    acknowledgment = payload.get("post_generation_evidence_plan_acknowledgment")
    if not isinstance(acknowledgment, dict) or any(
        acknowledgment.get(key) is not True
        for key in (
            "ablation_required",
            "reader_state_eval_required",
            "synthesis_required",
            "strongest_rival_remains_blocking",
        )
    ):
        failures.append("post-generation evidence plan acknowledgment is incomplete")

    report = {
        "validation_passed": not failures,
        "validation_failures": failures,
        "target_units_reported": sorted(reported_units),
        "missing_target_units": missing_units,
        "materiality_passed": materiality_report["passed"],
        "semantic_passed": semantic_report["passed"],
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
        raise NonlocalLawCandidateValidationError(report)
    return report


def _write_candidate_artifacts(
    *,
    writer: PacketWriter,
    model_writer: PacketWriter | None,
    subject: NonlocalLawCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
    model_results: list[ModelDriverResult],
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    payloads["source_authorization_intake_summary"] = _build_source_intake(
        subject,
        packet_dir,
        client_name,
        model,
    )
    artifacts["source_authorization_intake_summary"] = writer.write_artifact(
        "source_authorization_intake_summary",
        payloads["source_authorization_intake_summary"],
        parent_ids=list(subject.source_parent_ids),
    )

    payloads["base_candidate_subject"] = _build_base_subject(subject)
    artifacts["base_candidate_subject"] = writer.write_artifact(
        "base_candidate_subject",
        payloads["base_candidate_subject"],
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
        parent_ids=[artifacts["base_candidate_subject"].id],
    )

    payloads["candidate_diff_summary"] = _build_diff_summary(subject, model_payload)
    artifacts["candidate_diff_summary"] = writer.write_artifact(
        "candidate_diff_summary",
        payloads["candidate_diff_summary"],
        parent_ids=[artifacts["generated_candidate_text"].id],
    )

    payloads["target_unit_change_report"] = _build_target_report(model_payload)
    artifacts["target_unit_change_report"] = _write_artifact(
        writer=writer,
        model_writer=model_writer,
        artifact_type="target_unit_change_report",
        payload=payloads["target_unit_change_report"],
        parent_ids=[artifacts["generated_candidate_text"].id],
    )

    payloads["materiality_validation_report"] = _build_requirement_report(
        subject,
        model_payload,
        validation_report,
        "materiality",
    )
    artifacts["materiality_validation_report"] = _write_artifact(
        writer=writer,
        model_writer=model_writer,
        artifact_type="materiality_validation_report",
        payload=payloads["materiality_validation_report"],
        parent_ids=[artifacts["target_unit_change_report"].id],
    )

    payloads["semantic_validation_report"] = _build_requirement_report(
        subject,
        model_payload,
        validation_report,
        "semantic",
    )
    artifacts["semantic_validation_report"] = _write_artifact(
        writer=writer,
        model_writer=model_writer,
        artifact_type="semantic_validation_report",
        payload=payloads["semantic_validation_report"],
        parent_ids=[artifacts["materiality_validation_report"].id],
    )

    payloads["non_imitation_validation_report"] = _build_non_imitation_report(
        model_payload,
        validation_report,
    )
    artifacts["non_imitation_validation_report"] = _write_artifact(
        writer=writer,
        model_writer=model_writer,
        artifact_type="non_imitation_validation_report",
        payload=payloads["non_imitation_validation_report"],
        parent_ids=[artifacts["semantic_validation_report"].id],
    )

    payloads["protected_strengths_preservation_report"] = _build_protected_report(
        model_payload
    )
    artifacts["protected_strengths_preservation_report"] = _write_artifact(
        writer=writer,
        model_writer=model_writer,
        artifact_type="protected_strengths_preservation_report",
        payload=payloads["protected_strengths_preservation_report"],
        parent_ids=[artifacts["non_imitation_validation_report"].id],
    )

    payloads["forbidden_regression_report"] = _build_forbidden_regression_report(
        model_payload
    )
    artifacts["forbidden_regression_report"] = _write_artifact(
        writer=writer,
        model_writer=model_writer,
        artifact_type="forbidden_regression_report",
        payload=payloads["forbidden_regression_report"],
        parent_ids=[artifacts["protected_strengths_preservation_report"].id],
    )

    payloads["post_generation_evidence_plan"] = _build_evidence_plan(
        subject,
        model_payload,
    )
    artifacts["post_generation_evidence_plan"] = writer.write_artifact(
        "post_generation_evidence_plan",
        payloads["post_generation_evidence_plan"],
        parent_ids=[artifacts["forbidden_regression_report"].id],
    )

    payloads["authorization_consumption_report"] = _build_consumption_report(
        subject,
        client_name,
        model_results,
    )
    artifacts["authorization_consumption_report"] = writer.write_artifact(
        "authorization_consumption_report",
        payloads["authorization_consumption_report"],
        parent_ids=[artifacts["post_generation_evidence_plan"].id],
    )

    payloads["nonlocal_law_candidate_gate_report"] = _build_gate_report(
        subject,
        model_results,
    )
    artifacts["nonlocal_law_candidate_gate_report"] = writer.write_artifact(
        "nonlocal_law_candidate_gate_report",
        payloads["nonlocal_law_candidate_gate_report"],
        parent_ids=[artifacts["authorization_consumption_report"].id],
    )

    payloads["project_health_scope_guard_report"] = _build_health_report(
        subject,
        validation_report,
        model_results,
    )
    artifacts["project_health_scope_guard_report"] = writer.write_artifact(
        "project_health_scope_guard_report",
        payloads["project_health_scope_guard_report"],
        parent_ids=[artifacts["nonlocal_law_candidate_gate_report"].id],
    )

    payloads["nonlocal_law_guided_candidate_packet"] = _build_packet_summary(
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
    artifacts["nonlocal_law_guided_candidate_packet"] = writer.write_artifact(
        "nonlocal_law_guided_candidate_packet",
        payloads["nonlocal_law_guided_candidate_packet"],
        parent_ids=[
            artifact.id
            for artifact_type, artifact in artifacts.items()
            if artifact_type != "nonlocal_law_guided_candidate_packet"
        ],
    )
    return payloads, artifacts


def _build_source_intake(
    subject: NonlocalLawCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
) -> dict[str, object]:
    auth = subject.authorization_payloads[
        "nonlocal_law_guided_generation_authorization_packet"
    ]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "model": model,
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_authorization_packet_dir": str(subject.authorization_packet_dir),
        "source_work_order_packet_id": subject.work_order_packet_id,
        "source_strategy_packet_id": auth.get("source_strategy_packet_id"),
        "source_diagnostic_packet_id": auth.get("source_diagnostic_packet_id"),
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "current_best_candidate_packet_id": auth.get("current_best_candidate_packet_id"),
        "proof_packet_id": auth.get("proof_packet_id"),
        "reader_state_packet_id": auth.get("reader_state_packet_id"),
        "law_id": auth.get("law_id"),
        "authorization_optional_budget_aliases_missing": (
            subject.authorization_optional_budget_aliases_missing
        ),
        "consumed_authorization_top_level_budget_successfully": True,
        "generation_authorized": True,
        "authorization_consumed": True,
        "candidate_generated": True,
        "model_calls": 1 if client_name == "openai" else 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_authorization_intake_summary_v1_controller",
    }


def _build_base_subject(subject: NonlocalLawCandidateSubject) -> dict[str, object]:
    return {
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "base_candidate_packet_dir": str(subject.base_candidate_packet_dir),
        "base_candidate_artifact_id": subject.base_candidate_artifact_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "base_candidate_word_count": len(subject.base_text.split()),
        "current_best_candidate_packet_id": subject.base_candidate_packet_id,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "base_candidate_subject_v1_controller",
    }


def _build_generated_text(
    subject: NonlocalLawCandidateSubject,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
    model_call_id: str | None,
    client_name: str,
) -> dict[str, object]:
    text = str(model_payload["revised_text"])
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "current_best_candidate_packet_id": subject.base_candidate_packet_id,
        "text": text,
        "text_sha256": sha256_text(text),
        "base_text_sha256": subject.base_text_sha256,
        "word_count": len(text.split()),
        "model_call_id": model_call_id,
        "fixture_only": client_name == "fake",
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
    subject: NonlocalLawCandidateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    text = str(model_payload["revised_text"])
    base_words = _word_set(subject.base_text)
    revised_words = _word_set(text)
    return {
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "base_text_sha256": subject.base_text_sha256,
        "candidate_text_sha256": sha256_text(text),
        "changed": _normalize_text(text) != _normalize_text(subject.base_text),
        "added_unique_words": sorted(revised_words - base_words)[:50],
        "removed_unique_words": sorted(base_words - revised_words)[:50],
        "revision_summary": model_payload["revision_summary"],
        "law_application_summary": model_payload["law_application_summary"],
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "candidate_diff_summary_v1_controller",
    }


def _build_target_report(model_payload: dict[str, object]) -> dict[str, object]:
    target_units = list(NONLOCAL_TARGET_UNIT_IDS)
    return {
        "target_unit_ids": target_units,
        "target_units_reported": target_units,
        "target_unit_count": len(target_units),
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


def _build_requirement_report(
    subject: NonlocalLawCandidateSubject,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
    report_kind: str,
) -> dict[str, object]:
    if report_kind == "materiality":
        required = list(MATERIALITY_REQUIREMENTS)
        report = list(model_payload["materiality_self_report"])
        passed_key = "materiality_passed"
    else:
        required = list(SEMANTIC_VALIDATION_REQUIREMENTS)
        report = list(model_payload["semantic_self_report"])
        passed_key = "semantic_passed"
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        "required_requirements": required,
        "self_report": report,
        "passed": validation_report[passed_key],
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": f"{report_kind}_validation_report_v1_controller",
    }


def _build_non_imitation_report(
    model_payload: dict[str, object],
    validation_report: dict[str, object],
) -> dict[str, object]:
    return {
        **dict(model_payload["non_imitation_report"]),
        "forbidden_rival_objects_or_sequence": list(FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE),
        "forbidden_rival_imitation_modes": list(FORBIDDEN_RIVAL_IMITATION_MODES),
        "forbidden_rival_hits": list(validation_report["forbidden_rival_hits"]),
        "passed": validation_report["non_imitation_passed"],
        "strongest_rival_defeated_claimed": False,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "non_imitation_validation_report_v1_controller",
    }


def _build_protected_report(model_payload: dict[str, object]) -> dict[str, object]:
    return {
        **dict(model_payload["protected_strengths_report"]),
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "protected_strengths_preservation_report_v1_controller",
    }


def _build_forbidden_regression_report(model_payload: dict[str, object]) -> dict[str, object]:
    return {
        **dict(model_payload["forbidden_regression_report"]),
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "forbidden_regression_report_v1_controller",
    }


def _build_evidence_plan(
    subject: NonlocalLawCandidateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    acknowledgment = dict(model_payload["post_generation_evidence_plan_acknowledgment"])
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        **acknowledgment,
        "ablation_controls": list(ABLATION_CONTROLS),
        "reader_state_focus": list(READER_STATE_FOCUS),
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "candidate_generated": True,
        "authorization_consumed": True,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "post_generation_evidence_plan_v1_controller",
    }


def _build_consumption_report(
    subject: NonlocalLawCandidateSubject,
    client_name: str,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    return {
        "source_authorization_packet_id": subject.authorization_packet_id,
        "authorization_consumed": True,
        "candidate_generated": True,
        "generation_attempt_index": 1,
        "generation_attempt_budget": 1,
        "remaining_generation_attempt_budget": 0,
        "client": client_name,
        "model_calls": len(model_results),
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "authorization_consumption_report_v1_controller",
    }


def _build_gate_report(
    subject: NonlocalLawCandidateSubject,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    gate_results = [
        _gate_result("authorization_consumed", True),
        _gate_result("candidate_generated", True),
        _gate_result("target_units_reported", True),
        _gate_result("materiality_validation_passed", True),
        _gate_result("semantic_validation_passed", True),
        _gate_result("non_imitation_validation_passed", True),
        _gate_result("protected_strengths_preserved", True),
        _gate_result("post_generation_evidence_pending", False, ["ablation, reader-state evaluation, and synthesis remain pending"], record=False),
        _gate_result("finalization_eligible", False, ["candidate generation is not finalization evidence"], record=False),
    ]
    return {
        "passed": False,
        "eligible": False,
        "source_authorization_packet_id": subject.authorization_packet_id,
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
        "worker": "nonlocal_law_candidate_gate_report_v1_controller",
    }


def _build_health_report(
    subject: NonlocalLawCandidateSubject,
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
    ]
    passed = all(bool(check["passed"]) for check in checks)
    return {
        "checks": checks,
        "passed": passed,
        "project_health_scope_guard_passed": passed,
        "source_chain_coherent": True,
        "source_authorization_packet_id": subject.authorization_packet_id,
        "candidate_generated": True,
        "authorization_consumed": True,
        "model_calls": len(model_results),
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawCandidateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    model_payload: dict[str, object],
    validation_report: dict[str, object],
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    auth = subject.authorization_payloads[
        "nonlocal_law_guided_generation_authorization_packet"
    ]
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_CANDIDATE_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_guided_candidate_packet",
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
        "source_authorization_packet_id": subject.authorization_packet_id,
        "source_work_order_packet_id": subject.work_order_packet_id,
        "source_strategy_packet_id": auth.get("source_strategy_packet_id"),
        "source_diagnostic_packet_id": auth.get("source_diagnostic_packet_id"),
        "base_candidate_packet_id": subject.base_candidate_packet_id,
        "current_best_candidate_packet_id": subject.base_candidate_packet_id,
        "proof_packet_id": auth.get("proof_packet_id"),
        "reader_state_packet_id": auth.get("reader_state_packet_id"),
        "law_id": auth.get("law_id"),
        "selected_strategy_class": auth.get("selected_strategy_class"),
        "work_order_kind": auth.get("work_order_kind"),
        "target_scope": auth.get("target_scope"),
        "generation_contract_version": GENERATION_CONTRACT_VERSION,
        "materiality_policy_id": MATERIALITY_POLICY_ID,
        "semantic_validator_id": SEMANTIC_VALIDATOR_ID,
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": FUTURE_SCHEMA_NAME,
        "authorization_consumed": True,
        "generation_attempt_index": 1,
        "model_calls": len(model_results),
        "materiality_requirements": list(MATERIALITY_REQUIREMENTS),
        "semantic_validation_requirements": list(SEMANTIC_VALIDATION_REQUIREMENTS),
        "target_unit_ids": list(NONLOCAL_TARGET_UNIT_IDS),
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
            "nonlocal_law_guided_candidate_packet",
        ],
        "gate_report": payloads["nonlocal_law_candidate_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "nonlocal_law_guided_candidate_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_guided_candidate_packet"]
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
    subject: NonlocalLawCandidateSubject,
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
    message: str,
    validation_report: dict[str, object],
) -> NonlocalLawCandidateGenerationResult:
    with connect(config.db_path) as connection:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_guided_candidate_failed_generation"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CANDIDATE_GENERATION_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CANDIDATE_GENERATION_CREATED_BY,
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
            "source_authorization_packet_id": subject.authorization_packet_id,
            "source_work_order_packet_id": subject.work_order_packet_id,
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
            "passed": False,
            "eligible": False,
            "source_authorization_packet_id": subject.authorization_packet_id,
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
            required_artifact_types=FAILED_NONLOCAL_LAW_CANDIDATE_ARTIFACT_TYPES,
            produced_artifact_types=list(artifacts),
            packet_artifact_type="nonlocal_law_failed_generation_packet",
        )
        payloads["nonlocal_law_failed_generation_packet"] = {
            "accepted": False,
            "refused": True,
            "message": message,
            **failure_surface,
            "packet_id": packet_dir.name,
            "packet_dir": str(packet_dir),
            "source_authorization_packet_id": subject.authorization_packet_id,
            "source_work_order_packet_id": subject.work_order_packet_id,
            "authorization_consumed": False,
            "candidate_generated": False,
            "model_calls": len(model_results),
            "counts": {**counts, "model_calls": len(model_results)},
            "artifact_ids": {
                artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
            },
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "next_recommended_action": FAILED_NEXT_RECOMMENDED_ACTION,
            "worker": "nonlocal_law_failed_generation_packet_v1_controller",
        }
        artifacts["nonlocal_law_failed_generation_packet"] = writer.write_artifact(
            "nonlocal_law_failed_generation_packet",
            payloads["nonlocal_law_failed_generation_packet"],
            parent_ids=[
                artifacts["failed_generation_diagnostic"].id,
                artifacts["failed_generation_gate_report"].id,
            ],
        )
    return NonlocalLawCandidateGenerationResult(
        exit_code=1,
        payload={
            **payloads["nonlocal_law_failed_generation_packet"],
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
            latest_result.model_call.status
            if latest_result is not None
            else None
        )
    )
    observation = _model_output_observation(output_payload)
    if _is_generation_allowed_failure(validation_failures, output_payload):
        failure_class = SAFETY_METADATA_FAILURE_CLASS
        failure_reason = SAFETY_GENERATION_ALLOWED_REASON
        diagnostic_message = GENERATION_ALLOWED_DIAGNOSTIC_MESSAGE
    else:
        failure_class = "nonlocal_law_generation_validation_failure"
        failure_reason = (
            "structured_output_validation_failed"
            if model_call_status == MODEL_CALL_VALIDATION_FAILED
            else "controller_validation_failed"
        )
        diagnostic_message = "Nonlocal law-guided candidate generation failed validation."
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
    return {
        "model_output_keys": sorted(output_payload),
        "generation_allowed": output_payload.get("generation_allowed"),
        "finality_claimed": output_payload.get("finality_claimed"),
        "phase_shift_claimed": output_payload.get("phase_shift_claimed"),
        "strongest_rival_defeated_claimed": output_payload.get(
            "strongest_rival_defeated_claimed"
        ),
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
        "validation_failures": [model_result.model_call.error_message or model_result.model_call.status],
        "model_call_status": model_result.model_call.status,
    }
    report.update(_model_output_observation(_model_output_payload_for_result(model_result)))
    return report


def _model_failure_message(result: ModelDriverResult) -> str:
    return (
        "Nonlocal law-guided candidate generation refused; model call "
        f"{result.model_call.status}: {result.model_call.error_message or 'no parsed output'}"
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
    path = packet_dir / "macro_recomposed_candidate_text.json"
    if not path.exists():
        raise ValueError("base candidate macro_recomposed_candidate_text cannot be loaded")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        raise ValueError("base candidate text artifact is malformed")
    artifact = _artifact_for_path(connection, path)
    return payload, artifact.id if artifact else None


def _linked_candidate_for_authorization(
    connection: sqlite3.Connection,
    subject: NonlocalLawCandidateSubject,
) -> ArtifactRecord | None:
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type not in {
            "nonlocal_law_guided_candidate_packet",
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


def _authorization_optional_budget_aliases_missing(
    payloads: dict[str, dict[str, Any]],
) -> bool:
    budget = payloads.get("model_call_budget_report", {})
    transition = payloads.get("generation_lock_transition_report", {})
    return (
        budget.get("model_call_budget") is None
        or budget.get("budget_consumed") is None
        or transition.get("generation_lock_transition") is None
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


def _explanation_abolished_or_unearned(text: str) -> bool:
    lower = text.lower()
    if "without explanation" in lower or "no explanation" in lower or "abolish" in lower:
        return True
    if "explanation" not in lower:
        return True
    return not any(term in lower for term in ("only after", "earned", "until", "embedded", "delayed"))


def _contains_word(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower()))


def _valid_fake_payload(prompt: dict[str, object]) -> dict[str, object]:
    target_units = [str(unit) for unit in prompt["target_unit_ids"]]
    materiality = [str(item) for item in prompt["materiality_requirements"]]
    semantic = [str(item) for item in prompt["semantic_validation_requirements"]]
    revised_text = (
        "The table is still there in the morning. Dust has moved into the line "
        "where the night air pressed against the leg, and the spoon rests close "
        "enough to the saucer that their contact has left a faint ring in the "
        "powder. The mark is small, but it has already changed the surface before "
        "anyone tries to say what it means.\n\n"
        "In the middle of the room, each object answers the pressure of another. "
        "The table holds the dust; the dust shows where the spoon shifted; the "
        "spoon leans against the saucer; the saucer keeps the ring as a border "
        "that the morning cannot smooth away. Only after these crossings have "
        "settled does explanation become possible, and even then it arrives as "
        "something earned by the objects rather than imposed over them.\n\n"
        "When the room returns to its first sentence, it is not reset. The same "
        "table is there, but the first look now carries the later pressure inside "
        "it: dust, spoon, saucer, and ring have made the morning answer to what "
        "the surface kept."
    )
    return {
        "revised_text": revised_text,
        "revision_summary": (
            "Redistributed pressure across opening, middle object-event sequence, "
            "and return while preserving packet_0063's object field."
        ),
        "law_application_summary": (
            "Object consequence accumulates before explanation, and explanation "
            "is delayed until the table, dust, spoon, saucer, and ring have made "
            "their relations visible."
        ),
        "target_unit_change_report": [
            {
                "target_unit_id": unit_id,
                "change_summary": f"{unit_id} is addressed through object-event pressure.",
                "materiality_satisfied": True,
                "semantic_satisfied": True,
            }
            for unit_id in target_units
        ],
        "materiality_self_report": [
            {
                "requirement": requirement,
                "satisfied": True,
                "evidence": "The revised text materially redistributes object pressure.",
            }
            for requirement in materiality
        ],
        "semantic_self_report": [
            {
                "requirement": requirement,
                "satisfied": True,
                "evidence": "The revised text preserves the required semantic guard.",
            }
            for requirement in semantic
        ],
        "non_imitation_report": {
            "passed": True,
            "evidence": "No rival object sequence, scene structure, cadence, or causal plot is used.",
            "forbidden_material_absent": list(FORBIDDEN_RIVAL_OBJECTS_OR_SEQUENCE),
        },
        "protected_strengths_report": {
            "preserved": True,
            "evidence": "Table, dust, spoon, saucer, ring, return pressure, and no outside answer remain active.",
            "protected_strengths": [
                "packet_0063 object field",
                "object/tactile pressure",
                "proof/no-answer carry",
            ],
        },
        "forbidden_regression_report": {
            "passed": True,
            "evidence": "The revision avoids local patching, generic vividness, explanation deletion, and rival defeat claims.",
            "avoided_regressions": [
                "generic domestic grime as replacement for law",
                "local patching instead of nonlocal pressure redistribution",
                "deleting explanation rather than earning it",
                "claiming strongest-rival defeat",
            ],
        },
        "post_generation_evidence_plan_acknowledgment": {
            "ablation_required": True,
            "reader_state_eval_required": True,
            "synthesis_required": True,
            "strongest_rival_remains_blocking": True,
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
) -> NonlocalLawCandidateGenerationResult:
    return NonlocalLawCandidateGenerationResult(
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
            "current_best_candidate_packet_id": None,
            "base_candidate_packet_id": None,
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
            "next_recommended_action": "review_refusal_before_generation",
        },
    )


def _require_equal(payload: dict[str, Any], field_name: str, expected: object) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _with_contract_fallback(
    authorization_payload: dict[str, Any],
    contract_payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(authorization_payload)
    for field_name in (
        "generation_contract_version",
        "prompt_contract_id",
        "materiality_policy_id",
        "semantic_validator_id",
        "schema",
    ):
        if merged.get(field_name) is None and contract_payload.get(field_name) is not None:
            merged[field_name] = contract_payload[field_name]
    return merged


def _require_bool(payload: dict[str, Any], field_name: str, expected: bool) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(f"{field_name} must be {str(expected).lower()}")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _has_final_or_phase_claim(payloads: dict[str, dict[str, Any]]) -> bool:
    return any(_payload_has_final_or_phase_claim(payload) for payload in payloads.values())


def _payload_has_final_or_phase_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"finalization_eligible", "final_artifact", "final_claim"}:
                if item is True:
                    return True
            if key in {
                "phase_shift_claim",
                "strongest_rival_defeated",
                "strongest_rival_defeat_claim",
            }:
                if item is True:
                    return True
            if key in {"no_final_claim", "no_phase_shift_claim"}:
                if item is False:
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
