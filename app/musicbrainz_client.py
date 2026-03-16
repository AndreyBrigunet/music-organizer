from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Dict, List, Optional

from app.config import APP_NAME, APP_VERSION
from app.models import AudioMetadata, CandidateMatch
from app.utils import normalize_artist_for_compare, normalize_for_compare, normalize_text

try:
    import musicbrainzngs
except ImportError:  # pragma: no cover - exercised only when dependency missing
    musicbrainzngs = None


class MusicBrainzClient:
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger
        self.enabled = musicbrainzngs is not None
        self.status_reason = None if self.enabled else "musicbrainzngs not installed"
        self._search_cache: dict[tuple[str, str, str, int], List[CandidateMatch]] = {}
        self._lookup_cache: dict[str, Optional[AudioMetadata]] = {}
        if self.enabled:
            musicbrainzngs.set_useragent(
                APP_NAME,
                APP_VERSION,
                "https://example.invalid/music-organizer",
            )

    @property
    def status_label(self) -> str:
        if self.enabled:
            return "yes"
        return "no ({0})".format(self.status_reason or "disabled")

    def search_recordings(self, metadata: AudioMetadata, limit: int = 5) -> List[CandidateMatch]:
        if not self.enabled:
            return []
        if not metadata.title or not metadata.primary_artist():
            return []
        cache_key = self._search_cache_key(metadata, limit)
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            return self._clone_candidates(cached)

        query = {
            "recording": metadata.title,
            "artist": metadata.primary_artist(),
            "limit": limit,
        }
        if metadata.album:
            query["release"] = metadata.album

        try:
            response = musicbrainzngs.search_recordings(**query)
        except Exception as exc:
            if self.logger:
                self.logger.warning("MusicBrainz search failed for %s / %s: %s", metadata.artist, metadata.title, exc)
            return []

        recordings = response.get("recording-list", [])
        candidates = [self._recording_to_candidate(item) for item in recordings]
        self._search_cache[cache_key] = self._clone_candidates(candidates)
        return candidates

    def lookup_recording(self, recording_id: str) -> Optional[AudioMetadata]:
        if not self.enabled or not recording_id:
            return None
        if recording_id in self._lookup_cache:
            return deepcopy(self._lookup_cache[recording_id])

        try:
            response = musicbrainzngs.get_recording_by_id(
                recording_id,
                includes=["artists", "releases"],
            )
        except Exception as exc:
            if self.logger:
                self.logger.warning("MusicBrainz lookup failed for %s: %s", recording_id, exc)
            return None

        recording = response.get("recording", {})
        artist_phrase = normalize_text(recording.get("artist-credit-phrase"))
        artist_id = self._extract_primary_artist_id(recording.get("artist-credit", []))
        release_list = recording.get("release-list", [])
        release = release_list[0] if release_list else {}
        release_artist_id = self._extract_primary_artist_id(release.get("artist-credit", [])) or artist_id
        metadata = AudioMetadata(
            title=normalize_text(recording.get("title")),
            artist=artist_phrase,
            album=normalize_text(release.get("title")),
            album_artist=artist_phrase,
            track_number=None,
            musicbrainz_recording_id=normalize_text(recording.get("id")),
            musicbrainz_release_id=normalize_text(release.get("id")),
            musicbrainz_artist_id=artist_id,
            musicbrainz_album_artist_id=release_artist_id,
            source="musicbrainz",
        )
        self._lookup_cache[recording_id] = deepcopy(metadata)
        return metadata

    def _recording_to_candidate(self, item: Dict[str, Any]) -> CandidateMatch:
        release_list = item.get("release-list", [])
        first_release = release_list[0] if release_list else {}
        artist_phrase = normalize_text(item.get("artist-credit-phrase"))
        artist_id = self._extract_primary_artist_id(item.get("artist-credit", []))
        release_artist_id = self._extract_primary_artist_id(first_release.get("artist-credit", [])) or artist_id
        track_number = None
        medium_list = first_release.get("medium-list", [])
        if medium_list:
            track_list = medium_list[0].get("track-list", [])
            if track_list:
                track_number = normalize_text(track_list[0].get("number"))

        metadata = AudioMetadata(
            title=normalize_text(item.get("title")),
            artist=artist_phrase,
            album=normalize_text(first_release.get("title")),
            album_artist=artist_phrase,
            track_number=track_number,
            date=normalize_text(first_release.get("date")),
            musicbrainz_recording_id=normalize_text(item.get("id")),
            musicbrainz_release_id=normalize_text(first_release.get("id")),
            musicbrainz_artist_id=artist_id,
            musicbrainz_album_artist_id=release_artist_id,
            source="musicbrainz",
        )
        raw_score = self._extract_score(item)
        return CandidateMatch(
            metadata=metadata,
            confidence=0.0,
            source="musicbrainz",
            raw_score=raw_score,
            recording_id=item.get("id"),
            release_id=first_release.get("id"),
        )

    @staticmethod
    def _extract_score(item: Dict[str, Any]) -> float:
        raw_value = item.get("score", item.get("ext:score", 0))
        try:
            return float(raw_value) / 100.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _clone_candidates(candidates: List[CandidateMatch]) -> List[CandidateMatch]:
        return deepcopy(candidates)

    @staticmethod
    def _search_cache_key(metadata: AudioMetadata, limit: int) -> tuple[str, str, str, int]:
        return (
            normalize_for_compare(metadata.title),
            normalize_artist_for_compare(metadata.primary_artist()),
            normalize_for_compare(metadata.album),
            limit,
        )

    @staticmethod
    def _extract_primary_artist_id(artist_credit: object) -> Optional[str]:
        if not isinstance(artist_credit, list):
            return None
        for item in artist_credit:
            if not isinstance(item, dict):
                continue
            artist = item.get("artist")
            if isinstance(artist, dict):
                artist_id = normalize_text(artist.get("id"))
                if artist_id:
                    return artist_id
        return None
