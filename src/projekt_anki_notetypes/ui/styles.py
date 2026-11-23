"""Ankizin UI Design System.

theme-adaptive tokens, HiDPI icon loader,
screen-aware dialog sizing (for 13" MacBooks and high-DPI Retina screens),
and reusable components used across the Onboarding Wizard, Study Hub
(Lern-Zentrale), and Maintenance Center.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Callable, Iterable, Optional

from aqt.qt import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGuiApplication,
    QHBoxLayout,
    QLabel,
    QPalette,
    QPixmap,
    QPushButton,
    QRadioButton,
    QSize,
    QSizePolicy,
    Qt,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"

COLORS = {
    "accent": "#3B82D6",
    "accent_dim": "#2B6BB8",
    "accent_glow": "#5A9CE6",
    "accent_soft": "rgba(59, 130, 214, 0.13)",
    "success": "#2E9E5B",
    "success_soft": "rgba(46, 158, 91, 0.14)",
    "warning": "#D97706",
    "warning_soft": "rgba(217, 119, 6, 0.14)",
    "yield_strong": "#D97706",
    "yield_light": "#CA8A04",
    "danger": "#D64545",
    "danger_soft": "rgba(214, 69, 69, 0.14)",
    "border": "rgba(128, 128, 128, 0.24)",
    "border_medium": "rgba(128, 128, 128, 0.40)",
    "border_accent": "rgba(59, 130, 214, 0.45)",
    "muted_bg": "rgba(128, 128, 128, 0.10)",
    "scroll_track": "rgba(59, 130, 214, 0.08)",
    "scroll_handle": "rgba(59, 130, 214, 0.34)",
    "scroll_handle_hov": "rgba(59, 130, 214, 0.58)",
}

C = COLORS

ANKIZIN_STYLE = f"""
QDialog, QWidget {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI',
                 'Helvetica Neue', Ubuntu, sans-serif;
    font-size: 13px;
}}

QGroupBox {{
    border: 1px solid {C['border']};
    border-radius: 10px;
    margin-top: 12px;
    padding: 14px 12px 12px 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 3px;
    color: {C['accent']};
}}

QFrame#ankizin_card, QFrame#card_panel {{
    background-color: palette(base);
    border: 1px solid {C['border']};
    border-radius: 11px;
}}
QFrame#ankizin_card_soft {{
    background-color: {C['muted_bg']};
    border: 1px solid {C['border']};
    border-radius: 10px;
}}
QFrame#ankizin_card_accent {{
    background-color: {C['accent_soft']};
    border: 1px solid {C['border_accent']};
    border-radius: 10px;
}}

QLineEdit {{
    background-color: palette(base);
    border: 1.5px solid {C['border']};
    border-radius: 8px;
    color: palette(text);
    padding: 7px 12px;
    font-size: 13px;
    selection-background-color: {C['accent']};
    selection-color: white;
    min-height: 20px;
}}
QLineEdit:focus {{
    border: 1.5px solid {C['accent']};
}}
QLineEdit:hover:!focus {{
    border: 1.5px solid {C['border_medium']};
}}

QComboBox {{
    background-color: palette(base);
    border: 1.5px solid {C['border']};
    border-radius: 8px;
    color: palette(text);
    padding: 6px 28px 6px 12px;
    font-size: 13px;
    min-width: 110px;
    min-height: 20px;
}}
QComboBox:focus, QComboBox:on {{
    border: 1.5px solid {C['accent']};
}}
QComboBox:hover:!focus {{
    border: 1.5px solid {C['border_medium']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
    subcontrol-origin: padding;
    subcontrol-position: right center;
}}
QComboBox::down-arrow {{
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {C['accent']};
}}
QComboBox QAbstractItemView {{
    background-color: palette(base);
    border: 1.5px solid {C['border_accent']};
    border-radius: 7px;
    color: palette(text);
    padding: 4px;
    outline: none;
    selection-background-color: {C['accent']};
    selection-color: white;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: 4px;
    min-height: 22px;
}}

QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {C['accent_glow']}, stop:1 {C['accent']});
    border: none;
    border-radius: 8px;
    color: white;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6AAAEF, stop:1 {C['accent_dim']});
}}
QPushButton:pressed {{
    background: {C['accent_dim']};
}}
QPushButton:disabled {{
    background: rgba(128, 128, 128, 0.22);
    color: rgba(128, 128, 128, 0.65);
}}

QPushButton#secondary {{
    background: transparent;
    border: 1.5px solid {C['border_medium']};
    color: palette(text);
    font-weight: 600;
}}
QPushButton#secondary:hover {{
    background: {C['accent_soft']};
    border: 1.5px solid {C['accent']};
    color: {C['accent']};
}}
QPushButton#secondary:pressed {{
    background: rgba(59, 130, 214, 0.22);
}}
QPushButton#secondary:disabled {{
    background: transparent;
    border: 1.5px solid {C['border']};
    color: rgba(128, 128, 128, 0.55);
}}

QPushButton#danger {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #E25C5C, stop:1 {C['danger']});
    color: white;
}}
QPushButton#danger:hover {{
    background: #BE3838;
}}

QPushButton#danger_outline {{
    background: transparent;
    border: 1.5px solid rgba(214, 69, 69, 0.55);
    color: {C['danger']};
    font-weight: 600;
}}
QPushButton#danger_outline:hover {{
    background: {C['danger_soft']};
    border: 1.5px solid {C['danger']};
}}

QPushButton#ghost {{
    background: transparent;
    border: none;
    color: {C['accent']};
    padding: 6px 10px;
    font-weight: 600;
}}
QPushButton#ghost:hover {{
    background: {C['accent_soft']};
}}

QCheckBox, QRadioButton {{
    font-size: 13px;
    spacing: 9px;
    padding: 4px 2px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px;
    height: 17px;
    border: 1.5px solid {C['border_medium']};
    background-color: palette(base);
}}
QCheckBox::indicator {{
    border-radius: 5px;
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1.5px solid {C['accent']};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {C['accent']};
    border: 1.5px solid {C['accent']};
}}

QScrollArea {{
    border: 1px solid {C['border']};
    border-radius: 10px;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

QTreeWidget, QListWidget {{
    background-color: palette(base);
    border: 1px solid {C['border']};
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}
QTreeWidget {{
    show-decoration-selected: 1;
}}
QListWidget::item {{
    padding: 5px 6px;
    border-radius: 6px;
}}
QTreeWidget::item {{
    padding: 5px 6px;
    border: none;
    border-radius: 0px;
}}
QTreeWidget::item:hover, QListWidget::item:hover {{
    background-color: {C['accent_soft']};
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: rgba(59, 130, 214, 0.22);
    color: palette(text);
}}
QTreeWidget#ankizin_topic_tree {{
    selection-background-color: transparent;
    show-decoration-selected: 0;
}}
QTreeWidget#ankizin_topic_tree::item {{
    padding: 5px 6px;
    border: none;
    border-radius: 0px;
    background: transparent;
}}
QTreeWidget#ankizin_topic_tree::item:hover,
QTreeWidget#ankizin_topic_tree::item:selected,
QTreeWidget#ankizin_topic_tree::item:selected:hover,
QTreeWidget#ankizin_topic_tree::item:selected:active,
QTreeWidget#ankizin_topic_tree::item:selected:!active {{
    background: transparent;
    color: palette(text);
}}

QScrollBar:vertical {{
    background: {C['scroll_track']};
    width: 7px;
    border-radius: 3px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {C['scroll_handle']};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C['scroll_handle_hov']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QScrollBar:horizontal {{
    background: {C['scroll_track']};
    height: 7px;
    border-radius: 3px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {C['scroll_handle']};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C['scroll_handle_hov']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

QProgressBar {{
    background-color: {C['muted_bg']};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C['accent']}, stop:1 {C['accent_glow']});
    border-radius: 4px;
}}

QLabel {{
    background-color: transparent;
}}

QSplitter::handle {{
    background: {C['border']};
    width: 1px;
    margin: 6px 4px;
}}
"""


def escape_qt_mnemonic(text: str) -> str:
    """Escape literal '&' for Qt widgets so it isn't parsed as a mnemonic."""
    return text.replace("&", "&&")


def resolve_parent(parent, fallback=None) -> Optional[QWidget]:
    """Return a valid QWidget parent or None (guards against QAction bools or test stubs)."""
    if isinstance(parent, QWidget):
        return parent
    if isinstance(fallback, QWidget):
        return fallback
    return None


def set_scoped_style(widget: QWidget, object_name: str, declarations: str) -> None:
    """Style a single widget via objectName so its QToolTip stays readable on macOS."""
    widget.setObjectName(object_name)
    widget.setStyleSheet(f"#{object_name} {{ {declarations} }}")


def is_dark_mode() -> bool:
    """Detect whether the current Qt application palette is dark."""
    try:
        app = QApplication.instance()
        if app is None:
            return False
        return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    except Exception:
        return False


def apply_ankizin_style(widget: QWidget) -> None:
    """Apply the Ankizin stylesheet plus concrete tooltip colors for macOS."""
    dark = is_dark_mode()
    tt_bg = "#252932" if dark else "#F9FAFB"
    tt_text = "#F3F4F6" if dark else "#111827"
    tt_border = "rgba(180, 190, 210, 0.35)" if dark else "rgba(59, 130, 214, 0.35)"

    tooltip_css = f"""
QToolTip {{
    background-color: {tt_bg};
    color: {tt_text};
    border: 1px solid {tt_border};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    opacity: 255;
}}
"""
    widget.setStyleSheet(ANKIZIN_STYLE + tooltip_css)


def load_ankizin_pixmap(filename: str = "ankizin.png", size: int = 40) -> QPixmap:
    """Load an image from ankizin/resources scaled crisply for Retina displays."""
    path = RESOURCES_DIR / filename
    pm = QPixmap(str(path))
    if pm.isNull():
        return pm
    try:
        app = QApplication.instance()
        dpr = app.devicePixelRatio() if app else 1.0
    except Exception:
        dpr = 1.0
    target = max(1, round(size * dpr))
    scaled = pm.scaled(
        QSize(target, target),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled


def fit_dialog_to_screen(
    dialog: QDialog,
    pref_w: int,
    pref_h: int,
    min_w: int = 640,
    min_h: int = 440,
) -> None:
    """Size dialog comfortably while clamping to 88% of screen (13\" MacBook safe)."""
    try:
        screen = dialog.screen() or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
    except Exception:
        avail = None

    if avail is not None:
        max_w = max(520, int(avail.width() * 0.88))
        max_h = max(420, int(avail.height() * 0.88))
        w = min(pref_w, max_w)
        h = min(pref_h, max_h)
        dialog.setMinimumSize(min(min_w, max_w), min(min_h, max_h))
        dialog.resize(w, h)
    else:
        dialog.setMinimumSize(min_w, min_h)
        dialog.resize(pref_w, pref_h)


def disable_auto_default(dialog: QDialog, keep_primary: Optional[QPushButton] = None) -> None:
    """Prevent every button on macOS from looking like a default action button."""
    for btn in dialog.findChildren(QAbstractButton):
        if isinstance(btn, QPushButton):
            is_primary = keep_primary is not None and btn is keep_primary
            btn.setAutoDefault(is_primary)
            btn.setDefault(is_primary)


def make_header(
    title: str,
    subtitle: str = "",
    right_widget: Optional[QWidget] = None,
    icon_size: int = 38,
) -> QWidget:
    """Clean branded header bar with Ankizin mascot, title, subtitle, and bottom hairline."""
    header = QWidget()
    header.setObjectName("ankizin_header")
    header.setStyleSheet("#ankizin_header, #ankizin_header QWidget { background: transparent; }")

    outer = QVBoxLayout(header)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    inner = QWidget()
    row = QHBoxLayout(inner)
    row.setContentsMargins(18, 12, 18, 12)
    row.setSpacing(12)

    pm = load_ankizin_pixmap("ankizin.png", icon_size)
    if not pm.isNull():
        logo = QLabel()
        logo.setObjectName("ankizin_header_logo")
        logo.setPixmap(pm)
        logo.setFixedSize(icon_size, icon_size)
        row.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)

    text_col = QVBoxLayout()
    text_col.setSpacing(2)

    title_lbl = QLabel(title)
    set_scoped_style(
        title_lbl,
        "ankizin_header_title",
        f"font-size: 16px; font-weight: 700; color: {C['accent']}; background: transparent;",
    )
    text_col.addWidget(title_lbl)

    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setWordWrap(True)
        set_scoped_style(
            sub_lbl,
            "ankizin_header_sub",
            "font-size: 12px; color: palette(placeholderText); background: transparent;",
        )
        text_col.addWidget(sub_lbl)

    row.addLayout(text_col, 1)

    if right_widget is not None:
        row.addWidget(right_widget, 0, Qt.AlignmentFlag.AlignVCenter)

    outer.addWidget(inner)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {C['border']}; border: none;")
    outer.addWidget(line)

    return header


def make_card(object_name: str = "ankizin_card", padding: tuple[int, int, int, int] = (14, 12, 14, 12)) -> tuple[QFrame, QVBoxLayout]:
    """Create a rounded surface card and its inner vertical layout."""
    card = QFrame()
    card.setObjectName(object_name)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*padding)
    layout.setSpacing(8)
    return card, layout


def make_badge(text: str, tone: str = "neutral") -> QLabel:
    """Create a compact rounded pill badge."""
    palette_map = {
        "accent": (C["accent_soft"], C["accent"], C["border_accent"]),
        "success": (C["success_soft"], C["success"], "rgba(46, 158, 91, 0.38)"),
        "warning": (C["warning_soft"], C["warning"], "rgba(217, 119, 6, 0.38)"),
        "danger": (C["danger_soft"], C["danger"], "rgba(214, 69, 69, 0.38)"),
        "neutral": (C["muted_bg"], "palette(text)", C["border"]),
    }
    bg, fg, border = palette_map.get(tone, palette_map["neutral"])
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    set_scoped_style(
        lbl,
        f"ankizin_badge_{tone}",
        f"background-color: {bg}; color: {fg}; border: 1px solid {border}; "
        "border-radius: 10px; padding: 2px 9px; font-size: 11px; font-weight: 600;",
    )
    return lbl


def _make_wrapped_toggle(
    btn: QAbstractButton,
    title: str,
    description: str = "",
    bold_title: bool = True,
) -> QWidget:
    """Pair a checkbox/radio indicator with word-wrapped clickable labels (macOS safe)."""
    row_widget = QWidget()
    row_widget.setObjectName("ankizin_wrapped_toggle")
    row_widget.setStyleSheet("#ankizin_wrapped_toggle, #ankizin_wrapped_toggle QLabel { background: transparent; }")
    row_widget.setCursor(Qt.CursorShape.PointingHandCursor)

    btn.setText("")
    btn.setFixedWidth(22)

    row = QHBoxLayout(row_widget)
    row.setContentsMargins(0, 2, 0, 2)
    row.setSpacing(8)
    row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)

    text_col = QVBoxLayout()
    text_col.setContentsMargins(0, 1, 0, 0)
    text_col.setSpacing(2)

    title_lbl = QLabel(title)
    title_lbl.setWordWrap(True)
    title_lbl.setTextFormat(Qt.TextFormat.RichText)
    if bold_title:
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
    else:
        title_lbl.setStyleSheet("font-size: 13px;")
    text_col.addWidget(title_lbl)

    if description:
        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setTextFormat(Qt.TextFormat.RichText)
        desc_lbl.setStyleSheet("font-size: 12px; color: palette(placeholderText);")
        text_col.addWidget(desc_lbl)

    row.addLayout(text_col, 1)

    def _on_press(event) -> None:
        if btn.isEnabled():
            btn.click()
        event.accept()

    row_widget.mousePressEvent = _on_press
    return row_widget


def make_wrapped_checkbox(
    title: str,
    description: str = "",
    checked: bool = True,
    bold_title: bool = True,
) -> tuple[QWidget, QCheckBox]:
    """Create a word-wrapped checkbox row whose text never clips on macOS."""
    cb = QCheckBox()
    cb.setChecked(checked)
    row = _make_wrapped_toggle(cb, title, description=description, bold_title=bold_title)
    return row, cb


def make_wrapped_radio(
    title: str,
    description: str = "",
    checked: bool = False,
    bold_title: bool = True,
) -> tuple[QWidget, QRadioButton]:
    """Create a word-wrapped radio row whose text never clips on macOS."""
    rb = QRadioButton()
    rb.setChecked(checked)
    row = _make_wrapped_toggle(rb, title, description=description, bold_title=bold_title)
    return row, rb


class SegmentedControl(QWidget):
    """macOS-style pill segmented toggle control."""

    changed = pyqtSignal(str)

    def __init__(
        self,
        options: Iterable[tuple[str, str, str]],
        initial_key: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ankizin_segmented")
        self._options = list(options)
        self._buttons: dict[str, QPushButton] = {}
        self._current: Optional[str] = None

        self.setStyleSheet(
            f"#ankizin_segmented {{ background-color: {C['muted_bg']}; "
            f"border: 1px solid {C['border']}; border-radius: 9px; }}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)

        for key, label, tip in self._options:
            btn = QPushButton(escape_qt_mnemonic(label))
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if tip:
                btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, k=key: self._select(k, emit=True))
            row.addWidget(btn)
            self._buttons[key] = btn

        target = initial_key if initial_key in self._buttons else (self._options[0][0] if self._options else None)
        if target is not None:
            self._select(target, emit=False)

    def current_key(self) -> Optional[str]:
        return self._current

    def set_current(self, key: str, emit: bool = False) -> None:
        if key in self._buttons:
            self._select(key, emit=emit)

    def _select(self, key: str, emit: bool) -> None:
        if self._current == key:
            self._refresh_styles()
            return
        self._current = key
        self._refresh_styles()
        if emit:
            self.changed.emit(key)

    def _refresh_styles(self) -> None:
        for key, btn in self._buttons.items():
            active = key == self._current
            btn.setChecked(active)
            if active:
                btn.setStyleSheet(
                    "QPushButton { "
                    f"background-color: {C['accent']}; color: white; border: none; "
                    "border-radius: 6px; padding: 5px 11px; font-size: 12px; "
                    "font-weight: 600; min-height: 16px; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { "
                    "background: transparent; color: palette(text); border: none; "
                    "border-radius: 6px; padding: 5px 11px; font-size: 12px; "
                    "font-weight: 500; min-height: 16px; }"
                    f"QPushButton:hover {{ background-color: {C['accent_soft']}; }}"
                )


class StepRail(QWidget):
    """Vertical numbered step rail for the Onboarding Wizard."""

    step_clicked = pyqtSignal(str)

    def __init__(self, steps: list[tuple[str, str]], parent: Optional[QWidget] = None, width: int = 168) -> None:
        super().__init__(parent)
        self.setFixedWidth(width)
        self._steps = steps
        self._labels: dict[str, QLabel] = {}
        self._clickable: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 2, 0)
        layout.setSpacing(4)

        for key, title in steps:
            lbl = QLabel()
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            lbl.linkActivated.connect(lambda _=None, k=key: self._on_link(k))
            layout.addWidget(lbl)
            self._labels[key] = lbl

        layout.addStretch()

    def _on_link(self, key: str) -> None:
        if key in self._clickable:
            self.step_clicked.emit(key)

    def set_state(
        self,
        current: str,
        done_steps: set[str],
        skipped_steps: set[str],
        revisitable: Callable[[str], bool],
    ) -> None:
        self._clickable.clear()
        for idx, (key, title) in enumerate(self._steps, 1):
            lbl = self._labels[key]
            safe_title = html.escape(title)
            if key == current:
                lbl.setText(
                    f"<div style='padding:5px 8px;border-radius:7px;font-size:12px;"
                    f"background:{C['accent_soft']};color:{C['accent']};font-weight:700;'>"
                    f"{idx}. {safe_title}</div>"
                )
            elif revisitable(key):
                self._clickable.add(key)
                mark = "–" if key in skipped_steps else "✓"
                color = "gray" if key in skipped_steps else C["success"]
                lbl.setText(
                    f"<div style='padding:4px 8px;font-size:12px;'>"
                    f"<span style='color:{color};font-weight:700;'>{mark}</span>&nbsp; "
                    f"<a href='#' style='color:{C['accent']};text-decoration:none;'>{safe_title}</a></div>"
                )
            elif key in skipped_steps:
                lbl.setText(
                    f"<div style='padding:4px 8px;font-size:12px;color:gray;'>–&nbsp; {safe_title} (übersprungen)</div>"
                )
            elif key in done_steps:
                lbl.setText(
                    f"<div style='padding:4px 8px;font-size:12px;'>"
                    f"<span style='color:{C['success']};font-weight:700;'>✓</span>&nbsp; {safe_title}</div>"
                )
            else:
                lbl.setText(
                    f"<div style='padding:4px 8px;font-size:12px;color:gray;'>{idx}. {safe_title}</div>"
                )
