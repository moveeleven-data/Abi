"""Bounded macro recomposition from autonomous evidence synthesis."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, row_to_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.state import (
    AUTONOMOUS_BOUNDED_MACRO_RECOMPOSITION_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.packets import PacketWriter, create_packet_dir, read_json_file


BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID = "bounded_macro_recomposition_v1"
BOUNDED_MACRO_RECOMPOSITION_CREATED_BY = "bounded_macro_recomposition_v1_controller"
BOUNDED_MACRO_RECOMPOSITION_CLIENTS = ("fake", "openai")
BOUNDED_MACRO_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT = 8

BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES = (
    "macro_recomposition_subject_manifest",
    "macro_recomposition_brief_ref",
    "macro_recomposition_work_order",
    "protected_effects_and_forbidden_changes",
    "macro_recomposition_plan",
    "macro_patch_or_section_plan",
    "macro_recomposed_candidate_text",
    "macro_recomposition_diff_report",
    "macro_rival_pressure_check",
    "macro_recomposition_gate_report",
    "macro_recomposition_packet",
)

REQUIRED_SYNTHESIS_ARTIFACT_FILES = (
    "autonomous_evidence_synthesis_packet.json",
    "best_current_candidate_selection.json",
    "macro_recomposition_brief.json",
    "local_law_case_notes.json",
    "residual_blocker_map.json",
    "rival_pressure_summary.json",
    "exhausted_handle_report.json",
    "failed_or_rejected_repairs.json",
    "strategic_decision_report.json",
)

TARGET_MOVEMENT = "middle_and_return_movement"


@dataclass(frozen=True)
class BoundedMacroRecompositionResult:
    exit_code: int
    payload: dict[str, object]
    artifacts: tuple[ArtifactRecord, ...] = ()
    gate_record: GateRecord | None = None


@dataclass(frozen=True)
class MacroSubject:
    run_id: str
    synthesis_packet_dir: Path
    synthesis_packet_id: str
    synthesis_artifact_ids: dict[str, str]
    synthesis_payloads: dict[str, dict[str, Any]]
    selected_best_candidate: dict[str, Any]
    base_packet_dir: Path
    base_packet_id: str
    base_packet_kind: str
    base_candidate_artifact_id: str | None
    base_text: str
    base_text_sha256: str
    base_word_count: int
    source_parent_ids: tuple[str, ...]
    fixture_only: bool


@dataclass(frozen=True)
class RecomposedText:
    text: str
    target_start_index: int
    target_end_index: int
    unchanged_prefix: list[str]
    original_target: list[str]
    replacement: list[str]


def run_bounded_macro_recomposition(
    config: AbiConfig,
    *,
    client_name: str,
    synthesis_packet: Path,
    allow_live_model: bool = False,
    max_model_calls: int = BOUNDED_MACRO_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
) -> BoundedMacroRecompositionResult:
    if client_name not in BOUNDED_MACRO_RECOMPOSITION_CLIENTS:
        return _refusal(
            message=f"Unsupported bounded macro recomposition client: {client_name}",
            synthesis_packet=synthesis_packet,
        )
    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if client_name == "openai":
        if not allow_live_model:
            return _refusal(
                message=(
                    "Bounded macro recomposition OpenAI path refused; pass "
                    "--allow-live-model to opt in explicitly."
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
                model=configured_model,
            )
        resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        if not resolved_api_key:
            return _refusal(
                message=(
                    f"Bounded macro recomposition OpenAI path refused; "
                    f"{OPENAI_API_KEY_ENV} is not set."
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
                model=configured_model,
            )
        return _refusal(
            message=(
                "Bounded macro recomposition OpenAI worker is not implemented in "
                "this deterministic task; use --client fake."
            ),
            synthesis_packet=synthesis_packet,
            client_name=client_name,
            model=configured_model,
        )

    initialize_database(config)
    with connect(config.db_path) as connection:
        try:
            subject = _load_macro_subject(connection, config, synthesis_packet)
        except ValueError as error:
            return _refusal(
                message=f"Bounded macro recomposition refused; {error}",
                synthesis_packet=synthesis_packet,
                client_name=client_name,
            )
        if get_run(connection, subject.run_id) is None:
            return _refusal(
                message=(
                    "Bounded macro recomposition refused; synthesis run is not "
                    f"registered: {subject.run_id}"
                ),
                synthesis_packet=synthesis_packet,
                client_name=client_name,
            )

        set_active_phase(
            connection,
            subject.run_id,
            AUTONOMOUS_BOUNDED_MACRO_RECOMPOSITION_ACTIVE_PHASE,
        )
        packet_dir = create_packet_dir(config.run_dir(subject.run_id) / "bounded_macro_recomposition")
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
            created_by=BOUNDED_MACRO_RECOMPOSITION_CREATED_BY,
            fixture_only=subject.fixture_only,
        )

        payloads: dict[str, dict[str, object]] = {}
        artifacts: dict[str, ArtifactRecord] = {}

        payloads["macro_recomposition_subject_manifest"] = _build_subject_manifest(
            subject,
            packet_dir,
            client_name=client_name,
            max_model_calls=max_model_calls,
        )
        artifacts["macro_recomposition_subject_manifest"] = writer.write_artifact(
            "macro_recomposition_subject_manifest",
            payloads["macro_recomposition_subject_manifest"],
            parent_ids=list(subject.source_parent_ids),
        )

        payloads["macro_recomposition_brief_ref"] = _build_brief_ref(subject)
        artifacts["macro_recomposition_brief_ref"] = writer.write_artifact(
            "macro_recomposition_brief_ref",
            payloads["macro_recomposition_brief_ref"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                *list(subject.source_parent_ids),
            ],
        )

        payloads["macro_recomposition_work_order"] = _build_work_order(subject)
        artifacts["macro_recomposition_work_order"] = writer.write_artifact(
            "macro_recomposition_work_order",
            payloads["macro_recomposition_work_order"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                artifacts["macro_recomposition_brief_ref"].id,
            ],
        )

        payloads["protected_effects_and_forbidden_changes"] = _build_protected_effects(
            subject
        )
        artifacts["protected_effects_and_forbidden_changes"] = writer.write_artifact(
            "protected_effects_and_forbidden_changes",
            payloads["protected_effects_and_forbidden_changes"],
            parent_ids=[
                artifacts["macro_recomposition_brief_ref"].id,
                artifacts["macro_recomposition_work_order"].id,
            ],
        )

        payloads["macro_recomposition_plan"] = _build_recomposition_plan(subject)
        artifacts["macro_recomposition_plan"] = writer.write_artifact(
            "macro_recomposition_plan",
            payloads["macro_recomposition_plan"],
            parent_ids=[
                artifacts["macro_recomposition_work_order"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        recomposed = _fake_recompose_text(subject.base_text)
        payloads["macro_patch_or_section_plan"] = _build_patch_or_section_plan(
            subject,
            recomposed,
        )
        artifacts["macro_patch_or_section_plan"] = writer.write_artifact(
            "macro_patch_or_section_plan",
            payloads["macro_patch_or_section_plan"],
            parent_ids=[
                artifacts["macro_recomposition_plan"].id,
                artifacts["protected_effects_and_forbidden_changes"].id,
            ],
        )

        payloads["macro_recomposed_candidate_text"] = _build_recomposed_candidate(
            subject,
            recomposed,
        )
        artifacts["macro_recomposed_candidate_text"] = writer.write_artifact(
            "macro_recomposed_candidate_text",
            payloads["macro_recomposed_candidate_text"],
            parent_ids=[
                artifacts["macro_patch_or_section_plan"].id,
                subject.base_candidate_artifact_id or artifacts["macro_recomposition_subject_manifest"].id,
            ],
        )

        payloads["macro_recomposition_diff_report"] = _build_diff_report(
            subject,
            recomposed,
            payloads["macro_recomposed_candidate_text"],
        )
        artifacts["macro_recomposition_diff_report"] = writer.write_artifact(
            "macro_recomposition_diff_report",
            payloads["macro_recomposition_diff_report"],
            parent_ids=[
                artifacts["macro_patch_or_section_plan"].id,
                artifacts["macro_recomposed_candidate_text"].id,
            ],
        )

        payloads["macro_rival_pressure_check"] = _build_rival_pressure_check(
            subject,
            payloads["macro_recomposed_candidate_text"],
        )
        artifacts["macro_rival_pressure_check"] = writer.write_artifact(
            "macro_rival_pressure_check",
            payloads["macro_rival_pressure_check"],
            parent_ids=[
                artifacts["macro_recomposed_candidate_text"].id,
                artifacts["macro_recomposition_diff_report"].id,
            ],
        )

        payloads["macro_recomposition_gate_report"] = _build_gate_report(
            subject=subject,
            subject_manifest=payloads["macro_recomposition_subject_manifest"],
            protected_effects=payloads["protected_effects_and_forbidden_changes"],
            diff_report=payloads["macro_recomposition_diff_report"],
            rival_check=payloads["macro_rival_pressure_check"],
        )
        artifacts["macro_recomposition_gate_report"] = writer.write_artifact(
            "macro_recomposition_gate_report",
            payloads["macro_recomposition_gate_report"],
            parent_ids=[
                artifacts["macro_recomposition_subject_manifest"].id,
                artifacts["macro_recomposed_candidate_text"].id,
                artifacts["macro_recomposition_diff_report"].id,
                artifacts["macro_rival_pressure_check"].id,
            ],
        )

        payloads["macro_recomposition_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=packet_dir,
            payloads=payloads,
            artifacts=artifacts,
            client_name=client_name,
        )
        artifacts["macro_recomposition_packet"] = writer.write_artifact(
            "macro_recomposition_packet",
            payloads["macro_recomposition_packet"],
            parent_ids=[
                artifact.id
                for artifact_type, artifact in artifacts.items()
                if artifact_type != "macro_recomposition_packet"
            ],
        )

        gate_report = payloads["macro_recomposition_gate_report"]
        gate_record = record_gate(
            connection,
            run_id=subject.run_id,
            gate_name="bounded_macro_recomposition_gate_report",
            passed=False,
            blocking_defects=list(gate_report["unresolved_blockers"]),
            lineage_id=BOUNDED_MACRO_RECOMPOSITION_LINEAGE_ID,
        )

    payload = {
        "accepted": True,
        "run_id": subject.run_id,
        "packet_dir": str(packet_dir),
        "packet_id": packet_dir.name,
        "client": client_name,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_movement": TARGET_MOVEMENT,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "counts": {
            "model_calls": 0,
            "macro_recomposition_artifacts": len(artifacts),
            "required_macro_recomposition_artifacts": len(
                BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES
            ),
        },
        "gate_report": payloads["macro_recomposition_gate_report"],
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "not_human_validated": True,
    }
    return BoundedMacroRecompositionResult(
        exit_code=0,
        payload=payload,
        artifacts=tuple(artifacts.values()),
        gate_record=gate_record,
    )


def _load_macro_subject(
    connection: sqlite3.Connection,
    config: AbiConfig,
    synthesis_packet_dir: Path,
) -> MacroSubject:
    resolved_packet_dir = _resolve_path(config, synthesis_packet_dir)
    if not resolved_packet_dir.exists() or not resolved_packet_dir.is_dir():
        raise ValueError(f"synthesis packet directory not found: {synthesis_packet_dir}")
    missing = [
        file_name
        for file_name in REQUIRED_SYNTHESIS_ARTIFACT_FILES
        if not (resolved_packet_dir / file_name).exists()
    ]
    if missing:
        raise ValueError(
            "synthesis packet is missing required artifacts: " + ", ".join(missing)
        )
    payloads = {
        file_name.removesuffix(".json"): _read_payload(resolved_packet_dir / file_name)
        for file_name in REQUIRED_SYNTHESIS_ARTIFACT_FILES
    }
    packet = payloads["autonomous_evidence_synthesis_packet"]
    best = payloads["best_current_candidate_selection"]
    macro_brief = payloads["macro_recomposition_brief"]
    selected = best.get("selected_best_candidate")
    if not isinstance(selected, dict):
        raise ValueError("best_current_candidate_selection lacks selected_best_candidate")
    if macro_brief.get("target_region_or_movement") != TARGET_MOVEMENT:
        raise ValueError(
            "macro recomposition brief does not target middle_and_return_movement"
        )
    if macro_brief.get("allowed_scale") != "bounded_macro_recomposition_not_full_rewrite":
        raise ValueError("macro recomposition brief does not require bounded scale")
    if selected.get("packet_id") == "packet_0022":
        raise ValueError("synthesis-selected base is the failed pivot packet_0022")
    run_id = str(packet.get("run_id") or "")
    if not run_id:
        raise ValueError("synthesis packet has no run_id")
    synthesis_artifact_ids = packet.get("artifact_ids", {})
    if not isinstance(synthesis_artifact_ids, dict):
        synthesis_artifact_ids = {}
    base_packet_dir = _resolve_path(config, Path(str(selected.get("packet_dir", ""))))
    if not base_packet_dir.exists():
        raise ValueError(f"selected best candidate packet not found: {base_packet_dir}")
    base_packet_kind = str(selected.get("packet_kind") or "")
    base_payload = _load_base_candidate_payload(base_packet_dir, base_packet_kind)
    base_text = str(base_payload.get("text") or "")
    if not base_text:
        raise ValueError("selected best candidate packet has no candidate text")
    expected_hash = selected.get("selected_best_candidate_text_sha256") or selected.get(
        "text_sha256"
    )
    actual_hash = sha256_text(base_text)
    if expected_hash and str(expected_hash) != actual_hash:
        raise ValueError("selected best candidate text hash does not match base text")
    source_parent_ids = _source_parent_ids(connection, resolved_packet_dir, synthesis_artifact_ids)
    base_candidate_artifact_id = selected.get("candidate_artifact_id")
    if isinstance(base_candidate_artifact_id, str):
        source_parent_ids = _unique([*source_parent_ids, base_candidate_artifact_id])
    return MacroSubject(
        run_id=run_id,
        synthesis_packet_dir=resolved_packet_dir,
        synthesis_packet_id=str(packet.get("packet_id") or resolved_packet_dir.name),
        synthesis_artifact_ids={
            str(key): str(value) for key, value in synthesis_artifact_ids.items()
        },
        synthesis_payloads=payloads,
        selected_best_candidate=selected,
        base_packet_dir=base_packet_dir,
        base_packet_id=str(selected.get("packet_id") or base_packet_dir.name),
        base_packet_kind=base_packet_kind,
        base_candidate_artifact_id=(
            base_candidate_artifact_id if isinstance(base_candidate_artifact_id, str) else None
        ),
        base_text=base_text,
        base_text_sha256=actual_hash,
        base_word_count=len(_words(base_text)),
        source_parent_ids=tuple(source_parent_ids),
        fixture_only=any(
            bool(payload.get("fixture_only"))
            for payload in payloads.values()
            if isinstance(payload, dict)
        ),
    )


def _build_subject_manifest(
    subject: MacroSubject,
    packet_dir: Path,
    *,
    client_name: str,
    max_model_calls: int,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "max_model_calls": max_model_calls,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "source_synthesis_artifact_ids": subject.synthesis_artifact_ids,
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_kind": subject.base_packet_kind,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_artifact_id": subject.base_candidate_artifact_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "base_candidate_word_count": subject.base_word_count,
        "base_from_synthesis_selected_best_candidate": True,
        "failed_pivot_packet_used_as_base": subject.base_packet_id == "packet_0022",
        "original_candidate_used_as_base": False,
        "packet_0030_used_as_base": subject.base_packet_id == "packet_0030",
        "target_movement": TARGET_MOVEMENT,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_subject_manifest_v1_controller",
    }


def _build_brief_ref(subject: MacroSubject) -> dict[str, object]:
    brief = subject.synthesis_payloads["macro_recomposition_brief"]
    return {
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "macro_recomposition_brief_artifact_id": subject.synthesis_artifact_ids.get(
            "macro_recomposition_brief"
        ),
        "brief_type": brief.get("brief_type"),
        "target_region_or_movement": brief.get("target_region_or_movement"),
        "allowed_scale": brief.get("allowed_scale"),
        "protected_effects_to_preserve": list(brief.get("protected_effects_to_preserve", [])),
        "forbidden_changes": list(brief.get("forbidden_changes", [])),
        "success_criteria": list(brief.get("success_criteria", [])),
        "ablation_plan_after_recomposition": list(
            brief.get("ablation_plan_after_recomposition", [])
        ),
        "not_candidate_artifact": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_brief_ref_v1_controller",
    }


def _build_work_order(subject: MacroSubject) -> dict[str, object]:
    return {
        "work_order_id": f"macro_recomposition_{subject.synthesis_packet_id}",
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_movement": TARGET_MOVEMENT,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "allowed_touch": "multiple adjacent spans in the middle/return movement",
        "controller_owns": [
            "source packet references",
            "base candidate text",
            "macro target spans",
            "protected effects",
            "forbidden changes",
            "text assembly",
            "diff report",
            "gate report",
            "finalization status",
        ],
        "model_may_own_if_live_later": [
            "recomposition plan",
            "replacement section text",
            "rationale",
            "local-law explanation",
            "uncertainty",
        ],
        "model_must_not_own": [
            "finalization fields",
            "gate pass/fail",
            "before text",
            "source packet IDs",
            "phase-shift claim",
            "unrestricted full rewrite authority",
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_work_order_v1_controller",
    }


def _build_protected_effects(subject: MacroSubject) -> dict[str, object]:
    brief = subject.synthesis_payloads["macro_recomposition_brief"]
    protected = _unique(
        [
            *list(brief.get("protected_effects_to_preserve", [])),
            "table/dust/spoon/saucer local field",
            "proof from inside the line it integrates",
            "cosmic silence as isolation condition of proof",
            "return without regression",
            "strongest-rival pressure",
            "best current candidate's useful record/law/proof/answer compression",
        ]
    )
    forbidden = _unique(
        [
            *list(brief.get("forbidden_changes", [])),
            "rewriting the whole artifact",
            "thinning the opening scene",
            "repeating local record/law/proof/answer compression as the main move",
            "naming pressure more often instead of embodying pressure",
            "adding outside rescue",
            "weakening cosmic silence into mere lack of help",
            "marking final or phase-shift success",
        ]
    )
    return {
        "protected_effects": protected,
        "forbidden_changes": forbidden,
        "best_current_candidate_repair_preserved": True,
        "strongest_rival_pressure_must_remain_active": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "protected_effects_and_forbidden_changes_v1_controller",
    }


def _build_recomposition_plan(subject: MacroSubject) -> dict[str, object]:
    return {
        "plan_id": f"bounded_macro_plan_{sha256_text(subject.base_text)[:12]}",
        "target_movement": TARGET_MOVEMENT,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "plan_steps": [
            {
                "step_id": "macro_step_001",
                "action": "preserve opening scene and current useful compression",
                "rationale": "The synthesis selected the packet_0014 candidate as the current best base.",
            },
            {
                "step_id": "macro_step_002",
                "action": "replace the middle proof ladder with object/event sequence",
                "rationale": "The failed pivot showed pressure must be embodied rather than named.",
            },
            {
                "step_id": "macro_step_003",
                "action": "recompose return as record-bearing change, not explanatory closure",
                "rationale": "The return must carry contradiction internally.",
            },
            {
                "step_id": "macro_step_004",
                "action": "leave strongest-rival pressure unresolved and test later by executed ablation",
                "rationale": "No internal packet has closed rival pressure.",
            },
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_plan_v1_fake_controller",
    }


def _build_patch_or_section_plan(
    subject: MacroSubject,
    recomposed: RecomposedText,
) -> dict[str, object]:
    return {
        "section_plan_id": f"macro_section_{sha256_text(''.join(recomposed.replacement))[:12]}",
        "target_movement": TARGET_MOVEMENT,
        "target_paragraph_start_index": recomposed.target_start_index,
        "target_paragraph_end_index": recomposed.target_end_index,
        "unchanged_prefix_paragraph_count": len(recomposed.unchanged_prefix),
        "changed_paragraph_count": len(recomposed.replacement),
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "before_section_text": "\n\n".join(recomposed.original_target),
        "replacement_section_text": "\n\n".join(recomposed.replacement),
        "source_base_text_sha256": subject.base_text_sha256,
        "rationale": (
            "Replace the middle/return movement as one adjacent bounded section, "
            "preserving the selected base opening and object field."
        ),
        "worker": "macro_patch_or_section_plan_v1_fake_controller",
    }


def _build_recomposed_candidate(
    subject: MacroSubject,
    recomposed: RecomposedText,
) -> dict[str, object]:
    return {
        "candidate_id": f"bounded_macro_recomposition_{sha256_text(recomposed.text)[:12]}",
        "text": recomposed.text,
        "text_sha256": sha256_text(recomposed.text),
        "word_count": len(_words(recomposed.text)),
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_text_sha256": subject.base_text_sha256,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "target_movement": TARGET_MOVEMENT,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "assembled_by_controller": True,
        "candidate_only": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": subject.fixture_only,
        "requires_executed_ablation_before_improvement_claim": True,
        "worker": "macro_recomposed_candidate_text_v1_fake_controller",
    }


def _build_diff_report(
    subject: MacroSubject,
    recomposed: RecomposedText,
    candidate: dict[str, object],
) -> dict[str, object]:
    return {
        "base_candidate_packet_id": subject.base_packet_id,
        "base_text_sha256": subject.base_text_sha256,
        "revised_text_sha256": candidate["text_sha256"],
        "base_word_count": subject.base_word_count,
        "revised_word_count": candidate["word_count"],
        "target_movement": TARGET_MOVEMENT,
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "opening_scene_preserved": True,
        "unchanged_prefix_paragraph_count": len(recomposed.unchanged_prefix),
        "changed_paragraph_start_index": recomposed.target_start_index,
        "changed_paragraph_end_index": recomposed.target_end_index,
        "changed_spans": [
            {
                "changed_span_id": "macro_change_001",
                "movement": TARGET_MOVEMENT,
                "before_text": "\n\n".join(recomposed.original_target),
                "after_text": "\n\n".join(recomposed.replacement),
                "operation_type": "bounded_section_recomposition",
                "inside_target": True,
                "rationale": "Turn proof/return explanation into object-event sequence.",
            }
        ],
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_diff_report_v1_controller",
    }


def _build_rival_pressure_check(
    subject: MacroSubject,
    candidate: dict[str, object],
) -> dict[str, object]:
    rival = subject.synthesis_payloads["rival_pressure_summary"]
    text = str(candidate["text"]).lower()
    object_terms = ["table", "dust", "spoon", "saucer", "ring"]
    return {
        "strongest_rival_present": bool(rival.get("strongest_rival_present")),
        "strongest_rival_pressure_preserved": True,
        "strongest_rival_still_blocks": True,
        "strongest_rival_comparison_passed": False,
        "object_field_terms_preserved": [
            term for term in object_terms if term in text
        ],
        "current_candidate_closes_gap": False,
        "reason": (
            "The bounded recomposition preserves rival pressure for later testing; "
            "it does not claim to beat the strongest rival."
        ),
        "requires_executed_ablation_before_improvement_claim": True,
        "not_human_data": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "worker": "macro_rival_pressure_check_v1_controller",
    }


def _build_gate_report(
    *,
    subject: MacroSubject,
    subject_manifest: dict[str, object],
    protected_effects: dict[str, object],
    diff_report: dict[str, object],
    rival_check: dict[str, object],
) -> dict[str, object]:
    gate_results = [
        _gate_result("macro_recomposition_packet_exists", True),
        _gate_result("synthesis_packet_consumed", True),
        _gate_result(
            "best_candidate_used_as_base",
            subject_manifest["base_from_synthesis_selected_best_candidate"]
            and subject.base_packet_id != "packet_0022",
        ),
        _gate_result("macro_recomposition_bounded", bool(diff_report["bounded_macro_recomposition"])),
        _gate_result(
            "protected_effects_recorded",
            bool(protected_effects["protected_effects"])
            and bool(protected_effects["forbidden_changes"]),
        ),
        _gate_result(
            "rival_pressure_preserved",
            bool(rival_check["strongest_rival_pressure_preserved"]),
        ),
        _gate_result(
            "macro_recomposition_executed_ablation_completed",
            False,
            ["macro recomposition has not yet been tested by executed ablation"],
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            False,
            [
                "strongest-rival pressure remains blocking",
                "macro candidate requires executed ablation before any improvement claim",
            ],
        ),
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
    return {
        "passed": False,
        "eligible": False,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "non_final": True,
        "not_human_validated": True,
        "not_human_data": True,
        "no_phase_shift_claim": True,
        "phase_shift_claim": False,
        "strongest_rival_pressure_preserved": True,
        "requires_executed_ablation_before_improvement_claim": True,
        "operator_approval_absent": True,
        "profile": "autonomous_creative_candidate",
        "gate_results": gate_results,
        "failed_gates": failed_gates,
        "missing_gates": ["internal_operator_approval"],
        "final_gates_marked_passed": [],
        "unresolved_blockers": [
            "macro recomposition has not yet been tested by executed ablation",
            "strongest-rival pressure remains blocking",
            "internal operator approval is absent",
        ],
        "summary_verdict": (
            "Bounded macro recomposition produced a candidate for later executed "
            "ablation, but it is not final and makes no improvement claim."
        ),
        "worker": "macro_recomposition_gate_report_v1_controller",
    }


def _build_packet_summary(
    *,
    subject: MacroSubject,
    packet_dir: Path,
    payloads: dict[str, dict[str, object]],
    artifacts: dict[str, ArtifactRecord],
    client_name: str,
) -> dict[str, object]:
    return {
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "client": client_name,
        "source_synthesis_packet_id": subject.synthesis_packet_id,
        "source_synthesis_packet_dir": str(subject.synthesis_packet_dir),
        "base_candidate_packet_id": subject.base_packet_id,
        "base_candidate_packet_dir": str(subject.base_packet_dir),
        "base_candidate_text_sha256": subject.base_text_sha256,
        "target_movement": TARGET_MOVEMENT,
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_types": list(artifacts),
        "counts": {
            "model_calls": 0,
            "macro_recomposition_artifacts": len(artifacts),
            "required_macro_recomposition_artifacts": len(
                BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES
            ),
        },
        "candidate_artifact_id": artifacts["macro_recomposed_candidate_text"].id,
        "diff_report_artifact_id": artifacts["macro_recomposition_diff_report"].id,
        "rival_pressure_check_artifact_id": artifacts["macro_rival_pressure_check"].id,
        "gate_report": payloads["macro_recomposition_gate_report"],
        "bounded_macro_recomposition": True,
        "full_rewrite": False,
        "requires_executed_ablation_before_improvement_claim": True,
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "worker": "macro_recomposition_packet_v1_controller",
    }


def _fake_recompose_text(base_text: str) -> RecomposedText:
    paragraphs = _paragraphs(base_text)
    start = _target_start(paragraphs)
    unchanged_prefix = paragraphs[:start]
    original_target = paragraphs[start:]
    replacement = [
        (
            "The deeper pattern does not arrive as a sentence placed over the room. "
            "It starts where the room is already busy: the ring drying lighter at "
            "one edge, the dust dragged into a narrow fan by a passing shoe, the "
            "spoon turning a small seam of light toward the cracked saucer. Each "
            "object keeps its own history, but none of the histories stays sealed. "
            "The table gathers them without becoming an explanation of them."
        ),
        (
            "Pressure enters through these crossings. The cup leaves the ring, the "
            "ring changes the wood, the dust records the shoe, and the shoe belongs "
            "to a body that had already left the kitchen before morning could name "
            "what happened. Nothing needs to announce a law. The law is the way one "
            "condition presses into the next until the boundary between them becomes "
            "visible enough to hurt."
        ),
        (
            "No answer comes from outside that pressure. The silence above the room "
            "is not a refusal of comfort added for mood; it is the condition that "
            "keeps the proof honest. If help arrived from beyond the line, the line "
            "would no longer have to carry what it had made. The table would become "
            "a prop in someone else's solution. Instead it stays local, and the "
            "local facts have to bear each other all the way through."
        ),
        (
            "So return cannot mean going back to the untouched table. The table was "
            "never untouched. The ring, the dust, the spoon, the saucer, the weak "
            "light, the small engine-hum of the refrigerator: they are not damage "
            "laid over a purer beginning. They are the beginning finding out what it "
            "was able to include. The room comes back to itself with the record "
            "still in it."
        ),
        (
            "In the morning, the table is still there. The dust is still under it. "
            "The spoon is still on its side. Nothing has been rescued from the room, "
            "and nothing has escaped into an answer elsewhere. Yet the facts no "
            "longer sit as separate proofs waiting to be named. They lean into one "
            "another, and the table holds the leaning: a small world returning, not "
            "unchanged, but with enough of its own pressure inside it to be read."
        ),
    ]
    text = "\n\n".join([*unchanged_prefix, *replacement])
    return RecomposedText(
        text=text,
        target_start_index=start,
        target_end_index=len(paragraphs),
        unchanged_prefix=unchanged_prefix,
        original_target=original_target,
        replacement=replacement,
    )


def _load_base_candidate_payload(packet_dir: Path, packet_kind: str) -> dict[str, Any]:
    if packet_kind == "ablation_informed_revision":
        return _read_payload(packet_dir / "cycle2_revised_candidate_text.json")
    if packet_kind == "autonomous_revision":
        return _read_payload(packet_dir / "revised_candidate_text.json")
    raise ValueError(f"unsupported selected best candidate packet kind: {packet_kind}")


def _source_parent_ids(
    connection: sqlite3.Connection,
    synthesis_packet_dir: Path,
    synthesis_artifact_ids: dict[object, object],
) -> list[str]:
    parent_ids = [str(value) for value in synthesis_artifact_ids.values() if isinstance(value, str)]
    packet_artifact = _artifact_for_path(
        connection,
        synthesis_packet_dir / "autonomous_evidence_synthesis_packet.json",
    )
    if packet_artifact is not None:
        parent_ids.append(packet_artifact.id)
    return _unique(parent_ids)


def _artifact_for_path(connection: sqlite3.Connection, path: Path) -> ArtifactRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM artifacts
        WHERE path IN (?, ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(path), str(path.resolve())),
    ).fetchone()
    return row_to_artifact(row) if row is not None else None


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"required artifact is missing: {path.name}")
    envelope = read_json_file(path)
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"artifact payload is not an object: {path.name}")
    return payload


def _resolve_path(config: AbiConfig, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (config.root / path).resolve()


def _target_start(paragraphs: list[str]) -> int:
    needles = (
        "There is a deeper pattern",
        "A line of life and mind",
        "That is why the sky",
    )
    for index, paragraph in enumerate(paragraphs):
        if any(needle in paragraph for needle in needles):
            return index
    return max(1, len(paragraphs) - 4)


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]


def _words(text: str) -> list[str]:
    return [word for word in text.split() if word]


def _unique(values: list[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not value:
            continue
        value_text = str(value)
        if value_text not in result:
            result.append(value_text)
    return result


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


def _refusal(
    *,
    message: str,
    synthesis_packet: Path,
    client_name: str | None = None,
    model: str | None = None,
) -> BoundedMacroRecompositionResult:
    payload = {
        "accepted": False,
        "refused": True,
        "client": client_name,
        "model": model,
        "synthesis_packet": str(synthesis_packet),
        "message": message,
        "counts": {"model_calls": 0},
        "finalization_eligible": False,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
    }
    return BoundedMacroRecompositionResult(exit_code=1, payload=payload)
