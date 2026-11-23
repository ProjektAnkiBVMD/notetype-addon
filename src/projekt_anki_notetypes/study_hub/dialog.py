"""Ankizin Lern-Zentrale (Study Hub Dialog).

A top-to-bottom 3-step guided flow replacing Anki's Browser:
  ① Thema wählen (full-width category pills, smart search, & topic tree)
  ② Wichtigkeit (Yield) wählen (full-width readable cards, zero clipping)
  ③ Freischalten & lernen (clear action + daily limit explanation + progress)

Opens instantaneously with a skeleton loading state while building `AnkizinTagIndex`
on a background `QueryOp` thread, and performs all card actions without freezing.
"""
from __future__ import annotations

import html as _html
from typing import Optional

from aqt import mw
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import (
    QButtonGroup,
    QCheckBox,
    QColor,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QModelIndex,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QRect,
    QRectF,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QStyleOptionViewItem,
    QTimer,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import askUser, showInfo, tooltip

from ..compat import make_op_changes
from ..constants import ADDON_DIR_NAME
from ..onboarding.engine import OpResult
from ..ui import (
    COLORS,
    apply_ankizin_style,
    disable_auto_default,
    escape_qt_mnemonic,
    fit_dialog_to_screen,
    make_badge,
    make_card,
    make_header,
    make_wrapped_radio,
    resolve_parent,
)
from . import smart_decks
from .tag_index import (
    CATEGORIES,
    AnkizinTagIndex,
    TopicNode,
    build_tag_index,
    build_topic_search,
)

_study_hub_dialog: Optional["AnkizinStudyHubDialog"] = None

_YIELD_CHOICES: list[tuple[str, str, str]] = [
    ("stark", "🔥 Highest Yield (stark gelb)", "Nur das wichtigste IMPP-Schlüsselwissen"),
    ("high_yield", "⭐ High Yield (stark + leicht gelb)", "Optimal fürs Staatsexamen (Empfohlen)"),
    ("standard", "📘 Standard (ohne Low Yield)", "Alle regulären Karten ohne Kolibri-Details"),
    ("all", "📦 Alle Karten (inkl. Low Yield)", "Komplettes Thema inklusive Spezialwissen"),
]

_YIELD_LABELS: dict[str, str] = {k: title for k, title, _ in _YIELD_CHOICES}

_SEARCH_PLACEHOLDERS: dict[str, str] = {
    "amboss": "🔍 AMBOSS-Artikel oder Fach suchen (z. B. Pneumonie, Herzinsuffizienz)…",
    "lernplan": "🔍 Lerntag oder Thema suchen (z. B. Tag 9, Kardiologie, Pneumonie)…",
    "top100": "🔍 TOP-100 Kapitel suchen…",
    "m3": "🔍 M3-Thema suchen…",
    "vorklinik": "🔍 Vorklinik-Fach oder Thema suchen…",
    "unis": "🔍 Uni, Semester oder Modul suchen…",
}

_STEP_TITLES: list[str] = [
    "① Thema wählen",
    "② Wichtigkeit (Yield)",
    "③ Freischalten & lernen",
]


def _get_conf() -> dict:
    if mw is None or getattr(mw, "addonManager", None) is None:
        return {}
    return mw.addonManager.getConfig(ADDON_DIR_NAME) or {}


def _save_conf(conf: dict) -> None:
    if mw is not None and getattr(mw, "addonManager", None) is not None:
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)


class _ClickableYieldCard(QFrame):
    """Full-width card that selects its associated radio button on click anywhere."""

    def __init__(self, radio: QRadioButton, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._radio = radio
        self.setObjectName("ankizin_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._radio.isChecked():
            self._radio.click()
        super().mouseReleaseEvent(event)


class _AnkizinTopicTree(QTreeWidget):
    """QTreeWidget painting one continuous full-row highlight & crisp branch chevrons."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ankizin_topic_tree")
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._hover_index = QModelIndex()

    def _row_repaint_rect(self, index: QModelIndex) -> QRect:
        r = self.visualRect(index)
        if not r.isValid():
            return QRect()
        return QRect(0, r.y() - 1, self.viewport().width(), r.height() + 2)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        idx = self.indexAt(pos)
        idx = idx.siblingAtColumn(0) if idx.isValid() else QModelIndex()
        if idx != self._hover_index:
            old_idx = self._hover_index
            self._hover_index = idx
            if old_idx.isValid():
                self.viewport().update(self._row_repaint_rect(old_idx))
            if idx.isValid():
                self.viewport().update(self._row_repaint_rect(idx))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover_index.isValid():
            old_idx = self._hover_index
            self._hover_index = QModelIndex()
            self.viewport().update(self._row_repaint_rect(old_idx))
        super().leaveEvent(event)

    def drawRow(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        row_idx = index.siblingAtColumn(0) if index.isValid() else index
        is_sel = bool(self.selectionModel() and row_idx.isValid() and self.selectionModel().isSelected(row_idx))
        is_hov = bool(row_idx.isValid() and row_idx == self._hover_index)
        if is_sel or is_hov:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if is_sel and is_hov:
                fill = QColor(59, 130, 214, 62)
            elif is_sel:
                fill = QColor(59, 130, 214, 46)
            else:
                fill = QColor(59, 130, 214, 24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(option.rect.adjusted(2, 1, -2, -1)), 6.0, 6.0)
            painter.restore()

        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.state &= ~QStyle.StateFlag.State_MouseOver
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().drawRow(painter, opt, index)

    def drawBranches(self, painter: QPainter, rect: QRect, index: QModelIndex) -> None:
        """Draw crisp chevrons only for parent rows; never draw OS selection rectangles."""
        model = self.model()
        if model is None or not model.hasChildren(index) or rect.width() < 8:
            return
        box_w = min(self.indentation(), rect.width())
        cx = rect.right() - box_w / 2.0 + 1.0
        cy = rect.center().y() + 0.5

        path = QPainterPath()
        if self.isExpanded(index):
            path.moveTo(cx - 3.5, cy - 1.5)
            path.lineTo(cx, cy + 2.5)
            path.lineTo(cx + 3.5, cy - 1.5)
        else:
            path.moveTo(cx - 1.5, cy - 3.5)
            path.lineTo(cx + 2.5, cy)
            path.lineTo(cx - 1.5, cy + 3.5)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        col = self.palette().color(QPalette.ColorRole.PlaceholderText)
        pen = QPen(col, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()


class AnkizinStudyHubDialog(QDialog):
    """Calm top-to-bottom 3-step Study Hub replacing Anki's Browser for everyday studying."""

    def __init__(self, parent: Optional[QWidget] = None, *, sync_load: bool = False) -> None:
        super().__init__(resolve_parent(parent, mw))
        self.setWindowTitle("Ankizin Lern-Zentrale")
        apply_ankizin_style(self)
        fit_dialog_to_screen(self, 860, 650, 680, 500)

        conf = _get_conf()
        hub_conf = conf.get("study_hub") or {}

        self._index = AnkizinTagIndex({}, [], {})
        self._daily_limit_info = smart_decks.DailyNewLimitInfo()
        self._smart_decks_cache: list[smart_decks.SmartDeckInfo] = []
        self._is_loaded: bool = False
        self._current_step: int = 0

        self._active_category: str = hub_conf.get("last_category", "amboss")
        self._yield_preset: str = hub_conf.get("last_yield", "high_yield")
        self._mode: str = hub_conf.get("last_mode", "unsuspend")
        self._top100_only: bool = False

        self._cat_buttons: dict[str, QPushButton] = {}
        self._node_by_key: dict[str, TopicNode] = {}
        self._checked_keys: set[str] = set()
        self._focused_node: Optional[TopicNode] = None
        self._populating_tree = False
        self._showing_smart_page = False
        self._search_all_categories = False

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._populate_topic_tree)

        self._build_ui()
        self._main_stack.setCurrentIndex(0)
        disable_auto_default(self, self._primary_btn)
        self._start_initial_load(sync_load=sync_load)

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr_right = QWidget()
        hdr_row = QHBoxLayout(hdr_right)
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(8)

        self._smart_nav_btn = QPushButton("📌 Smart-Stapel")
        self._smart_nav_btn.setObjectName("secondary")
        self._smart_nav_btn.setAutoDefault(False)
        self._smart_nav_btn.setToolTip("Eigene gefilterte Smart-Lernstapel ansehen und verwalten")
        self._smart_nav_btn.clicked.connect(self._toggle_smart_page)
        hdr_row.addWidget(self._smart_nav_btn)

        maint_btn = QPushButton("Wartung")
        maint_btn.setObjectName("secondary")
        maint_btn.setAutoDefault(False)
        maint_btn.clicked.connect(self._open_maintenance)
        hdr_row.addWidget(maint_btn)

        root.addWidget(
            make_header(
                "Ankizin Lern-Zentrale",
                "In 3 einfachen Schritten zum Lernen — ganz ohne Kartenverwaltung",
                right_widget=hdr_right,
            )
        )

        # Stack: 0 = Skeleton Loading, 1 = Empty State, 2 = 3-Step Flow, 3 = Smart-Stapel
        self._main_stack = QStackedWidget()
        root.addWidget(self._main_stack, 1)

        self._main_stack.addWidget(self._build_loading_page())
        self._main_stack.addWidget(self._build_empty_page())
        self._main_stack.addWidget(self._build_flow_page())
        self._main_stack.addWidget(self._build_smart_decks_page())

    def _build_loading_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 36, 48, 36)
        lay.addStretch()

        card, card_lay = make_card("ankizin_card", padding=(28, 24, 28, 24))
        card_lay.setSpacing(12)

        self._load_title = QLabel("<b>Deine Ankizin-Themen werden geladen…</b>")
        self._load_title.setWordWrap(True)
        self._load_title.setStyleSheet("font-size: 16px;")
        self._load_sub = QLabel("Einen kurzen Moment — wir ordnen deine Kapitel und zählen aktive Karten.")
        self._load_sub.setWordWrap(True)
        self._load_sub.setStyleSheet("font-size: 13px; color: palette(placeholderText);")

        self._load_prog = QProgressBar()
        self._load_prog.setRange(0, 0)
        self._load_prog.setTextVisible(False)
        self._load_prog.setFixedHeight(7)

        card_lay.addWidget(self._load_title)
        card_lay.addWidget(self._load_sub)
        card_lay.addWidget(self._load_prog)

        # Crisp macOS-style skeleton placeholder rows
        self._skeleton_wrap = QWidget()
        skel_lay = QVBoxLayout(self._skeleton_wrap)
        skel_lay.setContentsMargins(0, 6, 0, 0)
        skel_lay.setSpacing(9)
        for fill_pct in (78, 62, 88, 54, 70):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
            bar = QFrame()
            bar.setFixedHeight(14)
            bar.setStyleSheet(f"background-color: {COLORS['muted_bg']}; border-radius: 7px;")
            count_pill = QFrame()
            count_pill.setFixedHeight(14)
            count_pill.setFixedWidth(48)
            count_pill.setStyleSheet(f"background-color: {COLORS['muted_bg']}; border-radius: 7px;")
            row.addWidget(bar, fill_pct)
            row.addStretch(100 - fill_pct)
            row.addWidget(count_pill)
            skel_lay.addLayout(row)
        card_lay.addWidget(self._skeleton_wrap)

        self._load_err_lbl = QLabel()
        self._load_err_lbl.setWordWrap(True)
        self._load_err_lbl.setVisible(False)
        card_lay.addWidget(self._load_err_lbl)

        self._load_retry_btn = QPushButton("Erneut versuchen")
        self._load_retry_btn.setAutoDefault(False)
        self._load_retry_btn.setVisible(False)
        self._load_retry_btn.clicked.connect(lambda: self._start_initial_load(sync_load=False))
        card_lay.addWidget(self._load_retry_btn, 0, Qt.AlignmentFlag.AlignLeft)

        lay.addWidget(card)
        lay.addStretch()
        return page

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 48, 48, 48)
        lay.addStretch()
        card, card_lay = make_card("ankizin_card_accent", padding=(24, 22, 24, 22))
        title = QLabel("<b>Noch kein Ankizin-Deck gefunden</b>")
        title.setStyleSheet("font-size: 16px;")
        desc = QLabel(
            "Starte einfach unseren Einrichtungs-Assistenten — er installiert AnkiCollab und lädt das "
            "aktuelle Ankizin-Deck automatisch für dich herunter."
        )
        desc.setWordWrap(True)
        btn = QPushButton("Einrichtungs-Assistent starten →")
        btn.setAutoDefault(False)
        btn.clicked.connect(self._open_wizard)
        card_lay.addWidget(title)
        card_lay.addWidget(desc)
        card_lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(card)
        lay.addStretch()
        return page

    def _build_flow_page(self) -> QWidget:
        """Full-width top-to-bottom 3-step explorer without any horizontal clipping."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 12, 18, 14)
        lay.setSpacing(10)

        # Horizontal top stepper bar
        stepper_wrap = QWidget()
        stepper_row = QHBoxLayout(stepper_wrap)
        stepper_row.setContentsMargins(0, 0, 0, 2)
        stepper_row.setSpacing(8)
        stepper_row.addStretch()

        self._step_btns: list[QPushButton] = []
        for idx, title in enumerate(_STEP_TITLES):
            btn = QPushButton(escape_qt_mnemonic(title))
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, s=idx: self._go_to_step(s))
            self._step_btns.append(btn)
            stepper_row.addWidget(btn)
            if idx < len(_STEP_TITLES) - 1:
                sep = QLabel("›")
                sep.setStyleSheet("color: palette(placeholderText); font-size: 15px; font-weight: 600;")
                stepper_row.addWidget(sep)

        stepper_row.addStretch()
        lay.addWidget(stepper_wrap)

        self._step_stack = QStackedWidget()
        self._step_stack.addWidget(self._build_step1_topic_page())
        self._step_stack.addWidget(self._build_step2_yield_page())
        self._step_stack.addWidget(self._build_step3_action_page())
        lay.addWidget(self._step_stack, 1)

        return page

    def _make_vertical_scroll(self, name: str) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName(name)
        scroll.setStyleSheet(f"#{name} {{ border: none; background: transparent; }}")
        content = QWidget()
        content.setObjectName(f"{name}_wrap")
        content.setStyleSheet(f"#{name}_wrap {{ background: transparent; }}")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(2, 2, 4, 6)
        content_lay.setSpacing(12)
        scroll.setWidget(content)
        return scroll, content_lay

    def _build_step1_topic_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        topic_card, card_lay = make_card("ankizin_card", padding=(14, 12, 14, 12))
        card_lay.setSpacing(8)

        # Category pills strip
        self._cat_layout = QHBoxLayout()
        self._cat_layout.setContentsMargins(0, 0, 0, 2)
        self._cat_layout.setSpacing(6)
        card_lay.addLayout(self._cat_layout)

        # Full-width smart search bar
        self._search_input = QLineEdit()
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setPlaceholderText("🔍 AMBOSS-Artikel oder Fach suchen (z. B. Pneumonie, Herzinsuffizienz)…")
        self._search_input.textChanged.connect(self._on_search_text_changed)
        card_lay.addWidget(self._search_input)

        # Compact filter & clear row
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)
        self._top100_cb = QCheckBox("⭐ Nur TOP-100 Themen")
        self._top100_cb.setChecked(self._top100_only)
        self._top100_cb.setToolTip("Zeigt nur die 100 wichtigsten Prüfungskapitel und zählt auch nur deren Karten.")
        self._top100_cb.toggled.connect(self._on_top100_toggled)
        filter_row.addWidget(self._top100_cb)
        filter_row.addStretch()
        self._clear_sel_btn = QPushButton("Auswahl aufheben")
        self._clear_sel_btn.setObjectName("ghost")
        self._clear_sel_btn.setAutoDefault(False)
        self._clear_sel_btn.setVisible(False)
        self._clear_sel_btn.clicked.connect(self._clear_checked)
        filter_row.addWidget(self._clear_sel_btn)
        card_lay.addLayout(filter_row)

        # Zero-hit cross-category fallback bar
        self._fallback_bar = QWidget()
        fb_row = QHBoxLayout(self._fallback_bar)
        fb_row.setContentsMargins(2, 2, 2, 2)
        fb_row.setSpacing(8)
        self._fallback_lbl = QLabel()
        self._fallback_lbl.setStyleSheet("font-size: 12px; color: palette(placeholderText);")
        self._fallback_btn = QPushButton("In allen Bereichen suchen")
        self._fallback_btn.setObjectName("ghost")
        self._fallback_btn.setAutoDefault(False)
        self._fallback_btn.clicked.connect(self._enable_all_categories_search)
        fb_row.addWidget(self._fallback_lbl)
        fb_row.addWidget(self._fallback_btn)
        fb_row.addStretch()
        self._fallback_bar.setVisible(False)
        card_lay.addWidget(self._fallback_bar)

        # Compact 100-Tage-Plan bar
        self._lernplan_bar = QWidget()
        lp_row = QHBoxLayout(self._lernplan_bar)
        lp_row.setContentsMargins(0, 0, 0, 0)
        lp_row.setSpacing(6)
        self._jump_lerntag_btn = QPushButton("▶ Aktueller Lerntag")
        self._jump_lerntag_btn.setAutoDefault(False)
        self._jump_lerntag_btn.clicked.connect(self._jump_to_current_lerntag)
        self._lernplan_mgr_btn = QPushButton("Lernplan-Manager →")
        self._lernplan_mgr_btn.setObjectName("secondary")
        self._lernplan_mgr_btn.setAutoDefault(False)
        self._lernplan_mgr_btn.clicked.connect(self._open_lernplan)
        lp_row.addWidget(self._jump_lerntag_btn)
        lp_row.addStretch()
        lp_row.addWidget(self._lernplan_mgr_btn)
        self._lernplan_bar.setVisible(False)
        card_lay.addWidget(self._lernplan_bar)

        # Full-width topic tree
        self._tree = _AnkizinTopicTree()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Thema / Kapitel", "Karten"])
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setUniformRowHeights(True)
        self._tree.setIndentation(18)
        self._tree.itemChanged.connect(self._on_tree_item_changed)
        self._tree.currentItemChanged.connect(self._on_tree_current_changed)
        self._tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        card_lay.addWidget(self._tree, 1)

        lay.addWidget(topic_card, 1)

        # Sticky bottom footer bar
        footer, footer_lay = make_card("ankizin_card_soft", padding=(14, 10, 14, 10))
        foot_row = QHBoxLayout()
        foot_row.setSpacing(12)
        self._step1_summary_lbl = QLabel()
        self._step1_summary_lbl.setWordWrap(True)
        self._step1_summary_lbl.setStyleSheet("font-size: 13px;")
        foot_row.addWidget(self._step1_summary_lbl, 1)

        self._to_step2_btn = QPushButton("Weiter: Wichtigkeit wählen →")
        self._to_step2_btn.setAutoDefault(False)
        self._to_step2_btn.setEnabled(False)
        self._to_step2_btn.clicked.connect(lambda: self._go_to_step(1))
        foot_row.addWidget(self._to_step2_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        footer_lay.addLayout(foot_row)
        lay.addWidget(footer)
        return page

    def _build_step2_yield_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        scroll, content_lay = self._make_vertical_scroll("hub_step2_scroll")

        # Selection summary header card
        sel_card, sel_lay = make_card("ankizin_card", padding=(16, 12, 16, 12))
        sel_top = QHBoxLayout()
        sel_top.setSpacing(10)
        self._sel_title = QLabel()
        self._sel_title.setWordWrap(True)
        self._sel_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['accent']};")
        sel_top.addWidget(self._sel_title, 1)
        change_topic_btn = QPushButton("Thema ändern")
        change_topic_btn.setObjectName("ghost")
        change_topic_btn.setAutoDefault(False)
        change_topic_btn.clicked.connect(lambda: self._go_to_step(0))
        sel_top.addWidget(change_topic_btn, 0, Qt.AlignmentFlag.AlignTop)
        sel_lay.addLayout(sel_top)

        self._sel_crumb = QLabel()
        self._sel_crumb.setWordWrap(True)
        self._sel_crumb.setStyleSheet("font-size: 12px; color: palette(placeholderText);")
        self._sel_bar = QProgressBar()
        self._sel_bar.setTextVisible(False)
        self._sel_bar.setFixedHeight(7)
        self._sel_stats_lbl = QLabel()
        self._sel_stats_lbl.setWordWrap(True)
        self._sel_stats_lbl.setStyleSheet("font-size: 12px;")
        sel_lay.addWidget(self._sel_crumb)
        sel_lay.addWidget(self._sel_bar)
        sel_lay.addWidget(self._sel_stats_lbl)
        content_lay.addWidget(sel_card)

        prompt_lbl = QLabel("<b>Wie ausführlich möchtest du dieses Thema lernen?</b>")
        prompt_lbl.setWordWrap(True)
        prompt_lbl.setStyleSheet("font-size: 14px; padding-left: 2px;")
        content_lay.addWidget(prompt_lbl)

        self._yield_group = QButtonGroup(self)
        self._yield_radios: dict[str, QRadioButton] = {}
        self._yield_count_badges: dict[str, QLabel] = {}
        self._yield_cards: dict[str, QFrame] = {}

        for key, title, desc in _YIELD_CHOICES:
            w_row, rb = make_wrapped_radio(title, desc, checked=(key == self._yield_preset), bold_title=True)
            self._yield_group.addButton(rb)
            self._yield_radios[key] = rb
            rb.toggled.connect(lambda checked, k=key: self._on_yield_toggled(k, checked))

            y_card = _ClickableYieldCard(rb)
            y_lay = QHBoxLayout(y_card)
            y_lay.setContentsMargins(16, 12, 16, 12)
            y_lay.setSpacing(12)
            y_lay.addWidget(w_row, 1)

            badge = make_badge("0 Karten", "neutral")
            self._yield_count_badges[key] = badge
            y_lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
            self._yield_cards[key] = y_card
            content_lay.addWidget(y_card)

        content_lay.addStretch()
        lay.addWidget(scroll, 1)

        # Sticky bottom footer bar
        footer, footer_lay = make_card("ankizin_card_soft", padding=(14, 10, 14, 10))
        foot_row = QHBoxLayout()
        foot_row.setSpacing(12)
        back_btn = QPushButton("← Zurück zu Schritt 1")
        back_btn.setObjectName("secondary")
        back_btn.setAutoDefault(False)
        back_btn.clicked.connect(lambda: self._go_to_step(0))
        foot_row.addWidget(back_btn)
        foot_row.addStretch()

        self._to_step3_btn = QPushButton("Weiter: Freischalten →")
        self._to_step3_btn.setAutoDefault(False)
        self._to_step3_btn.clicked.connect(lambda: self._go_to_step(2))
        foot_row.addWidget(self._to_step3_btn)
        footer_lay.addLayout(foot_row)
        lay.addWidget(footer)
        return page

    def _build_step3_action_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        scroll, content_lay = self._make_vertical_scroll("hub_step3_scroll")

        # Compact recap card
        recap_card, recap_lay = make_card("ankizin_card_soft", padding=(14, 11, 14, 11))
        recap_row = QHBoxLayout()
        recap_row.setSpacing(10)
        self._step3_recap_lbl = QLabel()
        self._step3_recap_lbl.setWordWrap(True)
        self._step3_recap_lbl.setStyleSheet("font-size: 13px;")
        recap_row.addWidget(self._step3_recap_lbl, 1)

        change_yield_btn = QPushButton("Wichtigkeit ändern")
        change_yield_btn.setObjectName("ghost")
        change_yield_btn.setAutoDefault(False)
        change_yield_btn.clicked.connect(lambda: self._go_to_step(1))
        recap_row.addWidget(change_yield_btn, 0, Qt.AlignmentFlag.AlignTop)
        recap_lay.addLayout(recap_row)
        content_lay.addWidget(recap_card)

        prompt_lbl = QLabel("<b>Wie möchtest du diese Karten lernen?</b>")
        prompt_lbl.setWordWrap(True)
        prompt_lbl.setStyleSheet("font-size: 14px; padding-left: 2px;")
        content_lay.addWidget(prompt_lbl)

        # Mode selection card
        mode_card, mode_lay = make_card("ankizin_card", padding=(16, 14, 16, 14))
        mode_lay.setSpacing(10)
        self._mode_group = QButtonGroup(self)
        w_unsusp, self._mode_unsusp_rb = make_wrapped_radio(
            "Im Ankizin-Stapel freischalten (Empfohlen)",
            "Schaltet die gewählten Karten direkt in deinem normalen Ankizin-Stapel frei.",
            checked=(self._mode == "unsuspend"),
            bold_title=True,
        )
        w_smart, self._mode_smart_rb = make_wrapped_radio(
            "Als Smart-Lernstapel erstellen",
            "Erstellt einen eigenen gefilterten Lernstapel mit automatischer Pflege.",
            checked=(self._mode == "smart"),
            bold_title=True,
        )
        self._mode_group.addButton(self._mode_unsusp_rb)
        self._mode_group.addButton(self._mode_smart_rb)
        self._mode_unsusp_rb.toggled.connect(lambda c: self._on_mode_toggled("unsuspend", c))
        self._mode_smart_rb.toggled.connect(lambda c: self._on_mode_toggled("smart", c))
        mode_lay.addWidget(w_unsusp)
        mode_lay.addWidget(w_smart)

        self._lifecycle_combo = QComboBox()
        self._lifecycle_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._lifecycle_combo.setMinimumContentsLength(24)
        self._lifecycle_combo.addItem("Täglich mit fälligen Karten aktualisieren (is:due)", "daily")
        self._lifecycle_combo.addItem("Einmalig durchlernen & danach selbst aufräumen", "auto_clean")
        self._lifecycle_combo.setVisible(self._mode == "smart")
        mode_lay.addWidget(self._lifecycle_combo)
        content_lay.addWidget(mode_card)

        # Daily new-card limit explanation banner
        self._limit_hint_lbl = QLabel()
        self._limit_hint_lbl.setWordWrap(True)
        self._limit_hint_lbl.setStyleSheet(
            "padding: 10px 12px; border-radius: 9px; font-size: 12px; "
            "background-color: rgba(245, 158, 11, 0.12); "
            "border: 1px solid rgba(245, 158, 11, 0.35);"
        )
        self._limit_hint_lbl.setVisible(False)
        content_lay.addWidget(self._limit_hint_lbl)

        # Quiet secondary maintenance actions
        sec_row = QHBoxLayout()
        sec_row.setSpacing(8)
        self._suspend_btn = QPushButton("Auswahl pausieren")
        self._suspend_btn.setObjectName("secondary")
        self._suspend_btn.setAutoDefault(False)
        self._suspend_btn.clicked.connect(self._on_suspend_selected)
        self._post_exam_btn = QPushButton("Nach Klausur: Nur High Yield behalten")
        self._post_exam_btn.setObjectName("secondary")
        self._post_exam_btn.setAutoDefault(False)
        self._post_exam_btn.setToolTip(
            "Behält Highest Yield & High Yield aktiv und pausiert alle unwichtigeren Karten dieses Themas."
        )
        self._post_exam_btn.clicked.connect(self._on_keep_only_high_yield)
        sec_row.addWidget(self._suspend_btn)
        sec_row.addWidget(self._post_exam_btn)
        sec_row.addStretch()
        content_lay.addLayout(sec_row)

        content_lay.addStretch()
        lay.addWidget(scroll, 1)

        # Sticky bottom footer bar
        footer, footer_lay = make_card("ankizin_card_soft", padding=(14, 10, 14, 10))
        foot_row = QHBoxLayout()
        foot_row.setSpacing(12)
        back_btn = QPushButton("← Zurück zu Schritt 2")
        back_btn.setObjectName("secondary")
        back_btn.setAutoDefault(False)
        back_btn.clicked.connect(lambda: self._go_to_step(1))
        foot_row.addWidget(back_btn)
        foot_row.addStretch()

        self._primary_btn = QPushButton("Karten freischalten")
        self._primary_btn.clicked.connect(self._on_primary_action)
        foot_row.addWidget(self._primary_btn)
        footer_lay.addLayout(foot_row)
        lay.addWidget(footer)
        return page

    def _build_smart_decks_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        top_row = QHBoxLayout()
        back_btn = QPushButton("← Zurück zu den Themen")
        back_btn.setObjectName("secondary")
        back_btn.setAutoDefault(False)
        back_btn.clicked.connect(self._toggle_smart_page)
        top_row.addWidget(back_btn)
        top_row.addStretch()
        lay.addLayout(top_row)

        info, info_lay = make_card("ankizin_card_soft", padding=(12, 10, 12, 10))
        info_txt = QLabel(
            "<b>Was sind Smart-Lernstapel?</b><br>"
            "Smart-Lernstapel bündeln ausgewählte Karten vorübergehend in einem eigenen Stapel — ohne dass "
            "Lernfortschritt verloren geht. Sie aktualisieren sich täglich mit <code>is:due</code> oder räumen "
            "sich nach dem Durchlernen automatisch selbst auf."
        )
        info_txt.setWordWrap(True)
        info_lay.addWidget(info_txt)
        lay.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("smart_decks_scroll")
        scroll.setStyleSheet("#smart_decks_scroll { border: none; background: transparent; }")
        self._smart_container = QWidget()
        self._smart_container.setObjectName("smart_decks_wrap")
        self._smart_container.setStyleSheet("#smart_decks_wrap { background: transparent; }")
        self._smart_lay = QVBoxLayout(self._smart_container)
        self._smart_lay.setContentsMargins(0, 0, 4, 0)
        self._smart_lay.setSpacing(8)
        scroll.setWidget(self._smart_container)
        lay.addWidget(scroll, 1)
        return page

    # ── Asynchronous Initial Index Load ──────────────────────────────────────

    def _start_initial_load(self, *, sync_load: bool = False) -> None:
        self._load_title.setText("<b>Deine Ankizin-Themen werden geladen…</b>")
        self._load_sub.setText("Einen kurzen Moment — wir ordnen deine Kapitel und zählen aktive Karten.")
        self._load_prog.setVisible(True)
        self._skeleton_wrap.setVisible(True)
        self._load_err_lbl.setVisible(False)
        self._load_retry_btn.setVisible(False)
        self._main_stack.setCurrentIndex(0)

        col = mw.col if mw else None
        if col is None:
            self._on_initial_loaded((AnkizinTagIndex({}, [], {}), smart_decks.DailyNewLimitInfo(), []))
            return

        conf = _get_conf()

        def _load_op(bg_col):
            idx = build_tag_index(bg_col)
            lim = smart_decks.get_daily_new_limit_info(bg_col)
            smart_items = smart_decks.list_smart_decks(bg_col, conf)
            return (idx, lim, smart_items)

        if sync_load or not hasattr(getattr(mw, "taskman", None), "run_in_background"):
            try:
                payload = _load_op(col)
            except Exception as exc:
                self._on_initial_load_failed(exc)
                return
            self._on_initial_loaded(payload)
            return

        QueryOp(
            parent=self,
            op=_load_op,
            success=self._on_initial_loaded,
        ).failure(self._on_initial_load_failed).run_in_background()

    def _on_initial_loaded(self, payload) -> None:
        try:
            _ = self._main_stack.currentIndex()
        except RuntimeError:
            return

        index, limit_info, smart_items = payload
        self._is_loaded = True
        self._index = index
        self._daily_limit_info = limit_info
        self._smart_decks_cache = list(smart_items or [])
        self._node_by_key = {n.key: n for n in self._index.all_nodes}
        self._update_smart_nav_count(len(self._smart_decks_cache))

        if not self._index.available_categories():
            self._main_stack.setCurrentIndex(1)
            return

        self._refresh_category_buttons()
        self._main_stack.setCurrentIndex(2)
        self._go_to_step(0)

    def _on_initial_load_failed(self, exc: Exception) -> None:
        try:
            _ = self._main_stack.currentIndex()
        except RuntimeError:
            return

        self._load_prog.setVisible(False)
        self._skeleton_wrap.setVisible(False)
        self._load_title.setText("<b>Laden der Themen fehlgeschlagen</b>")
        self._load_err_lbl.setText(f"Fehler: {_html.escape(str(exc))}")
        self._load_err_lbl.setVisible(True)
        self._load_retry_btn.setVisible(True)
        self._main_stack.setCurrentIndex(0)

    # ── Stepper & Flow Navigation ────────────────────────────────────────────

    def _go_to_step(self, step: int) -> None:
        if step > 0 and not self._target_nodes():
            step = 0
        self._current_step = max(0, min(2, step))
        self._step_stack.setCurrentIndex(self._current_step)
        self._update_stepper_ui()
        self._refresh_step_views()

    def _update_stepper_ui(self) -> None:
        has_target = bool(self._target_nodes())
        for idx, btn in enumerate(self._step_btns):
            enabled = idx == 0 or has_target
            btn.setEnabled(enabled)
            label = _STEP_TITLES[idx]
            is_active = idx == self._current_step
            is_done = idx < self._current_step and has_target

            if is_done:
                plain = label.split(" ", 1)[1] if " " in label else label
                btn.setText(escape_qt_mnemonic(f"✓ {plain}"))
                btn.setStyleSheet(
                    "QPushButton { background: rgba(16, 185, 129, 0.14); color: palette(text); "
                    "border: 1px solid rgba(16, 185, 129, 0.40); border-radius: 13px; "
                    "padding: 5px 12px; font-size: 12px; font-weight: 600; }"
                )
            else:
                btn.setText(escape_qt_mnemonic(label))
                if is_active:
                    btn.setStyleSheet(
                        f"QPushButton {{ background: {COLORS['accent']}; color: white; border: none; "
                        "border-radius: 13px; padding: 5px 13px; font-size: 12px; font-weight: 700; }"
                    )
                else:
                    btn.setStyleSheet(
                        f"QPushButton {{ background: {COLORS['muted_bg']}; color: palette(text); "
                        f"border: 1px solid {COLORS['border']}; border-radius: 13px; "
                        "padding: 5px 12px; font-size: 12px; font-weight: 500; }"
                    )

    # ── Category & Filter Refresh ────────────────────────────────────────────

    def _refresh_category_buttons(self) -> None:
        while self._cat_layout.count():
            item = self._cat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cat_buttons.clear()

        avail = self._index.available_categories()
        if not avail:
            self._main_stack.setCurrentIndex(1)
            return

        avail_keys = [k for k, _, _ in avail]
        if self._active_category not in avail_keys:
            self._active_category = avail_keys[0]

        for key, label, tip in avail:
            btn = QPushButton(escape_qt_mnemonic(label))
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, k=key: self._switch_category(k))
            self._cat_layout.addWidget(btn)
            self._cat_buttons[key] = btn

        self._cat_layout.addStretch()
        self._update_category_pill_styles()
        self._switch_category(self._active_category, save=False)

    def _update_category_pill_styles(self) -> None:
        for key, btn in self._cat_buttons.items():
            active = key == self._active_category
            btn.setChecked(active)
            if active:
                btn.setStyleSheet(
                    "QPushButton { "
                    f"background: {COLORS['accent']}; color: white; border: none; "
                    "border-radius: 13px; padding: 5px 11px; font-size: 12px; font-weight: 600; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { "
                    f"background: {COLORS['muted_bg']}; color: palette(text); "
                    f"border: 1px solid {COLORS['border']}; border-radius: 13px; "
                    "padding: 5px 11px; font-size: 12px; font-weight: 500; }"
                    f"QPushButton:hover {{ border-color: {COLORS['accent']}; }}"
                )

    def _switch_category(self, key: str, save: bool = True) -> None:
        self._active_category = key
        self._showing_smart_page = False
        self._search_all_categories = False
        self._update_category_pill_styles()
        if save:
            self._save_hub_prefs()

        self._main_stack.setCurrentIndex(2)
        self._search_input.setPlaceholderText(_SEARCH_PLACEHOLDERS.get(key, "🔍 Thema suchen…"))
        self._update_lernplan_bar()
        self._top100_cb.setVisible(key != "top100")
        self._populate_topic_tree()
        self._refresh_step_views()

    def _on_search_text_changed(self, _text: str) -> None:
        self._search_all_categories = False
        self._search_timer.start()

    def _enable_all_categories_search(self) -> None:
        self._search_all_categories = True
        self._populate_topic_tree()

    def _current_lerntag_node(self) -> Optional[TopicNode]:
        conf = _get_conf()
        lerntag_num = str((conf.get("lernplan") or {}).get("lerntag") or "").strip().zfill(3)
        if not lerntag_num or lerntag_num == "000":
            return None
        prefix = f"Tag {lerntag_num}"
        for node in self._index.roots.get("lernplan", []):
            if node.display_name.startswith(prefix):
                return node
        return None

    def _update_lernplan_bar(self) -> None:
        is_lp = self._active_category == "lernplan"
        self._lernplan_bar.setVisible(is_lp)
        if not is_lp:
            return
        node = self._current_lerntag_node()
        if node is not None:
            self._jump_lerntag_btn.setText(f"▶ {node.display_name}")
            self._jump_lerntag_btn.setVisible(True)
        else:
            self._jump_lerntag_btn.setVisible(False)

    def _jump_to_current_lerntag(self) -> None:
        node = self._current_lerntag_node()
        if node is None:
            return
        if self._search_input.text().strip():
            self._search_input.blockSignals(True)
            self._search_input.clear()
            self._search_input.blockSignals(False)
            self._search_all_categories = False
            self._populate_topic_tree()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == node.key:
                self._tree.setCurrentItem(item)
                item.setExpanded(True)
                self._tree.scrollToItem(item)
                break

    def _toggle_smart_page(self) -> None:
        if not self._is_loaded:
            return
        self._showing_smart_page = not self._showing_smart_page
        if self._showing_smart_page:
            self._main_stack.setCurrentIndex(3)
            items = smart_decks.list_smart_decks(mw.col, _get_conf()) if (mw and mw.col) else self._smart_decks_cache
            self._smart_decks_cache = list(items)
            self._refresh_smart_decks_list(self._smart_decks_cache)
        else:
            self._main_stack.setCurrentIndex(2 if self._index.available_categories() else 1)

    def _effective_top100(self) -> bool:
        return bool(self._top100_only and self._active_category != "top100")

    def _save_hub_prefs(self) -> None:
        conf = _get_conf()
        hub = conf.setdefault("study_hub", {})
        hub["last_category"] = self._active_category
        hub["last_yield"] = self._yield_preset
        hub["last_mode"] = self._mode
        _save_conf(conf)

    def _on_yield_toggled(self, preset: str, checked: bool) -> None:
        if not checked or self._yield_preset == preset:
            return
        self._yield_preset = preset
        self._save_hub_prefs()
        self._update_tree_counts_in_place()
        self._refresh_step_views()

    def _on_top100_toggled(self, checked: bool) -> None:
        self._top100_only = checked
        self._populate_topic_tree()
        self._refresh_step_views()

    def _on_mode_toggled(self, mode: str, checked: bool) -> None:
        if not checked:
            return
        self._mode = mode
        self._lifecycle_combo.setVisible(mode == "smart")
        self._save_hub_prefs()
        self._refresh_step_views()

    # ── Topic Tree (Zero-Freeze RAM updates) ─────────────────────────────────

    def _populate_topic_tree(self) -> None:
        if not self._index.available_categories():
            return

        top100_only = self._effective_top100()
        self._populating_tree = True
        self._tree.setUpdatesEnabled(False)
        self._tree.blockSignals(True)
        self._tree.clear()

        query = self._search_input.text().strip() if hasattr(self, "_search_input") else ""
        if query:
            scope_cat = None if self._search_all_categories else self._active_category
            hits = self._index.search_tree(
                query,
                category_key=scope_cat,
                yield_preset=self._yield_preset,
                top100_only=top100_only,
                exclude_zahni=False,
                limit=60,
            )
            cat_names = {k: lbl.split(" ", 1)[1] if " " in lbl else lbl for k, lbl, _ in CATEGORIES}

            if scope_cat is not None and not hits:
                all_hits = self._index.search_tree(
                    query,
                    category_key=None,
                    yield_preset=self._yield_preset,
                    top100_only=top100_only,
                    exclude_zahni=False,
                    limit=60,
                )
                if all_hits:
                    cat_lbl = cat_names.get(scope_cat, scope_cat)
                    self._fallback_lbl.setText(f"Keine Treffer in „{cat_lbl}“.")
                    self._fallback_btn.setText(f"In allen Bereichen suchen ({len(all_hits)}) →")
                    self._fallback_bar.setVisible(True)
                else:
                    self._fallback_bar.setVisible(False)
            else:
                self._fallback_bar.setVisible(False)

            for node in hits:
                parent_crumb = node.breadcrumb.rsplit(" › ", 1)[0] if " › " in node.breadcrumb else ""
                if self._search_all_categories:
                    cat_tag = cat_names.get(node.category_key, "")
                    ctx = f"{cat_tag}: {parent_crumb}" if parent_crumb else cat_tag
                    label = f"{node.display_name}  ({ctx})"
                elif parent_crumb:
                    label = f"{node.display_name}  ({parent_crumb})"
                else:
                    label = node.display_name
                if item := self._build_subtree(node, override_label=label):
                    self._tree.addTopLevelItem(item)
        else:
            self._fallback_bar.setVisible(False)
            roots = self._index.roots.get(self._active_category, [])
            for node in roots:
                if item := self._build_subtree(node):
                    self._tree.addTopLevelItem(item)

        has_expandable = any(
            self._tree.topLevelItem(i).childCount() > 0
            for i in range(self._tree.topLevelItemCount())
        )
        self._tree.setRootIsDecorated(has_expandable)

        self._tree.blockSignals(False)
        self._tree.setUpdatesEnabled(True)
        self._populating_tree = False

    def _update_tree_counts_in_place(self) -> None:
        """Update item counts without collapsing expanded branches."""
        top100_only = self._effective_top100()
        self._tree.setUpdatesEnabled(False)

        def _visit(item: QTreeWidgetItem) -> None:
            key = item.data(0, Qt.ItemDataRole.UserRole)
            node = self._node_by_key.get(key)
            if node is not None:
                st = node.stats(self._yield_preset, top100_only, False)
                item.setText(1, f"{st.active}/{st.total}" if st.active else f"{st.total}")
                item.setHidden(st.total == 0)
            for i in range(item.childCount()):
                _visit(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            _visit(self._tree.topLevelItem(i))
        has_expandable = any(
            not self._tree.topLevelItem(i).isHidden() and self._tree.topLevelItem(i).childCount() > 0
            for i in range(self._tree.topLevelItemCount())
        )
        self._tree.setRootIsDecorated(has_expandable)
        self._tree.setUpdatesEnabled(True)

    def _make_tree_item(self, node: TopicNode, label: str, total: int, active: int) -> QTreeWidgetItem:
        self._node_by_key[node.key] = node
        item = QTreeWidgetItem([label, f"{active}/{total}" if active else f"{total}"])
        item.setData(0, Qt.ItemDataRole.UserRole, node.key)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(
            0,
            Qt.CheckState.Checked if node.key in self._checked_keys else Qt.CheckState.Unchecked,
        )
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _build_subtree(self, node: TopicNode, override_label: Optional[str] = None) -> Optional[QTreeWidgetItem]:
        st = node.stats(self._yield_preset, self._effective_top100(), False)
        if st.total == 0:
            return None
        item = self._make_tree_item(node, override_label or node.display_name, st.total, st.active)
        for child in node.children:
            if ch_item := self._build_subtree(child):
                item.addChild(ch_item)
        return item

    def _on_tree_item_changed(self, item: QTreeWidgetItem, col_idx: int) -> None:
        if self._populating_tree or col_idx != 0:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not key:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            self._checked_keys.add(key)
        else:
            self._checked_keys.discard(key)
        self._clear_sel_btn.setVisible(bool(self._checked_keys))
        self._refresh_step_views()

    def _on_tree_current_changed(self, current: Optional[QTreeWidgetItem], _prev: Optional[QTreeWidgetItem]) -> None:
        key = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        self._focused_node = self._node_by_key.get(key) if key else None
        self._refresh_step_views()

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, _col_idx: int) -> None:
        """Double-clicking a leaf topic selects it and moves straight to Step 2."""
        if item is not None and item.childCount() == 0:
            key = item.data(0, Qt.ItemDataRole.UserRole)
            if key and key in self._node_by_key:
                self._focused_node = self._node_by_key[key]
                self._go_to_step(1)

    def _clear_checked(self) -> None:
        self._checked_keys.clear()
        self._clear_sel_btn.setVisible(False)
        self._populate_topic_tree()
        self._refresh_step_views()

    def _target_nodes(self) -> list[TopicNode]:
        """Deduplicated checked nodes, or fallback to focused topic."""
        if self._checked_keys:
            selected = [self._node_by_key[k] for k in self._checked_keys if k in self._node_by_key]
            tag_set = {t.lower() for n in selected for t in (n.all_tags or [n.full_tag])}
            normalized: list[TopicNode] = []
            for n in selected:
                parts = n.full_tag.lower().split("::")
                if any("::".join(parts[:i]) in tag_set for i in range(1, len(parts))):
                    continue
                normalized.append(n)
            return normalized or selected
        return [self._focused_node] if self._focused_node else []

    def _collect_tags(self, nodes: list[TopicNode]) -> list[str]:
        seen: list[str] = []
        for n in nodes:
            for t in (n.all_tags or [n.full_tag]):
                if t not in seen:
                    seen.append(t)
        return seen

    def _current_search(self) -> tuple[list[TopicNode], str]:
        nodes = self._target_nodes()
        if not nodes:
            return [], ""
        search = build_topic_search(
            self._collect_tags(nodes),
            yield_preset=self._yield_preset,
            top100_only=self._effective_top100(),
            exclude_zahni=False,
        )
        return nodes, search

    # ── Step Views Refresh (100% RAM, zero DB queries) ───────────────────────

    def _refresh_right_steps(self) -> None:
        self._refresh_step_views()

    def _refresh_step_views(self) -> None:
        top100_only = self._effective_top100()
        nodes = self._target_nodes()
        self._update_stepper_ui()

        if not nodes:
            col_st = self._index.collection_stats(
                yield_preset=self._yield_preset,
                top100_only=top100_only,
                exclude_zahni=False,
            )
            active_fmt = f"{col_st.active:,}".replace(",", ".")
            total_fmt = f"{col_st.total:,}".replace(",", ".")
            self._step1_summary_lbl.setText(
                f"Gesamtstand: <b>{active_fmt} aktiv</b> von <b>{total_fmt}</b> Karten — "
                "wähle oben ein Kapitel aus."
            )
            self._to_step2_btn.setEnabled(False)
            self._to_step2_btn.setText("Weiter: Wichtigkeit wählen →")
            if self._current_step > 0:
                self._current_step = 0
                self._step_stack.setCurrentIndex(0)
                self._update_stepper_ui()
            return

        breakdown = self._index.yield_breakdown(
            nodes,
            top100_only=top100_only,
            exclude_zahni=False,
        )
        st = breakdown[self._yield_preset]

        if len(nodes) == 1:
            topic_title = nodes[0].display_name
            topic_crumb = nodes[0].breadcrumb
        else:
            names = ", ".join(n.display_name for n in nodes[:3])
            if len(nodes) > 3:
                names += f" (+{len(nodes) - 3})"
            topic_title = f"{len(nodes)} Themen ausgewählt"
            topic_crumb = names

        # Step 1 footer
        self._step1_summary_lbl.setText(
            f"Ausgewählt: <b>{_html.escape(topic_title)}</b> · "
            f"<span style='color:{COLORS['success']};font-weight:600;'>{st.active} aktiv</span> · "
            f"<b>{st.suspended}</b> pausiert"
        )
        self._to_step2_btn.setEnabled(True)
        self._to_step2_btn.setText("Weiter: Wichtigkeit wählen →")

        # Step 2 selection summary & Yield cards
        self._sel_title.setText(topic_title)
        self._sel_crumb.setText(topic_crumb)
        self._sel_bar.setValue(int(st.active * 100 / max(st.total, 1)))
        self._sel_stats_lbl.setText(
            f"<b>{st.total}</b> passende Karten: "
            f"<span style='color:{COLORS['success']};font-weight:600;'>{st.active} aktiv</span> · "
            f"<b>{st.suspended}</b> pausiert"
        )

        for ykey, badge in self._yield_count_badges.items():
            yst = breakdown[ykey]
            badge.setText(f"{yst.total} Karten")
            card = self._yield_cards.get(ykey)
            if card is not None:
                is_sel = ykey == self._yield_preset
                target_name = "ankizin_card_accent" if is_sel else "ankizin_card"
                if card.objectName() != target_name:
                    card.setObjectName(target_name)
                    card.style().unpolish(card)
                    card.style().polish(card)

        self._to_step3_btn.setEnabled(st.total > 0)
        self._to_step3_btn.setText(f"Weiter: Freischalten ({st.total} Karten) →")

        # Step 3 recap, limit hint, & CTA
        y_lbl = _YIELD_LABELS.get(self._yield_preset, self._yield_preset)
        self._step3_recap_lbl.setText(
            f"<b>{_html.escape(topic_title)}</b> · {_html.escape(y_lbl)}<br>"
            f"<span style='color:{COLORS['success']};font-weight:600;'>{st.active} aktiv</span> · "
            f"<b>{st.suspended}</b> pausiert ({st.total} Karten insgesamt)"
        )

        lim_info = self._daily_limit_info
        lim = lim_info.daily_limit
        show_limit_hint = (
            self._mode == "unsuspend"
            and st.suspended > 0
            and 0 < lim < 9999
            and (st.suspended > lim or (lim_info.total_active_new + st.suspended) > lim)
        )
        if show_limit_hint:
            if st.suspended > lim:
                self._limit_hint_lbl.setText(
                    f"💡 <b>Tageslimit-Hinweis:</b> Dein Ankizin-Stapel zeigt maximal "
                    f"<b>{lim} neue Karten/Tag</b>. Von diesen <b>{st.suspended}</b> Karten siehst du "
                    f"heute die ersten {lim} — der Rest folgt automatisch an den nächsten Tagen."
                )
            else:
                total_after = lim_info.total_active_new + st.suspended
                self._limit_hint_lbl.setText(
                    f"💡 <b>Tageslimit-Hinweis:</b> Mit diesen Karten warten insgesamt "
                    f"<b>{total_after}</b> neue Karten bei einem Tageslimit von <b>{lim}/Tag</b> — "
                    "sie verteilen sich automatisch auf die nächsten Tage."
                )
            self._limit_hint_lbl.setVisible(True)
        else:
            self._limit_hint_lbl.setVisible(False)

        self._suspend_btn.setEnabled(st.active > 0)
        all_st = breakdown["all"]
        self._post_exam_btn.setVisible(all_st.active > 0 and (all_st.standard > 0 or all_st.low > 0))

        if self._mode == "unsuspend":
            self._primary_btn.setEnabled(st.suspended > 0)
            self._primary_btn.setText(
                f"{st.suspended} neue Karten freischalten" if st.suspended else "Alle gewählten Karten bereits aktiv ✓"
            )
        else:
            self._primary_btn.setEnabled(st.total > 0)
            self._primary_btn.setText(f"Smart-Stapel erstellen ({st.total} Karten)")

    # ── Busy State & Async Index Sync ────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        if busy:
            self._primary_btn.setEnabled(False)
            self._suspend_btn.setEnabled(False)
            self._post_exam_btn.setEnabled(False)
        else:
            self._post_exam_btn.setEnabled(True)

    def _update_smart_nav_count(self, smart_cnt: int) -> None:
        self._smart_nav_btn.setText(f"📌 Smart-Stapel ({smart_cnt})" if smart_cnt else "📌 Smart-Stapel")

    def _apply_rebuilt_index(
        self,
        new_index,
        limit_info: Optional[smart_decks.DailyNewLimitInfo] = None,
        repopulate_tree: bool = False,
    ) -> None:
        focused_key = self._focused_node.key if self._focused_node else None
        self._index = new_index
        self._node_by_key = {n.key: n for n in new_index.all_nodes}
        self._focused_node = self._node_by_key.get(focused_key) if focused_key else None
        if limit_info is not None:
            self._daily_limit_info = limit_info
        if repopulate_tree:
            self._populate_topic_tree()
        else:
            self._update_tree_counts_in_place()
        self._refresh_step_views()

    def _on_op_failed(self, exc: Exception) -> None:
        self._set_busy(False)
        self._refresh_step_views()
        showInfo(f"Vorgang fehlgeschlagen: {exc}", parent=self)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_primary_action(self) -> None:
        nodes, search = self._current_search()
        if not nodes or not search:
            return

        if self._mode == "unsuspend":
            self._set_busy(True)

            def op(col):
                cids, changes = smart_decks.unsuspend_matching_cards_detailed(col, search)
                new_index = build_tag_index(col)
                limit_info = smart_decks.get_daily_new_limit_info(col, cids)
                return OpResult((len(cids), new_index, limit_info), changes)

            def done(out: OpResult) -> None:
                count, new_index, limit_info = out.value
                self._set_busy(False)
                self._apply_rebuilt_index(new_index, limit_info)
                if not count:
                    return

                notice = smart_decks.format_daily_limit_notice(count, limit_info)
                msg = f"<b>{count}</b> Karten wurden im Ankizin-Stapel freigeschaltet!"
                if notice:
                    msg += f"<br><br>{notice}"
                msg += "<br><br>Möchtest du das Fenster schließen und direkt mit dem Lernen beginnen?"

                def _prompt() -> None:
                    if not self.isVisible():
                        return
                    if askUser(msg, parent=self):
                        self.accept()
                        if mw:
                            mw.moveToState("deckBrowser")

                QTimer.singleShot(0, _prompt)

            CollectionOp(self, op).success(done).failure(self._on_op_failed).run_in_background()
        else:
            lifecycle = self._lifecycle_combo.currentData() or "daily"
            title = nodes[0].display_name if len(nodes) == 1 else f"{nodes[0].display_name} +{len(nodes)-1}"
            self._set_busy(True)

            def op(col):
                conf = _get_conf()
                res = smart_decks.create_smart_filtered_deck(
                    col,
                    conf,
                    title=title,
                    base_search=search,
                    lifecycle=lifecycle,
                    yield_preset=self._yield_preset,
                )
                new_index = build_tag_index(col)
                limit_info = smart_decks.get_daily_new_limit_info(col)
                smart_items = smart_decks.list_smart_decks(col, conf)
                return OpResult((res, conf, new_index, limit_info, smart_items), res.changes)

            def done(out: OpResult) -> None:
                res, conf, new_index, limit_info, smart_items = out.value
                _save_conf(conf)
                self._smart_decks_cache = list(smart_items)
                self._set_busy(False)
                self._update_smart_nav_count(len(self._smart_decks_cache))
                self._apply_rebuilt_index(new_index, limit_info)

                def _notify() -> None:
                    if not self.isVisible():
                        return
                    if res.created:
                        showInfo(
                            f"Smart-Lernstapel <b>„{res.deck_name}“</b> erstellt ({res.card_count} Karten)!",
                            parent=self,
                        )
                    else:
                        showInfo(res.message or "Es konnten keine Karten hinzugefügt werden.", parent=self)

                QTimer.singleShot(0, _notify)

            CollectionOp(self, op).success(done).failure(self._on_op_failed).run_in_background()

    def _on_suspend_selected(self) -> None:
        nodes, search = self._current_search()
        if not nodes or not search:
            return
        self._set_busy(True)

        def op(col):
            cnt, changes = smart_decks.suspend_matching_cards(col, search)
            new_index = build_tag_index(col)
            limit_info = smart_decks.get_daily_new_limit_info(col)
            return OpResult((cnt, new_index, limit_info), changes)

        def done(out: OpResult) -> None:
            cnt, new_index, limit_info = out.value
            self._set_busy(False)
            self._apply_rebuilt_index(new_index, limit_info)
            tooltip(f"{cnt} Karten pausiert.", parent=self, period=3000)

        CollectionOp(self, op).success(done).failure(self._on_op_failed).run_in_background()

    def _on_keep_only_high_yield(self) -> None:
        nodes = self._target_nodes()
        if not nodes:
            return
        topic_search = build_topic_search(
            self._collect_tags(nodes),
            yield_preset="all",
            top100_only=self._effective_top100(),
            exclude_zahni=False,
        )
        if not askUser(
            "Alle aktiven Karten dieses Themas, die <b>kein High Yield</b> (stark/leicht gelb) sind, "
            "werden wieder pausiert.<br><br>Deine High-Yield-Karten bleiben aktiv. Fortfahren?",
            parent=self,
        ):
            return

        self._set_busy(True)

        def op(col):
            kept, suspended, changes = smart_decks.keep_only_high_yield(col, topic_search)
            new_index = build_tag_index(col)
            limit_info = smart_decks.get_daily_new_limit_info(col)
            return OpResult((kept, suspended, new_index, limit_info), changes)

        def done(out: OpResult) -> None:
            kept, susp, new_index, limit_info = out.value
            self._set_busy(False)
            self._apply_rebuilt_index(new_index, limit_info)

            def _notify() -> None:
                if not self.isVisible():
                    return
                showInfo(
                    f"Erledigt! <b>{kept}</b> High-Yield-Karten bleiben aktiv, <b>{susp}</b> übrige Karten pausiert.",
                    parent=self,
                )

            QTimer.singleShot(0, _notify)

        CollectionOp(self, op).success(done).failure(self._on_op_failed).run_in_background()

    # ── Smart Decks Management Page ──────────────────────────────────────────

    def _refresh_smart_decks_list(self, items: Optional[list[smart_decks.SmartDeckInfo]] = None) -> None:
        while self._smart_lay.count():
            item = self._smart_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if items is None:
            items = smart_decks.list_smart_decks(mw.col, _get_conf()) if (mw and mw.col) else []
        if not items:
            c, cl = make_card("ankizin_card_soft", padding=(18, 16, 18, 16))
            lbl = QLabel(
                "Du hast noch keine Smart-Lernstapel erstellt.<br>"
                "Wähle ein Thema aus und klicke unter Schritt 3 auf <i>„Als Smart-Lernstapel erstellen“</i>."
            )
            lbl.setWordWrap(True)
            cl.addWidget(lbl)
            self._smart_lay.addWidget(c)
            self._smart_lay.addStretch()
            return

        for sd in items:
            card, cl = make_card("ankizin_card", padding=(14, 12, 14, 12))
            top = QHBoxLayout()
            title = QLabel(f"<b>{_html.escape(sd.name)}</b>")
            title.setWordWrap(True)
            top.addWidget(title, 1)
            mode_txt = "Täglich (is:due)" if sd.lifecycle == "daily" else "Einmalig (Auto-Aufräumen)"
            top.addWidget(make_badge(mode_txt, "accent" if sd.lifecycle == "daily" else "warning"))
            top.addWidget(make_badge(f"{sd.remaining_cards} Karten im Stapel", "neutral"))
            cl.addLayout(top)

            btns = QHBoxLayout()
            if sd.lifecycle == "daily":
                reb = QPushButton("Jetzt aktualisieren")
                reb.setObjectName("secondary")
                reb.setAutoDefault(False)
                reb.clicked.connect(lambda _=False, d=sd.deck_id: self._rebuild_one_smart_deck(d))
                btns.addWidget(reb)

            toggle_btn = QPushButton(
                "Auf „Einmalig“ umstellen" if sd.lifecycle == "daily" else "Auf „Täglich (is:due)“ umstellen"
            )
            toggle_btn.setObjectName("secondary")
            toggle_btn.setAutoDefault(False)
            toggle_btn.clicked.connect(lambda _=False, d=sd.deck_id: self._toggle_smart_lifecycle(d))
            btns.addWidget(toggle_btn)

            dissolve_btn = QPushButton("Auflösen (Karten behalten)")
            dissolve_btn.setObjectName("danger_outline")
            dissolve_btn.setAutoDefault(False)
            dissolve_btn.clicked.connect(lambda _=False, d=sd.deck_id: self._dissolve_smart_deck(d))
            btns.addWidget(dissolve_btn)
            btns.addStretch()
            cl.addLayout(btns)
            self._smart_lay.addWidget(card)

        self._smart_lay.addStretch()

    def _rebuild_one_smart_deck(self, did: int) -> None:
        conf = _get_conf()

        def op(col):
            res = smart_decks.maintain_smart_decks(col, conf, rebuild_daily=True)
            smart_items = smart_decks.list_smart_decks(col, conf)
            return OpResult((res, conf, smart_items), res.changes)

        def done(out: OpResult) -> None:
            _, updated_conf, smart_items = out.value
            _save_conf(updated_conf)
            self._smart_decks_cache = list(smart_items)
            self._update_smart_nav_count(len(self._smart_decks_cache))
            self._refresh_smart_decks_list(self._smart_decks_cache)
            tooltip("Smart-Stapel aktualisiert.", parent=self, period=2500)

        CollectionOp(self, op).success(done).failure(self._on_op_failed).run_in_background()

    def _toggle_smart_lifecycle(self, did: int) -> None:
        conf = _get_conf()
        meta = (conf.get("smart_decks") or {}).get(str(did))
        if not meta:
            return
        meta["lifecycle"] = "auto_clean" if meta.get("lifecycle") == "daily" else "daily"
        _save_conf(conf)
        items = smart_decks.list_smart_decks(mw.col, conf) if (mw and mw.col) else []
        self._smart_decks_cache = list(items)
        self._refresh_smart_decks_list(self._smart_decks_cache)

    def _dissolve_smart_deck(self, did: int) -> None:
        conf = _get_conf()

        def op(col):
            ok = smart_decks.dissolve_smart_deck(col, conf, did)
            smart_items = smart_decks.list_smart_decks(col, conf)
            return OpResult((ok, conf, smart_items), make_op_changes(deck=True, study_queues=True))

        def done(out: OpResult) -> None:
            ok, updated_conf, smart_items = out.value
            _save_conf(updated_conf)
            self._smart_decks_cache = list(smart_items)
            self._update_smart_nav_count(len(self._smart_decks_cache))
            self._refresh_smart_decks_list(self._smart_decks_cache)
            if ok:
                tooltip("Smart-Stapel aufgelöst — alle Karten bleiben im Ankizin-Stapel.", parent=self, period=3500)

        CollectionOp(self, op).success(done).failure(self._on_op_failed).run_in_background()

    # ── Navigation Helpers ───────────────────────────────────────────────────

    def _reload_index(self) -> None:
        col = mw.col if mw else None
        self._apply_rebuilt_index(
            build_tag_index(col),
            smart_decks.get_daily_new_limit_info(col),
            repopulate_tree=True,
        )

    def _open_wizard(self) -> None:
        from ..onboarding.wizard import open_setup_wizard
        open_setup_wizard(force=True)

    def _open_maintenance(self) -> None:
        from ..onboarding.maintenance import open_maintenance_dialog
        open_maintenance_dialog(self)

    def _open_lernplan(self) -> None:
        from ..butler.lernplan_manager import open_lernplan_manager
        open_lernplan_manager()


def open_study_hub(parent: Optional[QWidget] = None) -> AnkizinStudyHubDialog:
    global _study_hub_dialog
    if _study_hub_dialog is not None:
        try:
            if _study_hub_dialog.isVisible():
                _study_hub_dialog.raise_()
                _study_hub_dialog.activateWindow()
                return _study_hub_dialog
        except RuntimeError:
            pass
    _study_hub_dialog = AnkizinStudyHubDialog(parent or mw)
    _study_hub_dialog.show()
    return _study_hub_dialog
