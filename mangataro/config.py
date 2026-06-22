"""Configuration management — JSON settings in project root."""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

SETTINGS_FILE = "settings.json"


@dataclass
class DownloadConfig:
    """Download-specific settings."""
    max_concurrent_chapters: int = 4
    max_concurrent_images: int = 8
    max_retries: int = 3
    retry_delay: float = 2.0
    timeout: int = 30
    max_concurrent_downloads: int = 3


@dataclass
class QualityConfig:
    """Quality and post-processing settings."""
    default: str = "original"
    convert_webp: bool = True
    jpeg_quality: int = 95
    delete_images_after_export: bool = False


@dataclass
class GUIConfig:
    """GUI-specific settings."""
    theme: str = "dark"
    sidebar_collapsed: bool = False
    show_thumbnails: bool = True


@dataclass
class Config:
    """Application configuration with JSON persistence.

    Priority (last wins):
      1. Built-in defaults
      2. settings.json in project root
      3. Environment variables (MANGATARO_*)
    """
    output_dir: str = "."
    default_format: str = "images"
    default_language: str = "en"
    check_updates: bool = True
    download: DownloadConfig = field(default_factory=DownloadConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    gui: GUIConfig = field(default_factory=GUIConfig)

    @classmethod
    def load(cls, settings_path: Optional[Path] = None) -> "Config":
        """Load config with priority: defaults → JSON → env vars."""
        config = cls()

        # Find settings.json
        if settings_path is None:
            settings_path = Path.cwd() / SETTINGS_FILE
            if not settings_path.exists():
                # Also look next to the package
                pkg_path = Path(__file__).parent.parent / SETTINGS_FILE
                if pkg_path.exists():
                    settings_path = pkg_path

        if settings_path.exists():
            try:
                with open(settings_path, encoding="utf-8") as f:
                    data = json.load(f)
                config._merge(data)
            except (json.JSONDecodeError, IOError):
                pass

        # Env var overrides
        import os
        for key, val in os.environ.items():
            if key.startswith("MANGATARO_"):
                config._apply_env(key, val)

        return config

    def save(self, path: Optional[Path] = None) -> None:
        """Save current config to JSON file."""
        if path is None:
            path = Path.cwd() / SETTINGS_FILE
        data = asdict(self)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def _merge(self, data: dict) -> None:
        """Recursively merge dict into this config."""
        for key, val in data.items():
            if hasattr(self, key):
                existing = getattr(self, key)
                if isinstance(existing, (DownloadConfig, QualityConfig, GUIConfig)):
                    if isinstance(val, dict):
                        for sk, sv in val.items():
                            if hasattr(existing, sk):
                                setattr(existing, sk, sv)
                else:
                    setattr(self, key, val)

    def _apply_env(self, key: str, val: str) -> None:
        """Apply a single env var override."""
        attr = key[len("MANGATARO_"):].lower()
        parts = attr.split("_", 1)
        if len(parts) == 2:
            section, subkey = parts
            section_map = {
                "download": self.download,
                "quality": self.quality,
                "gui": self.gui,
            }
            if section in section_map and hasattr(section_map[section], subkey):
                current = getattr(section_map[section], subkey)
                if isinstance(current, bool):
                    setattr(section_map[section], subkey, val.lower() in ("1", "true", "yes"))
                elif isinstance(current, int):
                    setattr(section_map[section], subkey, int(val))
                elif isinstance(current, float):
                    setattr(section_map[section], subkey, float(val))
                else:
                    setattr(section_map[section], subkey, val)
