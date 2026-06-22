"""Export pipeline — multiple output formats."""

import json
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from mangataro.config import Config


def export_images(images: list[bytes], output_dir: Path, filename: str = "images") -> Path:
    """Export images directly into output_dir (no extra subfolder)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for i, data in enumerate(images, 1):
        ext = _detect_ext(data)
        (output_dir / f"{i:04d}.{ext}").write_bytes(data)
    return output_dir


def export_cbz(images: list[bytes], output_dir: Path, filename: str = "chapter") -> Path:
    """Export as CBZ (Comic Book Zip)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{filename}.cbz"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, data in enumerate(images, 1):
            ext = _detect_ext(data)
            zf.writestr(f"{i:04d}.{ext}", data)
    return path


def export_zip(images: list[bytes], output_dir: Path, filename: str = "chapter") -> Path:
    """Export as plain ZIP."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{filename}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, data in enumerate(images, 1):
            ext = _detect_ext(data)
            zf.writestr(f"{i:04d}.{ext}", data)
    return path


def export_pdf(images: list[bytes], output_dir: Path, filename: str = "chapter") -> Path:
    """Export as PDF using Pillow."""
    from PIL import Image
    import io
    from concurrent.futures import ThreadPoolExecutor

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{filename}.pdf"

    def process_image(data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.load()  # Force decode in the worker thread
        return img

    with ThreadPoolExecutor() as executor:
        pil_images = list(executor.map(process_image, images))

    if pil_images:
        pil_images[0].save(path, save_all=True, append_images=pil_images[1:])
    return path


def _detect_ext(data: bytes) -> str:
    """Detect image extension from magic bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] in (b"\xff\xd8",):
        return "jpg"
    if data[:4] == b"RIFF":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "jpg"  # fallback


EXPORT_FORMATS = {
    "images": export_images,
    "cbz": export_cbz,
    "zip": export_zip,
    "pdf": export_pdf,
}

EXPORT_DESCRIPTIONS = {
    "images": "Raw image files in a folder",
    "cbz": "Comic Book Zip (standard manga format)",
    "zip": "Plain ZIP archive",
    "pdf": "Single PDF with all pages",
}


def export_chapter(
    images: list[bytes],
    output_dir: Path,
    manga_title: str,
    chapter_num: str,
    fmt: str = "images",
    delete_after: bool = False,
    config: Optional[Config] = None,
) -> Path:
    """Export a chapter's images in the specified format.

    Args:
        images: List of image bytes.
        output_dir: Root output directory.
        manga_title: Sanitized manga title for subfolder.
        chapter_num: Chapter number string.
        fmt: Export format (images/cbz/zip/pdf/folder).
        delete_after: Remove source images after export.
        config: Config for settings.

    Returns:
        Path to the exported file/folder.
    """
    safe_title = "".join(c for c in manga_title if c.isalnum() or c in " -_").strip()
    safe_title = safe_title.replace(" ", "_") or f"manga_{chapter_num}"
    ch_dir = output_dir / safe_title / f"Chapter_{chapter_num}"
    ch_dir.mkdir(parents=True, exist_ok=True)

    exporter = EXPORT_FORMATS.get(fmt, export_images)
    result = exporter(images, ch_dir, filename=f"Chapter_{chapter_num}")

    # If format is archive/PDF and user wants to keep source images, export them too
    if fmt not in ("images", "folder") and not delete_after:
        export_images(images, ch_dir)

    # Cleanup if requested
    if delete_after and result.exists():
        for img_path in ch_dir.iterdir():
            if img_path.is_file() and img_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                img_path.unlink()

    return result
