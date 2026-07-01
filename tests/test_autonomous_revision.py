import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

import abi.modules.ablation_informed_revision as ablation_informed_revision_module
import abi.modules.autonomous_revision as autonomous_revision_module
import abi.modules.residual_targets as residual_targets_module
from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.policy import GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
from abi.controller.state import AUTONOMOUS_CLOSED_LOOP_REVISION_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.hashing import sha256_text
from abi.model_calls import MODEL_CALL_SUCCESS, MODEL_CALL_VALIDATION_FAILED, list_model_calls
from abi.model_driver import WorkerRequest
from abi.model_schemas import (
    ABLATION_INFORMED_BASE_SELECTION_SCHEMA,
    ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA,
    ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA,
    AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA,
    AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA,
    AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA,
    EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_JUDGMENT_KEYS,
    AUTONOMOUS_REVISION_MODEL_SCHEMAS,
    AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS,
    AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA,
    BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
    OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA,
    RESIDUAL_INTERVENTION_GENERATION_SCHEMA,
    ModelValidationError,
    WorkerRole,
    json_schema_for_worker_schema,
    parse_and_validate_structured_output,
)
from abi.openai_adapter import openai_response_format_for_request
from abi.loop_integrity import (
    build_proof_before_next_generation_guard,
    build_repeated_target_drift_guard,
    detect_stale_recommendations,
)
from abi.modules.autonomous_revision import (
    AUTONOMOUS_REVISION_ARTIFACT_TYPES,
    AUTONOMOUS_REVISION_ALLOWED_ABLATION_PROBE_IDS,
    AUTONOMOUS_REVISION_ALLOWED_ABLATION_VARIANT_IDS,
    AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE,
    FakeAutonomousRevisionModelClient,
    RevisionIntegrityError,
    _load_revision_subject,
    _validate_revision_work_order_payload,
    run_autonomous_revision,
)
from abi.modules.autonomous_evidence_synthesis import (
    AUTONOMOUS_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES,
    _classify_failed_ending_return_attempt,
    run_autonomous_evidence_synthesis,
)
from abi.modules.bounded_macro_recomposition import (
    ACTIVE_TRANSFORMATION_TARGET_IDS,
    BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES,
    READER_STATE_MACRO_2_ACTIVE_TARGET_IDS,
    READER_STATE_MACRO_2_MATERIAL_REQUIRED_TARGET_IDS,
    READER_STATE_MACRO_2_TARGET_SCOPE,
    REQUIRED_SEMANTIC_CONSTRAINT_IDS,
    _build_target_assignment_consistency_report,
    run_bounded_macro_recomposition,
)
from abi.modules.ablation_informed_revision import (
    ABLATION_INFORMED_REVISION_ARTIFACT_TYPES,
    BASE_CHOICE_CONTROLLER_COMPOSED,
    BASE_CHOICE_DOMINANT_VARIANT,
    BASE_CHOICE_ORIGINAL,
    BASE_CHOICE_PACKET_0030,
    BASE_CHOICE_SOURCE_REVISION_CURRENT,
    HANDLE_RECORD_COMPRESSION,
    PIVOT_REPAIR_PRESERVING_BASE_CHOICES,
    RESIDUAL_BLOCKER_CANDIDATES,
    run_ablation_informed_revision,
)
from abi.modules.executed_ablation import (
    EXECUTED_ABLATION_ARTIFACT_TYPES,
    REVISION_PACKET_KIND_ABLATION_INFORMED,
    REVISION_PACKET_KIND_AUTONOMOUS,
    REVISION_PACKET_KIND_BOUNDED_MACRO,
    _build_comparison_consistency_report,
    _build_tactile_causal_effect_report,
    _load_subject,
    run_executed_ablation,
)
from abi.modules.evidence_loop_review import (
    EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES,
    run_evidence_loop_review,
)
from abi.modules.loop_integrity_cleanup import (
    LOOP_INTEGRITY_CLEANUP_ARTIFACT_TYPES,
    run_loop_integrity_cleanup,
)
from abi.modules.internal_reader_lab import FakeInternalReaderLabModelClient, run_internal_reader_lab
from abi.modules.internal_reader_state_evaluation import run_internal_reader_state_evaluation
from abi.modules.next_target_strategy import (
    NEXT_TARGET_STRATEGY_ARTIFACT_TYPES,
    run_next_target_strategy,
)
from abi.modules.object_event_recomposition import (
    OBJECT_EVENT_RECOMPOSITION_ARTIFACT_TYPES,
    OBJECT_EVENT_TARGET_SCOPE,
    run_object_event_recomposition,
)
from abi.modules.residual_target_selection import (
    NEXT_ALLOWED_ACTION,
    OBJECT_MOTION_CAUSALITY_TARGET_ID,
    RESIDUAL_TARGET_SELECTION_ARTIFACT_TYPES,
    run_residual_target_selection,
)
from abi.modules.residual_targets import (
    ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
    ENDING_RETURN_GENERATION_CONTRACT_VERSION,
    ENDING_RETURN_MATERIALITY_POLICY_ID,
    ENDING_RETURN_PLACEHOLDER_GENERATION_CONTRACT_VERSION,
    ENDING_RETURN_PLACEHOLDER_MATERIALITY_POLICY_ID,
    ENDING_RETURN_REGION_ID,
    ENDING_RETURN_SEMANTIC_VALIDATOR_ID,
    ENDING_RETURN_WORK_ORDER_CONTRACT_VERSION,
    HOSTILE_SCAFFOLD_GENERATION_CONTRACT_VERSION,
    HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID,
    HOSTILE_SCAFFOLD_PLACEHOLDER_MATERIALITY_POLICY_ID,
    HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
    HOSTILE_SCAFFOLD_WORK_ORDER_CONTRACT_VERSION,
    OBJECT_MOTION_GENERATION_CONTRACT_VERSION,
    OBJECT_MOTION_WORK_ORDER_CONTRACT_VERSION,
    TACTILE_GENERATION_CONTRACT_VERSION,
    TACTILE_INEVITABILITY_TARGET_ID,
    TACTILE_WORK_ORDER_CONTRACT_VERSION,
    ending_return_reset_diagnostic,
    payload_has_placeholder_generation_contract,
    require_residual_target_adapter,
    semantic_preflight_failures_for_work_order,
    target_generation_readiness_failures,
)
from abi.modules.residual_generation_authorization import (
    AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    NEXT_RECOMMENDED_ACTION as RESIDUAL_GENERATION_AUTHORIZATION_NEXT_ACTION,
    RESIDUAL_GENERATION_AUTHORIZATION_ARTIFACT_TYPES,
    run_residual_generation_authorization,
)
from abi.modules.residual_candidate_generation import (
    BOUNDED_MACRO_COMPATIBLE_ARTIFACT_TYPES as RESIDUAL_CANDIDATE_ARTIFACT_TYPES,
    FakeObjectMotionCausalityModelClient,
    REQUIRED_CHANGED_RATIO,
    REQUIRED_CHANGED_UNIQUE_WORD_COUNT,
    run_residual_candidate_generation,
)
from abi.modules.residual_work_order import (
    NEXT_RECOMMENDED_ACTION as RESIDUAL_WORK_ORDER_NEXT_RECOMMENDED_ACTION,
    RESIDUAL_WORK_ORDER_ARTIFACT_TYPES,
    SELECTED_REGION_ID as RESIDUAL_WORK_ORDER_SELECTED_REGION_ID,
    run_residual_work_order_planning,
)
from abi.modules.pilot_artifact_set import import_pilot_rival, run_pilot_artifact_set
from abi.modules.supervised_cycle_authorization import (
    SUPERVISED_CYCLE_AUTHORIZATION_ARTIFACT_TYPES,
    run_supervised_cycle_authorization,
)


SOURCE_NOTE = """# Source Note

The table remains visible while the room withholds what happened overnight.
"""

THEORY_FRAGMENT = """# Theory Fragment

The opening must return changed without announcing its own machinery.
"""


def config_for(tmp_path: Path) -> AbiConfig:
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def write_sources(root: Path) -> Path:
    source_dir = root / "fixtures" / "production_harness"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "source_note.md").write_text(SOURCE_NOTE, encoding="utf-8", newline="\n")
    (source_dir / "theory_fragment.md").write_text(
        THEORY_FRAGMENT,
        encoding="utf-8",
        newline="\n",
    )
    return source_dir


def read_payload(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["payload"]


def candidate_text_from_reader_lab_packet(packet_dir: str | Path) -> str:
    packet = read_payload(str(Path(packet_dir) / "internal_reader_lab_packet.json"))
    source_packet_dir = Path(str(packet["source_packet_dir"]))
    bundle = read_payload(str(source_packet_dir / "pilot_blinded_reader_bundle.json"))
    private_map = read_payload(str(source_packet_dir / "pilot_neutral_label_map_private.json"))[
        "label_map"
    ]
    for item in bundle["reader_items"]:
        label = item["label"]
        if private_map[label]["source_class"] == "abi_candidate":
            return str(item["text"])
    raise AssertionError("Abi candidate text not found in source packet")


def revision_subject_from_reader_lab_packet(config: AbiConfig, packet_dir: str | Path):
    with connect(config.db_path) as connection:
        return _load_revision_subject(connection, Path(packet_dir))


def build_reader_lab_packet(
    tmp_path: Path,
    *,
    with_rival: bool = False,
) -> tuple[AbiConfig, dict[str, object]]:
    config = config_for(tmp_path)
    pilot = run_pilot_artifact_set(
        config,
        client_name="fake",
        source_dir=write_sources(tmp_path),
    )
    assert pilot.exit_code == 0
    packet_dir = pilot.payload["packet_dir"]
    if with_rival:
        rival_dir = tmp_path / "inputs" / "private" / "pilot_001"
        rival_dir.mkdir(parents=True)
        rival_file = rival_dir / "strongest_rival_text_d.md"
        rival_file.write_text(
            "The table stood where the morning left it, colder than the room expected.",
            encoding="utf-8",
            newline="\n",
        )
        imported = import_pilot_rival(
            config,
            packet_dir=packet_dir,
            rival_file=rival_file,
        )
        assert imported.exit_code == 0
        packet_dir = imported.payload["packet_dir"]

    lab = run_internal_reader_lab(config, client_name="fake", packet_dir=packet_dir)
    assert lab.exit_code == 0
    return config, lab.payload


def build_live_style_reader_lab_packet(tmp_path: Path) -> tuple[AbiConfig, dict[str, object]]:
    config = config_for(tmp_path)
    pilot = run_pilot_artifact_set(
        config,
        client_name="fake",
        source_dir=write_sources(tmp_path),
    )
    assert pilot.exit_code == 0
    rival_dir = tmp_path / "inputs" / "private" / "pilot_001"
    rival_dir.mkdir(parents=True)
    rival_file = rival_dir / "strongest_rival_text_d.md"
    rival_file.write_text(
        "The table stood where the morning left it, colder than the room expected.",
        encoding="utf-8",
        newline="\n",
    )
    imported = import_pilot_rival(
        config,
        packet_dir=pilot.payload["packet_dir"],
        rival_file=rival_file,
    )
    assert imported.exit_code == 0

    def _factory(model: str) -> FakeInternalReaderLabModelClient:
        return FakeInternalReaderLabModelClient(provider="openai", model=model)

    lab = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=imported.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-internal-reader-model",
        client_factory=_factory,
    )
    assert lab.exit_code == 0
    assert lab.payload["counts"]["model_calls"] == 9
    return config, lab.payload


def build_fake_revision_packet(tmp_path: Path, *, with_rival: bool = True):
    config, lab_payload = build_reader_lab_packet(tmp_path, with_rival=with_rival)
    revision = run_autonomous_revision(
        config,
        client_name="fake",
        reader_lab_packet=lab_payload["packet_dir"],
    )
    assert revision.exit_code == 0
    assert revision.payload["accepted"] is True
    return config, revision.payload


def build_fake_executed_ablation_packet(tmp_path: Path):
    config, revision_payload = build_fake_revision_packet(tmp_path, with_rival=True)
    ablation = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=revision_payload["packet_dir"],
    )
    assert ablation.exit_code == 0
    assert ablation.payload["accepted"] is True
    return config, ablation.payload


def build_fake_ablation_informed_revision_packet(tmp_path: Path):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    revision = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )
    assert revision.exit_code == 0
    assert revision.payload["accepted"] is True
    return config, revision.payload


def build_fake_executed_ablation_from_ablation_informed_packet(tmp_path: Path):
    config, revision_payload = build_fake_ablation_informed_revision_packet(tmp_path)
    ablation = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=revision_payload["packet_dir"],
    )
    assert ablation.exit_code == 0
    assert ablation.payload["accepted"] is True
    assert ablation.payload["revision_packet_kind"] == "ablation_informed_revision"
    return config, ablation.payload, revision_payload


def build_pivot_required_executed_ablation_packet(tmp_path: Path):
    config, ablation_payload, revision_payload = (
        build_fake_executed_ablation_from_ablation_informed_packet(tmp_path)
    )

    def _make_causal_report_useful_but_exhausted(payload):
        payload["selected_repair_causal_status"] = "useful_but_insufficient"
        payload["selected_repair_appears_causal"] = True
        payload["strongest_rival_pressure_remains_blocking"] = True
        payload["recommended_next_action"] = (
            "preserve useful local repair and run a separate revision cycle "
            "for remaining blockers"
        )

    def _make_old_new_support_pivot(payload):
        payload["repair_has_causal_support"] = True
        payload["revert_performs_same_or_better"] = False
        payload["record_compression_improves_discovery"] = False
        payload["strongest_rival_still_beats_candidate"] = True

    rewrite_payload(
        ablation_payload["artifact_paths"]["ablation_causal_effect_report"],
        _make_causal_report_useful_but_exhausted,
    )
    rewrite_payload(
        ablation_payload["artifact_paths"]["ablation_old_new_rival_comparison"],
        _make_old_new_support_pivot,
    )
    return config, ablation_payload, revision_payload


def build_fake_evidence_synthesis_chain(tmp_path: Path):
    config, ablation_payload, revision_payload = build_pivot_required_executed_ablation_packet(
        tmp_path
    )
    pivot_revision = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )
    assert pivot_revision.exit_code == 0
    assert pivot_revision.payload["accepted"] is True
    failed_ablation = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=pivot_revision.payload["packet_dir"],
    )
    assert failed_ablation.exit_code == 0
    assert failed_ablation.payload["accepted"] is True

    def _make_pivot_causal_report_failed(payload):
        payload["selected_repair_causal_status"] = "noncausal_or_cosmetic"
        payload["selected_repair_appears_causal"] = False
        payload["strongest_rival_pressure_remains_blocking"] = True
        payload["recommended_next_action"] = (
            "consider reverting the patch or attacking a different causal handle"
        )

    def _make_pivot_comparison_failed(payload):
        payload["repair_has_causal_support"] = False
        payload["revert_performs_same_or_better"] = True
        payload["record_compression_improves_discovery"] = False
        payload["strongest_rival_still_beats_candidate"] = True

    def _make_pivot_packet_failed(payload):
        payload["selected_repair_causal_status"] = "noncausal_or_cosmetic"

    rewrite_payload(
        failed_ablation.payload["artifact_paths"]["ablation_causal_effect_report"],
        _make_pivot_causal_report_failed,
    )
    rewrite_payload(
        failed_ablation.payload["artifact_paths"]["ablation_old_new_rival_comparison"],
        _make_pivot_comparison_failed,
    )
    rewrite_payload(
        failed_ablation.payload["artifact_paths"]["executed_ablation_packet"],
        _make_pivot_packet_failed,
    )
    return config, failed_ablation.payload, pivot_revision.payload, revision_payload


def build_fake_bounded_macro_recomposition_packet(tmp_path: Path):
    config, _failed_ablation, _pivot_revision, _revision_payload = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    macro = run_bounded_macro_recomposition(
        config,
        client_name="fake",
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )
    assert macro.exit_code == 0
    assert macro.payload["accepted"] is True
    return config, macro.payload


def build_fake_macro_evidence_synthesis_chain(tmp_path: Path):
    config, failed_ablation, pivot_revision, _revision_payload = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    macro = run_bounded_macro_recomposition(
        config,
        client_name="fake",
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )
    assert macro.exit_code == 0
    ablation = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=macro.payload["packet_dir"],
    )
    assert ablation.exit_code == 0

    def _make_macro_causal_report_useful(payload):
        payload["selected_repair_causal_status"] = "useful_but_insufficient"
        payload["selected_repair_appears_causal"] = True
        payload["reduced_overexplanation"] = True
        payload["damaged_local_embodiment"] = False
        payload["strongest_rival_pressure_remains_blocking"] = True
        payload["recommended_next_action"] = (
            "preserve useful local repair and run a separate revision cycle "
            "for remaining blockers"
        )

    def _make_macro_comparison_useful(payload):
        payload["repair_has_causal_support"] = True
        payload["revert_performs_same_or_better"] = False
        payload["reverting_patch_weakens_candidate"] = True
        payload["record_compression_improves_discovery"] = False
        payload["strongest_rival_still_beats_candidate"] = True

    def _make_macro_packet_useful(payload):
        payload["selected_repair_causal_status"] = "useful_but_insufficient"
        payload["comparison_internal_consistency"] = True

    rewrite_payload(
        ablation.payload["artifact_paths"]["ablation_causal_effect_report"],
        _make_macro_causal_report_useful,
    )
    rewrite_payload(
        ablation.payload["artifact_paths"]["ablation_old_new_rival_comparison"],
        _make_macro_comparison_useful,
    )
    rewrite_payload(
        ablation.payload["artifact_paths"]["executed_ablation_packet"],
        _make_macro_packet_useful,
    )
    return config, failed_ablation, pivot_revision, macro.payload, ablation.payload


def build_reader_state_macro_synthesis_chain(tmp_path: Path):
    config, failed_ablation, pivot_revision, macro_payload, macro_ablation = (
        build_fake_macro_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    macro_synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert macro_synthesis.exit_code == 0

    def _reader_state_client_factory(model: str) -> FakeInternalReaderLabModelClient:
        return FakeInternalReaderLabModelClient(provider="openai", model=model)

    reader_state = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=macro_synthesis.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-reader-state-model",
        client_factory=_reader_state_client_factory,
    )
    assert reader_state.exit_code == 0
    assert reader_state.payload["accepted"] is True
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    return {
        "config": config,
        "run_id": run_id,
        "failed_ablation": failed_ablation,
        "pivot_revision": pivot_revision,
        "macro_payload": macro_payload,
        "macro_ablation": macro_ablation,
        "reader_state": reader_state.payload,
        "synthesis": synthesis.payload,
    }


def build_live_macro2_candidate_with_optional_proof(
    tmp_path: Path,
    *,
    proof_mode: str | None = "useful",
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    macro2 = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([]),
    )
    assert macro2.exit_code == 0
    assert macro2.payload["accepted"] is True
    assert macro2.payload["target_scope"] == READER_STATE_MACRO_2_TARGET_SCOPE
    proof_payload = None
    if proof_mode is not None:
        proof = run_executed_ablation(
            chain["config"],
            client_name="openai",
            revision_packet=macro2.payload["packet_dir"],
            allow_live_model=True,
            api_key="stub-key",
            model="stub-executed-ablation",
            client_factory=executed_ablation_stub_factory([]),
        )
        assert proof.exit_code == 0
        assert proof.payload["accepted"] is True
        proof_payload = proof.payload
        _rewrite_macro2_proof(proof_payload, useful=proof_mode == "useful")
    chain["macro2"] = macro2.payload
    chain["macro2_proof"] = proof_payload
    return chain


def build_live_macro2_candidate_with_reader_state(
    tmp_path: Path,
    *,
    strip_reader_identity_to_hash_only: bool = False,
):
    chain = build_live_macro2_candidate_with_optional_proof(tmp_path, proof_mode="useful")
    synthesis = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])
    assert synthesis.exit_code == 0
    assert synthesis.payload["best_current_candidate"]["packet_id"] == chain["macro2"]["packet_id"]

    def _reader_state_client_factory(model: str) -> FakeInternalReaderLabModelClient:
        return FakeInternalReaderLabModelClient(provider="openai", model=model)

    reader_state = run_internal_reader_state_evaluation(
        chain["config"],
        client_name="openai",
        synthesis_packet=synthesis.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-reader-state-model",
        client_factory=_reader_state_client_factory,
    )
    assert reader_state.exit_code == 0
    assert reader_state.payload["accepted"] is True
    assert reader_state.payload["selected_candidate_packet_id"] == chain["macro2"]["packet_id"]
    macro2_candidate = read_payload(
        Path(str(chain["macro2"]["packet_dir"])) / "macro_recomposed_candidate_text.json"
    )
    reader_packet_dir = Path(str(reader_state.payload["packet_dir"]))
    reader_packet = read_payload(reader_packet_dir / "internal_reader_state_eval_packet.json")
    chain["macro2_candidate_text_sha256"] = macro2_candidate["text_sha256"]
    assert reader_packet["selected_candidate_text_sha256"] == macro2_candidate["text_sha256"]

    def _make_macro2_reread(payload):
        payload["opening_becomes_more_necessary_after_return"] = True
        payload["ending_changes_opening"] = False

    def _make_macro2_opening(payload):
        payload["opening_return_transformation_strength"] = "partial"
        payload["ending_changes_opening"] = False

    def _make_macro2_rival(payload):
        payload["strongest_rival_still_blocks"] = True
        payload["macro_candidate_narrowed_rival_gap"] = True
        payload["rival_still_wins_on_first_read_vividness"] = True
        payload["rival_still_wins_on_lived_object_event_pressure"] = True

    rewrite_payload(reader_packet_dir / "reread_reader_state_trace.json", _make_macro2_reread)
    rewrite_payload(
        reader_packet_dir / "opening_return_transformation_report.json",
        _make_macro2_opening,
    )
    rewrite_payload(reader_packet_dir / "rival_reader_state_comparison.json", _make_macro2_rival)
    if strip_reader_identity_to_hash_only:
        def _strip_identity(payload):
            payload["source_synthesis_packet_id"] = "packet_stale_source_for_hash_link_test"
            payload["selected_candidate_packet_id"] = ""
            payload["selected_candidate_packet_dir"] = ""

        rewrite_payload(reader_packet_dir / "internal_reader_state_eval_packet.json", _strip_identity)
        rewrite_payload(
            reader_packet_dir / "internal_reader_state_eval_subject_manifest.json",
            _strip_identity,
        )
    chain["macro2_synthesis"] = synthesis.payload
    chain["macro2_reader_state"] = reader_state.payload
    return chain


def build_next_target_strategy_ready_chain(tmp_path: Path):
    chain = build_live_macro2_candidate_with_reader_state(tmp_path)
    synthesis = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])
    assert synthesis.exit_code == 0
    assert synthesis.payload["accepted"] is True
    assert synthesis.payload["best_current_candidate"]["packet_id"] == chain["macro2"][
        "packet_id"
    ]
    assert synthesis.payload["best_current_candidate"]["reader_state_evaluated"] is True
    chain["strategy_synthesis"] = synthesis.payload
    return chain


def build_authorized_next_target_strategy_chain(tmp_path: Path):
    chain = build_object_event_candidate_with_reader_state(tmp_path)
    config = chain["config"]
    synthesis = run_autonomous_evidence_synthesis(config, run_id=chain["run_id"])
    assert synthesis.exit_code == 0
    assert synthesis.payload["accepted"] is True
    assert synthesis.payload["best_current_candidate"]["packet_id"] == chain["object_event"][
        "packet_id"
    ]
    loop_review = run_evidence_loop_review(
        config,
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )
    assert loop_review.exit_code == 0
    authorization = run_supervised_cycle_authorization(
        config,
        loop_review_packet=Path(str(loop_review.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )
    assert authorization.exit_code == 0
    assert authorization.payload["next_strategy_authorized"] is True
    assert authorization.payload["next_generation_authorized"] is False
    chain["authorized_synthesis"] = synthesis.payload
    chain["loop_review"] = loop_review.payload
    chain["cycle_authorization"] = authorization.payload
    return chain


def build_residual_target_selection_ready_chain(tmp_path: Path):
    chain = build_authorized_next_target_strategy_chain(tmp_path)
    strategy = run_next_target_strategy(
        chain["config"],
        authorization_packet=Path(str(chain["cycle_authorization"]["packet_dir"])),
    )
    assert strategy.exit_code == 0
    assert strategy.payload["accepted"] is True
    assert strategy.payload["primary_next_target"] == (
        "next_residual_target_requires_operator_choice"
    )
    chain["selection_strategy"] = strategy.payload
    return chain


def build_residual_work_order_ready_chain(tmp_path: Path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=OBJECT_MOTION_CAUSALITY_TARGET_ID,
        operator_reviewed=True,
    )
    assert selection.exit_code == 0
    assert selection.payload["accepted"] is True
    assert selection.payload["next_strategy_or_work_order_authorized"] is True
    assert selection.payload["candidate_generation_authorized"] is False
    chain["residual_target_selection"] = selection.payload
    return chain


def build_residual_generation_authorization_ready_chain(tmp_path: Path):
    chain = build_residual_work_order_ready_chain(tmp_path)
    work_order = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(chain["residual_target_selection"]["packet_dir"])),
    )
    assert work_order.exit_code == 0
    assert work_order.payload["accepted"] is True
    assert work_order.payload["candidate_generation_authorized"] is False
    assert work_order.payload["candidate_generated"] is False
    chain["residual_work_order"] = work_order.payload
    return chain


def build_residual_candidate_authorization_chain(
    tmp_path: Path,
    *,
    fixture_only: bool = False,
):
    chain = build_residual_generation_authorization_ready_chain(tmp_path)
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    assert authorization.payload["accepted"] is True
    packet_dir = Path(str(authorization.payload["packet_dir"]))
    if fixture_only:
        mark_packet_fixture_only(packet_dir)
    chain["residual_generation_authorization"] = authorization.payload
    return chain


def build_tactile_residual_work_order_chain(tmp_path: Path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=TACTILE_INEVITABILITY_TARGET_ID,
        operator_reviewed=True,
    )
    assert selection.exit_code == 0
    work_order = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )
    assert work_order.exit_code == 0
    chain["residual_target_selection"] = selection.payload
    chain["residual_work_order"] = work_order.payload
    return chain


def build_tactile_residual_candidate_authorization_chain(
    tmp_path: Path,
    *,
    fixture_only: bool = False,
):
    chain = build_tactile_residual_work_order_chain(tmp_path)
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    assert authorization.payload["accepted"] is True
    packet_dir = Path(str(authorization.payload["packet_dir"]))
    if fixture_only:
        mark_packet_fixture_only(packet_dir)
    chain["residual_generation_authorization"] = authorization.payload
    return chain


def build_hostile_scaffold_residual_work_order_chain(tmp_path: Path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        operator_reviewed=True,
    )
    assert selection.exit_code == 0
    work_order = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )
    assert work_order.exit_code == 0
    chain["residual_target_selection"] = selection.payload
    chain["residual_work_order"] = work_order.payload
    return chain


def build_ending_return_residual_work_order_chain(tmp_path: Path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
        operator_reviewed=True,
    )
    assert selection.exit_code == 0
    work_order = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )
    assert work_order.exit_code == 0
    chain["residual_target_selection"] = selection.payload
    chain["residual_work_order"] = work_order.payload
    return chain


PACKET_0064_SOURCE_REGION_FIXTURE = (
    "A room like this teaches by repetition. When a cup is set down and "
    "lifted again, the ring tightens where the lip meets the wood, and "
    "the crumb is taken into the table's grain; the change is there before "
    "anyone names it. Morning does not wipe that away. Dust gathers where "
    "hand, foot, and air have pressed the same surface, and the spoon lies "
    "where a hand released it beside the saucer whose break the fall made "
    "visible. The world holds these crossings in place and makes them "
    "matter.\n\n"
    "At first, the table seems only ordinary. But ordinary things are "
    "strict about what reaches them. The ring keeps the trace of the glass "
    "because the pressure stays in the wood, the dust marks a passage "
    "through the window crack because the air and touch have already crossed "
    "it, the spoon lies where a hand released it too quickly, and the saucer "
    "shows the break that the fall made visible. Each object stays itself by "
    "carrying the force that brought it there. The kitchen is small, but it "
    "makes one rule plain: one thing enters another, leaves a mark, and that "
    "mark changes how the next thing is read."
)


def _apply_packet_0064_hostile_unit_fixture(work_order_packet: Path) -> None:
    region_sha = sha256_text(PACKET_0064_SOURCE_REGION_FIXTURE)
    base_text = (
        "The room begins with the table still in the morning light.\n\n"
        f"{PACKET_0064_SOURCE_REGION_FIXTURE}\n\n"
        "The return remains protected after the selected region."
    )
    base_sha = sha256_text(base_text)
    unit_specs = [
        (
            "trace_before_naming_scaffold_reduction",
            "the change is there before anyone names it.",
            ["cup", "ring", "crumb", "trace"],
        ),
        (
            "crossings_matter_without_thesis_pressure",
            "The world holds these crossings in place and makes them matter.",
            ["dust", "hand", "foot", "air", "surface"],
        ),
        (
            "ordinary_table_no_scaffold_signage",
            "At first, the table seems only ordinary.",
            ["table", "ordinary", "first"],
        ),
        (
            "ordinary_things_strict_without_abstraction",
            "But ordinary things are strict about what reaches them.",
            ["ordinary", "things", "strict", "reaches"],
        ),
        (
            "small_kitchen_rule_plainness_reduction",
            (
                "The kitchen is small, but it makes one rule plain: one thing "
                "enters another, leaves a mark, and that mark changes how the "
                "next thing is read."
            ),
            ["kitchen", "small", "mark", "read"],
        ),
    ]

    def _region(payload):
        payload["selected_region_before_text"] = PACKET_0064_SOURCE_REGION_FIXTURE
        payload["selected_region_sha256"] = region_sha

    def _packet(payload):
        payload["selected_region_sha256"] = region_sha

    def _unit_map(payload):
        payload["target_unit_count"] = len(unit_specs)
        payload["target_unit_ids"] = [unit_id for unit_id, _text, _objects in unit_specs]
        units = payload["target_units"]
        by_id = {unit["unit_id"]: unit for unit in units}
        for unit_id, before_text, objects in unit_specs:
            unit = by_id[unit_id]
            char_start = PACKET_0064_SOURCE_REGION_FIXTURE.index(before_text)
            unit["before_text"] = before_text
            unit["before_text_sha256"] = sha256_text(before_text)
            unit["objects"] = list(objects)
            unit["involved_object_labels"] = list(objects)
            unit["source_span"] = {
                "before_text_sha256": unit["before_text_sha256"],
                "char_start": char_start,
                "char_end": char_start + len(before_text),
                "contained_in_selected_region": True,
                "region_id": RESIDUAL_WORK_ORDER_SELECTED_REGION_ID,
            }

    rewrite_payload(work_order_packet / "selected_intervention_region.json", _region)
    rewrite_payload(work_order_packet / "residual_work_order_packet.json", _packet)
    rewrite_payload(work_order_packet / "future_generation_contract.json", _packet)
    rewrite_payload(work_order_packet / "object_motion_target_unit_map.json", _unit_map)
    manifest = read_payload(work_order_packet / "residual_work_order_subject_manifest.json")
    base_packet_dir = Path(str(manifest["current_best_candidate_packet_dir"]))

    def _candidate(payload):
        payload["text"] = base_text
        payload["text_sha256"] = base_sha
        payload["word_count"] = len(base_text.split())

    rewrite_payload(base_packet_dir / "macro_recomposed_candidate_text.json", _candidate)


def build_hostile_scaffold_residual_candidate_authorization_chain(
    tmp_path: Path,
    *,
    fixture_only: bool = False,
    packet_0064_unit_fixture: bool = False,
):
    chain = build_hostile_scaffold_residual_work_order_chain(tmp_path)
    if packet_0064_unit_fixture:
        _apply_packet_0064_hostile_unit_fixture(
            Path(str(chain["residual_work_order"]["packet_dir"]))
        )
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    assert authorization.payload["accepted"] is True
    packet_dir = Path(str(authorization.payload["packet_dir"]))
    if fixture_only:
        mark_packet_fixture_only(packet_dir)
    chain["residual_generation_authorization"] = authorization.payload
    return chain


def build_fake_tactile_residual_candidate_packet(tmp_path: Path):
    chain = build_tactile_residual_candidate_authorization_chain(
        tmp_path,
        fixture_only=True,
    )
    residual = run_residual_candidate_generation(
        chain["config"],
        client_name="fake",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
    )
    assert residual.exit_code == 0
    assert residual.payload["accepted"] is True
    assert residual.payload["target_adapter_id"] == "tactile_inevitability"
    return chain["config"], residual.payload


def build_completed_residual_loop_review_chain(tmp_path: Path):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    config = chain["config"]
    run_id = chain["run_id"]

    residual = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory([]),
    )
    assert residual.exit_code == 0
    assert residual.payload["accepted"] is True

    proof = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation-model",
        client_factory=executed_ablation_stub_factory([]),
    )
    assert proof.exit_code == 0
    assert proof.payload["accepted"] is True
    _rewrite_macro2_proof(proof.payload, useful=True)

    pre_reader_synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert pre_reader_synthesis.exit_code == 0
    assert pre_reader_synthesis.payload["accepted"] is True

    def _reader_state_client_factory(model: str) -> FakeInternalReaderLabModelClient:
        return FakeInternalReaderLabModelClient(provider="openai", model=model)

    reader_state = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=Path(str(pre_reader_synthesis.payload["packet_dir"])),
        target_candidate_packet=Path(str(residual.payload["packet_dir"])),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=5,
        model="stub-reader-state-model",
        client_factory=_reader_state_client_factory,
    )
    assert reader_state.exit_code == 0
    assert reader_state.payload["accepted"] is True

    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    assert synthesis.payload["accepted"] is True
    assert synthesis.payload["best_current_candidate"]["packet_id"] == residual.payload[
        "packet_id"
    ]

    loop_review = run_evidence_loop_review(
        config,
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )
    assert loop_review.exit_code == 0
    assert loop_review.payload["accepted"] is True

    chain["residual_candidate"] = residual.payload
    chain["residual_proof"] = proof.payload
    chain["residual_reader_state"] = reader_state.payload
    chain["residual_synthesis"] = synthesis.payload
    chain["residual_loop_review"] = loop_review.payload
    return chain


def build_completed_tactile_residual_loop_review_chain(tmp_path: Path):
    chain = build_tactile_residual_candidate_authorization_chain(tmp_path)
    config = chain["config"]
    run_id = chain["run_id"]

    residual = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=1,
        model="stub-tactile-model",
        client_factory=residual_intervention_stub_factory([]),
    )
    assert residual.exit_code == 0
    assert residual.payload["accepted"] is True

    generic_proof = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation",
        client_factory=executed_ablation_stub_factory([]),
    )
    assert generic_proof.exit_code == 0
    _rewrite_tactile_proof_as_generic_non_authoritative(generic_proof.payload)

    role_failed_proof = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation",
        client_factory=executed_ablation_stub_factory([]),
    )
    assert role_failed_proof.exit_code == 0
    _rewrite_tactile_proof_as_role_consistency_failed(role_failed_proof.payload)

    fixture_proof = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=residual.payload["packet_dir"],
    )
    assert fixture_proof.exit_code == 0

    authoritative_proof = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation",
        client_factory=executed_ablation_stub_factory([]),
    )
    assert authoritative_proof.exit_code == 0
    assert authoritative_proof.payload["accepted"] is True
    assert authoritative_proof.payload["target_aware_ablation"] is True
    assert authoritative_proof.payload["target_role_consistency_passed"] is True

    pre_reader_synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert pre_reader_synthesis.exit_code == 0
    assert pre_reader_synthesis.payload["accepted"] is True

    fixture_reader_state = run_internal_reader_state_evaluation(
        config,
        client_name="fake",
        synthesis_packet=Path(str(pre_reader_synthesis.payload["packet_dir"])),
        target_candidate_packet=Path(str(residual.payload["packet_dir"])),
    )
    assert fixture_reader_state.exit_code == 0
    assert fixture_reader_state.payload["accepted"] is True

    def _reader_state_client_factory(model: str) -> FakeInternalReaderLabModelClient:
        return FakeInternalReaderLabModelClient(provider="openai", model=model)

    reader_state = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=Path(str(pre_reader_synthesis.payload["packet_dir"])),
        target_candidate_packet=Path(str(residual.payload["packet_dir"])),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=5,
        model="stub-reader-state-model",
        client_factory=_reader_state_client_factory,
    )
    assert reader_state.exit_code == 0
    assert reader_state.payload["accepted"] is True

    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    assert synthesis.payload["accepted"] is True
    assert synthesis.payload["best_current_candidate"]["packet_id"] == residual.payload[
        "packet_id"
    ]
    assert synthesis.payload["best_current_candidate"]["proof_packet_id"] == (
        authoritative_proof.payload["packet_id"]
    )
    assert synthesis.payload["best_current_candidate"]["reader_state_packet_id"] == (
        reader_state.payload["packet_id"]
    )

    loop_review = run_evidence_loop_review(
        config,
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )
    assert loop_review.exit_code == 0
    assert loop_review.payload["accepted"] is True

    chain["residual_candidate"] = residual.payload
    chain["generic_proof"] = generic_proof.payload
    chain["role_failed_proof"] = role_failed_proof.payload
    chain["fixture_proof"] = fixture_proof.payload
    chain["residual_proof"] = authoritative_proof.payload
    chain["fixture_reader_state"] = fixture_reader_state.payload
    chain["residual_reader_state"] = reader_state.payload
    chain["residual_synthesis"] = synthesis.payload
    chain["residual_loop_review"] = loop_review.payload
    return chain


def retarget_cleanup_chain_to_proof(
    chain: dict[str, object],
    proof_payload: dict[str, object],
) -> None:
    proof_packet_id = str(proof_payload["packet_id"])
    proof_packet_dir = str(proof_payload["packet_dir"])
    synthesis_dir = Path(str(chain["residual_synthesis"]["packet_dir"]))
    loop_dir = Path(str(chain["residual_loop_review"]["packet_dir"]))
    reader_state_dir = Path(str(chain["residual_reader_state"]["packet_dir"]))

    def _update_best_candidate(candidate: dict[str, object]) -> None:
        candidate["proof_packet_id"] = proof_packet_id
        candidate["proof_packet_dir"] = proof_packet_dir

    def _update_synthesis_packet(payload: dict[str, object]) -> None:
        _update_best_candidate(payload["best_current_candidate"])

    def _update_best_selection(payload: dict[str, object]) -> None:
        _update_best_candidate(payload["selected_best_candidate"])

    def _update_graph(payload: dict[str, object]) -> None:
        for node in payload["nodes"]:
            if node["candidate_packet_id"] == chain["residual_candidate"]["packet_id"]:
                _update_best_candidate(node)

    def _update_adjudication(payload: dict[str, object]) -> None:
        payload["proof_packet_id"] = proof_packet_id

    def _update_reader_state(payload: dict[str, object]) -> None:
        payload["proof_packet_id"] = proof_packet_id

    def _update_loop_packet(payload: dict[str, object]) -> None:
        payload["proof_packet_id"] = proof_packet_id

    def _update_manifest(payload: dict[str, object]) -> None:
        payload["proof_packet_id"] = proof_packet_id
        payload["proof_packet_dir"] = proof_packet_dir

    def _update_cycle_map(payload: dict[str, object]) -> None:
        for cycle in payload["cycles"]:
            if cycle["candidate_packet_id"] == chain["residual_candidate"]["packet_id"]:
                cycle["proof_packet_id"] = proof_packet_id
                cycle["proof_packet_dir"] = proof_packet_dir

    rewrite_payload(
        synthesis_dir / "autonomous_evidence_synthesis_packet.json",
        _update_synthesis_packet,
    )
    rewrite_payload(
        synthesis_dir / "best_current_candidate_selection.json",
        _update_best_selection,
    )
    rewrite_payload(synthesis_dir / "candidate_evidence_graph.json", _update_graph)
    rewrite_payload(
        synthesis_dir / "residual_candidate_reader_state_adjudication.json",
        _update_adjudication,
    )
    rewrite_payload(
        reader_state_dir / "internal_reader_state_eval_packet.json",
        _update_reader_state,
    )
    rewrite_payload(loop_dir / "evidence_loop_review_packet.json", _update_loop_packet)
    rewrite_payload(
        loop_dir / "evidence_loop_review_subject_manifest.json",
        _update_manifest,
    )
    rewrite_payload(loop_dir / "completed_cycle_map.json", _update_cycle_map)


def build_completed_tactile_cleanup_chain(tmp_path: Path):
    chain = build_completed_tactile_residual_loop_review_chain(tmp_path)
    cleanup = run_loop_integrity_cleanup(
        chain["config"],
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )
    assert cleanup.exit_code == 0
    assert cleanup.payload["accepted"] is True
    chain["cleanup"] = cleanup.payload
    return chain


def build_object_event_strategy_chain(tmp_path: Path):
    chain = build_next_target_strategy_ready_chain(tmp_path)
    strategy = run_next_target_strategy(
        chain["config"],
        synthesis_packet=Path(str(chain["strategy_synthesis"]["packet_dir"])),
    )
    assert strategy.exit_code == 0
    assert strategy.payload["accepted"] is True
    assert strategy.payload["current_best_candidate_packet_id"] == chain["macro2"][
        "packet_id"
    ]
    chain["next_target_strategy"] = strategy.payload
    return chain


def build_object_event_candidate_with_optional_proof(
    tmp_path: Path,
    *,
    proof_mode: str | None = "useful",
    object_event_client: str = "openai",
):
    chain = build_object_event_strategy_chain(tmp_path)
    strategy_packet = Path(str(chain["next_target_strategy"]["packet_dir"]))
    if object_event_client == "openai":
        object_event = run_object_event_recomposition(
            chain["config"],
            client_name="openai",
            strategy_packet=strategy_packet,
            allow_live_model=True,
            api_key="stub-key",
            model="stub-object-event-model",
            client_factory=object_event_stub_factory([]),
        )
    else:
        object_event = run_object_event_recomposition(
            chain["config"],
            client_name="fake",
            strategy_packet=strategy_packet,
        )
    assert object_event.exit_code == 0
    assert object_event.payload["accepted"] is True
    assert object_event.payload["base_candidate_packet_id"] == chain["macro2"]["packet_id"]

    proof_payload = None
    if proof_mode is not None:
        proof_client = "openai" if object_event_client == "openai" else "fake"
        proof_kwargs = {
            "config": chain["config"],
            "client_name": proof_client,
            "revision_packet": object_event.payload["packet_dir"],
        }
        if proof_client == "openai":
            proof_kwargs.update(
                {
                    "allow_live_model": True,
                    "api_key": "stub-key",
                    "model": "stub-executed-ablation",
                    "client_factory": executed_ablation_stub_factory([]),
                }
            )
        proof = run_executed_ablation(**proof_kwargs)
        assert proof.exit_code == 0
        assert proof.payload["accepted"] is True
        proof_payload = proof.payload
        _rewrite_macro2_proof(proof_payload, useful=proof_mode == "useful")

    chain["object_event"] = object_event.payload
    chain["object_event_proof"] = proof_payload
    return chain


def build_object_event_candidate_with_reader_state(
    tmp_path: Path,
    *,
    strip_reader_identity_to_hash_only: bool = False,
):
    chain = build_object_event_candidate_with_optional_proof(
        tmp_path,
        proof_mode="useful",
        object_event_client="openai",
    )
    synthesis = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])
    assert synthesis.exit_code == 0
    assert synthesis.payload["best_current_candidate"]["packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert synthesis.payload["best_current_candidate"]["reader_state_evaluated"] is False

    def _reader_state_client_factory(model: str) -> FakeInternalReaderLabModelClient:
        return FakeInternalReaderLabModelClient(provider="openai", model=model)

    reader_state = run_internal_reader_state_evaluation(
        chain["config"],
        client_name="openai",
        synthesis_packet=synthesis.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-reader-state-model",
        client_factory=_reader_state_client_factory,
    )
    assert reader_state.exit_code == 0
    assert reader_state.payload["accepted"] is True
    assert reader_state.payload["selected_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    object_candidate = read_payload(
        Path(str(chain["object_event"]["packet_dir"])) / "macro_recomposed_candidate_text.json"
    )
    reader_packet_dir = Path(str(reader_state.payload["packet_dir"]))
    reader_packet = read_payload(reader_packet_dir / "internal_reader_state_eval_packet.json")
    chain["object_event_candidate_text_sha256"] = object_candidate["text_sha256"]
    assert reader_packet["selected_candidate_text_sha256"] == object_candidate["text_sha256"]

    def _make_object_event_first_pass(payload):
        payload["first_read_summary"] = (
            "The strongest effect is object-event pressure: table, dust, spoon, "
            "saucer, and ring begin to lean on one another before the explanation."
        )

    def _make_object_event_reread(payload):
        payload["opening_becomes_more_necessary_after_return"] = True
        payload["ending_changes_opening"] = False
        payload["return_without_regression"] = False
        payload["proof_no_outside_answer_logic"] = (
            "partly_structural_but_still_explicit"
        )
        payload["reread_summary"] = (
            "On reread, the object-event pressure is more coherent, but the "
            "return remains partial and the rival pressure is still active."
        )

    def _make_object_event_opening(payload):
        payload["opening_return_transformation_strength"] = "partial"
        payload["ending_changes_opening"] = False

    def _make_object_event_delta(payload):
        payload["post_reread_reader_state"] = "partial_opening_return_transformation"
        payload["reread_gain_estimate"] = "partial"
        payload["motifs_that_became_causal_after_reread"] = [
            "table",
            "dust",
            "spoon",
            "saucer",
            "ring",
        ]
        payload["selected_candidate_text_sha256"] = object_candidate["text_sha256"]

    def _make_object_event_rival(payload):
        payload["strongest_rival_still_blocks"] = True
        payload["macro_candidate_narrowed_rival_gap"] = True
        payload["rival_still_wins_on_first_read_vividness"] = True
        payload["rival_still_wins_on_lived_object_event_pressure"] = True

    def _make_object_event_hostile(payload):
        payload["blocking_or_active_risks"] = [
            "overexplanation",
            "thesis_replacing_artifact",
            "scaffold_leakage",
        ]

    rewrite_payload(
        reader_packet_dir / "first_pass_reader_state_trace.json",
        _make_object_event_first_pass,
    )
    rewrite_payload(reader_packet_dir / "reread_reader_state_trace.json", _make_object_event_reread)
    rewrite_payload(
        reader_packet_dir / "opening_return_transformation_report.json",
        _make_object_event_opening,
    )
    rewrite_payload(reader_packet_dir / "reader_delta_report.json", _make_object_event_delta)
    rewrite_payload(reader_packet_dir / "rival_reader_state_comparison.json", _make_object_event_rival)
    rewrite_payload(reader_packet_dir / "hostile_reader_state_report.json", _make_object_event_hostile)

    if strip_reader_identity_to_hash_only:

        def _strip_identity(payload):
            payload["source_synthesis_packet_id"] = "packet_stale_source_for_hash_link_test"
            payload["selected_candidate_packet_id"] = ""
            payload["selected_candidate_packet_dir"] = ""

        rewrite_payload(reader_packet_dir / "internal_reader_state_eval_packet.json", _strip_identity)
        rewrite_payload(
            reader_packet_dir / "internal_reader_state_eval_subject_manifest.json",
            _strip_identity,
        )

    chain["object_event_synthesis"] = synthesis.payload
    chain["object_event_reader_state"] = reader_state.payload
    return chain


def _rewrite_macro2_proof(proof_payload: dict[str, object], *, useful: bool) -> None:
    def _causal(payload):
        payload["selected_repair_causal_status"] = (
            "useful_but_insufficient" if useful else "noncausal_or_cosmetic"
        )
        payload["selected_repair_appears_causal"] = useful
        payload["reduced_overexplanation"] = useful
        payload["damaged_local_embodiment"] = False if useful else True
        payload["strongest_rival_pressure_remains_blocking"] = True
        payload["recommended_next_action"] = (
            "preserve useful local repair and run reader-state evaluation"
            if useful
            else "do not promote this repair"
        )

    def _comparison(payload):
        payload["repair_has_causal_support"] = useful
        payload["revert_performs_same_or_better"] = not useful
        payload["reverting_patch_weakens_candidate"] = useful
        payload["record_compression_improves_discovery"] = False
        payload["strongest_rival_still_beats_candidate"] = True

    def _packet(payload):
        payload["selected_repair_causal_status"] = (
            "useful_but_insufficient" if useful else "noncausal_or_cosmetic"
        )
        payload["comparison_internal_consistency"] = True
        gate_report = payload.get("gate_report", {})
        if isinstance(gate_report, dict):
            gate_report["actual_executed_ablation_evidence_exists"] = True
            gate_report["actual_ablation_comparison_exists"] = True
            gate_report["comparison_internal_consistency"] = True
            gate_report["countable_evidence_variant_count"] = 3

    def _gate(payload):
        payload["actual_executed_ablation_evidence_exists"] = True
        payload["actual_ablation_comparison_exists"] = True
        payload["comparison_internal_consistency"] = True
        payload["countable_evidence_variant_count"] = 3
        payload["rival_remains_blocking"] = True

    rewrite_payload(proof_payload["artifact_paths"]["ablation_causal_effect_report"], _causal)
    rewrite_payload(proof_payload["artifact_paths"]["ablation_old_new_rival_comparison"], _comparison)
    rewrite_payload(proof_payload["artifact_paths"]["executed_ablation_packet"], _packet)
    rewrite_payload(proof_payload["artifact_paths"]["executed_ablation_gate_report"], _gate)


def _rewrite_tactile_proof_as_generic_non_authoritative(
    proof_payload: dict[str, object],
) -> None:
    def _causal(payload):
        payload["target_aware_ablation"] = False
        payload["selected_repair_causal_status"] = "noncausal_or_cosmetic"
        payload["selected_repair_appears_causal"] = False
        payload["tactile_intervention_has_causal_support"] = False
        payload["tactile_force_contact_adds_value"] = False
        payload["object_motion_preserved_tactile_removed_performs_same_or_better"] = True
        payload["packet_0063_earns_reader_state_eval"] = False
        payload["candidate_earns_reader_state_eval"] = False
        payload["previous_generic_ablation_not_authoritative_for_target"] = True
        payload["supersedes_generic_ablation_for_target"] = False
        payload["strongest_rival_pressure_remains_blocking"] = True

    def _comparison(payload):
        payload["target_aware_ablation"] = False
        payload["repair_has_causal_support"] = False
        payload["tactile_intervention_has_causal_support"] = False
        payload["tactile_force_contact_adds_value"] = False
        payload["object_motion_preserved_tactile_removed_performs_same_or_better"] = True
        payload["revert_performs_same_or_better"] = True
        payload["reverting_patch_weakens_candidate"] = False
        payload["packet_0063_earns_reader_state_eval"] = False
        payload["strongest_rival_still_beats_candidate"] = True

    def _consistency(payload):
        payload["target_role_consistency_checked"] = False
        payload["target_role_consistency_passed"] = True
        payload["target_role_consistency_failures"] = []
        payload["comparison_internal_consistency"] = True

    def _packet(payload):
        payload["target_aware_ablation"] = False
        payload["selected_repair_causal_status"] = "noncausal_or_cosmetic"
        payload["comparison_internal_consistency"] = True
        payload["tactile_intervention_has_causal_support"] = False
        payload["target_role_consistency_checked"] = False
        payload["target_role_consistency_passed"] = True
        payload["previous_generic_ablation_not_authoritative_for_target"] = True
        payload["supersedes_generic_ablation_for_target"] = False
        gate_report = payload.get("gate_report", {})
        if isinstance(gate_report, dict):
            gate_report["target_aware_ablation"] = False
            gate_report["comparison_internal_consistency"] = True
            gate_report["target_role_consistency_checked"] = False
            gate_report["target_role_consistency_passed"] = True
            gate_report["previous_generic_ablation_not_authoritative_for_target"] = True
            gate_report["supersedes_generic_ablation_for_target"] = False

    def _gate(payload):
        payload["target_aware_ablation"] = False
        payload["comparison_internal_consistency"] = True
        payload["target_role_consistency_checked"] = False
        payload["target_role_consistency_passed"] = True
        payload["previous_generic_ablation_not_authoritative_for_target"] = True
        payload["supersedes_generic_ablation_for_target"] = False
        payload["rival_remains_blocking"] = True

    rewrite_payload(proof_payload["artifact_paths"]["ablation_causal_effect_report"], _causal)
    rewrite_payload(
        proof_payload["artifact_paths"]["ablation_old_new_rival_comparison"],
        _comparison,
    )
    rewrite_payload(proof_payload["artifact_paths"]["comparison_consistency_report"], _consistency)
    rewrite_payload(proof_payload["artifact_paths"]["executed_ablation_packet"], _packet)
    rewrite_payload(proof_payload["artifact_paths"]["executed_ablation_gate_report"], _gate)


def _rewrite_tactile_proof_as_role_consistency_failed(
    proof_payload: dict[str, object],
) -> None:
    failures = [
        "target-aware comparator row roles contradicted the target control operations"
    ]

    def _causal(payload):
        payload["selected_repair_causal_status"] = (
            "inconclusive_due_to_comparator_role_confusion"
        )
        payload["selected_repair_appears_causal"] = False
        payload["tactile_intervention_has_causal_support"] = False
        payload["tactile_force_contact_adds_value"] = False
        payload["packet_0063_earns_reader_state_eval"] = False
        payload["candidate_earns_reader_state_eval"] = False
        payload["target_role_consistency_checked"] = True
        payload["target_role_consistency_passed"] = False
        payload["target_role_consistency_failures"] = failures

    def _comparison(payload):
        payload["repair_has_causal_support"] = False
        payload["tactile_intervention_has_causal_support"] = False
        payload["tactile_force_contact_adds_value"] = False
        payload["packet_0063_earns_reader_state_eval"] = False

    def _consistency(payload):
        payload["comparison_internal_consistency"] = False
        payload["target_role_consistency_checked"] = True
        payload["target_role_consistency_passed"] = False
        payload["target_role_consistency_failures"] = failures

    def _packet(payload):
        payload["selected_repair_causal_status"] = (
            "inconclusive_due_to_comparator_role_confusion"
        )
        payload["comparison_internal_consistency"] = False
        payload["target_role_consistency_checked"] = True
        payload["target_role_consistency_passed"] = False
        payload["target_role_consistency_failures"] = failures
        gate_report = payload.get("gate_report", {})
        if isinstance(gate_report, dict):
            gate_report["comparison_internal_consistency"] = False
            gate_report["target_role_consistency_checked"] = True
            gate_report["target_role_consistency_passed"] = False
            gate_report["target_role_consistency_failures"] = failures

    def _gate(payload):
        payload["comparison_internal_consistency"] = False
        payload["target_role_consistency_checked"] = True
        payload["target_role_consistency_passed"] = False
        payload["target_role_consistency_failures"] = failures

    rewrite_payload(proof_payload["artifact_paths"]["ablation_causal_effect_report"], _causal)
    rewrite_payload(
        proof_payload["artifact_paths"]["ablation_old_new_rival_comparison"],
        _comparison,
    )
    rewrite_payload(proof_payload["artifact_paths"]["comparison_consistency_report"], _consistency)
    rewrite_payload(proof_payload["artifact_paths"]["executed_ablation_packet"], _packet)
    rewrite_payload(proof_payload["artifact_paths"]["executed_ablation_gate_report"], _gate)


def revision_stub_factory(
    clients: list[FakeAutonomousRevisionModelClient],
    *,
    mode: str = "valid",
    target_schema=AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA,
):
    def _factory(model: str) -> FakeAutonomousRevisionModelClient:
        client = FakeAutonomousRevisionModelClient(
            provider="openai",
            model=model,
            mode=mode,
            target_schema=target_schema,
        )
        clients.append(client)
        return client

    return _factory


def dump_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def rewrite_payload(path: str | Path, mutator) -> None:
    artifact_path = Path(path)
    envelope = json.loads(artifact_path.read_text(encoding="utf-8"))
    mutator(envelope["payload"])
    artifact_path.write_text(dump_json(envelope), encoding="utf-8", newline="\n")


def rewrite_envelope(path: str | Path, mutator) -> None:
    artifact_path = Path(path)
    envelope = json.loads(artifact_path.read_text(encoding="utf-8"))
    mutator(envelope)
    artifact_path.write_text(dump_json(envelope), encoding="utf-8", newline="\n")


def mark_packet_fixture_only(packet_dir: Path) -> None:
    for artifact_path in packet_dir.glob("*.json"):
        rewrite_envelope(
            artifact_path,
            lambda envelope: envelope.__setitem__("fixture_only", True),
        )


MULTI_PARAGRAPH_MACRO_BASE_TEXT = """The table is still there in the morning. Dust gathers under it, the spoon rests beside the saucer, and the room keeps the night's small pressure without explaining it.

There is a deeper pattern, and the pattern has to be named as record, law, proof, and answer before the reader can see why the table matters.

A line of life and mind proves itself by announcing that proof must arise inside the line, then announces the same proof again from a higher angle.

That is why the sky gives no answer. The silence is cosmic, the answer is withheld, and the pressure remains mostly stated instead of carried by the objects.

In the morning the table returns, and the return is described as changed, but the change still arrives as a closing explanation rather than an event inside the room."""


P003_RETURN_MACRO_BASE_TEXT = """The table is still there in the morning. Dust gathers under it, the spoon rests beside the saucer, and the room keeps the night's small pressure without explaining it.

There is a deeper pattern, and the pattern has to be named as record, law, proof, and answer before the reader can see why the table matters.

A line of life and mind proves itself by announcing that proof must arise inside the line. No answer enters from outside the kitchen; the silence holds the room to its own evidence.

Then the return, if it comes, will not be regression. It will come back through the table, through the dust, through the spoon on its side and the saucer with its crack, through the same room that held the earlier strain. The ring will remain a ring; the dust will remain dust; the room will remain the room, but now the morning sits in the grain and the day before sits in the gray body under the edge. The beginning is not restored untouched. It returns with what crossed it written into the surface, and the small world is still itself while no longer apart from what happened to it."""


def prepare_multi_paragraph_macro_synthesis(synthesis_payload: dict[str, object]) -> Path:
    return prepare_macro_synthesis_base_text(
        synthesis_payload,
        base_text=MULTI_PARAGRAPH_MACRO_BASE_TEXT,
    )


def prepare_macro_synthesis_base_text(
    synthesis_payload: dict[str, object],
    *,
    base_text: str,
) -> Path:
    synthesis_packet = Path(str(synthesis_payload["packet_dir"]))
    best_path = synthesis_packet / "best_current_candidate_selection.json"
    best = read_payload(best_path)
    selected = best["selected_best_candidate"]
    base_packet = Path(str(selected["packet_dir"]))
    base_text_path = next(
        path
        for path in (
            base_packet / "cycle2_revised_candidate_text.json",
            base_packet / "macro_recomposed_candidate_text.json",
        )
        if path.exists()
    )
    text_sha = sha256_text(base_text)

    def _rewrite_base(payload):
        payload["text"] = base_text
        payload["text_sha256"] = text_sha
        payload["word_count"] = len(base_text.split())

    def _rewrite_best(payload):
        selected_best = payload["selected_best_candidate"]
        selected_best["selected_best_candidate_text_sha256"] = text_sha
        selected_best["text_sha256"] = text_sha

    rewrite_payload(base_text_path, _rewrite_base)
    rewrite_payload(best_path, _rewrite_best)
    return synthesis_packet


def valid_old_new_rival_payload() -> dict[str, object]:
    provenance = {
        key: ["original_candidate_text", "revised_candidate_text"]
        for key in AUTONOMOUS_REVISION_JUDGMENT_KEYS
    }
    provenance["rival_still_beats_candidate"] = [
        "revised_candidate_text",
        "strongest_rival_text",
    ]
    rationale = {
        key: f"Rationale prose for {key} stays outside provenance sources."
        for key in AUTONOMOUS_REVISION_JUDGMENT_KEYS
    }
    return {
        "reread_transformation_improved": True,
        "opening_transformation_improved": True,
        "local_embodiment_improved": True,
        "overexplanation_decreased": True,
        "fake_depth_risk_decreased": False,
        "revised_candidate_became_more_schematic": False,
        "strongest_rival_present": True,
        "rival_still_beats_candidate": True,
        "another_revision_cycle_needed": True,
        "comparison_basis": "structured internal comparison, not human data",
        "rival_pressure_preserved": True,
        "old_new_summary": "The revised candidate improves but remains provisional.",
        "rival_pressure_summary": "The rival remains active pressure.",
        "judgment_provenance": provenance,
        "judgment_rationale": rationale,
        "not_human_data": True,
    }


def valid_ablation_comparison_payload() -> dict[str, object]:
    return {
        "candidate_label": "Text A",
        "comparison_rows": [
            {
                "row_id": "ablation_row_001",
                "comparison_summary": "Executed variant isolates the suspected handle.",
                "predicted_or_observed_effect": "reread pressure decreases predictably",
                "reader_state_effect_estimate": "opening attention becomes more object-bound",
                "rationale": "Uses an actual generated ablation variant, not a planned probe.",
                "risk_notes": "prediction-only row can overstate causal proof",
                "uncertainty": "medium",
                "not_human_data": True,
            },
            {
                "row_id": "ablation_row_002",
                "comparison_summary": "Planned probe is recorded without claiming execution.",
                "predicted_or_observed_effect": "predicted effect only",
                "reader_state_effect_estimate": "reread pressure remains uncertain",
                "rationale": "The probe has no generated variant yet.",
                "risk_notes": "planned-only rows cannot count as executed evidence",
                "uncertainty": "high",
                "not_human_data": True,
            },
        ],
        "summary": "Ablation rows keep executed variants separate from planned probes.",
        "not_human_data": True,
    }


class FullTextInjectionClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        if request.schema != AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            return raw_output
        payload = json.loads(raw_output)
        payload["text"] = (
            "This injected full-text rewrite should not become authoritative. "
            "The controller must ignore it and apply only accepted patches."
        )
        return dump_json(payload)


class TargetRegionViolationClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
            payload["selected_patch_target_id"] = "target_ending_return_closure"
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            prompt = json.loads(request.input_text)
            patch = payload["patches"][0]
            patch["patch_target_id"] = "target_opening_sentence"
            patch["patch_span_id"] = prompt["patchable_spans"][0]["patch_span_id"]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class BroadCanonicalTargetClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
            region = (
                "Opening paragraph through the first two image-to-interpretation pivots "
                "(table, ring, dust, spoon, record)."
            )
            payload["selected_patch_target_id"] = "target_opening_first_pivots"
            payload["span_ref"]["region"] = region
            payload["target_region_label"] = "target_region:opening_first_pivots"
            payload["target_region_description"] = region
            payload["allowed_span_refs"] = [region]
            payload["allowed_patch_targets"] = [
                {
                    "patch_target_id": "target_opening_first_pivots",
                    "target_region_label": "target_region:opening_first_pivots",
                    "target_region_description": region,
                    "allowed_span_ref": region,
                    "text_window": json.loads(request.input_text)["candidate"]["text"],
                    "paragraph_index": 0,
                    "protected_outside_spans": [f"all candidate spans outside {region}"],
                }
            ]
            payload["protected_outside_spans"] = [f"all candidate spans outside {region}"]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class ModelAuthoredPatchTargetInventoryClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
            prompt = json.loads(request.input_text)
            payload["selected_patch_target_id"] = prompt["allowed_patch_targets"][0][
                "patch_target_id"
            ]
            payload["allowed_patch_targets"] = [
                {
                    "patch_target_id": "target_model_authored_not_authoritative",
                    "target_region_label": "target_region:model_authored",
                    "target_region_description": "model-authored target must be ignored",
                    "allowed_span_ref": "model-authored target must be ignored",
                    "text_window": "model-authored target must be ignored",
                    "paragraph_index": 99,
                    "protected_outside_spans": ["model-authored inventory is ignored"],
                }
            ]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class DescriptionSelectedPatchTargetClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
            target = json.loads(request.input_text)["allowed_patch_targets"][0]
            payload["selected_patch_target_id"] = target["target_region_description"]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class InventedSelectedPatchTargetClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
            payload["selected_patch_target_id"] = "target_invented_elsewhere"
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class DisallowedPatchTargetClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            patch = payload["patches"][0]
            patch["patch_target_id"] = "target_ending_return_closure"
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class DescriptionPatchTargetClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            patch = payload["patches"][0]
            target = json.loads(request.input_text)["allowed_patch_targets"][0]
            patch["patch_target_id"] = target["target_region_description"]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class InventedPatchTargetClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            payload["patches"][0]["patch_target_id"] = "target_invented_elsewhere"
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class OriginalExcerptOutsideTargetClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            payload["patches"][0]["original_excerpt"] = (
                "not present inside the target window and not authoritative"
            )
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class InventedPatchSpanClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            payload["patches"][0]["patch_span_id"] = "span_target_invented_p99_s99"
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class DescriptionPatchSpanClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            span = json.loads(request.input_text)["patchable_spans"][0]
            payload["patches"][0]["patch_span_id"] = span["exact_text"]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class ReplacementPatchSpanClient(FakeAutonomousRevisionModelClient):
    replacement_text = (
        "The table is still there in the morning, but the room has not yet told the "
        "reader what that means."
    )

    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            patch = payload["patches"][0]
            patch["operation"] = "replace"
            patch["replacement_text"] = self.replacement_text
            patch["inserted_text"] = ""
            patch["rationale"] = "Replace only the selected controller span."
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class ExplicitTargetExpansionClient(TargetRegionViolationClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            payload["target_region_expanded"] = True
            payload["expanded_target_region"] = "opening paragraph plus ending paragraph"
            payload["expansion_reason"] = (
                "The selected ending pressure depends on the opening object record."
            )
            patch = payload["patches"][0]
            patch["requires_target_expansion"] = True
            patch["target_expansion_reason"] = (
                "Opening change is required to make the selected ending pressure legible."
            )
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class PlannedOnlyAblationClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA:
            payload["variants"][-1]["executed"] = False
            payload["variants"][-1]["expected_reader_state_change"] = (
                "planned probe only; not executed evidence"
            )
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class InvalidAblationComparisonClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
            payload["comparison_rows"][0]["row_id"] = "ablation_row_999"
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class DuplicateAblationRowClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
            payload["comparison_rows"][1]["row_id"] = payload["comparison_rows"][0]["row_id"]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class MissingAblationRowClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
            payload["comparison_rows"] = payload["comparison_rows"][:-1]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class ModelAuthoredAblationControlFieldsClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
            row = payload["comparison_rows"][0]
            row["planned_only"] = True
            row["executed_variant_id"] = "model_authored_variant"
            row["planned_probe_id"] = "model_authored_probe"
            row["evidence_basis"] = "planned_ablation_probe"
            row["operation"] = "model_authored_operation"
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class StubExecutedAblationClient:
    provider = "openai"

    def __init__(self, *, model: str, mode: str = "valid") -> None:
        self.model = model
        self.mode = mode
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if self.mode == "invalid":
            return "{not valid json"
        if self.mode == "malformed":
            return dump_json({"comparison_rows": "wrong", "not_human_data": True})
        prompt = json.loads(request.input_text)
        rows = []
        for variant in prompt["variants"]:
            summary = "stub comparison interpretation"
            rationale = "stub rationale, not human data"
            risk_notes = "stub risk note"
            if (
                self.mode == "confused_tactile_revert"
                and variant["operation_id"]
                == "operation_revert_tactile_intervention_to_current_best"
            ):
                summary = (
                    "The revert restores strong tactile-force contact and reads as the "
                    "full tactile intervention."
                )
                rationale = (
                    "This row confuses the current-best object-motion baseline with "
                    "the restored tactile repair, not human data."
                )
            if (
                self.mode == "confused_tactile_removed"
                and variant["operation_id"]
                == "operation_preserve_object_motion_remove_tactile_force_relation"
            ):
                summary = (
                    "The tactile-removed control is effectively the full tactile "
                    "candidate with restored force/contact."
                )
            if self.mode == "stale_tactile_macro_label":
                risk_notes = "This uses proof/no-outside-answer and record compression labels."
            rows.append(
                {
                    "variant_id": variant["variant_id"],
                    "comparison_summary": summary,
                    "reader_state_effect_estimate": "stub reader-state estimate",
                    "rationale": rationale,
                    "uncertainty": "medium",
                    "risk_notes": risk_notes,
                    "not_human_data": True,
                }
            )
        return dump_json(
            {
                "comparison_rows": rows,
                "summary": "stub executed ablation comparison",
                "not_human_data": True,
            }
        )


def executed_ablation_stub_factory(clients, *, mode: str = "valid"):
    def _factory(model: str) -> StubExecutedAblationClient:
        client = StubExecutedAblationClient(model=model, mode=mode)
        clients.append(client)
        return client

    return _factory


class StubAblationInformedRevisionClient:
    provider = "openai"

    def __init__(self, *, model: str, mode: str = "valid") -> None:
        self.model = model
        self.mode = mode
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if self.mode == "invalid_json":
            return "{not valid json"
        if request.schema == ABLATION_INFORMED_BASE_SELECTION_SCHEMA:
            prompt = json.loads(request.input_text)
            dominance = prompt["ablation_evidence_dominance_report"]
            pivot = prompt["residual_blocker_pivot_report"]
            selected = (
                pivot["base_policy"]["recommended_base_candidate_id"]
                if pivot["pivot_required"]
                else dominance["recommended_base_candidate_id"]
            )
            if self.mode == "same_handle_justified" and pivot["pivot_required"]:
                selected = BASE_CHOICE_CONTROLLER_COMPOSED
            rejection_reason = "not applicable; selected controller recommendation"
            rejection_evidence = "not applicable; no protected-effect rejection"
            if self.mode == "invented_base":
                selected = "invented_base_candidate"
            elif self.mode == "weaker_base":
                selected = BASE_CHOICE_CONTROLLER_COMPOSED
                rejection_reason = ""
                rejection_evidence = ""
            elif self.mode in {"dominance_rejection", "noop_patch", "regressive_patch"}:
                selected = BASE_CHOICE_CONTROLLER_COMPOSED
                rejection_reason = (
                    "The dominant variant is rejected for this test because it "
                    "would damage a protected concrete embodiment effect."
                )
                rejection_evidence = (
                    "Protected embodiment evidence: the dominant variant risks "
                    "flattening table, spoon, and room pressure."
                )
            return dump_json(
                {
                    "selected_base_candidate_id": selected,
                    "why_packet_0030_not_proven": (
                        "The executed ablation packet records the prior repair as "
                        "weak or noncausal, so it is not proof."
                    ),
                    "prior_repair_causal_status": "noncausal_or_cosmetic",
                    "evidence_rationale": (
                        "Select the controller-composed base because it preserves "
                        "supported embodiment without stacking the unproven repair."
                    ),
                    "embodiment_preserving_insight": (
                        "The opening needs concrete table, spoon, and room pressure."
                    ),
                    "record_law_proof_answer_insight": (
                        "Record/law/proof language should be compressed later."
                    ),
                    "explicit_dominance_rejection_reason": rejection_reason,
                    "dominance_rejection_protected_effect_or_forbidden_change_evidence": (
                        rejection_evidence
                    ),
                    "uncertainty": "medium",
                    "not_human_data": True,
                }
            )
        if request.schema == ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA:
            prompt = json.loads(request.input_text)
            pivot = prompt["residual_blocker_pivot_report"]
            selected = (
                pivot["selected_residual_blocker"]
                if pivot["pivot_required"]
                else HANDLE_RECORD_COMPRESSION
            )
            same_handle_justification = ""
            same_handle_evidence = ""
            if self.mode == "same_handle_no_justification":
                selected = pivot["prior_handle"]
            elif self.mode == "same_handle_justified":
                selected = pivot["prior_handle"]
                same_handle_justification = (
                    "The same handle is needed to protect a concrete embodiment "
                    "effect that the residual blocker would damage."
                )
                same_handle_evidence = (
                    "Protected embodiment evidence contradicts a clean pivot away "
                    "from the prior handle."
                )
            return dump_json(
                {
                    "selected_next_handle": selected,
                    "why_previous_repair_weak_or_cosmetic": (
                        "The prior opening repair was not causally proven by ablation."
                    ),
                    "evidence_summary": (
                        "Record compression has stronger diagnostic support than "
                        "repeating the opening patch."
                    ),
                    "why_handle_better_than_opening_patch": (
                        "It targets a countable evidence handle while preserving "
                        "strongest-rival pressure."
                    ),
                    "local_law_explanation": (
                        "Let objects hold the pattern before the text names it."
                    ),
                    "explicit_same_handle_justification": same_handle_justification,
                    "same_handle_justification_evidence": same_handle_evidence,
                    "uncertainty": "medium",
                    "strongest_rival_pressure_remains_blocking": True,
                    "not_human_data": True,
                }
            )
        if request.schema == ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA:
            prompt = json.loads(request.input_text)
            replacements = {
                "cycle2_patch_span_001": (
                    "together they make a record, local and plain, not a message sent "
                    "from elsewhere."
                ),
                "cycle2_patch_span_002": "It keeps a law of staying and change.",
                "cycle2_patch_span_003": (
                    "The proof, if there is one, has to join the line from within it."
                ),
                "cycle2_patch_span_005": "No completed answer has entered this local story.",
            }
            patches = []
            for span in prompt["patchable_spans"]:
                span_id = span["patch_span_id"]
                replacement = replacements.get(
                    span_id,
                    f"{span['exact_text']} compressed",
                )
                if self.mode == "noop_patch" and not patches:
                    replacement = span["exact_text"]
                if self.mode == "regressive_patch":
                    replacement = (
                        f"{span['exact_text']} record law proof answer validation"
                    )
                patches.append(
                    {
                        "patch_span_id": span_id,
                        "replacement_text": replacement,
                        "rationale": (
                            "Compress explanation into local object-bound pressure."
                        ),
                        "local_law_explanation": (
                            "The scene should carry the pressure before naming it."
                        ),
                        "uncertainty": "medium",
                    }
                )
            return dump_json(
                {
                    "patches": patches,
                    "preserves_necessary_philosophical_pressure": (
                        "The replacement keeps the night's pressure in the object-world."
                    ),
                    "avoids_full_rewrite": True,
                    "not_human_data": True,
                }
            )
        raise AssertionError(f"unexpected schema: {request.schema.name}")


def ablation_informed_stub_factory(clients, *, mode: str = "valid"):
    def _factory(model: str) -> StubAblationInformedRevisionClient:
        client = StubAblationInformedRevisionClient(model=model, mode=mode)
        clients.append(client)
        return client

    return _factory


class StubBoundedMacroRecompositionClient:
    provider = "openai"

    def __init__(self, *, model: str, mode: str = "valid") -> None:
        self.model = model
        self.mode = mode
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if request.schema != BOUNDED_MACRO_RECOMPOSITION_SCHEMA:
            raise AssertionError(f"unexpected schema: {request.schema.name}")
        prompt = json.loads(request.input_text)
        is_retry = prompt.get("retry_kind") == "target_addressed_corrective_retry"
        work_order = prompt.get("work_order", {})
        target_paragraphs = (
            work_order.get("target_paragraphs", [])
            if isinstance(work_order, dict)
            else []
        )
        target_spans = (
            work_order.get("target_spans", []) if isinstance(work_order, dict) else []
        )
        payload = live_macro_payload(
            prompt.get("active_transformation_targets", []),
            target_movement=str(prompt.get("target_movement") or "middle_and_return_movement"),
            target_paragraphs=target_paragraphs,
            target_spans=target_spans,
        )
        if self.mode == "invalid_json":
            return "{not valid json"
        if self.mode == "missing_constraint":
            payload["constraint_mapping"] = payload["constraint_mapping"][:-1]
        elif self.mode == "duplicate_constraint":
            payload["constraint_mapping"] = [
                *payload["constraint_mapping"],
                dict(payload["constraint_mapping"][0]),
            ]
        elif self.mode == "empty_excerpt":
            payload["constraint_mapping"][0]["supporting_replacement_excerpt"] = ""
        elif self.mode == "outside_rescue":
            payload["replacement_section_text"] += "\n\nThen outside rescue arrives."
        elif self.mode == "proof_from_outside":
            payload["replacement_section_text"] += "\n\nHere proof comes from outside."
        elif self.mode == "final_claim":
            payload["rationale"] = "phase shift achieved"
        elif self.mode == "artifact_final_claim":
            payload["target_paragraph_replacements"][0]["replacement_text"] = (
                "This is the final artifact."
            )
        elif self.mode == "metadata_final_artifact_claim":
            payload["rationale"] = "This is the final artifact."
        elif self.mode == "rival_defeated_claim":
            payload["rationale"] = "strongest rival defeated"
        elif self.mode == "metadata_controller_final_artifact_phrase":
            payload["constraint_mapping"][0]["uncertainty"] = (
                "Medium, because the controller still needs to assemble the final artifact "
                "and verify span coverage."
            )
        elif self.mode == "metadata_does_not_claim_finality":
            payload["predicted_reader_state_effect"] = (
                "The strongest-rival pressure should remain active because the text does "
                "not claim closure, finality, or defeat."
            )
        elif self.mode == "metadata_avoid_finality":
            payload["constraint_mapping"][4]["supporting_replacement_excerpt"] = (
                "The replacement preserves a concrete object sequence and avoids "
                "claim-language of victory or finality."
            )
        elif self.mode == "metadata_finalization_false":
            payload["uncertainty"] = "Finalization remains false until the controller acts."
        elif self.mode == "metadata_final_artifact_plus_copied_target_p003":
            payload["constraint_mapping"][0]["uncertainty"] = (
                "Medium, because the controller still needs to assemble the final artifact "
                "and verify span coverage."
            )
            _copy_target_paragraph(payload, target_paragraphs, "target_p003")
        elif self.mode == "prefix_rewrite":
            payload["replacement_section_text"] = (
                f"{prompt['unchanged_prefix_text']}\n\n{payload['replacement_section_text']}"
            )
        elif self.mode == "full_rewrite":
            payload["replacement_section_text"] = (
                f"{prompt['unchanged_prefix_text']}\n\n{prompt['before_section_text']}"
            )
        elif self.mode == "conflicting_replacement_section_text":
            payload["replacement_section_text"] = (
                "This conflicting model blob should not be used by the controller."
            )
        elif self.mode == "missing_target_p002":
            payload["target_paragraph_replacements"] = [
                item
                for item in payload.get("target_paragraph_replacements", [])
                if item["target_paragraph_ref"] != "target_p002"
            ]
        elif self.mode == "missing_target_p002_then_correct" and not is_retry:
            payload["target_paragraph_replacements"] = [
                item
                for item in payload.get("target_paragraph_replacements", [])
                if item["target_paragraph_ref"] != "target_p002"
            ]
        elif self.mode == "copied_target_p002_p003_then_correct" and not is_retry:
            _copy_target_paragraph(payload, target_paragraphs, "target_p002")
            _copy_target_paragraph(payload, target_paragraphs, "target_p003")
        elif self.mode == "copied_target_p002_p003_retry_only_p002":
            if not is_retry:
                _copy_target_paragraph(payload, target_paragraphs, "target_p002")
                _copy_target_paragraph(payload, target_paragraphs, "target_p003")
            else:
                payload["target_paragraph_replacements"] = [
                    item
                    for item in payload.get("target_paragraph_replacements", [])
                    if item["target_paragraph_ref"] != "target_p003"
                ]
        elif (
            self.mode == "missing_target_p002_copied_target_p003_then_correct"
            and not is_retry
        ):
            payload["target_paragraph_replacements"] = [
                item
                for item in payload.get("target_paragraph_replacements", [])
                if item["target_paragraph_ref"] != "target_p002"
            ]
            _copy_target_paragraph(payload, target_paragraphs, "target_p003")
        elif (
            self.mode == "copied_target_p002_missing_span_p001_then_correct"
            and not is_retry
        ):
            _copy_target_paragraph(payload, target_paragraphs, "target_p002")
            _remove_first_required_target_span(payload, target_spans, "target_p001")
        elif self.mode == "copied_target_p002":
            _copy_target_paragraph(payload, target_paragraphs, "target_p002")
        elif self.mode == "copied_target_p003":
            _copy_target_paragraph(payload, target_paragraphs, "target_p003")
        elif self.mode == "near_copy_target_p003":
            _near_copy_target_paragraph(payload, target_paragraphs, "target_p003")
        elif self.mode == "near_copy_target_p003_then_correct" and not is_retry:
            _near_copy_target_paragraph(payload, target_paragraphs, "target_p003")
        elif self.mode == "near_copy_target_p003_retry_near_copy":
            _near_copy_target_paragraph(payload, target_paragraphs, "target_p003")
        elif self.mode == "copied_target_p004":
            _copy_target_paragraph(payload, target_paragraphs, "target_p004")
        elif self.mode == "copied_target_p004_then_correct" and not is_retry:
            _copy_target_paragraph(payload, target_paragraphs, "target_p004")
        elif self.mode == "copied_target_p004_retry_copies":
            _copy_target_paragraph(payload, target_paragraphs, "target_p004")
        elif self.mode == "retry_extra_override":
            if not is_retry:
                _copy_target_paragraph(payload, target_paragraphs, "target_p004")
            else:
                extra = _successful_retry_override(prompt, "target_p001")
                if extra is not None:
                    payload["target_paragraph_replacements"].append(extra)
        elif self.mode == "mismatched_target_hash":
            payload["target_paragraph_replacements"][0]["before_text_sha256"] = "bad-hash"
        elif self.mode == "duplicate_target_ref":
            payload["target_paragraph_replacements"].append(
                dict(payload["target_paragraph_replacements"][0])
            )
        elif self.mode == "thesis_target_uncovered":
            for item in payload["target_paragraph_replacements"]:
                item["active_target_ids_covered"] = [
                    target_id
                    for target_id in item["active_target_ids_covered"]
                    if target_id != "thesis_visible_proof_language_reduction"
                ]
        elif self.mode == "extra_known_paragraph_target_claim":
            _append_target_paragraph_claim(
                payload,
                "target_p002",
                "final_return_echo_reread_strength",
            )
        elif self.mode == "paragraph_extra_known_does_not_cover_missing_assigned":
            _replace_target_paragraph_claims(
                payload,
                "target_p001",
                ["final_return_echo_reread_strength"],
            )
        elif self.mode == "unknown_paragraph_target_claim":
            _append_target_paragraph_claim(
                payload,
                "target_p002",
                "invented_macro_target",
            )
        elif self.mode == "extra_known_span_target_claim":
            _append_first_required_target_span_claim(
                payload,
                target_spans,
                "target_p001",
                "final_return_echo_reread_strength",
            )
        elif self.mode == "span_extra_known_does_not_cover_missing_assigned":
            _replace_first_required_target_span_claims(
                payload,
                target_spans,
                "target_p001",
                ["final_return_echo_reread_strength"],
            )
        elif self.mode == "unknown_span_target_claim":
            _append_first_required_target_span_claim(
                payload,
                target_spans,
                "target_p001",
                "invented_macro_target",
            )
        elif self.mode == "copied_target_p004_retry_extra_known_claim":
            if not is_retry:
                _copy_target_paragraph(payload, target_paragraphs, "target_p004")
            else:
                _append_target_paragraph_claim(
                    payload,
                    "target_p004",
                    "proof_no_outside_answer_refinement",
                )
        elif self.mode == "target_p001_final_proof_only":
            _copy_target_with_changed_proof_only(payload, target_paragraphs, "target_p001")
        elif self.mode == "target_p001_final_proof_only_then_correct" and not is_retry:
            _copy_target_with_changed_proof_only(payload, target_paragraphs, "target_p001")
        elif self.mode == "target_p001_span_retry_copies":
            _copy_target_with_changed_proof_only(payload, target_paragraphs, "target_p001")
        elif self.mode == "missing_target_span_p001_s001":
            _remove_first_required_target_span(payload, target_spans, "target_p001")
        elif self.mode == "mismatched_target_span_hash":
            _mismatch_first_required_target_span_hash(payload, target_spans)
        elif self.mode == "missing_active_target":
            payload["active_target_mapping"] = payload["active_target_mapping"][:-1]
        elif self.mode == "unchanged_without_justification":
            payload["active_target_mapping"][0]["unchanged"] = True
            payload["active_target_mapping"][0]["unchanged_justification"] = ""
        elif self.mode == "copied_first_two":
            payload["replacement_section_text"] = copied_target_replacement(
                prompt,
                copied_indexes={0, 1},
            )
        elif self.mode in {"proof_unchanged", "no_answer_unchanged"}:
            payload["replacement_section_text"] = copied_target_replacement(
                prompt,
                copied_indexes={1},
            )
        elif self.mode in {"final_only_change", "mostly_copied"}:
            before_paragraphs = [
                paragraph.strip()
                for paragraph in prompt["before_section_text"].split("\n\n")
                if paragraph.strip()
            ]
            replacement = list(before_paragraphs)
            if replacement:
                replacement[-1] = (
                    "The return is not a reset. Morning comes back to the same "
                    "table, but the table now carries the room's relations as a "
                    "record inside itself."
                )
            payload["replacement_section_text"] = "\n\n".join(replacement)
        return dump_json(payload)


def bounded_macro_stub_factory(clients, *, mode: str = "valid"):
    def _factory(model: str) -> StubBoundedMacroRecompositionClient:
        client = StubBoundedMacroRecompositionClient(model=model, mode=mode)
        clients.append(client)
        return client

    return _factory


class StubObjectEventRecompositionClient:
    provider = "openai"

    def __init__(self, *, model: str, mode: str = "valid") -> None:
        self.model = model
        self.mode = mode
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if request.schema != BOUNDED_MACRO_RECOMPOSITION_SCHEMA:
            raise AssertionError(f"unexpected schema: {request.schema.name}")
        prompt = json.loads(request.input_text)
        work_order = prompt.get("work_order", {})
        target_paragraphs = (
            work_order.get("target_paragraphs", [])
            if isinstance(work_order, dict)
            else []
        )
        payload = live_macro_payload(
            prompt.get("active_transformation_targets", []),
            target_movement=OBJECT_EVENT_TARGET_SCOPE,
            target_paragraphs=target_paragraphs,
            target_spans=[],
        )
        if self.mode == "invalid_json":
            return "{not valid json"
        if self.mode == "full_rewrite":
            payload["replacement_section_text"] = (
                f"{prompt['unchanged_prefix_text']}\n\n"
                f"{prompt['before_section_text']}\n\n"
                f"{prompt['unchanged_suffix_text']}"
            )
        elif self.mode == "decorative_only":
            payload["replacement_section_text"] = (
                "The table looks blue in the soft morning, the spoon shines, "
                "the saucer glows, the ring seems delicate, and the dust looks "
                "silver in a beautiful hush."
            )
        elif self.mode == "proof_only":
            payload["replacement_section_text"] = (
                "Proof has no outside answer because the law of record compresses "
                "the return into its own abstract necessity. The answer remains "
                "inside proof, and proof remains inside the answer."
            )
        elif self.mode == "unchanged_region":
            payload["replacement_section_text"] = str(prompt["before_section_text"])
        return dump_json(payload)


def object_event_stub_factory(clients, *, mode: str = "valid"):
    def _factory(model: str) -> StubObjectEventRecompositionClient:
        client = StubObjectEventRecompositionClient(model=model, mode=mode)
        clients.append(client)
        return client

    return _factory


class StubObjectMotionCausalityClient(FakeObjectMotionCausalityModelClient):
    provider = "openai"

    def __init__(self, *, model: str, mode: str = "valid") -> None:
        super().__init__(mode=mode)
        self.model = model
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if request.schema != OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA:
            raise AssertionError(f"unexpected schema: {request.schema.name}")
        return super().generate(request)


def object_motion_causality_stub_factory(clients, *, mode: str = "valid"):
    def _factory(model: str) -> StubObjectMotionCausalityClient:
        client = StubObjectMotionCausalityClient(model=model, mode=mode)
        clients.append(client)
        return client

    return _factory


class StubResidualInterventionClient:
    provider = "openai"

    def __init__(self, *, model: str, mode: str = "valid") -> None:
        self.model = model
        self.mode = mode
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if request.schema != RESIDUAL_INTERVENTION_GENERATION_SCHEMA:
            raise AssertionError(f"unexpected schema: {request.schema.name}")
        prompt = json.loads(request.input_text)
        units = prompt["target_units"]
        if self.mode == "object_motion_relabel":
            relabel_sentences = []
            for unit in units:
                labels = [str(value) for value in unit.get("objects", []) if str(value)]
                label_phrase = " ".join(labels[:5] or ["object", "mark"])
                relabel_sentences.append(
                    f"The {label_phrase} moves and changes, so the visible consequence is named by motion."
                )
            return dump_json(
                {
                    "replacement_region_text": " ".join(relabel_sentences),
                    "target_unit_mappings": _residual_intervention_mapping(units),
                    "intervention_plan": ["repeat object motion"],
                    "constraint_mapping": [
                        {
                            "constraint_id": "bounded_selected_region",
                            "how_satisfied": "bounded",
                            "risk_note": "weak",
                        }
                    ],
                    "protected_effects_notes": ["weak fixture note"],
                    "forbidden_change_self_check": ["no finality claim"],
                    "uncertainty": "invalid stub",
                }
            )
        if self.mode == "decorative":
            payload = _valid_residual_intervention_payload(units)
            payload["replacement_region_text"] = (
                "The luminous porcelain, beautiful dust, velvet air, silver spoon, "
                "and shimmering saucer make the room vivid and atmospheric."
            )
            return dump_json(payload)
        if self.mode == "abstract":
            payload = _valid_residual_intervention_payload(units)
            payload["replacement_region_text"] = (
                "The room explains inevitability as a metaphysical proof. Each "
                "object becomes inevitable because the thesis says the relation is "
                "non-optional."
            )
            return dump_json(payload)
        if self.mode == "packet_0062_like":
            return dump_json(_packet_0062_like_residual_payload(units))
        if self.mode == "hostile_packet_0064_like":
            return dump_json(_hostile_packet_0064_like_residual_payload(units))
        if self.mode == "hostile_packet_0065_like":
            return dump_json(_hostile_packet_0065_like_residual_payload(units))
        if self.mode == "hostile_packet_0066_like":
            return dump_json(_hostile_packet_0066_like_residual_payload(units))
        if self.mode == "hostile_packet_0067_like":
            return dump_json(_hostile_packet_0067_like_residual_payload(units))
        if self.mode == "hostile_strong":
            return dump_json(_valid_hostile_residual_intervention_payload(units))
        if self.mode == "ending_packet_0068_like":
            return dump_json(_ending_packet_0068_like_residual_payload(units))
        if self.mode == "ending_packet_0069_like":
            return dump_json(_ending_packet_0069_like_residual_payload(units))
        if self.mode == "ending_packet_0070_like":
            return dump_json(_ending_packet_0070_like_residual_payload(units))
        if self.mode == "ending_clearing_reset":
            return dump_json(_ending_clearing_reset_residual_payload(units))
        if self.mode == "ending_strong":
            return dump_json(_valid_ending_residual_intervention_payload(units))
        if self.mode == "protected_context_stable":
            prompt = json.loads(request.input_text)
            return dump_json(
                _protected_context_stable_residual_payload(
                    units,
                    str(prompt["selected_region_before_text"]),
                )
            )
        return dump_json(_valid_residual_intervention_payload(units))


def _residual_intervention_mapping(units):
    return [
        {
            "target_unit_id": str(unit["unit_id"]),
            "before_text_sha256": str(unit.get("before_text_sha256") or ""),
            "mechanism_operation": "make contact pressure residue and breakage materially causal",
            "material_relation_or_action": str(
                unit.get("current_physical_relation")
                or unit.get("current_motion_action_state")
                or "contact leaves a mark"
            ),
            "visible_consequence": str(
                unit.get("target_effect") or "the surface keeps the material mark"
            ),
            "intended_first_read_effect": (
                "reader feels the material consequence before explanation names it"
            ),
            "protected_effects_preserved": [
                "current-best partial reread transformation",
                "proof/no-answer gains",
            ],
            "covered_target_ids": [str(unit["unit_id"]), TACTILE_INEVITABILITY_TARGET_ID],
        }
        for unit in units
    ]


def _valid_residual_intervention_payload(units):
    return {
        "replacement_region_text": _tactile_stub_replacement_from_units(units),
        "target_unit_mappings": _residual_intervention_mapping(units),
        "intervention_plan": [
            "replace only the selected region",
            "preserve object-motion gains",
            "add force/contact necessity",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "only replacement_region_text is supplied",
                "risk_note": "controller owns final assembly",
            }
        ],
        "protected_effects_notes": [
            "opening, proof, and final return remain outside the replacement"
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no rival mimicry",
            "no abstract inevitability explanation",
        ],
        "uncertainty": "stub output for tests only",
    }


def _packet_0062_like_residual_payload(units):
    mapping = _residual_intervention_mapping(units)
    if len(mapping) >= 3:
        mapping[0].update(
            {
                "mechanism_operation": (
                    "Pressure and contact are made to produce the trace before any "
                    "explanation follows."
                ),
                "material_relation_or_action": (
                    "The ring tightens at the cup's lip, and the crumb is taken "
                    "into the table's grain."
                ),
                "visible_consequence": (
                    "The surface change appears immediately, as a tightened ring "
                    "and a displaced crumb."
                ),
            }
        )
        mapping[1].update(
            {
                "mechanism_operation": (
                    "Contact and passage are tied to the residue they leave on the "
                    "surface."
                ),
                "material_relation_or_action": (
                    "Dust gathers where hand, foot, and air have pressed the same "
                    "surface."
                ),
                "visible_consequence": (
                    "The settled dust reads as the result of prior contact and "
                    "crossing."
                ),
            }
        )
        mapping[2].update(
            {
                "mechanism_operation": (
                    "Release, weight, and fall are linked to the visible break "
                    "they leave behind."
                ),
                "material_relation_or_action": (
                    "The spoon lies where a hand released it too quickly, and the "
                    "saucer shows the break the fall made visible."
                ),
                "visible_consequence": (
                    "The cracked saucer reads as the unavoidable result of impact."
                ),
            }
        )
    return {
        "replacement_region_text": (
            "A room like this teaches by repetition. When a cup is set down and "
            "lifted again, the ring tightens where the lip meets the wood, and "
            "the crumb is taken into the table's grain; the change is there "
            "before anyone names it. Morning does not wipe that away. Dust gathers "
            "where hand, foot, and air have pressed the same surface, and "
            "the spoon lies where a hand released it beside the saucer whose "
            "break the fall made visible. The world holds "
            "these crossings in place and makes them matter.\n\n"
            "At first, the table seems only ordinary. But ordinary things are "
            "strict about what reaches them. The ring keeps the trace of the "
            "glass because the pressure stays in the wood, the dust marks a "
            "passage through the window crack because the air and touch have "
            "already crossed it, the spoon lies where a hand released it too "
            "quickly, and the saucer shows the break that the fall made visible. "
            "Each object stays itself by carrying the force that brought it "
            "there. The kitchen is small, but it makes one rule plain: one thing "
            "enters another, leaves a mark, and that mark changes how the next "
            "thing is read."
        ),
        "target_unit_mappings": mapping,
        "intervention_plan": ["packet 0062 regression shape"],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "bounded",
                "risk_note": "conservative rewrite",
            }
        ],
        "protected_effects_notes": ["protected context mostly stable"],
        "forbidden_change_self_check": ["no finality claim", "no phase-shift claim"],
        "uncertainty": "packet 0062-like regression fixture",
    }


def _hostile_intervention_mapping(units):
    return [
        {
            "target_unit_id": str(unit["unit_id"]),
            "before_text_sha256": str(unit.get("before_text_sha256") or ""),
            "mechanism_operation": (
                "shift visible thesis pressure into object relation and residue"
            ),
            "material_relation_or_action": str(
                unit.get("current_physical_relation")
                or unit.get("current_motion_action_state")
                or "object contact leaves pressure in the surface"
            ),
            "visible_consequence": (
                "the object sequence carries meaning before explanation names it"
            ),
            "intended_first_read_effect": (
                "reader feels scaffold pressure reduced through the material sequence"
            ),
            "protected_effects_preserved": [
                "proof/no-answer pressure remains protected",
                "opening-return and reread gains remain protected",
                "object/tactile causal field remains active",
            ],
            "covered_target_ids": [str(unit["unit_id"])],
        }
        for unit in units
    ]


def _hostile_packet_0064_like_residual_payload(units):
    return {
        "replacement_region_text": (
            "A room like this teaches by repetition. When a cup is set down and "
            "lifted again, the wet ring draws tight under the cup's weight, and "
            "the crumb is pressed into the table's grain; the room has taken "
            "the trace before anyone names it. Morning does not wipe that away. "
            "It keeps the spoon on its side and the saucer cracked, while dust "
            "settles where hand, foot, and air have crossed the same surface "
            "enough to leave it marked. These crossings stay put in the mark "
            "they make.\n\n"
            "At first, the table is only ordinary. Ordinary things do not give "
            "up what reaches them. The ring keeps the glass's trace because it "
            "is pressed there; dust holds the path through the window crack "
            "where movement has disturbed it; the spoon lies where a hand let "
            "it drop and the side hit hard enough to stay; the saucer shows "
            "the break the fall forced open. Each object stays itself by "
            "carrying the pressure that brought it there. In the small kitchen, "
            "one thing enters another, leaves a mark, and the mark changes how "
            "the next thing is read."
        ),
        "target_unit_mappings": _hostile_intervention_mapping(units),
        "intervention_plan": [
            "packet 0064 regression shape",
            "conservative sentence polishing",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "bounded",
                "risk_note": "too conservative for hostile scaffold target",
            }
        ],
        "protected_effects_notes": [
            "proof/no-answer pressure remains protected",
            "opening-return and object/tactile field remain protected",
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no rival imitation",
        ],
        "uncertainty": "packet 0064-like regression fixture",
    }


def _hostile_packet_0065_like_residual_payload(units):
    return {
        "replacement_region_text": (
            "A room like this teaches by repetition. When a cup is set down and "
            "lifted again, the wet ring draws tight under the cup's weight, and "
            "the crumb is pressed into the table's grain; the room has already "
            "taken the trace before anyone names it. Morning does not wipe that "
            "away. It keeps the spoon on its side and the saucer cracked, while "
            "dust settles because hand, foot, and air have crossed and rubbed "
            "the same surface enough to leave it marked. The crossings stay "
            "where they were made, and their pressure is what counts.\n\n"
            "At first, the table is just there. But ordinary things do not take "
            "everything; they keep what reaches them and turn the rest aside. "
            "The ring holds the glass's trace because it was pressed there; "
            "dust keeps the line from the window crack where movement has "
            "stirred it; the spoon lies where a hand let it drop and the side "
            "hit hard enough to stay; the saucer carries the break the fall "
            "opened. In the small kitchen, one thing enters another, leaves a "
            "mark, and the next thing comes away changed."
        ),
        "target_unit_mappings": _hostile_intervention_mapping(units),
        "intervention_plan": [
            "packet 0065 regression shape",
            "ordinary-table near-synonym sentence polish",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "bounded",
                "risk_note": "ordinary-table unit remains under-material",
            }
        ],
        "protected_effects_notes": [
            "proof/no-answer pressure remains protected",
            "opening-return and object/tactile field remain protected",
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no rival imitation",
        ],
        "uncertainty": "packet 0065-like regression fixture",
    }


def _hostile_packet_0066_like_residual_payload(units):
    return {
        "replacement_region_text": (
            "A room like this teaches by repetition. When a cup is set down and "
            "lifted again, the wet ring draws tight under the cup's weight, and "
            "the crumb is pressed into the table's grain; the room has already "
            "taken the trace before anyone names it. Morning does not wipe that "
            "away. It keeps the spoon on its side and the saucer cracked, while "
            "dust settles because hand, foot, and air have crossed and rubbed "
            "the same surface enough to leave it marked. The crossings stay "
            "where they were made, and the marks keep their hold.\n\n"
            "At first, the table only meets the room's use. But ordinary things "
            "in the small kitchen keep their own pressure: the ring holds the "
            "glass's trace, dust hangs in the window crack, the spoon lies where "
            "a hand let it drop, the saucer carries the opened break, and each "
            "mark changes the next reading after contact. Each thing keeps what "
            "reached it."
        ),
        "target_unit_mappings": _hostile_intervention_mapping(units),
        "intervention_plan": [
            "packet 0066 regression shape",
            "material rewrite still carries semantic scaffold leakage",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "bounded",
                "risk_note": "semantic scaffold leakage remains",
            }
        ],
        "protected_effects_notes": [
            "proof/no-answer pressure remains protected",
            "opening-return and object/tactile field remain protected",
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no rival imitation",
        ],
        "uncertainty": "packet 0066-like regression fixture",
    }


def _hostile_packet_0067_like_residual_payload(units):
    return {
        "replacement_region_text": (
            "A room like this teaches by repetition. When a cup is set down and "
            "lifted again, the ring tightens where the lip meets the wood, and "
            "the crumb is taken into the table's grain; the change is there "
            "before anyone names it. Morning does not wipe that away. Dust "
            "gathers where hand, foot, and air have pressed the same surface, "
            "and the spoon lies where a hand released it beside the saucer "
            "whose break the fall made visible. The room keeps those crossings "
            "in its grain.\n\n"
            "At first, the table seems only ordinary. But ordinary things are "
            "strict about what reaches them. The ring keeps the trace of the "
            "glass because the pressure stays in the wood, the dust marks a "
            "passage through the window crack because the air and touch have "
            "already crossed it, the spoon lies where a hand released it too "
            "quickly, and the saucer shows the break that the fall made visible. "
            "Each object stays itself by carrying the force that brought it "
            "there. The kitchen is small, but it makes one rule plain: one thing "
            "enters another, leaves a mark, and that mark changes how the next "
            "thing is read."
        ),
        "target_unit_mappings": _hostile_intervention_mapping(units),
        "intervention_plan": [
            "packet 0067 regression shape",
            "low target-bearing ratio with scaffold pressure still unresolved",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "bounded",
                "risk_note": "target-bearing materiality ratio remains too low",
            }
        ],
        "protected_effects_notes": [
            "proof/no-answer pressure remains protected",
            "opening-return and object/tactile field remain protected",
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no rival imitation",
        ],
        "uncertainty": "packet 0067-like regression fixture",
    }


def _valid_hostile_residual_intervention_payload(units):
    return {
        "replacement_region_text": (
            "The cup comes down first, and the table answers before the room "
            "has time to speak: the rim leaves a dark pressure-ring, the "
            "crumb catches at the damp edge, and the grain holds both marks as "
            "one small injury. Morning leaves the arrangement in place. Dust "
            "does not merely settle; it thickens along the path where a hand "
            "dragged the chair, where a foot paused, where air from the cracked "
            "window pushed the loose line sideways. The spoon lies against the "
            "saucer with its bowl turned toward the fracture, and the chipped "
            "edge keeps the sound of the fall in its shape. Nothing announces "
            "itself apart from pressure, residue, and position.\n\n"
            "The table stays ordinary because it keeps taking these touches "
            "seriously. The cup-ring darkens where weight met wood. The crumb "
            "does not stand aside from passage; it lodges where the wet circle caught "
            "it. Dust gathers in the hand-drag, foot-pause, and window-breath "
            "until the surface records a route. The spoon points the eye back "
            "to the saucer's split, and the split keeps the fall from becoming "
            "talk. By the time the kitchen is noticed, object has already "
            "entered object, pressure has already become mark, and each mark "
            "has changed the next thing the reader can trust."
        ),
        "target_unit_mappings": _hostile_intervention_mapping(units),
        "intervention_plan": [
            "materially re-author each hostile scaffold target unit",
            "carry meaning through object sequence instead of thesis summary",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "only replacement_region_text is supplied",
                "risk_note": "controller owns final assembly",
            }
        ],
        "protected_effects_notes": [
            "proof/no-answer pressure remains protected",
            "opening-return and reread gains remain protected",
            "object/tactile causal field remains active",
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no rival imitation",
            "no generic vividness",
        ],
        "uncertainty": "strong hostile scaffold stub output for tests only",
    }


def _ending_intervention_mapping(units):
    return [
        {
            "target_unit_id": str(unit["unit_id"]),
            "before_text_sha256": str(unit.get("before_text_sha256") or ""),
            "mechanism_operation": (
                "make final return happen through object relation and reader encounter"
            ),
            "material_relation_or_action": str(
                unit.get("current_physical_relation")
                or unit.get("current_motion_action_state")
                or "same table object field carries return pressure"
            ),
            "visible_consequence": (
                "the returned object field keeps proof/no-answer pressure without solving it"
            ),
            "intended_first_read_effect": (
                "reader feels final return as altered relation before explanation"
            ),
            "protected_effects_preserved": [
                "opening-return relation remains active",
                "proof/no-answer pressure remains pressure",
                "object table dust spoon saucer ring field returns",
            ],
            "covered_target_ids": [str(unit["unit_id"])],
        }
        for unit in units
    ]


def _valid_ending_residual_intervention_payload(units):
    return {
        "replacement_region_text": (
            "Then the return comes through the table, not as reset: the cup ring "
            "pulls the crumb deeper into grain, dust keeps the hand-foot mark, "
            "and the spoon leans toward the saucer split. The ring will still be "
            "ring and dust still dust, but each mark now carries the first "
            "morning inside it. It will come back through the table as proof "
            "held in objects, not as an answer."
        ),
        "target_unit_mappings": _ending_intervention_mapping(units),
        "intervention_plan": [
            "replace only the selected final-return region",
            "make return happen through the same object field",
            "preserve proof/no-answer carry without explaining the return",
        ],
        "constraint_mapping": [
            {
                "constraint_id": "bounded_selected_region",
                "how_satisfied": "bounded replacement region only",
                "risk_note": "controller owns final assembly",
            }
        ],
        "protected_effects_notes": [
            "opening-return reread gains preserved",
            "proof/no-answer pressure preserved as pressure",
            "object/tactile field with table dust spoon saucer ring preserved",
            "strongest-rival pressure remains blocking",
        ],
        "forbidden_change_self_check": [
            "no finality claim",
            "no phase-shift claim",
            "no nonselected region edits",
            "no rival imitation",
            "no return explanation",
        ],
        "uncertainty": "strong ending-return stub output for tests only",
    }


def _ending_packet_0068_like_residual_payload(units):
    payload = _valid_ending_residual_intervention_payload(units)
    payload["replacement_region_text"] = (
        "If it comes, the return passes through the table and the dust, through "
        "the spoon on its side and the saucer with its crack, and the room takes "
        "it in without clearing. The ring stays a ring, the dust stays dust; "
        "the grain holds the morning, the gray under the edge keeps the day "
        "before, and the opening is altered by what has crossed the table, not "
        "told over again. Nothing here settles into a reset; the same table "
        "field remains under pressure, and the return leaves proof asking "
        "without answering."
    )
    payload["intervention_plan"] = [
        "packet 0068-like ending-return regression shape",
        "uses negated clearing/reset language that should not fail by itself",
    ]
    payload["constraint_mapping"] = [
        {
            "constraint_id": "no_reset_or_finality",
            "how_satisfied": "explicitly rejects reset and preserves carried pressure",
            "risk_note": "negated reset wording must not be treated as reset semantics",
        }
    ]
    return payload


def _ending_packet_0069_like_residual_payload(units):
    payload = _valid_ending_residual_intervention_payload(units)
    payload["replacement_region_text"] = (
        "The return does not arrive as an explanation; it presses in with the "
        "table, the dust, the spoon laid on its side, the saucer's crack, and "
        "the same room that held the strain before. The ring stays ring, the "
        "dust stays dust, but the grain keeps the morning and the gray under "
        "the edge keeps the day before, so the opening comes back altered by "
        "what it has held. Nothing is wiped clean or started over: the pressure "
        "remains in the objects, and the proof of it is still no answer, only "
        "what the room keeps carrying."
    )
    payload["intervention_plan"] = [
        "packet 0069-like ending-return regression shape",
        "materially engaged units with opaque global relation failure",
    ]
    payload["constraint_mapping"] = [
        {
            "constraint_id": "opening_return_relation",
            "how_satisfied": "not satisfied clearly enough",
            "risk_note": (
                "uses negated explanation, object-list pressure, and opening "
                "comes back altered shortcut"
            ),
        }
    ]
    return payload


def _ending_clearing_reset_residual_payload(units):
    payload = _valid_ending_residual_intervention_payload(units)
    payload["replacement_region_text"] = (
        "The return clears the table, dust, spoon, saucer, and ring into a reset, "
        "and the room restarts the pressure as if the earlier marks had been made "
        "new. The opening comes back as the same table wiped clean, and the proof "
        "now answers itself instead of remaining a pressure in the objects. The "
        "return repeats the morning without carry, with the scene restarted and "
        "the record erased."
    )
    payload["intervention_plan"] = [
        "invalid ending-return reset regression shape",
        "turns return into clearing, restart, repetition, and answer",
    ]
    payload["constraint_mapping"] = [
        {
            "constraint_id": "no_reset_or_finality",
            "how_satisfied": "not satisfied",
            "risk_note": "contains reset and clearing language",
        }
    ]
    return payload


def _ending_packet_0070_like_residual_payload(units):
    payload = _valid_ending_residual_intervention_payload(units)
    by_unit = {str(unit["unit_id"]): unit for unit in units}
    final_before = str(
        by_unit.get("final_return_enacts_not_explains", {}).get("before_text")
        or "So the return is not a reset."
    )
    object_field_before = str(
        by_unit.get("same_object_field_returns_without_summary", {}).get("before_text")
        or "Morning comes back to the same table, but the table has kept the record of relation inside itself."
    )
    proof_before = str(
        by_unit.get("proof_no_answer_carry_preserved", {}).get("before_text")
        or final_before
    )
    payload["replacement_region_text"] = (
        f"{final_before} {object_field_before} {proof_before} The ring remains "
        "near the table and the dust remains near the edge, but the relation "
        "does not gain enough new object pressure to carry the ending."
    )
    payload["intervention_plan"] = [
        "packet 0070-like ending-return exact-copy/object-pressure failure shape",
        "copies overlapping target units while under-enacting global return relation",
    ]
    payload["constraint_mapping"] = [
        {
            "constraint_id": "opening_return_relation",
            "how_satisfied": "not satisfied",
            "risk_note": "same-unit exact copy and object-pressure relation remains too weak",
        }
    ]
    return payload


def _protected_context_stable_residual_payload(units, selected_region):
    paragraphs = selected_region.split("\n\n")
    protected = paragraphs[1] if len(paragraphs) > 1 else ""
    first = _tactile_stub_replacement_from_units(units).split("\n\n")[0]
    payload = _valid_residual_intervention_payload(units)
    payload["replacement_region_text"] = (
        first + ("\n\n" + protected if protected else "")
    )
    return payload


def _tactile_stub_replacement_from_units(units):
    sentences = []
    for unit in units:
        labels = [str(value) for value in unit.get("objects", []) if str(value)]
        if not labels:
            labels = ["object", "surface", "mark"]
        label_phrase = " ".join(labels[:5])
        relation = str(
            unit.get("current_physical_relation")
            or unit.get("current_motion_action_state")
            or "contact pressure leaves a mark"
        )
        sentences.append(
            f"The {label_phrase} relation works through contact and pressure: "
            f"{relation}, so a visible mark remains as material consequence before "
            "any explanation names it."
        )
    return (
        " ".join(sentences)
        + "\n\nAt first, the room seems only ordinary. But ordinary things are "
        "strict about what reaches them. Pressure crosses a surface and the mark "
        "changes what the next object can be; residue, displacement, and breakage "
        "hold the force locally before thought turns it into a rule."
    )


def residual_intervention_stub_factory(clients, *, mode: str = "valid"):
    def _factory(model: str) -> StubResidualInterventionClient:
        client = StubResidualInterventionClient(model=model, mode=mode)
        clients.append(client)
        return client

    return _factory


class DynamicObjectMotionCausalityClient:
    provider = "openai"

    def __init__(self, *, model: str) -> None:
        self.model = model
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if request.schema != OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA:
            raise AssertionError(f"unexpected schema: {request.schema.name}")
        prompt = json.loads(request.input_text)
        units = prompt["target_units"]
        object_groups = [
            [str(value) for value in unit.get("objects", [])][:3] for unit in units
        ]
        replacement_sentences = []
        mapping = []
        for index, unit in enumerate(units):
            objects = object_groups[index]
            first = objects[0]
            second = objects[1] if len(objects) > 1 else objects[0]
            third = objects[2] if len(objects) > 2 else objects[-1]
            action = (
                f"{first} slides against {second} and pulls {third} into the record"
            )
            consequence = (
                f"{second} leaves a visible mark and {third} changes the next object"
            )
            sentence = (
                f"The {first} slides against the {second} and pulls the {third} "
                "into a narrow track that leaves a visible mark before the "
                "passage explains it."
            )
            replacement_sentences.append(sentence)
            mapping.append(
                {
                    "unit_id": str(unit["unit_id"]),
                    "before_text_excerpt": str(unit.get("before_text", ""))[:220],
                    "replacement_text_excerpt": sentence,
                    "object_motion_or_action": action,
                    "visible_consequence": consequence,
                    "how_reader_infers_pressure_before_explanation": (
                        "the object movement leaves a mark before explanation"
                    ),
                    "forbidden_change_avoided": (
                        "no new object list, rival mimicry, full rewrite, or finality claim"
                    ),
                }
            )
        replacement = (
            " ".join(replacement_sentences)
            + " The room remains bounded to the selected middle, but the local "
            "motions now carry the pressure through marks and altered surfaces "
            "before any rule is named. These consequences keep the passage "
            "ordinary while making each object change the condition of the next."
        )
        return dump_json(
            {
                "replacement_region_text": replacement,
                "object_motion_generation_plan": [
                    "replace only the selected region",
                    "derive object terms from the provided target units",
                    "make each object movement leave visible consequence",
                ],
                "target_unit_mapping": mapping,
                "protected_effects_preservation_notes": [
                    "opening field remains untouched",
                    "proof/no-answer and final return are untouched",
                ],
                "uncertainty": "stub output for dynamic object-term validation",
                "predicted_reader_effect": (
                    "reader sees target-unit object motion causing visible consequence"
                ),
                "forbidden_change_self_check": [
                    "no finality claim",
                    "no phase-shift claim",
                    "no nonselected region edits",
                    "no rival mimicry",
                ],
            }
        )


def dynamic_object_motion_stub_factory(clients):
    def _factory(model: str) -> DynamicObjectMotionCausalityClient:
        client = DynamicObjectMotionCausalityClient(model=model)
        clients.append(client)
        return client

    return _factory


def live_macro_payload(
    active_targets: list[dict[str, object]] | None = None,
    *,
    target_movement: str = "middle_and_return_movement",
    target_paragraphs: list[dict[str, object]] | None = None,
    target_spans: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    replacement = (
        "The room does not need a new witness. The ring on the wood has dried "
        "lighter at one rim, and the spoon has turned a small brightness toward "
        "the saucer as if the night had moved through metal before it moved "
        "through thought. Dust gathers under the table leg in a shape the shoe "
        "made and then abandoned. The facts do not explain themselves, but they "
        "lean into one another until the leaning becomes the pressure.\n\n"
        "What matters is not that the room has become symbolic. It is that each "
        "object carries a mark it cannot complete alone. The cup left the ring, "
        "the ring changed the surface, the dust kept the path, and the path "
        "points back to a body already gone. A law appears only as this crossing, "
        "one condition tightening another until proof has no separate platform "
        "to stand on.\n\n"
        "The silence above the kitchen does not comfort the line or excuse it. "
        "It holds the conditions shut, so the pressure has to remain local. Help "
        "does not enter as a second story. The table, dust, spoon, saucer, ring, "
        "and weak light must bear the change they made together.\n\n"
        "So the return is not a reset. Morning comes back to the same table, but "
        "the table has kept the record of relation inside itself. The objects are "
        "ordinary and still altered by one another. The room has not been solved; "
        "it has become readable as the place where its own pressure learned to "
        "hold."
    )
    return {
        "replacement_section_text": replacement,
        "macro_recomposition_plan": {
            "plan_summary": "Replace the target movement with object-event pressure.",
            "plan_steps": [
                "keep the selected opening unchanged",
                "move explanation into domestic object crossings",
                "return through record-bearing relation rather than summary",
            ],
        },
        "section_plan": {
            "target_movement": target_movement,
            "bounded": True,
            "full_rewrite": False,
            "rationale": "The target movement can be recomposed as one bounded section.",
        },
        "constraint_mapping": [
            {
                "constraint_id": constraint_id,
                "satisfied_claim": True,
                "supporting_replacement_excerpt": "the objects keep relation inside the room",
                "rationale": "The claim is carried by object relation, not a label.",
                "uncertainty": "medium",
                "risk_note": "needs later reader or ablation validation",
            }
            for constraint_id in REQUIRED_SEMANTIC_CONSTRAINT_IDS
        ],
        "active_target_mapping": active_target_mapping_payload(active_targets),
        "target_paragraph_replacements": target_paragraph_replacements_payload(
            target_paragraphs or []
        ),
        "target_span_replacements": target_span_replacements_payload(
            target_spans or []
        ),
        "rationale": "The bounded section shifts pressure into scene and relation.",
        "local_law_explanation": "Each local mark becomes legible through another mark.",
        "uncertainty": "medium",
        "predicted_reader_state_effect": (
            "The reader should feel the return as changed relation rather than explanation."
        ),
    }


def target_paragraph_replacements_payload(
    target_paragraphs: list[dict[str, object]],
) -> list[dict[str, object]]:
    replacements: list[dict[str, object]] = []
    for index, paragraph in enumerate(target_paragraphs):
        ref = str(paragraph["target_paragraph_ref"])
        replacements.append(
            {
                "target_paragraph_ref": ref,
                "before_text_sha256": str(paragraph["before_text_sha256"]),
                "replacement_text": target_replacement_text(ref, index),
                "active_target_ids_covered": list(paragraph.get("active_target_ids", [])),
                "material_change_summary": (
                    "This paragraph is materially rewritten around its assigned active targets."
                ),
                "preserved_effects": list(paragraph.get("protected_effects", [])),
                "risk_notes": "needs later ablation or internal reader-state validation",
                "uncertainty": "medium",
            }
        )
    return replacements


def target_span_replacements_payload(
    target_spans: list[dict[str, object]],
) -> list[dict[str, object]]:
    replacements: list[dict[str, object]] = []
    for span in target_spans:
        if not span.get("material_change_required"):
            continue
        parent_ref = str(span["parent_target_paragraph_ref"])
        replacements.append(
            {
                "target_span_ref": str(span["target_span_ref"]),
                "parent_target_paragraph_ref": parent_ref,
                "before_text_sha256": str(span["before_text_sha256"]),
                "replacement_excerpt": target_replacement_text(parent_ref, 0),
                "active_target_ids_covered": list(span.get("active_target_ids", [])),
                "material_change_summary": (
                    "This required span is materially changed inside the parent target."
                ),
                "risk_notes": "needs later ablation or internal reader-state validation",
                "uncertainty": "medium",
            }
        )
    return replacements


def target_replacement_text(target_ref: str, index: int) -> str:
    replacements = {
        "target_p001": (
            "The room does not need a witness above it. The ring dries at the edge "
            "where the cup left pressure in the wood, and the dust under the leg "
            "keeps the path of a shoe that is already gone. The spoon turns its dull "
            "light toward the cracked saucer. The proof begins as those marks lean "
            "into one another, not as a sentence placed over them."
        ),
        "target_p002": (
            "No answer enters from outside the kitchen. The silence overhead closes "
            "the room around its own evidence, so the ring, the dust, the spoon, and "
            "the saucer have to carry the relation they made. If the line proves "
            "anything, it proves by staying with those traces until one mark becomes "
            "the condition for reading the next."
        ),
        "target_p003": (
            "The return touches the first table without restoring it. Morning gives "
            "back the same wood, the same dust, the same spoon beside the saucer, but "
            "the objects now hold the crossing that passed through them. The beginning "
            "comes back as a local field already altered by its own marks, not as a "
            "lesson waiting outside the room."
        ),
        "target_p004": (
            "The final return keeps the table ordinary while making the opening "
            "rereadable. Morning does not solve the room; it lets the same wood, dust, "
            "spoon, and saucer hold their changed relation together. The answer stays "
            "inside that local field, as pressure remembered rather than announced."
        ),
    }
    return replacements.get(
        target_ref,
        (
            f"The target paragraph {index + 1} is recomposed through local object "
            "relations, preserving pressure without turning the passage into summary."
        ),
    )


def _copy_target_paragraph(
    payload: dict[str, object],
    target_paragraphs: list[dict[str, object]],
    target_ref: str,
) -> None:
    before_by_ref = {
        str(paragraph["target_paragraph_ref"]): str(paragraph["before_text"])
        for paragraph in target_paragraphs
    }
    for item in payload.get("target_paragraph_replacements", []):
        if item["target_paragraph_ref"] == target_ref:
            item["replacement_text"] = before_by_ref[target_ref]


def _append_target_paragraph_claim(
    payload: dict[str, object],
    target_ref: str,
    target_id: str,
) -> None:
    for item in payload.get("target_paragraph_replacements", []):
        if item["target_paragraph_ref"] == target_ref:
            item.setdefault("active_target_ids_covered", []).append(target_id)
            return


def _replace_target_paragraph_claims(
    payload: dict[str, object],
    target_ref: str,
    target_ids: list[str],
) -> None:
    for item in payload.get("target_paragraph_replacements", []):
        if item["target_paragraph_ref"] == target_ref:
            item["active_target_ids_covered"] = list(target_ids)
            return


def _append_first_required_target_span_claim(
    payload: dict[str, object],
    target_spans: list[dict[str, object]],
    parent_ref: str,
    target_id: str,
) -> None:
    span_ref = _first_required_target_span_ref(target_spans, parent_ref)
    if not span_ref:
        return
    for item in payload.get("target_span_replacements", []):
        if item["target_span_ref"] == span_ref:
            item.setdefault("active_target_ids_covered", []).append(target_id)
            return


def _replace_first_required_target_span_claims(
    payload: dict[str, object],
    target_spans: list[dict[str, object]],
    parent_ref: str,
    target_ids: list[str],
) -> None:
    span_ref = _first_required_target_span_ref(target_spans, parent_ref)
    if not span_ref:
        return
    for item in payload.get("target_span_replacements", []):
        if item["target_span_ref"] == span_ref:
            item["active_target_ids_covered"] = list(target_ids)
            return


def _first_required_target_span_ref(
    target_spans: list[dict[str, object]],
    parent_ref: str,
) -> str:
    for span in target_spans:
        if (
            span.get("material_change_required")
            and span.get("parent_target_paragraph_ref") == parent_ref
        ):
            return str(span["target_span_ref"])
    return ""


def _near_copy_target_paragraph(
    payload: dict[str, object],
    target_paragraphs: list[dict[str, object]],
    target_ref: str,
) -> None:
    before_by_ref = {
        str(paragraph["target_paragraph_ref"]): str(paragraph["before_text"])
        for paragraph in target_paragraphs
    }
    before_text = before_by_ref[target_ref]
    replacement_text = (
        before_text.replace("will not be regression", "will not be a reset")
        .replace(
            "The beginning is not restored untouched.",
            "The beginning is not untouched when it comes back.",
        )
        .replace("restored untouched", "untouched")
    )
    for item in payload.get("target_paragraph_replacements", []):
        if item["target_paragraph_ref"] == target_ref:
            item["replacement_text"] = replacement_text


def _copy_target_with_changed_proof_only(
    payload: dict[str, object],
    target_paragraphs: list[dict[str, object]],
    target_ref: str,
) -> None:
    before_by_ref = {
        str(paragraph["target_paragraph_ref"]): str(paragraph["before_text"])
        for paragraph in target_paragraphs
    }
    before_text = before_by_ref[target_ref]
    sentences = _test_sentence_like_spans(before_text)
    replacement_sentences = list(sentences)
    proof_index = next(
        (
            index
            for index, sentence in enumerate(sentences)
            if "proof" in sentence.lower() or "proves" in sentence.lower()
        ),
        max(len(sentences) - 1, 0),
    )
    if replacement_sentences:
        replacement_sentences[proof_index] = (
            "Proof tightens through the ring, dust, spoon, and saucer instead of "
            "standing above the room as a thesis."
        )
    replacement_text = " ".join(replacement_sentences)
    for item in payload.get("target_paragraph_replacements", []):
        if item["target_paragraph_ref"] == target_ref:
            item["replacement_text"] = replacement_text


def _test_sentence_like_spans(text: str) -> list[str]:
    sentences: list[str] = []
    current: list[str] = []
    for character in text.strip():
        current.append(character)
        if character in ".!?":
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    remainder = "".join(current).strip()
    if remainder:
        sentences.append(remainder)
    return sentences or [text.strip()]


def _remove_first_required_target_span(
    payload: dict[str, object],
    target_spans: list[dict[str, object]],
    parent_ref: str,
) -> None:
    required_refs = [
        str(span["target_span_ref"])
        for span in target_spans
        if span.get("material_change_required")
        and span.get("parent_target_paragraph_ref") == parent_ref
    ]
    if not required_refs:
        return
    payload["target_span_replacements"] = [
        item
        for item in payload["target_span_replacements"]
        if item["target_span_ref"] != required_refs[0]
    ]


def _mismatch_first_required_target_span_hash(
    payload: dict[str, object],
    target_spans: list[dict[str, object]],
) -> None:
    required_refs = [
        str(span["target_span_ref"])
        for span in target_spans
        if span.get("material_change_required")
    ]
    if not required_refs:
        return
    for item in payload["target_span_replacements"]:
        if item["target_span_ref"] == required_refs[0]:
            item["before_text_sha256"] = "bad-span-hash"
            return


def _successful_retry_override(
    prompt: dict[str, object],
    target_ref: str,
) -> dict[str, object] | None:
    for item in prompt.get("successful_first_attempt_replacements", []):
        if isinstance(item, dict) and item.get("target_paragraph_ref") == target_ref:
            override = dict(item)
            override["replacement_text"] = (
                "This attempted retry override should never replace the successful "
                "first-attempt target paragraph."
            )
            override["material_change_summary"] = "attempted override of a passed ref"
            return override
    return None


def active_target_mapping_payload(
    active_targets: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    if not active_targets:
        active_targets = [
            {"target_id": target_id, "target_paragraph_ref": "target_section"}
            for target_id in ACTIVE_TRANSFORMATION_TARGET_IDS
        ]
    return [
        {
            "target_id": str(target["target_id"]),
            "target_paragraph_ref": str(target.get("target_paragraph_ref") or "target_section"),
            "before_excerpt": "controller-owned target paragraph",
            "supporting_replacement_excerpt": (
                "object marks lean into one another until the leaning becomes pressure"
            ),
            "what_changed": (
                "The target is materially recomposed through object-event relation."
            ),
            "rationale": "The model reports a bounded material transformation.",
            "uncertainty": "medium",
            "unchanged": str(target["target_id"]) == "preserve_reader_state_partial_gain",
            "unchanged_justification": (
                "Preservation is the intended result for this non-material target."
                if str(target["target_id"]) == "preserve_reader_state_partial_gain"
                else ""
            ),
        }
        for target in active_targets
    ]


def copied_target_replacement(
    prompt: dict[str, object],
    *,
    copied_indexes: set[int],
) -> str:
    before_paragraphs = [
        paragraph.strip()
        for paragraph in str(prompt["before_section_text"]).split("\n\n")
        if paragraph.strip()
    ]
    replacement_paragraphs = [
        paragraph.strip()
        for paragraph in str(live_macro_payload()["replacement_section_text"]).split("\n\n")
        if paragraph.strip()
    ]
    result = []
    for index, before in enumerate(before_paragraphs):
        if index in copied_indexes:
            result.append(before)
        elif index < len(replacement_paragraphs):
            result.append(replacement_paragraphs[index])
        else:
            result.append(
                "The local object field changes this paragraph through relation, "
                "not through explanation."
            )
    return "\n\n".join(result)


class InvalidOldNewRivalProvenanceClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA:
            payload["judgment_provenance"]["reread_transformation_improved"].append(
                "The revised closing remains image-led and therefore reads better."
            )
            return dump_json(payload)
        return raw_output


def custom_revision_factory(clients: list[FakeAutonomousRevisionModelClient], client_cls):
    def _factory(model: str) -> FakeAutonomousRevisionModelClient:
        client = client_cls(provider="openai", model=model)
        clients.append(client)
        return client

    return _factory


def assert_strict_object_schema(schema: object, *, path: str) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False, path
        if "properties" in schema:
            for key, value in schema["properties"].items():
                assert_strict_object_schema(value, path=f"{path}.properties.{key}")
        if "items" in schema:
            assert_strict_object_schema(schema["items"], path=f"{path}.items")
        for key in ("anyOf", "allOf", "oneOf"):
            for index, value in enumerate(schema.get(key, [])):
                assert_strict_object_schema(value, path=f"{path}.{key}[{index}]")
        for key in ("$defs", "definitions"):
            for name, value in schema.get(key, {}).items():
                assert_strict_object_schema(value, path=f"{path}.{key}.{name}")
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            assert_strict_object_schema(value, path=f"{path}[{index}]")


def assert_openai_strict_object_schema(schema: object, *, path: str) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False, path
            properties = schema.get("properties")
            required = schema.get("required")
            assert isinstance(properties, dict), path
            assert isinstance(required, list), path
            assert set(required) == set(properties), path
        if "properties" in schema:
            for key, value in schema["properties"].items():
                assert_openai_strict_object_schema(
                    value,
                    path=f"{path}.properties.{key}",
                )
        if "items" in schema:
            assert_openai_strict_object_schema(
                schema["items"],
                path=f"{path}.items",
            )
        for key in ("anyOf", "allOf", "oneOf"):
            for index, value in enumerate(schema.get(key, [])):
                assert_openai_strict_object_schema(
                    value,
                    path=f"{path}.{key}[{index}]",
                )
        for key in ("$defs", "definitions"):
            for name, value in schema.get(key, {}).items():
                assert_openai_strict_object_schema(
                    value,
                    path=f"{path}.{key}.{name}",
                )
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            assert_openai_strict_object_schema(value, path=f"{path}[{index}]")


def assert_valid_work_order_payload(
    *,
    work_order: dict[str, object],
    candidate_text: str,
    expected_artifact_id: str,
) -> None:
    assert work_order["controller_owned"] is True
    assert work_order["work_order_id"] == "revision_work_order_001"
    assert work_order.get("work_order_artifact_id") in {expected_artifact_id, None}
    assert work_order["source_candidate"]["text_sha256"]
    assert work_order["candidate_text_length"] == len(candidate_text)
    assert work_order["original_candidate_text_sha256"] == work_order["source_candidate"][
        "text_sha256"
    ]
    assert work_order["allowed_ablation_variant_ids"] == list(
        AUTONOMOUS_REVISION_ALLOWED_ABLATION_VARIANT_IDS
    )
    assert work_order["allowed_ablation_probe_ids"] == list(
        AUTONOMOUS_REVISION_ALLOWED_ABLATION_PROBE_IDS
    )
    assert set(work_order["allowed_provenance_tokens"]) == set(
        AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS
    )
    span_ids = {span["patch_span_id"] for span in work_order["patchable_spans"]}
    for paragraph in work_order["paragraph_inventory"]:
        assert candidate_text[paragraph["char_start"] : paragraph["char_end"]] == paragraph[
            "exact_text"
        ]
    for item in work_order["candidate_sentence_span_inventory"]:
        assert item["candidate_span_id"].startswith("candidate_span_")
        assert candidate_text[item["char_start"] : item["char_end"]] == item["exact_text"]
    for target in work_order["allowed_patch_targets"]:
        assert target["patch_target_id"].startswith("target_")
        assert "/" not in target["patch_target_id"]
        assert " " not in target["patch_target_id"]
        assert target["text_window_authoritative"] is False
        assert target["member_patch_span_ids"]
        assert set(target["member_patch_span_ids"]) <= span_ids
    for span in work_order["patchable_spans"]:
        assert span["patch_span_id"].startswith("span_")
        assert "/" not in span["patch_span_id"]
        assert " " not in span["patch_span_id"]
        assert candidate_text[span["char_start"] : span["char_end"]] == span["exact_text"]


def test_autonomous_revision_fake_creates_closed_loop_artifacts(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config, lab_payload = build_reader_lab_packet(tmp_path)

    with connect(config.db_path) as connection:
        before_count = len(list_artifacts(connection, lab_payload["run_id"]))

    result = run_autonomous_revision(
        config,
        client_name="fake",
        reader_lab_packet=lab_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "fake"
    assert set(result.payload["artifact_ids"]) == set(AUTONOMOUS_REVISION_ARTIFACT_TYPES)
    assert result.payload["counts"] == {
        "autonomous_revision_artifacts": 13,
        "required_autonomous_revision_artifacts": 13,
        "model_calls": 0,
        "recorded_autonomous_gates": 5,
    }
    assert Path(result.payload["packet_dir"]) == (
        tmp_path
        / "runs"
        / result.payload["run_id"]
        / "autonomous_revision"
        / "packet_0001"
    )

    selected = read_payload(result.payload["artifact_paths"]["selected_failure_diagnosis"])
    assert selected["selected_failure_type"] in selected["all_failure_types_present"]
    assert selected["reader_lab_evidence_artifacts"]
    assert "forensic_grounding_report" in selected["reader_lab_evidence_artifacts"]

    work_order = read_payload(
        result.payload["artifact_paths"][AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE]
    )
    assert_valid_work_order_payload(
        work_order=work_order,
        candidate_text=candidate_text_from_reader_lab_packet(lab_payload["packet_dir"]),
        expected_artifact_id=result.payload["artifact_ids"][
            AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
        ],
    )

    handle = read_payload(result.payload["artifact_paths"]["causal_handle_selection"])
    assert handle["revision_work_order_artifact_id"] == result.payload["artifact_ids"][
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
    ]
    assert handle["bounded_target"] is True
    assert handle["target_count"] == 1
    assert handle["span_ref"]["source_class"] == "abi_candidate"
    for key in (
        "quoted_text",
        "local_law_hypothesis",
        "suspected_failure",
        "why_it_might_be_junk",
        "why_it_might_be_treasure",
        "connotation_or_register_risk",
        "variant_probe",
        "ablation_probe",
        "expected_reader_state_change",
        "uncertainty",
    ):
        assert handle[key]

    patch_proposal = read_payload(result.payload["artifact_paths"]["revision_patch_proposal"])
    assert patch_proposal["patches"]
    assert patch_proposal["patches"][0]["patch_target_id"] == handle[
        "allowed_patch_targets"
    ][0]["patch_target_id"]
    assert patch_proposal["full_rewrite"] is False
    assert patch_proposal["bounded_patch_set"] is True

    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    assert revised["text"]
    assert revised["assembled_by_controller"] is True
    assert revised["work_order_artifact_id"] == result.payload["artifact_ids"][
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
    ]
    assert revised["source_patch_ids"] == ["patch_01"]
    assert revised["source_patch_target_ids"]
    assert revised["bounded_recomposition"] is True
    assert revised["full_rewrite"] is False
    assert revised["non_final"] is True
    assert revised["candidate_only"] is True
    assert revised["not_human_validated"] is True
    assert revised["not_finalization_eligible"] is True
    assert revised["finalization_eligible"] is False
    assert revised["phase_shift_claim"] is False

    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    assert diff["assembled_by_controller"] is True
    assert diff["work_order_artifact_id"] == result.payload["artifact_ids"][
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
    ]
    assert diff["source_patch_ids"] == ["patch_01"]
    assert diff["source_patch_target_ids"]
    assert diff["full_rewrite"] is False
    assert diff["bounded_change"] is True
    assert diff["operation"]["type"] == "insert_after"

    variants = read_payload(result.payload["artifact_paths"]["ablation_variant_set"])
    operations = {variant["operation"] for variant in variants["variants"]}
    assert {
        "remove_suspected_causal_handle",
        "replace_suspected_word_phrase_image",
        "flatten_metaphor",
        "move_motif_earlier_later",
        "remove_ending_echo",
        "restore_old_wording",
        "correct_or_normalize_irregularity",
        "damage_or_roughen_too_smooth_phrase",
    } == operations

    ablation = read_payload(result.payload["artifact_paths"]["ablation_reread_comparison"])
    assert ablation["comparison_rows"]

    comparison = read_payload(result.payload["artifact_paths"]["old_new_rival_comparison"])
    assert comparison["revised_candidate"]["artifact_id"] == result.payload["artifact_ids"][
        "revised_candidate_text"
    ]
    assert comparison["another_revision_cycle_needed"] is True
    assert comparison["comparison_basis"] == "deterministic fake internal comparison, not human data"

    local_law = read_payload(result.payload["artifact_paths"]["local_law_case_note"])
    assert "No feature is globally good or bad" in local_law["principle"]
    assert local_law["preserve_irregularity_rule"]

    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_closed_loop_gate_report"])
    assert gate_report["eligible"] is False
    assert gate_report["human_validation_required"] is False
    assert gate_report["paper_validation_required"] is False
    assert gate_report["phase_shift_claim"] is False
    assert "no_fixture_only_core_evidence" in gate_report["failed_gates"]
    assert "no_unresolved_internal_blockers" in gate_report["failed_gates"]
    assert "internal_operator_approval" in gate_report["missing_gates"]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        latest_run = get_latest_run(connection)
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(artifacts) == before_count + len(AUTONOMOUS_REVISION_ARTIFACT_TYPES)
    assert latest_run.active_phase == AUTONOMOUS_CLOSED_LOOP_REVISION_ACTIVE_PHASE
    revision_artifacts = {
        artifact.type: artifact
        for artifact in artifacts
        if artifact.type in AUTONOMOUS_REVISION_ARTIFACT_TYPES
    }
    assert set(revision_artifacts) == set(AUTONOMOUS_REVISION_ARTIFACT_TYPES)
    for artifact in revision_artifacts.values():
        envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        assert envelope["schema_version"] == "1"
        assert envelope["artifact_type"] == artifact.type
        assert envelope["fixture_only"] is True
        assert envelope["model_call_id"] is None
        assert envelope["parent_ids"] == artifact.parent_ids
        assert Path(artifact.path).is_relative_to(Path(result.payload["packet_dir"]))

    assert final_report.refused is True
    combined_blockers = " ".join(final_report.missing_gates + final_report.failed_gates)
    assert "internal_operator_approval" in combined_blockers
    assert "no_fixture_only_core_evidence" in combined_blockers
    assert "no_unresolved_internal_blockers" in combined_blockers
    assert "real_human_validation_passed" not in combined_blockers
    assert "paper" not in final_report.message.lower()


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda payload: payload["allowed_patch_targets"][0].update(
                {"patch_target_id": "target_ending_return/bad"}
            ),
            "lowercase letters, digits, and underscores",
        ),
        (
            lambda payload: payload["allowed_patch_targets"][0].update(
                {"patch_target_id": "ending paragraph especially the return"}
            ),
            "must start with 'target_'",
        ),
        (
            lambda payload: payload["patchable_spans"][0].update(
                {"patch_span_id": "span_ending prose id"}
            ),
            "must use only lowercase letters, digits, and underscores",
        ),
        (
            lambda payload: payload["patchable_spans"][0].update(
                {"exact_text": "not present in the candidate"}
            ),
            "exact_text does not match candidate_text",
        ),
        (
            lambda payload: payload["patchable_spans"][0].update({"char_end": 0}),
            "char_start/char_end are invalid",
        ),
    ],
)
def test_revision_work_order_rejects_noncanonical_or_invalid_inventory(
    tmp_path,
    mutator,
    message,
):
    config, lab_payload = build_reader_lab_packet(tmp_path)
    result = run_autonomous_revision(
        config,
        client_name="fake",
        reader_lab_packet=lab_payload["packet_dir"],
    )
    assert result.exit_code == 0
    subject = revision_subject_from_reader_lab_packet(config, lab_payload["packet_dir"])
    work_order = read_payload(
        result.payload["artifact_paths"][AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE]
    )
    mutated = json.loads(json.dumps(work_order))
    mutator(mutated)

    with pytest.raises(RevisionIntegrityError, match=message):
        _validate_revision_work_order_payload(subject, mutated)


def test_revision_work_order_allows_nonliteral_target_preview_when_member_spans_are_valid(
    tmp_path,
):
    config, lab_payload = build_reader_lab_packet(tmp_path)
    result = run_autonomous_revision(
        config,
        client_name="fake",
        reader_lab_packet=lab_payload["packet_dir"],
    )
    assert result.exit_code == 0
    subject = revision_subject_from_reader_lab_packet(config, lab_payload["packet_dir"])
    work_order = read_payload(
        result.payload["artifact_paths"][AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE]
    )
    mutated = json.loads(json.dumps(work_order))
    target = next(
        item
        for item in mutated["allowed_patch_targets"]
        if item["patch_target_id"] == "target_opening_first_pivots"
    )
    target["preview_text"] = "opening image span [...] non-contiguous advisory preview"
    target["text_window"] = target["preview_text"]
    assert target["text_window"] not in subject.candidate_text.text

    _validate_revision_work_order_payload(subject, mutated)


def test_invalid_work_order_construction_fails_before_downstream_model_calls(
    tmp_path,
    monkeypatch,
):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    def _bad_inventory(subject, primary_region):
        _ = subject, primary_region
        return [
            {
                "patch_target_id": "target_bad/slash",
                "target_region_label": "target_region:bad",
                "target_region_description": "bad slash target",
                "allowed_span_ref": "opening sentence",
                "text_window": "The table is still there in the morning.",
                "paragraph_index": 0,
                "protected_outside_spans": ["all outside bad target"],
            }
        ]

    monkeypatch.setattr(
        "abi.modules.autonomous_revision._controller_patch_target_inventory",
        _bad_inventory,
    )

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=revision_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "work-order validation failure" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert "causal_handle_selection" not in result.payload["artifact_ids"]
    assert AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE not in result.payload["artifact_ids"]
    assert len(clients[0].requests) == 1


def test_invalid_work_order_span_offsets_fail_before_downstream_model_calls(
    tmp_path,
    monkeypatch,
):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []
    original_builder = autonomous_revision_module._patchable_spans_for_target

    def _bad_spans(subject, target, sentence_inventory):
        spans = original_builder(subject, target, sentence_inventory)
        spans[0] = dict(spans[0])
        spans[0]["char_end"] = int(spans[0]["char_end"]) + 1
        return spans

    monkeypatch.setattr(
        autonomous_revision_module,
        "_patchable_spans_for_target",
        _bad_spans,
    )

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=revision_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "work-order validation failure" in result.payload["message"]
    assert "exact_text does not match candidate_text" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert "causal_handle_selection" not in result.payload["artifact_ids"]
    assert AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE not in result.payload["artifact_ids"]
    assert len(clients[0].requests) == 1


def test_autonomous_revision_packet_directory_is_unique(tmp_path):
    config, lab_payload = build_reader_lab_packet(tmp_path)

    first = run_autonomous_revision(
        config,
        client_name="fake",
        reader_lab_packet=lab_payload["packet_dir"],
    )
    second = run_autonomous_revision(
        config,
        client_name="fake",
        reader_lab_packet=lab_payload["packet_dir"],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.payload["packet_id"] == "packet_0001"
    assert second.payload["packet_id"] == "packet_0002"
    assert first.payload["packet_dir"] != second.payload["packet_dir"]
    assert set(first.payload["artifact_paths"].values()).isdisjoint(
        set(second.payload["artifact_paths"].values())
    )


def test_autonomous_revision_requires_reader_lab_packet(tmp_path):
    config = config_for(tmp_path)

    result = run_autonomous_revision(
        config,
        client_name="fake",
        reader_lab_packet=tmp_path / "missing_packet",
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "reader-lab packet directory not found" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_autonomous_revision_preserves_imported_rival_pressure(tmp_path):
    config, lab_payload = build_reader_lab_packet(tmp_path, with_rival=True)

    result = run_autonomous_revision(
        config,
        client_name="fake",
        reader_lab_packet=lab_payload["packet_dir"],
    )

    assert result.exit_code == 0
    comparison = read_payload(result.payload["artifact_paths"]["old_new_rival_comparison"])
    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_closed_loop_gate_report"])

    assert comparison["strongest_rival_present"] is True
    assert comparison["strongest_rival"]["label"] == "Text D"
    assert comparison["rival_still_beats_candidate"] in {True, False}
    rival_gate = {
        gate["gate_name"]: gate for gate in gate_report["gate_results"]
    }["rival_preservation_present"]
    assert rival_gate["passed"] is True
    assert "internal_operator_approval" in gate_report["missing_gates"]


def test_autonomous_revision_openai_refuses_without_allow(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, lab_payload = build_reader_lab_packet(tmp_path)

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_autonomous_revision_openai_refuses_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config, lab_payload = build_reader_lab_packet(tmp_path)

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_autonomous_revision_model_schemas_are_strict_objects():
    for schema in AUTONOMOUS_REVISION_MODEL_SCHEMAS:
        exposed = json_schema_for_worker_schema(schema)
        assert exposed["type"] == "object"
        assert exposed["required"]
        assert_strict_object_schema(exposed, path=schema.name)

    patch_schema = json_schema_for_worker_schema(AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA)
    patch_item = patch_schema["properties"]["patches"]["items"]
    assert patch_item["type"] == "object"
    assert patch_item["additionalProperties"] is False
    assert "patch_span_id" in patch_item["required"]
    assert "patch_target_id" in patch_item["required"]
    assert "original_excerpt" not in patch_item["properties"]
    assert "target_span_ref" not in patch_item["properties"]
    handle_schema = json_schema_for_worker_schema(AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA)
    assert "selected_patch_target_id" in handle_schema["required"]
    assert "allowed_patch_targets" not in handle_schema["properties"]

    variants_schema = json_schema_for_worker_schema(
        AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA
    )
    variant_item = variants_schema["properties"]["variants"]["items"]
    assert variant_item["type"] == "object"
    assert variant_item["additionalProperties"] is False
    diff_schema = json_schema_for_worker_schema(AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA)
    changed_span = diff_schema["properties"]["changed_spans"]["items"]
    for field in (
        "changed_span_id",
        "inside_target",
        "within_selected_target",
        "requires_target_expansion",
        "target_expansion_reason",
    ):
        assert field in changed_span["required"]


def test_ablation_comparison_schema_is_interpretation_only():
    schema = json_schema_for_worker_schema(AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA)
    row_schema = schema["properties"]["comparison_rows"]["items"]

    assert "variant_id" not in row_schema["properties"]
    assert "executed_variant_id" not in row_schema["properties"]
    assert "planned_probe_id" not in row_schema["properties"]
    assert "planned_only" not in row_schema["properties"]
    assert "evidence_basis" not in row_schema["properties"]
    assert "operation" not in row_schema["properties"]
    for field in (
        "row_id",
        "comparison_summary",
        "predicted_or_observed_effect",
        "reader_state_effect_estimate",
        "rationale",
        "risk_notes",
        "uncertainty",
        "not_human_data",
    ):
        assert field in row_schema["required"]

    parsed = parse_and_validate_structured_output(
        dump_json(valid_ablation_comparison_payload()),
        AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
    )

    assert parsed["comparison_rows"][0]["row_id"] == "ablation_row_001"
    assert "executed_variant_id" not in parsed["comparison_rows"][0]


def test_ablation_comparison_requires_reader_state_estimate():
    payload = valid_ablation_comparison_payload()
    del payload["comparison_rows"][0]["reader_state_effect_estimate"]

    with pytest.raises(ModelValidationError, match="reader_state_effect_estimate"):
        parse_and_validate_structured_output(
            dump_json(payload),
            AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
        )


def test_old_new_rival_provenance_schema_exposes_allowed_tokens():
    schema = json_schema_for_worker_schema(
        AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA
    )
    provenance = schema["properties"]["judgment_provenance"]
    rationale = schema["properties"]["judgment_rationale"]

    assert set(provenance["required"]) == set(AUTONOMOUS_REVISION_JUDGMENT_KEYS)
    assert set(rationale["required"]) == set(AUTONOMOUS_REVISION_JUDGMENT_KEYS)
    for key in AUTONOMOUS_REVISION_JUDGMENT_KEYS:
        token_schema = provenance["properties"][key]
        assert token_schema["items"]["enum"] == list(
            AUTONOMOUS_REVISION_PROVENANCE_SOURCE_TOKENS
        )
        assert rationale["properties"][key]["type"] == "string"


def test_old_new_rival_valid_provenance_and_rationale_pass_validation():
    payload = valid_old_new_rival_payload()

    parsed = parse_and_validate_structured_output(
        dump_json(payload),
        AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA,
    )

    assert parsed["judgment_provenance"]["rival_still_beats_candidate"] == [
        "revised_candidate_text",
        "strongest_rival_text",
    ]
    assert "stays outside provenance" in parsed["judgment_rationale"][
        "reread_transformation_improved"
    ]


def test_old_new_rival_prose_in_provenance_fails_validation():
    payload = valid_old_new_rival_payload()
    payload["judgment_provenance"]["reread_transformation_improved"].append(
        "The revised closing remains image-led and therefore reads better."
    )

    with pytest.raises(ModelValidationError, match="unsupported sources"):
        parse_and_validate_structured_output(
            dump_json(payload),
            AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA,
        )


def test_stubbed_openai_autonomous_revision_creates_model_backed_packet(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=revision_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "openai"
    assert result.payload["model"] == "stub-autonomous-revision-model"
    assert set(result.payload["artifact_ids"]) == set(AUTONOMOUS_REVISION_ARTIFACT_TYPES)
    assert result.payload["counts"] == {
        "autonomous_revision_artifacts": 13,
        "required_autonomous_revision_artifacts": 13,
        "model_calls": 7,
        "recorded_autonomous_gates": 5,
    }

    model_calls = result.payload["model_calls"]
    assert len(model_calls) == 7
    assert {call["status"] for call in model_calls} == {MODEL_CALL_SUCCESS}
    assert {call["provider"] for call in model_calls} == {"openai"}
    assert {call["model"] for call in model_calls} == {"stub-autonomous-revision-model"}
    assert all(call["input_hash"] for call in model_calls)
    assert all(
        call["prompt_contract_id"].startswith("autonomous.revision.")
        for call in model_calls
    )

    client = clients[0]
    assert len(client.requests) == 7
    assert "reader_lab_payloads" in client.requests[0].input_text
    assert "source_texts" in client.requests[0].input_text
    causal_request = next(
        request
        for request in client.requests
        if request.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA
    )
    causal_prompt = json.loads(causal_request.input_text)
    assert "revision_work_order" in causal_prompt
    assert causal_prompt["revision_work_order_artifact_id"] == result.payload[
        "artifact_ids"
    ][AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE]
    assert "controller_owned_patch_target_inventory" in causal_prompt
    assert causal_prompt["allowed_patch_targets"] == causal_prompt[
        "controller_owned_patch_target_inventory"
    ]["allowed_patch_targets"]
    assert causal_prompt["allowed_patch_target_ids"] == causal_prompt[
        "revision_work_order"
    ]["allowed_patch_target_ids"]
    assert all(
        target["patch_target_id"].startswith("target_")
        for target in causal_prompt["allowed_patch_targets"]
    )
    assert "Select exactly one selected_patch_target_id" in causal_prompt[
        "causal_handle_target_contract"
    ]
    reviser_request = next(
        request
        for request in client.requests
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA
    )
    reviser_prompt = json.loads(reviser_request.input_text)
    assert reviser_prompt["revision_work_order"] == causal_prompt["revision_work_order"]
    assert "selected_target_contract" in reviser_prompt
    assert "allowed_patch_targets" in reviser_prompt
    assert reviser_prompt["allowed_patch_targets"] == reviser_prompt[
        "selected_target_contract"
    ]["allowed_patch_targets"]
    assert reviser_prompt["allowed_patch_targets"][0]["patch_target_id"].startswith("target_")
    assert reviser_prompt["selected_patch_target_id"] == reviser_prompt[
        "allowed_patch_targets"
    ][0]["patch_target_id"]
    assert reviser_prompt["patchable_spans"]
    selected_target = next(
        target
        for target in reviser_prompt["revision_work_order"]["allowed_patch_targets"]
        if target["patch_target_id"] == reviser_prompt["selected_patch_target_id"]
    )
    assert {
        span["patch_span_id"] for span in reviser_prompt["patchable_spans"]
    } == set(selected_target["member_patch_span_ids"])
    assert all(
        span["patch_span_id"].startswith("span_")
        and span["patch_target_id"] == reviser_prompt["selected_patch_target_id"]
        and isinstance(span["char_start"], int)
        and isinstance(span["char_end"], int)
        and span["exact_text"]
        for span in reviser_prompt["patchable_spans"]
    )
    assert "candidate_reviser_target_contract" in reviser_prompt
    assert "Return patch operations only" in reviser_prompt["candidate_reviser_target_contract"]
    assert "choose patch_target_id exactly" in reviser_prompt[
        "candidate_reviser_target_contract"
    ]
    assert "choose patch_span_id exactly" in reviser_prompt[
        "candidate_reviser_target_contract"
    ]
    assert "Do not provide authoritative original_excerpt" in reviser_prompt[
        "candidate_reviser_target_contract"
    ]
    assert not any(
        request.schema == AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA for request in client.requests
    )
    ablation_request = next(
        request
        for request in client.requests
        if request.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA
    )
    ablation_prompt = json.loads(ablation_request.input_text)
    row_work_order = ablation_prompt["ablation_comparison_work_order"]
    assert row_work_order["controller_owned"] is True
    assert ablation_prompt["allowed_ablation_row_ids"] == [
        f"ablation_row_{index:03d}" for index in range(1, 9)
    ]
    assert [
        row["executed_variant_id"] for row in row_work_order["row_skeletons"]
    ] == [f"ablation_variant_{index:03d}" for index in range(1, 9)]
    assert all(row["planned_probe_id"] is None for row in row_work_order["row_skeletons"])
    assert "do not author planned_only" in ablation_prompt[
        "ablation_comparison_contract"
    ].lower()

    model_artifact_types = {schema.artifact_type for schema in AUTONOMOUS_REVISION_MODEL_SCHEMAS}
    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        revision_calls = [
            call
            for call in list_model_calls(connection, run_id=result.payload["run_id"])
            if call.prompt_contract_id.startswith("autonomous.revision.")
        ]
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(revision_calls) == 7
    artifact_by_type = {artifact.type: artifact for artifact in artifacts}
    for artifact_type in model_artifact_types:
        artifact = artifact_by_type[artifact_type]
        envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        assert envelope["schema_version"] == "1"
        assert envelope["artifact_type"] == artifact_type
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is not None
        expected_created_by = (
            "autonomous_closed_loop_revision_v1_controller"
            if artifact_type == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA.artifact_type
            else "model_driver:openai:stub-autonomous-revision-model"
        )
        assert envelope["created_by"] == expected_created_by

    for artifact_type in (
        "autonomous_revision_subject_manifest",
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE,
        "revised_candidate_text",
        "revision_diff_report",
        "autonomous_closed_loop_gate_report",
        "autonomous_closed_loop_packet",
    ):
        envelope = json.loads(
            Path(artifact_by_type[artifact_type].path).read_text(encoding="utf-8")
        )
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is None

    selected = read_payload(result.payload["artifact_paths"]["selected_failure_diagnosis"])
    assert selected["references_live_reader_lab_evidence"] is True
    assert selected["reader_lab_evidence_artifacts"]

    work_order = read_payload(
        result.payload["artifact_paths"][AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE]
    )
    assert_valid_work_order_payload(
        work_order=work_order,
        candidate_text=candidate_text_from_reader_lab_packet(lab_payload["packet_dir"]),
        expected_artifact_id=result.payload["artifact_ids"][
            AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
        ],
    )

    handle = read_payload(result.payload["artifact_paths"]["causal_handle_selection"])
    assert handle["revision_work_order_id"] == "revision_work_order_001"
    assert handle["revision_work_order_artifact_id"] == result.payload["artifact_ids"][
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
    ]
    assert handle["bounded_target"] is True
    assert handle["target_count"] == 1
    assert handle["does_not_rebuild_artifact"] is True
    assert handle["target_region_label"]
    assert handle["allowed_span_refs"]
    assert handle["allowed_patch_targets"]
    assert handle["allowed_patch_targets_source"] == "controller_owned"
    assert handle["selected_patch_target_id"] in {
        target["patch_target_id"] for target in handle["allowed_patch_targets"]
    }
    assert handle["allowed_patch_targets"][0]["patch_target_id"].startswith("target_")
    assert handle["patchable_spans"]
    assert handle["patchable_spans_source"] == "controller_owned"
    assert handle["protected_outside_spans"]

    patch_proposal = read_payload(result.payload["artifact_paths"]["revision_patch_proposal"])
    assert patch_proposal["patches"]
    assert "text" not in patch_proposal
    assert patch_proposal["patches"][0]["patch_target_id"] == handle[
        "allowed_patch_targets"
    ][0]["patch_target_id"]
    assert patch_proposal["patches"][0]["patch_span_id"] == handle["patchable_spans"][0][
        "patch_span_id"
    ]
    assert "original_excerpt" not in patch_proposal["patches"][0]
    assert patch_proposal["bounded_patch_set"] is True
    assert patch_proposal["full_rewrite"] is False

    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    assert revised["assembled_by_controller"] is True
    assert revised["work_order_artifact_id"] == result.payload["artifact_ids"][
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
    ]
    assert revised["source_patch_ids"] == ["patch_01"]
    assert revised["source_patch_span_ids"] == [
        patch_proposal["patches"][0]["patch_span_id"]
    ]
    assert revised["source_patch_target_ids"] == [
        patch_proposal["patches"][0]["patch_target_id"]
    ]
    assert revised["bounded_recomposition"] is True
    assert revised["full_rewrite"] is False
    assert revised["non_final"] is True
    assert revised["not_human_validated"] is True
    assert revised["not_finalization_eligible"] is True

    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    assert diff["assembled_by_controller"] is True
    assert diff["work_order_artifact_id"] == result.payload["artifact_ids"][
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
    ]
    assert diff["source_patch_ids"] == ["patch_01"]
    assert diff["source_patch_span_ids"] == [
        patch_proposal["patches"][0]["patch_span_id"]
    ]
    assert diff["source_patch_target_ids"] == [
        patch_proposal["patches"][0]["patch_target_id"]
    ]
    assert diff["bounded_change"] is True
    assert diff["changed_spans"]
    assert diff["target_region_expanded"] is False
    assert diff["expanded_target_region"] == ""
    assert diff["expansion_reason"] == ""
    assert diff["target_region_label"] == handle["target_region_label"]
    assert all("changed_span_id" in span for span in diff["changed_spans"])
    assert all("patch_span_id" in span for span in diff["changed_spans"])
    assert all("source_patch_span_ids" in span for span in diff["changed_spans"])
    assert all("source_patch_target_ids" in span for span in diff["changed_spans"])
    assert all(
        span["inside_target"] == span["within_selected_target"]
        for span in diff["changed_spans"]
    )

    variants = read_payload(result.payload["artifact_paths"]["ablation_variant_set"])
    assert variants["variants"]
    assert all(variant["executed"] is True for variant in variants["variants"])
    executed_variant_ids = {variant["variant_id"] for variant in variants["variants"]}
    ablation = read_payload(result.payload["artifact_paths"]["ablation_reread_comparison"])
    assert ablation["comparison_rows"]
    assert ablation["controller_owned"] is True
    assert ablation["model_call_id"]
    row_work_order = ablation["ablation_comparison_work_order"]
    assert row_work_order["controller_owned"] is True
    assert row_work_order["source_work_order_artifact_id"] == result.payload["artifact_ids"][
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE
    ]
    assert row_work_order["ablation_variant_set_artifact_id"] == result.payload["artifact_ids"][
        "ablation_variant_set"
    ]
    assert {
        row["row_id"] for row in row_work_order["row_skeletons"]
    } == {row["row_id"] for row in ablation["comparison_rows"]}
    assert all(row["planned_only"] is False for row in ablation["comparison_rows"])
    assert {
        row["executed_variant_id"] for row in ablation["comparison_rows"]
    } == executed_variant_ids
    assert {row["planned_probe_id"] for row in ablation["comparison_rows"]} == {None}
    assert {
        row["executed_variant_id"] for row in row_work_order["row_skeletons"]
    } == executed_variant_ids
    assert row_work_order["planned_probe_ids"] == []

    comparison = read_payload(result.payload["artifact_paths"]["old_new_rival_comparison"])
    assert comparison["strongest_rival_present"] is True
    assert comparison["rival_pressure_preserved"] is True
    assert comparison["another_revision_cycle_needed"] is True
    assert set(comparison["judgment_provenance"]) == {
        "reread_transformation_improved",
        "opening_transformation_improved",
        "local_embodiment_improved",
        "overexplanation_decreased",
        "fake_depth_risk_decreased",
        "revised_candidate_became_more_schematic",
        "rival_still_beats_candidate",
        "another_revision_cycle_needed",
    }
    assert "strongest_rival_text" in comparison["judgment_provenance"][
        "rival_still_beats_candidate"
    ]
    assert set(comparison["judgment_rationale"]) == set(
        AUTONOMOUS_REVISION_JUDGMENT_KEYS
    )
    assert "revised text" in comparison["judgment_rationale"][
        "reread_transformation_improved"
    ]

    local_law = read_payload(result.payload["artifact_paths"]["local_law_case_note"])
    assert local_law["principle"]
    assert local_law["comparison_result"]["another_revision_cycle_needed"] is True

    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_closed_loop_gate_report"])
    assert gate_report["eligible"] is False
    assert gate_report["fixture_fake_evidence"] is False
    assert "no_fixture_only_core_evidence" not in gate_report["failed_gates"]
    assert "no_unresolved_internal_blockers" in gate_report["failed_gates"]
    assert "internal_operator_approval" in gate_report["missing_gates"]
    assert gate_report["ablation_evidence"]["ablation_plan_exists"] is True
    assert gate_report["ablation_evidence"]["ablation_variants_executed"] is True
    assert gate_report["ablation_evidence"]["actual_ablation_variant_count"] == len(
        executed_variant_ids
    )
    assert gate_report["ablation_evidence"]["actual_comparison_row_count"] == len(
        executed_variant_ids
    )
    assert gate_report["ablation_evidence"][
        "executed_counterfactual_evidence_available"
    ] is True
    assert gate_report["ablation_evidence"]["ablation_comparison_predicted_only"] is True
    assert gate_report["ablation_evidence"]["ablation_comparison_actually_evaluated"] is False
    assert gate_report["human_validation_required"] is False
    assert gate_report["paper_validation_required"] is False
    assert gate_report["phase_shift_claim"] is False

    assert final_report.refused is True
    combined_blockers = " ".join(final_report.missing_gates + final_report.failed_gates)
    assert "internal_operator_approval" in combined_blockers
    assert "no_unresolved_internal_blockers" in combined_blockers
    assert "real_human_validation_passed" not in combined_blockers
    assert "paper" not in final_report.message.lower()


def test_stubbed_openai_full_text_injection_is_not_authoritative(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, FullTextInjectionClient),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    patch_proposal = read_payload(result.payload["artifact_paths"]["revision_patch_proposal"])
    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    assert "text" not in patch_proposal
    assert "injected full-text rewrite" not in revised["text"]
    assert revised["assembled_by_controller"] is True
    assert revised["source_patch_ids"] == ["patch_01"]

    with connect(config.db_path) as connection:
        revision_calls = [
            call
            for call in list_model_calls(connection, run_id=result.payload["run_id"])
            if call.prompt_contract_id.startswith("autonomous.revision.")
        ]
        revision_artifact_types = {
            artifact.type
            for artifact in list_artifacts(connection, result.payload["run_id"])
            if artifact.type in AUTONOMOUS_REVISION_ARTIFACT_TYPES
        }

    assert len(revision_calls) == 7
    assert "revision_patch_proposal" in revision_artifact_types
    assert "revised_candidate_text" in revision_artifact_types
    assert "revision_diff_report" in revision_artifact_types


def test_stubbed_openai_broad_target_uses_canonical_patch_target_id(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, BroadCanonicalTargetClient),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    handle = read_payload(result.payload["artifact_paths"]["causal_handle_selection"])
    patch_proposal = read_payload(result.payload["artifact_paths"]["revision_patch_proposal"])
    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    assert handle["allowed_patch_targets"][0]["patch_target_id"] == "target_opening_first_pivots"
    assert handle["patchable_spans"]
    assert all(
        span["patch_target_id"] == "target_opening_first_pivots"
        for span in handle["patchable_spans"]
    )
    assert patch_proposal["patches"][0]["patch_target_id"] == "target_opening_first_pivots"
    assert patch_proposal["patches"][0]["patch_span_id"] in {
        span["patch_span_id"] for span in handle["patchable_spans"]
    }
    assert diff["allowed_patch_targets"][0]["patch_target_id"] == "target_opening_first_pivots"
    assert diff["target_region_expanded"] is False


def test_stubbed_openai_model_authored_patch_target_inventory_is_ignored(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, ModelAuthoredPatchTargetInventoryClient),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    handle = read_payload(result.payload["artifact_paths"]["causal_handle_selection"])
    target_ids = {target["patch_target_id"] for target in handle["allowed_patch_targets"]}
    assert handle["allowed_patch_targets_source"] == "controller_owned"
    assert "target_model_authored_not_authoritative" not in target_ids
    assert handle["selected_patch_target_id"] in target_ids


def test_stubbed_openai_description_selected_patch_target_id_fails_early(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, DescriptionSelectedPatchTargetClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "selected_patch_target_id must be a canonical patch target id" in result.payload[
        "message"
    ]
    assert result.payload["counts"]["model_calls"] == 2
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "causal_handle_selection" not in result.payload["artifact_ids"]
    assert "revision_patch_proposal" not in result.payload["artifact_ids"]
    assert "revised_candidate_text" not in result.payload["artifact_ids"]


def test_stubbed_openai_invented_selected_patch_target_id_fails_early(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, InventedSelectedPatchTargetClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "selected unknown patch_target_id" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 2
    assert "causal_handle_selection" not in result.payload["artifact_ids"]
    assert "revision_patch_proposal" not in result.payload["artifact_ids"]
    assert "ablation_variant_set" not in result.payload["artifact_ids"]


def test_stubbed_openai_disallowed_patch_target_fails_before_revision_artifacts(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, DisallowedPatchTargetClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "model-call failure" in result.payload["message"]
    assert "selected target is" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    for artifact_type in (
        "revision_patch_proposal",
        "revised_candidate_text",
        "revision_diff_report",
        "ablation_variant_set",
        "ablation_reread_comparison",
        "old_new_rival_comparison",
        "local_law_case_note",
        "autonomous_closed_loop_gate_report",
        "autonomous_closed_loop_packet",
    ):
        assert artifact_type not in result.payload["artifact_ids"]
    assert result.payload["gate_report"] is None


def test_stubbed_openai_description_patch_target_id_fails_validation(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, DescriptionPatchTargetClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "canonical patch target id" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "revision_patch_proposal" not in result.payload["artifact_ids"]
    assert "revised_candidate_text" not in result.payload["artifact_ids"]
    assert "ablation_variant_set" not in result.payload["artifact_ids"]


def test_stubbed_openai_invented_patch_target_id_fails_validation(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, InventedPatchTargetClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "unknown patch_target_id" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    assert "revision_patch_proposal" not in result.payload["artifact_ids"]
    assert "revised_candidate_text" not in result.payload["artifact_ids"]
    assert "revision_diff_report" not in result.payload["artifact_ids"]
    assert "ablation_variant_set" not in result.payload["artifact_ids"]


def test_stubbed_openai_model_authored_original_excerpt_is_not_authoritative(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, OriginalExcerptOutsideTargetClient),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    patch_proposal = read_payload(result.payload["artifact_paths"]["revision_patch_proposal"])
    handle = read_payload(result.payload["artifact_paths"]["causal_handle_selection"])
    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    assert "original_excerpt" not in patch_proposal["patches"][0]
    span_text = handle["patchable_spans"][0]["exact_text"]
    assert f"{span_text} One ring of damp wood" in revised["text"]
    assert revised["assembled_by_controller"] is True
    assert diff["changed_spans"][0]["patch_span_id"] == patch_proposal["patches"][0][
        "patch_span_id"
    ]


def test_stubbed_openai_invented_patch_span_id_fails_before_revision_artifacts(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, InventedPatchSpanClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "unknown patch_span_id" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    for artifact_type in (
        "revision_patch_proposal",
        "revised_candidate_text",
        "revision_diff_report",
        "ablation_variant_set",
        "ablation_reread_comparison",
        "old_new_rival_comparison",
        "local_law_case_note",
        "autonomous_closed_loop_gate_report",
        "autonomous_closed_loop_packet",
    ):
        assert artifact_type not in result.payload["artifact_ids"]


def test_stubbed_openai_description_patch_span_id_fails_validation(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, DescriptionPatchSpanClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "patch_span_id must be a canonical patch span id" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    assert "revision_patch_proposal" not in result.payload["artifact_ids"]
    assert "revised_candidate_text" not in result.payload["artifact_ids"]


def test_stubbed_openai_replacement_uses_controller_exact_span_text(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, ReplacementPatchSpanClient),
    )

    assert result.exit_code == 0
    handle = read_payload(result.payload["artifact_paths"]["causal_handle_selection"])
    patch_proposal = read_payload(result.payload["artifact_paths"]["revision_patch_proposal"])
    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    selected_span = handle["patchable_spans"][0]
    patch = patch_proposal["patches"][0]
    assert patch["patch_span_id"] == selected_span["patch_span_id"]
    assert selected_span["exact_text"] not in revised["text"]
    assert ReplacementPatchSpanClient.replacement_text in revised["text"]
    assert diff["changed_spans"][0]["patch_span_id"] == selected_span["patch_span_id"]
    assert diff["source_patch_span_ids"] == [selected_span["patch_span_id"]]


def test_stubbed_openai_target_region_violation_fails_closed(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, TargetRegionViolationClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "model-call failure" in result.payload["message"]
    assert "selected target is" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "selected target is" in result.payload["message"]
    assert "revision_patch_proposal" not in result.payload["artifact_ids"]
    assert "revised_candidate_text" not in result.payload["artifact_ids"]
    assert "revision_diff_report" not in result.payload["artifact_ids"]
    assert "ablation_variant_set" not in result.payload["artifact_ids"]
    assert "ablation_reread_comparison" not in result.payload["artifact_ids"]
    assert "old_new_rival_comparison" not in result.payload["artifact_ids"]
    assert "local_law_case_note" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_gate_report" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_packet" not in result.payload["artifact_ids"]
    assert result.payload["gate_report"] is None

    with connect(config.db_path) as connection:
        revision_calls = [
            call
            for call in list_model_calls(connection, run_id=result.payload["run_id"])
            if call.prompt_contract_id.startswith("autonomous.revision.")
        ]
        revision_artifact_types = {
            artifact.type
            for artifact in list_artifacts(connection, result.payload["run_id"])
            if artifact.type in AUTONOMOUS_REVISION_ARTIFACT_TYPES
        }
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(revision_calls) == 3
    assert "revision_patch_proposal" not in revision_artifact_types
    assert "revised_candidate_text" not in revision_artifact_types
    assert "revision_diff_report" not in revision_artifact_types
    assert "ablation_variant_set" not in revision_artifact_types
    assert "autonomous_closed_loop_packet" not in revision_artifact_types
    assert final_report.refused is True


def test_stubbed_openai_explicit_target_expansion_request_fails_closed(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, ExplicitTargetExpansionClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "requested target expansion" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    assert "revision_patch_proposal" not in result.payload["artifact_ids"]
    assert "revised_candidate_text" not in result.payload["artifact_ids"]
    assert "revision_diff_report" not in result.payload["artifact_ids"]


def test_stubbed_openai_planned_only_ablation_is_not_executed_evidence(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, PlannedOnlyAblationClient),
    )

    assert result.exit_code == 0
    variants = read_payload(result.payload["artifact_paths"]["ablation_variant_set"])
    assert any(variant["executed"] is False for variant in variants["variants"])
    ablation = read_payload(result.payload["artifact_paths"]["ablation_reread_comparison"])
    planned_rows = [row for row in ablation["comparison_rows"] if row["planned_only"]]
    assert planned_rows
    assert all(row["executed_variant_id"] is None for row in planned_rows)
    assert all(row["planned_probe_id"] for row in planned_rows)
    assert {row["evidence_basis"] for row in planned_rows} == {"planned_ablation_probe"}
    skeleton_planned_rows = [
        row
        for row in ablation["ablation_comparison_work_order"]["row_skeletons"]
        if row["planned_only"]
    ]
    assert [row["row_id"] for row in skeleton_planned_rows] == [
        row["row_id"] for row in planned_rows
    ]

    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_closed_loop_gate_report"])
    evidence = gate_report["ablation_evidence"]
    assert evidence["planned_only_comparison_row_count"] == len(planned_rows)
    assert evidence["planned_only_ablation_probe_count"] == len(planned_rows)
    assert evidence["ablation_variants_executed"] is True
    assert evidence["executed_comparison_row_count"] == len(ablation["comparison_rows"]) - len(
        planned_rows
    )
    assert evidence["actual_comparison_row_count"] == evidence["executed_comparison_row_count"]
    assert evidence["actual_ablation_variant_count"] == evidence[
        "executed_ablation_variant_count"
    ]
    assert evidence["executed_counterfactual_evidence_available"] is True
    assert evidence["predicted_only_comparison_row_count"] == len(ablation["comparison_rows"])
    assert evidence["actual_ablation_comparison_evidence_count"] == 0
    assert evidence["ablation_comparison_predicted_only"] is True
    assert evidence["ablation_comparison_actually_evaluated"] is False


def test_stubbed_openai_model_authored_ablation_control_fields_are_ignored(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(
            clients,
            ModelAuthoredAblationControlFieldsClient,
        ),
    )

    assert result.exit_code == 0
    ablation = read_payload(result.payload["artifact_paths"]["ablation_reread_comparison"])
    first_row = ablation["comparison_rows"][0]
    first_skeleton = ablation["ablation_comparison_work_order"]["row_skeletons"][0]
    assert first_row["planned_only"] is first_skeleton["planned_only"] is False
    assert first_row["executed_variant_id"] == first_skeleton["executed_variant_id"]
    assert first_row["planned_probe_id"] is first_skeleton["planned_probe_id"] is None
    assert first_row["evidence_basis"] == first_skeleton["evidence_basis"]
    assert first_row["operation"] == first_skeleton["operation"]
    assert first_row["executed_variant_id"] != "model_authored_variant"
    assert first_row["planned_probe_id"] != "model_authored_probe"
    assert first_row["operation"] != "model_authored_operation"


def test_stubbed_openai_invalid_ablation_alignment_fails_closed(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, InvalidAblationComparisonClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "invented ablation comparison row_id" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 5
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "ablation_reread_comparison" not in result.payload["artifact_ids"]
    assert "old_new_rival_comparison" not in result.payload["artifact_ids"]
    assert "local_law_case_note" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_gate_report" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_packet" not in result.payload["artifact_ids"]
    assert result.payload["gate_report"] is None

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        revision_calls = [
            call
            for call in list_model_calls(connection, run_id=result.payload["run_id"])
            if call.prompt_contract_id.startswith("autonomous.revision.")
        ]
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(revision_calls) == 5
    revision_artifact_types = {
        artifact.type
        for artifact in artifacts
        if artifact.type in AUTONOMOUS_REVISION_ARTIFACT_TYPES
    }
    assert "ablation_reread_comparison" not in revision_artifact_types
    assert "old_new_rival_comparison" not in revision_artifact_types
    assert "local_law_case_note" not in revision_artifact_types
    assert "autonomous_closed_loop_gate_report" not in revision_artifact_types
    assert "autonomous_closed_loop_packet" not in revision_artifact_types
    assert final_report.refused is True


@pytest.mark.parametrize(
    ("client_cls", "message"),
    [
        (DuplicateAblationRowClient, "duplicate ablation comparison row_id"),
        (MissingAblationRowClient, "missing ablation comparison row_id"),
    ],
)
def test_stubbed_openai_ablation_row_identity_failures_stop_downstream(
    tmp_path,
    client_cls,
    message,
):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, client_cls),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert message in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 5
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "ablation_reread_comparison" not in result.payload["artifact_ids"]
    assert "old_new_rival_comparison" not in result.payload["artifact_ids"]
    assert "local_law_case_note" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_gate_report" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_packet" not in result.payload["artifact_ids"]


def test_stubbed_openai_invalid_old_new_provenance_fails_closed(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(
            clients,
            InvalidOldNewRivalProvenanceClient,
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "model-call failure" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 6
    failed_call = result.payload["model_calls"][-1]
    assert (
        failed_call["schema_name"]
        == AUTONOMOUS_REVISION_OLD_NEW_RIVAL_COMPARISON_SCHEMA.name
    )
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "old_new_rival_comparison" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_gate_report" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_packet" not in result.payload["artifact_ids"]
    assert result.payload["gate_report"] is None

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        revision_calls = [
            call
            for call in list_model_calls(connection, run_id=result.payload["run_id"])
            if call.prompt_contract_id.startswith("autonomous.revision.")
        ]
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(revision_calls) == 6
    revision_artifact_types = {
        artifact.type
        for artifact in artifacts
        if artifact.type in AUTONOMOUS_REVISION_ARTIFACT_TYPES
    }
    assert "old_new_rival_comparison" not in revision_artifact_types
    assert "autonomous_closed_loop_gate_report" not in revision_artifact_types
    assert "autonomous_closed_loop_packet" not in revision_artifact_types
    assert final_report.refused is True


def test_executed_ablation_fake_creates_diagnostic_packet(tmp_path):
    config, revision_payload = build_fake_revision_packet(tmp_path, with_rival=True)

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=revision_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert set(result.payload["artifact_ids"]) == set(EXECUTED_ABLATION_ARTIFACT_TYPES)
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["counts"]["countable_evidence_variant_count"] == 3

    work_order = read_payload(result.payload["artifact_paths"]["executed_ablation_work_order"])
    assert work_order["controller_owned"] is True
    assert work_order["source_autonomous_revision_packet_id"] == revision_payload["packet_id"]
    assert work_order["allowed_operation_ids"]
    assert work_order["allowed_source_patch_span_ids"]
    assert work_order["allowed_source_spans"]
    assert work_order["does_not_create_main_candidate"] is True

    variants = read_payload(result.payload["artifact_paths"]["actual_ablation_variant_set"])
    assert variants["variants"]
    assert variants["non_final"] is True
    assert variants["not_finalization_eligible"] is True
    assert all(variant["operation_id"] for variant in variants["variants"])
    assert all(
        variant["source_span_id"] or variant["source_patch_span_id"]
        for variant in variants["variants"]
    )
    no_ops = [variant for variant in variants["variants"] if variant["no_op"]]
    mismatches = [
        variant
        for variant in variants["variants"]
        if not variant["operation_matches_actual_change"]
    ]
    planned = [variant for variant in variants["variants"] if variant["planned_only"]]
    assert no_ops
    assert mismatches
    assert planned
    assert all(not variant["evidence_countable"] for variant in no_ops)
    assert all(not variant["evidence_countable"] for variant in mismatches)
    assert all(not variant["evidence_countable"] for variant in planned)

    execution = read_payload(result.payload["artifact_paths"]["ablation_execution_report"])
    assert execution["actual_executed_ablation_evidence_exists"] is True
    assert execution["planned_only_not_counted"] is True
    assert execution["no_op_not_counted"] is True
    assert execution["operation_mismatch_not_counted"] is True

    for artifact_type in (
        "ablation_internal_reader_comparison",
        "ablation_old_new_rival_comparison",
        "comparison_consistency_report",
        "ablation_causal_effect_report",
        "executed_ablation_gate_report",
        "executed_ablation_packet",
    ):
        assert artifact_type in result.payload["artifact_ids"]

    consistency = read_payload(
        result.payload["artifact_paths"]["comparison_consistency_report"]
    )
    assert consistency["comparison_internal_consistency"] is True
    assert consistency["countable_as_gate_evidence"] is True

    causal = read_payload(result.payload["artifact_paths"]["ablation_causal_effect_report"])
    assert causal["selected_repair_causal_status"] in {
        "ambiguous",
        "useful_but_insufficient",
        "noncausal_or_cosmetic",
    }
    assert causal["not_human_validated"] is True
    assert causal["no_phase_shift_claim"] is True

    gate = read_payload(result.payload["artifact_paths"]["executed_ablation_gate_report"])
    assert gate["eligible"] is False
    assert gate["passed"] is False
    assert gate["final_gates_marked_passed"] == []
    assert gate["phase_shift_claim"] is False
    assert gate["human_validation_required"] is False
    assert gate["paper_validation_required"] is False

    with connect(config.db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True
    assert "paper" not in final_report.message.lower()


def test_executed_ablation_refuses_missing_revision_packet(tmp_path):
    config = config_for(tmp_path)

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=tmp_path / "missing_packet",
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "not found" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_executed_ablation_accepts_ablation_informed_revision_packet(tmp_path):
    config, revision_payload = build_fake_ablation_informed_revision_packet(tmp_path)

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=revision_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["revision_packet_kind"] == "ablation_informed_revision"
    subject = read_payload(result.payload["artifact_paths"]["executed_ablation_subject_manifest"])
    assert subject["revision_packet_kind"] == "ablation_informed_revision"
    assert subject["ready_for_executed_ablation"] is True
    assert subject["patch_ledger"]["all_applied_patches_reflected_in_text"] is True

    work_order = read_payload(result.payload["artifact_paths"]["executed_ablation_work_order"])
    assert work_order["source_revision_packet_kind"] == "ablation_informed_revision"
    assert work_order["ready_for_executed_ablation"] is True

    variants = read_payload(result.payload["artifact_paths"]["actual_ablation_variant_set"])
    assert variants["source_revision_packet_kind"] == "ablation_informed_revision"
    assert variants["source_cycle2_patch_ids"] == work_order["allowed_source_patch_ids"]
    assert variants["source_cycle2_patch_span_ids"] == work_order[
        "allowed_source_patch_span_ids"
    ]
    assert any(
        variant["operation_type"]
        in {
            "revert_all_cycle2_applied_patches",
            "revert_direct_dominant_base_to_original_candidate",
        }
        for variant in variants["variants"]
    )
    assert all(
        variant["source_patch_span_ids"] or variants["direct_dominant_base_promotion"]
        for variant in variants["variants"]
        if variant["operation_id"]
        in {
            "operation_revert_applied_patch",
            "operation_record_label_compression",
        }
    )

    gate = read_payload(result.payload["artifact_paths"]["executed_ablation_gate_report"])
    assert gate["eligible"] is False
    assert gate["final_gates_marked_passed"] == []
    assert gate["phase_shift_claim"] is False
    assert gate["not_human_validated"] is True


def test_normalized_ablation_adapter_identifies_autonomous_revision_packet(tmp_path):
    config, revision_payload = build_fake_revision_packet(tmp_path, with_rival=True)

    with connect(config.db_path) as connection:
        subject = _load_subject(connection, Path(str(revision_payload["packet_dir"])))

    assert subject.subject_packet_kind == REVISION_PACKET_KIND_AUTONOMOUS
    assert subject.normalized_subject_kind == REVISION_PACKET_KIND_AUTONOMOUS
    assert subject.candidate_text
    assert subject.candidate_text_sha256 == sha256_text(subject.candidate_text)
    assert subject.target_scope == "revision_changed_spans"
    assert subject.no_phase_shift_claim is True


def test_normalized_ablation_adapter_identifies_ablation_informed_packet(tmp_path):
    config, revision_payload = build_fake_ablation_informed_revision_packet(tmp_path)

    with connect(config.db_path) as connection:
        subject = _load_subject(connection, Path(str(revision_payload["packet_dir"])))

    assert subject.subject_packet_kind == REVISION_PACKET_KIND_ABLATION_INFORMED
    assert subject.normalized_subject_kind == REVISION_PACKET_KIND_ABLATION_INFORMED
    assert subject.ready_for_executed_ablation is True
    assert subject.target_scope == "cycle2_changed_spans"
    assert subject.changed_region_refs
    assert subject.no_phase_shift_claim is True


def test_normalized_ablation_adapter_identifies_bounded_macro_packet(tmp_path):
    config, macro_payload = build_fake_bounded_macro_recomposition_packet(tmp_path)

    with connect(config.db_path) as connection:
        subject = _load_subject(connection, Path(str(macro_payload["packet_dir"])))

    assert subject.subject_packet_kind == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert subject.normalized_subject_kind == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert subject.ready_for_executed_ablation is True
    assert subject.target_scope == "macro_target_movement"
    assert subject.target_movement == "middle_and_return_movement"
    assert subject.base_candidate_packet_id
    assert subject.macro_target_coverage["macro_target_coverage_passed"] is True
    assert subject.macro_target_coverage["macro_materiality_passed"] is True


def test_executed_ablation_accepts_bounded_macro_recomposition_packet(tmp_path):
    config, macro_payload = build_fake_bounded_macro_recomposition_packet(tmp_path)

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=macro_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["revision_packet_kind"] == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert result.payload["normalized_subject_kind"] == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert result.payload["counts"]["model_calls"] == 0

    subject = read_payload(result.payload["artifact_paths"]["executed_ablation_subject_manifest"])
    assert subject["subject_packet_kind"] == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert subject["normalized_subject_kind"] == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert subject["target_movement"] == "middle_and_return_movement"
    assert subject["readiness"]["ready_for_executed_ablation"] is True
    assert subject["readiness"]["no_phase_shift_claim"] is True
    assert subject["readiness"]["finalization_eligible"] is False
    assert subject["macro_target_coverage"]["macro_target_coverage_passed"] is True

    variants = read_payload(result.payload["artifact_paths"]["actual_ablation_variant_set"])
    assert variants["source_subject_packet_kind"] == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert variants["source_macro_packet_id"] == macro_payload["packet_id"]
    assert variants["target_movement"] == "middle_and_return_movement"
    assert variants["macro_changed_region_refs"]
    macro_countable_ops = {
        "operation_revert_full_macro_section_to_base",
        "operation_isolate_proof_no_outside_answer_region",
        "operation_flatten_macro_to_summary_or_restore_return_echo",
    }
    assert {
        variant["operation_id"]
        for variant in variants["variants"]
        if variant["evidence_countable"]
    } == macro_countable_ops
    for variant in variants["variants"]:
        assert variant["source_subject_packet_kind"] == REVISION_PACKET_KIND_BOUNDED_MACRO
        assert variant["source_macro_packet_id"] == macro_payload["packet_id"]
        assert variant["target_movement"] == "middle_and_return_movement"
        assert variant["variant_text_sha256"]
    controls = [
        variant
        for variant in variants["variants"]
        if variant["operation_id"]
        in {
            "operation_no_op_control",
            "operation_mismatch_control",
            "operation_planned_probe_only",
        }
    ]
    assert controls
    assert all(not variant["evidence_countable"] for variant in controls)

    gate = read_payload(result.payload["artifact_paths"]["executed_ablation_gate_report"])
    assert gate["eligible"] is False
    assert gate["final_gates_marked_passed"] == []
    assert gate["phase_shift_claim"] is False

    with connect(config.db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_executed_ablation_detects_tactile_residual_candidate_as_target_aware(tmp_path):
    config, residual_payload = build_fake_tactile_residual_candidate_packet(tmp_path)

    with connect(config.db_path) as connection:
        subject = _load_subject(connection, Path(str(residual_payload["packet_dir"])))

    assert subject.subject_packet_kind == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert subject.target_aware_ablation is True
    assert subject.legacy_generic_ablation_fallback is False
    assert subject.target_adapter_id == "tactile_inevitability"
    assert subject.selected_residual_target_id == TACTILE_INEVITABILITY_TARGET_ID
    assert subject.base_candidate_packet_id
    assert subject.selected_region_id == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert subject.target_scope == TACTILE_INEVITABILITY_TARGET_ID
    assert subject.target_movement == TACTILE_INEVITABILITY_TARGET_ID
    assert set(subject.target_unit_ids) == {
        "tactile_unit_001",
        "tactile_unit_002",
        "tactile_unit_003",
    }
    assert "preserve_object_motion_remove_tactile_force_relation" in (
        subject.target_specific_ablation_controls
        or subject.ablation_controls
    )


def test_executed_ablation_fake_tactile_residual_uses_target_specific_controls(
    tmp_path,
):
    config, residual_payload = build_fake_tactile_residual_candidate_packet(tmp_path)

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=residual_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["target_aware_ablation"] is True
    assert result.payload["target_adapter_id"] == "tactile_inevitability"
    assert result.payload["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["counts"]["model_calls"] == 0

    subject = read_payload(result.payload["artifact_paths"]["executed_ablation_subject_manifest"])
    assert subject["target_aware_ablation"] is True
    assert subject["legacy_generic_ablation_fallback"] is False
    assert subject["target_adapter_id"] == "tactile_inevitability"
    assert subject["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert subject["target_unit_ids"] == [
        "tactile_unit_001",
        "tactile_unit_002",
        "tactile_unit_003",
    ]

    work_order = read_payload(result.payload["artifact_paths"]["executed_ablation_work_order"])
    assert work_order["target_aware_ablation"] is True
    assert work_order["legacy_generic_ablation_fallback"] is False
    assert work_order["base_candidate_packet_id"]
    assert work_order["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert "preserve_object_motion_remove_tactile_force_relation" in work_order[
        "target_specific_ablation_controls"
    ]

    variants = read_payload(result.payload["artifact_paths"]["actual_ablation_variant_set"])
    assert variants["target_aware_ablation"] is True
    operation_ids = [variant["operation_id"] for variant in variants["variants"]]
    assert "operation_revert_tactile_intervention_to_current_best" in operation_ids
    assert "operation_preserve_object_motion_remove_tactile_force_relation" in operation_ids
    assert "operation_decorative_or_abstract_tactile_control" in operation_ids
    assert "operation_revert_full_macro_section_to_base" not in operation_ids
    assert "operation_isolate_proof_no_outside_answer_region" not in operation_ids
    assert "operation_flatten_macro_to_summary_or_restore_return_echo" not in operation_ids

    tactile_removed = next(
        variant
        for variant in variants["variants"]
        if variant["operation_id"]
        == "operation_preserve_object_motion_remove_tactile_force_relation"
    )
    assert tactile_removed["target_region_coverage"][
        "covers_full_selected_region"
    ] is True
    report = tactile_removed["object_motion_preservation_report"]
    assert report["preserves_required_object_motion_content"] is True
    assert report["required_object_motion_terms"]
    assert set(report["preserved_object_motion_terms"]) == set(
        report["required_object_motion_terms"]
    )
    for term in report["required_object_motion_terms"]:
        assert term in tactile_removed["after_text"].lower()
    for leaked in ("cup’s weight", "pressed into", "rubbed", "forced open"):
        assert leaked not in tactile_removed["after_text"].lower()
    assert tactile_removed["tactile_force_contact_terms_removed"] is True

    comparison = read_payload(
        result.payload["artifact_paths"]["ablation_old_new_rival_comparison"]
    )
    assert comparison["target_aware_ablation"] is True
    assert comparison["target_adapter_id"] == "tactile_inevitability"
    assert "tactile_force_contact_adds_value" in comparison
    assert "object_motion_preserved_tactile_removed_performs_same_or_better" in comparison
    assert comparison["strongest_rival_still_beats_candidate"] is True

    causal = read_payload(result.payload["artifact_paths"]["ablation_causal_effect_report"])
    assert causal["target_aware_ablation"] is True
    assert causal["target_adapter_id"] == "tactile_inevitability"
    assert "tactile_intervention_has_causal_support" in causal
    assert "tactile_force_contact_adds_value" in causal
    assert "packet_0063_earns_reader_state_eval" in causal
    assert causal["strongest_rival_still_blocks"] is True
    assert causal["finalization_eligible"] is False
    assert causal["no_phase_shift_claim"] is True

    gate = read_payload(result.payload["artifact_paths"]["executed_ablation_gate_report"])
    assert gate["eligible"] is False
    assert gate["target_aware_ablation"] is True
    assert gate["final_gates_marked_passed"] == []


def test_executed_ablation_tactile_openai_guard_refuses_before_model_call(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, residual_payload = build_fake_tactile_residual_candidate_packet(tmp_path)
    clients = []

    result = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual_payload["packet_dir"],
        client_factory=executed_ablation_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert clients == []


def test_target_aware_ablation_openai_prompt_and_clean_output_preserve_roles(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, residual_payload = build_fake_tactile_residual_candidate_packet(tmp_path)
    clients = []

    result = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual_payload["packet_dir"],
        allow_live_model=True,
        max_model_calls=1,
        model="stub-model",
        client_factory=executed_ablation_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 1
    prompt = json.loads(clients[0].requests[0].input_text)
    assert "revert-to-current-best variant" in prompt[
        "target_aware_comparison_must_distinguish"
    ]
    assert "object-motion-preserved tactile-force-removed variant" in prompt[
        "target_aware_comparison_must_distinguish"
    ]
    revert_variant = next(
        variant
        for variant in prompt["variants"]
        if variant["operation_id"]
        == "operation_revert_tactile_intervention_to_current_best"
    )
    tactile_removed = next(
        variant
        for variant in prompt["variants"]
        if variant["operation_id"]
        == "operation_preserve_object_motion_remove_tactile_force_relation"
    )
    assert revert_variant["variant_role"] == "current_best_object_motion_baseline"
    assert "full tactile candidate" in revert_variant["comparator_do_not_confuse_with"]
    assert (
        tactile_removed["variant_role"]
        == "tactile_removed_object_motion_preserved_control"
    )
    assert "force/contact" in str(tactile_removed["expected_removed_mechanism"])

    consistency = read_payload(
        result.payload["artifact_paths"]["comparison_consistency_report"]
    )
    assert consistency["target_role_consistency_checked"] is True
    assert consistency["target_role_consistency_passed"] is True
    assert consistency["target_role_consistency_failures"] == []
    assert consistency["comparison_internal_consistency"] is True

    causal = read_payload(result.payload["artifact_paths"]["ablation_causal_effect_report"])
    assert causal["selected_repair_causal_status"] == "useful_but_insufficient"
    assert causal["tactile_intervention_has_causal_support"] is True
    assert causal["packet_0063_earns_reader_state_eval"] is True

    gate = read_payload(result.payload["artifact_paths"]["executed_ablation_gate_report"])
    assert gate["target_role_consistency_checked"] is True
    assert gate["target_role_consistency_passed"] is True
    assert gate["eligible"] is False


def test_target_aware_ablation_marks_role_confused_comparator_non_authoritative(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, residual_payload = build_fake_tactile_residual_candidate_packet(tmp_path)
    clients = []

    result = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual_payload["packet_dir"],
        allow_live_model=True,
        max_model_calls=1,
        model="stub-model",
        client_factory=executed_ablation_stub_factory(
            clients,
            mode="confused_tactile_revert",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["target_role_consistency_passed"] is False
    assert result.payload["comparison_internal_consistency"] is False

    consistency = read_payload(
        result.payload["artifact_paths"]["comparison_consistency_report"]
    )
    failures = "\n".join(consistency["target_role_consistency_failures"])
    assert consistency["target_role_consistency_checked"] is True
    assert consistency["target_role_consistency_passed"] is False
    assert "revert-to-current-best row describes restored tactile force/contact" in failures
    assert "causal report says tactile adds value" in failures
    revert_alignment = next(
        alignment
        for alignment in consistency["variant_role_alignment_by_id"].values()
        if alignment["operation_id"]
        == "operation_revert_tactile_intervention_to_current_best"
    )
    assert revert_alignment["role_aligned"] is False

    causal = read_payload(result.payload["artifact_paths"]["ablation_causal_effect_report"])
    assert (
        causal["selected_repair_causal_status"]
        == "inconclusive_due_to_comparator_role_confusion"
    )
    assert causal["tactile_intervention_has_causal_support"] is False
    assert causal["packet_0063_earns_reader_state_eval"] is False
    assert (
        causal["recommended_next_action"]
        == "review_target_aware_ablation_comparator_inconsistency"
    )

    gate = read_payload(result.payload["artifact_paths"]["executed_ablation_gate_report"])
    assert gate["target_role_consistency_passed"] is False
    assert "comparison_internal_consistency" in gate["failed_gates"]
    assert gate["eligible"] is False


def test_target_aware_ablation_role_consistency_ignores_negated_guardrails():
    variant_set = {
        "target_aware_ablation": True,
        "variants": [
            {
                "variant_id": "executed_ablation_variant_001",
                "operation_id": "operation_revert_tactile_intervention_to_current_best",
                "variant_role": "current_best_object_motion_baseline",
                "evidence_countable": True,
                "operation_matches_actual_change": True,
                "planned_only": False,
            },
            {
                "variant_id": "executed_ablation_variant_002",
                "operation_id": "operation_preserve_object_motion_remove_tactile_force_relation",
                "variant_role": "tactile_removed_object_motion_preserved_control",
                "evidence_countable": True,
                "operation_matches_actual_change": True,
                "planned_only": False,
            },
            {
                "variant_id": "executed_ablation_variant_003",
                "operation_id": "operation_decorative_or_abstract_tactile_control",
                "variant_role": "noncausal_vividness_or_explanation_control",
                "evidence_countable": True,
                "operation_matches_actual_change": True,
                "planned_only": False,
            },
        ],
    }
    internal = {
        "comparison_rows": [
            {
                "variant_id": "executed_ablation_variant_001",
                "operation_id": "operation_revert_tactile_intervention_to_current_best",
                "comparison_summary": (
                    "Current-best object-motion baseline; restores baseline object-motion "
                    "causality without tactile force/contact necessity."
                ),
                "reader_state_effect_estimate": "baseline anchor, low added tactile inevitability",
                "rationale": (
                    "Keeps trace logic while removing the target tactile intervention."
                ),
                "risk_notes": (
                    "Do not mislabel as full tactile candidate or as restored tactile force."
                ),
                "comparator_do_not_confuse_with": [
                    "full tactile candidate",
                    "restored tactile force/contact",
                ],
                "target_role_consistency_requirements": [
                    "do not say this variant restores tactile force/contact",
                    "do not count as full tactile intervention",
                ],
            },
            {
                "variant_id": "executed_ablation_variant_002",
                "operation_id": "operation_preserve_object_motion_remove_tactile_force_relation",
                "comparison_summary": (
                    "Primary target-aware control; preserves object-motion consequences "
                    "while removing force/contact necessity."
                ),
                "reader_state_effect_estimate": (
                    "likely negative relative to full tactile candidate on first-read "
                    "physical inevitability"
                ),
                "rationale": (
                    "Tests whether tactile force/contact adds value beyond object-motion "
                    "trace causality by stripping force/contact wording."
                ),
                "risk_notes": "avoid treating as decorative control",
                "target_role_consistency_requirements": [
                    "do not describe as full tactile intervention",
                ],
            },
            {
                "variant_id": "executed_ablation_variant_003",
                "operation_id": "operation_decorative_or_abstract_tactile_control",
                "comparison_summary": (
                    "Decorative or abstract tactile control; substitutes vivid "
                    "explanation for causal tactile necessity."
                ),
                "reader_state_effect_estimate": (
                    "weak to moderate, but not strong embodied tactile inevitability"
                ),
                "rationale": (
                    "Any gain would be noncausal and weaker than tactile necessity."
                ),
                "risk_notes": "Do not count as embodied proof of tactile force.",
                "target_role_consistency_requirements": [
                    "do not count as embodied tactile inevitability",
                    "do not treat as material force/contact proof",
                ],
            },
        ]
    }
    old_new = {
        "tactile_force_contact_adds_value": True,
        "summary": "target-aware comparison supports tactile value",
        "rationale": "target-aware comparison supports tactile value",
        "comparison_basis": "target-aware diagnostic",
    }

    report = _build_comparison_consistency_report(
        variant_set=variant_set,
        internal_comparison=internal,
        old_new_comparison=old_new,
        fixture_only=False,
    )

    assert report["target_role_consistency_checked"] is True
    assert report["target_role_consistency_passed"] is True
    assert report["comparison_internal_consistency"] is True
    assert report["target_role_consistency_failures"] == []
    assert report["contradictions"] == []


def test_target_aware_ablation_supersedes_prior_generic_ablation_metadata(tmp_path):
    config, residual_payload = build_fake_tactile_residual_candidate_packet(tmp_path)
    prior = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=residual_payload["packet_dir"],
    )
    assert prior.exit_code == 0

    def _make_prior_generic(payload):
        payload["target_aware_ablation"] = False
        payload["legacy_generic_ablation_fallback"] = True

    rewrite_payload(
        prior.payload["artifact_paths"]["executed_ablation_packet"],
        _make_prior_generic,
    )

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=residual_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["target_aware_ablation"] is True
    assert result.payload["previous_generic_ablation_packet_id"] == prior.payload[
        "packet_id"
    ]
    assert result.payload["previous_generic_ablation_not_authoritative_for_target"] is True
    assert result.payload["supersedes_generic_ablation_for_target"] is True

    packet = read_payload(result.payload["artifact_paths"]["executed_ablation_packet"])
    assert packet["previous_generic_ablation_packet_id"] == prior.payload["packet_id"]
    assert packet["supersedes_generic_ablation_for_target"] is True
    assert "target-specific tactile controls" in packet["supersession_reason"]


def test_executed_ablation_refuses_invalid_bounded_macro_packets(tmp_path):
    config, macro_payload = build_fake_bounded_macro_recomposition_packet(tmp_path)
    valid_packet_dir = Path(str(macro_payload["packet_dir"]))

    def _remove(filename):
        def _mutate(packet_dir: Path) -> None:
            (packet_dir / filename).unlink()

        return _mutate

    def _rewrite(filename, mutator):
        def _mutate(packet_dir: Path) -> None:
            rewrite_payload(packet_dir / filename, mutator)

        return _mutate

    cases = [
        (
            "missing_packet",
            _remove("macro_recomposition_packet.json"),
            "missing macro_recomposition_packet.json",
        ),
        (
            "missing_candidate",
            _remove("macro_recomposed_candidate_text.json"),
            "missing macro_recomposed_candidate_text.json",
        ),
        (
            "missing_diff",
            _remove("macro_recomposition_diff_report.json"),
            "missing macro_recomposition_diff_report.json",
        ),
        (
            "missing_gate",
            _remove("macro_recomposition_gate_report.json"),
            "missing macro_recomposition_gate_report.json",
        ),
        (
            "not_bounded",
            _rewrite(
                "macro_recomposed_candidate_text.json",
                lambda payload: payload.update({"bounded_macro_recomposition": False}),
            ),
            "bounded_macro_recomposition must be true",
        ),
        (
            "full_rewrite",
            _rewrite(
                "macro_recomposed_candidate_text.json",
                lambda payload: payload.update({"full_rewrite": True}),
            ),
            "full_rewrite must be false",
        ),
        (
            "coverage_false",
            _rewrite(
                "macro_recomposition_diff_report.json",
                lambda payload: payload["target_coverage_report"].update(
                    {"macro_target_coverage_passed": False}
                ),
            ),
            "target_coverage_report.macro_target_coverage_passed",
        ),
        (
            "materiality_false",
            _rewrite(
                "macro_recomposition_diff_report.json",
                lambda payload: payload["target_coverage_report"].update(
                    {"macro_materiality_passed": False}
                ),
            ),
            "target_coverage_report.macro_materiality_passed",
        ),
        (
            "not_ready",
            _rewrite(
                "macro_recomposition_diff_report.json",
                lambda payload: payload["target_coverage_report"].update(
                    {"ready_for_executed_ablation": False}
                ),
            ),
            "target_coverage_report.ready_for_executed_ablation",
        ),
    ]

    for case_name, mutate, expected in cases:
        invalid_packet = tmp_path / f"invalid_macro_{case_name}"
        shutil.copytree(valid_packet_dir, invalid_packet)
        mutate(invalid_packet)

        result = run_executed_ablation(
            config,
            client_name="fake",
            revision_packet=invalid_packet,
        )

        assert result.exit_code == 1, case_name
        assert result.payload["refused"] is True, case_name
        assert expected in result.payload["message"], case_name
        assert result.payload["counts"]["model_calls"] == 0, case_name


def test_executed_ablation_openai_guard_refuses_bounded_macro_packet(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, macro_payload = build_fake_bounded_macro_recomposition_packet(tmp_path)

    result = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=macro_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_executed_ablation_refuses_ablation_informed_packet_missing_cycle2_packet(tmp_path):
    config, revision_payload = build_fake_ablation_informed_revision_packet(tmp_path)
    Path(revision_payload["packet_dir"], "cycle2_packet.json").unlink()

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=revision_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "missing cycle2_packet.json" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("cycle2_revised_candidate_text.json", "cycle2_revised_candidate_text.json"),
        ("cycle2_revision_diff_report.json", "cycle2_revision_diff_report.json"),
        ("cycle2_applied_patch_ledger.json", "cycle2_applied_patch_ledger.json"),
        ("cycle2_gate_report.json", "cycle2_gate_report.json"),
    ],
)
def test_executed_ablation_refuses_ablation_informed_packet_missing_required_file(
    tmp_path,
    filename,
    expected,
):
    config, revision_payload = build_fake_ablation_informed_revision_packet(tmp_path)
    Path(revision_payload["packet_dir"], filename).unlink()

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=revision_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert expected in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_executed_ablation_refuses_ablation_informed_packet_bad_integrity(tmp_path):
    config, revision_payload = build_fake_ablation_informed_revision_packet(tmp_path)
    gate_path = Path(revision_payload["packet_dir"], "cycle2_gate_report.json")
    envelope = json.loads(gate_path.read_text(encoding="utf-8"))
    envelope["payload"]["integrity"]["text_diff_consistency_passed"] = False
    gate_path.write_text(dump_json(envelope), encoding="utf-8", newline="\n")

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=revision_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "text_diff_consistency_passed" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_executed_ablation_refuses_ablation_informed_packet_not_ready(tmp_path):
    config, revision_payload = build_fake_ablation_informed_revision_packet(tmp_path)
    gate_path = Path(revision_payload["packet_dir"], "cycle2_gate_report.json")
    envelope = json.loads(gate_path.read_text(encoding="utf-8"))
    envelope["payload"]["integrity"]["ready_for_executed_ablation"] = False
    gate_path.write_text(dump_json(envelope), encoding="utf-8", newline="\n")

    result = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=revision_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "ready_for_executed_ablation" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_executed_ablation_openai_guard_refuses_ablation_informed_packet(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, revision_payload = build_fake_ablation_informed_revision_packet(tmp_path)
    clients = []

    result = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=revision_payload["packet_dir"],
        client_factory=executed_ablation_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert clients == []


def test_executed_ablation_consistency_report_flags_contradictions():
    variant_set = {
        "variants": [
            {
                "variant_id": "executed_ablation_variant_001",
                "evidence_countable": True,
                "operation_matches_actual_change": False,
                "planned_only": False,
            }
        ]
    }
    internal = {
        "comparison_rows": [
            {
                "variant_id": "executed_ablation_variant_001",
                "evidence_countable": True,
                "planned_only": False,
            }
        ]
    }
    old_new = {
        "strongest_rival_still_beats_candidate": False,
        "another_revision_cycle_justified": False,
        "repair_has_causal_support": True,
        "revert_performs_same_or_better": True,
        "summary": "The rival still beats the candidate, so another cycle is needed.",
        "rationale": "The rival still beats the candidate.",
        "comparison_basis": "diagnostic",
    }

    report = _build_comparison_consistency_report(
        variant_set=variant_set,
        internal_comparison=internal,
        old_new_comparison=old_new,
        fixture_only=True,
    )

    assert report["comparison_internal_consistency"] is False
    assert report["countable_as_gate_evidence"] is False
    assert report["contradictions"]
    assert any("rival" in item for item in report["contradictions"])
    assert any("revert performs" in item for item in report["contradictions"])
    assert any("operation mismatch" in item for item in report["contradictions"])


def test_target_aware_ablation_consistency_rejects_stale_macro_labels():
    variant_set = {
        "target_aware_ablation": True,
        "variants": [
            {
                "variant_id": "executed_ablation_variant_001",
                "operation_id": "operation_preserve_object_motion_remove_tactile_force_relation",
                "variant_role": "tactile_removed_object_motion_preserved_control",
                "evidence_countable": True,
                "operation_matches_actual_change": True,
                "planned_only": False,
            }
        ],
    }
    internal = {
        "comparison_rows": [
            {
                "variant_id": "executed_ablation_variant_001",
                "operation_id": "operation_preserve_object_motion_remove_tactile_force_relation",
                "evidence_countable": True,
                "planned_only": False,
                "comparison_summary": "This is a proof/no-outside-answer isolation test.",
                "reader_state_effect_estimate": "It improves record compression.",
                "rationale": "Stale generic macro framing.",
                "risk_notes": "",
            }
        ]
    }
    old_new = {
        "tactile_force_contact_adds_value": False,
        "summary": "diagnostic only",
        "rationale": "diagnostic only",
        "comparison_basis": "diagnostic only",
    }

    report = _build_comparison_consistency_report(
        variant_set=variant_set,
        internal_comparison=internal,
        old_new_comparison=old_new,
        fixture_only=True,
    )

    failures = "\n".join(report["target_role_consistency_failures"])
    assert report["target_role_consistency_checked"] is True
    assert report["target_role_consistency_passed"] is False
    assert report["comparison_internal_consistency"] is False
    assert "proof/no-outside-answer" in failures
    assert "record compression" in failures


def test_tactile_causal_report_blocks_when_tactile_removed_control_matches_or_beats():
    subject = type(
        "DummyTactileSubject",
        (),
        {
            "target_adapter_id": "tactile_inevitability",
            "selected_residual_target_id": TACTILE_INEVITABILITY_TARGET_ID,
            "target_scope": TACTILE_INEVITABILITY_TARGET_ID,
            "target_movement": TACTILE_INEVITABILITY_TARGET_ID,
            "selected_region_id": RESIDUAL_WORK_ORDER_SELECTED_REGION_ID,
            "target_unit_ids": ("tactile_unit_001",),
            "target_specific_ablation_controls": (
                "preserve_object_motion_remove_tactile_force_relation",
            ),
            "revision_packet_id": "packet_0063",
            "target_aware_ablation": True,
            "previous_generic_ablation_packet_id": "packet_0026",
        },
    )()
    variant_set = {
        "variants": [
            {
                "variant_id": "executed_ablation_variant_002",
                "operation_id": "operation_preserve_object_motion_remove_tactile_force_relation",
                "evidence_countable": True,
            }
        ]
    }
    old_new = {
        "tactile_intervention_has_causal_support": True,
        "tactile_force_contact_adds_value": True,
        "object_motion_preserved_tactile_removed_performs_same_or_better": True,
        "revert_to_current_best_performs_same_or_better": False,
        "decorative_or_abstract_control_performs_same_or_better": False,
        "packet_0063_earns_reader_state_eval": True,
        "candidate_earns_reader_state_eval": True,
        "revised_improves_over_original": True,
        "strongest_rival_still_beats_candidate": True,
    }
    consistency = {
        "comparison_internal_consistency": True,
        "target_role_consistency_checked": True,
        "target_role_consistency_passed": True,
        "target_role_consistency_failures": [],
    }

    report = _build_tactile_causal_effect_report(
        subject=subject,
        variant_set=variant_set,
        old_new_comparison=old_new,
        consistency_report=consistency,
        fixture_only=False,
    )

    assert report["target_role_consistency_passed"] is True
    assert (
        report["object_motion_preserved_tactile_removed_performs_same_or_better"]
        is True
    )
    assert report["tactile_intervention_has_causal_support"] is False
    assert report["packet_0063_earns_reader_state_eval"] is False
    assert report["candidate_earns_reader_state_eval"] is False
    assert report["selected_repair_causal_status"] == "noncausal_or_cosmetic"


def test_executed_ablation_openai_guard_refuses_before_model_call(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, revision_payload = build_fake_revision_packet(tmp_path, with_rival=True)

    result = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=revision_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_executed_ablation_stubbed_openai_success_links_model_call(tmp_path):
    config, revision_payload = build_fake_revision_packet(tmp_path, with_rival=True)
    clients = []

    result = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=revision_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation-model",
        client_factory=executed_ablation_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 1
    assert len(clients[0].requests) == 1
    assert clients[0].requests[0].schema == EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA
    comparison = read_payload(
        result.payload["artifact_paths"]["ablation_internal_reader_comparison"]
    )
    assert comparison["model_call_id"] == result.payload["model_calls"][0]["id"]
    assert comparison["controller_owned_evidence_status"] is True
    assert result.payload["model_calls"][0]["parsed_output_artifact_id"] == result.payload[
        "artifact_ids"
    ]["ablation_internal_reader_comparison"]


def test_executed_ablation_invalid_model_output_fails_before_parsed_artifact(tmp_path):
    config, revision_payload = build_fake_revision_packet(tmp_path, with_rival=True)
    clients = []

    result = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=revision_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation-model",
        client_factory=executed_ablation_stub_factory(clients, mode="invalid"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 1
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == EXECUTED_ABLATION_INTERNAL_COMPARISON_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "ablation_internal_reader_comparison" not in result.payload["artifact_ids"]
    assert "executed_ablation_gate_report" not in result.payload["artifact_ids"]


def test_ablation_informed_revision_fake_creates_cycle2_packet(tmp_path):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert set(result.payload["artifact_ids"]) == set(
        ABLATION_INFORMED_REVISION_ARTIFACT_TYPES
    )
    assert result.payload["counts"]["model_calls"] == 0

    subject = read_payload(
        result.payload["artifact_paths"]["ablation_informed_revision_subject_manifest"]
    )
    assert subject["source_autonomous_revision_packet_id"] == "packet_0001"
    assert subject["source_reader_lab_packet_id"] == "packet_0001"
    assert subject["strongest_rival"] is not None

    evidence = read_payload(result.payload["artifact_paths"]["ablation_evidence_summary"])
    assert evidence["previous_repair_treated_as_proven"] is False
    assert evidence["packet_0030_treated_as_proven_improvement"] is False
    assert evidence["previous_repair_causal_status"] in {
        "noncausal_or_cosmetic",
        "ambiguous",
        "useful_but_insufficient",
    }
    assert "record" in evidence["evidence_interpretation"]

    dominance = read_payload(
        result.payload["artifact_paths"]["ablation_evidence_dominance_report"]
    )
    assert dominance["dominance_detected"] is True
    assert dominance["best_countable_variant_id"]
    assert dominance["recommended_base_candidate_id"] == BASE_CHOICE_DOMINANT_VARIANT

    base = read_payload(result.payload["artifact_paths"]["cycle2_base_candidate_selection"])
    assert base["selected_base_choice"] == BASE_CHOICE_DOMINANT_VARIANT
    assert base["previous_repair_treated_as_proven"] is False
    assert base["embodiment_preserving_insight_represented"] is True
    assert base["record_law_proof_compression_deferred_to_patch"] is True
    assert "packet_0030_revised_candidate" in base["allowed_choices"]
    assert BASE_CHOICE_DOMINANT_VARIANT in base["allowed_choices"]
    assert base["ablation_evidence_dominance"][
        "dominant_variant_promoted_or_justified"
    ] is True
    assert base["ablation_evidence_dominance"][
        "selected_base_dominated_by_available_variant"
    ] is False
    assert "as if nothing happened" not in base["selected_base_text"]

    handle = read_payload(result.payload["artifact_paths"]["selected_next_failure_or_handle"])
    assert handle["selected_next_handle"] == "record_law_proof_answer_compression"
    assert handle["strongest_rival_pressure_preserved"] is True
    assert "opening patch" in handle["why_better_supported_than_repeating_opening_patch"]

    work_order = read_payload(
        result.payload["artifact_paths"]["ablation_informed_revision_work_order"]
    )
    assert work_order["controller_owned"] is True
    assert work_order["selected_base_candidate"] == BASE_CHOICE_DOMINANT_VARIANT
    assert work_order["base_candidate_text_sha256"] == base["selected_base_text_sha256"]
    if not work_order["dominance_policy"]["dominant_variant_directly_selected"]:
        assert work_order["patchable_spans"]
    assert work_order["strongest_rival_reference"] is not None

    patch = read_payload(result.payload["artifact_paths"]["cycle2_patch_proposal"])
    assert patch["bounded_patch_set"] is True
    assert patch["full_rewrite"] is False
    if not patch["dominance_policy"]["dominant_variant_directly_selected"]:
        assert patch["patches"]
    assert all(item["bounded_patch"] is True for item in patch["patches"])

    ledger = read_payload(result.payload["artifact_paths"]["cycle2_applied_patch_ledger"])
    assert ledger["controller_owned"] is True
    assert ledger["proposed_patch_count"] == len(patch["patches"])
    assert ledger["applied_patch_count"] == len(patch["patches"])
    assert ledger["rejected_patch_count"] == 0
    assert ledger["all_applied_patches_reflected_in_text"] is True

    revised = read_payload(result.payload["artifact_paths"]["cycle2_revised_candidate_text"])
    assert revised["assembled_by_controller"] is True
    assert revised["bounded_recomposition"] is True
    assert revised["full_rewrite"] is False
    assert revised["non_final"] is True
    assert revised["not_finalization_eligible"] is True
    assert revised["supersedes_packet_0030_patch"] is True
    assert revised["applied_patch_ids"] == ledger["applied_patch_ids"]
    assert revised["source_patch_ids"] == ledger["applied_patch_ids"]
    assert revised["applied_patch_count"] == ledger["applied_patch_count"]

    diff = read_payload(result.payload["artifact_paths"]["cycle2_revision_diff_report"])
    assert diff["controller_owned"] is True
    if patch["patches"]:
        assert diff["changed_spans"]
        assert all(span["before_text"] for span in diff["changed_spans"])
        assert all(span["after_text"] for span in diff["changed_spans"])
        assert all("evidence_source" in span for span in diff["changed_spans"])
    assert diff["diff_changed_span_count"] == ledger["applied_patch_count"]
    assert diff["source_patch_ids"] == ledger["applied_patch_ids"]
    assert diff["text_matches_diff"] is True
    assert diff["all_applied_patches_reflected_in_text"] is True

    comparison = read_payload(
        result.payload["artifact_paths"]["cycle2_preliminary_old_new_rival_comparison"]
    )
    assert comparison["preliminary_not_proof"] is True
    assert comparison["does_not_count_as_executed_ablation_evidence"] is True
    assert comparison["comparison_uses_actual_revised_text"] is True
    assert comparison["actual_revised_text_sha256"] == revised["text_sha256"]
    assert comparison["record_law_proof_compression_improved_discovery"] is True
    assert comparison["cycle2_should_proceed_to_executed_ablation_next"] is True

    gate = read_payload(result.payload["artifact_paths"]["cycle2_gate_report"])
    assert gate["eligible"] is False
    assert gate["passed"] is False
    assert gate["final_gates_marked_passed"] == []
    assert gate["cycle2_requires_executed_ablation_before_claim"] is True
    assert gate["integrity"]["text_diff_consistency_passed"] is True
    assert gate["integrity"]["comparison_uses_actual_revised_text"] is True
    assert gate["integrity"]["mechanical_ready_for_ablation"] is True
    assert gate["integrity"]["strategic_ready_for_ablation"] is True
    assert gate["integrity"]["ready_for_executed_ablation"] is True
    assert gate["integrity"]["evidence_dominance_checked"] is True
    assert gate["integrity"]["dominant_variant_promoted_or_justified"] is True
    assert gate["integrity"]["selected_base_dominated_by_available_variant"] is False
    assert gate["human_validation_required"] is False
    assert gate["paper_validation_required"] is False
    assert gate["phase_shift_claim"] is False

    with connect(config.db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True
    assert "paper" not in final_report.message.lower()


def test_ablation_informed_revision_dominance_report_identifies_best_variant(tmp_path):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 0
    dominance = read_payload(
        result.payload["artifact_paths"]["ablation_evidence_dominance_report"]
    )
    assert dominance["dominance_detected"] is True
    assert dominance["best_countable_variant_id"] == "executed_ablation_variant_003"
    assert dominance["best_countable_variant_operation"] == (
        "operation_record_label_compression"
    )
    assert dominance["best_variant_improves_discovery"] is True
    assert dominance["best_variant_reduces_overexplanation"] is True
    assert dominance["best_variant_preserves_or_improves_embodiment"] is True
    assert dominance["recommended_base_candidate_id"] == BASE_CHOICE_DOMINANT_VARIANT


def test_ablation_informed_revision_controls_cannot_dominate(tmp_path):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    dominance = read_payload(
        result.payload["artifact_paths"]["ablation_evidence_dominance_report"]
    )
    analyses = {item["variant_id"]: item for item in dominance["variant_analysis"]}
    assert analyses["executed_ablation_variant_004"]["dominates_source_revision"] is False
    assert "not_evidence_countable" in analyses["executed_ablation_variant_004"][
        "disqualifiers"
    ]
    assert "no_op" in analyses["executed_ablation_variant_004"]["disqualifiers"]
    assert analyses["executed_ablation_variant_005"]["dominates_source_revision"] is False
    assert "operation_mismatch" in analyses["executed_ablation_variant_005"][
        "disqualifiers"
    ]
    assert analyses["executed_ablation_variant_006"]["dominates_source_revision"] is False
    assert "planned_only" in analyses["executed_ablation_variant_006"]["disqualifiers"]


def test_ablation_informed_revision_lower_embodiment_variant_does_not_dominate(
    tmp_path,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    comparison_path = Path(
        ablation_payload["artifact_paths"]["ablation_old_new_rival_comparison"]
    )

    def _lower_embodiment(payload):
        source = payload["revised_score"]
        scores = payload["variant_scores"]["executed_ablation_variant_003"]
        scores["discovery_score"] = source["discovery_score"] + 5
        scores["overexplanation_score"] = source["overexplanation_score"] - 1
        scores["local_embodiment_score"] = source["local_embodiment_score"] - 1

    rewrite_payload(comparison_path, _lower_embodiment)

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 0
    dominance = read_payload(
        result.payload["artifact_paths"]["ablation_evidence_dominance_report"]
    )
    assert dominance["dominance_detected"] is False
    record = {
        item["variant_id"]: item for item in dominance["variant_analysis"]
    }["executed_ablation_variant_003"]
    assert "protected_embodiment_loss" in record["disqualifiers"]


def test_ablation_informed_revision_base_options_include_dominant_variant(tmp_path):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    base = read_payload(result.payload["artifact_paths"]["cycle2_base_candidate_selection"])
    option_ids = {option["base_candidate_id"] for option in base["base_candidate_options"]}
    assert BASE_CHOICE_DOMINANT_VARIANT in option_ids
    assert base["selected_base_candidate_id"] == BASE_CHOICE_DOMINANT_VARIANT


def test_ablation_informed_revision_weaker_base_without_rejection_fails_closed(
    tmp_path,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(clients, mode="weaker_base"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 1
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "explicit_dominance_rejection_reason" in failed_call["error_message"]
    assert "cycle2_base_candidate_selection" not in result.payload["artifact_ids"]


def test_ablation_informed_revision_weaker_base_with_rejection_is_recorded(
    tmp_path,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(
            clients,
            mode="dominance_rejection",
        ),
    )

    assert result.exit_code == 0
    base = read_payload(result.payload["artifact_paths"]["cycle2_base_candidate_selection"])
    gate = read_payload(result.payload["artifact_paths"]["cycle2_gate_report"])
    assert base["selected_base_candidate_id"] == BASE_CHOICE_CONTROLLER_COMPOSED
    assert base["ablation_evidence_dominance"][
        "selected_base_dominated_by_available_variant"
    ] is True
    assert base["ablation_evidence_dominance"][
        "dominant_variant_promoted_or_justified"
    ] is True
    assert "protected" in base["ablation_evidence_dominance"][
        "dominance_rejection_protected_effect_or_forbidden_change_evidence"
    ].lower()
    assert gate["integrity"]["selected_base_dominated_by_available_variant"] is True
    assert gate["integrity"]["strategic_ready_for_ablation"] is False
    assert gate["integrity"]["ready_for_executed_ablation"] is False


def test_ablation_informed_revision_regressive_patch_is_flagged(tmp_path):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(clients, mode="regressive_patch"),
    )

    assert result.exit_code == 0
    comparison = read_payload(
        result.payload["artifact_paths"]["cycle2_preliminary_old_new_rival_comparison"]
    )
    gate = read_payload(result.payload["artifact_paths"]["cycle2_gate_report"])
    assert comparison["ablation_evidence_dominance"][
        "patch_regresses_from_dominant_variant"
    ] is True
    assert comparison["ablation_evidence_dominance"]["dominance_regression_reasons"]
    assert gate["integrity"]["patch_regresses_from_dominant_variant"] is True
    assert gate["integrity"]["strategic_ready_for_ablation"] is False


def test_ablation_informed_revision_accepts_ablation_informed_source_packet(tmp_path):
    config, ablation_payload, source_revision_payload = (
        build_fake_executed_ablation_from_ablation_informed_packet(tmp_path)
    )

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["source_revision_packet_kind"] == "ablation_informed_revision"
    assert result.payload["source_revision_packet_id"] == source_revision_payload["packet_id"]

    subject = read_payload(
        result.payload["artifact_paths"]["ablation_informed_revision_subject_manifest"]
    )
    assert subject["source_revision_packet_kind"] == "ablation_informed_revision"
    assert subject["source_revision_packet_id"] == source_revision_payload["packet_id"]
    assert subject["source_patch_ledger"]["all_applied_patches_reflected_in_text"] is True
    assert "source_patch_span_ids" in subject["source_revision_diff"]
    assert subject["source_revised_candidate"]["artifact_id"] == subject[
        "revision_artifact_ids"
    ]["revised_candidate_text"]

    evidence = read_payload(result.payload["artifact_paths"]["ablation_evidence_summary"])
    assert evidence["source_revision_packet_kind"] == "ablation_informed_revision"
    assert evidence["source_revision_packet_id"] == source_revision_payload["packet_id"]
    assert evidence["previous_repair_causal_status"] in {
        "noncausal_or_cosmetic",
        "ambiguous",
        "useful_but_insufficient",
    }
    assert "recommended_next_action" in evidence
    assert evidence["previous_repair_treated_as_proven"] is False

    base = read_payload(result.payload["artifact_paths"]["cycle2_base_candidate_selection"])
    assert base["source_revision_packet_kind"] == "ablation_informed_revision"
    assert base["source_revision_packet_id"] == source_revision_payload["packet_id"]
    assert any(
        option["base_candidate_id"]
        in {BASE_CHOICE_SOURCE_REVISION_CURRENT, BASE_CHOICE_PACKET_0030}
        and "ablation_informed_revision" in option["basis"]
        for option in base["base_candidate_options"]
    )

    work_order = read_payload(
        result.payload["artifact_paths"]["ablation_informed_revision_work_order"]
    )
    assert work_order["source_revision_packet_kind"] == "ablation_informed_revision"
    assert work_order["source_revision_packet_id"] == source_revision_payload["packet_id"]

    packet = read_payload(result.payload["artifact_paths"]["cycle2_packet"])
    assert packet["source_revision_packet_kind"] == "ablation_informed_revision"
    assert packet["source_revision_packet_id"] == source_revision_payload["packet_id"]

    gate = read_payload(result.payload["artifact_paths"]["cycle2_gate_report"])
    assert gate["eligible"] is False
    assert gate["phase_shift_claim"] is False
    assert gate["final_gates_marked_passed"] == []


def test_ablation_informed_revision_pivot_report_triggers_for_plateaued_handle(
    tmp_path,
):
    config, ablation_payload, _source_revision_payload = (
        build_pivot_required_executed_ablation_packet(tmp_path)
    )

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 0
    pivot = read_payload(result.payload["artifact_paths"]["residual_blocker_pivot_report"])
    candidate_ids = {
        candidate["blocker_id"] for candidate in pivot["residual_blocker_candidates"]
    }
    assert pivot["pivot_required"] is True
    assert pivot["prior_handle"] == HANDLE_RECORD_COMPRESSION
    assert pivot["prior_handle_status"] == "exhausted_for_now"
    assert pivot["same_handle_improvement_signal"] is False
    assert pivot["same_handle_allowed"] is False
    assert set(RESIDUAL_BLOCKER_CANDIDATES).issubset(candidate_ids)
    assert pivot["selected_residual_blocker"] in RESIDUAL_BLOCKER_CANDIDATES
    assert pivot["selected_residual_blocker"] != HANDLE_RECORD_COMPRESSION


def test_ablation_informed_revision_fake_pivots_from_stale_record_handle(
    tmp_path,
):
    config, ablation_payload, _source_revision_payload = (
        build_pivot_required_executed_ablation_packet(tmp_path)
    )

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    base = read_payload(result.payload["artifact_paths"]["cycle2_base_candidate_selection"])
    handle = read_payload(result.payload["artifact_paths"]["selected_next_failure_or_handle"])
    work_order = read_payload(
        result.payload["artifact_paths"]["ablation_informed_revision_work_order"]
    )
    ledger = read_payload(result.payload["artifact_paths"]["cycle2_applied_patch_ledger"])
    revised = read_payload(result.payload["artifact_paths"]["cycle2_revised_candidate_text"])
    gate = read_payload(result.payload["artifact_paths"]["cycle2_gate_report"])
    packet = read_payload(result.payload["artifact_paths"]["cycle2_packet"])

    selected_residual = handle["selected_residual_blocker"]
    assert base["selected_base_choice"] == BASE_CHOICE_SOURCE_REVISION_CURRENT
    assert base["pivot_required"] is True
    assert base["base_selection_locked_by_controller"] is True
    assert base["preserved_source_revision_packet_id"] == _source_revision_payload[
        "packet_id"
    ]
    assert base["preserved_useful_repair"] is True
    assert base["prior_handle_preserved"] is True
    assert base["prior_handle_status"] == "exhausted_for_now"
    assert base["model_call_id"] is None
    assert base["why_model_did_not_own_base_selection"]
    assert base["residual_blocker_pivot"]["base_preserves_current_useful_repair"] is True
    assert base["residual_blocker_pivot"]["base_selection_locked_by_controller"] is True
    assert set(base["allowed_choices"]) == {
        BASE_CHOICE_SOURCE_REVISION_CURRENT,
        BASE_CHOICE_CONTROLLER_COMPOSED,
    }
    assert BASE_CHOICE_ORIGINAL not in set(base["allowed_choices"])
    assert base["unavailable_base_options"]
    assert handle["selected_next_handle"] == selected_residual
    assert selected_residual in RESIDUAL_BLOCKER_CANDIDATES
    assert selected_residual != HANDLE_RECORD_COMPRESSION
    assert handle["residual_blocker_pivot"]["same_handle_reselected"] is False
    assert work_order["selected_residual_blocker"] == selected_residual
    assert work_order["allowed_patch_target_ids"] == [f"cycle2_target_{selected_residual}"]
    assert all(
        HANDLE_RECORD_COMPRESSION not in span["patch_target_id"]
        for span in work_order["patchable_spans"]
    )
    assert ledger["residual_blocker_pivot_policy"]["pivot_policy_satisfied"] is True
    assert revised["residual_blocker_pivot_policy"]["selected_residual_blocker"] == (
        selected_residual
    )
    assert gate["strongest_rival_pressure_preserved"] is True
    assert gate["integrity"]["prior_handle_preserved"] is True
    assert gate["integrity"]["pivot_required"] is True
    assert gate["integrity"]["residual_blocker_selected"] is True
    assert gate["integrity"]["same_handle_reselected"] is False
    assert gate["integrity"]["pivot_policy_satisfied"] is True
    assert gate["residual_blocker_pivot"]["selected_residual_blocker"] == (
        selected_residual
    )
    assert packet["residual_blocker_pivot"]["selected_residual_blocker"] == (
        selected_residual
    )

    with connect(config.db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_ablation_informed_revision_stubbed_openai_pivot_uses_controller_locked_base(
    tmp_path,
):
    config, ablation_payload, source_revision_payload = (
        build_pivot_required_executed_ablation_packet(tmp_path)
    )
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(clients, mode="invented_base"),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 2
    assert [request.schema for request in clients[0].requests] == [
        ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA,
        ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA,
    ]

    base_path = Path(result.payload["artifact_paths"]["cycle2_base_candidate_selection"])
    base_envelope = json.loads(base_path.read_text(encoding="utf-8"))
    base = base_envelope["payload"]
    handle = read_payload(result.payload["artifact_paths"]["selected_next_failure_or_handle"])
    patch = read_payload(result.payload["artifact_paths"]["cycle2_patch_proposal"])
    work_order = read_payload(
        result.payload["artifact_paths"]["ablation_informed_revision_work_order"]
    )
    gate = read_payload(result.payload["artifact_paths"]["cycle2_gate_report"])

    assert base_envelope["model_call_id"] is None
    assert base_envelope["fixture_only"] is False
    assert base["model_call_id"] is None
    assert base["base_selection_locked_by_controller"] is True
    assert base["selected_base_candidate_id"] == BASE_CHOICE_SOURCE_REVISION_CURRENT
    assert base["preserved_source_revision_packet_id"] == source_revision_payload[
        "packet_id"
    ]
    assert base["preserved_useful_repair"] is True
    assert base["prior_handle_preserved"] is True
    assert base["why_model_did_not_own_base_selection"]
    assert all(
        option["base_candidate_id"] in PIVOT_REPAIR_PRESERVING_BASE_CHOICES
        for option in base["base_candidate_options"]
    )
    assert base["unavailable_base_options"]

    selected_residual = handle["selected_residual_blocker"]
    assert selected_residual in RESIDUAL_BLOCKER_CANDIDATES
    assert selected_residual != HANDLE_RECORD_COMPRESSION
    assert work_order["allowed_patch_target_ids"] == [f"cycle2_target_{selected_residual}"]
    assert all(
        item["patch_span_id"] in work_order["patchable_span_ids"]
        for item in patch["patches"]
    )
    assert gate["integrity"]["pivot_required"] is True
    assert gate["integrity"]["pivot_policy_satisfied"] is True
    assert gate["phase_shift_claim"] is False
    assert gate["final_gates_marked_passed"] == []

    with connect(config.db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_ablation_informed_revision_same_handle_without_justification_fails_closed(
    tmp_path,
):
    config, ablation_payload, _source_revision_payload = (
        build_pivot_required_executed_ablation_packet(tmp_path)
    )
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(
            clients,
            mode="same_handle_no_justification",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 1
    assert "explicit_same_handle_justification" in result.payload["message"]
    assert [request.schema for request in clients[0].requests] == [
        ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA,
    ]
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "cycle2_base_candidate_selection" in result.payload["artifact_ids"]
    assert "selected_next_failure_or_handle" not in result.payload["artifact_ids"]
    assert "cycle2_packet" not in result.payload["artifact_ids"]


def test_ablation_informed_revision_same_handle_with_justification_reaches_patch_policy(
    tmp_path,
):
    config, ablation_payload, _source_revision_payload = (
        build_pivot_required_executed_ablation_packet(tmp_path)
    )
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(
            clients,
            mode="same_handle_justified",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 2
    assert "patch proposal must include at least one patch" in result.payload["message"]
    assert [request.schema for request in clients[0].requests] == [
        ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA,
        ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA,
    ]
    handle = read_payload(result.payload["artifact_paths"]["selected_next_failure_or_handle"])
    work_order = read_payload(
        result.payload["artifact_paths"]["ablation_informed_revision_work_order"]
    )

    assert handle["selected_next_handle"] == HANDLE_RECORD_COMPRESSION
    assert handle["selected_residual_blocker"] is None
    assert handle["residual_blocker_pivot"]["same_handle_reselected"] is True
    assert handle["residual_blocker_pivot"][
        "same_handle_reselected_with_justification"
    ] is True
    assert "protected" in handle["residual_blocker_pivot"][
        "same_handle_justification_evidence"
    ].lower()
    assert work_order["residual_blocker_pivot_policy"]["pivot_policy_satisfied"] is True
    assert work_order["residual_blocker_pivot_policy"]["selected_residual_blocker"] is None
    assert result.payload["model_calls"][-1]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "cycle2_patch_proposal" not in result.payload["artifact_ids"]
    assert "cycle2_packet" not in result.payload["artifact_ids"]


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("cycle2_revised_candidate_text.json", "cycle2_revised_candidate_text.json"),
        ("cycle2_revision_diff_report.json", "cycle2_revision_diff_report.json"),
        ("cycle2_applied_patch_ledger.json", "cycle2_applied_patch_ledger.json"),
    ],
)
def test_ablation_informed_revision_refuses_ablation_informed_source_missing_file(
    tmp_path,
    filename,
    expected,
):
    config, ablation_payload, source_revision_payload = (
        build_fake_executed_ablation_from_ablation_informed_packet(tmp_path)
    )
    Path(source_revision_payload["packet_dir"], filename).unlink()

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert expected in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


@pytest.mark.parametrize(
    ("field_name", "expected"),
    [
        ("text_diff_consistency_passed", "text_diff_consistency_passed"),
        ("comparison_uses_actual_revised_text", "comparison_uses_actual_revised_text"),
    ],
)
def test_ablation_informed_revision_refuses_ablation_informed_source_bad_integrity(
    tmp_path,
    field_name,
    expected,
):
    config, ablation_payload, source_revision_payload = (
        build_fake_executed_ablation_from_ablation_informed_packet(tmp_path)
    )
    gate_path = Path(source_revision_payload["packet_dir"], "cycle2_gate_report.json")
    envelope = json.loads(gate_path.read_text(encoding="utf-8"))
    envelope["payload"]["integrity"][field_name] = False
    gate_path.write_text(dump_json(envelope), encoding="utf-8", newline="\n")

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert expected in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_ablation_informed_revision_openai_guard_refuses_ablation_informed_source(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, ablation_payload, _source_revision_payload = (
        build_fake_executed_ablation_from_ablation_informed_packet(tmp_path)
    )
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        client_factory=ablation_informed_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert clients == []


def test_ablation_informed_revision_refuses_missing_packet(tmp_path):
    config = config_for(tmp_path)

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=tmp_path / "missing_ablation_packet",
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "not found" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_ablation_informed_revision_refuses_without_causal_effect_report(tmp_path):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    invalid_packet = tmp_path / "invalid_executed_ablation_packet"
    shutil.copytree(Path(ablation_payload["packet_dir"]), invalid_packet)
    packet_path = invalid_packet / "executed_ablation_packet.json"
    envelope = json.loads(packet_path.read_text(encoding="utf-8"))
    del envelope["payload"]["artifact_ids"]["ablation_causal_effect_report"]
    packet_path.write_text(dump_json(envelope), encoding="utf-8", newline="\n")

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "ablation_causal_effect_report" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_ablation_informed_revision_openai_guard_refuses_before_model_call(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_ablation_informed_revision_openai_refuses_without_api_key(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        client_factory=ablation_informed_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert clients == []


def test_ablation_informed_revision_stubbed_openai_success_is_controller_bounded(
    tmp_path,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert set(result.payload["artifact_ids"]) == set(
        ABLATION_INFORMED_REVISION_ARTIFACT_TYPES
    )
    assert result.payload["counts"]["model_calls"] == 3
    assert len(clients) == 1
    assert [request.schema for request in clients[0].requests] == [
        ABLATION_INFORMED_BASE_SELECTION_SCHEMA,
        ABLATION_INFORMED_HANDLE_SELECTION_SCHEMA,
        ABLATION_INFORMED_PATCH_PROPOSAL_SCHEMA,
    ]
    assert all(
        call["provider"] == "openai" and call["model"] == "stub-ablation-informed-model"
        for call in result.payload["model_calls"]
    )
    assert all(call["status"] == MODEL_CALL_SUCCESS for call in result.payload["model_calls"])

    base = read_payload(result.payload["artifact_paths"]["cycle2_base_candidate_selection"])
    handle = read_payload(result.payload["artifact_paths"]["selected_next_failure_or_handle"])
    patch = read_payload(result.payload["artifact_paths"]["cycle2_patch_proposal"])
    work_order = read_payload(
        result.payload["artifact_paths"]["ablation_informed_revision_work_order"]
    )
    ledger = read_payload(result.payload["artifact_paths"]["cycle2_applied_patch_ledger"])
    revised = read_payload(result.payload["artifact_paths"]["cycle2_revised_candidate_text"])
    diff = read_payload(result.payload["artifact_paths"]["cycle2_revision_diff_report"])
    comparison = read_payload(
        result.payload["artifact_paths"]["cycle2_preliminary_old_new_rival_comparison"]
    )
    gate = read_payload(result.payload["artifact_paths"]["cycle2_gate_report"])

    for artifact_type, call in zip(
        (
            "cycle2_base_candidate_selection",
            "selected_next_failure_or_handle",
            "cycle2_patch_proposal",
        ),
        result.payload["model_calls"],
        strict=True,
    ):
        envelope = json.loads(
            Path(result.payload["artifact_paths"][artifact_type]).read_text(
                encoding="utf-8"
            )
        )
        assert envelope["model_call_id"] == call["id"]
        assert envelope["fixture_only"] is False
        assert read_payload(result.payload["artifact_paths"][artifact_type])[
            "model_call_id"
        ] == call["id"]
        assert call["parsed_output_artifact_id"] == result.payload["artifact_ids"][
            artifact_type
        ]

    option_ids = {option["base_candidate_id"] for option in base["base_candidate_options"]}
    assert base["selected_base_candidate_id"] in option_ids
    assert base["selected_base_choice"] == BASE_CHOICE_DOMINANT_VARIANT
    assert base["previous_repair_treated_as_proven"] is False
    assert "proof" in base["model_record_law_proof_answer_insight"]
    assert base["ablation_evidence_dominance"][
        "dominant_variant_promoted_or_justified"
    ] is True

    assert handle["selected_next_handle"] == "record_law_proof_answer_compression"
    assert handle["strongest_rival_pressure_preserved"] is True
    assert handle["controller_owned_evidence_selection"] is True

    assert work_order["controller_owned"] is True
    assert work_order["dominance_policy"]["dominant_variant_directly_selected"] is True
    assert patch["bounded_patch_set"] is True
    assert patch["full_rewrite"] is False
    assert len(patch["patches"]) == len(work_order["patchable_spans"])
    assert all(
        item["patch_span_id"] in work_order["patchable_span_ids"]
        for item in patch["patches"]
    )
    assert all(item["before_text_owned_by_controller"] for item in patch["patches"])

    assert ledger["proposed_patch_count"] == len(patch["patches"])
    assert ledger["applied_patch_count"] == len(patch["patches"])
    assert ledger["rejected_patch_count"] == 0
    assert ledger["applied_patch_ids"] == [item["patch_id"] for item in patch["patches"]]
    assert ledger["all_applied_patches_reflected_in_text"] is True

    assert revised["assembled_by_controller"] is True
    assert revised["full_rewrite"] is False
    assert revised["source_patch_ids"] == ledger["applied_patch_ids"]
    assert revised["applied_patch_ids"] == ledger["applied_patch_ids"]
    assert revised["applied_patch_count"] == ledger["applied_patch_count"]
    assert diff["controller_owned"] is True
    assert diff["diff_changed_span_count"] == ledger["applied_patch_count"]
    assert diff["source_patch_ids"] == ledger["applied_patch_ids"]
    assert diff["text_matches_diff"] is True
    assert diff["all_diff_spans_reflected_in_text"] is True
    assert all(span["before_text"] for span in diff["changed_spans"])
    assert comparison["preliminary_not_proof"] is True
    assert comparison["does_not_count_as_executed_ablation_evidence"] is True
    assert comparison["comparison_uses_actual_revised_text"] is True
    assert comparison["actual_revised_text_sha256"] == revised["text_sha256"]
    assert gate["eligible"] is False
    assert gate["passed"] is False
    assert gate["integrity"]["proposed_patch_count"] == ledger["proposed_patch_count"]
    assert gate["integrity"]["applied_patch_count"] == ledger["applied_patch_count"]
    assert gate["integrity"]["rejected_patch_count"] == 0
    assert gate["integrity"]["text_diff_consistency_passed"] is True
    assert gate["integrity"]["comparison_uses_actual_revised_text"] is True
    assert gate["integrity"]["mechanical_ready_for_ablation"] is True
    assert gate["integrity"]["strategic_ready_for_ablation"] is True
    assert gate["integrity"]["ready_for_executed_ablation"] is True
    assert gate["integrity"]["selected_base_dominated_by_available_variant"] is False
    assert gate["human_validation_required"] is False
    assert gate["paper_validation_required"] is False
    assert gate["phase_shift_claim"] is False
    assert gate["final_gates_marked_passed"] == []

    with connect(config.db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True
    assert "paper" not in final_report.message.lower()


def test_ablation_informed_revision_stubbed_openai_rejects_noop_patch_without_diff(
    tmp_path,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(clients, mode="noop_patch"),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True

    patch = read_payload(result.payload["artifact_paths"]["cycle2_patch_proposal"])
    ledger = read_payload(result.payload["artifact_paths"]["cycle2_applied_patch_ledger"])
    revised = read_payload(result.payload["artifact_paths"]["cycle2_revised_candidate_text"])
    diff = read_payload(result.payload["artifact_paths"]["cycle2_revision_diff_report"])

    assert ledger["proposed_patch_count"] == len(patch["patches"])
    assert ledger["rejected_patch_count"] == 1
    assert ledger["rejected_patch_ids"] == ["cycle2_patch_001"]
    assert "cycle2_patch_001" not in revised["applied_patch_ids"]
    assert "cycle2_patch_001" in revised["rejected_patch_ids"]
    assert all(
        span["patch_id"] != "cycle2_patch_001" for span in diff["changed_spans"]
    )
    assert diff["diff_changed_span_count"] == ledger["applied_patch_count"]
    assert diff["text_matches_diff"] is True


def test_ablation_informed_revision_silent_dropped_patch_fails_closed(
    tmp_path,
    monkeypatch,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    comparison_path = Path(
        ablation_payload["artifact_paths"]["ablation_old_new_rival_comparison"]
    )

    def _disable_dominance(payload):
        source = payload["revised_score"]
        for scores in payload["variant_scores"].values():
            scores["discovery_score"] = source["discovery_score"]
            scores["overexplanation_score"] = source["overexplanation_score"]
            scores["local_embodiment_score"] = source["local_embodiment_score"]

    rewrite_payload(comparison_path, _disable_dominance)
    original = ablation_informed_revision_module._build_revised_candidate

    def _dropped_source_patch_ids(*args, **kwargs):
        payload = original(*args, **kwargs)
        payload["source_patch_ids"] = []
        payload["applied_patch_ids"] = []
        return payload

    monkeypatch.setattr(
        ablation_informed_revision_module,
        "_build_revised_candidate",
        _dropped_source_patch_ids,
    )

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "source_patch_ids omits" in result.payload["message"]
    assert "cycle2_applied_patch_ledger" in result.payload["artifact_ids"]
    assert "cycle2_revised_candidate_text" not in result.payload["artifact_ids"]
    assert "cycle2_revision_diff_report" not in result.payload["artifact_ids"]
    assert "cycle2_preliminary_old_new_rival_comparison" not in result.payload["artifact_ids"]
    assert "cycle2_gate_report" not in result.payload["artifact_ids"]
    assert "cycle2_packet" not in result.payload["artifact_ids"]


def test_ablation_informed_revision_unapplied_diff_patch_fails_closed(
    tmp_path,
    monkeypatch,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    original = ablation_informed_revision_module._build_diff_report

    def _diff_reports_unapplied_patch(*args, **kwargs):
        payload = original(*args, **kwargs)
        payload["changed_spans"].append(
            {
                "changed_span_id": "cycle2_change_unapplied",
                "patch_id": "cycle2_patch_unapplied",
                "patch_span_id": "cycle2_patch_span_unapplied",
                "source_patch_span_ids": ["cycle2_patch_span_unapplied"],
                "before_text": "not in base",
                "after_text": "not in revised",
                "operation_type": "replace",
                "change_rationale": "test corruption",
                "evidence_source": "test",
                "preserves_or_supersedes_packet_0030_prior_patch": "supersedes",
                "inside_target": True,
                "within_selected_target": True,
            }
        )
        payload["diff_changed_span_count"] = len(payload["changed_spans"])
        return payload

    monkeypatch.setattr(
        ablation_informed_revision_module,
        "_build_diff_report",
        _diff_reports_unapplied_patch,
    )

    result = run_ablation_informed_revision(
        config,
        client_name="fake",
        executed_ablation_packet=ablation_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "diff reports a patch" in result.payload["message"]
    assert "cycle2_preliminary_old_new_rival_comparison" not in result.payload["artifact_ids"]
    assert "cycle2_gate_report" not in result.payload["artifact_ids"]
    assert "cycle2_packet" not in result.payload["artifact_ids"]


def test_ablation_informed_revision_stubbed_openai_invented_base_fails_closed(
    tmp_path,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(clients, mode="invented_base"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 1
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == ABLATION_INFORMED_BASE_SELECTION_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "cycle2_base_candidate_selection" not in result.payload["artifact_ids"]
    assert "cycle2_packet" not in result.payload["artifact_ids"]


def test_ablation_informed_revision_stubbed_openai_malformed_output_fails_closed(
    tmp_path,
):
    config, ablation_payload = build_fake_executed_ablation_packet(tmp_path)
    clients = []

    result = run_ablation_informed_revision(
        config,
        client_name="openai",
        executed_ablation_packet=ablation_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-ablation-informed-model",
        client_factory=ablation_informed_stub_factory(clients, mode="invalid_json"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 1
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == ABLATION_INFORMED_BASE_SELECTION_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "cycle2_base_candidate_selection" not in result.payload["artifact_ids"]
    assert "cycle2_packet" not in result.payload["artifact_ids"]


def test_stubbed_openai_autonomous_revision_invalid_output_fails_closed(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=revision_stub_factory(
            clients,
            mode="malformed",
            target_schema=AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA,
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 3
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "revised_candidate_text" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_packet" not in result.payload["artifact_ids"]
    assert result.payload["gate_report"] is None

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        revision_calls = [
            call
            for call in list_model_calls(connection, run_id=result.payload["run_id"])
            if call.prompt_contract_id.startswith("autonomous.revision.")
        ]
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(revision_calls) == 3
    revision_artifact_types = {
        artifact.type
        for artifact in artifacts
        if artifact.type in AUTONOMOUS_REVISION_ARTIFACT_TYPES
    }
    assert revision_artifact_types == {
        "autonomous_revision_subject_manifest",
        "selected_failure_diagnosis",
        AUTONOMOUS_REVISION_WORK_ORDER_ARTIFACT_TYPE,
        "causal_handle_selection",
    }
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_creates_fail_closed_decision_packet(tmp_path):
    config, _failed_ablation, _pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)
        run_id = get_latest_run(connection).id

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["finalization_eligible"] is False
    packet_dir = Path(str(result.payload["packet_dir"]))
    assert packet_dir.name == "packet_0001"
    assert set(result.payload["artifact_ids"]) == set(
        AUTONOMOUS_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES
    )
    for artifact_type in AUTONOMOUS_EVIDENCE_SYNTHESIS_ARTIFACT_TYPES:
        assert (packet_dir / f"{artifact_type}.json").exists()

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert manifest["source_chain_complete"] is True
    assert manifest["synthesis_finalization_eligible"] is False
    assert manifest["no_phase_shift_claim"] is True

    history = read_payload(packet_dir / "repair_history_table.json")
    packet_kinds = {row["packet_kind"] for row in history["repair_events"]}
    assert "autonomous_revision" in packet_kinds
    assert "ablation_informed_revision" in packet_kinds
    assert "executed_ablation" in packet_kinds

    causal_summary = read_payload(packet_dir / "causal_status_summary.json")
    finding_statuses = {finding["status"] for finding in causal_summary["findings"]}
    assert "weak" in finding_statuses
    assert "useful_but_insufficient" in finding_statuses
    assert "exhausted_for_now" in finding_statuses
    assert "failed" in finding_statuses

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    assert best["selected_best_candidate"]["selected_candidate_is_final"] is False
    assert best["selected_best_candidate"]["selected_candidate_requires_further_testing"] is True
    assert best["selected_best_candidate"]["packet_id"] != _pivot_revision["packet_id"]

    failed = read_payload(packet_dir / "failed_or_rejected_repairs.json")
    assert failed["failed_or_rejected_count"] >= 1
    exhausted = read_payload(packet_dir / "exhausted_handle_report.json")
    statuses = {handle["status"] for handle in exhausted["handles"]}
    assert "exhausted_for_now" in statuses
    assert "failed" in statuses
    rival = read_payload(packet_dir / "rival_pressure_summary.json")
    assert rival["strongest_rival_still_blocks"] is True
    assert rival["strongest_rival_comparison_passed"] is False
    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    assert blockers["macro_recomposition_recommended"] is True
    laws = read_payload(packet_dir / "local_law_case_notes.json")
    assert laws["case_note_count"] >= 5
    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "stop_local_patching_and_synthesize_macro_recomposition_brief"
    )
    assert decision["not_candidate_artifact"] is True
    macro = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert macro["brief_type"] == "future_creative_instruction_not_artifact"
    assert macro["not_candidate_artifact"] is True
    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True
    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["counts"]["model_calls"] == 0
    assert packet["strategic_decision"] == decision["recommendation"]

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_consumes_macro_timeline_v2(tmp_path):
    config, failed_ablation, pivot_revision, macro_payload, macro_ablation = (
        build_fake_macro_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)
        run_id = get_latest_run(connection).id

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert manifest["normalized_evidence_timeline_version"] == "v2"
    assert "bounded_macro_recomposition" in manifest["source_packet_kinds"]
    assert "executed_ablation" in manifest["proof_packet_kinds"]
    assert macro_payload["packet_id"] in manifest["bounded_macro_packets_consumed"]
    assert macro_ablation["packet_id"] in manifest["bounded_macro_ablation_packets_consumed"]
    macro_ablation_summary = [
        source
        for source in manifest["source_packets"]
        if source["packet_id"] == macro_ablation["packet_id"]
    ][0]
    assert macro_ablation_summary["subject_kind"] == REVISION_PACKET_KIND_BOUNDED_MACRO

    history = read_payload(packet_dir / "repair_history_table.json")
    macro_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "bounded_macro_recomposition"
    ]
    assert macro_rows
    assert macro_rows[-1]["packet_id"] == macro_payload["packet_id"]
    assert macro_rows[-1]["macro_target_coverage_passed"] is True
    assert macro_rows[-1]["macro_materiality_passed"] is True
    proof_rows = [
        row
        for row in history["repair_events"]
        if row.get("subject_kind") == REVISION_PACKET_KIND_BOUNDED_MACRO
    ]
    assert proof_rows
    assert proof_rows[-1]["source_revision_packet_id"] == macro_payload["packet_id"]
    assert proof_rows[-1]["causal_status"] == "useful_but_insufficient"
    assert proof_rows[-1]["repair_has_causal_support"] is True
    assert proof_rows[-1]["reverting_patch_weakens_candidate"] is True
    assert proof_rows[-1]["reduced_overexplanation"] is True
    assert proof_rows[-1]["damaged_local_embodiment"] is False
    assert proof_rows[-1]["strongest_rival_still_beats_candidate"] is True
    assert proof_rows[-1]["flattened_summary_macro_variant_cautionary"] is True
    assert proof_rows[-1]["non_evidence_control_variant_ids"]

    causal = read_payload(packet_dir / "causal_status_summary.json")
    findings = {finding["finding_id"]: finding for finding in causal["findings"]}
    assert findings["bounded_macro_recomposition_packet_0008"][
        "status"
    ] == "useful_but_insufficient"
    assert findings["flattened_summary_macro_variant_cautionary"][
        "status"
    ] == "rejected_or_cautionary"
    assert causal["macro_useful_but_insufficient_detected"] is True

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_kind"] == "bounded_macro_recomposition"
    assert selected["packet_id"] == macro_payload["packet_id"]
    assert selected["packet_dir"] == macro_payload["packet_dir"]
    assert selected["selected_candidate_is_final"] is False
    assert selected["strongest_rival_still_blocks"] is True
    assert selected["packet_dir"] != pivot_revision["packet_dir"]
    assert selected["packet_dir"] != failed_ablation["packet_dir"]

    failed = read_payload(packet_dir / "failed_or_rejected_repairs.json")
    rejected_handles = {
        repair["selected_handle"] for repair in failed["failed_or_rejected_repairs"]
    }
    assert "flattened_summary_macro_variant" in rejected_handles
    assert "no_op_mismatch_or_planned_only_control" in rejected_handles

    exhausted = read_payload(packet_dir / "exhausted_handle_report.json")
    handles = {handle["handle"]: handle for handle in exhausted["handles"]}
    assert handles["local_patch_regime"]["status"] == "plateaued"
    assert handles["bounded_macro_recomposition"][
        "status"
    ] == "active_useful_but_insufficient"
    assert handles["middle_and_return_movement"]["status"] == "active_macro_target"
    assert handles["proof_no_outside_answer_region"][
        "status"
    ] == "possible_next_sub_handle"

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    blocker_ids = {blocker["blocker_id"] for blocker in blockers["residual_blockers"]}
    assert "proof_no_outside_answer_refinement" in blocker_ids
    assert "reader_state_opening_return_transformation_unproven" in blocker_ids
    assert blockers["macro_recomposition_recommended"] is False
    assert blockers["internal_reader_state_evaluation_recommended"] is True
    assert blockers["generic_more_compression_recommended"] is False

    laws = read_payload(packet_dir / "local_law_case_notes.json")
    law_ids = {law["law_id"] for law in laws["case_notes"]}
    assert "macro_recomposition_can_reduce_overexplanation_without_embodiment_loss" in law_ids
    assert "macro_revert_weakens_candidate" in law_ids
    assert "macro_improvement_is_not_rival_victory" in law_ids

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "preserve_macro_candidate_and_run_internal_reader_state_evaluation"
    )
    assert decision["do_not_continue_local_patching_immediately"] is True
    assert decision["do_not_immediately_run_second_macro_recomposition"] is True
    assert decision["internal_reader_state_evaluation_recommended"] is True

    brief = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert brief["brief_type"] == "macro_evidence_review_next_step_brief_not_artifact"
    assert brief["run_internal_reader_state_evaluation_before_further_recomposition"] is True
    assert brief["not_candidate_artifact"] is True

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    assert gate_results["macro_evidence_consumed"]["passed"] is True
    assert gate_results["macro_candidate_selected_if_supported"]["passed"] is True
    assert gate_results["macro_ablation_causal_status_recorded"]["passed"] is True
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["best_current_candidate"]["packet_id"] == macro_payload["packet_id"]
    assert packet["counts"]["model_calls"] == 0
    assert macro_ablation["packet_id"] in packet["bounded_macro_ablation_packets_consumed"]

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_adjudicates_reader_state_evidence(tmp_path):
    config, _failed_ablation, _pivot_revision, macro_payload, macro_ablation = (
        build_fake_macro_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id

    macro_synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert macro_synthesis.exit_code == 0

    def _reader_state_client_factory(model: str) -> FakeInternalReaderLabModelClient:
        return FakeInternalReaderLabModelClient(provider="openai", model=model)

    reader_state = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=macro_synthesis.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-reader-state-model",
        client_factory=_reader_state_client_factory,
    )
    assert reader_state.exit_code == 0
    assert reader_state.payload["accepted"] is True
    assert reader_state.payload["selected_candidate_packet_id"] == macro_payload["packet_id"]
    assert reader_state.payload["counts"]["model_calls"] == 5

    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["reader_state_evidence_consumed"] is True
    assert result.payload["reader_state_reread_transformation_strength"] == "partial"
    assert result.payload["reader_state_tension_count"] >= 1
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert "internal_reader_state_evaluation" in manifest["source_packet_kinds"]
    assert reader_state.payload["packet_id"] in manifest[
        "reader_state_evaluation_packets_consumed"
    ]
    assert manifest["live_reader_state_evidence_exists"] is True

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    source_chain = {
        (source["packet_kind"], source["packet_id"]) for source in packet["source_chain"]
    }
    assert ("internal_reader_state_evaluation", reader_state.payload["packet_id"]) in source_chain
    assert ("bounded_macro_recomposition", macro_payload["packet_id"]) in source_chain
    assert ("executed_ablation", macro_ablation["packet_id"]) in source_chain
    assert reader_state.payload["packet_id"] in packet[
        "reader_state_evaluation_packets_consumed"
    ]

    history = read_payload(packet_dir / "repair_history_table.json")
    reader_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "internal_reader_state_evaluation"
    ]
    assert reader_rows
    reader_row = reader_rows[-1]
    assert reader_row["selected_candidate_packet_id"] == macro_payload["packet_id"]
    assert reader_row["selected_candidate_kind"] == "bounded_macro_recomposition"
    assert reader_row["model_calls"] == 5
    assert reader_row["fixture_only"] is False
    assert reader_row["first_pass_trace_exists"] is True
    assert reader_row["reread_trace_exists"] is True
    assert reader_row["reader_delta_report_exists"] is True
    assert reader_row["hostile_reader_report_exists"] is True
    assert reader_row["forensic_grounding_report_exists"] is True
    assert reader_row["rival_reader_state_comparison_exists"] is True
    assert reader_row["strongest_rival_still_blocks"] is True
    assert reader_row["finalization_eligible"] is False
    assert reader_row["no_phase_shift_claim"] is True

    adjudication = read_payload(packet_dir / "reader_state_evidence_adjudication.json")
    assert adjudication["reader_state_evidence_present"] is True
    assert adjudication["packet_id"] == reader_state.payload["packet_id"]
    assert adjudication["selected_candidate_packet_id"] == macro_payload["packet_id"]
    assert adjudication["reread_transformation_strength"] == "partial"
    assert adjudication["opening_field_necessity_after_reread"] == "increased"
    assert adjudication["proof_no_outside_answer_carry_status"] == "partial_or_unresolved"
    assert adjudication["strongest_rival_status"] == "still_blocks"
    assert adjudication["finalization_eligible"] is False
    assert adjudication["no_phase_shift_claim"] is True

    tensions = read_payload(packet_dir / "reader_state_tension_report.json")
    tension_ids = {tension["tension_id"] for tension in tensions["tensions"]}
    assert "gap_narrowed_but_rival_still_blocks" in tension_ids
    assert "proof_carried_but_still_visible" in tension_ids
    assert "partial_delta_vs_hostile_risk" in tension_ids
    assert tensions["tension_count"] >= 3

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == macro_payload["packet_id"]
    assert selected["reader_state_evaluated"] is True
    assert selected["reader_state_packet_id"] == reader_state.payload["packet_id"]
    assert selected["reader_state_reread_transformation_strength"] == "partial"
    assert selected["reader_state_transformation_is_partial_not_decisive"] is True
    assert selected["selected_candidate_is_final"] is False
    assert selected["strongest_rival_still_blocks"] is True

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    blocker_ids = {blocker["blocker_id"] for blocker in blockers["residual_blockers"]}
    assert "proof_no_outside_answer_refinement" in blocker_ids
    assert "reader_state_opening_return_transformation_still_partial" in blocker_ids
    assert "thesis_visible_proof_language" in blocker_ids
    assert "first_read_vividness_gap" in blocker_ids
    assert blockers["internal_reader_state_evaluation_recommended"] is False
    assert blockers["reader_state_informed_macro_2_recomposition_recommended"] is True
    assert blockers["strongest_rival_still_blocks"] is True

    laws = read_payload(packet_dir / "local_law_case_notes.json")
    law_ids = {law["law_id"] for law in laws["case_notes"]}
    assert "macro_recomposition_can_create_partial_reread_transformation" in law_ids
    assert "reader_state_evidence_requires_cross_worker_adjudication" in law_ids
    assert "rival_pressure_remains_after_macro_reader_state_gain" in law_ids

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "preserve_macro_candidate_and_prepare_reader_state_informed_macro_2_brief"
    )
    assert decision["next_recommended_action"] == (
        "prepare_reader_state_informed_macro_2_recomposition_brief"
    )
    assert decision["do_not_return_to_blind_local_patching"] is True
    assert decision["internal_reader_state_evaluation_recommended"] is False
    assert decision["reader_state_informed_macro_2_recomposition_recommended"] is True
    assert decision["do_not_build_loop_controller_yet"] is True
    assert decision["do_not_add_taste_memory_yet"] is True
    assert decision["no_phase_shift_claim"] is True

    brief = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert brief["brief_type"] == (
        "reader_state_informed_macro_2_recomposition_brief_not_artifact"
    )
    assert brief["current_best_base_candidate_packet_id"] == macro_payload["packet_id"]
    assert brief["reader_state_evidence_packet_id"] == reader_state.payload["packet_id"]
    assert brief["reader_state_evidence_consumed"] is True
    assert brief["run_internal_reader_state_evaluation_before_further_recomposition"] is False
    assert "do not return to blind local patching" in brief["forbidden_changes"]
    assert "do not declare victory over the rival" in brief["forbidden_changes"]
    assert brief["not_candidate_artifact"] is True

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    assert gate_results["reader_state_evidence_consumed"]["passed"] is True
    assert gate_results["reader_state_adjudication_exists"]["passed"] is True
    assert gate_results["reader_state_transformation_classified"]["passed"] is True
    assert gate_results["reader_state_tensions_recorded"]["passed"] is True
    assert gate["reader_state_evidence_consumed"] is True
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_supersedes_with_live_macro2_proof(tmp_path):
    chain = build_live_macro2_candidate_with_optional_proof(tmp_path, proof_mode="useful")
    config = chain["config"]
    run_id = chain["run_id"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert chain["macro2"]["packet_id"] in manifest["macro2_candidate_packets_consumed"]
    assert chain["macro2_proof"]["packet_id"] in manifest["macro2_ablation_packets_consumed"]

    history = read_payload(packet_dir / "repair_history_table.json")
    macro2_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "bounded_macro_recomposition"
        and row["packet_id"] == chain["macro2"]["packet_id"]
    ]
    assert macro2_rows
    assert macro2_rows[0]["target_scope"] == READER_STATE_MACRO_2_TARGET_SCOPE
    assert macro2_rows[0]["model_backed"] is True
    assert macro2_rows[0]["fixture_only"] is False
    proof_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "executed_ablation"
        and row["packet_id"] == chain["macro2_proof"]["packet_id"]
    ]
    assert proof_rows
    assert proof_rows[0]["source_revision_packet_id"] == chain["macro2"]["packet_id"]
    assert proof_rows[0]["causal_status"] == "useful_but_insufficient"
    assert proof_rows[0]["actual_executed_ablation_evidence_exists"] is True
    assert proof_rows[0]["countable_evidence_variant_count"] > 0
    assert proof_rows[0]["model_backed"] is True
    assert proof_rows[0]["fixture_only"] is False

    causal = read_payload(packet_dir / "causal_status_summary.json")
    assert chain["macro2"]["packet_id"] in causal["macro2_candidate_packet_ids"]
    assert chain["macro2_proof"]["packet_id"] in causal["macro2_proof_packet_ids"]
    findings = {finding["finding_id"]: finding for finding in causal["findings"]}
    assert findings["reader_state_informed_macro_2_candidate_proof"][
        "status"
    ] == "useful_but_insufficient"

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["macro2"]["packet_id"]
    assert selected["packet_kind"] == "bounded_macro_recomposition"
    assert selected["base_candidate_packet_id"] == chain["macro_payload"]["packet_id"]
    assert selected["proof_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert selected["candidate_proof_linked"] is True
    assert selected["supersession_eligible"] is True
    assert selected["selected_by_candidate_proof_supersession"] is True
    assert best["candidate_supersession_evaluated"] is True
    assert best["candidate_proof_supersession_applied"] is True
    assert best["best_current_candidate_updated_from_macro2_proof"] is True
    pair = [
        item
        for item in best["candidate_proof_pairs"]
        if item["candidate_packet_id"] == chain["macro2"]["packet_id"]
        and item["candidate_packet_kind"] == "bounded_macro_recomposition"
    ][0]
    assert pair["proof_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert pair["supersession_eligible"] is True

    adjudication = read_payload(packet_dir / "reader_state_evidence_adjudication.json")
    assert adjudication["reader_state_evidence_present"] is False
    assert adjudication["selected_candidate_packet_id"] == chain["macro2"]["packet_id"]

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    assert blockers["internal_reader_state_evaluation_recommended"] is True
    assert blockers["reader_state_informed_macro_2_recomposition_recommended"] is False
    assert blockers["strongest_rival_still_blocks"] is True

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "preserve_macro2_candidate_and_run_reader_state_evaluation"
    )
    assert decision["next_recommended_action"] == (
        "run_internal_reader_state_evaluation_on_macro2_candidate"
    )
    assert decision["internal_reader_state_evaluation_recommended"] is True

    brief = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert brief["brief_type"] == "macro2_evidence_review_next_step_brief_not_artifact"
    assert brief["run_internal_reader_state_evaluation_before_further_recomposition"] is True
    assert brief["run_another_macro_recomposition_now"] is False

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    assert gate_results["macro2_candidate_consumed"]["passed"] is True
    assert gate_results["macro2_ablation_consumed"]["passed"] is True
    assert gate_results["macro2_candidate_proof_linked"]["passed"] is True
    assert gate_results["candidate_supersession_evaluated"]["passed"] is True
    assert gate_results["best_current_candidate_updated_from_macro2_proof"]["passed"] is True
    assert gate_results["strongest_rival_pressure_preserved"]["passed"] is True
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["best_current_candidate"]["packet_id"] == chain["macro2"]["packet_id"]
    assert packet["next_recommended_action"] == (
        "run_internal_reader_state_evaluation_on_macro2_candidate"
    )
    assert packet["best_current_candidate_updated_from_macro2_proof"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_consumes_macro2_reader_state_by_candidate_hash(
    tmp_path,
):
    chain = build_live_macro2_candidate_with_reader_state(
        tmp_path,
        strip_reader_identity_to_hash_only=True,
    )
    config = chain["config"]
    run_id = chain["run_id"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert chain["macro2"]["packet_id"] in manifest["macro2_candidate_packets_consumed"]
    assert chain["macro2_proof"]["packet_id"] in manifest["macro2_ablation_packets_consumed"]
    assert chain["macro2_reader_state"]["packet_id"] in manifest[
        "macro2_reader_state_evaluation_packets_consumed"
    ]
    assert chain["macro2_reader_state"]["packet_id"] in manifest[
        "reader_state_evaluation_packets_consumed"
    ]

    history = read_payload(packet_dir / "repair_history_table.json")
    reader_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "internal_reader_state_evaluation"
        and row["packet_id"] == chain["macro2_reader_state"]["packet_id"]
    ]
    assert reader_rows
    reader_row = reader_rows[0]
    assert reader_row["selected_candidate_packet_id"] == ""
    assert reader_row["selected_candidate_text_sha256"] == chain[
        "macro2_candidate_text_sha256"
    ]
    assert reader_row["fixture_only"] is False
    assert reader_row["model_calls"] == 5
    assert reader_row["first_pass_trace_exists"] is True
    assert reader_row["reread_trace_exists"] is True
    assert reader_row["reader_delta_report_exists"] is True
    assert reader_row["hostile_reader_report_exists"] is True
    assert reader_row["forensic_grounding_report_exists"] is True
    assert reader_row["rival_reader_state_comparison_exists"] is True
    assert reader_row["post_reread_reader_state"] == "partial_opening_return_transformation"
    assert reader_row["reread_transformation_strength"] == "partial"
    assert reader_row["strongest_rival_still_blocks"] is True
    assert reader_row["finalization_eligible"] is False
    assert reader_row["no_phase_shift_claim"] is True

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["macro2"]["packet_id"]
    assert selected["packet_kind"] == "bounded_macro_recomposition"
    assert selected["reader_state_evaluated"] is True
    assert selected["reader_state_packet_id"] == chain["macro2_reader_state"]["packet_id"]
    assert selected["reader_state_fixture_only"] is False
    assert selected["reader_state_model_calls"] == 5
    assert selected["reader_state_post_reread_state"] == (
        "partial_opening_return_transformation"
    )
    assert selected["reader_state_reread_transformation_strength"] == "partial"
    assert selected["reader_state_transformation_is_partial_not_decisive"] is True
    assert selected["reader_state_strongest_rival_still_blocks"] is True
    assert selected["selected_candidate_is_final"] is False

    adjudication = read_payload(packet_dir / "reader_state_evidence_adjudication.json")
    assert adjudication["reader_state_evidence_present"] is True
    assert adjudication["packet_id"] == chain["macro2_reader_state"]["packet_id"]
    assert adjudication["selected_candidate_text_sha256"] == chain[
        "macro2_candidate_text_sha256"
    ]
    assert adjudication["reread_transformation_strength"] == "partial"
    assert "partial" in adjudication["opening_return_transformation_status"]
    assert adjudication["opening_field_necessity_after_reread"] == "increased"
    assert adjudication["local_field_causal_necessity"] == "increased"
    assert adjudication["proof_no_outside_answer_carry_status"] == "partial_or_unresolved"
    assert adjudication["final_return_echo_status"] == "improved_but_unproven"
    assert adjudication["first_read_object_event_pressure_status"] == (
        "still_weaker_than_rival"
    )
    assert adjudication["hostile_risk_status"] == "active"
    assert adjudication["strongest_rival_status"] == "still_blocks"
    assert adjudication["not_human_data"] is True
    assert adjudication["no_phase_shift_claim"] is True

    tensions = read_payload(packet_dir / "reader_state_tension_report.json")
    tension_ids = {tension["tension_id"] for tension in tensions["tensions"]}
    assert "reread_transformation_partial_not_decisive" in tension_ids
    assert "structural_return_gain_vs_first_read_object_event_gap" in tension_ids
    assert "proof_carried_but_still_visible" in tension_ids
    assert "gap_narrowed_but_rival_still_blocks" in tension_ids
    assert "internal_reader_evidence_not_human_data" in tension_ids

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    blocker_ids = {blocker["blocker_id"] for blocker in blockers["residual_blockers"]}
    assert "first_read_object_event_pressure_gap" in blocker_ids
    assert "strongest_rival_still_winning" in blocker_ids
    assert "proof_no_outside_answer_carry_still_partial" in blocker_ids
    assert "final_return_echo_reread_strength_still_partial" in blocker_ids
    assert "thesis_visible_scaffold_risk" in blocker_ids
    assert "local_embodiment_vs_conceptual_compression_balance" in blocker_ids
    assert "reader_state_opening_return_transformation_still_partial" in blocker_ids
    assert blockers["macro2_reader_state_evidence_consumed"] is True
    assert blockers["internal_reader_state_evaluation_recommended"] is False
    assert blockers["reader_state_informed_macro_2_recomposition_recommended"] is False
    assert blockers["next_target_strategy_recommended"] is True
    assert blockers["first_read_object_event_pressure_strategy_recommended"] is True
    assert blockers["strongest_rival_still_blocks"] is True

    laws = read_payload(packet_dir / "local_law_case_notes.json")
    law_ids = {law["law_id"] for law in laws["case_notes"]}
    assert "macro2_live_support_can_remain_partial" in law_ids
    assert "macro2_structural_return_can_improve_while_first_read_lags" in law_ids
    assert "macro2_object_field_can_gain_causality_without_clearing_scaffold_risk" in law_ids
    assert "macro2_proof_no_answer_scene_bound_but_partial" in law_ids
    assert "reader_state_evidence_sets_next_target" in law_ids

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "preserve_macro2_candidate_and_prepare_next_reader_state_target_strategy"
    )
    assert decision["next_recommended_action"] == (
        "review_macro2_reader_state_synthesis_before_new_candidate"
    )
    assert decision["next_recommended_action"] != (
        "run_internal_reader_state_evaluation_on_macro2_candidate"
    )
    assert decision["internal_reader_state_evaluation_recommended"] is False
    assert decision["next_reader_state_target_strategy_recommended"] is True
    assert decision["first_read_object_event_pressure_strategy_recommended"] is True
    assert decision["reader_state_informed_macro_2_recomposition_recommended"] is False
    assert decision["no_phase_shift_claim"] is True

    brief = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert brief["brief_type"] == "macro2_reader_state_next_strategy_brief_not_artifact"
    assert brief["current_best_base_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert brief["linked_executed_ablation_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert brief["reader_state_evidence_packet_id"] == chain["macro2_reader_state"][
        "packet_id"
    ]
    assert brief["operator_review_required_before_new_creative_action"] is True
    assert brief["run_another_macro_recomposition_now"] is False
    assert brief["not_candidate_artifact"] is True
    assert brief["no_phase_shift_claim"] is True

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    assert gate_results["macro2_reader_state_evidence_consumed"]["passed"] is True
    assert gate_results["macro2_reader_state_eval_linked"]["passed"] is True
    assert gate_results["reader_state_transformation_classified"]["passed"] is True
    assert gate_results["best_candidate_reader_state_status_current"]["passed"] is True
    assert gate_results["strongest_rival_pressure_preserved"]["passed"] is True
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["best_current_candidate"]["packet_id"] == chain["macro2"]["packet_id"]
    assert packet["best_current_candidate"]["reader_state_evaluated"] is True
    assert chain["macro2_reader_state"]["packet_id"] in packet[
        "macro2_reader_state_evaluation_packets_consumed"
    ]
    assert packet["next_recommended_action"] == (
        "review_macro2_reader_state_synthesis_before_new_candidate"
    )
    assert packet["macro2_reader_state_evidence_consumed"] is True
    assert packet["macro2_reader_state_eval_linked"] is True
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_next_target_strategy_accepts_reader_state_synthesis_and_operationalizes_target(
    tmp_path,
):
    chain = build_next_target_strategy_ready_chain(tmp_path)
    config = chain["config"]
    synthesis_packet = Path(str(chain["strategy_synthesis"]["packet_dir"]))
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_next_target_strategy(config, synthesis_packet=synthesis_packet)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["current_best_candidate_packet_id"] == chain["macro2"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["macro2_reader_state"][
        "packet_id"
    ]
    assert result.payload["target_name"] == "first_read_object_event_pressure_gap"
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["current_best_candidate"]["packet_id"] == chain["macro2"][
        "packet_id"
    ]
    assert result.payload["primary_next_target"] == "first_read_object_event_pressure_gap"
    packet_dir = Path(str(result.payload["packet_dir"]))
    assert packet_dir.parent.name == "next_target_strategy"
    assert {artifact.type for artifact in result.artifacts} == set(
        NEXT_TARGET_STRATEGY_ARTIFACT_TYPES
    )

    for artifact_type in NEXT_TARGET_STRATEGY_ARTIFACT_TYPES:
        envelope = json.loads(
            (packet_dir / f"{artifact_type}.json").read_text(encoding="utf-8")
        )
        assert envelope["artifact_type"] == artifact_type
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is None

    subject = read_payload(packet_dir / "next_target_strategy_subject_manifest.json")
    assert subject["source_synthesis_packet_id"] == chain["strategy_synthesis"]["packet_id"]
    assert subject["current_best_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert subject["proof_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert subject["reader_state_eval_packet_id"] == chain["macro2_reader_state"][
        "packet_id"
    ]
    assert subject["strongest_rival_still_blocks"] is True
    assert subject["candidate_generated"] is False
    assert subject["no_phase_shift_claim"] is True

    source = read_payload(packet_dir / "source_evidence_summary.json")
    assert source["current_best_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert source["proof_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert source["reader_state_packet_id"] == chain["macro2_reader_state"]["packet_id"]
    assert source["not_human_data"] is True
    assert source["candidate_final"] is False

    best = read_payload(packet_dir / "current_best_candidate_summary.json")
    assert best["current_best_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert best["superseded_prior_best_packet_id"] == chain["macro_payload"][
        "packet_id"
    ]
    assert best["candidate_generated"] is False
    assert any(
        "reader-state evidence" in reason
        for reason in best["why_current_best_superseded_prior_best"]
    )

    blockers = read_payload(packet_dir / "reader_state_blocker_summary.json")
    assert blockers["top_blocker_id"] == "first_read_object_event_pressure_gap"
    assert blockers["ranked_blockers"][0]["blocker_id"] == (
        "first_read_object_event_pressure_gap"
    )
    assert "strongest_rival_still_winning" in blockers["active_blocker_ids"]
    assert blockers["prior_proof_no_answer_handle_status"] == "improved_but_not_solved"
    assert blockers["do_not_continue_proof_no_answer_compression_by_inertia"] is True
    assert blockers["next_target_should_follow_evidence_not_previous_momentum"] is True

    rival = read_payload(packet_dir / "strongest_rival_pressure_delta.json")
    assert rival["strongest_rival_still_blocks"] is True
    assert "first-read vividness" in rival["where_rival_still_wins"]
    assert "lived object-event pressure" in rival["where_rival_still_wins"]
    assert rival["strongest_rival_comparison_passed"] is False

    protected = read_payload(packet_dir / "protected_effects_and_forbidden_changes.json")
    assert any("partial reread transformation" in item for item in protected["protected_effects"])
    assert "writing a new candidate in this command" in protected["forbidden_changes"]
    assert "declaring phase shift" in protected["forbidden_changes"]

    target_map = read_payload(packet_dir / "object_event_pressure_target_map.json")
    assert target_map["target_name"] == "first_read_object_event_pressure_gap"
    assert "an object changes because another object or action pressures it" in target_map[
        "what_counts_as_object_event_pressure"
    ]
    assert "decorative furniture added to seem vivid" in target_map[
        "what_counts_as_fake_detail_only_vividness"
    ]
    assert "bounded early/middle scene-pressure recomposition" in target_map[
        "possible_intervention_types"
    ]
    assert target_map["generation_chosen"] is False

    region_map = read_payload(packet_dir / "candidate_region_pressure_map.json")
    region_ids = {region["region_id"] for region in region_map["regions"]}
    assert "opening_table_dust_spoon_saucer_ring_field" in region_ids
    assert "middle_recurrence_ordinary_trace_logic" in region_ids
    assert "proof_no_outside_answer_region" in region_ids
    assert "final_return_opening_transformation_region" in region_ids
    assert region_map["do_not_assume_final_return_is_next_region"] is True

    strategy = read_payload(packet_dir / "next_intervention_strategy.json")
    assert strategy["recommended_action"] == "request_operator_review_before_generation"
    assert strategy["secondary_recommendation"] == (
        "prepare_bounded_object_event_pressure_recomposition"
    )
    assert strategy["top_ranked_blocker"] == "first_read_object_event_pressure_gap"
    assert strategy["generation_allowed_by_this_packet"] is False
    assert strategy["operator_review_required_before_generation"] is True

    plan = read_payload(packet_dir / "ablation_and_reader_eval_plan.json")
    assert any(
        chain["macro2"]["packet_id"] in item
        for item in plan["if_future_candidate_is_generated"]
    )
    assert "revert_object_event_pressure_intervention" in plan["required_future_controls"]
    assert "strongest_rival_comparison" in plan["required_future_controls"]
    assert "first-read vividness" in plan["reader_eval_focus"]
    assert plan["next_candidate_generated"] is False

    gate = read_payload(packet_dir / "next_target_strategy_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "source_synthesis_consumed",
        "current_best_candidate_identified",
        "proof_packet_linked",
        "reader_state_packet_linked",
        "residual_blockers_ranked",
        "strongest_rival_pressure_preserved",
        "next_target_strategy_created",
        "no_candidate_generated",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "next_candidate_generated",
        "ablation_completed_for_next_candidate",
        "reader_state_eval_completed_for_next_candidate",
        "no_unresolved_internal_blockers",
        "internal_operator_approval",
        "finalization_eligible",
        "phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["not_human_validated"] is True
    assert gate["strongest_rival_still_blocks"] is True

    packet = read_payload(packet_dir / "next_target_strategy_packet.json")
    assert packet["current_best_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert packet["current_best_candidate"]["packet_id"] == chain["macro2"]["packet_id"]
    assert packet["proof_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert packet["reader_state_packet_id"] == chain["macro2_reader_state"]["packet_id"]
    assert packet["primary_next_target"] == "first_read_object_event_pressure_gap"
    assert packet["counts"]["model_calls"] == 0
    assert packet["counts"]["produced_artifacts"] == len(NEXT_TARGET_STRATEGY_ARTIFACT_TYPES)
    assert packet["counts"]["required_artifacts"] == len(NEXT_TARGET_STRATEGY_ARTIFACT_TYPES)
    assert packet["counts"]["candidate_artifacts_created"] == 0
    assert packet["counts"]["strategy_artifacts"] == len(NEXT_TARGET_STRATEGY_ARTIFACT_TYPES)
    assert packet["candidate_generated"] is False
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_next_target_strategy_refuses_missing_best_current_candidate(tmp_path):
    chain = build_next_target_strategy_ready_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_next_target_synthesis_missing_best"
    shutil.copytree(Path(str(chain["strategy_synthesis"]["packet_dir"])), invalid_packet)

    def _remove_best(payload):
        payload.pop("selected_best_candidate", None)

    rewrite_payload(invalid_packet / "best_current_candidate_selection.json", _remove_best)

    result = run_next_target_strategy(chain["config"], synthesis_packet=invalid_packet)

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "missing best_current_candidate" in result.payload["message"]
    assert result.payload["model_calls"] == 0


def test_next_target_strategy_refuses_without_reader_state_evidence(tmp_path):
    chain = build_live_macro2_candidate_with_optional_proof(tmp_path, proof_mode="useful")
    synthesis = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])
    assert synthesis.exit_code == 0
    assert synthesis.payload["best_current_candidate"]["packet_id"] == chain["macro2"][
        "packet_id"
    ]
    assert synthesis.payload["best_current_candidate"]["reader_state_evaluated"] is False

    result = run_next_target_strategy(
        chain["config"],
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "no reader-state evaluation" in result.payload["message"]
    assert result.payload["model_calls"] == 0


def test_next_target_strategy_accepts_authorization_packet_and_blocks_repeated_target(
    tmp_path,
):
    chain = build_authorized_next_target_strategy_chain(tmp_path)
    config = chain["config"]
    authorization_packet = Path(str(chain["cycle_authorization"]["packet_dir"]))
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_next_target_strategy(
        config,
        authorization_packet=authorization_packet,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert result.payload["source_synthesis_packet_id"] == chain["authorized_synthesis"][
        "packet_id"
    ]
    assert result.payload["authorization_packet_id"] == chain["cycle_authorization"][
        "packet_id"
    ]
    assert result.payload["loop_review_packet_id"] == chain["loop_review"]["packet_id"]
    assert result.payload["completed_cycles"] == 2
    assert result.payload["next_strategy_authorized"] is True
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["model_calls"] == 0
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["repeated_target_detected"] is True
    assert result.payload["repeated_target_id"] == "first_read_object_event_pressure_gap"
    assert result.payload["same_broad_target_allowed"] is False
    assert result.payload["primary_next_target"] == (
        "next_residual_target_requires_operator_choice"
    )
    assert result.payload["primary_next_subtarget"] == "operator_choice_required"
    assert result.payload["next_recommended_action"] == (
        "review_narrow_residual_target_options_before_generation"
    )
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True

    packet_dir = Path(str(result.payload["packet_dir"]))
    assert {artifact.type for artifact in result.artifacts} == set(
        NEXT_TARGET_STRATEGY_ARTIFACT_TYPES
    )

    subject = read_payload(packet_dir / "next_target_strategy_subject_manifest.json")
    assert subject["input_mode"] == "authorization"
    assert subject["authorization_packet_id"] == chain["cycle_authorization"]["packet_id"]
    assert subject["loop_review_packet_id"] == chain["loop_review"]["packet_id"]
    assert subject["source_synthesis_packet_id"] == chain["authorized_synthesis"][
        "packet_id"
    ]
    assert subject["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert subject["next_strategy_authorized"] is True
    assert subject["next_generation_authorized"] is False
    assert subject["repeated_target_report"]["repeated_target_detected"] is True
    assert subject["repeated_target_report"]["same_broad_target_allowed"] is False

    residual = read_payload(packet_dir / "residual_target_option_map.json")
    option_ids = {option["option_id"] for option in residual["specific_residual_options"]}
    assert residual["primary_next_target"] == (
        "next_residual_target_requires_operator_choice"
    )
    assert residual["primary_next_subtarget"] == "operator_choice_required"
    assert residual["same_broad_target_allowed"] is False
    assert residual["repeated_broad_target_authorized"] is False
    assert "tactile_inevitability_gap" in option_ids
    assert "object_motion_causality_specificity" in option_ids
    assert "rival_level_first_read_vividness" in option_ids
    assert "hostile_scaffold_visibility" in option_ids
    assert "proof_no_answer_residue" in option_ids
    assert "ending_explains_return_risk" in option_ids
    assert "local_busyness_decorative_detail_risk" in option_ids

    target_map = read_payload(packet_dir / "object_event_pressure_target_map.json")
    assert target_map["target_name"] == "next_residual_target_requires_operator_choice"
    assert target_map["broad_target_class"] == "first_read_object_event_pressure_gap"
    assert target_map["repeated_target_detected"] is True
    assert target_map["same_broad_target_allowed"] is False

    strategy = read_payload(packet_dir / "next_intervention_strategy.json")
    assert strategy["recommended_action"] == (
        "review_narrow_residual_target_options_before_generation"
    )
    assert strategy["primary_next_target"] == (
        "next_residual_target_requires_operator_choice"
    )
    assert strategy["same_broad_target_allowed"] is False
    assert strategy["generation_allowed_by_this_packet"] is False

    gate = read_payload(packet_dir / "next_target_strategy_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "authorization_packet_consumed",
        "loop_review_packet_consumed",
        "source_synthesis_consumed",
        "current_best_candidate_identified",
        "proof_packet_linked",
        "reader_state_packet_linked",
        "repeated_target_guard_checked",
        "no_candidate_generated",
        "no_openai_calls",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "next_candidate_generation_authorized",
        "repeated_broad_target_authorized",
        "no_unresolved_internal_blockers",
        "internal_operator_approval",
        "finalization_eligible",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["strongest_rival_still_blocks"] is True

    packet = read_payload(packet_dir / "next_target_strategy_packet.json")
    assert packet["current_best_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert packet["authorization_packet_id"] == chain["cycle_authorization"]["packet_id"]
    assert packet["loop_review_packet_id"] == chain["loop_review"]["packet_id"]
    assert packet["primary_next_target"] == (
        "next_residual_target_requires_operator_choice"
    )
    assert packet["primary_next_subtarget"] == "operator_choice_required"
    assert packet["repeated_target_detected"] is True
    assert packet["same_broad_target_allowed"] is False
    assert packet["candidate_generated"] is False
    assert packet["counts"]["model_calls"] == 0

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_next_target_strategy_synthesis_only_refuses_after_authorization(tmp_path):
    chain = build_authorized_next_target_strategy_chain(tmp_path)

    result = run_next_target_strategy(
        chain["config"],
        synthesis_packet=Path(str(chain["authorized_synthesis"]["packet_dir"])),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "--authorization-packet" in result.payload["message"]
    assert chain["cycle_authorization"]["packet_id"] in result.payload["message"]
    assert result.payload["candidate_generated"] is False
    assert result.payload["model_calls"] == 0
    assert result.payload["counts"]["model_calls"] == 0


def test_next_target_strategy_refuses_authorization_that_enables_generation(tmp_path):
    chain = build_authorized_next_target_strategy_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_authorization_generation_enabled"
    shutil.copytree(Path(str(chain["cycle_authorization"]["packet_dir"])), invalid_packet)

    def _enable_generation(payload):
        payload["next_generation_authorized"] = True

    rewrite_payload(
        invalid_packet / "supervised_cycle_authorization_packet.json",
        _enable_generation,
    )

    result = run_next_target_strategy(
        chain["config"],
        authorization_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "authorizes generation" in result.payload["message"]
    assert result.payload["candidate_generated"] is False
    assert result.payload["model_calls"] == 0


def test_residual_target_selection_refuses_without_operator_review(tmp_path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_target_selection(
        config,
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=OBJECT_MOTION_CAUSALITY_TARGET_ID,
        operator_reviewed=False,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "--operator-reviewed" in result.payload["message"]
    assert result.payload["selected_residual_target_id"] == (
        OBJECT_MOTION_CAUSALITY_TARGET_ID
    )
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
    assert len(after_calls) == len(before_calls)


def test_residual_target_selection_refuses_hostile_scaffold_without_operator_review(
    tmp_path,
):
    chain = build_residual_target_selection_ready_chain(tmp_path)

    result = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        operator_reviewed=False,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "--operator-reviewed" in result.payload["message"]
    assert result.payload["selected_residual_target_id"] == (
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    )
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 0


def test_residual_target_selection_refuses_invalid_target_id(tmp_path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_target_selection(
        config,
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target="generic_vividness_repetition",
        operator_reviewed=True,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "not an available residual option" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
    assert len(after_calls) == len(before_calls)


def test_residual_target_selection_accepts_object_motion_causality_specificity(
    tmp_path,
):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    config = chain["config"]
    strategy_packet = Path(str(chain["selection_strategy"]["packet_dir"]))
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_target_selection(
        config,
        strategy_packet=strategy_packet,
        target=OBJECT_MOTION_CAUSALITY_TARGET_ID,
        operator_reviewed=True,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    assert result.payload["next_strategy_or_work_order_authorized"] is True
    assert result.payload["selected_residual_target_id"] == (
        OBJECT_MOTION_CAUSALITY_TARGET_ID
    )
    assert result.payload["broad_blocker_class"] == "first_read_object_event_pressure_gap"
    assert result.payload["next_allowed_action"] == NEXT_ALLOWED_ACTION
    assert result.payload["next_recommended_action"] == NEXT_ALLOWED_ACTION
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True

    packet_dir = Path(str(result.payload["packet_dir"]))
    assert packet_dir.parent.name == "residual_target_selection"
    assert {artifact.type for artifact in result.artifacts} == set(
        RESIDUAL_TARGET_SELECTION_ARTIFACT_TYPES
    )

    for artifact_type in RESIDUAL_TARGET_SELECTION_ARTIFACT_TYPES:
        envelope = json.loads(
            (packet_dir / f"{artifact_type}.json").read_text(encoding="utf-8")
        )
        assert envelope["artifact_type"] == artifact_type
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is None

    subject = read_payload(packet_dir / "residual_target_selection_subject_manifest.json")
    assert subject["source_strategy_packet_id"] == chain["selection_strategy"]["packet_id"]
    assert subject["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert subject["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert subject["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert subject["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert subject["repeated_broad_target_detected"] is True
    assert subject["same_broad_target_allowed"] is False

    intake = read_payload(packet_dir / "strategy_packet_intake_summary.json")
    assert intake["strategy_packet_consumed"] is True
    assert intake["strategy_packet_id"] == chain["selection_strategy"]["packet_id"]
    assert intake["repeated_broad_target_detected"] is True
    assert intake["same_broad_target_allowed"] is False
    assert intake["next_generation_authorized"] is False

    options = read_payload(packet_dir / "available_residual_options_report.json")
    assert options["residual_options_loaded"] is True
    assert OBJECT_MOTION_CAUSALITY_TARGET_ID in options["available_option_ids"]
    assert options["selected_target_valid"] is True

    choice = read_payload(packet_dir / "operator_residual_target_choice.json")
    assert choice["operator_reviewed"] is True
    assert choice["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert choice["selected_target_is_narrower_than_repeated_broad_target"] is True
    assert choice["candidate_generation_authorized"] is False
    assert choice["next_strategy_or_work_order_authorized"] is True

    contract = read_payload(packet_dir / "selected_residual_target_contract.json")
    assert contract["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert contract["target_definition"][
        "object_movement_should_produce_visible_consequence_before_explanation"
    ] is True
    assert "generic vividness" in contract["forbidden_under_this_target"]
    assert "direct candidate generation in this command" in contract[
        "forbidden_under_this_target"
    ]

    protected = read_payload(packet_dir / "protected_effects_and_forbidden_changes.json")
    assert any(
        chain["object_event"]["packet_id"] in item
        for item in protected["protected_effects"]
    )
    assert any(
        chain["object_event_proof"]["packet_id"] in item
        for item in protected["protected_effects"]
    )
    assert any(
        chain["object_event_reader_state"]["packet_id"] in item
        for item in protected["protected_effects"]
    )
    assert "rival mimicry" in protected["forbidden_changes"]
    assert "phase-shift claim" in protected["forbidden_changes"]

    scope = read_payload(packet_dir / "next_work_order_scope.json")
    assert scope["next_allowed_action"] == NEXT_ALLOWED_ACTION
    assert scope["candidate_generation_authorized"] is False
    assert scope["live_model_call_authorized"] is False
    assert scope["ablation_authorized"] is False
    assert scope["reader_state_eval_authorized"] is False
    assert scope["requires_separate_generation_authorization"] is True
    assert scope["next_strategy_or_work_order_authorized"] is True

    gate = read_payload(packet_dir / "residual_target_selection_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "strategy_packet_consumed",
        "residual_options_loaded",
        "operator_review_recorded",
        "selected_target_valid",
        "selected_target_narrower_than_repeated_broad_target",
        "protected_effects_recorded",
        "no_candidate_generated",
        "no_openai_calls",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "candidate_generation_authorized",
        "live_model_call_authorized",
        "ablation_authorized",
        "reader_state_eval_authorized",
        "finalization_eligible",
        "strongest_rival_defeated",
        "human_validation_present",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["candidate_generation_authorized"] is False

    packet = read_payload(packet_dir / "residual_target_selection_packet.json")
    assert packet["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert packet["next_allowed_action"] == NEXT_ALLOWED_ACTION
    assert packet["candidate_generation_authorized"] is False
    assert packet["next_strategy_or_work_order_authorized"] is True
    assert packet["counts"]["model_calls"] == 0
    assert packet["counts"]["candidate_artifacts_created"] == 0
    assert packet["counts"]["produced_artifacts"] == len(
        RESIDUAL_TARGET_SELECTION_ARTIFACT_TYPES
    )
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_residual_target_selection_accepts_tactile_inevitability_gap(tmp_path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    config = chain["config"]

    result = run_residual_target_selection(
        config,
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=TACTILE_INEVITABILITY_TARGET_ID,
        operator_reviewed=True,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["next_allowed_action"] == "prepare_tactile_inevitability_work_order"
    assert result.payload["next_recommended_action"] == (
        "prepare_tactile_inevitability_work_order"
    )
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    assert result.payload["next_strategy_or_work_order_authorized"] is True
    assert result.payload["counts"]["model_calls"] == 0

    packet_dir = Path(str(result.payload["packet_dir"]))
    contract = read_payload(packet_dir / "selected_residual_target_contract.json")
    assert contract["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert contract["target_definition"][
        "material_force_or_contact_relation_must_drive_visible_consequence"
    ] is True
    assert "object_movement_should_produce_visible_consequence_before_explanation" not in (
        contract["target_definition"]
    )
    assert "new object inventory" in contract["forbidden_under_this_target"]

    scope = read_payload(packet_dir / "next_work_order_scope.json")
    assert scope["next_allowed_action"] == "prepare_tactile_inevitability_work_order"
    assert scope["work_order_adapter"] == "tactile_inevitability"
    assert scope["candidate_generation_authorized"] is False

    packet = read_payload(packet_dir / "residual_target_selection_packet.json")
    assert packet["next_allowed_action"] == "prepare_tactile_inevitability_work_order"
    assert packet["work_order_adapter"] == "tactile_inevitability"


def test_residual_target_selection_accepts_ending_explains_return_risk(tmp_path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_target_selection(
        config,
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
        operator_reviewed=True,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == (
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    )
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert result.payload["next_allowed_action"] == (
        "prepare_ending_explains_return_risk_work_order"
    )
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    assert result.payload["next_strategy_or_work_order_authorized"] is True
    assert result.payload["model_calls"] == 0
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True

    packet_dir = Path(str(result.payload["packet_dir"]))
    contract = read_payload(packet_dir / "selected_residual_target_contract.json")
    assert contract["selected_residual_target_id"] == (
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    )
    assert contract["target_definition"]["final_return_should_enact_not_explain"] is True
    assert "explaining return more explicitly" in contract["forbidden_under_this_target"]
    protected = read_payload(packet_dir / "protected_effects_and_forbidden_changes.json")
    assert "opening-return relation" in protected["protected_effects"]
    assert "strongest-rival pressure preservation" in protected["protected_effects"]
    assert "returning to hostile scaffold generation" in protected["forbidden_changes"]

    scope = read_payload(packet_dir / "next_work_order_scope.json")
    assert scope["work_order_adapter"] == "ending_return_risk"
    assert scope["next_allowed_action"] == (
        "prepare_ending_explains_return_risk_work_order"
    )
    assert scope["candidate_generation_authorized"] is False
    assert scope["future_generation_requires_separate_authorization"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_residual_target_selection_accepts_hostile_scaffold_visibility_and_normalizes_stale_best(
    tmp_path,
):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    strategy_packet = tmp_path / "strategy_with_stale_current_best_wording"
    shutil.copytree(Path(str(chain["selection_strategy"]["packet_dir"])), strategy_packet)
    current_best_id = chain["object_event"]["packet_id"]

    def _add_stale_strategy_text(payload):
        payload.setdefault("strategy", []).append(
            "preserve packet_0061 as current best candidate"
        )

    def _add_stale_protection(payload):
        payload.setdefault("protected_effects", []).append(
            "protect packet_0061 partial reread transformation"
        )

    def _add_stale_ablation_text(payload):
        payload.setdefault("if_future_candidate_is_generated", []).append(
            "future ablation should run against packet_0061"
        )

    rewrite_payload(
        strategy_packet / "next_intervention_strategy.json",
        _add_stale_strategy_text,
    )
    rewrite_payload(
        strategy_packet / "protected_effects_and_forbidden_changes.json",
        _add_stale_protection,
    )
    rewrite_payload(
        strategy_packet / "ablation_and_reader_eval_plan.json",
        _add_stale_ablation_text,
    )

    with connect(chain["config"].db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_target_selection(
        chain["config"],
        strategy_packet=strategy_packet,
        target=HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        operator_reviewed=True,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == (
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    )
    assert result.payload["current_best_candidate_packet_id"] == current_best_id
    assert result.payload["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert result.payload["next_allowed_action"] == (
        "prepare_hostile_scaffold_visibility_work_order"
    )
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    assert result.payload["next_strategy_or_work_order_authorized"] is True
    assert result.payload["model_calls"] == 0
    assert result.payload["stale_strategy_current_best_reference_detected"] is True
    assert result.payload["stale_reference_packet_id"] == "packet_0061"
    assert result.payload["authoritative_current_best_packet_id"] == current_best_id

    packet_dir = Path(str(result.payload["packet_dir"]))
    contract = read_payload(packet_dir / "selected_residual_target_contract.json")
    assert contract["target_definition"][
        "visible_thesis_scaffold_or_explanatory_pressure_should_decrease"
    ] is True
    assert "delete proof/no-answer structure" in contract["forbidden_under_this_target"]
    assert contract["stale_strategy_current_best_reference_detected"] is True

    protected = read_payload(packet_dir / "protected_effects_and_forbidden_changes.json")
    assert any(current_best_id in item for item in protected["protected_effects"])
    assert all("packet_0061" not in item for item in protected["protected_effects"])
    assert "turning the candidate into explanation" in protected["forbidden_changes"]

    scope = read_payload(packet_dir / "next_work_order_scope.json")
    assert scope["work_order_adapter"] == "hostile_scaffold_visibility"
    assert scope["candidate_generation_authorized"] is False
    assert scope["live_model_call_authorized"] is False

    with connect(chain["config"].db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_residual_target_adapter_registry_and_generic_schema_are_strict():
    object_adapter = require_residual_target_adapter(OBJECT_MOTION_CAUSALITY_TARGET_ID)
    tactile_adapter = require_residual_target_adapter(TACTILE_INEVITABILITY_TARGET_ID)
    hostile_adapter = require_residual_target_adapter(HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID)
    ending_adapter = require_residual_target_adapter(ENDING_EXPLAINS_RETURN_RISK_TARGET_ID)

    assert object_adapter.generation_contract_version == (
        OBJECT_MOTION_GENERATION_CONTRACT_VERSION
    )
    assert object_adapter.work_order_contract_version == (
        OBJECT_MOTION_WORK_ORDER_CONTRACT_VERSION
    )
    assert tactile_adapter.generation_schema == RESIDUAL_INTERVENTION_GENERATION_SCHEMA
    assert tactile_adapter.generation_contract_version == TACTILE_GENERATION_CONTRACT_VERSION
    assert tactile_adapter.work_order_contract_version == TACTILE_WORK_ORDER_CONTRACT_VERSION
    assert hostile_adapter.generation_schema == RESIDUAL_INTERVENTION_GENERATION_SCHEMA
    assert hostile_adapter.generation_contract_version == (
        HOSTILE_SCAFFOLD_GENERATION_CONTRACT_VERSION
    )
    assert hostile_adapter.generation_contract_version != "placeholder_1"
    assert hostile_adapter.work_order_contract_version == (
        HOSTILE_SCAFFOLD_WORK_ORDER_CONTRACT_VERSION
    )
    assert hostile_adapter.adapter_id == "hostile_scaffold_visibility"
    assert ending_adapter.adapter_id == "ending_return_risk"
    assert ending_adapter.work_order_contract_version == (
        ENDING_RETURN_WORK_ORDER_CONTRACT_VERSION
    )
    assert ending_adapter.generation_contract_version == (
        ENDING_RETURN_GENERATION_CONTRACT_VERSION
    )
    assert object_adapter.materiality_policy.policy_id
    assert tactile_adapter.materiality_policy.policy_id
    assert hostile_adapter.materiality_policy.policy_id == (
        HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID
    )
    assert hostile_adapter.materiality_policy.policy_id != (
        HOSTILE_SCAFFOLD_PLACEHOLDER_MATERIALITY_POLICY_ID
    )
    assert object_adapter.materiality_policy.primary_materiality_scope == (
        "whole_selected_region"
    )
    assert tactile_adapter.materiality_policy.primary_materiality_scope == (
        "target_bearing_scope"
    )
    assert tactile_adapter.materiality_policy.whole_region_guard[
        "near_copy_guard_only"
    ] is True
    assert tactile_adapter.materiality_policy.overlap_cluster_policy[
        "validate_member_semantics_separately"
    ] is True
    assert hostile_adapter.materiality_policy.primary_materiality_scope == (
        "target_bearing_scope"
    )
    assert "scaffold_leakage_failures" in (
        hostile_adapter.materiality_policy.failure_report_fields
    )
    assert ending_adapter.prompt_contract_id == (
        "autonomous.residual_intervention_generation.v1.ending_return_risk"
    )
    assert ending_adapter.semantic_validator_id == ENDING_RETURN_SEMANTIC_VALIDATOR_ID
    assert ending_adapter.materiality_policy.policy_id == ENDING_RETURN_MATERIALITY_POLICY_ID
    assert ending_adapter.materiality_policy.primary_materiality_scope == (
        "target_bearing_scope"
    )
    assert "ending_return_explanation_leakage_failures" in (
        ending_adapter.materiality_policy.failure_report_fields
    )
    assert target_generation_readiness_failures(
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    ) == []
    assert target_generation_readiness_failures(
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    ) == []
    with pytest.raises(ValueError, match="unsupported selected residual target"):
        require_residual_target_adapter("unsupported_target")

    schema = json_schema_for_worker_schema(RESIDUAL_INTERVENTION_GENERATION_SCHEMA)
    assert schema["properties"]["target_unit_mappings"]["items"][
        "additionalProperties"
    ] is False
    request = WorkerRequest(
        run_id="run_schema_test",
        worker_role=tactile_adapter.worker_role,
        prompt_contract_id=tactile_adapter.prompt_contract_id,
        schema=RESIDUAL_INTERVENTION_GENERATION_SCHEMA,
        input_text="{}",
    )
    response_format = openai_response_format_for_request(request)
    assert response_format["strict"] is True
    assert_strict_object_schema(response_format["schema"], path="ResidualIntervention")


def test_residual_work_order_refuses_invalid_target_selection(tmp_path):
    chain = build_residual_work_order_ready_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_residual_selection_target"
    shutil.copytree(
        Path(str(chain["residual_target_selection"]["packet_dir"])),
        invalid_packet,
    )

    def _wrong_target(payload):
        payload["selected_residual_target_id"] = "proof_no_answer_residue"

    rewrite_payload(invalid_packet / "residual_target_selection_packet.json", _wrong_target)

    result = run_residual_work_order_planning(
        chain["config"],
        selection_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "selected residual target" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False


def test_residual_work_order_refuses_missing_current_best_candidate(tmp_path):
    chain = build_residual_work_order_ready_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_residual_selection_missing_current_best"
    shutil.copytree(
        Path(str(chain["residual_target_selection"]["packet_dir"])),
        invalid_packet,
    )

    def _remove_current_best(payload):
        payload["current_best_candidate_packet_id"] = ""

    rewrite_payload(
        invalid_packet / "residual_target_selection_packet.json",
        _remove_current_best,
    )

    result = run_residual_work_order_planning(
        chain["config"],
        selection_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "current best candidate is missing" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False


def test_residual_work_order_normalizes_stale_tactile_selection_routing(tmp_path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=TACTILE_INEVITABILITY_TARGET_ID,
        operator_reviewed=True,
    )
    assert selection.exit_code == 0
    stale_packet = tmp_path / "stale_tactile_selection"
    shutil.copytree(Path(str(selection.payload["packet_dir"])), stale_packet)

    def _stale_action(payload):
        payload["next_allowed_action"] = NEXT_ALLOWED_ACTION
        payload["next_recommended_action"] = NEXT_ALLOWED_ACTION

    rewrite_payload(stale_packet / "residual_target_selection_packet.json", _stale_action)
    rewrite_payload(stale_packet / "next_work_order_scope.json", _stale_action)
    rewrite_payload(stale_packet / "residual_target_selection_gate_report.json", _stale_action)

    result = run_residual_work_order_planning(
        chain["config"],
        selection_packet=stale_packet,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["selected_residual_target_id"] != OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert result.payload["stale_selection_routing_detected"] is True
    assert result.payload["stale_next_action_ignored"] == NEXT_ALLOWED_ACTION
    assert result.payload["canonical_next_action"] == "prepare_tactile_inevitability_work_order"
    assert result.payload["routing_normalized_from_selected_target"] is True
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["target_unit_count"] > 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    assert result.payload["future_generation_authorized"] is False
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["next_recommended_action"] == (
        "review_tactile_inevitability_work_order_before_generation_authorization"
    )

    packet_dir = Path(str(result.payload["packet_dir"]))
    unit_map = read_payload(packet_dir / "object_motion_target_unit_map.json")
    assert unit_map["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert unit_map["unit_map_kind"] == "tactile_inevitability"
    assert unit_map["target_unit_count"] > 0
    for unit in unit_map["target_units"]:
        assert unit["target_unit_id"].startswith("tactile_unit_")
        assert "source_target_unit_id" in unit
        assert unit["before_text_sha256"]
        assert "distinct_from_object_motion_basis" in unit

    novelty = read_payload(packet_dir / "target_novelty_distinctness_report.json")
    assert novelty["selected_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert "first_read_object_event_pressure_gap" in novelty["attempted_target_ids"]
    assert novelty["merely_relabels_object_motion"] is False
    assert novelty["proceed_with_work_order"] is True

    gate = read_payload(packet_dir / "residual_work_order_gate_report.json")
    gates = {item["gate_name"]: item for item in gate["gate_results"]}
    for gate_name in (
        "selection_packet_consumed",
        "selected_target_supported",
        "operator_choice_matches_selected_target",
        "stale_selection_routing_detected",
        "stale_selection_routing_safely_normalized",
        "target_adapter_resolved",
        "current_best_candidate_resolved",
        "evidence_chain_resolved",
        "bounded_region_selected",
        "target_units_created",
        "target_mechanism_distinct",
        "no_candidate_generated",
        "no_openai_calls",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gates[gate_name]["passed"] is True
    for gate_name in (
        "candidate_generated",
        "candidate_generation_authorized",
        "ablation_completed",
        "reader_state_eval_completed",
        "strongest_rival_defeated",
        "finalization_eligible",
        "human_validation_present",
    ):
        assert gates[gate_name]["passed"] is False


def test_residual_work_order_accepts_hostile_scaffold_visibility_selection(
    tmp_path,
):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        operator_reviewed=True,
    )
    assert selection.exit_code == 0
    with connect(chain["config"].db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert result.payload["selected_residual_target_id"] == (
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    )
    assert result.payload["next_allowed_action"] == (
        "review_hostile_scaffold_visibility_work_order_before_generation_authorization"
    )
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    assert result.payload["counts"]["model_calls"] == 0

    packet_dir = Path(str(result.payload["packet_dir"]))
    subject = read_payload(packet_dir / "residual_work_order_subject_manifest.json")
    assert subject["target_adapter_id"] == "hostile_scaffold_visibility"
    assert subject["work_order_contract_version"] == (
        HOSTILE_SCAFFOLD_WORK_ORDER_CONTRACT_VERSION
    )
    assert subject["candidate_generated"] is False

    diagnostic = read_payload(packet_dir / "object_motion_causality_diagnostic.json")
    assert diagnostic["diagnostic_kind"] == "hostile_scaffold_visibility_diagnostic"
    assert diagnostic["legacy_artifact_name"] == "object_motion_causality_diagnostic"
    categories = {
        finding["category"] for finding in diagnostic["diagnostic_findings"]
    }
    assert "overexplanation" in categories
    assert "thesis_replacing_artifact" in categories
    assert "cosmic_silence_as_slogan" in categories
    assert "proof_no_outside_answer_refinement" in categories
    assert "final_return_echo_reread_strength" in categories
    assert "strongest_rival_first_read_vividness" in categories
    assert "local_embodiment_vs_compression_balance" in categories

    selected_region = read_payload(packet_dir / "selected_intervention_region.json")
    selected_region_text = " ".join(
        selected_region["selected_region_before_text"].split()
    )
    unit_map = read_payload(packet_dir / "object_motion_target_unit_map.json")
    assert unit_map["selected_residual_target_id"] == (
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    )
    assert unit_map["unit_map_kind"] == "hostile_scaffold_visibility"
    assert unit_map["legacy_artifact_name"] == "object_motion_target_unit_map"
    assert unit_map["material_target_units_all_inside_selected_region"] is True
    unit_ids = {unit["unit_id"] for unit in unit_map["target_units"]}
    assert {
        "trace_before_naming_scaffold_reduction",
        "crossings_matter_without_thesis_pressure",
        "ordinary_table_no_scaffold_signage",
        "ordinary_things_strict_without_abstraction",
        "small_kitchen_rule_plainness_reduction",
    }.issubset(unit_ids)
    protected_reference_ids = {
        unit["reference_unit_id"] for unit in unit_map["protected_reference_units"]
    }
    assert {
        "proof_no_answer_embodiment_preservation",
        "final_return_echo_without_explanation",
        "preserve_table_dust_spoon_saucer_ring_causal_field",
    } <= protected_reference_ids
    assert "proof_no_answer_embodiment_preservation" not in unit_ids
    assert "final_return_echo_without_explanation" not in unit_ids
    assert "preserve_table_dust_spoon_saucer_ring_causal_field" not in unit_ids
    for unit in unit_map["target_units"]:
        assert " ".join(unit["before_text"].split()) in selected_region_text
        assert unit["source_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
        assert unit["source_span"]["region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
        assert unit["source_span"]["contained_in_selected_region"] is True
        assert unit["before_text_sha256"]
        assert unit["future_generation_authorized"] is False
        assert "broad rewrite" in unit["forbidden_operation"]
    for unit in unit_map["protected_reference_units"]:
        assert unit["material_change_required"] is False
        assert unit["future_generation_authorized"] is False
    assert unit_map["future_generation_requires_separate_authorization"] is True
    assert unit_map["future_generation_authorized"] is False

    preflight_payloads = {
        artifact_type: read_payload(packet_dir / f"{artifact_type}.json")
        for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    }
    assert semantic_preflight_failures_for_work_order(preflight_payloads) == []

    protected = read_payload(packet_dir / "protected_effects_and_forbidden_changes.json")
    assert any(chain["object_event"]["packet_id"] in item for item in protected["protected_effects"])
    assert "table/dust/spoon/saucer/ring causal field" in protected["protected_effects"]
    assert "proof/no-answer pressure" in protected["protected_effects"]
    assert "opening-return relation" in protected["protected_effects"]
    assert "generic vividness" in protected["forbidden_changes"]
    assert "turning the candidate into explanation" in protected["forbidden_changes"]

    contract = read_payload(packet_dir / "future_generation_contract.json")
    assert contract["future_generation_requires_separate_authorization"] is True
    assert contract["candidate_generation_authorized"] is False
    assert contract["live_model_call_authorized"] is False
    assert "hostile scaffold visibility" in " ".join(
        contract["target_specific_reader_state_focus"]
    )

    plan = read_payload(packet_dir / "ablation_and_reader_eval_plan.json")
    assert "proof_no_answer_preservation_control" in plan["future_ablation_controls"]
    assert "hostile scaffold visibility" in plan["future_reader_state_eval_focus"]
    assert plan["ablation_authorized"] is False
    assert plan["reader_state_eval_authorized"] is False

    gate = read_payload(packet_dir / "residual_work_order_gate_report.json")
    gates = {item["gate_name"]: item for item in gate["gate_results"]}
    assert gates["target_adapter_resolved"]["passed"] is True
    assert gates["target_units_created"]["passed"] is True
    assert gates["target_units_inside_selected_region"]["passed"] is True
    assert gates["target_mechanism_distinct"]["passed"] is True
    assert gates["no_openai_calls"]["passed"] is True
    assert gates["candidate_generation_authorized"]["passed"] is False
    assert gate["finalization_eligible"] is False

    with connect(chain["config"].db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_residual_work_order_accepts_ending_explains_return_risk_selection(
    tmp_path,
):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=ENDING_EXPLAINS_RETURN_RISK_TARGET_ID,
        operator_reviewed=True,
    )
    assert selection.exit_code == 0
    with connect(chain["config"].db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert result.payload["selected_residual_target_id"] == (
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    )
    assert result.payload["target_adapter_id"] == "ending_return_risk"
    assert result.payload["selected_region_id"] == ENDING_RETURN_REGION_ID
    assert result.payload["next_recommended_action"] == (
        "review_ending_explains_return_risk_work_order_before_generation_authorization"
    )
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["finalization_eligible"] is False

    packet_dir = Path(str(result.payload["packet_dir"]))
    subject = read_payload(packet_dir / "residual_work_order_subject_manifest.json")
    assert subject["target_adapter_id"] == "ending_return_risk"
    assert subject["selected_region_id"] == ENDING_RETURN_REGION_ID
    assert subject["work_order_contract_version"] == (
        ENDING_RETURN_WORK_ORDER_CONTRACT_VERSION
    )
    assert subject["generation_contract_version"] == (
        ENDING_RETURN_GENERATION_CONTRACT_VERSION
    )

    inventory = read_payload(packet_dir / "current_candidate_region_inventory.json")
    final_region = [
        region
        for region in inventory["regions"]
        if region["region_id"] == ENDING_RETURN_REGION_ID
    ][0]
    middle_region = [
        region
        for region in inventory["regions"]
        if region["region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    ][0]
    assert final_region["eligible_for_ending_explains_return_risk_work"] is True
    assert middle_region["eligible_for_ending_explains_return_risk_work"] is False
    assert inventory["selected_region_candidate"] == ENDING_RETURN_REGION_ID

    selected_region = read_payload(packet_dir / "selected_intervention_region.json")
    selected_region_text = " ".join(
        selected_region["selected_region_before_text"].split()
    )
    assert selected_region["selected_region_id"] == ENDING_RETURN_REGION_ID
    assert selected_region["strategy_evidence_points_to_region"] is True
    assert selected_region["region_change_authorized_now"] is False
    assert "final-return region" in selected_region["selection_reason"]
    assert "final_return_opening_transformation_region" in (
        selected_region["selected_region_id"]
    )

    diagnostic = read_payload(packet_dir / "object_motion_causality_diagnostic.json")
    assert diagnostic["diagnostic_kind"] == "ending_explains_return_risk_diagnostic"
    assert diagnostic["likely_strongest_candidate_region"] == ENDING_RETURN_REGION_ID
    categories = {
        finding["category"] for finding in diagnostic["diagnostic_findings"]
    }
    assert "final_return_explains_rather_than_enacts" in categories
    assert "middle_recurrence_protection" in categories

    unit_map = read_payload(packet_dir / "object_motion_target_unit_map.json")
    assert unit_map["selected_residual_target_id"] == (
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    )
    assert unit_map["unit_map_kind"] == "ending_return_risk"
    assert unit_map["selected_region_id"] == ENDING_RETURN_REGION_ID
    assert unit_map["material_target_units_all_inside_selected_region"] is True
    assert unit_map["future_generation_authorized"] is False
    assert unit_map["materiality_policy_id"] == ENDING_RETURN_MATERIALITY_POLICY_ID
    assert unit_map["semantic_validator_id"] == ENDING_RETURN_SEMANTIC_VALIDATOR_ID
    unit_ids = {unit["unit_id"] for unit in unit_map["target_units"]}
    assert {
        "final_return_enacts_not_explains",
        "opening_return_relation_without_thesis",
        "no_reset_return_pressure",
        "same_object_field_returns_without_summary",
        "proof_no_answer_carry_preserved",
    } <= unit_ids
    for unit in unit_map["target_units"]:
        assert " ".join(unit["before_text"].split()) in selected_region_text
        assert unit["source_region_id"] == ENDING_RETURN_REGION_ID
        assert unit["source_span"]["region_id"] == ENDING_RETURN_REGION_ID
        assert unit["source_span"]["contained_in_selected_region"] is True
        assert unit["before_text_sha256"]
        assert unit["future_generation_authorized"] is False
        assert "explain return more explicitly" in unit["forbidden_operation"]
    overlap_report = unit_map["target_unit_overlap_cluster_report"]
    assert overlap_report["overlap_cluster_count"] >= 2
    cluster_sets = {
        frozenset(cluster["overlapping_unit_ids"])
        for cluster in overlap_report["overlap_clusters"]
    }
    assert frozenset(
        {
            "final_return_enacts_not_explains",
            "proof_no_answer_carry_preserved",
        }
    ) in cluster_sets
    assert any(
        {
            "opening_return_relation_without_thesis",
            "no_reset_return_pressure",
        }
        <= set(cluster)
        for cluster in cluster_sets
    )
    for cluster in overlap_report["overlap_clusters"]:
        assert cluster["overlap_allowed"] is True
        assert cluster["one_replacement_may_satisfy_multiple_units"] is True
        assert cluster["distinct_semantic_checks_required"] is True
        obligations = cluster["semantic_obligations_by_unit"]
        assert set(cluster["overlapping_unit_ids"]) <= set(obligations)

    protected_reference_ids = {
        unit["reference_unit_id"] for unit in unit_map["protected_reference_units"]
    }
    assert {
        "opening_table_field_reference",
        "middle_recurrence_object_field_reference",
        "proof_no_answer_pressure_reference",
    } <= protected_reference_ids
    assert "middle_recurrence_object_field_reference" not in unit_ids
    for unit in unit_map["protected_reference_units"]:
        assert unit["material_change_required"] is False
        assert unit["future_generation_authorized"] is False
        assert unit["source_region_id"] != ENDING_RETURN_REGION_ID

    contract = read_payload(packet_dir / "future_generation_contract.json")
    assert contract["selected_region_id"] == ENDING_RETURN_REGION_ID
    assert contract["future_generation_requires_separate_authorization"] is True
    assert contract["future_generation_authorized"] is False
    assert contract["candidate_generation_authorized"] is False
    assert contract["generation_contract_version"] == (
        ENDING_RETURN_GENERATION_CONTRACT_VERSION
    )
    assert contract["materiality_policy_id"] == ENDING_RETURN_MATERIALITY_POLICY_ID
    assert contract["semantic_validator_id"] == ENDING_RETURN_SEMANTIC_VALIDATOR_ID
    assert contract["target_unit_overlap_cluster_report"][
        "overlap_cluster_count"
    ] == overlap_report["overlap_cluster_count"]
    assert "full_ending_return_intervention" in contract[
        "target_specific_ablation_controls"
    ]
    assert "revert_ending_return_intervention_to_current_best" in contract[
        "target_specific_ablation_controls"
    ]
    assert "proof_no_answer_preservation_control" in contract[
        "target_specific_ablation_controls"
    ]
    assert "final return enacts rather than explains" in contract[
        "target_specific_reader_state_focus"
    ]
    assert "no-reset return pressure" in contract["target_specific_reader_state_focus"]
    assert "object-field return preservation" in contract[
        "target_specific_reader_state_focus"
    ]

    protected = read_payload(packet_dir / "protected_effects_and_forbidden_changes.json")
    assert "object/tactile causal field" in protected["protected_effects"]
    assert "proof/no-answer pressure" in protected["protected_effects"]
    assert "opening-return relation" in protected["protected_effects"]
    assert "hostile path paused/exhausted" in protected["protected_effects"]
    assert "explaining return more explicitly" in protected["forbidden_changes"]

    plan = read_payload(packet_dir / "ablation_and_reader_eval_plan.json")
    assert "full_ending_return_intervention" in plan["future_ablation_controls"]
    assert "revert_ending_return_intervention_to_current_best" in plan[
        "future_ablation_controls"
    ]
    assert "revert_ending_return_intervention" in plan["future_ablation_controls"]
    assert "strongest_rival_comparison" in plan["future_ablation_controls"]
    assert "reread transformation" in plan["future_reader_state_eval_focus"]
    assert "no-reset return pressure" in plan["future_reader_state_eval_focus"]
    assert plan["ablation_authorized"] is False
    assert plan["reader_state_eval_authorized"] is False

    gate = read_payload(packet_dir / "residual_work_order_gate_report.json")
    gates = {item["gate_name"]: item for item in gate["gate_results"]}
    assert gates["target_adapter_resolved"]["passed"] is True
    assert gates["bounded_region_selected"]["passed"] is True
    assert gates["target_units_created"]["passed"] is True
    assert gates["target_units_inside_selected_region"]["passed"] is True
    assert gates["no_openai_calls"]["passed"] is True
    assert gates["candidate_generation_authorized"]["passed"] is False
    assert gate["finalization_eligible"] is False

    preflight_payloads = {
        artifact_type: read_payload(packet_dir / f"{artifact_type}.json")
        for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    }
    assert semantic_preflight_failures_for_work_order(preflight_payloads) == []

    with connect(chain["config"].db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_hostile_scaffold_work_order_supersedes_out_of_region_target_units(
    tmp_path,
):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        operator_reviewed=True,
    )
    unsafe = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )
    assert unsafe.exit_code == 0
    unsafe_packet_dir = Path(str(unsafe.payload["packet_dir"]))
    out_of_region_text = "No answer enters from outside the room."

    def _add_out_of_region_material_unit(payload):
        payload["target_units"].append(
            {
                "unit_id": "proof_no_answer_embodiment_preservation",
                "target_unit_id": "proof_no_answer_embodiment_preservation",
                "before_text": out_of_region_text,
                "before_text_sha256": sha256_text(out_of_region_text),
                "parent_region_id": "proof_no_outside_answer_region",
                "source_region_id": "proof_no_outside_answer_region",
                "source_span": {
                    "region_id": "proof_no_outside_answer_region",
                    "char_start": None,
                    "char_end": None,
                    "before_text_sha256": sha256_text(out_of_region_text),
                    "contained_in_selected_region": False,
                },
                "material_change_required": True,
                "future_generation_authorized": False,
            }
        )
        payload["target_unit_count"] = len(payload["target_units"])
        payload["material_target_units_all_inside_selected_region"] = False

    rewrite_payload(
        unsafe_packet_dir / "object_motion_target_unit_map.json",
        _add_out_of_region_material_unit,
    )
    payloads = {
        artifact_type: read_payload(unsafe_packet_dir / f"{artifact_type}.json")
        for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    }
    failures = semantic_preflight_failures_for_work_order(payloads)
    assert any(
        "out_of_region_target_units_in_single_region_work_order" in failure
        for failure in failures
    )

    refused = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=unsafe_packet_dir,
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert refused.exit_code == 1
    assert refused.payload["accepted"] is False
    assert "work-order semantic preflight failed" in refused.payload["message"]
    assert "out_of_region_target_units_in_single_region_work_order" in refused.payload[
        "message"
    ]

    successor = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )

    assert successor.exit_code == 0
    assert successor.payload["accepted"] is True
    assert successor.payload["superseded_work_order_packet_id"] == unsafe_packet_dir.name
    assert successor.payload["supersession_reason"] == (
        "out_of_region_target_units_in_single_region_work_order"
    )
    assert successor.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert successor.payload["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert successor.payload["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert successor.payload["candidate_generated"] is False
    assert successor.payload["candidate_generation_authorized"] is False
    assert successor.payload["counts"]["model_calls"] == 0

    successor_dir = Path(str(successor.payload["packet_dir"]))
    selected_region = read_payload(successor_dir / "selected_intervention_region.json")
    selected_region_text = " ".join(
        selected_region["selected_region_before_text"].split()
    )
    unit_map = read_payload(successor_dir / "object_motion_target_unit_map.json")
    for unit in unit_map["target_units"]:
        assert unit["material_change_required"] is True
        assert " ".join(unit["before_text"].split()) in selected_region_text
        assert unit["source_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
        assert unit["source_span"]["region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    protected_reference_ids = {
        unit["reference_unit_id"] for unit in unit_map["protected_reference_units"]
    }
    assert "proof_no_answer_embodiment_preservation" in protected_reference_ids
    assert "final_return_echo_without_explanation" in protected_reference_ids
    assert "preserve_table_dust_spoon_saucer_ring_causal_field" in protected_reference_ids
    assert all(
        unit["material_change_required"] is False
        for unit in unit_map["protected_reference_units"]
    )

    successor_payloads = {
        artifact_type: read_payload(successor_dir / f"{artifact_type}.json")
        for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    }
    assert semantic_preflight_failures_for_work_order(successor_payloads) == []


def test_ending_return_work_order_supersedes_planning_only_handoff_metadata(
    tmp_path,
):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    config = chain["config"]
    stale_packet_dir = Path(str(chain["residual_work_order"]["packet_dir"]))

    for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES:
        def _make_planning_only(payload, artifact_type=artifact_type):
            payload["generation_contract_version"] = (
                ENDING_RETURN_PLACEHOLDER_GENERATION_CONTRACT_VERSION
            )
            payload["materiality_policy_id"] = (
                ENDING_RETURN_PLACEHOLDER_MATERIALITY_POLICY_ID
            )
            if artifact_type in {
                "residual_work_order_packet",
                "future_generation_contract",
            }:
                payload["future_generation_authorized"] = None

        rewrite_payload(stale_packet_dir / f"{artifact_type}.json", _make_planning_only)

    payloads = {
        artifact_type: read_payload(stale_packet_dir / f"{artifact_type}.json")
        for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    }
    assert semantic_preflight_failures_for_work_order(payloads) == []

    successor = run_residual_work_order_planning(
        config,
        selection_packet=Path(str(chain["residual_target_selection"]["packet_dir"])),
    )

    assert successor.exit_code == 0
    assert successor.payload["accepted"] is True
    assert successor.payload["superseded_work_order_packet_id"] == stale_packet_dir.name
    assert successor.payload["supersession_reason"] == (
        "ending_return_generation_handoff_metadata_missing"
    )
    assert successor.payload["selected_region_id"] == ENDING_RETURN_REGION_ID
    assert successor.payload["candidate_generated"] is False
    assert successor.payload["candidate_generation_authorized"] is False
    assert successor.payload["future_generation_authorized"] is False
    assert successor.payload["counts"]["model_calls"] == 0

    successor_dir = Path(str(successor.payload["packet_dir"]))
    packet = read_payload(successor_dir / "residual_work_order_packet.json")
    unit_map = read_payload(successor_dir / "object_motion_target_unit_map.json")
    contract = read_payload(successor_dir / "future_generation_contract.json")
    assert packet["generation_contract_version"] == ENDING_RETURN_GENERATION_CONTRACT_VERSION
    assert packet["materiality_policy_id"] == ENDING_RETURN_MATERIALITY_POLICY_ID
    assert packet["future_generation_authorized"] is False
    assert contract["future_generation_authorized"] is False
    assert unit_map["future_generation_authorized"] is False
    assert unit_map["target_unit_overlap_cluster_report"]["overlap_cluster_count"] >= 2
    successor_payloads = {
        artifact_type: read_payload(successor_dir / f"{artifact_type}.json")
        for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    }
    assert semantic_preflight_failures_for_work_order(successor_payloads) == []


def test_tactile_stale_work_order_fails_preflight_and_successor_supersedes(tmp_path):
    chain = build_tactile_residual_work_order_chain(tmp_path)
    config = chain["config"]
    stale_packet_dir = Path(str(chain["residual_work_order"]["packet_dir"]))

    def _stale_unit_two(payload):
        payload["target_adapter_version"] = "1"
        payload["work_order_contract_version"] = "1"
        for unit in payload["target_units"]:
            if unit["unit_id"] == "tactile_unit_002":
                unit["current_physical_relation"] = (
                    "release, fall, or impact leaves a visible break"
                )
                unit.pop("source_unit_role", None)

    def _stale_packet(payload):
        payload["target_adapter_version"] = "1"
        payload["work_order_contract_version"] = "1"

    rewrite_payload(stale_packet_dir / "object_motion_target_unit_map.json", _stale_unit_two)
    rewrite_payload(stale_packet_dir / "future_generation_contract.json", _stale_packet)
    rewrite_payload(stale_packet_dir / "residual_work_order_packet.json", _stale_packet)

    payloads = {
        artifact_type: read_payload(stale_packet_dir / f"{artifact_type}.json")
        for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    }
    failures = semantic_preflight_failures_for_work_order(payloads)
    assert any("fall/break/impact relation" in failure for failure in failures)

    refused = run_residual_generation_authorization(
        config,
        work_order_packet=stale_packet_dir,
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert refused.exit_code == 1
    assert refused.payload["accepted"] is False
    assert "semantic preflight failed" in refused.payload["message"]

    successor = run_residual_work_order_planning(
        config,
        selection_packet=Path(str(chain["residual_target_selection"]["packet_dir"])),
    )
    assert successor.exit_code == 0
    assert successor.payload["accepted"] is True
    assert successor.payload["superseded_work_order_packet_id"] == stale_packet_dir.name
    assert successor.payload["new_canonical_work_order_packet_id"] == successor.payload[
        "packet_id"
    ]
    successor_dir = Path(str(successor.payload["packet_dir"]))
    unit_map = read_payload(successor_dir / "object_motion_target_unit_map.json")
    unit_two = next(unit for unit in unit_map["target_units"] if unit["unit_id"] == "tactile_unit_002")
    assert unit_two["source_unit_role"] == "surface_residue_disturbance"
    assert "surface" in unit_two["current_physical_relation"]
    assert "fall" not in unit_two["current_physical_relation"]


def test_residual_work_order_tactile_units_derive_from_synthetic_artifacts(tmp_path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    candidate_dir = Path(str(chain["object_event"]["packet_dir"]))
    synthetic_text = "\n\n".join(
        [
            "Opening record remains protected.",
            "The first return stays quiet.",
            "The proof pressure waits elsewhere.",
            "A lamp leans against the hinge. When the key presses under its brass edge, the paper buckles and keeps the dent before anyone names the cause.",
            "The bowl rests on the cord; the cord resists, and the wax line drags across the tile as a visible consequence.",
            "Proof region remains untouched.",
            "No outside answer enters.",
            "The room keeps its answer local.",
            "The final return remains protected.",
            "The table returns without explanation.",
            "The ending is unchanged.",
        ]
    )

    def _replace_text(payload):
        payload["text"] = synthetic_text
        payload["text_sha256"] = sha256_text(synthetic_text)
        payload["word_count"] = len(synthetic_text.split())

    rewrite_payload(candidate_dir / "macro_recomposed_candidate_text.json", _replace_text)

    work_order_path = candidate_dir / "macro_recomposition_work_order.json"
    if work_order_path.exists():

        def _replace_units(payload):
            payload["target_units"] = [
                {
                    "unit_id": "synthetic_source_unit_001",
                    "before_text": "When the key presses under its brass edge, the paper buckles.",
                    "objects": ["lamp", "hinge", "key", "paper"],
                },
                {
                    "unit_id": "synthetic_source_unit_002",
                    "before_text": "The bowl rests on the cord; the cord resists.",
                    "objects": ["bowl", "cord", "wax", "tile"],
                },
            ]

        rewrite_payload(work_order_path, _replace_units)

    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=TACTILE_INEVITABILITY_TARGET_ID,
        operator_reviewed=True,
    )
    result = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )

    assert result.exit_code == 0
    packet_dir = Path(str(result.payload["packet_dir"]))
    unit_map = read_payload(packet_dir / "object_motion_target_unit_map.json")
    labels = {
        label
        for unit in unit_map["target_units"]
        for label in unit["involved_object_labels"]
    }
    assert {"lamp", "key", "paper"} & labels
    assert {"cup", "ring", "crumb"}.isdisjoint(labels)
    assert unit_map["target_unit_count"] > 0


def test_residual_work_order_tactile_refuses_missing_material_relation(tmp_path):
    chain = build_residual_target_selection_ready_chain(tmp_path)
    candidate_dir = Path(str(chain["object_event"]["packet_dir"]))
    generic_text = "\n\n".join(
        [
            "Opening remains.",
            "Return remains.",
            "Proof remains.",
            "The room is vivid and beautiful. The scene has many colors and feelings.",
            "The paragraph explains that everything matters without a material relation.",
            "Proof remains protected.",
            "No answer enters.",
            "The room keeps still.",
            "Final return remains.",
            "The end remains.",
            "Done.",
        ]
    )

    def _replace_text(payload):
        payload["text"] = generic_text
        payload["text_sha256"] = sha256_text(generic_text)
        payload["word_count"] = len(generic_text.split())

    rewrite_payload(candidate_dir / "macro_recomposed_candidate_text.json", _replace_text)
    work_order_path = candidate_dir / "macro_recomposition_work_order.json"
    if work_order_path.exists():

        def _remove_units(payload):
            payload["target_units"] = []

        rewrite_payload(work_order_path, _remove_units)

    selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=Path(str(chain["selection_strategy"]["packet_dir"])),
        target=TACTILE_INEVITABILITY_TARGET_ID,
        operator_reviewed=True,
    )
    result = run_residual_work_order_planning(
        chain["config"],
        selection_packet=Path(str(selection.payload["packet_dir"])),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "tactile inevitability adapter failed stop-test" in result.payload["message"]
    assert "no concrete tactile relation identified" in result.payload["message"]
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False


def test_residual_work_order_accepts_object_motion_selection_and_stays_fail_closed(
    tmp_path,
):
    chain = build_residual_work_order_ready_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_work_order_planning(
        config,
        selection_packet=Path(str(chain["residual_target_selection"]["packet_dir"])),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["selected_residual_target_id"] == (
        OBJECT_MOTION_CAUSALITY_TARGET_ID
    )
    assert result.payload["selected_region_id"] == (
        RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    )
    assert result.payload["target_unit_count"] >= 3
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_generation_authorized"] is False
    assert result.payload["future_generation_contract_created"] is True
    assert result.payload["next_allowed_action"] == (
        RESIDUAL_WORK_ORDER_NEXT_RECOMMENDED_ACTION
    )
    assert result.payload["next_recommended_action"] == (
        RESIDUAL_WORK_ORDER_NEXT_RECOMMENDED_ACTION
    )
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True

    packet_dir = Path(str(result.payload["packet_dir"]))
    assert packet_dir.parent.name == "residual_work_order"
    assert {artifact.type for artifact in result.artifacts} == set(
        RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    )

    for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES:
        envelope = json.loads(
            (packet_dir / f"{artifact_type}.json").read_text(encoding="utf-8")
        )
        assert envelope["artifact_type"] == artifact_type
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is None

    subject = read_payload(packet_dir / "residual_work_order_subject_manifest.json")
    assert subject["source_selection_packet_id"] == chain["residual_target_selection"][
        "packet_id"
    ]
    assert subject["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert subject["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert subject["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert subject["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert subject["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert subject["candidate_generated"] is False

    intake = read_payload(packet_dir / "residual_target_selection_intake.json")
    assert intake["selection_packet_consumed"] is True
    assert intake["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert intake["next_strategy_or_work_order_authorized"] is True
    assert intake["candidate_generation_authorized"] is False
    assert intake["live_model_call_authorized"] is False

    inventory = read_payload(packet_dir / "current_candidate_region_inventory.json")
    region_ids = {region["region_id"] for region in inventory["regions"]}
    assert "opening_table_dust_spoon_saucer_ring_field" in region_ids
    assert RESIDUAL_WORK_ORDER_SELECTED_REGION_ID in region_ids
    assert "proof_no_outside_answer_region" in region_ids
    assert "final_return_opening_transformation_region" in region_ids
    selected_inventory_region = [
        region
        for region in inventory["regions"]
        if region["region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    ][0]
    assert selected_inventory_region[
        "eligible_for_object_motion_causality_specificity_work"
    ] is True

    diagnostic = read_payload(packet_dir / "object_motion_causality_diagnostic.json")
    categories = {
        finding["category"] for finding in diagnostic["diagnostic_findings"]
    }
    assert "object_motion_with_consequence" in categories
    assert "object_state_without_motion" in categories
    assert "decorative_object_detail" in categories
    assert "abstract_explanation_of_causality" in categories
    assert "object_lists" in categories
    assert "rival_mimicry_risk" in categories
    assert diagnostic["likely_strongest_candidate_region"] == (
        RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    )

    selected_region = read_payload(packet_dir / "selected_intervention_region.json")
    assert selected_region["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert selected_region["selected_region_before_text"]
    assert (
        len(selected_region["selected_region_before_text"])
        < len(read_payload(
            Path(str(chain["object_event"]["packet_dir"]))
            / "macro_recomposed_candidate_text.json"
        )["text"])
    )
    assert selected_region["region_change_authorized_later"] is True
    assert selected_region["region_change_authorized_now"] is False

    unit_map = read_payload(packet_dir / "object_motion_target_unit_map.json")
    assert unit_map["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert unit_map["target_unit_count"] >= 3
    unit_ids = {unit["unit_id"] for unit in unit_map["target_units"]}
    assert "unit_001_cup_ring_crumb" in unit_ids
    assert "unit_003_spoon_saucer_fall" in unit_ids
    for unit in unit_map["target_units"]:
        assert unit["before_text_sha256"]
        assert unit["material_change_required"] is True
        assert "add decorative detail" in unit["forbidden_operation"]
        assert "full rewrite" in unit["forbidden_operation"]

    contract = read_payload(packet_dir / "future_generation_contract.json")
    assert contract["future_generation_contract_created"] is True
    assert contract["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert contract["must_use_base_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert contract["future_generation_requires_separate_authorization"] is True
    assert contract["candidate_generation_authorized"] is False
    assert contract["live_model_call_authorized"] is False
    assert "add decorative vividness" in contract["must_not"]
    assert "mimic rival" in contract["must_not"]

    plan = read_payload(packet_dir / "ablation_and_reader_eval_plan.json")
    assert "revert_object_motion_causality_intervention" in plan[
        "future_ablation_controls"
    ]
    assert "object_list_no_causal_motion_control" in plan["future_ablation_controls"]
    assert "first-read causal specificity" in plan["future_reader_state_eval_focus"]
    assert plan["ablation_authorized"] is False
    assert plan["reader_state_eval_authorized"] is False

    gate = read_payload(packet_dir / "residual_work_order_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "selection_packet_consumed",
        "selected_target_valid",
        "current_best_candidate_loaded",
        "candidate_region_inventory_created",
        "selected_region_chosen",
        "target_unit_map_created",
        "future_generation_contract_created",
        "ablation_and_reader_eval_plan_created",
        "no_candidate_generated",
        "no_openai_calls",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "candidate_generation_authorized",
        "live_model_call_authorized",
        "ablation_authorized",
        "reader_state_eval_authorized",
        "finalization_eligible",
        "strongest_rival_defeated",
        "human_validation_present",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False

    packet = read_payload(packet_dir / "residual_work_order_packet.json")
    assert packet["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert packet["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert packet["target_unit_count"] >= 3
    assert packet["candidate_generation_authorized"] is False
    assert packet["future_generation_contract_created"] is True
    assert packet["counts"]["model_calls"] == 0
    assert packet["counts"]["candidate_artifacts_created"] == 0
    assert packet["counts"]["produced_artifacts"] == len(
        RESIDUAL_WORK_ORDER_ARTIFACT_TYPES
    )
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_residual_generation_authorization_refuses_without_operator_review(tmp_path):
    chain = build_residual_generation_authorization_ready_chain(tmp_path)

    result = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=False,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "--operator-reviewed" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["generation_authorized"] is False
    assert result.payload["generation_attempt_budget"] == 0
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False


def test_residual_generation_authorization_refuses_missing_work_order_packet(tmp_path):
    config = config_for(tmp_path)

    result = run_residual_generation_authorization(
        config,
        work_order_packet=tmp_path / "missing_work_order_packet",
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "directory not found" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["generation_authorized"] is False


def test_residual_generation_authorization_refuses_invalid_target(tmp_path):
    chain = build_residual_generation_authorization_ready_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_residual_work_order_target"
    shutil.copytree(Path(str(chain["residual_work_order"]["packet_dir"])), invalid_packet)

    def _wrong_target(payload):
        payload["selected_residual_target_id"] = "proof_no_answer_residue"

    rewrite_payload(invalid_packet / "residual_work_order_packet.json", _wrong_target)

    result = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=invalid_packet,
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "selected residual target" in result.payload["message"]
    assert result.payload["generation_authorized"] is False
    assert result.payload["candidate_generated"] is False


def test_residual_generation_authorization_refuses_missing_selected_region_hash(
    tmp_path,
):
    chain = build_residual_generation_authorization_ready_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_residual_work_order_missing_region_hash"
    shutil.copytree(Path(str(chain["residual_work_order"]["packet_dir"])), invalid_packet)

    def _remove_region_hash(payload):
        payload["selected_region_sha256"] = ""

    rewrite_payload(
        invalid_packet / "selected_intervention_region.json",
        _remove_region_hash,
    )

    result = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=invalid_packet,
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "selected region SHA is missing" in result.payload["message"]
    assert result.payload["generation_authorized"] is False


def test_residual_generation_authorization_refuses_missing_target_unit_map(
    tmp_path,
):
    chain = build_residual_generation_authorization_ready_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_residual_work_order_missing_units"
    shutil.copytree(Path(str(chain["residual_work_order"]["packet_dir"])), invalid_packet)

    def _remove_target_units(payload):
        payload["target_units"] = []
        payload["target_unit_count"] = 0

    rewrite_payload(
        invalid_packet / "object_motion_target_unit_map.json",
        _remove_target_units,
    )

    result = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=invalid_packet,
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "target unit map is missing" in result.payload["message"]
    assert result.payload["generation_authorized"] is False


def test_residual_generation_authorization_accepts_one_bounded_attempt(
    tmp_path,
):
    chain = build_residual_generation_authorization_ready_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_generation_authorization(
        config,
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["selected_residual_target_id"] == (
        OBJECT_MOTION_CAUSALITY_TARGET_ID
    )
    assert result.payload["selected_region_id"] == (
        RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    )
    assert result.payload["selected_region_sha256"]
    assert result.payload["target_unit_count"] == 3
    assert result.payload["generation_authorized"] is True
    assert result.payload["generation_attempt_budget"] == 1
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["live_model_call_authorized_for_generation"] is True
    assert result.payload["ablation_authorized"] is False
    assert result.payload["reader_state_eval_authorized"] is False
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["model_calls"] == 0
    assert result.payload["next_recommended_action"] == (
        RESIDUAL_GENERATION_AUTHORIZATION_NEXT_ACTION
    )

    packet_dir = Path(str(result.payload["packet_dir"]))
    assert packet_dir.parent.name == "residual_generation_authorization"
    assert {artifact.type for artifact in result.artifacts} == set(
        RESIDUAL_GENERATION_AUTHORIZATION_ARTIFACT_TYPES
    )
    for artifact_type in RESIDUAL_GENERATION_AUTHORIZATION_ARTIFACT_TYPES:
        envelope = json.loads(
            (packet_dir / f"{artifact_type}.json").read_text(encoding="utf-8")
        )
        assert envelope["artifact_type"] == artifact_type
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is None

    subject = read_payload(
        packet_dir / "residual_generation_authorization_subject_manifest.json"
    )
    assert subject["source_work_order_packet_id"] == chain["residual_work_order"][
        "packet_id"
    ]
    assert subject["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert subject["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert subject["target_unit_count"] == 3
    assert set(subject["target_unit_ids"]) == {
        "unit_001_cup_ring_crumb",
        "unit_002_dust_hand_foot_air",
        "unit_003_spoon_saucer_fall",
    }

    review = read_payload(packet_dir / "operator_work_order_review_record.json")
    assert review["operator_reviewed"] is True
    assert review["decision"] == AUTHORIZATION_DECISION_AUTHORIZE_ONE
    assert review["generation_authorized"] is True
    assert review["generation_attempt_budget"] == 1

    scope = read_payload(packet_dir / "generation_scope_authorization.json")
    assert scope["generation_authorized"] is True
    assert scope["authorization_consumed"] is False
    assert scope["authorized_base_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert scope["authorized_selected_region_id"] == (
        RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    )
    assert "add decorative vividness" in scope["must_not"]
    assert "claim phase shift" in scope["must_not"]

    budget = read_payload(packet_dir / "generation_attempt_budget.json")
    assert budget["generation_attempt_budget"] == 1
    assert budget["remaining_generation_attempts"] == 1
    assert budget["authorization_consumed"] is False
    assert budget["max_model_calls_for_future_generation"] == 1
    assert budget["open_ended_generation_authorized"] is False
    assert budget["repeated_generation_authorized"] is False

    policy = read_payload(packet_dir / "target_unit_integration_policy.json")
    assert policy["future_generator_must_produce_one_bounded_replacement"] is True
    assert policy["overlapping_units_must_be_reconciled"] is True
    assert "unit_002_dust_hand_foot_air" in " ".join(policy["overlap_notes"])
    assert "add a new object list" in policy["must_not"]
    assert "alter nonselected regions" in policy["must_not"]

    contract = read_payload(packet_dir / "future_generator_contract_ref.json")
    assert contract["authorization_packet_id"] == result.payload["packet_id"]
    assert contract["work_order_packet_id"] == chain["residual_work_order"][
        "packet_id"
    ]
    assert contract["generation_attempt_budget"] == 1
    assert contract["authorization_consumed"] is False
    assert "executed ablation" in contract["required_after_generation"]
    assert "reader-state evaluation" in contract["required_after_generation"]
    assert "evidence synthesis" in contract["required_after_generation"]
    assert "phase-shift claim" in contract["forbidden"]

    gate = read_payload(packet_dir / "authorization_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "work_order_packet_consumed",
        "operator_review_recorded",
        "work_order_validated",
        "one_generation_attempt_authorized",
        "base_candidate_identified",
        "selected_region_identified",
        "selected_region_hash_recorded",
        "target_units_identified",
        "target_unit_integration_policy_recorded",
        "protected_effects_recorded",
        "no_candidate_generated",
        "no_openai_calls",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "candidate_generated",
        "authorization_consumed",
        "ablation_authorized",
        "reader_state_eval_authorized",
        "synthesis_authorized",
        "finalization_eligible",
        "strongest_rival_defeated",
        "human_validation_present",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["generation_authorized"] is True
    assert gate["generation_attempt_budget"] == 1
    assert gate["authorization_consumed"] is False
    assert gate["candidate_generated"] is False
    assert gate["model_calls"] == 0
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["strongest_rival_still_blocks"] is True

    packet = read_payload(packet_dir / "residual_generation_authorization_packet.json")
    assert packet["generation_authorized"] is True
    assert packet["generation_attempt_budget"] == 1
    assert packet["authorization_consumed"] is False
    assert packet["candidate_generated"] is False
    assert packet["counts"]["model_calls"] == 0
    assert packet["counts"]["candidate_artifacts_created"] == 0
    assert packet["counts"]["produced_artifacts"] == len(
        RESIDUAL_GENERATION_AUTHORIZATION_ARTIFACT_TYPES
    )
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_tactile_generation_authorization_records_target_contract(tmp_path):
    chain = build_tactile_residual_work_order_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_generation_authorization(
        config,
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["target_adapter_id"] == "tactile_inevitability"
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["generation_authorized"] is True
    assert result.payload["generation_attempt_budget"] == 1
    assert result.payload["candidate_generated"] is False
    packet_dir = Path(str(result.payload["packet_dir"]))
    contract = read_payload(packet_dir / "residual_generation_contract.json")
    assert contract["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert contract["generation_schema_name"] == RESIDUAL_INTERVENTION_GENERATION_SCHEMA.name
    assert contract["one_attempt_budget"] == 1
    assert contract["generation_authorized"] is True
    assert contract["model_calls"] == 0
    assert "full_tactile_intervention" in contract["target_specific_ablation_controls"]
    assert "first-read physical inevitability" in contract[
        "target_specific_reader_state_focus"
    ]
    assert all(unit["unit_id"].startswith("tactile_unit_") for unit in contract["authoritative_target_units"])

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_hostile_scaffold_generation_authorization_uses_real_contract(tmp_path):
    chain = build_hostile_scaffold_residual_work_order_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_generation_authorization(
        config,
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == (
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    )
    assert result.payload["generation_contract_version"] != "placeholder_1"
    assert result.payload["materiality_policy_id"] == (
        HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID
    )
    assert result.payload["generation_authorized"] is True
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["previous_placeholder_authorization_packet_id"] is None

    packet_dir = Path(str(result.payload["packet_dir"]))
    contract = read_payload(packet_dir / "residual_generation_contract.json")
    assert contract["generation_contract_version"] != "placeholder_1"
    assert contract["materiality_policy_id"] == HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID
    assert contract["materiality_policy"]["primary_materiality_scope"] == (
        "target_bearing_scope"
    )
    assert "semantic_validation_contract" in contract
    assert "materially address all five target units" in " ".join(
        contract["prompt_instructions"]
    )
    policy = read_payload(packet_dir / "target_unit_integration_policy.json")
    assert policy["materiality_policy"]["policy_id"] == (
        HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID
    )
    assert "generic vividness" in " ".join(policy["semantic_validation_contract"])
    packet = read_payload(packet_dir / "residual_generation_authorization_packet.json")
    assert packet["generation_contract_version"] != "placeholder_1"
    assert packet["materiality_policy_id"] == HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID
    assert payload_has_placeholder_generation_contract(packet) is False

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_ending_return_generation_authorization_uses_real_handoff_contract(tmp_path):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_generation_authorization(
        config,
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == (
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    )
    assert result.payload["selected_region_id"] == ENDING_RETURN_REGION_ID
    assert result.payload["target_adapter_id"] == "ending_return_risk"
    assert result.payload["generation_contract_version"] == (
        ENDING_RETURN_GENERATION_CONTRACT_VERSION
    )
    assert result.payload["materiality_policy_id"] == ENDING_RETURN_MATERIALITY_POLICY_ID
    assert result.payload["semantic_validator_id"] == ENDING_RETURN_SEMANTIC_VALIDATOR_ID
    assert result.payload["target_unit_count"] == 5
    assert result.payload["generation_authorized"] is True
    assert result.payload["generation_attempt_budget"] == 1
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True

    packet_dir = Path(str(result.payload["packet_dir"]))
    scope = read_payload(packet_dir / "generation_scope_authorization.json")
    assert scope["authorized_selected_region_id"] == ENDING_RETURN_REGION_ID
    assert scope["generation_authorized"] is True
    assert scope["authorization_consumed"] is False
    policy = read_payload(packet_dir / "target_unit_integration_policy.json")
    assert policy["target_unit_overlap_cluster_report"]["overlap_cluster_count"] >= 2
    assert policy["materiality_policy"]["policy_id"] == ENDING_RETURN_MATERIALITY_POLICY_ID
    contract = read_payload(packet_dir / "residual_generation_contract.json")
    assert contract["generation_contract_version"] == (
        ENDING_RETURN_GENERATION_CONTRACT_VERSION
    )
    assert contract["target_unit_overlap_cluster_report"][
        "overlap_cluster_count"
    ] >= 2
    assert "full_ending_return_intervention" in contract[
        "target_specific_ablation_controls"
    ]
    assert "object-field return preservation" in contract[
        "target_specific_reader_state_focus"
    ]
    gate = read_payload(packet_dir / "authorization_gate_report.json")
    gates = {item["gate_name"]: item for item in gate["gate_results"]}
    assert gates["selected_region_identified"]["passed"] is True
    assert gate["generation_authorized"] is True
    assert gate["model_calls"] == 0
    packet = read_payload(packet_dir / "residual_generation_authorization_packet.json")
    assert packet["generation_authorized"] is True
    assert packet["authorization_consumed"] is False
    assert packet["candidate_generated"] is False
    assert payload_has_placeholder_generation_contract(packet) is False

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_ending_return_planning_only_work_order_refuses_authorization(tmp_path):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    stale_packet_dir = Path(str(chain["residual_work_order"]["packet_dir"]))

    def _make_placeholder(payload):
        payload["generation_contract_version"] = (
            ENDING_RETURN_PLACEHOLDER_GENERATION_CONTRACT_VERSION
        )
        payload["materiality_policy_id"] = (
            ENDING_RETURN_PLACEHOLDER_MATERIALITY_POLICY_ID
        )

    for artifact_type in RESIDUAL_WORK_ORDER_ARTIFACT_TYPES:
        rewrite_payload(stale_packet_dir / f"{artifact_type}.json", _make_placeholder)

    result = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=stale_packet_dir,
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "placeholder generation metadata" in result.payload["message"]
    assert result.payload["generation_authorized"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 0


def test_hostile_scaffold_placeholder_adapter_refuses_authorization(
    tmp_path,
    monkeypatch,
):
    chain = build_hostile_scaffold_residual_work_order_chain(tmp_path)
    adapter = require_residual_target_adapter(HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID)
    placeholder_policy = replace(
        adapter.materiality_policy,
        policy_id=HOSTILE_SCAFFOLD_PLACEHOLDER_MATERIALITY_POLICY_ID,
    )
    monkeypatch.setitem(
        residual_targets_module.RESIDUAL_TARGET_ADAPTERS,
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        replace(
            adapter,
            generation_contract_version="placeholder_1",
            materiality_policy=placeholder_policy,
        ),
    )

    result = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "generation readiness failed" in result.payload["message"]
    assert "placeholder-only" in result.payload["message"]
    assert result.payload["generation_authorized"] is False
    assert result.payload["candidate_generated"] is False


def test_hostile_scaffold_placeholder_authorization_is_historical_not_authoritative(
    tmp_path,
):
    chain = build_hostile_scaffold_residual_work_order_chain(tmp_path)
    config = chain["config"]
    first = run_residual_generation_authorization(
        config,
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert first.exit_code == 0
    first_dir = Path(str(first.payload["packet_dir"]))

    def _make_placeholder(payload):
        payload["generation_contract_version"] = "placeholder_1"
        payload["materiality_policy_id"] = (
            HOSTILE_SCAFFOLD_PLACEHOLDER_MATERIALITY_POLICY_ID
        )

    rewrite_payload(first_dir / "residual_generation_authorization_packet.json", _make_placeholder)

    second = run_residual_generation_authorization(
        config,
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )

    assert second.exit_code == 0
    assert second.payload["accepted"] is True
    assert second.payload["packet_id"] != first.payload["packet_id"]
    assert second.payload["previous_placeholder_authorization_packet_id"] == (
        first.payload["packet_id"]
    )
    assert second.payload[
        "previous_placeholder_authorization_not_generation_authoritative"
    ] is True
    assert second.payload["supersedes_placeholder_authorization_for_target"] is True
    assert second.payload["supersession_reason"] == (
        "hostile scaffold generation contract was placeholder-only"
    )
    second_dir = Path(str(second.payload["packet_dir"]))
    packet = read_payload(second_dir / "residual_generation_authorization_packet.json")
    assert packet["previous_placeholder_authorization_packet_id"] == (
        first.payload["packet_id"]
    )
    assert packet["generation_contract_version"] != "placeholder_1"
    assert packet["materiality_policy_id"] == HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID
    assert payload_has_placeholder_generation_contract(packet) is False

    refused = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=first_dir,
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory([]),
    )
    assert refused.exit_code == 1
    assert refused.payload["accepted"] is False
    assert "placeholder generation contract" in refused.payload["message"]
    assert refused.payload["authorization_consumed"] is False
    assert refused.payload["candidate_generated"] is False
    assert refused.payload["counts"]["model_calls"] == 0


def test_hostile_scaffold_residual_candidate_openai_refuses_without_allow_live(
    tmp_path,
):
    chain = build_hostile_scaffold_residual_candidate_authorization_chain(tmp_path)
    clients = []

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=False,
        client_factory=residual_intervention_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "--allow-live-model" in result.payload["message"]
    assert clients == []
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["candidate_generated"] is False


def test_ending_return_residual_candidate_openai_refuses_without_allow_live(
    tmp_path,
):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    assert authorization.payload["accepted"] is True
    clients = []

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(str(authorization.payload["packet_dir"])),
        allow_live_model=False,
        client_factory=residual_intervention_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "--allow-live-model" in result.payload["message"]
    assert clients == []
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False


def test_ending_return_reset_diagnostic_distinguishes_negated_reset_language():
    valid = (
        "Morning returns to the same table. The opening is altered by the "
        "record on the surface, and nothing resets when the dust and ring carry "
        "proof as pressure."
    )
    diagnostic = ending_return_reset_diagnostic(replacement_text=valid)
    assert diagnostic["failed"] is False

    invalid_examples = [
        ("The scene is cleared and reset.", "explicit_reset_wording"),
        ("The table is wiped clean before the return.", "erase_clearing_semantics"),
        ("The room restarted as if made new.", "explicit_reset_wording"),
        ("The return leaves everything same as before.", "return_as_repeat_semantics"),
        ("The proof now answers itself.", "controller_overreach"),
    ]
    for text, failure_class in invalid_examples:
        diagnostic = ending_return_reset_diagnostic(replacement_text=text)
        assert diagnostic["failed"] is True
        assert diagnostic["reset_failure_class"] == failure_class
        assert diagnostic["likely_offending_span"]
        assert diagnostic["likely_offending_phrase"]


def test_ending_return_packet_0068_like_uses_ending_labels_and_valid_no_reset_language(
    tmp_path,
    monkeypatch,
):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    authorization_packet = Path(str(authorization.payload["packet_dir"]))
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-ending-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="ending_packet_0068_like",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == (
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    )
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["candidate_generated"] is True
    diff_payload = read_payload(
        Path(str(result.payload["packet_dir"])) / "macro_recomposition_diff_report.json"
    )
    materiality_report = diff_payload["materiality_report"]
    validation = materiality_report["residual_intervention_validation_report"]
    assert validation["passed"] is True
    assert validation["unit_semantics_passed"] is True
    assert validation["global_semantic_failure"] is False
    reset_report = materiality_report["ending_return_reset_diagnostic"]
    assert reset_report["failed"] is False

    unit_report = materiality_report["target_unit_materiality_report"]
    classifications = {unit["classification"] for unit in unit_report["units"]}
    assert "strong_tactile_intervention" not in classifications
    assert all("tactile" not in label for label in classifications)
    assert classifications <= {
        "strong_return_enactment",
        "no_reset_pressure_preserved",
        "object_field_return_preserved",
        "proof_no_answer_carry_preserved",
        "opening_return_relation_preserved",
    }
    assert "no_reset_pressure_preserved" in classifications

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_ending_return_packet_0069_like_fails_with_global_relation_alignment(
    tmp_path,
    monkeypatch,
):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    authorization_packet = Path(str(authorization.payload["packet_dir"]))
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-ending-model",
        client_factory=residual_intervention_stub_factory(
            [],
            mode="ending_packet_0069_like",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]

    categories = result.payload["validation_failure_categories"]
    assert "opening_return_relation_failures" in categories
    failure_text = " ".join(categories["opening_return_relation_failures"])
    assert "global_failure_class=explicit_negated_explanation" in failure_text
    assert "does not arrive as an explanation" in failure_text

    global_report = result.payload["ending_return_global_relation_report"]
    assert global_report["global_relation_passed"] is False
    assert global_report["global_failure_class"] == "explicit_negated_explanation"
    assert "does not arrive as an explanation" in global_report[
        "likely_offending_span_or_phrase"
    ]
    assert global_report["explicit_negated_explanation"] is True
    assert global_report["abstract_pressure_label"] is True
    assert global_report["object_sequence_too_listlike"] is True
    assert global_report["opening_return_stated_not_enacted"] is True
    assert global_report["object_pressure_too_weak"] is True
    assert global_report["proof_no_answer_explained"] is True
    assert global_report["object_field_return_present"] is True
    assert global_report["no_reset_pressure_preserved"] is True
    assert global_report["proof_no_answer_carry_preserved"] is True
    assert global_report[
        "opening_return_relation_enacted_through_object_pressure"
    ] is False

    alignment = result.payload["unit_global_alignment_report"]
    assert alignment["unit_semantics_passed"] is True
    assert alignment["global_relation_passed"] is False
    assert alignment["final_validation_failure_not_captured_by_unit_semantics"] is True
    assert set(alignment["warned_unit_ids"]) >= {
        "final_return_enacts_not_explains",
        "opening_return_relation_without_thesis",
        "same_object_field_returns_without_summary",
        "proof_no_answer_carry_preserved",
    }

    validation = result.payload["residual_intervention_validation_report"]
    assert validation["passed"] is False
    assert validation["unit_semantics_passed"] is True
    assert validation["global_semantic_failure"] is True
    assert validation["ending_return_global_relation_report"]["global_relation_passed"] is False
    assert validation["unit_global_alignment_report"]["warnings_attached_to_unit_reports"] is True

    unit_report = result.payload["target_unit_materiality_report"]
    by_unit = {
        unit["target_unit_id"]: unit
        for unit in unit_report["units"]
    }
    classifications = {unit["classification"] for unit in unit_report["units"]}
    assert "strong_tactile_intervention" not in classifications
    assert all("tactile" not in label for label in classifications)
    assert by_unit["final_return_enacts_not_explains"]["semantic_passed"] is True
    assert any(
        warning["warning_class"] == "explicit_negated_explanation"
        for warning in by_unit["final_return_enacts_not_explains"]["semantic_warnings"]
    )
    assert any(
        warning["warning_class"] == "opening_return_stated_not_enacted"
        for warning in by_unit[
            "opening_return_relation_without_thesis"
        ]["semantic_warnings"]
    )
    assert any(
        warning["warning_class"] == "object_sequence_too_listlike"
        for warning in by_unit[
            "same_object_field_returns_without_summary"
        ]["semantic_warnings"]
    )

    budget = read_payload(authorization_packet / "generation_attempt_budget.json")
    packet = read_payload(
        authorization_packet / "residual_generation_authorization_packet.json"
    )
    assert budget["authorization_consumed"] is False
    assert packet["authorization_consumed"] is False

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_ending_return_clearing_reset_language_fails_with_global_diagnostic(
    tmp_path,
    monkeypatch,
):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    authorization_packet = Path(str(authorization.payload["packet_dir"]))
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-ending-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="ending_clearing_reset",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]

    categories = result.payload["validation_failure_categories"]
    assert "no_reset_return_pressure_failures" in categories
    failure_text = " ".join(categories["no_reset_return_pressure_failures"])
    assert "reset_failure_class=explicit_reset_wording" in failure_text
    assert "likely_offending_span=" in failure_text
    reset_report = result.payload["ending_return_reset_diagnostic"]
    assert reset_report["failed"] is True
    assert reset_report["reset_failure_class"] == "explicit_reset_wording"
    assert reset_report["likely_offending_span"]
    assert reset_report["object_field_return_preserved"] is True
    assert reset_report["opening_return_relation_preserved"] is True

    validation = result.payload["residual_intervention_validation_report"]
    assert validation["passed"] is False
    assert validation["unit_semantics_passed"] is True
    assert validation["global_semantic_failure"] is True
    assert validation["final_validation_failure_not_captured_by_unit_semantics"] is True
    assert "no_reset_return_pressure_failures" in validation["global_failure_reason"]

    unit_report = result.payload["target_unit_materiality_report"]
    classifications = {unit["classification"] for unit in unit_report["units"]}
    assert "strong_tactile_intervention" not in classifications
    assert all("tactile" not in label for label in classifications)

    budget = read_payload(authorization_packet / "generation_attempt_budget.json")
    packet = read_payload(
        authorization_packet / "residual_generation_authorization_packet.json"
    )
    assert budget["authorization_consumed"] is False
    assert packet["authorization_consumed"] is False

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_ending_return_strong_stub_passes_with_return_and_altered_opening(
    tmp_path,
    monkeypatch,
):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    authorization_packet = Path(str(authorization.payload["packet_dir"]))
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-ending-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="ending_strong",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["candidate_generated"] is True
    assert result.payload["counts"]["model_calls"] == 1
    prompt = json.loads(clients[0].requests[0].input_text)
    feedback = prompt["ending_return_generation_feedback"]
    assert 'The word "return" is allowed and expected.' in feedback[
        "no_reset_language_feedback"
    ]
    assert any("opening is altered" in item for item in feedback["no_reset_language_feedback"])
    assert any("wiped clean" in item for item in feedback["no_reset_language_feedback"])

    diff_payload = read_payload(
        Path(str(result.payload["packet_dir"])) / "macro_recomposition_diff_report.json"
    )
    materiality_report = diff_payload["materiality_report"]
    validation = materiality_report["residual_intervention_validation_report"]
    assert validation["passed"] is True
    assert validation["unit_semantics_passed"] is True
    assert validation["global_semantic_failure"] is False
    classifications = {
        unit["classification"]
        for unit in materiality_report["target_unit_materiality_report"]["units"]
    }
    assert "strong_tactile_intervention" not in classifications
    assert "strong_return_enactment" in classifications
    assert "opening_return_relation_preserved" in classifications


def test_autonomous_evidence_synthesis_pauses_failed_ending_return_path(
    tmp_path,
    monkeypatch,
):
    chain = build_ending_return_residual_work_order_chain(tmp_path)
    authorization = run_residual_generation_authorization(
        chain["config"],
        work_order_packet=Path(str(chain["residual_work_order"]["packet_dir"])),
        operator_reviewed=True,
        decision=AUTHORIZATION_DECISION_AUTHORIZE_ONE,
    )
    assert authorization.exit_code == 0
    authorization_packet = Path(str(authorization.payload["packet_dir"]))
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    historical_0068_classes = _classify_failed_ending_return_attempt(
        replacement_text=(
            "If it comes, the return passes through the table and the dust, "
            "through the spoon on its side and the saucer with its crack. "
            "Nothing here settles into a reset; proof keeps asking without answering."
        ),
        subject_manifest={},
        work_order={},
        model_call_error_messages=[
            "residual intervention validation failed: ending lets return become reset language"
        ],
    )
    assert "reset_or_clearing_language_failure" in historical_0068_classes

    failed_results = []
    for mode in (
        "ending_clearing_reset",
        "ending_packet_0069_like",
        "ending_packet_0070_like",
    ):
        result = run_residual_candidate_generation(
            chain["config"],
            client_name="openai",
            authorization_packet=authorization_packet,
            allow_live_model=True,
            max_model_calls=1,
            model="stub-ending-model",
            client_factory=residual_intervention_stub_factory([], mode=mode),
        )
        assert result.exit_code == 1
        assert result.payload["accepted"] is False
        assert result.payload["authorization_consumed"] is False
        assert result.payload["candidate_generated"] is False
        assert result.payload["candidate_artifact_id"] is None
        assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]
        failed_results.append(result)

    budget = read_payload(authorization_packet / "generation_attempt_budget.json")
    packet = read_payload(
        authorization_packet / "residual_generation_authorization_packet.json"
    )
    assert budget["authorization_consumed"] is False
    assert packet["authorization_consumed"] is False

    synthesis = run_autonomous_evidence_synthesis(
        chain["config"],
        run_id=chain["run_id"],
    )

    assert synthesis.exit_code == 0
    assert synthesis.payload["accepted"] is True
    packet_dir = Path(str(synthesis.payload["packet_dir"]))

    history = read_payload(packet_dir / "repair_history_table.json")
    failed_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "failed_residual_generation"
        and row["selected_residual_target_id"] == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    ]
    assert len(failed_rows) == 3
    assert all(
        row["source_authorization_packet_id"] == authorization.payload["packet_id"]
        for row in failed_rows
    )
    assert all(
        row["source_work_order_packet_id"] == chain["residual_work_order"]["packet_id"]
        for row in failed_rows
    )
    assert all(row["authorization_consumed"] is False for row in failed_rows)
    assert all(row["candidate_generated"] is False for row in failed_rows)
    assert all(row["candidate_artifact_id"] is None for row in failed_rows)
    assert all(row["not_candidate_evidence"] is True for row in failed_rows)
    assert all(row["ablation_authorized"] is False for row in failed_rows)
    assert all(row["reader_state_evaluation_authorized"] is False for row in failed_rows)
    failure_classes = {
        failure_class
        for row in failed_rows
        for failure_class in row["failure_classes"]
    }
    assert "reset_or_clearing_language_failure" in failure_classes
    assert "explicit_negated_explanation_global_failure" in failure_classes
    assert "object_pressure_too_weak" in failure_classes
    assert "target_unit_exact_copy_regression" in failure_classes

    failed = read_payload(packet_dir / "failed_or_rejected_repairs.json")
    summary = failed["ending_return_failed_generation_path"]
    assert summary["attempted"] is True
    assert summary["failed_attempt_count"] == 3
    assert summary["stop_test_triggered"] is True
    assert summary["target_status"] == "paused_or_exhausted_pending_strategy_review"
    assert summary["generation_retry_recommended"] is False
    assert summary["next_recommended_action"] == (
        "synthesize_failed_ending_return_path_before_new_strategy"
    )
    assert summary["no_accepted_ending_return_candidate_exists"] is True
    assert summary["authorization_still_technically_unconsumed"] is True
    assert summary["should_not_reuse_authorization_without_strategy_review"] is True
    assert summary["source_authorization_packet_id"] == authorization.payload["packet_id"]
    assert summary["source_work_order_packet_id"] == chain["residual_work_order"][
        "packet_id"
    ]
    assert summary["base_candidate_packet_id"]
    assert summary["proof_packet_id"]
    assert summary["reader_state_packet_id"]
    assert summary["repeated_object_pressure_or_global_relation_failure"] is True
    assert summary["latest_target_unit_exact_copy_regression"] is True

    failed_packet_ids = {
        Path(str(result.payload["packet_dir"])).name for result in failed_results
    }
    graph = read_payload(packet_dir / "candidate_evidence_graph.json")
    assert failed_packet_ids.issubset(
        set(graph["failed_residual_generation_packet_ids"])
    )
    assert failed_packet_ids.isdisjoint(set(graph["candidate_packet_ids"]))
    assert all(
        node["not_candidate_evidence"] is True
        for node in graph["failed_residual_generation_nodes"]
        if node["selected_residual_target_id"] == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    )

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == summary["base_candidate_packet_id"]
    assert selected["packet_id"] not in failed_packet_ids
    assert selected["proof_packet_id"] == summary["proof_packet_id"]
    assert selected["reader_state_packet_id"] == summary["reader_state_packet_id"]
    assert selected["selected_candidate_is_final"] is False
    assert selected.get("no_phase_shift_claim", True) is True

    exhausted = read_payload(packet_dir / "exhausted_handle_report.json")
    ending_handle = [
        handle
        for handle in exhausted["handles"]
        if handle["handle"] == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    ][0]
    assert ending_handle["status"] == "paused_or_exhausted_pending_strategy_review"
    assert ending_handle["stop_test_triggered"] is True

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    assert blockers["ending_return_stop_test_triggered"] is True
    assert blockers["ending_return_target_status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    assert blockers["ending_return_next_recommended_action"] == (
        "synthesize_failed_ending_return_path_before_new_strategy"
    )

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "pause_ending_return_generation_path_for_strategy_review"
    )
    assert decision["next_recommended_action"] == (
        "synthesize_failed_ending_return_path_before_new_strategy"
    )
    assert decision["ending_return_retry_recommended"] is False
    assert (
        decision["ending_return_generation_authorization_reuse_recommended"] is False
    )
    decision_text = json.dumps(decision)
    assert "run_one_bounded_residual_intervention_generation" not in decision_text
    assert "reader-state evaluate" not in decision_text
    assert "run_internal_reader_state_evaluation" not in decision_text

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    assert gate["ending_return_failed_generation_path_adjudicated"] is True
    assert gate["ending_return_target_status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    synthesis_packet = read_payload(
        packet_dir / "autonomous_evidence_synthesis_packet.json"
    )
    assert synthesis_packet["best_current_candidate"]["packet_id"] == summary[
        "base_candidate_packet_id"
    ]
    assert synthesis_packet["ending_return_failed_attempt_count"] == 3
    assert synthesis_packet["ending_return_target_status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    status = synthesis_packet["failed_target_status_map"][
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    ]
    assert set(status["failed_packet_ids"]) == failed_packet_ids
    assert status["generation_retry_recommended"] is False
    assert status["failed_packets_are_not_candidate_evidence"] is True
    assert synthesis_packet["finalization_eligible"] is False
    assert synthesis_packet["no_phase_shift_claim"] is True

    loop_review = run_evidence_loop_review(
        chain["config"],
        synthesis_packet=packet_dir,
    )
    assert loop_review.exit_code == 0
    cleanup = run_loop_integrity_cleanup(
        chain["config"],
        loop_review_packet=Path(str(loop_review.payload["packet_dir"])),
        operator_reviewed=True,
    )
    assert cleanup.exit_code == 0
    next_cycle_authorization = run_supervised_cycle_authorization(
        chain["config"],
        loop_cleanup_packet=Path(str(cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )
    assert next_cycle_authorization.exit_code == 0
    strategy = run_next_target_strategy(
        chain["config"],
        authorization_packet=Path(str(next_cycle_authorization.payload["packet_dir"])),
    )
    assert strategy.exit_code == 0
    strategy_status = strategy.payload["failed_target_status_map"][
        ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    ]
    assert strategy_status["target_status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    assert strategy_status["failed_attempt_count"] == 3
    assert strategy_status["generation_retry_recommended"] is False
    strategy_dir = Path(str(strategy.payload["packet_dir"]))
    residual_map = read_payload(strategy_dir / "residual_target_option_map.json")
    ending_option = [
        option
        for option in residual_map["specific_residual_options"]
        if option["option_id"] == ENDING_EXPLAINS_RETURN_RISK_TARGET_ID
    ][0]
    assert ending_option["available_for_operator_selection"] is False
    assert ending_option["candidate_generation_authorized"] is False
    assert ending_option["generation_retry_recommended"] is False
    assert ENDING_EXPLAINS_RETURN_RISK_TARGET_ID not in residual_map[
        "available_option_ids"
    ]

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_hostile_scaffold_fake_fixture_generation_validates_semantics_without_model_calls(
    tmp_path,
):
    chain = build_hostile_scaffold_residual_candidate_authorization_chain(
        tmp_path,
        fixture_only=True,
    )
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_candidate_generation(
        config,
        client_name="fake",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_residual_target_id"] == (
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    )
    assert result.payload["counts"]["model_calls"] == 0
    packet_dir = Path(str(result.payload["packet_dir"]))
    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["fixture_only"] is True
    assert candidate["non_final"] is True
    assert candidate["not_human_validated"] is True
    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    report = diff["materiality_report"]
    assert report["materiality_policy_id"] == HOSTILE_SCAFFOLD_MATERIALITY_POLICY_ID
    assert report["residual_intervention_validation_report"]["passed"] is True
    mapping = report["target_specific_mapping_report"]
    assert mapping["hostile_scaffold_visibility_mapping_exists"] is True
    assert mapping["scaffold_pressure_reduced"] is True
    assert mapping["proof_no_answer_preserved"] is True
    assert mapping["object_field_preserved"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_hostile_scaffold_prompt_exposes_materiality_feedback_and_strong_stub_passes(
    tmp_path,
    monkeypatch,
):
    chain = build_hostile_scaffold_residual_candidate_authorization_chain(
        tmp_path,
        packet_0064_unit_fixture=True,
    )
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="hostile_strong",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert len(clients) == 1
    prompt = json.loads(clients[0].requests[0].input_text)
    feedback = prompt["hostile_scaffold_generation_feedback"]
    thresholds = feedback["active_thresholds"]
    assert thresholds["target_bearing_changed_unique_word_count_floor"] == 8
    assert thresholds["target_bearing_changed_unique_word_ratio_floor"] == 0.10
    assert thresholds["per_unit_changed_unique_word_count_floor"] == 3
    assert thresholds["per_unit_token_edit_distance_floor"] == 4
    assert len(feedback["required_target_units"]) == 5
    assert all(
        unit["target_unit_id"] and unit["before_text"]
        for unit in feedback["required_target_units"]
    )
    ordinary_feedback = [
        unit
        for unit in feedback["required_target_units"]
        if unit["target_unit_id"] == "ordinary_table_no_scaffold_signage"
    ][0]["unit_specific_feedback"]
    assert any('"seems only ordinary" to "is just there"' in item for item in ordinary_feedback)
    assert feedback["unit_specific_feedback"][0]["target_unit_id"] == (
        "ordinary_table_no_scaffold_signage"
    )
    assert "At first, the table is just there." in feedback[
        "unit_specific_feedback"
    ][0]["failure_to_avoid"]
    model_feedback = " ".join(feedback["model_feedback"])
    assert "one-word substitutions are insufficient" in model_feedback
    assert "preserving target sentence architecture is insufficient" in model_feedback
    assert '"seems only ordinary" to "is just there"' in model_feedback
    assert "object sequence carry meaning" in model_feedback
    assert "do not rewrite outside the selected region" in model_feedback
    semantic_feedback = " ".join(feedback["semantic_leakage_feedback"])
    assert "Do not replace one visible thesis with another" in semantic_feedback
    assert "colon-led thesis sentences" in semantic_feedback
    assert "Do not reuse one long object-list sentence" in semantic_feedback
    assert "abstract pressure as a thesis label is not sufficient" in semantic_feedback
    examples = " ".join(
        item["example"] for item in feedback["failure_shapes_from_packet_0064_regression"]
    )
    assert "At first, the table is only ordinary" in examples
    assert "In the small kitchen" in examples

    packet_dir = Path(str(result.payload["packet_dir"]))
    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    report = diff["materiality_report"]["target_unit_materiality_report"]
    assert report["all_required_units_materially_engaged"] is True
    classifications = {unit["classification"] for unit in report["units"]}
    assert classifications == {"strong_scaffold_reduction"}
    assert "strong_tactile_intervention" not in classifications
    ordinary = [
        unit
        for unit in report["units"]
        if unit["target_unit_id"] == "ordinary_table_no_scaffold_signage"
    ][0]
    assert ordinary["materiality"]["token_edit_distance"] >= 4
    assert ordinary["materiality"]["changed_unique_word_count"] >= 3
    assert ordinary["semantic_passed"] is True

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_hostile_scaffold_packet_0066_like_semantic_leakage_and_collapse_fails(
    tmp_path,
    monkeypatch,
):
    chain = build_hostile_scaffold_residual_candidate_authorization_chain(
        tmp_path,
        packet_0064_unit_fixture=True,
    )
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="hostile_packet_0066_like",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_artifact_id"] is None
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]

    validation = result.payload["residual_intervention_validation_report"]
    assert validation["passed"] is False
    categories = result.payload["validation_failure_categories"]
    assert "target_unit_materiality_failures" not in categories
    assert "scaffold_leakage_failures" in categories
    assert "unit_collapse_failures" in categories
    leakage_text = " ".join(categories["scaffold_leakage_failures"])
    assert "abstract_pressure_label" in leakage_text
    assert "thesis_before_object_sequence" in leakage_text
    assert "colon_introduced_explanation" in leakage_text
    assert "object_list_used_as_proof_after_explanatory_lead_in" in leakage_text
    assert "keep their own pressure" in leakage_text

    residual = result.payload["residual_materiality_report"]
    assert residual["whole_region_guard"]["passed"] is True
    assert residual["target_bearing_scope"]["passed"] is True
    unit_report = result.payload["target_unit_materiality_report"]
    assert all(unit["materiality_passed"] for unit in unit_report["units"])
    by_unit = {
        unit["target_unit_id"]: unit
        for unit in unit_report["units"]
    }
    assert by_unit["ordinary_things_strict_without_abstraction"]["classification"] == (
        "target_unit_collapsed_into_neighbor"
    )
    assert by_unit["small_kitchen_rule_plainness_reduction"]["classification"] == (
        "target_unit_collapsed_into_neighbor"
    )
    assert by_unit["ordinary_things_strict_without_abstraction"]["semantic_passed"] is False
    assert by_unit["small_kitchen_rule_plainness_reduction"]["semantic_passed"] is False

    leakage_report = result.payload[
        "hostile_scaffold_semantic_leakage_report"
    ]
    assert leakage_report["failed"] is True
    assert set(leakage_report["leakage_classes"]) >= {
        "abstract_pressure_label",
        "colon_introduced_explanation",
        "thesis_before_object_sequence",
        "object_list_used_as_proof_after_explanatory_lead_in",
    }
    assert any(
        "keep their own pressure" in span
        for span in leakage_report["likely_offending_spans"]
    )
    collapse_report = result.payload["unit_collapse_report"]
    assert collapse_report["unit_collapse_detected"] is True
    assert set(collapse_report["collapsed_target_unit_ids"]) >= {
        "ordinary_things_strict_without_abstraction",
        "small_kitchen_rule_plainness_reduction",
    }

    budget = read_payload(authorization_packet / "generation_attempt_budget.json")
    packet = read_payload(
        authorization_packet / "residual_generation_authorization_packet.json"
    )
    assert budget["authorization_consumed"] is False
    assert packet["authorization_consumed"] is False

    retry = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory([], mode="hostile_strong"),
    )
    assert retry.exit_code == 0
    assert retry.payload["accepted"] is True
    assert retry.payload["candidate_generated"] is True

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_hostile_scaffold_packet_0067_like_aligns_scaffold_leakage_report(
    tmp_path,
    monkeypatch,
):
    chain = build_hostile_scaffold_residual_candidate_authorization_chain(
        tmp_path,
        packet_0064_unit_fixture=True,
    )
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory(
            [],
            mode="hostile_packet_0067_like",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_artifact_id"] is None
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]

    categories = result.payload["validation_failure_categories"]
    assert "target_bearing_materiality_failures" in categories
    assert "scaffold_leakage_failures" in categories
    assert categories["target_bearing_materiality_failures"]
    leakage_report = result.payload["hostile_scaffold_semantic_leakage_report"]
    assert leakage_report["failed"] is True
    assert "semantic_leakage" in leakage_report["failure_modes"]
    assert "target_bearing_under_materiality" in leakage_report["failure_modes"]
    assert "controller_final_validation_failures" in leakage_report
    assert leakage_report["controller_final_validation_failures"]
    assert set(leakage_report["leakage_classes"]) >= {
        "semantic_leakage_and_target_bearing_under_materiality",
    }
    assert any(
        "controller final validation reported scaffold" in diagnostic["reason"]
        for diagnostic in leakage_report["diagnostics"]
    )
    assert leakage_report["likely_offending_spans"]

    budget = read_payload(authorization_packet / "generation_attempt_budget.json")
    packet = read_payload(
        authorization_packet / "residual_generation_authorization_packet.json"
    )
    assert budget["authorization_consumed"] is False
    assert packet["authorization_consumed"] is False

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_hostile_scaffold_packet_0065_like_ordinary_table_sentence_polish_fails(
    tmp_path,
    monkeypatch,
):
    chain = build_hostile_scaffold_residual_candidate_authorization_chain(
        tmp_path,
        packet_0064_unit_fixture=True,
    )
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="hostile_packet_0065_like",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_artifact_id"] is None
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]

    validation = result.payload["residual_intervention_validation_report"]
    assert validation["passed"] is False
    categories = result.payload["validation_failure_categories"]
    failures = " ".join(categories["target_unit_materiality_failures"])
    assert "ordinary_table_no_scaffold_signage" in failures
    assert "token edit distance below floor 3 < 4" in failures
    assert "sentence-polishing / near-synonym" in failures
    assert '"seems ordinary" for "is just there"' in failures

    unit_report = result.payload["target_unit_materiality_report"]
    by_unit = {
        unit["target_unit_id"]: unit
        for unit in unit_report["units"]
    }
    ordinary = by_unit["ordinary_table_no_scaffold_signage"]
    assert ordinary["replacement_excerpt"] == "At first, the table is just there."
    assert ordinary["materiality_passed"] is False
    assert ordinary["classification"] == "valid_direction_but_under_material"
    assert any(
        "sentence-polishing / near-synonym" in failure
        for failure in ordinary["materiality_failures"]
    )
    assert ordinary["classification"] != "strong_tactile_intervention"

    budget = read_payload(authorization_packet / "generation_attempt_budget.json")
    packet = read_payload(
        authorization_packet / "residual_generation_authorization_packet.json"
    )
    assert budget["authorization_consumed"] is False
    assert packet["authorization_consumed"] is False

    retry = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory([], mode="hostile_strong"),
    )
    assert retry.exit_code == 0
    assert retry.payload["accepted"] is True
    assert retry.payload["candidate_generated"] is True

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_hostile_scaffold_packet_0064_like_failure_reports_under_material_units(
    tmp_path,
    monkeypatch,
):
    chain = build_hostile_scaffold_residual_candidate_authorization_chain(
        tmp_path,
        packet_0064_unit_fixture=True,
    )
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="hostile_packet_0064_like",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_artifact_id"] is None
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]

    validation = result.payload["residual_intervention_validation_report"]
    assert validation["passed"] is False
    categories = result.payload["validation_failure_categories"]
    assert "target_unit_materiality_failures" in categories
    unit_report = result.payload["target_unit_materiality_report"]
    by_unit = {
        unit["target_unit_id"]: unit
        for unit in unit_report["units"]
    }
    ordinary = by_unit["ordinary_table_no_scaffold_signage"]
    kitchen = by_unit["small_kitchen_rule_plainness_reduction"]
    assert ordinary["materiality_passed"] is False
    assert kitchen["materiality_passed"] is False
    assert ordinary["classification"] == "valid_direction_but_under_material"
    assert kitchen["classification"] == "valid_direction_but_under_material"
    assert ordinary["classification"] != "strong_tactile_intervention"
    assert kitchen["classification"] != "strong_tactile_intervention"
    assert "At first, the table is only ordinary" in ordinary["replacement_excerpt"]
    assert "In the small kitchen" in kitchen["replacement_excerpt"]

    feedback = result.payload["hostile_scaffold_generation_feedback"]
    labels = set(feedback["diagnostic_labels"])
    assert "strong_scaffold_reduction" in labels
    assert "valid_direction_but_under_material" in labels
    assert "strong_tactile_intervention" not in labels

    budget = read_payload(authorization_packet / "generation_attempt_budget.json")
    packet = read_payload(
        authorization_packet / "residual_generation_authorization_packet.json"
    )
    assert budget["authorization_consumed"] is False
    assert packet["authorization_consumed"] is False

    retry = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-hostile-model",
        client_factory=residual_intervention_stub_factory([], mode="hostile_strong"),
    )
    assert retry.exit_code == 0
    assert retry.payload["accepted"] is True
    assert retry.payload["candidate_generated"] is True

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_pauses_failed_hostile_scaffold_path(
    tmp_path,
    monkeypatch,
):
    chain = build_hostile_scaffold_residual_candidate_authorization_chain(
        tmp_path,
        packet_0064_unit_fixture=True,
    )
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    failed_results = []
    for mode in (
        "hostile_packet_0064_like",
        "hostile_packet_0065_like",
        "hostile_packet_0066_like",
        "hostile_packet_0067_like",
    ):
        result = run_residual_candidate_generation(
            chain["config"],
            client_name="openai",
            authorization_packet=authorization_packet,
            allow_live_model=True,
            max_model_calls=1,
            model="stub-hostile-model",
            client_factory=residual_intervention_stub_factory([], mode=mode),
        )
        assert result.exit_code == 1
        assert result.payload["accepted"] is False
        assert result.payload["authorization_consumed"] is False
        assert result.payload["candidate_generated"] is False
        assert result.payload["candidate_artifact_id"] is None
        assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]
        failed_results.append(result)

    with connect(chain["config"].db_path) as connection:
        before_calls = list_model_calls(connection, run_id=chain["run_id"])

    synthesis = run_autonomous_evidence_synthesis(
        chain["config"],
        run_id=chain["run_id"],
    )

    assert synthesis.exit_code == 0
    assert synthesis.payload["accepted"] is True
    packet_dir = Path(str(synthesis.payload["packet_dir"]))

    history = read_payload(packet_dir / "repair_history_table.json")
    failed_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "failed_residual_generation"
    ]
    assert len(failed_rows) == 4
    assert all(
        row["selected_residual_target_id"] == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
        for row in failed_rows
    )
    assert all(row["authorization_consumed"] is False for row in failed_rows)
    assert all(row["candidate_generated"] is False for row in failed_rows)
    assert all(row["candidate_artifact_id"] is None for row in failed_rows)
    assert all(row["not_candidate_evidence"] is True for row in failed_rows)
    assert all(row["ablation_authorized"] is False for row in failed_rows)
    assert all(row["reader_state_evaluation_authorized"] is False for row in failed_rows)
    failure_sets = {
        row["packet_id"]: set(row["failure_classes"])
        for row in failed_rows
    }
    assert any("broad_materiality_failure" in classes for classes in failure_sets.values())
    assert any(
        "ordinary_table_unit_under_material_failure" in classes
        for classes in failure_sets.values()
    )
    assert any("scaffold_leakage_persisted" in classes for classes in failure_sets.values())
    assert any(
        "target_bearing_ratio_failure" in classes
        for classes in failure_sets.values()
    )

    failed = read_payload(packet_dir / "failed_or_rejected_repairs.json")
    summary = failed["hostile_scaffold_failed_generation_path"]
    assert summary["attempted"] is True
    assert summary["failed_attempt_count"] == 4
    assert summary["stop_test_triggered"] is True
    assert summary["target_status"] == "paused_or_exhausted_pending_strategy_review"
    assert summary["next_recommended_action"] == (
        "synthesize_failed_hostile_scaffold_path_before_new_strategy"
    )
    assert summary["no_accepted_hostile_scaffold_candidate_exists"] is True
    assert summary["authorization_still_technically_unconsumed"] is True
    assert summary["should_not_reuse_authorization_without_strategy_review"] is True
    assert summary["source_authorization_packet_id"] == chain[
        "residual_generation_authorization"
    ]["packet_id"]
    assert summary["source_work_order_packet_id"] == chain["residual_work_order"][
        "packet_id"
    ]

    graph = read_payload(packet_dir / "candidate_evidence_graph.json")
    failed_packet_ids = {
        Path(str(result.payload["packet_dir"])).name for result in failed_results
    }
    assert failed_packet_ids.issubset(
        set(graph["failed_residual_generation_packet_ids"])
    )
    assert failed_packet_ids.isdisjoint(set(graph["candidate_packet_ids"]))
    assert all(
        node["not_candidate_evidence"] is True
        for node in graph["failed_residual_generation_nodes"]
    )

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == summary["base_candidate_packet_id"]
    assert selected["packet_id"] not in failed_packet_ids
    assert selected["selected_candidate_is_final"] is False
    assert selected["selected_candidate_requires_further_testing"] is True
    assert selected.get("no_phase_shift_claim", True) is True

    exhausted = read_payload(packet_dir / "exhausted_handle_report.json")
    hostile_handle = [
        handle
        for handle in exhausted["handles"]
        if handle["handle"] == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    ][0]
    assert hostile_handle["status"] == "paused_or_exhausted_pending_strategy_review"
    assert hostile_handle["stop_test_triggered"] is True

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    assert blockers["hostile_scaffold_stop_test_triggered"] is True
    assert blockers["hostile_scaffold_visibility_target_status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    assert blockers["hostile_scaffold_next_recommended_action"] == (
        "synthesize_failed_hostile_scaffold_path_before_new_strategy"
    )

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "pause_hostile_scaffold_generation_path_for_strategy_review"
    )
    assert decision["next_recommended_action"] == (
        "synthesize_failed_hostile_scaffold_path_before_new_strategy"
    )
    assert decision["hostile_scaffold_retry_recommended"] is False
    assert decision["hostile_scaffold_generation_authorization_reuse_recommended"] is False
    decision_text = json.dumps(decision)
    assert "run_one_bounded_residual_intervention_generation" not in decision_text
    assert "authorize another hostile scaffold generation" not in decision_text
    assert "reader-state evaluate" not in decision_text

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    assert gate["hostile_scaffold_failed_generation_path_adjudicated"] is True
    assert gate["hostile_scaffold_visibility_target_status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["best_current_candidate"]["packet_id"] == summary[
        "base_candidate_packet_id"
    ]
    assert packet["hostile_scaffold_failed_attempt_count"] == 4
    assert packet["hostile_scaffold_visibility_target_status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    assert packet["next_recommended_action"] == (
        "synthesize_failed_hostile_scaffold_path_before_new_strategy"
    )
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    loop_review = run_evidence_loop_review(
        chain["config"],
        synthesis_packet=packet_dir,
    )
    assert loop_review.exit_code == 0
    cleanup = run_loop_integrity_cleanup(
        chain["config"],
        loop_review_packet=Path(str(loop_review.payload["packet_dir"])),
        operator_reviewed=True,
    )
    assert cleanup.exit_code == 0
    authorization = run_supervised_cycle_authorization(
        chain["config"],
        loop_cleanup_packet=Path(str(cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )
    assert authorization.exit_code == 0

    strategy = run_next_target_strategy(
        chain["config"],
        authorization_packet=Path(str(authorization.payload["packet_dir"])),
    )
    assert strategy.exit_code == 0
    assert strategy.payload["accepted"] is True
    assert strategy.payload["source_synthesis_packet_id"] == synthesis.payload["packet_id"]
    assert strategy.payload["source_loop_review_packet_id"] == loop_review.payload[
        "packet_id"
    ]
    assert strategy.payload["source_loop_cleanup_packet_id"] == cleanup.payload[
        "packet_id"
    ]
    assert strategy.payload["source_authorization_packet_id"] == authorization.payload[
        "packet_id"
    ]
    assert strategy.payload["current_best_candidate_packet_id"] == summary[
        "base_candidate_packet_id"
    ]
    assert strategy.payload["proof_packet_id"] == selected["proof_packet_id"]
    assert strategy.payload["reader_state_packet_id"] == selected[
        "reader_state_packet_id"
    ]
    assert strategy.payload["candidate_generated"] is False
    assert strategy.payload["model_calls"] == 0
    assert strategy.payload["counts"]["model_calls"] == 0
    assert HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID in strategy.payload[
        "exhausted_or_attempted_target_ids"
    ]
    failed_status = strategy.payload["failed_target_status_map"][
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    ]
    assert failed_status["target_status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    assert failed_status["failed_attempt_count"] == 4
    assert set(failed_status["failed_packet_ids"]) == failed_packet_ids
    assert failed_status["stop_test_triggered"] is True
    assert failed_status["generation_retry_recommended"] is False
    assert failed_status["next_allowed_status"] == "strategy_review_only"

    strategy_dir = Path(str(strategy.payload["packet_dir"]))
    residual_map = read_payload(strategy_dir / "residual_target_option_map.json")
    hostile_option = [
        option
        for option in residual_map["specific_residual_options"]
        if option["option_id"] == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    ][0]
    assert hostile_option["status"] == (
        "paused_or_exhausted_pending_strategy_review"
    )
    assert hostile_option["available_for_operator_selection"] is False
    assert hostile_option["candidate_generation_authorized"] is False
    assert hostile_option["broad_reuse_authorized"] is False
    assert hostile_option["generation_retry_recommended"] is False
    assert set(hostile_option["failed_packet_ids"]) == failed_packet_ids
    assert HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID not in residual_map[
        "available_option_ids"
    ]
    for option_id in (
        "rival_level_first_read_vividness",
        "proof_no_answer_residue",
        "ending_explains_return_risk",
        "local_busyness_decorative_detail_risk",
    ):
        assert option_id in residual_map["available_option_ids"]

    strategy_packet = read_payload(strategy_dir / "next_target_strategy_packet.json")
    assert strategy_packet["failed_target_status_map"][
        HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID
    ]["failed_packets_are_not_candidate_evidence"] is True
    assert strategy_packet["available_residual_target_ids"] == residual_map[
        "available_option_ids"
    ]

    stale_strategy = tmp_path / "packet_0009_like_stale_hostile_strategy"
    shutil.copytree(strategy_dir, stale_strategy)

    def _make_hostile_look_available(payload):
        payload.pop("failed_target_status_map", None)
        payload["available_option_ids"] = list(payload.get("available_option_ids", []))
        if HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID not in payload["available_option_ids"]:
            payload["available_option_ids"].append(HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID)
        for option in payload["specific_residual_options"]:
            if option["option_id"] == HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID:
                option["status"] = "available_for_operator_selection"
                option["available_for_operator_selection"] = True
                option["broad_reuse_authorized"] = None
                option["operator_may_select_narrower_subtarget"] = False
                option.pop("failed_packet_ids", None)
                option.pop("failed_attempt_count", None)
                option.pop("failure_classes", None)

    rewrite_payload(
        stale_strategy / "residual_target_option_map.json",
        _make_hostile_look_available,
    )
    rewrite_payload(
        stale_strategy / "next_target_strategy_packet.json",
        lambda payload: payload.pop("failed_target_status_map", None),
    )

    stale_selection = run_residual_target_selection(
        chain["config"],
        strategy_packet=stale_strategy,
        target=HOSTILE_SCAFFOLD_VISIBILITY_TARGET_ID,
        operator_reviewed=True,
    )
    assert stale_selection.exit_code == 1
    assert stale_selection.payload["accepted"] is False
    assert "paused/exhausted" in stale_selection.payload["message"]
    assert stale_selection.payload["candidate_generated"] is False
    assert stale_selection.payload["counts"]["model_calls"] == 0

    budget = read_payload(authorization_packet / "generation_attempt_budget.json")
    auth_packet = read_payload(
        authorization_packet / "residual_generation_authorization_packet.json"
    )
    assert budget["authorization_consumed"] is False
    assert auth_packet["authorization_consumed"] is False

    with connect(chain["config"].db_path) as connection:
        after_calls = list_model_calls(connection, run_id=chain["run_id"])
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_residual_candidate_generation_openai_refuses_without_allow_live(tmp_path):
    config = config_for(tmp_path)
    clients = []

    result = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=tmp_path / "missing_authorization",
        allow_live_model=False,
        client_factory=object_motion_causality_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "--allow-live-model" in result.payload["message"]
    assert clients == []
    assert result.payload["counts"]["model_calls"] == 0


def test_residual_candidate_generation_openai_refuses_without_api_key(
    tmp_path,
    monkeypatch,
):
    config = config_for(tmp_path)
    clients = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=tmp_path / "missing_authorization",
        allow_live_model=True,
        client_factory=object_motion_causality_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "OPENAI_API_KEY is not set" in result.payload["message"]
    assert clients == []
    assert result.payload["counts"]["model_calls"] == 0


def test_residual_candidate_generation_fake_refuses_live_authorization(tmp_path):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    config = chain["config"]
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_candidate_generation(
        config,
        client_name="fake",
        authorization_packet=authorization_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "fake mode refuses non-fixture" in result.payload["message"]
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
    assert len(after_calls) == len(before_calls)


def test_residual_candidate_generation_fake_accepts_fixture_authorization(
    tmp_path,
):
    chain = build_residual_candidate_authorization_chain(tmp_path, fixture_only=True)
    config = chain["config"]
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_residual_candidate_generation(
        config,
        client_name="fake",
        authorization_packet=authorization_packet,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["authorization_consumed"] is True
    assert result.payload["candidate_generated"] is True
    assert result.payload["source_authorization_packet_id"] == chain[
        "residual_generation_authorization"
    ]["packet_id"]
    assert result.payload["base_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert result.payload["selected_residual_target_id"] == (
        OBJECT_MOTION_CAUSALITY_TARGET_ID
    )
    assert result.payload["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert result.payload["target_unit_count"] == 3
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))
    assert packet_dir.parent.name == "bounded_macro_recomposition"
    assert {artifact.type for artifact in result.artifacts} == set(
        RESIDUAL_CANDIDATE_ARTIFACT_TYPES
    )

    for artifact_type in RESIDUAL_CANDIDATE_ARTIFACT_TYPES:
        envelope = json.loads(
            (packet_dir / f"{artifact_type}.json").read_text(encoding="utf-8")
        )
        assert envelope["artifact_type"] == artifact_type
        assert envelope["fixture_only"] is True
        assert envelope["model_call_id"] is None

    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["source_authorization_packet_id"] == chain[
        "residual_generation_authorization"
    ]["packet_id"]
    assert candidate["object_motion_causality_generation"] is True
    assert candidate["candidate_only"] is True
    assert candidate["non_final"] is True
    assert candidate["not_human_validated"] is True
    assert candidate["fixture_only"] is True
    assert candidate["finalization_eligible"] is False
    assert "cup comes down" in candidate["text"]

    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    assert diff["target_coverage_report"]["object_motion_causality_mapping_exists"] is True
    assert diff["target_coverage_report"]["no_nonselected_region_edits"] is True
    assert diff["ready_for_executed_ablation"] is True

    gate = read_payload(packet_dir / "macro_recomposition_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "authorization_packet_consumed",
        "work_order_packet_consumed",
        "selected_region_hash_verified",
        "target_units_mapped",
        "one_bounded_replacement_generated",
        "object_motion_causality_mapping_exists",
        "no_nonselected_region_edits",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["strongest_rival_still_blocks"] is True

    packet = read_payload(packet_dir / "macro_recomposition_packet.json")
    assert packet["counts"]["produced_artifacts"] == len(
        RESIDUAL_CANDIDATE_ARTIFACT_TYPES
    )
    assert packet["counts"]["model_calls"] == 0
    assert packet["object_motion_causality_generation"] is True
    assert packet["requires_executed_ablation_before_improvement_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_residual_candidate_generation_refuses_invalid_authorization(tmp_path):
    chain = build_residual_candidate_authorization_chain(tmp_path, fixture_only=True)
    invalid_packet = tmp_path / "invalid_residual_generation_authorization_target"
    shutil.copytree(
        Path(str(chain["residual_generation_authorization"]["packet_dir"])),
        invalid_packet,
    )

    def _wrong_target(payload):
        payload["selected_residual_target_id"] = "proof_no_answer_residue"

    rewrite_payload(
        invalid_packet / "residual_generation_authorization_packet.json",
        _wrong_target,
    )

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="fake",
        authorization_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "selected residual target" in result.payload["message"]
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 0


def test_residual_candidate_generation_refuses_consumed_authorization(tmp_path):
    chain = build_residual_candidate_authorization_chain(tmp_path, fixture_only=True)
    consumed_packet = tmp_path / "consumed_residual_generation_authorization"
    shutil.copytree(
        Path(str(chain["residual_generation_authorization"]["packet_dir"])),
        consumed_packet,
    )

    def _consume(payload):
        payload["authorization_consumed"] = True

    rewrite_payload(
        consumed_packet / "residual_generation_authorization_packet.json",
        _consume,
    )
    rewrite_payload(consumed_packet / "generation_attempt_budget.json", _consume)

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="fake",
        authorization_packet=consumed_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "already consumed" in result.payload["message"]
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False


def test_residual_candidate_generation_refuses_duplicate_authorization_use(tmp_path):
    chain = build_residual_candidate_authorization_chain(tmp_path, fixture_only=True)
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    first = run_residual_candidate_generation(
        chain["config"],
        client_name="fake",
        authorization_packet=authorization_packet,
    )
    assert first.exit_code == 0
    assert first.payload["accepted"] is True

    second = run_residual_candidate_generation(
        chain["config"],
        client_name="fake",
        authorization_packet=authorization_packet,
    )

    assert second.exit_code == 1
    assert second.payload["accepted"] is False
    assert "existing later candidate already references this authorization" in second.payload[
        "message"
    ]
    assert second.payload["authorization_consumed"] is False
    assert second.payload["candidate_generated"] is False


def test_residual_candidate_generation_refuses_selected_region_hash_mismatch(
    tmp_path,
):
    chain = build_residual_candidate_authorization_chain(tmp_path, fixture_only=True)
    invalid_packet = tmp_path / "invalid_residual_generation_authorization_hash"
    shutil.copytree(
        Path(str(chain["residual_generation_authorization"]["packet_dir"])),
        invalid_packet,
    )

    def _bad_hash(payload):
        payload["selected_region_sha256"] = "not-the-selected-region-hash"

    rewrite_payload(
        invalid_packet / "residual_generation_authorization_packet.json",
        _bad_hash,
    )

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="fake",
        authorization_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "selected region text hash does not match" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_residual_candidate_generation_stubbed_openai_success(
    tmp_path,
    monkeypatch,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert len(clients) == 1
    assert len(clients[0].requests) == 1
    prompt = json.loads(clients[0].requests[0].input_text)
    materiality = prompt["materiality_requirement"]
    assert materiality["selected_region_materiality_required"] is True
    assert materiality["replacement_must_be_genuinely_reauthored"] is True
    assert materiality["preserve_protected_effects_not_sentence_architecture"] is True
    assert materiality["lexical_substitutions_are_insufficient"] is True
    assert materiality["target_unit_mappings_are_necessary_but_insufficient"] is True
    assert materiality["required_changed_unique_word_count"] == (
        REQUIRED_CHANGED_UNIQUE_WORD_COUNT
    )
    assert materiality["required_changed_ratio"] == REQUIRED_CHANGED_RATIO
    assert prompt["target_unit_overlap_feedback"][
        "overlapping_units_must_be_reconciled"
    ] is True
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["authorization_consumed"] is True
    assert result.payload["candidate_generated"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))

    model_call = result.payload["model_calls"][0]
    assert model_call["provider"] == "openai"
    assert model_call["model"] == "stub-object-motion-model"
    assert model_call["worker_role"] == WorkerRole.OBJECT_MOTION_CAUSALITY_GENERATOR.value
    assert model_call["schema_name"] == OBJECT_MOTION_CAUSALITY_GENERATION_SCHEMA.name
    assert model_call["status"] == MODEL_CALL_SUCCESS
    assert model_call["parsed_output_artifact_id"] == result.payload["artifact_ids"][
        "macro_patch_or_section_plan"
    ]

    plan_envelope = json.loads(
        (packet_dir / "macro_recomposition_plan.json").read_text(encoding="utf-8")
    )
    patch_envelope = json.loads(
        (packet_dir / "macro_patch_or_section_plan.json").read_text(encoding="utf-8")
    )
    assert plan_envelope["fixture_only"] is False
    assert plan_envelope["model_call_id"] == result.payload["model_call_ids"][0]
    assert patch_envelope["fixture_only"] is False
    assert patch_envelope["model_call_id"] == result.payload["model_call_ids"][0]

    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["source_model_call_id"] == result.payload["model_call_ids"][0]
    assert candidate["fixture_only"] is False
    assert candidate["candidate_only"] is True
    assert candidate["non_final"] is True
    assert candidate["not_human_validated"] is True
    assert candidate["finalization_eligible"] is False
    assert candidate["no_phase_shift_claim"] is True

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_tactile_residual_candidate_generation_fake_fixture_success(tmp_path):
    chain = build_tactile_residual_candidate_authorization_chain(
        tmp_path,
        fixture_only=True,
    )

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="fake",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["target_adapter_id"] == "tactile_inevitability"
    packet_dir = Path(str(result.payload["packet_dir"]))
    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["residual_intervention_generation"] is True
    assert candidate["object_motion_causality_generation"] is False
    assert candidate["candidate_only"] is True
    assert candidate["non_final"] is True
    assert candidate["finalization_eligible"] is False
    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    assert diff["target_coverage_report"]["target_specific_mapping_exists"] is True
    assert "full_tactile_intervention" in diff["target_coverage_report"][
        "target_specific_ablation_controls"
    ]
    materiality = diff["materiality_report"]
    assert materiality["materiality_policy_id"].startswith("tactile_inevitability")
    assert materiality["primary_materiality_scope"] == "target_bearing_scope"
    assert materiality["residual_materiality_report"]["whole_region_guard"]["passed"] is True
    assert materiality["residual_materiality_report"]["target_bearing_scope"][
        "passed"
    ] is True
    assert materiality["target_unit_materiality_report"][
        "all_required_units_materially_engaged"
    ] is True
    assert "overlap_cluster_count" in materiality["overlap_cluster_report"]
    assert materiality["residual_intervention_validation_report"]["passed"] is True


def test_tactile_residual_candidate_generation_stubbed_openai_success(
    tmp_path,
    monkeypatch,
):
    chain = build_tactile_residual_candidate_authorization_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-tactile-model",
        client_factory=residual_intervention_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 1
    assert clients[0].requests[0].schema == RESIDUAL_INTERVENTION_GENERATION_SCHEMA
    prompt = json.loads(clients[0].requests[0].input_text)
    assert prompt["materiality_policy"]["primary_materiality_scope"] == (
        "target_bearing_scope"
    )
    assert prompt["materiality_policy"]["target_unit_scope"]["absolute_change_floor"] > 0
    assert "tactile necessity is distinct from object motion" in (
        " ".join(prompt["materiality_policy"]["prompt_feedback"])
    )
    model_call = result.payload["model_calls"][0]
    assert model_call["provider"] == "openai"
    assert model_call["model"] == "stub-tactile-model"
    assert model_call["worker_role"] == WorkerRole.RESIDUAL_INTERVENTION_GENERATOR.value
    assert model_call["schema_name"] == RESIDUAL_INTERVENTION_GENERATION_SCHEMA.name
    assert model_call["status"] == MODEL_CALL_SUCCESS
    packet_dir = Path(str(result.payload["packet_dir"]))
    patch = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    assert patch["target_unit_mappings"]
    assert patch["target_adapter_id"] == "tactile_inevitability"
    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["source_model_call_id"] == result.payload["model_call_ids"][0]
    assert candidate["fixture_only"] is False
    assert candidate["non_final"] is True
    assert candidate["not_human_validated"] is True
    assert candidate["residual_intervention_validation_report"]["passed"] is True
    assert candidate["target_unit_materiality_report"][
        "all_required_units_materially_engaged"
    ] is True


@pytest.mark.parametrize(
    ("mode", "expected_message"),
    [
        ("object_motion_relabel", "missing tactile necessity"),
        ("decorative", "decorative/generic vividness"),
        ("abstract", "abstractly"),
    ],
)
def test_tactile_residual_candidate_generation_validation_failures(
    tmp_path,
    monkeypatch,
    mode,
    expected_message,
):
    chain = build_tactile_residual_candidate_authorization_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-tactile-model",
        client_factory=residual_intervention_stub_factory(clients, mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected_message in result.payload["message"]
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]


def test_tactile_materiality_policy_allows_stable_protected_context(
    tmp_path,
    monkeypatch,
):
    chain = build_tactile_residual_candidate_authorization_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-tactile-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="protected_context_stable",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))
    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    report = diff["materiality_report"]
    protected = report["residual_materiality_report"]["protected_context"]
    if protected["protected_context_present"]:
        assert protected["protected_context_preserved"] is True
        assert protected["scope_failure"] is None
    assert report["residual_materiality_report"]["target_bearing_scope"][
        "passed"
    ] is True
    assert report["residual_intervention_validation_report"]["passed"] is True
    assert "token_edit_distance" in report["residual_materiality_report"][
        "target_bearing_scope"
    ]
    assert "sequence_similarity" in report["residual_materiality_report"][
        "target_bearing_scope"
    ]


def test_tactile_packet_0062_like_output_remains_rejected_with_unit_diagnostics(
    tmp_path,
    monkeypatch,
):
    chain = build_tactile_residual_candidate_authorization_chain(tmp_path)
    work_order_packet = Path(str(chain["residual_work_order"]["packet_dir"]))

    shared_under_material_text = (
        "Dust gathers where hand, foot, and air have pressed the same surface, "
        "and the spoon lies where a hand released it beside the saucer whose "
        "break the fall made visible."
    )

    def _force_packet_0062_unit_shape(payload):
        specs = [
            {
                "objects": ["cup", "ring", "crumb", "grain"],
                "source_unit_role": "contact_residue_displacement",
                "before_text": (
                    "When a cup is set down and lifted again, the ring tightens "
                    "where the lip meets the wood, and the crumb is taken into "
                    "the table's grain; the change is there before anyone names it."
                ),
                "current_physical_relation": (
                    "contact, pressure, residue, and displacement alter the surface trace"
                ),
            },
            {
                "objects": ["dust", "hand", "foot", "air", "surface"],
                "source_unit_role": "surface_residue_disturbance",
                "before_text": shared_under_material_text,
                "current_physical_relation": (
                    "contact, passage, and settling leave residue on the surface"
                ),
            },
            {
                "objects": ["spoon", "saucer", "hand", "fall", "break"],
                "source_unit_role": "impact_breakage",
                "before_text": shared_under_material_text,
                "current_physical_relation": (
                    "release, weight, impact, or breakage leaves a visible material change"
                ),
            },
        ]
        for unit, spec in zip(payload["target_units"], specs, strict=True):
            unit["objects"] = spec["objects"]
            unit["involved_object_labels"] = spec["objects"]
            unit["source_unit_role"] = spec["source_unit_role"]
            unit["before_text"] = spec["before_text"]
            unit["before_text_sha256"] = sha256_text(spec["before_text"])
            unit["current_physical_relation"] = spec["current_physical_relation"]
            unit["current_motion_action_state"] = spec["current_physical_relation"]

    rewrite_payload(
        work_order_packet / "object_motion_target_unit_map.json",
        _force_packet_0062_unit_shape,
    )
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-tactile-model",
        client_factory=residual_intervention_stub_factory(
            clients,
            mode="packet_0062_like",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_artifact_id"] is None
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]
    validation = result.payload["residual_intervention_validation_report"]
    assert validation["passed"] is False
    categories = result.payload["validation_failure_categories"]
    assert "target_unit_materiality_failures" in categories
    assert "object_motion_relabel_failures" in categories
    unit_report = result.payload["target_unit_materiality_report"]
    by_unit = {
        unit["target_unit_id"]: unit
        for unit in unit_report["units"]
    }
    assert by_unit["tactile_unit_002"]["materiality_passed"] is False
    assert by_unit["tactile_unit_002"]["classification"] == (
        "valid_direction_but_under_material"
    )
    assert by_unit["tactile_unit_003"]["semantic_passed"] is False
    assert by_unit["tactile_unit_003"]["classification"] == "object_motion_relabel"
    cluster_report = result.payload["overlap_cluster_report"]
    assert cluster_report["overlap_cluster_count"] >= 1
    cluster = cluster_report["clusters"][0]
    assert cluster["member_unit_ids"] == ["tactile_unit_002", "tactile_unit_003"]
    assert cluster["integrated_replacement_found"] is True
    assert any(
        member["target_unit_id"] == "tactile_unit_003"
        and member["semantic_passed"] is False
        for member in cluster["member_semantic_results"]
    )

    retry = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-tactile-model",
        client_factory=residual_intervention_stub_factory([], mode="valid"),
    )
    assert retry.exit_code == 0
    assert retry.payload["accepted"] is True


def test_tactile_materiality_uses_artifact_derived_objects_not_current_nouns(
    tmp_path,
    monkeypatch,
):
    chain = build_tactile_residual_candidate_authorization_chain(tmp_path)
    work_order_packet = Path(str(chain["residual_work_order"]["packet_dir"]))

    def _replace_objects(payload):
        replacements = [
            (
                ["cup", "thread", "stain"],
                "contact, pressure, residue, and displacement alter the surface trace",
            ),
            (
                ["ash", "sleeve", "surface", "draft"],
                "contact, passage, and settling leave residue on the surface",
            ),
            (
                ["key", "bowl", "wrist", "handle"],
                "contact, pressure, friction, and displacement leave visible material change",
            ),
        ]
        for unit, replacement in zip(payload["target_units"], replacements, strict=True):
            objects, relation = replacement
            unit["objects"] = objects
            unit["current_physical_relation"] = relation
            unit["current_motion_action_state"] = relation

    rewrite_payload(work_order_packet / "object_motion_target_unit_map.json", _replace_objects)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-tactile-model",
        client_factory=residual_intervention_stub_factory(clients),
    )

    assert result.exit_code == 0
    packet_dir = Path(str(result.payload["packet_dir"]))
    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    report = diff["materiality_report"]
    assert report["residual_intervention_validation_report"]["passed"] is True
    assert "thread" in report["object_terms_present"]
    assert "ash" in report["object_terms_present"]
    assert "key" in report["object_terms_present"]


def test_residual_candidate_generation_near_copy_records_materiality_feedback(
    tmp_path,
    monkeypatch,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory(clients, mode="near_copy"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["candidate_artifact_id"] is None
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "selected region materiality failed" in result.payload["message"]
    materiality = result.payload["materiality_report"]
    assert materiality["before_word_count"] > 0
    assert materiality["replacement_word_count"] > 0
    assert materiality["changed_unique_word_count"] < REQUIRED_CHANGED_UNIQUE_WORD_COUNT
    assert materiality["changed_unique_word_ratio"] < REQUIRED_CHANGED_RATIO
    assert materiality["required_changed_unique_word_count"] == (
        REQUIRED_CHANGED_UNIQUE_WORD_COUNT
    )
    assert materiality["required_changed_ratio"] == REQUIRED_CHANGED_RATIO
    assert materiality["exact_copy"] is False
    assert materiality["near_copy_or_under_materiality"] is True
    assert materiality["failed_materiality_reason"]
    assert materiality["target_unit_ids"] == result.payload["target_unit_ids"]
    assert result.payload["changed_unique_word_ratio"] == materiality[
        "changed_unique_word_ratio"
    ]
    assert "changed_unique_word_ratio" in result.payload["model_calls"][0][
        "error_message"
    ]
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]

    packet_dir = Path(str(result.payload["packet_dir"]))
    for artifact_name in (
        "macro_recomposition_subject_manifest",
        "macro_recomposition_work_order",
        "protected_effects_and_forbidden_changes",
    ):
        payload = read_payload(packet_dir / f"{artifact_name}.json")
        assert payload["authorization_consumed"] is False
        assert payload["planned_authorization_consumption_on_success"] is True
        if "candidate_generated" in payload:
            assert payload["candidate_generated"] is False
            assert payload["candidate_generation_intended"] is True


def test_residual_candidate_generation_failed_attempt_does_not_block_retry(
    tmp_path,
    monkeypatch,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    authorization_packet = Path(
        str(chain["residual_generation_authorization"]["packet_dir"])
    )
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    failed = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory([], mode="near_copy"),
    )
    assert failed.exit_code == 1
    assert failed.payload["candidate_generated"] is False

    retry = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=authorization_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory([]),
    )

    assert retry.exit_code == 0
    assert retry.payload["accepted"] is True
    assert retry.payload["candidate_generated"] is True


def test_residual_candidate_generation_derives_object_terms_from_work_order(
    tmp_path,
    monkeypatch,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    work_order_packet = Path(str(chain["residual_work_order"]["packet_dir"]))

    def _replace_objects(payload):
        replacements = [
            (
                ["lamp", "cord", "shade"],
                "lamp slides and cord pulls shade",
                "shade leaves a visible mark",
                "reader sees lamp and cord pressure alter the shade before explanation",
            ),
            (
                ["ink", "finger", "draft"],
                "ink drifts when finger crosses draft",
                "draft leaves a visible mark",
                "reader sees ink and finger pressure alter the draft before explanation",
            ),
            (
                ["hinge", "notebook", "thread"],
                "hinge turns and notebook pulls thread",
                "thread leaves a visible mark",
                "reader sees hinge and notebook pressure alter the thread before explanation",
            ),
        ]
        for unit, replacement in zip(payload["target_units"], replacements, strict=True):
            objects, action, consequence, target_effect = replacement
            unit["objects"] = objects
            unit["current_motion_action_state"] = action
            unit["current_consequence"] = consequence
            unit["target_effect"] = target_effect

    rewrite_payload(work_order_packet / "object_motion_target_unit_map.json", _replace_objects)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=dynamic_object_motion_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))
    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    report = diff["materiality_report"]
    assert report["object_terms_source"] == "target_units_from_work_order"
    for term in ("lamp", "cord", "shade", "ink", "finger", "draft", "hinge"):
        assert term in report["object_terms_present"]
    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert "lamp" in candidate["text"]
    assert "hinge" in candidate["text"]


def test_residual_candidate_generation_missing_object_labels_fail_closed(
    tmp_path,
    monkeypatch,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    work_order_packet = Path(str(chain["residual_work_order"]["packet_dir"]))

    def _remove_objects(payload):
        payload["target_units"][0]["objects"] = []

    rewrite_payload(work_order_packet / "object_motion_target_unit_map.json", _remove_objects)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "object labels are missing" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert clients == []


@pytest.mark.parametrize(
        ("mode", "expected_message"),
        [
            ("missing_mapping", "missing target unit IDs"),
            ("invented_unit", "invented or unsupported target unit"),
            ("decorative", "decorative object listing"),
            ("full_rewrite", "full rewrite"),
            ("finality", "forbidden claim/leakage"),
        ],
)
def test_residual_candidate_generation_stubbed_openai_validation_failures(
    tmp_path,
    monkeypatch,
    mode,
    expected_message,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_residual_candidate_generation(
        chain["config"],
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory(clients, mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected_message in result.payload["message"]
    assert result.payload["authorization_consumed"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]
    packet_dir = Path(str(result.payload["packet_dir"]))
    assert not (packet_dir / "macro_recomposed_candidate_text.json").exists()


def test_object_event_recomposition_fake_accepts_strategy_and_preserves_base(tmp_path):
    chain = build_object_event_strategy_chain(tmp_path)
    config = chain["config"]
    strategy_packet = Path(str(chain["next_target_strategy"]["packet_dir"]))
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_object_event_recomposition(
        config,
        client_name="fake",
        strategy_packet=strategy_packet,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["base_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert result.payload["base_candidate_packet_id"] != chain["macro_payload"]["packet_id"]
    assert result.payload["target_scope"] == OBJECT_EVENT_TARGET_SCOPE
    assert result.payload["target_name"] == OBJECT_EVENT_TARGET_SCOPE
    assert result.payload["primary_next_target"] == OBJECT_EVENT_TARGET_SCOPE
    assert result.payload["current_best_candidate"]["packet_id"] == chain["macro2"][
        "packet_id"
    ]
    assert result.payload["selected_region_id"] == "middle_recurrence_ordinary_trace_logic"
    assert result.payload["candidate_generated"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))
    assert packet_dir.parent.name == "bounded_macro_recomposition"

    manifest = read_payload(packet_dir / "macro_recomposition_subject_manifest.json")
    assert manifest["source_strategy_packet_id"] == chain["next_target_strategy"]["packet_id"]
    assert manifest["base_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert manifest["proof_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert manifest["reader_state_packet_id"] == chain["macro2_reader_state"]["packet_id"]

    target_selection = read_payload(packet_dir / "object_event_pressure_target_selection.json")
    assert target_selection["target_name"] == OBJECT_EVENT_TARGET_SCOPE
    assert target_selection["selected_region_id"] == "middle_recurrence_ordinary_trace_logic"
    assert target_selection["generation_authorized_by_command"] is True

    protected = read_payload(packet_dir / "protected_effects_and_forbidden_changes.json")
    assert any("partial reread transformation" in item for item in protected["protected_effects"])
    assert "decorative vividness with no causal object event" in protected["forbidden_changes"]
    assert "proof/no-answer compression by inertia" in protected["forbidden_changes"]

    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["base_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert candidate["target_scope"] == OBJECT_EVENT_TARGET_SCOPE
    assert candidate["bounded_macro_recomposition"] is True
    assert candidate["object_event_pressure_recomposition"] is True
    assert candidate["full_rewrite"] is False
    assert candidate["candidate_only"] is True
    assert candidate["non_final"] is True
    assert candidate["finalization_eligible"] is False
    assert candidate["no_phase_shift_claim"] is True
    assert candidate["fixture_only"] is True
    assert "The cup left the ring" in candidate["text"]
    base_candidate = read_payload(
        Path(str(chain["macro2"]["packet_dir"])) / "macro_recomposed_candidate_text.json"
    )
    assert str(base_candidate["text"]).split("\n\n")[0] in candidate["text"]

    patch = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    assert patch["object_event_pressure_mapping"]
    assert patch["target_coverage_report"]["object_event_pressure_mapping_exists"] is True
    assert patch["target_coverage_report"]["macro_materiality_passed"] is True

    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    assert diff["target_scope"] == OBJECT_EVENT_TARGET_SCOPE
    assert diff["changed_spans"][0]["within_selected_target"] is True
    assert diff["changed_spans"][0]["requires_target_expansion"] is False
    assert diff["target_coverage_report"]["ready_for_executed_ablation"] is True
    assert diff["materiality_report"]["object_event_relation_count"] >= 1

    rival = read_payload(packet_dir / "macro_rival_pressure_check.json")
    assert rival["strongest_rival_pressure_preserved"] is True
    assert rival["strongest_rival_still_blocks"] is True
    assert rival["strongest_rival_comparison_passed"] is False

    gate = read_payload(packet_dir / "macro_recomposition_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "strategy_packet_consumed",
        "base_candidate_packet_0056_used",
        "first_read_object_event_pressure_targeted",
        "bounded_region_selected",
        "object_event_pressure_mapping_exists",
        "region_materiality_passed",
        "protected_effects_recorded",
        "rival_pressure_preserved",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "executed_ablation_completed_for_object_event_candidate",
        "reader_state_eval_completed_for_object_event_candidate",
        "no_unresolved_internal_blockers",
        "internal_operator_approval",
        "finalization_eligible",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["passed"] is False
    assert gate["candidate_generated"] is True
    assert gate["requires_executed_ablation_before_improvement_claim"] is True

    packet = read_payload(packet_dir / "macro_recomposition_packet.json")
    assert packet["base_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert packet["current_best_candidate"]["packet_id"] == chain["macro2"]["packet_id"]
    assert packet["target_name"] == OBJECT_EVENT_TARGET_SCOPE
    assert packet["primary_next_target"] == OBJECT_EVENT_TARGET_SCOPE
    assert packet["target_scope"] == OBJECT_EVENT_TARGET_SCOPE
    assert packet["counts"]["model_calls"] == 0
    assert packet["counts"]["produced_artifacts"] == len(OBJECT_EVENT_RECOMPOSITION_ARTIFACT_TYPES)
    assert packet["requires_executed_ablation_before_improvement_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        ablation_subject = _load_subject(connection, packet_dir)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert ablation_subject.revision_packet_kind == REVISION_PACKET_KIND_BOUNDED_MACRO
    assert ablation_subject.base_candidate_packet_id == chain["macro2"]["packet_id"]
    assert ablation_subject.target_movement == OBJECT_EVENT_TARGET_SCOPE
    assert final_report.refused is True


def test_object_event_recomposition_refuses_strategy_missing_current_best(tmp_path):
    chain = build_object_event_strategy_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_object_event_strategy_missing_best"
    shutil.copytree(Path(str(chain["next_target_strategy"]["packet_dir"])), invalid_packet)

    def _remove_current_best(payload):
        payload.pop("current_best_candidate_packet_id", None)

    rewrite_payload(invalid_packet / "current_best_candidate_summary.json", _remove_current_best)

    result = run_object_event_recomposition(
        chain["config"],
        client_name="fake",
        strategy_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "missing current best candidate" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_object_event_recomposition_refuses_wrong_strategy_target(tmp_path):
    chain = build_object_event_strategy_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_object_event_strategy_wrong_target"
    shutil.copytree(Path(str(chain["next_target_strategy"]["packet_dir"])), invalid_packet)

    def _wrong_target(payload):
        payload["target_name"] = "proof_no_outside_answer_refinement"

    rewrite_payload(invalid_packet / "object_event_pressure_target_map.json", _wrong_target)

    result = run_object_event_recomposition(
        chain["config"],
        client_name="fake",
        strategy_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "object_event_pressure_target_map target_name" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_object_event_recomposition_openai_refuses_without_allow_live(tmp_path):
    chain = build_object_event_strategy_chain(tmp_path)
    clients = []

    result = run_object_event_recomposition(
        chain["config"],
        client_name="openai",
        strategy_packet=Path(str(chain["next_target_strategy"]["packet_dir"])),
        allow_live_model=False,
        client_factory=object_event_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "--allow-live-model" in result.payload["message"]
    assert clients == []
    assert result.payload["counts"]["model_calls"] == 0


def test_object_event_recomposition_openai_refuses_without_api_key(tmp_path, monkeypatch):
    chain = build_object_event_strategy_chain(tmp_path)
    clients = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = run_object_event_recomposition(
        chain["config"],
        client_name="openai",
        strategy_packet=Path(str(chain["next_target_strategy"]["packet_dir"])),
        allow_live_model=True,
        client_factory=object_event_stub_factory(clients),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "OPENAI_API_KEY is not set" in result.payload["message"]
    assert clients == []
    assert result.payload["counts"]["model_calls"] == 0


def test_object_event_recomposition_stubbed_openai_success(tmp_path, monkeypatch):
    chain = build_object_event_strategy_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_object_event_recomposition(
        chain["config"],
        client_name="openai",
        strategy_packet=Path(str(chain["next_target_strategy"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        model="stub-object-event-model",
        client_factory=object_event_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert len(clients) == 1
    assert len(clients[0].requests) == 1
    assert result.payload["counts"]["model_calls"] == 1
    packet_dir = Path(str(result.payload["packet_dir"]))
    model_call = result.payload["model_calls"][0]
    assert model_call["provider"] == "openai"
    assert model_call["model"] == "stub-object-event-model"
    assert model_call["status"] == MODEL_CALL_SUCCESS

    plan_envelope = json.loads(
        (packet_dir / "macro_recomposition_plan.json").read_text(encoding="utf-8")
    )
    patch_envelope = json.loads(
        (packet_dir / "macro_patch_or_section_plan.json").read_text(encoding="utf-8")
    )
    assert plan_envelope["model_call_id"] == result.payload["model_call_ids"][0]
    assert patch_envelope["model_call_id"] == result.payload["model_call_ids"][0]
    assert patch_envelope["fixture_only"] is False

    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["source_model_call_id"] == result.payload["model_call_ids"][0]
    assert candidate["fixture_only"] is False
    assert candidate["base_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert candidate["target_scope"] == OBJECT_EVENT_TARGET_SCOPE
    assert candidate["non_final"] is True
    assert candidate["finalization_eligible"] is False
    assert candidate["no_phase_shift_claim"] is True

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


@pytest.mark.parametrize(
    ("mode", "expected_message"),
    [
        ("full_rewrite", "full rewrite"),
        ("decorative_only", "object-event pressure mapping failed"),
        ("proof_only", "object-event pressure mapping failed"),
        ("unchanged_region", "selected region materiality failed"),
    ],
)
def test_object_event_recomposition_stubbed_openai_validation_failures(
    tmp_path,
    monkeypatch,
    mode,
    expected_message,
):
    chain = build_object_event_strategy_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_object_event_recomposition(
        chain["config"],
        client_name="openai",
        strategy_packet=Path(str(chain["next_target_strategy"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        model="stub-object-event-model",
        client_factory=object_event_stub_factory(clients, mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected_message in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED
    assert "macro_recomposed_candidate_text" not in result.payload["artifact_ids"]
    packet_dir = Path(str(result.payload["packet_dir"]))
    assert not (packet_dir / "macro_recomposed_candidate_text.json").exists()


def test_autonomous_evidence_synthesis_supersedes_with_object_event_proof(tmp_path):
    chain = build_object_event_candidate_with_optional_proof(
        tmp_path,
        proof_mode="useful",
        object_event_client="openai",
    )
    config = chain["config"]
    run_id = chain["run_id"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert chain["object_event"]["packet_id"] in manifest[
        "object_event_candidate_packets_consumed"
    ]
    assert chain["object_event_proof"]["packet_id"] in manifest[
        "object_event_ablation_packets_consumed"
    ]

    history = read_payload(packet_dir / "repair_history_table.json")
    object_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "bounded_macro_recomposition"
        and row["packet_id"] == chain["object_event"]["packet_id"]
    ]
    assert object_rows
    object_row = object_rows[0]
    assert object_row["target_scope"] == OBJECT_EVENT_TARGET_SCOPE
    assert object_row["base_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert object_row["selected_region_id"] == "middle_recurrence_ordinary_trace_logic"
    assert object_row["object_event_pressure_recomposition"] is True
    assert object_row["macro_target_coverage_passed"] is True
    assert object_row["macro_materiality_passed"] is True
    assert object_row["ready_for_executed_ablation"] is True
    assert object_row["finalization_eligible"] is False
    assert object_row["strongest_rival_pressure_preserved"] is True

    proof_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "executed_ablation"
        and row["packet_id"] == chain["object_event_proof"]["packet_id"]
    ]
    assert proof_rows
    proof_row = proof_rows[0]
    assert proof_row["source_revision_packet_id"] == chain["object_event"]["packet_id"]
    assert proof_row["source_revision_packet_kind"] == "bounded_macro_recomposition"
    assert proof_row["normalized_subject_kind"] == "bounded_macro_recomposition"
    assert proof_row["source_revision_packet_dir"] == chain["object_event"]["packet_dir"]
    assert proof_row["model_backed"] is True
    assert proof_row["fixture_only"] is False
    assert proof_row["model_calls"] == 1
    assert proof_row["countable_evidence_variant_count"] > 0
    assert proof_row["comparison_internal_consistency"] is True
    assert proof_row["repair_has_causal_support"] is True
    assert proof_row["selected_repair_appears_causal"] is True
    assert proof_row["selected_repair_causal_status"] == "useful_but_insufficient"
    assert proof_row["reverting_patch_weakens_candidate"] is True
    assert proof_row["revert_performs_same_or_better"] is False
    assert proof_row["reduced_overexplanation"] is True
    assert proof_row["damaged_local_embodiment"] is False
    assert proof_row["strongest_rival_pressure_remains_blocking"] is True
    assert proof_row["finalization_eligible"] is False

    causal = read_payload(packet_dir / "causal_status_summary.json")
    assert chain["object_event"]["packet_id"] in causal["object_event_candidate_packet_ids"]
    assert chain["object_event_proof"]["packet_id"] in causal["object_event_proof_packet_ids"]
    assert causal["object_event_causal_summary"]["object_event_repair_status"] == (
        "useful_but_insufficient"
    )

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["object_event"]["packet_id"]
    assert selected["packet_kind"] == "bounded_macro_recomposition"
    assert selected["selected_object_event_candidate"] is True
    assert selected["selected_macro2_candidate"] is False
    assert selected["base_candidate_packet_id"] == chain["macro2"]["packet_id"]
    assert selected["target_scope"] == OBJECT_EVENT_TARGET_SCOPE
    assert selected["selected_region_id"] == "middle_recurrence_ordinary_trace_logic"
    assert selected["candidate_proof_linked"] is True
    assert selected["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert selected["proof_model_backed"] is True
    assert selected["proof_fixture_only"] is False
    assert selected["proof_countable_evidence_variant_count"] > 0
    assert selected["proof_causal_status"] == "useful_but_insufficient"
    assert selected["reader_state_evaluated"] is False
    assert selected["selected_candidate_requires_further_testing"] is True
    assert selected["selected_candidate_is_final"] is False
    assert selected["strongest_rival_still_blocks"] is True
    assert best["best_current_candidate_updated_from_object_event_proof"] is True
    assert best["object_event_candidate_supersession_applied"] is True
    assert best["best_current_candidate_updated_from_macro2_proof"] is False

    pair = [
        item
        for item in best["candidate_proof_pairs"]
        if item["candidate_packet_id"] == chain["object_event"]["packet_id"]
    ][0]
    assert pair["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert pair["candidate_object_event_pressure_recomposition"] is True
    assert pair["supersession_eligible"] is True

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    blocker_ids = {blocker["blocker_id"] for blocker in blockers["residual_blockers"]}
    assert f"reader_state_evaluation_needed_for_{chain['object_event']['packet_id']}" in blocker_ids
    assert "object_event_pressure_gain_unproven_by_reader_state" in blocker_ids
    assert "first_read_vividness_requires_reader_state_confirmation" in blocker_ids
    assert f"preserve_{chain['macro2']['packet_id']}_macro2_gains" in blocker_ids
    assert "avoid_decorative_vividness" in blocker_ids
    assert "no_finalization" in blocker_ids
    assert blockers["object_event_reader_state_eval_needed"] is True
    assert blockers["strongest_rival_still_blocks"] is True

    laws = read_payload(packet_dir / "local_law_case_notes.json")
    law_ids = {law["law_id"] for law in laws["case_notes"]}
    assert "object_event_recomposition_can_gain_countable_causal_support" in law_ids
    assert "object_event_pressure_requires_reader_state_test" in law_ids
    assert "object_event_gain_can_coexist_with_rival_blocker" in law_ids
    assert "useful_but_insufficient_ablation_is_not_finality" in law_ids

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "preserve_object_event_candidate_and_run_reader_state_evaluation"
    )
    assert decision["next_recommended_action"] == (
        "run_internal_reader_state_evaluation_on_object_event_candidate"
    )
    assert decision["next_recommended_action"] != (
        "review_macro2_reader_state_synthesis_before_new_candidate"
    )
    assert decision["first_read_object_event_pressure_strategy_recommended"] is False
    assert decision["object_event_reader_state_evaluation_recommended"] is True
    assert decision["no_phase_shift_claim"] is True

    brief = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert brief["brief_type"] == "object_event_reader_state_evaluation_brief_not_artifact"
    assert brief["current_best_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert brief["base_prior_packet_id"] == chain["macro2"]["packet_id"]
    assert brief["proof_basis_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert brief["next_evidence_need"] == "internal_reader_state_evaluation"
    assert brief["run_another_object_event_recomposition_now"] is False
    assert brief["no_phase_shift_claim"] is True

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    assert gate_results["object_event_candidate_consumed"]["passed"] is True
    assert gate_results["object_event_ablation_consumed"]["passed"] is True
    assert gate_results["object_event_candidate_proof_linked"]["passed"] is True
    assert gate_results["object_event_candidate_supersession_evaluated"]["passed"] is True
    assert gate_results["best_current_candidate_updated_from_object_event_proof"][
        "passed"
    ] is True
    assert gate_results["object_event_reader_state_eval_needed"]["passed"] is True
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["best_current_candidate"]["packet_id"] == chain["object_event"]["packet_id"]
    assert chain["object_event"]["packet_id"] in packet[
        "object_event_candidate_packets_consumed"
    ]
    assert chain["object_event_proof"]["packet_id"] in packet[
        "object_event_ablation_packets_consumed"
    ]
    assert packet["best_current_candidate_updated_from_object_event_proof"] is True
    assert packet["next_recommended_action"] == (
        "run_internal_reader_state_evaluation_on_object_event_candidate"
    )
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_consumes_object_event_reader_state(tmp_path):
    chain = build_object_event_candidate_with_reader_state(tmp_path)
    config = chain["config"]
    run_id = chain["run_id"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["object_event_reader_state_evidence_consumed"] is True
    assert result.payload["object_event_reader_state_eval_linked"] is True
    assert result.payload["counts"]["model_calls"] == 0
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert chain["object_event"]["packet_id"] in manifest[
        "object_event_candidate_packets_consumed"
    ]
    assert chain["object_event_proof"]["packet_id"] in manifest[
        "object_event_ablation_packets_consumed"
    ]
    assert chain["object_event_reader_state"]["packet_id"] in manifest[
        "object_event_reader_state_evaluation_packets_consumed"
    ]

    history = read_payload(packet_dir / "repair_history_table.json")
    reader_rows = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "internal_reader_state_evaluation"
        and row["packet_id"] == chain["object_event_reader_state"]["packet_id"]
    ]
    assert reader_rows
    reader_row = reader_rows[0]
    assert reader_row["selected_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert reader_row["selected_candidate_text_sha256"] == chain[
        "object_event_candidate_text_sha256"
    ]
    assert reader_row["fixture_only"] is False
    assert reader_row["model_calls"] == 5
    assert reader_row["first_pass_trace_exists"] is True
    assert reader_row["reread_trace_exists"] is True
    assert reader_row["reader_delta_report_exists"] is True
    assert reader_row["proof_constraint_carry_report_exists"] is True
    assert reader_row["hostile_reader_report_exists"] is True
    assert reader_row["forensic_grounding_report_exists"] is True
    assert reader_row["rival_reader_state_comparison_exists"] is True
    assert reader_row["post_reread_reader_state"] == "partial_opening_return_transformation"
    assert reader_row["reread_gain_estimate"] == "partial"
    assert reader_row["strongest_rival_still_blocks"] is True
    assert reader_row["finalization_eligible"] is False
    assert reader_row["no_phase_shift_claim"] is True

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["object_event"]["packet_id"]
    assert selected["selected_object_event_candidate"] is True
    assert selected["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert selected["reader_state_evaluated"] is True
    assert selected["reader_state_packet_id"] == chain["object_event_reader_state"]["packet_id"]
    assert selected["reader_state_fixture_only"] is False
    assert selected["reader_state_model_calls"] == 5
    assert selected["reader_state_post_reread_state"] == (
        "partial_opening_return_transformation"
    )
    assert selected["reader_state_reread_transformation_strength"] == "partial"
    assert selected["reader_state_transformation_is_partial_not_decisive"] is True
    assert selected["reader_state_strongest_rival_still_blocks"] is True
    assert selected["selected_candidate_is_final"] is False

    adjudication = read_payload(packet_dir / "reader_state_evidence_adjudication.json")
    assert adjudication["reader_state_evidence_present"] is True
    assert adjudication["packet_id"] == chain["object_event_reader_state"]["packet_id"]
    assert adjudication["selected_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert adjudication["selected_object_event_candidate"] is True
    assert adjudication["object_event_pressure_gain_status"] == "improved_but_insufficient"
    assert adjudication["first_read_object_event_pressure_status"] == (
        "gap_narrowed_but_rival_still_blocks"
    )
    assert adjudication["lived_object_causality_status"] == (
        "improved_but_still_weaker_than_rival"
    )
    assert adjudication["first_read_vividness_status"] == (
        "gap_narrowed_but_rival_still_blocks"
    )
    assert adjudication["reread_transformation_status"] == "partial"
    assert adjudication["packet_0056_macro2_gains_preserved_status"] == (
        "preserved_as_base_but_partial"
    )
    assert adjudication["proof_no_outside_answer_carry_status"] == "partial_or_unresolved"
    assert adjudication["final_return_echo_status"] == "improved_but_unproven"
    assert adjudication["strongest_rival_status"] == "still_blocks"
    assert adjudication["hostile_risk_status"] == "active"
    assert adjudication["not_human_data"] is True
    assert adjudication["no_phase_shift_claim"] is True

    tensions = read_payload(packet_dir / "reader_state_tension_report.json")
    tension_ids = {tension["tension_id"] for tension in tensions["tensions"]}
    assert "object_event_pressure_improved_but_rival_still_blocks" in tension_ids
    assert "object_event_gain_preserves_macro2_but_reread_partial" in tension_ids
    assert "object_event_pressure_risks_busy_or_decorative_causality" in tension_ids
    assert "object_event_gain_must_protect_proof_and_return" in tension_ids
    assert "internal_reader_evidence_not_human_data" in tension_ids

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    blocker_ids = {blocker["blocker_id"] for blocker in blockers["residual_blockers"]}
    assert f"reader_state_evaluation_needed_for_{chain['object_event']['packet_id']}" not in (
        blocker_ids
    )
    assert "reader_state_gain_still_partial" in blocker_ids
    assert "first_read_vividness_gap_still_active" in blocker_ids
    assert "lived_object_event_pressure_still_weaker_than_rival" in blocker_ids
    assert "proof_no_outside_answer_carry_still_partial" in blocker_ids
    assert "final_return_echo_reread_strength_still_partial" in blocker_ids
    assert "hostile_scaffold_or_overexplanation_risk" in blocker_ids
    assert blockers["object_event_reader_state_eval_needed"] is False
    assert blockers["object_event_reader_state_evidence_consumed"] is True
    assert blockers["object_event_review_before_new_candidate_recommended"] is True
    assert blockers["strongest_rival_still_blocks"] is True

    laws = read_payload(packet_dir / "local_law_case_notes.json")
    law_ids = {law["law_id"] for law in laws["case_notes"]}
    assert "object_event_pressure_can_strengthen_first_read_without_finality" in law_ids
    assert "object_event_gains_must_preserve_macro2_gains" in law_ids
    assert "object_event_causality_can_improve_while_rival_blocks" in law_ids
    assert "ablation_plus_partial_reader_state_supports_preservation_not_finality" in law_ids
    assert "do_not_continue_generating_by_inertia" in law_ids

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "preserve_object_event_candidate_and_pause_for_loop_level_review"
    )
    assert decision["next_recommended_action"] == (
        "review_object_event_reader_state_synthesis_before_new_candidate"
    )
    assert decision["next_recommended_action"] != (
        "run_internal_reader_state_evaluation_on_object_event_candidate"
    )
    assert decision["object_event_reader_state_evaluation_recommended"] is False
    assert decision["object_event_reader_state_evidence_consumed"] is True
    assert decision["object_event_review_before_new_candidate_recommended"] is True
    assert decision["reader_state_informed_macro_2_recomposition_recommended"] is False
    assert decision["no_phase_shift_claim"] is True

    brief = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert brief["brief_type"] == "object_event_reader_state_synthesis_review_brief_not_artifact"
    assert brief["current_best_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert brief["evidence_basis"]["ablation_packet_id"] == chain["object_event_proof"][
        "packet_id"
    ]
    assert brief["evidence_basis"]["reader_state_packet_id"] == chain[
        "object_event_reader_state"
    ]["packet_id"]
    assert brief["operator_review_required_before_new_creative_action"] is True
    assert brief["run_internal_reader_state_evaluation_before_further_recomposition"] is False
    assert brief["run_another_object_event_recomposition_now"] is False
    assert brief["no_phase_shift_claim"] is True

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    assert gate_results["object_event_reader_state_evidence_consumed"]["passed"] is True
    assert gate_results["object_event_reader_state_eval_linked"]["passed"] is True
    assert gate_results["reader_state_transformation_classified"]["passed"] is True
    assert gate_results["best_candidate_reader_state_status_current"]["passed"] is True
    assert gate_results["strongest_rival_pressure_preserved"]["passed"] is True
    assert gate["object_event_reader_state_evidence_consumed"] is True
    assert gate["object_event_reader_state_eval_linked"] is True
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["best_current_candidate"]["packet_id"] == chain["object_event"]["packet_id"]
    assert packet["best_current_candidate"]["reader_state_evaluated"] is True
    assert chain["object_event_reader_state"]["packet_id"] in packet[
        "object_event_reader_state_evaluation_packets_consumed"
    ]
    assert packet["object_event_reader_state_evidence_consumed"] is True
    assert packet["object_event_reader_state_eval_linked"] is True
    assert packet["next_recommended_action"] == (
        "review_object_event_reader_state_synthesis_before_new_candidate"
    )
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_surfaces_proof_backed_residual_candidate(
    tmp_path,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    config = chain["config"]
    run_id = chain["run_id"]
    residual_clients = []
    residual = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory(residual_clients),
    )
    assert residual.exit_code == 0
    assert residual.payload["accepted"] is True
    assert residual.payload["base_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert residual.payload["selected_residual_target_id"] == (
        OBJECT_MOTION_CAUSALITY_TARGET_ID
    )
    assert residual.payload["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert residual.payload["authorization_consumed"] is True
    assert residual.payload["candidate_generated"] is True

    proof_clients = []
    proof = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation-model",
        client_factory=executed_ablation_stub_factory(proof_clients),
    )
    assert proof.exit_code == 0
    assert proof.payload["accepted"] is True
    _rewrite_macro2_proof(proof.payload, useful=True)

    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert residual.payload["packet_id"] in manifest["residual_candidate_packets_consumed"]
    assert proof.payload["packet_id"] in manifest[
        "residual_candidate_ablation_packets_consumed"
    ]

    history = read_payload(packet_dir / "repair_history_table.json")
    residual_row = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "bounded_macro_recomposition"
        and row["packet_id"] == residual.payload["packet_id"]
    ][0]
    assert residual_row["base_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert residual_row["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert residual_row["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert residual_row["source_authorization_packet_id"] == chain[
        "residual_generation_authorization"
    ]["packet_id"]
    assert residual_row["authorization_consumed"] is True
    assert residual_row["candidate_generated"] is True
    assert residual_row["target_unit_count"] == 3
    assert residual_row["target_unit_ids"]
    assert residual_row["protected_effects_recorded"] is True
    assert residual_row["no_nonselected_region_edits"] is True
    assert residual_row["reader_state_evaluated"] is False
    assert residual_row["finalization_eligible"] is False
    assert residual_row["no_phase_shift_claim"] is True

    proof_row = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "executed_ablation"
        and row["packet_id"] == proof.payload["packet_id"]
    ][0]
    assert proof_row["source_revision_packet_id"] == residual.payload["packet_id"]
    assert proof_row["source_revision_packet_kind"] == "bounded_macro_recomposition"
    assert proof_row["normalized_subject_kind"] == "bounded_macro_recomposition"
    assert proof_row["causal_status"] == "useful_but_insufficient"
    assert proof_row["repair_has_causal_support"] is True
    assert proof_row["revert_performs_same_or_better"] is False
    assert proof_row["reverting_patch_weakens_candidate"] is True
    assert proof_row["countable_evidence_variant_count"] == 3
    assert proof_row["comparison_internal_consistency"] is True
    assert proof_row["model_backed"] is True
    assert proof_row["fixture_only"] is False
    assert proof_row["finalization_eligible"] is False

    causal = read_payload(packet_dir / "causal_status_summary.json")
    assert residual.payload["packet_id"] in causal["residual_candidate_packet_ids"]
    assert proof.payload["packet_id"] in causal["residual_candidate_proof_packet_ids"]
    assert residual.payload["packet_id"] in causal[
        "residual_candidate_proof_backed_pending_packet_ids"
    ]

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["object_event"]["packet_id"]
    assert selected["reader_state_evaluated"] is True
    assert selected["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    residual_option = [
        option
        for option in best["candidate_options"]
        if option["packet_id"] == residual.payload["packet_id"]
    ][0]
    assert residual_option["candidate_proof_linked"] is True
    assert residual_option["proof_packet_id"] == proof.payload["packet_id"]
    assert residual_option["proof_supports_candidate"] is True
    assert residual_option["supersession_eligible"] is True
    assert residual_option["supersession_pending_reader_state"] is True
    assert residual_option["reader_state_evaluated"] is False
    assert residual_option["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert best["proof_backed_pending_candidate_count"] == 1
    assert best["current_best_preserved_pending_reader_state"] is True

    queue = read_payload(packet_dir / "provisional_candidate_queue.json")
    pending = queue["pending_candidates"][0]
    assert pending["packet_id"] == residual.payload["packet_id"]
    assert pending["proof_backed"] is True
    assert pending["proof_packet_id"] == proof.payload["packet_id"]
    assert pending["reader_state_evaluated"] is False
    assert pending["finalization_eligible"] is False
    assert pending["supersession_pending_reader_state"] is True
    assert pending["current_best_candidate_remains"] == chain["object_event"]["packet_id"]
    assert pending["next_required_evidence"] == "internal_reader_state_evaluation"
    assert pending["recommended_next_action"] == (
        f"run_internal_reader_state_evaluation_on_{residual.payload['packet_id']}"
    )
    assert queue["proof_backed_pending_count"] == 1
    assert queue["current_best_candidate_packet_id"] == chain["object_event"]["packet_id"]

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    blocker_ids = {blocker["blocker_id"] for blocker in blockers["residual_blockers"]}
    assert (
        f"{OBJECT_MOTION_CAUSALITY_TARGET_ID}_proof_backed_candidate_generated"
        in blocker_ids
    )
    assert f"reader_state_evaluation_missing_for_{residual.payload['packet_id']}" in (
        blocker_ids
    )
    assert "strongest_rival_still_blocks_residual_candidate" in blocker_ids
    assert blockers["proof_backed_residual_candidate_exists"] is True
    assert blockers["residual_candidate_reader_state_missing"] is True
    assert blockers["residual_candidate_next_required_evidence"] == (
        "internal_reader_state_evaluation"
    )

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "preserve_current_best_and_run_reader_state_evaluation_on_provisional_residual_candidate"
    )
    assert decision["next_recommended_action"] == (
        f"run_internal_reader_state_evaluation_on_{residual.payload['packet_id']}"
    )
    assert decision["provisional_residual_candidate_reader_state_evaluation_recommended"] is True
    assert decision["no_phase_shift_claim"] is True

    brief = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert brief["brief_type"] == (
        "provisional_residual_candidate_reader_state_evaluation_brief_not_artifact"
    )
    assert brief["current_best_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert brief["provisional_candidate_packet_id"] == residual.payload["packet_id"]
    assert brief["proof_basis_packet_id"] == proof.payload["packet_id"]
    assert brief["next_evidence_need"] == "internal_reader_state_evaluation"
    assert brief["run_internal_reader_state_evaluation_before_further_recomposition"] is True
    assert brief["run_another_macro_recomposition_now"] is False
    assert brief["no_phase_shift_claim"] is True

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    assert gate_results["residual_candidate_evidence_consumed"]["passed"] is True
    assert gate_results["residual_candidate_proof_linked"]["passed"] is True
    assert gate_results["residual_candidate_reader_state_missing"]["passed"] is True
    assert gate_results["no_final_claim"]["passed"] is True
    assert gate_results["no_phase_shift_claim"]["passed"] is True
    assert gate["residual_candidate_evidence_consumed"] is True
    assert gate["residual_candidate_proof_linked"] is True
    assert gate["residual_candidate_reader_state_missing"] is True
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert residual.payload["packet_id"] in packet["residual_candidate_packets_consumed"]
    assert proof.payload["packet_id"] in packet[
        "residual_candidate_ablation_packets_consumed"
    ]
    assert packet["best_current_candidate"]["packet_id"] == chain["object_event"]["packet_id"]
    assert packet["provisional_pending_candidate_count"] == 1
    assert packet["proof_backed_pending_candidate_count"] == 1
    assert packet["residual_candidate_reader_state_missing"] is True
    assert packet["next_recommended_action"] == (
        f"run_internal_reader_state_evaluation_on_{residual.payload['packet_id']}"
    )
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_queues_target_aware_tactile_residual_candidate(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    chain = build_tactile_residual_candidate_authorization_chain(tmp_path)
    config = chain["config"]
    residual_clients = []
    residual = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=1,
        model="stub-tactile-model",
        client_factory=residual_intervention_stub_factory(residual_clients),
    )
    assert residual.exit_code == 0
    assert residual.payload["accepted"] is True
    assert residual.payload["selected_residual_target_id"] == (
        TACTILE_INEVITABILITY_TARGET_ID
    )
    assert residual.payload["target_adapter_id"] == "tactile_inevitability"

    generic_proof = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation",
        client_factory=executed_ablation_stub_factory([]),
    )
    assert generic_proof.exit_code == 0
    _rewrite_tactile_proof_as_generic_non_authoritative(generic_proof.payload)

    role_confused = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation",
        client_factory=executed_ablation_stub_factory(
            [],
            mode="confused_tactile_revert",
        ),
    )
    assert role_confused.exit_code == 0
    assert role_confused.payload["target_role_consistency_passed"] is False

    role_failed = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation",
        client_factory=executed_ablation_stub_factory([]),
    )
    assert role_failed.exit_code == 0
    _rewrite_tactile_proof_as_role_consistency_failed(role_failed.payload)

    fake_proof = run_executed_ablation(
        config,
        client_name="fake",
        revision_packet=residual.payload["packet_dir"],
    )
    assert fake_proof.exit_code == 0
    fake_packet_envelope = json.loads(
        (Path(str(fake_proof.payload["packet_dir"])) / "executed_ablation_packet.json").read_text(
            encoding="utf-8"
        )
    )
    assert fake_packet_envelope["fixture_only"] is True

    authoritative = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation",
        client_factory=executed_ablation_stub_factory([]),
    )
    assert authoritative.exit_code == 0
    assert authoritative.payload["accepted"] is True
    assert authoritative.payload["target_aware_ablation"] is True
    assert authoritative.payload["target_adapter_id"] == "tactile_inevitability"
    assert authoritative.payload["target_role_consistency_passed"] is True

    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    synthesis = run_autonomous_evidence_synthesis(config, run_id=chain["run_id"])

    assert synthesis.exit_code == 0
    packet_dir = Path(str(synthesis.payload["packet_dir"]))
    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert residual.payload["packet_id"] in manifest["residual_candidate_packets_consumed"]
    assert authoritative.payload["packet_id"] in manifest[
        "residual_candidate_ablation_packets_consumed"
    ]

    history = read_payload(packet_dir / "repair_history_table.json")
    residual_row = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "bounded_macro_recomposition"
        and row["packet_id"] == residual.payload["packet_id"]
    ][0]
    assert residual_row["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert residual_row["target_adapter_id"] == "tactile_inevitability"
    assert residual_row["source_work_order_packet_id"] == chain["residual_work_order"][
        "packet_id"
    ]
    assert residual_row["source_authorization_packet_id"] == chain[
        "residual_generation_authorization"
    ]["packet_id"]
    assert residual_row["residual_candidate_generation"] is True

    authoritative_row = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "executed_ablation"
        and row["packet_id"] == authoritative.payload["packet_id"]
    ][0]
    assert authoritative_row["source_revision_packet_id"] == residual.payload["packet_id"]
    assert authoritative_row["target_aware_ablation"] is True
    assert authoritative_row["target_adapter_id"] == "tactile_inevitability"
    assert authoritative_row["target_role_consistency_passed"] is True
    assert authoritative_row["tactile_intervention_has_causal_support"] is True
    assert authoritative_row["tactile_force_contact_adds_value"] is True
    assert (
        authoritative_row[
            "object_motion_preserved_tactile_removed_performs_same_or_better"
        ]
        is False
    )

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["object_event"]["packet_id"]
    assert selected["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert selected["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    residual_option = [
        option
        for option in best["candidate_options"]
        if option["packet_id"] == residual.payload["packet_id"]
    ][0]
    assert residual_option["candidate_proof_linked"] is True
    assert residual_option["proof_packet_id"] == authoritative.payload["packet_id"]
    assert residual_option["proof_supports_candidate"] is True
    assert residual_option["proof_target_aware_ablation"] is True
    assert residual_option["proof_target_adapter_id"] == "tactile_inevitability"
    assert residual_option["supersession_pending_reader_state"] is True
    assert residual_option["reader_state_evaluated"] is False
    rejected_by_id = {
        proof["proof_packet_id"]: proof["rejection_reasons"]
        for proof in residual_option["rejected_proof_candidates"]
    }
    assert "target_aware_proof_required_for_residual_target" in rejected_by_id[
        generic_proof.payload["packet_id"]
    ]
    assert "target_role_consistency_failed" in rejected_by_id[
        role_confused.payload["packet_id"]
    ]
    assert "comparison_internal_consistency_missing" in rejected_by_id[
        role_failed.payload["packet_id"]
    ]
    assert "proof_not_live_model_backed" in rejected_by_id[fake_proof.payload["packet_id"]]

    graph = read_payload(packet_dir / "candidate_evidence_graph.json")
    graph_node = [
        node
        for node in graph["nodes"]
        if node["candidate_packet_id"] == residual.payload["packet_id"]
    ][0]
    assert graph_node["proof_packet_id"] == authoritative.payload["packet_id"]
    assert graph_node["target_adapter_id"] == "tactile_inevitability"
    assert graph_node["proof_backed"] is True
    assert residual.payload["packet_id"] in graph["residual_reader_state_pending_packet_ids"]

    queue = read_payload(packet_dir / "provisional_candidate_queue.json")
    assert queue["proof_backed_pending_count"] == 1
    pending = queue["pending_candidates"][0]
    assert pending["packet_id"] == residual.payload["packet_id"]
    assert pending["proof_packet_id"] == authoritative.payload["packet_id"]
    assert pending["target_adapter_id"] == "tactile_inevitability"
    assert pending["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert pending["reader_state_evaluated"] is False
    assert pending["current_best_candidate_remains"] == chain["object_event"]["packet_id"]
    assert pending["next_required_evidence"] == "internal_reader_state_evaluation"
    assert pending["recommended_next_action"] == (
        f"run_internal_reader_state_evaluation_on_{residual.payload['packet_id']}"
    )

    failed = read_payload(packet_dir / "failed_or_rejected_repairs.json")
    rejected_packets = {
        item["packet_id"]: item["rejection_reason"]
        for item in failed["failed_or_rejected_repairs"]
        if item["packet_kind"] == "executed_ablation"
    }
    assert generic_proof.payload["packet_id"] in rejected_packets
    assert role_confused.payload["packet_id"] in rejected_packets
    assert role_failed.payload["packet_id"] in rejected_packets
    assert fake_proof.payload["packet_id"] in rejected_packets

    causal = read_payload(packet_dir / "causal_status_summary.json")
    assert residual.payload["packet_id"] in causal["residual_candidate_packet_ids"]
    assert authoritative.payload["packet_id"] in causal[
        "residual_candidate_proof_packet_ids"
    ]
    assert residual.payload["packet_id"] in causal[
        "residual_candidate_proof_backed_pending_packet_ids"
    ]

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["next_recommended_action"] == (
        f"run_internal_reader_state_evaluation_on_{residual.payload['packet_id']}"
    )
    assert decision["strongest_rival_still_blocks"] is True
    assert decision["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["best_current_candidate"]["packet_id"] == chain["object_event"]["packet_id"]
    assert packet["proof_backed_pending_candidate_count"] == 1
    assert packet["provisional_pending_candidate_count"] == 1
    assert packet["residual_candidate_reader_state_missing"] is True
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_reader_state_eval_targets_proof_backed_provisional_residual_candidate(
    tmp_path,
    monkeypatch,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    config = chain["config"]
    run_id = chain["run_id"]
    residual_clients = []
    residual = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory(residual_clients),
    )
    assert residual.exit_code == 0
    assert residual.payload["accepted"] is True

    proof_clients = []
    proof = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation-model",
        client_factory=executed_ablation_stub_factory(proof_clients),
    )
    assert proof.exit_code == 0
    assert proof.payload["accepted"] is True
    _rewrite_macro2_proof(proof.payload, useful=True)

    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    assert synthesis.payload["accepted"] is True

    synthesis_packet_dir = Path(str(synthesis.payload["packet_dir"]))
    residual_packet_dir = Path(str(residual.payload["packet_dir"]))
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    unsafe_default = run_internal_reader_state_evaluation(
        config,
        client_name="fake",
        synthesis_packet=synthesis_packet_dir,
    )
    assert unsafe_default.exit_code == 1
    assert unsafe_default.payload["accepted"] is False
    assert unsafe_default.payload["refused"] is True
    assert unsafe_default.payload["counts"]["model_calls"] == 0
    assert "provisional candidate" in unsafe_default.payload["message"]
    assert residual.payload["packet_id"] in unsafe_default.payload["message"]
    assert chain["object_event"]["packet_id"] in unsafe_default.payload["message"]
    assert "--target-candidate-packet" in unsafe_default.payload["message"]

    openai_allow_guard = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet_dir,
        target_candidate_packet=residual_packet_dir,
    )
    assert openai_allow_guard.exit_code == 1
    assert openai_allow_guard.payload["counts"]["model_calls"] == 0
    assert "--allow-live-model" in openai_allow_guard.payload["message"]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    openai_key_guard = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet_dir,
        target_candidate_packet=residual_packet_dir,
        allow_live_model=True,
        max_model_calls=5,
    )
    assert openai_key_guard.exit_code == 1
    assert openai_key_guard.payload["counts"]["model_calls"] == 0
    assert "OPENAI_API_KEY" in openai_key_guard.payload["message"]

    openai_budget_guard = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet_dir,
        target_candidate_packet=residual_packet_dir,
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=4,
    )
    assert openai_budget_guard.exit_code == 1
    assert openai_budget_guard.payload["counts"]["model_calls"] == 0
    assert "below required budget" in openai_budget_guard.payload["message"]

    targeted = run_internal_reader_state_evaluation(
        config,
        client_name="fake",
        synthesis_packet=synthesis_packet_dir,
        target_candidate_packet=residual_packet_dir,
    )
    assert targeted.exit_code == 0
    assert targeted.payload["accepted"] is True
    assert targeted.payload["counts"]["model_calls"] == 0
    assert targeted.payload["selected_candidate_packet_id"] == residual.payload["packet_id"]
    assert targeted.payload["evaluated_candidate_packet_id"] == residual.payload["packet_id"]
    assert targeted.payload["evaluated_candidate_is_provisional"] is True
    assert targeted.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert targeted.payload["proof_packet_id"] == proof.payload["packet_id"]
    assert targeted.payload["target_scope"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert targeted.payload["target_movement"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert targeted.payload["reader_state_eval_reason"] == (
        "supersession_pending_reader_state"
    )
    assert targeted.payload["candidate_generated"] is False
    assert targeted.payload["finalization_eligible"] is False
    assert targeted.payload["no_phase_shift_claim"] is True
    assert targeted.payload["next_recommended_action"] == (
        "review_provisional_residual_reader_state_eval_before_synthesis"
    )

    reader_packet_dir = Path(str(targeted.payload["packet_dir"]))
    manifest = read_payload(
        reader_packet_dir / "internal_reader_state_eval_subject_manifest.json"
    )
    assert manifest["selected_candidate_packet_id"] == residual.payload["packet_id"]
    assert manifest["evaluated_candidate_packet_id"] == residual.payload["packet_id"]
    assert manifest["evaluated_candidate_is_provisional"] is True
    assert manifest["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert manifest["proof_packet_id"] == proof.payload["packet_id"]
    assert manifest["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert manifest["target_unit_ids"]

    reader_subject = read_payload(
        reader_packet_dir / "selected_candidate_reader_subject.json"
    )
    assert reader_subject["evaluation_subject"] == (
        "targeted_provisional_residual_candidate"
    )
    assert reader_subject["selected_macro_candidate"]["packet_id"] == residual.payload[
        "packet_id"
    ]
    assert reader_subject["selected_macro_candidate"]["packet_id"] != chain["object_event"][
        "packet_id"
    ]
    assert reader_subject["current_best_candidate"]["packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert reader_subject["selected_macro_candidate"]["proof_packet_id"] == proof.payload[
        "packet_id"
    ]

    packet = read_payload(reader_packet_dir / "internal_reader_state_eval_packet.json")
    assert packet["accepted"] is True
    assert packet["selected_candidate_packet_id"] == residual.payload["packet_id"]
    assert packet["evaluated_candidate_is_provisional"] is True
    assert packet["current_best_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert packet["proof_packet_id"] == proof.payload["packet_id"]
    assert packet["candidate_generated"] is False
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True
    assert packet["next_recommended_action"] == (
        "review_provisional_residual_reader_state_eval_before_synthesis"
    )

    gate = read_payload(reader_packet_dir / "internal_reader_state_eval_gate_report.json")
    gate_results = {item["gate_name"]: item for item in gate["gate_results"]}
    assert gate_results["synthesis_packet_consumed"]["passed"] is True
    assert gate_results["target_candidate_resolved"]["passed"] is True
    assert gate_results["provisional_candidate_targeted"]["passed"] is True
    assert gate_results["proof_packet_linked"]["passed"] is True
    assert gate_results["selected_candidate_evaluated"]["passed"] is True
    assert gate_results["first_pass_trace_exists"]["passed"] is True
    assert gate_results["reread_trace_exists"]["passed"] is True
    assert gate_results["reader_delta_report_exists"]["passed"] is True
    assert gate_results["rival_reader_state_comparison_exists"]["passed"] is True
    assert gate_results["no_unresolved_internal_blockers"]["passed"] is False
    assert gate_results["no_fixture_only_core_evidence"]["passed"] is False
    assert gate_results["strongest_rival_defeated"]["passed"] is False
    assert gate_results["human_validation_present"]["passed"] is False
    assert gate_results["finalization_eligible"]["passed"] is False
    assert gate_results["no_final_claim"]["passed"] is True
    assert gate_results["no_phase_shift_claim"]["passed"] is True
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_adjudicates_targeted_residual_reader_state(
    tmp_path,
):
    chain = build_residual_candidate_authorization_chain(tmp_path)
    config = chain["config"]
    run_id = chain["run_id"]
    residual = run_residual_candidate_generation(
        config,
        client_name="openai",
        authorization_packet=Path(
            str(chain["residual_generation_authorization"]["packet_dir"])
        ),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=1,
        model="stub-object-motion-model",
        client_factory=object_motion_causality_stub_factory([]),
    )
    assert residual.exit_code == 0
    assert residual.payload["accepted"] is True

    proof = run_executed_ablation(
        config,
        client_name="openai",
        revision_packet=residual.payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-executed-ablation-model",
        client_factory=executed_ablation_stub_factory([]),
    )
    assert proof.exit_code == 0
    assert proof.payload["accepted"] is True
    _rewrite_macro2_proof(proof.payload, useful=True)

    pre_reader_synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert pre_reader_synthesis.exit_code == 0
    assert pre_reader_synthesis.payload["accepted"] is True
    assert pre_reader_synthesis.payload["best_current_candidate"]["packet_id"] == chain[
        "object_event"
    ]["packet_id"]

    def _reader_state_client_factory(model: str) -> FakeInternalReaderLabModelClient:
        return FakeInternalReaderLabModelClient(provider="openai", model=model)

    targeted = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=Path(str(pre_reader_synthesis.payload["packet_dir"])),
        target_candidate_packet=Path(str(residual.payload["packet_dir"])),
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=5,
        model="stub-reader-state-model",
        client_factory=_reader_state_client_factory,
    )
    assert targeted.exit_code == 0
    assert targeted.payload["accepted"] is True
    assert targeted.payload["counts"]["model_calls"] == 5
    assert targeted.payload["evaluated_candidate_packet_id"] == residual.payload["packet_id"]
    assert targeted.payload["selected_candidate_packet_id"] == residual.payload["packet_id"]
    assert targeted.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert targeted.payload["proof_packet_id"] == proof.payload["packet_id"]
    assert targeted.payload["evaluated_candidate_is_provisional"] is True
    assert targeted.payload["target_scope"] == OBJECT_MOTION_CAUSALITY_TARGET_ID

    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert targeted.payload["packet_id"] in manifest[
        "residual_candidate_reader_state_evaluation_packets_consumed"
    ]
    assert targeted.payload["packet_id"] in manifest[
        "reader_state_evaluation_packets_consumed"
    ]

    history = read_payload(packet_dir / "repair_history_table.json")
    residual_row = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "bounded_macro_recomposition"
        and row["packet_id"] == residual.payload["packet_id"]
    ][0]
    assert residual_row["proof_packet_id"] == proof.payload["packet_id"]
    assert residual_row["proof_backed"] is True
    assert residual_row["reader_state_evaluated"] is True
    assert residual_row["reader_state_packet_id"] == targeted.payload["packet_id"]
    assert residual_row["selected_residual_target_id"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert residual_row["selected_region_id"] == RESIDUAL_WORK_ORDER_SELECTED_REGION_ID
    assert residual_row["strongest_rival_still_blocks"] is True
    assert residual_row["finalization_eligible"] is False
    assert residual_row["supersession_decision"] == "ready_for_synthesis_adjudication"

    reader_row = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "internal_reader_state_evaluation"
        and row["packet_id"] == targeted.payload["packet_id"]
    ][0]
    assert reader_row["evaluated_candidate_packet_id"] == residual.payload["packet_id"]
    assert reader_row["selected_candidate_packet_id"] == residual.payload["packet_id"]
    assert reader_row["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert reader_row["proof_packet_id"] == proof.payload["packet_id"]

    causal = read_payload(packet_dir / "causal_status_summary.json")
    assert residual.payload["packet_id"] not in causal[
        "residual_candidate_proof_backed_pending_packet_ids"
    ]
    assert residual.payload["packet_id"] in causal[
        "residual_candidate_reader_state_evaluated_packet_ids"
    ]
    assert targeted.payload["packet_id"] in causal[
        "residual_candidate_reader_state_packet_ids"
    ]
    assert causal["residual_candidate_proof_backed_pending_detected"] is False
    assert causal["residual_candidate_reader_state_evaluated_detected"] is True

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == residual.payload["packet_id"]
    assert selected["proof_packet_id"] == proof.payload["packet_id"]
    assert selected["reader_state_packet_id"] == targeted.payload["packet_id"]
    assert selected["reader_state_evaluated"] is True
    assert selected["selected_residual_candidate"] is True
    assert best["best_current_candidate_updated_from_residual_reader_state"] is True

    graph = read_payload(packet_dir / "candidate_evidence_graph.json")
    nodes = {node["candidate_packet_id"]: node for node in graph["nodes"]}
    assert chain["object_event"]["packet_id"] in nodes
    assert residual.payload["packet_id"] in nodes
    residual_node = nodes[residual.payload["packet_id"]]
    assert residual_node["proof_packet_id"] == proof.payload["packet_id"]
    assert residual_node["proof_backed"] is True
    assert residual_node["reader_state_packet_id"] == targeted.payload["packet_id"]
    assert residual_node["reader_state_evaluated"] is True
    assert residual_node["target_scope"] == OBJECT_MOTION_CAUSALITY_TARGET_ID
    assert residual_node["strongest_rival_still_blocks"] is True
    assert residual_node["finalization_eligible"] is False
    assert targeted.payload["packet_id"] != nodes[chain["object_event"]["packet_id"]].get(
        "reader_state_packet_id"
    )

    queue = read_payload(packet_dir / "provisional_candidate_queue.json")
    assert queue["pending_candidate_count"] == 0
    assert queue["proof_backed_pending_count"] == 0
    contender = [
        candidate
        for candidate in queue["evaluated_contenders"]
        if candidate["packet_id"] == residual.payload["packet_id"]
    ][0]
    assert contender["proof_backed"] is True
    assert contender["reader_state_evaluated"] is True
    assert contender["reader_state_packet_id"] == targeted.payload["packet_id"]
    assert contender["supersession_pending_reader_state"] is False
    assert contender["ready_for_synthesis_adjudication"] is True
    assert queue["next_recommended_action"] == (
        "review_residual_candidate_synthesis_before_loop_review"
    )
    assert "another reader-state run" in queue["supersession_policy"]

    adjudication = read_payload(
        packet_dir / "residual_candidate_reader_state_adjudication.json"
    )
    assert adjudication["residual_candidate_reader_state_evidence_present"] is True
    assert adjudication["candidate_packet_id"] == residual.payload["packet_id"]
    assert adjudication["proof_packet_id"] == proof.payload["packet_id"]
    assert adjudication["reader_state_packet_id"] == targeted.payload["packet_id"]
    assert adjudication["reader_state_evaluated"] is True
    assert adjudication["residual_candidate_reader_state_consumed"] is True
    assert adjudication["residual_candidate_reader_state_linked"] is True
    assert adjudication["residual_candidate_supersession_adjudicated"] is True
    assert adjudication["candidate_selected_as_best_current"] is True
    assert adjudication["strongest_rival_still_blocks"] is True
    assert adjudication["finalization_eligible"] is False
    assert adjudication["no_phase_shift_claim"] is True

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    blocker_ids = {blocker["blocker_id"] for blocker in blockers["residual_blockers"]}
    assert f"reader_state_evaluation_missing_for_{residual.payload['packet_id']}" not in (
        blocker_ids
    )
    assert (
        f"{OBJECT_MOTION_CAUSALITY_TARGET_ID}_reader_state_evidence_consumed_for_"
        f"{residual.payload['packet_id']}"
    ) in blocker_ids
    assert blockers["residual_candidate_reader_state_missing"] is False
    assert blockers["residual_candidate_reader_state_evidence_consumed"] is True
    assert blockers["residual_candidate_reader_state_linked"] is True
    assert blockers["residual_candidate_next_required_evidence"] is None

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["recommendation"] == (
        "preserve_residual_candidate_and_pause_for_loop_review"
    )
    assert decision["next_recommended_action"] == (
        "review_residual_candidate_synthesis_before_loop_review"
    )
    assert decision["residual_candidate_reader_state_evidence_consumed"] is True
    assert decision["residual_candidate_reader_state_packet_id"] == targeted.payload[
        "packet_id"
    ]
    assert decision["residual_candidate_supersession_adjudicated"] is True
    assert decision["internal_reader_state_evaluation_recommended"] is False
    assert decision["no_phase_shift_claim"] is True

    brief = read_payload(packet_dir / "macro_recomposition_brief.json")
    assert brief["brief_type"] == "residual_candidate_synthesis_review_brief_not_artifact"
    assert brief["current_best_candidate_packet_id"] == residual.payload["packet_id"]
    assert brief["proof_basis_packet_id"] == proof.payload["packet_id"]
    assert brief["reader_state_packet_id"] == targeted.payload["packet_id"]
    assert brief["next_evidence_need"] == "operator_loop_review"
    assert brief["run_internal_reader_state_evaluation_before_further_recomposition"] is False
    assert brief["run_another_macro_recomposition_now"] is False
    assert brief["run_another_local_patch_now"] is False

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "residual_candidate_proof_consumed",
        "residual_candidate_reader_state_consumed",
        "residual_candidate_reader_state_linked",
        "candidate_evidence_graph_created",
        "residual_candidate_supersession_adjudicated",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    assert gate["residual_candidate_reader_state_missing"] is False
    assert gate["residual_candidate_reader_state_consumed"] is True
    assert gate["residual_candidate_reader_state_linked"] is True
    assert gate["candidate_evidence_graph_created"] is True
    assert gate["residual_candidate_supersession_adjudicated"] is True
    assert gate["finalization_eligible"] is False
    assert gate["passed"] is False

    packet = read_payload(packet_dir / "autonomous_evidence_synthesis_packet.json")
    assert packet["best_current_candidate"]["packet_id"] == residual.payload["packet_id"]
    assert targeted.payload["packet_id"] in packet[
        "residual_candidate_reader_state_evaluation_packets_consumed"
    ]
    assert packet["residual_candidate_reader_state_consumed"] is True
    assert packet["residual_candidate_reader_state_linked"] is True
    assert packet["residual_candidate_reader_state_missing"] is False
    assert packet["next_recommended_action"] == (
        "review_residual_candidate_synthesis_before_loop_review"
    )
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_links_object_event_reader_state_by_hash(
    tmp_path,
):
    chain = build_object_event_candidate_with_reader_state(
        tmp_path,
        strip_reader_identity_to_hash_only=True,
    )
    config = chain["config"]
    run_id = chain["run_id"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_autonomous_evidence_synthesis(config, run_id=run_id)

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "autonomous_evidence_synthesis_subject_manifest.json")
    assert chain["object_event_reader_state"]["packet_id"] in manifest[
        "object_event_reader_state_evaluation_packets_consumed"
    ]

    history = read_payload(packet_dir / "repair_history_table.json")
    reader_row = [
        row
        for row in history["repair_events"]
        if row["packet_kind"] == "internal_reader_state_evaluation"
        and row["packet_id"] == chain["object_event_reader_state"]["packet_id"]
    ][0]
    assert reader_row["source_synthesis_packet_id"] == "packet_stale_source_for_hash_link_test"
    assert reader_row["selected_candidate_packet_id"] == ""
    assert reader_row["selected_candidate_packet_dir"] == ""
    assert reader_row["selected_candidate_text_sha256"] == chain[
        "object_event_candidate_text_sha256"
    ]

    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["object_event"]["packet_id"]
    assert selected["reader_state_evaluated"] is True
    assert selected["reader_state_packet_id"] == chain["object_event_reader_state"]["packet_id"]
    assert selected["reader_state_selected_candidate_text_sha256"] == chain[
        "object_event_candidate_text_sha256"
    ]
    assert selected["reader_state_strongest_rival_still_blocks"] is True

    adjudication = read_payload(packet_dir / "reader_state_evidence_adjudication.json")
    assert adjudication["packet_id"] == chain["object_event_reader_state"]["packet_id"]
    assert adjudication["selected_candidate_packet_id"] == ""
    assert adjudication["selected_candidate_text_sha256"] == chain[
        "object_event_candidate_text_sha256"
    ]
    assert adjudication["selected_object_event_candidate"] is True
    assert adjudication["object_event_pressure_gain_status"] == "improved_but_insufficient"

    decision = read_payload(packet_dir / "strategic_decision_report.json")
    assert decision["next_recommended_action"] == (
        "review_object_event_reader_state_synthesis_before_new_candidate"
    )
    assert decision["next_recommended_action"] != (
        "run_internal_reader_state_evaluation_on_object_event_candidate"
    )

    blockers = read_payload(packet_dir / "residual_blocker_map.json")
    blocker_ids = {blocker["blocker_id"] for blocker in blockers["residual_blockers"]}
    assert f"reader_state_evaluation_needed_for_{chain['object_event']['packet_id']}" not in (
        blocker_ids
    )
    assert blockers["object_event_reader_state_evidence_consumed"] is True

    gate = read_payload(packet_dir / "synthesis_gate_report.json")
    assert gate["object_event_reader_state_evidence_consumed"] is True
    assert gate["object_event_reader_state_eval_linked"] is True
    assert gate["passed"] is False

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_stale_recommendation_detector_catches_reader_state_eval_after_packet_exists():
    report = detect_stale_recommendations(
        selected_candidate={
            "packet_id": "packet_candidate",
            "reader_state_packet_id": "packet_reader_state",
        },
        synthesis_packet={
            "object_event_reader_state_eval_needed": True,
            "next_recommended_action": "run_object_event_reader_state_evaluation",
        },
        source_chain=[],
        reader_state_packet={"packet_id": "packet_reader_state"},
    )

    assert report["stale_recommendation_detected"] is True
    assert report["stale_recommendations"][0]["stale_recommendation_type"] == (
        "reader_state_eval_needed_but_packet_exists"
    )


def test_stale_recommendation_detector_catches_strategy_after_candidate_exists():
    report = detect_stale_recommendations(
        selected_candidate={
            "packet_id": "packet_candidate",
            "source_strategy_packet_id": "packet_strategy",
        },
        synthesis_packet={"next_recommended_action": "prepare_next_target_strategy"},
        source_chain=[
            {
                "packet_kind": "bounded_macro_recomposition",
                "packet_id": "packet_candidate",
                "source_strategy_packet_id": "packet_strategy",
            }
        ],
        strategy_packet={"packet_id": "packet_strategy"},
    )

    assert report["stale_recommendation_detected"] is True
    assert report["stale_recommendations"][0]["stale_recommendation_type"] == (
        "strategy_needed_but_strategy_or_candidate_exists"
    )


def test_proof_before_next_generation_guard_blocks_when_loop_cleanup_required():
    guard = build_proof_before_next_generation_guard(
        selected_candidate={
            "packet_id": "packet_candidate",
            "proof_packet_id": "packet_proof",
            "reader_state_packet_id": "packet_reader_state",
        },
        proof_packet={"packet_id": "packet_proof"},
        reader_state_packet={"packet_id": "packet_reader_state"},
        latest_loop_review_requires_cleanup_first=True,
        prior_generated_candidate_synthesized=True,
        stale_recommendation_active=False,
    )

    assert guard["next_generation_authorized"] is False
    assert guard["proof_status_current"] is True
    assert guard["reader_state_status_current"] is True
    assert "latest loop review requires cleanup before generation" in guard[
        "next_generation_blockers"
    ]


def test_repeated_target_drift_guard_flags_stale_target_repetition():
    guard = build_repeated_target_drift_guard(
        current_target_class="proof_no_answer_compression",
        previous_target_class="proof_no_answer_compression",
        evidence_shifted_to_target_class="first_read_object_event_pressure_gap",
        loop_integrity_cleanup_required=True,
    )

    assert guard["repeated_target_drift_detected"] is True
    finding_ids = {finding["finding_id"] for finding in guard["findings"]}
    assert "target_repeated_after_evidence_shift" in finding_ids
    assert "target_recommended_while_loop_cleanup_required" in finding_ids


def test_evidence_loop_review_accepts_completed_object_event_loop(tmp_path):
    chain = build_object_event_candidate_with_reader_state(tmp_path)
    config = chain["config"]
    synthesis = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])
    assert synthesis.exit_code == 0
    assert synthesis.payload["best_current_candidate"]["packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert synthesis.payload["best_current_candidate"]["reader_state_evaluated"] is True
    with connect(chain["config"].db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_evidence_loop_review(
        chain["config"],
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert set(result.payload["artifact_ids"]) == set(EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES)
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert result.payload["completed_cycles"] == 2
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["counts"]["produced_artifacts"] == len(
        EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES
    )
    assert result.payload["candidate_generated"] is False
    assert result.payload["model_calls"] == 0
    assert result.payload["loop_controller_ready"] is False
    assert result.payload["ready_for_full_autonomous_loop_controller"] is False
    assert result.payload["ready_for_supervised_next_cycle"] is False
    assert result.payload["loop_integrity_cleanup_required"] is True
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["next_generation_blockers"]
    assert result.payload["next_recommended_action"] == (
        "prepare_loop_integrity_cleanup_before_more_generation"
    )
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "evidence_loop_review_subject_manifest.json")
    assert manifest["source_synthesis_packet_id"] == synthesis.payload["packet_id"]
    assert manifest["current_best_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert manifest["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert manifest["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert manifest["prior_best_packet_id"] == chain["macro2"]["packet_id"]
    assert manifest["strongest_rival_still_blocks"] is True
    assert manifest["finalization_eligible"] is False
    assert manifest["no_phase_shift_claim"] is True

    cycle_map = read_payload(packet_dir / "completed_cycle_map.json")
    cycle_ids = {cycle["cycle_id"] for cycle in cycle_map["cycles"]}
    assert cycle_ids == {
        "cycle_a_macro2_reader_state",
        "cycle_b_object_event_reader_state",
    }
    cycle_by_id = {cycle["cycle_id"]: cycle for cycle in cycle_map["cycles"]}
    assert cycle_by_id["cycle_a_macro2_reader_state"]["candidate_packet_id"] == chain[
        "macro2"
    ]["packet_id"]
    assert cycle_by_id["cycle_a_macro2_reader_state"]["proof_packet_id"] == chain[
        "macro2_proof"
    ]["packet_id"]
    assert cycle_by_id["cycle_a_macro2_reader_state"]["reader_state_packet_id"] == chain[
        "macro2_reader_state"
    ]["packet_id"]
    assert cycle_by_id["cycle_b_object_event_reader_state"]["strategy_packet_id"] == chain[
        "next_target_strategy"
    ]["packet_id"]
    assert cycle_by_id["cycle_b_object_event_reader_state"]["candidate_packet_id"] == chain[
        "object_event"
    ]["packet_id"]
    assert cycle_by_id["cycle_b_object_event_reader_state"]["proof_packet_id"] == chain[
        "object_event_proof"
    ]["packet_id"]
    assert cycle_by_id["cycle_b_object_event_reader_state"]["reader_state_packet_id"] == chain[
        "object_event_reader_state"
    ]["packet_id"]

    best = read_payload(packet_dir / "current_best_candidate_review.json")
    assert best["selected_best_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert best["proof_linked"] is True
    assert best["reader_state_evaluated"] is True
    assert best["evidence_status"] == (
        "useful_but_insufficient_with_partial_internal_reader_state_support"
    )
    assert any("strongest rival" in item for item in best["what_remains_unresolved"])
    assert any("operator approval" in item for item in best["why_not_final"])
    assert any("loop-level review" in item for item in best["why_immediate_generation_not_authorized"])

    quality = read_payload(packet_dir / "evidence_quality_review.json")
    assert quality["evidence_quality"]["candidate_model_backed"] is True
    assert quality["evidence_quality"]["proof_model_backed"] is True
    assert quality["evidence_quality"]["countable_ablation_evidence_exists"] is True
    assert quality["evidence_quality"]["reader_state_evaluation_exists"] is True
    assert quality["evidence_quality"][
        "reader_state_is_internal_model_evidence_not_human_data"
    ] is True
    assert quality["nonblocking_integrity_classification"] == (
        "loop_automation_cleanup_not_creative_blocker"
    )

    progress = read_payload(packet_dir / "reader_state_progress_review.json")
    assert progress["progress_classification"]["object_event_pressure"] == (
        "improved_but_insufficient"
    )
    assert progress["progress_classification"]["reread_transformation"] == "partial"
    assert progress["progress_classification"]["strongest_rival"] == "still_blocks"
    assert progress["table_dust_spoon_saucer_ring_causal_field_strengthened"] is True

    rival = read_payload(packet_dir / "strongest_rival_status_review.json")
    assert rival["strongest_rival_still_blocks"] is True
    assert rival["strongest_rival_comparison_passed"] is False
    assert rival["no_rival_defeat_claim"] is True
    assert "first-read vividness" in rival["rival_still_wins_on"]

    taxonomy = read_payload(packet_dir / "residual_blocker_taxonomy.json")
    blocker_ids = {blocker["blocker_id"] for blocker in taxonomy["ranked_blockers"]}
    assert "strongest_rival_still_winning" in blocker_ids
    assert "reader_state_gain_still_partial" in blocker_ids
    assert "artifact_count_or_packet_summary_cleanup_needed" in blocker_ids
    assert "strongest_rival_still_winning" in taxonomy["creative_blockers"]
    assert "loop_automation_not_ready" in taxonomy["automation_blockers"]

    drift = read_payload(packet_dir / "drift_risk_report.json")
    assert drift["immediate_new_generation_authorized"] is False
    assert drift["next_generation_authorized"] is False
    assert drift["loop_integrity_cleanup_required"] is True
    assert "high" in drift["immediate_new_generation_risk"]
    assert chain["object_event_reader_state"]["packet_id"] in (
        drift["why_immediate_reader_state_eval_would_be_redundant"]
    )
    assert chain["object_event_proof"]["packet_id"] in (
        drift["why_immediate_ablation_would_be_redundant"]
    )
    assert drift["freshness_report"]["stale_recommendation_detected"] is False
    assert drift["proof_before_next_generation_guard"]["proof_status_current"] is True
    assert drift["proof_before_next_generation_guard"][
        "reader_state_status_current"
    ] is True
    assert drift["proof_before_next_generation_guard"][
        "next_generation_authorized"
    ] is False
    assert "latest loop review requires cleanup before generation" in drift[
        "proof_before_next_generation_guard"
    ]["next_generation_blockers"]
    assert drift["reader_state_before_synthesis_guard"][
        "reader_state_before_synthesis_warning"
    ] is False
    assert drift["repeated_target_drift_guard"][
        "repeated_target_drift_detected"
    ] is True
    assert drift["candidate_generated"] is False

    integrity = read_payload(packet_dir / "loop_integrity_report.json")
    assert integrity["ready_for_full_autonomous_loop"] is False
    assert integrity["ready_for_full_autonomous_loop_controller"] is False
    assert integrity["ready_for_supervised_next_cycle"] is False
    assert integrity["loop_integrity_cleanup_required"] is True
    assert integrity["next_generation_authorized"] is False
    assert integrity["next_generation_blockers"]
    assert integrity["cleanup_blockers"]
    assert integrity["automation_blockers"]
    assert "loop_controller_not_ready_for_full_autonomy" in integrity["conclusions"]
    assert integrity["checks"]["loop_review_command_exists"] is True
    assert integrity["checks"]["command_output_shape_aliases_present"] is True
    assert integrity["checks"]["manual_operator_still_required"] is True

    decision = read_payload(packet_dir / "next_action_decision.json")
    assert decision["recommended_next_action"] == (
        "prepare_loop_integrity_cleanup_before_more_generation"
    )
    assert decision["immediate_creative_generation_authorized"] is False
    assert decision["immediate_ablation_authorized"] is False
    assert decision["immediate_reader_state_eval_authorized"] is False
    assert decision["next_generation_authorized"] is False
    assert decision["loop_integrity_cleanup_required"] is True
    assert decision["next_generation_blockers"]
    assert decision["cleanup_blockers"]
    assert decision["automation_blockers"]

    readiness = read_payload(packet_dir / "loop_controller_readiness_report.json")
    assert readiness["ready_for_full_autonomous_loop_controller"] is False
    assert readiness["ready_for_autonomous_loop_controller"] is False
    assert readiness["ready_for_supervised_next_cycle"] is False
    assert readiness["loop_integrity_cleanup_required"] is True
    assert readiness["next_generation_authorized"] is False
    assert "finalization never auto-passes" in readiness["required_before_loop_controller"]
    assert "no finalization authority" in readiness["recommended_loop_controller_scope_if_later"]

    gate = read_payload(packet_dir / "evidence_loop_review_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "source_synthesis_consumed",
        "current_best_candidate_identified",
        "proof_packet_linked",
        "reader_state_packet_linked",
        "completed_cycles_mapped",
        "residual_blockers_classified",
        "drift_risk_assessed",
        "loop_integrity_reviewed",
        "no_candidate_generated",
        "no_openai_calls",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "autonomous_loop_controller_ready",
        "next_candidate_authorized",
        "no_unresolved_internal_blockers",
        "internal_operator_approval",
        "finalization_eligible",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["passed"] is False
    assert gate["next_generation_authorized"] is False
    assert gate["loop_integrity_cleanup_required"] is True
    assert gate["cleanup_blockers"]
    assert gate["automation_blockers"]
    assert gate["candidate_generated"] is False
    assert gate["model_calls"] == 0
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "evidence_loop_review_packet.json")
    assert packet["current_best_candidate_packet_id"] == chain["object_event"]["packet_id"]
    assert packet["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert packet["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert packet["completed_cycle_count"] == 2
    assert packet["counts"]["model_calls"] == 0
    assert packet["counts"]["produced_artifacts"] == len(EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES)
    assert packet["counts"]["required_artifacts"] == len(EVIDENCE_LOOP_REVIEW_ARTIFACT_TYPES)
    assert packet["loop_integrity_cleanup_required"] is True
    assert packet["next_generation_authorized"] is False
    assert packet["next_generation_blockers"]
    assert packet["candidate_generated"] is False
    assert packet["model_calls"] == 0
    assert packet["loop_controller_ready"] is False
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_loop_integrity_cleanup_refuses_without_operator_review(tmp_path):
    chain = build_completed_residual_loop_review_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_loop_integrity_cleanup(
        config,
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=False,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "--operator-reviewed" in result.payload["message"]
    assert result.payload["artifact_ids"] == {}
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["finalization_eligible"] is False
    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
    assert len(after_calls) == len(before_calls)


def test_loop_integrity_cleanup_accepts_completed_residual_cycle(tmp_path):
    chain = build_completed_residual_loop_review_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_loop_integrity_cleanup(
        config,
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["refused"] is False
    assert set(result.payload["artifact_ids"]) == set(
        LOOP_INTEGRITY_CLEANUP_ARTIFACT_TYPES
    )
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["counts"]["produced_artifacts"] == len(
        LOOP_INTEGRITY_CLEANUP_ARTIFACT_TYPES
    )
    assert result.payload["source_loop_review_packet_id"] == chain[
        "residual_loop_review"
    ]["packet_id"]
    assert result.payload["source_synthesis_packet_id"] == chain["residual_synthesis"][
        "packet_id"
    ]
    assert result.payload["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert result.payload["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert result.payload["loop_integrity_cleanup_completed"] is True
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["ready_for_supervised_strategy_authorization"] is True
    assert result.payload["ready_for_supervised_candidate_generation"] is False
    assert result.payload["ready_for_full_autonomous_loop_controller"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True
    assert result.payload["next_recommended_action"] == (
        "authorize_next_strategy_only_from_loop_cleanup"
    )

    packet_dir = Path(str(result.payload["packet_dir"]))
    manifest = read_payload(packet_dir / "loop_integrity_cleanup_subject_manifest.json")
    assert manifest["loop_review_packet_id"] == chain["residual_loop_review"]["packet_id"]
    assert manifest["source_synthesis_packet_id"] == chain["residual_synthesis"][
        "packet_id"
    ]
    assert manifest["current_best_candidate_packet_id"] == chain["residual_candidate"][
        "packet_id"
    ]
    assert manifest["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert manifest["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert manifest["candidate_generated"] is False
    assert manifest["model_calls"] == 0
    assert manifest["next_generation_authorized"] is False
    assert manifest["finalization_eligible"] is False
    assert manifest["no_phase_shift_claim"] is True

    checkpoint = read_payload(packet_dir / "active_evidence_state_checkpoint.json")
    assert checkpoint["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert checkpoint["current_best_candidate_kind"] == "bounded_macro_recomposition"
    assert checkpoint["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert checkpoint["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert checkpoint["synthesis_packet_id"] == chain["residual_synthesis"]["packet_id"]
    assert checkpoint["loop_review_packet_id"] == chain["residual_loop_review"][
        "packet_id"
    ]
    assert checkpoint["current_best_candidate_finalization_eligible"] is False
    assert checkpoint["reader_state_transformation_strength"] == "partial"
    assert checkpoint["strongest_rival_still_blocks"] is True
    assert checkpoint[
        "preferred_source_for_future_supervised_strategy_authorization"
    ] is True
    assert checkpoint["finalization_eligible"] is False
    assert checkpoint["no_phase_shift_claim"] is True

    stale = read_payload(packet_dir / "stale_recommendation_registry.json")
    entries = stale["stale_recommendations"]
    assert stale["active_current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert stale["older_packet_0059_object_event_path_superseded"] is True
    assert stale["consumed_generation_authorization_not_reusable"] is True
    assert stale["residual_work_order_not_reusable"] is True
    assert any(
        entry["reference_type"] == "prior_best_candidate"
        and entry["reference_packet_id"] == chain["object_event"]["packet_id"]
        and entry["status"] == "superseded"
        for entry in entries
    )
    assert any(
        entry["reference_type"] == "residual_generation_authorization"
        and entry["reference_packet_id"]
        == chain["residual_generation_authorization"]["packet_id"]
        and entry["reuse_allowed_for_new_generation"] is False
        for entry in entries
    )
    assert any(
        entry["reference_type"] == "residual_work_order"
        and entry["reference_packet_id"] == chain["residual_work_order"]["packet_id"]
        and entry["reuse_allowed_for_new_generation"] is False
        for entry in entries
    )

    supersession = read_payload(packet_dir / "prior_cycle_supersession_map.json")
    assert supersession["macro_2_cycle_led_to_packet_id"] == chain["macro2"]["packet_id"]
    assert supersession["object_event_cycle_led_to_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert supersession["residual_object_motion_cycle_led_to_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert supersession["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert supersession["superseded_prior_best_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert supersession["current_best_supersedes_prior_best"] is True
    assert supersession["strongest_rival_defeated"] is False
    assert supersession["strongest_rival_still_blocks"] is True
    assert supersession["current_best_is_final"] is False

    policy = read_payload(packet_dir / "next_command_safety_policy.json")
    assert policy["allowed_next_command_category"] == (
        "supervised_strategy_authorization_after_cleanup"
    )
    assert "generate candidate" in policy["disallowed_next_commands"]
    assert "ablate" in policy["disallowed_next_commands"]
    assert "reader-state-eval" in policy["disallowed_next_commands"]
    assert "synthesize" in policy["disallowed_next_commands"]
    assert "finalize" in policy["disallowed_next_commands"]
    assert "authorize generation" in policy["disallowed_next_commands"]
    assert "separate generation authorization" in policy["required_before_generation"]
    assert policy["loop_cleanup_packet_input_for_authorization_not_yet_wired"] is True
    assert policy["next_generation_authorized"] is False

    lock = read_payload(packet_dir / "generation_lock_report.json")
    assert lock["next_generation_authorized"] is False
    assert lock["previous_generation_authorization_consumed"] is True
    assert lock["consumed_generation_authorization_packet_id"] == chain[
        "residual_generation_authorization"
    ]["packet_id"]
    assert lock["current_best_candidate_has_complete_current_cycle_evidence"] is True
    assert lock["generation_locked_until_supervised_strategy"] is True
    assert lock["no_model_calls"] is True

    readiness = read_payload(packet_dir / "supervised_strategy_readiness_report.json")
    assert readiness["ready_for_supervised_strategy_authorization"] is True
    assert readiness["ready_for_supervised_candidate_generation"] is False
    assert readiness["ready_for_full_autonomous_loop_controller"] is False
    assert readiness["next_allowed_operator_decision"] == "authorize_next_strategy_only"
    assert "--loop-cleanup-packet" in readiness["recommended_next_command_after_cleanup"]
    assert readiness["candidate_generation_requires_later_authorization"] is True

    gate = read_payload(packet_dir / "loop_integrity_cleanup_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "loop_review_packet_consumed",
        "source_synthesis_resolved",
        "current_best_candidate_resolved",
        "proof_packet_linked",
        "reader_state_packet_linked",
        "active_evidence_state_checkpoint_created",
        "stale_recommendation_registry_created",
        "prior_cycle_supersession_map_created",
        "next_command_safety_policy_created",
        "generation_lock_recorded",
        "no_candidate_generated",
        "no_openai_calls",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "next_generation_authorized",
        "ready_for_full_autonomous_loop_controller",
        "finalization_eligible",
        "strongest_rival_defeated",
        "human_validation_present",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["passed"] is False
    assert gate["eligible"] is False
    assert gate["loop_integrity_cleanup_completed"] is True
    assert gate["ready_for_supervised_strategy_authorization"] is True
    assert gate["ready_for_supervised_candidate_generation"] is False
    assert gate["ready_for_full_autonomous_loop_controller"] is False
    assert gate["next_generation_authorized"] is False
    assert gate["candidate_generated"] is False
    assert gate["model_calls"] == 0
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True
    assert gate["strongest_rival_still_blocks"] is True
    assert gate["human_validation_present"] is False

    packet = read_payload(packet_dir / "loop_integrity_cleanup_packet.json")
    assert packet["current_best_candidate_packet_id"] == chain["residual_candidate"][
        "packet_id"
    ]
    assert packet["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert packet["reader_state_packet_id"] == chain["residual_reader_state"]["packet_id"]
    assert packet["source_synthesis_packet_id"] == chain["residual_synthesis"]["packet_id"]
    assert packet["source_loop_review_packet_id"] == chain["residual_loop_review"][
        "packet_id"
    ]
    assert packet["loop_integrity_cleanup_completed"] is True
    assert packet["next_generation_authorized"] is False
    assert packet["ready_for_supervised_strategy_authorization"] is True
    assert packet["ready_for_supervised_candidate_generation"] is False
    assert packet["ready_for_full_autonomous_loop_controller"] is False
    assert packet["candidate_generated"] is False
    assert packet["model_calls"] == 0
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True
    assert packet["next_recommended_action"] == (
        "authorize_next_strategy_only_from_loop_cleanup"
    )

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_loop_integrity_cleanup_accepts_target_aware_residual_cycle(tmp_path):
    chain = build_completed_tactile_residual_loop_review_chain(tmp_path)
    config = chain["config"]
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_loop_integrity_cleanup(
        config,
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["source_loop_review_packet_id"] == chain[
        "residual_loop_review"
    ]["packet_id"]
    assert result.payload["source_synthesis_packet_id"] == chain["residual_synthesis"][
        "packet_id"
    ]
    assert result.payload["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert result.payload["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert result.payload["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["target_adapter_id"] == "tactile_inevitability"
    assert result.payload["target_scope"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True

    packet_dir = Path(str(result.payload["packet_dir"]))
    manifest = read_payload(packet_dir / "loop_integrity_cleanup_subject_manifest.json")
    assert manifest["current_best_candidate_packet_id"] == chain["residual_candidate"][
        "packet_id"
    ]
    assert manifest["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert manifest["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert manifest["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert manifest["target_adapter_id"] == "tactile_inevitability"

    checkpoint = read_payload(packet_dir / "active_evidence_state_checkpoint.json")
    assert checkpoint["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert checkpoint["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert checkpoint["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert checkpoint["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert checkpoint["target_adapter_id"] == "tactile_inevitability"

    stale = read_payload(packet_dir / "stale_recommendation_registry.json")
    entries = stale["stale_recommendations"]
    assert any(
        entry["reference_type"] == "prior_best_candidate"
        and entry["reference_packet_id"] == chain["object_event"]["packet_id"]
        for entry in entries
    )
    assert any(
        entry["reference_type"] == "prior_best_proof"
        and entry["reference_packet_id"] == chain["object_event_proof"]["packet_id"]
        for entry in entries
    )
    assert any(
        entry["reference_type"] == "prior_best_reader_state"
        and entry["reference_packet_id"]
        == chain["object_event_reader_state"]["packet_id"]
        for entry in entries
    )
    assert any(
        entry["reference_type"] == "non_authoritative_proof_attempt"
        and entry["reference_packet_id"] == chain["generic_proof"]["packet_id"]
        and "target_aware_proof_required_for_residual_target"
        in entry["rejection_reasons"]
        for entry in entries
    )
    assert any(
        entry["reference_type"] == "non_authoritative_proof_attempt"
        and entry["reference_packet_id"] == chain["role_failed_proof"]["packet_id"]
        and "target_role_consistency_failed" in entry["rejection_reasons"]
        for entry in entries
    )
    assert any(
        entry["reference_type"] == "fixture_reader_state_attempt"
        and entry["reference_packet_id"] == chain["fixture_reader_state"]["packet_id"]
        for entry in entries
    )

    supersession = read_payload(packet_dir / "prior_cycle_supersession_map.json")
    assert supersession["active_target_cycle_led_to_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert supersession["active_target_cycle_proof_packet_id"] == chain[
        "residual_proof"
    ]["packet_id"]
    assert supersession["active_target_cycle_reader_state_packet_id"] == chain[
        "residual_reader_state"
    ]["packet_id"]
    assert supersession["active_target_cycle_target_id"] == (
        TACTILE_INEVITABILITY_TARGET_ID
    )
    assert supersession["active_target_cycle_adapter_id"] == "tactile_inevitability"

    packet = read_payload(packet_dir / "loop_integrity_cleanup_packet.json")
    assert packet["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert packet["target_adapter_id"] == "tactile_inevitability"
    assert packet["model_calls"] == 0
    assert packet["next_generation_authorized"] is False

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


@pytest.mark.parametrize(
    ("proof_key", "expected_message"),
    [
        ("generic_proof", "target-aware proof"),
        ("role_failed_proof", "target role consistency"),
        ("fixture_proof", "fixture-only"),
    ],
)
def test_loop_integrity_cleanup_refuses_invalid_target_aware_proof(
    tmp_path,
    proof_key,
    expected_message,
):
    chain = build_completed_tactile_residual_loop_review_chain(tmp_path)
    retarget_cleanup_chain_to_proof(chain, chain[proof_key])

    result = run_loop_integrity_cleanup(
        chain["config"],
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected_message in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["candidate_generated"] is False
    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_loop_integrity_cleanup_refuses_mismatched_source_synthesis(tmp_path):
    chain = build_completed_tactile_residual_loop_review_chain(tmp_path)
    synthesis_dir = Path(str(chain["residual_synthesis"]["packet_dir"]))

    def _mismatch_best(payload: dict[str, object]) -> None:
        payload["best_current_candidate"]["packet_id"] = chain["object_event"]["packet_id"]

    rewrite_payload(
        synthesis_dir / "autonomous_evidence_synthesis_packet.json",
        _mismatch_best,
    )

    result = run_loop_integrity_cleanup(
        chain["config"],
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "current best candidate mismatch" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["next_generation_authorized"] is False


def test_cleanup_aware_authorization_refuses_invalid_source_flags(tmp_path):
    config = config_for(tmp_path)

    neither = run_supervised_cycle_authorization(
        config,
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert neither.exit_code == 1
    assert neither.payload["accepted"] is False
    assert "exactly one" in neither.payload["message"]
    assert neither.payload["next_generation_authorized"] is False

    chain = build_completed_residual_loop_review_chain(tmp_path / "both")
    cleanup = run_loop_integrity_cleanup(
        chain["config"],
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )
    assert cleanup.exit_code == 0

    both = run_supervised_cycle_authorization(
        chain["config"],
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        loop_cleanup_packet=Path(str(cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert both.exit_code == 1
    assert both.payload["accepted"] is False
    assert "exactly one" in both.payload["message"]
    assert both.payload["candidate_generated"] is False
    assert both.payload["counts"]["model_calls"] == 0


def test_cleanup_aware_authorization_refuses_without_operator_review(tmp_path):
    chain = build_completed_residual_loop_review_chain(tmp_path)
    cleanup = run_loop_integrity_cleanup(
        chain["config"],
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )
    assert cleanup.exit_code == 0

    result = run_supervised_cycle_authorization(
        chain["config"],
        loop_cleanup_packet=Path(str(cleanup.payload["packet_dir"])),
        operator_reviewed=False,
        decision="authorize_next_strategy_only",
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "--operator-reviewed" in result.payload["message"]
    assert result.payload["loop_cleanup_packet"] == str(Path(cleanup.payload["packet_dir"]))
    assert result.payload["next_strategy_authorized"] is False
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["counts"]["model_calls"] == 0


def test_cleanup_aware_authorization_accepts_latest_cleanup_and_blocks_reuse(tmp_path):
    chain = build_completed_residual_loop_review_chain(tmp_path)
    config = chain["config"]
    first_cleanup = run_loop_integrity_cleanup(
        config,
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )
    assert first_cleanup.exit_code == 0
    second_cleanup = run_loop_integrity_cleanup(
        config,
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )
    assert second_cleanup.exit_code == 0

    stale = run_supervised_cycle_authorization(
        config,
        loop_cleanup_packet=Path(str(first_cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert stale.exit_code == 1
    assert stale.payload["accepted"] is False
    assert "stale" in stale.payload["message"]
    assert str(second_cleanup.payload["packet_dir"]) in stale.payload["message"]

    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_supervised_cycle_authorization(
        config,
        loop_cleanup_packet=Path(str(second_cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["source_kind"] == "loop_cleanup"
    assert result.payload["source_loop_cleanup_packet_id"] == second_cleanup.payload[
        "packet_id"
    ]
    assert result.payload["cleanup_checkpoint_consumed"] is True
    assert result.payload["source_loop_review_packet_id"] == chain[
        "residual_loop_review"
    ]["packet_id"]
    assert result.payload["source_synthesis_packet_id"] == chain["residual_synthesis"][
        "packet_id"
    ]
    assert result.payload["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert result.payload["current_best_candidate_packet_id"] != chain["object_event"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert result.payload["next_strategy_authorized"] is True
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["ready_for_supervised_next_strategy"] is True
    assert result.payload["ready_for_supervised_candidate_generation"] is False
    assert result.payload["ready_for_full_autonomous_loop_controller"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["model_calls"] == 0
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True
    assert result.payload["next_recommended_action"] == (
        "plan_next_target_from_cleanup_authorization"
    )

    packet_dir = Path(str(result.payload["packet_dir"]))
    manifest = read_payload(
        packet_dir / "supervised_cycle_authorization_subject_manifest.json"
    )
    assert manifest["source_loop_cleanup_packet_id"] == second_cleanup.payload["packet_id"]
    assert manifest["source_loop_review_packet_id"] == chain["residual_loop_review"][
        "packet_id"
    ]
    assert manifest["current_best_candidate_packet_id"] == chain["residual_candidate"][
        "packet_id"
    ]

    packet = read_payload(packet_dir / "supervised_cycle_authorization_packet.json")
    assert packet["source_loop_cleanup_packet_id"] == second_cleanup.payload["packet_id"]
    assert packet["cleanup_checkpoint_consumed"] is True
    assert packet["source_loop_review_packet_id"] == chain["residual_loop_review"][
        "packet_id"
    ]
    assert packet["source_synthesis_packet_id"] == chain["residual_synthesis"]["packet_id"]
    assert packet["current_best_candidate_packet_id"] == chain["residual_candidate"][
        "packet_id"
    ]
    assert packet["next_strategy_authorized"] is True
    assert packet["next_generation_authorized"] is False
    assert packet["next_recommended_action"] == "plan_next_target_from_cleanup_authorization"
    cleanup_consumed_gate = next(
        gate
        for gate in packet["gate_report"]["gate_results"]
        if gate["gate_name"] == "loop_cleanup_packet_consumed"
    )
    assert cleanup_consumed_gate["passed"] is True
    assert cleanup_consumed_gate["blocking_defects"] == []

    duplicate = run_supervised_cycle_authorization(
        config,
        loop_cleanup_packet=Path(str(second_cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert duplicate.exit_code == 1
    assert duplicate.payload["accepted"] is False
    assert "already has an accepted strategy authorization" in duplicate.payload["message"]

    cleanup_gate = read_payload(
        Path(str(second_cleanup.payload["packet_dir"]))
        / "loop_integrity_cleanup_gate_report.json"
    )
    false_gate_names = [
        gate["gate_name"]
        for gate in cleanup_gate["gate_results"]
        if gate["passed"] is False
    ]
    assert cleanup_gate["failed_gates"] == false_gate_names

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
    assert len(after_calls) == len(before_calls)


def test_cleanup_aware_authorization_accepts_target_aware_cleanup_cycle(tmp_path):
    chain = build_completed_tactile_cleanup_chain(tmp_path)
    config = chain["config"]
    first_cleanup = chain["cleanup"]
    second_cleanup = run_loop_integrity_cleanup(
        config,
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )
    assert second_cleanup.exit_code == 0

    stale = run_supervised_cycle_authorization(
        config,
        loop_cleanup_packet=Path(str(first_cleanup["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )
    assert stale.exit_code == 1
    assert stale.payload["accepted"] is False
    assert "stale" in stale.payload["message"]
    assert str(second_cleanup.payload["packet_dir"]) in stale.payload["message"]

    generation_decision = run_supervised_cycle_authorization(
        config,
        loop_cleanup_packet=Path(str(second_cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="pause_generation",
    )
    assert generation_decision.exit_code == 1
    assert generation_decision.payload["accepted"] is False
    assert "only supports --decision authorize_next_strategy_only" in (
        generation_decision.payload["message"]
    )

    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_supervised_cycle_authorization(
        config,
        loop_cleanup_packet=Path(str(second_cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["source_kind"] == "loop_cleanup"
    assert result.payload["source_loop_cleanup_packet_id"] == second_cleanup.payload[
        "packet_id"
    ]
    assert result.payload["source_loop_review_packet_id"] == chain[
        "residual_loop_review"
    ]["packet_id"]
    assert result.payload["source_synthesis_packet_id"] == chain["residual_synthesis"][
        "packet_id"
    ]
    assert result.payload["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert result.payload["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert result.payload["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["target_adapter_id"] == "tactile_inevitability"
    assert result.payload["target_scope"] == TACTILE_INEVITABILITY_TARGET_ID
    assert result.payload["next_strategy_authorized"] is True
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["ready_for_supervised_next_strategy"] is True
    assert result.payload["ready_for_supervised_candidate_generation"] is False
    assert result.payload["ready_for_full_autonomous_loop_controller"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["model_calls"] == 0
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True
    assert result.payload["next_recommended_action"] == (
        "plan_next_target_from_cleanup_authorization"
    )

    packet_dir = Path(str(result.payload["packet_dir"]))
    manifest = read_payload(
        packet_dir / "supervised_cycle_authorization_subject_manifest.json"
    )
    assert manifest["source_loop_cleanup_packet_id"] == second_cleanup.payload[
        "packet_id"
    ]
    assert manifest["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert manifest["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert manifest["target_adapter_id"] == "tactile_inevitability"

    cleanup_report = read_payload(packet_dir / "cleanup_resolution_report.json")
    assert cleanup_report["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert cleanup_report["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert cleanup_report["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert cleanup_report["selected_residual_target_id"] == (
        TACTILE_INEVITABILITY_TARGET_ID
    )
    assert cleanup_report["target_adapter_id"] == "tactile_inevitability"
    assert cleanup_report["stale_prior_cycle_summary"][
        "prior_cycle_entries_recorded"
    ] is True

    constraints = read_payload(packet_dir / "next_cycle_scope_constraints.json")
    assert constraints["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert constraints["target_adapter_id"] == "tactile_inevitability"
    assert constraints["next_generation_authorized"] is False

    packet = read_payload(packet_dir / "supervised_cycle_authorization_packet.json")
    assert packet["source_loop_cleanup_packet_id"] == second_cleanup.payload["packet_id"]
    assert packet["current_best_candidate_packet_id"] == chain["residual_candidate"][
        "packet_id"
    ]
    assert packet["selected_residual_target_id"] == TACTILE_INEVITABILITY_TARGET_ID
    assert packet["target_adapter_id"] == "tactile_inevitability"
    assert packet["next_strategy_authorized"] is True
    assert packet["next_generation_authorized"] is False
    assert packet["candidate_generated"] is False
    assert packet["model_calls"] == 0

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        ("next_generation_authorized", "authorizes generation directly"),
        ("finalization_eligible", "finality or phase-shift"),
        ("phase_shift_claim", "finality or phase-shift"),
        ("fixture_proof", "proof packet is fixture-only"),
        ("fixture_reader_state", "reader-state packet is fixture-only"),
        ("generic_proof", "target-aware proof"),
        ("role_failed_proof", "target role consistency"),
    ],
)
def test_cleanup_aware_authorization_refuses_invalid_target_aware_cleanup(
    tmp_path,
    mutation,
    expected_message,
):
    chain = build_completed_tactile_cleanup_chain(tmp_path)
    cleanup_dir = Path(str(chain["cleanup"]["packet_dir"]))

    if mutation == "next_generation_authorized":
        rewrite_payload(
            cleanup_dir / "loop_integrity_cleanup_packet.json",
            lambda payload: payload.__setitem__("next_generation_authorized", True),
        )
    elif mutation == "finalization_eligible":
        rewrite_payload(
            cleanup_dir / "loop_integrity_cleanup_packet.json",
            lambda payload: payload.__setitem__("finalization_eligible", True),
        )
    elif mutation == "phase_shift_claim":
        rewrite_payload(
            cleanup_dir / "loop_integrity_cleanup_packet.json",
            lambda payload: payload.__setitem__("no_phase_shift_claim", False),
        )
    elif mutation == "fixture_proof":
        mark_packet_fixture_only(Path(str(chain["residual_proof"]["packet_dir"])))
    elif mutation == "fixture_reader_state":
        mark_packet_fixture_only(
            Path(str(chain["residual_reader_state"]["packet_dir"]))
        )
    elif mutation == "generic_proof":
        _rewrite_tactile_proof_as_generic_non_authoritative(chain["residual_proof"])
    elif mutation == "role_failed_proof":
        _rewrite_tactile_proof_as_role_consistency_failed(chain["residual_proof"])

    result = run_supervised_cycle_authorization(
        chain["config"],
        loop_cleanup_packet=cleanup_dir,
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected_message in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["next_strategy_authorized"] is False
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["candidate_generated"] is False
    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_plan_next_target_consumes_cleanup_aware_authorization(tmp_path):
    chain = build_completed_residual_loop_review_chain(tmp_path)
    config = chain["config"]
    cleanup = run_loop_integrity_cleanup(
        config,
        loop_review_packet=Path(str(chain["residual_loop_review"]["packet_dir"])),
        operator_reviewed=True,
    )
    assert cleanup.exit_code == 0
    authorization = run_supervised_cycle_authorization(
        config,
        loop_cleanup_packet=Path(str(cleanup.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )
    assert authorization.exit_code == 0

    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_next_target_strategy(
        config,
        authorization_packet=Path(str(authorization.payload["packet_dir"])),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["source_loop_cleanup_packet_id"] == cleanup.payload["packet_id"]
    assert result.payload["source_authorization_packet_id"] == authorization.payload[
        "packet_id"
    ]
    assert result.payload["source_loop_review_packet_id"] == chain[
        "residual_loop_review"
    ]["packet_id"]
    assert result.payload["source_synthesis_packet_id"] == chain["residual_synthesis"][
        "packet_id"
    ]
    assert result.payload["current_best_candidate_packet_id"] == chain[
        "residual_candidate"
    ]["packet_id"]
    assert result.payload["current_best_candidate_packet_id"] != chain["object_event"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["residual_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["residual_reader_state"][
        "packet_id"
    ]
    assert result.payload["next_strategy_authorized"] is True
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["model_calls"] == 0
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True
    assert result.payload["primary_next_target"] == (
        "next_residual_target_requires_operator_choice"
    )
    assert result.payload["next_recommended_action"] == (
        "review_narrow_residual_target_options_before_generation"
    )
    attempted = set(result.payload["exhausted_or_attempted_target_ids"])
    assert {
        "reader_state_informed_macro_2",
        "first_read_object_event_pressure_gap",
        "object_motion_causality_specificity",
    }.issubset(attempted)
    option_map = result.payload["residual_target_option_map"]
    assert option_map["primary_next_target"] == (
        "next_residual_target_requires_operator_choice"
    )
    object_motion_option = [
        option
        for option in option_map["specific_residual_options"]
        if option["option_id"] == "object_motion_causality_specificity"
    ][0]
    assert object_motion_option["status"] == (
        "attempted_handle_requires_narrower_subtarget"
    )
    assert object_motion_option["candidate_generation_authorized"] is False

    packet_dir = Path(str(result.payload["packet_dir"]))
    packet = read_payload(packet_dir / "next_target_strategy_packet.json")
    assert packet["source_loop_cleanup_packet_id"] == cleanup.payload["packet_id"]
    assert packet["current_best_candidate_packet_id"] == chain["residual_candidate"][
        "packet_id"
    ]
    assert packet["current_best_candidate_packet_id"] != chain["object_event"]["packet_id"]
    assert "object_motion_causality_specificity" in packet[
        "exhausted_or_attempted_target_ids"
    ]
    assert packet["candidate_generated"] is False
    assert packet["next_generation_authorized"] is False

    stale_selection = run_residual_target_selection(
        config,
        strategy_packet=Path(str(chain["next_target_strategy"]["packet_dir"])),
        target=OBJECT_MOTION_CAUSALITY_TARGET_ID,
        operator_reviewed=True,
    )
    assert stale_selection.exit_code == 1
    assert stale_selection.payload["accepted"] is False
    assert "marked stale" in stale_selection.payload["message"]

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_evidence_loop_review_refuses_missing_best_current_candidate(tmp_path):
    chain = build_object_event_candidate_with_reader_state(tmp_path)
    synthesis = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])
    assert synthesis.exit_code == 0
    invalid_packet = tmp_path / "invalid_loop_review_missing_best"
    shutil.copytree(Path(str(synthesis.payload["packet_dir"])), invalid_packet)

    def _remove_packet_best(payload):
        payload.pop("best_current_candidate", None)

    def _remove_selected_best(payload):
        payload.pop("selected_best_candidate", None)

    rewrite_payload(
        invalid_packet / "autonomous_evidence_synthesis_packet.json",
        _remove_packet_best,
    )
    rewrite_payload(
        invalid_packet / "best_current_candidate_selection.json",
        _remove_selected_best,
    )

    result = run_evidence_loop_review(chain["config"], synthesis_packet=invalid_packet)

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "best_current_candidate" in result.payload["message"]
    assert result.payload["artifact_ids"] == {}
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["candidate_generated"] is False


def test_supervised_cycle_authorization_refuses_without_operator_review(tmp_path):
    chain = build_object_event_candidate_with_reader_state(tmp_path)
    synthesis = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])
    loop_review = run_evidence_loop_review(
        chain["config"],
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )

    with connect(chain["config"].db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_supervised_cycle_authorization(
        chain["config"],
        loop_review_packet=Path(str(loop_review.payload["packet_dir"])),
        operator_reviewed=False,
        decision=None,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["refused"] is True
    assert "--operator-reviewed" in result.payload["message"]
    assert result.payload["artifact_ids"] == {}
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["candidate_generated"] is False
    with connect(chain["config"].db_path) as connection:
        after_calls = list_model_calls(connection)
    assert len(after_calls) == len(before_calls)


def test_supervised_cycle_authorization_refuses_missing_loop_review_packet(tmp_path):
    config = config_for(tmp_path)

    result = run_supervised_cycle_authorization(
        config,
        loop_review_packet=tmp_path / "missing_loop_review_packet",
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "directory not found" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_supervised_cycle_authorization_accepts_reviewed_strategy_only_decision(
    tmp_path,
):
    chain = build_object_event_candidate_with_reader_state(tmp_path)
    config = chain["config"]
    synthesis = run_autonomous_evidence_synthesis(config, run_id=chain["run_id"])
    loop_review = run_evidence_loop_review(
        config,
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )
    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    result = run_supervised_cycle_authorization(
        config,
        loop_review_packet=Path(str(loop_review.payload["packet_dir"])),
        operator_reviewed=True,
        decision="authorize_next_strategy_only",
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert set(result.payload["artifact_ids"]) == set(
        SUPERVISED_CYCLE_AUTHORIZATION_ARTIFACT_TYPES
    )
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["counts"]["produced_artifacts"] == len(
        SUPERVISED_CYCLE_AUTHORIZATION_ARTIFACT_TYPES
    )
    assert result.payload["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert result.payload["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert result.payload["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert result.payload["operator_reviewed"] is True
    assert result.payload["decision"] == "authorize_next_strategy_only"
    assert result.payload["next_strategy_authorized"] is True
    assert result.payload["next_generation_authorized"] is False
    assert result.payload["ready_for_supervised_next_strategy"] is True
    assert result.payload["ready_for_supervised_candidate_generation"] is False
    assert result.payload["ready_for_full_autonomous_loop_controller"] is False
    assert result.payload["candidate_generated"] is False
    assert result.payload["model_calls"] == 0
    assert result.payload["finalization_eligible"] is False
    assert result.payload["no_phase_shift_claim"] is True
    assert result.payload["next_recommended_action"] == (
        "prepare_next_residual_target_strategy_under_supervision"
    )
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(
        packet_dir / "supervised_cycle_authorization_subject_manifest.json"
    )
    assert manifest["loop_review_packet_id"] == loop_review.payload["packet_id"]
    assert manifest["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert manifest["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert manifest["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert manifest["source_synthesis_packet_id"] == synthesis.payload["packet_id"]
    assert manifest["completed_cycles"] == 2
    assert manifest["finalization_eligible"] is False
    assert manifest["no_phase_shift_claim"] is True

    operator = read_payload(packet_dir / "operator_review_record.json")
    assert operator["operator_reviewed"] is True
    assert operator["decision"] == "authorize_next_strategy_only"
    assert operator["not_final_operator_approval"] is True
    assert operator["not_human_validation"] is True
    assert operator["does_not_authorize_finalization"] is True

    cleanup = read_payload(packet_dir / "cleanup_resolution_report.json")
    assert cleanup["fresh_loop_integrity_cleanup_passed"] is True
    assert cleanup["legacy_packet_count_quirks_nonblocking_for_supervised_cycle"] is True
    assert cleanup["full_autonomous_loop_cleanup_complete"] is False
    assert cleanup["supervised_strategy_step_cleanup_complete"] is True

    readiness = read_payload(
        packet_dir / "supervised_next_cycle_readiness_report.json"
    )
    assert readiness["ready_for_supervised_next_strategy"] is True
    assert readiness["ready_for_supervised_candidate_generation"] is False
    assert readiness["ready_for_full_autonomous_loop_controller"] is False
    assert readiness["next_strategy_authorized"] is True
    assert readiness["next_generation_authorized"] is False

    constraints = read_payload(packet_dir / "next_cycle_scope_constraints.json")
    assert constraints["next_strategy_authorized"] is True
    assert constraints["next_generation_authorized"] is False
    assert "no candidate generation" in constraints["scope"]
    assert constraints["candidate_generation_requires_later_authorization_packet"] is True
    assert constraints["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]

    gate = read_payload(packet_dir / "authorization_gate_report.json")
    gate_results = {gate_result["gate_name"]: gate_result for gate_result in gate["gate_results"]}
    for gate_name in (
        "loop_review_packet_consumed",
        "operator_review_recorded",
        "current_best_candidate_identified",
        "proof_packet_linked",
        "reader_state_packet_linked",
        "completed_cycles_present",
        "cleanup_resolution_recorded",
        "next_strategy_authorized",
        "no_candidate_generated",
        "no_openai_calls",
        "no_final_claim",
        "no_phase_shift_claim",
    ):
        assert gate_results[gate_name]["passed"] is True
    for gate_name in (
        "next_candidate_generation_authorized",
        "full_autonomous_loop_controller_ready",
        "finalization_eligible",
        "human_validation_present",
        "strongest_rival_defeated",
    ):
        assert gate_results[gate_name]["passed"] is False
    assert gate["ready_for_supervised_next_strategy"] is True
    assert gate["ready_for_supervised_candidate_generation"] is False
    assert gate["ready_for_full_autonomous_loop_controller"] is False
    assert gate["next_generation_authorized"] is False
    assert gate["candidate_generated"] is False
    assert gate["model_calls"] == 0
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True

    packet = read_payload(packet_dir / "supervised_cycle_authorization_packet.json")
    assert packet["current_best_candidate_packet_id"] == chain["object_event"][
        "packet_id"
    ]
    assert packet["proof_packet_id"] == chain["object_event_proof"]["packet_id"]
    assert packet["reader_state_packet_id"] == chain["object_event_reader_state"][
        "packet_id"
    ]
    assert packet["completed_cycles"] == 2
    assert packet["next_strategy_authorized"] is True
    assert packet["next_generation_authorized"] is False
    assert packet["ready_for_full_autonomous_loop_controller"] is False
    assert packet["candidate_generated"] is False
    assert packet["model_calls"] == 0
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_autonomous_evidence_synthesis_keeps_macro2_without_object_event_proof(tmp_path):
    chain = build_object_event_candidate_with_optional_proof(
        tmp_path,
        proof_mode=None,
        object_event_client="openai",
    )

    result = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])

    assert result.exit_code == 0
    packet_dir = Path(str(result.payload["packet_dir"]))
    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["macro2"]["packet_id"]
    object_event_option = [
        option
        for option in best["candidate_options"]
        if option["packet_id"] == chain["object_event"]["packet_id"]
    ][0]
    assert object_event_option["candidate_proof_linked"] is False
    assert object_event_option["supersession_eligible"] is False
    assert "no_executed_ablation_proof_linked" in object_event_option[
        "supersession_blockers"
    ]
    assert best["best_current_candidate_updated_from_object_event_proof"] is False
    assert any(
        "did not supersede" in item
        for item in best["object_event_candidate_supersession_rationale"]
    )


def test_autonomous_evidence_synthesis_rejects_failed_or_fake_object_event_supersession(
    tmp_path,
):
    failed_chain = build_object_event_candidate_with_optional_proof(
        tmp_path / "failed",
        proof_mode="failed",
        object_event_client="openai",
    )
    failed_result = run_autonomous_evidence_synthesis(
        failed_chain["config"],
        run_id=failed_chain["run_id"],
    )
    failed_packet_dir = Path(str(failed_result.payload["packet_dir"]))
    failed_best = read_payload(failed_packet_dir / "best_current_candidate_selection.json")
    failed_selected = failed_best["selected_best_candidate"]
    assert failed_selected["packet_id"] == failed_chain["macro2"]["packet_id"]
    failed_option = [
        option
        for option in failed_best["candidate_options"]
        if option["packet_id"] == failed_chain["object_event"]["packet_id"]
    ][0]
    assert failed_option["candidate_proof_linked"] is True
    assert failed_option["supersession_eligible"] is False
    assert "proof_causal_status_not_useful_or_stronger" in failed_option[
        "supersession_blockers"
    ]

    fake_chain = build_object_event_candidate_with_optional_proof(
        tmp_path / "fake",
        proof_mode="useful",
        object_event_client="fake",
    )
    fake_result = run_autonomous_evidence_synthesis(
        fake_chain["config"],
        run_id=fake_chain["run_id"],
    )
    fake_packet_dir = Path(str(fake_result.payload["packet_dir"]))
    fake_best = read_payload(fake_packet_dir / "best_current_candidate_selection.json")
    fake_selected = fake_best["selected_best_candidate"]
    assert fake_selected["packet_id"] == fake_chain["macro2"]["packet_id"]
    fake_option = [
        option
        for option in fake_best["candidate_options"]
        if option["packet_id"] == fake_chain["object_event"]["packet_id"]
    ][0]
    assert fake_option["candidate_proof_linked"] is True
    assert fake_option["supersession_eligible"] is False
    assert "candidate_not_live_model_backed" in fake_option["supersession_blockers"]
    assert "proof_not_live_model_backed" in fake_option["supersession_blockers"]
    assert fake_best["best_current_candidate_updated_from_object_event_proof"] is False


def test_autonomous_evidence_synthesis_does_not_select_new_macro2_without_proof(tmp_path):
    chain = build_live_macro2_candidate_with_optional_proof(tmp_path, proof_mode=None)

    result = run_autonomous_evidence_synthesis(chain["config"], run_id=chain["run_id"])

    assert result.exit_code == 0
    packet_dir = Path(str(result.payload["packet_dir"]))
    best = read_payload(packet_dir / "best_current_candidate_selection.json")
    selected = best["selected_best_candidate"]
    assert selected["packet_id"] == chain["macro_payload"]["packet_id"]
    assert selected["packet_kind"] == "bounded_macro_recomposition"
    macro2_option = [
        option
        for option in best["candidate_options"]
        if option["packet_id"] == chain["macro2"]["packet_id"]
        and option["packet_kind"] == "bounded_macro_recomposition"
    ][0]
    assert macro2_option["candidate_proof_linked"] is False
    assert macro2_option["supersession_eligible"] is False
    assert "no_executed_ablation_proof_linked" in macro2_option["supersession_blockers"]
    assert best["best_current_candidate_updated_from_macro2_proof"] is False


def test_autonomous_evidence_synthesis_rejects_failed_or_fake_macro2_supersession(
    tmp_path,
):
    failed_chain = build_live_macro2_candidate_with_optional_proof(
        tmp_path / "failed",
        proof_mode="failed",
    )
    failed_result = run_autonomous_evidence_synthesis(
        failed_chain["config"],
        run_id=failed_chain["run_id"],
    )
    failed_packet_dir = Path(str(failed_result.payload["packet_dir"]))
    failed_best = read_payload(failed_packet_dir / "best_current_candidate_selection.json")
    failed_selected = failed_best["selected_best_candidate"]
    assert failed_selected["packet_id"] == failed_chain["macro_payload"]["packet_id"]
    assert failed_selected["packet_kind"] == "bounded_macro_recomposition"
    failed_macro2_option = [
        option
        for option in failed_best["candidate_options"]
        if option["packet_id"] == failed_chain["macro2"]["packet_id"]
        and option["packet_kind"] == "bounded_macro_recomposition"
    ][0]
    assert failed_macro2_option["supersession_eligible"] is False
    assert "proof_causal_status_not_useful_or_stronger" in failed_macro2_option[
        "supersession_blockers"
    ]

    fake_chain = build_reader_state_macro_synthesis_chain(tmp_path / "fake")
    fake_macro2 = run_bounded_macro_recomposition(
        fake_chain["config"],
        client_name="fake",
        synthesis_packet=Path(str(fake_chain["synthesis"]["packet_dir"])),
    )
    assert fake_macro2.exit_code == 0
    fake_proof = run_executed_ablation(
        fake_chain["config"],
        client_name="fake",
        revision_packet=fake_macro2.payload["packet_dir"],
    )
    assert fake_proof.exit_code == 0
    _rewrite_macro2_proof(fake_proof.payload, useful=True)

    fake_result = run_autonomous_evidence_synthesis(
        fake_chain["config"],
        run_id=fake_chain["run_id"],
    )
    fake_packet_dir = Path(str(fake_result.payload["packet_dir"]))
    fake_best = read_payload(fake_packet_dir / "best_current_candidate_selection.json")
    fake_selected = fake_best["selected_best_candidate"]
    assert fake_selected["packet_id"] == fake_chain["macro_payload"]["packet_id"]
    assert fake_selected["packet_kind"] == "bounded_macro_recomposition"
    fake_macro2_option = [
        option
        for option in fake_best["candidate_options"]
        if option["packet_id"] == fake_macro2.payload["packet_id"]
        and option["packet_kind"] == "bounded_macro_recomposition"
    ][0]
    assert fake_macro2_option["candidate_proof_linked"] is True
    assert fake_macro2_option["supersession_eligible"] is False
    assert "candidate_not_live_model_backed" in fake_macro2_option["supersession_blockers"]
    assert "proof_not_live_model_backed" in fake_macro2_option["supersession_blockers"]
    assert fake_best["best_current_candidate_updated_from_macro2_proof"] is False


def test_autonomous_evidence_synthesis_refuses_missing_critical_packets(tmp_path):
    config = config_for(tmp_path)
    pilot = run_pilot_artifact_set(
        config,
        client_name="fake",
        source_dir=write_sources(tmp_path),
    )
    assert pilot.exit_code == 0

    result = run_autonomous_evidence_synthesis(config, run_id=pilot.payload["run_id"])

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "missing critical source packet kinds" in result.payload["message"]
    assert "internal_reader_lab" in result.payload["missing_critical_source_kinds"]
    assert result.payload["finalization_eligible"] is False


def test_bounded_macro_recomposition_fake_creates_fail_closed_packet(tmp_path):
    config, _failed_ablation, pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
        before_calls = list_model_calls(connection)
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0

    result = run_bounded_macro_recomposition(
        config,
        client_name="fake",
        synthesis_packet=Path(str(synthesis.payload["packet_dir"])),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    assert set(result.payload["artifact_ids"]) == set(BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES)
    assert result.payload["base_candidate_packet_id"] != pivot_revision["packet_id"]
    assert result.payload["target_movement"] == "middle_and_return_movement"
    assert result.payload["bounded_macro_recomposition"] is True
    assert result.payload["full_rewrite"] is False
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "macro_recomposition_subject_manifest.json")
    assert manifest["base_from_synthesis_selected_best_candidate"] is True
    assert manifest["failed_pivot_packet_used_as_base"] is False
    assert manifest["packet_0030_used_as_base"] is False

    protected = read_payload(packet_dir / "protected_effects_and_forbidden_changes.json")
    assert "table/dust/spoon/saucer local field" in protected["protected_effects"]
    assert "rewriting the whole artifact" in protected["forbidden_changes"]
    assert "naming pressure more often instead of embodying pressure" in protected[
        "forbidden_changes"
    ]

    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["base_candidate_packet_id"] == result.payload["base_candidate_packet_id"]
    assert candidate["target_movement"] == "middle_and_return_movement"
    assert candidate["bounded_macro_recomposition"] is True
    assert candidate["full_rewrite"] is False
    assert candidate["finalization_eligible"] is False
    assert candidate["no_phase_shift_claim"] is True

    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    assert diff["opening_scene_preserved"] is True
    assert diff["bounded_macro_recomposition"] is True
    assert diff["full_rewrite"] is False
    assert diff["unchanged_prefix_paragraph_count"] >= 0
    assert diff["changed_spans"]
    assert diff["target_coverage_report"]["macro_target_coverage_passed"] is True
    assert diff["target_coverage_report"]["macro_materiality_passed"] is True

    rival = read_payload(packet_dir / "macro_rival_pressure_check.json")
    assert rival["strongest_rival_pressure_preserved"] is True
    assert rival["strongest_rival_still_blocks"] is True
    assert rival["strongest_rival_comparison_passed"] is False

    gate = read_payload(packet_dir / "macro_recomposition_gate_report.json")
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert "macro_recomposition_executed_ablation_completed" in gate["failed_gates"]
    assert "no_unresolved_internal_blockers" in gate["failed_gates"]
    assert "internal_operator_approval" in gate["failed_gates"]

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(after_calls) == len(before_calls)
    assert final_report.refused is True


def test_bounded_macro_recomposition_refuses_invalid_synthesis_packet_missing_brief(
    tmp_path,
):
    config, _failed_ablation, _pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    invalid_packet = tmp_path / "invalid_synthesis_packet"
    shutil.copytree(Path(str(synthesis.payload["packet_dir"])), invalid_packet)
    (invalid_packet / "macro_recomposition_brief.json").unlink()

    result = run_bounded_macro_recomposition(
        config,
        client_name="fake",
        synthesis_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "macro_recomposition_brief.json" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_bounded_macro_recomposition_refuses_invalid_synthesis_packet_missing_best(
    tmp_path,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    invalid_packet = tmp_path / "invalid_synthesis_packet_missing_best"
    shutil.copytree(Path(str(chain["synthesis"]["packet_dir"])), invalid_packet)
    (invalid_packet / "best_current_candidate_selection.json").unlink()

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="fake",
        synthesis_packet=invalid_packet,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "best_current_candidate_selection.json" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_bounded_macro_recomposition_accepts_reader_state_macro_2_brief(tmp_path):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="fake",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["target_movement"] == READER_STATE_MACRO_2_TARGET_SCOPE
    assert result.payload["target_scope"] == READER_STATE_MACRO_2_TARGET_SCOPE
    assert result.payload["base_candidate_packet_id"] == chain["macro_payload"]["packet_id"]
    assert result.payload["base_candidate_packet_id"] != chain["pivot_revision"]["packet_id"]
    packet_dir = Path(str(result.payload["packet_dir"]))

    manifest = read_payload(packet_dir / "macro_recomposition_subject_manifest.json")
    assert manifest["base_candidate_packet_kind"] == "bounded_macro_recomposition"
    assert manifest["base_candidate_packet_id"] == chain["macro_payload"]["packet_id"]
    assert manifest["reader_state_informed_brief"] is True
    assert manifest["reader_state_evidence_packet_id"] == chain["reader_state"]["packet_id"]

    work_order = read_payload(packet_dir / "macro_recomposition_work_order.json")
    assert work_order["target_scope"] == READER_STATE_MACRO_2_TARGET_SCOPE
    assert work_order["selected_reader_state_evidence_packet_id"] == chain["reader_state"][
        "packet_id"
    ]
    assert work_order["base_candidate_packet_id"] == chain["macro_payload"]["packet_id"]
    assert work_order["selected_candidate_text"]
    target_paragraphs = work_order["target_paragraphs"]
    assert target_paragraphs
    assert {paragraph["target_paragraph_ref"] for paragraph in target_paragraphs} == {
        "target_p001",
        "target_p002",
        "target_p003",
        "target_p004",
    }
    for paragraph in target_paragraphs:
        assert paragraph["before_text"]
        assert paragraph["before_text_sha256"]
        assert paragraph["word_count"] > 0
        assert paragraph["active_target_ids"]
        assert paragraph["material_change_required"] is True
        materiality_contract = paragraph["paragraph_materiality_contract"]
        assert materiality_contract["material_rewrite_required"] is True
        assert materiality_contract["near_copy_rejected"] is True
        assert materiality_contract["lexical_substitution_insufficient"] is True
        assert (
            materiality_contract["span_mapping_necessary_but_not_sufficient"]
            is True
        )
        assert materiality_contract["preserve_function_not_sentence_structure"] is True
        assert materiality_contract["must_change_global_paragraph_relation"] is True
        assert materiality_contract["controller_thresholds"]["required_ratio"] == 0.18
        assert paragraph["transformation_instruction"]
        assert paragraph["protected_effects"]
        assert paragraph["forbidden_failures"]
    p003_contract = next(
        paragraph["paragraph_materiality_contract"]
        for paragraph in target_paragraphs
        if paragraph["target_paragraph_ref"] == "target_p003"
    )
    assert p003_contract["lexical_substitution_insufficient"] is True
    assert p003_contract["preserve_function_not_sentence_structure"] is True
    target_spans = work_order["target_spans"]
    assert target_spans
    assert work_order["active_target_units"] == target_spans
    assignment_report = work_order["target_assignment_consistency_report"]
    assert work_order["target_assignment_consistency_passed"] is True
    assert assignment_report["target_assignment_consistency_passed"] is True
    assert assignment_report["inconsistent_target_paragraph_refs"] == []
    assert assignment_report["material_targets_without_operational_unit"] == []
    assert assignment_report["paragraphs_with_material_targets_and_no_material_spans"] == []
    assert assignment_report["deferred_or_removed_targets_by_paragraph"]
    p001_spans = [
        span
        for span in target_spans
        if span["parent_target_paragraph_ref"] == "target_p001"
    ]
    assert len(p001_spans) >= 2
    assert {
        span["target_span_ref"] for span in p001_spans if span["material_change_required"]
    }
    assert all(span["before_text"] for span in p001_spans)
    assert all(span["before_text_sha256"] for span in p001_spans)
    assert all(span["parent_target_paragraph_ref"] == "target_p001" for span in p001_spans)
    assert any(
        "thesis_visible_proof_language_reduction" in span["active_target_ids"]
        and span["material_change_required"]
        for span in p001_spans
    )
    assert {
        span["allowed_operation"]
        for span in p001_spans
        if span["material_change_required"]
    } <= {"remove_thesis_frame", "relocate_to_object_sequence", "compress"}
    spans_by_parent = {}
    for span in target_spans:
        spans_by_parent.setdefault(span["parent_target_paragraph_ref"], []).append(span)
    final_ref = next(
        paragraph["target_paragraph_ref"]
        for paragraph in target_paragraphs
        if "final_return_echo_reread_strength" in paragraph["active_target_ids"]
    )
    final_paragraph = next(
        paragraph
        for paragraph in target_paragraphs
        if paragraph["target_paragraph_ref"] == final_ref
    )
    assert "opening_return_transformation_strengthening" in final_paragraph[
        "active_target_ids"
    ]
    assert "thesis_visible_proof_language_reduction" not in final_paragraph[
        "active_target_ids"
    ]
    assert "thesis_visible_proof_language_reduction" in final_paragraph[
        "deferred_or_removed_active_target_ids"
    ]
    final_material_spans = [
        span
        for span in spans_by_parent[final_ref]
        if span["material_change_required"]
    ]
    assert any(
        "final_return_echo_reread_strength" in span["active_target_ids"]
        and span["allowed_operation"] == "strengthen_return_echo"
        for span in final_material_spans
    )
    assert any(
        "opening_return_transformation_strengthening" in span["active_target_ids"]
        and span["allowed_operation"] == "make_opening_return_transformational"
        for span in final_material_spans
    )
    proof_ref = next(
        paragraph["target_paragraph_ref"]
        for paragraph in target_paragraphs
        if "proof_no_outside_answer_refinement" in paragraph["active_target_ids"]
    )
    assert any(
        span["material_change_required"]
        and span["allowed_operation"] == "embody_no_outside_answer_pressure"
        and "proof_no_outside_answer_refinement" in span["active_target_ids"]
        for span in spans_by_parent[proof_ref]
    )
    assert {
        target["target_id"] for target in work_order["active_transformation_targets"]
    } == set(READER_STATE_MACRO_2_ACTIVE_TARGET_IDS)

    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["base_candidate_packet_id"] == chain["macro_payload"]["packet_id"]
    assert candidate["target_movement"] == READER_STATE_MACRO_2_TARGET_SCOPE
    assert "The table is still there" in candidate["text"]
    assert candidate["finalization_eligible"] is False
    assert candidate["no_phase_shift_claim"] is True

    diff = read_payload(packet_dir / "macro_recomposition_diff_report.json")
    coverage = diff["target_coverage_report"]
    assert coverage["macro_target_coverage_passed"] is True
    assert coverage["controller_target_coverage_passed"] is True
    assert coverage["macro_materiality_passed"] is True
    assert coverage["paragraph_level_coverage_passed"] is True
    assert coverage["span_level_coverage_passed"] is True
    assert coverage["target_span_count"] == len(target_spans)
    assert coverage["materially_changed_target_span_count"] >= 2
    assert coverage["failed_target_span_refs"] == []
    assert coverage["active_targets_missing"] == []
    assert set(coverage["active_transformation_targets"]) == set(
        READER_STATE_MACRO_2_ACTIVE_TARGET_IDS
    )
    assert diff["target_assignment_consistency_passed"] is True

    gate = read_payload(packet_dir / "macro_recomposition_gate_report.json")
    assert gate["passed"] is False
    assert gate["reader_state_informed_brief_consumed"] is True
    assert gate["macro_target_coverage_passed"] is True
    assert gate["macro_materiality_passed"] is True
    assert gate["target_assignment_consistency_passed"] is True
    assert gate["target_assignment_consistency_report"][
        "target_assignment_consistency_passed"
    ] is True
    assert result.payload["target_assignment_consistency_passed"] is True
    assert "macro_recomposition_executed_ablation_completed" in gate["failed_gates"]
    assert "internal_operator_approval" in gate["failed_gates"]

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_bounded_macro_recomposition_target_assignment_consistency_rejects_all_preserve_material_spans(
    tmp_path,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="fake",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
    )
    assert result.exit_code == 0
    packet_dir = Path(str(result.payload["packet_dir"]))
    work_order = read_payload(packet_dir / "macro_recomposition_work_order.json")
    target_paragraphs = work_order["target_paragraphs"]
    target_spans = [dict(span) for span in work_order["target_spans"]]
    final_ref = next(
        paragraph["target_paragraph_ref"]
        for paragraph in target_paragraphs
        if "final_return_echo_reread_strength" in paragraph["active_target_ids"]
    )

    for span in target_spans:
        if span["parent_target_paragraph_ref"] == final_ref:
            span["material_change_required"] = False
            span["allowed_operation"] = "preserve_only"

    report = _build_target_assignment_consistency_report(
        target_paragraphs=target_paragraphs,
        target_spans=target_spans,
        material_required_target_ids=READER_STATE_MACRO_2_MATERIAL_REQUIRED_TARGET_IDS,
        reader_state_informed=True,
    )

    assert report["target_assignment_consistency_passed"] is False
    assert final_ref in report["paragraphs_with_material_targets_and_no_material_spans"]
    missing = {
        item["target_id"]
        for item in report["material_targets_without_operational_unit"]
        if item["target_paragraph_ref"] == final_ref
    }
    assert {
        "final_return_echo_reread_strength",
        "opening_return_transformation_strengthening",
    } <= missing


def test_bounded_macro_recomposition_openai_guards_refuse_before_model_calls(
    tmp_path,
    monkeypatch,
):
    config, _failed_ablation, _pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
        before_calls = list_model_calls(connection)
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    synthesis_packet = Path(str(synthesis.payload["packet_dir"]))

    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    missing_allow = run_bounded_macro_recomposition(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet,
    )
    assert missing_allow.exit_code == 1
    assert missing_allow.payload["accepted"] is False
    assert "--allow-live-model" in missing_allow.payload["message"]
    assert missing_allow.payload["counts"]["model_calls"] == 0

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    missing_key = run_bounded_macro_recomposition(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet,
        allow_live_model=True,
    )
    assert missing_key.exit_code == 1
    assert missing_key.payload["accepted"] is False
    assert "OPENAI_API_KEY" in missing_key.payload["message"]
    assert missing_key.payload["counts"]["model_calls"] == 0

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)
    assert len(after_calls) == len(before_calls)


def test_bounded_macro_recomposition_schema_is_strict_for_constraint_mapping():
    schema = json_schema_for_worker_schema(BOUNDED_MACRO_RECOMPOSITION_SCHEMA)

    assert_strict_object_schema(schema, path=BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name)
    assert "target_paragraph_replacements" in schema["required"]
    assert "target_span_replacements" in schema["required"]
    item_schema = schema["properties"]["constraint_mapping"]["items"]
    assert item_schema["additionalProperties"] is False
    assert "supporting_replacement_excerpt" in item_schema["required"]
    active_item_schema = schema["properties"]["active_target_mapping"]["items"]
    assert active_item_schema["additionalProperties"] is False
    assert "target_id" in active_item_schema["required"]
    assert "unchanged_justification" in active_item_schema["required"]
    replacement_item_schema = schema["properties"]["target_paragraph_replacements"][
        "items"
    ]
    assert replacement_item_schema["additionalProperties"] is False
    assert "target_paragraph_ref" in replacement_item_schema["required"]
    assert "before_text_sha256" in replacement_item_schema["required"]
    assert "replacement_text" in replacement_item_schema["required"]
    assert "active_target_ids_covered" in replacement_item_schema["required"]
    span_item_schema = schema["properties"]["target_span_replacements"]["items"]
    assert span_item_schema["additionalProperties"] is False
    assert "target_span_ref" in span_item_schema["required"]
    assert "parent_target_paragraph_ref" in span_item_schema["required"]
    assert "before_text_sha256" in span_item_schema["required"]
    assert "replacement_excerpt" in span_item_schema["required"]

    parsed_macro_1_payload = parse_and_validate_structured_output(
        dump_json(live_macro_payload()),
        BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
    )
    assert parsed_macro_1_payload["target_paragraph_replacements"] == []
    assert parsed_macro_1_payload["target_span_replacements"] == []

    missing_targets_payload = live_macro_payload()
    del missing_targets_payload["target_paragraph_replacements"]
    with pytest.raises(ModelValidationError, match="target_paragraph_replacements"):
        parse_and_validate_structured_output(
            dump_json(missing_targets_payload),
            BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
        )
    missing_spans_payload = live_macro_payload()
    del missing_spans_payload["target_span_replacements"]
    with pytest.raises(ModelValidationError, match="target_span_replacements"):
        parse_and_validate_structured_output(
            dump_json(missing_spans_payload),
            BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
        )


def test_bounded_macro_recomposition_openai_response_format_schema_is_strict():
    request = WorkerRequest(
        run_id="run_schema_test",
        worker_role=WorkerRole.BOUNDED_MACRO_RECOMPOSER,
        prompt_contract_id="schema.parity.test",
        schema=BOUNDED_MACRO_RECOMPOSITION_SCHEMA,
        input_text="{}",
    )

    response_format = openai_response_format_for_request(request)

    assert response_format["type"] == "json_schema"
    assert response_format["name"] == BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name
    assert response_format["strict"] is True
    schema = response_format["schema"]
    assert schema["additionalProperties"] is False
    assert "target_paragraph_replacements" in schema["properties"]
    assert "target_paragraph_replacements" in schema["required"]
    assert "target_span_replacements" in schema["properties"]
    assert "target_span_replacements" in schema["required"]
    assert set(schema["required"]) == set(schema["properties"])
    assert_openai_strict_object_schema(
        schema,
        path=BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name,
    )

    replacement_item_schema = schema["properties"]["target_paragraph_replacements"][
        "items"
    ]
    assert replacement_item_schema["additionalProperties"] is False
    assert set(replacement_item_schema["required"]) == set(
        replacement_item_schema["properties"]
    )
    span_item_schema = schema["properties"]["target_span_replacements"]["items"]
    assert span_item_schema["additionalProperties"] is False
    assert set(span_item_schema["required"]) == set(span_item_schema["properties"])
    active_item_schema = schema["properties"]["active_target_mapping"]["items"]
    assert active_item_schema["additionalProperties"] is False
    assert set(active_item_schema["required"]) == set(active_item_schema["properties"])
    constraint_item_schema = schema["properties"]["constraint_mapping"]["items"]
    assert constraint_item_schema["additionalProperties"] is False
    assert set(constraint_item_schema["required"]) == set(
        constraint_item_schema["properties"]
    )


def test_bounded_macro_recomposition_stubbed_openai_success_creates_model_backed_packet(
    tmp_path,
    monkeypatch,
):
    config, _failed_ablation, _pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    synthesis_packet = prepare_multi_paragraph_macro_synthesis(synthesis.payload)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet,
        allow_live_model=True,
        max_model_calls=1,
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 1
    assert len(clients) == 1
    assert len(clients[0].requests) == 1
    request_prompt = json.loads(clients[0].requests[0].input_text)
    assert request_prompt["target_movement"] == "middle_and_return_movement"
    assert request_prompt["protected_semantic_constraints"]
    assert request_prompt["active_transformation_targets"]
    assert "target span mappings are necessary but not enough" in request_prompt[
        "output_rule"
    ]
    assert "reject near-copies" in request_prompt["output_rule"]
    assert "lexical substitution" in request_prompt["output_rule"]
    packet_dir = Path(str(result.payload["packet_dir"]))

    plan_envelope = json.loads(
        (packet_dir / "macro_recomposition_plan.json").read_text(encoding="utf-8")
    )
    section_envelope = json.loads(
        (packet_dir / "macro_patch_or_section_plan.json").read_text(encoding="utf-8")
    )
    model_call_id = result.payload["model_call_ids"][0]
    assert plan_envelope["model_call_id"] == model_call_id
    assert section_envelope["model_call_id"] == model_call_id
    assert plan_envelope["fixture_only"] is False
    assert section_envelope["fixture_only"] is False

    section = section_envelope["payload"]
    assert section["semantic_constraint_claims_model_reported"] is True
    assert section["semantic_constraint_satisfaction_not_proven"] is True
    assert {item["constraint_id"] for item in section["constraint_mapping"]} == set(
        REQUIRED_SEMANTIC_CONSTRAINT_IDS
    )
    assert "the objects keep relation inside the room" in {
        item["supporting_replacement_excerpt"] for item in section["constraint_mapping"]
    }
    assert "proof_from_inside_line" not in section["replacement_section_text"]
    coverage = section["target_coverage_report"]
    assert coverage["macro_target_coverage_passed"] is True
    assert coverage["macro_materiality_passed"] is True
    assert coverage["ready_for_executed_ablation"] is True
    assert coverage["active_targets_missing"] == []
    assert coverage["materially_changed_target_paragraph_count"] >= 2

    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert candidate["source_model_call_id"] == model_call_id
    assert candidate["assembled_by_controller"] is True
    assert candidate["full_rewrite"] is False
    assert candidate["text"].startswith(request_prompt["unchanged_prefix_text"].split("\n\n")[0])
    assert "The room does not need a new witness." in candidate["text"]
    assert "The room does not need a new witness." not in request_prompt[
        "unchanged_prefix_text"
    ]

    gate = read_payload(packet_dir / "macro_recomposition_gate_report.json")
    assert gate["passed"] is False
    assert gate["semantic_constraint_claims_model_reported"] is True
    assert gate["semantic_constraint_satisfaction_not_proven"] is True
    assert gate["macro_target_coverage_passed"] is True
    assert gate["macro_materiality_passed"] is True
    assert gate["ready_for_executed_ablation"] is True
    assert "semantic_constraint_satisfaction_proven" in gate["failed_gates"]

    with connect(config.db_path) as connection:
        model_calls = list_model_calls(connection, run_id=run_id)
        final_report = check_finalization(
            connection,
            run_id=run_id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    macro_calls = [
        call
        for call in model_calls
        if call.schema_name == BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name
    ]
    assert len(macro_calls) == 1
    assert macro_calls[0].status == MODEL_CALL_SUCCESS
    assert macro_calls[0].provider == "openai"
    assert macro_calls[0].model == "stub-live-macro"
    assert macro_calls[0].parsed_output_artifact_id == result.payload["artifact_ids"][
        "macro_patch_or_section_plan"
    ]
    assert final_report.refused is True


def test_bounded_macro_recomposition_reader_state_macro_2_stubbed_openai_target_addressed_success(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["target_scope"] == READER_STATE_MACRO_2_TARGET_SCOPE
    packet_dir = Path(str(result.payload["packet_dir"]))
    prompt = json.loads(clients[0].requests[0].input_text)
    assert prompt["work_order"]["target_paragraphs"]
    assert prompt["work_order"]["target_spans"]
    assert any(
        span["parent_target_paragraph_ref"] == "target_p001"
        and span["material_change_required"]
        for span in prompt["work_order"]["target_spans"]
    )
    final_ref = next(
        paragraph["target_paragraph_ref"]
        for paragraph in prompt["work_order"]["target_paragraphs"]
        if "final_return_echo_reread_strength" in paragraph["active_target_ids"]
    )
    assert "thesis_visible_proof_language_reduction" not in next(
        paragraph["active_target_ids"]
        for paragraph in prompt["work_order"]["target_paragraphs"]
        if paragraph["target_paragraph_ref"] == final_ref
    )
    final_material_spans = [
        span
        for span in prompt["work_order"]["target_spans"]
        if span["parent_target_paragraph_ref"] == final_ref
        and span["material_change_required"]
    ]
    assert {
        "strengthen_return_echo",
        "make_opening_return_transformational",
    } <= {span["allowed_operation"] for span in final_material_spans}
    assert prompt["work_order"]["target_assignment_consistency_passed"] is True
    assert prompt["work_order"]["controller_target_assignment_authoritative"] is True
    assert prompt["work_order"][
        "model_extra_known_target_claims_are_ignored_as_non_evidence"
    ] is True
    assert "controller owns target assignment" in prompt["output_rule"]
    assert all(
        paragraph["active_target_ids_covered_must_be_subset_of"]
        == paragraph["active_target_ids"]
        for paragraph in prompt["work_order"]["target_paragraphs"]
    )
    assert all(
        span["active_target_ids_covered_must_be_subset_of"] == span["active_target_ids"]
        for span in prompt["work_order"]["target_spans"]
    )

    section = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    assert section["controller_assembled_from_target_paragraph_replacements"] is True
    assert section["model_replacement_section_text_authoritative"] is False
    replacements = section["target_paragraph_replacements"]
    assert {item["target_paragraph_ref"] for item in replacements} == {
        "target_p001",
        "target_p002",
        "target_p003",
        "target_p004",
    }
    assert all(item["before_text_sha256"] for item in replacements)
    span_replacements = section["target_span_replacements"]
    assert span_replacements
    assert {
        item["target_span_ref"] for item in span_replacements
    } == {
        span["target_span_ref"]
        for span in prompt["work_order"]["target_spans"]
        if span["material_change_required"]
    }
    assert all(item["replacement_excerpt"] for item in span_replacements)
    preserve_mapping = [
        item
        for item in section["active_target_mapping"]
        if item["target_id"] == "preserve_reader_state_partial_gain"
    ][0]
    assert preserve_mapping["unchanged"] is True
    assert preserve_mapping["unchanged_justification"]
    assert "No answer enters from outside the kitchen." in section[
        "replacement_section_text"
    ]
    assert "The return touches the first table" in section["replacement_section_text"]
    coverage = section["target_coverage_report"]
    assert coverage["macro_target_coverage_passed"] is True
    assert coverage["controller_target_coverage_passed"] is True
    assert coverage["model_active_target_mapping_complete"] is True
    assert coverage["span_level_coverage_passed"] is True
    assert coverage["failed_target_span_refs"] == []
    assert coverage["active_targets_missing"] == []

    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert "No answer enters from outside the kitchen." in candidate["text"]
    assert candidate["source_model_call_id"] == result.payload["model_call_ids"][0]
    assert candidate["finalization_eligible"] is False
    assert candidate["no_phase_shift_claim"] is True

    with connect(chain["config"].db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert final_report.refused is True


def test_bounded_macro_recomposition_reader_state_macro_2_ignores_extra_known_paragraph_claim(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="extra_known_paragraph_target_claim",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 1
    assert len(clients[0].requests) == 1
    packet_dir = Path(str(result.payload["packet_dir"]))
    section = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    coverage = section["target_coverage_report"]
    assert coverage["macro_target_coverage_passed"] is True
    assert coverage["ignored_model_target_claims_by_paragraph_ref"] == {
        "target_p002": ["final_return_echo_reread_strength"]
    }
    assert coverage["unknown_model_target_claims_by_paragraph_ref"] == {}
    assert coverage["model_target_claim_normalization_applied"] is True
    assert coverage["model_target_claims_used_as_evidence"] is False
    assert coverage["ignored_model_target_claims_used_as_evidence"] is False
    assert coverage["controller_target_assignment_authoritative"] is True
    assert section["ignored_model_target_claims_by_paragraph_ref"] == {
        "target_p002": ["final_return_echo_reread_strength"]
    }
    assert section["target_addressed_retry_report"]["retry_attempted"] is False
    gate = read_payload(packet_dir / "macro_recomposition_gate_report.json")
    assert gate["controller_target_assignment_authoritative"] is True
    assert gate["ignored_model_target_claims_by_paragraph_ref"] == {
        "target_p002": ["final_return_echo_reread_strength"]
    }
    packet = read_payload(packet_dir / "macro_recomposition_packet.json")
    assert packet["ignored_model_target_claims_by_paragraph_ref"] == {
        "target_p002": ["final_return_echo_reread_strength"]
    }


def test_bounded_macro_recomposition_reader_state_macro_2_extra_known_paragraph_claim_is_not_coverage(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=1,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="paragraph_extra_known_does_not_cover_missing_assigned",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "thesis_visible_proof_language_reduction" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_unknown_paragraph_target_claim_fails_closed(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="unknown_paragraph_target_claim",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "unknown model active target IDs: invented_macro_target" in result.payload[
        "message"
    ]
    assert result.payload["counts"]["model_calls"] == 1
    report = result.payload["target_addressed_retry_report"]
    assert report["retry_attempted"] is False
    assert "failure was fatal" in report["retry_reason"]
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_ignores_extra_known_span_claim(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="extra_known_span_target_claim",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 1
    packet_dir = Path(str(result.payload["packet_dir"]))
    section = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    coverage = section["target_coverage_report"]
    ignored = coverage["ignored_model_target_claims_by_span_ref"]
    assert ignored
    ignored_span_ref = next(iter(ignored))
    assert ignored[ignored_span_ref] == ["final_return_echo_reread_strength"]
    assert coverage["unknown_model_target_claims_by_span_ref"] == {}
    assert coverage["model_target_claims_used_as_evidence"] is False
    assert coverage["controller_target_assignment_authoritative"] is True
    assert section["ignored_model_target_claims_by_span_ref"] == ignored
    assert section["target_addressed_retry_report"]["retry_attempted"] is False


def test_bounded_macro_recomposition_reader_state_macro_2_extra_known_span_claim_is_not_coverage(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=1,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="span_extra_known_does_not_cover_missing_assigned",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "does not cover material active targets" in result.payload["message"]
    assert "thesis_visible_proof_language_reduction" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_unknown_span_target_claim_fails_closed(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode="unknown_span_target_claim"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "target_span_replacements" in result.payload["message"]
    assert "unknown model active target IDs: invented_macro_target" in result.payload[
        "message"
    ]
    assert result.payload["counts"]["model_calls"] == 1
    report = result.payload["target_addressed_retry_report"]
    assert report["retry_attempted"] is False
    assert "failure was fatal" in report["retry_reason"]
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_controller_assembly_overrides_blob(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="conflicting_replacement_section_text",
        ),
    )

    assert result.exit_code == 0
    packet_dir = Path(str(result.payload["packet_dir"]))
    section = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    candidate = read_payload(packet_dir / "macro_recomposed_candidate_text.json")
    assert "This conflicting model blob" not in section["replacement_section_text"]
    assert "This conflicting model blob" not in candidate["text"]
    assert "No answer enters from outside the kitchen." in candidate["text"]


def test_bounded_macro_recomposition_reader_state_macro_2_corrective_retry_accepts(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="copied_target_p004_then_correct",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 2
    assert len(result.payload["model_call_ids"]) == 2
    assert len(clients) == 1
    assert len(clients[0].requests) == 2
    retry_prompt = json.loads(clients[0].requests[1].input_text)
    assert retry_prompt["retry_kind"] == "target_addressed_corrective_retry"
    assert [
        item["target_paragraph_ref"]
        for item in retry_prompt["failed_target_paragraphs"]
    ] == ["target_p004"]
    failed_p004 = retry_prompt["failed_target_paragraphs"][0]
    assert failed_p004["target_paragraph_ref"] == "target_p004"
    failed_p004_spans = failed_p004["failed_target_spans"]
    assert {
        "strengthen_return_echo",
        "make_opening_return_transformational",
    } <= {span["allowed_operation"] for span in failed_p004_spans}
    assert any(
        "final_return_echo_reread_strength" in span["active_target_ids"]
        for span in failed_p004_spans
    )
    assert any(
        "opening_return_transformation_strengthening" in span["active_target_ids"]
        for span in failed_p004_spans
    )
    packet_dir = Path(str(result.payload["packet_dir"]))
    section = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    report = section["target_addressed_retry_report"]
    assert report["retry_attempted"] is True
    assert report["retry_count"] == 1
    assert report["max_retry_count"] == 1
    assert report["failed_target_paragraph_refs"] == ["target_p004"]
    assert report["retry_replaced_refs"] == ["target_p004"]
    assert "target_p001" in report["preserved_first_attempt_refs"]
    assert "target_p002" in report["preserved_first_attempt_refs"]
    assert report["merged_validation_passed"] is True
    assert report["first_attempt_model_call_id"] == result.payload["model_call_ids"][0]
    assert report["retry_model_call_id"] == result.payload["model_call_ids"][1]
    replacements = {
        item["target_paragraph_ref"]: item["replacement_text"]
        for item in section["target_paragraph_replacements"]
    }
    assert "The room does not need a witness above it." in replacements["target_p001"]
    assert "The final return keeps the table ordinary" in replacements["target_p004"]
    assert section["target_coverage_report"]["macro_target_coverage_passed"] is True
    assert section["target_coverage_report"]["macro_materiality_passed"] is True
    assert section["source_model_call_id"] == result.payload["model_call_ids"][1]
    gate = read_payload(packet_dir / "macro_recomposition_gate_report.json")
    assert gate["target_addressed_retry_report"]["retry_attempted"] is True
    assert gate["passed"] is False

    with connect(chain["config"].db_path) as connection:
        model_calls = [
            call
            for call in list_model_calls(connection, run_id=chain["run_id"])
            if call.schema_name == BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name
        ]
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert model_calls[-2].status == MODEL_CALL_VALIDATION_FAILED
    assert model_calls[-1].status == MODEL_CALL_SUCCESS
    assert final_report.refused is True


def test_bounded_macro_recomposition_reader_state_macro_2_retry_normalizes_extra_known_claim(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="copied_target_p004_retry_extra_known_claim",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 2
    packet_dir = Path(str(result.payload["packet_dir"]))
    section = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    report = section["target_addressed_retry_report"]
    assert report["retry_attempted"] is True
    assert report["failed_target_paragraph_refs"] == ["target_p004"]
    assert report["merged_validation_passed"] is True
    assert report["ignored_model_target_claims_by_paragraph_ref"] == {
        "target_p004": ["proof_no_outside_answer_refinement"]
    }
    assert report["model_target_claims_used_as_evidence"] is False
    coverage = section["target_coverage_report"]
    assert coverage["macro_target_coverage_passed"] is True
    assert coverage["ignored_model_target_claims_by_paragraph_ref"] == {
        "target_p004": ["proof_no_outside_answer_refinement"]
    }
    assert coverage["unknown_model_target_claims_by_paragraph_ref"] == {}


def test_bounded_macro_recomposition_reader_state_macro_2_retry_includes_materiality_feedback(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    synthesis_packet = prepare_macro_synthesis_base_text(
        chain["synthesis"],
        base_text=P003_RETURN_MACRO_BASE_TEXT,
    )
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=synthesis_packet,
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="near_copy_target_p003_then_correct",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 2
    retry_prompt = json.loads(clients[0].requests[1].input_text)
    assert retry_prompt["retry_kind"] == "target_addressed_corrective_retry"
    assert retry_prompt["first_attempt_failure"][
        "paragraph_materiality_failure_reason"
    ]
    assert retry_prompt["first_attempt_failure"][
        "paragraph_materiality_metrics_by_ref"
    ]["target_p003"]["changed_count"] >= 6
    assert retry_prompt["first_attempt_failure"][
        "paragraph_materiality_metrics_by_ref"
    ]["target_p003"]["changed_ratio"] < 0.18
    assert retry_prompt["first_attempt_failure"][
        "paragraph_materiality_metrics_by_ref"
    ]["target_p003"]["required_ratio"] == 0.18
    assert retry_prompt["first_attempt_failure"][
        "spans_passed_but_paragraph_failed_by_ref"
    ]["target_p003"] is True
    failed_p003 = retry_prompt["failed_target_paragraphs"][0]
    assert failed_p003["target_paragraph_ref"] == "target_p003"
    assert failed_p003["failed_target_spans"] == []
    assert failed_p003["material_target_spans"]
    assert {
        "target_p003_s001",
        "target_p003_s004",
    } <= {span["target_span_ref"] for span in failed_p003["material_target_spans"]}
    assert failed_p003["paragraph_materiality_contract"][
        "lexical_substitution_insufficient"
    ] is True
    assert "Your span mappings were not enough" in failed_p003["materiality_feedback"]
    assert "not a lexical polish" in failed_p003["retry_instruction"]
    assert "Do not copy the opening sentence architecture" in failed_p003[
        "retry_instruction"
    ]
    assert retry_prompt["work_order"]["retry_prompt_included_materiality_feedback"] is True
    assert retry_prompt["work_order"][
        "retry_prompt_included_material_spans_even_if_span_passed"
    ] is True

    packet_dir = Path(str(result.payload["packet_dir"]))
    section = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    report = section["target_addressed_retry_report"]
    assert report["paragraph_materiality_failure_reason"]
    assert report["paragraph_materiality_metrics_by_ref"]["target_p003"][
        "changed_ratio"
    ] < 0.18
    assert report["spans_passed_but_paragraph_failed_by_ref"]["target_p003"] is True
    assert report["retry_prompt_included_materiality_feedback"] is True
    assert report["retry_prompt_included_failed_span_refs"] is False
    assert report["retry_prompt_included_material_spans_even_if_span_passed"] is True
    replacements = {
        item["target_paragraph_ref"]: item["replacement_text"]
        for item in section["target_paragraph_replacements"]
    }
    assert "The return touches the first table" in replacements["target_p003"]


def test_bounded_macro_recomposition_reader_state_macro_2_p003_near_copy_still_refuses(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    synthesis_packet = prepare_macro_synthesis_base_text(
        chain["synthesis"],
        base_text=P003_RETURN_MACRO_BASE_TEXT,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=synthesis_packet,
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="near_copy_target_p003_retry_near_copy",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 2
    assert "corrective retry target_paragraph_replacements[target_p003] copied" in (
        result.payload["message"]
    )
    report = result.payload["target_addressed_retry_report"]
    assert report["failed_target_paragraph_refs"] == ["target_p003"]
    assert report["spans_passed_but_paragraph_failed_by_ref"]["target_p003"] is True
    assert report["retry_prompt_included_materiality_feedback"] is True
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_retry_collects_all_bad_refs(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="copied_target_p002_p003_then_correct",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 2
    assert len(result.payload["model_call_ids"]) == 2
    retry_prompt = json.loads(clients[0].requests[1].input_text)
    failed_refs = [
        item["target_paragraph_ref"]
        for item in retry_prompt["failed_target_paragraphs"]
    ]
    assert failed_refs == ["target_p002", "target_p003"]
    successful_refs = {
        item["target_paragraph_ref"]
        for item in retry_prompt["successful_first_attempt_replacements"]
    }
    assert "target_p002" not in successful_refs
    assert "target_p003" not in successful_refs

    section = read_payload(
        Path(str(result.payload["packet_dir"])) / "macro_patch_or_section_plan.json"
    )
    report = section["target_addressed_retry_report"]
    assert report["failed_target_paragraph_refs"] == ["target_p002", "target_p003"]
    assert "target_p003" not in report["preserved_first_attempt_refs"]
    assert report["retry_replaced_refs"] == ["target_p002", "target_p003"]
    assert report["merged_validation_passed"] is True
    assert report["first_attempt_model_call_id"] == result.payload["model_call_ids"][0]
    assert report["retry_model_call_id"] == result.payload["model_call_ids"][1]


def test_bounded_macro_recomposition_reader_state_macro_2_retry_only_p002_refuses(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="copied_target_p002_p003_retry_only_p002",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 2
    assert "corrective retry missing target paragraph replacement: target_p003" in (
        result.payload["message"]
    )
    retry_prompt = json.loads(clients[0].requests[1].input_text)
    assert [
        item["target_paragraph_ref"]
        for item in retry_prompt["failed_target_paragraphs"]
    ] == ["target_p002", "target_p003"]
    report = result.payload["target_addressed_retry_report"]
    assert report["failed_target_paragraph_refs"] == ["target_p002", "target_p003"]
    assert report["retry_replaced_refs"] == ["target_p002"]
    assert "target_p003" not in report["preserved_first_attempt_refs"]
    assert report["remaining_failed_target_paragraph_refs"] == ["target_p003"]
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_mixed_failures_aggregate(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="copied_target_p002_missing_span_p001_then_correct",
        ),
    )

    assert result.exit_code == 0
    retry_prompt = json.loads(clients[0].requests[1].input_text)
    failed_refs = [
        item["target_paragraph_ref"]
        for item in retry_prompt["failed_target_paragraphs"]
    ]
    assert "target_p001" in failed_refs
    assert "target_p002" in failed_refs
    assert retry_prompt["first_attempt_failure"]["failed_target_span_refs"]
    section = read_payload(
        Path(str(result.payload["packet_dir"])) / "macro_patch_or_section_plan.json"
    )
    report = section["target_addressed_retry_report"]
    assert "target_p001" in report["failed_target_paragraph_refs"]
    assert "target_p002" in report["failed_target_paragraph_refs"]
    assert report["failed_target_span_refs"]


def test_bounded_macro_recomposition_reader_state_macro_2_missing_and_copied_aggregate(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="missing_target_p002_copied_target_p003_then_correct",
        ),
    )

    assert result.exit_code == 0
    retry_prompt = json.loads(clients[0].requests[1].input_text)
    assert [
        item["target_paragraph_ref"]
        for item in retry_prompt["failed_target_paragraphs"]
    ] == ["target_p002", "target_p003"]
    report = read_payload(
        Path(str(result.payload["packet_dir"])) / "macro_patch_or_section_plan.json"
    )["target_addressed_retry_report"]
    assert report["failed_target_paragraph_refs"] == ["target_p002", "target_p003"]
    assert "missing target paragraph replacement" in report["failure_reasons_by_ref"][
        "target_p002"
    ]
    assert "copied or insufficiently changed" in report["failure_reasons_by_ref"][
        "target_p003"
    ]


def test_bounded_macro_recomposition_reader_state_macro_2_span_retry_accepts(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            clients,
            mode="target_p001_final_proof_only_then_correct",
        ),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 2
    retry_prompt = json.loads(clients[0].requests[1].input_text)
    assert retry_prompt["retry_kind"] == "target_addressed_corrective_retry"
    assert retry_prompt["first_attempt_failure"]["failed_target_span_refs"]
    failed_paragraph = retry_prompt["failed_target_paragraphs"][0]
    assert failed_paragraph["target_paragraph_ref"] == "target_p001"
    assert failed_paragraph["failed_target_spans"]
    assert {
        span["target_span_ref"] for span in failed_paragraph["failed_target_spans"]
    } == set(retry_prompt["first_attempt_failure"]["failed_target_span_refs"])
    assert "Changing only the final proof sentence is insufficient" in retry_prompt[
        "first_attempt_failure"
    ]["span_level_instruction"]
    packet_dir = Path(str(result.payload["packet_dir"]))
    section = read_payload(packet_dir / "macro_patch_or_section_plan.json")
    report = section["target_addressed_retry_report"]
    assert report["retry_attempted"] is True
    assert report["failed_target_paragraph_refs"] == ["target_p001"]
    assert report["failed_target_span_refs"]
    assert report["merged_validation_passed"] is True
    assert section["target_coverage_report"]["span_level_coverage_passed"] is True
    assert section["target_coverage_report"]["failed_target_span_refs"] == []


def test_bounded_macro_recomposition_reader_state_macro_2_span_retry_still_copied_refuses(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="target_p001_span_retry_copies",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 2
    report = result.payload["target_addressed_retry_report"]
    assert report["retry_attempted"] is True
    assert report["failed_target_paragraph_refs"] == ["target_p001"]
    assert report["failed_target_span_refs"]
    assert report["merged_validation_passed"] is False
    assert "target span coverage failed" in result.payload["message"]
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_retry_preserves_passed_refs(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode="retry_extra_override"),
    )

    assert result.exit_code == 0
    section = read_payload(
        Path(str(result.payload["packet_dir"])) / "macro_patch_or_section_plan.json"
    )
    report = section["target_addressed_retry_report"]
    assert report["ignored_retry_refs"] == ["target_p001"]
    replacements = {
        item["target_paragraph_ref"]: item["replacement_text"]
        for item in section["target_paragraph_replacements"]
    }
    assert "attempted retry override" not in replacements["target_p001"]
    assert "The room does not need a witness above it." in replacements["target_p001"]


def test_bounded_macro_recomposition_reader_state_macro_2_retry_budget_one_refuses(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=1,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="copied_target_p004_then_correct",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 1
    assert "Corrective retry not attempted" in result.payload["message"]
    report = result.payload["target_addressed_retry_report"]
    assert report["retry_attempted"] is False
    assert report["failed_target_paragraph_refs"] == ["target_p004"]
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_failed_retry_refuses(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="copied_target_p004_retry_copies",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 2
    report = result.payload["target_addressed_retry_report"]
    assert report["retry_attempted"] is True
    assert report["failed_target_paragraph_refs"] == ["target_p004"]
    assert report["merged_validation_passed"] is False
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_reader_state_macro_2_missing_ref_retry_accepts(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="missing_target_p002_then_correct",
        ),
    )

    assert result.exit_code == 0
    section = read_payload(
        Path(str(result.payload["packet_dir"])) / "macro_patch_or_section_plan.json"
    )
    report = section["target_addressed_retry_report"]
    assert report["retry_attempted"] is True
    assert report["failed_target_paragraph_refs"] == ["target_p002"]
    assert report["retry_replaced_refs"] == ["target_p002"]
    assert section["target_coverage_report"]["macro_target_coverage_passed"] is True


@pytest.mark.parametrize(
    "mode",
    [
        "metadata_controller_final_artifact_phrase",
        "metadata_does_not_claim_finality",
        "metadata_avoid_finality",
        "metadata_finalization_false",
    ],
)
def test_bounded_macro_recomposition_allows_nonclaim_finality_metadata(
    tmp_path,
    monkeypatch,
    mode,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=1,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode=mode),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 1
    packet_dir = Path(str(result.payload["packet_dir"]))
    gate = read_payload(packet_dir / "macro_recomposition_gate_report.json")
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True


@pytest.mark.parametrize(
    "mode, expected",
    [
        (
            "artifact_final_claim",
            "finality claim in target_paragraph_replacements[0].replacement_text",
        ),
        ("metadata_final_artifact_claim", "finality claim in rationale"),
        ("final_claim", "phase-shift claim in rationale"),
        ("rival_defeated_claim", "rival-defeat claim in rationale"),
    ],
)
def test_bounded_macro_recomposition_rejects_affirmative_finality_claims_with_path(
    tmp_path,
    monkeypatch,
    mode,
    expected,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert result.payload["target_addressed_retry_report"]["retry_attempted"] is False
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]


def test_bounded_macro_recomposition_finality_metadata_false_positive_reaches_target_failure(
    tmp_path,
    monkeypatch,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=1,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(
            [],
            mode="metadata_final_artifact_plus_copied_target_p003",
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "finality claim" not in result.payload["message"]
    assert "target_paragraph_replacements[target_p003] copied" in result.payload[
        "message"
    ]
    assert result.payload["target_addressed_retry_report"]["retry_attempted"] is False
    assert result.payload["target_addressed_retry_report"][
        "failed_target_paragraph_refs"
    ] == ["target_p003"]


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("invalid_json", "Corrective retry not attempted"),
        ("final_claim", "Corrective retry not attempted"),
    ],
)
def test_bounded_macro_recomposition_does_not_retry_schema_or_final_claim_failures(
    tmp_path,
    monkeypatch,
    mode,
    expected,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=2,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 1
    assert expected in result.payload["message"]
    assert result.payload["target_addressed_retry_report"]["retry_attempted"] is False


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("missing_target_p002", "missing target paragraph replacement: target_p002"),
        ("copied_target_p002", "proof_no_outside_answer_refinement"),
        ("near_copy_target_p003", "copied or insufficiently changed"),
        ("copied_target_p004", "final_return_echo_reread_strength"),
        ("mismatched_target_hash", "before_text_sha256 mismatch"),
        ("duplicate_target_ref", "duplicate target_paragraph_ref"),
        ("thesis_target_uncovered", "thesis_visible_proof_language_reduction"),
        ("target_p001_final_proof_only", "target span coverage failed"),
        ("missing_target_span_p001_s001", "missing target span replacement"),
        ("mismatched_target_span_hash", "before_text_sha256 mismatch"),
    ],
)
def test_bounded_macro_recomposition_reader_state_macro_2_live_validation_failures(
    tmp_path,
    monkeypatch,
    mode,
    expected,
):
    chain = build_reader_state_macro_synthesis_chain(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        chain["config"],
        client_name="openai",
        synthesis_packet=Path(str(chain["synthesis"]["packet_dir"])),
        allow_live_model=True,
        max_model_calls=1,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]
    with connect(chain["config"].db_path) as connection:
        model_calls = [
            call
            for call in list_model_calls(connection, run_id=chain["run_id"])
            if call.schema_name == BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name
        ]
        final_report = check_finalization(
            connection,
            run_id=chain["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert model_calls[-1].status == MODEL_CALL_VALIDATION_FAILED
    assert model_calls[-1].parsed_output_artifact_id is None
    assert final_report.refused is True


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("missing_constraint", "constraint_mapping must contain exactly"),
        ("duplicate_constraint", "duplicate constraint_id"),
        ("empty_excerpt", "supporting excerpt is empty"),
    ],
)
def test_bounded_macro_recomposition_live_constraint_mapping_failures(
    tmp_path,
    monkeypatch,
    mode,
    expected,
):
    config, _failed_ablation, _pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    synthesis_packet = prepare_multi_paragraph_macro_synthesis(synthesis.payload)
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet,
        allow_live_model=True,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory(clients, mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert "macro_recomposition_plan" not in result.payload["artifact_ids"]
    with connect(config.db_path) as connection:
        model_calls = list_model_calls(connection, run_id=run_id)
    macro_call = [
        call
        for call in model_calls
        if call.schema_name == BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name
    ][0]
    assert macro_call.status == MODEL_CALL_VALIDATION_FAILED
    assert macro_call.parsed_output_artifact_id is None


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("missing_active_target", "active_target_mapping must contain exactly"),
        ("unchanged_without_justification", "unchanged target requires justification"),
    ],
)
def test_bounded_macro_recomposition_live_active_target_mapping_failures(
    tmp_path,
    monkeypatch,
    mode,
    expected,
):
    config, _failed_ablation, _pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    synthesis_packet = prepare_multi_paragraph_macro_synthesis(synthesis.payload)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet,
        allow_live_model=True,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert "macro_recomposition_plan" not in result.payload["artifact_ids"]
    with connect(config.db_path) as connection:
        model_calls = [
            call
            for call in list_model_calls(connection, run_id=run_id)
            if call.schema_name == BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name
        ]
    assert model_calls[0].status == MODEL_CALL_VALIDATION_FAILED
    assert model_calls[0].parsed_output_artifact_id is None


@pytest.mark.parametrize(
    "mode, expected_missing",
    [
        ("copied_first_two", "middle_abstraction_ladder_compression"),
        ("proof_unchanged", "proof_line_redundancy_cleanup"),
        ("no_answer_unchanged", "no_outside_answer_pressure_preservation"),
        ("final_only_change", "middle_abstraction_ladder_compression"),
        ("mostly_copied", "middle_abstraction_ladder_compression"),
    ],
)
def test_bounded_macro_recomposition_live_target_coverage_failures(
    tmp_path,
    monkeypatch,
    mode,
    expected_missing,
):
    config, _failed_ablation, _pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    synthesis_packet = prepare_multi_paragraph_macro_synthesis(synthesis.payload)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet,
        allow_live_model=True,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "macro target coverage failed" in result.payload["message"]
    assert expected_missing in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    assert "macro_recomposition_packet" not in result.payload["artifact_ids"]
    with connect(config.db_path) as connection:
        model_calls = [
            call
            for call in list_model_calls(connection, run_id=run_id)
            if call.schema_name == BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name
        ]
    assert model_calls[0].status == MODEL_CALL_VALIDATION_FAILED
    assert model_calls[0].parsed_output_artifact_id is None


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("outside_rescue", "outside-rescue violation"),
        ("proof_from_outside", "proof-from-outside violation"),
        ("final_claim", "phase-shift claim"),
        ("prefix_rewrite", "controller-owned prefix"),
    ],
)
def test_bounded_macro_recomposition_live_rejects_forbidden_model_outputs(
    tmp_path,
    monkeypatch,
    mode,
    expected,
):
    config, _failed_ablation, _pivot_revision, _useful_revision = (
        build_fake_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    synthesis_packet = prepare_multi_paragraph_macro_synthesis(synthesis.payload)
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    result = run_bounded_macro_recomposition(
        config,
        client_name="openai",
        synthesis_packet=synthesis_packet,
        allow_live_model=True,
        api_key="stub-key",
        model="stub-live-macro",
        client_factory=bounded_macro_stub_factory([], mode=mode),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert expected in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 1
    with connect(config.db_path) as connection:
        model_calls = [
            call
            for call in list_model_calls(connection, run_id=run_id)
            if call.schema_name == BOUNDED_MACRO_RECOMPOSITION_SCHEMA.name
        ]
    assert model_calls[0].status == MODEL_CALL_VALIDATION_FAILED
    assert model_calls[0].parsed_output_artifact_id is None
