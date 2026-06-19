"""Pilot artifact-set scaffold for Phase 16."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from abi.artifacts import ArtifactRecord, get_artifact
from abi.config import AbiConfig
from abi.controller.state import (
    PHASE16_FIRST_REAL_CANDIDATE_SET_ACTIVE_PHASE,
    ensure_active_run,
    get_run,
    set_active_phase,
)
from abi.db import connect
from abi.hashing import sha256_file, sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_driver import ModelClient, ModelDriver, ModelDriverResult, WorkerRequest
from abi.model_schemas import (
    PILOT_ABI_CANDIDATE_SCHEMA,
    PILOT_DIRECT_PROMPT_BASELINE_SCHEMA,
    PILOT_RAW_MODEL_BASELINE_SCHEMA,
    WorkerRole,
    WorkerSchema,
)
from abi.packets import PacketWriter, create_packet_dir, read_json_file


PILOT_ARTIFACT_SET_LINEAGE_ID = "phase16_first_real_candidate_set"
PILOT_ARTIFACT_SET_CLIENT_FAKE = "fake"
PILOT_ARTIFACT_SET_CLIENT_OPENAI = "openai"
PILOT_ARTIFACT_SET_CLIENTS = (
    PILOT_ARTIFACT_SET_CLIENT_FAKE,
    PILOT_ARTIFACT_SET_CLIENT_OPENAI,
)
PILOT_ARTIFACT_SET_MAX_MODEL_CALLS_DEFAULT = 36
PILOT_ARTIFACT_SET_REQUIRED_MODEL_CALLS = 0
PILOT_ARTIFACT_SET_OPENAI_MODEL_CALLS = 3
PILOT_ARTIFACT_SET_FAKE_MODEL = "fake-pilot-artifact-set-v1"
PILOT_READER_TEXT_MIN_WORDS = 500
PILOT_READER_TEXT_FORBIDDEN_TERMS = (
    "baseline component",
    "role:",
    "status:",
    "non-final",
    "validation",
    "final gates",
    "phase-shift claim",
    "source manifest",
    "artifact-set",
    "json object",
    "fixture",
    "model_call_id",
    "abi candidate",
    "direct prompt baseline",
    "raw model baseline",
    "metadata",
    "finalization",
)
PILOT_ARTIFACT_SET_ARTIFACT_TYPES = (
    "pilot_source_manifest",
    "pilot_generation_plan",
    "pilot_abi_candidate_ref",
    "pilot_direct_prompt_baseline",
    "pilot_raw_model_baseline",
    "pilot_strongest_rival_slot",
    "pilot_neutral_label_map_private",
    "pilot_blinded_reader_bundle",
    "pilot_artifact_set_manifest",
    "pilot_readiness_report",
    "pilot_packet",
)
PILOT_RIVAL_IMPORT_ARTIFACT_TYPE = "pilot_strongest_rival_import"
PILOT_RIVAL_DERIVED_ARTIFACT_TYPES = (
    PILOT_RIVAL_IMPORT_ARTIFACT_TYPE,
    "pilot_strongest_rival_slot",
    "pilot_neutral_label_map_private",
    "pilot_blinded_reader_bundle",
    "pilot_artifact_set_manifest",
    "pilot_readiness_report",
    "pilot_packet",
)


@dataclass(frozen=True)
class PilotArtifactSetResult:
    exit_code: int
    payload: dict[str, object]
    model_results: tuple[ModelDriverResult, ...] = ()


@dataclass(frozen=True)
class PilotRivalImportResult:
    exit_code: int
    payload: dict[str, object]


@dataclass(frozen=True)
class PilotModelWorkerSpec:
    schema: WorkerSchema
    worker_role: WorkerRole
    prompt_contract_id: str

    @property
    def artifact_type(self) -> str:
        return self.schema.artifact_type


PILOT_PROMPT_CONTRACT_PREFIX = "phase16.pilot_artifact_set"
PILOT_MODEL_WORKERS = (
    PilotModelWorkerSpec(
        schema=PILOT_ABI_CANDIDATE_SCHEMA,
        worker_role=WorkerRole.PILOT_ABI_CANDIDATE_BUILDER,
        prompt_contract_id=f"{PILOT_PROMPT_CONTRACT_PREFIX}.abi_candidate",
    ),
    PilotModelWorkerSpec(
        schema=PILOT_DIRECT_PROMPT_BASELINE_SCHEMA,
        worker_role=WorkerRole.PILOT_DIRECT_PROMPT_BASELINE_BUILDER,
        prompt_contract_id=f"{PILOT_PROMPT_CONTRACT_PREFIX}.direct_prompt_baseline",
    ),
    PilotModelWorkerSpec(
        schema=PILOT_RAW_MODEL_BASELINE_SCHEMA,
        worker_role=WorkerRole.PILOT_RAW_MODEL_BASELINE_BUILDER,
        prompt_contract_id=f"{PILOT_PROMPT_CONTRACT_PREFIX}.raw_model_baseline",
    ),
)


def run_pilot_artifact_set(
    config: AbiConfig,
    *,
    client_name: str,
    source_dir: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = PILOT_ARTIFACT_SET_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> PilotArtifactSetResult:
    if client_name not in PILOT_ARTIFACT_SET_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            source_dir=source_dir,
            message=f"Pilot artifact-set client is not available: {client_name}",
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < PILOT_ARTIFACT_SET_REQUIRED_MODEL_CALLS:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == PILOT_ARTIFACT_SET_CLIENT_OPENAI else None,
            source_dir=source_dir,
            message=(
                "Pilot artifact-set refused; max-model-calls "
                f"{max_model_calls} is below required budget "
                f"{PILOT_ARTIFACT_SET_REQUIRED_MODEL_CALLS}."
            ),
        )

    if client_name == PILOT_ARTIFACT_SET_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            source_dir=source_dir,
            message=(
                "Pilot artifact-set refused; pass --allow-live-model "
                "to opt in explicitly."
            ),
        )

    resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == PILOT_ARTIFACT_SET_CLIENT_OPENAI and not resolved_api_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            source_dir=source_dir,
            message=f"Pilot artifact-set refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    if (
        client_name == PILOT_ARTIFACT_SET_CLIENT_OPENAI
        and max_model_calls < PILOT_ARTIFACT_SET_OPENAI_MODEL_CALLS
    ):
        return _refusal(
            client_name=client_name,
            model=configured_model,
            source_dir=source_dir,
            message=(
                "Pilot artifact-set refused; max-model-calls "
                f"{max_model_calls} is below required OpenAI worker budget "
                f"{PILOT_ARTIFACT_SET_OPENAI_MODEL_CALLS}."
            ),
        )

    source_root = _resolve_source_dir(config, source_dir)
    source_scan = _scan_source_dir(config, source_root)
    if isinstance(source_scan, PilotArtifactSetResult):
        return source_scan

    run, _created = ensure_active_run(config)
    packet_dir = create_packet_dir(config.run_dir(run.id) / "pilot_artifact_set")
    model_name = (
        configured_model
        if client_name == PILOT_ARTIFACT_SET_CLIENT_OPENAI
        else PILOT_ARTIFACT_SET_FAKE_MODEL
    )
    model_client = None
    if client_name == PILOT_ARTIFACT_SET_CLIENT_OPENAI:
        factory = client_factory or _default_openai_client_factory
        model_client = factory(configured_model)

    return _write_pilot_packet(
        config=config,
        run_id=run.id,
        packet_dir=packet_dir,
        source_files=source_scan,
        client_name=client_name,
        model=model_name,
        max_model_calls=max_model_calls,
        fixture_only=client_name == PILOT_ARTIFACT_SET_CLIENT_FAKE,
        source_dir=source_root,
        model_client=model_client,
    )


def import_pilot_rival(
    config: AbiConfig,
    *,
    packet_dir: Path | str,
    rival_file: Path | str,
) -> PilotRivalImportResult:
    source_packet_dir = _resolve_path(config, packet_dir)
    rival_path = _resolve_path(config, rival_file)
    if not source_packet_dir.exists() or not source_packet_dir.is_dir():
        return _rival_import_refusal(
            packet_dir=source_packet_dir,
            rival_file=rival_path,
            message=f"Pilot rival import refused; packet directory not found: {source_packet_dir}",
        )
    if not rival_path.exists() or not rival_path.is_file():
        return _rival_import_refusal(
            packet_dir=source_packet_dir,
            rival_file=rival_path,
            message=f"Pilot rival import refused; rival file not found: {rival_path}",
        )

    try:
        packet_envelope = read_json_file(source_packet_dir / "pilot_packet.json")
        packet_payload = packet_envelope["payload"]
        run_id = str(packet_envelope["run_id"])
        base_artifact_ids = dict(packet_payload["artifact_ids"])
    except (KeyError, TypeError, FileNotFoundError, json.JSONDecodeError) as error:
        return _rival_import_refusal(
            packet_dir=source_packet_dir,
            rival_file=rival_path,
            message=f"Pilot rival import refused; invalid pilot packet: {error}",
        )

    required_base_types = (
        "pilot_source_manifest",
        "pilot_generation_plan",
        "pilot_abi_candidate_ref",
        "pilot_direct_prompt_baseline",
        "pilot_raw_model_baseline",
        "pilot_strongest_rival_slot",
    )
    missing = [artifact_type for artifact_type in required_base_types if artifact_type not in base_artifact_ids]
    if missing:
        return _rival_import_refusal(
            packet_dir=source_packet_dir,
            rival_file=rival_path,
            message=f"Pilot rival import refused; missing base artifact IDs: {', '.join(missing)}",
        )

    rival_text = rival_path.read_text(encoding="utf-8", errors="replace").strip()
    if not rival_text:
        return _rival_import_refusal(
            packet_dir=source_packet_dir,
            rival_file=rival_path,
            message="Pilot rival import refused; rival text is empty.",
        )

    derived_packet_dir = create_packet_dir(source_packet_dir.parent)
    artifacts: dict[str, ArtifactRecord] = {}
    base_artifacts: dict[str, ArtifactRecord] = {}

    with connect(config.db_path) as connection:
        if get_run(connection, run_id) is None:
            return _rival_import_refusal(
                packet_dir=source_packet_dir,
                rival_file=rival_path,
                message=f"Pilot rival import refused; run is not registered: {run_id}",
            )
        set_active_phase(connection, run_id, PHASE16_FIRST_REAL_CANDIDATE_SET_ACTIVE_PHASE)
        for artifact_type, artifact_id_value in base_artifact_ids.items():
            artifact = get_artifact(connection, str(artifact_id_value))
            if artifact is not None:
                base_artifacts[artifact_type] = artifact

        missing_registered = [
            artifact_type for artifact_type in required_base_types if artifact_type not in base_artifacts
        ]
        if missing_registered:
            return _rival_import_refusal(
                packet_dir=source_packet_dir,
                rival_file=rival_path,
                message=(
                    "Pilot rival import refused; base artifacts are not registered: "
                    f"{', '.join(missing_registered)}"
                ),
            )
        try:
            base_payloads = _read_base_pilot_payloads(source_packet_dir, base_artifacts)
        except (KeyError, TypeError, FileNotFoundError, json.JSONDecodeError) as error:
            return _rival_import_refusal(
                packet_dir=source_packet_dir,
                rival_file=rival_path,
                message=f"Pilot rival import refused; invalid base artifact payloads: {error}",
            )
        payloads = dict(base_payloads)

        writer = PacketWriter(
            connection=connection,
            run_id=run_id,
            packet_dir=derived_packet_dir,
            lineage_id=PILOT_ARTIFACT_SET_LINEAGE_ID,
            created_by="pilot_import_rival_tool",
            fixture_only=False,
            model_call_id=None,
        )

        payloads[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE] = _build_rival_import_payload(
            config=config,
            rival_file=rival_path,
            rival_text=rival_text,
        )
        artifacts[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE] = writer.write_artifact(
            PILOT_RIVAL_IMPORT_ARTIFACT_TYPE,
            payloads[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE],
            parent_ids=[
                base_artifacts["pilot_source_manifest"].id,
                base_artifacts["pilot_strongest_rival_slot"].id,
            ],
        )

        payloads["pilot_strongest_rival_slot"] = _build_imported_strongest_rival_slot_payload(
            rival_artifact_id=artifacts[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE].id,
            source_slot_artifact_id=base_artifacts["pilot_strongest_rival_slot"].id,
        )
        artifacts["pilot_strongest_rival_slot"] = writer.write_artifact(
            "pilot_strongest_rival_slot",
            payloads["pilot_strongest_rival_slot"],
            parent_ids=[
                base_artifacts["pilot_strongest_rival_slot"].id,
                artifacts[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE].id,
            ],
        )

        combined_artifacts = dict(base_artifacts)
        combined_artifacts.update(artifacts)
        payloads["pilot_neutral_label_map_private"] = _build_label_map_payload(
            artifacts=combined_artifacts,
            payloads=payloads,
        )
        artifacts["pilot_neutral_label_map_private"] = writer.write_artifact(
            "pilot_neutral_label_map_private",
            payloads["pilot_neutral_label_map_private"],
            parent_ids=[
                base_artifacts["pilot_abi_candidate_ref"].id,
                base_artifacts["pilot_direct_prompt_baseline"].id,
                base_artifacts["pilot_raw_model_baseline"].id,
                artifacts[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE].id,
                artifacts["pilot_strongest_rival_slot"].id,
            ],
        )

        payloads["pilot_blinded_reader_bundle"] = _build_blinded_bundle_payload(
            payloads=payloads,
        )
        artifacts["pilot_blinded_reader_bundle"] = writer.write_artifact(
            "pilot_blinded_reader_bundle",
            payloads["pilot_blinded_reader_bundle"],
            parent_ids=[artifacts["pilot_neutral_label_map_private"].id],
        )

        payloads["pilot_readiness_report"] = _build_readiness_report_payload(
            client_name=str(packet_payload.get("client", "imported")),
            fixture_only=False,
            payloads=payloads,
        )
        artifacts["pilot_readiness_report"] = writer.write_artifact(
            "pilot_readiness_report",
            payloads["pilot_readiness_report"],
            parent_ids=[
                artifacts["pilot_strongest_rival_slot"].id,
                artifacts["pilot_blinded_reader_bundle"].id,
            ],
        )

        combined_artifacts = _manifest_artifacts_for_rival_import(
            base_artifacts=base_artifacts,
            derived_artifacts=artifacts,
        )
        payloads["pilot_artifact_set_manifest"] = _build_artifact_set_manifest_payload(
            artifacts=combined_artifacts,
            payloads=payloads,
            source_files=list(base_payloads["pilot_source_manifest"].get("source_files", [])),
        )
        artifacts["pilot_artifact_set_manifest"] = writer.write_artifact(
            "pilot_artifact_set_manifest",
            payloads["pilot_artifact_set_manifest"],
            parent_ids=[
                base_artifacts["pilot_source_manifest"].id,
                artifacts["pilot_blinded_reader_bundle"].id,
                artifacts["pilot_readiness_report"].id,
                artifacts[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE].id,
            ],
        )

        combined_artifacts = _manifest_artifacts_for_rival_import(
            base_artifacts=base_artifacts,
            derived_artifacts=artifacts,
        )
        payloads["pilot_packet"] = _build_rival_import_packet_summary_payload(
            run_id=run_id,
            packet_dir=derived_packet_dir,
            source_packet_dir=source_packet_dir,
            source_packet_payload=packet_payload,
            artifacts=combined_artifacts,
            payloads=payloads,
        )
        artifacts["pilot_packet"] = writer.write_artifact(
            "pilot_packet",
            payloads["pilot_packet"],
            parent_ids=[
                base_artifacts["pilot_source_manifest"].id,
                base_artifacts["pilot_generation_plan"].id,
                base_artifacts["pilot_abi_candidate_ref"].id,
                base_artifacts["pilot_direct_prompt_baseline"].id,
                base_artifacts["pilot_raw_model_baseline"].id,
                artifacts[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE].id,
                artifacts["pilot_strongest_rival_slot"].id,
                artifacts["pilot_neutral_label_map_private"].id,
                artifacts["pilot_blinded_reader_bundle"].id,
                artifacts["pilot_artifact_set_manifest"].id,
                artifacts["pilot_readiness_report"].id,
            ],
        )

    combined_artifacts = dict(base_artifacts)
    combined_artifacts.update(artifacts)
    return PilotRivalImportResult(
        exit_code=0,
        payload=_rival_import_summary_payload(
            run_id=run_id,
            source_packet_dir=source_packet_dir,
            derived_packet_dir=derived_packet_dir,
            rival_file=rival_path,
            artifacts=combined_artifacts,
            new_artifacts=artifacts,
            payloads=payloads,
            accepted=True,
            message=None,
        ),
    )


def _write_pilot_packet(
    *,
    config: AbiConfig,
    run_id: str,
    packet_dir: Path,
    source_files: list[dict[str, object]],
    client_name: str,
    model: str,
    max_model_calls: int,
    fixture_only: bool,
    source_dir: Path,
    model_client: ModelClient | None,
) -> PilotArtifactSetResult:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, object]] = {}
    model_results: list[ModelDriverResult] = []
    planned_model_calls = (
        len(PILOT_MODEL_WORKERS)
        if client_name == PILOT_ARTIFACT_SET_CLIENT_OPENAI
        else 0
    )

    with connect(config.db_path) as connection:
        set_active_phase(connection, run_id, PHASE16_FIRST_REAL_CANDIDATE_SET_ACTIVE_PHASE)
        writer = PacketWriter(
            connection=connection,
            run_id=run_id,
            packet_dir=packet_dir,
            lineage_id=PILOT_ARTIFACT_SET_LINEAGE_ID,
            created_by="pilot_artifact_set_scaffold",
            fixture_only=fixture_only,
            model_call_id=None,
        )

        payloads["pilot_source_manifest"] = _build_source_manifest_payload(
            config=config,
            source_dir=source_dir,
            source_files=source_files,
        )
        artifacts["pilot_source_manifest"] = writer.write_artifact(
            "pilot_source_manifest",
            payloads["pilot_source_manifest"],
            parent_ids=[],
        )

        payloads["pilot_generation_plan"] = _build_generation_plan_payload(
            client_name=client_name,
            model=model,
            max_model_calls=max_model_calls,
            model_calls_planned=planned_model_calls,
            fixture_only=fixture_only,
            source_manifest_artifact_id=artifacts["pilot_source_manifest"].id,
        )
        artifacts["pilot_generation_plan"] = writer.write_artifact(
            "pilot_generation_plan",
            payloads["pilot_generation_plan"],
            parent_ids=[artifacts["pilot_source_manifest"].id],
        )

        if client_name == PILOT_ARTIFACT_SET_CLIENT_OPENAI:
            connection.commit()
            if model_client is None:
                return _refusal(
                    client_name=client_name,
                    model=model,
                    source_dir=source_dir,
                    message="Pilot artifact-set refused; OpenAI model client is unavailable.",
                )
            model_results.extend(
                _run_pilot_model_calls(
                    config=config,
                    run_id=run_id,
                    packet_dir=packet_dir,
                    source_dir=source_dir,
                    source_files=source_files,
                    source_manifest_artifact_id=artifacts["pilot_source_manifest"].id,
                    generation_plan_artifact_id=artifacts["pilot_generation_plan"].id,
                    model_client=model_client,
                    max_model_calls=max_model_calls,
                )
            )
            for result in model_results:
                if (
                    not result.accepted
                    or result.parsed_artifact is None
                    or result.parsed_payload is None
                ):
                    return _failure_result(
                        client_name=client_name,
                        model=model,
                        run_id=run_id,
                        packet_dir=str(packet_dir),
                        source_dir=source_dir,
                        artifacts=artifacts,
                        payloads=payloads,
                        model_results=model_results,
                        max_model_calls=max_model_calls,
                        message="Pilot artifact-set stopped by model-call failure.",
                    )
                artifacts[result.parsed_artifact.type] = result.parsed_artifact
                payloads[result.parsed_artifact.type] = result.parsed_payload
            reader_validation_error = _reader_facing_text_validation_error(
                payloads=payloads,
                min_words=PILOT_READER_TEXT_MIN_WORDS,
            )
            if reader_validation_error is not None:
                return _failure_result(
                    client_name=client_name,
                    model=model,
                    run_id=run_id,
                    packet_dir=str(packet_dir),
                    source_dir=source_dir,
                    artifacts=artifacts,
                    payloads=payloads,
                    model_results=model_results,
                    max_model_calls=max_model_calls,
                    message=(
                        "Pilot artifact-set reader-facing text validation failed: "
                        f"{reader_validation_error}"
                    ),
                )
        else:
            payloads["pilot_abi_candidate_ref"] = _build_candidate_payload(
                source_files=source_files,
                client_name=client_name,
                fixture_only=fixture_only,
            )
            artifacts["pilot_abi_candidate_ref"] = writer.write_artifact(
                "pilot_abi_candidate_ref",
                payloads["pilot_abi_candidate_ref"],
                parent_ids=[
                    artifacts["pilot_source_manifest"].id,
                    artifacts["pilot_generation_plan"].id,
                ],
            )

            payloads["pilot_direct_prompt_baseline"] = _build_direct_baseline_payload(
                source_files=source_files,
                fixture_only=fixture_only,
            )
            artifacts["pilot_direct_prompt_baseline"] = writer.write_artifact(
                "pilot_direct_prompt_baseline",
                payloads["pilot_direct_prompt_baseline"],
                parent_ids=[
                    artifacts["pilot_source_manifest"].id,
                    artifacts["pilot_generation_plan"].id,
                ],
            )

            payloads["pilot_raw_model_baseline"] = _build_raw_baseline_payload(
                source_files=source_files,
                client_name=client_name,
                model=model,
                fixture_only=fixture_only,
            )
            artifacts["pilot_raw_model_baseline"] = writer.write_artifact(
                "pilot_raw_model_baseline",
                payloads["pilot_raw_model_baseline"],
                parent_ids=[
                    artifacts["pilot_source_manifest"].id,
                    artifacts["pilot_generation_plan"].id,
                ],
            )

        payloads["pilot_strongest_rival_slot"] = _build_strongest_rival_slot_payload()
        artifacts["pilot_strongest_rival_slot"] = writer.write_artifact(
            "pilot_strongest_rival_slot",
            payloads["pilot_strongest_rival_slot"],
            parent_ids=[artifacts["pilot_source_manifest"].id],
        )

        payloads["pilot_neutral_label_map_private"] = _build_label_map_payload(
            artifacts=artifacts,
            payloads=payloads,
        )
        artifacts["pilot_neutral_label_map_private"] = writer.write_artifact(
            "pilot_neutral_label_map_private",
            payloads["pilot_neutral_label_map_private"],
            parent_ids=[
                artifacts["pilot_abi_candidate_ref"].id,
                artifacts["pilot_direct_prompt_baseline"].id,
                artifacts["pilot_raw_model_baseline"].id,
                artifacts["pilot_strongest_rival_slot"].id,
            ],
        )

        payloads["pilot_blinded_reader_bundle"] = _build_blinded_bundle_payload(
            payloads=payloads,
        )
        artifacts["pilot_blinded_reader_bundle"] = writer.write_artifact(
            "pilot_blinded_reader_bundle",
            payloads["pilot_blinded_reader_bundle"],
            parent_ids=[artifacts["pilot_neutral_label_map_private"].id],
        )

        payloads["pilot_artifact_set_manifest"] = _build_artifact_set_manifest_payload(
            artifacts=artifacts,
            payloads=payloads,
            source_files=source_files,
        )
        artifacts["pilot_artifact_set_manifest"] = writer.write_artifact(
            "pilot_artifact_set_manifest",
            payloads["pilot_artifact_set_manifest"],
            parent_ids=[
                artifacts["pilot_source_manifest"].id,
                artifacts["pilot_blinded_reader_bundle"].id,
            ],
        )

        payloads["pilot_readiness_report"] = _build_readiness_report_payload(
            client_name=client_name,
            fixture_only=fixture_only,
            payloads=payloads,
        )
        artifacts["pilot_readiness_report"] = writer.write_artifact(
            "pilot_readiness_report",
            payloads["pilot_readiness_report"],
            parent_ids=[
                artifacts["pilot_artifact_set_manifest"].id,
                artifacts["pilot_strongest_rival_slot"].id,
            ],
        )

        payloads["pilot_packet"] = _build_packet_summary_payload(
            run_id=run_id,
            packet_dir=packet_dir,
            client_name=client_name,
            model=model,
            max_model_calls=max_model_calls,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
        )
        artifacts["pilot_packet"] = writer.write_artifact(
            "pilot_packet",
            payloads["pilot_packet"],
            parent_ids=[
                artifacts[artifact_type].id
                for artifact_type in PILOT_ARTIFACT_SET_ARTIFACT_TYPES[:-1]
            ],
        )

    return PilotArtifactSetResult(
        exit_code=0,
        payload=_summary_payload(
            client_name=client_name,
            model=model,
            run_id=run_id,
            packet_dir=str(packet_dir),
            source_dir=source_dir,
            artifacts=artifacts,
            payloads=payloads,
            max_model_calls=max_model_calls,
            model_results=model_results,
            refused=False,
            accepted=True,
            message=None,
        ),
        model_results=tuple(model_results),
    )


def _resolve_source_dir(config: AbiConfig, source_dir: Path | str) -> Path:
    path = Path(source_dir)
    if not path.is_absolute():
        path = config.root / path
    return path.resolve()


def _scan_source_dir(
    config: AbiConfig,
    source_dir: Path,
) -> list[dict[str, object]] | PilotArtifactSetResult:
    if not source_dir.exists() or not source_dir.is_dir():
        return _refusal(
            client_name=PILOT_ARTIFACT_SET_CLIENT_FAKE,
            model=PILOT_ARTIFACT_SET_FAKE_MODEL,
            source_dir=source_dir,
            message=f"Pilot artifact-set refused; source directory not found: {source_dir}",
        )
    files = sorted(path for path in source_dir.rglob("*") if path.is_file())
    if not files:
        return _refusal(
            client_name=PILOT_ARTIFACT_SET_CLIENT_FAKE,
            model=PILOT_ARTIFACT_SET_FAKE_MODEL,
            source_dir=source_dir,
            message=f"Pilot artifact-set refused; source directory has no files: {source_dir}",
        )
    return [
        {
            "relative_path": _relative_display(path, source_dir),
            "project_relative_path": _relative_display(path, config.root),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in files
    ]


def _run_pilot_model_calls(
    *,
    config: AbiConfig,
    run_id: str,
    packet_dir: Path,
    source_dir: Path,
    source_files: list[dict[str, object]],
    source_manifest_artifact_id: str,
    generation_plan_artifact_id: str,
    model_client: ModelClient,
    max_model_calls: int,
) -> list[ModelDriverResult]:
    results: list[ModelDriverResult] = []
    driver = ModelDriver(config=config, client=model_client)
    parent_ids = [source_manifest_artifact_id, generation_plan_artifact_id]
    input_text = _model_input_text(source_dir=source_dir, source_files=source_files)

    for index, worker in enumerate(PILOT_MODEL_WORKERS, start=1):
        if index > max_model_calls:
            break
        result = driver.run(
            WorkerRequest(
                run_id=run_id,
                worker_role=worker.worker_role,
                prompt_contract_id=worker.prompt_contract_id,
                schema=worker.schema,
                input_text=input_text,
                input_artifact_ids=parent_ids,
                input_packet_path=str(packet_dir),
                lineage_id=PILOT_ARTIFACT_SET_LINEAGE_ID,
                parent_ids=parent_ids,
                fixture_only=False,
                output_dir=str(packet_dir),
            )
        )
        results.append(result)
        if not result.accepted:
            break
    return results


def _build_source_manifest_payload(
    *,
    config: AbiConfig,
    source_dir: Path,
    source_files: list[dict[str, object]],
) -> dict[str, object]:
    source_set_hash = sha256_text(
        "\n".join(f"{item['relative_path']}:{item['sha256']}" for item in source_files)
    )
    return {
        "worker": "pilot_source_manifest_v1",
        "source_dir": _relative_display(source_dir, config.root),
        "source_count": len(source_files),
        "source_files": source_files,
        "source_set_hash": source_set_hash,
        "content_copied_to_docs": False,
        "private_source_policy": "inputs/private/ is gitignored; source files stay outside tracked docs.",
    }


def _manifest_artifacts_for_rival_import(
    *,
    base_artifacts: dict[str, ArtifactRecord],
    derived_artifacts: dict[str, ArtifactRecord],
) -> dict[str, ArtifactRecord]:
    artifact_types = (
        "pilot_source_manifest",
        "pilot_generation_plan",
        "pilot_abi_candidate_ref",
        "pilot_direct_prompt_baseline",
        "pilot_raw_model_baseline",
    )
    artifacts = {
        artifact_type: base_artifacts[artifact_type]
        for artifact_type in artifact_types
    }
    for artifact_type in (
        PILOT_RIVAL_IMPORT_ARTIFACT_TYPE,
        "pilot_strongest_rival_slot",
        "pilot_neutral_label_map_private",
        "pilot_blinded_reader_bundle",
        "pilot_readiness_report",
        "pilot_artifact_set_manifest",
    ):
        if artifact_type in derived_artifacts:
            artifacts[artifact_type] = derived_artifacts[artifact_type]
    return artifacts


def _build_generation_plan_payload(
    *,
    client_name: str,
    model: str,
    max_model_calls: int,
    model_calls_planned: int,
    fixture_only: bool,
    source_manifest_artifact_id: str,
) -> dict[str, object]:
    return {
        "worker": "pilot_generation_plan_v1",
        "client": client_name,
        "model": model,
        "source_manifest_artifact_id": source_manifest_artifact_id,
        "max_model_calls": max_model_calls,
        "model_calls_planned": model_calls_planned,
        "model_calls_used": model_calls_planned,
        "automatic_openai_call": False,
        "fixture_or_fake_mode": fixture_only,
        "artifact_set_arms": [
            "abi_candidate",
            "direct_prompt_baseline",
            "raw_model_baseline",
            "strongest_rival_slot",
        ],
        "claims_not_made": [
            "no phase-shift claim",
            "no human validation claim",
            "no final artifact claim",
            "no strongest-rival gate claim",
        ],
    }


def _build_candidate_payload(
    *,
    source_files: list[dict[str, object]],
    client_name: str,
    fixture_only: bool,
) -> dict[str, object]:
    return {
        "worker": "pilot_abi_candidate_ref_v1",
        "candidate_id": "pilot_candidate_scaffold_v1",
        "client": client_name,
        "text": _artifact_text(
            label="Pilot text",
            source_files=source_files,
            cadence="It keeps the source set visible without claiming a reader effect.",
        ),
        "source_file_count": len(source_files),
        "source_set_hashes": [str(item["sha256"]) for item in source_files],
        "fixture_or_fake": fixture_only,
        "non_final": True,
        "candidate_only": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "human_validated": False,
        "human_validation_claim": False,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
    }


def _build_direct_baseline_payload(
    *,
    source_files: list[dict[str, object]],
    fixture_only: bool,
) -> dict[str, object]:
    return {
        "worker": "pilot_direct_prompt_baseline_v1",
        "baseline_id": "pilot_direct_prompt_baseline_v1",
        "baseline_type": "direct_prompt",
        "text": _artifact_text(
            label="Pilot comparison text",
            source_files=source_files,
            cadence="It summarizes the visible source pressure in direct form.",
        ),
        "fixture_or_fake": fixture_only,
        "not_real_validation": True,
        "generation_rule": "deterministic scaffold baseline for pilot packet assembly",
        "final_gate_satisfied": False,
    }


def _build_raw_baseline_payload(
    *,
    source_files: list[dict[str, object]],
    client_name: str,
    model: str,
    fixture_only: bool,
) -> dict[str, object]:
    return {
        "worker": "pilot_raw_model_baseline_v1",
        "baseline_id": "pilot_raw_model_baseline_v1",
        "baseline_type": "raw_model",
        "client": client_name,
        "model": model,
        "text": _artifact_text(
            label="Pilot raw comparison text",
            source_files=source_files,
            cadence="It stands in for a raw-model baseline until a guarded live run is approved.",
        ),
        "fixture_or_fake": fixture_only,
        "not_real_validation": True,
        "raw_model_baseline_gate_satisfied": False,
        "model_calls_used": 0,
    }


def _build_strongest_rival_slot_payload() -> dict[str, object]:
    return {
        "worker": "pilot_strongest_rival_slot_v1",
        "slot_status": "unsatisfied",
        "placeholder_only": True,
        "imported_rival_artifact_id": None,
        "selection_required": True,
        "strongest_rival_gate_satisfied": False,
        "final_gate_satisfied": False,
        "operator_note": (
            "A real strongest rival must be imported or selected under the Phase 15 "
            "protocol before reader validation."
        ),
    }


def _build_rival_import_payload(
    *,
    config: AbiConfig,
    rival_file: Path,
    rival_text: str,
) -> dict[str, object]:
    return {
        "worker": "pilot_strongest_rival_import_v1",
        "source_class": "strongest_rival",
        "rival_file": _relative_display(rival_file, config.root),
        "rival_file_sha256": sha256_file(rival_file),
        "text": rival_text,
        "non_final": True,
        "candidate_only": False,
        "comparison_only": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "human_validated": False,
        "human_validation_claim": False,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "strongest_rival_comparison_passed": False,
        "final_gate_satisfied": False,
    }


def _build_imported_strongest_rival_slot_payload(
    *,
    rival_artifact_id: str,
    source_slot_artifact_id: str,
) -> dict[str, object]:
    return {
        "worker": "pilot_strongest_rival_slot_v1",
        "slot_status": "imported",
        "placeholder_only": False,
        "imported_rival_artifact_id": rival_artifact_id,
        "source_slot_artifact_id": source_slot_artifact_id,
        "selection_required": False,
        "strongest_rival_gate_satisfied": False,
        "strongest_rival_comparison_passed": False,
        "final_gate_satisfied": False,
        "operator_note": (
            "A strongest-rival text has been imported for blinded pilot comparison, "
            "but no strongest-rival comparison gate has been evaluated or passed."
        ),
    }


def _build_label_map_payload(
    *,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    rival_import = artifacts.get(PILOT_RIVAL_IMPORT_ARTIFACT_TYPE)
    text_d = (
        {
            "source_class": "strongest_rival",
            "artifact_id": rival_import.id,
            "included_for_readers": True,
        }
        if rival_import is not None
        else {
            "source_class": "strongest_rival_slot",
            "artifact_id": artifacts["pilot_strongest_rival_slot"].id,
            "included_for_readers": False,
        }
    )
    return {
        "worker": "pilot_neutral_label_map_private_v1",
        "private": True,
        "not_for_reader_distribution": True,
        "label_map": {
            "Text A": {
                "source_class": "abi_candidate",
                "artifact_id": artifacts["pilot_abi_candidate_ref"].id,
                "candidate_id": payloads["pilot_abi_candidate_ref"]["candidate_id"],
            },
            "Text B": {
                "source_class": "direct_prompt_baseline",
                "artifact_id": artifacts["pilot_direct_prompt_baseline"].id,
            },
            "Text C": {
                "source_class": "raw_model_baseline",
                "artifact_id": artifacts["pilot_raw_model_baseline"].id,
            },
            "Text D": text_d,
        },
        "blindness_rule": "Reader bundle must expose labels and text only, not source class.",
    }


def _build_blinded_bundle_payload(
    *,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    reader_items = [
        _reader_item("Text A", str(payloads["pilot_abi_candidate_ref"]["text"])),
        _reader_item("Text B", str(payloads["pilot_direct_prompt_baseline"]["text"])),
        _reader_item("Text C", str(payloads["pilot_raw_model_baseline"]["text"])),
    ]
    rival_import = payloads.get(PILOT_RIVAL_IMPORT_ARTIFACT_TYPE)
    if rival_import is not None:
        reader_items.append(_reader_item("Text D", str(rival_import["text"])))
    return {
        "reader_items": reader_items,
    }


def _build_artifact_set_manifest_payload(
    *,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    source_files: list[dict[str, object]],
) -> dict[str, object]:
    neutral_labels = ["Text A", "Text B", "Text C"]
    if PILOT_RIVAL_IMPORT_ARTIFACT_TYPE in artifacts:
        neutral_labels.append("Text D")
    return {
        "worker": "pilot_artifact_set_manifest_v1",
        "artifact_types": list(artifacts),
        "artifact_ids": {artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        "source_count": len(source_files),
        "neutral_labels": neutral_labels,
        "private_label_map_artifact_id": artifacts["pilot_neutral_label_map_private"].id,
        "blinded_reader_bundle_artifact_id": artifacts["pilot_blinded_reader_bundle"].id,
        "strongest_rival_import_artifact_id": artifacts.get(
            PILOT_RIVAL_IMPORT_ARTIFACT_TYPE
        ).id
        if PILOT_RIVAL_IMPORT_ARTIFACT_TYPE in artifacts
        else None,
        "candidate_flags": _candidate_flags(payloads["pilot_abi_candidate_ref"]),
        "baselines_fixture_or_fake": {
            "direct_prompt": payloads["pilot_direct_prompt_baseline"]["fixture_or_fake"],
            "raw_model": payloads["pilot_raw_model_baseline"]["fixture_or_fake"],
        },
        "strongest_rival_gate_satisfied": False,
        "finalization_eligible": False,
    }


def _build_readiness_report_payload(
    *,
    client_name: str,
    fixture_only: bool,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    candidate = payloads["pilot_abi_candidate_ref"]
    strongest = payloads["pilot_strongest_rival_slot"]
    defects = []
    if not candidate.get("non_final"):
        defects.append("candidate must remain non-final")
    if not candidate.get("not_human_validated"):
        defects.append("candidate must remain not human validated")
    if candidate.get("finalization_eligible"):
        defects.append("candidate must not be finalization eligible")
    if candidate.get("phase_shift_claim"):
        defects.append("candidate must not make a phase-shift claim")
    if strongest.get("strongest_rival_gate_satisfied"):
        defects.append("strongest-rival slot must not satisfy the strongest-rival gate")

    protocol_blockers = []
    if fixture_only:
        protocol_blockers.append("fake-mode baselines are fixture/fake engineering artifacts")
    if strongest.get("slot_status") == "imported":
        protocol_blockers.append("strongest rival imported; comparison gate not passed")
    else:
        protocol_blockers.append("strongest rival is not yet selected or imported")

    return {
        "worker": "pilot_readiness_report_v1",
        "client": client_name,
        "ready_for_protocol_dry_run": not defects,
        "ready_for_real_human_collection": False,
        "pilot_success_claim": False,
        "human_data_collected": False,
        "final_gates_marked_passed": [],
        "final_artifact_profile_eligible": False,
        "blocking_defects": defects,
        "protocol_blockers": protocol_blockers,
        "candidate_flags": _candidate_flags(candidate),
        "baseline_status": {
            "direct_prompt_fixture_or_fake": payloads["pilot_direct_prompt_baseline"][
                "fixture_or_fake"
            ],
            "raw_model_fixture_or_fake": payloads["pilot_raw_model_baseline"][
                "fixture_or_fake"
            ],
        },
        "strongest_rival_gate_satisfied": strongest["strongest_rival_gate_satisfied"],
        "summary_verdict": (
            "Pilot artifact set is assembled for protocol dry-run only; it does not "
            "collect human data or satisfy final-artifact gates."
        ),
    }


def _build_packet_summary_payload(
    *,
    run_id: str,
    packet_dir: Path,
    client_name: str,
    model: str,
    max_model_calls: int,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    candidate = payloads["pilot_abi_candidate_ref"]
    return {
        "worker": "pilot_packet_summary_v1",
        "run_id": run_id,
        "packet_id": packet_dir.name,
        "client": client_name,
        "model": model,
        "max_model_calls": max_model_calls,
        "model_calls_used": len(model_results),
        "model_call_ids": [result.model_call.id for result in model_results],
        "artifact_types": list(PILOT_ARTIFACT_SET_ARTIFACT_TYPES),
        "artifact_ids": {artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        "source_manifest_artifact_id": artifacts["pilot_source_manifest"].id,
        "abi_candidate_artifact_id": artifacts["pilot_abi_candidate_ref"].id,
        "direct_prompt_baseline_artifact_id": artifacts["pilot_direct_prompt_baseline"].id,
        "raw_model_baseline_artifact_id": artifacts["pilot_raw_model_baseline"].id,
        "strongest_rival_slot_artifact_id": artifacts["pilot_strongest_rival_slot"].id,
        "neutral_label_map_private_artifact_id": artifacts[
            "pilot_neutral_label_map_private"
        ].id,
        "blinded_reader_bundle_artifact_id": artifacts["pilot_blinded_reader_bundle"].id,
        "pilot_readiness_report_artifact_id": artifacts["pilot_readiness_report"].id,
        "candidate_flags": _candidate_flags(candidate),
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "human_data_collected": False,
        "final_gates_marked_passed": [],
        "strongest_rival_gate_satisfied": False,
    }


def _build_rival_import_packet_summary_payload(
    *,
    run_id: str,
    packet_dir: Path,
    source_packet_dir: Path,
    source_packet_payload: dict[str, object],
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    candidate = payloads["pilot_abi_candidate_ref"]
    return {
        "worker": "pilot_rival_import_packet_summary_v1",
        "run_id": run_id,
        "packet_id": packet_dir.name,
        "source_packet_id": source_packet_dir.name,
        "source_packet_dir": str(source_packet_dir),
        "client": source_packet_payload.get("client"),
        "model": source_packet_payload.get("model"),
        "model_calls_used": source_packet_payload.get("model_calls_used", 0),
        "model_call_ids": list(source_packet_payload.get("model_call_ids", [])),
        "artifact_types": list(artifacts),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "source_manifest_artifact_id": artifacts["pilot_source_manifest"].id,
        "abi_candidate_artifact_id": artifacts["pilot_abi_candidate_ref"].id,
        "direct_prompt_baseline_artifact_id": artifacts["pilot_direct_prompt_baseline"].id,
        "raw_model_baseline_artifact_id": artifacts["pilot_raw_model_baseline"].id,
        "strongest_rival_import_artifact_id": artifacts[PILOT_RIVAL_IMPORT_ARTIFACT_TYPE].id,
        "strongest_rival_slot_artifact_id": artifacts["pilot_strongest_rival_slot"].id,
        "neutral_label_map_private_artifact_id": artifacts[
            "pilot_neutral_label_map_private"
        ].id,
        "blinded_reader_bundle_artifact_id": artifacts["pilot_blinded_reader_bundle"].id,
        "pilot_readiness_report_artifact_id": artifacts["pilot_readiness_report"].id,
        "candidate_flags": _candidate_flags(candidate),
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "human_data_collected": False,
        "final_gates_marked_passed": [],
        "strongest_rival_gate_satisfied": False,
        "strongest_rival_comparison_passed": False,
    }


def _summary_payload(
    *,
    client_name: str,
    model: str | None,
    run_id: str | None,
    packet_dir: str | None,
    source_dir: Path | str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    max_model_calls: int,
    model_results: list[ModelDriverResult],
    refused: bool,
    accepted: bool,
    message: str | None,
) -> dict[str, object]:
    return {
        "refused": refused,
        "accepted": accepted,
        "client": client_name,
        "model": model,
        "run_id": run_id,
        "packet_id": Path(packet_dir).name if packet_dir else None,
        "packet_dir": packet_dir,
        "source_dir": str(source_dir),
        "required_artifact_types": list(PILOT_ARTIFACT_SET_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "pilot_artifacts": len(payloads),
            "required_pilot_artifacts": len(PILOT_ARTIFACT_SET_ARTIFACT_TYPES),
            "source_files": payloads.get("pilot_source_manifest", {}).get("source_count", 0),
            "model_calls": len(model_results),
            "max_model_calls": max_model_calls,
        },
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "model_call_ids": [result.model_call.id for result in model_results],
        "candidate_flags": _candidate_flags(payloads["pilot_abi_candidate_ref"])
        if "pilot_abi_candidate_ref" in payloads
        else {},
        "privacy": {
            "private_label_map_artifact_id": artifacts.get(
                "pilot_neutral_label_map_private"
            ).id
            if "pilot_neutral_label_map_private" in artifacts
            else None,
            "source_content_copied_to_tracked_docs": False,
            "private_source_dir_gitignored": True,
        },
        "readiness": payloads.get("pilot_readiness_report"),
        "message": message,
    }


def _rival_import_summary_payload(
    *,
    run_id: str,
    source_packet_dir: Path,
    derived_packet_dir: Path,
    rival_file: Path,
    artifacts: dict[str, ArtifactRecord],
    new_artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    accepted: bool,
    message: str | None,
) -> dict[str, object]:
    return {
        "accepted": accepted,
        "refused": False,
        "run_id": run_id,
        "source_packet_dir": str(source_packet_dir),
        "packet_id": derived_packet_dir.name,
        "packet_dir": str(derived_packet_dir),
        "rival_file": str(rival_file),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "new_artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in new_artifacts.items()
        },
        "new_artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in new_artifacts.items()
        },
        "counts": {
            "new_artifacts": len(new_artifacts),
            "reader_items": len(payloads["pilot_blinded_reader_bundle"]["reader_items"]),
        },
        "strongest_rival_slot": payloads["pilot_strongest_rival_slot"],
        "final_gates_marked_passed": [],
        "strongest_rival_comparison_passed": False,
        "message": message,
    }


def _rival_import_refusal(
    *,
    packet_dir: Path,
    rival_file: Path,
    message: str,
) -> PilotRivalImportResult:
    return PilotRivalImportResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "packet_dir": str(packet_dir),
            "rival_file": str(rival_file),
            "artifact_ids": {},
            "new_artifact_ids": {},
            "message": message,
        },
    )


def _read_base_pilot_payloads(
    packet_dir: Path,
    base_artifacts: dict[str, ArtifactRecord],
) -> dict[str, dict[str, object]]:
    artifact_types = (
        "pilot_source_manifest",
        "pilot_generation_plan",
        "pilot_abi_candidate_ref",
        "pilot_direct_prompt_baseline",
        "pilot_raw_model_baseline",
        "pilot_strongest_rival_slot",
    )
    payloads = {}
    for artifact_type in artifact_types:
        artifact = base_artifacts.get(artifact_type)
        path = Path(artifact.path) if artifact is not None else packet_dir / f"{artifact_type}.json"
        payloads[artifact_type] = read_json_file(path)["payload"]
    return payloads


def _failure_result(
    *,
    client_name: str,
    model: str,
    run_id: str,
    packet_dir: str,
    source_dir: Path | str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
    max_model_calls: int,
    message: str,
) -> PilotArtifactSetResult:
    return PilotArtifactSetResult(
        exit_code=1,
        payload=_summary_payload(
            client_name=client_name,
            model=model,
            run_id=run_id,
            packet_dir=packet_dir,
            source_dir=source_dir,
            artifacts=artifacts,
            payloads=payloads,
            max_model_calls=max_model_calls,
            model_results=model_results,
            refused=False,
            accepted=False,
            message=message,
        ),
        model_results=tuple(model_results),
    )


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = config.root / resolved
    return resolved.resolve()


def _refusal(
    *,
    client_name: str,
    model: str | None,
    source_dir: Path | str,
    message: str,
) -> PilotArtifactSetResult:
    return PilotArtifactSetResult(
        exit_code=1,
        payload={
            "refused": True,
            "accepted": False,
            "client": client_name,
            "model": model,
            "run_id": None,
            "packet_id": None,
            "packet_dir": None,
            "source_dir": str(source_dir),
            "artifact_ids": {},
            "model_calls": [],
            "message": message,
        },
    )


def _model_input_text(
    *,
    source_dir: Path,
    source_files: list[dict[str, object]],
) -> str:
    return json.dumps(
        {
            "source_files": source_files,
            "source_contents": _source_contents(source_dir=source_dir, source_files=source_files),
            "reader_facing_text_rules": {
                "target_words": "700-1200",
                "minimum_words": PILOT_READER_TEXT_MIN_WORDS,
                "must_be_prose_for_blind_readers": True,
                "forbidden_terms": list(PILOT_READER_TEXT_FORBIDDEN_TERMS),
            },
            "candidate_rules": {
                "non_final": True,
                "candidate_only": True,
                "not_human_validated": True,
                "not_finalization_eligible": True,
                "no_phase_shift_claim": True,
            },
            "baseline_rules": {
                "not_real_validation": True,
                "final_gates_satisfied": False,
            },
        },
        indent=2,
        sort_keys=True,
    )


def _source_contents(
    *,
    source_dir: Path,
    source_files: list[dict[str, object]],
) -> list[dict[str, object]]:
    contents = []
    for source_file in source_files:
        relative_path = str(source_file["relative_path"])
        path = source_dir / relative_path
        contents.append(
            {
                "relative_path": relative_path,
                "sha256": source_file["sha256"],
                "content": path.read_text(encoding="utf-8", errors="replace"),
            }
        )
    return contents


def _reader_facing_text_validation_error(
    *,
    payloads: dict[str, dict[str, object]],
    min_words: int,
) -> str | None:
    labels = {
        "pilot_abi_candidate_ref": "candidate",
        "pilot_direct_prompt_baseline": "direct baseline",
        "pilot_raw_model_baseline": "raw baseline",
    }
    for artifact_type, label in labels.items():
        text = str(payloads[artifact_type].get("text", ""))
        error = _reader_text_validation_error(text=text, label=label, min_words=min_words)
        if error is not None:
            return error
    return None


def _reader_text_validation_error(*, text: str, label: str, min_words: int) -> str | None:
    stripped = text.strip()
    if not stripped:
        return f"{label} text is empty"
    if stripped.startswith("{"):
        return f"{label} text starts with JSON object syntax"
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        pass
    else:
        return f"{label} text parses as JSON"

    word_count = len(re.findall(r"\b[\w'-]+\b", stripped))
    if word_count < min_words:
        return f"{label} text has {word_count} words; minimum is {min_words}"

    lowered = stripped.lower()
    for term in PILOT_READER_TEXT_FORBIDDEN_TERMS:
        if term in lowered:
            return f"{label} text contains scaffold leakage term: {term}"
    return None


def _artifact_text(
    *,
    label: str,
    source_files: list[dict[str, object]],
    cadence: str,
) -> str:
    names = ", ".join(str(item["relative_path"]) for item in source_files)
    digest = sha256_text("|".join(str(item["sha256"]) for item in source_files))[:12]
    return (
        f"{label} for source set {digest}. "
        f"The packet was assembled from {len(source_files)} frozen source file(s): {names}. "
        f"{cadence}"
    )


def _reader_item(label: str, text: str) -> dict[str, object]:
    return {
        "label": label,
        "text": text,
    }


def _candidate_flags(candidate_payload: dict[str, object]) -> dict[str, object]:
    return {
        "non_final": candidate_payload["non_final"],
        "candidate_only": candidate_payload["candidate_only"],
        "not_human_validated": candidate_payload["not_human_validated"],
        "not_finalization_eligible": candidate_payload["not_finalization_eligible"],
        "finalization_eligible": candidate_payload["finalization_eligible"],
        "human_validated": candidate_payload["human_validated"],
        "human_validation_claim": candidate_payload["human_validation_claim"],
        "phase_shift_claim": candidate_payload["phase_shift_claim"],
        "no_phase_shift_claim": candidate_payload["no_phase_shift_claim"],
    }


def _relative_display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)
