from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AudioMetadata:
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    track_number: Optional[str] = None
    disc_number: Optional[str] = None
    date: Optional[str] = None
    genre: Optional[str] = None
    source: str = "unknown"

    def has_core_identity(self) -> bool:
        return bool(self.title and (self.artist or self.album_artist))

    def has_any_identity(self) -> bool:
        return bool(
            self.title
            or self.artist
            or self.album
            or self.album_artist
            or self.track_number
        )

    def primary_artist(self) -> Optional[str]:
        return self.album_artist or self.artist

    def merged_with(
        self,
        fallback: "AudioMetadata",
        source: Optional[str] = None,
    ) -> "AudioMetadata":
        return AudioMetadata(
            title=self.title or fallback.title,
            artist=self.artist or fallback.artist,
            album=self.album or fallback.album,
            album_artist=self.album_artist or fallback.album_artist,
            track_number=self.track_number or fallback.track_number,
            disc_number=self.disc_number or fallback.disc_number,
            date=self.date or fallback.date,
            genre=self.genre or fallback.genre,
            source=source or self.source,
        )

    def merged_for_online_match(
        self,
        fallback: "AudioMetadata",
        source: Optional[str] = None,
    ) -> "AudioMetadata":
        artist = self.artist or fallback.artist
        album_artist = self.album_artist or self.artist or fallback.album_artist or artist
        return AudioMetadata(
            title=self.title or fallback.title,
            artist=artist,
            album=self.album,
            album_artist=album_artist,
            track_number=self.track_number or fallback.track_number,
            disc_number=self.disc_number or fallback.disc_number,
            date=self.date,
            genre=self.genre,
            source=source or self.source,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateMatch:
    metadata: AudioMetadata
    confidence: float
    source: str
    raw_score: float = 0.0
    recording_id: Optional[str] = None
    release_id: Optional[str] = None
    reason: str = ""
    score_explanation: str = ""
    title_similarity: float = 0.0
    artist_similarity: float = 0.0
    album_similarity: float = 0.0
    query_metadata: Optional[AudioMetadata] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "raw_score": self.raw_score,
            "recording_id": self.recording_id,
            "release_id": self.release_id,
            "reason": self.reason,
            "score_explanation": self.score_explanation,
            "title_similarity": round(self.title_similarity, 4),
            "artist_similarity": round(self.artist_similarity, 4),
            "album_similarity": round(self.album_similarity, 4),
            "query_metadata": self.query_metadata.to_dict() if self.query_metadata else None,
        }


@dataclass
class MatchDecision:
    action: str
    detected_metadata: AudioMetadata
    metadata_to_write: Optional[AudioMetadata]
    confidence: float
    chosen_match: Optional[CandidateMatch]
    reason: str
    notes: List[str] = field(default_factory=list)
    review_candidates: List[CandidateMatch] = field(default_factory=list)

    def to_report_dict(self, original_path: str, destination_path: Optional[str]) -> Dict[str, Any]:
        match_provider = self.report_provider()
        report_metadata = self.chosen_match.metadata if self.chosen_match else self.metadata_to_write
        return {
            "original_path": original_path,
            "detected_tags": self.detected_metadata.to_dict(),
            "chosen_match": self.chosen_match.to_dict() if self.chosen_match else None,
            "match_provider": match_provider,
            "match_title": report_metadata.title if report_metadata else None,
            "match_artist": report_metadata.primary_artist() if report_metadata else None,
            "match_album": report_metadata.album if report_metadata else None,
            "score_explanation": self.report_score_explanation(),
            "confidence": round(self.confidence, 4),
            "final_action": self.action,
            "destination_path": destination_path,
            "reason": self.reason,
            "notes": list(self.notes),
        }

    def report_provider(self) -> Optional[str]:
        if self.chosen_match:
            return self.chosen_match.source
        if self.metadata_to_write and "matched_by_tags" in self.notes:
            return "tags"
        return self.metadata_to_write.source if self.metadata_to_write else None

    def report_score_explanation(self) -> str:
        if self.chosen_match and self.chosen_match.score_explanation:
            return self.chosen_match.score_explanation
        if self.metadata_to_write and "matched_by_tags" in self.notes:
            return "Organized using existing local tags because no online match exceeded the confidence threshold."
        return ""

    def _report_score_explanation(self) -> str:
        return self.report_score_explanation()


@dataclass
class ProcessingResult:
    source_path: str
    destination_path: Optional[str]
    decision: MatchDecision
    tag_write_success: Optional[bool] = None
    transfer_success: Optional[bool] = None
    error: Optional[str] = None

    def to_report_dict(self) -> Dict[str, Any]:
        data = self.decision.to_report_dict(
            original_path=self.source_path,
            destination_path=self.destination_path,
        )
        data.update(
            {
                "tag_write_success": self.tag_write_success,
                "transfer_success": self.transfer_success,
                "error": self.error,
            }
        )
        return data
