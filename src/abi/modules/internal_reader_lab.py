"""Autonomous Internal Reader Lab v1 deterministic packet."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from abi.artifacts import ArtifactRecord, get_artifact
from abi.config import AbiConfig
from abi.controller.gates import GateRecord, record_gate
from abi.controller.policy import AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES
from abi.controller.state import (
    AUTONOMOUS_INTERNAL_READER_LAB_ACTIVE_PHASE,
    get_run,
    set_active_phase,
)
from abi.db import connect, initialize_database
from abi.hashing import sha256_text
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.packets import PacketWriter, create_packet_dir, read_json_file


INTERNAL_READER_LAB_LINEAGE_ID = "autonomous_internal_reader_lab_v1"
INTERNAL_READER_LAB_CLIENT_FAKE = "fake"
INTERNAL_READER_LAB_CLIENT_OPENAI = "openai"
INTERNAL_READER_LAB_CLIENTS = (
    INTERNAL_READER_LAB_CLIENT_FAKE,
    INTERNAL_READER_LAB_CLIENT_OPENAI,
)
INTERNAL_READER_LAB_MAX_MODEL_CALLS_DEFAULT = 12
INTERNAL_READER_LAB_ARTIFACT_TYPES = (
    "internal_reader_subject_manifest",
    "internal_stream_reader_trace",
    "internal_reread_reader_trace",
    "forensic_grounding_report",
    "hostile_reader_report",
    "internal_rival_comparison",
    "internal_failure_diagnosis",
    "targeted_recomposition_plan",
    "counterfactual_ablation_plan",
    "autonomous_candidate_gate_report",
    "internal_reader_lab_packet",
)


@dataclass(frozen=True)
class InternalReaderLabResult:
    exit_code: int
    payload: dict[str, object]
    gate_records: tuple[GateRecord, ...] = ()


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
class InternalReaderSubject:
    run_id: str
    source_packet_dir: Path
    source_packet_id: str
    source_packet_artifact_id: str | None
    artifacts: dict[str, ArtifactRecord]
    payloads: dict[str, dict[str, Any]]
    texts: tuple[SubjectText, ...]

    @property
    def candidate_text(self) -> SubjectText:
        return self.text_by_source_class("abi_candidate")

    @property
    def has_strongest_rival(self) -> bool:
        return any(text.source_class == "strongest_rival" for text in self.texts)

    def text_by_source_class(self, source_class: str) -> SubjectText:
        for text in self.texts:
            if text.source_class == source_class:
                return text
        raise KeyError(source_class)


def run_internal_reader_lab(
    config: AbiConfig,
    *,
    client_name: str,
    packet_dir: Path | str,
    allow_live_model: bool = False,
    max_model_calls: int = INTERNAL_READER_LAB_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
) -> InternalReaderLabResult:
    if client_name not in INTERNAL_READER_LAB_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            packet_dir=packet_dir,
            message=f"Autonomous reader lab client is not available: {client_name}",
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < 0:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            packet_dir=packet_dir,
            message="Autonomous reader lab refused; max-model-calls must be non-negative.",
        )

    if client_name == INTERNAL_READER_LAB_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            packet_dir=packet_dir,
            message=(
                "Autonomous reader lab refused; pass --allow-live-model "
                "to opt in explicitly."
            ),
        )

    resolved_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == INTERNAL_READER_LAB_CLIENT_OPENAI and not resolved_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            packet_dir=packet_dir,
            message=f"Autonomous reader lab refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    if client_name == INTERNAL_READER_LAB_CLIENT_OPENAI:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            packet_dir=packet_dir,
            message=(
                "Autonomous reader lab OpenAI path is interface-only in v1; "
                "use --client fake for deterministic local evidence."
            ),
        )

    source_packet_dir = _resolve_path(config, packet_dir)
    if not source_packet_dir.exists() or not source_packet_dir.is_dir():
        return _refusal(
            client_name=client_name,
            model=INTERNAL_READER_LAB_CLIENT_FAKE,
            packet_dir=source_packet_dir,
            message=f"Autonomous reader lab refused; packet directory not found: {source_packet_dir}",
        )

    initialize_database(config)
    try:
        with connect(config.db_path) as connection:
            subject = _load_subject(connection, source_packet_dir)
            if get_run(connection, subject.run_id) is None:
                return _refusal(
                    client_name=client_name,
                    model=INTERNAL_READER_LAB_CLIENT_FAKE,
                    packet_dir=source_packet_dir,
                    message=(
                        "Autonomous reader lab refused; source packet run is not "
                        f"registered: {subject.run_id}"
                    ),
                )
            output_dir = create_packet_dir(config.run_dir(subject.run_id) / "internal_reader_lab")
            set_active_phase(
                connection,
                subject.run_id,
                AUTONOMOUS_INTERNAL_READER_LAB_ACTIVE_PHASE,
            )
            artifacts, payloads = _write_fake_internal_reader_packet(
                connection=connection,
                subject=subject,
                output_dir=output_dir,
            )
            gate_records = _record_internal_gates(
                connection=connection,
                run_id=subject.run_id,
                gate_report=payloads["autonomous_candidate_gate_report"],
            )
    except (KeyError, TypeError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        return _refusal(
            client_name=client_name,
            model=INTERNAL_READER_LAB_CLIENT_FAKE,
            packet_dir=source_packet_dir,
            message=f"Autonomous reader lab refused; invalid source packet: {error}",
        )

    return InternalReaderLabResult(
        exit_code=0,
        payload=_summary_payload(
            run_id=subject.run_id,
            packet_dir=output_dir,
            source_packet_dir=source_packet_dir,
            client_name=client_name,
            artifacts=artifacts,
            payloads=payloads,
            gate_records=gate_records,
            accepted=True,
            message=None,
        ),
        gate_records=tuple(gate_records),
    )


def _write_fake_internal_reader_packet(
    *,
    connection,
    subject: InternalReaderSubject,
    output_dir: Path,
) -> tuple[dict[str, ArtifactRecord], dict[str, dict[str, Any]]]:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}
    writer = PacketWriter(
        connection=connection,
        run_id=subject.run_id,
        packet_dir=output_dir,
        lineage_id=INTERNAL_READER_LAB_LINEAGE_ID,
        created_by="autonomous_internal_reader_lab_v1_fake",
        fixture_only=True,
        model_call_id=None,
    )

    payloads["internal_reader_subject_manifest"] = _build_subject_manifest(subject)
    artifacts["internal_reader_subject_manifest"] = writer.write_artifact(
        "internal_reader_subject_manifest",
        payloads["internal_reader_subject_manifest"],
        parent_ids=_subject_parent_ids(subject),
    )

    payloads["internal_stream_reader_trace"] = _build_stream_trace(subject)
    artifacts["internal_stream_reader_trace"] = writer.write_artifact(
        "internal_stream_reader_trace",
        payloads["internal_stream_reader_trace"],
        parent_ids=[artifacts["internal_reader_subject_manifest"].id],
    )

    payloads["internal_reread_reader_trace"] = _build_reread_trace(
        subject,
        payloads["internal_stream_reader_trace"],
    )
    artifacts["internal_reread_reader_trace"] = writer.write_artifact(
        "internal_reread_reader_trace",
        payloads["internal_reread_reader_trace"],
        parent_ids=[
            artifacts["internal_reader_subject_manifest"].id,
            artifacts["internal_stream_reader_trace"].id,
        ],
    )

    payloads["forensic_grounding_report"] = _build_forensic_report(
        subject,
        payloads["internal_reread_reader_trace"],
    )
    artifacts["forensic_grounding_report"] = writer.write_artifact(
        "forensic_grounding_report",
        payloads["forensic_grounding_report"],
        parent_ids=[
            artifacts["internal_reader_subject_manifest"].id,
            artifacts["internal_reread_reader_trace"].id,
        ],
    )

    payloads["hostile_reader_report"] = _build_hostile_report(
        subject,
        payloads["forensic_grounding_report"],
    )
    artifacts["hostile_reader_report"] = writer.write_artifact(
        "hostile_reader_report",
        payloads["hostile_reader_report"],
        parent_ids=[
            artifacts["internal_reader_subject_manifest"].id,
            artifacts["forensic_grounding_report"].id,
        ],
    )

    payloads["internal_rival_comparison"] = _build_rival_comparison(subject)
    artifacts["internal_rival_comparison"] = writer.write_artifact(
        "internal_rival_comparison",
        payloads["internal_rival_comparison"],
        parent_ids=[
            artifacts["internal_reader_subject_manifest"].id,
            artifacts["internal_stream_reader_trace"].id,
            artifacts["internal_reread_reader_trace"].id,
        ],
    )

    payloads["internal_failure_diagnosis"] = _build_failure_diagnosis(
        payloads["internal_stream_reader_trace"],
        payloads["internal_reread_reader_trace"],
        payloads["forensic_grounding_report"],
        payloads["hostile_reader_report"],
        payloads["internal_rival_comparison"],
    )
    artifacts["internal_failure_diagnosis"] = writer.write_artifact(
        "internal_failure_diagnosis",
        payloads["internal_failure_diagnosis"],
        parent_ids=[
            artifacts["internal_stream_reader_trace"].id,
            artifacts["internal_reread_reader_trace"].id,
            artifacts["forensic_grounding_report"].id,
            artifacts["hostile_reader_report"].id,
            artifacts["internal_rival_comparison"].id,
        ],
    )

    payloads["targeted_recomposition_plan"] = _build_recomposition_plan(
        payloads["internal_failure_diagnosis"],
    )
    artifacts["targeted_recomposition_plan"] = writer.write_artifact(
        "targeted_recomposition_plan",
        payloads["targeted_recomposition_plan"],
        parent_ids=[artifacts["internal_failure_diagnosis"].id],
    )

    payloads["counterfactual_ablation_plan"] = _build_ablation_plan(
        payloads["internal_failure_diagnosis"],
        payloads["targeted_recomposition_plan"],
    )
    artifacts["counterfactual_ablation_plan"] = writer.write_artifact(
        "counterfactual_ablation_plan",
        payloads["counterfactual_ablation_plan"],
        parent_ids=[
            artifacts["internal_failure_diagnosis"].id,
            artifacts["targeted_recomposition_plan"].id,
        ],
    )

    payloads["autonomous_candidate_gate_report"] = _build_gate_report(
        subject=subject,
        fixture_only=True,
        payloads=payloads,
    )
    artifacts["autonomous_candidate_gate_report"] = writer.write_artifact(
        "autonomous_candidate_gate_report",
        payloads["autonomous_candidate_gate_report"],
        parent_ids=[
            artifacts["internal_reader_subject_manifest"].id,
            artifacts["internal_stream_reader_trace"].id,
            artifacts["internal_reread_reader_trace"].id,
            artifacts["forensic_grounding_report"].id,
            artifacts["hostile_reader_report"].id,
            artifacts["internal_rival_comparison"].id,
            artifacts["internal_failure_diagnosis"].id,
            artifacts["targeted_recomposition_plan"].id,
            artifacts["counterfactual_ablation_plan"].id,
        ],
    )

    payloads["internal_reader_lab_packet"] = _build_packet_summary(
        subject=subject,
        packet_dir=output_dir,
        artifacts=artifacts,
        payloads=payloads,
    )
    artifacts["internal_reader_lab_packet"] = writer.write_artifact(
        "internal_reader_lab_packet",
        payloads["internal_reader_lab_packet"],
        parent_ids=[artifacts[artifact_type].id for artifact_type in INTERNAL_READER_LAB_ARTIFACT_TYPES[:-1]],
    )
    return artifacts, payloads


def _load_subject(connection, source_packet_dir: Path) -> InternalReaderSubject:
    packet_envelope = read_json_file(source_packet_dir / "pilot_packet.json")
    packet_payload = packet_envelope["payload"]
    run_id = str(packet_envelope["run_id"])
    source_packet_id = str(packet_payload.get("packet_id", source_packet_dir.name))
    artifact_ids = dict(packet_payload["artifact_ids"])
    required_types = (
        "pilot_source_manifest",
        "pilot_abi_candidate_ref",
        "pilot_direct_prompt_baseline",
        "pilot_raw_model_baseline",
        "pilot_strongest_rival_slot",
        "pilot_neutral_label_map_private",
        "pilot_blinded_reader_bundle",
    )
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for artifact_type in required_types:
        artifact = _artifact_from_packet(connection, artifact_ids, artifact_type)
        artifacts[artifact_type] = artifact
        payloads[artifact_type] = _artifact_payload(artifact)

    if "pilot_strongest_rival_import" in artifact_ids:
        artifact = _artifact_from_packet(connection, artifact_ids, "pilot_strongest_rival_import")
        artifacts["pilot_strongest_rival_import"] = artifact
        payloads["pilot_strongest_rival_import"] = _artifact_payload(artifact)

    packet_artifact = _artifact_by_path(
        connection,
        run_id=run_id,
        artifact_path=source_packet_dir / "pilot_packet.json",
    )
    if packet_artifact is not None:
        artifacts["pilot_packet"] = packet_artifact
        payloads["pilot_packet"] = packet_payload

    texts = _subject_texts(
        bundle_payload=payloads["pilot_blinded_reader_bundle"],
        label_map_payload=payloads["pilot_neutral_label_map_private"],
    )
    if not any(text.source_class == "abi_candidate" for text in texts):
        raise ValueError("source packet does not include an Abi candidate text")

    return InternalReaderSubject(
        run_id=run_id,
        source_packet_dir=source_packet_dir,
        source_packet_id=source_packet_id,
        source_packet_artifact_id=packet_artifact.id if packet_artifact is not None else None,
        artifacts=artifacts,
        payloads=payloads,
        texts=tuple(texts),
    )


def _artifact_from_packet(
    connection,
    artifact_ids: dict[str, object],
    artifact_type: str,
) -> ArtifactRecord:
    artifact_id = artifact_ids.get(artifact_type)
    if artifact_id is None:
        raise ValueError(f"source packet is missing artifact ID for {artifact_type}")
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


def _subject_texts(
    *,
    bundle_payload: dict[str, Any],
    label_map_payload: dict[str, Any],
) -> list[SubjectText]:
    label_map = label_map_payload["label_map"]
    texts: list[SubjectText] = []
    for item in bundle_payload["reader_items"]:
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


def _build_subject_manifest(subject: InternalReaderSubject) -> dict[str, Any]:
    return {
        "worker": "internal_reader_subject_manifest_v1_fake",
        "source_packet_dir": str(subject.source_packet_dir),
        "source_packet_id": subject.source_packet_id,
        "source_packet_artifact_id": subject.source_packet_artifact_id,
        "fixture_only": True,
        "not_model_judgment": True,
        "private_source_classes_internal_only": True,
        "no_human_reader_bundle_required": True,
        "texts": [
            {
                "label": text.label,
                "source_class": text.source_class,
                "artifact_id": text.artifact_id,
                "text_sha256": sha256_text(text.text),
                "word_count": text.word_count,
            }
            for text in subject.texts
        ],
    }


def _build_stream_trace(subject: InternalReaderSubject) -> dict[str, Any]:
    candidate = subject.candidate_text
    retained = _retained_images(candidate.text)
    dropped = _dropped_details(subject.texts, candidate)
    motifs = _live_motifs(candidate.text, retained)
    return {
        "worker": "internal_stream_reader_v1_fake",
        "bounded_mode": True,
        "candidate_label": candidate.label,
        "retained_images": retained,
        "dropped_details": dropped,
        "live_motifs": motifs,
        "attention_points": [
            {
                "span": _support_snippet(candidate.text, retained[0] if retained else None),
                "reason": "first visible object anchors attention",
            },
            {
                "span": _first_sentence(candidate.text),
                "reason": "opening pressure is assessed before explanation",
            },
        ],
        "confusion_points": _confusion_points(candidate.text),
        "overexplicitness_points": _overexplicitness_points(candidate.text),
        "first_read_opening_interpretation": _first_read_opening(candidate.text, retained),
        "first_read_summary": _summary_sentence(candidate.text, "first_read"),
        "not_human_data": True,
        "fixture_only": True,
    }


def _build_reread_trace(
    subject: InternalReaderSubject,
    stream_trace: dict[str, Any],
) -> dict[str, Any]:
    candidate = subject.candidate_text
    retained = list(stream_trace["retained_images"])
    changed_images = retained[:3] or ["opening"]
    return {
        "worker": "internal_reread_reader_v1_fake",
        "candidate_label": candidate.label,
        "opening_changed": True,
        "opening_words_images_changed": changed_images,
        "hidden_consequence_clearer": (
            "The opening object reads less as set dressing and more as a pressure "
            "test for whether the later field was planted."
        ),
        "motif_returned_changed": [
            {
                "motif": motif,
                "first_read_state": "noticed",
                "reread_state": "tested for causal pressure",
            }
            for motif in stream_trace["live_motifs"]
        ],
        "reread_summary": _summary_sentence(candidate.text, "reread"),
        "reread_gain_estimate": _reread_gain_estimate(candidate.text, retained),
        "not_human_data": True,
        "fixture_only": True,
    }


def _build_forensic_report(
    subject: InternalReaderSubject,
    reread_trace: dict[str, Any],
) -> dict[str, Any]:
    candidate = subject.candidate_text
    support_terms = list(reread_trace["opening_words_images_changed"])
    support = [
        {
            "claim": f"{term} carries reread pressure",
            "exact_textual_support": _support_snippet(candidate.text, str(term)),
        }
        for term in support_terms
    ]
    unsupported = []
    if candidate.word_count < 120:
        unsupported.append("reread gain is only lightly grounded because the candidate is brief")
    return {
        "worker": "forensic_grounding_reader_v1_fake",
        "claimed_effects": [
            "opening returns with changed pressure",
            "local image should carry consequence",
            "candidate should resist paraphrase capture",
        ],
        "exact_textual_support": support,
        "unsupported_claims": unsupported,
        "fake_depth_risk": "medium" if unsupported else "low",
        "reread_claims_grounded": not unsupported,
        "grounding_verdict": (
            "partially grounded" if unsupported else "grounded for deterministic scaffold"
        ),
        "not_human_data": True,
        "fixture_only": True,
    }


def _build_hostile_report(
    subject: InternalReaderSubject,
    forensic_report: dict[str, Any],
) -> dict[str, Any]:
    candidate = subject.candidate_text
    register_risk = "wrong_register" if _contains(candidate.text, ("must", "claim", "source")) else "low"
    return {
        "worker": "hostile_internal_reader_v1_fake",
        "attacks": [
            _attack("fake_depth", str(forensic_report["fake_depth_risk"])),
            _attack("overexplanation", "check whether the text tells the reader what to infer"),
            _attack("scaffold_leakage", "scan for process terms replacing artifact pressure"),
            _attack("wrong_register", register_risk),
            _attack("accidental_comedy", "low but monitored around abrupt scale shifts"),
            _attack("cliche_contamination", "ordinary domestic image may flatten if unsupported"),
            _attack("thesis_replacing_artifact", "risk if explanatory cadence outruns image"),
            _attack("pasted_ending", "ending pressure must feel seeded by opening"),
            _attack("unearned_cosmic_scale", "block metaphysical scale not licensed locally"),
        ],
        "blocking_risks": [
            "forensic grounding is not strong enough for autonomous finalization",
            "rival pressure must remain active until internal comparison improves",
        ],
        "not_human_data": True,
        "fixture_only": True,
    }


def _build_rival_comparison(subject: InternalReaderSubject) -> dict[str, Any]:
    scores = [_score_subject_text(text) for text in subject.texts]
    source_by_label = {text.label: text.source_class for text in subject.texts}
    candidate_score = next(score for score in scores if score["source_class"] == "abi_candidate")
    strongest_rival = next(
        (score for score in scores if score["source_class"] == "strongest_rival"),
        None,
    )
    loses = []
    if strongest_rival is None:
        loses.append("strongest rival is absent, so rival pressure is unresolved")
    elif int(strongest_rival["local_embodiment_score"]) >= int(
        candidate_score["local_embodiment_score"]
    ):
        loses.append("strongest rival matches or exceeds local embodiment")
    if int(candidate_score["compression_score"]) < max(
        int(score["compression_score"]) for score in scores
    ):
        loses.append("candidate is not the most compressed text")
    return {
        "worker": "internal_rival_comparator_v1_fake",
        "scores": scores,
        "source_classes_by_label": source_by_label,
        "strongest_by_first_read_clarity": _max_label(scores, "first_read_clarity_score"),
        "strongest_by_reread_transformation": _max_label(scores, "reread_transformation_score"),
        "strongest_by_local_embodiment": _max_label(scores, "local_embodiment_score"),
        "strongest_by_compression_necessity": _max_label(scores, "compression_score"),
        "abi_candidate_loses_where": loses,
        "abi_candidate_wins_where": [
            "candidate keeps source hash lineage visible",
            "candidate carries explicit non-final safety flags outside reader-facing text",
        ],
        "rival_preservation_remains_required": True,
        "strongest_rival_present": strongest_rival is not None,
        "not_human_data": True,
        "fixture_only": True,
    }


def _build_failure_diagnosis(
    stream_trace: dict[str, Any],
    reread_trace: dict[str, Any],
    forensic_report: dict[str, Any],
    hostile_report: dict[str, Any],
    rival_comparison: dict[str, Any],
) -> dict[str, Any]:
    failures = [
        _failure(
            "underplanted",
            "opening pressure is present but needs more causal planting",
            ["internal_stream_reader_trace", "forensic_grounding_report"],
        ),
        _failure(
            "paraphrase_capture",
            "first-read summary can still flatten into premise statement",
            ["internal_stream_reader_trace"],
        ),
    ]
    if forensic_report["fake_depth_risk"] != "low":
        failures.append(
            _failure(
                "fake_depth",
                "claimed reread change outruns exact textual support",
                ["forensic_grounding_report"],
            )
        )
    if rival_comparison["rival_preservation_remains_required"]:
        failures.append(
            _failure(
                "rival_stronger_local_embodiment",
                "rival pressure remains unresolved by internal comparison",
                ["internal_rival_comparison"],
            )
        )
    if hostile_report["blocking_risks"]:
        failures.append(
            _failure(
                "cadence_or_register_damage",
                "hostile reader flags process cadence risk",
                ["hostile_reader_report"],
            )
        )
    return {
        "worker": "internal_failure_diagnoser_v1_fake",
        "failure_types_present": [failure["failure_type"] for failure in failures],
        "failures": failures,
        "reread_gain_estimate": reread_trace["reread_gain_estimate"],
        "requires_recomposition": True,
        "not_human_data": True,
        "fixture_only": True,
    }


def _build_recomposition_plan(failure_diagnosis: dict[str, Any]) -> dict[str, Any]:
    plan_items = []
    for index, failure in enumerate(failure_diagnosis["failures"], start=1):
        plan_items.append(
            {
                "step_id": f"recompose_{index:02d}",
                "target_region": "opening-to-first-return bridge",
                "causal_handle": _handle_for_failure(str(failure["failure_type"])),
                "failure_being_addressed": failure["failure_type"],
                "protected_effects": [
                    "preserve candidate non-final status",
                    "preserve strongest-rival pressure",
                    "preserve local image before interpretation",
                ],
                "forbidden_changes": [
                    "do not rewrite the whole artifact",
                    "do not add thesis explanation",
                    "do not claim finality or phase shift",
                ],
                "expected_improvement": "narrowly increase grounded reread pressure",
                "verification_plan": "rerun stream/reread/forensic traces against edited region",
            }
        )
    return {
        "worker": "targeted_recomposition_planner_v1_fake",
        "bounded": True,
        "does_not_rewrite_artifact": True,
        "plan_items": plan_items,
        "not_human_data": True,
        "fixture_only": True,
    }


def _build_ablation_plan(
    failure_diagnosis: dict[str, Any],
    recomposition_plan: dict[str, Any],
) -> dict[str, Any]:
    ablations = []
    for index, plan_item in enumerate(recomposition_plan["plan_items"], start=1):
        ablations.append(
            {
                "ablation_id": f"ablation_{index:02d}",
                "suspected_causal_handle": plan_item["causal_handle"],
                "ablation_operation": "remove or move the handle in a controlled copy",
                "predicted_reader_state_effect": (
                    "reread gain should drop if the handle is causally necessary"
                ),
                "test_condition": "compare internal traces before and after the ablation",
                "pass_fail_criterion": "pass if predicted drop appears without new scaffold leakage",
            }
        )
    return {
        "worker": "counterfactual_ablation_planner_v1_fake",
        "lightweight_plan_only": True,
        "does_not_execute_full_ablation": True,
        "source_failure_types": list(failure_diagnosis["failure_types_present"]),
        "ablation_tests": ablations,
        "not_human_data": True,
        "fixture_only": True,
    }


def _build_gate_report(
    *,
    subject: InternalReaderSubject,
    fixture_only: bool,
    payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    unresolved = list(payloads["internal_failure_diagnosis"]["failure_types_present"])
    gate_results = [
        _gate_result("autonomous_candidate_packet_exists", True),
        _gate_result("internal_stream_reader_trace_exists", True),
        _gate_result("internal_reread_trace_exists", True),
        _gate_result("forensic_grounding_report_exists", True),
        _gate_result("hostile_reader_report_exists", True),
        _gate_result("failure_diagnosis_exists", True),
        _gate_result("targeted_recomposition_plan_exists", True),
        _gate_result("counterfactual_ablation_plan_or_result_exists", True),
        _gate_result(
            "rival_preservation_present",
            subject.has_strongest_rival,
            ["strongest rival remains absent"] if not subject.has_strongest_rival else [],
        ),
        _gate_result("internal_rival_comparison_exists", True),
        _gate_result(
            "no_fixture_only_core_evidence",
            not fixture_only,
            ["internal reader lab v1 fake mode is fixture-only"] if fixture_only else [],
        ),
        _gate_result(
            "no_unresolved_internal_blockers",
            not unresolved,
            [f"unresolved failure type: {failure_type}" for failure_type in unresolved],
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
    missing = [
        result["gate_name"]
        for result in gate_results
        if not result["record"]
    ]
    return {
        "worker": "autonomous_candidate_gate_report_v1_fake",
        "profile": "autonomous_creative_candidate",
        "eligible": False,
        "passed": False,
        "required_gates": list(AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES),
        "gate_results": gate_results,
        "failed_gates": failed,
        "missing_gates": missing,
        "final_gates_marked_passed": [],
        "human_validation_required": False,
        "paper_validation_required": False,
        "phase_shift_claim": False,
        "summary_verdict": (
            "Autonomous reader lab evidence exists, but fake fixture mode, "
            "unresolved internal blockers, and missing operator approval keep "
            "autonomous finalization refused."
        ),
        "fixture_only": True,
    }


def _build_packet_summary(
    *,
    subject: InternalReaderSubject,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gate_report = payloads["autonomous_candidate_gate_report"]
    return {
        "worker": "internal_reader_lab_packet_v1_fake",
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "source_packet_id": subject.source_packet_id,
        "source_packet_dir": str(subject.source_packet_dir),
        "artifact_types": list(INTERNAL_READER_LAB_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "candidate_label": subject.candidate_text.label,
        "strongest_rival_present": subject.has_strongest_rival,
        "autonomous_profile_eligible": False,
        "failed_gates": list(gate_report["failed_gates"]),
        "missing_gates": list(gate_report["missing_gates"]),
        "final_gates_marked_passed": [],
        "no_phase_shift_claim": True,
        "fixture_only": True,
    }


def _record_internal_gates(
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
    source_packet_dir: Path,
    client_name: str,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, Any]],
    gate_records: list[GateRecord],
    accepted: bool,
    message: str | None,
) -> dict[str, object]:
    return {
        "accepted": accepted,
        "refused": False,
        "client": client_name,
        "run_id": run_id,
        "packet_id": packet_dir.name,
        "packet_dir": str(packet_dir),
        "source_packet_dir": str(source_packet_dir),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "required_artifact_types": list(INTERNAL_READER_LAB_ARTIFACT_TYPES),
        "counts": {
            "internal_reader_lab_artifacts": len(artifacts),
            "required_internal_reader_lab_artifacts": len(INTERNAL_READER_LAB_ARTIFACT_TYPES),
            "model_calls": 0,
            "recorded_autonomous_gates": len(gate_records),
        },
        "gate_report": payloads["autonomous_candidate_gate_report"],
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
    packet_dir: Path | str,
    message: str,
) -> InternalReaderLabResult:
    return InternalReaderLabResult(
        exit_code=1,
        payload={
            "accepted": False,
            "refused": True,
            "client": client_name,
            "model": model,
            "packet_dir": str(packet_dir),
            "artifact_ids": {},
            "artifact_paths": {},
            "counts": {"model_calls": 0},
            "message": message,
        },
    )


def _subject_parent_ids(subject: InternalReaderSubject) -> list[str]:
    parent_ids = [
        artifact.id
        for artifact_type, artifact in subject.artifacts.items()
        if artifact_type.startswith("pilot_")
    ]
    return sorted(set(parent_ids))


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
        "source",
        "pressure",
    )
    lowered = text.lower()
    retained = [term for term in image_terms if term in lowered]
    return retained[:6] or _words(text)[:3]


def _dropped_details(texts: tuple[SubjectText, ...], candidate: SubjectText) -> list[str]:
    candidate_words = set(_words(candidate.text.lower()))
    comparison_words = set()
    for text in texts:
        if text.label == candidate.label:
            continue
        comparison_words.update(_words(text.text.lower()))
    dropped = [
        word
        for word in ("cup", "dust", "window", "light", "night", "room", "silence")
        if word in comparison_words and word not in candidate_words
    ]
    return dropped or ["no major image drop detected by deterministic scan"]


def _live_motifs(text: str, retained_images: list[str]) -> list[str]:
    motifs = [image for image in retained_images if image in {"table", "morning", "room", "pressure"}]
    if "still" in text.lower() and "stillness" not in motifs:
        motifs.append("stillness")
    return motifs[:4] or retained_images[:2]


def _confusion_points(text: str) -> list[dict[str, str]]:
    points = []
    if len(_words(text)) < 120:
        points.append(
            {
                "span": _first_sentence(text),
                "issue": "brief candidate may not supply enough causal bridge",
            }
        )
    return points


def _overexplicitness_points(text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    points = []
    for marker in ("claim", "must", "source", "pressure"):
        if marker in lowered:
            points.append(
                {
                    "marker": marker,
                    "risk": "process language may replace artifact pressure",
                }
            )
    return points[:3]


def _first_read_opening(text: str, retained_images: list[str]) -> str:
    focus = retained_images[0] if retained_images else "opening"
    return f"The first read treats {focus} as a concrete local anchor, not proof yet."


def _summary_sentence(text: str, mode: str) -> str:
    prefix = "First read" if mode == "first_read" else "Reread"
    return f"{prefix} summary: {_first_sentence(text)}"


def _reread_gain_estimate(text: str, retained: list[str]) -> dict[str, object]:
    base = 0.35 + min(len(retained), 5) * 0.08
    if len(_words(text)) < 120:
        base -= 0.1
    return {
        "score": round(max(0.0, min(base, 0.85)), 2),
        "scale": "0_to_1_internal_fake_estimate",
        "not_human_score": True,
    }


def _score_subject_text(text: SubjectText) -> dict[str, object]:
    words = text.word_count
    retained_count = len(_retained_images(text.text))
    return {
        "label": text.label,
        "source_class": text.source_class,
        "first_read_clarity_score": min(10, 4 + retained_count),
        "reread_transformation_score": min(10, 3 + retained_count + (1 if words > 100 else 0)),
        "local_embodiment_score": min(10, 3 + retained_count),
        "compression_score": max(1, min(10, 10 - abs(words - 120) // 40)),
    }


def _max_label(scores: list[dict[str, object]], field: str) -> str:
    return str(max(scores, key=lambda score: int(score[field]))["label"])


def _failure(failure_type: str, diagnosis: str, evidence: list[str]) -> dict[str, object]:
    return {
        "failure_type": failure_type,
        "diagnosis": diagnosis,
        "evidence_artifacts": evidence,
        "severity": "blocking",
    }


def _handle_for_failure(failure_type: str) -> str:
    handles = {
        "underplanted": "plant one local consequence before explanation",
        "paraphrase_capture": "replace summary-like sentence with embodied action",
        "fake_depth": "tie claimed pressure to exact object behavior",
        "rival_stronger_local_embodiment": "borrow no text; increase local specificity",
        "cadence_or_register_damage": "lower abstract cadence near opening",
    }
    return handles.get(failure_type, "adjust the smallest causal handle")


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


def _attack(risk_type: str, finding: str) -> dict[str, str]:
    return {
        "risk_type": risk_type,
        "finding": finding,
    }


def _support_snippet(text: str, term: str | None = None) -> str:
    sentences = _sentences(text)
    if term is None:
        return sentences[0] if sentences else text[:120]
    lowered_term = term.lower()
    for sentence in sentences:
        if lowered_term in sentence.lower():
            return sentence
    return sentences[0] if sentences else text[:120]


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


def _resolve_path(config: AbiConfig, path: Path | str) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = config.root / resolved
    return resolved.resolve()
