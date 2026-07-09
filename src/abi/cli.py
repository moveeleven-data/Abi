"""Command line interface for Abi."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from abi.artifacts import artifact_to_dict, get_artifact, list_all_artifacts
from abi.config import AbiConfig
from abi.controller.control import inspect_active_run
from abi.controller.finalization import check_finalization
from abi.controller.policy import (
    DEFAULT_FINALIZATION_PROFILE,
    GATE_PROFILE_NAMES,
    gate_catalog_to_dict,
)
from abi.controller.release_readiness import evaluate_release_readiness
from abi.controller.state import ensure_active_run, get_latest_run, get_run, list_runs, run_to_dict
from abi.db import connect, get_counts, initialize_database
from abi.live_model import LIVE_WORKERS, run_live_abi_ear_worker
from abi.model_calls import get_model_call, list_model_calls, model_call_to_dict
from abi.model_driver import run_model_driver_demo
from abi.modules.abi_ear import run_abi_ear_demo
from abi.modules.autonomous_revision import (
    AUTONOMOUS_REVISION_CLIENTS,
    AUTONOMOUS_REVISION_MAX_MODEL_CALLS_DEFAULT,
    run_autonomous_revision,
)
from abi.modules.ablation_informed_revision import (
    ABLATION_INFORMED_REVISION_CLIENTS,
    ABLATION_INFORMED_REVISION_MAX_MODEL_CALLS_DEFAULT,
    run_ablation_informed_revision,
)
from abi.modules.executed_ablation import (
    EXECUTED_ABLATION_CLIENTS,
    EXECUTED_ABLATION_MAX_MODEL_CALLS_DEFAULT,
    run_executed_ablation,
)
from abi.modules.autonomous_evidence_synthesis import run_autonomous_evidence_synthesis
from abi.modules.architecture_evidence_risk_checkpoint import (
    run_architecture_evidence_risk_checkpoint,
)
from abi.modules.checkpoint_strategy_direction_review import (
    run_checkpoint_strategy_direction_review,
)
from abi.modules.post_local_residual_strategy_synthesis import (
    run_post_local_residual_strategy_synthesis,
)
from abi.modules.strongest_rival_forensic_diagnosis import (
    STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_CLIENTS,
    run_strongest_rival_forensic_diagnosis,
)
from abi.modules.local_law_discovery import run_local_law_discovery
from abi.modules.direct_rival_subject_materialization import (
    run_direct_rival_subject_materialization,
)
from abi.modules.model_backed_local_law_diagnostic import (
    MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_CLIENTS,
    MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_MAX_MODEL_CALLS_DEFAULT,
    run_model_backed_local_law_diagnostic,
)
from abi.modules.nonlocal_law_guided_strategy import (
    run_nonlocal_law_guided_strategy,
)
from abi.modules.nonlocal_law_guided_work_order import (
    run_nonlocal_law_guided_work_order_planning,
)
from abi.modules.nonlocal_law_guided_generation_authorization import (
    NONLOCAL_LAW_GENERATION_AUTHORIZATION_DECISIONS,
    run_nonlocal_law_generation_authorization,
)
from abi.modules.nonlocal_law_guided_candidate_generation import (
    NONLOCAL_LAW_CANDIDATE_GENERATION_CLIENTS,
    NONLOCAL_LAW_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT,
    run_nonlocal_law_candidate_generation,
)
from abi.modules.nonlocal_law_candidate_ablation import (
    run_nonlocal_law_candidate_ablation,
)
from abi.modules.nonlocal_law_candidate_reader_state_evaluation import (
    NONLOCAL_LAW_CANDIDATE_READER_STATE_CLIENTS,
    NONLOCAL_LAW_CANDIDATE_READER_STATE_MAX_MODEL_CALLS_DEFAULT,
    run_nonlocal_law_candidate_reader_state_evaluation,
)
from abi.modules.nonlocal_law_candidate_evidence_synthesis import (
    run_nonlocal_law_candidate_evidence_synthesis,
)
from abi.modules.nonlocal_law_cycle_consolidation import (
    run_nonlocal_law_cycle_consolidation,
)
from abi.modules.nonlocal_law_consolidated_target_selection import (
    run_nonlocal_law_consolidated_target_selection,
)
from abi.modules.nonlocal_law_selected_target_work_order import (
    run_nonlocal_law_selected_target_work_order_planning,
)
from abi.modules.nonlocal_law_selected_target_generation_authorization import (
    NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_DECISIONS,
    run_nonlocal_law_selected_target_generation_authorization,
)
from abi.modules.nonlocal_law_selected_target_candidate_generation import (
    NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_CLIENTS,
    NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT,
    run_nonlocal_law_selected_target_candidate_generation,
)
from abi.modules.nonlocal_law_selected_target_candidate_ablation import (
    run_nonlocal_law_selected_target_candidate_ablation,
)
from abi.modules.nonlocal_law_selected_target_reader_state_evaluation import (
    NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_CLIENTS,
    NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_MAX_MODEL_CALLS_DEFAULT,
    run_nonlocal_law_selected_target_reader_state_evaluation,
)
from abi.modules.nonlocal_law_selected_target_evidence_synthesis import (
    run_nonlocal_law_selected_target_evidence_synthesis,
)
from abi.modules.nonlocal_law_selected_target_cycle_consolidation import (
    run_selected_target_cycle_consolidation,
)
from abi.modules.nonlocal_law_selected_target_cycle_target_selection import (
    run_selected_target_cycle_target_selection,
)
from abi.modules.bounded_macro_recomposition import (
    BOUNDED_MACRO_RECOMPOSITION_CLIENTS,
    BOUNDED_MACRO_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT,
    run_bounded_macro_recomposition,
)
from abi.modules.evidence_loop_review import run_evidence_loop_review
from abi.modules.loop_integrity_cleanup import run_loop_integrity_cleanup
from abi.modules.internal_reader_lab import (
    INTERNAL_READER_LAB_CLIENTS,
    INTERNAL_READER_LAB_MAX_MODEL_CALLS_DEFAULT,
    run_internal_reader_lab,
)
from abi.modules.internal_reader_state_evaluation import (
    INTERNAL_READER_STATE_EVAL_CLIENTS,
    INTERNAL_READER_STATE_EVAL_MAX_MODEL_CALLS_DEFAULT,
    run_internal_reader_state_evaluation,
)
from abi.modules.next_target_strategy import run_next_target_strategy
from abi.modules.object_event_recomposition import (
    OBJECT_EVENT_RECOMPOSITION_CLIENTS,
    OBJECT_EVENT_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT,
    run_object_event_recomposition,
)
from abi.modules.residual_target_selection import run_residual_target_selection
from abi.modules.residual_generation_authorization import (
    RESIDUAL_GENERATION_AUTHORIZATION_DECISIONS,
    run_residual_generation_authorization,
)
from abi.modules.residual_candidate_generation import (
    RESIDUAL_CANDIDATE_GENERATION_CLIENTS,
    RESIDUAL_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT,
    run_residual_candidate_generation,
)
from abi.modules.residual_work_order import run_residual_work_order_planning
from abi.modules.supervised_cycle_authorization import (
    SUPERVISED_CYCLE_AUTHORIZATION_DECISIONS,
    run_supervised_cycle_authorization,
)
from abi.modules.live_abi_ear import (
    LIVE_ABI_EAR_CLIENTS,
    LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT,
    run_live_abi_ear_packet_demo,
)
from abi.modules.live_reread import (
    LIVE_REREAD_CLIENTS,
    LIVE_REREAD_MAX_MODEL_CALLS_DEFAULT,
    run_live_reread_packet_demo,
)
from abi.modules.production_harness import run_production_harness_demo
from abi.modules.production_run import (
    PRODUCTION_RUN_CLIENTS,
    PRODUCTION_RUN_MAX_MODEL_CALLS_DEFAULT,
    run_production_live_demo,
)
from abi.modules.pilot_artifact_set import (
    PILOT_ARTIFACT_SET_CLIENTS,
    PILOT_ARTIFACT_SET_MAX_MODEL_CALLS_DEFAULT,
    import_pilot_rival,
    run_pilot_artifact_set,
)
from abi.modules.reread import run_reread_demo
from abi.packets import read_json_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abi", description="Abi infrastructure CLI")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root. Defaults to the current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create Phase 0 folders, database, and an active run")
    subparsers.add_parser("status", help="Report current Phase 0 state")
    finalize_parser = subparsers.add_parser("finalize", help="Run fail-closed finalization checks")
    finalize_parser.add_argument(
        "--profile",
        choices=GATE_PROFILE_NAMES,
        default=None,
        help="Optional named finalization gate profile to evaluate.",
    )
    gate_parser = subparsers.add_parser("gate", help="Inspect gate profiles and catalog")
    gate_subparsers = gate_parser.add_subparsers(dest="gate_command", required=True)
    gate_subparsers.add_parser("list", help="List known gates and required profiles")
    finalization_parser = subparsers.add_parser(
        "finalization",
        help="Inspect profile-aware finalization readiness",
    )
    finalization_subparsers = finalization_parser.add_subparsers(
        dest="finalization_command",
        required=True,
    )
    finalization_status_parser = finalization_subparsers.add_parser(
        "status",
        help="Emit a release-readiness report for a gate profile",
    )
    finalization_status_parser.add_argument(
        "--profile",
        choices=GATE_PROFILE_NAMES,
        default=DEFAULT_FINALIZATION_PROFILE,
        help="Gate profile to evaluate.",
    )
    ear_parser = subparsers.add_parser("ear", help="Run deterministic Abi Ear commands")
    ear_subparsers = ear_parser.add_subparsers(dest="ear_command", required=True)
    ear_subparsers.add_parser("demo", help="Run the deterministic Abi Ear benchmark")
    ear_live_parser = ear_subparsers.add_parser(
        "live-demo",
        help="Run the guarded live Abi Ear packet pipeline",
    )
    ear_live_parser.add_argument(
        "--client",
        choices=LIVE_ABI_EAR_CLIENTS,
        required=True,
        help="Packet model client to use.",
    )
    ear_live_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow the OpenAI client to make live model calls.",
    )
    ear_live_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=LIVE_ABI_EAR_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for the packet.",
    )
    reread_parser = subparsers.add_parser("reread", help="Run deterministic minimal reread commands")
    reread_subparsers = reread_parser.add_subparsers(dest="reread_command", required=True)
    reread_subparsers.add_parser("demo", help="Run the deterministic minimal reread benchmark")
    reread_live_parser = reread_subparsers.add_parser(
        "live-demo",
        help="Run the guarded live Minimal Reread packet pipeline",
    )
    reread_live_parser.add_argument(
        "--client",
        choices=LIVE_REREAD_CLIENTS,
        required=True,
        help="Packet model client to use.",
    )
    reread_live_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow the OpenAI client to make live model calls.",
    )
    reread_live_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=LIVE_REREAD_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for the packet.",
    )
    harness_parser = subparsers.add_parser("harness", help="Run deterministic production harness commands")
    harness_subparsers = harness_parser.add_subparsers(dest="harness_command", required=True)
    harness_subparsers.add_parser("demo", help="Run the deterministic production harness scaffold")
    production_parser = subparsers.add_parser(
        "production",
        help="Run controlled source-to-artifact production commands",
    )
    production_subparsers = production_parser.add_subparsers(
        dest="production_command",
        required=True,
    )
    production_live_parser = production_subparsers.add_parser(
        "live-demo",
        help="Run the guarded source-to-artifact production scaffold",
    )
    production_live_parser.add_argument(
        "--client",
        choices=PRODUCTION_RUN_CLIENTS,
        required=True,
        help="Production packet client path to use.",
    )
    production_live_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow the OpenAI path to make live model calls.",
    )
    production_live_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=PRODUCTION_RUN_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed across upstream live packets.",
    )
    pilot_parser = subparsers.add_parser(
        "pilot",
        help="Prepare candidate/baseline/rival artifact sets",
    )
    pilot_subparsers = pilot_parser.add_subparsers(
        dest="pilot_command",
        required=True,
    )
    pilot_artifact_set_parser = pilot_subparsers.add_parser(
        "artifact-set",
        help="Build a source-frozen pilot artifact set",
    )
    pilot_artifact_set_parser.add_argument(
        "--client",
        choices=PILOT_ARTIFACT_SET_CLIENTS,
        required=True,
        help="Pilot artifact-set client path to use.",
    )
    pilot_artifact_set_parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        help="Directory containing frozen source files for the pilot set.",
    )
    pilot_artifact_set_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow the OpenAI path to make live model calls.",
    )
    pilot_artifact_set_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=PILOT_ARTIFACT_SET_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for pilot artifact-set workers.",
    )
    pilot_import_rival_parser = pilot_subparsers.add_parser(
        "import-rival",
        help="Import a strongest-rival text into an existing pilot packet.",
    )
    pilot_import_rival_parser.add_argument(
        "--packet-dir",
        type=Path,
        required=True,
        help="Existing pilot packet directory to derive from.",
    )
    pilot_import_rival_parser.add_argument(
        "--rival-file",
        type=Path,
        required=True,
        help="Private strongest-rival text file to import as Text D.",
    )
    autonomous_parser = subparsers.add_parser(
        "autonomous",
        help="Run autonomous internal creative-engine commands",
    )
    autonomous_subparsers = autonomous_parser.add_subparsers(
        dest="autonomous_command",
        required=True,
    )
    reader_lab_parser = autonomous_subparsers.add_parser(
        "reader-lab",
        help="Run the Autonomous Internal Reader Lab v1 packet",
    )
    reader_lab_parser.add_argument(
        "--client",
        choices=INTERNAL_READER_LAB_CLIENTS,
        required=True,
        help="Internal reader lab client path to use.",
    )
    reader_lab_parser.add_argument(
        "--packet-dir",
        type=Path,
        required=True,
        help="Pilot candidate/baseline/rival packet directory to inspect.",
    )
    reader_lab_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    reader_lab_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=INTERNAL_READER_LAB_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for internal reader workers.",
    )
    autonomous_revise_parser = autonomous_subparsers.add_parser(
        "revise",
        help="Run the Autonomous Closed-Loop Revision v1 packet",
    )
    autonomous_revise_parser.add_argument(
        "--client",
        choices=AUTONOMOUS_REVISION_CLIENTS,
        required=True,
        help="Autonomous revision client path to use.",
    )
    autonomous_revise_parser.add_argument(
        "--reader-lab-packet",
        type=Path,
        required=True,
        help="Internal reader-lab packet directory to revise from.",
    )
    autonomous_revise_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_revise_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=AUTONOMOUS_REVISION_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for revision workers.",
    )
    autonomous_ablate_parser = autonomous_subparsers.add_parser(
        "ablate",
        help=(
            "Run executed counterfactual ablation over an autonomous or "
            "ablation-informed revision packet"
        ),
    )
    autonomous_ablate_parser.add_argument(
        "--client",
        choices=EXECUTED_ABLATION_CLIENTS,
        required=True,
        help="Executed ablation client path to use.",
    )
    autonomous_ablate_parser.add_argument(
        "--revision-packet",
        type=Path,
        required=True,
        help=(
            "Revision packet directory to ablate; accepts autonomous_revision "
            "or ablation_informed_revision packets."
        ),
    )
    autonomous_ablate_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_ablate_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=EXECUTED_ABLATION_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for executed ablation workers.",
    )
    autonomous_revise_from_ablation_parser = autonomous_subparsers.add_parser(
        "revise-from-ablation",
        help=(
            "Run one ablation-informed bounded revision cycle from executed "
            "ablation evidence"
        ),
    )
    autonomous_revise_from_ablation_parser.add_argument(
        "--client",
        choices=ABLATION_INFORMED_REVISION_CLIENTS,
        required=True,
        help="Ablation-informed revision client path to use.",
    )
    autonomous_revise_from_ablation_parser.add_argument(
        "--executed-ablation-packet",
        type=Path,
        required=True,
        help=(
            "Executed ablation packet directory to revise from; its source "
            "revision may be autonomous_revision or ablation_informed_revision."
        ),
    )
    autonomous_revise_from_ablation_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_revise_from_ablation_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=ABLATION_INFORMED_REVISION_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for ablation-informed revision.",
    )
    autonomous_synthesize_evidence_parser = autonomous_subparsers.add_parser(
        "synthesize-evidence",
        help="Synthesize autonomous revision/ablation evidence into a fail-closed decision packet",
    )
    autonomous_synthesize_evidence_parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID whose autonomous evidence chain should be synthesized.",
    )
    autonomous_macro_recompose_parser = autonomous_subparsers.add_parser(
        "macro-recompose",
        help="Run bounded macro recomposition from an evidence synthesis packet",
    )
    autonomous_macro_recompose_parser.add_argument(
        "--client",
        choices=BOUNDED_MACRO_RECOMPOSITION_CLIENTS,
        required=True,
        help="Bounded macro recomposition client path to use.",
    )
    autonomous_macro_recompose_parser.add_argument(
        "--synthesis-packet",
        type=Path,
        required=True,
        help="Autonomous evidence synthesis packet directory to consume.",
    )
    autonomous_macro_recompose_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_macro_recompose_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=BOUNDED_MACRO_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for bounded macro recomposition.",
    )
    autonomous_reader_state_eval_parser = autonomous_subparsers.add_parser(
        "reader-state-eval",
        help="Evaluate the synthesis-selected candidate through internal reader-state traces",
    )
    autonomous_reader_state_eval_parser.add_argument(
        "--client",
        choices=INTERNAL_READER_STATE_EVAL_CLIENTS,
        required=True,
        help="Internal reader-state evaluation client path to use.",
    )
    autonomous_reader_state_eval_parser.add_argument(
        "--synthesis-packet",
        type=Path,
        required=True,
        help="Autonomous evidence synthesis packet directory to consume.",
    )
    autonomous_reader_state_eval_parser.add_argument(
        "--target-candidate-packet",
        type=Path,
        required=False,
        help=(
            "Optional provisional candidate packet directory to evaluate when "
            "synthesis preserves a different current best."
        ),
    )
    autonomous_reader_state_eval_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_reader_state_eval_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=INTERNAL_READER_STATE_EVAL_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for reader-state workers.",
    )
    autonomous_plan_next_target_parser = autonomous_subparsers.add_parser(
        "plan-next-target",
        help="Plan the next evidence-grounded autonomous target without generation",
    )
    autonomous_plan_next_target_parser.add_argument(
        "--synthesis-packet",
        type=Path,
        required=False,
        help="Autonomous evidence synthesis packet directory to consume.",
    )
    autonomous_plan_next_target_parser.add_argument(
        "--authorization-packet",
        type=Path,
        required=False,
        help=(
            "Supervised cycle authorization packet directory to consume for "
            "authorization-aware next-target planning."
        ),
    )
    autonomous_plan_next_target_parser.add_argument(
        "--architecture-risk-checkpoint",
        type=Path,
        required=False,
        help="Architecture/evidence-risk checkpoint packet directory to consume.",
    )
    autonomous_review_checkpoint_strategy_parser = autonomous_subparsers.add_parser(
        "review-checkpoint-strategy",
        help="Record an operator-reviewed checkpoint direction without generation",
    )
    autonomous_review_checkpoint_strategy_parser.add_argument(
        "--strategy-packet",
        type=Path,
        required=True,
        help="Checkpoint-aware next-target strategy packet directory to consume.",
    )
    autonomous_review_checkpoint_strategy_parser.add_argument(
        "--direction",
        required=True,
        help="Checkpoint plausible direction ID to review.",
    )
    autonomous_review_checkpoint_strategy_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the checkpoint-aware strategy packet.",
    )
    autonomous_post_local_strategy_parser = autonomous_subparsers.add_parser(
        "synthesize-post-local-residual-strategy",
        help=(
            "Synthesize a higher-order strategy after local residual paths "
            "are paused"
        ),
    )
    autonomous_post_local_strategy_parser.add_argument(
        "--direction-review-packet",
        type=Path,
        required=True,
        help="Checkpoint strategy direction review packet directory to consume.",
    )
    autonomous_post_local_strategy_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the post-local strategy direction.",
    )
    autonomous_strongest_rival_diagnosis_parser = autonomous_subparsers.add_parser(
        "diagnose-strongest-rival",
        help="Diagnose why the strongest rival still blocks without generation",
    )
    autonomous_strongest_rival_diagnosis_parser.add_argument(
        "--client",
        choices=STRONGEST_RIVAL_FORENSIC_DIAGNOSIS_CLIENTS,
        required=True,
        help="Forensic diagnosis client path to use.",
    )
    autonomous_strongest_rival_diagnosis_parser.add_argument(
        "--post-local-strategy-packet",
        type=Path,
        required=True,
        help="Post-local residual strategy synthesis packet directory to consume.",
    )
    autonomous_strongest_rival_diagnosis_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the post-local strategy packet.",
    )
    autonomous_strongest_rival_diagnosis_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_local_law_parser = autonomous_subparsers.add_parser(
        "discover-local-law",
        help="Discover a diagnostic local law from strongest-rival forensics",
    )
    autonomous_local_law_parser.add_argument(
        "--diagnosis-packet",
        type=Path,
        required=True,
        help="Strongest-rival forensic diagnosis packet directory to consume.",
    )
    autonomous_local_law_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the source diagnosis packet.",
    )
    autonomous_direct_rival_parser = autonomous_subparsers.add_parser(
        "materialize-direct-rival-subject",
        help="Materialize direct strongest-rival subject evidence if present",
    )
    autonomous_direct_rival_parser.add_argument(
        "--local-law-packet",
        type=Path,
        required=True,
        help="Local-law discovery packet directory to consume.",
    )
    autonomous_direct_rival_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the source local-law packet.",
    )
    autonomous_local_law_rival_diagnostic_parser = autonomous_subparsers.add_parser(
        "diagnose-local-law-with-rival",
        help="Diagnose a local law against a materialized direct rival subject",
    )
    autonomous_local_law_rival_diagnostic_parser.add_argument(
        "--client",
        choices=MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_CLIENTS,
        required=True,
        help="Local-law rival diagnostic client path to use.",
    )
    autonomous_local_law_rival_diagnostic_parser.add_argument(
        "--direct-rival-materialization-packet",
        type=Path,
        required=True,
        help="Direct-rival subject materialization packet directory to consume.",
    )
    autonomous_local_law_rival_diagnostic_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the materialized direct rival subject.",
    )
    autonomous_local_law_rival_diagnostic_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_local_law_rival_diagnostic_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=MODEL_BACKED_LOCAL_LAW_DIAGNOSTIC_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for local-law rival diagnosis.",
    )
    autonomous_nonlocal_law_strategy_parser = autonomous_subparsers.add_parser(
        "plan-nonlocal-law-strategy",
        help="Plan a non-generative nonlocal strategy from a live rival diagnostic",
    )
    autonomous_nonlocal_law_strategy_parser.add_argument(
        "--diagnostic-packet",
        type=Path,
        required=True,
        help="Live model-backed local-law/rival diagnostic packet directory to consume.",
    )
    autonomous_nonlocal_law_strategy_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the live rival diagnostic packet.",
    )
    autonomous_nonlocal_law_work_order_parser = autonomous_subparsers.add_parser(
        "plan-nonlocal-law-work-order",
        help="Plan a nonlocal law-guided work order without generation",
    )
    autonomous_nonlocal_law_work_order_parser.add_argument(
        "--strategy-packet",
        type=Path,
        required=True,
        help="Nonlocal law-guided strategy packet directory to consume.",
    )
    autonomous_nonlocal_law_work_order_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the nonlocal strategy packet.",
    )
    autonomous_selected_nonlocal_law_work_order_parser = (
        autonomous_subparsers.add_parser(
            "plan-selected-nonlocal-law-work-order",
            help="Plan a work order from a selected nonlocal law target",
        )
    )
    autonomous_selected_nonlocal_law_work_order_parser.add_argument(
        "--target-selection-packet",
        type=Path,
        required=True,
        help="Corrected nonlocal law target-selection packet directory to consume.",
    )
    autonomous_selected_nonlocal_law_work_order_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the selected target packet.",
    )
    autonomous_selected_nonlocal_law_authorization_parser = (
        autonomous_subparsers.add_parser(
            "authorize-selected-nonlocal-law-generation",
            help="Authorize one bounded selected-target generation attempt",
        )
    )
    autonomous_selected_nonlocal_law_authorization_parser.add_argument(
        "--work-order-packet",
        type=Path,
        required=True,
        help="Corrected selected-target work-order packet directory to consume.",
    )
    autonomous_selected_nonlocal_law_authorization_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the selected-target work order.",
    )
    autonomous_selected_nonlocal_law_authorization_parser.add_argument(
        "--decision",
        choices=NONLOCAL_LAW_SELECTED_TARGET_GENERATION_AUTHORIZATION_DECISIONS,
        required=True,
        help="Operator selected-target generation authorization decision.",
    )
    autonomous_selected_nonlocal_law_candidate_parser = (
        autonomous_subparsers.add_parser(
            "generate-selected-nonlocal-law-candidate",
            help="Generate one bounded selected nonlocal law candidate",
        )
    )
    autonomous_selected_nonlocal_law_candidate_parser.add_argument(
        "--client",
        choices=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_CLIENTS,
        required=True,
        help="Selected-target generation client path.",
    )
    autonomous_selected_nonlocal_law_candidate_parser.add_argument(
        "--authorization-packet",
        type=Path,
        required=True,
        help="Selected-target generation authorization packet directory.",
    )
    autonomous_selected_nonlocal_law_candidate_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_selected_nonlocal_law_candidate_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=NONLOCAL_LAW_SELECTED_TARGET_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model calls allowed for guarded live-model paths.",
    )
    autonomous_selected_nonlocal_law_candidate_ablation_parser = (
        autonomous_subparsers.add_parser(
            "ablate-selected-nonlocal-law-candidate",
            help="Create deterministic ablation controls for a selected-target candidate",
        )
    )
    autonomous_selected_nonlocal_law_candidate_ablation_parser.add_argument(
        "--candidate-packet",
        type=Path,
        required=True,
        help="Accepted selected nonlocal-law candidate packet directory.",
    )
    autonomous_selected_nonlocal_law_candidate_ablation_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the accepted selected-target candidate.",
    )
    autonomous_selected_nonlocal_law_reader_state_parser = (
        autonomous_subparsers.add_parser(
            "evaluate-selected-nonlocal-law-candidate-reader-state",
            help="Evaluate selected-target candidate reader-state effects",
        )
    )
    autonomous_selected_nonlocal_law_reader_state_parser.add_argument(
        "--client",
        choices=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_CLIENTS,
        required=True,
        help="Selected-target reader-state evaluation client path.",
    )
    autonomous_selected_nonlocal_law_reader_state_parser.add_argument(
        "--ablation-packet",
        type=Path,
        required=True,
        help="Selected-target candidate ablation packet directory.",
    )
    autonomous_selected_nonlocal_law_reader_state_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the selected-target ablation packet.",
    )
    autonomous_selected_nonlocal_law_reader_state_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_selected_nonlocal_law_reader_state_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=NONLOCAL_LAW_SELECTED_TARGET_READER_STATE_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model calls allowed for guarded live-model paths.",
    )
    autonomous_selected_nonlocal_law_synthesis_parser = (
        autonomous_subparsers.add_parser(
            "synthesize-selected-nonlocal-law-candidate-evidence",
            help="Synthesize selected-target evidence without generation",
        )
    )
    autonomous_selected_nonlocal_law_synthesis_parser.add_argument(
        "--reader-state-packet",
        type=Path,
        required=True,
        help="Model-backed selected-target reader-state packet directory.",
    )
    autonomous_selected_nonlocal_law_synthesis_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the selected-target reader-state packet.",
    )
    autonomous_nonlocal_law_authorization_parser = autonomous_subparsers.add_parser(
        "authorize-nonlocal-law-generation",
        help="Authorize one bounded nonlocal law-guided generation attempt",
    )
    autonomous_nonlocal_law_authorization_parser.add_argument(
        "--work-order-packet",
        type=Path,
        required=True,
        help="Corrected nonlocal law-guided work-order packet directory to consume.",
    )
    autonomous_nonlocal_law_authorization_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the nonlocal law-guided work order.",
    )
    autonomous_nonlocal_law_authorization_parser.add_argument(
        "--decision",
        choices=NONLOCAL_LAW_GENERATION_AUTHORIZATION_DECISIONS,
        required=True,
        help="Operator generation authorization decision.",
    )
    autonomous_nonlocal_law_candidate_parser = autonomous_subparsers.add_parser(
        "generate-nonlocal-law-candidate",
        help="Generate one bounded nonlocal law-guided candidate",
    )
    autonomous_nonlocal_law_candidate_parser.add_argument(
        "--client",
        choices=NONLOCAL_LAW_CANDIDATE_GENERATION_CLIENTS,
        required=True,
        help="Nonlocal law-guided generation client path.",
    )
    autonomous_nonlocal_law_candidate_parser.add_argument(
        "--authorization-packet",
        type=Path,
        required=True,
        help="Nonlocal law-guided generation authorization packet directory.",
    )
    autonomous_nonlocal_law_candidate_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_nonlocal_law_candidate_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=NONLOCAL_LAW_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model calls allowed for guarded live-model paths.",
    )
    autonomous_nonlocal_law_candidate_ablation_parser = (
        autonomous_subparsers.add_parser(
            "ablate-nonlocal-law-candidate",
            help="Create deterministic ablation controls for a reviewed candidate",
        )
    )
    autonomous_nonlocal_law_candidate_ablation_parser.add_argument(
        "--candidate-packet",
        type=Path,
        required=True,
        help="Accepted nonlocal law-guided candidate packet directory.",
    )
    autonomous_nonlocal_law_candidate_ablation_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the accepted candidate before ablation.",
    )
    autonomous_nonlocal_law_reader_state_parser = autonomous_subparsers.add_parser(
        "evaluate-nonlocal-law-candidate-reader-state",
        help="Evaluate a nonlocal law-guided candidate through reader-state controls",
    )
    autonomous_nonlocal_law_reader_state_parser.add_argument(
        "--client",
        choices=NONLOCAL_LAW_CANDIDATE_READER_STATE_CLIENTS,
        required=True,
        help="Nonlocal law candidate reader-state evaluation client path.",
    )
    autonomous_nonlocal_law_reader_state_parser.add_argument(
        "--ablation-packet",
        type=Path,
        required=True,
        help="Nonlocal law candidate ablation packet directory.",
    )
    autonomous_nonlocal_law_reader_state_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the ablation packet before evaluation.",
    )
    autonomous_nonlocal_law_reader_state_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_nonlocal_law_reader_state_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=NONLOCAL_LAW_CANDIDATE_READER_STATE_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model calls allowed for guarded live-model paths.",
    )
    autonomous_nonlocal_law_candidate_synthesis_parser = (
        autonomous_subparsers.add_parser(
            "synthesize-nonlocal-law-candidate-evidence",
            help="Synthesize model-backed nonlocal law candidate evidence",
        )
    )
    autonomous_nonlocal_law_candidate_synthesis_parser.add_argument(
        "--reader-state-packet",
        type=Path,
        required=True,
        help="Model-backed nonlocal law candidate reader-state packet directory.",
    )
    autonomous_nonlocal_law_candidate_synthesis_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the reader-state packet before synthesis.",
    )
    autonomous_loop_review_parser = autonomous_subparsers.add_parser(
        "loop-review",
        help="Review a completed autonomous evidence loop without generation",
    )
    autonomous_loop_review_parser.add_argument(
        "--synthesis-packet",
        type=Path,
        required=True,
        help="Autonomous evidence synthesis packet directory to consume.",
    )
    autonomous_cleanup_loop_integrity_parser = autonomous_subparsers.add_parser(
        "cleanup-loop-integrity",
        help="Create a loop-integrity cleanup checkpoint without generation",
    )
    autonomous_cleanup_loop_integrity_parser.add_argument(
        "--loop-review-packet",
        type=Path,
        required=True,
        help="Evidence loop-review packet directory to checkpoint.",
    )
    autonomous_cleanup_loop_integrity_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the loop-review packet.",
    )
    autonomous_consolidate_nonlocal_law_cycle_parser = (
        autonomous_subparsers.add_parser(
            "consolidate-nonlocal-law-cycle",
            help="Consolidate nonlocal law cycle learning without generation",
        )
    )
    autonomous_consolidate_nonlocal_law_cycle_parser.add_argument(
        "--loop-review-packet",
        type=Path,
        required=True,
        help="Corrected nonlocal law candidate loop-review packet directory.",
    )
    autonomous_consolidate_nonlocal_law_cycle_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the loop-review packet.",
    )
    autonomous_consolidate_selected_target_loop_parser = (
        autonomous_subparsers.add_parser(
            "consolidate-selected-target-loop",
            help="Consolidate selected-target loop learning without generation",
        )
    )
    autonomous_consolidate_selected_target_loop_parser.add_argument(
        "--loop-review-packet",
        type=Path,
        required=True,
        help="Corrected selected-target loop-review packet directory.",
    )
    autonomous_consolidate_selected_target_loop_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the selected-target loop-review packet.",
    )
    autonomous_select_next_selected_target_parser = autonomous_subparsers.add_parser(
        "select-next-selected-target",
        help="Select one target from selected-target cycle consolidation memory",
    )
    autonomous_select_next_selected_target_parser.add_argument(
        "--consolidation-packet",
        type=Path,
        required=True,
        help="Selected-target cycle consolidation packet directory.",
    )
    autonomous_select_next_selected_target_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the selected-target consolidation packet.",
    )
    autonomous_select_nonlocal_law_target_parser = (
        autonomous_subparsers.add_parser(
            "select-nonlocal-law-target",
            help="Select one target from nonlocal law cycle consolidation memory",
        )
    )
    autonomous_select_nonlocal_law_target_parser.add_argument(
        "--consolidation-packet",
        type=Path,
        required=True,
        help="Corrected nonlocal law cycle-consolidation packet directory.",
    )
    autonomous_select_nonlocal_law_target_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the consolidation packet.",
    )
    autonomous_authorize_next_cycle_parser = autonomous_subparsers.add_parser(
        "authorize-next-cycle",
        help="Record supervised operator review of a loop-review packet",
    )
    autonomous_authorize_next_cycle_parser.add_argument(
        "--loop-review-packet",
        type=Path,
        required=False,
        help="Evidence loop-review packet directory to inspect.",
    )
    autonomous_authorize_next_cycle_parser.add_argument(
        "--loop-cleanup-packet",
        type=Path,
        required=False,
        help="Loop-integrity cleanup packet directory to inspect.",
    )
    autonomous_authorize_next_cycle_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the loop-review packet.",
    )
    autonomous_authorize_next_cycle_parser.add_argument(
        "--decision",
        choices=SUPERVISED_CYCLE_AUTHORIZATION_DECISIONS,
        help="Supervised decision for the next cycle.",
    )
    autonomous_architecture_risk_checkpoint_parser = autonomous_subparsers.add_parser(
        "architecture-risk-checkpoint",
        help="Create a deterministic architecture/evidence-risk checkpoint",
    )
    autonomous_architecture_risk_checkpoint_parser.add_argument(
        "--authorization-packet",
        type=Path,
        required=True,
        help="Strategy-only supervised cycle authorization packet directory to consume.",
    )
    autonomous_architecture_risk_checkpoint_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the current loop state.",
    )
    autonomous_select_residual_target_parser = autonomous_subparsers.add_parser(
        "select-residual-target",
        help="Record operator selection of a narrow residual target without generation",
    )
    autonomous_select_residual_target_parser.add_argument(
        "--strategy-packet",
        type=Path,
        help="Next-target strategy packet directory to consume.",
    )
    autonomous_select_residual_target_parser.add_argument(
        "--direction-review-packet",
        type=Path,
        help="Checkpoint strategy direction-review packet directory to consume.",
    )
    autonomous_select_residual_target_parser.add_argument(
        "--target",
        required=True,
        help="Residual target option ID to select.",
    )
    autonomous_select_residual_target_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed and selected the target.",
    )
    autonomous_plan_residual_work_order_parser = autonomous_subparsers.add_parser(
        "plan-residual-work-order",
        help="Plan a target-aware residual work order without generation",
    )
    autonomous_plan_residual_work_order_parser.add_argument(
        "--selection-packet",
        type=Path,
        required=True,
        help="Residual target selection packet directory to consume.",
    )
    autonomous_authorize_residual_generation_parser = autonomous_subparsers.add_parser(
        "authorize-residual-generation",
        help="Record supervised review and authorize one bounded residual generation",
    )
    autonomous_authorize_residual_generation_parser.add_argument(
        "--work-order-packet",
        type=Path,
        required=True,
        help="Residual work-order packet directory to consume.",
    )
    autonomous_authorize_residual_generation_parser.add_argument(
        "--operator-reviewed",
        action="store_true",
        help="Confirm the operator reviewed the residual work-order packet.",
    )
    autonomous_authorize_residual_generation_parser.add_argument(
        "--decision",
        choices=RESIDUAL_GENERATION_AUTHORIZATION_DECISIONS,
        help="Supervised decision for residual generation.",
    )
    autonomous_generate_residual_candidate_parser = autonomous_subparsers.add_parser(
        "generate-residual-candidate",
        help="Run one bounded residual candidate generation attempt",
    )
    autonomous_generate_residual_candidate_parser.add_argument(
        "--client",
        choices=RESIDUAL_CANDIDATE_GENERATION_CLIENTS,
        required=True,
        help="Residual candidate generation client path to use.",
    )
    autonomous_generate_residual_candidate_parser.add_argument(
        "--authorization-packet",
        type=Path,
        required=True,
        help="Residual generation authorization packet directory to consume.",
    )
    autonomous_generate_residual_candidate_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow the guarded OpenAI path.",
    )
    autonomous_generate_residual_candidate_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=RESIDUAL_CANDIDATE_GENERATION_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for residual candidate generation.",
    )
    autonomous_object_event_parser = autonomous_subparsers.add_parser(
        "object-event-recompose",
        help="Run one bounded object-event pressure recomposition from a strategy packet",
    )
    autonomous_object_event_parser.add_argument(
        "--client",
        choices=OBJECT_EVENT_RECOMPOSITION_CLIENTS,
        required=True,
        help="Object-event recomposition client path to use.",
    )
    autonomous_object_event_parser.add_argument(
        "--strategy-packet",
        type=Path,
        required=True,
        help="Next-target strategy packet directory to consume.",
    )
    autonomous_object_event_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow guarded live-model paths.",
    )
    autonomous_object_event_parser.add_argument(
        "--max-model-calls",
        type=int,
        default=OBJECT_EVENT_RECOMPOSITION_MAX_MODEL_CALLS_DEFAULT,
        help="Maximum model-shaped calls allowed for object-event recomposition.",
    )
    controller_parser = subparsers.add_parser("controller", help="Inspect fail-closed controller state")
    controller_subparsers = controller_parser.add_subparsers(
        dest="controller_command",
        required=True,
    )
    controller_subparsers.add_parser("status", help="Emit structured controller decision status")
    controller_subparsers.add_parser("blockers", help="Emit structured controller blocker report")
    controller_subparsers.add_parser("demo", help="Inspect or create a run and show refusal decision")
    artifact_parser = subparsers.add_parser("artifact", help="Inspect registered artifacts")
    artifact_subparsers = artifact_parser.add_subparsers(
        dest="artifact_command",
        required=True,
    )
    artifact_subparsers.add_parser("list", help="List registered artifacts")
    artifact_show_parser = artifact_subparsers.add_parser("show", help="Show one artifact")
    artifact_show_parser.add_argument("artifact_id", help="Registered artifact ID")
    run_parser = subparsers.add_parser("run", help="Inspect runs")
    run_subparsers = run_parser.add_subparsers(dest="run_command", required=True)
    run_subparsers.add_parser("list", help="List runs")
    run_show_parser = run_subparsers.add_parser("show", help="Show one run")
    run_show_parser.add_argument("run_id", help="Run ID")
    run_subparsers.add_parser("latest", help="Show the latest run")
    model_driver_parser = subparsers.add_parser(
        "model-driver",
        help="Run sealed fake-client model-driver commands",
    )
    model_driver_subparsers = model_driver_parser.add_subparsers(
        dest="model_driver_command",
        required=True,
    )
    model_driver_demo_parser = model_driver_subparsers.add_parser(
        "demo",
        help="Run the fake-client structured-output demo",
    )
    model_driver_demo_parser.add_argument(
        "--mode",
        choices=("valid", "minimal", "invalid_json", "malformed", "failure"),
        default="valid",
        help="Fake client mode.",
    )
    model_driver_live_parser = model_driver_subparsers.add_parser(
        "live-demo",
        help="Run the guarded live Abi Ear germ-analysis worker",
    )
    model_driver_live_parser.add_argument(
        "--worker",
        choices=LIVE_WORKERS,
        required=True,
        help="Live worker to run.",
    )
    model_driver_live_parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow the command to make a live model call.",
    )
    model_call_parser = subparsers.add_parser("model-call", help="Inspect model call records")
    model_call_subparsers = model_call_parser.add_subparsers(
        dest="model_call_command",
        required=True,
    )
    model_call_subparsers.add_parser("list", help="List model call records")
    model_call_show_parser = model_call_subparsers.add_parser("show", help="Show one model call")
    model_call_show_parser.add_argument("model_call_id", help="Model call ID")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AbiConfig.from_env(root=args.root)

    if args.command == "init":
        return _cmd_init(config)
    if args.command == "status":
        return _cmd_status(config)
    if args.command == "finalize":
        return _cmd_finalize(config, profile=args.profile)
    if args.command == "gate" and args.gate_command == "list":
        return _cmd_gate_list()
    if args.command == "finalization" and args.finalization_command == "status":
        return _cmd_finalization_status(config, profile=args.profile)
    if args.command == "ear" and args.ear_command == "demo":
        return _cmd_ear_demo(config)
    if args.command == "ear" and args.ear_command == "live-demo":
        return _cmd_ear_live_demo(
            config,
            client_name=args.client,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "reread" and args.reread_command == "demo":
        return _cmd_reread_demo(config)
    if args.command == "reread" and args.reread_command == "live-demo":
        return _cmd_reread_live_demo(
            config,
            client_name=args.client,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "harness" and args.harness_command == "demo":
        return _cmd_harness_demo(config)
    if args.command == "production" and args.production_command == "live-demo":
        return _cmd_production_live_demo(
            config,
            client_name=args.client,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "pilot" and args.pilot_command == "artifact-set":
        return _cmd_pilot_artifact_set(
            config,
            client_name=args.client,
            source_dir=args.source_dir,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "pilot" and args.pilot_command == "import-rival":
        return _cmd_pilot_import_rival(
            config,
            packet_dir=args.packet_dir,
            rival_file=args.rival_file,
        )
    if args.command == "autonomous" and args.autonomous_command == "reader-lab":
        return _cmd_autonomous_reader_lab(
            config,
            client_name=args.client,
            packet_dir=args.packet_dir,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "autonomous" and args.autonomous_command == "revise":
        return _cmd_autonomous_revise(
            config,
            client_name=args.client,
            reader_lab_packet=args.reader_lab_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "autonomous" and args.autonomous_command == "ablate":
        return _cmd_autonomous_ablate(
            config,
            client_name=args.client,
            revision_packet=args.revision_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "autonomous" and args.autonomous_command == "revise-from-ablation":
        return _cmd_autonomous_revise_from_ablation(
            config,
            client_name=args.client,
            executed_ablation_packet=args.executed_ablation_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "autonomous" and args.autonomous_command == "synthesize-evidence":
        return _cmd_autonomous_synthesize_evidence(
            config,
            run_id=args.run_id,
        )
    if args.command == "autonomous" and args.autonomous_command == "macro-recompose":
        return _cmd_autonomous_macro_recompose(
            config,
            client_name=args.client,
            synthesis_packet=args.synthesis_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "autonomous" and args.autonomous_command == "reader-state-eval":
        return _cmd_autonomous_reader_state_eval(
            config,
            client_name=args.client,
            synthesis_packet=args.synthesis_packet,
            target_candidate_packet=args.target_candidate_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "autonomous" and args.autonomous_command == "plan-next-target":
        return _cmd_autonomous_plan_next_target(
            config,
            synthesis_packet=args.synthesis_packet,
            authorization_packet=args.authorization_packet,
            architecture_risk_checkpoint=args.architecture_risk_checkpoint,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "review-checkpoint-strategy"
    ):
        return _cmd_autonomous_review_checkpoint_strategy(
            config,
            strategy_packet=args.strategy_packet,
            direction=args.direction,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "synthesize-post-local-residual-strategy"
    ):
        return _cmd_autonomous_synthesize_post_local_residual_strategy(
            config,
            direction_review_packet=args.direction_review_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "diagnose-strongest-rival"
    ):
        return _cmd_autonomous_diagnose_strongest_rival(
            config,
            client_name=args.client,
            post_local_strategy_packet=args.post_local_strategy_packet,
            operator_reviewed=args.operator_reviewed,
            allow_live_model=args.allow_live_model,
        )
    if args.command == "autonomous" and args.autonomous_command == "discover-local-law":
        return _cmd_autonomous_discover_local_law(
            config,
            diagnosis_packet=args.diagnosis_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "materialize-direct-rival-subject"
    ):
        return _cmd_autonomous_materialize_direct_rival_subject(
            config,
            local_law_packet=args.local_law_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "diagnose-local-law-with-rival"
    ):
        return _cmd_autonomous_diagnose_local_law_with_rival(
            config,
            client_name=args.client,
            direct_rival_materialization_packet=(
                args.direct_rival_materialization_packet
            ),
            operator_reviewed=args.operator_reviewed,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "plan-nonlocal-law-strategy"
    ):
        return _cmd_autonomous_plan_nonlocal_law_strategy(
            config,
            diagnostic_packet=args.diagnostic_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "plan-nonlocal-law-work-order"
    ):
        return _cmd_autonomous_plan_nonlocal_law_work_order(
            config,
            strategy_packet=args.strategy_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "authorize-nonlocal-law-generation"
    ):
        return _cmd_autonomous_authorize_nonlocal_law_generation(
            config,
            work_order_packet=args.work_order_packet,
            operator_reviewed=args.operator_reviewed,
            decision=args.decision,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "generate-nonlocal-law-candidate"
    ):
        return _cmd_autonomous_generate_nonlocal_law_candidate(
            config,
            client_name=args.client,
            authorization_packet=args.authorization_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "ablate-nonlocal-law-candidate"
    ):
        return _cmd_autonomous_ablate_nonlocal_law_candidate(
            config,
            candidate_packet=args.candidate_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command
        == "evaluate-nonlocal-law-candidate-reader-state"
    ):
        return _cmd_autonomous_evaluate_nonlocal_law_candidate_reader_state(
            config,
            client_name=args.client,
            ablation_packet=args.ablation_packet,
            operator_reviewed=args.operator_reviewed,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "synthesize-nonlocal-law-candidate-evidence"
    ):
        return _cmd_autonomous_synthesize_nonlocal_law_candidate_evidence(
            config,
            reader_state_packet=args.reader_state_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if args.command == "autonomous" and args.autonomous_command == "loop-review":
        return _cmd_autonomous_loop_review(
            config,
            synthesis_packet=args.synthesis_packet,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "cleanup-loop-integrity"
    ):
        return _cmd_autonomous_cleanup_loop_integrity(
            config,
            loop_review_packet=args.loop_review_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "consolidate-nonlocal-law-cycle"
    ):
        return _cmd_autonomous_consolidate_nonlocal_law_cycle(
            config,
            loop_review_packet=args.loop_review_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "consolidate-selected-target-loop"
    ):
        return _cmd_autonomous_consolidate_selected_target_loop(
            config,
            loop_review_packet=args.loop_review_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "select-next-selected-target"
    ):
        return _cmd_autonomous_select_next_selected_target(
            config,
            consolidation_packet=args.consolidation_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "select-nonlocal-law-target"
    ):
        return _cmd_autonomous_select_nonlocal_law_target(
            config,
            consolidation_packet=args.consolidation_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "plan-selected-nonlocal-law-work-order"
    ):
        return _cmd_autonomous_plan_selected_nonlocal_law_work_order(
            config,
            target_selection_packet=args.target_selection_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "authorize-selected-nonlocal-law-generation"
    ):
        return _cmd_autonomous_authorize_selected_nonlocal_law_generation(
            config,
            work_order_packet=args.work_order_packet,
            operator_reviewed=args.operator_reviewed,
            decision=args.decision,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "generate-selected-nonlocal-law-candidate"
    ):
        return _cmd_autonomous_generate_selected_nonlocal_law_candidate(
            config,
            client_name=args.client,
            authorization_packet=args.authorization_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "ablate-selected-nonlocal-law-candidate"
    ):
        return _cmd_autonomous_ablate_selected_nonlocal_law_candidate(
            config,
            candidate_packet=args.candidate_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command
        == "evaluate-selected-nonlocal-law-candidate-reader-state"
    ):
        return _cmd_autonomous_evaluate_selected_nonlocal_law_candidate_reader_state(
            config,
            client_name=args.client,
            ablation_packet=args.ablation_packet,
            operator_reviewed=args.operator_reviewed,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command
        == "synthesize-selected-nonlocal-law-candidate-evidence"
    ):
        return _cmd_autonomous_synthesize_selected_nonlocal_law_candidate_evidence(
            config,
            reader_state_packet=args.reader_state_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if args.command == "autonomous" and args.autonomous_command == "authorize-next-cycle":
        return _cmd_autonomous_authorize_next_cycle(
            config,
            loop_review_packet=args.loop_review_packet,
            loop_cleanup_packet=args.loop_cleanup_packet,
            operator_reviewed=args.operator_reviewed,
            decision=args.decision,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "architecture-risk-checkpoint"
    ):
        return _cmd_autonomous_architecture_risk_checkpoint(
            config,
            authorization_packet=args.authorization_packet,
            operator_reviewed=args.operator_reviewed,
        )
    if args.command == "autonomous" and args.autonomous_command == "select-residual-target":
        return _cmd_autonomous_select_residual_target(
            config,
            strategy_packet=args.strategy_packet,
            direction_review_packet=args.direction_review_packet,
            target=args.target,
            operator_reviewed=args.operator_reviewed,
        )
    if args.command == "autonomous" and args.autonomous_command == "plan-residual-work-order":
        return _cmd_autonomous_plan_residual_work_order(
            config,
            selection_packet=args.selection_packet,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "authorize-residual-generation"
    ):
        return _cmd_autonomous_authorize_residual_generation(
            config,
            work_order_packet=args.work_order_packet,
            operator_reviewed=args.operator_reviewed,
            decision=args.decision,
        )
    if (
        args.command == "autonomous"
        and args.autonomous_command == "generate-residual-candidate"
    ):
        return _cmd_autonomous_generate_residual_candidate(
            config,
            client_name=args.client,
            authorization_packet=args.authorization_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "autonomous" and args.autonomous_command == "object-event-recompose":
        return _cmd_autonomous_object_event_recompose(
            config,
            client_name=args.client,
            strategy_packet=args.strategy_packet,
            allow_live_model=args.allow_live_model,
            max_model_calls=args.max_model_calls,
        )
    if args.command == "controller" and args.controller_command == "status":
        return _cmd_controller_status(config)
    if args.command == "controller" and args.controller_command == "blockers":
        return _cmd_controller_blockers(config)
    if args.command == "controller" and args.controller_command == "demo":
        return _cmd_controller_demo(config)
    if args.command == "artifact" and args.artifact_command == "list":
        return _cmd_artifact_list(config)
    if args.command == "artifact" and args.artifact_command == "show":
        return _cmd_artifact_show(config, args.artifact_id)
    if args.command == "run" and args.run_command == "list":
        return _cmd_run_list(config)
    if args.command == "run" and args.run_command == "show":
        return _cmd_run_show(config, args.run_id)
    if args.command == "run" and args.run_command == "latest":
        return _cmd_run_latest(config)
    if args.command == "model-driver" and args.model_driver_command == "demo":
        return _cmd_model_driver_demo(config, args.mode)
    if args.command == "model-driver" and args.model_driver_command == "live-demo":
        return _cmd_model_driver_live_demo(
            config,
            worker=args.worker,
            allow_live_model=args.allow_live_model,
        )
    if args.command == "model-call" and args.model_call_command == "list":
        return _cmd_model_call_list(config)
    if args.command == "model-call" and args.model_call_command == "show":
        return _cmd_model_call_show(config, args.model_call_id)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _cmd_init(config: AbiConfig) -> int:
    run, created = ensure_active_run(config)
    payload = {
        "database_path": str(config.db_path),
        "runs_dir": str(config.runs_dir),
        "outputs_dir": str(config.outputs_dir),
        "active_run_id": run.id,
        "created_run": created,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_status(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        counts = get_counts(connection)
        latest_run = get_latest_run(connection)
    payload = {
        "database_path": str(config.db_path),
        "run_count": counts["runs"],
        "latest_run": run_to_dict(latest_run) if latest_run is not None else None,
        "artifact_count": counts["artifacts"],
        "gate_count": counts["gates"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_finalize(config: AbiConfig, *, profile: str | None = None) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        latest_run = get_latest_run(connection)
        if latest_run is None:
            payload = {
                "run_id": None,
                "refused": True,
                "missing_gates": [],
                "failed_gates": [],
                "message": "Finalization refused; no run exists.",
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 1
        report = check_finalization(connection, run_id=latest_run.id, profile=profile)

    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 1 if report.refused else 0


def _cmd_gate_list() -> int:
    print(json.dumps(gate_catalog_to_dict(), indent=2, sort_keys=True))
    return 0


def _cmd_finalization_status(config: AbiConfig, *, profile: str) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        latest_run = get_latest_run(connection)
        if latest_run is None:
            payload = {
                "run_id": None,
                "profile": profile,
                "eligible": False,
                "missing_gates": [],
                "failed_gates": [],
                "blocking_defects": {},
                "fixture_only_blockers": [],
                "non_final_blockers": [],
                "artifact_blockers": [],
                "blockers": ["no run exists"],
                "recommended_next_action": "run abi init before finalization checks",
                "message": "Finalization status unavailable; no run exists.",
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        report = evaluate_release_readiness(
            connection,
            run_id=latest_run.id,
            profile=profile,
        )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0


def _cmd_ear_demo(config: AbiConfig) -> int:
    result = run_abi_ear_demo(config)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0


def _cmd_ear_live_demo(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_live_abi_ear_packet_demo(
        config,
        client_name=client_name,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_reread_demo(config: AbiConfig) -> int:
    result = run_reread_demo(config)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0


def _cmd_reread_live_demo(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_live_reread_packet_demo(
        config,
        client_name=client_name,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_harness_demo(config: AbiConfig) -> int:
    result = run_production_harness_demo(config)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0


def _cmd_production_live_demo(
    config: AbiConfig,
    *,
    client_name: str,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_production_live_demo(
        config,
        client_name=client_name,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_pilot_artifact_set(
    config: AbiConfig,
    *,
    client_name: str,
    source_dir: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_pilot_artifact_set(
        config,
        client_name=client_name,
        source_dir=source_dir,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_pilot_import_rival(
    config: AbiConfig,
    *,
    packet_dir: Path,
    rival_file: Path,
) -> int:
    result = import_pilot_rival(
        config,
        packet_dir=packet_dir,
        rival_file=rival_file,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_reader_lab(
    config: AbiConfig,
    *,
    client_name: str,
    packet_dir: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_internal_reader_lab(
        config,
        client_name=client_name,
        packet_dir=packet_dir,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_revise(
    config: AbiConfig,
    *,
    client_name: str,
    reader_lab_packet: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_autonomous_revision(
        config,
        client_name=client_name,
        reader_lab_packet=reader_lab_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_ablate(
    config: AbiConfig,
    *,
    client_name: str,
    revision_packet: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_executed_ablation(
        config,
        client_name=client_name,
        revision_packet=revision_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_revise_from_ablation(
    config: AbiConfig,
    *,
    client_name: str,
    executed_ablation_packet: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_ablation_informed_revision(
        config,
        client_name=client_name,
        executed_ablation_packet=executed_ablation_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_synthesize_evidence(
    config: AbiConfig,
    *,
    run_id: str,
) -> int:
    result = run_autonomous_evidence_synthesis(config, run_id=run_id)
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_macro_recompose(
    config: AbiConfig,
    *,
    client_name: str,
    synthesis_packet: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_bounded_macro_recomposition(
        config,
        client_name=client_name,
        synthesis_packet=synthesis_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_reader_state_eval(
    config: AbiConfig,
    *,
    client_name: str,
    synthesis_packet: Path,
    target_candidate_packet: Path | None,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_internal_reader_state_evaluation(
        config,
        client_name=client_name,
        synthesis_packet=synthesis_packet,
        target_candidate_packet=target_candidate_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_plan_next_target(
    config: AbiConfig,
    *,
    synthesis_packet: Path | None,
    authorization_packet: Path | None,
    architecture_risk_checkpoint: Path | None,
) -> int:
    result = run_next_target_strategy(
        config,
        synthesis_packet=synthesis_packet,
        authorization_packet=authorization_packet,
        architecture_risk_checkpoint=architecture_risk_checkpoint,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_review_checkpoint_strategy(
    config: AbiConfig,
    *,
    strategy_packet: Path,
    direction: str,
    operator_reviewed: bool,
) -> int:
    result = run_checkpoint_strategy_direction_review(
        config,
        strategy_packet=strategy_packet,
        direction=direction,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_synthesize_post_local_residual_strategy(
    config: AbiConfig,
    *,
    direction_review_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_post_local_residual_strategy_synthesis(
        config,
        direction_review_packet=direction_review_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_diagnose_strongest_rival(
    config: AbiConfig,
    *,
    client_name: str,
    post_local_strategy_packet: Path,
    operator_reviewed: bool,
    allow_live_model: bool,
) -> int:
    result = run_strongest_rival_forensic_diagnosis(
        config,
        client_name=client_name,
        post_local_strategy_packet=post_local_strategy_packet,
        operator_reviewed=operator_reviewed,
        allow_live_model=allow_live_model,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_discover_local_law(
    config: AbiConfig,
    *,
    diagnosis_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_local_law_discovery(
        config,
        diagnosis_packet=diagnosis_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_materialize_direct_rival_subject(
    config: AbiConfig,
    *,
    local_law_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_direct_rival_subject_materialization(
        config,
        local_law_packet=local_law_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_diagnose_local_law_with_rival(
    config: AbiConfig,
    *,
    client_name: str,
    direct_rival_materialization_packet: Path,
    operator_reviewed: bool,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_model_backed_local_law_diagnostic(
        config,
        client_name=client_name,
        direct_rival_materialization_packet=direct_rival_materialization_packet,
        operator_reviewed=operator_reviewed,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_plan_nonlocal_law_strategy(
    config: AbiConfig,
    *,
    diagnostic_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_guided_strategy(
        config,
        diagnostic_packet=diagnostic_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_plan_nonlocal_law_work_order(
    config: AbiConfig,
    *,
    strategy_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_guided_work_order_planning(
        config,
        strategy_packet=strategy_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_authorize_nonlocal_law_generation(
    config: AbiConfig,
    *,
    work_order_packet: Path,
    operator_reviewed: bool,
    decision: str | None,
) -> int:
    result = run_nonlocal_law_generation_authorization(
        config,
        work_order_packet=work_order_packet,
        operator_reviewed=operator_reviewed,
        decision=decision,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_generate_nonlocal_law_candidate(
    config: AbiConfig,
    *,
    client_name: str,
    authorization_packet: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_nonlocal_law_candidate_generation(
        config,
        client_name=client_name,
        authorization_packet=authorization_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_ablate_nonlocal_law_candidate(
    config: AbiConfig,
    *,
    candidate_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_candidate_ablation(
        config,
        candidate_packet=candidate_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_evaluate_nonlocal_law_candidate_reader_state(
    config: AbiConfig,
    *,
    client_name: str,
    ablation_packet: Path,
    operator_reviewed: bool,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_nonlocal_law_candidate_reader_state_evaluation(
        config,
        client_name=client_name,
        ablation_packet=ablation_packet,
        operator_reviewed=operator_reviewed,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_synthesize_nonlocal_law_candidate_evidence(
    config: AbiConfig,
    *,
    reader_state_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_candidate_evidence_synthesis(
        config,
        reader_state_packet=reader_state_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_loop_review(
    config: AbiConfig,
    *,
    synthesis_packet: Path,
) -> int:
    result = run_evidence_loop_review(config, synthesis_packet=synthesis_packet)
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_cleanup_loop_integrity(
    config: AbiConfig,
    *,
    loop_review_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_loop_integrity_cleanup(
        config,
        loop_review_packet=loop_review_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_consolidate_nonlocal_law_cycle(
    config: AbiConfig,
    *,
    loop_review_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_cycle_consolidation(
        config,
        loop_review_packet=loop_review_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_consolidate_selected_target_loop(
    config: AbiConfig,
    *,
    loop_review_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_selected_target_cycle_consolidation(
        config,
        loop_review_packet=loop_review_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_select_next_selected_target(
    config: AbiConfig,
    *,
    consolidation_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_selected_target_cycle_target_selection(
        config,
        consolidation_packet=consolidation_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_select_nonlocal_law_target(
    config: AbiConfig,
    *,
    consolidation_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_consolidated_target_selection(
        config,
        consolidation_packet=consolidation_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_plan_selected_nonlocal_law_work_order(
    config: AbiConfig,
    *,
    target_selection_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_selected_target_work_order_planning(
        config,
        target_selection_packet=target_selection_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_authorize_selected_nonlocal_law_generation(
    config: AbiConfig,
    *,
    work_order_packet: Path,
    operator_reviewed: bool,
    decision: str | None,
) -> int:
    result = run_nonlocal_law_selected_target_generation_authorization(
        config,
        work_order_packet=work_order_packet,
        operator_reviewed=operator_reviewed,
        decision=decision,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_generate_selected_nonlocal_law_candidate(
    config: AbiConfig,
    *,
    client_name: str,
    authorization_packet: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_nonlocal_law_selected_target_candidate_generation(
        config,
        client_name=client_name,
        authorization_packet=authorization_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_ablate_selected_nonlocal_law_candidate(
    config: AbiConfig,
    *,
    candidate_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_selected_target_candidate_ablation(
        config,
        candidate_packet=candidate_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_evaluate_selected_nonlocal_law_candidate_reader_state(
    config: AbiConfig,
    *,
    client_name: str,
    ablation_packet: Path,
    operator_reviewed: bool,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_nonlocal_law_selected_target_reader_state_evaluation(
        config,
        client_name=client_name,
        ablation_packet=ablation_packet,
        operator_reviewed=operator_reviewed,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_synthesize_selected_nonlocal_law_candidate_evidence(
    config: AbiConfig,
    *,
    reader_state_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_nonlocal_law_selected_target_evidence_synthesis(
        config,
        reader_state_packet=reader_state_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_authorize_next_cycle(
    config: AbiConfig,
    *,
    loop_review_packet: Path | None,
    loop_cleanup_packet: Path | None,
    operator_reviewed: bool,
    decision: str | None,
) -> int:
    result = run_supervised_cycle_authorization(
        config,
        loop_review_packet=loop_review_packet,
        loop_cleanup_packet=loop_cleanup_packet,
        operator_reviewed=operator_reviewed,
        decision=decision,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_architecture_risk_checkpoint(
    config: AbiConfig,
    *,
    authorization_packet: Path,
    operator_reviewed: bool,
) -> int:
    result = run_architecture_evidence_risk_checkpoint(
        config,
        authorization_packet=authorization_packet,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_select_residual_target(
    config: AbiConfig,
    *,
    strategy_packet: Path | None,
    direction_review_packet: Path | None,
    target: str,
    operator_reviewed: bool,
) -> int:
    result = run_residual_target_selection(
        config,
        strategy_packet=strategy_packet,
        direction_review_packet=direction_review_packet,
        target=target,
        operator_reviewed=operator_reviewed,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_plan_residual_work_order(
    config: AbiConfig,
    *,
    selection_packet: Path,
) -> int:
    result = run_residual_work_order_planning(
        config,
        selection_packet=selection_packet,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_authorize_residual_generation(
    config: AbiConfig,
    *,
    work_order_packet: Path,
    operator_reviewed: bool,
    decision: str | None,
) -> int:
    result = run_residual_generation_authorization(
        config,
        work_order_packet=work_order_packet,
        operator_reviewed=operator_reviewed,
        decision=decision,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_generate_residual_candidate(
    config: AbiConfig,
    *,
    client_name: str,
    authorization_packet: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_residual_candidate_generation(
        config,
        client_name=client_name,
        authorization_packet=authorization_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_autonomous_object_event_recompose(
    config: AbiConfig,
    *,
    client_name: str,
    strategy_packet: Path,
    allow_live_model: bool,
    max_model_calls: int,
) -> int:
    result = run_object_event_recomposition(
        config,
        client_name=client_name,
        strategy_packet=strategy_packet,
        allow_live_model=allow_live_model,
        max_model_calls=max_model_calls,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_controller_status(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
    if decision is None:
        payload = {
            "decision": None,
            "message": "No active run exists.",
        }
    else:
        payload = decision.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_controller_blockers(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
    if decision is None:
        payload = {
            "blocker_report": None,
            "message": "No active run exists.",
        }
    else:
        payload = decision.blocker_report.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_controller_demo(config: AbiConfig) -> int:
    ensure_active_run(config)
    with connect(config.db_path) as connection:
        decision = inspect_active_run(connection)
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return 0


def _cmd_artifact_list(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        artifacts = list_all_artifacts(connection)
    payload = {"artifacts": [artifact_to_dict(artifact) for artifact in artifacts]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_artifact_show(config: AbiConfig, artifact_id: str) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        artifact = get_artifact(connection, artifact_id)
    if artifact is None:
        payload = {
            "artifact": None,
            "message": f"Artifact not found: {artifact_id}",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    payload = {
        "artifact": artifact_to_dict(artifact),
        "content": None,
    }
    try:
        payload["content"] = read_json_file(artifact.path)
    except (OSError, json.JSONDecodeError):
        payload["content"] = None
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_run_list(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        runs = list_runs(connection)
    payload = {"runs": [run_to_dict(run) for run in runs]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_run_show(config: AbiConfig, run_id: str) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        run = get_run(connection, run_id)
    if run is None:
        payload = {
            "run": None,
            "message": f"Run not found: {run_id}",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"run": run_to_dict(run)}, indent=2, sort_keys=True))
    return 0


def _cmd_run_latest(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        run = get_latest_run(connection)
    if run is None:
        payload = {
            "run": None,
            "message": "No run exists.",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"run": run_to_dict(run)}, indent=2, sort_keys=True))
    return 0


def _cmd_model_driver_demo(config: AbiConfig, mode: str) -> int:
    result = run_model_driver_demo(config, mode=mode)
    print(json.dumps(result.to_cli_summary(), indent=2, sort_keys=True))
    return 0 if result.accepted else 1


def _cmd_model_driver_live_demo(
    config: AbiConfig,
    *,
    worker: str,
    allow_live_model: bool,
) -> int:
    result = run_live_abi_ear_worker(
        config,
        worker=worker,
        allow_live_model=allow_live_model,
    )
    print(json.dumps(result.payload, indent=2, sort_keys=True))
    return result.exit_code


def _cmd_model_call_list(config: AbiConfig) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        records = list_model_calls(connection)
    payload = {"model_calls": [model_call_to_dict(record) for record in records]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_model_call_show(config: AbiConfig, model_call_id: str) -> int:
    initialize_database(config)
    with connect(config.db_path) as connection:
        record = get_model_call(connection, model_call_id)
    if record is None:
        payload = {
            "model_call": None,
            "message": f"Model call not found: {model_call_id}",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"model_call": model_call_to_dict(record)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
