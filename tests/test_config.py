from pathlib import Path

import pytest

from app.config import DEFAULT_MATCHED_PATH_TEMPLATE, build_config


def test_build_config_rejects_same_input_and_output(tmp_path: Path) -> None:
    input_dir = tmp_path / "library"
    input_dir.mkdir()

    with pytest.raises(ValueError, match="different from --input"):
        build_config(
            input_dir=input_dir,
            output_dir=input_dir,
            dry_run=True,
            copy_mode=False,
            move_mode=False,
            min_confidence=0.85,
            export_unmatched_playlist=False,
        )


def test_build_config_rejects_output_inside_input(tmp_path: Path) -> None:
    input_dir = tmp_path / "library"
    output_dir = input_dir / "sorted"
    input_dir.mkdir()

    with pytest.raises(ValueError, match="must not be inside --input"):
        build_config(
            input_dir=input_dir,
            output_dir=output_dir,
            dry_run=True,
            copy_mode=False,
            move_mode=False,
            min_confidence=0.85,
            export_unmatched_playlist=False,
        )


def test_build_config_reads_matched_path_template_from_env(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setenv("MATCHED_PATH_TEMPLATE", "{artist}/{title}.{ext}")

    config = build_config(
        input_dir=input_dir,
        output_dir=output_dir,
        dry_run=True,
        copy_mode=False,
        move_mode=False,
        min_confidence=0.85,
        export_unmatched_playlist=False,
    )

    assert config.matched_path_template == "{artist}/{title}.{ext}"


def test_build_config_uses_default_matched_path_template_when_missing(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("MATCHED_PATH_TEMPLATE", raising=False)

    config = build_config(
        input_dir=input_dir,
        output_dir=output_dir,
        dry_run=True,
        copy_mode=False,
        move_mode=False,
        min_confidence=0.85,
        export_unmatched_playlist=False,
    )

    assert config.matched_path_template == DEFAULT_MATCHED_PATH_TEMPLATE


def test_build_config_rejects_invalid_matched_path_template_field(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setenv("MATCHED_PATH_TEMPLATE", "{artist}/{unknown}.{ext}")

    with pytest.raises(ValueError, match="unsupported fields"):
        build_config(
            input_dir=input_dir,
            output_dir=output_dir,
            dry_run=True,
            copy_mode=False,
            move_mode=False,
            min_confidence=0.85,
            export_unmatched_playlist=False,
        )


def test_build_config_rejects_non_relative_matched_path_template(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setenv("MATCHED_PATH_TEMPLATE", "../outside/{title}.{ext}")

    with pytest.raises(ValueError, match="relative path template"):
        build_config(
            input_dir=input_dir,
            output_dir=output_dir,
            dry_run=True,
            copy_mode=False,
            move_mode=False,
            min_confidence=0.85,
            export_unmatched_playlist=False,
        )


def test_build_config_rejects_absolute_matched_path_template(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setenv("MATCHED_PATH_TEMPLATE", "C:/Music/{title}.{ext}")

    with pytest.raises(ValueError, match="relative path template"):
        build_config(
            input_dir=input_dir,
            output_dir=output_dir,
            dry_run=True,
            copy_mode=False,
            move_mode=False,
            min_confidence=0.85,
            export_unmatched_playlist=False,
        )
