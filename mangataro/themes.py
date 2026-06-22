"""Theme manager — centralized color palette and QSS loading."""

_THEME_CACHE: dict[str, str] = {}


def get_theme_qss(name: str = "dark") -> str:
    """Get the QSS stylesheet for a theme (cached)."""
    name = name.lower().strip()
    if name in _THEME_CACHE:
        return _THEME_CACHE[name]

    if name == "light":
        qss = _get_light_qss()
    else:
        qss = _get_dark_qss()

    _THEME_CACHE[name] = qss
    return qss


def clear_cache() -> None:
    _THEME_CACHE.clear()


# ── Color palettes ──────────────────────────────────────────────────────

class Colors:
    PRIMARY = "#6C5CE7"       # Electric Purple
    SECONDARY = "#00CEC9"     # Turquoise
    ACCENT = "#FD79A8"        # Hot Pink
    SUCCESS = "#00B894"       # Mint Green
    WARNING = "#FDCB6E"       # Sunshine
    ERROR = "#E17055"         # Coral
    BG_DARK = "#0D1117"       # Main background (GitHub Dark)
    BG_CARD = "#161B22"       # Card Surface
    BG_ELEVATED = "#1C2128"   # Hover/active surfaces
    BORDER = "#21262D"        # Borders and separators
    TEXT = "#E6EDF3"          # Primary text
    TEXT_MUTED = "#7D8590"    # Secondary/dim text
    TEXT_DIM = "#484F58"      # Disabled/very dim text


# ── Dark Theme ──────────────────────────────────────────────────────────

def _get_dark_qss() -> str:
    c = Colors
    return f"""
QWidget {{
    background-color: {c.BG_DARK};
    color: {c.TEXT};
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {c.BG_DARK};
}}

/* ── Sidebar Navigation ── */
QPushButton.navButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 12px;
    text-align: left;
    font-size: 13px;
    color: {c.TEXT_MUTED};
}}
QPushButton.navButton:hover {{
    background-color: {c.BG_ELEVATED};
    color: {c.TEXT};
}}
QPushButton.navButton:checked {{
    background-color: {c.PRIMARY}20;
    color: {c.PRIMARY};
    border-left: 3px solid {c.PRIMARY};
}}

/* ── Generic Buttons ── */
QPushButton {{
    background-color: {c.BG_CARD};
    border: 1px solid {c.BORDER};
    border-radius: 6px;
    padding: 6px 16px;
    color: {c.TEXT};
}}
QPushButton:hover {{
    background-color: {c.BG_ELEVATED};
    border-color: {c.PRIMARY}60;
}}
QPushButton:pressed {{
    background-color: {c.PRIMARY}30;
}}
QPushButton:disabled {{
    color: {c.TEXT_DIM};
    background-color: {c.BG_CARD};
}}
QPushButton#primaryButton {{
    background-color: {c.PRIMARY};
    border: none;
    color: white;
    font-weight: bold;
    padding: 8px 24px;
}}
QPushButton#primaryButton:hover {{
    background-color: #7C6CF7;
}}

/* ── Inputs ── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {c.BG_CARD};
    border: 1px solid {c.BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    color: {c.TEXT};
    selection-background-color: {c.PRIMARY}60;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c.PRIMARY};
}}
QComboBox:hover, QComboBox:focus {{
    border-color: {c.PRIMARY}60;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {c.TEXT_MUTED};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {c.BG_CARD};
    border: 1px solid {c.BORDER};
    border-radius: 6px;
    selection-background-color: {c.PRIMARY}30;
    selection-color: {c.TEXT};
}}

/* ── Checkboxes ── */
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {c.BORDER};
    border-radius: 3px;
    background-color: {c.BG_CARD};
}}
QCheckBox::indicator:checked {{
    background-color: {c.PRIMARY};
    border-color: {c.PRIMARY};
    image: none;
}}
QCheckBox::indicator:hover {{
    border-color: {c.PRIMARY}60;
}}

/* ── Radio Buttons ── */
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {c.BORDER};
    border-radius: 7px;
    background-color: {c.BG_CARD};
}}
QRadioButton::indicator:checked {{
    background-color: {c.PRIMARY};
    border-color: {c.PRIMARY};
}}

/* ── Tables ── */
QTableWidget, QTableView {{
    background-color: {c.BG_DARK};
    border: 1px solid {c.BORDER};
    border-radius: 6px;
    gridline-color: {c.BORDER};
    selection-background-color: {c.PRIMARY}30;
    selection-color: {c.TEXT};
}}
QHeaderView::section {{
    background-color: {c.BG_CARD};
    border: none;
    border-bottom: 1px solid {c.BORDER};
    border-right: 1px solid {c.BORDER};
    padding: 6px 10px;
    font-weight: bold;
    color: {c.TEXT_MUTED};
}}
QTableWidget::item {{
    padding: 4px 8px;
}}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c.BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {c.BORDER};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c.TEXT_MUTED};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Progress Bar ── */
QProgressBar {{
    background-color: {c.BG_CARD};
    border: 1px solid {c.BORDER};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: 11px;
}}
QProgressBar::chunk {{
    background-color: {c.PRIMARY};
    border-radius: 3px;
}}

/* ── Group Box ── */
QGroupBox {{
    border: 1px solid {c.BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {c.PRIMARY};
}}

/* ── Tabs ── */
QTabWidget::pane {{
    border: 1px solid {c.BORDER};
    border-radius: 6px;
    background-color: {c.BG_DARK};
}}
QTabBar::tab {{
    background-color: {c.BG_CARD};
    border: 1px solid {c.BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    margin-right: 2px;
    color: {c.TEXT_MUTED};
}}
QTabBar::tab:selected {{
    background-color: {c.BG_DARK};
    color: {c.PRIMARY};
    border-bottom: 2px solid {c.PRIMARY};
}}

/* ── Labels ── */
QLabel#headingLabel {{
    font-size: 18px;
    font-weight: bold;
    color: {c.TEXT};
}}
QLabel#subheadingLabel {{
    font-size: 14px;
    color: {c.TEXT_MUTED};
}}
QLabel#mutedLabel {{
    color: {c.TEXT_MUTED};
    font-size: 11px;
}}

/* ── Frame / Card ── */
QFrame#card {{
    background-color: {c.BG_CARD};
    border: 1px solid {c.BORDER};
    border-radius: 8px;
}}
QFrame#card:hover {{
    border-color: {c.PRIMARY}60;
}}

/* ── Splitter ── */
QSplitter::handle {{
    background-color: {c.BORDER};
    width: 1px;
}}

/* ── Tooltips ── */
QToolTip {{
    background-color: {c.BG_ELEVATED};
    border: 1px solid {c.BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    color: {c.TEXT};
}}

/* ── Status Bar ── */
QStatusBar {{
    background-color: {c.BG_CARD};
    border-top: 1px solid {c.BORDER};
    color: {c.TEXT_MUTED};
    font-size: 12px;
}}
QStatusBar::item {{
    border: none;
}}

/* ── Menu ── */
QMenuBar {{
    background-color: {c.BG_CARD};
    border-bottom: 1px solid {c.BORDER};
    padding: 2px;
}}
QMenuBar::item:selected {{
    background-color: {c.PRIMARY}30;
    border-radius: 4px;
}}
QMenu {{
    background-color: {c.BG_CARD};
    border: 1px solid {c.BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {c.PRIMARY}30;
    color: {c.PRIMARY};
}}
QMenu::separator {{
    height: 1px;
    background: {c.BORDER};
    margin: 4px 8px;
}}
"""


# ── Light Theme ─────────────────────────────────────────────────────────

def _get_light_qss() -> str:
    """Simple light theme (same structure, lighter colors)."""
    # Reuse Colors approach with light palette
    c = type("LightColors", (), {
        "PRIMARY": "#6C5CE7",
        "SECONDARY": "#00CEC9",
        "ACCENT": "#FD79A8",
        "SUCCESS": "#00B894",
        "WARNING": "#FDCB6E",
        "ERROR": "#E17055",
        "BG_DARK": "#FFFFFF",
        "BG_CARD": "#F6F8FA",
        "BG_ELEVATED": "#EEF1F5",
        "BORDER": "#D0D7DE",
        "TEXT": "#1F2328",
        "TEXT_MUTED": "#656D76",
        "TEXT_DIM": "#8C959F",
    })()

    qss = _get_dark_qss()
    # Replace colors via simple substitution
    replacements = [
        (Colors.BG_DARK, c.BG_DARK),
        (Colors.BG_CARD, c.BG_CARD),
        (Colors.BG_ELEVATED, c.BG_ELEVATED),
        (Colors.BORDER, c.BORDER),
        (Colors.TEXT, c.TEXT),
        (Colors.TEXT_MUTED, c.TEXT_MUTED),
        (Colors.TEXT_DIM, c.TEXT_DIM),
    ]
    for old, new in replacements:
        qss = qss.replace(old, new)
    return qss
