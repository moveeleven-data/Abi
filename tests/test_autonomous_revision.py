import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.policy import GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
from abi.controller.state import AUTONOMOUS_CLOSED_LOOP_REVISION_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.model_calls import MODEL_CALL_SUCCESS, MODEL_CALL_VALIDATION_FAILED, list_model_calls
from abi.model_schemas import (
    AUTONOMOUS_REVISION_ABLATION_REREAD_COMPARISON_SCHEMA,
    AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA,
    AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA,
    AUTONOMOUS_REVISION_MODEL_SCHEMAS,
    AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA,
    json_schema_for_worker_schema,
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


class UnreportedMaterialChangeClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        if request.schema != AUTONOMOUS_REVISION_REVISED_CANDIDATE_SCHEMA:
            return raw_output
        payload = json.loads(raw_output)
        payload["text"] = (
            str(payload["text"])
            + " The cup by the sill made a second record that the diff never names."
        )
        return dump_json(payload)


class TargetRegionViolationClient(FakeAutonomousRevisionModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_CAUSAL_HANDLE_SCHEMA:
            payload["span_ref"]["region"] = "ending paragraph only"
            self.payloads[request.schema.artifact_type] = payload
            return dump_json(payload)
        return raw_output


class ExplicitTargetExpansionClient(TargetRegionViolationClient):
    def generate(self, request):
        raw_output = super().generate(request)
        payload = json.loads(raw_output)
        if request.schema == AUTONOMOUS_REVISION_DIFF_REPORT_SCHEMA:
            payload["target_region"] = "opening paragraph plus ending paragraph"
            payload["target_region_expanded"] = True
            payload["target_expansion_justification"] = (
                "The selected ending pressure depends on the opening object record, "
                "so the repair explicitly expands the target."
            )
            for span in payload["changed_spans"]:
                span["within_selected_target"] = False
                span["region"] = "opening paragraph"
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
                    "variant_id": "planned_probe_99",
                    "operation": "move_motif_earlier_later",
                    "predicted_reread_pressure_delta": "planned_probe_only",
                    "local_law_read": "planned probe, not executed ablation evidence",
                    "pass_fail_criterion": "requires a generated variant before evidence use",
                    "planned_only": True,
                    "evidence_basis": "planned_probe_only",
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
                    "variant_id": "missing_variant_99",
                    "operation": "move_motif_earlier_later",
                    "predicted_reread_pressure_delta": "claimed_executed_without_variant",
                    "local_law_read": "bad row should fail controller integrity",
                    "pass_fail_criterion": "must reference a variant or be planned_only",
                    "planned_only": False,
                    "evidence_basis": "actual_variant_predicted_effect",
                    "not_human_data": True,
                }
            )
            self.payloads[request.schema.artifact_type] = payload
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
        "autonomous_revision_artifacts": 11,
        "required_autonomous_revision_artifacts": 11,
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

    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    assert revised["text"]
    assert revised["bounded_recomposition"] is True
    assert revised["full_rewrite"] is False
    assert revised["non_final"] is True
    assert revised["candidate_only"] is True
    assert revised["not_human_validated"] is True
    assert revised["not_finalization_eligible"] is True
    assert revised["finalization_eligible"] is False
    assert revised["phase_shift_claim"] is False

    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    assert diff["full_rewrite"] is False
    assert diff["bounded_change"] is True
    assert diff["operation"]["type"] == "append_local_consequence"

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

    variants_schema = json_schema_for_worker_schema(AUTONOMOUS_REVISION_MODEL_SCHEMAS[4])
    variant_item = variants_schema["properties"]["variants"]["items"]
    assert variant_item["type"] == "object"
    assert variant_item["additionalProperties"] is False


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
        "autonomous_revision_artifacts": 11,
        "required_autonomous_revision_artifacts": 11,
        "model_calls": 8,
        "recorded_autonomous_gates": 5,
    }

    model_calls = result.payload["model_calls"]
    assert len(model_calls) == 8
    assert {call["status"] for call in model_calls} == {MODEL_CALL_SUCCESS}
    assert {call["provider"] for call in model_calls} == {"openai"}
    assert {call["model"] for call in model_calls} == {"stub-autonomous-revision-model"}
    assert all(call["input_hash"] for call in model_calls)
    assert all(
        call["prompt_contract_id"].startswith("autonomous.revision.")
        for call in model_calls
    )

    client = clients[0]
    assert len(client.requests) == 8
    assert "reader_lab_payloads" in client.requests[0].input_text
    assert "source_texts" in client.requests[0].input_text

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

    assert len(revision_calls) == 8
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

    revised = read_payload(result.payload["artifact_paths"]["revised_candidate_text"])
    assert revised["bounded_recomposition"] is True
    assert revised["full_rewrite"] is False
    assert revised["non_final"] is True
    assert revised["not_human_validated"] is True
    assert revised["not_finalization_eligible"] is True

    diff = read_payload(result.payload["artifact_paths"]["revision_diff_report"])
    assert diff["bounded_change"] is True
    assert diff["changed_spans"]
    assert diff["target_region_expanded"] is False

    variants = read_payload(result.payload["artifact_paths"]["ablation_variant_set"])
    assert variants["variants"]
    assert all(variant["executed"] is True for variant in variants["variants"])
    ablation = read_payload(result.payload["artifact_paths"]["ablation_reread_comparison"])
    assert ablation["comparison_rows"]
    assert all(row["planned_only"] is False for row in ablation["comparison_rows"])

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


def test_stubbed_openai_unreported_material_change_fails_closed(tmp_path):
    config, lab_payload = build_live_style_reader_lab_packet(tmp_path)
    clients: list[FakeAutonomousRevisionModelClient] = []

    result = run_autonomous_revision(
        config,
        client_name="openai",
        reader_lab_packet=lab_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-autonomous-revision-model",
        client_factory=custom_revision_factory(clients, UnreportedMaterialChangeClient),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "integrity validation failure" in result.payload["message"]
    assert "revision_diff_report does not cover material text changes" in result.payload[
        "message"
    ]
    assert result.payload["counts"]["model_calls"] == 8
    assert "autonomous_closed_loop_packet" not in result.payload["artifact_ids"]
    assert "autonomous_closed_loop_gate_report" not in result.payload["artifact_ids"]


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
    assert "changes outside selected target region" in result.payload["message"]
    assert "autonomous_closed_loop_packet" not in result.payload["artifact_ids"]


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
    assert diff["target_expansion_justification"]
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

    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_closed_loop_gate_report"])
    evidence = gate_report["ablation_evidence"]
    assert evidence["planned_only_comparison_row_count"] == len(planned_rows)
    assert evidence["ablation_variants_executed"] is True
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
    assert "autonomous_closed_loop_packet" not in result.payload["artifact_ids"]


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
