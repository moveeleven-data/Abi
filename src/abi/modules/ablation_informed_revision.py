"""Ablation-informed manual revision cycle v1."""

from __future__ import annotations

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
from abi.packets import PacketWriter, create_packet_dir, read_json_file


ABLATION_INFORMED_REVISION_LINEAGE_ID = "ablation_informed_revision_cycle_v1"
ABLATION_INFORMED_REVISION_ACTIVE_PHASE = "ablation_informed_revision_cycle_v1"
ABLATION_INFORMED_REVISION_CLIENT_FAKE = "fake"
ABLATION_INFORMED_REVISION_CLIENT_OPENAI = "openai"
ABLATION_INFORMED_REVISION_CLIENTS = (
    ABLATION_INFORMED_REVISION_CLIENT_FAKE,
    ABLATION_INFORMED_REVISION_CLIENT_OPENAI,
)
ABLATION_INFORMED_REVISION_MAX_MODEL_CALLS_DEFAULT = 8

ABLATION_INFORMED_REVISION_ARTIFACT_TYPES = (
    "ablation_informed_revision_subject_manifest",
    "ablation_evidence_summary",
    "cycle2_base_candidate_selection",
    "selected_next_failure_or_handle",
    "ablation_informed_revision_work_order",
    "cycle2_patch_proposal",
    "cycle2_revised_candidate_text",
    "cycle2_revision_diff_report",
    "cycle2_preliminary_old_new_rival_comparison",
    "cycle2_gate_report",
    "cycle2_packet",
)

BASE_CHOICE_ORIGINAL = "original_candidate"
BASE_CHOICE_PACKET_0030 = "packet_0030_revised_candidate"
BASE_CHOICE_EMBODIMENT = "embodiment_preserving_ablation_variant"
BASE_CHOICE_RECORD = "record_label_compression_ablation_variant"
BASE_CHOICE_CONTROLLER_COMPOSED = "controller_composed_base_from_evidence_supported_changes"


@dataclass(frozen=True)
class AblationInformedRevisionResult:
    exit_code: int
    payload: dict[str, object]
    gate_records: tuple[GateRecord, ...] = ()


@dataclass(frozen=True)
class SourceText:
    label: str
    source_class: str
    artifact_id: str
    text: str


@dataclass(frozen=True)
class AblationInformedSubject:
    run_id: str
    packet_dir: Path
    packet_id: str
    packet_artifact_id: str | None
    artifacts: dict[str, ArtifactRecord]
    payloads: dict[str, dict[str, Any]]
    revision_packet_dir: Path
    revision_packet_id: str
    revision_artifacts: dict[str, ArtifactRecord]
    revision_payloads: dict[str, dict[str, Any]]
    reader_lab_packet_dir: Path
    reader_lab_packet_id: str
    source_packet_dir: Path
    source_packet_id: str
    source_texts: tuple[SourceText, ...]

    @property
    def original_candidate(self) -> SourceText:
        return self.text_by_source_class("abi_candidate")

    @property
    def packet_0030_revised_text(self) -> str:
        return str(self.revision_payloads["revised_candidate_text"]["text"])

    @property
    def strongest_rival(self) -> SourceText | None:
        for text in self.source_texts:
            if text.source_class == "strongest_rival":
                return text
        return None

    def text_by_source_class(self, source_class: str) -> SourceText:
        for text in self.source_texts:
            if text.source_class == source_class:
                return text
        raise KeyError(source_class)

    def variant_by_operation_id(self, operation_id: str) -> dict[str, Any] | None:
        variants = self.payloads["actual_ablation_variant_set"]["variants"]
        for variant in variants:
            if str(variant.get("operation_id")) == operation_id:
                return variant
        return None


def run_ablation_informed_revision(
    config: AbiConfig,
    *,
    client_name: str,
    executed_ablation_packet: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = ABLATION_INFORMED_REVISION_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
) -> AblationInformedRevisionResult:
    if client_name not in ABLATION_INFORMED_REVISION_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            executed_ablation_packet=executed_ablation_packet,
            message=(
                "Ablation-informed revision client is not available: "
                f"{client_name}"
            ),
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < 0:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            executed_ablation_packet=executed_ablation_packet,
            message=(
                "Ablation-informed revision refused; max-model-calls must be "
                "non-negative."
            ),
        )
    if client_name == ABLATION_INFORMED_REVISION_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            executed_ablation_packet=executed_ablation_packet,
            message=(
                "Ablation-informed revision refused; pass --allow-live-model to opt "
                "in explicitly."
            ),
        )
    resolved_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == ABLATION_INFORMED_REVISION_CLIENT_OPENAI and not resolved_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            executed_ablation_packet=executed_ablation_packet,
            message=f"Ablation-informed revision refused; {OPENAI_API_KEY_ENV} is not set.",
        )
    if client_name == ABLATION_INFORMED_REVISION_CLIENT_OPENAI:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            executed_ablation_packet=executed_ablation_packet,
            message=(
                "Ablation-informed revision OpenAI worker is not implemented in this "
                "manual cycle; use --client fake for deterministic local revision."
            ),
        )

    packet_dir = _resolve_path(config, executed_ablation_packet)
    if not packet_dir.exists() or not packet_dir.is_dir():
        return _refusal(
            client_name=client_name,
            model=None,
            executed_ablation_packet=packet_dir,
            message=(
                "Ablation-informed revision refused; executed ablation packet "
                f"directory not found: {packet_dir}"
            ),
        )

    initialize_database(config)
    try:
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, packet_dir)
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    client_name=client_name,
                    model=None,
                    executed_ablation_packet=packet_dir,
                    message=(
                        "Ablation-informed revision refused; run is not registered: "
                        f"{subject.run_id}"
                    ),
                )
            output_dir = create_packet_dir(
                config.run_dir(subject.run_id) / "ablation_informed_revision"
            )
            set_active_phase(
                connection,
                subject.run_id,
                ABLATION_INFORMED_REVISION_ACTIVE_PHASE,
            )
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            client_name=client_name,
            model=None,
            executed_ablation_packet=packet_dir,
            message=(
                "Ablation-informed revision refused; invalid executed ablation "
                f"packet: {error}"
            ),
        )

    return _run_fake_packet(config=config, subject=subject, output_dir=output_dir)


def _run_fake_packet(
    *,
    config: AbiConfig,
    subject: AblationInformedSubject,
    output_dir: Path,
) -> AblationInformedRevisionResult:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=output_dir,
            lineage_id=ABLATION_INFORMED_REVISION_LINEAGE_ID,
            created_by="ablation_informed_revision_cycle_v1_controller",
            fixture_only=True,
            model_call_id=None,
        )

        payloads["ablation_informed_revision_subject_manifest"] = _build_subject_manifest(
            subject
        )
        artifacts["ablation_informed_revision_subject_manifest"] = writer.write_artifact(
            "ablation_informed_revision_subject_manifest",
            payloads["ablation_informed_revision_subject_manifest"],
            parent_ids=_subject_parent_ids(subject),
        )

        payloads["ablation_evidence_summary"] = _build_evidence_summary(subject)
        artifacts["ablation_evidence_summary"] = writer.write_artifact(
            "ablation_evidence_summary",
            payloads["ablation_evidence_summary"],
            parent_ids=[
                subject.artifacts["ablation_causal_effect_report"].id,
                subject.artifacts["ablation_old_new_rival_comparison"].id,
                subject.artifacts["comparison_consistency_report"].id,
                subject.artifacts["actual_ablation_variant_set"].id,
            ],
        )

        payloads["cycle2_base_candidate_selection"] = _build_base_selection(
            subject,
            payloads["ablation_evidence_summary"],
        )
        artifacts["cycle2_base_candidate_selection"] = writer.write_artifact(
            "cycle2_base_candidate_selection",
            payloads["cycle2_base_candidate_selection"],
            parent_ids=[
                artifacts["ablation_evidence_summary"].id,
                subject.revision_artifacts["revised_candidate_text"].id,
                subject.artifacts["actual_ablation_variant_set"].id,
            ],
        )

        payloads["selected_next_failure_or_handle"] = _build_next_handle(
            subject,
            payloads["ablation_evidence_summary"],
        )
        artifacts["selected_next_failure_or_handle"] = writer.write_artifact(
            "selected_next_failure_or_handle",
            payloads["selected_next_failure_or_handle"],
            parent_ids=[
                artifacts["ablation_evidence_summary"].id,
                subject.revision_artifacts["selected_failure_diagnosis"].id,
                subject.artifacts["ablation_causal_effect_report"].id,
            ],
        )

        payloads["ablation_informed_revision_work_order"] = _build_work_order(
            subject=subject,
            base_selection=payloads["cycle2_base_candidate_selection"],
            next_handle=payloads["selected_next_failure_or_handle"],
        )
        artifacts["ablation_informed_revision_work_order"] = writer.write_artifact(
            "ablation_informed_revision_work_order",
            payloads["ablation_informed_revision_work_order"],
            parent_ids=[
                artifacts["cycle2_base_candidate_selection"].id,
                artifacts["selected_next_failure_or_handle"].id,
                subject.artifacts["executed_ablation_work_order"].id,
            ],
        )

        payloads["cycle2_patch_proposal"] = _build_patch_proposal(
            payloads["ablation_informed_revision_work_order"]
        )
        artifacts["cycle2_patch_proposal"] = writer.write_artifact(
            "cycle2_patch_proposal",
            payloads["cycle2_patch_proposal"],
            parent_ids=[artifacts["ablation_informed_revision_work_order"].id],
        )

        payloads["cycle2_revised_candidate_text"] = _build_revised_candidate(
            base_selection=payloads["cycle2_base_candidate_selection"],
            patch_proposal=payloads["cycle2_patch_proposal"],
        )
        artifacts["cycle2_revised_candidate_text"] = writer.write_artifact(
            "cycle2_revised_candidate_text",
            payloads["cycle2_revised_candidate_text"],
            parent_ids=[
                artifacts["cycle2_base_candidate_selection"].id,
                artifacts["cycle2_patch_proposal"].id,
            ],
        )

        payloads["cycle2_revision_diff_report"] = _build_diff_report(
            base_selection=payloads["cycle2_base_candidate_selection"],
            work_order=payloads["ablation_informed_revision_work_order"],
            patch_proposal=payloads["cycle2_patch_proposal"],
            revised_candidate=payloads["cycle2_revised_candidate_text"],
        )
        artifacts["cycle2_revision_diff_report"] = writer.write_artifact(
            "cycle2_revision_diff_report",
            payloads["cycle2_revision_diff_report"],
            parent_ids=[
                artifacts["ablation_informed_revision_work_order"].id,
                artifacts["cycle2_patch_proposal"].id,
                artifacts["cycle2_revised_candidate_text"].id,
            ],
        )

        payloads["cycle2_preliminary_old_new_rival_comparison"] = (
            _build_preliminary_comparison(
                subject=subject,
                base_selection=payloads["cycle2_base_candidate_selection"],
                revised_candidate=payloads["cycle2_revised_candidate_text"],
            )
        )
        artifacts["cycle2_preliminary_old_new_rival_comparison"] = writer.write_artifact(
            "cycle2_preliminary_old_new_rival_comparison",
            payloads["cycle2_preliminary_old_new_rival_comparison"],
            parent_ids=[
                artifacts["cycle2_revised_candidate_text"].id,
                artifacts["cycle2_revision_diff_report"].id,
                subject.artifacts["ablation_old_new_rival_comparison"].id,
            ],
        )

        payloads["cycle2_gate_report"] = _build_gate_report(
            subject=subject,
            evidence_summary=payloads["ablation_evidence_summary"],
            revised_candidate=payloads["cycle2_revised_candidate_text"],
            preliminary_comparison=payloads[
                "cycle2_preliminary_old_new_rival_comparison"
            ],
        )
        artifacts["cycle2_gate_report"] = writer.write_artifact(
            "cycle2_gate_report",
            payloads["cycle2_gate_report"],
            parent_ids=[
                artifacts["cycle2_revised_candidate_text"].id,
                artifacts["cycle2_preliminary_old_new_rival_comparison"].id,
            ],
        )

        payloads["cycle2_packet"] = _build_packet_summary(
            subject=subject,
            packet_dir=output_dir,
            artifacts=artifacts,
            payloads=payloads,
        )
        artifacts["cycle2_packet"] = writer.write_artifact(
            "cycle2_packet",
            payloads["cycle2_packet"],
            parent_ids=[
                artifacts[artifact_type].id
                for artifact_type in ABLATION_INFORMED_REVISION_ARTIFACT_TYPES[:-1]
            ],
        )

    return AblationInformedRevisionResult(
        exit_code=0,
        payload=_summary_payload(
            subject=subject,
            packet_dir=output_dir,
            client_name=ABLATION_INFORMED_REVISION_CLIENT_FAKE,
            artifacts=artifacts,
            payloads=payloads,
            accepted=True,
            message=None,
            model=None,
        ),
    )


def _build_subject_manifest(subject: AblationInformedSubject) -> dict[str, Any]:
    return {
        "worker": "ablation_informed_revision_subject_manifest_v1",
        "run_id": subject.run_id,
        "executed_ablation_packet_id": subject.packet_id,
        "executed_ablation_packet_dir": str(subject.packet_dir),
        "executed_ablation_packet_artifact_id": subject.packet_artifact_id,
        "executed_ablation_artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in subject.artifacts.items()
        },
        "source_autonomous_revision_packet_id": subject.revision_packet_id,
        "source_autonomous_revision_packet_dir": str(subject.revision_packet_dir),
        "source_reader_lab_packet_id": subject.reader_lab_packet_id,
        "source_reader_lab_packet_dir": str(subject.reader_lab_packet_dir),
        "source_packet_id": subject.source_packet_id,
        "source_packet_dir": str(subject.source_packet_dir),
        "original_candidate": _text_ref(subject.original_candidate),
        "packet_0030_revised_candidate": {
            "artifact_id": subject.revision_artifacts["revised_candidate_text"].id,
            "text_sha256": sha256_text(subject.packet_0030_revised_text),
            "word_count": len(_words(subject.packet_0030_revised_text)),
        },
        "strongest_rival": _text_ref(subject.strongest_rival),
        "previous_repair_causal_status": subject.payloads[
            "ablation_causal_effect_report"
        ]["selected_repair_causal_status"],
        "controller_owned": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_evidence_summary(subject: AblationInformedSubject) -> dict[str, Any]:
    causal = subject.payloads["ablation_causal_effect_report"]
    old_new = subject.payloads["ablation_old_new_rival_comparison"]
    execution = subject.payloads["ablation_execution_report"]
    consistency = subject.payloads["comparison_consistency_report"]
    variant_set = subject.payloads["actual_ablation_variant_set"]
    countable = [
        {
            "variant_id": variant["variant_id"],
            "operation_id": variant["operation_id"],
            "operation_type": variant["operation_type"],
            "evidence_countable": variant["evidence_countable"],
            "text_sha256": variant["text_sha256"],
        }
        for variant in variant_set["variants"]
        if variant["evidence_countable"]
    ]
    return {
        "worker": "ablation_evidence_summary_v1_controller",
        "source_executed_ablation_packet_id": subject.packet_id,
        "previous_repair_causal_status": causal["selected_repair_causal_status"],
        "previous_repair_treated_as_proven": False,
        "packet_0030_treated_as_proven_improvement": False,
        "repair_has_causal_support": old_new["repair_has_causal_support"],
        "revert_performs_same_or_better": old_new["revert_performs_same_or_better"],
        "record_compression_improves_discovery": old_new[
            "record_compression_improves_discovery"
        ],
        "embodiment_preserving_variant_beats_current": old_new[
            "embodiment_preserving_variant_beats_current"
        ],
        "strongest_rival_pressure_remains_blocking": causal[
            "strongest_rival_pressure_remains_blocking"
        ],
        "countable_evidence_variant_count": execution[
            "countable_evidence_variant_count"
        ],
        "countable_variants": countable,
        "comparison_internal_consistency": consistency[
            "comparison_internal_consistency"
        ],
        "evidence_interpretation": (
            "The first repair is treated as weak/noncausal evidence. Cycle 2 may "
            "preserve only the supported opening compression while superseding the "
            "flattened embodiment and moving the main handle to record/law/proof/"
            "answer compression."
        ),
        "requires_cycle2_executed_ablation_before_improvement_claim": True,
        "not_human_data": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_base_selection(
    subject: AblationInformedSubject,
    evidence_summary: dict[str, Any],
) -> dict[str, Any]:
    original = subject.original_candidate.text
    packet_0030 = subject.packet_0030_revised_text
    embodiment_variant = subject.variant_by_operation_id(
        "operation_embodiment_preserving_repair"
    )
    record_variant = subject.variant_by_operation_id("operation_record_label_compression")
    controller_base = _compose_cycle2_base_from_evidence(
        original,
        subject.packet_0030_revised_text,
    )
    choices = [
        _base_option(BASE_CHOICE_ORIGINAL, original, "source Text A before packet_0030"),
        _base_option(
            BASE_CHOICE_PACKET_0030,
            packet_0030,
            "packet_0030 revised candidate, not assumed proven",
        ),
    ]
    if embodiment_variant is not None:
        choices.append(
            _base_option(
                BASE_CHOICE_EMBODIMENT,
                str(embodiment_variant["text"]),
                "executed embodiment-preserving ablation variant",
            )
        )
    if record_variant is not None:
        choices.append(
            _base_option(
                BASE_CHOICE_RECORD,
                str(record_variant["text"]),
                "executed record-label compression ablation variant",
            )
        )
    choices.append(
        _base_option(
            BASE_CHOICE_CONTROLLER_COMPOSED,
            controller_base,
            "controller-composed base from evidence-supported opening changes",
        )
    )
    return {
        "worker": "cycle2_base_candidate_selection_v1_controller",
        "controller_owned": True,
        "allowed_choices": [
            BASE_CHOICE_ORIGINAL,
            BASE_CHOICE_PACKET_0030,
            BASE_CHOICE_EMBODIMENT,
            BASE_CHOICE_RECORD,
            BASE_CHOICE_CONTROLLER_COMPOSED,
        ],
        "base_candidate_options": choices,
        "selected_base_choice": BASE_CHOICE_CONTROLLER_COMPOSED,
        "selected_base_text": controller_base,
        "selected_base_text_sha256": sha256_text(controller_base),
        "selected_base_word_count": len(_words(controller_base)),
        "selection_rationale": (
            "Use a controller-composed base: preserve the supported removal of 'as if "
            "nothing happened' while restoring concrete embodiment from the original/"
            "embodiment-preserving evidence. Packet_0030 is not treated as proven."
        ),
        "previous_repair_causal_status": evidence_summary["previous_repair_causal_status"],
        "previous_repair_treated_as_proven": False,
        "packet_0030_changes_superseded": [
            "flattened legs/plain wording",
            "flattened spoon placement",
            "weakened refrigerator/weather detail",
        ],
        "packet_0030_changes_preserved_if_supported": [
            "removed 'as if nothing happened' from the opening embodiment field"
        ],
        "embodiment_preserving_insight_represented": True,
        "record_law_proof_compression_deferred_to_patch": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_next_handle(
    subject: AblationInformedSubject,
    evidence_summary: dict[str, Any],
) -> dict[str, Any]:
    selected_failure = subject.revision_payloads["selected_failure_diagnosis"]
    return {
        "worker": "selected_next_failure_or_handle_v1_controller",
        "previous_selected_failure": selected_failure.get("selected_failure_type"),
        "previous_repair_causal_status": evidence_summary[
            "previous_repair_causal_status"
        ],
        "why_previous_repair_was_weak_or_cosmetic": (
            "Executed ablation reported revert performs same or better and repair "
            "has no strong causal support, so the packet_0030 opening patch cannot "
            "be reused as proof of improvement."
        ),
        "executed_ablation_evidence": {
            "revert_performs_same_or_better": evidence_summary[
                "revert_performs_same_or_better"
            ],
            "record_compression_improves_discovery": evidence_summary[
                "record_compression_improves_discovery"
            ],
            "embodiment_preserving_variant_beats_current": evidence_summary[
                "embodiment_preserving_variant_beats_current"
            ],
            "strongest_rival_pressure_remains_blocking": evidence_summary[
                "strongest_rival_pressure_remains_blocking"
            ],
        },
        "selected_next_handle": "record_law_proof_answer_compression",
        "why_better_supported_than_repeating_opening_patch": (
            "Record-label compression was countable executed evidence and improved "
            "discovery in the ablation comparison, while repeating packet_0030's "
            "opening patch would preserve an unproven repair."
        ),
        "revision_goal": [
            "preserve or restore concrete opening embodiment",
            "compress early record/law/proof/answer labels",
            "let objects carry significance longer before naming it",
            "preserve philosophical pressure without turning descriptive only",
        ],
        "strongest_rival_pressure_preserved": True,
        "controller_owned_evidence_selection": True,
        "model_owned_fields_allowed_if_live": [
            "replacement_text",
            "rationale",
            "local_law_explanation",
            "uncertainty",
        ],
        "model_must_not_own": [
            "finalization fields",
            "gate pass/fail",
            "before text",
            "authoritative full revised text",
            "target IDs",
            "span IDs",
            "evidence counts",
        ],
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_work_order(
    *,
    subject: AblationInformedSubject,
    base_selection: dict[str, Any],
    next_handle: dict[str, Any],
) -> dict[str, Any]:
    base_text = str(base_selection["selected_base_text"])
    patchable_spans = _patchable_spans(base_text)
    allowed_target = {
        "patch_target_id": "cycle2_target_record_law_proof_answer_compression",
        "target_label": "record/law/proof/answer compression",
        "member_patch_span_ids": [
            str(span["patch_span_id"]) for span in patchable_spans
        ],
        "evidence_source": "executed ablation record-label compression variant",
    }
    return {
        "worker": "ablation_informed_revision_work_order_v1_controller",
        "controller_owned": True,
        "source_executed_ablation_packet_dir": str(subject.packet_dir),
        "source_executed_ablation_packet_id": subject.packet_id,
        "source_autonomous_revision_packet_dir": str(subject.revision_packet_dir),
        "source_autonomous_revision_packet_id": subject.revision_packet_id,
        "source_reader_lab_packet_dir": str(subject.reader_lab_packet_dir),
        "source_reader_lab_packet_id": subject.reader_lab_packet_id,
        "selected_base_candidate": base_selection["selected_base_choice"],
        "base_candidate_text_sha256": base_selection["selected_base_text_sha256"],
        "candidate_span_inventory": _candidate_span_inventory(base_text),
        "allowed_patch_targets": [allowed_target],
        "allowed_patch_target_ids": [allowed_target["patch_target_id"]],
        "patchable_spans": patchable_spans,
        "patchable_span_ids": [
            str(span["patch_span_id"]) for span in patchable_spans
        ],
        "protected_effects": [
            "domestic stillness",
            "morning quiet",
            "concrete table/kitchen embodiment",
            "philosophical pressure carried by objects",
        ],
        "forbidden_changes": [
            "rewrite the full artifact",
            "remove the table/kitchen setup",
            "add external plot",
            "turn the piece into abstract argument only",
            "claim final or phase-shift success",
        ],
        "strongest_rival_reference": _text_ref(subject.strongest_rival),
        "ablation_evidence_references": {
            "executed_ablation_packet_artifact_id": subject.packet_artifact_id,
            "ablation_causal_effect_report": subject.artifacts[
                "ablation_causal_effect_report"
            ].id,
            "actual_ablation_variant_set": subject.artifacts[
                "actual_ablation_variant_set"
            ].id,
            "ablation_old_new_rival_comparison": subject.artifacts[
                "ablation_old_new_rival_comparison"
            ].id,
        },
        "selected_next_handle": next_handle["selected_next_handle"],
        "previous_repair_treated_as_proven": False,
        "bounded_revision_only": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_patch_proposal(work_order: dict[str, Any]) -> dict[str, Any]:
    patches = []
    replacements = _cycle2_replacements()
    for index, span in enumerate(work_order["patchable_spans"], start=1):
        before = str(span["exact_text"])
        after = replacements.get(before)
        if after is None:
            continue
        patches.append(
            {
                "patch_id": f"cycle2_patch_{index:03d}",
                "patch_target_id": "cycle2_target_record_law_proof_answer_compression",
                "patch_span_id": span["patch_span_id"],
                "replacement_text": after,
                "rationale": (
                    "Compress early interpretive labels so objects carry significance "
                    "longer before the text names the pattern."
                ),
                "evidence_source": "ablation_old_new_rival_comparison.record_compression_improves_discovery",
                "preserves_or_supersedes_packet_0030_prior_patch": "supersedes",
                "bounded_patch": True,
            }
        )
    return {
        "worker": "cycle2_patch_proposal_v1_deterministic",
        "controller_validated": True,
        "full_rewrite": False,
        "bounded_patch_set": True,
        "selected_next_handle": work_order["selected_next_handle"],
        "patches": patches,
        "model_call_id": None,
        "model_owned_fields": [],
        "controller_owned_fields": [
            "patch_id",
            "patch_target_id",
            "patch_span_id",
            "before_text via work_order",
            "evidence_source",
        ],
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_revised_candidate(
    *,
    base_selection: dict[str, Any],
    patch_proposal: dict[str, Any],
) -> dict[str, Any]:
    text = str(base_selection["selected_base_text"])
    source_patch_ids = []
    source_patch_span_ids = []
    for patch in patch_proposal["patches"]:
        span_before = _span_before_from_patch_id(base_selection, patch)
        if span_before and span_before in text:
            text = text.replace(span_before, str(patch["replacement_text"]), 1)
            source_patch_ids.append(str(patch["patch_id"]))
            source_patch_span_ids.append(str(patch["patch_span_id"]))
    return {
        "worker": "cycle2_revised_candidate_text_v1_controller",
        "text": text,
        "text_sha256": sha256_text(text),
        "word_count": len(_words(text)),
        "assembled_by_controller": True,
        "base_candidate_choice": base_selection["selected_base_choice"],
        "base_candidate_text_sha256": base_selection["selected_base_text_sha256"],
        "source_patch_ids": source_patch_ids,
        "source_patch_span_ids": source_patch_span_ids,
        "bounded_recomposition": True,
        "full_rewrite": False,
        "previous_repair_treated_as_proven": False,
        "supersedes_packet_0030_patch": True,
        "cycle2_requires_executed_ablation_before_improvement_claim": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_diff_report(
    *,
    base_selection: dict[str, Any],
    work_order: dict[str, Any],
    patch_proposal: dict[str, Any],
    revised_candidate: dict[str, Any],
) -> dict[str, Any]:
    spans_by_id = {
        str(span["patch_span_id"]): span for span in work_order["patchable_spans"]
    }
    changed_spans = []
    for patch in patch_proposal["patches"]:
        span = spans_by_id[str(patch["patch_span_id"])]
        before = str(span["exact_text"])
        after = str(patch["replacement_text"])
        changed_spans.append(
            {
                "changed_span_id": f"cycle2_change_{len(changed_spans) + 1:03d}",
                "patch_id": patch["patch_id"],
                "patch_span_id": patch["patch_span_id"],
                "source_patch_span_ids": [patch["patch_span_id"]],
                "before_text": before,
                "after_text": after,
                "change_rationale": patch["rationale"],
                "evidence_source": patch["evidence_source"],
                "preserves_or_supersedes_packet_0030_prior_patch": patch[
                    "preserves_or_supersedes_packet_0030_prior_patch"
                ],
                "inside_target": True,
                "within_selected_target": True,
            }
        )
    return {
        "worker": "cycle2_revision_diff_report_v1_controller",
        "controller_owned": True,
        "base_candidate_choice": base_selection["selected_base_choice"],
        "base_text_sha256": base_selection["selected_base_text_sha256"],
        "revised_text_sha256": revised_candidate["text_sha256"],
        "source_patch_ids": list(revised_candidate["source_patch_ids"]),
        "source_patch_span_ids": list(revised_candidate["source_patch_span_ids"]),
        "changed_spans": changed_spans,
        "material_change_count": len(changed_spans),
        "bounded_change": True,
        "full_rewrite": False,
        "all_material_changes_reported": True,
        "previous_repair_treated_as_proven": False,
        "not_human_data": True,
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_preliminary_comparison(
    *,
    subject: AblationInformedSubject,
    base_selection: dict[str, Any],
    revised_candidate: dict[str, Any],
) -> dict[str, Any]:
    original_score = _score_text(subject.original_candidate.text)
    packet_0030_score = _score_text(subject.packet_0030_revised_text)
    cycle2_score = _score_text(str(revised_candidate["text"]))
    rival_score = (
        _score_text(subject.strongest_rival.text)
        if subject.strongest_rival is not None
        else None
    )
    old_new = subject.payloads["ablation_old_new_rival_comparison"]
    cycle2_text = str(revised_candidate["text"])
    return {
        "worker": "cycle2_preliminary_old_new_rival_comparison_v1",
        "comparison_basis": "deterministic ablation-informed preliminary comparison; not proof",
        "preliminary_not_proof": True,
        "does_not_count_as_executed_ablation_evidence": True,
        "compared_items": [
            "original Text A",
            "packet_0030 revised Text A",
            "cycle2 revised candidate",
            "strongest rival Text D",
            "record-label compression ablation variant",
            "embodiment-preserving ablation variant",
        ],
        "scores": {
            "original": original_score,
            "packet_0030": packet_0030_score,
            "cycle2": cycle2_score,
            "strongest_rival": rival_score,
        },
        "cycle2_reduced_overexplanation": (
            cycle2_score["overexplanation_score"]
            < packet_0030_score["overexplanation_score"]
        ),
        "cycle2_preserved_embodiment_better_than_packet_0030": (
            cycle2_score["local_embodiment_score"]
            >= packet_0030_score["local_embodiment_score"]
            and "The legs are steady." in cycle2_text
            and "A spoon lies on its side" in cycle2_text
        ),
        "record_law_proof_compression_improved_discovery": bool(
            old_new["record_compression_improves_discovery"]
        ),
        "strongest_rival_remains_stronger": bool(
            old_new["strongest_rival_still_beats_candidate"]
        ),
        "cycle2_should_proceed_to_executed_ablation_next": True,
        "rationale": (
            "Cycle2 combines the supported opening-detail preservation with the "
            "record/law/proof compression handle. This is preliminary and must be "
            "tested by executed ablation before any improvement claim."
        ),
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _build_gate_report(
    *,
    subject: AblationInformedSubject,
    evidence_summary: dict[str, Any],
    revised_candidate: dict[str, Any],
    preliminary_comparison: dict[str, Any],
) -> dict[str, Any]:
    unresolved = [
        "cycle2 requires executed ablation before any improvement claim",
        "strongest-rival pressure remains blocking",
        "internal operator approval is absent",
        "fake ablation-informed revision mode is fixture-only",
    ]
    gate_results = [
        _gate_result("ablation_informed_revision_packet_exists", True),
        _gate_result(
            "previous_repair_causal_status_recorded_as_weak",
            evidence_summary["previous_repair_causal_status"]
            in {"noncausal_or_cosmetic", "ambiguous"},
        ),
        _gate_result("cycle2_bounded_revision_produced", True),
        _gate_result("strongest_rival_pressure_preserved", True),
        _gate_result(
            "cycle2_executed_ablation_completed",
            False,
            ["cycle2 has not yet been tested by executed counterfactual ablation"],
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
        "worker": "cycle2_gate_report_v1_controller",
        "profile": "autonomous_creative_candidate",
        "passed": False,
        "eligible": False,
        "previous_repair_causal_status": evidence_summary[
            "previous_repair_causal_status"
        ],
        "previous_repair_treated_as_proven": False,
        "cycle2_bounded_revision_produced": bool(revised_candidate["text"]),
        "strongest_rival_pressure_preserved": preliminary_comparison[
            "strongest_rival_remains_stronger"
        ],
        "cycle2_requires_executed_ablation_before_claim": True,
        "operator_approval_absent": True,
        "unresolved_blockers": unresolved,
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
        "fixture_only": True,
        "not_human_data": True,
        "summary_verdict": (
            "Cycle2 produced a bounded ablation-informed revision, but it remains "
            "diagnostic, non-final, and requires executed ablation before any "
            "improvement claim."
        ),
        "source_executed_ablation_packet_id": subject.packet_id,
    }


def _build_packet_summary(
    *,
    subject: AblationInformedSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "worker": "cycle2_packet_v1",
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_executed_ablation_packet_id": subject.packet_id,
        "source_executed_ablation_packet_dir": str(subject.packet_dir),
        "source_autonomous_revision_packet_id": subject.revision_packet_id,
        "source_reader_lab_packet_id": subject.reader_lab_packet_id,
        "artifact_types": list(ABLATION_INFORMED_REVISION_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "ablation_informed_revision_artifacts": len(artifacts),
            "required_ablation_informed_revision_artifacts": len(
                ABLATION_INFORMED_REVISION_ARTIFACT_TYPES
            ),
            "model_calls": 0,
        },
        "selected_base_choice": payloads["cycle2_base_candidate_selection"][
            "selected_base_choice"
        ],
        "selected_next_handle": payloads["selected_next_failure_or_handle"][
            "selected_next_handle"
        ],
        "previous_repair_causal_status": payloads["ablation_evidence_summary"][
            "previous_repair_causal_status"
        ],
        "previous_repair_treated_as_proven": False,
        "gate_report": payloads["cycle2_gate_report"],
        "model_call_ids": [],
        "non_final": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "no_phase_shift_claim": True,
        "fixture_only": True,
        "not_human_data": True,
    }


def _load_subject(connection, packet_dir: Path) -> AblationInformedSubject:
    packet_envelope = read_json_file(packet_dir / "executed_ablation_packet.json")
    if packet_envelope.get("artifact_type") != "executed_ablation_packet":
        raise ValueError("packet must contain executed_ablation_packet.json")
    packet_payload = packet_envelope["payload"]
    if not isinstance(packet_payload, dict):
        raise ValueError("executed ablation packet payload is not an object")
    run_id = str(packet_envelope["run_id"])
    packet_id = str(packet_payload.get("packet_id", packet_dir.name))
    artifact_ids = dict(packet_payload["artifact_ids"])

    required = (
        "executed_ablation_subject_manifest",
        "executed_ablation_work_order",
        "actual_ablation_variant_set",
        "ablation_execution_report",
        "ablation_internal_reader_comparison",
        "ablation_old_new_rival_comparison",
        "comparison_consistency_report",
        "ablation_causal_effect_report",
        "executed_ablation_gate_report",
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
        artifact_path=packet_dir / "executed_ablation_packet.json",
    )
    if packet_artifact is not None:
        artifacts["executed_ablation_packet"] = packet_artifact
        payloads["executed_ablation_packet"] = packet_payload

    subject_manifest = payloads["executed_ablation_subject_manifest"]
    revision_packet_dir = Path(str(subject_manifest["revision_packet_dir"])).resolve()
    revision_packet = read_json_file(
        revision_packet_dir / "autonomous_closed_loop_packet.json"
    )["payload"]
    revision_artifact_ids = dict(revision_packet["artifact_ids"])
    revision_required = (
        "autonomous_revision_subject_manifest",
        "selected_failure_diagnosis",
        "autonomous_revision_work_order",
        "revision_patch_proposal",
        "revised_candidate_text",
        "revision_diff_report",
        "old_new_rival_comparison",
        "local_law_case_note",
    )
    revision_artifacts: dict[str, ArtifactRecord] = {}
    revision_payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in revision_required:
        artifact = _artifact_from_packet(connection, revision_artifact_ids, artifact_type)
        revision_artifacts[artifact_type] = artifact
        revision_payloads[artifact_type] = _artifact_payload(artifact)

    source_packet_dir = Path(str(revision_packet["source_packet_dir"])).resolve()
    reader_lab_packet_dir = Path(str(revision_packet["reader_lab_packet_dir"])).resolve()
    source_texts = _load_source_texts(source_packet_dir)
    if not any(text.source_class == "abi_candidate" for text in source_texts):
        raise ValueError("source packet does not include an Abi candidate text")
    return AblationInformedSubject(
        run_id=run_id,
        packet_dir=packet_dir,
        packet_id=packet_id,
        packet_artifact_id=packet_artifact.id if packet_artifact is not None else None,
        artifacts=artifacts,
        payloads=payloads,
        revision_packet_dir=revision_packet_dir,
        revision_packet_id=str(revision_packet["packet_id"]),
        revision_artifacts=revision_artifacts,
        revision_payloads=revision_payloads,
        reader_lab_packet_dir=reader_lab_packet_dir,
        reader_lab_packet_id=str(revision_packet["reader_lab_packet_id"]),
        source_packet_dir=source_packet_dir,
        source_packet_id=str(revision_packet["source_packet_id"]),
        source_texts=tuple(source_texts),
    )


def _artifact_from_packet(
    connection,
    artifact_ids: dict[str, object],
    artifact_type: str,
) -> ArtifactRecord:
    artifact_id = artifact_ids.get(artifact_type)
    if artifact_id is None:
        raise ValueError(f"packet is missing artifact ID for {artifact_type}")
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


def _compose_cycle2_base_from_evidence(original: str, packet_0030: str) -> str:
    text = original.replace(" as if nothing happened", "", 1)
    text = text.replace("The legs are plain.", "The legs are steady.", 1)
    text = text.replace("A spoon lies beside", "A spoon lies on its side beside", 1)
    text = text.replace(
        "The room is quiet enough that the refrigerator hum is almost weather.",
        "The room is quiet enough that the refrigerator hum feels like a small engine of weather.",
        1,
    )
    if not _patchable_spans(text):
        text = packet_0030.replace(" as if nothing happened", "", 1)
    return text


def _patchable_spans(text: str) -> list[dict[str, Any]]:
    spans = []
    for index, before in enumerate(_cycle2_replacements(), start=1):
        start = text.find(before)
        if start < 0:
            continue
        spans.append(
            {
                "patch_span_id": f"cycle2_patch_span_{index:03d}",
                "patch_target_id": "cycle2_target_record_law_proof_answer_compression",
                "char_start": start,
                "char_end": start + len(before),
                "exact_text": before,
                "selection_basis": "executed ablation record/law/proof/answer handle",
            }
        )
    return spans


def _candidate_span_inventory(text: str) -> list[dict[str, Any]]:
    inventory = []
    for index, paragraph in enumerate(text.split("\n\n"), start=1):
        if not paragraph.strip():
            continue
        inventory.append(
            {
                "span_id": f"cycle2_candidate_paragraph_{index:03d}",
                "paragraph_index": index,
                "text_sha256": sha256_text(paragraph.strip()),
                "word_count": len(_words(paragraph)),
            }
        )
    return inventory


def _cycle2_replacements() -> dict[str, str]:
    return {
        (
            "together they make a record. Not a message sent from elsewhere. "
            "A local record. The kind of record that is not trying to be believed, "
            "only noticed."
        ): (
            "together they leave a pattern. Not a message sent from elsewhere, "
            "only a set of marks asking to be noticed."
        ),
        "It obeys a law of staying and change.": "It keeps staying and change together.",
        (
            "The proof, if there is one, cannot arrive from outside the line it is "
            "meant to join."
        ): (
            "If an answer comes, it cannot arrive from outside the line it is "
            "meant to join."
        ),
        "It did not explain the night": "It held the night in the grain",
        "No visible completed answer has entered this local story.": (
            "No completed answer has entered this local story."
        ),
    }


def _span_before_from_patch_id(
    base_selection: dict[str, Any],
    patch: dict[str, Any],
) -> str | None:
    text = str(base_selection["selected_base_text"])
    replacements = _cycle2_replacements()
    for before, after in replacements.items():
        if after == patch["replacement_text"] and before in text:
            return before
    return None


def _base_option(choice: str, text: str, basis: str) -> dict[str, Any]:
    return {
        "choice": choice,
        "basis": basis,
        "text_sha256": sha256_text(text),
        "word_count": len(_words(text)),
    }


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
        "steady",
        "side",
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
        "answer",
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


def _subject_parent_ids(subject: AblationInformedSubject) -> list[str]:
    parent_ids = [artifact.id for artifact in subject.artifacts.values()]
    parent_ids.extend(artifact.id for artifact in subject.revision_artifacts.values())
    parent_ids.extend(text.artifact_id for text in subject.source_texts)
    return sorted(set(parent_ids))


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
    subject: AblationInformedSubject,
    packet_dir: Path,
    client_name: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    accepted: bool,
    message: str | None,
    model: str | None,
) -> dict[str, object]:
    return {
        "accepted": accepted,
        "refused": False,
        "client": client_name,
        "model": model,
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "executed_ablation_packet_dir": str(subject.packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "required_artifact_types": list(ABLATION_INFORMED_REVISION_ARTIFACT_TYPES),
        "counts": {
            "ablation_informed_revision_artifacts": len(artifacts),
            "required_ablation_informed_revision_artifacts": len(
                ABLATION_INFORMED_REVISION_ARTIFACT_TYPES
            ),
            "model_calls": 0,
        },
        "model_calls": [],
        "gate_report": payloads.get("cycle2_gate_report"),
        "message": message,
    }


def _refusal(
    *,
    client_name: str,
    model: str | None,
    executed_ablation_packet: Path | str,
    message: str,
) -> AblationInformedRevisionResult:
    return AblationInformedRevisionResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "executed_ablation_packet": str(executed_ablation_packet),
            "artifact_ids": {},
            "artifact_paths": {},
            "counts": {"model_calls": 0},
            "message": message,
        },
    )


def _resolve_path(config: AbiConfig, value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (config.root / path).resolve()


def _words(text: str) -> list[str]:
    return [word.strip(".,;:!?()[]{}\"'").lower() for word in text.split() if word.strip()]
