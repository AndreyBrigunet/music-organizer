from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
from typing import List, Optional

from app.models import AudioMetadata, CandidateMatch
from app.musicbrainz_client import MusicBrainzClient
from app.utils import normalize_text

try:
    import acoustid
except ImportError:  # pragma: no cover - exercised only when dependency missing
    acoustid = None


class AcoustIdClient:
    def __init__(
        self,
        api_key: Optional[str],
        musicbrainz_client: Optional[MusicBrainzClient] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.api_key = api_key
        self.musicbrainz_client = musicbrainz_client
        self.logger = logger
        self.fpcalc_path = self._resolve_fpcalc_path()
        self.status_reason = self._build_status_reason()
        self.enabled = self.status_reason is None

    @property
    def status_label(self) -> str:
        if self.enabled:
            return "yes"
        return "no ({0})".format(self.status_reason or "disabled")

    def match_file(self, path: Path) -> List[CandidateMatch]:
        if not self.enabled:
            return []

        if self.fpcalc_path:
            os.environ["FPCALC"] = self.fpcalc_path

        try:
            duration, fingerprint = acoustid.fingerprint_file(
                str(path),
                force_fpcalc=bool(self.fpcalc_path),
            )
        except Exception as exc:
            if self.logger:
                self.logger.warning("AcoustID fingerprint failed for %s: %s", path, exc)
            return []

        try:
            response = acoustid.lookup(
                self.api_key,
                fingerprint,
                duration,
            )
        except Exception as exc:
            if self.logger:
                self.logger.warning("AcoustID lookup failed for %s: %s", path, exc)
            return []

        self._log_lookup_response(path, response)

        if not isinstance(response, dict) or response.get("status") != "ok":
            self._handle_error_response(path, response)
            return []

        try:
            results = list(acoustid.parse_lookup_result(response))
        except Exception as exc:
            if self.logger:
                self.logger.warning("AcoustID lookup failed for %s: %s", path, exc)
            return []

        matches = []
        for result in results:
            if len(result) < 4:
                continue
            score = float(result[0])
            recording_id = result[1]
            title = normalize_text(result[2])
            artist = normalize_text(result[3])

            lookup_metadata = None
            if self.musicbrainz_client and recording_id:
                lookup_metadata = self.musicbrainz_client.lookup_recording(recording_id)

            metadata = AudioMetadata(
                title=(lookup_metadata.title if lookup_metadata else None) or title,
                artist=(lookup_metadata.artist if lookup_metadata else None) or artist,
                album=(lookup_metadata.album if lookup_metadata else None),
                album_artist=(lookup_metadata.album_artist if lookup_metadata else None) or artist,
                track_number=(lookup_metadata.track_number if lookup_metadata else None),
                date=(lookup_metadata.date if lookup_metadata else None),
                source="acoustid",
            )
            matches.append(
                CandidateMatch(
                    metadata=metadata,
                    confidence=0.0,
                    source="acoustid",
                    raw_score=score,
                    recording_id=recording_id,
                    reason="AcoustID fingerprint match",
                )
            )
        return matches

    def _handle_error_response(self, path: Path, response: object) -> None:
        message = "status: error"
        code = None

        if isinstance(response, dict):
            status = normalize_text(str(response.get("status"))) or "error"
            message = "status: {0}".format(status)

            error = response.get("error")
            if isinstance(error, dict):
                raw_message = normalize_text(str(error.get("message"))) if error.get("message") else None
                message = raw_message or message
                code = error.get("code")

        if self._is_invalid_api_key(code, message):
            self.enabled = False
            self.status_reason = "invalid ACOUSTID_API_KEY"

        if self.logger:
            if code is None:
                self.logger.warning("AcoustID lookup failed for %s: %s", path, message)
            else:
                self.logger.warning("AcoustID lookup failed for %s: %s (code %s)", path, message, code)

    def _log_lookup_response(self, path: Path, response: object) -> None:
        if not self.logger:
            return
        self.logger.info("AcoustID response for %s: %s", path, self._serialize_for_log(response))

    @staticmethod
    def _is_invalid_api_key(code: object, message: str) -> bool:
        if code == 4:
            return True
        return "invalid api key" in message.casefold()

    @classmethod
    def _serialize_for_log(cls, value: object) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, default=cls._json_default)
        except TypeError:
            return repr(value)

    @staticmethod
    def _json_default(value: object) -> object:
        if isinstance(value, bytes):
            return value.decode("ascii", errors="backslashreplace")
        return repr(value)

    def _build_status_reason(self) -> Optional[str]:
        if acoustid is None:
            return "pyacoustid not installed"
        if not self.api_key:
            return "missing ACOUSTID_API_KEY"
        if self._has_fingerprint_backend():
            return None
        return "missing Chromaprint/fpcalc backend"

    def _has_fingerprint_backend(self) -> bool:
        if acoustid is None:
            return False
        if getattr(acoustid, "have_audioread", False) and getattr(acoustid, "have_chromaprint", False):
            return True
        return self.fpcalc_path is not None

    @staticmethod
    def _resolve_fpcalc_path() -> Optional[str]:
        project_fpcalc = Path(__file__).resolve().parent.parent / "tool" / "fpcalc.exe"
        if project_fpcalc.exists():
            return str(project_fpcalc)

        env_fpcalc = os.getenv("FPCALC")
        if env_fpcalc:
            resolved_env = shutil.which(env_fpcalc) or env_fpcalc
            if Path(resolved_env).exists():
                return str(Path(resolved_env))

        path_fpcalc = shutil.which("fpcalc")
        if path_fpcalc:
            return path_fpcalc

        return None
