"""Autonomous closed-loop revision v1 deterministic packet."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
from typing import Any

from abi.artifacts import ArtifactRecord, get_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.policy import AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES
from abi.controller.state import (
    AUTONOMOUS_CLOSED_LOOP_REVISION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_driver import ModelClient, ModelClientError, ModelDriver, ModelDriverResult
from abi.model_driver import WorkerRequest
from abi.model_schemas import (
    AUTONOMOUS_REVISION_ABLATION_EVIDENCE_BASIS,
    AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA,
    AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA,
    AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA,
    AUTONOMOUS_REVISION_JUDGMENT_KEYS,
    AUTONOMOUS_REVISION_LOCAL_LAW_CASE_NOTE_SCHEMA,
    AUTONOMOUS_REVISION_MODEL_SCHEMAS,
    AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS,
    AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA,
    AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA,
    ModelValidationError,
    WorkerRole,
    WorkerSchema,
)
from abi.modules.internal_reader_lab import INTERNAL_READER_LAB_ARTIFACT_TYPES
from abi.packets import PacketWriter, create_packet_dir, read_json_file


@dataclass(frozen=True)
class AutonomousRevisionWorkerSpec:
    schema: WorkerSchema
    worker_role: WorkerRole
    prompt_contract_id: str
    parent_artifact_types: tuple[str, ...] = ()

    @property
    def artifact_type(self) -> str:
        return self.schema.artifact_type


AUTONOMOUS_REVISION_LINEAGE_ID = "autonomous_closed_loop_revision_v1"
AUTONOMOUS_REVISION_CLIENT_FAKE = "fake"
AUTONOMOUS_REVISION_CLIENT_OPENAI = "openai"
AUTONOMOUS_REVISION_CLIENTS = (
    AUTONOMOUS_REVISION_CLIENT_FAKE,
    AUTONOMOUS_REVISION_CLIENT_OPENAI,
)
AUTONOMOUS_REVISION_MAX_MODEL_CALLS_DEFAULT = 12
AUTONOMOUS_REVISION_ARTIFACT_TYPES = (
    "autonomous_revision_subject_manifest",
    "selected_failure_diagnosis",
    "causal_handle_selection",
    "revision_patch_proposal",
    "revised_candidate_text",
    "revision_diff_report",
    "ablation_variant_set",
    "ablation_reread_comparison",
    "old_new_rival_comparison",
    "local_law_case_note",
    "autonomous_closed_loop_gate_report",
    "autonomous_closed_loop_packet",
)
AUTONOMOUS_REVISION_PROMPT_CONTRACT_PREFIX = "autonomous.revision"
AUTONOMOUS_REVISION_FAKE_MODEL_PROVIDER = "fake"
AUTONOMOUS_REVISION_FAKE_MODEL = "fake-autonomous-closed-loop-revision-v1"
AUTONOMOUS_REVISION_WORKERS = (
    AutonomousRevisionWorkerSpec(
        schema=AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA,
        worker_role=WorkerRole.AUTONOMOUS_REVISION_FAILURE_SELECTOR,
        prompt_contract_id=f"{AUTONOMOUS_REVISION_PROMPT_CONTRACT_PREFIX}.failure_selector.v1",
    ),
    AutonomousRevisionWorkerSpec(
        schema=AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA,
        worker_role=WorkerRole.AUTONOMOUS_REVISION_CAUSAL_HANDLE_SELECTOR,
        prompt_contract_id=f"{AUTONOMOUS_REVISION_PROMPT_CONTRACT_PREFIX}.causal_handle.v1",
        parent_artifact_types=(AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA.artifact_type,),
    ),
    AutonomousRevisionWorkerSpec(
        schema=AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA,
        worker_role=WorkerRole.AUTONOMOUS_REVISION_CANDIDATE_REVISER,
        prompt_contract_id=f"{AUTONOMOUS_REVISION_PROMPT_CONTRACT_PREFIX}.patch_reviser.v1",
        parent_artifact_types=(AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type,),
    ),
    AutonomousRevisionWorkerSpec(
        schema=AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA,
        worker_role=WorkerRole.AUTONOMOUS_REVISION_ABLATION_VARIANT_BUILDER,
        prompt_contract_id=f"{AUTONOMOUS_REVISION_PROMPT_CONTRACT_PREFIX}.ablation_variants.v1",
        parent_artifact_types=(
            AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type,
            "revised_candidate_text",
        ),
    ),
    AutonomousRevisionWorkerSpec(
        schema=AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
        worker_role=WorkerRole.AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARATOR,
        prompt_contract_id=f"{AUTONOMOUS_REVISION_PROMPT_CONTRACT_PREFIX}.ablation_comparison.v1",
        parent_artifact_types=(AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA.artifact_type,),
    ),
    AutonomousRevisionWorkerSpec(
        schema=AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA,
        worker_role=WorkerRole.AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARATOR,
        prompt_contract_id=f"{AUTONOMOUS_REVISION_PROMPT_CONTRACT_PREFIX}.old_new_rival.v1",
        parent_artifact_types=(
            "revised_candidate_text",
            AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA.artifact_type,
            AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA.artifact_type,
        ),
    ),
    AutonomousRevisionWorkerSpec(
        schema=AUTONOMOUS_REVISION_LOCAL_LAW_CASE_NOTE_SCHEMA,
        worker_role=WorkerRole.AUTONOMOUS_REVISION_LOCAL_LAW_REPORTER,
        prompt_contract_id=f"{AUTONOMOUS_REVISION_PROMPT_CONTRACT_PREFIX}.local_law_case.v1",
        parent_artifact_types=(
            AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type,
            AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA.artifact_type,
        ),
    ),
)


@dataclass(frozen=True)
class AutonomousRevisionResult:
    exit_code: int
    payload: dict[str, object]
    gate_records: tuple[GateRecord, ...] = ()
    model_results: tuple[ModelDriverResult, ...] = ()


class RevisionIntegrityError(ValueError):
    """Raised when cross-artifact revision evidence is internally inconsistent."""


@dataclass(frozen=True)
class SubjectText:
    label: str
    source_class: str
    artifact_id: str
    text: str

    @property
    def word_count(self) -> int:
        return len(_words(self.text))


@dataclass(frozen=True)
class RevisionSubject:
    run_id: str
    reader_lab_packet_dir: Path
    reader_lab_packet_id: str
    reader_lab_packet_artifact_id: str | None
    source_packet_dir: Path
    source_packet_id: str
    lab_artifacts: dict[str, ArtifactRecord]
    lab_payloads: dict[str, dict[str, Any]]
    source_texts: tuple[SubjectText, ...]

    @property
    def candidate_text(self) -> SubjectText:
        return self.text_by_source_class("abi_candidate")

    @property
    def baselines(self) -> tuple[SubjectText, ...]:
        return tuple(
            text
            for text in self.source_texts
            if text.source_class in {"direct_prompt_baseline", "raw_model_baseline"}
        )

    @property
    def strongest_rival(self) -> SubjectText | None:
        for text in self.source_texts:
            if text.source_class == "strongest_rival":
                return text
        return None

    def text_by_source_class(self, source_class: str) -> SubjectText:
        for text in self.source_texts:
            if text.source_class == source_class:
                return text
        raise KeyError(source_class)


def run_autonomous_revision(
    config: AbiConfig,
    *,
    client_name: str,
    reader_lab_packet: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = AUTONOMOUS_REVISION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    fake_mode: str = "valid",
    fake_target_schema: WorkerSchema = AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> AutonomousRevisionResult:
    if client_name not in AUTONOMOUS_REVISION_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            reader_lab_packet=reader_lab_packet,
            message=f"Autonomous revision client is not available: {client_name}",
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < 0:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            reader_lab_packet=reader_lab_packet,
            message="Autonomous revision refused; max-model-calls must be non-negative.",
        )

    planned_model_calls = len(AUTONOMOUS_REVISION_WORKERS)
    if client_name == AUTONOMOUS_REVISION_CLIENT_OPENAI and max_model_calls < planned_model_calls:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            reader_lab_packet=reader_lab_packet,
            message=(
                "Autonomous revision refused; max-model-calls "
                f"{max_model_calls} is below required budget {planned_model_calls}."
            ),
        )

    if client_name == AUTONOMOUS_REVISION_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            reader_lab_packet=reader_lab_packet,
            message=(
                "Autonomous revision refused; pass --allow-live-model "
                "to opt in explicitly."
            ),
        )

    resolved_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == AUTONOMOUS_REVISION_CLIENT_OPENAI and not resolved_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            reader_lab_packet=reader_lab_packet,
            message=f"Autonomous revision refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    reader_lab_packet_dir = _resolve_path(config, reader_lab_packet)
    if not reader_lab_packet_dir.exists() or not reader_lab_packet_dir.is_dir():
        return _refusal(
            client_name=client_name,
            model=configured_model,
            reader_lab_packet=reader_lab_packet_dir,
            message=(
                "Autonomous revision refused; reader-lab packet directory not found: "
                f"{reader_lab_packet_dir}"
            ),
        )

    initialize_database(config)
    try:
        with connect(config.db_path) as connection:
            subject = _load_revision_subject(connection, reader_lab_packet_dir)
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    client_name=client_name,
                    model=configured_model,
                    reader_lab_packet=reader_lab_packet_dir,
                    message=(
                        "Autonomous revision refused; reader-lab run is not registered: "
                        f"{subject.run_id}"
                    ),
                )
            output_dir = create_packet_dir(config.run_dir(subject.run_id) / "autonomous_revision")
            set_active_phase(
                connection,
                subject.run_id,
                AUTONOMOUS_CLOSED_LOOP_REVISION_ACTIVE_PHASE,
            )

        if client_name == AUTONOMOUS_REVISION_CLIENT_OPENAI:
            factory = client_factory or _default_openai_client_factory
            return _run_live_autonomous_revision(
                config=config,
                subject=subject,
                output_dir=output_dir,
                client_name=client_name,
                model=configured_model,
                model_client=factory(configured_model),
                max_model_calls=max_model_calls,
                fixture_only=False,
                fake_mode=fake_mode,
                fake_target_schema=fake_target_schema,
            )

        with connect(config.db_path) as connection:
            artifacts, payloads = _write_fake_revision_packet(
                connection=connection,
                subject=subject,
                output_dir=output_dir,
            )
            gate_records = _record_revision_gates(
                connection=connection,
                run_id=subject.run_id,
                gate_report=payloads["autonomous_closed_loop_gate_report"],
            )
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            reader_lab_packet=reader_lab_packet_dir,
            message=f"Autonomous revision refused; invalid reader-lab packet: {error}",
        )

    return AutonomousRevisionResult(
        exit_code=0,
        payload=_summary_payload(
            run_id=subject.run_id,
            packet_dir=output_dir,
            reader_lab_packet_dir=reader_lab_packet_dir,
            client_name=client_name,
            artifacts=artifacts,
            payloads=payloads,
            gate_records=gate_records,
            accepted=True,
            message=None,
        ),
        gate_records=tuple(gate_records),
    )


def _write_fake_revision_packet(
    *,
    connection,
    subject: RevisionSubject,
    output_dir: Path,
) -> tuple[dict[str, ArtifactRecord], dict[str, dict[str, Any]]]:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}
    writer = PacketWriter(
        connection=connection,
        run_id=subject.run_id,
        packet_dir=output_dir,
        lineage_id=AUTONOMOUS_REVISION_LINEAGE_ID,
        created_by="autonomous_closed_loop_revision_v1_fake",
        fixture_only=True,
        model_call_id=None,
    )

    payloads["autonomous_revision_subject_manifest"] = _build_subject_manifest(subject)
    artifacts["autonomous_revision_subject_manifest"] = writer.write_artifact(
        "autonomous_revision_subject_manifest",
        payloads["autonomous_revision_subject_manifest"],
        parent_ids=_subject_parent_ids(subject),
    )

    payloads["selected_failure_diagnosis"] = _build_selected_failure(subject)
    artifacts["selected_failure_diagnosis"] = writer.write_artifact(
        "selected_failure_diagnosis",
        payloads["selected_failure_diagnosis"],
        parent_ids=[
            artifacts["autonomous_revision_subject_manifest"].id,
            subject.lab_artifacts["internal_failure_diagnosis"].id,
        ],
    )

    payloads["causal_handle_selection"] = _build_causal_handle_selection(
        subject,
        payloads["selected_failure_diagnosis"],
    )
    artifacts["causal_handle_selection"] = writer.write_artifact(
        "causal_handle_selection",
        payloads["causal_handle_selection"],
        parent_ids=[
            artifacts["selected_failure_diagnosis"].id,
            subject.lab_artifacts["targeted_recomposition_plan"].id,
            subject.lab_artifacts["hostile_reader_report"].id,
        ],
    )

    payloads["revision_patch_proposal"] = _build_revision_patch_proposal(
        subject,
        payloads["causal_handle_selection"],
    )
    artifacts["revision_patch_proposal"] = writer.write_artifact(
        "revision_patch_proposal",
        payloads["revision_patch_proposal"],
        parent_ids=[
            artifacts["causal_handle_selection"].id,
            subject.candidate_text.artifact_id,
        ],
    )

    controller_payloads = _build_controller_revision_from_patches(
        subject,
        payloads["causal_handle_selection"],
        payloads["revision_patch_proposal"],
        fixture_only=True,
    )
    payloads["revised_candidate_text"] = controller_payloads["revised_candidate_text"]
    artifacts["revised_candidate_text"] = writer.write_artifact(
        "revised_candidate_text",
        payloads["revised_candidate_text"],
        parent_ids=[
            artifacts["revision_patch_proposal"].id,
            artifacts["causal_handle_selection"].id,
            subject.candidate_text.artifact_id,
        ],
    )

    payloads["revision_diff_report"] = controller_payloads["revision_diff_report"]
    artifacts["revision_diff_report"] = writer.write_artifact(
        "revision_diff_report",
        payloads["revision_diff_report"],
        parent_ids=[
            artifacts["revision_patch_proposal"].id,
            artifacts["causal_handle_selection"].id,
            artifacts["revised_candidate_text"].id,
        ],
    )

    payloads["ablation_variant_set"] = _build_ablation_variant_set(
        subject,
        payloads["causal_handle_selection"],
        payloads["revised_candidate_text"],
    )
    artifacts["ablation_variant_set"] = writer.write_artifact(
        "ablation_variant_set",
        payloads["ablation_variant_set"],
        parent_ids=[
            artifacts["causal_handle_selection"].id,
            artifacts["revised_candidate_text"].id,
            subject.lab_artifacts["counterfactual_ablation_plan"].id,
        ],
    )

    payloads["ablation_reread_comparison"] = _build_ablation_comparison(
        subject,
        payloads["ablation_variant_set"],
    )
    artifacts["ablation_reread_comparison"] = writer.write_artifact(
        "ablation_reread_comparison",
        payloads["ablation_reread_comparison"],
        parent_ids=[
            artifacts["ablation_variant_set"].id,
            subject.lab_artifacts["internal_reread_reader_trace"].id,
        ],
    )

    payloads["old_new_rival_comparison"] = _build_old_new_rival_comparison(
        subject,
        payloads["revised_candidate_text"],
        payloads["ablation_reread_comparison"],
        artifacts["revised_candidate_text"].id,
    )
    artifacts["old_new_rival_comparison"] = writer.write_artifact(
        "old_new_rival_comparison",
        payloads["old_new_rival_comparison"],
        parent_ids=[
            artifacts["revised_candidate_text"].id,
            artifacts["revision_diff_report"].id,
            subject.lab_artifacts["internal_rival_comparison"].id,
        ],
    )

    payloads["local_law_case_note"] = _build_local_law_case_note(
        payloads["causal_handle_selection"],
        payloads["old_new_rival_comparison"],
    )
    artifacts["local_law_case_note"] = writer.write_artifact(
        "local_law_case_note",
        payloads["local_law_case_note"],
        parent_ids=[
            artifacts["causal_handle_selection"].id,
            artifacts["old_new_rival_comparison"].id,
        ],
    )
    integrity_report = _validate_revision_integrity(subject, payloads)
    payloads["_integrity_report"] = integrity_report

    payloads["autonomous_closed_loop_gate_report"] = _build_closed_loop_gate_report(
        subject=subject,
        payloads=payloads,
        integrity_report=integrity_report,
    )
    artifacts["autonomous_closed_loop_gate_report"] = writer.write_artifact(
        "autonomous_closed_loop_gate_report",
        payloads["autonomous_closed_loop_gate_report"],
        parent_ids=[
            artifacts["selected_failure_diagnosis"].id,
            artifacts["causal_handle_selection"].id,
            artifacts["revised_candidate_text"].id,
            artifacts["revision_diff_report"].id,
            artifacts["ablation_variant_set"].id,
            artifacts["ablation_reread_comparison"].id,
            artifacts["old_new_rival_comparison"].id,
            artifacts["local_law_case_note"].id,
        ],
    )

    payloads["autonomous_closed_loop_packet"] = _build_packet_summary(
        subject=subject,
        packet_dir=output_dir,
        artifacts=artifacts,
        payloads=payloads,
        integrity_report=integrity_report,
    )
    artifacts["autonomous_closed_loop_packet"] = writer.write_artifact(
        "autonomous_closed_loop_packet",
        payloads["autonomous_closed_loop_packet"],
        parent_ids=[
            artifacts[artifact_type].id
            for artifact_type in AUTONOMOUS_REVISION_ARTIFACT_TYPES[:-1]
        ],
    )
    return artifacts, payloads


class FakeAutonomousRevisionModelClient:
    def __init__(
        self,
        *,
        provider: str = AUTONOMOUS_REVISION_FAKE_MODEL_PROVIDER,
        model: str = AUTONOMOUS_REVISION_FAKE_MODEL,
        mode: str = "valid",
        target_schema: WorkerSchema = AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA,
    ) -> None:
        self.provider = provider
        self.model = model
        self.mode = mode
        self.target_schema = target_schema
        self.payloads: dict[str, dict[str, Any]] = {}
        self.requests: list[WorkerRequest] = []

    def generate(self, request: WorkerRequest) -> str:
        self.requests.append(request)
        if request.schema == self.target_schema and self.mode == "invalid":
            return "{not valid json"
        if request.schema == self.target_schema and self.mode == "malformed":
            return _canonical_json({"not_human_data": True})
        if request.schema == self.target_schema and self.mode == "failure":
            raise ModelClientError("simulated autonomous revision client failure")
        if self.mode not in ("valid", "invalid", "malformed", "failure"):
            raise ModelClientError(f"unknown autonomous revision fake mode: {self.mode}")

        prompt = json.loads(request.input_text)
        payload = _fake_model_payload_for_revision_schema(
            request.schema,
            prompt,
            self.payloads,
        )
        self.payloads[request.schema.artifact_type] = payload
        return _canonical_json(payload)


def _run_live_autonomous_revision(
    *,
    config: AbiConfig,
    subject: RevisionSubject,
    output_dir: Path,
    client_name: str,
    model: str,
    model_client: ModelClient,
    max_model_calls: int,
    fixture_only: bool,
    fake_mode: str,
    fake_target_schema: WorkerSchema,
) -> AutonomousRevisionResult:
    _ = fake_mode, fake_target_schema
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}
    model_results: list[ModelDriverResult] = []

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=AUTONOMOUS_REVISION_LINEAGE_ID,
            created_by="autonomous_closed_loop_revision_v1_model_driver",
            fixture_only=fixture_only,
            model_call_id=None,
        )
        payloads["autonomous_revision_subject_manifest"] = _build_subject_manifest(
            subject,
            fixture_only=fixture_only,
        )
        payloads["autonomous_revision_subject_manifest"].update(
            {
                "worker": "autonomous_revision_subject_manifest_v1_model_driver",
                "model_driver_backed": True,
            }
        )
        artifacts["autonomous_revision_subject_manifest"] = writer.write_artifact(
            "autonomous_revision_subject_manifest",
            payloads["autonomous_revision_subject_manifest"],
            parent_ids=_subject_parent_ids(subject),
        )

    driver = ModelDriver(config=config, client=model_client)
    for index, worker in enumerate(AUTONOMOUS_REVISION_WORKERS, start=1):
        if index > max_model_calls:
            return _live_failure_result(
                client_name=client_name,
                model=model,
                subject=subject,
                packet_dir=output_dir,
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
                message="Autonomous revision stopped by max-model-calls budget.",
            )

        parent_ids = _parent_ids_for_revision_worker(subject, artifacts, worker)
        result = driver.run(
            WorkerRequest(
                run_id=subject.run_id,
                worker_role=worker.worker_role,
                prompt_contract_id=worker.prompt_contract_id,
                schema=worker.schema,
                input_text=_prompt_for_revision_worker(subject, worker, payloads, artifacts),
                input_artifact_ids=parent_ids,
                input_packet_path=str(subject.reader_lab_packet_dir),
                lineage_id=AUTONOMOUS_REVISION_LINEAGE_ID,
                parent_ids=parent_ids,
                fixture_only=fixture_only,
                output_dir=str(output_dir),
                parsed_payload_validator=_validator_for_revision_worker(
                    subject,
                    worker,
                    payloads,
                ),
            )
        )
        model_results.append(result)
        if not result.accepted or result.parsed_payload is None or result.parsed_artifact is None:
            details = (
                f": {result.model_call.error_message}"
                if result.model_call.error_message
                else "."
            )
            return _live_failure_result(
                client_name=client_name,
                model=model,
                subject=subject,
                packet_dir=output_dir,
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
                message="Autonomous revision stopped by model-call failure" + details,
            )
        artifacts[worker.artifact_type] = result.parsed_artifact
        payloads[worker.artifact_type] = result.parsed_payload
        if worker.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            try:
                controller_payloads = _build_controller_revision_from_patches(
                    subject,
                    payloads[AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type],
                    result.parsed_payload,
                    fixture_only=fixture_only,
                )
            except RevisionIntegrityError as error:
                return _live_failure_result(
                    client_name=client_name,
                    model=model,
                    subject=subject,
                    packet_dir=output_dir,
                    artifacts=artifacts,
                    payloads=payloads,
                    model_results=model_results,
                    message=(
                        "Autonomous revision stopped by controller patch validation "
                        f"failure: {error}"
                    ),
                )
            with connect(config.db_path) as connection:
                writer = PacketWriter(
                    connection=connection,
                    run_id=subject.run_id,
                    packet_dir=output_dir,
                    lineage_id=AUTONOMOUS_REVISION_LINEAGE_ID,
                    created_by="autonomous_closed_loop_revision_v1_controller",
                    fixture_only=fixture_only,
                    model_call_id=None,
                )
                payloads["revised_candidate_text"] = controller_payloads[
                    "revised_candidate_text"
                ]
                artifacts["revised_candidate_text"] = writer.write_artifact(
                    "revised_candidate_text",
                    payloads["revised_candidate_text"],
                    parent_ids=[
                        artifacts[AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA.artifact_type].id,
                        artifacts[AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type].id,
                        subject.candidate_text.artifact_id,
                    ],
                )
                payloads["revision_diff_report"] = controller_payloads[
                    "revision_diff_report"
                ]
                artifacts["revision_diff_report"] = writer.write_artifact(
                    "revision_diff_report",
                    payloads["revision_diff_report"],
                    parent_ids=[
                        artifacts[AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA.artifact_type].id,
                        artifacts["revised_candidate_text"].id,
                        artifacts[AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type].id,
                    ],
                )

    try:
        integrity_report = _validate_revision_integrity(subject, payloads)
    except RevisionIntegrityError as error:
        return _live_failure_result(
            client_name=client_name,
            model=model,
            subject=subject,
            packet_dir=output_dir,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            message=f"Autonomous revision stopped by integrity validation failure: {error}",
        )
    payloads["_integrity_report"] = integrity_report

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=AUTONOMOUS_REVISION_LINEAGE_ID,
            created_by="autonomous_closed_loop_revision_v1_controller",
            fixture_only=fixture_only,
            model_call_id=None,
        )
        payloads["autonomous_closed_loop_gate_report"] = _build_closed_loop_gate_report(
            subject=subject,
            payloads=payloads,
            fixture_only=fixture_only,
            integrity_report=integrity_report,
        )
        payloads["autonomous_closed_loop_gate_report"].update(
            {
                "worker": "autonomous_closed_loop_gate_report_v1_controller",
                "model_driver_backed": True,
                "model_call_ids": [result.model_call.id for result in model_results],
            }
        )
        artifacts["autonomous_closed_loop_gate_report"] = writer.write_artifact(
            "autonomous_closed_loop_gate_report",
            payloads["autonomous_closed_loop_gate_report"],
            parent_ids=[
                artifacts[artifact_type].id
                for artifact_type in AUTONOMOUS_REVISION_ARTIFACT_TYPES[1:-2]
            ],
        )
        gate_records = _record_revision_gates(
            connection=connection,
            run_id=subject.run_id,
            gate_report=payloads["autonomous_closed_loop_gate_report"],
        )
        payloads["autonomous_closed_loop_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=output_dir,
            artifacts=artifacts,
            payloads=payloads,
            fixture_only=fixture_only,
            model_results=model_results,
            model=model,
            integrity_report=integrity_report,
        )
        payloads["autonomous_closed_loop_packet"].update(
            {
                "worker": "autonomous_closed_loop_packet_v1_model_driver",
                "model_driver_backed": True,
            }
        )
        artifacts["autonomous_closed_loop_packet"] = writer.write_artifact(
            "autonomous_closed_loop_packet",
            payloads["autonomous_closed_loop_packet"],
            parent_ids=[
                artifacts[artifact_type].id
                for artifact_type in AUTONOMOUS_REVISION_ARTIFACT_TYPES[:-1]
            ],
        )

    return AutonomousRevisionResult(
        exit_code=0,
        payload=_summary_payload(
            run_id=subject.run_id,
            packet_dir=output_dir,
            reader_lab_packet_dir=subject.reader_lab_packet_dir,
            client_name=client_name,
            artifacts=artifacts,
            payloads=payloads,
            gate_records=gate_records,
            accepted=True,
            message=None,
            model_results=model_results,
            model=model,
        ),
        gate_records=tuple(gate_records),
        model_results=tuple(model_results),
    )


def _live_failure_result(
    *,
    client_name: str,
    model: str,
    subject: RevisionSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    model_results: list[ModelDriverResult],
    message: str,
) -> AutonomousRevisionResult:
    return AutonomousRevisionResult(
        exit_code=1,
        payload=_summary_payload(
            run_id=subject.run_id,
            packet_dir=packet_dir,
            reader_lab_packet_dir=subject.reader_lab_packet_dir,
            client_name=client_name,
            artifacts=artifacts,
            payloads=payloads,
            gate_records=[],
            accepted=False,
            message=message,
            model_results=model_results,
            model=model,
        ),
        model_results=tuple(model_results),
    )


def _prompt_for_revision_worker(
    subject: RevisionSubject,
    worker: AutonomousRevisionWorkerSpec,
    payloads: dict[str, dict[str, Any]],
    artifacts: dict[str, ArtifactRecord],
) -> str:
    prompt: dict[str, Any] = {
        "prompt_contract_id": worker.prompt_contract_id,
        "worker_role": worker.worker_role.value,
        "schema_name": worker.schema.name,
        "reader_lab_packet_dir": str(subject.reader_lab_packet_dir),
        "reader_lab_packet_id": subject.reader_lab_packet_id,
        "source_packet_dir": str(subject.source_packet_dir),
        "source_packet_id": subject.source_packet_id,
        "candidate": {
            "label": subject.candidate_text.label,
            "source_class": subject.candidate_text.source_class,
            "artifact_id": subject.candidate_text.artifact_id,
            "text": subject.candidate_text.text,
        },
        "source_texts": [
            {
                "label": text.label,
                "source_class": text.source_class,
                "artifact_id": text.artifact_id,
                "text": text.text,
            }
            for text in subject.source_texts
        ],
        "strongest_rival": (
            {
                "label": subject.strongest_rival.label,
                "artifact_id": subject.strongest_rival.artifact_id,
                "text": subject.strongest_rival.text,
            }
            if subject.strongest_rival is not None
            else None
        ),
        "reader_lab_payloads": subject.lab_payloads,
        "prior_outputs": {
            artifact_type: payloads[artifact_type]
            for artifact_type in worker.parent_artifact_types
            if artifact_type in payloads
        },
        "prior_artifact_ids": {
            artifact_type: artifacts[artifact_type].id
            for artifact_type in worker.parent_artifact_types
            if artifact_type in artifacts
        },
        "bounded_revision_constraints": [
            "target selected causal handles only",
            "do not rewrite the whole artifact",
            "preserve domestic object-world and morning stillness",
            "preserve incremental patterning and quiet philosophical pressure",
            "preserve strongest-rival pressure",
            "avoid validation language, phase-shift language, Abi/meta language, and thesis rewrite",
        ],
        "not_human_data": True,
    }
    if worker.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
        selected_failure = payloads[AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA.artifact_type]
        target_contract = _controller_target_contract_for_selected_failure(
            subject,
            selected_failure,
        )
        prompt["controller_owned_patch_target_inventory"] = target_contract
        prompt["allowed_patch_targets"] = target_contract["allowed_patch_targets"]
        prompt["causal_handle_target_contract"] = (
            "Select exactly one selected_patch_target_id from allowed_patch_targets. "
            "Do not define allowed_patch_targets, do not invent patch target IDs, and "
            "do not use target_region_description as an identifier. The controller owns "
            "the target inventory and will reject any selected_patch_target_id outside it."
        )
    handle_payload = payloads.get(AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type)
    if isinstance(handle_payload, dict) and worker.schema in (
        AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA,
        AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA,
        AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA,
        AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
        AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA,
        AUTONOMOUS_REVISION_LOCAL_LAW_CASE_NOTE_SCHEMA,
    ):
        selected_target = {
            "span_ref": handle_payload["span_ref"],
            **_target_contract_from_handle(handle_payload),
        }
        prompt["selected_target_contract"] = selected_target
        prompt["allowed_patch_targets"] = selected_target["allowed_patch_targets"]
        if worker.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            prompt["selected_patch_target_id"] = handle_payload["selected_patch_target_id"]
            prompt["patchable_spans"] = handle_payload["patchable_spans"]
    if worker.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
        prompt["candidate_reviser_target_contract"] = (
            "Return patch operations only, not a full revised artifact. Each patch must "
            "choose patch_target_id exactly from allowed_patch_targets and choose "
            "patch_span_id exactly from patchable_spans. Do not invent patch_target_id "
            "or patch_span_id values. Do not use target_region_description, exact_text, "
            "or other prose descriptions as IDs. Do not provide authoritative "
            "original_excerpt; the controller owns exact before-text and applies the "
            "accepted patch to the chosen span. If outside-target text is needed, set "
            "requires_target_expansion true with target_expansion_reason instead of "
            "silently patching outside patchable_spans."
        )
    if worker.schema == AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA:
        prompt["revision_diff_integrity_contract"] = (
            "Report every material text change in changed_spans. For each changed span, "
            "set inside_target and within_selected_target truthfully against "
            "selected_target_contract.allowed_span_refs. If any material change is outside "
            "the selected target, set target_region_expanded true, provide "
            "expanded_target_region, expansion_reason, target_expansion_justification, and "
            "mark that changed span requires_target_expansion with target_expansion_reason. "
            "If there is no explicit expansion, all changed spans must remain inside target."
        )
    if worker.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
        variant_set = payloads.get(AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA.artifact_type)
        executed_variant_ids = _executed_ablation_variant_ids(variant_set or {})
        prompt["allowed_executed_ablation_variant_ids"] = executed_variant_ids
        prompt["ablation_comparison_contract"] = (
            "Each executed comparison row must use executed_variant_id exactly from "
            "allowed_executed_ablation_variant_ids. If discussing a non-executed "
            "operation or probe, set planned_only true, set executed_variant_id null, "
            "and provide planned_probe_id. Do not invent executed IDs and do not use "
            "short labels like v4 or A4 unless that exact ID appears in the allowed list."
        )
        prompt["allowed_ablation_evidence_basis"] = list(
            AUTONOMOUS_REVISION_ABLATION_EVIDENCE_BASIS
        )
    if worker.schema == AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA:
        prompt["allowed_provenance_source_tokens"] = list(
            AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS
        )
        prompt["old_new_rival_provenance_contract"] = (
            "judgment_provenance values must be arrays containing only exact tokens "
            "from allowed_provenance_source_tokens. Do not put sentences, quotes, "
            "summaries, or explanations in judgment_provenance."
        )
        prompt["old_new_rival_rationale_contract"] = (
            "Put prose justification in judgment_rationale using the same judgment "
            "keys. Rationale may explain the judgment, but provenance remains token-only."
        )
    return _canonical_json(prompt)


def _validator_for_revision_worker(
    subject: RevisionSubject,
    worker: AutonomousRevisionWorkerSpec,
    payloads: dict[str, dict[str, Any]],
):
    if worker.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:

        def _validate_causal_handle(parsed_payload: dict[str, object]) -> None:
            try:
                _attach_controller_target_contract(
                    subject=subject,
                    handle=parsed_payload,
                    selected_failure=payloads[
                        AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA.artifact_type
                    ],
                )
            except RevisionIntegrityError as error:
                raise ModelValidationError(str(error)) from error

        return _validate_causal_handle

    if worker.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
        handle = payloads[AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type]

        def _validate_patch_proposal(parsed_payload: dict[str, object]) -> None:
            try:
                _build_controller_revision_from_patches(
                    subject,
                    handle,
                    parsed_payload,
                    fixture_only=False,
                )
            except RevisionIntegrityError as error:
                raise ModelValidationError(str(error)) from error

        return _validate_patch_proposal

    if worker.schema == AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA:

        def _validate_diff(parsed_payload: dict[str, object]) -> None:
            try:
                candidate_payloads = dict(payloads)
                candidate_payloads[AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA.artifact_type] = (
                    parsed_payload
                )
                _validate_diff_integrity(subject, candidate_payloads)
            except RevisionIntegrityError as error:
                raise ModelValidationError(str(error)) from error

        return _validate_diff

    if worker.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
        variant_set = payloads[AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA.artifact_type]

        def _validate_ablation(parsed_payload: dict[str, object]) -> None:
            try:
                _validate_ablation_alignment(variant_set, parsed_payload)
            except RevisionIntegrityError as error:
                raise ModelValidationError(str(error)) from error

        return _validate_ablation

    return None


def _parent_ids_for_revision_worker(
    subject: RevisionSubject,
    artifacts: dict[str, ArtifactRecord],
    worker: AutonomousRevisionWorkerSpec,
) -> list[str]:
    parent_ids = [artifacts["autonomous_revision_subject_manifest"].id]
    parent_ids.extend(
        artifacts[artifact_type].id
        for artifact_type in worker.parent_artifact_types
        if artifact_type in artifacts
    )
    if worker.schema == AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA:
        parent_ids.append(subject.lab_artifacts["internal_failure_diagnosis"].id)
    if worker.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
        parent_ids.extend(
            [
                subject.lab_artifacts["targeted_recomposition_plan"].id,
                subject.lab_artifacts["hostile_reader_report"].id,
            ]
        )
    if worker.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
        parent_ids.append(subject.candidate_text.artifact_id)
    if worker.schema == AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA:
        parent_ids.append(subject.lab_artifacts["counterfactual_ablation_plan"].id)
    if worker.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
        parent_ids.append(subject.lab_artifacts["internal_reread_reader_trace"].id)
    if worker.schema == AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA:
        parent_ids.append(subject.lab_artifacts["internal_rival_comparison"].id)
    return sorted(set(parent_ids))


def _validate_revision_integrity(
    subject: RevisionSubject,
    payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    diff_report = _validate_diff_integrity(subject, payloads)
    ablation_report = _validate_ablation_integrity(payloads)
    provenance_report = _validate_old_new_rival_provenance(subject, payloads)
    return {
        "diff": diff_report["diff"],
        "target": diff_report["target"],
        "ablation": ablation_report,
        "old_new_rival_provenance": provenance_report,
    }


def _controller_target_contract_for_selected_failure(
    subject: RevisionSubject,
    selected_failure: dict[str, Any],
) -> dict[str, object]:
    plan_item = _plan_item_for_failure(
        subject.lab_payloads["targeted_recomposition_plan"],
        str(selected_failure["selected_failure_type"]),
    )
    primary_region = str(plan_item["target_region"])
    contract = _target_region_contract(
        primary_region,
        candidate_text=subject.candidate_text.text,
    )
    contract["allowed_patch_targets"] = _controller_patch_target_inventory(
        subject,
        primary_region,
    )
    contract["allowed_span_refs"] = [
        str(target["allowed_span_ref"])
        for target in contract["allowed_patch_targets"]
        if isinstance(target, dict)
    ]
    contract["protected_outside_spans"] = [
        f"all candidate spans outside {primary_region}",
    ]
    return contract


def _attach_controller_target_contract(
    *,
    subject: RevisionSubject,
    handle: dict[str, object],
    selected_failure: dict[str, Any],
) -> None:
    target_contract = _controller_target_contract_for_selected_failure(
        subject,
        selected_failure,
    )
    allowed_targets = {
        str(target["patch_target_id"]): target
        for target in target_contract["allowed_patch_targets"]
        if isinstance(target, dict)
    }
    selected_target_id = str(handle["selected_patch_target_id"])
    selected_target = allowed_targets.get(selected_target_id)
    if selected_target is None:
        known_descriptions = {
            str(target["target_region_description"]): target_id
            for target_id, target in allowed_targets.items()
        }
        if selected_target_id in known_descriptions:
            raise RevisionIntegrityError(
                "causal_handle_selector used target_region_description as "
                "selected_patch_target_id; use canonical id "
                f"{known_descriptions[selected_target_id]!r}"
            )
        allowed_ids = ", ".join(sorted(allowed_targets))
        raise RevisionIntegrityError(
            "causal_handle_selector selected unknown patch_target_id "
            f"{selected_target_id!r}; allowed_patch_targets are: {allowed_ids}"
        )

    span_ref = handle.get("span_ref")
    selection_basis = (
        str(span_ref.get("selection_basis"))
        if isinstance(span_ref, dict) and span_ref.get("selection_basis")
        else "controller-owned target inventory selected by model id"
    )
    handle["span_ref"] = {
        "source_label": subject.candidate_text.label,
        "source_class": subject.candidate_text.source_class,
        "artifact_id": subject.candidate_text.artifact_id,
        "region": selected_target["allowed_span_ref"],
        "selection_basis": selection_basis,
    }
    handle["target_region_label"] = selected_target["target_region_label"]
    handle["target_region_description"] = selected_target["target_region_description"]
    all_targets = [
        target
        for target in target_contract["allowed_patch_targets"]
        if isinstance(target, dict)
    ]
    handle["allowed_span_refs"] = [selected_target["allowed_span_ref"]]
    handle["allowed_patch_targets"] = [
        selected_target,
        *[
            target
            for target in all_targets
            if str(target["patch_target_id"]) != selected_target_id
        ],
    ]
    handle["protected_outside_spans"] = list(selected_target["protected_outside_spans"])
    handle["allowed_patch_targets_source"] = "controller_owned"
    handle["patchable_spans"] = _patchable_spans_for_target(subject, selected_target)
    handle["patchable_spans_source"] = "controller_owned"


def _build_controller_revision_from_patches(
    subject: RevisionSubject,
    handle: dict[str, Any],
    patch_proposal: dict[str, Any],
    *,
    fixture_only: bool,
) -> dict[str, dict[str, Any]]:
    original = subject.candidate_text.text
    revised = original
    patch_ids = []
    expansion_required = bool(patch_proposal["target_region_expanded"])
    expansion_reasons = []
    allowed_targets = _allowed_patch_targets_by_id(handle)
    patchable_spans = _patchable_spans_by_id(handle)
    selected_target_region = str(handle["span_ref"]["region"])
    patch_span_ids = []

    for patch in patch_proposal["patches"]:
        target = _resolve_patch_target(
            patch=patch,
            allowed_targets=allowed_targets,
            target_region_label=str(handle["target_region_label"]),
            proposal_expands_target=bool(patch_proposal["target_region_expanded"]),
        )
        span = _resolve_patch_span(
            patch=patch,
            target=target,
            patchable_spans=patchable_spans,
        )
        revised = _apply_patch_operation(revised, patch, target, span)
        patch_ids.append(str(patch["patch_id"]))
        patch_span_ids.append(str(span["patch_span_id"]))
        if bool(patch["requires_target_expansion"]):
            expansion_required = True
            expansion_reasons.append(str(patch["target_expansion_reason"]))

    if revised == original:
        raise RevisionIntegrityError("patch proposal produced no text change")

    candidate_id = f"autonomous_revision_{sha256_text(revised)[:12]}"
    changed_spans = _controller_changed_spans_from_patches(
        original=original,
        revised=revised,
        target_region=selected_target_region,
        patch_ids=patch_ids,
        patch_span_ids=patch_span_ids,
        expansion_reason=_first_nonempty(
            [
                str(patch_proposal["expansion_reason"]),
                *expansion_reasons,
            ]
        ),
    )
    diff_payload = {
        "worker": "revision_diff_report_v1_controller",
        "assembled_by_controller": True,
        "source_patch_ids": patch_ids,
        "source_patch_span_ids": patch_span_ids,
        "source_patch_proposal_id": patch_proposal["proposal_id"],
        "full_rewrite": False,
        "bounded_change": True,
        "operation_type": _operation_summary(patch_proposal["patches"]),
        "target_region": selected_target_region,
        **_target_contract_from_handle(handle),
        "causal_handle": str(handle["causal_handle"]),
        "operation": {
            "type": _operation_summary(patch_proposal["patches"]),
            "target_region": selected_target_region,
            "causal_handle": str(handle["causal_handle"]),
            "source_patch_ids": patch_ids,
        },
        "original_excerpt": _first_sentence(original),
        "revised_excerpt": _first_two_sentences(revised),
        "changed_spans": changed_spans,
        "target_region_expanded": expansion_required,
        "expanded_target_region": (
            str(patch_proposal["expanded_target_region"]) if expansion_required else ""
        ),
        "expansion_reason": _first_nonempty(
            [
                str(patch_proposal["expansion_reason"]),
                *expansion_reasons,
            ]
        )
        if expansion_required
        else "",
        "target_expansion_justification": _first_nonempty(
            [
                str(patch_proposal["expansion_reason"]),
                *expansion_reasons,
            ]
        )
        if expansion_required
        else "",
        "protected_effects_preserved": list(patch_proposal["protected_effects"]),
        "forbidden_changes_honored": list(patch_proposal["forbidden_changes_respected"]),
        "explanation": "Controller assembled the authoritative diff from accepted patches.",
        "fixture_only": fixture_only,
        "not_human_data": True,
    }
    revised_payload = {
        "worker": "bounded_targeted_recomposer_v1_controller",
        "assembled_by_controller": True,
        "source_patch_ids": patch_ids,
        "source_patch_span_ids": patch_span_ids,
        "source_patch_proposal_id": patch_proposal["proposal_id"],
        "candidate_id": candidate_id,
        "source_candidate_artifact_id": subject.candidate_text.artifact_id,
        "text": revised,
        "text_sha256": sha256_text(revised),
        "original_text_sha256": sha256_text(original),
        "targeted_causal_handle": str(handle["causal_handle"]),
        "bounded_recomposition": True,
        "full_rewrite": False,
        "changed_region": selected_target_region,
        "target_region_expanded": expansion_required,
        "preserved_protected_effects": list(patch_proposal["protected_effects"]),
        "forbidden_changes_honored": list(patch_proposal["forbidden_changes_respected"]),
        "non_final": True,
        "candidate_only": True,
        "not_human_validated": True,
        "human_validated": False,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "no_final_claim": True,
        "fixture_only": fixture_only,
        "not_human_data": True,
    }
    payloads = {
        "revised_candidate_text": revised_payload,
        "revision_diff_report": diff_payload,
    }
    _validate_diff_integrity(
        subject,
        {
            "causal_handle_selection": handle,
            "revised_candidate_text": revised_payload,
            "revision_diff_report": diff_payload,
        },
    )
    return payloads


def _validate_patch_target(
    *,
    patch: dict[str, Any],
    allowed_targets: dict[str, dict[str, Any]],
    target_region_label: str,
    proposal_expands_target: bool,
) -> None:
    _resolve_patch_target(
        patch=patch,
        allowed_targets=allowed_targets,
        target_region_label=target_region_label,
        proposal_expands_target=proposal_expands_target,
    )


def _resolve_patch_target(
    *,
    patch: dict[str, Any],
    allowed_targets: dict[str, dict[str, Any]],
    target_region_label: str,
    proposal_expands_target: bool,
) -> dict[str, Any]:
    patch_id = str(patch["patch_id"])
    patch_target_id = str(patch["patch_target_id"])
    target = allowed_targets.get(patch_target_id)
    if target is None:
        known_descriptions = {
            str(target["target_region_description"]): target_id
            for target_id, target in allowed_targets.items()
        }
        if patch_target_id in known_descriptions:
            raise RevisionIntegrityError(
                f"patch {patch_id} uses target_region_description as patch_target_id; "
                f"use canonical id {known_descriptions[patch_target_id]!r}"
            )
        allowed_ids = ", ".join(sorted(allowed_targets))
        raise RevisionIntegrityError(
            f"patch {patch_id} uses unknown patch_target_id {patch_target_id!r}; "
            f"allowed_patch_targets are: {allowed_ids}"
        )
    _ = target_region_label, proposal_expands_target
    if bool(patch["requires_target_expansion"]):
        raise RevisionIntegrityError(
            f"patch {patch_id} requested target expansion; safe target expansion is "
            "not implemented for autonomous revision patch application"
        )
    return target


def _resolve_patch_span(
    *,
    patch: dict[str, Any],
    target: dict[str, Any],
    patchable_spans: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    patch_id = str(patch["patch_id"])
    patch_span_id = str(patch["patch_span_id"])
    span = patchable_spans.get(patch_span_id)
    if span is None:
        known_exact_text = {
            str(span["exact_text"]): span_id for span_id, span in patchable_spans.items()
        }
        if patch_span_id in known_exact_text:
            raise RevisionIntegrityError(
                f"patch {patch_id} uses exact_text as patch_span_id; use canonical id "
                f"{known_exact_text[patch_span_id]!r}"
            )
        allowed_ids = ", ".join(sorted(patchable_spans))
        raise RevisionIntegrityError(
            f"patch {patch_id} uses unknown patch_span_id {patch_span_id!r}; "
            f"patchable_spans are: {allowed_ids}"
        )
    if str(span["patch_target_id"]) != str(target["patch_target_id"]):
        raise RevisionIntegrityError(
            f"patch {patch_id} patch_span_id {patch_span_id!r} belongs to target "
            f"{span['patch_target_id']!r}, not {target['patch_target_id']!r}"
        )
    if bool(span.get("protected", False)):
        raise RevisionIntegrityError(
            f"patch {patch_id} selected protected patch_span_id {patch_span_id!r}: "
            f"{span.get('protected_reason', '')}"
        )
    return span


def _apply_patch_operation(
    text: str,
    patch: dict[str, Any],
    target: dict[str, Any],
    span: dict[str, Any],
) -> str:
    operation = str(patch["operation"])
    before_text = str(span["exact_text"])
    replacement_text = str(patch["replacement_text"])
    inserted_text = str(patch["inserted_text"])
    patch_id = str(patch["patch_id"])
    target_window = str(target["text_window"])
    if before_text not in target_window:
        raise RevisionIntegrityError(
            f"patch {patch_id} patch_span_id {span['patch_span_id']!r} exact_text "
            f"does not appear inside patch target {target['patch_target_id']!r}"
        )
    if target_window not in text:
        raise RevisionIntegrityError(
            f"patch target {target['patch_target_id']!r} text_window does not appear in "
            "candidate text"
        )
    if before_text not in text:
        raise RevisionIntegrityError(
            f"patch {patch_id} patch_span_id {span['patch_span_id']!r} exact_text "
            "does not appear in candidate text"
        )
    target_start = text.index(target_window)
    target_end = target_start + len(target_window)
    before_target = text[:target_start]
    target_text = text[target_start:target_end]
    after_target = text[target_end:]
    if operation in {"replace", "compress"}:
        changed_target = target_text.replace(before_text, replacement_text, 1)
        return before_target + changed_target + after_target
    if operation == "delete":
        changed_target = target_text.replace(before_text, "", 1)
        return before_target + changed_target + after_target
    if operation == "insert_after":
        changed_target = target_text.replace(
            before_text,
            f"{before_text} {inserted_text}",
            1,
        )
        return before_target + changed_target + after_target
    if operation == "insert_before":
        changed_target = target_text.replace(
            before_text,
            f"{inserted_text} {before_text}",
            1,
        )
        return before_target + changed_target + after_target
    raise RevisionIntegrityError(f"patch {patch_id} has unsupported operation {operation!r}")


def _controller_changed_spans_from_patches(
    *,
    original: str,
    revised: str,
    target_region: str,
    patch_ids: list[str],
    patch_span_ids: list[str],
    expansion_reason: str,
) -> list[dict[str, object]]:
    spans = _reported_changed_spans_for_texts(
        original,
        revised,
        target_region,
        "controller-applied patch operation",
    )
    patch_id_summary = ",".join(patch_ids)
    for span in spans:
        span["source_patch_ids"] = patch_ids
        span["source_patch_span_ids"] = patch_span_ids
        span["patch_span_id"] = patch_span_ids[0] if len(patch_span_ids) == 1 else ""
        span["reason"] = f"controller-applied patch ids: {patch_id_summary}"
        if bool(span["requires_target_expansion"]):
            span["target_expansion_reason"] = expansion_reason
    return spans


def _operation_summary(patches: list[dict[str, Any]]) -> str:
    operations = sorted({str(patch["operation"]) for patch in patches})
    return "+".join(operations)


def _first_nonempty(values: list[str]) -> str:
    for value in values:
        if value.strip():
            return value.strip()
    return ""


def _validate_diff_integrity(
    subject: RevisionSubject,
    payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    original = subject.candidate_text.text
    revised = str(payloads["revised_candidate_text"]["text"])
    diff_report = payloads["revision_diff_report"]
    handle = payloads["causal_handle_selection"]
    selected_target_region = str(handle["span_ref"]["region"])
    material_changes = _material_text_changes(original, revised)
    reported_spans = list(diff_report["changed_spans"])
    missing_changes = []
    target_violations = []
    out_of_target_changes = []

    for change in material_changes:
        matching_span = _matching_changed_span(reported_spans, change)
        if matching_span is None:
            missing_changes.append(_change_summary(change))
            continue
        within_selected_target = _region_matches_target(
            str(change["region"]),
            selected_target_region,
        )
        if not within_selected_target:
            out_of_target_changes.append(
                _change_summary(change, matching_span=matching_span, inside_target=False)
            )
            expansion_reported = (
                bool(diff_report["target_region_expanded"])
                and bool(str(diff_report["target_expansion_justification"]).strip())
                and bool(str(diff_report.get("expanded_target_region", "")).strip())
                and bool(str(diff_report.get("expansion_reason", "")).strip())
                and not bool(matching_span["within_selected_target"])
                and not bool(matching_span.get("inside_target", True))
                and bool(matching_span.get("requires_target_expansion", False))
                and bool(str(matching_span.get("target_expansion_reason", "")).strip())
            )
            if (
                not expansion_reported
            ):
                target_violations.append(
                    _change_summary(
                        change,
                        matching_span=matching_span,
                        inside_target=False,
                        expansion_absent=True,
                    )
                )

    if missing_changes:
        raise RevisionIntegrityError(
            "revision_diff_report does not cover material text changes: "
            + "; ".join(missing_changes)
        )
    if target_violations:
        raise RevisionIntegrityError(
            "revised_candidate_text changes outside selected target region "
            f"{selected_target_region!r} without explicit target expansion: "
            + "; ".join(target_violations)
        )

    return {
        "diff": {
            "material_change_count": len(material_changes),
            "reported_changed_span_count": len(reported_spans),
            "all_material_changes_reported": True,
        },
        "target": {
            "selected_target_region": selected_target_region,
            "reported_target_region": diff_report["target_region"],
            "target_region_label": diff_report.get("target_region_label"),
            "allowed_span_refs": diff_report.get("allowed_span_refs", []),
            "target_region_expanded": bool(diff_report["target_region_expanded"]),
            "expanded_target_region": diff_report.get("expanded_target_region", ""),
            "expansion_reason": diff_report.get("expansion_reason", ""),
            "target_expansion_justification": diff_report["target_expansion_justification"],
            "out_of_target_change_count": len(out_of_target_changes),
            "out_of_target_changes": out_of_target_changes,
        },
    }


def _validate_ablation_integrity(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _validate_ablation_alignment(
        payloads["ablation_variant_set"],
        payloads["ablation_reread_comparison"],
    )


def _validate_ablation_alignment(
    variant_set: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    variants_by_id = {
        str(variant["variant_id"]): variant
        for variant in variant_set["variants"]
    }
    executed_variant_ids = {
        variant_id
        for variant_id, variant in variants_by_id.items()
        if bool(variant["executed"])
    }
    invalid_rows = []
    planned_only_rows = []
    executed_rows = []
    actual_evaluation_rows = []
    predicted_rows = []

    for row in comparison["comparison_rows"]:
        planned_only = bool(row["planned_only"])
        executed_variant_id = row.get("executed_variant_id")
        planned_probe_id = row.get("planned_probe_id")
        row_id = str(row["row_id"])

        if planned_only:
            if executed_variant_id is not None:
                invalid_rows.append(
                    f"{row_id} is planned_only but has executed_variant_id "
                    f"{executed_variant_id}"
                )
                continue
            if not planned_probe_id:
                invalid_rows.append(f"{row_id} is planned_only but has no planned_probe_id")
                continue
            planned_only_rows.append(str(planned_probe_id))
            predicted_rows.append(str(planned_probe_id))
            continue

        if not executed_variant_id:
            invalid_rows.append(f"{row_id} has no executed_variant_id and is not planned_only")
            continue
        variant_id = str(executed_variant_id)
        if variant_id not in variants_by_id:
            invalid_rows.append(
                f"{variant_id} is not in ablation_variant_set and is not planned_only"
            )
            continue
        if variant_id not in executed_variant_ids:
            invalid_rows.append(f"{variant_id} references an unexecuted variant")
            continue

        executed_rows.append(variant_id)
        if row["evidence_basis"] == "actual_ablation_reread_evaluation":
            actual_evaluation_rows.append(variant_id)
        else:
            predicted_rows.append(variant_id)

    if invalid_rows:
        raise RevisionIntegrityError(
            "ablation_reread_comparison rows are not aligned with ablation_variant_set: "
            + "; ".join(invalid_rows)
        )

    return {
        "variant_count": len(variants_by_id),
        "executed_variant_count": len(executed_variant_ids),
        "comparison_row_count": len(comparison["comparison_rows"]),
        "planned_only_row_count": len(planned_only_rows),
        "executed_row_count": len(executed_rows),
        "actual_evaluation_row_count": len(actual_evaluation_rows),
        "predicted_row_count": len(predicted_rows),
        "comparison_predicted_only": len(actual_evaluation_rows) == 0,
        "comparison_actually_evaluated": len(actual_evaluation_rows) > 0,
        "planned_only_rows": planned_only_rows,
        "executed_rows": executed_rows,
    }


def _executed_ablation_variant_ids(variant_set: dict[str, Any]) -> list[str]:
    variants = variant_set.get("variants")
    if not isinstance(variants, list):
        return []
    return [
        str(variant["variant_id"])
        for variant in variants
        if isinstance(variant, dict) and bool(variant.get("executed"))
    ]


def _validate_old_new_rival_provenance(
    subject: RevisionSubject,
    payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    comparison = payloads["old_new_rival_comparison"]
    provenance = comparison["judgment_provenance"]
    invalid = []
    for key in AUTONOMOUS_REVISION_JUDGMENT_KEYS:
        sources = list(provenance.get(key, []))
        if not sources:
            invalid.append(f"{key} has no provenance")
            continue
        unsupported = [
            source
            for source in sources
            if source not in AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS
        ]
        if unsupported:
            invalid.append(f"{key} has unsupported provenance: {unsupported}")
    if subject.strongest_rival is not None and "strongest_rival_text" not in provenance[
        "rival_still_beats_candidate"
    ]:
        invalid.append("rival_still_beats_candidate must cite strongest_rival_text")
    if invalid:
        raise RevisionIntegrityError(
            "old_new_rival_comparison provenance is incomplete: " + "; ".join(invalid)
        )
    return {
        "judgment_count": len(AUTONOMOUS_REVISION_JUDGMENT_KEYS),
        "all_judgments_have_provenance": True,
        "allowed_sources": sorted(AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS),
    }


def _material_text_changes(original: str, revised: str) -> list[dict[str, object]]:
    original_units = _diff_units(original)
    revised_units = _diff_units(revised)
    matcher = SequenceMatcher(None, original_units, revised_units, autojunk=False)
    changes = []
    for tag, original_start, original_end, revised_start, revised_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        before = " ".join(original_units[original_start:original_end]).strip()
        after = " ".join(revised_units[revised_start:revised_end]).strip()
        if not before and not after:
            continue
        if before == after:
            continue
        index = min(original_start, max(0, len(original_units) - 1))
        changes.append(
            {
                "change_id": f"change_{len(changes) + 1:02d}",
                "unit_index": index,
                "before": before,
                "after": after,
                "region": _region_for_unit_index(index, len(original_units)),
                "tag": tag,
            }
        )
    return changes


def _reported_changed_spans_for_texts(
    original: str,
    revised: str,
    target_region: str,
    reason: str,
) -> list[dict[str, object]]:
    spans = []
    for change in _material_text_changes(original, revised):
        inside_target = _region_matches_target(str(change["region"]), target_region)
        spans.append(
            {
                "changed_span_id": str(change["change_id"]),
                "before": change["before"],
                "after": change["after"],
                "region": change["region"],
                "inside_target": inside_target,
                "within_selected_target": inside_target,
                "requires_target_expansion": not inside_target,
                "target_expansion_reason": (
                    ""
                    if inside_target
                    else "outside selected target; top-level target expansion is required"
                ),
                "reason": reason,
            }
        )
    return spans


def _target_region_contract(region: str, *, candidate_text: str = "") -> dict[str, object]:
    label = "_".join(_words(region)[:8]) or "target_region"
    target = _patch_target_for_region(region, candidate_text)
    return {
        "target_region_label": f"target_region:{label}",
        "target_region_description": (
            "Selected bounded revision target; material edits outside this region "
            "require explicit target expansion."
        ),
        "allowed_span_refs": [region],
        "allowed_patch_targets": [target],
        "protected_outside_spans": [f"all candidate spans outside {region}"],
    }


def _patch_target_for_region(region: str, candidate_text: str) -> dict[str, object]:
    label = "_".join(_words(region)[:8]) or "target_region"
    return {
        "patch_target_id": _patch_target_id_for_region(region),
        "target_region_label": f"target_region:{label}",
        "target_region_description": region,
        "allowed_span_ref": region,
        "text_window": _target_text_window(candidate_text, region),
        "paragraph_index": _target_paragraph_index(region),
        "protected_outside_spans": [f"all candidate spans outside {region}"],
    }


def _controller_patch_target_inventory(
    subject: RevisionSubject,
    primary_region: str,
) -> list[dict[str, object]]:
    candidate_text = subject.candidate_text.text
    regions = [
        primary_region,
        "opening sentence",
        "opening paragraph through the first two image-to-interpretation pivots",
        "middle conceptual ladder",
        "ending return closure",
        "final image",
    ]
    targets: dict[str, dict[str, object]] = {}
    for region in regions:
        target = _patch_target_for_region(region, candidate_text)
        targets.setdefault(str(target["patch_target_id"]), target)
    return list(targets.values())


def _patchable_spans_for_target(
    subject: RevisionSubject,
    target: dict[str, object],
) -> list[dict[str, object]]:
    target_window = str(target["text_window"])
    candidate_text = subject.candidate_text.text
    if target_window not in candidate_text:
        raise RevisionIntegrityError(
            f"patch target {target['patch_target_id']!r} text_window does not appear in "
            "candidate text"
        )
    span_texts = _sentences(target_window) or [target_window.strip()]
    spans = []
    used_ids: set[str] = set()
    for index, exact_text in enumerate(span_texts, start=1):
        if not exact_text.strip():
            continue
        paragraph_index = _paragraph_index_for_excerpt(candidate_text, exact_text)
        span_id = _patch_span_id(
            str(target["patch_target_id"]),
            paragraph_index=paragraph_index,
            sentence_index=index,
        )
        while span_id in used_ids:
            span_id = f"{span_id}_{len(used_ids) + 1:02d}"
        used_ids.add(span_id)
        spans.append(
            {
                "patch_span_id": span_id,
                "patch_target_id": target["patch_target_id"],
                "paragraph_index": paragraph_index,
                "sentence_index": index,
                "span_index": index,
                "exact_text": exact_text,
                "context_before": _context_before(target_window, exact_text),
                "context_after": _context_after(target_window, exact_text),
                "source_text_sha256": sha256_text(candidate_text),
                "protected": False,
                "protected_reason": "",
            }
        )
    if not spans:
        raise RevisionIntegrityError(
            f"patch target {target['patch_target_id']!r} exposes no patchable spans"
        )
    return spans


def _patchable_spans_by_id(handle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(span["patch_span_id"]): span
        for span in handle.get("patchable_spans", [])
        if isinstance(span, dict)
    }


def _patch_span_id(
    patch_target_id: str,
    *,
    paragraph_index: int,
    sentence_index: int,
) -> str:
    target = "".join(
        character if character.isalnum() else "_"
        for character in patch_target_id.lower()
    ).strip("_")
    while "__" in target:
        target = target.replace("__", "_")
    return f"span_{target}_p{paragraph_index + 1:02d}_s{sentence_index:02d}"


def _paragraph_index_for_excerpt(candidate_text: str, excerpt: str) -> int:
    for index, paragraph in enumerate(
        part.strip() for part in candidate_text.split("\n\n") if part.strip()
    ):
        if excerpt in paragraph:
            return index
    return 0


def _context_before(container: str, exact_text: str) -> str:
    index = container.find(exact_text)
    if index <= 0:
        return ""
    return container[:index].strip()[-180:]


def _context_after(container: str, exact_text: str) -> str:
    index = container.find(exact_text)
    if index < 0:
        return ""
    start = index + len(exact_text)
    return container[start:].strip()[:180]


def _target_contract_from_handle(handle: dict[str, Any]) -> dict[str, object]:
    region = str(handle["span_ref"]["region"])
    fallback = _target_region_contract(region)
    allowed_patch_targets = list(
        handle.get("allowed_patch_targets", fallback["allowed_patch_targets"])
    )
    return {
        "target_region_label": str(
            handle.get("target_region_label", fallback["target_region_label"])
        ),
        "target_region_description": str(
            handle.get(
                "target_region_description",
                fallback["target_region_description"],
            )
        ),
        "allowed_span_refs": list(handle.get("allowed_span_refs", fallback["allowed_span_refs"])),
        "allowed_patch_targets": allowed_patch_targets,
        "protected_outside_spans": list(
            handle.get("protected_outside_spans", fallback["protected_outside_spans"])
        ),
    }


def _patch_target_id_for_region(region: str) -> str:
    lowered = region.lower()
    if "first two" in lowered and ("pivot" in lowered or "image-to-interpretation" in lowered):
        return "target_opening_first_pivots"
    words = _words(region)
    compact = "_".join(words[:8])
    return f"target_{compact or 'region'}"


def _target_text_window(candidate_text: str, region: str) -> str:
    if not candidate_text.strip():
        return region
    lowered = region.lower()
    paragraphs = [part.strip() for part in candidate_text.split("\n\n") if part.strip()]
    if "ending" in lowered and paragraphs:
        return paragraphs[-1]
    if "middle" in lowered and len(paragraphs) > 2:
        return paragraphs[len(paragraphs) // 2]
    if "whole" in lowered or "artifact" in lowered:
        return candidate_text.strip()
    if "first two" in lowered and ("pivot" in lowered or "image-to-interpretation" in lowered):
        if len(paragraphs) >= 2:
            return "\n\n".join(paragraphs[:2])
        sentences = _sentences(candidate_text)
        return _leading_sentence_window(candidate_text, min(8, len(sentences)))
    sentences = _sentences(candidate_text)
    if "first two" in lowered and len(sentences) >= 2:
        return _leading_sentence_window(candidate_text, 2)
    if sentences:
        return sentences[0]
    return candidate_text.strip()


def _leading_sentence_window(candidate_text: str, count: int) -> str:
    if count <= 0:
        return candidate_text.strip()
    sentences = _sentences(candidate_text)
    end = 0
    for sentence in sentences[:count]:
        index = candidate_text.find(sentence, end)
        if index < 0:
            break
        end = index + len(sentence)
    return candidate_text[:end].strip() if end else candidate_text.strip()


def _target_paragraph_index(region: str) -> int:
    lowered = region.lower()
    if "ending" in lowered:
        return -1
    if "middle" in lowered:
        return 1
    return 0


def _allowed_patch_targets_by_id(handle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(target["patch_target_id"]): target
        for target in handle.get("allowed_patch_targets", [])
        if isinstance(target, dict)
    }


def _diff_units(text: str) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if len(paragraphs) > 1:
        return paragraphs
    sentences = _sentences(text)
    if sentences:
        return sentences
    stripped = text.strip()
    return [stripped] if stripped else []


def _region_for_unit_index(index: int, total: int) -> str:
    if total <= 1:
        return "whole artifact"
    if index == 0:
        return "opening paragraph"
    if index >= total - 1:
        return "ending paragraph"
    return "middle paragraph"


def _matching_changed_span(
    reported_spans: list[dict[str, Any]],
    change: dict[str, object],
) -> dict[str, Any] | None:
    for span in reported_spans:
        if _span_covers_change(span, change):
            return span
    return None


def _span_covers_change(span: dict[str, Any], change: dict[str, object]) -> bool:
    before_actual = _normalize_diff_text(str(change["before"]))
    after_actual = _normalize_diff_text(str(change["after"]))
    before_reported = _normalize_diff_text(str(span.get("before", "")))
    after_reported = _normalize_diff_text(str(span.get("after", "")))
    return _text_covers(before_reported, before_actual) or _text_covers(
        after_reported,
        after_actual,
    )


def _text_covers(reported: str, actual: str) -> bool:
    if not actual:
        return False
    if not reported:
        return False
    if reported in actual or actual in reported:
        return True
    reported_tokens = set(reported.split())
    actual_tokens = set(actual.split())
    if not reported_tokens or not actual_tokens:
        return False
    overlap = len(reported_tokens & actual_tokens)
    return overlap / max(1, min(len(reported_tokens), len(actual_tokens))) >= 0.65


def _normalize_diff_text(text: str) -> str:
    return " ".join(_words(text))


def _region_matches_target(change_region: str, selected_target_region: str) -> bool:
    change = change_region.lower()
    target = selected_target_region.lower()
    if "whole" in target or "artifact" in target:
        return True
    if "opening-to" in target or "bridge" in target:
        return "opening" in change or "middle" in change
    if "first two" in target and ("pivot" in target or "image-to-interpretation" in target):
        return "opening" in change or "middle" in change
    for marker in ("opening", "middle", "ending"):
        if marker in target and marker in change:
            return True
    return change in target or target in change


def _change_summary(
    change: dict[str, object],
    *,
    matching_span: dict[str, Any] | None = None,
    inside_target: bool | None = None,
    expansion_absent: bool | None = None,
) -> str:
    before = str(change["before"])[:80].replace("\n", " ")
    after = str(change["after"])[:80].replace("\n", " ")
    parts = [
        f"change_id={change.get('change_id', 'unknown')}",
        f"unit_index={change.get('unit_index', 'unknown')}",
        f"region={change['region']!r}",
    ]
    if matching_span is not None:
        parts.append(f"changed_span_id={matching_span.get('changed_span_id', 'unknown')}")
    if inside_target is not None:
        parts.append(f"inside_target={inside_target}")
    if expansion_absent is not None:
        parts.append(f"expansion_absent={expansion_absent}")
    parts.append(f"before={before!r}")
    parts.append(f"after={after!r}")
    return " ".join(parts)


def _fake_model_payload_for_revision_schema(
    schema: WorkerSchema,
    prompt: dict[str, Any],
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if schema == AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA:
        return _fake_model_selected_failure_payload(prompt)
    if schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
        return _fake_model_causal_handle_payload(prompt, prior_payloads)
    if schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
        return _fake_model_revised_candidate_payload(prompt, prior_payloads)
    if schema == AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA:
        return _fake_model_diff_payload(prompt, prior_payloads)
    if schema == AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA:
        return _fake_model_ablation_variants_payload(prompt, prior_payloads)
    if schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
        return _fake_model_ablation_comparison_payload(prompt, prior_payloads)
    if schema == AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA:
        return _fake_model_old_new_rival_payload(prompt, prior_payloads)
    if schema == AUTONOMOUS_REVISION_LOCAL_LAW_CASE_NOTE_SCHEMA:
        return _fake_model_local_law_payload(prior_payloads)
    raise ModelClientError(f"unsupported autonomous revision schema: {schema.name}")


def _fake_model_selected_failure_payload(prompt: dict[str, Any]) -> dict[str, Any]:
    diagnosis = prompt["reader_lab_payloads"]["internal_failure_diagnosis"]
    failures = list(diagnosis["failures"])
    selected = _choose_failure(failures)
    return {
        "selection_rule": "first live-reader-lab failure with bounded repair leverage",
        "selected_failure_type": str(selected["failure_type"]),
        "selected_diagnosis": str(selected["diagnosis"]),
        "severity": str(selected["severity"]),
        "reader_lab_evidence_artifacts": [str(name) for name in selected["evidence_artifacts"]],
        "source_failure_index": failures.index(selected),
        "references_live_reader_lab_evidence": True,
        "not_human_data": True,
    }


def _fake_model_causal_handle_payload(
    prompt: dict[str, Any],
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected_failure = prior_payloads[AUTONOMOUS_REVISION_SELECTED_FAILURE_SCHEMA.artifact_type]
    plan = prompt["reader_lab_payloads"]["targeted_recomposition_plan"]
    plan_item = _plan_item_for_failure(plan, str(selected_failure["selected_failure_type"]))
    candidate = prompt["candidate"]
    quoted = _first_sentence(str(candidate["text"]))
    target_contract = dict(
        prompt.get("controller_owned_patch_target_inventory")
        or _target_region_contract(
            str(plan_item["target_region"]),
            candidate_text=str(candidate["text"]),
        )
    )
    patch_target = _first_allowed_patch_target(target_contract)
    return {
        "bounded_target": True,
        "target_count": 1,
        "does_not_rebuild_artifact": True,
        "selected_patch_target_id": str(patch_target["patch_target_id"]),
        "span_ref": {
            "source_label": str(candidate["label"]),
            "source_class": str(candidate["source_class"]),
            "artifact_id": str(candidate["artifact_id"]),
            "region": str(patch_target["allowed_span_ref"]),
            "selection_basis": "smallest handle connected to live reader-lab evidence",
        },
        "target_region_label": str(patch_target["target_region_label"]),
        "target_region_description": str(patch_target["target_region_description"]),
        "allowed_span_refs": list(target_contract["allowed_span_refs"]),
        "protected_outside_spans": list(target_contract["protected_outside_spans"]),
        "quoted_text": quoted,
        "causal_handle": str(plan_item["causal_handle"]),
        "local_law_hypothesis": (
            "The opening object must create a consequence before interpretation takes over."
        ),
        "suspected_failure": str(selected_failure["selected_diagnosis"]),
        "why_it_might_be_junk": "The handle becomes junk if it explains the artifact.",
        "why_it_might_be_treasure": (
            "The handle becomes treasure if it lets the opening return changed."
        ),
        "connotation_or_register_risk": (
            "Keep the repair inside domestic object-world pressure, not process language."
        ),
        "variant_probe": "insert one local consequence and test whether reread pressure rises",
        "ablation_probe": "remove that consequence and test whether reread pressure falls",
        "expected_reader_state_change": (
            "the first read notices an object condition; reread treats it as planted cause"
        ),
        "uncertainty": "internal model evidence can guide revision but cannot finalize",
        "protected_effects": list(plan_item["protected_effects"]),
        "forbidden_changes": list(plan_item["forbidden_changes"]),
        "not_human_data": True,
    }


def _fake_model_revised_candidate_payload(
    prompt: dict[str, Any],
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    candidate = prompt["candidate"]
    original = str(candidate["text"])
    handle = dict(prior_payloads[AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type])
    selected_target_contract = prompt.get("selected_target_contract")
    if isinstance(selected_target_contract, dict):
        handle.update(
            {
                "span_ref": selected_target_contract["span_ref"],
                "target_region_label": selected_target_contract["target_region_label"],
                "target_region_description": selected_target_contract[
                    "target_region_description"
                ],
                "allowed_span_refs": selected_target_contract["allowed_span_refs"],
                "allowed_patch_targets": selected_target_contract["allowed_patch_targets"],
                "protected_outside_spans": selected_target_contract[
                    "protected_outside_spans"
                ],
            }
        )
    first_sentence = _first_sentence(original)
    inserted_text = _revision_insertion_text()
    patch_target = _selected_allowed_patch_target(handle)
    patch_span = _first_patchable_span_for_target(prompt, str(patch_target["patch_target_id"]))
    return {
        "proposal_id": f"revision_patch_{sha256_text(first_sentence + inserted_text)[:12]}",
        "source_candidate_artifact_id": str(candidate["artifact_id"]),
        "targeted_causal_handle": str(handle["causal_handle"]),
        "target_region_label": str(handle["target_region_label"]),
        "patches": [
            {
                "patch_id": "patch_01",
                "patch_span_id": str(patch_span["patch_span_id"]),
                "patch_target_id": str(patch_target["patch_target_id"]),
                "operation": "insert_after",
                "replacement_text": "",
                "inserted_text": inserted_text,
                "failure_addressed": str(handle["suspected_failure"]),
                "causal_handle_id": str(handle["causal_handle"]),
                "protected_effects_preserved": list(handle["protected_effects"]),
                "forbidden_changes_respected": list(handle["forbidden_changes"]),
                "rationale": "Patch the controller-selected span without rewriting the artifact.",
                "expected_reader_state_change": str(handle["expected_reader_state_change"]),
                "requires_target_expansion": False,
                "target_expansion_reason": "",
                "confidence": 0.62,
                "uncertainty": "patch proposal is model-guided internal evidence only",
            }
        ],
        "bounded_patch_set": True,
        "full_rewrite": False,
        "target_region_expanded": False,
        "expanded_target_region": "",
        "expansion_reason": "",
        "protected_effects": list(handle["protected_effects"]),
        "forbidden_changes_respected": list(handle["forbidden_changes"]),
        "non_final": True,
        "candidate_only": True,
        "not_human_validated": True,
        "human_validated": False,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "not_human_data": True,
    }


def _fake_model_diff_payload(
    prompt: dict[str, Any],
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    original = str(prompt["candidate"]["text"])
    handle = prior_payloads[AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type]
    revised = _prior_revised_candidate_payload(prompt, prior_payloads)
    target_region = str(handle["span_ref"]["region"])
    target_contract = _target_contract_from_handle(handle)
    return {
        "full_rewrite": False,
        "bounded_change": True,
        "operation_type": "append_local_consequence",
        "target_region": target_region,
        **target_contract,
        "causal_handle": str(handle["causal_handle"]),
        "original_excerpt": _first_sentence(original),
        "revised_excerpt": _first_two_sentences(str(revised["text"])),
        "changed_spans": _reported_changed_spans_for_texts(
            original,
            str(revised["text"]),
            target_region,
            "bounded insertion adds consequence while preserving object-world",
        ),
        "target_region_expanded": False,
        "expanded_target_region": "",
        "expansion_reason": "",
        "target_expansion_justification": "",
        "protected_effects_preserved": list(handle["protected_effects"]),
        "forbidden_changes_honored": list(handle["forbidden_changes"]),
        "explanation": "The repair targets one local causal handle instead of rewriting the artifact.",
        "not_human_data": True,
    }


def _fake_model_ablation_variants_payload(
    prompt: dict[str, Any],
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    original = str(prompt["candidate"]["text"])
    handle = prior_payloads[AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type]
    revised = _prior_revised_candidate_payload(prompt, prior_payloads)
    revised_text = str(revised["text"])
    operations = (
        (
            "remove_suspected_causal_handle",
            "Remove the inserted consequence and expect reread pressure to drop.",
            original,
        ),
        (
            "replace_suspected_word_phrase_image",
            "Replace pressure phrase with plainer image and test register loss.",
            revised_text.replace("one ring of damp wood", "one pale mark"),
        ),
        (
            "flatten_metaphor",
            "Flatten local pressure into explanation and watch fake depth.",
            revised_text + " This means the room has consequences.",
        ),
        (
            "move_motif_earlier_later",
            "Move the morning/table motif later and test opening pressure.",
            _move_first_sentence_to_end(revised_text),
        ),
        (
            "remove_ending_echo",
            "Cut the final echo and test whether reread return closes.",
            _remove_last_sentence(revised_text),
        ),
        (
            "restore_old_wording",
            "Restore old wording to see whether the new handle was necessary.",
            original,
        ),
        (
            "correct_or_normalize_irregularity",
            "Normalize the odd pressure and test whether smoothness damages the field.",
            revised_text.replace("It did not explain the night", "The room was quiet"),
        ),
        (
            "damage_or_roughen_too_smooth_phrase",
            "Roughen a smooth phrase only if local law needs friction.",
            revised_text.replace("room to the morning", "room to morning's uneven edge"),
        ),
    )
    return {
        "targeted_causal_handle": str(handle["causal_handle"]),
        "variants": [
            {
                "variant_id": f"variant_{index:02d}",
                "operation": operation,
                "variant_probe": description,
                "ablation_probe": "compare internal first-read/reread deltas",
                "text": text,
                "executed": True,
                "expected_reader_state_change": _expected_ablation_change(operation),
                "uncertainty": "model-guided probe, not reader evidence",
            }
            for index, (operation, description, text) in enumerate(operations, start=1)
        ],
        "does_not_select_winner": True,
        "not_human_data": True,
    }


def _fake_model_ablation_comparison_payload(
    prompt: dict[str, Any],
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    variants = prior_payloads[AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA.artifact_type]
    return {
        "candidate_label": str(prompt["candidate"]["label"]),
        "comparison_rows": [
            {
                "row_id": f"comparison_{str(variant['variant_id'])}",
                "executed_variant_id": str(variant["variant_id"]),
                "planned_probe_id": None,
                "operation": str(variant["operation"]),
                "planned_only": False,
                "evidence_basis": "actual_ablation_variant",
                "comparison_summary": (
                    "probe only; local field decides whether the feature is treasure or junk"
                ),
                "predicted_or_observed_effect": _variant_delta(str(variant["operation"])),
                "rationale": "executed generated variant, not human reader evidence",
                "not_human_data": True,
            }
            for variant in variants["variants"]
        ],
        "summary": (
            "Ablation comparison keeps the repair provisional and points to another "
            "closed-loop pass before operator approval."
        ),
        "not_human_data": True,
    }


def _fake_model_old_new_rival_payload(
    prompt: dict[str, Any],
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    original = str(prompt["candidate"]["text"])
    revised = _prior_revised_candidate_payload(prompt, prior_payloads)
    rival = prompt.get("strongest_rival")
    original_score = _score_text(original)
    revised_score = _score_text(str(revised["text"]))
    rival_score = _score_text(str(rival["text"])) if isinstance(rival, dict) else None
    rival_still_beats = False
    if rival_score is not None:
        rival_still_beats = int(rival_score["local_embodiment_score"]) >= int(
            revised_score["local_embodiment_score"]
        )
    return {
        "reread_transformation_improved": int(revised_score["reread_transformation_score"])
        >= int(original_score["reread_transformation_score"]),
        "opening_transformation_improved": True,
        "local_embodiment_improved": int(revised_score["local_embodiment_score"])
        >= int(original_score["local_embodiment_score"]),
        "overexplanation_decreased": True,
        "fake_depth_risk_decreased": False,
        "revised_candidate_became_more_schematic": False,
        "strongest_rival_present": rival_score is not None,
        "rival_still_beats_candidate": rival_still_beats,
        "another_revision_cycle_needed": True,
        "comparison_basis": "model-driver internal comparison, not human data",
        "rival_pressure_preserved": rival_score is not None,
        "old_new_summary": "The revised candidate is bounded and improved but not final.",
        "rival_pressure_summary": (
            "Strongest rival pressure remains active and cannot be collapsed into a pass."
        ),
        "judgment_provenance": _default_judgment_provenance(rival_score is not None),
        "judgment_rationale": _default_judgment_rationale(rival_score is not None),
        "not_human_data": True,
    }


def _prior_revised_candidate_payload(
    prompt: dict[str, Any],
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    prior_outputs = prompt.get("prior_outputs")
    if isinstance(prior_outputs, dict) and isinstance(
        prior_outputs.get("revised_candidate_text"),
        dict,
    ):
        return prior_outputs["revised_candidate_text"]
    return prior_payloads["revised_candidate_text"]


def _first_allowed_patch_target(handle: dict[str, Any]) -> dict[str, Any]:
    targets = list(handle.get("allowed_patch_targets", []))
    if not targets:
        raise ModelClientError("causal handle exposes no allowed_patch_targets")
    first = targets[0]
    if not isinstance(first, dict):
        raise ModelClientError("causal handle allowed_patch_targets must contain objects")
    return first


def _selected_allowed_patch_target(handle: dict[str, Any]) -> dict[str, Any]:
    targets = _allowed_patch_targets_by_id(handle)
    selected_target_id = str(handle.get("selected_patch_target_id", ""))
    target = targets.get(selected_target_id)
    if target is None:
        return _first_allowed_patch_target(handle)
    return target


def _first_patchable_span_for_target(
    prompt: dict[str, Any],
    patch_target_id: str,
) -> dict[str, Any]:
    for span in prompt.get("patchable_spans", []):
        if isinstance(span, dict) and str(span.get("patch_target_id")) == patch_target_id:
            return span
    raise ModelClientError(
        f"candidate reviser prompt exposes no patchable spans for {patch_target_id!r}"
    )


def _first_span_for_target_from_handle(
    handle: dict[str, Any],
    patch_target_id: str,
) -> dict[str, Any]:
    for span in handle.get("patchable_spans", []):
        if isinstance(span, dict) and str(span.get("patch_target_id")) == patch_target_id:
            return span
    raise ModelClientError(f"causal handle exposes no patchable spans for {patch_target_id!r}")


def _fake_model_local_law_payload(
    prior_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    handle = prior_payloads[AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.artifact_type]
    comparison = prior_payloads[
        AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA.artifact_type
    ]
    return {
        "principle": (
            "No feature is globally good or bad; it becomes useful only when necessary "
            "inside the local field."
        ),
        "span_ref": handle["span_ref"],
        "quoted_text": str(handle["quoted_text"]),
        "local_law_hypothesis": str(handle["local_law_hypothesis"]),
        "suspected_failure": str(handle["suspected_failure"]),
        "why_it_might_be_junk": str(handle["why_it_might_be_junk"]),
        "why_it_might_be_treasure": str(handle["why_it_might_be_treasure"]),
        "connotation_or_register_risk": str(handle["connotation_or_register_risk"]),
        "variant_probe": str(handle["variant_probe"]),
        "ablation_probe": str(handle["ablation_probe"]),
        "expected_reader_state_change": str(handle["expected_reader_state_change"]),
        "uncertainty": str(handle["uncertainty"]),
        "preserve_irregularity_rule": (
            "Smoothing is forbidden when irregularity carries local pressure."
        ),
        "comparison_result": {
            "another_revision_cycle_needed": bool(comparison["another_revision_cycle_needed"]),
            "rival_still_beats_candidate": bool(comparison["rival_still_beats_candidate"]),
        },
        "not_human_data": True,
    }


def _load_revision_subject(connection, reader_lab_packet_dir: Path) -> RevisionSubject:
    packet_envelope = read_json_file(reader_lab_packet_dir / "internal_reader_lab_packet.json")
    if packet_envelope.get("artifact_type") != "internal_reader_lab_packet":
        raise ValueError("reader-lab packet must contain internal_reader_lab_packet.json")
    packet_payload = packet_envelope["payload"]
    if not isinstance(packet_payload, dict):
        raise ValueError("reader-lab packet payload is not an object")

    run_id = str(packet_envelope["run_id"])
    reader_lab_packet_id = str(packet_payload.get("packet_id", reader_lab_packet_dir.name))
    source_packet_dir = Path(str(packet_payload["source_packet_dir"])).resolve()
    source_packet_id = str(packet_payload["source_packet_id"])
    artifact_ids = dict(packet_payload["artifact_ids"])

    lab_artifacts: dict[str, ArtifactRecord] = {}
    lab_payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in INTERNAL_READER_LAB_ARTIFACT_TYPES[:-1]:
        artifact = _artifact_from_packet(connection, artifact_ids, artifact_type)
        lab_artifacts[artifact_type] = artifact
        lab_payloads[artifact_type] = _artifact_payload(artifact)

    packet_artifact = _artifact_by_path(
        connection,
        run_id=run_id,
        artifact_path=reader_lab_packet_dir / "internal_reader_lab_packet.json",
    )
    if packet_artifact is not None:
        lab_artifacts["internal_reader_lab_packet"] = packet_artifact
        lab_payloads["internal_reader_lab_packet"] = packet_payload

    source_texts = _load_source_texts(source_packet_dir)
    if not any(text.source_class == "abi_candidate" for text in source_texts):
        raise ValueError("source packet does not include an Abi candidate text")

    return RevisionSubject(
        run_id=run_id,
        reader_lab_packet_dir=reader_lab_packet_dir,
        reader_lab_packet_id=reader_lab_packet_id,
        reader_lab_packet_artifact_id=packet_artifact.id if packet_artifact is not None else None,
        source_packet_dir=source_packet_dir,
        source_packet_id=source_packet_id,
        lab_artifacts=lab_artifacts,
        lab_payloads=lab_payloads,
        source_texts=tuple(source_texts),
    )


def _artifact_from_packet(
    connection,
    artifact_ids: dict[str, object],
    artifact_type: str,
) -> ArtifactRecord:
    artifact_id = artifact_ids.get(artifact_type)
    if artifact_id is None:
        raise ValueError(f"reader-lab packet is missing artifact ID for {artifact_type}")
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


def _load_source_texts(source_packet_dir: Path) -> list[SubjectText]:
    bundle = read_json_file(source_packet_dir / "pilot_blinded_reader_bundle.json")["payload"]
    label_map = read_json_file(source_packet_dir / "pilot_neutral_label_map_private.json")[
        "payload"
    ]["label_map"]
    texts: list[SubjectText] = []
    for item in bundle["reader_items"]:
        label = str(item["label"])
        private_entry = label_map[label]
        source_class = str(private_entry["source_class"])
        if source_class == "strongest_rival_slot":
            continue
        texts.append(
            SubjectText(
                label=label,
                source_class=source_class,
                artifact_id=str(private_entry["artifact_id"]),
                text=str(item["text"]).strip(),
            )
        )
    return texts


def _build_subject_manifest(subject: RevisionSubject, *, fixture_only: bool = True) -> dict[str, Any]:
    return {
        "worker": (
            "autonomous_revision_subject_manifest_v1_fake"
            if fixture_only
            else "autonomous_revision_subject_manifest_v1_model_driver"
        ),
        "run_id": subject.run_id,
        "reader_lab_packet_dir": str(subject.reader_lab_packet_dir),
        "reader_lab_packet_id": subject.reader_lab_packet_id,
        "reader_lab_packet_artifact_id": subject.reader_lab_packet_artifact_id,
        "source_packet_dir": str(subject.source_packet_dir),
        "source_packet_id": subject.source_packet_id,
        "fixture_only": fixture_only,
        "not_human_data": True,
        "not_paper_validation": True,
        "no_phase_shift_claim": True,
        "texts": [
            {
                "label": text.label,
                "source_class": text.source_class,
                "artifact_id": text.artifact_id,
                "text_sha256": sha256_text(text.text),
                "word_count": text.word_count,
            }
            for text in subject.source_texts
        ],
        "reader_lab_evidence_artifacts": _reader_lab_evidence_artifacts(subject),
    }


def _build_selected_failure(subject: RevisionSubject) -> dict[str, Any]:
    diagnosis = subject.lab_payloads["internal_failure_diagnosis"]
    failures = list(diagnosis["failures"])
    selected = _choose_failure(failures)
    evidence_names = [str(name) for name in selected["evidence_artifacts"]]
    evidence_ids = {
        artifact_type: subject.lab_artifacts[artifact_type].id
        for artifact_type in evidence_names
        if artifact_type in subject.lab_artifacts
    }
    return {
        "worker": "selected_failure_diagnosis_v1_fake",
        "selection_rule": "first blocking failure with local recomposition leverage",
        "selected_failure_type": selected["failure_type"],
        "selected_diagnosis": selected["diagnosis"],
        "severity": selected["severity"],
        "all_failure_types_present": list(diagnosis["failure_types_present"]),
        "reader_lab_evidence_artifacts": evidence_ids,
        "source_failure_payload": selected,
        "fixture_only": True,
        "not_human_data": True,
    }


def _build_causal_handle_selection(
    subject: RevisionSubject,
    selected_failure: dict[str, Any],
) -> dict[str, Any]:
    plan_item = _plan_item_for_failure(
        subject.lab_payloads["targeted_recomposition_plan"],
        str(selected_failure["selected_failure_type"]),
    )
    candidate = subject.candidate_text
    quoted = _first_sentence(candidate.text)
    handle = str(plan_item["causal_handle"])
    target_contract = _controller_target_contract_for_selected_failure(
        subject,
        selected_failure,
    )
    patch_target = _first_allowed_patch_target(target_contract)
    payload = {
        "worker": "causal_handle_selector_v1_fake",
        "bounded_target": True,
        "target_count": 1,
        "selected_patch_target_id": str(patch_target["patch_target_id"]),
        "span_ref": {
            "source_label": candidate.label,
            "source_class": candidate.source_class,
            "artifact_id": candidate.artifact_id,
            "region": patch_target["allowed_span_ref"],
            "selection_basis": "smallest local handle connected to selected failure",
        },
        **target_contract,
        "allowed_patch_targets_source": "controller_owned",
        "quoted_text": quoted,
        "causal_handle": handle,
        "local_law_hypothesis": (
            "The opening object becomes useful only if it exerts a consequence before "
            "the artifact explains itself."
        ),
        "suspected_failure": selected_failure["selected_diagnosis"],
        "why_it_might_be_junk": (
            "The handle may become a pasted hint if it merely announces pressure."
        ),
        "why_it_might_be_treasure": (
            "The same handle may become necessary if it makes the opening return changed."
        ),
        "connotation_or_register_risk": (
            "Avoid process vocabulary and keep the change inside the object-field register."
        ),
        "variant_probe": "insert one concrete local consequence and compare reread pressure",
        "ablation_probe": "remove the inserted consequence and test whether reread pressure drops",
        "expected_reader_state_change": (
            "first read notices a concrete condition; reread treats it as planted cause"
        ),
        "uncertainty": "fake deterministic evidence cannot prove reader-state change",
        "protected_effects": list(plan_item["protected_effects"]),
        "forbidden_changes": list(plan_item["forbidden_changes"]),
        "fixture_only": True,
    }
    payload["patchable_spans"] = _patchable_spans_for_target(subject, patch_target)
    payload["patchable_spans_source"] = "controller_owned"
    return payload


def _build_revision_patch_proposal(
    subject: RevisionSubject,
    handle_selection: dict[str, Any],
) -> dict[str, Any]:
    original = subject.candidate_text.text
    first_sentence = _first_sentence(original)
    inserted_text = _revision_insertion_text()
    patch_target = _selected_allowed_patch_target(handle_selection)
    patch_span = _first_span_for_target_from_handle(
        handle_selection,
        str(patch_target["patch_target_id"]),
    )
    return {
        "worker": "revision_patch_proposal_v1_fake",
        "proposal_id": f"revision_patch_{sha256_text(first_sentence + inserted_text)[:12]}",
        "source_candidate_artifact_id": subject.candidate_text.artifact_id,
        "targeted_causal_handle": handle_selection["causal_handle"],
        "target_region_label": handle_selection["target_region_label"],
        "patches": [
            {
                "patch_id": "patch_01",
                "patch_span_id": str(patch_span["patch_span_id"]),
                "patch_target_id": str(patch_target["patch_target_id"]),
                "operation": "insert_after",
                "replacement_text": "",
                "inserted_text": inserted_text,
                "failure_addressed": handle_selection["suspected_failure"],
                "causal_handle_id": handle_selection["causal_handle"],
                "protected_effects_preserved": list(handle_selection["protected_effects"]),
                "forbidden_changes_respected": list(handle_selection["forbidden_changes"]),
                "rationale": "Patch the controller-selected span without rewriting the artifact.",
                "expected_reader_state_change": handle_selection[
                    "expected_reader_state_change"
                ],
                "requires_target_expansion": False,
                "target_expansion_reason": "",
                "confidence": 0.62,
                "uncertainty": "fake deterministic patch proposal cannot prove reader effect",
            }
        ],
        "bounded_patch_set": True,
        "full_rewrite": False,
        "target_region_expanded": False,
        "expanded_target_region": "",
        "expansion_reason": "",
        "protected_effects": list(handle_selection["protected_effects"]),
        "forbidden_changes_respected": list(handle_selection["forbidden_changes"]),
        "non_final": True,
        "candidate_only": True,
        "not_human_validated": True,
        "human_validated": False,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "fixture_only": True,
        "not_human_data": True,
    }


def _build_revision_diff_report(
    subject: RevisionSubject,
    handle_selection: dict[str, Any],
    revised_candidate: dict[str, Any],
) -> dict[str, Any]:
    original = subject.candidate_text.text
    revised = str(revised_candidate["text"])
    original_words = set(_words(original))
    revised_words = set(_words(revised))
    added_words = sorted(revised_words - original_words)[:20]
    removed_words = sorted(original_words - revised_words)[:20]
    target_region = str(handle_selection["span_ref"]["region"])
    target_contract = _target_contract_from_handle(handle_selection)
    return {
        "worker": "revision_diff_report_v1_fake",
        "full_rewrite": False,
        "bounded_change": True,
        "operation_type": "append_local_consequence",
        "target_region": target_region,
        **target_contract,
        "causal_handle": handle_selection["causal_handle"],
        "operation": {
            "type": "append_local_consequence",
            "target_region": handle_selection["span_ref"]["region"],
            "causal_handle": handle_selection["causal_handle"],
        },
        "original_excerpt": _first_sentence(original),
        "revised_excerpt": _first_two_sentences(revised),
        "changed_spans": _reported_changed_spans_for_texts(
            original,
            revised,
            target_region,
            (
                "The fake recomposer adds one local consequence without replacing the "
                "artifact's governing field."
            ),
        ),
        "target_region_expanded": False,
        "expanded_target_region": "",
        "expansion_reason": "",
        "target_expansion_justification": "",
        "added_words_sample": added_words,
        "removed_words_sample": removed_words,
        "original_word_count": len(_words(original)),
        "revised_word_count": len(_words(revised)),
        "protected_effects_preserved": list(handle_selection["protected_effects"]),
        "forbidden_changes_honored": list(handle_selection["forbidden_changes"]),
        "explanation": (
            "The fake recomposer adds one local consequence instead of replacing the "
            "artifact's governing field."
        ),
        "fixture_only": True,
    }


def _build_ablation_variant_set(
    subject: RevisionSubject,
    handle_selection: dict[str, Any],
    revised_candidate: dict[str, Any],
) -> dict[str, Any]:
    original = subject.candidate_text.text
    revised = str(revised_candidate["text"])
    handle = str(handle_selection["causal_handle"])
    operations = (
        (
            "remove_suspected_causal_handle",
            "Remove the inserted local consequence and expect reread pressure to drop.",
            original,
        ),
        (
            "replace_suspected_word_phrase_image",
            "Replace the pressure phrase with a plainer image and test register loss.",
            revised.replace("one ring of damp wood", "one pale mark"),
        ),
        (
            "flatten_metaphor",
            "Flatten the local pressure into explanation and watch for fake depth.",
            revised + " This means the room has consequences.",
        ),
        (
            "move_motif_earlier_later",
            "Move the morning/table motif later and test whether opening pressure weakens.",
            _move_first_sentence_to_end(revised),
        ),
        (
            "remove_ending_echo",
            "Cut the final echo and test whether reread return still closes.",
            _remove_last_sentence(revised),
        ),
        (
            "restore_old_wording",
            "Restore old wording to check whether the new handle was necessary.",
            original,
        ),
        (
            "correct_or_normalize_irregularity",
            "Normalize the odd local pressure and test whether smoothness damages the field.",
            revised.replace("It did not explain the night", "The room was quiet"),
        ),
        (
            "damage_or_roughen_too_smooth_phrase",
            "Roughen a too-smooth phrase if local law needs friction.",
            revised.replace("room to the morning", "room to morning's uneven edge"),
        ),
    )
    return {
        "worker": "ablation_variant_set_v1_fake",
        "targeted_causal_handle": handle,
        "variants": [
            {
                "variant_id": f"variant_{index:02d}",
                "operation": operation,
                "variant_probe": description,
                "ablation_probe": "compare internal first-read/reread deltas against revised candidate",
                "text": text,
                "text_sha256": sha256_text(text),
                "executed": True,
                "expected_reader_state_change": _expected_ablation_change(operation),
                "uncertainty": "fake variant, not reader evidence",
            }
            for index, (operation, description, text) in enumerate(operations, start=1)
        ],
        "does_not_select_winner": True,
        "fixture_only": True,
    }


def _build_ablation_comparison(
    subject: RevisionSubject,
    ablation_variant_set: dict[str, Any],
) -> dict[str, Any]:
    candidate_terms = set(_words(subject.candidate_text.text))
    rows = []
    for variant in ablation_variant_set["variants"]:
        text = str(variant["text"])
        terms = set(_words(text))
        overlap = len(candidate_terms & terms)
        rows.append(
            {
                "row_id": f"comparison_{variant['variant_id']}",
                "executed_variant_id": variant["variant_id"],
                "planned_probe_id": None,
                "operation": variant["operation"],
                "planned_only": False,
                "evidence_basis": "actual_ablation_variant",
                "comparison_summary": (
                    "probe only; feature is neither good nor bad until the local field accepts it"
                ),
                "predicted_or_observed_effect": _variant_delta(str(variant["operation"])),
                "rationale": (
                    "executed fake variant with word overlap "
                    f"{overlap}; useful only if it isolates the handle without leakage"
                ),
                "not_human_data": True,
            }
        )
    return {
        "worker": "ablation_reread_comparator_v1_fake",
        "candidate_label": subject.candidate_text.label,
        "comparison_rows": rows,
        "summary": (
            "Ablations are probe variants only; fake comparison suggests the inserted local "
            "consequence needs another cycle before it can count as resolved."
        ),
        "fixture_only": True,
    }


def _build_old_new_rival_comparison(
    subject: RevisionSubject,
    revised_candidate: dict[str, Any],
    ablation_comparison: dict[str, Any],
    revised_candidate_artifact_id: str,
) -> dict[str, Any]:
    original_score = _score_text(subject.candidate_text.text)
    revised_score = _score_text(str(revised_candidate["text"]))
    rival = subject.strongest_rival
    rival_score = _score_text(rival.text) if rival is not None else None
    baseline_scores = [
        {
            "label": baseline.label,
            "source_class": baseline.source_class,
            "score": _score_text(baseline.text),
        }
        for baseline in subject.baselines
    ]
    rival_still_beats = None
    if rival_score is not None:
        rival_still_beats = int(rival_score["local_embodiment_score"]) >= int(
            revised_score["local_embodiment_score"]
        )
    return {
        "worker": "old_new_rival_comparator_v1_fake",
        "original_candidate": {
            "label": subject.candidate_text.label,
            "artifact_id": subject.candidate_text.artifact_id,
            "score": original_score,
        },
        "revised_candidate": {
            "artifact_id": revised_candidate_artifact_id,
            "score": revised_score,
            "non_final": True,
        },
        "strongest_rival_present": rival is not None,
        "strongest_rival": (
            {
                "label": rival.label,
                "artifact_id": rival.artifact_id,
                "score": rival_score,
            }
            if rival is not None
            else None
        ),
        "baseline_scores": baseline_scores,
        "reread_transformation_improved": int(
            revised_score["reread_transformation_score"]
        )
        >= int(original_score["reread_transformation_score"]),
        "opening_transformation_improved": True,
        "local_embodiment_improved": int(revised_score["local_embodiment_score"])
        >= int(original_score["local_embodiment_score"]),
        "overexplanation_decreased": True,
        "fake_depth_risk_decreased": False,
        "revised_candidate_became_more_schematic": False,
        "rival_still_beats_candidate": rival_still_beats,
        "another_revision_cycle_needed": True,
        "comparison_basis": "deterministic fake internal comparison, not human data",
        "ablation_summary": ablation_comparison["summary"],
        "judgment_provenance": _default_judgment_provenance(rival is not None),
        "judgment_rationale": _default_judgment_rationale(rival is not None),
        "fixture_only": True,
    }


def _build_local_law_case_note(
    handle_selection: dict[str, Any],
    old_new_comparison: dict[str, Any],
) -> dict[str, Any]:
    return {
        "worker": "local_law_case_note_v1_fake",
        "principle": (
            "No feature is globally good or bad; a feature becomes good only when "
            "necessary inside the local field, and bad when that field rejects it."
        ),
        "span_ref": handle_selection["span_ref"],
        "quoted_text": handle_selection["quoted_text"],
        "local_law_hypothesis": handle_selection["local_law_hypothesis"],
        "suspected_failure": handle_selection["suspected_failure"],
        "why_it_might_be_junk": handle_selection["why_it_might_be_junk"],
        "why_it_might_be_treasure": handle_selection["why_it_might_be_treasure"],
        "connotation_or_register_risk": handle_selection["connotation_or_register_risk"],
        "variant_probe": handle_selection["variant_probe"],
        "ablation_probe": handle_selection["ablation_probe"],
        "expected_reader_state_change": handle_selection["expected_reader_state_change"],
        "uncertainty": handle_selection["uncertainty"],
        "preserve_irregularity_rule": (
            "Correcting or smoothing is forbidden when the irregularity carries the local field."
        ),
        "comparison_result": {
            "another_revision_cycle_needed": old_new_comparison["another_revision_cycle_needed"],
            "rival_still_beats_candidate": old_new_comparison["rival_still_beats_candidate"],
        },
        "fixture_only": True,
    }


def _build_closed_loop_gate_report(
    *,
    subject: RevisionSubject,
    payloads: dict[str, dict[str, Any]],
    fixture_only: bool = True,
    integrity_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comparison = payloads["old_new_rival_comparison"]
    ablation_integrity = (integrity_report or {}).get("ablation", {})
    selected_failure_type = payloads["selected_failure_diagnosis"]["selected_failure_type"]
    unresolved = [f"selected failure remains provisional: {selected_failure_type}"]
    if fixture_only:
        unresolved.append("closed-loop comparison is deterministic fixture evidence")
    if not ablation_integrity.get("comparison_actually_evaluated", False):
        unresolved.append("ablation comparison is predicted-only, not counterfactual proof")
    if comparison["rival_still_beats_candidate"] is True:
        unresolved.append("strongest rival still matches or beats revised candidate")
    if comparison["another_revision_cycle_needed"]:
        unresolved.append("another autonomous revision cycle is needed")

    gate_results = [
        _gate_result("autonomous_candidate_packet_exists", True),
        _gate_result("counterfactual_ablation_plan_or_result_exists", True),
        _gate_result(
            "rival_preservation_present",
            subject.strongest_rival is not None,
            ["strongest rival remains absent"] if subject.strongest_rival is None else [],
        ),
        _gate_result(
            "no_fixture_only_core_evidence",
            not fixture_only,
            (
                ["autonomous closed-loop revision v1 fake mode is fixture-only"]
                if fixture_only
                else []
            ),
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            unresolved,
        ),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator approval is intentionally absent"],
            record=False,
        ),
    ]
    failed = [
        result["gate_name"]
        for result in gate_results
        if result["record"] and not result["passed"]
    ]
    missing = [result["gate_name"] for result in gate_results if not result["record"]]
    return {
        "worker": (
            "autonomous_closed_loop_gate_report_v1_fake"
            if fixture_only
            else "autonomous_closed_loop_gate_report_v1_controller"
        ),
        "profile": "autonomous_creative_candidate",
        "eligible": False,
        "passed": False,
        "required_gates": list(AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES),
        "gate_results": gate_results,
        "failed_gates": failed,
        "missing_gates": missing,
        "useful_internal_progress": [
            "selected a failure diagnosis",
            "selected one bounded causal handle",
            "created a non-final revised candidate",
            "created ablation probes",
            "compared old/new/rival internally",
        ],
        "fixture_fake_evidence": fixture_only,
        "integrity_report": integrity_report or {},
        "ablation_evidence": {
            "ablation_plan_exists": "counterfactual_ablation_plan" in subject.lab_artifacts,
            "ablation_variants_executed": bool(
                ablation_integrity.get("executed_variant_count", 0)
            ),
            "ablation_variant_count": int(ablation_integrity.get("variant_count", 0)),
            "executed_ablation_variant_count": int(
                ablation_integrity.get("executed_variant_count", 0)
            ),
            "ablation_comparison_predicted_only": bool(
                ablation_integrity.get("comparison_predicted_only", True)
            ),
            "ablation_comparison_actually_evaluated": bool(
                ablation_integrity.get("comparison_actually_evaluated", False)
            ),
            "planned_only_comparison_row_count": int(
                ablation_integrity.get("planned_only_row_count", 0)
            ),
            "planned_only_ablation_probe_count": int(
                ablation_integrity.get("planned_only_row_count", 0)
            ),
            "executed_comparison_row_count": int(
                ablation_integrity.get("executed_row_count", 0)
            ),
            "predicted_only_comparison_row_count": int(
                ablation_integrity.get("predicted_row_count", 0)
            ),
            "actual_ablation_comparison_evidence_count": int(
                ablation_integrity.get("actual_evaluation_row_count", 0)
            ),
        },
        "unresolved_blockers": unresolved,
        "rival_still_stronger": comparison["rival_still_beats_candidate"],
        "needs_another_cycle": comparison["another_revision_cycle_needed"],
        "eligible_only_when": [
            "core evidence is non-fixture",
            "unresolved internal blockers are cleared",
            "rival pressure is preserved and no longer blocking",
            "internal operator approval is explicitly recorded",
        ],
        "final_gates_marked_passed": [],
        "human_validation_required": False,
        "paper_validation_required": False,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "summary_verdict": (
            "Closed-loop revision created internal repair evidence, but unresolved "
            "blockers and missing operator approval keep autonomous finalization refused."
            if not fixture_only
            else (
                "Closed-loop revision created internal repair evidence, but fake fixture "
                "mode, unresolved blockers, and missing operator approval keep "
                "autonomous finalization refused."
            )
        ),
        "fixture_only": fixture_only,
    }


def _build_packet_summary(
    *,
    subject: RevisionSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    fixture_only: bool = True,
    model_results: list[ModelDriverResult] | None = None,
    model: str | None = None,
    integrity_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate_report = payloads["autonomous_closed_loop_gate_report"]
    return {
        "worker": (
            "autonomous_closed_loop_packet_v1_fake"
            if fixture_only
            else "autonomous_closed_loop_packet_v1_model_driver"
        ),
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "reader_lab_packet_id": subject.reader_lab_packet_id,
        "reader_lab_packet_dir": str(subject.reader_lab_packet_dir),
        "source_packet_id": subject.source_packet_id,
        "source_packet_dir": str(subject.source_packet_dir),
        "artifact_types": list(AUTONOMOUS_REVISION_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "candidate_label": subject.candidate_text.label,
        "strongest_rival_present": subject.strongest_rival is not None,
        "autonomous_profile_eligible": False,
        "failed_gates": list(gate_report["failed_gates"]),
        "missing_gates": list(gate_report["missing_gates"]),
        "final_gates_marked_passed": [],
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": fixture_only,
        "integrity_report": integrity_report or {},
        "model": model,
        "model_call_ids": [
            result.model_call.id for result in (model_results or [])
        ],
        "model_artifact_types": [
            schema.artifact_type for schema in AUTONOMOUS_REVISION_MODEL_SCHEMAS
        ],
    }


def _record_revision_gates(
    *,
    connection,
    run_id: str,
    gate_report: dict[str, Any],
) -> list[GateRecord]:
    records = []
    for gate_result in gate_report["gate_results"]:
        if not gate_result["record"]:
            continue
        records.append(
            record_gate(
                connection,
                run_id=run_id,
                gate_name=str(gate_result["gate_name"]),
                passed=bool(gate_result["passed"]),
                blocking_defects=list(gate_result["blocking_defects"]),
                lineage_id=None,
            )
        )
    return records


def _summary_payload(
    *,
    run_id: str,
    packet_dir: Path,
    reader_lab_packet_dir: Path,
    client_name: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    gate_records: list[GateRecord],
    accepted: bool,
    message: str | None,
    model_results: list[ModelDriverResult] | None = None,
    model: str | None = None,
) -> dict[str, object]:
    model_results = list(model_results or [])
    return {
        "accepted": accepted,
        "refused": False,
        "client": client_name,
        "model": model,
        "run_id": run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "reader_lab_packet_dir": str(reader_lab_packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "required_artifact_types": list(AUTONOMOUS_REVISION_ARTIFACT_TYPES),
        "counts": {
            "autonomous_revision_artifacts": len(artifacts),
            "required_autonomous_revision_artifacts": len(AUTONOMOUS_REVISION_ARTIFACT_TYPES),
            "model_calls": len(model_results),
            "recorded_autonomous_gates": len(gate_records),
        },
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "parsed_model_artifact_ids": {
            result.model_call.schema_name: result.parsed_artifact.id
            for result in model_results
            if result.parsed_artifact is not None
        },
        "gate_report": payloads.get("autonomous_closed_loop_gate_report"),
        "gate_records": [
            {
                "gate_name": record.gate_name,
                "passed": record.passed,
                "blocking_defects": record.blocking_defects,
            }
            for record in gate_records
        ],
        "message": message,
    }


def _refusal(
    *,
    client_name: str,
    model: str | None,
    reader_lab_packet: Path | str,
    message: str,
) -> AutonomousRevisionResult:
    return AutonomousRevisionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "reader_lab_packet": str(reader_lab_packet),
            "artifact_ids": {},
            "artifact_paths": {},
            "counts": {"model_calls": 0},
            "message": message,
        },
    )


def _subject_parent_ids(subject: RevisionSubject) -> list[str]:
    parent_ids = [artifact.id for artifact in subject.lab_artifacts.values()]
    parent_ids.extend(text.artifact_id for text in subject.source_texts)
    return sorted(set(parent_ids))


def _reader_lab_evidence_artifacts(subject: RevisionSubject) -> dict[str, str]:
    return {
        artifact_type: artifact.id
        for artifact_type, artifact in subject.lab_artifacts.items()
        if artifact_type in INTERNAL_READER_LAB_ARTIFACT_TYPES
    }


def _choose_failure(failures: list[dict[str, Any]]) -> dict[str, Any]:
    priority = (
        "underplanted",
        "fake_depth",
        "paraphrase_capture",
        "rival_stronger_local_embodiment",
        "cadence_or_register_damage",
    )
    by_type = {str(failure["failure_type"]): failure for failure in failures}
    for failure_type in priority:
        if failure_type in by_type:
            return by_type[failure_type]
    if not failures:
        raise ValueError("reader-lab failure diagnosis contains no failures")
    return failures[0]


def _plan_item_for_failure(recomposition_plan: dict[str, Any], failure_type: str) -> dict[str, Any]:
    for plan_item in recomposition_plan["plan_items"]:
        if str(plan_item["failure_being_addressed"]) == failure_type:
            return plan_item
    plan_items = list(recomposition_plan["plan_items"])
    if not plan_items:
        raise ValueError("targeted recomposition plan contains no plan items")
    return plan_items[0]


def _bounded_revision(original: str) -> str:
    sentences = _sentences(original)
    insertion = _revision_insertion_text()
    if not sentences:
        return insertion
    if insertion.lower() in original.lower():
        return original
    first = sentences[0]
    remainder = original[len(first) :].strip()
    if remainder:
        return f"{first} {insertion} {remainder}".strip()
    return f"{first} {insertion}"


def _revision_insertion_text() -> str:
    return (
        "One ring of damp wood had darkened beneath the table leg. "
        "It did not explain the night; it made the room answer to the morning."
    )


def _move_first_sentence_to_end(text: str) -> str:
    sentences = _sentences(text)
    if len(sentences) < 2:
        return text
    return " ".join(sentences[1:] + sentences[:1])


def _remove_last_sentence(text: str) -> str:
    sentences = _sentences(text)
    if len(sentences) < 2:
        return text
    return " ".join(sentences[:-1])


def _expected_ablation_change(operation: str) -> str:
    changes = {
        "remove_suspected_causal_handle": "reread pressure should fall if handle is necessary",
        "replace_suspected_word_phrase_image": "register may flatten or become clearer",
        "flatten_metaphor": "overexplanation and fake-depth risk should rise",
        "move_motif_earlier_later": "opening transformation may weaken",
        "remove_ending_echo": "closure pressure may no longer return to the opening",
        "restore_old_wording": "tests whether revision improved anything locally",
        "correct_or_normalize_irregularity": "smoothness may damage useful friction",
        "damage_or_roughen_too_smooth_phrase": "roughness may help only if locally necessary",
    }
    return changes.get(operation, "unknown local-law effect")


def _variant_delta(operation: str) -> str:
    if operation in {"remove_suspected_causal_handle", "restore_old_wording"}:
        return "negative_if_revision_handle_is_real"
    if operation == "flatten_metaphor":
        return "negative_from_scaffold_leakage"
    if operation == "damage_or_roughen_too_smooth_phrase":
        return "uncertain_local_friction_probe"
    return "uncertain_probe"


def _score_text(text: str) -> dict[str, object]:
    retained = _retained_images(text)
    words = len(_words(text))
    process_penalty = 1 if _contains(text, ("claim", "source manifest", "final gates")) else 0
    return {
        "first_read_clarity_score": min(10, 4 + len(retained)),
        "reread_transformation_score": min(10, 3 + len(retained) + (1 if words > 60 else 0)),
        "local_embodiment_score": min(10, 3 + len(retained) - process_penalty),
        "compression_score": max(1, min(10, 10 - abs(words - 120) // 40)),
    }


def _default_judgment_provenance(strongest_rival_present: bool) -> dict[str, list[str]]:
    rival_sources = (
        ["revised_candidate_text", "strongest_rival_text"]
        if strongest_rival_present
        else ["revised_candidate_text", "prior_reader_lab_evidence"]
    )
    return {
        "reread_transformation_improved": [
            "original_candidate_text",
            "revised_candidate_text",
            "predicted_ablation_effect",
            "prior_reader_lab_evidence",
            "ablation_reread_comparison",
        ],
        "opening_transformation_improved": [
            "original_candidate_text",
            "revised_candidate_text",
            "revision_diff_report",
        ],
        "local_embodiment_improved": [
            "original_candidate_text",
            "revised_candidate_text",
            "strongest_rival_text",
        ]
        if strongest_rival_present
        else ["original_candidate_text", "revised_candidate_text"],
        "overexplanation_decreased": [
            "original_candidate_text",
            "revised_candidate_text",
            "prior_reader_lab_evidence",
            "revision_diff_report",
        ],
        "fake_depth_risk_decreased": [
            "revised_candidate_text",
            "prior_reader_lab_evidence",
            "ablation_reread_comparison",
        ],
        "revised_candidate_became_more_schematic": [
            "revised_candidate_text",
            "prior_reader_lab_evidence",
            "revision_diff_report",
        ],
        "rival_still_beats_candidate": rival_sources,
        "another_revision_cycle_needed": [
            "revised_candidate_text",
            "actual_ablation_variant",
            "planned_ablation_probe",
            "predicted_ablation_effect",
            "prior_reader_lab_evidence",
        ],
    }


def _default_judgment_rationale(strongest_rival_present: bool) -> dict[str, str]:
    rival_rationale = (
        "The rival comparison remains active because the imported rival still supplies "
        "local embodiment pressure against the revised candidate."
        if strongest_rival_present
        else "No imported rival is present, so the judgment leans on revised text and "
        "prior internal reader-lab pressure."
    )
    return {
        "reread_transformation_improved": (
            "The revised text carries more reread pressure through concrete consequence, "
            "but the ablation comparison still treats this as provisional."
        ),
        "opening_transformation_improved": (
            "The opening is judged against the original and the diff report rather than "
            "against a free-form impression."
        ),
        "local_embodiment_improved": (
            "The local object-world is stronger when the revision keeps the room and "
            "table as pressure-bearing evidence."
        ),
        "overexplanation_decreased": (
            "The revision is credited only where it reduces explanatory declaration and "
            "lets the domestic field carry the point."
        ),
        "fake_depth_risk_decreased": (
            "Fake-depth risk is not treated as solved; the rationale notes pressure from "
            "reader-lab evidence and ablation comparison."
        ),
        "revised_candidate_became_more_schematic": (
            "The revised candidate is checked for schematic drift using the revision "
            "diff and local-law note."
        ),
        "rival_still_beats_candidate": rival_rationale,
        "another_revision_cycle_needed": (
            "Another cycle remains necessary because ablation probes and prior reader "
            "evidence do not yet prove the repair stable."
        ),
    }


def _retained_images(text: str) -> list[str]:
    image_terms = (
        "table",
        "morning",
        "window",
        "cup",
        "room",
        "light",
        "dust",
        "night",
        "wood",
        "silence",
        "ring",
        "pressure",
    )
    lowered = text.lower()
    retained = [term for term in image_terms if term in lowered]
    return retained[:6] or _words(text)[:3]


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


def _first_two_sentences(text: str) -> str:
    sentences = _sentences(text)
    return " ".join(sentences[:2]) if sentences else text[:240]


def _first_sentence(text: str) -> str:
    sentences = _sentences(text)
    return sentences[0] if sentences else text.strip()[:160]


def _sentences(text: str) -> list[str]:
    candidates = []
    for part in text.replace("!", ".").replace("?", ".").split("."):
        stripped = part.strip()
        if stripped:
            candidates.append(stripped + ".")
    return candidates


def _words(text: str) -> list[str]:
    return [word.strip(".,;:!?()[]{}\"'").lower() for word in text.split() if word.strip()]


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = config.root / resolved
    return resolved.resolve()
