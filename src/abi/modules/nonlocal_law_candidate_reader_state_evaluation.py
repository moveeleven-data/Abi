"""Reader-state evaluation for accepted nonlocal law-guided candidates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_calls import link_model_call_parsed_artifact
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    ModelValidationError,
    NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA,
    WorkerRole,
)
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
from abi.modules.nonlocal_law_candidate_ablation import (
    ABLATION_CONTROL_IDS,
    CANDIDATE_REVIEW_RISKS,
    LAW_BEARING_SPANS,
    NONLOCAL_LAW_CANDIDATE_ABLATION_ARTIFACT_TYPES,
)
from abi.modules.nonlocal_law_guided_work_order import NONLOCAL_LAW_TARGET_SCOPE
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


NONLOCAL_LAW_CANDIDATE_READER_STATE_LINEAGE_ID = (
    "nonlocal_law_candidate_reader_state_evaluation_v1"
)
NONLOCAL_LAW_CANDIDATE_READER_STATE_CREATED_BY = (
    "nonlocal_law_candidate_reader_state_evaluation_v1_controller"
)
NONLOCAL_LAW_CANDIDATE_READER_STATE_CLIENTS = ("fake", "openai")
NONLOCAL_LAW_CANDIDATE_READER_STATE_REQUIRED_MODEL_CALLS = 1
NONLOCAL_LAW_CANDIDATE_READER_STATE_MAX_MODEL_CALLS_DEFAULT = 1
PROMPT_CONTRACT_ID = "autonomous.nonlocal_law_candidate_reader_state_evaluation.v1"
NEXT_RECOMMENDED_ACTION = (
    "review_nonlocal_law_reader_state_evaluation_before_synthesis"
)
FAILED_NEXT_RECOMMENDED_ACTION = (
    "review_failed_nonlocal_law_candidate_reader_state_evaluation"
)

NONLOCAL_LAW_CANDIDATE_READER_STATE_ARTIFACT_TYPES = (
    "source_ablation_intake_summary",
    "candidate_reader_state_subject",
    "base_candidate_reader_state_subject",
    "ablation_control_reader_state_matrix",
    "first_pass_pressure_before_explanation_report",
    "object_event_consequence_reader_state_report",
    "explanation_earned_not_abolished_report",
    "reread_return_preparation_report",
    "non_imitation_reader_signal_report",
    "candidate_review_risk_probe_report",
    "candidate_vs_packet_0063_reader_state_comparison",
    "strongest_rival_pressure_status_report",
    "synthesis_readiness_report",
    "nonlocal_law_reader_state_gate_report",
    "project_health_scope_guard_report",
    "nonlocal_law_candidate_reader_state_evaluation_packet",
)

FAILED_NONLOCAL_LAW_CANDIDATE_READER_STATE_ARTIFACT_TYPES = (
    "failed_reader_state_evaluation_diagnostic",
    "failed_reader_state_evaluation_gate_report",
    "nonlocal_law_candidate_reader_state_failed_evaluation_packet",
)

FIRST_READ_PRESSURE_RESULT = "improved"
OBJECT_EVENT_CONSEQUENCE_RESULT = "improved"
EXPLANATION_TIMING_RESULT = "improved"
REREAD_RETURN_RESULT = "mixed_requires_synthesis"
NON_IMITATION_RESULT = "passed"
STRONGEST_RIVAL_PRESSURE_RESULT = "narrowed_but_blocking"
OVERALL_READER_STATE_RESULT = "mixed_requires_synthesis"
RISK_IDS = tuple(str(risk["risk_id"]) for risk in CANDIDATE_REVIEW_RISKS)


@dataclass(frozen=True)
class NonlocalLawCandidateReaderStateEvaluationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class NonlocalLawCandidateReaderStateSubject:
    run_id: str
    ablation_packet_dir: Path
    ablation_packet_id: str
    ablation_packet_artifact_id: str | None
    ablation_payloads: dict[str, dict[str, Any]]
    ablation_artifact_ids: dict[str, str]
    source_parent_ids: tuple[str, ...]
    source_candidate_packet_dir: Path
    source_candidate_payloads: dict[str, dict[str, Any]]
    source_candidate_artifact_ids: dict[str, str]
    candidate_text: str
    candidate_text_sha256: str
    candidate_word_count: int
    base_candidate_packet_dir: Path
    base_candidate_text: str
    base_candidate_text_sha256: str
    base_subject_hash_missing: bool


@dataclass(frozen=True)
class ExistingReaderStateEvaluation:
    artifact: ArtifactRecord
    payload: dict[str, Any]
    packet_id: str
    client: str
    model_backed: bool
    provisional: bool
    usable_for_synthesis: bool


class FakeNonlocalLawCandidateReaderStateModelClient:
    provider = "fake"
    model = "fake-nonlocal-law-candidate-reader-state-v1"

    def __init__(
        self,
        mode: str = "valid",
        *,
        provider: str = "fake",
        model: str = "fake-nonlocal-law-candidate-reader-state-v1",
    ) -> None:
        self.mode = mode
        self.provider = provider
        self.model = model

    def generate(self, request: WorkerRequest) -> str:
        prompt = json.loads(request.input_text)
        payload = _valid_model_payload(prompt)
        if self.mode == "finality":
            payload["finality_claimed"] = True
        elif self.mode == "synthesis_authorized":
            payload["synthesis_authorized"] = True
        elif self.mode == "rival_defeat":
            payload["strongest_rival_defeated_claimed"] = True
        elif self.mode == "missing_control":
            payload["ablation_control_reader_state_matrix"] = (
                payload["ablation_control_reader_state_matrix"][:-1]
            )
        elif self.mode == "invalid_json":
            return "{not valid json"
        return _canonical_json(payload)


def run_nonlocal_law_candidate_reader_state_evaluation(
    config: AbiConfig,
    *,
    client_name: str,
    ablation_packet: Path | str,
    operator_reviewed: bool = False,
    allow_live_model: bool = False,
    max_model_calls: int = NONLOCAL_LAW_CANDIDATE_READER_STATE_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> NonlocalLawCandidateReaderStateEvaluationResult:
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name not in NONLOCAL_LAW_CANDIDATE_READER_STATE_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=f"Unsupported nonlocal law reader-state client: {client_name}",
        )
    if not operator_reviewed:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Nonlocal law candidate reader-state evaluation refused; pass "
                "--operator-reviewed after reviewing the ablation packet."
            ),
        )
    if max_model_calls < 0:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Nonlocal law candidate reader-state evaluation refused; "
                "max-model-calls must be non-negative."
            ),
        )
    if client_name == "openai" and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Nonlocal law candidate reader-state evaluation refused; pass "
                "--allow-live-model to opt in explicitly."
            ),
        )
    resolved_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == "openai" and not resolved_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Nonlocal law candidate reader-state evaluation refused; "
                f"{OPENAI_API_KEY_ENV} is not set."
            ),
        )
    if (
        client_name == "openai"
        and max_model_calls < NONLOCAL_LAW_CANDIDATE_READER_STATE_REQUIRED_MODEL_CALLS
    ):
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=ablation_packet,
            message=(
                "Nonlocal law candidate reader-state evaluation refused; "
                f"max-model-calls {max_model_calls} is below required budget 1."
            ),
        )

    initialize_database(config)
    resolved_packet = _resolve_path(config, ablation_packet)
    if not resolved_packet.exists() or not resolved_packet.is_dir():
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=resolved_packet,
            message=(
                "Nonlocal law candidate reader-state evaluation refused; "
                f"ablation packet directory not found: {resolved_packet}"
            ),
        )

    try:
        superseded_evaluation: ExistingReaderStateEvaluation | None = None
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, config, resolved_packet)
            superseded_evaluation = _validate_subject_before_evaluation(
                connection,
                subject,
                client_name=client_name,
            )
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    client_name=client_name,
                    model=configured_model,
                    ablation_packet=resolved_packet,
                    message=(
                        "Nonlocal law candidate reader-state evaluation refused; "
                        f"run is not registered: {subject.run_id}"
                    ),
                )
            set_active_phase(
                connection,
                subject.run_id,
                AUTONOMOUS_NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_ACTIVE_PHASE,
            )
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            ablation_packet=resolved_packet,
            message=f"Nonlocal law candidate reader-state evaluation refused; {error}",
        )

    model_results: list[ModelDriverResult] = []
    if client_name == "openai":
        factory = client_factory or _default_openai_client_factory
        model_result = _run_live_reader_state_model(
            config=config,
            subject=subject,
            model_client=factory(configured_model),
        )
        model_results.append(model_result)
        if not model_result.accepted or model_result.parsed_payload is None:
            return _failed_model_result(
                config=config,
                subject=subject,
                client_name=client_name,
                model=configured_model,
                model_results=model_results,
                validation_report=_validation_report_for_model_failure(model_result),
                message=_model_failure_message(model_result),
            )
        model_payload = model_result.parsed_payload
    else:
        model_payload = _valid_model_payload(_prompt_packet(subject))
        model_payload["fixture_only"] = True

    try:
        _validate_model_payload_for_subject(subject, model_payload)
    except ModelValidationError as error:
        return _failed_model_result(
            config=config,
            subject=subject,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_results=model_results,
            validation_report={
                "validation_passed": False,
                "validation_failures": [str(error)],
            },
            message=(
                "Nonlocal law candidate reader-state evaluation refused; "
                f"{error}"
            ),
        )

    packet_dir = create_packet_dir(
        config.run_dir(subject.run_id)
        / "nonlocal_law_candidate_reader_state_evaluation"
    )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CANDIDATE_READER_STATE_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CANDIDATE_READER_STATE_CREATED_BY,
            fixture_only=client_name == "fake",
            model_call_id=None,
        )
        model_writer = (
            PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=packet_dir,
                lineage_id=NONLOCAL_LAW_CANDIDATE_READER_STATE_LINEAGE_ID,
                created_by=f"model_driver:openai:{configured_model}",
                fixture_only=False,
                model_call_id=model_results[-1].model_call.id,
            )
            if model_results
            else None
        )
        payloads, artifacts = _write_evaluation_artifacts(
            writer=writer,
            model_writer=model_writer,
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=configured_model if client_name == "openai" else None,
            model_payload=model_payload,
            model_results=model_results,
            superseded_evaluation=superseded_evaluation,
        )
        if model_results:
            linked_call = link_model_call_parsed_artifact(
                connection,
                model_call_id=model_results[-1].model_call.id,
                parsed_output_artifact_id=artifacts[
                    "first_pass_pressure_before_explanation_report"
                ].id,
            )
            model_results[-1] = ModelDriverResult(
                model_call=linked_call,
                parsed_payload=model_results[-1].parsed_payload,
                parsed_artifact=artifacts[
                    "first_pass_pressure_before_explanation_report"
                ],
            )
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="nonlocal_law_reader_state_gate_report",
            passed=False,
            blocking_defects=list(
                payloads["nonlocal_law_reader_state_gate_report"][
                    "unresolved_blockers"
                ]
            ),
            lineage_id=NONLOCAL_LAW_CANDIDATE_READER_STATE_LINEAGE_ID,
        )

    return NonlocalLawCandidateReaderStateEvaluationResult(
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
    ablation_packet_dir: Path,
) -> NonlocalLawCandidateReaderStateSubject:
    _envelopes, ablation_payloads = _load_required_payloads(
        ablation_packet_dir,
        NONLOCAL_LAW_CANDIDATE_ABLATION_ARTIFACT_TYPES,
        "nonlocal law candidate ablation packet",
    )
    packet = ablation_payloads["nonlocal_law_candidate_ablation_packet"]
    run_id = str(packet.get("run_id") or "")
    if not run_id:
        raise ValueError("ablation packet missing run_id")
    ablation_packet_id = str(packet.get("packet_id") or ablation_packet_dir.name)
    ablation_artifact_ids = {
        artifact_type: artifact.id
        for artifact_type in NONLOCAL_LAW_CANDIDATE_ABLATION_ARTIFACT_TYPES
        if (artifact := _artifact_for_path(connection, ablation_packet_dir / f"{artifact_type}.json"))
        is not None
    }
    source_candidate_dir = _resolve_source_candidate_dir(config, packet, run_id)
    _candidate_envelopes, candidate_payloads = _load_required_payloads(
        source_candidate_dir,
        (
            "generated_candidate_text",
            "nonlocal_law_guided_candidate_packet",
        ),
        "source nonlocal law candidate packet",
    )
    generated = candidate_payloads["generated_candidate_text"]
    candidate_text = generated.get("text")
    if not isinstance(candidate_text, str) or not candidate_text.strip():
        raise ValueError("source candidate generated_candidate_text.payload.text missing")
    candidate_sha = sha256_text(candidate_text)
    recorded_sha = generated.get("text_sha256")
    if recorded_sha is not None and recorded_sha != candidate_sha:
        raise ValueError("source candidate generated text hash mismatch")
    if packet.get("candidate_text_sha256") != candidate_sha:
        raise ValueError("ablation candidate_text_sha256 does not match source candidate")

    base_id = str(packet.get("base_candidate_packet_id") or "")
    base_dir = config.run_dir(run_id) / "bounded_macro_recomposition" / base_id
    base_text = _load_base_candidate_text(base_dir)
    base_subject = ablation_payloads["base_candidate_control_subject"]
    base_subject_hash_missing = not bool(
        base_subject.get("base_text_sha256")
        or base_subject.get("base_subject_hash")
    )

    candidate_artifact_ids = {
        artifact_type: artifact.id
        for artifact_type in ("generated_candidate_text", "nonlocal_law_guided_candidate_packet")
        if (artifact := _artifact_for_path(connection, source_candidate_dir / f"{artifact_type}.json"))
        is not None
    }
    parent_ids = _unique(
        [
            *ablation_artifact_ids.values(),
            *candidate_artifact_ids.values(),
            *[
                str(value)
                for value in dict(packet.get("artifact_ids") or {}).values()
                if value
            ],
        ]
    )
    packet_artifact = _artifact_for_path(
        connection,
        ablation_packet_dir / "nonlocal_law_candidate_ablation_packet.json",
    )
    return NonlocalLawCandidateReaderStateSubject(
        run_id=run_id,
        ablation_packet_dir=ablation_packet_dir,
        ablation_packet_id=ablation_packet_id,
        ablation_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        ablation_payloads=ablation_payloads,
        ablation_artifact_ids=ablation_artifact_ids,
        source_parent_ids=tuple(parent_ids),
        source_candidate_packet_dir=source_candidate_dir,
        source_candidate_payloads=candidate_payloads,
        source_candidate_artifact_ids=candidate_artifact_ids,
        candidate_text=candidate_text,
        candidate_text_sha256=candidate_sha,
        candidate_word_count=len(candidate_text.split()),
        base_candidate_packet_dir=base_dir,
        base_candidate_text=base_text,
        base_candidate_text_sha256=sha256_text(base_text),
        base_subject_hash_missing=base_subject_hash_missing,
    )


def _validate_subject_before_evaluation(
    connection: sqlite3.Connection,
    subject: NonlocalLawCandidateReaderStateSubject,
    *,
    client_name: str,
) -> ExistingReaderStateEvaluation | None:
    packet = subject.ablation_payloads["nonlocal_law_candidate_ablation_packet"]
    _require_bool(packet, "accepted", True)
    _require_bool(packet, "ablation_executed", True)
    _require_bool(packet, "ready_for_reader_state_evaluation", True)
    _require_bool(packet, "reader_state_evaluation_authorized", False)
    _require_equal(packet, "base_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID)
    _require_equal(packet, "current_best_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID)
    _require_equal(packet, "proof_packet_id", EXPECTED_PROOF_PACKET_ID)
    _require_equal(packet, "reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID)
    _require_equal(packet, "law_id", DISCOVERED_LOCAL_LAW_ID)
    _require_equal(packet, "target_scope", NONLOCAL_LAW_TARGET_SCOPE)
    _require_bool(packet, "no_final_claim", True)
    _require_bool(packet, "no_phase_shift_claim", True)
    _require_bool(packet, "strongest_rival_defeated_claimed", False)

    controls = _control_ids(subject)
    missing_controls = [control for control in ABLATION_CONTROL_IDS if control not in controls]
    if missing_controls:
        raise ValueError("ablation controls missing: " + ", ".join(missing_controls))
    choices = _law_bearing_choices(subject)
    if len(choices) < len(LAW_BEARING_SPANS):
        raise ValueError("law-bearing choices missing")
    risks = _candidate_review_risks(subject)
    missing_risks = [risk_id for risk_id in RISK_IDS if risk_id not in risks]
    if missing_risks:
        raise ValueError("candidate review risks missing: " + ", ".join(missing_risks))
    if _payload_has_final_or_phase_claim(packet) or _payload_has_final_or_phase_claim(
        subject.source_candidate_payloads
    ):
        raise ValueError("source carries finality, phase-shift, or rival-defeat claim")
    existing_evaluations = _accepted_reader_state_for_ablation(connection, subject)
    if client_name == "fake" and existing_evaluations:
        raise ValueError(
            "accepted reader-state evaluation packet already exists for ablation"
        )
    blocking_evaluations = [
        evaluation
        for evaluation in existing_evaluations
        if evaluation.model_backed
        or (evaluation.usable_for_synthesis and not evaluation.provisional)
    ]
    if blocking_evaluations:
        raise ValueError(
            "current-valid model-backed reader-state evaluation packet already "
            "exists for ablation"
        )
    provisional_evaluations = [
        evaluation for evaluation in existing_evaluations if evaluation.provisional
    ]
    if provisional_evaluations:
        return provisional_evaluations[-1]
    return None


def _run_live_reader_state_model(
    *,
    config: AbiConfig,
    subject: NonlocalLawCandidateReaderStateSubject,
    model_client: ModelClient,
) -> ModelDriverResult:
    return ModelDriver(config=config, client=model_client).run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATOR,
            prompt_contract_id=PROMPT_CONTRACT_ID,
            schema=NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA,
            input_text=_canonical_json(_prompt_packet(subject)),
            input_artifact_ids=list(subject.source_parent_ids),
            input_packet_path=str(subject.ablation_packet_dir),
            lineage_id=NONLOCAL_LAW_CANDIDATE_READER_STATE_LINEAGE_ID,
            parent_ids=list(subject.source_parent_ids),
            fixture_only=False,
            register_parsed_artifact=False,
            parsed_payload_validator=lambda payload: _validate_model_payload_for_subject(
                subject,
                payload,
            ),
        )
    )


def _write_evaluation_artifacts(
    *,
    writer: PacketWriter,
    model_writer: PacketWriter | None,
    subject: NonlocalLawCandidateReaderStateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    model_payload: dict[str, object],
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingReaderStateEvaluation | None,
) -> tuple[dict[str, dict[str, object]], dict[str, ArtifactRecord]]:
    payloads: dict[str, dict[str, object]] = {}
    artifacts: dict[str, ArtifactRecord] = {}

    payloads["source_ablation_intake_summary"] = _build_source_intake(
        subject,
        packet_dir,
        client_name,
        model,
        model_results,
        superseded_evaluation,
    )
    artifacts["source_ablation_intake_summary"] = writer.write_artifact(
        "source_ablation_intake_summary",
        payloads["source_ablation_intake_summary"],
        parent_ids=_source_parent_ids(subject, superseded_evaluation),
    )

    payloads["candidate_reader_state_subject"] = _build_candidate_subject(subject)
    artifacts["candidate_reader_state_subject"] = writer.write_artifact(
        "candidate_reader_state_subject",
        payloads["candidate_reader_state_subject"],
        parent_ids=[artifacts["source_ablation_intake_summary"].id],
    )

    payloads["base_candidate_reader_state_subject"] = _build_base_subject(subject)
    artifacts["base_candidate_reader_state_subject"] = writer.write_artifact(
        "base_candidate_reader_state_subject",
        payloads["base_candidate_reader_state_subject"],
        parent_ids=[artifacts["source_ablation_intake_summary"].id],
    )

    payloads["ablation_control_reader_state_matrix"] = _build_control_matrix(
        subject,
        model_payload,
    )
    artifacts["ablation_control_reader_state_matrix"] = _write_artifact(
        writer=writer,
        model_writer=model_writer,
        artifact_type="ablation_control_reader_state_matrix",
        payload=payloads["ablation_control_reader_state_matrix"],
        parent_ids=[
            artifacts["candidate_reader_state_subject"].id,
            artifacts["base_candidate_reader_state_subject"].id,
        ],
    )

    model_parent = artifacts["ablation_control_reader_state_matrix"].id
    for artifact_type, payload in {
        "first_pass_pressure_before_explanation_report": _build_first_pass_report(
            subject,
            model_payload,
        ),
        "object_event_consequence_reader_state_report": _build_object_event_report(
            subject,
            model_payload,
        ),
        "explanation_earned_not_abolished_report": _build_explanation_report(
            subject,
            model_payload,
        ),
        "reread_return_preparation_report": _build_reread_return_report(
            subject,
            model_payload,
        ),
        "non_imitation_reader_signal_report": _build_non_imitation_report(
            subject,
            model_payload,
        ),
        "candidate_review_risk_probe_report": _build_risk_probe_report(
            subject,
            model_payload,
        ),
        "candidate_vs_packet_0063_reader_state_comparison": _build_candidate_comparison(
            subject,
            model_payload,
        ),
        "strongest_rival_pressure_status_report": _build_strongest_rival_report(
            subject,
            model_payload,
        ),
    }.items():
        payloads[artifact_type] = payload
        artifacts[artifact_type] = _write_artifact(
            writer=writer,
            model_writer=model_writer,
            artifact_type=artifact_type,
            payload=payload,
            parent_ids=[model_parent],
        )
        model_parent = artifacts[artifact_type].id

    payloads["synthesis_readiness_report"] = _build_synthesis_readiness(
        subject,
        model_payload,
        client_name,
        model_results,
        superseded_evaluation,
    )
    artifacts["synthesis_readiness_report"] = writer.write_artifact(
        "synthesis_readiness_report",
        payloads["synthesis_readiness_report"],
        parent_ids=[artifacts["strongest_rival_pressure_status_report"].id],
    )

    payloads["nonlocal_law_reader_state_gate_report"] = _build_gate_report(
        subject,
        model_payload,
        client_name,
        model_results,
        superseded_evaluation,
    )
    artifacts["nonlocal_law_reader_state_gate_report"] = writer.write_artifact(
        "nonlocal_law_reader_state_gate_report",
        payloads["nonlocal_law_reader_state_gate_report"],
        parent_ids=[artifacts["synthesis_readiness_report"].id],
    )

    payloads["project_health_scope_guard_report"] = _build_health_report(
        subject,
        model_payload,
        model_results,
        superseded_evaluation,
    )
    artifacts["project_health_scope_guard_report"] = writer.write_artifact(
        "project_health_scope_guard_report",
        payloads["project_health_scope_guard_report"],
        parent_ids=[artifacts["nonlocal_law_reader_state_gate_report"].id],
    )

    payloads["nonlocal_law_candidate_reader_state_evaluation_packet"] = (
        _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            model=model,
            payloads=payloads,
            artifacts=artifacts,
            model_payload=model_payload,
            model_results=model_results,
            superseded_evaluation=superseded_evaluation,
        )
    )
    artifacts["nonlocal_law_candidate_reader_state_evaluation_packet"] = (
        writer.write_artifact(
            "nonlocal_law_candidate_reader_state_evaluation_packet",
            payloads["nonlocal_law_candidate_reader_state_evaluation_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type
                != "nonlocal_law_candidate_reader_state_evaluation_packet"
            ],
        )
    )
    return payloads, artifacts


def _build_source_intake(
    subject: NonlocalLawCandidateReaderStateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingReaderStateEvaluation | None,
) -> dict[str, object]:
    mode_fields = _reader_state_mode_fields(
        client_name,
        model_results,
        superseded_evaluation,
    )
    return {
        **_source_fields(subject),
        **mode_fields,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "model": model,
        "candidate_text_extracted_from": "generated_candidate_text.payload.text",
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "base_subject_hash_missing": subject.base_subject_hash_missing,
        "base_subject_resolved_from_packet_id": EXPECTED_CURRENT_BEST_PACKET_ID,
        "consumed_base_candidate_packet_successfully": True,
        "reader_state_evaluation_executed": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "synthesis_authorized": False,
        "current_best_updated": False,
        "model_calls": 0 if client_name == "fake" else 1,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "worker": "source_ablation_intake_summary_v1_controller",
    }


def _build_candidate_subject(
    subject: NonlocalLawCandidateReaderStateSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "candidate_text": subject.candidate_text,
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "candidate_text_extracted_from": "generated_candidate_text.payload.text",
        "reader_state_subject": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "candidate_reader_state_subject_v1_controller",
    }


def _build_base_subject(
    subject: NonlocalLawCandidateReaderStateSubject,
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "base_candidate_text": subject.base_candidate_text,
        "base_candidate_text_sha256": subject.base_candidate_text_sha256,
        "base_subject_hash_missing": subject.base_subject_hash_missing,
        "base_subject_resolved_from_packet_id": EXPECTED_CURRENT_BEST_PACKET_ID,
        "consumed_base_candidate_packet_successfully": True,
        "candidate_generated": False,
        "generation_authorized": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "base_candidate_reader_state_subject_v1_controller",
    }


def _build_control_matrix(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    by_id = {
        str(row["control_id"]): row
        for row in _object_list(model_payload, "ablation_control_reader_state_matrix")
    }
    return {
        **_source_fields(subject),
        "ablation_controls": [
            {
                "control_id": control_id,
                "reader_state_evaluation_scope": "evaluation_condition",
                "model_result": by_id[control_id],
            }
            for control_id in ABLATION_CONTROL_IDS
        ],
        "ablation_control_count": len(ABLATION_CONTROL_IDS),
        "candidate_generated": False,
        "generation_authorized": False,
        "synthesis_authorized": False,
        "model_calls": _model_call_count(model_payload),
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "ablation_control_reader_state_matrix_v1_controller",
    }


def _build_first_pass_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    first = dict(model_payload["first_pass_reader_state"])
    comparison = dict(model_payload["candidate_vs_packet_0063_comparison"])
    return {
        **_source_fields(subject),
        "first_read_pressure_result": comparison["first_read_pressure_result"],
        "first_pass_reader_state": first,
        "question": "Did pressure arrive before explanation?",
        "reader_state_result_claimed_as_final": False,
        "candidate_generated": False,
        "finalization_eligible": False,
        "worker": "first_pass_pressure_before_explanation_report_v1_controller",
    }


def _build_object_event_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    comparison = dict(model_payload["candidate_vs_packet_0063_comparison"])
    law = dict(model_payload["law_effect_assessment"])
    return {
        **_source_fields(subject),
        "object_event_consequence_result": comparison[
            "object_event_consequence_result"
        ],
        "law_effect_object_event_result": law["object_event_consequence_result"],
        "law_effect_summary": law["law_effect_summary"],
        "sequence_evaluation": "object-event consequence before naming",
        "candidate_generated": False,
        "finalization_eligible": False,
        "worker": "object_event_consequence_reader_state_report_v1_controller",
    }


def _build_explanation_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    comparison = dict(model_payload["candidate_vs_packet_0063_comparison"])
    law = dict(model_payload["law_effect_assessment"])
    return {
        **_source_fields(subject),
        "explanation_timing_result": comparison["explanation_timing_result"],
        "explanation_earned_not_abolished": law["explanation_earned_not_abolished"],
        "law_effect_explanation_result": law["explanation_timing_result"],
        "candidate_generated": False,
        "finalization_eligible": False,
        "worker": "explanation_earned_not_abolished_report_v1_controller",
    }


def _build_reread_return_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    second = dict(model_payload["second_pass_reader_state"])
    comparison = dict(model_payload["candidate_vs_packet_0063_comparison"])
    return {
        **_source_fields(subject),
        "reread_return_result": comparison["reread_return_result"],
        "second_pass_reader_state": second,
        "opening_table_field_returns_changed": True,
        "candidate_generated": False,
        "finalization_eligible": False,
        "worker": "reread_return_preparation_report_v1_controller",
    }


def _build_non_imitation_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "non_imitation_result": NON_IMITATION_RESULT,
        "rival_imitation_detected": False,
        "strongest_rival_defeated_claimed": False,
        "evidence": (
            "Candidate is evaluated as avoiding rival objects/scenes while "
            "strongest-rival pressure remains active."
        ),
        "candidate_generated": False,
        "finalization_eligible": False,
        "worker": "non_imitation_reader_signal_report_v1_controller",
    }


def _build_risk_probe_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    return {
        **_source_fields(subject),
        "risk_probe_results": list(model_payload["risk_probe_results"]),
        "risk_probe_count": len(model_payload["risk_probe_results"]),
        "candidate_review_risks": list(CANDIDATE_REVIEW_RISKS),
        "candidate_generated": False,
        "synthesis_authorized": False,
        "finalization_eligible": False,
        "worker": "candidate_review_risk_probe_report_v1_controller",
    }


def _build_candidate_comparison(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    comparison = dict(model_payload["candidate_vs_packet_0063_comparison"])
    return {
        **_source_fields(subject),
        **comparison,
        "candidate_superiority_claimed": False,
        "current_best_updated": False,
        "current_best_supersession_claimed": False,
        "candidate_generated": False,
        "finalization_eligible": False,
        "worker": "candidate_vs_packet_0063_reader_state_comparison_v1_controller",
    }


def _build_strongest_rival_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
) -> dict[str, object]:
    rival = dict(model_payload["strongest_rival_pressure_assessment"])
    return {
        **_source_fields(subject),
        **rival,
        "strongest_rival_defeated_claimed": False,
        "strongest_rival_comparison_passed": False,
        "candidate_generated": False,
        "finalization_eligible": False,
        "worker": "strongest_rival_pressure_status_report_v1_controller",
    }


def _build_synthesis_readiness(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
    client_name: str,
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingReaderStateEvaluation | None,
) -> dict[str, object]:
    mode_fields = _reader_state_mode_fields(
        client_name,
        model_results,
        superseded_evaluation,
    )
    usable_for_synthesis = bool(mode_fields["usable_for_synthesis"])
    return {
        **_source_fields(subject),
        **mode_fields,
        "ready_for_synthesis": usable_for_synthesis,
        "synthesis_authorized": False,
        "synthesis_requires_separate_command": True,
        "synthesis_ready_only_after_model_backed_evaluation": not usable_for_synthesis,
        "recommended_next_action": "review_reader_state_then_run_autonomous_evidence_synthesis",
        "overall_reader_state_result": model_payload["reader_state_summary"][
            "overall_reader_state_result"
        ],
        "candidate_generated": False,
        "current_best_updated": False,
        "finalization_eligible": False,
        "worker": "synthesis_readiness_report_v1_controller",
    }


def _build_gate_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
    client_name: str,
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingReaderStateEvaluation | None,
) -> dict[str, object]:
    mode_fields = _reader_state_mode_fields(
        client_name,
        model_results,
        superseded_evaluation,
    )
    model_backed = bool(mode_fields["model_backed"])
    gate_results = [
        _gate_result("operator_reviewed", True),
        _gate_result("source_ablation_accepted", True),
        _gate_result("candidate_text_loaded_from_payload_text", True),
        _gate_result("reader_state_evaluation_executed", True),
        _gate_result(
            "model_backed_reader_state_evaluation",
            model_backed,
            [] if model_backed else ["fake reader-state evaluation is provisional"],
        ),
        _gate_result("all_ablation_controls_evaluated", True),
        _gate_result("synthesis_authorized", False, ["synthesis requires separate command"]),
        _gate_result("current_best_updated", False, ["current best remains packet_0063"]),
        _gate_result(
            "strongest_rival_pressure_resolved",
            False,
            ["strongest rival remains blocking"],
        ),
        _gate_result(
            "finalization_eligible",
            False,
            ["reader-state evidence is not finalization evidence"],
        ),
    ]
    return {
        **_source_fields(subject),
        **mode_fields,
        "passed": False,
        "eligible": False,
        "reader_state_evaluation_executed": True,
        "overall_reader_state_result": model_payload["reader_state_summary"][
            "overall_reader_state_result"
        ],
        "candidate_generated": False,
        "generation_authorized": False,
        "synthesis_authorized": False,
        "current_best_updated": False,
        "model_calls": _model_call_count(model_payload),
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "gate_results": gate_results,
        "failed_gates": [
            str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
        ],
        "unresolved_blockers": [
            "synthesis has not been run",
            "strongest rival remains blocking",
            "current best remains packet_0063 until synthesis",
            "finalization remains refused",
        ],
        "worker": "nonlocal_law_reader_state_gate_report_v1_controller",
    }


def _build_health_report(
    subject: NonlocalLawCandidateReaderStateSubject,
    model_payload: dict[str, object],
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingReaderStateEvaluation | None,
) -> dict[str, object]:
    mode_fields = _reader_state_mode_fields(
        "openai" if model_results else "fake",
        model_results,
        superseded_evaluation,
    )
    checks = [
        _check("source_ablation_accepted", True),
        _check("candidate_text_loaded_from_payload_text", True),
        _check("base_subject_alias_gap_tolerated", subject.base_subject_hash_missing),
        _check("no_candidate_generated", True),
        _check("no_generation_authorized", True),
        _check("no_synthesis_authorized", True),
        _check("current_best_not_updated", True),
        _check("no_final_claim", True),
        _check("no_phase_shift_claim", True),
        _check("strongest_rival_not_defeated", True),
    ]
    return {
        **_source_fields(subject),
        **mode_fields,
        "checks": checks,
        "passed": True,
        "project_health_scope_guard_passed": True,
        "model_calls": len(model_results),
        "candidate_generated": False,
        "generation_authorized": False,
        "synthesis_authorized": False,
        "current_best_updated": False,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "project_health_scope_guard_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: NonlocalLawCandidateReaderStateSubject,
    packet_dir: Path,
    client_name: str,
    model: str | None,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    model_payload: dict[str, object],
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingReaderStateEvaluation | None,
) -> dict[str, object]:
    counts = packet_artifact_count_summary(
        required_artifact_types=NONLOCAL_LAW_CANDIDATE_READER_STATE_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="nonlocal_law_candidate_reader_state_evaluation_packet",
    )
    mode_fields = _reader_state_mode_fields(
        client_name,
        model_results,
        superseded_evaluation,
    )
    usable_for_synthesis = bool(mode_fields["usable_for_synthesis"])
    return {
        **_source_fields(subject),
        **mode_fields,
        "accepted": True,
        "client": client_name,
        "model": model,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "reader_state_evaluation_executed": True,
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_word_count": subject.candidate_word_count,
        "ablation_control_count": len(ABLATION_CONTROL_IDS),
        "law_bearing_choice_count": len(_law_bearing_choices(subject)),
        "candidate_review_risk_count": len(_candidate_review_risks(subject)),
        "first_read_pressure_result": model_payload[
            "candidate_vs_packet_0063_comparison"
        ]["first_read_pressure_result"],
        "object_event_consequence_result": model_payload[
            "candidate_vs_packet_0063_comparison"
        ]["object_event_consequence_result"],
        "explanation_timing_result": model_payload[
            "candidate_vs_packet_0063_comparison"
        ]["explanation_timing_result"],
        "reread_return_result": model_payload[
            "candidate_vs_packet_0063_comparison"
        ]["reread_return_result"],
        "non_imitation_result": NON_IMITATION_RESULT,
        "strongest_rival_pressure_result": model_payload[
            "strongest_rival_pressure_assessment"
        ]["strongest_rival_pressure_result"],
        "overall_reader_state_result": model_payload["reader_state_summary"][
            "overall_reader_state_result"
        ],
        "reader_state_summary": model_payload["reader_state_summary"],
        "ready_for_synthesis": usable_for_synthesis,
        "synthesis_ready_only_after_model_backed_evaluation": not usable_for_synthesis,
        "synthesis_authorized": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "current_best_updated": False,
        "model_calls": len(model_results),
        "model_call_ids": [result.model_call.id for result in model_results],
        "counts": {**counts, "model_calls": len(model_results)},
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "nonlocal_law_candidate_reader_state_evaluation_packet",
        ],
        "gate_report": payloads["nonlocal_law_reader_state_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "strongest_rival_defeated_claimed": False,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "worker": "nonlocal_law_candidate_reader_state_evaluation_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    packet = payloads["nonlocal_law_candidate_reader_state_evaluation_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
        "model_calls": len(model_results),
        "model_call_records": [
            result.model_call_to_dict() for result in model_results
        ],
    }


def _failed_model_result(
    *,
    config: AbiConfig,
    subject: NonlocalLawCandidateReaderStateSubject,
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
    validation_report: dict[str, object],
    message: str,
) -> NonlocalLawCandidateReaderStateEvaluationResult:
    with connect(config.db_path) as connection:
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id)
            / "nonlocal_law_candidate_reader_state_failed_evaluation"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=NONLOCAL_LAW_CANDIDATE_READER_STATE_LINEAGE_ID,
            created_by=NONLOCAL_LAW_CANDIDATE_READER_STATE_CREATED_BY,
            fixture_only=client_name == "fake",
            model_call_id=None,
        )
        failure_surface = _failure_surface_fields(validation_report, model_results)
        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}
        payloads["failed_reader_state_evaluation_diagnostic"] = {
            **_source_fields(subject),
            "accepted": False,
            "message": message,
            **failure_surface,
            "client": client_name,
            "model": model,
            "validation_report": validation_report,
            "model_call_ids": [result.model_call.id for result in model_results],
            "reader_state_evaluation_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "synthesis_authorized": False,
            "current_best_updated": False,
            "model_calls": len(model_results),
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "worker": "failed_reader_state_evaluation_diagnostic_v1_controller",
        }
        artifacts["failed_reader_state_evaluation_diagnostic"] = writer.write_artifact(
            "failed_reader_state_evaluation_diagnostic",
            payloads["failed_reader_state_evaluation_diagnostic"],
            parent_ids=list(subject.source_parent_ids),
        )
        payloads["failed_reader_state_evaluation_gate_report"] = {
            **_source_fields(subject),
            "passed": False,
            "eligible": False,
            "reader_state_evaluation_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "synthesis_authorized": False,
            "current_best_updated": False,
            "model_calls": len(model_results),
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "unresolved_blockers": [message],
            "worker": "failed_reader_state_evaluation_gate_report_v1_controller",
        }
        artifacts["failed_reader_state_evaluation_gate_report"] = writer.write_artifact(
            "failed_reader_state_evaluation_gate_report",
            payloads["failed_reader_state_evaluation_gate_report"],
            parent_ids=[artifacts["failed_reader_state_evaluation_diagnostic"].id],
        )
        counts = packet_artifact_count_summary(
            required_artifact_types=FAILED_NONLOCAL_LAW_CANDIDATE_READER_STATE_ARTIFACT_TYPES,
            produced_artifact_types=list(artifacts),
            packet_artifact_type=(
                "nonlocal_law_candidate_reader_state_failed_evaluation_packet"
            ),
        )
        payloads["nonlocal_law_candidate_reader_state_failed_evaluation_packet"] = {
            **_source_fields(subject),
            "accepted": False,
            "refused": True,
            "message": message,
            **failure_surface,
            "packet_id": packet_dir.name,
            "packet_dir": str(packet_dir),
            "reader_state_evaluation_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "synthesis_authorized": False,
            "current_best_updated": False,
            "model_calls": len(model_results),
            "counts": {**counts, "model_calls": len(model_results)},
            "artifact_ids": {
                artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
            },
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "next_recommended_action": FAILED_NEXT_RECOMMENDED_ACTION,
            "worker": (
                "nonlocal_law_candidate_reader_state_failed_evaluation_packet_v1_controller"
            ),
        }
        artifacts["nonlocal_law_candidate_reader_state_failed_evaluation_packet"] = (
            writer.write_artifact(
                "nonlocal_law_candidate_reader_state_failed_evaluation_packet",
                payloads[
                    "nonlocal_law_candidate_reader_state_failed_evaluation_packet"
                ],
                parent_ids=[
                    artifacts["failed_reader_state_evaluation_diagnostic"].id,
                    artifacts["failed_reader_state_evaluation_gate_report"].id,
                ],
            )
        )
    return NonlocalLawCandidateReaderStateEvaluationResult(
        exit_code=1,
        payload={
            **payloads["nonlocal_law_candidate_reader_state_failed_evaluation_packet"],
            "artifact_paths": {
                artifact_type: str(packet_dir / f"{artifact_type}.json")
                for artifact_type in artifacts
            },
            "validation_report": validation_report,
        },
        artifacts=tuple(artifacts.values()),
        model_results=tuple(model_results),
    )


def _prompt_packet(subject: NonlocalLawCandidateReaderStateSubject) -> dict[str, object]:
    return {
        "task": "evaluate nonlocal law-guided candidate reader-state effects only",
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "schema": NONLOCAL_LAW_CANDIDATE_READER_STATE_EVALUATION_SCHEMA.name,
        "source_ablation_packet_id": subject.ablation_packet_id,
        "source_candidate_packet_id": _source_fields(subject)["source_candidate_packet_id"],
        "base_candidate_packet_id": EXPECTED_CURRENT_BEST_PACKET_ID,
        "prior_reader_state_packet_id": EXPECTED_READER_STATE_PACKET_ID,
        "proof_packet_id": EXPECTED_PROOF_PACKET_ID,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "candidate_text_sha256": subject.candidate_text_sha256,
        "candidate_text": subject.candidate_text,
        "base_candidate_text_sha256": subject.base_candidate_text_sha256,
        "base_candidate_text": subject.base_candidate_text,
        "ablation_controls": list(ABLATION_CONTROL_IDS),
        "law_bearing_choices": list(LAW_BEARING_SPANS),
        "candidate_review_risks": list(CANDIDATE_REVIEW_RISKS),
        "evaluation_dimensions": [
            "first-read pressure before explanation",
            "object-event consequence before naming",
            "explanation earned, not abolished",
            "reread return preparation",
            "non-imitation reader signal",
            "strongest-rival pressure remains active",
        ],
        "model_must_not": [
            "generate or rewrite candidate text",
            "authorize generation or synthesis",
            "update current best",
            "claim improvement is proven",
            "claim strongest-rival defeat",
            "claim finality or phase shift",
        ],
    }


def _valid_model_payload(prompt: dict[str, object]) -> dict[str, object]:
    controls = [
        {
            "control_id": control_id,
            "expected_reader_state_contrast": (
                "Tests whether the candidate reader-state effect depends on "
                f"{control_id}."
            ),
            "predicted_result": "supports_candidate"
            if control_id
            in {
                "full_nonlocal_law_guided_intervention",
                "remove_consequence_first_sequence",
                "restore_early_explanation_timing",
            }
            else "mixed",
            "evidence": f"{control_id} remains an evaluation condition, not proof.",
        }
        for control_id in ABLATION_CONTROL_IDS
    ]
    risks = [
        {
            "risk_id": str(risk["risk_id"]),
            "result": "at_risk"
            if risk["risk_id"]
            in {"chemistry_register_risk", "conclusion_may_summarize_law"}
            else "inconclusive",
            "evidence": str(risk["risk"]) + " remains to be adjudicated in synthesis.",
        }
        for risk in CANDIDATE_REVIEW_RISKS
    ]
    return {
        "first_pass_reader_state": {
            "result": FIRST_READ_PRESSURE_RESULT,
            "evidence": (
                "The candidate opens with object marks before naming the law, "
                "creating pressure before explanation."
            ),
            "reader_state_effect": (
                "First pass feels more object-led than packet_0063, but not final."
            ),
            "packet_0063_contrast": (
                "packet_0063 keeps the field stable; the candidate puts it under "
                "earlier sequence pressure."
            ),
        },
        "second_pass_reader_state": {
            "result": "improved",
            "evidence": (
                "The later return asks the opening table/dust/spoon/saucer field "
                "to be reread as prepared consequence."
            ),
            "reader_state_effect": "Return is more prepared, but still needs synthesis.",
            "packet_0063_contrast": (
                "packet_0063 returns cleanly; the candidate tries to make the "
                "return more causally loaded."
            ),
        },
        "candidate_vs_packet_0063_comparison": {
            "first_read_pressure_result": FIRST_READ_PRESSURE_RESULT,
            "object_event_consequence_result": OBJECT_EVENT_CONSEQUENCE_RESULT,
            "explanation_timing_result": EXPLANATION_TIMING_RESULT,
            "reread_return_result": "improved",
            "comparison_summary": (
                "Reader-state evidence supports sending the candidate to synthesis "
                "without superseding packet_0063."
            ),
        },
        "ablation_control_reader_state_matrix": controls,
        "law_effect_assessment": {
            "object_event_consequence_result": OBJECT_EVENT_CONSEQUENCE_RESULT,
            "explanation_timing_result": EXPLANATION_TIMING_RESULT,
            "explanation_earned_not_abolished": True,
            "law_effect_summary": (
                "The candidate appears to stage consequence before naming while "
                "retaining explanation as a later function."
            ),
        },
        "risk_probe_results": risks,
        "strongest_rival_pressure_assessment": {
            "strongest_rival_pressure_result": STRONGEST_RIVAL_PRESSURE_RESULT,
            "pressure_summary": (
                "The candidate narrows the law-specific gap but the strongest "
                "rival remains active and blocking."
            ),
            "strongest_rival_remains_blocking": True,
        },
        "reader_state_summary": {
            "overall_reader_state_result": OVERALL_READER_STATE_RESULT,
            "summary": (
                "The candidate earns reader-state evaluation for synthesis, not "
                "current-best supersession."
            ),
            "candidate_superiority_claimed": False,
            "current_best_supersession_claimed": False,
        },
        "recommended_next_evidence_step": "run_autonomous_evidence_synthesis",
        "generation_allowed": False,
        "synthesis_authorized": False,
        "finality_claimed": False,
        "phase_shift_claimed": False,
        "strongest_rival_defeated_claimed": False,
    }


def _validate_model_payload_for_subject(
    subject: NonlocalLawCandidateReaderStateSubject,
    payload: dict[str, object],
) -> None:
    controls = {
        str(row.get("control_id"))
        for row in _object_list(payload, "ablation_control_reader_state_matrix")
    }
    missing_controls = [control for control in ABLATION_CONTROL_IDS if control not in controls]
    if missing_controls:
        raise ModelValidationError(
            "model output missing ablation controls: " + ", ".join(missing_controls)
        )
    risks = {str(row.get("risk_id")) for row in _object_list(payload, "risk_probe_results")}
    missing_risks = [risk_id for risk_id in RISK_IDS if risk_id not in risks]
    if missing_risks:
        raise ModelValidationError(
            "model output missing risk probes: " + ", ".join(missing_risks)
        )
    for key in (
        "generation_allowed",
        "synthesis_authorized",
        "finality_claimed",
        "phase_shift_claimed",
        "strongest_rival_defeated_claimed",
    ):
        if payload.get(key) is not False:
            raise ModelValidationError(f"{key} must be false")
    summary = payload.get("reader_state_summary")
    if not isinstance(summary, dict):
        raise ModelValidationError("reader_state_summary must be an object")
    if summary.get("candidate_superiority_claimed") is not False:
        raise ModelValidationError("candidate_superiority_claimed must be false")
    if summary.get("current_best_supersession_claimed") is not False:
        raise ModelValidationError("current_best_supersession_claimed must be false")
    rival = payload.get("strongest_rival_pressure_assessment")
    if not isinstance(rival, dict) or rival.get("strongest_rival_remains_blocking") is not True:
        raise ModelValidationError("strongest rival must remain blocking")
    _ = subject


def _source_fields(subject: NonlocalLawCandidateReaderStateSubject) -> dict[str, object]:
    packet = subject.ablation_payloads["nonlocal_law_candidate_ablation_packet"]
    return {
        "source_ablation_packet_id": subject.ablation_packet_id,
        "source_ablation_packet_dir": str(subject.ablation_packet_dir),
        "source_candidate_packet_id": packet.get("source_candidate_packet_id"),
        "source_authorization_packet_id": packet.get("source_authorization_packet_id"),
        "source_work_order_packet_id": packet.get("source_work_order_packet_id"),
        "source_strategy_packet_id": packet.get("source_strategy_packet_id"),
        "source_diagnostic_packet_id": packet.get("source_diagnostic_packet_id"),
        "base_candidate_packet_id": packet.get("base_candidate_packet_id"),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "prior_reader_state_packet_id": packet.get("reader_state_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "law_id": packet.get("law_id"),
        "selected_strategy_class": packet.get("selected_strategy_class"),
        "target_scope": packet.get("target_scope"),
    }


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


def _load_base_candidate_text(packet_dir: Path) -> str:
    path = packet_dir / "macro_recomposed_candidate_text.json"
    if not path.exists():
        raise ValueError("base candidate macro_recomposed_candidate_text cannot be loaded")
    envelope = read_json_file(path)
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ValueError("base candidate text artifact is malformed")
    return str(payload["text"])


def _resolve_source_candidate_dir(
    config: AbiConfig,
    packet: dict[str, Any],
    run_id: str,
) -> Path:
    source_dir = packet.get("source_candidate_packet_dir")
    if isinstance(source_dir, str) and source_dir.strip():
        path = Path(source_dir)
        return path if path.is_absolute() else config.root / path
    source_id = str(packet.get("source_candidate_packet_id") or "")
    return config.run_dir(run_id) / "nonlocal_law_guided_candidate" / source_id


def _accepted_reader_state_for_ablation(
    connection: sqlite3.Connection,
    subject: NonlocalLawCandidateReaderStateSubject,
) -> list[ExistingReaderStateEvaluation]:
    evaluations: list[ExistingReaderStateEvaluation] = []
    for artifact in list_artifacts(connection, subject.run_id):
        if artifact.type != "nonlocal_law_candidate_reader_state_evaluation_packet":
            continue
        payload = _artifact_payload(artifact)
        if payload.get("source_ablation_packet_id") != subject.ablation_packet_id:
            continue
        if (
            payload.get("accepted") is True
            and payload.get("reader_state_evaluation_executed") is True
        ):
            evaluations.append(_classify_existing_reader_state_evaluation(artifact, payload))
    return evaluations


def _classify_existing_reader_state_evaluation(
    artifact: ArtifactRecord,
    payload: dict[str, Any],
) -> ExistingReaderStateEvaluation:
    client = str(payload.get("client") or "")
    raw_model_calls = payload.get("model_calls")
    model_calls = raw_model_calls if isinstance(raw_model_calls, int) else 0
    model_backed = bool(payload.get("model_backed") is True) or (
        client == "openai" and model_calls > 0
    )
    provisional = bool(payload.get("provisional_reader_state_evaluation") is True) or (
        client == "fake" or not model_backed
    )
    usable_for_synthesis = (
        bool(payload.get("usable_for_synthesis") is True)
        and model_backed
        and not provisional
    )
    return ExistingReaderStateEvaluation(
        artifact=artifact,
        payload=payload,
        packet_id=str(payload.get("packet_id") or Path(artifact.path).parent.name),
        client=client,
        model_backed=model_backed,
        provisional=provisional,
        usable_for_synthesis=usable_for_synthesis,
    )


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    try:
        envelope = read_json_file(artifact.path)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        return {}
    return envelope["payload"]


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


def _control_ids(subject: NonlocalLawCandidateReaderStateSubject) -> set[str]:
    packet = subject.ablation_payloads["nonlocal_law_candidate_ablation_packet"]
    matrix = subject.ablation_payloads["ablation_control_matrix"]
    controls = set(_string_list(packet.get("ablation_controls")))
    for row in _object_list(matrix, "ablation_controls"):
        controls.add(str(row.get("control_id")))
    return controls


def _law_bearing_choices(subject: NonlocalLawCandidateReaderStateSubject) -> list[object]:
    map_payload = subject.ablation_payloads["law_bearing_choice_map"]
    choices = map_payload.get("law_bearing_choices") or map_payload.get("law_bearing_spans")
    return list(choices) if isinstance(choices, list) else []


def _candidate_review_risks(
    subject: NonlocalLawCandidateReaderStateSubject,
) -> set[str]:
    packet = subject.ablation_payloads["nonlocal_law_candidate_ablation_packet"]
    map_payload = subject.ablation_payloads["law_bearing_choice_map"]
    risks = packet.get("candidate_review_risks") or map_payload.get("candidate_review_risks")
    if not isinstance(risks, list):
        return set()
    return {str(risk.get("risk_id")) for risk in risks if isinstance(risk, dict)}


def _object_list(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    values = payload.get(key)
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _payload_has_final_or_phase_claim(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "finalization_eligible",
                "final_artifact",
                "final_claim",
                "current_best_updated",
                "candidate_superiority_claimed",
                "current_best_supersession_claimed",
            }:
                if item is True:
                    return True
            if key in {
                "phase_shift_claim",
                "phase_shift_claimed",
                "strongest_rival_defeated",
                "strongest_rival_defeated_claimed",
                "strongest_rival_defeat_claim",
            }:
                if item is True:
                    return True
            if key in {"no_final_claim", "no_phase_shift_claim"} and item is False:
                return True
            if _payload_has_final_or_phase_claim(item):
                return True
    elif isinstance(value, list):
        return any(_payload_has_final_or_phase_claim(item) for item in value)
    return False


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
    return {
        "failure_class": "nonlocal_law_reader_state_evaluation_validation_failure",
        "failure_reason": (
            "structured_output_validation_failed"
            if latest_result is not None and not latest_result.accepted
            else "controller_validation_failed"
        ),
        "validation_failures": validation_failures,
        "model_call_status": latest_result.model_call.status if latest_result else None,
        "model_output_keys": sorted(output_payload),
        "generation_allowed": output_payload.get("generation_allowed"),
        "synthesis_authorized": output_payload.get("synthesis_authorized"),
        "finality_claimed": output_payload.get("finality_claimed"),
        "phase_shift_claimed": output_payload.get("phase_shift_claimed"),
        "strongest_rival_defeated_claimed": output_payload.get(
            "strongest_rival_defeated_claimed"
        ),
    }


def _validation_report_for_model_failure(
    model_result: ModelDriverResult,
) -> dict[str, object]:
    return {
        "validation_passed": False,
        "validation_failures": [
            model_result.model_call.error_message or model_result.model_call.status
        ],
        "model_call_status": model_result.model_call.status,
        **{
            key: value
            for key, value in _model_output_payload_for_result(model_result).items()
            if key
            in {
                "generation_allowed",
                "synthesis_authorized",
                "finality_claimed",
                "phase_shift_claimed",
                "strongest_rival_defeated_claimed",
            }
        },
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


def _model_failure_message(result: ModelDriverResult) -> str:
    return (
        "Nonlocal law candidate reader-state evaluation refused; model call "
        f"{result.model_call.status}: {result.model_call.error_message or 'no parsed output'}"
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


def _source_parent_ids(
    subject: NonlocalLawCandidateReaderStateSubject,
    superseded_evaluation: ExistingReaderStateEvaluation | None,
) -> list[str]:
    parent_ids = list(subject.source_parent_ids)
    if superseded_evaluation is not None:
        parent_ids.append(superseded_evaluation.artifact.id)
    return parent_ids


def _reader_state_mode_fields(
    client_name: str,
    model_results: list[ModelDriverResult],
    superseded_evaluation: ExistingReaderStateEvaluation | None,
) -> dict[str, object]:
    model_backed = client_name == "openai" and bool(model_results)
    provisional = not model_backed
    fields: dict[str, object] = {
        "model_backed": model_backed,
        "reader_state_evaluation_mode": (
            "model_backed_live"
            if model_backed
            else "deterministic_fake_verification"
        ),
        "provisional_reader_state_evaluation": provisional,
        "usable_for_command_verification": True,
        "usable_for_synthesis": model_backed,
        "ready_for_live_reader_state_evaluation": not model_backed,
    }
    if not model_backed:
        fields["synthesis_ready_only_after_model_backed_evaluation"] = True
    if superseded_evaluation is not None:
        fields.update(
            {
                "superseded_reader_state_evaluation_packet_id": (
                    superseded_evaluation.packet_id
                ),
                "supersession_reason": (
                    "model_backed_reader_state_evaluation_supersedes_fake_evaluation"
                ),
                "superseded_evaluation_client": superseded_evaluation.client,
                "superseded_evaluation_model_backed": (
                    superseded_evaluation.model_backed
                ),
                "superseded_evaluation_was_provisional": (
                    superseded_evaluation.provisional
                ),
            }
        )
    return fields


def _model_call_count(model_payload: dict[str, object]) -> int:
    return 0 if model_payload.get("fixture_only") is True else 1


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
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "blocking_defects": blockers or ([] if passed else [f"{gate_name} failed"]),
    }


def _refusal(
    *,
    client_name: str,
    model: str | None,
    ablation_packet: Path | str,
    message: str,
) -> NonlocalLawCandidateReaderStateEvaluationResult:
    return NonlocalLawCandidateReaderStateEvaluationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "message": message,
            "ablation_packet": str(ablation_packet),
            "reader_state_evaluation_executed": False,
            "candidate_generated": False,
            "generation_authorized": False,
            "synthesis_authorized": False,
            "current_best_updated": False,
            "model_calls": 0,
            "artifact_ids": {},
            "artifact_paths": {},
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
            "strongest_rival_defeated_claimed": False,
        },
    )


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _require_equal(payload: dict[str, Any], field_name: str, expected: object) -> None:
    if payload.get(field_name) != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _require_bool(payload: dict[str, Any], field_name: str, expected: bool) -> None:
    if payload.get(field_name) is not expected:
        raise ValueError(f"{field_name} must be {str(expected).lower()}")


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
