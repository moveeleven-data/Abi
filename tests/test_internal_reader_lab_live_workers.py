import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.policy import GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
from abi.db import connect
from abi.model_calls import MODEL_CALL_SUCCESS, MODEL_CALL_VALIDATION_FAILED, list_model_calls
from abi.model_schemas import (
    FORENSIC_GROUNDING_READER_SCHEMA,
    INTERNAL_READER_LAB_MODEL_SCHEMAS,
    json_schema_for_worker_schema,
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
):
    def _factory(model: str) -> FakeInternalReaderLabModelClient:
        client = FakeInternalReaderLabModelClient(
            provider="openai",
            model=model,
            mode=mode,
            target_schema=FORENSIC_GROUNDING_READER_SCHEMA,
        )
        clients.append(client)
        return client

    return _factory


def test_internal_reader_lab_schema_catalog_exposes_internal_worker_schemas():
    for schema in INTERNAL_READER_LAB_MODEL_SCHEMAS:
        exposed = json_schema_for_worker_schema(schema)
        assert exposed["type"] == "object"
        assert exposed["required"]


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

    rival = read_payload(result.payload["artifact_paths"]["internal_rival_comparison"])
    assert rival["strongest_rival_present"] is True
    assert rival["source_classes_by_label"]["Text D"] == "strongest_rival"

    stream = read_payload(result.payload["artifact_paths"]["internal_stream_reader_trace"])
    reread = read_payload(result.payload["artifact_paths"]["internal_reread_reader_trace"])
    assert stream["not_human_data"] is True
    assert reread["not_human_data"] is True

    assert final_report.refused is True
    combined_blockers = " ".join(final_report.missing_gates + final_report.failed_gates)
    assert "internal_operator_approval" in combined_blockers
    assert "no_unresolved_internal_blockers" in combined_blockers
    assert "real_human_validation_passed" not in combined_blockers
    assert "paper" not in final_report.message.lower()


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
