from aqt import mw
from aqt.operations import CollectionOp
from aqt.qt import *
from aqt.utils import showWarning

from ..constants import ADDON_DIR_NAME
from .lernplan_decks import (
    LERNTAG_PREFIX,
    LerntagSettings,
    effective_today,
    get_lerntag_list,
    get_lerntag_order,
    is_past_day,
    rebuild_lernplan_decks,
    set_past_day,
    update_past_days,
)
from .utils import check_ankizin_installation, report_result

DEFAULT_WOCHENTAGE = [True] * 5 + [False] * 2


def _get_config() -> dict:
    """Get addon config or return empty dict if not configured."""
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    return conf if conf is not None else {}


class LerntagDeckCreatorDialog(QDialog):
    def __init__(self, parent, conf_key: str = "man_lernplan"):
        super().__init__(parent)
        self._conf_key = conf_key
        self.setWindowTitle("Lerntag-Auswahlstapel erstellen")

        main_layout = QHBoxLayout(self)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self._load_config()
        self._setup_logo(main_layout)

        right_layout = QVBoxLayout()
        self._setup_explanation(right_layout)
        self._setup_main_content(right_layout)
        self._setup_action_buttons(right_layout)

        main_layout.addLayout(right_layout)
        self.setWindowIcon(QIcon("icons:ankizin.png"))

    def _load_config(self) -> None:
        conf = _get_config()
        lernplan_conf = conf.get(self._conf_key, {})
        settings = LerntagSettings.from_conf(lernplan_conf)
        self._lerntag = settings.lerntag
        self._highyield_stark = settings.highyield_stark
        self._highyield_leicht = settings.highyield_leicht
        self._lowyield = settings.lowyield
        self._top100 = settings.top100
        self._normyield = lernplan_conf.get("normyield", True)
        self._create_subchapter_decks = settings.subchapters

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
    ) -> None:
        extra_choices_group_box = QGroupBox()
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
        yield_group_box = QGroupBox()
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

    def _setup_action_buttons(self, right_layout: QVBoxLayout) -> None:
        buttons_layout = QHBoxLayout()
        confirm_btn = QPushButton("Stapel erstellen!")
        confirm_btn.setFixedWidth(200)
        confirm_btn.clicked.connect(self.create_lerntag_deck_wrapper)
        buttons_layout.addWidget(confirm_btn)
        buttons_layout.addStretch()
        right_layout.addLayout(buttons_layout)

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
        )

    def _update_section(self, conf: dict, section: dict, settings: LerntagSettings, mark_today: bool) -> None:
        """Hook: write the settings into `section` (= conf[self._conf_key])."""
        section.update(settings.to_conf())

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
        kwargs = self._rebuild_kwargs()
        CollectionOp(
            mw, lambda col: rebuild_lernplan_decks(col, settings, **kwargs)
        ).success(report_result).with_progress(
            "Lerntag-Karten werden gesammelt..."
        ).run_in_background()
        self.accept()

    def _rebuild_kwargs(self) -> dict:
        # Hook for subclass: prefix, cleanup, previous, due, past_days
        return {"prefix": "Lerntag "}

class LernplanManagerDialog(LerntagDeckCreatorDialog):
    def __init__(self, parent):
        super().__init__(parent, conf_key="lernplan")

    def _load_config(self) -> None:
        super()._load_config()
        conf = _get_config()
        lernplan_conf = conf.get("lernplan", {})
        self._autocreate = lernplan_conf.get("autocreate", False)
        self._autocreate_due = lernplan_conf.get("autocreate_due", True)
        self._autocreate_previous = lernplan_conf.get("autocreate_previous", False)
        self._autocreate_no_previous = lernplan_conf.get("autocreate_no_previous", False)
        self._wochentage = lernplan_conf.get("wochentage", DEFAULT_WOCHENTAGE)
        self._order = get_lerntag_order(mw.col, lernplan_conf)
        self._topics = {n: t.replace("_", " ") for n, t in get_lerntag_list(mw.col)}
        self._past_days = lernplan_conf.get("past_days", [])

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

    def _setup_lerntag_list(self, layout: QVBoxLayout) -> None:
        layout.addWidget(QLabel(
            "<b>Lerntage:</b> Reihenfolge per Drag & Drop ändern, "
            "Haken = bereits gelernt, ▶ = aktueller Lerntag"
        ))
        self.lerntag_list = QListWidget()
        self.lerntag_list.setFont(self._fixed_font())
        self.lerntag_list.setMinimumHeight(220)
        self.lerntag_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.lerntag_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._current = self._lerntag
        done = {n for n in self._order if is_past_day(self._past_days, int(n))}
        self._fill_lerntag_list(self._order, done)
        layout.addWidget(self.lerntag_list)

        buttons_layout = QHBoxLayout()
        current_btn = QPushButton("Als aktuellen Lerntag setzen")
        current_btn.clicked.connect(self._set_current_lerntag)
        buttons_layout.addWidget(current_btn)
        reset_btn = QPushButton("Reihenfolge zurücksetzen")
        reset_btn.clicked.connect(self._reset_lerntag_order)
        buttons_layout.addWidget(reset_btn)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

    def _lerntag_rows(self) -> list[tuple[str, bool]]:
        """(number, done) in the order currently shown."""
        items = [self.lerntag_list.item(row) for row in range(self.lerntag_list.count())]
        return [(i.data(Qt.ItemDataRole.UserRole), i.checkState() == Qt.CheckState.Checked) for i in items]

    def _fill_lerntag_list(self, order: list[str], done: set[str]) -> None:
        self.lerntag_list.clear()
        for number in order:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, number)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if number in done else Qt.CheckState.Unchecked)
            self.lerntag_list.addItem(item)
        self._refresh_current_marker()

    def _refresh_current_marker(self) -> None:
        for row in range(self.lerntag_list.count()):
            item = self.lerntag_list.item(row)
            number = item.data(Qt.ItemDataRole.UserRole)
            is_current = number == self._current
            item.setText(f"{'▶' if is_current else ' '} {number} - {self._topics[number]}")
            font = item.font()
            font.setBold(is_current)
            item.setFont(font)

    def _set_current_lerntag(self) -> None:
        if item := self.lerntag_list.currentItem():
            self._current = item.data(Qt.ItemDataRole.UserRole)
            self._refresh_current_marker()

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
        self.settings_frame = QFrame()
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

        settings_layout.addSpacing(10)
        self._setup_lerntag_list(settings_layout)
        self._setup_extra_choices(settings_layout, self._top100, self._create_subchapter_decks)
        self._setup_yield_group(settings_layout, self._highyield_stark, self._highyield_leicht, self._normyield, self._lowyield)

        autocreate_group_box = QGroupBox()
        autocreate_options_layout = QVBoxLayout()
        autocreate_options_layout.setContentsMargins(5, 5, 5, 5)

        self.autocreate_due_button = QRadioButton()
        self._setup_autocreate_option(
            autocreate_options_layout,
            self.autocreate_due_button,
            self._autocreate_due,
            "Erstellt einen Auswahlstapel (<code>!FÄLLIGE KARTEN VERGANGENER LERNTAGE</code>) mit allen fälligen Karten aus vergangenen Lerntagen.",
            "Ich will die relevanten Lernplan‑Karten im Anki‑Algorithmus während des Lernplanes regelmäßig wiederholen. (Standard)",
        )

        self.autocreate_previous_button = QRadioButton()
        self._setup_autocreate_option(
            autocreate_options_layout,
            self.autocreate_previous_button,
            self._autocreate_previous,
            "Erstellt die Auswahlstapel <code>!LERNTAG&nbsp;XX</code> jeden Tag neu, sammelt dabei alle (nicht nur fällige) Karten ein.<br>Die lange Liste an Lerntag-Stapeln ist dann unter <code>!VORHERIGE&nbsp;LERNTAGE</code> zu finden.",
            "Ich will einzelne Lerntage später nochmal spezifisch wiederholen.",
        )

        self.autocreate_no_previous_button = QRadioButton()
        self._setup_autocreate_option(
            autocreate_options_layout,
            self.autocreate_no_previous_button,
            self._autocreate_no_previous,
            "Nur <code>!LERNTAG&nbsp;XX</code> wird kreiert, alle gelernten Karten fallen in die ganz normale Rotation zurück.<br>Macht eigentlich nur Sinn, wenn Du schon seit dem 5. Semester mit Ankizin lernst und im Lernplan nur auffrischst.",
            "Ich will nur die relevanten Lernplan‑Karten ausgewählt haben.",
        )

        self.autocreate_button_group = QButtonGroup(self)
        self.autocreate_button_group.addButton(self.autocreate_due_button)
        self.autocreate_button_group.addButton(self.autocreate_previous_button)
        self.autocreate_button_group.addButton(self.autocreate_no_previous_button)

        autocreate_group_box.setLayout(autocreate_options_layout)
        settings_layout.addWidget(autocreate_group_box)

        buttons_layout = QHBoxLayout()

        confirm_btn = QPushButton("Speichern und loslernen!")
        confirm_btn.setFixedWidth(200)
        confirm_btn.clicked.connect(self.create_lerntag_deck_wrapper)
        buttons_layout.addWidget(confirm_btn)

        buttons_layout.addSpacing(10)

        self.deactivate_button = QPushButton("Lernplan-Manager deaktivieren")
        self.deactivate_button.setFixedWidth(240)
        self.deactivate_button.setVisible(self._autocreate)
        self.deactivate_button.clicked.connect(self.deactivate_lernplan_manager)
        buttons_layout.addWidget(self.deactivate_button)

        buttons_layout.addStretch()

        settings_layout.addLayout(buttons_layout)
        self.settings_frame.setLayout(settings_layout)
        right_layout.addWidget(self.settings_frame)

    def _setup_action_buttons(self, right_layout: QVBoxLayout) -> None:
        self.save_button = QPushButton("Speichern")
        self.save_button.setFixedWidth(120)
        self.save_button.setVisible(not self._autocreate)
        self.save_button.clicked.connect(self.save_and_close)
        right_layout.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignLeft)

    def toggle_settings(self, checked):
        self.settings_frame.setVisible(checked)
        self.save_button.setVisible(not checked)
        self.deactivate_button.setVisible(checked)
        self.updateGeometry()
        self.resize(0, 0)
        self.adjustSize()

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
        section["autocreate_no_previous"] = self.autocreate_no_previous_button.isChecked()
        section["wochentage"] = [button.isChecked() for button in self.weekday_buttons]
        # Only mark "today is handled" when decks were created (or on first activation),
        # otherwise merely closing the dialog would skip today's automatic day change.
        if mark_today or "last_updated" not in section:
            today = effective_today(mw.col)
            section["last_updated"] = today.isoformat()
            section["last_due_updated"] = today.isoformat()
            section["lernplan_started_on"] = today.weekday()

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
