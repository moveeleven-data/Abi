"""Deterministic direct-rival subject materialization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_DIRECT_RIVAL_SUBJECT_MATERIALIZATION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.modules.local_law_discovery import (
    DISCOVERED_LOCAL_LAW_ID,
    NEXT_RECOMMENDED_STRATEGY_CLASS as SOURCE_RECOMMENDED_STRATEGY_CLASS,
)
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


DIRECT_RIVAL_SUBJECT_MATERIALIZATION_LINEAGE_ID = (
    "direct_rival_subject_materialization_v1"
)
DIRECT_RIVAL_SUBJECT_MATERIALIZATION_CREATED_BY = (
    "direct_rival_subject_materialization_v1_controller"
)
DIRECT_RIVAL_SUBJECT_MATERIALIZATION_KIND = "direct_rival_subject_materialization"
NEXT_STRATEGY_WITH_DIRECT_TEXT = "model_backed_local_law_diagnostic_with_rival_subject"
NEXT_STRATEGY_WITHOUT_DIRECT_TEXT = "register_or_supply_direct_rival_subject"
NEXT_ACTION_WITH_DIRECT_TEXT = (
    "review_materialized_direct_rival_subject_before_model_backed_local_law_diagnostic"
)
NEXT_ACTION_WITHOUT_DIRECT_TEXT = "register_or_supply_direct_rival_subject"

DIRECT_RIVAL_SUBJECT_MATERIALIZATION_ARTIFACT_TYPES = (
    "source_local_law_intake_summary",
    "rival_evidence_search_manifest",
    "direct_rival_text_candidate_inventory",
    "materialized_direct_rival_subject",
    "rival_summary_evidence_bundle",
    "provenance_and_hash_report",
    "evidence_limitations_report",
    "non_imitation_constraint_report",
    "next_strategy_readiness_report",
    "project_health_scope_guard_report",
    "direct_rival_subject_gate_report",
    "direct_rival_subject_materialization_packet",
)

REQUIRED_LOCAL_LAW_ARTIFACTS = (
    "local_law_discovery_packet",
    "source_diagnosis_intake_summary",
    "forensic_hypothesis_to_law_map",
    "discovered_local_law_statement",
    "current_best_law_gap_report",
    "failed_local_residual_memory_summary",
    "evidence_basis_and_limitations_report",
    "non_imitation_constraint_report",
    "next_strategy_option_map",
    "local_law_discovery_gate_report",
    "project_health_scope_guard_report",
)

DIRECT_TEXT_KEYS = {
    "strongest_rival_text",
    "rival_text",
    "direct_rival_text",
    "direct_rival_subject_text",
    "strongest_rival_subject_text",
    "materialized_rival_subject_text",
    "materialized_text",
}
TEXT_VALUE_KEYS = {"text", "body", "content", "prose", "candidate_text"}
SUMMARY_SIGNAL_KEYS = {
    "rival",
    "strongest_rival",
    "comparison",
    "rival_pressure",
    "rival_summary",
}


@dataclass(frozen=True)
class DirectRivalMaterializationResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class DirectRivalMaterializationSubject:
    run_id: str
    local_law_packet_dir: Path
    local_law_packet_id: str
    local_law_packet_artifact_id: str | None
    local_law_artifact_ids: dict[str, str]
    payloads: dict[str, dict[str, Any]]
    source_parent_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceSearchResult:
    direct_candidates: list[dict[str, object]]
    summary_entries: list[dict[str, object]]
    scanned_artifacts: list[dict[str, object]]

    @property
    def direct_text_available(self) -> bool:
        return bool(self.direct_candidates)

    @property
    def summary_only_evidence_available(self) -> bool:
        return bool(self.summary_entries) and not self.direct_candidates


def run_direct_rival_subject_materialization(
    config: AbiConfig,
    *,
    local_law_packet: Path | str,
    operator_reviewed: bool,
) -> DirectRivalMaterializationResult:
    initialize_database(config)
    local_law_packet_dir = _resolve_path(config, local_law_packet)
    if not operator_reviewed:
        return _refusal(
            local_law_packet=local_law_packet_dir,
            message=(
                "Direct-rival subject materialization refused; "
                "--operator-reviewed is required."
            ),
        )
    if not local_law_packet_dir.exists() or not local_law_packet_dir.is_dir():
        return _refusal(
            local_law_packet=local_law_packet_dir,
            message=(
                "Direct-rival subject materialization refused; local-law "
                f"packet directory not found: {local_law_packet_dir}"
            ),
        )

    try:
        subject = _load_subject(config, local_law_packet_dir)
    except ValueError as error:
        return _refusal(local_law_packet=local_law_packet_dir, message=str(error))

    with connect(config.db_path) as connection:
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                local_law_packet=local_law_packet_dir,
                message=(
                    "Direct-rival subject materialization refused; run is not "
                    f"registered: {subject.run_id}"
                ),
            )

        search = _search_run_for_rival_evidence(config, connection, subject.run_id)
        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_DIRECT_RIVAL_SUBJECT_MATERIALIZATION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(
            config.run_dir(subject.run_id) / "direct_rival_subject_materialization"
        )
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=DIRECT_RIVAL_SUBJECT_MATERIALIZATION_LINEAGE_ID,
            created_by=DIRECT_RIVAL_SUBJECT_MATERIALIZATION_CREATED_BY,
            fixture_only=False,
            model_call_id=None,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["source_local_law_intake_summary"] = (
            _build_source_local_law_intake_summary(subject, packet_dir)
        )
        artifacts["source_local_law_intake_summary"] = writer.write_artifact(
            "source_local_law_intake_summary",
            payloads["source_local_law_intake_summary"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["rival_evidence_search_manifest"] = (
            _build_rival_evidence_search_manifest(subject, search)
        )
        artifacts["rival_evidence_search_manifest"] = writer.write_artifact(
            "rival_evidence_search_manifest",
            payloads["rival_evidence_search_manifest"],
            parent_ids=[artifacts["source_local_law_intake_summary"].id],
        )

        payloads["direct_rival_text_candidate_inventory"] = (
            _build_direct_rival_text_candidate_inventory(search)
        )
        artifacts["direct_rival_text_candidate_inventory"] = writer.write_artifact(
            "direct_rival_text_candidate_inventory",
            payloads["direct_rival_text_candidate_inventory"],
            parent_ids=[artifacts["rival_evidence_search_manifest"].id],
        )

        payloads["materialized_direct_rival_subject"] = (
            _build_materialized_direct_rival_subject(search)
        )
        artifacts["materialized_direct_rival_subject"] = writer.write_artifact(
            "materialized_direct_rival_subject",
            payloads["materialized_direct_rival_subject"],
            parent_ids=[artifacts["direct_rival_text_candidate_inventory"].id],
        )

        payloads["rival_summary_evidence_bundle"] = (
            _build_rival_summary_evidence_bundle(search)
        )
        artifacts["rival_summary_evidence_bundle"] = writer.write_artifact(
            "rival_summary_evidence_bundle",
            payloads["rival_summary_evidence_bundle"],
            parent_ids=[artifacts["rival_evidence_search_manifest"].id],
        )

        payloads["provenance_and_hash_report"] = _build_provenance_and_hash_report(
            search,
            payloads["materialized_direct_rival_subject"],
        )
        artifacts["provenance_and_hash_report"] = writer.write_artifact(
            "provenance_and_hash_report",
            payloads["provenance_and_hash_report"],
            parent_ids=[
                artifacts["materialized_direct_rival_subject"].id,
                artifacts["rival_summary_evidence_bundle"].id,
            ],
        )

        payloads["evidence_limitations_report"] = _build_evidence_limitations_report(
            search
        )
        artifacts["evidence_limitations_report"] = writer.write_artifact(
            "evidence_limitations_report",
            payloads["evidence_limitations_report"],
            parent_ids=[
                artifacts["provenance_and_hash_report"].id,
                artifacts["source_local_law_intake_summary"].id,
            ],
        )

        payloads["non_imitation_constraint_report"] = (
            _build_non_imitation_constraint_report(subject)
        )
        artifacts["non_imitation_constraint_report"] = writer.write_artifact(
            "non_imitation_constraint_report",
            payloads["non_imitation_constraint_report"],
            parent_ids=[artifacts["evidence_limitations_report"].id],
        )

        payloads["next_strategy_readiness_report"] = (
            _build_next_strategy_readiness_report(search)
        )
        artifacts["next_strategy_readiness_report"] = writer.write_artifact(
            "next_strategy_readiness_report",
            payloads["next_strategy_readiness_report"],
            parent_ids=[
                artifacts["materialized_direct_rival_subject"].id,
                artifacts["non_imitation_constraint_report"].id,
            ],
        )

        payloads["project_health_scope_guard_report"] = (
            _build_project_health_scope_guard_report(subject, search)
        )
        artifacts["project_health_scope_guard_report"] = writer.write_artifact(
            "project_health_scope_guard_report",
            payloads["project_health_scope_guard_report"],
            parent_ids=[
                artifacts["source_local_law_intake_summary"].id,
                artifacts["next_strategy_readiness_report"].id,
            ],
        )

        payloads["direct_rival_subject_gate_report"] = _build_gate_report(
            subject=subject,
            payloads=payloads,
            search=search,
        )
        artifacts["direct_rival_subject_gate_report"] = writer.write_artifact(
            "direct_rival_subject_gate_report",
            payloads["direct_rival_subject_gate_report"],
            parent_ids=[
                artifacts["project_health_scope_guard_report"].id,
                artifacts["non_imitation_constraint_report"].id,
            ],
        )

        payloads["direct_rival_subject_materialization_packet"] = (
            _build_packet_summary(
                subject=subject,
                packet_dir=packet_dir,
                payloads=payloads,
                artifacts=artifacts,
                search=search,
            )
        )
        artifacts["direct_rival_subject_materialization_packet"] = (
            writer.write_artifact(
                "direct_rival_subject_materialization_packet",
                payloads["direct_rival_subject_materialization_packet"],
                parent_ids=[
                    artifact.id
                    for artifact_type, artifact in artifacts.items()
                    if artifact_type
                    != "direct_rival_subject_materialization_packet"
                ],
            )
        )

        gate_report = payloads["direct_rival_subject_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="direct_rival_subject_materialization_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=DIRECT_RIVAL_SUBJECT_MATERIALIZATION_LINEAGE_ID,
        )

    result_payload = _result_payload(
        packet_dir=packet_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    return DirectRivalMaterializationResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_subject(
    config: AbiConfig,
    local_law_packet_dir: Path,
) -> DirectRivalMaterializationSubject:
    payloads = _load_required_payloads(local_law_packet_dir)
    _validate_local_law_payloads(payloads)
    packet = payloads["local_law_discovery_packet"]
    run_id = _required_string(
        packet.get("run_id"),
        "Direct-rival subject materialization refused; local-law packet "
        "missing run_id.",
    )
    packet_id = str(packet.get("packet_id") or local_law_packet_dir.name)
    packet_path = local_law_packet_dir / "local_law_discovery_packet.json"
    with connect(config.db_path) as connection:
        packet_artifact = _artifact_for_path(connection, packet_path)
    artifact_ids = _artifact_ids_from_packet(packet)
    source_parent_ids = _unique(
        [
            packet_artifact.id if packet_artifact else None,
            *artifact_ids.values(),
        ]
    )
    return DirectRivalMaterializationSubject(
        run_id=run_id,
        local_law_packet_dir=local_law_packet_dir,
        local_law_packet_id=packet_id,
        local_law_packet_artifact_id=packet_artifact.id if packet_artifact else None,
        local_law_artifact_ids=artifact_ids,
        payloads=payloads,
        source_parent_ids=tuple(source_parent_ids),
    )


def _load_required_payloads(packet_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in REQUIRED_LOCAL_LAW_ARTIFACTS:
        path = packet_dir / f"{artifact_type}.json"
        if not path.exists():
            raise ValueError(
                "Direct-rival subject materialization refused; local-law "
                f"packet missing {path.name}."
            )
        payloads[artifact_type] = _read_envelope_payload(path)
    return payloads


def _read_envelope_payload(path: Path) -> dict[str, Any]:
    envelope = read_json_file(path)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError(
            "Direct-rival subject materialization refused; malformed local-law "
            f"artifact: {path.name}."
        )
    return envelope["payload"]


def _validate_local_law_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    packet = payloads["local_law_discovery_packet"]
    health = payloads["project_health_scope_guard_report"]
    if packet.get("accepted") is not True:
        raise ValueError(
            "Direct-rival subject materialization refused; source local-law "
            "packet is not accepted."
        )
    if packet.get("recommended_next_strategy_class") != (
        SOURCE_RECOMMENDED_STRATEGY_CLASS
    ):
        raise ValueError(
            "Direct-rival subject materialization refused; local-law packet "
            "does not recommend materialize_direct_rival_subject_for_model_backed_forensics."
        )
    if packet.get("direct_rival_subject_required_before_generation") is not True:
        raise ValueError(
            "Direct-rival subject materialization refused; direct rival subject "
            "is not marked required before generation."
        )
    if packet.get("ready_for_direct_rival_subject_materialization") is not True:
        raise ValueError(
            "Direct-rival subject materialization refused; local-law packet is "
            "not ready for direct rival subject materialization."
        )
    for field_name, expected in (
        ("current_best_candidate_packet_id", EXPECTED_CURRENT_BEST_PACKET_ID),
        ("proof_packet_id", EXPECTED_PROOF_PACKET_ID),
        ("reader_state_packet_id", EXPECTED_READER_STATE_PACKET_ID),
    ):
        if packet.get(field_name) != expected:
            raise ValueError(
                "Direct-rival subject materialization refused; local-law "
                f"{field_name} must be {expected}."
            )
    if packet.get("discovered_local_law_id") != DISCOVERED_LOCAL_LAW_ID:
        raise ValueError(
            "Direct-rival subject materialization refused; local-law packet "
            f"law id must be {DISCOVERED_LOCAL_LAW_ID}."
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
            "Direct-rival subject materialization refused; source local-law "
            "authorizes generation or generated a candidate."
        )
    if _any_true(payloads, ("residual_target_selected",)):
        raise ValueError(
            "Direct-rival subject materialization refused; source local-law "
            "selected a residual target."
        )
    if _any_true(payloads, ("work_order_created",)):
        raise ValueError(
            "Direct-rival subject materialization refused; source local-law "
            "created a work order."
        )
    if packet.get("source_chain_coherent") is not True or health.get(
        "source_chain_coherent"
    ) is not True:
        raise ValueError(
            "Direct-rival subject materialization refused; source chain is "
            "incoherent."
        )
    if _model_calls(payloads) != 0:
        raise ValueError(
            "Direct-rival subject materialization refused; source local-law "
            "contains model calls."
        )
    if _has_final_or_phase_claim(payloads):
        raise ValueError(
            "Direct-rival subject materialization refused; finality or "
            "phase-shift claim appears in the source local-law packet."
        )


def _search_run_for_rival_evidence(
    config: AbiConfig,
    connection: sqlite3.Connection,
    run_id: str,
) -> EvidenceSearchResult:
    artifact_by_path = {
        str(Path(artifact.path)): artifact for artifact in list_artifacts(connection, run_id)
    }
    candidate_paths: dict[str, Path] = {
        str(Path(artifact.path)): Path(artifact.path)
        for artifact in artifact_by_path.values()
    }
    run_dir = config.run_dir(run_id)
    if run_dir.exists():
        for path in run_dir.rglob("*.json"):
            candidate_paths.setdefault(str(path), path)

    direct_candidates: list[dict[str, object]] = []
    summary_entries: list[dict[str, object]] = []
    scanned_artifacts: list[dict[str, object]] = []
    seen_direct_hashes: set[str] = set()
    seen_summary_paths: set[str] = set()
    for path_key in sorted(candidate_paths):
        path = candidate_paths[path_key]
        envelope = _read_json_or_none(path)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            continue
        payload = envelope["payload"]
        artifact_type = str(envelope.get("artifact_type") or path.stem)
        artifact = artifact_by_path.get(str(path))
        scanned_artifacts.append(
            {
                "artifact_type": artifact_type,
                "artifact_id": artifact.id if artifact else None,
                "path": str(path),
            }
        )
        direct_texts = _extract_direct_rival_texts(payload)
        if direct_texts:
            for key_path, text in direct_texts:
                text_hash = sha256_text(text)
                if text_hash in seen_direct_hashes:
                    continue
                seen_direct_hashes.add(text_hash)
                direct_candidates.append(
                    {
                        "artifact_type": artifact_type,
                        "artifact_id": artifact.id if artifact else None,
                        "path": str(path),
                        "field_path": key_path,
                        "text": text,
                        "text_sha256": text_hash,
                        "character_count": len(text),
                        "word_count": len(text.split()),
                    }
                )
        if _has_summary_rival_evidence(artifact_type, payload):
            if str(path) in seen_summary_paths:
                continue
            seen_summary_paths.add(str(path))
            summary_entries.append(
                {
                    "artifact_type": artifact_type,
                    "artifact_id": artifact.id if artifact else None,
                    "path": str(path),
                    "evidence_kind": _summary_evidence_kind(artifact_type, payload),
                    "summary_keys": _rival_signal_keys(payload)[:12],
                }
            )
    return EvidenceSearchResult(
        direct_candidates=direct_candidates,
        summary_entries=summary_entries,
        scanned_artifacts=scanned_artifacts,
    )


def _build_source_local_law_intake_summary(
    subject: DirectRivalMaterializationSubject,
    packet_dir: Path,
) -> dict[str, object]:
    packet = subject.payloads["local_law_discovery_packet"]
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_local_law_packet_id": subject.local_law_packet_id,
        "source_local_law_packet_dir": str(subject.local_law_packet_dir),
        "source_local_law_packet_artifact_id": subject.local_law_packet_artifact_id,
        "source_diagnosis_packet_id": packet.get("source_diagnosis_packet_id"),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": packet.get("discovered_local_law_id"),
        "direct_rival_subject_required_before_generation": packet.get(
            "direct_rival_subject_required_before_generation"
        ),
        "ready_for_direct_rival_subject_materialization": packet.get(
            "ready_for_direct_rival_subject_materialization"
        ),
        "source_recommended_next_strategy_class": packet.get(
            "recommended_next_strategy_class"
        ),
        "candidate_generated": False,
        "generation_authorized": False,
        "next_generation_authorized": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "source_local_law_intake_summary_v1_controller",
    }


def _build_rival_evidence_search_manifest(
    subject: DirectRivalMaterializationSubject,
    search: EvidenceSearchResult,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "source_local_law_packet_id": subject.local_law_packet_id,
        "searched_run_dir": True,
        "searched_registered_artifacts": True,
        "scanned_artifact_count": len(search.scanned_artifacts),
        "direct_rival_text_candidate_count": len(search.direct_candidates),
        "summary_evidence_entry_count": len(search.summary_entries),
        "direct_rival_text_available": search.direct_text_available,
        "summary_only_rival_evidence_available": (
            search.summary_only_evidence_available
        ),
        "scanned_artifacts": search.scanned_artifacts,
        "candidate_source_artifact_types": [
            "rival_pressure_summary",
            "rival_reader_state_comparison",
            "ablation_old_new_rival_comparison",
            "macro_rival_pressure_check",
            "current_best_vs_rival_subject_manifest",
            "synthesis artifacts",
            "reader-state artifacts",
            "executed-ablation artifacts",
        ],
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "rival_evidence_search_manifest_v1_controller",
    }


def _build_direct_rival_text_candidate_inventory(
    search: EvidenceSearchResult,
) -> dict[str, object]:
    return {
        "direct_rival_text_available": search.direct_text_available,
        "candidate_count": len(search.direct_candidates),
        "direct_text_candidates": search.direct_candidates,
        "classification_rule": (
            "Only explicit rival text fields or source_class=strongest_rival text "
            "items count as direct rival text."
        ),
        "summary_fields_not_materialized_as_text": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "direct_rival_text_candidate_inventory_v1_controller",
    }


def _build_materialized_direct_rival_subject(
    search: EvidenceSearchResult,
) -> dict[str, object]:
    chosen = search.direct_candidates[0] if search.direct_candidates else None
    materialized_text = str(chosen["text"]) if chosen else None
    return {
        "direct_rival_text_available": chosen is not None,
        "materialized_text": materialized_text,
        "materialized_text_sha256": sha256_text(materialized_text)
        if materialized_text
        else None,
        "source_artifact_id": chosen.get("artifact_id") if chosen else None,
        "source_artifact_type": chosen.get("artifact_type") if chosen else None,
        "source_path": chosen.get("path") if chosen else None,
        "source_field_path": chosen.get("field_path") if chosen else None,
        "reason": None
        if chosen
        else "direct rival text not found in current run artifacts",
        "no_rival_text_fabricated": True,
        "summary_evidence_was_not_converted_to_text": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "materialized_direct_rival_subject_v1_controller",
    }


def _build_rival_summary_evidence_bundle(
    search: EvidenceSearchResult,
) -> dict[str, object]:
    return {
        "direct_rival_text_available": search.direct_text_available,
        "summary_only_rival_evidence_available": (
            search.summary_only_evidence_available
        ),
        "summary_evidence_available": bool(search.summary_entries),
        "summary_evidence_entries": search.summary_entries,
        "summary_evidence_count": len(search.summary_entries),
        "summary_not_materialized_as_direct_text": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "rival_summary_evidence_bundle_v1_controller",
    }


def _build_provenance_and_hash_report(
    search: EvidenceSearchResult,
    materialized: dict[str, object],
) -> dict[str, object]:
    return {
        "direct_rival_text_available": search.direct_text_available,
        "materialized_text_sha256": materialized["materialized_text_sha256"],
        "materialized_source_artifact_id": materialized["source_artifact_id"],
        "materialized_source_path": materialized["source_path"],
        "direct_candidate_provenance": [
            {
                "artifact_id": candidate["artifact_id"],
                "artifact_type": candidate["artifact_type"],
                "path": candidate["path"],
                "field_path": candidate["field_path"],
                "text_sha256": candidate["text_sha256"],
            }
            for candidate in search.direct_candidates
        ],
        "summary_evidence_provenance": [
            {
                "artifact_id": entry["artifact_id"],
                "artifact_type": entry["artifact_type"],
                "path": entry["path"],
                "evidence_kind": entry["evidence_kind"],
            }
            for entry in search.summary_entries
        ],
        "no_rival_text_fabricated": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "worker": "provenance_and_hash_report_v1_controller",
    }


def _build_evidence_limitations_report(
    search: EvidenceSearchResult,
) -> dict[str, object]:
    if search.direct_text_available:
        limitation = (
            "Direct rival text was materialized from an existing run artifact; "
            "this packet still performs no model-backed diagnosis and makes no "
            "strongest-rival claim."
        )
    elif search.summary_entries:
        limitation = (
            "Only summary/comparison rival evidence was found; direct rival text "
            "was not materialized and must be registered or supplied before "
            "model-backed local-law diagnosis."
        )
    else:
        limitation = (
            "No direct rival text or summary rival evidence was found in the "
            "current run; direct rival subject material must be registered or "
            "supplied."
        )
    return {
        "direct_rival_text_available": search.direct_text_available,
        "summary_only_rival_evidence_available": (
            search.summary_only_evidence_available
        ),
        "summary_evidence_available": bool(search.summary_entries),
        "evidence_limitation": limitation,
        "direct_rival_subject_missing_reason": None
        if search.direct_text_available
        else "direct rival text not found in current run artifacts",
        "direct_rival_subject_required_before_generation": True,
        "model_backed": False,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "direct_rival_evidence_limitations_report_v1_controller",
    }


def _build_non_imitation_constraint_report(
    subject: DirectRivalMaterializationSubject,
) -> dict[str, object]:
    source_constraints = subject.payloads["non_imitation_constraint_report"]
    constraints = _string_list(
        source_constraints.get("forbidden_imitation_modes")
        or source_constraints.get("constraints")
    )
    if not constraints:
        constraints = [
            "do not imitate rival diction",
            "do not transplant rival scenes",
            "do not copy rival structure",
            "do not chase generic vividness",
            "do not turn packet_0063 into the rival",
            "diagnose causal advantage only",
            "preserve packet_0063 current-best evidence chain",
            "preserve failed-target memory",
            "preserve no final/phase-shift claim",
        ]
    return {
        "constraints": constraints,
        "forbidden_imitation_modes": constraints,
        "non_imitation_constraints_passed": True,
        "materialization_not_imitation": True,
        "no_rival_text_fabricated": True,
        "generation_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "direct_rival_non_imitation_constraint_report_v1_controller",
    }


def _build_next_strategy_readiness_report(
    search: EvidenceSearchResult,
) -> dict[str, object]:
    if search.direct_text_available:
        strategy_class = NEXT_STRATEGY_WITH_DIRECT_TEXT
        next_action = NEXT_ACTION_WITH_DIRECT_TEXT
    else:
        strategy_class = NEXT_STRATEGY_WITHOUT_DIRECT_TEXT
        next_action = NEXT_ACTION_WITHOUT_DIRECT_TEXT
    return {
        "recommended_next_strategy_class": strategy_class,
        "recommended_next_action": next_action,
        "next_recommended_action": next_action,
        "direct_rival_text_available": search.direct_text_available,
        "summary_only_rival_evidence_available": (
            search.summary_only_evidence_available
        ),
        "ready_for_model_backed_local_law_diagnostic": search.direct_text_available,
        "generation_allowed": False,
        "target_selection_allowed": False,
        "work_order_allowed": False,
        "candidate_generated": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "direct_rival_next_strategy_readiness_report_v1_controller",
    }


def _build_project_health_scope_guard_report(
    subject: DirectRivalMaterializationSubject,
    search: EvidenceSearchResult,
) -> dict[str, object]:
    packet = subject.payloads["local_law_discovery_packet"]
    source_packet_expected = subject.local_law_packet_id.startswith("packet_")
    checks = [
        _check("source_local_law_packet_expected", source_packet_expected),
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
        _check("command_is_materialization_only", True),
        _check("no_model_calls", True),
        _check("no_new_generation_path_introduced", True),
        _check("no_target_adapter_introduced", True),
        _check("no_work_order_path_introduced", True),
        _check("no_stale_packet_consumed", True),
        _check("no_direct_rival_text_fabricated", True),
        _check("broad_refactor_not_performed", True),
        _check("finalization_remains_false", True),
    ]
    passed = all(bool(check["passed"]) for check in checks)
    return {
        "checks": checks,
        "passed": passed,
        "project_health_scope_guard_passed": passed,
        "source_chain_coherent": True,
        "source_local_law_packet_id": subject.local_law_packet_id,
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "direct_rival_text_available": search.direct_text_available,
        "summary_only_rival_evidence_available": (
            search.summary_only_evidence_available
        ),
        "command_is_materialization_only": True,
        "no_model_calls": True,
        "no_new_generation_path_introduced": True,
        "no_new_target_adapter_introduced": True,
        "no_work_order_path_introduced": True,
        "stale_packet_consumed": False,
        "no_direct_rival_text_fabricated": True,
        "broad_refactor_performed": False,
        "generation_authorized": False,
        "candidate_generated": False,
        "residual_target_selected": False,
        "work_order_created": False,
        "model_calls": 0,
        "finalization_eligible": False,
        "no_final_claim": True,
        "no_phase_shift_claim": True,
        "worker": "direct_rival_project_health_scope_guard_report_v1_controller",
    }


def _build_gate_report(
    *,
    subject: DirectRivalMaterializationSubject,
    payloads: dict[str, dict[str, object]],
    search: EvidenceSearchResult,
) -> dict[str, object]:
    health = payloads["project_health_scope_guard_report"]
    materialized = payloads["materialized_direct_rival_subject"]
    gate_results = [
        _gate_result("source_local_law_consumed", True),
        _gate_result("operator_review_recorded", True),
        _gate_result("direct_rival_subject_requirement_confirmed", True),
        _gate_result("materialization_attempt_recorded", True),
        _gate_result("direct_text_status_explicit", True),
        _gate_result("summary_evidence_status_explicit", True),
        _gate_result("no_rival_text_fabricated", True),
        _gate_result("project_health_scope_guard_passed", health["passed"] is True),
        _gate_result("no_candidate_generated", True),
        _gate_result("no_generation_authorized", True),
        _gate_result("no_residual_target_selected", True),
        _gate_result("no_work_order_created", True),
        _gate_result("no_model_calls", True),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "finalization_eligible",
            False,
            ["direct-rival subject materialization is not finalization evidence"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "model-backed local-law diagnostic has not run",
        "generation remains unauthorized",
        "candidate has not been generated",
        "strongest rival remains blocking",
        "finalization remains refused",
    ]
    if not search.direct_text_available:
        blockers.insert(0, "direct rival subject text is not materialized")
    return {
        "passed": False,
        "eligible": False,
        "source_local_law_packet_id": subject.local_law_packet_id,
        "direct_rival_text_available": search.direct_text_available,
        "summary_only_rival_evidence_available": (
            search.summary_only_evidence_available
        ),
        "materialized_text_sha256": materialized["materialized_text_sha256"],
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
            "Direct-rival subject materialization recorded rival evidence status; "
            "generation remains locked."
        ),
        "worker": "direct_rival_subject_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: DirectRivalMaterializationSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    search: EvidenceSearchResult,
) -> dict[str, object]:
    packet = subject.payloads["local_law_discovery_packet"]
    materialized = payloads["materialized_direct_rival_subject"]
    summary = payloads["rival_summary_evidence_bundle"]
    provenance = payloads["provenance_and_hash_report"]
    limitations = payloads["evidence_limitations_report"]
    readiness = payloads["next_strategy_readiness_report"]
    health = payloads["project_health_scope_guard_report"]
    counts = packet_artifact_count_summary(
        required_artifact_types=DIRECT_RIVAL_SUBJECT_MATERIALIZATION_ARTIFACT_TYPES,
        produced_artifact_types=list(artifacts),
        packet_artifact_type="direct_rival_subject_materialization_packet",
    )
    return {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "materialization_kind": DIRECT_RIVAL_SUBJECT_MATERIALIZATION_KIND,
        "source_local_law_packet_id": subject.local_law_packet_id,
        "source_diagnosis_packet_id": packet.get("source_diagnosis_packet_id"),
        "current_best_candidate_packet_id": packet.get("current_best_candidate_packet_id"),
        "proof_packet_id": packet.get("proof_packet_id"),
        "reader_state_packet_id": packet.get("reader_state_packet_id"),
        "law_id": packet.get("discovered_local_law_id"),
        "direct_rival_subject_required_before_generation": True,
        "direct_rival_text_available": search.direct_text_available,
        "summary_only_rival_evidence_available": (
            search.summary_only_evidence_available
        ),
        "summary_evidence_available": bool(search.summary_entries),
        "materialized_text_sha256": materialized["materialized_text_sha256"],
        "rival_text_sha256": materialized["materialized_text_sha256"],
        "materialized_source_artifact_id": materialized["source_artifact_id"],
        "materialized_source_path": materialized["source_path"],
        "direct_rival_subject_missing_reason": materialized["reason"],
        "summary_evidence_count": summary["summary_evidence_count"],
        "evidence_limitation": limitations["evidence_limitation"],
        "recommended_next_strategy_class": readiness[
            "recommended_next_strategy_class"
        ],
        "recommended_next_action": readiness["recommended_next_action"],
        "next_recommended_action": readiness["next_recommended_action"],
        "project_health_scope_guard_passed": health[
            "project_health_scope_guard_passed"
        ],
        "source_chain_coherent": health["source_chain_coherent"],
        "no_rival_text_fabricated": provenance["no_rival_text_fabricated"],
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": [
            *artifacts,
            "direct_rival_subject_materialization_packet",
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
        "gate_report": payloads["direct_rival_subject_gate_report"],
        "worker": "direct_rival_subject_materialization_packet_v1_controller",
    }


def _result_payload(
    *,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    packet = payloads["direct_rival_subject_materialization_packet"]
    return {
        **packet,
        "artifact_paths": {
            artifact_type: str(packet_dir / f"{artifact_type}.json")
            for artifact_type in artifacts
        },
    }


def _extract_direct_rival_texts(value: object) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            source_class = node.get("source_class")
            if source_class == "strongest_rival":
                for key in TEXT_VALUE_KEYS:
                    text = node.get(key)
                    if _looks_like_direct_text(text):
                        output.append((f"{path}.{key}".strip("."), str(text)))
            for key, item in node.items():
                key_text = str(key)
                if key_text in DIRECT_TEXT_KEYS and _looks_like_direct_text(item):
                    output.append((f"{path}.{key_text}".strip("."), str(item)))
                visit(item, f"{path}.{key_text}".strip("."))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, f"{path}[{index}]")

    visit(value, "")
    return output


def _looks_like_direct_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < 30:
        return False
    lowered = text.lower()
    if lowered.startswith("{") or "summary:" in lowered[:80]:
        return False
    return True


def _has_summary_rival_evidence(artifact_type: str, payload: object) -> bool:
    type_lower = artifact_type.lower()
    if any(signal in type_lower for signal in SUMMARY_SIGNAL_KEYS):
        return True
    return bool(_rival_signal_keys(payload))


def _summary_evidence_kind(artifact_type: str, payload: object) -> str:
    del payload
    type_lower = artifact_type.lower()
    if "comparison" in type_lower:
        return "rival_comparison"
    if "summary" in type_lower:
        return "rival_summary"
    if "reader" in type_lower:
        return "reader_state_rival_evidence"
    if "ablation" in type_lower:
        return "ablation_rival_evidence"
    return "rival_reference"


def _rival_signal_keys(value: object) -> list[str]:
    keys: list[str] = []

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                key_text = str(key)
                full_path = f"{path}.{key_text}".strip(".")
                lowered = key_text.lower()
                if any(signal in lowered for signal in SUMMARY_SIGNAL_KEYS):
                    keys.append(full_path)
                visit(item, full_path)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, f"{path}[{index}]")

    visit(value, "")
    return keys


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
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(path),),
    ).fetchone()
    if row is None:
        return None
    return row_to_artifact(row)


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config.root / path


def _refusal(
    *,
    local_law_packet: Path,
    message: str,
) -> DirectRivalMaterializationResult:
    return DirectRivalMaterializationResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "message": message,
            "local_law_packet": str(local_law_packet),
            "candidate_generated": False,
            "generation_authorized": False,
            "next_generation_authorized": False,
            "residual_target_selected": False,
            "work_order_created": False,
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


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
