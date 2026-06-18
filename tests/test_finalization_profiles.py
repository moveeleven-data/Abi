import json
from pathlib import Path

from abi.cli import main
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.gates import record_gate
from abi.controller.policy import (
    FINAL_ARTIFACT_REQUIRED_GATES,
    GATE_PROFILE_CANDIDATE_RELEASE,
    GATE_PROFILE_FINAL_ARTIFACT,
    GATE_PROFILE_INFRASTRUCTURE,
    gate_catalog_to_dict,
)
from abi.controller.release_readiness import evaluate_release_readiness
from abi.controller.state import ensure_active_run
from abi.db import connect
from abi.modules.evaluation import run_evaluation_demo
from abi.packets import PacketWriter


SOURCE_NOTE = """# Source Note

The table is the ordinary object the production scaffold must keep visible.
"""

THEORY_FRAGMENT = """# Theory Fragment

Reread pressure should remain inspectable through lineage.
"""

PROTOCOL = """# Fixture Human Calibration Protocol

This is fixture-only protocol material and not real validation.
"""

TRIAL = {
    "fixture_only": True,
    "not_real_validation": True,
    "trial_id": "fixture_trial_001",
    "reader_label": "fixture_reader_alpha",
    "artifact_label": "table_morning_fixture",
    "first_read": {
        "opening_interpretation": "A domestic object remained in place.",
        "retained_images": ["table", "morning"],
        "predictions": ["the room may matter"],
        "attention_drops": [],
        "confusion": [],
        "overexplicitness": [],
    },
    "reread": {
        "post_ending_opening_reread": "The table now reads as evidence.",
        "changed_interpretation": "Still becomes pressure.",
        "paraphrase_attempt": "The room has been tested.",
        "details_that_gained_force": ["table"],
        "details_that_felt_fake": [],
    },
}

BASELINE = """# Fixture Baseline Direct Prompt

This fixture baseline is not real validation.
"""


def config_for(tmp_path: Path) -> AbiConfig:
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def write_fixtures(root: Path) -> None:
    production_dir = root / "fixtures" / "production_harness"
    production_dir.mkdir(parents=True, exist_ok=True)
    (production_dir / "source_note.md").write_text(SOURCE_NOTE, encoding="utf-8", newline="\n")
    (production_dir / "theory_fragment.md").write_text(
        THEORY_FRAGMENT,
        encoding="utf-8",
        newline="\n",
    )

    calibration_dir = root / "fixtures" / "human_calibration"
    calibration_dir.mkdir(parents=True, exist_ok=True)
    (calibration_dir / "protocol.md").write_text(PROTOCOL, encoding="utf-8", newline="\n")
    (calibration_dir / "human_reader_trial.json").write_text(
        json.dumps(TRIAL, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (calibration_dir / "baseline_direct_prompt.md").write_text(
        BASELINE,
        encoding="utf-8",
        newline="\n",
    )


def test_gate_catalog_exposes_required_profiles() -> None:
    catalog = gate_catalog_to_dict()

    assert set(catalog["profiles"]) == {
        GATE_PROFILE_INFRASTRUCTURE,
        GATE_PROFILE_CANDIDATE_RELEASE,
        GATE_PROFILE_FINAL_ARTIFACT,
    }
    final_profile = catalog["profiles"][GATE_PROFILE_FINAL_ARTIFACT]
    assert final_profile["required_gates"] == list(FINAL_ARTIFACT_REQUIRED_GATES)
    gate_names = {gate["name"] for gate in catalog["gates"]}
    assert "real_human_validation_passed" in gate_names
    assert "hostile_final_audit_passed" in gate_names
    assert "final_operator_approval" in gate_names


def test_gate_list_and_finalization_status_cli_emit_json(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "init"]) == 0
    capsys.readouterr()

    assert main(["--root", str(tmp_path), "gate", "list"]) == 0
    gate_payload = json.loads(capsys.readouterr().out)
    assert GATE_PROFILE_FINAL_ARTIFACT in gate_payload["profiles"]

    assert main(["--root", str(tmp_path), "finalization", "status"]) == 0
    default_payload = json.loads(capsys.readouterr().out)
    assert default_payload["profile"] == GATE_PROFILE_INFRASTRUCTURE
    assert default_payload["eligible"] is False
    assert "infrastructure_initialized" in default_payload["missing_gates"]

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "finalization",
                "status",
                "--profile",
                "final_artifact",
            ]
        )
        == 0
    )
    final_payload = json.loads(capsys.readouterr().out)
    assert final_payload["profile"] == GATE_PROFILE_FINAL_ARTIFACT
    assert final_payload["eligible"] is False
    assert "final_artifact_packet_exists" in final_payload["missing_gates"]


def test_final_artifact_profile_refuses_fixture_candidate_state(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_fixtures(tmp_path)
    config = config_for(tmp_path)
    result = run_evaluation_demo(config, client_name="fake")

    with connect(config.db_path) as connection:
        readiness = evaluate_release_readiness(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )
        report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    assert readiness.eligible is False
    assert report.refused is True
    assert "final_artifact_packet_exists" in readiness.missing_gates
    assert "real_human_validation_passed" in readiness.missing_gates
    assert "strongest_rival_comparison_passed" in readiness.missing_gates
    assert "raw_model_baseline_comparison_passed" in readiness.missing_gates
    assert "hostile_final_audit_passed" in readiness.missing_gates
    assert "final_operator_approval" in readiness.missing_gates
    assert any("no final artifact packet" in blocker for blocker in readiness.artifact_blockers)
    assert any("non-final" in blocker for blocker in readiness.non_final_blockers)
    assert any("fixture" in blocker for blocker in readiness.fixture_only_blockers)
    assert "Finalization refused for profile final_artifact" in report.message


def test_fixture_evidence_blocks_final_profile_even_with_required_gates(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_fixtures(tmp_path)
    config = config_for(tmp_path)
    result = run_evaluation_demo(config, client_name="fake")

    with connect(config.db_path) as connection:
        _write_controlled_final_artifact(connection, config, result.payload["run_id"])
        for gate_name in FINAL_ARTIFACT_REQUIRED_GATES:
            record_gate(
                connection,
                run_id=result.payload["run_id"],
                gate_name=gate_name,
                passed=True,
            )
        readiness = evaluate_release_readiness(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    assert readiness.missing_gates == []
    assert readiness.failed_gates == []
    assert readiness.eligible is False
    assert readiness.fixture_only_blockers


def test_controlled_final_artifact_profile_can_become_eligible(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)

    with connect(config.db_path) as connection:
        _write_controlled_final_artifact(connection, config, run.id)
        for gate_name in FINAL_ARTIFACT_REQUIRED_GATES:
            record_gate(connection, run_id=run.id, gate_name=gate_name, passed=True)
        readiness = evaluate_release_readiness(
            connection,
            run_id=run.id,
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )
        report = check_finalization(
            connection,
            run_id=run.id,
            profile=GATE_PROFILE_FINAL_ARTIFACT,
        )

    assert readiness.eligible is True
    assert readiness.fixture_only_blockers == []
    assert readiness.non_final_blockers == []
    assert readiness.artifact_blockers == []
    assert readiness.recommended_next_action == "finalize"
    assert report.refused is False


def test_cli_finalize_final_artifact_profile_refuses_current_state(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ABI_DB_PATH", raising=False)
    monkeypatch.delenv("ABI_RUNS_DIR", raising=False)
    monkeypatch.delenv("ABI_OUTPUTS_DIR", raising=False)

    assert main(["--root", str(tmp_path), "init"]) == 0
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "finalize", "--profile", "final_artifact"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["refused"] is True
    assert payload["profile"] == GATE_PROFILE_FINAL_ARTIFACT
    assert "final_artifact_packet_exists" in payload["missing_gates"]
    assert any("no final artifact packet" in blocker for blocker in payload["artifact_blockers"])


def _write_controlled_final_artifact(
    connection,
    config: AbiConfig,
    run_id: str,
) -> None:
    packet_dir = config.run_dir(run_id) / "final_artifact" / "packet_0001"
    writer = PacketWriter(
        connection=connection,
        run_id=run_id,
        packet_dir=packet_dir,
        lineage_id="controlled_final_artifact",
        created_by="test_finalization_profile_v2",
        fixture_only=False,
        model_call_id=None,
    )
    writer.write_artifact(
        "final_artifact_packet",
        {
            "worker": "controlled_final_artifact_fixture_for_policy_test",
            "final_artifact_id": "controlled_final_artifact_v1",
            "fixture_only": False,
            "non_final": False,
            "candidate_only": False,
            "not_finalization_eligible": False,
            "finalization_eligible": True,
            "human_validated": False,
            "human_validation_claim": False,
            "phase_shift_claim": False,
            "controlled_policy_test_only": True,
        },
        parent_ids=[],
    )
