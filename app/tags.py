from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, Dict, Iterable, Optional

from app.models import AudioMetadata
from app.utils import normalize_text

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import TXXX
except ImportError:  # pragma: no cover - exercised only when dependency missing
    MutagenFile = None
    TXXX = None


YEAR_RE = re.compile(r"(?P<year>\d{4})")


def _first_value(tags: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = tags.get(key)
        if isinstance(value, list):
            if value:
                return normalize_text(str(value[0]))
        elif value is not None:
            return normalize_text(str(value))
    return None


def read_metadata(path: Path, logger: Optional[logging.Logger] = None) -> AudioMetadata:
    if MutagenFile is None:
        raise RuntimeError("mutagen is not installed. Install dependencies from requirements.txt.")

    try:
        audio = MutagenFile(path, easy=True)
    except Exception as exc:
        if logger:
            logger.warning("Failed to read tags from %s: %s", path, exc)
        return AudioMetadata(source="read-error")

    if audio is None or audio.tags is None:
        return AudioMetadata(source="tags")

    tags = dict(audio.tags)
    return AudioMetadata(
        title=_first_value(tags, ("title",)),
        artist=_first_value(tags, ("artist",)),
        album=_first_value(tags, ("album",)),
        album_artist=_first_value(tags, ("albumartist", "album artist")),
        track_number=_first_value(tags, ("tracknumber", "track")),
        disc_number=_first_value(tags, ("discnumber", "disc")),
        date=_first_value(tags, ("date", "year")),
        genre=_first_value(tags, ("genre",)),
        source="tags",
    )


def write_metadata(
    path: Path,
    metadata: AudioMetadata,
    logger: Optional[logging.Logger] = None,
) -> None:
    if MutagenFile is None:
        raise RuntimeError("mutagen is not installed. Install dependencies from requirements.txt.")

    audio = MutagenFile(path, easy=True)
    if audio is None:
        raise RuntimeError("Mutagen could not open file for writing: {0}".format(path))

    if audio.tags is None and hasattr(audio, "add_tags"):
        try:
            audio.add_tags()
        except Exception as exc:
            if logger:
                logger.warning("Could not create tags for %s: %s", path, exc)

    if audio.tags is None:
        raise RuntimeError("Mutagen could not prepare writable tags for: {0}".format(path))

    tag_map = {
        "title": metadata.title,
        "artist": metadata.artist,
        "album": metadata.album,
        "albumartist": metadata.album_artist,
        "tracknumber": metadata.track_number,
        "discnumber": metadata.disc_number,
        "date": _normalize_year_value(metadata.date),
        "genre": metadata.genre,
    }

    for key, value in tag_map.items():
        if value:
            audio.tags[key] = [value]
        elif key in audio.tags:
            del audio.tags[key]

    audio.save()
    _write_musicbrainz_tags(path, metadata, logger=logger)


def _normalize_year_value(value: Optional[str]) -> Optional[str]:
    cleaned = normalize_text(value)
    if not cleaned:
        return None
    match = YEAR_RE.search(cleaned)
    if match:
        return match.group("year")
    return cleaned


def _write_musicbrainz_tags(
    path: Path,
    metadata: AudioMetadata,
    logger: Optional[logging.Logger] = None,
) -> None:
    musicbrainz_tags = {
        "MusicBrainz Track Id": metadata.musicbrainz_recording_id,
        "MusicBrainz Album Id": metadata.musicbrainz_release_id,
        "MusicBrainz Artist Id": metadata.musicbrainz_artist_id,
        "MusicBrainz Album Artist Id": metadata.musicbrainz_album_artist_id,
    }
    if not any(musicbrainz_tags.values()):
        return

    if MutagenFile is None:
        raise RuntimeError("mutagen is not installed. Install dependencies from requirements.txt.")

    audio = MutagenFile(path)
    if audio is None:
        raise RuntimeError("Mutagen could not open file for MusicBrainz tag writing: {0}".format(path))

    suffix = path.suffix.lower()
    try:
        if suffix in {".mp3", ".wav"}:
            _write_id3_musicbrainz_tags(audio, musicbrainz_tags)
        elif suffix in {".flac", ".ogg", ".opus"}:
            _write_vorbis_musicbrainz_tags(audio, musicbrainz_tags)
        elif suffix in {".m4a", ".mp4"}:
            _write_mp4_musicbrainz_tags(audio, musicbrainz_tags)
        else:
            return
        audio.save()
    except Exception as exc:
        if logger:
            logger.warning("MusicBrainz tag write failed for %s: %s", path, exc)


def _write_id3_musicbrainz_tags(audio: Any, musicbrainz_tags: Dict[str, Optional[str]]) -> None:
    if TXXX is None:
        raise RuntimeError("mutagen.id3 is not available.")
    if getattr(audio, "tags", None) is None and hasattr(audio, "add_tags"):
        audio.add_tags()
    tags = getattr(audio, "tags", None)
    if tags is None:
        raise RuntimeError("ID3 tags are not available.")

    for description, value in musicbrainz_tags.items():
        tags.delall("TXXX:{0}".format(description))
        if value:
            tags.add(TXXX(encoding=3, desc=description, text=[value]))


def _write_vorbis_musicbrainz_tags(audio: Any, musicbrainz_tags: Dict[str, Optional[str]]) -> None:
    tags = getattr(audio, "tags", None)
    container = tags if tags is not None else audio
    key_map = {
        "MusicBrainz Track Id": "MUSICBRAINZ_TRACKID",
        "MusicBrainz Album Id": "MUSICBRAINZ_ALBUMID",
        "MusicBrainz Artist Id": "MUSICBRAINZ_ARTISTID",
        "MusicBrainz Album Artist Id": "MUSICBRAINZ_ALBUMARTISTID",
    }
    for description, key in key_map.items():
        value = musicbrainz_tags.get(description)
        if value:
            container[key] = [value]
        elif key in container:
            del container[key]


def _write_mp4_musicbrainz_tags(audio: Any, musicbrainz_tags: Dict[str, Optional[str]]) -> None:
    tags = getattr(audio, "tags", None)
    container = tags if tags is not None else audio
    key_map = {
        "MusicBrainz Track Id": "----:com.apple.iTunes:MusicBrainz Track Id",
        "MusicBrainz Album Id": "----:com.apple.iTunes:MusicBrainz Album Id",
        "MusicBrainz Artist Id": "----:com.apple.iTunes:MusicBrainz Artist Id",
        "MusicBrainz Album Artist Id": "----:com.apple.iTunes:MusicBrainz Album Artist Id",
    }
    for description, key in key_map.items():
        value = musicbrainz_tags.get(description)
        if value:
            container[key] = [value.encode("utf-8")]
        elif key in container:
            del container[key]
