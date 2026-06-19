import json
from pathlib import Path

import pytest

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.policy import (
    AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES,
    GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
)
from abi.db import connect
from abi.model_calls import MODEL_CALL_SUCCESS, MODEL_CALL_VALIDATION_FAILED, list_model_calls
from abi.model_schemas import (
    AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA,
    FORENSIC_GROUNDING_READER_SCHEMA,
    INTERNAL_FAILURE_DIAGNOSIS_SCHEMA,
    INTERNAL_FAILURE_TYPES,
    INTERNAL_HOSTILE_RISK_FAILURE_TYPE_MAP,
    INTERNAL_READER_LAB_MODEL_SCHEMAS,
    ModelValidationError,
    json_schema_for_worker_schema,
    normalize_internal_failure_type,
    parse_and_validate_structured_output,
)
from abi.modules.internal_reader_lab import (
    FakeInternalReaderLabModelClient,
    INTERNAL_READER_LAB_ARTIFACT_TYPES,
    run_internal_reader_lab,
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


def internal_failure_payload(*failure_types: str) -> dict[str, object]:
    return {
        "failure_types_present": list(failure_types),
        "failures": [
            {
                "failure_type": failure_type,
                "diagnosis": f"{failure_type} blocks the current candidate.",
                "evidence_artifacts": ["hostile_reader_report"],
                "severity": "blocking",
            }
            for failure_type in failure_types
        ],
        "requires_recomposition": True,
        "reread_gain_estimate": {
            "score": 0.4,
            "scale": "0_to_1",
            "not_human_score": True,
        },
        "not_human_data": True,
    }


def build_pilot_packet(
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
    packet_payload = pilot.payload
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
            packet_dir=pilot.payload["packet_dir"],
            rival_file=rival_file,
        )
        assert imported.exit_code == 0
        packet_payload = imported.payload
    return config, packet_payload


def stub_factory(
    clients: list[FakeInternalReaderLabModelClient],
    *,
    mode: str = "valid",
    target_schema=FORENSIC_GROUNDING_READER_SCHEMA,
):
    def _factory(model: str) -> FakeInternalReaderLabModelClient:
        client = FakeInternalReaderLabModelClient(
            provider="openai",
            model=model,
            mode=mode,
            target_schema=target_schema,
        )
        clients.append(client)
        return client

    return _factory


class OverreachingGateReportClient(FakeInternalReaderLabModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        if request.schema != AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA:
            return raw_output
        payload = json.loads(raw_output)
        payload.update(
            {
                "profile": "paper_public_final",
                "passed": True,
                "eligible": True,
                "required_gates": ["model_chosen_gate"],
                "failed_gates": [],
                "missing_gates": [],
                "human_validation_required": True,
                "paper_validation_required": True,
                "phase_shift_claim": True,
                "final_gates_marked_passed": [
                    "real_human_validation_passed",
                    "final_operator_approval",
                ],
                "summary_verdict": "The model attempted to approve the candidate.",
            }
        )
        for gate_result in payload["gate_results"]:
            if gate_result["gate_name"] in {
                "no_unresolved_internal_blockers",
                "internal_operator_approval",
            }:
                gate_result["passed"] = True
                gate_result["blocking_defects"] = []
                gate_result["record"] = True
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


class BadForensicSupportClient(FakeInternalReaderLabModelClient):
    def generate(self, request):
        raw_output = super().generate(request)
        if request.schema != FORENSIC_GROUNDING_READER_SCHEMA:
            return raw_output
        payload = json.loads(raw_output)
        payload["exact_textual_support"][0]["quoted_span"] = (
            "this span is not present in the candidate artifact text"
        )
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def test_internal_reader_lab_schema_catalog_exposes_internal_worker_schemas():
    for schema in INTERNAL_READER_LAB_MODEL_SCHEMAS:
        exposed = json_schema_for_worker_schema(schema)
        assert exposed["type"] == "object"
        assert exposed["required"]
        assert_strict_object_schema(exposed, path=schema.name)


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


def test_internal_reader_lab_nested_array_item_schemas_are_strict_objects():
    stream_schema = json_schema_for_worker_schema(INTERNAL_READER_LAB_MODEL_SCHEMAS[0])
    attention_item = stream_schema["properties"]["attention_points"]["items"]
    assert attention_item["type"] == "object"
    assert attention_item["additionalProperties"] is False
    assert attention_item["required"] == ["span", "reason"]

    gate_schema = json_schema_for_worker_schema(INTERNAL_READER_LAB_MODEL_SCHEMAS[-1])
    gate_item = gate_schema["properties"]["gate_results"]["items"]
    assert gate_item["type"] == "object"
    assert gate_item["additionalProperties"] is False
    assert gate_item["required"] == ["gate_name", "passed", "blocking_defects", "record"]

    forensic_schema = json_schema_for_worker_schema(FORENSIC_GROUNDING_READER_SCHEMA)
    support_item = forensic_schema["properties"]["exact_textual_support"]["items"]
    assert support_item["type"] == "object"
    assert support_item["additionalProperties"] is False
    assert support_item["required"] == [
        "claim",
        "source_label",
        "quoted_span",
        "support_reason",
    ]


def test_internal_failure_schema_enum_matches_canonical_validator():
    schema = json_schema_for_worker_schema(INTERNAL_FAILURE_DIAGNOSIS_SCHEMA)
    types_enum = schema["properties"]["failure_types_present"]["items"]["enum"]
    failure_enum = schema["properties"]["failures"]["items"]["properties"]["failure_type"]["enum"]
    assert tuple(types_enum) == INTERNAL_FAILURE_TYPES
    assert tuple(failure_enum) == INTERNAL_FAILURE_TYPES

    payload = internal_failure_payload(*INTERNAL_FAILURE_TYPES)
    parsed = parse_and_validate_structured_output(
        json.dumps(payload),
        INTERNAL_FAILURE_DIAGNOSIS_SCHEMA,
    )

    assert tuple(parsed["failure_types_present"]) == INTERNAL_FAILURE_TYPES
    assert [failure["failure_type"] for failure in parsed["failures"]] == list(
        INTERNAL_FAILURE_TYPES
    )


def test_internal_failure_taxonomy_accepts_thesis_replacing_artifact():
    payload = internal_failure_payload("thesis_replacing_artifact")

    parsed = parse_and_validate_structured_output(
        json.dumps(payload),
        INTERNAL_FAILURE_DIAGNOSIS_SCHEMA,
    )

    assert parsed["failure_types_present"] == ["thesis_replacing_artifact"]
    assert parsed["failures"][0]["failure_type"] == "thesis_replacing_artifact"


def test_internal_failure_taxonomy_maps_known_hostile_terms_only():
    assert normalize_internal_failure_type("overexplanation") == "overexplained"
    assert normalize_internal_failure_type("scaffold_leakage") == "thesis_replacing_artifact"
    assert normalize_internal_failure_type("wrong_register") == "cadence_or_register_damage"
    assert normalize_internal_failure_type("accidental_comedy") == "wrong_scale"
    assert normalize_internal_failure_type("cliche_contamination") == "unlicensed_field"
    assert normalize_internal_failure_type("pasted_ending") == "motif_returns_unchanged"
    assert normalize_internal_failure_type("unearned_cosmic_scale") == "wrong_scale"
    assert set(INTERNAL_HOSTILE_RISK_FAILURE_TYPE_MAP).issuperset(
        {
            "fake_depth",
            "overexplanation",
            "scaffold_leakage",
            "wrong_register",
            "accidental_comedy",
            "cliche_contamination",
            "thesis_replacing_artifact",
            "pasted_ending",
            "unearned_cosmic_scale",
        }
    )


def test_internal_failure_taxonomy_rejects_arbitrary_types():
    with pytest.raises(ModelValidationError):
        normalize_internal_failure_type("totally_random_scanner_label")

    payload = internal_failure_payload("totally_random_scanner_label")
    with pytest.raises(ModelValidationError):
        parse_and_validate_structured_output(
            json.dumps(payload),
            INTERNAL_FAILURE_DIAGNOSIS_SCHEMA,
        )


def test_stubbed_openai_internal_reader_lab_creates_model_artifacts(tmp_path):
    config, pilot_payload = build_pilot_packet(tmp_path, with_rival=True)
    clients: list[FakeInternalReaderLabModelClient] = []

    result = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=pilot_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-internal-reader-model",
        client_factory=stub_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "openai"
    assert result.payload["model"] == "stub-internal-reader-model"
    assert set(result.payload["artifact_ids"]) == set(INTERNAL_READER_LAB_ARTIFACT_TYPES)
    assert result.payload["counts"] == {
        "internal_reader_lab_artifacts": 11,
        "required_internal_reader_lab_artifacts": 11,
        "model_calls": 9,
        "recorded_autonomous_gates": 12,
    }

    model_calls = result.payload["model_calls"]
    assert len(model_calls) == 9
    assert {call["status"] for call in model_calls} == {MODEL_CALL_SUCCESS}
    assert {call["provider"] for call in model_calls} == {"openai"}
    assert {call["model"] for call in model_calls} == {"stub-internal-reader-model"}
    assert all(call["input_hash"] for call in model_calls)
    assert all(call["prompt_contract_id"].startswith("autonomous.reader_lab.") for call in model_calls)

    client = clients[0]
    assert len(client.requests) == 9
    assert "source_class" not in client.requests[0].input_text
    assert "source_class" not in client.requests[1].input_text
    candidate_text = json.loads(client.requests[0].input_text)["candidate"]["text"]
    forensic_request = next(
        request
        for request in client.requests
        if request.prompt_contract_id.endswith(".forensic_reader.v1")
    )
    forensic_prompt = json.loads(forensic_request.input_text)
    assert forensic_prompt["forensic_grounding_target"]["candidate_label"] == "Text A"
    assert forensic_prompt["forensic_grounding_target"]["candidate_text"] == candidate_text
    assert "reread_claims_to_check" in forensic_prompt["forensic_grounding_target"]
    hostile_request = next(
        request
        for request in client.requests
        if request.prompt_contract_id.endswith(".hostile_reader.v1")
    )
    hostile_prompt = json.loads(hostile_request.input_text)
    assert hostile_prompt["hostile_attack_target"]["candidate_label"] == "Text A"
    assert hostile_prompt["hostile_attack_target"]["candidate_text"] == candidate_text
    assert "literary artifact text itself" in hostile_prompt["hostile_reader_instruction"]
    rival_request = next(
        request
        for request in client.requests
        if request.prompt_contract_id.endswith(".rival_comparator.v1")
    )
    assert "source_class" in rival_request.input_text

    model_artifact_types = {schema.artifact_type for schema in INTERNAL_READER_LAB_MODEL_SCHEMAS}
    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        calls = list_model_calls(connection, run_id=result.payload["run_id"])
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert len(calls) == 9
    artifact_by_type = {artifact.type: artifact for artifact in artifacts}
    for artifact_type in model_artifact_types:
        artifact = artifact_by_type[artifact_type]
        envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        assert envelope["schema_version"] == "1"
        assert envelope["artifact_type"] == artifact_type
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is not None
        if artifact_type == AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA.artifact_type:
            assert envelope["created_by"] == "autonomous_internal_reader_lab_v1_controller"
        else:
            assert envelope["created_by"] == "model_driver:openai:stub-internal-reader-model"

    manifest = json.loads(
        Path(artifact_by_type["internal_reader_subject_manifest"].path).read_text(encoding="utf-8")
    )
    packet = json.loads(
        Path(artifact_by_type["internal_reader_lab_packet"].path).read_text(encoding="utf-8")
    )
    assert manifest["fixture_only"] is False
    assert manifest["model_call_id"] is None
    assert packet["fixture_only"] is False
    assert packet["model_call_id"] is None
    assert "fake_mode" not in packet["payload"]
    assert "fake_target_schema" not in packet["payload"]

    rival = read_payload(result.payload["artifact_paths"]["internal_rival_comparison"])
    assert rival["strongest_rival_present"] is True
    assert rival["source_classes_by_label"]["Text D"] == "strongest_rival"

    stream = read_payload(result.payload["artifact_paths"]["internal_stream_reader_trace"])
    reread = read_payload(result.payload["artifact_paths"]["internal_reread_reader_trace"])
    forensic = read_payload(result.payload["artifact_paths"]["forensic_grounding_report"])
    hostile = read_payload(result.payload["artifact_paths"]["hostile_reader_report"])
    diagnosis = read_payload(result.payload["artifact_paths"]["internal_failure_diagnosis"])
    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_candidate_gate_report"])
    assert stream["not_human_data"] is True
    assert reread["not_human_data"] is True
    assert forensic["exact_textual_support"]
    assert all(
        support["source_label"] == "Text A"
        and support["quoted_span"]
        and support["quoted_span"] in candidate_text
        for support in forensic["exact_textual_support"]
    )
    hostile_serialized = json.dumps(hostile, sort_keys=True).lower()
    for phrase in (
        "packet component",
        "the response should",
        "evaluation steps",
        "json",
    ):
        assert phrase not in hostile_serialized
    assert "thesis_replacing_artifact" in diagnosis["failure_types_present"]
    assert "fake fixture mode" not in gate_report["summary_verdict"].lower()
    assert "non-fixture internal model evidence" in gate_report["summary_verdict"]

    assert final_report.refused is True
    combined_blockers = " ".join(final_report.missing_gates + final_report.failed_gates)
    assert "internal_operator_approval" in combined_blockers
    assert "no_unresolved_internal_blockers" in combined_blockers
    assert "real_human_validation_passed" not in combined_blockers
    assert "paper" not in final_report.message.lower()


def test_stubbed_openai_gate_reporter_cannot_choose_finalization_authority(tmp_path):
    config, pilot_payload = build_pilot_packet(tmp_path, with_rival=True)
    clients: list[OverreachingGateReportClient] = []

    def _factory(model: str) -> OverreachingGateReportClient:
        client = OverreachingGateReportClient(
            provider="openai",
            model=model,
            mode="valid",
            target_schema=FORENSIC_GROUNDING_READER_SCHEMA,
        )
        clients.append(client)
        return client

    result = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=pilot_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-internal-reader-model",
        client_factory=_factory,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["counts"]["model_calls"] == 9

    gate_report_path = result.payload["artifact_paths"]["autonomous_candidate_gate_report"]
    gate_envelope = json.loads(Path(gate_report_path).read_text(encoding="utf-8"))
    gate_report = gate_envelope["payload"]
    serialized_report = json.dumps(gate_report, sort_keys=True)

    assert gate_report["profile"] == GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
    assert gate_report["required_gates"] == list(AUTONOMOUS_CREATIVE_CANDIDATE_REQUIRED_GATES)
    assert gate_report["passed"] is False
    assert gate_report["eligible"] is False
    assert gate_report["human_validation_required"] is False
    assert gate_report["paper_validation_required"] is False
    assert gate_report["phase_shift_claim"] is False
    assert gate_report["final_gates_marked_passed"] == []
    assert "paper_public_final" not in serialized_report
    assert "real_human_validation_passed" not in gate_report["final_gates_marked_passed"]
    assert "no_unresolved_internal_blockers" in gate_report["failed_gates"]
    assert "internal_operator_approval" in gate_report["missing_gates"]

    gate_results = {gate["gate_name"]: gate for gate in gate_report["gate_results"]}
    assert gate_results["no_unresolved_internal_blockers"]["passed"] is False
    assert gate_results["internal_operator_approval"]["passed"] is False
    assert gate_results["internal_operator_approval"]["record"] is False

    gate_call = next(
        call
        for call in result.payload["model_calls"]
        if call["schema_name"] == AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA.name
    )
    assert gate_call["status"] == MODEL_CALL_SUCCESS
    assert gate_call["parsed_output_artifact_id"] == result.payload["artifact_ids"][
        "autonomous_candidate_gate_report"
    ]
    assert gate_envelope["model_call_id"] == gate_call["id"]
    assert result.payload["parsed_model_artifact_ids"][
        AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA.name
    ] == result.payload["artifact_ids"]["autonomous_candidate_gate_report"]

    with connect(config.db_path) as connection:
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert final_report.refused is True
    combined_blockers = " ".join(final_report.missing_gates + final_report.failed_gates)
    assert "internal_operator_approval" in combined_blockers
    assert "no_unresolved_internal_blockers" in combined_blockers
    assert "real_human_validation_passed" not in combined_blockers
    assert "paper" not in final_report.message.lower()


def test_stubbed_openai_malformed_gate_commentary_fails_closed(tmp_path):
    config, pilot_payload = build_pilot_packet(tmp_path, with_rival=True)
    clients: list[FakeInternalReaderLabModelClient] = []

    result = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=pilot_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-internal-reader-model",
        client_factory=stub_factory(
            clients,
            mode="malformed",
            target_schema=AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA,
        ),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 9
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == AUTONOMOUS_CANDIDATE_GATE_REPORT_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert "autonomous_candidate_gate_report" not in result.payload["artifact_ids"]
    assert "internal_reader_lab_packet" not in result.payload["artifact_ids"]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])

    reader_lab_types = {
        artifact.type
        for artifact in artifacts
        if artifact.type in INTERNAL_READER_LAB_ARTIFACT_TYPES
    }
    assert "autonomous_candidate_gate_report" not in reader_lab_types
    assert "internal_reader_lab_packet" not in reader_lab_types


def test_stubbed_openai_invalid_forensic_support_span_fails_closed(tmp_path):
    config, pilot_payload = build_pilot_packet(tmp_path, with_rival=True)
    clients: list[BadForensicSupportClient] = []

    def _factory(model: str) -> BadForensicSupportClient:
        client = BadForensicSupportClient(
            provider="openai",
            model=model,
            mode="valid",
            target_schema=FORENSIC_GROUNDING_READER_SCHEMA,
        )
        clients.append(client)
        return client

    result = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=pilot_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-internal-reader-model",
        client_factory=_factory,
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "evidence validation failure" in result.payload["message"]
    assert "quoted_span is not present" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    forensic_call = result.payload["model_calls"][-1]
    assert forensic_call["schema_name"] == FORENSIC_GROUNDING_READER_SCHEMA.name
    assert forensic_call["status"] == MODEL_CALL_SUCCESS
    assert forensic_call["parsed_output_artifact_id"] is None
    assert "forensic_grounding_report" not in result.payload["artifact_ids"]
    assert "hostile_reader_report" not in result.payload["artifact_ids"]
    assert "internal_reader_lab_packet" not in result.payload["artifact_ids"]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])

    reader_lab_types = {
        artifact.type
        for artifact in artifacts
        if artifact.type in INTERNAL_READER_LAB_ARTIFACT_TYPES
    }
    assert reader_lab_types == {
        "internal_reader_subject_manifest",
        "internal_stream_reader_trace",
        "internal_reread_reader_trace",
    }


def test_stubbed_openai_invalid_output_rejects_without_parsed_artifact(tmp_path):
    config, pilot_payload = build_pilot_packet(tmp_path)
    clients: list[FakeInternalReaderLabModelClient] = []

    result = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=pilot_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-internal-reader-model",
        client_factory=stub_factory(clients, mode="invalid"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["counts"]["model_calls"] == 3
    failed_call = result.payload["model_calls"][-1]
    assert failed_call["schema_name"] == FORENSIC_GROUNDING_READER_SCHEMA.name
    assert failed_call["status"] == MODEL_CALL_VALIDATION_FAILED
    assert failed_call["parsed_output_artifact_id"] is None
    assert FORENSIC_GROUNDING_READER_SCHEMA.artifact_type not in result.payload["artifact_ids"]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])

    reader_lab_types = {
        artifact.type
        for artifact in artifacts
        if artifact.type in INTERNAL_READER_LAB_ARTIFACT_TYPES
    }
    assert reader_lab_types == {
        "internal_reader_subject_manifest",
        "internal_stream_reader_trace",
        "internal_reread_reader_trace",
    }


def test_internal_reader_lab_openai_budget_guard_refuses_before_run(tmp_path):
    config, pilot_payload = build_pilot_packet(tmp_path)

    result = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=pilot_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        max_model_calls=8,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "max-model-calls" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
