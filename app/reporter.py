from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List

from app.config import AppConfig
from app.models import ProcessingResult


class ReportWriter:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def write_reports(self, results: Iterable[ProcessingResult]) -> None:
        result_objects = list(results)
        rows = [result.to_report_dict() for result in result_objects]
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(rows, self.config.report_json_path)
        self._write_csv(rows, self.config.report_csv_path)

        if self.config.export_unmatched_playlist:
            self._write_unmatched_playlist(result_objects, self.config.unmatched_playlist_path)

    @staticmethod
    def _write_json(rows: List[dict], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)

    @staticmethod
    def _write_csv(rows: List[dict], path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            fieldnames = [
                "original_path",
                "match_provider",
                "match_title",
                "match_artist",
                "match_album",
                "score_explanation",
                "detected_tags",
                "chosen_match",
                "confidence",
                "final_action",
                "destination_path",
                "reason",
                "notes",
                "tag_write_success",
                "transfer_success",
                "error",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                serializable_row = dict(row)
                serializable_row["detected_tags"] = json.dumps(
                    serializable_row["detected_tags"],
                    ensure_ascii=False,
                )
                serializable_row["chosen_match"] = json.dumps(
                    serializable_row["chosen_match"],
                    ensure_ascii=False,
                )
                serializable_row["notes"] = json.dumps(serializable_row["notes"], ensure_ascii=False)
                writer.writerow(serializable_row)

    def _write_unmatched_playlist(self, results: Iterable[ProcessingResult], path: Path) -> None:
        entries = []
        for result in results:
            if result.decision.action != "Unmatched":
                continue
            if self.config.is_dry_run or result.transfer_success is not True:
                entries.append(result.source_path)
            else:
                entries.append(result.destination_path or result.source_path)

        with path.open("w", encoding="utf-8") as handle:
            handle.write("#EXTM3U\n")
            for entry in entries:
                handle.write("{0}\n".format(entry))
