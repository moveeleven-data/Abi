import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.policy import GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
from abi.controller.state import AUTONOMOUS_INTERNAL_READER_LAB_ACTIVE_PHASE, get_latest_run
from abi.db import connect
from abi.modules.internal_reader_lab import (
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


def build_pilot_packet(tmp_path: Path) -> tuple[AbiConfig, dict[str, object]]:
    config = config_for(tmp_path)
    source_dir = write_sources(tmp_path)
    pilot = run_pilot_artifact_set(
        config,
        client_name="fake",
        source_dir=source_dir,
    )
    assert pilot.exit_code == 0
    return config, pilot.payload


def test_internal_reader_lab_fake_creates_required_artifacts(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config, pilot_payload = build_pilot_packet(tmp_path)

    result = run_internal_reader_lab(
        config,
        client_name="fake",
        packet_dir=pilot_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "fake"
    assert set(result.payload["artifact_ids"]) == set(INTERNAL_READER_LAB_ARTIFACT_TYPES)
    assert result.payload["counts"] == {
        "internal_reader_lab_artifacts": 11,
        "required_internal_reader_lab_artifacts": 11,
        "model_calls": 0,
        "recorded_autonomous_gates": 12,
    }
    assert Path(result.payload["packet_dir"]) == (
        tmp_path
        / "runs"
        / result.payload["run_id"]
        / "internal_reader_lab"
        / "packet_0001"
    )

    stream = read_payload(result.payload["artifact_paths"]["internal_stream_reader_trace"])
    assert stream["retained_images"]
    assert stream["dropped_details"]
    assert stream["live_motifs"]
    assert stream["attention_points"]
    assert "first_read_opening_interpretation" in stream
    assert "first_read_summary" in stream

    reread = read_payload(result.payload["artifact_paths"]["internal_reread_reader_trace"])
    assert reread["opening_changed"] is True
    assert reread["opening_words_images_changed"]
    assert reread["hidden_consequence_clearer"]
    assert reread["motif_returned_changed"]
    assert reread["reread_gain_estimate"]["not_human_score"] is True

    forensic = read_payload(result.payload["artifact_paths"]["forensic_grounding_report"])
    assert forensic["claimed_effects"]
    assert forensic["exact_textual_support"]
    assert "unsupported_claims" in forensic
    assert "fake_depth_risk" in forensic
    assert "reread_claims_grounded" in forensic

    hostile = read_payload(result.payload["artifact_paths"]["hostile_reader_report"])
    risk_types = {attack["risk_type"] for attack in hostile["attacks"]}
    assert {
        "fake_depth",
        "overexplanation",
        "scaffold_leakage",
        "wrong_register",
        "accidental_comedy",
        "cliche_contamination",
        "thesis_replacing_artifact",
        "pasted_ending",
        "unearned_cosmic_scale",
    } <= risk_types

    rival = read_payload(result.payload["artifact_paths"]["internal_rival_comparison"])
    assert rival["rival_preservation_remains_required"] is True
    assert "abi_candidate_loses_where" in rival
    assert "abi_candidate_wins_where" in rival

    diagnosis = read_payload(result.payload["artifact_paths"]["internal_failure_diagnosis"])
    assert {
        "underplanted",
        "paraphrase_capture",
        "rival_stronger_local_embodiment",
        "cadence_or_register_damage",
    } <= set(diagnosis["failure_types_present"])

    plan = read_payload(result.payload["artifact_paths"]["targeted_recomposition_plan"])
    assert plan["bounded"] is True
    assert plan["does_not_rewrite_artifact"] is True
    assert plan["plan_items"]
    assert all("do not rewrite the whole artifact" in item["forbidden_changes"] for item in plan["plan_items"])

    ablation = read_payload(result.payload["artifact_paths"]["counterfactual_ablation_plan"])
    assert ablation["lightweight_plan_only"] is True
    assert ablation["ablation_tests"]

    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_candidate_gate_report"])
    assert gate_report["eligible"] is False
    assert gate_report["human_validation_required"] is False
    assert gate_report["paper_validation_required"] is False
    assert gate_report["phase_shift_claim"] is False
    assert "no_fixture_only_core_evidence" in gate_report["failed_gates"]
    assert "internal_operator_approval" in gate_report["missing_gates"]

    with connect(config.db_path) as connection:
        artifacts = list_artifacts(connection, result.payload["run_id"])
        latest_run = get_latest_run(connection)
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )

    assert latest_run.active_phase == AUTONOMOUS_INTERNAL_READER_LAB_ACTIVE_PHASE
    internal_artifacts = {
        artifact.type: artifact
        for artifact in artifacts
        if artifact.type in INTERNAL_READER_LAB_ARTIFACT_TYPES
    }
    assert set(internal_artifacts) == set(INTERNAL_READER_LAB_ARTIFACT_TYPES)
    for artifact in internal_artifacts.values():
        envelope = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        assert envelope["schema_version"] == "1"
        assert envelope["artifact_type"] == artifact.type
        assert envelope["fixture_only"] is True
        assert envelope["model_call_id"] is None
        assert Path(artifact.path).is_relative_to(Path(result.payload["packet_dir"]))

    assert final_report.refused is True
    combined_blockers = " ".join(final_report.missing_gates + final_report.failed_gates)
    assert "real_human_validation_passed" not in combined_blockers
    assert "paper" not in final_report.message.lower()


def test_internal_reader_lab_packet_directory_is_unique(tmp_path):
    config, pilot_payload = build_pilot_packet(tmp_path)

    first = run_internal_reader_lab(config, client_name="fake", packet_dir=pilot_payload["packet_dir"])
    second = run_internal_reader_lab(config, client_name="fake", packet_dir=pilot_payload["packet_dir"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.payload["packet_id"] == "packet_0001"
    assert second.payload["packet_id"] == "packet_0002"
    assert first.payload["packet_dir"] != second.payload["packet_dir"]
    assert set(first.payload["artifact_paths"].values()).isdisjoint(
        set(second.payload["artifact_paths"].values())
    )


def test_internal_reader_lab_preserves_imported_strongest_rival_pressure(tmp_path):
    config, pilot_payload = build_pilot_packet(tmp_path)
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
        packet_dir=pilot_payload["packet_dir"],
        rival_file=rival_file,
    )
    assert imported.exit_code == 0

    result = run_internal_reader_lab(
        config,
        client_name="fake",
        packet_dir=imported.payload["packet_dir"],
    )

    comparison = read_payload(result.payload["artifact_paths"]["internal_rival_comparison"])
    gate_report = read_payload(result.payload["artifact_paths"]["autonomous_candidate_gate_report"])

    assert comparison["strongest_rival_present"] is True
    assert comparison["rival_preservation_remains_required"] is True
    rival_gate = {
        gate["gate_name"]: gate for gate in gate_report["gate_results"]
    }["rival_preservation_present"]
    assert rival_gate["passed"] is True
    assert "internal_operator_approval" in gate_report["missing_gates"]


def test_internal_reader_lab_openai_refuses_without_allow(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    config, pilot_payload = build_pilot_packet(tmp_path)

    result = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=pilot_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "--allow-live-model" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0


def test_internal_reader_lab_openai_refuses_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config, pilot_payload = build_pilot_packet(tmp_path)

    result = run_internal_reader_lab(
        config,
        client_name="openai",
        packet_dir=pilot_payload["packet_dir"],
        allow_live_model=True,
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "OPENAI_API_KEY" in result.payload["message"]
    assert result.payload["counts"]["model_calls"] == 0
