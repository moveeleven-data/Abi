"""Generic Internal Reader-State Evaluation v1 packet."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from abi.artifacts import ArtifactRecord, get_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_INTERNAL_READER_STATE_EVALUATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    FORENSIC_GROUNDING_READER_SCHEMA,
    HOSTILE_INTERNAL_READER_SCHEMA,
    INTERNAL_REREAD_READER_SCHEMA,
    INTERNAL_RIVAL_COMPARISON_SCHEMA,
    INTERNAL_STREAM_READER_SCHEMA,
    WorkerRole,
    WorkerSchema,
)
from abi.packets import PacketWriter, create_packet_dir, read_json_file


INTERNAL_READER_STATE_EVAL_LINEAGE_ID = "internal_reader_state_evaluation_v1"
INTERNAL_READER_STATE_EVAL_CREATED_BY = "internal_reader_state_evaluation_v1_controller"
INTERNAL_READER_STATE_EVAL_CLIENT_FAKE = "fake"
INTERNAL_READER_STATE_EVAL_CLIENT_OPENAI = "openai"
INTERNAL_READER_STATE_EVAL_CLIENTS = (
    INTERNAL_READER_STATE_EVAL_CLIENT_FAKE,
    INTERNAL_READER_STATE_EVAL_CLIENT_OPENAI,
)
INTERNAL_READER_STATE_EVAL_MAX_MODEL_CALLS_DEFAULT = 8
INTERNAL_READER_STATE_EVAL_LIVE_WORKERS = (
    INTERNAL_STREAM_READER_SCHEMA,
    INTERNAL_REREAD_READER_SCHEMA,
    FORENSIC_GROUNDING_READER_SCHEMA,
    HOSTILE_INTERNAL_READER_SCHEMA,
    INTERNAL_RIVAL_COMPARISON_SCHEMA,
)
INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES = (
    "internal_reader_state_eval_subject_manifest",
    "selected_candidate_reader_subject",
    "first_pass_reader_state_trace",
    "reread_reader_state_trace",
    "opening_return_transformation_report",
    "reader_delta_report",
    "proof_constraint_carry_report",
    "rival_reader_state_comparison",
    "hostile_reader_state_report",
    "forensic_grounding_reader_report",
    "residual_blocker_reader_report",
    "internal_reader_state_eval_gate_report",
    "internal_reader_state_eval_packet",
)


@dataclass(frozen=True)
class ReaderStateEvaluationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_records: tuple[GateRecord, ...] = ()
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class ReaderStateSubject:
    run_id: str
    synthesis_packet_dir: Path
    synthesis_packet_id: str
    synthesis_packet_artifact_id: str | None
    synthesis_artifact_ids: dict[str, str]
    synthesis_payloads: dict[str, dict[str, Any]]
    selected_candidate: dict[str, Any]
    selected_candidate_packet_dir: Path
    selected_candidate_packet_payload: dict[str, Any]
    selected_candidate_artifact_id: str | None
    selected_candidate_text: str
    selected_candidate_text_sha256: str
    selected_base_packet_dir: Path | None
    selected_base_packet_id: str | None
    selected_base_text: str | None
    selected_base_text_sha256: str | None
    strongest_rival_packet_dir: Path | None
    strongest_rival_artifact_id: str | None
    strongest_rival_text: str | None
    strongest_rival_text_sha256: str | None
    macro_ablation_packet_dir: Path | None
    macro_ablation_packet_id: str | None
    macro_ablation_evidence: dict[str, Any]
    source_parent_ids: tuple[str, ...]

    @property
    def has_strongest_rival(self) -> bool:
        return bool(self.strongest_rival_text)


def run_internal_reader_state_evaluation(
    config: AbiConfig,
    *,
    client_name: str,
    synthesis_packet: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = INTERNAL_READER_STATE_EVAL_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> ReaderStateEvaluationResult:
    if client_name not in INTERNAL_READER_STATE_EVAL_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            synthesis_packet=synthesis_packet,
            message=f"Unsupported internal reader-state evaluation client: {client_name}",
        )
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < 0:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            synthesis_packet=synthesis_packet,
            message="Internal reader-state evaluation refused; max-model-calls must be non-negative.",
        )
    if client_name == INTERNAL_READER_STATE_EVAL_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            synthesis_packet=synthesis_packet,
            message=(
                "Internal reader-state evaluation refused; pass --allow-live-model "
                "to opt in explicitly."
            ),
        )
    resolved_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == INTERNAL_READER_STATE_EVAL_CLIENT_OPENAI and not resolved_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            synthesis_packet=synthesis_packet,
            message=f"Internal reader-state evaluation refused; {OPENAI_API_KEY_ENV} is not set.",
        )
    if (
        client_name == INTERNAL_READER_STATE_EVAL_CLIENT_OPENAI
        and max_model_calls < len(INTERNAL_READER_STATE_EVAL_LIVE_WORKERS)
    ):
        return _refusal(
            client_name=client_name,
            model=configured_model,
            synthesis_packet=synthesis_packet,
            message=(
                "Internal reader-state evaluation refused; max-model-calls "
                f"{max_model_calls} is below required budget "
                f"{len(INTERNAL_READER_STATE_EVAL_LIVE_WORKERS)}."
            ),
        )

    initialize_database(config)
    source_packet_dir = _resolve_path(config, synthesis_packet)
    if not source_packet_dir.exists() or not source_packet_dir.is_dir():
        return _refusal(
            client_name=client_name,
            model=configured_model,
            synthesis_packet=source_packet_dir,
            message=(
                "Internal reader-state evaluation refused; synthesis packet "
                f"directory not found: {source_packet_dir}"
            ),
        )

    try:
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, config, source_packet_dir)
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    client_name=client_name,
                    model=configured_model,
                    synthesis_packet=source_packet_dir,
                    message=(
                        "Internal reader-state evaluation refused; source run is "
                        f"not registered: {subject.run_id}"
                    ),
                )
            packet_dir = create_packet_dir(
                config.run_dir(subject.run_id) / "internal_reader_state_evaluation"
            )
            set_active_phase(
                connection,
                subject.run_id,
                AUTONOMOUS_INTERNAL_READER_STATE_EVALUATION_ACTIVE_PHASE,
            )
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            synthesis_packet=source_packet_dir,
            message=f"Internal reader-state evaluation refused; invalid synthesis packet: {error}",
        )

    if client_name == INTERNAL_READER_STATE_EVAL_CLIENT_OPENAI:
        factory = client_factory or _default_openai_client_factory
        return _run_live_eval(
            config=config,
            subject=subject,
            packet_dir=packet_dir,
            model=configured_model,
            model_client=factory(configured_model),
            max_model_calls=max_model_calls,
        )

    with connect(config.db_path) as connection:
        artifacts, payloads = _write_fake_eval_packet(
            connection=connection,
            subject=subject,
            packet_dir=packet_dir,
        )
        gate_records = _record_eval_gates(
            connection=connection,
            run_id=subject.run_id,
            gate_report=payloads["internal_reader_state_eval_gate_report"],
        )
    return ReaderStateEvaluationResult(
        exit_code=0,
        payload=_summary_payload(
            accepted=True,
            refused=False,
            client_name=client_name,
            model=None,
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            gate_records=gate_records,
            model_results=[],
            message=None,
        ),
        artifacts=tuple(artifacts.values()),
        gate_records=tuple(gate_records),
    )


def _write_fake_eval_packet(
    *,
    connection,
    subject: ReaderStateSubject,
    packet_dir: Path,
) -> tuple[dict[str, ArtifactRecord], dict[str, dict[str, Any]]]:
    writer = PacketWriter(
        connection=connection,
        run_id=subject.run_id,
        packet_dir=packet_dir,
        lineage_id=INTERNAL_READER_STATE_EVAL_LINEAGE_ID,
        created_by=INTERNAL_READER_STATE_EVAL_CREATED_BY,
        fixture_only=True,
        model_call_id=None,
    )
    return _write_eval_payloads(
        writer=writer,
        subject=subject,
        packet_dir=packet_dir,
        fixture_only=True,
        model_payloads={},
        model_results=[],
    )


def _run_live_eval(
    *,
    config: AbiConfig,
    subject: ReaderStateSubject,
    packet_dir: Path,
    model: str,
    model_client: ModelClient,
    max_model_calls: int,
) -> ReaderStateEvaluationResult:
    model_payloads: dict[str, dict[str, Any]] = {}
    model_results: list[ModelDriverResult] = []
    driver = ModelDriver(config=config, client=model_client)
    for index, schema in enumerate(INTERNAL_READER_STATE_EVAL_LIVE_WORKERS, start=1):
        if index > max_model_calls:
            return _live_failure_result(
                subject=subject,
                packet_dir=packet_dir,
                model=model,
                model_results=model_results,
                message="Internal reader-state evaluation stopped by max-model-calls budget.",
            )
        result = driver.run(
            WorkerRequest(
                run_id=subject.run_id,
                worker_role=_worker_role_for_schema(schema),
                prompt_contract_id=f"autonomous.reader_state_eval.{schema.artifact_type}.v1",
                schema=schema,
                input_text=_model_prompt(subject, schema, model_payloads),
                input_artifact_ids=list(subject.source_parent_ids),
                input_packet_path=str(subject.synthesis_packet_dir),
                lineage_id=INTERNAL_READER_STATE_EVAL_LINEAGE_ID,
                parent_ids=list(subject.source_parent_ids),
                fixture_only=False,
                output_dir=str(packet_dir),
                register_parsed_artifact=False,
            )
        )
        model_results.append(result)
        if not result.accepted or result.parsed_payload is None:
            return _live_failure_result(
                subject=subject,
                packet_dir=packet_dir,
                model=model,
                model_results=model_results,
                message="Internal reader-state evaluation stopped by model-call failure.",
            )
        model_payloads[schema.artifact_type] = result.parsed_payload

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=INTERNAL_READER_STATE_EVAL_LINEAGE_ID,
            created_by="internal_reader_state_evaluation_v1_model_driver",
            fixture_only=False,
            model_call_id=None,
        )
        artifacts, payloads = _write_eval_payloads(
            writer=writer,
            subject=subject,
            packet_dir=packet_dir,
            fixture_only=False,
            model_payloads=model_payloads,
            model_results=model_results,
        )
        gate_records = _record_eval_gates(
            connection=connection,
            run_id=subject.run_id,
            gate_report=payloads["internal_reader_state_eval_gate_report"],
        )
    return ReaderStateEvaluationResult(
        exit_code=0,
        payload=_summary_payload(
            accepted=True,
            refused=False,
            client_name=INTERNAL_READER_STATE_EVAL_CLIENT_OPENAI,
            model=model,
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            gate_records=gate_records,
            model_results=model_results,
            message=None,
        ),
        artifacts=tuple(artifacts.values()),
        gate_records=tuple(gate_records),
        model_results=tuple(model_results),
    )


def _write_eval_payloads(
    *,
    writer: PacketWriter,
    subject: ReaderStateSubject,
    packet_dir: Path,
    fixture_only: bool,
    model_payloads: dict[str, dict[str, Any]],
    model_results: list[ModelDriverResult],
) -> tuple[dict[str, ArtifactRecord], dict[str, dict[str, Any]]]:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}
    model_call_by_source = _model_call_by_source(model_results)

    def write(
        artifact_type: str,
        payload: dict[str, Any],
        parent_ids: list[str],
        *,
        model_source_artifact_type: str | None = None,
    ) -> None:
        old_model_call_id = writer.model_call_id
        if model_source_artifact_type is not None:
            writer.model_call_id = model_call_by_source.get(model_source_artifact_type)
        try:
            artifacts[artifact_type] = writer.write_artifact(
                artifact_type,
                payload,
                parent_ids=parent_ids,
            )
        finally:
            writer.model_call_id = old_model_call_id
        payloads[artifact_type] = payload

    payloads["internal_reader_state_eval_subject_manifest"] = _build_subject_manifest(
        subject,
        packet_dir=packet_dir,
        fixture_only=fixture_only,
    )
    artifacts["internal_reader_state_eval_subject_manifest"] = writer.write_artifact(
        "internal_reader_state_eval_subject_manifest",
        payloads["internal_reader_state_eval_subject_manifest"],
        parent_ids=list(subject.source_parent_ids),
    )

    write(
        "selected_candidate_reader_subject",
        _build_selected_candidate_reader_subject(subject, fixture_only=fixture_only),
        [artifacts["internal_reader_state_eval_subject_manifest"].id],
    )
    write(
        "first_pass_reader_state_trace",
        _build_first_pass_trace(subject, model_payloads, fixture_only=fixture_only),
        [artifacts["selected_candidate_reader_subject"].id],
        model_source_artifact_type=INTERNAL_STREAM_READER_SCHEMA.artifact_type,
    )
    write(
        "reread_reader_state_trace",
        _build_reread_trace(subject, payloads, model_payloads, fixture_only=fixture_only),
        [
            artifacts["selected_candidate_reader_subject"].id,
            artifacts["first_pass_reader_state_trace"].id,
        ],
        model_source_artifact_type=INTERNAL_REREAD_READER_SCHEMA.artifact_type,
    )
    write(
        "opening_return_transformation_report",
        _build_opening_return_report(subject, payloads, fixture_only=fixture_only),
        [
            artifacts["first_pass_reader_state_trace"].id,
            artifacts["reread_reader_state_trace"].id,
        ],
    )
    write(
        "reader_delta_report",
        _build_reader_delta_report(subject, payloads, fixture_only=fixture_only),
        [
            artifacts["first_pass_reader_state_trace"].id,
            artifacts["reread_reader_state_trace"].id,
            artifacts["opening_return_transformation_report"].id,
        ],
    )
    write(
        "proof_constraint_carry_report",
        _build_proof_constraint_report(subject, payloads, fixture_only=fixture_only),
        [
            artifacts["selected_candidate_reader_subject"].id,
            artifacts["reader_delta_report"].id,
        ],
    )
    write(
        "rival_reader_state_comparison",
        _build_rival_comparison(subject, model_payloads, fixture_only=fixture_only),
        [
            artifacts["selected_candidate_reader_subject"].id,
            artifacts["reader_delta_report"].id,
        ],
        model_source_artifact_type=INTERNAL_RIVAL_COMPARISON_SCHEMA.artifact_type,
    )
    write(
        "hostile_reader_state_report",
        _build_hostile_report(subject, model_payloads, fixture_only=fixture_only),
        [
            artifacts["selected_candidate_reader_subject"].id,
            artifacts["proof_constraint_carry_report"].id,
        ],
        model_source_artifact_type=HOSTILE_INTERNAL_READER_SCHEMA.artifact_type,
    )
    write(
        "forensic_grounding_reader_report",
        _build_forensic_report(subject, model_payloads, fixture_only=fixture_only),
        [
            artifacts["selected_candidate_reader_subject"].id,
            artifacts["reader_delta_report"].id,
        ],
        model_source_artifact_type=FORENSIC_GROUNDING_READER_SCHEMA.artifact_type,
    )
    write(
        "residual_blocker_reader_report",
        _build_residual_blocker_report(subject, payloads, fixture_only=fixture_only),
        [
            artifacts["rival_reader_state_comparison"].id,
            artifacts["hostile_reader_state_report"].id,
            artifacts["forensic_grounding_reader_report"].id,
        ],
    )
    write(
        "internal_reader_state_eval_gate_report",
        _build_gate_report(subject, payloads, fixture_only=fixture_only),
        [
            artifacts["first_pass_reader_state_trace"].id,
            artifacts["reread_reader_state_trace"].id,
            artifacts["reader_delta_report"].id,
            artifacts["rival_reader_state_comparison"].id,
            artifacts["hostile_reader_state_report"].id,
            artifacts["forensic_grounding_reader_report"].id,
            artifacts["residual_blocker_reader_report"].id,
        ],
    )
    write(
        "internal_reader_state_eval_packet",
        _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            fixture_only=fixture_only,
            model_results=model_results,
        ),
        [
            artifacts[artifact_type].id
            for artifact_type in INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES[:-1]
        ],
    )
    return artifacts, payloads


def _build_subject_manifest(
    subject: ReaderStateSubject,
    *,
    packet_dir: Path,
    fixture_only: bool,
) -> dict[str, Any]:
    return {
        "worker": "internal_reader_state_eval_subject_manifest_v1_controller",
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_synthesis_packet_artifact_id": subject.synthesis_packet_artifact_id,
        "selected_candidate_packet_id": subject.selected_candidate["packet_id"],
        "selected_candidate_packet_kind": subject.selected_candidate["packet_kind"],
        "selected_candidate_packet_dir": str(subject.selected_candidate_packet_dir),
        "selected_candidate_artifact_id": subject.selected_candidate_artifact_id,
        "selected_candidate_text_sha256": subject.selected_candidate_text_sha256,
        "selected_base_packet_id": subject.selected_base_packet_id,
        "selected_base_packet_dir": str(subject.selected_base_packet_dir)
        if subject.selected_base_packet_dir is not None
        else None,
        "strongest_rival_packet_dir": str(subject.strongest_rival_packet_dir)
        if subject.strongest_rival_packet_dir is not None
        else None,
        "strongest_rival_artifact_id": subject.strongest_rival_artifact_id,
        "strongest_rival_present": subject.has_strongest_rival,
        "macro_ablation_packet_id": subject.macro_ablation_packet_id,
        "macro_ablation_packet_dir": str(subject.macro_ablation_packet_dir)
        if subject.macro_ablation_packet_dir is not None
        else None,
        "strategy_consumed": subject.synthesis_payloads["strategic_decision_report"].get(
            "recommendation"
        ),
        "next_recommended_action_consumed": subject.synthesis_payloads[
            "strategic_decision_report"
        ].get("next_recommended_action"),
        "fixture_only": fixture_only,
        "not_human_data": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
    }


def _build_selected_candidate_reader_subject(
    subject: ReaderStateSubject,
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    return {
        "worker": "selected_candidate_reader_subject_v1_controller",
        "evaluation_subject": "synthesis_selected_best_candidate",
        "reader_comparison_subjects": [
            "selected_macro_candidate",
            "prior_best_candidate",
            "strongest_rival",
        ],
        "selected_macro_candidate": {
            "packet_id": subject.selected_candidate["packet_id"],
            "packet_kind": subject.selected_candidate["packet_kind"],
            "packet_dir": str(subject.selected_candidate_packet_dir),
            "candidate_artifact_id": subject.selected_candidate_artifact_id,
            "text_sha256": subject.selected_candidate_text_sha256,
            "word_count": len(_words(subject.selected_candidate_text)),
            "target_movement": subject.selected_candidate.get("target_movement"),
            "non_final": True,
            "not_human_validated": True,
            "not_finalization_eligible": True,
            "no_phase_shift_claim": True,
        },
        "prior_best_candidate": {
            "packet_id": subject.selected_base_packet_id,
            "packet_dir": str(subject.selected_base_packet_dir)
            if subject.selected_base_packet_dir is not None
            else None,
            "text_sha256": subject.selected_base_text_sha256,
            "word_count": len(_words(subject.selected_base_text or "")),
        },
        "strongest_rival": {
            "present": subject.has_strongest_rival,
            "artifact_id": subject.strongest_rival_artifact_id,
            "packet_dir": str(subject.strongest_rival_packet_dir)
            if subject.strongest_rival_packet_dir is not None
            else None,
            "text_sha256": subject.strongest_rival_text_sha256,
            "word_count": len(_words(subject.strongest_rival_text or "")),
            "comparison_gate_satisfied": False,
        },
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_first_pass_trace(
    subject: ReaderStateSubject,
    model_payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    model_payload = model_payloads.get(INTERNAL_STREAM_READER_SCHEMA.artifact_type)
    text = subject.selected_candidate_text
    retained = _retained_images(text)
    return {
        "worker": "first_pass_reader_state_trace_v1",
        "source": "model_driver" if model_payload else "deterministic_fake_controller",
        "model_reader_trace": model_payload,
        "what_survives_first_read": model_payload.get("retained_images", retained)
        if model_payload
        else retained,
        "what_feels_concrete": retained,
        "what_feels_explained_rather_than_enacted": _overexplicit_terms(text),
        "confusion_points": model_payload.get("confusion_points", _confusion_points(text))
        if model_payload
        else _confusion_points(text),
        "motifs_remain_active": _live_motifs(text),
        "opening_field_retained": all(
            term in text.lower() for term in ("table", "dust", "spoon", "saucer")
        ),
        "first_read_summary": model_payload.get("first_read_summary")
        if model_payload
        else (
            "The table field remains concrete, but the first pass still notices "
            "explanatory pressure around proof and answer."
        ),
        "fixture_only": fixture_only,
        "not_human_data": True,
    }


def _build_reread_trace(
    subject: ReaderStateSubject,
    payloads: dict[str, dict[str, Any]],
    model_payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    model_payload = model_payloads.get(INTERNAL_REREAD_READER_SCHEMA.artifact_type)
    text = subject.selected_candidate_text
    motifs = payloads["first_pass_reader_state_trace"]["motifs_remain_active"]
    return {
        "worker": "reread_reader_state_trace_v1",
        "source": "model_driver" if model_payload else "deterministic_fake_controller",
        "model_reader_trace": model_payload,
        "ending_changes_opening": bool(model_payload.get("opening_changed", True))
        if model_payload
        else True,
        "opening_becomes_more_necessary_after_return": "still there" in text.lower(),
        "table_dust_spoon_saucer_transformed": all(
            motif in motifs for motif in ("table", "dust", "spoon", "saucer")
        ),
        "proof_no_outside_answer_logic": _proof_logic_state(text),
        "cosmic_silence_as_formal_condition": "formal" in text.lower()
        or "outside" in text.lower(),
        "return_without_regression": "return" in text.lower()
        and "regression" in text.lower(),
        "motif_returned_changed": model_payload.get("motif_returned_changed", [])
        if model_payload
        else [
            {
                "motif": motif,
                "first_read_state": "visible",
                "reread_state": "tested for transformed return",
            }
            for motif in motifs
        ],
        "reread_summary": model_payload.get("reread_summary")
        if model_payload
        else "Reread makes the opening table field more necessary, but not fully proven.",
        "fixture_only": fixture_only,
        "not_human_data": True,
    }


def _build_opening_return_report(
    subject: ReaderStateSubject,
    payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    first = payloads["first_pass_reader_state_trace"]
    reread = payloads["reread_reader_state_trace"]
    return {
        "worker": "opening_return_transformation_report_v1_controller",
        "opening_field_retained": first["opening_field_retained"],
        "ending_changes_opening": reread["ending_changes_opening"],
        "opening_return_transformation_strength": "partial",
        "changed_interpretation_of_opening": (
            "The table/dust/spoon/saucer field becomes a record-bearing field "
            "rather than only a domestic scene."
        ),
        "changed_interpretation_of_ending": (
            "The ending is read as return-with-record, but the transformation still "
            "requires internal reader proof before any improvement claim."
        ),
        "opening_return_transformation_unproven": True,
        "candidate_text_sha256": subject.selected_candidate_text_sha256,
        "fixture_only": fixture_only,
        "not_human_data": True,
    }


def _build_reader_delta_report(
    subject: ReaderStateSubject,
    payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    first = payloads["first_pass_reader_state_trace"]
    reread = payloads["reread_reader_state_trace"]
    inert = [
        motif
        for motif in ("proof", "answer", "silence")
        if motif not in subject.selected_candidate_text.lower()
    ]
    causal_motifs = [
        motif
        for motif in first["motifs_remain_active"]
        if motif in ("table", "dust", "spoon", "saucer", "ring")
    ]
    return {
        "worker": "reader_delta_report_v1_controller",
        "initial_reader_state": "concrete_table_field_with_explanatory_pressure",
        "post_reread_reader_state": "partial_opening_return_transformation",
        "delta_reader_state_summary": (
            "Reread increases necessity of the opening field, but strongest-rival "
            "pressure and proof/no-outside-answer carry remain unresolved."
        ),
        "changed_interpretation_of_opening": payloads[
            "opening_return_transformation_report"
        ]["changed_interpretation_of_opening"],
        "changed_interpretation_of_middle": (
            "Middle movement reads as more compressed and object-mediated than the "
            "prior local patch regime."
        ),
        "changed_interpretation_of_ending": payloads[
            "opening_return_transformation_report"
        ]["changed_interpretation_of_ending"],
        "motifs_that_became_causal_after_reread": causal_motifs,
        "motifs_that_remained_inert": inert,
        "uncertainty": [
            "No human reader data is present.",
            "Internal reader-state evidence remains provisional.",
            "Strongest rival still blocks first-read vividness and object-event pressure.",
        ],
        "reread_gain_estimate": "partial",
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "candidate_final": False,
        "selected_candidate_text_sha256": subject.selected_candidate_text_sha256,
        "reread_trace_summary": reread["reread_summary"],
    }


def _build_proof_constraint_report(
    subject: ReaderStateSubject,
    payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    text = subject.selected_candidate_text
    constraints = [
        "table/dust/spoon/saucer local field",
        "proof arises inside the line",
        "no outside answer",
        "return without regression",
        "strongest-rival pressure preserved",
    ]
    carried = [
        constraint
        for constraint in constraints
        if _constraint_carried(text, constraint)
    ]
    unsupported = [constraint for constraint in constraints if constraint not in carried]
    return {
        "worker": "proof_constraint_carry_report_v1_controller",
        "constraints_checked": constraints,
        "constraints_carried_by_actual_wording": carried,
        "unsupported_or_weak_constraints": unsupported,
        "proof_logic_felt_as_structure": "partial",
        "summary_replacing_behavior_risk": bool(
            payloads["first_pass_reader_state_trace"][
                "what_feels_explained_rather_than_enacted"
            ]
        ),
        "local_field_supports_metaphysical_movement": bool(
            {"table", "dust", "spoon", "saucer"}.issubset(set(_words(text.lower())))
        ),
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_rival_comparison(
    subject: ReaderStateSubject,
    model_payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    model_payload = model_payloads.get(INTERNAL_RIVAL_COMPARISON_SCHEMA.artifact_type)
    candidate_score = _reader_score(subject.selected_candidate_text)
    rival_score = _reader_score(subject.strongest_rival_text or "")
    rival_present = subject.has_strongest_rival
    rival_still_wins = rival_present and rival_score["local_embodiment"] >= candidate_score[
        "local_embodiment"
    ]
    return {
        "worker": "rival_reader_state_comparison_v1",
        "source": "model_driver" if model_payload else "deterministic_fake_controller",
        "model_reader_comparison": model_payload,
        "strongest_rival_present": rival_present,
        "strongest_rival_artifact_id": subject.strongest_rival_artifact_id,
        "macro_candidate_narrowed_rival_gap": True,
        "rival_still_wins_on_first_read_vividness": rival_still_wins,
        "rival_still_wins_on_lived_object_event_pressure": rival_still_wins,
        "macro_candidate_improves_structural_return": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_comparison_passed": False,
        "candidate_scores": candidate_score,
        "rival_scores": rival_score if rival_present else None,
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_hostile_report(
    subject: ReaderStateSubject,
    model_payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    model_payload = model_payloads.get(HOSTILE_INTERNAL_READER_SCHEMA.artifact_type)
    text = subject.selected_candidate_text.lower()
    risks = [
        "fake_depth",
        "overexplanation",
        "scaffold_leakage",
        "pressure_word_overuse",
        "thesis_replacing_artifact",
        "wrong_register",
        "accidental_abstraction",
        "ending_explaining_its_own_return",
        "cosmic_silence_as_slogan",
    ]
    active = [
        risk
        for risk in risks
        if risk in {"overexplanation", "thesis_replacing_artifact", "cosmic_silence_as_slogan"}
        or (risk == "pressure_word_overuse" and text.count("pressure") > 5)
    ]
    return {
        "worker": "hostile_reader_state_report_v1",
        "source": "model_driver" if model_payload else "deterministic_fake_controller",
        "model_hostile_report": model_payload,
        "risk_categories_checked": risks,
        "blocking_or_active_risks": active,
        "fake_depth": "monitored",
        "overexplanation": "still possible in proof/answer language",
        "scaffold_leakage": "not detected as packet metadata in candidate text",
        "pressure_word_overuse": text.count("pressure"),
        "thesis_replacing_artifact": "active risk until reader-state delta is stronger",
        "wrong_register": "monitored",
        "accidental_abstraction": "monitored in middle movement",
        "ending_explaining_its_own_return": "active risk",
        "cosmic_silence_as_slogan": "active risk if not felt as formal condition",
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_forensic_report(
    subject: ReaderStateSubject,
    model_payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    model_payload = model_payloads.get(FORENSIC_GROUNDING_READER_SCHEMA.artifact_type)
    text = subject.selected_candidate_text
    claims = [
        "opening table field is retained",
        "return changes the opening",
        "proof/no-outside-answer logic is present",
        "strongest rival remains blocking",
    ]
    return {
        "worker": "forensic_grounding_reader_report_v1",
        "source": "model_driver" if model_payload else "deterministic_fake_controller",
        "model_forensic_report": model_payload,
        "claims_grounded_in_text": [
            {
                "claim": claim,
                "quoted_span": _support_snippet(text, claim),
                "grounded": True,
            }
            for claim in claims[:3]
        ],
        "unsupported_reader_state_claims": [
            "phase-shift-level transformation",
            "strongest-rival defeat",
            "human validation",
        ],
        "proof_constraints_carried_by_actual_wording": "partial",
        "local_field_supports_metaphysical_movement": True,
        "strongest_claims_rely_on_summary": True,
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_residual_blocker_report(
    subject: ReaderStateSubject,
    payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    synthesis_blockers = subject.synthesis_payloads["residual_blocker_map"].get(
        "residual_blockers",
        [],
    )
    blockers = [
        "proof_no_outside_answer_refinement",
        "final_return_echo_reread_strength",
        "strongest_rival_still_winning",
        "over_compression_risk",
        "local_embodiment_vs_compression_balance",
        "reader_state_opening_return_transformation_still_unproven",
    ]
    if payloads["hostile_reader_state_report"]["blocking_or_active_risks"]:
        blockers.append("hostile_reader_active_risks")
    return {
        "worker": "residual_blocker_reader_report_v1_controller",
        "source_synthesis_blockers": synthesis_blockers,
        "reader_state_blockers": blockers,
        "new_blockers_discovered": [
            "hostile_reader_active_risks"
        ]
        if "hostile_reader_active_risks" in blockers
        else [],
        "proof_no_outside_answer_refinement": "active",
        "final_return_echo_reread_strength": "unproven",
        "strongest_rival_still_winning": True,
        "over_compression_risk": "monitored",
        "local_embodiment_vs_compression_balance": "active",
        "opening_return_transformation_still_weak_or_unproven": True,
        "recommended_next_action": "operator_review_reader_state_evaluation",
        "does_not_revise": True,
        "does_not_run_ablation": True,
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_gate_report(
    subject: ReaderStateSubject,
    payloads: dict[str, dict[str, Any]],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    blocker_report = payloads["residual_blocker_reader_report"]
    strongest_rival_still_blocks = bool(
        payloads["rival_reader_state_comparison"]["strongest_rival_still_blocks"]
    )
    gate_results = [
        _gate_result("internal_reader_state_eval_packet_exists", True),
        _gate_result("synthesis_packet_consumed", True),
        _gate_result("selected_candidate_evaluated", True),
        _gate_result("first_pass_trace_exists", True),
        _gate_result("reread_trace_exists", True),
        _gate_result("reader_delta_report_exists", True),
        _gate_result("rival_reader_state_comparison_exists", True),
        _gate_result("hostile_reader_report_exists", True),
        _gate_result("forensic_grounding_report_exists", True),
        _gate_result("rival_preservation_present", subject.has_strongest_rival),
        _gate_result(
            "no_fixture_only_core_evidence",
            not fixture_only,
            ["fake reader-state evaluation is fixture-only"] if fixture_only else [],
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            [
                *[
                    f"reader-state blocker remains: {blocker}"
                    for blocker in blocker_report["reader_state_blockers"]
                ],
                "strongest-rival pressure remains blocking"
                if strongest_rival_still_blocks
                else "operator review is still required",
            ],
        ),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator approval is intentionally absent"],
            record=False,
        ),
    ]
    failed = [
        str(gate["gate_name"])
        for gate in gate_results
        if bool(gate["record"]) and not bool(gate["passed"])
    ]
    missing = [str(gate["gate_name"]) for gate in gate_results if not bool(gate["record"])]
    return {
        "worker": "internal_reader_state_eval_gate_report_v1_controller",
        "profile": "autonomous_creative_candidate",
        "passed": False,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "human_validation_required": False,
        "final_gates_marked_passed": [],
        "strongest_rival_pressure_preserved": True,
        "strongest_rival_still_blocks": strongest_rival_still_blocks,
        "requires_further_ablation_recomposition_or_operator_decision": True,
        "gate_results": gate_results,
        "failed_gates": failed,
        "missing_gates": missing,
        "unresolved_blockers": blocker_report["reader_state_blockers"],
        "summary_verdict": (
            "Internal reader-state evaluation exists for the synthesis-selected "
            "macro candidate, but blockers and missing operator approval keep "
            "finalization fail-closed."
        ),
        "fixture_only": fixture_only,
    }


def _build_packet_summary(
    *,
    subject: ReaderStateSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    fixture_only: bool,
    model_results: list[ModelDriverResult],
) -> dict[str, Any]:
    gate = payloads["internal_reader_state_eval_gate_report"]
    return {
        "worker": "internal_reader_state_eval_packet_v1_controller",
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "selected_candidate_packet_id": subject.selected_candidate["packet_id"],
        "selected_candidate_packet_kind": subject.selected_candidate["packet_kind"],
        "selected_candidate_packet_dir": str(subject.selected_candidate_packet_dir),
        "selected_candidate_artifact_id": subject.selected_candidate_artifact_id,
        "selected_candidate_text_sha256": subject.selected_candidate_text_sha256,
        "prior_best_packet_id": subject.selected_base_packet_id,
        "strongest_rival_present": subject.has_strongest_rival,
        "strongest_rival_artifact_id": subject.strongest_rival_artifact_id,
        "macro_ablation_packet_id": subject.macro_ablation_packet_id,
        "artifact_types": list(INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "internal_reader_state_eval_artifacts": len(artifacts),
            "required_internal_reader_state_eval_artifacts": len(
                INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES
            ),
            "model_calls": len(model_results),
        },
        "model_call_ids": [result.model_call.id for result in model_results],
        "reader_delta_summary": payloads["reader_delta_report"][
            "delta_reader_state_summary"
        ],
        "rival_comparison": {
            "strongest_rival_still_blocks": payloads[
                "rival_reader_state_comparison"
            ]["strongest_rival_still_blocks"],
            "strongest_rival_comparison_passed": False,
        },
        "gate_report": gate,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _load_subject(
    connection,
    config: AbiConfig,
    synthesis_packet_dir: Path,
) -> ReaderStateSubject:
    packet_envelope = read_json_file(
        synthesis_packet_dir / "autonomous_evidence_synthesis_packet.json"
    )
    if packet_envelope.get("artifact_type") != "autonomous_evidence_synthesis_packet":
        raise ValueError("synthesis packet must contain autonomous_evidence_synthesis_packet.json")
    packet_payload = _payload(packet_envelope)
    run_id = str(packet_envelope["run_id"])
    synthesis_packet_id = str(packet_payload.get("packet_id") or synthesis_packet_dir.name)
    artifact_ids = _string_dict(packet_payload.get("artifact_ids", {}))
    required_inputs = (
        "best_current_candidate_selection",
        "strategic_decision_report",
        "macro_recomposition_brief",
        "local_law_case_notes",
        "residual_blocker_map",
        "rival_pressure_summary",
        "causal_status_summary",
    )
    synthesis_payloads = {"autonomous_evidence_synthesis_packet": packet_payload}
    source_parent_ids = list(artifact_ids.values())
    for artifact_type in required_inputs:
        if artifact_type not in artifact_ids:
            raise ValueError(f"synthesis packet is missing artifact ID for {artifact_type}")
        artifact = get_artifact(connection, artifact_ids[artifact_type])
        if artifact is not None:
            synthesis_payloads[artifact_type] = _artifact_payload(artifact)
        else:
            synthesis_payloads[artifact_type] = _payload(
                read_json_file(synthesis_packet_dir / f"{artifact_type}.json")
            )

    best = synthesis_payloads["best_current_candidate_selection"]
    selected = best.get("selected_best_candidate")
    if not isinstance(selected, dict):
        raise ValueError("best_current_candidate_selection has no selected_best_candidate")
    if selected.get("packet_kind") != "bounded_macro_recomposition":
        raise ValueError("selected best candidate is not a bounded_macro_recomposition packet")
    candidate_packet_dir = _resolve_path(config, str(selected["packet_dir"]))
    candidate_packet = _payload(
        read_json_file(candidate_packet_dir / "macro_recomposition_packet.json")
    )
    candidate_text_payload = _payload(
        read_json_file(candidate_packet_dir / "macro_recomposed_candidate_text.json")
    )
    candidate_text = str(candidate_text_payload["text"])
    selected_base_packet_dir = _optional_path(
        config,
        candidate_packet.get("base_candidate_packet_dir"),
    )
    selected_base_text = _load_candidate_text_from_packet(selected_base_packet_dir)
    selected_base_sha = sha256_text(selected_base_text) if selected_base_text else None
    pilot_packet_dir = _pilot_packet_dir_for_rival(packet_payload)
    strongest_rival_text, strongest_rival_artifact_id = _load_strongest_rival(
        connection,
        pilot_packet_dir,
    )
    macro_ablation_packet_dir = _source_packet_dir(
        packet_payload,
        "executed_ablation",
        subject_kind="bounded_macro_recomposition",
        source_revision_packet_id=str(selected["packet_id"]),
    )
    macro_evidence = _load_macro_ablation_evidence(macro_ablation_packet_dir)
    packet_artifact = _artifact_by_path(
        connection,
        run_id=run_id,
        artifact_path=synthesis_packet_dir / "autonomous_evidence_synthesis_packet.json",
    )
    if packet_artifact is not None:
        source_parent_ids.append(packet_artifact.id)
    if selected.get("candidate_artifact_id"):
        source_parent_ids.append(str(selected["candidate_artifact_id"]))
    if strongest_rival_artifact_id:
        source_parent_ids.append(strongest_rival_artifact_id)
    return ReaderStateSubject(
        run_id=run_id,
        synthesis_packet_dir=synthesis_packet_dir,
        synthesis_packet_id=synthesis_packet_id,
        synthesis_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        synthesis_artifact_ids=artifact_ids,
        synthesis_payloads=synthesis_payloads,
        selected_candidate=selected,
        selected_candidate_packet_dir=candidate_packet_dir,
        selected_candidate_packet_payload=candidate_packet,
        selected_candidate_artifact_id=str(selected.get("candidate_artifact_id") or ""),
        selected_candidate_text=candidate_text,
        selected_candidate_text_sha256=str(candidate_text_payload["text_sha256"]),
        selected_base_packet_dir=selected_base_packet_dir,
        selected_base_packet_id=str(candidate_packet.get("base_candidate_packet_id") or ""),
        selected_base_text=selected_base_text,
        selected_base_text_sha256=selected_base_sha,
        strongest_rival_packet_dir=pilot_packet_dir,
        strongest_rival_artifact_id=strongest_rival_artifact_id,
        strongest_rival_text=strongest_rival_text,
        strongest_rival_text_sha256=sha256_text(strongest_rival_text)
        if strongest_rival_text
        else None,
        macro_ablation_packet_dir=macro_ablation_packet_dir,
        macro_ablation_packet_id=macro_ablation_packet_dir.name
        if macro_ablation_packet_dir is not None
        else None,
        macro_ablation_evidence=macro_evidence,
        source_parent_ids=tuple(_unique(source_parent_ids)),
    )


def _load_candidate_text_from_packet(packet_dir: Path | None) -> str | None:
    if packet_dir is None:
        return None
    for filename in (
        "macro_recomposed_candidate_text.json",
        "cycle2_revised_candidate_text.json",
        "revised_candidate_text.json",
    ):
        path = packet_dir / filename
        if path.exists():
            payload = _payload(read_json_file(path))
            text = payload.get("text")
            return str(text) if isinstance(text, str) else None
    return None


def _load_strongest_rival(connection, packet_dir: Path | None) -> tuple[str | None, str | None]:
    if packet_dir is None:
        return None, None
    import_path = packet_dir / "pilot_strongest_rival_import.json"
    if import_path.exists():
        payload = _payload(read_json_file(import_path))
        text = payload.get("text")
        artifact = _artifact_by_path(
            connection,
            run_id=str(read_json_file(import_path)["run_id"]),
            artifact_path=import_path,
        )
        return (str(text) if isinstance(text, str) else None), artifact.id if artifact else None
    bundle = _payload(read_json_file(packet_dir / "pilot_blinded_reader_bundle.json"))
    label_map = _payload(read_json_file(packet_dir / "pilot_neutral_label_map_private.json"))
    for item in bundle.get("reader_items", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", ""))
        private = label_map.get("label_map", {}).get(label, {})
        if isinstance(private, dict) and private.get("source_class") == "strongest_rival":
            return str(item.get("text", "")), str(private.get("artifact_id") or "")
    return None, None


def _load_macro_ablation_evidence(packet_dir: Path | None) -> dict[str, Any]:
    if packet_dir is None:
        return {}
    return {
        "packet": _payload(read_json_file(packet_dir / "executed_ablation_packet.json")),
        "causal_effect_report": _payload(
            read_json_file(packet_dir / "ablation_causal_effect_report.json")
        ),
        "old_new_rival_comparison": _payload(
            read_json_file(packet_dir / "ablation_old_new_rival_comparison.json")
        ),
    }


def _source_packet_dir(
    packet_payload: dict[str, Any],
    packet_kind: str,
    *,
    subject_kind: str | None = None,
    source_revision_packet_id: str | None = None,
) -> Path | None:
    for source in packet_payload.get("source_chain", []):
        if not isinstance(source, dict) or source.get("packet_kind") != packet_kind:
            continue
        if subject_kind is not None and source.get("subject_kind") != subject_kind:
            continue
        if (
            source_revision_packet_id is not None
            and source.get("source_revision_packet_id") != source_revision_packet_id
        ):
            continue
        packet_dir = source.get("packet_dir")
        return Path(str(packet_dir)) if packet_dir else None
    return None


def _pilot_packet_dir_for_rival(packet_payload: dict[str, Any]) -> Path | None:
    pilot_dirs = [
        Path(str(source["packet_dir"]))
        for source in packet_payload.get("source_chain", [])
        if isinstance(source, dict)
        and source.get("packet_kind") == "pilot_artifact_set"
        and source.get("packet_dir")
    ]
    for packet_dir in reversed(pilot_dirs):
        if (packet_dir / "pilot_strongest_rival_import.json").exists():
            return packet_dir
    for packet_dir in reversed(pilot_dirs):
        label_map_path = packet_dir / "pilot_neutral_label_map_private.json"
        if not label_map_path.exists():
            continue
        try:
            label_map = _payload(read_json_file(label_map_path))
        except (ValueError, json.JSONDecodeError):
            continue
        if any(
            isinstance(item, dict) and item.get("source_class") == "strongest_rival"
            for item in dict(label_map.get("label_map", {})).values()
        ):
            return packet_dir
    return pilot_dirs[-1] if pilot_dirs else None


def _model_prompt(
    subject: ReaderStateSubject,
    schema: WorkerSchema,
    model_payloads: dict[str, dict[str, Any]],
) -> str:
    prompt: dict[str, Any] = {
        "prompt_contract_id": f"autonomous.reader_state_eval.{schema.artifact_type}.v1",
        "schema_name": schema.name,
        "candidate": {
            "label": "Selected Macro Candidate",
            "text": subject.selected_candidate_text,
        },
        "reader_items": [
            {"label": "Selected Macro Candidate", "text": subject.selected_candidate_text},
            {"label": "Prior Best", "text": subject.selected_base_text or ""},
            {"label": "Strongest Rival", "text": subject.strongest_rival_text or ""},
        ],
        "source_items": [
            {
                "label": "Selected Macro Candidate",
                "source_class": "abi_candidate",
                "artifact_id": subject.selected_candidate_artifact_id,
                "text": subject.selected_candidate_text,
            },
            {
                "label": "Prior Best",
                "source_class": "prior_best_candidate",
                "artifact_id": "",
                "text": subject.selected_base_text or "",
            },
            {
                "label": "Strongest Rival",
                "source_class": "strongest_rival",
                "artifact_id": subject.strongest_rival_artifact_id or "",
                "text": subject.strongest_rival_text or "",
            },
        ],
        "source_classes_by_label": {
            "Selected Macro Candidate": "abi_candidate",
            "Prior Best": "prior_best_candidate",
            "Strongest Rival": "strongest_rival",
        },
        "prior_outputs": model_payloads,
        "synthesis_decision": subject.synthesis_payloads["strategic_decision_report"],
        "macro_ablation_evidence": subject.macro_ablation_evidence,
        "not_human_data": True,
    }
    if schema == HOSTILE_INTERNAL_READER_SCHEMA:
        prompt["hostile_attack_target"] = {
            "candidate_label": "Selected Macro Candidate",
            "candidate_text": subject.selected_candidate_text,
        }
    if schema == FORENSIC_GROUNDING_READER_SCHEMA:
        prompt["forensic_grounding_target"] = {
            "candidate_label": "Selected Macro Candidate",
            "candidate_text": subject.selected_candidate_text,
        }
    return json.dumps(prompt, indent=2, sort_keys=True) + "\n"


def _worker_role_for_schema(schema: WorkerSchema) -> WorkerRole:
    if schema == INTERNAL_STREAM_READER_SCHEMA:
        return WorkerRole.INTERNAL_STREAM_READER
    if schema == INTERNAL_REREAD_READER_SCHEMA:
        return WorkerRole.INTERNAL_REREAD_READER
    if schema == INTERNAL_RIVAL_COMPARISON_SCHEMA:
        return WorkerRole.INTERNAL_RIVAL_COMPARATOR
    if schema == HOSTILE_INTERNAL_READER_SCHEMA:
        return WorkerRole.HOSTILE_INTERNAL_READER
    if schema == FORENSIC_GROUNDING_READER_SCHEMA:
        return WorkerRole.FORENSIC_GROUNDING_READER
    raise ValueError(f"unsupported reader-state eval schema: {schema.name}")


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _live_failure_result(
    *,
    subject: ReaderStateSubject,
    packet_dir: Path,
    model: str,
    model_results: list[ModelDriverResult],
    message: str,
) -> ReaderStateEvaluationResult:
    return ReaderStateEvaluationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": False,
            "client": INTERNAL_READER_STATE_EVAL_CLIENT_OPENAI,
            "model": model,
            "run_id": subject.run_id,
            "packet_id": packet_dir.name,
            "packet_dir": str(packet_dir),
            "synthesis_packet_dir": str(subject.synthesis_packet_dir),
            "artifact_ids": {},
            "artifact_paths": {},
            "model_calls": [result.model_call_to_dict() for result in model_results],
            "model_call_ids": [result.model_call.id for result in model_results],
            "message": message,
        },
        model_results=tuple(model_results),
    )


def _record_eval_gates(
    *,
    connection,
    run_id: str,
    gate_report: dict[str, Any],
) -> list[GateRecord]:
    records = []
    for gate_result in gate_report["gate_results"]:
        if not bool(gate_result["record"]):
            continue
        records.append(
            record_gate(
                connection,
                run_id=run_id,
                gate_name=str(gate_result["gate_name"]),
                passed=bool(gate_result["passed"]),
                blocking_defects=list(gate_result["blocking_defects"]),
                lineage_id=INTERNAL_READER_STATE_EVAL_LINEAGE_ID,
            )
        )
    return records


def _summary_payload(
    *,
    accepted: bool,
    refused: bool,
    client_name: str,
    model: str | None,
    subject: ReaderStateSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    gate_records: list[GateRecord],
    model_results: list[ModelDriverResult],
    message: str | None,
) -> dict[str, object]:
    return {
        "accepted": accepted,
        "refused": refused,
        "client": client_name,
        "model": model,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "selected_candidate_packet_id": subject.selected_candidate["packet_id"],
        "selected_candidate_packet_dir": str(subject.selected_candidate_packet_dir),
        "strongest_rival_present": subject.has_strongest_rival,
        "required_artifact_types": list(INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "internal_reader_state_eval_artifacts": len(artifacts),
            "required_internal_reader_state_eval_artifacts": len(
                INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES
            ),
            "model_calls": len(model_results),
            "recorded_gates": len(gate_records),
        },
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "model_call_ids": [result.model_call.id for result in model_results],
        "reader_delta_report": payloads.get("reader_delta_report"),
        "rival_reader_state_comparison": payloads.get("rival_reader_state_comparison"),
        "gate_report": payloads.get("internal_reader_state_eval_gate_report"),
        "message": message,
    }


def _refusal(
    *,
    client_name: str,
    model: str | None,
    synthesis_packet: Path | str,
    message: str,
) -> ReaderStateEvaluationResult:
    return ReaderStateEvaluationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "synthesis_packet": str(synthesis_packet),
            "artifact_ids": {},
            "artifact_paths": {},
            "model_calls": [],
            "message": message,
        },
    )


def _gate_result(
    gate_name: str,
    passed: bool,
    blocking_defects: list[str] | None = None,
    *,
    record: bool = True,
) -> dict[str, object]:
    return {
        "gate_name": gate_name,
        "passed": passed,
        "record": record,
        "blocking_defects": list(blocking_defects or ([] if passed else [f"{gate_name} is missing"])),
    }


def _artifact_by_path(connection, *, run_id: str, artifact_path: Path) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT id
        FROM artifacts
        WHERE run_id = ?
          AND path IN (?, ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (run_id, str(artifact_path), str(artifact_path.resolve())),
    ).fetchone()
    if row is None:
        return None
    return get_artifact(connection, row["id"])


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    return _payload(read_json_file(artifact.path))


def _payload(envelope: dict[str, Any]) -> dict[str, Any]:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("artifact payload is not an object")
    return payload


def _string_dict(value: object) -> dict[str, str]:
    return {str(key): str(item) for key, item in dict(value).items()}


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = config.root / resolved
    return resolved.resolve()


def _optional_path(config: AbiConfig, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return _resolve_path(config, value)


def _model_call_by_source(model_results: list[ModelDriverResult]) -> dict[str, str]:
    return {
        result.model_call.schema_name: result.model_call.id
        for result in model_results
    } | {
        INTERNAL_STREAM_READER_SCHEMA.artifact_type: result.model_call.id
        for result in model_results
        if result.model_call.schema_name == INTERNAL_STREAM_READER_SCHEMA.name
    } | {
        INTERNAL_REREAD_READER_SCHEMA.artifact_type: result.model_call.id
        for result in model_results
        if result.model_call.schema_name == INTERNAL_REREAD_READER_SCHEMA.name
    } | {
        INTERNAL_RIVAL_COMPARISON_SCHEMA.artifact_type: result.model_call.id
        for result in model_results
        if result.model_call.schema_name == INTERNAL_RIVAL_COMPARISON_SCHEMA.name
    } | {
        HOSTILE_INTERNAL_READER_SCHEMA.artifact_type: result.model_call.id
        for result in model_results
        if result.model_call.schema_name == HOSTILE_INTERNAL_READER_SCHEMA.name
    } | {
        FORENSIC_GROUNDING_READER_SCHEMA.artifact_type: result.model_call.id
        for result in model_results
        if result.model_call.schema_name == FORENSIC_GROUNDING_READER_SCHEMA.name
    }


def _retained_images(text: str) -> list[str]:
    lower = text.lower()
    return [
        term
        for term in ("table", "dust", "spoon", "saucer", "ring", "room", "morning")
        if term in lower
    ]


def _live_motifs(text: str) -> list[str]:
    lower = text.lower()
    return [
        term
        for term in (
            "table",
            "dust",
            "spoon",
            "saucer",
            "ring",
            "proof",
            "answer",
            "return",
            "silence",
        )
        if term in lower
    ]


def _overexplicit_terms(text: str) -> list[str]:
    lower = text.lower()
    return [
        term
        for term in ("proof", "answer", "pattern", "formal", "condition", "return")
        if lower.count(term) > 1
    ]


def _confusion_points(text: str) -> list[str]:
    points = []
    if "proof" in text.lower() and "answer" in text.lower():
        points.append("proof/no-outside-answer relation may remain concept-heavy")
    if "return" in text.lower():
        points.append("return must be felt as event, not explanation")
    return points or ["no deterministic confusion point isolated"]


def _proof_logic_state(text: str) -> str:
    lower = text.lower()
    if "outside" in lower and "answer" in lower and "proof" in lower:
        return "partly_structural_but_still_explicit"
    return "not_clearly_carried"


def _constraint_carried(text: str, constraint: str) -> bool:
    lower = text.lower()
    if constraint == "table/dust/spoon/saucer local field":
        return all(term in lower for term in ("table", "dust", "spoon", "saucer"))
    if constraint == "proof arises inside the line":
        return "proof" in lower and "inside" in lower
    if constraint == "no outside answer":
        return "outside" in lower and "answer" in lower
    if constraint == "return without regression":
        return "return" in lower and "regression" in lower
    if constraint == "strongest-rival pressure preserved":
        return True
    return False


def _reader_score(text: str) -> dict[str, int]:
    words = _words(text.lower())
    retained = _retained_images(text)
    return {
        "first_read_vividness": min(10, 3 + len(retained)),
        "local_embodiment": min(10, 3 + len(retained) + ("scar" in words)),
        "structural_return": min(10, 4 + ("return" in words) + ("morning" in words)),
        "overexplanation_risk": min(10, len(_overexplicit_terms(text)) + 3),
    }


def _support_snippet(text: str, claim: str) -> str:
    lower = text.lower()
    for term in ("table", "dust", "spoon", "saucer", "proof", "answer", "return"):
        if term in claim.lower() or term in lower:
            index = lower.find(term)
            if index >= 0:
                start = max(0, index - 45)
                end = min(len(text), index + 120)
                return text[start:end].strip()
    return text[:160].strip()


def _words(text: str) -> list[str]:
    return [word.strip(".,;:!?()[]{}\"'").lower() for word in text.split() if word.strip()]


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
