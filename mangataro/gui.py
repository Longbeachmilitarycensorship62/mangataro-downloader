"""MangaTaro Downloader — PyQt6 GUI Application."""

import sys
import time
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QStackedWidget, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QComboBox, QGroupBox, QFrame, QSplitter, QStatusBar,
    QMessageBox, QProgressBar, QFileDialog,
    QListWidget, QListWidgetItem, QTextBrowser,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QUrl
from PyQt6.QtGui import QPixmap, QFont, QIcon, QDesktopServices, QColor
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from mangataro.config import Config
from mangataro.engine import (
    get_manga_info, get_chapter_list, get_chapters_rev,
    get_chapter_images, get_chapter_id_from_url,
    extract_slug, download_image,
)
from mangataro.search import search_manga
from mangataro.export import export_chapter, EXPORT_FORMATS, EXPORT_DESCRIPTIONS
from mangataro.history import History
from mangataro.models import MangaInfo, SearchResult, Chapter
from mangataro.themes import get_theme_qss


# ═══════════════════════════════════════════════════════════════════════
# Workers (QThread-based)
# ═══════════════════════════════════════════════════════════════════════

class SearchWorker(QThread):
    """Search for manga in a background thread."""
    results_ready = pyqtSignal(object)  # SearchResponse
    error_occurred = pyqtSignal(str)

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self._query = query

    def run(self):
        try:
            result = search_manga(self._query)
            self.results_ready.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))


class InfoWorker(QThread):
    """Fetch manga info in background."""
    info_ready = pyqtSignal(object)  # MangaInfo
    chapters_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, slug: str, parent=None):
        super().__init__(parent)
        self._slug = slug

    def run(self):
        try:
            manga = get_manga_info(self._slug)
            self.info_ready.emit(manga)
            if manga.id:
                chapters = get_chapter_list(manga.id, manga.slug)
                self.chapters_ready.emit(get_chapters_rev(chapters))
        except Exception as e:
            self.error_occurred.emit(str(e))


class DownloadWorker(QThread):
    """Download chapters in a background thread."""
    progress = pyqtSignal(int, str)  # percent, status text
    chapter_progress = pyqtSignal(str, int, str)  # chapter num, percent, status
    chapter_done = pyqtSignal(str, bool)  # chapter num, success
    finished = pyqtSignal(int, str)  # total pages, first chapter range
    error_occurred = pyqtSignal(str)

    def __init__(self, manga: MangaInfo, chapters: list[Chapter],
                 fmt: str, output_dir: Path, delete_imgs: bool, parent=None):
        super().__init__(parent)
        self._manga = manga
        self._chapters = chapters
        self._fmt = fmt
        self._output_dir = output_dir
        self._delete_imgs = delete_imgs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from mangataro.engine import download_images_concurrent
        import threading

        config = Config.load()
        max_ch_workers = config.download.max_concurrent_chapters
        max_img_workers = config.download.max_concurrent_images

        total = len(self._chapters)
        completed = 0
        total_pages = 0
        lock = threading.Lock()

        # Emit initial status for all chapters
        for ch in self._chapters:
            self.chapter_progress.emit(ch.chapter, 0, "Pending...")

        def _dl_one_chapter(ch) -> int:
            if self._cancelled:
                return 0
            ch_id = get_chapter_id_from_url(ch.url)
            self.chapter_progress.emit(ch.chapter, 5, "Fetching images...")
            try:
                content = get_chapter_images(ch_id, referer=ch.url)
            except Exception as e:
                self.chapter_progress.emit(ch.chapter, 0, f"Error: {e}")
                raise e
            
            if self._cancelled:
                return 0

            total_imgs = len(content.images)
            completed_imgs = 0

            def on_img_done():
                nonlocal completed_imgs
                if self._cancelled:
                    return
                completed_imgs += 1
                pct = int((completed_imgs / total_imgs) * 85) if total_imgs > 0 else 85
                self.chapter_progress.emit(ch.chapter, 5 + pct, f"Downloading ({completed_imgs}/{total_imgs})...")

            try:
                images = download_images_concurrent(
                    content.images,
                    max_workers=max_img_workers,
                    on_image_downloaded=on_img_done,
                    config=config,
                )
            except Exception as e:
                self.chapter_progress.emit(ch.chapter, 0, f"Error: {e}")
                raise e
            
            if self._cancelled:
                return 0

            self.chapter_progress.emit(ch.chapter, 95, "Exporting...")
            try:
                export_chapter(
                    images,
                    self._output_dir,
                    self._manga.title,
                    ch.chapter,
                    fmt=self._fmt,
                    delete_after=self._delete_imgs,
                    config=config,
                )
            except Exception as e:
                self.chapter_progress.emit(ch.chapter, 0, f"Export error: {e}")
                raise e

            self.chapter_progress.emit(ch.chapter, 100, "Done")
            return len(images)

        self.progress.emit(0, "Starting download...")

        with ThreadPoolExecutor(max_workers=max_ch_workers) as executor:
            future_to_chapter = {
                executor.submit(_dl_one_chapter, ch): ch for ch in self._chapters
            }

            for future in as_completed(future_to_chapter):
                ch = future_to_chapter[future]
                if self._cancelled:
                    continue
                try:
                    pages = future.result()
                    with lock:
                        completed += 1
                        total_pages += pages
                        pct = int((completed / total) * 100)
                        self.progress.emit(pct, f"Ch.{ch.chapter} done ({completed}/{total})")
                        self.chapter_done.emit(ch.chapter, True)
                except Exception as e:
                    with lock:
                        completed += 1
                        pct = int((completed / total) * 100)
                        self.progress.emit(pct, f"Ch.{ch.chapter} failed ({completed}/{total})")
                        self.chapter_done.emit(ch.chapter, False)

        if self._cancelled:
            return

        range_str = f"{self._chapters[0].chapter}-{self._chapters[-1].chapter}"
        self.finished.emit(total_pages, range_str)


class CoverLoader(QThread):
    """Load cover images in background with retry and CDN fallback."""
    loaded = pyqtSignal(QPixmap)
    failed = pyqtSignal()

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._urls = [url]

    def run(self):
        from urllib.request import Request, urlopen
        import ssl

        ctx = ssl.create_default_context()
        pixmap = QPixmap()

        for url in self._urls:
            if not url:
                continue
            try:
                req = Request(url, headers={"User-Agent": self.UA})
                with urlopen(req, context=ctx, timeout=15) as r:
                    data = r.read()
                if pixmap.loadFromData(data) and not pixmap.isNull():
                    self.loaded.emit(pixmap)
                    return
            except Exception:
                continue

        self.failed.emit()


# ═══════════════════════════════════════════════════════════════════════
# Sidebar
# ═══════════════════════════════════════════════════════════════════════

class SidebarNav(QWidget):
    """Left sidebar with icon + text navigation tabs."""

    page_changed = pyqtSignal(int)

    TABS = [
        ("🔍", "Search"),
        ("🔗", "Open URL"),
        ("⬇️", "Downloads"),
        ("📋", "History"),
        ("⚙️", "Settings"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self._active_index = 0
        self._buttons: list[QPushButton] = []
        self._expanded = True
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        # Logo area
        logo = QLabel("📚")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size: 28px; padding: 16px 0;")
        layout.addWidget(logo)

        # Title
        title = QLabel("MangaTaro")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #6C5CE7; padding-bottom: 12px;")
        layout.addWidget(title)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #21262D; max-height: 1px; margin: 4px 12px;")
        layout.addWidget(sep)

        # Nav buttons
        for idx, (icon, text) in enumerate(self.TABS):
            btn = QPushButton(f"  {icon}  {text}")
            btn.setProperty("class", "navButton")
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, i=idx: self._on_tab_clicked(i))
            self._buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Collapse toggle
        self._collapse_btn = QPushButton("◀")
        self._collapse_btn.setFixedSize(36, 36)
        self._collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        layout.addWidget(self._collapse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _on_tab_clicked(self, index: int):
        self._buttons[self._active_index].setChecked(False)
        self._active_index = index
        self._buttons[index].setChecked(True)
        self.page_changed.emit(index)

    def set_current_index(self, index: int):
        if 0 <= index < len(self._buttons) and index != self._active_index:
            self._on_tab_clicked(index)

    def _toggle_collapse(self):
        if self._expanded:
            self.setFixedWidth(72)
            for btn in self._buttons:
                icon = btn.text().strip().split()[0] if btn.text().strip() else ""
                btn.setText(f"  {icon}  ")
            self._collapse_btn.setText("▶")
        else:
            self.setFixedWidth(180)
            for idx, (icon, text) in enumerate(self.TABS):
                self._buttons[idx].setText(f"  {icon}  {text}")
            self._collapse_btn.setText("◀")
        self._expanded = not self._expanded


# ═══════════════════════════════════════════════════════════════════════
# Widgets
# ═══════════════════════════════════════════════════════════════════════

class SearchResultCard(QFrame):
    """Clickable card showing manga search result."""

    clicked = pyqtSignal(object)  # SearchResult

    CARD_WIDTH = 240
    CARD_HEIGHT = 360

    def __init__(self, result: SearchResult, parent=None):
        super().__init__(parent)
        self._result = result
        self._loader = None
        self._setup_ui()
        self._load_cover()

    def _setup_ui(self):
        self.setObjectName("card")
        self.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Cover
        self._cover = QLabel()
        self._cover.setFixedSize(self.CARD_WIDTH, 320)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setStyleSheet(
            "background-color: #1C2128; border-top-left-radius: 8px; border-top-right-radius: 8px;"
        )
        self._cover.setText("📖\nLoading...")
        self._cover.setWordWrap(True)
        layout.addWidget(self._cover)

        # Info bar
        info = QWidget()
        info.setStyleSheet("background-color: #161B22; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(10, 6, 10, 8)
        info_layout.setSpacing(2)

        title = QLabel(self._result.title)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 12px; font-weight: bold; color: #E6EDF3;")
        info_layout.addWidget(title)

        meta = QLabel(
            f"{'🟢' if self._result.status == 'Ongoing' else '🔴' if self._result.status == 'Completed' else '🟡'} {self._result.status or '?'}  ·  Ch.{self._result.chapter_count or '?'}"
        )
        meta.setStyleSheet("font-size: 10px; color: #7D8590;")
        info_layout.addWidget(meta)

        layout.addWidget(info)

    def _load_cover(self):
        """Load cover with CDN fallback URLs."""
        url = self._result.cover_url
        if not url:
            self._cover.setText("📖\nNo Cover")
            self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return

        # Build fallback URLs
        urls = [url]
        slug = self._result.slug
        if slug:
            urls.append(f"https://mangataro.org/content/media/{slug}.jpg")
            urls.append(f"https://mangataro.yachts/covers/{slug}.jpg")
            urls.append(f"https://mangataro.yachts/uploads/covers/{slug}.jpg")

        self._loader = CoverLoader(urls[0], parent=self)
        self._loader._urls = urls
        self._loader.loaded.connect(self._on_cover_loaded)
        self._loader.failed.connect(lambda: self._cover.setText("📖\nNo Cover"))
        self._loader.start()

    def _on_cover_loaded(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            self.CARD_WIDTH, 320,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cover.setPixmap(scaled)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event):
        self.clicked.emit(self._result)
        super().mousePressEvent(event)

    def cleanup(self):
        if self._loader and self._loader.isRunning():
            self._loader.quit()
            self._loader.wait(1000)


class MangaDetailPage(QWidget):
    """Full manga detail view with chapters."""

    download_requested = pyqtSignal(object, list, str, bool)  # manga, chapters, format, delete_images

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manga: Optional[MangaInfo] = None
        self._all_chapters: list[Chapter] = []
        self._filtered_chapters: list[Chapter] = []
        self._checkboxes: list[QCheckBox] = []
        self._cover_loader = None
        self._visible = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Back bar ──
        back_bar = QHBoxLayout()
        back_btn = QPushButton("← Back to Browse")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("background: transparent; color: #7D8590; padding: 4px 12px;")
        back_btn.clicked.connect(lambda: self.hide())
        back_bar.addWidget(back_btn)
        back_bar.addStretch()
        layout.addLayout(back_bar)

        # ── Cover + Info Header ──
        header = QFrame()
        header.setObjectName("card")
        header.setStyleSheet("QFrame#card { background: #161B22; border: 1px solid #21262D; border-radius: 8px; }")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 16, 16, 16)
        h_layout.setSpacing(20)

        self._cover = QLabel()
        self._cover.setFixedSize(140, 200)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setStyleSheet("background: #1C2128; border-radius: 4px; font-size: 32px;")
        self._cover.setText("📖")
        h_layout.addWidget(self._cover)

        info = QVBoxLayout()
        info.setSpacing(3)

        self._title = QLabel("")
        self._title.setStyleSheet("font-size: 20px; font-weight: bold; color: #E6EDF3;")
        self._title.setWordWrap(True)
        info.addWidget(self._title)

        self._status = QLabel("")
        self._status.setStyleSheet("font-size: 13px; color: #7D8590;")
        info.addWidget(self._status)

        # Extra info line: genres, views, etc.
        self._extra_info = QLabel("")
        self._extra_info.setStyleSheet("font-size: 12px; color: #484F58; line-height: 1.5;")
        self._extra_info.setWordWrap(True)
        info.addWidget(self._extra_info)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #21262D; max-height: 1px; margin: 4px 0;")
        info.addWidget(sep)

        # Description — QTextBrowser for full scrollable text
        self._desc = QTextBrowser()
        self._desc.setOpenExternalLinks(False)
        self._desc.setMaximumHeight(120)
        self._desc.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; color: #484F58; font-size: 12px; }"
        )
        info.addWidget(self._desc)

        h_layout.addLayout(info, stretch=1)
        layout.addWidget(header)

        # ── Toolbar: Group filter + Select All / None + Download ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Group filter
        toolbar.addWidget(QLabel("Group:"))
        self._group_filter = QComboBox()
        self._group_filter.setFixedWidth(180)
        self._group_filter.currentIndexChanged.connect(self._on_group_filter_changed)
        toolbar.addWidget(self._group_filter)

        toolbar.addWidget(QLabel("Format:"))
        self._fmt_sel = QComboBox()
        for fmt in EXPORT_FORMATS:
            desc = EXPORT_DESCRIPTIONS.get(fmt, "")
            self._fmt_sel.addItem(f"{fmt.upper()} — {desc}", fmt)
        self._fmt_sel.setMinimumWidth(220)
        toolbar.addWidget(self._fmt_sel)

        self._delete_cb = QCheckBox("Delete images")
        toolbar.addWidget(self._delete_cb)

        toolbar.addStretch()

        # Select All / None
        sel_all_btn = QPushButton("✓ All")
        sel_all_btn.setFixedWidth(75)
        sel_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sel_all_btn.clicked.connect(lambda: self._toggle_all(True))
        toolbar.addWidget(sel_all_btn)

        sel_none_btn = QPushButton("✗ None")
        sel_none_btn.setFixedWidth(85)
        sel_none_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sel_none_btn.clicked.connect(lambda: self._toggle_all(False))
        toolbar.addWidget(sel_none_btn)

        self._dl_btn = QPushButton("⬇️ Download")
        self._dl_btn.setObjectName("primaryButton")
        self._dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dl_btn.clicked.connect(self._on_download)
        toolbar.addWidget(self._dl_btn)

        layout.addLayout(toolbar)

        # ── Chapter table ──
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["✓", "Chapter", "Title", "Group", "Date"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, stretch=1)

    def load(self, manga: MangaInfo, chapters: list[Chapter]):
        """Load manga data and chapter list."""
        self._manga = manga
        self._all_chapters = chapters

        # ── Header info ──
        self._title.setText(manga.title)

        # Status line
        status_str = f"{'🟢' if manga.status == 'Ongoing' else '🔴' if manga.status == 'Completed' else '🟡'} {manga.status}"
        meta_parts = [status_str]
        if manga.type:
            meta_parts.append(manga.type)
        if manga.authors:
            meta_parts.append(f"by {', '.join(manga.authors)}")
        if manga.total_chapters:
            meta_parts.append(f"{manga.total_chapters} chapters")
        self._status.setText(" · ".join(meta_parts))

        # Extra info block
        extra_lines = []
        if manga.genres:
            extra_lines.append(f"📂 Genres: {', '.join(manga.genres)}")
        if manga.views:
            extra_lines.append(f"👁️ Views: {manga.views}")
        if manga.original_title:
            extra_lines.append(f"📝 Alt: {manga.original_title}")

        mal_parts = []
        if manga.mal_score:
            mal_parts.append(f"Score: {manga.mal_score}")
        if manga.mal_rank:
            mal_parts.append(f"Rank: #{manga.mal_rank}")
        if manga.mal_popularity:
            mal_parts.append(f"Pop: #{manga.mal_popularity}")
        if manga.mal_members:
            mal_parts.append(f"Members: {manga.mal_members}")
        if mal_parts:
            extra_lines.append("📊 MAL " + " · ".join(mal_parts))

        if manga.tags:
            tag_str = ", ".join(manga.tags[:12])
            extra_lines.append(f"🏷️ Tags: {tag_str}")

        date_parts = []
        if manga.date_published:
            date_parts.append(f"Published: {manga.date_published[:10]}")
        if manga.date_modified:
            date_parts.append(f"Updated: {manga.date_modified[:10]}")
        if date_parts:
            extra_lines.append("📅 " + " · ".join(date_parts))

        self._extra_info.setText("\n".join(extra_lines) if extra_lines else "")
        self._extra_info.setVisible(bool(extra_lines))

        # Full description
        desc_html = manga.description.replace("\n", "<br>") if manga.description else ""
        if desc_html:
            # Truncate very long descriptions
            words = desc_html.split()
            if len(words) > 200:
                desc_html = " ".join(words[:200]) + "..."
        self._desc.setHtml(f'<p style="color: #484F58; line-height: 1.5;">{desc_html}</p>')
        self._desc.setVisible(bool(desc_html))

        # ── Cover with CDN fallback ──
        if manga.cover:
            cover_urls = [manga.cover]
            slug = manga.slug
            if slug:
                cover_urls.append(f"https://mangataro.yachts/covers/{slug}.jpg")
                cover_urls.append(f"https://mangataro.yachts/uploads/covers/{slug}.jpg")
            self._cover_loader = CoverLoader(cover_urls[0], parent=self)
            self._cover_loader._urls = cover_urls
            self._cover_loader.loaded.connect(self._on_cover_loaded)
            self._cover_loader.failed.connect(lambda: None)
            self._cover_loader.start()

        # ── Chapters ──
        self._populate_groups(chapters)
        self._filtered_chapters = chapters
        self._populate_table(chapters)

    def _populate_groups(self, chapters: list[Chapter]):
        """Populate the group filter combobox."""
        self._group_filter.blockSignals(True)
        self._group_filter.clear()
        self._group_filter.addItem("All Groups", None)

        groups = {}
        for ch in chapters:
            g = ch.group_name
            if g:
                groups[g] = groups.get(g, 0) + 1

        for g, count in sorted(groups.items()):
            self._group_filter.addItem(f"{g} ({count})", g)

        self._group_filter.blockSignals(False)

    def _on_group_filter_changed(self, idx: int):
        """Filter chapter table by selected group."""
        if not self._all_chapters:
            return
        group = self._group_filter.itemData(idx)
        if group is None:
            self._filtered_chapters = self._all_chapters[:]
        else:
            self._filtered_chapters = [ch for ch in self._all_chapters if ch.group_name == group]
        self._populate_table(self._filtered_chapters)

    def _populate_table(self, chapters: list[Chapter]):
        self._table.setRowCount(0)
        self._table.setRowCount(len(chapters))
        self._checkboxes.clear()

        for row, ch in enumerate(chapters):
            cb = QCheckBox()
            cb.setChecked(True)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._checkboxes.append(cb)

            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(4, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.addWidget(cb)
            self._table.setCellWidget(row, 0, cb_widget)

            ch_item = QTableWidgetItem(f"Ch. {ch.chapter}")
            ch_item.setForeground(QColor("#6C5CE7"))
            self._table.setItem(row, 1, ch_item)
            self._table.setItem(row, 2, QTableWidgetItem(ch.title or "—"))
            self._table.setItem(row, 3, QTableWidgetItem(ch.group_name or "—"))
            self._table.setItem(row, 4, QTableWidgetItem(ch.date[:10] if ch.date else "—"))

    def _toggle_all(self, state: bool):
        for cb in self._checkboxes:
            cb.setChecked(state)

    def _on_cover_loaded(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            140, 200,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cover.setPixmap(scaled)

    def _on_download(self):
        if not self._manga or not self._all_chapters:
            return

        # Use filtered chapters for download
        chapters_source = self._filtered_chapters if hasattr(self, '_filtered_chapters') and self._filtered_chapters else self._all_chapters

        sel = [c for c, cb in zip(chapters_source, self._checkboxes) if cb.isChecked()]

        if not sel:
            QMessageBox.warning(self, "No Chapters", "Please select at least one chapter to download.")
            return

        fmt = self._fmt_sel.currentData()
        delete_imgs = self._delete_cb.isChecked()

        self.download_requested.emit(self._manga, sel, fmt, delete_imgs)

    def get_selected_chapters(self) -> list[Chapter]:
        """Get currently selected chapters."""
        return [c for c, cb in zip(self._all_chapters, self._checkboxes) if cb.isChecked()]


# ═══════════════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════════════

class SearchPage(QWidget):
    """Search and browse manga."""

    manga_selected = pyqtSignal(object, list)  # manga_info, chapters

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_worker = None
        self._info_worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
        search_bar = QWidget()
        search_bar.setStyleSheet("background: #161B22; border-bottom: 1px solid #21262D;")
        sb_layout = QHBoxLayout(search_bar)
        sb_layout.setContentsMargins(20, 12, 20, 12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 Search manga by name...")
        self._search_input.setFixedHeight(38)
        self._search_input.returnPressed.connect(self._on_search)
        sb_layout.addWidget(self._search_input, stretch=1)

        search_btn = QPushButton("🔍 Search")
        search_btn.setObjectName("primaryButton")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.clicked.connect(self._on_search)
        sb_layout.addWidget(search_btn)

        layout.addWidget(search_bar)

        # Results area with scroll
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._results_container = QWidget()
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Welcome placeholder
        self._welcome = QLabel(
            "🔍  Search for manga by name\n\n"
            "Enter a title above to find manga\n"
            "from MangaTaro.org"
        )
        self._welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome.setStyleSheet("color: #484F58; font-size: 16px; padding: 60px;")
        self._results_layout.addWidget(self._welcome)

        self._grid_layout = None  # Will be created on search

        self._scroll.setWidget(self._results_container)
        layout.addWidget(self._scroll, stretch=1)

    def _on_search(self):
        query = self._search_input.text().strip()
        if not query:
            return

        # Clear results
        self._clear_results()

        # Loading indicator
        loading = QLabel("⏳ Searching...")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setStyleSheet("color: #7D8590; font-size: 14px; padding: 40px;")
        self._results_layout.addWidget(loading)

        # Start search worker
        self._search_worker = SearchWorker(query, parent=self)
        self._search_worker.results_ready.connect(self._on_results)
        self._search_worker.error_occurred.connect(self._on_search_error)
        self._search_worker.start()

    def _clear_results(self):
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            if item.widget():
                if hasattr(item.widget(), 'cleanup'):
                    item.widget().cleanup()
                item.widget().deleteLater()

    def _on_results(self, response):
        self._clear_results()

        if not response.results:
            empty = QLabel("😕 No results found. Try a different search.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #7D8590; font-size: 14px; padding: 40px;")
            self._results_layout.addWidget(empty)
            return

        # Create grid layout
        grid = QHBoxLayout()
        grid.setSpacing(16)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cards: list[SearchResultCard] = []
        row_count = 0
        for result in response.results:
            card = SearchResultCard(result)
            card.clicked.connect(self._on_card_clicked)
            cards.append(card)

        # Arrange in rows of 4
        cols = 4
        rows = [cards[i:i+cols] for i in range(0, len(cards), cols)]

        for row_cards in rows:
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setSpacing(16)
            row_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for c in row_cards:
                row_l.addWidget(c)
            self._results_layout.addWidget(row_w)

        info = QLabel(f"Found {response.count} results for \"{response.query}\"")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #7D8590; font-size: 12px; padding: 8px;")
        self._results_layout.addWidget(info)

    def _on_card_clicked(self, result: SearchResult):
        """When a card is clicked, load manga info and show detail."""
        slug = extract_slug(result.permalink)
        self._info_worker = InfoWorker(slug, parent=self)
        self._info_worker.info_ready.connect(self._on_info_ready)
        self._info_worker.chapters_ready.connect(self._on_chapters_ready)
        self._info_worker.error_occurred.connect(lambda e: QMessageBox.warning(self, "Error", str(e)))
        self._info_worker.start()

    def _on_info_ready(self, manga: MangaInfo):
        self._current_manga = manga

    def _on_chapters_ready(self, chapters: list[Chapter]):
        if hasattr(self, '_current_manga') and self._current_manga:
            self.manga_selected.emit(self._current_manga, chapters)

    def _on_search_error(self, error: str):
        self._clear_results()
        err = QLabel(f"⚠️ {error}")
        err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        err.setStyleSheet("color: #E17055; font-size: 14px; padding: 40px;")
        self._results_layout.addWidget(err)


class OpenUrlPage(QWidget):
    """Open manga by URL or slug."""

    manga_selected = pyqtSignal(object, list)  # manga_info, chapters

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info_worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Heading
        heading = QLabel("🔗 Open Manga by URL or Slug")
        heading.setStyleSheet("font-size: 20px; font-weight: bold; color: #E6EDF3;")
        layout.addWidget(heading)

        sub = QLabel("Paste a MangaTaro URL (https://mangataro.org/manga/...) or just the slug")
        sub.setStyleSheet("font-size: 13px; color: #7D8590;")
        layout.addWidget(sub)

        # Input row
        input_row = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("e.g. the-gwichon-village-mystery or full URL...")
        self._url_input.setFixedHeight(40)
        self._url_input.returnPressed.connect(self._on_open)
        input_row.addWidget(self._url_input, stretch=1)

        open_btn = QPushButton("📖 Open")
        open_btn.setObjectName("primaryButton")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._on_open)
        input_row.addWidget(open_btn)

        layout.addLayout(input_row)

        # Recent
        recent_label = QLabel("Recent manga in history:")
        recent_label.setStyleSheet("font-size: 13px; color: #7D8590; margin-top: 12px;")
        layout.addWidget(recent_label)

        self._recent_list = QListWidget()
        self._recent_list.setStyleSheet(
            "QListWidget { background: #161B22; border: 1px solid #21262D; border-radius: 6px; }"
            "QListWidget::item { padding: 10px; border-bottom: 1px solid #21262D; }"
            "QListWidget::item:hover { background: #1C2128; }"
        )
        self._recent_list.itemDoubleClicked.connect(self._on_recent_clicked)
        layout.addWidget(self._recent_list, stretch=1)

        self._populate_recent()

        layout.addStretch()

    def _populate_recent(self):
        self._recent_list.clear()
        try:
            h = History()
            for e in h.get_all(10):
                if e.manga_slug:
                    item = QListWidgetItem(f"📚 {e.manga_title} ({e.manga_slug})")
                    item.setData(Qt.ItemDataRole.UserRole, e.manga_slug)
                    self._recent_list.addItem(item)
        except Exception:
            pass

    def _on_open(self):
        text = self._url_input.text().strip()
        if not text:
            return
        slug = extract_slug(text)

        self._info_worker = InfoWorker(slug, parent=self)
        self._info_worker.info_ready.connect(self._on_info_ready)
        self._info_worker.chapters_ready.connect(self._on_chapters_ready)
        self._info_worker.error_occurred.connect(lambda e: QMessageBox.warning(self, "Error", str(e)))
        self._info_worker.start()

    def _on_recent_clicked(self, item: QListWidgetItem):
        slug = item.data(Qt.ItemDataRole.UserRole)
        if slug:
            self._info_worker = InfoWorker(slug, parent=self)
            self._info_worker.info_ready.connect(self._on_info_ready)
            self._info_worker.chapters_ready.connect(self._on_chapters_ready)
            self._info_worker.error_occurred.connect(lambda e: QMessageBox.warning(self, "Error", str(e)))
            self._info_worker.start()

    def _on_info_ready(self, manga: MangaInfo):
        self._current_manga = manga

    def _on_chapters_ready(self, chapters: list[Chapter]):
        if hasattr(self, '_current_manga') and self._current_manga:
            self.manga_selected.emit(self._current_manga, chapters)


class DownloadsPage(QWidget):
    """Active and completed downloads."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_items: dict[int, dict] = {}
        self._completed_items: list[QWidget] = []
        self._next_task_id = 1
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel("⬇️ Downloads")
        heading.setStyleSheet("font-size: 20px; font-weight: bold; color: #E6EDF3;")
        layout.addWidget(heading)

        # Active section
        active_group = QGroupBox("Active Downloads")
        active_layout = QVBoxLayout(active_group)
        self._active_container = QVBoxLayout()
        self._active_container.setAlignment(Qt.AlignmentFlag.AlignTop)
        active_layout.addLayout(self._active_container)
        active_layout.addStretch()
        layout.addWidget(active_group, stretch=1)

        # Completed section
        completed_group = QGroupBox("Completed")
        completed_layout = QVBoxLayout(completed_group)
        self._completed_container = QVBoxLayout()
        self._completed_container.setAlignment(Qt.AlignmentFlag.AlignTop)
        completed_layout.addLayout(self._completed_container)
        completed_layout.addStretch()
        layout.addWidget(completed_group, stretch=1)

    def add_active(self, task_id: int, title: str, chapter_list: list[str]):
        item = QFrame()
        item.setObjectName("card")
        item.setStyleSheet("QFrame#card { background: #161B22; border: 1px solid #21262D; border-radius: 6px; padding: 12px; }")
        
        card_layout = QVBoxLayout(item)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        # Header: Manga Title
        header_layout = QHBoxLayout()
        title_label = QLabel(f"📚 {title}")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E6EDF3;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        card_layout.addLayout(header_layout)

        # Scroll area for chapters
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #161B22;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #21262D;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)

        ch_container = QWidget()
        ch_container.setStyleSheet("background-color: transparent;")
        ch_layout = QVBoxLayout(ch_container)
        ch_layout.setContentsMargins(0, 0, 0, 0)
        ch_layout.setSpacing(6)

        item_data = {
            "widget": item,
            "chapters": {}
        }

        for ch in chapter_list:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            ch_lbl = QLabel(f"Ch. {ch}")
            ch_lbl.setFixedWidth(80)
            ch_lbl.setStyleSheet("color: #C9D1D9; font-size: 12px;")
            row_layout.addWidget(ch_lbl)

            pbar = QProgressBar()
            pbar.setValue(0)
            pbar.setFixedHeight(12)
            pbar.setStyleSheet("""
                QProgressBar {
                    background-color: #21262D;
                    border: 1px solid #30363D;
                    border-radius: 6px;
                    text-align: center;
                    color: transparent;
                }
                QProgressBar::chunk {
                    background-color: #6C5CE7;
                    border-radius: 5px;
                }
            """)
            row_layout.addWidget(pbar, stretch=1)

            status_lbl = QLabel("Pending...")
            status_lbl.setStyleSheet("color: #7D8590; font-size: 11px;")
            status_lbl.setFixedWidth(150)
            row_layout.addWidget(status_lbl)

            ch_layout.addWidget(row)

            item_data["chapters"][ch] = {
                "pbar": pbar,
                "status": status_lbl
            }

        scroll.setWidget(ch_container)
        card_layout.addWidget(scroll)

        self._active_items[task_id] = item_data
        self._active_container.addWidget(item)
        return item

    def update_progress(self, task_id: int, percent: int, status_text: str):
        # Overall progress signal can be handled as no-op
        pass

    def update_chapter_progress(self, task_id: int, chapter: str, percent: int, status_text: str):
        item_data = self._active_items.get(task_id)
        if not item_data:
            return
        ch_data = item_data["chapters"].get(chapter)
        if ch_data:
            ch_data["pbar"].setValue(percent)
            ch_data["status"].setText(status_text)
            if percent == 100:
                ch_data["status"].setStyleSheet("color: #00B894; font-size: 11px;")
            elif "error" in status_text.lower() or "failed" in status_text.lower():
                ch_data["status"].setStyleSheet("color: #FF7675; font-size: 11px;")

    def complete_download(self, task_id: int, title: str = "", chapter_range: str = "", fmt: str = ""):
        item_data = self._active_items.pop(task_id, None)
        if item_data:
            widget = item_data["widget"]
            self._active_container.removeWidget(widget)
            widget.deleteLater()

        # Add to completed
        done = QFrame()
        done.setObjectName("card")
        done.setStyleSheet("QFrame#card { background: #161B22; border: 1px solid #21262D; border-radius: 6px; padding: 8px; }")
        done_layout = QHBoxLayout(done)
        done_layout.setContentsMargins(12, 8, 12, 8)

        info = QVBoxLayout()
        label = QLabel(f"✅ {title} ({chapter_range})")
        label.setStyleSheet("color: #00B894;")
        info.addWidget(label)
        info.addWidget(QLabel(f"Format: {fmt}"))
        done_layout.addLayout(info, stretch=1)

        self._completed_container.insertWidget(0, done)


class HistoryPage(QWidget):
    """Download history display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel("📋 Download History")
        heading.setStyleSheet("font-size: 20px; font-weight: bold; color: #E6EDF3;")
        layout.addWidget(heading)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh)
        layout.addWidget(refresh_btn)

        clear_btn = QPushButton("🗑️ Clear All")
        clear_btn.setStyleSheet("color: #E17055;")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear)
        layout.addWidget(clear_btn)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["Title", "Chapters", "Format", "Slug", "Date", "Status"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, stretch=1)

        self._refresh()

    def _refresh(self):
        try:
            h = History()
            entries = h.get_all(100)
            self._table.setRowCount(len(entries))
            for row, e in enumerate(entries):
                self._table.setItem(row, 0, QTableWidgetItem(e.manga_title or "—"))
                self._table.setItem(row, 1, QTableWidgetItem(e.chapter_range or "—"))
                self._table.setItem(row, 2, QTableWidgetItem(e.export_format or "—"))
                self._table.setItem(row, 3, QTableWidgetItem(e.manga_slug or "—"))
                self._table.setItem(row, 4, QTableWidgetItem(e.timestamp[:19] if e.timestamp else "—"))
                status_icon = "✅" if e.status == "success" else "❌"
                self._table.setItem(row, 5, QTableWidgetItem(status_icon))
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _clear(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Delete all download history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                History().clear()
                self._table.setRowCount(0)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))


class SettingsPage(QWidget):
    """Application settings."""

    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = Config.load()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        heading = QLabel("⚙️ Settings")
        heading.setStyleSheet("font-size: 20px; font-weight: bold; color: #E6EDF3;")
        layout.addWidget(heading)

        # General section
        gen = QGroupBox("General")
        gen_layout = QVBoxLayout(gen)

        rows = [
            ("Output Directory", self._make_path_input(str(self._config.output_dir))),
            ("Default Format", self._make_combo(list(EXPORT_FORMATS.keys()), self._config.default_format)),
            ("Theme", self._make_combo(["dark", "light"], self._config.gui.theme)),
        ]
        for label, widget in rows:
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 1)
            row.addWidget(widget, 2)
            gen_layout.addLayout(row)

        layout.addWidget(gen)

        # Download section
        dl = QGroupBox("Download")
        dl_layout = QVBoxLayout(dl)

        dl_rows = [
            ("Max Concurrent Chapters", self._make_spin(self._config.download.max_concurrent_chapters, 1, 16)),
            ("Max Concurrent Downloads", self._make_spin(self._config.download.max_concurrent_downloads, 1, 10)),
            ("Max Retries", self._make_spin(self._config.download.max_retries, 0, 10)),
            ("Delete Images After Export", self._make_check(self._config.quality.delete_images_after_export)),
        ]
        for label, widget in dl_rows:
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 1)
            row.addWidget(widget, 2)
            dl_layout.addLayout(row)

        layout.addWidget(dl)

        # Save button
        save_btn = QPushButton("💾 Save Settings")
        save_btn.setObjectName("primaryButton")
        save_btn.setFixedWidth(200)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        # Store references
        self._widgets = {
            "output_dir": rows[0][1],
            "default_format": rows[1][1],
            "gui.theme": rows[2][1],
            "download.max_concurrent_chapters": dl_rows[0][1],
            "download.max_concurrent_downloads": dl_rows[1][1],
            "download.max_retries": dl_rows[2][1],
            "quality.delete_images_after_export": dl_rows[3][1],
        }

    def _make_path_input(self, val: str) -> QLineEdit:
        w = QLineEdit(val)
        w.setStyleSheet("padding: 4px 8px;")
        return w

    def _make_combo(self, items: list, default: str) -> QComboBox:
        w = QComboBox()
        for item in items:
            w.addItem(item)
        idx = w.findText(default)
        if idx >= 0:
            w.setCurrentIndex(idx)
        return w

    def _make_spin(self, val: int, min_val: int, max_val: int):
        from PyQt6.QtWidgets import QSpinBox
        w = QSpinBox()
        w.setRange(min_val, max_val)
        w.setValue(val)
        w.setStyleSheet("padding: 4px 8px;")
        return w

    def _make_check(self, val: bool) -> QCheckBox:
        w = QCheckBox()
        w.setChecked(val)
        return w

    def _save(self):
        try:
            config = Config.load()
            config.output_dir = self._widgets["output_dir"].text()
            config.default_format = self._widgets["default_format"].currentText()
            config.gui.theme = self._widgets["gui.theme"].currentText()
            config.download.max_concurrent_chapters = self._widgets["download.max_concurrent_chapters"].value()
            config.download.max_concurrent_downloads = self._widgets["download.max_concurrent_downloads"].value()
            config.download.max_retries = self._widgets["download.max_retries"].value()
            config.quality.delete_images_after_export = self._widgets["quality.delete_images_after_export"].isChecked()

            config.save()

            self._config = config
            QMessageBox.information(self, "Saved", "Settings saved successfully!")
            self.settings_changed.emit()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save: {e}")

    def get_config(self) -> Config:
        return self._config


# ═══════════════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self._config = Config.load()
        self._current_manga: Optional[MangaInfo] = None
        self._download_workers: list[DownloadWorker] = []
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        self.setWindowTitle("📚 MangaTaro Downloader")
        self.setMinimumSize(1100, 700)
        self.resize(1300, 800)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self._sidebar = SidebarNav()
        self._sidebar.page_changed.connect(self._on_page_changed)
        main_layout.addWidget(self._sidebar)

        # Content stack
        self._stack = QStackedWidget()

        # Page 0: Search
        self._search_page = SearchPage()
        self._search_page.manga_selected.connect(self._show_detail)
        self._stack.addWidget(self._search_page)

        # Page 1: Open URL
        self._open_url_page = OpenUrlPage()
        self._open_url_page.manga_selected.connect(self._show_detail)
        self._stack.addWidget(self._open_url_page)

        # Page 2: Downloads
        self._downloads_page = DownloadsPage()
        self._stack.addWidget(self._downloads_page)

        # Page 3: History
        self._history_page = HistoryPage()
        self._stack.addWidget(self._history_page)

        # Page 4: Settings
        self._settings_page = SettingsPage()
        self._settings_page.settings_changed.connect(self._on_settings_changed)
        self._stack.addWidget(self._settings_page)

        # Page 5: Detail view (hidden initially)
        self._detail_page = MangaDetailPage()
        self._detail_page.download_requested.connect(self._on_download_requested)
        self._detail_page.hide()
        self._stack.addWidget(self._detail_page)

        main_layout.addWidget(self._stack, stretch=1)

        # Status bar
        status = QStatusBar()
        status.showMessage("✅ Ready")
        self.setStatusBar(status)

    def _on_page_changed(self, index: int):
        self._stack.setCurrentIndex(index)
        # Refresh history when visiting that tab
        if index == 3:
            self._history_page._refresh()
        if index == 1:
            self._open_url_page._populate_recent()

    def _show_detail(self, manga: MangaInfo, chapters: list[Chapter]):
        self._current_manga = manga
        self._detail_page.load(manga, chapters)
        self._detail_page.show()
        self._stack.setCurrentIndex(5)

    def _on_download_requested(self, manga: MangaInfo, chapters: list[Chapter],
                                fmt: str, delete_imgs: bool):
        """Handle download request from detail page."""
        task_id = self._downloads_page._next_task_id
        self._downloads_page._next_task_id += 1

        self._downloads_page.add_active(task_id, manga.title, [ch.chapter for ch in chapters])
        self._sidebar.set_current_index(2)  # Switch to downloads tab

        # Start worker
        output_dir = Path(self._config.output_dir)
        worker = DownloadWorker(
            manga, chapters, fmt, output_dir, delete_imgs,
            parent=self,
        )
        worker.progress.connect(
            lambda pct, status: self._downloads_page.update_progress(task_id, pct, status)
        )
        worker.chapter_progress.connect(
            lambda ch, pct, status: self._downloads_page.update_chapter_progress(task_id, ch, pct, status)
        )
        worker.chapter_done.connect(
            lambda ch, ok: None  # Could log per-chapter status
        )
        worker.finished.connect(
            lambda total_pages, ch_range: self._on_download_complete(
                task_id, manga, len(chapters), ch_range, fmt, total_pages
            )
        )
        worker.error_occurred.connect(
            lambda e: QMessageBox.warning(self, "Download Error", str(e))
        )

        self._download_workers.append(worker)
        worker.start()

    def _on_download_complete(self, task_id: int, manga: MangaInfo,
                               chapter_count: int, chapter_range: str, fmt: str, total_pages: int):
        """Handle download completion."""
        self._downloads_page.complete_download(
            task_id,
            title=manga.title,
            chapter_range=chapter_range,
            fmt=fmt,
        )

        # Record in history
        try:
            History().add(
                manga_id=manga.id,
                manga_title=manga.title,
                manga_slug=manga.slug,
                chapter_range=chapter_range,
                chapter_count=chapter_count,
                export_format=fmt,
                output_path=str(Path(self._config.output_dir)),
            )
        except Exception:
            pass

        self.statusBar().showMessage(
            f"✅ Downloaded {manga.title} ({chapter_range}) — {total_pages} pages",
            8000,
        )

    def _on_settings_changed(self):
        """Reload theme when settings change."""
        self._config = Config.load()
        self._apply_theme()

    def _apply_theme(self):
        theme_name = self._config.gui.theme if self._config else "dark"
        qss = get_theme_qss(theme_name)
        self.setStyleSheet(qss)

    def closeEvent(self, event):
        """Clean up threads on close."""
        for worker in self._download_workers:
            if worker.isRunning():
                worker.cancel()
                worker.wait(2000)
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════

def main():
    """Launch the GUI application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
