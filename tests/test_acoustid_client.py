import logging
from pathlib import Path

from app.acoustid_client import AcoustIdClient


def test_resolve_fpcalc_path_uses_project_tool_location() -> None:
    path = AcoustIdClient._resolve_fpcalc_path()
    assert path is not None
    assert Path(path).name.lower() == "fpcalc.exe"


def test_match_file_parses_raw_acoustid_response(monkeypatch) -> None:
    client = AcoustIdClient(api_key="key")

    def fake_fingerprint_file(*args, **kwargs):
        return 198.0, "abc123fingerprint"

    def fake_lookup(*args, **kwargs):
        return {"status": "ok", "results": ["ignored"]}

    def fake_parse_lookup_result(response):
        assert response["status"] == "ok"
        return iter([(0.91, "recording-id", "Song Title", "Artist Name")])

    monkeypatch.setattr("app.acoustid_client.acoustid.fingerprint_file", fake_fingerprint_file)
    monkeypatch.setattr("app.acoustid_client.acoustid.lookup", fake_lookup)
    monkeypatch.setattr("app.acoustid_client.acoustid.parse_lookup_result", fake_parse_lookup_result)

    matches = client.match_file(Path("track.flac"))

    assert len(matches) == 1
    assert matches[0].source == "acoustid"
    assert matches[0].metadata.title == "Song Title"
    assert matches[0].metadata.artist == "Artist Name"
    assert matches[0].recording_id == "recording-id"


def test_match_file_disables_client_after_invalid_api_key(monkeypatch) -> None:
    client = AcoustIdClient(api_key="key")

    def fake_fingerprint_file(*args, **kwargs):
        return 198.0, "abc123fingerprint"

    def fake_lookup(*args, **kwargs):
        return {
            "status": "error",
            "error": {
                "code": 4,
                "message": "invalid API key",
            },
        }

    monkeypatch.setattr("app.acoustid_client.acoustid.fingerprint_file", fake_fingerprint_file)
    monkeypatch.setattr("app.acoustid_client.acoustid.lookup", fake_lookup)

    matches = client.match_file(Path("track.flac"))

    assert matches == []
    assert client.enabled is False
    assert client.status_reason == "invalid ACOUSTID_API_KEY"


def test_match_file_logs_acoustid_request_and_response(monkeypatch, caplog) -> None:
    logger = logging.getLogger("test_acoustid")
    client = AcoustIdClient(api_key="abcdef123456", logger=logger)

    def fake_fingerprint_file(*args, **kwargs):
        return 198.0, "abc123fingerprint"

    def fake_lookup(*args, **kwargs):
        return {"status": "ok", "results": []}

    def fake_parse_lookup_result(response):
        return iter([])

    monkeypatch.setattr("app.acoustid_client.acoustid.fingerprint_file", fake_fingerprint_file)
    monkeypatch.setattr("app.acoustid_client.acoustid.lookup", fake_lookup)
    monkeypatch.setattr("app.acoustid_client.acoustid.parse_lookup_result", fake_parse_lookup_result)

    with caplog.at_level(logging.INFO, logger="test_acoustid"):
        matches = client.match_file(Path("track.flac"))

    assert matches == []
    assert "AcoustID request for track.flac" in caplog.text
    assert '"client": "abc...456"' in caplog.text
    assert '"fingerprint_length": 17' in caplog.text
    assert "AcoustID response for track.flac" in caplog.text
    assert '"status": "ok"' in caplog.text


def test_match_file_logs_bytes_fingerprint_without_crashing(monkeypatch, caplog) -> None:
    logger = logging.getLogger("test_acoustid_bytes")
    client = AcoustIdClient(api_key="abcdef123456", logger=logger)

    def fake_fingerprint_file(*args, **kwargs):
        return 198.0, b"abc123fingerprint"

    def fake_lookup(*args, **kwargs):
        return {"status": "ok", "results": []}

    def fake_parse_lookup_result(response):
        return iter([])

    monkeypatch.setattr("app.acoustid_client.acoustid.fingerprint_file", fake_fingerprint_file)
    monkeypatch.setattr("app.acoustid_client.acoustid.lookup", fake_lookup)
    monkeypatch.setattr("app.acoustid_client.acoustid.parse_lookup_result", fake_parse_lookup_result)

    with caplog.at_level(logging.INFO, logger="test_acoustid_bytes"):
        matches = client.match_file(Path("track.flac"))

    assert matches == []
    assert '"fingerprint_type": "bytes"' in caplog.text
    assert '"fingerprint_preview": "abc123fingerprint"' in caplog.text
