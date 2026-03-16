from __future__ import annotations

import logging
from typing import List, Optional

import requests

from app.models import AudioMetadata, CandidateMatch
from app.utils import normalize_text


class LastFmClient:
    api_url = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: Optional[str], logger: Optional[logging.Logger] = None) -> None:
        self.api_key = api_key
        self.logger = logger
        self.status_reason = None if api_key else "missing LASTFM_API_KEY"
        self.enabled = self.status_reason is None

    @property
    def status_label(self) -> str:
        if self.enabled:
            return "yes"
        return "no ({0})".format(self.status_reason or "disabled")

    def search_recordings(self, metadata: AudioMetadata, limit: int = 5) -> List[CandidateMatch]:
        if not self.enabled or not metadata.title:
            return []

        params = {
            "method": "track.search",
            "track": metadata.title,
            "artist": metadata.primary_artist() or "",
            "api_key": self.api_key,
            "format": "json",
            "limit": limit,
        }

        try:
            response = requests.get(self.api_url, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            if self.logger:
                self.logger.warning("Last.fm search failed for %s / %s: %s", metadata.artist, metadata.title, exc)
            return []

        track_matches = payload.get("results", {}).get("trackmatches", {}).get("track", [])
        if isinstance(track_matches, dict):
            track_matches = [track_matches]

        candidates: List[CandidateMatch] = []
        for index, item in enumerate(track_matches, start=1):
            listeners = self._safe_int(item.get("listeners"))
            listener_bonus = min(0.12, listeners / 1_000_000) if listeners is not None else 0.0
            candidates.append(
                CandidateMatch(
                    metadata=AudioMetadata(
                        title=normalize_text(item.get("name")),
                        artist=normalize_text(item.get("artist")),
                        source="lastfm",
                    ),
                    confidence=0.0,
                    source="lastfm",
                    raw_score=max(0.35, 0.88 - ((index - 1) * 0.10) + listener_bonus),
                    reason="Last.fm track.search match",
                )
            )
        return candidates

    @staticmethod
    def _safe_int(value: object) -> Optional[int]:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None
