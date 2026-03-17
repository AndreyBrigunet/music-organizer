from __future__ import annotations

import shutil
import stat
from pathlib import Path
from typing import Set

from app.config import AppConfig, OperationMode
from app.models import MatchDecision
from app.utils import (
    format_track_number,
    sanitize_path_component,
    sanitize_relative_path,
    safe_relative_path,
)


class LibraryMover:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._reserved_destinations: Set[str] = set()

    def plan_destination(self, source_path: Path, decision: MatchDecision) -> Path:
        suffix = source_path.suffix.lower()
        if decision.action == "Matched" and decision.metadata_to_write:
            metadata = decision.metadata_to_write
            artist = metadata.album_artist or metadata.artist or "Unknown Artist"
            album = metadata.album or "Singles"
            title = metadata.title or source_path.stem or "Unknown Title"
            track_number = format_track_number(metadata.track_number)
            relative = self._build_matched_relative_path(
                artist=artist,
                album=album,
                track_number=track_number,
                title=title,
                ext=suffix.lstrip("."),
            )
            return self.config.output_dir / relative

        relative_source = sanitize_relative_path(
            safe_relative_path(source_path, self.config.input_dir)
        )
        folder = "Review" if decision.action == "Review" else "Unmatched"
        return self.config.output_dir / folder / relative_source

    def transfer(self, source_path: Path, planned_destination: Path) -> Path:
        final_destination = self._reserve_unique_destination(planned_destination)
        if self.config.mode == OperationMode.DRY_RUN:
            return final_destination

        final_destination.parent.mkdir(parents=True, exist_ok=True)
        if self.config.mode == OperationMode.COPY:
            shutil.copy2(source_path, final_destination)
        elif self.config.mode == OperationMode.MOVE:
            shutil.move(str(source_path), str(final_destination))
        self._ensure_destination_writable(final_destination)
        return final_destination

    def is_dry_run(self) -> bool:
        return self.config.mode == OperationMode.DRY_RUN

    def _reserve_unique_destination(self, path: Path) -> Path:
        candidate = path
        counter = 2
        while candidate.exists() or str(candidate) in self._reserved_destinations:
            candidate = path.with_name("{0} ({1}){2}".format(path.stem, counter, path.suffix))
            counter += 1
        self._reserved_destinations.add(str(candidate))
        return candidate

    def _build_matched_relative_path(
        self,
        artist: str,
        album: str,
        track_number: str,
        title: str,
        ext: str,
    ) -> Path:
        rendered = self.config.matched_path_template.format(
            artist=artist,
            album=album,
            track_number=track_number,
            title=title,
            ext=ext,
        ).replace("\\", "/")
        path_parts = [part for part in Path(rendered).parts if part not in {"", "."}]
        sanitized_parts = [sanitize_path_component(part) for part in path_parts]
        return Path("Matched", *sanitized_parts)

    def _ensure_destination_writable(self, path: Path) -> None:
        try:
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
        except FileNotFoundError:
            return
        except Exception:
            return
