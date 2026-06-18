"""Structured fail-closed controller decisions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlockerReport:
    run_id: str
    active_phase: str
    status: str
    blockers: list[str]
    missing_gates: list[str]
    failed_gates: list[str]
    blocking_defects: dict[str, list[str]]
    recommended_next_action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "active_phase": self.active_phase,
            "status": self.status,
            "blockers": self.blockers,
            "missing_gates": self.missing_gates,
            "failed_gates": self.failed_gates,
            "blocking_defects": self.blocking_defects,
            "recommended_next_action": self.recommended_next_action,
        }


@dataclass(frozen=True)
class ControllerDecision:
    run_id: str
    decision: str
    active_phase: str
    status: str
    eligible_to_finalize: bool
    missing_gates: list[str]
    failed_gates: list[str]
    blocking_defects: dict[str, list[str]]
    recommended_next_action: str
    message: str
    blocker_report: BlockerReport

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "decision": self.decision,
            "active_phase": self.active_phase,
            "status": self.status,
            "eligible_to_finalize": self.eligible_to_finalize,
            "missing_gates": self.missing_gates,
            "failed_gates": self.failed_gates,
            "blocking_defects": self.blocking_defects,
            "recommended_next_action": self.recommended_next_action,
            "message": self.message,
            "blocker_report": self.blocker_report.to_dict(),
        }
