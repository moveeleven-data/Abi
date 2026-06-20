import json
from pathlib import Path

import pytest

import abi.modules.autonomous_revision as autonomous_revision_module
from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.policy import GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
from abi.controller.state import AUTONOMOUS_CLOSED_LOOP_REVISION_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.model_calls import MODEL_CALL_SUCCESS, MODEL_CALL_VALIDATION_FAILED, list_model_calls
from abi.model_schemas import (
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
from abi.modules.executed_ablation import (
    EXECUTED_ABLATION_ARTIFACT_TYPES,
    _build_comparison_consistency_report,
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
