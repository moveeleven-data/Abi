"""Diagnostic local-law comparison against a materialized direct rival subject."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.modules.direct_rival_subject_materialization import NEXT_STRATEGY_WITH_DIRECT_TEXT
from abi.modules.local_law_discovery import DISCOVERED_LOCAL_LAW_ID
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


MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_LINEAGE_ID = (
    "model_backed_local_law_diagnostic_with_rival_subject_v1"
)
MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_CREATED_BY = (
    "model_backed_local_law_diagnostic_v1_controller"
)
MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_KIND = (
    "model_backed_local_law_diagnostic_with_rival_subject"
)
MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_CLIENTS = ("fake", "openai")
MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_MAX_MODEL_CALLS_DEFAULT = 1
NEXT_RECOMMENDED_ACTION = "review_local_law_rival_diagnostic_before_nonlocal_strategy"
NEXT_FAKE_RECOMMENDED_STRATEGY_CLASS = (
    "review_model_backed_local_law_diagnostic_before_live_run"
)
FUTURE_LIVE_RECOMMENDED_STRATEGY_CLASS = (
    "nonlocal_law_guided_strategy_from_rival_diagnostic"
)
LIKELY_RIVAL_ADVANTAGE = "first_read_pressure_advantage"
LIKELY_PACKET_0063_GAP = "pressure still arrives too conceptually or too late"

MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_ARTIFACT_TYPES = (
    "source_direct_rival_materialization_intake_summary",
    "current_best_subject_for_law_comparison",
    "direct_rival_subject_for_law_comparison",
    "law_application_comparison_matrix",
    "first_read_pressure_diagnostic_report",
    "rival_advantage_under_law_report",
    "packet_0063_law_gap_report",
    "non_imitation_constraint_report",
    "next_strategy_readiness_report",
    "project_health_scope_guard_report",
    "local_law_rival_diagnostic_gate_report",
    "model_backed_local_law_diagnostic_packet",
)

REQUIRED_MATERIALIZATION_ARTIFACTS = (
    "direct_rival_subject_materialization_packet",
    "source_local_law_intake_summary",
    "materialized_direct_rival_subject",
    "rival_summary_evidence_bundle",
    "provenance_and_hash_report",
    "evidence_limitations_report",
    "non_imitation_constraint_report",
    "next_strategy_readiness_report",
    "project_health_scope_guard_report",
    "direct_rival_subject_gate_report",
)

CURRENT_BEST_TEXT_ARTIFACT_CANDIDATES = (
    "macro_recomposed_candidate_text",
    "bounded_macro_recomposed_candidate",
    "candidate_text",
    "revision_candidate",
)
TEXT_FIELD_CANDIDATES = (
    "text",
    "candidate_text",
    "recomposed_text",
    "revision_text",
    "macro_recomposed_text",
)
NON_IMITATION_CONSTRAINTS = (
    "do not imitate rival diction",
    "do not transplant rival scenes",
    "do not copy rival structure",
    "do not chase generic vividness",
    "do not turn packet_0063 into the rival",
    "diagnose causal advantage only",
    "preserve packet_0063 current-best evidence chain",
    "preserve failed-target memory",
    "preserve no final/phase-shift claim",
)


@dataclass(frozen=True)
class ModelBackedLocalLawDiagnosticResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class MaterializedRivalSubject:
    direct_rival_text_available: bool
    materialized_text: str
    materialized_text_sha256: str
    source_artifact_id: str | None
    source_artifact_type: str | None
    source_path: str | None
    source_field_path: str | None


@dataclass(frozen=True)
class CurrentBestSubject:
    text_available: bool
    text: str | None
    text_sha256: str | None
    source_artifact_id: str | None
    source_artifact_type: str | None
    source_path: str | None
    source_field: str | None


@dataclass(frozen=True)
class ModelBackedLocalLawDiagnosticSubject:
    run_id: str
    materialization_packet_dir: Path
    materialization_packet_id: str
    materialization_packet_artifact_id: str | None
    materialization_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]
    materialized_subject: MaterializedRivalSubject
    current_best_subject: CurrentBestSubject
    materialization_surface_alias_warning: bool


def run_model_backed_local_law_diagnostic(
    config: AbiConfig,
    *,
    client_name: str,
    direct_rival_materialization_packet: Path | str,
    operator_reviewed: bool,
    allow_live_model: bool,
    max_model_calls: int,
) -> ModelBackedLocalLawDiagnosticResult:
    initialize_database(config)
    materialization_packet_dir = _resolve_path(
        config,
        direct_rival_materialization_packet,
    )
    if client_name not in MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_CLIENTS:
        return _refusal(
            direct_rival_materialization_packet=materialization_packet_dir,
            client_name=client_name,
            message=(
                "Model-backed local-law diagnostic refused; unsupported "
                f"client: {client_name}."
            ),
        )
    if client_name == "openai" and not allow_live_model:
        return _refusal(
            direct_rival_materialization_packet=materialization_packet_dir,
            client_name=client_name,
            message=(
                "Model-backed local-law diagnostic refused; --allow-live-model "
                "is required for client openai."
            ),
        )
    if client_name == "openai" and allow_live_model:
        return _refusal(
            direct_rival_materialization_packet=materialization_packet_dir,
            client_name=client_name,
            message=(
                "Model-backed local-law diagnostic refused; live OpenAI local-law "
                "rival diagnosis is not implemented in this diagnostic-only task."
            ),
        )
    if not operator_reviewed:
        return _refusal(
            direct_rival_materialization_packet=materialization_packet_dir,
            client_name=client_name,
            message=(
                "Model-backed local-law diagnostic refused; --operator-reviewed "
                "is required."
            ),
        )
    if max_model_calls < 0:
        return _refusal(
            direct_rival_materialization_packet=materialization_packet_dir,
            client_name=client_name,
            message=(
                "Model-backed local-law diagnostic refused; --max-model-calls "
                "cannot be negative."
            ),
        )
    if (
        not materialization_packet_dir.exists()
        or not materialization_packet_dir.is_dir()
    ):
        return _refusal(
            direct_rival_materialization_packet=materialization_packet_dir,
            client_name=client_name,
            message=(
                "Model-backed local-law diagnostic refused; direct-rival "
                f"materialization packet directory not found: {materialization_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(
            config,
            materialization_packet_dir,
        )
    except ValueError as error:
        return _refusal(
            direct_rival_materialization_packet=materialization_packet_dir,
            client_name=client_name,
            message=str(error),
        )

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                direct_rival_materialization_packet=materialization_packet_dir,
                client_name=client_name,
                message=(
                    "Model-backed local-law diagnostic refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "model_backed_local_law_diagnostic"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_LINEAGE_ID,
            created_by=MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_direct_rival_materialization_intake_summary"] = (
            _build_source_direct_rival_materialization_intake_summary(
                subject,
                packet_dir,
                client_name=client_name,
            )
        )
        artifacts["source_direct_rival_materialization_intake_summary"] = (
            writer.write_artifact(
                "source_direct_rival_materialization_intake_summary",
                payloads["source_direct_rival_materialization_intake_summary"],
                parent_ids=list(subject.source_parent_ids),
            )
        )

        payloads["current_best_subject_for_law_comparison"] = (
            _build_current_best_subject_for_law_comparison(subject)
        )
        artifacts["current_best_subject_for_law_comparison"] = writer.write_artifact(
            "current_best_subject_for_law_comparison",
            payloads["current_best_subject_for_law_comparison"],
            parent_ids=[
                artifacts["source_direct_rival_materialization_intake_summary"].id
            ],
        )

        payloads["direct_rival_subject_for_law_comparison"] = (
            _build_direct_rival_subject_for_law_comparison(subject)
        )
        artifacts["direct_rival_subject_for_law_comparison"] = writer.write_artifact(
            "direct_rival_subject_for_law_comparison",
            payloads["direct_rival_subject_for_law_comparison"],
            parent_ids=[
                artifacts["source_direct_rival_materialization_intake_summary"].id
            ],
        )

        payloads["law_application_comparison_matrix"] = (
            _build_law_application_comparison_matrix(subject)
        )
        artifacts["law_application_comparison_matrix"] = writer.write_artifact(
            "law_application_comparison_matrix",
            payloads["law_application_comparison_matrix"],
            parent_ids=[
                artifacts["current_best_subject_for_law_comparison"].id,
                artifacts["direct_rival_subject_for_law_comparison"].id,
            ],
        )

        payloads["first_read_pressure_diagnostic_report"] = (
            _build_first_read_pressure_diagnostic_report(subject)
        )
        artifacts["first_read_pressure_diagnostic_report"] = writer.write_artifact(
            "first_read_pressure_diagnostic_report",
            payloads["first_read_pressure_diagnostic_report"],
            parent_ids=[artifacts["law_application_comparison_matrix"].id],
        )

        payloads["rival_advantage_under_law_report"] = (
            _build_rival_advantage_under_law_report(subject)
        )
        artifacts["rival_advantage_under_law_report"] = writer.write_artifact(
            "rival_advantage_under_law_report",
            payloads["rival_advantage_under_law_report"],
            parent_ids=[artifacts["first_read_pressure_diagnostic_report"].id],
        )

        payloads["packet_0063_law_gap_report"] = _build_packet_0063_law_gap_report(
            subject
        )
        artifacts["packet_0063_law_gap_report"] = writer.write_artifact(
            "packet_0063_law_gap_report",
            payloads["packet_0063_law_gap_report"],
            parent_ids=[
                artifacts["current_best_subject_for_law_comparison"].id,
                artifacts["rival_advantage_under_law_report"].id,
            ],
        )

        payloads["non_imitation_constraint_report"] = (
            _build_non_imitation_constraint_report(subject)
        )
        artifacts["non_imitation_constraint_report"] = writer.write_artifact(
            "non_imitation_constraint_report",
            payloads["non_imitation_constraint_report"],
            parent_ids=[
                artifacts["direct_rival_subject_for_law_comparison"].id,
                artifacts["packet_0063_law_gap_report"].id,
            ],
        )

        payloads["next_strategy_readiness_report"] = (
            _build_next_strategy_readiness_report(subject)
        )
        artifacts["next_strategy_readiness_report"] = writer.write_artifact(
            "next_strategy_readiness_report",
            payloads["next_strategy_readiness_report"],
            parent_ids=[
                artifacts["rival_advantage_under_law_report"].id,
                artifacts["non_imitation_constraint_report"].id,
            ],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[
                artifacts["source_direct_rival_materialization_intake_summary"].id,
                artifacts["next_strategy_readiness_report"].id,
            ],
        )

        payloads["local_law_rival_diagnostic_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
        )
        artifacts["local_law_rival_diagnostic_gate_report"] = writer.write_artifact(
            "local_law_rival_diagnostic_gate_report",
            payloads["local_law_rival_diagnostic_gate_report"],
            parent_ids=[
                artifacts["project_health_scope_guard_report"].id,
                artifacts["non_imitation_constraint_report"].id,
            ],
        )

        payloads["model_backed_local_law_diagnostic_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
            client_name=client_name,
        )
        artifacts["model_backed_local_law_diagnostic_packet"] = writer.write_artifact(
            "model_backed_local_law_diagnostic_packet",
            payloads["model_backed_local_law_diagnostic_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "model_backed_local_law_diagnostic_packet"
            ],
        )

        gate_report = payloads["local_law_rival_diagnostic_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="local_law_rival_diagnostic_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_LINEAGE_ID,
        )

    result_payload = _result_payload(
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    return ModelBackedLocalLawDiagnosticResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    materialization_packet_dir: Path,
) -> ModelBackedLocalLawDiagnosticSubject:
    payloads = _load_required_payloads(materialization_packet_dir)
    alias_warning = _validate_materialization_payloads(payloads)
    packet = payloads["direct_rival_subject_materialization_packet"]
    materialized = _materialized_subject_from_payloads(payloads)
    run_id = _required_string(
        packet.get("run_id"),
        "Model-backed local-law diagnostic refused; materialization packet "
        "missing run_id.",
    )
    packet_id = str(packet.get("packet_id") or materialization_packet_dir.name)
    packet_path = (
        materialization_packet_dir / "direct_rival_subject_materialization_packet.json"
    )
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
        current_best = _load_current_best_subject(
            config,
            connection,
            run_id=run_id,
        )
    artifact_ids = _artifact_ids_from_packet(packet)
    source_parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *artifact_ids.values(),
        ]
    )
    return ModelBackedLocalLawDiagnosticSubject(
        run_id=run_id,
        materialization_packet_dir=materialization_packet_dir,
        materialization_packet_id=packet_id,
        materialization_packet_artifact_id=packet_artifact.id
        if packet_artifact
        else None,
        materialization_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
        materialized_subject=materialized,
        current_best_subject=current_best,
        materialization_surface_alias_warning=alias_warning,
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_MATERIALIZATION_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Model-backed local-law diagnostic refused; direct-rival "
                f"materialization packet missing {path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Model-backed local-law diagnostic refused; malformed materialization "
            f"artifact: {path.name}."
        )
    return envelope["payload"]


def _validate_materialization_payloads(
    payloads: dict[str, dict[str, Any]],
) -> bool:
    packet = payloads["direct_rival_subject_materialization_packet"]
    materialized = payloads["materialized_direct_rival_subject"]
    provenance = payloads["provenance_and_hash_report"]
    readiness = payloads["next_strategy_readiness_report"]
    health = payloads["project_health_scope_guard_report"]
    constraints = payloads["non_imitation_constraint_report"]

    if packet.get("accepted") is not True:
        raise ValueError(
            "Model-backed local-law diagnostic refused; materialization packet "
            "is not accepted."
        )
    if packet.get("direct_rival_text_available") is not True or materialized.get(
        "direct_rival_text_available"
    ) is not True:
        raise ValueError(
            "Model-backed local-law diagnostic refused; direct rival text is "
            "not available."
        )
    materialized_text = materialized.get("materialized_text")
    if not isinstance(materialized_text, str) or not materialized_text.strip():
        raise ValueError(
            "Model-backed local-law diagnostic refused; materialized direct "
            "rival text is missing."
        )
    materialized_sha = materialized.get("materialized_text_sha256")
    if not isinstance(materialized_sha, str) or not materialized_sha:
        raise ValueError(
            "Model-backed local-law diagnostic refused; materialized_text_sha256 "
            "is missing."
        )
    if sha256_text(materialized_text) != materialized_sha:
        raise ValueError(
            "Model-backed local-law diagnostic refused; materialized rival text "
            "hash does not match materialized_text_sha256."
        )
    if packet.get("law_id") != DISCOVERED_LOCAL_LAW_ID:
        raise ValueError(
            "Model-backed local-law diagnostic refused; law id must be "
            f"{DISCOVERED_LOCAL_LAW_ID}."
        )
    if packet.get("recommended_next_strategy_class") != NEXT_STRATEGY_WITH_DIRECT_TEXT:
        raise ValueError(
            "Model-backed local-law diagnostic refused; materialization packet "
            "does not recommend model_backed_local_law_diagnostic_with_rival_subject."
        )
    for field_name, expected in (
        ("current_best_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID),
        ("proof_packet_id", EXPECTED_PROOF_PACKET_ID),
        ("reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID),
    ):
        if packet.get(field_name) != expected:
            raise ValueError(
                "Model-backed local-law diagnostic refused; materialization "
                f"{field_name} must be {expected}."
            )
    if _any_true(
        payloads,
        (
            "generation_authorized",
            "next_generation_authorized",
            "candidate_generated",
        ),
    ):
        raise ValueError(
            "Model-backed local-law diagnostic refused; source materialization "
            "authorizes generation or generated a candidate."
        )
    if _any_true(payloads, ("residual_target_selected",)):
        raise ValueError(
            "Model-backed local-law diagnostic refused; source materialization "
            "selected a residual target."
        )
    if _any_true(payloads, ("work_order_created",)):
        raise ValueError(
            "Model-backed local-law diagnostic refused; source materialization "
            "created a work order."
        )
    if _model_calls(payloads) != 0:
        raise ValueError(
            "Model-backed local-law diagnostic refused; source materialization "
            "contains model calls."
        )
    if packet.get("source_chain_coherent") is not True or health.get(
        "source_chain_coherent"
    ) is not True:
        raise ValueError(
            "Model-backed local-law diagnostic refused; source chain is incoherent."
        )
    if health.get("project_health_scope_guard_passed") is not True:
        raise ValueError(
            "Model-backed local-law diagnostic refused; source materialization "
            "lacks a passing project-health guard."
        )
    if constraints.get("non_imitation_constraints_passed") is not True:
        raise ValueError(
            "Model-backed local-law diagnostic refused; source materialization "
            "lacks passing non-imitation constraints."
        )
    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Model-backed local-law diagnostic refused; finality or phase-shift "
            "claim appears in the source materialization packet."
        )

    primary_source_alias_missing = (
        not provenance.get("primary_source_path")
        or not provenance.get("primary_source_artifact_id")
    )
    readiness_alias_missing = readiness.get("ready_for_model_backed_forensics") is None
    return bool(primary_source_alias_missing or readiness_alias_missing)


def _materialized_subject_from_payloads(
    payloads: dict[str, dict[str, Any]],
) -> MaterializedRivalSubject:
    materialized = payloads["materialized_direct_rival_subject"]
    text = str(materialized["materialized_text"])
    return MaterializedRivalSubject(
        direct_rival_text_available=True,
        materialized_text=text,
        materialized_text_sha256=str(materialized["materialized_text_sha256"]),
        source_artifact_id=_first_string_or_none(
            materialized.get("source_artifact_id"),
            payloads["provenance_and_hash_report"].get("materialized_source_artifact_id"),
        ),
        source_artifact_type=_first_string_or_none(materialized.get("source_artifact_type")),
        source_path=_first_string_or_none(
            materialized.get("source_path"),
            payloads["provenance_and_hash_report"].get("materialized_source_path"),
        ),
        source_field_path=_first_string_or_none(materialized.get("source_field_path")),
    )


def _load_current_best_subject(
    config: AbiConfig,
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> CurrentBestSubject:
    packet_dir = config.run_dir(run_id) / "bounded_macro_recomposition" / "packet_0063"
    candidate_paths: list[Path] = [
        packet_dir / f"{artifact_type}.json"
        for artifact_type in CURRENT_BEST_TEXT_ARTIFACT_CANDIDATES
    ]
    if packet_dir.exists():
        candidate_paths.extend(sorted(packet_dir.glob("*.json")))
    seen: set[str] = set()
    for path in candidate_paths:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        envelope = _read_json_or_none(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            continue
        payload = envelope["payload"]
        artifact_type = str(envelope.get("artifact_type") or path.stem)
        for field_name in TEXT_FIELD_CANDIDATES:
            value = payload.get(field_name)
            if isinstance(value, str) and value.strip():
                artifact = _artifact_for_path(connection, path)
                return CurrentBestSubject(
                    text_available=True,
                    text=value,
                    text_sha256=sha256_text(value),
                    source_artifact_id=artifact.id if artifact else None,
                    source_artifact_type=artifact_type,
                    source_path=str(path),
                    source_field=field_name,
                )
    return CurrentBestSubject(
        text_available=False,
        text=None,
        text_sha256=None,
        source_artifact_id=None,
        source_artifact_type=None,
        source_path=str(packet_dir),
        source_field=None,
    )


def _build_source_direct_rival_materialization_intake_summary(
    subject: ModelBackedLocalLawDiagnosticSubject,
    packet_dir: Path,
    *,
    client_name: str,
) -> dict[str, object]:
    packet = subject.payloads["direct_rival_subject_materialization_packet"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_direct_rival_materialization_packet_id": (
            subject.materialization_packet_id
        ),
        "source_direct_rival_materialization_packet_dir": str(
            subject.materialization_packet_dir
        ),
        "source_direct_rival_materialization_packet_artifact_id": (
            subject.materialization_packet_artifact_id
        ),
        "source_local_law_packet_id": packet.get("source_local_law_packet_id"),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "direct_rival_text_available": True,
        "rival_text_sha256": subject.materialized_subject.materialized_text_sha256,
        "diagnostic_kind": MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_KIND,
        "client": client_name,
        "model_backed": False,
        "diagnostic_is_provisional": True,
        "materialization_surface_alias_warning": (
            subject.materialization_surface_alias_warning
        ),
        "consumed_materialized_subject_from_artifact": True,
        "alias_warning_detail": (
            "readiness/provenance display aliases were absent; consumed "
            "materialized_direct_rival_subject.json as the canonical source"
            if subject.materialization_surface_alias_warning
            else None
        ),
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_direct_rival_materialization_intake_summary_v1_controller",
    }


def _build_current_best_subject_for_law_comparison(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    current = subject.current_best_subject
    return {
        "current_best_candidate_packet_id": EXPECTED_CURRENT_BEST_PACKET_ID,
        "subject_role": "current_best_candidate",
        "text_available": current.text_available,
        "text_sha256": current.text_sha256,
        "source_artifact_id": current.source_artifact_id,
        "source_artifact_type": current.source_artifact_type,
        "source_path": current.source_path,
        "source_field": current.source_field,
        "word_count": len(current.text.split()) if current.text else 0,
        "comparison_excerpt": _excerpt(current.text),
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "law_question": (
            "Does first-read pressure arise from object-event sequence before "
            "explanation, thesis, or named pressure appears?"
        ),
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "current_best_subject_for_law_comparison_v1_controller",
    }


def _build_direct_rival_subject_for_law_comparison(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    rival = subject.materialized_subject
    return {
        "source_direct_rival_materialization_packet_id": (
            subject.materialization_packet_id
        ),
        "subject_role": "direct_rival_subject",
        "direct_rival_text_available": True,
        "text": rival.materialized_text,
        "text_sha256": rival.materialized_text_sha256,
        "source_artifact_id": rival.source_artifact_id,
        "source_artifact_type": rival.source_artifact_type,
        "source_path": rival.source_path,
        "source_field_path": rival.source_field_path,
        "word_count": len(rival.materialized_text.split()),
        "comparison_excerpt": _excerpt(rival.materialized_text),
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "non_imitation_constraint": "diagnose rival causal advantage without copying it",
        "candidate_generated": False,
        "generation_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "direct_rival_subject_for_law_comparison_v1_controller",
    }


def _build_law_application_comparison_matrix(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    return {
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "law_statement": (
            "A successful next candidate must make first-read pressure arise "
            "from object-event sequence before explanation, thesis, or named "
            "pressure appears."
        ),
        "diagnostic_kind": MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_KIND,
        "model_backed": False,
        "diagnostic_is_provisional": True,
        "rows": [
            {
                "question": "Does packet_0063 make pressure felt before naming it?",
                "packet_0063_assessment": "partial",
                "direct_rival_assessment": "stronger_provisional",
                "finding": (
                    "packet_0063 preserves object field and causal marks, but "
                    "the pressure still appears to arrive conceptually or late."
                ),
            },
            {
                "question": "Does the rival make pressure felt before naming it?",
                "packet_0063_assessment": "weaker_provisional",
                "direct_rival_assessment": "likely_yes",
                "finding": (
                    "The materialized rival subject appears to make the reader "
                    "feel pressure through scene/object arrival before naming "
                    "the pressure."
                ),
            },
            {
                "question": "Which text makes object-event consequence arrive first?",
                "packet_0063_assessment": "object_event_present",
                "direct_rival_assessment": "object_event_more_immediate",
                "finding": "likely direct rival advantage under the discovered local law",
            },
            {
                "question": "Where does packet_0063 explain too soon?",
                "packet_0063_assessment": LIKELY_PACKET_0063_GAP,
                "direct_rival_assessment": "less visibly explanatory",
                "finding": "future diagnosis should locate explanation-before-pressure spans",
            },
            {
                "question": (
                    "Where does the rival produce first-read pressure without explanation?"
                ),
                "packet_0063_assessment": "requires model-backed span diagnosis",
                "direct_rival_assessment": "requires model-backed span diagnosis",
                "finding": "fake mode records the question but does not quote-model diagnose",
            },
            {
                "question": (
                    "What must a future candidate learn without imitating the rival?"
                ),
                "packet_0063_assessment": "preserve object/tactile evidence chain",
                "direct_rival_assessment": "learn causal ordering, not diction or scene",
                "finding": "learn first-read pressure sequencing without transplanting rival form",
            },
        ],
        "current_best_excerpt": _excerpt(subject.current_best_subject.text),
        "direct_rival_excerpt": _excerpt(subject.materialized_subject.materialized_text),
        "generation_allowed": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "law_application_comparison_matrix_v1_controller",
    }


def _build_first_read_pressure_diagnostic_report(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    del subject
    return {
        "diagnostic_kind": MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_KIND,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "model_backed": False,
        "diagnostic_is_provisional": True,
        "required_questions": [
            "Does packet_0063 make pressure felt before naming it?",
            "Does the rival make pressure felt before naming it?",
            "Which text makes object-event consequence arrive first?",
            "Where does packet_0063 explain too soon?",
            "Where does the rival produce first-read pressure without explanation?",
            "What must a future candidate learn without imitating the rival?",
        ],
        "provisional_findings": {
            "packet_0063_pressure_before_naming": "partial_or_uncertain",
            "rival_pressure_before_naming": "likely_stronger",
            "object_event_consequence_arrives_first": "rival_likely_stronger",
            "packet_0063_explanation_risk": LIKELY_PACKET_0063_GAP,
            "rival_support_span_status": "requires future live model-backed diagnostic",
            "future_learning_constraint": "learn law-level causal ordering only",
        },
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "first_read_pressure_diagnostic_report_v1_controller",
    }


def _build_rival_advantage_under_law_report(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    return {
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "source_direct_rival_materialization_packet_id": (
            subject.materialization_packet_id
        ),
        "rival_text_sha256": subject.materialized_subject.materialized_text_sha256,
        "model_backed": False,
        "diagnostic_is_provisional": True,
        "likely_rival_advantage": LIKELY_RIVAL_ADVANTAGE,
        "advantage_description": (
            "The rival likely creates first-read pressure before explanatory "
            "naming; this remains a provisional deterministic diagnosis until "
            "a live schema-bound comparison locates support spans."
        ),
        "strongest_rival_pressure_remains_blocking": True,
        "strongest_rival_defeated": False,
        "strongest_rival_defeat_claim": False,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "rival_advantage_under_law_report_v1_controller",
    }


def _build_packet_0063_law_gap_report(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    return {
        "current_best_candidate_packet_id": EXPECTED_CURRENT_BEST_PACKET_ID,
        "proof_packet_id": EXPECTED_PROOF_PACKET_ID,
        "reader_state_packet_id": EXPECTED_READER_STATE_PACKET_ID,
        "law_id": DISCOVERED_LOCAL_LAW_ID,
        "model_backed": False,
        "diagnostic_is_provisional": True,
        "likely_packet_0063_gap": LIKELY_PACKET_0063_GAP,
        "gap_description": (
            "packet_0063 has object/tactile causal gains, but the discovered "
            "law still points to first-read pressure arriving after conceptual "
            "orientation rather than before it."
        ),
        "current_best_text_available": subject.current_best_subject.text_available,
        "current_best_text_sha256": subject.current_best_subject.text_sha256,
        "future_live_diagnostic_needed": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "packet_0063_law_gap_report_v1_controller",
    }


def _build_non_imitation_constraint_report(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    source_constraints = subject.payloads["non_imitation_constraint_report"]
    constraints = _string_list(
        source_constraints.get("forbidden_imitation_modes")
        or source_constraints.get("constraints")
    )
    if not constraints:
        constraints = list(NON_IMITATION_CONSTRAINTS)
    return {
        "constraints": constraints,
        "forbidden_imitation_modes": constraints,
        "non_imitation_constraints_passed": True,
        "diagnosis_not_imitation": True,
        "diagnose_causal_advantage_only": True,
        "do_not_copy_rival_text": True,
        "do_not_transplant_rival_scene": True,
        "preserve_packet_0063_current_best_evidence_chain": True,
        "preserve_failed_target_memory": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "local_law_rival_non_imitation_constraint_report_v1_controller",
    }


def _build_next_strategy_readiness_report(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    return {
        "recommended_next_strategy_class": NEXT_FAKE_RECOMMENDED_STRATEGY_CLASS,
        "recommended_next_action": NEXT_RECOMMENDED_ACTION,
        "next_recommended_action": NEXT_RECOMMENDED_ACTION,
        "future_likely_next_strategy_class_after_live_model_backed_diagnostic": (
            FUTURE_LIVE_RECOMMENDED_STRATEGY_CLASS
        ),
        "source_direct_rival_materialization_packet_id": (
            subject.materialization_packet_id
        ),
        "direct_rival_text_available": True,
        "rival_text_sha256": subject.materialized_subject.materialized_text_sha256,
        "model_backed": False,
        "diagnostic_is_provisional": True,
        "ready_for_live_model_backed_local_law_diagnostic": True,
        "ready_for_generation": False,
        "generation_allowed": False,
        "next_generation_authorized": False,
        "residual_target_selection_allowed": False,
        "work_order_allowed": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "local_law_rival_next_strategy_readiness_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: ModelBackedLocalLawDiagnosticSubject,
) -> dict[str, object]:
    packet = subject.payloads["direct_rival_subject_materialization_packet"]
    checks = [
        _check("source_materialization_packet_expected", subject.materialization_packet_id.startswith("packet_")),
        _check(
            "current_best_is_packet_0063",
            packet.get("current_best_candidate_packet_id")
            == EXPECTED_CURRENT_BEST_PACKET_ID,
        ),
        _check("proof_is_packet_0034", packet.get("proof_packet_id") == "packet_0034"),
        _check(
            "reader_state_is_packet_0013",
            packet.get("reader_state_packet_id") == "packet_0013",
        ),
        _check("direct_rival_text_materialized", True),
        _check("command_is_diagnostic_only", True),
        _check("no_model_calls_in_fake_mode", True),
        _check("no_new_generation_path_introduced", True),
        _check("no_target_selection_introduced", True),
        _check("no_work_order_path_introduced", True),
        _check("no_ablation_or_reader_state_eval_authorized", True),
        _check("no_imitation_allowed", True),
        _check("finalization_remains_false", True),
    ]
    passed = all(bool(check["passed"]) for check in checks)
    return {
        "checks": checks,
        "passed": passed,
        "project_health_scope_guard_passed": passed,
        "source_chain_coherent": True,
        "source_direct_rival_materialization_packet_id": (
            subject.materialization_packet_id
        ),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "direct_rival_text_available": True,
        "rival_text_sha256": subject.materialized_subject.materialized_text_sha256,
        "materialization_surface_alias_warning": (
            subject.materialization_surface_alias_warning
        ),
        "consumed_materialized_subject_from_artifact": True,
        "command_is_diagnostic_only": True,
        "no_model_calls": True,
        "no_new_generation_path_introduced": True,
        "no_target_selection_introduced": True,
        "no_work_order_path_introduced": True,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "local_law_rival_project_health_scope_guard_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: ModelBackedLocalLawDiagnosticSubject,
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    health = payloads["project_health_scope_guard_report"]
    constraints = payloads["non_imitation_constraint_report"]
    gate_results = [
        _gate_result("source_materialization_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("direct_rival_text_materialized", True),
        _gate_result("local_law_confirmed", True),
        _gate_result("current_best_preserved", True),
        _gate_result(
            "non_imitation_constraints_passed",
            constraints["non_imitation_constraints_passed"] is True,
        ),
        _gate_result("project_health_scope_guard_passed", health["passed"] is True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_residual_target_selected", True),
        _gate_result("no_work_order_created", True),
        _gate_result("no_ablation_authorized", True),
        _gate_result("no_reader_state_eval_authorized", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "finalization_eligible",
            False,
            ["local-law rival diagnostic is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "live model-backed local-law diagnostic has not run",
        "generation remains unauthorized",
        "candidate has not been generated",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    return {
        "passed": False,
        "eligible": False,
        "diagnostic_kind": MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_KIND,
        "source_direct_rival_materialization_packet_id": (
            subject.materialization_packet_id
        ),
        "direct_rival_text_available": True,
        "rival_text_sha256": subject.materialized_subject.materialized_text_sha256,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": [],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Deterministic local-law rival diagnostic recorded provisional "
            "comparison evidence only; generation remains locked."
        ),
        "worker": "local_law_rival_diagnostic_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: ModelBackedLocalLawDiagnosticSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    client_name: str,
) -> dict[str, object]:
    packet = subject.payloads["direct_rival_subject_materialization_packet"]
    readiness = payloads["next_strategy_readiness_report"]
    health = payloads["project_health_scope_guard_report"]
    counts = packet_artifact_count_summary(
        required_artifact_types=MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="model_backed_local_law_diagnostic_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_direct_rival_materialization_packet_id": (
            subject.materialization_packet_id
        ),
        "source_local_law_packet_id": packet.get("source_local_law_packet_id"),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": packet.get("law_id"),
        "direct_rival_text_available": True,
        "rival_text_sha256": subject.materialized_subject.materialized_text_sha256,
        "diagnostic_kind": MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_KIND,
        "client": client_name,
        "model_backed": False,
        "diagnostic_is_provisional": True,
        "likely_rival_advantage": LIKELY_RIVAL_ADVANTAGE,
        "likely_packet_0063_gap": LIKELY_PACKET_0063_GAP,
        "generation_allowed": False,
        "next_recommended_action": readiness["next_recommended_action"],
        "recommended_next_action": readiness["recommended_next_action"],
        "recommended_next_strategy_class": readiness[
            "recommended_next_strategy_class"
        ],
        "future_likely_next_strategy_class_after_live_model_backed_diagnostic": (
            readiness[
                "future_likely_next_strategy_class_after_live_model_backed_diagnostic"
            ]
        ),
        "materialization_surface_alias_warning": (
            subject.materialization_surface_alias_warning
        ),
        "consumed_materialized_subject_from_artifact": True,
        "project_health_scope_guard_passed": health[
            "project_health_scope_guard_passed"
        ],
        "source_chain_coherent": health["source_chain_coherent"],
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "model_backed_local_law_diagnostic_packet",
        ],
        "counts": {
            **counts,
            "model_calls": 0,
            "candidate_artifacts_created": 0,
            "work_order_artifacts_created": 0,
            "residual_target_selection_artifacts_created": 0,
        },
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "ablation_authorized": False,
        "reader_state_eval_authorized": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "gate_report": payloads["local_law_rival_diagnostic_gate_report"],
        "worker": "model_backed_local_law_diagnostic_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["model_backed_local_law_diagnostic_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _read_json_or_none(path: Path) -> object | None:
    try:
        return read_json_file(path)
    except (OSError, ValueError):
        return None


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


def _any_true(
    payloads: dict[str, dict[str, Any]],
    field_names: tuple[str, ...],
) -> bool:
    for payload in payloads.values():
        for field_name in field_names:
            if payload.get(field_name) is True:
                return True
        counts = _as_dict(payload.get("counts"))
        if (
            "candidate_generated" in field_names
            and _int_or_zero(counts.get("candidate_artifacts_created"))
        ):
            return True
        if (
            "work_order_created" in field_names
            and _int_or_zero(counts.get("work_order_artifacts_created"))
        ):
            return True
        if (
            "residual_target_selected" in field_names
            and _int_or_zero(counts.get("residual_target_selection_artifacts_created"))
        ):
            return True
    return False


def _model_calls(payloads: dict[str, dict[str, Any]]) -> int:
    total = 0
    for payload in payloads.values():
        total += _int_or_zero(payload.get("model_calls"))
        total += _int_or_zero(_as_dict(payload.get("counts")).get("model_calls"))
    return total


def _has_final_or_phase_claim(payloads: dict[str, dict[str, Any]]) -> bool:
    for payload in payloads.values():
        if _payload_has_final_or_phase_claim(payload):
            return True
    return False


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


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _refusal(
    *,
    direct_rival_materialization_packet: Path,
    client_name: str,
    message: str,
) -> ModelBackedLocalLawDiagnosticResult:
    return ModelBackedLocalLawDiagnosticResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "client": client_name,
            "direct_rival_materialization_packet": str(
                direct_rival_materialization_packet
            ),
            "candidate_generated": False,
            "generation_authorized": False,
            "next_generation_authorized": False,
            "residual_target_selected": False,
            "work_order_created": False,
            "ablation_authorized": False,
            "reader_state_eval_authorized": False,
            "model_calls": 0,
            "finalization_eligible": False,
            "no_final_claim": True,
            "no_phase_shift_claim": True,
        },
    )


def _required_string(value: object, message: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(message)


def _first_string_or_none(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_zero(value: object) -> int:
    return value if isinstance(value, int) else 0


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _excerpt(text: str | None, *, max_words: int = 32) -> str | None:
    if not text:
        return None
    words = text.strip().split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])
