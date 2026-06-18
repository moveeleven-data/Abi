"""Gate policies for fail-closed controller decisions."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from abi.controller.gates import REQUIRED_PHASE0_GATES, GateRecord, required_gate_records


@dataclass(frozen=True)
class GatePolicy:
    name: str
    required_gates: tuple[str, ...]
    lineage_id: str | None = None


@dataclass(frozen=True)
class GateCatalogEntry:
    name: str
    purpose: str
    required_profiles: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "required_profiles": list(self.required_profiles),
        }


@dataclass(frozen=True)
class GatePolicyEvaluation:
    policy: GatePolicy
    run_id: str
    gate_records: dict[str, GateRecord | None]
    missing_gates: list[str]
    failed_gates: list[str]
    blocking_defects: dict[str, list[str]]

    @property
    def eligible(self) -> bool:
        return not self.missing_gates and not self.failed_gates and not self.blocking_defects

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": {
                "name": self.policy.name,
                "required_gates": list(self.policy.required_gates),
                "lineage_id": self.policy.lineage_id,
            },
            "run_id": self.run_id,
            "missing_gates": self.missing_gates,
            "failed_gates": self.failed_gates,
            "blocking_defects": self.blocking_defects,
            "eligible": self.eligible,
        }


GATE_PROFILE_INFRASTRUCTURE = "infrastructure"
GATE_PROFILE_CANDIDATE_RELEASE = "candidate_release"
GATE_PROFILE_FINAL_ARTIFACT = "final_artifact"

CANDIDATE_RELEASE_REQUIRED_GATES = (
    "source_to_artifact_production_run_v1",
    "evaluation_baselines_v1",
)

FINAL_ARTIFACT_REQUIRED_GATES = (
    "final_artifact_packet_exists",
    "final_artifact_not_fixture",
    "final_artifact_not_marked_non_final",
    "real_human_validation_passed",
    "strongest_rival_comparison_passed",
    "raw_model_baseline_comparison_passed",
    "hostile_final_audit_passed",
    "no_fixture_only_evidence_used_as_final_claim",
    "no_unresolved_blocking_defects",
    "final_operator_approval",
)

GATE_PROFILES: dict[str, GatePolicy] = {
    GATE_PROFILE_INFRASTRUCTURE: GatePolicy(
        name=GATE_PROFILE_INFRASTRUCTURE,
        required_gates=REQUIRED_PHASE0_GATES,
    ),
    GATE_PROFILE_CANDIDATE_RELEASE: GatePolicy(
        name=GATE_PROFILE_CANDIDATE_RELEASE,
        required_gates=CANDIDATE_RELEASE_REQUIRED_GATES,
    ),
    GATE_PROFILE_FINAL_ARTIFACT: GatePolicy(
        name=GATE_PROFILE_FINAL_ARTIFACT,
        required_gates=FINAL_ARTIFACT_REQUIRED_GATES,
    ),
}

DEFAULT_FINALIZATION_POLICY = GATE_PROFILES[GATE_PROFILE_INFRASTRUCTURE]
DEFAULT_FINALIZATION_PROFILE = GATE_PROFILE_INFRASTRUCTURE

GATE_CATALOG: tuple[GateCatalogEntry, ...] = (
    GateCatalogEntry(
        name="infrastructure_initialized",
        purpose="Phase 0 infrastructure was initialized for the run.",
        required_profiles=(GATE_PROFILE_INFRASTRUCTURE,),
    ),
    GateCatalogEntry(
        name="artifact_registry_ready",
        purpose="Immutable artifact registration is available for the run.",
        required_profiles=(GATE_PROFILE_INFRASTRUCTURE,),
    ),
    GateCatalogEntry(
        name="required_phase0_tests_passed",
        purpose="Required Phase 0 regression tests passed for the run.",
        required_profiles=(GATE_PROFILE_INFRASTRUCTURE,),
    ),
    GateCatalogEntry(
        name="source_to_artifact_production_run_v1",
        purpose="Controlled source-to-artifact candidate packet scaffold passed.",
        required_profiles=(GATE_PROFILE_CANDIDATE_RELEASE,),
    ),
    GateCatalogEntry(
        name="evaluation_baselines_v1",
        purpose="Evaluation and baseline scaffold packet passed.",
        required_profiles=(GATE_PROFILE_CANDIDATE_RELEASE,),
    ),
    GateCatalogEntry(
        name="final_artifact_packet_exists",
        purpose="A final artifact packet is registered for the run.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="final_artifact_not_fixture",
        purpose="The final artifact packet is not fixture-only evidence.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="final_artifact_not_marked_non_final",
        purpose="The final artifact is not marked candidate-only or non-final.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="real_human_validation_passed",
        purpose="Real human validation passed without relying on fixture traces.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="strongest_rival_comparison_passed",
        purpose="The final artifact passed strongest-rival comparison.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="raw_model_baseline_comparison_passed",
        purpose="The final artifact passed raw-model baseline comparison.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="hostile_final_audit_passed",
        purpose="A hostile final audit found no blocking defects.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="no_fixture_only_evidence_used_as_final_claim",
        purpose="No fixture-only evidence is used as a final validation claim.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="no_unresolved_blocking_defects",
        purpose="No unresolved blocking defects remain for finalization.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
    GateCatalogEntry(
        name="final_operator_approval",
        purpose="The final operator explicitly approved release.",
        required_profiles=(GATE_PROFILE_FINAL_ARTIFACT,),
    ),
)

GATE_PROFILE_NAMES = tuple(GATE_PROFILES)


def get_gate_policy(profile: str) -> GatePolicy:
    try:
        return GATE_PROFILES[profile]
    except KeyError as error:
        valid = ", ".join(GATE_PROFILE_NAMES)
        raise ValueError(f"Unknown gate profile {profile!r}; expected one of: {valid}") from error


def gate_catalog_to_dict() -> dict[str, object]:
    return {
        "profiles": {
            profile_name: {
                "name": profile.name,
                "required_gates": list(profile.required_gates),
                "lineage_id": profile.lineage_id,
            }
            for profile_name, profile in GATE_PROFILES.items()
        },
        "gates": [entry.to_dict() for entry in GATE_CATALOG],
    }


def evaluate_gate_policy(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    policy: GatePolicy = DEFAULT_FINALIZATION_POLICY,
) -> GatePolicyEvaluation:
    gate_records = required_gate_records(
        connection,
        run_id=run_id,
        required_gates=policy.required_gates,
        lineage_id=policy.lineage_id,
    )
    missing_gates = [gate_name for gate_name, gate in gate_records.items() if gate is None]
    failed_gates = [
        gate_name
        for gate_name, gate in gate_records.items()
        if gate is not None and not gate.passed
    ]
    blocking_defects = {
        gate_name: list(gate.blocking_defects)
        for gate_name, gate in gate_records.items()
        if gate is not None and gate.blocking_defects
    }
    return GatePolicyEvaluation(
        policy=policy,
        run_id=run_id,
        gate_records=gate_records,
        missing_gates=missing_gates,
        failed_gates=failed_gates,
        blocking_defects=blocking_defects,
    )
