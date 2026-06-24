import json
from pathlib import Path

from abi.artifacts import list_artifacts
from abi.config import AbiConfig
from abi.controller.finalization import check_finalization
from abi.controller.policy import GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE
from abi.controller.state import (
    AUTONOMOUS_INTERNAL_READER_STATE_EVALUATION_ACTIVE_PHASE,
    get_latest_run,
)
from abi.db import connect
from abi.model_calls import MODEL_CALL_SUCCESS, MODEL_CALL_VALIDATION_FAILED, list_model_calls
from abi.model_schemas import INTERNAL_STREAM_READER_SCHEMA
from abi.modules.autonomous_evidence_synthesis import run_autonomous_evidence_synthesis
from abi.modules.internal_reader_lab import FakeInternalReaderLabModelClient
from abi.modules.internal_reader_state_evaluation import (
    INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES,
    run_internal_reader_state_evaluation,
)
from test_autonomous_revision import (
    build_fake_macro_evidence_synthesis_chain,
    read_payload,
)


def build_macro_synthesis_packet(
    tmp_path: Path,
) -> tuple[AbiConfig, dict[str, object], dict[str, object], dict[str, object]]:
    config, _failed_ablation, _pivot_revision, macro_payload, macro_ablation_payload = (
        build_fake_macro_evidence_synthesis_chain(tmp_path)
    )
    with connect(config.db_path) as connection:
        run_id = get_latest_run(connection).id
    synthesis = run_autonomous_evidence_synthesis(config, run_id=run_id)
    assert synthesis.exit_code == 0
    assert synthesis.payload["accepted"] is True
    return config, synthesis.payload, macro_payload, macro_ablation_payload


def read_envelope(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stub_reader_state_factory(clients: list[FakeInternalReaderLabModelClient], *, mode="valid"):
    def _factory(model: str) -> FakeInternalReaderLabModelClient:
        client = FakeInternalReaderLabModelClient(
            provider="openai",
            model=model,
            mode=mode,
            target_schema=INTERNAL_STREAM_READER_SCHEMA,
        )
        clients.append(client)
        return client

    return _factory


def test_internal_reader_state_eval_fake_creates_fail_closed_packet(tmp_path):
    config, synthesis_payload, macro_payload, macro_ablation_payload = build_macro_synthesis_packet(
        tmp_path
    )

    result = run_internal_reader_state_evaluation(
        config,
        client_name="fake",
        synthesis_packet=synthesis_payload["packet_dir"],
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["client"] == "fake"
    assert result.payload["selected_candidate_packet_id"] == macro_payload["packet_id"]
    assert result.payload["strongest_rival_present"] is True
    assert result.payload["counts"]["internal_reader_state_eval_artifacts"] == len(
        INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES
    )
    assert result.payload["counts"]["required_internal_reader_state_eval_artifacts"] == len(
        INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES
    )
    assert result.payload["counts"]["produced_artifacts"] == len(
        INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES
    )
    assert result.payload["counts"]["required_artifacts"] == len(
        INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES
    )
    assert result.payload["counts"]["model_calls"] == 0
    assert result.payload["counts"]["recorded_gates"] == 12
    assert set(result.payload["artifact_ids"]) == set(INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES)

    packet_dir = Path(str(result.payload["packet_dir"]))
    for artifact_type in INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES:
        assert (packet_dir / f"{artifact_type}.json").exists()

    subject = read_payload(packet_dir / "internal_reader_state_eval_subject_manifest.json")
    assert subject["selected_candidate_packet_id"] == macro_payload["packet_id"]
    assert subject["macro_ablation_packet_id"] == macro_ablation_payload["packet_id"]
    assert subject["strongest_rival_present"] is True

    selected = read_payload(packet_dir / "selected_candidate_reader_subject.json")
    assert selected["selected_macro_candidate"]["packet_id"] == macro_payload["packet_id"]
    assert selected["selected_macro_candidate"]["non_final"] is True
    assert selected["strongest_rival"]["comparison_gate_satisfied"] is False

    rival = read_payload(packet_dir / "rival_reader_state_comparison.json")
    assert rival["strongest_rival_still_blocks"] is True
    assert rival["strongest_rival_comparison_passed"] is False

    gate = read_payload(packet_dir / "internal_reader_state_eval_gate_report.json")
    assert gate["passed"] is False
    assert gate["finalization_eligible"] is False
    assert gate["no_phase_shift_claim"] is True
    assert "no_unresolved_internal_blockers" in gate["failed_gates"]

    packet = read_payload(packet_dir / "internal_reader_state_eval_packet.json")
    assert packet["macro_ablation_packet_id"] == macro_ablation_payload["packet_id"]
    assert packet["rival_comparison"]["strongest_rival_comparison_passed"] is False
    assert packet["not_human_validated"] is True

    with connect(config.db_path) as connection:
        run = get_latest_run(connection)
        final_report = check_finalization(
            connection,
            run_id=run.id,
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert run.active_phase == AUTONOMOUS_INTERNAL_READER_STATE_EVALUATION_ACTIVE_PHASE
    assert final_report.refused is True


def test_internal_reader_state_eval_refuses_invalid_synthesis_packet(tmp_path):
    config, synthesis_payload, _macro_payload, _macro_ablation_payload = (
        build_macro_synthesis_packet(tmp_path)
    )
    packet_path = (
        Path(str(synthesis_payload["packet_dir"])) / "autonomous_evidence_synthesis_packet.json"
    )
    envelope = read_envelope(packet_path)
    del envelope["payload"]["artifact_ids"]["best_current_candidate_selection"]
    packet_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_internal_reader_state_evaluation(
        config,
        client_name="fake",
        synthesis_packet=synthesis_payload["packet_dir"],
    )

    assert result.exit_code == 1
    assert result.payload["refused"] is True
    assert "best_current_candidate_selection" in result.payload["message"]
    assert result.payload["artifact_ids"] == {}


def test_internal_reader_state_eval_openai_guards_refuse_before_model_calls(
    tmp_path,
    monkeypatch,
):
    config, synthesis_payload, _macro_payload, _macro_ablation_payload = (
        build_macro_synthesis_packet(tmp_path)
    )
    called = False

    def _forbidden_factory(model: str):
        nonlocal called
        called = True
        raise AssertionError(f"client factory should not run for {model}")

    with connect(config.db_path) as connection:
        before_calls = list_model_calls(connection)

    missing_allow = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=synthesis_payload["packet_dir"],
        api_key="stub-key",
        client_factory=_forbidden_factory,
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    missing_key = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=synthesis_payload["packet_dir"],
        allow_live_model=True,
        client_factory=_forbidden_factory,
    )

    with connect(config.db_path) as connection:
        after_calls = list_model_calls(connection)

    assert called is False
    assert missing_allow.exit_code == 1
    assert "--allow-live-model" in missing_allow.payload["message"]
    assert missing_key.exit_code == 1
    assert "OPENAI_API_KEY" in missing_key.payload["message"]
    assert len(after_calls) == len(before_calls)


def test_internal_reader_state_eval_stubbed_openai_creates_model_backed_packet(tmp_path):
    config, synthesis_payload, macro_payload, _macro_ablation_payload = build_macro_synthesis_packet(
        tmp_path
    )
    clients: list[FakeInternalReaderLabModelClient] = []

    result = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=synthesis_payload["packet_dir"],
        allow_live_model=True,
        max_model_calls=8,
        api_key="stub-key",
        model="stub-reader-state-model",
        client_factory=stub_reader_state_factory(clients),
    )

    assert result.exit_code == 0
    assert result.payload["accepted"] is True
    assert result.payload["selected_candidate_packet_id"] == macro_payload["packet_id"]
    assert result.payload["counts"]["model_calls"] == 5
    assert len(result.payload["model_call_ids"]) == 5
    assert len(clients) == 1
    assert len(clients[0].requests) == 5

    with connect(config.db_path) as connection:
        model_calls = list_model_calls(connection)
    new_calls = [call for call in model_calls if call.id in result.payload["model_call_ids"]]
    assert len(new_calls) == 5
    assert {call.status for call in new_calls} == {MODEL_CALL_SUCCESS}
    assert {call.provider for call in new_calls} == {"openai"}
    assert {call.model for call in new_calls} == {"stub-reader-state-model"}

    model_backed_types = {
        "first_pass_reader_state_trace",
        "reread_reader_state_trace",
        "rival_reader_state_comparison",
        "hostile_reader_state_report",
        "forensic_grounding_reader_report",
    }
    for artifact_type in model_backed_types:
        envelope = read_envelope(result.payload["artifact_paths"][artifact_type])
        assert envelope["model_call_id"] in result.payload["model_call_ids"]
        assert envelope["fixture_only"] is False
        assert envelope["payload"]["fixture_only"] is False


def test_internal_reader_state_eval_validation_failure_registers_no_packet_artifacts(tmp_path):
    config, synthesis_payload, _macro_payload, _macro_ablation_payload = (
        build_macro_synthesis_packet(tmp_path)
    )

    result = run_internal_reader_state_evaluation(
        config,
        client_name="openai",
        synthesis_packet=synthesis_payload["packet_dir"],
        allow_live_model=True,
        api_key="stub-key",
        model="stub-reader-state-model",
        client_factory=stub_reader_state_factory([], mode="invalid"),
    )

    assert result.exit_code == 1
    assert result.payload["accepted"] is False
    assert result.payload["artifact_ids"] == {}
    assert len(result.payload["model_call_ids"]) == 1
    assert result.payload["model_calls"][0]["status"] == MODEL_CALL_VALIDATION_FAILED

    with connect(config.db_path) as connection:
        eval_artifacts = [
            artifact
            for artifact in list_artifacts(connection, result.payload["run_id"])
            if artifact.type in INTERNAL_READER_STATE_EVAL_ARTIFACT_TYPES
        ]
        final_report = check_finalization(
            connection,
            run_id=result.payload["run_id"],
            profile=GATE_PROFILE_AUTONOMOUS_CREATIVE_CANDIDATE,
        )
    assert eval_artifacts == []
    assert final_report.refused is True
