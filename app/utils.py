from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
WHITESPACE_RE = re.compile(r"\s+")
TRACK_NUMBER_RE = re.compile(r"(?P<number>\d{1,3})")
ARTIST_SEPARATOR_RE = re.compile(
    r"\s*(?:;|,|&|\bfeat(?:uring)?\.?\b|\bft\.?\b|\bx\b)\s*",
    re.IGNORECASE,
)
PATH_PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201B": "'",
        "\u02BC": "'",
        "\u0060": "'",
        "\u00B4": "'",
    }
)
RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = normalized.replace("\u0000", "")
    normalized = WHITESPACE_RE.sub(" ", normalized)
    return normalized or None


def normalize_for_compare(value: Optional[str]) -> str:
    cleaned = normalize_text(value)
    if not cleaned:
        return ""
    lowered = cleaned.casefold()
    lowered = strip_diacritics(lowered)
    lowered = re.sub(r"[^\w\s]+", " ", lowered)
    lowered = WHITESPACE_RE.sub(" ", lowered)
    return lowered.strip()


def strip_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def split_artist_names(value: Optional[str]) -> list[str]:
    cleaned = normalize_text(value)
    if not cleaned:
        return []
    parts = ARTIST_SEPARATOR_RE.split(cleaned)
    normalized_parts = [normalize_for_compare(part) for part in parts if normalize_for_compare(part)]
    deduplicated = list(dict.fromkeys(normalized_parts))
    return sorted(deduplicated)


def split_artist_display_names(value: Optional[str]) -> list[str]:
    cleaned = normalize_text(value)
    if not cleaned:
        return []
    parts = ARTIST_SEPARATOR_RE.split(cleaned)
    normalized_parts = [normalize_text(part) for part in parts if normalize_text(part)]
    return list(dict.fromkeys(part for part in normalized_parts if part))


def normalize_artist_text(value: Optional[str]) -> Optional[str]:
    artists = split_artist_display_names(value)
    if artists:
        return " & ".join(artists)
    return normalize_text(value)


def normalize_artist_for_compare(value: Optional[str]) -> str:
    artists = split_artist_names(value)
    if artists:
        return " | ".join(artists)
    return normalize_for_compare(value)


def artist_similarity(a: Optional[str], b: Optional[str]) -> float:
    first_artists = split_artist_names(a)
    second_artists = split_artist_names(b)
    if not first_artists and not second_artists:
        return 1.0
    if not first_artists or not second_artists:
        return 0.0

    first_set = set(first_artists)
    second_set = set(second_artists)
    if first_set == second_set:
        return 1.0

    overlap_ratio = len(first_set & second_set) / max(len(first_set), len(second_set))
    sequence_ratio = SequenceMatcher(None, " | ".join(first_artists), " | ".join(second_artists)).ratio()
    return max(overlap_ratio, sequence_ratio)


def similarity(a: Optional[str], b: Optional[str]) -> float:
    first = normalize_for_compare(a)
    second = normalize_for_compare(b)
    if not first and not second:
        return 1.0
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    return SequenceMatcher(None, first, second).ratio()


def sanitize_path_component(value: str, fallback: str = "Unknown") -> str:
    cleaned = normalize_text(value) or fallback
    cleaned = cleaned.translate(PATH_PUNCTUATION_TRANSLATION)
    cleaned = INVALID_WINDOWS_CHARS.sub("_", cleaned)
    cleaned = cleaned.rstrip(" .")
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = fallback
    if cleaned.upper() in RESERVED_WINDOWS_NAMES:
        cleaned = cleaned + "_"
    return cleaned


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name("{0} ({1}){2}".format(path.stem, counter, path.suffix))
        if not candidate.exists():
            return candidate
        counter += 1


def safe_relative_path(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return Path(path.name)


def sanitize_relative_path(path: Path) -> Path:
    return Path(*[sanitize_path_component(part) for part in path.parts])


def format_track_number(value: Optional[str], default: str = "00") -> str:
    if not value:
        return default
    match = TRACK_NUMBER_RE.search(value)
    if not match:
        return default
    number = int(match.group("number"))
    return "{0:02d}".format(number)


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def setup_logging(log_file: Path, verbose: bool = False, console: Optional[Console] = None) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("music_organizer")
    logger.setLevel(logging.INFO)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if verbose:
        console_handler = RichHandler(
            console=console,
            show_time=False,
            show_path=False,
            markup=False,
            rich_tracebacks=False,
        )
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console_handler)

    logger.propagate = False
    return logger
