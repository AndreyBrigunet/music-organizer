from app.musicbrainz_client import MusicBrainzClient
from app.models import AudioMetadata


def test_recording_to_candidate_uses_ext_score_and_track_number() -> None:
    client = MusicBrainzClient()
    candidate = client._recording_to_candidate(
        {
            "id": "recording-id",
            "ext:score": "100",
            "title": "Noaptea pe la 3",
            "artist-credit-phrase": "Satoshi & Carla’s Dreams",
            "artist-credit": [
                {
                    "artist": {
                        "id": "artist-id-1",
                    }
                }
            ],
            "release-list": [
                {
                    "id": "release-id",
                    "title": "Noaptea pe la 3",
                    "date": "2023-05-24",
                    "medium-list": [
                        {
                            "track-list": [
                                {"number": "1"},
                            ]
                        }
                    ],
                }
            ],
        }
    )

    assert candidate.raw_score == 1.0
    assert candidate.metadata.track_number == "1"
    assert candidate.metadata.musicbrainz_recording_id == "recording-id"
    assert candidate.metadata.musicbrainz_release_id == "release-id"
    assert candidate.metadata.musicbrainz_artist_id == "artist-id-1"


def test_search_recordings_uses_cache_for_identical_queries(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_search_recordings(**kwargs):
        calls["count"] += 1
        return {
            "recording-list": [
                {
                    "id": "recording-id",
                    "ext:score": "100",
                    "title": "Noaptea pe la 3",
                    "artist-credit-phrase": "Satoshi & Carla's Dreams",
                    "release-list": [],
                }
            ]
        }

    monkeypatch.setattr("app.musicbrainz_client.musicbrainzngs.search_recordings", fake_search_recordings)

    client = MusicBrainzClient()
    metadata = AudioMetadata(title="Noaptea pe la 3", artist="Satoshi & Carla's Dreams")
    first = client.search_recordings(metadata, limit=5)
    second = client.search_recordings(metadata, limit=5)

    assert len(first) == 1
    assert len(second) == 1
    assert calls["count"] == 1
    assert first is not second
