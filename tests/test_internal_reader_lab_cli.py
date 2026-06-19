import json
from pathlib import Path

from abi.cli import main
from abi.modules.internal_reader_lab import INTERNAL_READER_LAB_ARTIFACT_TYPES


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


def test_autonomous_reader_lab_cli_fake(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
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
    assert lab_payload["accepted"] is True
    assert set(lab_payload["artifact_ids"]) == set(INTERNAL_READER_LAB_ARTIFACT_TYPES)
    assert lab_payload["counts"]["model_calls"] == 0
    assert lab_payload["gate_report"]["eligible"] is False


def test_autonomous_reader_lab_cli_openai_guard(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
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

    openai_exit = main(
        [
            "--root",
            str(tmp_path),
            "autonomous",
            "reader-lab",
            "--client",
            "openai",
            "--packet-dir",
            pilot_payload["packet_dir"],
        ]
    )
    openai_payload = json.loads(capsys.readouterr().out)

    assert openai_exit == 1
    assert openai_payload["refused"] is True
    assert "--allow-live-model" in openai_payload["message"]
    assert openai_payload["counts"]["model_calls"] == 0
