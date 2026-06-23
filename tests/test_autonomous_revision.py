import json
import shutil
from pathlib import Path

import pytest

import abi.modules.ablation_informed_revision as ablation_informed_revision_module
import abi.modules.autonomous_revision as autonomous_revision_module
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
    ModelValidationError,
    WorkerRole,
    json_schema_for_worker_schema,
    parse_and_validate_structured_output,
)
from abi.openai_adapter import openai_response_format_for_request
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
    _load_subject,
    run_executed_ablation,
)
from abi.modules.internal_reader_lab import FakeInternalReaderLabModelClient, run_internal_reader_lab
from abi.modules.internal_reader_state_evaluation import run_internal_reader_state_evaluation
from abi.modules.next_target_strategy import (
    NEXT_TARGET_STRATEGY_ARTIFACT_TYPES,
    run_next_target_strategy,
)
from abi.modules.pilot_artifact_set import import_pilot_rival, run_pilot_artifact_set


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
        return dump_json(
            {
                "comparison_rows": [
                    {
                        "variant_id": variant["variant_id"],
                        "comparison_summary": "stub comparison interpretation",
                        "reader_state_effect_estimate": "stub reader-state estimate",
                        "rationale": "stub rationale, not human data",
                        "uncertainty": "medium",
                        "risk_notes": "stub risk note",
                        "not_human_data": True,
                    }
                    for variant in prompt["variants"]
                ],
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
    assert packet["proof_packet_id"] == chain["macro2_proof"]["packet_id"]
    assert packet["reader_state_packet_id"] == chain["macro2_reader_state"]["packet_id"]
    assert packet["counts"]["model_calls"] == 0
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
