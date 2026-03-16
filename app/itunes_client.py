from __future__ import annotations

import logging
from typing import List, Optional

import requests

from app.models import AudioMetadata, CandidateMatch
from app.utils import normalize_text


class ItunesClient:
    search_url = "https://itunes.apple.com/search"

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger
        self.enabled = True
        self.status_reason: Optional[str] = None

    @property
    def status_label(self) -> str:
        return "yes"

    def search_recordings(self, metadata: AudioMetadata, limit: int = 5) -> List[CandidateMatch]:
        if not metadata.title:
            return []

        term_parts = [metadata.primary_artist(), metadata.album, metadata.title]
        term = " ".join(part for part in term_parts if part)
        params = {
            "term": term,
            "entity": "song",
            "limit": limit,
        }

        try:
            response = requests.get(self.search_url, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            if self.logger:
                self.logger.warning("iTunes search failed for %s / %s: %s", metadata.artist, metadata.title, exc)
            return []

        candidates: List[CandidateMatch] = []
        for index, item in enumerate(payload.get("results", []), start=1):
            candidates.append(
                CandidateMatch(
                    metadata=AudioMetadata(
                        title=normalize_text(item.get("trackName")),
                        artist=normalize_text(item.get("artistName")),
                        album=normalize_text(item.get("collectionName")),
                        album_artist=normalize_text(item.get("artistName")),
                        track_number=normalize_text(str(item.get("trackNumber"))) if item.get("trackNumber") is not None else None,
                        disc_number=normalize_text(str(item.get("discNumber"))) if item.get("discNumber") is not None else None,
                        date=normalize_text(str(item.get("releaseDate", ""))[:10]) or None,
                        genre=normalize_text(item.get("primaryGenreName")),
                        source="itunes",
                    ),
                    confidence=0.0,
                    source="itunes",
                    raw_score=max(0.45, 1.0 - ((index - 1) * 0.10)),
                    recording_id=str(item.get("trackId")) if item.get("trackId") is not None else None,
                    release_id=str(item.get("collectionId")) if item.get("collectionId") is not None else None,
                    reason="iTunes Search API match",
                )
            )
        return candidates
