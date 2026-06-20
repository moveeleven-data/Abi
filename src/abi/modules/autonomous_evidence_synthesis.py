"""Deterministic autonomous evidence synthesis packet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_EVIDENCE_SYNTHESIS_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.packets import PacketWriter, create_packet_dir, read_json_file


AUTONOMOUS_EVIDENCE_SYNTHESIS_LINEAGE_ID = "autonomous_evidence_synthesis_v1"
AUTONOMOUS_EVIDENCE_SYNTHESIS_CREATED_BY = "autonomous_evidence_synthesis_v1_controller"

AUTONOMOUS_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES = (
    "autonomous_evidence_synthesis_subject_manifest",
    "repair_history_table",
    "causal_status_summary",
    "best_current_candidate_selection",
    "failed_or_rejected_repairs",
    "exhausted_handle_report",
    "rival_pressure_summary",
    "residual_blocker_map",
    "local_law_case_notes",
    "strategic_decision_report",
    "macro_recomposition_brief",
    "synthesis_gate_report",
    "autonomous_evidence_synthesis_packet",
)

KNOWN_SYNTHESIS_RUN_ID = "run_8fa54199f23f3d8e"
KNOWN_PACKET_CHAIN = (
    ("pilot_artifact_set", "packet_0017"),
    ("internal_reader_lab", "packet_0014"),
    ("autonomous_revision", "packet_0030"),
    ("executed_ablation", "packet_0004"),
    ("ablation_informed_revision", "packet_0006"),
    ("executed_ablation", "packet_0008"),
    ("ablation_informed_revision", "packet_0010"),
    ("executed_ablation", "packet_0010"),
    ("ablation_informed_revision", "packet_0012"),
    ("ablation_informed_revision", "packet_0014"),
    ("executed_ablation", "packet_0012"),
    ("ablation_informed_revision", "packet_0022"),
    ("executed_ablation", "packet_0014"),
)

SOURCE_PACKET_FILES = {
    "pilot_artifact_set": "pilot_packet.json",
    "internal_reader_lab": "internal_reader_lab_packet.json",
    "autonomous_revision": "autonomous_closed_loop_packet.json",
    "executed_ablation": "executed_ablation_packet.json",
    "ablation_informed_revision": "cycle2_packet.json",
}

CRITICAL_SOURCE_KINDS = (
    "pilot_artifact_set",
    "internal_reader_lab",
    "autonomous_revision",
    "executed_ablation",
    "ablation_informed_revision",
)


@dataclass(frozen=True)
class EvidenceSynthesisResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class SourcePacket:
    packet_kind: str
    packet_id: str
    packet_dir: Path
    packet_file: Path
    envelope: dict[str, Any]
    payload: dict[str, Any]
    packet_artifact_id: str | None
    artifact_ids: dict[str, str]
    parent_artifact_ids: tuple[str, ...]
    fixture_only: bool
    model_backed: bool
    model_call_ids: tuple[str, ...]
    created_at: str


def run_autonomous_evidence_synthesis(
    config: AbiConfig,
    *,
    run_id: str,
) -> EvidenceSynthesisResult:
    initialize_database(config)
    run_dir = config.run_dir(run_id)
    if not run_dir.exists():
        return _refusal(
            run_id=run_id,
            message=f"Autonomous evidence synthesis refused; run folder not found: {run_dir}",
        )

    with connect(config.db_path) as connection:
        if get_run(connection, run_id) is None:
            return _refusal(
                run_id=run_id,
                message=f"Autonomous evidence synthesis refused; run is not registered: {run_id}",
            )

        sources, missing_expected = _discover_source_packets(connection, config, run_id)
        critical_missing = _critical_missing(sources)
        if critical_missing:
            return _refusal(
                run_id=run_id,
                message=(
                    "Autonomous evidence synthesis refused; missing critical source "
                    f"packet kinds: {', '.join(critical_missing)}"
                ),
                missing_critical_source_kinds=critical_missing,
                missing_expected_source_packets=missing_expected,
            )

        set_active_phase(connection, run_id, AUTONOMOUS_EVIDENCE_SYNTHESIS_ACTIVE_PHASE)
        packet_dir = create_packet_dir(run_dir / "autonomous_evidence_synthesis")
        fixture_only = any(source.fixture_only for source in sources)
        writer = PacketWriter(
            connection=connection,
            run_id=run_id,
            packet_dir=packet_dir,
            lineage_id=AUTONOMOUS_EVIDENCE_SYNTHESIS_LINEAGE_ID,
            created_by=AUTONOMOUS_EVIDENCE_SYNTHESIS_CREATED_BY,
            fixture_only=fixture_only,
        )

        source_parent_ids = _unique(
            parent_id
            for source in sources
            for parent_id in source.parent_artifact_ids
            if parent_id
        )
        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["autonomous_evidence_synthesis_subject_manifest"] = _build_subject_manifest(
            run_id=run_id,
            packet_dir=packet_dir,
            sources=sources,
            missing_expected=missing_expected,
            critical_missing=critical_missing,
        )
        artifacts["autonomous_evidence_synthesis_subject_manifest"] = writer.write_artifact(
            "autonomous_evidence_synthesis_subject_manifest",
            payloads["autonomous_evidence_synthesis_subject_manifest"],
            parent_ids=source_parent_ids,
        )

        history = _build_repair_history(sources)
        payloads["repair_history_table"] = history
        artifacts["repair_history_table"] = writer.write_artifact(
            "repair_history_table",
            history,
            parent_ids=[
                artifacts["autonomous_evidence_synthesis_subject_manifest"].id,
                *source_parent_ids,
            ],
        )

        payloads["causal_status_summary"] = _build_causal_status_summary(history)
        artifacts["causal_status_summary"] = writer.write_artifact(
            "causal_status_summary",
            payloads["causal_status_summary"],
            parent_ids=[artifacts["repair_history_table"].id],
        )

        payloads["best_current_candidate_selection"] = _build_best_candidate_selection(
            sources,
            history,
        )
        artifacts["best_current_candidate_selection"] = writer.write_artifact(
            "best_current_candidate_selection",
            payloads["best_current_candidate_selection"],
            parent_ids=[
                artifacts["repair_history_table"].id,
                artifacts["causal_status_summary"].id,
            ],
        )

        payloads["failed_or_rejected_repairs"] = _build_failed_or_rejected_repairs(history)
        artifacts["failed_or_rejected_repairs"] = writer.write_artifact(
            "failed_or_rejected_repairs",
            payloads["failed_or_rejected_repairs"],
            parent_ids=[artifacts["repair_history_table"].id],
        )

        payloads["exhausted_handle_report"] = _build_exhausted_handle_report(history)
        artifacts["exhausted_handle_report"] = writer.write_artifact(
            "exhausted_handle_report",
            payloads["exhausted_handle_report"],
            parent_ids=[
                artifacts["repair_history_table"].id,
                artifacts["causal_status_summary"].id,
            ],
        )

        payloads["rival_pressure_summary"] = _build_rival_pressure_summary(sources, history)
        artifacts["rival_pressure_summary"] = writer.write_artifact(
            "rival_pressure_summary",
            payloads["rival_pressure_summary"],
            parent_ids=[
                artifacts["repair_history_table"].id,
                artifacts["best_current_candidate_selection"].id,
            ],
        )

        payloads["residual_blocker_map"] = _build_residual_blocker_map(
            payloads["exhausted_handle_report"],
            payloads["rival_pressure_summary"],
        )
        artifacts["residual_blocker_map"] = writer.write_artifact(
            "residual_blocker_map",
            payloads["residual_blocker_map"],
            parent_ids=[
                artifacts["exhausted_handle_report"].id,
                artifacts["rival_pressure_summary"].id,
            ],
        )

        payloads["local_law_case_notes"] = _build_local_law_case_notes(history)
        artifacts["local_law_case_notes"] = writer.write_artifact(
            "local_law_case_notes",
            payloads["local_law_case_notes"],
            parent_ids=[
                artifacts["repair_history_table"].id,
                artifacts["residual_blocker_map"].id,
            ],
        )

        payloads["strategic_decision_report"] = _build_strategic_decision_report(
            payloads["causal_status_summary"],
            payloads["best_current_candidate_selection"],
            payloads["exhausted_handle_report"],
            payloads["rival_pressure_summary"],
        )
        artifacts["strategic_decision_report"] = writer.write_artifact(
            "strategic_decision_report",
            payloads["strategic_decision_report"],
            parent_ids=[
                artifacts["causal_status_summary"].id,
                artifacts["best_current_candidate_selection"].id,
                artifacts["exhausted_handle_report"].id,
                artifacts["rival_pressure_summary"].id,
            ],
        )

        payloads["macro_recomposition_brief"] = _build_macro_recomposition_brief(
            payloads["best_current_candidate_selection"],
            payloads["failed_or_rejected_repairs"],
            payloads["exhausted_handle_report"],
            payloads["rival_pressure_summary"],
            payloads["local_law_case_notes"],
        )
        artifacts["macro_recomposition_brief"] = writer.write_artifact(
            "macro_recomposition_brief",
            payloads["macro_recomposition_brief"],
            parent_ids=[
                artifacts["best_current_candidate_selection"].id,
                artifacts["failed_or_rejected_repairs"].id,
                artifacts["exhausted_handle_report"].id,
                artifacts["rival_pressure_summary"].id,
                artifacts["local_law_case_notes"].id,
            ],
        )

        payloads["synthesis_gate_report"] = _build_gate_report(
            subject_manifest=payloads["autonomous_evidence_synthesis_subject_manifest"],
            best_candidate=payloads["best_current_candidate_selection"],
            failed_repairs=payloads["failed_or_rejected_repairs"],
            exhausted_handles=payloads["exhausted_handle_report"],
            rival_pressure=payloads["rival_pressure_summary"],
            macro_brief=payloads["macro_recomposition_brief"],
        )
        artifacts["synthesis_gate_report"] = writer.write_artifact(
            "synthesis_gate_report",
            payloads["synthesis_gate_report"],
            parent_ids=[
                artifacts["autonomous_evidence_synthesis_subject_manifest"].id,
                artifacts["best_current_candidate_selection"].id,
                artifacts["failed_or_rejected_repairs"].id,
                artifacts["exhausted_handle_report"].id,
                artifacts["rival_pressure_summary"].id,
                artifacts["macro_recomposition_brief"].id,
            ],
        )

        payloads["autonomous_evidence_synthesis_packet"] = _build_packet_summary(
            run_id=run_id,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
            sources=sources,
        )
        artifacts["autonomous_evidence_synthesis_packet"] = writer.write_artifact(
            "autonomous_evidence_synthesis_packet",
            payloads["autonomous_evidence_synthesis_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "autonomous_evidence_synthesis_packet"
            ],
        )

        gate_report = payloads["synthesis_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=run_id,
            gate_name="autonomous_evidence_synthesis_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=AUTONOMOUS_EVIDENCE_SYNTHESIS_LINEAGE_ID,
        )

    result_payload = {
        "accepted": True,
        "run_id": run_id,
        "packet_dir": str(packet_dir),
        "packet_id": packet_dir.name,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "source_packet_count": len(sources),
        "best_current_candidate": payloads["best_current_candidate_selection"][
            "selected_best_candidate"
        ],
        "strategic_decision": payloads["strategic_decision_report"]["recommendation"],
        "next_recommended_action": payloads["strategic_decision_report"][
            "next_recommended_action"
        ],
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "not_human_validated": True,
    }
    return EvidenceSynthesisResult(
        exit_code=0,
        payload=result_payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _discover_source_packets(
    connection: sqlite3.Connection,
    config: AbiConfig,
    run_id: str,
) -> tuple[list[SourcePacket], list[str]]:
    run_dir = config.run_dir(run_id)
    missing_expected: list[str] = []
    packet_dirs: list[tuple[str, Path]] = []
    if run_id == KNOWN_SYNTHESIS_RUN_ID:
        for packet_kind, packet_id in KNOWN_PACKET_CHAIN:
            packet_dir = run_dir / packet_kind / packet_id
            if packet_dir.exists():
                packet_dirs.append((packet_kind, packet_dir))
            else:
                missing_expected.append(str(packet_dir))
    else:
        for packet_kind in SOURCE_PACKET_FILES:
            packet_base = run_dir / packet_kind
            if not packet_base.exists():
                continue
            for packet_dir in sorted(packet_base.glob("packet_*"), key=_packet_sort_key):
                if packet_dir.is_dir():
                    packet_dirs.append((packet_kind, packet_dir))

    sources: list[SourcePacket] = []
    for packet_kind, packet_dir in packet_dirs:
        source = _load_source_packet(connection, packet_kind, packet_dir)
        if source is not None:
            sources.append(source)
    return sources, missing_expected


def _load_source_packet(
    connection: sqlite3.Connection,
    packet_kind: str,
    packet_dir: Path,
) -> SourcePacket | None:
    packet_file = packet_dir / SOURCE_PACKET_FILES[packet_kind]
    if not packet_file.exists():
        return None
    envelope = read_json_file(packet_file)
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return None
    artifact_ids = payload.get("artifact_ids", {})
    if not isinstance(artifact_ids, dict):
        artifact_ids = {}
    packet_artifact = _artifact_for_path(connection, packet_file)
    packet_artifact_id = packet_artifact.id if packet_artifact is not None else None
    parent_ids = _unique(
        [
            packet_artifact_id,
            *[str(value) for value in artifact_ids.values() if isinstance(value, str)],
        ]
    )
    model_call_ids = tuple(
        str(value)
        for value in payload.get("model_call_ids", [])
        if isinstance(value, str)
    )
    fixture_only = bool(envelope.get("fixture_only") or payload.get("fixture_only"))
    model_backed = bool(
        model_call_ids
        or payload.get("model_driver_backed")
        or payload.get("client") == "openai"
    )
    created_at = packet_artifact.created_at if packet_artifact is not None else ""
    return SourcePacket(
        packet_kind=packet_kind,
        packet_id=str(payload.get("packet_id") or packet_dir.name),
        packet_dir=packet_dir,
        packet_file=packet_file,
        envelope=envelope,
        payload=payload,
        packet_artifact_id=packet_artifact_id,
        artifact_ids={str(key): str(value) for key, value in artifact_ids.items()},
        parent_artifact_ids=tuple(parent_ids),
        fixture_only=fixture_only,
        model_backed=model_backed,
        model_call_ids=model_call_ids,
        created_at=created_at,
    )


def _build_subject_manifest(
    *,
    run_id: str,
    packet_dir: Path,
    sources: list[SourcePacket],
    missing_expected: list[str],
    critical_missing: list[str],
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_packets": [_source_packet_summary(source) for source in sources],
        "source_packet_count": len(sources),
        "source_packet_kinds": sorted({source.packet_kind for source in sources}),
        "missing_source_packets": missing_expected,
        "missing_critical_source_kinds": critical_missing,
        "source_chain_complete": not critical_missing,
        "live_model_backed_evidence_exists": any(source.model_backed for source in sources),
        "source_fixture_only_exists": any(source.fixture_only for source in sources),
        "synthesis_finalization_eligible": False,
        "non_final": True,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "worker": "autonomous_evidence_synthesis_subject_manifest_v1_controller",
    }


def _build_repair_history(sources: list[SourcePacket]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for source in sources:
        if source.packet_kind == "autonomous_revision":
            rows.append(_revision_history_row(source))
        elif source.packet_kind == "executed_ablation":
            rows.append(_executed_ablation_history_row(source))
        elif source.packet_kind == "ablation_informed_revision":
            rows.append(_ablation_informed_history_row(source))
    rows.sort(key=lambda row: (str(row["created_at"]), str(row["packet_kind"]), str(row["packet_id"])))
    for index, row in enumerate(rows, start=1):
        row["event_index"] = index
    return {
        "repair_events": rows,
        "event_count": len(rows),
        "revision_event_count": sum(
            1
            for row in rows
            if row["packet_kind"] in {"autonomous_revision", "ablation_informed_revision"}
        ),
        "executed_ablation_event_count": sum(
            1 for row in rows if row["packet_kind"] == "executed_ablation"
        ),
        "worker": "repair_history_table_v1_controller",
    }


def _revision_history_row(source: SourcePacket) -> dict[str, object]:
    handle = _optional_payload(source.packet_dir, "causal_handle_selection.json")
    failure = _optional_payload(source.packet_dir, "selected_failure_diagnosis.json")
    revised = _optional_payload(source.packet_dir, "revised_candidate_text.json")
    gate_report = _as_dict(source.payload.get("gate_report"))
    selected_handle = _first_text(
        handle,
        (
            "selected_causal_handle",
            "targeted_causal_handle",
            "selected_handle",
            "selected_failure_type",
        ),
    ) or _first_text(failure, ("failure_type", "primary_failure_type", "selected_failure_type"))
    return _base_history_row(source) | {
        "source_packet": source.payload.get("source_packet_id"),
        "selected_handle": selected_handle or "opening_only_thesis_pressure_repair",
        "selected_base": "original_candidate",
        "proposed_patch_count": _len_payload_list(
            _optional_payload(source.packet_dir, "revision_patch_proposal.json"),
            "patches",
        ),
        "applied_patch_count": len(source.payload.get("source_patch_ids", [])),
        "causal_status": "weak_or_unproven_planned_revision",
        "repair_has_causal_support": False,
        "revert_performs_same_or_better": None,
        "strongest_rival_pressure_remains_blocking": bool(
            source.payload.get("strongest_rival_present")
        ),
        "candidate_artifact_id": source.artifact_ids.get("revised_candidate_text"),
        "candidate_id": revised.get("candidate_id"),
        "candidate_text_sha256": revised.get("text_sha256"),
        "candidate_word_count": _word_count(str(revised.get("text", ""))),
        "gate_passed": bool(gate_report.get("passed", False)),
        "gate_failed_gates": list(gate_report.get("failed_gates", [])),
        "classification": "weak",
    }


def _ablation_informed_history_row(source: SourcePacket) -> dict[str, object]:
    base = _optional_payload(source.packet_dir, "cycle2_base_candidate_selection.json")
    handle = _optional_payload(source.packet_dir, "selected_next_failure_or_handle.json")
    ledger = _optional_payload(source.packet_dir, "cycle2_applied_patch_ledger.json")
    revised = _optional_payload(source.packet_dir, "cycle2_revised_candidate_text.json")
    gate_report = _as_dict(source.payload.get("gate_report"))
    integrity = _as_dict(gate_report.get("integrity"))
    selected_handle = (
        source.payload.get("selected_next_handle")
        or handle.get("selected_next_handle")
        or _nested_text(handle, ("residual_blocker_pivot", "selected_residual_blocker"))
        or handle.get("prior_handle")
        or "record_law_proof_answer_compression"
    )
    selected_base = (
        source.payload.get("selected_base_choice")
        or base.get("selected_base_choice")
        or base.get("selected_base_candidate_id")
    )
    prior_handle_status = _nested_text(base, ("residual_blocker_pivot", "prior_handle_status"))
    if not prior_handle_status:
        prior_handle_status = _nested_text(handle, ("residual_blocker_pivot", "prior_handle_status"))
    return _base_history_row(source) | {
        "source_packet": source.payload.get("source_executed_ablation_packet_id")
        or source.payload.get("source_revision_packet_id"),
        "source_revision_packet_id": source.payload.get("source_revision_packet_id"),
        "selected_handle": selected_handle,
        "selected_base": selected_base,
        "proposed_patch_count": integrity.get("proposed_patch_count")
        if "proposed_patch_count" in integrity
        else _len_payload_list(
            _optional_payload(source.packet_dir, "cycle2_patch_proposal.json"),
            "patches",
        ),
        "applied_patch_count": integrity.get("applied_patch_count")
        if "applied_patch_count" in integrity
        else _len_payload_list(ledger, "applied_patches"),
        "causal_status": source.payload.get("previous_repair_causal_status"),
        "previous_repair_treated_as_proven": bool(
            source.payload.get("previous_repair_treated_as_proven", False)
        ),
        "repair_has_causal_support": None,
        "revert_performs_same_or_better": None,
        "record_compression_improves_discovery": None,
        "prior_handle": _nested_text(base, ("residual_blocker_pivot", "prior_handle"))
        or handle.get("prior_handle"),
        "prior_handle_status": prior_handle_status,
        "same_handle_reselected": _nested_bool(
            source.payload,
            ("residual_blocker_pivot", "same_handle_reselected"),
        ),
        "strongest_rival_pressure_remains_blocking": True,
        "candidate_artifact_id": source.artifact_ids.get("cycle2_revised_candidate_text"),
        "candidate_id": revised.get("candidate_id"),
        "candidate_text_sha256": revised.get("text_sha256"),
        "candidate_word_count": _word_count(str(revised.get("text", ""))),
        "dominant_variant_promoted_or_justified": _nested_bool(
            gate_report,
            ("ablation_evidence_dominance", "dominant_variant_promoted_or_justified"),
        ),
        "selected_base_dominated_by_available_variant": _nested_bool(
            gate_report,
            ("ablation_evidence_dominance", "selected_base_dominated_by_available_variant"),
        ),
        "gate_passed": bool(gate_report.get("passed", False)),
        "gate_failed_gates": list(gate_report.get("failed_gates", [])),
        "classification": _classify_revision_source(source.payload),
    }


def _executed_ablation_history_row(source: SourcePacket) -> dict[str, object]:
    causal = _optional_payload(source.packet_dir, "ablation_causal_effect_report.json")
    comparison = _optional_payload(source.packet_dir, "ablation_old_new_rival_comparison.json")
    gate_report = _as_dict(source.payload.get("gate_report"))
    causal_status = (
        source.payload.get("selected_repair_causal_status")
        or causal.get("selected_repair_causal_status")
    )
    return _base_history_row(source) | {
        "source_packet": source.payload.get("source_revision_packet_id"),
        "source_revision_packet_id": source.payload.get("source_revision_packet_id"),
        "source_revision_packet_kind": source.payload.get("source_revision_packet_kind"),
        "selected_handle": None,
        "selected_base": None,
        "proposed_patch_count": None,
        "applied_patch_count": None,
        "causal_status": causal_status,
        "selected_repair_appears_causal": causal.get("selected_repair_appears_causal"),
        "repair_has_causal_support": comparison.get("repair_has_causal_support"),
        "revert_performs_same_or_better": comparison.get("revert_performs_same_or_better"),
        "record_compression_improves_discovery": comparison.get(
            "record_compression_improves_discovery"
        ),
        "reduced_overexplanation": causal.get("reduced_overexplanation"),
        "damaged_local_embodiment": causal.get("damaged_local_embodiment"),
        "recommended_next_action": causal.get("recommended_next_action"),
        "strongest_rival_pressure_remains_blocking": bool(
            causal.get("strongest_rival_pressure_remains_blocking")
            or comparison.get("strongest_rival_still_beats_candidate")
            or _nested_bool(gate_report, ("rival_remains_blocking",))
        ),
        "gate_passed": bool(gate_report.get("passed", False)),
        "gate_failed_gates": list(gate_report.get("failed_gates", [])),
        "classification": _classify_causal_status(causal_status, comparison),
    }


def _base_history_row(source: SourcePacket) -> dict[str, object]:
    return {
        "packet_dir": str(source.packet_dir),
        "packet_kind": source.packet_kind,
        "packet_id": source.packet_id,
        "packet_artifact_id": source.packet_artifact_id,
        "created_at": source.created_at,
        "finalization_eligible": bool(source.payload.get("finalization_eligible", False)),
        "non_final": bool(source.payload.get("non_final", True)),
        "model_backed": source.model_backed,
        "model_call_ids": list(source.model_call_ids),
        "fixture_only": source.fixture_only,
    }


def _build_causal_status_summary(history: dict[str, object]) -> dict[str, object]:
    rows = _rows(history)
    classifications = sorted({str(row["classification"]) for row in rows})
    useful_rows = [row for row in rows if row.get("causal_status") == "useful_but_insufficient"]
    failed_rows = [
        row
        for row in rows
        if row.get("classification") in {"failed", "weak"}
        or row.get("causal_status") == "noncausal_or_cosmetic"
    ]
    exhausted_rows = [
        row
        for row in rows
        if row.get("prior_handle_status") == "exhausted_for_now"
        or row.get("record_compression_improves_discovery") is False
    ]
    findings: list[dict[str, object]] = [
        {
            "finding_id": "opening_repair_weak_or_unproven",
            "status": "weak",
            "evidence_packet_ids": [
                str(row["packet_id"])
                for row in rows
                if row["packet_kind"] == "autonomous_revision"
            ],
            "summary": "The first autonomous revision is treated as weak/unproven until executed ablation supplies causal support.",
        },
        {
            "finding_id": "record_law_proof_answer_compression_useful",
            "status": "useful_but_insufficient" if useful_rows else "not_observed",
            "evidence_packet_ids": [str(row["packet_id"]) for row in useful_rows],
            "summary": "Record/law/proof/answer compression is preserved where executed ablation reports useful-but-insufficient support.",
        },
        {
            "finding_id": "same_handle_plateau_or_exhaustion",
            "status": "exhausted_for_now" if exhausted_rows else "not_observed",
            "evidence_packet_ids": [str(row["packet_id"]) for row in exhausted_rows],
            "summary": "Repeated local compression should pause when discovery no longer improves or the prior handle is marked exhausted.",
        },
        {
            "finding_id": "rival_informed_pressure_pivot",
            "status": "failed" if failed_rows else "not_observed",
            "evidence_packet_ids": [
                str(row["packet_id"])
                for row in failed_rows
                if row.get("causal_status") == "noncausal_or_cosmetic"
            ],
            "summary": "A rival-pressure pivot is rejected when executed ablation marks it noncausal/cosmetic or revert performs as well or better.",
        },
        {
            "finding_id": "strongest_rival_pressure",
            "status": "blocking"
            if any(row.get("strongest_rival_pressure_remains_blocking") for row in rows)
            else "not_detected",
            "evidence_packet_ids": [
                str(row["packet_id"])
                for row in rows
                if row.get("strongest_rival_pressure_remains_blocking")
            ],
            "summary": "Strongest-rival pressure remains a blocking internal comparison pressure, not a passed gate.",
        },
    ]
    return {
        "trajectory": rows,
        "classifications_present": classifications,
        "finding_count": len(findings),
        "findings": findings,
        "weak_repairs_detected": any(row.get("classification") == "weak" for row in rows),
        "useful_repairs_detected": bool(useful_rows),
        "exhausted_handles_detected": bool(exhausted_rows),
        "failed_repairs_detected": bool(failed_rows),
        "strongest_rival_pressure_remains_blocking": any(
            row.get("strongest_rival_pressure_remains_blocking") for row in rows
        ),
        "no_phase_shift_claim": True,
        "not_human_data": True,
        "worker": "causal_status_summary_v1_controller",
    }


def _build_best_candidate_selection(
    sources: list[SourcePacket],
    history: dict[str, object],
) -> dict[str, object]:
    rows = _rows(history)
    executed_by_source = {
        str(row["source_revision_packet_id"]): row
        for row in rows
        if row["packet_kind"] == "executed_ablation" and row.get("source_revision_packet_id")
    }
    candidates: list[dict[str, object]] = []
    for row in rows:
        if row["packet_kind"] not in {"autonomous_revision", "ablation_informed_revision"}:
            continue
        candidate = {
            "packet_id": row["packet_id"],
            "packet_kind": row["packet_kind"],
            "packet_dir": row["packet_dir"],
            "candidate_artifact_id": row.get("candidate_artifact_id"),
            "candidate_id": row.get("candidate_id"),
            "text_sha256": row.get("candidate_text_sha256"),
            "word_count": row.get("candidate_word_count"),
            "selected_handle": row.get("selected_handle"),
            "selected_base": row.get("selected_base"),
        }
        score, reasons = _candidate_score(row, executed_by_source.get(str(row["packet_id"])))
        candidate["evidence_score"] = score
        candidate["selection_reasons"] = reasons
        candidates.append(candidate)

    candidates.sort(key=lambda candidate: (int(candidate["evidence_score"]), str(candidate["packet_id"])))
    selected = candidates[-1] if candidates else None
    rejected_latest = None
    if candidates:
        latest = sorted(candidates, key=lambda candidate: str(candidate["packet_id"]))[-1]
        if selected is not None and latest["packet_id"] != selected["packet_id"]:
            rejected_latest = {
                "packet_id": latest["packet_id"],
                "why_not_selected": latest["selection_reasons"],
            }
    selected_payload = dict(selected) if selected is not None else None
    if selected_payload is not None:
        selected_payload.update(
            {
                "selected_best_candidate_packet_id": selected_payload["packet_id"],
                "selected_best_candidate_text_sha256": selected_payload["text_sha256"],
                "selected_candidate_is_final": False,
                "selected_candidate_requires_further_testing": True,
                "strongest_rival_still_blocks": any(
                    row.get("strongest_rival_pressure_remains_blocking") for row in rows
                ),
            }
        )
    return {
        "candidate_options": candidates,
        "selected_best_candidate": selected_payload,
        "why_latest_candidate_may_not_be_selected": rejected_latest,
        "selection_basis": "controller-derived from executed ablation and ablation-informed evidence; not human validation",
        "candidate_is_final": False,
        "requires_further_testing": True,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "best_current_candidate_selection_v1_controller",
    }


def _candidate_score(
    revision_row: dict[str, object],
    executed_row: dict[str, object] | None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if revision_row.get("dominant_variant_promoted_or_justified"):
        score += 2
        reasons.append("dominant countable ablation evidence was promoted or justified")
    if revision_row.get("prior_handle_status") == "exhausted_for_now":
        score += 1
        reasons.append("prior useful handle was preserved while marked exhausted for now")
    if executed_row is None:
        score -= 1
        reasons.append("candidate still requires executed ablation evidence")
        return score, reasons

    status = executed_row.get("causal_status")
    if status == "useful_but_insufficient":
        score += 5
        reasons.append("executed ablation reports useful-but-insufficient causal support")
    if status == "noncausal_or_cosmetic":
        score -= 6
        reasons.append("executed ablation reports noncausal/cosmetic repair")
    if executed_row.get("repair_has_causal_support") is True:
        score += 2
        reasons.append("old/new/rival comparison reports causal support")
    if executed_row.get("repair_has_causal_support") is False:
        score -= 2
        reasons.append("old/new/rival comparison does not support repair causality")
    if executed_row.get("revert_performs_same_or_better") is True:
        score -= 4
        reasons.append("revert performs the same or better")
    if executed_row.get("record_compression_improves_discovery") is False:
        reasons.append("same-handle record compression no longer improves discovery")
    if executed_row.get("damaged_local_embodiment") is True:
        score -= 3
        reasons.append("repair damages local embodiment")
    if executed_row.get("strongest_rival_pressure_remains_blocking"):
        score -= 1
        reasons.append("strongest-rival pressure remains blocking")
    return score, reasons


def _build_failed_or_rejected_repairs(history: dict[str, object]) -> dict[str, object]:
    repairs: list[dict[str, object]] = []
    for row in _rows(history):
        classification = str(row.get("classification"))
        if classification not in {"failed", "weak", "rejected"}:
            continue
        repairs.append(
            {
                "packet_id": row["packet_id"],
                "packet_kind": row["packet_kind"],
                "packet_dir": row["packet_dir"],
                "selected_handle": row.get("selected_handle"),
                "causal_status": row.get("causal_status"),
                "classification": classification,
                "rejection_reason": _repair_rejection_reason(row),
                "source_evidence": [
                    str(row.get("packet_id")),
                    str(row.get("source_revision_packet_id") or row.get("source_packet") or ""),
                ],
            }
        )
    return {
        "failed_or_rejected_repairs": repairs,
        "failed_or_rejected_count": len(repairs),
        "mechanically_invalid_prior_packets": [],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "failed_or_rejected_repairs_v1_controller",
    }


def _build_exhausted_handle_report(history: dict[str, object]) -> dict[str, object]:
    rows = _rows(history)
    record_rows = [
        row
        for row in rows
        if row.get("selected_handle") == "record_law_proof_answer_compression"
        or row.get("prior_handle") == "record_law_proof_answer_compression"
        or row.get("causal_status") == "useful_but_insufficient"
    ]
    pivot_failed = any(
        row.get("causal_status") == "noncausal_or_cosmetic"
        or row.get("selected_handle") == "rival_informed_object_event_pressure"
        and row.get("classification") == "failed"
        for row in rows
    )
    handles = [
        {
            "handle": "opening_only_thesis_pressure_repair",
            "status": "weak_noncausal_or_unproven",
            "evidence_packet_ids": [
                str(row["packet_id"])
                for row in rows
                if row["packet_kind"] == "autonomous_revision"
            ],
            "reason": "Opening-only thesis pressure was not enough to become causal proof.",
            "allowed_to_revisit_only_if": "new executed evidence identifies a narrow opening-local target",
        },
        {
            "handle": "record_law_proof_answer_compression",
            "status": "exhausted_for_now"
            if any(row.get("record_compression_improves_discovery") is False for row in rows)
            or any(row.get("prior_handle_status") == "exhausted_for_now" for row in rows)
            else "useful_but_insufficient",
            "evidence_packet_ids": [str(row["packet_id"]) for row in record_rows],
            "reason": "Compression became useful but does not justify repeating the same local handle without new evidence.",
            "allowed_to_revisit_only_if": "a later ablation shows compression newly improves discovery without embodiment loss",
        },
        {
            "handle": "rival_informed_object_event_pressure",
            "status": "failed" if pivot_failed else "active_unresolved",
            "evidence_packet_ids": [
                str(row["packet_id"])
                for row in rows
                if row.get("selected_handle") == "rival_informed_object_event_pressure"
                or row.get("causal_status") == "noncausal_or_cosmetic"
            ],
            "reason": "The rival pressure cannot be repaired by naming pressure more explicitly.",
            "allowed_to_revisit_only_if": "macro recomposition embodies pressure through object/event sequence rather than labels",
        },
    ]
    return {
        "handles": handles,
        "exhausted_or_failed_count": sum(
            1
            for handle in handles
            if handle["status"] in {"exhausted_for_now", "failed", "weak_noncausal_or_unproven"}
        ),
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "exhausted_handle_report_v1_controller",
    }


def _build_rival_pressure_summary(
    sources: list[SourcePacket],
    history: dict[str, object],
) -> dict[str, object]:
    rows = _rows(history)
    strongest_rival_present = any(
        source.payload.get("strongest_rival_present")
        or source.payload.get("strongest_rival_gate_satisfied") is not None
        for source in sources
    )
    still_blocks = any(row.get("strongest_rival_pressure_remains_blocking") for row in rows)
    return {
        "strongest_rival_present": strongest_rival_present,
        "strongest_rival_still_blocks": still_blocks,
        "current_candidate_closes_gap": False,
        "what_rival_still_does_better": [
            "object-event pressure remains more immediate",
            "first-read vividness has less explanatory drag",
            "lived causal sequence is less dependent on labels",
        ],
        "current_candidate_strength": [
            "more architectonic",
            "more explicit about proof and return logic",
            "better aligned to Abi's symbolic architecture",
        ],
        "future_recomposition_must_preserve_rival_pressure": True,
        "strongest_rival_comparison_passed": False,
        "not_human_data": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "rival_pressure_summary_v1_controller",
    }


def _build_residual_blocker_map(
    exhausted_handle_report: dict[str, object],
    rival_pressure_summary: dict[str, object],
) -> dict[str, object]:
    handles = {
        str(handle["handle"]): handle for handle in exhausted_handle_report["handles"]
    }
    rival_failed = handles["rival_informed_object_event_pressure"]["status"] == "failed"
    blockers = [
        _blocker(
            "proof_line_redundancy_cleanup",
            "medium",
            "record/law/proof/answer compression was useful but is now exhausted for direct repetition",
            False,
        ),
        _blocker(
            "no_outside_answer_pressure_preservation",
            "high",
            "cosmic silence must remain the isolation condition of proof, not a mere no-rescue slogan",
            False,
        ),
        _blocker(
            "final_return_closure_embodiment",
            "high",
            "return requires embodied ending rather than explanatory closure",
            False,
        ),
        _blocker(
            "separation_pressure_overnaming",
            "high" if rival_failed else "medium",
            "rival-informed pressure cannot be fixed by saying pressure more often",
            False,
        ),
        _blocker(
            "middle_abstraction_ladder_compression",
            "medium",
            "middle movement still risks abstraction laddering",
            False,
        ),
        _blocker(
            "rival_informed_object_event_pressure",
            "high",
            "strongest rival still blocks in object-event pressure",
            False,
            status="failed_as_local_patch" if rival_failed else "active",
        ),
    ]
    return {
        "residual_blockers": blockers,
        "blocker_count": len(blockers),
        "macro_recomposition_recommended": True,
        "strongest_rival_still_blocks": rival_pressure_summary["strongest_rival_still_blocks"],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "residual_blocker_map_v1_controller",
    }


def _build_local_law_case_notes(history: dict[str, object]) -> dict[str, object]:
    packet_ids = [str(row["packet_id"]) for row in _rows(history)]
    notes = [
        {
            "law_id": "do_not_thin_scene_to_reduce_overexplanation",
            "case_note": "Do not reduce overexplanation by weakening concrete domestic embodiment.",
            "source_evidence_packet_ids": packet_ids,
        },
        {
            "law_id": "preserve_pressure_bearing_details",
            "case_note": "Preserve steady, on-its-side, ring, dust, spoon, and saucer details where they carry pressure.",
            "source_evidence_packet_ids": packet_ids,
        },
        {
            "law_id": "compress_labels_only_when_scene_carries_function",
            "case_note": "Labels may be compressed only when the scene carries the same causal function.",
            "source_evidence_packet_ids": packet_ids,
        },
        {
            "law_id": "do_not_name_pressure_as_pressure",
            "case_note": "Do not repair object/event pressure by adding more explicit pressure language.",
            "source_evidence_packet_ids": packet_ids,
        },
        {
            "law_id": "cosmic_silence_is_formal_condition",
            "case_note": "Cosmic silence is the isolation condition of proof, not merely a lack of rescue.",
            "source_evidence_packet_ids": packet_ids,
        },
        {
            "law_id": "rival_pressure_remains_active",
            "case_note": "Strongest-rival pressure remains active until a later comparison actually closes it.",
            "source_evidence_packet_ids": packet_ids,
        },
    ]
    return {
        "case_notes": notes,
        "case_note_count": len(notes),
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "worker": "local_law_case_notes_v1_controller",
    }


def _build_strategic_decision_report(
    causal_status_summary: dict[str, object],
    best_candidate: dict[str, object],
    exhausted_handle_report: dict[str, object],
    rival_pressure_summary: dict[str, object],
) -> dict[str, object]:
    plateau_detected = bool(causal_status_summary["exhausted_handles_detected"])
    failed_detected = bool(causal_status_summary["failed_repairs_detected"])
    recommendation = (
        "stop_local_patching_and_synthesize_macro_recomposition_brief"
        if plateau_detected or failed_detected
        else "continue_local_patching_only_after_new_evidence"
    )
    return {
        "recommendation": recommendation,
        "next_recommended_action": "inspect_macro_recomposition_brief_before_any_new_candidate",
        "do_not_continue_local_patching_immediately": recommendation.startswith("stop_"),
        "do_not_build_loop_controller_yet": True,
        "do_not_add_taste_memory_yet": True,
        "decision_basis": [
            "local patching has plateaued or failed on residual rival pressure",
            "best candidate remains non-final and requires further testing",
            "strongest-rival pressure remains blocking",
        ],
        "best_candidate_reference": best_candidate["selected_best_candidate"],
        "exhausted_handles": exhausted_handle_report["handles"],
        "strongest_rival_still_blocks": rival_pressure_summary[
            "strongest_rival_still_blocks"
        ],
        "no_finalization": True,
        "no_phase_shift_claim": True,
        "no_operator_approval": True,
        "not_candidate_artifact": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "worker": "strategic_decision_report_v1_controller",
    }


def _build_macro_recomposition_brief(
    best_candidate: dict[str, object],
    failed_repairs: dict[str, object],
    exhausted_handles: dict[str, object],
    rival_pressure: dict[str, object],
    local_law_notes: dict[str, object],
) -> dict[str, object]:
    return {
        "brief_type": "future_creative_instruction_not_artifact",
        "best_current_base_candidate": best_candidate["selected_best_candidate"],
        "protected_effects_to_preserve": [
            "domestic table/dust/spoon/saucer object field",
            "proof arising from inside the line it integrates",
            "cosmic silence as isolation condition of proof",
            "return with record intact rather than regression",
            "local concrete pressure before explanatory labels",
            "active strongest-rival pressure",
        ],
        "failed_repairs_to_avoid": failed_repairs["failed_or_rejected_repairs"],
        "exhausted_handles_not_to_repeat": exhausted_handles["handles"],
        "target_region_or_movement": "middle_and_return_movement",
        "allowed_scale": "bounded_macro_recomposition_not_full_rewrite",
        "source_constraints": [
            "world/proof must carry contradiction internally",
            "table/dust/spoon/saucer remain the local field",
            "return is not regression",
            "no outside answer can rescue the proof",
        ],
        "rival_pressure_constraints": rival_pressure["what_rival_still_does_better"],
        "local_laws": local_law_notes["case_notes"],
        "forbidden_changes": [
            "do not write a new artifact inside this packet",
            "do not repeat exhausted same-handle compression without new evidence",
            "do not name pressure in place of embodying it",
            "do not mark final gates passed",
            "do not make a phase-shift claim",
        ],
        "success_criteria": [
            "middle abstraction compresses without thinning scene",
            "record/law/proof/answer terms are carried by events and objects",
            "rival pressure becomes embodied rather than announced",
            "return preserves record and change together",
            "a later executed ablation can test the recomposed passage",
        ],
        "ablation_plan_after_recomposition": [
            "execute ablation against the recomposed middle/return movement",
            "include revert, no-op, embodiment-preserving, and rival-pressure variants",
            "compare against strongest rival without treating internal evidence as human validation",
        ],
        "not_finalization_eligible": True,
        "not_candidate_artifact": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_brief_v1_controller",
    }


def _build_gate_report(
    *,
    subject_manifest: dict[str, object],
    best_candidate: dict[str, object],
    failed_repairs: dict[str, object],
    exhausted_handles: dict[str, object],
    rival_pressure: dict[str, object],
    macro_brief: dict[str, object],
) -> dict[str, object]:
    gate_results = [
        _gate_result("synthesis_packet_exists", True),
        _gate_result("source_chain_complete", bool(subject_manifest["source_chain_complete"])),
        _gate_result(
            "live_evidence_present",
            bool(subject_manifest["live_model_backed_evidence_exists"]),
            [] if subject_manifest["live_model_backed_evidence_exists"] else ["no live/model-backed evidence in this source chain"],
        ),
        _gate_result(
            "best_candidate_selected",
            best_candidate["selected_best_candidate"] is not None,
        ),
        _gate_result(
            "failed_repairs_classified",
            int(failed_repairs["failed_or_rejected_count"]) > 0,
        ),
        _gate_result(
            "exhausted_handles_classified",
            int(exhausted_handles["exhausted_or_failed_count"]) > 0,
        ),
        _gate_result(
            "rival_pressure_preserved",
            bool(rival_pressure["future_recomposition_must_preserve_rival_pressure"]),
        ),
        _gate_result("macro_recomposition_brief_exists", bool(macro_brief)),
        _gate_result("no_final_claim", True),
        _gate_result("no_phase_shift_claim", True),
        _gate_result(
            "internal_operator_approval",
            False,
            ["operator approval is intentionally absent"],
            record=False,
        ),
    ]
    failed_gates = [
        str(gate["gate_name"]) for gate in gate_results if not bool(gate["passed"])
    ]
    blockers = [
        "synthesis is a controller decision packet, not finalization evidence",
        "strongest-rival pressure remains blocking",
        "internal operator approval is absent",
        "no human validation is present",
    ]
    return {
        "passed": False,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "non_final": True,
        "not_human_validated": True,
        "not_human_data": True,
        "human_validation_required": False,
        "paper_validation_required": False,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "operator_approval_absent": True,
        "profile": "autonomous_creative_candidate",
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "unresolved_blockers": blockers,
        "summary_verdict": (
            "Evidence synthesis selected a provisional best candidate and a macro "
            "recomposition brief, but finalization remains fail-closed."
        ),
        "worker": "synthesis_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    run_id: str,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    sources: list[SourcePacket],
) -> dict[str, object]:
    decision = payloads["strategic_decision_report"]
    return {
        "run_id": run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": list(artifacts),
        "counts": {
            "source_packets": len(sources),
            "synthesis_artifacts": len(artifacts),
            "required_synthesis_artifacts": len(AUTONOMOUS_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES),
            "model_calls": 0,
        },
        "source_chain": [_source_packet_summary(source) for source in sources],
        "best_current_candidate": payloads["best_current_candidate_selection"][
            "selected_best_candidate"
        ],
        "failed_repairs_identified": payloads["failed_or_rejected_repairs"][
            "failed_or_rejected_repairs"
        ],
        "exhausted_handles_identified": payloads["exhausted_handle_report"]["handles"],
        "strategic_decision": decision["recommendation"],
        "next_recommended_action": decision["next_recommended_action"],
        "macro_recomposition_brief_artifact_id": artifacts["macro_recomposition_brief"].id,
        "synthesis_gate_report_artifact_id": artifacts["synthesis_gate_report"].id,
        "gate_report": payloads["synthesis_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "autonomous_evidence_synthesis_packet_v1_controller",
    }


def _source_packet_summary(source: SourcePacket) -> dict[str, object]:
    return {
        "packet_kind": source.packet_kind,
        "packet_id": source.packet_id,
        "packet_dir": str(source.packet_dir),
        "packet_artifact_id": source.packet_artifact_id,
        "artifact_ids": source.artifact_ids,
        "model_backed": source.model_backed,
        "model_call_ids": list(source.model_call_ids),
        "fixture_only": source.fixture_only,
        "finalization_eligible": bool(source.payload.get("finalization_eligible", False)),
        "no_phase_shift_claim": bool(source.payload.get("no_phase_shift_claim", True)),
    }


def _critical_missing(sources: list[SourcePacket]) -> list[str]:
    loaded = {source.packet_kind for source in sources}
    return [packet_kind for packet_kind in CRITICAL_SOURCE_KINDS if packet_kind not in loaded]


def _artifact_for_path(connection: sqlite3.Connection, path: Path) -> ArtifactRecord | None:
    values = [str(path), str(path.resolve())]
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path IN (?, ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        values,
    ).fetchone()
    if row is None:
        return None
    from abi.artifacts import row_to_artifact

    return row_to_artifact(row)


def _optional_payload(packet_dir: Path, file_name: str) -> dict[str, Any]:
    path = packet_dir / file_name
    if not path.exists():
        return {}
    envelope = read_json_file(path)
    payload = envelope.get("payload")
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(history: dict[str, object]) -> list[dict[str, object]]:
    rows = history.get("repair_events", [])
    return list(rows) if isinstance(rows, list) else []


def _classify_revision_source(payload: dict[str, Any]) -> str:
    if payload.get("previous_repair_causal_status") == "useful_but_insufficient":
        return "useful"
    if payload.get("previous_repair_treated_as_proven") is False:
        return "weak"
    return "unproven"


def _classify_causal_status(status: object, comparison: dict[str, Any]) -> str:
    if status == "useful_but_insufficient":
        if comparison.get("record_compression_improves_discovery") is False:
            return "exhausted"
        return "useful"
    if status == "noncausal_or_cosmetic":
        return "failed"
    if status is None:
        return "unproven"
    status_text = str(status).lower()
    if "weak" in status_text:
        return "weak"
    if "cosmetic" in status_text or "noncausal" in status_text or "revert" in status_text:
        return "failed"
    return "unproven"


def _repair_rejection_reason(row: dict[str, object]) -> str:
    if row.get("causal_status") == "noncausal_or_cosmetic":
        return "executed ablation reports the repair as noncausal/cosmetic"
    if row.get("revert_performs_same_or_better") is True:
        return "revert performs the same or better"
    if row.get("classification") == "weak":
        return "repair remains weak or unproven"
    return "repair is rejected by controller-owned evidence synthesis"


def _blocker(
    blocker_id: str,
    severity: str,
    source_evidence: str,
    local_patching_sufficient: bool,
    *,
    status: str = "active",
) -> dict[str, object]:
    return {
        "blocker_id": blocker_id,
        "status": status,
        "source_evidence": source_evidence,
        "severity": severity,
        "local_patching_sufficient": local_patching_sufficient,
        "macro_recomposition_recommended": not local_patching_sufficient,
    }


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


def _first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _nested_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, str) and value else None


def _nested_bool(payload: dict[str, Any], keys: tuple[str, ...]) -> bool | None:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, bool) else None


def _len_payload_list(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key, [])
    return len(value) if isinstance(value, list) else 0


def _word_count(text: str) -> int:
    return len([part for part in text.split() if part])


def _unique(values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        if not value:
            continue
        value_text = str(value)
        if value_text not in result:
            result.append(value_text)
    return result


def _packet_sort_key(path: Path) -> tuple[int, str]:
    suffix = path.name.removeprefix("packet_")
    return (int(suffix) if suffix.isdecimal() else 0, path.name)


def _refusal(run_id: str, message: str, **extra: object) -> EvidenceSynthesisResult:
    payload = {
        "accepted": False,
        "run_id": run_id,
        "message": message,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        **extra,
    }
    return EvidenceSynthesisResult(exit_code=1, payload=payload)
