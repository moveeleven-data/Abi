"""Guarded live Minimal Reread packet pipeline for Phase 9."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os

from abi.artifacts import ArtifactRecord
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    PHASE9_LIVE_MINIMAL_REREAD_ACTIVE_PHASE,
    ensure_active_run,
    set_active_phase,
)
from abi.db import connect
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_driver import ModelClient, ModelClientError, ModelDriver, ModelDriverResult
from abi.model_driver import WorkerRequest
from abi.model_schemas import (
    LIVE_MINIMAL_REREAD_MODEL_SCHEMAS,
    REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    REREAD_COUNTERFACTUAL_RESULT_SCHEMA,
    REREAD_DRAFT_VERSION_SCHEMA,
    REREAD_FAILURE_DIAGNOSIS_SCHEMA,
    REREAD_FIRST_READ_TRACE_SCHEMA,
    REREAD_FORMAL_PROBLEM_SCHEMA,
    REREAD_GATE_REPORT_SCHEMA,
    REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA,
    REREAD_INTERVENTION_SCHEMA,
    REREAD_IRREDUCIBILITY_REPORT_SCHEMA,
    REREAD_RECOMPOSED_DRAFT_SCHEMA,
    REREAD_REREAD_TRACE_SCHEMA,
    WorkerRole,
    WorkerSchema,
)
from abi.modules.abi_ear import BENCHMARK_INPUT, build_benchmark_payloads
from abi.modules.reread import build_reread_payloads
from abi.packets import PacketWriter, create_packet_dir


LIVE_REREAD_LINEAGE_ID = "phase9_live_minimal_reread"
LIVE_REREAD_GATE_NAME = "live_minimal_reread_v1"
LIVE_REREAD_PROMPT_CONTRACT_PREFIX = "phase9.live_minimal_reread"
LIVE_REREAD_CLIENT_FAKE = "fake"
LIVE_REREAD_CLIENT_OPENAI = "openai"
LIVE_REREAD_CLIENTS = (LIVE_REREAD_CLIENT_FAKE, LIVE_REREAD_CLIENT_OPENAI)
LIVE_REREAD_MAX_MODEL_CALLS_DEFAULT = 12
LIVE_REREAD_FAKE_PROVIDER = "fake"
LIVE_REREAD_FAKE_MODEL = "fake-live-minimal-reread-v1"
LIVE_REREAD_PACKET_ARTIFACT_TYPE = "live_reread_packet"
LIVE_REREAD_ARTIFACT_TYPES = tuple(
    schema.artifact_type for schema in LIVE_MINIMAL_REREAD_MODEL_SCHEMAS
) + (LIVE_REREAD_PACKET_ARTIFACT_TYPE,)


@dataclass(frozen=True)
class LiveRereadPacketResult:
    exit_code: int
    payload: dict[str, object]
    model_results: tuple[ModelDriverResult, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class LiveRereadWorkerSpec:
    schema: WorkerSchema
    worker_role: WorkerRole
    prompt_contract_id: str
    parent_artifact_types: tuple[str, ...] = ()

    @property
    def artifact_type(self) -> str:
        return self.schema.artifact_type


LIVE_REREAD_WORKERS = (
    LiveRereadWorkerSpec(
        schema=REREAD_FORMAL_PROBLEM_SCHEMA,
        worker_role=WorkerRole.REREAD_FORMAL_PROBLEM_BUILDER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.formal_problem",
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA,
        worker_role=WorkerRole.REREAD_GERM_AFTERIMAGE_PAIRER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.germ_afterimage_pair",
        parent_artifact_types=(REREAD_FORMAL_PROBLEM_SCHEMA.artifact_type,),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_CONSEQUENCE_GRAPH_SCHEMA,
        worker_role=WorkerRole.REREAD_CONSEQUENCE_GRAPH_BUILDER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.consequence_graph",
        parent_artifact_types=(
            REREAD_FORMAL_PROBLEM_SCHEMA.artifact_type,
            REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA.artifact_type,
        ),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_DRAFT_VERSION_SCHEMA,
        worker_role=WorkerRole.REREAD_DRAFT_COMPOSER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.draft_version",
        parent_artifact_types=(
            REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA.artifact_type,
            REREAD_CONSEQUENCE_GRAPH_SCHEMA.artifact_type,
        ),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_FIRST_READ_TRACE_SCHEMA,
        worker_role=WorkerRole.REREAD_FIRST_READ_TRACER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.first_read_trace",
        parent_artifact_types=(REREAD_DRAFT_VERSION_SCHEMA.artifact_type,),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_REREAD_TRACE_SCHEMA,
        worker_role=WorkerRole.REREAD_REREAD_TRACER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.reread_trace",
        parent_artifact_types=(
            REREAD_DRAFT_VERSION_SCHEMA.artifact_type,
            REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA.artifact_type,
            REREAD_CONSEQUENCE_GRAPH_SCHEMA.artifact_type,
        ),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_FAILURE_DIAGNOSIS_SCHEMA,
        worker_role=WorkerRole.REREAD_FAILURE_DIAGNOSER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.failure_diagnosis",
        parent_artifact_types=(
            REREAD_FIRST_READ_TRACE_SCHEMA.artifact_type,
            REREAD_REREAD_TRACE_SCHEMA.artifact_type,
        ),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_INTERVENTION_SCHEMA,
        worker_role=WorkerRole.REREAD_INTERVENTION_BUILDER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.intervention",
        parent_artifact_types=(
            REREAD_FAILURE_DIAGNOSIS_SCHEMA.artifact_type,
            REREAD_CONSEQUENCE_GRAPH_SCHEMA.artifact_type,
        ),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_RECOMPOSED_DRAFT_SCHEMA,
        worker_role=WorkerRole.REREAD_RECOMPOSER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.recomposed_draft",
        parent_artifact_types=(
            REREAD_DRAFT_VERSION_SCHEMA.artifact_type,
            REREAD_INTERVENTION_SCHEMA.artifact_type,
        ),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_COUNTERFACTUAL_RESULT_SCHEMA,
        worker_role=WorkerRole.REREAD_COUNTERFACTUAL_EVALUATOR,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.counterfactual_result",
        parent_artifact_types=(
            REREAD_DRAFT_VERSION_SCHEMA.artifact_type,
            REREAD_RECOMPOSED_DRAFT_SCHEMA.artifact_type,
            REREAD_INTERVENTION_SCHEMA.artifact_type,
            REREAD_REREAD_TRACE_SCHEMA.artifact_type,
        ),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_IRREDUCIBILITY_REPORT_SCHEMA,
        worker_role=WorkerRole.REREAD_IRREDUCIBILITY_REPORTER,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.irreducibility_report",
        parent_artifact_types=(
            REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA.artifact_type,
            REREAD_INTERVENTION_SCHEMA.artifact_type,
            REREAD_COUNTERFACTUAL_RESULT_SCHEMA.artifact_type,
        ),
    ),
    LiveRereadWorkerSpec(
        schema=REREAD_GATE_REPORT_SCHEMA,
        worker_role=WorkerRole.REREAD_GATE_EVALUATOR,
        prompt_contract_id=f"{LIVE_REREAD_PROMPT_CONTRACT_PREFIX}.gate_report",
        parent_artifact_types=(
            REREAD_FORMAL_PROBLEM_SCHEMA.artifact_type,
            REREAD_COUNTERFACTUAL_RESULT_SCHEMA.artifact_type,
            REREAD_IRREDUCIBILITY_REPORT_SCHEMA.artifact_type,
        ),
    ),
)


class FakeRereadPacketClient:
    provider = LIVE_REREAD_FAKE_PROVIDER
    model = LIVE_REREAD_FAKE_MODEL

    def __init__(
        self,
        *,
        mode: str = "valid",
        target_schema: WorkerSchema = REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    ) -> None:
        self.mode = mode
        self.target_schema = target_schema
        self.payloads = _build_fake_model_payloads()

    def generate(self, request: WorkerRequest) -> str:
        if request.schema == self.target_schema and self.mode == "invalid":
            return "{not valid json"
        if request.schema == self.target_schema and self.mode == "failure":
            raise ModelClientError("simulated fake reread packet client failure")
        if self.mode not in ("valid", "invalid", "failure"):
            raise ModelClientError(f"unknown fake reread packet client mode: {self.mode}")
        payload = self.payloads.get(request.schema)
        if payload is None:
            raise ModelClientError(f"unsupported fake reread schema: {request.schema.name}")
        return _canonical_json(payload)


def run_live_reread_packet_demo(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool = False,
    max_model_calls: int = LIVE_REREAD_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    fake_mode: str = "valid",
    fake_target_schema: WorkerSchema = REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    client_factory: Callable[[str], ModelClient] | None = None,
) -> LiveRereadPacketResult:
    if client_name not in LIVE_REREAD_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            message=f"Live Minimal Reread client is not available: {client_name}",
        )

    planned_model_calls = len(LIVE_REREAD_WORKERS)
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < planned_model_calls:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == LIVE_REREAD_CLIENT_OPENAI else None,
            message=(
                "Live Minimal Reread command refused; max-model-calls "
                f"{max_model_calls} is below required budget {planned_model_calls}."
            ),
        )

    if client_name == LIVE_REREAD_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=(
                "Live Minimal Reread command refused; pass --allow-live-model "
                "to opt in explicitly."
            ),
        )

    resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == LIVE_REREAD_CLIENT_OPENAI and not resolved_api_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=f"Live Minimal Reread command refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    run, _ = ensure_active_run(config)
    packet_dir = create_packet_dir(config.run_dir(run.id) / "live_reread")
    with connect(config.db_path) as connection:
        set_active_phase(connection, run.id, PHASE9_LIVE_MINIMAL_REREAD_ACTIVE_PHASE)

    if client_name == LIVE_REREAD_CLIENT_FAKE:
        client = FakeRereadPacketClient(mode=fake_mode, target_schema=fake_target_schema)
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
        model=configured_model if client_name == LIVE_REREAD_CLIENT_OPENAI else client.model,
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
) -> LiveRereadPacketResult:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, object]] = {}
    model_results: list[ModelDriverResult] = []
    driver = ModelDriver(config=config, client=model_client)

    for index, worker in enumerate(LIVE_REREAD_WORKERS, start=1):
        if index > max_model_calls:
            return _failure_result(
                client_name=client_name,
                model=model,
                run_id=run_id,
                packet_dir=packet_dir,
                message="Live Minimal Reread command stopped by max-model-calls budget.",
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
                lineage_id=LIVE_REREAD_LINEAGE_ID,
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
                message="Live Minimal Reread command stopped by model-call failure.",
                artifacts=artifacts,
                payloads=payloads,
                model_results=model_results,
            )
        artifacts[worker.artifact_type] = result.parsed_artifact
        payloads[worker.artifact_type] = result.parsed_payload

    gate_record = _write_packet_summary(
        config=config,
        run_id=run_id,
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
        model_results=model_results,
        fixture_only=fixture_only,
    )
    return LiveRereadPacketResult(
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


def _write_packet_summary(
    *,
    config: AbiConfig,
    run_id: str,
    packet_dir: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    model_results: list[ModelDriverResult],
    fixture_only: bool,
) -> GateRecord:
    gate_report = payloads[REREAD_GATE_REPORT_SCHEMA.artifact_type]
    gate_report["gate_name"] = LIVE_REREAD_GATE_NAME
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
            lineage_id=LIVE_REREAD_LINEAGE_ID,
            created_by="live_minimal_reread_packet_scaffold",
            fixture_only=fixture_only,
        )
        gate_record = record_gate(
            connection,
            run_id=run_id,
            gate_name=LIVE_REREAD_GATE_NAME,
            passed=bool(gate_report["passed"]),
            blocking_defects=list(gate_report["blocking_defects"]),
            lineage_id=LIVE_REREAD_LINEAGE_ID,
        )
        artifacts[LIVE_REREAD_PACKET_ARTIFACT_TYPE] = writer.write_artifact(
            LIVE_REREAD_PACKET_ARTIFACT_TYPE,
            packet_summary,
            parent_ids=[artifacts[artifact_type].id for artifact_type in LIVE_REREAD_ARTIFACT_TYPES[:-1]],
        )
    payloads[LIVE_REREAD_PACKET_ARTIFACT_TYPE] = packet_summary
    return gate_record


def _build_packet_summary(
    *,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    gate_report: dict[str, object],
    model_results: list[ModelDriverResult],
) -> dict[str, object]:
    return {
        "worker": "live_minimal_reread_packet_summarizer_v1",
        "benchmark_input": BENCHMARK_INPUT,
        "artifact_types": list(LIVE_REREAD_ARTIFACT_TYPES),
        "loop_shape": [
            "first-read trace",
            "reread trace",
            "diagnosed failure",
            "targeted intervention",
            "recomposed draft",
            "counterfactual proof",
        ],
        "problem_statement": payloads[REREAD_FORMAL_PROBLEM_SCHEMA.artifact_type][
            "problem_statement"
        ],
        "versions": {
            "draft": payloads[REREAD_DRAFT_VERSION_SCHEMA.artifact_type]["version_id"],
            "recomposed": payloads[REREAD_RECOMPOSED_DRAFT_SCHEMA.artifact_type]["version_id"],
        },
        "counterfactual_summary": payloads[REREAD_COUNTERFACTUAL_RESULT_SCHEMA.artifact_type][
            "delta"
        ],
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
        "lineage_id": LIVE_REREAD_LINEAGE_ID,
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
        "required_artifact_types": list(LIVE_REREAD_ARTIFACT_TYPES),
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
        1 for schema in LIVE_MINIMAL_REREAD_MODEL_SCHEMAS if schema.artifact_type in payloads
    )
    counts = {
        "artifacts": len(payloads),
        "model_artifacts": model_artifact_count,
    }
    graph = payloads.get(REREAD_CONSEQUENCE_GRAPH_SCHEMA.artifact_type)
    first_read_trace = payloads.get(REREAD_FIRST_READ_TRACE_SCHEMA.artifact_type)
    counterfactual = payloads.get(REREAD_COUNTERFACTUAL_RESULT_SCHEMA.artifact_type)
    if graph is not None:
        counts["graph_nodes"] = len(graph["nodes"])
        counts["graph_edges"] = len(graph["edges"])
    if first_read_trace is not None:
        counts["blind_spots"] = len(first_read_trace["blind_spots"])
    if counterfactual is not None:
        counts["counterfactual_results"] = 1
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
) -> LiveRereadPacketResult:
    return LiveRereadPacketResult(
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


def _refusal(*, client_name: str, model: str | None, message: str) -> LiveRereadPacketResult:
    return LiveRereadPacketResult(
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
    source = build_reread_payloads(build_benchmark_payloads(BENCHMARK_INPUT))
    return {
        REREAD_FORMAL_PROBLEM_SCHEMA: _copy_fields(
            source["reread_formal_problem"],
            (
                "benchmark_input",
                "problem_statement",
                "initial_reader_state",
                "target_reader_state",
                "success_conditions",
                "forbidden_shortcuts",
            ),
        ),
        REREAD_GERM_AFTERIMAGE_PAIR_SCHEMA: _copy_fields(
            source["reread_germ_afterimage_pair"],
            ("germ", "afterimage", "reader_state_delta", "load_bearing_words"),
        ),
        REREAD_CONSEQUENCE_GRAPH_SCHEMA: _copy_fields(
            source["reread_consequence_graph"],
            ("problem_statement", "germ", "nodes", "edges", "cycle", "structural_claim"),
        ),
        REREAD_DRAFT_VERSION_SCHEMA: _copy_fields(
            source["reread_draft_version"],
            ("version_id", "used_graph_nodes", "text", "intended_afterimage", "known_weakness"),
        ),
        REREAD_FIRST_READ_TRACE_SCHEMA: _copy_fields(
            source["reread_first_read_trace"],
            (
                "draft_version_id",
                "opening_read",
                "noticed_evidence",
                "missed_evidence",
                "reader_state",
                "blind_spots",
            ),
        ),
        REREAD_REREAD_TRACE_SCHEMA: _copy_fields(
            source["reread_reread_trace"],
            (
                "draft_version_id",
                "opening_reread",
                "changed_opening_words",
                "supporting_nodes",
                "supporting_passages",
                "reader_state",
                "cycle_used",
            ),
        ),
        REREAD_FAILURE_DIAGNOSIS_SCHEMA: _copy_fields(
            source["reread_failure_diagnosis"],
            ("failure_id", "diagnosed_failure", "evidence", "severity", "repair_requirement"),
        ),
        REREAD_INTERVENTION_SCHEMA: _copy_fields(
            source["reread_intervention"],
            (
                "intervention_id",
                "targets_failure_id",
                "operation",
                "target_passage",
                "replacement_strategy",
                "affected_graph_nodes",
                "expected_effect",
            ),
        ),
        REREAD_RECOMPOSED_DRAFT_SCHEMA: _copy_fields(
            source["reread_recomposed_draft"],
            ("version_id", "source_version_id", "intervention_id", "text", "change_log"),
        ),
        REREAD_COUNTERFACTUAL_RESULT_SCHEMA: _copy_fields(
            source["reread_counterfactual_result"],
            (
                "counterfactual_id",
                "tested_condition",
                "baseline_version_id",
                "intervention_version_id",
                "predicted_without_intervention",
                "predicted_with_intervention",
                "delta",
                "intervention_id",
                "uses_previous_reread_trace_confidence",
            ),
        ),
        REREAD_IRREDUCIBILITY_REPORT_SCHEMA: _copy_fields(
            source["reread_irreducibility_report"],
            (
                "load_bearing_elements",
                "germ_afterimage_dependency",
                "counterfactual_delta",
                "verdict",
            ),
        ),
        REREAD_GATE_REPORT_SCHEMA: _compact_gate_report(source["reread_gate_report"]),
    }


def _copy_fields(payload: object, fields: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError("reread fixture payload must be a dict")
    return {field: payload[field] for field in fields}


def _compact_gate_report(payload: object) -> dict[str, object]:
    gate_report = _copy_fields(
        payload,
        ("gate_name", "passed", "blocking_defects", "gate_scores", "summary_verdict"),
    )
    gate_report["gate_name"] = LIVE_REREAD_GATE_NAME
    gate_report["summary_verdict"] = (
        "Live Minimal Reread fixture packet passes scaffold gates."
        if gate_report["passed"]
        else "Live Minimal Reread fixture packet is blocked by scaffold gate defects."
    )
    return gate_report


def _default_openai_client_factory(model: str) -> ModelClient:
    from abi.openai_adapter import OpenAIResponsesClient

    return OpenAIResponsesClient(model=model)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
