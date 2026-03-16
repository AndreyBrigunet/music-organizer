from __future__ import annotations

import json
import logging
from typing import Any, List, Optional, Tuple

import requests

from app.config import APP_NAME, APP_VERSION
from app.models import AudioMetadata, CandidateMatch
from app.utils import normalize_text


class DiscogsClient:
    api_url = "https://api.discogs.com/database/search"

    def __init__(self, user_token: Optional[str], logger: Optional[logging.Logger] = None) -> None:
        self.user_token = normalize_text(user_token)
        self.logger = logger
        self.status_reason = None if self.user_token else "missing DISCOGS_USER_TOKEN"
        self.enabled = self.status_reason is None

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

        params: dict[str, str | int] = {
            "track": metadata.title,
            "artist": metadata.primary_artist(),
            "type": "release",
            "per_page": max(1, min(int(limit), 5)),
            "page": 1,
        }
        if metadata.album:
            params["release_title"] = metadata.album

        headers = {
            "Authorization": "Discogs token={0}".format(self.user_token),
            "User-Agent": "{0}/{1}".format(APP_NAME, APP_VERSION),
            "Accept": "application/vnd.discogs.v2.plaintext+json",
        }

        try:
            response = requests.get(self.api_url, params=params, headers=headers, timeout=15)
        except Exception as exc:
            if self.logger:
                self.logger.warning("Discogs search failed for %s / %s: %s", metadata.artist, metadata.title, exc)
            return []

        if response.status_code >= 400:
            self._handle_error_response(response, metadata, params)
            return []

        try:
            payload = response.json()
        except ValueError as exc:
            if self.logger:
                self.logger.warning("Discogs search failed for %s / %s: invalid JSON response (%s)", metadata.artist, metadata.title, exc)
            return []

        results = payload.get("results", [])
        candidates: List[CandidateMatch] = []
        for index, item in enumerate(results, start=1):
            artist_name, album_title = self._parse_release_title(item.get("title"))
            artist = artist_name or metadata.primary_artist()
            album = album_title or normalize_text(item.get("title")) or metadata.album
            year = normalize_text(str(item.get("year"))) if item.get("year") is not None else None
            genres = item.get("genre") if isinstance(item.get("genre"), list) else []
            genre = normalize_text(genres[0]) if genres else None
            candidates.append(
                CandidateMatch(
                    metadata=AudioMetadata(
                        title=metadata.title,
                        artist=artist,
                        album=album,
                        album_artist=artist,
                        date=year,
                        genre=genre,
                        source="discogs",
                    ),
                    confidence=0.0,
                    source="discogs",
                    raw_score=max(0.25, 0.72 - ((index - 1) * 0.08)),
                    recording_id=str(item.get("id")) if item.get("id") is not None else None,
                    release_id=str(item.get("master_id")) if item.get("master_id") is not None else None,
                    reason="Discogs database search release match",
                )
            )
        return candidates

    def _handle_error_response(
        self,
        response: requests.Response,
        metadata: AudioMetadata,
        params: dict[str, str | int],
    ) -> None:
        reason, message, body = self._parse_error_response(response)
        if response.status_code in {401, 403} and reason in {"invalid_token", "forbidden"}:
            self.enabled = False
            self.status_reason = "invalid DISCOGS_USER_TOKEN"
        if self.logger:
            payload = {
                "provider": "discogs",
                "endpoint": self.api_url,
                "params": params,
                "status_code": response.status_code,
                "reason": reason,
                "message": message,
                "response_body": body,
                "artist": metadata.primary_artist(),
                "title": metadata.title,
            }
            self.logger.warning("Discogs request failed: %s", json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _parse_error_response(response: requests.Response) -> Tuple[str, str, str]:
        body = response.text
        reason = "http_error"
        message = body or "Discogs API request failed."
        try:
            payload = response.json()
        except ValueError:
            return reason, message, body

        if isinstance(payload, dict):
            message = normalize_text(payload.get("message")) or message
            if response.status_code == 401:
                reason = "invalid_token"
            elif response.status_code == 403:
                reason = "forbidden"
            elif response.status_code == 429:
                reason = "rate_limited"
            elif response.status_code == 400:
                reason = "bad_request"
        return reason, message, body

    @staticmethod
    def _parse_release_title(value: object) -> Tuple[Optional[str], Optional[str]]:
        cleaned = normalize_text(value)
        if not cleaned:
            return None, None
        if " - " not in cleaned:
            return None, cleaned
        artist, release = cleaned.split(" - ", 1)
        return normalize_text(artist), normalize_text(release)
