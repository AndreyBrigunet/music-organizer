import logging

from app.deezer_client import DeezerClient
from app.models import AudioMetadata


class _SuccessResponse:
    status_code = 200
    text = ""

    def json(self) -> dict:
        return {
            "data": [
                {
                    "id": 123,
                    "title": "Noaptea pe la 3",
                    "track_position": 1,
                    "disk_number": 1,
                    "release_date": "2023-05-24",
                    "rank": 987654,
                    "artist": {
                        "id": 456,
                        "name": "Satoshi & Carla's Dreams",
                    },
                    "album": {
                        "id": 789,
                        "title": "Noaptea pe la 3",
                    },
                }
            ]
        }


class _ApiErrorResponse:
    status_code = 200
    text = '{"error":{"type":"Exception","message":"Quota exceeded","code":4}}'

    def json(self) -> dict:
        return {
            "error": {
                "type": "Exception",
                "message": "Quota exceeded",
                "code": 4,
            }
        }


def test_deezer_client_parses_search_result(monkeypatch) -> None:
    captured = {}

    def fake_get(self, url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _SuccessResponse()

    monkeypatch.setattr("app.deezer_client.requests.Session.get", fake_get)

    client = DeezerClient()
    candidates = client.search_recordings(
        AudioMetadata(title="Noaptea pe la 3", artist="Satoshi & Carla's Dreams", album="Noaptea pe la 3"),
        limit=5,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source == "deezer"
    assert candidate.metadata.title == "Noaptea pe la 3"
    assert candidate.metadata.artist == "Satoshi & Carla's Dreams"
    assert candidate.metadata.album == "Noaptea pe la 3"
    assert candidate.metadata.track_number == "1"
    assert candidate.metadata.disc_number == "1"
    assert candidate.metadata.date == "2023-05-24"
    assert candidate.recording_id == "123"
    assert candidate.release_id == "789"
    assert captured["url"] == client.api_url
    assert 'track:"Noaptea pe la 3"' in captured["params"]["q"]
    assert 'artist:"Satoshi & Carla\'s Dreams"' in captured["params"]["q"]


def test_deezer_client_uses_cache_for_identical_queries(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_get(self, *args, **kwargs):
        calls["count"] += 1
        return _SuccessResponse()

    monkeypatch.setattr("app.deezer_client.requests.Session.get", fake_get)

    client = DeezerClient()
    metadata = AudioMetadata(title="Song", artist="Artist", album="Album")
    first = client.search_recordings(metadata, limit=5)
    second = client.search_recordings(metadata, limit=5)

    assert len(first) == 1
    assert len(second) == 1
    assert calls["count"] == 1
    assert first is not second


def test_deezer_client_logs_api_error(monkeypatch, caplog) -> None:
    def fake_get(self, *args, **kwargs):
        return _ApiErrorResponse()

    monkeypatch.setattr("app.deezer_client.requests.Session.get", fake_get)

    client = DeezerClient(logger=logging.getLogger("test_deezer"))
    with caplog.at_level(logging.WARNING, logger="test_deezer"):
        results = client.search_recordings(
            AudioMetadata(title="Song", artist="Artist"),
            limit=5,
        )

    assert results == []
    assert '"provider": "deezer"' in caplog.text
    assert '"message": "Quota exceeded"' in caplog.text
