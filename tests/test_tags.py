from pathlib import Path

from app.models import AudioMetadata
from app.tags import write_metadata


class _FakeEasyAudio:
    def __init__(self) -> None:
        self.tags = {}
        self.saved = False

    def add_tags(self) -> None:
        self.tags = {}

    def save(self) -> None:
        self.saved = True


class _FakeID3Tags:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.added: list[object] = []

    def delall(self, key: str) -> None:
        self.deleted.append(key)

    def add(self, frame: object) -> None:
        self.added.append(frame)


class _FakeRawAudio:
    def __init__(self) -> None:
        self.tags = _FakeID3Tags()
        self.saved = False

    def add_tags(self) -> None:
        self.tags = _FakeID3Tags()

    def save(self) -> None:
        self.saved = True


class _FakeTXXX:
    def __init__(self, encoding: int, desc: str, text: list[str]) -> None:
        self.encoding = encoding
        self.desc = desc
        self.text = text


def test_write_metadata_writes_year_only_from_provider_date(monkeypatch) -> None:
    easy_audio = _FakeEasyAudio()
    raw_audio = _FakeRawAudio()

    def fake_mutagen_file(path: Path, easy: bool = False):
        return easy_audio if easy else raw_audio

    monkeypatch.setattr("app.tags.MutagenFile", fake_mutagen_file)
    monkeypatch.setattr("app.tags.TXXX", _FakeTXXX)

    write_metadata(
        Path("song.mp3"),
        AudioMetadata(
            title="Song",
            artist="Artist",
            date="2014-12-03",
            source="itunes",
        ),
    )

    assert easy_audio.tags["date"] == ["2014"]
    assert easy_audio.saved is True
    assert raw_audio.saved is False


def test_write_metadata_writes_musicbrainz_ids_for_mp3(monkeypatch) -> None:
    easy_audio = _FakeEasyAudio()
    raw_audio = _FakeRawAudio()

    def fake_mutagen_file(path: Path, easy: bool = False):
        return easy_audio if easy else raw_audio

    monkeypatch.setattr("app.tags.MutagenFile", fake_mutagen_file)
    monkeypatch.setattr("app.tags.TXXX", _FakeTXXX)

    write_metadata(
        Path("song.mp3"),
        AudioMetadata(
            title="Song",
            artist="Artist",
            musicbrainz_recording_id="recording-id",
            musicbrainz_release_id="release-id",
            musicbrainz_artist_id="artist-id",
            musicbrainz_album_artist_id="album-artist-id",
            source="musicbrainz",
        ),
    )

    assert raw_audio.saved is True
    assert raw_audio.tags.deleted == [
        "TXXX:MusicBrainz Track Id",
        "TXXX:MusicBrainz Album Id",
        "TXXX:MusicBrainz Artist Id",
        "TXXX:MusicBrainz Album Artist Id",
    ]
    assert [(frame.desc, frame.text) for frame in raw_audio.tags.added] == [
        ("MusicBrainz Track Id", ["recording-id"]),
        ("MusicBrainz Album Id", ["release-id"]),
        ("MusicBrainz Artist Id", ["artist-id"]),
        ("MusicBrainz Album Artist Id", ["album-artist-id"]),
    ]
