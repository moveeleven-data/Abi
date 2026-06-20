"""Executed counterfactual ablation v1 diagnostic packet."""

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
    EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA,
    ModelValidationError,
    WorkerRole,
)
from abi.packets import PacketWriter, create_packet_dir, read_json_file


EXECUTED_ABLATION_LINEAGE_ID = "executed_counterfactual_ablation_v1"
EXECUTED_ABLATION_ACTIVE_PHASE = "executed_counterfactual_ablation_v1"
EXECUTED_ABLATION_CLIENT_FAKE = "fake"
EXECUTED_ABLATION_CLIENT_OPENAI = "openai"
EXECUTED_ABLATION_CLIENTS = (
    EXECUTED_ABLATION_CLIENT_FAKE,
    EXECUTED_ABLATION_CLIENT_OPENAI,
)
EXECUTED_ABLATION_MAX_MODEL_CALLS_DEFAULT = 8
EXECUTED_ABLATION_REQUIRED_MODEL_CALLS = 1

EXECUTED_ABLATION_ARTIFACT_TYPES = (
    "executed_ablation_subject_manifest",
    "executed_ablation_work_order",
    "actual_ablation_variant_set",
    "ablation_execution_report",
    "ablation_internal_reader_comparison",
    "ablation_old_new_rival_comparison",
    "comparison_consistency_report",
    "ablation_causal_effect_report",
    "executed_ablation_gate_report",
    "executed_ablation_packet",
)

EXECUTED_ABLATION_ALLOWED_OPERATION_IDS = (
    "operation_revert_applied_patch",
    "operation_embodiment_preserving_repair",
    "operation_record_label_compression",
    "operation_no_op_control",
    "operation_mismatch_control",
    "operation_planned_probe_only",
)
EXECUTED_ABLATION_ALLOWED_VARIANT_IDS = tuple(
    f"executed_ablation_variant_{index:03d}" for index in range(1, 7)
)
EXECUTED_ABLATION_PROVENANCE_TOKENS = (
    "original_candidate_text",
    "revised_candidate_text",
    "actual_ablation_variant",
    "strongest_rival_text",
    "direct_prompt_baseline_text",
    "raw_model_baseline_text",
    "revision_diff_report",
    "revision_patch_proposal",
    "local_law_case_note",
)


@dataclass(frozen=True)
class ExecutedAblationResult:
    exit_code: int
    payload: dict[str, object]
    gate_records: tuple[GateRecord, ...] = ()
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class SourceText:
    label: str
    source_class: str
    artifact_id: str
    text: str


@dataclass(frozen=True)
class ExecutedAblationSubject:
    run_id: str
    revision_packet_dir: Path
    revision_packet_id: str
    revision_packet_artifact_id: str | None
    source_packet_dir: Path
    source_packet_id: str
    revision_artifacts: dict[str, ArtifactRecord]
    revision_payloads: dict[str, dict[str, Any]]
    source_texts: tuple[SourceText, ...]

    @property
    def original_candidate(self) -> SourceText:
        return self.text_by_source_class("abi_candidate")

    @property
    def revised_text(self) -> str:
        return str(self.revision_payloads["revised_candidate_text"]["text"])

    @property
    def strongest_rival(self) -> SourceText | None:
        for text in self.source_texts:
            if text.source_class == "strongest_rival":
                return text
        return None

    @property
    def baselines(self) -> tuple[SourceText, ...]:
        return tuple(
            text
            for text in self.source_texts
            if text.source_class in {"direct_prompt_baseline", "raw_model_baseline"}
        )

    def text_by_source_class(self, source_class: str) -> SourceText:
        for text in self.source_texts:
            if text.source_class == source_class:
                return text
        raise KeyError(source_class)


class ExecutedAblationError(ValueError):
    """Raised when executed ablation evidence is internally inconsistent."""


def run_executed_ablation(
    config: AbiConfig,
    *,
    client_name: str,
    revision_packet: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = EXECUTED_ABLATION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> ExecutedAblationResult:
    if client_name not in EXECUTED_ABLATION_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            revision_packet=revision_packet,
            message=f"Executed ablation client is not available: {client_name}",
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < 0:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            revision_packet=revision_packet,
            message="Executed ablation refused; max-model-calls must be non-negative.",
        )
    if client_name == EXECUTED_ABLATION_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            revision_packet=revision_packet,
            message=(
                "Executed ablation refused; pass --allow-live-model to opt in explicitly."
            ),
        )
    resolved_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == EXECUTED_ABLATION_CLIENT_OPENAI and not resolved_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            revision_packet=revision_packet,
            message=f"Executed ablation refused; {OPENAI_API_KEY_ENV} is not set.",
        )
    if (
        client_name == EXECUTED_ABLATION_CLIENT_OPENAI
        and max_model_calls < EXECUTED_ABLATION_REQUIRED_MODEL_CALLS
    ):
        return _refusal(
            client_name=client_name,
            model=configured_model,
            revision_packet=revision_packet,
            message=(
                "Executed ablation refused; max-model-calls "
                f"{max_model_calls} is below required budget "
                f"{EXECUTED_ABLATION_REQUIRED_MODEL_CALLS}."
            ),
        )

    revision_packet_dir = _resolve_path(config, revision_packet)
    if not revision_packet_dir.exists() or not revision_packet_dir.is_dir():
        return _refusal(
            client_name=client_name,
            model=configured_model,
            revision_packet=revision_packet_dir,
            message=(
                "Executed ablation refused; autonomous revision packet directory not found: "
                f"{revision_packet_dir}"
            ),
        )

    initialize_database(config)
    try:
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, revision_packet_dir)
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    client_name=client_name,
                    model=configured_model,
                    revision_packet=revision_packet_dir,
                    message=(
                        "Executed ablation refused; revision run is not registered: "
                        f"{subject.run_id}"
                    ),
                )
            output_dir = create_packet_dir(config.run_dir(subject.run_id) / "executed_ablation")
            set_active_phase(connection, subject.run_id, EXECUTED_ABLATION_ACTIVE_PHASE)
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            revision_packet=revision_packet_dir,
            message=f"Executed ablation refused; invalid revision packet: {error}",
        )

    if client_name == EXECUTED_ABLATION_CLIENT_OPENAI:
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
    subject: ExecutedAblationSubject,
    output_dir: Path,
    client_name: str,
    fixture_only: bool,
    model: str | None,
    model_client: ModelClient | None,
) -> ExecutedAblationResult:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}
    model_results: list[ModelDriverResult] = []

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=EXECUTED_ABLATION_LINEAGE_ID,
            created_by="executed_counterfactual_ablation_v1_controller",
            fixture_only=fixture_only,
            model_call_id=None,
        )

        payloads["executed_ablation_subject_manifest"] = _build_subject_manifest(
            subject,
            fixture_only=fixture_only,
        )
        artifacts["executed_ablation_subject_manifest"] = writer.write_artifact(
            "executed_ablation_subject_manifest",
            payloads["executed_ablation_subject_manifest"],
            parent_ids=_subject_parent_ids(subject),
        )

        payloads["executed_ablation_work_order"] = _build_work_order(
            subject,
            fixture_only=fixture_only,
        )
        artifacts["executed_ablation_work_order"] = writer.write_artifact(
            "executed_ablation_work_order",
            payloads["executed_ablation_work_order"],
            parent_ids=[
                artifacts["executed_ablation_subject_manifest"].id,
                *[
                    subject.revision_artifacts[artifact_type].id
                    for artifact_type in (
                        "autonomous_revision_work_order",
                        "revision_patch_proposal",
                        "revision_diff_report",
                        "old_new_rival_comparison",
                        "local_law_case_note",
                    )
                    if artifact_type in subject.revision_artifacts
                ],
            ],
        )

        payloads["actual_ablation_variant_set"] = _build_actual_variant_set(
            subject,
            payloads["executed_ablation_work_order"],
            fixture_only=fixture_only,
        )
        artifacts["actual_ablation_variant_set"] = writer.write_artifact(
            "actual_ablation_variant_set",
            payloads["actual_ablation_variant_set"],
            parent_ids=[
                artifacts["executed_ablation_work_order"].id,
                subject.revision_artifacts["revised_candidate_text"].id,
                subject.revision_artifacts["revision_diff_report"].id,
            ],
        )

        payloads["ablation_execution_report"] = _build_execution_report(
            payloads["actual_ablation_variant_set"],
            fixture_only=fixture_only,
        )
        artifacts["ablation_execution_report"] = writer.write_artifact(
            "ablation_execution_report",
            payloads["ablation_execution_report"],
            parent_ids=[
                artifacts["executed_ablation_work_order"].id,
                artifacts["actual_ablation_variant_set"].id,
            ],
        )

    if model_client is not None:
        result = _run_internal_comparison_model(
            config=config,
            subject=subject,
            output_dir=output_dir,
            model_client=model_client,
            work_order=payloads["executed_ablation_work_order"],
            variant_set=payloads["actual_ablation_variant_set"],
            parent_ids=[
                artifacts["executed_ablation_work_order"].id,
                artifacts["actual_ablation_variant_set"].id,
                artifacts["ablation_execution_report"].id,
            ],
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
                message=(
                    "Executed ablation stopped by model-call failure"
                    + (
                        f": {result.model_call.error_message}"
                        if result.model_call.error_message
                        else "."
                    )
                ),
            )
        try:
            internal_comparison = _merge_model_internal_comparison(
                variant_set=payloads["actual_ablation_variant_set"],
                model_payload=result.parsed_payload,
                fixture_only=fixture_only,
                model_call_id=result.model_call.id,
            )
        except ExecutedAblationError as error:
            return _failure_result(
                client_name=client_name,
                model=model,
                subject=subject,
                packet_dir=output_dir,
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
                message=f"Executed ablation stopped by comparison merge failure: {error}",
            )
        with connect(config.db_path) as connection:
            writer = PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=output_dir,
                lineage_id=EXECUTED_ABLATION_LINEAGE_ID,
                created_by="executed_counterfactual_ablation_v1_controller",
                fixture_only=fixture_only,
                model_call_id=result.model_call.id,
            )
            payloads["ablation_internal_reader_comparison"] = internal_comparison
            artifacts["ablation_internal_reader_comparison"] = writer.write_artifact(
                "ablation_internal_reader_comparison",
                internal_comparison,
                parent_ids=[
                    artifacts["actual_ablation_variant_set"].id,
                    artifacts["ablation_execution_report"].id,
                ],
            )
            linked_call = link_model_call_parsed_artifact(
                connection,
                model_call_id=result.model_call.id,
                parsed_output_artifact_id=artifacts["ablation_internal_reader_comparison"].id,
            )
            model_results[-1] = ModelDriverResult(
                model_call=linked_call,
                parsed_payload=internal_comparison,
                parsed_artifact=artifacts["ablation_internal_reader_comparison"],
            )
    else:
        with connect(config.db_path) as connection:
            writer = PacketWriter(
                connection=connection,
                run_id=subject.run_id,
                packet_dir=output_dir,
                lineage_id=EXECUTED_ABLATION_LINEAGE_ID,
                created_by="executed_counterfactual_ablation_v1_controller",
                fixture_only=fixture_only,
                model_call_id=None,
            )
            payloads["ablation_internal_reader_comparison"] = (
                _build_internal_reader_comparison(
                    payloads["actual_ablation_variant_set"],
                    fixture_only=fixture_only,
                )
            )
            artifacts["ablation_internal_reader_comparison"] = writer.write_artifact(
                "ablation_internal_reader_comparison",
                payloads["ablation_internal_reader_comparison"],
                parent_ids=[
                    artifacts["actual_ablation_variant_set"].id,
                    artifacts["ablation_execution_report"].id,
                ],
            )

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=EXECUTED_ABLATION_LINEAGE_ID,
            created_by="executed_counterfactual_ablation_v1_controller",
            fixture_only=fixture_only,
            model_call_id=None,
        )
        payloads["ablation_old_new_rival_comparison"] = _build_old_new_rival_comparison(
            subject,
            payloads["actual_ablation_variant_set"],
            payloads["ablation_internal_reader_comparison"],
            fixture_only=fixture_only,
        )
        artifacts["ablation_old_new_rival_comparison"] = writer.write_artifact(
            "ablation_old_new_rival_comparison",
            payloads["ablation_old_new_rival_comparison"],
            parent_ids=[
                artifacts["actual_ablation_variant_set"].id,
                artifacts["ablation_internal_reader_comparison"].id,
                subject.revision_artifacts["old_new_rival_comparison"].id,
            ],
        )

        payloads["comparison_consistency_report"] = _build_comparison_consistency_report(
            variant_set=payloads["actual_ablation_variant_set"],
            internal_comparison=payloads["ablation_internal_reader_comparison"],
            old_new_comparison=payloads["ablation_old_new_rival_comparison"],
            fixture_only=fixture_only,
        )
        artifacts["comparison_consistency_report"] = writer.write_artifact(
            "comparison_consistency_report",
            payloads["comparison_consistency_report"],
            parent_ids=[
                artifacts["actual_ablation_variant_set"].id,
                artifacts["ablation_internal_reader_comparison"].id,
                artifacts["ablation_old_new_rival_comparison"].id,
            ],
        )

        payloads["ablation_causal_effect_report"] = _build_causal_effect_report(
            subject=subject,
            variant_set=payloads["actual_ablation_variant_set"],
            old_new_comparison=payloads["ablation_old_new_rival_comparison"],
            consistency_report=payloads["comparison_consistency_report"],
            fixture_only=fixture_only,
        )
        artifacts["ablation_causal_effect_report"] = writer.write_artifact(
            "ablation_causal_effect_report",
            payloads["ablation_causal_effect_report"],
            parent_ids=[
                artifacts["actual_ablation_variant_set"].id,
                artifacts["ablation_old_new_rival_comparison"].id,
                artifacts["comparison_consistency_report"].id,
            ],
        )

        payloads["executed_ablation_gate_report"] = _build_gate_report(
            subject=subject,
            variant_set=payloads["actual_ablation_variant_set"],
            execution_report=payloads["ablation_execution_report"],
            consistency_report=payloads["comparison_consistency_report"],
            causal_effect_report=payloads["ablation_causal_effect_report"],
            fixture_only=fixture_only,
        )
        artifacts["executed_ablation_gate_report"] = writer.write_artifact(
            "executed_ablation_gate_report",
            payloads["executed_ablation_gate_report"],
            parent_ids=[
                artifacts["ablation_execution_report"].id,
                artifacts["comparison_consistency_report"].id,
                artifacts["ablation_causal_effect_report"].id,
            ],
        )

        payloads["executed_ablation_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=output_dir,
            artifacts=artifacts,
            payloads=payloads,
            client_name=client_name,
            model=model,
            model_results=model_results,
            fixture_only=fixture_only,
        )
        artifacts["executed_ablation_packet"] = writer.write_artifact(
            "executed_ablation_packet",
            payloads["executed_ablation_packet"],
            parent_ids=[
                artifacts[artifact_type].id
                for artifact_type in EXECUTED_ABLATION_ARTIFACT_TYPES[:-1]
            ],
        )

    return ExecutedAblationResult(
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


def _run_internal_comparison_model(
    *,
    config: AbiConfig,
    subject: ExecutedAblationSubject,
    output_dir: Path,
    model_client: ModelClient,
    work_order: dict[str, Any],
    variant_set: dict[str, Any],
    parent_ids: list[str],
) -> ModelDriverResult:
    driver = ModelDriver(config=config, client=model_client)
    return driver.run(
        WorkerRequest(
            run_id=subject.run_id,
            worker_role=WorkerRole.EXECUTED_ABLATION_INTERNAL_COMPARATOR,
            prompt_contract_id="executed_ablation.internal_comparison.v1",
            schema=EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA,
            input_text=_prompt_for_internal_comparison(subject, work_order, variant_set),
            input_artifact_ids=parent_ids,
            input_packet_path=str(subject.revision_packet_dir),
            lineage_id=EXECUTED_ABLATION_LINEAGE_ID,
            parent_ids=parent_ids,
            fixture_only=False,
            output_dir=str(output_dir),
            register_parsed_artifact=False,
            parsed_payload_validator=lambda payload: _validate_model_comparison_variant_ids(
                variant_set,
                payload,
            ),
        )
    )


def _prompt_for_internal_comparison(
    subject: ExecutedAblationSubject,
    work_order: dict[str, Any],
    variant_set: dict[str, Any],
) -> str:
    return _canonical_json(
        {
            "prompt_contract": "executed_ablation.internal_comparison.v1",
            "candidate_label": subject.original_candidate.label,
            "revision_packet_id": subject.revision_packet_id,
            "work_order": work_order,
            "variants": [
                {
                    "variant_id": variant["variant_id"],
                    "operation_id": variant["operation_id"],
                    "operation_type": variant["operation_type"],
                    "text": variant["text"],
                    "evidence_countable": variant["evidence_countable"],
                }
                for variant in variant_set["variants"]
            ],
            "comparison_contract": (
                "Return interpretation only for exactly the provided variant_id values. "
                "Do not decide execution status, evidence_countable, gates, finalization, "
                "or rival defeat."
            ),
        }
    )


def _validate_model_comparison_variant_ids(
    variant_set: dict[str, Any],
    model_payload: dict[str, Any],
) -> None:
    expected = {str(variant["variant_id"]) for variant in variant_set["variants"]}
    rows = model_payload.get("comparison_rows")
    if not isinstance(rows, list) or not rows:
        raise ModelValidationError("comparison_rows must not be empty")
    seen = [str(row.get("variant_id", "")) for row in rows if isinstance(row, dict)]
    if len(seen) != len(set(seen)):
        raise ModelValidationError("duplicate executed ablation variant_id in comparison rows")
    missing = sorted(expected - set(seen))
    invented = sorted(set(seen) - expected)
    if missing or invented:
        details = []
        if missing:
            details.append("missing variant IDs: " + ", ".join(missing))
        if invented:
            details.append("invented variant IDs: " + ", ".join(invented))
        raise ModelValidationError("; ".join(details))


def _merge_model_internal_comparison(
    *,
    variant_set: dict[str, Any],
    model_payload: dict[str, Any],
    fixture_only: bool,
    model_call_id: str | None,
) -> dict[str, Any]:
    variants_by_id = {str(variant["variant_id"]): variant for variant in variant_set["variants"]}
    _validate_model_comparison_variant_ids(variant_set, model_payload)
    rows = []
    for row in model_payload["comparison_rows"]:
        variant = variants_by_id[str(row["variant_id"])]
        rows.append(
            {
                "variant_id": variant["variant_id"],
                "operation_id": variant["operation_id"],
                "evidence_countable": variant["evidence_countable"],
                "planned_only": variant["planned_only"],
                "comparison_summary": row["comparison_summary"],
                "reader_state_effect_estimate": row["reader_state_effect_estimate"],
                "rationale": row["rationale"],
                "uncertainty": row["uncertainty"],
                "risk_notes": row["risk_notes"],
                "not_human_data": True,
            }
        )
    return {
        "worker": "ablation_internal_reader_comparison_v1_model_driver",
        "controller_owned_evidence_status": True,
        "comparison_rows": rows,
        "summary": model_payload["summary"],
        "model_call_id": model_call_id,
        "fixture_only": fixture_only,
        "not_human_data": True,
    }


def _build_subject_manifest(
    subject: ExecutedAblationSubject,
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    return {
        "worker": "executed_ablation_subject_manifest_v1",
        "run_id": subject.run_id,
        "revision_packet_id": subject.revision_packet_id,
        "revision_packet_dir": str(subject.revision_packet_dir),
        "revision_packet_artifact_id": subject.revision_packet_artifact_id,
        "source_packet_id": subject.source_packet_id,
        "source_packet_dir": str(subject.source_packet_dir),
        "revision_artifact_ids": {
            artifact_type: artifact.id
            for artifact_type, artifact in subject.revision_artifacts.items()
        },
        "original_candidate": _text_ref(subject.original_candidate),
        "revised_candidate": {
            "artifact_id": subject.revision_artifacts["revised_candidate_text"].id,
            "text_sha256": sha256_text(subject.revised_text),
            "word_count": len(_words(subject.revised_text)),
        },
        "strongest_rival": (
            _text_ref(subject.strongest_rival) if subject.strongest_rival is not None else None
        ),
        "baselines": [_text_ref(text) for text in subject.baselines],
        "controller_owned": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_work_order(subject: ExecutedAblationSubject, *, fixture_only: bool) -> dict[str, Any]:
    work_order = subject.revision_payloads["autonomous_revision_work_order"]
    diff = subject.revision_payloads["revision_diff_report"]
    patch_proposal = subject.revision_payloads["revision_patch_proposal"]
    source_spans = _source_spans_from_revised_text(subject.revised_text)
    changed_span_ids = [str(span["changed_span_id"]) for span in diff["changed_spans"]]
    return {
        "worker": "executed_ablation_work_order_v1_controller",
        "controller_owned": True,
        "source_autonomous_revision_packet_dir": str(subject.revision_packet_dir),
        "source_autonomous_revision_packet_id": subject.revision_packet_id,
        "source_revision_artifact_ids": {
            artifact_type: artifact.id
            for artifact_type, artifact in subject.revision_artifacts.items()
        },
        "original_candidate_reference": _text_ref(subject.original_candidate),
        "revised_candidate_reference": {
            "artifact_id": subject.revision_artifacts["revised_candidate_text"].id,
            "text_sha256": sha256_text(subject.revised_text),
        },
        "selected_failure_reference": {
            "artifact_id": subject.revision_artifacts["selected_failure_diagnosis"].id,
            "selected_failure_type": subject.revision_payloads[
                "selected_failure_diagnosis"
            ].get("selected_failure_type"),
        },
        "revision_work_order_reference": {
            "artifact_id": subject.revision_artifacts["autonomous_revision_work_order"].id,
            "work_order_id": work_order.get("work_order_id"),
        },
        "revision_patch_proposal_reference": {
            "artifact_id": subject.revision_artifacts["revision_patch_proposal"].id,
            "proposal_id": patch_proposal.get("proposal_id"),
            "patch_ids": [str(patch["patch_id"]) for patch in patch_proposal.get("patches", [])],
        },
        "revision_diff_report_reference": {
            "artifact_id": subject.revision_artifacts["revision_diff_report"].id,
            "changed_span_ids": changed_span_ids,
        },
        "old_new_rival_comparison_reference": {
            "artifact_id": subject.revision_artifacts["old_new_rival_comparison"].id,
        },
        "local_law_case_note_reference": {
            "artifact_id": subject.revision_artifacts["local_law_case_note"].id,
        },
        "strongest_rival_reference": (
            _text_ref(subject.strongest_rival) if subject.strongest_rival is not None else None
        ),
        "allowed_operation_ids": list(EXECUTED_ABLATION_ALLOWED_OPERATION_IDS),
        "allowed_variant_ids": list(EXECUTED_ABLATION_ALLOWED_VARIANT_IDS),
        "allowed_source_spans": source_spans,
        "allowed_changed_span_ids": changed_span_ids,
        "allowed_source_patch_span_ids": list(
            subject.revision_payloads["revised_candidate_text"].get("source_patch_span_ids", [])
        ),
        "allowed_comparison_provenance_tokens": list(EXECUTED_ABLATION_PROVENANCE_TOKENS),
        "protected_effects": list(work_order.get("protected_effects", [])),
        "forbidden_changes": list(work_order.get("forbidden_changes", [])),
        "not_cycle_2": True,
        "does_not_create_main_candidate": True,
        "non_final": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _build_actual_variant_set(
    subject: ExecutedAblationSubject,
    work_order: dict[str, Any],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    revised = subject.revised_text
    diff = subject.revision_payloads["revision_diff_report"]
    changed_span = diff["changed_spans"][0] if diff.get("changed_spans") else {}
    source_patch_span_ids = list(
        subject.revision_payloads["revised_candidate_text"].get("source_patch_span_ids", [])
    )
    source_patch_span_id = source_patch_span_ids[0] if source_patch_span_ids else None
    changed_span_id = str(changed_span.get("changed_span_id", "change_01"))
    diff_before = str(changed_span.get("before", ""))
    diff_after = str(changed_span.get("after", ""))

    variants = [
        _variant(
            variant_id=EXECUTED_ABLATION_ALLOWED_VARIANT_IDS[0],
            operation_id="operation_revert_applied_patch",
            operation_type="revert_applied_patch",
            source_span_id=changed_span_id,
            source_patch_span_id=source_patch_span_id,
            source_patch_span_ids=source_patch_span_ids,
            base_text=revised,
            before_text=diff_after,
            after_text=diff_before,
            rationale="Test whether undoing the controller-applied repair weakens the text.",
            expected_reader_state_effect=(
                "If the repair mattered, reverting should restore more immediate thesis pressure."
            ),
        ),
        _variant(
            variant_id=EXECUTED_ABLATION_ALLOWED_VARIANT_IDS[1],
            operation_id="operation_embodiment_preserving_repair",
            operation_type="embodiment_preserving_variant",
            source_span_id=changed_span_id,
            source_patch_span_id=source_patch_span_id,
            source_patch_span_ids=source_patch_span_ids,
            base_text=revised,
            before_text=diff_after,
            after_text=_embodiment_preserving_text(diff_after),
            rationale=(
                "Test whether the repair can keep concrete details while reducing the same "
                "pre-interpretive pressure."
            ),
            expected_reader_state_effect=(
                "Should reduce overexplanation without flattening local embodiment."
            ),
        ),
        _record_compression_variant(
            variant_id=EXECUTED_ABLATION_ALLOWED_VARIANT_IDS[2],
            subject=subject,
            work_order=work_order,
        ),
        _variant(
            variant_id=EXECUTED_ABLATION_ALLOWED_VARIANT_IDS[3],
            operation_id="operation_no_op_control",
            operation_type="no_op_control",
            source_span_id="source_span_opening_sentence",
            source_patch_span_id=None,
            source_patch_span_ids=[],
            base_text=revised,
            before_text="The table is still there in the morning.",
            after_text="The table is still there in the morning.",
            rationale="Diagnostic no-op control; it must not count as evidence of repair.",
            expected_reader_state_effect="No reader-state change should be inferred.",
            planned_only=False,
            explicit_diagnostic_no_op=True,
        ),
        _variant(
            variant_id=EXECUTED_ABLATION_ALLOWED_VARIANT_IDS[4],
            operation_id="operation_mismatch_control",
            operation_type="operation_mismatch_control",
            source_span_id="source_span_record_law_proof_001",
            source_patch_span_id=None,
            source_patch_span_ids=[],
            base_text=revised,
            before_text="almost weather",
            after_text="almost weather at the edge",
            rationale=(
                "Intentional mismatch control: changed text does not match the claimed "
                "record/law/proof operation, so it is not countable evidence."
            ),
            expected_reader_state_effect="Unreliable diagnostic; must not count.",
            operation_matches_actual_change=False,
        ),
        _variant(
            variant_id=EXECUTED_ABLATION_ALLOWED_VARIANT_IDS[5],
            operation_id="operation_planned_probe_only",
            operation_type="planned_only_probe",
            source_span_id="source_span_record_law_proof_001",
            source_patch_span_id=None,
            source_patch_span_ids=[],
            base_text=revised,
            before_text="record/law/proof pressure",
            after_text="planned future compression",
            rationale="Planned-only probe retained for ledger distinction.",
            expected_reader_state_effect="Speculative only; not executed evidence.",
            planned_only=True,
            controller_applied=False,
        ),
    ]
    validated = [_validate_variant_operation(variant) for variant in variants]
    return {
        "worker": "actual_ablation_variant_set_v1_controller",
        "controller_owned": True,
        "source_revision_packet_id": subject.revision_packet_id,
        "source_revised_candidate_artifact_id": subject.revision_artifacts[
            "revised_candidate_text"
        ].id,
        "variants": validated,
        "actual_variant_count": sum(
            1 for variant in validated if not variant["planned_only"]
        ),
        "countable_evidence_variant_count": sum(
            1 for variant in validated if variant["evidence_countable"]
        ),
        "planned_only_variant_count": sum(
            1 for variant in validated if variant["planned_only"]
        ),
        "no_op_variant_count": sum(1 for variant in validated if variant["no_op"]),
        "operation_mismatch_variant_count": sum(
            1 for variant in validated if not variant["operation_matches_actual_change"]
        ),
        "does_not_select_winner": True,
        "does_not_create_main_candidate": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
    }


def _record_compression_variant(
    *,
    variant_id: str,
    subject: ExecutedAblationSubject,
    work_order: dict[str, Any],
) -> dict[str, Any]:
    revised = subject.revised_text
    transformed = revised
    replacements = (
        (
            "together they make a record. Not a message sent from elsewhere. A local record. "
            "The kind of record that is not trying to be believed, only noticed.",
            "together they leave a pattern. Not a message sent from elsewhere, only a set of marks asking to be noticed.",
        ),
        ("It obeys a law of staying and change.", "It keeps staying and change together."),
        (
            "The proof, if there is one, cannot arrive from outside the line it is meant to join.",
            "If an answer comes, it cannot arrive from outside the line it is meant to join.",
        ),
        (
            "It did not explain the night",
            "It held the night in the grain",
        ),
    )
    before_parts = []
    after_parts = []
    for before, after in replacements:
        if before in transformed:
            before_parts.append(before)
            after_parts.append(after)
            transformed = transformed.replace(before, after, 1)
    source_span_ids = [
        span["source_span_id"]
        for span in work_order["allowed_source_spans"]
        if str(span["source_span_id"]).startswith("source_span_record_law_proof")
    ]
    return _variant_from_text(
        variant_id=variant_id,
        operation_id="operation_record_label_compression",
        operation_type="record_label_compression",
        source_span_id=source_span_ids[0] if source_span_ids else "source_span_record_law_proof_001",
        source_span_ids=source_span_ids,
        source_patch_span_id=None,
        source_patch_span_ids=[],
        base_text=revised,
        variant_text=transformed,
        before_text="\n\n".join(before_parts) or "record/law/proof labels",
        after_text="\n\n".join(after_parts) or "compressed discovery language",
        rationale=(
            "Test whether the larger problem is early interpretive record/law/proof "
            "labeling rather than only the opening patch."
        ),
        expected_reader_state_effect=(
            "Should improve discovery if label compression is the stronger causal handle."
        ),
    )


def _variant(
    *,
    variant_id: str,
    operation_id: str,
    operation_type: str,
    source_span_id: str,
    source_patch_span_id: str | None,
    source_patch_span_ids: list[str],
    base_text: str,
    before_text: str,
    after_text: str,
    rationale: str,
    expected_reader_state_effect: str,
    operation_matches_actual_change: bool = True,
    planned_only: bool = False,
    controller_applied: bool = True,
    explicit_diagnostic_no_op: bool = False,
) -> dict[str, Any]:
    if planned_only:
        text = base_text
    elif before_text and before_text in base_text:
        text = base_text.replace(before_text, after_text, 1)
    else:
        text = base_text
        operation_matches_actual_change = False
    return _variant_from_text(
        variant_id=variant_id,
        operation_id=operation_id,
        operation_type=operation_type,
        source_span_id=source_span_id,
        source_span_ids=[source_span_id],
        source_patch_span_id=source_patch_span_id,
        source_patch_span_ids=source_patch_span_ids,
        base_text=base_text,
        variant_text=text,
        before_text=before_text,
        after_text=after_text,
        rationale=rationale,
        expected_reader_state_effect=expected_reader_state_effect,
        operation_matches_actual_change=operation_matches_actual_change,
        planned_only=planned_only,
        controller_applied=controller_applied,
        explicit_diagnostic_no_op=explicit_diagnostic_no_op,
    )


def _variant_from_text(
    *,
    variant_id: str,
    operation_id: str,
    operation_type: str,
    source_span_id: str,
    source_span_ids: list[str],
    source_patch_span_id: str | None,
    source_patch_span_ids: list[str],
    base_text: str,
    variant_text: str,
    before_text: str,
    after_text: str,
    rationale: str,
    expected_reader_state_effect: str,
    operation_matches_actual_change: bool = True,
    planned_only: bool = False,
    controller_applied: bool = True,
    explicit_diagnostic_no_op: bool = False,
) -> dict[str, Any]:
    changed = variant_text != base_text
    no_op = not changed
    evidence_countable = (
        controller_applied
        and not planned_only
        and changed
        and not no_op
        and operation_matches_actual_change
    )
    if no_op and not explicit_diagnostic_no_op:
        evidence_countable = False
    return {
        "variant_id": variant_id,
        "operation_id": operation_id,
        "operation_type": operation_type,
        "source_span_id": source_span_id,
        "source_span_ids": source_span_ids,
        "source_patch_span_id": source_patch_span_id,
        "source_patch_span_ids": source_patch_span_ids,
        "before_text": before_text,
        "after_text": after_text,
        "text": variant_text,
        "text_sha256": sha256_text(variant_text),
        "changed": changed,
        "operation_matches_actual_change": operation_matches_actual_change,
        "no_op": no_op,
        "explicit_diagnostic_no_op": explicit_diagnostic_no_op,
        "evidence_countable": evidence_countable,
        "controller_applied": controller_applied,
        "planned_only": planned_only,
        "rationale": rationale,
        "expected_reader_state_effect": expected_reader_state_effect,
        "not_main_candidate": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
    }


def _validate_variant_operation(variant: dict[str, Any]) -> dict[str, Any]:
    if variant["variant_id"] not in EXECUTED_ABLATION_ALLOWED_VARIANT_IDS:
        raise ExecutedAblationError(f"unsupported executed ablation variant_id: {variant['variant_id']}")
    if variant["operation_id"] not in EXECUTED_ABLATION_ALLOWED_OPERATION_IDS:
        raise ExecutedAblationError(f"unsupported executed ablation operation_id: {variant['operation_id']}")
    if not variant.get("source_span_id") and not variant.get("source_patch_span_id"):
        raise ExecutedAblationError(f"{variant['variant_id']} has no source span reference")
    evidence_countable = (
        bool(variant["controller_applied"])
        and not bool(variant["planned_only"])
        and bool(variant["changed"])
        and not bool(variant["no_op"])
        and bool(variant["operation_matches_actual_change"])
    )
    if variant["no_op"] and not variant.get("explicit_diagnostic_no_op"):
        evidence_countable = False
    if variant["planned_only"]:
        evidence_countable = False
    if not variant["operation_matches_actual_change"]:
        evidence_countable = False
    if not variant["changed"]:
        evidence_countable = False
    normalized = dict(variant)
    normalized["evidence_countable"] = evidence_countable
    return normalized


def _build_execution_report(
    variant_set: dict[str, Any],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    variants = list(variant_set["variants"])
    countable = [variant for variant in variants if variant["evidence_countable"]]
    planned = [variant for variant in variants if variant["planned_only"]]
    no_ops = [variant for variant in variants if variant["no_op"]]
    mismatches = [
        variant for variant in variants if not variant["operation_matches_actual_change"]
    ]
    return {
        "worker": "ablation_execution_report_v1_controller",
        "controller_owned": True,
        "variant_count": len(variants),
        "actual_variant_count": sum(1 for variant in variants if not variant["planned_only"]),
        "countable_evidence_variant_count": len(countable),
        "planned_only_variant_count": len(planned),
        "no_op_variant_count": len(no_ops),
        "operation_mismatch_variant_count": len(mismatches),
        "countable_variant_ids": [variant["variant_id"] for variant in countable],
        "planned_only_variant_ids": [variant["variant_id"] for variant in planned],
        "no_op_variant_ids": [variant["variant_id"] for variant in no_ops],
        "operation_mismatch_variant_ids": [variant["variant_id"] for variant in mismatches],
        "actual_executed_ablation_evidence_exists": bool(countable),
        "planned_only_not_counted": all(not variant["evidence_countable"] for variant in planned),
        "no_op_not_counted": all(not variant["evidence_countable"] for variant in no_ops),
        "operation_mismatch_not_counted": all(
            not variant["evidence_countable"] for variant in mismatches
        ),
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_internal_reader_comparison(
    variant_set: dict[str, Any],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    rows = []
    for variant in variant_set["variants"]:
        rows.append(
            {
                "variant_id": variant["variant_id"],
                "operation_id": variant["operation_id"],
                "evidence_countable": variant["evidence_countable"],
                "planned_only": variant["planned_only"],
                "comparison_summary": _variant_summary(variant),
                "reader_state_effect_estimate": _variant_effect_estimate(variant),
                "rationale": "Deterministic internal comparison, not human reader evidence.",
                "uncertainty": (
                    "not countable" if not variant["evidence_countable"] else "medium"
                ),
                "risk_notes": _variant_risk_notes(variant),
                "not_human_data": True,
            }
        )
    return {
        "worker": "ablation_internal_reader_comparison_v1_fake",
        "controller_owned_evidence_status": True,
        "comparison_rows": rows,
        "summary": (
            "Executed ablations distinguish actual text changes from planned/no-op/mismatch "
            "controls before any causal claim is allowed."
        ),
        "model_call_id": None,
        "fixture_only": fixture_only,
        "not_human_data": True,
    }


def _build_old_new_rival_comparison(
    subject: ExecutedAblationSubject,
    variant_set: dict[str, Any],
    internal_comparison: dict[str, Any],
    *,
    fixture_only: bool,
) -> dict[str, Any]:
    original_score = _score_text(subject.original_candidate.text)
    revised_score = _score_text(subject.revised_text)
    variants = {variant["operation_id"]: variant for variant in variant_set["variants"]}
    variant_scores = {
        variant["variant_id"]: _score_text(str(variant["text"]))
        for variant in variant_set["variants"]
    }
    revert = variants["operation_revert_applied_patch"]
    embodiment = variants["operation_embodiment_preserving_repair"]
    record_compression = variants["operation_record_label_compression"]
    revert_score = variant_scores[revert["variant_id"]]
    embodiment_score = variant_scores[embodiment["variant_id"]]
    record_score = variant_scores[record_compression["variant_id"]]
    rival_score = (
        _score_text(subject.strongest_rival.text)
        if subject.strongest_rival is not None
        else None
    )
    revised_improves_over_original = revised_score["overexplanation_score"] <= original_score[
        "overexplanation_score"
    ]
    revert_performs_same_or_better = _total_score(revert_score) >= _total_score(revised_score)
    embodiment_variant_beats_current = _total_score(embodiment_score) > _total_score(revised_score)
    record_compression_improves_discovery = record_score["overexplanation_score"] < revised_score[
        "overexplanation_score"
    ]
    strongest_rival_still_beats_candidate = (
        bool(rival_score and _total_score(rival_score) >= _total_score(revised_score))
        or subject.strongest_rival is not None
    )
    repair_has_causal_support = (
        not revert_performs_same_or_better
        and any(variant["evidence_countable"] for variant in variant_set["variants"])
    )
    return {
        "worker": "ablation_old_new_rival_comparison_v1",
        "controller_owned_evidence_status": True,
        "original_score": original_score,
        "revised_score": revised_score,
        "variant_scores": variant_scores,
        "strongest_rival_score": rival_score,
        "revised_improves_over_original": revised_improves_over_original,
        "revert_performs_same_or_better": revert_performs_same_or_better,
        "reverting_patch_weakens_candidate": not revert_performs_same_or_better,
        "embodiment_preserving_variant_beats_current": embodiment_variant_beats_current,
        "record_compression_improves_discovery": record_compression_improves_discovery,
        "strongest_rival_present": subject.strongest_rival is not None,
        "strongest_rival_still_beats_candidate": strongest_rival_still_beats_candidate,
        "repair_has_causal_support": repair_has_causal_support,
        "another_revision_cycle_justified": True,
        "comparison_basis": "executed deterministic counterfactual ablation; not human data",
        "summary": (
            "The selected repair has diagnostic value, but executed ablations still leave "
            "rival pressure and embodiment/overexplanation tradeoffs unresolved."
        ),
        "rationale": (
            "Revert, embodiment-preserving, and record-label compression variants are "
            "actual text transformations. No-op, mismatch, and planned-only controls are "
            "kept out of countable evidence."
        ),
        "internal_comparison_summary": internal_comparison["summary"],
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_comparison_consistency_report(
    *,
    variant_set: dict[str, Any],
    internal_comparison: dict[str, Any],
    old_new_comparison: dict[str, Any],
    fixture_only: bool,
) -> dict[str, Any]:
    contradictions = []
    rationale = " ".join(
        str(old_new_comparison.get(key, ""))
        for key in ("summary", "rationale", "comparison_basis")
    ).lower()
    if (
        old_new_comparison.get("strongest_rival_still_beats_candidate") is False
        and "rival still beats" in rationale
    ):
        contradictions.append(
            "boolean says rival no longer beats candidate, but rationale says rival still beats"
        )
    if (
        old_new_comparison.get("another_revision_cycle_justified") is False
        and "cycle" in rationale
    ):
        contradictions.append(
            "boolean says another cycle is not needed, but rationale references another cycle"
        )
    if (
        old_new_comparison.get("repair_has_causal_support") is True
        and old_new_comparison.get("revert_performs_same_or_better") is True
    ):
        contradictions.append(
            "comparison says repair helped, but revert performs the same or better"
        )
    for variant in variant_set["variants"]:
        if variant["evidence_countable"] and not variant["operation_matches_actual_change"]:
            contradictions.append(
                f"{variant['variant_id']} is counted despite operation mismatch"
            )
        if variant["evidence_countable"] and variant["planned_only"]:
            contradictions.append(
                f"{variant['variant_id']} is counted despite planned-only status"
            )
    comparison_rows = internal_comparison.get("comparison_rows", [])
    for row in comparison_rows:
        if row.get("evidence_countable") and row.get("planned_only"):
            contradictions.append(
                f"{row.get('variant_id')} internal row counts planned-only evidence"
            )
    consistency_passed = not contradictions
    return {
        "worker": "comparison_consistency_report_v1_controller",
        "comparison_internal_consistency": consistency_passed,
        "contradictions": contradictions,
        "contradiction_count": len(contradictions),
        "contradictory_verdicts_count_as_gate_evidence": False,
        "countable_as_gate_evidence": consistency_passed,
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
    }


def _build_causal_effect_report(
    *,
    subject: ExecutedAblationSubject,
    variant_set: dict[str, Any],
    old_new_comparison: dict[str, Any],
    consistency_report: dict[str, Any],
    fixture_only: bool,
) -> dict[str, Any]:
    if not consistency_report["comparison_internal_consistency"]:
        status = "ambiguous"
        next_action = "repair comparison contradictions before using evidence"
    elif old_new_comparison["repair_has_causal_support"]:
        status = "useful_but_insufficient"
        next_action = "preserve useful local repair and run a separate revision cycle for remaining blockers"
    elif old_new_comparison["revert_performs_same_or_better"]:
        status = "noncausal_or_cosmetic"
        next_action = "consider reverting the patch or attacking a different causal handle"
    else:
        status = "ambiguous"
        next_action = "collect stronger internal counterfactual evidence before another claim"
    return {
        "worker": "ablation_causal_effect_report_v1",
        "selected_repair_causal_status": status,
        "selected_repair_appears_causal": status == "useful_but_insufficient",
        "evidence_supporting": [
            variant["variant_id"]
            for variant in variant_set["variants"]
            if variant["evidence_countable"]
        ],
        "evidence_weakening": [
            variant["variant_id"]
            for variant in variant_set["variants"]
            if variant["operation_id"]
            in {"operation_no_op_control", "operation_mismatch_control", "operation_planned_probe_only"}
        ],
        "reduced_overexplanation": bool(old_new_comparison["revised_improves_over_original"]),
        "damaged_local_embodiment": bool(
            old_new_comparison["embodiment_preserving_variant_beats_current"]
        ),
        "strongest_rival_pressure_remains_blocking": bool(
            old_new_comparison["strongest_rival_still_beats_candidate"]
        ),
        "recommended_next_action": next_action,
        "allowed_verdicts": [
            "repair appears cosmetic",
            "repair helped locally but hurt embodiment",
            "repair is useful but insufficient",
            "repair should be reverted",
            "repair should be preserved and cycle 2 should attack another blocker",
            "evidence is inconclusive",
        ],
        "does_not_create_main_candidate": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "fixture_only": fixture_only,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "source_revision_packet_id": subject.revision_packet_id,
    }


def _build_gate_report(
    *,
    subject: ExecutedAblationSubject,
    variant_set: dict[str, Any],
    execution_report: dict[str, Any],
    consistency_report: dict[str, Any],
    causal_effect_report: dict[str, Any],
    fixture_only: bool,
) -> dict[str, Any]:
    actual_evidence_exists = bool(execution_report["countable_evidence_variant_count"])
    consistency_passed = bool(consistency_report["comparison_internal_consistency"])
    unresolved = [
        "executed ablation is diagnostic only, not finalization evidence",
        "operator approval is absent",
    ]
    if fixture_only:
        unresolved.append("fake executed ablation mode is fixture-only")
    if causal_effect_report["strongest_rival_pressure_remains_blocking"]:
        unresolved.append("strongest-rival pressure remains blocking")
    if causal_effect_report["selected_repair_causal_status"] != "useful_but_insufficient":
        unresolved.append("selected repair causality remains ambiguous or weak")
    gate_results = [
        _gate_result("executed_ablation_packet_exists", True),
        _gate_result(
            "actual_executed_ablation_evidence_exists",
            actual_evidence_exists,
            [] if actual_evidence_exists else ["no countable executed ablation evidence"],
        ),
        _gate_result("actual_ablation_comparison_exists", True),
        _gate_result(
            "comparison_internal_consistency",
            consistency_passed,
            list(consistency_report["contradictions"]),
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
        "worker": "executed_ablation_gate_report_v1_controller",
        "profile": "autonomous_creative_candidate",
        "passed": False,
        "eligible": False,
        "actual_executed_ablation_evidence_exists": actual_evidence_exists,
        "actual_ablation_comparison_exists": True,
        "countable_evidence_variant_count": execution_report[
            "countable_evidence_variant_count"
        ],
        "planned_only_variant_count": execution_report["planned_only_variant_count"],
        "no_op_variant_count": execution_report["no_op_variant_count"],
        "operation_mismatch_variant_count": execution_report[
            "operation_mismatch_variant_count"
        ],
        "comparison_internal_consistency": consistency_passed,
        "unresolved_blockers": unresolved,
        "rival_remains_blocking": causal_effect_report[
            "strongest_rival_pressure_remains_blocking"
        ],
        "operator_approval_absent": True,
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
            "Executed ablation created diagnostic counterfactual evidence, but gates "
            "remain fail-closed and the artifact is not final."
        ),
        "source_revision_packet_id": subject.revision_packet_id,
    }


def _build_packet_summary(
    *,
    subject: ExecutedAblationSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    client_name: str,
    model: str | None,
    model_results: list[ModelDriverResult],
    fixture_only: bool,
) -> dict[str, Any]:
    return {
        "worker": "executed_ablation_packet_v1",
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_revision_packet_id": subject.revision_packet_id,
        "source_revision_packet_dir": str(subject.revision_packet_dir),
        "client": client_name,
        "model": model,
        "artifact_types": list(EXECUTED_ABLATION_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "executed_ablation_artifacts": len(artifacts),
            "required_executed_ablation_artifacts": len(EXECUTED_ABLATION_ARTIFACT_TYPES),
            "actual_variant_count": payloads["ablation_execution_report"][
                "actual_variant_count"
            ],
            "countable_evidence_variant_count": payloads["ablation_execution_report"][
                "countable_evidence_variant_count"
            ],
            "model_calls": len(model_results),
        },
        "selected_repair_causal_status": payloads["ablation_causal_effect_report"][
            "selected_repair_causal_status"
        ],
        "comparison_internal_consistency": payloads["comparison_consistency_report"][
            "comparison_internal_consistency"
        ],
        "gate_report": payloads["executed_ablation_gate_report"],
        "model_call_ids": [result.model_call.id for result in model_results],
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
        "not_human_data": True,
    }


def _load_subject(connection, revision_packet_dir: Path) -> ExecutedAblationSubject:
    packet_envelope = read_json_file(revision_packet_dir / "autonomous_closed_loop_packet.json")
    if packet_envelope.get("artifact_type") != "autonomous_closed_loop_packet":
        raise ValueError(
            "revision packet must contain autonomous_closed_loop_packet.json"
        )
    packet_payload = packet_envelope["payload"]
    if not isinstance(packet_payload, dict):
        raise ValueError("autonomous revision packet payload is not an object")
    run_id = str(packet_envelope["run_id"])
    revision_packet_id = str(packet_payload.get("packet_id", revision_packet_dir.name))
    source_packet_dir = Path(str(packet_payload["source_packet_dir"])).resolve()
    source_packet_id = str(packet_payload["source_packet_id"])
    artifact_ids = dict(packet_payload["artifact_ids"])

    required = (
        "autonomous_revision_subject_manifest",
        "selected_failure_diagnosis",
        "autonomous_revision_work_order",
        "causal_handle_selection",
        "revision_patch_proposal",
        "revised_candidate_text",
        "revision_diff_report",
        "ablation_variant_set",
        "ablation_reread_comparison",
        "old_new_rival_comparison",
        "local_law_case_note",
        "autonomous_closed_loop_gate_report",
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
        artifact_path=revision_packet_dir / "autonomous_closed_loop_packet.json",
    )
    if packet_artifact is not None:
        artifacts["autonomous_closed_loop_packet"] = packet_artifact
        payloads["autonomous_closed_loop_packet"] = packet_payload
    source_texts = _load_source_texts(source_packet_dir)
    if not any(text.source_class == "abi_candidate" for text in source_texts):
        raise ValueError("source packet does not include an Abi candidate text")
    return ExecutedAblationSubject(
        run_id=run_id,
        revision_packet_dir=revision_packet_dir,
        revision_packet_id=revision_packet_id,
        revision_packet_artifact_id=packet_artifact.id if packet_artifact is not None else None,
        source_packet_dir=source_packet_dir,
        source_packet_id=source_packet_id,
        revision_artifacts=artifacts,
        revision_payloads=payloads,
        source_texts=tuple(source_texts),
    )


def _artifact_from_packet(
    connection,
    artifact_ids: dict[str, object],
    artifact_type: str,
) -> ArtifactRecord:
    artifact_id = artifact_ids.get(artifact_type)
    if artifact_id is None:
        raise ValueError(f"revision packet is missing artifact ID for {artifact_type}")
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


def _source_spans_from_revised_text(text: str) -> list[dict[str, Any]]:
    spans = []
    opening = "The table is still there in the morning."
    if opening in text:
        start = text.index(opening)
        spans.append(
            {
                "source_span_id": "source_span_opening_sentence",
                "char_start": start,
                "char_end": start + len(opening),
                "exact_text": opening,
                "selection_basis": "opening sentence",
            }
        )
    for index, sentence in enumerate(_sentences(text), start=1):
        lowered = sentence.lower()
        if any(term in lowered for term in ("record", "law", "proof", "explain")):
            start = text.find(sentence)
            spans.append(
                {
                    "source_span_id": f"source_span_record_law_proof_{len(spans):03d}",
                    "char_start": start,
                    "char_end": start + len(sentence),
                    "exact_text": sentence,
                    "sentence_index": index,
                    "selection_basis": "record/law/proof language",
                }
            )
    return spans


def _embodiment_preserving_text(text: str) -> str:
    replacements = (
        ("The legs are plain.", "The legs are steady."),
        ("A spoon lies beside", "A spoon lies on its side beside"),
        ("almost weather.", "a small engine of weather."),
    )
    result = text
    for before, after in replacements:
        result = result.replace(before, after, 1)
    if result == text and text.strip():
        result = text.rstrip() + " The spoon keeps its dull edge in the light."
    return result


def _variant_summary(variant: dict[str, Any]) -> str:
    if variant["planned_only"]:
        return "Planned-only probe; it cannot count as executed counterfactual evidence."
    if variant["no_op"]:
        return "No-op diagnostic; no text change was executed."
    if not variant["operation_matches_actual_change"]:
        return "Operation mismatch diagnostic; the actual change does not match the claimed operation."
    if variant["operation_id"] == "operation_revert_applied_patch":
        return "Revert variant tests whether the controller repair carried causal weight."
    if variant["operation_id"] == "operation_embodiment_preserving_repair":
        return "Embodiment-preserving variant tests whether detail was overcut."
    if variant["operation_id"] == "operation_record_label_compression":
        return "Record-label compression tests whether interpretive labels are the stronger handle."
    return "Executed diagnostic variant."


def _variant_effect_estimate(variant: dict[str, Any]) -> str:
    mapping = {
        "operation_revert_applied_patch": "likely restores some opening thesis pressure",
        "operation_embodiment_preserving_repair": "may improve local embodiment without restoring explicit framing",
        "operation_record_label_compression": "may improve discovery by delaying labels",
        "operation_no_op_control": "no reliable effect",
        "operation_mismatch_control": "unreliable effect due to operation mismatch",
        "operation_planned_probe_only": "speculative only",
    }
    return mapping.get(str(variant["operation_id"]), "uncertain internal effect")


def _variant_risk_notes(variant: dict[str, Any]) -> str:
    if not variant["evidence_countable"]:
        return "Not countable as executed causal evidence."
    if variant["operation_id"] == "operation_embodiment_preserving_repair":
        return "May preserve detail but also restore decorative excess."
    if variant["operation_id"] == "operation_record_label_compression":
        return "May improve discovery while leaving deeper abstraction untouched."
    return "Internal estimate only; no human reader evidence."


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


def _total_score(score: dict[str, int]) -> int:
    return int(score["local_embodiment_score"]) + int(score["discovery_score"]) - int(
        score["overexplanation_score"]
    )


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


def _subject_parent_ids(subject: ExecutedAblationSubject) -> list[str]:
    ids = [artifact.id for artifact in subject.revision_artifacts.values()]
    return sorted(set(ids))


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
    subject: ExecutedAblationSubject,
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
        "revision_packet_dir": str(subject.revision_packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "required_artifact_types": list(EXECUTED_ABLATION_ARTIFACT_TYPES),
        "counts": {
            "executed_ablation_artifacts": len(artifacts),
            "required_executed_ablation_artifacts": len(EXECUTED_ABLATION_ARTIFACT_TYPES),
            "model_calls": len(model_results),
            "countable_evidence_variant_count": (
                payloads.get("ablation_execution_report", {}).get(
                    "countable_evidence_variant_count",
                    0,
                )
            ),
        },
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "gate_report": payloads.get("executed_ablation_gate_report"),
        "message": message,
    }


def _failure_result(
    *,
    client_name: str,
    model: str | None,
    subject: ExecutedAblationSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    model_results: list[ModelDriverResult],
    message: str,
) -> ExecutedAblationResult:
    return ExecutedAblationResult(
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


def _refusal(
    *,
    client_name: str,
    model: str | None,
    revision_packet: Path | str,
    message: str,
) -> ExecutedAblationResult:
    return ExecutedAblationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "revision_packet": str(revision_packet),
            "artifact_ids": {},
            "artifact_paths": {},
            "counts": {"model_calls": 0},
            "message": message,
        },
    )


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (config.root / path).resolve()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _words(text: str) -> list[str]:
    return [word.strip(".,;:!?()[]{}\"'").lower() for word in text.split() if word.strip()]


def _sentences(text: str) -> list[str]:
    normalized = text.replace("\n", " ")
    sentences = []
    start = 0
    for index, char in enumerate(normalized):
        if char in ".!?":
            sentence = normalized[start : index + 1].strip()
            if sentence:
                sentences.append(sentence)
            start = index + 1
    tail = normalized[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences
