"""Controlled source-to-artifact production run scaffold for Phase 10."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path

from abi.artifacts import ArtifactRecord
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import PHASE10_PRODUCTION_RUN_ACTIVE_PHASE, set_active_phase
from abi.db import connect
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.model_driver import ModelClient
from abi.model_schemas import (
    ABI_EAR_VARIANTS_SCHEMA,
    REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    REREAD_RECOMPOSED_DRAFT_SCHEMA,
    WorkerSchema,
)
from abi.modules.abi_ear import BENCHMARK_INPUT
from abi.modules.live_abi_ear import (
    LIVE_ABI_EAR_CLIENT_FAKE,
    LIVE_ABI_EAR_CLIENT_OPENAI,
    LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT,
    LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE,
    LIVE_ABI_EAR_PACKET_ARTIFACT_TYPES,
    LiveAbiEarPacketResult,
    run_live_abi_ear_packet_demo,
)
from abi.modules.live_reread import (
    LIVE_REREAD_CLIENT_FAKE,
    LIVE_REREAD_CLIENT_OPENAI,
    LIVE_REREAD_MAX_MODEL_CALLS_DEFAULT,
    LIVE_REREAD_PACKET_ARTIFACT_TYPE,
    LIVE_REREAD_ARTIFACT_TYPES,
    LiveRereadPacketResult,
    run_live_reread_packet_demo,
)
from abi.modules.production_harness import (
    HARNESS_ARTIFACT_TYPES,
    HarnessRunResult,
    run_production_harness_demo,
)
from abi.packets import PacketWriter, create_packet_dir, read_json_file


PRODUCTION_RUN_LINEAGE_ID = "phase10_source_to_artifact_production_run"
PRODUCTION_RUN_GATE_NAME = "source_to_artifact_production_run_v1"
PRODUCTION_RUN_CLIENT_FAKE = "fake"
PRODUCTION_RUN_CLIENT_OPENAI = "openai"
PRODUCTION_RUN_CLIENTS = (PRODUCTION_RUN_CLIENT_FAKE, PRODUCTION_RUN_CLIENT_OPENAI)
PRODUCTION_RUN_MAX_MODEL_CALLS_DEFAULT = 24
PRODUCTION_RUN_REQUIRED_MODEL_CALLS = (
    LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT + LIVE_REREAD_MAX_MODEL_CALLS_DEFAULT
)
PRODUCTION_RUN_ARTIFACT_TYPES = (
    "production_source_manifest",
    "production_harness_packet_ref",
    "production_selected_germ",
    "production_target_effect",
    "production_live_abi_ear_packet_ref",
    "production_live_reread_packet_ref",
    "production_candidate_artifact",
    "production_candidate_report",
    "production_gate_report",
    "production_packet",
)


@dataclass(frozen=True)
class ProductionRunResult:
    exit_code: int
    payload: dict[str, object]
    harness_result: HarnessRunResult | None = None
    ear_result: LiveAbiEarPacketResult | None = None
    reread_result: LiveRereadPacketResult | None = None
    gate_record: GateRecord | None = None


def run_production_live_demo(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool = False,
    max_model_calls: int = PRODUCTION_RUN_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
    ear_fake_mode: str = "valid",
    ear_fake_target_schema: WorkerSchema = ABI_EAR_VARIANTS_SCHEMA,
    reread_fake_mode: str = "valid",
    reread_fake_target_schema: WorkerSchema = REREAD_CONSEQUENCE_GRAPH_SCHEMA,
    ear_client_factory: Callable[[str], ModelClient] | None = None,
    reread_client_factory: Callable[[str], ModelClient] | None = None,
) -> ProductionRunResult:
    if client_name not in PRODUCTION_RUN_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            message=f"Production live-demo client is not available: {client_name}",
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < PRODUCTION_RUN_REQUIRED_MODEL_CALLS:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == PRODUCTION_RUN_CLIENT_OPENAI else None,
            message=(
                "Production live-demo refused; max-model-calls "
                f"{max_model_calls} is below required budget "
                f"{PRODUCTION_RUN_REQUIRED_MODEL_CALLS}."
            ),
        )

    if client_name == PRODUCTION_RUN_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=(
                "Production live-demo refused; pass --allow-live-model "
                "to opt in explicitly."
            ),
        )

    resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == PRODUCTION_RUN_CLIENT_OPENAI and not resolved_api_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=f"Production live-demo refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    harness_result = run_production_harness_demo(config)
    upstream_client = (
        LIVE_ABI_EAR_CLIENT_FAKE
        if client_name == PRODUCTION_RUN_CLIENT_FAKE
        else LIVE_ABI_EAR_CLIENT_OPENAI
    )
    ear_result = run_live_abi_ear_packet_demo(
        config,
        client_name=upstream_client,
        allow_live_model=allow_live_model,
        max_model_calls=LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT,
        api_key=resolved_api_key,
        model=configured_model,
        fake_mode=ear_fake_mode,
        fake_target_schema=ear_fake_target_schema,
        client_factory=ear_client_factory,
    )
    if ear_result.exit_code != 0:
        return _upstream_failure(
            client_name=client_name,
            model=_model_for_summary(client_name, configured_model),
            message="Production live-demo stopped because live Abi Ear packet failed.",
            harness_result=harness_result,
            ear_result=ear_result,
            reread_result=None,
        )

    reread_client = (
        LIVE_REREAD_CLIENT_FAKE
        if client_name == PRODUCTION_RUN_CLIENT_FAKE
        else LIVE_REREAD_CLIENT_OPENAI
    )
    reread_result = run_live_reread_packet_demo(
        config,
        client_name=reread_client,
        allow_live_model=allow_live_model,
        max_model_calls=LIVE_REREAD_MAX_MODEL_CALLS_DEFAULT,
        api_key=resolved_api_key,
        model=configured_model,
        fake_mode=reread_fake_mode,
        fake_target_schema=reread_fake_target_schema,
        client_factory=reread_client_factory,
    )
    if reread_result.exit_code != 0:
        return _upstream_failure(
            client_name=client_name,
            model=_model_for_summary(client_name, configured_model),
            message="Production live-demo stopped because live Minimal Reread packet failed.",
            harness_result=harness_result,
            ear_result=ear_result,
            reread_result=reread_result,
        )

    return _write_production_packet(
        config=config,
        client_name=client_name,
        model=_model_for_summary(client_name, configured_model),
        harness_result=harness_result,
        ear_result=ear_result,
        reread_result=reread_result,
        max_model_calls=max_model_calls,
        fixture_only=client_name == PRODUCTION_RUN_CLIENT_FAKE,
    )


def _write_production_packet(
    *,
    config: AbiConfig,
    client_name: str,
    model: str,
    harness_result: HarnessRunResult,
    ear_result: LiveAbiEarPacketResult,
    reread_result: LiveRereadPacketResult,
    max_model_calls: int,
    fixture_only: bool,
) -> ProductionRunResult:
    run_id = harness_result.run_id
    packet_dir = create_packet_dir(config.run_dir(run_id) / "production")
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, object]] = {}

    with connect(config.db_path) as connection:
        set_active_phase(connection, run_id, PHASE10_PRODUCTION_RUN_ACTIVE_PHASE)
        writer = PacketWriter(
            connection=connection,
            run_id=run_id,
            packet_dir=packet_dir,
            lineage_id=PRODUCTION_RUN_LINEAGE_ID,
            created_by="source_to_artifact_production_run_scaffold",
            fixture_only=fixture_only,
        )

        payloads["production_source_manifest"] = _build_source_manifest_payload(harness_result)
        artifacts["production_source_manifest"] = writer.write_artifact(
            "production_source_manifest",
            payloads["production_source_manifest"],
            parent_ids=[harness_result.artifact_ids["harness_source_manifest"]],
        )

        payloads["production_harness_packet_ref"] = _build_harness_ref_payload(harness_result)
        artifacts["production_harness_packet_ref"] = writer.write_artifact(
            "production_harness_packet_ref",
            payloads["production_harness_packet_ref"],
            parent_ids=[harness_result.artifact_ids["harness_packet"]],
        )

        payloads["production_selected_germ"] = _build_selected_germ_payload(harness_result)
        artifacts["production_selected_germ"] = writer.write_artifact(
            "production_selected_germ",
            payloads["production_selected_germ"],
            parent_ids=[
                artifacts["production_source_manifest"].id,
                artifacts["production_harness_packet_ref"].id,
            ],
        )

        payloads["production_target_effect"] = _build_target_effect_payload()
        artifacts["production_target_effect"] = writer.write_artifact(
            "production_target_effect",
            payloads["production_target_effect"],
            parent_ids=[artifacts["production_selected_germ"].id],
        )

        payloads["production_live_abi_ear_packet_ref"] = _build_ear_ref_payload(ear_result)
        artifacts["production_live_abi_ear_packet_ref"] = writer.write_artifact(
            "production_live_abi_ear_packet_ref",
            payloads["production_live_abi_ear_packet_ref"],
            parent_ids=[
                ear_result.payload["artifact_ids"][LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE],
                artifacts["production_selected_germ"].id,
            ],
        )

        payloads["production_live_reread_packet_ref"] = _build_reread_ref_payload(reread_result)
        artifacts["production_live_reread_packet_ref"] = writer.write_artifact(
            "production_live_reread_packet_ref",
            payloads["production_live_reread_packet_ref"],
            parent_ids=[
                reread_result.payload["artifact_ids"][LIVE_REREAD_PACKET_ARTIFACT_TYPE],
                artifacts["production_live_abi_ear_packet_ref"].id,
                artifacts["production_target_effect"].id,
            ],
        )

        payloads["production_candidate_artifact"] = _build_candidate_artifact_payload(
            reread_result
        )
        artifacts["production_candidate_artifact"] = writer.write_artifact(
            "production_candidate_artifact",
            payloads["production_candidate_artifact"],
            parent_ids=[
                artifacts["production_live_reread_packet_ref"].id,
                reread_result.payload["artifact_ids"][REREAD_RECOMPOSED_DRAFT_SCHEMA.artifact_type],
            ],
        )

        payloads["production_candidate_report"] = _build_candidate_report_payload(
            client_name=client_name,
            model=model,
            max_model_calls=max_model_calls,
            harness_result=harness_result,
            ear_result=ear_result,
            reread_result=reread_result,
            candidate_payload=payloads["production_candidate_artifact"],
        )
        artifacts["production_candidate_report"] = writer.write_artifact(
            "production_candidate_report",
            payloads["production_candidate_report"],
            parent_ids=[
                artifacts["production_candidate_artifact"].id,
                artifacts["production_live_abi_ear_packet_ref"].id,
                artifacts["production_live_reread_packet_ref"].id,
            ],
        )

        payloads["production_gate_report"] = _build_gate_report_payload(
            payloads=payloads,
            max_model_calls=max_model_calls,
        )
        artifacts["production_gate_report"] = writer.write_artifact(
            "production_gate_report",
            payloads["production_gate_report"],
            parent_ids=[
                artifacts["production_source_manifest"].id,
                artifacts["production_harness_packet_ref"].id,
                artifacts["production_live_abi_ear_packet_ref"].id,
                artifacts["production_live_reread_packet_ref"].id,
                artifacts["production_candidate_report"].id,
            ],
        )
        gate_record = record_gate(
            connection,
            run_id=run_id,
            gate_name=PRODUCTION_RUN_GATE_NAME,
            passed=bool(payloads["production_gate_report"]["passed"]),
            blocking_defects=list(payloads["production_gate_report"]["blocking_defects"]),
            lineage_id=PRODUCTION_RUN_LINEAGE_ID,
        )

        payloads["production_packet"] = _build_packet_summary_payload(
            client_name=client_name,
            model=model,
            run_id=run_id,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
            harness_result=harness_result,
            ear_result=ear_result,
            reread_result=reread_result,
            max_model_calls=max_model_calls,
        )
        artifacts["production_packet"] = writer.write_artifact(
            "production_packet",
            payloads["production_packet"],
            parent_ids=[artifacts[artifact_type].id for artifact_type in PRODUCTION_RUN_ARTIFACT_TYPES[:-1]],
        )

    summary = _summary_payload(
        client_name=client_name,
        model=model,
        run_id=run_id,
        packet_dir=str(packet_dir),
        artifacts=artifacts,
        payloads=payloads,
        harness_result=harness_result,
        ear_result=ear_result,
        reread_result=reread_result,
        refused=False,
        accepted=True,
        message=None,
    )
    return ProductionRunResult(
        exit_code=0,
        payload=summary,
        harness_result=harness_result,
        ear_result=ear_result,
        reread_result=reread_result,
        gate_record=gate_record,
    )


def _build_source_manifest_payload(harness_result: HarnessRunResult) -> dict[str, object]:
    return {
        "worker": "production_source_manifest_reference_v1",
        "source_manifest_artifact_id": harness_result.artifact_ids["harness_source_manifest"],
        "source_manifest": harness_result.payloads["harness_source_manifest"],
        "harness_packet_artifact_id": harness_result.artifact_ids["harness_packet"],
        "fixture_only": True,
    }


def _build_harness_ref_payload(harness_result: HarnessRunResult) -> dict[str, object]:
    return {
        "worker": "production_harness_packet_reference_v1",
        "harness_packet_artifact_id": harness_result.artifact_ids["harness_packet"],
        "harness_packet_dir": harness_result.packet_dir,
        "harness_artifact_types": list(HARNESS_ARTIFACT_TYPES),
        "harness_artifact_ids": dict(harness_result.artifact_ids),
        "harness_gate_result": harness_result.gate_result,
    }


def _build_selected_germ_payload(harness_result: HarnessRunResult) -> dict[str, object]:
    source_manifest = harness_result.payloads["harness_source_manifest"]
    return {
        "worker": "production_selected_germ_selector_v1",
        "selected_germ_id": "selected_germ_table_morning_v1",
        "text": BENCHMARK_INPUT,
        "source_manifest_artifact_id": harness_result.artifact_ids["harness_source_manifest"],
        "source_count": source_manifest["source_count"],
        "selection_basis": (
            "Phase 10 keeps the frozen benchmark germ as an explicit selected source "
            "for controlled packet composition."
        ),
        "not_generation": True,
    }


def _build_target_effect_payload() -> dict[str, object]:
    return {
        "worker": "production_target_effect_builder_v1",
        "target_effect_id": "target_effect_reread_pressure_v1",
        "description": (
            "A later reread should make the opening sentence feel causally loaded, "
            "without claiming human validation."
        ),
        "reader_state_delta": {
            "from": "ordinary object observed in a room",
            "to": "ordinary object understood as carrying the unseen interval",
        },
        "success_constraints": [
            "no final essay generation",
            "no human validation claim",
            "candidate remains non-final",
        ],
        "not_human_validated": True,
    }


def _build_ear_ref_payload(ear_result: LiveAbiEarPacketResult) -> dict[str, object]:
    return {
        "worker": "production_live_abi_ear_packet_reference_v1",
        "live_abi_ear_packet_artifact_id": ear_result.payload["artifact_ids"][
            LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE
        ],
        "live_abi_ear_packet_dir": ear_result.payload["packet_dir"],
        "live_abi_ear_artifact_types": list(LIVE_ABI_EAR_PACKET_ARTIFACT_TYPES),
        "live_abi_ear_artifact_ids": dict(ear_result.payload["artifact_ids"]),
        "model_call_ids": [result.model_call.id for result in ear_result.model_results],
        "parsed_model_artifact_ids": dict(ear_result.payload["parsed_model_artifact_ids"]),
    }


def _build_reread_ref_payload(reread_result: LiveRereadPacketResult) -> dict[str, object]:
    return {
        "worker": "production_live_reread_packet_reference_v1",
        "live_reread_packet_artifact_id": reread_result.payload["artifact_ids"][
            LIVE_REREAD_PACKET_ARTIFACT_TYPE
        ],
        "live_reread_packet_dir": reread_result.payload["packet_dir"],
        "live_reread_artifact_types": list(LIVE_REREAD_ARTIFACT_TYPES),
        "live_reread_artifact_ids": dict(reread_result.payload["artifact_ids"]),
        "counterfactual_result_artifact_id": reread_result.payload["artifact_ids"][
            "live_reread_counterfactual_result"
        ],
        "model_call_ids": [result.model_call.id for result in reread_result.model_results],
        "parsed_model_artifact_ids": dict(reread_result.payload["parsed_model_artifact_ids"]),
    }


def _build_candidate_artifact_payload(
    reread_result: LiveRereadPacketResult,
) -> dict[str, object]:
    recomposed_envelope = read_json_file(
        Path(reread_result.payload["artifact_paths"][REREAD_RECOMPOSED_DRAFT_SCHEMA.artifact_type])
    )
    recomposed_payload = recomposed_envelope["payload"]
    return {
        "worker": "production_candidate_artifact_assembler_v1",
        "candidate_id": "candidate_table_morning_scaffold_v1",
        "source_recomposed_draft_artifact_id": reread_result.payload["artifact_ids"][
            REREAD_RECOMPOSED_DRAFT_SCHEMA.artifact_type
        ],
        "text": recomposed_payload["text"],
        "non_final": True,
        "candidate_only": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "human_validated": False,
        "human_validation_claim": False,
        "phase_shift_claim": False,
        "production_limits": [
            "scaffold candidate only",
            "not a final essay",
            "not human validated",
            "not eligible for controller finalization",
        ],
    }


def _build_candidate_report_payload(
    *,
    client_name: str,
    model: str,
    max_model_calls: int,
    harness_result: HarnessRunResult,
    ear_result: LiveAbiEarPacketResult,
    reread_result: LiveRereadPacketResult,
    candidate_payload: dict[str, object],
) -> dict[str, object]:
    upstream_model_call_ids = _upstream_model_call_ids(ear_result, reread_result)
    return {
        "worker": "production_candidate_reporter_v1",
        "client": client_name,
        "model": model,
        "harness_packet_artifact_id": harness_result.artifact_ids["harness_packet"],
        "live_abi_ear_packet_artifact_id": ear_result.payload["artifact_ids"][
            LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE
        ],
        "live_reread_packet_artifact_id": reread_result.payload["artifact_ids"][
            LIVE_REREAD_PACKET_ARTIFACT_TYPE
        ],
        "candidate_id": candidate_payload["candidate_id"],
        "candidate_flags": _candidate_flags(candidate_payload),
        "upstream_model_call_count": len(upstream_model_call_ids),
        "upstream_model_call_ids": upstream_model_call_ids,
        "max_model_calls": max_model_calls,
        "assessment": (
            "Candidate artifact is a controlled scaffold output for lineage testing only; "
            "it is non-final, not human-validated, and not finalization-eligible."
        ),
    }


def _build_gate_report_payload(
    *,
    payloads: dict[str, dict[str, object]],
    max_model_calls: int,
) -> dict[str, object]:
    candidate = payloads["production_candidate_artifact"]
    candidate_report = payloads["production_candidate_report"]
    defects = []
    if not candidate.get("non_final"):
        defects.append("candidate artifact must be marked non-final")
    if not candidate.get("not_human_validated"):
        defects.append("candidate artifact must be marked not human validated")
    if candidate.get("finalization_eligible"):
        defects.append("candidate artifact must not be finalization eligible")
    if candidate.get("human_validation_claim"):
        defects.append("candidate artifact must not make a human validation claim")
    if candidate.get("phase_shift_claim"):
        defects.append("candidate artifact must not make a phase-shift claim")
    if candidate_report["upstream_model_call_count"] > max_model_calls:
        defects.append("upstream model-call count exceeds max-model-calls budget")

    return {
        "worker": "production_gate_evaluator_v1",
        "gate_name": PRODUCTION_RUN_GATE_NAME,
        "passed": not defects,
        "blocking_defects": defects,
        "gate_scores": {
            "source_manifest_present": 1.0
            if "production_source_manifest" in payloads
            else 0.0,
            "harness_packet_ref_present": 1.0
            if "production_harness_packet_ref" in payloads
            else 0.0,
            "live_abi_ear_packet_ref_present": 1.0
            if "production_live_abi_ear_packet_ref" in payloads
            else 0.0,
            "live_reread_packet_ref_present": 1.0
            if "production_live_reread_packet_ref" in payloads
            else 0.0,
            "candidate_non_final": 1.0 if candidate.get("non_final") else 0.0,
            "candidate_not_human_validated": 1.0
            if candidate.get("not_human_validated")
            else 0.0,
            "candidate_not_finalization_eligible": 1.0
            if candidate.get("not_finalization_eligible")
            else 0.0,
        },
        "finalization_gate": False,
        "finalization_eligible": False,
        "summary_verdict": (
            "Production packet passes scaffold gates but remains ineligible for finalization."
            if not defects
            else "Production packet is blocked by scaffold gate defects."
        ),
    }


def _build_packet_summary_payload(
    *,
    client_name: str,
    model: str,
    run_id: str,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    harness_result: HarnessRunResult,
    ear_result: LiveAbiEarPacketResult,
    reread_result: LiveRereadPacketResult,
    max_model_calls: int,
) -> dict[str, object]:
    upstream_model_call_ids = _upstream_model_call_ids(ear_result, reread_result)
    return {
        "worker": "production_packet_summarizer_v1",
        "run_id": run_id,
        "packet_id": packet_dir.name,
        "client": client_name,
        "model": model,
        "artifact_types": list(PRODUCTION_RUN_ARTIFACT_TYPES),
        "artifact_ids": {artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        "source_manifest_artifact_id": artifacts["production_source_manifest"].id,
        "harness_packet_reference_artifact_id": artifacts["production_harness_packet_ref"].id,
        "selected_germ_artifact_id": artifacts["production_selected_germ"].id,
        "target_effect_artifact_id": artifacts["production_target_effect"].id,
        "live_abi_ear_packet_reference_artifact_id": artifacts[
            "production_live_abi_ear_packet_ref"
        ].id,
        "live_reread_packet_reference_artifact_id": artifacts[
            "production_live_reread_packet_ref"
        ].id,
        "candidate_artifact_id": artifacts["production_candidate_artifact"].id,
        "candidate_report_artifact_id": artifacts["production_candidate_report"].id,
        "production_gate_report_artifact_id": artifacts["production_gate_report"].id,
        "upstream_packet_refs": {
            "harness_packet": harness_result.artifact_ids["harness_packet"],
            "live_abi_ear_packet": ear_result.payload["artifact_ids"][
                LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE
            ],
            "live_reread_packet": reread_result.payload["artifact_ids"][
                LIVE_REREAD_PACKET_ARTIFACT_TYPE
            ],
        },
        "counts": {
            "production_artifacts": len(PRODUCTION_RUN_ARTIFACT_TYPES),
            "upstream_model_calls": len(upstream_model_call_ids),
            "max_model_calls": max_model_calls,
        },
        "candidate_flags": _candidate_flags(payloads["production_candidate_artifact"]),
        "gate_summary": {
            "gate_name": payloads["production_gate_report"]["gate_name"],
            "passed": payloads["production_gate_report"]["passed"],
            "blocking_defects": payloads["production_gate_report"]["blocking_defects"],
            "summary_verdict": payloads["production_gate_report"]["summary_verdict"],
        },
        "finalization_eligible": False,
        "not_human_validated": True,
        "lineage_id": PRODUCTION_RUN_LINEAGE_ID,
    }


def _summary_payload(
    *,
    client_name: str,
    model: str | None,
    run_id: str | None,
    packet_dir: str | None,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    harness_result: HarnessRunResult | None,
    ear_result: LiveAbiEarPacketResult | None,
    reread_result: LiveRereadPacketResult | None,
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
        "required_artifact_types": list(PRODUCTION_RUN_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "upstream_packet_refs": _upstream_packet_refs(harness_result, ear_result, reread_result),
        "upstream_model_call_ids": _upstream_model_call_ids(ear_result, reread_result)
        if ear_result is not None and reread_result is not None
        else [],
        "counts": _counts_from_payloads(payloads, ear_result, reread_result),
        "candidate_flags": _candidate_flags(payloads["production_candidate_artifact"])
        if "production_candidate_artifact" in payloads
        else {},
        "gate_result": _gate_result(payloads),
        "message": message,
    }


def _counts_from_payloads(
    payloads: dict[str, dict[str, object]],
    ear_result: LiveAbiEarPacketResult | None,
    reread_result: LiveRereadPacketResult | None,
) -> dict[str, int]:
    counts = {
        "production_artifacts": len(payloads),
        "required_production_artifacts": len(PRODUCTION_RUN_ARTIFACT_TYPES),
    }
    if ear_result is not None and reread_result is not None:
        counts["upstream_model_calls"] = len(_upstream_model_call_ids(ear_result, reread_result))
    if "production_candidate_artifact" in payloads:
        counts["candidate_artifacts"] = 1
    return counts


def _gate_result(payloads: dict[str, dict[str, object]]) -> dict[str, object] | None:
    gate_report = payloads.get("production_gate_report")
    if gate_report is None:
        return None
    return {
        "gate_name": gate_report["gate_name"],
        "passed": gate_report["passed"],
        "blocking_defects": gate_report["blocking_defects"],
        "summary_verdict": gate_report["summary_verdict"],
        "finalization_eligible": gate_report["finalization_eligible"],
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
    }


def _upstream_model_call_ids(
    ear_result: LiveAbiEarPacketResult,
    reread_result: LiveRereadPacketResult,
) -> list[str]:
    return [result.model_call.id for result in ear_result.model_results] + [
        result.model_call.id for result in reread_result.model_results
    ]


def _upstream_packet_refs(
    harness_result: HarnessRunResult | None,
    ear_result: LiveAbiEarPacketResult | None,
    reread_result: LiveRereadPacketResult | None,
) -> dict[str, object]:
    refs: dict[str, object] = {}
    if harness_result is not None:
        refs["harness_packet"] = harness_result.artifact_ids["harness_packet"]
    if ear_result is not None and ear_result.payload.get("artifact_ids"):
        refs["live_abi_ear_packet"] = ear_result.payload["artifact_ids"].get(
            LIVE_ABI_EAR_PACKET_ARTIFACT_TYPE
        )
    if reread_result is not None and reread_result.payload.get("artifact_ids"):
        refs["live_reread_packet"] = reread_result.payload["artifact_ids"].get(
            LIVE_REREAD_PACKET_ARTIFACT_TYPE
        )
    return refs


def _upstream_failure(
    *,
    client_name: str,
    model: str,
    message: str,
    harness_result: HarnessRunResult,
    ear_result: LiveAbiEarPacketResult | None,
    reread_result: LiveRereadPacketResult | None,
) -> ProductionRunResult:
    return ProductionRunResult(
        exit_code=1,
        payload=_summary_payload(
            client_name=client_name,
            model=model,
            run_id=harness_result.run_id,
            packet_dir=None,
            artifacts={},
            payloads={},
            harness_result=harness_result,
            ear_result=ear_result,
            reread_result=reread_result,
            refused=False,
            accepted=False,
            message=message,
        ),
        harness_result=harness_result,
        ear_result=ear_result,
        reread_result=reread_result,
    )


def _refusal(*, client_name: str, model: str | None, message: str) -> ProductionRunResult:
    return ProductionRunResult(
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
            "upstream_model_call_ids": [],
            "message": message,
        },
    )


def _model_for_summary(client_name: str, configured_model: str) -> str:
    if client_name == PRODUCTION_RUN_CLIENT_OPENAI:
        return configured_model
    return "fake-source-to-artifact-production-run-v1"
