from __future__ import annotations

from copy import deepcopy
import json
import logging
from typing import List, Optional

import requests

from app.models import AudioMetadata, CandidateMatch
from app.utils import normalize_artist_for_compare, normalize_for_compare, normalize_text


class DeezerClient:
    api_url = "https://api.deezer.com/search"
    source = "deezer"

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger
        self.enabled = True
        self.status_reason: Optional[str] = None
        self.session = requests.Session()
        self._search_cache: dict[tuple[str, str, str, int], List[CandidateMatch]] = {}

    @property
    def status_label(self) -> str:
        return "yes"

    def search_recordings(self, metadata: AudioMetadata, limit: int = 5) -> List[CandidateMatch]:
        if not metadata.title:
            return []
        cache_key = self._search_cache_key(metadata, limit)
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            return self._clone_candidates(cached)

        query_parts = ['track:"{0}"'.format(metadata.title)]
        if metadata.primary_artist():
            query_parts.append('artist:"{0}"'.format(metadata.primary_artist()))
        if metadata.album:
            query_parts.append('album:"{0}"'.format(metadata.album))
        params = {
            "q": " ".join(query_parts),
            "limit": max(1, min(int(limit), 10)),
        }

        try:
            response = self.session.get(self.api_url, params=params, timeout=15)
        except Exception as exc:
            if self.logger:
                self.logger.warning("Deezer search failed for %s / %s: %s", metadata.artist, metadata.title, exc)
            return []

        if response.status_code >= 400:
            self._log_http_error(response, metadata, params)
            return []

        try:
            payload = response.json()
        except ValueError as exc:
            if self.logger:
                self.logger.warning("Deezer search failed for %s / %s: invalid JSON response (%s)", metadata.artist, metadata.title, exc)
            return []

        if isinstance(payload, dict) and payload.get("error"):
            self._log_api_error(payload, metadata, params)
            return []

        candidates: List[CandidateMatch] = []
        for index, item in enumerate(payload.get("data", []), start=1):
            artist_info = item.get("artist") if isinstance(item.get("artist"), dict) else {}
            album_info = item.get("album") if isinstance(item.get("album"), dict) else {}
            rank = self._safe_int(item.get("rank"))
            rank_bonus = min(0.08, (rank or 0) / 10_000_000) if rank is not None else 0.0
            candidates.append(
                CandidateMatch(
                    metadata=AudioMetadata(
                        title=normalize_text(item.get("title")),
                        artist=normalize_text(artist_info.get("name")),
                        album=normalize_text(album_info.get("title")),
                        album_artist=normalize_text(artist_info.get("name")),
                        track_number=normalize_text(str(item.get("track_position"))) if item.get("track_position") is not None else None,
                        disc_number=normalize_text(str(item.get("disk_number"))) if item.get("disk_number") is not None else None,
                        date=normalize_text(item.get("release_date")),
                        source="deezer",
                    ),
                    confidence=0.0,
                    source="deezer",
                    raw_score=max(0.40, 0.96 - ((index - 1) * 0.10) + rank_bonus),
                    recording_id=normalize_text(str(item.get("id"))) if item.get("id") is not None else None,
                    release_id=normalize_text(str(album_info.get("id"))) if album_info.get("id") is not None else None,
                    reason="Deezer search match",
                )
            )

        self._search_cache[cache_key] = self._clone_candidates(candidates)
        return candidates

    def _log_http_error(self, response: requests.Response, metadata: AudioMetadata, params: dict[str, object]) -> None:
        if not self.logger:
            return
        payload = {
            "provider": "deezer",
            "endpoint": self.api_url,
            "params": params,
            "status_code": response.status_code,
            "response_body": response.text,
            "artist": metadata.primary_artist(),
            "title": metadata.title,
        }
        self.logger.warning("Deezer request failed: %s", json.dumps(payload, ensure_ascii=False))

    def _log_api_error(self, payload: dict, metadata: AudioMetadata, params: dict[str, object]) -> None:
        if not self.logger:
            return
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        body = {
            "provider": "deezer",
            "endpoint": self.api_url,
            "params": params,
            "code": error.get("code"),
            "type": error.get("type"),
            "message": error.get("message"),
            "artist": metadata.primary_artist(),
            "title": metadata.title,
        }
        self.logger.warning("Deezer API error: %s", json.dumps(body, ensure_ascii=False))

    @staticmethod
    def _safe_int(value: object) -> Optional[int]:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clone_candidates(candidates: List[CandidateMatch]) -> List[CandidateMatch]:
        return deepcopy(candidates)

    @staticmethod
    def _search_cache_key(metadata: AudioMetadata, limit: int) -> tuple[str, str, str, int]:
        return (
            normalize_for_compare(metadata.title),
            normalize_artist_for_compare(metadata.primary_artist()),
            normalize_for_compare(metadata.album),
            max(1, min(int(limit), 10)),
        )
