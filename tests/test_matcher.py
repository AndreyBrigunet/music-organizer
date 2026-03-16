from pathlib import Path

import pytest

from app.matcher import (
    TrackMatcher,
    is_ambiguous,
    parse_filename_metadata,
    parse_filename_metadata_candidates,
    score_candidate_confidence,
)
from app.models import AudioMetadata, CandidateMatch


def test_parse_filename_metadata_with_artist_and_title() -> None:
    parsed = parse_filename_metadata(Path("B.U.G. Mafia - Pantelimonu' Petrece.mp3"))
    assert parsed.artist == "B.U.G. Mafia"
    assert parsed.title == "Pantelimonu' Petrece"
    assert parsed.album is None


def test_parse_filename_metadata_with_track_artist_album_title() -> None:
    parsed = parse_filename_metadata(Path("07 - Subcarpati - Culori - Balada Romanului.flac"))
    assert parsed.track_number == "07"
    assert parsed.artist == "Subcarpati"
    assert parsed.album == "Culori"
    assert parsed.title == "Balada Romanului"


def test_parse_filename_metadata_normalizes_artist_separators() -> None:
    parsed = parse_filename_metadata(Path("Magnat; Feoctist - Doi Vecini.flac"))
    assert parsed.artist == "Magnat & Feoctist"
    assert parsed.title == "Doi Vecini"


def test_parse_filename_metadata_supports_title_artist_variants() -> None:
    candidates = parse_filename_metadata_candidates(Path("Noaptea pe la 3 - Satoshi; Carla's Dreams.flac"))
    assert any(candidate.title == "Noaptea pe la 3" and candidate.artist == "Satoshi & Carla's Dreams" for candidate in candidates)


def test_exact_tag_match_scores_high_confidence() -> None:
    raw = AudioMetadata(title="Song", artist="Artist", album="Album", track_number="1", source="tags")
    detected = raw
    candidate = CandidateMatch(
        metadata=AudioMetadata(title="Song", artist="Artist", album="Album", track_number="1", source="musicbrainz"),
        confidence=0.0,
        source="musicbrainz",
        raw_score=0.99,
    )
    score = score_candidate_confidence(candidate, detected, raw)
    assert score >= 0.9


def test_filename_derived_match_scores_medium_confidence() -> None:
    raw = AudioMetadata(source="tags")
    detected = AudioMetadata(title="Song", artist="Artist", source="filename")
    candidate = CandidateMatch(
        metadata=AudioMetadata(title="Song", artist="Artist", album="Singles", source="musicbrainz"),
        confidence=0.0,
        source="musicbrainz",
        raw_score=0.90,
    )
    score = score_candidate_confidence(candidate, detected, raw)
    assert 0.6 <= score < 0.9


def test_diacritics_do_not_hurt_similarity_matching() -> None:
    raw = AudioMetadata(title="În Ochii Tăi", artist="Carla’s Dreams", source="tags")
    detected = raw
    candidate = CandidateMatch(
        metadata=AudioMetadata(title="In Ochii Tai", artist="Carla's Dreams", source="musicbrainz"),
        confidence=0.0,
        source="musicbrainz",
        raw_score=0.99,
    )
    score = score_candidate_confidence(candidate, detected, raw)
    assert score >= 0.9


def test_close_confidence_candidates_are_ambiguous() -> None:
    best = CandidateMatch(
        metadata=AudioMetadata(title="Song A", artist="Artist 1"),
        confidence=0.87,
        source="musicbrainz",
    )
    runner_up = CandidateMatch(
        metadata=AudioMetadata(title="Song B", artist="Artist 2"),
        confidence=0.84,
        source="musicbrainz",
    )
    assert is_ambiguous(best, runner_up) is True


def test_cross_source_corroboration_increases_confidence() -> None:
    musicbrainz_candidate = CandidateMatch(
        metadata=AudioMetadata(title="Song", artist="Artist"),
        confidence=0.80,
        source="musicbrainz",
        reason="MusicBrainz recording search",
    )
    itunes_candidate = CandidateMatch(
        metadata=AudioMetadata(title="Song", artist="Artist"),
        confidence=0.78,
        source="itunes",
        reason="iTunes Search API match",
    )

    TrackMatcher._apply_cross_source_corroboration([musicbrainz_candidate, itunes_candidate])

    assert musicbrainz_candidate.confidence == pytest.approx(0.85)
    assert itunes_candidate.confidence == pytest.approx(0.83)
    assert "corroborated by itunes" in musicbrainz_candidate.reason


class _SingleCandidateClient:
    def search_recordings(self, metadata: AudioMetadata, limit: int = 5):
        return [
            CandidateMatch(
                metadata=AudioMetadata(
                    title=metadata.title,
                    artist=metadata.artist,
                    album=metadata.album,
                    source="discogs",
                ),
                confidence=0.0,
                source="discogs",
                raw_score=0.40,
                recording_id="candidate-1",
            )
        ]


class _NoAcoustIdClient:
    def match_file(self, path: Path):
        return []


def test_review_decision_keeps_candidate_list_for_interactive_selection() -> None:
    matcher = TrackMatcher(
        min_confidence=0.95,
        search_clients=[_SingleCandidateClient()],
        acoustid_client=_NoAcoustIdClient(),
        search_limit=5,
    )

    decision = matcher.match(
        Path("song.flac"),
        AudioMetadata(
            title="Song",
            artist="Artist",
            album="Album",
            source="tags",
        ),
    )

    assert decision.action == "Review"
    assert len(decision.review_candidates) == 1
    assert decision.review_candidates[0].recording_id == "candidate-1"
