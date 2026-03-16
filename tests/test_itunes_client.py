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
    def fake_get(self, *args, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr("app.itunes_client.requests.Session.get", fake_get)

    client = ItunesClient()
    candidates = client.search_recordings(
        AudioMetadata(title="Song", artist="Artist", album="Album"),
        limit=1,
    )

    assert len(candidates) == 1
    assert candidates[0].metadata.track_number == "3"
    assert candidates[0].metadata.disc_number == "1"


def test_itunes_client_uses_cache_for_identical_queries(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_get(self, *args, **kwargs):
        calls["count"] += 1
        return _FakeResponse()

    monkeypatch.setattr("app.itunes_client.requests.Session.get", fake_get)

    client = ItunesClient()
    metadata = AudioMetadata(title="Song", artist="Artist", album="Album")
    first = client.search_recordings(metadata, limit=1)
    second = client.search_recordings(metadata, limit=1)

    assert len(first) == 1
    assert len(second) == 1
    assert calls["count"] == 1
    assert first is not second
