"""Profile-aware release readiness reports for Phase 12 finalization policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from abi.artifacts import ArtifactRecord, list_artifacts
from abi.controller.gates import list_gates
from abi.controller.policy import (
    GATE_PROFILE_CANDIDATE_RELEASE,
    GATE_PROFILE_FINAL_ARTIFACT,
    evaluate_gate_policy,
    get_gate_policy,
)
from abi.packets import read_json_file


@dataclass(frozen=True)
class ReleaseReadinessReport:
    run_id: str
    profile: str
    eligible: bool
    missing_gates: list[str]
    failed_gates: list[str]
    blocking_defects: dict[str, list[str]]
    fixture_only_blockers: list[str]
    non_final_blockers: list[str]
    recommended_next_action: str
    artifact_blockers: list[str]
    blockers: list[str]
    required_gates: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "profile": self.profile,
            "eligible": self.eligible,
            "missing_gates": self.missing_gates,
            "failed_gates": self.failed_gates,
            "blocking_defects": self.blocking_defects,
            "fixture_only_blockers": self.fixture_only_blockers,
            "non_final_blockers": self.non_final_blockers,
            "artifact_blockers": self.artifact_blockers,
            "blockers": self.blockers,
            "required_gates": self.required_gates,
            "recommended_next_action": self.recommended_next_action,
        }


def evaluate_release_readiness(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    profile: str,
) -> ReleaseReadinessReport:
    policy = get_gate_policy(profile)
    gate_evaluation = evaluate_gate_policy(connection, run_id=run_id, policy=policy)
    artifacts_by_type = _artifacts_by_type(list_artifacts(connection, run_id))

    blocking_defects = {
        gate_name: list(defects)
        for gate_name, defects in gate_evaluation.blocking_defects.items()
    }
    artifact_blockers: list[str] = []
    fixture_only_blockers: list[str] = []
    non_final_blockers: list[str] = []

    if profile == GATE_PROFILE_CANDIDATE_RELEASE:
        _add_candidate_release_artifact_checks(
            artifacts_by_type=artifacts_by_type,
            artifact_blockers=artifact_blockers,
            non_final_blockers=non_final_blockers,
        )
    elif profile == GATE_PROFILE_FINAL_ARTIFACT:
        _add_final_artifact_checks(
            artifacts_by_type=artifacts_by_type,
            artifact_blockers=artifact_blockers,
            fixture_only_blockers=fixture_only_blockers,
            non_final_blockers=non_final_blockers,
        )
        _add_unresolved_gate_defects(
            connection=connection,
            run_id=run_id,
            blocking_defects=blocking_defects,
        )

    blockers = _build_blockers(
        missing_gates=gate_evaluation.missing_gates,
        failed_gates=gate_evaluation.failed_gates,
        blocking_defects=blocking_defects,
        artifact_blockers=artifact_blockers,
        fixture_only_blockers=fixture_only_blockers,
        non_final_blockers=non_final_blockers,
    )
    eligible = not blockers

    return ReleaseReadinessReport(
        run_id=run_id,
        profile=profile,
        eligible=eligible,
        missing_gates=gate_evaluation.missing_gates,
        failed_gates=gate_evaluation.failed_gates,
        blocking_defects=blocking_defects,
        fixture_only_blockers=fixture_only_blockers,
        non_final_blockers=non_final_blockers,
        recommended_next_action=_recommended_next_action(profile, eligible),
        artifact_blockers=artifact_blockers,
        blockers=blockers,
        required_gates=list(policy.required_gates),
    )


def _add_candidate_release_artifact_checks(
    *,
    artifacts_by_type: dict[str, list[ArtifactRecord]],
    artifact_blockers: list[str],
    non_final_blockers: list[str],
) -> None:
    production_packet = _latest_artifact(artifacts_by_type, "production_packet")
    evaluation_packet = _latest_artifact(artifacts_by_type, "evaluation_packet")
    candidate = _latest_artifact(artifacts_by_type, "production_candidate_artifact")

    if production_packet is None:
        artifact_blockers.append("no production candidate packet is registered")
    if evaluation_packet is None:
        artifact_blockers.append("no evaluation packet is registered")
    if candidate is None:
        artifact_blockers.append("no production candidate artifact is registered")
        return

    payload = _payload_from_artifact(candidate)
    if not _truthy(payload, "non_final") or not _truthy(payload, "not_finalization_eligible"):
        non_final_blockers.append(
            f"candidate artifact {candidate.id} is not clearly marked non-final"
        )
    if bool(payload.get("finalization_eligible")):
        non_final_blockers.append(
            f"candidate artifact {candidate.id} is incorrectly marked finalization eligible"
        )


def _add_final_artifact_checks(
    *,
    artifacts_by_type: dict[str, list[ArtifactRecord]],
    artifact_blockers: list[str],
    fixture_only_blockers: list[str],
    non_final_blockers: list[str],
) -> None:
    final_packet = _latest_artifact(artifacts_by_type, "final_artifact_packet")
    if final_packet is None:
        artifact_blockers.append("no final artifact packet is registered")
        _add_non_final_candidate_blockers(
            artifacts_by_type=artifacts_by_type,
            non_final_blockers=non_final_blockers,
        )
    else:
        _add_final_packet_blockers(
            final_packet=final_packet,
            fixture_only_blockers=fixture_only_blockers,
            non_final_blockers=non_final_blockers,
        )

    _add_fixture_evidence_blockers(
        artifacts_by_type=artifacts_by_type,
        fixture_only_blockers=fixture_only_blockers,
    )


def _add_final_packet_blockers(
    *,
    final_packet: ArtifactRecord,
    fixture_only_blockers: list[str],
    non_final_blockers: list[str],
) -> None:
    envelope = _read_artifact(final_packet)
    payload = _payload_from_envelope(envelope)
    if bool(envelope.get("fixture_only")) or bool(payload.get("fixture_only")):
        fixture_only_blockers.append(
            f"final artifact packet {final_packet.id} is fixture-only"
        )
    if _artifact_payload_is_non_final(payload):
        non_final_blockers.append(
            f"final artifact packet {final_packet.id} is marked non-final or candidate-only"
        )


def _add_non_final_candidate_blockers(
    *,
    artifacts_by_type: dict[str, list[ArtifactRecord]],
    non_final_blockers: list[str],
) -> None:
    candidate = _latest_artifact(artifacts_by_type, "production_candidate_artifact")
    if candidate is not None:
        payload = _payload_from_artifact(candidate)
        if _artifact_payload_is_non_final(payload):
            non_final_blockers.append(
                f"candidate artifact {candidate.id} remains non-final and not finalization eligible"
            )

    evaluation_packet = _latest_artifact(artifacts_by_type, "evaluation_packet")
    if evaluation_packet is None:
        return
    payload = _payload_from_artifact(evaluation_packet)
    candidate_flags = payload.get("candidate_flags")
    if isinstance(candidate_flags, dict) and _artifact_payload_is_non_final(candidate_flags):
        non_final_blockers.append(
            f"evaluation packet {evaluation_packet.id} references a non-final candidate"
        )


def _add_fixture_evidence_blockers(
    *,
    artifacts_by_type: dict[str, list[ArtifactRecord]],
    fixture_only_blockers: list[str],
) -> None:
    evaluation_packet = _latest_artifact(artifacts_by_type, "evaluation_packet")
    if evaluation_packet is not None:
        envelope = _read_artifact(evaluation_packet)
        payload = _payload_from_envelope(envelope)
        if bool(envelope.get("fixture_only")) or bool(payload.get("fixture_only")):
            fixture_only_blockers.append(
                f"evaluation packet {evaluation_packet.id} is fixture-only"
            )
        human_trace = payload.get("human_trace")
        if isinstance(human_trace, dict) and bool(human_trace.get("fixture_only")):
            fixture_only_blockers.append(
                f"evaluation packet {evaluation_packet.id} uses fixture-only human trace evidence"
            )
        baseline_flags = payload.get("baseline_flags")
        if isinstance(baseline_flags, dict):
            _add_fixture_baseline_blockers(
                evaluation_packet=evaluation_packet,
                baseline_flags=baseline_flags,
                fixture_only_blockers=fixture_only_blockers,
            )

    human_trace_import = _latest_artifact(artifacts_by_type, "evaluation_human_trace_import")
    if human_trace_import is not None:
        payload = _payload_from_artifact(human_trace_import)
        if bool(payload.get("fixture_only")) or bool(payload.get("not_real_validation")):
            fixture_only_blockers.append(
                f"human trace import {human_trace_import.id} is fixture-only and not real validation"
            )


def _add_fixture_baseline_blockers(
    *,
    evaluation_packet: ArtifactRecord,
    baseline_flags: dict[str, Any],
    fixture_only_blockers: list[str],
) -> None:
    if bool(baseline_flags.get("direct_prompt_fixture_only")):
        fixture_only_blockers.append(
            f"evaluation packet {evaluation_packet.id} uses a fixture direct-prompt baseline"
        )
    if bool(baseline_flags.get("best_of_n_fixture_only")):
        fixture_only_blockers.append(
            f"evaluation packet {evaluation_packet.id} uses a fixture best-of-N baseline"
        )


def _add_unresolved_gate_defects(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    blocking_defects: dict[str, list[str]],
) -> None:
    unresolved = [
        f"{gate.gate_name}: {defect}"
        for gate in list_gates(connection, run_id)
        for defect in gate.blocking_defects
    ]
    if unresolved:
        blocking_defects.setdefault("no_unresolved_blocking_defects", []).extend(unresolved)


def _build_blockers(
    *,
    missing_gates: list[str],
    failed_gates: list[str],
    blocking_defects: dict[str, list[str]],
    artifact_blockers: list[str],
    fixture_only_blockers: list[str],
    non_final_blockers: list[str],
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(f"missing required gate: {gate_name}" for gate_name in missing_gates)
    blockers.extend(f"failed required gate: {gate_name}" for gate_name in failed_gates)
    blockers.extend(
        f"blocking defects on gate {gate_name}: {', '.join(defects)}"
        for gate_name, defects in blocking_defects.items()
    )
    blockers.extend(artifact_blockers)
    blockers.extend(fixture_only_blockers)
    blockers.extend(non_final_blockers)
    return blockers


def _recommended_next_action(profile: str, eligible: bool) -> str:
    if eligible and profile == GATE_PROFILE_FINAL_ARTIFACT:
        return "finalize"
    if eligible and profile == GATE_PROFILE_CANDIDATE_RELEASE:
        return "candidate release profile is ready; do not treat it as final artifact readiness"
    if eligible:
        return "profile gates are satisfied; this is diagnostic readiness only"
    if profile == GATE_PROFILE_FINAL_ARTIFACT:
        return "resolve final artifact gates, replace fixture evidence, and obtain final approval"
    if profile == GATE_PROFILE_CANDIDATE_RELEASE:
        return "create passing production and evaluation candidate packets"
    return "resolve required gate blockers"


def _artifacts_by_type(artifacts: list[ArtifactRecord]) -> dict[str, list[ArtifactRecord]]:
    by_type: dict[str, list[ArtifactRecord]] = {}
    for artifact in artifacts:
        by_type.setdefault(artifact.type, []).append(artifact)
    return by_type


def _latest_artifact(
    artifacts_by_type: dict[str, list[ArtifactRecord]],
    artifact_type: str,
) -> ArtifactRecord | None:
    artifacts = artifacts_by_type.get(artifact_type, [])
    if not artifacts:
        return None
    return artifacts[-1]


def _payload_from_artifact(artifact: ArtifactRecord) -> dict[str, Any]:
    return _payload_from_envelope(_read_artifact(artifact))


def _read_artifact(artifact: ArtifactRecord) -> dict[str, Any]:
    try:
        content = read_json_file(Path(artifact.path))
    except (OSError, ValueError):
        return {}
    return content if isinstance(content, dict) else {}


def _payload_from_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    payload = envelope.get("payload", envelope)
    return payload if isinstance(payload, dict) else {}


def _truthy(payload: dict[str, Any], key: str) -> bool:
    return bool(payload.get(key))


def _artifact_payload_is_non_final(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("non_final")
        or payload.get("candidate_only")
        or payload.get("not_finalization_eligible")
        or payload.get("finalization_eligible") is False
    )
