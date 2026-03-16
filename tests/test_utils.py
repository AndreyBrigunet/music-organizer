from pathlib import Path

from app.utils import (
    artist_similarity,
    format_track_number,
    normalize_artist_for_compare,
    normalize_for_compare,
    sanitize_path_component,
    sanitize_relative_path,
)


def test_sanitize_path_component_replaces_invalid_windows_characters() -> None:
    assert sanitize_path_component('A:Song*Name?') == "A_Song_Name_"


def test_sanitize_reserved_windows_name() -> None:
    assert sanitize_path_component("CON") == "CON_"


def test_sanitize_relative_path_handles_every_component() -> None:
    sanitized = sanitize_relative_path(Path("Artist:Name/Album?/Track*.mp3"))
    assert sanitized == Path("Artist_Name/Album_/Track_.mp3")


def test_format_track_number_zero_pads_numeric_values() -> None:
    assert format_track_number("3/12") == "03"


def test_sanitize_path_component_normalizes_smart_apostrophes() -> None:
    assert sanitize_path_component("Carla’s Dreams") == "Carla's Dreams"


def test_normalize_for_compare_strips_diacritics_for_matching() -> None:
    assert normalize_for_compare("În Ochii Tăi") == "in ochii tai"


def test_normalize_artist_for_compare_unifies_artist_separators() -> None:
    assert normalize_artist_for_compare("Magnat; Feoctist x Satoshi") == "feoctist | magnat | satoshi"


def test_artist_similarity_handles_separator_variants() -> None:
    assert artist_similarity("Magnat; Feoctist", "Feoctist & Magnat") == 1.0
