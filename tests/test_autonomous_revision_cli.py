import json
from pathlib import Path

from abi.cli import main
from abi.modules.autonomous_revision import AUTONOMOUS_REVISION_ARTIFACT_TYPES


SOURCE_NOTE = """# Source Note

The table remains visible while the room withholds what happened overnight.
"""

THEORY_FRAGMENT = """# Theory Fragment

The opening must return changed without announcing its own machinery.
"""


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


def build_reader_lab_packet(tmp_path: Path, capsys) -> dict[str, object]:
    source_dir = write_sources(tmp_path)
    pilot_exit = main(
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
    pilot_payload = json.loads(capsys.readouterr().out)
    assert pilot_exit == 0

    lab_exit = main(
        [
            "--root",
            str(tmp_path),
            "autonomous",
            "reader-lab",
            "--client",
            "fake",
            "--packet-dir",
            pilot_payload["packet_dir"],
        ]
    )
    lab_payload = json.loads(capsys.readouterr().out)
    assert lab_exit == 0
    return lab_payload


def test_autonomous_revise_cli_fake(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    lab_payload = build_reader_lab_packet(tmp_path, capsys)

    revise_exit = main(
        [
            "--root",
            str(tmp_path),
            "autonomous",
            "revise",
            "--client",
            "fake",
            "--reader-lab-packet",
            lab_payload["packet_dir"],
        ]
    )
    revise_payload = json.loads(capsys.readouterr().out)

    assert revise_exit == 0
    assert revise_payload["accepted"] is True
    assert set(revise_payload["artifact_ids"]) == set(AUTONOMOUS_REVISION_ARTIFACT_TYPES)
    assert revise_payload["counts"]["model_calls"] == 0
    assert revise_payload["gate_report"]["eligible"] is False
    assert "internal_operator_approval" in revise_payload["gate_report"]["missing_gates"]

    status_exit = main(
        [
            "--root",
            str(tmp_path),
            "finalization",
            "status",
            "--profile",
            "autonomous_creative_candidate",
        ]
    )
    status_payload = json.loads(capsys.readouterr().out)

    assert status_exit == 0
    assert status_payload["eligible"] is False
    assert "internal_operator_approval" in status_payload["missing_gates"]


def test_autonomous_revise_cli_openai_guard(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    lab_payload = build_reader_lab_packet(tmp_path, capsys)

    openai_exit = main(
        [
            "--root",
            str(tmp_path),
            "autonomous",
            "revise",
            "--client",
            "openai",
            "--reader-lab-packet",
            lab_payload["packet_dir"],
        ]
    )
    openai_payload = json.loads(capsys.readouterr().out)

    assert openai_exit == 1
    assert openai_payload["refused"] is True
    assert "--allow-live-model" in openai_payload["message"]
    assert openai_payload["counts"]["model_calls"] == 0
