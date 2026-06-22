"""Download history tracking — JSON persistence."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from mangataro.models import DownloadRecord


class History:
    """Download history with JSON persistence."""

    FILE_NAME = "download_history.json"

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path.cwd()
        self._path = data_dir / self.FILE_NAME
        self._entries: list[DownloadRecord] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = [DownloadRecord(**e) for e in data]
            except (json.JSONDecodeError, IOError):
                self._entries = []

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                [e.model_dump() for e in self._entries],
                f, indent=2, default=str,
            )

    def add(self, manga_id: str, manga_title: str, manga_slug: str,
            chapter_range: str, chapter_count: int = 0,
            export_format: str = "images", output_path: str = "",
            status: str = "success") -> DownloadRecord:
        record = DownloadRecord(
            manga_id=manga_id,
            manga_title=manga_title,
            manga_slug=manga_slug,
            chapter_range=chapter_range,
            chapter_count=chapter_count,
            export_format=export_format,
            output_path=output_path,
            timestamp=datetime.now().isoformat(),
            status=status,
        )
        self._entries.insert(0, record)
        self.save()
        return record

    def get_all(self, limit: int = 100) -> list[DownloadRecord]:
        return self._entries[:limit]

    def get_latest(self) -> Optional[DownloadRecord]:
        return self._entries[0] if self._entries else None

    def clear(self) -> None:
        self._entries.clear()
        self.save()
