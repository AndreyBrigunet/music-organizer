from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.models import AudioMetadata
from app.utils import normalize_text

try:
    from mutagen import File as MutagenFile
except ImportError:  # pragma: no cover - exercised only when dependency missing
    MutagenFile = None


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
        "date": metadata.date,
        "genre": metadata.genre,
    }

    for key, value in tag_map.items():
        if value:
            audio.tags[key] = [value]
        elif key in audio.tags:
            del audio.tags[key]

    audio.save()
