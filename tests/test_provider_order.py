from pathlib import Path

import pytest

from app.config import build_config


def test_build_config_reads_provider_order_from_env(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setenv("SEARCH_PROVIDER_ORDER", "discogs,deezer,musicbrainz,itunes")

    config = build_config(
        input_dir=input_dir,
        output_dir=output_dir,
        dry_run=True,
        copy_mode=False,
        move_mode=False,
        min_confidence=0.85,
        export_unmatched_playlist=False,
    )

    assert config.provider_order == ("discogs", "deezer", "musicbrainz", "itunes")


def test_build_config_rejects_invalid_provider_order(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setenv("SEARCH_PROVIDER_ORDER", "spotify,musicbrainz")

    with pytest.raises(ValueError, match="unsupported providers"):
        build_config(
            input_dir=input_dir,
            output_dir=output_dir,
            dry_run=True,
            copy_mode=False,
            move_mode=False,
            min_confidence=0.85,
            export_unmatched_playlist=False,
        )
