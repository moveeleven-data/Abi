import json
from pathlib import Path

import pytest

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.policy import GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
from abi.controller.state import AUTONOMOUS_CLOSED_LOOP_REVISION_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.model_calls import MODEL_CALL_SUCCESS, MODEL_CALL_VALIDATION_FAILED, list_model_calls
from abi.model_schemas import (
    AUTONOMOUS_REVISION_ABLATION_EVIDENCE_BASIS,
    AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_ABLATION_VARIANT_SET_SCHEMA,
    AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA,
    AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA,
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
    FakeAutonomousRevisionModelClient,
    run_autonomous_revision,
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
                "row_id": "comparison_variant_01",
                "executed_variant_id": "variant_01",
                "planned_probe_id": None,
                "operation": "remove_suspected_causal_handle",
                "planned_only": False,
                "evidence_basis": "actual_ablation_variant",
                "comparison_summary": "Executed variant isolates the suspected handle.",
                "predicted_or_observed_effect": "reread pressure decreases predictably",
                "rationale": "Uses an actual generated ablation variant, not a planned probe.",
                "not_human_data": True,
            },
            {
                "row_id": "comparison_planned_probe_01",
                "executed_variant_id": None,
                "planned_probe_id": "planned_probe_01",
                "operation": "move_motif_earlier_later",
                "planned_only": True,
                "evidence_basis": "planned_ablation_probe",
                "comparison_summary": "Planned probe is recorded without claiming execution.",
                "predicted_or_observed_effect": "predicted effect only",
                "rationale": "The probe has no generated variant yet.",
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
            payload["span_ref"]["region"] = "ending paragraph only"
            payload["target_region_label"] = "target_region:ending_paragraph_only"
            payload["target_region_description"] = (
                "Selected bounded revision target; material edits outside this region "
                "require explicit target expansion."
            )
            payload["allowed_span_refs"] = ["ending paragraph only"]
            payload["protected_outside_spans"] = [
                "all candidate spans outside ending paragraph only"
            ]
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class DisallowedPatchTargetClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            patch = payload["patches"][0]
            patch["target_span_ref"]["region"] = "ending paragraph only"
            patch["target_region_label"] = "target_region:ending_paragraph_only"
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
            patch["target_span_ref"]["region"] = "opening paragraph"
            patch["target_region_label"] = "target_region:opening_paragraph"
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
        if request.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
            payload["comparison_rows"].append(
                {
                    "row_id": "comparison_planned_probe_99",
                    "executed_variant_id": None,
                    "planned_probe_id": "planned_probe_99",
                    "operation": "move_motif_earlier_later",
                    "planned_only": True,
                    "evidence_basis": "planned_ablation_probe",
                    "comparison_summary": "planned probe, not executed ablation evidence",
                    "predicted_or_observed_effect": "planned_probe_only",
                    "rationale": "requires a generated variant before evidence use",
                    "not_human_data": True,
                }
            )
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class InvalidAblationComparisonClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA:
            payload["comparison_rows"].append(
                {
                    "row_id": "comparison_missing_variant_99",
                    "executed_variant_id": "missing_variant_99",
                    "planned_probe_id": None,
                    "operation": "move_motif_earlier_later",
                    "planned_only": False,
                    "evidence_basis": "actual_ablation_variant",
                    "comparison_summary": "bad row should fail before artifact registration",
                    "predicted_or_observed_effect": "claimed_executed_without_variant",
                    "rationale": "must reference a variant or be planned_only",
                    "not_human_data": True,
                }
            )
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


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
        "autonomous_revision_artifacts": 12,
        "required_autonomous_revision_artifacts": 12,
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

    handle = read_payload(result.payload["artifact_paths"]["causal_handle_selection"])
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
    assert patch_proposal["full_rewrite"] is False
    assert patch_proposal["bounded_patch_set"] is True

    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    assert revised["text"]
    assert revised["assembled_by_controller"] is True
    assert revised["source_patch_ids"] == ["patch_01"]
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
    assert diff["source_patch_ids"] == ["patch_01"]
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
    assert "target_span_ref" in patch_item["required"]

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


def test_ablation_comparison_schema_distinguishes_executed_and_planned_rows():
    schema = json_schema_for_worker_schema(AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA)
    row_schema = schema["properties"]["comparison_rows"]["items"]

    assert "variant_id" not in row_schema["properties"]
    assert row_schema["properties"]["evidence_basis"]["enum"] == list(
        AUTONOMOUS_REVISION_ABLATION_EVIDENCE_BASIS
    )

    parsed = parse_and_validate_structured_output(
        dump_json(valid_ablation_comparison_payload()),
        AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
    )

    executed_row = parsed["comparison_rows"][0]
    planned_row = parsed["comparison_rows"][1]
    assert executed_row["executed_variant_id"] == "variant_01"
    assert executed_row["planned_probe_id"] is None
    assert planned_row["planned_only"] is True
    assert planned_row["executed_variant_id"] is None
    assert planned_row["planned_probe_id"] == "planned_probe_01"


def test_ablation_comparison_rejects_planned_row_with_executed_variant_id():
    payload = valid_ablation_comparison_payload()
    payload["comparison_rows"][1]["executed_variant_id"] = "variant_99"

    with pytest.raises(ModelValidationError, match="executed_variant_id must be null"):
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
        "autonomous_revision_artifacts": 12,
        "required_autonomous_revision_artifacts": 12,
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
    reviser_request = next(
        request
        for request in client.requests
        if request.schema == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA
    )
    reviser_prompt = json.loads(reviser_request.input_text)
    assert "selected_target_contract" in reviser_prompt
    assert "candidate_reviser_target_contract" in reviser_prompt
    assert "Return patch operations only" in reviser_prompt["candidate_reviser_target_contract"]
    assert not any(
        request.schema == AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA for request in client.requests
    )
    ablation_request = next(
        request
        for request in client.requests
        if request.schema == AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA
    )
    ablation_prompt = json.loads(ablation_request.input_text)
    assert ablation_prompt["allowed_executed_ablation_variant_ids"] == [
        f"variant_{index:02d}" for index in range(1, 9)
    ]
    assert "do not use short labels like v4" in ablation_prompt[
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
        assert envelope["created_by"] == "model_driver:openai:stub-autonomous-revision-model"

    for artifact_type in (
        "autonomous_revision_subject_manifest",
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

    handle = read_payload(result.payload["artifact_paths"]["causal_handle_selection"])
    assert handle["bounded_target"] is True
    assert handle["target_count"] == 1
    assert handle["does_not_rebuild_artifact"] is True
    assert handle["target_region_label"]
    assert handle["allowed_span_refs"]
    assert handle["protected_outside_spans"]

    patch_proposal = read_payload(result.payload["artifact_paths"]["revision_patch_proposal"])
    assert patch_proposal["patches"]
    assert "text" not in patch_proposal
    assert patch_proposal["bounded_patch_set"] is True
    assert patch_proposal["full_rewrite"] is False

    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    assert revised["assembled_by_controller"] is True
    assert revised["source_patch_ids"] == ["patch_01"]
    assert revised["bounded_recomposition"] is True
    assert revised["full_rewrite"] is False
    assert revised["non_final"] is True
    assert revised["not_human_validated"] is True
    assert revised["not_finalization_eligible"] is True

    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    assert diff["assembled_by_controller"] is True
    assert diff["source_patch_ids"] == ["patch_01"]
    assert diff["bounded_change"] is True
    assert diff["changed_spans"]
    assert diff["target_region_expanded"] is False
    assert diff["expanded_target_region"] == ""
    assert diff["expansion_reason"] == ""
    assert diff["target_region_label"] == handle["target_region_label"]
    assert all("changed_span_id" in span for span in diff["changed_spans"])
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
    assert all(row["planned_only"] is False for row in ablation["comparison_rows"])
    assert {
        row["executed_variant_id"] for row in ablation["comparison_rows"]
    } == executed_variant_ids
    assert {row["planned_probe_id"] for row in ablation["comparison_rows"]} == {None}

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
    assert "targets disallowed span" in result.payload["message"]
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
    assert "changes outside selected target region" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "inside_target=False" in result.payload["message"]
    assert "expansion_absent=True" in result.payload["message"]
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


def test_stubbed_openai_explicit_target_expansion_passes(tmp_path):
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

    assert result.exit_code == 0
    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_closed_loop_gate_report"])
    assert diff["target_region_expanded"] is True
    assert diff["expanded_target_region"] == "opening paragraph plus ending paragraph"
    assert diff["expansion_reason"]
    assert diff["target_expansion_justification"]
    assert any(not span["inside_target"] for span in diff["changed_spans"])
    assert all(
        span["requires_target_expansion"]
        for span in diff["changed_spans"]
        if not span["inside_target"]
    )
    assert gate_report["integrity_report"]["target"]["target_region_expanded"] is True
    assert gate_report["integrity_report"]["target"]["out_of_target_change_count"] >= 1
    assert gate_report["eligible"] is False


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
    ablation = read_payload(result.payload["artifact_paths"]["ablation_reread_comparison"])
    planned_rows = [row for row in ablation["comparison_rows"] if row["planned_only"]]
    assert planned_rows
    assert all(row["executed_variant_id"] is None for row in planned_rows)
    assert all(row["planned_probe_id"] for row in planned_rows)
    assert {row["evidence_basis"] for row in planned_rows} == {"planned_ablation_probe"}

    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_closed_loop_gate_report"])
    evidence = gate_report["ablation_evidence"]
    assert evidence["planned_only_comparison_row_count"] == len(planned_rows)
    assert evidence["planned_only_ablation_probe_count"] == len(planned_rows)
    assert evidence["ablation_variants_executed"] is True
    assert evidence["executed_comparison_row_count"] == len(ablation["comparison_rows"]) - len(
        planned_rows
    )
    assert evidence["predicted_only_comparison_row_count"] == len(ablation["comparison_rows"])
    assert evidence["actual_ablation_comparison_evidence_count"] == 0
    assert evidence["ablation_comparison_predicted_only"] is True
    assert evidence["ablation_comparison_actually_evaluated"] is False


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
    assert "ablation_reread_comparison rows are not aligned" in result.payload["message"]
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
        "causal_handle_selection",
    }
    assert final_report.refused is True
