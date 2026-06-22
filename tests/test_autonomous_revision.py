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
    json_schema_for_worker_schema,
    parse_and_validate_structured_output,
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
    run_autonomous_evidence_synthesis,
)
from abi.modules.bounded_macro_recomposition import (
    ACTIVE_TRANSFORMATION_TARGET_IDS,
    BOUNDED_MACRO_RECOMPOSITION_ARTIFACT_TYPES,
    REQUIRED_SEMANTIC_CONSTRAINT_IDS,
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


def prepare_multi_paragraph_macro_synthesis(synthesis_payload: dict[str, object]) -> Path:
    synthesis_packet = Path(str(synthesis_payload["packet_dir"]))
    best_path = synthesis_packet / "best_current_candidate_selection.json"
    best = read_payload(best_path)
    selected = best["selected_best_candidate"]
    base_packet = Path(str(selected["packet_dir"]))
    base_text_path = base_packet / "cycle2_revised_candidate_text.json"
    text_sha = sha256_text(MULTI_PARAGRAPH_MACRO_BASE_TEXT)

    def _rewrite_base(payload):
        payload["text"] = MULTI_PARAGRAPH_MACRO_BASE_TEXT
        payload["text_sha256"] = text_sha
        payload["word_count"] = len(MULTI_PARAGRAPH_MACRO_BASE_TEXT.split())

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
        payload = live_macro_payload(prompt.get("active_transformation_targets", []))
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
            payload["rationale"] = "This achieves phase-shift success."
        elif self.mode == "prefix_rewrite":
            payload["replacement_section_text"] = (
                f"{prompt['unchanged_prefix_text']}\n\n{payload['replacement_section_text']}"
            )
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
            "target_movement": "middle_and_return_movement",
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
        "rationale": "The bounded section shifts pressure into scene and relation.",
        "local_law_explanation": "Each local mark becomes legible through another mark.",
        "uncertainty": "medium",
        "predicted_reader_state_effect": (
            "The reader should feel the return as changed relation rather than explanation."
        ),
    }


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
            "unchanged": False,
            "unchanged_justification": "",
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
    item_schema = schema["properties"]["constraint_mapping"]["items"]
    assert item_schema["additionalProperties"] is False
    assert "supporting_replacement_excerpt" in item_schema["required"]
    active_item_schema = schema["properties"]["active_target_mapping"]["items"]
    assert active_item_schema["additionalProperties"] is False
    assert "target_id" in active_item_schema["required"]
    assert "unchanged_justification" in active_item_schema["required"]


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
