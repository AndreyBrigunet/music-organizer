from app.models import AudioMetadata, MatchDecision


def test_report_dict_exposes_match_provider_from_online_source() -> None:
    decision = MatchDecision(
        action="Matched",
        detected_metadata=AudioMetadata(title="Song", artist="Artist"),
        metadata_to_write=AudioMetadata(title="Song", artist="Artist", album="Album", source="musicbrainz"),
        confidence=0.95,
        chosen_match=None,
        reason="matched by tags",
        notes=["matched_by_tags"],
    )

    report = decision.to_report_dict("input.flac", "output.flac")

    assert report["match_provider"] == "tags"
    assert report["match_title"] == "Song"
    assert report["match_artist"] == "Artist"
    assert report["match_album"] == "Album"
    assert report["score_explanation"] == "Organized using existing local tags because no online match exceeded the confidence threshold."
