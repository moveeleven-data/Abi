"""Ablation-informed manual revision cycle v1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from abi.artifacts import ArtifactRecord, get_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord
from abi.controller.state import get_run, set_active_phase
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_calls import link_model_call_parsed_artifact
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    ABLATION_INFORMED_BASE_SELECTION_SCHEMA,
    ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA,
    ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA,
    ModelValidationError,
    WorkerRole,
)
from abi.packets import PacketWriter, create_packet_dir, read_json_file


ABLATION_INFORMED_REVISION_LINEAGE_ID = "ablation_informed_revision_cycle_v1"
ABLATION_INFORMED_REVISION_ACTIVE_PHASE = "ablation_informed_revision_cycle_v1"
ABLATION_INFORMED_REVISION_CLIENT_FAKE = "fake"
ABLATION_INFORMED_REVISION_CLIENT_OPENAI = "openai"
ABLATION_INFORMED_REVISION_CLIENTS = (
    ABLATION_INFORMED_REVISION_CLIENT_FAKE,
    ABLATION_INFORMED_REVISION_CLIENT_OPENAI,
)
ABLATION_INFORMED_REVISION_MAX_MODEL_CALLS_DEFAULT = 8
ABLATION_INFORMED_REVISION_REQUIRED_MODEL_CALLS = 3

ABLATION_INFORMED_REVISION_ARTIFACT_TYPES = (
    "ablation_informed_revision_subject_manifest",
    "ablation_evidence_summary",
    "cycle2_base_candidate_selection",
    "selected_next_failure_or_handle",
    "ablation_informed_revision_work_order",
    "cycle2_patch_proposal",
    "cycle2_applied_patch_ledger",
    "cycle2_revised_candidate_text",
    "cycle2_revision_diff_report",
    "cycle2_preliminary_old_new_rival_comparison",
    "cycle2_gate_report",
    "cycle2_packet",
)

BASE_CHOICE_ORIGINAL = "original_candidate"
BASE_CHOICE_PACKET_0030 = "packet_0030_revised_candidate"
BASE_CHOICE_EMBODIMENT = "embodiment_preserving_ablation_variant"
BASE_CHOICE_RECORD = "record_label_compression_ablation_variant"
BASE_CHOICE_CONTROLLER_COMPOSED = "controller_composed_base_from_evidence_supported_changes"

SOURCE_REVISION_KIND_AUTONOMOUS = "autonomous_revision"
SOURCE_REVISION_KIND_ABLATION_INFORMED = "ablation_informed_revision"

ABLATION_INFORMED_SOURCE_REQUIRED_FILES = (
    "cycle2_packet.json",
    "cycle2_revised_candidate_text.json",
    "cycle2_revision_diff_report.json",
    "cycle2_applied_patch_ledger.json",
    "cycle2_gate_report.json",
)


@dataclass(frozen=True)
class AblationInformedRevisionResult:
    exit_code: int
    payload: dict[str, object]
    gate_records: tuple[GateRecord, ...] = ()
    model_results: tuple[ModelDriverResult, ...] = ()


class AblationInformedRevisionIntegrityError(ValueError):
    """Raised when controller patch ledger, revised text, and diff disagree."""


@dataclass(frozen=True)
class SourceText:
    label: str
    source_class: str
    artifact_id: str
    text: str


@dataclass(frozen=True)
class AblationInformedSubject:
    run_id: str
    packet_dir: Path
    packet_id: str
    packet_artifact_id: str | None
    artifacts: dict[str, ArtifactRecord]
    payloads: dict[str, dict[str, Any]]
    source_revision_packet_kind: str
    revision_packet_dir: Path
    revision_packet_id: str
    revision_artifacts: dict[str, ArtifactRecord]
    revision_payloads: dict[str, dict[str, Any]]
    reader_lab_packet_dir: Path
    reader_lab_packet_id: str
    source_packet_dir: Path
    source_packet_id: str
    source_texts: tuple[SourceText, ...]

    @property
    def original_candidate(self) -> SourceText:
        return self.text_by_source_class("abi_candidate")

    @property
    def packet_0030_revised_text(self) -> str:
        return self.source_revised_candidate_text

    @property
    def source_revised_candidate_text(self) -> str:
        return str(self.revision_payloads["revised_candidate_text"]["text"])

    @property
    def source_selected_failure_or_handle(self) -> str | None:
        selected = self.revision_payloads.get("selected_failure_diagnosis", {})
        return (
            selected.get("selected_failure_type")
            or selected.get("selected_next_handle")
            or selected.get("previous_selected_failure")
        )

    @property
    def strongest_rival(self) -> SourceText | None:
        for text in self.source_texts:
            if text.source_class == "strongest_rival":
                return text
        return None

    def text_by_source_class(self, source_class: str) -> SourceText:
        for text in self.source_texts:
            if text.source_class == source_class:
                return text
        raise KeyError(source_class)

    def variant_by_operation_id(self, operation_id: str) -> dict[str, Any] | None:
        variants = self.payloads["actual_ablation_variant_set"]["variants"]
        for variant in variants:
            if str(variant.get("operation_id")) == operation_id:
                return variant
        return None


def run_ablation_informed_revision(
    config: AbiConfig,
    *,
    client_name: str,
    executed_ablation_packet: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = ABLATION_INFORMED_REVISION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> AblationInformedRevisionResult:
    if client_name not in ABLATION_INFORMED_REVISION_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            executed_ablation_packet=executed_ablation_packet,
            message=(
                "Ablation-informed revision client is not available: "
                f"{client_name}"
            ),
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < 0:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            executed_ablation_packet=executed_ablation_packet,
            message=(
                "Ablation-informed revision refused; max-model-calls must be "
                "non-negative."
            ),
        )
    if client_name == ABLATION_INFORMED_REVISION_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            executed_ablation_packet=executed_ablation_packet,
            message=(
                "Ablation-informed revision refused; pass --allow-live-model to opt "
                "in explicitly."
            ),
        )
    resolved_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == ABLATION_INFORMED_REVISION_CLIENT_OPENAI and not resolved_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            executed_ablation_packet=executed_ablation_packet,
            message=f"Ablation-informed revision refused; {OPENAI_API_KEY_ENV} is not set.",
        )
    if (
        client_name == ABLATION_INFORMED_REVISION_CLIENT_OPENAI
        and max_model_calls < ABLATION_INFORMED_REVISION_REQUIRED_MODEL_CALLS
    ):
        return _refusal(
            client_name=client_name,
            model=configured_model,
            executed_ablation_packet=executed_ablation_packet,
            message=(
                "Ablation-informed revision refused; max-model-calls "
                f"{max_model_calls} is below required budget "
                f"{ABLATION_INFORMED_REVISION_REQUIRED_MODEL_CALLS}."
            ),
        )

    packet_dir = _resolve_path(config, executed_ablation_packet)
    if not packet_dir.exists() or not packet_dir.is_dir():
        return _refusal(
            client_name=client_name,
            model=None,
            executed_ablation_packet=packet_dir,
            message=(
                "Ablation-informed revision refused; executed ablation packet "
                f"directory not found: {packet_dir}"
            ),
        )

    initialize_database(config)
    try:
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, packet_dir)
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    client_name=client_name,
                    model=None,
                    executed_ablation_packet=packet_dir,
                    message=(
                        "Ablation-informed revision refused; run is not registered: "
                        f"{subject.run_id}"
                    ),
                )
            output_dir = create_packet_dir(
                config.run_dir(subject.run_id) / "ablation_informed_revision"
            )
            set_active_phase(
                connection,
                subject.run_id,
                ABLATION_INFORMED_REVISION_ACTIVE_PHASE,
            )
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            client_name=client_name,
            model=None,
            executed_ablation_packet=packet_dir,
            message=(
                "Ablation-informed revision refused; invalid executed ablation "
                f"packet: {error}"
            ),
        )

    if client_name == ABLATION_INFORMED_REVISION_CLIENT_OPENAI:
        factory = client_factory or _default_openai_client_factory
        return _run_packet(
            config=config,
            subject=subject,
            output_dir=output_dir,
            client_name=client_name,
            fixture_only=False,
            model=configured_model,
            model_client=factory(configured_model),
        )

    return _run_packet(
        config=config,
        subject=subject,
        output_dir=output_dir,
        client_name=client_name,
        fixture_only=True,
        model=None,
        model_client=None,
    )


def _run_packet(
    *,
    config: AbiConfig,
    subject: AblationInformedSubject,
    output_dir: Path,
    client_name: str,
    fixture_only: bool,
    model: str | None,
    model_client: ModelClient | None,
) -> AblationInformedRevisionResult:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}
    model_results: list[ModelDriverResult] = []

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
            created_by="ablation_informed_revision_cycle_v1_controller",
            fixture_only=fixture_only,
            model_call_id=None,
        )

        payloads["ablation_informed_revision_subject_manifest"] = _build_subject_manifest(
            subject,
            fixture_only=fixture_only,
        )
        artifacts["ablation_informed_revision_subject_manifest"] = writer.write_artifact(
            "ablation_informed_revision_subject_manifest",
            payloads["ablation_informed_revision_subject_manifest"],
            parent_ids=_subject_parent_ids(subject),
        )

        payloads["ablation_evidence_summary"] = _build_evidence_summary(
            subject,
            fixture_only=fixture_only,
        )
        artifacts["ablation_evidence_summary"] = writer.write_artifact(
            "ablation_evidence_summary",
            payloads["ablation_evidence_summary"],
            parent_ids=[
                subject.artifacts["ablation_causal_effect_report"].id,
                subject.artifacts["ablation_old_new_rival_comparison"].id,
                subject.artifacts["comparison_consistency_report"].id,
                subject.artifacts["actual_ablation_variant_set"].id,
            ],
        )

    if model_client is not None:
        base_parent_ids = [
            artifacts["ablation_evidence_summary"].id,
            subject.revision_artifacts["revised_candidate_text"].id,
            subject.artifacts["actual_ablation_variant_set"].id,
        ]
        result = _run_base_selection_model(
            config=config,
            subject=subject,
            output_dir=output_dir,
            model_client=model_client,
            evidence_summary=payloads["ablation_evidence_summary"],
            parent_ids=base_parent_ids,
        )
        model_results.append(result)
        if not result.accepted or result.parsed_payload is None:
            return _failure_result(
                client_name=client_name,
                model=model,
                subject=subject,
                packet_dir=output_dir,
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
                message=_model_failure_message("base selection", result),
            )
        payloads["cycle2_base_candidate_selection"] = _build_base_selection(
            subject,
            payloads["ablation_evidence_summary"],
            model_payload=result.parsed_payload,
            model_call_id=result.model_call.id,
            fixture_only=fixture_only,
        )
        artifacts["cycle2_base_candidate_selection"], model_results[-1] = (
            _write_model_produced_artifact(
                config=config,
                result=result,
                run_id=subject.run_id,
                packet_dir=output_dir,
                artifact_type="cycle2_base_candidate_selection",
                payload=payloads["cycle2_base_candidate_selection"],
                parent_ids=base_parent_ids,
                fixture_only=fixture_only,
            )
        )

        handle_parent_ids = [
            artifacts["ablation_evidence_summary"].id,
            artifacts["cycle2_base_candidate_selection"].id,
            subject.artifacts["ablation_causal_effect_report"].id,
        ]
        if "selected_failure_diagnosis" in subject.revision_artifacts:
            handle_parent_ids.append(
                subject.revision_artifacts["selected_failure_diagnosis"].id
            )
        result = _run_handle_selection_model(
            config=config,
            subject=subject,
            output_dir=output_dir,
            model_client=model_client,
            evidence_summary=payloads["ablation_evidence_summary"],
            base_selection=payloads["cycle2_base_candidate_selection"],
            parent_ids=handle_parent_ids,
        )
        model_results.append(result)
        if not result.accepted or result.parsed_payload is None:
            return _failure_result(
                client_name=client_name,
                model=model,
                subject=subject,
                packet_dir=output_dir,
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
                message=_model_failure_message("next handle", result),
            )
        payloads["selected_next_failure_or_handle"] = _build_next_handle(
            subject,
            payloads["ablation_evidence_summary"],
            model_payload=result.parsed_payload,
            model_call_id=result.model_call.id,
            fixture_only=fixture_only,
        )
        artifacts["selected_next_failure_or_handle"], model_results[-1] = (
            _write_model_produced_artifact(
                config=config,
                result=result,
                run_id=subject.run_id,
                packet_dir=output_dir,
                artifact_type="selected_next_failure_or_handle",
                payload=payloads["selected_next_failure_or_handle"],
                parent_ids=handle_parent_ids,
                fixture_only=fixture_only,
            )
        )
    else:
        with connect(config.db_path) as connection:
            writer = PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=output_dir,
                lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
                created_by="ablation_informed_revision_cycle_v1_controller",
                fixture_only=fixture_only,
                model_call_id=None,
            )
            payloads["cycle2_base_candidate_selection"] = _build_base_selection(
                subject,
                payloads["ablation_evidence_summary"],
                fixture_only=fixture_only,
            )
            artifacts["cycle2_base_candidate_selection"] = writer.write_artifact(
                "cycle2_base_candidate_selection",
                payloads["cycle2_base_candidate_selection"],
                parent_ids=[
                    artifacts["ablation_evidence_summary"].id,
                    subject.revision_artifacts["revised_candidate_text"].id,
                    subject.artifacts["actual_ablation_variant_set"].id,
                ],
            )

            payloads["selected_next_failure_or_handle"] = _build_next_handle(
                subject,
                payloads["ablation_evidence_summary"],
                fixture_only=fixture_only,
            )
            artifacts["selected_next_failure_or_handle"] = writer.write_artifact(
                "selected_next_failure_or_handle",
                payloads["selected_next_failure_or_handle"],
                parent_ids=[
                    artifacts["ablation_evidence_summary"].id,
                    subject.artifacts["ablation_causal_effect_report"].id,
                    *(
                        [subject.revision_artifacts["selected_failure_diagnosis"].id]
                        if "selected_failure_diagnosis" in subject.revision_artifacts
                        else []
                    ),
                ],
            )

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
            created_by="ablation_informed_revision_cycle_v1_controller",
            fixture_only=fixture_only,
            model_call_id=None,
        )
        payloads["ablation_informed_revision_work_order"] = _build_work_order(
            subject=subject,
            base_selection=payloads["cycle2_base_candidate_selection"],
            next_handle=payloads["selected_next_failure_or_handle"],
        )
        artifacts["ablation_informed_revision_work_order"] = writer.write_artifact(
            "ablation_informed_revision_work_order",
            payloads["ablation_informed_revision_work_order"],
            parent_ids=[
                artifacts["cycle2_base_candidate_selection"].id,
                artifacts["selected_next_failure_or_handle"].id,
                subject.artifacts["executed_ablation_work_order"].id,
            ],
        )

    patch_parent_ids = [artifacts["ablation_informed_revision_work_order"].id]
    if model_client is not None:
        result = _run_patch_proposal_model(
            config=config,
            subject=subject,
            output_dir=output_dir,
            model_client=model_client,
            work_order=payloads["ablation_informed_revision_work_order"],
            next_handle=payloads["selected_next_failure_or_handle"],
            parent_ids=patch_parent_ids,
        )
        model_results.append(result)
        if not result.accepted or result.parsed_payload is None:
            return _failure_result(
                client_name=client_name,
                model=model,
                subject=subject,
                packet_dir=output_dir,
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
                message=_model_failure_message("patch proposal", result),
            )
        payloads["cycle2_patch_proposal"] = _build_patch_proposal(
            payloads["ablation_informed_revision_work_order"],
            model_payload=result.parsed_payload,
            model_call_id=result.model_call.id,
            fixture_only=fixture_only,
        )
        artifacts["cycle2_patch_proposal"], model_results[-1] = (
            _write_model_produced_artifact(
                config=config,
                result=result,
                run_id=subject.run_id,
                packet_dir=output_dir,
                artifact_type="cycle2_patch_proposal",
                payload=payloads["cycle2_patch_proposal"],
                parent_ids=patch_parent_ids,
                fixture_only=fixture_only,
            )
        )
    else:
        with connect(config.db_path) as connection:
            writer = PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=output_dir,
                lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
                created_by="ablation_informed_revision_cycle_v1_controller",
                fixture_only=fixture_only,
                model_call_id=None,
            )
            payloads["cycle2_patch_proposal"] = _build_patch_proposal(
                payloads["ablation_informed_revision_work_order"],
                fixture_only=fixture_only,
            )
            artifacts["cycle2_patch_proposal"] = writer.write_artifact(
                "cycle2_patch_proposal",
                payloads["cycle2_patch_proposal"],
                parent_ids=patch_parent_ids,
            )

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
            created_by="ablation_informed_revision_cycle_v1_controller",
            fixture_only=fixture_only,
            model_call_id=None,
        )
        payloads["cycle2_applied_patch_ledger"] = _build_applied_patch_ledger(
            base_selection=payloads["cycle2_base_candidate_selection"],
            work_order=payloads["ablation_informed_revision_work_order"],
            patch_proposal=payloads["cycle2_patch_proposal"],
            fixture_only=fixture_only,
        )
        try:
            _validate_applied_patch_ledger(payloads["cycle2_applied_patch_ledger"])
        except AblationInformedRevisionIntegrityError as error:
            return _failure_result(
                client_name=client_name,
                model=model,
                subject=subject,
                packet_dir=output_dir,
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
                message=str(error),
            )
        artifacts["cycle2_applied_patch_ledger"] = writer.write_artifact(
            "cycle2_applied_patch_ledger",
            payloads["cycle2_applied_patch_ledger"],
            parent_ids=[
                artifacts["cycle2_base_candidate_selection"].id,
                artifacts["ablation_informed_revision_work_order"].id,
                artifacts["cycle2_patch_proposal"].id,
            ],
        )

        payloads["cycle2_revised_candidate_text"] = _build_revised_candidate(
            base_selection=payloads["cycle2_base_candidate_selection"],
            applied_patch_ledger=payloads["cycle2_applied_patch_ledger"],
            applied_patch_ledger_artifact_id=artifacts["cycle2_applied_patch_ledger"].id,
            fixture_only=fixture_only,
        )

        payloads["cycle2_revision_diff_report"] = _build_diff_report(
            base_selection=payloads["cycle2_base_candidate_selection"],
            work_order=payloads["ablation_informed_revision_work_order"],
            applied_patch_ledger=payloads["cycle2_applied_patch_ledger"],
            revised_candidate=payloads["cycle2_revised_candidate_text"],
            fixture_only=fixture_only,
        )
        try:
            _validate_text_diff_integrity(
                applied_patch_ledger=payloads["cycle2_applied_patch_ledger"],
                revised_candidate=payloads["cycle2_revised_candidate_text"],
                diff_report=payloads["cycle2_revision_diff_report"],
            )
        except AblationInformedRevisionIntegrityError as error:
            return _failure_result(
                client_name=client_name,
                model=model,
                subject=subject,
                packet_dir=output_dir,
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
                message=str(error),
            )

        artifacts["cycle2_revised_candidate_text"] = writer.write_artifact(
            "cycle2_revised_candidate_text",
            payloads["cycle2_revised_candidate_text"],
            parent_ids=[
                artifacts["cycle2_base_candidate_selection"].id,
                artifacts["cycle2_patch_proposal"].id,
                artifacts["cycle2_applied_patch_ledger"].id,
            ],
        )
        artifacts["cycle2_revision_diff_report"] = writer.write_artifact(
            "cycle2_revision_diff_report",
            payloads["cycle2_revision_diff_report"],
            parent_ids=[
                artifacts["ablation_informed_revision_work_order"].id,
                artifacts["cycle2_applied_patch_ledger"].id,
                artifacts["cycle2_revised_candidate_text"].id,
            ],
        )

        payloads["cycle2_preliminary_old_new_rival_comparison"] = (
            _build_preliminary_comparison(
                subject=subject,
                base_selection=payloads["cycle2_base_candidate_selection"],
                revised_candidate=payloads["cycle2_revised_candidate_text"],
                fixture_only=fixture_only,
            )
        )
        artifacts["cycle2_preliminary_old_new_rival_comparison"] = writer.write_artifact(
            "cycle2_preliminary_old_new_rival_comparison",
            payloads["cycle2_preliminary_old_new_rival_comparison"],
            parent_ids=[
                artifacts["cycle2_revised_candidate_text"].id,
                artifacts["cycle2_revision_diff_report"].id,
                subject.artifacts["ablation_old_new_rival_comparison"].id,
            ],
        )

        payloads["cycle2_gate_report"] = _build_gate_report(
            subject=subject,
            evidence_summary=payloads["ablation_evidence_summary"],
            applied_patch_ledger=payloads["cycle2_applied_patch_ledger"],
            revised_candidate=payloads["cycle2_revised_candidate_text"],
            diff_report=payloads["cycle2_revision_diff_report"],
            preliminary_comparison=payloads[
                "cycle2_preliminary_old_new_rival_comparison"
            ],
            fixture_only=fixture_only,
        )
        artifacts["cycle2_gate_report"] = writer.write_artifact(
            "cycle2_gate_report",
            payloads["cycle2_gate_report"],
            parent_ids=[
                artifacts["cycle2_revised_candidate_text"].id,
                artifacts["cycle2_preliminary_old_new_rival_comparison"].id,
            ],
        )

        payloads["cycle2_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=output_dir,
            artifacts=artifacts,
            payloads=payloads,
            model=model,
            model_results=model_results,
            fixture_only=fixture_only,
        )
        artifacts["cycle2_packet"] = writer.write_artifact(
            "cycle2_packet",
            payloads["cycle2_packet"],
            parent_ids=[
                artifacts[artifact_type].id
                for artifact_type in ABLATION_INFORMED_REVISION_ARTIFACT_TYPES[:-1]
            ],
        )

    return AblationInformedRevisionResult(
        exit_code=0,
        payload=_summary_payload(
            subject=subject,
            packet_dir=output_dir,
            client_name=client_name,
            artifacts=artifacts,
            payloads=payloads,
            accepted=True,
            message=None,
            model=model,
            model_results=model_results,
        ),
        model_results=tuple(model_results),
    )


def _run_base_selection_model(
    *,
    config: AbiConfig,
    subject: AblationInformedSubject,
    output_dir: Path,
    model_client: ModelClient,
    evidence_summary: dict[str, Any],
    parent_ids: list[str],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    return driver.run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.ABLATION_INFORMED_BASE_SELECTOR,
            prompt_contract_id="autonomous.ablation_informed_revision.base_selection.v1",
            schema=ABLATION_INFORMED_BASE_SELECTION_SCHEMA,
            input_text=_prompt_for_base_selection(subject, evidence_summary),
            input_artifact_ids=list(parent_ids),
            input_packet_path=str(subject.packet_dir),
            lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
            parent_ids=list(parent_ids),
            fixture_only=False,
            output_dir=str(output_dir),
            register_parsed_artifact=False,
            parsed_payload_validator=lambda payload: _validate_model_base_selection(
                subject,
                payload,
            ),
        )
    )


def _run_handle_selection_model(
    *,
    config: AbiConfig,
    subject: AblationInformedSubject,
    output_dir: Path,
    model_client: ModelClient,
    evidence_summary: dict[str, Any],
    base_selection: dict[str, Any],
    parent_ids: list[str],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    return driver.run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.ABLATION_INFORMED_HANDLE_SELECTOR,
            prompt_contract_id="autonomous.ablation_informed_revision.handle_selection.v1",
            schema=ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA,
            input_text=_prompt_for_handle_selection(
                subject,
                evidence_summary,
                base_selection,
            ),
            input_artifact_ids=list(parent_ids),
            input_packet_path=str(subject.packet_dir),
            lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
            parent_ids=list(parent_ids),
            fixture_only=False,
            output_dir=str(output_dir),
            register_parsed_artifact=False,
            parsed_payload_validator=lambda payload: _validate_model_handle_selection(
                evidence_summary,
                payload,
            ),
        )
    )


def _run_patch_proposal_model(
    *,
    config: AbiConfig,
    subject: AblationInformedSubject,
    output_dir: Path,
    model_client: ModelClient,
    work_order: dict[str, Any],
    next_handle: dict[str, Any],
    parent_ids: list[str],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    return driver.run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.ABLATION_INFORMED_PATCH_PROPOSER,
            prompt_contract_id="autonomous.ablation_informed_revision.patch_proposal.v1",
            schema=ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA,
            input_text=_prompt_for_patch_proposal(work_order, next_handle),
            input_artifact_ids=list(parent_ids),
            input_packet_path=str(subject.packet_dir),
            lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
            parent_ids=list(parent_ids),
            fixture_only=False,
            output_dir=str(output_dir),
            register_parsed_artifact=False,
            parsed_payload_validator=lambda payload: _validate_model_patch_proposal(
                work_order,
                payload,
            ),
        )
    )


def _prompt_for_base_selection(
    subject: AblationInformedSubject,
    evidence_summary: dict[str, Any],
) -> str:
    return _canonical_json(
        {
            "task": "Select exactly one controller-owned base candidate option.",
            "model_may_own": [
                "selected_base_candidate_id",
                "evidence rationale",
                "uncertainty",
            ],
            "model_must_not_own": [
                "base candidate text",
                "base candidate IDs",
                "evidence counts",
                "finalization",
                "phase-shift claims",
            ],
            "base_candidate_options": _base_options(subject),
            "evidence_summary": evidence_summary,
        }
    )


def _prompt_for_handle_selection(
    subject: AblationInformedSubject,
    evidence_summary: dict[str, Any],
    base_selection: dict[str, Any],
) -> str:
    return _canonical_json(
        {
            "task": (
                "Select the next bounded causal handle from executed ablation evidence "
                "without treating the prior repair as proven."
            ),
            "source_revision_packet_kind": subject.source_revision_packet_kind,
            "previous_selected_failure": subject.source_selected_failure_or_handle,
            "base_selection": {
                "selected_base_candidate_id": base_selection[
                    "selected_base_candidate_id"
                ],
                "selected_base_text_sha256": base_selection[
                    "selected_base_text_sha256"
                ],
            },
            "evidence_summary": evidence_summary,
            "required_pressure": {
                "previous_repair_treated_as_proven": False,
                "strongest_rival_pressure_remains_blocking": evidence_summary[
                    "strongest_rival_pressure_remains_blocking"
                ],
            },
        }
    )


def _prompt_for_patch_proposal(
    work_order: dict[str, Any],
    next_handle: dict[str, Any],
) -> str:
    return _canonical_json(
        {
            "task": (
                "Propose bounded replacement text only for listed patch_span_ids. "
                "Do not provide before text or a full revised candidate."
            ),
            "selected_next_handle": next_handle["selected_next_handle"],
            "allowed_patch_target_ids": work_order["allowed_patch_target_ids"],
            "patchable_span_ids": work_order["patchable_span_ids"],
            "patchable_spans": work_order["patchable_spans"],
            "protected_effects": work_order["protected_effects"],
            "forbidden_changes": work_order["forbidden_changes"],
        }
    )


def _validate_model_base_selection(
    subject: AblationInformedSubject,
    payload: dict[str, object],
) -> None:
    allowed_ids = {option["base_candidate_id"] for option in _base_options(subject)}
    selected = str(payload.get("selected_base_candidate_id", ""))
    if selected not in allowed_ids:
        raise ModelValidationError(
            "selected_base_candidate_id must be one of controller-owned base options"
        )
    prior_status = str(payload.get("prior_repair_causal_status", "")).strip()
    if not prior_status:
        raise ModelValidationError("prior_repair_causal_status must not be empty")


def _validate_model_handle_selection(
    evidence_summary: dict[str, Any],
    payload: dict[str, object],
) -> None:
    selected = str(payload.get("selected_next_handle", "")).strip()
    if not selected:
        raise ModelValidationError("selected_next_handle must not be empty")
    if (
        evidence_summary["strongest_rival_pressure_remains_blocking"]
        and payload.get("strongest_rival_pressure_remains_blocking") is not True
    ):
        raise ModelValidationError(
            "strongest_rival_pressure_remains_blocking must preserve controller evidence"
        )


def _validate_model_patch_proposal(
    work_order: dict[str, Any],
    payload: dict[str, object],
) -> None:
    allowed_ids = {str(value) for value in work_order["patchable_span_ids"]}
    seen: set[str] = set()
    for patch in payload.get("patches", []):
        if not isinstance(patch, dict):
            raise ModelValidationError("patches must contain objects")
        patch_span_id = str(patch.get("patch_span_id", ""))
        if patch_span_id not in allowed_ids:
            raise ModelValidationError(
                "patch_span_id must be one of controller-owned patchable spans"
            )
        if patch_span_id in seen:
            raise ModelValidationError("duplicate patch_span_id in patch proposal")
        seen.add(patch_span_id)
        replacement = str(patch.get("replacement_text", "")).strip()
        if not replacement:
            raise ModelValidationError("replacement_text must not be empty")
        if len(_words(replacement)) > 80:
            raise ModelValidationError("replacement_text must remain bounded")
    if not seen:
        raise ModelValidationError("patch proposal must include at least one patch")


def _write_model_produced_artifact(
    *,
    config: AbiConfig,
    result: ModelDriverResult,
    run_id: str,
    packet_dir: Path,
    artifact_type: str,
    payload: dict[str, Any],
    parent_ids: list[str],
    fixture_only: bool,
) -> tuple[ArtifactRecord, ModelDriverResult]:
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=run_id,
            packet_dir=packet_dir,
            lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
            created_by=(
                f"model_driver:{result.model_call.provider}:{result.model_call.model}"
            ),
            fixture_only=fixture_only,
            model_call_id=result.model_call.id,
        )
        artifact = writer.write_artifact(artifact_type, payload, parent_ids=parent_ids)
        linked_call = link_model_call_parsed_artifact(
            connection,
            model_call_id=result.model_call.id,
            parsed_output_artifact_id=artifact.id,
        )
    return artifact, ModelDriverResult(
        model_call=linked_call,
        parsed_payload=result.parsed_payload,
        parsed_artifact=artifact,
    )


def _failure_result(
    *,
    client_name: str,
    model: str | None,
    subject: AblationInformedSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    model_results: list[ModelDriverResult],
    message: str,
) -> AblationInformedRevisionResult:
    return AblationInformedRevisionResult(
        exit_code=1,
        payload=_summary_payload(
            subject=subject,
            packet_dir=packet_dir,
            client_name=client_name,
            artifacts=artifacts,
            payloads=payloads,
            accepted=False,
            message=message,
            model=model,
            model_results=model_results,
        ),
        model_results=tuple(model_results),
    )


def _model_failure_message(step: str, result: ModelDriverResult) -> str:
    detail = result.model_call.error_message or result.model_call.status
    return f"Ablation-informed revision refused during {step}: {detail}"


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _build_subject_manifest(
    subject: AblationInformedSubject,
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    return {
        "worker": "ablation_informed_revision_subject_manifest_v1",
        "run_id": subject.run_id,
        "executed_ablation_packet_id": subject.packet_id,
        "executed_ablation_packet_dir": str(subject.packet_dir),
        "executed_ablation_packet_artifact_id": subject.packet_artifact_id,
        "executed_ablation_artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in subject.artifacts.items()
        },
        "source_revision_packet_kind": subject.source_revision_packet_kind,
        "source_revision_packet_id": subject.revision_packet_id,
        "source_revision_packet_dir": str(subject.revision_packet_dir),
        "source_revision_artifact_ids": {
            artifact_type: artifact.id
            for artifact_type, artifact in subject.revision_artifacts.items()
        },
        "revision_artifact_ids": {
            artifact_type: artifact.id
            for artifact_type, artifact in subject.revision_artifacts.items()
        },
        "source_autonomous_revision_packet_id": subject.revision_packet_id,
        "source_autonomous_revision_packet_dir": str(subject.revision_packet_dir),
        "source_reader_lab_packet_id": subject.reader_lab_packet_id,
        "source_reader_lab_packet_dir": str(subject.reader_lab_packet_dir),
        "source_packet_id": subject.source_packet_id,
        "source_packet_dir": str(subject.source_packet_dir),
        "original_candidate": _text_ref(subject.original_candidate),
        "source_revised_candidate": {
            "artifact_id": subject.revision_artifacts["revised_candidate_text"].id,
            "text_sha256": sha256_text(subject.source_revised_candidate_text),
            "word_count": len(_words(subject.source_revised_candidate_text)),
        },
        "packet_0030_revised_candidate": {
            "artifact_id": subject.revision_artifacts["revised_candidate_text"].id,
            "text_sha256": sha256_text(subject.source_revised_candidate_text),
            "word_count": len(_words(subject.source_revised_candidate_text)),
        },
        "source_revision_diff": {
            "artifact_id": subject.revision_artifacts["revision_diff_report"].id,
            "source_patch_ids": list(
                subject.revision_payloads["revision_diff_report"].get(
                    "source_patch_ids",
                    [],
                )
            ),
            "source_patch_span_ids": list(
                subject.revision_payloads["revision_diff_report"].get(
                    "source_patch_span_ids",
                    [],
                )
            ),
            "changed_span_count": len(
                subject.revision_payloads["revision_diff_report"].get(
                    "changed_spans",
                    [],
                )
            ),
        },
        "source_patch_ledger": _source_patch_ledger_reference(subject),
        "strongest_rival": _text_ref(subject.strongest_rival),
        "previous_repair_causal_status": subject.payloads[
            "ablation_causal_effect_report"
        ]["selected_repair_causal_status"],
        "controller_owned": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_evidence_summary(
    subject: AblationInformedSubject,
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    causal = subject.payloads["ablation_causal_effect_report"]
    old_new = subject.payloads["ablation_old_new_rival_comparison"]
    execution = subject.payloads["ablation_execution_report"]
    consistency = subject.payloads["comparison_consistency_report"]
    variant_set = subject.payloads["actual_ablation_variant_set"]
    countable = [
        {
            "variant_id": variant["variant_id"],
            "operation_id": variant["operation_id"],
            "operation_type": variant["operation_type"],
            "evidence_countable": variant["evidence_countable"],
            "text_sha256": variant["text_sha256"],
        }
        for variant in variant_set["variants"]
        if variant["evidence_countable"]
    ]
    return {
        "worker": "ablation_evidence_summary_v1_controller",
        "source_executed_ablation_packet_id": subject.packet_id,
        "source_revision_packet_kind": subject.source_revision_packet_kind,
        "source_revision_packet_id": subject.revision_packet_id,
        "previous_repair_causal_status": causal["selected_repair_causal_status"],
        "previous_repair_treated_as_proven": False,
        "packet_0030_treated_as_proven_improvement": False,
        "repair_has_causal_support": old_new["repair_has_causal_support"],
        "revert_performs_same_or_better": old_new["revert_performs_same_or_better"],
        "record_compression_improves_discovery": old_new[
            "record_compression_improves_discovery"
        ],
        "embodiment_preserving_variant_beats_current": old_new[
            "embodiment_preserving_variant_beats_current"
        ],
        "strongest_rival_pressure_remains_blocking": causal[
            "strongest_rival_pressure_remains_blocking"
        ],
        "recommended_next_action": causal["recommended_next_action"],
        "selected_repair_appears_causal": causal["selected_repair_appears_causal"],
        "countable_evidence_variant_count": execution[
            "countable_evidence_variant_count"
        ],
        "countable_variants": countable,
        "comparison_internal_consistency": consistency[
            "comparison_internal_consistency"
        ],
        "evidence_interpretation": _evidence_interpretation(causal, old_new),
        "requires_cycle2_executed_ablation_before_improvement_claim": True,
        "not_human_data": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_base_selection(
    subject: AblationInformedSubject,
    evidence_summary: dict[str, Any],
    *,
    model_payload: dict[str, Any] | None = None,
    model_call_id: str | None = None,
    fixture_only: bool,
) -> dict[str, Any]:
    choices = _base_options(subject)
    selected_choice = (
        str(model_payload["selected_base_candidate_id"])
        if model_payload is not None
        else BASE_CHOICE_CONTROLLER_COMPOSED
    )
    selected_text = _base_text_for_choice(subject, selected_choice)
    model_selection = model_payload or {}
    return {
        "worker": (
            "cycle2_base_candidate_selection_v1_model_driver"
            if model_payload is not None
            else "cycle2_base_candidate_selection_v1_controller"
        ),
        "controller_owned": True,
        "source_revision_packet_kind": subject.source_revision_packet_kind,
        "source_revision_packet_id": subject.revision_packet_id,
        "allowed_choices": [
            BASE_CHOICE_ORIGINAL,
            BASE_CHOICE_PACKET_0030,
            BASE_CHOICE_EMBODIMENT,
            BASE_CHOICE_RECORD,
            BASE_CHOICE_CONTROLLER_COMPOSED,
        ],
        "base_candidate_options": choices,
        "selected_base_candidate_id": selected_choice,
        "selected_base_choice": selected_choice,
        "selected_base_text": selected_text,
        "selected_base_text_sha256": sha256_text(selected_text),
        "selected_base_word_count": len(_words(selected_text)),
        "selection_rationale": (
            str(model_selection["evidence_rationale"])
            if model_payload is not None
            else (
                "Use a controller-composed base from source-revision and executed "
                "ablation evidence while preserving concrete embodiment. The source "
                "revision is evidence to inspect, not proof to stack onto."
            )
        ),
        "why_packet_0030_not_treated_as_proven": (
            str(model_selection["why_packet_0030_not_proven"])
            if model_payload is not None
            else (
                "Executed ablation evidence is diagnostic. The source revision is "
                "evidence to inspect rather than proof to stack onto."
            )
        ),
        "why_source_revision_not_treated_as_proven": (
            str(model_selection["why_packet_0030_not_proven"])
            if model_payload is not None
            else (
                "Executed ablation evidence is diagnostic. The source revision is "
                "not final proof of improvement."
            )
        ),
        "previous_repair_causal_status": evidence_summary["previous_repair_causal_status"],
        "previous_repair_treated_as_proven": False,
        "model_reported_prior_repair_causal_status": (
            model_selection.get("prior_repair_causal_status")
            if model_payload is not None
            else None
        ),
        "model_embodiment_preserving_insight": (
            model_selection.get("embodiment_preserving_insight")
            if model_payload is not None
            else None
        ),
        "model_record_law_proof_answer_insight": (
            model_selection.get("record_law_proof_answer_insight")
            if model_payload is not None
            else None
        ),
        "model_uncertainty": (
            model_selection.get("uncertainty") if model_payload is not None else None
        ),
        "model_call_id": model_call_id,
        "packet_0030_changes_superseded": [
            "flattened legs/plain wording",
            "flattened spoon placement",
            "weakened refrigerator/weather detail",
        ],
        "packet_0030_changes_preserved_if_supported": [
            "removed 'as if nothing happened' from the opening embodiment field"
        ],
        "source_revision_changes_preserved_if_supported": list(
            _source_revision_preservation_notes(subject)
        ),
        "embodiment_preserving_insight_represented": True,
        "record_law_proof_compression_deferred_to_patch": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_next_handle(
    subject: AblationInformedSubject,
    evidence_summary: dict[str, Any],
    *,
    model_payload: dict[str, Any] | None = None,
    model_call_id: str | None = None,
    fixture_only: bool,
) -> dict[str, Any]:
    model_selection = model_payload or {}
    return {
        "worker": (
            "selected_next_failure_or_handle_v1_model_driver"
            if model_payload is not None
            else "selected_next_failure_or_handle_v1_controller"
        ),
        "source_revision_packet_kind": subject.source_revision_packet_kind,
        "source_revision_packet_id": subject.revision_packet_id,
        "previous_selected_failure": subject.source_selected_failure_or_handle,
        "previous_repair_causal_status": evidence_summary[
            "previous_repair_causal_status"
        ],
        "selected_repair_appears_causal": evidence_summary[
            "selected_repair_appears_causal"
        ],
        "recommended_next_action": evidence_summary["recommended_next_action"],
        "why_previous_repair_was_weak_or_cosmetic": (
            str(model_selection["why_previous_repair_weak_or_cosmetic"])
            if model_payload is not None
            else (
                "Executed ablation evidence is diagnostic and still leaves blockers, "
                "so the source revision cannot be reused as proof of improvement."
            )
        ),
        "executed_ablation_evidence": {
            "revert_performs_same_or_better": evidence_summary[
                "revert_performs_same_or_better"
            ],
            "record_compression_improves_discovery": evidence_summary[
                "record_compression_improves_discovery"
            ],
            "embodiment_preserving_variant_beats_current": evidence_summary[
                "embodiment_preserving_variant_beats_current"
            ],
            "strongest_rival_pressure_remains_blocking": evidence_summary[
                "strongest_rival_pressure_remains_blocking"
            ],
        },
        "selected_next_handle": (
            str(model_selection["selected_next_handle"])
            if model_payload is not None
            else "record_law_proof_answer_compression"
        ),
        "why_better_supported_than_repeating_opening_patch": (
            str(model_selection["why_handle_better_than_opening_patch"])
            if model_payload is not None
            else (
                "The selected handle follows countable executed evidence and the "
                "recommended next action rather than merely repeating the opening "
                "patch; strongest-rival pressure remains preserved."
            )
        ),
        "revision_goal": [
            "preserve or restore concrete opening embodiment",
            "compress early record/law/proof/answer labels",
            "let objects carry significance longer before naming it",
            "preserve philosophical pressure without turning descriptive only",
        ],
        "strongest_rival_pressure_preserved": True,
        "model_evidence_summary": (
            model_selection.get("evidence_summary") if model_payload is not None else None
        ),
        "model_local_law_explanation": (
            model_selection.get("local_law_explanation")
            if model_payload is not None
            else None
        ),
        "model_uncertainty": (
            model_selection.get("uncertainty") if model_payload is not None else None
        ),
        "model_call_id": model_call_id,
        "controller_owned_evidence_selection": True,
        "model_owned_fields_allowed_if_live": [
            "replacement_text",
            "rationale",
            "local_law_explanation",
            "uncertainty",
        ],
        "model_must_not_own": [
            "finalization fields",
            "gate pass/fail",
            "before text",
            "authoritative full revised text",
            "target IDs",
            "span IDs",
            "evidence counts",
        ],
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_work_order(
    *,
    subject: AblationInformedSubject,
    base_selection: dict[str, Any],
    next_handle: dict[str, Any],
) -> dict[str, Any]:
    base_text = str(base_selection["selected_base_text"])
    patchable_spans = _patchable_spans(base_text)
    allowed_target = {
        "patch_target_id": "cycle2_target_record_law_proof_answer_compression",
        "target_label": "record/law/proof/answer compression",
        "member_patch_span_ids": [
            str(span["patch_span_id"]) for span in patchable_spans
        ],
        "evidence_source": "executed ablation record-label compression variant",
    }
    return {
        "worker": "ablation_informed_revision_work_order_v1_controller",
        "controller_owned": True,
        "source_executed_ablation_packet_dir": str(subject.packet_dir),
        "source_executed_ablation_packet_id": subject.packet_id,
        "source_revision_packet_kind": subject.source_revision_packet_kind,
        "source_revision_packet_dir": str(subject.revision_packet_dir),
        "source_revision_packet_id": subject.revision_packet_id,
        "source_autonomous_revision_packet_dir": str(subject.revision_packet_dir),
        "source_autonomous_revision_packet_id": subject.revision_packet_id,
        "source_reader_lab_packet_dir": str(subject.reader_lab_packet_dir),
        "source_reader_lab_packet_id": subject.reader_lab_packet_id,
        "selected_base_candidate": base_selection["selected_base_choice"],
        "base_candidate_text_sha256": base_selection["selected_base_text_sha256"],
        "candidate_span_inventory": _candidate_span_inventory(base_text),
        "allowed_patch_targets": [allowed_target],
        "allowed_patch_target_ids": [allowed_target["patch_target_id"]],
        "patchable_spans": patchable_spans,
        "patchable_span_ids": [
            str(span["patch_span_id"]) for span in patchable_spans
        ],
        "protected_effects": [
            "domestic stillness",
            "morning quiet",
            "concrete table/kitchen embodiment",
            "philosophical pressure carried by objects",
        ],
        "forbidden_changes": [
            "rewrite the full artifact",
            "remove the table/kitchen setup",
            "add external plot",
            "turn the piece into abstract argument only",
            "claim final or phase-shift success",
        ],
        "strongest_rival_reference": _text_ref(subject.strongest_rival),
        "ablation_evidence_references": {
            "executed_ablation_packet_artifact_id": subject.packet_artifact_id,
            "ablation_causal_effect_report": subject.artifacts[
                "ablation_causal_effect_report"
            ].id,
            "actual_ablation_variant_set": subject.artifacts[
                "actual_ablation_variant_set"
            ].id,
            "ablation_old_new_rival_comparison": subject.artifacts[
                "ablation_old_new_rival_comparison"
            ].id,
        },
        "selected_next_handle": next_handle["selected_next_handle"],
        "previous_repair_treated_as_proven": False,
        "bounded_revision_only": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": base_selection["fixture_only"],
    }


def _build_patch_proposal(
    work_order: dict[str, Any],
    *,
    model_payload: dict[str, Any] | None = None,
    model_call_id: str | None = None,
    fixture_only: bool,
) -> dict[str, Any]:
    patches = []
    replacements = _cycle2_replacements()
    spans_by_id = {str(span["patch_span_id"]): span for span in work_order["patchable_spans"]}
    if model_payload is not None:
        proposed_by_span = {
            str(patch["patch_span_id"]): patch for patch in model_payload["patches"]
        }
        span_items = [
            (
                index,
                span,
                str(proposed_by_span[str(span["patch_span_id"])]["replacement_text"]),
            )
            for index, span in enumerate(work_order["patchable_spans"], start=1)
            if str(span["patch_span_id"]) in proposed_by_span
        ]
    else:
        span_items = []
        for index, span in enumerate(work_order["patchable_spans"], start=1):
            before = str(span["exact_text"])
            after = replacements.get(before)
            if after is not None:
                span_items.append((index, span, after))
    for index, span, after in span_items:
        patch_span_id = str(span["patch_span_id"])
        model_patch = (
            {str(patch["patch_span_id"]): patch for patch in model_payload["patches"]}[
                patch_span_id
            ]
            if model_payload is not None
            else None
        )
        patches.append(
            {
                "patch_id": f"cycle2_patch_{index:03d}",
                "patch_target_id": "cycle2_target_record_law_proof_answer_compression",
                "patch_span_id": patch_span_id,
                "replacement_text": str(after),
                "rationale": (
                    str(model_patch["rationale"])
                    if model_patch is not None
                    else (
                        "Compress early interpretive labels so objects carry significance "
                        "longer before the text names the pattern."
                    )
                ),
                "local_law_explanation": (
                    model_patch.get("local_law_explanation") if model_patch else None
                ),
                "uncertainty": model_patch.get("uncertainty") if model_patch else None,
                "evidence_source": "ablation_old_new_rival_comparison.record_compression_improves_discovery",
                "preserves_or_supersedes_packet_0030_prior_patch": "supersedes",
                "bounded_patch": True,
                "before_text_owned_by_controller": str(spans_by_id[patch_span_id]["exact_text"]),
            }
        )
    return {
        "worker": (
            "cycle2_patch_proposal_v1_model_driver"
            if model_payload is not None
            else "cycle2_patch_proposal_v1_deterministic"
        ),
        "controller_validated": True,
        "full_rewrite": False,
        "bounded_patch_set": True,
        "selected_next_handle": work_order["selected_next_handle"],
        "patches": patches,
        "model_call_id": model_call_id,
        "model_owned_fields": (
            [
                "replacement_text",
                "rationale",
                "local_law_explanation",
                "uncertainty",
            ]
            if model_payload is not None
            else []
        ),
        "controller_owned_fields": [
            "patch_id",
            "patch_target_id",
            "patch_span_id",
            "before_text via work_order",
            "evidence_source",
        ],
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_applied_patch_ledger(
    *,
    base_selection: dict[str, Any],
    work_order: dict[str, Any],
    patch_proposal: dict[str, Any],
    fixture_only: bool,
) -> dict[str, Any]:
    text = str(base_selection["selected_base_text"])
    spans_by_id = {
        str(span["patch_span_id"]): span for span in work_order["patchable_spans"]
    }
    ledger_entries = []
    for patch in patch_proposal["patches"]:
        patch_id = str(patch["patch_id"])
        patch_span_id = str(patch["patch_span_id"])
        span = spans_by_id.get(patch_span_id)
        before_text = str(span["exact_text"]) if span is not None else ""
        after_text = str(patch["replacement_text"])
        status = "rejected"
        rejection_reason = "patch_span_id_not_in_controller_inventory"
        changed = False
        controller_applied = False

        if span is not None:
            if before_text not in text:
                rejection_reason = "before_text_not_found_in_current_controller_text"
            elif before_text == after_text:
                rejection_reason = "replacement_text_matches_before_text"
            else:
                text = text.replace(before_text, after_text, 1)
                status = "applied"
                rejection_reason = None
                changed = True
                controller_applied = True

        ledger_entries.append(
            {
                "patch_id": patch_id,
                "patch_span_id": patch_span_id,
                "target_span_id": patch_span_id,
                "patch_target_id": patch["patch_target_id"],
                "before_text": before_text,
                "after_text": after_text,
                "operation_type": "replace",
                "application_status": status,
                "rejection_reason": rejection_reason,
                "changed": changed,
                "source_evidence": patch["evidence_source"],
                "evidence_supporting_change": [
                    patch["evidence_source"],
                    "cycle2_patch_proposal",
                ],
                "controller_applied": controller_applied,
                "bounded_patch": bool(patch.get("bounded_patch")),
                "rationale": patch["rationale"],
                "local_law_explanation": patch.get("local_law_explanation"),
                "uncertainty": patch.get("uncertainty"),
                "reflected_after_application": (
                    after_text in text if status == "applied" else False
                ),
            }
        )

    applied = [
        entry for entry in ledger_entries if entry["application_status"] == "applied"
    ]
    rejected = [
        entry for entry in ledger_entries if entry["application_status"] == "rejected"
    ]
    return {
        "worker": "cycle2_applied_patch_ledger_v1_controller",
        "controller_owned": True,
        "base_candidate_choice": base_selection["selected_base_choice"],
        "base_text_sha256": base_selection["selected_base_text_sha256"],
        "revised_text": text,
        "revised_text_sha256": sha256_text(text),
        "ledger_entries": ledger_entries,
        "proposed_patch_count": len(ledger_entries),
        "applied_patch_count": len(applied),
        "rejected_patch_count": len(rejected),
        "applied_patch_ids": [str(entry["patch_id"]) for entry in applied],
        "rejected_patch_ids": [str(entry["patch_id"]) for entry in rejected],
        "applied_patch_span_ids": [str(entry["patch_span_id"]) for entry in applied],
        "rejected_patch_span_ids": [str(entry["patch_span_id"]) for entry in rejected],
        "all_proposed_patches_accounted_for": (
            len(applied) + len(rejected) == len(ledger_entries)
        ),
        "all_applied_patches_reflected_in_text": all(
            bool(entry["reflected_after_application"]) for entry in applied
        ),
        "silent_drop_detected": False,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _validate_applied_patch_ledger(ledger: dict[str, Any]) -> None:
    entries = list(ledger.get("ledger_entries", []))
    statuses = [str(entry.get("application_status", "")) for entry in entries]
    invalid = [status for status in statuses if status not in {"applied", "rejected"}]
    if invalid:
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; patch ledger contains a patch "
            "that is neither applied nor rejected."
        )
    if len(statuses) != int(ledger["proposed_patch_count"]):
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; proposed patch count does not "
            "match patch ledger entries."
        )
    if statuses.count("applied") != int(ledger["applied_patch_count"]):
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; applied patch count is inconsistent."
        )
    if statuses.count("rejected") != int(ledger["rejected_patch_count"]):
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; rejected patch count is inconsistent."
        )
    if not ledger["all_proposed_patches_accounted_for"]:
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; patch ledger silently dropped a patch."
        )
    if not ledger["all_applied_patches_reflected_in_text"]:
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; applied patch is not reflected "
            "in revised text."
        )


def _build_revised_candidate(
    *,
    base_selection: dict[str, Any],
    applied_patch_ledger: dict[str, Any],
    applied_patch_ledger_artifact_id: str,
    fixture_only: bool,
) -> dict[str, Any]:
    text = str(applied_patch_ledger["revised_text"])
    applied_patch_ids = list(applied_patch_ledger["applied_patch_ids"])
    rejected_patch_ids = list(applied_patch_ledger["rejected_patch_ids"])
    applied_patch_span_ids = list(applied_patch_ledger["applied_patch_span_ids"])
    return {
        "worker": "cycle2_revised_candidate_text_v1_controller",
        "text": text,
        "text_sha256": sha256_text(text),
        "word_count": len(_words(text)),
        "assembled_by_controller": True,
        "base_candidate_choice": base_selection["selected_base_choice"],
        "base_candidate_text_sha256": base_selection["selected_base_text_sha256"],
        "source_patch_ids": applied_patch_ids,
        "source_patch_span_ids": applied_patch_span_ids,
        "applied_patch_ids": applied_patch_ids,
        "rejected_patch_ids": rejected_patch_ids,
        "applied_patch_count": int(applied_patch_ledger["applied_patch_count"]),
        "rejected_patch_count": int(applied_patch_ledger["rejected_patch_count"]),
        "proposed_patch_count": int(applied_patch_ledger["proposed_patch_count"]),
        "applied_patch_ledger": {
            "artifact_id": applied_patch_ledger_artifact_id,
            "applied_patch_count": int(applied_patch_ledger["applied_patch_count"]),
            "rejected_patch_count": int(applied_patch_ledger["rejected_patch_count"]),
            "all_applied_patches_reflected_in_text": bool(
                applied_patch_ledger["all_applied_patches_reflected_in_text"]
            ),
        },
        "bounded_recomposition": True,
        "full_rewrite": False,
        "previous_repair_treated_as_proven": False,
        "supersedes_packet_0030_patch": True,
        "cycle2_requires_executed_ablation_before_improvement_claim": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_diff_report(
    *,
    base_selection: dict[str, Any],
    work_order: dict[str, Any],
    applied_patch_ledger: dict[str, Any],
    revised_candidate: dict[str, Any],
    fixture_only: bool,
) -> dict[str, Any]:
    changed_spans = []
    for entry in applied_patch_ledger["ledger_entries"]:
        if entry["application_status"] != "applied":
            continue
        changed_spans.append(
            {
                "changed_span_id": f"cycle2_change_{len(changed_spans) + 1:03d}",
                "patch_id": entry["patch_id"],
                "patch_span_id": entry["patch_span_id"],
                "source_patch_span_ids": [entry["patch_span_id"]],
                "before_text": entry["before_text"],
                "after_text": entry["after_text"],
                "operation_type": entry["operation_type"],
                "change_rationale": entry["rationale"],
                "evidence_source": entry["source_evidence"],
                "preserves_or_supersedes_packet_0030_prior_patch": "supersedes",
                "inside_target": True,
                "within_selected_target": True,
            }
        )
    text_matches_diff = _diff_reconstructs_revised_text(
        base_text=str(base_selection["selected_base_text"]),
        changed_spans=changed_spans,
        revised_text=str(revised_candidate["text"]),
    )
    all_diff_spans_reflected = all(
        str(span["after_text"]) in str(revised_candidate["text"])
        for span in changed_spans
    )
    all_applied_reflected = bool(
        applied_patch_ledger["all_applied_patches_reflected_in_text"]
    )
    applied_patch_count = int(applied_patch_ledger["applied_patch_count"])
    rejected_patch_count = int(applied_patch_ledger["rejected_patch_count"])
    return {
        "worker": "cycle2_revision_diff_report_v1_controller",
        "controller_owned": True,
        "base_candidate_choice": base_selection["selected_base_choice"],
        "base_text_sha256": base_selection["selected_base_text_sha256"],
        "revised_text_sha256": revised_candidate["text_sha256"],
        "source_patch_ids": list(revised_candidate["source_patch_ids"]),
        "source_patch_span_ids": list(revised_candidate["source_patch_span_ids"]),
        "changed_spans": changed_spans,
        "material_change_count": len(changed_spans),
        "proposed_patch_count": int(applied_patch_ledger["proposed_patch_count"]),
        "applied_patch_count": applied_patch_count,
        "rejected_patch_count": rejected_patch_count,
        "diff_changed_span_count": len(changed_spans),
        "text_matches_diff": text_matches_diff,
        "all_applied_patches_reflected_in_text": all_applied_reflected,
        "all_diff_spans_reflected_in_text": all_diff_spans_reflected,
        "rejected_patch_ids": list(applied_patch_ledger["rejected_patch_ids"]),
        "bounded_change": True,
        "full_rewrite": False,
        "all_material_changes_reported": True,
        "previous_repair_treated_as_proven": False,
        "not_human_data": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _diff_reconstructs_revised_text(
    *,
    base_text: str,
    changed_spans: list[dict[str, Any]],
    revised_text: str,
) -> bool:
    reconstructed = base_text
    for span in changed_spans:
        before_text = str(span["before_text"])
        after_text = str(span["after_text"])
        if before_text not in reconstructed:
            return False
        reconstructed = reconstructed.replace(before_text, after_text, 1)
    return sha256_text(reconstructed) == sha256_text(revised_text)


def _validate_text_diff_integrity(
    *,
    applied_patch_ledger: dict[str, Any],
    revised_candidate: dict[str, Any],
    diff_report: dict[str, Any],
) -> None:
    applied_patch_ids = list(applied_patch_ledger["applied_patch_ids"])
    revised_source_patch_ids = list(revised_candidate["source_patch_ids"])
    diff_patch_ids = [str(span["patch_id"]) for span in diff_report["changed_spans"]]
    if revised_source_patch_ids != applied_patch_ids:
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; revised_candidate_text "
            "source_patch_ids omits or reorders an applied patch."
        )
    if diff_patch_ids != applied_patch_ids:
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; diff reports a patch that was "
            "not applied or omits an applied patch."
        )
    if int(diff_report["diff_changed_span_count"]) != int(
        applied_patch_ledger["applied_patch_count"]
    ):
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; diff_changed_span_count does not "
            "match applied_patch_count."
        )
    if not diff_report["text_matches_diff"]:
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; revised text does not match diff."
        )
    if not diff_report["all_applied_patches_reflected_in_text"]:
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; not all applied patches are "
            "reflected in revised text."
        )
    if not diff_report["all_diff_spans_reflected_in_text"]:
        raise AblationInformedRevisionIntegrityError(
            "Ablation-informed revision refused; diff span after_text is not "
            "reflected in revised text."
        )


def _build_preliminary_comparison(
    *,
    subject: AblationInformedSubject,
    base_selection: dict[str, Any],
    revised_candidate: dict[str, Any],
    fixture_only: bool,
) -> dict[str, Any]:
    original_score = _score_text(subject.original_candidate.text)
    source_revision_score = _score_text(subject.source_revised_candidate_text)
    cycle2_score = _score_text(str(revised_candidate["text"]))
    rival_score = (
        _score_text(subject.strongest_rival.text)
        if subject.strongest_rival is not None
        else None
    )
    old_new = subject.payloads["ablation_old_new_rival_comparison"]
    cycle2_text = str(revised_candidate["text"])
    return {
        "worker": "cycle2_preliminary_old_new_rival_comparison_v1",
        "comparison_basis": "deterministic ablation-informed preliminary comparison; not proof",
        "preliminary_not_proof": True,
        "does_not_count_as_executed_ablation_evidence": True,
        "comparison_uses_actual_revised_text": True,
        "actual_revised_text_sha256": revised_candidate["text_sha256"],
        "actual_revised_word_count": revised_candidate["word_count"],
        "source_revision_packet_kind": subject.source_revision_packet_kind,
        "source_revision_packet_id": subject.revision_packet_id,
        "compared_items": [
            "original Text A",
            "source revision Text A",
            "cycle2 revised candidate",
            "strongest rival Text D",
            "record-label compression ablation variant",
            "embodiment-preserving ablation variant",
        ],
        "scores": {
            "original": original_score,
            "source_revision": source_revision_score,
            "packet_0030": source_revision_score,
            "cycle2": cycle2_score,
            "strongest_rival": rival_score,
        },
        "cycle2_reduced_overexplanation": (
            cycle2_score["overexplanation_score"]
            < source_revision_score["overexplanation_score"]
        ),
        "cycle2_preserved_embodiment_better_than_source_revision": (
            cycle2_score["local_embodiment_score"]
            >= source_revision_score["local_embodiment_score"]
            and "The legs are steady." in cycle2_text
            and "A spoon lies on its side" in cycle2_text
        ),
        "cycle2_preserved_embodiment_better_than_packet_0030": (
            cycle2_score["local_embodiment_score"]
            >= source_revision_score["local_embodiment_score"]
            and "The legs are steady." in cycle2_text
            and "A spoon lies on its side" in cycle2_text
        ),
        "record_law_proof_compression_improved_discovery": bool(
            old_new["record_compression_improves_discovery"]
        ),
        "strongest_rival_remains_stronger": bool(
            old_new["strongest_rival_still_beats_candidate"]
        ),
        "cycle2_should_proceed_to_executed_ablation_next": True,
        "rationale": (
            "Cycle2 combines the supported opening-detail preservation with the "
            "record/law/proof compression handle. This is preliminary and must be "
            "tested by executed ablation before any improvement claim."
        ),
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_gate_report(
    *,
    subject: AblationInformedSubject,
    evidence_summary: dict[str, Any],
    applied_patch_ledger: dict[str, Any],
    revised_candidate: dict[str, Any],
    diff_report: dict[str, Any],
    preliminary_comparison: dict[str, Any],
    fixture_only: bool,
) -> dict[str, Any]:
    unresolved = [
        "cycle2 requires executed ablation before any improvement claim",
        "strongest-rival pressure remains blocking",
        "internal operator approval is absent",
    ]
    if fixture_only:
        unresolved.append("fake ablation-informed revision mode is fixture-only")
    text_diff_consistency = bool(
        diff_report["text_matches_diff"]
        and diff_report["all_applied_patches_reflected_in_text"]
        and diff_report["all_diff_spans_reflected_in_text"]
        and diff_report["diff_changed_span_count"]
        == applied_patch_ledger["applied_patch_count"]
    )
    comparison_uses_actual = bool(
        preliminary_comparison["comparison_uses_actual_revised_text"]
        and preliminary_comparison["actual_revised_text_sha256"]
        == revised_candidate["text_sha256"]
    )
    gate_results = [
        _gate_result("ablation_informed_revision_packet_exists", True),
        _gate_result(
            "previous_repair_causal_status_recorded",
            evidence_summary["previous_repair_causal_status"]
            in {"noncausal_or_cosmetic", "ambiguous", "useful_but_insufficient"},
        ),
        _gate_result("cycle2_bounded_revision_produced", True),
        _gate_result("cycle2_text_diff_integrity_passed", text_diff_consistency),
        _gate_result(
            "cycle2_comparison_uses_actual_revised_text",
            comparison_uses_actual,
        ),
        _gate_result("strongest_rival_pressure_preserved", True),
        _gate_result(
            "cycle2_executed_ablation_completed",
            False,
            ["cycle2 has not yet been tested by executed counterfactual ablation"],
        ),
        _gate_result("no_unresolved_internal_blockers", False, unresolved),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator approval is intentionally absent"],
            record=False,
        ),
    ]
    return {
        "worker": "cycle2_gate_report_v1_controller",
        "profile": "autonomous_creative_candidate",
        "passed": False,
        "eligible": False,
        "previous_repair_causal_status": evidence_summary[
            "previous_repair_causal_status"
        ],
        "previous_repair_treated_as_proven": False,
        "cycle2_bounded_revision_produced": bool(revised_candidate["text"]),
        "integrity": {
            "proposed_patch_count": applied_patch_ledger["proposed_patch_count"],
            "applied_patch_count": applied_patch_ledger["applied_patch_count"],
            "rejected_patch_count": applied_patch_ledger["rejected_patch_count"],
            "text_diff_consistency_passed": text_diff_consistency,
            "comparison_uses_actual_revised_text": comparison_uses_actual,
            "ready_for_executed_ablation": (
                text_diff_consistency and comparison_uses_actual
            ),
        },
        "strongest_rival_pressure_preserved": preliminary_comparison[
            "strongest_rival_remains_stronger"
        ],
        "cycle2_requires_executed_ablation_before_claim": True,
        "operator_approval_absent": True,
        "unresolved_blockers": unresolved,
        "gate_results": gate_results,
        "failed_gates": [
            result["gate_name"] for result in gate_results if not result["passed"]
        ],
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "human_validation_required": False,
        "paper_validation_required": False,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
        "not_human_data": True,
        "summary_verdict": (
            "Cycle2 produced a bounded ablation-informed revision, but it remains "
            "diagnostic, non-final, and requires executed ablation before any "
            "improvement claim."
        ),
        "source_executed_ablation_packet_id": subject.packet_id,
    }


def _build_packet_summary(
    *,
    subject: AblationInformedSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    model: str | None,
    model_results: list[ModelDriverResult],
    fixture_only: bool,
) -> dict[str, Any]:
    return {
        "worker": "cycle2_packet_v1",
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_executed_ablation_packet_id": subject.packet_id,
        "source_executed_ablation_packet_dir": str(subject.packet_dir),
        "source_revision_packet_kind": subject.source_revision_packet_kind,
        "source_revision_packet_id": subject.revision_packet_id,
        "source_revision_packet_dir": str(subject.revision_packet_dir),
        "source_autonomous_revision_packet_id": subject.revision_packet_id,
        "source_reader_lab_packet_id": subject.reader_lab_packet_id,
        "artifact_types": list(ABLATION_INFORMED_REVISION_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "ablation_informed_revision_artifacts": len(artifacts),
            "required_ablation_informed_revision_artifacts": len(
                ABLATION_INFORMED_REVISION_ARTIFACT_TYPES
            ),
            "model_calls": len(model_results),
        },
        "model": model,
        "model_call_ids": [result.model_call.id for result in model_results],
        "selected_base_choice": payloads["cycle2_base_candidate_selection"][
            "selected_base_choice"
        ],
        "selected_next_handle": payloads["selected_next_failure_or_handle"][
            "selected_next_handle"
        ],
        "previous_repair_causal_status": payloads["ablation_evidence_summary"][
            "previous_repair_causal_status"
        ],
        "previous_repair_treated_as_proven": False,
        "gate_report": payloads["cycle2_gate_report"],
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
        "not_human_data": True,
    }


def _load_subject(connection, packet_dir: Path) -> AblationInformedSubject:
    packet_envelope = read_json_file(packet_dir / "executed_ablation_packet.json")
    if packet_envelope.get("artifact_type") != "executed_ablation_packet":
        raise ValueError("packet must contain executed_ablation_packet.json")
    packet_payload = packet_envelope["payload"]
    if not isinstance(packet_payload, dict):
        raise ValueError("executed ablation packet payload is not an object")
    run_id = str(packet_envelope["run_id"])
    packet_id = str(packet_payload.get("packet_id", packet_dir.name))
    artifact_ids = dict(packet_payload["artifact_ids"])

    required = (
        "executed_ablation_subject_manifest",
        "executed_ablation_work_order",
        "actual_ablation_variant_set",
        "ablation_execution_report",
        "ablation_internal_reader_comparison",
        "ablation_old_new_rival_comparison",
        "comparison_consistency_report",
        "ablation_causal_effect_report",
        "executed_ablation_gate_report",
    )
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in required:
        artifact = _artifact_from_packet(connection, artifact_ids, artifact_type)
        artifacts[artifact_type] = artifact
        payloads[artifact_type] = _artifact_payload(artifact)
    packet_artifact = _artifact_by_path(
        connection,
        run_id=run_id,
        artifact_path=packet_dir / "executed_ablation_packet.json",
    )
    if packet_artifact is not None:
        artifacts["executed_ablation_packet"] = packet_artifact
        payloads["executed_ablation_packet"] = packet_payload

    subject_manifest = payloads["executed_ablation_subject_manifest"]
    revision_packet_dir = Path(str(subject_manifest["revision_packet_dir"])).resolve()
    source_kind = _detect_source_revision_kind(subject_manifest, revision_packet_dir)
    if source_kind == SOURCE_REVISION_KIND_AUTONOMOUS:
        (
            revision_packet,
            revision_packet_id,
            revision_artifacts,
            revision_payloads,
            source_packet_dir,
            reader_lab_packet_dir,
            reader_lab_packet_id,
        ) = _load_autonomous_source_revision(connection, revision_packet_dir)
    elif source_kind == SOURCE_REVISION_KIND_ABLATION_INFORMED:
        (
            revision_packet,
            revision_packet_id,
            revision_artifacts,
            revision_payloads,
            source_packet_dir,
            reader_lab_packet_dir,
            reader_lab_packet_id,
        ) = _load_ablation_informed_source_revision(connection, revision_packet_dir)
    else:
        raise ValueError(f"unsupported source revision packet kind: {source_kind}")

    source_texts = _load_source_texts(source_packet_dir)
    if not any(text.source_class == "abi_candidate" for text in source_texts):
        raise ValueError("source packet does not include an Abi candidate text")
    return AblationInformedSubject(
        run_id=run_id,
        packet_dir=packet_dir,
        packet_id=packet_id,
        packet_artifact_id=packet_artifact.id if packet_artifact is not None else None,
        artifacts=artifacts,
        payloads=payloads,
        source_revision_packet_kind=source_kind,
        revision_packet_dir=revision_packet_dir,
        revision_packet_id=revision_packet_id,
        revision_artifacts=revision_artifacts,
        revision_payloads=revision_payloads,
        reader_lab_packet_dir=reader_lab_packet_dir,
        reader_lab_packet_id=reader_lab_packet_id,
        source_packet_dir=source_packet_dir,
        source_packet_id=str(revision_packet["source_packet_id"]),
        source_texts=tuple(source_texts),
    )


def _detect_source_revision_kind(
    subject_manifest: dict[str, Any],
    revision_packet_dir: Path,
) -> str:
    declared = str(subject_manifest.get("revision_packet_kind", ""))
    if declared in {
        SOURCE_REVISION_KIND_AUTONOMOUS,
        SOURCE_REVISION_KIND_ABLATION_INFORMED,
    }:
        return declared
    if (revision_packet_dir / "autonomous_closed_loop_packet.json").exists():
        return SOURCE_REVISION_KIND_AUTONOMOUS
    if (revision_packet_dir / "cycle2_packet.json").exists():
        return SOURCE_REVISION_KIND_ABLATION_INFORMED
    if any(
        (revision_packet_dir / filename).exists()
        for filename in ABLATION_INFORMED_SOURCE_REQUIRED_FILES[1:]
    ):
        raise ValueError(
            "ablation_informed_revision source is missing cycle2_packet.json"
        )
    raise ValueError(
        "source revision packet must contain autonomous_closed_loop_packet.json "
        "or cycle2_packet.json"
    )


def _load_autonomous_source_revision(
    connection,
    revision_packet_dir: Path,
) -> tuple[
    dict[str, Any],
    str,
    dict[str, ArtifactRecord],
    dict[str, dict[str, Any]],
    Path,
    Path,
    str,
]:
    revision_packet = read_json_file(
        revision_packet_dir / "autonomous_closed_loop_packet.json"
    )["payload"]
    revision_artifact_ids = dict(revision_packet["artifact_ids"])
    revision_required = (
        "autonomous_revision_subject_manifest",
        "selected_failure_diagnosis",
        "autonomous_revision_work_order",
        "revision_patch_proposal",
        "revised_candidate_text",
        "revision_diff_report",
        "old_new_rival_comparison",
        "local_law_case_note",
    )
    revision_artifacts: dict[str, ArtifactRecord] = {}
    revision_payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in revision_required:
        artifact = _artifact_from_packet(connection, revision_artifact_ids, artifact_type)
        revision_artifacts[artifact_type] = artifact
        revision_payloads[artifact_type] = _artifact_payload(artifact)
    return (
        revision_packet,
        str(revision_packet["packet_id"]),
        revision_artifacts,
        revision_payloads,
        Path(str(revision_packet["source_packet_dir"])).resolve(),
        Path(str(revision_packet["reader_lab_packet_dir"])).resolve(),
        str(revision_packet["reader_lab_packet_id"]),
    )


def _load_ablation_informed_source_revision(
    connection,
    revision_packet_dir: Path,
) -> tuple[
    dict[str, Any],
    str,
    dict[str, ArtifactRecord],
    dict[str, dict[str, Any]],
    Path,
    Path,
    str,
]:
    revision_packet_envelope, revision_packet = _read_source_revision_payload_file(
        revision_packet_dir,
        "cycle2_packet.json",
        "cycle2_packet",
    )
    revision_artifact_ids = dict(revision_packet["artifact_ids"])
    required = {
        "ablation_informed_revision_subject_manifest": (
            "ablation_informed_revision_subject_manifest.json",
            "ablation_informed_revision_subject_manifest",
        ),
        "ablation_informed_revision_work_order": (
            "ablation_informed_revision_work_order.json",
            "ablation_informed_revision_work_order",
        ),
        "cycle2_patch_proposal": (
            "cycle2_patch_proposal.json",
            "cycle2_patch_proposal",
        ),
        "cycle2_applied_patch_ledger": (
            "cycle2_applied_patch_ledger.json",
            "cycle2_applied_patch_ledger",
        ),
        "cycle2_revised_candidate_text": (
            "cycle2_revised_candidate_text.json",
            "cycle2_revised_candidate_text",
        ),
        "cycle2_revision_diff_report": (
            "cycle2_revision_diff_report.json",
            "cycle2_revision_diff_report",
        ),
        "cycle2_gate_report": ("cycle2_gate_report.json", "cycle2_gate_report"),
    }
    optional = {
        "cycle2_preliminary_old_new_rival_comparison": (
            "cycle2_preliminary_old_new_rival_comparison.json",
            "cycle2_preliminary_old_new_rival_comparison",
        ),
        "ablation_evidence_summary": (
            "ablation_evidence_summary.json",
            "ablation_evidence_summary",
        ),
        "selected_next_failure_or_handle": (
            "selected_next_failure_or_handle.json",
            "selected_next_failure_or_handle",
        ),
    }
    revision_artifacts: dict[str, ArtifactRecord] = {}
    revision_payloads: dict[str, dict[str, Any]] = {}
    cycle2_packet_artifact = _artifact_by_path(
        connection,
        run_id=str(revision_packet_envelope["run_id"]),
        artifact_path=revision_packet_dir / "cycle2_packet.json",
    )
    if cycle2_packet_artifact is not None:
        revision_artifacts["cycle2_packet"] = cycle2_packet_artifact
        revision_payloads["cycle2_packet"] = revision_packet
    for artifact_type, (filename, expected_type) in required.items():
        _read_source_revision_payload_file(
            revision_packet_dir,
            filename,
            expected_type,
        )
        artifact = _artifact_from_packet(connection, revision_artifact_ids, artifact_type)
        revision_artifacts[artifact_type] = artifact
        revision_payloads[artifact_type] = _artifact_payload(artifact)
    for artifact_type, (filename, expected_type) in optional.items():
        if not (revision_packet_dir / filename).exists():
            continue
        _read_source_revision_payload_file(
            revision_packet_dir,
            filename,
            expected_type,
        )
        artifact = _artifact_from_packet(connection, revision_artifact_ids, artifact_type)
        revision_artifacts[artifact_type] = artifact
        revision_payloads[artifact_type] = _artifact_payload(artifact)

    _validate_ablation_informed_source_readiness(revision_payloads)
    _alias_revision_artifact(
        revision_artifacts,
        revision_payloads,
        alias="revised_candidate_text",
        source="cycle2_revised_candidate_text",
    )
    _alias_revision_artifact(
        revision_artifacts,
        revision_payloads,
        alias="revision_diff_report",
        source="cycle2_revision_diff_report",
    )
    _alias_revision_artifact(
        revision_artifacts,
        revision_payloads,
        alias="autonomous_revision_work_order",
        source="ablation_informed_revision_work_order",
    )
    _alias_revision_artifact(
        revision_artifacts,
        revision_payloads,
        alias="revision_patch_proposal",
        source="cycle2_patch_proposal",
    )
    _alias_revision_artifact(
        revision_artifacts,
        revision_payloads,
        alias="selected_failure_diagnosis",
        source="selected_next_failure_or_handle",
    )
    if "cycle2_preliminary_old_new_rival_comparison" in revision_artifacts:
        _alias_revision_artifact(
            revision_artifacts,
            revision_payloads,
            alias="old_new_rival_comparison",
            source="cycle2_preliminary_old_new_rival_comparison",
        )

    subject_manifest = revision_payloads["ablation_informed_revision_subject_manifest"]
    revision_packet = dict(revision_packet)
    revision_packet["source_packet_id"] = subject_manifest["source_packet_id"]
    source_packet_dir = Path(str(subject_manifest["source_packet_dir"])).resolve()
    reader_lab_packet_dir = Path(
        str(subject_manifest["source_reader_lab_packet_dir"])
    ).resolve()
    return (
        revision_packet,
        str(revision_packet["packet_id"]),
        revision_artifacts,
        revision_payloads,
        source_packet_dir,
        reader_lab_packet_dir,
        str(subject_manifest["source_reader_lab_packet_id"]),
    )


def _read_source_revision_payload_file(
    packet_dir: Path,
    filename: str,
    expected_artifact_type: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = packet_dir / filename
    if not path.exists():
        raise ValueError(f"ablation_informed_revision source is missing {filename}")
    envelope = read_json_file(path)
    if envelope.get("artifact_type") != expected_artifact_type:
        raise ValueError(
            f"{filename} must have artifact_type {expected_artifact_type}"
        )
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"{filename} payload is not an object")
    return envelope, payload


def _validate_ablation_informed_source_readiness(
    revision_payloads: dict[str, dict[str, Any]],
) -> None:
    revised = revision_payloads["cycle2_revised_candidate_text"]
    diff = revision_payloads["cycle2_revision_diff_report"]
    ledger = revision_payloads["cycle2_applied_patch_ledger"]
    gate = revision_payloads["cycle2_gate_report"]
    integrity = gate.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("cycle2_gate_report integrity block is missing")
    for field_name in (
        "text_diff_consistency_passed",
        "comparison_uses_actual_revised_text",
    ):
        if integrity.get(field_name) is not True:
            raise ValueError(f"cycle2_gate_report integrity.{field_name} must be true")
    if revised.get("no_phase_shift_claim") is not True or gate.get("no_phase_shift_claim") is not True:
        raise ValueError("ablation_informed_revision source must not make a phase-shift claim")
    if (
        revised.get("not_finalization_eligible") is not True
        or gate.get("not_finalization_eligible") is not True
        or gate.get("finalization_eligible") is not False
    ):
        raise ValueError(
            "ablation_informed_revision source must remain not finalization eligible"
        )
    if diff.get("text_matches_diff") is not True:
        raise ValueError("cycle2_revision_diff_report text_matches_diff must be true")
    if ledger.get("all_applied_patches_reflected_in_text") is not True:
        raise ValueError(
            "cycle2_applied_patch_ledger all_applied_patches_reflected_in_text must be true"
        )


def _alias_revision_artifact(
    revision_artifacts: dict[str, ArtifactRecord],
    revision_payloads: dict[str, dict[str, Any]],
    *,
    alias: str,
    source: str,
) -> None:
    if source not in revision_artifacts:
        return
    revision_artifacts[alias] = revision_artifacts[source]
    revision_payloads[alias] = revision_payloads[source]


def _artifact_from_packet(
    connection,
    artifact_ids: dict[str, object],
    artifact_type: str,
) -> ArtifactRecord:
    artifact_id = artifact_ids.get(artifact_type)
    if artifact_id is None:
        raise ValueError(f"packet is missing artifact ID for {artifact_type}")
    artifact = get_artifact(connection, str(artifact_id))
    if artifact is None:
        raise ValueError(f"artifact is not registered: {artifact_id}")
    return artifact


def _artifact_by_path(connection, *, run_id: str, artifact_path: Path) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT id
        FROM artifacts
        WHERE run_id = ?
          AND path = ?
        """,
        (run_id, str(artifact_path)),
    ).fetchone()
    if row is None:
        return None
    return get_artifact(connection, row["id"])


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    envelope = read_json_file(artifact.path)
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise ValueError(f"artifact payload is not an object: {artifact.id}")
    return payload


def _load_source_texts(source_packet_dir: Path) -> list[SourceText]:
    bundle = read_json_file(source_packet_dir / "pilot_blinded_reader_bundle.json")["payload"]
    label_map = read_json_file(source_packet_dir / "pilot_neutral_label_map_private.json")[
        "payload"
    ]["label_map"]
    texts: list[SourceText] = []
    for item in bundle["reader_items"]:
        label = str(item["label"])
        private_entry = label_map[label]
        source_class = str(private_entry["source_class"])
        if source_class == "strongest_rival_slot":
            continue
        texts.append(
            SourceText(
                label=label,
                source_class=source_class,
                artifact_id=str(private_entry["artifact_id"]),
                text=str(item["text"]).strip(),
            )
        )
    return texts


def _compose_cycle2_base_from_evidence(original: str, source_revision_text: str) -> str:
    text = original.replace(" as if nothing happened", "", 1)
    text = text.replace("The legs are plain.", "The legs are steady.", 1)
    text = text.replace("A spoon lies beside", "A spoon lies on its side beside", 1)
    text = text.replace(
        "The room is quiet enough that the refrigerator hum is almost weather.",
        "The room is quiet enough that the refrigerator hum feels like a small engine of weather.",
        1,
    )
    if not _patchable_spans(text):
        text = source_revision_text.replace(" as if nothing happened", "", 1)
    return text


def _patchable_spans(text: str) -> list[dict[str, Any]]:
    spans = []
    for index, before in enumerate(_cycle2_replacements(), start=1):
        start = text.find(before)
        if start < 0:
            continue
        spans.append(
            {
                "patch_span_id": f"cycle2_patch_span_{index:03d}",
                "patch_target_id": "cycle2_target_record_law_proof_answer_compression",
                "char_start": start,
                "char_end": start + len(before),
                "exact_text": before,
                "selection_basis": "executed ablation record/law/proof/answer handle",
            }
        )
    return spans


def _candidate_span_inventory(text: str) -> list[dict[str, Any]]:
    inventory = []
    for index, paragraph in enumerate(text.split("\n\n"), start=1):
        if not paragraph.strip():
            continue
        inventory.append(
            {
                "span_id": f"cycle2_candidate_paragraph_{index:03d}",
                "paragraph_index": index,
                "text_sha256": sha256_text(paragraph.strip()),
                "word_count": len(_words(paragraph)),
            }
        )
    return inventory


def _cycle2_replacements() -> dict[str, str]:
    return {
        (
            "together they make a record. Not a message sent from elsewhere. "
            "A local record. The kind of record that is not trying to be believed, "
            "only noticed."
        ): (
            "together they leave a pattern. Not a message sent from elsewhere, "
            "only a set of marks asking to be noticed."
        ),
        "It obeys a law of staying and change.": "It keeps staying and change together.",
        (
            "The proof, if there is one, cannot arrive from outside the line it is "
            "meant to join."
        ): (
            "If an answer comes, it cannot arrive from outside the line it is "
            "meant to join."
        ),
        "It did not explain the night": "It held the night in the grain",
        "No visible completed answer has entered this local story.": (
            "No completed answer has entered this local story."
        ),
    }


def _span_before_from_patch_id(
    base_selection: dict[str, Any],
    patch: dict[str, Any],
) -> str | None:
    text = str(base_selection["selected_base_text"])
    replacements = _cycle2_replacements()
    for before, after in replacements.items():
        if after == patch["replacement_text"] and before in text:
            return before
    return None


def _base_option(choice: str, text: str, basis: str) -> dict[str, Any]:
    return {
        "base_candidate_id": choice,
        "choice": choice,
        "basis": basis,
        "text_sha256": sha256_text(text),
        "word_count": len(_words(text)),
    }


def _base_options(subject: AblationInformedSubject) -> list[dict[str, Any]]:
    original = subject.original_candidate.text
    source_revision = subject.source_revised_candidate_text
    embodiment = _variant_text_by_operation_id(
        subject,
        "operation_embodiment_preserving_repair",
        fallback=source_revision,
    )
    record = _variant_text_by_operation_id(
        subject,
        "operation_record_label_compression",
        fallback=source_revision,
    )
    controller_composed = _compose_cycle2_base_from_evidence(original, source_revision)
    return [
        _base_option(
            BASE_CHOICE_ORIGINAL,
            original,
            "original reader-facing candidate from the pilot packet",
        ),
        _base_option(
            BASE_CHOICE_PACKET_0030,
            source_revision,
            (
                "prior source revision packet; not treated as proven "
                f"({subject.source_revision_packet_kind})"
            ),
        ),
        _base_option(
            BASE_CHOICE_EMBODIMENT,
            embodiment,
            "executed ablation embodiment-preserving variant",
        ),
        _base_option(
            BASE_CHOICE_RECORD,
            record,
            "executed ablation record-label compression variant",
        ),
        _base_option(
            BASE_CHOICE_CONTROLLER_COMPOSED,
            controller_composed,
            "controller-composed base from evidence-supported changes",
        ),
    ]


def _base_text_for_choice(subject: AblationInformedSubject, choice: str) -> str:
    if choice == BASE_CHOICE_ORIGINAL:
        return subject.original_candidate.text
    if choice == BASE_CHOICE_PACKET_0030:
        return subject.source_revised_candidate_text
    if choice == BASE_CHOICE_EMBODIMENT:
        return _variant_text_by_operation_id(
            subject,
            "operation_embodiment_preserving_repair",
            fallback=subject.source_revised_candidate_text,
        )
    if choice == BASE_CHOICE_RECORD:
        return _variant_text_by_operation_id(
            subject,
            "operation_record_label_compression",
            fallback=subject.source_revised_candidate_text,
        )
    if choice == BASE_CHOICE_CONTROLLER_COMPOSED:
        return _compose_cycle2_base_from_evidence(
            subject.original_candidate.text,
            subject.source_revised_candidate_text,
        )
    raise ModelValidationError(
        "selected_base_candidate_id must be one of controller-owned base options"
    )


def _variant_text_by_operation_id(
    subject: AblationInformedSubject,
    operation_id: str,
    *,
    fallback: str,
) -> str:
    variant = subject.variant_by_operation_id(operation_id)
    if variant is None:
        return fallback
    return str(variant.get("text", fallback))


def _evidence_interpretation(
    causal: dict[str, Any],
    old_new: dict[str, Any],
) -> str:
    status = str(causal["selected_repair_causal_status"])
    support = bool(old_new["repair_has_causal_support"])
    record = bool(old_new["record_compression_improves_discovery"])
    rival_blocking = bool(causal["strongest_rival_pressure_remains_blocking"])
    next_action = str(causal["recommended_next_action"])
    return (
        "Executed ablation reports selected_repair_causal_status="
        f"{status}, repair_has_causal_support={support}, "
        f"record_compression_improves_discovery={record}, and "
        f"strongest_rival_pressure_remains_blocking={rival_blocking}. "
        f"Recommended next action: {next_action}. The next bounded revision "
        "may use this diagnostic evidence, but it remains non-final and must "
        "not treat the source revision as final proof."
    )


def _source_revision_preservation_notes(
    subject: AblationInformedSubject,
) -> tuple[str, ...]:
    if subject.source_revision_packet_kind == SOURCE_REVISION_KIND_ABLATION_INFORMED:
        ledger = subject.revision_payloads.get("cycle2_applied_patch_ledger", {})
        return tuple(
            f"source patch {patch_id} may be preserved if supported"
            for patch_id in ledger.get("applied_patch_ids", [])
        )
    return ("removed 'as if nothing happened' from the opening embodiment field",)


def _score_text(text: str) -> dict[str, int]:
    lower = text.lower()
    detail_terms = (
        "table",
        "ring",
        "dust",
        "spoon",
        "saucer",
        "grain",
        "window",
        "refrigerator",
        "floor",
        "crumb",
        "shadow",
        "cold",
        "colder",
        "steady",
        "side",
    )
    thesis_terms = (
        "record",
        "law",
        "proof",
        "explain",
        "message",
        "pattern",
        "formal",
        "completion",
        "legible",
        "answer",
    )
    embodiment = sum(lower.count(term) for term in detail_terms)
    overexplanation = sum(lower.count(term) for term in thesis_terms)
    discovery = max(0, embodiment - overexplanation)
    return {
        "local_embodiment_score": embodiment,
        "overexplanation_score": overexplanation,
        "discovery_score": discovery,
        "word_count": len(_words(text)),
    }


def _text_ref(text: SourceText | None) -> dict[str, object] | None:
    if text is None:
        return None
    return {
        "label": text.label,
        "source_class": text.source_class,
        "artifact_id": text.artifact_id,
        "text_sha256": sha256_text(text.text),
        "word_count": len(_words(text.text)),
    }


def _source_patch_ledger_reference(
    subject: AblationInformedSubject,
) -> dict[str, object] | None:
    if "cycle2_applied_patch_ledger" not in subject.revision_artifacts:
        return None
    ledger = subject.revision_payloads["cycle2_applied_patch_ledger"]
    return {
        "artifact_id": subject.revision_artifacts["cycle2_applied_patch_ledger"].id,
        "applied_patch_ids": list(ledger.get("applied_patch_ids", [])),
        "applied_patch_span_ids": list(ledger.get("applied_patch_span_ids", [])),
        "rejected_patch_ids": list(ledger.get("rejected_patch_ids", [])),
        "all_applied_patches_reflected_in_text": ledger.get(
            "all_applied_patches_reflected_in_text"
        ),
    }


def _subject_parent_ids(subject: AblationInformedSubject) -> list[str]:
    parent_ids = [artifact.id for artifact in subject.artifacts.values()]
    parent_ids.extend(artifact.id for artifact in subject.revision_artifacts.values())
    parent_ids.extend(text.artifact_id for text in subject.source_texts)
    return sorted(set(parent_ids))


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
        "blocking_defects": list(blocking_defects or []),
        "record": record,
    }


def _summary_payload(
    *,
    subject: AblationInformedSubject,
    packet_dir: Path,
    client_name: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    accepted: bool,
    message: str | None,
    model: str | None,
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    return {
        "accepted": accepted,
        "refused": False,
        "client": client_name,
        "model": model,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "executed_ablation_packet_dir": str(subject.packet_dir),
        "source_revision_packet_kind": subject.source_revision_packet_kind,
        "source_revision_packet_id": subject.revision_packet_id,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "required_artifact_types": list(ABLATION_INFORMED_REVISION_ARTIFACT_TYPES),
        "counts": {
            "ablation_informed_revision_artifacts": len(artifacts),
            "required_ablation_informed_revision_artifacts": len(
                ABLATION_INFORMED_REVISION_ARTIFACT_TYPES
            ),
            "model_calls": len(model_results),
        },
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "gate_report": payloads.get("cycle2_gate_report"),
        "message": message,
    }


def _refusal(
    *,
    client_name: str,
    model: str | None,
    executed_ablation_packet: Path | str,
    message: str,
) -> AblationInformedRevisionResult:
    return AblationInformedRevisionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "executed_ablation_packet": str(executed_ablation_packet),
            "artifact_ids": {},
            "artifact_paths": {},
            "counts": {"model_calls": 0},
            "message": message,
        },
    )


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (config.root / path).resolve()


def _words(text: str) -> list[str]:
    return [word.strip(".,;:!?()[]{}\"'").lower() for word in text.split() if word.strip()]


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
