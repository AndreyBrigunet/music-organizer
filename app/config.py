from __future__ import annotations

import os
import string
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Set, Tuple

from dotenv import load_dotenv


APP_NAME = "music-organizer"
APP_VERSION = "1.0.0"
SUPPORTED_EXTENSIONS: Set[str] = {".mp3", ".flac", ".m4a", ".opus", ".ogg", ".wav"}
DEFAULT_PROVIDER_ORDER: Tuple[str, ...] = ("musicbrainz", "itunes", "deezer", "lastfm", "discogs")
SUPPORTED_SEARCH_PROVIDERS: Set[str] = set(DEFAULT_PROVIDER_ORDER)
DEFAULT_MATCHED_PATH_TEMPLATE = "{artist}/{album}/{track_number} - {title}.{ext}"
SUPPORTED_MATCHED_TEMPLATE_FIELDS: Set[str] = {"artist", "album", "track_number", "title", "ext"}


class OperationMode(str, Enum):
    DRY_RUN = "dry-run"
    COPY = "copy"
    MOVE = "move"


@dataclass(frozen=True)
class AppConfig:
    input_dir: Path
    output_dir: Path
    mode: OperationMode
    min_confidence: float = 0.85
    export_unmatched_playlist: bool = False
    acoustid_api_key: Optional[str] = None
    lastfm_api_key: Optional[str] = None
    discogs_user_token: Optional[str] = None
    musicbrainz_limit: int = 5
    provider_order: Tuple[str, ...] = DEFAULT_PROVIDER_ORDER
    matched_path_template: str = DEFAULT_MATCHED_PATH_TEMPLATE

    @property
    def logs_path(self) -> Path:
        return self.output_dir / "logs" / "app.log"

    @property
    def report_csv_path(self) -> Path:
        return self.output_dir / "report.csv"

    @property
    def report_json_path(self) -> Path:
        return self.output_dir / "report.json"

    @property
    def unmatched_playlist_path(self) -> Path:
        return self.output_dir / "unmatched.m3u"

    @property
    def is_dry_run(self) -> bool:
        return self.mode == OperationMode.DRY_RUN


def build_config(
    input_dir: Path,
    output_dir: Path,
    dry_run: bool,
    copy_mode: bool,
    move_mode: bool,
    min_confidence: float,
    export_unmatched_playlist: bool,
) -> AppConfig:
    load_dotenv()
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    if copy_mode and move_mode:
        raise ValueError("--copy and --move are mutually exclusive.")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("--min-confidence must be between 0.0 and 1.0.")
    if not input_dir.exists():
        raise ValueError("Input directory does not exist: {0}".format(input_dir))
    if not input_dir.is_dir():
        raise ValueError("Input path must be a directory: {0}".format(input_dir))
    if output_dir == input_dir:
        raise ValueError("--output must be different from --input.")
    if _is_relative_to(output_dir, input_dir):
        raise ValueError("--output must not be inside --input.")

    resolved_mode = OperationMode.DRY_RUN
    if move_mode:
        resolved_mode = OperationMode.MOVE
    elif copy_mode:
        resolved_mode = OperationMode.COPY
    elif not dry_run:
        resolved_mode = OperationMode.COPY

    provider_order = _parse_provider_order(os.getenv("SEARCH_PROVIDER_ORDER"))
    matched_path_template = _parse_matched_path_template(os.getenv("MATCHED_PATH_TEMPLATE"))

    return AppConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        mode=resolved_mode,
        min_confidence=min_confidence,
        export_unmatched_playlist=export_unmatched_playlist,
        acoustid_api_key=os.getenv("ACOUSTID_API_KEY"),
        lastfm_api_key=os.getenv("LASTFM_API_KEY"),
        discogs_user_token=os.getenv("DISCOGS_USER_TOKEN"),
        provider_order=provider_order,
        matched_path_template=matched_path_template,
    )


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _parse_provider_order(raw_value: Optional[str]) -> Tuple[str, ...]:
    if not raw_value or not raw_value.strip():
        return DEFAULT_PROVIDER_ORDER

    provider_names = tuple(
        part.strip().casefold()
        for part in raw_value.split(",")
        if part.strip()
    )
    if not provider_names:
        return DEFAULT_PROVIDER_ORDER

    invalid = [provider for provider in provider_names if provider not in SUPPORTED_SEARCH_PROVIDERS]
    if invalid:
        raise ValueError(
            "SEARCH_PROVIDER_ORDER contains unsupported providers: {0}. Supported values: {1}".format(
                ", ".join(invalid),
                ", ".join(DEFAULT_PROVIDER_ORDER),
            )
        )

    deduplicated = tuple(dict.fromkeys(provider_names))
    return deduplicated


def _parse_matched_path_template(raw_value: Optional[str]) -> str:
    template = raw_value.strip() if raw_value and raw_value.strip() else DEFAULT_MATCHED_PATH_TEMPLATE

    normalized_template = template.replace("\\", "/")
    template_path = Path(normalized_template)
    if template_path.is_absolute() or template_path.drive:
        raise ValueError("MATCHED_PATH_TEMPLATE must be a relative path template.")
    if normalized_template.startswith("/") or normalized_template.startswith("./") or normalized_template.startswith("../"):
        raise ValueError("MATCHED_PATH_TEMPLATE must be a relative path template.")
    if ".." in template_path.parts:
        raise ValueError("MATCHED_PATH_TEMPLATE must not contain '..' path segments.")

    formatter = string.Formatter()
    fields: Set[str] = set()
    for _, field_name, _, _ in formatter.parse(template):
        if not field_name:
            continue
        field_key = field_name.split("!", 1)[0].split(":", 1)[0]
        fields.add(field_key)

    invalid_fields = sorted(field for field in fields if field not in SUPPORTED_MATCHED_TEMPLATE_FIELDS)
    if invalid_fields:
        raise ValueError(
            "MATCHED_PATH_TEMPLATE contains unsupported fields: {0}. Supported fields: {1}".format(
                ", ".join(invalid_fields),
                ", ".join(sorted(SUPPORTED_MATCHED_TEMPLATE_FIELDS)),
            )
        )

    if "{title}" not in template or "{ext}" not in template:
        raise ValueError("MATCHED_PATH_TEMPLATE must include at least {title} and {ext}.")

    return template
