from app.itunes_client import ItunesClient
from app.models import AudioMetadata


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "results": [
                {
                    "trackName": "Song",
                    "artistName": "Artist",
                    "collectionName": "Album",
                    "trackNumber": 3,
                    "discNumber": 1,
                    "releaseDate": "2024-01-01T08:00:00Z",
                    "primaryGenreName": "Pop",
                    "trackId": 123,
                    "collectionId": 456,
                }
            ]
        }


def test_itunes_client_parses_numeric_track_fields(monkeypatch) -> None:
    def fake_get(*args, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr("app.itunes_client.requests.get", fake_get)

    client = ItunesClient()
    candidates = client.search_recordings(
        AudioMetadata(title="Song", artist="Artist", album="Album"),
        limit=1,
    )

    assert len(candidates) == 1
    assert candidates[0].metadata.track_number == "3"
    assert candidates[0].metadata.disc_number == "1"
