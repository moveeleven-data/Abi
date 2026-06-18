"""Guarded live Abi Ear packet pipeline for Phase 8."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os

from abi.artifacts import ArtifactRecord
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    PHASE8_LIVE_ABI_EAR_PACKET_ACTIVE_PHASE,
    ensure_active_run,
    set_active_phase,
)
from abi.db import connect
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_driver import ModelClient, ModelClientError, ModelDriver, ModelDriverResult
from abi.model_driver import WorkerRequest
from abi.model_schemas import (
    ABI_EAR_FIELD_MODEL_SCHEMA,
    ABI_EAR_GERM_ANALYSIS_SCHEMA,
    ABI_EAR_MOVES_SCHEMA,
    ABI_EAR_PROSE_INVENTIONS_SCHEMA,
    ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA,
    ABI_EAR_REFINED_INVENTION_SCHEMA,
    ABI_EAR_REREAD_TRACE_SCHEMA,
    ABI_EAR_VARIANTS_SCHEMA,
    LIVE_ABI_EAR_PACKET_MODEL_SCHEMAS,
    WorkerRole,
    WorkerSchema,
)
from abi.modules.abi_ear import (
    BENCHMARK_INPUT,
    build_benchmark_payloads,
    evaluate_gate_packet,
    report_ablation,
)
from abi.packets import PacketWriter, create_packet_dir


LIVE_ABI_EAR_PACKET_LINEAGE_ID = "phase8_live_abi_ear_packet"
LIVE_ABI_EAR_GATE_NAME = "live_abi_ear_packet_v1"
LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX = "phase8.live.abi_ear_packet"
LIVE_ABI_EAR_CLIENT_FAKE = "fake"
LIVE_ABI_EAR_CLIENT_OPENAI = "openai"
LIVE_ABI_EAR_CLIENTS = (LIVE_ABI_EAR_CLIENT_FAKE, LIVE_ABI_EAR_CLIENT_OPENAI)
LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT = 8
LIVE_ABI_EAR_FAKE_PROVIDER = "fake"
LIVE_ABI_EAR_FAKE_MODEL = "fake-live-abi-ear-packet-v1"
LIVE_ABI_EAR_ABLATION_ARTIFACT_TYPE = "live_abi_ear_ablation_report"
LIVE_ABI_EAR_GATE_ARTIFACT_TYPE = "live_abi_ear_gate_report"
LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE = "live_abi_ear_packet"
LIVE_ABI_EAR_PACKET_ARTIFACT_TYPES = tuple(
    schema.artifact_type for schema in LIVE_ABI_EAR_PACKET_MODEL_SCHEMAS
) + (
    LIVE_ABI_EAR_ABLATION_ARTIFACT_TYPE,
    LIVE_ABI_EAR_GATE_ARTIFACT_TYPE,
    LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE,
)


@dataclass(frozen=True)
class LiveAbiEarPacketResult:
    exit_code: int
    payload: dict[str, object]
    model_results: tuple[ModelDriverResult, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class LiveAbiEarPacketWorkerSpec:
    schema: WorkerSchema
    worker_role: WorkerRole
    prompt_contract_id: str
    parent_artifact_types: tuple[str, ...] = ()

    @property
    def artifact_type(self) -> str:
        return self.schema.artifact_type


LIVE_ABI_EAR_PACKET_WORKERS = (
    LiveAbiEarPacketWorkerSpec(
        schema=ABI_EAR_GERM_ANALYSIS_SCHEMA,
        worker_role=WorkerRole.ABI_EAR_GERM_ANALYZER,
        prompt_contract_id=f"{LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX}.germ_analysis",
    ),
    LiveAbiEarPacketWorkerSpec(
        schema=ABI_EAR_FIELD_MODEL_SCHEMA,
        worker_role=WorkerRole.ABI_EAR_FIELD_MODEL_BUILDER,
        prompt_contract_id=f"{LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX}.field_model",
        parent_artifact_types=(ABI_EAR_GERM_ANALYSIS_SCHEMA.artifact_type,),
    ),
    LiveAbiEarPacketWorkerSpec(
        schema=ABI_EAR_VARIANTS_SCHEMA,
        worker_role=WorkerRole.ABI_EAR_VARIANT_GENERATOR,
        prompt_contract_id=f"{LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX}.variants",
        parent_artifact_types=(ABI_EAR_GERM_ANALYSIS_SCHEMA.artifact_type,),
    ),
    LiveAbiEarPacketWorkerSpec(
        schema=ABI_EAR_MOVES_SCHEMA,
        worker_role=WorkerRole.ABI_EAR_MOVE_COMPOSER,
        prompt_contract_id=f"{LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX}.moves",
        parent_artifact_types=(ABI_EAR_FIELD_MODEL_SCHEMA.artifact_type,),
    ),
    LiveAbiEarPacketWorkerSpec(
        schema=ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA,
        worker_role=WorkerRole.ABI_EAR_MOVE_RANKER,
        prompt_contract_id=f"{LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX}.ranked_moves",
        parent_artifact_types=(
            ABI_EAR_MOVES_SCHEMA.artifact_type,
            ABI_EAR_FIELD_MODEL_SCHEMA.artifact_type,
        ),
    ),
    LiveAbiEarPacketWorkerSpec(
        schema=ABI_EAR_PROSE_INVENTIONS_SCHEMA,
        worker_role=WorkerRole.ABI_EAR_PROSE_INVENTOR,
        prompt_contract_id=f"{LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX}.prose_inventions",
        parent_artifact_types=(
            ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA.artifact_type,
            ABI_EAR_FIELD_MODEL_SCHEMA.artifact_type,
        ),
    ),
    LiveAbiEarPacketWorkerSpec(
        schema=ABI_EAR_REFINED_INVENTION_SCHEMA,
        worker_role=WorkerRole.ABI_EAR_REFINER,
        prompt_contract_id=f"{LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX}.refined_invention",
        parent_artifact_types=(
            ABI_EAR_PROSE_INVENTIONS_SCHEMA.artifact_type,
            ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA.artifact_type,
        ),
    ),
    LiveAbiEarPacketWorkerSpec(
        schema=ABI_EAR_REREAD_TRACE_SCHEMA,
        worker_role=WorkerRole.ABI_EAR_REREAD_TRACER,
        prompt_contract_id=f"{LIVE_ABI_EAR_PROMPT_CONTRACT_PREFIX}.reread_trace",
        parent_artifact_types=(
            ABI_EAR_REFINED_INVENTION_SCHEMA.artifact_type,
            ABI_EAR_GERM_ANALYSIS_SCHEMA.artifact_type,
            ABI_EAR_FIELD_MODEL_SCHEMA.artifact_type,
        ),
    ),
)


class FakeAbiEarPacketClient:
    provider = LIVE_ABI_EAR_FAKE_PROVIDER
    model = LIVE_ABI_EAR_FAKE_MODEL

    def __init__(
        self,
        *,
        mode: str = "valid",
        target_schema: WorkerSchema = ABI_EAR_VARIANTS_SCHEMA,
    ) -> None:
        self.mode = mode
        self.target_schema = target_schema
        self.payloads = _build_fake_model_payloads()

    def generate(self, request: WorkerRequest) -> str:
        if request.schema == self.target_schema and self.mode == "invalid":
            return "{not valid json"
        if request.schema == self.target_schema and self.mode == "failure":
            raise ModelClientError("simulated fake packet client failure")
        if self.mode not in ("valid", "invalid", "failure"):
            raise ModelClientError(f"unknown fake packet client mode: {self.mode}")
        payload = self.payloads.get(request.schema)
        if payload is None:
            raise ModelClientError(f"unsupported fake packet schema: {request.schema.name}")
        return _canonical_json(payload)


def run_live_abi_ear_packet_demo(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool = False,
    max_model_calls: int = LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    fake_mode: str = "valid",
    fake_target_schema: WorkerSchema = ABI_EAR_VARIANTS_SCHEMA,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> LiveAbiEarPacketResult:
    if client_name not in LIVE_ABI_EAR_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            message=f"Live Abi Ear packet client is not available: {client_name}",
        )

    planned_model_calls = len(LIVE_ABI_EAR_PACKET_WORKERS)
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < planned_model_calls:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == LIVE_ABI_EAR_CLIENT_OPENAI else None,
            message=(
                "Live Abi Ear packet command refused; max-model-calls "
                f"{max_model_calls} is below required budget {planned_model_calls}."
            ),
        )

    if client_name == LIVE_ABI_EAR_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=(
                "Live Abi Ear packet command refused; pass --allow-live-model "
                "to opt in explicitly."
            ),
        )

    resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == LIVE_ABI_EAR_CLIENT_OPENAI and not resolved_api_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=f"Live Abi Ear packet command refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    run, _ = ensure_active_run(config)
    packet_dir = create_packet_dir(config.run_dir(run.id) / "live_abi_ear")
    with connect(config.db_path) as connection:
        set_active_phase(connection, run.id, PHASE8_LIVE_ABI_EAR_PACKET_ACTIVE_PHASE)

    if client_name == LIVE_ABI_EAR_CLIENT_FAKE:
        client = FakeAbiEarPacketClient(mode=fake_mode, target_schema=fake_target_schema)
        fixture_only = True
    else:
        factory = client_factory or _default_openai_client_factory
        client = factory(configured_model)
        fixture_only = False

    return _run_packet_model_calls(
        config=config,
        run_id=run.id,
        packet_dir=str(packet_dir),
        client_name=client_name,
        model=configured_model if client_name == LIVE_ABI_EAR_CLIENT_OPENAI else client.model,
        model_client=client,
        fixture_only=fixture_only,
        max_model_calls=max_model_calls,
    )


def _run_packet_model_calls(
    *,
    config: AbiConfig,
    run_id: str,
    packet_dir: str,
    client_name: str,
    model: str,
    model_client: ModelClient,
    fixture_only: bool,
    max_model_calls: int,
) -> LiveAbiEarPacketResult:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, object]] = {}
    model_results: list[ModelDriverResult] = []
    driver = ModelDriver(config=config, client=model_client)

    for index, worker in enumerate(LIVE_ABI_EAR_PACKET_WORKERS, start=1):
        if index > max_model_calls:
            return _failure_result(
                client_name=client_name,
                model=model,
                run_id=run_id,
                packet_dir=packet_dir,
                message="Live Abi Ear packet command stopped by max-model-calls budget.",
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
            )
        parent_ids = [
            artifacts[artifact_type].id
            for artifact_type in worker.parent_artifact_types
            if artifact_type in artifacts
        ]
        result = driver.run(
            WorkerRequest(
                run_id=run_id,
                worker_role=worker.worker_role,
                prompt_contract_id=worker.prompt_contract_id,
                schema=worker.schema,
                input_text=BENCHMARK_INPUT,
                input_artifact_ids=parent_ids,
                input_packet_path=packet_dir,
                lineage_id=LIVE_ABI_EAR_PACKET_LINEAGE_ID,
                parent_ids=parent_ids,
                fixture_only=fixture_only,
                output_dir=packet_dir,
            )
        )
        model_results.append(result)
        if not result.accepted or result.parsed_artifact is None or result.parsed_payload is None:
            return _failure_result(
                client_name=client_name,
                model=model,
                run_id=run_id,
                packet_dir=packet_dir,
                message="Live Abi Ear packet command stopped by model-call failure.",
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
            )
        artifacts[worker.artifact_type] = result.parsed_artifact
        payloads[worker.artifact_type] = result.parsed_payload

    gate_record = _write_local_packet_artifacts(
        config=config,
        run_id=run_id,
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
        model_results=model_results,
        fixture_only=fixture_only,
    )
    return LiveAbiEarPacketResult(
        exit_code=0,
        payload=_summary_payload(
            client_name=client_name,
            model=model,
            run_id=run_id,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            refused=False,
            accepted=True,
            message=None,
        ),
        model_results=tuple(model_results),
        gate_record=gate_record,
    )


def _write_local_packet_artifacts(
    *,
    config: AbiConfig,
    run_id: str,
    packet_dir: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
    fixture_only: bool,
) -> GateRecord:
    ablation_report = report_ablation(
        payloads[ABI_EAR_REFINED_INVENTION_SCHEMA.artifact_type],
        BENCHMARK_INPUT,
        payloads[ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA.artifact_type],
        payloads[ABI_EAR_REREAD_TRACE_SCHEMA.artifact_type],
    )
    ablation_report["worker"] = "live_abi_ear_ablation_scaffold_v1"
    gate_report = evaluate_gate_packet(
        germ_analysis=payloads[ABI_EAR_GERM_ANALYSIS_SCHEMA.artifact_type],
        variants=payloads[ABI_EAR_VARIANTS_SCHEMA.artifact_type],
        field_model=payloads[ABI_EAR_FIELD_MODEL_SCHEMA.artifact_type],
        moves=payloads[ABI_EAR_MOVES_SCHEMA.artifact_type],
        ranked_move_sequence=payloads[ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA.artifact_type],
        prose_inventions=payloads[ABI_EAR_PROSE_INVENTIONS_SCHEMA.artifact_type],
        refined_invention=payloads[ABI_EAR_REFINED_INVENTION_SCHEMA.artifact_type],
        reread_trace=payloads[ABI_EAR_REREAD_TRACE_SCHEMA.artifact_type],
        ablation_report=ablation_report,
    )
    gate_report["worker"] = "live_abi_ear_gate_scaffold_v1"
    gate_report["gate_name"] = LIVE_ABI_EAR_GATE_NAME
    packet_summary = _build_packet_summary(
        artifacts=artifacts,
        payloads=payloads,
        gate_report=gate_report,
        model_results=model_results,
    )
    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=run_id,
            packet_dir=packet_dir,
            lineage_id=LIVE_ABI_EAR_PACKET_LINEAGE_ID,
            created_by="live_abi_ear_packet_scaffold",
            fixture_only=fixture_only,
        )
        artifacts[LIVE_ABI_EAR_ABLATION_ARTIFACT_TYPE] = writer.write_artifact(
            LIVE_ABI_EAR_ABLATION_ARTIFACT_TYPE,
            ablation_report,
            parent_ids=[
                artifacts[ABI_EAR_REFINED_INVENTION_SCHEMA.artifact_type].id,
                artifacts[ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA.artifact_type].id,
                artifacts[ABI_EAR_REREAD_TRACE_SCHEMA.artifact_type].id,
            ],
        )
        artifacts[LIVE_ABI_EAR_GATE_ARTIFACT_TYPE] = writer.write_artifact(
            LIVE_ABI_EAR_GATE_ARTIFACT_TYPE,
            gate_report,
            parent_ids=[
                artifacts[ABI_EAR_GERM_ANALYSIS_SCHEMA.artifact_type].id,
                artifacts[ABI_EAR_FIELD_MODEL_SCHEMA.artifact_type].id,
                artifacts[ABI_EAR_VARIANTS_SCHEMA.artifact_type].id,
                artifacts[ABI_EAR_MOVES_SCHEMA.artifact_type].id,
                artifacts[ABI_EAR_PROSE_INVENTIONS_SCHEMA.artifact_type].id,
                artifacts[LIVE_ABI_EAR_ABLATION_ARTIFACT_TYPE].id,
            ],
        )
        gate_record = record_gate(
            connection,
            run_id=run_id,
            gate_name=LIVE_ABI_EAR_GATE_NAME,
            passed=bool(gate_report["passed"]),
            blocking_defects=list(gate_report["blocking_defects"]),
            lineage_id=LIVE_ABI_EAR_PACKET_LINEAGE_ID,
        )
        packet_summary["gate_summary"] = {
            "gate_name": gate_report["gate_name"],
            "passed": gate_report["passed"],
            "blocking_defects": gate_report["blocking_defects"],
            "summary_verdict": gate_report["summary_verdict"],
        }
        artifacts[LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE] = writer.write_artifact(
            LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE,
            packet_summary,
            parent_ids=[artifacts[artifact_type].id for artifact_type in LIVE_ABI_EAR_PACKET_ARTIFACT_TYPES[:-1]],
        )
    payloads[LIVE_ABI_EAR_ABLATION_ARTIFACT_TYPE] = ablation_report
    payloads[LIVE_ABI_EAR_GATE_ARTIFACT_TYPE] = gate_report
    payloads[LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE] = packet_summary
    return gate_record


def _build_packet_summary(
    *,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    gate_report: dict[str, object],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    return {
        "worker": "live_abi_ear_packet_summarizer_v1",
        "benchmark_input": BENCHMARK_INPUT,
        "artifact_types": list(LIVE_ABI_EAR_PACKET_ARTIFACT_TYPES),
        "counts": {
            "word_forces": len(payloads[ABI_EAR_GERM_ANALYSIS_SCHEMA.artifact_type]["word_forces"]),
            "variants": len(payloads[ABI_EAR_VARIANTS_SCHEMA.artifact_type]["variants"]),
            "moves": len(payloads[ABI_EAR_MOVES_SCHEMA.artifact_type]["moves"]),
            "prose_inventions": len(
                payloads[ABI_EAR_PROSE_INVENTIONS_SCHEMA.artifact_type]["prose_inventions"]
            ),
            "model_calls": len(model_results),
        },
        "model_call_ids": [result.model_call.id for result in model_results],
        "upstream_artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "gate_summary": {
            "gate_name": gate_report["gate_name"],
            "passed": gate_report["passed"],
            "blocking_defects": gate_report["blocking_defects"],
            "summary_verdict": gate_report["summary_verdict"],
        },
        "lineage_id": LIVE_ABI_EAR_PACKET_LINEAGE_ID,
    }


def _summary_payload(
    *,
    client_name: str,
    model: str | None,
    run_id: str | None,
    packet_dir: str | None,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
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
        "packet_id": packet_dir.rsplit("\\", maxsplit=1)[-1].rsplit("/", maxsplit=1)[-1]
        if packet_dir
        else None,
        "packet_dir": packet_dir,
        "benchmark_input": BENCHMARK_INPUT,
        "required_artifact_types": list(LIVE_ABI_EAR_PACKET_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "model_calls": [result.model_call_to_dict() for result in model_results],
        "parsed_model_artifact_ids": {
            result.model_call.schema_name: result.model_call.parsed_output_artifact_id
            for result in model_results
            if result.model_call.parsed_output_artifact_id is not None
        },
        "counts": _counts_from_payloads(payloads),
        "message": message,
    }


def _counts_from_payloads(payloads: dict[str, dict[str, object]]) -> dict[str, int]:
    model_artifact_count = sum(
        1 for schema in LIVE_ABI_EAR_PACKET_MODEL_SCHEMAS if schema.artifact_type in payloads
    )
    counts = {
        "artifacts": len(payloads),
        "model_artifacts": model_artifact_count,
    }
    germ = payloads.get(ABI_EAR_GERM_ANALYSIS_SCHEMA.artifact_type)
    variants = payloads.get(ABI_EAR_VARIANTS_SCHEMA.artifact_type)
    moves = payloads.get(ABI_EAR_MOVES_SCHEMA.artifact_type)
    prose = payloads.get(ABI_EAR_PROSE_INVENTIONS_SCHEMA.artifact_type)
    if germ is not None:
        counts["word_forces"] = len(germ["word_forces"])
    if variants is not None:
        counts["variants"] = len(variants["variants"])
    if moves is not None:
        counts["moves"] = len(moves["moves"])
    if prose is not None:
        counts["prose_inventions"] = len(prose["prose_inventions"])
    return counts


def _failure_result(
    *,
    client_name: str,
    model: str,
    run_id: str,
    packet_dir: str,
    message: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
) -> LiveAbiEarPacketResult:
    return LiveAbiEarPacketResult(
        exit_code=1,
        payload=_summary_payload(
            client_name=client_name,
            model=model,
            run_id=run_id,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            model_results=model_results,
            refused=False,
            accepted=False,
            message=message,
        ),
        model_results=tuple(model_results),
    )


def _refusal(*, client_name: str, model: str | None, message: str) -> LiveAbiEarPacketResult:
    return LiveAbiEarPacketResult(
        exit_code=1,
        payload={
            "refused": True,
            "accepted": False,
            "client": client_name,
            "model": model,
            "run_id": None,
            "packet_id": None,
            "packet_dir": None,
            "artifact_ids": {},
            "model_calls": [],
            "message": message,
        },
    )


def _build_fake_model_payloads() -> dict[WorkerSchema, dict[str, object]]:
    source = build_benchmark_payloads(BENCHMARK_INPUT)
    field_model = source["abi_ear_field_model"]
    return {
        ABI_EAR_GERM_ANALYSIS_SCHEMA: _compact_germ_analysis(source["abi_ear_germ_analysis"]),
        ABI_EAR_FIELD_MODEL_SCHEMA: _compact_field_model(field_model),
        ABI_EAR_VARIANTS_SCHEMA: {
            "germ_text": BENCHMARK_INPUT,
            "variants": source["abi_ear_variants"]["variants"],
            "risks": ["fixture output is not real validation"],
        },
        ABI_EAR_MOVES_SCHEMA: {
            "germ_text": BENCHMARK_INPUT,
            "moves": [
                {
                    "id": move["id"],
                    "operation_name": move["operation_name"],
                    "new_material": move["new_material"],
                    "predicted_field_delta": move["predicted_field_delta"],
                    "risk": move["risk"],
                }
                for move in source["abi_ear_moves"]["moves"]
            ],
            "risks": ["fixture output is not real validation"],
        },
        ABI_EAR_RANKED_MOVE_SEQUENCE_SCHEMA: _compact_ranked_moves(
            source["abi_ear_ranked_move_sequence"]
        ),
        ABI_EAR_PROSE_INVENTIONS_SCHEMA: {
            "prose_inventions": source["abi_ear_prose_inventions"]["prose_inventions"],
            "risks": ["fixture output is not real validation"],
        },
        ABI_EAR_REFINED_INVENTION_SCHEMA: {
            "source_invention_ids": source["abi_ear_refined_invention"]["source_invention_ids"],
            "used_move_ids": source["abi_ear_refined_invention"]["used_move_ids"],
            "text": source["abi_ear_refined_invention"]["text"],
            "refinement_notes": source["abi_ear_refined_invention"]["refinement_notes"],
            "risks": ["fixture output is not real validation"],
        },
        ABI_EAR_REREAD_TRACE_SCHEMA: _compact_reread_trace(source["abi_ear_reread_trace"]),
    }


def _compact_germ_analysis(payload: object) -> dict[str, object]:
    germ_analysis = payload
    if not isinstance(germ_analysis, dict):
        raise TypeError("germ analysis fixture must be a dict")
    return {
        "germ_text": BENCHMARK_INPUT,
        "word_forces": [
            {
                "word": word_force["word"],
                "force": word_force["force"],
            }
            for word_force in germ_analysis["word_forces"]
        ],
        "fertility_score": germ_analysis["fertility_score"],
        "risks": germ_analysis["risks"],
    }


def _compact_field_model(payload: object) -> dict[str, object]:
    field_model = payload
    if not isinstance(field_model, dict):
        raise TypeError("field model fixture must be a dict")
    return {
        "germ_text": BENCHMARK_INPUT,
        "objects": [
            field_object["name"] if isinstance(field_object, dict) else str(field_object)
            for field_object in field_model["objects"]
        ],
        "local_laws": field_model["local_laws"],
        "latent_oppositions": field_model["latent_oppositions"],
        "negative_space": field_model["negative_space"],
        "scale_ceiling": field_model["scale_ceiling"],
        "forbidden_imports": field_model["forbidden_imports"],
        "possible_returns": field_model["possible_returns"],
        "risks": ["fixture output is not real validation"],
    }


def _compact_ranked_moves(payload: object) -> dict[str, object]:
    ranked = payload
    if not isinstance(ranked, dict):
        raise TypeError("ranked moves fixture must be a dict")
    return {
        "ranked_moves": [
            {
                "rank": move["rank"],
                "move_id": move["move_id"],
                "operation_name": move["operation_name"],
                "combined_score": move["combined_score"],
            }
            for move in ranked["ranked_moves"]
        ],
        "selected_sequence": ranked["selected_sequence"],
        "risks": ranked["risks"],
    }


def _compact_reread_trace(payload: object) -> dict[str, object]:
    trace = payload
    if not isinstance(trace, dict):
        raise TypeError("reread trace fixture must be a dict")
    return {
        "first_read_opening_interpretation": trace["first_read_opening_interpretation"],
        "second_read_opening_interpretation": trace["second_read_opening_interpretation"],
        "changed_opening_words": trace["changed_opening_words"],
        "supporting_lines_or_passages": trace["supporting_lines_or_passages"],
        "reread_gain_estimate": trace["reread_gain_estimate"],
        "unsupported_claims": trace["unsupported_claims"],
    }


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
