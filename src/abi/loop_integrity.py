"""Deterministic loop-integrity guards for supervised autonomous cycles."""

from __future__ import annotations

from typing import Any


REVIEW_OR_CLEANUP_ACTION_TOKENS = (
    "review",
    "cleanup",
    "clean_up",
    "loop_integrity",
    "prepare_loop_integrity",
)
READER_STATE_ACTION_TOKENS = ("reader_state", "reader-state")
STRATEGY_ACTION_TOKENS = ("strategy", "target")
ABLATION_ACTION_TOKENS = ("ablation", "ablate")
NEEDED_ACTION_TOKENS = ("needed", "need", "run", "complete", "prepare")


def detect_stale_recommendations(
    *,
    selected_candidate: dict[str, Any],
    synthesis_packet: dict[str, Any],
    source_chain: list[dict[str, Any]],
    proof_packet: dict[str, Any] | None = None,
    reader_state_packet: dict[str, Any] | None = None,
    strategy_packet: dict[str, Any] | None = None,
    loop_review_next_action: str | None = None,
) -> dict[str, object]:
    """Detect stale strategic recommendations without authorizing next work."""

    action_text = _action_text(synthesis_packet)
    selected_packet_id = str(selected_candidate.get("packet_id") or "")
    stale: list[dict[str, object]] = []
    reader_state_eval_needed = bool(
        synthesis_packet.get("object_event_reader_state_eval_needed")
        or (
            _mentions(action_text, READER_STATE_ACTION_TOKENS)
            and _mentions(action_text, ("eval", "evaluation", "needed"))
            and "review" not in action_text
        )
    )
    if reader_state_eval_needed and _reader_state_exists(selected_candidate, reader_state_packet):
        stale.append(
            {
                "stale_recommendation_type": "reader_state_eval_needed_but_packet_exists",
                "candidate_packet_id": selected_packet_id,
                "existing_packet_id": str((reader_state_packet or {}).get("packet_id") or ""),
                "recommendation": action_text,
            }
        )
    strategy_needed = _mentions(action_text, STRATEGY_ACTION_TOKENS) and _mentions(
        action_text,
        NEEDED_ACTION_TOKENS,
    )
    if strategy_needed and _strategy_already_consumed(
        selected_candidate=selected_candidate,
        source_chain=source_chain,
        strategy_packet=strategy_packet,
    ):
        stale.append(
            {
                "stale_recommendation_type": "strategy_needed_but_strategy_or_candidate_exists",
                "candidate_packet_id": selected_packet_id,
                "existing_strategy_packet_id": str((strategy_packet or {}).get("packet_id") or ""),
                "recommendation": action_text,
            }
        )
    ablation_needed = _mentions(action_text, ABLATION_ACTION_TOKENS) and _mentions(
        action_text,
        NEEDED_ACTION_TOKENS,
    )
    if ablation_needed and _proof_exists(
        selected_candidate,
        proof_packet,
    ):
        stale.append(
            {
                "stale_recommendation_type": "ablation_needed_but_proof_exists",
                "candidate_packet_id": selected_packet_id,
                "existing_packet_id": str((proof_packet or {}).get("packet_id") or ""),
                "recommendation": action_text,
            }
        )
    if loop_review_next_action:
        loop_action = loop_review_next_action.lower()
        if "generation" in loop_action and _mentions(
            action_text,
            REVIEW_OR_CLEANUP_ACTION_TOKENS,
        ):
            stale.append(
                {
                    "stale_recommendation_type": "loop_review_generation_conflicts_with_synthesis_cleanup",
                    "candidate_packet_id": selected_packet_id,
                    "recommendation": loop_review_next_action,
                    "synthesis_action": action_text,
                }
            )
    return {
        "stale_recommendation_detected": bool(stale),
        "stale_recommendations": stale,
        "stale_recommendation_count": len(stale),
    }


def build_proof_before_next_generation_guard(
    *,
    selected_candidate: dict[str, Any],
    proof_packet: dict[str, Any] | None,
    reader_state_packet: dict[str, Any] | None,
    latest_loop_review_requires_cleanup_first: bool,
    prior_generated_candidate_synthesized: bool,
    stale_recommendation_active: bool,
    operator_override_artifact_exists: bool = False,
) -> dict[str, object]:
    proof_current = bool(selected_candidate.get("proof_packet_id") and proof_packet)
    reader_current = bool(
        selected_candidate.get("reader_state_packet_id") and reader_state_packet
    )
    blockers: list[str] = []
    if not proof_current:
        blockers.append("current best candidate has no current proof packet")
    if not (reader_current or operator_override_artifact_exists):
        blockers.append(
            "current best candidate has no current reader-state packet or override artifact"
        )
    if latest_loop_review_requires_cleanup_first:
        blockers.append("latest loop review requires cleanup before generation")
    if not prior_generated_candidate_synthesized:
        blockers.append("prior generated candidate has not been synthesized")
    if stale_recommendation_active:
        blockers.append("stale recommendation is active")
    return {
        "next_generation_authorized": False,
        "proof_status_current": proof_current,
        "reader_state_status_current": reader_current,
        "operator_override_artifact_exists": operator_override_artifact_exists,
        "latest_loop_review_requires_cleanup_first": (
            latest_loop_review_requires_cleanup_first
        ),
        "prior_generated_candidate_synthesized": prior_generated_candidate_synthesized,
        "stale_recommendation_active": stale_recommendation_active,
        "next_generation_blockers": blockers,
    }


def build_reader_state_before_synthesis_guard(
    *,
    selected_candidate: dict[str, Any],
    available_reader_state_packet: dict[str, Any] | None,
    consumed_reader_state_packet_id: str | None,
) -> dict[str, object]:
    available_id = str((available_reader_state_packet or {}).get("packet_id") or "")
    consumed_id = str(consumed_reader_state_packet_id or "")
    warning_active = bool(available_id and available_id != consumed_id)
    return {
        "reader_state_before_synthesis_warning": warning_active,
        "selected_candidate_packet_id": selected_candidate.get("packet_id"),
        "available_reader_state_packet_id": available_id,
        "consumed_reader_state_packet_id": consumed_id,
        "strategic_decision_should_consume_available_reader_state": warning_active,
    }


def build_repeated_target_drift_guard(
    *,
    current_target_class: str | None,
    previous_target_class: str | None,
    evidence_shifted_to_target_class: str | None,
    loop_integrity_cleanup_required: bool,
) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    if (
        current_target_class
        and previous_target_class
        and current_target_class == previous_target_class
        and evidence_shifted_to_target_class
        and evidence_shifted_to_target_class != current_target_class
    ):
        findings.append(
            {
                "finding_id": "target_repeated_after_evidence_shift",
                "repeated_target_class": current_target_class,
                "evidence_shifted_to_target_class": evidence_shifted_to_target_class,
            }
        )
    if current_target_class and loop_integrity_cleanup_required:
        findings.append(
            {
                "finding_id": "target_recommended_while_loop_cleanup_required",
                "target_class": current_target_class,
            }
        )
    return {
        "repeated_target_drift_detected": bool(findings),
        "findings": findings,
        "autonomous_loop_readiness_blocked": bool(findings),
    }


def _action_text(synthesis_packet: dict[str, Any]) -> str:
    values = [
        synthesis_packet.get("next_recommended_action"),
        synthesis_packet.get("strategic_decision"),
    ]
    decision = synthesis_packet.get("strategic_decision_report")
    if isinstance(decision, dict):
        values.extend(
            [
                decision.get("next_recommended_action"),
                decision.get("recommendation"),
            ]
        )
    return " ".join(str(value) for value in values if value).lower()


def _mentions(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _proof_exists(
    selected_candidate: dict[str, Any],
    proof_packet: dict[str, Any] | None,
) -> bool:
    return bool(selected_candidate.get("proof_packet_id") or (proof_packet or {}).get("packet_id"))


def _reader_state_exists(
    selected_candidate: dict[str, Any],
    reader_state_packet: dict[str, Any] | None,
) -> bool:
    return bool(
        selected_candidate.get("reader_state_packet_id")
        or selected_candidate.get("reader_state_evaluated")
        or (reader_state_packet or {}).get("packet_id")
    )


def _strategy_already_consumed(
    *,
    selected_candidate: dict[str, Any],
    source_chain: list[dict[str, Any]],
    strategy_packet: dict[str, Any] | None,
) -> bool:
    strategy_id = str((strategy_packet or {}).get("packet_id") or "")
    if selected_candidate.get("source_strategy_packet_id"):
        return True
    if strategy_id:
        for source in source_chain:
            if source.get("source_strategy_packet_id") == strategy_id:
                return True
    return bool(strategy_packet and selected_candidate.get("packet_id"))
