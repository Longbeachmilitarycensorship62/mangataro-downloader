"""Core MangaTaro API engine — manga info, chapters, images."""

import hashlib
import re
import json
import time
import httpx
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, quote

from mangataro.models import MangaInfo, Chapter, ChapterImage, ChapterContent, ChapterListResponse

BASE = "https://mangataro.org"
IMAGE_CDN = "https://mangataro.yachts"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Re-use a single Client instance for connection pooling (Keep-Alive)
_client = httpx.Client(
    headers={"User-Agent": UA},
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
    follow_redirects=True,
)


# ── Low-level HTTP helpers ──────────────────────────────────────────────

def _http_get(url: str, headers: dict | None = None, timeout: int = 120) -> str:
    r = _client.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def _http_get_bytes(url: str, headers: dict | None = None, timeout: int = 120) -> bytes:
    r = _client.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.content


def _generate_token():
    """Generate authentication token for chapter list API."""
    ts = int(time.time())
    hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    secret = f"mng_ch_{hour}"
    h = hashlib.md5(f"{ts}{secret}".encode()).hexdigest()[:16]
    return h, ts


def _extract_json_ld(html: str) -> dict:
    """Extract JSON-LD structured data from HTML."""
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return {}


# ── Manga Info ──────────────────────────────────────────────────────────

def get_manga_info(manga_slug: str) -> MangaInfo:
    """Fetch manga metadata from HTML + JSON-LD."""
    url = f"{BASE}/manga/{quote(manga_slug)}"
    html = _http_get(url)

    id_match = re.search(r'data-manga-id="(\d+)"', html)
    manga_id = id_match.group(1) if id_match else ""

    ld = _extract_json_ld(html)

    title = ld.get("name", "").replace(" Manhwa | Read Online Free at MangaTaro", "") \
                              .replace(" Manga | Read Online Free at MangaTaro", "")
    description = ld.get("description", "")

    author_raw = ""
    author_ld = ld.get("author", {})
    if isinstance(author_ld, dict):
        author_raw = author_ld.get("name", "")
    elif isinstance(author_ld, str):
        author_raw = author_ld
    authors = [a.strip() for a in author_raw.split(",") if a.strip()] if author_raw else []

    status = ld.get("status", "")
    status_html = re.search(r'data-status="([^"]+)"', html)
    if status_html:
        status = status_html.group(1)

    views_match = re.search(r'view-info">([^<]+)', html)
    views = views_match.group(1).strip() if views_match else ""

    tags = re.findall(r'/tag/([a-zA-Z0-9-]+)(?:/|")', html)
    tags = list(dict.fromkeys(tags))

    genres_section = re.search(r'Genres</h4>\s*<div[^>]*>(.*?)</div>', html, re.DOTALL)
    genres = []
    if genres_section:
        genres = re.findall(r'>([^<]{2,})<', genres_section.group(1))
        genres = [g.strip() for g in genres if g.strip() and g.strip() not in ("div", "span")]

    # MAL info
    mal_score = mal_rank = mal_popularity = mal_members = ""
    mal_section = re.search(r'mal-info-section[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
    if mal_section:
        vals = re.findall(r'text-lg font-bold[^>]*>([^<]+)', mal_section.group(1), re.DOTALL)
        labels = re.findall(r'text-xs text-neutral-400">([^<]+)', mal_section.group(1))
        lm = dict(zip(labels, vals))
        mal_score = lm.get("MAL Score", "")
        mal_rank = lm.get("Rank", "")
        mal_popularity = lm.get("Popularity", "")
        mal_members = lm.get("Members", "")

    orig_title = ""
    alt_match = re.search(r'(?:Alt[^a]*Titles?|Alternative)[^<]*<[^>]*>[^<]*<[^>]*>([^<]+)', html)
    if alt_match:
        orig_title = alt_match.group(1).strip()

    cover = ld.get("image", "")

    return MangaInfo(
        id=manga_id,
        title=title,
        original_title=orig_title,
        slug=manga_slug,
        description=description,
        authors=authors,
        tags=tags,
        genres=genres,
        type=ld.get("genre", ""),
        status=status,
        total_chapters=ld.get("numberOfEpisodes", ""),
        views=views,
        cover=cover,
        date_published=ld.get("datePublished", ""),
        date_modified=ld.get("dateModified", ""),
        mal_score=mal_score,
        mal_rank=mal_rank,
        mal_popularity=mal_popularity,
        mal_members=mal_members,
    )


# ── Chapter List ────────────────────────────────────────────────────────

def get_chapter_list(manga_id: str, manga_slug: str) -> list[Chapter]:
    """Fetch chapter list (authenticated API)."""
    token, ts = _generate_token()
    params = urlencode({
        "manga_id": manga_id,
        "offset": 0,
        "limit": 500,
        "order": "DESC",
        "_t": token,
        "_ts": ts,
    })
    url = f"{BASE}/auth/manga-chapters?{params}"
    data = json.loads(_http_get(url, headers={
        "Accept": "application/json",
        "Referer": f"{BASE}/manga/{quote(manga_slug)}",
    }))
    if not data.get("success"):
        raise RuntimeError(f"Chapter list API error: {data.get('message')}")
    return [Chapter(**ch) for ch in data["chapters"]]


def get_chapters_rev(chapters: list[Chapter]) -> list[Chapter]:
    """Return chapters in ascending order (chapter 1 first)."""
    return list(reversed(chapters))


def get_chapter_groups(chapters: list[Chapter]) -> dict[str, int]:
    """Get available groups and their chapter counts."""
    groups = {}
    for ch in chapters:
        g = ch.group_name
        if g:
            groups[g] = groups.get(g, 0) + 1
    return groups


def filter_chapters_by_group(chapters: list[Chapter], group_name: str | None = None) -> list[Chapter]:
    """Filter chapters by group name. None = all."""
    if group_name is None:
        return chapters
    return [ch for ch in chapters if ch.group_name == group_name]


def get_chapter_id_from_url(chapter_url: str) -> str:
    """Extract chapter ID from URL like /read/slug/ch1-356073."""
    return chapter_url.rsplit("-", 1)[-1]


# ── Chapter Images ──────────────────────────────────────────────────────

def get_chapter_images(chapter_id: str, referer: str | None = None) -> ChapterContent:
    """Get all image URLs for a chapter (no auth needed)."""
    url = f"{BASE}/auth/chapter-content?chapter_id={chapter_id}"
    data = json.loads(_http_get(url, headers={
        "Accept": "application/json",
        "Referer": referer or f"{BASE}/",
    }))
    if not data.get("success"):
        raise RuntimeError(f"Chapter content API error: {data}")
    raw_images = data["images"]
    # API can return strings (just URLs) or dicts (url/filename/width/height)
    images: list[ChapterImage] = []
    for img in raw_images:
        if isinstance(img, str):
            images.append(ChapterImage(url=img))
        else:
            images.append(ChapterImage(**img))
    return ChapterContent(images=images, total=data.get("total", len(images)))


def download_image(img_url: str, max_retries: int = 3, retry_delay: float = 2.0, timeout: int = 30) -> bytes:
    """Download a single image by URL with retries."""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return _http_get_bytes(img_url, timeout=timeout)
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(retry_delay)
    raise last_err if last_err else RuntimeError("Download failed")


def download_images_concurrent(images: list["ChapterImage"], max_workers: int = 8, on_image_downloaded=None, config=None) -> list[bytes]:
    """Download all images for a chapter concurrently."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Load config if not provided to get retry settings
    if config is None:
        try:
            from mangataro.config import Config
            config = Config.load()
        except Exception:
            pass

    max_retries = config.download.max_retries if config else 3
    retry_delay = config.download.retry_delay if config else 2.0
    timeout = config.download.timeout if config else 30

    results: list[bytes] = [b""] * len(images)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        fut_map = {
            executor.submit(download_image, img.url, max_retries=max_retries, retry_delay=retry_delay, timeout=timeout): i 
            for i, img in enumerate(images)
        }
        for fut in as_completed(fut_map):
            idx = fut_map[fut]
            results[idx] = fut.result()
            if on_image_downloaded:
                on_image_downloaded()
    return results


# ── Slug resolution ─────────────────────────────────────────────────────

def extract_slug(url_or_slug: str) -> str:
    """Extract manga slug from URL or return as-is if already a slug."""
    # Remove trailing slash
    url_or_slug = url_or_slug.rstrip("/")
    # If it's a full URL, extract the slug part
    if url_or_slug.startswith("http"):
        parts = url_or_slug.split("/")
        # Format: https://mangataro.org/manga/{slug}
        # or:      https://mangataro.org/manga/{slug}/some/extra
        for i, p in enumerate(parts):
            if p == "manga" and i + 1 < len(parts):
                return parts[i + 1]
    # Already a slug or ID
    return url_or_slug
