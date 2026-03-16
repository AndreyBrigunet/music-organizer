from app.lastfm_client import LastFmClient
from app.models import AudioMetadata


class _LastFmResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "results": {
                "trackmatches": {
                    "track": [
                        {
                            "name": "Song",
                            "artist": "Artist",
                            "listeners": "1200",
                        }
                    ]
                }
            }
        }


def test_lastfm_client_uses_cache_for_identical_queries(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_get(self, *args, **kwargs):
        calls["count"] += 1
        return _LastFmResponse()

    monkeypatch.setattr("app.lastfm_client.requests.Session.get", fake_get)

    client = LastFmClient(api_key="key")
    metadata = AudioMetadata(title="Song", artist="Artist")
    first = client.search_recordings(metadata, limit=5)
    second = client.search_recordings(metadata, limit=5)

    assert len(first) == 1
    assert len(second) == 1
    assert calls["count"] == 1
    assert first is not second
