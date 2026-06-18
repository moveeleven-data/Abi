"""Final-artifact candidate and paper-packet scaffold for Phase 13."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from abi.artifacts import ArtifactRecord, get_artifact, list_all_artifacts
from abi.config import AbiConfig
from abi.controller.policy import GATE_PROFILE_FINAL_ARTIFACT
from abi.controller.release_readiness import evaluate_release_readiness
from abi.controller.state import PHASE13_FINAL_ARTIFACT_PACKET_ACTIVE_PHASE, set_active_phase
from abi.db import connect, initialize_database
from abi.live_model import ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT, OPENAI_API_KEY_ENV
from abi.modules.evaluation import EVALUATION_MAX_MODEL_CALLS_DEFAULT, run_evaluation_demo
from abi.packets import PacketWriter, create_packet_dir, read_json_file


FINAL_ARTIFACT_LINEAGE_ID = "phase13_final_artifact_and_paper_packet"
FINAL_ARTIFACT_CLIENT_FAKE = "fake"
FINAL_ARTIFACT_CLIENT_OPENAI = "openai"
FINAL_ARTIFACT_CLIENTS = (FINAL_ARTIFACT_CLIENT_FAKE, FINAL_ARTIFACT_CLIENT_OPENAI)
FINAL_ARTIFACT_MAX_MODEL_CALLS_DEFAULT = 8
FINAL_ARTIFACT_REQUIRED_MODEL_CALLS = 0
FINAL_ARTIFACT_FAKE_MODEL = "fake-final-artifact-paper-packet-v1"
FINAL_ARTIFACT_ARTIFACT_TYPES = (
    "final_artifact_source_refs",
    "final_artifact_candidate_text",
    "final_artifact_lineage_summary",
    "hidden_consequence_report",
    "reader_effect_claim_map",
    "final_artifact_risk_register",
    "hostile_final_audit_scaffold",
    "paper_outline",
    "paper_evidence_map",
    "finalization_readiness_report",
    "final_artifact_packet",
)


@dataclass(frozen=True)
class FinalArtifactPacketResult:
    exit_code: int
    payload: dict[str, object]


@dataclass(frozen=True)
class FinalArtifactSubject:
    run_id: str
    production_packet_artifact: ArtifactRecord
    production_packet_payload: dict[str, object]
    candidate_artifact: ArtifactRecord
    candidate_payload: dict[str, object]
    evaluation_packet_artifact: ArtifactRecord
    evaluation_packet_payload: dict[str, object]


def run_final_artifact_packet(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool = False,
    max_model_calls: int = FINAL_ARTIFACT_MAX_MODEL_CALLS_DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
) -> FinalArtifactPacketResult:
    if client_name not in FINAL_ARTIFACT_CLIENTS:
        return _refusal(
            client_name=client_name,
            model=model,
            message=f"Final-artifact packet client is not available: {client_name}",
        )

    configured_model = model or os.environ.get(ABI_OPENAI_MODEL_ENV, LIVE_MODEL_DEFAULT)
    if max_model_calls < FINAL_ARTIFACT_REQUIRED_MODEL_CALLS:
        return _refusal(
            client_name=client_name,
            model=configured_model if client_name == FINAL_ARTIFACT_CLIENT_OPENAI else None,
            message=(
                "Final-artifact packet refused; max-model-calls "
                f"{max_model_calls} is below required budget "
                f"{FINAL_ARTIFACT_REQUIRED_MODEL_CALLS}."
            ),
        )

    if client_name == FINAL_ARTIFACT_CLIENT_OPENAI and not allow_live_model:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=(
                "Final-artifact packet refused; pass --allow-live-model "
                "to opt in explicitly."
            ),
        )

    resolved_api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if client_name == FINAL_ARTIFACT_CLIENT_OPENAI and not resolved_api_key:
        return _refusal(
            client_name=client_name,
            model=configured_model,
            message=f"Final-artifact packet refused; {OPENAI_API_KEY_ENV} is not set.",
        )

    subject_result = _load_or_create_subject(config)
    if isinstance(subject_result, FinalArtifactPacketResult):
        return subject_result
    subject = subject_result
    packet_dir = create_packet_dir(config.run_dir(subject.run_id) / "final_artifact")
    model_name = (
        configured_model if client_name == FINAL_ARTIFACT_CLIENT_OPENAI else FINAL_ARTIFACT_FAKE_MODEL
    )

    return _write_final_artifact_packet(
        config=config,
        subject=subject,
        packet_dir=packet_dir,
        client_name=client_name,
        model=model_name,
        max_model_calls=max_model_calls,
        fixture_only=client_name == FINAL_ARTIFACT_CLIENT_FAKE,
    )


def _load_or_create_subject(config: AbiConfig) -> FinalArtifactSubject | FinalArtifactPacketResult:
    subject = _load_latest_subject(config)
    if subject is not None:
        return subject

    evaluation_result = run_evaluation_demo(
        config,
        client_name="fake",
        max_model_calls=EVALUATION_MAX_MODEL_CALLS_DEFAULT,
    )
    if evaluation_result.exit_code != 0:
        return _refusal(
            client_name=FINAL_ARTIFACT_CLIENT_FAKE,
            model=FINAL_ARTIFACT_FAKE_MODEL,
            message=(
                "Final-artifact packet refused; unable to create fake evaluation "
                f"dependency: {evaluation_result.payload.get('message')}"
            ),
        )
    subject = _load_latest_subject(config)
    if subject is None:
        return _refusal(
            client_name=FINAL_ARTIFACT_CLIENT_FAKE,
            model=FINAL_ARTIFACT_FAKE_MODEL,
            message="Final-artifact packet refused; no evaluation packet was registered.",
        )
    return subject


def _load_latest_subject(config: AbiConfig) -> FinalArtifactSubject | None:
    if not config.db_path.exists():
        return None
    initialize_database(config)
    with connect(config.db_path) as connection:
        evaluation_packets = [
            artifact
            for artifact in list_all_artifacts(connection)
            if artifact.type == "evaluation_packet"
        ]
        if not evaluation_packets:
            return None
        evaluation_packet_artifact = evaluation_packets[-1]
        evaluation_packet_payload = read_json_file(evaluation_packet_artifact.path)["payload"]

        production_packet_id = evaluation_packet_payload["production_packet_artifact_id"]
        candidate_id = evaluation_packet_payload["candidate_artifact_id"]
        production_packet_artifact = get_artifact(connection, production_packet_id)
        candidate_artifact = get_artifact(connection, candidate_id)
        if production_packet_artifact is None:
            raise RuntimeError(f"Production packet not found: {production_packet_id}")
        if candidate_artifact is None:
            raise RuntimeError(f"Production candidate artifact not found: {candidate_id}")

    return FinalArtifactSubject(
        run_id=evaluation_packet_artifact.run_id,
        production_packet_artifact=production_packet_artifact,
        production_packet_payload=read_json_file(production_packet_artifact.path)["payload"],
        candidate_artifact=candidate_artifact,
        candidate_payload=read_json_file(candidate_artifact.path)["payload"],
        evaluation_packet_artifact=evaluation_packet_artifact,
        evaluation_packet_payload=evaluation_packet_payload,
    )


def _write_final_artifact_packet(
    *,
    config: AbiConfig,
    subject: FinalArtifactSubject,
    packet_dir: Path,
    client_name: str,
    model: str,
    max_model_calls: int,
    fixture_only: bool,
) -> FinalArtifactPacketResult:
    artifacts: dict[str, ArtifactRecord] = {}
    payloads: dict[str, dict[str, object]] = {}

    with connect(config.db_path) as connection:
        set_active_phase(connection, subject.run_id, PHASE13_FINAL_ARTIFACT_PACKET_ACTIVE_PHASE)
        writer = PacketWriter(
            connection=connection,
            run_id=subject.run_id,
            packet_dir=packet_dir,
            lineage_id=FINAL_ARTIFACT_LINEAGE_ID,
            created_by="final_artifact_paper_packet_scaffold",
            fixture_only=fixture_only,
            model_call_id=None,
        )

        payloads["final_artifact_source_refs"] = _build_source_refs_payload(subject)
        artifacts["final_artifact_source_refs"] = writer.write_artifact(
            "final_artifact_source_refs",
            payloads["final_artifact_source_refs"],
            parent_ids=[
                subject.production_packet_artifact.id,
                subject.evaluation_packet_artifact.id,
            ],
        )

        payloads["final_artifact_candidate_text"] = _build_candidate_text_payload(subject)
        artifacts["final_artifact_candidate_text"] = writer.write_artifact(
            "final_artifact_candidate_text",
            payloads["final_artifact_candidate_text"],
            parent_ids=[
                subject.candidate_artifact.id,
                artifacts["final_artifact_source_refs"].id,
            ],
        )

        payloads["final_artifact_lineage_summary"] = _build_lineage_summary_payload(subject)
        artifacts["final_artifact_lineage_summary"] = writer.write_artifact(
            "final_artifact_lineage_summary",
            payloads["final_artifact_lineage_summary"],
            parent_ids=[
                subject.production_packet_artifact.id,
                subject.evaluation_packet_artifact.id,
                artifacts["final_artifact_candidate_text"].id,
            ],
        )

        payloads["hidden_consequence_report"] = _build_hidden_consequence_payload(subject)
        artifacts["hidden_consequence_report"] = writer.write_artifact(
            "hidden_consequence_report",
            payloads["hidden_consequence_report"],
            parent_ids=[
                artifacts["final_artifact_candidate_text"].id,
                artifacts["final_artifact_lineage_summary"].id,
            ],
        )

        payloads["reader_effect_claim_map"] = _build_reader_effect_claim_map_payload(subject)
        artifacts["reader_effect_claim_map"] = writer.write_artifact(
            "reader_effect_claim_map",
            payloads["reader_effect_claim_map"],
            parent_ids=[
                subject.evaluation_packet_artifact.id,
                artifacts["hidden_consequence_report"].id,
            ],
        )

        payloads["final_artifact_risk_register"] = _build_risk_register_payload(subject)
        artifacts["final_artifact_risk_register"] = writer.write_artifact(
            "final_artifact_risk_register",
            payloads["final_artifact_risk_register"],
            parent_ids=[
                artifacts["reader_effect_claim_map"].id,
                artifacts["hidden_consequence_report"].id,
            ],
        )

        payloads["hostile_final_audit_scaffold"] = _build_hostile_audit_payload(subject)
        artifacts["hostile_final_audit_scaffold"] = writer.write_artifact(
            "hostile_final_audit_scaffold",
            payloads["hostile_final_audit_scaffold"],
            parent_ids=[
                artifacts["final_artifact_risk_register"].id,
                artifacts["reader_effect_claim_map"].id,
            ],
        )

        payloads["paper_outline"] = _build_paper_outline_payload(subject)
        artifacts["paper_outline"] = writer.write_artifact(
            "paper_outline",
            payloads["paper_outline"],
            parent_ids=[
                artifacts["final_artifact_source_refs"].id,
                artifacts["final_artifact_risk_register"].id,
            ],
        )

        payloads["paper_evidence_map"] = _build_paper_evidence_map_payload(subject)
        artifacts["paper_evidence_map"] = writer.write_artifact(
            "paper_evidence_map",
            payloads["paper_evidence_map"],
            parent_ids=[
                artifacts["paper_outline"].id,
                artifacts["final_artifact_lineage_summary"].id,
                subject.evaluation_packet_artifact.id,
            ],
        )

        readiness = evaluate_release_readiness(
            connection,
            run_id=subject.run_id,
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )
        payloads["finalization_readiness_report"] = _build_readiness_payload(
            readiness=readiness,
        )
        artifacts["finalization_readiness_report"] = writer.write_artifact(
            "finalization_readiness_report",
            payloads["finalization_readiness_report"],
            parent_ids=[
                artifacts["hostile_final_audit_scaffold"].id,
                artifacts["paper_evidence_map"].id,
                subject.evaluation_packet_artifact.id,
            ],
        )

        payloads["final_artifact_packet"] = _build_packet_summary_payload(
            client_name=client_name,
            model=model,
            max_model_calls=max_model_calls,
            packet_dir=packet_dir,
            artifacts=artifacts,
            payloads=payloads,
            subject=subject,
        )
        artifacts["final_artifact_packet"] = writer.write_artifact(
            "final_artifact_packet",
            payloads["final_artifact_packet"],
            parent_ids=[
                artifacts[artifact_type].id
                for artifact_type in FINAL_ARTIFACT_ARTIFACT_TYPES[:-1]
            ],
        )

    with connect(config.db_path) as connection:
        readiness_after_packet = evaluate_release_readiness(
            connection,
            run_id=subject.run_id,
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    return FinalArtifactPacketResult(
        exit_code=0,
        payload=_summary_payload(
            client_name=client_name,
            model=model,
            run_id=subject.run_id,
            packet_dir=str(packet_dir),
            artifacts=artifacts,
            payloads=payloads,
            readiness_after_packet=readiness_after_packet.to_dict(),
            max_model_calls=max_model_calls,
            refused=False,
            accepted=True,
            message=None,
        ),
    )


def _build_source_refs_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    production = subject.production_packet_payload
    evaluation = subject.evaluation_packet_payload
    return {
        "worker": "final_artifact_source_refs_v1",
        "production_packet_artifact_id": subject.production_packet_artifact.id,
        "evaluation_packet_artifact_id": subject.evaluation_packet_artifact.id,
        "source_manifest_artifact_id": production.get("source_manifest_artifact_id"),
        "harness_packet_reference_artifact_id": production.get(
            "harness_packet_reference_artifact_id"
        ),
        "candidate_artifact_id": subject.candidate_artifact.id,
        "evaluation_artifact_ids": evaluation.get("artifact_ids", {}),
        "fixture_or_scaffold_evidence_present": True,
    }


def _build_candidate_text_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    candidate = subject.candidate_payload
    return {
        "worker": "final_artifact_candidate_text_v1",
        "candidate_artifact_id": subject.candidate_artifact.id,
        "candidate_id": candidate["candidate_id"],
        "text": candidate["text"],
        "non_final": True,
        "candidate_only": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "human_validated": False,
        "human_validation_claim": False,
        "no_real_human_validation_claim": True,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "fixture_or_scaffold_evidence_present": True,
        "source_candidate_flags": _candidate_flags(candidate),
    }


def _build_lineage_summary_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    production = subject.production_packet_payload
    evaluation = subject.evaluation_packet_payload
    return {
        "worker": "final_artifact_lineage_summarizer_v1",
        "lineage_id": FINAL_ARTIFACT_LINEAGE_ID,
        "production_lineage_id": production.get("lineage_id"),
        "evaluation_lineage_id": evaluation.get("lineage_id"),
        "upstream_packet_refs": production.get("upstream_packet_refs", {}),
        "production_gate_summary": production.get("gate_summary", {}),
        "evaluation_gate_summary": evaluation.get("gate_summary", {}),
        "model_call_ids": {
            "production_upstream": production.get("counts", {}).get("upstream_model_calls"),
            "evaluation": evaluation.get("model_call_ids", []),
        },
        "lineage_limit": (
            "This is a packet scaffold over a non-final candidate; it is not a "
            "final artifact lineage proof."
        ),
    }


def _build_hidden_consequence_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    text = subject.candidate_payload["text"]
    return {
        "worker": "hidden_consequence_report_scaffold_v1",
        "candidate_id": subject.candidate_payload["candidate_id"],
        "candidate_text_excerpt": text[:240],
        "hidden_consequences": [
            {
                "id": "hc_001",
                "description": "The object remaining visible makes absence legible by contrast.",
                "evidence_status": "scaffold inference from reread packet",
            },
            {
                "id": "hc_002",
                "description": "Morning acts as a test boundary rather than scenery.",
                "evidence_status": "scaffold inference from candidate text",
            },
            {
                "id": "hc_003",
                "description": "The sentence withholds cause so later evidence can reload it.",
                "evidence_status": "requires stronger external validation later",
            },
        ],
        "not_human_validated": True,
        "no_phase_shift_claim": True,
        "claims_not_made": [
            "no final artifact claim",
            "no phase-shift claim",
            "no real human validation claim",
        ],
    }


def _build_reader_effect_claim_map_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    evaluation = subject.evaluation_packet_payload
    return {
        "worker": "reader_effect_claim_map_scaffold_v1",
        "candidate_id": subject.candidate_payload["candidate_id"],
        "mapped_claims": [
            {
                "claim_id": "reader_effect_001",
                "claim": "Opening reread pressure is hypothesized.",
                "status": "hypothesis_only",
                "evidence": "fixture evaluation packet",
            },
            {
                "claim_id": "reader_effect_002",
                "claim": "Candidate may preserve more delay than direct baseline.",
                "status": "fixture_comparison_only",
                "evidence": "evaluation baseline scaffold",
            },
        ],
        "evaluation_human_trace": evaluation.get("human_trace", {}),
        "baseline_flags": evaluation.get("baseline_flags", {}),
        "not_human_validated": True,
        "no_real_human_validation_claim": True,
        "no_phase_shift_claim": True,
    }


def _build_risk_register_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    evaluation = subject.evaluation_packet_payload
    return {
        "worker": "final_artifact_risk_register_v1",
        "candidate_id": subject.candidate_payload["candidate_id"],
        "risks": [
            {
                "risk_id": "risk_fixture_evidence",
                "severity": "blocking",
                "description": "Evaluation evidence is fixture/scaffold evidence.",
            },
            {
                "risk_id": "risk_no_real_human_validation",
                "severity": "blocking",
                "description": "No real human validation gate has passed.",
            },
            {
                "risk_id": "risk_no_strongest_rival",
                "severity": "blocking",
                "description": "No strongest-rival comparison gate has passed.",
            },
            {
                "risk_id": "risk_no_raw_model_baseline",
                "severity": "blocking",
                "description": "No raw-model baseline comparison gate has passed.",
            },
            {
                "risk_id": "risk_candidate_non_final",
                "severity": "blocking",
                "description": "Candidate remains marked non-final and not finalization eligible.",
            },
        ],
        "evaluation_gate_summary": evaluation.get("gate_summary", {}),
        "no_phase_shift_claim": True,
        "not_finalization_eligible": True,
    }


def _build_hostile_audit_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    return {
        "worker": "hostile_final_audit_scaffold_v1",
        "audit_status": "scaffold_only",
        "would_test_gate": "hostile_final_audit_passed",
        "passed": False,
        "final_gate_marked_passed": False,
        "candidate_id": subject.candidate_payload["candidate_id"],
        "blocking_findings": [
            "candidate is non-final",
            "fixture-only evidence cannot support final claims",
            "real human validation is absent",
            "strongest-rival and raw-model baseline gates are absent",
            "operator approval is absent",
        ],
        "claims_not_made": [
            "no hostile final audit passed claim",
            "no final approval claim",
            "no phase-shift claim",
        ],
    }


def _build_paper_outline_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    return {
        "worker": "paper_outline_scaffold_v1",
        "paper_status": "outline_only",
        "project_thesis": (
            "Abi is structured to make reader-state evidence first-class before "
            "any final artifact claim."
        ),
        "sections": [
            "Problem and architecture",
            "Artifact lineage and candidate packet",
            "Evaluation and baseline scaffold",
            "Reader-effect evidence required before claims",
            "Finalization gates and current blockers",
        ],
        "candidate_id": subject.candidate_payload["candidate_id"],
        "claims_not_yet_made": [
            "phase-shift claim",
            "real human validation claim",
            "final artifact claim",
            "baseline victory claim",
        ],
        "next_required_validation_steps": [
            "real human validation",
            "strongest-rival comparison",
            "raw-model baseline comparison",
            "hostile final audit",
            "final operator approval",
        ],
    }


def _build_paper_evidence_map_payload(subject: FinalArtifactSubject) -> dict[str, object]:
    evaluation = subject.evaluation_packet_payload
    return {
        "worker": "paper_evidence_map_scaffold_v1",
        "evidence_status": "scaffold_only",
        "candidate_artifact_id": subject.candidate_artifact.id,
        "production_packet_artifact_id": subject.production_packet_artifact.id,
        "evaluation_packet_artifact_id": subject.evaluation_packet_artifact.id,
        "evidence_rows": [
            {
                "claim_area": "lineage",
                "artifact_id": subject.production_packet_artifact.id,
                "status": "registered scaffold evidence",
            },
            {
                "claim_area": "reader trace",
                "artifact_id": evaluation.get("artifact_ids", {}).get(
                    "evaluation_human_trace_import"
                ),
                "status": "fixture only, not real validation",
            },
            {
                "claim_area": "baseline comparison",
                "artifact_id": evaluation.get("artifact_ids", {}).get(
                    "evaluation_baseline_comparison_report"
                ),
                "status": "fixture/fake scaffold",
            },
        ],
        "fixture_or_scaffold_evidence_present": True,
        "not_real_validation": True,
    }


def _build_readiness_payload(*, readiness) -> dict[str, object]:
    readiness_payload = readiness.to_dict()
    return {
        "worker": "finalization_readiness_report_v1",
        "profile": GATE_PROFILE_FINAL_ARTIFACT,
        "eligible": False,
        "current_run_ineligible": True,
        "final_artifact_profile_refuses": True,
        "release_readiness": readiness_payload,
        "missing_gates": readiness_payload["missing_gates"],
        "fixture_only_blockers": readiness_payload["fixture_only_blockers"],
        "non_final_blockers": readiness_payload["non_final_blockers"],
        "artifact_blockers": readiness_payload["artifact_blockers"],
        "recommended_next_action": readiness_payload["recommended_next_action"],
        "final_gates_marked_passed": [],
        "claims_not_made": [
            "no finalization claim",
            "no phase-shift claim",
            "no real human validation claim",
        ],
    }


def _build_packet_summary_payload(
    *,
    client_name: str,
    model: str,
    max_model_calls: int,
    packet_dir: Path,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    subject: FinalArtifactSubject,
) -> dict[str, object]:
    candidate = payloads["final_artifact_candidate_text"]
    return {
        "worker": "final_artifact_packet_summarizer_v1",
        "run_id": subject.run_id,
        "packet_id": packet_dir.name,
        "client": client_name,
        "model": model,
        "max_model_calls": max_model_calls,
        "model_calls_used": 0,
        "artifact_types": list(FINAL_ARTIFACT_ARTIFACT_TYPES),
        "artifact_ids": {artifact_type: artifact.id for artifact_type, artifact in artifacts.items()},
        "source_refs_artifact_id": artifacts["final_artifact_source_refs"].id,
        "candidate_text_artifact_id": artifacts["final_artifact_candidate_text"].id,
        "lineage_summary_artifact_id": artifacts["final_artifact_lineage_summary"].id,
        "hidden_consequence_report_artifact_id": artifacts["hidden_consequence_report"].id,
        "reader_effect_claim_map_artifact_id": artifacts["reader_effect_claim_map"].id,
        "risk_register_artifact_id": artifacts["final_artifact_risk_register"].id,
        "hostile_final_audit_scaffold_artifact_id": artifacts[
            "hostile_final_audit_scaffold"
        ].id,
        "paper_outline_artifact_id": artifacts["paper_outline"].id,
        "paper_evidence_map_artifact_id": artifacts["paper_evidence_map"].id,
        "finalization_readiness_report_artifact_id": artifacts[
            "finalization_readiness_report"
        ].id,
        "non_final": True,
        "candidate_only": True,
        "not_human_validated": True,
        "not_finalization_eligible": True,
        "finalization_eligible": False,
        "human_validation_claim": False,
        "no_real_human_validation_claim": True,
        "phase_shift_claim": False,
        "no_phase_shift_claim": True,
        "fixture_or_scaffold_evidence_present": True,
        "candidate_flags": _candidate_flags(candidate),
        "finalization_readiness": {
            "eligible": payloads["finalization_readiness_report"]["eligible"],
            "profile": GATE_PROFILE_FINAL_ARTIFACT,
            "current_run_ineligible": True,
        },
    }


def _summary_payload(
    *,
    client_name: str,
    model: str | None,
    run_id: str | None,
    packet_dir: str | None,
    artifacts: dict[str, ArtifactRecord],
    payloads: dict[str, dict[str, object]],
    readiness_after_packet: dict[str, object] | None,
    max_model_calls: int,
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
        "required_artifact_types": list(FINAL_ARTIFACT_ARTIFACT_TYPES),
        "artifact_ids": {
            artifact_type: artifact.id for artifact_type, artifact in artifacts.items()
        },
        "artifact_paths": {
            artifact_type: artifact.path for artifact_type, artifact in artifacts.items()
        },
        "counts": {
            "final_artifact_artifacts": len(payloads),
            "required_final_artifact_artifacts": len(FINAL_ARTIFACT_ARTIFACT_TYPES),
            "model_calls": 0,
            "max_model_calls": max_model_calls,
        },
        "candidate_flags": _candidate_flags(payloads["final_artifact_candidate_text"])
        if "final_artifact_candidate_text" in payloads
        else {},
        "finalization_readiness": readiness_after_packet,
        "message": message,
    }


def _candidate_flags(candidate_payload: dict[str, object]) -> dict[str, object]:
    return {
        "non_final": candidate_payload["non_final"],
        "candidate_only": candidate_payload.get("candidate_only", True),
        "not_human_validated": candidate_payload["not_human_validated"],
        "not_finalization_eligible": candidate_payload["not_finalization_eligible"],
        "finalization_eligible": candidate_payload["finalization_eligible"],
        "human_validated": candidate_payload.get("human_validated", False),
        "human_validation_claim": candidate_payload["human_validation_claim"],
        "phase_shift_claim": candidate_payload["phase_shift_claim"],
        "no_phase_shift_claim": candidate_payload.get("no_phase_shift_claim", True),
    }


def _refusal(*, client_name: str, model: str | None, message: str) -> FinalArtifactPacketResult:
    return FinalArtifactPacketResult(
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
