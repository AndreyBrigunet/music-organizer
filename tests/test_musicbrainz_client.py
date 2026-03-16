from app.musicbrainz_client import MusicBrainzClient


def test_recording_to_candidate_uses_ext_score_and_track_number() -> None:
    client = MusicBrainzClient()
    candidate = client._recording_to_candidate(
        {
            "id": "recording-id",
            "ext:score": "100",
            "title": "Noaptea pe la 3",
            "artist-credit-phrase": "Satoshi & Carla’s Dreams",
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
