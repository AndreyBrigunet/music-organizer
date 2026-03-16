from pathlib import Path

from app.matcher import TrackMatcher
from app.models import AudioMetadata


class _NoResultClient:
    def search_recordings(self, metadata: AudioMetadata, limit: int = 5):
        return []


class _NoAcoustIdClient:
    def match_file(self, path: Path):
        return []


def test_fallback_by_tags_is_reported_as_matched() -> None:
    matcher = TrackMatcher(
        min_confidence=0.85,
        search_clients=[_NoResultClient()],
        acoustid_client=_NoAcoustIdClient(),
        search_limit=5,
    )

    decision = matcher.match(
        Path("song.flac"),
        AudioMetadata(
            title="Song",
            artist="Artist",
            album="Album",
            track_number="1",
            source="tags",
        ),
    )

    assert decision.action == "Matched"
    assert decision.metadata_to_write is not None
    assert decision.notes == ["matched_by_tags"]
