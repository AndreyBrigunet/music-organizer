import logging
from pathlib import Path

from app.main import maybe_resolve_review_decision, prompt_for_review_candidate
from app.models import AudioMetadata, CandidateMatch, MatchDecision


def test_interactive_review_selection_converts_review_to_matched(monkeypatch) -> None:
    selected_candidate = CandidateMatch(
        metadata=AudioMetadata(
            title="Noaptea pe la 3",
            artist="Satoshi & Carla's Dreams",
            album="Noaptea pe la 3",
            source="musicbrainz",
        ),
        confidence=0.88,
        source="musicbrainz",
        recording_id="mbid-1",
        query_metadata=AudioMetadata(
            title="Noaptea pe la 3",
            artist="Satoshi & Carla's Dreams",
            source="filename",
        ),
    )
    decision = MatchDecision(
        action="Review",
        detected_metadata=AudioMetadata(
            title="Noaptea pe la 3",
            artist="Satoshi & Carla's Dreams",
            source="filename",
        ),
        metadata_to_write=None,
        confidence=0.88,
        chosen_match=selected_candidate,
        reason="Candidate exists but confidence is below the acceptance threshold.",
        notes=["low_confidence_candidate"],
        review_candidates=[selected_candidate],
        provider_trace=["musicbrainz: trying", "musicbrainz: best 0.88 (below threshold); trying next provider"],
    )

    monkeypatch.setattr("app.main.supports_interactive_review", lambda: True)
    monkeypatch.setattr("app.main.prompt_for_review_candidate", lambda *args, **kwargs: selected_candidate)

    resolved = maybe_resolve_review_decision(
        audio_path=Path("song.flac"),
        raw_metadata=AudioMetadata(
            title="Noaptea pe la 3",
            artist="Satoshi & Carla's Dreams",
            album="PrimeMusic.ru December 2014",
            genre="Prime Music",
            track_number="1",
            source="tags",
        ),
        decision=decision,
        logger=logging.getLogger("test_interactive_review"),
        interactive_review=True,
    )

    assert resolved.action == "Matched"
    assert resolved.chosen_match is selected_candidate
    assert resolved.metadata_to_write is not None
    assert resolved.metadata_to_write.track_number == "1"
    assert resolved.metadata_to_write.album == "Noaptea pe la 3"
    assert resolved.metadata_to_write.genre is None
    assert "user_selected_candidate" in resolved.notes
    assert resolved.provider_trace == decision.provider_trace


def test_interactive_review_can_be_skipped(monkeypatch) -> None:
    candidate = CandidateMatch(
        metadata=AudioMetadata(title="Song", artist="Artist", source="discogs"),
        confidence=0.70,
        source="discogs",
    )
    decision = MatchDecision(
        action="Review",
        detected_metadata=AudioMetadata(title="Song", artist="Artist", source="filename"),
        metadata_to_write=None,
        confidence=0.70,
        chosen_match=candidate,
        reason="Multiple similar candidates were found; manual review required.",
        notes=["ambiguous_online_match"],
        review_candidates=[candidate],
    )

    monkeypatch.setattr("app.main.supports_interactive_review", lambda: True)
    monkeypatch.setattr("app.main.prompt_for_review_candidate", lambda *args, **kwargs: None)

    resolved = maybe_resolve_review_decision(
        audio_path=Path("song.flac"),
        raw_metadata=AudioMetadata(title="Song", artist="Artist", source="tags"),
        decision=decision,
        logger=logging.getLogger("test_interactive_review"),
        interactive_review=True,
    )

    assert resolved is decision


def test_interactive_review_pauses_and_resumes_progress(monkeypatch) -> None:
    events: list[str] = []
    candidate = CandidateMatch(
        metadata=AudioMetadata(title="Song", artist="Artist", source="discogs"),
        confidence=0.70,
        source="discogs",
    )
    decision = MatchDecision(
        action="Review",
        detected_metadata=AudioMetadata(title="Song", artist="Artist", source="filename"),
        metadata_to_write=None,
        confidence=0.70,
        chosen_match=candidate,
        reason="Multiple similar candidates were found; manual review required.",
        notes=["ambiguous_online_match"],
        review_candidates=[candidate],
    )

    monkeypatch.setattr("app.main.supports_interactive_review", lambda: True)

    def fake_prompt(*args, **kwargs):
        events.append("prompt")
        return None

    monkeypatch.setattr("app.main.prompt_for_review_candidate", fake_prompt)

    resolved = maybe_resolve_review_decision(
        audio_path=Path("song.flac"),
        raw_metadata=AudioMetadata(title="Song", artist="Artist", source="tags"),
        decision=decision,
        logger=logging.getLogger("test_interactive_review"),
        interactive_review=True,
        pause_progress=lambda: events.append("pause"),
        resume_progress=lambda: events.append("resume"),
    )

    assert resolved is decision
    assert events == ["pause", "prompt", "resume"]


def test_interactive_review_does_not_recheck_terminal_support(monkeypatch) -> None:
    selected_candidate = CandidateMatch(
        metadata=AudioMetadata(title="Song", artist="Artist", source="discogs"),
        confidence=0.72,
        source="discogs",
    )
    decision = MatchDecision(
        action="Review",
        detected_metadata=AudioMetadata(title="Song", artist="Artist", source="filename"),
        metadata_to_write=None,
        confidence=0.72,
        chosen_match=selected_candidate,
        reason="Multiple similar candidates were found; manual review required.",
        notes=["ambiguous_online_match"],
        review_candidates=[selected_candidate],
    )

    monkeypatch.setattr("app.main.supports_interactive_review", lambda: False)
    monkeypatch.setattr("app.main.prompt_for_review_candidate", lambda *args, **kwargs: selected_candidate)

    resolved = maybe_resolve_review_decision(
        audio_path=Path("song.flac"),
        raw_metadata=AudioMetadata(title="Song", artist="Artist", source="tags"),
        decision=decision,
        logger=logging.getLogger("test_interactive_review"),
        interactive_review=True,
    )

    assert resolved.action == "Matched"
    assert resolved.chosen_match is selected_candidate


def test_prompt_for_review_candidate_accepts_zero_as_keep_in_review(monkeypatch) -> None:
    candidate = CandidateMatch(
        metadata=AudioMetadata(title="Song", artist="Artist", album="Album", source="discogs"),
        confidence=0.72,
        source="discogs",
    )
    monkeypatch.setattr("builtins.input", lambda _: "0")

    selected = prompt_for_review_candidate(
        audio_path=Path("song.flac"),
        detected_metadata=AudioMetadata(title="Song", artist="Artist", source="filename"),
        candidates=[candidate],
    )

    assert selected is None
