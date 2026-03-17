from pathlib import Path

import stat
from app.config import AppConfig, OperationMode
from app.models import AudioMetadata, MatchDecision
from app.mover import LibraryMover


def build_config(tmp_path: Path, mode: OperationMode) -> AppConfig:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    return AppConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        mode=mode,
        min_confidence=0.85,
        export_unmatched_playlist=False,
    )


def test_matched_destination_uses_track_and_title(tmp_path: Path) -> None:
    config = build_config(tmp_path, OperationMode.DRY_RUN)
    mover = LibraryMover(config)
    source = config.input_dir / "track.mp3"
    source.write_text("x", encoding="utf-8")
    decision = MatchDecision(
        action="Matched",
        detected_metadata=AudioMetadata(),
        metadata_to_write=AudioMetadata(
            title="Song:Name",
            artist="Artist",
            album="Best Of",
            album_artist="Artist",
            track_number="3",
        ),
        confidence=0.95,
        chosen_match=None,
        reason="test",
    )

    destination = mover.plan_destination(source, decision)
    assert destination == config.output_dir / "Matched" / "Artist" / "Best Of" / "03 - Song_Name.mp3"


def test_matched_destination_uses_custom_template(tmp_path: Path) -> None:
    config = build_config(tmp_path, OperationMode.DRY_RUN)
    config = AppConfig(
        input_dir=config.input_dir,
        output_dir=config.output_dir,
        mode=config.mode,
        min_confidence=config.min_confidence,
        export_unmatched_playlist=config.export_unmatched_playlist,
        matched_path_template="{artist}/{track_number}.{title}.{ext}",
    )
    mover = LibraryMover(config)
    source = config.input_dir / "track.flac"
    source.write_text("x", encoding="utf-8")
    decision = MatchDecision(
        action="Matched",
        detected_metadata=AudioMetadata(),
        metadata_to_write=AudioMetadata(
            title="Song:Name",
            artist="Artist",
            track_number="3",
        ),
        confidence=0.95,
        chosen_match=None,
        reason="test",
    )

    destination = mover.plan_destination(source, decision)
    assert destination == config.output_dir / "Matched" / "Artist" / "03.Song_Name.flac"


def test_transfer_avoids_filename_collision(tmp_path: Path) -> None:
    config = build_config(tmp_path, OperationMode.COPY)
    mover = LibraryMover(config)
    source = config.input_dir / "track.mp3"
    source.write_text("source", encoding="utf-8")
    source.chmod(source.stat().st_mode & ~stat.S_IWRITE)

    destination = config.output_dir / "Matched" / "Artist" / "Album" / "01 - Song.mp3"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("existing", encoding="utf-8")

    final_destination = mover.transfer(source, destination)
    assert final_destination.name == "01 - Song (2).mp3"
    assert final_destination.read_text(encoding="utf-8") == "source"
    assert final_destination.stat().st_mode & stat.S_IWRITE
    assert source.exists()


def test_dry_run_does_not_create_files(tmp_path: Path) -> None:
    config = build_config(tmp_path, OperationMode.DRY_RUN)
    mover = LibraryMover(config)
    source = config.input_dir / "track.mp3"
    source.write_text("source", encoding="utf-8")
    destination = config.output_dir / "Matched" / "Artist" / "Album" / "01 - Song.mp3"

    final_destination = mover.transfer(source, destination)
    assert final_destination == destination
    assert not destination.exists()
    assert source.exists()


def test_dry_run_reserves_duplicate_names_across_multiple_files(tmp_path: Path) -> None:
    config = build_config(tmp_path, OperationMode.DRY_RUN)
    mover = LibraryMover(config)
    first_source = config.input_dir / "track1.mp3"
    second_source = config.input_dir / "track2.mp3"
    first_source.write_text("one", encoding="utf-8")
    second_source.write_text("two", encoding="utf-8")
    destination = config.output_dir / "Matched" / "Artist" / "Album" / "01 - Song.mp3"

    first_destination = mover.transfer(first_source, destination)
    second_destination = mover.transfer(second_source, destination)

    assert first_destination.name == "01 - Song.mp3"
    assert second_destination.name == "01 - Song (2).mp3"
