import datetime
import os

from aqt import mw
from aqt.operations import CollectionOp
from aqt.qt import *
from aqt.utils import askUser, disable_help_button, showWarning

from ..constants import ADDON_DIR_NAME
from .lernplan_decks import (
    LERNTAG_PREFIX,
    OBSOLETE_CONFIG_KEYS,
    LerntagSettings,
    effective_today,
    get_kreuzen_tage,
    get_lerntag_list,
    get_lerntag_order,
    get_lerntag_topics,
    is_past_day,
    kreuzen_count,
    rebuild_lernplan_decks,
    set_past_day,
    update_past_days,
)
from .lernplan_calendar import build_ics
from .lernplan_progress import GRID_LEGEND, ProgressTiles, summary_lines
from .lernplan_schedule import (
    DEFAULT_WOCHENTAGE,
    M2_TERMINE,
    compute_schedule,
    parse_date,
    parse_dates,
)
from .utils import check_ankizin_installation, report_result


def _get_config() -> dict:
    """Get addon config or return empty dict if not configured."""
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    return conf if conf is not None else {}


class LerntagDeckCreatorDialog(QDialog):
    mark_done_cb: QCheckBox | None = None  # only the manual deck creator has it
    include_unfinished_cb: QCheckBox | None = None  # only the Lernplan-Manager has it

    def __init__(self, parent, conf_key: str = "man_lernplan"):
        super().__init__(parent)
        disable_help_button(self)
        self._conf_key = conf_key
        self.setWindowTitle("Lerntag-Auswahlstapel erstellen")

        self._load_config()

        # the dialog can be taller than the screen, so the whole content scrolls
        self._content = QWidget()
        content_layout = QHBoxLayout(self._content)
        self._setup_logo(content_layout)

        right_layout = QVBoxLayout()
        self._setup_explanation(right_layout)
        self._setup_main_content(right_layout)
        self._setup_action_buttons(right_layout)
        content_layout.addLayout(right_layout)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setWidget(self._content)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._scroll_area)

        self.setWindowIcon(QIcon("icons:ankizin.png"))
        self._fit_to_content()

    def _fit_to_content(self) -> None:
        """Size the window to its content, but never taller than the screen."""
        self._content.layout().activate()
        hint = self._content.sizeHint()
        scrollbar_width = self._scroll_area.verticalScrollBar().sizeHint().width()
        max_height = int(QGuiApplication.primaryScreen().availableGeometry().height() * 0.9)
        self.resize(hint.width() + scrollbar_width, min(hint.height(), max_height))

    def _load_config(self) -> None:
        conf = _get_config()
        lernplan_conf = conf.get(self._conf_key, {})
        settings = LerntagSettings.from_conf(lernplan_conf)
        self._lerntag = settings.lerntag
        self._highyield_stark = settings.highyield_stark
        self._highyield_leicht = settings.highyield_leicht
        self._lowyield = settings.lowyield
        self._top100 = settings.top100
        self._normyield = not (settings.highyield_stark or settings.lowyield)
        self._create_subchapter_decks = settings.subchapters
        self._include_unfinished = settings.include_unfinished

    def _setup_logo(self, main_layout: QHBoxLayout) -> None:
        logo_label = QLabel()
        logo_pixmap = QPixmap("icons:ankizin.png")
        logo_label.setPixmap(
            logo_pixmap.scaled(
                100, 100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        main_layout.addWidget(logo_label)

    def _fixed_font(self) -> QFont:
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPointSize(font.pointSize() + 2)
        return font

    def _selected_lerntag(self) -> str | None:
        return self.lerntag_combo.currentData()

    def _setup_lerntag_combo(
        self,
        layout: QLayout,
        lerntag: str,
        label_text: str = "<b>Lerntag:</b>",
    ) -> None:
        self.lerntag_combo_label = QLabel(label_text)
        layout.addWidget(self.lerntag_combo_label)
        self.lerntag_combo = QComboBox()
        self.lerntag_combo.setFont(self._fixed_font())
        for number, topic in get_lerntag_list(mw.col):
            display_text = f"{number} - {topic.replace('_', ' ')}"
            self.lerntag_combo.addItem(display_text, number)
        self.lerntag_combo.setCurrentIndex(max(self.lerntag_combo.findData(lerntag), 0))
        layout.addWidget(self.lerntag_combo)

    def _setup_extra_choices(
        self,
        layout: QLayout,
        top100: bool,
        create_subchapter_decks: bool,
        include_unfinished: bool | None = None,
    ) -> None:
        extra_choices_group_box = QGroupBox("Auswahl:")
        extra_choices_buttons_layout = QVBoxLayout()
        extra_choices_buttons_layout.setContentsMargins(5, 5, 5, 5)

        self.top100_button = QCheckBox("nur TOP-100 Themen")
        self.top100_button.setChecked(top100)
        self.top100_button.setToolTip("Beschränkt die Auswahl auf die wichtigsten 100 Themen aus AMBOSS.")
        extra_choices_buttons_layout.addWidget(self.top100_button)

        self.create_subchapter_decks_button = QCheckBox("Separate Auswahlstapel für jedes Kapitel erstellen")
        self.create_subchapter_decks_button.setChecked(create_subchapter_decks)
        self.create_subchapter_decks_button.setToolTip("Erstellt mehrere Unter-Stapel, einen pro Kapitel/Thema des Lerntages.")
        extra_choices_buttons_layout.addWidget(self.create_subchapter_decks_button)

        if include_unfinished is not None:  # only the Lernplan-Manager builds the due deck
            self.include_unfinished_cb = QCheckBox("Nicht geschaffte Karten vergangener Lerntage weiter einplanen")
            self.include_unfinished_cb.setChecked(include_unfinished)
            self.include_unfinished_cb.setToolTip(
                "Neue Karten und Karten im Lernen, die du an ihrem Lerntag nicht geschafft hast, landen im Stapel "
                "<code>!FÄLLIGE&nbsp;KARTEN&nbsp;VERGANGENER&nbsp;LERNTAGE</code>.<br>"
                "Ohne diese Option enthält er nur fällige Karten und die übrigen fallen aus dem Lernplan."
            )
            extra_choices_buttons_layout.addWidget(self.include_unfinished_cb)

        extra_choices_group_box.setLayout(extra_choices_buttons_layout)
        layout.addWidget(extra_choices_group_box)

    def _setup_yield_group(
        self,
        layout: QLayout,
        highyield_stark: bool,
        highyield_leicht: bool,
        normyield: bool,
        lowyield: bool,
    ) -> None:
        yield_group_box = QGroupBox("Karten:")
        yield_buttons_layout = QVBoxLayout()
        yield_buttons_layout.setContentsMargins(5, 5, 5, 5)

        self.highyield_stark_button = QRadioButton("nur HIGH-YIELD stark gelb")
        self.highyield_stark_button.setChecked(highyield_stark and not highyield_leicht)
        yield_buttons_layout.addWidget(self.highyield_stark_button)

        self.highyield_all_button = QRadioButton("alle HIGH-YIELD Karten (stark + leicht gelb)")
        self.highyield_all_button.setChecked(highyield_stark and highyield_leicht)
        yield_buttons_layout.addWidget(self.highyield_all_button)

        self.standard_button = QRadioButton("STANDARD Karten (high-yield und normal)")
        self.standard_button.setChecked(normyield)
        yield_buttons_layout.addWidget(self.standard_button)

        self.lowyield_button = QRadioButton("ALLE Karten (high-yield, normal UND low-yield)")
        self.lowyield_button.setChecked(lowyield)
        yield_buttons_layout.addWidget(self.lowyield_button)

        self.yield_button_group = QButtonGroup(self)
        self.yield_button_group.addButton(self.highyield_stark_button)
        self.yield_button_group.addButton(self.highyield_all_button)
        self.yield_button_group.addButton(self.standard_button)
        self.yield_button_group.addButton(self.lowyield_button)

        yield_group_box.setLayout(yield_buttons_layout)
        layout.addWidget(yield_group_box)

    def _setup_explanation(self, right_layout: QVBoxLayout) -> None:
        explanation_label = QLabel("Erstelle einen spezifischen Lerntag-Auswahlstapel <b>unabhängig</b> vom automatischen Lernplan-Manager.")
        explanation_label.setWordWrap(True)
        right_layout.addWidget(explanation_label)
        right_layout.addSpacing(20)

    def _setup_main_content(self, right_layout: QVBoxLayout) -> None:
        self._setup_lerntag_combo(right_layout, self._lerntag)
        self._setup_extra_choices(right_layout, self._top100, self._create_subchapter_decks)
        self._setup_yield_group(
            right_layout,
            self._highyield_stark,
            self._highyield_leicht,
            self._normyield,
            self._lowyield,
        )
        self.mark_done_cb = QCheckBox("Lerntag als gelernt markieren (z. B. für eine Klausur vorgelernt)")
        self.mark_done_cb.setChecked(True)
        self.mark_done_cb.setToolTip("Der automatische Lernplan-Manager überspringt diesen Lerntag dann.")
        right_layout.addWidget(self.mark_done_cb)

    def _setup_action_buttons(self, right_layout: QVBoxLayout) -> None:
        box = QDialogButtonBox()
        confirm_btn = box.addButton("Stapel erstellen!", QDialogButtonBox.ButtonRole.AcceptRole)
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(self.create_lerntag_deck_wrapper)
        right_layout.addWidget(box)

    def closeEvent(self, event):
        event.ignore()
        self.reject()

    def _read_settings(self) -> LerntagSettings:
        highyield_leicht = self.highyield_all_button.isChecked()
        return LerntagSettings(
            lerntag=(self._selected_lerntag() or self._lerntag).zfill(3),
            highyield_stark=self.highyield_stark_button.isChecked() or highyield_leicht,
            highyield_leicht=highyield_leicht,
            lowyield=self.lowyield_button.isChecked(),
            top100=self.top100_button.isChecked(),
            subchapters=self.create_subchapter_decks_button.isChecked(),
            include_unfinished=self.include_unfinished_cb is None or self.include_unfinished_cb.isChecked(),
        )

    def _update_section(self, conf: dict, section: dict, settings: LerntagSettings, mark_today: bool) -> None:
        """Hook: write the settings into `section` (= conf[self._conf_key])."""
        section.update(settings.to_conf())
        for key in OBSOLETE_CONFIG_KEYS:
            section.pop(key, None)

    def save_config(self, mark_today: bool = False) -> LerntagSettings:
        conf = _get_config()
        settings = self._read_settings()
        self._update_section(conf, conf.setdefault(self._conf_key, {}), settings, mark_today)
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        return settings

    # ==== DECK CREATION FLOW ====
    #
    # create_lerntag_deck_wrapper() saves the config, then runs ONE CollectionOp
    # (rebuild_lernplan_decks) which cleans up, creates the decks and merges all
    # of it into a single undo step. UI feedback happens in the success callback.
    #
    # LernplanManagerDialog only differs in:
    #   • _update_section()     -> lernplan-specific config (autocreate, weekdays, ...)
    #   • _rebuild_kwargs()     -> prefix, cleanup, previous/due decks

    def create_lerntag_deck_wrapper(self):
        if not self._selected_lerntag():
            showWarning("Keine Lerntage gefunden. Ist Ankizin korrekt installiert?")
            return
        settings = self.save_config(mark_today=True)
        if self.mark_done_cb and self.mark_done_cb.isChecked():
            conf = _get_config()
            set_past_day(conf.setdefault("lernplan", {}).setdefault("past_days", []), int(settings.lerntag), True)
            mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        kwargs = self._rebuild_kwargs()
        CollectionOp(
            mw, lambda col: rebuild_lernplan_decks(col, settings, **kwargs)
        ).success(report_result).run_in_background()  # shows its own progress popup
        self.accept()

    def _rebuild_kwargs(self) -> dict:
        # Hook for subclass: prefix, cleanup, previous, due, past_days
        return {"prefix": "Lerntag "}

class LernplanManagerDialog(LerntagDeckCreatorDialog):
    _tiles: ProgressTiles | None = None  # the progress group is created after the Lerntag list, which already updates it

    def __init__(self, parent):
        super().__init__(parent, conf_key="lernplan")
        # the platform's highlighted (on macOS blue) main button, instead of whichever button has the focus
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self._sync_buttons(self._autocreate)

    def _load_config(self) -> None:
        super()._load_config()
        conf = _get_config()
        lernplan_conf = conf.get("lernplan", {})
        self._autocreate = lernplan_conf.get("autocreate", False)
        self._autocreate_due = lernplan_conf.get("autocreate_due", True)
        self._autocreate_previous = lernplan_conf.get("autocreate_previous", False)
        self._wochentage = lernplan_conf.get("wochentage", DEFAULT_WOCHENTAGE)
        self._order = get_lerntag_order(mw.col, lernplan_conf)
        self._kreuzen = get_kreuzen_tage(mw.col, kreuzen_count(lernplan_conf))
        self._topics = get_lerntag_topics(mw.col, kreuzen_count(lernplan_conf))
        self._past_days = lernplan_conf.get("past_days", [])
        self._extra_days = parse_dates(lernplan_conf.get("extra_days"))
        self._skip_days = parse_dates(lernplan_conf.get("skip_days"))
        self._m2_date = parse_date(lernplan_conf.get("m2_date"))

    def _setup_explanation(self, right_layout: QVBoxLayout) -> None:
        self.setWindowTitle("Lernplan-Manager (automatisch)")
        explanation_label = QLabel(
            "Lass den <b>automatischen Lernplan-Manager</b> Deine Lerntag-Auswahlstapel erstellen.<br>"
            "Du kannst wählen, ob nur TOP-100 Themen und/oder nur HIGH-YIELD Karten oder auch normale und low-yield Karten enthalten sein sollen.<br>"
            "Der Lernplan-Manager erstellt jeden Tag automatisch einen neuen Lerntag-Auswahlstapel.<br>"
            "Alte Stapel werden automatisch aus der Übersicht entfernt, wenn sie nicht nach <code>!VORHERIGE&nbsp;LERNTAGE</code> verschoben werden sollen.<br><br>"
            "Der Lernplan-Manager funktioniert am besten mit der aktuellsten Version von Ankizin (aktuell: AnkiCollab / V4+)."
        )
        explanation_label.setWordWrap(True)
        right_layout.addWidget(explanation_label)

        right_layout.addSpacing(20)

        right_layout.addWidget(QLabel("<b>Lernplan-Manager aktivieren:</b> [Haken raus zum Abschalten]"))
        self.autocreate_button = QCheckBox("Lerntag-Auswahlstapel jeden Tag automatisch erstellen (empfohlen)")
        self.autocreate_button.setChecked(self._autocreate)
        self.autocreate_button.setToolTip("Aktiviert den automatischen Lernplan-Manager.<br>Erstellt jeden Tag einen neuen Lerntag-Auswahlstapel <code>!&#8288;LERNTAG&nbsp;XX</code>.")
        self.autocreate_button.toggled.connect(self.toggle_settings)
        right_layout.addWidget(self.autocreate_button)

        past_days_info_label = QLabel("<i>Lerntage werden automatisch als gelernt (Haken) markiert, sobald der Lernplan-Manager <b>automatisch</b> zu einem neuen Lerntag wechselt.</i>")
        past_days_info_label.setWordWrap(True)
        right_layout.addWidget(past_days_info_label)

        right_layout.addSpacing(10)

    def _setup_extra_days(self, layout: QVBoxLayout) -> None:
        """Drop-down with a calendar to add single extra Lernplan days or to skip single days."""
        group = QGroupBox()
        group_layout = QVBoxLayout()
        toggle = QToolButton()
        toggle.setText("Einzelne Zusatz- und Pausentage")
        toggle.setCheckable(True)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        group_layout.addWidget(toggle)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "<i>Klick auf einen Tag: Ein freier Tag wird zum Zusatz-Lerntag (grün), ein Lerntag wird "
            "ausgesetzt (grau, durchgestrichen). Nochmal klicken setzt ihn zurück.</i>"
        )
        hint.setWordWrap(True)
        content_layout.addWidget(hint)
        self._calendar = QCalendarWidget()
        self._calendar.setMinimumDate(QDate.currentDate())
        self._calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._calendar.clicked.connect(self._toggle_extra_day)
        content_layout.addWidget(self._calendar)
        content.setVisible(False)
        group_layout.addWidget(content)
        group.setLayout(group_layout)
        layout.addWidget(group)

        def on_toggled(checked: bool) -> None:
            content.setVisible(checked)
            toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
            self._fit_to_content()

        toggle.toggled.connect(on_toggled)
        self._mark_extra_days()
        if any(day >= datetime.date.today() for day in self._extra_days | self._skip_days):
            toggle.setChecked(True)  # planned days are not hidden

    def _toggle_extra_day(self, qdate: QDate) -> None:
        day = qdate.toPyDate()
        if day in self._extra_days:
            self._extra_days.discard(day)
        elif day in self._skip_days:
            self._skip_days.discard(day)
        elif self.weekday_buttons[day.weekday()].isChecked():
            self._skip_days.add(day)
        else:
            self._extra_days.add(day)
        self._mark_extra_days()
        self._update_progress_view()

    def _mark_extra_days(self) -> None:
        self._calendar.setDateTextFormat(QDate(), QTextCharFormat())  # reset all marks
        palette = self._calendar.palette()  # skipped days follow the light/dark theme
        for days, background, foreground, tip in (
            (self._extra_days, QColor("#43a047"), QColor("#ffffff"), "Zusätzlicher Lerntag"),
            (
                self._skip_days,
                palette.color(QPalette.ColorRole.Mid),
                palette.color(QPalette.ColorRole.PlaceholderText),
                "Ausgesetzt",
            ),
        ):
            fmt = QTextCharFormat()
            fmt.setBackground(background)
            fmt.setForeground(foreground)
            fmt.setFontStrikeOut(days is self._skip_days)
            fmt.setToolTip(tip)
            for day in days:
                self._calendar.setDateTextFormat(QDate(day), fmt)

    def _setup_lerntag_list(self, outer_layout: QVBoxLayout) -> None:
        group = QGroupBox("Lerntage:")
        layout = QVBoxLayout(group)
        layout.addWidget(QLabel("Reihenfolge per Drag & Drop ändern, Haken = bereits gelernt, ▶ = aktueller Lerntag"))
        self.lerntag_list = QListWidget()
        self.lerntag_list.setFont(self._fixed_font())
        self.lerntag_list.setMinimumHeight(220)
        self.lerntag_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lerntag_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.lerntag_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        # Qt drops item widgets when a row is moved, so recreate the missing ones afterwards
        for signal in (self.lerntag_list.model().rowsInserted, self.lerntag_list.model().rowsMoved):
            signal.connect(lambda *_: QTimer.singleShot(0, self._refresh_lerntag_rows))
        self._current = self._lerntag
        done = {n for n in self._order if is_past_day(self._past_days, int(n))}
        self._fill_lerntag_list(self._order, done)
        layout.addWidget(self.lerntag_list)

        buttons_layout = QHBoxLayout()
        current_btn = QPushButton("Als aktuellen Lerntag setzen")
        current_btn.clicked.connect(self._set_current_lerntag)
        buttons_layout.addWidget(current_btn)
        for text, delta in (("↑ Nach oben", -1), ("↓ Nach unten", 1)):
            move_btn = QPushButton(text)
            move_btn.clicked.connect(lambda _, delta=delta: self._move_selected_lerntage(delta))
            buttons_layout.addWidget(move_btn)
        reset_btn = QPushButton("Reihenfolge zurücksetzen")
        reset_btn.clicked.connect(self._reset_lerntag_order)
        buttons_layout.addWidget(reset_btn)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        outer_layout.addWidget(group)

    def _setup_progress(self, layout: QVBoxLayout) -> None:
        """Fortschritt & Prognose: the Lerntage in their current order, the projected end and the M2 buffer."""
        group = QGroupBox("Fortschritt && Prognose:")
        group_layout = QVBoxLayout()
        self._tiles = ProgressTiles()
        group_layout.addWidget(self._tiles, alignment=Qt.AlignmentFlag.AlignLeft)
        group_layout.addWidget(QLabel(f"<small>{GRID_LEGEND}</small>"))
        self._progress_label = QLabel()
        group_layout.addWidget(self._progress_label)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self._kreuzen_spin = QSpinBox()
        self._kreuzen_spin.setRange(0, 30)
        self._kreuzen_spin.setValue(len(self._kreuzen))
        self._kreuzen_spin.setSuffix(" Tage")
        self._kreuzen_spin.setToolTip(
            "AMBOSS-Plan: 2 Wiederholungsexamen (6 Tage) + 3 Generalproben (9 Tage) = 15 Tage.<br>"
            "Erhöhe den Wert, wenn du zusätzlich Altexamen kreuzen willst, oder setze ihn auf 0,<br>"
            "wenn du die Kreuzen-Tage nicht mitplanen möchtest."
        )
        self._kreuzen_spin.valueChanged.connect(self._sync_kreuzen_rows)
        form.addRow("Kreuzen-Tage nach dem letzten Lerntag:", self._kreuzen_spin)

        self._m2_dates = list(M2_TERMINE.values())
        self._m2_combo = QComboBox()
        self._m2_combo.addItems(["Kein M2-Termin", *M2_TERMINE])
        self._m2_combo.setToolTip("Zeigt, wie viele Puffertage zwischen dem letzten Lerntag und dem M2 bleiben.")
        self._m2_combo.setCurrentIndex(self._m2_dates.index(self._m2_date) + 1 if self._m2_date in self._m2_dates else 0)
        self._m2_combo.currentIndexChanged.connect(self._update_progress_view)
        for button in self.weekday_buttons:
            button.toggled.connect(self._update_progress_view)
        form.addRow("M2-Prüfungstermin:", self._m2_combo)
        group_layout.addLayout(form)

        export_button = QPushButton("📅 Lernplan als Kalender exportieren (.ics)")
        export_button.setToolTip("Exportiert alle offenen Lerntage als ganztägige Termine, z. B. für den iCloud-Kalender.")
        export_button.clicked.connect(self._export_ics)
        group_layout.addWidget(export_button, alignment=Qt.AlignmentFlag.AlignLeft)

        group.setLayout(group_layout)
        layout.addWidget(group)
        self._update_progress_view()

    def _sync_kreuzen_rows(self, count: int) -> None:
        """Add or remove Kreuzen-Tage at the end of the list, keeping the rest of the order."""
        rows = self._lerntag_rows()
        wanted = get_kreuzen_tage(mw.col, count)
        numbers = [n for n, _ in rows if n not in self._kreuzen or n in wanted]
        numbers += [n for n in wanted if n not in numbers]
        self._kreuzen = wanted
        self._topics = get_lerntag_topics(mw.col, count)
        self._fill_lerntag_list(numbers, {n for n, done in rows if done})

    def _m2_selected(self) -> datetime.date | None:
        index = self._m2_combo.currentIndex()
        return self._m2_dates[index - 1] if index else None

    def _compute_schedule(self, rows: list[tuple[str, bool]]) -> list[tuple[str, datetime.date]] | None:
        return compute_schedule(
            [n for n, _ in rows],
            {n for n, done in rows if done},
            self._current,
            [b.isChecked() for b in self.weekday_buttons],
            effective_today(mw.col),
            self._extra_days,
            self._skip_days,
        )

    def _export_ics(self) -> None:
        schedule = self._compute_schedule(self._lerntag_rows())
        if not schedule:
            showWarning("Es gibt keine offenen Lerntage zu exportieren (oder keinen ausgewählten Wochentag).")
            return
        m2 = self._m2_selected()
        path, _ = QFileDialog.getSaveFileName(
            self, "Lernplan als Kalender exportieren", os.path.expanduser("~/Lernplan.ics"), "Kalender-Datei (*.ics)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(build_ics(schedule, self._topics, m2))
        if askUser(
            f"{len(schedule)} Lerntage wurden exportiert. In der Kalender-App öffnen?<br><br>"
            "<i>Bei einem erneuten Export in denselben Kalender werden die Termine aktualisiert, nicht doppelt angelegt.</i>"
        ):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _update_progress_view(self, *_) -> None:
        if self._tiles is None:
            return  # the list is filled before the progress group exists
        rows = self._lerntag_rows()
        order = [number for number, _ in rows]
        finished = {number for number, done in rows if done}
        schedule = self._compute_schedule(rows)
        m2 = self._m2_selected()
        self._tiles.set_tiles(order, finished, self._current, self._topics, set(self._kreuzen))
        finish = schedule[-1][1] if schedule else None
        self._progress_label.setText("<br>".join(summary_lines(len(finished), len(order), finish, m2)))

    def _lerntag_rows(self) -> list[tuple[str, bool]]:
        """(number, done) in the order currently shown."""
        numbers = [self.lerntag_list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.lerntag_list.count())]
        return [(number, number in self._done) for number in numbers]

    def _fill_lerntag_list(self, order: list[str], done: set[str]) -> None:
        self._done = set(done)
        self.lerntag_list.clear()
        for number in order:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, number)
            self.lerntag_list.addItem(item)
        self._refresh_lerntag_rows()

    def _refresh_lerntag_rows(self) -> None:
        """Make sure every row has its checkbox and shows the current-day marker."""
        for row in range(self.lerntag_list.count()):
            item = self.lerntag_list.item(row)
            number = item.data(Qt.ItemDataRole.UserRole)
            row_widget = self.lerntag_list.itemWidget(item)
            if row_widget is None:
                row_widget = self._create_lerntag_row(number)
                self.lerntag_list.setItemWidget(item, row_widget)
            is_current = number == self._current
            font = self._fixed_font()
            font.setBold(is_current)
            row_widget.label.setFont(font)
            row_widget.label.setText(f"{'▶' if is_current else ' '} {number} - {self._topics[number]}")
            item.setSizeHint(row_widget.sizeHint())
        self._update_progress_view()

    def _create_lerntag_row(self, number: str) -> QWidget:
        # The label ignores mouse presses, so they reach the list and start a drag.
        row_widget = QWidget()
        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(4, 0, 0, 0)
        row_widget.checkbox = QCheckBox()
        row_widget.checkbox.setChecked(number in self._done)
        row_widget.checkbox.toggled.connect(lambda checked: self._set_done(number, checked))
        row_widget.label = QLabel()
        layout.addWidget(row_widget.checkbox)
        layout.addWidget(row_widget.label, 1)
        return row_widget

    def _set_done(self, number: str, done: bool) -> None:
        if done:
            self._done.add(number)
        else:
            self._done.discard(number)
        self._update_progress_view()

    def _move_selected_lerntage(self, delta: int) -> None:
        """Move the selected rows one step up (-1) or down (+1)."""
        rows = sorted(self.lerntag_list.row(item) for item in self.lerntag_list.selectedItems())
        if not rows or rows[0] + delta < 0 or rows[-1] + delta >= self.lerntag_list.count():
            return
        for row in rows if delta < 0 else reversed(rows):
            self.lerntag_list.insertItem(row + delta, self.lerntag_list.takeItem(row))
        for row in rows:  # the row widgets are recreated by _refresh_lerntag_rows
            self.lerntag_list.item(row + delta).setSelected(True)

    def _set_current_lerntag(self) -> None:
        if item := self.lerntag_list.currentItem():
            self._current = item.data(Qt.ItemDataRole.UserRole)
            self._refresh_lerntag_rows()

    def _reset_lerntag_order(self) -> None:
        rows = self._lerntag_rows()
        self._fill_lerntag_list(sorted((n for n, _ in rows), key=int), {n for n, done in rows if done})

    def _selected_lerntag(self) -> str | None:
        return self._current if self.lerntag_list.count() else None

    def _setup_autocreate_option(
        self,
        layout: QVBoxLayout,
        button: QRadioButton,
        checked: bool,
        tooltip: str,
        label_text: str,
    ) -> None:
        button_layout = QHBoxLayout()
        button.setChecked(checked)
        button_layout.addWidget(button, 0)
        button_layout.insertWidget(1, self._info_icon_label(tooltip))
        label = QLabel(label_text)
        label.setWordWrap(True)
        button_layout.addWidget(label, 1)
        layout.addLayout(button_layout)

    def _setup_main_content(self, right_layout: QVBoxLayout) -> None:
        self.settings_frame = QFrame(self._content)  # parented now, or its size is unknown before show
        self.settings_frame.setVisible(self._autocreate)
        settings_layout = QVBoxLayout()
        settings_layout.setContentsMargins(0, 0, 0, 0)

        settings_layout.addSpacing(10)
        self.weekdays = QGroupBox("Wochentage für den Lernplan:")
        weekdays_layout = QHBoxLayout()
        self.weekday_buttons = []
        for weekday, check in zip(
            ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], self._wochentage
        ):
            button = QCheckBox(weekday)
            button.setChecked(check)
            self.weekday_buttons.append(button)
            weekdays_layout.addWidget(button)
        self.weekdays.setLayout(weekdays_layout)
        settings_layout.addWidget(self.weekdays)
        self._setup_extra_days(settings_layout)

        settings_layout.addSpacing(10)
        self._setup_lerntag_list(settings_layout)
        self._setup_extra_choices(settings_layout, self._top100, self._create_subchapter_decks, self._include_unfinished)
        self._setup_yield_group(settings_layout, self._highyield_stark, self._highyield_leicht, self._normyield, self._lowyield)

        autocreate_group_box = QGroupBox("Vergangene Lerntage:")
        autocreate_options_layout = QVBoxLayout()
        autocreate_options_layout.setContentsMargins(5, 5, 5, 5)

        # (attribute, checked, tooltip, label)
        options = [
            (
                "autocreate_due_button",
                self._autocreate_due,
                "Erstellt einen Auswahlstapel (<code>!FÄLLIGE KARTEN VERGANGENER LERNTAGE</code>) mit allen fälligen Karten aus vergangenen Lerntagen.",
                "Ich will die relevanten Lernplan‑Karten im Anki‑Algorithmus während des Lernplanes regelmäßig wiederholen. (Standard)",
            ),
            (
                "autocreate_previous_button",
                self._autocreate_previous,
                "Erstellt die Auswahlstapel <code>!LERNTAG&nbsp;XX</code> jeden Tag neu, sammelt dabei alle (nicht nur fällige) Karten ein.<br>Die lange Liste an Lerntag-Stapeln ist dann unter <code>!VORHERIGE&nbsp;LERNTAGE</code> zu finden.",
                "Ich will einzelne Lerntage später nochmal spezifisch wiederholen.",
            ),
            (
                "autocreate_no_previous_button",
                not (self._autocreate_due or self._autocreate_previous),
                "Nur <code>!LERNTAG&nbsp;XX</code> wird kreiert, alle gelernten Karten fallen in die ganz normale Rotation zurück.<br>Macht eigentlich nur Sinn, wenn Du schon seit dem 5. Semester mit Ankizin lernst und im Lernplan nur auffrischst.",
                "Ich will nur die relevanten Lernplan‑Karten ausgewählt haben.",
            ),
        ]
        self.autocreate_button_group = QButtonGroup(self)
        for attr, checked, tooltip, label_text in options:
            button = QRadioButton()
            setattr(self, attr, button)
            self._setup_autocreate_option(autocreate_options_layout, button, checked, tooltip, label_text)
            self.autocreate_button_group.addButton(button)

        autocreate_group_box.setLayout(autocreate_options_layout)
        settings_layout.addWidget(autocreate_group_box)
        self._setup_progress(settings_layout)
        self.settings_frame.setLayout(settings_layout)
        right_layout.addWidget(self.settings_frame)

    def _setup_action_buttons(self, right_layout: QVBoxLayout) -> None:
        box = QDialogButtonBox()
        role = QDialogButtonBox.ButtonRole
        self.confirm_button = box.addButton("Speichern und loslernen!", role.AcceptRole)
        self.confirm_button.clicked.connect(self.create_lerntag_deck_wrapper)
        self.save_button = box.addButton("Speichern", role.AcceptRole)
        self.save_button.clicked.connect(self.save_and_close)
        self.deactivate_button = box.addButton("Lernplan-Manager deaktivieren", role.DestructiveRole)
        self.deactivate_button.clicked.connect(self.deactivate_lernplan_manager)
        right_layout.addWidget(box)
        self._sync_buttons(self._autocreate)

    def _sync_buttons(self, active: bool) -> None:
        """Show the buttons that fit the state and highlight the main one."""
        self.confirm_button.setVisible(active)
        self.deactivate_button.setVisible(active)
        self.save_button.setVisible(not active)
        (self.confirm_button if active else self.save_button).setDefault(True)

    def toggle_settings(self, checked):
        self.settings_frame.setVisible(checked)
        self._sync_buttons(checked)
        self._fit_to_content()

    def save_and_close(self):
        self.save_config()
        self.accept()

    def deactivate_lernplan_manager(self):
        self.autocreate_button.setChecked(False)
        self.toggle_settings(False)
        self.save_config()
        self.accept()

    def closeEvent(self, event):
        self.save_config()
        event.ignore()
        self.reject()

    def _update_section(self, conf: dict, section: dict, settings: LerntagSettings, mark_today: bool) -> None:
        rows = self._lerntag_rows()
        section["lerntag_order"] = [number for number, _ in rows]
        past_days = section.setdefault("past_days", [])
        for number, done in rows:
            set_past_day(past_days, int(number), done)
        # the day being left counts as learned, even if its checkbox was not ticked
        update_past_days(section.get("lerntag"), settings.lerntag, conf)
        super()._update_section(conf, section, settings, mark_today)

        section["autocreate"] = self.autocreate_button.isChecked()
        section["autocreate_due"] = self.autocreate_due_button.isChecked()
        section["autocreate_previous"] = self.autocreate_previous_button.isChecked()
        section["wochentage"] = [button.isChecked() for button in self.weekday_buttons]
        section["extra_days"] = sorted(d.isoformat() for d in self._extra_days)
        section["skip_days"] = sorted(d.isoformat() for d in self._skip_days)
        section["kreuzen_tage"] = self._kreuzen_spin.value()
        m2 = self._m2_selected()
        section["m2_date"] = m2.isoformat() if m2 else None
        # Only mark "today is handled" when decks were created (or on first activation),
        # otherwise merely closing the dialog would skip today's automatic day change.
        if mark_today or "last_updated" not in section:
            today = effective_today(mw.col)
            section["last_updated"] = today.isoformat()
            section["last_due_updated"] = today.isoformat()

    def _rebuild_kwargs(self) -> dict:
        return {
            "prefix": LERNTAG_PREFIX,
            "cleanup": True,
            "previous": self.autocreate_previous_button.isChecked(),
            "due": self.autocreate_due_button.isChecked(),
            "past_days": _get_config().get("lernplan", {}).get("past_days", []),
        }

    def _info_icon_label(self, tooltip: str) -> QLabel:
        dummy = QCheckBox()
        icon = dummy.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        result = QLabel("")
        pixmap = icon.pixmap(dummy.iconSize())
        result.setPixmap(pixmap)
        result.setToolTip(tooltip)
        result.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        return result


def open_lernplan_manager(self):
    # Check if Ankizin is installed
    if not check_ankizin_installation():
        return

    dialog = LernplanManagerDialog(mw)
    # dialog.setFixedSize(dialog.sizeHint())
    dialog.exec()


def open_lerntag_deck_creator(self):
    # Check if Ankizin is installed
    if not check_ankizin_installation():
        return

    dialog = LerntagDeckCreatorDialog(mw)
    # dialog.setFixedSize(dialog.sizeHint())
    dialog.exec()
