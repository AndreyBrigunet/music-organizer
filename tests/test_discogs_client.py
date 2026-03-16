import logging

from app.discogs_client import DiscogsClient
from app.models import AudioMetadata


class _SuccessResponse:
    status_code = 200
    text = ""

    def json(self) -> dict:
        return {
            "results": [
                {
                    "id": 123,
                    "master_id": 456,
                    "title": "Carla's Dreams - Antiexemplu",
                    "year": 2017,
                    "genre": ["Pop"],
                }
            ]
        }


class _ForbiddenResponse:
    status_code = 403
    text = '{"message":"You are not allowed to access this resource."}'

    def json(self) -> dict:
        return {
            "message": "You are not allowed to access this resource.",
        }


def test_discogs_client_requires_user_token() -> None:
    client = DiscogsClient(user_token=None)

    assert client.enabled is False
    assert client.status_reason == "missing DISCOGS_USER_TOKEN"


def test_discogs_client_parses_release_search_result(monkeypatch) -> None:
    captured = {}

    def fake_get(self, url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _SuccessResponse()

    monkeypatch.setattr("app.discogs_client.requests.Session.get", fake_get)

    client = DiscogsClient(user_token="token")
    candidates = client.search_recordings(
        AudioMetadata(title="Imperfect", artist="Carla's Dreams"),
        limit=7,
    )

    assert len(candidates) == 1
    assert candidates[0].source == "discogs"
    assert candidates[0].metadata.title == "Imperfect"
    assert candidates[0].metadata.artist == "Carla's Dreams"
    assert candidates[0].metadata.album == "Antiexemplu"
    assert candidates[0].recording_id == "123"
    assert candidates[0].release_id == "456"
    assert captured["url"] == client.api_url
    assert captured["params"]["track"] == "Imperfect"
    assert captured["params"]["artist"] == "Carla's Dreams"
    assert captured["params"]["type"] == "release"
    assert captured["params"]["per_page"] == 5
    assert captured["headers"]["Authorization"] == "Discogs token=token"


def test_discogs_client_logs_structured_error(monkeypatch, caplog) -> None:
    def fake_get(self, *args, **kwargs):
        return _ForbiddenResponse()

    monkeypatch.setattr("app.discogs_client.requests.Session.get", fake_get)

    client = DiscogsClient(user_token="token", logger=logging.getLogger("test_discogs"))
    with caplog.at_level(logging.WARNING, logger="test_discogs"):
        results = client.search_recordings(
            AudioMetadata(title="Imperfect", artist="Carla's Dreams"),
            limit=5,
        )

    assert results == []
    assert client.enabled is False
    assert client.status_reason == "invalid DISCOGS_USER_TOKEN"
    assert '"provider": "discogs"' in caplog.text
    assert '"status_code": 403' in caplog.text


def test_discogs_client_uses_cache_for_identical_queries(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_get(self, *args, **kwargs):
        calls["count"] += 1
        return _SuccessResponse()

    monkeypatch.setattr("app.discogs_client.requests.Session.get", fake_get)

    client = DiscogsClient(user_token="token")
    metadata = AudioMetadata(title="Imperfect", artist="Carla's Dreams")
    first = client.search_recordings(metadata, limit=5)
    second = client.search_recordings(metadata, limit=5)

    assert len(first) == 1
    assert len(second) == 1
    assert calls["count"] == 1
    assert first is not second
