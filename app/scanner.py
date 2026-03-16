from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence


class LibraryScanner:
    def __init__(self, supported_extensions: Sequence[str]) -> None:
        self.supported_extensions = {extension.lower() for extension in supported_extensions}

    def scan(self, input_dir: Path) -> Iterable[Path]:
        files = (
            path
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in self.supported_extensions
        )
        return sorted(files)
