"""Pydantic models for MangaTaro API responses."""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class MangaInfo(BaseModel):
    """Comprehensive manga information."""
    id: str = ""
    title: str = ""
    original_title: str = ""
    slug: str = ""
    description: str = ""
    authors: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    type: str = ""
    status: str = ""
    total_chapters: str | int = ""
    views: str = ""
    cover: str = ""
    date_published: str = ""
    date_modified: str = ""
    mal_score: str = ""
    mal_rank: str = ""
    mal_popularity: str = ""
    mal_members: str = ""


class SearchResult(BaseModel):
    """A single search result."""
    id: int | str = 0
    title: str = ""
    slug: str = ""
    permalink: str = ""
    description: str = ""
    type: str = ""
    status: str = ""
    authors: list[str] = Field(default_factory=list)
    photo: Optional[str] = None
    thumbnail: Optional[str] = None
    genres: list[str] = Field(default_factory=list)
    rating: str = ""
    chapter_count: int = 0

    @property
    def cover_url(self) -> str:
        """Get full cover URL with slug-based fallback."""
        url = self.thumbnail or self.photo
        if url:
            if url.startswith("http"):
                return url
            return f"https://mangataro.org{url}"
        # Build from slug pattern
        if self.slug:
            return f"https://mangataro.org/content/media/{self.slug}.jpg"
        return ""


class Chapter(BaseModel):
    """A single chapter entry."""
    id: int | str = 0
    chapter: str = "0"
    title: str = ""
    url: str = ""
    group_name: Optional[str] = None
    group_id: Optional[int] = None
    language: str = "en"
    date: str = ""
    views: int = 0

    @property
    def chapter_num(self) -> float:
        """Parse chapter number as float for sorting."""
        try:
            return float(self.chapter)
        except (ValueError, TypeError):
            return 0.0


class ChapterImage(BaseModel):
    """A single chapter page image."""
    url: str = ""
    filename: str = ""
    width: int = 0
    height: int = 0


class ChapterContent(BaseModel):
    """Chapter content response."""
    images: list[ChapterImage] = Field(default_factory=list)
    total: int = 0


class SearchResponse(BaseModel):
    """Search API response."""
    success: bool = True
    count: int = 0
    query: str = ""
    results: list[SearchResult] = Field(default_factory=list)


class ChapterListResponse(BaseModel):
    """Chapter list API response."""
    success: bool = True
    chapters: list[Chapter] = Field(default_factory=list)
    total: int = 0


class DownloadRecord(BaseModel):
    """A record of a completed download."""
    manga_id: str = ""
    manga_title: str = ""
    manga_slug: str = ""
    chapter_range: str = ""
    chapter_count: int = 0
    export_format: str = "images"
    output_path: str = ""
    timestamp: str = ""
    status: str = "success"
