import json

from abi.config import AbiConfig
from abi.controller.state import ensure_active_run
from abi.db import connect
from abi.packets import PacketWriter, create_packet_dir, packet_artifact_count_summary


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_create_packet_dir_uses_next_available_directory(tmp_path):
    base_dir = tmp_path / "runs" / "run_1" / "module"
    (base_dir / "packet_0001").mkdir(parents=True)

    first = create_packet_dir(base_dir)
    first.mkdir()
    second = create_packet_dir(base_dir)

    assert first.name == "packet_0002"
    assert second.name == "packet_0003"


def test_packet_writer_writes_normalized_envelope_and_registers_artifact(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)
    packet_dir = create_packet_dir(config.run_dir(run.id) / "packet_writer")
    payload = {"field": "value"}

    with connect(config.db_path) as connection:
        writer = PacketWriter(
            connection=connection,
            run_id=run.id,
            packet_dir=packet_dir,
            lineage_id="lineage_packet_test",
            created_by="packet_writer_test",
            fixture_only=True,
        )
        parent = writer.write_artifact("packet_parent", {"parent": True})
        artifact = writer.write_artifact("packet_child", payload, parent_ids=[parent.id])

    path = packet_dir / "packet_child.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))

    assert artifact.id.startswith("artifact_")
    assert artifact.path == str(path)
    assert artifact.parent_ids == [parent.id]
    assert envelope == {
        "schema_version": "1",
        "artifact_type": "packet_child",
        "run_id": run.id,
        "lineage_id": "lineage_packet_test",
        "parent_ids": [parent.id],
        "created_by": "packet_writer_test",
        "fixture_only": True,
        "model_call_id": None,
        "payload": payload,
    }


def test_packet_artifact_count_summary_includes_packet_self_artifact():
    summary = packet_artifact_count_summary(
        required_artifact_types=("a", "b", "packet"),
        produced_artifact_types=("a", "b"),
        packet_artifact_type="packet",
    )

    assert summary["required_artifacts"] == 3
    assert summary["produced_artifacts"] == 3
    assert summary["packet_artifact_type"] == "packet"
    assert summary["packet_artifact_included_in_counts"] is True
    assert summary["packet_artifact_present"] is True
    assert summary["missing_artifact_types"] == []
    assert summary["artifact_count_consistent"] is True
