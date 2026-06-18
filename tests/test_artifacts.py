import json

import pytest

from abi.artifacts import get_artifact, list_artifacts, register_artifact
from abi.config import AbiConfig
from abi.controller.state import ensure_active_run
from abi.db import connect
from abi.hashing import sha256_bytes


def config_for(tmp_path):
    return AbiConfig(
        root=tmp_path,
        db_path=tmp_path / "db" / "abi.sqlite",
        runs_dir=tmp_path / "runs",
        outputs_dir=tmp_path / "outputs",
    )


def test_register_artifact_stores_hash_and_parent_ids(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)
    artifact_path = config.output_dir(run.id) / "artifact.txt"
    artifact_path.write_bytes(b"phase zero artifact\n")

    with connect(config.db_path) as connection:
        artifact = register_artifact(
            connection,
            run_id=run.id,
            artifact_type="phase0_fixture",
            path=artifact_path,
            lineage_id="lineage_alpha",
            parent_ids=["artifact_parent_a", "artifact_parent_b"],
        )
        stored = get_artifact(connection, artifact.id)
        artifacts = list_artifacts(connection, run.id)
        row = connection.execute(
            "SELECT parent_ids_json FROM artifacts WHERE id = ?",
            (artifact.id,),
        ).fetchone()

    assert artifact.id.startswith("artifact_")
    assert artifact.hash == sha256_bytes(b"phase zero artifact\n")
    assert stored == artifact
    assert artifacts == [artifact]
    assert json.loads(row["parent_ids_json"]) == ["artifact_parent_a", "artifact_parent_b"]


def test_artifact_registration_is_immutable_by_id(tmp_path):
    config = config_for(tmp_path)
    run, _ = ensure_active_run(config)
    artifact_path = config.output_dir(run.id) / "artifact.txt"
    artifact_path.write_bytes(b"same content\n")

    with connect(config.db_path) as connection:
        register_artifact(
            connection,
            run_id=run.id,
            artifact_type="phase0_fixture",
            path=artifact_path,
        )
        with pytest.raises(ValueError):
            register_artifact(
                connection,
                run_id=run.id,
                artifact_type="phase0_fixture",
                path=artifact_path,
            )
