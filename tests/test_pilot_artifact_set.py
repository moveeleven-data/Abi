import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.cli import main
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.gates import list_gates
from abi.controller.policy import FINAL_ARTIFACT_REQUIRED_GATES, GATE_PROFILE_FINAL_ARTIFACT
from abi.controller.state import get_latest_run
from abi.db import connect
from abi.hashing import sha256_file
from abi.model_calls import MODEL_CALL_SUCCESS, list_model_calls
from abi.model_schemas import (
    PILOT_ABI_CANDIDATE_SCHEMA,
    PILOT_DIRECT_PROMPT_BASELINE_SCHEMA,
    PILOT_RAW_MODEL_BASELINE_SCHEMA,
)
from abi.modules.pilot_artifact_set import (
    PILOT_ARTIFACT_SET_ARTIFACT_TYPES,
    run_pilot_artifact_set,
)


SOURCE_NOTE = """# Source Note

The table remains visible while the night stays withheld.
"""

THEORY_FRAGMENT = """# Theory Fragment

The opening should be testable by reread without telling the reader what to feel.
"""

PROSE_SENTENCES = (
    "At dawn the table kept its place by the window, and everyone who entered the "
    "room noticed the silence before they noticed the wood. "
    "A cup stood near one corner with a faint ring beneath it, as if the night had "
    "lifted its hand but left the pressure behind. "
    "Nothing announced itself, yet the room seemed arranged around a question that "
    "had waited patiently for morning."
)
FORBIDDEN_READER_TERMS = (
    "source_class",
    "abi candidate",
    "direct prompt baseline",
    "raw model baseline",
    "non-final",
    "validation",
    "gate",
    "artifact",
    "metadata",
    "fixture",
    "model_call_id",
)


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


def clean_reader_prose() -> str:
    return " ".join(PROSE_SENTENCES for _ in range(15))


class StubOpenAIPilotClient:
    provider = "openai"

    def __init__(self, model: str, mode: str = "clean") -> None:
        self.model = model
        self.mode = mode

    def generate(self, request) -> str:
        source_context = json.loads(request.input_text)
        source_files = source_context["source_files"]
        source_contents = source_context["source_contents"]
        assert any(SOURCE_NOTE.strip() in item["content"] for item in source_contents)
        assert any(THEORY_FRAGMENT.strip() in item["content"] for item in source_contents)
        hashes = [item["sha256"] for item in source_files]
        if request.schema == PILOT_ABI_CANDIDATE_SCHEMA:
            text = clean_reader_prose()
            if self.mode == "candidate_leakage":
                text = f"{text} BASELINE COMPONENT"
            return json.dumps(
                {
                    "candidate_id": "stub_openai_candidate",
                    "text": text,
                    "source_file_count": len(source_files),
                    "source_set_hashes": hashes,
                    "non_final": True,
                    "candidate_only": True,
                    "not_human_validated": True,
                    "not_finalization_eligible": True,
                    "finalization_eligible": False,
                    "human_validated": False,
                    "human_validation_claim": False,
                    "phase_shift_claim": False,
                    "no_phase_shift_claim": True,
                    "risks": ["stub output is not validation"],
                },
                sort_keys=True,
            )
        if request.schema == PILOT_DIRECT_PROMPT_BASELINE_SCHEMA:
            text = clean_reader_prose()
            if self.mode == "baseline_json":
                text = '{"paragraph":"this is a JSON object, not reader prose"}'
            return json.dumps(
                {
                    "baseline_id": "stub_direct_prompt_baseline",
                    "text": text,
                    "generation_rule": "stubbed OpenAI test client",
                    "risks": ["stub output is not validation"],
                },
                sort_keys=True,
            )
        if request.schema == PILOT_RAW_MODEL_BASELINE_SCHEMA:
            return json.dumps(
                {
                    "baseline_id": "stub_raw_model_baseline",
                    "text": clean_reader_prose(),
                    "risks": ["stub output is not validation"],
                },
                sort_keys=True,
            )
        raise AssertionError(f"unexpected schema: {request.schema}")


def test_fake_pilot_artifact_set_creates_source_frozen_packet(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source_dir = write_sources(tmp_path)
    config = config_for(tmp_path)

    result = run_pilot_artifact_set(
        config,
        client_name="fake",
        source_dir=source_dir,
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "fake"
    assert set(result.payload["artifact_ids"]) == set(PILOT_ARTIFACT_SET_ARTIFACT_TYPES)
    assert result.payload["counts"]["pilot_artifacts"] == 11
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["model_calls"] == []
    assert Path(result.payload["packet_dir"]) == (
        tmp_path / "runs" / result.payload["run_id"] / "pilot_artifact_set" / "packet_0001"
    )

    source_manifest = read_payload(result.payload["artifact_paths"]["pilot_source_manifest"])
    assert source_manifest["source_count"] == 2
    expected_hashes = {
        "source_note.md": sha256_file(source_dir / "source_note.md"),
        "theory_fragment.md": sha256_file(source_dir / "theory_fragment.md"),
    }
    observed_hashes = {
        item["relative_path"]: item["sha256"] for item in source_manifest["source_files"]
    }
    assert observed_hashes == expected_hashes
    assert source_manifest["content_copied_to_docs"] is False

    candidate = read_payload(result.payload["artifact_paths"]["pilot_abi_candidate_ref"])
    assert candidate["non_final"] is True
    assert candidate["not_human_validated"] is True
    assert candidate["not_finalization_eligible"] is True
    assert candidate["finalization_eligible"] is False
    assert candidate["human_validation_claim"] is False
    assert candidate["phase_shift_claim"] is False
    assert candidate["no_phase_shift_claim"] is True

    direct = read_payload(result.payload["artifact_paths"]["pilot_direct_prompt_baseline"])
    raw = read_payload(result.payload["artifact_paths"]["pilot_raw_model_baseline"])
    assert direct["fixture_or_fake"] is True
    assert raw["fixture_or_fake"] is True
    assert raw["raw_model_baseline_gate_satisfied"] is False

    strongest = read_payload(result.payload["artifact_paths"]["pilot_strongest_rival_slot"])
    assert strongest["slot_status"] == "unsatisfied"
    assert strongest["strongest_rival_gate_satisfied"] is False
    assert strongest["final_gate_satisfied"] is False

    label_map = read_payload(result.payload["artifact_paths"]["pilot_neutral_label_map_private"])
    assert label_map["private"] is True
    assert label_map["not_for_reader_distribution"] is True
    assert label_map["label_map"]["Text A"]["source_class"] == "abi_candidate"

    bundle = read_payload(result.payload["artifact_paths"]["pilot_blinded_reader_bundle"])
    assert set(bundle) == {"reader_items"}
    assert [item["label"] for item in bundle["reader_items"]] == ["Text A", "Text B", "Text C"]
    for item in bundle["reader_items"]:
        assert set(item) == {"label", "text"}

    readiness = read_payload(result.payload["artifact_paths"]["pilot_readiness_report"])
    assert readiness["ready_for_protocol_dry_run"] is True
    assert readiness["ready_for_real_human_collection"] is False
    assert readiness["human_data_collected"] is False
    assert readiness["final_gates_marked_passed"] == []
    assert readiness["strongest_rival_gate_satisfied"] is False

    packet = read_payload(result.payload["artifact_paths"]["pilot_packet"])
    assert packet["non_final"] is True
    assert packet["not_human_validated"] is True
    assert packet["not_finalization_eligible"] is True
    assert packet["finalization_eligible"] is False
    assert packet["no_phase_shift_claim"] is True

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        latest_run = get_latest_run(connection)
        gates = list_gates(connection, result.payload["run_id"])
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    assert latest_run.active_phase == "phase16_first_real_candidate_set"
    assert not ({gate.gate_name for gate in gates} & set(FINAL_ARTIFACT_REQUIRED_GATES))
    assert final_report.refused is True
    assert "real_human_validation_passed" in final_report.missing_gates

    pilot_artifacts = {
        artifact.type: artifact
        for artifact in artifacts
        if artifact.type in PILOT_ARTIFACT_SET_ARTIFACT_TYPES
    }
    assert set(pilot_artifacts) == set(PILOT_ARTIFACT_SET_ARTIFACT_TYPES)
    for artifact in pilot_artifacts.values():
        envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        assert envelope["artifact_type"] == artifact.type
        assert envelope["fixture_only"] is True
        assert envelope["model_call_id"] is None
        if artifact.type != "pilot_source_manifest":
            assert artifact.parent_ids
        assert Path(artifact.path).is_relative_to(Path(result.payload["packet_dir"]))


def test_pilot_artifact_set_uses_unique_packet_dirs(tmp_path):
    source_dir = write_sources(tmp_path)
    config = config_for(tmp_path)

    first = run_pilot_artifact_set(config, client_name="fake", source_dir=source_dir)
    second = run_pilot_artifact_set(config, client_name="fake", source_dir=source_dir)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.payload["packet_id"] == "packet_0001"
    assert second.payload["packet_id"] == "packet_0002"
    assert first.payload["packet_dir"] != second.payload["packet_dir"]
    assert set(first.payload["artifact_paths"].values()).isdisjoint(
        set(second.payload["artifact_paths"].values())
    )


def test_openai_pilot_refuses_without_allow_before_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    source_dir = write_sources(tmp_path)
    config = config_for(tmp_path)

    result = run_pilot_artifact_set(config, client_name="openai", source_dir=source_dir)

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert not config.db_path.exists()


def test_openai_pilot_refuses_without_key_before_run(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source_dir = write_sources(tmp_path)
    config = config_for(tmp_path)

    result = run_pilot_artifact_set(
        config,
        client_name="openai",
        source_dir=source_dir,
        allow_live_model=True,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert not config.db_path.exists()


def test_stubbed_openai_pilot_creates_model_records_and_model_artifacts(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    monkeypatch.setenv("ABI_OPENAI_MODEL", "abi-test-model")
    source_dir = write_sources(tmp_path)
    config = config_for(tmp_path)

    result = run_pilot_artifact_set(
        config,
        client_name="openai",
        source_dir=source_dir,
        allow_live_model=True,
        client_factory=lambda model: StubOpenAIPilotClient(model),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "openai"
    assert result.payload["model"] == "abi-test-model"
    assert result.payload["counts"]["model_calls"] == 3
    assert len(result.payload["model_calls"]) == 3
    assert result.payload["readiness"]["baseline_status"] == {
        "direct_prompt_fixture_or_fake": False,
        "raw_model_fixture_or_fake": False,
    }
    assert result.payload["readiness"]["strongest_rival_gate_satisfied"] is False

    with connect(config.db_path) as connection:
        calls = list_model_calls(connection, run_id=result.payload["run_id"])
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    assert len(calls) == 3
    assert {call.status for call in calls} == {MODEL_CALL_SUCCESS}
    assert {call.provider for call in calls} == {"openai"}
    assert {call.model for call in calls} == {"abi-test-model"}
    assert {
        call.parsed_output_artifact_id for call in calls
    } == {
        result.payload["artifact_ids"]["pilot_abi_candidate_ref"],
        result.payload["artifact_ids"]["pilot_direct_prompt_baseline"],
        result.payload["artifact_ids"]["pilot_raw_model_baseline"],
    }

    for artifact_type in (
        "pilot_abi_candidate_ref",
        "pilot_direct_prompt_baseline",
        "pilot_raw_model_baseline",
    ):
        envelope = json.loads(
            Path(result.payload["artifact_paths"][artifact_type]).read_text(encoding="utf-8")
        )
        assert envelope["artifact_type"] == artifact_type
        assert envelope["fixture_only"] is False
        assert envelope["model_call_id"] is not None

    candidate = read_payload(result.payload["artifact_paths"]["pilot_abi_candidate_ref"])
    direct = read_payload(result.payload["artifact_paths"]["pilot_direct_prompt_baseline"])
    raw = read_payload(result.payload["artifact_paths"]["pilot_raw_model_baseline"])
    assert candidate["non_final"] is True
    assert candidate["candidate_only"] is True
    assert candidate["not_human_validated"] is True
    assert candidate["not_finalization_eligible"] is True
    assert candidate["finalization_eligible"] is False
    assert candidate["phase_shift_claim"] is False
    assert direct["baseline_type"] == "direct_prompt"
    assert direct["fixture_or_fake"] is False
    assert direct["not_real_validation"] is True
    assert direct["final_gate_satisfied"] is False
    assert raw["baseline_type"] == "raw_model"
    assert raw["fixture_or_fake"] is False
    assert raw["not_real_validation"] is True
    assert raw["raw_model_baseline_gate_satisfied"] is False

    bundle = read_payload(result.payload["artifact_paths"]["pilot_blinded_reader_bundle"])
    assert set(bundle) == {"reader_items"}
    assert [item["label"] for item in bundle["reader_items"]] == ["Text A", "Text B", "Text C"]
    for item in bundle["reader_items"]:
        assert set(item) == {"label", "text"}
        assert len(item["text"].split()) >= 500
    bundle_text = json.dumps(bundle, sort_keys=True).lower()
    for forbidden in FORBIDDEN_READER_TERMS:
        assert forbidden not in bundle_text

    strongest = read_payload(result.payload["artifact_paths"]["pilot_strongest_rival_slot"])
    assert strongest["strongest_rival_gate_satisfied"] is False
    assert final_report.refused is True
    assert "strongest_rival_comparison_passed" in final_report.missing_gates


def test_stubbed_openai_pilot_fails_closed_on_scaffold_leakage(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    source_dir = write_sources(tmp_path)
    config = config_for(tmp_path)

    result = run_pilot_artifact_set(
        config,
        client_name="openai",
        source_dir=source_dir,
        allow_live_model=True,
        client_factory=lambda model: StubOpenAIPilotClient(model, mode="candidate_leakage"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "reader-facing text validation failed" in result.payload["message"]
    assert "scaffold leakage" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    assert "pilot_blinded_reader_bundle" not in result.payload["artifact_ids"]
    assert "pilot_packet" not in result.payload["artifact_ids"]


def test_stubbed_openai_pilot_fails_closed_on_json_baseline_text(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    source_dir = write_sources(tmp_path)
    config = config_for(tmp_path)

    result = run_pilot_artifact_set(
        config,
        client_name="openai",
        source_dir=source_dir,
        allow_live_model=True,
        client_factory=lambda model: StubOpenAIPilotClient(model, mode="baseline_json"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert "reader-facing text validation failed" in result.payload["message"]
    assert "JSON" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 3
    assert "pilot_blinded_reader_bundle" not in result.payload["artifact_ids"]
    assert "pilot_packet" not in result.payload["artifact_ids"]


def test_pilot_import_rival_rebuilds_reader_bundle_without_mutating_source_packet(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source_dir = write_sources(tmp_path)
    rival_dir = tmp_path / "inputs" / "private" / "pilot_001"
    rival_dir.mkdir(parents=True)
    rival_file = rival_dir / "strongest_rival_text_d.md"
    rival_text = (
        "The cup waited by the window with the first light standing inside it. "
        "Dust held the sill in a thin line, and the room seemed to remember every "
        "touch by refusing to arrange itself into comfort."
    )
    rival_file.write_text(rival_text, encoding="utf-8", newline="\n")
    config = config_for(tmp_path)
    original = run_pilot_artifact_set(config, client_name="fake", source_dir=source_dir)
    original_bundle_path = Path(original.payload["artifact_paths"]["pilot_blinded_reader_bundle"])
    original_packet_path = Path(original.payload["artifact_paths"]["pilot_packet"])
    original_bundle_text = original_bundle_path.read_text(encoding="utf-8")
    original_packet_text = original_packet_path.read_text(encoding="utf-8")

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "pilot",
            "import-rival",
            "--packet-dir",
            str(original.payload["packet_dir"]),
            "--rival-file",
            str(rival_file),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["source_packet_dir"] == original.payload["packet_dir"]
    assert payload["packet_id"] == "packet_0002"
    assert payload["packet_dir"] != original.payload["packet_dir"]
    assert set(payload["new_artifact_ids"]) == {
        "pilot_strongest_rival_import",
        "pilot_strongest_rival_slot",
        "pilot_neutral_label_map_private",
        "pilot_blinded_reader_bundle",
        "pilot_artifact_set_manifest",
        "pilot_readiness_report",
        "pilot_packet",
    }
    assert original_bundle_path.read_text(encoding="utf-8") == original_bundle_text
    assert original_packet_path.read_text(encoding="utf-8") == original_packet_text
    assert not (Path(original.payload["packet_dir"]) / "pilot_strongest_rival_import.json").exists()

    import_envelope = json.loads(
        Path(payload["new_artifact_paths"]["pilot_strongest_rival_import"]).read_text(
            encoding="utf-8"
        )
    )
    assert import_envelope["artifact_type"] == "pilot_strongest_rival_import"
    assert import_envelope["fixture_only"] is False
    assert import_envelope["model_call_id"] is None
    import_payload = import_envelope["payload"]
    assert import_payload["source_class"] == "strongest_rival"
    assert import_payload["non_final"] is True
    assert import_payload["candidate_only"] is False
    assert import_payload["not_finalization_eligible"] is True
    assert import_payload["no_phase_shift_claim"] is True
    assert import_payload["strongest_rival_comparison_passed"] is False

    private_map = read_payload(payload["new_artifact_paths"]["pilot_neutral_label_map_private"])
    assert private_map["private"] is True
    assert private_map["label_map"]["Text A"]["source_class"] == "abi_candidate"
    assert private_map["label_map"]["Text B"]["source_class"] == "direct_prompt_baseline"
    assert private_map["label_map"]["Text C"]["source_class"] == "raw_model_baseline"
    assert private_map["label_map"]["Text D"]["source_class"] == "strongest_rival"
    assert private_map["label_map"]["Text D"]["included_for_readers"] is True

    bundle = read_payload(payload["new_artifact_paths"]["pilot_blinded_reader_bundle"])
    assert set(bundle) == {"reader_items"}
    assert [item["label"] for item in bundle["reader_items"]] == [
        "Text A",
        "Text B",
        "Text C",
        "Text D",
    ]
    assert bundle["reader_items"][3]["text"] == rival_text
    bundle_text = json.dumps(bundle, sort_keys=True).lower()
    for forbidden in ("source_class", "abi_candidate", "direct_prompt_baseline", "raw_model_baseline"):
        assert forbidden not in bundle_text

    slot = read_payload(payload["new_artifact_paths"]["pilot_strongest_rival_slot"])
    assert slot["slot_status"] == "imported"
    assert slot["placeholder_only"] is False
    assert slot["imported_rival_artifact_id"] == payload["new_artifact_ids"][
        "pilot_strongest_rival_import"
    ]
    assert slot["strongest_rival_gate_satisfied"] is False
    assert slot["strongest_rival_comparison_passed"] is False

    manifest = read_payload(payload["new_artifact_paths"]["pilot_artifact_set_manifest"])
    packet = read_payload(payload["new_artifact_paths"]["pilot_packet"])
    for artifact_type in (
        "pilot_blinded_reader_bundle",
        "pilot_neutral_label_map_private",
        "pilot_readiness_report",
        "pilot_strongest_rival_import",
        "pilot_strongest_rival_slot",
    ):
        assert manifest["artifact_ids"][artifact_type] == packet["artifact_ids"][artifact_type]
        assert manifest["artifact_ids"][artifact_type] == payload["new_artifact_ids"][artifact_type]
    assert packet["artifact_ids"]["pilot_artifact_set_manifest"] == payload["new_artifact_ids"][
        "pilot_artifact_set_manifest"
    ]
    assert manifest["artifact_ids"]["pilot_abi_candidate_ref"] == original.payload["artifact_ids"][
        "pilot_abi_candidate_ref"
    ]

    kit_dir = tmp_path / "inputs" / "private" / "pilot_001" / "reader_kit"
    export_exit = main(
        [
            "--root",
            str(tmp_path),
            "pilot",
            "export-reader-kit",
            "--packet-dir",
            payload["packet_dir"],
            "--out-dir",
            str(kit_dir),
            "--reader-count",
            "6",
        ]
    )
    export_payload = json.loads(capsys.readouterr().out)

    assert export_exit == 0
    assert export_payload["accepted"] is True
    assert export_payload["out_dir"] == str(kit_dir.resolve())
    assert len(export_payload["reader_bundle_files"]) == 6
    assert export_payload["order_is_counterbalanced"] is True
    response_template = Path(export_payload["response_form_template"])
    assert response_template.exists()
    assert "First Read" in response_template.read_text(encoding="utf-8")
    forbidden_reader_terms = (
        "source_class",
        "abi_candidate",
        "direct_prompt_baseline",
        "raw_model_baseline",
        "strongest_rival",
    )
    for reader_file in export_payload["reader_bundle_files"]:
        text = Path(reader_file).read_text(encoding="utf-8")
        assert "Text A" in text or "Text B" in text or "Text C" in text or "Text D" in text
        lowered = text.lower()
        for forbidden in forbidden_reader_terms:
            assert forbidden not in lowered

    schedule = json.loads(Path(export_payload["order_schedule_private"]).read_text(encoding="utf-8"))
    assert schedule["private"] is True
    assert schedule["not_for_reader_distribution"] is True
    source_classes = {
        item["source_class"]
        for reader in schedule["readers"]
        for item in reader["presentation_order"]
    }
    assert source_classes == {
        "abi_candidate",
        "direct_prompt_baseline",
        "raw_model_baseline",
        "strongest_rival",
    }
    orders = [
        tuple(item["label"] for item in reader["presentation_order"])
        for reader in schedule["readers"]
    ]
    assert len(set(orders)) > 1

    with connect(config.db_path) as connection:
        gates = list_gates(connection, payload["run_id"])
        final_report = check_finalization(
            connection,
            run_id=payload["run_id"],
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    assert not ({gate.gate_name for gate in gates} & set(FINAL_ARTIFACT_REQUIRED_GATES))
    assert final_report.refused is True
    assert "strongest_rival_comparison_passed" in final_report.missing_gates


def test_pilot_cli_fake_and_openai_guard(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source_dir = write_sources(tmp_path)

    fake_exit = main(
        [
            "--root",
            str(tmp_path),
            "pilot",
            "artifact-set",
            "--client",
            "fake",
            "--source-dir",
            str(source_dir),
        ]
    )
    fake_payload = json.loads(capsys.readouterr().out)

    assert fake_exit == 0
    assert fake_payload["client"] == "fake"
    assert set(fake_payload["artifact_ids"]) == set(PILOT_ARTIFACT_SET_ARTIFACT_TYPES)

    openai_exit = main(
        [
            "--root",
            str(tmp_path),
            "pilot",
            "artifact-set",
            "--client",
            "openai",
            "--source-dir",
            str(source_dir),
        ]
    )
    openai_payload = json.loads(capsys.readouterr().out)

    assert openai_exit == 1
    assert openai_payload["refused"] is True
    assert "--allow-live-model" in openai_payload["message"]


def test_private_source_directory_is_gitignored_and_readme_documents_command():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "inputs/private/" in gitignore
    assert (
        r".\.venv\Scripts\abi.exe pilot artifact-set --client fake "
        r"--source-dir fixtures/production_harness"
    ) in readme
